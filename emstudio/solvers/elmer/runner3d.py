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

#: Total magnetic field energy, printed by MagnetoDynamicsCalcFields when
#: ``Calculate Field Energy`` is on. The label is "ElectroMagnetic Field
#: Energy" — MEASURED from a real run, not guessed from the keyword name.
_ENERGY_RE = re.compile(
    r"ElectroMagnetic Field Energy:\s*([0-9.EeDd+-]+)")

#: CoilSolver's normalized average current density (A/m^2) per coil, in the
#: order the coils appear in the deck. Delivered current = this x the coil
#: cross-sectional area, and comparing that with the REQUESTED ampere-turns
#: is how an open (non-circulating) coil is caught — see model3d.
#:
#: CLOSED COILS ONLY. The open branch takes a different code path in Elmer and
#: prints no average current density at all (measured 2026-08-05 on a 324 deg
#: split ring) — it reports the two numbers below instead.
_JAVG_RE = re.compile(
    r"CoilSolver:\s*Average current density:\s*([0-9.EeDd+-]+)")

#: The OPEN branch's own reporting. ``Initial coil current`` x ``Coil
#: potential multiplier`` is the normalized coil current, and it equals the
#: requested value BY CONSTRUCTION — the multiplier is chosen to make it so.
#:
#: Be clear about what that is worth: measured across three runs with the
#: cross section correct, 4x wrong and omitted, BOTH numbers were byte
#: identical while the field moved by 75 %. So this pair proves the open drive
#: ran and normalized to a finite value; it CANNOT detect a mis-scaled coil,
#: and must never be presented as a delivery measurement.
_OPEN_I0_RE = re.compile(
    r"CoilSolver:\s*Initial coil current for coil\s*\d+:\s*([0-9.EeDd+-]+)")
_OPEN_MULT_RE = re.compile(
    r"CoilSolver:\s*Coil potential multiplier:\s*([0-9.EeDd+-]+)")

#: CoilSolver's own complaints. "Crappy potentials in coil 1" / "No negative
#: current sources on coil 1 end!" are what a MIS-DECLARED topology produces,
#: and they preceded the hard ERROR on the split ring. They were being dropped
#: — only "did not converge" was scanned for.
_COIL_WARN = "coilsolver"


def _fortran_float(text):
    """Elmer prints Fortran doubles; 1.0D-3 is not a Python literal."""
    return float(text.replace("D", "E").replace("d", "e"))


def parse_scalars(log_path):
    """Global scalars scraped from the solver log.

    Returns ``{"energy_j": float|None, "j_avg": [float, ...]}``. Absent
    values stay None/empty rather than defaulting to 0.0 — a silent zero
    reads as "no energy" instead of "not reported", and this project has
    been bitten by exactly that (the hard-coded ``energy_j = 0.0`` these
    replace).
    """
    energy = None
    j_avg = []
    open_i0 = []
    open_mult = []
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _ENERGY_RE.search(line)
            if m:
                energy = _fortran_float(m.group(1))     # last one wins
                continue
            m = _JAVG_RE.search(line)
            if m:
                j_avg.append(_fortran_float(m.group(1)))
                continue
            m = _OPEN_I0_RE.search(line)
            if m:
                open_i0.append(_fortran_float(m.group(1)))
                continue
            m = _OPEN_MULT_RE.search(line)
            if m:
                open_mult.append(_fortran_float(m.group(1)))
    open_current = [i0 * mult for i0, mult in zip(open_i0, open_mult)]
    return {"energy_j": energy, "j_avg": j_avg,
            "open_coil_current": open_current}


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
            low = line.lower()
            if "ERROR::" in line:
                errors.append(line)
            if "did not converge" in low:
                warns.append(line)
            # CoilSolver's own complaints — "Crappy potentials in coil 1",
            # "No negative current sources on coil 1 end!" — are exactly what a
            # mis-declared topology produces, and they were being discarded.
            if "warning::" in low and _COIL_WARN in low:
                warns.append(line.strip())
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

    scalars = parse_scalars(log_path)
    return {
        "norms": parse_norms(log_path),
        "saveline": saveline,
        "vtu": vtu,
        "workdir": workdir,
        "body_ids": body_ids,
        "solver_warnings": warns,
        "duration_s": time.time() - t0,
        "energy_j": scalars["energy_j"],
        "j_avg": scalars["j_avg"],
        "open_coil_current": scalars["open_coil_current"],
    }
