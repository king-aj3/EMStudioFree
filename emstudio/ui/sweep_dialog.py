# SPDX-License-Identifier: LGPL-2.1-or-later
"""Plot dialog for a WPT gap sweep: coupling k and mutual M vs coil gap."""

from __future__ import annotations

import os

from PySide import QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


class GapSweepDialog(QtWidgets.QDialog):
    """k(gap) and M(gap) from a WPT parametric gap sweep."""

    def __init__(self, curve, parent=None):
        super().__init__(parent)
        self.curve = list(curve)
        self.setWindowTitle("EMStudio — WPT Gap Sweep")
        self.resize(760, 560)

        layout = QtWidgets.QVBoxLayout(self)
        fig = Figure(figsize=(7, 4.5), tight_layout=True)
        canvas = FigureCanvas(fig)
        layout.addWidget(NavigationToolbar2QT(canvas, self))
        layout.addWidget(canvas)

        gaps = [p["gap_mm"] for p in self.curve]
        ks = [p["k"] for p in self.curve]
        ms = [p["M_h"] * 1e6 for p in self.curve]
        ax = fig.add_subplot(111)
        ax.plot(gaps, ks, "-o", lw=2, color="#2b8cff", label="coupling k")
        ax.set_xlabel("coil gap (mm)")
        ax.set_ylabel("coupling coefficient k", color="#2b8cff")
        ax.grid(True, alpha=0.4)
        ax2 = ax.twinx()
        ax2.plot(gaps, ms, "--s", lw=1.6, color="#c8553d", label="mutual M")
        ax2.set_ylabel("mutual inductance M (µH)", color="#c8553d")
        ax.set_title("Wireless-power coupling vs coil gap")
        layout.addWidget(QtWidgets.QLabel(
            "k = {0:.4g} at {1:.0f} mm  →  {2:.4g} at {3:.0f} mm".format(
                ks[0], gaps[0], ks[-1], gaps[-1])))

        buttons = QtWidgets.QHBoxLayout()
        csv_btn = QtWidgets.QPushButton("Export CSV…", self)
        csv_btn.clicked.connect(self._export_csv)
        buttons.addWidget(csv_btn)
        buttons.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close", self)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _export_csv(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export gap sweep", os.path.expanduser("~/wpt_gap_sweep.csv"),
            "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("gap_mm,k,L1_uH,L2_uH,M_uH\n")
            for p in self.curve:
                fh.write("{0:.6g},{1:.6g},{2:.6g},{3:.6g},{4:.6g}\n".format(
                    p["gap_mm"], p["k"], p["L1_h"] * 1e6, p["L2_h"] * 1e6,
                    p["M_h"] * 1e6))
        QtWidgets.QMessageBox.information(self, "EMStudio", "Saved " + path)
