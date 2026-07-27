# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace ADAPTIVE fast frequency sweep vs the direct sweep.

Pass: exit 0 and 'FASTSWEEP GATE PASSED'.

Palace's adaptive fast frequency sweep builds a reduced-order model from a few
full solves and interpolates a DENSE S-parameter grid. On the validated WR-90
waveguide it must (a) reproduce the TE10 S-parameters at every dense point (so
the interpolation is exact, not just at the support frequencies) and (b) do it
from far fewer full solves than output points (the speedup).

Gate A (pure python3): run WR-90 over a dense 41-point grid (8-12 GHz, step
0.1) with fast_sweep=True; assert |S11| low, |S21|~0 dB and the S21 phase slope
match TE10 across ALL points, and that Palace converged with far fewer full
solves than 41 (scraped from its log).
    Reference run 2026-07-07 (Palace Order 2): 41 points from 6 full solves,
    |S11| -94.7 dB, |S21| dev 5.5e-6 dB, phase slope 0.0002 deg, ~60 s.

Gate B (freecadcmd only): the WR-90 template with FastSweep enabled runs the
full FreeCAD path.
"""
import cmath
import math
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
A_M = 22.86e-3   # WR-90 broad wall
L_M = 30e-3      # section length
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _beta(f_hz):
    return math.sqrt((2 * math.pi * f_hz / C0) ** 2 - (math.pi / A_M) ** 2)


def _validate_te10(result, tag, n_expected):
    import numpy as np

    f = result.freq
    s11 = result.s11
    s21 = result.s_others[(2, 1)]
    s11_db = 20.0 * np.log10(np.maximum(np.abs(s11), 1e-12))
    s21_db = 20.0 * np.log10(np.maximum(np.abs(s21), 1e-12))
    check("{0}: dense grid ({1}+ points)".format(tag, n_expected),
          len(f) >= n_expected, "{0} points".format(len(f)))
    check("{0}: |S11| low (matched)".format(tag), s11_db.max() < -30.0,
          "max {0:.1f} dB".format(s11_db.max()))
    check("{0}: |S21| ~ 0 dB everywhere".format(tag), np.abs(s21_db).max() < 0.05,
          "max dev {0:.3e} dB".format(np.abs(s21_db).max()))
    worst = 0.0
    for i in range(1, len(f)):
        dp = math.degrees(cmath.phase(s21[i]) - cmath.phase(s21[i - 1]))
        dp = (dp + 180.0) % 360.0 - 180.0
        da = math.degrees(-(_beta(f[i]) - _beta(f[i - 1])) * L_M)
        da = (da + 180.0) % 360.0 - 180.0
        worst = max(worst, abs(dp - da))
    check("{0}: S21 phase slope vs TE10 at every point".format(tag), worst < 1.0,
          "worst {0:.4f} deg".format(worst))


def gate_a_pure():
    from emstudio.solvers.palace import run_waveguide

    log_lines = []
    res = run_waveguide((22.86, 10.16, 30.0), axis=2, f1_ghz=8.0, f2_ghz=12.0,
                        step_ghz=0.1, order=2, fast_sweep=True, adaptive_tol=1e-3,
                        line_callback=log_lines.append)
    n_out = len(res.freq)
    _validate_te10(res, "WR-90 fast", 40)

    # the speedup: Palace solved far fewer full frequencies than it output
    n_full = None
    for line in log_lines:
        m = re.search(r"converged with\s+(\d+)\s+frequency samples", line)
        if m:
            n_full = int(m.group(1))
            break
    check("adaptive used far fewer full solves than output points",
          n_full is not None and n_full < n_out / 2.0,
          "{0} full solves for {1} output points".format(n_full, n_out))
    print("  (workdir: {0}, {1:.0f} s)".format(res.meta["workdir"], res.meta["duration_s"]))


def gate_b_template():
    import FreeCAD

    from emstudio.solvers import palace
    from emstudio.templates import waveguide

    doc = FreeCAD.newDocument("FastSweepGate")
    try:
        ana = waveguide.makeWaveguide(doc, length_mm=30.0, f1_ghz=8.0, f2_ghz=12.0,
                                      points=21)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverPalace"][0]
        solver.Order = 2
        solver.FastSweep = True
        result = palace.run(ana, solver)
        _validate_te10(result, "template fast", 20)
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio adaptive fast-frequency-sweep validation gate (Palace)")
    print("Gate A: WR-90 dense adaptive sweep vs TE10 (all points) + solve count")
    gate_a_pure()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD WR-90 template with FastSweep enabled")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("FASTSWEEP GATE FAILED: {0}".format(FAILURES))
        return 1
    print("FASTSWEEP GATE PASSED")
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
        raise SystemExit("fast-sweep validation failed")
    sys.exit(0)
