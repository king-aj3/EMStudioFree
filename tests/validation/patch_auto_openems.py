# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: SYNTHESIZED microstrip patch via openEMS (Element Designer E4).

Unlike ``patch_openems.py`` (which solves the fixed openEMS tutorial geometry),
this gate SYNTHESIZES a patch from the ``patch_tl`` TL engine (``makePatchDesign``)
at 2.4 GHz on the tutorial substrate (εr 3.38, h 1.524 mm) and checks the openEMS
FDTD resonance lands within the TL model's stated **±5 %** of the design frequency,
with a patch-class boresight gain. This closes the loop: the analytic synthesis
predicts the geometry, the full-wave solve confirms the resonance.

Expensive (full FDTD, ~minutes) — NOT in the smoke suite. Needs the openEMS venv.
Run:  freecadcmd tests/validation/patch_auto_openems.py
Pass: exit 0 and 'PATCH-AUTO GATE PASSED'.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: Every bound below prints one "  ok"/"  FAIL" line, so the battery can COUNT
#: what this gate checked. Until 2026-09-25 they were bare asserts: the gate
#: passed with ZERO countable lines, and a run that checked nothing looked the
#: same as one that checked everything. (The v1.13.0 proof log names this gate
#: in its "ZERO per-check lines" warning.)
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _verdict():
    if FAILURES:
        print("PATCH-AUTO GATE FAILED: {0}".format(FAILURES))
        return 1
    print("PATCH-AUTO GATE PASSED")
    return 0


def main():
    # A live FDTD run needs the openEMS PYTHON modules, not just the binary.
    # Without them this gate used to die with SolverError -- a FAILURE that
    # says nothing about EMStudio, and that made the battery red on every box
    # where openEMS is not installed. Absence of an optional backend is a
    # SKIP; the same correction the nec2c gates got in v0.83.0. The
    # deck-writing paths stay covered by smoke.py and the STL mesh gate.
    from emstudio.setup.solvers import find_openems_python

    if find_openems_python() is None:
        # NO self-skip-and-pass. This used to print the PASSED banner and
        # return 0, so on a box without openEMS the gate reported success
        # while testing nothing -- and freecadcmd drops print(), so the exit
        # code was the only thing a caller saw. Skipping is the BATTERY's job
        # (run_battery.SOLVER_REQS declares "openems_python" for this gate and
        # prints a real "skip"); running this file BY HAND must fail loudly,
        # because you asked for it specifically.
        raise SystemExit(
            "openEMS is required for this gate and was not found -- set "
            "EMSTUDIO_OPENEMS_PYTHON, or install openEMS with its venv beside "
            "the binary. (The battery skips this gate automatically; a direct "
            "run does not.)")
    import FreeCAD

    from emstudio.antenna import patch_tl
    from emstudio.solvers import openems
    from emstudio.templates import patch

    f0 = 2.4e9
    des = patch_tl.design_patch(f0, 3.38, 1.524e-3)
    print("patch-auto: synthesized W {0:.2f} mm, L {1:.2f} mm, feed offset "
          "{2:.2f} mm, predicted gain {3:.1f} dBi".format(
              des["width_m"] * 1e3, des["length_m"] * 1e3,
              des["feed_offset_m"] * 1e3, des["gain_dbi"]))

    doc = FreeCAD.newDocument("patch_auto_gate")
    ana = patch.makePatchDesign(doc, f0_hz=f0, er=3.38, h_mm=1.524)
    solver = [o for o in ana.Group
              if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]

    result = openems.run(ana, solver)
    f_min, s11_min = result.min_s11()
    print("patch-auto: FDTD best match {0:.2f} dB at {1:.4f} GHz (design "
          "{2:.3f} GHz)".format(s11_min, f_min / 1e9, f0 / 1e9))
    print("patch-auto: run took {0:.1f} s in {1}".format(
        result.meta.get("duration_s", -1), result.meta.get("workdir", "?")))

    # --- gates: resonance within the TL model's stated ±5 % of f0 ----------
    lo, hi = f0 * (1.0 - patch_tl.TL_ACCURACY), f0 * (1.0 + patch_tl.TL_ACCURACY)
    check("resonance within the TL model's +/-{0:.0%} of the {1:.3f} GHz "
          "design ({2:.3f}-{3:.3f} GHz)".format(
              patch_tl.TL_ACCURACY, f0 / 1e9, lo / 1e9, hi / 1e9),
          lo <= f_min <= hi, "{0:.4f} GHz".format(f_min / 1e9))
    check("S11 dips below -10 dB", s11_min < -10.0, "{0:.2f} dB".format(s11_min))

    ff = getattr(result, "farfield", None)
    check("openEMS produced a far field", ff is not None)
    if ff is not None:
        g_peak, th_peak, _ = ff.peak()
        print("patch-auto: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(
            g_peak, th_peak))
        check("peak gain within 4.5-9.5 dBi (patch class)", 4.5 <= g_peak <= 9.5,
              "{0:.2f} dBi".format(g_peak))
        check("peak near boresight (theta <= 30 or >= 150 deg)",
              th_peak <= 30.0 or th_peak >= 150.0, "theta={0:.0f}".format(th_peak))

    return _verdict()


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
        raise SystemExit("patch-auto validation failed")
    sys.exit(0)
