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

Runs under freecadcmd (needs FreeCAD for the BREP export). ~15 s live.
Pass: exit 0 and 'SOLENOID3D GATE PASSED'.

WHAT MAY BE A SKIP, AND WHAT MAY NOT
------------------------------------
Only an ABSENT backend (or an absent FreeCAD) may be reported as "not run",
the backends are PROBED UP FRONT to establish that, and a skip never prints
the PASS token: it prints 'SOLENOID3D GATE SKIPPED' and exits 2. Everything
else — a broken deck, a renamed SaveLine column, a solver that errors out, a
physics regression — is a FAILURE.

This used to be a bare ``except Exception`` wrapped round the one and only
solve call, relabelling every one of those "3-D Elmer run unavailable" and
returning 0 with all four live checks never run. The exception TYPE cannot
tell the two cases apart: ``SolverError`` is a ``RuntimeError`` and
``_resolve_elmersolver`` raises it for a MISSING ElmerSolver, exactly as
``run_model3d`` raises it for a solve that failed. So the question is asked
directly instead — the same shape whitney3d_elmer.py uses.
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


#: The backends the live tier drives. ``run_model3d`` meshes with gmsh, then
#: converts and solves with the Elmer suite — the absence of either is the
#: ONLY condition that may be reported as "not run" rather than as a failure.
_LIVE_BACKENDS = ("elmer", "gmsh")


def missing_backends():
    """Backend keys the live tier needs and this box does not have."""
    from emstudio.setup import solvers as solver_setup
    return [k for k in _LIVE_BACKENDS
            if not solver_setup.find_backend(k).found]


def main():
    print("EMStudio 3-D GUI-wiring (solenoid template) validation gate")
    try:
        import FreeCAD  # noqa: F401
    except ImportError:
        # NOT the PASS token, and NOT exit 0 — this branch verified nothing.
        # run_battery.py lists this gate in NEEDS_FREECAD and skips it
        # honestly when freecadcmd is absent, so the battery never reaches
        # here; the exposure is a HAND run, which is precisely where a
        # vacuous "GATE PASSED" gets believed (Gate-B audit 2026-08-23,
        # docs/upstream/gate-b-audit-2026-08-23.md names these very lines).
        # Narrowed to ImportError as well: anything else raised while
        # importing FreeCAD is a broken install, not an absent one.
        print("  SKIP  needs FreeCAD (BREP export)")
        print("SOLENOID3D GATE SKIPPED — no FreeCAD; run it under "
              "freecadcmd via tests/run_gate.py")
        return 2

    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.base import make_workdir
    from emstudio.solvers.elmer.model3d import build_3d_model, run3d
    from emstudio.templates import solenoid3d

    doc = FreeCAD.newDocument("gate_solenoid3d")
    skipped = []
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

        # live tier: asked UP FRONT whether the backends exist, because
        # that is the one question an exception cannot answer (see the
        # module docstring). Everything below runs a real solver.
        skipped = missing_backends()
        if skipped:
            print("  SKIP  live tier NOT RUN — backend(s) not installed: "
                  "{0}".format(", ".join(skipped)))
        else:
            # No try/except: with the backends present, a solve that raises
            # IS the regression this gate exists to catch. It propagates to
            # the auto-run guard below, which prints the traceback and exits
            # non-zero.
            from emstudio.solvers.elmer.runner3d import run_model3d

            res = run_model3d(model, workdir=os.path.join(workdir, "run"))
            line = res["saveline"]
            pts = sorted(zip(line["coordinate 3"],
                             line["magnetic flux density 3"]))
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
    if skipped:
        # Exit 2, NOT 0, and not the PASS token. run_battery.py declares no
        # SOLVER_REQS entry for this gate, so nothing upstream would turn a
        # silent zero into an honest "skip" line — the battery would print
        # "ok" for a run in which no solver ever started. Same contract as
        # whitney3d_elmer.py, which exits 2 for the identical reason.
        print("SOLENOID3D GATE SKIPPED — live tier did not run (backend(s) "
              "not installed: {0}); the template/extraction checks are green "
              "but NO solve ran and NO physics was verified".format(
                  ", ".join(skipped)))
        return 2
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
    if rc == 2:
        # SystemExit(int) is what tests/run_gate.py raises and maps back out,
        # so the 2 survives both the direct and the freecadcmd route. The
        # SKIPPED line above carries the reason.
        raise SystemExit(2)
    if rc != 0:
        raise SystemExit("solenoid3d validation failed")
    sys.exit(0)
