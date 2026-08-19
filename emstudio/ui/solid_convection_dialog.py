# SPDX-License-Identifier: LGPL-2.1-or-later
"""Solid Convection dialog — CFD on the solid the user SELECTED (§8a).

The door carries the problem (AJ, 2026-08-17): this dialog receives the
tessellated geometry of the user's own selection and solves ITS natural
convection in open air. There is no built-in geometry anywhere on this
path — `write_solid` refuses to invent one.

Open air means a far-wall box at ambient (see `solvers/openfoam/solid.py`
for the honest scope and the conduction sandwich that anchors it). When
the document contains no enclosure, open air is the right assumption; a
designated enclosure solid is a planned extension, not silently ignored
geometry — the dialog says so.

Qt is imported lazily; `describe_solid` is importable headless so the gate
can check the prose against the geometry it claims to describe.
"""

from __future__ import annotations

from emstudio.solvers.openfoam.solid import SolidCase

#: FreeCAD tessellation tolerance, DOCUMENT millimetres. 0.5 mm keeps a
#: 100 mm coil smooth without exploding the STL; the dialog reports the
#: triangle count so a pathological tessellation is visible, not silent.
TESS_TOL_MM = 0.5

#: Default fidelity — matched to the recorded full-fidelity PROBE
#: (cells_bg 32, 2026-08-17); the SOLVER gate runs its own smaller/longer
#: configurations and self-pins those separately.
DEFAULT_ITERATIONS = 6000
DEFAULT_WRITE_INTERVAL = 2000


def describe_solid(triangles, label=""):
    """What is about to be solved, in prose, before any time is spent."""
    case = SolidCase(triangles=triangles)      # geometry probe only
    lo, hi = case.bbox
    ext = tuple(1000.0 * (b - a) for a, b in zip(lo, hi))
    return ("%s: %d surface triangles, wetted area %.1f cm%s, extent "
            "%.0f x %.0f x %.0f mm. Open-air box %.0f mm across — walls at "
            "ambient stand in for the far field; no enclosure geometry is "
            "read (yet). Gravity is -z, the document's down. Laminar, "
            "convection only — NO radiation (a high-emissivity surface "
            "sheds a comparable power by radiation, so the solved rise is "
            "an over-estimate) — constant-property air at a film "
            "temperature." % (label or "Selected solid", len(triangles),
                              1.0e4 * case.area_m2, "²",
                              ext[0], ext[1], ext[2], 2000.0 * case.box_half))


def film_note(t_mean, t_amb, t_film_k=315.0):
    """A property-honesty note when the solved film temperature strays.

    The air table is evaluated at a FIXED film temperature before the solve
    (the surface temperature is the answer, so it cannot inform the input).
    When the solved film lands far from that guess the properties carry an
    error worth saying out loud rather than hiding in a constant.
    """
    film = 0.5 * (t_mean + t_amb)
    if abs(film - t_film_k) <= 25.0:
        return ""
    return ("air properties were evaluated at a %.0f K film; the solved "
            "film is %.0f K, so h carries roughly %.0f %% of property "
            "drift (~0.3 %%/K). The API takes t_film_k for a re-run at "
            "the solved film" % (t_film_k, film,
                                 0.3 * abs(film - t_film_k)))


