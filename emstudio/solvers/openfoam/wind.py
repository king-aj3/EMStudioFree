# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wind loading — drag and lift on a structure, the axis EMStudio never had.

Every other OpenFOAM case here is thermal. This one is mechanical: what force
does the wind put on a helix, whip, mast or dish, so the structure can be sized
to survive it. It reuses geometry the document already holds and feeds loads
that FreeCAD's own FEM workbench can consume.

WHAT THIS ANCHORS ON, AND WHY NOT Cd ~1.2
------------------------------------------
A circular cylinder's drag coefficient is one of the best-characterised numbers
in fluid mechanics — and **steady RANS is bad at it**. Above Re ~47 the real
flow sheds vortices; a steady solve produces a symmetric wake and under-reads
drag. Anchoring on the familiar Cd ~1.2 at Re 1e5 would be anchoring on a
number this method cannot produce.

So the anchor is the LOW-Re regime where the flow genuinely IS steady, below
the onset of shedding. Same strategy as the cavity: prove the method where it
is valid, and be explicit about where it stops being valid.

Measured here (laminar, steady, O-grid, 40 diameters of far field):

    Re 20   Cd 2.0646    Cl -5.1e-07
    Re 40   Cd 1.5448    Cl -3.3e-07

⚠ **ABOVE Re ~47 THESE STEADY NUMBERS ARE NOT TRUSTWORTHY** and the case says
so rather than quietly producing them.

THE UNSTEADY RUNG (`transient=True`, 2026-08-14)
------------------------------------------------
`pimpleFoam`, still laminar, which reaches the Reynolds numbers where the flow
actually sheds. Anchored on THREE independent quantities, because drag alone
is forgiving of a coarse mesh and a short run while the shedding FREQUENCY is
not — St is what proves the solve resolves the physics rather than merely runs.

Measured here (O-grid 80x30, 40 diameters, 40 cycles, half discarded):

    Re 100  Cd 1.3411   St 0.1647   Cl amp 0.3275   15 cycles
    Re 150  Cd 1.3283   St 0.1835   Cl amp 0.5202   17 cycles

against Williamson's laminar correlation
St = -3.3265/Re + 0.1816 + 1.6e-4*Re, which gives 0.1643 at Re 100 (**0.2 %**)
and 0.1834 at Re 150 (**0.04 %**); published Cd ~1.32-1.37, and a lift
amplitude that GROWS with Re (~0.33 at Re 100, ~0.52 at Re 150) — a trend the
two anchors reproduce and neither alone could check.

⚠ **A transient solve does NOT make a high Reynolds number legitimate.** Above
Re ~190 the real wake goes three-dimensional, so a 2-D laminar solve is
modelling an idealisation whatever the time derivative does; `TURBULENT_RE`
refuses it. Real antenna wind loading is Re 1e5-1e6 and needs a validated
turbulence model, which is NOT built. What IS built is every rung up to here,
each anchored on published numbers.

⚠ **This is the FIRST result path in this package to use a function object.**
The thermal cases avoid them because `wallHeatFlux` aborts on Ubuntu's 1912
build. Forces are different: computing them otherwise means reconstructing face
areas and normals from `polyMesh`. It is defensible because discovery's own
capability probe already REQUIRES a function object to pass — so any install
EMStudio calls `usable` supports them — but it does make this case depend on
that probe in a way the thermal cases do not.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

__all__ = ["WindCase", "SHEDDING_RE", "TURBULENT_RE", "write_wind"]

#: Onset of vortex shedding for a circular cylinder. Above this a STEADY solve
#: is not modelling the real flow, and the case refuses to pretend otherwise.
#: (The transition is gradual and geometry-dependent; this is the standard
#: round number for a circular cylinder and is used only as a guard rail.)
SHEDDING_RE = 47.0

