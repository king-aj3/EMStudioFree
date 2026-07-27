# SPDX-License-Identifier: LGPL-2.1-or-later
"""FastHenry orchestration: write deck -> run binary -> parse Zc.mat.

FastHenry itself is single-threaded and solves the frequency sweep sequentially, so
EMStudio parallelizes ACROSS frequencies: one FastHenry process per frequency point,
up to the machine's core count, run concurrently and merged. On a many-core machine
this turns an N-frequency sweep into roughly the wall-clock of the slowest single
point.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor

from emstudio.setup import solvers as solver_setup
from emstudio.solvers.base import SolverError, SolverJob, make_workdir

from . import parser, writer


def sweep_frequencies(fmin, fmax, ndec):
    """The frequency points FastHenry's .Freq card produces (log, ndec/decade)."""
    freqs = []
    f = fmin
    step = 10.0 ** (1.0 / max(1, int(ndec)))
    while f < fmax * (1.0 + 1e-9):
        freqs.append(f)
        f *= step
    if not math.isclose(freqs[-1], fmax, rel_tol=1e-6) and freqs[-1] < fmax:
        freqs.append(fmax)
    return freqs


def _run_single(info_path, workdir, tag, deck_writer, line_callback):
    subdir = os.path.join(workdir, tag)
    os.makedirs(subdir, exist_ok=True)
    deck = os.path.join(subdir, "case.inp")
    deck_writer(deck)
    SolverJob([info_path, "case.inp"], cwd=subdir,
              line_callback=line_callback).run_blocking(timeout=3600)
    zc = os.path.join(subdir, "Zc.mat")
    if not os.path.isfile(zc):
        raise SolverError("FastHenry produced no Zc.mat in " + subdir)
    return zc


def run_parallel_sweep(wire_paths, radius_m, sigma_s_per_m, fmin, fmax, ndec,
                       nhinc, ports, workdir=None, line_callback=None,
                       max_workers=None):
    """Run one FastHenry process per frequency, concurrently.

    Returns (freqs, list of NxN complex matrices, workdir).
    """
    info = solver_setup.find_backend("fasthenry")
    if not info.found:
        raise SolverError(
            "fasthenry not found.\n" + solver_setup.install_hint(info.backend)
        )
    workdir = make_workdir("emstudio_fasthenry_", base=workdir)
    freqs = sweep_frequencies(fmin, fmax, ndec)
    workers = max_workers or min(len(freqs), os.cpu_count() or 4)

    def make_task(f):
        def deck_writer(path):
            writer.write_inp(path, wire_paths, radius_m, sigma_s_per_m,
                             f, f, 1, nhinc=nhinc, ports=ports)
        tag = "f_{0:012.0f}".format(f)
        return _run_single(info.path, workdir, tag, deck_writer, line_callback)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        zc_paths = list(pool.map(make_task, freqs))

    mats = []
    for f, zc in zip(freqs, zc_paths):
        fs, ms = parser.parse_zc_matrix(zc)
        mats.append(ms[0])
    return freqs, mats, workdir


def run_wire_paths(
    wire_paths,
    radius_m,
    sigma_s_per_m=5.8e7,
    fmin=1e3,
    fmax=1e6,
    ndec=3,
    nhinc=9,
    workdir=None,
    line_callback=None,
    parallel=True,
):
    """R(f)/L(f) of parallel wire paths. Returns (freqs, R_ohm, L_henry, workdir).

    ``parallel=True`` (default) fans one FastHenry process per frequency across
    the available CPU cores.
    """
    if parallel:
        freqs, mats, workdir = run_parallel_sweep(
            wire_paths, radius_m, sigma_s_per_m, fmin, fmax, ndec,
            nhinc, "parallel", workdir=workdir, line_callback=line_callback,
        )
        rs = [m[0][0].real for m in mats]
        ls = [m[0][0].imag / (2.0 * math.pi * f) for f, m in zip(freqs, mats)]
        return freqs, rs, ls, workdir

    info = solver_setup.find_backend("fasthenry")
    if not info.found:
        raise SolverError(
            "fasthenry not found.\n" + solver_setup.install_hint(info.backend)
        )
    workdir = make_workdir("emstudio_fasthenry_", base=workdir)
    deck = os.path.join(workdir, "case.inp")
    writer.write_inp(deck, wire_paths, radius_m, sigma_s_per_m, fmin, fmax, ndec, nhinc=nhinc)
    job = SolverJob([info.path, "case.inp"], cwd=workdir, line_callback=line_callback)
    job.run_blocking(timeout=3600)
    zc = os.path.join(workdir, "Zc.mat")
    if not os.path.isfile(zc):
        raise SolverError("FastHenry produced no Zc.mat in " + workdir)
    freqs, rs, ls = parser.parse_zc(zc)
    return freqs, rs, ls, workdir