def build_dialog(triangles, label, doc=None, parent=None):  # pragma: no cover
    """The Qt dialog. Same worker + polling-timer + real-Cancel idiom as the
    bundle convection dialog — proven there the hard way (2026-08-17)."""
    from PySide import QtCore, QtWidgets

    from emstudio.solvers.openfoam import runner

    class SolidConvectionDialog(QtWidgets.QDialog):
        def __init__(self):
            super(SolidConvectionDialog, self).__init__(parent)
            self.setWindowTitle("Solid Convection — %s" % label)
            self.result_obj = None
            self.case_dir = ""
            lay = QtWidgets.QVBoxLayout(self)

            lay.addWidget(QtWidgets.QLabel("<b>What will be solved</b>"))
            plan = QtWidgets.QLabel(describe_solid(triangles, label))
            plan.setWordWrap(True)
            lay.addWidget(plan)

            form = QtWidgets.QFormLayout()
            self.power = QtWidgets.QDoubleSpinBox()
            self.power.setRange(0.001, 100000.0)
            self.power.setDecimals(3)
            self.power.setValue(1.0)
            self.power.setSuffix(" W")
            form.addRow("Dissipated power", self.power)
            self.ambient = QtWidgets.QDoubleSpinBox()
            self.ambient.setRange(250.0, 400.0)
            self.ambient.setDecimals(1)
            self.ambient.setValue(300.0)
            self.ambient.setSuffix(" K")
            form.addRow("Ambient temperature", self.ambient)
            lay.addLayout(form)

            warn = QtWidgets.QLabel(
                "<b>This runs a 3-D CFD solve and takes minutes.</b> The "
                "result is the surface temperature rise and mean film "
                "coefficient of YOUR solid, plus the solved field for the "
                "3-D view.")
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
                "Solve convection…", QtWidgets.QDialogButtonBox.ActionRole)
            self.cancel_btn = box.addButton(
                "Cancel solve", QtWidgets.QDialogButtonBox.ActionRole)
            self.cancel_btn.setEnabled(False)
            self.show_btn = box.addButton(
                "Show field in 3-D view", QtWidgets.QDialogButtonBox.ActionRole)
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

        def _solve(self):
            import tempfile
            import threading

            # ⚠ The film guess follows the chosen ambient (ambient + 15 K) —
            # a fixed 315 K film against a 250 K ambient would start 50 K
            # off before the solve even ran. `film_note` reports the drift
            # that remains after the solve.
            case = SolidCase(triangles=triangles,
                             power_w=float(self.power.value()),
                             t_amb=float(self.ambient.value()),
                             t_film_k=float(self.ambient.value()) + 15.0,
                             iterations=DEFAULT_ITERATIONS,
                             write_interval=DEFAULT_WRITE_INTERVAL)
            case_dir = tempfile.mkdtemp(prefix="emstudio-solidconv-")
            state = {"done": False, "result": None, "error": None,
                     "report": None, "case_dir": case_dir, "case": case,
                     "cancel": threading.Event()}
            self._run = state

            def work():
                # Only the captured state dict is written off the GUI thread.
                try:
                    report, res = runner.run_solid(
                        case_dir, case, cancel=state["cancel"])
                    state["report"] = report
                    if res is None:
                        raise ValueError(
                            "the solve did not complete (%s): %s"
                            % (report.get("failed_at"), report.get("error")))
                    state["result"] = res
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
            super(SolidConvectionDialog, self).reject()

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
            res = state["result"]
            self.result_obj = res
            self.case_dir = state["case_dir"]
            self.show_btn.setEnabled(True)
            case = state["case"]
            text = ("<b>Surface temperature: %.2f K mean (%.2f K max) — "
                    "%.2f K above the %.1f K ambient.<br>"
                    "Mean film coefficient h = %.3f W/m%sK at "
                    "%.3f W dissipated over %.1f cm%s.</b><br><br>%s"
                    % (res.t_mean, res.t_max, res.dt, res.t_amb,
                       res.h_w_m2k, "²", case.power_w,
                       1.0e4 * case.area_m2, "²", res.provenance))
            if not res.converged:
                drift = ("%.2g" % res.drift) if res.drift == res.drift else "?"
                text += ("<br><br>⚠ residualControl did not fire; "
                         "surface-dT drift between the last two snapshots: "
                         "%s. Treat the last digit with suspicion." % drift)
            note = film_note(res.t_mean, res.t_amb, case.t_film_k)
            if note:
                text += "<br><br>⚠ " + note
            # ⚠ The laminar steady model has a ceiling, and nothing else
            # would say so: above Ra ~1e8 the plume is transitional and a
            # converged answer is not thereby a right one (§8b honesty).
            ra_d = res.ra_for(2.0 * case.bounding_radius)
            if ra_d > 1.0e8:
                text += ("<br><br>⚠ Ra over the solid's size is %.2g — "
                         "beyond the laminar steady regime this case "
                         "models. Treat the result as UNVALIDATED at this "
                         "scale (a turbulence rung is ROADMAP §8b)." % ra_d)
            for w in res.warnings:
                text += "<br><br>⚠ " + w
            self.out.setText(text)

        def _show_field(self):
            # The same chain "Show Convection Field in 3-D View" uses — the
            # field this dialog just solved, on the user's own document.
            try:
                import os

                from emstudio.post import vtk_out
                from emstudio.solvers.openfoam import vtk_export

                vtu = vtk_export.convert(self.case_dir)
                patches = vtk_export.boundary_vtps(self.case_dir)
                vtk_out.show_foam_case(
                    vtu, patches, doc,
                    label_prefix="SolidConvection {0}".format(
                        os.path.basename(self.case_dir.rstrip("\\/"))))
            except Exception as exc:            # noqa: BLE001 — surfaced
                self.out.setText(self.out.text()
                                 + "<br><br>⚠ could not show the field: "
                                 + "%s" % exc)

    return SolidConvectionDialog()
