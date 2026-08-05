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

import os


class Axi3DModelError(ValueError):
    """The analysis cannot be expressed as a 3-D magnetostatic model."""


def _export_solid(shape, name, workdir):
    """Export one solid as BREP (mm). Returns (path, bbox_mm)."""
    path = os.path.join(workdir, "body_{0}.brep".format(name))
    shape.exportBrep(path)
    bb = shape.BoundBox
    return path, (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)


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
                min_dim = min(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
                normal = coil_mod.axis_vector(coil)
                bodies.append({
                    "name": name,
                    "shape": {"kind": "brep", "path": path, "bbox": bb},
                    "mu_r": 1.0,
                    "lc": lc_user if lc_user > 0 else max(min_dim / 10.0, 1.0),
                    "coil": {"amp_turns": amp_turns, "normal": normal,
                             # Total conductor area cut by a half-plane through
                             # the axis — counts EVERY turn, so
                             # J_avg x this == the delivered ampere-turns.
                             "section_area_m2": _coil_section_area_m2(
                                 shape, normal)},
                })

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
                min_dim = min(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
                bodies.append({
                    "name": name,
                    "shape": {"kind": "brep", "path": path, "bbox": bb},
                    "mu_r": mu_r, "sigma": sigma,
                    "lc": lc_user if lc_user > 0 else max(min_dim / 10.0, 1.0),
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
    warnings = list(res["solver_warnings"])
    energy_j = res.get("energy_j")

    inductance_h = None
    if energy_j is not None and len(coils) == 1:
        # W = 1/2 L I^2 with I the SINGLE-TURN equivalent current the FEM
        # actually drives, i.e. the ampere-turns. The caller multiplies by
        # N^2 to get a physical N-turn coil's inductance.
        nia = abs(float(coils[0]["coil"]["amp_turns"]))
        if nia > 0.0:
            inductance_h = 2.0 * float(energy_j) / (nia * nia)

    # --- the open-coil / under-delivery guard ---------------------------
    delivered = []
    j_avg = res.get("j_avg") or []
    for i, b in enumerate(coils):
        area = (b["coil"] or {}).get("section_area_m2")
        req = abs(float(b["coil"]["amp_turns"]))
        if area is None or i >= len(j_avg) or req <= 0.0:
            delivered.append(None)
            continue
        got = abs(float(j_avg[i])) * float(area)
        delivered.append(got)
        frac = got / req
        # Generous bounds on purpose: a healthy closed coil measures 0.9998,
        # an open one 0.008. Anything outside 0.5..2.0 is a real defect, not
        # mesh coarseness (the writer's own -0.5 % note is far inside this).
        if not (0.5 <= frac <= 2.0):
            warnings.append(
                "coil '{0}': the solver delivered {1:.4g} ampere-turns "
                "against {2:.4g} requested ({3:.1%}). The current is not "
                "circulating as asked — the usual cause is an OPEN conductor "
                "(free ends), because the deck declares 'Coil Closed'. Close "
                "the current path (add a return leg) or set the coil's Axis "
                "to the real winding axis. Every field value from this run "
                "is wrong by roughly this factor.".format(
                    b["name"], got, req, frac))

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
