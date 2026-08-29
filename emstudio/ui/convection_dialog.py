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
    """Normalise the accepted geometry shapes to ``(x, y, d[, gradient])``.

    Accepts ``[(x, y)]`` with a separate diameter, ``[(x, y, d)]``, or
    ``[(x, y, d, gradient)]``. The dialog and the command both hand geometry
    straight to the solver, so one shape here is what stops a mixed bundle
    being described with a single diameter it does not have.

    ⚠ A 4-tuple's gradient is PRESERVED, not dropped. Two cables of one size on
    different fluxes are different thermal cables, and a normaliser that
    quietly flattened them would make the dialog describe a bundle that is not
    the one being solved.
    """
    out = []
    for c in geometry:
        if len(c) == 4:
            out.append((float(c[0]), float(c[1]), float(c[2]), float(c[3])))
        elif len(c) == 3:
            out.append((float(c[0]), float(c[1]), float(c[2])))
        elif d_cable is None:
            raise ValueError("a cable is (x, y, diameter[, gradient]), or "
                             "(x, y) with a diameter given separately")
        else:
            out.append((float(c[0]), float(c[1]), float(d_cable)))
    return out


def size_counts(cables):
    """``[(d, n)]``, largest diameter first."""
    counts = {}
    for c in cables:
        d = round(float(c[2]), 12)
        counts[d] = counts.get(d, 0) + 1
    return sorted(counts.items(), reverse=True)


def group_counts(cables):
    """``[((d, gradient), n)]`` — the units that each get their own factor.

    A group is one diameter at one wall flux, because that is what one snappy
    patch carries. Equals :func:`size_counts` whenever the loading is uniform;
    it exceeds it when the Cable Designer's per-member **Current (A)** column
    is filled, since cables of one size on different currents run at different
    temperatures and get their own factors.
    """
    counts = {}
    for c in cables:
        k = (round(float(c[2]), 12),
             round(float(c[3]), 12) if len(c) > 3 else None)
        counts[k] = counts.get(k, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[0][0],
                                                  -(kv[0][1] or 0.0)))


def describe_plan(geometry, d_cable=None, box_w=None, box_h=None):
    """What is about to be solved, in prose, before any time is spent.

    ⚠ A mixed bundle is described SIZE BY SIZE. Quoting one diameter for a
    bundle that has three is exactly how a user ends up believing the number
    applies to the cable they care about — and a bundle of ONE size whose
    cables carry different loads is described as that too, because it looks
    uniform and is not.

    ⚠ Indexes ``c[0..2]`` rather than unpacking: a cable may be a 3-tuple or a
    4-tuple with its own gradient, and unpacking would raise on the loaded path
    only — the one this text most needs to describe correctly.
    """
    cables = as_cables(geometry, d_cable)
    n = len(cables)
    reach = max(math.hypot(c[0], c[1]) + c[2] / 2.0 for c in cables)
    sizes = size_counts(cables)
    groups = group_counts(cables)
    if len(sizes) == 1:
        what = "%d cable%s of %.1f mm" % (n, "" if n == 1 else "s",
                                          1000.0 * sizes[0][0])
    else:
        what = "%d cables in %d sizes (%s)" % (
            n, len(sizes),
            ", ".join("%d x %.1f mm" % (c, 1000.0 * d) for d, c in sizes))
    if len(groups) == 1:
        note = ""
    elif len(groups) > len(sizes):
        note = (" %d of these carry different heat loads, so the bundle has "
                "%d groups — each is solved on its own surface and gets its "
                "own Nusselt number and its own factor. Cables of one size on "
                "different currents are not thermally interchangeable."
                % (n, len(groups)))
    else:
        note = (" Each size is solved on its own surface and gets its own "
                "Nusselt number and its own factor — nothing is averaged "
                "across unlike cables.")
    return ("%s in a %.0f x %.0f mm enclosure (bundle extent %.1f mm).%s"
            % (what, 1000.0 * box_w, 1000.0 * box_h, 2000.0 * reach, note))


