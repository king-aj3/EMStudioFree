# SPDX-License-Identifier: LGPL-2.1-or-later
"""Conjugate Heat Transfer dialog — the slab-against-air-gap stack (§8c).

⚠ THE DOOR CARRIES THE PROBLEM, honestly: this dialog solves a PARAMETRIC
planar stack — an insulating solid layer between a hot face and a vertical
air gap against a cold face — and it says so. It does NOT read document
geometry (the reference-trefoil lesson, 2026-08-17: a solve that quietly
ignores the viewport is worse than none). CHT on a selected assembly is the
ROADMAP §8c extension this rung anchors.

What makes it shippable is the ladder under it:
  * conduction (buoyancy off): the answer is CLOSED FORM and the solve
    reproduces the analytic means to 5 decimals (gated, `openfoam_cht`);
  * natural convection: the gap Nusselt number recovered by
    `cht.gap_nusselt` lands between the in-range vertical-cavity
    correlations — measured live 2026-08-19 on the gate's 40x60 mesh: Nu 6.8529 at
    interface Ra 8.49e5, A = 4. ⚠ That is the GATE MESH's value; the
    3-grid study (docs/results/cht_refinement_fixedmesh.txt) puts the
    mesh-independent number at ~6.5, i.e. the gate mesh reads ~5 % high.
    ~6.5 sits between the two in-range references, Berkovsky-Polevikov
    6.64 and ElSherbiny-class at A=5 6.41 (gated,
    `openfoam_cht_convection`).
Off that anchor the dialog does not go silent — `regime_note` names when
the entered case leaves the validated envelope.

Qt is imported lazily; `describe_case` and `regime_note` are importable
headless so the gate can check the prose against the case it claims to
describe.
"""

from __future__ import annotations

from emstudio.solvers.openfoam.cht import ChtCase, gap_nusselt

#: Dialog default iterations. The anchor gate runs 20000 (~70 min at 40x60);
#: the measured field was static to 8 figures from ~10000 on, so the dialog
#: defaults there and exposes the knob — the honest trade is stated in the
#: result text, not hidden.
DEFAULT_ITERATIONS = 10000

#: The vertical-cavity correlations behind the anchor are laminar fits over
#: roughly A 2-10; transition takes the gap flow past what a steady laminar
#: solve represents well before Ra 1e8, so warn early.
RA_VALIDATED = 8.5e5
RA_WARN = 1.0e7
ASPECT_LO, ASPECT_HI = 2.0, 10.0


def make_case(t_hot, t_cold, l_solid_m, k_solid, l_fluid_m, height_m,
              buoyant, n_fluid=40, n_y=60, iterations=DEFAULT_ITERATIONS):
    """The ChtCase the dialog solves — REAL air, never a derived viscosity.

    ⚠ ``target_ra`` stays 0 on purpose: the gates derive an artificial mu to
    HIT a Rayleigh number; a user's gap must be solved with air as it is,
    and the resulting Ra reported, not chosen.

    ⚠ REFUSES a buoyant case whose written Boussinesq EOS is non-physical:
    the density the case writes is rho0*(1 - beta*(T - t_ref)) with 300 K
    air constants, which reaches ZERO at ~603 K — a solve past that would
    still run and print confident numbers from a negative-density fluid.
    Refusal, not a warning: there is no reading of that case that means
    anything.
    """
    case = ChtCase(t_hot=t_hot, t_cold=t_cold,
                   l_solid=l_solid_m, k_solid=k_solid,
                   l_fluid=l_fluid_m, height=height_m,
                   gravity=9.81 if buoyant else 0.0,
                   n_y=n_y if buoyant else 1,
                   n_fluid=n_fluid,
                   iterations=iterations)
    if case.buoyant and case.beta * (case.t_hot - case.t_ref) >= 0.9:
        raise ValueError(
            "hot face %.0f K is beyond what the Boussinesq air model can "
            "represent (its linearised density reaches zero at ~%.0f K) — "
            "this stack needs a variable-property model this dialog does "
            "not have" % (case.t_hot, case.t_ref + 1.0 / case.beta))
    return case


