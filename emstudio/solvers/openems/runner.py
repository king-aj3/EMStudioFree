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
from emstudio.solvers.base import SolverError, SolverJob, make_workdir

from . import writer


def find_openems_python():
    """Interpreter with the openEMS/CSXCAD python modules.

    Order: EMSTUDIO_OPENEMS_PYTHON env var -> venv next to the detected openEMS
    binary (the layout our guided install produces) -> None.
    """
    env = os.environ.get("EMSTUDIO_OPENEMS_PYTHON", "")
    if env and os.path.isfile(env):
        return env
    info = solver_setup.find_backend("openems")
    if info.found:
        # <prefix>/bin/openEMS -> <prefix>/venv/bin/python
        prefix = os.path.dirname(os.path.dirname(info.path))
        cand = os.path.join(prefix, "venv", "bin", "python")
        if os.path.isfile(cand):
            return cand
    return None


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

    job = SolverJob([python, deck], cwd=workdir, line_callback=line_callback)
    job.run_blocking(timeout=4 * 3600)

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
    return result
