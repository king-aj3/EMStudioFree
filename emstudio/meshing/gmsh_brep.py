# SPDX-License-Identifier: LGPL-2.1-or-later
"""Gmsh 3-D meshing of a general BREP solid (Palace eigenmode, beyond boxes).

Meshes an ARBITRARY closed solid — exported from FreeCAD as a BREP — into
tetrahedra for a PEC-walled cavity eigenmode solve. The whole outer boundary of
the imported solid becomes one PEC group, so any single closed solid (cylinder,
sphere, chamfered box, …) works, not just a rectangular box.

Physical groups match the box mesher exactly, so the Palace eigenmode config
writer is reused unchanged:

* ``interior`` volume -> MFEM attribute 1 (``VOLUME_ATTR``)
* ``pec_walls``       -> attribute 2 (``WALL_ATTR``) — every boundary face

Recipe (verified against a cylinder vs the analytic cavity modes on 2026-07-07):
``Merge`` the BREP under the OpenCASCADE kernel, tag all volumes as attribute 1,
and tag ``Abs(Boundary{Volume{...}})`` as attribute 2. ``Abs()`` strips the
orientation sign gmsh attaches to boundary tags (a signed tag in a Physical
Surface list is malformed). Output is gmsh ``.msh`` 2.2 (Palace/MFEM reads it
reliably); the BREP carries raw mm, so the Palace config's ``L0 = 1e-3`` sets
the scale (same as the box path).

Units: mm. Qt-free and FreeCAD-free (subprocess to gmsh only).
"""
from __future__ import annotations

import os

from emstudio.meshing.gmsh_box import (
    VOLUME_ATTR,
    WALL_ATTR,
    WG_PORT1_ATTR,
    WG_PORT2_ATTR,
    WG_VOLUME_ATTR,
    WG_WALL_ATTR,
    run_gmsh,
)


class BrepMeshError(ValueError):
    """The BREP cannot be meshed as requested."""


