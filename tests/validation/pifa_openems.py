# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: PIFA against a PUBLISHED CHAMBER MEASUREMENT.

⭐ THIS IS THE PROJECT'S FIRST RADIATING ANCHOR AGAINST MEASURED HARDWARE.
--------------------------------------------------------------------------
Every other radiating gate here compares against something computed. The patch
reproduces openEMS's own tutorial GEOMETRY; the Ka-band horn compares against a
vendor's ANALYTIC (NRL) gain curve, and tutorial 33 says plainly that this is
weaker than a measured anchor; the n78 patch of item A1 is a consistency check
between two of our own models; the IFA rebuilds a published geometry whose
author published no numbers.

This one is different. The geometry AND its resonance were measured in an
anechoic chamber and published: a 20 x 20 mm top plate, 5 mm shorting plate at
the plate's side edge, 10 mm above an 80 mm square ground, measured at
**1.892 GHz** (Huynh, MS thesis, Virginia Tech 2000, Table 5-1; the same table
gives 1.886 GHz on a 100 mm ground, which is how we know the ground plane is
part of the antenna). See docs/upstream/pifa-anchors.md.

⚠⚠ THE FINDING THIS GATE EXISTS TO PROTECT
-------------------------------------------
The shorting plate's POSITION along the plate edge appears in NO term of the
Hirasawa closed form -- and it is worth **7.6 %**. Measured, on this exact
geometry, changing nothing else:

    shorting plate CENTRED on the edge -> 2.0370 GHz   (+7.66 % vs measured)
    shorting plate AT the side edge    -> 1.8930 GHz   (+0.05 % vs measured)

The closed form returns 1873.7 MHz for BOTH, because it cannot tell them apart.
So a PIFA built to the right L1/L2/H/W and the wrong short position is off by
more than the closed form's own stated accuracy, and nothing analytic will say
so. The template places the short at the edge; this gate is what stops that
quietly changing.

⛳ Not the IFA's mesh trap. ``ifa_openems`` has to gate feed-point impedance
because a coarse grid leaves that antenna SHORTED while still reporting the
right frequency. This antenna's smallest features are 5 mm and 10 mm, so the
default grid already resolves it -- measured, mesh 20 gives a real -11.18 dB
match. Zin is gated here anyway, cheaply, but it is not load-bearing the way it
is over there.

Expensive (full FDTD, ~30 s at the shipped mesh) -- NOT in the smoke suite.
Run:  freecadcmd tests/validation/pifa_openems.py
Pass: exit 0 and 'PIFA GATE PASSED'.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: The published CHAMBER MEASUREMENT for this geometry on its 80 mm ground (Hz).
MEASURED_HZ = 1.892e9

#: Window against that measurement. Measured mesh spread on this geometry is
#: 1.8849-1.9149 GHz across mesh 20..90, i.e. -0.37 % to +1.21 %; 3 % carries
#: that comfortably without being so wide it would accept the centred-short
#: geometry (+7.66 %), which is the error this gate exists to catch.
MEASURED_TOL = 0.03


