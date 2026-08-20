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
    WG_VOLUME_ATTR,
    run_gmsh,
    wg_port_attr,
    wg_wall_attr,
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


def normalise_port_faces(ports, axis=None):
    """Turn the ``ports`` argument into a list of face selections. Returns a list.

    Two spellings are accepted, and they exist for different jobs:

    * ``(axis, at_max)`` — the face at one extreme of one axis, which is the
      same slab query the 2-port path has always used. It covers the geometries
      that actually turn up: straight sections, T and Y junctions, crosses,
      a connector transition with a port per interface.
    * an explicit 6-tuple ``(xmin, ymin, zmin, xmax, ymax, zmax)`` — a raw
      selection box in mm, for what the shorthand cannot say: two ports on the
      SAME face plane, or a port that is not at an extreme at all. Nothing is
      computed for you there; you are naming the faces yourself.

    ``ports=None`` reproduces the historical two ports at the min and max ends
    of ``axis``, so every existing caller means exactly what it always did.

    ⚠ **Order is the port numbering.** ``ports[0]`` becomes port 1, which is
    the port Palace excites by default and the one whose S11 the sweep reports.
    It is not sorted, deduplicated or re-derived from geometry, because the
    caller is the only thing that knows which physical connector is "port 1".
    """
    if ports is None:
        if axis not in (0, 1, 2):
            raise BrepMeshError(
                "axis must be 0, 1 or 2 when ports are not given; got {0}"
                .format(axis))
        return [(axis, False), (axis, True)]
    out = []
    for k, spec in enumerate(ports):
        seq = tuple(spec)
        if len(seq) == 2:
            ax, at_max = int(seq[0]), bool(seq[1])
            if ax not in (0, 1, 2):
                raise BrepMeshError(
                    "port {0}: axis must be 0, 1 or 2; got {1}".format(k + 1, seq[0]))
            out.append((ax, at_max))
        elif len(seq) == 6:
            out.append(tuple(float(v) for v in seq))
        else:
            raise BrepMeshError(
                "port {0}: expected (axis, at_max) or a 6-tuple bounding box, "
                "got {1} values".format(k + 1, len(seq)))
    if not out:
        raise BrepMeshError("a driven mesh needs at least one port")
    return out


