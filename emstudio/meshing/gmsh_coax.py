# SPDX-License-Identifier: LGPL-2.1-or-later
"""Gmsh 3-D meshing for a coaxial line (Palace lumped-port S-parameters).

Meshes an annular tube (the dielectric between the inner and outer conductor
of a coax) along +Z into tetrahedra, with the physical groups Palace needs for
a radial lumped port at each end:

* ``dielectric`` volume  -> MFEM attribute 1
* ``pec`` walls          -> attribute 2  (inner + outer conductor cylinders)
* ``port1`` annular face -> attribute 3  (z = 0 end; the driven lumped port)
* ``port2`` annular face -> attribute 4  (z = L end; the passive lumped port)

The annulus is an outer disk minus an inner disk, extruded along z (OpenCASCADE).
The two flat end faces are picked by thin z-slab bounding boxes; the two curved
conductor walls are the *rest* of the volume boundary — ``Abs(Boundary{...})``
strips the orientation sign gmsh attaches, without which the list subtraction
silently fails and a face lands in two groups (Palace then aborts). Recipe
verified against the AWS Palace ``coaxial`` example on 2026-07-07.

Units: the ``.geo`` is in MILLIMETERS; the Palace config sets ``L0 = 1e-3``.
Qt-free and FreeCAD-free (subprocess to gmsh only).
"""
from __future__ import annotations

import os

from emstudio.meshing.gmsh_box import run_gmsh

#: MFEM attribute numbers (gmsh physical tags) the coax config writer references
COAX_VOLUME_ATTR = 1
COAX_WALL_ATTR = 2   # inner + outer conductor cylinder walls (PEC)
COAX_PORT1_ATTR = 3  # annular end face at z = 0 (driven lumped port)
COAX_PORT2_ATTR = 4  # annular end face at z = L (passive lumped port)


class CoaxMeshError(ValueError):
    """The coax cannot be meshed as requested."""


def write_geo_coax(a_mm, b_mm, length_mm, path, elem_mm=None):
    """Write a coax annulus ``.geo`` (along +Z). Returns ``path``.

    :param a_mm: inner conductor radius (mm).
    :param b_mm: outer conductor radius (mm).
    :param length_mm: coax length along z (mm).
    :param elem_mm: target tetra edge length (default: annular gap / 3, so the
        radial field is carried by a few elements).
    """
    a, b, L = float(a_mm), float(b_mm), float(length_mm)
    if not (0.0 < a < b):
        raise CoaxMeshError(
            "need 0 < inner radius < outer radius; got a={0}, b={1}".format(a, b))
    if L <= 0:
        raise CoaxMeshError("coax length must be positive, got {0}".format(L))
    if elem_mm is None:
        elem_mm = (b - a) / 3.0
    lines = [
        "// EMStudio coaxial mesh (annular tube along z), units: mm; Palace L0 = 1e-3",
        "// rerun: gmsh -3 -format msh22 <this file> -o out.msh",
        "// Physical groups (deterministic MFEM attributes):",
        "//   Physical Volume  {0} = dielectric (annular interior)".format(COAX_VOLUME_ATTR),
        "//   Physical Surface {0} = PEC (inner + outer conductor cylinder walls)".format(COAX_WALL_ATTR),
        "//   Physical Surface {0} = port1 (annular end face at z=0)".format(COAX_PORT1_ATTR),
        "//   Physical Surface {0} = port2 (annular end face at z=L)".format(COAX_PORT2_ATTR),
        'SetFactory("OpenCASCADE");',
        "ri  = {0:.9g};".format(a),
        "ro  = {0:.9g};".format(b),
        "L   = {0:.9g};".format(L),
        "eps = {0:.9g};".format(min((b - a), L) * 1e-3 + 1e-6),  # z-slab half-thickness
        "h   = {0:.9g};".format(float(elem_mm)),
        "// annulus (outer disk minus inner disk), extruded along z",
        "Disk(1) = {0, 0, 0, ro};",
        "Disk(2) = {0, 0, 0, ri};",
        "BooleanDifference(3) = { Surface{1}; Delete; }{ Surface{2}; Delete; };",
        "Extrude { 0, 0, L } { Surface{3}; }",
        "// the two flat annular end faces (zmin==zmax) by thin z-slab bboxes",
        "port1() = Surface In BoundingBox { -ro-eps, -ro-eps, -eps,   ro+eps, ro+eps, eps   };",
        "port2() = Surface In BoundingBox { -ro-eps, -ro-eps, L-eps,  ro+eps, ro+eps, L+eps };",
        "// walls = remaining boundary faces (inner + outer cylinders); Abs() strips",
        "// the orientation sign so the subtraction actually removes the ports.",
        "walls() = Abs( Boundary { Volume{1}; } );",
        "walls() -= port1();",
        "walls() -= port2();",
        'Physical Volume ("dielectric", {0}) = {{ 1 }};'.format(COAX_VOLUME_ATTR),
        'Physical Surface("pec",        {0}) = {{ walls() }};'.format(COAX_WALL_ATTR),
        'Physical Surface("port1",      {0}) = {{ port1() }};'.format(COAX_PORT1_ATTR),
        'Physical Surface("port2",      {0}) = {{ port2() }};'.format(COAX_PORT2_ATTR),
        "Mesh.MeshSizeMin = h;",
        "Mesh.MeshSizeMax = h;",
        "Mesh.MshFileVersion = 2.2;",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def mesh_coax(a_mm, b_mm, length_mm, workdir, elem_mm=None, line_callback=None):
    """Full meshing step: write ``coax.geo`` and run gmsh. Returns the .msh path."""
    geo = write_geo_coax(a_mm, b_mm, length_mm,
                         os.path.join(workdir, "coax.geo"), elem_mm=elem_mm)
    return run_gmsh(geo, os.path.join(workdir, "coax.msh"),
                    line_callback=line_callback)
