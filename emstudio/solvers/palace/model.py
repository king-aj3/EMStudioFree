# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD analysis -> cavity model dict for the Palace eigenmode backend.

Geometry class (first slice): a single axis-aligned box solid representing
the cavity INTERIOR (the dielectric/air region); its outer surface is the
PEC wall. The dielectric properties come from the material assigned to that
solid. Anything else raises ``CavityModelError`` with an actionable message.

The box's bounding box gives the cavity dimensions. Box faces are flat, so
``Shape.BoundBox`` is exact even when the GUI has tessellated the shape
(unlike curved surfaces — see the magnetics coil-ring lesson), so a
rectangular cavity is bbox-safe.

FreeCAD imports stay inside functions — the rest of the backend is
importable without FreeCAD (plain-python validation gates).
"""
from __future__ import annotations


class CavityModelError(ValueError):
    """The analysis cannot be expressed as a Palace cavity eigenmode model."""


class CoaxModelError(ValueError):
    """The analysis cannot be expressed as a Palace coax lumped-port model."""


def _box_dims_mm(shape, label):
    """(dx, dy, dz) in mm of an axis-aligned box solid."""
    if not getattr(shape, "Solids", None):
        raise CavityModelError("'{0}' has no solid to mesh".format(label))
    bb = shape.BoundBox
    dx, dy, dz = bb.XLength, bb.YLength, bb.ZLength
    if min(dx, dy, dz) <= 1e-6:
        raise CavityModelError("'{0}' is degenerate (a zero-thickness box?)".format(label))
    # a rectangular cavity: the solid must fill its bounding box (flat faces)
    vol_bb = dx * dy * dz
    if abs(shape.Volume - vol_bb) > 1e-2 * vol_bb:
        raise CavityModelError(
            "'{0}' is not an axis-aligned rectangular box — the Palace cavity "
            "slice supports rectangular cavities (a Part Box); its volume "
            "({1:.4g}) does not fill its bounding box ({2:.4g})".format(
                label, shape.Volume, vol_bb))
    return dx, dy, dz


def build_cavity_model(analysis, solver):
    """Extract the cavity eigenmode model dict from a FreeCAD analysis.

    A rectangular box returns ``{"kind": "box", "size_mm", ...}`` and takes the
    fast box mesher (unchanged). ANY OTHER closed solid (cylinder, sphere,
    chamfered box, …) returns ``{"kind": "brep", "brep_path", "target_ghz", ...}``
    — it is exported to a BREP and meshed with its whole boundary as PEC.
    """
    mat, link_obj, shape = _single_box(analysis)  # the single dielectric solid

    eps_r = float(getattr(mat, "RelPermittivity", 1.0) or 1.0)
    mu_r = float(getattr(mat, "RelPermeability", 1.0) or 1.0)
    loss = float(getattr(mat, "LossTangent", 0.0) or 0.0)
    if eps_r <= 0:
        raise CavityModelError("material '{0}' has non-positive permittivity".format(mat.Label))
    elem_mm = _solver_elem_mm(solver)

    try:
        size_mm = _box_dims_mm(shape, link_obj.Label)
    except CavityModelError:
        # not a box -> general BREP path (any closed solid)
        return _brep_cavity_model(shape, link_obj.Label, eps_r, mu_r, loss, elem_mm)

    return {
        "kind": "box",
        "size_mm": size_mm,
        "eps_r": eps_r,
        "mu_r": mu_r,
        "loss_tan": loss,
        "elem_mm": elem_mm,
    }


def _estimate_target_ghz_bbox(dims_mm, eps_r=1.0):
    """Rough fundamental (GHz) from a bounding box (the box-cavity heuristic).

    Only seeds the shift-invert eigensolver; it just needs to sit below the true
    fundamental. A general solid's exact modes come from the mesh, not this.
    """
    import math

    dims_m = sorted(s * 1e-3 for s in dims_mm)
    a, d = dims_m[-1], dims_m[-2]  # two largest
    f = (299792458.0 / (2.0 * math.sqrt(eps_r))) * math.sqrt((1.0 / a) ** 2 + (1.0 / d) ** 2)
    return f / 1e9


def _brep_cavity_model(shape, label, eps_r, mu_r, loss, elem_mm):
    """General closed solid -> BREP model dict (bbox-seeded target + mesh size)."""
    import os
    import tempfile

    bb = shape.BoundBox
    dims = (bb.XLength, bb.YLength, bb.ZLength)
    if min(dims) <= 1e-6:
        raise CavityModelError("'{0}' is degenerate (a zero-thickness solid?)".format(label))
    # target just below the fundamental (bbox estimate * 0.9 for margin, since a
    # curved solid's bbox is only approximate); mesh capped so curved faces are
    # resolved (a raw BREP carries no size, unlike a box).
    target_ghz = _estimate_target_ghz_bbox(dims, eps_r) * 0.9
    if not elem_mm:
        elem_mm = min(dims) / 6.0
    fd, brep_path = tempfile.mkstemp(suffix=".brep", prefix="emstudio_cav_")
    os.close(fd)
    shape.exportBrep(brep_path)
    return {
        "kind": "brep",
        "brep_path": brep_path,
        "target_ghz": target_ghz,
        "eps_r": eps_r,
        "mu_r": mu_r,
        "loss_tan": loss,
        "elem_mm": elem_mm,
    }


def _solver_elem_mm(solver):
    if hasattr(solver, "MeshSize"):
        try:
            elem = float(solver.MeshSize.getValueAs("mm"))
            return elem if elem > 0 else None
        except Exception:
            return None
    return None


def _single_box(analysis):
    """The one dielectric box solid of the analysis: (mat, link_obj, shape)."""
    from emstudio.objects import query

    solids = []
    for mat in query.get_materials(analysis):
        for link_obj, shape, sub in query.resolved_references(mat):
            if sub in ("", None) and shape is not None and getattr(shape, "Solids", None):
                solids.append((mat, link_obj, shape))
    if not solids:
        raise CavityModelError(
            "no box solid — draw a box (Part Box) and assign it a Dielectric "
            "material (air = permittivity 1)")
    if len(solids) > 1:
        raise CavityModelError(
            "the Palace slice supports ONE box solid; found {0}".format(len(solids)))
    return solids[0]


#: How far to inflate a declared port face's bounding box, as a fraction of the
#: solid's smallest extent. A planar face has ZERO thickness in its normal
#: direction, and gmsh's ``Surface In BoundingBox`` selects surfaces that lie
#: INSIDE the box -- a zero-thickness query is a coin toss against floating
#: point and selects nothing about half the time. This is the same slab trick
#: the inferred path already uses (``port_slab_frac``), applied to a face the
#: user picked instead of one we guessed.
_PORT_SLAB_FRAC = 0.02


def declared_port_boxes(analysis, shape):
    """Selection boxes for the ports the DOCUMENT declares, or None.

    EMStudio has always been able to say which face is a port -- an
    ``EMStudio::LumpedPort`` carries ``References`` (a LinkSubList of
    sub-elements) and a 1-based ``PortNumber``. The driven Palace path simply
    never read them: it inferred TWO ports from the longest bounding-box axis,
    which is why every GUI-driven solve was a 2-port even though the engine
    below is N-port end to end.

    Returns a list of ``(xmin, ymin, zmin, xmax, ymax, zmax)`` in mm **ordered
    by PortNumber**, which ``normalise_port_faces`` accepts verbatim.

    ⚠ **Order is the port numbering**, and it comes from ``PortNumber`` rather
    than from document order or geometry: the user is the only one who knows
    which physical connector is port 1, and S11 is reported for whichever port
    ends up first.

    Returns ``None`` -- meaning "infer, exactly as before" -- when the document
    declares fewer than two usable port FACES. That is deliberate: a document
    with one lumped port on an *edge* (the NEC2/openEMS shape) must keep
    behaving as it always did, so this cannot regress anything that worked.
    """
    from emstudio.objects import query

    try:
        ports = query.get_ports(analysis)
    except Exception:
        return None
    if len(ports) < 2:
        return None

    bb = getattr(shape, "BoundBox", None)
    if bb is None:
        return None
    slab = max(1e-6, min(bb.XLength, bb.YLength, bb.ZLength) * _PORT_SLAB_FRAC)

    boxes = []
    for port in ports:
        face_bb = None
        for _obj, sub_shape, sub_name in query.resolved_references(port):
            # Faces only. An Edge reference is a lumped/MSL port, not a
            # waveguide mouth, and silently treating one as a wave port would
            # mesh a line as a surface and fail somewhere far from the cause.
            if sub_shape is None or not str(sub_name).startswith("Face"):
                continue
            face_bb = getattr(sub_shape, "BoundBox", None)
            if face_bb is not None:
                break
        if face_bb is None:
            return None                      # incomplete -> infer, do not guess
        boxes.append((face_bb.XMin - slab, face_bb.YMin - slab, face_bb.ZMin - slab,
                      face_bb.XMax + slab, face_bb.YMax + slab, face_bb.ZMax + slab))
    return boxes or None


def build_waveguide_model(analysis, solver):
    """Extract the waveguide model dict for a driven S-parameter solve.

    The propagation axis defaults to the solid's LONGEST dimension (the two faces
    perpendicular to it become the wave ports). An axis-aligned box returns
    ``{"kind": "box", "size_mm", ...}`` (fast box mesher, unchanged); ANY OTHER
    closed solid (circular cylinder, tapered/stepped guide, …) returns
    ``{"kind": "brep", "brep_path", "bbox_mm", ...}`` — exported to a BREP with its
    two end faces tagged as ports and the rest PEC (mirrors the eigenmode BREP
    path).
    """
    mat, link_obj, shape = _single_box(analysis)
    eps_r = float(getattr(mat, "RelPermittivity", 1.0) or 1.0)
    mu_r = float(getattr(mat, "RelPermeability", 1.0) or 1.0)
    loss = float(getattr(mat, "LossTangent", 0.0) or 0.0)
    elem_mm = _solver_elem_mm(solver)

    # The DOCUMENT gets the first word. If it declares port faces, they are
    # honoured and the solve is N-port; otherwise nothing changes and two ports
    # are inferred from the longest axis exactly as before.
    ports = declared_port_boxes(analysis, shape)

    # ⚠ Declared ports FORCE the BREP path even for a plain box. The fast box
    # mesher takes no ``ports`` argument, so routing a declaration through it
    # would drop it on the floor and quietly solve a 2-port -- the worst
    # outcome, because the user asked for something specific and got silence.
    # The BREP mesher handles a box perfectly well; it is only slower.
    if ports:
        return _brep_waveguide_model(shape, link_obj.Label, eps_r, mu_r, loss,
                                     elem_mm, ports=ports)
    try:
        size_mm = _box_dims_mm(shape, link_obj.Label)
    except CavityModelError:
        # not an axis-aligned box -> general BREP driven path (any closed solid)
        return _brep_waveguide_model(shape, link_obj.Label, eps_r, mu_r, loss, elem_mm)

    axis = int(max(range(3), key=lambda i: size_mm[i]))  # longest dim = guide axis
    return {
        "kind": "box",
        "size_mm": size_mm,
        "axis": axis,
        "eps_r": eps_r,
        "mu_r": mu_r,
        "loss_tan": loss,
        "elem_mm": elem_mm,
    }


def _brep_waveguide_model(shape, label, eps_r, mu_r, loss, elem_mm, ports=None):
    """General closed solid -> driven BREP model dict.

    Ports are the two faces perpendicular to the LONGEST bounding-box axis (the
    propagation direction, same rule the box path uses). The full bounding box
    (min+max per axis) is passed to the mesher so it can slab-select the two end
    faces on an arbitrary — possibly off-origin, possibly curved — solid.
    """
    import os
    import tempfile

    bb = shape.BoundBox
    ext = (bb.XLength, bb.YLength, bb.ZLength)
    if min(ext) <= 1e-6:
        raise CavityModelError("'{0}' is degenerate (a zero-thickness solid?)".format(label))
    axis = int(max(range(3), key=lambda i: ext[i]))  # longest = propagation axis
    bbox_mm = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
    if not elem_mm:
        elem_mm = min(ext) / 5.0
    fd, brep_path = tempfile.mkstemp(suffix=".brep", prefix="emstudio_wg_")
    os.close(fd)
    shape.exportBrep(brep_path)
    return {
        "kind": "brep",
        "brep_path": brep_path,
        "axis": axis,
        "bbox_mm": bbox_mm,
        "eps_r": eps_r,
        "mu_r": mu_r,
        "loss_tan": loss,
        "elem_mm": elem_mm,
        # None means "the two ends of `axis`", which is what every existing
        # document means. A list is N explicit selection boxes, in port order.
        "ports": ports,
    }


def _coax_dims_mm(shape, label):
    """(a_mm inner radius, b_mm outer radius, length_mm) of a coaxial annulus along Z.

    The radii come from the CYLINDRICAL FACE radii (``surf.Radius``), NOT from
    ``Shape.BoundBox`` — a coax is curved, so under the real GUI the bbox is
    tessellation-shrunk ~0.1 mm inside the true radius (the coil-ring lesson).
    The length is the axial (Z) extent, which IS bbox-safe because the annular
    end caps are flat.
    """
    import math

    import Part

    radii = set()
    for face in shape.Faces:
        surf = face.Surface
        if isinstance(surf, Part.Cylinder):
            if abs(abs(surf.Axis.z) - 1.0) > 1e-6:
                raise CoaxModelError(
                    "'{0}': the coax slice needs a line coaxial with the global "
                    "Z axis — a cylindrical face is not aligned with Z".format(label))
            center = surf.Center
            if math.hypot(center.x, center.y) > 1e-4:
                raise CoaxModelError(
                    "'{0}': coax not centered on the Z axis (offset {1:.3g} mm)".format(
                        label, math.hypot(center.x, center.y)))
            radii.add(round(surf.Radius, 9))
    if len(radii) < 2:
        raise CoaxModelError(
            "'{0}' is not a coaxial annulus — it needs an inner AND an outer "
            "cylindrical conductor wall (draw a tube: cut an inner cylinder from "
            "an outer one). Found {1} distinct cylindrical radius/radii.".format(
                label, len(radii)))
    bb = shape.BoundBox
    if bb.ZLength <= 1e-6:
        raise CoaxModelError("'{0}' has no length along Z".format(label))
    return min(radii), max(radii), bb.ZLength


def build_coax_model(analysis, solver):
    """Extract the coax model dict from a FreeCAD analysis.

    Returns ``{a_mm, b_mm, length_mm, eps_r, mu_r, loss_tan, elem_mm}``.
    """
    mat, link_obj, shape = _single_box(analysis)  # the single dielectric solid
    a_mm, b_mm, length_mm = _coax_dims_mm(shape, link_obj.Label)

    eps_r = float(getattr(mat, "RelPermittivity", 1.0) or 1.0)
    mu_r = float(getattr(mat, "RelPermeability", 1.0) or 1.0)
    loss = float(getattr(mat, "LossTangent", 0.0) or 0.0)
    if eps_r <= 0:
        raise CoaxModelError(
            "material '{0}' has non-positive permittivity".format(mat.Label))

    return {
        "a_mm": a_mm,
        "b_mm": b_mm,
        "length_mm": length_mm,
        "eps_r": eps_r,
        "mu_r": mu_r,
        "loss_tan": loss,
        "elem_mm": _solver_elem_mm(solver),
    }
