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
        print("PIFA GATE FAILED: {0}".format(FAILURES))
        return 1
    print("PIFA GATE PASSED")
    return 0

#: The published CHAMBER MEASUREMENT for this geometry on its 80 mm ground (Hz).
MEASURED_HZ = 1.892e9

#: Window against that measurement. Measured mesh spread on this geometry is
#: 1.8849-1.9149 GHz across mesh 20..90, i.e. -0.37 % to +1.21 %; 3 % carries
#: that comfortably without being so wide it would accept the centred-short
#: geometry (+7.66 %), which is the error this gate exists to catch.
MEASURED_TOL = 0.03

#: B-i rung 1 — the GROUND-PLANE LADDER. Ground sides (mm) solved in addition
#: to the anchor's own 80 mm, each against Huynh Table 5-1's MEASURED column.
#:
#: ⭐ WHY THIS EXISTS. Until 2026-08-27 this project had ONE measured radiating
#: point. The same table publishes the same antenna on seven ground sizes, and
#: the resonance moves 29 % across them — so the anchor was always a TREND and
#: only one row of it was being used. On a handset the chassis IS the radiator;
#: this is that statement, gated.
#:
#: ⚠⚠ WHY *THESE* ROWS, and why NOT the obvious cheap one. The 80 mm and 100 mm
#: rows differ by 6 MHz. This gate's own measured mesh spread across
#: MeshResolution 20..90 is 1.8849-1.9149 GHz — about 30 MHz. A check built on
#: that 6 MHz pair would be pinning a number FIVE TIMES SMALLER than its own
#: numerical noise, and it would look like the cheapest possible first step.
#: The 20 mm row moves 548 MHz, roughly 18x the spread, which is why the ladder
#: is anchored there.
GROUND_LADDER_MM = (20, 40, 100)

#: Per-ground agreement with the MEASURED resonance. Same 3 % as the anchor
#: itself, deliberately: these are the same antenna and the same solver, so a
#: looser band here would be special pleading. Measured 2026-08-27 the four
#: rungs land +0.75 / +1.84 / +0.22 / -0.65 %, i.e. worst case 1.84 %.
LADDER_TOL = 0.03

#: How closely our SHIFT (relative to our own 80 mm solve) must track the
#: published measured shift, in percentage POINTS. Differential on purpose —
#: much of the mesh bias is common to both solves and cancels. Measured
#: deltas: +0.68 / +1.70 / -0.87 pp.
SHIFT_TOL_PP = 4.0

