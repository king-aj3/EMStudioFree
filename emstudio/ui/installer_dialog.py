# SPDX-License-Identifier: LGPL-2.1-or-later
"""Guided solver installer — the first-run / Detect Solvers wizard.

Shows every backend with its detection status, the ONE sudo apt line that
covers all missing packages and build prerequisites (copy button — EMStudio
never runs sudo itself), and a Build button per missing source-built backend
that runs the no-sudo build recipe (``emstudio.setup.solvers.run_build``) in
a background thread with the compiler output streamed into the dialog.
Prerequisites are preflighted BEFORE any compile starts.

On native Windows the from-source build buttons are replaced by the per-backend
guidance from ``WINDOWS_HINTS`` — except backends whose upstream publishes real
prebuilt Windows binaries, which get an Install button instead
(``solvers.run_win_install``: stdlib download + extract, per-user, no admin).
"""

from __future__ import annotations

import os
import threading

import FreeCAD
from PySide import QtCore, QtGui, QtWidgets

from emstudio.setup import solvers

#: preference flag so the first-run popup fires only once
_FIRST_RUN_FLAG = "InstallerFirstRunShown"


class SolverInstallerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_win = os.name == "nt"
        self.setWindowTitle("EMStudio — Solver Setup")
        self.resize(760, 620)
        self._job = None
        self._busy_key = None
        self._state = None  # {"done", "error", "lines"} while a build runs

        layout = QtWidgets.QVBoxLayout(self)
        if self._is_win:
            intro_text = (
                "EMStudio drives open-source solvers as separate programs. "
                "This window shows which are installed. Backends with an "
                "Install button download the official prebuilt Windows binaries "
                "for you (per-user, no admin rights). For the rest, see Details "
                "/ the Report view — or install FreeCAD + EMStudio inside WSL2 "
                "(Ubuntu) for the complete toolchain.")
        else:
            intro_text = (
                "EMStudio drives open-source solvers as separate programs. "
                "This wizard finds them, gives you ONE copy-paste command for the "
                "packages that need sudo, and builds the from-source backends for "
                "you (no sudo needed for the builds).")
        intro = QtWidgets.QLabel(intro_text, self)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QtWidgets.QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Backend", "Status", "Details", ""])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        layout.addWidget(self.table, 2)

        # apt one-liner + guided builds are Linux-only; hidden entirely on Windows
        self.apt_row_widget = QtWidgets.QWidget(self)
        apt_row = QtWidgets.QHBoxLayout(self.apt_row_widget)
        apt_row.setContentsMargins(0, 0, 0, 0)
        self.apt_edit = QtWidgets.QLineEdit(self)
        self.apt_edit.setReadOnly(True)
        self.apt_edit.setPlaceholderText("(nothing missing that apt can provide)")
        self.pkg_label = QtWidgets.QLabel("sudo step:", self)
        apt_row.addWidget(self.pkg_label)
        apt_row.addWidget(self.apt_edit, 1)
        self.copy_btn = QtWidgets.QPushButton("Copy", self)
        self.copy_btn.setToolTip(
            "Copy the apt command — run it in a terminal, then Re-detect. "
            "EMStudio never runs sudo itself.")
        self.copy_btn.clicked.connect(self._copy_apt)
        apt_row.addWidget(self.copy_btn)
        layout.addWidget(self.apt_row_widget)

        self.log = QtWidgets.QPlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setFont(QtGui.QFont("Monospace"))
        self.log.setMaximumBlockCount(5000)
        self.log.setPlaceholderText("Build output appears here…")
        layout.addWidget(self.log, 3)

        if self._is_win:
            # No apt line on Windows. The log pane STAYS: guided installs
            # stream their download/extract progress into it.
            self.apt_row_widget.setVisible(False)

        buttons = QtWidgets.QHBoxLayout()
        self.redetect_btn = QtWidgets.QPushButton("Re-detect", self)
        self.redetect_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.redetect_btn)
        self.abort_btn = QtWidgets.QPushButton("Abort build", self)
        self.abort_btn.setEnabled(False)
        self.abort_btn.clicked.connect(self._abort)
        self.abort_btn.setVisible(not self._is_win)  # no builds on Windows
        buttons.addWidget(self.abort_btn)
        buttons.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll)

        self.refresh()

    # -- table ---------------------------------------------------------------

    def refresh(self):
        plan = solvers.install_plan()
        rows = [(info, None) for info in plan["found"]]
        rows += [(m["info"], m) for m in plan["missing"]]
        rows.sort(key=lambda r: list(solvers.BACKENDS).index(r[0].backend.key))
        # macOS gets a brew line, Linux an apt line; install_plan() guarantees
        # at most one is non-empty, so a Mac never sees a sudo apt command.
        pkg_line = plan.get("brew_line") or plan["apt_line"]
        self.pkg_label.setText("brew step:" if plan.get("brew_line")
                               else "sudo step:")
        self.apt_edit.setText(pkg_line)
        self.copy_btn.setEnabled(bool(pkg_line))

        self.table.setRowCount(len(rows))
        for i, (info, miss) in enumerate(rows):
            b = info.backend
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(b.label))
            status = QtWidgets.QTableWidgetItem("found" if info.found else "MISSING")
            status.setForeground(QtGui.QBrush(
                QtGui.QColor("darkgreen" if info.found else "darkred")))
            self.table.setItem(i, 1, status)
            if info.found:
                detail = info.path + ((" — " + info.version) if info.version else "")
                if solvers.is_ephemeral_path(info.path):
                    detail += "  (bundled/ephemeral — re-detected each session)"
            elif os.name == "nt":
                detail = solvers.WINDOWS_HINTS.get(b.key, b.homepage)
            elif miss and not miss["prereqs_ok"]:
                _mac = solvers._is_mac()
                detail = "needs packages first: " + ", ".join(
                    (p.brew if _mac else p.apt)
                    for p in miss["missing_prereqs"]
                    if (p.brew if _mac else p.apt))
            elif solvers._is_mac():
                detail = solvers.MACOS_HINTS.get(b.key, b.homepage)
            elif b.apt_package and not b.source_build:
                detail = "in the sudo step below (apt: {0})".format(b.apt_package)
            else:
                detail = b.manual_hint.splitlines()[0] if b.manual_hint else b.homepage
            item = QtWidgets.QTableWidgetItem(detail)
            item.setToolTip(detail if info.found else (miss or {}).get("steps", detail))
            self.table.setItem(i, 2, item)

            self.table.setCellWidget(i, 3, None)
            bplan = solvers.build_plan(b.key)
            if not info.found and bplan is not None:
                btn = QtWidgets.QPushButton("Build…", self.table)
                btn.setToolTip("Runs the no-sudo source build ({0}); output "
                               "streams below.".format(bplan["estimate"]))
                if miss and not miss["prereqs_ok"]:
                    btn.setEnabled(False)
                    btn.setToolTip("Install the sudo-step packages first, then "
                                   "Re-detect — the build is preflighted so it "
                                   "will not fail mid-compile.")
                btn.clicked.connect(lambda _=False, key=b.key: self._build(key))
                self.table.setCellWidget(i, 3, btn)
            elif not info.found and solvers.win_install_plan(b.key) is not None:
                wplan = solvers.win_install_plan(b.key)
                btn = QtWidgets.QPushButton("Install…", self.table)
                btn.setToolTip(
                    "Downloads the official Windows build ({0}); progress "
                    "streams below. Per-user, no admin rights needed.".format(
                        wplan["estimate"]))
                btn.clicked.connect(
                    lambda _=False, key=b.key: self._win_install(key))
                self.table.setCellWidget(i, 3, btn)

    def _copy_apt(self):
        QtWidgets.QApplication.clipboard().setText(self.apt_edit.text())
        FreeCAD.Console.PrintMessage("EMStudio: apt command copied to clipboard.\n")

    # -- builds ----------------------------------------------------------------

    def _build(self, key):
        if self._busy_key:
            return
        bplan = solvers.build_plan(key)
        label = solvers.BACKENDS[key].label
        answer = QtWidgets.QMessageBox.question(
            self, "EMStudio — build {0}?".format(label),
            "Build {0} from source now?\n\nEstimated time: {1}\nInstalls to: {2}\n\n"
            "No sudo is used; you can keep working while it runs.".format(
                label, bplan["estimate"], bplan["prefix"]),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if answer != QtWidgets.QMessageBox.Yes:
            return

        self._busy_key = key
        self._state = {"done": False, "error": None, "lines": []}
        state = self._state
        lock = threading.Lock()

        def line_cb(line):
            with lock:
                state["lines"].append(line)

        def job_slot(job):
            self._job = job

        def work():
            try:
                solvers.run_build(key, line_callback=line_cb, job_slot=job_slot)
            except Exception as exc:  # noqa: BLE001 — surfaced in the dialog
                state["error"] = exc
            finally:
                state["done"] = True

        self.log.appendPlainText("=== building {0} ===".format(label))
        self.abort_btn.setEnabled(True)
        self.redetect_btn.setEnabled(False)
        self._lock = lock
        threading.Thread(target=work, daemon=True).start()
        self._timer.start(300)

    def _win_install(self, key):
        """Guided Windows install — official prebuilt download, in a thread."""
        if self._busy_key:
            return
        wplan = solvers.win_install_plan(key)
        label = solvers.BACKENDS[key].label
        answer = QtWidgets.QMessageBox.question(
            self, "EMStudio — install {0}?".format(label),
            "Download and install {0} now?\n\nEstimated time: {1}\n"
            "Installs to: {2}\n\nOfficial upstream binaries, per-user, no "
            "admin rights needed.".format(
                label, wplan["estimate"],
                os.path.join(solvers.win_install_root(), key)),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if answer != QtWidgets.QMessageBox.Yes:
            return

        self._busy_key = key
        self._state = {"done": False, "error": None, "lines": []}
        state = self._state
        lock = threading.Lock()

        def line_cb(line):
            with lock:
                state["lines"].append(line)

        def work():
            try:
                solvers.run_win_install(key, line_callback=line_cb)
            except Exception as exc:  # noqa: BLE001 — surfaced in the dialog
                state["error"] = exc
            finally:
                state["done"] = True

        self.log.appendPlainText("=== installing {0} ===".format(label))
        self.redetect_btn.setEnabled(False)
        self._lock = lock
        threading.Thread(target=work, daemon=True).start()
        self._timer.start(300)

    def _poll(self):
        state = self._state
        if state is None:
            return
        with self._lock:
            lines, state["lines"] = state["lines"], []
        for line in lines:
            self.log.appendPlainText(line)
        if not state["done"]:
            return
        self._timer.stop()
        self.abort_btn.setEnabled(False)
        self.redetect_btn.setEnabled(True)
        key, self._busy_key = self._busy_key, None
        self._job = None
        if state["error"] is not None:
            self.log.appendPlainText("=== FAILED: {0} ===".format(state["error"]))
            QtWidgets.QMessageBox.critical(
                self, "EMStudio — build failed", str(state["error"]))
        else:
            self.log.appendPlainText("=== done ===")
        self._state = None
        self.refresh()
        if key:
            FreeCAD.Console.PrintMessage(
                "EMStudio: build of '{0}' finished.\n".format(key))

    def _abort(self):
        if self._job is not None:
            self._job.abort()
            self.log.appendPlainText("=== abort requested ===")

    def closeEvent(self, event):
        if self._busy_key:
            answer = QtWidgets.QMessageBox.question(
                self, "EMStudio", "A build is still running — abort it?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if answer != QtWidgets.QMessageBox.Yes:
                event.ignore()
                return
            self._abort()
        super().closeEvent(event)


def maybe_show_first_run(parent=None):
    """Show the wizard once, on first activation, if backends are missing.

    Never raises (called from the workbench Activated hook, where exceptions
    would be swallowed and could destabilize activation).
    """
    try:
        params = FreeCAD.ParamGet(solvers.PREF_GROUP)
        if params.GetBool(_FIRST_RUN_FLAG, False):
            return None
        params.SetBool(_FIRST_RUN_FLAG, True)
        if not solvers.install_plan()["missing"]:
            return None
        dlg = SolverInstallerDialog(parent=parent)
        dlg.show()  # non-modal: don't block workbench activation
        return dlg
    except Exception as exc:  # noqa: BLE001 — first-run popup is best-effort
        try:
            FreeCAD.Console.PrintWarning(
                "EMStudio: first-run installer skipped: {0}\n".format(exc))
        except Exception:
            pass
        return None
