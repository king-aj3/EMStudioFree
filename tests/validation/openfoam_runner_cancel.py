# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — run_chain cancellation actually stops the chain.

FAST tier: no OpenFOAM needed. The chain is driven against a FAKE install
whose bashrc is an empty file, so the "steps" are plain shell commands — a
long ``sleep`` stands in for a multi-minute solver step.

Exists because the convection dialog shipped a Cancel button that could not
work: the solve ran synchronously on the GUI thread, so the click that was
meant to stop it queued behind it (AJ, 2026-08-17). The cancellation now
lives in ``run_chain``, and this gate proves three things a green dialog
cannot:

* a fired cancel returns PROMPTLY, not at the step's natural end,
* the report says ``cancelled=True`` — distinct from a failed step,
* ⚠ the step's CHILD process dies too. Each step is a sourcing bash whose
  child is the real solver; killing the bash alone ORPHANS the solver, which
  keeps burning CPU behind a "cancelled" UI. The kill is therefore a
  process-group kill, and the child-is-dead check here is the one that fails
  if that regresses.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(label, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", label,
                                 " - " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


class _FakeInfo:
    """Just enough of an OpenFoamInfo for `_command` to build a bash argv."""

    found = True
    fork = "esi"
    native_root = ""
    wsl_distro = ""

    def __init__(self, bashrc):
        self.bashrc = bashrc

    def describe(self):
        return "fake OpenFOAM (cancellation gate)"


def main():
    from emstudio.solvers.openfoam import runner

    print("EMStudio run_chain cancellation gate")
    if os.name == "nt":
        # The live checks drive a real `bash`; the Windows boxes reach bash
        # only through MSYS/WSL installs this gate must not depend on.
        print("  skip: live-subprocess checks are POSIX-only")
        return 0

    wd = tempfile.mkdtemp(prefix="emstudio-cancelgate-")
    try:
        _checks(wd)
    finally:
        shutil.rmtree(wd, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-RUNNER-CANCEL GATE PASSED")
    return 0


def _checks(wd):
    from emstudio.solvers.openfoam import runner

    bashrc = os.path.join(wd, "bashrc")
    with open(bashrc, "w") as fh:
        fh.write("# empty on purpose: sourcing this is a no-op\n")
    info = _FakeInfo(bashrc)

    # --- control: an uncancelled chain still runs and reports ok -----------
    rep = runner.run_chain(wd, info=info, steps=("true",), timeout=60)
    check("control chain (no cancel) completes ok",
          rep.get("ok") is True and not rep.get("cancelled"),
          str({k: rep.get(k) for k in ("ok", "failed_at", "error")}))

    # --- cancel mid-step: must stop THE WHOLE TREE, promptly ---------------
    marker = "sleep 987.653"            # unique argv, ps-greppable
    cancel = threading.Event()
    threading.Timer(0.7, cancel.set).start()
    t0 = time.monotonic()
    rep = runner.run_chain(wd, info=info, steps=(marker,), timeout=120,
                           cancel=cancel)
    elapsed = time.monotonic() - t0
    check("cancelled chain returns promptly", elapsed < 15.0,
          "%.1f s (the step alone would run ~987 s)" % elapsed)
    check("report says cancelled, not merely failed",
          rep.get("cancelled") is True and rep.get("ok") is False
          and rep.get("failed_at") == marker,
          str({k: rep.get(k) for k in ("ok", "cancelled", "failed_at",
                                       "error")}))

    # ⚠ The CHILD must be dead, not orphaned. Give the group kill a moment,
    # then look for the child's EXACT argv in the process table. Exact
    # equality, not substring: any harness that carries this gate's source
    # text on ITS command line (a heredoc, a -c string) would otherwise match
    # itself and report a phantom orphan — measured, first run of this gate.
    time.sleep(1.0)
    ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True)
    alive = [ln for ln in ps.stdout.splitlines() if ln.strip() == marker]
    check("the step's child process is dead (no orphaned solver)",
          not alive, "; ".join(alive[:3]))
    if alive:                           # never leave a stray behind on a FAIL
        subprocess.run(["pkill", "-f", marker])

    # --- run_cht THREADS cancel through — both chains ----------------------
    # The mechanism above lives in run_chain; the CHT dialog's "real Cancel"
    # headline additionally depends on run_cht PASSING cancel to its two
    # run_chain calls. Dropping either `cancel=cancel` reverts to the
    # pre-08-17 uncancellable behavior with the whole battery green — this
    # pins the plumbing. The chain steps are monkeypatched to sleeps (the
    # chain itself is proven above); write_region_fields is stubbed for the
    # solve-phase case because only a genuinely split mesh has the interface
    # patches it discovers — the subject here is cancel/cancelled PLUMBING.
    from emstudio.solvers.openfoam.cht import ChtCase

    tiny = ChtCase(n_solid=3, n_fluid=3, iterations=10)
    real_mesh = runner.CHT_MESH_STEPS
    real_solve = runner.CHT_SOLVE_STEPS
    real_wrf = runner.write_region_fields
    try:
        # (a) cancel during the MESH chain
        runner.CHT_MESH_STEPS = ("sleep 987.654",)
        cancel = threading.Event()
        threading.Timer(0.7, cancel.set).start()
        t0 = time.monotonic()
        wd_a = os.path.join(wd, "cht_a")
        rep, means = runner.run_cht(wd_a, tiny, info=info, timeout=120,
                                    cancel=cancel)
        check("run_cht cancels during the mesh chain, promptly",
              time.monotonic() - t0 < 15.0 and means is None
              and rep.get("cancelled") is True and rep.get("ok") is False,
              str({k: rep.get(k) for k in ("ok", "cancelled", "failed_at")}))

        # (b) cancel during the SOLVE chain — and the ``cancelled`` marker
        # must SURVIVE into run_cht's merged report (it was dropped once).
        runner.CHT_MESH_STEPS = ("true",)
        runner.CHT_SOLVE_STEPS = ("sleep 987.655",)
        runner.write_region_fields = lambda case_dir, case=None: {}
        cancel = threading.Event()
        threading.Timer(0.7, cancel.set).start()
        t0 = time.monotonic()
        wd_b = os.path.join(wd, "cht_b")
        rep, means = runner.run_cht(wd_b, tiny, info=info, timeout=120,
                                    cancel=cancel)
        check("run_cht cancels during the solve chain, promptly",
              time.monotonic() - t0 < 15.0 and means is None
              and rep.get("ok") is False,
              str({k: rep.get(k) for k in ("ok", "cancelled", "failed_at")}))
        check("a solve-phase cancel reads as CANCELLED, not solver failure",
              rep.get("cancelled") is True,
              "run_chain's contract: cancelled distinguishes 'the user "
              "stopped it' from 'it broke' — run_cht must not drop it "
              "when merging the solve sub-report")
    finally:
        runner.CHT_MESH_STEPS = real_mesh
        runner.CHT_SOLVE_STEPS = real_solve
        runner.write_region_fields = real_wrf
    for m in ("sleep 987.654", "sleep 987.655"):
        subprocess.run(["pkill", "-f", m],
                       capture_output=True)  # hygiene; nothing should match


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("openfoam-runner-cancel validation failed")
    sys.exit(0)
