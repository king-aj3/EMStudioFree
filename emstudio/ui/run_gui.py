# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI solver execution: background thread + progress dialog + results plot.

Keeps the FreeCAD UI responsive while a backend runs. The solver pipeline executes in
a Python thread; a QTimer polls for completion; solver output lines stream to the
Report view. Cancel terminates the solver process.
"""

from __future__ import annotations

import threading
import time

import FreeCAD
from PySide import QtCore, QtWidgets


#: Last successful result per analysis Name. A solve is expensive and the
#: results dialog was ONLY reachable from the run that produced it — close it
#: and the numbers were gone until you paid for the whole solve again. Keeping
#: the object costs nothing (it is already in memory) and turns "Show Results"
#: into a lookup. In-process only: a FreeCAD restart clears it, which is
#: honest, because nothing is persisted to the document.
_LAST_RESULTS = {}


def remember_result(analysis, result):
    """Record a completed result so Show Results can reopen it."""
    key = getattr(analysis, "Name", None)
    if key and result is not None:
        _LAST_RESULTS[key] = result


def last_result(analysis):
    """The last result for this analysis in THIS session, or None."""
    return _LAST_RESULTS.get(getattr(analysis, "Name", None))


class _JobState:
    def __init__(self):
        self.result = None
        self.error = None
        self.done = False
        self.abort_cb = None
        #: (done, total, note) from the worker, or None while unknown.
        self.progress = None
        self.t_start = time.time()


class _Reporter:
    """What a worker is handed to talk back with.

    It is CALLABLE, so every existing worker that just does ``log("...")``
    keeps working untouched — there are two dozen call sites and none of them
    needed changing. Workers that can say how far along they are call
    ``log.progress(done, total, note)`` and the dialog stops being a
    meaningless swinging bar.

    WHY: an indeterminate bar tells the user nothing except "not hung". On a
    job that can run for minutes — the centreline march over a large solid is
    the standard example — the two things worth knowing are how much is left
    and roughly how long that is. Both are cheap once the worker reports a
    fraction.
    """

    def __init__(self, state, prefix):
        self._state = state
        self._prefix = prefix

    def __call__(self, line):
        FreeCAD.Console.PrintMessage("[{0}] {1}\n".format(self._prefix, line))

    def progress(self, done, total, note=""):
        """Report progress. ``total`` <= 0 means 'still unknown'."""
        try:
            self._state.progress = (float(done), float(total), str(note))
        except (TypeError, ValueError):
            pass


def _clock(seconds):
    """A duration a human reads at a glance: '45 s', '3 min 07 s', '1 h 12 m'."""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return "{0:.0f} s".format(seconds)
    if seconds < 3600:
        return "{0:.0f} min {1:02.0f} s".format(seconds // 60, seconds % 60)
    return "{0:.0f} h {1:02.0f} m".format(seconds // 3600, (seconds % 3600) // 60)


def _eta_text(state, done, total):
    """The four numbers AJ asked for: done, to go, elapsed, and the ETA.

    ``42% done  ·  58% to go  ·  elapsed 1 min 20 s  ·  about 2 min left``

    Elapsed is shown from the FIRST report — it is a measured fact and always
    honest. The ETA is not: it extrapolates, so it is withheld until there is
    enough evidence to be worth reading (3 s and 5 % done). An estimate
    offered at 1 % is off by whatever the first mesh happened to cost, and a
    number that swings from "8 hours" to "20 s" teaches the user to ignore
    the field. Better to show three true numbers and add the fourth when it
    means something.

    The ETA is also deliberately COARSE — rounded to 5 s, then whole minutes.
    A countdown re-rendered every 200 ms that ticks 97, 94, 96, 91 reads as
    broken even when it is perfectly accurate.
    """
    pct = 0.0 if total <= 0 else max(0.0, min(1.0, done / total))
    elapsed = time.time() - state.t_start
    parts = ["{0:.0f}% done".format(pct * 100.0),
             "{0:.0f}% to go".format((1.0 - pct) * 100.0),
             "elapsed " + _clock(elapsed)]
    if elapsed < 3.0 or pct < 0.05 or pct >= 1.0:
        return "  ·  ".join(parts)
    remain = elapsed * (1.0 - pct) / pct
    if remain < 10:
        eta = "a few seconds left"
    elif remain < 90:
        eta = "about {0:.0f} s left".format(round(remain / 5.0) * 5.0)
    elif remain < 3600:
        eta = "about {0:.0f} min left".format(remain / 60.0)
    else:
        eta = "about " + _clock(remain) + " left"
    parts.append(eta)
    return "  ·  ".join(parts)


def _apply_progress(dlg, state, label):
    """Move the dialog from indeterminate to a REAL bar once numbers arrive."""
    p = state.progress
    if not p:
        return
    done, total, note = p
    if total <= 0:
        return
    if dlg.maximum() == 0:                   # first real report: switch modes
        dlg.setRange(0, 1000)
    dlg.setValue(int(max(0.0, min(1.0, done / total)) * 1000))
    head = note or label
    dlg.setLabelText("{0}\n{1}".format(head, _eta_text(state, done, total)))


def _remember_and_finish(state, parent, analysis):
    if state.error is None and state.result is not None:
        remember_result(analysis, state.result)
    _finish(state, parent)


#: Preference that mutes the pre-solve estimate dialog, like the Pattern
#: Frequencies prompt. Muting is per-user and never per-run: a user who has
#: seen it once should not have to keep dismissing it.
MUTE_PREF = "MuteSolveEstimate"


def confirm_solve_work(parent, backend, work, label=""):
    """Pre-solve estimate for a caller that knows its own work measure.

    The parametric CFD dialogs have no analysis or solver object to read a size
    from — they are typed-in stacks — so they state their work directly. Those
    are also the LONGEST solves in the product (the CHT dialog's own docs say
    tens of minutes), which makes them the ones that most need asking first.
    """
    try:
        from emstudio.solvers import estimate as est

        params = None
        try:
            import FreeCAD as _FC
            params = _FC.ParamGet(est.PREF_GROUP)
            if params.GetBool(MUTE_PREF, False):
                return True
        except Exception:                                  # noqa: BLE001
            params = None

        hist = est.freecad_history()
        box = QtWidgets.QMessageBox(parent)
        box.setWindowTitle("EMStudio")
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setText("Run {0}?".format(label or backend))
        box.setInformativeText(
            "{0}\n\nProgress is reported as a percentage with a live ETA "
            "once the solve is under way, and Cancel stops it.".format(
                est.describe(backend, work, hist)))
        run_btn = box.addButton("Run solver", QtWidgets.QMessageBox.AcceptRole)
        box.addButton(QtWidgets.QMessageBox.Cancel)
        mute = QtWidgets.QCheckBox("Don't ask again")
        box.setCheckBox(mute)
        box.exec_()
        if params is not None and mute.isChecked():
            params.SetBool(MUTE_PREF, True)
        return box.clickedButton() is run_btn
    except Exception as exc:                               # noqa: BLE001
        FreeCAD.Console.PrintWarning(
            "EMStudio: pre-solve estimate unavailable ({0}); running anyway.\n"
            .format(exc))
        return True


def record_solve_work(backend, work, seconds):
    """Remember a completed solve whose caller knows its own work measure."""
    try:
        from emstudio.solvers import estimate as est
        est.freecad_history().record(backend, work, seconds)
    except Exception:                                      # noqa: BLE001
        pass


def confirm_solve(parent, backend, analysis, solver_obj=None, label=""):
    """Show what this solve is expected to cost, and let the user back out.

    Returns True to proceed. Answers the question a user actually has before
    a long run — thirty seconds or forty minutes — using measured history and
    saying plainly when there is none. See :mod:`emstudio.solvers.estimate`
    for why it does not fall back to a cost model.

    Never blocks a solve on its own failure: anything unexpected here returns
    True, because a broken estimate must not stop work.
    """
    try:
        from emstudio.solvers import estimate as est

        params = None
        try:
            import FreeCAD as _FC
            params = _FC.ParamGet(est.PREF_GROUP)
            if params.GetBool(MUTE_PREF, False):
                return True
        except Exception:                                  # noqa: BLE001
            params = None

        return confirm_solve_work(parent, backend,
                                  est.work_of(analysis, solver_obj), label)
    except Exception as exc:                               # noqa: BLE001
        FreeCAD.Console.PrintWarning(
            "EMStudio: pre-solve estimate unavailable ({0}); running anyway.\n"
            .format(exc))
        return True


def record_solve(backend, analysis, solver_obj, result):
    """Remember how long a completed solve took, for the next estimate.

    Best effort by construction — a result with no duration, or an unwritable
    preference, simply teaches it nothing.
    """
    try:
        from emstudio.solvers import estimate as est

        secs = (result.meta or {}).get("duration_s")
        est.freecad_history().record(
            backend, est.work_of(analysis, solver_obj), secs)
    except Exception:                                      # noqa: BLE001
        pass


def run_solver_gui(analysis, solver_obj, run_fn, parent=None):
    """Run ``run_fn(analysis, solver_obj, line_callback)`` off the GUI thread.

    Shows an indeterminate progress dialog with Cancel; on success opens the
    SweepResultsDialog.
    """
    backend = str(getattr(solver_obj, "Backend", "") or
                  getattr(solver_obj, "Label", "solver"))
    if not confirm_solve(parent, backend, analysis, solver_obj,
                         label=getattr(solver_obj, "Label", backend)):
        FreeCAD.Console.PrintMessage("EMStudio: solve cancelled before it "
                                     "started.\n")
        return _JobState()

    state = _JobState()

    line_cb = _Reporter(state, "solver")

    def work():
        try:
            state.result = run_fn(analysis, solver_obj, line_cb)
            record_solve(backend, analysis, solver_obj, state.result)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user below
            state.error = exc
        finally:
            state.done = True

    dlg = QtWidgets.QProgressDialog(
        "Running {0}…".format(solver_obj.Label), "Cancel", 0, 0, parent
    )
    dlg.setWindowTitle("EMStudio")
    dlg.setWindowModality(QtCore.Qt.WindowModal)
    dlg.setMinimumDuration(0)

    thread = threading.Thread(target=work, daemon=True)
    thread.start()

    timer = QtCore.QTimer(dlg)

    def poll():
        if state.done:
            timer.stop()
            dlg.reset()
            dlg.close()
            _remember_and_finish(state, parent, analysis)
            return
        _apply_progress(dlg, state, "Running {0}".format(solver_obj.Label))
        if dlg.wasCanceled():
            if state.abort_cb:
                state.abort_cb()
            timer.stop()
            FreeCAD.Console.PrintWarning("EMStudio: solver run canceled by user.\n")

    timer.timeout.connect(poll)
    timer.start(200)
    dlg.show()
    return state


def run_generic_gui(label, run_fn, on_success, parent=None,
                    on_error=None, on_cancel=None):
    """Run ``run_fn(None, None, line_cb)`` off the GUI thread with a progress dialog.

    On success calls ``on_success(result)``; on error shows a message box. Used for
    non-solver background work (e.g. FastHenry current-sharing sweeps).

    :param on_error: optional callback ``(exc)`` invoked (after the message box)
        when ``run_fn`` raises — callers use it to release resources they set up
        before dispatching (e.g. a scratch document). Defaults to no-op.
    :param on_cancel: optional callback ``()`` invoked when the user cancels.
        The worker thread is a daemon and keeps running to completion; the
        callback lets the caller mark the run abandoned. Defaults to no-op.
    """
    state = _JobState()

    line_cb = _Reporter(state, "emstudio")

    def work():
        try:
            state.result = run_fn(None, None, line_cb)
        except Exception as exc:  # noqa: BLE001
            state.error = exc
        finally:
            state.done = True

    dlg = QtWidgets.QProgressDialog(label + "…", "Cancel", 0, 0, parent)
    dlg.setWindowTitle("EMStudio")
    dlg.setWindowModality(QtCore.Qt.WindowModal)
    dlg.setMinimumDuration(0)
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    timer = QtCore.QTimer(dlg)

    def poll():
        if state.done:
            timer.stop()
            dlg.reset()
            dlg.close()
            if state.error is not None:
                QtWidgets.QMessageBox.critical(parent, "EMStudio — failed", str(state.error))
                if on_error is not None:
                    on_error(state.error)
            else:
                on_success(state.result)
            return
        _apply_progress(dlg, state, label)
        if dlg.wasCanceled():
            timer.stop()
            FreeCAD.Console.PrintWarning("EMStudio: canceled by user.\n")
            if on_cancel is not None:
                on_cancel()

    timer.timeout.connect(poll)
    timer.start(200)
    dlg.show()
    return state


def _finish(state, parent):
    if state.error is not None:
        QtWidgets.QMessageBox.critical(
            parent, "EMStudio — solver failed", str(state.error)
        )
        return
    result = state.result
    f_min, s11_min = result.min_s11()
    FreeCAD.Console.PrintMessage(
        "EMStudio: solve finished in {0:.2f}s — best match {1:.2f} dB at {2:.3f} MHz "
        "(results in {3})\n".format(
            result.meta.get("duration_s", -1.0),
            s11_min,
            f_min / 1e6,
            result.meta.get("workdir", "?"),
        )
    )
    from emstudio.ui.results_dialog import show_sweep_results

    # Non-modal on purpose: the results feed the 3-D viewport (balloon +
    # floating scrubber), and a modal dialog would input-block both.
    show_sweep_results(result, parent=parent)
