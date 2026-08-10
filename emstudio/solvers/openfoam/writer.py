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


def _properties_for(ra, pr):
    """(nu, alpha) giving exactly this Ra and Pr.

    Ra = g b dT L^3 / (nu alpha) and Pr = nu / alpha
      => nu alpha = g b dT L^3 / Ra  and  nu = Pr alpha
      => alpha = sqrt(g b dT L^3 / (Ra Pr)),  nu = Pr alpha
    """
    if ra <= 0:
        raise ValueError("Rayleigh number must be positive")
    if pr <= 0:
        raise ValueError("Prandtl number must be positive")
    alpha = (G * BETA * DT * L ** 3 / (ra * pr)) ** 0.5
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

    @property
    def nu(self):
        return _properties_for(self.ra, self.pr)[0]

    @property
    def alpha(self):
        return _properties_for(self.ra, self.pr)[1]

    @property
    def ra_written(self):
        """Ra recomputed from the derived properties — must match .ra."""
        return rayleigh(self.nu, self.alpha)

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
    thick = L / n
    put("system/blockMeshDict", _header("dictionary", "blockMeshDict", "system") +
        "scale   1;\n\nvertices\n(\n"
        "    (0 0 0)\n    (%(L)g 0 0)\n    (%(L)g %(L)g 0)\n    (0 %(L)g 0)\n"
        "    (0 0 %(t)g)\n    (%(L)g 0 %(t)g)\n    (%(L)g %(L)g %(t)g)\n"
        "    (0 %(L)g %(t)g)\n);\n\n"
        "blocks\n(\n    hex (0 1 2 3 4 5 6 7) (%(n)d %(n)d 1) simpleGrading (1 1 1)\n);\n\n"
        "edges ();\n\nboundary\n(\n"
        "    hot   { type wall;  faces ( (0 4 7 3) ); }\n"
        "    cold  { type wall;  faces ( (1 2 6 5) ); }\n"
        "    walls { type wall;  faces ( (0 1 5 4) (3 7 6 2) ); }\n"
        "    frontAndBack { type empty; faces ( (0 3 2 1) (4 5 6 7) ); }\n"
        ");\n\nmergePatchPairs ();\n"
        % {"L": L, "t": thick, "n": n})

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

    put("system/fvSchemes", _header("dictionary", "fvSchemes", "system") +
        "ddtSchemes      { default steadyState; }\n"
        "gradSchemes     { default Gauss linear; }\n"
        "divSchemes\n{\n    default none;\n"
        "    div(phi,U)      bounded Gauss linearUpwind grad(U);\n"
        "    div(phi,T)      bounded Gauss limitedLinear 1;\n"
        "    div(phi,k)      bounded Gauss limitedLinear 1;\n"
        "    div(phi,epsilon) bounded Gauss limitedLinear 1;\n"
        "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n}\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes   { default corrected; }\n")

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