def write_geo_brep(brep_path, geo_path, elem_mm=None):
    """Write a ``.geo`` that Merges ``brep_path`` and tags it for a PEC cavity.

    :param brep_path: path to a BREP solid (mm).
    :param elem_mm: target tetra edge length (mm). Curved surfaces need this
        capped or the round cross-section is under-faceted; the caller estimates
        it from the solid's bounding box.
    """
    if not os.path.isfile(brep_path):
        raise BrepMeshError("BREP not found: {0}".format(brep_path))
    lines = [
        "// EMStudio general-3D cavity mesh (imported BREP), units: mm; Palace L0 = 1e-3",
        "// rerun: gmsh -3 -format msh22 <this file> -o out.msh",
        "// Physical groups: interior volume = {0}, all boundary faces (PEC) = {1}".format(
            VOLUME_ATTR, WALL_ATTR),
        'SetFactory("OpenCASCADE");',
        'Merge "{0}";'.format(os.path.abspath(brep_path)),
        "vv() = Volume{:};",
        'Physical Volume ("interior", {0}) = {{ vv() }};'.format(VOLUME_ATTR),
        "// every boundary face -> one PEC group; Abs() drops the orientation sign",
        'Physical Surface("pec_walls", {0}) = {{ Abs(Boundary{{ Volume{{ vv() }}; }}) }};'.format(
            WALL_ATTR),
    ]
    if elem_mm and float(elem_mm) > 0:
        lines.append("Mesh.MeshSizeMin = {0:.9g};".format(float(elem_mm)))
        lines.append("Mesh.MeshSizeMax = {0:.9g};".format(float(elem_mm)))
    lines.append("Mesh.MshFileVersion = 2.2;")
    with open(geo_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return geo_path


def mesh_brep(brep_path, workdir, elem_mm=None, line_callback=None):
    """Full meshing step: write ``cavity.geo`` and run gmsh. Returns the .msh path."""
    geo = write_geo_brep(brep_path, os.path.join(workdir, "cavity.geo"), elem_mm=elem_mm)
    return run_gmsh(geo, os.path.join(workdir, "cavity.msh"),
                    line_callback=line_callback)


def write_geo_brep_driven(brep_path, geo_path, axis, bbox_mm, elem_mm=None,
                          port_slab_frac=0.05):
    """Write a ``.geo`` that Merges ``brep_path`` and tags TWO end faces as ports.

    The general-BREP analogue of ``gmsh_box.write_geo_waveguide``: the two faces
    at the min/max of ``axis`` become the driven/passive wave ports; the rest of
    the boundary is PEC. Any closed solid works (box, circular cylinder, …), so
    a circular waveguide, a stepped/tapered guide, etc. can be driven — not just
    an axis-aligned box.

    Physical groups deliberately equal the box waveguide's (interior=1, port1=2,
    port2=3, walls=4 = the ``WG_*`` constants), so ``build_driven_config`` and
    ``parse_sparams`` are reused unchanged.

    Recipe (verified vs the box path + a circular-waveguide TE11 cutoff on
    2026-07-07):

    * ``Merge`` the BREP under the OpenCASCADE kernel, ``vv() = Volume{:}``.
    * Pick the two port faces with thin ``Surface In BoundingBox`` slabs at the
      axis extremes: slab thickness ``port_slab_frac * axis_extent`` (5%), with
      the two lateral axes padded by ``0.5*extent + 1 mm`` per side so the query
      box fully contains the flat end face even when FreeCAD reports a
      tessellation-shrunk bounding box for a curved solid.
    * ``walls() = Abs(Boundary{Volume{vv()}}); walls() -= port1(); -= port2()``.
      ``Abs()`` is mandatory (a signed boundary tag breaks the list subtraction
      and lands a face in two Physical groups -> Palace aborts).

    :param axis: 0=x, 1=y, 2=z — the propagation axis (its two end faces = ports).
    :param bbox_mm: ``(xmin, ymin, zmin, xmax, ymax, zmax)`` of the solid, mm.
    """
    if not os.path.isfile(brep_path):
        raise BrepMeshError("BREP not found: {0}".format(brep_path))
    if axis not in (0, 1, 2):
        raise BrepMeshError("axis must be 0, 1 or 2; got {0}".format(axis))
    mins = [float(bbox_mm[0]), float(bbox_mm[1]), float(bbox_mm[2])]
    maxs = [float(bbox_mm[3]), float(bbox_mm[4]), float(bbox_mm[5])]
    ext = [maxs[i] - mins[i] for i in range(3)]
    if min(ext) <= 1e-6:
        raise BrepMeshError("degenerate bounding box {0}".format(bbox_mm))
    slab = float(port_slab_frac) * ext[axis]

    def _port_bbox(at_max):
        # lateral (non-axis) padding is generous on purpose (bbox-shrink immune)
        lo = [mins[i] - (0.5 * ext[i] + 1.0) for i in range(3)]
        hi = [maxs[i] + (0.5 * ext[i] + 1.0) for i in range(3)]
        if at_max:
            lo[axis] = maxs[axis] - slab
            hi[axis] = maxs[axis] + 1.0
        else:
            lo[axis] = mins[axis] - 1.0
            hi[axis] = mins[axis] + slab
        return lo + hi

    def _sel(vals):
        return "Surface In BoundingBox{{{0}}}".format(
            ", ".join("{0:.9g}".format(v) for v in vals))

    lines = [
        "// EMStudio general-3D waveguide mesh (imported BREP), ports on axis {0}, "
        "units: mm".format("xyz"[axis]),
        "// Physical groups match the box waveguide: interior={0}, port1={1}, "
        "port2={2}, walls={3}".format(
            WG_VOLUME_ATTR, WG_PORT1_ATTR, WG_PORT2_ATTR, WG_WALL_ATTR),
        'SetFactory("OpenCASCADE");',
        'Merge "{0}";'.format(os.path.abspath(brep_path)),
        "vv() = Volume{:};",
        "port1() = {0};".format(_sel(_port_bbox(False))),
        "port2() = {0};".format(_sel(_port_bbox(True))),
        # walls = whole boundary minus the two ports; Abs() drops the orientation
        # sign so the list subtraction is well-formed
        "walls() = Abs( Boundary{ Volume{ vv() }; } );",
        "walls() -= port1();",
        "walls() -= port2();",
        'Physical Volume ("interior", {0}) = {{ vv() }};'.format(WG_VOLUME_ATTR),
        'Physical Surface("port1", {0}) = {{ port1() }};'.format(WG_PORT1_ATTR),
        'Physical Surface("port2", {0}) = {{ port2() }};'.format(WG_PORT2_ATTR),
        'Physical Surface("walls", {0}) = {{ walls() }};'.format(WG_WALL_ATTR),
    ]
    if elem_mm and float(elem_mm) > 0:
        lines.append("Mesh.MeshSizeMin = {0:.9g};".format(float(elem_mm)))
        lines.append("Mesh.MeshSizeMax = {0:.9g};".format(float(elem_mm)))
    lines.append("Mesh.MshFileVersion = 2.2;")
    with open(geo_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return geo_path


def mesh_brep_driven(brep_path, workdir, axis, bbox_mm, elem_mm=None,
                     line_callback=None):
    """Write ``waveguide.geo`` for a driven BREP solid and run gmsh. Returns .msh."""
    geo = write_geo_brep_driven(brep_path, os.path.join(workdir, "waveguide.geo"),
                                axis, bbox_mm, elem_mm=elem_mm)
    return run_gmsh(geo, os.path.join(workdir, "waveguide.msh"),
                    line_callback=line_callback)
