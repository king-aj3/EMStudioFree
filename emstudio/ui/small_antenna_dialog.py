# SPDX-License-Identifier: LGPL-2.1-or-later
"""Electrically-small antenna designer dialog (VLF / LF / MF characterization).

The analytic analogue of the Litz designer, for the electrically-small regime
where a resonant antenna would be kilometres long and the full-wave field solvers
are impractical. Left column: the antenna type, frequency (with representative
VLF/LF/MF band presets), geometry and loss budget. Right tabs: the predicted
performance read-out (radiation resistance, effective height, efficiency, Chu
Q/bandwidth, loading), a dimension-annotated 2-D sketch, and the Chu minimum-Q
guardrail plot. A band -> recommended-method banner routes the user to the valid
EMStudio method.

Physics per A.D. Watt, *VLF Radio Engineering* (Pergamon, 1967) and Balanis /
Kraus. Wraps the Qt-free analytics in ``emstudio.antenna.small_antenna`` and the
router in ``emstudio.antenna.band_picker`` — the dialog is a thin view, so the
physics is unit-tested headlessly (gate ``tests/validation/small_antenna.py``).
"""

from __future__ import annotations

import math

from PySide import QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

# Representative VLF/LF/MF band frequencies (kHz) — the electrically-small
# broadcast/navigation region. Generic band anchors, not specific installations:
# the ~10-30 kHz VLF submarine-broadcast region, the LF band, and low MF. The
# picker/analytics only need f.
FREQ_PRESETS = [
    ("— frequency preset —", 0.0),
    ("VLF 10 kHz", 10.0),
    ("VLF 16 kHz", 16.0),
    ("VLF 20 kHz", 20.0),
    ("VLF 24 kHz", 24.0),
    ("VLF 30 kHz", 30.0),
    ("LF 40 kHz", 40.0),
    ("LF 60 kHz", 60.0),
    ("LF 100 kHz", 100.0),
    ("MF 300 kHz", 300.0),
    ("MF 500 kHz", 500.0),
]


