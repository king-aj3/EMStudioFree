# SPDX-License-Identifier: LGPL-2.1-or-later
"""Elmer magnetodynamics pipeline: Prepare -> Mesh -> Solve -> Results.

Pipeline per analysis::

    model  = build_axi_model(analysis, solver)      # FreeCAD layer (model.py)
    result = run_model(model, freqs, ...)           # pure layer (this file)

``run_model`` meshes once (gmsh -> ElmerGrid), then runs one ElmerSolver
case per (frequency, excitation) in parallel (ElmerSolver is
single-threaded for these 2-D cases; the sweep parallelizes across
processes like the FastHenry backend). Each case gets its own directory
with a COPY of the small Elmer mesh, because ResultOutputSolver writes
the VTU into the mesh directory — sharing one mesh across concurrent
runs would collide.

ElmerSolver exits 0 even when the .sif has parse errors (verified v26.2)
— the runner therefore scans the streamed output for ``ERROR::`` and
fails loudly on it.
"""
from __future__ import annotations

import math
import os
import shutil

from emstudio.meshing import gmsh_axi
from emstudio.setup import solvers as solver_setup
from emstudio.solvers.base import SolverError, SolverJob, make_workdir

from . import parser, writer

#: Elmer's axisymmetric CalcFields scalars ("eddy current power",
#: "electromagnetic field energy") are integrated per RADIAN — multiply by
#: 2*pi for the full circumference. Pinned against the analytic Bessel
#: solution by tests/validation/induction_elmer.py (2026-07-05).
AXI_SCALAR_FACTOR = 2.0 * math.pi

_SOLVE_TIMEOUT_S = 3600
_MESH_TIMEOUT_S = 600


def find_elmergrid():
    """ElmerGrid path: sibling of the detected ElmerSolver, else PATH.

    ElmerGrid is a companion tool of the ``elmer`` backend, not a backend
    of its own — it is resolved relative to ElmerSolver rather than via a
    registry entry.
    """
    info = solver_setup.find_backend("elmer")
    if info.found:
        cand = os.path.join(os.path.dirname(info.path), "ElmerGrid")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    which = shutil.which("ElmerGrid")
    if which:
        return which
    raise SolverError(
        "ElmerGrid not found (needed to convert gmsh meshes).\n"
        + solver_setup.install_hint(solver_setup.BACKENDS["elmer"]))


def _resolve_elmersolver():
    info = solver_setup.find_backend("elmer")
    if not info.found:
        raise SolverError(
            "ElmerSolver not found.\n" + solver_setup.install_hint(info.backend))
    return info.path


