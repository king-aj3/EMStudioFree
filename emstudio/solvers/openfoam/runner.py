# SPDX-License-Identifier: LGPL-2.1-or-later
"""Drive an OpenFOAM case through whichever install discovery resolved.

One dispatch point for all three routes so the rest of the package never has
to know which it got:

* **native Windows** — ESI's mingw build, driven through the MSYS2 bash it
  ships. ⚠ Always from a plain ``subprocess``; a parent MSYS shell (Git Bash)
  hands the child its own mount table and ``/home/ofuser`` stops resolving,
  which looks exactly like a broken install.
* **WSL2 distro** — ``wsl -d <distro> -- bash -lc``.
* **POSIX** — the local shell.

A LOGIN shell (``-l``) is required on the native route: without it MSYS2's own
PATH is unset, ``dirname`` is missing, and sourcing OpenFOAM's bashrc dies
half-way, leaving a plausible-looking but truncated result.

⚠ **The exit code of a piped command is the LAST command's.** ``blockMesh |
head`` returns 0 while blockMesh is dying. Nothing here pipes; each step's own
status is what gets recorded.
"""

from __future__ import annotations

import os
import subprocess

from emstudio import procutil
from emstudio.setup import openfoam as _setup
from emstudio.solvers.base import SolverError
from emstudio.solvers.openfoam.cylinder import CylinderCase, write_cylinder
from emstudio.solvers.openfoam.parser import (latest_time_dir,
                                              nusselt_cylinder_from_field,
                                              nusselt_from_field,
                                              read_internal_field)
from emstudio.solvers.openfoam.writer import CavityCase, L, write_cavity

__all__ = ["run_chain", "run_cavity", "run_cylinder"]

#: The meshing + solving chain for the cavity. blockMesh only — no
#: snappyHexMesh, which is what keeps this runnable as a gate.
CAVITY_STEPS = ("blockMesh", "checkMesh", "buoyantBoussinesqSimpleFoam")


def _to_posix(path):
    r"""C:\a\b -> /c/a/b for the MSYS2 and WSL shells alike."""
    path = os.path.abspath(path)
    drive, rest = os.path.splitdrive(path)
    if not drive:
        return path
    return "/" + drive[0].lower() + rest.replace("\\", "/")


def _command(info, script, case_dir):
    """The argv that runs `script` with the OpenFOAM environment sourced."""
    cd = "cd '%s' || exit 91\n" % _to_posix(case_dir)
    full = ". %s >/dev/null 2>&1 || exit 90\n%s%s" % (info.bashrc, cd, script)
    if getattr(info, "native_root", ""):
        return [info.native_bash, "-lc", full]
    if getattr(info, "wsl_distro", ""):
        # WSL sees the Windows disk under /mnt/<drive>, not /<drive>.
        full = full.replace("cd '%s'" % _to_posix(case_dir),
                            "cd '/mnt%s'" % _to_posix(case_dir))
        return [_setup._wsl_exe(), "-d", info.wsl_distro, "--", "bash", "-lc",
                full]
    return ["bash", "-lc", full]