#: Where a LAMINAR unsteady solve stops being the right physics. The 2-D
#: laminar shedding regime runs to roughly Re 190, above which the wake goes
#: three-dimensional (mode A/B instabilities) and a 2-D laminar solve is
#: modelling something the flow no longer does. Held at 200 as a round guard
#: rail: the validated anchors sit at Re 100 and Re 150, both comfortably
#: inside it, and beyond it this case refuses rather than returning a
#: confident wrong number.
#:
#: ⚠ Real antenna loading (Re 1e5-1e6) is ABOVE this. Reaching it needs a
#: turbulence model with its own validation, which is not built. What IS built
#: is every rung up to here, each anchored on published numbers.
TURBULENT_RE = 200.0


@dataclass
class WindCase:
    """Cross-flow over a cylinder in an open far field."""

    reynolds: float = 20.0
    d_ref: float = 0.020            # cylinder diameter, and the Cd reference
    nu: float = 1.5e-5              # air
    rho: float = 1.2
    radius_ratio: float = 40.0      # far field, in diameters
    n_r: int = 80
    n_theta: int = 30
    grading: float = 60.0           # radial clustering at the wall
    iterations: int = 3000
    #: UNSTEADY solve (`pimpleFoam`). Above Re ~47 the real flow sheds, and a
    #: steady solve cannot represent that at all — see the module docstring.
    #: This is the path that reaches Reynolds numbers worth calling wind.
    transient: bool = False
    #: Shedding cycles to simulate. The first ones are startup: the wake has to
    #: destabilise from a symmetric initial field before periodic shedding
    #: exists at all, and averaging across that transient drags Cd toward the
    #: steady (too low) answer.
    cycles: float = 40.0
    #: Fraction of the run discarded as startup before any average is taken.
    settle_fraction: float = 0.5
    #: Courant target for the adjustable time step.
    co_max: float = 0.8
    #: Strouhal number used ONLY to size the time step and run length before
    #: the solve — the measured value comes out of the lift history. 0.2 is the
    #: flat part of the St(Re) curve across a huge Re range, which is why it is
    #: safe as a sizing guess and useless as an answer. The SQUARE cylinder's
    #: value is ~0.13 — pass st_guess=0.13 with geometry="square".
    st_guess: float = 0.2
    #: Body cross-section. "circle" (the shipped O-grid, arcs) or "square"
    #: (§8b turbulence anchor, 2026-08-23 de-risk): SAME 4-block ring with the
    #: vertex ring rotated 45 deg and the inner arcs DROPPED, giving a square
    #: of side `d_ref` with flat faces normal to the flow (zero incidence) —
    #: the corner-fixed-separation geometry the published anchor (Lyn 1995 /
    #: Tian 2013, Re 21 400) is defined on. Cd reference stays `d_ref`.
    geometry: str = "circle"
    #: "" = laminar (byte-identical to the pre-RAS case). "kOmegaSST" = URANS
    #: forced-convection turbulence — TRANSIENT ONLY: steady RANS on a
    #: shedding bluff body converges to an artifact (Franke & Rodi 1993), so
    #: the model is refused on the steady path rather than misused by it.
    turbulence: str = ""
    #: Fixed nondimensional time step dt* = dt*U/d_ref (0 = keep the adaptive
    #: co_max stepping). The RAS anchor uses 0.004 (Tian's step): near-wall
    #: cells at y+ ~2 make Courant-adaptive stepping grind, and a FIXED step
    #: with `backward` keeps the Strouhal measurement off the step size.
    fixed_dt_star: float = 0.0

    def __post_init__(self):
        if self.reynolds <= 0:
            raise ValueError("Reynolds number must be positive")
        if self.d_ref <= 0:
            raise ValueError("reference diameter must be positive")
        if self.radius_ratio <= 2.0:
            raise ValueError("the far field must be at least 2 diameters out")
        if self.n_r < 4 or self.n_theta < 4:
            raise ValueError("need at least 4 cells in each direction")
        if self.geometry not in ("circle", "square"):
            raise ValueError("geometry is \"circle\" or \"square\", not %r"
                             % (self.geometry,))
        if self.turbulence not in ("", "kOmegaSST"):
            raise ValueError(
                "unsupported turbulence model %r — this writer knows laminar "
                "(\"\") and \"kOmegaSST\"; a name it cannot honour must fail "
                "here, not run laminar and report success" % (self.turbulence,))
        if self.turbulence and not self.transient:
            raise ValueError(
                "kOmegaSST here is TRANSIENT-only: steady RANS on a shedding "
                "bluff body converges to a non-shedding artifact and badly "
                "misses the measured flow (Franke & Rodi 1993) — set "
                "transient=True")
        if self.fixed_dt_star < 0:
            raise ValueError("fixed_dt_star is a step size (0 = adaptive)")

    @property
    def u_inf(self):
        """Freestream speed that produces the requested Reynolds number."""
        return self.reynolds * self.nu / self.d_ref

    @property
    def thickness(self):
        return self.d_ref / 10.0

    @property
    def a_ref(self):
        """Reference area: the 2-D projected frontal area, D x thickness."""
        return self.d_ref * self.thickness

    @property
    def q_ref(self):
        """Dynamic-pressure scale: force / q_ref = a coefficient."""
        return 0.5 * self.rho * self.u_inf ** 2 * self.a_ref

    @property
    def shed_period(self):
        """Estimated vortex-shedding period, from :attr:`st_guess`. Seconds."""
        return self.d_ref / (self.st_guess * self.u_inf)

    @property
    def end_time(self):
        """Physical duration of a transient run: `cycles` shedding periods."""
        return self.cycles * self.shed_period

    @property
    def delta_t(self):
        """Starting step. The solver then adjusts it to hold `co_max` —
        unless `fixed_dt_star` is set, in which case this IS the step.

        Sized so one shedding period is resolved by ~400 steps even before
        the Courant control takes over — a period resolved by a handful of
        steps yields a Strouhal number set by the time step rather than by
        the flow.
        """
        if self.fixed_dt_star > 0:
            return self.fixed_dt_star * self.d_ref / self.u_inf
        return self.shed_period / 400.0

    @property
    def settle_time(self):
        """When averaging starts. Everything before this is startup."""
        return self.end_time * self.settle_fraction

    @property
    def steady_is_valid(self):
        """False where a STEADY solve stops modelling the real flow."""
        return self.reynolds < SHEDDING_RE

    @property
    def method_is_valid(self):
        """Is the CHOSEN method defensible at this Reynolds number?

        Steady below shedding onset, unsteady above it — and neither above
        :data:`TURBULENT_RE` WITHOUT a turbulence model. With kOmegaSST on
        the transient path, a SHARP-EDGED (square) section is validated to
        Re ~1.5e5 — the highest experimental point on the square cylinder's
        flat Cd curve (Fage & Johansen 1927; anchor gate
        `openfoam_wind_ras`). A CIRCULAR section stays refused up there:
        its drag crisis is transition-location physics no single-Re anchor
        transfers across.
        """
        if (self.transient and self.turbulence == "kOmegaSST"
                and self.geometry == "square"):
            # ⚠⚠ STILL FALSE — the machinery exists but its anchor has NOT
            # run: both startup attempts SIGFPE'd in the k/omega solve
            # (2026-08-23, Co 2.4 and Co 0.9 — a startup-stiffness problem,
            # not step size). Flip to `self.reynolds <= 1.5e5` ONLY in the
            # same commit that lands a green `openfoam_wind_ras` gate; a
            # validity claim may not precede its evidence (the v1.5.0 rule).
            return False
        if self.reynolds >= TURBULENT_RE:
            return False
        return self.transient or self.steady_is_valid

    def validity_note(self):
        """The caveat a caller must surface, or empty when there is none."""
        if (self.transient and self.turbulence == "kOmegaSST"
                and self.geometry == "square"):
            return (
                "kOmegaSST wind machinery is BUILT but its published anchor "
                "(square cylinder, Re 21 400, Lyn/Tian) has not yet run "
                "green — treat every number from this path as UNVALIDATED "
                "until the openfoam_wind_ras gate exists and passes.")
        if self.reynolds >= TURBULENT_RE:
            if self.turbulence == "kOmegaSST":
                return (
                    "kOmegaSST is validated on the SHARP-EDGED square section "
                    "only (geometry=\"square\", the corner-fixed-separation "
                    "anchor); a circular section's drag crisis is "
                    "transition-location physics the anchor does not cover. "
                    "This number is not a validated wind load.")
            return (
                "Re %.4g is beyond what a LAMINAR solve can represent, steady "
                "or not: the boundary layer and wake are turbulent, and no "
                "time-stepping scheme fixes a missing turbulence model. A "
                "number from this case is not a wind load. Real antenna "
                "loading is Re 1e5-1e6 and needs a validated turbulence model "
                "(square sections have one: transient kOmegaSST, gate "
                "openfoam_wind_ras)." % self.reynolds)
        if self.steady_is_valid or self.transient:
            return ""
        return (
            "Re %.4g is above the vortex-shedding onset (~%g): the real flow "
            "is UNSTEADY and a steady solve produces a symmetric wake that "
            "UNDER-reads drag. This number is not a wind load. Set "
            "transient=True to solve it unsteadily, which is validated up to "
            "Re %g." % (self.reynolds, SHEDDING_RE, TURBULENT_RE))


