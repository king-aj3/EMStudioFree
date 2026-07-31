# SPDX-License-Identifier: LGPL-2.1-or-later
"""VTU writers + FreeCAD 3D-viewport display for EMStudio results.

Turns results into objects in FreeCAD's own 3D view — fully rotatable/zoom/pan/tilt
with the design geometry in context — via ``Fem::FemPostPipeline`` (verified to read
hand-written VTU with scalar point data):

* radiation-pattern **gain balloon** (r ~ normalized gain, colored by dBi),
* **wire currents** (the wire path colored by |I|),
* **near-field plane** (the |E| cut plane as a colored surface).

The writers are Qt-free and FreeCAD-free (plain XML), unit-testable headlessly; only
``show_in_freecad`` needs FreeCAD.
"""

from __future__ import annotations

import math
import os

import numpy as np


# ------------------------------------------------------------------ XML plumbing
def _vtu(points, cells, cell_type, scalars):
    """Assemble a VTU (UnstructuredGrid) document.

    :param points: (N,3) floats.
    :param cells: list of index tuples (all of the same VTK cell type).
    :param cell_type: VTK type id (5=triangle, 4=polyline, 9=quad).
    :param scalars: dict name -> (N,) floats (point data; first is the default).
    """
    points = np.asarray(points, dtype=float)
    pts_txt = " ".join("{0:.6g} {1:.6g} {2:.6g}".format(*p) for p in points)
    conn = " ".join(" ".join(str(i) for i in c) for c in cells)
    offsets = []
    off = 0
    for c in cells:
        off += len(c)
        offsets.append(str(off))
    types = " ".join(str(cell_type) for _ in cells)

    arrays = []
    names = list(scalars)
    for name in names:
        vals = np.asarray(scalars[name], dtype=float)
        arrays.append(
            '<DataArray type="Float32" Name="{0}" format="ascii">{1}</DataArray>'.format(
                name, " ".join("{0:.6g}".format(v) for v in vals)
            )
        )
    return (
        '<?xml version="1.0"?>\n'
        '<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">\n'
        "<UnstructuredGrid><Piece NumberOfPoints=\"{np}\" NumberOfCells=\"{nc}\">\n"
        "<Points><DataArray type=\"Float32\" NumberOfComponents=\"3\" format=\"ascii\">"
        "{pts}</DataArray></Points>\n"
        "<Cells>\n"
        "<DataArray type=\"Int32\" Name=\"connectivity\" format=\"ascii\">{conn}</DataArray>\n"
        "<DataArray type=\"Int32\" Name=\"offsets\" format=\"ascii\">{offs}</DataArray>\n"
        "<DataArray type=\"UInt8\" Name=\"types\" format=\"ascii\">{types}</DataArray>\n"
        "</Cells>\n"
        "<PointData Scalars=\"{first}\">\n{arrays}\n</PointData>\n"
        "</Piece></UnstructuredGrid></VTKFile>\n"
    ).format(np=len(points), nc=len(cells), pts=pts_txt, conn=conn,
             offs=" ".join(offsets), types=types, first=names[0],
             arrays="\n".join(arrays))


# ------------------------------------------------------------------ pattern balloon
def auto_radius_mm(extent_mm, fraction=0.5, minimum_mm=50.0):
    """A balloon radius that reads well beside geometry ``extent_mm`` across.

    The fixed 100 mm default is right for a single patch and useless for an
    8-element array 450 mm wide — the balloon disappears inside its own antenna.
    Scale with the geometry instead, with a floor so a tiny (or degenerate)
    extent still yields something visible rather than a point at the origin.
    """
    return max(float(minimum_mm), float(fraction) * abs(float(extent_mm)))


def write_pattern_vtu(farfield, path, radius_mm=100.0, floor_db=-30.0,
                      center_mm=(0.0, 0.0, 0.0)):
    """Gain balloon: r = normalized (gain - floor), colored by gain in dBi.

    Needs a far field sampled over a (theta, phi) GRID (full-sphere sweeps from
    v0.7 solvers). Balloon max radius = ``radius_mm`` in the FreeCAD view.

    ``center_mm`` places the balloon on the radiator's phase centre. It defaults
    to the origin, which is where NEC2 patterns belong; an antenna modelled away
    from the origin needs the real centre, or the overlay sits beside its own
    geometry looking perfectly plausible and meaning nothing.
    """
    ff = farfield
    cx, cy, cz = (float(v) for v in center_mm)
    theta = np.deg2rad(ff.theta)
    phi = np.deg2rad(ff.phi)
    gain = ff.gain  # (Nt, Np) dBi
    g_max = gain.max()
    r_norm = np.clip((gain - (g_max + floor_db)) / (-floor_db), 0.0, 1.0)

    nt, npnts = gain.shape
    pts = np.zeros((nt * npnts, 3))
    scal = np.zeros(nt * npnts)
    for i in range(nt):
        for j in range(npnts):
            r = radius_mm * r_norm[i, j]
            st, ct = math.sin(theta[i]), math.cos(theta[i])
            pts[i * npnts + j] = (cx + r * st * math.cos(phi[j]),
                                  cy + r * st * math.sin(phi[j]),
                                  cz + r * ct)
            scal[i * npnts + j] = gain[i, j]

    cells = []
    closed = abs((ff.phi[-1] + (ff.phi[1] - ff.phi[0])) % 360.0 - ff.phi[0] % 360.0) < 1e-6
    for i in range(nt - 1):
        for j in range(npnts if closed else npnts - 1):
            j2 = (j + 1) % npnts
            a, b = i * npnts + j, i * npnts + j2
            c, d = (i + 1) * npnts + j, (i + 1) * npnts + j2
            cells.append((a, b, d))
            cells.append((a, d, c))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_vtu(pts, cells, 5, {"Gain_dBi": scal}))
    return path


