# SPDX-License-Identifier: LGPL-2.1-or-later
"""Results dialog for Elmer magnetics runs (induction heating / WPT).

Shows the engineering summary (powers, L/M/k, reflected R) and offers to
load the field VTU (B field, Joule heating) into the 3-D viewport as a
FemPostPipeline — the same display path the antenna results use.
"""

from __future__ import annotations

import os

from PySide import QtCore, QtGui, QtWidgets


class MagneticsResultsDialog(QtWidgets.QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle("EMStudio — Magnetics Results")
        self.resize(640, 480)

        layout = QtWidgets.QVBoxLayout(self)
        # Quasi-static frequency-validity warning (if the guard fired): a
        # prominent banner so the user sees when the magnetics solve was set up
        # outside its electrically-small regime (see emstudio.solvers.validity).
        warning = result.meta.get("frequency_warning") if hasattr(result, "meta") else None
        if warning:
            banner = QtWidgets.QLabel("⚠ " + warning, self)
            banner.setWordWrap(True)
            banner.setStyleSheet(
                "QLabel { background: #7a5900; color: #fff; padding: 8px; "
                "border-radius: 4px; }")
            layout.addWidget(banner)
        text = QtWidgets.QPlainTextEdit(self)
        text.setReadOnly(True)
        text.setFont(QtGui.QFont("Monospace"))
        text.setPlainText(result.summary_text())
        layout.addWidget(text)

        buttons = QtWidgets.QHBoxLayout()
        show_btn = QtWidgets.QPushButton("Show Fields in 3D", self)
        show_btn.setToolTip(
            "Load the solved B field / Joule heating into the 3-D viewport "
            "(colored surface, rotate/zoom with the geometry)")
        show_btn.clicked.connect(self._show_fields)
        buttons.addWidget(show_btn)
        report_btn = QtWidgets.QPushButton("Save PDF Report…", self)
        report_btn.setToolTip("A build-house-ready document: summary, r–z "
                              "cross-section, |B| field map, and results/BOM.")
        report_btn.clicked.connect(self._save_report)
        buttons.addWidget(report_btn)
        open_btn = QtWidgets.QPushButton("Open Work Folder", self)
        open_btn.clicked.connect(self._open_workdir)
        buttons.addWidget(open_btn)
        buttons.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _show_fields(self):
        import FreeCAD

        from emstudio.post import vtk_out

        sweeps = self.result.sweep_cases()
        if not sweeps:
            return
        case = sweeps[0]
        label = "Magnetics fields ({0:.4g} Hz)".format(case["freq_hz"])
        try:
            vtk_out.show_in_freecad(case["vtu"], label)
            if FreeCAD.GuiUp:
                import FreeCADGui

                FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception as exc:  # noqa: BLE001 — display is best-effort
            QtWidgets.QMessageBox.warning(
                self, "EMStudio", "Could not load the VTU:\n{0}".format(exc))

    def _save_report(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDF report", os.path.expanduser("~/magnetics_report.pdf"),
            "PDF (*.pdf)")
        if not path:
            return
        try:
            from emstudio.report import magnetics_report

            title = self.result.meta.get("analysis", "Magnetics Analysis")
            magnetics_report(self.result, path, title=title)
            QtWidgets.QMessageBox.information(self, "EMStudio", "Saved report:\n" + path)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            QtWidgets.QMessageBox.critical(self, "EMStudio",
                                           "Report failed: {0}".format(exc))

    def _open_workdir(self):
        workdir = self.result.meta.get("workdir", "")
        if workdir:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(workdir))
