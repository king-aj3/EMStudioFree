# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: half-wave dipole via the NEC2 backend.

Physics reference: a thin-wire center-fed dipole of length L = 0.475 lambda0 resonates
(reactance zero-crossing) within a few percent of f0, with a feedpoint resistance near
the textbook ~70 ohm (67-73 ohm for practical wire radii; Balanis, Antenna Theory).

Run:  freecadcmd tests/validation/dipole_nec2.py
Pass: exit 0 and 'DIPOLE GATE PASSED'.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    import FreeCAD

    import numpy as np

    from emstudio.solvers import nec2
    from emstudio.templates import dipole

    doc = FreeCAD.newDocument("dipole_gate")
    ana = dipole.makeDipole(doc, f0_hz=300e6, wire_radius_mm=2.0)
    solver = [o for o in ana.Group if getattr(o, "EMStudioType", "") == "EMStudio::SolverNEC2"][0]

    result = nec2.run(ana, solver)

    res_list = result.resonances()
    assert res_list, "no reactance zero-crossing found in sweep"
    f_res = res_list[0]
    r_res = result.r_at(f_res)
    f_min, s11_min = result.min_s11()

    print("dipole: f_res = {0:.2f} MHz, R(f_res) = {1:.1f} ohm".format(f_res / 1e6, r_res))
    print("dipole: best match {0:.2f} dB at {1:.2f} MHz".format(s11_min, f_min / 1e6))
    print("dipole: run took {0:.2f} s in {1}".format(
        result.meta.get("duration_s", -1), result.meta.get("workdir", "?")))

    # --- gates ---
    # Reference run 2026-07-05 (nec2c 1.3.1): f_res=296.29 MHz, R=71.9 ohm,
    # S11min=-15.2 dB. Windows allow ~2% drift across nec2c versions/platforms.
    assert 290e6 <= f_res <= 303e6, "resonance {0:.1f} MHz outside gate".format(f_res / 1e6)
    assert 64.0 <= r_res <= 79.0, "feedpoint R {0:.1f} ohm outside gate".format(r_res)
    assert s11_min < -12.0, "dipole should match better than -12 dB vs 50 ohm"

    # --- far-field gates ---
    # Literature: lambda/2 dipole peak gain 2.15 dBi, donut pattern with nulls on
    # axis. Reference probe 2026-07-05: 2.13 dBi at theta=90.
    ff = result.farfield
    assert ff is not None, "NEC2 run produced no far field: " + str(
        result.meta.get("farfield_error"))
    g_peak, th_peak, _ = ff.peak()
    print("dipole: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(g_peak, th_peak))
    assert 1.9 <= g_peak <= 2.4, "peak gain {0:.2f} dBi outside 1.9-2.4 gate".format(g_peak)
    assert 80.0 <= th_peak <= 100.0, "peak not broadside (theta={0:.0f})".format(th_peak)
    theta_axis_gain = ff.cut(0.0)[1][0]  # gain at theta=0 (on axis)
    assert theta_axis_gain < -20.0, "axial null missing (got {0:.1f} dBi)".format(theta_axis_gain)

    # --- current-distribution gate ---
    # A resonant half-wave dipole has a half-sine current: max at the center feed,
    # ~zero at the wire ends.
    cur = getattr(result, "currents", None)
    assert cur is not None, "NEC2 run produced no current distribution"
    i_mag = cur["i_mag"]
    n = len(i_mag)
    peak_frac = int(np.argmax(i_mag)) / n
    end_ratio = (i_mag[0] + i_mag[-1]) / 2.0 / i_mag.max()
    print("dipole: {0} segs, peak at {1:.2f} of length, end/peak {2:.3f}".format(
        n, peak_frac, end_ratio))
    assert 0.4 <= peak_frac <= 0.6, "current peak not at center (frac {0:.2f})".format(peak_frac)
    assert end_ratio < 0.2, "current not near-zero at ends (ratio {0:.3f})".format(end_ratio)

    print("DIPOLE GATE PASSED")
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
        raise SystemExit("dipole validation failed")
    sys.exit(0)