#: The 20 mm shrink must clear this. It is far above the ~1.6 % mesh spread the
#: gate would otherwise be measuring, and far below the +29.6 % actually seen —
#: so it cannot be satisfied by noise, and it is not fitted to the result.
SHIFT_FLOOR_PCT = 15.0


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
    check("ANCHOR records the short at the plate edge (worth 7.6 %, and not "
          "in the closed form)", a["short_at_edge"] is True,
          "short_at_edge = {0!r}".format(a["short_at_edge"]))
    if FAILURES:
        return _verdict()               # don't spend the solve on a known red

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
    # ⚠ An error near +7.6 % is the signature of the shorting plate having
    # moved off the plate edge — the closed form cannot see that; this can.
    check("resonance within +/-{0:.0%} of the PUBLISHED CHAMBER MEASUREMENT "
          "{1:.4f} GHz".format(MEASURED_TOL, MEASURED_HZ / 1e9),
          lo <= f_min <= hi, "{0:.4f} GHz ({1:+.2f} %)".format(
              f_min / 1e9, (f_min / MEASURED_HZ - 1.0) * 100.0))

    # --- and still inside the closed form's own stated accuracy -------------
    check("full-wave within the closed form's own stated +/-{0:.0%} of "
          "{1:.4f} GHz".format(pifa_engine.PIFA_ACCURACY, f_form / 1e9),
          abs(f_min / f_form - 1.0) <= pifa_engine.PIFA_ACCURACY,
          "{0:+.2f} %".format((f_min / f_form - 1.0) * 100.0))

    # --- a fed antenna, not a shorted one -----------------------------------
    check("feed-point R is a 50 ohm-class match (25-60 ohm)",
          25.0 <= zin.real <= 60.0, "{0:.2f} ohm".format(zin.real))
    check("feed-point |X| <= 20 ohm (resonant at its own best match)",
          abs(zin.imag) <= 20.0, "{0:+.2f}j ohm".format(zin.imag))
    check("S11 dips below -10 dB", s11_min < -10.0, "{0:.2f} dB".format(s11_min))

    db = result.s11_db()
    in_band = [x for x, d in zip(result.freq, db) if d <= -10.0]
    check("some frequency reaches -10 dB", bool(in_band),
          "{0} samples".format(len(in_band)))
    if in_band:
        bw = max(in_band) - min(in_band)
        print("pifa: -10 dB bandwidth {0:.1f} MHz ({1:.2f} %)".format(
            bw / 1e6, bw / f_min * 100.0))

    ff = getattr(result, "farfield", None)
    check("openEMS produced a far field", ff is not None)
    if ff is not None:
        g_peak, th_peak, _ = ff.peak()
        print("pifa: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(
            g_peak, th_peak))
        check("peak gain within 0-5 dBi (a low-profile plate over a small "
              "ground is low-gain)", 0.0 <= g_peak <= 5.0,
              "{0:.2f} dBi".format(g_peak))

    # --- B-i rung 1: the GROUND-PLANE LADDER, against measured hardware ----
    # The closed form returns the SAME number for every rung below (it has no
    # ground-size term at all), so nothing analytic can do this check.
    ladder = pifa_engine.GROUND_LADDER_MEAS_HZ
    check("the ladder's 80 mm row IS this gate's MEASURED_HZ (the same "
          "published measurement)", ladder[80] == MEASURED_HZ,
          "{0} vs {1}".format(ladder[80], MEASURED_HZ))
    f_ref = f_min                       # our own 80 mm solve, measured above
    pub_ref = float(ladder[80])
    solved = {80: f_ref}

    for g_mm in GROUND_LADDER_MM:
        pub = float(ladder[g_mm])
        gdoc = FreeCAD.newDocument("pifa_gnd_%d" % g_mm)
        gana = pifa_tpl.makePIFA(gdoc, ground_m=g_mm / 1000.0)
        gsolver = [o for o in gana.Group
                   if getattr(o, "EMStudioType", "") ==
                   "EMStudio::SolverOpenEMS"][0]
        gres = openems.run(gana, gsolver)
        f_g, s11_g = gres.min_s11()
        solved[g_mm] = f_g
        FreeCAD.closeDocument(gdoc.Name)

        ours_pct = (f_g / f_ref - 1.0) * 100.0
        pub_pct = (pub / pub_ref - 1.0) * 100.0
        print("pifa ladder: {0:3d} mm ground -> {1:.1f} MHz vs MEASURED "
              "{2:.0f} MHz ({3:+.2f} %); shift vs 80 mm ours {4:+.2f} % "
              "published {5:+.2f} % (delta {6:+.2f} pp), S11 {7:.2f} dB"
              .format(g_mm, f_g / 1e6, pub / 1e6,
                      (f_g / pub - 1.0) * 100.0, ours_pct, pub_pct,
                      ours_pct - pub_pct, s11_g))

        check("{0} mm ground within +/-{1:.0%} of the PUBLISHED CHAMBER "
              "MEASUREMENT {2:.0f} MHz".format(g_mm, LADDER_TOL, pub / 1e6),
              abs(f_g / pub - 1.0) <= LADDER_TOL,
              "{0:.1f} MHz ({1:+.2f} %)".format(f_g / 1e6,
                                               (f_g / pub - 1.0) * 100.0))
        # A miss here means the ground-plane TREND has drifted even if the
        # individual frequencies still land.
        check("{0} mm ground: our shift vs our own 80 mm solve tracks the "
              "published shift to {1:g} pp".format(g_mm, SHIFT_TOL_PP),
              abs(ours_pct - pub_pct) <= SHIFT_TOL_PP,
              "ours {0:+.2f} %, published {1:+.2f} %".format(ours_pct, pub_pct))

        # ⚠ NOTHING about S11 depth or bandwidth is asserted across the ladder,
        # and that is deliberate, not an omission. Huynh RE-MATCHES the probe
        # at every ground size (px 1.7 mm at L = 20 rising to 3.5 mm at
        # L = 140); makePIFA holds the feed fixed. Measured here: the 20 mm
        # rung reaches only -9.56 dB. Comparing match depth across this ladder
        # would be comparing two different experiments.

    # The headline: shrinking the ground to 0.156 lambda is a HUGE effect, and
    # the point of gating it is that it dwarfs the numerical noise. If this
    # ever passes on a few MHz, the ladder has stopped measuring the chassis.
    shrink = (solved[20] / f_ref - 1.0) * 100.0
    # The floor sits ~10x above this gate's own mesh spread; a smaller shift
    # means the ground plane is not being modelled as part of the antenna.
    check("shrinking the ground 80 -> 20 mm moves the resonance at least "
          "{0:.0f} %".format(SHIFT_FLOOR_PCT), shrink >= SHIFT_FLOOR_PCT,
          "{0:+.2f} %".format(shrink))

    # ⚠⚠ THE TRAP, PINNED. The measured trend is NOT monotonic: resonance
    # falls as the ground GROWS only until the minimum at L = 100 mm, then
    # rises again (1886 -> 1899 -> 1942 MHz at 100/120/140). A "bigger ground,
    # lower resonance" rule is false in general, and the honest form of the
    # check is that the minimum has NOT been passed at 80 mm.
    check("our 100 mm solve is below our 80 mm one (the measured minimum "
          "sits at 100 mm)", solved[100] < solved[80],
          "{0:.1f} vs {1:.1f} MHz".format(solved[100] / 1e6, solved[80] / 1e6))
    check("the 40 > 80 > 100 mm ordering holds",
          solved[40] > solved[80] > solved[100], "{0}".format(
              {k: round(v / 1e6, 1) for k, v in sorted(solved.items())}))
    if not FAILURES:
        print("pifa ladder: 4 measured rungs reproduced, and the minimum at "
              "100 mm is on the correct side of 80 mm")

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
        raise SystemExit("pifa validation failed")
    sys.exit(0)
