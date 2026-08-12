# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cable Designer dialog (ROADMAP §2) — Litz | Coax | Single Wire.

The generalized Litz / Wire Designer shell: one top-level Construction selector
drives three left-column pages over the shared right-hand tabs (Cross-Section ·
RF/AC · Spec/BOM).

* **Litz / stranded** — the full industry Type 1-9 designer (New England Wire
  taxonomy): per-level lay length + S/Z direction, strand sizing in AWG/mm/mil,
  live cross-section, AC-resistance curves (with optional winding-field external
  proximity), build-house spec/BOM export, FreeCAD profile export, PDF report,
  FastHenry current sharing.
* **Coax** — the §2 analytic TEM engine (``emstudio.wire.coax``): Z0 / VF /
  C' / L' / TE11 cutoff / conductor+dielectric attenuation, RG-58/RG-142
  primary-datasheet presets, dielectric presets, and a "Full-wave verify" hook
  into the shipped Palace coax lumped-port backend (``run_coax``).
* **Single wire** — a solid conductor + insulation, reusing the litz analytics
  with ``ops=[]`` (exact Kelvin skin effect, Rdc, ampacity, spec, PDF).
* **Twisted pair** — the §2-B analytic engine (``emstudio.wire.twisted_pair``):
  differential/odd-mode Z0 (exact two-wire acosh line + the Lefferson twist/
  insulation effective permittivity, θ in DEGREES), VF, C'/L', attenuation,
  UTP/STP (RDRE shielded form), Cat5e/Cat6 primary-datasheet presets.
* **Bundle** — the §2-C geometric composer (``emstudio.wire.bundle``): any
  member mix packed largest-first at exact tangency candidates + minimal-
  enclosing-circle axis; core/finished OD, fill factor, jacket, spec.
  Member-to-member RLGC/crosstalk is a planned FastHenry slice.
