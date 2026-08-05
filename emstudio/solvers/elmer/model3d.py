# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD analysis -> model3d dict for the 3-D WhitneyAV magnetics chain.

Unlike the axisymmetric extractor (``model.py``), the 3-D path accepts
ARBITRARY solids: every referenced solid is exported as a BREP (mm) and
meshed conformally by ``gmsh_3d`` (Merge + BooleanFragments, tag-stable —
bodies must be interior/disjoint). The deck runs in mm with ``Coordinate
Scaling`` and reverts the VTU to mm so fields overlay the geometry
(equivalence to the validated meters decks probed at 0.05 %, 2026-07-17).

Scope (v0.56 GUI slice): **3-D Magnetostatic (DC)** — closed coils driven
by signed ampere-turns (CoilSolver), linear materials (µr), B-field VTU +
solver diagnostics. No eddy/thermal/B-H quantities at DC (clear errors);
the transient 3-D drive stays engine-level (see writer3d/TEAM-7 gate).

The closed-coil circulation SENSE is mesh-arbitrary (CoilSolver picks
internal fixing nodes — pinned de-risk pitfall): if the field comes out
inverted, toggle the Coil's ``Reversed`` property.

FreeCAD imports stay inside functions (headless-importable).
"""
from __future__ import annotations

import math
import os


class Axi3DModelError(ValueError):
    """The analysis cannot be expressed as a 3-D magnetostatic model."""


def _export_solid(shape, name, workdir):
    """Export one solid as BREP (mm). Returns (path, bbox_mm)."""
    path = os.path.join(workdir, "body_{0}.brep".format(name))
    shape.exportBrep(path)
    bb = shape.BoundBox
    return path, (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)


def _auto_lc_mm(shape, bbox):
    """Default body mesh size in mm. Returns ``(lc, feature_mm_or_None)``.

    The old default was ``min(bbox side)/10``, which describes the body's
    ENVELOPE, not the thing that has to be resolved. On the real user helix
    that is ~22 mm — COARSER than the 20 mm conductor it is meshing, so the
    conductor got barely one element across it and the CoilSolver's stranded
    normalization degrades (the writer's own note asks for 2-3 elements across
    the coil section).

    ``min_feature_mm`` recovers the real feature size from volume/surface
    (2V/A -> a rod's radius, a plate's thickness); it reads 9.22 mm on that
    helix against a true 19.98 mm across flats, i.e. the conservative half.
    Using it puts ~2 elements across the conductor.

    The finer of the two is taken, so this can only REFINE an existing
    default, never coarsen one.
    """
    min_dim = min(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2])
    envelope = max(min_dim / 10.0, 1.0)
    try:
        from emstudio.geometry.measure import min_feature_mm

        feat = float(min_feature_mm(shape=shape) or 0.0)
    except Exception:                                           # noqa: BLE001
        feat = 0.0
    if feat > 0.0:
        return max(min(envelope, feat), 0.1), feat
    return envelope, None


#: A terminal face is crossed BY the current, so its normal points along the
#: conductor — i.e. roughly PERPENDICULAR to the winding axis (a helix's pitch
#: angle tilts it only a couple of degrees). A closed annular tube also has two
#: equal-area planar faces, but they are its flat ends and their normals lie
#: ALONG the axis. Without this test the shipped 3-D Solenoid template — a
#: genuinely closed tube — is reported as having "two free ends", which
#: gui_smoke caught. 0.5 sits far from both cases (helix ~0.03, tube 1.0).
_TERMINAL_AXIS_DOT_MAX = 0.5


def _faces_look_like_terminals(caps, normal):
    """True when a pair of end caps is really the conductor's two TERMINALS.

    Deliberately FreeCAD-free — it only reads ``.x/.y/.z`` off whatever
    ``normalAt`` returns, so the rule can be gated without FreeCAD present.
    """
    try:
        na = math.sqrt(sum(float(c) ** 2 for c in normal))
        if na <= 0.0:
            return False
        for _area, face in caps:
            n = face.normalAt(0, 0)
            nn = math.sqrt(n.x * n.x + n.y * n.y + n.z * n.z)
            if nn <= 0.0:
                return False
            dot = (n.x * normal[0] + n.y * normal[1] + n.z * normal[2])
            if abs(dot / (nn * na)) > _TERMINAL_AXIS_DOT_MAX:
                return False              # points along the axis: a flat end
        return True
    except Exception:                                           # noqa: BLE001
        return False


def _end_caps_quiet(shape, normal=None):
    """``end_caps`` that never raises — used only to offer a hint.

    With ``normal`` given, only caps that look like real current TERMINALS are
    returned, so a closed tube's flat ends do not masquerade as free ends.
    """
    try:
        from emstudio.geometry import wire_extract

        caps = wire_extract.end_caps(shape)
        if normal is not None and caps \
                and not _faces_look_like_terminals(caps, normal):
            return []
        return caps
    except Exception:                                           # noqa: BLE001
        return []


def _face_bbox(face):
    bb = face.BoundBox
    return (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)


def _resolve_terminals(coil, shape, label, normal):
    """The two terminal faces of an OPEN conductor. Returns (boxes, note, area).

    ``area`` is one terminal cap's area in mm^2 — the conductor's OWN
    cross-section, which is what makes the geometric-turns count below
    possible.

    Uses the coil's explicit ``StartFace``/``EndFace`` if set, otherwise the
    geometric detection in :func:`wire_extract.end_caps` — the smallest pair
    of equal-area planar faces, which is what a swept conductor's caps are
    (proven on the real user helix: exactly 2 found, 282.843 mm^2 each).

    The chosen faces are always REPORTED, never picked silently: which face
    the current enters through is a modelling decision the user is entitled
    to audit, and this project's stated direction is to explain rather than
    to be quietly clever.
    """
    from emstudio.geometry import wire_extract

    faces = []
    for prop in ("StartFace", "EndFace"):
        link = getattr(coil, prop, None)
        if not link:
            continue
        obj, subs = link
        subs = [s for s in (subs or []) if s.startswith("Face")]
        if len(subs) != 1:
            raise Axi3DModelError(
                "coil '{0}': {1} must reference exactly ONE face".format(
                    label, prop))
        faces.append(obj.Shape.getElement(subs[0]))
    if faces and len(faces) != 2:
        raise Axi3DModelError(
            "coil '{0}': set BOTH StartFace and EndFace, or neither (an open "
            "conductor has two ends, and guessing the other one is exactly "
            "the kind of silent choice that produces a wrong field)".format(
                label))

    if faces:
        how = "named by StartFace/EndFace"
    else:
        caps = wire_extract.end_caps(shape)
        if len(caps) != 2:
            raise Axi3DModelError(
                "coil '{0}' is marked OPEN, but its solid has no pair of end "
                "faces to drive it through ({1} candidate(s) found). An open "
                "coil is driven by Dirichlet conditions on its two terminal "
                "faces, so they must exist. If the conductor really is a "
                "closed loop, tick Closed; otherwise name the two faces "
                "explicitly in StartFace/EndFace.".format(label, len(caps)))
        if not _faces_look_like_terminals(caps, normal):
            raise Axi3DModelError(
                "coil '{0}' is marked OPEN, but the only pair of end faces "
                "found points ALONG the winding axis — those are a closed "
                "ring's flat ends, not current terminals (current crosses a "
                "terminal, so its normal runs along the conductor). Either "
                "the coil really is closed (tick Closed), the Axis is wrong, "
                "or the two real ends must be named in "
                "StartFace/EndFace.".format(label))
        faces = [caps[0][1], caps[1][1]]
        how = "auto-detected as the smallest pair of equal-area planar faces"

    boxes = {"start": _face_bbox(faces[0]), "end": _face_bbox(faces[1])}
    note = ("coil '{0}': OPEN conductor — terminal faces {1}. "
            "Start: area {2:.4g} mm^2 at ({3:.1f}, {4:.1f}, {5:.1f}); "
            "End: area {6:.4g} mm^2 at ({7:.1f}, {8:.1f}, {9:.1f}). Current "
            "enters through Start and leaves through End; swap them (or set "
            "Reversed) if the field comes out inverted.".format(
                label, how,
                float(faces[0].Area), faces[0].CenterOfMass.x,
                faces[0].CenterOfMass.y, faces[0].CenterOfMass.z,
                float(faces[1].Area), faces[1].CenterOfMass.x,
                faces[1].CenterOfMass.y, faces[1].CenterOfMass.z))
    return boxes, note, float(faces[0].Area)


def _turns_from_areas(section_area_mm2, cap_area_mm2):
    """Winding count implied by a half-plane section and one cap. Ratio only."""
    if not section_area_mm2 or not cap_area_mm2 or float(cap_area_mm2) <= 0.0:
        return None
    turns = float(section_area_mm2) / float(cap_area_mm2)
    return turns if turns > 0.0 else None


#: Azimuths sampled when counting how many times a conductor winds. A single
#: half-plane QUANTIZES: it is crossed a whole number of times, so a 6.44-turn
#: helix reads 7 at some azimuths and 6 at others (measured on the fixture:
#: 7,6,6,6,6,6,6,6,6,6,7,7,7,7,7,7). The mean over uniformly spaced azimuths
#: is the true count; the residue is bounded by ~0.5/samples of a turn, and 16
#: gave 6.4375 against the parametric truth 6.43588 (0.025 %) for 2.8 s.
_TURN_SAMPLES = 16


def _measure_geometric_turns(shape, normal, cap_area_mm2,
                             samples=_TURN_SAMPLES):
    """How many times the conductor itself winds about its axis, or None.

    One terminal cap is ONE turn's cross-section, and a half-plane through
    the axis is crossed once per turn — so the ratio counts the winding the
    SOLID already carries: ~6.44 on the real user helix, 1.0 on a C-shape.

    This matters because Elmer means different things by ``Desired Coil
    Current`` in its two branches, and the difference is silent. MEASURED
    2026-08-05 on the fixture: requesting 100 on the OPEN branch put 100 A in
    the CONDUCTOR, and its 6.44 geometric turns delivered ~644 ampere-turns —
    the field landed 0.72 % from the finite-solenoid closed form for 644, and
    6.39x above the one for 100. The CLOSED branch normalizes over a
    half-plane instead, which counts those turns itself, so the same request
    means 100 ampere-turns there.

    Returns None if the sections cannot be built — the caller then says
    nothing rather than printing a fabricated turn count.
    """
    try:
        import FreeCAD
        import Part

        n = FreeCAD.Vector(*normal).normalize()
        bb = shape.BoundBox
        reach = bb.DiagonalLength * 2.0 + 10.0
        centre = bb.Center
        seed = FreeCAD.Vector(1.0, 0.0, 0.0)
        if abs(seed.dot(n)) > 0.9:
            seed = FreeCAD.Vector(0.0, 1.0, 0.0)
        radial0 = (seed - n * seed.dot(n)).normalize()
        perp = n.cross(radial0)

        counts = []
        for k in range(int(samples)):
            a = 2.0 * math.pi * k / float(samples)
            radial = (radial0 * math.cos(a) + perp * math.sin(a)).normalize()
            p0 = centre - n * (reach / 2.0)
            p1 = p0 + n * reach
            p2 = p1 + radial * reach
            p3 = p0 + radial * reach
            face = Part.Face(Part.makePolygon([p0, p1, p2, p3, p0]))
            area = float(shape.common(face).Area)
            t = _turns_from_areas(area, cap_area_mm2)
            if t is not None:
                counts.append(t)
        if not counts:
            return None
        return sum(counts) / float(len(counts))
    except Exception:                                           # noqa: BLE001
        return None


def _coil_section_area_m2(shape, normal):
    """Conductor area cut by a half-plane containing the winding axis, in m^2.

    This is the quantity that makes the delivered-current check exact for ANY
    winding: current circulates about the axis, so every turn crosses such a
    half-plane exactly once, and

        delivered ampere-turns = J_avg  x  (this area)

    which is directly comparable with the REQUESTED ampere-turns. Measured
    2026-08-05: a closed ring returns 99.98 % of requested, an open 6.4-turn
    helix 5.2 % — a 19x separation, so the check discriminates with a wide
    margin and cannot false-positive on real geometry. (The
    obvious alternative, an Euler-characteristic/genus test, was tried FIRST
    and rejected: it calls EMStudio's own closed template tube genus-0,
    because OCC's seam edges break the naive V-E+F count.)

    Returns None if the section cannot be built — the caller then skips the
    check rather than inventing a number.
    """
    try:
        import FreeCAD
        import Part

        n = FreeCAD.Vector(*normal).normalize()
        bb = shape.BoundBox
        reach = bb.DiagonalLength * 2.0 + 10.0
        centre = bb.Center
        # A radial direction perpendicular to the axis.
        seed = FreeCAD.Vector(1.0, 0.0, 0.0)
        if abs(seed.dot(n)) > 0.9:
            seed = FreeCAD.Vector(0.0, 1.0, 0.0)
        radial = (seed - n * seed.dot(n)).normalize()
        # Half-plane: from the axis outward, spanning the full axial extent.
        origin = centre - n * (reach / 2.0)
        face = Part.makePlane(reach, reach / 2.0, origin, n.cross(radial))
        # makePlane's local axes are awkward to reason about; build explicitly.
        p0 = centre - n * (reach / 2.0)
        p1 = p0 + n * reach
        p2 = p1 + radial * reach
        p3 = p0 + radial * reach
        face = Part.Face(Part.makePolygon([p0, p1, p2, p3, p0]))
        sect = shape.common(face)
        area = float(sect.Area)
        return (area * 1e-6) if area > 0.0 else None      # mm^2 -> m^2
    except Exception:
        return None


def build_3d_model(analysis, solver, workdir):
    """Extract the model3d dict (mm units) from a FreeCAD analysis."""
    from emstudio.solvers.elmer.model import AxiModelError, _referenced_solids
    from emstudio.objects import coil as coil_mod
    from emstudio.objects import query

    lc_user = float(solver.MeshSizeBodies.getValueAs("mm")) \
        if hasattr(solver, "MeshSizeBodies") else 0.0
    if bool(getattr(solver, "SolveThermal", False)):
        raise Axi3DModelError(
            "3-D Magnetostatic (DC) has no Joule heating — turn SolveThermal "
            "off (the thermal chain is the axisymmetric Harmonic (AC) path)")

    bodies = []
    used = set()
    geo_owner = set()
    notes = []

    def _name(label):
        base = "".join(c if c.isalnum() else "_" for c in label.lower()).strip("_") or "body"
        if base in ("air", "outer"):
            base += "_body"
        name, i = base, 2
        while name in used:
            name = "{0}{1}".format(base, i)
            i += 1
        used.add(name)
        return name

    try:
        for coil in query.get_coils(analysis):
            if float(coil.PhaseDeg) % 360.0 != 0.0:
                raise Axi3DModelError(
                    "coil '{0}': phase is meaningless at DC — set PhaseDeg 0".format(
                        coil.Label))
            amp_turns = float(coil.Turns) * float(coil.Current.getValueAs("A"))
            if bool(coil.Reversed):
                amp_turns = -amp_turns
            if amp_turns == 0.0:
                raise Axi3DModelError(
                    "coil '{0}' carries no current (Turns x Current = 0)".format(
                        coil.Label))
            for link_obj, shape in _referenced_solids(coil):
                if link_obj.Name in geo_owner:
                    raise Axi3DModelError(
                        "two objects reference the same solid '{0}'".format(
                            link_obj.Label))
                geo_owner.add(link_obj.Name)
                name = _name(coil.Label)
                path, bb = _export_solid(shape, name, workdir)
                normal = coil_mod.axis_vector(coil)
                closed = bool(getattr(coil, "Closed", True))
                lc_auto, feat = _auto_lc_mm(shape, bb)
                if lc_user <= 0 and feat is not None:
                    notes.append(
                        "coil '{0}': body mesh size defaulted to {1:.3g} mm, "
                        "sized from the conductor's own smallest feature "
                        "({2:.3g} mm from 2V/A) rather than its bounding box "
                        "— the CoilSolver needs 2-3 elements across the "
                        "section. Set MeshSizeBodies to override.".format(
                            coil.Label, lc_auto, feat))
                body = {
                    "name": name,
                    "shape": {"kind": "brep", "path": path, "bbox": bb},
                    "mu_r": 1.0,
                    "lc": lc_user if lc_user > 0 else lc_auto,
                    "coil": {"amp_turns": amp_turns, "normal": normal,
                             "closed": closed,
                             # Total conductor area cut by a half-plane through
                             # the axis — counts EVERY turn, so
                             # J_avg x this == the delivered ampere-turns.
                             "section_area_m2": _coil_section_area_m2(
                                 shape, normal)},
                }
                if closed:
                    # Free ends on a coil declared closed is the exact
                    # configuration that produced a 160x-wrong field. It is
                    # cheap to spot here, BEFORE a solve that can run for
                    # half an hour, so say so rather than waiting for the
                    # delivered-ampere-turns guard to catch it afterwards.
                    if len(_end_caps_quiet(shape, normal)) == 2:
                        notes.append(
                            "coil '{0}' is marked Closed, but its solid has "
                            "two free ends. If the conductor does not close "
                            "on itself, untick Closed — Elmer is TOLD the "
                            "path is closed and believes it, and an open one "
                            "silently under-delivers current.".format(
                                coil.Label))
                else:
                    boxes, note, cap_mm2 = _resolve_terminals(
                        coil, shape, coil.Label, normal)
                    body["terminals"] = boxes
                    notes.append(note)
                    # One terminal cap IS the conductor's own cross-section —
                    # the section Elmer normalizes on the open branch, and so
                    # the one the delivery guard must compare against.
                    body["coil"]["cap_area_m2"] = cap_mm2 * 1e-6
                    g = _measure_geometric_turns(shape, normal, cap_mm2)
                    body["coil"]["turns_geometric"] = g
                    if g is not None:
                        notes.append(
                            "coil '{0}': the SOLID itself winds {1:.4g} "
                            "time(s) about the axis, and on the open branch "
                            "Elmer drives {2:.6g} A through the conductor — "
                            "so the model delivers about {3:.6g} "
                            "ampere-turns.".format(
                                coil.Label, g, amp_turns, amp_turns * g))
                        # The double-count. Turns is documented as "turns
                        # wound through this cross-section", which is 1 for a
                        # single drawn conductor; the winding count is already
                        # in the geometry. Multiplying the two silently scales
                        # every field by Turns.
                        if int(coil.Turns) > 1 and g > 1.5:
                            notes.append(
                                "coil '{0}': POSSIBLE DOUBLE COUNT — Turns is "
                                "{1} AND the solid already winds {2:.3g} "
                                "times, so the drive is being multiplied "
                                "twice ({3:.6g} ampere-turns). For a single "
                                "drawn conductor set Turns = 1 and let the "
                                "geometry supply the turns; use Turns > 1 "
                                "only when ONE cross-section carries that "
                                "many strands.".format(
                                    coil.Label, int(coil.Turns), g,
                                    amp_turns * g))
                bodies.append(body)

        for mat in query.get_materials(analysis):
            if list(getattr(mat, "BHCurveB", None) or []):
                raise Axi3DModelError(
                    "material '{0}': nonlinear B-H is not wired for the 3-D "
                    "chain yet — use the axisymmetric Static (DC) analysis".format(
                        mat.Label))
            if float(getattr(mat, "ConductivityTempCoeff", 0.0) or 0.0) != 0.0:
                raise Axi3DModelError(
                    "material '{0}': σ(T) needs the axisymmetric thermal "
                    "chain".format(mat.Label))
            mu_r = float(getattr(mat, "RelPermeability", 1.0) or 1.0)
            sigma = float(getattr(mat, "Conductivity", 0.0) or 0.0)
            for link_obj, shape in _referenced_solids(mat):
                if link_obj.Name in geo_owner:
                    continue  # material on a coil body: stranded, µr only
                geo_owner.add(link_obj.Name)
                name = _name(mat.Label)
                path, bb = _export_solid(shape, name, workdir)
                bodies.append({
                    "name": name,
                    "shape": {"kind": "brep", "path": path, "bbox": bb},
                    "mu_r": mu_r, "sigma": sigma,
                    "lc": lc_user if lc_user > 0 else _auto_lc_mm(shape, bb)[0],
                })
    except AxiModelError as exc:  # reference errors from _referenced_solids
        raise Axi3DModelError(str(exc))

    if not any(b.get("coil") for b in bodies):
        raise Axi3DModelError(
            "no coil excitation — add a Coil referencing a closed loop solid")

    # air: pad the body extents; the A=0 truncation UNDERESTIMATES the field
    # (~-0.22*(R/R_box)^2, pinned pitfall) so the default is generous
    extent = max(max(b["shape"]["bbox"][3 + k] - b["shape"]["bbox"][k]
                     for k in range(3)) for b in bodies)
    domain_scale = float(getattr(solver, "DomainScale", 8.0) or 8.0)
    pad = 0.5 * max(domain_scale, 8.0) * extent
    return {
        "bodies": bodies,
        "air": {"kind": "pad", "pad": pad},
        "lc_air": pad / 4.0,
        "units_mm": True,
        # Modelling decisions taken on the user's behalf. run3d surfaces these
        # with the solver's own warnings — the choice of terminal faces is not
        # something to make silently.
        "notes": notes,
    }


def run3d(analysis, solver, workdir=None, line_callback=None):
    """Run the 3-D magnetostatic pipeline. Returns a MagneticsResult."""
    import time

    from emstudio.post.magnetics import MagneticsResult
    from emstudio.solvers.base import make_workdir

    from .runner3d import run_model3d

    t0 = time.time()
    workdir = make_workdir("emstudio_elmer3d_", base=workdir)
    model = build_3d_model(analysis, solver, workdir)
    # run in a SUBDIR: run_model3d wipes-and-recreates its workdir, and the
    # exported BREPs above must survive
    res = run_model3d(model, workdir=os.path.join(workdir, "run"),
                      line_callback=line_callback)

    # wrap as a MagneticsResult so the magnetics dialog works unchanged:
    # one static case (0 Hz), no eddy/thermal quantities, B-field VTU.
    # energy_j and the coil inductance are REAL numbers as of v0.81.0 — they
    # were hard-coded 0.0 placeholders before, which is why nothing noticed
    # that an open coil produced no usable energy at all.
    coils = [b for b in model["bodies"] if b.get("coil")]
    warnings = list(model.get("notes") or []) + list(res["solver_warnings"])
    energy_j = res.get("energy_j")

    inductance_h = None
    if energy_j is not None and len(coils) == 1:
        # W = 1/2 L I^2 with I the SINGLE-TURN equivalent current the FEM
        # actually drives, i.e. the ampere-turns. The caller multiplies by
        # N^2 to get a physical N-turn coil's inductance.
        nia = abs(float(coils[0]["coil"]["amp_turns"]))
        if nia > 0.0:
            inductance_h = 2.0 * float(energy_j) / (nia * nia)

    # --- the delivered-ampere-turns guard -------------------------------
    # Delivered = J_avg x the half-plane section, which counts EVERY turn.
    # It covers BOTH topologies, but what it should be compared AGAINST
    # differs, because Elmer's two branches normalize over different
    # cross-sections (measured — see _measure_geometric_turns):
    #   closed  the half-plane itself, so 'Desired Coil Current' already IS
    #           the ampere-turns and expected == requested;
    #   open    ONE conductor cross-section, so the solid's own geometric
    #           turns multiply the request.
    # Using the closed rule on an open coil would flag a CORRECT 6.44-turn
    # helix as 644 % over-delivered.
    delivered = []
    j_avg = res.get("j_avg") or []
    open_current = res.get("open_coil_current") or []
    for i, b in enumerate(coils):
        coil = b["coil"] or {}
        is_open = not coil.get("closed", True)
        req = abs(float(coil["amp_turns"]))
        turns_g = 1.0
        if is_open:
            # Compare LIKE WITH LIKE. On this branch Elmer normalizes ONE
            # conductor cross-section, so the comparable pair is conductor
            # current against requested current — one terminal cap is that
            # section, and the winding count cancels out of the ratio
            # entirely. (Using the half-plane here instead would compare
            # 7 crossings' worth of current against a 6.44-turn request and
            # report a correct coil as 8.6 % over-delivered.)
            area = coil.get("cap_area_m2") or coil.get("section_area_m2")
            turns_g = float(coil.get("turns_geometric") or 1.0)
        else:
            area = coil.get("section_area_m2")
        if is_open and not (i < len(open_current) and open_current[i]):
            warnings.append(
                "coil '{0}' is OPEN but Elmer reported no normalized coil "
                "current — the drive may not have been applied at all. Check "
                "that the two terminal faces are the conductor's real "
                "ends.".format(b["name"]))
        if area is None or i >= len(j_avg) or req <= 0.0:
            delivered.append(None)
            continue
        got = abs(float(j_avg[i])) * float(area)
        # Reported: the AMPERE-TURNS the model produces. For a closed coil the
        # half-plane already counted the turns; for an open one they multiply
        # in from the geometry.
        delivered.append(got * turns_g)
        frac = got / req
        # Generous bounds on purpose: a healthy closed coil measures 0.9998
        # and a correctly driven open split ring 0.9998, while a mis-declared
        # open helix measured 0.052. Anything outside 0.5..2.0 is a real
        # defect, not mesh coarseness (the writer's own -0.5 % note is far
        # inside this).
        if 0.5 <= frac <= 2.0:
            continue
        if is_open:
            warnings.append(
                "coil '{0}': the solver drove {1:.4g} A through the conductor "
                "against {2:.4g} requested ({3:.1%}). The terminal faces are "
                "the usual cause — check that Start and End are the "
                "conductor's two real ends, and not two faces of the same "
                "cut. Every field value from this run is wrong by roughly "
                "this factor.".format(b["name"], got, req, frac))
        else:
            warnings.append(
                "coil '{0}': the solver delivered {1:.4g} ampere-turns "
                "against {2:.4g} requested ({3:.1%}). The current is not "
                "circulating as asked — the usual cause is an OPEN conductor "
                "(free ends), because the deck declares 'Coil Closed'. Untick "
                "the coil's Closed property, close the current path (add a "
                "return leg), or set the coil's Axis to the real winding "
                "axis. Every field value from this run is wrong by roughly "
                "this factor.".format(b["name"], got, req, frac))

    case = {
        "freq_hz": 0.0,
        "tag": "sweep000",
        "excitation": None,
        "ref_current_a": None,
        "eddy_power_w": 0.0,
        "energy_j": float(energy_j) if energy_j is not None else 0.0,
        "inductance_h": inductance_h,
        "delivered_amp_turns": delivered,
        "body_power_w": {},
        "coil_lambda": {},
        "temperature": {},
        "temp_history": None,
        "solver_warnings": warnings,
        "vtu": res["vtu"],
        "rundir": res["workdir"],
        "duration_s": res["duration_s"],
    }
    body_meta = [{"name": b["name"], "sigma": b.get("sigma", 0.0),
                  "mu_r": b.get("mu_r", 1.0),
                  "is_coil": bool(b.get("coil")),
                  "amp_turns": (b.get("coil") or {}).get("amp_turns")}
                 for b in model["bodies"]]
    result = MagneticsResult([case], [], body_meta, meta={
        "backend": "elmer",
        "mode3d": True,
        "static": True,
        "workdir": res["workdir"],
        "duration_s": time.time() - t0,
        "body_ids": res["body_ids"],
        "norms": res["norms"],
        "analysis": analysis.Label,
    })
    return result
