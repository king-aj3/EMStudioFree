# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wind Loading dialog — cross-flow drag on a mast/member section (§8b).

The engine (`solvers/openfoam/wind.py`) carried three validated rungs with no
door for a year of releases — CAPABILITIES said "ENGINE ONLY, no UI caller"
out loud, and the run_wind-dialog decision was AJ's to make (recorded in
NEXT_SESSION since v1.6.0). He made it 2026-08-24, the day after the
forced-convection anchor went green: this is that door, built AFTER its
anchor per the triage's own B6 ordering ("do not build the dialog first").

The dialog chooses the SOLVE METHOD the same way the thermal dialogs choose
their turbulence model (the T4 pattern): from the physics, automatically,
with the choice NAMED — never a knob whose wrong setting produces a
confident wrong number. The regime thresholds are read from the engine's own
constants, so this module cannot drift from `method_is_valid`:

* Re below :data:`~emstudio.solvers.openfoam.wind.SHEDDING_RE` — steady
  `simpleFoam` (validated Re 20-40, exact zero-lift symmetry check);
* up to :data:`~emstudio.solvers.openfoam.wind.TURBULENT_RE` — transient
  laminar `pimpleFoam` (validated at Re 100/150 vs Williamson + published
  Cd);
* above that, SQUARE sections only — transient kOmegaSST URANS on the
  benchmark domain (Lyn/Tian square cylinder, gate `openfoam_wind_ras`),
  valid to :data:`~emstudio.solvers.openfoam.wind.RAS_SQUARE_RE_MAX`;
* everything else REFUSES with the engine's own validity note. A circular
  mast above the shedding regime is the big one: its drag crisis is
  transition-location physics no single-Re anchor covers, and this dialog
  refuses to run rather than disclaim afterwards.

