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
from emstudio.solvers.openfoam.parser import (latest_time_dir,
                                              nusselt_from_field,
                                              read_internal_field)
from emstudio.solvers.openfoam.writer import CavityCase, L, write_cavity

__all__ = ["run_chain", "run_cavity"]

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
        report["steps"].append({"step": step, "rc": rc, "tail": tail})
        if rc != 0:
            report.update(ok=False, failed_at=step)
            return report
    return report


def run_cavity(case_dir, case=None, info=None, timeout=3600):
    """Write, run and read a cavity case. Returns (report, NusseltResult|None).

    ``NusseltResult`` is None whenever the chain did not get far enough to
    produce one — never a zero, because a zero Nu is a physical claim and
    "nothing ran" is not.
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
    return report, result
