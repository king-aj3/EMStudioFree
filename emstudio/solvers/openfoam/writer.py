# SPDX-License-Identifier: LGPL-2.1-or-later
"""Write a differentially-heated square-cavity case for buoyantBoussinesqSimpleFoam.

The cavity is the standard buoyancy benchmark and the reduced form of an RF
enclosure: a square box, hot left wall, cold right wall, adiabatic top and
bottom, one cell deep with ``empty`` front/back so it solves as 2-D.

WHY THE PHYSICAL PROPERTIES ARE DERIVED, NOT TYPED
--------------------------------------------------
The controlling group is the Rayleigh number

    Ra = g beta dT L^3 / (nu alpha),      Pr = nu / alpha

so Ra and Pr fix the flow and everything else is a free choice. Rather than
hand-tuning nu and beta until Ra comes out near the target — which is how a
case ends up quietly at Ra 9.4e4 while the report says 1e5 — this module takes
Ra and Pr as INPUTS and solves for ``nu`` and ``alpha`` exactly, holding
g, beta, dT and L at fixed reference values. :func:`rayleigh` recomputes Ra
from the written numbers so the round trip can be asserted.

⚠ **The Boussinesq solver's ``alphat``/``Prt`` are TURBULENT quantities.** The
laminar Prandtl number lives in ``constant/transportProperties`` as ``Pr``, and
the molecular diffusivity the solver actually uses is ``nu/Pr`` — NOT the
``alphat`` field, which is zero in a laminar run. Setting Pr in the wrong file
leaves the run laminar-but-wrong with no error.

⚠ **ESI flavour.** ``constant/turbulenceProperties`` (not Foundation's
``momentumTransport``), ``buoyantBoussinesqSimpleFoam``. A Foundation build
fails on the first dictionary read; the caller is expected to have checked the
fork through :mod:`emstudio.setup.openfoam`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["CavityCase", "rayleigh", "write_cavity"]

#: Held fixed so that a requested (Ra, Pr) maps to exactly one (nu, alpha).
#: Any self-consistent set works; these are ordinary air-like magnitudes and
#: keep the solved velocities in a range where the default relaxation is happy.
G = 9.81            # m/s^2
BETA = 3.3e-3       # 1/K   (~1/300 K, Boussinesq expansion coefficient)
L = 1.0             # m     cavity side
DT = 1.0            # K     hot wall minus cold wall
T_REF = 300.0       # K     Boussinesq reference temperature


def rayleigh(nu, alpha, g=G, beta=BETA, dt=DT, length=L):
    """Ra from the properties actually written. The inverse of the derivation.

    Kept public so a gate can assert the round trip instead of trusting that
    the algebra below stayed correct.
    """
    if nu <= 0 or alpha <= 0:
        raise ValueError("nu and alpha must be positive")
    return g * beta * dt * length ** 3 / (nu * alpha)


def _properties_for(ra, pr, dt=DT, width=L):
    """(nu, alpha) giving exactly this Ra and Pr.

    Ra = g b dT W^3 / (nu alpha) and Pr = nu / alpha
      => nu alpha = g b dT W^3 / Ra  and  nu = Pr alpha
      => alpha = sqrt(g b dT W^3 / (Ra Pr)),  nu = Pr alpha

    ⚠ dT and width default to the module constants, which is the shipped
    square-cavity contract — but they must track the CASE when a caller sets
    t_hot/t_cold or a non-square geometry, or the derivation quietly holds Ra
    for a cavity the case no longer describes (the latent trap the tall
    Betts & Bokhari case exposed: dt was 19.6 while the algebra assumed 1).
    """
    if ra <= 0:
        raise ValueError("Rayleigh number must be positive")
    if pr <= 0:
        raise ValueError("Prandtl number must be positive")
    if dt <= 0:
        raise ValueError("t_hot must exceed t_cold")
    if width <= 0:
        raise ValueError("cavity width must be positive")
    alpha = (G * BETA * dt * width ** 3 / (ra * pr)) ** 0.5
    return pr * alpha, alpha


@dataclass
class CavityCase:
    """Everything a written cavity case needs, and what it resolved to."""

    ra: float = 1.0e4
    pr: float = 0.71                 # air
    cells: int = 40                  # per side; the mesh is cells x cells x 1
    iterations: int = 2000
    t_hot: float = T_REF + DT / 2.0
    t_cold: float = T_REF - DT / 2.0
    #: Cavity width (the Ra length scale — hot-to-cold gap). The default is
    #: the module's original square metre; the tall Betts & Bokhari anchor is
    #: 0.076 m wide by 2.18 m high.
    width: float = L
    #: Cavity height; None = width (square, the shipped contract).
    height: float = None
    #: Cells up the height; None derives from the aspect ratio so cell aspect
    #: stays near 1 (a square cavity gets cells x cells, exactly as before).
    cells_y: int = None
    #: "" = laminar — byte-identical to the pre-T2 case. "kOmegaSST" = RAS
    #: with wall functions (T2 of docs/OPENFOAM_TURBULENCE_PLAN.md). Any
    #: other string raises: a model name the writer cannot honour must not
    #: pass silently — that is the v1.4.0 defect class.
    turbulence: str = ""

    def __post_init__(self):
        if self.turbulence not in ("", "kOmegaSST"):
            raise ValueError(
                "unsupported turbulence model %r — this writer knows laminar "
                "(\"\") and \"kOmegaSST\"; a name it cannot honour must fail "
                "here, not run laminar and report success" % (self.turbulence,))
        if self.height is not None and self.height <= 0:
            raise ValueError("cavity height must be positive")

    @property
    def height_m(self):
        return self.width if self.height is None else self.height

    @property
    def cells_up(self):
        if self.cells_y is not None:
            return int(self.cells_y)
        return max(2, int(round(self.cells * self.height_m / self.width)))

    @property
    def nu(self):
        return _properties_for(self.ra, self.pr, self.dt, self.width)[0]

    @property
    def alpha(self):
        return _properties_for(self.ra, self.pr, self.dt, self.width)[1]

    @property
    def ra_written(self):
        """Ra recomputed from the derived properties — must match .ra."""
        return rayleigh(self.nu, self.alpha, dt=self.dt, length=self.width)

    @property
    def dt(self):
        return self.t_hot - self.t_cold


def _header(cls, obj, loc):
    return (
        "FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
        "    class       %s;\n    location    \"%s\";\n    object      %s;\n}\n\n"
        % (cls, loc, obj))


def _field(obj, dims, internal, boundary):
    return (_header("volScalarField" if obj != "U" else "volVectorField",
                    obj, "0")
            + "dimensions      %s;\n\ninternalField   uniform %s;\n\n"
              "boundaryField\n{\n%s}\n" % (dims, internal, boundary))


def write_cavity(case_dir, case=None):
    """Write a complete cavity case. Returns the resolved :class:`CavityCase`.

    Everything is plain text — no OpenFOAM import, so this is unit-testable
    with no solver installed, which is what lets the offline gate run in CI.
    """
    case = case or CavityCase()
    nu, alpha = case.nu, case.alpha
    n = int(case.cells)
    if n < 2:
        raise ValueError("need at least 2 cells per side")

    for sub in ("0", "constant", "system"):
        os.makedirs(os.path.join(case_dir, sub), exist_ok=True)

    def put(rel, text):
        with open(os.path.join(case_dir, rel), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("/*--------------------------------*- C++ -*-------"
                     "---------------------*/\n")
            fh.write(text)

    # --- mesh: one hex block, `empty` front/back so the solve is 2-D --------
    W, H, ny = case.width, case.height_m, case.cells_up
    thick = W / n
    put("system/blockMeshDict", _header("dictionary", "blockMeshDict", "system") +
        "scale   1;\n\nvertices\n(\n"
        "    (0 0 0)\n    (%(W)g 0 0)\n    (%(W)g %(H)g 0)\n    (0 %(H)g 0)\n"
        "    (0 0 %(t)g)\n    (%(W)g 0 %(t)g)\n    (%(W)g %(H)g %(t)g)\n"
        "    (0 %(H)g %(t)g)\n);\n\n"
        "blocks\n(\n    hex (0 1 2 3 4 5 6 7) (%(n)d %(ny)d 1) simpleGrading (1 1 1)\n);\n\n"
        "edges ();\n\nboundary\n(\n"
        "    hot   { type wall;  faces ( (0 4 7 3) ); }\n"
        "    cold  { type wall;  faces ( (1 2 6 5) ); }\n"
        "    walls { type wall;  faces ( (0 1 5 4) (3 7 6 2) ); }\n"
        "    frontAndBack { type empty; faces ( (0 3 2 1) (4 5 6 7) ); }\n"
        ");\n\nmergePatchPairs ();\n"
        % {"W": W, "H": H, "t": thick, "n": n, "ny": ny})

    # --- physical properties ------------------------------------------------
    # Pr here is the LAMINAR Prandtl number; the solver forms the molecular
    # thermal diffusivity as nu/Pr. Prt is turbulent and inert in a laminar run.
    put("constant/transportProperties",
        _header("dictionary", "transportProperties", "constant") +
        "transportModel  Newtonian;\n"
        "nu              %.10g;\n"
        "beta            %.10g;\n"
        "TRef            %.10g;\n"
        "Pr              %.10g;\n"
        "Prt             0.85;\n" % (nu, BETA, T_REF, case.pr))

    ras = case.turbulence == "kOmegaSST"
    if ras:
        put("constant/turbulenceProperties",
            _header("dictionary", "turbulenceProperties", "constant") +
            "simulationType  RAS;\n\nRAS\n{\n    RASModel        kOmegaSST;\n"
            "    turbulence      on;\n    printCoeffs     off;\n}\n")
    else:
        put("constant/turbulenceProperties",
            _header("dictionary", "turbulenceProperties", "constant") +
            "simulationType  laminar;\n")

    put("constant/g", _header("uniformDimensionedVectorField", "g", "constant") +
        "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 -%.10g 0);\n" % G)

    # --- fields -------------------------------------------------------------
    put("0/T", _field(
        "T", "[0 0 0 1 0 0 0]", "%.10g" % T_REF,
        "    hot   { type fixedValue; value uniform %.10g; }\n"
        "    cold  { type fixedValue; value uniform %.10g; }\n"
        "    walls { type zeroGradient; }\n"
        "    frontAndBack { type empty; }\n" % (case.t_hot, case.t_cold)))

    put("0/U", _field(
        "U", "[0 1 -1 0 0 0 0]", "(0 0 0)",
        "    hot   { type noSlip; }\n    cold  { type noSlip; }\n"
        "    walls { type noSlip; }\n    frontAndBack { type empty; }\n"))

    # p_rgh is the pressure MINUS the hydrostatic head; a closed cavity has no
    # outlet, so every patch is fixedFluxPressure and the level is pinned by
    # pRefCell below. Without that pin the solve is singular in p.
    put("0/p_rgh", _field(
        "p_rgh", "[0 2 -2 0 0 0 0]", "0",
        "    hot   { type fixedFluxPressure; value uniform 0; }\n"
        "    cold  { type fixedFluxPressure; value uniform 0; }\n"
        "    walls { type fixedFluxPressure; value uniform 0; }\n"
        "    frontAndBack { type empty; }\n"))

    if ras:
        # RAS turbulent thermal diffusivity is MODELLED at the wall — the
        # Jayatilleke wall function — where the laminar `calculated` form
        # would leave the near-wall heat flux unmodelled and the solution
        # laminar-but-labelled-turbulent. BC types are the v2512 tree's own
        # (hotRoom Boussinesq tutorial), not remembered names.
        put("0/alphat", _field(
            "alphat", "[0 2 -1 0 0 0 0]", "0",
            "    hot   { type alphatJayatillekeWallFunction; Prt 0.85; "
            "value uniform 0; }\n"
            "    cold  { type alphatJayatillekeWallFunction; Prt 0.85; "
            "value uniform 0; }\n"
            "    walls { type alphatJayatillekeWallFunction; Prt 0.85; "
            "value uniform 0; }\n"
            "    frontAndBack { type empty; }\n"))
        # Seeds only: a steady solve forgets its initial turbulence, but a
        # zero k or omega divides by zero before it can. Buoyant velocity
        # scale U_b = sqrt(g beta dT W), 5 % intensity, mixing length 7 % of
        # the gap — ordinary seeding, stated so nobody reads physics into it.
        u_b = (G * BETA * case.dt * W) ** 0.5
        k0 = max(1.5 * (0.05 * u_b) ** 2, 1e-8)
        omega0 = max(k0 ** 0.5 / (0.09 ** 0.25 * 0.07 * W), 1e-6)
        put("0/k", _field(
            "k", "[0 2 -2 0 0 0 0]", "%.6g" % k0,
            "    hot   { type kqRWallFunction; value uniform %(k)0.6g; }\n"
            "    cold  { type kqRWallFunction; value uniform %(k)0.6g; }\n"
            "    walls { type kqRWallFunction; value uniform %(k)0.6g; }\n"
            "    frontAndBack { type empty; }\n" % {"k": k0}))
        put("0/omega", _field(
            "omega", "[0 0 -1 0 0 0 0]", "%.6g" % omega0,
            "    hot   { type omegaWallFunction; value uniform %(w)0.6g; }\n"
            "    cold  { type omegaWallFunction; value uniform %(w)0.6g; }\n"
            "    walls { type omegaWallFunction; value uniform %(w)0.6g; }\n"
            "    frontAndBack { type empty; }\n" % {"w": omega0}))
        put("0/nut", _field(
            "nut", "[0 2 -1 0 0 0 0]", "0",
            "    hot   { type nutkWallFunction; value uniform 0; }\n"
            "    cold  { type nutkWallFunction; value uniform 0; }\n"
            "    walls { type nutkWallFunction; value uniform 0; }\n"
            "    frontAndBack { type empty; }\n"))
    else:
        put("0/alphat", _field(
            "alphat", "[0 2 -1 0 0 0 0]", "0",
            "    hot   { type calculated; value uniform 0; }\n"
            "    cold  { type calculated; value uniform 0; }\n"
            "    walls { type calculated; value uniform 0; }\n"
            "    frontAndBack { type empty; }\n"))

    # --- control ------------------------------------------------------------
    # writeInterval == endTime: only the final state is needed and a per-
    # iteration dump of 40x40 cells x 2000 iterations is pure I/O.
    put("system/controlDict",
        _header("dictionary", "controlDict", "system") +
        "application     buoyantBoussinesqSimpleFoam;\nstartFrom       startTime;\n"
        "startTime       0;\nstopAt          endTime;\nendTime         %d;\n"
        "deltaT          1;\nwriteControl    timeStep;\nwriteInterval   %d;\n"
        "purgeWrite      0;\nwriteFormat     ascii;\nwritePrecision  10;\n"
        "writeCompression off;\ntimeFormat      general;\ntimePrecision   6;\n"
        "runTimeModifiable false;\n" % (case.iterations, case.iterations))

    # ⚠ kOmegaSST needs a wall-distance method — v2512 has no default and
    # aborts on the first omega evaluation without one. RAS-only, so the
    # laminar file stays byte-identical.
    put("system/fvSchemes", _header("dictionary", "fvSchemes", "system") +
        "ddtSchemes      { default steadyState; }\n"
        "gradSchemes     { default Gauss linear; }\n"
        "divSchemes\n{\n    default none;\n"
        "    div(phi,U)      bounded Gauss linearUpwind grad(U);\n"
        "    div(phi,T)      bounded Gauss limitedLinear 1;\n"
        "    div(phi,k)      bounded Gauss limitedLinear 1;\n"
        "    div(phi,epsilon) bounded Gauss limitedLinear 1;\n"
        + ("    div(phi,omega)  bounded Gauss limitedLinear 1;\n" if ras else "")
        + "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n}\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes   { default corrected; }\n"
        + ("wallDist        { method meshWave; }\n" if ras else ""))

    if ras:
        put("system/fvSolution", _header("dictionary", "fvSolution", "system") +
            "solvers\n{\n"
            "    p_rgh { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0.01; }\n"
            "    \"(U|T|k|omega)\" { solver PBiCGStab; preconditioner DILU; tolerance 1e-10; relTol 0.1; }\n"
            "}\n\n"
            "SIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n"
            "    pRefCell        0;\n    pRefValue       0;\n"
            "    residualControl { p_rgh 1e-6; U 1e-6; T 1e-7; \"(k|omega)\" 1e-6; }\n}\n\n"
            "relaxationFactors\n{\n    fields { p_rgh 0.7; }\n"
            "    equations { U 0.3; T 0.5; \"(k|omega)\" 0.5; }\n}\n")
    else:
        put("system/fvSolution", _header("dictionary", "fvSolution", "system") +
            "solvers\n{\n"
            "    p_rgh { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0.01; }\n"
            "    \"(U|T)\" { solver PBiCGStab; preconditioner DILU; tolerance 1e-10; relTol 0.1; }\n"
            "}\n\n"
            "SIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n"
            "    pRefCell        0;\n    pRefValue       0;\n"
            "    residualControl { p_rgh 1e-6; U 1e-6; T 1e-7; }\n}\n\n"
            "relaxationFactors\n{\n    fields { p_rgh 0.7; }\n"
            "    equations { U 0.3; T 0.5; }\n}\n")

    return case
