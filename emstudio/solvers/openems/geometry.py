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


def export_stl(shape, path):
    """Tessellate a shape and write (binary) STL. Returns the path."""
    import Mesh
    import MeshPart

    diag = max(shape.BoundBox.DiagonalLength, 1.0)
    mesh = MeshPart.meshFromShape(
        Shape=shape, LinearDeflection=diag * 0.005, AngularDeflection=0.35, Relative=False
    )
    mesh.write(path)
    return path


def min_feature_mm(shape=None, mesh=None, bbox=None):
    """The smallest dimension the FDTD grid has to resolve, in mm.

    An axis-aligned box announces its own smallest side, but a swept or
    tessellated body does not: a 6-turn helix has a 320 mm bounding box and a
    20 mm conductor, and only the second number tells you whether a grid can
    represent it. Volume/surface recovers it without any topology work —

        thin plate, thickness t:  V/A -> t/2
        long rod, radius r:       V/A -> r/2

    so ``2*V/A`` is the plate's thickness exactly and the rod's RADIUS (i.e.
    half its diameter). Taking the smaller reading is deliberate: this figure
    gates a refusal, and under-estimating errs toward warning the user.
    Measured on a real octagonal helix: 2V/A = 9.22 mm against a true 19.98 mm
    across-flats — the conservative half, as intended.

    Falls back to the smallest bounding-box side when there is no usable
    volume (sheets, open shells, meshes without a closed volume).
    """
    vol = area = 0.0
    if shape is not None:
        try:
            vol, area = float(shape.Volume), float(shape.Area)
        except Exception:                                    # noqa: BLE001
            vol = area = 0.0
    elif mesh is not None:
        try:
            vol, area = abs(float(mesh.Volume)), float(mesh.Area)
        except Exception:                                    # noqa: BLE001
            vol = area = 0.0
    if vol > 0.0 and area > 0.0:
        return 2.0 * vol / area
    if bbox is not None:
        lo, hi = bbox
        sides = [hi[i] - lo[i] for i in range(3) if hi[i] - lo[i] > 0.0]
        if sides:
            return min(sides)
    return 0.0


def classify_shapes(material_obj, workdir, name_prefix):
    """Classify every referenced shape of a material.

    Returns a list of primitive dicts:
      {"kind": "box",  "start": (x,y,z), "stop": (x,y,z), "sheet_axis": int|None}
      {"kind": "stl",  "path": str,      "start": (...),  "stop": (...)}
    """
    from emstudio.objects import query

    prims = []
    stl_count = 0
    for link_obj, shape, sub in query.resolved_references(material_obj):
        if shape is None:
            # Mesh::Feature (e.g. an imported STL): pass its triangles through
            # verbatim — CSXCAD reads STL natively, no solid conversion needed.
            mesh = getattr(link_obj, "Mesh", None)
            if mesh is not None and mesh.CountFacets > 0:
                stl_count += 1
                path = os.path.join(workdir, "{0}_{1}.stl".format(name_prefix, stl_count))
                mesh.write(path)
                bb = mesh.BoundBox
                start = (bb.XMin, bb.YMin, bb.ZMin)
                stop = (bb.XMax, bb.YMax, bb.ZMax)
                prims.append(
                    {
                        "kind": "stl",
                        "path": path,
                        "start": start,
                        "stop": stop,
                        "min_feature": min_feature_mm(mesh=mesh,
                                                      bbox=(start, stop)),
                    }
                )
            continue
        # whole-object references to non-shapes are skipped silently
        if getattr(shape, "isNull", lambda: False)():
            continue
        start, stop = _bbox_tuple(shape)
        if _is_axis_aligned_box(shape):
            prims.append({"kind": "box", "start": start, "stop": stop,
                          "sheet_axis": None,
                          "min_feature": min_feature_mm(bbox=(start, stop))})
        elif _is_axis_aligned_sheet(shape):
            prims.append(
                {
                    "kind": "box",
                    "start": start,
                    "stop": stop,
                    "sheet_axis": _sheet_normal_axis(shape),
                    "min_feature": min_feature_mm(bbox=(start, stop)),
                }
            )
        elif sub.startswith("Edge"):
            # bare edges belong to the wire/NEC2 world; openEMS ignores them unless
            # they are port spans (handled separately)
            continue
        else:
            stl_count += 1
            fname = "{0}_{1}.stl".format(name_prefix, stl_count)
            path = export_stl(shape, os.path.join(workdir, fname))
            prims.append({"kind": "stl", "path": path, "start": start,
                          "stop": stop,
                          "min_feature": min_feature_mm(shape=shape,
                                                        bbox=(start, stop))})
    return prims