Qt is imported lazily; `choose_case` and `describe_wind` are importable
headless so gui_smoke can check the choice and the prose against the
engine without a display or a solve.
"""

from __future__ import annotations

from dataclasses import replace

from emstudio.solvers.openfoam.wind import (
    RAS_SQUARE_RADIUS_RATIO,
    RAS_SQUARE_RE_MAX,
    SHEDDING_RE,
    TURBULENT_RE,
    WindCase,
)

#: Air kinematic viscosity used to turn the typed wind speed into Re. The
#: same 1.5e-5 the engine's dataclass defaults carry — stated once here so
#: the dialog's Re readout and the case it builds cannot disagree.
NU_AIR = 1.5e-5

#: The RAS square rung runs the VALIDATED gate configuration exactly —
#: mesh, stepping and domain are part of what `openfoam_wind_ras` proved,
#: and the domain is additionally enforced by `method_is_valid` (a 2.5 %
#: blockage domain completes cleanly and still reads Cd below the published
#: band, which is why "close enough" domains are refused, not warned).
RAS_N_R = 160
RAS_GRADING = 4.0
RAS_DT_STAR = 0.004
RAS_ST_GUESS = 0.13
RAS_CYCLES = 20.0


def reynolds_of(u_ms, d_m):
    """Re = U d / nu — the number every regime decision hangs on."""
    return float(u_ms) * float(d_m) / NU_AIR


def choose_case(geometry, d_m, u_ms):
    """Build the WindCase the physics calls for, or raise with the refusal.

    Returns ``(case, method_label)``. Raises ``ValueError`` carrying the
    ENGINE's own validity note when no validated method covers the request —
    the dialog shows that text verbatim, so the refusal a user reads is the
    same one the API produces.
    """
    if geometry not in ("circle", "square"):
        raise ValueError("geometry is 'circle' or 'square', not %r"
                         % (geometry,))
    if d_m <= 0 or u_ms <= 0:
        raise ValueError("section size and wind speed must be positive")
    re = reynolds_of(u_ms, d_m)

    if re < SHEDDING_RE:
        case = WindCase(reynolds=re, d_ref=d_m, geometry=geometry)
        label = "steady simpleFoam (below shedding onset)"
    elif re < TURBULENT_RE:
        case = WindCase(reynolds=re, d_ref=d_m, geometry=geometry,
                        transient=True)
        label = "transient laminar pimpleFoam (laminar shedding regime)"
    else:
        # The turbulent rung: kOmegaSST on the square anchor's own
        # configuration. Built for BOTH geometries so a circle lands in the
        # engine's refusal branch below and we surface ITS note — the
        # dialog never writes its own physics prose for a refusal.
        case = WindCase(reynolds=re, d_ref=d_m, geometry=geometry,
                        transient=True, turbulence="kOmegaSST",
                        st_guess=RAS_ST_GUESS, fixed_dt_star=RAS_DT_STAR,
                        grading=RAS_GRADING, n_r=RAS_N_R,
                        radius_ratio=RAS_SQUARE_RADIUS_RATIO,
                        cycles=RAS_CYCLES)
        label = ("transient kOmegaSST URANS (square-section anchor "
                 "configuration)")

    if not case.method_is_valid:
        note = case.validity_note() or (
            "no validated method covers Re %.3g on a %s section" %
            (re, geometry))
        raise ValueError(note)
    return case, label


def describe_wind(case, method_label, length_m):
    """What is about to be solved, in prose, before any time is spent."""
    q = case.q_ref
    return ("%s section, %.0f mm across, %.2f m/s wind → Re %.3g. Method: "
            "%s. Dynamic pressure q = %.1f Pa; drag is reported as Cd, as "
            "force per metre of length, and as the total over your %.2f m. "
            "2-D cross-flow — end effects and gusting are NOT modelled; "
            "the answer is the section's steady-wind load."
            % (case.geometry, 1000.0 * case.d_ref, case.u_inf,
               case.reynolds, method_label, q, length_m))


def solve_estimate(case):
    """(work_units, honest_runtime_hint) for the pre-solve confirmation.

    Work = steps x cells for a transient case, iterations x cells for the
    steady one — the same currency `confirm_solve_work` prices. The hint is
    stated in words because the three rungs differ by two orders of
    magnitude and a user deciding whether to click deserves the magnitude
    up front, not after.
    """
    cells = 4 * case.n_theta * case.n_r
    if not case.transient:
        return float(case.iterations) * cells, "typically about a minute"
    steps = case.end_time / case.delta_t
    if case.turbulence:
        # The validated RAS configuration, measured on the reference box:
        # ~50 min on 4 MPI ranks, ~3 h serial (the gate's own runtime).
        return steps * cells, ("HOURS — this is the validated turbulent "
                               "benchmark configuration (~3 h serial on the "
                               "reference box)")
    return steps * cells, "typically ~10 minutes"


def result_text(case, method_label, report, forces, hist, length_m):
    """The result pane, assembled headless so gui_smoke can read it.

    Every number here comes off the report/parser objects the gates
    already pin; this function only formats. The validity note — even an
    unexpected one — is surfaced verbatim, always (the §8a rule: the model
    that ran is named, and a caveat is never swallowed).
    """
    q = case.q_ref
    parts = []
    if case.transient:
        cd = report.get("cd")
        drag_n_per_m = cd * q * case.d_ref
        parts.append(
            "<b>Mean Cd %.4f → drag %.3f N per metre — %.2f N over "
            "%.2f m at %.2f m/s.</b>" % (cd, drag_n_per_m,
                                         drag_n_per_m * length_m,
                                         length_m, case.u_inf))
        parts.append(
            "Strouhal %.4f (shedding at %.2f Hz), lift amplitude %.3f — "
            "%.0f whole cycles measured after discarding startup."
            % (report.get("strouhal", 0.0),
               report.get("strouhal", 0.0) * case.u_inf / case.d_ref,
               report.get("cl_amplitude", 0.0),
               report.get("cycles_measured", 0)))
        if report.get("cycles_measured", 0) < 8:
            parts.append("⚠ fewer than 8 whole cycles were measured — "
                         "treat Cd and St as provisional.")
    else:
        cd = forces.cd
        drag_n_per_m = cd * q * case.d_ref
        parts.append(
            "<b>Cd %.4f → drag %.3f N per metre — %.2f N over %.2f m at "
            "%.2f m/s.</b>" % (cd, drag_n_per_m, drag_n_per_m * length_m,
                               length_m, case.u_inf))
    parts.append("Solved with %s." % method_label)
    if case.turbulence:
        parts.append(
            "The kOmegaSST square-section rung is validated against the "
            "Lyn (1995) experiment / Tian (2013) URANS study at Re 21,400 "
            "on this exact configuration (gate openfoam_wind_ras), and "
            "carries the square's flat measured Cd plateau to Re 1.5e5.")
    note = report.get("validity")
    if note:
        parts.append("⚠ " + note)
    if not report.get("converged", True) and not case.transient:
        parts.append("⚠ the steady solve did not meet residualControl — "
                     "treat the last digit with suspicion.")
    return "<br><br>".join(parts)


def build_dialog(parent=None):  # pragma: no cover — exercised by gui_smoke
    """The Qt dialog. Worker + polling-timer + real-Cancel idiom, same as
    the solid-convection dialog (proven the hard way, 2026-08-17)."""
    from PySide import QtCore, QtWidgets

    from emstudio.solvers.openfoam import runner

    class WindLoadingDialog(QtWidgets.QDialog):
        def __init__(self):
            super(WindLoadingDialog, self).__init__(parent)
            self.setWindowTitle("Wind Loading — cross-flow drag (§8b)")
            lay = QtWidgets.QVBoxLayout(self)

            form = QtWidgets.QFormLayout()
            self.section_combo = QtWidgets.QComboBox()
            self.section_combo.addItems(["square", "circle"])
            form.addRow("Section", self.section_combo)
            self.width_spin = QtWidgets.QDoubleSpinBox()
            self.width_spin.setRange(1.0, 5000.0)
            self.width_spin.setDecimals(1)
            self.width_spin.setValue(20.0)
            self.width_spin.setSuffix(" mm")
            form.addRow("Section width d", self.width_spin)
            self.speed = QtWidgets.QDoubleSpinBox()
            self.speed.setRange(0.1, 80.0)
            self.speed.setDecimals(2)
            self.speed.setValue(16.0)
            self.speed.setSuffix(" m/s")
            form.addRow("Wind speed", self.speed)
            self.length = QtWidgets.QDoubleSpinBox()
            self.length.setRange(0.01, 1000.0)
            self.length.setDecimals(2)
            self.length.setValue(1.0)
            self.length.setSuffix(" m")
            form.addRow("Member length (for total force)", self.length)
            lay.addLayout(form)

            self.plan = QtWidgets.QLabel("")
            self.plan.setWordWrap(True)
            lay.addWidget(self.plan)

            self.bar = QtWidgets.QProgressBar()
            self.bar.setRange(0, 0)
            self.bar.hide()
            lay.addWidget(self.bar)
            self.out = QtWidgets.QLabel("")
            self.out.setWordWrap(True)
            lay.addWidget(self.out)

            box = QtWidgets.QDialogButtonBox()
            self.solve_btn = box.addButton(
                "Solve wind loading…", QtWidgets.QDialogButtonBox.ActionRole)
            self.cancel_btn = box.addButton(
                "Cancel solve", QtWidgets.QDialogButtonBox.ActionRole)
            self.cancel_btn.setEnabled(False)
            box.addButton(QtWidgets.QDialogButtonBox.Close)
            box.rejected.connect(self.reject)
            self.solve_btn.clicked.connect(self._solve)
            self.cancel_btn.clicked.connect(self._cancel_solve)
            lay.addWidget(box)

            for w in (self.section_combo, self.width_spin, self.speed, self.length):
                sig = getattr(w, "currentIndexChanged", None) or w.valueChanged
                sig.connect(self._replan)
            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self._poll)
            self._run = None
            self._replan()

        # The plan re-derives on every edit, so a refused configuration is
        # visible BEFORE the button is pressed and the Solve button is
        # disabled with the engine's own note on display — a refusal the
        # user cannot reach is a refusal that never confuses anyone.
        def _replan(self):
            try:
                case, label = choose_case(
                    self.section_combo.currentText(),
                    float(self.width_spin.value()) * 1e-3,
                    float(self.speed.value()))
            except ValueError as exc:
                self.plan.setText("<b>Cannot solve this configuration:"
                                  "</b><br>%s" % exc)
                self.solve_btn.setEnabled(False)
                return
            _work, hint = solve_estimate(case)
            self.plan.setText(
                describe_wind(case, label, float(self.length.value()))
                + "<br><b>Runtime: %s.</b>" % hint)
            self.solve_btn.setEnabled(self._run is None
                                      or self._run.get("done", True))

        def _solve(self):
            import tempfile
            import threading

            try:
                case, label = choose_case(
                    self.section_combo.currentText(),
                    float(self.width_spin.value()) * 1e-3,
                    float(self.speed.value()))
            except ValueError as exc:
                self.out.setText("<b>Refused:</b> %s" % exc)
                return
            work, _hint = solve_estimate(case)
            from emstudio.ui import run_gui
            if not run_gui.confirm_solve_work(
                    self, "openfoam", work,
                    label="Wind loading on a %s section (OpenFOAM)"
                          % case.geometry):
                return

            case_dir = tempfile.mkdtemp(prefix="emstudio-wind-")
            state = {"done": False, "report": None, "forces": None,
                     "hist": None, "error": None, "case": case,
                     "label": label, "length": float(self.length.value()),
                     "cancel": threading.Event()}
            self._run = state

            def work_fn():
                # Only the captured state dict is written off the GUI thread.
                try:
                    report, res = runner.run_wind(
                        case_dir, case, cancel=state["cancel"])
                    state["report"] = report
                    if not report.get("ok"):
                        raise ValueError(
                            "the solve did not complete (%s): %s"
                            % (report.get("failed_at"), report.get("error")))
                    if case.transient:
                        state["hist"] = res
                    else:
                        state["forces"] = res
                except Exception as exc:      # a failed solve is REPORTED
                    state["error"] = exc
                finally:
                    state["done"] = True

            self.solve_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.bar.show()
            self.out.setText("")
            threading.Thread(target=work_fn, daemon=True).start()
            self._timer.start(200)

        def _cancel_solve(self):
            if self._run is not None:
                self._run["cancel"].set()
            self.cancel_btn.setEnabled(False)
            self.out.setText("Cancelling — stopping the OpenFOAM chain…")

        def reject(self):
            # Closing mid-solve cancels — never a chain grinding on behind
            # a closed window (the 08-17 lesson).
            if self._run is not None and not self._run["done"]:
                self._run["cancel"].set()
            super(WindLoadingDialog, self).reject()

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
                    self.out.setText("<b>Solve cancelled.</b>")
                else:
                    self.out.setText(
                        "<b>The solve did not complete.</b><br>%s"
                        % state["error"])
                return
            self.out.setText(result_text(
                state["case"], state["label"], state["report"],
                state["forces"], state["hist"], state["length"]))

    return WindLoadingDialog()
