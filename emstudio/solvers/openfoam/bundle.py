# SPDX-License-Identifier: LGPL-2.1-or-later
"""Natural convection from a CABLE BUNDLE in an enclosure — where the
correlation EMStudio ships is wrong, and by how much.

``wire/thermal.py`` takes its film coefficient from Churchill-Chu, which is
correct for an isolated horizontal cylinder in unbounded quiescent air. Real
cables are bundled and the air is confined. This module solves that case.

MEASURED, on the ladder this module's gate reproduces (D 20 mm, trefoil at
30 mm pitch, 200 mm enclosure, uniform wall flux):

    1 cable, 0.40 m box   Nu 3.9830 @ Ra 5021   Churchill-Chu +6.99 %
    1 cable, 0.20 m box   Nu 3.8621 @ Ra 5179   Churchill-Chu +3.01 %
    3 cables, 0.20 m box  Nu 3.1542 @ Ra 6341   Churchill-Chu -19.72 %

The single-cable cases sit INSIDE the Churchill-Chu/Morgan envelope, which is
what validates the pipeline. The bundle sits decisively BELOW it. Confinement
alone costs 3 %; the bundle costs a further 18 %. Over-predicted `h` means
over-predicted cooling means over-predicted ampacity, so the error is in the
unsafe direction.

WHY THE BOUNDARY CONDITION IS FLUX, NOT TEMPERATURE
----------------------------------------------------
Rungs 1 and 2 fixed the wall temperature and read the gradient by exploiting
``blockMesh``'s predictable cell ordering. snappyHexMesh destroys that: the
mesh is unstructured, so no index arithmetic finds the wall-adjacent cell, and
the alternatives are reconstructing cell centroids from ``polyMesh`` or using
a function object (which every other result path here avoids on purpose).

Prescribing the FLUX inverts the problem into one that needs neither:

    Nu_D = D * (dT/dn)_wall / (T_surface - T_ambient)

The gradient is an input; the surface temperature is written straight into the
field's ``boundaryField``. No conductivity is needed — it cancels. It is also
the physically honest condition: a Joule-heated conductor knows its heat
output, not its surface temperature.

⚠ **Ra is an OUTPUT here, not an input.** dT is solved for, so the comparison
against any correlation must be made at the Ra the solve produced, not at a
nominal one. Rungs 1 and 2 had it the other way round.

THREE TRAPS, EACH OF WHICH FAILS SILENTLY OR MISLEADINGLY
-----------------------------------------------------------
* **``writePrecision`` must be emitted explicitly.** It defaults to 6, and
  snappyHexMesh ABORTS when the merge tolerance (1e-6) is finer than the write
  precision. The trap is omission, not a wrong value.
* **front/back must be ``symmetry``, not ``symmetryPlane`` or ``empty``.**
  ``symmetryPlane`` refuses a patch whose faces are not co-planar, and front
  and back have opposing normals. ``empty`` is worse: snappy refines
  ISOTROPICALLY, so it splits the single z-layer and the mesh is no longer 2-D
  — checkMesh then fails "faces on empty patches is not divisible by the
  number of cells". Nothing drives axial variation, so ``symmetry`` keeps the
  physics 2-D while letting snappy refine freely.
* **``fixedGradient`` writes NO ``value``.** Verified by reading the written
  file: it emits ``type`` and ``gradient`` only, so the patch temperatures the
  whole result path depends on are never written. ``mixed`` with
  ``valueFraction 0`` is the same boundary condition mathematically — a pure
  prescribed gradient — and its ``write()`` does emit ``value``.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field as _field

__all__ = ["BundleCase", "TREFOIL", "cable_stl", "write_bundle"]

G = 9.81
T_REF = 300.0


def trefoil(pitch):
    """Three cable centres in the standard trefoil, centroid at the origin."""
    return [(-pitch / 2.0, -pitch * 0.2887),
            (+pitch / 2.0, -pitch * 0.2887),
            (0.0, pitch * 0.5774)]


#: The default arrangement. Trefoil is the shape the helix work already cares
#: about — see the current-sharing findings — so it is the useful default.
TREFOIL = trefoil(0.030)


@dataclass
class BundleCase:
    """A flux-heated cable set in a closed rectangular enclosure."""

    centres: list = _field(default_factory=lambda: list(TREFOIL))
    d_cable: float = 0.020
    box_w: float = 0.200
    box_h: float = 0.200
    thickness: float = 0.004         # one background cell deep (2-D)
    gradient: float = 400.0          # K/m at the cable surface
    ra_nominal: float = 1.0e4        # sets nu/alpha; Ra is an OUTPUT
    pr: float = 0.71
    cells_x: int = 100               # background cells across the enclosure
    refine_min: int = 3              # snappy surface refinement (min max)
    refine_max: int = 4
    iterations: int = 20000
    write_interval: int = 5000
    t_amb: float = T_REF
    stl_facets: int = 64

    def __post_init__(self):
        if not self.centres:
            raise ValueError("a bundle needs at least one cable")
        if self.d_cable <= 0:
            raise ValueError("cable diameter must be positive")
        if self.box_w <= 0 or self.box_h <= 0:
            raise ValueError("enclosure dimensions must be positive")
        if self.gradient == 0:
            raise ValueError("a zero wall gradient deposits no heat; "
                             "the Nusselt number would be undefined")
        if self.cells_x < 4:
            raise ValueError("need at least 4 background cells across")
        r = self.d_cable / 2.0
        for cx, cy in self.centres:
            if abs(cx) + r >= self.box_w / 2.0 or abs(cy) + r >= self.box_h / 2.0:
                raise ValueError(
                    "cable at (%.4g, %.4g) does not fit inside the enclosure"
                    % (cx, cy))
        for i, (ax, ay) in enumerate(self.centres):
            for bx, by in self.centres[i + 1:]:
                if math.hypot(ax - bx, ay - by) < self.d_cable:
                    raise ValueError("cables at (%.4g, %.4g) and (%.4g, %.4g) "
                                     "overlap" % (ax, ay, bx, by))

    @property
    def r_cable(self):
        return self.d_cable / 2.0

    @property
    def n_cables(self):
        return len(self.centres)

    @property
    def properties(self):
        """(nu, alpha) from the NOMINAL Ra, exactly as the cavity/cylinder do.

        ⚠ Nominal, because the real Ra depends on the solved dT. This only
        fixes the fluid; :func:`nusselt_from_patch` reports the Ra that
        actually resulted.
        """
        dt_nom = self.gradient * self.d_cable / 2.0
        alpha = (G * (1.0 / T_REF) * dt_nom * self.d_cable ** 3
                 / (self.ra_nominal * self.pr)) ** 0.5
        return self.pr * alpha, alpha

    @property
    def cable_area_m2(self):
        """Analytic wetted area of the cables — the geometry check's anchor."""
        return self.n_cables * math.pi * self.d_cable * self.thickness

    @property
    def fluid_volume_m3(self):
        """Analytic fluid volume. ⚠ Uses the TRUE circle; the STL is a
        polygon, so a meshed volume reads very slightly HIGH."""
        solid = self.n_cables * math.pi * self.r_cable ** 2
        return (self.box_w * self.box_h - solid) * self.thickness


