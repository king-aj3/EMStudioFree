# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — solid convection (§8a), run FOR REAL on a sphere.

SOLVER tier. Two rungs, both on the UV sphere because the sphere is the
one solid with closed-form anchors, and both at a GATE fidelity smaller
than the recorded full-fidelity probes (2026-08-17, cells_bg 32):

* full-fidelity conduction: Nu_D 2.5575, mid-sandwich (the gate rung at
  cells_bg 24 lands 2.5511 — 0.25 % apart, so the anchor is comfortably
  mesh-insensitive);
* full-fidelity convection: Nu_D 18.1748 at Ra_D 1.33e6 — Churchill's
  sphere correlation gives 17.42 there, so the whole arbitrary-geometry
  chain (tessellate -> snappy -> flux BC -> patch read) lands +4.3 %
  (+5.6 % at gate fidelity), inside the correlation's own scatter and
  beside the bundle ladder's single-cylinder rungs (+7.0 %/+3.0 %).

Rung 1 — CONDUCTION SANDWICH (g = 0). The exact two-sided bound
2/(1-r/r_cir) <= Nu <= 2/(1-r/r_ins) holds for the CONTINUUM solution;
the gate asserts it with a small recorded discretisation margin at gate
fidelity. A coupling that loses flux, reads the wrong patch, or heats the
wrong side leaves the sandwich — in either direction, which is what makes
it sharper than any one-sided tolerance.

Rung 2 — CONVECTION vs Churchill. The gate asserts (a) the SELF-PIN: the
same case reproduces its own recorded Nu (snappy is deterministic; a
quiet re-mesh or scheme change moves it), and (b) the physics window:
within the Churchill band. Ra is an OUTPUT (flux BC): the comparison is
made at the Ra that resulted.

