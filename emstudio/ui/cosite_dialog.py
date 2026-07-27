# SPDX-License-Identifier: LGPL-2.1-or-later
"""Co-site interference calculator dialog (ROADMAP §5).

Enter a list of co-located radios (transmitters / receivers) and the
antenna-to-antenna isolation, and get the classic co-site interference report:
intermodulation products landing in a receiver's passband (with levels from the
junction intercept point), receiver desensitization, broadband-noise coupling and
frequency-plan clashes. A frequency-map tab plots the transmit carriers, the
receiver passbands and the intermod products at a glance.

Thin view over the Qt-free engine in ``emstudio.cosite.interference`` — the physics
is unit-tested headlessly (gate ``tests/validation/cosite.py``). Radio lists are
generic / user-supplied; no specific sites are referenced.
"""

from __future__ import annotations

from PySide import QtGui, QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

# columns: label, tx MHz, tx dBm, rx MHz, rx BW kHz, rx sens dBm, rx block dBm
_COLS = ["Label", "TX f (MHz)", "TX P (dBm)", "RX f (MHz)", "RX BW (kHz)",
         "RX sens (dBm)", "RX block (dBm)"]
# a two-transmitter + victim example whose 2f1-f2 lands on the receiver
_DEFAULT_ROWS = [
    ["TX-A", "150.0", "40", "", "", "", ""],
    ["TX-B", "151.0", "40", "", "", "", ""],
    ["RX-C", "", "", "149.0", "25", "-110", "-20"],
    ["Radio-D", "162.0", "43", "158.0", "25", "-113", "-20"],
]


class CositeDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio — Co-site Interference Calculator")
        self.resize(1040, 680)

        root = QtWidgets.QHBoxLayout(self)

        # ================= left: radio table + params =================
        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel(
            "Co-located radios (a transmitter, a receiver, or both):"))
        self.table = QtWidgets.QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row in _DEFAULT_ROWS:
            self._add_row(row)
        left.addWidget(self.table, 1)

        row_btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("+ radio")
        del_btn = QtWidgets.QPushButton("− radio")
        add_btn.clicked.connect(lambda: self._add_row())
        del_btn.clicked.connect(self._del_row)
        row_btns.addWidget(add_btn)
        row_btns.addWidget(del_btn)
        row_btns.addStretch(1)
        left.addLayout(row_btns)

        params = QtWidgets.QGroupBox("Coupling & junction")
        pform = QtWidgets.QFormLayout(params)
        self._iso_pairs = None   # {(i, j): dB} from the NEC2 isolation matrix
        iso_row = QtWidgets.QHBoxLayout()
        self.isolation = QtWidgets.QDoubleSpinBox()
        self.isolation.setRange(0.0, 200.0)
        self.isolation.setValue(30.0)
        self.isolation.setSuffix(" dB")
        self.isolation.setToolTip(
            "Antenna-to-antenna isolation applied to all pairs — or import the "
            "real per-pair matrix from the NEC2 multi-port solve (button). "
            "Editing this scalar clears an imported matrix.")
        self.iso_matrix_btn = QtWidgets.QPushButton("From NEC2 matrix…")
        self.iso_matrix_btn.setToolTip(
            "Runs the antenna-isolation-matrix solve on the active document's\n"
            "EM Analysis (2+ ports + NEC2 solver, e.g. the Co-site Antenna\n"
            "Pair template) and applies the computed PER-PAIR isolation.\n"
            "Antenna order maps to the radio-table row order.")
        self.iso_matrix_btn.clicked.connect(self._iso_from_matrix)
        iso_row.addWidget(self.isolation, 1)
        iso_row.addWidget(self.iso_matrix_btn)
        pform.addRow("Isolation", iso_row)
        self.iso_status = QtWidgets.QLabel("scalar (all pairs)")
        self.iso_status.setStyleSheet("color: gray; font-size: 8pt;")
        pform.addRow("", self.iso_status)
        self.isolation.valueChanged.connect(self._clear_iso_pairs)
        self.ip3 = QtWidgets.QDoubleSpinBox()
        self.ip3.setRange(-50.0, 80.0)
        self.ip3.setValue(20.0)
        self.ip3.setSuffix(" dBm")
        self.ip3.setToolTip(
            "Third-order output intercept of the mixing junction. Lower = worse "
            "IMD (a passive rusty-bolt junction is far worse than a linear amp).")
        pform.addRow("Junction IP3", self.ip3)
        self.order = QtWidgets.QSpinBox()
        self.order.setRange(2, 7)
        self.order.setValue(3)
        self.order.setToolTip("Highest intermodulation order to enumerate.")
        pform.addRow("Max IMD order", self.order)
        left.addWidget(params)

        act_row = QtWidgets.QHBoxLayout()
        self.analyze_btn = QtWidgets.QPushButton("Analyze")
        self.analyze_btn.clicked.connect(self._analyze)
        self.optimize_btn = QtWidgets.QPushButton("Optimize TX frequencies")
        self.optimize_btn.setToolTip(
            "Search transmit-channel assignments that minimise the interference "
            "(intermod + co-channel); retunes each transmitter within a few "
            "channels and applies the best plan found.")
        self.optimize_btn.clicked.connect(self._optimize)
        act_row.addWidget(self.analyze_btn)
        act_row.addWidget(self.optimize_btn)
        left.addLayout(act_row)
        root.addLayout(left, 1)

        # ================= right: report + spectrum =================
        self.tabs = QtWidgets.QTabWidget()
        self.report_view = QtWidgets.QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QtGui.QFont("Monospace"))
        self.tabs.addTab(self.report_view, "Report")
        self.fig = Figure(figsize=(5, 5), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        self.tabs.addTab(self.canvas, "Frequency map")
        root.addWidget(self.tabs, 1)

        self._analyze()

    # ---------------- table helpers ----------------
    def _add_row(self, values=None):
        r = self.table.rowCount()
        self.table.insertRow(r)
        values = values or ["Radio-{0}".format(r + 1), "", "", "", "25", "-110", "-20"]
        for c, v in enumerate(values):
            self.table.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))

    def _del_row(self):
        r = self.table.rowCount()
        if r > 1:
            self.table.removeRow(r - 1)

    def _cell(self, r, c, default=0.0):
        item = self.table.item(r, c)
        if item is None:
            return default
        txt = item.text().strip()
        if not txt:
            return default
        try:
            return float(txt)
        except ValueError:
            return default

    def _radios(self):
        from emstudio.cosite.interference import Radio

        radios = []
        for r in range(self.table.rowCount()):
            label_item = self.table.item(r, 0)
            label = label_item.text().strip() if label_item else ""
            if not label:
                label = "Radio-{0}".format(r + 1)
            radios.append(Radio(
                label=label,
                tx_freq_hz=self._cell(r, 1) * 1e6,
                tx_power_dbm=self._cell(r, 2, 40.0),
                rx_freq_hz=self._cell(r, 3) * 1e6,
                rx_bw_hz=self._cell(r, 4, 25.0) * 1e3,
                rx_sens_dbm=self._cell(r, 5, -110.0),
                rx_blocking_dbm=self._cell(r, 6, -20.0),
            ))
        return radios

    # ---------------- isolation-matrix import ----------------
    def _iso_value(self):
        """Per-pair dict when a matrix was imported, else the scalar."""
        return self._iso_pairs if self._iso_pairs else self.isolation.value()

    def _clear_iso_pairs(self, _v=None):
        if self._iso_pairs:
            self._iso_pairs = None
            self.iso_status.setText("scalar (all pairs)")

    def _apply_iso_pairs(self, pairs, note):
        """Adopt a per-pair isolation dict (row order = antenna order)."""
        self._iso_pairs = dict(pairs)
        self.iso_status.setText("per-pair NEC2 matrix: {0}".format(note))
        self._analyze()

    def _iso_from_matrix(self):
        import FreeCAD

        from emstudio.objects import query

        doc = FreeCAD.ActiveDocument
        ana = None
        if doc is not None:
            for obj in doc.Objects:
                if query.em_type(obj) == "EMStudio::Analysis":
                    ana = obj
                    break
        if ana is None or len(query.get_ports(ana)) < 2:
            QtWidgets.QMessageBox.information(
                self, "EMStudio",
                "Needs an EM Analysis with 2+ ports in the active document\n"
                "(e.g. Template: Co-site Antenna Pair). Antenna order maps to\n"
                "the radio-table row order.")
            return
        solvers = [s for s in query.get_solvers(ana)
                   if query.em_type(s) == "EMStudio::SolverNEC2"]
        if not solvers:
            QtWidgets.QMessageBox.information(
                self, "EMStudio", "Add a NEC2 solver to the analysis first.")
            return

        def run_iso(_a, _s, cb):
            from emstudio.cosite import isolation

            return isolation.isolation_matrix(ana, solvers[0], line_callback=cb)

        def on_ok(res):
            from emstudio.cosite import isolation

            self._apply_iso_pairs(
                isolation.isolation_pairs_db(res),
                "{0} antennas ({1})".format(len(res["labels"]),
                                            ", ".join(res["labels"])))

        from emstudio.ui import run_gui

        run_gui.run_generic_gui("Isolation matrix (NEC2 multi-port)",
                                run_iso, on_ok, parent=self)

    # ---------------- analysis ----------------
    def _analyze(self):
        from emstudio.cosite import interference as ci

        radios = self._radios()
        try:
            rep = ci.analyze_site(radios, isolation_db=self._iso_value(),
                                  junction_ip3_dbm=self.ip3.value(),
                                  max_order=self.order.value())
        except Exception as exc:  # noqa: BLE001
            self.report_view.setPlainText("Analysis failed: {0}".format(exc))
            return
        self._rep = rep
        self.report_view.setPlainText(ci.summary_text(rep))
        self._draw_map(radios, rep)

    def _optimize(self):
        from emstudio.cosite import interference as ci

        radios = self._radios()
        tx_idx = [i for i, r in enumerate(radios) if r.tx_freq_hz > 0]
        if not tx_idx:
            self.report_view.setPlainText("No transmitters to optimize.")
            return
        rx_bws = [r.rx_bw_hz for r in radios if r.rx_freq_hz > 0]
        step = max(min(rx_bws) if rx_bws else 25e3, 12.5e3)
        n = 8  # +/- 8 channels around each transmitter's current frequency
        candidates = {
            i: [radios[i].tx_freq_hz + k * step for k in range(-n, n + 1)
                if radios[i].tx_freq_hz + k * step > 0]
            for i in tx_idx}
        try:
            opt = ci.optimize_frequency_plan(
                radios, tunable=tx_idx, candidates=candidates,
                isolation_db=self._iso_value(),
                junction_ip3_dbm=self.ip3.value(), max_order=self.order.value())
        except Exception as exc:  # noqa: BLE001
            self.report_view.setPlainText("Optimization failed: {0}".format(exc))
            return
        # apply the winning plan to the table, then re-analyze
        changes = []
        for i, f in opt["assignment"].items():
            if abs(f - radios[i].tx_freq_hz) > 1.0:
                changes.append("  {0}: {1:.4f} -> {2:.4f} MHz".format(
                    radios[i].label, radios[i].tx_freq_hz / 1e6, f / 1e6))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem("{0:.4f}".format(f / 1e6)))
        self._analyze()
        note = ["Frequency plan optimized: cost {0:.1f} -> {1:.1f}  ({2}, {3} plans "
                "evaluated{4})".format(opt["baseline_cost"], opt["cost"],
                                       opt["method"], opt["evaluated"],
                                       ", capped" if opt["capped"] else "")]
        note += changes or ["  (no retune improved on the current plan)"]
        note.append("")
        self.report_view.setPlainText("\n".join(note) + "\n" +
                                      self.report_view.toPlainText())

    def _draw_map(self, radios, rep):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        mhz = 1e-6

        tx = [r for r in radios if r.tx_freq_hz > 0]
        rx = [r for r in radios if r.rx_freq_hz > 0]

        # receiver passbands as shaded vertical bands
        for r in rx:
            f0 = r.rx_freq_hz * mhz
            bw = r.rx_bw_hz * mhz
            ax.axvspan(f0 - bw / 2, f0 + bw / 2, color="#2b8cff", alpha=0.15)
            ax.text(f0, 1.02, "rx " + r.label, rotation=90, fontsize=7,
                    color="#2b6cbf", ha="center", va="bottom")

        # transmit carriers as stems at their power
        for r in tx:
            f0 = r.tx_freq_hz * mhz
            ax.vlines(f0, -120, r.tx_power_dbm, color="#c87533", lw=2)
            ax.plot([f0], [r.tx_power_dbm], "o", color="#c87533")
            ax.text(f0, r.tx_power_dbm + 3, "tx " + r.label, fontsize=7,
                    color="#8a4c1c", ha="center")

        # intermod products: red if they land on a receiver, faint otherwise
        hit_freqs = {round(h["freq_hz"], 3) for h in rep["imd"]}
        for h in rep["imd"]:
            f0 = h["freq_hz"] * mhz
            ax.plot([f0], [h["level_dbm"]], "v", color="#d33", ms=7)
            ax.text(f0, h["level_dbm"] - 6, "IM{0}".format(h["order"]), fontsize=6,
                    color="#d33", ha="center", va="top")

        ax.set_ylim(-120, 60)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Power (dBm)")
        ax.grid(True, alpha=0.3)
        n_hit = len([h for h in rep["imd"] if h["margin_db"] > 0])
        ax.set_title("Co-site frequency map — {0} tx, {1} rx, {2} IMD hit(s)".format(
            len(tx), len(rx), n_hit), fontsize=9)
        self.canvas.draw_idle()
