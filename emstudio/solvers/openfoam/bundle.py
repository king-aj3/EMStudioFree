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

MEASURED for the mixed case (same three centres, same 0.20 m enclosure, same
400 K/m — two of the three cables shrunk from 20 mm to 10 mm, and nothing
else):

    1 x 20 mm   Nu 3.6097 @ Ra 5541   Churchill-Chu  -5.21 %   factor 0.9479
    2 x 10 mm   Nu 1.9997 @ Ra  625   Churchill-Chu -15.62 %   factor 0.8438

**The two sizes' factors are 12.3 % apart**, which is the whole argument for
per-size factors: one number for this bundle is wrong by 12 % for one of them.
Both still sit BELOW their own correlation, so the bundle error is per size,
not a property of one diameter. And the 20 mm cable recovers most of the
bundle penalty when its neighbours shrink — **Nu 3.1542 -> 3.6097 (+14.4 %),
Churchill-Chu error -19.72 % -> -5.21 %** — because smaller neighbours dump
less heat into the same air.

MIXED DIAMETERS — ONE PATCH PER SIZE
-------------------------------------
``Nu_D`` is built on a diameter, so a bundle of unlike cables has no single
Nusselt number and the first version REFUSED one rather than averaging. That
refusal was correct and useless: the shipped default cable mix is mixed, so the
button refused on first click.

What makes it answerable is that a mixed bundle does not need ONE Nusselt
number — it needs one PER SIZE. Each size group is written as its own STL
solid, becomes its own snappy geometry entry, and therefore its own **patch**,
so the solve reports a separate mean surface temperature per size and each size
gets ``Nu_D = D_i (dT/dn)_i / (T_i - T_inf)`` against its own diameter. Nothing
is averaged across unlike cables at any point.

⚠ **Uniform bundles are untouched.** One size means one group, named ``cables``
exactly as before, so the measured ladder above still describes what this
writer emits. That is deliberate: it is the anchor, and a change that quietly
re-meshed it would invalidate the only validated numbers here.

⚠ **The gradient may differ per size, and usually should.** Cables of different
sizes rarely carry the same loss. A scalar ``gradient`` is applied to every
group (equal flux DENSITY, not equal loss per metre) and the provenance says
so; pass per-cable gradients — or per-cable ``joule_w_per_m`` through
:mod:`emstudio.wire.bundle_convection` — to drive each size by its own I²R.

⚠ **Smaller cables are refined HARDER, on purpose.** snappy's levels are
relative to the background cell, so at one level a 10 mm cable gets half the
faces of a 20 mm one and its boundary layer is resolved half as well — the
small cable's Nu would carry a discretisation bias the large one does not.
``refine_match_perimeter`` adds ``ceil(log2(d_max/d_i))`` levels to the smaller
groups so every cable is resolved to a comparable angular resolution. Turning
it off is allowed and is a fidelity choice, not a free saving.

⚠ **The fluid is ONE fluid.** ``nu``/``alpha`` are fixed once, from the LARGEST
cable's nominal dT, and every group's ``Ra_D`` is then formed with its OWN
diameter and its OWN solved dT. Choosing per-group properties would be solving
a different fluid around each cable, which is not a physical case.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field as _field

__all__ = ["BundleCase", "SizeGroup", "TREFOIL", "cable_stl", "group_cables",
           "write_bundle"]

G = 9.81
T_REF = 300.0

#: Diameters closer than this are the SAME size. 1 nm — far below any real
#: manufacturing tolerance, so it only ever merges values that differ by
#: floating-point noise, never two cables a user meant to distinguish.
D_TOL_M = 1e-9


@dataclass
class SizeGroup:
    """Every cable of one diameter — the unit a Nusselt number is defined on.

    One group becomes one STL solid, one snappy geometry entry and therefore
    one OpenFOAM patch, which is what lets the result path report a separate
    surface temperature per size without averaging unlike cables.
    """

    d_cable: float
    centres: list
    gradient: float
    patch: str
    refine_min: int = 3
    refine_max: int = 4

    @property
    def r_cable(self):
        return self.d_cable / 2.0

    @property
    def n_cables(self):
        return len(self.centres)

    @property
    def stl_name(self):
        return "%s.stl" % self.patch


