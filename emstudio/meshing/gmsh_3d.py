# SPDX-License-Identifier: LGPL-2.1-or-later
"""Gmsh 3-D multi-body CONFORMAL meshing for the Elmer WhitneyAV chain.

Meshes N solid bodies (OpenCASCADE primitives and/or imported BREPs) inside
an auto- or user-sized air domain into tetrahedra, with one Physical Volume
per body (+ ``air``) and the outer skin as Physical Surface ``outer`` —
ElmerGrid then names them in ``mesh.names``. Conformality across body/air
interfaces comes from ``BooleanFragments`` (verified: TEAM-7 + the analytic
coil probes, 2026-07-16).

Recipes this module encodes (all probe-verified — keep them):

* ``BooleanFragments`` RENUMBERS volume tags — bodies are re-identified
  AFTER fragmenting with ``Volume In BoundingBox`` on each body's own
  (padded) bounding box. Bodies must therefore be pairwise disjoint and
  their padded bounding boxes must not fully contain another body.
* The mesh-size tiering only works with ``Mesh.MeshSizeExtendFromBoundary
  = 0`` + a ``Min``-combined field list — gmsh's defaults otherwise flood
  the air with body-sized tets (or vice versa).
* Two probe-validated field styles: per-body ``Box`` fields (TEAM-7 tier)
  and ``Distance``+``Threshold`` off body surfaces / embedded curves (the
  sub-percent analytic tier). The default is a Box field per body.
* Evaluation polylines are embedded as NON-physical ``Curve In Volume``
  curves in the air region: mesh nodes land on the line (smooth SaveLine
  interpolation) without generating Elmer boundary elements.
* ``Mesh.OptimizeNetgen`` is NOT compiled into gmsh 4.12 — use only
  ``Mesh.Optimize = 1``.

Units: METERS (the WhitneyAV decks carry no ``Coordinate Scaling``; this
differs from the mm-based axisymmetric mesher — deliberate, matching the
validated 3-D probe decks). Qt-free and FreeCAD-free (subprocess to gmsh).

Body shape descriptors (``body["shape"]``):

``{"kind": "box", "origin": (x,y,z), "size": (dx,dy,dz)}``
``{"kind": "tube", "center": (x,y), "r_in": ri, "r_out": ro, "z0": z0, "z1": z1}``
    annular cylinder about a z-parallel axis; ``r_in`` 0 = solid cylinder.
``{"kind": "racetrack", "cx0","cy0","cx1","cy1", "r_in", "r_out", "z0","z1"}``
    rounded-rectangular prism ring (a racetrack coil): the four corner-arc
    centers span the rectangle (cx0,cy0)-(cx1,cy1); the inner window is
    that rectangle padded by ``r_in``, the outer envelope padded by
    ``r_out``. Built as 2 boxes + 4 corner cylinders, outer minus inner.
``{"kind": "hole", ...}``  same kinds with ``"hole": True`` — subtracted
    from the PREVIOUS body in the list (e.g. the TEAM-7 plate hole).
``{"kind": "brep", "path": p, "bbox": (x0,y0,z0,x1,y1,z1), "scale": s}``
    imported solid (FreeCAD ``exportBrep``); ``scale`` rescales at merge
    (1.0 default — pass 0.001 to bring a mm export into a meters model).
    ``bbox`` is in FINAL (post-scale) units and feeds the size fields/air
    sizing only — re-identification after fragmenting uses the CAPTURED
    tag (OCC bboxes of curved imports are loose; see the geo comments).
    The solid must be interior (not touching air boundary or other bodies)
    so fragments leave it uncut and its tag stable.
"""
from __future__ import annotations

import os
import subprocess

from emstudio.setup import solvers as solver_setup


class Mesh3DError(ValueError):
    """The 3-D model cannot be meshed as requested."""