⚠ The conduction rung is the SLOW one: pure diffusion under SIMPLE's
relaxation needs thousands of iterations, and an unconverged conduction
solve reads HIGH (the surface is still heating). The first probe measured
exactly that: Nu 2.83 at 8.7 % drift, outside the sandwich, converging
into it. The gate therefore also asserts the drift it converged to.
"""
import math
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
                                 " - " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


#: Gate fidelity — smaller than the recorded probes so the rung fits a
#: SOLVER-tier budget; the pins below were measured AT THIS fidelity.
GATE_CELLS = 24
R_SPHERE = 0.05

#: SELF-PINS, measured 2026-08-18 at GATE_CELLS on the reference box.
#: These are this project's own numbers with their configuration recorded —
#: not literature anchors. See docs/PROJECT_MEMORY.md for the full-fidelity
#: (cells_bg 32) companions.
PIN_CONDUCTION_NU = 2.5511    # measured 2026-08-17, first gate run
PIN_CONVECTION_NU = 18.3508   # measured 2026-08-17, first gate run
PIN_TOL = 0.03                # re-run reproducibility band
#: Discretisation margin at gate fidelity. ⚠ It also covers the small gap
#: between the UNWEIGHTED face mean the reader computes and the
#: area-weighted mean the sandwich theorem strictly bounds — snapped faces
#: are near-uniform on a sphere, so the difference is far inside this.
SANDWICH_MARGIN = 0.03
CHURCHILL_BAND = 0.15         # correlation scatter + laminar snapped mesh


def churchill_sphere(ra_d, pr):
    """Churchill's free-convection sphere correlation (AHTT eq. 8.33 form),
    Ra_D <= 1e11, Pr >= 0.7: Nu = 2 + 0.589 Ra^1/4 / [1+(0.469/Pr)^9/16]^4/9."""
    if ra_d <= 0:
        raise ValueError("Ra must be positive")
    return 2.0 + (0.589 * ra_d ** 0.25
                  / (1.0 + (0.469 / pr) ** (9.0 / 16.0)) ** (4.0 / 9.0))


def main():
    from emstudio.solvers.openfoam.runner import run_solid
    from emstudio.solvers.openfoam.solid import SolidCase, uv_sphere

    print("EMStudio solid-convection gate (LIVE SOLVES, sphere anchors)")
    tris = uv_sphere(R_SPHERE, n_theta=24, n_phi=48)
    d = 2.0 * R_SPHERE

    # ---- rung 1: the conduction sandwich ---------------------------------
    wd = tempfile.mkdtemp(prefix="solid_gate_cond_")
    try:
        case = SolidCase(triangles=tris, power_w=0.5, gravity=0.0,
                         cells_bg=GATE_CELLS, iterations=12000,
                         write_interval=3000)
        lo, up = case.conduction_nu_bounds(R_SPHERE)
        report, res = run_solid(wd, case, timeout=7200)
        if res is None:
            check("conduction rung ran", False, "{0}: {1}".format(
                report.get("failed_at"), report.get("error")))
            return 1
        check("conduction rung ran", True)
        nu = res.nu_for(d)
        drift = report.get("dt_drift")
        check("conduction solve settled (drift < 1e-3 or converged)",
              bool(report.get("converged"))
              or (drift is not None and drift < 1e-3),
              "converged=%s drift=%s" % (report.get("converged"), drift))
        check("Nu %.4f inside the EXACT sandwich [%.4f, %.4f] "
              "(margin %.0f%%)" % (nu, lo, up, 100 * SANDWICH_MARGIN),
              lo * (1.0 - SANDWICH_MARGIN) <= nu <= up * (1.0 + SANDWICH_MARGIN),
              "an unconverged solve reads HIGH; a lost-flux coupling reads LOW")
        if PIN_CONDUCTION_NU:
            check("conduction self-pin %.4f (recorded %.4f)"
                  % (nu, PIN_CONDUCTION_NU),
                  abs(nu - PIN_CONDUCTION_NU) / PIN_CONDUCTION_NU < PIN_TOL)
        cond_spread = res.t_max - res.t_min
        print("  [conduction] Nu %.4f, sandwich [%.4f, %.4f], drift %s, "
              "spread %.3f K" % (nu, lo, up, drift, cond_spread))
    finally:
        shutil.rmtree(wd, ignore_errors=True)

    # ---- rung 2: convection vs Churchill ---------------------------------
    wd = tempfile.mkdtemp(prefix="solid_gate_conv_")
    try:
        case = SolidCase(triangles=tris, power_w=2.8, cells_bg=GATE_CELLS,
                         iterations=8000, write_interval=2000)
        report, res = run_solid(wd, case, timeout=7200)
        if res is None:
            check("convection rung ran", False, "{0}: {1}".format(
                report.get("failed_at"), report.get("error")))
            return 1
        check("convection rung ran", True)
        check("convection solve converged or settled",
              bool(report.get("converged"))
              or (report.get("dt_drift") is not None
                  and report["dt_drift"] < 1e-3),
              "converged=%s drift=%s" % (report.get("converged"),
                                         report.get("dt_drift")))
        nu = res.nu_for(d)
        ra = res.ra_for(d)
        want = churchill_sphere(ra, 0.705)
        check("Nu %.4f within %.0f%% of Churchill %.4f at the RESULTING "
              "Ra %.3g" % (nu, 100 * CHURCHILL_BAND, want, ra),
              abs(nu - want) / want < CHURCHILL_BAND)
        spread = res.t_max - res.t_min
        check("buoyancy signature: convective spread %.2f K exceeds 5x the "
              "conduction rung's %.3f K" % (spread, cond_spread),
              spread > 5.0 * cond_spread and spread > 2.0,
              "a no-flow solve has the conduction rung's near-uniform "
              "surface")
        if PIN_CONVECTION_NU:
            check("convection self-pin %.4f (recorded %.4f)"
                  % (nu, PIN_CONVECTION_NU),
                  abs(nu - PIN_CONVECTION_NU) / PIN_CONVECTION_NU < PIN_TOL)
        print("  [convection] Nu %.4f at Ra %.4g, Churchill %.4f (%+.1f%%)"
              % (nu, ra, want, 100.0 * (nu - want) / want))
    finally:
        shutil.rmtree(wd, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-SOLID GATE PASSED")
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
        raise SystemExit("openfoam-solid validation failed")
    sys.exit(0)
