# SPDX-License-Identifier: LGPL-2.1-or-later
"""Gmsh meshing for 2-D axisymmetric (rz-plane) EM analyses.

Generates a gmsh ``.geo`` for a set of rectangular regions (billets, coil
cross-sections) inside an auto-sized air domain in the r >= 0 half-plane,
then runs gmsh as a subprocess to produce a ``.msh`` (msh2 format — the
traditionally safe input for ``ElmerGrid 14 2``; msh4.1 also works with
Elmer v26 but msh2 is kept for older ElmerGrid compatibility).

Geometry uses gmsh's OpenCASCADE kernel with ``BooleanFragments`` so the
region rectangles and the air domain share conformal edges without any
manual point/line bookkeeping; regions and boundary lines are recovered
after fragmentation via ``In BoundingBox`` searches (verified with gmsh
4.12.1 on 2026-07-05).

Units: the ``.geo`` is written in MILLIMETERS (FreeCAD's native length);
the Elmer ``.sif`` compensates with ``Coordinate Scaling = 0.001`` (the
same convention FreeCAD's own FEM/Elmer pipeline uses) so results overlay
the FreeCAD geometry in the 3-D viewport.

Physical groups written (bodies tagged 1..N in region order, then lines):

* one ``Physical Surface`` per region (its ``name``),
* ``air`` — the remainder of the domain,
* ``router`` / ``ztop`` / ``zbottom`` — the three outer boundary lines,
* ``axis`` — every line on r = 0.

ElmerGrid renumbers boundary lines independently of surfaces; the
authoritative name -> id map must be parsed from ``mesh.names`` (see
``emstudio.solvers.elmer.parser.parse_mesh_names``).

Qt-free and FreeCAD-free: usable from plain python3 validation gates.
"""
from __future__ import annotations

import os

from emstudio.setup import solvers as solver_setup
from emstudio.solvers.base import SolverError, SolverJob

#: names reserved for the auto-generated groups
AIR_NAME = "air"
BOUNDARY_NAMES = ("router", "ztop", "zbottom", "axis")


class AxiMeshError(ValueError):
    """The region list cannot be meshed as an axisymmetric model."""


def _check_regions(regions):
    if not regions:
        raise AxiMeshError("no regions to mesh — the analysis has no magnetics bodies")
    for reg in regions:
        for key in ("name", "r0", "r1", "z0", "z1"):
            if key not in reg:
                raise AxiMeshError("region missing '{0}': {1}".format(key, reg))
        if reg["r0"] < -1e-9:
            raise AxiMeshError(
                "region '{0}' extends to r < 0 (r0={1}); axisymmetric bodies "
                "must live in the r >= 0 half-plane".format(reg["name"], reg["r0"])
            )
        if reg["r1"] - reg["r0"] <= 0 or reg["z1"] - reg["z0"] <= 0:
            raise AxiMeshError("region '{0}' has non-positive extent".format(reg["name"]))
        if reg["name"] in BOUNDARY_NAMES or reg["name"] == AIR_NAME:
            raise AxiMeshError(
                "region name '{0}' is reserved for auto-generated groups".format(reg["name"])
            )
    names = [r["name"] for r in regions]
    if len(set(names)) != len(names):
        raise AxiMeshError("duplicate region names: {0}".format(names))


def domain_extents(regions, scale=8.0):
    """Auto-size the air domain: (r_out, z_min, z_max) from the regions.

    ``scale`` multiplies the largest region extent from the origin; the
    domain is a rectangle 0..r_out x z_min..z_max, z-centered on the
    regions' midpoint.
    """
    r_max = max(reg["r1"] for reg in regions)
    z_lo = min(reg["z0"] for reg in regions)
    z_hi = max(reg["z1"] for reg in regions)
    z_mid = 0.5 * (z_lo + z_hi)
    half = max(r_max, 0.5 * (z_hi - z_lo))
    r_out = scale * half
    return r_out, z_mid - scale * half, z_mid + scale * half