def _run_case(elmersolver, model, f_hz, tag, excitation, workdir, mesh_src,
              body_ids, boundary_ids, line_callback):
    """One ElmerSolver case in its own directory. Returns the case dict."""
    rundir = os.path.join(workdir, "run_" + tag)
    os.makedirs(rundir, exist_ok=True)
    shutil.copytree(mesh_src, os.path.join(rundir, "mesh"))
    sif = os.path.join(rundir, "case.sif")

    # coupling cases drive the exciter at a nonzero REFERENCE current so L/M/k
    # are extractable even when its operating current is 0 (undriven pickup);
    # equal to the operating current when that is nonzero (identical results).
    ref_current = None
    ref_currents = None
    if tag.startswith("couple_"):
        cname = tag[len("couple_"):]
        op_i = next(b["coil"]["current_a"] for b in model["bodies"]
                    if b.get("coil") and b["name"] == cname)
        ref_current = op_i if op_i > 0 else 1.0
        ref_currents = {cname: ref_current}
    _, bc_sections = writer.write_sif(model, f_hz, sif, body_ids, boundary_ids,
                                      excitation=excitation, ref_currents=ref_currents,
                                      mesh_dir="mesh", vtu_name="case")

    errors = []
    warns = []
    log_path = os.path.join(rundir, "solver.log")
    with open(log_path, "w", encoding="utf-8") as log:
        def _cb(line):
            log.write(line + "\n")
            if "ERROR::" in line:
                errors.append(line)
            # ComputeChange's non-convergence is a WARNING at exit 0 — for a
            # σ(T) deck it is the only signal of a stalled coupling loop or
            # genuine thermal runaway (de-risk probe 2026-07-16)
            if "did not converge" in line.lower():
                warns.append(line)
            if line_callback is not None:
                line_callback("[{0}] {1}".format(tag, line))

        job = SolverJob([elmersolver, "case.sif"], cwd=rundir, line_callback=_cb)
        job.run_blocking(timeout=_SOLVE_TIMEOUT_S)
    if errors:
        # ElmerSolver exits 0 on sif parse errors — treat ERROR:: as fatal
        raise SolverError(
            "ElmerSolver reported errors for case {0}:\n{1}\n(full log: {2})".format(
                tag, "\n".join(errors[:10]), log_path))

    scalars = parser.parse_scalars(os.path.join(rundir, "scalars.dat"))
    vtu = os.path.join(rundir, "mesh", "case_t0001.vtu")
    if not os.path.isfile(vtu):
        raise SolverError("ElmerSolver produced no VTU at {0}".format(vtu))
    mesh = parser.parse_vtu(vtu)

    eddy_per_rad = 0.0
    for key, val in scalars.items():
        if "eddy current power" in key:
            eddy_per_rad = val
    energy_per_rad = 0.0
    for key, val in scalars.items():
        if "field energy" in key:
            energy_per_rad = val

    body_power = {}
    for b in model["bodies"]:
        if (float(b.get("sigma", 0.0)) > 0.0 and not b.get("coil")
                and not model.get("static")):  # DC: no joule-heating field
            body_power[b["name"]] = parser.body_integral(
                mesh, body_ids[b["name"]], "joule heating")
    coil_lambda = {}
    for b in model["bodies"]:
        if b.get("coil"):
            coil_lambda[b["name"]] = parser.flux_linkage(
                mesh, body_ids[b["name"]], b["coil"]["turns"])

    temperature = {}
    thermal = model.get("thermal") or {}
    for name in (thermal.get("bodies") or {}):
        import numpy as np

        temp = mesh["point_data"]["temperature"]
        nodes = np.unique(mesh["triangles"][mesh["tri_body"] == body_ids[name]])
        t_ext = float(thermal.get("t_ext", 293.15))
        h = float(thermal.get("h", 10.0))
        # boundary elements carry GeometryIds = 100 + sif BC section number
        conv_w = h * parser.boundary_integral(
            mesh, 100 + bc_sections["surf_" + name], "temperature", offset=t_ext)
        temperature[name] = {
            "t_max": float(temp[nodes].max()),
            "t_min": float(temp[nodes].min()),
            "t_mean": float(temp[nodes].mean()),
            "conv_power_w": conv_w,  # steady state: equals the body's Joule power
        }

    # transient heating curve (time, max temperature) — one thermal body typical
    temp_history = None
    if (model.get("thermal") or {}).get("transient") and thermal.get("bodies"):
        series = parser.parse_scalars_series(os.path.join(rundir, "scalars.dat"))
        t_col = next((v for k, v in series.items() if "time" in k.lower()), None)
        tmax_col = next((v for k, v in series.items()
                         if "temperature" in k.lower() and "max" in k.lower()), None)
        if t_col and tmax_col:
            temp_history = {"time_s": list(t_col), "t_max_k": list(tmax_col)}

    return {
        "freq_hz": f_hz,
        "tag": tag,
        "solver_warnings": warns,
        "excitation": dict(excitation) if excitation else None,
        "ref_current_a": ref_current,  # coupling reference (None for sweep cases)
        "eddy_power_w": AXI_SCALAR_FACTOR * eddy_per_rad,
        "energy_j": AXI_SCALAR_FACTOR * energy_per_rad,
        "body_power_w": body_power,
        "coil_lambda": coil_lambda,
        "temperature": temperature,
        "temp_history": temp_history,
        "vtu": vtu,
        "rundir": rundir,
        "duration_s": job.duration_s,
    }