def advice_for(n_cables, enclosed, factor=1.0, provenance="", converged=None,
               nec_adjustment_applied=False, sizes=1, groups=None):
    """Guardrail notes, from the Pro assistant when present.

    ⚠ Falls back to the SAME warning in plainer words rather than going silent.
    The free tier gets correct maths and honest warnings; what Pro adds is the
    assistant noticing on the user's behalf. Silence would turn a tier
    boundary into a correctness difference, which it must never be.
    """
    n_groups = int(groups if groups is not None else sizes)
    try:
        from emstudio.assistant import thermal_advice
    except ImportError:
        thermal_advice = None
    if thermal_advice is not None:
        # ⚠ AdviceProblem becomes a NOTE here, never an exception: advice_for
        # is called from _poll mid-solve (and from the dialog open), and
        # check_factor's raise used to escape both call sites uncaught — the
        # companion defect the 2026-08-24 audit filed. An implausible factor
        # is exactly when the user most needs the advice to REACH them.
        try:
            return thermal_advice.convection_advice(
                n_cables=n_cables, enclosed=enclosed, bundle_factor=factor,
                provenance=provenance, converged=converged,
                nec_adjustment_applied=nec_adjustment_applied, sizes=sizes,
                groups=n_groups)
        except thermal_advice.AdviceProblem as exc:
            return [str(exc)]
    # ⚠⚠ The FREE tier's PRODUCTION advice path — every Convection Designer
    # open and every CFD solve on a free install runs THIS half, while dev
    # trees only ever run the Pro half above. The 2026-08-24 audit CONFIRMED
    # it litz-class (two real parity breaks vs Pro, zero gate coverage on
    # either half) and it was FIXED the same day: rule 4 (NEC double-count)
    # and the plausible-band check are mirrored below, and the
    # `convection_advice_parity` gate (FAST, Pro-only) now compares the
    # fired warning CONDITIONS of this fallback, run in a child interpreter
    # whose emstudio.assistant import is BLOCKED, against the real
    # thermal_advice rule by rule — so the docstring's same-warnings claim
    # is enforced, not aspirational.
    # The plausible-band check, mirrored from Pro's check_factor and
    # SHORT-CIRCUITING exactly as check_factor does (it is Pro's first
    # statement, so an implausible factor yields ONLY the band note on
    # both tiers). A NOTE, not a raise — see the AdviceProblem comment
    # above. ⚠ The bounds duplicate Pro's PLAUSIBLE_FACTOR (0.30, 1.30)
    # BY VALUE, unavoidably — this tree cannot import the Pro constant,
    # and the parity gate reds if the two drift apart.
    try:
        _f = float(factor)
    except (TypeError, ValueError):
        _f = float("nan")
    if not math.isfinite(_f) or _f <= 0 or not (0.30 <= _f <= 1.30):
        return [
            "The bundle factor %r is outside the plausible band "
            "[0.30, 1.30], or is not a finite number. Below 0.30 implies "
            "confinement more severe than a sealed box; above 1.30 "
            "implies the bundle cools BETTER than a lone cable, which "
            "needs forced flow. Check what produced it before sizing "
            "anything on it." % (factor,)]
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
    # ⚠ The free tier must carry this too, and it is the note most easily
    # lost: a bundle of ONE diameter has sizes == 1, so the note above
    # never fires, and the design looks uniform while its cables have
    # different factors.
    if n_groups > sizes:
        notes.append(
            "Some cables here are the same SIZE but carry different "
            "losses, so this bundle has %d factors across %d diameter%s. "
            "Cables of one size stop being thermally interchangeable once "
            "their currents differ. Rate each by its own size AND loss."
            % (n_groups, sizes, "" if sizes == 1 else "s"))
    if abs(factor - 1.0) > 1e-12 and not provenance:
        notes.append("This factor carries no provenance and cannot be "
                     "re-checked.")
    # Rule 4's mirror — the parity break the 2026-08-24 audit confirmed: this
    # argument was accepted and forwarded to Pro but IGNORED here, so the
    # double-derating warning never reached a free user. Same guard as Pro:
    # a BARE factor (1.0) plus the NEC table is single-derating and must not
    # fire (the verifier's precision).
    if abs(factor - 1.0) > 1e-12 and nec_adjustment_applied:
        notes.append("Both a solved bundle factor and the NEC 310.15(C)(1) "
                     "adjustment are applied. They correct the SAME effect — "
                     "one measured for this geometry, one tabulated by "
                     "conductor count — so using both derates twice. Pick "
                     "one: the solved factor if the geometry is real, the "
                     "NEC table if the install must be code-compliant.")
    if abs(factor - 1.0) > 1e-12 and converged is False:
        notes.append("This factor came from a solve that did not "
                     "converge; it is provisional.")
    return notes


