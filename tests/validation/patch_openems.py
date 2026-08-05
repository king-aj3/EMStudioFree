# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: microstrip patch antenna via the openEMS backend.

Reference: the official openEMS Python tutorial ``Simple_Patch_Antenna.py`` — the same
geometry (32 x 40 mm patch, 60 x 60 x 1.524 mm epsR 3.38 substrate, feed at x = -6 mm)
produces an S11 dip near 2.4 GHz.

This is the expensive gate (full FDTD run, ~minutes). Not part of the smoke suite.

Run:  freecadcmd tests/validation/patch_openems.py
Pass: exit 0 and 'PATCH GATE PASSED'.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


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

    from emstudio.solvers import openems
    from emstudio.templates import patch

    doc = FreeCAD.newDocument("patch_gate")
    ana = patch.makePatch(doc)
    solver = [
        o for o in ana.Group if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"
    ][0]

    result = openems.run(ana, solver)

    f_min, s11_min = result.min_s11()
    print("patch: best match {0:.2f} dB at {1:.4f} GHz".format(s11_min, f_min / 1e9))
    print("patch: run took {0:.1f} s in {1}".format(
        result.meta.get("duration_s", -1), result.meta.get("workdir", "?")))

    # --- gates ---
    # Tutorial reference: resonance ~2.4 GHz. Window allows for our slightly
    # tighter MUR domain (lambda/4 padding vs the tutorial's fixed 200 mm box).
    assert 2.30e9 <= f_min <= 2.50e9, (
        "patch resonance {0:.3f} GHz outside 2.30-2.50 GHz gate".format(f_min / 1e9)
    )
    assert s11_min < -10.0, "patch should dip below -10 dB (got {0:.1f} dB)".format(s11_min)

    # --- far-field gates ---
    # Typical microstrip patch directivity: 5-9 dBi, boresight (+z, theta=0).
    ff = getattr(result, "farfield", None)
    assert ff is not None, "openEMS run produced no far field"
    g_peak, th_peak, _ = ff.peak()
    print("patch: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(g_peak, th_peak))
    assert 4.5 <= g_peak <= 9.5, "peak gain {0:.2f} dBi outside patch gate".format(g_peak)
    assert th_peak <= 30.0 or th_peak >= 150.0, (
        "patch peak should be near boresight (theta={0:.0f})".format(th_peak)
    )

    # --- near-field map gate ---
    nf = getattr(result, "nearfield", None)
    assert nf is not None, "openEMS run produced no near-field map"
    e = nf["e_mag"]
    assert e.ndim == 2 and e.size > 100, "near-field map malformed: {0}".format(e.shape)
    assert e.max() > 0.0, "near-field map is all zero"
    print("patch: near-field {0} map, plane {1}".format(e.shape, str(nf.get("plane"))))

    print("PATCH GATE PASSED")
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
        raise SystemExit("patch validation failed")
    sys.exit(0)
