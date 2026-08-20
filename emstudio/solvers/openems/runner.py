# SPDX-License-Identifier: LGPL-2.1-or-later
"""openEMS backend orchestration: Prepare -> Solve -> Results.

The deck runs under the openEMS *venv* Python (never FreeCAD's interpreter), which
decouples EMStudio from FreeCAD's bundled-Python version differences (0.21 = 3.12
system, 1.1 AppImage = 3.11).
"""

from __future__ import annotations

import os

from emstudio.post.sparams import SweepResult
from emstudio.setup import solvers as solver_setup
from emstudio.solvers import progress
from emstudio.solvers.base import SolverError, SolverJob, make_workdir

from . import writer


#: Re-exported for every existing caller. The implementation LIVES in
#: ``emstudio.setup.solvers`` because that module is FreeCAD-free, and this one
#: is not: importing it drags in ``writer`` -> ``objects.analysis`` ->
#: ``import FreeCAD``. A gate that only wants to ask "is openEMS available?"
#: must be able to do so without FreeCAD, or it cannot skip cleanly — which is
#: exactly why four openEMS gates were failing instead of skipping.
find_openems_python = solver_setup.find_openems_python


def _analysis_port_numbers(analysis):
    """The port numbers this analysis carries, ascending.

    ⚠ These are the document's own ``PortNumber`` values, NOT ``1..N``. A user
    who deletes a port leaves 1 and 3 behind, and a loop over ``range(1, n+1)``
    would then ask the writer for a port 2 that does not exist and re-run port 1
    under the wrong label. Drive the numbers that are actually there.
    """
    from emstudio.objects import query

    return [int(p.PortNumber) for p in query.get_ports(analysis)]


def _add_excitations(analysis, solver, workdir, python, result, line_callback,
                     port_numbers):
    """Drive each remaining port in its own subdirectory and merge its column in.

    Kept as an EXTENSION of the single-excitation path rather than a rewrite of
    it: run 1 still writes exactly what it always did, in exactly the same
    place, so nothing about the default behaviour moves. Each later run lives in
    ``excN/`` because every run writes ``port_<n>.csv`` and a shared directory
    would have them treading on each other.

    From the run driving port k the NEW terms are Skk (that port's own
    reflection, in ``port_k.csv``) and the ``sparam_<to>_k.csv`` column. Terms
    an earlier run already produced are deliberately not re-read.

    ``port_numbers`` is every port EXCEPT the one run 1 drove — the caller owns
    that decision, because run 1's driven port comes from the document's own
    ``Excited`` flag and is not necessarily port 1.
    """
    import glob

    import numpy as np

    if not port_numbers:
        return
    for i, nr in enumerate(port_numbers):
        sub = os.path.join(workdir, "exc{0}".format(int(nr)))
        os.makedirs(sub, exist_ok=True)
        deck, _z0, driven = writer.write_deck(analysis, solver, sub,
                                              excite_port=int(nr))

        # The extra excitations share the last 8 % of the bar between them, so
        # a 4-port run does not reset the bar three times.
        frac = 0.92 + 0.08 * (i / float(len(port_numbers)))
        progress.report(line_callback, frac,
                        "Excitation {0} of {1} (port {2})".format(
                            i + 2, len(port_numbers) + 1, driven))
        job = SolverJob([python, deck], cwd=sub, line_callback=line_callback)
        job.run_blocking(timeout=4 * 3600)

        own = os.path.join(sub, "port_{0}.csv".format(driven))
        if not os.path.isfile(own):
            raise SolverError(
                "openEMS excitation of port {0} produced no results file: {1}"
                .format(driven, own))
        rk = SweepResult.load_csv(own, meta={"backend": "openEMS"})
        if len(rk.freq) != len(result.freq) or not np.allclose(
                rk.freq, result.freq, rtol=1e-9):
            raise SolverError(
                "openEMS: excitation of port {0} swept different frequencies "
                "({1} vs {2} points) — every excitation must share one grid, "
                "and resampling here would fabricate the S-matrix."
                .format(driven, len(rk.freq), len(result.freq)))

        result.s_others[(driven, driven)] = np.asarray(rk.s11, dtype=complex)
        for path in sorted(glob.glob(os.path.join(sub, "sparam_*_*.csv"))):
            base = os.path.basename(path)[len("sparam_"):-len(".csv")]
            try:
                to_port, from_port = (int(t) for t in base.split("_"))
            except ValueError:
                continue
            data = np.atleast_2d(np.loadtxt(path, delimiter=",", skiprows=1))
            result.s_others[(to_port, from_port)] = data[:, 1] + 1j * data[:, 2]
        result.meta["duration_s"] = (
            result.meta.get("duration_s", 0.0) + job.duration_s)
    result.meta["excitations"] = 1 + len(port_numbers)


