# SPDX-License-Identifier: LGPL-2.1-or-later
"""Natural convection around an ARBITRARY solid — geometry from the document.

ROADMAP §8a (AJ, 2026-08-17): CFD attaches to the thing the user selects.
The OpenFOAM path previously solved only parametric geometry it wrote
itself (cable circles, cavities, cylinders); this module takes a
TRIANGULATED solid — any FreeCAD shape, tessellated by the command that
owns the selection — immerses it in an OPEN-AIR box, prescribes its
dissipated power as a surface heat flux, and solves the buoyant flow.

OPEN AIR, honestly
------------------
"Open air" is a finite box whose walls sit at ambient temperature, sized
by ``open_air`` bounding radii around the solid. That is an APPROXIMATION
with a measurable size: the conduction anchor below bounds the box
EXACTLY, and for convection the box bias is folded into the gate's
Churchill band — the conduction offset (Nu 2.56 vs the unbounded 2)
predicts +3-4 %, and the T1 layered mesh measures +2.9 % (the unlayered
mesh read +4.3 %; wall layers moved the answer toward the correlation) —
while the gate's cells 24 -> 32 self-pins put MESH sensitivity at
0.25 %/0.7 % (re-measured 2026-08-23, layered).
There is deliberately no unbounded-domain pretence — a wall the solve
contains is honest; an "infinite" claim the mesh cannot deliver is not.

THE ANCHOR — a citation-free sandwich
-------------------------------------
For a SPHERE of radius r_i centred in the box, steady conduction (g = 0)
to an outer boundary at ambient has the concentric-shell closed form
Nu_D = 2 / (1 - r_i/r_o). The box is not a sphere — but it CONTAINS the
inscribed sphere (radius r_ins, the nearest wall) and is CONTAINED BY the
circumscribed one (r_cir, the farthest corner), and Dirichlet domain
monotonicity orders the thermal resistances. Therefore, exactly:

    2/(1 - r_i/r_cir)  <=  Nu_box  <=  2/(1 - r_i/r_ins)

Both bounds tend to the textbook 2 as the box grows. Pure mathematics, no
citation, two-sided — a coupling that is wrong in either direction leaves
the sandwich.

Units are METRES and the fluid is REAL AIR (AHTT A.6 via
``emstudio.wire.thermal.air_properties``) at the film temperature: this
case predicts real kelvins from real watts. (The bundle case instead
scales a synthetic fluid to a nominal Ra — legitimate there because it
ships a RATIO; a surface-temperature prediction cannot play that trick.)

⚠ Gravity acts along −z. FreeCAD documents are z-up and the solid arrives
in DOCUMENT orientation, so "down" here must be the viewport's down — a
case built with the bundle's −y convention would silently convect
sideways across the very geometry the user is looking at.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field as _field

from emstudio.solvers.openfoam.bundle import G, T_REF, _field_file, _header

__all__ = ["SolidCase", "SolidResult", "write_solid", "solid_stl",
           "uv_sphere"]


def uv_sphere(r, centre=(0.0, 0.0, 0.0), n_theta=24, n_phi=48):
    """Triangulated UV sphere — the anchor geometry, deterministic.

    Lives here (not in a gate) because the sphere IS this feature's
    validation instrument and the dialog's self-test uses it too. The
    polyhedron's area is slightly under 4*pi*r^2; the case uses the
    TRIANGLE area everywhere, so flux and area can never disagree.
    """
    if r <= 0:
        raise ValueError("sphere radius must be positive")
    if n_theta < 4 or n_phi < 8:
        raise ValueError("sphere tessellation too coarse to be watertight")
    cx, cy, cz = centre

    def pt(it, ip):
        th = math.pi * it / n_theta
        ph = 2.0 * math.pi * ip / n_phi
        return (cx + r * math.sin(th) * math.cos(ph),
                cy + r * math.sin(th) * math.sin(ph),
                cz + r * math.cos(th))

    tris = []
    for it in range(n_theta):
        for ip in range(n_phi):
            a = pt(it, ip)
            b = pt(it + 1, ip)
            c = pt(it + 1, ip + 1)
            d = pt(it, ip + 1)
            if it > 0:                       # top cap rows are triangles
                tris.append((a, b, d))
            if it < n_theta - 1:
                tris.append((b, c, d))
    return tris


def _tri_normal_area(tri):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    mag = math.sqrt(nx * nx + ny * ny + nz * nz)
    if mag == 0.0:
        return (0.0, 0.0, 0.0), 0.0
    return (nx / mag, ny / mag, nz / mag), 0.5 * mag


def solid_stl(path, triangles, name="solid"):
    """ASCII STL from raw triangles. No FreeCAD import — the writer stays
    Qt-free and the offline half of the gate runs with no GUI."""
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("solid %s\n" % name)
        for tri in triangles:
            n, area = _tri_normal_area(tri)
            if area == 0.0:
                continue                     # degenerate slivers add nothing
            fh.write("  facet normal %.9g %.9g %.9g\n"
                     "    outer loop\n" % n)
            for p in tri:
                fh.write("      vertex %.9g %.9g %.9g\n" % tuple(p))
            fh.write("    endloop\n  endfacet\n")
        fh.write("endsolid %s\n" % name)


@dataclass
class SolidResult:
    """Surface reading of a solved solid-convection case."""

    t_mean: float
    t_min: float
    t_max: float
    t_amb: float
    flux_w_m2: float
    k_fluid: float
    nu_fluid: float
    alpha_fluid: float
    beta: float
    gravity: float
    faces: int
    converged: bool = False
    drift: float = float("nan")
    provenance: str = ""
    warnings: list = _field(default_factory=list)

    @property
    def dt(self):
        return self.t_mean - self.t_amb

    @property
    def h_w_m2k(self):
        """Mean film coefficient, q'' / dT — the number a datasheet quotes."""
        if self.dt == 0:
            raise ValueError("the surface sits at ambient; h is undefined")
        return self.flux_w_m2 / self.dt

    def nu_for(self, d_m):
        """Nu on a caller-chosen length. ⚠ The CALLER owns the choice of D —
        an arbitrary solid has no canonical length, and inventing one here
        would let a correlation be quoted at a scale the user never chose."""
        if d_m <= 0:
            raise ValueError("reference length must be positive")
        return self.h_w_m2k * d_m / self.k_fluid

    def ra_for(self, d_m):
        """Ra that RESULTED at the solved dT, on the caller's length."""
        if d_m <= 0:
            raise ValueError("reference length must be positive")
        return (self.gravity * self.beta * abs(self.dt) * d_m ** 3
                / (self.nu_fluid * self.alpha_fluid))