def describe_case(case):
    """What is about to be solved, in prose, before any time is spent."""
    base = ("Parametric stack — NOT read from the document: hot face "
            "%.1f K | %.1f mm solid (k = %.3g W/m·K) | %.1f mm air gap "
            "| cold face %.1f K; cavity height %.1f mm. Air properties are "
            "constants near 300 K (k = %.4g W/m·K, Pr 0.7). Pure-conduction "
            "reference: q = %.3f W/m², interface at %.2f K."
            % (case.t_hot, 1e3 * case.l_solid, case.k_solid,
               1e3 * case.l_fluid, case.t_cold, 1e3 * case.height,
               case.k_fluid, case.flux, case.t_interface))
    if case.buoyant:
        return (base + " Buoyancy ON: gravity along the cavity, nominal "
                "Ra %.3g at aspect H/L %.1f — the solved interface Ra and "
                "the gap Nusselt number come out of the solve."
                % (case.rayleigh, case.aspect))
    return (base + " Buoyancy OFF: the stack is conduction in series and "
            "the solve should land on the reference numbers above almost "
            "exactly — a live check of the machinery, not a prediction.")


#: Air-property honesty: the case writes 300 K constants; ~0.3 %/K drift in
#: k and mu means a 50 K film departure is ~15 % of property error riding
#: silently under the bold numbers — say it from there on.
FILM_WARN_K = 50.0

#: Instrument floor: gap_nusselt reads the interface off the SOLID's mean,
#: so a solid taking under ~1 % of the total drop leaves the recovery
#: dividing solver noise (the anchor's solid takes 2.6 % and was proven
#: against a second instrument; an order below that is micro-kelvins).
R_SOLID_FLOOR = 0.01


def regime_note(case, ra=None):
    """Where this case stands relative to the validated envelope, or ''.

    ``ra``: the SOLVED interface-referenced Ra when available — the honest
    one; the nominal Ra stands in before a solve exists.
    """
    if not case.buoyant:
        return ""
    r = case.rayleigh if ra is None else ra
    notes = []
    if r > RA_WARN:
        notes.append(
            "Ra %.3g is beyond the laminar steady regime this case models "
            "(validated at Ra ~%.2g; the vertical-cavity correlations are "
            "laminar fits) — treat the number as UNVALIDATED at this "
            "driving" % (r, RA_VALIDATED))
    if not (ASPECT_LO <= case.aspect <= ASPECT_HI):
        notes.append(
            "aspect H/L %.2f is outside the %.0f-%.0f range the "
            "correlations (and the A = 4 anchor) cover — the recovered Nu "
            "has no reference at this shape" % (case.aspect,
                                                ASPECT_LO, ASPECT_HI))
    film = 0.5 * (case.t_hot + case.t_cold)
    if abs(film - case.t_ref) > FILM_WARN_K:
        notes.append(
            "air properties are %.0f K constants and the film temperature "
            "is %.0f K — roughly %.0f %% of property drift (~0.3 %%/K in k "
            "and mu) rides under these numbers"
            % (case.t_ref, film, 0.3 * abs(film - case.t_ref)))
    if case.r_solid < R_SOLID_FLOOR * case.r_fluid:
        notes.append(
            "the solid layer takes only %.2g %% of the total resistance — "
            "the Nu recovery reads the interface from the SOLID's "
            "temperature drop and has almost nothing to measure here, so "
            "Nu/q are amplified solver noise (the anchor's solid takes "
            "2.6 %%); thicken the layer or lower its conductivity to get a "
            "measurable stack"
            % (100.0 * case.r_solid / (case.r_solid + case.r_fluid)))
    return "; ".join(notes)


