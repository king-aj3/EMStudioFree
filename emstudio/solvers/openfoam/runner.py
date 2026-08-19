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
import signal
import subprocess
import time

from emstudio import procutil
from emstudio.setup import openfoam as _setup
from emstudio.solvers.base import SolverError
from emstudio.solvers.openfoam.bundle import BundleCase, write_bundle
from emstudio.solvers.openfoam.wind import WindCase, write_wind
from emstudio.solvers.openfoam.cylinder import CylinderCase, write_cylinder
from emstudio.solvers.openfoam.parser import (MixedBundleNusselt,
                                              latest_time_dir,
                                              nusselt_cylinder_from_field,
                                              nusselt_from_field,
                                              nusselt_from_patch,
                                              read_internal_field,
                                              read_patch_values,
                                              forces_from_log,
                                              force_history_from_log)
from emstudio.solvers.openfoam.writer import CavityCase, L, write_cavity
from emstudio.solvers.openfoam.cht import (ChtCase, write_cht,
                                           write_region_fields,
                                           SOLID_REGION as _CHT_SOLID,
                                           FLUID_REGION as _CHT_FLUID)
from emstudio.solvers.openfoam.solid import (SolidCase, SolidResult,
                                             write_solid)

__all__ = ["run_chain", "run_cavity", "run_cylinder", "run_bundle",
           "run_wind", "run_solid"]

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


