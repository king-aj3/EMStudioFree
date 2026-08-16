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
#: Balloon RADIUS as a multiple of the geometry's largest dimension.
#: 1.0 makes the balloon's DIAMETER twice the model, so it clearly surrounds
#: the antenna instead of sharing its volume.
BALLOON_FRACTION = 1.0

#: Anything whose bounding box exceeds this is construction geometry, not a
#: model: FreeCAD's infinite datum planes/axes measure ~2e100 mm. A real
#: antenna is never a kilometre across in a CAD document, and if one ever is,
#: drawing its pattern balloon is not the pressing problem.
_DATUM_MM = 1.0e6


def auto_radius_mm(extent_mm, fraction=None, minimum_mm=50.0):
    """A balloon radius that reads well AROUND geometry ``extent_mm`` across.

    The fixed 100 mm default was right for a single patch and useless for an
    8-element array 450 mm wide — the balloon disappeared inside its own
    antenna. Scaling with the geometry fixed that only halfway: at the old
    fraction of 0.5 the RADIUS was half the extent, so the balloon's DIAMETER
    exactly equalled the model's own size and it still shared the same volume.
    On a solid helix the coil simply wraps around the balloon and hides it —
    reported 2026-08-05 as "I add the 3D pattern and it is not shown".

    A radius of one full extent puts the whole balloon OUTSIDE the geometry's
    bounding sphere, which is what every EM tool draws and the only way the
    thing is legible without hiding the model. The floor keeps a tiny or
    degenerate extent from collapsing to a point at the origin.
    """
    if fraction is None:
        fraction = BALLOON_FRACTION
    try:
        ext = abs(float(extent_mm))
    except (TypeError, ValueError):
        return float(minimum_mm)
    if not math.isfinite(ext) or ext > 1e12:
        return float(minimum_mm)
    return max(float(minimum_mm), float(fraction) * ext)


def geometry_extent_mm(objects):
    """``(center_mm, extent_mm)`` of the drawable geometry in ``objects``.

    Used to sit a pattern balloon ON its antenna. A far field is referenced to
    the SOLVER's origin, and a template built from x=0 puts that origin at one
    end of the structure — a Yagi's balloon then hangs off the reflector rather
    than covering the array. Directions are unaffected either way; only where the
    plot is drawn changes, so this is presentation, and every EM tool draws it
    over the radiator.

    This is the bounding-box centre, which is NOT the phase centre — the solvers
    do not report one. It is an honest "where the antenna is", not a claim about
    where the fields appear to originate.

    Returns ``(None, None)`` when nothing has a usable bounding box, so a caller
    falls back rather than centring on a point it invented.
    """
    lo = [None, None, None]
    hi = [None, None, None]
    for obj in objects or ():
        # SKIP OUR OWN RESULT OVERLAYS. This walked every object in the
        # document, including the pattern balloons it had itself created on
        # previous clicks — and a balloon is deliberately BIGGER than the
        # geometry. So each "Show in 3D View" sized the new balloon from the
        # last one, compounding on every click: a user testing repeatedly got
        # a balloon at 1.99e+100 mm, far outside Float32, which VTK reads as
        # infinity. The overlay then loads with no field and the FLT_MAX
        # sentinel bounding box, appears in the tree and draws NOTHING.
        # Diagnosed 2026-08-05 from the actual pattern3d.vtu on disk.
        # It works the FIRST time and degrades every time after, which is
        # exactly what makes it look like an unrelated intermittent fault.
        if str(getattr(obj, "TypeId", "")).startswith("Fem::FemPost"):
            continue
        shape = getattr(obj, "Shape", None)
        bb = getattr(shape, "BoundBox", None) if shape is not None else None
        if bb is None or not getattr(bb, "isValid", lambda: False)():
            continue
        # SKIP DATUM / CONSTRUCTION GEOMETRY. A PartDesign Body brings an
        # Origin with X/Y/Z axes and XY/XZ/YZ planes, and FreeCAD gives those
        # INFINITE shapes a bounding box of ~2e100 mm. They pass isValid(), so
        # measuring the document measured 2e100 and the balloon was written
        # with coordinates of 1.99e+100 — outside Float32, read back as
        # infinity, overlay present in the tree and drawing NOTHING.
        # Diagnosed 2026-08-05 from the user's own object list; every earlier
        # reproduction used a plain Part::Feature, which has no Origin, which
        # is exactly why it never reproduced here.
        # Reject PER OBJECT, not by poisoning the whole extent: discarding the
        # measurement entirely just falls back to a fixed default and draws an
        # undersized balloon, which is what the first version of this guard did.
        dims = (bb.XLength, bb.YLength, bb.ZLength)
        if not all(math.isfinite(d) for d in dims) or max(dims) > _DATUM_MM:
            continue
        mins = (bb.XMin, bb.YMin, bb.ZMin)
        maxs = (bb.XMax, bb.YMax, bb.ZMax)
        for i in range(3):
            lo[i] = mins[i] if lo[i] is None else min(lo[i], mins[i])
            hi[i] = maxs[i] if hi[i] is None else max(hi[i], maxs[i])
    if lo[0] is None:
        return None, None
    center = tuple(0.5 * (lo[i] + hi[i]) for i in range(3))
    extent = max(hi[i] - lo[i] for i in range(3))
    # Belt and braces: never hand back a size that cannot survive the Float32
    # the VTU is written in. Anything this large is a bug upstream, and
    # returning None makes the caller fall back to its fixed default rather
    # than writing a file whose coordinates read back as infinity.
    if not math.isfinite(extent) or not all(math.isfinite(c) for c in center) \
            or extent > 1e12:
        return None, None
    return center, extent


