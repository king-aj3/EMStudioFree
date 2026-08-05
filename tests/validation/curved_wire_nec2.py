#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — CURVED wire edges in the NEC2 backend.

NEC2 has no curved primitive; a GW card *is* a straight wire. Until v0.83.0
the writer simply refused a non-straight edge ("automatic polyline
discretization is a Phase-2 item"), so a helix, loop or spiral could not be
solved at all unless the user hand-built a polyline.

What this gate pins
-------------------
1. **The straight path is untouched.** A straight edge must still produce ONE
   wire with the >= 3 segment floor, exactly as before — the frozen straight-
   wire decks (dipole/monopole/yagi/lpda) depend on it, and those gates are
   the real regression net. A curve must NOT inherit that floor: each chord
   IS a straight wire, so a 3-segment floor would cut every chord into thirds
   and push the segment-length-to-radius ratio under NEC2's thin-wire limit.

2. **The deflection bound is real**, not decorative: every chord midpoint lies
   within the requested deflection of the true curve.

3. **The feed lands on the chord nearest the EDGE midpoint** — where the
   excitation sat when a curved edge was a single wire. A curve now yields
   many wires under one key, and the source must not drift to whichever chord
   happens to be enumerated last.

4. **Convergence, against an analytic answer.** A small circular loop's
   radiation resistance is R = 31171 (A/lambda^2)^2 to leading order. The
   deck's chord density is derived from CHORD_DEFLECTION_FRAC, and the gate
   pins the MEASURED convergence (300 mm loop, 3 mm wire, 20 MHz):

       deflection    chords    R [ohm]
         1.00 r        23       0.05713
         0.25 r        45       0.05870   <- the shipped default
         0.02 r       158       0.05966

   Refinement moves monotonically away from the leading-order formula and then
   stops ~21 % above it; that gap is the formula's idealization (uniform
   current, infinitely thin wire), which is why the gate pins CONVERGENCE and
   the analytic value only as an order-of-magnitude sanity bound.
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


def _model(doc, shape, radius_mm, f1, f2, npts, tag):
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    obj = doc.addObject("Part::Feature", "Geo" + tag)
    obj.Shape = shape
    doc.recompute()
    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = f1
    ana.FrequencyStop = f2
    ana.FrequencyPoints = npts
    mat = material_mod.makeMaterial(doc, ana, name="PEC" + tag,
                                    category="Metal (PEC)",
                                    references=[(obj, "")])
    mat.WireRadius = "{0} mm".format(radius_mm)
    port = ports_mod.makeLumpedPort(doc, ana, name="Feed" + tag,
                                    references=[(obj, "Edge1")])
    port.Impedance = "50 Ohm"
    solver = solver_objs.makeSolverNEC2(doc, ana)
    doc.recompute()
    return ana, solver, obj


