# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pipeline for the general 3-D magnetodynamics chain (WhitneyAV).

``run_model3d`` meshes the model with ``gmsh_3d`` (meters), converts with
ElmerGrid, writes the three-solver .sif via ``writer3d`` and runs
ElmerSolver — scanning stdout for ``ERROR::`` (fatal; Elmer exits 0 on sif
errors) and ``did not converge`` (warning). Returns a plain result dict:

``{"norms": {solver_name: last_norm}, "saveline": {column: [values]},``
``  "vtu": path-or-None, "workdir", "solver_warnings", "duration_s"}``

The ``saveline`` columns come from Elmer's ``line.dat.names`` (SaveLine
column order is mesh/chain dependent — ALWAYS resolved by name, never by
index). Norms are the last ``ComputeChange: ... :: <solver>`` NRM per
solver — the self-pinned regression numbers of the 3-D gates.
"""
from __future__ import annotations

import os
import re
import time

from emstudio.meshing import gmsh_3d
from emstudio.solvers.base import SolverError, SolverJob, make_workdir

from . import writer3d
from .parser import parse_mesh_names
from .runner import _resolve_elmersolver, elmer_env, find_elmergrid

_MESH_TIMEOUT_S = 900
_SOLVE_TIMEOUT_S = 3600

_NORM_RE = re.compile(
    r"ComputeChange:\s+\S+\s+\(ITER=\d+\)\s+\(NRM,RELC\):\s+\(\s*([0-9.Ee+-]+)"
    r"\s+[0-9.Ee+-]+\s*\)\s+::\s+(.+?)\s*$")


def parse_norms(log_path):
    """Last reported NRM per solver equation name (lower-cased)."""
    norms = {}
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _NORM_RE.search(line)
            if m:
                norms[m.group(2).strip().lower()] = float(m.group(1))
    return norms


def parse_saveline(dat_path):
    """SaveLine output as {column_name: [values]} (rows across ALL steps).

    Column names from ``<dat_path>.names``; duplicate names get ``#2``…
    suffixes. Resolve columns BY NAME — the order shifts with the chain.
    """
    names = []
    with open(dat_path + ".names", "r", encoding="utf-8", errors="replace") as fh:
        in_cols = False
        for line in fh:
            if "data on different columns" in line.lower() \
                    or "columns of matrix" in line.lower():
                in_cols = True
                continue
            m = re.match(r"\s*(\d+)\s*:\s*(.+?)\s*$", line)
            if in_cols and m:
                name = m.group(2)
                if name in names:
                    k = 2
                    while "{0}#{1}".format(name, k) in names:
                        k += 1
                    name = "{0}#{1}".format(name, k)
                names.append(name)
    cols = [[] for _ in names]
    with open(dat_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != len(names):
                continue
            for i, v in enumerate(parts):
                cols[i].append(float(v))
    if not names or not cols or not cols[0]:
        raise SolverError("empty SaveLine output at {0}".format(dat_path))
    return dict(zip(names, cols))


def run_model3d(model, workdir=None, line_callback=None):
    """Mesh + solve one 3-D magnetodynamics model. Returns the result dict."""
    t0 = time.time()
    workdir = make_workdir("emstudio_elmer3d_", base=workdir)
    elmersolver = _resolve_elmersolver()
    elmergrid = find_elmergrid()

    msh = gmsh_3d.mesh_3d(
        model["bodies"], workdir, air=model["air"], lc_air=model["lc_air"],
        size_fields=model.get("size_fields"),
        embed_lines=model.get("embed_lines"), line_callback=line_callback)
    SolverJob([elmergrid, "14", "2", os.path.basename(msh), "-autoclean",
               "-out", "mesh"],
              cwd=workdir, env=elmer_env(elmergrid),
              line_callback=line_callback).run_blocking(
                  timeout=_MESH_TIMEOUT_S)
    names_file = os.path.join(workdir, "mesh", "mesh.names")
    if not os.path.isfile(names_file):
        raise SolverError("ElmerGrid produced no mesh at {0}".format(workdir))
    body_ids, boundary_ids = parse_mesh_names(names_file)

    results_dir = os.path.join(workdir, "results")
    os.makedirs(results_dir, exist_ok=True)
    sif = os.path.join(workdir, "case.sif")
    writer3d.write_sif3d(model, sif, body_ids, boundary_ids,
                         mesh_dir="mesh", results_dir="results")

    errors, warns = [], []
    log_path = os.path.join(workdir, "solver.log")
    with open(log_path, "w", encoding="utf-8") as log:
        def _cb(line):
            log.write(line + "\n")
            if "ERROR::" in line:
                errors.append(line)
            if "did not converge" in line.lower():
                warns.append(line)
            if line_callback is not None:
                line_callback(line)

        job = SolverJob([elmersolver, "case.sif"], cwd=workdir,
                        env=elmer_env(elmersolver), line_callback=_cb)
        job.run_blocking(timeout=_SOLVE_TIMEOUT_S)
    if errors:
        raise SolverError(
            "ElmerSolver reported errors:\n{0}\n(full log: {1})".format(
                "\n".join(errors[:10]), log_path))

    saveline = None
    dat = os.path.join(results_dir, "line.dat")
    if model.get("save_lines"):
        if not os.path.isfile(dat):
            raise SolverError("SaveLine produced no {0}".format(dat))
        saveline = parse_saveline(dat)

    vtu = None
    for cand in (os.path.join(results_dir, "case_t0001.vtu"),
                 os.path.join(workdir, "mesh", "case_t0001.vtu")):
        if os.path.isfile(cand):
            vtu = cand
            break

    return {
        "norms": parse_norms(log_path),
        "saveline": saveline,
        "vtu": vtu,
        "workdir": workdir,
        "body_ids": body_ids,
        "solver_warnings": warns,
        "duration_s": time.time() - t0,
    }
