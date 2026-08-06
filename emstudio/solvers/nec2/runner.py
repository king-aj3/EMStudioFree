# SPDX-License-Identifier: LGPL-2.1-or-later
"""NEC2 backend orchestration: Prepare -> Solve -> Results."""

from __future__ import annotations

import os

from emstudio.setup import solvers as solver_setup
from emstudio.solvers import progress
from emstudio.solvers.base import (SolverError, SolverJob, make_workdir,
                                   nec2_argv)

from . import parser, pattern_band, writer

#: The marker that means "one sweep point is done", in NEC2's OUTPUT FILE.
#:
#: It must match the DATUM line and NOT the banner above it. nec2++ writes
#: BOTH for every point:
#:
#:     --------- FREQUENCY --------      <- banner, no ':' or '='
#:     FREQUENCY=  2.0000E+02 MHZ        <- the datum
#:
#: so a bare "FREQUENCY" counts twice per point and the bar reaches 100 % at
#: the halfway mark. Measured on a real 201-point deck: 402 occurrences of
#: "FREQUENCY", 201 of this pattern. The `[:=]` also covers both engines —
#: nec2c writes "FREQUENCY : ... MHz", nec2++ "FREQUENCY= ... MHZ" — which is
#: why parser.py uses the same discriminator to split result blocks.
#:
#: Exported so the validation gate can test the REAL pattern rather than a
#: copy of it that could drift.
FREQ_MARKER = r"FREQUENCY\s*[:=]"


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

    deck_report = {}
    _, sweep, z0 = writer.write_nec(analysis, solver, deck, report=deck_report)

    # A determinate bar, polled from NEC2's OUTPUT FILE — not from the line
    # callback, which can never work here: nec2++ writes ZERO bytes to stdout
    # and stderr (measured), putting everything in the -o file. That file IS
    # written incrementally (measured), so polling it gives a true fraction.
    #
    # The marker is the one parser.py already splits blocks on, so it is
    # verified against BOTH nec2c ("FREQUENCY : 3.0E+02 MHz") and nec2++
    # ("FREQUENCY=  3.0E+02 MHZ") wordings, and it deliberately does NOT match
    # the "--------- FREQUENCY --------" banner that precedes each one — the
    # file carries two "FREQUENCY" strings per point and only one is a datum.
    #
    # The sweep gets 90 % of the bar and the pattern pass the last 10 %: the
    # pattern is one frequency, but its RP evaluation over a full sphere is
    # not instant on a large model, and the bar should not sit at 100 % there.
    npts = int(sweep[2]) if sweep and len(sweep) > 2 else 0

    job = SolverJob(
        nec2_argv(info.path, deck, outfile),
        cwd=workdir,
        line_callback=line_callback,
    )
    with progress.FileWatcher(
            outfile, FREQ_MARKER, npts, line_callback,
            note="Sweeping {0} frequencies".format(npts) if npts
                 else "Sweeping",
            base=0.0, span=0.90):
        job.run_blocking(timeout=600)

    result = parser.parse_output(outfile, z0=z0)
    result.meta.update(
        {"workdir": workdir, "duration_s": job.duration_s, "analysis": analysis.Label}
    )
    if deck_report.get("thin_wire"):
        result.meta["thin_wire"] = deck_report["thin_wire"]
    result.save_csv(os.path.join(workdir, "port_1.csv"))
    result.write_touchstone(os.path.join(workdir, "port_1.s1p"))

    # second pass: radiation pattern at the best-match frequency (cheap for MoM)
    result.farfield = None
    progress.report(line_callback, 0.90, "Radiation pattern")
    result.farfields = []
    try:
        f_ff, _ = result.min_s11()
        # How many patterns the user asked for. 0 = one at the best match,
        # which is what every document produced before this existed.
        n_pat = int(getattr(solver, "PatternFrequencies", 0) or 0)
        f1, f2 = (float(sweep[0]), float(sweep[1])) if sweep else (f_ff, f_ff)
        # PatternFreqStart/Stop narrow the pattern pass to part of the sweep;
        # both 0 (the default, and every pre-0.91 document) keeps the sweep.
        f1, f2 = pattern_band.resolve_band(solver, f1, f2)
        multi = n_pat > 1 and f2 > f1
        ff_deck = os.path.join(workdir, "case_ff.nec")
        ff_out = os.path.join(workdir, "case_ff.out")
        if multi:
            # ONE extra run gives a pattern at every step of the FR card.
            writer.write_nec_farfield(analysis, solver, ff_deck, f1,
                                      npts=n_pat, f2_hz=f2)
        else:
            writer.write_nec_farfield(analysis, solver, ff_deck, f_ff)
        SolverJob(
            nec2_argv(info.path, ff_deck, ff_out),
            cwd=workdir,
            line_callback=line_callback,
        ).run_blocking(timeout=600)
        if multi:
            # parse_radiation_patterns() would pour every frequency into ONE
            # grid and silently return a pattern belonging to no frequency.
            result.farfields = parser.parse_radiation_patterns_all(ff_out)
            if not result.farfields:
                raise parser.NecParseError(
                    "pattern sweep produced no radiation-pattern blocks")
            # .farfield stays the SINGLE best-match pattern so that every
            # existing caller — the 2-D cuts, the 3-D balloon, the PDF report,
            # gui_smoke — is untouched by this feature.
            result.farfield = min(result.farfields,
                                  key=lambda ff: abs(ff.freq - f_ff))
        else:
            result.farfield = parser.parse_radiation_patterns(ff_out, f_ff)
            result.farfields = [result.farfield]
        result.farfield.save_csv(os.path.join(workdir, "farfield_port_1.csv"))
        # the same single-frequency output carries the current distribution
        result.currents = parser.parse_currents(ff_out, f_ff)
        progress.report(line_callback, 1.0, "Done")
    except Exception as exc:  # noqa: BLE001 — far field is best-effort extra
        result.meta["farfield_error"] = str(exc)
    return result
