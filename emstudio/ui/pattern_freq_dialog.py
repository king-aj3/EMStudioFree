# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pattern Frequencies — choose the band and spacing of the radiation-pattern pass.

The three numbers NEC2 needs are a band and a count. This dialog offers the
analysis sweep as the band (the usual answer, and the one the feature had
hard-wired before this existed), a recommended STEP that lands pattern
frequencies on the sweep's own sample points, and lets both be overridden.

It writes ``PatternFrequencies`` / ``PatternFreqStart`` / ``PatternFreqStop``
onto the NEC2 solver and nothing else — solving is still Run Solver.
"""

from __future__ import annotations

from PySide import QtCore, QtWidgets

from emstudio.solvers.nec2 import pattern_band

MHZ = 1e6


class PatternFrequenciesDialog(QtWidgets.QDialog):
    """Set the radiation-pattern band and spacing on a NEC2 solver."""

    def __init__(self, analysis, solver, parent=None):
        super().__init__(parent)
        self.analysis = analysis
        self.solver = solver
        self.setWindowTitle("EMStudio — Pattern Frequencies")
        self.setMinimumWidth(560)

        from emstudio.objects.analysis import Analysis

        self.sweep_f1, self.sweep_f2, self.sweep_pts = Analysis.freq_range_hz(analysis)
        # The SWEEP's spacing, held once. Recomputing it from whatever band is
        # on screen would move the grid every time the user narrowed the band,
        # which is precisely the alignment this feature is for.
        self.sweep_step = pattern_band.sweep_step_hz(
            self.sweep_f1, self.sweep_f2, self.sweep_pts)
        self.rec = pattern_band.recommend(self.sweep_f1, self.sweep_f2,
                                          self.sweep_step)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._intro())

        # -- enable ----------------------------------------------------------
        self.enable = QtWidgets.QCheckBox(
            "Compute a radiation pattern at several frequencies")
        self.enable.setToolTip(
            "Off = one pattern at the best-match frequency (the default, and "
            "what every earlier run produced).")
        layout.addWidget(self.enable)

        self.body = QtWidgets.QWidget(self)
        form = QtWidgets.QFormLayout(self.body)
        form.setContentsMargins(18, 4, 0, 0)

        # -- band ------------------------------------------------------------
        self.use_sweep = QtWidgets.QCheckBox(
            "Use the analysis sweep band  ({0:.4g} – {1:.4g} MHz)".format(
                self.sweep_f1 / MHZ, self.sweep_f2 / MHZ))
        self.use_sweep.setToolTip(
            "Uncheck to compute patterns over only PART of the swept band — "
            "usually what you want, since the interesting patterns cluster "
            "around resonance and each one costs output.")
        form.addRow(self.use_sweep)

        self.start = self._freq_spin("First pattern frequency.")
        self.stop = self._freq_spin("Last pattern frequency.")
        form.addRow("Start (MHz)", self.start)
        form.addRow("Stop (MHz)", self.stop)

        # -- step ------------------------------------------------------------
        self.step = self._freq_spin(
            "Spacing between patterns. The recommended value is a whole "
            "number of analysis sweep steps, so every pattern lands on a "
            "frequency the S11 curve was actually sampled at.")
        self.step.setDecimals(6)
        self.step.setMinimum(1e-6)
        step_row = QtWidgets.QHBoxLayout()
        step_row.addWidget(self.step, 1)
        self.reset_btn = QtWidgets.QPushButton("Use recommended", self)
        self.reset_btn.clicked.connect(self._apply_recommended)
        step_row.addWidget(self.reset_btn)
        form.addRow("Step (MHz)", step_row)

        self.summary = QtWidgets.QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(QtCore.Qt.RichText)
        form.addRow(self.summary)

        layout.addWidget(self.body)
        layout.addStretch(1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_from_solver()
        for w in (self.start, self.stop, self.step):
            w.valueChanged.connect(self._refresh)
        self.use_sweep.toggled.connect(self._band_toggled)
        self.enable.toggled.connect(self._enable_toggled)
        self._enable_toggled(self.enable.isChecked())

    # -- construction helpers -------------------------------------------------
    def _intro(self):
        lab = QtWidgets.QLabel(
            "NEC2 evaluates the pattern at every step of its frequency card, so "
            "N patterns cost <b>one</b> extra solver run, not N (measured: 201 "
            "patterns in 7.18 s). What they cost is output — about "
            "{0:.2f} MB each.".format(pattern_band.MB_PER_PATTERN))
        lab.setWordWrap(True)
        return lab

    def _freq_spin(self, tip):
        box = QtWidgets.QDoubleSpinBox(self)
        box.setDecimals(4)
        box.setRange(1e-6, 1e9)          # MHz: 1 Hz to 1000 THz
        box.setToolTip(tip)
        return box

    # -- state ----------------------------------------------------------------
    def _load_from_solver(self):
        count = int(getattr(self.solver, "PatternFrequencies", 0) or 0)
        f1, f2 = pattern_band.resolve_band(self.solver, self.sweep_f1,
                                           self.sweep_f2)
        overridden = (
            pattern_band.to_hz(getattr(self.solver, "PatternFreqStart", 0)) > 0
            and pattern_band.to_hz(getattr(self.solver, "PatternFreqStop", 0)) > 0)

        self.enable.setChecked(count > 1)
        self.use_sweep.setChecked(not overridden)
        self.start.setValue(f1 / MHZ)
        self.stop.setValue(f2 / MHZ)
        # An existing count implies the step it was solved at; a fresh solver
        # gets the recommendation.
        if count > 1:
            self.step.setValue(pattern_band.step_hz(f1, f2, count) / MHZ)
        else:
            self.step.setValue(self.rec["step_hz"] / MHZ)
        self._refresh()

    def _apply_recommended(self):
        """Recommend against the band ON SCREEN, not the sweep.

        Recomputing from the sweep would silently ignore a band the user had
        just narrowed, and the button would look broken.
        """
        f1 = self.start.value() * MHZ
        f2 = self.stop.value() * MHZ
        rec = pattern_band.recommend(f1, f2, self.sweep_step)
        self.step.setValue(rec["step_hz"] / MHZ)

    def _band_toggled(self, on):
        self.start.setEnabled(not on)
        self.stop.setEnabled(not on)
        if on:
            self.start.setValue(self.sweep_f1 / MHZ)
            self.stop.setValue(self.sweep_f2 / MHZ)
        self._refresh()

    def _enable_toggled(self, on):
        self.body.setEnabled(on)
        if on:
            self._band_toggled(self.use_sweep.isChecked())
        self._refresh()

    # -- derived --------------------------------------------------------------
    def resolved(self):
        """(count, f1_hz, f2_hz) as they will be STORED.

        The stop is pulled back to the last frequency the chosen step actually
        reaches. NEC2 derives its step from (band / count-1), so storing the
        requested stop with a count that does not divide it would solve at a
        step the user never asked for — a silent disagreement between the
        dialog and the deck.
        """
        f1 = self.start.value() * MHZ
        f2 = self.stop.value() * MHZ
        if not self.enable.isChecked() or f2 <= f1:
            return 0, f1, f2
        step = self.step.value() * MHZ
        count = pattern_band.count_for_step(f1, f2, step)
        return count, f1, f1 + (count - 1) * step

    def _refresh(self):
        if not self.enable.isChecked():
            self.summary.setText(
                "<b>One pattern</b>, at the best-match frequency — the "
                "results dialog will show it with no frequency picker.")
            return
        count, f1, f2 = self.resolved()
        if count < 2:
            self.summary.setText(
                "<span style='color:#b00000'>Stop must be above start.</span>")
            return
        lines = ["<b>{0}</b>".format(pattern_band.describe(f1, f2, count))]
        requested = self.stop.value() * MHZ
        if abs(f2 - requested) > 1.0:
            lines.append(
                "Last pattern lands at {0:.4g} MHz — a {1:.4g} MHz step does "
                "not reach {2:.4g} MHz exactly. This is the band that will be "
                "stored.".format(f2 / MHZ, self.step.value(), requested / MHZ))
        if self.rec.get("on_sweep_points"):
            lines.append("<i>Recommended: {0:.4g} MHz — {1}.</i>".format(
                self.rec["step_hz"] / MHZ, self.rec["note"]))
        self.summary.setText("<br>".join(lines))

    # -- commit ---------------------------------------------------------------
    def apply_to_solver(self):
        """Write the choice onto the solver. Returns a one-line description."""
        count, f1, f2 = self.resolved()
        self.solver.PatternFrequencies = int(count)
        # Store 0/0 ("follow the sweep") only when the resolved band really IS
        # the sweep. Keying this off the checkbox instead was wrong: with the
        # box ticked and a step that does not divide the sweep evenly, the
        # runner would re-derive step = span/(count-1) over the FULL sweep and
        # solve at a spacing the dialog never showed. The checkbox chooses
        # where the band comes from; what gets stored is whatever reproduces
        # the step on screen.
        #
        # App::PropertyFrequency's internal unit is Hz (verified against a
        # saved document: 10 MHz stores as 10000000.0), so a plain float is
        # exact and skips a locale-sensitive string parse.
        follows_sweep = count < 2 or (abs(f1 - self.sweep_f1) <= 1.0
                                      and abs(f2 - self.sweep_f2) <= 1.0)
        self.solver.PatternFreqStart = 0.0 if follows_sweep else float(f1)
        self.solver.PatternFreqStop = 0.0 if follows_sweep else float(f2)
        if count < 2:
            return "one pattern, at the best-match frequency"
        return pattern_band.describe(f1, f2, count)
