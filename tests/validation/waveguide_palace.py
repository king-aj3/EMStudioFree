# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace WR-90 waveguide S-parameters vs TE10 theory.

Pass: exit 0 and 'WAVEGUIDE GATE PASSED'.

A straight air-filled WR-90 section (a x b = 22.86 x 10.16 mm) with a wave
port on each end is a matched, uniform, lossless guide over X-band, so:
* |S11| ~ 0 (numerically -90 dB or lower) — no reflection,
* |S21| ~ 1 (0 dB) — lossless transmission,
* arg(S21) advances as -beta*L with the TE10 propagation constant
  beta = sqrt((2*pi*f/c0)^2 - (pi/a)^2). The gate checks the phase SLOPE
  d(arg S21) between frequencies = -(beta2-beta1)*L, which is immune to any
  wave-port reference-plane offset.
    Reference run 2026-07-06 (Palace, Order 2): |S11|<-94 dB, |S21|=0.000 dB,
    phase-slope error < 0.01 deg.

Gate B (freecadcmd only): the WR-90 template runs the full FreeCAD path.
"""
import cmath
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
A_M = 22.86e-3  # WR-90 broad wall
L_M = 30e-3     # section length
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _beta(f_hz):
    return math.sqrt((2 * math.pi * f_hz / C0) ** 2 - (math.pi / A_M) ** 2)


def _validate(result, tag):
    import numpy as np

    f = result.freq
    s11 = result.s11
    s21 = result.s_others[(2, 1)]
    s11_db = 20.0 * np.log10(np.maximum(np.abs(s11), 1e-12))
    s21_db = 20.0 * np.log10(np.maximum(np.abs(s21), 1e-12))
    check("{0}: |S11| low (matched guide)".format(tag), s11_db.max() < -30.0,
          "max {0:.1f} dB".format(s11_db.max()))
    check("{0}: |S21| ~ 0 dB (lossless)".format(tag), np.abs(s21_db).max() < 0.05,
          "max dev {0:.4f} dB".format(np.abs(s21_db).max()))
    # phase-slope vs -beta*L (reference-plane-independent)
    worst = 0.0
    for i in range(1, len(f)):
        dp_p = math.degrees(cmath.phase(s21[i]) - cmath.phase(s21[i - 1]))
        dp_p = (dp_p + 180.0) % 360.0 - 180.0
        dp_a = math.degrees(-(_beta(f[i]) - _beta(f[i - 1])) * L_M)
        dp_a = (dp_a + 180.0) % 360.0 - 180.0
        worst = max(worst, abs(dp_p - dp_a))
    check("{0}: S21 phase slope vs TE10 -beta*L".format(tag), worst < 1.0,
          "worst {0:.3f} deg".format(worst))


def gate_a_pure():
    from emstudio.solvers.palace import run_waveguide

    res = run_waveguide((22.86, 10.16, 30.0), axis=2, f1_ghz=8.0, f2_ghz=12.0,
                        step_ghz=1.0, order=2)
    _validate(res, "WR-90")
    print("  (workdir: {0}, {1:.0f} s)".format(res.meta["workdir"], res.meta["duration_s"]))


def gate_b_template():
    import FreeCAD

    from emstudio.solvers import palace
    from emstudio.templates import waveguide

    doc = FreeCAD.newDocument("WgGate")
    try:
        ana = waveguide.makeWaveguide(doc, length_mm=30.0, f1_ghz=8.0, f2_ghz=12.0,
                                      points=5)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverPalace"][0]
        solver.Order = 2
        result = palace.run(ana, solver)
        _validate(result, "template")
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio WR-90 waveguide S-parameter validation gate (Palace)")
    print("Gate A: WR-90 driven wave ports vs TE10 theory")
    gate_a_pure()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD WR-90 template end-to-end")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("WAVEGUIDE GATE FAILED: {0}".format(FAILURES))
        return 1
    print("WAVEGUIDE GATE PASSED")
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
        raise SystemExit("waveguide validation failed")
    sys.exit(0)
