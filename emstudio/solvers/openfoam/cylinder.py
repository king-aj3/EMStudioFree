# SPDX-License-Identifier: LGPL-2.1-or-later
"""Natural convection from a horizontal cylinder — the ampacity anchor case.

WHY THIS CASE, AND WHY IT COMES BEFORE THE BUNDLE
--------------------------------------------------
``emstudio/wire/thermal.py`` takes its film coefficient from Churchill-Chu,
which is correct for an ISOLATED horizontal cylinder in unbounded quiescent
air and wrong for a BUNDLE in an ENCLOSURE — which is the case that actually
matters. The 2026-08-10 decision is to replace it with a solved ``h``, and to
anchor the gate where the correlation is provably right before extending into
the regime where it is not.

This module is that anchor: one cylinder, no neighbours, no enclosure. If the
CFD cannot reproduce Churchill-Chu here, nothing it later says about a bundle
is worth reading — a disagreement would be uninterpretable, because there
would be no way to separate a real confinement effect from a meshing artifact.

WHY THERE IS NO snappyHexMesh HERE
-----------------------------------
A cylinder in a concentric far field is an **O-grid**, and ``blockMesh`` does
arc edges — four blocks, radial x circumferential, one cell deep with ``empty``
front/back. Measured on v2512: 3200 cells, ``checkMesh`` "Mesh OK", max
non-orthogonality 1.5e-6, max skewness 0.095, about a second. So this rung
keeps the property that made the cavity usable as a gate, and snappyHexMesh is
deferred to the bundle, which genuinely needs it.

⚠ **This is a THIRD case writer, deliberately beside the cavity rather than a
generalisation of it.** The cavity is a benchmark fixture; smearing it into a
geometry pipeline would cost the thing that makes it a good gate. The small
amount of duplicated dictionary boilerplate below is the price of that, and it
is the cheaper side of the trade.

THE TWO MODES, AND WHY BOTH EXIST
----------------------------------
``mode="annulus"`` closes the outer boundary with a cold wall. Its value is
that **pure conduction across an annulus has an exact closed form** — Nu_D
= 2 / ln(r_o/r_i), see :func:`conduction_nusselt` — so this mode has a hard,
citation-free anchor in the same way the cavity has Nu -> 1.

``mode="farfield"`` opens the outer boundary and is the one comparable to
Churchill-Chu. It has NO conduction anchor, and that is not an oversight:
steady 2-D conduction from a cylinder to infinity **has no solution** (the
logarithmic profile does not converge), which is precisely why every cylinder
correlation is convective. The anchor for this mode is therefore the shipped
correlation itself, and the conduction check has to happen in ``annulus``.

⚠ **The far-field answer depends on the domain size.** That is the domain
padding fight the CT calculator already knows. :data:`RADIUS_RATIO` is not a
number picked and hoped over — the gate sweeps it and the sensitivity is
recorded rather than assumed.

⚠ **pRefCell must be set in ``annulus`` and must NOT be set in ``farfield``.**
A closed domain is singular in pressure and needs the level pinned; an open one
has its level fixed by the boundary, and pinning it as well over-constrains the
solve. Getting this backwards does not error — it converges to something wrong.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

__all__ = ["CylinderCase", "conduction_nusselt", "rayleigh_d",
           "first_cell_height", "write_cylinder"]

G = 9.81              # m/s^2
T_REF = 300.0         # K   Boussinesq reference / ambient

#: Default outer/inner radius ratio for the far-field mode. Swept by the gate,
#: not assumed — see the module docstring.
RADIUS_RATIO = 20.0


def rayleigh_d(nu, alpha, dt, d_m, g=G, t_ref=T_REF):
    """Ra_D from the properties actually written. The inverse of the derivation.

    ⚠ beta = 1/T_ref (ideal gas), which is what ``wire/thermal.surface_h``
    uses. A Rayleigh number formed with a different beta is a different number
    with the same name, and the comparison against Churchill-Chu would be
    silently off by that ratio.
    """
    if nu <= 0 or alpha <= 0:
        raise ValueError("nu and alpha must be positive")
    if d_m <= 0:
        raise ValueError("diameter must be positive")
    return g * (1.0 / t_ref) * abs(dt) * d_m ** 3 / (nu * alpha)


def _properties_for(ra_d, pr, dt, d_m):
    """(nu, alpha) giving exactly this Ra_D and Pr, as the cavity does it.

    Ra = g b dT D^3 / (nu alpha), Pr = nu/alpha
      => alpha = sqrt(g b dT D^3 / (Ra Pr)), nu = Pr alpha
    """
    if ra_d <= 0:
        raise ValueError("Rayleigh number must be positive")
    if pr <= 0:
        raise ValueError("Prandtl number must be positive")
    if d_m <= 0:
        raise ValueError("diameter must be positive")
    if dt == 0:
        raise ValueError("temperature difference must be non-zero")
    alpha = (G * (1.0 / T_REF) * abs(dt) * d_m ** 3 / (ra_d * pr)) ** 0.5
    return pr * alpha, alpha


def conduction_nusselt(radius_ratio):
    """Exact Nu_D for PURE CONDUCTION across a concentric annulus.

    q' = 2 pi k dT / ln(r_o/r_i) per unit length, and Nu_D = h D_i / k with
    h = q' / (pi D_i dT), so

        Nu_D = 2 / ln(r_o / r_i)

    exactly. This is the annulus mode's hard anchor — the direct analogue of
    the cavity's Nu -> 1, and equally free of any citation.
    """
    rr = float(radius_ratio)
    if rr <= 1.0:
        raise ValueError("radius ratio must exceed 1")
    return 2.0 / math.log(rr)


def first_cell_height(length, cells, grading):
    """Width of the FIRST cell of a simpleGrading run of `cells` over `length`.

    OpenFOAM's simpleGrading ratio is last-cell/first-cell. With n cells the
    ratio between neighbours is r = R^(1/(n-1)) and the widths are geometric,
    so w1 (r^n - 1)/(r - 1) = L.

    Needed because the wall gradient is taken across the first cell, so its
    height is part of the measurement — not a meshing detail the reader can
    ignore.
    """
    n = int(cells)
    if n < 2:
        raise ValueError("need at least 2 cells")
    if length <= 0:
        raise ValueError("length must be positive")
    ratio = float(grading)
    if ratio <= 0:
        raise ValueError("grading must be positive")
    if abs(ratio - 1.0) < 1e-12:
        return float(length) / n
    r = ratio ** (1.0 / (n - 1))
    return float(length) * (r - 1.0) / (r ** n - 1.0)


def radial_layer_centres(r_in, r_out, n_r, grading):
    """Mid-height radii of each radial LAYER, innermost first.

    ⚠ **These are not the cell centroid radii, and the difference is not
    negligible.** The mesh is faceted: a cell is a trapezoid between two
    chords, so its centroid sits at a smaller RADIUS than the layer mid-height
    — measured on a 40 x 20 O-grid, layer mid-height r_i + w1/2 = 1.0031658e-2
    against an actual centroid radius of 1.0023948e-2.

    What matters for the wall gradient is neither of those: it is the
    PERPENDICULAR distance from the wall FACE (the chord, not the arc) to the
    centroid, and that is w1/2 — confirmed against the trapezoid centroid to
    seven figures. So this function is right for the gradient and wrong for
    anything that wants a true radius, which is why it no longer claims to
    return cell centres.

    Exposed because the gate lays a synthetic conduction field on these radii;
    that is a measurement, not an internal.
    """
    n = int(n_r)
    w1 = first_cell_height(r_out - r_in, n, grading)
    ratio = float(grading)
    r = 1.0 if abs(ratio - 1.0) < 1e-12 else ratio ** (1.0 / (n - 1))
    out, edge, w = [], float(r_in), w1
    for _ in range(n):
        out.append(edge + w / 2.0)
        edge += w
        w *= r
    return out


@dataclass
class CylinderCase:
    """An O-grid cylinder case and what it resolved to."""

    ra_d: float = 1.0e4
    pr: float = 0.71                 # air
    d_m: float = 0.020               # 20 mm — mid of the cable regime
    radius_ratio: float = RADIUS_RATIO
    n_r: int = 60                    # radial cells
    n_theta: int = 30                # per 90 deg block -> 4x around
    grading: float = 40.0            # last/first radial cell — wall clustering
    iterations: int = 3000
    #: 0 = write only the final state. A positive value writes intermediate
    #: snapshots, which is how the iteration count gets CHOSEN rather than
    #: guessed: one run yields the whole Nu-vs-iteration trajectory, so
    #: "converged" can be judged on the quantity of interest instead of on a
    #: residual threshold that may be unreachable.
    write_interval: int = 0
    mode: str = "farfield"           # or "annulus"
    dt: float = 30.0                 # K, cylinder above ambient
    t_amb: float = T_REF

    def __post_init__(self):
        if self.mode not in ("farfield", "annulus"):
            raise ValueError("mode must be 'farfield' or 'annulus', got %r"
                             % (self.mode,))

    @property
    def nu(self):
        return _properties_for(self.ra_d, self.pr, self.dt, self.d_m)[0]

    @property
    def alpha(self):
        return _properties_for(self.ra_d, self.pr, self.dt, self.d_m)[1]

    @property
    def ra_written(self):
        """Ra_D recomputed from the derived properties — must match .ra_d."""
        return rayleigh_d(self.nu, self.alpha, self.dt, self.d_m)

    @property
    def r_in(self):
        return self.d_m / 2.0

    @property
    def r_out(self):
        return self.r_in * float(self.radius_ratio)

    @property
    def t_wall(self):
        return self.t_amb + self.dt

    @property
    def first_cell_m(self):
        """Radial height of the wall-adjacent cell — the gradient's baseline."""
        return first_cell_height(self.r_out - self.r_in, self.n_r,
                                 self.grading)

    @property
    def last_cell_m(self):
        """Radial height of the OUTER-wall cell. simpleGrading's ratio is
        last/first by definition, so this is exactly first x grading."""
        return self.first_cell_m * float(self.grading)

    @property
    def conduction_nu(self):
        """The annulus conduction limit for this geometry (annulus mode only)."""
        return conduction_nusselt(self.radius_ratio)


