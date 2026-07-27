# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI solver execution: background thread + progress dialog + results plot.

Keeps the FreeCAD UI responsive while a backend runs. The solver pipeline executes in
a Python thread; a QTimer polls for completion; solver output lines stream to the
Report view. Cancel terminates the solver process.
"""

from __future__ import annotations

import threading

import FreeCAD
from PySide import QtCore, QtWidgets


class _JobState:
    def __init__(self):
        self.result = None
        self.error = None
        self.done = False
        self.abort_cb = None


def run_solver_gui(analysis, solver_obj, run_fn, parent=None):
    """Run ``run_fn(analysis, solver_obj, line_callback)`` off the GUI thread.

    Shows an indeterminate progress dialog with Cancel; on success opens the
    SweepResultsDialog.
    """
    state = _JobState()

    def line_cb(line):
        FreeCAD.Console.PrintMessage("[solver] {0}\n".format(line))

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
            _finish(state, parent)
        elif dlg.wasCanceled():
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

    def line_cb(line):
        FreeCAD.Console.PrintMessage("[emstudio] {0}\n".format(line))

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
        elif dlg.wasCanceled():
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