def cable_stl(path, centres, r, z0, z1, facets=64, name="cables"):
    """ASCII STL of closed cylinders, written from parameters.

    No FreeCAD import: the writer stays Qt-free and unit-testable, and the
    offline half of the gate runs with no solver and no GUI. Real document
    geometry can be substituted later through the existing
    ``solvers/openems/geometry.export_stl`` path.

    ⚠ The cylinders must OVERHANG the domain in z (z0 < 0 < thickness < z1) so
    they cut cleanly through it; a surface that stops inside the domain leaves
    snappy trying to close a hole.
    """
    if facets < 8:
        raise ValueError("need at least 8 facets to approximate a circle")
    if r <= 0:
        raise ValueError("cable radius must be positive")

    def tri(fh, a, b, c):
        ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        fh.write("facet normal %.9g %.9g %.9g\n outer loop\n"
                 % (nx / m, ny / m, nz / m))
        for p in (a, b, c):
            fh.write("  vertex %.9g %.9g %.9g\n" % p)
        fh.write(" endloop\nendfacet\n")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("solid %s\n" % name)
        for cx, cy in centres:
            ring = [(cx + r * math.cos(2 * math.pi * k / facets),
                     cy + r * math.sin(2 * math.pi * k / facets))
                    for k in range(facets)]
            for k in range(facets):
                x0, y0 = ring[k]
                x1, y1 = ring[(k + 1) % facets]
                tri(fh, (x0, y0, z0), (x1, y1, z0), (x1, y1, z1))
                tri(fh, (x0, y0, z0), (x1, y1, z1), (x0, y0, z1))
                tri(fh, (cx, cy, z0), (x1, y1, z0), (x0, y0, z0))
                tri(fh, (cx, cy, z1), (x0, y0, z1), (x1, y1, z1))
        fh.write("endsolid %s\n" % name)