def _header(cls, obj, loc):
    return (
        "FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
        "    class       %s;\n    location    \"%s\";\n    object      %s;\n}\n\n"
        % (cls, loc, obj))


def _field(obj, dims, internal, boundary):
    return (_header("volVectorField" if obj == "U" else "volScalarField",
                    obj, "0")
            + "dimensions      %s;\n\ninternalField   uniform %s;\n\n"
              "boundaryField\n{\n%s}\n" % (dims, internal, boundary))


def _blockmesh(case):
    """The four-block O-grid. Vertex order is proved by the gate, not asserted.

    Layout: z=0 holds inner 0-3 then outer 4-7 at 0/90/180/270 deg; z=t repeats
    them at +8. Block k spans k*90 to (k+1)*90 with local directions
    (x1 radial, x2 circumferential, x3 axial) — that ordering is what the
    parser relies on to find the wall-adjacent cells, so it is not incidental.
    """
    r_i, r_o = case.r_in, case.r_out
    thick = case.d_m / 10.0
    n_r, n_t = int(case.n_r), int(case.n_theta)

    verts = ""
    for z in (0.0, thick):
        for r in (r_i, r_o):
            for k in range(4):
                a = math.radians(k * 90.0)
                verts += ("    (%.10g %.10g %.10g)\n"
                          % (r * math.cos(a), r * math.sin(a), z))

    def i_(k):
        return k % 4

    def o_(k):
        return 4 + k % 4

    blocks = ""
    for k in range(4):
        blocks += ("    hex (%d %d %d %d %d %d %d %d) (%d %d 1) "
                   "simpleGrading (%.10g 1 1)\n"
                   % (i_(k), o_(k), o_(k + 1), i_(k + 1),
                      i_(k) + 8, o_(k) + 8, o_(k + 1) + 8, i_(k + 1) + 8,
                      n_r, n_t, float(case.grading)))

    edges = ""
    for zi, z in enumerate((0.0, thick)):
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
                    % (i_(k), o_(k), o_(k + 1), i_(k + 1),
                       i_(k) + 8, o_(k) + 8, o_(k + 1) + 8, i_(k + 1) + 8)
                    for k in range(4))

    outer_type = "wall" if case.mode == "annulus" else "patch"
    return (_header("dictionary", "blockMeshDict", "system")
            + "scale   1;\n\nvertices\n(\n" + verts + ");\n\nblocks\n(\n"
            + blocks + ");\n\nedges\n(\n" + edges + ");\n\nboundary\n(\n"
            + "    cylinder { type wall; faces (\n" + inner + "    ); }\n"
            + "    farfield { type %s; faces (\n" % outer_type + outer
            + "    ); }\n"
            + "    frontAndBack { type empty; faces (\n" + fandb + "    ); }\n"
            + ");\n\nmergePatchPairs ();\n")