"""

from __future__ import annotations

import math
import os

from PySide import QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Circle as MplCircle  # noqa: E402
from matplotlib.patches import Rectangle as MplRect  # noqa: E402


class CableDesignerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio — Cable Designer (Litz · Coax · Single Wire)")
        self.resize(1120, 700)

        root = QtWidgets.QHBoxLayout(self)

        # ================= left column: construction pages =================
        left = QtWidgets.QVBoxLayout()

        sel_form = QtWidgets.QFormLayout()
        self.construction = QtWidgets.QComboBox()
        self.construction.addItem("Litz / stranded (Types 1-9)", "litz")
        self.construction.addItem("Coax", "coax")
        self.construction.addItem("Single wire", "wire")
        self.construction.addItem("Twisted pair", "tp")
        self.construction.addItem("Bundle (multi-design)", "bundle")
        sel_form.addRow("<b>Construction</b>", self.construction)
        left.addLayout(sel_form)

        self.pages = QtWidgets.QStackedWidget()
        self.pages.addWidget(self._build_litz_page())
        self.pages.addWidget(self._build_coax_page())
        self.pages.addWidget(self._build_wire_page())
        self.pages.addWidget(self._build_tp_page())
        self.pages.addWidget(self._build_bundle_page())
        left.addWidget(self.pages)

        # operating context — shared by the litz + single-wire analytics
        # (the coax page carries its own report frequency)
        self.ctx_box = QtWidgets.QGroupBox("Operating context")
        ctx = QtWidgets.QFormLayout(self.ctx_box)
        self.fmin = QtWidgets.QDoubleSpinBox()
        self.fmin.setRange(0.001, 1e6)
        self.fmin.setValue(1.0)
        self.fmin.setSuffix(" kHz")
        ctx.addRow("f min", self.fmin)
        self.fmax = QtWidgets.QDoubleSpinBox()
        self.fmax.setRange(0.01, 1e6)
        self.fmax.setValue(1000.0)
        self.fmax.setSuffix(" kHz")
        ctx.addRow("f max", self.fmax)
        self.h_ext = QtWidgets.QDoubleSpinBox()
        self.h_ext.setRange(0.0, 1e6)
        self.h_ext.setValue(0.0)
        self.h_ext.setToolTip(
            "Winding field per ampere He/I in 1/m (external proximity).\n"
            "Long solenoid interior: ~ turns / length. 0 = isolated bundle."
        )
        ctx.addRow("Winding He/I (1/m)", self.h_ext)
        self.i_rms = QtWidgets.QDoubleSpinBox()
        self.i_rms.setRange(0.0, 1e5)
        self.i_rms.setValue(1.0)
        self.i_rms.setSuffix(" A rms")
        ctx.addRow("Current", self.i_rms)
        left.addWidget(self.ctx_box)

        self.update_btn = QtWidgets.QPushButton("Update")
        self.update_btn.clicked.connect(self._recalc)
        left.addWidget(self.update_btn)

        self.summary = QtWidgets.QLabel("")
        self.summary.setWordWrap(True)
        left.addWidget(self.summary)

        export_row = QtWidgets.QHBoxLayout()
        self.detail_combo = QtWidgets.QComboBox()
        self.detail_combo.addItem("Profile: auto", "auto")
        self.detail_combo.addItem("Profile: full strands", "full")
        self.detail_combo.addItem("Profile: bundle outlines", "bundles")
        self.detail_combo.addItem("Profile: envelope (OD+jacket)", "envelope")
        self.detail_combo.setToolTip(
            "Simplification of the exported CAD profile. Detailed profiles cause\n"
            "computational/visual problems in downstream sweeps and drawings:\n"
            "• full — every strand (small cables only)\n"
            "• bundle outlines — one circle per sub-cable + cores (most sweeps)\n"
            "• envelope — conductor OD + jacket only (long coil sweeps)\n"
            "• auto — full up to 5000 strands, else bundle outlines"
        )
        self.export_cad_btn = QtWidgets.QPushButton("Export → FreeCAD")
        self.export_cad_btn.setToolTip(
            "Creates the selected profile at the XY origin — use as the profile "
            "for Part Sweep/Loft along your coil path."
        )
        self.export_cad_btn.clicked.connect(self._export_cad)
        self.export_spec_btn = QtWidgets.QPushButton("Save spec / BOM…")
        self.export_spec_btn.clicked.connect(self._export_spec)
        export_row.addWidget(self.detail_combo)
        export_row.addWidget(self.export_cad_btn)
        export_row.addWidget(self.export_spec_btn)
        left.addLayout(export_row)

        report_row = QtWidgets.QHBoxLayout()
        self.report_btn = QtWidgets.QPushButton("PDF Report…")
        self.report_btn.setToolTip("Build-house-ready document: summary, "
                                   "cross-section drawing, AC curves, and schedule/BOM.")
        self.report_btn.clicked.connect(self._pdf_report)
        self.sharing_btn = QtWidgets.QPushButton("Current Sharing…")
        self.sharing_btn.setToolTip("Per-bundle current sharing of the final cabling "
                                    "level (twist quality). Runs FastHenry — minutes.")
        self.sharing_btn.clicked.connect(self._current_sharing)
        report_row.addWidget(self.report_btn)
        report_row.addWidget(self.sharing_btn)
        left.addLayout(report_row)
        left.addStretch(1)

        root.addLayout(left, 0)

        # ================= right column: shared tabs =================
        self.tabs = QtWidgets.QTabWidget()
        self.fig_xs = Figure(figsize=(5, 5), tight_layout=True)
        self.canvas_xs = FigureCanvas(self.fig_xs)
        self.tabs.addTab(self.canvas_xs, "Cross-Section")
        self.fig_ac = Figure(figsize=(5, 5), tight_layout=True)
        self.canvas_ac = FigureCanvas(self.fig_ac)
        self.tabs.addTab(self.canvas_ac, "AC Resistance")
        self.spec_view = QtWidgets.QPlainTextEdit()
        self.spec_view.setReadOnly(True)
        self.tabs.addTab(self.spec_view, "Spec / BOM")
        self.tabs.addTab(self._build_thermal_tab(), "Thermal")
        root.addWidget(self.tabs, 1)

        # default construction: Type 2, 20x5 of AWG 38
        self._set_ops([(20, 0.0, "", "none"), (5, 0.0, "", "none")])
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self.construction.currentIndexChanged.connect(self._construction_changed)
        self._recalc()

    # ================= page builders =================
    def _build_litz_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        form_box = QtWidgets.QGroupBox("Construction")
        form = QtWidgets.QFormLayout(form_box)
        self.type_combo = QtWidgets.QComboBox()
        from emstudio.wire.litz import LITZ_TYPE_DESCRIPTIONS

        for t in range(1, 10):
            self.type_combo.addItem(
                "Type {0} — {1}".format(t, LITZ_TYPE_DESCRIPTIONS[t]), t
            )
        form.addRow("Litz type", self.type_combo)

        size_row = QtWidgets.QHBoxLayout()
        self.strand_size = QtWidgets.QDoubleSpinBox()
        self.strand_size.setDecimals(4)
        self.strand_size.setRange(0.0001, 60.0)
        self.strand_size.setValue(38.0)
        self.size_unit = QtWidgets.QComboBox()
        self.size_unit.addItems(["AWG", "mm", "mil"])
        size_row.addWidget(self.strand_size, 1)
        size_row.addWidget(self.size_unit)
        form.addRow("Strand size", size_row)
        lay.addWidget(form_box)

        ops_box = QtWidgets.QGroupBox("Bunching / cabling operations (innermost first)")
        ops_lay = QtWidgets.QVBoxLayout(ops_box)
        hint = QtWidgets.QLabel(
            "Each row is ONE operation, innermost first — use as many or as few rows\n"
            "as YOUR construction has (the type presets are only examples).\n"
            "E.g. a Type 6 of 20 Type-4s, each 13 Type-2s of 70 strands = 3 rows:\n"
            "  70 → 13 (Core=auto, makes each Type 4) → 20 (Core=auto, the big core)"
        )
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        ops_lay.addWidget(hint)
        self.ops_table = QtWidgets.QTableWidget(0, 5)
        self.ops_table.setHorizontalHeaderLabels(
            ["Members", "Lay (mm, 0=auto)", "Dir", "Core Ø", "Member wrap"]
        )
        self.ops_table.horizontalHeader().setStretchLastSection(True)
        ops_lay.addWidget(self.ops_table)
        btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("+ level")
        del_btn = QtWidgets.QPushButton("− level")
        add_btn.clicked.connect(self._add_level)
        del_btn.clicked.connect(self._del_level)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addStretch(1)
        ops_lay.addLayout(btns)
        lay.addWidget(ops_box)

        jacket_box = QtWidgets.QGroupBox("Overall jacket")
        jform = QtWidgets.QFormLayout(jacket_box)
        self.jacket_combo = QtWidgets.QComboBox()
        self.jacket_combo.setEditable(True)
        self.jacket_combo.addItems(["none", "PVC", "polyethylene", "silicone", "PTFE"])
        jform.addRow("Material", self.jacket_combo)
        self.jacket_thk = QtWidgets.QDoubleSpinBox()
        self.jacket_thk.setRange(0.0, 12.7)
        self.jacket_thk.setDecimals(3)
        self.jacket_thk.setSuffix(" mm")
        self.jacket_thk.setSpecialValueText("auto (1/8\")")
        self.jacket_thk.setToolTip(
            "Jacket wall thickness. Industry standard for heavy Type-6 cable: "
            "1/8\" (3.175 mm) to 1/4\" (6.35 mm). 'auto' = 1/8\"."
        )
        jform.addRow("Wall thickness", self.jacket_thk)
        lay.addWidget(jacket_box)
        return page

    def _build_coax_page(self):
        from emstudio.wire import coax

        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        geo_box = QtWidgets.QGroupBox("Coax geometry (analytic TEM)")
        form = QtWidgets.QFormLayout(geo_box)
        self.coax_preset = QtWidgets.QComboBox()
        self.coax_preset.addItem("Custom geometry")
        for name in coax.PRESETS:
            self.coax_preset.addItem(name)
        self.coax_preset.setToolTip(
            "Primary-datasheet geometry presets (the same anchors as the "
            "validation gate). Stranded centres use the effective electrical "
            "diameter — see each preset's note in the Spec tab."
        )
        form.addRow("Preset", self.coax_preset)
        self.coax_a = QtWidgets.QDoubleSpinBox()
        self.coax_a.setDecimals(4)
        self.coax_a.setRange(0.001, 60.0)
        self.coax_a.setValue(0.836)
        self.coax_a.setSuffix(" mm")
        self.coax_a.setToolTip(
            "Inner-conductor diameter 2a. For a STRANDED centre use the effective\n"
            "electrical diameter (~0.94x the physical envelope), which is what\n"
            "reproduces datasheet Z0 and capacitance."
        )
        form.addRow("Inner conductor Ø (2a)", self.coax_a)
        self.coax_b = QtWidgets.QDoubleSpinBox()
        self.coax_b.setDecimals(4)
        self.coax_b.setRange(0.002, 200.0)
        self.coax_b.setValue(2.921)
        self.coax_b.setSuffix(" mm")
        self.coax_b.setToolTip("Dielectric diameter 2b (= shield inner face).")
        form.addRow("Dielectric Ø (2b)", self.coax_b)
        self.coax_diel = QtWidgets.QComboBox()
        for name in coax.DIELECTRICS:
            self.coax_diel.addItem(name)
        self.coax_diel.addItem("Custom (edit εr / tanδ)")
        form.addRow("Dielectric", self.coax_diel)
        self.coax_eps = QtWidgets.QDoubleSpinBox()
        self.coax_eps.setDecimals(4)
        self.coax_eps.setRange(1.0, 12.0)
        self.coax_eps.setSingleStep(0.01)
        self.coax_eps.setValue(2.25)
        form.addRow("εr", self.coax_eps)
        self.coax_tan = QtWidgets.QDoubleSpinBox()
        self.coax_tan.setDecimals(6)
        self.coax_tan.setRange(0.0, 0.05)
        self.coax_tan.setSingleStep(1e-4)
        self.coax_tan.setValue(3e-4)
        form.addRow("tan δ", self.coax_tan)
        self.coax_freq = QtWidgets.QDoubleSpinBox()
        self.coax_freq.setDecimals(3)
        self.coax_freq.setRange(0.001, 100000.0)
        self.coax_freq.setValue(100.0)
        self.coax_freq.setSuffix(" MHz")
        form.addRow("Report frequency", self.coax_freq)
        solve_row = QtWidgets.QHBoxLayout()
        self.coax_z0_target = QtWidgets.QDoubleSpinBox()
        self.coax_z0_target.setDecimals(2)
        self.coax_z0_target.setRange(1.0, 500.0)
        self.coax_z0_target.setValue(50.0)
        self.coax_z0_target.setSuffix(" Ω")
        self.coax_solve_btn = QtWidgets.QPushButton("Solve 2b")
        self.coax_solve_btn.setToolTip(
            "Sets the dielectric Ø for the target Z0 at the current inner Ø\n"
            "and εr (exact inversion: b = a·exp(2π·Z0·√εr/η0))."
        )
        self.coax_solve_btn.clicked.connect(self._solve_coax_b)
        solve_row.addWidget(self.coax_z0_target, 1)
        solve_row.addWidget(self.coax_solve_btn)
        form.addRow("Target Z0", solve_row)
        lay.addWidget(geo_box)

        fw_box = QtWidgets.QGroupBox("Full-wave verify (Palace lumped-port)")
        fw = QtWidgets.QFormLayout(fw_box)
        fw_box.setToolTip(
            "Meshes an (a, b, L) coax line and runs the shipped Palace coax\n"
            "backend (the validated lumped-port S-parameter path): a uniform\n"
            "matched line must show tiny |S11|, and the S21 phase slope gives\n"
            "the full-wave velocity factor to compare with 1/sqrt(εr)."
        )
        self.fw_f1 = QtWidgets.QDoubleSpinBox()
        self.fw_f1.setRange(0.05, 60.0)
        self.fw_f1.setValue(1.0)
        self.fw_f1.setSuffix(" GHz")
        fw.addRow("f start", self.fw_f1)
        self.fw_f2 = QtWidgets.QDoubleSpinBox()
        self.fw_f2.setRange(0.1, 60.0)
        self.fw_f2.setValue(3.0)
        self.fw_f2.setSuffix(" GHz")
        fw.addRow("f stop", self.fw_f2)
        self.fw_pts = QtWidgets.QSpinBox()
        self.fw_pts.setRange(2, 41)
        self.fw_pts.setValue(3)
        fw.addRow("Points", self.fw_pts)
        self.fw_len = QtWidgets.QDoubleSpinBox()
        self.fw_len.setRange(1.0, 500.0)
        self.fw_len.setValue(20.0)
        self.fw_len.setSuffix(" mm")
        self.fw_len.setToolTip(
            "Line length. Keep under λ/2 at f start so the S21 phase is "
            "unambiguous for the VF extraction."
        )
        fw.addRow("Line length", self.fw_len)
        self.fw_btn = QtWidgets.QPushButton("Run full-wave verify (Palace)…")
        self.fw_btn.clicked.connect(self._fullwave_verify)
        fw.addRow(self.fw_btn)
        lay.addWidget(fw_box)
        lay.addStretch(1)

        self.coax_preset.currentIndexChanged.connect(self._apply_coax_preset)
        self.coax_diel.currentIndexChanged.connect(self._apply_coax_dielectric)
        return page

    def _build_wire_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        box = QtWidgets.QGroupBox("Single wire")
        form = QtWidgets.QFormLayout(box)
        size_row = QtWidgets.QHBoxLayout()
        self.wire_size = QtWidgets.QDoubleSpinBox()
        self.wire_size.setDecimals(4)
        self.wire_size.setRange(0.0001, 60.0)
        self.wire_size.setValue(10.0)
        self.wire_unit = QtWidgets.QComboBox()
        self.wire_unit.addItems(["AWG", "mm", "mil"])
        size_row.addWidget(self.wire_size, 1)
        size_row.addWidget(self.wire_unit)
        form.addRow("Conductor size", size_row)
        self.wire_ins = QtWidgets.QComboBox()
        self.wire_ins.addItems(["bare", "PVC", "polyethylene", "PTFE", "enamel"])
        form.addRow("Insulation", self.wire_ins)
        self.wire_wall = QtWidgets.QDoubleSpinBox()
        self.wire_wall.setDecimals(3)
        self.wire_wall.setRange(0.001, 6.35)
        self.wire_wall.setValue(0.30)
        self.wire_wall.setSuffix(" mm")
        self.wire_wall.setEnabled(False)  # default insulation = bare
        form.addRow("Insulation wall", self.wire_wall)
        hint = QtWidgets.QLabel(
            "Solid conductor: exact Kelvin skin effect (Rac/Rdc), Rdc, ampacity,\n"
            "spec + PDF — the litz analytics with zero bunching operations."
        )
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        form.addRow(hint)
        lay.addWidget(box)
        lay.addStretch(1)

        self.wire_ins.currentIndexChanged.connect(
            lambda _i: self.wire_wall.setEnabled(self.wire_ins.currentText() != "bare"))
        return page

    def _build_tp_page(self):
        from emstudio.wire import twisted_pair as tp

        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        box = QtWidgets.QGroupBox("Twisted pair (differential TEM analytics)")
        form = QtWidgets.QFormLayout(box)
        self.tp_preset = QtWidgets.QComboBox()
        self.tp_preset.addItem("Custom geometry")
        for name in tp.PRESETS:
            self.tp_preset.addItem(name)
        self.tp_preset.setToolTip(
            "Primary-datasheet UTP presets (the same anchors as the validation "
            "gate). Their εeff comes from the datasheet NVP — see the preset "
            "note in the Spec tab."
        )
        form.addRow("Preset", self.tp_preset)
        self.tp_d = QtWidgets.QDoubleSpinBox()
        self.tp_d.setDecimals(4)
        self.tp_d.setRange(0.01, 10.0)
        self.tp_d.setValue(0.511)
        self.tp_d.setSuffix(" mm")
        form.addRow("Conductor Ø (bare)", self.tp_d)
        self.tp_s = QtWidgets.QDoubleSpinBox()
        self.tp_s.setDecimals(4)
        self.tp_s.setRange(0.02, 20.0)
        self.tp_s.setValue(0.993)
        self.tp_s.setSuffix(" mm")
        self.tp_s.setToolTip(
            "Centre-to-centre spacing s. For a tight twist this equals one\n"
            "insulated-conductor OD (the insulation surfaces touch)."
        )
        form.addRow("Insulated OD (= spacing s)", self.tp_s)
        self.tp_ins = QtWidgets.QComboBox()
        self.tp_ins.addItems(["hard film (enamel / PE / PVC)", "soft (PTFE etc.)"])
        self.tp_ins.setToolTip(
            "Lefferson filling-factor branch: q = 0.25 + k·θ² (θ in degrees),\n"
            "k = 0.0004 for hard film insulation, 0.001 for soft insulation."
        )
        form.addRow("Insulation class", self.tp_ins)
        self.tp_eps = QtWidgets.QDoubleSpinBox()
        self.tp_eps.setDecimals(3)
        self.tp_eps.setRange(1.0, 12.0)
        self.tp_eps.setSingleStep(0.05)
        self.tp_eps.setValue(2.3)
        form.addRow("εr (insulation)", self.tp_eps)
        self.tp_tan = QtWidgets.QDoubleSpinBox()
        self.tp_tan.setDecimals(6)
        self.tp_tan.setRange(0.0, 0.05)
        self.tp_tan.setSingleStep(1e-4)
        self.tp_tan.setValue(2e-4)
        form.addRow("tan δ", self.tp_tan)
        self.tp_lay = QtWidgets.QDoubleSpinBox()
        self.tp_lay.setDecimals(2)
        self.tp_lay.setRange(1.0, 100.0)
        self.tp_lay.setValue(15.0)
        self.tp_lay.setSuffix(" mm/turn")
        self.tp_lay.setToolTip(
            "Twist lay length (one full turn). Cat5e/Cat6 pairs run ~6-26 mm.\n"
            "Optimum pitch angle 20-45°; wire breaks near ~50°."
        )
        form.addRow("Twist lay", self.tp_lay)
        self.tp_nvp_on = QtWidgets.QCheckBox("εeff from datasheet NVP")
        self.tp_nvp_on.setChecked(True)
        self.tp_nvp_on.setToolTip(
            "For real cables the honest εeff is 1/NVP² from the datasheet\n"
            "velocity. Unchecked = the Lefferson twist/insulation model."
        )
        self.tp_nvp = QtWidgets.QDoubleSpinBox()
        self.tp_nvp.setDecimals(3)
        self.tp_nvp.setRange(0.40, 0.95)
        self.tp_nvp.setValue(0.70)
        nvp_row = QtWidgets.QHBoxLayout()
        nvp_row.addWidget(self.tp_nvp_on)
        nvp_row.addWidget(self.tp_nvp)
        form.addRow(nvp_row)
        self.tp_shield_on = QtWidgets.QCheckBox("Shielded (STP)")
        self.tp_shield = QtWidgets.QDoubleSpinBox()
        self.tp_shield.setDecimals(3)
        self.tp_shield.setRange(0.1, 100.0)
        self.tp_shield.setValue(3.0)
        self.tp_shield.setSuffix(" mm shield Ø")
        self.tp_shield.setEnabled(False)
        self.tp_shield.setToolTip(
            "Shield inner diameter D (thin-wire model, best for d/s ≤ 0.4;\n"
            "+2 % at 0.4, +5 % at 0.6 vs the exact solution — flagged)."
        )
        sh_row = QtWidgets.QHBoxLayout()
        sh_row.addWidget(self.tp_shield_on)
        sh_row.addWidget(self.tp_shield)
        form.addRow(sh_row)
        self.tp_freq = QtWidgets.QDoubleSpinBox()
        self.tp_freq.setDecimals(3)
        self.tp_freq.setRange(0.001, 10000.0)
        self.tp_freq.setValue(100.0)
        self.tp_freq.setSuffix(" MHz")
        form.addRow("Report frequency", self.tp_freq)
        tsolve_row = QtWidgets.QHBoxLayout()
        self.tp_z0_target = QtWidgets.QDoubleSpinBox()
        self.tp_z0_target.setDecimals(2)
        self.tp_z0_target.setRange(1.0, 500.0)
        self.tp_z0_target.setValue(100.0)
        self.tp_z0_target.setSuffix(" Ω")
        self.tp_solve_btn = QtWidgets.QPushButton("Solve lay")
        self.tp_solve_btn.setToolTip(
            "Sets the twist lay for the target differential Z0 at the current\n"
            "geometry/insulation (Lefferson twist model — switches εeff off\n"
            "NVP mode; more twist only LOWERS Z0, unreachable targets are\n"
            "reported)."
        )
        self.tp_solve_btn.clicked.connect(self._solve_tp_lay)
        tsolve_row.addWidget(self.tp_z0_target, 1)
        tsolve_row.addWidget(self.tp_solve_btn)
        form.addRow("Target Z0", tsolve_row)
        lay.addWidget(box)
        lay.addStretch(1)

        self.tp_preset.currentIndexChanged.connect(self._apply_tp_preset)
        self.tp_nvp_on.toggled.connect(self.tp_nvp.setEnabled)
        self.tp_shield_on.toggled.connect(self.tp_shield.setEnabled)
        return page

    def _build_bundle_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        box = QtWidgets.QGroupBox("Bundle members (any construction mix)")
        blay = QtWidgets.QVBoxLayout(box)
        hint = QtWidgets.QLabel(
            "Each row is one member design placed qty times. The OD is the\n"
            "member's bundle ENVELOPE: wire/litz = finished OD; coax = OD over\n"
            "shield+jacket; twisted pair = 2×spacing (its rotating circle)."
        )
        hint.setStyleSheet("color: gray; font-size: 8pt;")
        blay.addWidget(hint)
        self.bundle_table = QtWidgets.QTableWidget(0, 5)
        self.bundle_table.setHorizontalHeaderLabels(
            ["Label", "Envelope OD (mm)", "Qty", "Kind", "Cond. Ø (mm)"])
        self.bundle_table.horizontalHeader().setStretchLastSection(True)
        blay.addWidget(self.bundle_table)
        btns = QtWidgets.QHBoxLayout()
        add_b = QtWidgets.QPushButton("+ member")
        del_b = QtWidgets.QPushButton("− member")
        self.bundle_grab_btn = QtWidgets.QPushButton("Add last construction")
        self.bundle_grab_btn.setToolTip(
            "Adds the construction last computed on another page (its\n"
            "envelope OD + label) as a member row."
        )
        add_b.clicked.connect(lambda: self._bundle_add_row())
        del_b.clicked.connect(self._bundle_del_row)
        self.bundle_grab_btn.clicked.connect(self._bundle_grab_last)
        btns.addWidget(add_b)
        btns.addWidget(del_b)
        btns.addWidget(self.bundle_grab_btn)
        btns.addStretch(1)
        blay.addLayout(btns)
        lay.addWidget(box)

        jbox = QtWidgets.QGroupBox("Overall jacket")
        jform = QtWidgets.QFormLayout(jbox)
        self.bundle_jacket = QtWidgets.QComboBox()
        self.bundle_jacket.setEditable(True)
        self.bundle_jacket.addItems(["none", "PVC", "polyethylene", "PTFE"])
        jform.addRow("Material", self.bundle_jacket)
        self.bundle_wall = QtWidgets.QDoubleSpinBox()
        self.bundle_wall.setDecimals(3)
        self.bundle_wall.setRange(0.05, 12.7)
        self.bundle_wall.setValue(1.0)
        self.bundle_wall.setSuffix(" mm")
        jform.addRow("Wall thickness", self.bundle_wall)
        lay.addWidget(jbox)

        xbox = QtWidgets.QGroupBox("Crosstalk estimate (weak coupling)")
        xbox.setToolTip(
            "Paul's inductive-capacitive weak-coupling model between a\n"
            "generator and a receptor member sharing a reference (return)\n"
            "member. Analytic wide-separation L/C (valid when every\n"
            "separation/conductor-radius >= 4 — flagged otherwise); the\n"
            "FastHenry option extracts the L/R loop matrix at any spacing."
        )
        xform = QtWidgets.QFormLayout(xbox)
        idx_row = QtWidgets.QHBoxLayout()
        self.xt_gen = QtWidgets.QSpinBox()
        self.xt_rec = QtWidgets.QSpinBox()
        self.xt_ref = QtWidgets.QSpinBox()
        for w, v in ((self.xt_gen, 1), (self.xt_rec, 2), (self.xt_ref, 3)):
            w.setRange(1, 999)
            w.setValue(v)
            w.setToolTip(
                "Index into the PACKED member list: table rows expand by "
                "Qty\nin order (a row with Qty 3 occupies three consecutive "
                "numbers,\nmatching the spec tab's position table)."
            )
        idx_row.addWidget(QtWidgets.QLabel("gen #"))
        idx_row.addWidget(self.xt_gen)
        idx_row.addWidget(QtWidgets.QLabel("rec #"))
        idx_row.addWidget(self.xt_rec)
        idx_row.addWidget(QtWidgets.QLabel("ref #"))
        idx_row.addWidget(self.xt_ref)
        xform.addRow("Members (packed #)", idx_row)
        self.xt_diff = QtWidgets.QCheckBox(
            "Differential pair-to-pair (mixed-mode)")
        self.xt_diff.setToolTip(
            "Reduce four picked conductors + the reference to differential\n"
            "modes (Vd = V1−V2, Id = (I1−I2)/2; congruence transform) and\n"
            "report k_diff, the ASTM D4566 pair-to-pair capacitance\n"
            "unbalance (CUPP = −4·Cdd_AB) and differential NE/FE crosstalk\n"
            "with the RADC-TR-76-101 Vol V twist model. Terminations are\n"
            "DIFFERENTIAL ohms (50 Ω per wire to reference = 100 Ω)."
        )
        self.xt_diff.toggled.connect(self._xt_mode_changed)
        xform.addRow(self.xt_diff)
        pair_row = QtWidgets.QHBoxLayout()
        self.xt_a1 = QtWidgets.QSpinBox()
        self.xt_a2 = QtWidgets.QSpinBox()
        self.xt_b1 = QtWidgets.QSpinBox()
        self.xt_b2 = QtWidgets.QSpinBox()
        for w, lab, v in ((self.xt_a1, "A1", 1), (self.xt_a2, "A2", 2),
                          (self.xt_b1, "B1", 4), (self.xt_b2, "B2", 5)):
            w.setRange(1, 999)
            w.setValue(v)
            w.setEnabled(False)
            w.setToolTip(
                "Index into the PACKED member list: table rows expand by "
                "Qty\nin order (a row with Qty 3 occupies three consecutive "
                "numbers)."
            )
            pair_row.addWidget(QtWidgets.QLabel(lab))
            pair_row.addWidget(w)
        xform.addRow("Diff pairs (packed #)", pair_row)
        twist_row = QtWidgets.QHBoxLayout()
        self.xt_twist = QtWidgets.QSpinBox()
        self.xt_twist.setRange(0, 100000)
        self.xt_twist.setValue(0)
        self.xt_twist.setSuffix(" half-twists")
        self.xt_twist.setSpecialValueText("untwisted")
        self.xt_twist.setToolTip(
            "Half-twist loop count N of the receptor pair over the run\n"
            "(N = 2 × length / lay). Quoted improvement is the conservative\n"
            "odd-N envelope 1/N — the ideal even-N null is parity luck."
        )
        self.xt_recmode = QtWidgets.QComboBox()
        self.xt_recmode.addItem("Balanced (differential)", "balanced")
        self.xt_recmode.addItem("Unbalanced (single ground)",
                                "unbalanced_single_ground")
        self.xt_recmode.addItem("Grounded both ends (loop)",
                                "unbalanced_ground_loop")
        self.xt_recmode.setToolTip(
            "Receptor termination topology. Unbalanced keeps the full\n"
            "capacitive floor regardless of twist (RADC eqs 4-8/4-10);\n"
            "balancing nulls it (eq 4-43); a both-ends ground loop defeats\n"
            "the twist entirely (~1 dB)."
        )
        self.xt_twist.setEnabled(False)
        self.xt_recmode.setEnabled(False)
        twist_row.addWidget(self.xt_twist)
        twist_row.addWidget(self.xt_recmode)
        xform.addRow("Receptor twist / topology", twist_row)
        r_row = QtWidgets.QHBoxLayout()
        self.xt_rs = QtWidgets.QDoubleSpinBox()
        self.xt_rl = QtWidgets.QDoubleSpinBox()
        self.xt_rne = QtWidgets.QDoubleSpinBox()
        self.xt_rfe = QtWidgets.QDoubleSpinBox()
        for w, lab in ((self.xt_rs, "RS"), (self.xt_rl, "RL"),
                       (self.xt_rne, "RNE"), (self.xt_rfe, "RFE")):
            w.setRange(0.1, 1e7)
            w.setValue(50.0)
            w.setDecimals(1)
            w.setToolTip(
                "Single-ended mode: per-wire terminations.\n"
                "Differential mode: DIFFERENTIAL resistances — 50 Ω per wire "
                "to\nreference at an end = 100 Ω differential."
            )
            r_row.addWidget(QtWidgets.QLabel(lab))
            r_row.addWidget(w)
        self.xt_r_label = QtWidgets.QLabel("Terminations (Ω)")
        xform.addRow(self.xt_r_label, r_row)
        self.xt_len = QtWidgets.QDoubleSpinBox()
        self.xt_len.setRange(0.01, 1000.0)
        self.xt_len.setValue(2.0)
        self.xt_len.setSuffix(" m")
        xform.addRow("Run length", self.xt_len)
        self.xt_freq = QtWidgets.QDoubleSpinBox()
        self.xt_freq.setDecimals(4)
        self.xt_freq.setRange(0.0001, 1000.0)
        self.xt_freq.setValue(1.0)
        self.xt_freq.setSuffix(" MHz")
        xform.addRow("Report frequency", self.xt_freq)
        self.xt_eps = QtWidgets.QDoubleSpinBox()
        self.xt_eps.setDecimals(2)
        self.xt_eps.setRange(1.0, 12.0)
        self.xt_eps.setValue(3.5)
        self.xt_eps.setToolTip(
            "Insulation relative permittivity for the capacitance solve. When "
            "the picked members are insulated (envelope OD > conductor Ø), the "
            "mutual capacitance is computed by the method-of-moments insulated "
            "solve (Paul's RIBBON.FOR method) instead of the bare identity — "
            "insulation raises C by ~50-66%. Bare members ignore this.")
        xform.addRow("Insulation εr", self.xt_eps)
        self.xt_fh = QtWidgets.QCheckBox(
            "FastHenry L/R (accurate at any spacing — runs the solver)")
        xform.addRow(self.xt_fh)
        self.xt_btn = QtWidgets.QPushButton("Estimate crosstalk")
        self.xt_btn.clicked.connect(self._bundle_coupling)
        xform.addRow(self.xt_btn)
        lay.addWidget(xbox)

        # --- convection: what bundling costs the ampacity ------------------
        # This lives on the BUNDLE page on purpose. Churchill-Chu assumes ONE
        # cable in unbounded still air, so the moment a user builds a bundle
        # here the thermal answer elsewhere in this dialog is optimistic — and
        # this is the page where they can be told, without hunting for a CFD
        # panel they have no reason to open.
        cbox = QtWidgets.QGroupBox("Convection (bundling and confinement)")
        cform = QtWidgets.QFormLayout(cbox)
        self.conv_clearance = QtWidgets.QDoubleSpinBox()
        self.conv_clearance.setRange(1.5, 50.0)
        self.conv_clearance.setValue(5.0)
        self.conv_clearance.setSingleStep(0.5)
        self.conv_clearance.setToolTip(
            "Enclosure size as a multiple of the bundle's own extent. NOT "
            "packaging: measured, shrinking a 0.40 m box to 0.20 m around one "
            "20 mm cable cost 3 % of the film coefficient.")
        cform.addRow("Enclosure / bundle extent", self.conv_clearance)
        self.conv_btn = QtWidgets.QPushButton(
            "Solve convection for this bundle…")
        self.conv_btn.setToolTip(
            "Solve natural convection for the members above and derive a "
            "bundle factor on Churchill-Chu. Measured for a trefoil of three "
            "20 mm cables: 0.80, i.e. the correlation over-predicts cooling "
            "by ~25 %. Runs a CFD solve — minutes, not seconds.")
        self.conv_btn.clicked.connect(self._bundle_convection)
        cform.addRow(self.conv_btn)
        lay.addWidget(cbox)
        lay.addStretch(1)

        # a representative default mix
        self._bundle_add_row("Coax member", 4.95, 1, "coax")
        self._bundle_add_row("Twisted pair", 1.99, 2, "twisted_pair")
        self._bundle_add_row("Hookup wire", 1.20, 4, "wire", 0.644)
        return page

    def _bundle_add_row(self, label="member", od_mm=2.0, qty=1, kind="generic",
                        cond_mm=0.0):
        r = self.bundle_table.rowCount()
        self.bundle_table.insertRow(r)
        lab = QtWidgets.QLineEdit(str(label))
        od = QtWidgets.QDoubleSpinBox()
        od.setDecimals(3)
        od.setRange(0.01, 100.0)
        od.setValue(float(od_mm))
        q = QtWidgets.QSpinBox()
        q.setRange(1, 500)
        q.setValue(int(qty))
        k = QtWidgets.QComboBox()
        k.addItems(["generic", "wire", "litz", "coax", "twisted_pair"])
        k.setCurrentText(kind)
        cd = QtWidgets.QDoubleSpinBox()
        cd.setDecimals(3)
        cd.setRange(0.0, 50.0)
        cd.setValue(float(cond_mm))
        cd.setSpecialValueText("n/a")
        cd.setToolTip(
            "Bare (or equivalent-solid) conductor Ø — needed by the crosstalk\n"
            "estimates. 'n/a' excludes the member from coupling analysis\n"
            "(shielded coax members are excluded by design — their return is\n"
            "their own shield). A twisted_pair-kind row is a packing envelope,\n"
            "not a coupling conductor: model a pair as TWO wire members and\n"
            "use the differential pair-to-pair mode."
        )
        self.bundle_table.setCellWidget(r, 0, lab)
        self.bundle_table.setCellWidget(r, 1, od)
        self.bundle_table.setCellWidget(r, 2, q)
        self.bundle_table.setCellWidget(r, 3, k)
        self.bundle_table.setCellWidget(r, 4, cd)

    def _bundle_del_row(self):
        r = self.bundle_table.rowCount()
        if r > 1:
            self.bundle_table.removeRow(r - 1)

    def _bundle_grab_last(self):
        env = getattr(self, "_last_envelope", None)
        if not env:
            QtWidgets.QMessageBox.information(
                self, "EMStudio",
                "Compute a construction on another page first — its envelope "
                "OD is then added here.")
            return
        label, od_m, kind, cond_d_m = env
        self._bundle_add_row(label, od_m * 1e3, 1, kind, cond_d_m * 1e3)
        self._recalc()

    # ================= construction switching =================
    def _construction_changed(self):
        kind = self.construction.currentData()
        self.pages.setCurrentIndex(self.construction.currentIndex())
        self.ctx_box.setVisible(kind in ("litz", "wire"))
        litzish = kind in ("litz", "wire")
        self.detail_combo.setEnabled(litzish)
        self.export_cad_btn.setEnabled(litzish)
        self.report_btn.setEnabled(litzish)
        self.sharing_btn.setEnabled(kind == "litz")
        self.tabs.setTabText(
            1, "AC Resistance" if litzish
            else ("RF / Coupling" if kind == "bundle" else "RF Attenuation"))
        self._recalc()

    def _type_changed(self):
        """Type-aware helper: seed ops layout with cores + wraps + jacket marked."""
        t = self.type_combo.currentData()
        seeds = {
            1: [(20, 0.0, "", "none", "none")],
            2: [(20, 0.0, "", "none", "none"), (5, 0.0, "", "none", "none")],
            3: [(20, 0.0, "", "none", "none"), (5, 0.0, "", "none", "none"),
                (4, 0.0, "", "none", "polyester tape")],
            4: [(20, 0.0, "", "none", "none"), (5, 0.0, "", "none", "none"),
                (4, 0.0, "", "auto", "none")],
            5: [(20, 0.0, "", "none", "none"), (5, 0.0, "", "none", "none"),
                (4, 0.0, "", "auto", "polyester tape")],
            6: [(20, 0.0, "", "none", "none"), (5, 0.0, "", "none", "none"),
                (4, 0.0, "", "auto", "polyester tape"),
                (6, 0.0, "", "auto", "polyester tape")],
            7: [(40, 0.0, "", "none", "none")],
            8: [(40, 0.0, "", "none", "none")],
            9: [(20, 0.0, "", "none", "none"), (5, 0.0, "", "none", "none")],
        }
        self._set_ops(seeds.get(t, [(20, 0.0, "", "none", "none")]))
        # jacket defaults: Type 6 ships PVC 1/8" per industry practice
        if t == 6:
            self.jacket_combo.setCurrentText("PVC")
            self.jacket_thk.setValue(0.0)  # auto = 1/8"
        else:
            self.jacket_combo.setCurrentText("none")
            self.jacket_thk.setValue(0.0)
        self._recalc()

    # ---------------- ops table helpers ----------------
    def _set_ops(self, rows):
        self.ops_table.setRowCount(0)
        for row in rows:
            self._add_level(*row)

    def _add_level(self, count=4, lay_mm=0.0, direction="", core="none", wrap="none"):
        r = self.ops_table.rowCount()
        self.ops_table.insertRow(r)
        cnt = QtWidgets.QSpinBox()
        cnt.setRange(2, 2000)
        cnt.setValue(int(count) if count else 4)
        lay = QtWidgets.QDoubleSpinBox()
        lay.setRange(0.0, 500.0)
        lay.setDecimals(2)
        lay.setValue(float(lay_mm))
        lay.setSpecialValueText("auto")
        dcombo = QtWidgets.QComboBox()
        dcombo.addItems(["auto", "S", "Z"])
        if direction in ("S", "Z"):
            dcombo.setCurrentText(direction)
        core_combo = QtWidgets.QComboBox()
        core_combo.setEditable(True)
        core_combo.addItems(["none", "auto", "0.5 mm", "1.0 mm"])
        core_combo.setToolTip(
            "Fiber core at this operation: members are packed around its "
            "circumference.\n'auto' = snug single-ring core sized to the member "
            "count.\nType 4/5: last level. Type 6: last TWO levels (each Type-4's "
            "core + the larger final core). Enter a value in mm for an exact core."
        )
        core_combo.setCurrentText(core)
        wrap_combo = QtWidgets.QComboBox()
        wrap_combo.setEditable(True)
        wrap_combo.addItems(
            ["none", "polyester tape", "PTFE tape", "kapton tape", "nylon serve"]
        )
        wrap_combo.setToolTip(
            "Insulation wrapped on each MEMBER before this operation cables them\n"
            "(e.g. tape on the Type-2s inside a Type 4/6). Default thickness:\n"
            "tape 0.05 mm (~2 mil), serve 0.08 mm. Append a thickness in mm to\n"
            "override, e.g. 'polyester tape 0.1'."
        )
        wrap_combo.setCurrentText(wrap)
        self.ops_table.setCellWidget(r, 0, cnt)
        self.ops_table.setCellWidget(r, 1, lay)
        self.ops_table.setCellWidget(r, 2, dcombo)
        self.ops_table.setCellWidget(r, 3, core_combo)
        self.ops_table.setCellWidget(r, 4, wrap_combo)

    def _del_level(self):
        r = self.ops_table.rowCount()
        if r > 1:
            self.ops_table.removeRow(r - 1)

    # ---------------- models ----------------
    def _construction(self):
        from emstudio.wire import litz, units

        d_m = units.to_meters(self.strand_size.value(), self.size_unit.currentText())
        ops = []
        for r in range(self.ops_table.rowCount()):
            count = self.ops_table.cellWidget(r, 0).value()
            lay_mm = self.ops_table.cellWidget(r, 1).value()
            direction = self.ops_table.cellWidget(r, 2).currentText()
            core_text = self.ops_table.cellWidget(r, 3).currentText().strip().lower()
            if core_text in ("", "none", "0", "—"):
                core_m = 0.0
            elif core_text == "auto":
                core_m = litz.AUTO_CORE
            else:
                core_m = float(core_text.replace("mm", "").strip()) * 1e-3

            wrap_text = self.ops_table.cellWidget(r, 4).currentText().strip()
            wrap_name, wrap_m = "", 0.0
            if wrap_text.lower() not in ("", "none", "—"):
                # optional trailing thickness in mm, e.g. 'polyester tape 0.1'
                parts = wrap_text.rsplit(" ", 1)
                try:
                    wrap_m = float(parts[-1].replace("mm", "")) * 1e-3
                    wrap_name = parts[0]
                except (ValueError, IndexError):
                    wrap_name, wrap_m = wrap_text, litz.AUTO_WRAP

            ops.append(
                litz.BunchOp(
                    count=count,
                    lay_m=lay_mm * 1e-3,
                    direction="" if direction == "auto" else direction,
                    core_m=core_m,
                    member_wrap=wrap_name,
                    member_wrap_m=wrap_m,
                )
            )

        jacket_text = self.jacket_combo.currentText().strip()
        jacket = "" if jacket_text.lower() in ("", "none") else jacket_text
        jthk = self.jacket_thk.value()
        kw = {}
        if jacket:
            kw["jacket"] = jacket
            kw["jacket_m"] = litz.AUTO_WRAP if jthk <= 0.0 else jthk * 1e-3
        return litz.make_type(self.type_combo.currentData(), d_m, ops, **kw)

    def _wire_construction(self):
        from emstudio.wire import litz, units

        d_m = units.to_meters(self.wire_size.value(), self.wire_unit.currentText())
        kw = {}
        ins = self.wire_ins.currentText()
        if ins != "bare":
            kw["jacket"] = ins
            kw["jacket_m"] = self.wire_wall.value() * 1e-3
        return litz.LitzConstruction(
            strand_diameter_m=d_m, ops=[],
            name="Solid wire {0}".format(units.format_diameter(d_m)), **kw)

    # ---------------- actions ----------------
    def _recalc(self):
        from emstudio.wire import units

        kind = self.construction.currentData()
        if kind == "coax":
            self._recalc_coax()
            return
        if kind == "tp":
            self._recalc_tp()
            return
        if kind == "bundle":
            self._recalc_bundle()
            return
        try:
            con = self._wire_construction() if kind == "wire" else self._construction()
        except Exception as exc:
            self.summary.setText("<b>Invalid construction:</b> {0}".format(exc))
            return
        self._con = con
        # conductor Ø for coupling: solid wire = the strand; litz = the
        # equivalent solid (same copper area — a documented approximation)
        d_eq = 2.0 * math.sqrt(con.copper_area_m2() / math.pi)
        self._last_envelope = (con.name, con.finished_od_m(),
                               "litz" if kind == "litz" else "wire", d_eq)

        f2 = max(self.fmax.value(), self.fmin.value() * 2) * 1e3
        f1 = self.fmin.value() * 1e3
        h_ext = self.h_ext.value()
        i_rms = self.i_rms.value()

        fac_f2 = con.ac_factor(f2, h_ext)
        self.summary.setText(
            "<b>{0}</b><br>strand: {1}<br>Rdc: {2:.3f} mΩ/m &nbsp; OD ≈ {3:.3f} mm"
            " (finished {4:.2f} mm)<br>"
            "equiv. solid: AWG {5:.1f} &nbsp; copper: {6:.2f} g/m<br>"
            "Rac/Rdc @ f max: {7:.3f} &nbsp; loss @ {8:g} A: {9:.3f} W/m<br>"
            "<b>ampacity est. @ f max: {10:.1f} A</b> "
            "<small>(30 K rise, still air — see manual)</small>".format(
                con.name,
                units.format_diameter(con.strand_diameter_m),
                con.rdc_per_meter() * 1e3,
                con.bundle_diameter_m() * 1e3,
                con.finished_od_m() * 1e3,
                con.equivalent_awg(),
                con.copper_weight_kg_per_m() * 1e3,
                fac_f2,
                i_rms,
                con.loss_w_per_m(f2, i_rms, h_ext),
                con.ampacity(f2, h_ext_per_amp=h_ext),
            )
        )
        self._draw_cross_section(con)
        self._draw_ac(con, f1, f2, h_ext)
        self.spec_view.setPlainText(con.spec_markdown())

    def _draw_cross_section(self, con):
        """Bulk-rendered cross-section (EllipseCollection): fast at 100k+ strands."""
        from matplotlib.collections import EllipseCollection

        from emstudio.wire import cross_section

        self.fig_xs.clear()
        ax = self.fig_xs.add_subplot(111)
        ax.set_aspect("equal")
        mm = 1e3
        data = cross_section.layout_arrays(con)
        max_r = data["jacket_r"] or data["od_r"]

        # background layers first
        if data["jacket_r"] > 0:
            ax.add_patch(MplCircle((0, 0), data["jacket_r"] * mm, facecolor="#4a4a55",
                                   edgecolor="#222222", lw=1.4))
            ax.add_patch(MplCircle((0, 0), data["od_r"] * mm, facecolor="#f4f0e8",
                                   edgecolor="#333333", lw=1.0))
        else:
            ax.add_patch(MplCircle((0, 0), data["od_r"] * mm, fill=False,
                                   edgecolor="#333333", lw=1.4))

        def _collection(centers, radius, **kw):
            n = len(centers)
            if n == 0:
                return
            d = 2.0 * radius * mm
            ax.add_collection(EllipseCollection(
                widths=[d] * n, heights=[d] * n, angles=0, units="xy",
                offsets=centers * mm, transOffset=ax.transData, **kw))

        for centers, r, _lvl in data["wraps"]:
            _collection(centers, r, facecolors="none", edgecolors="#7a9c48",
                        linestyles=":", linewidths=1.0)
        for centers, r, _lvl in data["bundles"]:
            _collection(centers, r, facecolors="none", edgecolors="#2b8cff",
                        linestyles="--", linewidths=0.9)

        core_pos, core_r = data["cores"]
        for (kx, ky), kr in zip(core_pos, core_r):
            ax.add_patch(MplCircle((kx * mm, ky * mm), kr * mm, facecolor="#eeeeee",
                                   edgecolor="#888888", lw=0.8, hatch="...."))

        # strands: edge stroke only when few enough to matter visually
        n_strands = len(data["strands"])
        _collection(
            data["strands"], data["strand_r"], facecolors="#c87533",
            edgecolors=("#7a4418" if n_strands <= 20000 else "none"),
            linewidths=(0.4 if n_strands <= 20000 else 0.0),
        )

        if data["profile"] is not None:
            hw, hh = data["profile"]
            ax.add_patch(MplRect((-hw * mm, -hh * mm), 2 * hw * mm, 2 * hh * mm,
                                 fill=False, edgecolor="#ff5a5f", lw=1.4,
                                 linestyle="-."))
            max_r = max(max_r, hw)

        lim = max_r * mm * 1.15
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xlabel("mm")
        ax.set_title(
            "{0}\n(nominal layout — strands migrate along the lay)".format(con.name),
            fontsize=9,
        )
        self.canvas_xs.draw_idle()

    def _draw_ac(self, con, f1, f2, h_ext):
        freqs = np.logspace(np.log10(f1), np.log10(f2), 200)
        fac_iso = np.array([con.ac_factor(f) for f in freqs])
        self.fig_ac.clear()
        ax = self.fig_ac.add_subplot(211)
        ax.semilogx(freqs / 1e3, fac_iso, "-", linewidth=2, label="isolated bundle")
        if h_ext > 0:
            fac_w = np.array([con.ac_factor(f, h_ext) for f in freqs])
            ax.semilogx(freqs / 1e3, fac_w, "--", linewidth=2,
                        label="in winding (He/I={0:g}/m)".format(h_ext))
        ax.set_ylabel("Rac / Rdc")
        ax.grid(True, which="both", alpha=0.4)
        ax.legend(fontsize=8)
        ax2 = self.fig_ac.add_subplot(212, sharex=ax)
        rac = np.array([con.rac_per_meter(f, h_ext) for f in freqs])
        ax2.loglog(freqs / 1e3, rac * 1e3, "-", linewidth=2)
        ax2.set_xlabel("Frequency (kHz)")
        ax2.set_ylabel("Rac (mΩ/m)")
        ax2.grid(True, which="both", alpha=0.4)
        self.canvas_ac.draw_idle()

    # ---------------- coax page ----------------
    def _apply_coax_preset(self):
        from emstudio.wire import coax

        p = coax.PRESETS.get(self.coax_preset.currentText())
        if not p:
            return
        # per-cable eps/tan win over the generic dielectric preset values, so
        # apply the dielectric combo silently and then overwrite the spins
        self.coax_diel.blockSignals(True)
        self.coax_diel.setCurrentText(p["dielectric"])
        self.coax_diel.blockSignals(False)
        self.coax_a.setValue(p["a_m"] * 2e3)
        self.coax_b.setValue(p["b_m"] * 2e3)
        self.coax_eps.setValue(p["eps_r"])
        self.coax_tan.setValue(p["tan_delta"])
        self._recalc()

    def _solve_coax_b(self):
        from emstudio.wire import coax

        b_m = coax.b_for_z0(self.coax_a.value() * 1e-3 / 2.0,
                            self.coax_z0_target.value(), self.coax_eps.value())
        if 2 * b_m * 1e3 > self.coax_b.maximum():
            QtWidgets.QMessageBox.warning(
                self, "EMStudio", "Target Z0 needs 2b = {0:.1f} mm — beyond "
                "the input range; raise εr or the target.".format(2e3 * b_m))
            return
        self.coax_b.setValue(2.0 * b_m * 1e3)
        self._recalc()

    def _solve_tp_lay(self):
        from emstudio.wire import twisted_pair as tp

        ins = "soft" if "soft" in self.tp_ins.currentText() else "film"
        try:
            lay_m, theta = tp.lay_for_z0(
                self.tp_z0_target.value(), self.tp_d.value() * 1e-3,
                self.tp_s.value() * 1e-3, self.tp_eps.value(), ins)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "EMStudio", str(exc))
            return
        if lay_m * 1e3 > self.tp_lay.maximum():
            QtWidgets.QMessageBox.information(
                self, "EMStudio",
                "Target met with almost no twist (lay {0:.0f} mm, θ {1:.2f}°) "
                "— setting the maximum lay.".format(lay_m * 1e3, theta))
            lay_m = self.tp_lay.maximum() * 1e-3
        self.tp_lay.setValue(lay_m * 1e3)
        self.tp_nvp_on.setChecked(False)   # the solve is a Lefferson-mode result
        self._recalc()

    def _apply_coax_dielectric(self):
        from emstudio.wire import coax

        vals = coax.DIELECTRICS.get(self.coax_diel.currentText())
        if not vals:
            return  # "Custom" — leave the spins alone
        self.coax_eps.setValue(vals[0])
        self.coax_tan.setValue(vals[1])
        self._recalc()

    def _recalc_coax(self):
        from emstudio.wire import coax

        a_m = self.coax_a.value() * 1e-3 / 2.0
        b_m = self.coax_b.value() * 1e-3 / 2.0
        if b_m <= a_m:
            self.summary.setText(
                "<b>Invalid coax:</b> dielectric Ø (2b) must exceed inner Ø (2a)")
            return
        f_hz = self.coax_freq.value() * 1e6
        rep = coax.analyze(a_m, b_m, self.coax_eps.value(), self.coax_tan.value(),
                           freq_hz=f_hz)
        self._coax = rep
        self._coax_geom = (a_m, b_m)
        # bundle envelope: dielectric OD only — shield/braid/jacket build is
        # not modeled here, so the member OD should be edited up in the bundle
        self._last_envelope = ("Coax 2b {0:.2f} mm (no jacket)".format(
            2 * b_m * 1e3), 2 * b_m, "coax", 0.0)  # shielded: no coupling Ø
        self.summary.setText(
            "<b>Coax 2a {0:.3f} / 2b {1:.3f} mm, εr {2:g}</b><br>"
            "<b>Z0: {3:.2f} Ω</b> &nbsp; VF: {4:.1%}<br>"
            "C′: {5:.1f} pF/m &nbsp; L′: {6:.1f} nH/m<br>"
            "TE11 cutoff: {7:.2f} GHz (single-mode TEM below)<br>"
            "attenuation @ {8:g} MHz: <b>{9:.2f} dB/100 m</b> "
            "(conductor {10:.2f} + dielectric {11:.2f})<br>"
            "<small>smooth-solid-conductor model — real braided/stranded cables "
            "run ~10-45 % higher (see Spec tab)</small>".format(
                self.coax_a.value(), self.coax_b.value(), self.coax_eps.value(),
                rep["z0_ohm"], rep["velocity_factor"],
                rep["capacitance_pf_m"], rep["inductance_nh_m"],
                rep["cutoff_te11_hz"] / 1e9,
                self.coax_freq.value(), rep["attenuation_db_100m"],
                rep["conductor_db_100m"], rep["dielectric_db_100m"],
            )
        )
        self._draw_coax_xs(a_m, b_m, rep)
        self._draw_coax_rf(a_m, b_m, rep)
        self._coax_spec = self._coax_spec_markdown(rep)
        self.spec_view.setPlainText(self._coax_spec)

    def _draw_coax_xs(self, a_m, b_m, rep):
        self.fig_xs.clear()
        ax = self.fig_xs.add_subplot(111)
        ax.set_aspect("equal")
        mm = 1e3
        ax.add_patch(MplCircle((0, 0), b_m * mm, facecolor="#f4f0e8",
                               edgecolor="none"))
        ax.add_patch(MplCircle((0, 0), b_m * mm, fill=False, edgecolor="#555555",
                               lw=2.0, linestyle="--"))
        ax.add_patch(MplCircle((0, 0), a_m * mm, facecolor="#c87533",
                               edgecolor="#7a4418", lw=1.0))
        ax.annotate("shield inner face (2b)", (0, b_m * mm), (0, b_m * mm * 1.18),
                    ha="center", fontsize=8,
                    arrowprops=dict(arrowstyle="-", lw=0.6))
        lim = b_m * mm * 1.35
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xlabel("mm")
        ax.set_title(
            "Coax 2a {0:.3f} / 2b {1:.3f} mm — Z0 {2:.2f} Ω, VF {3:.1%}".format(
                2 * a_m * mm, 2 * b_m * mm, rep["z0_ohm"],
                rep["velocity_factor"]),
            fontsize=9,
        )
        self.canvas_xs.draw_idle()

    def _draw_coax_rf(self, a_m, b_m, rep):
        from emstudio.wire import coax

        eps_r = self.coax_eps.value()
        tan_d = self.coax_tan.value()
        freqs = np.logspace(6, 10, 200)  # 1 MHz .. 10 GHz
        a_c = np.array([100.0 * coax.conductor_loss_db_m(f, a_m, b_m, eps_r)
                        for f in freqs])
        a_d = np.array([100.0 * coax.dielectric_loss_db_m(f, eps_r, tan_d)
                        for f in freqs])
        self.fig_ac.clear()
        ax = self.fig_ac.add_subplot(111)
        ax.loglog(freqs / 1e6, a_c + a_d, "-", linewidth=2, label="total")
        ax.loglog(freqs / 1e6, a_c, "--", linewidth=1.2, label="conductor (∝√f)")
        ax.loglog(freqs / 1e6, a_d, ":", linewidth=1.2, label="dielectric (∝f)")
        fc = rep["cutoff_te11_hz"]
        if freqs[0] < fc < freqs[-1]:
            ax.axvline(fc / 1e6, color="#ff5a5f", lw=1.0, linestyle="-.")
            ax.text(fc / 1e6, ax.get_ylim()[1], " TE11 cutoff", fontsize=8,
                    color="#ff5a5f", va="top")
        f0 = rep["freq_hz"]
        ax.plot([f0 / 1e6], [rep["attenuation_db_100m"]], "o", ms=6)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Attenuation (dB/100 m)")
        ax.grid(True, which="both", alpha=0.4)
        ax.legend(fontsize=8)
        ax.set_title("smooth-conductor TEM model — braided cables run ~10-45 % higher",
                     fontsize=8)
        self.canvas_ac.draw_idle()

    def _coax_spec_markdown(self, rep):
        from emstudio.wire import coax

        preset = self.coax_preset.currentText()
        p = coax.PRESETS.get(preset)
        lines = [
            "# Coax spec — {0}".format(preset if p else "custom geometry"),
            "",
            "| Item | Value |",
            "|---|---|",
            "| Inner conductor Ø (2a) | {0:.4f} mm |".format(self.coax_a.value()),
            "| Dielectric Ø (2b) | {0:.4f} mm |".format(self.coax_b.value()),
            "| Dielectric | {0} (εr {1:g}, tanδ {2:g}) |".format(
                self.coax_diel.currentText(), self.coax_eps.value(),
                self.coax_tan.value()),
            "| Z0 | {0:.2f} Ω |".format(rep["z0_ohm"]),
            "| Velocity factor | {0:.1%} |".format(rep["velocity_factor"]),
            "| Capacitance C′ | {0:.1f} pF/m |".format(rep["capacitance_pf_m"]),
            "| Inductance L′ | {0:.1f} nH/m |".format(rep["inductance_nh_m"]),
            "| TE11 cutoff (single-mode limit) | {0:.2f} GHz |".format(
                rep["cutoff_te11_hz"] / 1e9),
            "",
            "## Attenuation (smooth-conductor TEM model, dB/100 m)",
            "",
            "| f (MHz) | conductor | dielectric | total |",
            "|---|---|---|---|",
        ]
        a_m, b_m = self._coax_geom
        eps_r, tan_d = self.coax_eps.value(), self.coax_tan.value()
        for mhz in (1.0, 10.0, 100.0, 400.0, 1000.0):
            ac = 100.0 * coax.conductor_loss_db_m(mhz * 1e6, a_m, b_m, eps_r)
            ad = 100.0 * coax.dielectric_loss_db_m(mhz * 1e6, eps_r, tan_d)
            lines.append("| {0:g} | {1:.2f} | {2:.2f} | {3:.2f} |".format(
                mhz, ac, ad, ac + ad))
        lines += [
            "",
            "*Smooth-solid-conductor loss model: real braided/tinned/stranded",
            "cables run ~10-45 % higher (braid weave + stranding). Z0/VF/C′ are",
            "geometry-exact. Full-wave cross-check: the Palace lumped-port coax",
            "backend (Full-wave verify button).*",
        ]
        if p:
            lines += ["", "*Preset note: {0}*".format(p["note"])]
        from emstudio.legal import SPEC_DISCLAIMER

        lines += ["", SPEC_DISCLAIMER]
        return "\n".join(lines)

    # ---------------- twisted-pair page ----------------
    def _apply_tp_preset(self):
        from emstudio.wire import twisted_pair as tp

        p = tp.PRESETS.get(self.tp_preset.currentText())
        if not p:
            return
        self.tp_d.setValue(p["d_m"] * 1e3)
        self.tp_s.setValue(p["s_m"] * 1e3)
        self.tp_ins.setCurrentIndex(0 if p["insulation"] == "film" else 1)
        self.tp_eps.setValue(p["eps_r"])
        self.tp_tan.setValue(p["tan_delta"])
        self.tp_lay.setValue(p["lay_m"] * 1e3)
        self.tp_nvp_on.setChecked(True)
        self.tp_nvp.setValue(p["nvp"])
        self.tp_shield_on.setChecked(False)
        self._recalc()

    def _recalc_tp(self):
        from emstudio.wire import twisted_pair as tp

        d_m = self.tp_d.value() * 1e-3
        s_m = self.tp_s.value() * 1e-3
        if s_m <= d_m:
            self.summary.setText(
                "<b>Invalid pair:</b> insulated OD (spacing s) must exceed "
                "the bare conductor Ø")
            return
        shield_m = self.tp_shield.value() * 1e-3 if self.tp_shield_on.isChecked() \
            else 0.0
        if shield_m and shield_m <= s_m + d_m:
            self.summary.setText(
                "<b>Invalid shield:</b> shield Ø must exceed s + d "
                "(both wires must fit inside)")
            return
        ins = "soft" if "soft" in self.tp_ins.currentText() else "film"
        twists_per_m = 1000.0 / self.tp_lay.value()
        rep = tp.analyze(
            d_m, s_m, self.tp_eps.value(), self.tp_tan.value(), twists_per_m,
            ins, shield_id_m=shield_m,
            nvp=self.tp_nvp.value() if self.tp_nvp_on.isChecked() else None,
            freq_hz=self.tp_freq.value() * 1e6)
        self._tp = rep
        self._tp_geom = (d_m, s_m, shield_m)
        self._last_envelope = ("Twisted pair s {0:.2f} mm".format(s_m * 1e3),
                               2.0 * s_m, "twisted_pair", 0.0)  # differential

        warns = []
        if rep["q_exceeds_1"] and rep["eps_eff_source"] == "lefferson":
            warns.append("q &gt; 1: the Lefferson fit is outside its physical "
                         "regime (θ &gt; 43.3° film / 27.4° soft)")
        if not rep["thin_wire_ok"]:
            warns.append("shield model thin-wire limit exceeded (d/s &gt; 0.4: "
                         "expect a few % optimistic Z0)")
        if rep["theta_deg"] > 50.0:
            warns.append("pitch angle &gt; 50°: wire typically breaks in "
                         "manufacture near 50.5°")
        self.summary.setText(
            "<b>Twisted pair d {0:.3f} / s {1:.3f} mm{2}</b><br>"
            "<b>Z0 (differential): {3:.1f} Ω</b> &nbsp; Z_odd: {4:.1f} Ω<br>"
            "VF: {5:.1%} &nbsp; (εeff {6:.3f}, from {7})<br>"
            "C′: {8:.1f} pF/m &nbsp; L′: {9:.1f} nH/m<br>"
            "twist: θ {10:.1f}° (q {11:.2f}) &nbsp; wire length ×{12:.3f}<br>"
            "attenuation @ {13:g} MHz: <b>{14:.2f} dB/100 m</b> "
            "(conductor {15:.2f} + dielectric {16:.2f})"
            "{17}".format(
                self.tp_d.value(), self.tp_s.value(),
                " (shielded)" if rep["shielded"] else "",
                rep["z0_diff_ohm"], rep["z0_odd_ohm"],
                rep["velocity_factor"], rep["eps_eff"],
                "datasheet NVP" if rep["eps_eff_source"] == "nvp"
                else "Lefferson twist model",
                rep["capacitance_pf_m"], rep["inductance_nh_m"],
                rep["theta_deg"], rep["q"], rep["length_factor"],
                self.tp_freq.value(), rep["attenuation_db_100m"],
                rep["conductor_db_100m"], rep["dielectric_db_100m"],
                "".join("<br><span style='color:#b06000'>⚠ {0}</span>".format(w)
                        for w in warns),
            )
        )
        self._draw_tp_xs(d_m, s_m, shield_m, rep)
        self._draw_tp_rf(d_m, s_m, shield_m, ins, rep)
        self._tp_spec = self._tp_spec_markdown(rep)
        self.spec_view.setPlainText(self._tp_spec)

    def _draw_tp_xs(self, d_m, s_m, shield_m, rep):
        self.fig_xs.clear()
        ax = self.fig_xs.add_subplot(111)
        ax.set_aspect("equal")
        mm = 1e3
        for sign in (-1.0, 1.0):
            cx = sign * s_m / 2.0 * mm
            ax.add_patch(MplCircle((cx, 0), s_m / 2.0 * mm, facecolor="#f4f0e8",
                                   edgecolor="#333333", lw=1.0))
            ax.add_patch(MplCircle((cx, 0), d_m / 2.0 * mm, facecolor="#c87533",
                                   edgecolor="#7a4418", lw=1.0))
        lim = s_m * mm * 1.4
        if shield_m:
            ax.add_patch(MplCircle((0, 0), shield_m / 2.0 * mm, fill=False,
                                   edgecolor="#555555", lw=2.0, linestyle="--"))
            lim = max(lim, shield_m / 2.0 * mm * 1.25)
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xlabel("mm")
        ax.set_title(
            "Twisted pair d {0:.3f} / s {1:.3f} mm{2} — Z0 {3:.1f} Ω, "
            "VF {4:.1%}".format(
                d_m * mm, s_m * mm,
                " / shield {0:.2f} mm".format(shield_m * mm) if shield_m else "",
                rep["z0_diff_ohm"], rep["velocity_factor"]),
            fontsize=9,
        )
        self.canvas_xs.draw_idle()

    def _draw_tp_rf(self, d_m, s_m, shield_m, ins, rep):
        from emstudio.wire import twisted_pair as tp

        self.fig_ac.clear()
        # top: Z0 vs twist lay (Lefferson path; the NVP value as a reference)
        ax = self.fig_ac.add_subplot(211)
        lays = np.linspace(2.0, 60.0, 200)  # mm/turn
        z_lay = []
        for lm in lays:
            th = tp.twist_angle_deg(1000.0 / lm, s_m)
            ee = tp.eps_effective(self.tp_eps.value(), th, ins)
            z_lay.append(tp.z0_shielded_ohm(s_m, d_m, shield_m, ee)
                         if shield_m else tp.z0_diff_ohm(s_m, d_m, ee))
        ax.plot(lays, z_lay, "-", linewidth=2,
                label="Lefferson εeff (εr {0:g}, {1})".format(
                    self.tp_eps.value(), ins))
        if rep["eps_eff_source"] == "nvp":
            ax.axhline(rep["z0_diff_ohm"], color="#2b8cff", lw=1.2,
                       linestyle="--",
                       label="datasheet NVP εeff → {0:.1f} Ω".format(
                           rep["z0_diff_ohm"]))
        ax.plot([self.tp_lay.value()], [rep["z0_diff_ohm"]], "o", ms=6)
        ax.set_xlabel("Twist lay (mm/turn)")
        ax.set_ylabel("Z0 diff (Ω)")
        ax.grid(True, alpha=0.4)
        ax.legend(fontsize=7)
        # bottom: attenuation vs frequency
        ax2 = self.fig_ac.add_subplot(212)
        freqs = np.logspace(6, 9, 150)
        att = [tp.attenuation_db_per_100m(f, s_m, d_m, rep["eps_eff"],
                                          self.tp_tan.value()) for f in freqs]
        ax2.loglog(freqs / 1e6, att, "-", linewidth=2)
        ax2.plot([rep["freq_hz"] / 1e6], [rep["attenuation_db_100m"]], "o", ms=6)
        ax2.set_xlabel("Frequency (MHz)")
        ax2.set_ylabel("Attenuation (dB/100 m)")
        ax2.grid(True, which="both", alpha=0.4)
        self.fig_ac.suptitle(
            "smooth-conductor model — real cables run higher", fontsize=8)
        self.canvas_ac.draw_idle()

    def _tp_spec_markdown(self, rep):
        from emstudio.wire import twisted_pair as tp

        preset = self.tp_preset.currentText()
        p = tp.PRESETS.get(preset)
        d_m, s_m, shield_m = self._tp_geom
        lines = [
            "# Twisted-pair spec — {0}".format(preset if p else "custom geometry"),
            "",
            "| Item | Value |",
            "|---|---|",
            "| Conductor Ø (bare) | {0:.4f} mm |".format(d_m * 1e3),
            "| Insulated OD (= spacing s) | {0:.4f} mm |".format(s_m * 1e3),
            "| Shield | {0} |".format(
                "{0:.3f} mm inner Ø".format(shield_m * 1e3) if shield_m
                else "none (UTP)"),
            "| Insulation | εr {0:g}, tanδ {1:g}, {2} |".format(
                self.tp_eps.value(), self.tp_tan.value(),
                self.tp_ins.currentText()),
            "| Twist lay | {0:.2f} mm/turn (θ {1:.1f}°, q {2:.3f}) |".format(
                self.tp_lay.value(), rep["theta_deg"], rep["q"]),
            "| εeff | {0:.4f} (from {1}) |".format(
                rep["eps_eff"],
                "datasheet NVP {0:g}".format(self.tp_nvp.value())
                if rep["eps_eff_source"] == "nvp" else "the Lefferson model"),
            "| Z0 (differential) | {0:.1f} Ω |".format(rep["z0_diff_ohm"]),
            "| Z odd-mode (= Z0/2) | {0:.1f} Ω |".format(rep["z0_odd_ohm"]),
            "| Velocity factor | {0:.1%} |".format(rep["velocity_factor"]),
            "| Capacitance C′ | {0:.1f} pF/m |".format(rep["capacitance_pf_m"]),
            "| Inductance L′ | {0:.1f} nH/m |".format(rep["inductance_nh_m"]),
            "| Wire length per line length | ×{0:.4f} |".format(
                rep["length_factor"]),
            "",
            "## Attenuation (smooth-conductor model, dB/100 m)",
            "",
            "| f (MHz) | conductor | dielectric | total |",
            "|---|---|---|---|",
        ]
        for mhz in (1.0, 10.0, 100.0, 500.0):
            ac = 100.0 * tp.conductor_loss_db_m(mhz * 1e6, s_m, d_m,
                                                rep["eps_eff"])
            ad = 100.0 * tp.dielectric_loss_db_m(mhz * 1e6, rep["eps_eff"],
                                                 self.tp_tan.value())
            lines.append("| {0:g} | {1:.2f} | {2:.2f} | {3:.2f} |".format(
                mhz, ac, ad, ac + ad))
        lines += [
            "",
            "*Exact two-wire acosh line + Lefferson (1971) twist/insulation",
            "effective permittivity (θ in degrees); shielded form: RDRE",
            "thin-wire (best for d/s ≤ 0.4). For real cables εeff from the",
            "datasheet NVP is the honest choice. Validated in",
            "tests/validation/cable.py.*",
        ]
        if p:
            lines += ["", "*Preset note: {0}*".format(p["note"])]
        from emstudio.legal import SPEC_DISCLAIMER

        lines += ["", SPEC_DISCLAIMER]
        return "\n".join(lines)

    # ---------------- bundle page ----------------
    def _bundle_model(self):
        from emstudio.wire import bundle as bn

        members = []
        for r in range(self.bundle_table.rowCount()):
            members.append(bn.BundleMember(
                label=self.bundle_table.cellWidget(r, 0).text() or "member",
                od_m=self.bundle_table.cellWidget(r, 1).value() * 1e-3,
                qty=self.bundle_table.cellWidget(r, 2).value(),
                kind=self.bundle_table.cellWidget(r, 3).currentText(),
                conductor_d_m=self.bundle_table.cellWidget(r, 4).value() * 1e-3,
            ))
        jtxt = self.bundle_jacket.currentText().strip()
        jacket = "" if jtxt.lower() in ("", "none") else jtxt
        return bn.Bundle(members=members, jacket=jacket,
                         jacket_m=self.bundle_wall.value() * 1e-3
                         if jacket else 0.0,
                         name="multi-design bundle")

    def _bundle_convection(self):
        """Solve convection for the members in the table above.

        ⚠ The geometry comes from ``_bundle_model()`` — the SAME packing the
        rest of this page reports — so the factor is solved for the bundle the
        user is actually looking at. Re-deriving positions here would risk
        solving a geometry the dialog never showed.

        ⚠ MIXED diameters are still never AVERAGED — they are solved size by
        size. Each diameter becomes its own snappy patch and gets its own
        Nusselt number and its own factor, because Nu_D is built on a diameter
        and a mean of unlike cables would be a number with no defensible
        definition. The mix is the common case, so refusing it (which is what
        this did until now) was honest and useless.
        """
        from PySide import QtWidgets

        from emstudio.ui import convection_dialog
        from emstudio.wire import bundle_convection as bc

        try:
            cables = bc.cables_from_bundle(self._bundle_model())
        except ValueError as exc:
            QtWidgets.QMessageBox.information(
                self, "Convection", str(exc))
            return
        side = convection_dialog.enclosure_side(
            cables, None, float(self.conv_clearance.value()))
        dlg = convection_dialog.build_dialog(cables, None, side, side,
                                             parent=self)
        dlg.exec()

    def _recalc_bundle(self):
        if self.bundle_table.rowCount() == 0:
            self.summary.setText("<b>Empty bundle:</b> add at least one member")
            return
        b = self._bundle_model()
        placed, r_enc = b.pack()
        self._bundle = b
        n_placed = len(placed)
        self.summary.setText(
            "<b>Bundle — {0} members placed</b><br>"
            "core OD (packed): <b>{1:.3f} mm</b><br>"
            "finished OD (over jacket): <b>{2:.3f} mm</b><br>"
            "fill factor: {3:.3f} &nbsp; (7-member hex = 0.778)<br>"
            "<small>nominal tangency packing — members migrate along the lay; "
            "member-to-member coupling (RLGC/crosstalk) is a planned "
            "FastHenry slice</small>".format(
                n_placed, b.core_od_m() * 1e3, b.od_m() * 1e3,
                b.fill_factor()))
        self._draw_bundle_xs(b, placed, r_enc)
        self._draw_bundle_rf()
        self._bundle_spec = b.spec_markdown()
        self.spec_view.setPlainText(self._bundle_spec)

    _BUNDLE_COLORS = {"wire": "#c87533", "litz": "#c87533",
                      "coax": "#2b8cff", "twisted_pair": "#7a9c48",
                      "generic": "#999999"}

    def _draw_bundle_xs(self, b, placed, r_enc):
        self.fig_xs.clear()
        ax = self.fig_xs.add_subplot(111)
        ax.set_aspect("equal")
        mm = 1e3
        if b.jacket:
            ax.add_patch(MplCircle((0, 0), (r_enc + b.jacket_m) * mm,
                                   facecolor="#4a4a55", edgecolor="#222222",
                                   lw=1.4))
        ax.add_patch(MplCircle((0, 0), r_enc * mm, facecolor="#f4f0e8",
                               edgecolor="#333333", lw=1.0))
        for x, y, r, m in placed:
            ax.add_patch(MplCircle((x * mm, y * mm), r * mm,
                                   facecolor=self._BUNDLE_COLORS.get(
                                       m.kind, "#999999"),
                                   edgecolor="#333333", lw=0.8, alpha=0.85))
        lim = (r_enc + b.jacket_m) * mm * 1.15
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xlabel("mm")
        ax.set_title(
            "Bundle — core {0:.2f} mm / finished {1:.2f} mm, fill {2:.2f}\n"
            "(nominal packing; colors = member kind)".format(
                b.core_od_m() * 1e3, b.od_m() * 1e3, b.fill_factor()),
            fontsize=9)
        self.canvas_xs.draw_idle()

    def _draw_bundle_rf(self):
        self.fig_ac.clear()
        ax = self.fig_ac.add_subplot(111)
        ax.axis("off")
        ax.text(0.5, 0.5,
                "Pick generator / receptor / reference members below\n"
                "and press 'Estimate crosstalk' — the weak-coupling\n"
                "NE/FE curves render here.",
                ha="center", va="center", fontsize=9, color="gray")
        self.canvas_ac.draw_idle()

    # ---------------- bundle coupling / crosstalk ----------------
    def _xt_mode_changed(self, diff_on):
        """Swap the crosstalk group between single-ended and diff-pair mode."""
        for w in (self.xt_a1, self.xt_a2, self.xt_b1, self.xt_b2,
                  self.xt_twist, self.xt_recmode):
            w.setEnabled(diff_on)
        for w in (self.xt_gen, self.xt_rec):
            w.setEnabled(not diff_on)
        self.xt_r_label.setText("Terminations (differential Ω)" if diff_on
                                else "Terminations (Ω)")

    def _pick_members(self, spin_roles, distinct_msg):
        """([(pos, cond_r, env_r, label)] in spin order, "") or (None, msg).

        Shared validated picker for the crosstalk estimates. ``env_r`` is the
        member's envelope (insulation-OD) radius, so the insulation wall
        = env_r - cond_r feeds the insulated-C MoM. Indices are into the
        PACKED (qty-expanded) member list.
        """
        if getattr(self, "_bundle", None) is None:
            self._recalc()
        if getattr(self, "_bundle", None) is None:
            return None, "add at least one bundle member first"
        placed, _r = self._bundle.pack()
        picks = []
        for spin, role in spin_roles:
            i = spin.value() - 1
            if i < 0 or i >= len(placed):
                return None, "{0} member #{1} does not exist".format(
                    role, spin.value())
            x, y, r_env, m = placed[i]
            if m.conductor_d_m <= 0.0:
                return None, ("{0} member #{1} ('{2}') has no conductor Ø — "
                              "set the Cond. Ø column".format(
                                  role, spin.value(), m.label))
            picks.append(((x, y), m.conductor_d_m / 2.0, r_env, m.label))
        if len({p[0] for p in picks}) < len(spin_roles):
            return None, distinct_msg
        return picks, ""

    def _coupling_quint(self):
        """Picks for [ref, A1, A2, B1, B2] (diff-pair mode)."""
        return self._pick_members(
            ((self.xt_ref, "reference"), (self.xt_a1, "A1"),
             (self.xt_a2, "A2"), (self.xt_b1, "B1"), (self.xt_b2, "B2")),
            "reference and the four pair conductors must be five distinct "
            "members")

    def _coupling_triple(self):
        """Picks for [ref, gen, rec] (single-ended mode)."""
        return self._pick_members(
            ((self.xt_ref, "reference"), (self.xt_gen, "generator"),
             (self.xt_rec, "receptor")),
            "generator / receptor / reference must be distinct members")

    def _bundle_c_matrix(self, positions, radii, walls):
        """(TL C matrix or None, source label) for the picked conductors.

        MoM insulated solve when any picked member is insulated (wall > 0) —
        exact at ANY spacing; ``None`` for all-bare picks: the caller uses the
        identity C from the ANALYTIC wide-separation L (deliberate — the
        identity needs the electrostatic-consistent L; a FastHenry
        uniform-current L corrupts C by ~20 %).
        """
        if any(w > 1e-9 for w in walls):
            from emstudio.wire import electrostatics as es

            er = self.xt_eps.value()
            mom = es.bundle_c_mom(
                positions, radii,
                er=[er if w > 1e-9 else 1.0 for w in walls],
                wall=walls, ref=0, nf=10)
            return mom["c_tl"], "MoM insulated (εr {0:g})".format(er)
        return None, "bare identity"

    @staticmethod
    def _widesep_warn(widesep_ok, ratio, source, c_source):
        """(plot-title suffix, summary HTML) for the s/rw >= 4 validity flag.

        On the FastHenry route L is spacing-exact, but a BARE pick's C still
        comes from the analytic wide-separation identity, so tight spacings
        keep a C-side caveat there; the MoM insulated C is a full
        electrostatic solve — valid at any spacing, no caveat.
        """
        if widesep_ok:
            return "", ""
        if not source.startswith("FastHenry"):
            return ("  [s/rw {0:.1f} < 4: analytic L over-estimated — use "
                    "FastHenry]".format(ratio),
                    "<br><span style='color:#b06000'>⚠ analytic validity "
                    "s/rw ≥ 4 violated — prefer the FastHenry option</span>")
        if c_source == "bare identity":
            return ("  [s/rw {0:.1f} < 4: bare-identity C still "
                    "analytic]".format(ratio),
                    "<br><span style='color:#b06000'>⚠ s/rw &lt; 4: FastHenry "
                    "L is exact, but the bare-identity C still derives from "
                    "the analytic wide-separation L — treat capacitive "
                    "values as approximate</span>")
        return "", ""

    def _bundle_coupling(self):
        from emstudio.wire import coupling as cp

        if self.xt_diff.isChecked():
            return self._bundle_diff_coupling()
        picks, err = self._coupling_triple()
        if picks is None:
            QtWidgets.QMessageBox.warning(self, "EMStudio", err)
            return
        positions = [p[0] for p in picks]
        radii = [p[1] for p in picks]
        walls = [max(p[2] - p[1], 0.0) for p in picks]   # env_r - cond_r
        params = {
            "length_m": self.xt_len.value(),
            "rs": self.xt_rs.value(), "rl": self.xt_rl.value(),
            "rne": self.xt_rne.value(), "rfe": self.xt_rfe.value(),
            "freq_hz": self.xt_freq.value() * 1e6,
        }
        cpl = cp.bundle_coupling_analytic(positions, radii, ref=0)
        # picks order is [ref, gen, rec] -> the crosstalk cm is the gen<->rec
        # mutual [0][1] of the TL C (ref removed); C source per the shared
        # helper (MoM insulated at any spacing / bare identity from analytic L)
        c4m, c_src = self._bundle_c_matrix(positions, radii, walls)
        cm = -float((c4m if c4m is not None else cpl["c_matrix"])[0][1])
        cpl = dict(cpl, c_source=c_src)
        if self.xt_fh.isChecked():
            def run_fn(a, s, cb):
                return cp.fasthenry_loop_matrices(
                    positions, radii, freq_hz=params["freq_hz"],
                    length_m=0.5, nhinc=5, line_callback=cb)

            from emstudio.ui import run_gui

            run_gui.run_generic_gui(
                "FastHenry bundle coupling (2 runs)", run_fn,
                lambda rl_mats: self._show_bundle_coupling(
                    float(rl_mats[1][0][1]), cm, float(rl_mats[0][0][1]),
                    params, cpl, "FastHenry L (loop, {0:g} MHz)".format(
                        params["freq_hz"] / 1e6)),
                parent=self)
            return
        self._show_bundle_coupling(
            float(cpl["l_matrix"][0][1]), cm, cpl["ref_r_dc_ohm_m"],
            params, cpl, "analytic wide-separation")

    def _show_bundle_coupling(self, lm, cm, r_common, params, cpl, source):
        from emstudio.wire import coupling as cp

        xt = cp.crosstalk_weak(lm, cm, params["length_m"], params["rs"],
                               params["rl"], params["rne"], params["rfe"],
                               params["freq_hz"], r_common_ohm_m=r_common)
        self._xtalk = dict(xt, lm_h_m=lm, cm_f_m=cm, source=source,
                           c_source=cpl.get("c_source", "bare identity"),
                           widesep_ok=cpl["widesep_ok"],
                           min_s_over_rw=cpl["min_s_over_rw"])
        # NE/FE vs frequency on the RF tab (weak coupling: 20 dB/decade)
        self.fig_ac.clear()
        ax = self.fig_ac.add_subplot(111)
        f_hi = min(xt["short_line_max_hz"], 1e9)
        freqs = np.logspace(3, math.log10(f_hi), 120)
        ne = [cp.crosstalk_weak(lm, cm, params["length_m"], params["rs"],
                                params["rl"], params["rne"], params["rfe"],
                                f, r_common_ohm_m=r_common) for f in freqs]
        ax.loglog(freqs / 1e6, [max(v["vne_over_vs"], 1e-12) for v in ne],
                  "-", linewidth=2, label="near end |VNE/VS|")
        ax.loglog(freqs / 1e6, [max(v["vfe_over_vs"], 1e-12) for v in ne],
                  "--", linewidth=2, label="far end |VFE/VS|")
        if xt["common_impedance_floor"] > 0:
            ax.axhline(xt["common_impedance_floor"], color="#ff5a5f", lw=1.0,
                       linestyle=":", label="common-impedance floor")
        ax.plot([params["freq_hz"] / 1e6], [xt["vne_over_vs"]], "o", ms=6)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("crosstalk ratio")
        ax.grid(True, which="both", alpha=0.4)
        ax.legend(fontsize=8)
        warn, warn_html = self._widesep_warn(
            cpl["widesep_ok"], cpl["min_s_over_rw"], source,
            cpl.get("c_source", "bare identity"))
        ax.set_title(
            "weak coupling ({0}) — valid while the line is electrically short "
            "(< {1:.1f} MHz){2}".format(source, xt["short_line_max_hz"] / 1e6,
                                        warn),
            fontsize=8)
        self.canvas_ac.draw_idle()
        self.tabs.setCurrentIndex(1)
        self.summary.setText(
            self.summary.text().split("<hr>")[0]
            + "<hr><b>Crosstalk ({0})</b>: lm {1:.1f} nH/m, cm {2:.2f} pF/m"
              " [{8}]"
              "<br>@ {3:g} MHz: NE <b>{4:.1f} dB</b>, FE <b>{5:.1f} dB</b>"
              " ({6} coupling dominant){7}".format(
                  source, lm * 1e9, cm * 1e12, params["freq_hz"] / 1e6,
                  xt["vne_db"], xt["vfe_db"],
                  "inductive" if xt["inductive_dominant_ne"] else "capacitive",
                  warn_html, self._xtalk["c_source"]))

    def _bundle_diff_coupling(self):
        from emstudio.wire import coupling as cp

        picks, err = self._coupling_quint()
        if picks is None:
            QtWidgets.QMessageBox.warning(self, "EMStudio", err)
            return
        positions = [p[0] for p in picks]
        radii = [p[1] for p in picks]
        walls = [max(p[2] - p[1], 0.0) for p in picks]   # env_r - cond_r
        params = {
            "length_m": self.xt_len.value(),
            "rs": self.xt_rs.value(), "rl": self.xt_rl.value(),
            "rne": self.xt_rne.value(), "rfe": self.xt_rfe.value(),
            "freq_hz": self.xt_freq.value() * 1e6,
            "n_half_twists": self.xt_twist.value(),
            "receptor": self.xt_recmode.currentData(),
        }
        cpl = cp.bundle_coupling_analytic(positions, radii, ref=0)
        meta = {
            "min_s_over_rw": cpl["min_s_over_rw"],
            "widesep_ok": cpl["widesep_ok"],
        }
        c4m, meta["c_source"] = self._bundle_c_matrix(positions, radii, walls)
        # bare picks keep the identity C from the ANALYTIC L on BOTH routes
        # (deliberate: the identity needs the electrostatic-consistent L —
        # a FastHenry uniform-current L corrupts C; see _bundle_c_matrix)
        c4 = c4m if c4m is not None else cpl["c_matrix"]
        if self.xt_fh.isChecked():
            def run_fn(a, s, cb):
                return cp.fasthenry_loop_matrices(
                    positions, radii, freq_hz=params["freq_hz"],
                    length_m=0.5, nhinc=5, line_callback=cb)

            from emstudio.ui import run_gui

            run_gui.run_generic_gui(
                "FastHenry bundle coupling (2 runs)", run_fn,
                lambda rl_mats: self._show_bundle_diff(
                    rl_mats[1], c4, params, meta,
                    "FastHenry L (loop, {0:g} MHz)".format(
                        params["freq_hz"] / 1e6)),
                parent=self)
            return
        self._show_bundle_diff(cpl["l_matrix"], c4, params, meta,
                               "analytic wide-separation")

    def _show_bundle_diff(self, l4, c4, params, meta, source):
        import html as _html

        from emstudio.wire import coupling as cp
        from emstudio.wire import mixed_mode as mmx

        xt = mmx.diff_crosstalk(
            np.asarray(l4, dtype=float), np.asarray(c4, dtype=float),
            params["length_m"], params["rs"], params["rl"], params["rne"],
            params["rfe"], params["freq_hz"], params["n_half_twists"],
            params["receptor"])
        self._xtalk_diff = dict(xt, source=source, **meta)
        n = params["n_half_twists"]
        # differential NE/FE vs frequency, untwisted + twisted envelope —
        # the reduction is frequency-independent, so sweep only crosstalk_weak
        # on the couplings already in hand (same lm/cm as the marker readout)
        self.fig_ac.clear()
        ax = self.fig_ac.add_subplot(111)
        f_hi = min(xt["short_line_max_hz"], 1e9)
        freqs = np.logspace(3, math.log10(f_hi), 120)
        lm, cm = xt["lm_h_m"], xt["cm_f_m"]

        def _sweep(li, ci):
            return [cp.crosstalk_weak(li, ci, params["length_m"],
                                      params["rs"], params["rl"],
                                      params["rne"], params["rfe"], f)
                    for f in freqs]

        base_sw = _sweep(lm, cm)
        tw_sw = base_sw if n == 0 else _sweep(lm * xt["f_inductive"],
                                              cm * xt["f_capacitive"])
        ax.loglog(freqs / 1e6,
                  [max(v["vne_over_vs"], 1e-15) for v in base_sw],
                  "-", linewidth=2, label="NE diff (untwisted)")
        ax.loglog(freqs / 1e6,
                  [max(v["vfe_over_vs"], 1e-15) for v in base_sw],
                  "--", linewidth=2, label="FE diff (untwisted)")
        if n > 0:
            ax.loglog(freqs / 1e6,
                      [max(v["vne_over_vs"], 1e-15) for v in tw_sw],
                      "-", linewidth=1.2,
                      label="NE diff (N={0}, {1})".format(
                          n, self.xt_recmode.currentText().lower()))
            ax.loglog(freqs / 1e6,
                      [max(v["vfe_over_vs"], 1e-15) for v in tw_sw],
                      "--", linewidth=1.2, label="FE diff (twisted)")
        ax.plot([params["freq_hz"] / 1e6], [xt["twisted"]["vne_over_vs"]],
                "o", ms=6)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("differential crosstalk ratio")
        ax.grid(True, which="both", alpha=0.4)
        ax.legend(fontsize=8)
        warn, warn_html = self._widesep_warn(
            meta["widesep_ok"], meta["min_s_over_rw"], source,
            meta["c_source"])
        ax.set_title(
            "diff pair-to-pair, weak coupling ({0}) — electrically short "
            "(< {1:.1f} MHz){2}".format(source,
                                        xt["short_line_max_hz"] / 1e6, warn),
            fontsize=8)
        self.canvas_ac.draw_idle()
        self.tabs.setCurrentIndex(1)
        # signed rendering: improvement can be NEGATIVE (twist worsens
        # opposite-sign lm/cm cases) — "{:+.1f} dB vs untwisted" of the CHANGE
        twist_note = "" if n == 0 else \
            " (N={0}: {1:+.1f} dB vs untwisted)".format(
                n, -xt["improvement_ne_db"])
        mdd_note = " (pair B relabeled)" if xt["polarity_flipped"] else ""
        extra_warn = "".join(
            "<br><span style='color:#b06000'>⚠ {0}</span>".format(
                _html.escape(w))
            for w in xt["warnings"]) + warn_html
        self.summary.setText(
            self.summary.text().split("<hr>")[0]
            + "<hr><b>Diff pair-to-pair ({0})</b>: k_diff <b>{1:.2e}</b>, "
              "CUPP {2:.2f} pF/100 m [{3}]"
              "<br>Zdd A/B: {4:.1f} / {5:.1f} Ω &nbsp; Mdd {6:.3f} nH/m{7}"
              "<br>@ {8:g} MHz diff NE <b>{9:.1f} dB</b>, FE {10:.1f} dB"
              "{11}{12}".format(
                  source, xt["k_diff"],
                  xt["cupp_f_m"] * 1e12 * 100.0, meta["c_source"],
                  xt["zdd_a_ohm"], xt["zdd_b_ohm"], xt["mdd"] * 1e9,
                  mdd_note, params["freq_hz"] / 1e6,
                  xt["twisted"]["vne_db"], xt["twisted"]["vfe_db"],
                  twist_note, extra_warn))

    # ---------------- thermal tab (§2 thermal slice) ----------------
    def _build_thermal_tab(self):
        from emstudio.wire import thermal as th

        tab = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(tab)
        strip = QtWidgets.QHBoxLayout()
        self.th_current = QtWidgets.QDoubleSpinBox()
        self.th_current.setRange(0.01, 5000.0)
        self.th_current.setValue(10.0)
        self.th_current.setSuffix(" A")
        self.th_freq = QtWidgets.QDoubleSpinBox()
        self.th_freq.setRange(0.0, 100000.0)
        self.th_freq.setDecimals(1)
        self.th_freq.setValue(0.0)
        self.th_freq.setSuffix(" kHz")
        self.th_freq.setSpecialValueText("DC")
        self.th_freq.setToolTip(
            "AC load frequency: the conductor loss uses this page's own\n"
            "Rac/Rdc factor (skin + internal proximity). DC = factor 1.")
        self.th_amb = QtWidgets.QDoubleSpinBox()
        self.th_amb.setRange(-60.0, 85.0)
        self.th_amb.setValue(30.0)
        self.th_amb.setSuffix(" °C")
        self.th_class = QtWidgets.QComboBox()
        for name in th.TEMP_CLASSES:
            self.th_class.addItem(name)
        self.th_class.setCurrentText(th.DEFAULT_TEMP_CLASS)
        self.th_eps = QtWidgets.QDoubleSpinBox()
        self.th_eps.setRange(0.05, 0.98)
        self.th_eps.setDecimals(2)
        self.th_eps.setValue(0.92)
        self.th_eps.setToolTip(
            "Surface emissivity. Polymer jackets 0.90-0.95; bare bright "
            "copper ~0.05,\noxidized ~0.3-0.8 — set accordingly for "
            "unjacketed conductors.")
        self.th_btn = QtWidgets.QPushButton("Analyze thermal")
        self.th_btn.clicked.connect(self._run_thermal)
        for lab, w in (("Load", self.th_current), ("@", self.th_freq),
                       ("Ambient", self.th_amb),
                       ("Limit", self.th_class), ("ε", self.th_eps)):
            strip.addWidget(QtWidgets.QLabel(lab))
            strip.addWidget(w)
        strip.addWidget(self.th_btn)
        strip.addStretch(1)
        lay.addLayout(strip)
        self.fig_th = Figure(figsize=(7, 6), tight_layout=True)
        self.canvas_th = FigureCanvas(self.fig_th)
        lay.addWidget(self.canvas_th, 1)
        self.th_result = QtWidgets.QLabel(
            "Free-air steady/transient model (IEC 60287 radial ladder + "
            "Churchill-Chu surface, gated in tests/validation/thermal.py). "
            "Pick a load and press Analyze.")
        self.th_result.setWordWrap(True)
        lay.addWidget(self.th_result)
        return tab

    def _run_thermal(self):
        kind = self.construction.currentData()
        if kind in ("litz", "wire"):
            self._thermal_wirelike()
        elif kind == "coax":
            self._thermal_coax()
        elif kind == "bundle":
            self._thermal_bundle()
        else:
            self._thermal_tp()

    def _thermal_message(self, html):
        self.fig_th.clear()
        self.canvas_th.draw_idle()
        self.th_result.setText(html)

    def _thermal_bundle(self):
        from emstudio.wire import thermal as th

        n = sum(self.bundle_table.cellWidget(r, 2).value()
                for r in range(self.bundle_table.rowCount()))
        self._thermal_message(
            "<b>Bundle thermal:</b> NEC 310.15(C)(1) adjustment for "
            "{0} conductors = <b>{1:.0%}</b> of each member's free-air "
            "ampacity (compute members on the Single Wire page). A "
            "conduction-resolved bundle interior is a future slice — "
            "the derating factors are the honest tool here.".format(
                n, th.nec_derate(max(n, 1))))

    def _thermal_tp(self):
        self._thermal_message(
            "<b>Twisted pair:</b> analyze each conductor on the Single "
            "Wire page (same current, halved free-air dissipation is a "
            "conservative bound for a tight pair); pair-specific "
            "thermal is a future slice.")

    def _thermal_wirelike(self):
        from emstudio.wire import thermal as th

        self._recalc()                       # always analyze LIVE inputs
        con = getattr(self, "_con", None)
        if con is None:
            self._thermal_message(
                "<b>No valid construction</b> — fix the inputs on this "
                "page first (see the summary pane).")
            return
        i_a = self.th_current.value()
        tamb = self.th_amb.value()
        eps = self.th_eps.value()
        t_lim = th.TEMP_CLASSES[self.th_class.currentText()]
        if t_lim <= tamb:
            self._thermal_message(
                "<b>Ambient {0:.0f} °C is at/above the {1:.0f} °C class "
                "limit</b> — no thermal headroom exists; pick a higher "
                "class or lower ambient.".format(tamb, t_lim))
            return
        d_cond, layers, mat_warns = th.layers_from_construction(con)
        f_hz = self.th_freq.value() * 1e3
        rac = con.ac_factor(f_hz) if f_hz > 0.0 else 1.0
        rdc = con.rdc_per_meter()
        rep = th.solve_steady(i_a, d_cond, layers, rdc, rac_factor=rac,
                              tamb_c=tamb, emissivity=eps)
        if rep["runaway"]:
            self._thermal_message(
                "<span style='color:#c00'><b>THERMAL RUNAWAY</b> at "
                "{0:g} A: {1}</span>".format(i_a, rep["warnings"][0]))
            self._thermal = dict(rep, kind="wire")
            return
        a_cu = con.copper_area_m2()
        amp = th.ampacity(d_cond, layers, rdc, t_lim, rac_factor=rac,
                          tamb_c=tamb, emissivity=eps)
        tr = th.transient(rep, d_cond, a_cond_m2=a_cu)
        hc = th.heating_curve(i_a, d_cond, layers, rdc, rac_factor=rac,
                              tamb_c=tamb, emissivity=eps, a_cond_m2=a_cu,
                              t_limit_c=t_lim,
                              t_end_s=max(6.0 * tr["tau_s"], 30.0))
        s_mm2 = a_cu * 1e6
        i_sc = th.adiabatic_current_a(s_mm2, 1.0, t_lim, 160.0
                                      if t_lim < 150.0 else 250.0)
        self._thermal = dict(rep, kind="wire", ampacity_a=amp["ampacity_a"],
                             tau_s=tr["tau_s"], i_adiabatic_1s_a=i_sc,
                             t_limit_c=t_lim, rac_factor=rac,
                             t_hit_s=hc["t_hit_s"])
        self._draw_thermal_wire(rep, amp, hc, t_lim, i_a, d_cond, layers,
                                rdc, rac, tamb, eps)
        warns = list(mat_warns) + list(rep["warnings"])
        if not layers and eps >= 0.88:
            warns.append(
                "bare conductor with polymer-class ε = {0:.2f}: bright Cu "
                "is ~0.05, oxidized ~0.3-0.8 — set ε for the real surface "
                "state".format(eps))
        warn = "".join("<br><span style='color:#b06000'>⚠ {0}</span>"
                       .format(w) for w in warns)
        self.th_result.setText(
            "<b>{0} @ {1:g} A{2}:</b> conductor <b>{3:.1f} °C</b>, surface "
            "{4:.1f} °C, {5:.2f} W/m (h {6:.1f} W/m²K, Ra {7:.1e}) · "
            "margin to {8:.0f} °C: <b>{9:+.1f} °C</b><br>"
            "<b>Ampacity @ class:</b> {10:.1f} A · small-signal τ "
            "{11:.0f} s · adiabatic 1 s short-circuit {12:.0f} A "
            "({13:.2f} mm² Cu){14}".format(
                con.name or "construction", i_a,
                " (DC)" if rac == 1.0 else
                " ({0:g} kHz, Rac/Rdc {1:.2f})".format(f_hz / 1e3, rac),
                rep["t_conductor_c"], rep["t_surface_c"], rep["q_w_m"],
                rep["h_w_m2k"], rep["ra"], t_lim,
                t_lim - rep["t_conductor_c"], amp["ampacity_a"],
                tr["tau_s"], i_sc, s_mm2, warn))

    def _thermal_coax(self):
        from emstudio.wire import thermal as th

        a_m = self.coax_a.value() * 1e-3 / 2.0
        b_m = self.coax_b.value() * 1e-3 / 2.0
        t_lim = th.TEMP_CLASSES[self.th_class.currentText()]
        tamb = self.th_amb.value()
        if t_lim <= tamb:
            self._thermal_message(
                "<b>Ambient {0:.0f} °C is at/above the {1:.0f} °C class "
                "limit</b> — no thermal headroom exists.".format(tamb,
                                                                 t_lim))
            return
        k_d, k_name, k_j, j_name = th.k_thermal_from_eps_r(
            self.coax_eps.value())
        kwargs = {"eps_r": self.coax_eps.value(),
                  "tan_delta": self.coax_tan.value(),
                  "t_inner_limit_c": t_lim, "k_diel_w_mk": k_d,
                  "jacket_t_m": 1.0e-3, "k_jacket_w_mk": k_j,
                  "tamb_c": tamb, "emissivity": self.th_eps.value()}
        freqs = [10 ** (6 + 0.2 * i) for i in range(19)]   # 1 MHz - 4 GHz
        pmaxs = [th.coax_power_w(f, a_m, b_m, **kwargs) for f in freqs]
        self._thermal = {"kind": "coax", "freqs": freqs,
                         "p_max_w": [p["p_max_w"] for p in pmaxs],
                         "t_limit_c": t_lim}
        self.fig_th.clear()
        ax = self.fig_th.add_subplot(111)
        ax.loglog([f / 1e6 for f in freqs],
                  [p["p_max_w"] for p in pmaxs], "-", linewidth=2)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("matched average power (W)")
        ax.grid(True, which="both", alpha=0.4)
        ax.set_title(
            "RF average-power rating — inner conductor {0:.0f} °C, ambient "
            "{1:.0f} °C\n(smooth-conductor loss → optimistic rating; "
            "validated 90-125% vs LMR-240 w/ datasheet loss)".format(
                t_lim, tamb), fontsize=8)
        self.canvas_th.draw_idle()
        # freqs[15] = 10^(6+3.0) = 1 GHz exactly — the headline reads the
        # SAME curve, no second parameter set to drift
        self.th_result.setText(
            "<b>Coax RF power @ 1 GHz:</b> {0:.0f} W matched (VSWR 1.0, "
            "sea level, still air). Dielectric k: {1}; generic build "
            "assumed — shield OD 1.3×2b, 1 mm {2} jacket (pass a real "
            "build via the API for tighter numbers). Conditions per the "
            "gated LMR-240/Belden anchors.".format(
                pmaxs[15]["p_max_w"], k_name, j_name))

    def _draw_thermal_wire(self, rep, amp, hc, t_lim, i_a, d_cond, layers,
                           rdc, rac, tamb, eps):
        from matplotlib import colors as mcolors
        from matplotlib.cm import ScalarMappable
        from matplotlib.patches import Wedge

        from emstudio.wire import thermal as th

        self.fig_th.clear()
        try:                                   # matplotlib >= 3.6
            from matplotlib import colormaps
            cmap = colormaps["inferno"]
        except ImportError:                    # older bundled matplotlib
            from matplotlib import cm as mcm
            cmap = mcm.get_cmap("inferno")
        norm = mcolors.Normalize(vmin=tamb, vmax=rep["t_conductor_c"])
        mm = 1e3
        # ONE gated sampler feeds both the cross-section coloring and the
        # exterior field — no second copy of the ladder formula in the UI
        fld, _fmeta = th.exterior_field(rep, tamb)

        # (1) cross-section colored by the exact layer temperatures
        ax1 = self.fig_th.add_subplot(221)
        ax1.set_aspect("equal")
        ax1.add_patch(MplCircle((0, 0), d_cond / 2.0 * mm,
                                facecolor=cmap(norm(rep["t_conductor_c"])),
                                edgecolor="none"))
        for name, rho, qv, r_in, r_out, t_k in rep["stack"]:
            for j in range(16):
                r0 = r_in * (r_out / r_in) ** (j / 16.0)
                r1 = r_in * (r_out / r_in) ** ((j + 1) / 16.0)
                ax1.add_patch(Wedge((0, 0), r1 * mm, 0, 360,
                                    width=(r1 - r0) * mm,
                                    facecolor=cmap(norm(
                                        fld(0.5 * (r0 + r1), 0.0))),
                                    edgecolor="none"))
        lim = rep["d_surface_m"] / 2.0 * mm * 1.3
        ax1.set_xlim(-lim, lim)
        ax1.set_ylim(-lim, lim)
        ax1.set_title("cross-section T (°C)", fontsize=8)
        self.fig_th.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax1,
                             fraction=0.046)

        # (2) exterior 2-D field: conduction film hugging the cable + the
        # buoyant plume rising above it (same gated sampler)
        ax2 = self.fig_th.add_subplot(222)
        r_s = rep["d_surface_m"] / 2.0
        nx, nz = 61, 81
        xs = [(-5.0 + 10.0 * i / (nx - 1)) * r_s for i in range(nx)]
        zs = [(-4.0 + 18.0 * j / (nz - 1)) * r_s for j in range(nz)]
        grid = [[fld(x, z) for x in xs] for z in zs]
        ax2.pcolormesh([x * mm for x in xs], [z * mm for z in zs], grid,
                       cmap=cmap, norm=norm, shading="auto")
        n_iso = 6
        levels = [tamb + (rep["t_surface_c"] - tamb) * (k + 1) / (n_iso + 1)
                  for k in range(n_iso)]
        ax2.contour([x * mm for x in xs], [z * mm for z in zs], grid,
                    levels=levels, colors="white", linewidths=0.4,
                    alpha=0.65)
        ax2.add_patch(MplCircle((0, 0), r_s * mm, fill=False,
                                edgecolor="white", lw=1.0))
        ax2.set_aspect("equal")
        ax2.set_xlabel("x (mm)")
        ax2.set_ylabel("z (mm)")
        ax2.set_title(
            "heat dissipation & rise — film + laminar plume\n"
            "(similarity model, still air; illustrative outside the film)",
            fontsize=7)

        # (3) conductor temperature vs current + class limit + rating
        ax3 = self.fig_th.add_subplot(223)
        i_hi = max(amp["ampacity_a"] * 1.25, i_a * 1.1)
        cur = [i_hi * k / 11.0 for k in range(12)]
        tc = []
        for i_c in cur:
            r = th.solve_steady(i_c, d_cond, layers, rdc, rac_factor=rac,
                                tamb_c=tamb, emissivity=eps)
            tc.append(float("nan") if r["runaway"] else r["t_conductor_c"])
        ax3.plot(cur, tc, "-", linewidth=2)
        ax3.axhline(t_lim, color="#c00", lw=1.0, linestyle="--",
                    label="{0:.0f} °C class".format(t_lim))
        ax3.axvline(amp["ampacity_a"], color="#c00", lw=1.0, linestyle=":")
        ax3.plot([i_a], [rep["t_conductor_c"]], "o", ms=6)
        ax3.set_xlabel("I (A)")
        ax3.set_ylabel("conductor T (°C)")
        ax3.set_title("rise vs current — ampacity {0:.1f} A".format(
            amp["ampacity_a"]), fontsize=8)
        ax3.grid(alpha=0.4)
        ax3.legend(fontsize=7)

        # (4) heating trajectory at the set current — the ODE-integrated
        # curve (the small-signal exponential is unsafe at overload: it can
        # undercut even the adiabatic bound)
        ax4 = self.fig_th.add_subplot(224)
        ax4.plot([t / 60.0 for t in hc["times_s"]], hc["temps_c"],
                 "-", linewidth=2)
        ax4.axhline(t_lim, color="#c00", lw=1.0, linestyle="--")
        if hc["t_hit_s"] is not None:
            ax4.axvline(hc["t_hit_s"] / 60.0, color="#c00", lw=1.0,
                        linestyle=":")
            ax4.set_title("heating curve — limit at {0:.1f} min".format(
                hc["t_hit_s"] / 60.0), fontsize=8)
        else:
            ax4.set_title("heating curve (settles {0:.1f} °C)".format(
                hc["t_final_c"]), fontsize=8)
        ax4.set_xlabel("t (min)")
        ax4.set_ylabel("conductor T (°C)")
        ax4.grid(alpha=0.4)
        self.canvas_th.draw_idle()

    # ---------------- full-wave verify (Palace) ----------------
    def _fullwave_params(self):
        """Marshal the coax page into the shipped ``run_coax`` kwargs."""
        n = max(2, int(self.fw_pts.value()))
        f1 = self.fw_f1.value()
        f2 = max(self.fw_f2.value(), f1)
        return {
            "a_mm": self.coax_a.value() / 2.0,
            "b_mm": self.coax_b.value() / 2.0,
            "length_mm": self.fw_len.value(),
            "f1_ghz": f1,
            "f2_ghz": f2,
            "step_ghz": (f2 - f1) / (n - 1) if f2 > f1 else 0.5,
            "eps_r": self.coax_eps.value(),
            "loss_tan": self.coax_tan.value(),
        }

    def _fullwave_verify(self):
        params = self._fullwave_params()
        if params["a_mm"] >= params["b_mm"]:
            QtWidgets.QMessageBox.warning(
                self, "EMStudio", "Dielectric Ø (2b) must exceed inner Ø (2a).")
            return

        def run_fn(a, s, cb):
            from emstudio.solvers.palace import run_coax

            return run_coax(line_callback=cb, **params)

        from emstudio.ui import run_gui

        run_gui.run_generic_gui(
            "Full-wave verify (Palace, {0:g}-{1:g} GHz)".format(
                params["f1_ghz"], params["f2_ghz"]),
            run_fn, lambda res: self._show_fullwave(res, params), parent=self)

    def _fullwave_message(self, result, params):
        """Pure formatter for the verify read-out (headlessly testable)."""
        from emstudio.wire import coax

        s11 = np.asarray(result.s11)
        s21 = np.asarray(result.s_others.get((2, 1)))
        worst_s11_db = 20.0 * math.log10(max(float(np.abs(s11).max()), 1e-12))
        vf_an = coax.velocity_factor(params["eps_r"])
        msg = [
            "Full-wave (Palace lumped-port) vs analytic TEM:",
            "",
            "Port reference Z0 (analytic): {0:.2f} Ω".format(result.z0),
            "Matched-line check: worst |S11| = {0:.1f} dB over the sweep".format(
                worst_s11_db),
        ]
        # VF from the S21 phase at the LOWEST frequency (least wrap risk)
        f0 = float(np.asarray(result.freq)[0])
        length_m = params["length_mm"] * 1e-3
        ph = float(np.angle(s21[0]))
        if ph < 0.0:
            vf_fw = 2.0 * math.pi * f0 * length_m / (coax.C0 * (-ph))
            msg.append(
                "S21 phase @ {0:.2f} GHz → full-wave VF = {1:.4f} "
                "(analytic 1/√εr = {2:.4f}, Δ {3:+.2%})".format(
                    f0 / 1e9, vf_fw, vf_an, (vf_fw - vf_an) / vf_an))
        else:
            msg.append(
                "S21 phase wrapped at f start (line ≥ λ/2) — shorten the line "
                "or lower f start for a VF read-out.")
        msg += [
            "",
            "solve time: {0:.1f} s".format(result.meta.get("duration_s", -1.0)),
            "workdir: {0}".format(result.meta.get("workdir", "?")),
        ]
        return "\n".join(msg)

    def _show_fullwave(self, result, params):
        QtWidgets.QMessageBox.information(
            self, "EMStudio — Full-wave verify", self._fullwave_message(result, params))

    # ---------------- exports / reports ----------------
    def _export_cad(self):
        try:
            from emstudio.wire import cross_section

            obj = cross_section.export_to_freecad(
                self._con, detail=self.detail_combo.currentData()
            )
            QtWidgets.QMessageBox.information(
                self, "EMStudio",
                "Created '{0}' ({1} edges).\n\nUse it as the profile for Part → "
                "Sweep/Loft along your coil path (e.g. a helix).".format(
                    obj.Label, len(obj.Shape.Edges)
                ),
            )
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "EMStudio", "Export failed: {0}".format(exc))

    def _export_spec(self):
        kind = self.construction.currentData()
        if kind == "coax":
            text = getattr(self, "_coax_spec", "")
            default = "~/coax_spec.md"
        elif kind == "tp":
            text = getattr(self, "_tp_spec", "")
            default = "~/twisted_pair_spec.md"
        elif kind == "bundle":
            text = getattr(self, "_bundle_spec", "")
            default = "~/bundle_spec.md"
        else:
            text = self._con.spec_markdown()
            default = "~/litz_spec.md" if kind == "litz" else "~/wire_spec.md"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save construction spec",
            os.path.expanduser(default), "Markdown (*.md);;All files (*)",
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            QtWidgets.QMessageBox.information(self, "EMStudio", "Saved " + path)

    def _pdf_report(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDF report", os.path.expanduser("~/litz_report.pdf"),
            "PDF (*.pdf)",
        )
        if not path:
            return
        try:
            from emstudio.report import litz_report

            litz_report(self._con, path,
                        freq_min_hz=self.fmin.value() * 1e3,
                        freq_max_hz=self.fmax.value() * 1e3,
                        h_ext_per_amp=self.h_ext.value())
            QtWidgets.QMessageBox.information(self, "EMStudio", "Saved report:\n" + path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "EMStudio", "Report failed: {0}".format(exc))

    def _current_sharing(self):
        from emstudio.wire import current_sharing

        con = self._con
        if len(con.ops) < 1 or con.ops[-1].count < 2:
            QtWidgets.QMessageBox.information(
                self, "EMStudio", "Current sharing needs a cabled construction "
                "(2+ members in the final operation).")
            return
        f = self.fmax.value() * 1e3

        def run_fn(a, s, cb):
            res = current_sharing.analyze_construction(con, fmin=f, fmax=f, ndec=1,
                                                       line_callback=cb)
            return res[0]

        from emstudio.ui import run_gui

        run_gui.run_generic_gui(
            "Current sharing ({0} members)".format(con.ops[-1].count), run_fn,
            self._show_sharing, parent=self)

    def _show_sharing(self, res):
        norm = res["normalized"]
        msg = ["Per-bundle current sharing at the final cabling level:", ""]
        msg.append("Imbalance (max/min): {0:.3f}   (1.0 = perfect)".format(res["imbalance"]))
        msg.append("Relative spread: {0:.1%}".format(res["spread"]))
        msg.append("")
        for i, nv in enumerate(norm):
            bar = "#" * max(1, int(round(nv * 20)))
            msg.append("bundle {0:2d}: {1:.3f}  {2}".format(i + 1, nv, bar))
        QtWidgets.QMessageBox.information(self, "EMStudio — Current Sharing", "\n".join(msg))


# back-compat: the pre-v0.37 dialog name (the Litz Designer became the Cable Designer)
LitzDesignerDialog = CableDesignerDialog
