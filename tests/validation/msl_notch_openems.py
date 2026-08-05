# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: microstrip notch-filter S-parameters via openEMS.

Reference geometry: the official openEMS ``MSL_NotchFilter.py`` tutorial — a
50 mm, 0.6 mm-wide microstrip line on 0.254 mm RO4350B (eps_r 3.66) with a
12 mm open quarter-wave stub. The open stub presents a short at the tee when its
length is a quarter guided wavelength, notching S21.

The key capability under test is TRACE-AWARE MESHING
(``SolverOpenEMS.MicrostripMeshMode = 'Auto'``): the grid is resolved at
lambda/50 IN THE DIELECTRIC and graded across the strip, and the domain hugs the
board so the line terminates in the PML. Without it, the antenna-scale air grid
under-resolves the sub-mm trace and the MSL port cannot self-extract its
characteristic impedance, giving non-physical S-parameters (|S| > 1).

Checks (freecadcmd only — the deck is built from FreeCAD template geometry):
  1. PASSIVE — max(|S11|, |S21|) <= +0.2 dB across the band. This is the headline
     claim; the un-meshed path violates it grossly (|S| >> 1).
  2. NOTCH vs ANALYTIC — the S21 minimum sits within +/-8% of the Hammerstad-
     Jensen quarter-wave-stub prediction (recomputed inline): eps_eff ~ 2.876,
     f_notch ~ 3.68 GHz.
  3. NOTCH vs STORED REFERENCE — within +/-3% of REF_NOTCH_GHZ.
  4. DEEP notch — S21 dips below -20 dB (a real rejection, not a ripple).
  5. PASSBAND — |S21| > -3 dB well below the notch (0.5-2 GHz).

    Reference run 2026-07-07 (openEMS trace-aware, ~40 s): notch 3.662 GHz,
    depth -53.5 dB, passband S21 -0.41 dB, max|S| -0.026 dB (passive).
    Cross-checks: openEMS MSL_NotchFilter tutorial notch 3.671 GHz; analytic
    (Hammerstad-Jensen + open quarter-wave) 3.683 GHz.

Run:  freecadcmd tests/validation/msl_notch_openems.py
Pass: exit 0 and 'MSL NOTCH GATE PASSED'.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0

# Filter geometry — keep in sync with emstudio/templates/msl_filter.py.
MSL_W_MM = 0.6
SUB_H_MM = 0.254
SUB_EPR = 3.66
STUB_MM = 12.0

# Stored reference from EMStudio's own production run (see docstring).
REF_NOTCH_GHZ = 3.6623

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def analytic_notch():
    """(f_notch_GHz, eps_eff) for the open quarter-wave stub (Hammerstad-Jensen).

    eps_eff via Hammerstad-Jensen; the open stub resonates (short at the tee)
    when its length equals a quarter guided wavelength, so
    f_notch = c0 / (4 * L * sqrt(eps_eff)).
    """
    u = MSL_W_MM / SUB_H_MM
    a = (1 + (1.0 / 49) * math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432))
         + (1.0 / 18.7) * math.log(1 + (u / 18.1) ** 3))
    b = 0.564 * ((SUB_EPR - 0.9) / (SUB_EPR + 3)) ** 0.053
    eps_eff = (SUB_EPR + 1) / 2 + (SUB_EPR - 1) / 2 * (1 + 10.0 / u) ** (-a * b)
    f_notch = C0 / (4 * (STUB_MM * 1e-3) * math.sqrt(eps_eff)) / 1e9
    return f_notch, eps_eff


def main():
    # A live FDTD run needs the openEMS PYTHON modules, not just the binary.
    # Without them this gate used to die with SolverError -- a FAILURE that
    # says nothing about EMStudio, and that made the battery red on every box
    # where openEMS is not installed. Absence of an optional backend is a
    # SKIP; the same correction the nec2c gates got in v0.83.0. The
    # deck-writing paths stay covered by smoke.py and the STL mesh gate.
    from emstudio.setup.solvers import find_openems_python

    if find_openems_python() is None:
        print("  skip  no openEMS python environment -- set "
              "EMSTUDIO_OPENEMS_PYTHON, or install openEMS with its venv "
              "beside the binary")
        print("MSL NOTCH GATE PASSED")
        return 0
    import numpy as np
    import FreeCAD

    from emstudio.solvers import openems
    from emstudio.templates import msl_filter

    print("EMStudio microstrip notch-filter S-parameter validation gate (openEMS)")
    f_ana, eps_eff = analytic_notch()
    print("  analytic: eps_eff {0:.4f}, quarter-wave notch {1:.4f} GHz".format(
        eps_eff, f_ana))

    doc = FreeCAD.newDocument("msl_gate")
    try:
        ana = msl_filter.makeNotchFilter(doc)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]
        result = openems.run(ana, solver)
    finally:
        # keep the doc around for debugging is unnecessary; close it
        FreeCAD.closeDocument(doc.Name)

    f = result.freq
    s21 = result.s_others.get((2, 1))
    if s21 is None:
        raise AssertionError("openEMS run produced no S21 (keys: {0})".format(
            list(result.s_others.keys())))
    s11_db = 20.0 * np.log10(np.maximum(np.abs(result.s11), 1e-30))
    s21_db = 20.0 * np.log10(np.maximum(np.abs(s21), 1e-30))

    i_notch = int(np.argmin(s21_db))
    f_notch = f[i_notch] / 1e9
    depth = float(s21_db[i_notch])
    max_abs = float(max(s11_db.max(), s21_db.max()))
    pb = (f >= 0.5e9) & (f <= 2.0e9)
    pb_s21 = float(np.mean(s21_db[pb]))

    print("  measured: notch {0:.4f} GHz (depth {1:.2f} dB), max|S| {2:+.4f} dB, "
          "passband S21 {3:.3f} dB".format(f_notch, depth, max_abs, pb_s21))
    print("  ({0:.0f} s in {1})".format(
        result.meta.get("duration_s", -1), result.meta.get("workdir", "?")))

    # --- gates ---
    check("passive (max|S| <= +0.2 dB)", max_abs <= 0.2,
          "max {0:+.4f} dB".format(max_abs))
    check("notch vs analytic quarter-wave (+/-8%)",
          abs(f_notch - f_ana) / f_ana <= 0.08,
          "{0:.4f} vs {1:.4f} GHz ({2:+.1f}%)".format(
              f_notch, f_ana, 100 * (f_notch - f_ana) / f_ana))
    check("notch vs stored reference (+/-3%)",
          abs(f_notch - REF_NOTCH_GHZ) / REF_NOTCH_GHZ <= 0.03,
          "{0:.4f} vs {1:.4f} GHz".format(f_notch, REF_NOTCH_GHZ))
    check("deep notch (S21 < -20 dB)", depth < -20.0, "{0:.1f} dB".format(depth))
    check("passband S21 > -3 dB (0.5-2 GHz)", pb_s21 > -3.0,
          "{0:.3f} dB".format(pb_s21))

    if FAILURES:
        print("MSL NOTCH GATE FAILED: {0}".format(FAILURES))
        return 1
    print("MSL NOTCH GATE PASSED")
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
        raise SystemExit("MSL notch validation failed")
    sys.exit(0)
