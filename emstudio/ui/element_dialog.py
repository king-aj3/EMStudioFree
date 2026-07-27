# SPDX-License-Identifier: LGPL-2.1-or-later
"""Element Designer dialog (ROADMAP §1, slices E2-E5) — the family-selector shell.

Designer-shell layout (the Cable Designer precedent): one top-level
Element-family selector drives left-column pages over shared right-hand tabs
(Schematic · Predicted Performance · Verify). Shipped families: **Wire**
(dipole / monopole / folded / λ-fraction verticals, the E1 ``wire_elements``
synthesis), **Yagi-Uda** (NBS TN-688 ``yagi`` synthesis, slice E3),
**Microstrip patch** (``patch_tl`` transmission-line synthesis, openEMS Verify,
slice E4), **LPDA** (Carrel ``lpda`` synthesis over the shared
Frequency/Band-top band, crossed-TL feeder through the production writer,
slice E5 — ALL FIVE core families shipped), and **Small antenna** (routes to
the shipped VLF/LF/MF dialog). Verify runs NEC2 for wire/Yagi/LPDA and
openEMS FDTD for the patch.

* **Requirements → Recommend**: the left column captures the requirements
  schema (frequency, target gain dBd/dBi, pattern, polarization, size
  envelope, conductor Ø) and runs the deterministic
  ``element_picker.recommend_element`` rules — ranked families, each with a
  one-line printable rationale (the "AI" transparency requirement).
* **Synthesized geometry is editable**: the length spinbox carries a
  synthesized/edited badge + Reset (any synthesis input change
  re-synthesizes); "Length → f₀" is the cheap inverse.
* **Verify with NEC2** runs the design through the PRODUCTION writer
  off-thread (``run_generic_gui``) and reports predicted-vs-achieved.
  Resonance is selected by an R-WINDOW (the E1 lesson: multi-wire/harmonic
  structures have several X = 0 crossings — never take the first blindly);
  the read-out formatter is a pure function so ``gui_smoke`` gates it
  headlessly, like ``cable_dialog._fullwave_message``.
* **Accept & Generate** calls the gated templates (``makeDipole`` /
  ``makeMonopole`` with the new optional dimension overrides — defaults
  byte-identical) or builds the four-wire fold (the E1 gate's live deck).

The dialog is a thin view: every number comes from the Qt-free engines
(``wire_elements``, ``element_picker``, ``band_picker``), all gated in
``tests/validation/element_designer.py``. Reports feed-point Z and STOPS —
matching networks are §7 System Designer territory (scope contract).
"""

from __future__ import annotations

import math

from PySide import QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

C0 = 299792458.0

WIRE_TYPES = [
    ("Half-wave dipole", "dipole"),
    ("Quarter-wave monopole", "monopole"),
    ("Folded dipole", "folded"),
    ("5/8-wave vertical", "v58"),
    ("3/4-wave vertical", "v34"),
    ("Full-wave vertical", "v100"),
]
#: λ-fraction vertical kinds → electrical fraction (rows of fraction_table).
FRACTIONS = {"monopole": 0.25, "v58": 0.625, "v34": 0.75, "v100": 1.0}

#: R-window (ohm) for resonance selection per kind in the verify read-out.
#: Kinds absent here are NOT resonant by design (5/8, full-wave) — the
#: read-out reports Z at f0 instead of hunting a crossing.
VERIFY_R_WINDOWS = {
    "dipole": (40.0, 120.0),
    "monopole": (15.0, 80.0),
    "folded": (150.0, 500.0),   # the E1 gate's window (kΩ anti-resonances outside)
    "v34": (40.0, 300.0),
}


def _make_folded_analysis(doc, f0_hz, length_m, wire_radius_mm):
    """Four-wire folded dipole (the E1 gate's live deck): two parallel λ/2
    wires spaced λ/100, shorted at both ends, fed on one — spw = 42 keeps
    both long wires at equal odd segment counts. Returns the analysis."""
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    lam_mm = C0 / f0_hz * 1000.0
    L = length_m * 1000.0
    s = lam_mm / 100.0
    objs = {}
    for name, (a, b) in {
            "FedWire": ((0, 0, -L / 2), (0, 0, L / 2)),
            "ReturnWire": ((s, 0, -L / 2), (s, 0, L / 2)),
            "ShortBot": ((0, 0, -L / 2), (s, 0, -L / 2)),
            "ShortTop": ((0, 0, L / 2), (s, 0, L / 2))}.items():
        w = doc.addObject("Part::Feature", name)
        w.Shape = Part.makeLine(FreeCAD.Vector(*a), FreeCAD.Vector(*b))
        objs[name] = w
    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Folded Dipole Analysis"
    ana.FrequencyStart = "{0} MHz".format(f0_hz / 1e6 * 2.0 / 3.0)
    ana.FrequencyStop = "{0} MHz".format(f0_hz / 1e6 * 4.0 / 3.0)
    ana.FrequencyPoints = 201
    mat = material_mod.makeMaterial(doc, ana, name="WirePEC",
                                    category="Metal (PEC)")
    mat.References = [(objs[n], "Edge1") for n in
                      ("FedWire", "ReturnWire", "ShortBot", "ShortTop")]
    mat.WireRadius = "{0} mm".format(wire_radius_mm)
    port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort", direction="+Z")
    port.References = [(objs["FedWire"], "Edge1")]
    solver = solver_objs.makeSolverNEC2(doc, ana)
    solver.SegmentsPerWavelength = 42
    doc.recompute()
    return ana


class ElementDesignerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            "EMStudio — Element Designer (Wire · Yagi · Patch · LPDA · "
            "Small antenna)")
        self.resize(1150, 700)

        self._updating = False
        self._length_edited = False
        self._design = None
        self._yagi_design = None
        self._patch_design = None
        self._lpda_design = None
        self._rec = None
        self._verify_docname = None

        root = QtWidgets.QHBoxLayout(self)

        # ================= left column =================
        left = QtWidgets.QVBoxLayout()

        sel_form = QtWidgets.QFormLayout()
        self.family = QtWidgets.QComboBox()
        self.family.addItem("Wire (dipole / monopole / folded / fractions)", "wire")
        self.family.addItem("Yagi-Uda (NBS TN-688)", "yagi")
        self.family.addItem("Microstrip patch", "patch")
        self.family.addItem("LPDA (log-periodic, Carrel)", "lpda")
        self.family.addItem("Small antenna (VLF/LF/MF)", "small")
        sel_form.addRow("<b>Element family</b>", self.family)
        left.addLayout(sel_form)

        # ---- requirements (the element_picker schema) ----
        req_box = QtWidgets.QGroupBox("Requirements")
        rform = QtWidgets.QFormLayout(req_box)

        # service presets (E6): auto-fill the schema from a verified band row
        self.preset = QtWidgets.QComboBox()
        self.preset.addItem("— service preset —", None)
        from emstudio.antenna import service_presets

        for row in service_presets.PRESETS:
            self.preset.addItem(row["label"], row["key"])
        self.preset.setToolTip(
            "Fill frequency/band/polarization/pattern from a verified "
            "service band (docs/upstream/service-presets-anchors.md). "
            "US values where regions differ — see the note after applying.")
        rform.addRow("Service preset", self.preset)

        freq_row = QtWidgets.QHBoxLayout()
        self.freq = QtWidgets.QDoubleSpinBox()
        self.freq.setDecimals(4)
        self.freq.setRange(0.0001, 1e6)
        self.freq.setValue(300.0)
        self.freq_unit = QtWidgets.QComboBox()
        self.freq_unit.addItems(["Hz", "kHz", "MHz", "GHz"])
        self.freq_unit.setCurrentText("MHz")
        freq_row.addWidget(self.freq, 1)
        freq_row.addWidget(self.freq_unit)
        self.freq.setToolTip(
            "Design frequency f0 — for band designs (LPDA) this is the LOW "
            "band edge f_lo.")
        rform.addRow("Frequency", freq_row)

        band_row = QtWidgets.QHBoxLayout()
        self.band_top = QtWidgets.QDoubleSpinBox()
        self.band_top.setDecimals(4)
        self.band_top.setRange(0.0, 1e6)
        self.band_top.setValue(0.0)
        self.band_top.setSpecialValueText("single frequency")
        self.band_top.setToolTip(
            "High band edge f_hi for BAND designs — drives the recommender's "
            "wide-band (log-periodic) rule and the LPDA page. Leave at "
            "'single frequency' for resonant elements.")
        self.band_top_unit = QtWidgets.QComboBox()
        self.band_top_unit.addItems(["Hz", "kHz", "MHz", "GHz"])
        self.band_top_unit.setCurrentText("MHz")
        band_row.addWidget(self.band_top, 1)
        band_row.addWidget(self.band_top_unit)
        rform.addRow("Band top (f_hi)", band_row)

        gain_row = QtWidgets.QHBoxLayout()
        self.gain_on = QtWidgets.QCheckBox()
        self.gain_on.setToolTip("Enable a target gain (drives the Yagi rule).")
        self.gain = QtWidgets.QDoubleSpinBox()
        self.gain.setDecimals(2)
        self.gain.setRange(-10.0, 30.0)
        self.gain.setValue(7.0)
        self.gain.setEnabled(False)
        self.gain_unit = QtWidgets.QComboBox()
        self.gain_unit.addItems(["dBd", "dBi"])
        self.gain_unit.setToolTip(
            "dBd = relative to a half-wave dipole = dBi − 2.15 (both always "
            "reported — the classic silent-2.15-dB trap).")
        self.gain_unit.setEnabled(False)
        gain_row.addWidget(self.gain_on)
        gain_row.addWidget(self.gain, 1)
        gain_row.addWidget(self.gain_unit)
        rform.addRow("Target gain", gain_row)

        self.pattern = QtWidgets.QComboBox()
        self.pattern.addItem("(any)", None)
        self.pattern.addItem("Omnidirectional", "omni")
        self.pattern.addItem("Directional", "directional")
        rform.addRow("Pattern", self.pattern)

        self.polar = QtWidgets.QComboBox()
        self.polar.addItem("(any)", None)
        self.polar.addItem("Vertical", "V")
        self.polar.addItem("Horizontal", "H")
        self.polar.addItem("Circular", "CP")
        rform.addRow("Polarization", self.polar)

        self.max_dim = QtWidgets.QDoubleSpinBox()
        self.max_dim.setDecimals(3)
        self.max_dim.setRange(0.0, 1e6)
        self.max_dim.setValue(0.0)
        self.max_dim.setSuffix(" m")
        self.max_dim.setSpecialValueText("no limit")
        self.max_dim.setToolTip(
            "Largest allowed dimension — drives the Chu-bandwidth guardrail "
            "and the Yagi boom-fits rule.")
        rform.addRow("Max dimension", self.max_dim)

        self.wire_dia = QtWidgets.QDoubleSpinBox()
        self.wire_dia.setDecimals(3)
        self.wire_dia.setRange(0.01, 1000.0)
        self.wire_dia.setValue(4.0)
        self.wire_dia.setSuffix(" mm")
        self.wire_dia.setToolTip(
            "Conductor diameter — sets the end-effect K on the measured NEC2 "
            "curve (thick elements shorten more).")
        rform.addRow("Conductor Ø", self.wire_dia)

        rec_row = QtWidgets.QHBoxLayout()
        self.rec_btn = QtWidgets.QPushButton("Recommend family")
        self.rec_btn.clicked.connect(self._recommend)
        self.rec_use_btn = QtWidgets.QPushButton("Use top family")
        self.rec_use_btn.setEnabled(False)
        self.rec_use_btn.clicked.connect(self._use_recommended)
        rec_row.addWidget(self.rec_btn)
        rec_row.addWidget(self.rec_use_btn)
        rform.addRow(rec_row)

        self.rec_view = QtWidgets.QPlainTextEdit()
        self.rec_view.setReadOnly(True)
        self.rec_view.setMaximumHeight(150)
        from PySide import QtGui

        self.rec_view.setFont(QtGui.QFont("Monospace"))
        self.rec_view.setPlaceholderText(
            "Ranked element families with rationale appear here.")
        rform.addRow(self.rec_view)
        left.addWidget(req_box)

        # ---- family pages ----
        self.pages = QtWidgets.QStackedWidget()
        self.pages.addWidget(self._build_wire_page())     # index 0
        self.pages.addWidget(self._build_yagi_page())     # index 1
        self.pages.addWidget(self._build_patch_page())    # index 2
        self.pages.addWidget(self._build_lpda_page())     # index 3
        self.pages.addWidget(self._build_small_page())    # index 4
        left.addWidget(self.pages)

        # ---- actions ----
        act_row = QtWidgets.QHBoxLayout()
        # the button labels name the per-family solver (set in _family_changed):
        # NEC2 for wire/Yagi, openEMS for the patch.
        self.verify_btn = QtWidgets.QPushButton("Verify with NEC2")
        self.verify_btn.clicked.connect(self._verify)
        self.accept_btn = QtWidgets.QPushButton("Accept && Generate")
        self.accept_btn.clicked.connect(self._accept_generate)
        self.report_btn = QtWidgets.QPushButton("PDF Report…")
        self.report_btn.setToolTip(
            "Save a build report (design summary + dimensioned sketch + "
            "element schedule) — the deliverable a build house needs.")
        self.report_btn.clicked.connect(self._save_report)
        act_row.addWidget(self.verify_btn)
        act_row.addWidget(self.accept_btn)
        act_row.addWidget(self.report_btn)
        left.addLayout(act_row)
        left.addStretch(1)
        root.addLayout(left, 0)

        # ================= right column =================
        right = QtWidgets.QVBoxLayout()
        self.banner = QtWidgets.QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "QLabel { background: #234; color: #dfe8f4; padding: 8px; "
            "border-radius: 4px; }")
        right.addWidget(self.banner)

        self.tabs = QtWidgets.QTabWidget()
        self.fig_sketch = Figure(figsize=(5, 5), tight_layout=True)
        self.canvas_sketch = FigureCanvas(self.fig_sketch)
        self.tabs.addTab(self.canvas_sketch, "Schematic")
        self.perf_view = QtWidgets.QPlainTextEdit()
        self.perf_view.setReadOnly(True)
        self.perf_view.setFont(QtGui.QFont("Monospace"))
        self.tabs.addTab(self.perf_view, "Predicted Performance")
        self.verify_view = QtWidgets.QPlainTextEdit()
        self.verify_view.setReadOnly(True)
        self.verify_view.setFont(QtGui.QFont("Monospace"))
        self.verify_view.setPlaceholderText(
            "Run 'Verify with NEC2' for a predicted-vs-achieved read-out.")
        self.tabs.addTab(self.verify_view, "Verify")
        right.addWidget(self.tabs, 1)
        root.addLayout(right, 1)

        # solver availability gates the Verify button per family (NEC2 for
        # wire/Yagi, openEMS for the patch)
        try:
            from emstudio.setup import solvers as solver_setup

            self._nec2_found = bool(solver_setup.find_backend("nec2").found)
            self._openems_found = bool(solver_setup.find_backend("openems").found)
        except Exception:  # noqa: BLE001 — availability probe is best-effort
            self._nec2_found = True
            self._openems_found = True

        # ---- signals ----
        self.preset.currentIndexChanged.connect(self._apply_preset)
        self.family.currentIndexChanged.connect(self._family_changed)
        self.gain_on.toggled.connect(self.gain.setEnabled)
        self.gain_on.toggled.connect(self.gain_unit.setEnabled)
        for w in (self.freq.valueChanged, self.freq_unit.currentIndexChanged,
                  self.wire_dia.valueChanged,
                  self.wtype.currentIndexChanged,
                  self.kmode.currentIndexChanged, self.kcustom.valueChanged):
            w.connect(self._synthesis_input_changed)
        self.length.valueChanged.connect(self._length_changed)
        self.reset_btn.clicked.connect(self._reset_length)
        self.inv_btn.clicked.connect(self._length_to_f0)
        for w in (self.yagi_gain.valueChanged,
                  self.yagi_gain_unit.currentIndexChanged,
                  self.yagi_boom.currentIndexChanged,
                  self.yagi_boom_dia.valueChanged):
            w.connect(self._recalc)
        for w in (self.patch_er.valueChanged, self.patch_h.valueChanged,
                  self.patch_preset.currentIndexChanged,
                  self.patch_z.valueChanged):
            w.connect(self._recalc)
        for w in (self.band_top.valueChanged,
                  self.band_top_unit.currentIndexChanged,
                  self.lpda_by.currentIndexChanged,
                  self.lpda_gain.valueChanged, self.lpda_tau.valueChanged,
                  self.lpda_sigma.valueChanged, self.lpda_r0.valueChanged):
            w.connect(self._recalc)
        # QDialog.reject() (Esc) returns from exec() WITHOUT firing closeEvent,
        # so rely on the finished signal (fires on accept AND reject) to clean
        # up the transient verify document. _close_verify_doc is idempotent.
        self.finished.connect(lambda _r: self._close_verify_doc())

        self._family_changed()

    # ================= page builders =================
    def _build_wire_page(self):
        page = QtWidgets.QGroupBox("Wire element (E1 synthesis)")
        form = QtWidgets.QFormLayout(page)

        self.wtype = QtWidgets.QComboBox()
        for label, key in WIRE_TYPES:
            self.wtype.addItem(label, key)
        form.addRow("Type", self.wtype)

        krow = QtWidgets.QHBoxLayout()
        self.kmode = QtWidgets.QComboBox()
        self.kmode.addItem("Thin-wire default (K = 0.95)", "default")
        self.kmode.addItem("NEC2-measured curve (uses Ø)", "curve")
        self.kmode.addItem("Custom…", "custom")
        self.kmode.setToolTip(
            "End-effect shortening K: L = K·c/(2f). The printed 468/f embeds "
            "K = 0.9516; the measured curve is this repo's own NEC2 "
            "(published charts disagree ±0.01).")
        self.kcustom = QtWidgets.QDoubleSpinBox()
        self.kcustom.setDecimals(4)
        self.kcustom.setRange(0.85, 1.0)
        self.kcustom.setValue(0.95)
        self.kcustom.setEnabled(False)
        self.kmode.currentIndexChanged.connect(
            lambda _i: self.kcustom.setEnabled(
                self.kmode.currentData() == "custom"))
        krow.addWidget(self.kmode, 1)
        krow.addWidget(self.kcustom)
        form.addRow("K factor", krow)

        lrow = QtWidgets.QHBoxLayout()
        self.length = QtWidgets.QDoubleSpinBox()
        self.length.setDecimals(6)
        self.length.setRange(1e-4, 1e6)  # up to ~140 Hz wire; below that -> small antenna
        self.length.setSuffix(" m")
        self.badge = QtWidgets.QLabel("synthesized")
        self.badge.setStyleSheet("QLabel { color: #2b8cff; }")
        self.reset_btn = QtWidgets.QPushButton("Reset")
        self.reset_btn.setToolTip("Back to the synthesized length.")
        lrow.addWidget(self.length, 1)
        lrow.addWidget(self.badge)
        lrow.addWidget(self.reset_btn)
        form.addRow("Length / height", lrow)

        self.inv_btn = QtWidgets.QPushButton("Length → f₀")
        self.inv_btn.setToolTip(
            "Inverse solve: set the frequency this length resonates at "
            "(f₀ = K·fraction·c / L).")
        form.addRow(self.inv_btn)
        return page

    def _build_yagi_page(self):
        page = QtWidgets.QGroupBox("Yagi-Uda (NBS TN-688)")
        form = QtWidgets.QFormLayout(page)

        self.yagi_by = QtWidgets.QComboBox()
        self.yagi_by.addItem("By gain target", "gain")
        self.yagi_by.addItem("By boom length", "boom")
        self.yagi_by.setToolTip(
            "Pick the smallest TN-688 boom meeting a gain target, or a boom "
            "length directly.")
        form.addRow("Design by", self.yagi_by)

        grow = QtWidgets.QHBoxLayout()
        self.yagi_gain = QtWidgets.QDoubleSpinBox()
        self.yagi_gain.setDecimals(2)
        self.yagi_gain.setRange(6.0, 16.5)
        self.yagi_gain.setValue(10.0)
        self.yagi_gain_unit = QtWidgets.QComboBox()
        self.yagi_gain_unit.addItems(["dBd", "dBi"])
        self.yagi_gain_unit.setToolTip("TN-688 gains are dBd; dBi = dBd + 2.15.")
        grow.addWidget(self.yagi_gain, 1)
        grow.addWidget(self.yagi_gain_unit)
        form.addRow("Target gain", grow)

        self.yagi_boom = QtWidgets.QComboBox()
        for b in (0.4, 0.8, 1.2, 2.2, 3.2, 4.2):
            self.yagi_boom.addItem("{0:g} lambda".format(b), b)
        self.yagi_boom.setCurrentIndex(1)  # 0.8 lambda
        self.yagi_boom.setEnabled(False)  # default is "by gain target"
        form.addRow("Boom length", self.yagi_boom)

        self.yagi_boom_dia = QtWidgets.QDoubleSpinBox()
        self.yagi_boom_dia.setDecimals(1)
        self.yagi_boom_dia.setRange(0.0, 200.0)
        self.yagi_boom_dia.setValue(0.0)
        self.yagi_boom_dia.setSuffix(" mm")
        self.yagi_boom_dia.setSpecialValueText("no metal boom")
        self.yagi_boom_dia.setToolTip(
            "Metal support-boom diameter — adds the Fig 10 build correction to "
            "the physical cut lengths (0 = non-conductive boom / bare wires; "
            "the NEC2 model is always bare wires).")
        form.addRow("Metal boom Ø", self.yagi_boom_dia)

        self.yagi_by.currentIndexChanged.connect(self._yagi_by_changed)
        return page

    def _yagi_by_changed(self):
        by_gain = self.yagi_by.currentData() == "gain"
        self.yagi_gain.setEnabled(by_gain)
        self.yagi_gain_unit.setEnabled(by_gain)
        self.yagi_boom.setEnabled(not by_gain)
        self._recalc()

    def _build_patch_page(self):
        page = QtWidgets.QGroupBox("Microstrip patch (transmission-line synthesis)")
        form = QtWidgets.QFormLayout(page)

        # common laminates: (label, er, h_mm). h is the standard thickness.
        self.patch_preset = QtWidgets.QComboBox()
        self._PATCH_PRESETS = [
            ("— substrate preset —", None, None),
            ("RT/duroid 5880 (er 2.20, 1.575 mm)", 2.20, 1.575),
            ("Rogers RO4003C (er 3.38, 1.524 mm)", 3.38, 1.524),
            ("Rogers RO4350B (er 3.48, 1.524 mm)", 3.48, 1.524),
            ("FR-4 (er 4.40, 1.600 mm)", 4.40, 1.600),
            ("Alumina (er 9.80, 0.635 mm)", 9.80, 0.635),
        ]
        for label, _e, _h in self._PATCH_PRESETS:
            self.patch_preset.addItem(label)
        form.addRow("Substrate preset", self.patch_preset)

        self.patch_er = QtWidgets.QDoubleSpinBox()
        self.patch_er.setDecimals(2)
        self.patch_er.setRange(1.0, 20.0)
        self.patch_er.setValue(3.38)
        form.addRow("Substrate εr", self.patch_er)

        self.patch_h = QtWidgets.QDoubleSpinBox()
        self.patch_h.setDecimals(3)
        self.patch_h.setRange(0.05, 20.0)
        self.patch_h.setValue(1.524)
        self.patch_h.setSuffix(" mm")
        form.addRow("Substrate height h", self.patch_h)

        self.patch_z = QtWidgets.QDoubleSpinBox()
        self.patch_z.setDecimals(1)
        self.patch_z.setRange(10.0, 300.0)
        self.patch_z.setValue(50.0)
        self.patch_z.setSuffix(" ohm")
        self.patch_z.setToolTip(
            "Feed impedance for the inset/probe placement (the offset is a "
            "two-slot ESTIMATE — openEMS Verify refines it).")
        form.addRow("Feed impedance", self.patch_z)

        note = QtWidgets.QLabel(
            "Uses the shared Frequency (left). TL model ±5% on f_res — Verify "
            "with openEMS (FDTD, ~seconds-minutes) for the achieved resonance "
            "and gain.")
        note.setWordWrap(True)
        note.setStyleSheet("QLabel { color: #888; }")
        form.addRow(note)

        self.patch_preset.currentIndexChanged.connect(self._patch_preset_changed)
        return page

    def _patch_preset_changed(self):
        idx = self.patch_preset.currentIndex()
        if 0 <= idx < len(self._PATCH_PRESETS):
            _label, er, h = self._PATCH_PRESETS[idx]
            if er is not None:
                self.patch_er.setValue(er)
                self.patch_h.setValue(h)  # → _recalc via valueChanged

    def _build_lpda_page(self):
        page = QtWidgets.QGroupBox("LPDA (Carrel log-periodic synthesis)")
        form = QtWidgets.QFormLayout(page)

        self.lpda_by = QtWidgets.QComboBox()
        self.lpda_by.addItem("By gain target (optimum sigma)", "gain")
        self.lpda_by.addItem("By explicit tau / sigma", "explicit")
        self.lpda_by.setToolTip(
            "Gain target picks tau on Carrel's optimum-sigma line "
            "(Butson-Thompson corrected contours); explicit tau/sigma "
            "designs off-line geometries.")
        form.addRow("Design by", self.lpda_by)

        self.lpda_gain = QtWidgets.QDoubleSpinBox()
        self.lpda_gain.setDecimals(2)
        self.lpda_gain.setRange(6.5, 11.0)
        self.lpda_gain.setValue(8.0)
        self.lpda_gain.setSuffix(" dBi")
        self.lpda_gain.setToolTip(
            "Free-space directivity on the CORRECTED contour calibration "
            "(Carrel's original labels read 1 dB higher).")
        form.addRow("Target gain", self.lpda_gain)

        self.lpda_tau = QtWidgets.QDoubleSpinBox()
        self.lpda_tau.setDecimals(3)
        self.lpda_tau.setRange(0.700, 0.980)
        self.lpda_tau.setSingleStep(0.005)
        self.lpda_tau.setValue(0.865)
        self.lpda_tau.setEnabled(False)
        form.addRow("Scale factor τ", self.lpda_tau)

        self.lpda_sigma = QtWidgets.QDoubleSpinBox()
        self.lpda_sigma.setDecimals(3)
        self.lpda_sigma.setRange(0.030, 0.220)
        self.lpda_sigma.setSingleStep(0.005)
        self.lpda_sigma.setValue(0.158)
        self.lpda_sigma.setEnabled(False)
        form.addRow("Spacing σ", self.lpda_sigma)

        self.lpda_r0 = QtWidgets.QDoubleSpinBox()
        self.lpda_r0.setDecimals(1)
        self.lpda_r0.setRange(20.0, 300.0)
        self.lpda_r0.setValue(65.0)
        self.lpda_r0.setSuffix(" ohm")
        self.lpda_r0.setToolTip(
            "Target mean input resistance — sets the crossed-feeder Z0 "
            "(Carrel: the achieved band mean is within ~10%).")
        form.addRow("Target R0", self.lpda_r0)

        note = QtWidgets.QLabel(
            "Band: Frequency (left) = f_lo, Band top = f_hi. The crossed "
            "feeder is modeled with NEC2 TL cards (ideal line); expect "
            "log-periodic ripple around R0 and a gain droop at exactly "
            "f_lo (truncated active region).")
        note.setWordWrap(True)
        note.setStyleSheet("QLabel { color: #888; }")
        form.addRow(note)

        self.lpda_by.currentIndexChanged.connect(self._lpda_by_changed)
        return page

    def _lpda_by_changed(self):
        by_gain = self.lpda_by.currentData() == "gain"
        self.lpda_gain.setEnabled(by_gain)
        self.lpda_tau.setEnabled(not by_gain)
        self.lpda_sigma.setEnabled(not by_gain)

    def _build_small_page(self):
        page = QtWidgets.QGroupBox("Small antenna (VLF/LF/MF)")
        lay = QtWidgets.QVBoxLayout(page)
        note = QtWidgets.QLabel(
            "Electrically-small elements (below ~λ/10, or any request under "
            "3 MHz) are the Chu-Harrington regime: radiation resistance, "
            "loading, efficiency and the Q/bandwidth limit dominate. The "
            "shipped Small-Antenna Designer handles this family — analytic "
            "models plus the NEC2 monopole-over-ground path.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.small_btn = QtWidgets.QPushButton("Open Small-Antenna Designer…")
        self.small_btn.clicked.connect(self._open_small)
        lay.addWidget(self.small_btn)
        lay.addStretch(1)
        return page

    # ================= input helpers =================
    def _freq_hz(self):
        mult = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6,
                "GHz": 1e9}[self.freq_unit.currentText()]
        return self.freq.value() * mult

    def _wire_kind(self):
        return self.wtype.currentData()

    def _k_arg(self):
        mode = self.kmode.currentData()
        if mode == "curve":
            return "curve"
        if mode == "custom":
            return self.kcustom.value()
        return None

    def _wire_d_m(self):
        return self.wire_dia.value() * 1e-3

    # ================= service presets =================
    @staticmethod
    def _fill_freq_widgets(freq_spin, unit_combo, f_hz):
        """Pick the natural unit and set the spinbox (shared by f0/band-top)."""
        for unit, mult in (("GHz", 1e9), ("MHz", 1e6), ("kHz", 1e3)):
            if f_hz >= mult:
                unit_combo.setCurrentText(unit)
                freq_spin.setValue(f_hz / mult)
                return
        unit_combo.setCurrentText("Hz")
        freq_spin.setValue(f_hz)

    def _apply_preset(self):
        """Auto-fill the requirements schema from the selected service row."""
        key = self.preset.currentData()
        if not key:
            return
        from emstudio.antenna import service_presets

        row = service_presets.apply_preset(key)
        if "f0_hz" in row:
            self._fill_freq_widgets(self.freq, self.freq_unit, row["f0_hz"])
            self.band_top.setValue(0.0)  # spot service
        else:
            self._fill_freq_widgets(self.freq, self.freq_unit, row["f_lo_hz"])
            self._fill_freq_widgets(self.band_top, self.band_top_unit,
                                    row["f_hi_hz"])
        pol_idx = self.polar.findData(row["polarization"])
        self.polar.setCurrentIndex(pol_idx if pol_idx >= 0 else 0)
        pat_idx = self.pattern.findData(row["pattern"])
        self.pattern.setCurrentIndex(pat_idx if pat_idx >= 0 else 0)
        self.rec_view.setPlainText(
            "{0}\n\n{1}\n\nRegion: {2}\n\nNow hit 'Recommend family' (or "
            "design directly).".format(row["label"], row["note"],
                                       row["region_note"]))

    # ================= recommender =================
    def _band_top_hz(self):
        mult = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6,
                "GHz": 1e9}[self.band_top_unit.currentText()]
        return self.band_top.value() * mult

    def _requirements(self):
        f_hi = self._band_top_hz()
        if f_hi > 0.0:
            req = {"f_lo_hz": self._freq_hz(), "f_hi_hz": f_hi,
                   "wire_d_m": self._wire_d_m()}
        else:
            req = {"f0_hz": self._freq_hz(), "wire_d_m": self._wire_d_m()}
        if self.gain_on.isChecked():
            key = "gain_dbd" if self.gain_unit.currentText() == "dBd" else "gain_dbi"
            req[key] = self.gain.value()
        req["pattern"] = self.pattern.currentData()
        req["polarization"] = self.polar.currentData()
        if self.max_dim.value() > 0:
            req["max_dim_m"] = self.max_dim.value()
        return req

    def _recommend(self):
        from emstudio.antenna import element_picker

        self._rec = element_picker.recommend_element(self._requirements())
        text = element_picker.summary_text(self._rec)
        top = self._rec["candidates"][0] if self._rec["candidates"] else None
        if top and not top["available"]:
            avail = next((c for c in self._rec["candidates"] if c["available"]),
                         None)
            if avail:
                text += ("\n\n'{0}' ships in slice {1} — the best AVAILABLE "
                         "family today is '{2}'.".format(
                             top["label"], top["ships_in"], avail["label"]))
        self.rec_view.setPlainText(text)
        self.rec_use_btn.setEnabled(top is not None)

    #: recommender family key -> dialog family-selector data key (available fams)
    _FAMILY_PAGE = {"wire": "wire", "yagi": "yagi", "patch": "patch",
                    "lpda": "lpda", "small_antenna": "small"}

    def _use_recommended(self):
        if not self._rec or not self._rec["candidates"]:
            return
        avail = next((c for c in self._rec["candidates"] if c["available"]), None)
        if avail is None:
            return
        idx = self.family.findData(
            self._FAMILY_PAGE.get(avail["family"], "wire"))
        if idx >= 0:
            self.family.setCurrentIndex(idx)

    # ================= recalc =================
    def _family_changed(self):
        fam = self.family.currentData()
        self.pages.setCurrentIndex(
            {"wire": 0, "yagi": 1, "patch": 2, "lpda": 3, "small": 4}[fam])
        can_solve = fam in ("wire", "yagi", "patch", "lpda")
        if fam == "patch":
            solver_ok, missing, solver = self._openems_found, "openEMS", "openEMS"
        else:
            solver_ok, missing, solver = self._nec2_found, "nec2c", "NEC2"
        self._solver_name = solver
        self.verify_btn.setText("Verify with {0}".format(solver))
        self.verify_btn.setEnabled(can_solve and solver_ok)
        self.verify_btn.setToolTip(
            "{0} not found — use Detect / Install Solvers.".format(missing)
            if (can_solve and not solver_ok) else
            "Solve this design through the production {0} solver (off-thread) "
            "and report predicted vs achieved.".format(solver))
        self.accept_btn.setEnabled(can_solve)
        self.accept_btn.setToolTip(
            "Create the runnable FreeCAD analysis (geometry + material + feed + "
            "{0} solver) in the active document.".format(solver))
        self.report_btn.setEnabled(can_solve)
        self._recalc()

    def _synthesis_input_changed(self, *_a):
        self._length_edited = False
        self._recalc()

    def _length_changed(self, *_a):
        if self._updating:
            return
        self._length_edited = True
        self.badge.setText("edited")
        self.badge.setStyleSheet("QLabel { color: #d38b2b; }")
        self._refresh_predicted()

    def _reset_length(self):
        self._length_edited = False
        self._recalc()

    def _length_to_f0(self):
        """Inverse: the frequency at which THIS length is the design length —
        f0 = K·(electrical fraction)·c / L. In "curve" K mode K depends on f,
        so solve the fixed point f0 = K(f0)·frac·c/L (a few iterations) — that
        keeps the result self-consistent with the resynthesis it triggers, so
        the typed length is not silently shifted."""
        from emstudio.antenna import wire_elements as we

        design = self._design
        if not design:
            return
        kind = self._wire_kind()
        frac = 0.5 if kind in ("dipole", "folded") else FRACTIONS[kind]
        L = self.length.value()
        d = self._wire_d_m()
        k_arg = self._k_arg()
        f0 = design["k_factor"] * frac * C0 / L
        for _ in range(6):  # constant-K modes converge in one step
            f0 = we._resolve_k(f0, d, k_arg) * frac * C0 / L
        mult = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6,
                "GHz": 1e9}[self.freq_unit.currentText()]
        self.freq.setValue(f0 / mult)  # → _synthesis_input_changed → recalc

    def _synthesize(self):
        """Run the E1 engine for the current wire type. Returns the design
        dict (fraction rows adapted to the same keys)."""
        from emstudio.antenna import wire_elements as we

        f = self._freq_hz()
        d = self._wire_d_m()
        k = self._k_arg()
        kind = self._wire_kind()
        if kind == "dipole":
            return we.design_dipole(f, d, k_factor=k)
        if kind == "monopole":
            return we.design_monopole(f, d, k_factor=k)
        if kind == "folded":
            return we.design_folded_dipole(f, d, k_factor=k)
        table = we.fraction_table(f, wire_d_m=d, k_factor=k)
        row = next(r for r in table["rows"]
                   if abs(r["fraction"] - FRACTIONS[kind]) < 1e-9)
        design = dict(row)
        design["feed_r_ohm"] = None      # not resonant / rising-R rows
        design["feed_x_ohm"] = None
        design["warnings"] = [row["note"]]
        design["source_note"] = (
            "{0}: electrical fraction {1:g}*lambda -> physical L = "
            "K*fraction*lambda (K={2:.4f}); see the note above for the feed/"
            "gain caveats".format(row["name"], row["fraction"], row["k_factor"]))
        return design

    def _recalc(self):
        from emstudio.antenna import band_picker

        f = self._freq_hz()
        fam = self.family.currentData()
        if fam == "yagi":
            self._recalc_yagi()
            return
        if fam == "patch":
            self._recalc_patch()
            return
        if fam == "lpda":
            self._recalc_lpda()
            return
        if fam == "small":
            rec = band_picker.recommend_method(f, wire_structure=True)
            self.banner.setText("Band {0} ({1}) — recommended: {2}".format(
                rec["band"], band_picker._fmt_freq(f), rec["primary_label"]))
            self.perf_view.setPlainText(
                "Small-antenna family — open the dedicated designer (left) "
                "for radiation resistance, loading and the Chu limit.\n\n"
                + band_picker.summary_text(rec))
            self.fig_sketch.clear()
            ax = self.fig_sketch.add_subplot(111)
            ax.axis("off")
            ax.text(0.5, 0.5, "Small-antenna family:\nuse the dedicated "
                    "designer (left column)", ha="center", va="center")
            self.canvas_sketch.draw_idle()
            return

        try:
            design = self._synthesize()
        except Exception as exc:  # noqa: BLE001 — surfaced in the read-out
            self.perf_view.setPlainText("Invalid inputs: {0}".format(exc))
            return
        self._design = design
        self._design_f0 = f
        if not self._length_edited:
            self._updating = True
            self.length.setValue(design["length_m"])
            self._updating = False
            self.badge.setText("synthesized")
            self.badge.setStyleSheet("QLabel { color: #2b8cff; }")

        rec = band_picker.recommend_method(
            f, max_dim_m=design["length_m"], wire_structure=True)
        self.banner.setText("Band {0} ({1}) — recommended: {2}".format(
            rec["band"], band_picker._fmt_freq(f), rec["primary_label"]))
        self._refresh_predicted()
        self._draw_schematic()

    def _refresh_predicted(self):
        from emstudio.antenna import band_picker

        design = self._design
        if not design:
            return
        f = self._design_f0
        kind = self._wire_kind()
        label = self.wtype.currentText()
        L = []
        L.append("PREDICTED PERFORMANCE — {0}".format(label))
        L.append("=" * (26 + len(label)))
        if kind in ("v58", "v100"):
            # loading flag up front (E6): the 5/8-wave feed is capacitive
            # (series-L base network) and the full-wave is anti-resonant
            # (very high feed Z) — both need matching before they are
            # usable. The 3/4-wave is resonant (engine row note) — no flag.
            L.append(">>> LOADING REQUIRED: this fraction's feed is not a "
                     "usable resistive match — budget a base matching/"
                     "loading network (section-7); details in the notes "
                     "below <<<")
            L.append("")
        L.append("frequency        : {0}".format(band_picker._fmt_freq(f)))
        L.append("wavelength       : {0}".format(
            band_picker._fmt_wavelength(C0 / f)))
        L.append("K factor         : {0:.5f}   (lambda/2d = {1:.0f})".format(
            design["k_factor"], design.get("halfwave_over_d", float("inf"))))
        L.append("synthesized L    : {0:.6g} m  ({1:.2f} ft)".format(
            design["length_m"], design["length_ft"]))
        if self._length_edited:
            L.append("EDITED length    : {0:.6g} m — predictions below refer "
                     "to the SYNTHESIZED length; Verify with NEC2 for the "
                     "edited geometry".format(self.length.value()))
        if design.get("feed_r_ohm") is not None:
            L.append("feed Z (design)  : {0:.1f} {1} j{2:.1f} ohm".format(
                design["feed_r_ohm"],
                "+" if design["feed_x_ohm"] >= 0 else "-",
                abs(design["feed_x_ohm"])))
        else:
            L.append("feed Z           : not resonant by design — see the "
                     "notes (matching is section-7 territory)")
        L.append("gain             : {0:.2f} dBi = {1:+.2f} dBd".format(
            design["gain_dbi"], design["gain_dbd"]))
        if kind in ("monopole", "v58", "v34", "v100"):
            L.append("                   (over a good ground plane)")
        for w in design.get("warnings", []):
            L.append("")
            L.append("warning: {0}".format(w))
        L.append("")
        L.append("source: {0}".format(design.get("source_note", "")))
        self.perf_view.setPlainText("\n".join(L))

    # ================= schematic =================
    def _draw_schematic(self):
        design = self._design
        if not design:
            return
        kind = self._wire_kind()
        Lm = design["length_m"]
        f = self._design_f0
        lam = C0 / f
        self.fig_sketch.clear()
        ax = self.fig_sketch.add_subplot(111)
        ax.set_aspect("equal")
        ax.axis("off")

        if kind in ("dipole", "folded"):
            ax.plot([0, 0], [-Lm / 2, Lm / 2], "-", color="#c87533", lw=3)
            ax.plot([-0.06 * Lm, 0.06 * Lm], [0, 0], "-", color="#d33", lw=2)
            if kind == "folded":
                s = lam / 100.0
                sx = max(s, 0.04 * Lm)  # visual spacing floor
                ax.plot([sx, sx], [-Lm / 2, Lm / 2], "-", color="#c87533", lw=3)
                ax.plot([0, sx], [Lm / 2, Lm / 2], "-", color="#c87533", lw=3)
                ax.plot([0, sx], [-Lm / 2, -Lm / 2], "-", color="#c87533", lw=3)
                ax.text(sx * 1.2, 0, "s = λ/100 = {0:.3g} m".format(s),
                        color="#666", fontsize=8, va="center")
            ax.annotate("", xy=(-0.3 * Lm, Lm / 2), xytext=(-0.3 * Lm, -Lm / 2),
                        arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
            ax.text(-0.35 * Lm, 0, "L = {0:.4g} m".format(Lm), rotation=90,
                    va="center", ha="right", color="#2b8cff")
            ax.set_xlim(-0.6 * Lm, 0.6 * Lm)
            ax.set_ylim(-0.7 * Lm, 0.7 * Lm)
        else:
            h = Lm
            ax.axhline(0.0, color="#4a4a55", lw=3)
            ax.fill_between([-0.6 * h, 0.6 * h], -0.08 * h, 0.0,
                            color="#6b6b55", alpha=0.4)
            ax.plot([0, 0], [0, h], "-", color="#c87533", lw=3)
            ax.plot([0, 0.12 * h], [0, 0], "-", color="#d33", lw=2)
            # standing-wave current hint: I(z) ∝ sin(k·(h − z)) from the open tip
            frac = FRACTIONS[kind]
            z = np.linspace(0.0, h, 120)
            cur = np.sin(2.0 * np.pi * frac * (1.0 - z / h))
            ax.plot(0.25 * h * cur, z, "--", color="#2b8cff", lw=1.2)
            ax.annotate("", xy=(-0.35 * h, h), xytext=(-0.35 * h, 0),
                        arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
            ax.text(-0.4 * h, h * 0.5, "h = {0:.4g} m".format(h), rotation=90,
                    va="center", ha="right", color="#2b8cff")
            ax.text(0.3 * h, h * 0.55, "I(z)", color="#2b8cff")
            ax.set_xlim(-0.6 * h, 0.6 * h)
            ax.set_ylim(-0.15 * h, 1.2 * h)

        ax.set_title("{0}  ({1:.4g} m at {2:.4g} MHz, K = {3:.4f})".format(
            self.wtype.currentText(), Lm, f / 1e6, design["k_factor"]),
            fontsize=9)
        self.canvas_sketch.draw_idle()

    # ================= yagi family =================
    def _recalc_yagi(self):
        from emstudio.antenna import band_picker
        from emstudio.antenna import yagi as yg

        f = self._freq_hz()
        d = self._wire_d_m()
        boom_d = self.yagi_boom_dia.value() / 1000.0
        try:
            if self.yagi_by.currentData() == "gain":
                g = self.yagi_gain.value()
                gain_dbd = (g if self.yagi_gain_unit.currentText() == "dBd"
                            else g - 2.15)
                design = yg.design_yagi(f, gain_dbd=gain_dbd, wire_d_m=d,
                                        boom_d_m=boom_d)
            else:
                design = yg.design_yagi(
                    f, boom_lambda=float(self.yagi_boom.currentData()),
                    wire_d_m=d, boom_d_m=boom_d)
        except Exception as exc:  # noqa: BLE001 — surfaced in the read-out
            self._yagi_design = None
            # a failed synthesis (e.g. a gain target above the TN-688 table)
            # must disable Verify/Accept so they never dereference a None design
            self.verify_btn.setEnabled(False)
            self.accept_btn.setEnabled(False)
            self.perf_view.setPlainText("Invalid Yagi inputs: {0}".format(exc))
            self.fig_sketch.clear()
            self.canvas_sketch.draw_idle()
            return
        self._yagi_design = design
        self.verify_btn.setEnabled(self._nec2_found)
        self.accept_btn.setEnabled(True)
        rec = band_picker.recommend_method(
            f, max_dim_m=design["boom_length_m"], wire_structure=True)
        self.banner.setText("Band {0} ({1}) — recommended: {2}".format(
            rec["band"], band_picker._fmt_freq(f), rec["primary_label"]))
        self._refresh_predicted_yagi()
        self._draw_schematic_yagi()

    def _refresh_predicted_yagi(self):
        from emstudio.antenna import band_picker

        d = self._yagi_design
        if not d:
            return
        L = ["PREDICTED PERFORMANCE — Yagi-Uda ({0:g} lambda boom)".format(
            d["boom_lambda"])]
        L.append("=" * 52)
        L.append("frequency        : {0}".format(
            band_picker._fmt_freq(d["f0_hz"])))
        L.append("wavelength       : {0}".format(
            band_picker._fmt_wavelength(d["wavelength_m"])))
        L.append("elements         : {0}  (reflector + driven + {1} "
                 "directors)".format(d["n_elements"], d["n_directors"]))
        L.append("boom length      : {0:.4g} m  ({1:g} lambda)".format(
            d["boom_length_m"], d["boom_lambda"]))
        L.append("director spacing : {0:.4g} m  ({1:g} lambda)".format(
            d["director_spacing_m"], d["director_spacing_lambda"]))
        L.append("gain (NBS meas.) : {0:.2f} dBi = {1:.2f} dBd".format(
            d["gain_dbi"], d["gain_dbd"]))
        L.append("d/lambda         : {0:.4f}".format(d["d_over_lambda"]))
        if d["boom_correction_lambda"]:
            L.append("boom correction  : {0:+.4f} lambda (added to the cut "
                     "lengths below)".format(d["boom_correction_lambda"]))
        L.append("")
        L.append("element            pos (m)   L_wire (m)   L_cut (m)")
        for e in d["elements"]:
            L.append("  {0:15s} {1:8.4f} {2:11.4f} {3:11.4f}".format(
                e["name"], e["position_m"], e["length_m"], e["cut_length_m"]))
        L.append("")
        L.append("driven feed      : ~{0:.0f} ohm plain dipole / ~{1:.0f} ohm "
                 "folded (E1)".format(
                     d["driven_feed_r_ohm"], d["folded_driven_feed_r_ohm"]))
        for w in d.get("warnings", []):
            L.append("")
            L.append("warning: {0}".format(w))
        L.append("")
        L.append("source: {0}".format(d.get("source_note", "")))
        self.perf_view.setPlainText("\n".join(L))

    def _draw_schematic_yagi(self):
        d = self._yagi_design
        if not d:
            return
        self.fig_sketch.clear()
        ax = self.fig_sketch.add_subplot(111)
        ax.set_aspect("equal")
        ax.axis("off")
        xs = [e["position_m"] for e in d["elements"]]
        maxlen = max(e["length_m"] for e in d["elements"])
        ax.plot([min(xs), max(xs)], [0, 0], "-", color="#666", lw=2)  # boom
        driven = None
        for e in d["elements"]:
            x = e["position_m"]
            half = e["length_m"] / 2.0
            color = "#d33" if e["kind"] == "driven" else "#c87533"
            ax.plot([x, x], [-half, half], "-", color=color, lw=2.5)
            if e["kind"] == "driven":
                driven = e
        if driven is not None:
            ax.plot([driven["position_m"]], [0], "o", color="#d33", ms=5)
            ax.text(driven["position_m"], maxlen * 0.62, "DE", fontsize=7,
                    ha="center", color="#d33")
        ax.text(min(xs), maxlen * 0.62, "REFL", fontsize=7, ha="center",
                color="#888")
        span = max(max(xs) - min(xs), 1e-9)
        ax.annotate("", xy=(max(xs), -maxlen * 0.62),
                    xytext=(min(xs), -maxlen * 0.62),
                    arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
        ax.text((min(xs) + max(xs)) / 2.0, -maxlen * 0.74,
                "boom {0:.3g} m".format(d["boom_length_m"]), ha="center",
                color="#2b8cff", fontsize=8)
        ax.set_xlim(min(xs) - 0.08 * span, max(xs) + 0.08 * span)
        ax.set_ylim(-maxlen * 0.9, maxlen * 0.75)
        ax.set_title("Yagi-Uda {0:g}λ — {1} elements, {2:.1f} dBd "
                     "(fires along the boom →)".format(
                         d["boom_lambda"], d["n_elements"], d["gain_dbd"]),
                     fontsize=8)
        self.canvas_sketch.draw_idle()

    # ================= LPDA family =================
    def _recalc_lpda(self):
        from emstudio.antenna import band_picker
        from emstudio.antenna import lpda as lp

        f_lo = self._freq_hz()
        f_hi = self._band_top_hz()
        try:
            if f_hi <= 0.0:
                raise ValueError(
                    "set 'Band top (f_hi)' in the requirements column — an "
                    "LPDA is a BAND design (Frequency = f_lo)")
            kwargs = {"wire_d_m": self._wire_d_m(),
                      "r0_ohm": self.lpda_r0.value()}
            if self.lpda_by.currentData() == "gain":
                design = lp.design_lpda(f_lo, f_hi,
                                        gain_dbi=self.lpda_gain.value(),
                                        **kwargs)
            else:
                design = lp.design_lpda(f_lo, f_hi,
                                        tau=self.lpda_tau.value(),
                                        sigma=self.lpda_sigma.value(),
                                        **kwargs)
        except Exception as exc:  # noqa: BLE001 — surfaced in the read-out
            self._lpda_design = None
            self.verify_btn.setEnabled(False)
            self.accept_btn.setEnabled(False)
            self.perf_view.setPlainText("Invalid LPDA inputs: {0}".format(exc))
            self.fig_sketch.clear()
            self.canvas_sketch.draw_idle()
            return
        self._lpda_design = design
        self.verify_btn.setEnabled(self._nec2_found)
        self.accept_btn.setEnabled(True)
        rec = band_picker.recommend_method(
            design["f_mid_hz"], max_dim_m=design["boom_length_m"],
            wire_structure=True)
        self.banner.setText(
            "Band {0} ({1} - {2}) — recommended: {3}".format(
                rec["band"], band_picker._fmt_freq(f_lo),
                band_picker._fmt_freq(f_hi), rec["primary_label"]))
        self._refresh_predicted_lpda()
        self._draw_schematic_lpda()

    def _refresh_predicted_lpda(self):
        from emstudio.antenna import band_picker

        d = self._lpda_design
        if not d:
            return
        L = ["PREDICTED PERFORMANCE — LPDA (Carrel synthesis)"]
        L.append("=" * 52)
        L.append("band             : {0} - {1}  (B = {2:.3g})".format(
            band_picker._fmt_freq(d["f_lo_hz"]),
            band_picker._fmt_freq(d["f_hi_hz"]), d["bandwidth"]))
        L.append("tau / sigma      : {0:.3f} / {1:.3f}{2}".format(
            d["tau"], d["sigma"],
            "  (optimum-sigma line)" if d["on_optimum_sigma"] else
            "  (sigma_opt would be {0:.3f})".format(d["sigma_opt"])))
        L.append("apex half-angle  : {0:.1f} deg  (cot alpha {1:.3f})".format(
            d["alpha_deg"], d["cot_alpha"]))
        L.append("B_ar / B_s       : {0:.3f} / {1:.3f}".format(
            d["b_ar"], d["b_s"]))
        L.append("elements         : {0}  (N_exact {1:.2f})".format(
            d["n_elements"], d["n_exact"]))
        L.append("boom length      : {0:.4g} m  (Carrel closed form "
                 "{1:.4g} m)".format(d["boom_length_m"], d["boom_carrel_m"]))
        L.append("gain (corrected) : {0:.2f} dBi = {1:.2f} dBd  "
                 "(Carrel-original label {2:.2f} dBi)".format(
                     d["gain_dbi"], d["gain_dbd"],
                     d["gain_dbi_carrel_original"]))
        L.append("feeder Z0        : {0:.1f} ohm (crossed) for R0 ~ {1:.0f} "
                 "ohm  (Za {2:.0f}, sigma' {3:.3f})".format(
                     d["feeder_z0_ohm"], d["r0_ohm"], d["za_ohm"],
                     d["sigma_prime"]))
        L.append("")
        L.append("element            pos (m)    length (m)")
        for e in d["elements"]:
            tag = "  <- fed" if e["kind"] == "fed" else ""
            L.append("  {0:15s} {1:8.4f} {2:11.4f}{3}".format(
                e["name"], e["position_m"], e["length_m"], tag))
        for w in d.get("warnings", []):
            L.append("")
            L.append("warning: {0}".format(w))
        L.append("")
        L.append("source: {0}".format(d.get("source_note", "")))
        self.perf_view.setPlainText("\n".join(L))

    def _draw_schematic_lpda(self):
        d = self._lpda_design
        if not d:
            return
        self.fig_sketch.clear()
        ax = self.fig_sketch.add_subplot(111)
        ax.set_aspect("equal")
        ax.axis("off")
        xs = [e["position_m"] for e in d["elements"]]
        maxlen = max(e["length_m"] for e in d["elements"])
        ax.plot([min(xs), max(xs)], [0, 0], "-", color="#666", lw=2)  # boom
        fed = None
        for e in d["elements"]:
            x = e["position_m"]
            half = e["length_m"] / 2.0
            color = "#d33" if e["kind"] == "fed" else "#c87533"
            ax.plot([x, x], [-half, half], "-", color=color, lw=2.0)
            if e["kind"] == "fed":
                fed = e
        if fed is not None:
            ax.plot([fed["position_m"]], [0], "o", color="#d33", ms=5)
            ax.text(fed["position_m"], maxlen * 0.60, "FEED", fontsize=7,
                    ha="center", color="#d33")
        span = max(max(xs) - min(xs), 1e-9)
        ax.annotate("", xy=(max(xs), -maxlen * 0.62),
                    xytext=(min(xs), -maxlen * 0.62),
                    arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
        ax.text((min(xs) + max(xs)) / 2.0, -maxlen * 0.74,
                "boom {0:.3g} m".format(d["boom_length_m"]), ha="center",
                color="#2b8cff", fontsize=8)
        ax.annotate("", xy=(max(xs) + 0.16 * span, 0.0),
                    xytext=(max(xs) + 0.02 * span, 0.0),
                    arrowprops=dict(arrowstyle="->", color="#3a3"))
        ax.text(max(xs) + 0.09 * span, maxlen * 0.10, "beam", fontsize=7,
                ha="center", color="#3a3")
        ax.set_xlim(min(xs) - 0.08 * span, max(xs) + 0.22 * span)
        ax.set_ylim(-maxlen * 0.9, maxlen * 0.75)
        ax.set_title(
            "LPDA tau {0:.3f} / sigma {1:.3f} — {2} elements, {3:.1f} dBi "
            "(fires off the short end ->)".format(
                d["tau"], d["sigma"], d["n_elements"], d["gain_dbi"]),
            fontsize=8)
        self.canvas_sketch.draw_idle()

    # ================= patch family =================
    def _recalc_patch(self):
        from emstudio.antenna import band_picker
        from emstudio.antenna import patch_tl as pt

        f = self._freq_hz()
        try:
            design = pt.design_patch(f, self.patch_er.value(),
                                     self.patch_h.value() / 1000.0,
                                     target_z_ohm=self.patch_z.value())
        except Exception as exc:  # noqa: BLE001 — surfaced in the read-out
            self._patch_design = None
            self.verify_btn.setEnabled(False)
            self.accept_btn.setEnabled(False)
            self.perf_view.setPlainText("Invalid patch inputs: {0}".format(exc))
            self.fig_sketch.clear()
            self.canvas_sketch.draw_idle()
            return
        self._patch_design = design
        self.verify_btn.setEnabled(self._openems_found)
        self.accept_btn.setEnabled(True)
        rec = band_picker.recommend_method(
            f, max_dim_m=max(design["width_m"], design["length_m"]),
            wire_structure=False)
        self.banner.setText("Band {0} ({1}) — recommended: {2}".format(
            rec["band"], band_picker._fmt_freq(f), rec["primary_label"]))
        self._refresh_predicted_patch()
        self._draw_schematic_patch()

    def _refresh_predicted_patch(self):
        from emstudio.antenna import band_picker

        d = self._patch_design
        if not d:
            return
        L = ["PREDICTED PERFORMANCE — Microstrip patch"]
        L.append("=" * 42)
        L.append("frequency        : {0}".format(
            band_picker._fmt_freq(d["f0_hz"])))
        L.append("substrate        : er {0:g}, h {1:.3g} mm".format(
            d["er"], d["h_m"] * 1e3))
        L.append("eff. permittivity: {0:.4f}".format(d["er_eff"]))
        L.append("radiating width W: {0:.3f} mm".format(d["width_m"] * 1e3))
        L.append("resonant length L: {0:.3f} mm  (+2*dL {1:.3f} mm fringing)"
                 .format(d["length_m"] * 1e3, d["delta_l_m"] * 1e3))
        L.append("edge resistance  : {0:.0f} ohm".format(
            d["edge_resistance_ohm"]))
        L.append("{0:.0f}-ohm feed offset: {1:.2f} mm from centre  (probe; "
                 "ESTIMATE)".format(d["target_z_ohm"], d["feed_offset_m"] * 1e3))
        L.append("gain (estimate)  : {0:.2f} dBi = {1:.2f} dBd".format(
            d["gain_dbi"], d["gain_dbd"]))
        for w in d.get("warnings", []):
            L.append("")
            L.append("warning: {0}".format(w))
        L.append("")
        L.append("source: {0}".format(d.get("source_note", "")))
        self.perf_view.setPlainText("\n".join(L))

    def _draw_schematic_patch(self):
        d = self._patch_design
        if not d:
            return
        from matplotlib.patches import Rectangle as _Rect

        self.fig_sketch.clear()
        ax = self.fig_sketch.add_subplot(111)
        ax.set_aspect("equal")
        ax.axis("off")
        Lm = d["length_m"] * 1e3   # resonant (x)
        Wm = d["width_m"] * 1e3    # radiating (y)
        margin = 15.0
        ax.add_patch(_Rect((-Lm / 2 - margin, -Wm / 2 - margin),
                           Lm + 2 * margin, Wm + 2 * margin,
                           facecolor="#2b3b2b", edgecolor="#4a5", lw=1))
        ax.add_patch(_Rect((-Lm / 2, -Wm / 2), Lm, Wm,
                           facecolor="#c87533", edgecolor="#e0a060", lw=1.5))
        off = d["feed_offset_m"] * 1e3
        ax.plot([-off], [0], "o", color="#d33", ms=7)
        ax.annotate("feed", (-off, 0), (-off, Wm * 0.35),
                    color="#d33", fontsize=8, ha="center",
                    arrowprops=dict(arrowstyle="->", color="#d33"))
        ax.annotate("", xy=(Lm / 2, -Wm / 2 - margin * 0.6),
                    xytext=(-Lm / 2, -Wm / 2 - margin * 0.6),
                    arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
        ax.text(0, -Wm / 2 - margin * 0.9, "L = {0:.2f} mm".format(Lm),
                ha="center", color="#2b8cff", fontsize=8)
        ax.annotate("", xy=(Lm / 2 + margin * 0.6, Wm / 2),
                    xytext=(Lm / 2 + margin * 0.6, -Wm / 2),
                    arrowprops=dict(arrowstyle="<->", color="#2b8cff"))
        ax.text(Lm / 2 + margin * 0.9, 0, "W = {0:.2f} mm".format(Wm),
                rotation=90, va="center", color="#2b8cff", fontsize=8)
        lim = max(Lm, Wm) / 2 + margin * 1.4
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_title("Microstrip patch on er {0:g} / {1:.3g} mm — {2:.1f} dBi "
                     "est. (feed along L)".format(
                         d["er"], d["h_m"] * 1e3, d["gain_dbi"]), fontsize=8)
        self.canvas_sketch.draw_idle()

    # ================= verify (production NEC2 writer, off-thread) ========
    def _close_verify_doc(self):
        if not self._verify_docname:
            return
        try:
            import FreeCAD

            if self._verify_docname in FreeCAD.listDocuments():
                FreeCAD.closeDocument(self._verify_docname)
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass
        self._verify_docname = None

    def _build_verify_analysis(self, doc):
        """Build the current design in ``doc`` (called on the GUI thread)."""
        from emstudio.objects import query
        from emstudio.templates import dipole as dipole_tpl
        from emstudio.templates import monopole as monopole_tpl

        fam = self.family.currentData()
        if fam == "yagi":
            from emstudio.templates import yagi as yagi_tpl

            d = self._yagi_design
            if d is None:
                raise ValueError("no valid Yagi design — adjust the inputs")
            ana = yagi_tpl.makeYagi(doc, f0_hz=self._freq_hz(),
                                    boom_lambda=d["boom_lambda"],
                                    wire_radius_mm=self.wire_dia.value() / 2.0)
            return ana, query.get_solvers(ana)[0]
        if fam == "patch":
            from emstudio.templates import patch as patch_tpl

            if self._patch_design is None:
                raise ValueError("no valid patch design — adjust the inputs")
            ana = patch_tpl.makePatchDesign(
                doc, f0_hz=self._freq_hz(), er=self.patch_er.value(),
                h_mm=self.patch_h.value(), target_z_ohm=self.patch_z.value())
            return ana, query.get_solvers(ana)[0]
        if fam == "lpda":
            ana = self._make_lpda_analysis(doc)
            return ana, query.get_solvers(ana)[0]

        kind = self._wire_kind()
        f0 = self._freq_hz()
        Lm = self.length.value()
        radius_mm = self.wire_dia.value() / 2.0
        if kind == "dipole":
            ana = dipole_tpl.makeDipole(doc, f0_hz=f0,
                                        wire_radius_mm=radius_mm, length_m=Lm)
        elif kind == "folded":
            ana = _make_folded_analysis(doc, f0, Lm, radius_mm)
        else:
            ana = monopole_tpl.makeMonopole(
                doc, f0_hz=f0, wire_radius_m=radius_mm * 1e-3, height_m=Lm)
            # designer-class sweep (the template default is a narrow VLF probe)
            ana.FrequencyStart = "{0} MHz".format(f0 / 1e6 * 2.0 / 3.0)
            ana.FrequencyStop = "{0} MHz".format(f0 / 1e6 * 4.0 / 3.0)
            ana.FrequencyPoints = 201
            doc.recompute()
        solver = query.get_solvers(ana)[0]
        return ana, solver

    def _make_lpda_analysis(self, doc):
        """Build the current LPDA design in ``doc`` (Verify and Generate)."""
        from emstudio.templates import lpda as lpda_tpl

        if self._lpda_design is None:
            raise ValueError("no valid LPDA design — adjust the inputs")
        kwargs = {"f_lo_hz": self._freq_hz(), "f_hi_hz": self._band_top_hz(),
                  "wire_radius_mm": self.wire_dia.value() / 2.0,
                  "r0_ohm": self.lpda_r0.value()}
        if self.lpda_by.currentData() == "gain":
            kwargs["gain_dbi"] = self.lpda_gain.value()
        else:
            kwargs["tau"] = self.lpda_tau.value()
            kwargs["sigma"] = self.lpda_sigma.value()
        return lpda_tpl.makeLPDA(doc, **kwargs)

    def _verify(self):
        import FreeCAD

        # Build the verify geometry in a scratch document, then restore the
        # previously-active document so Accept & Generate (and any other
        # command) never lands in the transient verify doc.
        prev_active = FreeCAD.ActiveDocument
        self._close_verify_doc()
        doc = FreeCAD.newDocument("ElementVerify")
        self._verify_docname = doc.Name
        try:
            ana, solver = self._build_verify_analysis(doc)
        except Exception as exc:  # noqa: BLE001 — geometry build must not crash
            self._close_verify_doc()
            if prev_active is not None:
                try:
                    FreeCAD.setActiveDocument(prev_active.Name)
                except Exception:  # noqa: BLE001
                    pass
            QtWidgets.QMessageBox.critical(
                self, "EMStudio", "Cannot build the verify model:\n{0}".format(exc))
            return
        if prev_active is not None:
            try:
                FreeCAD.setActiveDocument(prev_active.Name)
            except Exception:  # noqa: BLE001 — restore is best-effort
                pass
        fam = self.family.currentData()
        f0 = self._freq_hz()
        if fam == "yagi":
            design = dict(self._yagi_design or {})
            label = "NEC2, Yagi {0:g}λ".format(design.get("boom_lambda", 0.0))
        elif fam == "patch":
            design = dict(self._patch_design or {})
            label = "openEMS, patch"
        elif fam == "lpda":
            design = dict(self._lpda_design or {})
            label = "NEC2, LPDA {0}el".format(design.get("n_elements", 0))
        else:
            design = dict(self._design or {})
            design["length_used_m"] = self.length.value()
            design["edited"] = self._length_edited
            label = "NEC2, " + self.wtype.currentText()
        design["f0_hz"] = f0
        kind = self._wire_kind()

        def run_fn(_a, _s, cb):
            if fam == "patch":
                from emstudio.solvers import openems

                return openems.run(ana, solver, line_callback=cb)
            from emstudio.solvers import nec2

            result = nec2.run(ana, solver, line_callback=cb)
            if fam == "lpda":
                # pin the far field at the geometric band centre (the
                # min-S11 default wanders in the ripple; mid-band is the
                # honest design-gain read-out)
                import os

                from emstudio.setup import solvers as solver_setup
                from emstudio.solvers.base import SolverJob, make_workdir
                from emstudio.solvers.nec2 import parser as nec_parser
                from emstudio.solvers.nec2 import writer as nec_writer

                f_mid = design.get("f_mid_hz", f0)
                info = solver_setup.find_backend("nec2")
                wd = make_workdir("emstudio_lpda_ff_")
                ffd = os.path.join(wd, "ff.nec")
                ffo = os.path.join(wd, "ff.out")
                nec_writer.write_nec_farfield(ana, solver, ffd, f_mid)
                SolverJob([info.path, "-i", ffd, "-o", ffo],
                          cwd=wd, line_callback=cb).run_blocking(timeout=300)
                result.farfield = nec_parser.parse_radiation_patterns(
                    ffo, f_mid)
                return result
            if fam == "yagi":
                # pin the far-field at the DESIGN frequency (the runner's
                # default min-S11 pattern frequency wanders when the driven
                # element is not matched — the de-risk lesson).
                import os

                from emstudio.setup import solvers as solver_setup
                from emstudio.solvers.base import SolverJob, make_workdir
                from emstudio.solvers.nec2 import parser as nec_parser
                from emstudio.solvers.nec2 import writer as nec_writer

                info = solver_setup.find_backend("nec2")
                wd = make_workdir("emstudio_yagi_ff_")
                ffd = os.path.join(wd, "ff.nec")
                ffo = os.path.join(wd, "ff.out")
                nec_writer.write_nec_farfield(ana, solver, ffd, f0)
                SolverJob([info.path, "-i", ffd, "-o", ffo],
                          cwd=wd, line_callback=cb).run_blocking(timeout=300)
                result.farfield = nec_parser.parse_radiation_patterns(ffo, f0)
            return result

        def on_success(result):
            self._close_verify_doc()
            if fam == "yagi":
                msg = self._verify_message_yagi(result, design)
            elif fam == "patch":
                msg = self._verify_message_patch(result, design)
            elif fam == "lpda":
                msg = self._verify_message_lpda(result, design)
            else:
                msg = self._verify_message(result, design, kind)
            self.verify_view.setPlainText(msg)
            self.tabs.setCurrentWidget(self.verify_view)

        from emstudio.ui import run_gui

        # cleanup on EVERY exit path: success closes the doc above; error/cancel
        # close it here (run_generic_gui otherwise only shows a message box, and
        # a canceled daemon worker would otherwise strand the doc).
        run_gui.run_generic_gui(
            "Element verify ({0})".format(label),
            run_fn, on_success, parent=self,
            on_error=lambda _exc: self._close_verify_doc(),
            on_cancel=self._close_verify_doc)

    def _verify_message(self, result, design, kind):
        """Pure predicted-vs-achieved formatter (headlessly gated in
        gui_smoke, like cable_dialog._fullwave_message)."""
        freq = np.asarray(result.freq, dtype=float)
        zin = np.asarray(result.zin, dtype=complex)
        f0 = design["f0_hz"]
        L = ["NEC2 verify — {0} (production writer)".format(kind),
             ""]
        L.append("design f0        : {0:.4f} MHz".format(f0 / 1e6))
        L.append("length solved    : {0:.6g} m{1}".format(
            design.get("length_used_m", design.get("length_m", 0.0)),
            "  [user-edited]" if design.get("edited") else ""))

        i0 = int(np.argmin(np.abs(freq - f0)))
        z_f0 = zin[i0]
        L.append("Z at f0          : {0:.1f} {1} j{2:.1f} ohm".format(
            z_f0.real, "+" if z_f0.imag >= 0 else "-", abs(z_f0.imag)))

        window = VERIFY_R_WINDOWS.get(kind)
        if window:
            best = None
            for f_hz, z in zip(freq, zin):
                if window[0] <= z.real <= window[1] and (
                        best is None or abs(z.imag) < abs(best[1].imag)):
                    best = (f_hz, z)
            if best is not None:
                f_res, z_res = best
                L.append("")
                L.append("achieved f_res   : {0:.4f} MHz  ({1:+.2%} vs f0)".format(
                    f_res / 1e6, f_res / f0 - 1.0))
                L.append("achieved R       : {0:.1f} ohm (X {1:+.1f})".format(
                    z_res.real, z_res.imag))
                if design.get("feed_r_ohm") is not None:
                    L.append("predicted R      : {0:.1f} ohm  (delta {1:+.1f}%)".format(
                        design["feed_r_ohm"],
                        (z_res.real / design["feed_r_ohm"] - 1.0) * 100.0))
            else:
                L.append("")
                L.append("no resonance found inside the {0:.0f}-{1:.0f} ohm "
                         "window — check the sweep span / geometry".format(
                             window[0], window[1]))
        else:
            L.append("")
            L.append("this type is NOT resonant by design (see the predicted "
                     "notes) — Z at f0 is the honest read-out; matching is "
                     "section-7 territory")

        ff = getattr(result, "farfield", None)
        if ff is not None:
            try:
                g_peak, theta, _phi = ff.peak()
                L.append("")
                L.append("achieved peak    : {0:.2f} dBi = {1:+.2f} dBd "
                         "(theta {2:.0f} deg)".format(
                             g_peak, g_peak - 2.15, theta))
                if design.get("gain_dbi") is not None:
                    L.append("predicted        : {0:.2f} dBi  (free-space "
                             "dipole class{1})".format(
                                 design["gain_dbi"],
                                 "; monopole values assume the PEC image"
                                 if kind not in ("dipole", "folded") else ""))
            except Exception:  # noqa: BLE001 — far field is best-effort
                pass

        meta = getattr(result, "meta", {}) or {}
        if meta:
            L.append("")
            L.append("solve time: {0:.1f} s".format(meta.get("duration_s", -1.0)))
            L.append("workdir: {0}".format(meta.get("workdir", "?")))
        return "\n".join(L)

    def _verify_message_yagi(self, result, design):
        """Pure predicted-vs-achieved formatter for the Yagi family (far-field
        pinned at the design frequency). Headlessly gated in gui_smoke."""
        f0 = design["f0_hz"]
        freq = np.asarray(result.freq, dtype=float)
        zin = np.asarray(result.zin, dtype=complex)
        L = ["NEC2 verify — Yagi-Uda {0:g} lambda (production writer)".format(
            design.get("boom_lambda", 0.0)), ""]
        L.append("design f0        : {0:.4f} MHz".format(f0 / 1e6))
        z0 = zin[int(np.argmin(np.abs(freq - f0)))]
        L.append("driven Z at f0   : {0:.1f} {1} j{2:.1f} ohm".format(
            z0.real, "+" if z0.imag >= 0 else "-", abs(z0.imag)))
        ff = getattr(result, "farfield", None)
        if ff is not None:
            try:
                g_peak, _th, _ph = ff.peak()
                th, g0 = ff.cut(0.0)
                _, g180 = ff.cut(180.0)
                j90 = int(np.argmin(np.abs(th - 90.0)))
                fb = g0[j90] - g180[j90]
                L.append("")
                L.append("achieved peak    : {0:.2f} dBi = {1:.2f} dBd".format(
                    g_peak, g_peak - 2.15))
                L.append("predicted (NBS)  : {0:.2f} dBi = {1:.2f} dBd  "
                         "(delta {2:+.2f} dB)".format(
                             design["gain_dbi"], design["gain_dbd"],
                             (g_peak - 2.15) - design["gain_dbd"]))
                L.append("front/back       : {0:.1f} dB (at the design "
                         "frequency)".format(fb))
            except Exception:  # noqa: BLE001 — far field is best-effort
                pass
        L.append("")
        L.append("driven not matched here — tune it or use a folded driven + "
                 "balun (matching is section-7).")
        meta = getattr(result, "meta", {}) or {}
        if meta:
            L.append("solve time: {0:.1f} s".format(meta.get("duration_s", -1.0)))
        return "\n".join(L)

    def _verify_message_patch(self, result, design):
        """Pure predicted-vs-achieved formatter for the patch family (openEMS
        FDTD; resonance = the S11 dip). Headlessly gated in gui_smoke."""
        f0 = design["f0_hz"]
        L = ["openEMS verify — microstrip patch (FDTD)", ""]
        L.append("design f0        : {0:.4f} GHz".format(f0 / 1e9))
        try:
            f_res, s11_db = result.min_s11()
            L.append("achieved f_res   : {0:.4f} GHz  ({1:+.2%} vs design; "
                     "TL model ±5%)".format(f_res / 1e9, f_res / f0 - 1.0))
            L.append("match at f_res   : {0:.1f} dB |S11|".format(s11_db))
        except Exception:  # noqa: BLE001
            L.append("(no S11 minimum found in the sweep)")
        ff = getattr(result, "farfield", None)
        if ff is not None:
            try:
                g_peak, theta, _phi = ff.peak()
                L.append("")
                L.append("achieved gain    : {0:.2f} dBi (theta {1:.0f} deg, "
                         "boresight)".format(g_peak, theta))
                L.append("predicted (est.) : {0:.2f} dBi  (delta {1:+.2f} "
                         "dB)".format(design["gain_dbi"],
                                      g_peak - design["gain_dbi"]))
            except Exception:  # noqa: BLE001
                pass
        L.append("")
        L.append("the FDTD resonance is the achieved value; adjust L to centre "
                 "it, and use openEMS to refine the feed offset.")
        meta = getattr(result, "meta", {}) or {}
        if meta:
            L.append("solve time: {0:.1f} s  workdir: {1}".format(
                meta.get("duration_s", -1.0), meta.get("workdir", "?")))
        return "\n".join(L)

    def _verify_message_lpda(self, result, design):
        """Pure predicted-vs-achieved formatter for the LPDA family (band
        VSWR statistics vs R0 + far field pinned at the geometric band
        centre). Headlessly gated in gui_smoke."""
        r0 = design.get("r0_ohm", 65.0)
        f_mid = design.get("f_mid_hz", design.get("f0_hz", 0.0))
        freq = np.asarray(result.freq, dtype=float)
        zin = np.asarray(result.zin, dtype=complex)
        gam = np.abs((zin - r0) / (zin + r0))
        gam = np.minimum(gam, 0.999999)
        vswr = (1.0 + gam) / (1.0 - gam)
        L = ["NEC2 verify — LPDA {0} elements (production writer, crossed "
             "TL feeder)".format(design.get("n_elements", 0)), ""]
        L.append("band             : {0:.2f} - {1:.2f} MHz".format(
            design.get("f_lo_hz", 0.0) / 1e6, design.get("f_hi_hz", 0.0) / 1e6))
        L.append("mean R achieved  : {0:.1f} ohm  (target R0 {1:.0f})".format(
            float(np.mean(zin.real)), r0))
        L.append("VSWR vs R0       : median {0:.2f} / worst {1:.2f} over "
                 "{2} points".format(float(np.median(vswr)),
                                     float(np.max(vswr)), len(vswr)))
        z_mid = zin[int(np.argmin(np.abs(freq - f_mid)))]
        L.append("Z at band centre : {0:.1f} {1} j{2:.1f} ohm  "
                 "({3:.1f} MHz)".format(
                     z_mid.real, "+" if z_mid.imag >= 0 else "-",
                     abs(z_mid.imag), f_mid / 1e6))
        ff = getattr(result, "farfield", None)
        if ff is not None:
            try:
                g_peak, _th, _ph = ff.peak()
                th, g0 = ff.cut(0.0)
                _, g180 = ff.cut(180.0)
                j90 = int(np.argmin(np.abs(th - 90.0)))
                fb = g0[j90] - g180[j90]
                L.append("")
                L.append("achieved peak    : {0:.2f} dBi = {1:.2f} dBd (at "
                         "band centre)".format(g_peak, g_peak - 2.15))
                L.append("predicted        : {0:.2f} dBi (corrected contour; "
                         "delta {1:+.2f} dB)".format(
                             design.get("gain_dbi", 0.0),
                             g_peak - design.get("gain_dbi", 0.0)))
                L.append("front/back       : {0:.1f} dB (at band "
                         "centre)".format(fb))
            except Exception:  # noqa: BLE001 — far field is best-effort
                pass
        L.append("")
        L.append("expect the gain/F-B to droop at exactly f_lo (truncated "
                 "active region) and log-periodic ripple across the band; "
                 "matching networks are section-7.")
        meta = getattr(result, "meta", {}) or {}
        if meta:
            L.append("solve time: {0:.1f} s".format(meta.get("duration_s", -1.0)))
        return "\n".join(L)

    # ================= PDF report =================
    def _current_report_design(self):
        """(family, enriched design dict or None) for the report — pure, so
        gui_smoke gates it headlessly."""
        fam = self.family.currentData()
        if fam == "yagi":
            d = self._yagi_design
        elif fam == "patch":
            d = self._patch_design
        elif fam == "lpda":
            d = self._lpda_design
        elif fam == "wire":
            d = self._design
        else:
            return fam, None
        if d is None:
            return fam, None
        d = dict(d)
        d.setdefault("f0_hz", self._freq_hz())
        if fam == "wire":
            d["kind"] = self._wire_kind()
            d["length_m"] = self.length.value()
            d["length_ft"] = self.length.value() / 0.3048
            if self._length_edited:
                # the K/feed-Z/gain rows describe the SYNTHESIZED design —
                # say so in the deliverable (mirrors the on-screen caveat)
                d["edited"] = True
                d["warnings"] = [
                    "length EDITED by the user — the K-factor, feed-Z and "
                    "gain rows describe the SYNTHESIZED design; Verify with "
                    "NEC2 for the edited geometry",
                ] + list(d.get("warnings", []) or [])
        return fam, d

    def _save_report(self):
        import os

        fam, design = self._current_report_design()
        if design is None:
            QtWidgets.QMessageBox.information(
                self, "EMStudio", "No valid design to report — adjust the "
                "inputs first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDF report",
            os.path.expanduser("~/element_{0}_report.pdf".format(fam)),
            "PDF (*.pdf)",
        )
        if not path:
            return
        try:
            from emstudio.report import element_report

            title = "{0} — Element Design".format(
                self.family.currentText().split(" (")[0])
            element_report(design, path, family=fam, title=title)
            QtWidgets.QMessageBox.information(
                self, "EMStudio", "Saved report:\n" + path)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            QtWidgets.QMessageBox.critical(
                self, "EMStudio", "Report failed: {0}".format(exc))

    # ================= accept & generate =================
    def _generate(self, doc):
        """Create the accepted design as a runnable analysis in ``doc``
        (pure creation — no message boxes; gui_smoke calls this)."""
        from emstudio.templates import dipole as dipole_tpl
        from emstudio.templates import monopole as monopole_tpl

        fam = self.family.currentData()
        if fam == "yagi":
            from emstudio.templates import yagi as yagi_tpl

            d = self._yagi_design
            if d is None:
                raise ValueError("no valid Yagi design — adjust the inputs")
            return yagi_tpl.makeYagi(doc, f0_hz=self._freq_hz(),
                                     boom_lambda=d["boom_lambda"],
                                     wire_radius_mm=self.wire_dia.value() / 2.0)
        if fam == "patch":
            from emstudio.templates import patch as patch_tpl

            if self._patch_design is None:
                raise ValueError("no valid patch design — adjust the inputs")
            return patch_tpl.makePatchDesign(
                doc, f0_hz=self._freq_hz(), er=self.patch_er.value(),
                h_mm=self.patch_h.value(), target_z_ohm=self.patch_z.value())
        if fam == "lpda":
            return self._make_lpda_analysis(doc)

        kind = self._wire_kind()
        f0 = self._freq_hz()
        Lm = self.length.value()
        radius_mm = self.wire_dia.value() / 2.0
        if kind == "dipole":
            return dipole_tpl.makeDipole(doc, f0_hz=f0,
                                         wire_radius_mm=radius_mm, length_m=Lm)
        if kind == "folded":
            return _make_folded_analysis(doc, f0, Lm, radius_mm)
        ana = monopole_tpl.makeMonopole(
            doc, f0_hz=f0, wire_radius_m=radius_mm * 1e-3, height_m=Lm)
        ana.FrequencyStart = "{0} MHz".format(f0 / 1e6 * 2.0 / 3.0)
        ana.FrequencyStop = "{0} MHz".format(f0 / 1e6 * 4.0 / 3.0)
        ana.FrequencyPoints = 201
        doc.recompute()
        return ana

    def _accept_generate(self):
        import FreeCAD

        doc = FreeCAD.ActiveDocument
        # never target the transient verify document (it gets closed on the next
        # verify / dialog close, which would destroy the accepted analysis)
        fresh = doc is None or doc.Name == self._verify_docname
        if fresh:
            doc = FreeCAD.newDocument()
        try:
            ana = self._generate(doc)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the dialog
            if fresh:  # don't leave an empty scratch document behind
                try:
                    FreeCAD.closeDocument(doc.Name)
                except Exception:  # noqa: BLE001
                    pass
            QtWidgets.QMessageBox.critical(
                self, "EMStudio", "Generate failed:\n{0}".format(exc))
            return
        QtWidgets.QMessageBox.information(
            self, "EMStudio — Element Designer",
            "Created '{0}' at {1:.4g} MHz.\n\nThe analysis has geometry, "
            "material, feed port and a {2} solver — use Run Solver when "
            "ready.".format(ana.Label, self._freq_hz() / 1e6,
                            getattr(self, "_solver_name", "NEC2")))

    # ================= small-antenna routing =================
    def _open_small(self):
        from emstudio.ui.small_antenna_dialog import SmallAntennaDialog

        dlg = SmallAntennaDialog(parent=self)
        dlg.exec()

    # ================= lifecycle =================
    def closeEvent(self, event):  # noqa: N802 — Qt naming
        self._close_verify_doc()
        super().closeEvent(event)
