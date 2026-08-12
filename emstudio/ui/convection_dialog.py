# SPDX-License-Identifier: LGPL-2.1-or-later
"""Convection Designer — solve what confinement and bundling cost a cable.

WHY THIS IS QUESTION-SHAPED AND NOT A CFD PANEL
------------------------------------------------
FreeCAD already has general CFD front ends. Competing with them is a losing
game, and worse, a generic panel helps only a user who has ALREADY decided to
run CFD. The user who needs this most is the one who never opens it and simply
reads an optimistic ampacity number.

So this dialog asks one question — *what does this bundle in this enclosure do
to the film coefficient?* — states the answer the product is using TODAY
(Churchill-Chu, isolated cable, unbounded still air), and offers to replace the
assumption with a solve. The advice panel is populated by
:mod:`emstudio.assistant.thermal_advice` where Pro is present, and degrades to
the same facts in plainer form where it is not.

⚠ **This runs a real CFD solve: minutes, not milliseconds.** The dialog says so
before starting, reports progress, and can be cancelled. The result is a single
dimensionless factor precisely so it can be CACHED — `thermal.solve_steady`
bisects and calls `surface_h` ~80 times per ampacity answer, so nothing
interactive may ever trigger a solve.

Qt is imported lazily and the compute path is importable without it, so the
engine stays testable headless.
"""

from __future__ import annotations

import math

from emstudio.wire import bundle_convection as bc
from emstudio.wire.thermal import nu_churchill_chu

#: The measured reference, quoted in the UI so the user sees a magnitude before
#: committing minutes to a solve. Trefoil of three 20 mm cables at 30 mm pitch
#: in a 200 mm enclosure.
REFERENCE_TEXT = ("Measured reference: a trefoil of three 20 mm cables in a "
                  "200 mm enclosure solves to a factor of 0.80 — Churchill-Chu "
                  "over-predicts the film coefficient by about 25 %, and it "
                  "errs toward MORE cooling than is really there.")


def describe_plan(centres, d_cable, box_w, box_h):
    """What is about to be solved, in prose, before any time is spent."""
    n = len(centres)
    reach = max(math.hypot(x, y) for x, y in centres) + d_cable / 2.0
    return ("%d cable%s of %.1f mm in a %.0f x %.0f mm enclosure "
            "(bundle extent %.1f mm)."
            % (n, "" if n == 1 else "s", 1000.0 * d_cable,
               1000.0 * box_w, 1000.0 * box_h, 2000.0 * reach))


def advice_for(n_cables, enclosed, factor=1.0, provenance="", converged=None,
               nec_adjustment_applied=False):
    """Guardrail notes, from the Pro assistant when present.

    ⚠ Falls back to the SAME warning in plainer words rather than going silent.
    The free tier gets correct maths and honest warnings; what Pro adds is the
    assistant noticing on the user's behalf. Silence would turn a tier
    boundary into a correctness difference, which it must never be.
    """
    try:
        from emstudio.assistant import thermal_advice
        return thermal_advice.convection_advice(
            n_cables=n_cables, enclosed=enclosed, bundle_factor=factor,
            provenance=provenance, converged=converged,
            nec_adjustment_applied=nec_adjustment_applied)
    except ImportError:
        notes = []
        if abs(factor - 1.0) < 1e-12 and (n_cables > 1 or enclosed):
            notes.append(
                "This ampacity uses Churchill-Chu, which assumes one cable in "
                "unbounded still air. This design is a bundle and/or confined, "
                "so the rating is optimistic. Solve the convection to replace "
                "the assumption with a measured factor.")
        if abs(factor - 1.0) > 1e-12 and not provenance:
            notes.append("This factor carries no provenance and cannot be "
                         "re-checked.")
        if abs(factor - 1.0) > 1e-12 and converged is False:
            notes.append("This factor came from a solve that did not "
                         "converge; it is provisional.")
        return notes


