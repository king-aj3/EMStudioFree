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


def as_cables(geometry, d_cable=None):
    """Normalise ``[(x, y)]`` + a diameter, or ``[(x, y, d)]``, to the latter.

    The dialog and the command both hand geometry straight to the solver, so
    one shape here is what stops a mixed bundle being described with a single
    diameter it does not have.
    """
    out = []
    for c in geometry:
        if len(c) == 3:
            out.append((float(c[0]), float(c[1]), float(c[2])))
        elif d_cable is None:
            raise ValueError("a cable is (x, y, diameter), or (x, y) with a "
                             "diameter given separately")
        else:
            out.append((float(c[0]), float(c[1]), float(d_cable)))
    return out


def size_counts(cables):
    """``[(d, n)]``, largest diameter first."""
    counts = {}
    for _x, _y, d in cables:
        counts[round(float(d), 12)] = counts.get(round(float(d), 12), 0) + 1
    return sorted(counts.items(), reverse=True)


def describe_plan(geometry, d_cable=None, box_w=None, box_h=None):
    """What is about to be solved, in prose, before any time is spent.

    ⚠ A mixed bundle is described SIZE BY SIZE. Quoting one diameter for a
    bundle that has three is exactly how a user ends up believing the number
    applies to the cable they care about.
    """
    cables = as_cables(geometry, d_cable)
    n = len(cables)
    reach = max(math.hypot(x, y) + d / 2.0 for x, y, d in cables)
    sizes = size_counts(cables)
    if len(sizes) == 1:
        what = "%d cable%s of %.1f mm" % (n, "" if n == 1 else "s",
                                          1000.0 * sizes[0][0])
    else:
        what = "%d cables in %d sizes (%s)" % (
            n, len(sizes),
            ", ".join("%d x %.1f mm" % (c, 1000.0 * d) for d, c in sizes))
    return ("%s in a %.0f x %.0f mm enclosure (bundle extent %.1f mm).%s"
            % (what, 1000.0 * box_w, 1000.0 * box_h, 2000.0 * reach,
               "" if len(sizes) == 1 else
               " Each size is solved on its own surface and gets its own "
               "Nusselt number and its own factor — nothing is averaged "
               "across unlike cables."))


def advice_for(n_cables, enclosed, factor=1.0, provenance="", converged=None,
               nec_adjustment_applied=False, sizes=1):
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
            nec_adjustment_applied=nec_adjustment_applied, sizes=sizes)
    except ImportError:
        notes = []
        if abs(factor - 1.0) < 1e-12 and (n_cables > 1 or enclosed):
            notes.append(
                "This ampacity uses Churchill-Chu, which assumes one cable in "
                "unbounded still air. This design is a bundle and/or confined, "
                "so the rating is optimistic. Solve the convection to replace "
                "the assumption with a measured factor.")
        if sizes > 1:
            notes.append(
                "This bundle mixes %d cable sizes, so it has %d factors and "
                "not one — Nu_D is built on a diameter. Apply each size's own "
                "factor to that size; a single number for the whole bundle "
                "either under-rates the sizes that cool well or over-rates "
                "the one that does not." % (sizes, sizes))
        if abs(factor - 1.0) > 1e-12 and not provenance:
            notes.append("This factor carries no provenance and cannot be "
                         "re-checked.")
        if abs(factor - 1.0) > 1e-12 and converged is False:
            notes.append("This factor came from a solve that did not "
                         "converge; it is provisional.")
        return notes


def summarise(result):
    """The solved factor as a sentence a cable engineer would write.

    Handles both a single :class:`~emstudio.wire.bundle_convection.BundleFactor`
    and a per-size :class:`~emstudio.wire.bundle_convection.MixedBundleFactor`.
    """
    by_size = getattr(result, "by_size", None)
    if by_size is None:
        return ("Bundle factor %.4f — Churchill-Chu over-predicts the film "
                "coefficient by %+.1f %%. Solved Nu %.4f against the "
                "correlation's %.4f at Ra %.4g."
                % (result.factor, result.correlation_error_pct,
                   result.nu_solved, result.nu_correlation, result.ra_d))
    lines = ["This bundle has %d cable sizes, so it has %d factors — one per "
             "size, all solved together in the same enclosure:"
             % (len(by_size), len(by_size))]
    for d in result.sizes:
        f = by_size[d]
        lines.append(
            "  %.1f mm (%d off): factor %.4f — Churchill-Chu over-predicts "
            "by %+.1f %%. Nu %.4f vs %.4f at Ra %.4g."
            % (1000.0 * d, f.n_cables, f.factor, f.correlation_error_pct,
               f.nu_solved, f.nu_correlation, f.ra_d))
    lines.append(
        "Rate each size with its own factor. If you must use ONE, use %.4f "
        "(the %.1f mm size) — it is the most pessimistic, and anything less "
        "conservative over-rates that cable."
        % (result.worst.factor, 1000.0 * result.worst.d_cable))
    return "\n".join(lines)