def main():
    from emstudio.setup.solvers import find_openems_python

    if find_openems_python() is None:
        # NO self-skip-and-pass -- freecadcmd drops print(), so a gate returning
        # 0 from its own skip branch reports a success it never earned.
        raise SystemExit(
            "openEMS is required for this gate and was not found -- set "
            "EMSTUDIO_OPENEMS_PYTHON, or install openEMS with its venv beside "
            "the binary. (The battery skips this gate automatically; a direct "
            "run does not.)")
    import numpy as np
    import FreeCAD

    from emstudio.antenna import pifa as pifa_engine
    from emstudio.solvers import openems
    from emstudio.templates import pifa as pifa_tpl

    a = pifa_engine.ANCHOR
    f_form = pifa_engine.resonant_frequency(a["l1_m"], a["l2_m"], a["h_m"],
                                            a["w_m"])
    print("pifa: closed form {0:.4f} GHz; published measurement {1:.4f} GHz "
          "({2:+.2f} %)".format(f_form / 1e9, MEASURED_HZ / 1e9,
                                (f_form / MEASURED_HZ - 1.0) * 100.0))
    # The anchor dict is what both the engine and the template read. If someone
    # edits it, this says so in milliseconds instead of after a 30 s solve.
    assert a["short_at_edge"] is True, (
        "ANCHOR no longer records the short as being at the plate edge — that "
        "placement is worth 7.6 % and is not in the closed form")

    doc = FreeCAD.newDocument("pifa_gate")
    ana = pifa_tpl.makePIFA(doc)
    solver = [o for o in ana.Group
              if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]
    result = openems.run(ana, solver)

    f_min, s11_min = result.min_s11()
    i = int(np.argmin(result.s11_db()))
    zin = result.zin[i]
    print("pifa: FDTD {0:.4f} GHz ({1:+.2f} % vs MEASURED), S11 {2:.2f} dB, "
          "Zin {3:.2f} {4:+.2f}j ohm".format(
              f_min / 1e9, (f_min / MEASURED_HZ - 1.0) * 100.0, s11_min,
              zin.real, zin.imag))
    print("pifa: run took {0:.1f} s at mesh {1} in {2}".format(
        result.meta.get("duration_s", -1), ana.MeshResolution,
        result.meta.get("workdir", "?")))

    # --- the anchor: against MEASURED hardware ------------------------------
    lo = MEASURED_HZ * (1.0 - MEASURED_TOL)
    hi = MEASURED_HZ * (1.0 + MEASURED_TOL)
    assert lo <= f_min <= hi, (
        "PIFA resonance {0:.4f} GHz is outside +/-{1:.0%} of the PUBLISHED "
        "CHAMBER MEASUREMENT {2:.4f} GHz ({3:.4f}-{4:.4f} GHz). ⚠ A {5:.1f} % "
        "error is the signature of the shorting plate having moved off the "
        "plate edge — the closed form cannot see that, and this gate can."
        .format(f_min / 1e9, MEASURED_TOL, MEASURED_HZ / 1e9, lo / 1e9,
                hi / 1e9, (f_min / MEASURED_HZ - 1.0) * 100.0))

    # --- and still inside the closed form's own stated accuracy -------------
    assert abs(f_min / f_form - 1.0) <= pifa_engine.PIFA_ACCURACY, (
        "full-wave {0:.4f} GHz is outside the closed form's stated +/-{1:.0%} "
        "of its own {2:.4f} GHz — engine and solver now disagree by more than "
        "the engine admits to".format(f_min / 1e9, pifa_engine.PIFA_ACCURACY,
                                      f_form / 1e9))

    # --- a fed antenna, not a shorted one -----------------------------------
    assert 25.0 <= zin.real <= 60.0, (
        "feed-point resistance {0:.2f} ohm is not a 50 ohm-class match"
        .format(zin.real))
    assert abs(zin.imag) <= 20.0, (
        "feed-point reactance {0:+.2f}j ohm is too large — not resonant at its "
        "own best-match point".format(zin.imag))
    assert s11_min < -10.0, \
        "PIFA should dip below -10 dB (got {0:.1f} dB)".format(s11_min)

    db = result.s11_db()
    in_band = [x for x, d in zip(result.freq, db) if d <= -10.0]
    assert in_band, "no frequency reached -10 dB"
    bw = max(in_band) - min(in_band)
    print("pifa: -10 dB bandwidth {0:.1f} MHz ({1:.2f} %)".format(
        bw / 1e6, bw / f_min * 100.0))

    ff = getattr(result, "farfield", None)
    assert ff is not None, "openEMS run produced no far field"
    g_peak, th_peak, _ = ff.peak()
    print("pifa: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(
        g_peak, th_peak))
    assert 0.0 <= g_peak <= 5.0, (
        "peak gain {0:.2f} dBi outside the PIFA window — a low-profile plate "
        "over a small ground is a low-gain element".format(g_peak))

    print("PIFA GATE PASSED")
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
        raise SystemExit("pifa validation failed")
    sys.exit(0)