def _shape_bbox(shape):
    k = shape["kind"]
    if k == "box":
        x, y, z = shape["origin"]
        dx, dy, dz = shape["size"]
        return (x, y, z, x + dx, y + dy, z + dz)
    if k == "tube":
        cx, cy = shape["center"]
        r = float(shape["r_out"])
        return (cx - r, cy - r, shape["z0"], cx + r, cy + r, shape["z1"])
    if k == "racetrack":
        r = float(shape["r_out"])
        return (shape["cx0"] - r, shape["cy0"] - r, shape["z0"],
                shape["cx1"] + r, shape["cy1"] + r, shape["z1"])
    if k == "brep":
        return tuple(shape["bbox"])
    raise Mesh3DError("unknown shape kind '{0}'".format(k))


def _emit_shape(w, shape, tag):
    """Emit OCC statements creating ``shape`` into geo variable ``v<tag>()``."""
    k = shape["kind"]
    if k == "box":
        x, y, z = shape["origin"]
        dx, dy, dz = shape["size"]
        w("v{0} = newv; Box(v{0}) = {{{1:.9g}, {2:.9g}, {3:.9g}, {4:.9g}, "
          "{5:.9g}, {6:.9g}}};".format(tag, x, y, z, dx, dy, dz))
        w("v{0}() = {{v{0}}};".format(tag))
        return
    if k == "tube":
        cx, cy = shape["center"]
        z0, z1 = float(shape["z0"]), float(shape["z1"])
        h = z1 - z0
        if h <= 0:
            raise Mesh3DError("tube z1 must exceed z0")
        w("v{0}o = newv; Cylinder(v{0}o) = {{{1:.9g}, {2:.9g}, {3:.9g}, 0, 0, "
          "{4:.9g}, {5:.9g}}};".format(tag, cx, cy, z0, h, float(shape["r_out"])))
        if float(shape.get("r_in", 0.0)) > 0.0:
            w("v{0}i = newv; Cylinder(v{0}i) = {{{1:.9g}, {2:.9g}, {3:.9g}, 0, 0, "
              "{4:.9g}, {5:.9g}}};".format(tag, cx, cy, z0 - 0.001, h + 0.002,
                                           float(shape["r_in"])))
            w("v{0}() = BooleanDifference{{ Volume{{v{0}o}}; Delete; }}"
              "{{ Volume{{v{0}i}}; Delete; }};".format(tag))
        else:
            w("v{0}() = {{v{0}o}};".format(tag))
        return
    if k == "racetrack":
        cx0, cy0, cx1, cy1 = (float(shape[c]) for c in ("cx0", "cy0", "cx1", "cy1"))
        z0, z1 = float(shape["z0"]), float(shape["z1"])
        h = z1 - z0
        r_in, r_out = float(shape["r_in"]), float(shape["r_out"])
        if not (cx1 > cx0 and cy1 > cy0 and h > 0 and r_out > r_in > 0):
            raise Mesh3DError("degenerate racetrack parameters")

        def rounded_rect(sub, rr, zlo, hh):
            # 2 boxes + 4 corner cylinders, unioned (probe recipe)
            w("v{0}{1}b1 = newv; Box(v{0}{1}b1) = {{{2:.9g}, {3:.9g}, {4:.9g}, "
              "{5:.9g}, {6:.9g}, {7:.9g}}};".format(
                  tag, sub, cx0, cy0 - rr, zlo, cx1 - cx0, (cy1 - cy0) + 2 * rr, hh))
            w("v{0}{1}b2 = newv; Box(v{0}{1}b2) = {{{2:.9g}, {3:.9g}, {4:.9g}, "
              "{5:.9g}, {6:.9g}, {7:.9g}}};".format(
                  tag, sub, cx0 - rr, cy0, zlo, (cx1 - cx0) + 2 * rr, cy1 - cy0, hh))
            cyls = []
            for i, (ccx, ccy) in enumerate(((cx0, cy0), (cx1, cy0),
                                            (cx1, cy1), (cx0, cy1))):
                w("v{0}{1}c{2} = newv; Cylinder(v{0}{1}c{2}) = {{{3:.9g}, {4:.9g}, "
                  "{5:.9g}, 0, 0, {6:.9g}, {7:.9g}}};".format(
                      tag, sub, i, ccx, ccy, zlo, hh, rr))
                cyls.append("v{0}{1}c{2}".format(tag, sub, i))
            w("v{0}{1}() = BooleanUnion{{ Volume{{v{0}{1}b1}}; Delete; }}"
              "{{ Volume{{v{0}{1}b2, {2}}}; Delete; }};".format(
                  tag, sub, ", ".join(cyls)))

        rounded_rect("o", r_out, z0, h)
        # inner cutter overshoots 1 mm in z so the difference is clean
        rounded_rect("i", r_in, z0 - 0.001, h + 0.002)
        w("v{0}() = BooleanDifference{{ Volume{{v{0}o()}}; Delete; }}"
          "{{ Volume{{v{0}i()}}; Delete; }};".format(tag))
        return
    if k == "brep":
        path = shape["path"]
        if not os.path.isfile(path):
            raise Mesh3DError("BREP not found: {0}".format(path))
        # capture the merged volume tag by set-difference; optional Dilate
        # rescales (e.g. a FreeCAD mm export into a meters model)
        w("vPre{0}() = Volume{{:}};".format(tag))
        w('Merge "{0}";'.format(os.path.abspath(path)))
        w("v{0}() = Volume{{:}};".format(tag))
        w("v{0}() -= vPre{0}();".format(tag))
        scale = float(shape.get("scale", 1.0))
        if scale != 1.0:
            w("Dilate {{{{0, 0, 0}}, {0:.9g}}} {{ Volume{{v{1}()}}; }}".format(
                scale, tag))
        return
    raise Mesh3DError("unknown shape kind '{0}'".format(k))


