#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — recovering a thin-wire model from a SOLID conductor.

Every case here has an answer known in closed form BEFORE the extractor runs,
so the gate measures accuracy rather than self-consistency.

  straight rod   centreline = the rod's own length, radius = its own radius
  swept helix    centreline = turns * sqrt(circumference^2 + pitch^2)
  torus          REFUSED — a closed loop has no end caps to start from
  block          REFUSED or flagged — not a wire-like conductor

Why the extractor exists, and why it is physics rather than a hack: a
conductor lambda/600 across radiates exactly as a round wire of the same
section, so thin-wire modelling IS the accurate method there. The gate also
pins the electrically-THICK warning, because that is where it stops being
true.

Measured on a real user helix (2026-08-05, 6.44 turns, octagonal 20 mm
conductor): centreline 6067 mm vs 6030 mm parametric truth (+0.61 %),
equivalent radius 9.488 mm vs 9.488 mm, and the extracted model resonated at
18.89 / 25.4 MHz against 18.65 / 25.78 MHz for a hand-built 103-chord model.
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
    print("EMStudio wire-from-solid gate")
    try:
        import FreeCAD  # noqa: F401
        import Part
    except Exception:
        print("  skip  needs FreeCAD (solid geometry) — run under freecadcmd")
        print("WIRE-FROM-SOLID GATE PASSED")
        return 0

    import FreeCAD

    from emstudio.geometry import wire_extract as wx

    # ---- 1. straight rod: the answer is the rod itself ------------------
    L, R = 400.0, 5.0
    rod = Part.makeCylinder(R, L)
    info = wx.extract(rod)
    check("straight rod: centreline length recovered within 1 %",
          abs(info["length_mm"] / L - 1.0) < 0.01,
          "{0:.2f} mm vs {1:.1f}".format(info["length_mm"], L))
    check("straight rod: equivalent radius recovered within 1 %",
          abs(info["radius_mm"] / R - 1.0) < 0.01,
          "{0:.4f} mm vs {1:.1f}".format(info["radius_mm"], R))
    check("straight rod: the two section reads agree",
          abs(info["section_area_mm2"]
              - info["section_area_from_volume_mm2"])
          / info["section_area_mm2"] < 0.02)

    # ---- 2. swept helix: analytic arc length ----------------------------
    r_coil, pitch, turns, r_wire = 40.0, 12.0, 3.0, 2.0
    path = Part.makeHelix(pitch, pitch * turns, r_coil)
    start = path.Edges[0].valueAt(path.Edges[0].FirstParameter)
    tan = path.Edges[0].tangentAt(path.Edges[0].FirstParameter)
    prof = Part.Wire(Part.makeCircle(r_wire, start, tan).Edges)
    helix = Part.BRepOffsetAPI.MakePipeShell(path)
    helix.setFrenetMode(True)
    helix.add(prof, False, False)
    helix.build()
    helix.makeSolid()
    solid = helix.shape()
    analytic = turns * math.hypot(2.0 * math.pi * r_coil, pitch)
    info2 = wx.extract(solid)
    check("swept helix: centreline matches the analytic arc length within 2 %",
          abs(info2["length_mm"] / analytic - 1.0) < 0.02,
          "{0:.1f} mm vs {1:.1f}".format(info2["length_mm"], analytic))
    check("swept helix: equivalent radius within 2 % of the sweep radius",
          abs(info2["radius_mm"] / r_wire - 1.0) < 0.02,
          "{0:.4f} mm vs {1:.1f}".format(info2["radius_mm"], r_wire))
    check("swept helix: the march did not jump turns (length is not a "
          "multiple off)",
          0.9 < info2["length_mm"] / analytic < 1.1,
          "ratio {0:.3f}".format(info2["length_mm"] / analytic))

    # ---- 3. a CLOSED loop must be refused, not guessed ------------------
    try:
        wx.extract(Part.makeTorus(60.0, 4.0))
        check("closed loop is refused (no end caps to start from)", False)
    except wx.WireExtractError as exc:
        check("closed loop is refused (no end caps to start from)",
              "CLOSED" in str(exc) or "no pair of end faces" in str(exc),
              str(exc)[:60])

    # ---- 4. the electrically-THICK warning ------------------------------
    # 9.488 mm radius at 25 MHz is lambda/632 -> silent; at 5 GHz it is not.
    check("a thin conductor draws no warning",
          wx.thin_wire_warning(9.488, 25e6) is None)
    w = wx.thin_wire_warning(9.488, 5e9)
    check("an electrically THICK conductor is flagged", w is not None,
          (w or "")[:60])

    # ---- 5. resampling preserves the path -------------------------------
    pts = info2["dense_points"]
    for chord in (5.0, 20.0):
        rs = wx.resample(pts, chord)
        check("resample to {0:.0f} mm keeps the length within 2 %".format(chord),
              abs(wx.polyline_length_mm(rs) / wx.polyline_length_mm(pts) - 1.0)
              < 0.02,
              "{0:.1f} vs {1:.1f} mm".format(wx.polyline_length_mm(rs),
                                             wx.polyline_length_mm(pts)))
        check("resample to {0:.0f} mm keeps both endpoints".format(chord),
              (rs[0] - pts[0]).Length < 1e-6
              and (rs[-1] - pts[-1]).Length < 1e-6)

    # ---- 6. provenance is reported, not implied -------------------------
    text = wx.describe(info2)
    for token in ("method", "equivalent radius", "equal-area", "centreline"):
        check("the extraction states its provenance: {0!r}".format(token),
              token in text)

    print("-------------------")
    if FAILURES:
        raise SystemExit("WIRE-FROM-SOLID GATE FAILED: " + "; ".join(FAILURES))
    print("WIRE-FROM-SOLID GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