class PatternGridError(ValueError):
    """The far field cannot form a drawable 3-D balloon."""


def analysis_geometry(analysis):
    """The objects an analysis actually references (materials + ports).

    The pattern belongs to ONE antenna. Measuring the whole document put the
    balloon on the bounding-box centre of everything present — a second
    analysis, a leftover body or an unrelated sketch all moved it. Falling back
    to the document is still right when an analysis references nothing
    resolvable, because a balloon drawn somewhere beats no balloon at all.
    """
    from emstudio.objects import query

    seen, out = set(), []
    for getter in (query.get_materials, query.get_ports):
        for obj in getter(analysis) or ():
            for link_obj, _shape, _sub in query.resolved_references(obj):
                name = getattr(link_obj, "Name", None)
                if name and name not in seen:
                    seen.add(name)
                    out.append(link_obj)
    return out


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
    gain = np.asarray(ff.gain, dtype=float)  # (Nt, Np) dBi

    # A BALLOON NEEDS A GRID, AND A GRID NEEDS TWO ROWS.
    # The cell loop is `for i in range(nt - 1)`, so a single theta row yields
    # points and ZERO CELLS -- a VTU that VTK reads as an empty dataset. It
    # loads without error, shows no field ('choices [None]') and reports the
    # uninitialised FLT_MAX bounding box, so the overlay appears in the tree
    # and draws NOTHING. Reported 2026-08-05 as "I add the 3D pattern and it
    # is not shown"; the object was real and empty. Refusing here is the only
    # honest option: a silent empty overlay is indistinguishable from a bug in
    # the user's model.
    nt, npnts = gain.shape if gain.ndim == 2 else (0, 0)
    if nt < 2 or npnts < 2:
        raise PatternGridError(
            "a 3-D pattern needs a THETA x PHI grid of at least 2x2, but this "
            "far field is {0} x {1}. A balloon cannot be built from a single "
            "cut.\n\nThe solver produced only one {2} row — re-run with a "
            "full-sphere pattern (the RP card must sweep both theta and phi), "
            "or use the 2-D polar plot for a single cut."
            .format(nt, npnts, "theta" if nt < 2 else "phi"))

    # A single NaN would poison g_max and write NaN COORDINATES into the file,
    # which renders as nothing in the same silent way. NEC2 can emit them on a
    # degenerate segment. Drop them to the floor and carry on: losing one
    # sample beats losing the whole picture with no explanation.
    if not np.all(np.isfinite(gain)):
        finite = gain[np.isfinite(gain)]
        if finite.size == 0:
            raise PatternGridError(
                "the far field contains no finite gain values, so there is "
                "nothing to draw. The solve produced no usable pattern.")
        gain = np.where(np.isfinite(gain), gain, finite.min())

    g_max = gain.max()
    r_norm = np.clip((gain - (g_max + floor_db)) / (-floor_db), 0.0, 1.0)

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


#: How see-through the boundary patches are. ⚠ NOT cosmetic: the enclosure
#: patch ENCLOSES the volume field, so at low transparency it hides the very
#: thing the view exists to show — the same trap the pattern balloon hit when
#: it started enclosing its own antenna. High enough to see the field through,
#: low enough that the walls still read as surfaces.
FOAM_PATCH_TRANSPARENCY = 78


def show_foam_case(vtu_path, patch_paths=(), doc=None, label_prefix="Convection",
                   patch_transparency=None):
    """Load an OpenFOAM volume field and its boundary patches. Returns objects.

    The VOLUME goes in first and opaque — it carries the answer (temperature).
    Patches follow, transparent, as context: they show where the cables and the
    enclosure are, which is what makes a plume readable as a plume.

    A patch that fails to load is skipped rather than aborting the lot: a
    missing wall is worth less than the field, and losing the field because one
    surface would not read would be the wrong trade.
    """
    trans = (FOAM_PATCH_TRANSPARENCY if patch_transparency is None
             else patch_transparency)
    objs = [show_in_freecad(vtu_path, "{0} field".format(label_prefix), doc)]
    for path in patch_paths:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            objs.append(show_in_freecad(
                path, "{0} patch — {1}".format(label_prefix, name), doc,
                transparency=trans))
        except Exception:                      # noqa: BLE001 — context only
            continue
    return objs


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
