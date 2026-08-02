# SPDX-License-Identifier: LGPL-2.1-or-later
"""NEC2 backend orchestration: Prepare -> Solve -> Results."""

from __future__ import annotations

import os

from emstudio.setup import solvers as solver_setup
from emstudio.solvers.base import (SolverError, SolverJob, make_workdir,
                                   nec2_argv)

from . import parser, writer


def run(analysis, solver, workdir=None, line_callback=None):
    """Run the full NEC2 pipeline for an analysis. Returns a SweepResult.

    Writes deck + results (CSV, Touchstone) into the working directory.
    """
    info = solver_setup.find_backend("nec2")
    if not info.found:
        raise SolverError(
            "nec2c not found.\n" + solver_setup.install_hint(info.backend)
        )

    workdir = make_workdir("emstudio_nec2_", base=workdir)
    deck = os.path.join(workdir, "case.nec")
    outfile = os.path.join(workdir, "case.out")

    _, sweep, z0 = writer.write_nec(analysis, solver, deck)

    job = SolverJob(
        nec2_argv(info.path, deck, outfile),
        cwd=workdir,
        line_callback=line_callback,
    )
    job.run_blocking(timeout=600)

    result = parser.parse_output(outfile, z0=z0)
    result.meta.update(
        {"workdir": workdir, "duration_s": job.duration_s, "analysis": analysis.Label}
    )
    result.save_csv(os.path.join(workdir, "port_1.csv"))
    result.write_touchstone(os.path.join(workdir, "port_1.s1p"))

    # second pass: radiation pattern at the best-match frequency (cheap for MoM)
    result.farfield = None
    try:
        f_ff, _ = result.min_s11()
        ff_deck = os.path.join(workdir, "case_ff.nec")
        ff_out = os.path.join(workdir, "case_ff.out")
        writer.write_nec_farfield(analysis, solver, ff_deck, f_ff)
        SolverJob(
            nec2_argv(info.path, ff_deck, ff_out),
            cwd=workdir,
            line_callback=line_callback,
        ).run_blocking(timeout=600)
        result.farfield = parser.parse_radiation_patterns(ff_out, f_ff)
        result.farfield.save_csv(os.path.join(workdir, "farfield_port_1.csv"))
        # the same single-frequency output carries the current distribution
        result.currents = parser.parse_currents(ff_out, f_ff)
    except Exception as exc:  # noqa: BLE001 — far field is best-effort extra
        result.meta["farfield_error"] = str(exc)
    return result