def _kill_job(job, info=None, step=""):
    """Terminate a chain step AND its children.

    ⚠ The step is a sourcing bash whose CHILD is the actual solver, so
    killing ``job.pid`` alone orphans the very process the user is trying to
    stop — it keeps solving with its parent gone. POSIX: the step is started
    as its own process group (``start_new_session``) and the whole group gets
    the signal. Windows native/MSYS: ``taskkill /T`` walks the tree.

    ⚠ The WSL route is the exception ``taskkill`` cannot cover: the solver is
    a Linux process inside the distro's VM, invisible to the Windows process
    tree — killing the ``wsl.exe`` relay orphans it and it keeps burning CPU
    in Vmmem. So on that route the step binary is ALSO pkilled by name
    inside the distro, best-effort.
    """
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(job.pid)],
                           capture_output=True,
                           creationflags=procutil.CREATE_NO_WINDOW)
            if step and info is not None and getattr(info, "wsl_distro", ""):
                try:
                    subprocess.run(
                        [_setup._wsl_exe(), "-d", info.wsl_distro, "--",
                         "pkill", "-f", step.split()[0]],
                        capture_output=True, timeout=15,
                        creationflags=procutil.CREATE_NO_WINDOW)
                except (OSError, subprocess.SubprocessError):
                    pass        # the relay is gone; nothing more to reach
        else:
            os.killpg(job.pid, signal.SIGTERM)
            try:
                job.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            # ⚠ The LEADER's death is not the GROUP's: a child that shrugged
            # off SIGTERM still holds the pgid (a pgid is not recycled while
            # any member lives), so this KILL always lands on stragglers —
            # and raises ESRCH into the except below when nobody is left.
            os.killpg(job.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass                    # the group died between the check and the kill


def _reap(job):
    """Collect a killed step WITHOUT blocking on its pipes.

    ⚠ A bare ``communicate()`` here waits for EOF on stdout/stderr, and a
    grandchild that escaped the process group (or survived a partial kill)
    holds those pipes open — turning "cancel" into a silent wait for the very
    solve the user stopped. Bounded waits, then give up: the group has been
    signalled, and a stray fd is the lesser evil than a frozen cancel.
    """
    try:
        job.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        job.kill()
        try:
            job.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    except (OSError, subprocess.SubprocessError):
        pass


def run_chain(case_dir, info=None, steps=CAVITY_STEPS, timeout=3600,
              cancel=None):
    """Run each step in order. Returns a report; does NOT raise on a bad step.

    The log of the step that failed is the thing worth reading, so a failure
    is reported rather than thrown.

    ``cancel`` is anything with ``is_set()`` (a ``threading.Event``). When it
    fires mid-step the step's whole process group is killed and the report
    comes back ``ok=False`` with ``cancelled=True`` — distinguishable from a
    failed solve, because "the user stopped it" and "it broke" call for
    different messages.
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
        # A cancel that fired between steps (or before the chain started —
        # the dialog closed the instant after Solve) must not spawn a doomed
        # step just to kill it half a second later.
        if cancel is not None and cancel.is_set():
            report.update(ok=False, failed_at=step, cancelled=True,
                          error="cancelled by user")
            return report
        argv = _command(info, "%s > log.%s 2>&1; echo rc=$?"
                        % (step, step.split()[0]), case_dir)
        # ⚠ Popen, not subprocess.run: a blocking run() gives the caller no
        # moment in which a cancel could ever be honoured — which is exactly
        # how the convection dialog shipped a Cancel button that could not
        # work. `start_new_session` makes the step its own process group so
        # `_kill_job` can take down the solver child, not just the bash
        # (False on Windows — the default — where `taskkill /T` covers it).
        try:
            job = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   start_new_session=(os.name != "nt"),
                                   creationflags=procutil.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as exc:
            report.update(ok=False, failed_at=step, error=str(exc))
            return report
        deadline = time.monotonic() + timeout
        while True:
            try:
                out_b, _err = job.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    _kill_job(job, info, step)
                    _reap(job)
                    report.update(ok=False, failed_at=step, cancelled=True,
                                  error="cancelled by user")
                    return report
                if time.monotonic() >= deadline:
                    _kill_job(job, info, step)
                    _reap(job)
                    report.update(ok=False, failed_at=step,
                                  error="timed out after %ds" % timeout)
                    return report
            except (OSError, subprocess.SubprocessError) as exc:
                _kill_job(job, info, step)
                report.update(ok=False, failed_at=step, error=str(exc))
                return report
        out = (out_b or b"").decode("utf-8", "replace")
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


#: The bundle needs a MESHING chain the structured cases do not: an STL, its
#: feature edges, and snappyHexMesh. checkMesh stays in, because a snapped mesh
#: can be invalid in ways a blockMesh one cannot.
BUNDLE_STEPS = ("blockMesh", "surfaceFeatureExtract", "snappyHexMesh -overwrite",
                "checkMesh", "buoyantBoussinesqSimpleFoam")


def run_bundle(case_dir, case=None, info=None, timeout=7200, cancel=None):
    """Write, mesh, run and read a bundle case.

    Returns ``(report, BundleNusselt | MixedBundleNusselt | None)``.

    ``None`` whenever the chain did not reach a reading — never a zero, for the
    same reason as the other two runners: a zero Nu is a physical claim and
    "nothing ran" is not.

    ⚠ Ra is an OUTPUT here. The wall FLUX is prescribed and the surface
    temperature is solved for, so ``result.ra_d`` is what the solve produced
    and any correlation comparison must be made at THAT Ra.

    ⚠ A MIXED-diameter bundle returns :class:`MixedBundleNusselt` — one reading
    per size patch, and NO single ``nu_d``. A uniform bundle returns the same
    :class:`BundleNusselt` it always did, from the same single ``cables``
    patch, so the measured ladder still describes exactly this path.
    """
    case = write_bundle(case_dir, case or BundleCase())
    report = run_chain(case_dir, info=info, steps=BUNDLE_STEPS,
                       timeout=timeout, cancel=cancel)
    nu_f, alpha_f = case.properties
    report["case"] = {"cables": case.n_cables, "d_cable": case.d_cable,
                      "box": (case.box_w, case.box_h),
                      "gradient": case.gradient, "cells_x": case.cells_x,
                      "cable_area_m2": case.cable_area_m2,
                      "fluid_volume_m3": case.fluid_volume_m3,
                      "mixed": case.mixed,
                      "groups": [{"patch": g.patch, "d_cable": g.d_cable,
                                  "gradient": g.gradient, "n": g.n_cables,
                                  "refine": (g.refine_min, g.refine_max)}
                                 for g in case.groups]}
    if not report["ok"]:
        return report, None

    time_dir = latest_time_dir(case_dir)
    if not time_dir:
        report.update(ok=False, failed_at="write",
                      error="the solver exited 0 but wrote no time directory")
        return report, None
    report["time_dir"] = time_dir

    def read_all(tdir):
        """One BundleNusselt per size patch, keyed by patch, largest first."""
        path = os.path.join(case_dir, tdir, "T")
        out = {}
        for g in case.groups:
            out[g.patch] = nusselt_from_patch(
                read_patch_values(path, g.patch), g.d_cable, g.gradient,
                case.t_amb, nu=nu_f, alpha=alpha_f)
        return out

    try:
        per_patch = read_all(time_dir)
    except (OSError, ValueError) as exc:
        report.update(ok=False, failed_at="read", error=str(exc))
        return report, None

    if case.mixed:
        result = MixedBundleNusselt(
            by_patch=per_patch,
            diameter={g.patch: g.d_cable for g in case.groups},
            gradient={g.patch: g.gradient for g in case.groups})
        report["nu_d"] = None            # there is no single one — by design
        report["ra_d"] = None
        report["by_patch"] = {
            p: {"nu_d": r.nu_d, "ra_d": r.ra_d, "faces": r.faces,
                "t_surface": r.t_surface, "dt": r.dt, "spread": r.spread,
                "d_cable": result.diameter[p], "gradient": result.gradient[p]}
            for p, r in per_patch.items()}
    else:
        result = per_patch[case.groups[0].patch]
        report["nu_d"] = result.nu_d
        report["ra_d"] = result.ra_d

    solve = [s for s in report["steps"] if s["step"].startswith("buoyant")]
    report["converged"] = bool(solve and solve[0]["converged"])

    # Same lesson as the cylinder: residualControl may be unreachable, so the
    # honest convergence test is that Nu itself stopped moving.
    #
    # ⚠ On a mixed bundle the reported drift is the WORST size's, not a mean.
    # One settled size says nothing about another, and a mean would let a
    # settled large cable hide a still-moving small one.
    report["nu_drift"] = None
    times = sorted(
        (t for t in (_as_time(n) for n in os.listdir(case_dir)
                     if os.path.isdir(os.path.join(case_dir, n))) if t),
        key=lambda p: p[0])
    if len(times) >= 2:
        try:
            earlier = read_all(times[-2][1])
            drifts = {p: abs(per_patch[p].nu_d - e.nu_d) / abs(e.nu_d)
                      for p, e in earlier.items() if e.nu_d}
            if drifts:
                report["nu_drift"] = max(drifts.values())
                report["nu_drift_by_patch"] = drifts
                if not case.mixed:
                    report["nu_d_previous"] = earlier[
                        case.groups[0].patch].nu_d
        except (OSError, ValueError):
            pass
    if not report["converged"] and report["nu_drift"] is None:
        result.warnings.append(
            "residualControl never fired in %d iterations and no intermediate "
            "snapshot exists, so nothing here establishes convergence"
            % case.iterations)
    return report, result


WIND_STEPS = ("blockMesh", "checkMesh", "simpleFoam")
WIND_TRANSIENT_STEPS = ("blockMesh", "checkMesh", "pimpleFoam")

#: ⚠ The region split is a MESH step, and the order matters: topoSet makes the
#: cellZones, splitMeshRegions turns them into regions AND generates the
#: `<region>_to_<neighbour>` interface patches, and only then can
#: changeDictionary attach the coupled BC to a patch that exists. Read off the
#: shipped v2512 tutorial rather than guessed.
#: ⚠ The split copies EVERY field into EVERY region, so the solid ends up with
#: U/p/p_rgh/alphat that mean nothing there. The shipped tutorial removes them
#: explicitly ("important for post-processing"); so do we.
#: ⚠ Two chains with a PYTHON step between them, not one. The interface patch
#: does not exist until splitMeshRegions has run, so the per-region fields that
#: reference it cannot be written before the mesh is split — and the tool that
#: normally bridges that gap (`changeDictionary`) crashes on `U` in v2512.
#: `write_region_fields` writes them whole instead.
CHT_MESH_STEPS = ("blockMesh", "topoSet",
                  "splitMeshRegions -cellZones -overwrite")
CHT_SOLVE_STEPS = ("chtMultiRegionSimpleFoam",)


def run_cht(case_dir, case=None, info=None, timeout=3600, cancel=None):
    """Write, run and read a conjugate two-region case.

    Returns ``(report, {region: mean T})``. The means are the check: for a
    LINEAR profile on uniform cells the cell-average equals the analytic mean
    exactly, so they can be compared to closed form without a mesh-convergence
    argument. See :mod:`emstudio.solvers.openfoam.cht`.

    ``cancel``: a ``threading.Event`` — same contract as ``run_solid`` and
    the bundle chain, so the CHT dialog's Cancel actually kills the solver
    (the 08-17 lesson: an uncancellable CFD freezes FreeCAD's Close button).
    """
    case = write_cht(case_dir, case or ChtCase())
    report = run_chain(case_dir, info=info, steps=CHT_MESH_STEPS,
                       timeout=timeout, cancel=cancel)
    if report["ok"]:
        # The interface patch exists only now. Write the fields that name it,
        # then solve. A failure here is a case-setup failure, not a solver one,
        # and is reported as such rather than as a mysterious solver abort.
        try:
            report["patches"] = write_region_fields(case_dir, case)
        except (OSError, ValueError) as exc:
            report.update(ok=False, failed_at="write_region_fields",
                          error=str(exc))
        else:
            solve = run_chain(case_dir, info=info, steps=CHT_SOLVE_STEPS,
                              timeout=timeout, cancel=cancel)
            report["steps"].extend(solve["steps"])
            if not solve["ok"]:
                # ``cancelled`` travels too — run_chain's contract is that it
                # distinguishes "the user stopped it" from "it broke", and a
                # solve-phase cancel must not read as a solver failure.
                report.update(ok=False, failed_at=solve.get("failed_at"),
                              error=solve.get("error"),
                              cancelled=bool(solve.get("cancelled")))
    report["case"] = {
        "t_hot": case.t_hot, "t_cold": case.t_cold,
        "k_solid": case.k_solid, "k_fluid": case.k_fluid,
        "flux_exact": case.flux, "t_interface_exact": case.t_interface,
        "t_solid_mean_exact": case.t_solid_mean,
        "t_fluid_mean_exact": case.t_fluid_mean,
    }
    if not report["ok"]:
        return report, None

    means = {}
    for region in (_CHT_SOLID, _CHT_FLUID):
        latest = latest_time_dir(os.path.join(case_dir))
        path = os.path.join(case_dir, latest or "", region, "T")
        if not os.path.isfile(path):
            report.update(ok=False, failed_at="read",
                          error="no T field for region %r at %r" % (region, path))
            return report, None
        try:
            values = read_internal_field(path)
        except (OSError, ValueError) as exc:
            report.update(ok=False, failed_at="read", error=str(exc))
            return report, None
        if not values:
            report.update(ok=False, failed_at="read",
                          error="empty T field for region %r" % region)
            return report, None
        means[region] = sum(values) / len(values)

    report["t_solid_mean"] = means[_CHT_SOLID]
    report["t_fluid_mean"] = means[_CHT_FLUID]
    return report, means


#: Same chain as the bundle: snappy carves the solid out of the box.
SOLID_STEPS = ("blockMesh", "surfaceFeatureExtract", "snappyHexMesh -overwrite",
               "checkMesh", "buoyantBoussinesqSimpleFoam")


def run_solid(case_dir, case, info=None, timeout=7200, cancel=None):
    """Write, mesh, run and read an open-air solid-convection case.

    Returns ``(report, SolidResult | None)`` — ``None`` whenever the chain
    did not reach a surface reading, never a zero, for the same reason as
    every other runner here: a zero dT is a physical claim and "nothing ran"
    is not.

    ⚠ No default case: this path exists to solve the USER'S geometry, and a
    silent built-in default is exactly the confusion the reference-trefoil
    episode taught (2026-08-17).
    """
    case = write_solid(case_dir, case)
    report = run_chain(case_dir, info=info, steps=SOLID_STEPS,
                       timeout=timeout, cancel=cancel)
    report["case"] = {"power_w": case.power_w, "area_m2": case.area_m2,
                      "flux_w_m2": case.flux_w_m2, "t_amb": case.t_amb,
                      "open_air": case.open_air, "box_half": case.box_half,
                      "cells_bg": case.cells_bg, "gravity": case.gravity,
                      "triangles": len(case.triangles)}
    if not report["ok"]:
        return report, None

    time_dir = latest_time_dir(case_dir)
    if not time_dir:
        report.update(ok=False, failed_at="write",
                      error="the solver exited 0 but wrote no time directory")
        return report, None
    report["time_dir"] = time_dir

    k, nu_f, alpha_f, _pr = case.air

    def surface_mean(tdir):
        values = read_patch_values(
            os.path.join(case_dir, tdir, "T"), case.patch)
        if not values:
            raise ValueError("no surface values on patch %r" % case.patch)
        return values

    try:
        values = surface_mean(time_dir)
    except (OSError, ValueError) as exc:
        report.update(ok=False, failed_at="read", error=str(exc))
        return report, None

    result = SolidResult(
        t_mean=sum(values) / len(values), t_min=min(values),
        t_max=max(values), t_amb=case.t_amb, flux_w_m2=case.flux_w_m2,
        k_fluid=k, nu_fluid=nu_f, alpha_fluid=alpha_f, beta=case.beta,
        gravity=case.gravity, faces=len(values),
        provenance="open-air solid, %d triangles, box %.3g m, %s cells_bg %d"
                   % (len(case.triangles), 2.0 * case.box_half,
                      time_dir, case.cells_bg))
    solve = [s for s in report["steps"] if s["step"].startswith("buoyant")]
    report["converged"] = bool(solve and solve[0]["converged"])
    result.converged = report["converged"]

    # Drift of the surface mean between the last two snapshots — the same
    # honesty the cylinder path records: residuals establish less than the
    # quantity of interest having stopped moving.
    report["dt_drift"] = None
    times = sorted(
        (t for t in (_as_time(n) for n in os.listdir(case_dir)
                     if os.path.isdir(os.path.join(case_dir, n))) if t),
        key=lambda p: p[0])
    if len(times) >= 2:
        try:
            prev = surface_mean(times[-2][1])
            dt_prev = sum(prev) / len(prev) - case.t_amb
            if dt_prev:
                result.drift = abs(result.dt - dt_prev) / abs(dt_prev)
                report["dt_drift"] = result.drift
                report["previous_time"] = times[-2][1]
        except (OSError, ValueError):
            pass                      # a snapshot we cannot read is not a claim
    if not report["converged"] and report["dt_drift"] is None:
        result.warnings.append(
            "residualControl never fired in %d iterations and no intermediate "
            "snapshot was written, so nothing here establishes convergence — "
            "set write_interval to get a drift measurement" % case.iterations)
    return report, result


def run_wind(case_dir, case=None, info=None, timeout=3600):
    """Write, run and read a cross-flow case. Returns (report, WindForces|None).

    ⚠ The forces come from the SOLVER LOG, not from ``postProcessing``:
    measured on v2512 this function object reports to the log and writes no
    files under this configuration. The report therefore carries the log tail
    that produced the numbers, so a reader can check them by eye.
    """
    case = write_wind(case_dir, case or WindCase())
    steps = WIND_TRANSIENT_STEPS if case.transient else WIND_STEPS
    app = steps[-1]
    report = run_chain(case_dir, info=info, steps=steps, timeout=timeout)
    report["case"] = {"reynolds": case.reynolds, "d_ref": case.d_ref,
                      "u_inf": case.u_inf, "q_ref": case.q_ref,
                      "radius_ratio": case.radius_ratio,
                      "steady_is_valid": case.steady_is_valid,
                      "transient": case.transient,
                      "method_is_valid": case.method_is_valid}
    # ⚠ Surfaced whether or not it is asked for: a drag number produced above
    # the shedding onset is not a wind load, and the caller must not have to
    # know that to be told.
    note = case.validity_note()
    if note:
        report["validity"] = note
    if not report["ok"]:
        return report, None

    solve = [s for s in report["steps"] if s["step"] == app]
    report["converged"] = bool(solve and solve[0]["converged"])
    log_path = os.path.join(case_dir, "log." + app)

    if case.transient:
        # ⚠ ALWAYS the whole log, never the tail: the tail is the last few
        # thousand characters and a transient answer is the SHAPE of the
        # history, not its end. Reading the tail would give a handful of
        # samples off one arbitrary phase of the cycle.
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                hist = force_history_from_log(
                    fh.read(), case.q_ref, case.d_ref, case.u_inf,
                    settle_time=case.settle_time)
        except (OSError, ValueError) as exc:
            report.update(ok=False, failed_at="read", error=str(exc))
            return report, None
        report["cd"] = hist.cd_mean
        report["cl_amplitude"] = hist.cl_amplitude
        report["strouhal"] = hist.strouhal
        report["cycles_measured"] = hist.cycles_measured
        if note:
            hist.warnings.append(note)
        return report, hist

    try:
        result = forces_from_log(solve[0]["tail"] if solve else "", case.q_ref)
    except (IndexError, ValueError) as exc:
        # the tail is only the last 3000 chars; fall back to the whole log
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                result = forces_from_log(fh.read(), case.q_ref)
        except (OSError, ValueError):
            report.update(ok=False, failed_at="read", error=str(exc))
            return report, None
    if note:
        result.warnings.append(note)
    report["cd"], report["cl"] = result.cd, result.cl
    return report, result
