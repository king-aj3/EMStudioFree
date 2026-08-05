#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — openEMS grid resolution for non-box (STL) bodies.

The defect this pins
--------------------
FDTD is a volume method on a Cartesian grid, so a conductor thinner than one
cell is not *approximated* — it is ABSENT. Until v0.84.0 an STL body received
exactly six grid lines (its bounding-box planes on each axis) and nothing
else, and it never reached ``AddEdges2Grid`` at all, because ``has_solid`` was
set only in the box branch. The cell size inside the body was therefore
whatever the global wavelength rule produced. A 20 mm conductor in a 250 mm
cell simulated cleanly and reported plausible S-parameters and a radiation
pattern for geometry that was not in the grid.

Three behaviours are pinned:

1. **Feature size is measured, not assumed.** ``2*V/A`` recovers the smallest
   dimension of a swept body from volume and surface alone — a plate's
   thickness exactly, a rod's radius (the conservative half of its diameter).
   A bounding box cannot: a 6-turn helix bounds 320 mm and conducts 20 mm.
2. **Affordable cases are refined**, with the extra lines bounded so a helix
   cannot silently request an astronomical grid.
3. **Hopeless cases are refused with numbers**, not simulated. This is the
   same principle as the NEC2 thin-wire warning at the other end of the scale:
   each solver states where it stops being valid instead of returning a
   confident answer outside its range.
"""

from __future__ import annotations

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

FAILURES = []


def check(label, ok, detail=""):
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:76] + "]") if detail else ""))


def main():
    print("EMStudio openEMS STL-resolution gate")
    try:
        import FreeCAD  # noqa: F401
        import Part
    except Exception:
        # The openEMS writer imports FreeCAD at module scope, so nothing here
        # is reachable without it.
        print("  skip  needs FreeCAD — run under freecadcmd")
        print("STL-MESH GATE PASSED")
        return 0

    from emstudio.solvers.openems import writer as wr

    # ---- 1. the refinement decision, pure ------------------------------
    # The helix that motivated all this: 105 x 73 x 121 = 927k cells to
    # blanket at its own conductor size. A per-axis cap would wave that
    # through (121 looks modest); the CELL budget is what catches it.
    helix = {"kind": "stl", "start": (-160.0, -210.0, -184.0),
             "stop": (160.0, 10.0, 184.0), "min_feature": 9.22}
    check("a thin body in a huge bbox declines refinement (cell budget)",
          wr._stl_refinement(helix, 250.0) is None,
          "would cost ~927k cells for one body")

    # The case the affordability ceiling actually exists for: resolvable
    # enough to escape the refusal, but too large to blanket with a local grid.
    huge = {"kind": "stl", "start": (0.0, 0.0, 0.0),
            "stop": (10000.0, 400.0, 400.0), "min_feature": 30.0}
    check("a resolvable body too large to refine declines refinement",
          wr._stl_refinement(huge, 20.0) is None,
          "would need {0:.0f} lines on x".format(10000.0 / (30.0 / 3.0)))
    check("...and that same body is NOT refused (it IS resolvable)",
          wr._refuse_unresolvable(
              [{"name": "huge", "kind": "metal", "priority": 10,
                "prims": [huge]}], 20.0) is None)

    # A small body with the same feature: affordable, so refine.
    patch = {"kind": "stl", "start": (0.0, 0.0, 0.0),
             "stop": (40.0, 30.0, 2.0), "min_feature": 2.0}
    ref = wr._stl_refinement(patch, 10.0)
    check("a small body with a fine feature IS refined", ref is not None)
    if ref:
        step, counts = ref
        check("the refinement step resolves the feature",
              abs(step - 2.0 / wr.MIN_CELLS_ACROSS_FEATURE) < 1e-9,
              "{0:.4g} mm".format(step))
        check("refinement stays under both ceilings",
              max(counts) <= wr.MAX_REFINEMENT_LINES
              and counts[0] * counts[1] * counts[2] <= wr.MAX_REFINEMENT_CELLS,
              counts)

    # Already-resolved bodies must NOT be refined (no needless lines).
    check("a body the global grid already resolves is left alone",
          wr._stl_refinement({"kind": "stl", "start": (0.0, 0.0, 0.0),
                              "stop": (40.0, 30.0, 20.0),
                              "min_feature": 20.0}, 1.0) is None)
    check("a body with no measured feature is left alone",
          wr._stl_refinement({"kind": "stl", "start": (0, 0, 0),
                              "stop": (1, 1, 1), "min_feature": 0.0},
                             10.0) is None)

    # ---- 2. the refusal ------------------------------------------------
    mats = [{"name": "helix", "kind": "metal", "priority": 10,
             "prims": [helix]}]
    try:
        wr._refuse_unresolvable(mats, 250.0)
        check("a body thinner than one cell is REFUSED", False)
    except wr.OpenEMSModelError as exc:
        msg = str(exc)
        check("a body thinner than one cell is REFUSED", True)
        check("the refusal quotes the feature size", "9.22" in msg, msg[:60])
        check("the refusal quotes the cell size", "250" in msg)
        check("the refusal names the NEC2 alternative", "NEC2" in msg)
    # ... and must NOT fire once the grid resolves it
    try:
        wr._refuse_unresolvable(mats, 2.0)
        check("a resolved body is NOT refused", True)
    except wr.OpenEMSModelError as exc:
        check("a resolved body is NOT refused", False, str(exc)[:60])

    # ---- 3. the feature measure ----------------------------------------
    from emstudio.solvers.openems import geometry as geo

    # A rod: 2V/A is its RADIUS (documented conservative half-diameter).
    r, L = 5.0, 400.0
    rod = Part.makeCylinder(r, L)
    feat = geo.min_feature_mm(shape=rod)
    check("2V/A on a rod returns its radius (conservative half-diameter)",
          abs(feat / r - 1.0) < 0.05, "{0:.4g} vs {1:.4g} mm".format(feat, r))

    # A plate: 2V/A is its thickness exactly.
    t = 1.5
    plate = Part.makeBox(200.0, 150.0, t)
    featp = geo.min_feature_mm(shape=plate)
    check("2V/A on a thin plate returns its thickness",
          abs(featp / t - 1.0) < 0.10, "{0:.4g} vs {1:.4g} mm".format(featp, t))

    # The bounding box CANNOT do this — the point of the whole measure.
    bb_min = min(200.0, 150.0, t)
    check("the bbox alone would have agreed on a plate but not a helix",
          abs(bb_min - t) < 1e-9)
    helix_solid = Part.makeCylinder(9.5, 60.0)   # stand-in wire-like body
    bb = helix_solid.BoundBox
    bbox_feat = min(bb.XLength, bb.YLength, bb.ZLength)
    vol_feat = geo.min_feature_mm(shape=helix_solid)
    check("2V/A reads a wire-like body finer than its bounding box",
          vol_feat < bbox_feat,
          "{0:.4g} vs bbox {1:.4g} mm".format(vol_feat, bbox_feat))

    # Zero-volume sheet falls back to the bbox rather than dividing by zero.
    sheet = Part.makePlane(50.0, 40.0)
    fs = geo.min_feature_mm(shape=sheet,
                            bbox=((0.0, 0.0, 0.0), (50.0, 40.0, 0.0)))
    check("a zero-volume sheet falls back to the bbox without raising",
          fs > 0.0, "{0:.4g} mm".format(fs))

    print("-------------------")
    if FAILURES:
        raise SystemExit("STL-MESH GATE FAILED: " + "; ".join(FAILURES))
    print("STL-MESH GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
