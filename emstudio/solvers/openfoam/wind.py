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
    #: safe as a sizing guess and useless as an answer.
    st_guess: float = 0.2

    def __post_init__(self):
        if self.reynolds <= 0:
            raise ValueError("Reynolds number must be positive")
        if self.d_ref <= 0:
            raise ValueError("reference diameter must be positive")
        if self.radius_ratio <= 2.0:
            raise ValueError("the far field must be at least 2 diameters out")
        if self.n_r < 4 or self.n_theta < 4:
            raise ValueError("need at least 4 cells in each direction")

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
        """Starting step. The solver then adjusts it to hold `co_max`.

        Sized so one shedding period is resolved by ~400 steps even before
        the Courant control takes over — a period resolved by a handful of
        steps yields a Strouhal number set by the time step rather than by
        the flow.
        """
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
        :data:`TURBULENT_RE`, where a laminar solve of any kind stops being
        the right physics regardless of how the time derivative is treated.
        """
        if self.reynolds >= TURBULENT_RE:
            return False
        return self.transient or self.steady_is_valid

    def validity_note(self):
        """The caveat a caller must surface, or empty when there is none."""
        if self.reynolds >= TURBULENT_RE:
            return (
                "Re %.4g is beyond what a LAMINAR solve can represent, steady "
                "or not: the boundary layer and wake are turbulent, and no "
                "time-stepping scheme fixes a missing turbulence model. A "
                "number from this case is not a wind load. Real antenna "
                "loading is Re 1e5-1e6 and needs a validated turbulence model."
                % self.reynolds)
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
    r_i = case.d_ref / 2.0
    r_o = r_i * case.radius_ratio
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
                a = math.radians(k * 90.0)
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
            a = math.radians((k + 0.5) * 90.0)
            for r, lo, hi in ((r_i, i_(k) + off, i_(k + 1) + off),
                              (r_o, o_(k) + off, o_(k + 1) + off)):
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
        put("system/controlDict",
            _header("dictionary", "controlDict", "system")
            + "application     pimpleFoam;\nstartFrom       startTime;\n"
              "startTime       0;\nstopAt          endTime;\n"
              "endTime         %.10g;\ndeltaT          %.10g;\n"
              "writeControl    runTime;\nwriteInterval   %.10g;\n"
              "purgeWrite      2;\nwriteFormat     ascii;\nwritePrecision  10;\n"
              "writeCompression off;\ntimeFormat      general;\ntimePrecision   6;\n"
              "runTimeModifiable false;\n"
              "adjustTimeStep  yes;\nmaxCo           %.10g;\n"
              "maxDeltaT       %.10g;\n\n"
              "functions\n{\n    forces\n    {\n        type            forces;\n"
              "        libs            (forces);\n        patches         (cylinder);\n"
              "        rho             rhoInf;\n        rhoInf          %.10g;\n"
              "        CofR            (0 0 0);\n        writeControl    timeStep;\n"
              "        writeInterval   1;\n    }\n}\n"
            % (case.end_time, case.delta_t, case.end_time / n_writes,
               case.co_max, case.delta_t * 20.0, case.rho))

        # `backward` is second order in time. Euler is stable but damps the
        # oscillation this case exists to measure, which shows up as a
        # Strouhal number that drifts with the time step.
        put("system/fvSchemes", _header("dictionary", "fvSchemes", "system")
            + "ddtSchemes      { default backward; }\n"
              "gradSchemes     { default Gauss linear; }\n"
              "divSchemes\n{\n    default none;\n"
              "    div(phi,U)      Gauss linearUpwind grad(U);\n"
              "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n}\n"
              "laplacianSchemes { default Gauss linear corrected; }\n"
              "interpolationSchemes { default linear; }\n"
              "snGradSchemes   { default corrected; }\n")
        # ⚠ No `bounded` on div(phi,U) here: that term exists to help a steady
        # solve converge and is not wanted in a transient one.
        put("system/fvSolution", _header("dictionary", "fvSolution", "system")
            + "solvers\n{\n"
              "    p { solver GAMG; tolerance 1e-8; relTol 0.01; smoother GaussSeidel; }\n"
              "    pFinal { $p; relTol 0; }\n"
              "    \"(U|UFinal)\" { solver smoothSolver; smoother symGaussSeidel; "
              "tolerance 1e-9; relTol 0; }\n"
              "}\n\nPIMPLE\n{\n    nOuterCorrectors 2;\n    nCorrectors 2;\n"
              "    nNonOrthogonalCorrectors 0;\n}\n")
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
