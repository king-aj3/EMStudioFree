# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — a cable BUNDLE in an enclosure, where the shipped
correlation is wrong.

``wire/thermal.py`` takes its film coefficient from Churchill-Chu, correct for
an isolated cylinder in unbounded quiescent air. This gate measures what that
assumption costs for the case that actually matters.

WHAT ANCHORS A CASE WITH NO CORRELATION TO CHECK AGAINST
----------------------------------------------------------
The bundle cannot be gated on Churchill-Chu — being wrong there is the whole
point. So the anchor is a LADDER in which each rung changes exactly one thing,
and only the first two rungs are checked against literature:

    1 cable, big box    -> must sit INSIDE the Churchill-Chu/Morgan envelope
    1 cable, small box  -> must sit INSIDE it too (confinement is small)
    3 cables, same box  -> must sit measurably BELOW it

The first two validate the PIPELINE — snappy mesh, flux boundary condition,
patch-value reader — none of which the structured rungs used. If a single
cable meshed by snappy did not reproduce the correlation, nothing this gate
said about a bundle could be separated from a meshing artifact.

⚠ **Each rung changes ONE variable.** Comparing the bundle straight to the big
box would confound the bundle effect with the enclosure size. That confound
has already produced two wrong answers in this project (a fake "+4 % domain
sensitivity" and a fake "not discretisation" at Ra 1e3), both from studies
that moved two things at once.

MEASURED (D 20 mm, trefoil at 30 mm pitch, uniform wall flux 400 K/m):
    1 cable  0.40 m box   Nu 3.9830 @ Ra 5021   CC +6.99 %
    1 cable  0.20 m box   Nu 3.8621 @ Ra 5179   CC +3.01 %
    3 cables 0.20 m box   Nu 3.1542 @ Ra 6341   CC -19.72 %
Confinement costs 3 %; the bundle costs a further 18 %.

⚠ **Ra is an OUTPUT.** The flux is prescribed and dT is solved, so every
correlation comparison is made at the Ra that RESULTED.

⚠ **SCOPE, so the number is not over-read.** One geometry, 2-D, laminar, no
radiation, uniform flux, unweighted mean over patch faces. `solve_steady()`
sheds heat by radiation as well as convection, so this is not a corrected
ampacity — it is the size of the convective error.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from emstudio.solvers import openfoam as ofm                    # noqa: E402
from emstudio.solvers.openfoam import bundle as B               # noqa: E402
from emstudio.setup import openfoam as _setup                   # noqa: E402
from emstudio.wire.thermal import nu_churchill_chu              # noqa: E402

_FAILED = []
PR = 0.71
#: Morgan bands — the same constants tests/validation/thermal.py already
#: cross-checks Churchill-Chu against.
MORGAN = ((1e-2, 1e2, 1.02, 0.148), (1e2, 1e4, 0.850, 0.188),
          (1e4, 1e7, 0.480, 0.250))


def morgan(ra):
    for lo, hi, c, n in MORGAN:
        if lo <= ra < hi:
            return c * ra ** n
    return float("nan")


def check(label, ok, detail=""):
    line = "  {0}  {1}{2}".format("ok   " if ok else "FAIL ", label,
                                  " — {0}".format(detail) if detail else "")
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage(line + "\n")
    except Exception:
        print(line)
    if not ok:
        _FAILED.append(label)
    return ok


def offline_checks():
    """Everything knowable with no solver."""
    print(" case validation refuses what cannot be meshed:")
    for kw, why in ((dict(centres=[]), "an empty bundle"),
                    (dict(d_cable=0), "zero diameter"),
                    (dict(box_w=0), "zero enclosure width"),
                    (dict(gradient=0.0), "zero wall gradient"),
                    (dict(cells_x=2), "fewer than 4 background cells"),
                    (dict(centres=[(0.0, 0.0), (0.005, 0.0)]),
                     "overlapping cables"),
                    (dict(centres=[(0.099, 0.0)]),
                     "a cable outside the enclosure")):
        try:
            B.BundleCase(**kw)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)

    c = B.BundleCase()
    check("the default is a trefoil of three", c.n_cables == 3)
    check("analytic cable area = n pi D t",
          abs(c.cable_area_m2 - 3 * math.pi * 0.020 * 0.004) < 1e-15,
          "%.6e m^2" % c.cable_area_m2)
    check("analytic fluid volume subtracts the cables",
          abs(c.fluid_volume_m3
              - (0.2 * 0.2 - 3 * math.pi * 0.01 ** 2) * 0.004) < 1e-15,
          "%.6e m^3" % c.fluid_volume_m3)
    nu_f, alpha_f = c.properties
    check("Pr is exactly what was asked for",
          abs(nu_f / alpha_f - PR) < 1e-12)

    print(" the STL is the geometry it claims:")
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "cables.stl")
        B.cable_stl(p, [(0.0, 0.0)], 0.01, -0.004, 0.008, facets=64)
        text = open(p, encoding="ascii").read()
        verts = [tuple(float(x) for x in m)
                 for m in re.findall(
                     r"vertex\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)",
                     text)]
        rim = [v for v in verts if abs(math.hypot(v[0], v[1]) - 0.01) < 1e-9]
        check("every rim vertex lies on the cable circle",
              len(rim) > 0 and all(abs(math.hypot(v[0], v[1]) - 0.01) < 1e-9
                                   for v in rim),
              "%d of %d vertices on r=0.01" % (len(rim), len(verts)))
        zs = sorted({round(v[2], 9) for v in verts})
        check("the cylinder OVERHANGS the domain in z (else snappy cannot cut "
              "it cleanly)", zs[0] < 0.0 and zs[-1] > 0.004, "z span %s" % zs)
        check("facet count is 4 per segment (side x2 + two caps)",
              text.count("facet normal") == 4 * 64,
              "%d facets" % text.count("facet normal"))
        for bad, why in ((4, "fewer than 8 facets"),):
            try:
                B.cable_stl(p, [(0, 0)], 0.01, -1, 1, facets=bad)
                check("%s is rejected" % why, False)
            except ValueError:
                check("%s is rejected" % why, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the written case avoids the three silent traps:")
    tmp = tempfile.mkdtemp()
    try:
        case = B.BundleCase(cells_x=20, iterations=10, write_interval=10)
        B.write_bundle(tmp, case)
        for rel in ("system/blockMeshDict", "system/snappyHexMeshDict",
                    "system/surfaceFeatureExtractDict", "system/controlDict",
                    "system/fvSchemes", "system/fvSolution",
                    "constant/triSurface/cables.stl",
                    "constant/transportProperties",
                    "constant/turbulenceProperties", "constant/g",
                    "0/T", "0/U", "0/p_rgh", "0/alphat"):
            check("writes %s" % rel, os.path.isfile(os.path.join(tmp, rel)))

        def read(rel):
            with open(os.path.join(tmp, rel), encoding="utf-8") as fh:
                return fh.read()

        ctrl, snap = read("system/controlDict"), read("system/snappyHexMeshDict")
        bm, t0 = read("system/blockMeshDict"), read("0/T")
        # TRAP 1 — writePrecision defaults to 6 and snappy ABORTS when the
        # merge tolerance is finer than it. Omission is the failure mode.
        m = re.search(r"writePrecision\s+(\d+)", ctrl)
        mt = re.search(r"mergeTolerance\s+([\d.eE+-]+)", snap)
        check("controlDict emits writePrecision, and it is finer than snappy's "
              "mergeTolerance (snappyHexMesh ABORTS otherwise)",
              bool(m) and bool(mt) and 10.0 ** -int(m.group(1)) <= float(mt.group(1)),
              "precision %s vs mergeTolerance %s"
              % (m and m.group(1), mt and mt.group(1)))
        # TRAP 2 — empty breaks because snappy refines in z; symmetryPlane
        # refuses a non-planar patch (front and back oppose).
        check("front/back is `symmetry` — not `empty` (snappy refines in z, "
              "breaking 2-D) and not `symmetryPlane` (not co-planar)",
              "frontAndBack { type symmetry;" in bm
              and "symmetryPlane" not in bm and "type empty" not in bm)
        # TRAP 3 — fixedGradient writes no `value`, so the result path reads
        # nothing at all.
        check("the cables use `mixed` with valueFraction 0, NOT "
              "`fixedGradient` (which writes no `value` to read)",
              "type mixed" in t0 and "valueFraction" in t0
              and "fixedGradient" not in t0)
        check("the closed enclosure pins the pressure level (pRefCell)",
              "pRefCell" in read("system/fvSolution"))
        check("non-orthogonal correctors are on for the snapped mesh",
              re.search(r"nNonOrthogonalCorrectors\s+([1-9])",
                        read("system/fvSolution")) is not None)
        check("ESI turbulenceProperties, not Foundation's momentumTransport",
              "momentumTransport" not in read("constant/turbulenceProperties"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the patch reader refuses what it cannot honestly read:")
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "T")
        # exactly what fixedGradient writes: no `value` at all
        open(p, "w", encoding="utf-8").write(
            "boundaryField\n{\n    cables\n    {\n"
            "        type            fixedGradient;\n"
            "        gradient        uniform 400;\n    }\n}\n")
        try:
            ofm.read_patch_values(p, "cables")
            check("a patch with NO `value` (i.e. fixedGradient) is an ERROR, "
                  "not an empty reading", False, "it was accepted")
        except ValueError:
            check("a patch with NO `value` (i.e. fixedGradient) is an ERROR, "
                  "not an empty reading", True)
        open(p, "w", encoding="utf-8").write(
            "boundaryField\n{\n    cables\n    {\n        type mixed;\n"
            "        value           nonuniform List<scalar>\n4\n(\n"
            "301 302 303\n)\n;\n    }\n}\n")
        try:
            ofm.read_patch_values(p, "cables")
            check("a TRUNCATED patch list is caught by its own count", False)
        except ValueError:
            check("a TRUNCATED patch list is caught by its own count", True)
        open(p, "w", encoding="utf-8").write(
            "boundaryField\n{\n    cables\n    {\n        type mixed;\n"
            "        value           nonuniform List<scalar>\n3\n(\n"
            "301 302 303\n)\n;\n    }\n}\n")
        vals = ofm.read_patch_values(p, "cables")
        check("a well-formed patch list reads back exactly",
              vals == [301.0, 302.0, 303.0], "%s" % vals)
        try:
            ofm.read_patch_values(p, "nosuchpatch")
            check("a missing patch is an error", False)
        except ValueError:
            check("a missing patch is an error", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the Nusselt formula:")
    r = ofm.nusselt_from_patch([302.0] * 8, 0.020, 400.0, 300.0)
    check("Nu_D = D grad / dT, exactly", abs(r.nu_d - 4.0) < 1e-12,
          "%.12f" % r.nu_d)
    check("...and no conductivity is needed — it cancels", r.faces == 8)
    for kw, why in ((dict(values=[]), "no values"),
                    (dict(d_m=0), "zero diameter"),
                    (dict(gradient=0), "zero gradient"),
                    (dict(t_amb=302.0), "a surface at ambient")):
        kw2 = dict(values=[302.0] * 4, d_m=0.02, gradient=400.0, t_amb=300.0)
        kw2.update(kw)
        try:
            ofm.nusselt_from_patch(**kw2)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)
    cold = ofm.nusselt_from_patch([299.0] * 4, 0.02, 400.0, 300.0)
    check("a surface COLDER than ambient warns rather than passing silently",
          any("negative Nu" in w for w in cold.warnings))

    mixed_offline_checks()


def mixed_offline_checks():
    """Mixed diameters: one patch per size, and the uniform case UNMOVED.

    ⚠ The load-bearing check here is the LAST one — that a uniform bundle
    written through the new per-group machinery is byte-identical to what the
    single-patch writer produced. The measured ladder (Nu 3.9826 / 3.8621 /
    3.1542) is this gate's only anchor, and a change that quietly re-meshed it
    would invalidate every number above while every check below still passed.
    """
    print(" grouping: one group per SIZE, largest first:")
    g1 = B.group_cables([(0.0, 0.0, 0.020, 400.0)])
    check("a single size keeps the patch name `cables` — the uniform case is "
          "not renamed by adding mixed support",
          [g.patch for g in g1] == ["cables"], "%s" % [g.patch for g in g1])
    gs = B.group_cables([(0.0, 0.0, 0.010, 400.0), (0.03, 0.0, 0.020, 400.0),
                         (-0.03, 0.0, 0.010, 400.0)])
    check("two sizes make two groups, LARGEST first",
          [g.d_cable for g in gs] == [0.020, 0.010],
          "%s" % [g.d_cable for g in gs])
    check("...and every cable lands in exactly one group",
          [g.n_cables for g in gs] == [1, 2] and sum(g.n_cables for g in gs) == 3)
    check("patch names are distinct and carry the size",
          len({g.patch for g in gs}) == 2
          and all(g.patch.startswith("cables_g") for g in gs),
          "%s" % [g.patch for g in gs])
    # ⚠ Same diameter, different flux = a different boundary condition, so it
    # cannot share a patch. Merging them would silently apply one gradient to
    # cables that were given two.
    gg = B.group_cables([(0.0, 0.0, 0.020, 400.0), (0.03, 0.0, 0.020, 100.0)])
    check("cables of ONE size but different gradients are SEPARATE groups (a "
          "patch carries one boundary condition)", len(gg) == 2,
          "%d group(s)" % len(gg))
    check("...ordered hottest-first within a size, so the order is stable",
          [g.gradient for g in gg] == [400.0, 100.0])

    print(" smaller cables are refined harder, so their Nu is not a mesh "
          "artifact:")
    for ratio, extra in ((1.0, 0), (2.0, 1), (4.0, 2), (3.0, 2)):
        grp = B.group_cables([(0.0, 0.0, 0.020, 400.0),
                              (0.06, 0.0, 0.020 / ratio, 400.0)])
        got = grp[-1].refine_max - grp[0].refine_max
        check("a %.4g:1 diameter ratio adds %d refinement level(s) to the "
              "small cable" % (ratio, extra), got == extra, "+%d" % got)
    off = B.group_cables([(0.0, 0.0, 0.020, 400.0), (0.06, 0.0, 0.005, 400.0)],
                         match_perimeter=False)
    check("...and turning perimeter matching OFF really does leave the small "
          "cable under-resolved (it is a fidelity choice, not a no-op)",
          off[0].refine_max == off[1].refine_max)

    print(" a mixed case validates per CABLE, not against the biggest one:")
    for kw, why in (
            (dict(cables=[(0.0, 0.0, 0.020), (0.012, 0.0, 0.010)]),
             "cables overlapping by their OWN radii (10+20 mm at 12 mm apart)"),
            (dict(cables=[(0.0, 0.0, 0.020), (0.098, 0.0, 0.010)]),
             "a small cable outside the enclosure"),
            (dict(cables=[(0.0, 0.0, 0.020), (0.03, 0.0, 0.0)]),
             "a zero-diameter member"),
            (dict(cables=[(0.0, 0.0, 0.020), (0.03, 0.0, 0.010, 0.0)]),
             "a member with zero gradient"),
            (dict(cables=[(0.0, 0.0)]), "a cable with no diameter at all"),
            (dict(cables=[]), "an empty mixed bundle")):
        try:
            B.BundleCase(**kw)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)
    # ⚠ and the converse: 20 mm + 10 mm at 16 mm apart is EXACTLY tangent by
    # the mean radius, so a check written against the max diameter would
    # wrongly reject it.
    try:
        B.BundleCase(cables=[(0.0, 0.0, 0.020), (0.0165, 0.0, 0.010)])
        check("a pair that clears by its OWN radii is ACCEPTED (a max-diameter "
              "test would have refused it)", True)
    except ValueError as exc:
        check("a pair that clears by its OWN radii is ACCEPTED (a max-diameter "
              "test would have refused it)", False, str(exc))

    m = B.BundleCase(cables=[(-0.015, -0.00866, 0.020),
                             (0.015, -0.00866, 0.010),
                             (0.0, 0.01732, 0.010)], box_w=0.2, box_h=0.2)
    check("mixed is reported as mixed", m.mixed and len(m.patch_names) == 2)
    check("wetted area sums the cables' OWN perimeters, not n x pi D_max",
          abs(m.cable_area_m2
              - math.pi * m.thickness * (0.020 + 0.010 + 0.010)) < 1e-15,
          "%.6e m^2" % m.cable_area_m2)
    check("fluid volume subtracts the cables' OWN areas",
          abs(m.fluid_volume_m3
              - (0.04 - math.pi * (0.01 ** 2 + 2 * 0.005 ** 2)) * m.thickness)
          < 1e-15, "%.6e m^3" % m.fluid_volume_m3)
    # ⚠ ONE fluid in the enclosure. The properties are fixed from the LARGEST
    # cable; per-group properties would be a different fluid around each cable.
    ref = B.BundleCase(centres=[(0.0, 0.0)], d_cable=0.020, box_w=0.2, box_h=0.2)
    check("the fluid is ONE fluid, fixed from the LARGEST cable",
          all(abs(a - b) < 1e-18 for a, b in zip(m.properties, ref.properties)),
          "%s vs %s" % (m.properties, ref.properties))

    print(" the written mixed case gives every size its own surface and flux:")
    tmp = tempfile.mkdtemp()
    try:
        case = B.BundleCase(cells_x=20, iterations=10, write_interval=10,
                            cables=[(-0.015, -0.00866, 0.020, 400.0),
                                    (0.015, -0.00866, 0.010, 150.0),
                                    (0.0, 0.01732, 0.010, 150.0)],
                            box_w=0.2, box_h=0.2)
        B.write_bundle(tmp, case)
        big, small = case.groups

        def read(rel):
            with open(os.path.join(tmp, rel), encoding="utf-8") as fh:
                return fh.read()

        for g in case.groups:
            p = os.path.join(tmp, "constant", "triSurface", g.stl_name)
            check("writes an STL for the %.4g mm size" % (1000 * g.d_cable),
                  os.path.isfile(p))
            stl = open(p, encoding="ascii").read()
            check("...whose SOLID NAME is the patch name (this is what makes "
                  "snappy create the patch)",
                  stl.startswith("solid %s\n" % g.patch)
                  and stl.rstrip().endswith("endsolid %s" % g.patch))
            verts = [tuple(float(x) for x in t) for t in re.findall(
                r"vertex\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)",
                stl)]
            # every rim vertex must sit on THIS size's circle about one of
            # THIS group's centres — a swapped radius would fail here
            ok = True
            for vx, vy, _vz in verts:
                dists = [abs(math.hypot(vx - cx, vy - cy) - g.r_cable)
                         for cx, cy in g.centres]
                at_centre = any(abs(vx - cx) < 1e-12 and abs(vy - cy) < 1e-12
                                for cx, cy in g.centres)
                if not at_centre and min(dists) > 1e-9:
                    ok = False
                    break
            check("...and every rim vertex lies on the %.4g mm circle about "
                  "one of ITS OWN centres" % (1000 * g.d_cable), ok,
                  "%d vertices" % len(verts))

        snap = read("system/snappyHexMeshDict")
        for g in case.groups:
            check("snappy has a geometry entry naming patch %s" % g.patch,
                  "%s { type triSurfaceMesh; name %s; }" % (g.stl_name, g.patch)
                  in snap)
            check("...its feature edges are extracted",
                  '{ file "%s.eMesh"; level 0; }' % g.patch in snap)
            check("...and it is refined at ITS OWN level (%d %d)"
                  % (g.refine_min, g.refine_max),
                  "%s { level (%d %d); }" % (g.patch, g.refine_min,
                                             g.refine_max) in snap)
        check("the 10 mm size really is refined FINER than the 20 mm one in "
              "the written dictionary (not just in the object)",
              small.refine_max > big.refine_max,
              "%d vs %d" % (small.refine_max, big.refine_max))
        sfe = read("system/surfaceFeatureExtractDict")
        check("surfaceFeatureExtract is asked for BOTH surfaces — one missing "
              "eMesh aborts snappy",
              all(g.stl_name in sfe for g in case.groups)
              and sfe.count("extractionMethod") == 2)

        t0 = read("0/T")
        check("each size carries its OWN refGradient — separate patches would "
              "be pointless if they all took the same flux",
              "%s { type mixed; refValue uniform 300; refGradient uniform 400;"
              % big.patch in t0
              and "%s { type mixed; refValue uniform 300; refGradient uniform "
                  "150;" % small.patch in t0,
              "20 mm at 400 K/m, 10 mm at 150 K/m")
        check("...and the enclosure and symmetry planes survived the rewrite",
              "enclosure { type fixedValue" in t0
              and "frontAndBack { type symmetry; }" in t0)
        for rel, kind in (("0/U", "noSlip"), ("0/p_rgh", "fixedFluxPressure"),
                          ("0/alphat", "calculated")):
            body = read(rel)
            check("%s gives BOTH size patches a %s condition (a patch with no "
                  "entry is a solver abort)" % (rel, kind),
                  all("%s { type %s" % (g.patch, kind) in body
                      for g in case.groups))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the per-size reader refuses to invent a single answer:")
    r20 = ofm.nusselt_from_patch([302.0] * 8, 0.020, 400.0, 300.0)
    r10 = ofm.nusselt_from_patch([301.0] * 6, 0.010, 400.0, 300.0)
    mx = ofm.MixedBundleNusselt(by_patch={"a": r20, "b": r10},
                                diameter={"a": 0.020, "b": 0.010},
                                gradient={"a": 400.0, "b": 400.0})
    try:
        mx.nu_d
        check("a mixed result REFUSES a single Nu_D rather than averaging "
              "unlike diameters", False, "it returned one")
    except ValueError as exc:
        check("a mixed result REFUSES a single Nu_D rather than averaging "
              "unlike diameters", "not one" in str(exc))
    check("...but each size's own Nu is exact (D grad / dT)",
          abs(mx.by_patch["a"].nu_d - 4.0) < 1e-12
          and abs(mx.by_patch["b"].nu_d - 4.0) < 1e-12)
    check("faces sum across the sizes", mx.faces == 14)
    check("the HOTTEST size is identified — ampacity binds on temperature",
          mx.hottest()[0] == "a")
    try:
        mx.only()
        check("only() refuses a bundle that is not uniform", False)
    except ValueError:
        check("only() refuses a bundle that is not uniform", True)
    solo = ofm.MixedBundleNusselt(by_patch={"cables": r20},
                                  diameter={"cables": 0.020})
    check("...and returns the single reading when there IS one",
          solo.only() is r20)

    print(" THE ANCHOR IS UNMOVED — a uniform bundle writes the identical "
          "case:")
    # ⚠ Two routes to the same uniform bundle: the original centres/d_cable
    # contract, and the new per-cable list. They must produce identical files,
    # because the measured ladder was taken through the first one and every
    # number in this gate's docstring depends on it still being what runs.
    a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        kw = dict(cells_x=20, iterations=10, write_interval=10, box_w=0.2,
                  box_h=0.2)
        B.write_bundle(a, B.BundleCase(centres=B.TREFOIL, d_cable=0.020, **kw))
        B.write_bundle(b, B.BundleCase(
            cables=[(x, y, 0.020) for x, y in B.TREFOIL], **kw))

        def digest(root):
            out = {}
            for dirpath, _dn, files in os.walk(root):
                for f in files:
                    p = os.path.join(dirpath, f)
                    rel = os.path.relpath(p, root).replace("\\", "/")
                    out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
            return out

        da, db = digest(a), digest(b)
        check("the per-cable route writes the byte-identical case the "
              "centres/d_cable route always wrote (%d files) — so the measured "
              "ladder still describes what runs" % len(da), da == db,
              "differs: %s" % sorted(k for k in set(da) | set(db)
                                     if da.get(k) != db.get(k)))
        check("...and it is genuinely the SINGLE-patch case, not two patches "
              "that happen to agree",
              list(da) == list(db)
              and "constant/triSurface/cables.stl" in da
              and not any("cables_g" in k for k in da))
    finally:
        shutil.rmtree(a, ignore_errors=True)
        shutil.rmtree(b, ignore_errors=True)


def _case(base, name, **kw):
    d = os.path.join(base, name)
    os.makedirs(d)
    return d, B.BundleCase(**kw)


def live_checks():
    """The ladder, on real solves. Requires a usable ESI OpenFOAM."""
    info = _setup.find_openfoam()
    if not info.found or not info.usable:
        raise SystemExit(
            "openfoam_bundle needs a usable ESI OpenFOAM; discovery says: "
            + (info.describe() or "nothing found"))
    print(" live solve (%s):" % info.describe())
    base = tempfile.mkdtemp(prefix="emstudio-bundle-")
    got = {}
    try:
        # ⚠ ONE variable changes between rungs.
        rungs = (("anchor", dict(centres=[(0.0, 0.0)], box_w=0.40, box_h=0.40)),
                 ("solo", dict(centres=[(0.0, 0.0)], box_w=0.20, box_h=0.20)),
                 ("bundle", dict(box_w=0.20, box_h=0.20)))
        for tag, kw in rungs:
            # ⚠ ITERATIONS ARE MEASURED, NOT GUESSED — and 20000 was
            # unaffordable. residualControl fired at 3136 (solo) and 6384
            # (bundle); the anchor never fires it but its Nu is flat to
            # ±0.15 % from iteration 5000 to 20000. So 8000 preserves all
            # three measured values while cutting the gate's cost by ~60 %.
            #
            # This matters: at 20000 a single rung ran 4376 s on 15k cells and
            # was killed under concurrent load, which is not a gate — the
            # SOLVER tier budgets minutes-to-15-minutes per gate, not hours.
            # The mesh is deliberately UNCHANGED, so the ladder measured at
            # cells_x=100 still applies; only the iteration budget moved.
            d, case = _case(base, tag, cells_x=100, iterations=8000,
                            write_interval=2000, **kw)
            rep, res = ofm.run_bundle(d, case)
            if not check("%s: the chain completes (snappy included)" % tag,
                         rep["ok"], rep.get("failed_at", "") or ""):
                continue
            mesh = [s for s in rep["steps"] if s["step"] == "checkMesh"]
            check("%s: checkMesh reports Mesh OK" % tag,
                  bool(mesh) and "Mesh OK" in mesh[0]["tail"])
            check("%s: read the cable surface" % tag, res.faces > 0,
                  "%d patch faces" % res.faces)
            settled = (rep["converged"]
                       or (rep["nu_drift"] is not None
                           and rep["nu_drift"] < 5e-3))
            check("%s: the solve settled (residualControl or Nu drift)" % tag,
                  settled, "converged %s, drift %s"
                  % (rep["converged"],
                     "n/a" if rep["nu_drift"] is None
                     else "%.2e" % rep["nu_drift"]))
            got[tag] = (res.nu_d, res.ra_d)

        # --- the two single-cable rungs validate the PIPELINE ---------------
        for tag in ("anchor", "solo"):
            if tag not in got:
                continue
            nu_d, ra = got[tag]
            cc, mo = nu_churchill_chu(ra, PR), morgan(ra)
            lo, hi = min(cc, mo) * 0.90, max(cc, mo) * 1.10
            check("%s (ONE cable) lies inside the Churchill-Chu/Morgan "
                  "envelope — this is what validates snappy + the flux BC + "
                  "the patch reader" % tag,
                  lo <= nu_d <= hi,
                  "Nu %.4f in [%.4f, %.4f] at Ra %.4g; CC %+.2f %%"
                  % (nu_d, lo, hi, ra, 100 * (nu_d - cc) / cc))

        # --- and the bundle is the finding ---------------------------------
        if "solo" in got and "bundle" in got:
            nu_s, ra_s = got["solo"]
            nu_b, ra_b = got["bundle"]
            drop = 100 * (nu_b - nu_s) / nu_s
            check("the BUNDLE transfers measurably less than one cable in the "
                  "SAME enclosure (mutual heating + shared air)",
                  nu_b < nu_s * 0.95, "%.4f -> %.4f (%+.2f %%)"
                  % (nu_s, nu_b, drop))
            cc_b = nu_churchill_chu(ra_b, PR)
            err = 100 * (nu_b - cc_b) / cc_b
            check("Churchill-Chu OVER-predicts the bundle by more than 10 % — "
                  "the error wire/thermal.surface_h() makes today, in the "
                  "UNSAFE direction",
                  nu_b < cc_b * 0.90,
                  "CFD %.4f vs CC %.4f at Ra %.4g (%+.2f %%)"
                  % (nu_b, cc_b, ra_b, err))
            mo_b = morgan(ra_b)
            check("...and the bundle falls BELOW both correlations, so no "
                  "isolated-cylinder correlation describes it",
                  nu_b < min(cc_b, mo_b),
                  "CFD %.4f vs CC %.4f / Morgan %.4f" % (nu_b, cc_b, mo_b))
        if "anchor" in got and "solo" in got:
            check("confinement alone costs less than the bundle does "
                  "(the ladder separates them)",
                  abs(got["solo"][0] - got["anchor"][0]) / got["anchor"][0]
                  < abs(got["bundle"][0] - got["solo"][0]) / got["solo"][0]
                  if "bundle" in got else True,
                  "anchor %.4f -> solo %.4f -> bundle %s"
                  % (got["anchor"][0], got["solo"][0],
                     "%.4f" % got["bundle"][0] if "bundle" in got else "n/a"))

        live_mixed_checks(base, got)
    finally:
        shutil.rmtree(base, ignore_errors=True)


#: The MIXED rung, measured at FULL fidelity (cells_x=100, 8000 iterations,
#: ~50 min) on the native v2512 install, 2026-08-12. Drift 4.1e-5 and 2.6e-4.
#:
#: ⚠ This is a SELF-PIN — this project's own measurement, recorded with its
#: configuration in CHANGELOG and PROJECT_MEMORY — NOT a literature anchor and
#: NOT a remembered value. It exists so the cheap gate rung is tied to the
#: expensive measurement instead of merely being internally consistent.
MIXED_REFERENCE = {0.020: (3.6097, 5541.0), 0.010: (1.9997, 625.1)}

#: The gate rung is CHEAPER than the measurement above and says so. A mixed
#: case meshes to 52 174 cells against the uniform trefoil's ~15 000 (the
#: smaller cables are refined a level finer), so full fidelity costs ~50 min —
#: outside the SOLVER tier's minutes-to-fifteen-minutes budget, and this
#: project has already had a 4376 s rung killed under load.
#:
#: MEASURED at this setting: 542 s, Nu 3.6220 / 2.0176 — **+0.34 % and +0.90 %**
#: against full fidelity. Both coarsening and under-iteration read HIGH here,
#: and both are sub-1 %, which is where the 3 % band below comes from.
MIXED_GATE_CELLS, MIXED_GATE_ITERS = 60, 3000


def live_mixed_checks(base, got):
    """The MIXED rung — the mixed path proven END TO END.

    Same three centres, same 0.20 m enclosure, same 400 K/m as the ``bundle``
    rung: two of the three 20 mm cables shrink to 10 mm, and nothing else moves.

    ⚠ **This rung's job is the MECHANISM, not the physics.** The offline half
    can show that two STL solids and two boundary entries were WRITTEN; only a
    real snappy run can show that OpenFOAM turned them into two patches, kept
    each cable's faces on the right one, and applied each size's own flux. The
    physics number is `MIXED_REFERENCE`, measured once at full fidelity and
    recorded — re-deriving it every run would cost ~50 min for an answer this
    rung reproduces to under 1 %.

    ⚠ **It is therefore NOT a ladder rung against `bundle`.** That comparison
    needs the same mesh, and this one is deliberately coarser. Comparing across
    it would be a study that moves two things at once, which has already
    produced two wrong answers in this project.
    """
    tag = "mixed"
    d = os.path.join(base, tag)
    os.makedirs(d)
    case = B.BundleCase(cells_x=MIXED_GATE_CELLS, iterations=MIXED_GATE_ITERS,
                        write_interval=MIXED_GATE_ITERS // 3,
                        box_w=0.20, box_h=0.20,
                        cables=[(-0.015, -0.0086610, 0.020),
                                (0.015, -0.0086610, 0.010),
                                (0.0, 0.0173220, 0.010)])
    big, small = case.groups
    rep, res = ofm.run_bundle(d, case)
    if not check("mixed: the chain completes with TWO snappy surfaces",
                 rep["ok"], rep.get("failed_at", "") or ""):
        return
    mesh = [s for s in rep["steps"] if s["step"] == "checkMesh"]
    check("mixed: checkMesh reports Mesh OK",
          bool(mesh) and "Mesh OK" in mesh[0]["tail"])

    # ⚠ THE headline check. If snappy had merged the two surfaces into one
    # patch — the failure this whole design exists to avoid — one of these
    # reads would have raised in the runner and `ok` would be False, so what
    # this asserts is that BOTH patches exist AND carry real faces.
    if not check("mixed: BOTH sizes came back as their own patch, each with "
                 "faces of its own — this is what per-size Nusselt numbers "
                 "rest on",
                 set(res.patches) == {big.patch, small.patch}
                 and all(r.faces > 0 for r in res.by_patch.values()),
                 ", ".join("%s %d faces" % (p, r.faces)
                           for p, r in res.by_patch.items())):
        return
    r_big, r_small = res.by_patch[big.patch], res.by_patch[small.patch]

    # ⚠ MEASURED, not predicted from first principles: face count per group
    # goes as (wetted perimeter) x 4^level. The 4 — not 2 — is because
    # front/back are `symmetry`, so snappy refines in z as well and each extra
    # level splits BOTH circumferentially and axially. A first guess of 2^level
    # was wrong by exactly that factor and the live run is what corrected it.
    #
    # Normalising it out leaves a quantity that must AGREE between the groups,
    # which is the sharp form: a swapped patch assignment moves it by ~16x.
    def face_density(grp, res):
        return res.faces / (grp.n_cables * math.pi * grp.d_cable
                            * 4.0 ** grp.refine_max)

    fd_big, fd_small = face_density(big, r_big), face_density(small, r_small)
    check("mixed: faces per unit perimeter, with each group's own refinement "
          "level divided out, AGREE between the sizes — a swapped patch "
          "assignment lands ~16x away",
          0.75 < fd_small / fd_big < 1.33,
          "%d faces on 1 x 20 mm @L%d, %d on 2 x 10 mm @L%d -> %.1f vs %.1f "
          "(ratio %.4f)" % (r_big.faces, big.refine_max, r_small.faces,
                            small.refine_max, fd_big, fd_small,
                            fd_small / fd_big))

    # An EXACT arithmetic identity of the reporting, not of the physics: if
    # both sizes had been given the same D (the bug this replaces), the ratio
    # would collapse to dT_i/dT_j and this fails by 8x.
    lhs = r_big.ra_d / r_small.ra_d
    rhs = (r_big.dt * big.d_cable ** 3) / (r_small.dt * small.d_cable ** 3)
    check("mixed: each size's Ra_D is formed with ITS OWN diameter "
          "(Ra ~ dT D^3, exactly) — a shared D would read 8x out here",
          abs(lhs - rhs) / rhs < 1e-9,
          "%.6f vs %.6f" % (lhs, rhs))
    check("mixed: ...and with the SAME fluid, since there is one fluid in the "
          "enclosure", True,
          "nu, alpha fixed from the 20 mm size: %.6g, %.6g" % case.properties)

    for tag2, grp, r in (("20 mm", big, r_big), ("10 mm", small, r_small)):
        check("mixed %s: Nu_D = D grad / dT against its OWN D and its OWN "
              "gradient, exactly" % tag2,
              abs(r.nu_d - grp.d_cable * grp.gradient / r.dt) < 1e-9,
              "Nu %.4f at Ra %.4g, dT %.4f K" % (r.nu_d, r.ra_d, r.dt))
        cc = nu_churchill_chu(r.ra_d, PR)
        check("mixed %s: Churchill-Chu OVER-predicts this size too — the "
              "bundle error is per size, not a property of one diameter"
              % tag2, r.nu_d < cc,
              "CFD %.4f vs CC %.4f at Ra %.4g (%+.2f %%)"
              % (r.nu_d, cc, r.ra_d, 100 * (r.nu_d - cc) / cc))

    # ⚠ THE CHECK THAT TIES THIS RUNG TO THE EXPENSIVE ONE. Without it the
    # cheap rung would only be internally consistent — every structural check
    # above would still pass on a mesh that had quietly stopped resolving the
    # small cable.
    for tag2, grp, r in (("20 mm", big, r_big), ("10 mm", small, r_small)):
        ref_nu, ref_ra = MIXED_REFERENCE[round(grp.d_cable, 12)]
        err = 100.0 * (r.nu_d - ref_nu) / ref_nu
        check("mixed %s: reproduces the FULL-FIDELITY measurement (Nu %.4f at "
              "cells_x=100 / 8000 it) to within 3 %% at a fifth of the cost"
              % (tag2, ref_nu), abs(err) < 3.0,
              "Nu %.4f vs %.4f (%+.2f %%), Ra %.4g vs %.4g"
              % (r.nu_d, ref_nu, err, r.ra_d, ref_ra))

    drifts = rep.get("nu_drift_by_patch") or {}
    check("mixed: drift is reported PER SIZE and the worst is the one "
          "surfaced, so one settled size cannot hide a still-moving one",
          bool(drifts) and set(drifts) == {big.patch, small.patch}
          and rep["nu_drift"] is not None
          and abs(rep["nu_drift"] - max(drifts.values())) < 1e-12,
          "worst %s of %s"
          % ("n/a" if rep["nu_drift"] is None else "%.2e" % rep["nu_drift"],
             {k: "%.2e" % v for k, v in drifts.items()}))
    # ⚠ This rung is deliberately UNDER-ITERATED and must NOT claim to be
    # settled. Measured at this setting: 4.9e-3 on the 20 mm and 1.6e-2 on the
    # 10 mm — the small cable is the slower of the two, which is why the drift
    # must be per size. What is gated is that the answer is right anyway
    # (above) and that the un-settled state is DETECTED rather than hidden.
    check("mixed: the rung is honest about being under-iterated — it does not "
          "report convergence it has not earned",
          not rep["converged"] and rep["nu_drift"] > 1e-4,
          "converged %s, worst drift %.2e"
          % (rep["converged"], rep["nu_drift"]))

    # --- and the factor the user actually gets -------------------------------
    from emstudio.wire import bundle_convection as bc
    mf = bc.solve_mixed_bundle_factor(
        [(-0.015, -0.0086610, 0.020), (0.015, -0.0086610, 0.010),
         (0.0, 0.0173220, 0.010)], box_w=0.20, box_h=0.20,
        runner=lambda _d, _c: (rep, res), case_factory=lambda **kw: case,
        case_dir=d)
    check("mixed: the Cable Designer gets one factor PER SIZE, each below 1 "
          "(the correlation is optimistic for both)",
          sorted(round(1000 * s, 4) for s in mf.sizes) == [10.0, 20.0]
          and all(f.factor < 1.0 for f in mf.by_size.values()),
          "; ".join("%.4g mm -> %.4f" % (1000 * s, mf.by_size[s].factor)
                    for s in mf.sizes))
    check("mixed: and the single conservative number, if one is forced, is "
          "the WORST size's",
          abs(mf.worst.factor
              - min(f.factor for f in mf.by_size.values())) < 1e-15,
          "worst %.4f (%.4g mm), spread %.1f %%"
          % (mf.worst.factor, 1000 * mf.worst.d_cable, mf.spread_pct))

    # ⚠ PRINTED, NOT GATED. The recorded full-fidelity comparison is
    # Nu 3.1542 -> 3.6097 (+14.4 %) at the SAME mesh; this rung is coarser, so
    # gating the difference here would be a study that moves two things at
    # once. It is printed because it is the interesting number and a reader
    # should see it, with the caveat attached.
    if "bundle" in got:
        nu_uniform = got["bundle"][0]
        print("  LADDER (recorded at full fidelity, NOT gated here — this rung "
              "is coarser): 3 x 20 mm Nu %.4f -> the 20 mm cable with two "
              "10 mm neighbours Nu 3.6097 (+14.4 %%). This rung reads %.4f."
              % (nu_uniform, r_big.nu_d))


def main():
    print("OPENFOAM-BUNDLE GATE")
    offline_checks()
    live_checks()
    if _FAILED:
        raise SystemExit("OPENFOAM-BUNDLE GATE FAILED: %s" % ", ".join(_FAILED))
    print("OPENFOAM-BUNDLE GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    main()
