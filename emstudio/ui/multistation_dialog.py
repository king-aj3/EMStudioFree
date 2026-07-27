# SPDX-License-Identifier: LGPL-2.1-or-later
"""Multi-station service & interference (D/U) contour dialog (ROADMAP §6, phase C).

Enter two or more co-channel transmitters (label, lat/lon, height, frequency,
power, antenna gain), pick a wanted station, an FCC/ITU protection ratio and a
protected-service field threshold, and get the composite map: where the wanted
station is SERVED (interference-free), INTERFERENCE-LIMITED, or has NO SERVICE, plus
the raw D/U-ratio and per-station field grids and a network best-server view. Export
any layer to a Google-Earth KML.

Thin view over the Qt-free engine in :mod:`emstudio.coverage.multistation` (gated by
``tests/validation/coverage.py``), which composes the shipped single-station
``heatmap.coverage_grid`` footprints and reuses the §5 co-site D/U logic. Station
locations / frequencies / ground are user-supplied; no specific sites referenced.
"""

from __future__ import annotations

from PySide import QtGui, QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

_COLS = ["Label", "Lat (deg)", "Lon (deg)", "Height (m)", "Freq (MHz)",
         "Power (dBm)", "Gain (dBi)"]
# a co-channel MF pair ~30 km apart (generic coords — no site names)
_DEFAULT_ROWS = [
    ["Wanted", "40.0000", "-100.0000", "100", "1.0", "70", "0"],
    ["Interferer", "40.0000", "-99.6500", "100", "1.0", "70", "0"],
]

_METRICS = ["Service (classified)", "D/U ratio (dB)", "Wanted field (dBuV/m)",
            "Interference field (dBuV/m)", "Best server (network)"]


class MultiStationDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EMStudio — Multi-Station Service / Interference (D/U)")
        self.resize(1160, 760)
        self._result = None
        self._bs = None

        root = QtWidgets.QHBoxLayout(self)

        # ================= left: station table + params =================
        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel("Co-channel transmitters:"))
        self.table = QtWidgets.QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row in _DEFAULT_ROWS:
            self._add_row(row)
        left.addWidget(self.table, 1)

        row_btns = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("+ station")
        del_btn = QtWidgets.QPushButton("− station")
        add_btn.clicked.connect(lambda: self._add_row())
        del_btn.clicked.connect(self._del_row)
        row_btns.addWidget(add_btn)
        row_btns.addWidget(del_btn)
        row_btns.addStretch(1)
        left.addLayout(row_btns)

        # ---- wanted + protection ----
        svc = QtWidgets.QGroupBox("Service / protection")
        sf = QtWidgets.QFormLayout(svc)
        self.wanted = QtWidgets.QComboBox()
        self.wanted.setToolTip("The desired station; the map centres on it and its "
                               "service area is what is protected. (Ignored for the "
                               "network best-server metric.)")
        sf.addRow("Wanted station", self.wanted)

        from emstudio.coverage import multistation as _ms
        self.prot_preset = QtWidgets.QComboBox()
        self.prot_preset.addItem("Custom")
        for name in _ms.PROTECTION_RATIOS:
            self.prot_preset.addItem(name)
        self.prot_preset.currentIndexChanged.connect(self._prot_preset_changed)
        sf.addRow("Protection preset", self.prot_preset)
        self.prot = self._spin(sf, "Protection ratio", 26.0, " dB", -100, 100, 2)
        self.prot.setToolTip("Required D/U (wanted − unwanted). May be negative for "
                             "adjacent-channel cases (receiver selectivity).")

        self.svc_preset = QtWidgets.QComboBox()
        self.svc_preset.addItem("Custom")
        for name in _ms.SERVICE_THRESHOLDS_DBUV_M:
            self.svc_preset.addItem(name)
        self.svc_preset.currentIndexChanged.connect(self._svc_preset_changed)
        sf.addRow("Service preset", self.svc_preset)
        self.service = self._spin(sf, "Service threshold", 54.0, " dBuV/m",
                                  -50, 200, 2)
        self.service.setToolTip("Gate A: the wanted field must reach this protected "
                                "field strength to count as covered.")
        self.combine = QtWidgets.QComboBox()
        self.combine.addItems(["Power sum (RSS)", "Worst case (strongest)"])
        self.combine.setToolTip("How co-channel interferers are aggregated into one "
                                "unwanted field. Power sum = 10log10(Σ10^(E/10)) "
                                "(ITU-R BT.2265); worst case = the single strongest "
                                "(FCC OET-69 DTV).")
        sf.addRow("Interferer combine", self.combine)
        left.addWidget(svc)

        # ---- propagation / grid ----
        prop = QtWidgets.QGroupBox("Propagation & grid")
        pf = QtWidgets.QFormLayout(prop)
        self.pmodel = QtWidgets.QComboBox()
        self.pmodel.addItems(["Ground-wave flat earth (LF/MF, P.368, <100 km)",
                              "Ground-wave spherical (ITU-R P.368-10)",
                              "Auto (free-space / plane-earth)"])
        self.pmodel.currentIndexChanged.connect(self._model_changed)
        pf.addRow("Propagation model", self.pmodel)
        self.ground = QtWidgets.QComboBox()
        from emstudio.coverage import groundwave as _gw
        for name in _gw.GROUND_TYPES:
            self.ground.addItem(name)
        self.ground.setCurrentText("Average ground")
        pf.addRow("Ground type", self.ground)
        self.metric_combo = QtWidgets.QComboBox()
        self.metric_combo.addItems(_METRICS)
        pf.addRow("Display", self.metric_combo)
        self.radius = self._spin(pf, "Radius", 60.0, " km", 0.1, 4000, 2)
        self.grid_n = QtWidgets.QSpinBox()
        self.grid_n.setRange(11, 301)
        self.grid_n.setValue(61)
        self.grid_n.setToolTip("Grid points per side (each station is solved on this "
                               "shared grid, so cost scales with stations × n²).")
        pf.addRow("Grid points", self.grid_n)
        self.kfactor = self._spin(pf, "Earth k-factor", 1.333, "", 0.1, 1e6, 3)
        left.addWidget(prop)

        arow = QtWidgets.QHBoxLayout()
        self.compute_btn = QtWidgets.QPushButton("Compute contours")
        self.compute_btn.clicked.connect(self._compute)
        self.export_btn = QtWidgets.QPushButton("Export KML…")
        self.export_btn.clicked.connect(self._export_kml)
        self.export_btn.setEnabled(False)
        arow.addWidget(self.compute_btn)
        arow.addWidget(self.export_btn)
        left.addLayout(arow)
        root.addLayout(left, 0)

        # ================= right: map + readout =================
        right = QtWidgets.QVBoxLayout()
        self.fig = Figure(figsize=(6.2, 6.2), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        right.addWidget(self.canvas, 1)
        self.readout = QtWidgets.QPlainTextEdit()
        self.readout.setReadOnly(True)
        self.readout.setFont(QtGui.QFont("Monospace"))
        self.readout.setMaximumHeight(150)
        right.addWidget(self.readout, 0)
        root.addLayout(right, 1)

        self._model_changed()
        self._refresh_wanted()
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

    def _add_row(self, values=None):
        r = self.table.rowCount()
        self.table.insertRow(r)
        values = values or ["Station-{0}".format(r + 1), "40.0", "-100.0", "30",
                            "1.0", "60", "0"]
        for c, v in enumerate(values):
            self.table.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))
        self._refresh_wanted()

    def _del_row(self):
        if self.table.rowCount() > 1:
            self.table.removeRow(self.table.rowCount() - 1)
            self._refresh_wanted()

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

    def _refresh_wanted(self):
        """Keep the wanted-station combo in sync with the table labels."""
        if not hasattr(self, "wanted"):
            return
        cur = self.wanted.currentIndex()
        self.wanted.blockSignals(True)
        self.wanted.clear()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            label = item.text().strip() if item else ""
            self.wanted.addItem(label or "Station-{0}".format(r + 1))
        if 0 <= cur < self.wanted.count():
            self.wanted.setCurrentIndex(cur)
        self.wanted.blockSignals(False)

    def _stations(self):
        from emstudio.coverage.multistation import Station

        stations = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            label = (item.text().strip() if item else "") or "Station-{0}".format(r + 1)
            stations.append(Station(
                label=label,
                lat=self._cell(r, 1, 40.0),
                lon=self._cell(r, 2, -100.0),
                height_m=self._cell(r, 3, 30.0),
                freq_hz=self._cell(r, 4, 1.0) * 1e6,
                power_dbm=self._cell(r, 5, 60.0),
                peak_gain_dbi=self._cell(r, 6, 0.0),
            ))
        return stations

    def _prot_preset_changed(self):
        from emstudio.coverage.multistation import PROTECTION_RATIOS

        name = self.prot_preset.currentText()
        if name in PROTECTION_RATIOS:
            self.prot.setValue(PROTECTION_RATIOS[name][0])

    def _svc_preset_changed(self):
        from emstudio.coverage.multistation import SERVICE_THRESHOLDS_DBUV_M

        name = self.svc_preset.currentText()
        if name in SERVICE_THRESHOLDS_DBUV_M:
            self.service.setValue(SERVICE_THRESHOLDS_DBUV_M[name][0])

    def _model_changed(self):
        self.ground.setEnabled(self.pmodel.currentIndex() in (0, 1))

    def _model_key(self):
        return ("ground_wave" if self.pmodel.currentIndex() in (0, 1)
                else "auto")

    def _gw_engine_key(self):
        return "p368" if self.pmodel.currentIndex() == 1 else "flat"

    def _metric_key(self):
        idx = self.metric_combo.currentIndex()
        return ["class", "du", "wanted", "unwanted", "best"][idx]

    # ---------------- compute + draw ----------------
    def _compute(self):
        from emstudio.coverage import groundwave, multistation as ms

        stations = self._stations()
        if len(stations) < 1:
            self.readout.setPlainText("Add at least one station.")
            return
        ground = groundwave.GROUND_TYPES.get(self.ground.currentText())
        combine = "worst_case" if self.combine.currentIndex() == 1 else "power_sum"
        kw = dict(radius_m=self.radius.value() * 1e3, n=self.grid_n.value(),
                  protection_ratio_db=self.prot.value(),
                  service_threshold_dbuv_m=self.service.value(),
                  combine=combine, model=self._model_key(), ground=ground,
                  k_factor=self.kfactor.value(),
                  gw_engine=self._gw_engine_key())
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtGui.Qt.WaitCursor))
        try:
            wanted = max(0, min(self.wanted.currentIndex(), len(stations) - 1))
            self._result = ms.service_contour(stations, wanted=wanted, **kw)
            if self._metric_key() == "best":
                bkw = dict(kw)
                bkw.pop("combine", None)
                self._bs = ms.best_server(stations, **bkw)
            else:
                self._bs = None
        except Exception as exc:  # noqa: BLE001 — surface to the user
            QtWidgets.QApplication.restoreOverrideCursor()
            self.readout.setPlainText("Contour computation failed: {0}".format(exc))
            self.export_btn.setEnabled(False)
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        self.export_btn.setEnabled(True)
        self._draw()
        self._summarize()

    def _extent(self, lats, lons):
        return [float(lons.min()), float(lons.max()),
                float(lats.min()), float(lats.max())]

    def _plot_stations(self, ax):
        res = self._result
        labels = res.meta["station_labels"]
        latlon = res.meta["station_latlon"]
        wi = res.meta.get("wanted", -1)
        for i, (la, lo) in enumerate(latlon):
            wanted = (i == wi)
            ax.plot([lo], [la], "*" if wanted else "v", ms=13 if wanted else 8,
                    markerfacecolor="white",
                    markeredgecolor="k" if wanted else "#333")
            ax.annotate(labels[i], (lo, la), fontsize=7, ha="center",
                        va="bottom", xytext=(0, 6), textcoords="offset points")

    def _draw(self):
        res = self._result
        metric = self._metric_key()
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        if metric == "best" and self._bs is not None:
            self._draw_best(ax)
        elif metric == "class":
            self._draw_class(ax)
        elif metric == "du":
            self._draw_du(ax)
        else:  # wanted / unwanted field
            self._draw_field(ax, metric)

        ax.set_xlabel("Longitude (deg)", fontsize=8)
        ax.set_ylabel("Latitude (deg)", fontsize=8)
        ax.tick_params(labelsize=7)
        self.canvas.draw_idle()

    def _draw_class(self, ax):
        res = self._result
        extent = self._extent(res.lats, res.lons)
        # 0 no-service (transparent), 1 interference-limited (red), 2 served (green)
        cmap = ListedColormap([(0, 0, 0, 0), "#d94040", "#2ca25f"])
        norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)
        ax.imshow(res.classification, origin="lower", extent=extent, cmap=cmap,
                  norm=norm, aspect="auto", interpolation="nearest")
        self._plot_stations(ax)
        served = res.fraction()
        ax.set_title("Service — green=served, red=interference-limited "
                     "({0:.0%} served)".format(served), fontsize=9)

    def _draw_du(self, ax):
        res = self._result
        extent = self._extent(res.lats, res.lons)
        g = np.ma.masked_invalid(res.du_db)
        prot = res.meta["protection_ratio_db"]
        finite = g.compressed()
        if finite.size:
            lo, hi = float(np.percentile(finite, 2)), float(np.percentile(finite, 98))
        else:
            lo, hi = prot - 20, prot + 20
        lo = min(lo, prot - 1.0)
        hi = max(hi, prot + 1.0)
        cmap = matplotlib.cm.get_cmap("RdYlGn").copy()
        cmap.set_bad(alpha=0.0)
        try:
            norm = TwoSlopeNorm(vmin=lo, vcenter=prot, vmax=hi)
        except Exception:  # degenerate range
            norm = None
        im = ax.imshow(g, origin="lower", extent=extent, cmap=cmap, norm=norm,
                       aspect="auto", interpolation="bilinear")
        cbar = self.fig.colorbar(im, ax=ax, shrink=0.85)
        cbar.set_label("D/U (dB)  [white line = protection ratio]", fontsize=8)
        try:
            ax.contour(res.lons, res.lats, res.du_db, levels=[prot], colors="white",
                       linewidths=1.2)
        except Exception:
            pass
        self._plot_stations(ax)
        ax.set_title("Wanted-to-unwanted ratio — protection {0:g} dB".format(prot),
                     fontsize=9)

    def _draw_field(self, ax, metric):
        res = self._result
        extent = self._extent(res.lats, res.lons)
        g = np.ma.masked_invalid(res.grid(metric))
        cmap = matplotlib.cm.get_cmap("jet").copy()
        cmap.set_bad(alpha=0.0)
        im = ax.imshow(g, origin="lower", extent=extent, cmap=cmap, aspect="auto",
                       interpolation="bilinear")
        cbar = self.fig.colorbar(im, ax=ax, shrink=0.85)
        cbar.set_label("E (dBuV/m)", fontsize=8)
        self._plot_stations(ax)
        which = "wanted" if metric == "wanted" else "combined interference"
        ax.set_title("Field strength — {0}".format(which), fontsize=9)

    def _draw_best(self, ax):
        bs = self._bs
        extent = self._extent(bs["lats"], bs["lons"])
        srv = np.ma.masked_less(bs["server"], 0)
        k = bs["meta"]["n_stations"]
        base = matplotlib.cm.get_cmap("tab10")
        cmap = ListedColormap([base(i % 10) for i in range(max(k, 1))])
        cmap.set_bad(alpha=0.0)
        im = ax.imshow(srv, origin="lower", extent=extent, cmap=cmap, aspect="auto",
                       interpolation="nearest", vmin=0, vmax=max(k - 1, 1))
        cbar = self.fig.colorbar(im, ax=ax, shrink=0.85,
                                 ticks=range(k))
        cbar.ax.set_yticklabels(bs["meta"]["station_labels"], fontsize=7)
        # station markers (reuse the service-result metadata)
        for i, (la, lo) in enumerate(bs["meta"]["station_latlon"]):
            ax.plot([lo], [la], "kv", ms=8, markerfacecolor="white")
        served = float(np.count_nonzero(bs["classification"] == 2)
                       / max(np.count_nonzero(np.isfinite(bs["best_field"])), 1))
        ax.set_title("Best server per cell ({0} stations, {1:.0%} served)".format(
            k, served), fontsize=9)

    def _summarize(self):
        res = self._result
        meta = res.meta
        served = res.fraction()
        interf = res.fraction(1)  # INTERFERENCE_LIMITED
        served_of_cov = res.fraction(over="coverage")
        model = ("ground-wave ({0}, {1})".format(
                     "P.368-10 spherical"
                     if meta.get("gw_engine") == "p368" else "P.368 flat",
                     self.ground.currentText())
                 if meta["model"] == "ground_wave" else "free-space / plane-earth")
        L = [
            "MULTI-STATION SERVICE / INTERFERENCE (D/U)",
            "  wanted      : {0}  @ {1:.4g} MHz".format(
                meta["wanted_label"], meta["freq_hz"] / 1e6),
            "  interferers : {0}  ({1})".format(
                meta["n_interferers"],
                ", ".join(meta["interferers"]) or "none"),
            "  protection  : {0:g} dB  D/U   (combine: {1})".format(
                meta["protection_ratio_db"], meta["combine"]),
            "  service thr : {0:g} dBuV/m".format(meta["service_threshold_dbuv_m"]),
            "  model       : {0}".format(model),
            "  radius      : {0:.3g} km, {1}x{1} grid".format(
                meta["radius_m"] / 1e3, meta["n"]),
            "  served      : {0:.0%} of area   ({1:.0%} of the covered area)".format(
                served, served_of_cov),
            "  interfered  : {0:.0%} of area (covered but D/U below protection)".format(
                interf),
        ]
        self.readout.setPlainText("\n".join(L))

    def _export_kml(self):
        from emstudio.coverage import multistation as ms

        if self._result is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export service/interference to KML", "service.kml", "KML (*.kml)")
        if not path:
            return
        metric = self._metric_key()
        if metric == "best":
            metric = "du"  # KML export operates on the ServiceResult layers
        try:
            kml_path, png_path = ms.export_service_kml(self._result, path,
                                                       metric=metric)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "EMStudio — export failed", str(exc))
            return
        QtWidgets.QMessageBox.information(
            self, "EMStudio",
            "Service/interference exported:\n{0}\n{1}\n\nOpen the .kml in Google "
            "Earth / QGIS.".format(kml_path, png_path))
