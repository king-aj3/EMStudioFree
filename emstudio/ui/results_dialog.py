# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sweep-results dialog: S11 / VSWR / impedance plots + Touchstone export.

Matplotlib embedded in a Qt dialog via the Agg-Qt canvas that ships with FreeCAD's
bundled matplotlib. Only imported from GUI code paths.
"""

from __future__ import annotations

import os

from PySide import QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import numpy as np  # noqa: E402


class SweepResultsDialog(QtWidgets.QDialog):
    """Tabbed plots for a one-port SweepResult."""

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        backend = result.meta.get("backend", "solver")
        self.setWindowTitle("EMStudio Results — {0}".format(backend))
        self.resize(820, 600)

        layout = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(tabs)

        tabs.addTab(self._plot_s11(), "S-Parameters")
        tabs.addTab(self._plot_vswr(), "VSWR")
        tabs.addTab(self._plot_z(), "Impedance")
        farfield = getattr(result, "farfield", None)
        if farfield is not None:
            tabs.addTab(self._plot_pattern(farfield), "Pattern")
            if farfield.phi.size > 4:  # full-sphere data -> 3-D balloon
                tabs.addTab(self._plot_pattern3d(farfield), "Pattern 3D")
        currents = getattr(result, "currents", None)
        if currents is not None:
            tabs.addTab(self._plot_currents(currents), "Currents")
        nearfield = getattr(result, "nearfield", None)
        if nearfield is not None:
            tabs.addTab(self._plot_nearfield(nearfield), "Near Field")

        # summary + export row
        f_min, s11_min = result.min_s11()
        summary = QtWidgets.QLabel(
            "Best match: {0:.2f} dB at {1:.3f} MHz    |    VSWR min: {2:.2f}".format(
                s11_min, f_min / 1e6, float(result.vswr().min())
            )
        )
        layout.addWidget(summary)

        buttons = QtWidgets.QHBoxLayout()
        export_btn = QtWidgets.QPushButton("Export Touchstone (.s1p)…")
        export_btn.clicked.connect(self._export_touchstone)
        report_btn = QtWidgets.QPushButton("Save PDF Report…")
        report_btn.setToolTip("A build-house-ready document: summary, S11/Zin, "
                              "radiation pattern, and BOM.")
        report_btn.clicked.connect(self._save_report)
        show3d_btn = QtWidgets.QPushButton("Show in 3D View")
        show3d_btn.setToolTip(
            "Add the results to FreeCAD's 3D viewport alongside your geometry:\n"
            "gain balloon (full-sphere pattern), current-colored wires, and the\n"
            "near-field plane — rotate/zoom/pan/tilt with normal navigation."
        )
        show3d_btn.clicked.connect(self._show_in_3d)
        buttons.addWidget(show3d_btn)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(export_btn)
        buttons.addWidget(report_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    # -- tabs -----------------------------------------------------------------
    def _canvas(self):
        """(figure, tab_widget) — every tab gets the matplotlib navigation toolbar
        (pan/zoom/save; 3-D axes additionally rotate with left-drag, zoom with
        right-drag/scroll)."""
        fig = Figure(figsize=(7, 5), tight_layout=True)
        canvas = FigureCanvas(fig)
        holder = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(NavigationToolbar2QT(canvas, holder))
        lay.addWidget(canvas)
        holder._canvas = canvas  # keep a ref
        return fig, holder

    def _plot_s11(self):
        fig, canvas = self._canvas()
        ax = fig.add_subplot(111)
        ax.plot(self.result.freq / 1e6, self.result.s11_db(), "-", linewidth=2,
                label="S11")
        for (to_p, from_p), s in sorted(getattr(self.result, "s_others", {}).items()):
            db = 20.0 * np.log10(np.maximum(np.abs(s), 1e-30))
            ax.plot(self.result.freq / 1e6, db, "--", linewidth=2,
                    label="S{0}{1}".format(to_p, from_p))
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("S-Parameters (dB)")
        ax.grid(True)
        ax.axhline(-10.0, linestyle="--", linewidth=1, color="#999999")
        ax.legend()
        return canvas

    def _plot_pattern3d(self, ff):
        """Rotatable 3-D gain balloon (drag to rotate, right-drag/scroll to zoom)."""
        fig, holder = self._canvas()
        ax = fig.add_subplot(111, projection="3d")
        floor = -30.0
        g = ff.gain
        g_max = g.max()
        r = np.clip((g - (g_max + floor)) / (-floor), 0.0, 1.0)
        th = np.deg2rad(ff.theta)[:, None]
        ph = np.deg2rad(ff.phi)[None, :]
        x = r * np.sin(th) * np.cos(ph)
        y = r * np.sin(th) * np.sin(ph)
        z = r * np.cos(th) * np.ones_like(ph)
        norm = matplotlib.colors.Normalize(vmin=g_max + floor, vmax=g_max)
        colors = matplotlib.cm.get_cmap("jet")(norm(g))
        ax.plot_surface(x, y, z, facecolors=colors, rstride=1, cstride=1,
                        linewidth=0, antialiased=True, shade=False)
        m = matplotlib.cm.ScalarMappable(cmap="jet", norm=norm)
        fig.colorbar(m, ax=ax, shrink=0.7, label="Gain (dBi)")
        ax.set_title("3-D pattern @ {0:.3f} GHz — drag to rotate".format(ff.freq / 1e9),
                     fontsize=9)
        ax.set_box_aspect((1, 1, 1))
        for a in (ax.xaxis, ax.yaxis, ax.zaxis):
            a.set_ticklabels([])
        return holder

    def _plot_currents(self, cur):
        fig, canvas = self._canvas()
        ax = fig.add_subplot(111)
        pos = cur["pos_m"]
        # distance along the wire run (works for straight and modestly curved wires)
        d = np.zeros(len(pos))
        if len(pos) > 1:
            d[1:] = np.cumsum(np.linalg.norm(np.diff(pos, axis=0), axis=1))
        ax.plot(d * 1e3, cur["i_mag"] * 1e3, "-o", linewidth=2, markersize=3)
        ax.set_xlabel("Position along wire (mm)")
        ax.set_ylabel("|I| (mA per volt drive)")
        ax.set_title("Current distribution @ {0:.3f} MHz".format(cur["freq"] / 1e6))
        ax.grid(True)
        return canvas

    def _plot_nearfield(self, nf):
        fig, canvas = self._canvas()
        ax = fig.add_subplot(111)
        plane = str(nf.get("plane", "XY"))
        axes_mm = {"XY": ("x", "y"), "XZ": ("x", "z"), "YZ": ("y", "z")}[plane]
        a1 = np.asarray(nf[axes_mm[0]]) * 1e3
        a2 = np.asarray(nf[axes_mm[1]]) * 1e3
        e = np.asarray(nf["e_mag"])
        # h5 field arrays come (z, y, x); squeeze left a 2-D slice — orient to (a2, a1)
        if e.shape == (len(a1), len(a2)):
            e = e.T
        e_db = 20.0 * np.log10(np.maximum(e / max(e.max(), 1e-30), 1e-4))
        pcm = ax.pcolormesh(a1, a2, e_db, cmap="inferno", shading="nearest")
        fig.colorbar(pcm, ax=ax, label="|E| (dB rel. max)")
        ax.set_xlabel("{0} (mm)".format(axes_mm[0]))
        ax.set_ylabel("{0} (mm)".format(axes_mm[1]))
        ax.set_aspect("equal")
        ax.set_title("Near-field |E|, {0} plane @ {1:.3f} GHz".format(
            plane, float(nf.get("freq", 0.0)) / 1e9))
        return canvas

    def _plot_vswr(self):
        fig, canvas = self._canvas()
        ax = fig.add_subplot(111)
        ax.plot(self.result.freq / 1e6, np.clip(self.result.vswr(), 1, 20), "-", linewidth=2)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("VSWR (ref {0:g} Ω)".format(self.result.z0))
        ax.set_ylim(1, 10)
        ax.grid(True)
        return canvas

    def _plot_z(self):
        fig, canvas = self._canvas()
        ax = fig.add_subplot(111)
        ax.plot(self.result.freq / 1e6, np.real(self.result.zin), "-", linewidth=2, label="R")
        ax.plot(self.result.freq / 1e6, np.imag(self.result.zin), "--", linewidth=2, label="X")
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Input impedance (Ω)")
        ax.axhline(0.0, linewidth=0.8)
        ax.grid(True)
        ax.legend()
        return canvas

    def _plot_pattern(self, ff):
        fig, canvas = self._canvas()
        ax = fig.add_subplot(111, projection="polar")
        for phi, style, label in ((0.0, "-", "xz-plane (phi=0°)"), (90.0, "--", "yz-plane (phi=90°)")):
            theta, gain = ff.cut(phi)
            ax.plot(np.deg2rad(theta), gain, style, linewidth=2, label=label)
            # mirror the cut for the full circle when theta covers only 0..180
            if theta.max() <= 180.0:
                ax.plot(-np.deg2rad(theta), gain, style, linewidth=1, alpha=0.6)
        g, th, phv = ff.peak()
        ax.set_theta_zero_location("N")
        ax.set_title(
            "Gain (dBi) at {0:.3f} GHz — peak {1:.2f} dBi @ θ={2:.0f}° φ={3:.0f}°".format(
                ff.freq / 1e9, g, th, phv
            ),
            fontsize=10,
        )
        ax.set_rmin(max(ff.gain.min(), g - 40.0))
        ax.legend(loc="lower left", fontsize=8)
        return canvas

    # -- export ---------------------------------------------------------------
    def _export_touchstone(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Touchstone", os.path.expanduser("~/port_1.s1p"),
            "Touchstone 1-port (*.s1p)",
        )
        if path:
            self.result.write_touchstone(path)
            QtWidgets.QMessageBox.information(self, "EMStudio", "Saved " + path)

    def _show_in_3d(self):
        """Write result VTUs into the workdir and load them into the 3D viewport."""
        import os

        import FreeCAD

        from emstudio.post import vtk_out

        workdir = self.result.meta.get("workdir", "")
        if not workdir or not os.path.isdir(workdir):
            import tempfile

            workdir = tempfile.mkdtemp(prefix="emstudio_vis_")
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()
        created = []
        try:
            ff = getattr(self.result, "farfield", None)
            if ff is not None and ff.phi.size > 4:
                # Sit the balloon ON the antenna and size it to the model. The
                # far field is referenced to the SOLVER's origin, which for a
                # structure built from x=0 is one END of it, so an origin-drawn
                # balloon hangs off the edge of its own geometry. Only the draw
                # position moves; the directions shown are unchanged.
                centre, extent = vtk_out.geometry_extent_mm(doc.Objects)
                p = vtk_out.write_pattern_vtu(
                    ff, os.path.join(workdir, "pattern3d.vtu"),
                    radius_mm=(vtk_out.auto_radius_mm(extent) if extent else 100.0),
                    center_mm=(centre or (0.0, 0.0, 0.0)))
                # Semi-transparent: the balloon now ENCLOSES the antenna, so
                # an opaque one would hide the very geometry it describes.
                created.append(vtk_out.show_in_freecad(
                    p, "Pattern balloon @ {0:.3f} GHz".format(ff.freq / 1e9),
                    doc, transparency=55).Label)
            cur = getattr(self.result, "currents", None)
            if cur is not None:
                p = vtk_out.write_currents_vtu(cur, os.path.join(workdir, "currents.vtu"))
                created.append(vtk_out.show_in_freecad(p, "Wire currents", doc).Label)
            nf = getattr(self.result, "nearfield", None)
            if nf is not None:
                p = vtk_out.write_field_plane_vtu(nf, os.path.join(workdir, "nearfield.vtu"))
                created.append(vtk_out.show_in_freecad(p, "Near-field |E| plane", doc).Label)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "EMStudio", "3D view failed: {0}".format(exc))
            return
        if created:
            try:
                import FreeCADGui

                FreeCADGui.SendMsgToActiveView("ViewFit")
            except Exception:
                pass
            QtWidgets.QMessageBox.information(
                self, "EMStudio",
                "Added to the 3D view:\n• " + "\n• ".join(created) +
                "\n\nRotate/zoom/pan with normal FreeCAD navigation. Color scale: "
                "select the object and adjust in its view properties.")
        else:
            QtWidgets.QMessageBox.information(
                self, "EMStudio",
                "No 3D-viewable results in this run (need a full-sphere pattern, "
                "currents, or a near-field plane).")

    def _save_report(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save PDF report", os.path.expanduser("~/antenna_report.pdf"),
            "PDF (*.pdf)",
        )
        if not path:
            return
        try:
            from emstudio.report import antenna_report

            antenna_report(self.result, path,
                           title=self.result.meta.get("analysis", "Antenna Analysis"))
            QtWidgets.QMessageBox.information(self, "EMStudio", "Saved report:\n" + path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "EMStudio", "Report failed: {0}".format(exc))