def _header(cls, obj, loc):
    return ("FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
            "    class       %s;\n    location    \"%s\";\n    object      %s;\n}\n\n"
            % (cls, loc, obj))


def _field_file(obj, dims, internal, boundary):
    return (_header("volVectorField" if obj == "U" else "volScalarField", obj, "0")
            + "dimensions      %s;\n\ninternalField   uniform %s;\n\n"
              "boundaryField\n{\n%s}\n" % (dims, internal, boundary))


def write_bundle(case_dir, case=None):
    """Write a complete bundle case. Returns the resolved :class:`BundleCase`.

    Plain text plus one ASCII STL — no OpenFOAM and no FreeCAD import — so the
    offline half of the gate runs anywhere.
    """
    case = case or BundleCase()
    nu, alpha = case.properties
    hw, hh = case.box_w / 2.0, case.box_h / 2.0
    t = case.thickness

    for sub in ("0", "constant/triSurface", "system"):
        os.makedirs(os.path.join(case_dir, sub), exist_ok=True)

    cable_stl(os.path.join(case_dir, "constant", "triSurface", "cables.stl"),
              case.centres, case.r_cable, -t, 2.0 * t, facets=case.stl_facets)

    def put(rel, text):
        p = os.path.join(case_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("/*--------------------------------*- C++ -*-------"
                     "---------------------*/\n")
            fh.write(text)

    nx = int(case.cells_x)
    ny = max(1, int(round(nx * case.box_h / case.box_w)))
    put("system/blockMeshDict", _header("dictionary", "blockMeshDict", "system")
        + "scale   1;\n\nvertices\n(\n"
        + "".join("    (%.10g %.10g %.10g)\n" % v for v in (
            (-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0),
            (-hw, -hh, t), (hw, -hh, t), (hw, hh, t), (-hw, hh, t)))
        + ");\n\nblocks\n(\n    hex (0 1 2 3 4 5 6 7) (%d %d 1) "
          "simpleGrading (1 1 1)\n);\n\nedges ();\n\nboundary\n(\n"
          "    enclosure { type wall; faces ( (0 4 7 3) (1 2 6 5) "
          "(0 1 5 4) (3 7 6 2) ); }\n"
          # ⚠ symmetry, NOT symmetryPlane (front and back are not co-planar)
          # and NOT empty (snappy refines in z, breaking 2-D).
          "    frontAndBack { type symmetry; faces ( (0 3 2 1) (4 5 6 7) ); }\n"
          ");\n\nmergePatchPairs ();\n" % (nx, ny))

    put("system/surfaceFeatureExtractDict",
        _header("dictionary", "surfaceFeatureExtractDict", "system")
        + "cables.stl\n{\n    extractionMethod    extractFromSurface;\n"
          "    includedAngle       150;\n}\n")

    # ⚠ locationInMesh must be in the FLUID and off any face plane. A point
    # near a corner is outside every cable by construction.
    put("system/snappyHexMeshDict",
        _header("dictionary", "snappyHexMeshDict", "system")
        + "castellatedMesh true;\nsnap true;\naddLayers false;\n\n"
          "geometry\n{\n    cables.stl { type triSurfaceMesh; name cables; }\n}\n\n"
          "castellatedMeshControls\n{\n    maxLocalCells 2000000;\n"
          "    maxGlobalCells 8000000;\n    minRefinementCells 10;\n"
          "    nCellsBetweenLevels 3;\n    maxLoadUnbalance 0.10;\n"
          "    resolveFeatureAngle 30;\n    allowFreeStandingZoneFaces true;\n"
          "    features ( { file \"cables.eMesh\"; level 0; } );\n"
          "    refinementSurfaces { cables { level (%d %d); } }\n"
          "    refinementRegions {}\n    locationInMesh (%.10g %.10g %.10g);\n}\n\n"
          "snapControls\n{\n    nSmoothPatch 3;\n    tolerance 2.0;\n"
          "    nSolveIter 50;\n    nRelaxIter 5;\n    nFeatureSnapIter 10;\n"
          "    implicitFeatureSnap false;\n    explicitFeatureSnap true;\n"
          "    multiRegionFeatureSnap false;\n}\n\n"
          "addLayersControls\n{\n    relativeSizes true;\n    layers {}\n"
          "    expansionRatio 1.0;\n    finalLayerThickness 0.3;\n"
          "    minThickness 0.1;\n    nGrow 0;\n    featureAngle 60;\n"
          "    nRelaxIter 3;\n    nSmoothSurfaceNormals 1;\n    nSmoothNormals 3;\n"
          "    nSmoothThickness 10;\n    maxFaceThicknessRatio 0.5;\n"
          "    maxThicknessToMedialRatio 0.3;\n    minMedianAxisAngle 90;\n"
          "    nBufferCellsNoExtrude 0;\n    nLayerIter 50;\n}\n\n"
          "meshQualityControls\n{\n    maxNonOrtho 65;\n    maxBoundarySkewness 20;\n"
          "    maxInternalSkewness 4;\n    maxConcave 80;\n    minVol 1e-13;\n"
          "    minTetQuality 1e-30;\n    minArea -1;\n    minTwist 0.02;\n"
          "    minDeterminant 0.001;\n    minFaceWeight 0.02;\n    minVolRatio 0.01;\n"
          "    minTriangleTwist -1;\n    nSmoothScale 4;\n    errorReduction 0.75;\n}\n\n"
          "mergeTolerance 1e-6;\n"
        % (case.refine_min, case.refine_max, -hw * 0.95, -hh * 0.95, t / 2.0))

    put("constant/transportProperties",
        _header("dictionary", "transportProperties", "constant")
        + "transportModel  Newtonian;\nnu              %.10g;\n"
          "beta            %.10g;\nTRef            %.10g;\n"
          "Pr              %.10g;\nPrt             0.85;\n"
        % (nu, 1.0 / T_REF, case.t_amb, case.pr))
    put("constant/turbulenceProperties",
        _header("dictionary", "turbulenceProperties", "constant")
        + "simulationType  laminar;\n")
    put("constant/g", _header("uniformDimensionedVectorField", "g", "constant")
        + "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 -%.10g 0);\n" % G)

    # ⚠ mixed/valueFraction 0 == a pure prescribed gradient, but it WRITES the
    # patch values. fixedGradient does not, and the result path reads nothing.
    put("0/T", _field_file(
        "T", "[0 0 0 1 0 0 0]", "%.10g" % case.t_amb,
        "    cables { type mixed; refValue uniform %.10g; refGradient uniform "
        "%.10g; valueFraction uniform 0; value uniform %.10g; }\n"
        "    enclosure { type fixedValue; value uniform %.10g; }\n"
        "    frontAndBack { type symmetry; }\n"
        % (case.t_amb, case.gradient, case.t_amb, case.t_amb)))
    put("0/U", _field_file(
        "U", "[0 1 -1 0 0 0 0]", "(0 0 0)",
        "    cables { type noSlip; }\n    enclosure { type noSlip; }\n"
        "    frontAndBack { type symmetry; }\n"))
    put("0/p_rgh", _field_file(
        "p_rgh", "[0 2 -2 0 0 0 0]", "0",
        "    cables { type fixedFluxPressure; value uniform 0; }\n"
        "    enclosure { type fixedFluxPressure; value uniform 0; }\n"
        "    frontAndBack { type symmetry; }\n"))
    put("0/alphat", _field_file(
        "alphat", "[0 2 -1 0 0 0 0]", "0",
        "    cables { type calculated; value uniform 0; }\n"
        "    enclosure { type calculated; value uniform 0; }\n"
        "    frontAndBack { type symmetry; }\n"))

    # ⚠ writePrecision is NOT optional: it defaults to 6 and snappyHexMesh
    # aborts because mergeTolerance 1e-6 is finer than the write precision.
    put("system/controlDict", _header("dictionary", "controlDict", "system")
        + "application     buoyantBoussinesqSimpleFoam;\n"
          "startFrom       startTime;\nstartTime       0;\nstopAt          endTime;\n"
          "endTime         %d;\ndeltaT          1;\nwriteControl    timeStep;\n"
          "writeInterval   %d;\npurgeWrite      0;\nwriteFormat     ascii;\n"
          "writePrecision  10;\nwriteCompression off;\ntimeFormat      general;\n"
          "timePrecision   6;\nrunTimeModifiable false;\n"
        % (case.iterations, int(case.write_interval) or case.iterations))

    put("system/fvSchemes", _header("dictionary", "fvSchemes", "system")
        + "ddtSchemes      { default steadyState; }\n"
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

    # ⚠ nNonOrthogonalCorrectors 2, not 0: the snapped mesh runs to ~35 deg
    # non-orthogonality where the structured rungs were at 1.5e-6.
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