def run_model(model, freqs, workdir=None, line_callback=None,
              extract_coupling=True, parallel=True):
    """Run the full pipeline on an axi model dict. Returns a MagneticsResult.

    :param freqs: iterable of frequencies in Hz. Every frequency gets an
        all-coils-excited "sweep" case; when ``extract_coupling`` and the
        model has >= 2 coils, one single-coil "couple_<name>" case per coil
        runs at the FIRST frequency (L/M/k are frequency-independent for
        non-conducting coil systems).
    """
    import time

    from emstudio.post.magnetics import MagneticsResult

    t0 = time.time()
    freqs = [float(f) for f in freqs]
    if not freqs:
        raise SolverError("no frequencies to solve")
    workdir = make_workdir("emstudio_elmer_", base=workdir)
    elmersolver = _resolve_elmersolver()
    elmergrid = find_elmergrid()

    # --- mesh once -------------------------------------------------------
    regions = [{k: b[k] for k in ("name", "r0", "r1", "z0", "z1") } for b in model["bodies"]]
    for reg, b in zip(regions, model["bodies"]):
        if b.get("lc"):
            reg["lc"] = b["lc"]
    msh = gmsh_axi.mesh_axisymmetric(
        regions, workdir, air=model.get("air"), lc_air=model.get("lc_air"),
        domain_scale=model.get("domain_scale", 8.0),
        mesh_grade=model.get("mesh_grade", 0.12), line_callback=line_callback)
    mesh_dir = os.path.join(workdir, "mesh")
    SolverJob([elmergrid, "14", "2", os.path.basename(msh), "-autoclean",
               "-out", "mesh"],
              cwd=workdir, line_callback=line_callback).run_blocking(
                  timeout=_MESH_TIMEOUT_S)
    names_file = os.path.join(mesh_dir, "mesh.names")
    if not os.path.isfile(names_file):
        raise SolverError("ElmerGrid produced no mesh at {0}".format(mesh_dir))
    body_ids, boundary_ids = parser.parse_mesh_names(names_file)

    # --- case list ---------------------------------------------------------
    coils = [b for b in model["bodies"] if b.get("coil")]
    cases = []
    if model.get("static"):
        # DC magnetostatics: one case (tagged sweep000 at 0 Hz so the whole
        # MagneticsResult machinery — L = lambda/I, R = 0 at w = 0 — works
        # unchanged). No coupling extraction: superposition does not hold
        # for a nonlinear B-H solve.
        cases.append((0.0, "sweep000", None))
        if extract_coupling and len(coils) >= 2 and line_callback is not None:
            line_callback("static (DC): coupling extraction skipped — "
                          "superposition does not hold with nonlinear B-H")
    else:
        for i, f in enumerate(freqs):
            cases.append((f, "sweep{0:03d}".format(i), None))
        if extract_coupling and len(coils) >= 2:
            for b in coils:
                cases.append((freqs[0], "couple_" + b["name"], {b["name"]: 1.0}))

    # --- solve -------------------------------------------------------------
    def _one(args):
        f, tag, exc = args
        return _run_case(elmersolver, model, f, tag, exc, workdir, mesh_dir,
                         body_ids, boundary_ids, line_callback)

    results = []
    if parallel and len(cases) > 1:
        from concurrent.futures import ThreadPoolExecutor

        workers = min(len(cases), os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_one, cases))
    else:
        results = [_one(c) for c in cases]

    coil_meta = [dict(b["coil"], name=b["name"]) for b in coils]
    thermal_bodies = (model.get("thermal") or {}).get("bodies") or {}
    body_meta = [{"name": b["name"], "sigma": b.get("sigma", 0.0),
                  "mu_r": b.get("mu_r", 1.0),
                  "r0": b["r0"], "r1": b["r1"], "z0": b["z0"], "z1": b["z1"],
                  "is_coil": bool(b.get("coil")),
                  "turns": b["coil"]["turns"] if b.get("coil") else None,
                  "current_a": b["coil"]["current_a"] if b.get("coil") else None,
                  "k_th": thermal_bodies.get(b["name"], {}).get("k")}
                 for b in model["bodies"]]
    result = MagneticsResult(results, coil_meta, body_meta, meta={
        "backend": "elmer",
        "workdir": workdir,
        "duration_s": time.time() - t0,
        "body_ids": body_ids,
        "boundary_ids": boundary_ids,
        "static": bool(model.get("static")),
    })
    result.save_csv(os.path.join(workdir, "magnetics.csv"))
    result.save_summary(os.path.join(workdir, "summary.txt"))
    return result


def run(analysis, solver, workdir=None, line_callback=None):
    """Run the Elmer magnetics pipeline for a FreeCAD analysis.

    Same signature as the other backends' ``run``; returns a
    MagneticsResult (not a SweepResult — magnetics has no S11).
    Dispatches on ``AnalysisType``: the 3-D modes go through the WhitneyAV
    chain (``model3d``); everything else is the axisymmetric path.
    """
    if "3-D" in str(getattr(solver, "AnalysisType", "") or ""):
        from .model3d import run3d

        return run3d(analysis, solver, workdir=workdir,
                     line_callback=line_callback)

    from emstudio.objects.analysis import Analysis

    from .model import build_axi_model

    model = build_axi_model(analysis, solver)
    f1, f2, npts = Analysis.freq_range_hz(analysis)
    if npts <= 1 or f2 <= f1:
        freqs = [f1]
    else:
        step = (f2 - f1) / (npts - 1)
        freqs = [f1 + i * step for i in range(npts)]

    # Quasi-static validity guard: warn (never block) if the magnetics analysis
    # is set up above the electrically-small regime where Elmer's
    # magneto-quasistatic solve is trustworthy (see emstudio.solvers.validity).
    # DC magnetostatics has no electrical-size question.
    warning = None
    if not model.get("static"):
        from emstudio.solvers import validity

        warning = validity.electrical_size_warning(
            max(freqs), validity.axi_model_max_dim_m(model),
            method="magneto-quasistatic (Elmer)")
        validity.emit(warning, line_callback)

    extract = bool(getattr(solver, "ExtractCoupling", True))
    result = run_model(model, freqs, workdir=workdir,
                       line_callback=line_callback, extract_coupling=extract)
    if warning:
        result.meta["frequency_warning"] = warning
    result.meta["analysis"] = analysis.Label
    return result
