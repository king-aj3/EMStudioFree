# SPDX-License-Identifier: LGPL-2.1-or-later
"""Conjugate heat transfer — solid and fluid solved TOGETHER.

Every thermal case here so far imposes a condition on the cable surface: a
wall temperature, or a wall heat flux. That is an assumption about the answer.
What a cable actually does is generate heat inside the copper, conduct it out
through insulation, and hand it to the air at whatever interface temperature
makes the two fluxes match. Conjugate heat transfer solves that coupling
instead of assuming one side of it.

WHAT THIS ANCHORS ON
--------------------
The same strategy as the cavity and the wind case: prove the method where the
answer is EXACT, and be explicit about where it stops being exact.

With gravity set to zero the fluid cannot convect, so a two-region stack is
pure conduction in series and has a closed-form answer needing no citation:

    q      = (T_hot - T_cold) / (L_s/k_s + L_f/k_f)
    T_int  = T_hot - q * L_s/k_s

⚠ And a second, sharper check falls out of it: for a LINEAR profile on uniform
cells the cell-average equals the analytic mean exactly, so

    mean(T_solid) = (T_hot + T_int)/2      mean(T_fluid) = (T_int + T_cold)/2

hold to solver tolerance and are MESH-INSENSITIVE. A wrong coupling — the
classic being an interface that transmits temperature but not flux, or one
where a region's kappa is silently ignored — moves the interface temperature
and breaks both.

⚠ **This validates the COUPLING, not convection.** g = 0 is what makes the
answer exact; it is also what removes the buoyancy the real cable problem
depends on. The next rung is the same two regions with gravity restored,
anchored against the existing bundle-factor work.

THE v2512 RECIPE, which is not obvious and was read off the shipped tutorial
(`tutorials/basic/chtMultiRegionFoam/2DImplicitCyclic`) rather than guessed:

    blockMesh -> topoSet (make one cellZone per region)
              -> splitMeshRegions -cellZones -overwrite
              -> changeDictionary -region <each>
              -> chtMultiRegionFoam

⚠ `splitMeshRegions` NAMES the interface patches `<region>_to_<neighbour>`.
Nothing declares that name; it is generated, and a changeDictionary entry that
does not match it leaves the interface with a default BC and the solve quietly
answers a different problem.

⚠ The coupling BC in v2512 is `compressible::turbulentTemperatureRadCoupledMixed`.
The older `...CoupledBaffleMixed` name is gone.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["ChtCase", "GapNusselt", "gap_nusselt", "write_cht",
           "SOLID_REGION", "FLUID_REGION"]

SOLID_REGION = "slab"
FLUID_REGION = "gap"


@dataclass
class ChtCase:
    """A 1-D two-region conduction stack: solid slab against a fluid gap."""

    t_hot: float = 350.0            # K, outer face of the solid
    t_cold: float = 300.0           # K, outer face of the fluid
    l_solid: float = 0.020          # m
    l_fluid: float = 0.005          # m
    k_solid: float = 0.10           # W/m/K — an insulator, so the two
    #                                 resistances are COMPARABLE. With copper
    #                                 the solid drop is ~0.006 % of the total
    #                                 and the interface check asserts nothing.
    cp_fluid: float = 1005.0
    mu_fluid: float = 1.8e-5
    pr_fluid: float = 0.7
    rho_fluid: float = 1.2
    rho_solid: float = 200.0
    cp_solid: float = 900.0
    n_solid: int = 20               # cells across each region
    n_fluid: int = 20
    iterations: int = 2000
    width: float = 0.002            # z extent (the empty direction)

    # --- buoyancy ----------------------------------------------------------
    #: Gravity, m/s^2, acting along -y. ⚠ ZERO is what makes the conduction
    #: anchor exact. Non-zero turns this into conjugate NATURAL CONVECTION and
    #: the closed form no longer applies except in the low-Ra limit.
    gravity: float = 0.0
    #: Cavity height. Only meaningful with gravity: it is the dimension a
    #: convection cell turns over in, and the length scale in Ra.
    height: float = 0.020
    #: Cells up the cavity. ⚠ ONE cell here means no convection can form at
    #: all, whatever g says — the case would silently return the conduction
    #: answer and look like a validated buoyant solve.
    n_y: int = 1
    #: Boussinesq expansion coefficient, 1/K. Same convention as the cavity
    #: case (`solvers/openfoam/writer.py`), so the two Ra agree.
    beta: float = 3.3e-3
    t_ref: float = 300.0
    #: Target Rayleigh number. When set with gravity on, mu is DERIVED to hit
    #: it exactly, exactly as the cavity case derives nu and alpha.
    target_ra: float = 0.0

    def __post_init__(self):
        if self.t_hot <= self.t_cold:
            raise ValueError("the hot face must be hotter than the cold face")
        for name in ("l_solid", "l_fluid", "k_solid", "n_solid", "n_fluid"):
            if getattr(self, name) <= 0:
                raise ValueError("%s must be positive" % name)

    @property
    def buoyant(self):
        """Is this a natural-convection case at all?

        ⚠ BOTH conditions. Gravity with one cell up the cavity cannot convect,
        and cells with no gravity have nothing to drive them — either alone
        gives the conduction answer while looking like a buoyant case.
        """
        return self.gravity > 0.0 and self.n_y > 1

    @property
    def ra_length(self):
        """The length scale in Ra: the GAP WIDTH, not the cavity height.

        ⚠ This was the height and that was WRONG. A side-heated vertical gap
        is governed by the distance the buoyant layer has to cross — the gap
        width — with the aspect ratio H/L entering separately. Every standard
        vertical-cavity correlation (Berkovsky-Polevikov, MacGregor & Emery,
        ElSherbiny) is written that way.

        Measured cost of the error: at a nominal Ra 1e6 on the HEIGHT, the
        width-based Ra was only 1e6*(5/20)^3 ~ 1.6e4 and the solve returned
        Nu 1.014 — 1.4 % above conduction, i.e. essentially no convection,
        from a case that claimed Ra 1e6.
        """
        return self.l_fluid

    @property
    def aspect(self):
        """Cavity aspect ratio H/L — a parameter of the correlations, not Ra."""
        return self.height / self.l_fluid

    def rayleigh_for(self, dt):
        """Ra at an arbitrary driving temperature difference.

        ⚠ The fluid does NOT see `t_hot - t_cold`: the solid takes part of the
        drop. The physically meaningful Ra uses the SOLVED interface
        temperature, so this is what a measured comparison should quote.
        """
        if not self.buoyant or dt <= 0:
            return 0.0
        nu = self.mu / self.rho_fluid
        alpha = nu / self.pr_fluid
        return (self.gravity * self.beta * dt * self.ra_length ** 3
                / (nu * alpha))

    @property
    def mu(self):
        """Viscosity, DERIVED from the target Rayleigh number when buoyant.

        Ra = g*beta*dT*L^3 / (nu*alpha) and Pr = nu/alpha, so
        nu = sqrt(g*beta*dT*L^3*Pr / Ra) and mu = rho0*nu. `target_ra` is
        NOMINAL — it uses the full hot-to-cold drop, because the interface
        temperature is not known until the case is solved.
        """
        if not (self.buoyant and self.target_ra > 0.0):
            return self.mu_fluid
        dt = self.t_hot - self.t_cold
        nu = (self.gravity * self.beta * dt * self.ra_length ** 3
              * self.pr_fluid / self.target_ra) ** 0.5
        return self.rho_fluid * nu

    @property
    def rayleigh(self):
        """Nominal Ra from the properties actually WRITTEN — inverse of `mu`.

        Kept so a gate can assert the round trip rather than trust the algebra.
        """
        return self.rayleigh_for(self.t_hot - self.t_cold)

    @property
    def k_fluid(self):
        """Fluid conductivity implied by Cp, mu and Pr. kappa = Cp*mu/Pr."""
        return self.cp_fluid * self.mu / self.pr_fluid

    @property
    def r_solid(self):
        """Thermal resistance of the solid layer, per unit area."""
        return self.l_solid / self.k_solid

    @property
    def r_fluid(self):
        return self.l_fluid / self.k_fluid

    @property
    def flux(self):
        """EXACT through-flux, W/m^2. Series resistances."""
        return (self.t_hot - self.t_cold) / (self.r_solid + self.r_fluid)

    @property
    def t_interface(self):
        """EXACT interface temperature, K."""
        return self.t_hot - self.flux * self.r_solid

    @property
    def t_solid_mean(self):
        """Exact mean over the solid: a linear profile between two knowns."""
        return 0.5 * (self.t_hot + self.t_interface)

    @property
    def t_fluid_mean(self):
        return 0.5 * (self.t_interface + self.t_cold)


@dataclass(frozen=True)
class GapNusselt:
    """The convective measurement of a solved buoyant CHT case."""

    q: float          # W/m^2 through-flux, recovered from the solid
    t_interface: float  # K, the SOLVED mean interface temperature
    dt_gap: float     # K, the drop the fluid actually sees
    nu: float         # gap Nusselt number: actual flux / pure-conduction flux
    ra: float         # Ra at dt_gap — the interface-referenced Rayleigh number


def gap_nusselt(case, t_solid_mean):
    """Nu of the fluid gap, recovered from the SOLVED solid mean temperature.

    The solid cannot convect, so in steady state each of its columns is
    linear and the solid mean identifies the mean interface temperature:

        q     = 2*k_solid*(T_hot - mean(T_solid)) / L_solid
        T_int = T_hot - q*R_solid
        Nu    = q*R_fluid / (T_int - T_cold)
        Ra    = rayleigh_for(T_int - T_cold)

    ⚠ Nu is referenced to the SOLVED interface drop, not the nominal
    hot-to-cold drop — the fluid never sees the full drop, the solid takes
    its share, and quoting Ra/Nu at the nominal drop overstates both. This
    is the exact recovery validated against the recorded 08-14 study run
    (Nu 1.8768 / q 11.6040 / Ra 9.536e5 reproduced to the digit) and the
    measurement behind the fixed-mesh verification (Nu 6.8529 at 40x60).

    ⚠ Lateral (vertical) conduction inside the solid perturbs the
    column-linearity this rests on; with k_solid 0.1 and A = 4 the effect is
    far inside the correlation window the gate asserts. A second instrument
    (a wallHeatFlux patch integral) agreed to 0.7 % when cross-checked
    (2026-08-18 bisection, step 2).
    """
    q = 2.0 * case.k_solid * (case.t_hot - t_solid_mean) / case.l_solid
    t_int = case.t_hot - q * case.r_solid
    dt_gap = t_int - case.t_cold
    if dt_gap <= 0:
        raise ValueError(
            "recovered gap drop %.4g K is not positive — the solid mean "
            "%.4g K is not from a converged solve of this case" %
            (dt_gap, t_solid_mean))
    nu = q * case.r_fluid / dt_gap
    return GapNusselt(q=q, t_interface=t_int, dt_gap=dt_gap, nu=nu,
                      ra=case.rayleigh_for(dt_gap))


def region_patches(case_dir, region):
    """Patch names in a split region's mesh, in file order.

    ⚠ DISCOVERED, not assumed. `splitMeshRegions` generates the interface
    patch as `<region>_to_<neighbour>`, and nothing in the case declares that
    name — so a writer that hard-codes it produces a field whose interface
    entry silently matches nothing, leaving the coupled boundary at its default
    and answering a different problem. Reading the mesh is the only honest way
    to know what to write.
    """
    path = os.path.join(case_dir, "constant", region, "polyMesh", "boundary")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise ValueError("cannot read %s: %s" % (path, exc))

    names, depth, current = [], 0, None
    types = {}
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("//") or not line:
            continue
        # A patch is a bare word whose NEXT meaningful line opens a block.
        if depth == 1 and line and not any(
                c in line for c in "{};()") and not line[0].isdigit():
            for nxt in lines[i + 1:]:
                nxt = nxt.strip()
                if not nxt or nxt.startswith("//"):
                    continue
                if nxt.startswith("{"):
                    names.append(line)
                    current = line
                break
        elif current and line.startswith("type"):
            types.setdefault(current, line.split()[-1].rstrip(";"))
        depth += line.count("(") + line.count("{")
        depth -= line.count(")") + line.count("}")
    if not names:
        raise ValueError("no patches found in %s" % path)
    _PATCH_TYPES[(os.path.abspath(case_dir), region)] = types
    return names


#: Patch TYPES from the last read, keyed by (case, region). ⚠ An `empty` patch
#: needs `type empty;` in EVERY field — give it `zeroGradient` instead and the
#: solver rejects the case. The 2-D (buoyant) mesh has one; the 1-D stack does
#: not, so this cannot be assumed either way.
_PATCH_TYPES = {}


def region_patch_types(case_dir, region):
    """{patch: mesh type} for a split region, reading the mesh if needed."""
    key = (os.path.abspath(case_dir), region)
    if key not in _PATCH_TYPES:
        region_patches(case_dir, region)
    return _PATCH_TYPES.get(key, {})


def _boundary(entries):
    return ("boundaryField\n{\n%s}\n"
            % "".join("    %s\n    {\n%s    }\n" % (name, body)
                      for name, body in entries))


def write_region_fields(case_dir, case=None):
    """Write every region's 0/ fields AFTER the split. Returns {region: patches}.

    ⚠ This REPLACES `changeDictionary`, deliberately. changeDictionary MERGES
    into the fields the split produced, and on v2512 that merge crashes
    outright on `U` — silently, with a truncated log and (through a pipeline)
    an exit status of 0. Writing the files whole removes the merge, and with
    it a dependency on a tool that is failing for reasons we do not control.
    """
    case = case or ChtCase()
    t_mid = 0.5 * (case.t_hot + case.t_cold)
    found = {}

    for region, kappa_method, outer_patch, outer_t in (
            (SOLID_REGION, "solidThermo", "hot", case.t_hot),
            (FLUID_REGION, "fluidThermo", "cold", case.t_cold)):
        patches = region_patches(case_dir, region)
        ptypes = region_patch_types(case_dir, region)
        found[region] = patches

        def _generic(kind, value):
            """Per-patch entry, honouring `empty` where the MESH says so."""
            out = []
            for p in patches:
                if ptypes.get(p) == "empty":
                    out.append((p, "        type            empty;\n"))
                else:
                    out.append((p, "        type            %s;\n"
                                   "        value           uniform %s;\n"
                                % (kind, value)))
            return out
        interface = [p for p in patches if p.startswith(region + "_to_")]
        if len(interface) != 1:
            raise ValueError(
                "region %r has %d interface patches (%r); expected exactly one "
                "named %s_to_<neighbour>"
                % (region, len(interface), patches, region))
        iface = interface[0]

        t_entries = []
        for p in patches:
            if ptypes.get(p) == "empty":
                t_entries.append((p, "        type            empty;\n"))
            elif p == iface:
                t_entries.append((p,
                    "        type            compressible::"
                    "turbulentTemperatureRadCoupledMixed;\n"
                    "        Tnbr            T;\n        qrNbr           none;\n"
                    "        qr              none;\n        kappaMethod     %s;\n"
                    "        value           uniform %.10g;\n" % (kappa_method, t_mid)))
            elif p == outer_patch:
                t_entries.append((p, "        type            fixedValue;\n"
                                     "        value           uniform %.10g;\n" % outer_t))
            else:
                t_entries.append((p, "        type            zeroGradient;\n"))

        _put(case_dir, "0/%s/T" % region,
             _header("volScalarField", "T", "0")
             + "dimensions      [0 0 0 1 0 0 0];\n"
               "internalField   uniform %.10g;\n\n" % t_mid
             + _boundary(t_entries))

        if region == SOLID_REGION:
            # ⚠ The split copies EVERY field into EVERY region, so the solid
            # carries flow fields that mean nothing there. The shipped tutorial
            # removes exactly `nut alphat epsilon k U p_rgh` — and NOT `p`:
            # heSolidThermo still reads pressure for its equation of state, and
            # deleting it aborts the solve with "cannot find file 0/<solid>/p".
            for junk in ("U", "p_rgh", "alphat", "nut", "k", "epsilon"):
                try:
                    os.remove(os.path.join(case_dir, "0", region, junk))
                except OSError:
                    pass
            continue

        _put(case_dir, "0/%s/U" % region,
             _header("volVectorField", "U", "0")
             + "dimensions      [0 1 -1 0 0 0 0];\n"
               "internalField   uniform (0 0 0);\n\n"
             + _boundary(_generic("fixedValue", "(0 0 0)")))
        _put(case_dir, "0/%s/p" % region,
             _header("volScalarField", "p", "0")
             + "dimensions      [1 -1 -2 0 0 0 0];\n"
               "internalField   uniform 1e5;\n\n"
             + _boundary(_generic("calculated", "1e5")))
        _put(case_dir, "0/%s/p_rgh" % region,
             _header("volScalarField", "p_rgh", "0")
             + "dimensions      [1 -1 -2 0 0 0 0];\n"
               "internalField   uniform 1e5;\n\n"
             + _boundary(_generic("fixedFluxPressure", "1e5")))
        _put(case_dir, "0/%s/alphat" % region,
             _header("volScalarField", "alphat", "0")
             + "dimensions      [1 -1 -1 0 0 0 0];\n"
               "internalField   uniform 0;\n\n"
             + _boundary(_generic("calculated", "0")))
    return found


def _header(cls, obj, loc):
    return ("FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
            "    class       %s;\n    location    \"%s\";\n    object      %s;\n}\n\n"
            % (cls, loc, obj))


def _put(case_dir, rel, text):
    path = os.path.join(case_dir, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("/*--------------------------------*- C++ -*----------------"
                 "------------------*\\\n\\*----------------------------------"
                 "---------------------------------------*/\n")
        fh.write(text)


def write_cht(case_dir, case=None):
    """Write a complete two-region conduction case. Returns the ChtCase."""
    case = case or ChtCase()
    total = case.l_solid + case.l_fluid
    w = case.width
    h = case.height if case.n_y > 1 else case.width

    # --- mesh: ONE mesh, two blocks, split later by cellZone ---------------
    # ⚠ n_y > 1 makes this 2-D, which is what a convection cell needs. With
    # n_y == 1 it is the 1-D conduction stack and buoyancy cannot form.
    vtx = "\n".join("    (%.10g %.10g %.10g)" % v for v in [
        (0.0, 0.0, 0.0), (0.0, h, 0.0), (0.0, h, w), (0.0, 0.0, w),
        (case.l_solid, 0.0, 0.0), (case.l_solid, h, 0.0),
        (case.l_solid, h, w), (case.l_solid, 0.0, w),
        (total, 0.0, 0.0), (total, h, 0.0), (total, h, w), (total, 0.0, w)])
    _put(case_dir, "system/blockMeshDict",
         _header("dictionary", "blockMeshDict", "system")
         + "scale   1;\n\nvertices\n(\n%s\n);\n\n" % vtx
         + "blocks\n(\n"
           "    hex (0 4 5 1 3 7 6 2) (%d %d 1) simpleGrading (1 1 1)\n"
           "    hex (4 8 9 5 7 11 10 6) (%d %d 1) simpleGrading (1 1 1)\n);\n\n"
           % (case.n_solid, case.n_y, case.n_fluid, case.n_y)
         + "edges ();\n\nboundary\n(\n"
           "    hot { type wall; faces ( (0 3 2 1) ); }\n"
           "    cold { type wall; faces ( (8 9 10 11) ); }\n"
           # Top and bottom are ADIABATIC walls: with gravity they are what
           # closes the convection cell, and the temperature drop must stay
           # between the hot and cold faces.
           #
           # ⚠ THE FACE SETS BELOW WERE SWAPPED until 2026-08-18, and the bug
           # cost four days of misdiagnosis. With vertices 1=(0,h,0) and
           # 3=(0,0,w), the faces (0 1 5 4)... lie on the Z-planes and
           # (0 4 7 3)... on the Y-planes. Labelling the y-planes `empty` put
           # gravity's direction OUT of the solved plane and made the z-planes
           # no-slip walls ONE CELL apart — Hele-Shaw drag that crushed the
           # convection to Nu ~1.9 regardless of Ra, scale-invariantly, while
           # every conduction anchor still passed exactly (conduction along x
           # never touches the y/z labels). The solver never complained: empty
           # faces just drop their boundary contribution. Verify GEOMETRY, not
           # labels — the gate now recomputes each face's plane from the
           # vertex coordinates.
           "    topBottom { type wall; faces ( (0 4 7 3) (4 8 11 7) "
           "(1 2 6 5) (5 6 10 9) ); }\n"
           "    frontAndBack { type empty; faces ( (0 1 5 4) (4 5 9 8) "
           "(3 7 6 2) (7 11 10 6) ); }\n);\n\nmergePatchPairs ();\n")

    # --- cellZones, one per region -----------------------------------------
    _put(case_dir, "system/topoSetDict",
         _header("dictionary", "topoSetDict", "system")
         + "actions\n(\n"
           "    { name %(s)sCells; type cellSet; action new; source boxToCell;\n"
           "      box (-1e6 -1e6 -1e6) (%(xs).10g 1e6 1e6); }\n"
           "    { name %(s)s; type cellZoneSet; action new; source setToCellZone;\n"
           "      set %(s)sCells; }\n"
           "    { name %(f)sCells; type cellSet; action new; source boxToCell;\n"
           "      box (%(xs).10g -1e6 -1e6) (1e6 1e6 1e6); }\n"
           "    { name %(f)s; type cellZoneSet; action new; source setToCellZone;\n"
           "      set %(f)sCells; }\n);\n"
         % {"s": SOLID_REGION, "f": FLUID_REGION,
            "xs": case.l_solid})

    _put(case_dir, "constant/regionProperties",
         _header("dictionary", "regionProperties", "constant")
         + "regions\n(\n    fluid       (%s)\n    solid       (%s)\n);\n"
         % (FLUID_REGION, SOLID_REGION))

    # ⚠ ZERO gravity is what makes the conduction answer exact. Non-zero turns
    # this into conjugate NATURAL CONVECTION — see the module docstring.
    _put(case_dir, "constant/g",
         _header("uniformDimensionedVectorField", "g", "constant")
         # `-0.0` formats as "-0", which is the same number and a different
         # string — and the gate reads the string.
         + "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 %.10g 0);\n"
         % (-case.gravity if case.gravity else 0.0))

    # --- materials ----------------------------------------------------------
    _put(case_dir, "constant/%s/thermophysicalProperties" % SOLID_REGION,
         _header("dictionary", "thermophysicalProperties", "constant")
         + "thermoType\n{\n    type            heSolidThermo;\n"
           "    mixture         pureMixture;\n    transport       constIso;\n"
           "    thermo          hConst;\n    equationOfState rhoConst;\n"
           "    specie          specie;\n    energy          sensibleEnthalpy;\n}\n\n"
           "mixture\n{\n    specie { molWeight 12; }\n"
           "    transport { kappa %.10g; }\n"
           "    thermodynamics { Hf 0; Cp %.10g; }\n"
           "    equationOfState { rho %.10g; }\n}\n"
         % (case.k_solid, case.cp_solid, case.rho_solid))

    # ⚠ kappa is NOT set directly for the fluid: it comes from Cp*mu/Pr, which
    # is why ChtCase derives k_fluid the same way instead of carrying a second
    # number that could disagree with the dictionary.
    # ⚠ THE EQUATION OF STATE IS WHAT DECIDES WHETHER BUOYANCY EXISTS AT ALL.
    # With `rhoConst` the density cannot respond to temperature, so gravity is
    # inert and the case silently returns the conduction answer no matter what
    # `g` says — a "buoyant" solve that never convects. `Boussinesq` gives
    # rho = rho0*(1 - beta*(T - T0)), which is the same model the cavity case
    # uses, so the two agree on what Ra means.
    if case.buoyant:
        eos = "Boussinesq"
        eos_block = ("    equationOfState { rho0 %.10g; T0 %.10g; beta %.10g; }\n"
                     % (case.rho_fluid, case.t_ref, case.beta))
    else:
        eos = "rhoConst"
        eos_block = "    equationOfState { rho %.10g; }\n" % case.rho_fluid
    _put(case_dir, "constant/%s/thermophysicalProperties" % FLUID_REGION,
         _header("dictionary", "thermophysicalProperties", "constant")
         + "thermoType\n{\n    type            heRhoThermo;\n"
           "    mixture         pureMixture;\n    transport       const;\n"
           "    thermo          hConst;\n    equationOfState %s;\n"
           "    specie          specie;\n    energy          sensibleEnthalpy;\n}\n\n"
           "mixture\n{\n    specie { molWeight 28.9; }\n"
           "    thermodynamics { Hf 0; Cp %.10g; }\n"
           "    transport { mu %.10g; Pr %.10g; }\n%s}\n"
         % (eos, case.cp_fluid, case.mu, case.pr_fluid, eos_block))
    _put(case_dir, "constant/%s/turbulenceProperties" % FLUID_REGION,
         _header("dictionary", "turbulenceProperties", "constant")
         + "simulationType laminar;\n")

    # --- initial fields on the WHOLE mesh; splitMeshRegions maps them --------
    # These are only SEEDS: splitMeshRegions maps them, then
    # `write_region_fields` replaces each region's copy whole. They still have
    # to be valid for the un-split mesh, which is why frontAndBack is empty.
    t_mid = 0.5 * (case.t_hot + case.t_cold)
    empty2d = "    frontAndBack { type empty; }\n"
    _put(case_dir, "0/T", _header("volScalarField", "T", "0")
         + "dimensions      [0 0 0 1 0 0 0];\ninternalField   uniform %.10g;\n\n"
           "boundaryField\n{\n    hot { type fixedValue; value uniform %.10g; }\n"
           "    cold { type fixedValue; value uniform %.10g; }\n"
           "    topBottom { type zeroGradient; }\n%s}\n"
         % (t_mid, case.t_hot, case.t_cold, empty2d))
    for obj, cls, dims, internal, kind, val in (
            ("p", "volScalarField", "[1 -1 -2 0 0 0 0]", "1e5", "calculated", "1e5"),
            ("p_rgh", "volScalarField", "[1 -1 -2 0 0 0 0]", "1e5",
             "fixedFluxPressure", "1e5"),
            ("U", "volVectorField", "[0 1 -1 0 0 0 0]", "(0 0 0)",
             "fixedValue", "(0 0 0)"),
            ("alphat", "volScalarField", "[1 -1 -1 0 0 0 0]", "0",
             "calculated", "0")):
        _put(case_dir, "0/%s" % obj, _header(cls, obj, "0")
             + "dimensions      %s;\ninternalField   uniform %s;\n\n"
               "boundaryField\n{\n"
               "    \"(hot|cold|topBottom)\" { type %s; value uniform %s; }\n"
               "%s}\n" % (dims, internal, kind, val, empty2d))

    # --- per-region BCs, INCLUDING the generated interface patch name -------
    for region, other, kappa_method, outer in (
            (SOLID_REGION, FLUID_REGION, "solidThermo", ("hot", case.t_hot)),
            (FLUID_REGION, SOLID_REGION, "fluidThermo", ("cold", case.t_cold))):
        t_block = (
            "T\n{\n    internalField   uniform %.10g;\n\n"
            "    boundaryField\n    {\n"
            "        %s\n        {\n            type            fixedValue;\n"
            "            value           uniform %.10g;\n        }\n\n"
            "        \"%s_to_.*\"\n        {\n"
            "            type            compressible::"
            "turbulentTemperatureRadCoupledMixed;\n"
            "            Tnbr            T;\n            qrNbr           none;\n"
            "            qr              none;\n            kappaMethod     %s;\n"
            "            value           uniform %.10g;\n        }\n\n"
            "        sides\n        {\n            type            zeroGradient;\n"
            "        }\n    }\n}\n"
            % (t_mid, outer[0], outer[1], region, kappa_method, t_mid))

        # ⚠ EVERY fluid field needs the generated interface patch named, not
        # just T. splitMeshRegions creates `<region>_to_<neighbour>` AFTER the
        # 0/ fields were written, so it inherits a `calculated` default — and
        # the solver aborts on the first momentum solve with "trying to solve
        # for a field with a default boundary condition". T alone is not
        # enough, which is easy to miss because T is the field CHT is about.
        extra = ""
        if region == FLUID_REGION:
            extra = (
                # ⚠ fixedValue, NOT noSlip. splitMeshRegions leaves the new
                # patch as `calculated` WITH a `value`, changeDictionary MERGES
                # rather than replaces, and noSlip takes no `value` — the merged
                # dictionary crashes changeDictionary outright, with no FOAM
                # error and a truncated log. fixedValue accepts the value that
                # is already there, so the merge stays consistent.
                "\nU\n{\n    boundaryField\n    {\n"
                "        \"%(r)s_to_.*\" { type fixedValue; "
                "value uniform (0 0 0); }\n    }\n}\n"
                "\np_rgh\n{\n    boundaryField\n    {\n"
                "        \"%(r)s_to_.*\" { type fixedFluxPressure; "
                "value uniform 1e5; }\n    }\n}\n"
                "\np\n{\n    boundaryField\n    {\n"
                "        \"%(r)s_to_.*\" { type calculated; value uniform 1e5; }\n"
                "    }\n}\n"
                "\nalphat\n{\n    boundaryField\n    {\n"
                "        \"%(r)s_to_.*\" { type calculated; value uniform 0; }\n"
                "    }\n}\n" % {"r": region})

        _put(case_dir, "system/%s/changeDictionaryDict" % region,
             _header("dictionary", "changeDictionaryDict", "system")
             + t_block + extra)

        _put(case_dir, "system/%s/fvSchemes" % region,
             _header("dictionary", "fvSchemes", "system")
             + "ddtSchemes      { default steadyState; }\n"
               "gradSchemes     { default Gauss linear; }\n"
               "divSchemes\n{\n    default none;\n"
               "    div(phi,U)      bounded Gauss upwind;\n"
               "    div(phi,K)      bounded Gauss linear;\n"
               "    div(phi,h)      bounded Gauss upwind;\n"
               "    div(phi,e)      bounded Gauss upwind;\n"
               "    div(phi,Ekp)    bounded Gauss linear;\n"
               "    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;\n}\n"
               "laplacianSchemes { default Gauss linear corrected; }\n"
               "interpolationSchemes { default linear; }\n"
               "snGradSchemes   { default corrected; }\n")

        if region == SOLID_REGION:
            _put(case_dir, "system/%s/fvSolution" % region,
                 _header("dictionary", "fvSolution", "system")
                 + "solvers\n{\n    h\n    {\n        solver PCG;\n"
                   "        preconditioner DIC;\n        tolerance 1e-10;\n"
                   "        relTol 0;\n    }\n}\n\n"
                   "SIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n"
                   "    residualControl { h 1e-6; }\n}\n\n"
                   "relaxationFactors { equations { h 1; } }\n")
        else:
            # ⚠ `momentumPredictor no` was the expensive mistake. With it off,
            # velocity is only ever updated through the pressure correction,
            # so on a BUOYANCY-driven flow — where momentum is the whole story
            # — the pressure equation is left to do all the work. Measured: it
            # hit GAMG's 1000-iteration cap on EVERY step while the energy
            # residual was already ~1e-8, and a run took the better part of an
            # hour. Buoyant cases want the predictor ON.
            #
            # ⚠ `residualControl` is the other half: without it the solve
            # cannot stop when it is done, so a converged case grinds on to
            # `endTime` regardless. Iterations become a ceiling, not a cost.
            _put(case_dir, "system/%s/fvSolution" % region,
                 _header("dictionary", "fvSolution", "system")
                 + "solvers\n{\n"
                   "    rho { solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0; }\n"
                   "    p_rgh\n    {\n        solver          GAMG;\n"
                   "        tolerance       1e-8;\n        relTol          0.01;\n"
                   "        smoother        GaussSeidel;\n"
                   "        nCellsInCoarsestLevel 10;\n"
                   "        mergeLevels     1;\n"
                   "        cacheAgglomeration on;\n    }\n"
                   "    \"(U|h|k|epsilon)\" { solver PBiCGStab; preconditioner DILU; "
                   "tolerance 1e-9; relTol 0.01; }\n}\n\n"
                   "SIMPLE\n{\n    momentumPredictor yes;\n"
                   "    nNonOrthogonalCorrectors 0;\n    pRefCell 0;\n"
                   "    pRefValue 1e5;\n"
                   "    residualControl { p_rgh 1e-5; U 1e-5; h 1e-6; }\n}\n\n"
                   "relaxationFactors { fields { p_rgh 0.7; } "
                   "equations { U 0.3; h 0.7; } }\n")

    _put(case_dir, "system/fvSchemes",
         _header("dictionary", "fvSchemes", "system")
         + "ddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\n"
           "divSchemes { default none; }\nlaplacianSchemes { default Gauss linear corrected; }\n"
           "interpolationSchemes { default linear; }\nsnGradSchemes { default corrected; }\n")
    _put(case_dir, "system/fvSolution",
         _header("dictionary", "fvSolution", "system")
         + "solvers {}\nSIMPLE { nNonOrthogonalCorrectors 0; }\n")

    _put(case_dir, "system/controlDict",
         _header("dictionary", "controlDict", "system")
         # ⚠ The STEADY variant. `chtMultiRegionFoam` is the transient solver
         # and demands a PIMPLE block; these schemes are steadyState, and the
         # answer wanted here is the converged one, not a history.
         + "application     chtMultiRegionSimpleFoam;\nstartFrom       startTime;\n"
           "startTime       0;\nstopAt          endTime;\nendTime         %d;\n"
           "deltaT          1;\nwriteControl    timeStep;\nwriteInterval   %d;\n"
           "purgeWrite      0;\nwriteFormat     ascii;\nwritePrecision  10;\n"
           "writeCompression off;\ntimeFormat      general;\ntimePrecision   6;\n"
           "runTimeModifiable false;\nmaxCo           1;\n"
           "maxDi           10;\nadjustTimeStep  no;\n"
         % (case.iterations, case.iterations))
    return case