def write_geo(regions, path, air=None, lc_air=None, domain_scale=8.0,
              mesh_grade=0.12):
    """Write the axisymmetric ``.geo`` file. Returns ``path``.

    :param regions: list of dicts ``{name, r0, r1, z0, z1, lc}`` in mm
        (``lc`` = target mesh size in the region, mm).
    :param air: optional ``(r_out, z_min, z_max)`` override in mm.
    :param lc_air: mesh size at the far boundary (default r_out / 20).
    :param domain_scale: auto air-domain factor when ``air`` is None.
    """
    _check_regions(regions)
    if air is None:
        air = domain_extents(regions, scale=domain_scale)
    r_out, z_min, z_max = air
    if lc_air is None:
        lc_air = r_out / 20.0
    for reg in regions:
        if reg["r1"] > r_out + 1e-9 or reg["z0"] < z_min - 1e-9 or reg["z1"] > z_max + 1e-9:
            raise AxiMeshError(
                "region '{0}' sticks out of the air domain "
                "(r_out={1}, z={2}..{3})".format(reg["name"], r_out, z_min, z_max)
            )

    # bounding-box search tolerance: well below any feature, above round-off
    eps = max(1e-6, 1e-4 * min(min(r["r1"] - r["r0"], r["z1"] - r["z0"]) for r in regions))

    L = []
    w = L.append
    w("// EMStudio axisymmetric mesh (rz half-plane, x = r, y = z), units: mm")
    w("// rerun manually: gmsh -2 -format msh2 <this file> -o out.msh")
    w('SetFactory("OpenCASCADE");')
    w("")
    w("// air domain")
    w("Rectangle(1) = {{0, {0:.9g}, 0, {1:.9g}, {2:.9g}}};".format(z_min, r_out, z_max - z_min))
    w("// regions")
    for i, reg in enumerate(regions):
        w("Rectangle({0}) = {{{1:.9g}, {2:.9g}, 0, {3:.9g}, {4:.9g}}};  // {5}".format(
            i + 2, reg["r0"], reg["z0"], reg["r1"] - reg["r0"], reg["z1"] - reg["z0"],
            reg["name"]))
    region_ids = ", ".join(str(i + 2) for i in range(len(regions)))
    w("BooleanFragments{ Surface{1}; Delete; }{ Surface{" + region_ids + "}; Delete; }")
    w("")
    w("// recover surfaces by bounding box after fragmentation")
    for i, reg in enumerate(regions):
        w("s{0}() = Surface In BoundingBox{{{1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}, {6:.9g}}};".format(
            i, reg["r0"] - eps, reg["z0"] - eps, -eps,
            reg["r1"] + eps, reg["z1"] + eps, eps))
    w("sair() = Surface In BoundingBox{{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}}};".format(
        -eps, z_min - eps, -eps, r_out + eps, z_max + eps, eps))
    for i in range(len(regions)):
        w("sair() -= {s" + str(i) + "()};")
    w("")
    w("// physical groups: bodies first (tags 1..N keep ElmerGrid numbering stable)")
    for i, reg in enumerate(regions):
        w('Physical Surface("{0}", {1}) = {{s{2}()}};'.format(reg["name"], i + 1, i))
    w('Physical Surface("{0}", {1}) = {{sair()}};'.format(AIR_NAME, len(regions) + 1))
    w("")
    w("// boundary lines")
    w("lrout() = Curve In BoundingBox{{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}}};".format(
        r_out - eps, z_min - eps, -eps, r_out + eps, z_max + eps, eps))
    w("ltop() = Curve In BoundingBox{{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}}};".format(
        -eps, z_max - eps, -eps, r_out + eps, z_max + eps, eps))
    w("lbot() = Curve In BoundingBox{{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}}};".format(
        -eps, z_min - eps, -eps, r_out + eps, z_min + eps, eps))
    w("laxis() = Curve In BoundingBox{{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, {5:.9g}}};".format(
        -eps, z_min - eps, -eps, eps, z_max + eps, eps))
    base = len(regions) + 2
    w('Physical Curve("router", {0}) = {{lrout()}};'.format(base))
    w('Physical Curve("ztop", {0}) = {{ltop()}};'.format(base + 1))
    w('Physical Curve("zbottom", {0}) = {{lbot()}};'.format(base + 2))
    w('Physical Curve("axis", {0}) = {{laxis()}};'.format(base + 3))
    w("")
    w("// per-region surface groups (convection BCs on body/air interfaces);")
    w("// only edges strictly inside the domain — never the axis or the outer")
    w("// boundary (a curve in two physical groups would duplicate boundary")
    w("// elements with conflicting tags)")
    tag = base + 4
    for i, reg in enumerate(regions):
        edges = []
        if reg["r1"] < r_out - eps:
            edges.append((reg["r1"] - eps, reg["z0"] - eps, reg["r1"] + eps, reg["z1"] + eps))
        if reg["r0"] > eps:
            edges.append((reg["r0"] - eps, reg["z0"] - eps, reg["r0"] + eps, reg["z1"] + eps))
        if reg["z1"] < z_max - eps:
            edges.append((reg["r0"] - eps, reg["z1"] - eps, reg["r1"] + eps, reg["z1"] + eps))
        if reg["z0"] > z_min + eps:
            edges.append((reg["r0"] - eps, reg["z0"] - eps, reg["r1"] + eps, reg["z0"] + eps))
        if not edges:
            continue
        w("srf{0}() = {{}};".format(i))
        for x0, y0, x1, y1 in edges:
            w("srf{0}() += Curve In BoundingBox{{{1:.9g}, {2:.9g}, {3:.9g}, "
              "{4:.9g}, {5:.9g}, {6:.9g}}};".format(i, x0, y0, -eps, x1, y1, eps))
        w('Physical Curve("surf_{0}", {1}) = {{srf{2}()}};'.format(reg["name"], tag, i))
        tag += 1
    w("")
    w("// mesh sizes: per-region point sizes + distance-graded background field")
    w("// (uniform-coarse air visibly degrades inductance extraction — verified")
    w("//  against analytic coil L/M/k on 2026-07-05; keep the grading)")
    field_ids = []
    for i, reg in enumerate(regions):
        lc = reg.get("lc") or min(reg["r1"] - reg["r0"], reg["z1"] - reg["z0"]) / 6.0
        w("MeshSize{{ PointsOf{{ Surface{{s{0}()}}; }} }} = {1:.9g};".format(i, lc))
        rc = 0.5 * (reg["r0"] + reg["r1"])
        zc = 0.5 * (reg["z0"] + reg["z1"])
        fid = i + 1
        field_ids.append(fid)
        w("Field[{0}] = MathEval;".format(fid))
        # sign folded in: "(y+5)" not "(y--5)" — gmsh mathex rejects double minus
        w('Field[{0}].F = "{1:.9g} + {2:.9g}*Sqrt((x{3:+.9g})^2 + (y{4:+.9g})^2)";'.format(
            fid, lc, mesh_grade, -rc, -zc))
    combo = len(field_ids) + 1
    w("Field[{0}] = Min;".format(combo))
    w("Field[{0}].FieldsList = {{{1}}};".format(combo, ", ".join(str(f) for f in field_ids)))
    w("Background Field = {0};".format(combo))
    w("Mesh.MeshSizeMax = {0:.9g};".format(lc_air))
    w("Mesh.MeshSizeFromPoints = 1;")
    w("Mesh.Algorithm = 6;  // Frontal-Delaunay")
    w("Mesh.ElementOrder = 1;")
    w("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path


def run_gmsh(geo_path, msh_path, line_callback=None, timeout=600):
    """Mesh a ``.geo`` to msh2 format via the gmsh subprocess. Returns ``msh_path``."""
    info = solver_setup.find_backend("gmsh")
    if not info.found:
        raise SolverError("gmsh not found.\n" + solver_setup.install_hint(info.backend))
    job = SolverJob(
        [info.path, "-2", "-format", "msh2", "-o", msh_path, geo_path],
        cwd=os.path.dirname(os.path.abspath(geo_path)),
        line_callback=line_callback,
    )
    job.run_blocking(timeout=timeout)
    if not os.path.isfile(msh_path):
        raise SolverError("gmsh produced no mesh at {0}".format(msh_path))
    return msh_path


def mesh_axisymmetric(regions, workdir, air=None, lc_air=None, domain_scale=8.0,
                      mesh_grade=0.12, line_callback=None):
    """Full meshing step: write ``model.geo`` and run gmsh. Returns the .msh path."""
    geo = write_geo(regions, os.path.join(workdir, "model.geo"), air=air,
                    lc_air=lc_air, domain_scale=domain_scale, mesh_grade=mesh_grade)
    return run_gmsh(geo, os.path.join(workdir, "model.msh"), line_callback=line_callback)