@dataclass
class SolidCase:
    """A power-dissipating triangulated solid in an open-air box."""

    triangles: list
    power_w: float = 1.0
    t_amb: float = T_REF
    #: Box half-extent in bounding radii. 1.0 would touch the solid; the
    #: floor below keeps the walls genuinely far-field-ish.
    open_air: float = 4.0
    cells_bg: int = 32               # background cells across the box
    refine_min: int = 3
    refine_max: int = 4
    iterations: int = 6000
    write_interval: int = 2000
    t_film_k: float = 315.0
    gravity: float = G               # 0.0 = the conduction anchor
    patch: str = "solid"
    #: Prism layers grown on the solid's surface (T1 of the turbulence plan).
    #: Near-wall resolution is where the thermal boundary layer lives, and a
    #: castellated-only mesh samples it with stair-stepped hex cells; layers
    #: resolve the gradient the flux BC feeds. 0 = no layers — byte-identical
    #: to the pre-T1 mesh, kept as the escape hatch for geometry where snappy's
    #: layer addition degrades (it collapses layers rather than failing, so
    #: coverage is read from the snappy log by the gate, never assumed).
    wall_layers: int = 3
    #: "" = laminar — byte-identical to the pre-T4 case. "kOmegaSST" = RAS
    #: with wall functions (T4 of docs/OPENFOAM_TURBULENCE_PLAN.md; the model
    #: itself is validated against the measured Betts & Bokhari cavity by
    #: `openfoam_ras_cavity`, and this case's turbulent regime is gated
    #: against Churchill's sphere correlation by `openfoam_ras_solid` — the
    #: correlation-anchor policy is AJ's ruling, 2026-08-23). Any other
    #: string raises: a model name the writer cannot honour must not pass
    #: silently — the v1.4.0 defect class.
    turbulence: str = ""

    def __post_init__(self):
        if not self.triangles:
            raise ValueError("no triangles — tessellate the solid first")
        if self.power_w <= 0:
            raise ValueError(
                "dissipated power must be positive: a solid dissipating "
                "nothing has no convection problem, and a negative power is "
                "a heat SINK this case does not model")
        if self.open_air < 1.5:
            raise ValueError(
                "open_air below 1.5 bounding radii puts the walls against "
                "the solid — that is an enclosure study, not open air")
        if self.cells_bg < 8:
            raise ValueError("need at least 8 background cells across")
        if self.wall_layers < 0:
            raise ValueError("wall_layers is a count (0 disables layers)")
        if self.turbulence not in ("", "kOmegaSST"):
            raise ValueError(
                "unsupported turbulence model %r — this writer knows laminar "
                "(\"\") and \"kOmegaSST\"; a name it cannot honour must fail "
                "here, not run laminar and report success" % (self.turbulence,))
        if self.area_m2 <= 0:
            raise ValueError("the triangulation has zero area")
        if self.iterations < 1:
            raise ValueError("need at least one iteration")
        wi = int(self.write_interval)
        if not (0 < wi <= self.iterations) or self.iterations % wi:
            # ⚠ OpenFOAM writes only when timeIndex %% interval == 0: an
            # interval that does not divide endTime means the FINAL state is
            # never written and the reader silently reports an older
            # snapshot as the answer.
            raise ValueError(
                "write_interval must divide iterations (got %s per %s) — "
                "otherwise the final state is never written and an older "
                "snapshot would be read as the result"
                % (self.write_interval, self.iterations))

    # --- geometry ----------------------------------------------------------
    @property
    def area_m2(self):
        return sum(_tri_normal_area(t)[1] for t in self.triangles)

    @property
    def bbox(self):
        xs = [p[0] for t in self.triangles for p in t]
        ys = [p[1] for t in self.triangles for p in t]
        zs = [p[2] for t in self.triangles for p in t]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    @property
    def centre(self):
        lo, hi = self.bbox
        return tuple(0.5 * (a + b) for a, b in zip(lo, hi))

    @property
    def bounding_radius(self):
        cx, cy, cz = self.centre
        return max(math.sqrt((p[0] - cx) ** 2 + (p[1] - cy) ** 2
                             + (p[2] - cz) ** 2)
                   for t in self.triangles for p in t)

    @property
    def box_half(self):
        return self.open_air * self.bounding_radius

    # --- fluid: real air at the film temperature ---------------------------
    @property
    def air(self):
        """(k, nu, alpha, Pr) — AHTT A.6, the same table the ampacity path
        uses, so a solid and a cable never disagree about what air is."""
        from emstudio.wire.thermal import air_properties
        return air_properties(self.t_film_k)

    @property
    def k_fluid(self):
        return self.air[0]

    @property
    def beta(self):
        """Ideal-gas expansion at the film temperature."""
        return 1.0 / self.t_film_k

    @property
    def flux_w_m2(self):
        return self.power_w / self.area_m2

    @property
    def gradient(self):
        """dT/dn (K/m) at the surface — the prescribed-gradient BC.
        ⚠ k is the AIR conductivity: the gradient is taken in the fluid."""
        return self.flux_w_m2 / self.k_fluid

    def ra_estimate(self):
        """PRE-solve estimate of the resulting Ra_D — the regime chooser.

        Ra is an OUTPUT of this flux-BC case (dT is solved), so choosing a
        turbulence model needs an estimate BEFORE any solve exists. The flux
        and Churchill's sphere correlation close the loop: q'' = Nu(Ra) k
        dT / D with Ra ∝ dT, solved by a fixed point (converges in a few
        steps — Nu^~1/4 damps it). Good to the correlation's own accuracy,
        which is all a REGIME choice needs; the solved Ra is still what gets
        reported. Conduction-only cases (gravity 0) estimate 0.
        """
        if not self.gravity:
            return 0.0
        k, nu_f, alpha, pr = self.air
        d = 2.0 * self.bounding_radius
        chch = (1.0 + (0.469 / pr) ** (9.0 / 16.0)) ** (4.0 / 9.0)
        dt = 10.0                       # any positive start; the map contracts
        for _ in range(30):
            ra = self.gravity * self.beta * dt * d ** 3 / (nu_f * alpha)
            nu_d = 2.0 + 0.589 * ra ** 0.25 / chch
            dt_new = self.flux_w_m2 * d / (nu_d * k)
            if abs(dt_new - dt) < 1e-9 * max(dt, 1.0):
                dt = dt_new
                break
            dt = dt_new
        return self.gravity * self.beta * dt * d ** 3 / (nu_f * alpha)

    # --- the sandwich ------------------------------------------------------
    def conduction_nu_bounds(self, r_sphere):
        """(lower, upper) bounds on the conduction Nu_D of a CENTRED sphere.

        Only meaningful for the sphere anchor: the closed form is spherical.
        Exactness is the point — see the module docstring.
        """
        if not 0 < r_sphere < self.box_half:
            raise ValueError("the sphere must sit inside the box")
        r_ins = self.box_half
        r_cir = self.box_half * math.sqrt(3.0)
        return (2.0 / (1.0 - r_sphere / r_cir),
                2.0 / (1.0 - r_sphere / r_ins))