def write_geo_brep_driven(brep_path, geo_path, axis=None, bbox_mm=None, elem_mm=None,
                          port_slab_frac=0.05, ports=None):
    """Write a ``.geo`` that Merges ``brep_path`` and tags N faces as ports.

    The general-BREP analogue of ``gmsh_box.write_geo_waveguide``. By default
    the two faces at the min/max of ``axis`` become ports 1 and 2 and the rest
    of the boundary is PEC — the 2-port behaviour this has always had. Pass
    ``ports`` to tag any number of faces instead (see
    :func:`normalise_port_faces`), which is what makes a 3-port junction or a
    4-port coupler meshable at all.

    Any closed solid works (box, circular cylinder, …), so a circular
    waveguide, a stepped/tapered guide, a T-junction etc. can be driven — not
    just an axis-aligned box.

    Physical groups follow ``gmsh_box``'s derivation — interior 1, ports
    2..N+1, walls N+2 — which for two ports is exactly the historical
    ``interior=1, port1=2, port2=3, walls=4``, so every 2-port mesh and config
    in the tree is byte-identical to before.

    ⚠ **The wall attribute is DERIVED, not the constant.** ``WG_WALL_ATTR`` is
    4, and 4 is port 3's attribute on a 3-port mesh — tagging walls with it
    would hand Palace a face that is both a port and PEC. See
    :func:`gmsh_box.wg_wall_attr`.

    Recipe (verified vs the box path + a circular-waveguide TE11 cutoff on
    2026-07-07):

    * ``Merge`` the BREP under the OpenCASCADE kernel, ``vv() = Volume{:}``.
    * Pick each port face with a thin ``Surface In BoundingBox`` slab at its
      axis extreme: slab thickness ``port_slab_frac * that_axis_extent`` (5%),
      with the two lateral axes padded by ``0.5*extent + 1 mm`` per side so the
      query box fully contains the flat end face even when FreeCAD reports a
      tessellation-shrunk bounding box for a curved solid.
    * ``walls() = Abs(Boundary{Volume{vv()}})`` minus every port.
      ``Abs()`` is mandatory (a signed boundary tag breaks the list subtraction
      and lands a face in two Physical groups -> Palace aborts).

    :param axis: 0=x, 1=y, 2=z — the propagation axis, used only when ``ports``
        is not given (its two end faces become the two ports).
    :param bbox_mm: ``(xmin, ymin, zmin, xmax, ymax, zmax)`` of the solid, mm.
    :param ports: optional explicit port faces; see :func:`normalise_port_faces`.
    """
    if not os.path.isfile(brep_path):
        raise BrepMeshError("BREP not found: {0}".format(brep_path))
    faces = normalise_port_faces(ports, axis)
    if bbox_mm is None:
        raise BrepMeshError("bbox_mm is required")
    mins = [float(bbox_mm[0]), float(bbox_mm[1]), float(bbox_mm[2])]
    maxs = [float(bbox_mm[3]), float(bbox_mm[4]), float(bbox_mm[5])]
    ext = [maxs[i] - mins[i] for i in range(3)]
    if min(ext) <= 1e-6:
        raise BrepMeshError("degenerate bounding box {0}".format(bbox_mm))

    def _port_bbox(face):
        if len(face) == 6:              # explicit box: taken as given
            return list(face)
        port_axis, at_max = face
        # The slab is a fraction of THAT port's own axis extent, not of one
        # global propagation axis — a T-junction's side arm is a different
        # length from its through arm, and a slab sized off the wrong axis is
        # either too thin to catch the face or thick enough to catch a wall.
        slab = float(port_slab_frac) * ext[port_axis]
        # lateral (non-axis) padding is generous on purpose (bbox-shrink immune)
        lo = [mins[i] - (0.5 * ext[i] + 1.0) for i in range(3)]
        hi = [maxs[i] + (0.5 * ext[i] + 1.0) for i in range(3)]
        if at_max:
            lo[port_axis] = maxs[port_axis] - slab
            hi[port_axis] = maxs[port_axis] + 1.0
        else:
            lo[port_axis] = mins[port_axis] - 1.0
            hi[port_axis] = mins[port_axis] + slab
        return lo + hi

    def _sel(vals):
        return "Surface In BoundingBox{{{0}}}".format(
            ", ".join("{0:.9g}".format(v) for v in vals))

    n_ports = len(faces)
    wall_attr = wg_wall_attr(n_ports)

    def _describe(face):
        if len(face) == 6:
            return "explicit box"
        return "{0}{1}".format("-+"[int(bool(face[1]))], "xyz"[face[0]])

    lines = [
        "// EMStudio general-3D waveguide mesh (imported BREP), {0} port(s) at "
        "{1}, units: mm".format(n_ports, ", ".join(_describe(f) for f in faces)),
        "// Physical groups: interior={0}, port1..port{1}={2}..{3}, walls={4}"
        .format(WG_VOLUME_ATTR, n_ports, wg_port_attr(1), wg_port_attr(n_ports),
                wall_attr),
        'SetFactory("OpenCASCADE");',
        'Merge "{0}";'.format(os.path.abspath(brep_path)),
        "vv() = Volume{:};",
    ]
    for k, face in enumerate(faces, start=1):
        lines.append("port{0}() = {1};".format(k, _sel(_port_bbox(face))))
    # walls = whole boundary minus every port; Abs() drops the orientation
    # sign so the list subtraction is well-formed
    lines.append("walls() = Abs( Boundary{ Volume{ vv() }; } );")
    for k in range(1, n_ports + 1):
        lines.append("walls() -= port{0}();".format(k))
    lines.append(
        'Physical Volume ("interior", {0}) = {{ vv() }};'.format(WG_VOLUME_ATTR))
    for k in range(1, n_ports + 1):
        lines.append('Physical Surface("port{0}", {1}) = {{ port{0}() }};'
                     .format(k, wg_port_attr(k)))
    lines.append(
        'Physical Surface("walls", {0}) = {{ walls() }};'.format(wall_attr))
    if elem_mm and float(elem_mm) > 0:
        lines.append("Mesh.MeshSizeMin = {0:.9g};".format(float(elem_mm)))
        lines.append("Mesh.MeshSizeMax = {0:.9g};".format(float(elem_mm)))
    lines.append("Mesh.MshFileVersion = 2.2;")
    with open(geo_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return geo_path


def mesh_brep_driven(brep_path, workdir, axis, bbox_mm, elem_mm=None,
                     line_callback=None, ports=None):
    """Write ``waveguide.geo`` for a driven BREP solid and run gmsh. Returns .msh."""
    geo = write_geo_brep_driven(brep_path, os.path.join(workdir, "waveguide.geo"),
                                axis, bbox_mm, elem_mm=elem_mm, ports=ports)
    return run_gmsh(geo, os.path.join(workdir, "waveguide.msh"),
                    line_callback=line_callback)
