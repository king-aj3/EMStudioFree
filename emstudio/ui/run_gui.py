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


def _eta_text(state, done, total):
    """'42% — about 1 min 20 s left', or just the percent when it is too early.

    Deliberately coarse: a countdown that jitters every 200 ms reads as broken.
    """
    pct = 0 if total <= 0 else max(0.0, min(1.0, done / total))
    txt = "{0:.0f}%".format(pct * 100.0)
    elapsed = time.time() - state.t_start
    # Under 3 s of evidence, or under 5% done, any estimate is a guess.
    if elapsed < 3.0 or pct < 0.05 or pct >= 1.0:
        return txt
    remain = elapsed * (1.0 - pct) / pct
    if remain < 10:
        return txt + " — a few seconds left"
    if remain < 90:
        return txt + " — about {0:.0f} s left".format(remain / 5.0 * 5.0)
    mins = remain / 60.0
    if mins < 60:
        return txt + " — about {0:.0f} min left".format(mins)
    return txt + " — over an hour left"


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


def run_solver_gui(analysis, solver_obj, run_fn, parent=None):
    """Run ``run_fn(analysis, solver_obj, line_callback)`` off the GUI thread.

    Shows an indeterminate progress dialog with Cancel; on success opens the
    SweepResultsDialog.
    """
    state = _JobState()

    line_cb = _Reporter(state, "solver")

    def work():
        try:
            state.result = run_fn(analysis, solver_obj, line_cb)
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
    from emstudio.ui.results_dialog import SweepResultsDialog

    SweepResultsDialog(result, parent=parent).exec()