def write_solid(case_dir, case=None):
    """Write a complete open-air solid case. Returns the SolidCase."""
    if case is None:
        raise ValueError("a SolidCase is required — there is no default "
                         "geometry here, by design: this path exists to "
                         "solve the USER'S solid")
    k, nu, alpha, pr = case.air
    cx, cy, cz = case.centre
    h = case.box_half

    for sub in ("0", "constant/triSurface", "system"):
        os.makedirs(os.path.join(case_dir, sub), exist_ok=True)
    solid_stl(os.path.join(case_dir, "constant", "triSurface",
                           case.patch + ".stl"),
              case.triangles, name=case.patch)

    def put(rel, text):
        p = os.path.join(case_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("/*--------------------------------*- C++ -*-------"
                     "---------------------*/\n")
            fh.write(text)

    n = int(case.cells_bg)
    put("system/blockMeshDict", _header("dictionary", "blockMeshDict", "system")
        + "scale   1;\n\nvertices\n(\n"
        + "".join("    (%.10g %.10g %.10g)\n" % v for v in (
            (cx - h, cy - h, cz - h), (cx + h, cy - h, cz - h),
            (cx + h, cy + h, cz - h), (cx - h, cy + h, cz - h),
            (cx - h, cy - h, cz + h), (cx + h, cy - h, cz + h),
            (cx + h, cy + h, cz + h), (cx - h, cy + h, cz + h)))
        + ");\n\nblocks\n(\n    hex (0 1 2 3 4 5 6 7) (%d %d %d) "
          "simpleGrading (1 1 1)\n);\n\nedges ();\n\nboundary\n(\n"
          "    walls { type wall; faces ( (0 3 2 1) (4 5 6 7) (0 4 7 3) "
          "(1 2 6 5) (0 1 5 4) (3 7 6 2) ); }\n"
          ");\n\nmergePatchPairs ();\n" % (n, n, n))

    put("system/surfaceFeatureExtractDict",
        _header("dictionary", "surfaceFeatureExtractDict", "system")
        + "%s.stl\n{\n    extractionMethod    extractFromSurface;\n"
          "    includedAngle       150;\n}\n" % case.patch)

    # ⚠ locationInMesh: a corner inset with three UNEQUAL fractions, so it
    # sits off every face/diagonal plane. It is in the fluid by construction:
    # its distance from the centre is >= 0.87*h*sqrt(3) > bounding_radius
    # whenever open_air >= 1.5 — asserted, not hoped.
    loc = (cx + 0.93 * h, cy + 0.90 * h, cz + 0.87 * h)
    loc_r = math.sqrt(sum((a - b) ** 2 for a, b in zip(loc, (cx, cy, cz))))
    assert loc_r > case.bounding_radius, "locationInMesh landed in the solid"
    # T1 of the turbulence plan: prism layers on the solid's surface.
    # ⚠ wall_layers == 0 must reproduce the pre-T1 dict byte-for-byte (empty
    # layers{}, expansionRatio 1.0) — that is the differential control the
    # bundle writer's sha256 identity and the gates rely on.
    if case.wall_layers > 0:
        add_layers = "true"
        layers = "layers { %s { nSurfaceLayers %d; } }" % (case.patch,
                                                           case.wall_layers)
        expansion = "1.2"
    else:
        add_layers = "false"
        layers = "layers {}"
        expansion = "1.0"
    put("system/snappyHexMeshDict",
        _header("dictionary", "snappyHexMeshDict", "system")
        + "castellatedMesh true;\nsnap true;\naddLayers %s;\n\n"
          "geometry\n{\n    %s.stl { type triSurfaceMesh; name %s; }\n}\n\n"
          "castellatedMeshControls\n{\n    maxLocalCells 2000000;\n"
          "    maxGlobalCells 8000000;\n    minRefinementCells 10;\n"
          "    nCellsBetweenLevels 3;\n    maxLoadUnbalance 0.10;\n"
          "    resolveFeatureAngle 30;\n    allowFreeStandingZoneFaces true;\n"
          "    features ( { file \"%s.eMesh\"; level 0; } );\n"
          "    refinementSurfaces { %s { level (%d %d); } }\n"
          "    refinementRegions {}\n    locationInMesh (%.10g %.10g %.10g);\n}\n\n"
          "snapControls\n{\n    nSmoothPatch 3;\n    tolerance 2.0;\n"
          "    nSolveIter 50;\n    nRelaxIter 5;\n    nFeatureSnapIter 10;\n"
          "    implicitFeatureSnap false;\n    explicitFeatureSnap true;\n"
          "    multiRegionFeatureSnap false;\n}\n\n"
          "addLayersControls\n{\n    relativeSizes true;\n    %s\n"
          "    expansionRatio %s;\n    finalLayerThickness 0.3;\n"
          "    minThickness 0.1;\n    nGrow 0;\n    featureAngle 60;\n"
          "    nRelaxIter 3;\n    nSmoothSurfaceNormals 1;\n    nSmoothNormals 3;\n"
          "    nSmoothThickness 10;\n    maxFaceThicknessRatio 0.5;\n"
          "    maxThicknessToMedialRatio 0.3;\n    minMedialAxisAngle 90;\n"
          "    nBufferCellsNoExtrude 0;\n    nLayerIter 50;\n}\n\n"
          "meshQualityControls\n{\n    maxNonOrtho 65;\n    maxBoundarySkewness 20;\n"
          "    maxInternalSkewness 4;\n    maxConcave 80;\n    minVol 1e-13;\n"
          "    minTetQuality 1e-30;\n    minArea -1;\n    minTwist 0.02;\n"
          "    minDeterminant 0.001;\n    minFaceWeight 0.02;\n    minVolRatio 0.01;\n"
          "    minTriangleTwist -1;\n    nSmoothScale 4;\n    errorReduction 0.75;\n}\n\n"
          "mergeTolerance 1e-6;\n"
        % (add_layers, case.patch, case.patch, case.patch, case.patch,
           case.refine_min, case.refine_max, loc[0], loc[1], loc[2],
           layers, expansion))

    put("constant/transportProperties",
        _header("dictionary", "transportProperties", "constant")
        + "transportModel  Newtonian;\nnu              %.10g;\n"
          "beta            %.10g;\nTRef            %.10g;\n"
          "Pr              %.10g;\nPrt             0.85;\n"
        % (nu, case.beta, case.t_amb, pr))
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
    # ⚠ -z: FreeCAD is z-up and the solid is in DOCUMENT orientation.
    put("constant/g", _header("uniformDimensionedVectorField", "g", "constant")
        + "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 0 -%.10g);\n"
        % case.gravity)

    # ⚠ mixed/valueFraction 0 == a pure prescribed gradient that WRITES the
    # patch values; fixedGradient writes none and the result path would read
    # nothing (the bundle path measured this).
    put("0/T", _field_file(
        "T", "[0 0 0 1 0 0 0]", "%.10g" % case.t_amb,
        "    %s { type mixed; refValue uniform %.10g; refGradient uniform "
        "%.10g; valueFraction uniform 0; value uniform %.10g; }\n"
        "    walls { type fixedValue; value uniform %.10g; }\n"
        % (case.patch, case.t_amb, case.gradient, case.t_amb, case.t_amb)))
    put("0/U", _field_file(
        "U", "[0 1 -1 0 0 0 0]", "(0 0 0)",
        "    %s { type noSlip; }\n    walls { type noSlip; }\n" % case.patch))
    put("0/p_rgh", _field_file(
        "p_rgh", "[0 2 -2 0 0 0 0]", "0",
        "    %s { type fixedFluxPressure; value uniform 0; }\n"
        "    walls { type fixedFluxPressure; value uniform 0; }\n"
        % case.patch))
    if ras:
        # BC types are the v2512 tree's own (hotRoom Boussinesq tutorial),
        # identical to the cavity writer's T2 — never remembered names.
        put("0/alphat", _field_file(
            "alphat", "[0 2 -1 0 0 0 0]", "0",
            "    %s { type alphatJayatillekeWallFunction; Prt 0.85; "
            "value uniform 0; }\n"
            "    walls { type alphatJayatillekeWallFunction; Prt 0.85; "
            "value uniform 0; }\n" % case.patch))
        # Seeds only — a steady solve forgets them, but zero k or omega
        # divides by zero first. The buoyant velocity scale uses a nominal
        # 1 K because dT is an OUTPUT of this flux-BC case; the floors keep a
        # tiny geometry from seeding a zero.
        d_seed = 2.0 * case.bounding_radius
        u_b = (case.gravity * case.beta * 1.0 * d_seed) ** 0.5 if case.gravity else 0.0
        k0 = max(1.5 * (0.05 * u_b) ** 2, 1e-8)
        omega0 = max(k0 ** 0.5 / (0.09 ** 0.25 * 0.07 * max(d_seed, 1e-6)), 1e-6)
        put("0/k", _field_file(
            "k", "[0 2 -2 0 0 0 0]", "%.6g" % k0,
            "    %s { type kqRWallFunction; value uniform %.6g; }\n"
            "    walls { type kqRWallFunction; value uniform %.6g; }\n"
            % (case.patch, k0, k0)))
        put("0/omega", _field_file(
            "omega", "[0 0 -1 0 0 0 0]", "%.6g" % omega0,
            "    %s { type omegaWallFunction; value uniform %.6g; }\n"
            "    walls { type omegaWallFunction; value uniform %.6g; }\n"
            % (case.patch, omega0, omega0)))
        put("0/nut", _field_file(
            "nut", "[0 2 -1 0 0 0 0]", "0",
            "    %s { type nutkWallFunction; value uniform 0; }\n"
            "    walls { type nutkWallFunction; value uniform 0; }\n"
            % case.patch))
    else:
        put("0/alphat", _field_file(
            "alphat", "[0 2 -1 0 0 0 0]", "0",
            "    %s { type calculated; value uniform 0; }\n"
            "    walls { type calculated; value uniform 0; }\n" % case.patch))

    put("system/controlDict", _header("dictionary", "controlDict", "system")
        + "application     buoyantBoussinesqSimpleFoam;\n"
          "startFrom       startTime;\nstartTime       0;\nstopAt          endTime;\n"
          "endTime         %d;\ndeltaT          1;\nwriteControl    timeStep;\n"
          "writeInterval   %d;\npurgeWrite      0;\nwriteFormat     ascii;\n"
          "writePrecision  10;\nwriteCompression off;\ntimeFormat      general;\n"
          "timePrecision   6;\nrunTimeModifiable false;\n"
        % (case.iterations, int(case.write_interval) or case.iterations))

    # ⚠ kOmegaSST needs a wall-distance method — v2512 has no default and
    # aborts on the first omega evaluation without one. RAS-only, so the
    # laminar files stay byte-identical.
    put("system/fvSchemes", _header("dictionary", "fvSchemes", "system")
        + "ddtSchemes      { default steadyState; }\n"
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
        put("system/fvSolution", _header("dictionary", "fvSolution", "system")
            + "solvers\n{\n"
              "    p_rgh { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0.01; }\n"
              "    \"(U|T|k|omega)\" { solver PBiCGStab; preconditioner DILU; tolerance 1e-10; relTol 0.1; }\n"
              "}\n\nSIMPLE\n{\n    nNonOrthogonalCorrectors 2;\n"
              "    pRefCell        0;\n    pRefValue       0;\n"
              "    residualControl { p_rgh 1e-5; U 1e-5; T 1e-6; \"(k|omega)\" 1e-5; }\n}\n\n"
              "relaxationFactors\n{\n    fields { p_rgh 0.7; }\n"
              "    equations { U 0.3; T 0.5; \"(k|omega)\" 0.5; }\n}\n")
    else:
        put("system/fvSolution", _header("dictionary", "fvSolution", "system")
            + "solvers\n{\n"
              "    p_rgh { solver PCG; preconditioner DIC; tolerance 1e-10; relTol 0.01; }\n"
              "    \"(U|T)\" { solver PBiCGStab; preconditioner DILU; tolerance 1e-10; relTol 0.1; }\n"
              "}\n\nSIMPLE\n{\n    nNonOrthogonalCorrectors 2;\n"
              "    pRefCell        0;\n    pRefValue       0;\n"
              "    residualControl { p_rgh 1e-5; U 1e-5; T 1e-6; }\n}\n\n"
              "relaxationFactors\n{\n    fields { p_rgh 0.7; }\n"
              "    equations { U 0.3; T 0.5; }\n}\n")

    return case
