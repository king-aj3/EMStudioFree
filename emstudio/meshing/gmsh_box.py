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

#: Outer boundary of an OPEN (radiating) domain. Kept distinct from
#: WALL_ATTR because the two mean opposite things: a PEC wall REFLECTS
#: everything and a radiation boundary ABSORBS it. Until v1.5.0 every Palace
#: mesh this project wrote tagged its entire outer boundary `pec_walls`, which
#: is exactly right for a resonant cavity and makes radiation impossible by
#: construction — a closed metal box cannot have a far field. That, not any
#: Palace limitation, is why nothing radiating had ever been gated on Palace.
RADIATION_ATTR = 3
#: waveguide (driven) attributes. The interior is always 1 and the ports run
#: consecutively from :data:`WG_PORT_ATTR_BASE`; the side walls take whatever
#: number is left after the ports, so the numbering DERIVES from the port count
#: instead of being fixed at two.
WG_VOLUME_ATTR = 1
WG_PORT_ATTR_BASE = 2


class BoxMeshError(ValueError):
    """The box cannot be meshed as requested."""


def wg_port_attr(index):
    """MFEM boundary attribute for 1-based port ``index``.

    Ports are numbered the way Palace numbers them — ``Index`` 1 upward — and
    the attribute is just that shifted past the interior's 1.
    """
    idx = int(index)
    if idx < 1:
        raise BoxMeshError("port index is 1-based; got {0}".format(index))
    return WG_PORT_ATTR_BASE + idx - 1


def wg_wall_attr(n_ports=2):
    """MFEM boundary attribute for the side walls of an ``n_ports`` mesh.

    ⚠ **The wall attribute MOVES when the port count does** — it is whatever
    number sits immediately after the last port, because the ports have to be
    consecutive for the config writer to name them. A 3-port mesh puts its
    walls on 5, not on 4.

    That is the trap this function exists to close: the walls used to be the
    literal constant 4, correct only for two ports, and a hard-coded 4 on a
    3-port mesh would tag the walls with PORT 3's attribute. Palace would then
    see a port face that is also PEC, which is not an error it reports as one.
    Take the wall attribute from HERE, with the same port count the mesh was
    written with, never from a remembered number.
    """
    n = int(n_ports)
    if n < 1:
        raise BoxMeshError("a mesh needs at least one port; got {0}".format(n_ports))
    return WG_PORT_ATTR_BASE + n


#: The 2-port names, kept because the box and coax geometries ARE 2-port by
#: construction (a box section has two end faces; a coax has two ends) and
#: every existing caller means exactly these.
WG_PORT1_ATTR = wg_port_attr(1)
WG_PORT2_ATTR = wg_port_attr(2)
#: ⚠ **2-PORT ONLY** — see :func:`wg_wall_attr`. Correct for the box and coax
#: meshes; wrong for anything with a different port count.
WG_WALL_ATTR = wg_wall_attr(2)


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


def write_geo_open(size_mm, path, elem_mm=None, origin_mm=(0.0, 0.0, 0.0)):
    """Write an OPEN air box whose outer boundary is a radiation surface.

    Same geometry as :func:`write_geo`, one difference that changes everything:
    the six faces become ``radiation`` (attribute :data:`RADIATION_ATTR`)
    rather than ``pec_walls``. The Palace writer then attaches
    ``Boundaries.Absorbing`` to that attribute so the wave leaves, and
    ``Boundaries.Postprocessing.FarField`` to the same attribute so the far
    field can be extracted from it.

    ⛳ Palace's own requirement, quoted from its config schema: the far-field
    attributes "must enclose the system and be on an external boundary". One
    group covering all six faces satisfies both, which is why they are tagged
    together rather than per-face.

    ⚠ The radiating STRUCTURE is meshed separately and sits inside this box;
    this writes only the air region and its absorbing shell.
    """
    dx, dy, dz = size_mm
    x0, y0, z0 = origin_mm
    if elem_mm is None:
        elem_mm = min(dx, dy, dz) / 10.0
    lines = [
        "// EMStudio 3-D OPEN (radiating) air box, units: mm; Palace L0 = 1e-3",
        "// rerun: gmsh -3 -format msh22 <this file> -o out.msh",
        'SetFactory("OpenCASCADE");',
        "Box(1) = {{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}}};".format(
            x0, y0, z0, dx, dy, dz),
        "Mesh.MeshSizeMin = {0:.9g};".format(elem_mm),
        "Mesh.MeshSizeMax = {0:.9g};".format(elem_mm),
        "// air region -> MFEM domain attribute {0}".format(VOLUME_ATTR),
        'Physical Volume("interior", {0}) = {{1}};'.format(VOLUME_ATTR),
        "// all 6 faces -> ONE absorbing/far-field group -> attribute {0}".format(
            RADIATION_ATTR),
        "outer() = Boundary{ Volume{1}; };",
        'Physical Surface("radiation", {0}) = {{ outer() }};'.format(
            RADIATION_ATTR),
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
