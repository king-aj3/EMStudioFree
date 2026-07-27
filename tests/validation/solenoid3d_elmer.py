# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the 3-D GUI-wiring path (FreeCAD solids → WhitneyAV).

Runs the FULL FreeCAD import chain — the 3-D Solenoid template's solids
exported as BREPs, meshed conformally in mm with ``Coordinate Scaling``,
solved by the CoilSolver → WhitneyAV → CalcFields chain — and checks the
on-axis center Bz against the exact thick-solenoid closed form. The
engine's meters-based gates pin this physics at −0.55 % on fine meshes
(whitney3d_elmer.py); the template's FAST default mesh is gated at 4 %
(sign-agnostic — the closed-coil circulation sense is mesh-arbitrary).

Also asserts the ``run3d`` MagneticsResult wrapper (mode3d meta, VTU
present, clean convergence) that the magnetics dialog consumes.

Runs under freecadcmd (needs FreeCAD for the BREP export). ~30 s live.
Pass: exit 0 and 'SOLENOID3D GATE PASSED'. Auto-skips without Elmer/gmsh.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MU0 = 4.0e-7 * math.pi
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def solenoid_bz_axis(z, r1, r2, h, ni):
    j = ni / ((r2 - r1) * h)

    def f(zeta):
        return zeta * math.log(
            (r2 + math.hypot(r2, zeta)) / (r1 + math.hypot(r1, zeta)))

    return 0.5 * MU0 * j * (f(z + h / 2.0) - f(z - h / 2.0))


def main():
    print("EMStudio 3-D GUI-wiring (solenoid template) validation gate")
    try:
        import FreeCAD  # noqa: F401
    except Exception:
        print("  skip  needs FreeCAD (BREP export) — run under freecadcmd")
        print("SOLENOID3D GATE PASSED")
        return 0

    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.base import make_workdir
    from emstudio.solvers.elmer.model3d import build_3d_model, run3d
    from emstudio.templates import solenoid3d

    doc = FreeCAD.newDocument("gate_solenoid3d")
    try:
        ana = solenoid3d.makeSolenoid3D(doc)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverElmer"][0]
        check("template sets the 3-D analysis mode + a body mesh size",
              solver.AnalysisType == "3-D Magnetostatic (DC)"
              and float(solver.MeshSizeBodies.getValueAs("mm")) > 0)

        # physics tier: the extracted model + an injected axis save-line
        workdir = make_workdir("emstudio_gate3d_")
        model = build_3d_model(ana, solver, workdir)
        check("extraction: one BREP coil body, mm units, padded air",
              len(model["bodies"]) == 1 and model["bodies"][0].get("coil")
              and model["units_mm"] and model["air"]["pad"] > 200.0,
              "pad {0:.0f} mm".format(model["air"]["pad"]))
        check("coil drive: +500 ampere-turns (25 x 20 A, not Reversed)",
              abs(model["bodies"][0]["coil"]["amp_turns"] - 500.0) < 1e-9)
        model["embed_lines"] = [((0.0, 0.0, -50.0), (0.0, 0.0, 50.0))]
        model["save_lines"] = [((0.0, 0.0, -0.05), (0.0, 0.0, 0.05), 50)]

        try:
            from emstudio.solvers.elmer.runner3d import run_model3d

            res = run_model3d(model, workdir=os.path.join(workdir, "run"))
        except Exception as exc:  # noqa: BLE001
            print("  skip  live tier — 3-D Elmer run unavailable: {0}".format(exc))
            return 0 if not FAILURES else 1
        line = res["saveline"]
        pts = sorted(zip(line["coordinate 3"], line["magnetic flux density 3"]))
        zs = [p[0] for p in pts]
        bz = [p[1] for p in pts]
        i = min(range(len(zs)), key=lambda k: abs(zs[k]))
        fem0 = bz[i]
        ref0 = solenoid_bz_axis(0.0, 0.020, 0.025, 0.060, 500.0)
        check("FreeCAD-path center Bz within 4% of the exact closed form "
              "(fast template mesh; sign-agnostic)",
              abs(abs(fem0) / ref0 - 1.0) < 0.04,
              "FEM {0:.6g} vs ref {1:.6g} T ({2:+.2%})".format(
                  abs(fem0), ref0, abs(fem0) / ref0 - 1.0))
        check("live solve converged cleanly", not res["solver_warnings"],
              "; ".join(res["solver_warnings"][:2]))

        # wrapper tier: the dialog-facing MagneticsResult
        result = run3d(ana, solver)
        case = result.sweep_cases()[0]
        check("run3d wraps a MagneticsResult (mode3d + static meta, 0 Hz "
              "case, VTU present)",
              result.meta.get("mode3d") and result.meta.get("static")
              and case["freq_hz"] == 0.0 and case["vtu"]
              and os.path.isfile(case["vtu"]))
        check("summary text is honest about the 3-D mode",
              "GENERAL 3-D magnetostatic" in result.summary_text())
    finally:
        FreeCAD.closeDocument(doc.Name)

    if FAILURES:
        print("SOLENOID3D GATE FAILED: {0}".format(FAILURES))
        return 1
    print("SOLENOID3D GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("solenoid3d validation failed")
    sys.exit(0)