def build_dialog(geometry, d_cable, box_w, box_h, parent=None):  # pragma: no cover
    """The Qt dialog. Imported lazily so the module stays headless-testable.

    ``geometry`` is ``[(x, y, d)]`` (mixed diameters welcome) or ``[(x, y)]``
    with ``d_cable`` supplying the one diameter.
    """
    from PySide import QtCore, QtWidgets

    cables = as_cables(geometry, d_cable)
    mixed = len(size_counts(cables)) > 1

    class ConvectionDialog(QtWidgets.QDialog):
        def __init__(self):
            super(ConvectionDialog, self).__init__(parent)
            self.setWindowTitle("Convection Designer — bundle factor")
            self.result_obj = None
            lay = QtWidgets.QVBoxLayout(self)

            lay.addWidget(QtWidgets.QLabel("<b>What will be solved</b>"))
            plan = QtWidgets.QLabel(describe_plan(cables, box_w=box_w,
                                                  box_h=box_h))
            plan.setWordWrap(True)
            lay.addWidget(plan)

            cur = QtWidgets.QLabel(
                "<b>What the ampacity uses today</b><br>"
                "Churchill-Chu — one cable, unbounded still air.<br><i>"
                + REFERENCE_TEXT + "</i>")
            cur.setWordWrap(True)
            lay.addWidget(cur)

            self.notes = QtWidgets.QLabel("")
            self.notes.setWordWrap(True)
            self.notes.setStyleSheet("color: #a05000;")
            for n in advice_for(len(cables), True, sizes=len(size_counts(cables))):
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
                # ⚠ The MIXED entry point handles a uniform set too and gives
                # the identical answer, but the uniform path is kept for the
                # uniform case so the shipped single-factor result type — the
                # one SolverOpenFOAM caches — is unchanged.
                if mixed:
                    res = bc.solve_mixed_bundle_factor(cables, box_w=box_w,
                                                       box_h=box_h)
                else:
                    res = bc.solve_bundle_factor(
                        [(x, y) for x, y, _d in cables], cables[0][2],
                        box_w=box_w, box_h=box_h)
            except Exception as exc:            # a failed solve is REPORTED
                self.out.setText("<b>The solve did not complete.</b><br>%s"
                                 % exc)
                self.bar.hide()
                self.solve_btn.setEnabled(True)
                return
            self.result_obj = res
            text = ("<b>" + summarise(res).replace("\n", "<br>")
                    + "</b><br><br>" + res.provenance)
            worst = res.worst.factor if mixed else res.factor
            for n in advice_for(len(cables), True, factor=worst,
                                provenance=res.provenance,
                                converged=res.converged,
                                sizes=len(size_counts(cables))):
                text += "<br><br>⚠ " + n
            for w in res.warnings:
                text += "<br><br>⚠ " + w
            self.out.setText(text)
            self.bar.hide()
            self.solve_btn.setEnabled(True)

    return ConvectionDialog()


def enclosure_side(geometry, d_cable, clearance_ratio):
    """Square enclosure side from the bundle's own extent.

    Shared with the command so the dialog and the solve size the SAME box —
    two independent sizings would mean the factor was solved for a geometry
    the dialog never showed.

    ⚠ On a mixed bundle the reach is taken PER CABLE: the outermost centre is
    not always the one that reaches furthest, so sizing on one diameter can
    build a box a fatter inner cable does not fit.
    """
    return bc._enclosure_for(as_cables(geometry, d_cable), d_cable,
                             clearance_ratio)
