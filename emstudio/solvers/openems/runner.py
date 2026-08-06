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


def run(analysis, solver, workdir=None, line_callback=None):
    """Run the full openEMS pipeline for an analysis. Returns a SweepResult."""
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
    result.write_touchstone(os.path.join(workdir, "port_{0}.s1p".format(port_nr)))

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

    # optional near-field |E| map (NearFieldPlane)
    result.nearfield = None
    nf_path = os.path.join(workdir, "nearfield.npz")
    if os.path.isfile(nf_path):
        result.nearfield = dict(np.load(nf_path, allow_pickle=False))
    progress.report(line_callback, 1.0, "Done")
    return result