# ------------------------------------------------------------------ wire currents
def write_currents_vtu(currents, path):
    """The wire run as a polyline, colored by |I| (mA)."""
    pos = np.asarray(currents["pos_m"]) * 1e3  # mm for FreeCAD
    i_ma = np.asarray(currents["i_mag"]) * 1e3
    cells = [tuple(range(len(pos)))]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_vtu(pos, cells, 4, {"Current_mA": i_ma}))
    return path


# ------------------------------------------------------------------ field plane
def write_field_plane_vtu(nearfield, path):
    """The near-field |E| cut plane as a colored quad surface (linear + dB fields)."""
    nf = nearfield
    plane = str(nf.get("plane", "XY"))
    ax_names = {"XY": ("x", "y"), "XZ": ("x", "z"), "YZ": ("y", "z")}[plane]
    a1 = np.asarray(nf[ax_names[0]]) * 1e3  # mm
    a2 = np.asarray(nf[ax_names[1]]) * 1e3
    e = np.asarray(nf["e_mag"])
    if e.shape != (len(a1), len(a2)):
        e = e.T
    fixed_name = ({"x", "y", "z"} - set(ax_names)).pop()
    fixed_val = float(np.asarray(nf[fixed_name]).ravel()[0]) * 1e3

    n1, n2 = len(a1), len(a2)
    pts = np.zeros((n1 * n2, 3))
    for i in range(n1):
        for j in range(n2):
            coord = {ax_names[0]: a1[i], ax_names[1]: a2[j], fixed_name: fixed_val}
            pts[i * n2 + j] = (coord["x"], coord["y"], coord["z"])
    e_flat = e.reshape(-1)
    e_db = 20.0 * np.log10(np.maximum(e_flat / max(e_flat.max(), 1e-30), 1e-4))
    cells = []
    for i in range(n1 - 1):
        for j in range(n2 - 1):
            a, b = i * n2 + j, i * n2 + j + 1
            c, d = (i + 1) * n2 + j + 1, (i + 1) * n2 + j
            cells.append((a, b, c, d))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_vtu(pts, cells, 9, {"E_dB_rel_max": e_db, "E_mag": e_flat}))
    return path


# ------------------------------------------------------------------ FreeCAD display
def show_pattern(farfield, label, extent_mm=None, center_mm=(0.0, 0.0, 0.0),
                 floor_db=-30.0, doc=None, workdir=None, transparency=0):
    """Write a gain balloon and load it straight into the FreeCAD 3-D view.

    The one call a dialog needs: ``extent_mm`` sizes the balloon against the
    geometry it has to sit beside (see ``auto_radius_mm``), and ``center_mm``
    puts it on the radiator. Omitting both reproduces the historical fixed
    100 mm balloon at the origin.
    """
    import tempfile

    if not workdir or not os.path.isdir(workdir):
        workdir = tempfile.mkdtemp(prefix="emstudio_vis_")
    radius = auto_radius_mm(extent_mm) if extent_mm else 100.0
    path = write_pattern_vtu(farfield, os.path.join(workdir, "pattern3d.vtu"),
                             radius_mm=radius, floor_db=floor_db,
                             center_mm=center_mm)
    return show_in_freecad(path, label, doc, transparency=transparency)


def show_in_freecad(vtu_path, label, doc=None, transparency=0):
    """Load a VTU into the active document as a colored FemPostPipeline surface.

    The object lives in FreeCAD's 3D view: rotate/zoom/pan/tilt with the standard
    navigation, colored by the VTU's default scalar field.
    """
    import FreeCAD

    if doc is None:
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()
    obj = doc.addObject("Fem::FemPostPipeline", "EMResult")
    obj.Label = label
    obj.read(vtu_path)
    if FreeCAD.GuiUp:
        try:
            obj.ViewObject.DisplayMode = "Surface"
            # Colour by the VTU's own scalar field. This used to read the
            # property into a local and throw it away, so every overlay rendered
            # flat grey with a colour legend beside it that explained nothing —
            # the one thing the overlay exists to show.
            #
            # `Field` is an ENUMERATION: reading it returns the CURRENT value (a
            # string), not the choices, so list() on it yields that string's
            # characters. The choices come from getEnumerationsOfProperty.
            choices = [f for f in
                       (obj.ViewObject.getEnumerationsOfProperty("Field") or [])
                       if f and f != "None"]
            if choices:
                obj.ViewObject.Field = choices[0]
            if transparency:
                obj.ViewObject.Transparency = int(transparency)
        except Exception:
            pass
    doc.recompute()
    return obj
