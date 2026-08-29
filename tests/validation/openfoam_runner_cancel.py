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

⚠ That child-is-dead check is an ABSENCE test, and an absence test is only
worth its exit code when the instrument can see a presence. Two ways it used
to read "pass" while proving nothing, both closed here:

* it never ran at all. ``main`` opened with ``if os.name == "nt": print(
  "skip"); return 0`` — and ``run_battery.FAST`` lists this gate with
  requirement ``None``, so on every Windows box the battery printed **ok** for
  a gate that had executed zero checks. The skip is now a NON-SUCCESS
  (``_SKIP_RC``) with its own token, so neither a battery run nor a hand run
  can read it as a pass. See ``_unavailable``.
* the probe was blind. ``ps -eo args`` returning nothing at all — no ``ps``,
  an empty table, an argv format the exact-match never matches — yields the
  same empty list as a correctly killed child. A POSITIVE CONTROL now proves
  the probe can see a live process of exactly that shape first.
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

#: Exit code for "this gate did NOT run". Distinct from 0 (a pass it earned)
#: and from 1 (a check that failed), so a hand run cannot be mistaken for
#: success and the battery cannot count it as ok.
#:
#: ⚠ ``run_battery.FAST`` currently declares this gate's requirement as
#: ``None``, so the battery has no honest "skip" line to print for it: on a
#: box that cannot run the gate the battery will now report FAIL rather than
#: ok. That is deliberate and it is the lesser evil — printing "ok" for a
#: gate that ran nothing is the 2026-08-05 defect class (see SOLVER_REQS in
#: run_battery.py). The proper cure is a declared prerequisite for this gate
#: in run_battery.py; until that exists, red-and-honest beats green-and-blind.
_SKIP_RC = 3


def _unavailable():
    """Why this gate cannot run on this box, or "" when it can.

    Probed UP FRONT, and reported by the caller as a NON-SUCCESS. The whole
    body of this gate drives a real ``bash`` and then reads a POSIX process
    table; there is no partial mode, so "cannot run" has to be said out loud
    rather than returned as a zero.
    """
    if os.name == "nt":
        # The live checks drive a real `bash`; the Windows boxes reach bash
        # only through MSYS/WSL installs this gate must not depend on, and
        # `ps -eo args` has no equivalent there (the Windows kill path is
        # `taskkill /T`, a different mechanism needing a different gate).
        return ("live-subprocess checks are POSIX-only (os.name={0!r}) — the "
                "cancellation path is exercised on Linux/macOS".format(os.name))
    # Probed with `shutil.which` BEFORE anything is launched, so a missing
    # tool reports itself by name instead of surfacing as a FileNotFoundError
    # traceback from somewhere in the middle of the chain.
    for tool in ("bash", "ps"):
        if shutil.which(tool) is None:
            return ("no {0!r} on PATH — the chain steps are bash and the "
                    "orphan check reads `ps -eo args`".format(tool))
    return ""


def _argv_alive(argv_line):
    """Process-table lines whose argv is EXACTLY ``argv_line``.

    Exact equality, not substring: any harness that carries this gate's source
    text on ITS command line (a heredoc, a ``-c`` string) would otherwise
    match itself and report a phantom orphan — measured, first run of this
    gate. Kept as one function so the orphan check and its positive control
    below cannot drift apart and ask the process table different questions.
    """
    ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True)
    return [ln for ln in ps.stdout.splitlines() if ln.strip() == argv_line]


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
    why = _unavailable()
    if why:
        print("  SKIP: {0}".format(why))
        print("")
        print("OPENFOAM-RUNNER-CANCEL GATE SKIPPED — NOT RUN, NOTHING PROVED")
        return _SKIP_RC

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
    # then look for the child's EXACT argv in the process table.
    time.sleep(1.0)

    # ⚠ POSITIVE CONTROL, and it is not ceremony. The check below passes on an
    # EMPTY match list — which is also what a blind probe returns: no `ps`, a
    # `ps` that errored, an argv rendering this exact-match can never equal.
    # Any of those would make the one check that catches an orphaned solver
    # pass on every box forever, which is precisely the regression this gate
    # exists to catch. So prove the instrument can see a live process of
    # exactly this shape before believing it that the real child is gone.
    # A distinct number (…998) so it can never collide with a chain marker,
    # and it is held by a handle we kill ourselves — never pkill'd by name.
    sentinel = subprocess.Popen(["sleep", "987.998"])
    try:
        time.sleep(0.4)
        seen = _argv_alive("sleep 987.998")
        check("orphan probe can SEE a live process (detector not blind)",
              bool(seen), "ps -eo args matched %d exact line(s)" % len(seen))
    finally:
        sentinel.kill()
        sentinel.wait()

    alive = _argv_alive(marker)
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
    if rc == _SKIP_RC:
        # SystemExit(int) so the DISTINCT code survives; a message-form
        # SystemExit would collapse it to 1 and lose "did not run" vs "failed".
        # Written to stderr as well because freecadcmd drops print() on exit.
        sys.stderr.write("openfoam-runner-cancel SKIPPED — the gate did not "
                         "run on this box and proved nothing\n")
        raise SystemExit(_SKIP_RC)
    if rc != 0:
        raise SystemExit("openfoam-runner-cancel validation failed")
    sys.exit(0)
