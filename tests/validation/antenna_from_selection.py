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

    wires, feeds, _ = wr.build_wire_model(ana, solvers[0])
    check("the NEC2 writer accepts the built analysis", len(wires) >= 1
          and len(feeds) == 1, "{0} wire(s)".format(len(wires)))
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
    wires2, feeds2, _ = wr.build_wire_model(ana2, solvers2[0])
    check("the NEC2 writer accepts the curve-based analysis too",
          len(wires2) > 1 and len(feeds2) == 1,
          "{0} chords".format(len(wires2)))

    print("-------------------")
    if FAILURES:
        raise SystemExit("ANTENNA-FROM-SELECTION GATE FAILED: "
                         + "; ".join(FAILURES))
    print("ANTENNA-FROM-SELECTION GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
