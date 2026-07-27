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


def build_3d_model(analysis, solver, workdir):
    """Extract the model3d dict (mm units) from a FreeCAD analysis."""
    from emstudio.solvers.elmer.model import AxiModelError, _referenced_solids
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
                bodies.append({
                    "name": name,
                    "shape": {"kind": "brep", "path": path, "bbox": bb},
                    "mu_r": 1.0,
                    "lc": lc_user if lc_user > 0 else max(min_dim / 10.0, 1.0),
                    "coil": {"amp_turns": amp_turns, "normal": (0.0, 0.0, 1.0)},
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
    # coils meta stays EMPTY (L/λ extraction for 3-D coils is a future
    # slice — flux linkage needs the A·J energy integral, not the 2-D
    # cross-section formula).
    case = {
        "freq_hz": 0.0,
        "tag": "sweep000",
        "excitation": None,
        "ref_current_a": None,
        "eddy_power_w": 0.0,
        "energy_j": 0.0,
        "body_power_w": {},
        "coil_lambda": {},
        "temperature": {},
        "temp_history": None,
        "solver_warnings": res["solver_warnings"],
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