def group_cables(cables, base_refine=(3, 4), match_perimeter=True):
    """``[(x, y, d, gradient)]`` -> ordered :class:`SizeGroup` list.

    Groups are ordered LARGEST DIAMETER FIRST and the ordering is part of the
    contract: group 0 is the size whose nominal dT fixes the fluid properties,
    and a stable order is what makes patch names reproducible between runs.

    ⚠ A single group is named ``cables``, exactly as the uniform writer always
    named it. Multi-group names carry the index as well as the size
    (``cables_g1_d10p0``) because two sizes can round to the same millimetre
    label while being genuinely different cables — the index is what guarantees
    the patch names are distinct.

    ⚠ Cables of one diameter but different gradients are DIFFERENT groups:
    the boundary condition is per patch, so a group must be uniform in both.
    """
    if not cables:
        raise ValueError("a bundle needs at least one cable")
    keys, order = {}, []
    for x, y, d, grad in cables:
        if d <= 0:
            raise ValueError("cable diameter must be positive")
        k = (round(float(d) / D_TOL_M), round(float(grad), 12))
        if k not in keys:
            keys[k] = []
            order.append((float(d), float(grad), k))
        keys[k].append((float(x), float(y)))
    # largest first, then hottest first, then the key so ties are deterministic
    order.sort(key=lambda t: (-t[0], -abs(t[1]), t[2]))
    d_max = order[0][0]
    out = []
    for i, (d, grad, k) in enumerate(order):
        if len(order) == 1:
            patch = "cables"
        else:
            patch = "cables_g%d_d%sp%s" % (
                i, int(1000.0 * d), ("%.1f" % (1000.0 * d)).split(".")[1])
        bump = 0
        if match_perimeter and d < d_max:
            # ⚠ snappy levels are relative to the BACKGROUND cell, so a smaller
            # cable gets proportionally fewer faces at the same level. Matching
            # the angular resolution is what stops the small cable's Nu from
            # carrying a discretisation bias the large one does not.
            bump = int(math.ceil(math.log(d_max / d, 2.0) - 1e-12))
        out.append(SizeGroup(d_cable=d, centres=keys[k], gradient=grad,
                             patch=patch, refine_min=base_refine[0] + bump,
                             refine_max=base_refine[1] + bump))
    return out


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
    #: ``[(x, y, d)]`` or ``[(x, y, d, gradient)]``. ``None`` means the uniform
    #: bundle described by ``centres``/``d_cable``/``gradient`` — the original
    #: contract, and byte-for-byte the same case it always wrote.
    cables: list = None
    #: Add refinement levels to smaller cables so every size is resolved to a
    #: comparable angular resolution. See the module note; off is a fidelity
    #: choice, not a free saving.
    refine_match_perimeter: bool = True

    def __post_init__(self):
        if self.box_w <= 0 or self.box_h <= 0:
            raise ValueError("enclosure dimensions must be positive")
        if self.cells_x < 4:
            raise ValueError("need at least 4 background cells across")
        if self.cables is None:
            if not self.centres:
                raise ValueError("a bundle needs at least one cable")
            if self.d_cable <= 0:
                raise ValueError("cable diameter must be positive")
            if self.gradient == 0:
                raise ValueError("a zero wall gradient deposits no heat; "
                                 "the Nusselt number would be undefined")
            spec = [(x, y, self.d_cable, self.gradient)
                    for x, y in self.centres]
        else:
            if not self.cables:
                raise ValueError("a bundle needs at least one cable")
            spec = []
            for c in self.cables:
                if len(c) == 3:
                    x, y, d = c
                    grad = self.gradient
                elif len(c) == 4:
                    x, y, d, grad = c
                else:
                    raise ValueError(
                        "a cable is (x, y, diameter) or "
                        "(x, y, diameter, gradient); got %d values" % len(c))
                if d <= 0:
                    raise ValueError("cable diameter must be positive")
                if grad == 0:
                    raise ValueError(
                        "the cable at (%.4g, %.4g) has a zero wall gradient; "
                        "it deposits no heat and its Nusselt number would be "
                        "undefined. Leave an unheated member out of the solve "
                        "rather than giving it a meaningless number"
                        % (x, y))
                spec.append((float(x), float(y), float(d), float(grad)))
            # ⚠ Keep the scalar mirrors CONSISTENT with what is really solved.
            # A stale `d_cable` on a mixed case is exactly how a caller reads
            # a diameter the solve never used.
            self.centres = [(x, y) for x, y, _d, _g in spec]
            self.d_cable = max(d for _x, _y, d, _g in spec)
        self._spec = spec
        self._groups = group_cables(
            spec, base_refine=(self.refine_min, self.refine_max),
            match_perimeter=self.refine_match_perimeter)

        for cx, cy, d, _g in spec:
            r = d / 2.0
            if abs(cx) + r >= self.box_w / 2.0 or abs(cy) + r >= self.box_h / 2.0:
                raise ValueError(
                    "cable at (%.4g, %.4g) does not fit inside the enclosure"
                    % (cx, cy))
        for i, (ax, ay, da, _ga) in enumerate(spec):
            for bx, by, db, _gb in spec[i + 1:]:
                if math.hypot(ax - bx, ay - by) < (da + db) / 2.0:
                    raise ValueError("cables at (%.4g, %.4g) and (%.4g, %.4g) "
                                     "overlap" % (ax, ay, bx, by))

    @property
    def r_cable(self):
        return self.d_cable / 2.0

    @property
    def n_cables(self):
        return len(self._spec)

    @property
    def groups(self):
        """Size groups, largest first. One group == one patch."""
        return list(self._groups)

    @property
    def mixed(self):
        return len(self._groups) > 1

    @property
    def patch_names(self):
        return [g.patch for g in self._groups]

    @property
    def gradient_for(self):
        """``{patch: gradient}`` — what the result path must divide by."""
        return {g.patch: g.gradient for g in self._groups}

    @property
    def properties(self):
        """(nu, alpha) from the NOMINAL Ra, exactly as the cavity/cylinder do.

        ⚠ Nominal, because the real Ra depends on the solved dT. This only
        fixes the fluid; :func:`nusselt_from_patch` reports the Ra that
        actually resulted.

        ⚠ On a MIXED bundle the nominal is taken from the LARGEST cable, which
        is group 0. There is one fluid in the enclosure, so there is one
        (nu, alpha); per-group properties would be a different fluid around
        each cable, which is not a physical case. Every group's Ra_D is then
        formed from these properties with its own D and its own solved dT.
        """
        g0 = self._groups[0]
        dt_nom = g0.gradient * g0.d_cable / 2.0
        alpha = (G * (1.0 / T_REF) * dt_nom * g0.d_cable ** 3
                 / (self.ra_nominal * self.pr)) ** 0.5
        return self.pr * alpha, alpha

    @property
    def cable_area_m2(self):
        """Analytic wetted area of the cables — the geometry check's anchor."""
        return sum(math.pi * d * self.thickness for _x, _y, d, _g in self._spec)

    @property
    def fluid_volume_m3(self):
        """Analytic fluid volume. ⚠ Uses the TRUE circle; the STL is a
        polygon, so a meshed volume reads very slightly HIGH."""
        solid = sum(math.pi * (d / 2.0) ** 2 for _x, _y, d, _g in self._spec)
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

    # ⚠ ONE STL PER SIZE GROUP, and the solid's name IS the patch name. That is
    # the whole mechanism behind mixed-diameter support: snappy names a patch
    # after the geometry entry, so a separate surface per size is what gives
    # each size its own surface temperature to divide by its own D.
    for grp in case.groups:
        cable_stl(os.path.join(case_dir, "constant", "triSurface",
                               grp.stl_name),
                  grp.centres, grp.r_cable, -t, 2.0 * t,
                  facets=case.stl_facets, name=grp.patch)

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
        + "".join("%s\n{\n    extractionMethod    extractFromSurface;\n"
                  "    includedAngle       150;\n}\n" % g.stl_name
                  for g in case.groups))

    geom = "".join("    %s { type triSurfaceMesh; name %s; }\n"
                   % (g.stl_name, g.patch) for g in case.groups)
    feats = " ".join("{ file \"%s.eMesh\"; level 0; }" % g.patch
                     for g in case.groups)
    surfs = " ".join("%s { level (%d %d); }" % (g.patch, g.refine_min,
                                                g.refine_max)
                     for g in case.groups)

    # ⚠ locationInMesh must be in the FLUID and off any face plane. A point
    # near a corner is outside every cable by construction.
    put("system/snappyHexMeshDict",
        _header("dictionary", "snappyHexMeshDict", "system")
        + "castellatedMesh true;\nsnap true;\naddLayers false;\n\n"
          "geometry\n{\n" + geom + "}\n\n"
          "castellatedMeshControls\n{\n    maxLocalCells 2000000;\n"
          "    maxGlobalCells 8000000;\n    minRefinementCells 10;\n"
          "    nCellsBetweenLevels 3;\n    maxLoadUnbalance 0.10;\n"
          "    resolveFeatureAngle 30;\n    allowFreeStandingZoneFaces true;\n"
          "    features ( " + feats + " );\n"
          "    refinementSurfaces { " + surfs + " }\n"
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
        # ⚠ `%` binds tighter than `+`, so these three fill the LAST literal
        # group only — the one that starts at `refinementRegions`. The geometry
        # / features / refinementSurfaces text is spliced in above, not
        # formatted, precisely so a patch name containing a `%` could never be
        # read as a conversion.
        % (-hw * 0.95, -hh * 0.95, t / 2.0))

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

    def per_group(template):
        """One boundaryField entry per size patch, in group order."""
        return "".join(template % g.patch for g in case.groups)

    # ⚠ mixed/valueFraction 0 == a pure prescribed gradient, but it WRITES the
    # patch values. fixedGradient does not, and the result path reads nothing.
    #
    # ⚠ EACH SIZE GETS ITS OWN refGradient. That is the second half of
    # mixed-diameter support: separate patches would be pointless if they all
    # carried the same flux, and cables of different sizes rarely dissipate the
    # same loss per metre.
    put("0/T", _field_file(
        "T", "[0 0 0 1 0 0 0]", "%.10g" % case.t_amb,
        "".join(
            "    %s { type mixed; refValue uniform %.10g; refGradient uniform "
            "%.10g; valueFraction uniform 0; value uniform %.10g; }\n"
            % (g.patch, case.t_amb, g.gradient, case.t_amb)
            for g in case.groups)
        + "    enclosure { type fixedValue; value uniform %.10g; }\n"
          "    frontAndBack { type symmetry; }\n" % case.t_amb))
    put("0/U", _field_file(
        "U", "[0 1 -1 0 0 0 0]", "(0 0 0)",
        per_group("    %s { type noSlip; }\n")
        + "    enclosure { type noSlip; }\n"
          "    frontAndBack { type symmetry; }\n"))
    put("0/p_rgh", _field_file(
        "p_rgh", "[0 2 -2 0 0 0 0]", "0",
        per_group("    %s { type fixedFluxPressure; value uniform 0; }\n")
        + "    enclosure { type fixedFluxPressure; value uniform 0; }\n"
          "    frontAndBack { type symmetry; }\n"))
    put("0/alphat", _field_file(
        "alphat", "[0 2 -1 0 0 0 0]", "0",
        per_group("    %s { type calculated; value uniform 0; }\n")
        + "    enclosure { type calculated; value uniform 0; }\n"
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
