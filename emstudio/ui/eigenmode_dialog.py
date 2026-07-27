# SPDX-License-Identifier: LGPL-2.1-or-later
"""Results dialog for Palace eigenmode (resonant-cavity) analyses."""

from __future__ import annotations

import os

from PySide import QtGui, QtWidgets


class EigenModeResultsDialog(QtWidgets.QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle("EMStudio — Cavity Eigenmodes")
        self.resize(520, 460)

        layout = QtWidgets.QVBoxLayout(self)
        dom = result.dominant_ghz()
        if dom is not None:
            layout.addWidget(QtWidgets.QLabel(
                "Fundamental mode: <b>{0:.5f} GHz</b>   "
                "({1} modes computed)".format(dom, len(result.modes))))

        table = QtWidgets.QTableWidget(len(result.modes), 3, self)
        table.setHorizontalHeaderLabels(["Mode", "Frequency (GHz)", "Q"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for i, m in enumerate(result.modes):
            table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(m["index"])))
            table.setItem(i, 1, QtWidgets.QTableWidgetItem("{0:.6f}".format(m["freq_ghz"])))
            q = m["q"]
            q_txt = "∞" if q != q or q == float("inf") or q > 1e12 else "{0:.4g}".format(q)
            table.setItem(i, 2, QtWidgets.QTableWidgetItem(q_txt))
        layout.addWidget(table)

        buttons = QtWidgets.QHBoxLayout()
        csv_btn = QtWidgets.QPushButton("Export CSV…", self)
        csv_btn.clicked.connect(self._export_csv)
        buttons.addWidget(csv_btn)
        open_btn = QtWidgets.QPushButton("Open Work Folder", self)
        open_btn.clicked.connect(self._open_workdir)
        buttons.addWidget(open_btn)
        buttons.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export eigenmodes", os.path.expanduser("~/cavity_modes.csv"),
            "CSV (*.csv)")
        if path:
            self.result.save_csv(path)
            QtWidgets.QMessageBox.information(self, "EMStudio", "Saved " + path)

    def _open_workdir(self):
        from PySide import QtCore

        workdir = self.result.meta.get("workdir", "")
        if workdir:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(workdir))