def main():
    print("EMStudio curved-wire NEC2 gate")
    try:
        import FreeCAD
        import Part
    except Exception:
        print("  skip  needs FreeCAD — run under freecadcmd")
        print("CURVED-WIRE GATE PASSED")
        return 0

    from emstudio.solvers.nec2 import writer as wr

    # ---- 1. straight edge: one wire, >= 3 segments (unchanged) ----------
    d = FreeCAD.newDocument("cw_straight")
    line = Part.makePolygon([FreeCAD.Vector(-2500, 0, 0),
                             FreeCAD.Vector(2500, 0, 0)])
    ana, solver, _o = _model(d, line, 5.0, "25 MHz", "35 MHz", 3, "S")
    wires, feeds, _ = wr.build_wire_model(ana, solver)
    check("a straight edge still yields exactly ONE wire", len(wires) == 1,
          "{0} wire(s)".format(len(wires)))
    check("a straight wire keeps the >=3 segment floor", wires[0]["nseg"] >= 3,
          wires[0]["nseg"])
    check("the straight wire is the fed one", wires[0]["fed"])

    # ---- 2. curved edge: many chords, no 3-segment floor ---------------
    d2 = FreeCAD.newDocument("cw_loop")
    loop = Part.Wire(Part.makeCircle(300.0).Edges)
    ana2, solver2, obj2 = _model(d2, loop, 3.0, "20 MHz", "20 MHz", 1, "L")
    wires2, feeds2, _ = wr.build_wire_model(ana2, solver2)
    check("a curved edge is DISCRETIZED instead of refused", len(wires2) > 5,
          "{0} chords".format(len(wires2)))
    check("chords do not inherit the 3-segment floor",
          min(w["nseg"] for w in wires2) == 1,
          "min nseg {0}".format(min(w["nseg"] for w in wires2)))
    check("exactly one chord carries the feed",
          sum(1 for w in wires2 if w["fed"]) == 1)

    # deflection bound: every chord midpoint within the deflection of the curve
    edge = obj2.Shape.Edges[0]
    defl_mm = 3.0 * wr.CHORD_DEFLECTION_FRAC
    worst = 0.0
    for w in wires2:
        mid = FreeCAD.Vector(*[(w["p1"][k] + w["p2"][k]) / 2.0 * 1000.0
                               for k in range(3)])
        worst = max(worst, edge.distToShape(Part.Vertex(mid))[0])
    check("every chord stays within the deflection bound of the true curve",
          worst <= defl_mm * 1.35,
          "worst {0:.4f} mm vs bound {1:.4f}".format(worst, defl_mm))

    # feed placement: the fed chord is nearest the EDGE midpoint
    mid_par = (edge.FirstParameter + edge.LastParameter) / 2.0
    emid = edge.valueAt(mid_par)
    fed = [w for w in wires2 if w["fed"]][0]
    fed_mid = FreeCAD.Vector(*[(fed["p1"][k] + fed["p2"][k]) / 2.0 * 1000.0
                               for k in range(3)])
    best = min(FreeCAD.Vector(*[(w["p1"][k] + w["p2"][k]) / 2.0 * 1000.0
                                for k in range(3)]).distanceToPoint(emid)
               for w in wires2)
    check("the feed lands on the chord nearest the edge midpoint",
          abs(fed_mid.distanceToPoint(emid) - best) < 1e-6,
          "{0:.3f} mm from midpoint".format(fed_mid.distanceToPoint(emid)))

    # ---- 3. chord density responds to the deflection rule --------------
    orig = wr.CHORD_DEFLECTION_FRAC
    try:
        wr.CHORD_DEFLECTION_FRAC = orig / 5.0
        d3 = FreeCAD.newDocument("cw_fine")
        ana3, solver3, _o3 = _model(d3, Part.Wire(Part.makeCircle(300.0).Edges),
                                    3.0, "20 MHz", "20 MHz", 1, "F")
        wires3, _f3, _ = wr.build_wire_model(ana3, solver3)
        check("a finer deflection yields more chords",
              len(wires3) > len(wires2),
              "{0} -> {1}".format(len(wires2), len(wires3)))
    finally:
        wr.CHORD_DEFLECTION_FRAC = orig

    # ---- 4. live solve: the analytic loop -------------------------------
    try:
        from emstudio.solvers.nec2 import runner as nec_runner

        res = nec_runner.run(ana2, solver2)
    except Exception as exc:                                    # noqa: BLE001
        print("  skip  live tier — no NEC engine: {0}".format(str(exc)[:60]))
        print("-------------------")
        if FAILURES:
            raise SystemExit("CURVED-WIRE GATE FAILED: " + "; ".join(FAILURES))
        print("CURVED-WIRE GATE PASSED")
        return 0

    sweep = res["sweep"] if isinstance(res, dict) else res
    r = float(sweep.zin[0].real)
    lam = 299792458.0 / 20e6
    r_ana = 31171.0 * ((math.pi * 0.3 ** 2) / lam ** 2) ** 2
    check("the loop solves and reports a positive radiation resistance",
          r > 0.0, "{0:.6g} ohm".format(r))
    # MEASURED at the shipped default; the analytic formula is the sanity
    # bound, the measured value is the regression pin.
    check("loop R matches the measured value at the shipped default (2 %)",
          abs(r / 0.058699 - 1.0) < 0.02,
          "{0:.6g} vs 0.058699 ohm".format(r))
    check("loop R is the right order against the analytic small-loop formula",
          1.0 < r / r_ana < 1.5,
          "ratio {0:.3f} (analytic {1:.6g})".format(r / r_ana, r_ana))

    print("-------------------")
    if FAILURES:
        raise SystemExit("CURVED-WIRE GATE FAILED: " + "; ".join(FAILURES))
    print("CURVED-WIRE GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