def summarise(result):
    """The solved factor as a sentence a cable engineer would write.

    Handles both a single :class:`~emstudio.wire.bundle_convection.BundleFactor`
    and a per-group :class:`~emstudio.wire.bundle_convection.MixedBundleFactor`.

    ⚠ Detects the mixed case on ``by_group``, never on ``by_size``: the latter
    is a property that RAISES when one diameter carries several groups, and
    ``getattr(obj, name, default)`` only swallows AttributeError — a ValueError
    would escape straight through a "safe" lookup.
    """
    by_group = getattr(result, "by_group", None)
    if by_group is None:
        return ("Bundle factor %.4f — Churchill-Chu over-predicts the film "
                "coefficient by %+.1f %%. Solved Nu %.4f against the "
                "correlation's %.4f at Ra %.4g."
                % (result.factor, result.correlation_error_pct,
                   result.nu_solved, result.nu_correlation, result.ra_d))
    n_sizes = len(result.sizes)
    what = ("%d cable sizes" % n_sizes if len(by_group) == n_sizes
            else "%d groups across %d cable sizes (some sizes carry different "
                 "losses)" % (len(by_group), n_sizes))
    lines = ["This bundle has %s, so it has %d factors — all solved together "
             "in the same enclosure:" % (what, len(by_group))]
    for f in by_group.values():
        # ⚠ Name the FLUX as well as the size. On a bundle with two same-size
        # groups the diameter alone does not say which line is which.
        lines.append(
            "  %.1f mm at %.4g K/m (%d off): factor %.4f — Churchill-Chu "
            "over-predicts by %+.1f %%. Nu %.4f vs %.4f at Ra %.4g."
            % (1000.0 * f.d_cable, f.gradient, f.n_cables, f.factor,
               f.correlation_error_pct, f.nu_solved, f.nu_correlation, f.ra_d))
    w = result.worst
    lines.append(
        "Rate each cable with its own factor. If you must use ONE, use %.4f "
        "(the %.1f mm at %.4g K/m) — it is the most pessimistic, and anything "
        "less conservative over-rates that cable."
        % (w.factor, 1000.0 * w.d_cable, w.gradient))
    return "\n".join(lines)