def write_cylinder(case_dir, case=None):
    """Write a complete cylinder case. Returns the resolved :class:`CylinderCase`.

    Plain text only — no OpenFOAM import — so the offline half of the gate runs
    with no solver installed.
    """
    case = case or CylinderCase()
    nu, alpha = case.nu, case.alpha
    if case.n_r < 2 or case.n_theta < 2:
        raise ValueError("need at least 2 cells in each direction")
    if case.radius_ratio <= 1.0:
        raise ValueError("radius ratio must exceed 1")

    for sub in ("0", "constant", "system"):
        os.makedirs(os.path.join(case_dir, sub), exist_ok=True)

    def put(rel, text):
        with open(os.path.join(case_dir, rel), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("/*--------------------------------*- C++ -*-------"
                     "---------------------*/\n")
            fh.write(text)

    put("system/blockMeshDict", _blockmesh(case))

    # Pr here is the LAMINAR Prandtl number; the solver forms the molecular
    # diffusivity as nu/Pr. Prt is turbulent and inert in a laminar run.
    put("constant/transportProperties",
        _header("dictionary", "transportProperties", "constant") +
        "transportModel  Newtonian;\n"
        "nu              %.10g;\n"
        "beta            %.10g;\n"
        "TRef            %.10g;\n"
        "Pr              %.10g;\n"
        "Prt             0.85;\n"
        % (nu, 1.0 / T_REF, case.t_amb, case.pr))

    put("constant/turbulenceProperties",
        _header("dictionary", "turbulenceProperties", "constant") +
        "simulationType  laminar;\n")

    put("constant/g", _header("uniformDimensionedVectorField", "g", "constant")
        + "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 -%.10g 0);\n"
        % G)

    # --- fields; the outer patch is where the two modes actually differ -----
    if case.mode == "annulus":
        t_outer = "    farfield { type fixedValue; value uniform %.10g; }\n" \
                  % case.t_amb
        u_outer = "    farfield { type noSlip; }\n"
        p_outer = "    farfield { type fixedFluxPressure; value uniform 0; }\n"
    else:
        # inletOutlet: ambient air enters, solved air leaves. A plain
        # fixedValue would drag the plume back to ambient on the way OUT and
        # quietly inflate the wall flux.
        t_outer = ("    farfield { type inletOutlet; "
                   "inletValue uniform %.10g; value uniform %.10g; }\n"
                   % (case.t_amb, case.t_amb))
        u_outer = ("    farfield { type pressureInletOutletVelocity; "
                   "value uniform (0 0 0); }\n")
        p_outer = ("    farfield { type totalPressure; p0 uniform 0; "
                   "value uniform 0; }\n")

    put("0/T", _field("T", "[0 0 0 1 0 0 0]", "%.10g" % case.t_amb,
                      "    cylinder { type fixedValue; value uniform %.10g; }\n"
                      % case.t_wall
                      + t_outer
                      + "    frontAndBack { type empty; }\n"))

    put("0/U", _field("U", "[0 1 -1 0 0 0 0]", "(0 0 0)",
                      "    cylinder { type noSlip; }\n" + u_outer
                      + "    frontAndBack { type empty; }\n"))

    put("0/p_rgh", _field("p_rgh", "[0 2 -2 0 0 0 0]", "0",
                          "    cylinder { type fixedFluxPressure; "
                          "value uniform 0; }\n" + p_outer
                          + "    frontAndBack { type empty; }\n"))

    put("0/alphat", _field("alphat", "[0 2 -1 0 0 0 0]", "0",
                           "    cylinder { type calculated; value uniform 0; }\n"
                           "    farfield { type calculated; value uniform 0; }\n"
                           "    frontAndBack { type empty; }\n"))

    put("system/controlDict",
        _header("dictionary", "controlDict", "system") +
        "application     buoyantBoussinesqSimpleFoam;\nstartFrom       startTime;\n"
        "startTime       0;\nstopAt          endTime;\nendTime         %d;\n"
        "deltaT          1;\nwriteControl    timeStep;\nwriteInterval   %d;\n"
        "purgeWrite      0;\nwriteFormat     ascii;\nwritePrecision  10;\n"
        "writeCompression off;\ntimeFormat      general;\ntimePrecision   6;\n"
        "runTimeModifiable false;\n"
        % (case.iterations,
           int(case.write_interval) or case.iterations))

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

    # ⚠ pRefCell ONLY in the closed (annulus) case — see the module docstring.
    pref = ("    pRefCell        0;\n    pRefValue       0;\n"
            if case.mode == "annulus" else "")
    put("system/fvSolution", _header("dictionary", "fvSolution", "system") +
        "solvers\n{\n"
        "    p_rgh { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0.01; }\n"
        "    \"(U|T)\" { solver PBiCGStab; preconditioner DILU; tolerance 1e-10; relTol 0.1; }\n"
        "}\n\n"
        "SIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n" + pref +
        "    residualControl { p_rgh 1e-6; U 1e-6; T 1e-7; }\n}\n\n"
        "relaxationFactors\n{\n    fields { p_rgh 0.7; }\n"
        "    equations { U 0.3; T 0.5; }\n}\n")

    return case