def summarise(result):
    """The solved factor as a sentence a cable engineer would write."""
    return ("Bundle factor %.4f — Churchill-Chu over-predicts the film "
            "coefficient by %+.1f %%. Solved Nu %.4f against the "
            "correlation's %.4f at Ra %.4g."
            % (result.factor, result.correlation_error_pct, result.nu_solved,
               result.nu_correlation, result.ra_d))


def build_dialog(centres, d_cable, box_w, box_h, parent=None):   # pragma: no cover
    """The Qt dialog. Imported lazily so the module stays headless-testable."""
    from PySide import QtCore, QtWidgets

    class ConvectionDialog(QtWidgets.QDialog):
        def __init__(self):
            super(ConvectionDialog, self).__init__(parent)
            self.setWindowTitle("Convection Designer — bundle factor")
            self.result_obj = None
            lay = QtWidgets.QVBoxLayout(self)

            lay.addWidget(QtWidgets.QLabel("<b>What will be solved</b>"))
            lay.addWidget(QtWidgets.QLabel(
                describe_plan(centres, d_cable, box_w, box_h)))

            cur = QtWidgets.QLabel(
                "<b>What the ampacity uses today</b><br>"
                "Churchill-Chu — one cable, unbounded still air.<br><i>"
                + REFERENCE_TEXT + "</i>")
            cur.setWordWrap(True)
            lay.addWidget(cur)

            self.notes = QtWidgets.QLabel("")
            self.notes.setWordWrap(True)
            self.notes.setStyleSheet("color: #a05000;")
            for n in advice_for(len(centres), True):
                self.notes.setText(self.notes.text() + "⚠ " + n + "\n\n")
            lay.addWidget(self.notes)

            # ⚠ Tell the user the cost BEFORE they spend it.
            warn = QtWidgets.QLabel(
                "<b>This runs a CFD solve and takes minutes.</b> The result is "
                "a single cached factor; nothing interactive re-runs it.")
            warn.setWordWrap(True)
            lay.addWidget(warn)

            self.bar = QtWidgets.QProgressBar()
            self.bar.setRange(0, 0)
            self.bar.hide()
            lay.addWidget(self.bar)

            self.out = QtWidgets.QLabel("")
            self.out.setWordWrap(True)
            lay.addWidget(self.out)

            box = QtWidgets.QDialogButtonBox()
            self.solve_btn = box.addButton("Solve convection…",
                                           QtWidgets.QDialogButtonBox.ActionRole)
            box.addButton(QtWidgets.QDialogButtonBox.Close)
            box.rejected.connect(self.reject)
            self.solve_btn.clicked.connect(self._solve)
            lay.addWidget(box)

        def _solve(self):
            self.solve_btn.setEnabled(False)
            self.bar.show()
            QtWidgets.QApplication.processEvents()
            try:
                res = bc.solve_bundle_factor(centres, d_cable, box_w=box_w,
                                             box_h=box_h)
            except Exception as exc:            # a failed solve is REPORTED
                self.out.setText("<b>The solve did not complete.</b><br>%s"
                                 % exc)
                self.bar.hide()
                self.solve_btn.setEnabled(True)
                return
            self.result_obj = res
            text = "<b>" + summarise(res) + "</b><br><br>" + res.provenance
            for n in advice_for(len(centres), True, factor=res.factor,
                                provenance=res.provenance,
                                converged=res.converged):
                text += "<br><br>⚠ " + n
            for w in res.warnings:
                text += "<br><br>⚠ " + w
            self.out.setText(text)
            self.bar.hide()
            self.solve_btn.setEnabled(True)

    return ConvectionDialog()


def enclosure_side(centres, d_cable, clearance_ratio):
    """Square enclosure side from the bundle's own extent.

    Shared with the command so the dialog and the solve size the SAME box —
    two independent sizings would mean the factor was solved for a geometry
    the dialog never showed.
    """
    return bc._enclosure_for(centres, d_cable, clearance_ratio)