def write_geo_3d(bodies, geo_path, air, lc_air, size_fields=None,
                 embed_lines=None):
    """Write the multi-body conformal ``.geo``. Returns ``geo_path``.

    :param bodies: list of dicts ``{name, shape, lc}`` (``hole`` shapes are
        subtracted from the previous body and get no Physical Volume).
    :param air: ``{"kind": "pad", "pad": p}`` (box: union bbox padded by p),
        ``{"kind": "box", "origin": .., "size": ..}`` or
        ``{"kind": "cylinder", "r": R, "z0": z0, "z1": z1}`` (about z at 0,0).
    :param lc_air: far-field mesh size (m).
    :param size_fields: optional explicit field list; default = one Box
        field per body (bbox padded 2·lc, ``Thickness`` 2·lc_air).
        Entries: ``{"kind":"box", lc, box:(x0..z1), thickness}`` or
        ``{"kind":"distance", "body": name|"line:<i>", lc, dist_min, dist_max}``.
    :param embed_lines: ``[((x,y,z),(x,y,z)), ...]`` — non-physical curves
        embedded in the AIR volume (must lie wholly in air).
    """
    lc_air = float(lc_air)
    solids = [b for b in bodies if not b["shape"].get("hole")]
    if not solids:
        raise Mesh3DError("no solid bodies")
    names = [b["name"] for b in solids]
    if len(set(names)) != len(names) or "air" in names or "outer" in names:
        raise Mesh3DError("body names must be unique and not 'air'/'outer'")

    L = []
    w = L.append
    w("// EMStudio 3-D multi-body conformal mesh (WhitneyAV chain) — units: METERS")
    w("// rerun: gmsh -3 -format msh22 <this file> -o out.msh")
    w('SetFactory("OpenCASCADE");')
    w("")

    # ---------- bodies (holes subtract from the previous body) ----------
    tags = []
    prev = None
    for i, b in enumerate(bodies):
        shape = b["shape"]
        if shape.get("hole"):
            if prev is None:
                raise Mesh3DError("a hole shape needs a preceding body")
            _emit_shape(w, dict(shape, hole=False), "h{0}".format(i))
            w("v{0}() = BooleanDifference{{ Volume{{v{0}()}}; Delete; }}"
              "{{ Volume{{vh{1}()}}; Delete; }};".format(prev, i))
            continue
        _emit_shape(w, shape, i)
        tags.append((b["name"], i))
        prev = i
    w("")

    # ---------- air domain ----------
    boxes = [_shape_bbox(b["shape"]) for b in solids]
    lo = [min(bb[k] for bb in boxes) for k in range(3)]
    hi = [max(bb[3 + k] for bb in boxes) for k in range(3)]
    if air.get("kind") == "pad":
        p = float(air["pad"])
        w("vair = newv; Box(vair) = {{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, "
          "{4:.9g}, {5:.9g}}};".format(lo[0] - p, lo[1] - p, lo[2] - p,
                                       hi[0] - lo[0] + 2 * p,
                                       hi[1] - lo[1] + 2 * p,
                                       hi[2] - lo[2] + 2 * p))
    elif air.get("kind") == "box":
        x, y, z = air["origin"]
        dx, dy, dz = air["size"]
        w("vair = newv; Box(vair) = {{{0:.9g}, {1:.9g}, {2:.9g}, {3:.9g}, "
          "{4:.9g}, {5:.9g}}};".format(x, y, z, dx, dy, dz))
    elif air.get("kind") == "cylinder":
        w("vair = newv; Cylinder(vair) = {{0, 0, {0:.9g}, 0, 0, {1:.9g}, "
          "{2:.9g}}};".format(float(air["z0"]),
                              float(air["z1"]) - float(air["z0"]),
                              float(air["r"])))
    else:
        raise Mesh3DError("air kind must be pad/box/cylinder")
    w("")

    # ---------- conformal fragmenting + bbox re-identification ----------
    body_list = ", ".join("v{0}()".format(t) for _, t in tags)
    w("f() = BooleanFragments{ Volume{vair}; Delete; }{ Volume{" + body_list + "}; Delete; };")
    w("")
    w("// re-identify bodies after fragmenting: primitives by (tight) bounding")
    w("// box; merged BREPs by CAPTURED TAG — fragments preserve an UNCUT tool")
    w("// volume's tag (probe-verified), and OCC bboxes of curved imports are")
    w("// LOOSE (B-spline control points reach ~2R), so In BoundingBox misses them")
    w("eps = {0:.9g};".format(min(float(b.get("lc", lc_air)) for b in solids) * 0.25))
    for name, t in tags:
        shape = next(b["shape"] for b in solids if b["name"] == name)
        if shape["kind"] == "brep":
            w("vB{0}() = v{0}();  // tag-stable (interior body, uncut by fragments)".format(t))
            continue
        bb = _shape_bbox(shape)
        w("vB{0}() = Volume In BoundingBox {{{1:.9g}-eps, {2:.9g}-eps, {3:.9g}-eps, "
          "{4:.9g}+eps, {5:.9g}+eps, {6:.9g}+eps}};".format(t, *bb))
    w("vAll() = Volume{:};")
    w("vAir() = vAll();")
    for _, t in tags:
        w("vAir() -= vB{0}();".format(t))
    w("")

    # ---------- embedded evaluation lines (non-physical, in air) ----------
    line_tags = []
    for i, (p0, p1) in enumerate(embed_lines or []):
        w("pl{0}a = newp; Point(pl{0}a) = {{{1:.9g}, {2:.9g}, {3:.9g}}};".format(
            i, *p0))
        w("pl{0}b = newp; Point(pl{0}b) = {{{1:.9g}, {2:.9g}, {3:.9g}}};".format(
            i, *p1))
        w("ll{0} = newl; Line(ll{0}) = {{pl{0}a, pl{0}b}};".format(i))
        w("Curve{{ll{0}}} In Volume{{vAir(0)}};".format(i))
        line_tags.append("ll{0}".format(i))
    w("")

    # ---------- physical groups ----------
    w('Physical Volume("air", 1) = {vAir()};')
    for j, (name, t) in enumerate(tags):
        w('Physical Volume("{0}", {1}) = {{vB{2}()}};'.format(name, j + 2, t))
    w("sOuter() = CombinedBoundary{ Volume{vAll()}; };")
    w('Physical Surface("outer", {0}) = {{sOuter()}};'.format(len(tags) + 2))
    w("")

    # ---------- mesh size fields ----------
    if size_fields is None:
        size_fields = []
        for b in solids:
            lc = float(b.get("lc", lc_air))
            bb = _shape_bbox(b["shape"])
            pad = 2.0 * lc
            size_fields.append({
                "kind": "box", "lc": lc, "thickness": 2.0 * lc_air,
                "box": (bb[0] - pad, bb[1] - pad, bb[2] - pad,
                        bb[3] + pad, bb[4] + pad, bb[5] + pad)})
    fid = 0
    fids = []
    for f in size_fields:
        fid += 1
        if f["kind"] == "box":
            b0 = f["box"]
            w("Field[{0}] = Box;".format(fid))
            w("Field[{0}].VIn = {1:.9g}; Field[{0}].VOut = {2:.9g};".format(
                fid, float(f["lc"]), lc_air))
            w("Field[{0}].XMin = {1:.9g}; Field[{0}].XMax = {2:.9g};".format(
                fid, b0[0], b0[3]))
            w("Field[{0}].YMin = {1:.9g}; Field[{0}].YMax = {2:.9g};".format(
                fid, b0[1], b0[4]))
            w("Field[{0}].ZMin = {1:.9g}; Field[{0}].ZMax = {2:.9g};".format(
                fid, b0[2], b0[5]))
            w("Field[{0}].Thickness = {1:.9g};".format(
                fid, float(f.get("thickness", 2.0 * lc_air))))
        elif f["kind"] == "distance":
            tgt = f["body"]
            w("Field[{0}] = Distance;".format(fid))
            if str(tgt).startswith("line:"):
                w("Field[{0}].CurvesList = {{{1}}};".format(
                    fid, line_tags[int(str(tgt)[5:])]))
                w("Field[{0}].NumPointsPerCurve = 250;".format(fid))
            else:
                t = next(t for n, t in tags if n == tgt)
                w("Field[{0}].SurfacesList = {{Abs(Boundary{{Volume{{vB{1}()}};}})}};".format(fid, t))
                w("Field[{0}].Sampling = 40;".format(fid))
            fid += 1
            w("Field[{0}] = Threshold; Field[{0}].InField = {1};".format(fid, fid - 1))
            w("Field[{0}].SizeMin = {1:.9g}; Field[{0}].SizeMax = {2:.9g};".format(
                fid, float(f["lc"]), lc_air))
            w("Field[{0}].DistMin = {1:.9g}; Field[{0}].DistMax = {2:.9g};".format(
                fid, float(f["dist_min"]), float(f["dist_max"])))
        else:
            raise Mesh3DError("unknown size field kind '{0}'".format(f["kind"]))
        fids.append(fid)
    fid += 1
    w("Field[{0}] = Min; Field[{0}].FieldsList = {{{1}}};".format(
        fid, ", ".join(str(i) for i in fids)))
    w("Background Field = {0};".format(fid))
    w("")
    w("Mesh.MeshSizeMax = {0:.9g};".format(lc_air))
    w("Mesh.MeshSizeFromPoints = 0;")
    w("Mesh.MeshSizeFromCurvature = 0;")
    w("Mesh.MeshSizeExtendFromBoundary = 0;")
    w("Mesh.Algorithm = 6;    // Frontal-Delaunay 2D")
    w("Mesh.Algorithm3D = 1;  // Delaunay")
    w("Mesh.Optimize = 1;     // (OptimizeNetgen is not compiled into gmsh 4.12)")
    w("Mesh.MshFileVersion = 2.2;")

    with open(geo_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return geo_path


def mesh_3d(bodies, workdir, air, lc_air, size_fields=None, embed_lines=None,
            line_callback=None, timeout_s=900):
    """Write ``model3d.geo``, run gmsh -3. Returns the ``.msh`` path."""
    geo = write_geo_3d(bodies, os.path.join(workdir, "model3d.geo"), air,
                       lc_air, size_fields=size_fields, embed_lines=embed_lines)
    msh = os.path.join(workdir, "model3d.msh")
    gmsh = solver_setup.find_backend("gmsh")
    exe = gmsh.path if gmsh.found else "gmsh"
    proc = subprocess.run([exe, "-3", "-format", "msh22", geo, "-o", msh],
                          capture_output=True, text=True, timeout=timeout_s)
    if line_callback is not None:
        for line in (proc.stdout + proc.stderr).splitlines():
            line_callback(line)
    if proc.returncode != 0 or not os.path.isfile(msh):
        raise Mesh3DError("gmsh failed (exit {0}):\n{1}".format(
            proc.returncode, (proc.stderr or proc.stdout)[-2000:]))
    return msh
