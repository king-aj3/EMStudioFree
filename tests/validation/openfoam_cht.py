# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — conjugate heat transfer, run for real.

SOLVER tier: runs `chtMultiRegionSimpleFoam` on a two-region conduction stack
(~3 min on the reference box) and compares against the closed form.

⚠ The tolerance is TIGHT on purpose. This is not a correlation with a
literature spread — with g = 0 the answer is exact, and the cell-average of a
linear profile equals its analytic mean on uniform cells. So the solve should
land on the analytic means to within solver tolerance, and it does: measured
2026-08-14, both means agreed to 5 decimal places (+0.00000 K).

A loose tolerance here would hide the failure this gate exists for — a coupled
interface that transmits temperature but not flux still produces a smooth,
plausible field; what it gets wrong is WHERE the interface temperature sits,
and therefore how the total drop divides between the two layers.
"""
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(label, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", label,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


def main():
    from emstudio.solvers.openfoam.cht import ChtCase
    from emstudio.solvers.openfoam.runner import run_cht

    print("EMStudio conjugate heat transfer gate (LIVE SOLVE)")
    case = ChtCase()
    print("  k_solid %.4g  k_fluid %.4g W/m/K | q %.4f W/m^2 | T_int %.4f K"
          % (case.k_solid, case.k_fluid, case.flux, case.t_interface))

    tmp = tempfile.mkdtemp(prefix="cht_gate_")
    try:
        report, means = run_cht(tmp, case, timeout=3600)
        if not report.get("ok"):
            check("the solve ran", False, "{0}: {1}".format(
                report.get("failed_at"), report.get("error")))
            for s in report.get("steps", []):
                if s.get("rc"):
                    print("    last of {0}:\n{1}".format(
                        s["step"], s.get("tail", "")[-600:]))
            return 1
        check("the solve ran", True)

        # The interface patch must have been DISCOVERED, not assumed.
        patches = report.get("patches") or {}
        check("both regions were split and their patches found",
              len(patches) == 2 and all(
                  any(p.startswith(r + "_to_") for p in names)
                  for r, names in patches.items()),
              str(patches))

        for label, got, want in (
                ("solid", report["t_solid_mean"], case.t_solid_mean),
                ("fluid", report["t_fluid_mean"], case.t_fluid_mean)):
            err = abs(got - want)
            check("{0} mean {1:.5f} K matches the exact {2:.5f} K".format(
                label, got, want), err < 0.01,
                "{0:+.5f} K — the answer is EXACT here, not a correlation".format(
                    got - want))

        # The division of the total drop is the thing a bad coupling gets
        # wrong, so state it as its own check rather than trusting the means.
        t_int = 2.0 * report["t_solid_mean"] - case.t_hot
        check("interface temperature {0:.4f} K matches the exact {1:.4f} K"
              .format(t_int, case.t_interface),
              abs(t_int - case.t_interface) < 0.02,
              "recovered from the solid mean, which is linear in T_int")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-CHT GATE PASSED")
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
        raise SystemExit("openfoam-cht validation failed")
    sys.exit(0)
