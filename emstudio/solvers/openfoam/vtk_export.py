# SPDX-License-Identifier: LGPL-2.1-or-later
"""Turn a solved OpenFOAM case into VTK files FreeCAD can display.

The convection solve distils a whole temperature and velocity field into ONE
number (the bundle factor). This is the other half: the field itself, in the
3-D view, so what the solver actually did can be looked at rather than trusted.

⚠ `foamToVTK` writes a MULTI-BLOCK set, not one file:

    VTK/<case>_<time>/internal.vtu          <- the volume field
    VTK/<case>_<time>/boundary/<patch>.vtp  <- one per patch
    VTK/<case>_<time>.vtm, VTK/<case>.vtm.series

Only `internal.vtu` is an unstructured grid FreeCAD's `Fem::FemPostPipeline`
reads directly, which is why this returns it separately rather than handing
back the `.vtm`.

⚠ The flag is `-latestTime`. `-latest-time` is REJECTED by v2512 — it exits
non-zero with "Invalid option", and if that is run through a shell pipeline the
pipeline's exit status hides it. Never pipe the converter.
"""
from __future__ import annotations

import os

from emstudio.solvers.base import SolverError


def vtk_dir(case_dir):
    """The VTK output directory for a case (may not exist yet)."""
    return os.path.join(case_dir, "VTK")


def find_internal_vtu(case_dir):
    """Newest ``internal.vtu`` under the case's VTK dir, or ''.

    Newest by the TIME in the directory name where that parses, because
    `<case>_300` and `<case>_400` sort lexically in an order that is only
    sometimes the physical one — `_1000` sorts before `_300`.
    """
    root = vtk_dir(case_dir)
    if not os.path.isdir(root):
        return ""
    found = []
    for name in os.listdir(root):
        vtu = os.path.join(root, name, "internal.vtu")
        if os.path.isfile(vtu):
            try:
                t = float(name.rsplit("_", 1)[-1])
            except (ValueError, IndexError):
                t = -1.0
            found.append((t, name, vtu))
    if not found:
        return ""
    found.sort(key=lambda r: (r[0], r[1]))
    return found[-1][2]


def boundary_vtps(case_dir):
    """Patch surface files beside the newest ``internal.vtu``. Possibly empty."""
    vtu = find_internal_vtu(case_dir)
    if not vtu:
        return []
    bdir = os.path.join(os.path.dirname(vtu), "boundary")
    if not os.path.isdir(bdir):
        return []
    return sorted(os.path.join(bdir, f) for f in os.listdir(bdir)
                  if f.lower().endswith(".vtp"))


def convert(case_dir, info=None, timeout=900, line_callback=None):
    """Run ``foamToVTK -latestTime`` on ``case_dir``. Returns the internal.vtu.

    Raises :class:`SolverError` when the case is not there, OpenFOAM cannot be
    found, or the converter produced nothing.
    """
    from emstudio.setup import openfoam as of_setup
    from emstudio.solvers.openfoam import runner as of_runner

    say = line_callback or (lambda _line: None)
    if not case_dir or not os.path.isdir(case_dir):
        raise SolverError(
            "no OpenFOAM case at {0!r} — solve the convection case first, and "
            "note a case in a temp directory does not survive a "
            "reboot".format(case_dir))
    if not os.path.isdir(os.path.join(case_dir, "system")):
        raise SolverError(
            "{0} is not an OpenFOAM case (no system/ directory)".format(case_dir))

    info = info or of_setup.find_openfoam()
    if info is None or not getattr(info, "bashrc", ""):
        raise SolverError(
            "OpenFOAM was not found — Solver Setup can install it. The case "
            "itself is still on disk at " + case_dir)

    # NOT piped: a pipeline's exit status is the LAST command's, which would
    # hide a converter that refused its arguments.
    argv = of_runner._command(info, "foamToVTK -latestTime\n", case_dir)
    say("converting case to VTK: " + case_dir)
    import subprocess

    from emstudio import procutil

    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=procutil.CREATE_NO_WINDOW)
    for line in (proc.stdout + proc.stderr).splitlines():
        if line.strip():
            say(line)

    vtu = find_internal_vtu(case_dir)
    # Trust the OUTPUT over the exit code, but only in the direction that is
    # safe: a missing file is a failure whatever the code said.
    if not vtu:
        raise SolverError(
            "foamToVTK produced no internal.vtu (exit {0}). Last output: "
            "{1}".format(proc.returncode,
                         (proc.stdout + proc.stderr).strip()[-300:] or "(none)"))
    say("wrote " + vtu)
    return vtu
