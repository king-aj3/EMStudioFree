# SPDX-License-Identifier: LGPL-2.1-or-later
"""Point-to-point link-budget dialog (ROADMAP §6, phase A).

Enter a link (frequency, distance, transmit power, antenna gains/heights,
receiver sensitivity) and get the path loss under the free-space and two-ray
plane-earth models, the received power and fade margin, and the broadcast field
strength — plus a path-loss-vs-distance plot marking the plane-earth breakpoint.

Thin view over the Qt-free models in ``emstudio.coverage.propagation`` (gate
``tests/validation/propagation.py``). Terrain single-edge diffraction is available
in the engine (`terrain_profile_loss`) and gets its own UI with DEM import in a
later phase. Transmitter locations are user-supplied; no specific sites referenced.
"""

from __future__ import annotations

from PySide import QtGui, QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


class LinkBudgetDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio — Point-to-Point Link Budget")
        self.resize(1000, 660)

        root = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()

        link = QtWidgets.QGroupBox("Link")
        form = QtWidgets.QFormLayout(link)
        frow = QtWidgets.QHBoxLayout()
        self.freq = QtWidgets.QDoubleSpinBox()
        self.freq.setDecimals(4)
        self.freq.setRange(0.0001, 1e6)
        self.freq.setValue(300.0)
        self.freq_unit = QtWidgets.QComboBox()
        self.freq_unit.addItems(["kHz", "MHz", "GHz"])
        self.freq_unit.setCurrentText("MHz")
        frow.addWidget(self.freq, 1)
        frow.addWidget(self.freq_unit)
        form.addRow("Frequency", frow)
        self.distance = QtWidgets.QDoubleSpinBox()
        self.distance.setDecimals(4)
        self.distance.setRange(0.001, 40000.0)
        self.distance.setValue(10.0)
        self.distance.setSuffix(" km")
        form.addRow("Distance", self.distance)
        self.tx_power = self._spin(form, "TX power", 43.0, " dBm", -30, 90)
        self.tx_gain = self._spin(form, "TX gain", 10.0, " dBi", -10, 60)
        self.rx_gain = self._spin(form, "RX gain", 3.0, " dBi", -10, 60)
        self.rx_sens = self._spin(form, "RX sensitivity", -95.0, " dBm", -160, 0)
        self.tx_h = self._spin(form, "TX height", 30.0, " m", 0.1, 5000)
        self.rx_h = self._spin(form, "RX height", 10.0, " m", 0.1, 5000)
        self.eirp = self._spin(form, "EIRP (field str.)", 1000.0, " W", 0.001, 1e7)
        left.addWidget(link)

        self.analyze_btn = QtWidgets.QPushButton("Analyze")
        self.analyze_btn.clicked.connect(self._analyze)
        left.addWidget(self.analyze_btn)
        left.addStretch(1)
        root.addLayout(left, 0)

        self.tabs = QtWidgets.QTabWidget()
        self.readout = QtWidgets.QPlainTextEdit()
        self.readout.setReadOnly(True)
        self.readout.setFont(QtGui.QFont("Monospace"))
        self.tabs.addTab(self.readout, "Link budget")
        self.fig = Figure(figsize=(5, 5), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.tabs.addTab(self.canvas, "Path loss vs distance")
        root.addWidget(self.tabs, 1)

        self._analyze()

    def _spin(self, form, label, value, suffix, lo, hi):
        s = QtWidgets.QDoubleSpinBox()
        s.setDecimals(3)
        s.setRange(lo, hi)
        s.setValue(value)
        s.setSuffix(suffix)
        form.addRow(label, s)
        return s

    def _freq_hz(self):
        mult = {"kHz": 1e3, "MHz": 1e6, "GHz": 1e9}[self.freq_unit.currentText()]
        return self.freq.value() * mult

    def _analyze(self):
        from emstudio.coverage import propagation as pr

        f = self._freq_hz()
        d = self.distance.value() * 1e3
        fspl = pr.free_space_path_loss_db(d, f)
        pe = pr.plane_earth_loss_db(d, self.tx_h.value(), self.rx_h.value())
        bp = pr.plane_earth_breakpoint_m(self.tx_h.value(), self.rx_h.value(), f)
        # beyond the breakpoint the plane-earth (d^4) model governs; inside it,
        # free space is the better estimate
        governing = pe if d > bp else fspl
        lb = pr.link_budget(self.tx_power.value(), governing,
                            tx_gain_dbi=self.tx_gain.value(),
                            rx_gain_dbi=self.rx_gain.value(),
                            rx_sens_dbm=self.rx_sens.value())
        eirp_w = self.eirp.value()
        e = pr.field_strength_dbuv_m(eirp_w, d)

        L = ["POINT-TO-POINT LINK BUDGET", "==========================",
             "frequency        : {0:.4g} MHz".format(f / 1e6),
             "distance         : {0:.4g} km".format(d / 1e3), "",
             "free-space loss  : {0:.2f} dB".format(fspl),
             "plane-earth loss : {0:.2f} dB  (two-ray d^4)".format(pe),
             "breakpoint       : {0:.4g} km  ({1})".format(
                 bp / 1e3, "beyond -> plane-earth governs" if d > bp
                 else "inside -> free space governs"),
             "governing loss   : {0:.2f} dB".format(governing), "",
             "received power   : {0:.2f} dBm".format(lb["rx_power_dbm"]),
             "fade margin      : {0:+.2f} dB  ({1})".format(
                 lb["fade_margin_db"],
                 "link closes" if lb["fade_margin_db"] > 0 else "LINK FAILS"),
             "",
             "field strength   : {0:.2f} dBuV/m  (free space, {1:g} W EIRP)".format(
                 e, eirp_w)]
        self.readout.setPlainText("\n".join(L))
        self._draw(f, d, bp)

    def _draw(self, f, d, bp):
        from emstudio.coverage import propagation as pr

        self.fig.clear()
        ax = self.fig.add_subplot(111)
        dd = np.logspace(np.log10(max(d / 100.0, 10.0)),
                         np.log10(max(d * 10.0, 1e3)), 300)
        fspl = [pr.free_space_path_loss_db(x, f) for x in dd]
        pe = [pr.plane_earth_loss_db(x, self.tx_h.value(), self.rx_h.value())
              for x in dd]
        ax.semilogx(dd / 1e3, fspl, "-", color="#2b8cff", lw=2, label="free space")
        ax.semilogx(dd / 1e3, pe, "-", color="#c87533", lw=2, label="plane earth (d^4)")
        ax.axvline(bp / 1e3, color="#888", ls=":", lw=1, label="breakpoint")
        ax.axvline(d / 1e3, color="#d33", ls="--", lw=1, label="this link")
        ax.set_xlabel("distance (km)")
        ax.set_ylabel("path loss (dB)")
        ax.grid(True, which="both", alpha=0.35)
        ax.legend(fontsize=8)
        ax.invert_yaxis()
        ax.set_title("Path loss vs distance @ {0:.4g} MHz".format(f / 1e6), fontsize=9)
        self.canvas.draw_idle()
