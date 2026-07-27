# SPDX-License-Identifier: LGPL-2.1-or-later
"""Area coverage map dialog (ROADMAP §6, phase B).

Place a transmitter (lat/lon, height, frequency, power, antenna gain), optionally
load a DEM (SRTM .hgt or GeoTIFF) for terrain shadowing and/or an antenna pattern
(a FarFieldResult CSV exported from a NEC2/openEMS solve), and compute the
received-power / field-strength footprint over a grid. Export the result to a
Google-Earth KML GroundOverlay.

Thin view over the Qt-free engine in ``emstudio.coverage`` (``geodesy`` /
``terrain`` / ``pattern`` / ``heatmap`` / ``kml``), gated by
``tests/validation/coverage.py``. Transmitter location is user-supplied; no
specific sites are referenced.
"""

from __future__ import annotations

from PySide import QtGui, QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


class CoverageDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio — Area Coverage Map")
        self.resize(1080, 720)
        self._result = None

        root = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()

        # ---- transmitter ----
        tx = QtWidgets.QGroupBox("Transmitter")
        tf = QtWidgets.QFormLayout(tx)
        self.lat = self._spin(tf, "Latitude", 40.0, " deg", -90, 90, 6)
        self.lon = self._spin(tf, "Longitude", -100.0, " deg", -180, 180, 6)
        self.tx_h = self._spin(tf, "TX height", 30.0, " m", 0.1, 5000, 2)
        frow = QtWidgets.QHBoxLayout()
        self.freq = QtWidgets.QDoubleSpinBox()
        self.freq.setDecimals(4)
        self.freq.setRange(0.0001, 1e6)
        self.freq.setValue(100.0)
        self.freq_unit = QtWidgets.QComboBox()
        self.freq_unit.addItems(["kHz", "MHz", "GHz"])
        self.freq_unit.setCurrentText("MHz")
        frow.addWidget(self.freq, 1)
        frow.addWidget(self.freq_unit)
        tf.addRow("Frequency", frow)
        self.tx_power = self._spin(tf, "TX power", 50.0, " dBm", -30, 90, 2)
        self.peak_gain = self._spin(tf, "Peak gain", 2.15, " dBi", -20, 60, 2)
        left.addWidget(tx)

        # ---- coverage grid ----
        cov = QtWidgets.QGroupBox("Coverage")
        cf = QtWidgets.QFormLayout(cov)
        self.radius = self._spin(cf, "Radius", 30.0, " km", 0.1, 2000, 2)
        self.grid_n = QtWidgets.QSpinBox()
        self.grid_n.setRange(11, 301)
        self.grid_n.setValue(61)
        self.grid_n.setToolTip("Grid points per side. Larger = finer + slower "
                               "(especially with a DEM).")
        cf.addRow("Grid points", self.grid_n)
        self.rx_h = self._spin(cf, "RX height", 2.0, " m", 0.1, 5000, 2)
        self.pmodel = QtWidgets.QComboBox()
        self.pmodel.addItems(["Auto (free-space / plane-earth)",
                              "Ground-wave flat earth (LF/MF, P.368, <100 km)",
                              "Ground-wave spherical (ITU-R P.368-10)",
                              "Hata / COST-231 (150 MHz-2 GHz)"])
        self.pmodel.setToolTip(
            "Auto: free-space, switching to two-ray plane-earth beyond the "
            "breakpoint (terrain-aware if a DEM is loaded).\nGround-wave flat "
            "earth: the Norton LF/MF surface wave over homogeneous ground "
            "(smooth earth, valid to ~100 km; the DEM and antenna heights are "
            "not used).\nGround-wave spherical: the ITU-R P.368-10 reference "
            "model (flat-earth Sommerfeld switching to the Wait/Hufford "
            "residue series) — 0.01-30 MHz, out to 10000 km; below 10 kHz it "
            "refuses (ionospheric, P.684 territory).\nHata / "
            "COST-231: the empirical land-mobile clutter model over the chosen "
            "environment (150-1500 MHz Okumura-Hata, 1500-2000 MHz COST-231; "
            "macro-cells, d 1-20 km; DEM ignored).")
        self.pmodel.currentIndexChanged.connect(self._model_changed)
        cf.addRow("Propagation model", self.pmodel)
        self.environment = QtWidgets.QComboBox()
        self.environment.addItems(["Urban (small/medium city)",
                                   "Urban (large/metropolitan)",
                                   "Suburban", "Open / rural"])
        self.environment.setEnabled(False)
        self.environment.setToolTip("Hata clutter category (the environment IS the "
                                    "clutter model: urban > suburban > open loss).")
        cf.addRow("Environment", self.environment)
        self.ground = QtWidgets.QComboBox()
        from emstudio.coverage import groundwave as _gw
        for name in _gw.GROUND_TYPES:
            self.ground.addItem(name)
        self.ground.setCurrentText("Average ground")
        self.ground.setEnabled(False)
        self.ground.setToolTip("Ground electrical type (ITU-R P.368 Table 2) for the "
                               "ground-wave model: sea water propagates farthest, dry "
                               "ground least.")
        cf.addRow("Ground type", self.ground)
        self.metric_combo = QtWidgets.QComboBox()
        self.metric_combo.addItems(["Received power (dBm)", "Field strength (dBuV/m)"])
        cf.addRow("Metric", self.metric_combo)
        self.threshold = self._spin(cf, "Coverage threshold", -100.0, "", -200, 200, 1)
        self.threshold.setToolTip("Cells at/above this (in the chosen metric) count "
                                  "as covered and are drawn; below is transparent.")
        self.kfactor = self._spin(cf, "Earth k-factor", 1.333, "", 0.1, 1e6, 3)
        self.kfactor.setToolTip("Effective-earth-radius factor (4/3 standard "
                                "atmosphere). Large value = flat earth.")
        left.addWidget(cov)

        # ---- terrain ----
        ter = QtWidgets.QGroupBox("Terrain (optional)")
        tl = QtWidgets.QVBoxLayout(ter)
        drow = QtWidgets.QHBoxLayout()
        self.dem_path = QtWidgets.QLineEdit()
        self.dem_path.setPlaceholderText("SRTM .hgt / GeoTIFF file or folder — "
                                         "empty = smooth earth")
        dbtn = QtWidgets.QPushButton("Browse…")
        dbtn.clicked.connect(self._browse_dem)
        drow.addWidget(self.dem_path, 1)
        drow.addWidget(dbtn)
        tl.addLayout(drow)
        drow2 = QtWidgets.QHBoxLayout()
        drow2.addWidget(QtWidgets.QLabel("Diffraction:"))
        self.diffraction = QtWidgets.QComboBox()
        self.diffraction.addItems(["Single-edge (Deygout)", "Multi-edge (Deygout)",
                                   "Multi-edge (Deygout + Causebrook)",
                                   "Multi-edge (Epstein-Peterson)",
                                   "Bullington (equivalent edge)"])
        self.diffraction.setToolTip(
            "Terrain diffraction method — only used with a DEM. Single-edge = the "
            "dominant obstacle only (fast); the multi-edge Deygout / Epstein-"
            "Peterson methods add the secondary ridges a single edge misses; "
            "Bullington folds all edges into one equivalent edge (optimistic). "
            "All validated vs NTIA TR-26-580.")
        drow2.addWidget(self.diffraction, 1)
        tl.addLayout(drow2)
        self.ground_refl = QtWidgets.QCheckBox(
            "Two-ray plane-earth on clear paths")
        self.ground_refl.setToolTip(
            "With a DEM: on unobstructed paths beyond the breakpoint, also apply "
            "the two-ray plane-earth (d^4) loss the smooth-earth mode carries — a "
            "flat DEM then matches the no-DEM footprint exactly.")
        tl.addWidget(self.ground_refl)
        left.addWidget(ter)

        # ---- antenna pattern ----
        pat = QtWidgets.QGroupBox("Antenna pattern (optional)")
        pl = QtWidgets.QFormLayout(pat)
        self.pattern_mode = QtWidgets.QComboBox()
        self.pattern_mode.addItems(["Omni (peak gain)", "From pattern CSV"])
        self.pattern_mode.currentIndexChanged.connect(self._pattern_mode_changed)
        pl.addRow("Source", self.pattern_mode)
        prow = QtWidgets.QHBoxLayout()
        self.pattern_path = QtWidgets.QLineEdit()
        self.pattern_path.setPlaceholderText("FarField pattern CSV from an antenna solve")
        self.pattern_path.setEnabled(False)
        pbtn = QtWidgets.QPushButton("Browse…")
        pbtn.clicked.connect(self._browse_pattern)
        prow.addWidget(self.pattern_path, 1)
        prow.addWidget(pbtn)
        pl.addRow("CSV", prow)
        self.pat_elev = self._spin(pl, "Take-off elevation", 0.0, " deg", -90, 90, 1)
        self.pat_orient = self._spin(pl, "Orientation (bearing)", 0.0, " deg", 0, 360, 1)
        left.addWidget(pat)

        arow = QtWidgets.QHBoxLayout()
        self.compute_btn = QtWidgets.QPushButton("Compute coverage")
        self.compute_btn.clicked.connect(self._compute)
        self.export_btn = QtWidgets.QPushButton("Export KML…")
        self.export_btn.clicked.connect(self._export_kml)
        self.export_btn.setEnabled(False)
        arow.addWidget(self.compute_btn)
        arow.addWidget(self.export_btn)
        left.addLayout(arow)
        left.addStretch(1)
        root.addLayout(left, 0)

        # ---- right: map + readout ----
        right = QtWidgets.QVBoxLayout()
        self.fig = Figure(figsize=(6, 6), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        right.addWidget(self.canvas, 1)
        self.readout = QtWidgets.QPlainTextEdit()
        self.readout.setReadOnly(True)
        self.readout.setFont(QtGui.QFont("Monospace"))
        self.readout.setMaximumHeight(120)
        right.addWidget(self.readout, 0)
        root.addLayout(right, 1)

        self._compute()

    # ---------------- helpers ----------------
    def _spin(self, form, label, value, suffix, lo, hi, decimals=3):
        s = QtWidgets.QDoubleSpinBox()
        s.setDecimals(decimals)
        s.setRange(lo, hi)
        s.setValue(value)
        if suffix:
            s.setSuffix(suffix)
        form.addRow(label, s)
        return s

    def _freq_hz(self):
        mult = {"kHz": 1e3, "MHz": 1e6, "GHz": 1e9}[self.freq_unit.currentText()]
        return self.freq.value() * mult

    def _metric_key(self):
        return "field" if self.metric_combo.currentIndex() == 1 else "prx"

    def _diffraction_key(self):
        return ["single", "deygout", "deygout_causebrook", "epstein_peterson",
                "bullington"][self.diffraction.currentIndex()]

    def _pattern_mode_changed(self):
        self.pattern_path.setEnabled(self.pattern_mode.currentIndex() == 1)

    def _model_changed(self):
        ground_wave = self.pmodel.currentIndex() in (1, 2)
        self.ground.setEnabled(ground_wave)
        self.environment.setEnabled(self.pmodel.currentIndex() == 3)
        # field strength is the natural ground-wave output; heights/DEM are unused
        if ground_wave:
            self.metric_combo.setCurrentIndex(1)

    def _browse_dem(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select a DEM file (.hgt / .tif)", "",
            "DEM (*.hgt *.tif *.tiff);;All files (*)")
        if path:
            self.dem_path.setText(path)

    def _browse_pattern(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select a far-field pattern CSV", "", "CSV (*.csv);;All files (*)")
        if path:
            self.pattern_path.setText(path)

    def _load_dem(self):
        path = self.dem_path.text().strip()
        if not path:
            return None
        from emstudio.coverage import terrain
        return terrain.DEM.load(path)

    def _load_pattern(self):
        from emstudio.coverage import pattern as pat_mod

        if self.pattern_mode.currentIndex() != 1:
            return pat_mod.omni(self.peak_gain.value())
        path = self.pattern_path.text().strip()
        if not path:
            return pat_mod.omni(self.peak_gain.value())
        from emstudio.post.farfield import FarFieldResult
        ff = FarFieldResult.load_csv(path)
        return pat_mod.AzimuthPattern.from_farfield(
            ff, elevation_deg=self.pat_elev.value(),
            orientation_deg=self.pat_orient.value())

    # ---------------- compute + draw ----------------
    def _compute(self):
        from emstudio.coverage import groundwave, heatmap

        model = ["auto", "ground_wave", "ground_wave", "hata"][
            self.pmodel.currentIndex()]
        gw_engine = "p368" if self.pmodel.currentIndex() == 2 else "flat"
        ground = groundwave.GROUND_TYPES.get(self.ground.currentText())
        environment = ["urban", "urban_large", "suburban", "open"][
            self.environment.currentIndex()]
        # ground-wave and Hata are smooth-earth/clutter models — ignore any loaded
        # DEM so we don't imply terrain-aware behaviour they don't have
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtGui.Qt.WaitCursor))
        try:
            dem = self._load_dem() if model == "auto" else None
            pattern = self._load_pattern()
            self._result = heatmap.coverage_grid(
                self.lat.value(), self.lon.value(), self.tx_h.value(),
                self._freq_hz(), self.tx_power.value(), dem=dem,
                radius_m=self.radius.value() * 1e3, n=self.grid_n.value(),
                pattern=pattern, peak_gain_dbi=self.peak_gain.value(),
                rx_height_m=self.rx_h.value(), k_factor=self.kfactor.value(),
                model=model, ground=ground, diffraction=self._diffraction_key(),
                ground_reflection=self.ground_refl.isChecked(),
                environment=environment, gw_engine=gw_engine)
        except Exception as exc:  # noqa: BLE001 — surface to the user
            QtWidgets.QApplication.restoreOverrideCursor()
            self.readout.setPlainText("Coverage failed: {0}".format(exc))
            self.export_btn.setEnabled(False)
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        self.export_btn.setEnabled(True)
        self._draw()
        self._summarize()

    def _draw(self):
        res = self._result
        metric = self._metric_key()
        g = np.ma.masked_invalid(res.grid(metric))
        thr = self.threshold.value()
        g = np.ma.masked_less(g, thr)
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        extent = [float(res.lons.min()), float(res.lons.max()),
                  float(res.lats.min()), float(res.lats.max())]
        cmap = matplotlib.cm.get_cmap("jet").copy()
        cmap.set_bad(alpha=0.0)
        im = ax.imshow(g, origin="lower", extent=extent, cmap=cmap,
                       aspect="auto", interpolation="bilinear")
        ax.plot([res.meta["tx_lon"]], [res.meta["tx_lat"]], "kv", ms=9,
                markerfacecolor="white", label="TX")
        cbar = self.fig.colorbar(im, ax=ax, shrink=0.85)
        cbar.set_label("Prx (dBm)" if metric == "prx" else "E (dBuV/m)", fontsize=8)
        ax.set_xlabel("Longitude (deg)", fontsize=8)
        ax.set_ylabel("Latitude (deg)", fontsize=8)
        if res.meta.get("model") == "ground_wave":
            tag = "  (ground-wave {0}, {1})".format(
                "P.368-10 spherical" if res.meta.get("gw_engine") == "p368"
                else "flat earth", self.ground.currentText())
        elif res.meta.get("model") == "hata":
            tag = "  (Hata, {0})".format(self.environment.currentText())
        elif res.meta["has_dem"]:
            tag = "  (terrain)"
        else:
            tag = ""
        ttl = "Coverage @ {0:.4g} MHz{1}".format(self._freq_hz() / 1e6, tag)
        ax.set_title(ttl, fontsize=9)
        ax.tick_params(labelsize=7)
        self.canvas.draw_idle()

    def _summarize(self):
        res = self._result
        metric = self._metric_key()
        g = res.grid(metric)
        valid = ~np.isnan(g)
        thr = self.threshold.value()
        frac = res.coverage_fraction(thr, metric)
        unit = "dBm" if metric == "prx" else "dBuV/m"
        peak = float(np.nanmax(g)) if valid.any() else float("nan")
        erp_w = 10.0 ** ((res.meta["tx_power_dbm"] + res.meta["peak_gain_dbi"]
                          - 30.0) / 10.0)
        L = [
            "AREA COVERAGE",
            "  frequency   : {0:.4g} MHz".format(self._freq_hz() / 1e6),
            "  peak ERP    : {0:.4g} W  ({1:.1f} dBm + {2:.1f} dBi)".format(
                erp_w, res.meta["tx_power_dbm"], res.meta["peak_gain_dbi"]),
            "  model       : {0}".format(
                "ground-wave ({0}, {1})".format(
                    "P.368-10 spherical"
                    if res.meta.get("gw_engine") == "p368" else "P.368 flat",
                    self.ground.currentText())
                if res.meta.get("model") == "ground_wave"
                else "Hata/COST-231 ({0})".format(self.environment.currentText())
                if res.meta.get("model") == "hata"
                else ("terrain DEM" if res.meta["has_dem"]
                      else "free-space / plane-earth")),
            "  radius      : {0:.3g} km, {1}x{1} grid".format(
                res.meta["radius_m"] / 1e3, res.meta["n"]),
            "  peak {0:<7}: {1:.1f} {0}".format(unit, peak),
            "  covered     : {0:.0%} of area >= {1:g} {2}".format(frac, thr, unit),
        ]
        self.readout.setPlainText("\n".join(L))

    def _export_kml(self):
        from emstudio.coverage import kml

        if self._result is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export coverage to KML", "coverage.kml", "KML (*.kml)")
        if not path:
            return
        try:
            kml_path, png_path = kml.export_coverage_kml(
                self._result, path, metric=self._metric_key(),
                threshold=self.threshold.value())
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "EMStudio — export failed", str(exc))
            return
        QtWidgets.QMessageBox.information(
            self, "EMStudio",
            "Coverage exported:\n{0}\n{1}\n\nOpen the .kml in Google Earth / QGIS."
            .format(kml_path, png_path))
