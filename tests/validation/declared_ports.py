# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the DOCUMENT decides which faces are wave ports.

Until 2026-08-20 the driven Palace path inferred **two** ports from the longest
bounding-box axis, so every GUI-driven solve was a 2-port even though the engine
underneath — mesher attributes, config, excitation loop, merge, ``.sNp`` writer
— has been N-port end to end since v1.2.0. Nothing was missing except a way for
the document to say *"this face is port 3"*.

It turned out the document could already say it: an ``EMStudio::LumpedPort``
carries ``References`` (a LinkSubList of sub-elements) and a 1-based
``PortNumber``. ``declared_port_boxes`` reads them and returns selection boxes
that ``normalise_port_faces`` already accepts.

**What this gate pins, and why each rule exists:**

1. **Order is ``PortNumber``, not document order.** S11 is reported for
   whichever port ends up first, so a picker that returned faces in creation
   order would silently relabel the user's ports.
2. **Faces only.** An ``Edge`` reference is a lumped / MSL port, not a
   waveguide mouth. Treating one as a wave port would mesh a line as a surface
   and fail a long way from the cause.
3. **Fewer than two usable port faces ⇒ ``None`` ⇒ infer, exactly as before.**
   This is the no-regression rule: every document that worked yesterday
   declares zero or one port face and must keep taking the old path.
4. **An incomplete declaration ⇒ ``None``, never a partial guess.** Two ports
   where only one names a face is a half-finished edit, and solving it as a
   1-port would be a plausible-looking wrong answer.
5. **Each box is inflated by a slab.** A planar face has ZERO thickness along
   its normal, and gmsh's ``Surface In BoundingBox`` selects surfaces lying
   INSIDE the box — a zero-thickness query is a coin toss against floating
   point. The inferred path already slabs for this reason.

⚠ **SCOPE — what this gate does NOT cover.** It stubs FreeCAD's object lookups
(``query.get_ports`` / ``query.resolved_references``) and uses fake bounding boxes,
so it tests the SELECTION LOGIC and nothing about real BREP geometry. The real
geometry path — a picked ``FaceN`` on an actual solid reaching the mesher — is
exercised under ``freecadcmd`` and by the live SOLVER-tier waveguide gates.
Saying so here rather than implying full coverage.

Pure python3, no FreeCAD, no solver.
Pass: exit 0 and 'DECLARED PORTS GATE PASSED'.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


class _BB(object):
    """Just enough of FreeCAD's BoundBox for the selection logic."""

    def __init__(self, xmin, ymin, zmin, xmax, ymax, zmax):
        self.XMin, self.YMin, self.ZMin = xmin, ymin, zmin
        self.XMax, self.YMax, self.ZMax = xmax, ymax, zmax

    @property
    def XLength(self):
        return self.XMax - self.XMin

    @property
    def YLength(self):
        return self.YMax - self.YMin

    @property
    def ZLength(self):
        return self.ZMax - self.ZMin


class _Shape(object):
    def __init__(self, bb):
        self.BoundBox = bb


class _Port(object):
    """A stand-in LumpedPort: a PortNumber and (sub_shape, sub_name) refs."""

    def __init__(self, number, refs):
        self.PortNumber = number
        self._refs = refs


def _run(ports, solid_bb):
    """Call declared_port_boxes with query stubbed to the given ports."""
    from emstudio.objects import query
    from emstudio.solvers.palace import model

    real_get, real_iter = query.get_ports, query.resolved_references
    try:
        query.get_ports = lambda _a: sorted(ports, key=lambda p: p.PortNumber)
        query.resolved_references = lambda p: [
            (None, shp, name) for shp, name in p._refs]
        return model.declared_port_boxes(object(), _Shape(solid_bb))
    finally:
        query.get_ports, query.resolved_references = real_get, real_iter


def _face(xmin, ymin, zmin, xmax, ymax, zmax):
    return _Shape(_BB(xmin, ymin, zmin, xmax, ymax, zmax))


def main():
    # A deliberately ASYMMETRIC 3-port solid: 60 x 20 x 10 mm. Asymmetric
    # because a uniform 2-port cannot fail an ordering check -- the same reason
    # the n_port_smatrix fixture is 3 ports and lopsided.
    solid = _BB(0, 0, 0, 60, 20, 10)
    f_lo = _face(0, 0, 0, 0, 20, 10)         # x = 0   end
    f_hi = _face(60, 0, 0, 60, 20, 10)       # x = 60  end
    f_side = _face(0, 20, 0, 60, 20, 10)     # y = 20  side wall -> port 3

    # --- 1. three declared faces come back in PortNumber order -------------
    boxes = _run([_Port(3, [(f_side, "Face5")]),
                  _Port(1, [(f_lo, "Face1")]),
                  _Port(2, [(f_hi, "Face2")])], solid)
    check("three declared port faces are honoured", boxes is not None
          and len(boxes) == 3, "got %s" % (None if boxes is None else len(boxes)))
    if boxes and len(boxes) == 3:
        # Port 1 is the x=0 end, port 2 the x=60 end, port 3 the y=20 side
        # wall. ⚠ Identify each by a property the OTHER TWO DO NOT SHARE, or
        # the check cannot fail: all three faces span y = 0..20, so asserting
        # on ymax matched every permutation. The distinguishing facts are that
        # the two ends are THIN in x at opposite extremes, while the side wall
        # spans x completely. Proven: reversing the order now fails HERE.
        x_span = boxes[2][3] - boxes[2][0]
        check("ordered by PortNumber, not document order",
              boxes[0][3] < 1.0 and boxes[1][0] > 59.0 and x_span > 50.0,
              "p1 xmax %.1f, p2 xmin %.1f, p3 x-span %.1f"
              % (boxes[0][3], boxes[1][0], x_span))
        # 2 % of the smallest extent (10 mm) = 0.2 mm each way.
        thick = boxes[0][3] - boxes[0][0]
        check("a zero-thickness face is inflated into a slab",
              thick > 0.3, "port 1 box is %.3f mm thick" % thick)
        check("the slab is small next to the solid, not a bulk selection",
              thick < 2.0, "%.3f mm vs a 10 mm minimum extent" % thick)

    # --- 2. the no-regression rules ---------------------------------------
    check("one port face alone still infers (the lumped/MSL shape)",
          _run([_Port(1, [(f_lo, "Face1")])], solid) is None)
    check("no ports at all still infers",
          _run([], solid) is None)
    check("EDGE references are not wave ports — still infers",
          _run([_Port(1, [(f_lo, "Edge1")]),
                _Port(2, [(f_hi, "Edge2")])], solid) is None)
    check("an INCOMPLETE declaration infers rather than guessing a subset",
          _run([_Port(1, [(f_lo, "Face1")]), _Port(2, [])], solid) is None)

    # --- 3. what the mesher will accept ------------------------------------
    boxes = _run([_Port(1, [(f_lo, "Face1")]), _Port(2, [(f_hi, "Face2")])],
                 solid)
    check("two declared faces produce two boxes", boxes and len(boxes) == 2)
    if boxes:
        from emstudio.meshing.gmsh_brep import normalise_port_faces
        spec = normalise_port_faces(boxes, axis=0)
        check("normalise_port_faces accepts them verbatim",
              len(spec) == 2, "%d specs" % len(spec))
        check("every box is a 6-tuple of floats (the explicit spelling)",
              all(len(b) == 6 and all(isinstance(v, float) for v in b)
                  for b in boxes))

    if FAILURES:
        print("DECLARED PORTS GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("DECLARED PORTS GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
