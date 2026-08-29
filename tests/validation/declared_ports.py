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
   order would silently relabel the user's ports. ⚠ The sort itself lives one
   level down, in ``query.get_ports`` — ``declared_port_boxes`` inherits the
   ordering by delegating to it. That is exactly why this gate fakes the
   DOCUMENT and not the query helpers (see SCOPE below): a gate that stubbed
   ``query.get_ports`` with a sorting lambda would be grading its own stub, and
   deleting the real ``sorted(...)`` would leave it green. Measured, 2026-08-29:
   it did.
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

⚠ **SCOPE — what this gate does and does NOT cover.** It fakes the DOCUMENT: an
analysis object whose ``Group`` holds stand-in ``EMStudio::LumpedPort`` objects
carrying real ``References`` tuples, over fake bounding boxes. It patches
NOTHING — the whole production chain runs, ``declared_port_boxes`` ->
``query.get_ports`` (the sort) -> ``query.resolved_references`` (the FaceN
lookup). What it still cannot see is real BREP geometry: every shape here is a
hand-built box, so this tests the SELECTION LOGIC and nothing about OCC. The
real geometry path — a picked ``FaceN`` on an actual solid reaching the mesher
— is exercised under ``freecadcmd`` and by the live SOLVER-tier waveguide
gates. Saying so here rather than implying full coverage.

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


class _ElementShape(object):
    """The ``Shape`` of a linked object: it resolves sub-element names.

    ``query.resolved_references`` reaches a face by calling
    ``link_obj.Shape.getElement("Face3")``, so the fake has to answer that call
    rather than merely carry a shape. A name this dict does not know raises,
    which ``resolved_references`` swallows into ``None`` — that would surface as
    "no usable face" and turn check 1 RED, not as a silent pass.
    """

    def __init__(self, elements):
        self._elements = elements

    def getElement(self, name):
        return self._elements[name]


class _LinkedObject(object):
    """Stand-in for the document object a reference points AT."""

    def __init__(self, elements):
        self.Shape = _ElementShape(elements)


class _Port(object):
    """A stand-in ``EMStudio::LumpedPort``.

    It carries the two things production reads — the ``EMStudioType`` tag that
    ``query.get_members`` filters on, and a ``References`` LinkSubList in the
    real ``[(link_object, [subname, ...]), ...]`` shape — so no query helper has
    to be replaced to make it work.
    """

    EMStudioType = "EMStudio::LumpedPort"

    def __init__(self, number, refs):
        self.PortNumber = number
        self.References = [(_LinkedObject({name: shp}), [name])
                           for shp, name in refs]


class _Analysis(object):
    """The analysis group, holding its members in DOCUMENT (creation) order.

    ⚠ Deliberately NOT sorted. Ordering by ``PortNumber`` is the property under
    test; handing it in pre-sorted is how the old version of this gate ended up
    proving nothing.
    """

    def __init__(self, ports):
        self.Group = list(ports)


def _run(ports, solid_bb):
    """Call declared_port_boxes over a faked document — nothing is patched."""
    from emstudio.solvers.palace import model

    return model.declared_port_boxes(_Analysis(ports), _Shape(solid_bb))


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
    # Document order is 3, 1, 2 -- i.e. NOT port order. Production has to do
    # the sorting; this gate must never do it on production's behalf.
    doc_ports = [_Port(3, [(f_side, "Face5")]),
                 _Port(1, [(f_lo, "Face1")]),
                 _Port(2, [(f_hi, "Face2")])]
    declared = [p.PortNumber for p in doc_ports]
    check("the fixture is scrambled, so the ordering check CAN fail",
          declared != sorted(declared), "document order %s" % (declared,))
    boxes = _run(doc_ports, solid)
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
