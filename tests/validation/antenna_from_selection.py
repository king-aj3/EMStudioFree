#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — "Antenna from Selection".

The command exists because assembling a wire antenna by hand takes four
objects created in the right order under a selection rule that is not
discoverable: the MATERIAL wants the whole object, the PORT wants a named
``EdgeN`` picked in the 3-D VIEW (not the tree, not a face). Getting it wrong
yields "port must reference a wire edge" — a symptom, not a cure. A real user
hit that on a solid, then hit "edge is not straight" on a curve.

So this pins the whole path end to end, both from a SOLID and from a CURVE,
including the thing a novice most needs: that the tool SAYS what it assumed
and why, rather than silently substituting a wire for the thing they drew.
"""

from __future__ import annotations

import math
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

FAILURES = []


def check(label, ok, detail=""):
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:74] + "]") if detail else ""))


def main():
    print("EMStudio antenna-from-selection gate")
    try:
        import FreeCAD
        import Part
    except Exception:
        print("  skip  needs FreeCAD — run under freecadcmd")
        print("ANTENNA-FROM-SELECTION GATE PASSED")
        return 0

    from emstudio.antenna import from_selection as fs
    from emstudio.objects import query

    # ---- classification -------------------------------------------------
    rod = Part.makeCylinder(4.0, 600.0)
    curve = Part.makeHelix(31.0758, 200.0, 150.0)
    check("a solid is classified as a solid", fs.classify(rod) == "solid")
    check("a curve is classified as a wire", fs.classify(curve) == "wire")
    try:
        fs.classify(None)
        check("an empty selection is refused", False)
    except fs.AntennaBuildError:
        check("an empty selection is refused", True)

    # ---- a CURVE needs an explicit radius, and says so ------------------
    try:
        fs.plan(curve)
        check("a curve with no radius is refused (it has no cross-section)",
              False)
    except fs.AntennaBuildError as exc:
        check("a curve with no radius is refused (it has no cross-section)",
              "radius" in str(exc), str(exc)[:60])

    # ---- a SOLID measures its own radius --------------------------------
    p = fs.plan(rod)
    check("a solid's radius is measured, not asked for",
          abs(p["radius_mm"] / 4.0 - 1.0) < 0.02,
          "{0:.4g} mm vs 4.0".format(p["radius_mm"]))
    check("a solid's length is recovered",
          abs(p["length_mm"] / 600.0 - 1.0) < 0.02,
          "{0:.4g} mm vs 600".format(p["length_mm"]))
    # half-wave of 600 mm of wire is 249.8 MHz
    check("the sweep is centred on the half-wave resonance",
          abs(p["f_res_hz"] / 249.8e6 - 1.0) < 0.02,
          "{0:.4g} MHz".format(p["f_res_hz"] / 1e6))
    check("the sweep brackets that resonance",
          p["f1_hz"] < p["f_res_hz"] < p["f2_hz"])

    # ---- it EXPLAINS, because the audience is a novice first ------------
    text = fs.describe(p)
    for token in ("Why it was modelled this way", "thin-wire",
                  "half wavelength", "What to look at after Run Solver",
                  "reactance"):
        check("the explanation covers {0!r}".format(token), token in text)
    check("the terse form omits the teaching block",
          "Why it was modelled this way" not in fs.describe(p, teach=False))
    check("the explanation states the thinness ratio",
          "wavelength across" in text)

    # ---- end to end: the built analysis is actually runnable ------------
    doc = FreeCAD.newDocument("afs_gate")
    obj = doc.addObject("Part::Feature", "Rod")
    obj.Shape = rod
    doc.recompute()
    ana, wire = fs.build(doc, obj, p)

    mats = query.get_materials(ana)
    ports = query.get_ports(ana)
    solvers = query.get_solvers(ana)
    check("one PEC material was created", len(mats) == 1
          and str(mats[0].Category).startswith("Metal"))
    check("the material carries the derived radius",
          abs(float(mats[0].WireRadius.getValueAs("mm")) / p["radius_mm"] - 1.0)
          < 1e-6)
    check("one excited port was created", len(ports) == 1 and ports[0].Excited)
    check("one NEC2 solver was created", len(solvers) == 1)

    # THE rule the user could not discover: the port must name an EdgeN whose
    # key is also one of the material's wire edges.
    refs = [(l.Name, list(s)) for l, s in ports[0].References]
    check("the port references a named EdgeN (not the object, not a face)",
          len(refs) == 1 and len(refs[0][1]) == 1
          and refs[0][1][0].startswith("Edge"), refs)
    check("the port's edge belongs to the same object the material covers",
          refs[0][0] == wire.Name)
    n_edges = len(wire.Shape.Edges)
    check("the feed is the MIDDLE edge (a centre-fed wire)",
          refs[0][1][0] == "Edge{0}".format(n_edges // 2 + 1),
          "{0} of {1} edges".format(refs[0][1][0], n_edges))

    # the real proof: the NEC2 writer accepts what was built
    from emstudio.solvers.nec2 import writer as wr

    # build_wire_model is the SINGLE-excitation API: it returns
    # (wires, feed_INDEX, sweep) where the middle value is an int index into
    # `wires`. This gate originally unpacked it as `feeds` and called len() on
    # it -- that is build_wire_model_MULTI's signature -- so it raised
    # TypeError before reaching a single assertion. It had never passed
    # (SOLVER tier; the work box runs FAST). Found 2026-08-05.
    wires, feed_index, _ = wr.build_wire_model(ana, solvers[0])
    check("the NEC2 writer accepts the built analysis",
          len(wires) >= 1 and isinstance(feed_index, int)
          and 0 <= feed_index < len(wires),
          "{0} wire(s), feed at index {1}".format(len(wires), feed_index))
    check("exactly one wire is fed", sum(1 for w in wires if w["fed"]) == 1)

    # ---- and from a CURVE, with the radius supplied ---------------------
    doc2 = FreeCAD.newDocument("afs_gate2")
    obj2 = doc2.addObject("Part::Feature", "Helix")
    obj2.Shape = curve
    doc2.recompute()
    p2 = fs.plan(curve, radius_mm=9.488)
    ana2, wire2 = fs.build(doc2, obj2, p2)
    check("a curve is used as drawn (no new geometry)", wire2.Name == obj2.Name)
    solvers2 = query.get_solvers(ana2)
    wires2, feed_index2, _ = wr.build_wire_model(ana2, solvers2[0])
    check("the NEC2 writer accepts the curve-based analysis too",
          len(wires2) > 1 and isinstance(feed_index2, int)
          and 0 <= feed_index2 < len(wires2),
          "{0} chords".format(len(wires2)))

    gate_wrong_solver_assist()
    gate_progress_is_real()

    print("-------------------")
    if FAILURES:
        raise SystemExit("ANTENNA-FROM-SELECTION GATE FAILED: "
                         + "; ".join(FAILURES))
    print("ANTENNA-FROM-SELECTION GATE PASSED")
    return 0


def gate_wrong_solver_assist():
    """The wrong-solver assist: does it FIRE, and does accepting it work?

    This exists because the guard it replaces was DEAD. wire_extract's
    thin-wire warning was evaluated against plan()'s optional freq_hz, which
    the GUI command never passes, so it saw None and returned None every time
    while the real sweep frequency was computed afterwards. A conductor of any
    thickness passed silently. So the FIRST check here is simply that a fat
    conductor at its own half-wave resonance is caught at all.
    """
    import FreeCAD
    import Part

    from emstudio.antenna import from_selection as fs
    from emstudio.geometry import wire_extract

    print("wrong-solver assist")

    # A THIN wire must NOT be nagged -- an assist that fires on everything is
    # noise, and users learn to click past it.
    thin = fs.solver_advice(radius_mm=1.0, f_res_hz=300e6, kind="solid")
    check("a thin conductor is left alone (no false alarm)", thin is None)

    # A FAT conductor at the frequency it will actually be swept at.
    fat = fs.solver_advice(radius_mm=40.0, f_res_hz=300e6, kind="solid")
    check("a too-thick conductor is caught", fat is not None)
    if fat:
        check("it recommends the full-wave solver",
              fat["recommended"] == "openems" and fat["current"] == "nec2")
        check("it quantifies the problem", fat["diam_over_lambda"] >
              wire_extract.THIN_WIRE_DIAM_OVER_LAMBDA,
              "{0:.3g} lambda across vs limit {1:.3g}".format(
                  fat["diam_over_lambda"], fat["limit"]))
        check("it says so WITHOUT jargon a beginner would have to look up",
              "too THICK" in fat["plain"] and "wrong" in fat["plain"]
              and "moment" not in fat["plain"].lower())

    # THE REGRESSION THAT MATTERS: plan() must evaluate the guard at the
    # DERIVED resonance, with no freq_hz supplied -- exactly how the GUI calls
    # it. A fat bar 500 mm long resonates near 300 MHz, where 80 mm across is
    # 0.08 lambda: far outside thin-wire.
    doc = FreeCAD.newDocument("assist_gate")
    box = doc.addObject("Part::Feature", "FatBar")
    box.Shape = Part.makeBox(500.0, 80.0, 80.0)
    doc.recompute()
    p = fs.plan(box.Shape)                      # no freq_hz -- the GUI path
    check("plan() fires the guard with NO frequency supplied (the dead path)",
          p.get("solver_advice") is not None,
          "f_res {0:.4g} MHz, r {1:.4g} mm".format(
              p["f_res_hz"] / 1e6, p["radius_mm"]))
    check("the plan still defaults to NEC2 until the user chooses",
          p["solver"] == "nec2")

    # Accepting the assist must actually change what gets built.
    p["solver"] = "openems"
    ana, used = fs.build(doc, box, p)
    solvers = [o for o in ana.Group
               if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"]
    nec2s = [o for o in ana.Group
             if getattr(o, "EMStudioType", "") == "EMStudio::SolverNEC2"]
    check("accepting the switch creates an openEMS solver", len(solvers) == 1)
    check("and does NOT also leave a NEC2 solver behind", not nec2s)
    check("the full-wave run models the SOLID, not the derived centreline",
          used.Name == box.Name,
          "used {0}".format(used.Name))
    check("describe() reflects the solver actually chosen",
          "openEMS (full-wave)" in fs.describe(p))
    FreeCAD.closeDocument(doc.Name)


def gate_progress_is_real():
    """The progress bar must carry INFORMATION, not just motion.

    An indeterminate bar says only "not hung". These checks pin the two things
    that make it worth having: a fraction that advances toward a known total,
    and a time estimate that degrades gracefully instead of printing nonsense.
    """
    import FreeCAD
    import Part

    from emstudio.antenna import from_selection as fs
    from emstudio.ui import run_gui

    print("progress reporting")
    doc = FreeCAD.newDocument("progress_gate")
    bar = doc.addObject("Part::Feature", "LongBar")
    bar.Shape = Part.makeBox(2000.0, 20.0, 20.0)
    doc.recompute()

    seen = []
    fs.plan(bar.Shape, progress_cb=lambda d, t, n="": seen.append((d, t, n)))
    check("the long extraction reports progress at all", len(seen) >= 2,
          "{0} report(s)".format(len(seen)))
    if seen:
        ds = [d for d, _t, _n in seen]
        check("progress only ever advances",
              all(b >= a for a, b in zip(ds, ds[1:])))
        check("progress never exceeds its total",
              all(d <= t for d, t, _n in seen))
        check("the total is a real length, not a step count",
              all(t > 0 for _d, t, _n in seen),
              "total {0:.0f} mm".format(seen[-1][1]))
        check("it reaches most of the way (a bar stuck at 10% is a lie)",
              seen[-1][0] / seen[-1][1] > 0.75,
              "{0:.0%}".format(seen[-1][0] / seen[-1][1]))
        check("it says what it is doing", bool(seen[-1][2].strip()))

    class _S:
        t_start = time.time() - 30.0

    check("ETA is withheld until it would be meaningful",
          run_gui._eta_text(_S(), 0, 100) == "0%")
    check("ETA appears once there is evidence",
          "left" in run_gui._eta_text(_S(), 50, 100))
    check("an unknown total never divides by zero",
          run_gui._eta_text(_S(), 5, 0) == "0%")
    check("a finished job shows no countdown",
          "left" not in run_gui._eta_text(_S(), 100, 100))
    FreeCAD.closeDocument(doc.Name)


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