def build_dialog(geometry, d_cable, box_w, box_h, parent=None,
                 reference=False):  # pragma: no cover
    """The Qt dialog. Imported lazily so the module stays headless-testable.

    ``geometry`` is ``[(x, y, d)]`` (mixed diameters welcome) or ``[(x, y)]``
    with ``d_cable`` supplying the one diameter.

    ``reference=True`` marks the geometry as the BUILT-IN reference trefoil
    rather than anything from the user's document, and the dialog says so in
    red — a user with a helical coil on screen read "3 cables" as a solve of
    their document and had no way to know otherwise (AJ, 2026-08-17).
    """
    from PySide import QtCore, QtWidgets

    cables = as_cables(geometry, d_cable)
    # ⚠ GROUPS, not sizes. A bundle of ONE diameter whose cables carry
    # different currents has one size and several groups, and routing it to
    # the single-diameter solver would collapse those loads into one answer —
    # the exact failure the per-group work exists to prevent.
    mixed = len(group_counts(cables)) > 1

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

            if reference:
                ref = QtWidgets.QLabel(
                    "<b>⚠ This is the built-in REFERENCE trefoil — three "
                    "20 mm cables at 30 mm pitch — NOT geometry from your "
                    "document.</b> Nothing in the 3-D view is read by this "
                    "solve. To solve your own bundle, open the Cable "
                    "Designer's Bundle configuration and press its Solve "
                    "convection button — that passes the real cable table "
                    "to this dialog.")
                ref.setWordWrap(True)
                ref.setStyleSheet("color: #a00000;")
                lay.addWidget(ref)

            cur = QtWidgets.QLabel(
                "<b>What the ampacity uses today</b><br>"
                "Churchill-Chu — one cable, unbounded still air.<br><i>"
                + REFERENCE_TEXT + "</i>")
            cur.setWordWrap(True)
            lay.addWidget(cur)

            self.notes = QtWidgets.QLabel("")
            self.notes.setWordWrap(True)
            self.notes.setStyleSheet("color: #a05000;")
            for n in advice_for(len(cables), True, sizes=len(size_counts(cables)),
                                groups=len(group_counts(cables))):
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
            self.cancel_btn = box.addButton(
                "Cancel solve", QtWidgets.QDialogButtonBox.ActionRole)
            self.cancel_btn.setEnabled(False)
            box.addButton(QtWidgets.QDialogButtonBox.Close)
            box.rejected.connect(self.reject)
            self.solve_btn.clicked.connect(self._solve)
            self.cancel_btn.clicked.connect(self._cancel_solve)
            lay.addWidget(box)

            # ⚠ The solve runs on a WORKER THREAD, never the GUI thread. The
            # first shipped version ran it synchronously with one
            # processEvents() before the chain started, so the event loop was
            # frozen for the whole multi-minute CFD — the Close button, while
            # visibly present, could not be serviced until the very solve it
            # was meant to stop had finished (AJ, 2026-08-17). Same disease
            # installer_dialog.refresh() had; same worker + polling-timer
            # idiom cures it.
            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self._poll)
            # ⚠ Per-RUN state dict, captured by the worker's closure — the
            # installer idiom, verbatim. An abandoned worker from an earlier
            # run can then never scribble on a later run's flags, by
            # construction rather than by invariant.
            self._run = None

        def _solve(self):
            import threading

            # Minutes, not seconds — ask before committing the user to it.
            from emstudio.ui import run_gui
            # ⚠ The work measure comes from the CLOSURE's geometry, not from
            # the dialog: this class has no cable count to read, and the
            # version that tried to read one off `self` priced every bundle
            # the same. See _trefoil_work.
            if not run_gui.confirm_solve_work(
                    self, "openfoam", _trefoil_work(cables, box_w, box_h),
                    label="Convection on the reference trefoil (OpenFOAM)"):
                return

            state = {"done": False, "result": None, "error": None,
                     "cancel": threading.Event()}
            self._run = state

            def work():
                # Only the captured state dict is written from here — no
                # widget is safe to touch off the GUI thread, and the dialog
                # may already be closed by the time the chain winds down.
                try:
                    # ⚠ The MIXED entry point handles a uniform set too and
                    # gives the identical answer, but the uniform path is kept
                    # for the uniform case so the shipped single-factor result
                    # type — the one SolverOpenFOAM caches — is unchanged.
                    if mixed:
                        state["result"] = bc.solve_mixed_bundle_factor(
                            cables, box_w=box_w, box_h=box_h,
                            cancel=state["cancel"])
                    else:
                        state["result"] = bc.solve_bundle_factor(
                            [(c[0], c[1]) for c in cables], cables[0][2],
                            box_w=box_w, box_h=box_h, cancel=state["cancel"])
                except Exception as exc:        # a failed solve is REPORTED
                    state["error"] = exc
                finally:
                    # ⚠ In a finally: a BaseException the except above misses
                    # must not leave the dialog stuck "solving" forever with
                    # Solve disabled and the bar spinning.
                    state["done"] = True

            self.solve_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.bar.show()
            self.out.setText("")
            threading.Thread(target=work, daemon=True).start()
            self._timer.start(200)

        def _cancel_solve(self):
            if self._run is not None:
                self._run["cancel"].set()
            self.cancel_btn.setEnabled(False)
            self.out.setText("Cancelling — stopping the OpenFOAM chain…")

        def reject(self):
            # Closing the dialog mid-solve CANCELS the solve: a multi-minute
            # chain grinding on behind a closed window is the worst of both
            # worlds. The worker writes only its own state dict, so it is
            # safe to let it wind down after the widgets are gone.
            if self._run is not None and not self._run["done"]:
                self._run["cancel"].set()
            super(ConvectionDialog, self).reject()

        def _poll(self):
            state = self._run
            if state is None or not state["done"]:
                return
            self._timer.stop()
            self.bar.hide()
            self.solve_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            if state["error"] is not None:
                if state["cancel"].is_set():
                    self.out.setText(
                        "<b>Solve cancelled.</b> No factor was stored; a "
                        "previously cached factor, if any, is untouched.")
                else:
                    self.out.setText(
                        "<b>The solve did not complete.</b><br>%s"
                        % state["error"])
                return
            res = state["result"]
            self.result_obj = res
            text = ("<b>" + summarise(res).replace("\n", "<br>")
                    + "</b><br><br>" + res.provenance)
            worst = res.worst.factor if mixed else res.factor
            for n in advice_for(len(cables), True, factor=worst,
                                provenance=res.provenance,
                                converged=res.converged,
                                sizes=len(size_counts(cables)),
                                groups=len(group_counts(cables))):
                text += "<br><br>⚠ " + n
            for w in res.warnings:
                text += "<br><br>⚠ " + w
            self.out.setText(text)

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


