# SPDX-License-Identifier: LGPL-2.1-or-later
"""Gmsh 3-D meshing for box/cavity FEM analyses (Palace backend).

Meshes an axis-aligned rectangular box (a cavity interior) into 3-D
tetrahedra with one physical volume (the dielectric interior) and one
physical surface group (the PEC walls). Output is gmsh ``.msh`` version
2.2 ASCII — the format AWS Palace / MFEM reads most reliably (verified
with Palace on 2026-07-06). Physical tags become MFEM attributes: the
volume is attribute 1, the walls attribute 2.

Units: the ``.geo`` is written in MILLIMETERS; the Palace config sets
``L0 = 1e-3`` so mesh coordinates are interpreted as mm.

Qt-free and FreeCAD-free (subprocess to gmsh only) so validation gates
run headlessly.
"""
from __future__ import annotations

import os

from emstudio.setup import solvers as solver_setup
from emstudio.solvers.base import SolverError, SolverJob

#: MFEM attribute numbers (physical tags) the config writer references
VOLUME_ATTR = 1
WALL_ATTR = 2
#: waveguide (driven) attributes: interior 1, port1 2, port2 3, side walls 4
WG_VOLUME_ATTR = 1
WG_PORT1_ATTR = 2
WG_PORT2_ATTR = 3
WG_WALL_ATTR = 4


class BoxMeshError(ValueError):
    """The box cannot be meshed as requested."""


