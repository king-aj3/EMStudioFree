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
                prims.append(
                    {
                        "kind": "stl",
                        "path": path,
                        "start": (bb.XMin, bb.YMin, bb.ZMin),
                        "stop": (bb.XMax, bb.YMax, bb.ZMax),
                    }
                )
            continue
        # whole-object references to non-shapes are skipped silently
        if getattr(shape, "isNull", lambda: False)():
            continue
        start, stop = _bbox_tuple(shape)
        if _is_axis_aligned_box(shape):
            prims.append({"kind": "box", "start": start, "stop": stop, "sheet_axis": None})
        elif _is_axis_aligned_sheet(shape):
            prims.append(
                {
                    "kind": "box",
                    "start": start,
                    "stop": stop,
                    "sheet_axis": _sheet_normal_axis(shape),
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
            prims.append({"kind": "stl", "path": path, "start": start, "stop": stop})
    return prims
