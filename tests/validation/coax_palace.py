# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace coaxial-line S-parameters vs TEM theory (lumped ports).

Pass: exit 0 and 'COAX GATE PASSED'.

A uniform air coaxial line (inner radius a, outer b, length L) driven through a
RADIAL LUMPED PORT at each end, referenced to its own characteristic impedance
Z0 = (eta0 / 2pi) / sqrt(eps_r) * ln(b/a), is a matched, lossless TEM line, so:
* |S11| ~ 0 (numerically low) — the lumped port matches the line,
* |S21| ~ 1 (0 dB) — lossless transmission (a small constant lumped-port
  normalization offset is not gain),
* arg(S21) advances as -beta*L with the TEM phase constant
  beta = 2*pi*f*sqrt(eps_r)/c0 (no cutoff). The gate checks the phase SLOPE
  d(arg S21) between frequencies = -(beta2-beta1)*L, immune to any lumped-port
  de-embedding reference-plane offset.
    Reference run 2026-07-07 (Palace, Order 2, air line a=0.5/b=1.15 mm, ~35 s):
    Z0 = 49.94 ohm, max|S11| = -29.3 dB, |S21| = +0.34 dB, phase-slope err 0.043 deg.

Gate B (freecadcmd only): the Coaxial Line template runs the full FreeCAD path.
"""
import cmath
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
ETA0 = 376.730313668
# gate geometry (air line ~50 ohm) — kept in sync with templates/coax.py
A_MM, B_MM, L_MM, EPS_R = 0.5, 1.15, 20.0, 1.0
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _beta(f_hz):
    return 2.0 * math.pi * f_hz * math.sqrt(EPS_R) / C0  # TEM: no cutoff


def _z0():
    return (ETA0 / (2.0 * math.pi)) / math.sqrt(EPS_R) * math.log(B_MM / A_MM)


def _validate(result, tag):
    import numpy as np

    f = result.freq
    s11 = result.s11
    s21 = result.s_others[(2, 1)]
    s11_db = 20.0 * np.log10(np.maximum(np.abs(s11), 1e-12))
    s21_db = 20.0 * np.log10(np.maximum(np.abs(s21), 1e-12))
    check("{0}: |S11| low (matched line)".format(tag), s11_db.max() < -20.0,
          "max {0:.1f} dB".format(s11_db.max()))
    check("{0}: |S21| ~ 0 dB (lossless)".format(tag), np.abs(s21_db).max() < 1.0,
          "max dev {0:.3f} dB".format(np.abs(s21_db).max()))
    # phase-slope vs -beta*L (reference-plane-independent)
    L_m = L_MM * 1e-3
    worst = 0.0
    for i in range(1, len(f)):
        dp_p = math.degrees(cmath.phase(s21[i]) - cmath.phase(s21[i - 1]))
        dp_p = (dp_p + 180.0) % 360.0 - 180.0
        dp_a = math.degrees(-(_beta(f[i]) - _beta(f[i - 1])) * L_m)
        dp_a = (dp_a + 180.0) % 360.0 - 180.0
        worst = max(worst, abs(dp_p - dp_a))
    check("{0}: S21 phase slope vs TEM -beta*L".format(tag), worst < 1.0,
          "worst {0:.3f} deg".format(worst))
    # characteristic impedance (analytic vs the run's reference)
    check("{0}: Z0 ~ 50 ohm".format(tag), abs(result.z0 - _z0()) < 0.1,
          "{0:.2f} ohm".format(result.z0))


def gate_a_pure():
    from emstudio.solvers.palace import run_coax

    res = run_coax(a_mm=A_MM, b_mm=B_MM, length_mm=L_MM, eps_r=EPS_R,
                   f1_ghz=2.0, f2_ghz=6.0, step_ghz=1.0, order=2, elem_mm=0.4)
    _validate(res, "air-coax")
    print("  (workdir: {0}, {1:.0f} s)".format(res.meta["workdir"], res.meta["duration_s"]))


def gate_b_template():
    import FreeCAD

    from emstudio.solvers import palace
    from emstudio.templates import coax

    doc = FreeCAD.newDocument("CoaxGate")
    try:
        ana = coax.makeCoax(doc)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverPalace"][0]
        result = palace.run(ana, solver)
        _validate(result, "template")
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio coaxial-line S-parameter validation gate (Palace lumped ports)")
    print("analytic Z0 = {0:.3f} ohm".format(_z0()))
    print("Gate A: air coax radial lumped ports vs TEM theory")
    gate_a_pure()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD coaxial-line template end-to-end")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("COAX GATE FAILED: {0}".format(FAILURES))
        return 1
    print("COAX GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    # freecadcmd exits 0 on uncaught exceptions (verified 2026-07-05) — convert
    # EVERY failure into SystemExit, which does propagate a non-zero exit code.
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("coax validation failed")
    sys.exit(0)