def write_geo(size_mm, path, elem_mm=None, origin_mm=(0.0, 0.0, 0.0)):
    """Write a box ``.geo``. Returns ``path``.

    :param size_mm: (dx, dy, dz) box dimensions in mm.
    :param elem_mm: target tetra edge length in mm (default: smallest
        dimension / 4, so every dimension carries >= 4 elements).
    :param origin_mm: box corner (x0, y0, z0) in mm.
    """
    dx, dy, dz = (float(s) for s in size_mm)
    if min(dx, dy, dz) <= 0:
        raise BoxMeshError("box dimensions must be positive, got {0}".format(size_mm))
    if elem_mm is None:
        elem_mm = min(dx, dy, dz) / 4.0
    x0, y0, z0 = origin_mm

    lines = [
        "// EMStudio 3-D cavity mesh (box), units: mm; Palace L0 = 1e-3",
        "// rerun: gmsh -3 -format msh22 <this file> -o out.msh",
        'SetFactory("OpenCASCADE");',
        "Box(1) = {{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}}};".format(
            x0, y0, z0, dx, dy, dz),
        "Mesh.MeshSizeMin = {0:.9g};".format(elem_mm),
        "Mesh.MeshSizeMax = {0:.9g};".format(elem_mm),
        "// interior dielectric -> MFEM domain attribute {0}".format(VOLUME_ATTR),
        'Physical Volume("interior", {0}) = {{1}};'.format(VOLUME_ATTR),
        "// all 6 faces -> one PEC wall group -> MFEM boundary attribute {0}".format(WALL_ATTR),
        "wall() = Boundary{ Volume{1}; };",
        'Physical Surface("pec_walls", {0}) = {{ wall() }};'.format(WALL_ATTR),
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def write_geo_waveguide(size_mm, path, axis=2, elem_mm=None):
    """Write a waveguide-section ``.geo`` with the two end faces as ports.

    The two faces perpendicular to ``axis`` (0=x, 1=y, 2=z) become separate
    physical surface groups (port1 = min face -> attr 2, port2 = max face ->
    attr 3); the other four faces are the PEC walls (attr 4); the interior is
    attr 1. Faces are picked by ``Surface In BoundingBox`` (verified with
    Palace wave ports on 2026-07-06).

    :param size_mm: (dx, dy, dz) box dimensions in mm.
    """
    dx, dy, dz = (float(s) for s in size_mm)
    if min(dx, dy, dz) <= 0:
        raise BoxMeshError("box dimensions must be positive, got {0}".format(size_mm))
    if axis not in (0, 1, 2):
        raise BoxMeshError("axis must be 0, 1 or 2; got {0}".format(axis))
    if elem_mm is None:
        elem_mm = min(dx, dy, dz) / 5.0
    dims = [dx, dy, dz]
    eps = 1e-3

    def _bbox_face(ax, at_max):
        """BoundingBox slab for the face perpendicular to ax at its min/max."""
        lo = [-eps, -eps, -eps]
        hi = [dims[0] + eps, dims[1] + eps, dims[2] + eps]
        if at_max:
            lo[ax] = dims[ax] - eps
        else:
            hi[ax] = eps
        return lo + hi

    def _sel(fmt_args):
        return "Surface In BoundingBox{{{0}}}".format(
            ", ".join("{0:.9g}".format(v) for v in fmt_args))

    other = [i for i in range(3) if i != axis]  # the two wall axes
    lines = [
        "// EMStudio waveguide mesh (box, ports on axis {0}), units: mm".format("xyz"[axis]),
        'SetFactory("OpenCASCADE");',
        "Box(1) = {{0, 0, 0, {0:.9g}, {1:.9g}, {2:.9g}}};".format(dx, dy, dz),
        # each face selected EXPLICITLY by its own slab (no list subtraction —
        # a face landing in two physical groups makes Palace abort)
        "port1() = {0};".format(_sel(_bbox_face(axis, False))),
        "port2() = {0};".format(_sel(_bbox_face(axis, True))),
    ]
    wall_terms = []
    for w, ax in enumerate(other):
        lines.append("w{0}a() = {1};".format(w, _sel(_bbox_face(ax, False))))
        lines.append("w{0}b() = {1};".format(w, _sel(_bbox_face(ax, True))))
        wall_terms += ["w{0}a()".format(w), "w{0}b()".format(w)]
    lines.append('Physical Volume("interior", {0}) = {{1}};'.format(WG_VOLUME_ATTR))
    lines.append('Physical Surface("port1", {0}) = {{ port1() }};'.format(WG_PORT1_ATTR))
    lines.append('Physical Surface("port2", {0}) = {{ port2() }};'.format(WG_PORT2_ATTR))
    lines.append('Physical Surface("walls", {0}) = {{ {1} }};'.format(
        WG_WALL_ATTR, ", ".join(wall_terms)))
    lines.append("Mesh.MeshSizeMin = {0:.9g};".format(elem_mm))
    lines.append("Mesh.MeshSizeMax = {0:.9g};".format(elem_mm))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def run_gmsh(geo_path, msh_path, line_callback=None, timeout=600):
    """Mesh a ``.geo`` to 3-D msh2.2 via the gmsh subprocess. Returns ``msh_path``."""
    info = solver_setup.find_backend("gmsh")
    if not info.found:
        raise SolverError("gmsh not found.\n" + solver_setup.install_hint(info.backend))
    job = SolverJob(
        [info.path, "-3", "-format", "msh22", "-o", msh_path, geo_path],
        cwd=os.path.dirname(os.path.abspath(geo_path)),
        line_callback=line_callback,
    )
    job.run_blocking(timeout=timeout)
    if not os.path.isfile(msh_path):
        raise SolverError("gmsh produced no mesh at {0}".format(msh_path))
    return msh_path


def mesh_box(size_mm, workdir, elem_mm=None, origin_mm=(0.0, 0.0, 0.0),
             line_callback=None):
    """Full meshing step: write ``cavity.geo`` and run gmsh. Returns the .msh path."""
    geo = write_geo(size_mm, os.path.join(workdir, "cavity.geo"), elem_mm=elem_mm,
                    origin_mm=origin_mm)
    return run_gmsh(geo, os.path.join(workdir, "cavity.msh"),
                    line_callback=line_callback)


def mesh_waveguide(size_mm, workdir, axis=2, elem_mm=None, line_callback=None):
    """Full meshing step for a waveguide section. Returns the .msh path."""
    geo = write_geo_waveguide(size_mm, os.path.join(workdir, "waveguide.geo"),
                              axis=axis, elem_mm=elem_mm)
    return run_gmsh(geo, os.path.join(workdir, "waveguide.msh"),
                    line_callback=line_callback)