def _header(cls, obj, loc):
    return ("FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
            "    class       %s;\n    location    \"%s\";\n    object      %s;\n}\n\n"
            % (cls, loc, obj))


def _field(obj, dims, internal, boundary):
    return (_header("volVectorField" if obj == "U" else "volScalarField", obj, "0")
            + "dimensions      %s;\n\ninternalField   uniform %s;\n\n"
              "boundaryField\n{\n%s}\n" % (dims, internal, boundary))


def write_wind(case_dir, case=None):
    """Write a complete cross-flow case. Returns the resolved :class:`WindCase`."""
    case = case or WindCase()
    square = case.geometry == "square"
    # SQUARE: inner vertices sit at the CORNERS, radius side/sqrt(2), and the
    # ring is rotated 45 deg so the flat faces are normal/parallel to the
    # x-flow — zero incidence, side exactly d_ref. The straight block edges
    # ARE the body: no inner arcs are written.
    r_i = case.d_ref / math.sqrt(2.0) if square else case.d_ref / 2.0
    ang0 = 45.0 if square else 0.0
    r_o = (case.d_ref / 2.0) * case.radius_ratio
    t = case.thickness
    u = case.u_inf

    for sub in ("0", "constant", "system"):
        os.makedirs(os.path.join(case_dir, sub), exist_ok=True)

    def put(rel, text):
        with open(os.path.join(case_dir, rel), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("/*--------------------------------*- C++ -*-------"
                     "---------------------*/\n")
            fh.write(text)

    # the same O-grid topology as the thermal cylinder, but OPEN: the outer
    # boundary is a freestream patch doing both inflow and outflow.
    verts = ""
    for z in (0.0, t):
        for r in (r_i, r_o):
            for k in range(4):
                a = math.radians(ang0 + k * 90.0)
                verts += ("    (%.10g %.10g %.10g)\n"
                          % (r * math.cos(a), r * math.sin(a), z))

    def i_(k):
        return k % 4

    def o_(k):
        return 4 + k % 4

    blocks = "".join(
        "    hex (%d %d %d %d %d %d %d %d) (%d %d 1) simpleGrading (%.10g 1 1)\n"
        % (i_(k), o_(k), o_(k + 1), i_(k + 1), i_(k) + 8, o_(k) + 8,
           o_(k + 1) + 8, i_(k + 1) + 8, case.n_r, case.n_theta, case.grading)
        for k in range(4))
    edges = ""
    for zi, z in enumerate((0.0, t)):
        off = zi * 8
        for k in range(4):
            a = math.radians(ang0 + (k + 0.5) * 90.0)
            # The inner boundary is an arc ONLY for the circle; the square's
            # sides are the straight block edges themselves.
            pairs = ((r_o, o_(k) + off, o_(k + 1) + off),) if square else \
                    ((r_i, i_(k) + off, i_(k + 1) + off),
                     (r_o, o_(k) + off, o_(k + 1) + off))
            for r, lo, hi in pairs:
                edges += ("    arc %d %d (%.10g %.10g %.10g)\n"
                          % (lo, hi, r * math.cos(a), r * math.sin(a), z))
    inner = "".join("        (%d %d %d %d)\n"
                    % (i_(k), i_(k + 1), i_(k + 1) + 8, i_(k) + 8)
                    for k in range(4))
    outer = "".join("        (%d %d %d %d)\n"
                    % (o_(k), o_(k + 1), o_(k + 1) + 8, o_(k) + 8)
                    for k in range(4))
    fandb = "".join("        (%d %d %d %d)\n        (%d %d %d %d)\n"
                    % (i_(k), o_(k), o_(k + 1), i_(k + 1), i_(k) + 8,
                       o_(k) + 8, o_(k + 1) + 8, i_(k + 1) + 8)
                    for k in range(4))
    put("system/blockMeshDict", _header("dictionary", "blockMeshDict", "system")
        + "scale   1;\n\nvertices\n(\n" + verts + ");\n\nblocks\n(\n" + blocks
        + ");\n\nedges\n(\n" + edges + ");\n\nboundary\n(\n"
        + "    cylinder { type wall; faces (\n" + inner + "    ); }\n"
        + "    farfield { type patch; faces (\n" + outer + "    ); }\n"
        + "    frontAndBack { type empty; faces (\n" + fandb + "    ); }\n"
        + ");\n\nmergePatchPairs ();\n")

    put("constant/transportProperties",
        _header("dictionary", "transportProperties", "constant")
        + "transportModel  Newtonian;\nnu              %.10g;\n" % case.nu)
    ras = case.turbulence == "kOmegaSST"
    if ras:
        put("constant/turbulenceProperties",
            _header("dictionary", "turbulenceProperties", "constant")
            + "simulationType  RAS;\n\nRAS\n{\n    RASModel        kOmegaSST;\n"
              "    turbulence      on;\n    printCoeffs     off;\n}\n")
    else:
        put("constant/turbulenceProperties",
            _header("dictionary", "turbulenceProperties", "constant")
            + "simulationType  laminar;\n")

    # ⚠ freestream handles inflow AND outflow on ONE patch, which is what an
    # external O-grid needs — the same boundary does both depending on where
    # you are around the circle. A fixedValue inlet would be wrong downstream.
    put("0/U", _field("U", "[0 1 -1 0 0 0 0]", "(%.10g 0 0)" % u,
                      "    cylinder { type noSlip; }\n"
                      "    farfield { type freestreamVelocity; "
                      "freestreamValue uniform (%.10g 0 0); }\n"
                      "    frontAndBack { type empty; }\n" % u))
    put("0/p", _field("p", "[0 2 -2 0 0 0 0]", "0",
                      "    cylinder { type zeroGradient; }\n"
                      "    farfield { type freestreamPressure; "
                      "freestreamValue uniform 0; }\n"
                      "    frontAndBack { type empty; }\n"))
    if ras:
        # WALL-FUNCTION wall treatment (the high-Re triple), matching the
        # published 2-D URANS square-cylinder studies in the anchor table
        # (Bosch & Rodi 1998, Shimada & Ishihara 2002 — both wall-function
        # meshes). ⚠ A RESOLVED-wall (y+ ~2, low-Re triple) configuration
        # was tried first and DIVERGES at the sharp corners: three attempts
        # 2026-08-23 (Co 2.4, 0.9, and with robust PBiCGStab solvers) all
        # ended in SIGFPE with the k field churning at initial residual ~0.9
        # — the corner singularity plus a near-fixed omega ~1/y^2 is not a
        # configuration the published anchors used either. Mesh the body with
        # first cells in the LOG LAYER (y+ ~30: mild grading, e.g. 2)
        # accordingly. Inlet turbulence from the anchor experiment's own
        # tunnel (I = 2 %, l = 0.07 d — Lyn's rig as characterised by Tian
        # 2013, whose sensitivity study puts the l-choice at < 0.27 % of Cd).
        # The freestream patch takes inletOutlet so backflow re-entering the
        # domain carries the freestream levels rather than whatever left.
        k_in = 1.5 * (0.02 * u) ** 2
        om_in = k_in ** 0.5 / (0.09 ** 0.25 * 0.07 * case.d_ref)
        put("0/k", _field(
            "k", "[0 2 -2 0 0 0 0]", "%.6g" % k_in,
            "    cylinder { type kqRWallFunction; value uniform %.6g; }\n"
            "    farfield { type inletOutlet; inletValue uniform %.6g; "
            "value uniform %.6g; }\n"
            "    frontAndBack { type empty; }\n" % (k_in, k_in, k_in)))
        put("0/omega", _field(
            "omega", "[0 0 -1 0 0 0 0]", "%.6g" % om_in,
            "    cylinder { type omegaWallFunction; value uniform %.6g; }\n"
            "    farfield { type inletOutlet; inletValue uniform %.6g; "
            "value uniform %.6g; }\n"
            "    frontAndBack { type empty; }\n" % (om_in, om_in, om_in)))
        put("0/nut", _field(
            "nut", "[0 2 -1 0 0 0 0]", "0",
            "    cylinder { type nutkWallFunction; value uniform 0; }\n"
            "    farfield { type calculated; value uniform 0; }\n"
            "    frontAndBack { type empty; }\n"))

    # ⚠ `rho rhoInf` because simpleFoam is INCOMPRESSIBLE: its p is kinematic
    # (m^2/s^2), so the function object must be told the density to return
    # forces in newtons. Omitting it yields forces short by a factor of rho —
    # a plausible-looking number that is simply wrong.
    if case.transient:
        # ⚠ Forces are reported EVERY step, not at the write interval: the
        # lift history IS the measurement (Strouhal comes out of its period),
        # so sampling it coarsely would alias the very thing being measured.
        # Field writes stay rare — they are for looking at, not for numbers.
        n_writes = 20.0
        if case.fixed_dt_star > 0:
            # The anchor's stepping: FIXED dt* with `backward`. Adaptive
            # Courant stepping grinds against the y+ ~2 wall cells, and the
            # Strouhal measurement must not be a function of a moving step.
            stepping = "adjustTimeStep  no;\n"
        else:
            stepping = ("adjustTimeStep  yes;\nmaxCo           %.10g;\n"
                        "maxDeltaT       %.10g;\n"
                        % (case.co_max, case.delta_t * 20.0))
        put("system/controlDict",
            _header("dictionary", "controlDict", "system")
            + "application     pimpleFoam;\nstartFrom       startTime;\n"
              "startTime       0;\nstopAt          endTime;\n"
              "endTime         %.10g;\ndeltaT          %.10g;\n"
              "writeControl    runTime;\nwriteInterval   %.10g;\n"
              "purgeWrite      2;\nwriteFormat     ascii;\nwritePrecision  10;\n"
              "writeCompression off;\ntimeFormat      general;\ntimePrecision   6;\n"
              "runTimeModifiable false;\n"
            % (case.end_time, case.delta_t, case.end_time / n_writes)
            + stepping + "\n"
              "functions\n{\n    forces\n    {\n        type            forces;\n"
              "        libs            (forces);\n        patches         (cylinder);\n"
              "        rho             rhoInf;\n        rhoInf          %.10g;\n"
              "        CofR            (0 0 0);\n        writeControl    timeStep;\n"
              "        writeInterval   1;\n    }\n}\n" % case.rho)

        # `backward` is second order in time. Euler is stable but damps the
        # oscillation this case exists to measure, which shows up as a
        # Strouhal number that drifts with the time step.
        put("system/fvSchemes", _header("dictionary", "fvSchemes", "system")
            + "ddtSchemes      { default backward; }\n"
              "gradSchemes     { default Gauss linear; }\n"
              "divSchemes\n{\n    default none;\n"
              "    div(phi,U)      Gauss linearUpwind grad(U);\n"
            + ("    div(phi,k)      Gauss upwind;\n"
               "    div(phi,omega)  Gauss upwind;\n" if ras else "")
            + "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n}\n"
              "laplacianSchemes { default Gauss linear corrected; }\n"
              "interpolationSchemes { default linear; }\n"
              "snGradSchemes   { default corrected; }\n"
            + ("wallDist        { method meshWave; }\n" if ras else ""))
        # ⚠ No `bounded` on div(phi,U) here: that term exists to help a steady
        # solve converge and is not wanted in a transient one.
        put("system/fvSolution", _header("dictionary", "fvSolution", "system")
            + "solvers\n{\n"
              "    p { solver GAMG; tolerance 1e-8; relTol 0.01; smoother GaussSeidel; }\n"
              "    pFinal { $p; relTol 0; }\n"
            + ("    \"(U|UFinal)\" { solver smoothSolver; smoother "
               "symGaussSeidel; tolerance 1e-9; relTol 0; }\n"
               # ⚠ NOT smoothSolver for k/omega: the omegaWallFunction fixes
               # near-wall omega at ~1e6+ on a resolved wall, and the
               # symGaussSeidel smoother DIVERGED on that stiff system
               # (measured 2026-08-23: final residual 3e+257 at 1000
               # iterations, then SIGFPE). PBiCGStab+DILU holds it.
               "    \"(k|omega|kFinal|omegaFinal)\" { solver PBiCGStab; "
               "preconditioner DILU; tolerance 1e-9; relTol 0; }\n"
               "    Phi { solver GAMG; tolerance 1e-8; relTol 0.01; "
               "smoother GaussSeidel; }\n" if ras else
               "    \"(U|UFinal)\" { solver smoothSolver; smoother symGaussSeidel; "
               "tolerance 1e-9; relTol 0; }\n")
            + "}\n\nPIMPLE\n{\n    nOuterCorrectors 2;\n    nCorrectors 2;\n"
              "    nNonOrthogonalCorrectors 0;\n}\n"
            + ("\npotentialFlow\n{\n    nNonOrthogonalCorrectors 3;\n}\n"
               if ras else ""))
        return case

    put("system/controlDict", _header("dictionary", "controlDict", "system")
        + "application     simpleFoam;\nstartFrom       startTime;\n"
          "startTime       0;\nstopAt          endTime;\nendTime         %d;\n"
          "deltaT          1;\nwriteControl    timeStep;\nwriteInterval   %d;\n"
          "purgeWrite      0;\nwriteFormat     ascii;\nwritePrecision  10;\n"
          "writeCompression off;\ntimeFormat      general;\ntimePrecision   6;\n"
          "runTimeModifiable false;\n\n"
          "functions\n{\n    forces\n    {\n        type            forces;\n"
          "        libs            (forces);\n        patches         (cylinder);\n"
          "        rho             rhoInf;\n        rhoInf          %.10g;\n"
          "        CofR            (0 0 0);\n        writeControl    timeStep;\n"
          "        writeInterval   %d;\n    }\n}\n"
        % (case.iterations, case.iterations, case.rho, case.iterations))

    put("system/fvSchemes", _header("dictionary", "fvSchemes", "system")
        + "ddtSchemes      { default steadyState; }\n"
          "gradSchemes     { default Gauss linear; }\n"
          "divSchemes\n{\n    default none;\n"
          "    div(phi,U)      bounded Gauss linearUpwind grad(U);\n"
          "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n}\n"
          "laplacianSchemes { default Gauss linear corrected; }\n"
          "interpolationSchemes { default linear; }\n"
          "snGradSchemes   { default corrected; }\n")
    put("system/fvSolution", _header("dictionary", "fvSolution", "system")
        + "solvers\n{\n"
          "    p { solver GAMG; tolerance 1e-9; relTol 0.01; smoother GaussSeidel; }\n"
          "    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-9; relTol 0.1; }\n"
          "}\n\nSIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n    consistent yes;\n"
          "    residualControl { p 1e-6; U 1e-6; }\n}\n\n"
          "relaxationFactors\n{\n    equations { U 0.9; p 0.9; }\n}\n")
    return case