def run(analysis, solver, workdir=None, line_callback=None, full_smatrix=False):
    """Run the full openEMS pipeline for an analysis. Returns a SweepResult.

    ``full_smatrix`` adds one FDTD run per remaining port, so the result carries
    the complete NxN S-matrix instead of the single column one excitation
    gives. openEMS solves one excitation per run by construction, so this is
    genuinely N simulations and roughly N times the time — required for a
    .sNp, because no assumption recovers Skk from a port-1 solve.
    """
    python = find_openems_python()
    if not python:
        info = solver_setup.find_backend("openems")
        raise SolverError(
            "openEMS python environment not found.\n"
            + solver_setup.install_hint(info.backend)
            + "\n(or set EMSTUDIO_OPENEMS_PYTHON to a python with the openEMS module)"
        )

    workdir = make_workdir("emstudio_openems_", base=workdir)
    deck, z0, port_nr = writer.write_deck(analysis, solver, workdir)

    # A determinate bar from openEMS's own timestep counter. The TOTAL is
    # learned from a line the GENERATED DECK prints ("EMStudio: starting
    # openEMS run (NrTS=..., ...)"), so the runner never duplicates the
    # writer's `max(1000, int(solver.MaxTimesteps))` and the two cannot drift.
    #
    # UNVERIFIED AGAINST A LIVE RUN: openEMS is not installed on the box this
    # was written on, so the step pattern is matched loosely against openEMS's
    # documented progress line ("... Timestep   600 || Speed: ..."). That is
    # deliberately a no-risk bet — if the wording does not match, nothing is
    # reported and the dialog behaves exactly as it does today. Confirm on a
    # machine with openEMS and tighten it there.
    #
    # FDTD gets 0..90 %; the far-field / near-field post-processing the deck
    # does afterwards is the last 10 %.
    cb = progress.StreamProgress(
        line_callback,
        step_pattern=r"Timestep\s+(\d+)",
        total_pattern=r"NrTS\s*=\s*(\d+)",
        note="Running FDTD", base=0.0, span=0.90)
    job = SolverJob([python, deck], cwd=workdir,
                    line_callback=cb if line_callback is not None
                    else line_callback)
    job.run_blocking(timeout=4 * 3600)
    progress.report(line_callback, 0.90, "Reading results")

    csv_path = os.path.join(workdir, "port_{0}.csv".format(port_nr))
    if not os.path.isfile(csv_path):
        raise SolverError("openEMS deck produced no results file: " + csv_path)
    result = SweepResult.load_csv(csv_path, meta={"backend": "openEMS"})
    result.meta.update(
        {"workdir": workdir, "duration_s": job.duration_s, "analysis": analysis.Label}
    )
    # (Touchstone is written at the end, once the port count is known.)

    # optional far field written by the deck (ComputeFarField)
    result.farfield = None
    ff_path = os.path.join(workdir, "farfield_port_{0}.csv".format(port_nr))
    if os.path.isfile(ff_path):
        from emstudio.post.farfield import FarFieldResult

        result.farfield = FarFieldResult.load_csv(ff_path, meta={"backend": "openEMS"})

    # optional transmission S-parameters (multi-port): sparam_<to>_<from>.csv
    import glob

    import numpy as np

    result.s_others = {}
    for path in sorted(glob.glob(os.path.join(workdir, "sparam_*_*.csv"))):
        base = os.path.basename(path)[len("sparam_"):-len(".csv")]
        try:
            to_port, from_port = (int(t) for t in base.split("_"))
        except ValueError:
            continue
        data = np.atleast_2d(np.loadtxt(path, delimiter=",", skiprows=1))
        result.s_others[(to_port, from_port)] = data[:, 1] + 1j * data[:, 2]

    # -- optional REMAINING excitations, for a complete N-port ---------------
    # Run 1 drove `port_nr` (the document's own Excited port, which need not be
    # port 1), so the runs still owed are every OTHER port. Subtracting the one
    # already driven is what keeps a 2-port at two solves rather than three.
    if full_smatrix:
        others = [nr for nr in _analysis_port_numbers(analysis) if nr != port_nr]
        _add_excitations(analysis, solver, workdir, python, result,
                         line_callback, others)

    # The order is decided by the DATA: .s1p for one excitation, .s2p once the
    # matrix is complete. Writing a fixed .s1p would have mislabelled the file
    # the moment full_smatrix produced four terms.
    n = result.max_complete_ports()
    result.write_touchstone(
        os.path.join(workdir, "port_{0}.s{1}p".format(port_nr, n)), n_ports=n)

    # optional near-field |E| map (NearFieldPlane)
    result.nearfield = None
    nf_path = os.path.join(workdir, "nearfield.npz")
    if os.path.isfile(nf_path):
        result.nearfield = dict(np.load(nf_path, allow_pickle=False))
    progress.report(line_callback, 1.0, "Done")
    return result
