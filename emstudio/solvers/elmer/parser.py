# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parsers for Elmer run artifacts: mesh.names, scalars.dat, ASCII VTU.

Also provides the axisymmetric integration helpers the runner uses to
extract engineering numbers from the field solution:

* per-body volume integrals with the 2*pi*r metric (Joule power in W),
* coil flux linkage lambda = (N/A_c) * integral(A_phi * 2*pi*r dA) over the
  coil cross-section — the standard FEM inductance extraction for
  uniformly-distributed (stranded) coils,
* nearest-node field probes (B at a point).

All formats verified against ElmerGrid/ElmerSolver v26.2 output on
2026-07-05. FreeCAD-free and Qt-free (numpy only, imported lazily).
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET


class ElmerParseError(RuntimeError):
    pass


# --- mesh.names -------------------------------------------------------------

def parse_mesh_names(path):
    """Parse ElmerGrid's ``mesh.names``. Returns (bodies, boundaries) dicts.

    Format (ElmerGrid 14 2 -autoclean): comment headers split the two
    namespaces, entries are ``$ name = id``::

        ! ----- names for bodies -----
        $ billet = 1
        ...
        ! ----- names for boundaries -----
        $ router = 1
    """
    bodies = {}
    boundaries = {}
    target = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            low = line.lower()
            if low.startswith("!"):
                if "bodies" in low:
                    target = bodies
                elif "boundaries" in low:
                    target = boundaries
                continue
            m = re.match(r"\s*\$\s*(\S+)\s*=\s*(\d+)", line)
            if m:
                if target is None:
                    # no headers seen (older ElmerGrid): first block is bodies
                    target = bodies
                target[m.group(1)] = int(m.group(2))
    if not bodies:
        raise ElmerParseError("no body names found in {0}".format(path))
    return bodies, boundaries


# --- scalars.dat ------------------------------------------------------------

def parse_scalars(dat_path):
    """Read SaveScalars output. Returns {column_name: last-row value}.

    Column names come from ``<dat_path>.names`` (lines like
    ``   1: res: eddy current power``).
    """
    names = []
    with open(dat_path + ".names", "r", encoding="utf-8", errors="replace") as fh:
        in_cols = False
        for line in fh:
            if "columns of matrix" in line.lower():
                in_cols = True
                continue
            m = re.match(r"\s*(\d+)\s*:\s*(.+?)\s*$", line)
            if in_cols and m:
                names.append(m.group(2))
    with open(dat_path, "r", encoding="utf-8", errors="replace") as fh:
        rows = [line.split() for line in fh if line.strip()]
    if not rows or not names:
        raise ElmerParseError("empty scalars output at {0}".format(dat_path))
    vals = [float(v) for v in rows[-1]]
    if len(vals) != len(names):
        raise ElmerParseError(
            "scalars.dat has {0} columns but {1} names".format(len(vals), len(names)))
    return dict(zip(names, vals))


