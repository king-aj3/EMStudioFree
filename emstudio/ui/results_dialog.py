# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sweep-results dialog: S11 / VSWR / impedance plots + Touchstone export.

Matplotlib embedded in a Qt dialog via the Agg-Qt canvas that ships with FreeCAD's
bundled matplotlib. Only imported from GUI code paths.
"""

from __future__ import annotations

import os

from PySide import QtCore, QtWidgets

import matplotlib

matplotlib.use("QtAgg", force=False)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # noqa: E402
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import numpy as np  # noqa: E402

#: Top of the familiar linear VSWR view. A curve that fits under this is drawn
#: exactly as it always was; one that does not gets a log axis instead of being
#: silently clipped off the top of the axes.
#:
#: That silent clip was a real defect, found on a real model: a 300 mm helix
#: swept 10-100 MHz has a minimum VSWR of 411, so every one of its 51 points sat
#: ~40x above the ceiling and the tab drew an empty grid. The data was present
#: and correct the whole time and the plot said "no data".
VSWR_VIEW_TOP = 10.0

#: The usual acceptance line. Drawn only when it is inside the view — a 2:1
#: marker three decades below the data teaches nothing.
VSWR_ACCEPT = 2.0


#: Open non-modal results dialogs. WA_DeleteOnClose destroys the C++ side on
#: close, and with a None parent nothing else would keep the PYTHON wrapper
#: alive while shown — this list does. Entries remove themselves on destroy.
_open_results = []


def show_sweep_results(result, parent=None):
    """Show the sweep-results dialog NON-MODAL, deleted for real on close.

    Every caller used ``.exec()`` (application-modal) — which an adversarial
    review (2026-08-06) showed broke the scrubbing feature twice over: the
    modal dialog input-blocked the floating viewport scrubber (unusable
    until close), and ``close()`` on a parented dialog only HID it, so
    post-close scrubs drove a hidden dialog that lazily built matplotlib
    figures forever and the scrubber's dead-dialog detection could never
    fire. Non-modal + WA_DeleteOnClose fixes all of it at once — and lets
    the user rotate the 3-D view while the plots are up, which is the whole
    point of putting results in the viewport.
    """
    dlg = SweepResultsDialog(result, parent=parent)
    dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    _open_results.append(dlg)

    def _gone(*_a):
        try:
            _open_results.remove(dlg)
        except ValueError:
            pass

    dlg.destroyed.connect(_gone)
    dlg.show()
    return dlg


def _retarget_balloon(balloon, ctx, ff):
    """Rewrite a 3-D pattern balloon's VTU in place for a new far field.

    Returns False when the balloon is gone (deleted from the tree, or its
    document closed) — callers drop their reference. Shared by the dialog's
    live-follow and the floating viewport scrubber, so the two can never
    disagree about what an update does. Same path, same centre and radius:
    only the pattern changes, never the framing.
    """
    try:
        doc = balloon.Document
        if doc.getObject(balloon.Name) is None:
            return False
    except Exception:                          # noqa: BLE001 — deleted object
        return False
    if ff is None or not (ff.phi.size > 4 and ff.theta.size > 1):
        return True                            # nothing drawable; keep the ref
    from emstudio.post import vtk_out

    path, centre, extent = ctx
    try:
        p = vtk_out.write_pattern_vtu(
            ff, path,
            radius_mm=(vtk_out.auto_radius_mm(extent) if extent else 100.0),
            center_mm=centre)
        balloon.read(p)
        balloon.Label = "Pattern balloon @ {0:.3f} GHz".format(ff.freq / 1e9)
        doc.recompute()
    except Exception as exc:                   # noqa: BLE001 — non-fatal
        import FreeCAD
        FreeCAD.Console.PrintWarning(
            "EMStudio: balloon update failed: {0}\n".format(exc))
    return True


class BalloonScrubber(QtWidgets.QWidget):
    """Floating frequency slider that lives over the 3-D viewport.

    "Show in 3D View" spawns it beside the balloon it controls (AJ,
    2026-08-06: scrub the frequencies and watch the balloon change without
    the results dialog in the way). It OWNS its data — the far-field list,
    the balloon object and the write context — so it keeps working after
    the results dialog closes; while the dialog lives, ``on_change`` routes
    every scrub through the dialog's shared selection, so the 2-D tabs and
    the sweep-plot cursors move with it. One scrubber at a time: a new
    "Show in 3D View" replaces the old one (a stack of orphaned sliders,
    each bound to a dead balloon, is worse than none).
    """

    _instance = None

    @classmethod
    def show_for(cls, farfields, index, balloon, ctx, on_change=None):
        old, cls._instance = cls._instance, None
        if old is not None:
            try:
                old.close()
            except RuntimeError:
                pass                           # Qt C++ side already deleted
        sc = cls(farfields, index, balloon, ctx, on_change)
        cls._instance = sc
        sc.show()
        return sc

    def __init__(self, farfields, index, balloon, ctx, on_change=None):
        import FreeCADGui
        mw = FreeCADGui.getMainWindow()
        super().__init__(mw, QtCore.Qt.Tool)
        self.setWindowTitle("EMStudio — pattern frequency")
        self._ffs = list(farfields)
        self._balloon = balloon
        self._ctx = ctx
        self.on_change = on_change

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider.setRange(0, len(self._ffs) - 1)
        self.slider.setValue(index)
        self.slider.setTracking(True)
        self.slider.setMinimumWidth(280)
        row.addWidget(self.slider, 1)
        self.label = QtWidgets.QLabel(self)
        self.label.setMinimumWidth(90)
        row.addWidget(self.label)

        # Same coalescing the dialog uses: label instantly, balloon ~16 fps
        # with the trailing edge guaranteed.
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._apply)
        self.slider.valueChanged.connect(self._on_value)

        self._set_label(index)
        self._position_over_view(mw)

    # -- wiring ---------------------------------------------------------------
    def balloon_is(self, obj):
        return obj is not None and obj is self._balloon

    def set_index_silent(self, idx):
        """Follow an external selection without echoing it back."""
        if self.slider.value() != idx:
            self.slider.blockSignals(True)
            self.slider.setValue(idx)
            self.slider.blockSignals(False)
        self._set_label(idx)

    def _set_label(self, idx):
        self.label.setText("{0:.4g} MHz".format(self._ffs[idx].freq / 1e6))

    def _on_value(self, idx):
        self._set_label(idx)
        self._timer.start()

    def _apply(self):
        idx = self.slider.value()
        if self.on_change is not None:
            # The dialog drives everything (tabs, cursors, balloon) while it
            # lives; when it has been closed the bound method's C++ side is
            # gone and raises — drop the hook and scrub the balloon solo.
            try:
                self.on_change(idx)
                return
            except RuntimeError:
                self.on_change = None
        if not _retarget_balloon(self._balloon, self._ctx, self._ffs[idx]):
            self.close()

    def closeEvent(self, event):
        if BalloonScrubber._instance is self:
            BalloonScrubber._instance = None
        super().closeEvent(event)

    def _position_over_view(self, mw):
        """Bottom-centre of the active 3-D view; centre of the window else.

        Positioning is cosmetic, so every step is allowed to fail — a
        scrubber that appears at a default spot beats one that crashed
        trying to be pretty. It is a normal Tool window: the user can drag
        it wherever they like afterwards.
        """
        try:
            mdi = mw.findChild(QtWidgets.QMdiArea)
            sub = mdi.activeSubWindow() if mdi is not None else None
            ref = sub if sub is not None else mw
            top_left = ref.mapToGlobal(QtCore.QPoint(0, 0))
            self.adjustSize()
            x = top_left.x() + (ref.width() - self.width()) // 2
            y = top_left.y() + ref.height() - self.height() - 48
            self.move(max(x, 0), max(y, 0))
        except Exception:                      # noqa: BLE001 — cosmetic only
            pass


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

        # The scrub state is decided BEFORE any plot is built: the sweep
        # plots (S11 / VSWR / impedance) each register a frequency CURSOR —
        # a vertical line with intersection markers and a live readout —
        # that follows the same shared selection the pattern tabs and the
        # 3-D balloon use, so sliding through the band moves everything at
        # once (AJ, 2026-08-06).
        farfield = getattr(result, "farfield", None)
        self._freq_cursors = []
        if farfield is not None:
            # A sweep can carry a pattern PER FREQUENCY (the solver's
            # PatternFrequencies). Wrap each pattern tab in a picker so the
            # user can scroll the band; with a single pattern the picker is
            # not built at all and the tab is exactly what it always was.
            self._farfields = list(getattr(result, "farfields", None)
                                   or [farfield])
            self._farfields.sort(key=lambda ff: ff.freq)
            # ONE selection shared by every pattern view and by "Show in 3D
            # View". Two tabs each owning their own combo would let the 2-D cut,
            # the balloon and the FreeCAD overlay disagree about which frequency
            # is on screen, and nothing on any of them says which is which.
            self._ff_index = min(
                range(len(self._farfields)),
                key=lambda i: abs(self._farfields[i].freq - farfield.freq))
            self._pattern_views = []

        tabs.addTab(self._plot_s11(), "S-Parameters")
        tabs.addTab(self._plot_vswr(), "VSWR")
        tabs.addTab(self._plot_z(), "Impedance")
        if farfield is not None:
            tabs.addTab(self._pattern_tab(self._plot_pattern), "Pattern")
            if farfield.phi.size > 4:  # full-sphere data -> 3-D balloon
                tabs.addTab(self._pattern_tab(self._plot_pattern3d),
                            "Pattern 3D")
            if len(self._farfields) >= 2:
                # Land every cursor on the starting selection so the plots
                # open already annotated, not waiting for a first drag.
                self._fire_freq_cursors()
        currents = getattr(result, "currents", None)
        if currents is not None:
            tabs.addTab(self._plot_currents(currents), "Currents")
        nearfield = getattr(result, "nearfield", None)
        if nearfield is not None:
            tabs.addTab(self._plot_nearfield(nearfield), "Near Field")

        # summary + export row
        f_min, s11_min = result.min_s11()
        text = "Best match: {0:.2f} dB at {1:.3f} MHz    |    VSWR min: {2:.2f}".format(
            s11_min, f_min / 1e6, float(result.vswr().min())
        )
        # Say it in words as well as on the axes. A user who reads "VSWR min
        # 411" understands an empty-looking 1..10 plot; one who does not read
        # the number concludes the run produced nothing.
        if float(result.vswr().min()) >= VSWR_VIEW_TOP:
            text += "  —  never matched in this band (VSWR tab is on a log scale)"
        summary = QtWidgets.QLabel(text)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # NEC2 has a validity limit its own output never mentions. If the deck
        # is under it, say so HERE — beside the numbers it qualifies — rather
        # than leaving the user to know that NEC has such a limit at all.
        thin = result.meta.get("thin_wire")
        if thin and not thin.get("ok", True):
            warn = QtWidgets.QLabel(
                "⚠ Thin-wire check: shortest segment is {0:.2g} wire radii "
                "(NEC-2's kernel is derived for ≳ {1:.0f}). The impedance "
                "above is outside the kernel's stated range — treat it as "
                "indicative and re-check with a thinner conductor or a coarser "
                "wire path.".format(thin["ratio"], thin["limit"]))
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #b06000;")
            layout.addWidget(warn)

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

    def _add_freq_cursor(self, ax, holder, series, unit):
        """A frequency cursor on a sweep plot: vline + markers + readout.

        ``series`` is ``[(label, y_array), ...]`` on ``self.result.freq``.
        Values at the selected frequency come from ``np.interp`` — pattern
        frequencies USUALLY land on sweep samples (the recommended step is
        built to), but a hand-typed step need not, and a cursor that snaps
        to the wrong sample would disagree with the pattern tab's title.
        Invisible until the first fire, so single-pattern results keep
        their plots exactly as they were.
        """
        f = self.result.freq
        vline = ax.axvline(float(f[0]) / 1e6, color="#c8553d",
                           linewidth=1.2, alpha=0.0)
        dots = [ax.plot([], [], "o", markersize=6, color="#c8553d",
                        zorder=5)[0] for _ in series]
        note = ax.annotate("", xy=(0.02, 0.02), xycoords="axes fraction",
                           va="bottom", fontsize=8, color="#c8553d",
                           bbox={"boxstyle": "round,pad=0.25",
                                 "fc": "#ffffff", "ec": "#c8553d",
                                 "alpha": 0.85})
        canvas = holder._canvas

        def update(freq_hz):
            x = freq_hz / 1e6
            # A pattern band is allowed to EXCEED the sweep (resolve_band
            # never clamps an override), and np.interp would then silently
            # report the band-edge sweep value under the wrong frequency —
            # a confident wrong number on three plots at once (adversarial
            # review, 2026-08-06). Outside the sweep (or on a single-point
            # sweep, where interpolation is fiction) the cursor SAYS SO
            # instead of guessing.
            in_band = (f.size > 1
                       and float(f[0]) <= freq_hz <= float(f[-1]))
            vline.set_xdata([x, x])
            vline.set_alpha(0.8 if in_band else 0.0)
            if not in_band:
                for dot in dots:
                    dot.set_data([], [])
                text = ("{0:.4g} MHz: outside the swept band — no "
                        "curve value here".format(x))
                note.set_text(text)
                canvas.draw_idle()
                return text
            vals = []
            for (label, y), dot in zip(series, dots):
                yv = float(np.interp(freq_hz, f, y))
                dot.set_data([x], [yv])
                vals.append("{0} {1:.4g}{2}".format(label, yv, unit))
            text = "{0:.4g} MHz:  {1}".format(x, ",  ".join(vals))
            note.set_text(text)
            canvas.draw_idle()
            return text

        self._freq_cursors.append(update)

    def _fire_freq_cursors(self):
        ffs = getattr(self, "_farfields", None)
        if not ffs or len(ffs) < 2:
            return
        freq = ffs[self._ff_index].freq
        for update in self._freq_cursors:
            update(freq)

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
        self._add_freq_cursor(ax, canvas, [("S11", self.result.s11_db())],
                              " dB")
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

    def _pattern_tab(self, plot_fn):
        """One pattern plot, with a frequency picker when there is a choice.

        The picker rebuilds the plot rather than caching every figure: a
        full-sphere balloon at 201 frequencies is a lot of matplotlib to hold
        for a control the user may never touch, and redrawing one is fast.
        """
        current = self.result.farfield
        if len(self._farfields) < 2:
            # Nothing to choose — the plot is exactly what it always was. But
            # SAY WHY there is no picker: a user who asked for a swept pattern
            # and got one tab with no control cannot tell "the feature is off"
            # from "the feature is missing", and the switch is a solver
            # property they have no reason to have found.
            holder = QtWidgets.QWidget(self)
            box = QtWidgets.QVBoxLayout(holder)
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(plot_fn(current))
            hint = QtWidgets.QLabel(
                "One pattern only, at the best-match frequency. For a pattern "
                "you can scroll across the band, run "
                "EMStudio ▸ Analysis ▸ Pattern Frequencies… before solving.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #666666;")
            box.addWidget(hint)
            return holder

        holder = QtWidgets.QWidget(self)
        box = QtWidgets.QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Frequency:"))
        combo = QtWidgets.QComboBox(holder)
        for ff in self._farfields:
            combo.addItem("{0:.4g} MHz".format(ff.freq / 1e6))
        combo.setCurrentIndex(self._ff_index)
        row.addWidget(combo)
        row.addWidget(QtWidgets.QLabel(
            "({0} solved frequencies — 'Show in 3D View' uses this one)".format(
                len(self._farfields))))
        row.addStretch(1)
        box.addLayout(row)

        stack = QtWidgets.QStackedWidget(holder)
        box.addWidget(stack)
        built = {}

        def show(idx):
            if idx not in built:
                w = plot_fn(self._farfields[idx])
                built[idx] = stack.addWidget(w)
            stack.setCurrentIndex(built[idx])

        # The scrub slider (AJ, 2026-08-06): drag through the solved
        # frequencies and watch the plot — and the 3-D balloon, when one is
        # up — change in real time. Bottom of the tab, full width, with
        # tracking ON; the balloon rewrite is throttled in
        # _select_frequency so dragging stays smooth.
        srow = QtWidgets.QHBoxLayout()
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, holder)
        slider.setRange(0, len(self._farfields) - 1)
        slider.setValue(self._ff_index)
        slider.setTracking(True)
        slider.setToolTip("Slide through the solved frequencies — plots and "
                          "the 3-D balloon follow live.")
        srow.addWidget(QtWidgets.QLabel(
            "{0:.4g}".format(self._farfields[0].freq / 1e6)))
        srow.addWidget(slider, 1)
        srow.addWidget(QtWidgets.QLabel(
            "{0:.4g} MHz".format(self._farfields[-1].freq / 1e6)))
        box.addLayout(srow)

        combo.currentIndexChanged.connect(self._select_frequency)
        slider.valueChanged.connect(self._select_frequency)
        self._pattern_views.append((combo, slider, show))
        show(self._ff_index)
        return holder

    def _select_frequency(self, idx):
        """Point every pattern view — and the 3-D export — at one frequency."""
        if not (0 <= idx < len(self._farfields)):
            return
        self._ff_index = idx
        for combo, slider, _show in self._pattern_views:
            for w in (combo, slider):
                if (w.currentIndex() if w is combo else w.value()) != idx:
                    # Without the block this re-enters through the signals.
                    w.blockSignals(True)
                    (w.setCurrentIndex if w is combo else w.setValue)(idx)
                    w.blockSignals(False)
        # The sweep plots' frequency cursors ride along (vline + markers +
        # readout). draw_idle coalesces repaints on the Qt loop, so these
        # stay direct — they are what makes the drag feel live.
        self._fire_freq_cursors()
        # EVERYTHING EXPENSIVE is coalesced (~16 fps, trailing edge
        # guaranteed): the pattern-figure builds AND the balloon rewrite. A
        # tracking slider emits a value per pixel; building a polar figure
        # plus a full-sphere plot_surface per pixel froze the drag for
        # seconds and cached every intermediate figure forever (adversarial
        # review, 2026-08-06 — a drag across 201 frequencies could construct
        # ~400 figures). Deferring the builds means only indices the user
        # dwells on get built; the release value always lands.
        if not hasattr(self, "_balloon_timer"):
            self._balloon_timer = QtCore.QTimer(self)
            self._balloon_timer.setSingleShot(True)
            self._balloon_timer.setInterval(60)
            self._balloon_timer.timeout.connect(self._apply_selection)
        self._balloon_timer.start()
        # Keep a floating viewport scrubber (if it points at OUR balloon)
        # on the same frequency.
        sc = BalloonScrubber._instance
        if sc is not None and sc.balloon_is(getattr(self, "_balloon", None)):
            sc.set_index_silent(idx)

    def _apply_selection(self):
        """Trailing edge of a scrub: build the visible plots, move the balloon."""
        idx = self._ff_index
        for _combo, _slider, show in self._pattern_views:
            show(idx)
        self._update_balloon()

    def _update_balloon(self):
        """Re-point an existing 3-D pattern balloon at the picked frequency.

        Live-follow: once "Show in 3D View" has created a balloon, scrolling
        the picker rewrites its VTU (same path, same centre and radius so
        only the pattern changes, never the framing) and re-reads it in
        place — no second button press, no second overlay. A balloon the
        user deleted from the tree is dropped silently; the next "Show in
        3D View" starts a fresh one.
        """
        obj = getattr(self, "_balloon", None)
        if obj is None:
            return
        ff = self._selected_farfield()
        if not _retarget_balloon(obj, self._balloon_ctx, ff):
            self._balloon = None

    def _selected_farfield(self):
        """The far field the user is looking at, or the only one there is."""
        ffs = getattr(self, "_farfields", None)
        if not ffs:
            return getattr(self.result, "farfield", None)
        return ffs[min(max(self._ff_index, 0), len(ffs) - 1)]

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
        f_mhz = self.result.freq / 1e6
        v = self.result.vswr()
        v_min = float(v.min())
        i_min = int(np.argmin(v))
        # A single-point sweep draws NOTHING with a bare line style — there is
        # no second vertex to draw a line to. Markers make one point visible.
        style = "-" if v.size > 1 else "o"

        if v_min < VSWR_VIEW_TOP:
            # The familiar view, unchanged: linear 1..10 with the acceptance
            # line. This is every matched antenna, which is nearly all of them.
            ax.plot(f_mhz, np.clip(v, 1, 20), style, linewidth=2)
            ax.set_ylim(1, VSWR_VIEW_TOP)
            ax.axhline(VSWR_ACCEPT, linestyle="--", linewidth=1, color="#999999")
            ax.annotate("{0:g}:1".format(VSWR_ACCEPT), (f_mhz[0], VSWR_ACCEPT),
                        textcoords="offset points", xytext=(2, 3),
                        fontsize=8, color="#777777")
        else:
            # Nothing in the band fits the linear view. Clipping to it is what
            # produced an empty plot on a run that had 51 perfectly good points,
            # so show the real numbers on a log axis and label the best one.
            ax.semilogy(f_mhz, v, style, linewidth=2)
            ax.plot([f_mhz[i_min]], [v_min], "o", color="#c8553d", markersize=6)
            ax.annotate(
                "min {0:.4g}:1 at {1:.4g} MHz".format(v_min, f_mhz[i_min]),
                (f_mhz[i_min], v_min), textcoords="offset points",
                xytext=(6, 8), fontsize=9, color="#c8553d")
            ax.set_title(
                "Never below {0:g}:1 in this band — log scale".format(
                    VSWR_VIEW_TOP), fontsize=9)
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("VSWR (ref {0:g} Ω)".format(self.result.z0))
        ax.grid(True, which="both", alpha=0.4)
        self._add_freq_cursor(ax, canvas, [("VSWR", v)], ":1")
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
        self._add_freq_cursor(ax, canvas,
                              [("R", np.real(self.result.zin)),
                               ("X", np.imag(self.result.zin))], " Ω")
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
        ff = None          # the post-try check reads this; keep it bound
        try:
            # The pattern the user is LOOKING AT, not the best-match one. This
            # read self.result.farfield, which is pinned to the resonance, so
            # scrolling the picker to 40 MHz and pressing "Show in 3D View"
            # silently added a balloon for a different frequency — with the
            # right frequency in its own label, so nothing looked wrong.
            ff = self._selected_farfield()
            # theta MATTERS TOO. This gate only ever checked phi, so a
            # single-theta cut sailed through and write_pattern_vtu produced a
            # VTU with points and no cells: an overlay that appears in the tree
            # and draws nothing (2026-08-05). The writer now refuses such a
            # grid; catch that and SAY SO rather than leaving a dead object.
            if ff is not None and ff.phi.size > 4 and ff.theta.size > 1:
                # Sit the balloon ON the antenna and size it to the model. The
                # far field is referenced to the SOLVER's origin, which for a
                # structure built from x=0 is one END of it, so an origin-drawn
                # balloon hangs off the edge of its own geometry. Only the draw
                # position moves; the directions shown are unchanged.
                # Measure the ANTENNA THIS RESULT CAME FROM, not the whole
                # document. A second analysis or a leftover body would
                # otherwise move the balloon off its own radiator.
                # meta carries the analysis LABEL (a string), not the object —
                # resolve it, or this silently falls back to the whole document
                # and looks like it worked.
                geo = []
                label = self.result.meta.get("analysis")
                ana = None
                if label:
                    from emstudio.objects import query
                    for cand in query.find_analyses(doc):
                        if cand.Label == label:
                            ana = cand
                            break
                if ana is not None:
                    try:
                        geo = vtk_out.analysis_geometry(ana)
                    except Exception:                    # noqa: BLE001
                        geo = []
                centre, extent = vtk_out.geometry_extent_mm(geo or doc.Objects)
                p = vtk_out.write_pattern_vtu(
                    ff, os.path.join(workdir, "pattern3d.vtu"),
                    radius_mm=(vtk_out.auto_radius_mm(extent) if extent else 100.0),
                    center_mm=(centre or (0.0, 0.0, 0.0)))
                # Semi-transparent: the balloon now ENCLOSES the antenna, so
                # an opaque one would hide the very geometry it describes.
                balloon = vtk_out.show_in_freecad(
                    p, "Pattern balloon @ {0:.3f} GHz".format(ff.freq / 1e9),
                    doc, transparency=55)
                created.append(balloon.Label)
                # Remember it: from here on the balloon FOLLOWS the picker
                # live (AJ, 2026-08-06 — scrolling the solved frequencies
                # should update the 3-D view, not need another button press).
                self._balloon = balloon
                self._balloon_ctx = (p, centre or (0.0, 0.0, 0.0),
                                     extent)
                # ...and with a band to scrub, a floating slider appears on
                # the viewport itself. It routes through _select_frequency
                # while this dialog lives (tabs + cursors + balloon all
                # move) and keeps driving the balloon alone after close.
                if len(getattr(self, "_farfields", [])) >= 2:
                    BalloonScrubber.show_for(
                        self._farfields, self._ff_index, balloon,
                        self._balloon_ctx, on_change=self._select_frequency)
            cur = getattr(self.result, "currents", None)
            if cur is not None:
                p = vtk_out.write_currents_vtu(cur, os.path.join(workdir, "currents.vtu"))
                # NAME the frequency. Currents are solved at the best match
                # only, so once the balloon can be at a different frequency an
                # unlabelled "Wire currents" sitting beside it reads as though
                # the two belong to the same point in the sweep.
                created.append(vtk_out.show_in_freecad(
                    p, "Wire currents @ {0:.3f} GHz".format(
                        float(cur.get("freq", 0.0)) / 1e9), doc).Label)
            nf = getattr(self.result, "nearfield", None)
            if nf is not None:
                p = vtk_out.write_field_plane_vtu(nf, os.path.join(workdir, "nearfield.vtu"))
                created.append(vtk_out.show_in_freecad(p, "Near-field |E| plane", doc).Label)
        except vtk_out.PatternGridError as exc:
            # Not a crash: the pattern genuinely cannot be drawn as a balloon.
            # Explain it and still show whatever else IS drawable.
            QtWidgets.QMessageBox.warning(
                self, "EMStudio — no 3-D pattern",
                "{0}\n\nAnything else the run produced (wire currents, "
                "near field) has still been added.".format(exc))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "EMStudio", "3D view failed: {0}".format(exc))
            return
        if ff is not None and (ff.phi.size <= 4 or ff.theta.size <= 1):
            QtWidgets.QMessageBox.warning(
                self, "EMStudio — no 3-D pattern",
                "This run's far field is a single cut ({0} theta x {1} phi), "
                "not a full-sphere grid, so a 3-D balloon cannot be built "
                "from it.\n\nUse the Pattern tab for the 2-D polar plot, or "
                "re-run with a full-sphere pattern.".format(
                    ff.theta.size, ff.phi.size))
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