def build_dialog(doc=None, parent=None):  # pragma: no cover
    """The Qt dialog. Same worker + polling-timer + real-Cancel idiom as the
    solid-convection dialog — proven there the hard way (2026-08-17)."""
    from PySide import QtCore, QtWidgets

    from emstudio.solvers.openfoam import runner

    class ChtDialog(QtWidgets.QDialog):
        def __init__(self):
            super(ChtDialog, self).__init__(parent)
            self.setWindowTitle("Conjugate Heat Transfer — slab + air gap")
            self.case_dir = ""
            lay = QtWidgets.QVBoxLayout(self)

            lay.addWidget(QtWidgets.QLabel("<b>What will be solved</b>"))
            self.plan = QtWidgets.QLabel("")
            self.plan.setWordWrap(True)
            lay.addWidget(self.plan)

            form = QtWidgets.QFormLayout()

            def spin(lo, hi, val, dec, suffix):
                s = QtWidgets.QDoubleSpinBox()
                s.setRange(lo, hi)
                s.setDecimals(dec)
                s.setValue(val)
                s.setSuffix(suffix)
                s.valueChanged.connect(self._replan)
                return s

            self.t_hot = spin(260.0, 1000.0, 350.0, 1, " K")
            form.addRow("Hot face temperature", self.t_hot)
            self.t_cold = spin(250.0, 990.0, 300.0, 1, " K")
            form.addRow("Cold face temperature", self.t_cold)
            self.l_solid = spin(0.1, 500.0, 20.0, 1, " mm")
            form.addRow("Solid thickness", self.l_solid)
            self.k_solid = spin(0.01, 500.0, 0.10, 3, " W/m·K")
            form.addRow("Solid conductivity", self.k_solid)
            self.l_fluid = spin(0.5, 500.0, 5.0, 1, " mm")
            form.addRow("Air-gap width", self.l_fluid)
            self.height = spin(1.0, 5000.0, 20.0, 1, " mm")
            form.addRow("Cavity height", self.height)
            self.buoyant = QtWidgets.QCheckBox(
                "Include buoyancy (natural convection in the gap)")
            self.buoyant.setChecked(True)
            self.buoyant.toggled.connect(self._replan)
            form.addRow("", self.buoyant)
            self.iters = QtWidgets.QSpinBox()
            self.iters.setRange(500, 50000)
            self.iters.setValue(DEFAULT_ITERATIONS)
            form.addRow("Iterations (max)", self.iters)
            lay.addLayout(form)

            warn = QtWidgets.QLabel(
                "<b>The buoyant solve is a 2-region CFD run and can take "
                "tens of minutes</b> (the 40×60 anchor ran ~70 min at "
                "20000 iterations; the field was steady from ~10000). "
                "Conduction-only runs finish in minutes.")
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
            self.solve_btn = box.addButton(
                "Solve…", QtWidgets.QDialogButtonBox.ActionRole)
            self.cancel_btn = box.addButton(
                "Cancel solve", QtWidgets.QDialogButtonBox.ActionRole)
            self.cancel_btn.setEnabled(False)
            self.show_btn = box.addButton(
                "Show gap field in 3-D view",
                QtWidgets.QDialogButtonBox.ActionRole)
            self.show_btn.setEnabled(False)
            box.addButton(QtWidgets.QDialogButtonBox.Close)
            box.rejected.connect(self.reject)
            self.solve_btn.clicked.connect(self._solve)
            self.cancel_btn.clicked.connect(self._cancel_solve)
            self.show_btn.clicked.connect(self._show_field)
            lay.addWidget(box)

            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self._poll)
            self._run = None
            self._replan()

        def _case(self):
            return make_case(
                t_hot=float(self.t_hot.value()),
                t_cold=float(self.t_cold.value()),
                l_solid_m=1e-3 * float(self.l_solid.value()),
                k_solid=float(self.k_solid.value()),
                l_fluid_m=1e-3 * float(self.l_fluid.value()),
                height_m=1e-3 * float(self.height.value()),
                buoyant=self.buoyant.isChecked(),
                iterations=int(self.iters.value()))

        def _replan(self, *_args):
            try:
                case = self._case()
            except ValueError as exc:
                self.plan.setText("⚠ %s" % exc)
                self.solve_btn.setEnabled(False)
                return
            self.solve_btn.setEnabled(self._run is None
                                      or self._run.get("done", True))
            text = describe_case(case)
            note = regime_note(case)
            if note:
                text += "\n\n⚠ " + note
            self.plan.setText(text)

        def _solve(self):
            import tempfile
            import threading

            try:
                case = self._case()
            except ValueError as exc:
                # APPEND — a completed run's numbers may be on display, and
                # they cost tens of minutes; a typo must not erase them.
                prior = self.out.text()
                self.out.setText((prior + "<br><br>" if prior else "")
                                 + "⚠ %s" % exc)
                return
            case_dir = tempfile.mkdtemp(prefix="emstudio-cht-")
            state = {"done": False, "report": None, "error": None,
                     "case_dir": case_dir, "case": case,
                     "cancel": threading.Event()}
            self._run = state

            def work():
                # Only the captured state dict is written off the GUI thread.
                try:
                    report, means = runner.run_cht(
                        case_dir, case, timeout=4 * 3600,
                        cancel=state["cancel"])
                    state["report"] = report
                    if means is None:
                        raise ValueError(
                            "the solve did not complete (%s): %s"
                            % (report.get("failed_at"), report.get("error")))
                except Exception as exc:        # a failed solve is REPORTED
                    state["error"] = exc
                finally:
                    state["done"] = True

            self.solve_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.show_btn.setEnabled(False)
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
            # Closing mid-solve cancels — never a chain grinding on behind a
            # closed window.
            if self._run is not None and not self._run["done"]:
                self._run["cancel"].set()
            super(ChtDialog, self).reject()

        def _poll(self):
            state = self._run
            if state is None or not state["done"]:
                return
            self._timer.stop()
            self.bar.hide()
            self.solve_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self._run = None
            # Inputs may have been edited mid-run; Solve's enabled state must
            # come from the CURRENT inputs, not from "a run just finished".
            self._replan()
            if state["error"] is not None:
                if state["cancel"].is_set():
                    self.out.setText("<b>Solve cancelled.</b>")
                else:
                    self.out.setText(
                        "<b>The solve did not complete.</b><br>%s"
                        % state["error"])
                return
            report = state["report"]
            case = state["case"]
            self.case_dir = state["case_dir"]
            self.show_btn.setEnabled(True)
            if case.buoyant:
                try:
                    m = gap_nusselt(case, report["t_solid_mean"])
                except ValueError as exc:
                    # The engine's honesty message for a run that exited 0
                    # on a non-physical field — it must REACH the user, not
                    # vanish into the Qt event loop. Show-field stays live:
                    # LOOKING at the garbage field is the diagnostic.
                    self.out.setText(
                        "<b>The solve finished but its result does not "
                        "describe a converged state.</b><br>%s<br><br>"
                        "Show the gap field to see what the solver actually "
                        "produced." % exc)
                    return
                text = ("<b>Gap Nusselt number Nu = %.3f at interface "
                        "Ra = %.3g.<br>Through-flux q = %.3f W/m² — "
                        "%.2f× the pure-conduction %.3f W/m². Interface at "
                        "%.2f K (conduction would put it at %.2f K).</b>"
                        % (m.nu, m.ra, m.q, m.q / case.flux, case.flux,
                           m.t_interface, case.t_interface))
                note = regime_note(case, ra=m.ra)
                if note:
                    text += "<br><br>⚠ " + note
                text += ("<br><br>Ran ≤%d iterations (the anchor ran 20000; "
                         "raise the knob for a slow-converging case)."
                         % case.iterations)
            else:
                text = ("<b>Conduction check: solved solid mean %.5f K "
                        "(exact %.5f), fluid mean %.5f K (exact %.5f).</b>"
                        "<br>q = %.3f W/m², interface at %.2f K — closed "
                        "form; disagreement here would be a machinery "
                        "fault, and the battery gates it."
                        % (report["t_solid_mean"], case.t_solid_mean,
                           report["t_fluid_mean"], case.t_fluid_mean,
                           case.flux, case.t_interface))
            self.out.setText(text)

        def _show_field(self):
            # The gap region carries the answer (the slab is a linear ramp);
            # foamToVTK needs -region on a split case — MEASURED layout, see
            # vtk_export.vtk_dir.
            try:
                import os

                from emstudio.post import vtk_out
                from emstudio.solvers.openfoam import vtk_export

                vtu = vtk_export.convert(self.case_dir, region="gap")
                patches = vtk_export.boundary_vtps(self.case_dir,
                                                   region="gap")
                vtk_out.show_foam_case(
                    vtu, patches, doc,
                    label_prefix="CHT {0}".format(
                        os.path.basename(self.case_dir.rstrip("\\/"))))
            except Exception as exc:            # noqa: BLE001 — surfaced
                self.out.setText(self.out.text()
                                 + "<br><br>⚠ could not show the field: "
                                 + "%s" % exc)

    return ChtDialog()
