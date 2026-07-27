# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the Palace full-wave path holds at mmWave (~40 GHz and up).

Pass: exit 0 and 'MMWAVE GATE PASSED'.

EMStudio claims "DC to 40 GHz and beyond" for its full-wave analyses. This gate
backs that claim with a regression net: Palace FEM must reproduce closed-form
answers deep into the millimetre-wave band, where the only real cost is a finer
mesh (there is no physics-assumption break in full-wave Maxwell, unlike the
quasi-static Elmer/FastHenry paths — see docs/CAPABILITIES.md "Frequency range").

Gate A (pure python3):
  * two rectangular PEC cavities whose TE101 lands at ~39 GHz and ~57 GHz — each
    must match the closed-form f_101 to <0.1% (the 57 GHz point proves headroom
    well past 40 GHz);
  * a WR-22-class waveguide (a=5.69 mm, TE10 cutoff ~26 GHz) driven over 38-42 GHz
    must look like a matched TE10 line: |S21| ~ 0 dB and |S11| low at every point.
    Reference run 2026-07-07 (Palace Order 2): cavity 39.0255 GHz (+0.003%) /
    56.9092 GHz (+0.002%); WR-22 |S21| dev 5.4e-6 dB, |S11| -106 dB, ~45 s each.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def te101(size_mm):
    """Closed-form fundamental (GHz): the two largest cavity dimensions, m=p=1."""
    dims = sorted(s * 1e-3 for s in size_mm)
    x, y = dims[-1], dims[-2]
    return (C0 / 2.0) * math.sqrt((1.0 / x) ** 2 + (1.0 / y) ** 2) / 1e9


def gate_cavities():
    from emstudio.solvers.palace import run_cavity

    for size, label in [((6.0, 3.0, 5.0), "~39 GHz"), ((4.0, 2.0, 3.5), "~57 GHz")]:
        res = run_cavity(size, n_modes=4, order=2)
        dom = res.dominant_ghz()
        ana = te101(size)
        check("cavity TE101 at {0} ({1}) matches closed form (<0.1%)".format(
            label, size), abs(dom / ana - 1) < 0.001,
            "{0:.4f} GHz vs {1:.4f} GHz ({2:+.3%}), {3:.0f}s".format(
                dom, ana, dom / ana - 1, res.meta["duration_s"]))


def gate_waveguide_40ghz():
    import numpy as np

    from emstudio.solvers.palace import run_waveguide

    # WR-22 broad wall a=5.69 mm -> TE10 cutoff ~26.4 GHz; propagating over 38-42 GHz
    res = run_waveguide((5.69, 2.845, 10.0), f1_ghz=38.0, f2_ghz=42.0, step_ghz=1.0,
                        order=2)
    s21 = res.s_others[(2, 1)]
    s21_db = 20.0 * np.log10(np.maximum(np.abs(s21), 1e-12))
    s11_db = 20.0 * np.log10(np.maximum(np.abs(res.s11), 1e-12))
    check("WR-22 waveguide propagates at 40 GHz (|S21| ~ 0 dB)",
          np.abs(s21_db).max() < 0.05, "max dev {0:.3e} dB".format(np.abs(s21_db).max()))
    check("WR-22 matched TE10 at 40 GHz (|S11| low)", s11_db.max() < -30.0,
          "max {0:.1f} dB over {1} pts, {2:.0f}s".format(
              s11_db.max(), len(res.freq), res.meta["duration_s"]))


def main():
    print("EMStudio mmWave full-wave validation gate (Palace, ~40 GHz and up)")
    print("Gate A: cavity eigenmodes at 39 & 57 GHz + WR-22 driven S-params at 40 GHz")
    gate_cavities()
    gate_waveguide_40ghz()
    if FAILURES:
        print("MMWAVE GATE FAILED: {0}".format(FAILURES))
        return 1
    print("MMWAVE GATE PASSED")
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
        raise SystemExit("mmwave validation failed")
    sys.exit(0)
