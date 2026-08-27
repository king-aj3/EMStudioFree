# SPDX-License-Identifier: LGPL-2.1-or-later
"""Gmsh 3-D meshing for FEM analyses (Palace backend) — closed AND open.

Four geometries now, not one: :func:`write_geo` (a closed PEC cavity),
:func:`write_geo_open` (an open box with an absorbing far-field shell),
:func:`write_geo_dipole_open` (a centre-fed dipole in a radiating domain —
v1.10.0) and the coax writer. The original and simplest case meshes an
axis-aligned rectangular box (a cavity interior) into 3-D tetrahedra with one
physical volume (the dielectric interior) and one physical surface group (the
PEC walls). Output is gmsh ``.msh`` version
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
#: A radiating DIPOLE inside an open domain: the two PEC arms and the flat
#: gap rectangle that carries the lumped port. Numbered above RADIATION_ATTR
#: so an open box and an open dipole can never collide, and kept distinct from
#: WALL_ATTR because these conductors are the ANTENNA, not the enclosure.
DIPOLE_PEC_ATTR = 4
DIPOLE_PORT_ATTR = 5

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


def write_geo_dipole_open(path, wavelength_mm, arm_len_mm=None,
                          arm_radius_mm=None, gap_mm=None,
                          outer_radius_mm=None, elem_mm=None,
                          gap_elem_mm=None):
    """Write an OPEN (radiating) domain containing a centre-fed DIPOLE.

    ⭐ **This is the geometry the far-field path was missing.** EMStudio could
    hand Palace an absorbing boundary and a ``Postprocessing.FarField`` block
    (v1.5.0), and could read the answer back (the far-field parser) — but
    nothing ever BUILT a radiating Palace domain. This writes one.

    ⚠ **There is still no GUI click-path.** The only caller is
    ``tests/validation/palace_dipole_farfield.py``; no Templates entry and no
    command builds this. "The capability had no click-path" was the reason it
    was written, and writing it did not by itself create one — a Templates
    entry is separate, unstarted work. Do not read this function's existence
    as a button a user can press.

    The arrangement follows Palace's own antenna example
    (``examples/antenna/mesh/mesh.jl``, Copyright Amazon.com Inc., Apache-2.0),
    because it is the one its lumped port is known to accept: two cylinder arms
    on the Z axis separated by a thin gap, **a flat rectangle filling that gap
    as the port surface**, and a large sphere tagged as the single absorbing /
    far-field group.

    ⚠⚠ **The port rectangle is the part that is not obvious, and the order of
    operations is what makes it mesh.** A lumped port needs a SURFACE to drive
    across; a bare gap between two solids is not one. Three constructions were
    tried before one meshed:

    * embedding the rectangle with ``Surface{} In Volume{}`` → *"Could not
      recover boundary mesh"*;
    * fragmenting arms, rectangle and sphere all together → *"Invalid boundary
      mesh (overlapping facets)"*;
    * **what works**: cut the arms out of the sphere FIRST
      (``BooleanDifference``), then fragment the rectangle into the resulting
      air volume. The gap stays air, and the port face becomes a shared
      internal facet rather than something floating in a volume.

    ⚠ Surfaces are selected as SETS, not by clever bounding boxes: the port by
    its own thin slab, the conductors as everything inside the dipole's
    bounding box minus the port, and the sphere as everything else. The first
    attempt picked the sphere with a bounding box and silently tagged **zero**
    elements — a physical group can exist and be empty, and Palace will happily
    run with no absorbing boundary at all.

    ⚠ **Do not add a graded mesh field over the whole antenna.** It was tried:
    refining the full arm length ran past ten minutes without finishing. The
    two scales here (a gap ~1/400 of a wavelength inside a domain three
    wavelengths across) are handled by a plain min/max size instead.

    Defaults reproduce the reference: arms of a quarter wavelength each (a
    half-wave dipole), radius arm/20, gap arm/100, sphere at 1.5 wavelengths.

    ⚠ The outer boundary is a SPHERE, not the box :func:`write_geo_open`
    writes: a sphere presents the same angle of incidence everywhere, so an
    absorbing condition performs uniformly on it, while a box absorbs worst at
    its corners. For a resonator the shape does not matter and a box meshes
    more cheaply, which is why both exist.

    Returns the path written.
    """
    lam = float(wavelength_mm)
    if lam <= 0:
        raise BoxMeshError("wavelength must be positive")
    arm = float(arm_len_mm) if arm_len_mm else lam / 4.0
    rad = float(arm_radius_mm) if arm_radius_mm else arm / 20.0
    gap = float(gap_mm) if gap_mm else arm / 100.0
    outer = float(outer_radius_mm) if outer_radius_mm else 1.5 * lam
    if min(arm, rad, gap) <= 0:
        raise BoxMeshError("arm length, radius and gap must all be positive")
    if outer <= arm + gap / 2.0:
        raise BoxMeshError(
            "the outer boundary ({0:.4g} mm) must enclose the dipole "
            "({1:.4g} mm half-length)".format(outer, arm + gap / 2.0))
    if elem_mm is None:
        elem_mm = lam / 10.0
    if gap_elem_mm is None:
        gap_elem_mm = max(gap / 3.0, rad / 20.0)

    lines = [
        "// EMStudio OPEN radiating domain: a centre-fed dipole inside an",
        "// absorbing sphere. Units mm; Palace L0 = 1e-3.",
        "// Arrangement follows Palace's own examples/antenna/mesh/mesh.jl.",
        "// rerun: gmsh -3 -format msh22 <this file> -o out.msh",
        'SetFactory("OpenCASCADE");',
        "arm = {0:.9g}; rad = {1:.9g}; gap = {2:.9g};".format(arm, rad, gap),
        "outer = {0:.9g}; eps = {1:.9g};".format(outer, min(gap, rad) * 1e-3),
        "",
        "// the two arms, +Z and -Z, separated by the feed gap",
        "Cylinder(1) = {0,0, gap/2, 0,0, arm, rad};",
        "Cylinder(2) = {0,0,-gap/2, 0,0,-arm, rad};",
        "Sphere(3) = {0,0,0, outer};",
        "",
        "// ⚠ ORDER MATTERS: cut the conductors out FIRST, then fragment the",
        "// port face into the air. Fragmenting all three together produces",
        "// overlapping facets; embedding the face fails to recover the mesh.",
        "BooleanDifference(4) = { Volume{3}; Delete; }{ Volume{1,2}; Delete; };",
        "",
        "// the flat gap rectangle: THE LUMPED PORT SURFACE",
        "Rectangle(1000) = {-rad, -gap/2, 0, 2*rad, gap, 0};",
        "Rotate { {1,0,0}, {0,0,0}, Pi/2 } { Surface{1000}; }",
        "BooleanFragments{ Volume{4}; Delete; }{ Surface{1000}; Delete; }",
        "",
        'Physical Volume("interior", {0}) = {{ Volume{{:}} }};'.format(
            VOLUME_ATTR),
        "",
        "// Set arithmetic, NOT bounding-box cleverness: an empty physical",
        "// group is silently legal and Palace would run with no absorber.",
        "all() = Surface{:};",
        "port() = Surface In BoundingBox "
        "{ -rad-eps,-eps,-gap/2-eps, rad+eps, eps, gap/2+eps };",
        "dip()  = Surface In BoundingBox "
        "{ -rad-eps,-rad-eps,-arm-gap, rad+eps, rad+eps, arm+gap };",
        "pec() = dip();",
        "pec() -= port();",
        "sph() = all();",
        "sph() -= dip();",
        'Physical Surface("radiation", {0}) = {{ sph() }};'.format(
            RADIATION_ATTR),
        'Physical Surface("pec", {0}) = {{ pec() }};'.format(DIPOLE_PEC_ATTR),
        'Physical Surface("port", {0}) = {{ port() }};'.format(
            DIPOLE_PORT_ATTR),
        "",
        "Mesh.MeshSizeMin = {0:.9g};".format(gap_elem_mm),
        "Mesh.MeshSizeMax = {0:.9g};".format(elem_mm),
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