def run_chain(case_dir, info=None, steps=CAVITY_STEPS, timeout=3600):
    """Run each step in order. Returns a report; does NOT raise on a bad step.

    The log of the step that failed is the thing worth reading, so a failure
    is reported rather than thrown.
    """
    info = info or _setup.find_openfoam()
    if not info.found:
        raise SolverError("no OpenFOAM found — install it from Solver Setup")
    if info.fork != "esi":
        raise SolverError(
            "this case is the ESI flavour (transportProperties, "
            "buoyantBoussinesqSimpleFoam) and will fail on the first "
            "dictionary read against %s" % info.describe())

    report = {"ok": True, "install": info.describe(), "steps": []}
    for step in steps:
        argv = _command(info, "%s > log.%s 2>&1; echo rc=$?"
                        % (step, step.split()[0]), case_dir)
        try:
            job = subprocess.run(argv, capture_output=True, timeout=timeout,
                                 creationflags=procutil.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as exc:
            report.update(ok=False, failed_at=step, error=str(exc))
            return report
        out = (job.stdout or b"").decode("utf-8", "replace")
        rc = 0 if "rc=0" in out else 1
        log = os.path.join(case_dir, "log.%s" % step.split()[0])
        tail = ""
        if os.path.isfile(log):
            with open(log, encoding="utf-8", errors="replace") as fh:
                tail = fh.read()[-3000:]
        # ⚠ rc == 0 means the binary exited cleanly, NOT that the solve
        # converged: SIMPLE exits 0 just as happily when it runs out of
        # iterations with its residuals still falling. Recorded separately so
        # a caller can tell "finished" from "finished converging" — which
        # cost a 34 %-wrong Nusselt number before it was recorded here.
        report["steps"].append({"step": step, "rc": rc, "tail": tail,
                                "converged": "SIMPLE solution converged"
                                             in tail})
        if rc != 0:
            report.update(ok=False, failed_at=step)
            return report
    return report


def run_cavity(case_dir, case=None, info=None, timeout=3600):
    """Write, run and read a cavity case. Returns (report, NusseltResult|None).

    ``NusseltResult`` is None whenever the chain did not get far enough to
    produce one — never a zero, because a zero Nu is a physical claim and
    "nothing ran" is not.

    ``report["converged"]`` says whether ``residualControl`` actually fired.
    Read it before reading ``nu_avg``: the two are independent, and a clean
    exit code establishes neither.
    """
    case = write_cavity(case_dir, case or CavityCase())
    report = run_chain(case_dir, info=info, timeout=timeout)
    report["case"] = {"ra": case.ra, "pr": case.pr, "cells": case.cells,
                      "ra_written": case.ra_written}
    if not report["ok"]:
        return report, None

    time_dir = latest_time_dir(case_dir)
    if not time_dir:
        report.update(ok=False, failed_at="write",
                      error="the solver exited 0 but wrote no time directory")
        return report, None
    report["time_dir"] = time_dir

    try:
        values = read_internal_field(os.path.join(case_dir, time_dir, "T"))
        result = nusselt_from_field(values, case.cells, case.t_hot,
                                    case.t_cold, length=L)
    except (OSError, ValueError) as exc:
        report.update(ok=False, failed_at="read", error=str(exc))
        return report, None
    report["nu_avg"] = result.nu_avg

    # ⚠ rc == 0 is not convergence — SIMPLE exits 0 just as happily when it
    # runs out of iterations with residuals still falling. This was recorded
    # for the cylinder and NOT wired through here, which left the cavity gate
    # running a fixed 1200 iterations with no way to say whether that was
    # enough.
    #
    # ⚠ And `imbalance` does not close that gap. It is a genuine energy
    # conservation check — hot-wall and cold-wall Nusselt numbers are the same
    # number measured at opposite ends — but a partially-converged field that
    # is still symmetric satisfies it, so a small imbalance is NECESSARY for
    # convergence and not SUFFICIENT. Treating it as sufficient is how an
    # under-converged Nu gets read as a physical result.
    solve = [s for s in report["steps"] if s["step"].startswith("buoyant")]
    report["converged"] = bool(solve and solve[0]["converged"])
    if not report["converged"]:
        result.warnings.append(
            "residualControl never fired in %d iterations — the run stopped at "
            "endTime with its residuals still falling, so this Nu is a "
            "snapshot of an unconverged solve, whatever the imbalance says"
            % case.iterations)
    return report, result


#: Identical to CAVITY_STEPS by coincidence, not by sharing: the two cases are
#: independent on purpose (see cylinder.py's "third case writer" note), so a
#: future snappyHexMesh step on one must not silently appear in the other.
CYLINDER_STEPS = ("blockMesh", "checkMesh", "buoyantBoussinesqSimpleFoam")


def run_cylinder(case_dir, case=None, info=None, timeout=3600):
    """Write, run and read a cylinder case. Returns (report, CylinderNusselt|None).

    ``None`` whenever the chain did not get far enough to produce a reading —
    never a zero, for the same reason as :func:`run_cavity`: a zero Nu is a
    physical claim and "nothing ran" is not.
    """
    case = write_cylinder(case_dir, case or CylinderCase())
    report = run_chain(case_dir, info=info, steps=CYLINDER_STEPS,
                       timeout=timeout)
    report["case"] = {"ra_d": case.ra_d, "pr": case.pr, "d_m": case.d_m,
                      "mode": case.mode, "radius_ratio": case.radius_ratio,
                      "n_r": case.n_r, "n_theta": case.n_theta,
                      "grading": case.grading,
                      "first_cell_m": case.first_cell_m,
                      "ra_written": case.ra_written}
    if not report["ok"]:
        return report, None

    time_dir = latest_time_dir(case_dir)
    if not time_dir:
        report.update(ok=False, failed_at="write",
                      error="the solver exited 0 but wrote no time directory")
        return report, None
    report["time_dir"] = time_dir

    try:
        values = read_internal_field(os.path.join(case_dir, time_dir, "T"))
        # The outer wall is only a wall in annulus mode; passing its geometry
        # in far-field mode would compute a "balance" against an open boundary,
        # which is a number with no meaning.
        extra = ({"last_cell_m": case.last_cell_m, "r_out": case.r_out}
                 if case.mode == "annulus" else {})
        result = nusselt_cylinder_from_field(
            values, case.n_r, case.n_theta, case.t_wall, case.t_amb,
            case.d_m, case.first_cell_m, **extra)
    except (OSError, ValueError) as exc:
        report.update(ok=False, failed_at="read", error=str(exc))
        return report, None
    report["nu_d"] = result.nu_d
    solve = [s for s in report["steps"] if s["step"].startswith("buoyant")]
    report["converged"] = bool(solve and solve[0]["converged"])

    # ⚠ residualControl is the WRONG convergence test for the open domain.
    # Measured: a far-field case at Ra 1e4 held Nu at 4.821 +-0.01 % from
    # iteration 2500 all the way to 30000 while its residuals sat around 1e-3
    # and the control (1e-6/1e-7) never fired. The residual floor comes from
    # the open boundary; the quantity of interest had long since settled.
    # So when intermediate snapshots exist, the honest test is that Nu itself
    # stopped moving — reported here rather than left for each caller to
    # reinvent. It costs nothing: the snapshots are from the same run.
    report["nu_drift"] = None
    times = sorted(
        (t for t in (_as_time(n) for n in os.listdir(case_dir)
                     if os.path.isdir(os.path.join(case_dir, n))) if t),
        key=lambda p: p[0])
    if len(times) >= 2:
        try:
            prev = read_internal_field(
                os.path.join(case_dir, times[-2][1], "T"))
            earlier = nusselt_cylinder_from_field(
                prev, case.n_r, case.n_theta, case.t_wall, case.t_amb,
                case.d_m, case.first_cell_m)
            if earlier.nu_d:
                report["nu_drift"] = abs(result.nu_d - earlier.nu_d) \
                                     / abs(earlier.nu_d)
                report["nu_d_previous"] = earlier.nu_d
                report["previous_time"] = times[-2][1]
        except (OSError, ValueError):
            pass                      # a snapshot we cannot read is not a claim

    if not report["converged"] and report["nu_drift"] is None:
        result.warnings.append(
            "residualControl never fired in %d iterations and no intermediate "
            "snapshot was written, so nothing here establishes convergence — "
            "set write_interval to get a drift measurement" % case.iterations)
    return report, result


def _as_time(name):
    """(value, name) if `name` is a positive time directory, else None."""
    try:
        value = float(name)
    except ValueError:
        return None
    return (value, name) if value > 0 else None
