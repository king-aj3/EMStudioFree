# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — the UNSTEADY wind solve, run for real.

SOLVER tier: this actually runs `pimpleFoam` (~9 min on the reference box) and
checks the answer against published numbers. The FAST companion
(`wind_transient`) covers the case setup, the guard rails and the history
arithmetic; this one covers the only thing those cannot — whether the solve
reproduces the flow.

THE ANCHOR: a 2-D circular cylinder at Re 100, in the laminar shedding regime.

* **Strouhal number.** Williamson's correlation (J. Fluid Mech. 1988) for the
  laminar regime, St = -3.3265/Re + 0.1816 + 1.6e-4*Re, gives **0.1643** at
  Re 100. ⚠ This is the sharp check. Drag is forgiving of a coarse mesh and a
  short run; the shedding FREQUENCY is not, and it is what distinguishes a
  solve that resolves the physics from one that merely ran.
* **Mean drag** ~1.32-1.37 (Braza 1.364, Liu 1.35, Park 1.33).
* **Lift amplitude** ~0.32-0.34 — and non-zero lift is itself proof of
  shedding, because the steady solve's symmetric wake gives |Cl| ~2e-7.

⚠ The tolerances are the published SPREAD, not this box's measured numbers.
Gating on what we happened to measure would pass by construction and catch
nothing; gating on the literature's range can fail, which is the point.

Measured here 2026-08-14 (v2512, O-grid 80x30, 40 diameters, 40 cycles, half
discarded as startup): Cd 1.3411, St 0.1647, Cl amplitude 0.3275, 15 cycles.
"""
import os
import sys
import tempfile
import shutil

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
    from emstudio.solvers.openfoam import WindCase, run_wind

    print("EMStudio unsteady wind gate (LIVE SOLVE)")
    re = 100.0
    st_published = -3.3265 / re + 0.1816 + 1.6e-4 * re

    case = WindCase(reynolds=re, transient=True, cycles=40.0)
    print("  Re %g | U %.5g m/s | shed period %.4g s | dt0 %.3g s | end %.4g s"
          % (re, case.u_inf, case.shed_period, case.delta_t, case.end_time))

    tmp = tempfile.mkdtemp(prefix="windt_gate_")
    try:
        report, hist = run_wind(tmp, case, timeout=5400)
        if not report.get("ok"):
            check("the solve ran", False,
                  "{0}: {1}".format(report.get("failed_at"), report.get("error")))
            return 1
        check("the solve ran", True)

        # Shedding must actually have happened. Without this every number
        # below could come from a settled symmetric wake.
        check("whole shedding cycles were measured",
              report["cycles_measured"] >= 8,
              "{0} cycles".format(report["cycles_measured"]))
        check("lift OSCILLATES, so the wake is shedding",
              report["cl_amplitude"] > 0.15,
              "amplitude {0:.4f} (a steady solve gives ~2e-7)".format(
                  report["cl_amplitude"]))

        st = report["strouhal"]
        err = abs(st - st_published) / st_published * 100.0
        check("Strouhal {0:.4f} matches Williamson {1:.4f}".format(st, st_published),
              err < 5.0, "{0:.2f} % — the sharp check".format(err))

        cd = report["cd"]
        check("mean Cd {0:.4f} is in the published 1.30-1.40".format(cd),
              1.30 <= cd <= 1.40)
        check("lift amplitude {0:.4f} is in the published 0.28-0.38".format(
            report["cl_amplitude"]), 0.28 <= report["cl_amplitude"] <= 0.38)

        # The transient answer must BEAT the steady one it replaces. A steady
        # solve at this Re under-reads drag; if the unsteady number were no
        # better there would be no reason to pay for it.
        check("Cd is above the steady solve's under-read",
              cd > 1.15,
              "steady RANS at Re 100 gives ~1.0-1.1 with a symmetric wake")
        check("the case carries no validity caveat at Re 100",
              not report.get("validity"), report.get("validity", "")[:60])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-WIND-TRANSIENT GATE PASSED")
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
        raise SystemExit("openfoam-wind-transient validation failed")
    sys.exit(0)
