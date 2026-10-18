# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD-shape → CSXCAD-primitive classification and export.

Two primitive paths per referenced shape:

* **Native box** — axis-aligned solid boxes and axis-aligned planar rectangular faces
  (sheets) become CSXCAD ``AddBox`` primitives. Sheets are boxes with one collapsed
  axis (the openEMS-canonical way to model thin metal, per the official tutorials).
* **STL polyhedron** — everything else is tessellated and exported as STL, loaded in
  the deck via ``AddPolyhedronReader`` (verified native STL support in CSXCAD).

All coordinates stay in FreeCAD's mm; the deck sets the CSXCAD drawing unit to mm.
"""

from __future__ import annotations

import math
import os

_EPS = 1e-6  # mm-scale tolerance for box/sheet detection


def _bbox_tuple(shape):
    bb = shape.BoundBox
    return (bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)


def _is_axis_aligned_box(shape):
    """Solid whose volume fills its bounding box -> axis-aligned box."""
    try:
        if not shape.Solids:
            return False
        bb = shape.BoundBox
        vol_bb = bb.XLength * bb.YLength * bb.ZLength
        if vol_bb <= 0:
            return False
        return abs(shape.Volume - vol_bb) <= 1e-3 * vol_bb
    except Exception:
        return False


def _is_axis_aligned_sheet(shape):
    """Planar rectangular face with an axis-aligned normal -> degenerate box."""
    try:
        faces = shape.Faces
        if len(faces) != 1 or shape.Solids:
            return False
        bb = shape.BoundBox
        dims = [bb.XLength, bb.YLength, bb.ZLength]
        collapsed = [i for i, d in enumerate(dims) if d <= _EPS]
        if len(collapsed) != 1:
            return False
        # area of the face must fill the bbox rectangle (i.e. really a rectangle)
        other = [d for i, d in enumerate(dims) if i != collapsed[0]]
        area_bb = other[0] * other[1]
        return area_bb > 0 and abs(faces[0].Area - area_bb) <= 1e-3 * area_bb
    except Exception:
        return False


def _sheet_normal_axis(shape):
    bb = shape.BoundBox
    dims = [bb.XLength, bb.YLength, bb.ZLength]
    return int(min(range(3), key=lambda i: dims[i]))  # collapsed axis index


#: Linear tessellation deflection as a fraction of the shape's bounding-box
#: diagonal — the only term until v1.14.0. It is still the CEILING: a body
#: that is neither thin nor small against the grid keeps exactly the facets
#: it always had.
_DEFLECTION_OF_DIAG = 0.005

#: Angular deflection (rad) of every tessellation — unchanged since it was
#: introduced; it is what keeps a curved face's facets bounded when the
#: linear term is large.
_ANGULAR_DEFLECTION = 0.35


def stl_deflection_mm(diag_mm, mesh_res_mm=None, feature_mm=None):
    """The linear deflection a body is tessellated at, in mm.

    ``min(diag * 0.005, mesh_res / 4, feature / 2)`` — each term omitted when
    its input is unknown or not positive.

    WHY THE TWO NEW TERMS (v1.14.0). 0.5 % of the diagonal is a fixed
    fraction of the WHOLE body, so on a large body it is no bound at all:
    a 1.2 m disc is allowed 8.5 mm of facet error. ``feature / 2`` keeps the
    facet error under half the body's thinnest dimension, so tessellation
    cannot close a wall or a slot that the grid was refined to resolve;
    ``mesh_res / 4`` keeps it under a quarter of the global cell, so the
    facets are below what the grid can see anywhere. Both only ever make the
    deflection SMALLER, so a shape that is flat (every planar face
    triangulates exactly, whatever the deflection) is unchanged in geometry;
    only curved faces gain facets.

    ⚠⚠ WHERE THEY BIND — MEASURED, after a false claim here was caught by
    the v1.14.0 review. The linear term was never what faceted a small
    curve: the ANGULAR deflection (_ANGULAR_DEFLECTION) is. Under the old
    rule a full circle came out in 36 facets (a chord sag of 0.0038 x its
    radius) at every radius tried, 1.5 mm to 1000 mm, so the forum J-pole's
    18 mm tube (1.2 mm wall, 1451 mm long: linear term 7.26 mm) and an M3
    screw on their own write BYTE-IDENTICAL STLs under both rules — 0.034 mm
    and 0.006 mm of sag. (This docstring used to say that tube "had a 7.3 mm
    deflection — 6x its wall"; the linear term was 7.3 mm, the facets never
    were.) The new terms bind only where that angular sag exceeds them, on
    LARGE-radius curves: at a 5 mm cell a 600 mm-radius disc goes from
    2.28 mm of sag (36 facets) to 0.62 mm (69; cell / 4 = 1.25 mm), and a
    400 mm-radius ring with a 2 mm wall from 1.52 mm (36) to 0.48 mm (64;
    feature / 2 = 0.97 mm). stl_mesh_openems section 11 measures both on
    the STLs the deck writer actually writes. (With a linear term far ABOVE
    the radius OCC goes coarser than 36 — an M3 screw inside a 1.5 m group
    under the old rule got 13 facets, 0.044 mm of sag: still no wall at
    risk.)
    """
    d = max(float(diag_mm), 1.0) * _DEFLECTION_OF_DIAG
    if mesh_res_mm is not None and float(mesh_res_mm) > 0.0:
        d = min(d, float(mesh_res_mm) / 4.0)
    if feature_mm is not None and float(feature_mm) > 0.0:
        d = min(d, float(feature_mm) / 2.0)
    return d


def export_stl(shape, path, mesh_res_mm=None, feature_mm=None):
    """Tessellate a shape and write (binary) STL. Returns the path.

    The deflection is :func:`stl_deflection_mm` of the shape's own diagonal;
    with neither keyword it is the pre-v1.14.0 rule exactly (0.5 % of the
    diagonal), so a caller that passes nothing gets the facets it always got.
    """
    import Mesh  # noqa: F401  (registers the STL writer on some builds)
    import MeshPart

    mesh = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=stl_deflection_mm(shape.BoundBox.DiagonalLength,
                                           mesh_res_mm, feature_mm),
        AngularDeflection=_ANGULAR_DEFLECTION, Relative=False)
    mesh.write(path)
    return path


#: Above this many triangles the STL topology check is skipped (and says
#: so): it is pure Python over every triangle, ~3 s per million, and an
#: imported scan that large is not worth stalling the deck writer on.
_TOPOLOGY_MAX_TRIANGLES = 2000000


def _read_stl_triangles(path):
    """Triangles of an STL file as float32-exact vertex triples, or None.

    ⚠ FLOAT32, ON PURPOSE. A binary STL stores single-precision vertices and
    CSXCAD's reader (vtkSTLReader) merges points that are BIT-identical in
    that precision, so two corners that are distinct in OpenCASCADE's double
    precision can become ONE vertex in openEMS — and a triangle can
    degenerate. Reading the written file back, not the in-memory mesh, is
    the only way to see what openEMS will see.
    """
    import struct

    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + 50 * n:
            out = []
            for k in range(n):
                v = struct.unpack_from("<9f", data, 84 + 50 * k + 12)
                out.append((v[0:3], v[3:6], v[6:9]))
            return out
    # ASCII STL: round through float32 like the binary branch, so both
    # report the same thing for the same geometry.
    try:
        text = data.decode("ascii", "replace")
    except Exception:                                        # noqa: BLE001
        return None
    pts = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("vertex"):
            try:
                xyz = [struct.unpack("<f", struct.pack("<f", float(c)))[0]
                       for c in ln.split()[1:4]]
            except (ValueError, struct.error):
                return None
            pts.append(tuple(xyz))
    if not pts or len(pts) % 3:
        return None
    return [tuple(pts[i:i + 3]) for i in range(0, len(pts), 3)]


def stl_topology(path):
    """What openEMS's polyhedron reader will make of an STL file.

    Returns ``{"triangles", "open", "nonmanifold", "pinched", "duplicate",
    "degenerate", "refused", "worst": [(x, y, z), ...]}`` — open = edges
    used by ONE triangle, nonmanifold = edges used by MORE than two, pinched
    = vertices where the surface meets itself at a point (their triangles
    form more than one fan), duplicate = repeated triangles, refused = a
    LOWER BOUND on the triangles CSXCAD's CGAL builder will drop, ``worst``
    = up to 20 offending places (so a warning can name the part they sit
    on). ``{"skipped": reason}`` when the file cannot be read or is too
    large to check.

    WHY. CSXCAD builds each STL into a CGAL halfedge polyhedron
    (CSPrimPolyhedron.cpp, Polyhedron_Builder): a triangle whose halfedge
    already exists in BOTH orientations is refused with "Trying reverse
    order... failed" and left out, and the inside test is then a RAY-PARITY
    count over the triangles that remain — so every refused triangle is a
    hole that flips inside/outside along a pencil of grid points behind it.
    Measured on the forum J-pole (v1.13 export, one STL per referenced
    group): the Feed group's two clamps and back plate, touching face to
    face, became one surface with 240 edges shared by four triangles and
    78 duplicated triangles, and CGAL refused 458 faces. An open surface
    with NO refused face is read as 2-D instead — never inside at all.
    ⚠ ``refused`` IS A FLOOR, NOT openEMS's COUNT. It simulates the
    builder's halfedge rule only (a directed halfedge may exist once; the
    reversed triangle is tried before giving up). CGAL's test_facet also
    refuses a triangle that would make a non-manifold VERTEX or break a
    border fan (Polyhedron_incremental_builder_3.h, test_facet_indices),
    which this does not replay — so it never over-states. MEASURED against
    openEMS's own "Trying reverse order... failed" lines: equal on the
    forum J-pole's clamps and bar (16 = 16), 8 against 18 on two boxes and a
    plate written as one STL. Any non-zero value, or any pinched vertex, is
    a real defect either way, and the warning says "at least".
    """
    from collections import defaultdict

    tris = _read_stl_triangles(path)
    if tris is None:
        return {"skipped": "unreadable STL"}
    if len(tris) > _TOPOLOGY_MAX_TRIANGLES:
        return {"skipped": "{0:,} triangles is too many to check".format(
            len(tris))}
    index = {}
    pts = []
    faces = []
    for t in tris:
        f = []
        for q in t:
            k = index.get(q)
            if k is None:
                k = index[q] = len(pts)
                pts.append(q)
            f.append(k)
        faces.append(f)
    uses = defaultdict(int)
    seen = defaultdict(int)
    degenerate = 0
    for f in faces:
        if len(set(f)) < 3:
            degenerate += 1
            continue
        seen[tuple(sorted(f))] += 1
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            uses[(a, b) if a < b else (b, a)] += 1
    used = set()
    refused = 0
    for f in faces:
        if len(set(f)) < 3:
            refused += 1
            continue
        fwd = ((f[0], f[1]), (f[1], f[2]), (f[2], f[0]))
        if not any(h in used for h in fwd):
            used.update(fwd)
            continue
        rev = ((f[0], f[2]), (f[2], f[1]), (f[1], f[0]))
        if not any(h in used for h in rev):
            used.update(rev)
            continue
        refused += 1
    # PINCHED VERTICES: around a manifold vertex its triangles form ONE fan
    # (each joined to the next across an edge through the vertex); two
    # solids touching at a point, or a surface meeting itself there, make
    # two or more — which CGAL refuses even when every edge is manifold.
    fans = defaultdict(list)
    for fi, f in enumerate(faces):
        if len(set(f)) == 3:
            for v in f:
                fans[v].append(fi)
    pinched = []
    for v, fl in fans.items():
        if len(fl) < 2:
            continue
        parent = {fi: fi for fi in fl}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        by_other = defaultdict(list)
        for fi in fl:
            for w in faces[fi]:
                if w != v:
                    by_other[w].append(fi)
        for group in by_other.values():
            for fi in group[1:]:
                ra, rb = find(group[0]), find(fi)
                if ra != rb:
                    parent[ra] = rb
        if len({find(fi) for fi in fl}) > 1:
            pinched.append(v)
    bad = [e for e, c in uses.items() if c != 2]
    worst = []
    for a, b in bad[:20]:
        pa, pb = pts[a], pts[b]
        worst.append(tuple(0.5 * (pa[i] + pb[i]) for i in range(3)))
    for v in pinched[:max(0, 20 - len(worst))]:
        worst.append(tuple(pts[v]))
    return {
        "triangles": len(faces),
        "open": sum(1 for c in uses.values() if c == 1),
        "nonmanifold": sum(1 for c in uses.values() if c > 2),
        "pinched": len(pinched),
        "duplicate": sum(c - 1 for c in seen.values() if c > 1),
        "degenerate": degenerate,
        "refused": refused,
        "worst": worst,
    }


def _topology_defects(topo):
    """The defects of a :func:`stl_topology` record that matter, as text, or
    None. Open edges count for EVERY STL, a sheet's too: an open polyhedron
    is never inside anything to openEMS (see :func:`stl_topology`), so an
    open surface in a metal or dielectric material is simply not modelled."""
    if not topo or topo.get("skipped"):
        return None
    parts = []
    if topo.get("open"):
        parts.append("{0} open edge(s)".format(topo["open"]))
    if topo.get("nonmanifold"):
        parts.append("{0} edge(s) shared by more than two triangles".format(
            topo["nonmanifold"]))
    if topo.get("pinched"):
        parts.append("{0} point(s) where the surface touches itself".format(
            topo["pinched"]))
    if topo.get("duplicate"):
        parts.append("{0} duplicated triangle(s)".format(topo["duplicate"]))
    if topo.get("refused"):
        parts.append("at least {0} triangle(s) openEMS will refuse ('Trying "
                     "reverse order... failed')".format(topo["refused"]))
    return ", ".join(parts) if parts else None


#: Re-exported so every existing caller keeps working. The definition
#: LIVES in ``emstudio.geometry.measure`` because it is not an openEMS
#: concept -- the Elmer 3-D mesh-size default needs the same number, and
#: importing it from HERE drags this package's __init__ -> runner ->
#: writer -> objects.analysis -> ``import FreeCAD``, which a FreeCAD-free
#: caller (or gate) cannot afford.
from emstudio.geometry.measure import min_feature_mm  # noqa: F401,E402


#: A solid is a THIN-WALLED HOLLOW candidate only when its 2V/A wall estimate
#: is at most this fraction of the smallest side of its bounding box. Solid
#: bodies all sit below it — a plate reads 1 (2V/A IS its smallest side), a
#: long rod 2 (2V/A is its radius), a cube or a sphere 3 — while a tube reads
#: OD/wall (15 for an 18 mm tube with a 1.2 mm wall). It is only a cheap
#: pre-filter: the ray test in hollow_envelope decides.
_HOLLOW_MIN_RATIO = 4.0

#: Rays cast from the bounding-box centre in the plane across a candidate
#: axis. ALL of them must hit the wall for the body to count as enclosing a
#: bore around that axis. Eight is enough to reject an L-bracket (measured:
#: at most 5 of 8 across any axis) while every closed ring hits all eight.
_HOLLOW_RAYS = 8

#: Surface types whose orientation is ONE direction, and the attribute that
#: carries it (a plane's ``Axis`` is its normal; the rest are their axis of
#: symmetry or of extrusion). A body built only from these has a frame of its
#: own that can be READ, exactly, from its faces — see :func:`_own_frame`.
_FRAME_DIR_ATTR = {
    "Part::GeomPlane": "Axis",
    "Part::GeomCylinder": "Axis",
    "Part::GeomCone": "Axis",
    "Part::GeomToroid": "Axis",
    "Part::GeomSurfaceOfRevolution": "Direction",
    "Part::GeomSurfaceOfExtrusion": "Direction",
}

#: ...and the one that has no orientation at all: a sphere looks the same in
#: every frame, so it neither sets one nor contradicts one.
_FRAME_FREE = ("Part::GeomSphere",)

#: |cos| within this of 0 or 1 counts as perpendicular / parallel. Directions
#: read from an OpenCASCADE surface are exact to ~1e-15 after FreeCAD's own
#: rotate() (measured: a 135-degree tube's cylinder axis and its end normals
#: agree to every printed digit); 1e-7 is far above that and far below any
#: real "nearly aligned" design angle (1e-7 rad is 6e-6 degrees).
_FRAME_TOL = 1e-7

#: A thin-walled body's half surface area (its outer skin, near enough)
#: divided by the side area of the elliptic cylinder of its measured outline
#: — the consistency test that the outline IS the body's cross-section.
#: Genuine bodies sit inside this window: an open circular tube reads
#: 1 - wall/OD (0.75 at the pre-filter's thickest wall, OD = 4 x wall, 0.93
#: for the forum's 18/1.2 mm tube), a rectangular tube ~4/pi, a closed box
#: at most 4/pi x 1.5 = 1.91 (a cube; measured 1.83 for a 50 mm cube with
#: 1 mm walls). A misread outline falls far outside: MEASURED, a 45-degree
#: 10 mm sloped radial read in the global frame (outline 10 x 375 mm) gives
#: 0.07, and an 18 mm tube with a 100 mm flange at one end 0.19 — both
#: shapes whose "outline" is not the tube, and whose fill advice and price
#: would therefore be wrong.
_ENVELOPE_RATIO = (0.5, 2.1)


def _own_frame(solid):
    """``(frame, aligned)`` — the orthonormal frame ``solid`` is built in.

    ``frame`` is three unit vectors (global coordinates), the first two of
    them directions the solid's faces actually carry; ``aligned`` is True
    when that frame is the global one (every vector along x, y or z), so a
    caller need not rotate anything. ``None`` when no frame can be read
    reliably — a face of a type that carries no exact direction (a B-spline,
    an offset surface), or two directions neither parallel nor perpendicular
    (a hexagonal tube, a mitred end): then nothing measured "across the bore"
    can be trusted, and the caller gives no advice at all.

    WHY. ``hollow_envelope`` used to read the axis-aligned BOUNDING BOX, so a
    tube not parallel to x, y or z was mis-measured outright: a 45-degree,
    10 mm sloped radial of a ground-plane antenna read as a CLOSED shell
    with a 374 mm inside, and its "fill it" price came out at MeshResolution
    211 when the filled 10 mm rod needs 404 — a user who followed it would
    be refused again. A tilted 18 mm, 1450 mm tube read a 1 m "bore" that
    "must NOT be filled". Reading the frame from the faces (the cylinders'
    axis, the end caps' normals) measures the tube in its OWN frame instead.
    """
    import FreeCAD

    found = []
    for face in solid.Faces:
        surf = face.Surface
        tid = getattr(surf, "TypeId", "")
        if tid in _FRAME_FREE:
            continue
        attr = _FRAME_DIR_ATTR.get(tid)
        if attr is None:
            return None                 # no exact direction: no frame to trust
        d = FreeCAD.Vector(getattr(surf, attr))
        if d.Length <= 0.0:
            return None
        d.normalize()
        for e in found:
            c = abs(d.dot(e))
            if c >= 1.0 - _FRAME_TOL:
                break                   # parallel to one already found
            if c > _FRAME_TOL:
                return None             # oblique: not one orthonormal frame
        else:
            # Perpendicular to every direction found so far — so at most
            # three ever get here, by construction.
            found.append(d)
    axes = (FreeCAD.Vector(1, 0, 0), FreeCAD.Vector(0, 1, 0),
            FreeCAD.Vector(0, 0, 1))
    frame = list(found) or [FreeCAD.Vector(axes[2])]
    if len(frame) == 1:
        # One direction only (a round tube: its cylinders and end caps all
        # share the axis) — the cross-section is round, so ANY perpendicular
        # completes the frame. The global axis least aligned with it is
        # taken, which for an axis along x, y or z IS a global axis, so an
        # axis-aligned round tube keeps the global frame exactly.
        g = min(axes, key=lambda a: abs(a.dot(frame[0])))
        e = g - frame[0] * g.dot(frame[0])
        e.normalize()
        frame.append(e)
    # The third axis is ALWAYS rebuilt as e1 x e2 (parallel to a third
    # direction found, if any): a right-handed frame makes the change of
    # coordinates a pure rotation — with a left-handed one transformShape
    # would MIRROR the copy (harmless for a box, but a reflection is not
    # what "the same body, seen in its own frame" means).
    e = frame[0].cross(frame[1])
    e.normalize()
    frame = [frame[0], frame[1], e]
    aligned = all(any(abs(abs(e.dot(a)) - 1.0) <= _FRAME_TOL for a in axes)
                  for e in frame)
    return tuple(tuple(float(c) for c in e) for e in frame), aligned


def _frame_matrix(frame):
    """The rotation taking GLOBAL coordinates into ``frame``'s (rows = axes)."""
    import FreeCAD

    (a, b, c) = frame
    return FreeCAD.Matrix(a[0], a[1], a[2], 0.0, b[0], b[1], b[2], 0.0,
                          c[0], c[1], c[2], 0.0, 0.0, 0.0, 0.0, 1.0)


def _in_frame(shape, frame):
    """A COPY of ``shape`` expressed in ``frame`` (``frame`` None: itself).

    A pure rotation, so planes stay planes and cylinders cylinders — the
    bounding box of the copy is then the body's extent along its OWN axes
    (measured: a 135-degree, 10 x 520 mm tube reads exactly 10 x 10 x 520,
    volume and area unchanged to 1e-12).
    """
    if frame is None:
        return shape
    out = shape.copy()
    out.transformShape(_frame_matrix(frame))
    return out


def _envelope_consistent(solid, outline, length):
    """True when ``outline`` x ``length`` can be the body's own envelope —
    see :data:`_ENVELOPE_RATIO` for the window and what falls outside it."""
    a, b = outline
    side = 0.5 * math.pi * (a + b) * float(length)
    if side <= 0.0:
        return False
    r = 0.5 * float(solid.Area) / side
    return _ENVELOPE_RATIO[0] <= r <= _ENVELOPE_RATIO[1]


def hollow_envelope(solid, feature_mm):
    """Describe ``solid`` as a thin wall around a bore, or None.

    Returns ``{"axis": i, "wall_mm": t, "outline_mm": (a, b),
    "length_mm": L, "closed": bool, "frame": F, "box": (lo, hi)}`` —
    ``outline_mm`` is the extent ACROSS the bore axis, ``length_mm`` the
    extent along it, and ``closed`` True when the wall also caps BOTH ends
    of that axis (a closed shell such as a box enclosure, not a tube), so the
    advice can say "solid body", not "solid rod". All of it is measured in
    the body's OWN frame (:func:`_own_frame`): ``frame`` is None when that is
    the global frame, else its three unit vectors, and ``axis`` and ``box``
    (the bounding box, as two corners) are in that frame's coordinates —
    what :func:`bore_occupant` needs to look inside the same bore.

    WHY. 2V/A reads a tube's WALL (1.2 mm on an 18 mm tube), so the openEMS
    resolvability refusal asked a forum user for a 1.2 mm grid across a
    3 m domain — 9.4e9 cells — when the body was electrically just its outer
    skin. A wall estimate far below the outline is not enough to say "hollow",
    though: an L-bracket or a bent strap has a thin wall and a big box too,
    and "fill it" would be absurd advice for them. So the centre of the
    bounding box must lie OUTSIDE the material and rays from it, in the plane
    across some axis, must ALL hit the wall — a ring around a bore. Measured:
    18/1.2 mm tube -> hollow about its long axis (8/8 hits; 6/8 across the
    others, the open ends); solid rod -> centre inside, not hollow; L-bracket
    -> 1 and 5 hits; a closed 50 mm box with 1 mm walls -> hollow.

    ⚠⚠ NEVER WRONG ADVICE, AT THE PRICE OF A MISSED HINT. Until the v1.14.0
    review this measured the GLOBAL bounding box, so any tube not parallel
    to x, y or z was mis-measured (see :func:`_own_frame` for the two cases
    that proved it). Now: no readable frame -> None; and the outline found
    must pass :func:`_envelope_consistent` (a flanged or bent tube, whose
    box is not its cross-section, fails it) -> None. A body the advice
    cannot measure gets no advice; it never gets a wrong one.
    """
    import FreeCAD
    import Part

    try:
        t = float(feature_mm)
        if t <= 0.0:
            return None
        own = _own_frame(solid)
        if own is None:
            return None                 # no frame we can trust: no advice
        frame = None if own[1] else own[0]
        body = _in_frame(solid, frame)
        bb = body.BoundBox
        ext = [bb.XLength, bb.YLength, bb.ZLength]
        if min(ext) < _HOLLOW_MIN_RATIO * t:
            return None
        centre = bb.Center
        tol = max(1e-7, 1e-9 * bb.DiagonalLength)
        if body.isInside(centre, tol, True):
            return None                 # metal at the centre: a solid body
        reach = 2.0 * bb.DiagonalLength

        def _hits(direction):
            end = centre + FreeCAD.Vector(*direction) * reach
            ray = Part.LineSegment(centre, end).toShape()
            return body.distToShape(ray)[0] <= tol

        # The LONG axis first: a tube is hollow about its length, and a closed
        # box (hollow about every axis) is then described along its longest.
        for ax in sorted(range(3), key=lambda i: -ext[i]):
            u, v = [i for i in range(3) if i != ax]
            hits = 0
            for k in range(_HOLLOW_RAYS):
                th = 2.0 * math.pi * k / _HOLLOW_RAYS
                d = [0.0, 0.0, 0.0]
                d[u], d[v] = math.cos(th), math.sin(th)
                if _hits(d):
                    hits += 1
                else:
                    break
            if hits == _HOLLOW_RAYS:
                # Two more rays, ALONG the axis: both blocked means the wall
                # caps both ends — a closed shell, not a tube. A tube's open
                # ends let both escape; a cup (one end capped) is still a tube
                # for the advice, whose bore test is the same either way.
                # Each end's own answer is kept too ("open_ends", low end
                # first): bore_occupant treats an open MOUTH differently.
                along = [0.0, 0.0, 0.0]
                along[ax] = 1.0
                hi_capped = _hits(along)
                lo_capped = _hits([-c for c in along])
                if not _envelope_consistent(body, (ext[u], ext[v]), ext[ax]):
                    return None         # the box is not its cross-section
                return {"axis": ax, "wall_mm": t,
                        "outline_mm": (ext[u], ext[v]), "length_mm": ext[ax],
                        "closed": bool(hi_capped and lo_capped),
                        "open_ends": (not lo_capped, not hi_capped),
                        "frame": frame,
                        "box": ((bb.XMin, bb.YMin, bb.ZMin),
                                (bb.XMax, bb.YMax, bb.ZMax))}
    except Exception:                                        # noqa: BLE001
        return None                     # unknown is "not hollow": no advice
    return None


#: A Mesh::Feature is turned into a Part shell for the bore test only up to
#: this many facets; past it the mesh is not checked, and is then counted as
#: POSSIBLY in the bore (no fill advice) — the conservative side.
_BORE_MESH_MAX_FACETS = 50000

#: The bore's centre line is searched in this many pieces as well as whole:
#: the point of an object nearest a piece is in the bore wherever the object
#: is, so an object that ALSO comes near the line just past the tube's end
#: (a feed bending out of it) cannot hide the part of it that is inside.
_BORE_AXIS_PIECES = 8

#: How deep past an OPEN end, in widths of the bore (its widest inner
#: dimension a), a part must reach before it is "inside" — the tube's MOUTH
#: is not its inside. In a bore below cut-off the field falls from an open
#: end as about exp(-pi z / a) (the slowest-decaying mode), so 1.5 a in it
#: is ~41 dB down: a part that reaches no deeper sits in the fringe, where
#: filling the tube changes nothing it touches. MEASURED: the four 45-degree
#: sloped radials of a ground-plane antenna meet at a hub, and each pokes
#: up to 11 mm into its neighbour's 9 mm bore (10 mm tubes 60 degrees
#: apart: the axes part at s sin 60, the walls at s < 9.5 / 0.866) — read
#: as a "coax" without this, losing the fill advice the radials need. Capped
#: at a quarter of the tube's length, so a SHORT coax (an SMA body, 10 mm
#: long and 6 mm across) is still looked inside along its middle half; a
#: CAPPED end has no mouth, and gets no allowance at all.
_BORE_MOUTH_DEPTH = 1.5


def bore_occupant(solid, hollow, others):
    """The name of the first of ``others`` that lies inside the bore, or None.

    ``hollow`` is :func:`hollow_envelope`'s description of ``solid``;
    ``others`` is a list of ``{"name": str, "geo": Part shape | Mesh}`` or
    ``{"name": str, "segment": (start, stop)}`` (a port's span), every one
    in global coordinates. ``solid`` itself, if listed, is skipped.

    WHY. The fill advice's bore test is an EMPTY-waveguide cut-off (c / 2a),
    and a tube with something inside it is not an empty waveguide: a shield
    around an inner conductor is a COAX, which carries a TEM wave with no
    cut-off at all, and its bore holds the inner conductor, the dielectric
    and the feed port. MEASURED in the v1.14.0 review: a 400 mm coax shield
    (6 mm OD, 0.3 mm wall) around a 1 mm inner conductor, PTFE and a lumped
    port, at 400-600 MHz, was told "model it as a solid rod (fill the bore)"
    — advice that deletes the feed line. So ANY other referenced solid,
    sheet, mesh or port inside the bore (metal or dielectric, connected or
    not) means the inside is part of the model and the tube is not filled.

    HOW. In the bore's own frame, for each piece of its centre line, the
    point of the other object NEAREST it is taken (OpenCASCADE's exact
    distToShape, so an object inside the bore anywhere along it is found,
    however far it also runs out of the tube), and that point is in the bore
    when it lies strictly inside the tube's length — past the mouth of an
    open end (:data:`_BORE_MOUTH_DEPTH`) — and outline, outside the wall,
    and every ray from it across the axis hits the wall: the same ring test
    that found the bore. A point near the line but outside the tube (a
    ground plane under its open end) fails the ring or the length test, so
    a tube merely STANDING on something is not "occupied".
    ⚠ Unknown counts as occupied: an object that cannot be checked (a mesh
    too large to convert, a boolean that throws) returns its name, because
    the cost of a wrong answer here is advice that deletes the feed.
    """
    import FreeCAD
    import Part

    frame = hollow.get("frame")
    lo, hi = hollow["box"]
    ax = int(hollow["axis"])
    u, v = [i for i in range(3) if i != ax]
    try:
        body = _in_frame(solid, frame)
        gbb = solid.BoundBox
        tol = max(1e-7, 1e-9 * gbb.DiagonalLength)
        span = float(hi[ax]) - float(lo[ax])
        # A point within this of either end plane is ON the end, not inside:
        # a ground plane touching the open end must not count as occupying.
        margin = max(10.0 * tol, 1e-6 * span)
        # ...and an OPEN end's mouth is not inside either (see
        # _BORE_MOUTH_DEPTH); a capped end keeps only the margin.
        bore = max(hollow["outline_mm"]) - 2.0 * float(hollow["wall_mm"])
        mouth = min(_BORE_MOUTH_DEPTH * max(bore, 0.0), 0.25 * span)
        open_lo, open_hi = hollow.get("open_ends", (True, True))
        in_lo = float(lo[ax]) + max(margin, mouth if open_lo else 0.0)
        in_hi = float(hi[ax]) - max(margin, mouth if open_hi else 0.0)
        reach = 2.0 * gbb.DiagonalLength
        centre = [0.5 * (float(lo[i]) + float(hi[i])) for i in range(3)]
        a0 = in_lo + margin
        a1 = in_hi - margin
        if a1 <= a0:
            return None
        cuts = [a0 + (a1 - a0) * k / _BORE_AXIS_PIECES
                for k in range(_BORE_AXIS_PIECES + 1)]
        pieces = []
        for p, q in [(a0, a1)] + list(zip(cuts[:-1], cuts[1:])):
            pa, pb = list(centre), list(centre)
            pa[ax], pb[ax] = p, q
            pieces.append(Part.LineSegment(FreeCAD.Vector(*pa),
                                           FreeCAD.Vector(*pb)).toShape())
    except Exception:                                        # noqa: BLE001
        return "a part that could not be checked"

    def _in_bore(pt):
        c = (pt.x, pt.y, pt.z)
        if not (in_lo < c[ax] < in_hi):
            return False
        if not (float(lo[u]) < c[u] < float(hi[u])
                and float(lo[v]) < c[v] < float(hi[v])):
            return False
        if body.isInside(pt, tol, True):
            return False                # in (or on) the wall itself
        for k in range(_HOLLOW_RAYS):
            th = 2.0 * math.pi * k / _HOLLOW_RAYS
            d = [0.0, 0.0, 0.0]
            d[u], d[v] = math.cos(th), math.sin(th)
            ray = Part.LineSegment(
                pt, pt + FreeCAD.Vector(*d) * reach).toShape()
            if body.distToShape(ray)[0] > tol:
                return False            # escapes: outside the ring
        return True

    for o in others:
        geo = o.get("geo")
        if geo is not None and geo is solid:
            continue
        name = o.get("name") or "another part"
        try:
            if "segment" in o:
                a, b = (FreeCAD.Vector(*o["segment"][0]),
                        FreeCAD.Vector(*o["segment"][1]))
                shp = (Part.Vertex(a) if (b - a).Length <= tol
                       else Part.LineSegment(a, b).toShape())
            elif hasattr(geo, "Topology") and hasattr(geo, "CountFacets"):
                if geo.CountFacets > _BORE_MESH_MAX_FACETS:
                    obb = geo.BoundBox
                    if obb.intersect(gbb):
                        return name     # too big to check: assume inside
                    continue
                shp = Part.Shape()
                shp.makeShapeFromMesh(geo.Topology, 1e-6)
            else:
                shp = geo
            if shp is None or shp.isNull() or not shp.BoundBox.intersect(gbb):
                continue
            shp_f = _in_frame(shp, frame)
            for piece in pieces:
                _d, pairs, _info = piece.distToShape(shp_f)
                if any(_in_bore(p_o) for _p, p_o in pairs):
                    return name
        except Exception:                                    # noqa: BLE001
            return name                 # unknown counts as occupied
    return None


#: Surfaces that are RULED along an axis, by FreeCAD type: the face is the
#: same at every coordinate along that axis, so a grid line ACROSS it adds
#: nothing between the face's own ends. A plane qualifies when it CONTAINS
#: the axis (normal perpendicular to it), a cylinder or extrusion when its
#: generator IS the axis. Everything else — cones, spheres, tori, B-splines,
#: inclined planes, a cylinder lying across the axis — changes the section
#: along the axis and is resolved over its whole extent.
_RULED_ALONG = ("Part::GeomPlane", "Part::GeomCylinder",
                "Part::GeomSurfaceOfExtrusion")


def axis_profile(solid, axis):
    """Where along ``axis`` a solid's cross-section changes: (fills, planes).

    ``fills`` is a merged list of (lo, hi) intervals over which the section
    VARIES and must be resolved at the body's own refinement step; ``planes``
    are the sorted coordinates where it only STEPS (a face perpendicular to
    the axis, or an edge lying in such a plane) — a grid line there plus a
    band either side is enough. Between them the solid is an exact extrusion
    along the axis, and needs no fine lines at all. None when the topology
    cannot be read (the caller then resolves the whole extent).

    WHY. Local refinement used to blanket a body's whole bounding box at a
    third of its smallest feature, and refused to (leaving the body
    UNRESOLVED) once that cost more than 400 lines on an axis or 200k cells.
    Every body of a forum J-pole crossed those caps — its 1450.9 mm radiator
    tube alone wanted 3,632 lines along its length to resolve a 1.2 mm wall
    that never changes along that length — so not one of them was refined at
    any MeshResolution, and the only way to resolve its 1 mm hardware was a
    global MeshResolution of 2700. The tube's section changes only at its
    two ends; this says so exactly, from its faces: two cylinders whose axis
    is the tube's (ruled along it) and two annuli perpendicular to it (the
    planes).
    ⛳ Exact, not sampled: a face is ruled along the axis or it is not, by
    type and orientation, so a helix (swept B-spline faces), a cone or a
    sphere is never mistaken for an extrusion. An edge that wanders along the
    axis without being a line parallel to it (a helix, an ellipse, a
    trimmed boundary) is resolved over its extent too.
    """
    try:
        e = [0.0, 0.0, 0.0]
        e[axis] = 1.0
        bb = solid.BoundBox
        tol = max(1e-7, 1e-7 * bb.DiagonalLength)
        lo_hi = ((bb.XMin, bb.XMax), (bb.YMin, bb.YMax), (bb.ZMin, bb.ZMax))
        fills, planes = [], []

        def _rng(b):
            return ((b.XMin, b.XMax), (b.YMin, b.YMax), (b.ZMin, b.ZMax))[axis]

        def _dot(v):
            return abs(v.x * e[0] + v.y * e[1] + v.z * e[2])

        for face in solid.Faces:
            a, b = _rng(face.BoundBox)
            if b - a <= tol:
                planes.append(0.5 * (a + b))
                continue
            surf = face.Surface
            tid = getattr(surf, "TypeId", "")
            ruled = False
            if tid == "Part::GeomPlane":
                ruled = _dot(surf.Axis) <= 1e-9          # contains the axis
            elif tid == "Part::GeomCylinder":
                ruled = _dot(surf.Axis) >= 1.0 - 1e-9    # generator = axis
            elif tid == "Part::GeomSurfaceOfExtrusion":
                ruled = _dot(surf.Direction) >= 1.0 - 1e-9
            if not ruled:
                fills.append((a, b))
        for edge in solid.Edges:
            a, b = _rng(edge.BoundBox)
            if b - a <= tol:
                planes.append(0.5 * (a + b))
                continue
            curve = getattr(edge, "Curve", None)
            if (getattr(curve, "TypeId", "") == "Part::GeomLine"
                    and _dot(curve.Direction) >= 1.0 - 1e-9):
                continue                    # a generator: nothing changes
            fills.append((a, b))
        # The body's own ends are planes whatever the faces say (a fill that
        # reaches an end already covers it).
        planes.extend(lo_hi[axis])
    except Exception:                                        # noqa: BLE001
        return None
    fills.sort()
    merged = []
    for a, b in fills:
        if merged and a <= merged[-1][1] + tol:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out_planes = []
    for c in sorted(planes):
        if not out_planes or c - out_planes[-1] > tol:
            out_planes.append(c)
    return merged, out_planes


def _sources(label, shape, start, stop, feature):
    """Per-SOLID feature sizes of one primitive, each with its label.

    The primitive's own ``min_feature`` (2V/A of the whole exported shape)
    still sizes local refinement, so decks stay byte-identical; these are
    what the resolvability refusal judges and NAMES. A multi-solid body's
    2V/A is a surface-weighted AVERAGE of its solids' — a 0.8 mm part hides
    inside it — and a later stage that fuses a material's solids into one
    STL would lose which object was thin altogether. Measured on a forum
    model: the 'Mast' group read 0.9475 mm as a whole, its 'junction' part
    0.827 mm.
    """
    try:
        solids = list(shape.Solids) if shape is not None else []
    except Exception:                                        # noqa: BLE001
        solids = []
    if not solids:
        return [{"label": label, "object": label, "min_feature": feature,
                 "start": start, "stop": stop}]
    out = []
    for i, solid in enumerate(solids):
        s_start, s_stop = _bbox_tuple(solid)
        out.append({
            "label": label if len(solids) == 1 else
            "{0} (solid {1} of {2})".format(label, i + 1, len(solids)),
            "object": label,            # what the user referenced, for lists
            "min_feature": min_feature_mm(shape=solid, bbox=(s_start, s_stop)),
            "start": s_start, "stop": s_stop,
            # kept for the hollow test, which only runs if this body is refused
            "solid": solid,
        })
    return out


def _emit(notes, level, text):
    """Collect a model note, or — with no collector — say it on the console.

    "WARNING"/"NOTE" are the prefixes the solver log and the deck use; with
    no list given (a caller outside write_deck) the message still reaches
    FreeCAD's Report view, so nothing is ever skipped in silence.
    """
    msg = "EMStudio: {0} - {1}".format(
        "WARNING" if level == "warning" else "NOTE", text)
    if notes is not None:
        notes.append(msg)
        return
    try:
        import FreeCAD
        (FreeCAD.Console.PrintWarning if level == "warning"
         else FreeCAD.Console.PrintMessage)(msg + "\n")
    except Exception:                                        # noqa: BLE001
        pass


#: Wall-clock budget (s) for fusing the touching solids of ONE material.
#: OpenCASCADE booleans are milliseconds on plain parts (the whole forum
#: J-pole, 21 solids, fuses in 1.4 s) but can take minutes on threaded
#: Fasteners hardware, and a fuse already running cannot be interrupted, so
#: this bounds the START of each cluster's fuse: past it, the remaining
#: clusters are exported part by part — still closed solids each — and a
#: NOTE says so. It is not a correctness limit, only a patience one.
_FUSE_BUDGET_S = 30.0


def _touch_clusters(items, tol):
    """Indices of ``items`` (each with "start"/"stop") grouped so that
    bounding boxes which touch or overlap share a group, in first-index
    order. Only solids that can share a face need fusing: one alone already
    tessellates to a closed surface of its own, and fusing parts that are
    nowhere near each other would only spend boolean time on nothing."""
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        si, ti = items[i]["start"], items[i]["stop"]
        for j in range(i + 1, n):
            sj, tj = items[j]["start"], items[j]["stop"]
            if all(si[k] <= tj[k] + tol and sj[k] <= ti[k] + tol
                   for k in range(3)):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [groups[k] for k in sorted(groups)]


def _fuse(members, tol):
    """Fuse 2+ member solids: (result solids, [member indices per result]),
    or (None, why) when the fuse cannot be trusted.

    ⚠ Every check is a failure seen or feared, and each falls back to
    exporting the parts one by one rather than shipping a doubtful solid:
      * an exception or an invalid result (OpenCASCADE's fuse is not total);
      * a volume outside [largest part, sum of parts] — a fuse that lost or
        doubled material is worse than no fuse;
      * a part that maps to no result solid or to two — its name could no
        longer be given to the solid that carries it, which the thin-body
        refusal and the defect warning both need.
    """
    solids = [m["solid"] for m in members]
    try:
        fused = solids[0].multiFuse(solids[1:])
        try:
            # Merges the coplanar faces the fuse leaves where parts met
            # face to face; cosmetic for openEMS, but it halves the facets
            # along such seams. Optional: a failure keeps the plain fuse.
            fused = fused.removeSplitter()
        except Exception:                                    # noqa: BLE001
            pass
        if not fused.isValid():
            return None, "OpenCASCADE returned an invalid shape"
        out = list(fused.Solids)
        if not out:
            return None, "the fuse returned no solid"
        vols = [float(s.Volume) for s in solids]
        vol = sum(float(r.Volume) for r in out)
        slack = 1e-6 * sum(vols) + 1e-9
        if vol > sum(vols) + slack or vol < max(vols) - slack:
            return None, ("the fused volume {0:.6g} mm^3 is outside the "
                          "parts' own [{1:.6g}, {2:.6g}]".format(
                              vol, max(vols), sum(vols)))
        owner = []
        for m in members:
            pts = [v.Point for v in m["solid"].Vertexes[:1]] or [
                m["solid"].BoundBox.Center]
            hits = [k for k, r in enumerate(out)
                    if r.isInside(pts[0], tol, True)]
            if len(hits) != 1:
                return None, ("part '{0}' could not be traced into the "
                              "fused solid".format(m["label"]))
            owner.append(hits[0])
    except Exception as exc:                                 # noqa: BLE001
        return None, "OpenCASCADE could not fuse them ({0})".format(
            str(exc).strip() or type(exc).__name__)
    groups = [[i for i, o in enumerate(owner) if o == k]
              for k in range(len(out))]
    keep = [(out[k], g) for k, g in enumerate(groups) if g]
    return [s for s, _g in keep], [g for _s, g in keep]


def _names(members, limit=3):
    """'A', 'B' and 'C' (and N more) — for a note about several parts."""
    labels = ["'{0}'".format(m["label"]) for m in members]
    if len(labels) <= limit:
        return ", ".join(labels)
    return "{0} and {1} more".format(", ".join(labels[:limit]),
                                     len(labels) - limit)


def _near(members, topo, tol):
    """The members whose bounding box holds one of the defect points ``topo``
    reports — the parts a defect warning should name. All of them when none
    does (a defect on a fused seam can sit between two boxes' faces)."""
    hit = []
    for m in members:
        s, t = m["start"], m["stop"]
        for q in topo.get("worst") or ():
            if all(s[k] - tol <= q[k] <= t[k] + tol for k in range(3)):
                hit.append(m)
                break
    return hit or list(members)


def _score(topo):
    """Badness of an STL for openEMS: refused triangles first (they are the
    holes in the ray-parity fill), then the rest of the defect count."""
    if not topo or topo.get("skipped"):
        return (0, 0)
    return (topo.get("refused", 0),
            topo.get("open", 0) + topo.get("nonmanifold", 0)
            + topo.get("pinched", 0) + topo.get("duplicate", 0)
            + topo.get("degenerate", 0))


def _mesh_prim(rec, path):
    """The primitive of a Mesh::Feature leaf (its triangles pass verbatim).

    Shared by the export below and the no-export count (``export=False``),
    so the grid the estimate prices is built from the same records.
    """
    mesh, label = rec["mesh"], rec["label"]
    bb = mesh.BoundBox
    start = (bb.XMin, bb.YMin, bb.ZMin)
    stop = (bb.XMax, bb.YMax, bb.ZMax)
    feat = min_feature_mm(mesh=mesh, bbox=(start, stop))
    return {"kind": "stl", "path": path, "start": start, "stop": stop,
            "min_feature": feat, "label": label,
            "sources": _sources(label, None, start, stop, feat), "mesh": mesh}


def _shell_prim(rec, path):
    """The primitive of a sheet / shell leaf (one STL of the whole shape)."""
    shape, label = rec["shape"], rec["label"]
    start, stop = _bbox_tuple(shape)
    feat = min_feature_mm(shape=shape, bbox=(start, stop))
    return {"kind": "stl", "path": path, "start": start, "stop": stop,
            "min_feature": feat, "label": label,
            "sources": _sources(label, shape, start, stop, feat),
            "shape": shape}


def classify_shapes(material_obj, workdir, name_prefix, notes=None,
                    mesh_res_mm=None, export=True):
    """Classify every referenced shape of a material.

    Returns a list of primitive dicts:
      {"kind": "box",  "start": (x,y,z), "stop": (x,y,z), "sheet_axis": int|None}
      {"kind": "stl",  "path": str,      "start": (...),  "stop": (...)}
    each also carrying ``"label"`` (the referenced object, e.g. "Feed > Mount"),
    ``"sources"`` (per-solid feature sizes, see :func:`_sources`) and
    ``"shape"`` / ``"mesh"`` (the global geometry, for the overlap check).
    An STL that FUSES several parts also carries ``"parts"`` (one record per
    source part: label, bbox, solid), so a message about it can still name
    the part it means.

    References are resolved through ``query.reference_leaves``: a part picked
    through a group is honoured, a whole group is exported part by part, each
    part ONCE, and a reference that reaches nothing is reported in ``notes``
    (a list of "EMStudio: WARNING - ..." / "EMStudio: NOTE - ..." strings;
    with None they go straight to FreeCAD's Report view). Until v1.14.0 such
    a reference — and a whole-object reference to something with no shape —
    was skipped silently.

    ⚠⚠ WATERTIGHT EXPORT (v1.14.0). Solids of one material that TOUCH are
    fused (multiFuse + removeSplitter) and each resulting solid is written as
    one STL; a solid that touches nothing is written on its own. Until then
    each referenced object was one STL however many solids it held, and
    solids touching face to face inside it made coincident, duplicated
    triangles — the forum J-pole's Feed group (two clamps and a back plate)
    came out with 240 edges shared by four triangles and 78 duplicated
    triangles, CGAL refused 458 of them, and openEMS then filled the body by
    ray parity through the holes. Measured on that model: fused, its 21 PEC
    solids are one valid solid in 1.4 s. Every written STL is then checked
    as openEMS will read it (:func:`stl_topology`); a fuse whose STL is WORSE
    than its parts' own is undone, and any defect that remains is a WARNING
    naming the parts it sits on (warn only in v1.14.0 — the model still
    runs, as it did). ⚠ Never "repair" by deleting faces: Mesh's
    removeNonManifolds leaves an OPEN shell, which CSXCAD reads as a 2-D
    surface that is never inside — the body vanishes.

    ``mesh_res_mm`` (the global FDTD cell, when the caller knows it) caps the
    tessellation deflection at a quarter cell, see :func:`stl_deflection_mm`.

    ``export=False`` (the pre-solve estimate, writer.grid_estimate): the
    same classification, but nothing is tessellated, fused, checked or
    written — each solid comes back as its own STL-kind primitive with its
    own source, ``"path"`` None. The refinement plan and its grid count are
    judged per SOURCE part, and fusing never changes a source (a fused STL
    carries its parts as its sources), so the refined grid counted from
    these is exactly the one write_deck counts (preflight_live_openems
    checks the two are equal) — without minutes of tessellation in front of
    a dialog that only asks "how long?".
    """
    import time

    from emstudio.objects import query

    prims = []
    stl_count = [0]
    mat_label = str(getattr(material_obj, "Label", "") or "material")
    leaves, issues = query.reference_leaves(material_obj)
    for level, text in issues:
        _emit(notes, level, "material '{0}': {1}".format(mat_label, text))

    def _next_path():
        stl_count[0] += 1
        return os.path.join(workdir, "{0}_{1}.stl".format(name_prefix,
                                                          stl_count[0]))

    def _warn_defects(path, members):
        topo = stl_topology(path)
        if topo.get("skipped"):
            # Never a silent pass: say the check did not run.
            _emit(notes, "note", (
                "material '{0}': the STL for {1} was not checked for the "
                "defects openEMS's reader refuses ({2})").format(
                    mat_label, _names(members) if members else "a body",
                    topo["skipped"]))
            return topo
        why = _topology_defects(topo)
        if why:
            # 1 um: an STL vertex is float32, so a defect ON a part's face
            # can sit a few float32 ulps outside that part's double bbox.
            bb_tol = 1e-3
            near = _near(members, topo, bb_tol) if members else []
            where = topo["worst"][0] if topo.get("worst") else None
            only_open = topo.get("open") and not (
                topo.get("nonmanifold") or topo.get("pinched")
                or topo.get("duplicate") or topo.get("refused"))
            if not only_open:
                hint = ("openEMS's polyhedron reader drops the triangles it "
                        "cannot place and decides inside/outside by counting "
                        "crossings through what is left, so grid cells near "
                        "there can be filled wrongly. This is usually two "
                        "faces of the part(s) touching along a line or at a "
                        "point (a clamp closed on itself, a tube end resting "
                        "on another part's edge): open a small gap there, or "
                        "make the parts overlap.")
            else:
                # ⚠⚠ Only open edges: with nothing refused CSXCAD marks an
                # open polyhedron 2-D (CSPrimPolyhedron::BuildTree) and its
                # IsInside is then ALWAYS false, while openEMS assigns PEC or
                # a material only where IsInside is true (Operator::
                # CalcPEC_Range, GetPropertyByCoordPriority) — so the body is
                # not in the grid at all. Until v1.14.0 a tilted sheet drawn
                # as a face, or an imported STL with one hole, vanished from
                # the model in silence.
                hint = ("The surface is not closed, and openEMS counts no "
                        "grid point as inside an open surface, so this body "
                        "is NOT in the model at all. Close its holes "
                        "(FreeCAD Mesh: Analyze > Evaluate and repair) or "
                        "export it from a solid; a flat sheet is modelled "
                        "natively only when it is axis-aligned.")
            _emit(notes, "warning", (
                "material '{m}': the STL openEMS reads for {who} has {why}"
                "{at}. {hint}").format(
                    m=mat_label,
                    who=_names(near) if near else "this body",
                    why=why, hint=hint,
                    at=(" (e.g. near x {0:.4g}, y {1:.4g}, z {2:.4g} mm)"
                        .format(*where) if where else "")))
        return topo

    # Leaves in reference order; a solid leaf becomes "members" that may be
    # fused across leaves, and each fused solid takes the place (and the STL
    # number) of its first member, so a model with nothing to fuse writes
    # exactly the files, in exactly the order, it always did.
    slots = []
    members = []
    for rec in leaves:
        shape, mesh, label = rec["shape"], rec["mesh"], rec["label"]
        if shape is None:
            if mesh is not None:
                slots.append(("mesh", rec))
            continue
        start, stop = _bbox_tuple(shape)
        if _is_axis_aligned_box(shape):
            feat = min_feature_mm(bbox=(start, stop))
            slots.append(("prim", {"kind": "box", "start": start, "stop": stop,
                                   "sheet_axis": None,
                                   "min_feature": feat, "label": label,
                                   "sources": _sources(label, None, start,
                                                       stop, feat),
                                   "shape": shape}))
            continue
        if _is_axis_aligned_sheet(shape):
            feat = min_feature_mm(bbox=(start, stop))
            slots.append(("prim", {"kind": "box", "start": start, "stop": stop,
                                   "sheet_axis": _sheet_normal_axis(shape),
                                   "min_feature": feat, "label": label,
                                   "sources": _sources(label, None, start,
                                                       stop, feat),
                                   "shape": shape}))
            continue
        # (Bare edges never get here any more: reference_leaves reports a
        # wire-only reference as reaching no geometry. Before v1.14.0 an
        # 'EdgeN' pick was skipped here in silence, and a whole sketch was
        # tessellated into an STL with no facets at all.)
        try:
            solids = list(shape.Solids)
            in_solids = sum(len(s.Faces) for s in solids)
            loose = in_solids < len(shape.Faces)
        except Exception:                                    # noqa: BLE001
            solids, loose = [], True
        if not solids or loose:
            # A sheet or shell the user drew (or solids mixed with loose
            # faces): one STL of the whole shape, as before — fusing is for
            # solids, and an open surface is what a sheet IS to CSXCAD.
            slots.append(("shell", rec))
            continue
        feat_leaf = min_feature_mm(shape=shape, bbox=(start, stop))
        for src in _sources(label, shape, start, stop, feat_leaf):
            src["slot"] = len(slots)
            src["leaf_feature"] = feat_leaf
            members.append(src)
        slots.append(("solids", len(members)))

    if not export:
        # COUNT ONLY (see the docstring): every slot as the primitive the
        # export below would make of it, minus the files — and every solid
        # as its own primitive, since a fuse changes no source.
        for si, (kind, item) in enumerate(slots):
            if kind == "prim":
                prims.append(item)
            elif kind == "mesh":
                prims.append(_mesh_prim(item, None))
            elif kind == "shell":
                prims.append(_shell_prim(item, None))
            else:
                prims.extend(
                    {"kind": "stl", "path": None, "start": m["start"],
                     "stop": m["stop"], "min_feature": m["min_feature"],
                     "label": m["label"], "sources": [m],
                     "shape": m["solid"]}
                    for m in members if m["slot"] == si)
        return prims

    # ---- fuse touching solids, cluster by cluster, within the budget ----
    # 1e-6 mm: the plane tolerance the deck's _snap and the box/sheet tests
    # use — two parts closer than that touch (and may be fused), and a
    # part's vertex within it of a fused solid lies on it.
    tol = 1e-6
    groups = []                   # (member indices, solid or None, fused?)
    t_end = time.monotonic() + _FUSE_BUDGET_S
    for cl in _touch_clusters(members, tol):
        if len(cl) == 1:
            groups.append((cl, members[cl[0]]["solid"], False))
            continue
        if time.monotonic() > t_end:
            _emit(notes, "note", (
                "material '{0}': fusing its touching parts took longer than "
                "{1:g} s, so {2} are exported part by part. Each is still a "
                "closed solid and openEMS fills them correctly; only the "
                "faces where they touch stay in the model.").format(
                    mat_label, _FUSE_BUDGET_S,
                    _names([members[i] for i in cl])))
            groups.extend(([i], members[i]["solid"], False) for i in cl)
            continue
        res, how = _fuse([members[i] for i in cl], tol)
        if res is None:
            _emit(notes, "note", (
                "material '{0}': the touching parts {1} could not be fused "
                "into one solid ({2}); they are exported part by part. Each "
                "is still a closed solid and openEMS fills them correctly; "
                "only the faces where they touch stay in the model.").format(
                    mat_label, _names([members[i] for i in cl]), how))
            groups.extend(([i], members[i]["solid"], False) for i in cl)
            continue
        for solid, owned in zip(res, how):
            idx = [cl[k] for k in owned]
            groups.append((idx, solid, len(idx) > 1))
    groups.sort(key=lambda g: min(g[0]))

    def _stl_prim(idx, solid, path):
        mem = [members[i] for i in idx]
        lo = tuple(min(m["start"][k] for m in mem) for k in range(3))
        hi = tuple(max(m["stop"][k] for m in mem) for k in range(3))
        if len(mem) == 1:
            # One part: exactly the primitive this path always produced
            # (its own 2V/A sizes refinement, its leaf's label names it).
            m = mem[0]
            same_leaf = [x for x in members if x["slot"] == m["slot"]]
            label = m["object"]
            feat = (m["leaf_feature"] if len(same_leaf) == 1
                    else m["min_feature"])
            if len(same_leaf) > 1:
                label = m["label"]
            return {"kind": "stl", "path": path, "start": lo, "stop": hi,
                    "min_feature": feat, "label": label,
                    "sources": [m], "shape": solid}
        whole = sorted({m["slot"] for m in mem})
        if len(whole) == 1 and len(mem) == sum(
                1 for x in members if x["slot"] == whole[0]):
            label = mem[0]["object"]        # one object's own solids, fused
        else:
            label = "{0} (fused with {1} touching part{2})".format(
                mem[0]["label"], len(mem) - 1, "" if len(mem) == 2 else "s")
        return {"kind": "stl", "path": path, "start": lo, "stop": hi,
                "min_feature": min_feature_mm(shape=solid, bbox=(lo, hi)),
                "label": label, "sources": mem, "shape": solid,
                "parts": mem}

    def _write(solid, mem):
        feat = min(m["min_feature"] for m in mem if m["min_feature"] > 0) \
            if any(m["min_feature"] > 0 for m in mem) else None
        path = _next_path()
        export_stl(solid, path, mesh_res_mm=mesh_res_mm, feature_mm=feat)
        return path

    emitted = set()
    for si, (kind, item) in enumerate(slots):
        if kind == "prim":
            prims.append(item)
            continue
        if kind == "mesh":
            # Mesh::Feature (e.g. an imported STL): pass its triangles through
            # verbatim — CSXCAD reads STL natively, no solid conversion needed.
            # (reference_leaves only hands over a mesh WITH facets.)
            path = _next_path()
            item["mesh"].write(path)
            prim = _mesh_prim(item, path)
            _warn_defects(path, [{"label": prim["label"],
                                  "start": prim["start"],
                                  "stop": prim["stop"]}])
            prims.append(prim)
            continue
        if kind == "shell":
            path = _next_path()
            prim = _shell_prim(item, path)
            export_stl(item["shape"], path, mesh_res_mm=mesh_res_mm,
                       feature_mm=prim["min_feature"])
            _warn_defects(path, [{"label": prim["label"],
                                  "start": prim["start"],
                                  "stop": prim["stop"]}])
            prims.append(prim)
            continue
        # "solids": every group whose FIRST member came from this leaf.
        for gi, (idx, solid, fused) in enumerate(groups):
            if gi in emitted or members[min(idx)]["slot"] != si:
                continue
            emitted.add(gi)
            mem = [members[i] for i in idx]
            path = _write(solid, mem)
            if fused:
                topo = stl_topology(path)
                bad = _score(topo)
                if bad > (0, 0):
                    # Never ship a fuse WORSE than its parts: tessellate them
                    # one by one and keep whichever openEMS will read better
                    # (measured on the forum J-pole: the fused PEC has 18
                    # edges where a tube's bore edge rests on the mast
                    # junction; its parts alone have 8, all where a clamp
                    # closes on itself).
                    alt = []
                    for i in idx:
                        p_i = os.path.join(workdir, "{0}_part{1}.stl".format(
                            name_prefix, i + 1))
                        export_stl(members[i]["solid"], p_i,
                                   mesh_res_mm=mesh_res_mm,
                                   feature_mm=members[i]["min_feature"])
                        alt.append((i, p_i, stl_topology(p_i)))
                    tot = tuple(sum(_score(t)[k] for _i, _p, t in alt)
                                for k in range(2))
                    if tot < bad:
                        _emit(notes, "note", (
                            "material '{0}': fused into one solid, {1} would "
                            "leave {2} triangle(s) openEMS refuses, part by "
                            "part {3}, so they are exported part by part "
                            "(each still a closed solid; only the faces where "
                            "they touch stay in the model).").format(
                                mat_label, _names(mem), bad[0], tot[0]))
                        os.remove(path)
                        stl_count[0] -= 1
                        for i, p_i, _t in alt:
                            final = _next_path()
                            os.replace(p_i, final)
                            _warn_defects(final, [members[i]])
                            prims.append(_stl_prim([i], members[i]["solid"],
                                                   final))
                        continue
                    for _i, p_i, _t in alt:
                        os.remove(p_i)
            _warn_defects(path, mem)
            prims.append(_stl_prim(idx, solid, path))
    return prims
