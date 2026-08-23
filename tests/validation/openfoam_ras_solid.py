# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: kOmegaSST free convection on a solid at TURBULENT Ra.

Pass: exit 0 and 'OPENFOAM RAS SOLID GATE PASSED'.

**T4 of docs/OPENFOAM_TURBULENCE_PLAN.md, the §8a half.** The MODEL is
validated against a measured experiment by `openfoam_ras_cavity` (Betts &
Bokhari); THIS gate anchors the turbulent free-convection REGIME the §8a
dialog now enters above Ra 1e8, against Churchill's sphere correlation
(AJ's correlation-anchor ruling, 2026-08-23; the correlation is stated valid
to Ra 1e11). Everything runs through the product's own writer and runner —
`run_solid` on a `SolidCase(turbulence="kOmegaSST")` — never a hand case.

**Measured 2026-08-23 (uv_sphere r=0.5 m, 260 W, cells_bg 24, layered mesh,
12000 iterations, serial ~3.2 h):**

    kOmegaSST:  Nu_D 107.65 at resulting Ra_D 2.08e9 — Churchill 99.03,
                **+8.70 %**, SETTLED (dT drift 3.4e-4 < the 1e-3 bar)
    laminar  :  Nu_D  91.76 at resulting Ra_D 2.45e9 — Churchill 102.99,
                **−10.90 %**, NEVER SETTLES (drift 6.1e-3 at 12000 it)

⛳ **The discriminator is the SETTLE criterion, stated on purpose**: at
turbulent Ra both deltas fit inside the correlation's ±15 % scatter band, so
the Nu window alone could not kill the laminar mutation — but a steady
laminar solve of a turbulent flow has no steady state to find and its drift
never crosses the bar. The mutation is therefore caught by requirement, not
luck. The ±15 % band is the SAME `CHURCHILL_BAND` the laminar-regime solid
gate uses — correlation scatter, not tuned to this run.

⚠ The most expensive OpenFOAM gate after the horn: one ~3 h RAS solve.
`SLOW_GATES_TIMEOUT_S` carries its measured runtime.
"""
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: Churchill's correlation scatter — the laminar solid gate's own band.
CHURCHILL_BAND = 0.15
#: The regime floor the §8a dialog switches at; the case must genuinely land
#: above it or the gate is anchoring the wrong physics.
RA_TURBULENT = 1.0e8


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def churchill_sphere(ra_d, pr):
    """AHTT eq. 8.33 form, Ra_D <= 1e11, Pr >= 0.7."""
    if ra_d <= 0:
        raise ValueError("Ra must be positive")
    return 2.0 + (0.589 * ra_d ** 0.25
                  / (1.0 + (0.469 / pr) ** (9.0 / 16.0)) ** (4.0 / 9.0))


def main():
    from emstudio.solvers.openfoam.runner import run_solid
    from emstudio.solvers.openfoam.solid import SolidCase, uv_sphere

    print("EMStudio RAS solid gate (kOmegaSST turbulent sphere vs Churchill, "
          "through the product's own writer+runner)")
    tris = uv_sphere(0.5, n_theta=24, n_phi=48)
    d = 1.0
    case = SolidCase(triangles=tris, power_w=260.0, cells_bg=24,
                     iterations=12000, write_interval=3000,
                     turbulence="kOmegaSST")
    # The T4 chooser must agree this case is turbulent — this ties the gate
    # to the same estimate the §8a dialog switches on.
    check("ra_estimate puts this case above the 1e8 switch",
          case.ra_estimate() > RA_TURBULENT,
          "%.3g" % case.ra_estimate())

    wd = tempfile.mkdtemp(prefix="ras_solid_gate_")
    try:
        report, res = run_solid(wd, case, timeout=14400)
        if res is None:
            check("the chain completes", False, "{0}: {1}".format(
                report.get("failed_at"), report.get("error")))
            return 1
        check("the chain completes", True)
        # The product's own output, read back: the case must genuinely be RAS
        # (a silent laminar fallback here would validate nothing).
        with open(os.path.join(wd, "constant",
                               "turbulenceProperties")) as fh:
            tp = fh.read()
        check("written case declares RAS kOmegaSST",
              "RAS" in tp and "kOmegaSST" in tp)
        # ⛳ THE discriminator (see docstring): the laminar mutation NEVER
        # settles at turbulent Ra; requiring settlement is what makes the
        # ±15 % band below un-passable by the wrong model.
        drift = report.get("dt_drift")
        check("the solve SETTLED (converged or drift < 1e-3)",
              bool(report.get("converged"))
              or (drift is not None and drift < 1e-3),
              "converged=%s drift=%s (laminar mutation measured 6.1e-3)"
              % (report.get("converged"), drift))
        nu = res.nu_for(d)
        ra = res.ra_for(d)
        check("the RESULTING Ra is genuinely turbulent (>= %.0e)"
              % RA_TURBULENT, ra >= RA_TURBULENT, "Ra %.3g" % ra)
        want = churchill_sphere(ra, 0.705)
        check("Nu %.4f within %.0f%% of Churchill %.4f at the RESULTING "
              "Ra %.3g (measured +8.7%%; laminar mutation -10.9%% AND "
              "unsettled)" % (nu, 100 * CHURCHILL_BAND, want, ra),
              abs(nu - want) / want < CHURCHILL_BAND)
        print("  [ras] Nu %.4f at Ra %.4g, Churchill %.4f (%+.1f%%), "
              "dT %.2f K" % (nu, ra, want, 100.0 * (nu - want) / want,
                             res.dt))
    finally:
        shutil.rmtree(wd, ignore_errors=True)

    if FAILURES:
        print("OPENFOAM RAS SOLID GATE FAILED: {0}".format(FAILURES))
        return 1
    print("OPENFOAM RAS SOLID GATE PASSED")
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
        raise SystemExit("openfoam ras solid validation failed")
    sys.exit(0)