class SmallAntennaDialog(QtWidgets.QDialog):
    TYPES = [
        ("Short monopole (vertical, over ground)", "monopole"),
        ("Short dipole", "dipole"),
        ("Small loop (receive / DF)", "loop"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio — Small-Antenna Designer (VLF / LF / MF)")
        self.resize(1040, 680)

        root = QtWidgets.QHBoxLayout(self)

        # ================= left column: inputs =================
        left = QtWidgets.QVBoxLayout()

        ant_box = QtWidgets.QGroupBox("Antenna")
        aform = QtWidgets.QFormLayout(ant_box)
        self.type_combo = QtWidgets.QComboBox()
        for label, _key in self.TYPES:
            self.type_combo.addItem(label, _key)
        aform.addRow("Type", self.type_combo)

        self.preset_combo = QtWidgets.QComboBox()
        for label, _f in FREQ_PRESETS:
            self.preset_combo.addItem(label, _f)
        self.preset_combo.setToolTip(
            "Fill the frequency from a representative VLF/LF/MF band value.")
        aform.addRow("Band preset", self.preset_combo)

        freq_row = QtWidgets.QHBoxLayout()
        self.freq = QtWidgets.QDoubleSpinBox()
        self.freq.setDecimals(4)
        self.freq.setRange(0.0001, 1e6)
        self.freq.setValue(24.0)
        self.freq_unit = QtWidgets.QComboBox()
        self.freq_unit.addItems(["Hz", "kHz", "MHz", "GHz"])
        self.freq_unit.setCurrentText("kHz")
        freq_row.addWidget(self.freq, 1)
        freq_row.addWidget(self.freq_unit)
        aform.addRow("Frequency", freq_row)
        left.addWidget(ant_box)

        geo_box = QtWidgets.QGroupBox("Geometry")
        gform = QtWidgets.QFormLayout(geo_box)
        self.size_spin = QtWidgets.QDoubleSpinBox()
        self.size_spin.setDecimals(3)
        self.size_spin.setRange(0.001, 5000.0)
        self.size_spin.setValue(150.0)
        self.size_spin.setSuffix(" m")
        self.size_label = QtWidgets.QLabel("Height h")
        gform.addRow(self.size_label, self.size_spin)

        self.radius_spin = QtWidgets.QDoubleSpinBox()
        self.radius_spin.setDecimals(3)
        self.radius_spin.setRange(0.001, 1000.0)
        self.radius_spin.setValue(5.0)
        self.radius_spin.setSuffix(" mm")
        self.radius_spin.setToolTip(
            "Conductor radius — sizes the monopole static capacitance (loading "
            "coil) and the enclosing-sphere ka.")
        gform.addRow("Wire radius", self.radius_spin)

        self.dia_spin = QtWidgets.QDoubleSpinBox()
        self.dia_spin.setDecimals(3)
        self.dia_spin.setRange(0.001, 1000.0)
        self.dia_spin.setValue(1.0)
        self.dia_spin.setSuffix(" m")
        self.dia_spin.setToolTip("Loop diameter (small-loop only).")
        gform.addRow("Loop diameter", self.dia_spin)

        self.turns_spin = QtWidgets.QSpinBox()
        self.turns_spin.setRange(1, 100000)
        self.turns_spin.setValue(10)
        self.turns_spin.setToolTip("Loop turns N (small-loop only). Rr scales as N^2.")
        gform.addRow("Loop turns", self.turns_spin)
        left.addWidget(geo_box)

        loss_box = QtWidgets.QGroupBox("Loss budget & matching")
        lform = QtWidgets.QFormLayout(loss_box)
        self.rloss = QtWidgets.QDoubleSpinBox()
        self.rloss.setDecimals(4)
        self.rloss.setRange(0.0, 1e6)
        self.rloss.setValue(1.0)
        self.rloss.setSuffix(" ohm")
        self.rloss.setToolTip(
            "Total loss resistance (conductor + ground/counterpoise + loading-coil "
            "ESR). At VLF the ground system usually dominates and sets efficiency.")
        lform.addRow("Loss resistance", self.rloss)
        self.vswr = QtWidgets.QDoubleSpinBox()
        self.vswr.setDecimals(2)
        self.vswr.setRange(1.05, 20.0)
        self.vswr.setValue(2.0)
        self.vswr.setToolTip("VSWR threshold for the matched fractional-bandwidth estimate.")
        lform.addRow("VSWR limit", self.vswr)
        left.addWidget(loss_box)

        self.update_btn = QtWidgets.QPushButton("Update")
        self.update_btn.clicked.connect(self._recalc)
        left.addWidget(self.update_btn)
        left.addStretch(1)
        root.addLayout(left, 0)

        # ================= right column: banner + tabs =================
        right = QtWidgets.QVBoxLayout()
        self.banner = QtWidgets.QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "QLabel { background: #234; color: #dfe8f4; padding: 8px; "
            "border-radius: 4px; }")
        right.addWidget(self.banner)

        self.tabs = QtWidgets.QTabWidget()
        self.perf_view = QtWidgets.QPlainTextEdit()
        self.perf_view.setReadOnly(True)
        from PySide import QtGui

        self.perf_view.setFont(QtGui.QFont("Monospace"))
        self.tabs.addTab(self.perf_view, "Predicted Performance")
        self.fig_sketch = Figure(figsize=(5, 5), tight_layout=True)
        self.canvas_sketch = FigureCanvas(self.fig_sketch)
        self.tabs.addTab(self.canvas_sketch, "Sketch")
        self.fig_chu = Figure(figsize=(5, 5), tight_layout=True)
        self.canvas_chu = FigureCanvas(self.fig_chu)
        self.tabs.addTab(self.canvas_chu, "Chu Q limit")
        self.tabs.addTab(self._build_topload_tab(), "Top loading && ground")
        right.addWidget(self.tabs, 1)
        root.addLayout(right, 1)

        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        # main-input changes mark the top-loading tab read-out stale
        self.update_btn.clicked.connect(self._topload_stale)
        self.type_combo.currentIndexChanged.connect(self._topload_stale)
        self.preset_combo.currentIndexChanged.connect(self._topload_stale)
        self.freq.valueChanged.connect(self._topload_stale)
        self.size_spin.valueChanged.connect(self._topload_stale)
        self._type_changed()
        self._recalc()

    # ---------------- top-loading & ground tab (§4 breadth) ----------------
    _GROUNDS = [
        ("Sea water (4 S/m)", 4.0),
        ("Good ground (30 mS/m)", 0.03),
        ("Average ground (5 mS/m)", 0.005),
        ("Poor/rocky ground (1 mS/m)", 0.001),
    ]

    def _build_topload_tab(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(page)
        form_col = QtWidgets.QVBoxLayout()

        hat_box = QtWidgets.QGroupBox("Top loading (monopole)")
        hform = QtWidgets.QFormLayout(hat_box)
        self.tl_hat = QtWidgets.QComboBox()
        self.tl_hat.addItem("None (bare mast)", "none")
        self.tl_hat.addItem("Flat top (n parallel wires)", "flat")
        self.tl_hat.addItem("T (single top wire, centre-fed)", "t")
        self.tl_hat.addItem("Inverted L (single top wire)", "l")
        self.tl_hat.addItem("Solid/mesh plate hat", "plate")
        hform.addRow("Hat type", self.tl_hat)
        self.tl_n = QtWidgets.QSpinBox()
        self.tl_n.setRange(2, 100)
        self.tl_n.setValue(6)
        hform.addRow("Wires n (flat top)", self.tl_n)
        self.tl_len = QtWidgets.QDoubleSpinBox()
        self.tl_len.setDecimals(1)
        self.tl_len.setRange(1.0, 5000.0)
        self.tl_len.setValue(200.0)
        self.tl_len.setSuffix(" m")
        hform.addRow("Top length l", self.tl_len)
        self.tl_spacing = QtWidgets.QDoubleSpinBox()
        self.tl_spacing.setDecimals(2)
        self.tl_spacing.setRange(0.1, 200.0)
        self.tl_spacing.setValue(8.0)
        self.tl_spacing.setSuffix(" m")
        hform.addRow("Wire spacing D", self.tl_spacing)
        self.tl_wire_d = QtWidgets.QDoubleSpinBox()
        self.tl_wire_d.setDecimals(1)
        self.tl_wire_d.setRange(1.0, 200.0)
        self.tl_wire_d.setValue(10.0)
        self.tl_wire_d.setSuffix(" mm")
        hform.addRow("Top-wire Ø", self.tl_wire_d)
        self.tl_area = QtWidgets.QDoubleSpinBox()
        self.tl_area.setDecimals(0)
        self.tl_area.setRange(1.0, 1e6)
        self.tl_area.setValue(5000.0)
        self.tl_area.setSuffix(" m²")
        hform.addRow("Plate area", self.tl_area)
        self.tl_perim = QtWidgets.QDoubleSpinBox()
        self.tl_perim.setDecimals(0)
        self.tl_perim.setRange(0.0, 1e5)
        self.tl_perim.setValue(300.0)
        self.tl_perim.setSuffix(" m")
        hform.addRow("Plate perimeter", self.tl_perim)
        form_col.addWidget(hat_box)

        gnd_box = QtWidgets.QGroupBox("Radial ground screen")
        gform = QtWidgets.QFormLayout(gnd_box)
        self.tl_ground = QtWidgets.QComboBox()
        for label, sig in self._GROUNDS:
            self.tl_ground.addItem(label, sig)
        self.tl_ground.setCurrentIndex(2)
        gform.addRow("Earth", self.tl_ground)
        self.tl_nrad = QtWidgets.QSpinBox()
        self.tl_nrad.setRange(0, 1000)
        self.tl_nrad.setValue(120)
        self.tl_nrad.setSpecialValueText("no screen")
        gform.addRow("Radials N", self.tl_nrad)
        self.tl_arad = QtWidgets.QDoubleSpinBox()
        self.tl_arad.setDecimals(0)
        self.tl_arad.setRange(1.0, 20000.0)
        self.tl_arad.setValue(400.0)
        self.tl_arad.setSuffix(" m")
        gform.addRow("Screen radius a", self.tl_arad)
        form_col.addWidget(gnd_box)

        lim_box = QtWidgets.QGroupBox("Voltage limit & other losses")
        lform = QtWidgets.QFormLayout(lim_box)
        self.tl_volt = QtWidgets.QDoubleSpinBox()
        self.tl_volt.setDecimals(0)
        self.tl_volt.setRange(1.0, 1000.0)
        self.tl_volt.setValue(200.0)
        self.tl_volt.setSuffix(" kV")
        self.tl_volt.setToolTip(
            "Top-hat potential limit (insulation/corona) — VLF antennas "
            "are voltage-limited devices.")
        lform.addRow("V limit", self.tl_volt)
        self.tl_rother = QtWidgets.QDoubleSpinBox()
        self.tl_rother.setDecimals(4)
        self.tl_rother.setRange(0.0, 1000.0)
        self.tl_rother.setValue(0.1)
        self.tl_rother.setSuffix(" ohm")
        self.tl_rother.setToolTip(
            "Loading-coil ESR + conductor + dielectric losses — EXCLUDING "
            "the ground system (Rg is computed above; the main panel's "
            "loss budget is NOT used here to avoid double-counting "
            "ground loss).")
        lform.addRow("Other losses", self.tl_rother)
        form_col.addWidget(lim_box)

        self.tl_btn = QtWidgets.QPushButton("Update top loading")
        self.tl_btn.clicked.connect(self._recalc_topload)
        form_col.addWidget(self.tl_btn)
        form_col.addStretch(1)
        lay.addLayout(form_col, 0)
        self.tl_hat.currentIndexChanged.connect(self._topload_fields)
        self._topload_fields()

        self.tl_view = QtWidgets.QPlainTextEdit()
        self.tl_view.setReadOnly(True)
        from PySide import QtGui

        self.tl_view.setFont(QtGui.QFont("Monospace"))
        self.tl_view.setPlaceholderText(
            "Top-loading capacitance, effective height, ground-system "
            "resistance, efficiency and voltage-limited power/bandwidth "
            "appear here (monopole type). Hit 'Update top loading'.")
        lay.addWidget(self.tl_view, 1)
        return page

    def _topload_fields(self):
        """Per-hat-type field enablement (the wrong fields stay grey)."""
        hat = self.tl_hat.currentData()
        self.tl_n.setEnabled(hat == "flat")
        self.tl_spacing.setEnabled(hat == "flat")
        self.tl_len.setEnabled(hat in ("flat", "t", "l"))
        self.tl_wire_d.setEnabled(hat in ("flat", "t", "l"))
        self.tl_area.setEnabled(hat == "plate")
        self.tl_perim.setEnabled(hat == "plate")

    def _topload_stale(self):
        """The main inputs changed — mark the tab's read-out stale."""
        if self.tl_view.toPlainText():
            self.tl_view.setPlainText(
                "(inputs changed — hit 'Update top loading' to refresh)")

    def _recalc_topload(self):
        """Top-loading + ground read-out (pure engines; gui_smoke-gated)."""
        from emstudio.antenna import ground_system as gs
        from emstudio.antenna import small_antenna as sa
        from emstudio.antenna import topload as tp

        if self._kind() != "monopole":
            self.tl_view.setPlainText(
                "Top loading & ground applies to the MONOPOLE type — "
                "switch the antenna type on the left.")
            return
        f = self._freq_hz()
        h = self.size_spin.value()
        d_top = self.tl_wire_d.value() * 1e-3
        warnings = []
        try:
            hat = self.tl_hat.currentData()
            if hat == "flat":
                c_hat, warnings = tp.flat_top_c(
                    self.tl_n.value(), self.tl_len.value(), h, d_top,
                    self.tl_spacing.value())
            elif hat == "t":
                c_hat = tp.t_antenna_c(self.tl_len.value(), h, h, 0.01 * h,
                                       d_top)
            elif hat == "l":
                c_hat = tp.inverted_l_c(self.tl_len.value(), h, h, 0.01 * h,
                                        d_top)
            elif hat == "plate":
                c_hat = tp.plate_hat_c(self.tl_area.value(), h,
                                       perimeter_m=self.tl_perim.value())
            else:
                c_hat = 0.0
            c_mast = sa._monopole_capacitance_f(
                h, self.radius_spin.value() * 1e-3)
            if hat in ("t", "l"):
                # the composite already includes the downlead — split it
                # with the SAME model family (Watt vertical wire at the
                # same conductor diameter the composite assumed), never
                # the ln-form mast estimate (different model — the review
                # showed the mismatch corrupts h_e)
                c_down = tp.vertical_wire_c(h, 0.01 * h, d_top)
                c_total = c_hat
                c_hat_only = c_hat - c_down
                if c_hat_only <= 0:
                    warnings.append(
                        "the top section adds no net capacitance in this "
                        "geometry (composite <= downlead alone) — the "
                        "mutual X term dominates; lengthen the top or "
                        "raise it")
                    c_hat_only = 0.0
                mast_r_mm = self.radius_spin.value()
                if mast_r_mm > 0 and not (1.0 / 3.0 <= (d_top * 1e3 / 2.0)
                                          / mast_r_mm <= 3.0):
                    warnings.append(
                        "the T/inverted-L composite assumes ONE conductor "
                        "diameter ({0:g} mm) for both sections; the mast "
                        "radius you set ({1:g} mm) differs a lot — treat "
                        "C as approximate for a fat tower".format(
                            d_top * 1e3, mast_r_mm))
                h_e = tp.effective_height_toploaded(h, c_hat_only, c_down)
            else:
                c_total = c_hat + c_mast
                c_hat_only = c_hat
                h_e = tp.effective_height_toploaded(h, c_hat_only, c_mast)
            lam = 299792458.0 / f
            r_r = 160.0 * math.pi ** 2 * (h_e / lam) ** 2
            sigma = self.tl_ground.currentData()
            n_rad = self.tl_nrad.value()
            if n_rad > 0:
                g = gs.ground_resistance(f, h_e, n_rad, self.tl_arad.value(),
                                         sigma)
            else:
                g = gs.ground_resistance(f, h_e, 0, 0.0, sigma)
            r_g = g["rg_ohm"]
            warnings += g["warnings"]
            r_other = self.tl_rother.value()
            eta = r_r / (r_r + r_g + r_other)
            vl = sa.voltage_limited(f, c_total, h_e,
                                    self.tl_volt.value() * 1e3, eta_ts=eta)
            warnings += vl["warnings"]
        except Exception as exc:  # noqa: BLE001 — surfaced in the read-out
            self.tl_view.setPlainText("Invalid top-loading inputs: "
                                      "{0}".format(exc))
            return
        from emstudio.antenna import band_picker

        L = ["TOP LOADING & GROUND — short monopole h = {0:g} m at "
             "{1}".format(h, band_picker._fmt_freq(f))]
        L.append("=" * 52)
        L.append("hat capacitance   : {0:.1f} pF   (mast static "
                 "{1:.1f} pF)".format(c_hat_only * 1e12, c_mast * 1e12))
        L.append("total capacitance : {0:.1f} pF".format(c_total * 1e12))
        L.append("effective height  : {0:.1f} m  (bare mast {1:.1f} m — "
                 "trapezoid estimate)".format(h_e, h / 2.0))
        L.append("radiation R       : {0:.4f} ohm".format(r_r))
        rg_bare = gs.ground_resistance(f, h_e, 0, 0.0, sigma)["rg_ohm"]
        L.append("ground system Rg  : {0:.4f} ohm  (bare earth would be "
                 "{1:.4f})".format(r_g, rg_bare))
        L.append("other losses      : {0:.4f} ohm (tab input — coil/"
                 "conductor/dielectric, EXCLUDING ground)".format(r_other))
        L.append("efficiency        : {0:.1%}  (= Rr/(Rr+Rg+Rl))".format(eta))
        L.append("")
        L.append("VOLTAGE-LIMITED at {0:g} kV:".format(self.tl_volt.value()))
        L.append("radiated power    : {0:.1f} kW".format(
            vl["radiated_power_w"] / 1e3))
        L.append("3-dB bandwidth    : {0:.1f} Hz".format(
            vl["bandwidth_3db_hz"]))
        L.append("power-bandwidth   : {0:.3g} W*Hz".format(
            vl["power_bandwidth_w_hz"]))
        for w in warnings:
            L.append("")
            L.append("warning: {0}".format(w))
        L.append("")
        L.append("source: verified §2.1/§2.3/§2.4 sets "
                 "(docs/upstream/watt-topload-anchors.md); umbrella "
                 "landmarks: max h_e at insulator ratio ~0.35; ratio 0.7 "
                 "buys ~8x power / ~3x bandwidth")
        self.tl_view.setPlainText("\n".join(L))

    # ---------------- input helpers ----------------
    def _kind(self):
        return self.type_combo.currentData()

    def _freq_hz(self):
        mult = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}[self.freq_unit.currentText()]
        return self.freq.value() * mult

    def _type_changed(self):
        kind = self._kind()
        is_loop = kind == "loop"
        is_wire = not is_loop
        self.size_label.setText("Height h" if kind == "monopole" else "Length L")
        self.size_spin.setEnabled(is_wire)
        self.radius_spin.setEnabled(is_wire)
        self.dia_spin.setEnabled(is_loop)
        self.turns_spin.setEnabled(is_loop)
        self._recalc()

    def _preset_changed(self):
        f_khz = self.preset_combo.currentData()
        if f_khz and f_khz > 0:
            self.freq_unit.setCurrentText("kHz")
            self.freq.setValue(float(f_khz))
            self._recalc()

    # ---------------- compute + render ----------------
    def _recalc(self):
        from emstudio.antenna import band_picker, small_antenna as sa

        f = self._freq_hz()
        kind = self._kind()
        rloss = self.rloss.value()
        vswr = self.vswr.value()

        try:
            if kind == "monopole":
                h = self.size_spin.value()
                res = sa.short_monopole(h, f, r_loss=rloss,
                                        wire_radius_m=self.radius_spin.value() * 1e-3,
                                        vswr=vswr)
                max_dim = h
            elif kind == "dipole":
                L = self.size_spin.value()
                res = sa.short_dipole(L, f, r_loss=rloss,
                                      radius_m=self.radius_spin.value() * 1e-3 or None,
                                      vswr=vswr)
                max_dim = L
            else:
                d = self.dia_spin.value()
                area = math.pi * (d / 2.0) ** 2
                res = sa.short_loop(area, f, turns=self.turns_spin.value(),
                                    r_loss=rloss, vswr=vswr)
                max_dim = d
        except Exception as exc:  # noqa: BLE001 — surfaced in the read-out
            self.perf_view.setPlainText("Invalid inputs: {0}".format(exc))
            return

        self._res = res
        rec = band_picker.recommend_method(f, max_dim_m=max_dim, wire_structure=True)
        self.banner.setText(
            "Band {0} ({1}) — recommended: {2}".format(
                rec["band"], band_picker._fmt_freq(f), rec["primary_label"]))
        self.perf_view.setPlainText(self._perf_text(kind, res, rec, f))
        self._draw_sketch(kind, res, f)
        self._draw_chu(res, f)

    def _perf_text(self, kind, res, rec, f):
        from emstudio.antenna import band_picker

        lam = res["wavelength_m"]
        L = []
        L.append("PREDICTED PERFORMANCE")
        L.append("=====================")
        L.append("frequency        : {0}".format(band_picker._fmt_freq(f)))
        L.append("wavelength       : {0}".format(band_picker._fmt_wavelength(lam)))
        frac = res.get("height_over_lambda", res.get("length_over_lambda"))
        if frac is not None:
            L.append("size / lambda    : {0:.5g}".format(frac))
        L.append("electrically small: {0}".format("yes" if res["electrically_small"] else "NO"))
        L.append("")
        L.append("radiation R (Rr) : {0:.5g} ohm".format(res["radiation_resistance_ohm"]))
        if "effective_height_m" in res:
            L.append("effective height : {0:.5g} m".format(res["effective_height_m"]))
        if "effective_length_m" in res:
            L.append("effective length : {0:.5g} m".format(res["effective_length_m"]))
        L.append("radiation eff.   : {0:.4g} %".format(res["radiation_efficiency"] * 100.0))
        L.append("ka               : {0:.4g}".format(res["ka"]))
        L.append("Chu min Q        : {0:.5g}".format(res["chu_min_q"]))
        L.append("fractional BW    : {0:.4g} %  (VSWR {1:.2g})".format(
            res["fractional_bandwidth"] * 100.0, self.vswr.value()))
        bw_hz = res["fractional_bandwidth"] * f
        L.append("=> bandwidth     : {0}".format(band_picker._fmt_freq(bw_hz)))
        if kind == "monopole":
            L.append("")
            L.append("static capacitance: {0:.4g} pF".format(res["capacitance_f"] * 1e12))
            L.append("input reactance   : -j {0:.5g} ohm".format(res["capacitive_reactance_ohm"]))
            L.append("needs loading     : {0}".format("yes" if res["needs_loading"] else "no"))
            L.append("loading inductance: {0:.4g} mH  (to resonate)".format(
                res["loading_inductance_h"] * 1e3))
        L.append("")
        L.append("-- BAND -> METHOD -----------------------------------------")
        L.append(band_picker.summary_text(rec))
        return "\n".join(L)

    def _draw_sketch(self, kind, res, f):
        self.fig_sketch.clear()
        ax = self.fig_sketch.add_subplot(111)
        ax.set_aspect("equal")
        ax.axis("off")
        lam = res["wavelength_m"]

        if kind == "loop":
            r = self.dia_spin.value() / 2.0
            circ = plt_circle(0, 0, r)
            ax.plot(circ[0], circ[1], "-", color="#c87533", lw=2.5)
            ax.plot([0, r * 0.2], [-r, -r], "-", color="#333", lw=2)  # feed gap hint
            ax.annotate("", xy=(r, -r * 1.15), xytext=(-r, -r * 1.15),
                        arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
            ax.text(0, -r * 1.3, "d = {0:.3g} m".format(2 * r), ha="center",
                    color="#2b8cff")
            ax.text(0, r * 1.15, "N = {0} turns".format(self.turns_spin.value()),
                    ha="center")
            lim = r * 1.5
            ax.set_xlim(-lim, lim)
            ax.set_ylim(-lim, lim)
            title = "Small loop"
        elif kind == "monopole":
            h = self.size_spin.value()
            # ground plane
            ax.axhline(0.0, color="#4a4a55", lw=3)
            ax.fill_between([-0.6 * h, 0.6 * h], -0.08 * h, 0.0, color="#6b6b55", alpha=0.4)
            ax.plot([0, 0], [0, h], "-", color="#c87533", lw=3)  # the monopole
            # triangular current distribution (short antenna: max at base, 0 at tip)
            tri_x = np.array([0.0, 0.28 * h, 0.0])
            tri_z = np.array([0.0, h * 0.5, h])
            ax.plot(0.0 + tri_x, tri_z, "--", color="#2b8cff", lw=1.2)
            ax.plot([0, 0.15 * h], [0, 0], "-", color="#d33", lw=2)  # feed
            ax.annotate("", xy=(-0.35 * h, h), xytext=(-0.35 * h, 0),
                        arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
            ax.text(-0.4 * h, h * 0.5, "h = {0:.3g} m".format(h), rotation=90,
                    va="center", ha="right", color="#2b8cff")
            ax.text(0.3 * h, h * 0.5, "I(z)", color="#2b8cff")
            ax.set_xlim(-0.6 * h, 0.6 * h)
            ax.set_ylim(-0.15 * h, 1.2 * h)
            title = "Short monopole over ground"
        else:  # dipole
            L = self.size_spin.value()
            ax.plot([0, 0], [-L / 2, L / 2], "-", color="#c87533", lw=3)
            ax.plot([-0.08 * L, 0.08 * L], [0, 0], "-", color="#d33", lw=2)  # feed
            # triangular current (short dipole): max at the center feed, 0 at tips
            ax.plot([0.0, 0.28 * L, 0.0], [-L / 2, 0.0, L / 2], "--",
                    color="#2b8cff", lw=1.2)
            ax.annotate("", xy=(-0.35 * L, L / 2), xytext=(-0.35 * L, -L / 2),
                        arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
            ax.text(-0.4 * L, 0, "L = {0:.3g} m".format(L), rotation=90,
                    va="center", ha="right", color="#2b8cff")
            ax.set_xlim(-0.6 * L, 0.6 * L)
            ax.set_ylim(-0.7 * L, 0.7 * L)
            title = "Short dipole"

        ax.set_title("{0}  (lambda = {1})".format(
            title, _fmt_km(lam)), fontsize=9)
        self.canvas_sketch.draw_idle()

    def _draw_chu(self, res, f):
        from emstudio.antenna import small_antenna as sa

        self.fig_chu.clear()
        ax = self.fig_chu.add_subplot(111)
        ka = np.logspace(-2, 0.3, 200)
        q = 1.0 / ka ** 3 + 1.0 / ka
        ax.loglog(ka, q, "-", color="#2b8cff", lw=2, label="Chu min Q = 1/(ka)^3 + 1/(ka)")
        ka0 = res["ka"]
        if ka0 > 0:
            ax.axvline(ka0, color="#d33", ls="--", lw=1)
            ax.plot([ka0], [res["chu_min_q"]], "o", color="#d33")
            ax.text(ka0, res["chu_min_q"], "  this design\n  ka={0:.3g}, Q={1:.3g}".format(
                ka0, res["chu_min_q"]), color="#d33", fontsize=8, va="bottom")
        ax.axvline(0.5, color="#888", ls=":", lw=1)
        ax.text(0.5, q.min(), " ka=0.5\n electrically small", color="#888",
                fontsize=8, ha="left", va="bottom")
        ax.set_xlabel("ka  (electrical size)")
        ax.set_ylabel("minimum radiation Q")
        ax.grid(True, which="both", alpha=0.35)
        ax.legend(fontsize=8)
        ax.set_title("Chu-Harrington small-antenna Q limit", fontsize=9)
        self.canvas_chu.draw_idle()


def plt_circle(cx, cy, r, n=200):
    t = np.linspace(0, 2 * np.pi, n)
    return cx + r * np.cos(t), cy + r * np.sin(t)


def _fmt_km(lam):
    if lam >= 1e3:
        return "{0:.3g} km".format(lam / 1e3)
    if lam >= 1.0:
        return "{0:.3g} m".format(lam)
    return "{0:.3g} mm".format(lam * 1e3)