def parse_scalars_series(dat_path):
    """Read a multi-row SaveScalars file. Returns {column_name: [values]}.

    Used for the transient heating curve (one row per timestep: time + max
    temperature + the auto-injected eddy-power columns).
    """
    names = []
    with open(dat_path + ".names", "r", encoding="utf-8", errors="replace") as fh:
        in_cols = False
        for line in fh:
            if "columns of matrix" in line.lower():
                in_cols = True
                continue
            m = re.match(r"\s*(\d+)\s*:\s*(.+?)\s*$", line)
            if in_cols and m:
                names.append(m.group(2))
    cols = [[] for _ in names]
    with open(dat_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != len(names):
                continue
            for i, v in enumerate(parts):
                cols[i].append(float(v))
    if not names or not cols[0]:
        raise ElmerParseError("empty scalars series at {0}".format(dat_path))
    return dict(zip(names, cols))


# --- VTU (ASCII) ------------------------------------------------------------

def parse_vtu(path):
    """Parse an ASCII .vtu (Elmer ResultOutputSolver, Ascii Output = True).

    Returns a dict:
        ``points``     (N, 3) float array (file units — mm after
                       Coordinate Scaling Revert),
        ``triangles``  (M, 3) int array (VTK cell type 5 only),
        ``tri_body``   (M,) GeometryIds per triangle (0 if absent),
        ``point_data`` {name: (N,) or (N, comp) array}.

    Non-triangle cells (boundary lines etc.) are dropped from the
    connectivity but their presence is tolerated.
    """
    import numpy as np

    # VTU files carry no XML namespace — plain tag names throughout
    tree = ET.parse(path)
    piece = tree.getroot().find(".//Piece")
    if piece is None:
        raise ElmerParseError("no <Piece> in {0}".format(path))

    def _read(da):
        if (da.get("format") or "ascii") != "ascii":
            raise ElmerParseError(
                "{0}: DataArray '{1}' is not ascii — was the sif written "
                "without 'Ascii Output = Logical True'?".format(path, da.get("Name")))
        return np.array((da.text or "").split(), dtype=float)

    pts = None
    for da in piece.find("Points").iter("DataArray"):
        pts = _read(da).reshape(-1, 3)
    cells = {}
    for da in piece.find("Cells").iter("DataArray"):
        cells[da.get("Name")] = _read(da).astype(int)
    point_data = {}
    pd = piece.find("PointData")
    if pd is not None:
        for da in pd.iter("DataArray"):
            arr = _read(da)
            ncomp = int(da.get("NumberOfComponents") or 1)
            if ncomp > 1:
                arr = arr.reshape(-1, ncomp)
            point_data[da.get("Name")] = arr
    cell_data = {}
    cd = piece.find("CellData")
    if cd is not None:
        for da in cd.iter("DataArray"):
            cell_data[da.get("Name")] = _read(da)

    if pts is None or "connectivity" not in cells:
        raise ElmerParseError("malformed VTU {0}".format(path))
    conn, offs, types = cells["connectivity"], cells["offsets"], cells["types"]
    tris = []
    tri_body = []
    lines = []
    line_body = []
    geo = cell_data.get("GeometryIds")
    start = 0
    for i, off in enumerate(offs):
        if types[i] == 5:  # VTK_TRIANGLE
            tris.append(conn[start:off])
            tri_body.append(int(geo[i]) if geo is not None else 0)
        elif types[i] == 3:  # VTK_LINE (boundary elements)
            lines.append(conn[start:off])
            line_body.append(int(geo[i]) if geo is not None else 0)
        start = off
    if not tris:
        raise ElmerParseError("no triangle cells in {0}".format(path))
    return {
        "points": pts,
        "triangles": np.array(tris, dtype=int),
        "tri_body": np.array(tri_body, dtype=int),
        "lines": (np.array(lines, dtype=int) if lines
                  else np.zeros((0, 2), dtype=int)),
        "line_body": np.array(line_body, dtype=int),
        "point_data": point_data,
    }


# --- axisymmetric integrals -------------------------------------------------

def body_integral(mesh, body_id, field_name, coord_scale=1e-3):
    """Integral of a nodal field over one body with the 2*pi*r metric (SI).

    ``coord_scale`` converts mesh coordinates to meters (mm -> 1e-3).
    Linear-triangle quadrature: centroid value x centroid radius x area
    (exact for the r-weighted linear part; converges O(h^2)).
    """
    import numpy as np

    field = mesh["point_data"].get(field_name)
    if field is None:
        raise ElmerParseError(
            "field '{0}' not in VTU (have: {1})".format(
                field_name, ", ".join(sorted(mesh["point_data"]))))
    sel = mesh["triangles"][mesh["tri_body"] == body_id]
    if not len(sel):
        raise ElmerParseError("body id {0} has no triangles".format(body_id))
    p = mesh["points"] * coord_scale
    a, b, c = p[sel[:, 0]], p[sel[:, 1]], p[sel[:, 2]]
    area = 0.5 * np.abs(
        (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
        - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
    r_bar = (a[:, 0] + b[:, 0] + c[:, 0]) / 3.0
    f_bar = (field[sel[:, 0]] + field[sel[:, 1]] + field[sel[:, 2]]) / 3.0
    return float(np.sum(2.0 * math.pi * r_bar * f_bar * area))


def body_area(mesh, body_id, coord_scale=1e-3):
    """Cross-section area of one body in m^2 (no 2*pi*r weight)."""
    import numpy as np

    sel = mesh["triangles"][mesh["tri_body"] == body_id]
    p = mesh["points"] * coord_scale
    a, b, c = p[sel[:, 0]], p[sel[:, 1]], p[sel[:, 2]]
    area = 0.5 * np.abs(
        (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
        - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
    return float(np.sum(area))


def flux_linkage(mesh, body_id, turns, coord_scale=1e-3):
    """Complex flux linkage of a stranded coil body (henry-ready, SI).

    lambda = (N / A_c) * integral(A_phi * 2*pi*r dA) over the coil
    cross-section, using the actual meshed area for A_c so quadrature
    biases cancel.
    """
    a_c = body_area(mesh, body_id, coord_scale)
    if "potential re" in mesh["point_data"]:
        lam_re = body_integral(mesh, body_id, "potential re", coord_scale)
        lam_im = body_integral(mesh, body_id, "potential im", coord_scale)
    else:
        # static (DC) magnetodynamics exposes the scalar 'potential' (v0.54)
        lam_re = body_integral(mesh, body_id, "potential", coord_scale)
        lam_im = 0.0
    return complex(lam_re, lam_im) * float(turns) / a_c


def boundary_integral(mesh, boundary_id, field_name, offset=0.0, coord_scale=1e-3):
    """Surface integral of (field - offset) over one boundary group (SI).

    Axisymmetric: integral of (f - offset) * 2*pi*r dl over the group's line
    elements — e.g. the convected power h * integral(T - T_ext) dA of a body
    surface. Elmer's VTU tags boundary elements' GeometryIds with the boundary
    id (verified v26.2; distinct from the body-id numbering of the bulk).
    """
    import numpy as np

    field = mesh["point_data"].get(field_name)
    if field is None:
        raise ElmerParseError("field '{0}' not in VTU".format(field_name))
    sel = mesh["lines"][mesh["line_body"] == boundary_id]
    if not len(sel):
        raise ElmerParseError(
            "boundary id {0} has no line elements (have ids: {1})".format(
                boundary_id, sorted(set(mesh["line_body"].tolist()))))
    p = mesh["points"] * coord_scale
    a, b = p[sel[:, 0]], p[sel[:, 1]]
    length = np.sqrt(np.sum((b - a) ** 2, axis=1))
    r_bar = 0.5 * (a[:, 0] + b[:, 0])
    f_bar = 0.5 * (field[sel[:, 0]] + field[sel[:, 1]]) - offset
    return float(np.sum(2.0 * math.pi * r_bar * f_bar * length))


def field_at(mesh, r_mm, z_mm, field_name):
    """Nodal field value(s) at the mesh node nearest (r, z) in mm."""
    import numpy as np

    p = mesh["points"]
    idx = int(np.argmin((p[:, 0] - r_mm) ** 2 + (p[:, 1] - z_mm) ** 2))
    field = mesh["point_data"].get(field_name)
    if field is None:
        raise ElmerParseError("field '{0}' not in VTU".format(field_name))
    return field[idx]