def _trefoil_work(cables, box_w, box_h):
    """A work measure for the bundle CFD — cells x iterations, as its siblings.

    ⚠ This used to take the DIALOG and probe it for ``count`` / ``n_cables`` /
    ``cables`` / ``iterations`` / ``iters``. ``ConvectionDialog`` sets none of
    them — its cables are a CLOSURE variable of :func:`build_dialog`, never
    ``self.cables`` — so every probe returned None, ``int(None)`` raised, both
    loops fell through, and it handed ``confirm_solve_work`` ``1.0`` for every
    bundle it would ever be given. A 3-cable reference trefoil and a 30-cable
    mixed bundle therefore shared ONE history bucket, and the estimate quoted
    "median of N previous runs of this size" from runs of a completely
    different size — a provenance claim the key could not support
    (2026-08-29 audit). A parameter that changes nothing is worse here than no
    parameter, because the sentence it feeds sounds measured either way.

    So price the case that is actually about to be written: background cells
    plus the refined band snappy grows on each cable, times the iteration
    budget. That is the same currency ``cht_dialog`` and
    ``solid_convection_dialog`` hand ``confirm_solve_work``, and a history key
    only has to be monotonic in cost — see :mod:`emstudio.solvers.estimate`.
    """
    try:
        # ⚠ Read the DEFAULTS off the case class rather than copying the
        # numbers here: the dialog passes no ``case_kw``, so BundleCase's own
        # fields ARE the budget this solve will run under, and a duplicated
        # constant is exactly what drifts the day one of them moves.
        from emstudio.solvers.openfoam import BundleCase

        case = BundleCase()
        nx = int(case.cells_x)
        ny = max(1, int(round(nx * float(box_h) / float(box_w))))
        dx = float(box_w) / nx          # background cell — what snappy halves
        d_max = max(float(c[2]) for c in cables)
        # ⚠ Every cable contributes the SAME surface-cell count, set by the
        # LARGEST diameter and not by its own: ``refine_match_perimeter`` adds
        # ceil(log2(d_max/d)) levels to a smaller cable precisely so all of
        # them resolve to comparable angular resolution (see
        # solvers/openfoam/bundle.py). The bump is an integer, so a small cable
        # can be over-refined by up to 2x — which a log-bucketed key does not
        # care about.
        band = math.pi * d_max * (2.0 ** case.refine_max) / dx
        # ⚠ Charge that band once per refinement LEVEL and once per prism
        # layer, not once in total. snappy castellates hierarchically — every
        # level from 1 to refine_max grows its own band around the surface,
        # several cells deep, and the layers go on top — so charging one band
        # would under-count the refined region several-fold and let the FIXED
        # background mesh swamp the only term that varies with the bundle.
        # Still a deliberate under-count: the exact band depths live in the
        # writer's snappyHexMeshDict literals, and a copy of them here would
        # drift the day one of them moves.
        per_cable = band * (case.refine_max + case.wall_layers)
        return float(case.iterations) * (nx * ny + len(cables) * per_cable)
    except Exception:                                      # noqa: BLE001
        # ⚠ This must never raise. It is evaluated as an ARGUMENT to
        # confirm_solve_work, i.e. OUTSIDE that function's own try/except, so
        # an exception here would take the Solve button down with a traceback
        # instead of merely leaving the estimate unpriced. 0.0 is what
        # estimate.work_of returns when nothing can be read, and it buckets to
        # "no useful history key" rather than to a wrong one.
        return 0.0
