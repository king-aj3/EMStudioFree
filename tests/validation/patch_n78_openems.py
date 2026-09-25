# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: SYNTHESIZED 5G NR n78 (sub-6) patch via openEMS.

The same contract as ``patch_auto_openems.py`` — TL synthesis predicts the
geometry, the full-wave solve confirms the resonance — moved up to **3.5 GHz**,
the centre of **3GPP band n78 (3300-3800 MHz)**, on the same RO4003-class
substrate (er 3.38, h 1.524 mm) the 2.4 GHz patch uses. Holding the board fixed
and changing only the frequency is the point: it isolates the one variable and
makes the two gates directly comparable.

WHY A SEPARATE GATE RATHER THAN A PARAMETER ON THE 2.4 GHz ONE
--------------------------------------------------------------
Because the claim being made is different. ``patch_auto_openems`` proves the
synthesis-to-full-wave loop closes *somewhere*. This one proves it closes **in
the band people actually asked about**, and it adds the check that only makes
sense here: that the TL model's own uncertainty window still lands inside n78.

THE CHECK THAT IS SPECIFIC TO THIS BAND
---------------------------------------
The TL engine states its resonance accuracy as +/-5 % (``patch_tl.TL_ACCURACY``).
At a 3.5 GHz design that window is **3.325-3.675 GHz**, and n78 runs
**3.300-3.800 GHz** — so the synthesis is in-band even at BOTH edges of its own
stated error. That is a real, falsifiable statement about the tool: it says the
analytic designer can be trusted to put an n78 patch in n78 without a solver in
the loop. It is asserted here rather than merely written in the tutorial,
because a number in prose is a number that goes stale.

WHAT THIS GATE DOES **NOT** PROVE — say this whenever the gate is quoted
------------------------------------------------------------------------
There is no published *measured* n78 patch behind this number. ``patch_openems``
reproduces the openEMS project's own tutorial geometry (an external, freely
re-runnable reference); ``horn_openems`` compares against a vendor's published
gain curve. This gate has neither: it checks our solver against **our own
synthesis**, which is a consistency check between two independent models — the
TL/cavity formulation and full-wave FDTD — not a validation against reality.
That is weaker than the other two and the tutorial says so in place. The
published n78 designs in the literature are slotted, L-shaped or stacked
patches whose geometry this template cannot build, so anchoring to one would
have meant comparing different antennas.

MEASURED, AND THE ONE RESULT WORTH READING TWICE
------------------------------------------------
On the reference box the synthesized n78 patch matches to **-10.71 dB at
3.3950 GHz**. The SAME synthesis at 2.4 GHz (``patch_auto_openems``) matches to
**-10.71 dB at 2.3328 GHz** — the same depth to two decimals, and the same
-3 % resonance offset. That is not a coincidence and it is not a solver fault:
the two-slot edge resistance the feed offset is derived from barely moves
between the two designs (282.25 ohm at 2.4 GHz, 280.79 ohm at 3.5 GHz, 0.5 %
apart), so the synthesizer commits the SAME proportional feed-placement error
at both frequencies.

⛳ The control that settles it: ``patch_openems``, which solves the openEMS
project's own HAND-DIMENSIONED tutorial geometry, reaches **-29.95 dB** on this
same box in the same 9 s. So the chain is healthy and a well-placed feed really
does match to -30 dB — the ~19 dB shortfall is the price of the analytic feed
estimate, which ``patch_tl`` warns about in its own ``warnings`` list ("the
two-slot edge R is only order-of-magnitude accurate — seed for openEMS /
measurement, not fabrication-ready").

⚠ **Match depth is therefore NOT gated tightly here, and must not be.** The
``< -10 dB`` threshold is inherited unchanged from ``patch_auto_openems`` so
the two synthesis gates stay directly comparable; note it passes on 0.71 dB of
margin, in BOTH gates, and has done since the sibling shipped. Tightening it
would gate the feed-offset estimate's systematic error; loosening it would stop
it meaning anything. Improving that estimate is an engine change, out of this
gate's scope, and it would move both gates together.

⚠ The -10 dB bandwidth is REPORTED, not gated tight. A 1.524 mm board is
~0.018 lambda at 3.5 GHz, so a single patch on it is inherently narrowband and
cannot cover all 500 MHz of n78. The gate asserts only that the bandwidth is
patch-class (0.2-8 %); the honest consequence — one patch is a *channel* in
n78, not the *band* — belongs in the tutorial, and the gate prints the covered
fraction so the tutorial's figure can be re-derived rather than believed.

Expensive (full FDTD, ~minutes) — NOT in the smoke suite. Needs the openEMS venv.
Run:  freecadcmd tests/validation/patch_n78_openems.py
Pass: exit 0 and 'PATCH-N78 GATE PASSED'.
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
        print("PATCH-N78 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("PATCH-N78 GATE PASSED")
    return 0

#: 3GPP TS 38.104 band n78, in Hz. Named constants because the whole point of
#: this gate is the relationship between the TL error window and these two
#: edges — a bare 3.3e9 in an assert would hide what is being compared.
N78_LO_HZ = 3.300e9
N78_HI_HZ = 3.800e9

#: Design centre. Not the arithmetic centre of n78 (3.55 GHz) — 3.5 GHz is the
#: figure the band is universally referred to by, and the one the request that
#: put this on the roadmap actually used.
F0_HZ = 3.5e9

#: The same RO4003-class board as the 2.4 GHz patch, deliberately unchanged.
ER = 3.38
H_MM = 1.524


def main():
    # A live FDTD run needs the openEMS PYTHON modules, not just the binary.
    # Absence of an optional backend is a SKIP, and skipping is the BATTERY's
    # job (run_battery.SOLVER_REQS declares "openems_python" for this gate);
    # running this file BY HAND must fail loudly, because you asked for it
    # specifically. NO self-skip-and-pass: freecadcmd drops print(), so a gate
    # that returned 0 from its own skip branch would report a success it never
    # earned and the exit code would be the only thing a caller ever saw.
    from emstudio.setup.solvers import find_openems_python

    if find_openems_python() is None:
        raise SystemExit(
            "openEMS is required for this gate and was not found -- set "
            "EMSTUDIO_OPENEMS_PYTHON, or install openEMS with its venv beside "
            "the binary. (The battery skips this gate automatically; a direct "
            "run does not.)")
    import FreeCAD

    from emstudio.antenna import patch_tl
    from emstudio.solvers import openems
    from emstudio.templates import patch

    des = patch_tl.design_patch(F0_HZ, ER, H_MM / 1000.0)
    print("patch-n78: synthesized W {0:.2f} mm, L {1:.2f} mm, feed offset "
          "{2:.2f} mm, predicted gain {3:.1f} dBi".format(
              des["width_m"] * 1e3, des["length_m"] * 1e3,
              des["feed_offset_m"] * 1e3, des["gain_dbi"]))

    # --- the band check, before any solver runs -----------------------------
    # This half needs no FDTD at all: it is a statement about the SYNTHESIS,
    # and it is the reason an n78 user can trust the Element Designer without
    # installing openEMS. Asserted first so that a synthesis regression is
    # reported in milliseconds instead of after a multi-minute solve.
    lo = F0_HZ * (1.0 - patch_tl.TL_ACCURACY)
    hi = F0_HZ * (1.0 + patch_tl.TL_ACCURACY)
    print("patch-n78: TL +/-{0:.0%} window {1:.4f}-{2:.4f} GHz vs n78 "
          "{3:.3f}-{4:.3f} GHz".format(patch_tl.TL_ACCURACY, lo / 1e9,
                                       hi / 1e9, N78_LO_HZ / 1e9,
                                       N78_HI_HZ / 1e9))
    # The interval of DESIGN frequencies for which the whole +/-5 % window
    # stays inside n78. Printed because it is the honest limit of the claim
    # tutorial 34 makes: "design analytically and you land in band" is true
    # near the middle of n78 and FALSE near its edges, and a reader deserves
    # the actual edge rather than the reassuring half of the sentence.
    safe_lo = N78_LO_HZ / (1.0 - patch_tl.TL_ACCURACY)
    safe_hi = N78_HI_HZ / (1.0 + patch_tl.TL_ACCURACY)
    print("patch-n78: design frequencies whose whole window stays in n78: "
          "{0:.4f}-{1:.4f} GHz (this design {2:.3f} GHz)".format(
              safe_lo / 1e9, safe_hi / 1e9, F0_HZ / 1e9))
    # A FAIL here means the synthesis can land out of band at its own stated
    # error, and the tutorial's central claim is false.
    check("the TL model's own +/-{0:.0%} window fits inside n78 "
          "({1:.3f}-{2:.3f} GHz)".format(patch_tl.TL_ACCURACY,
                                         N78_LO_HZ / 1e9, N78_HI_HZ / 1e9),
          N78_LO_HZ <= lo and hi <= N78_HI_HZ,
          "window {0:.4f}-{1:.4f} GHz".format(lo / 1e9, hi / 1e9))
    if FAILURES:
        return _verdict()               # don't spend the solve on a known red

    doc = FreeCAD.newDocument("patch_n78_gate")
    ana = patch.makePatchDesign(doc, f0_hz=F0_HZ, er=ER, h_mm=H_MM)
    solver = [o for o in ana.Group
              if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]

    result = openems.run(ana, solver)
    f_min, s11_min = result.min_s11()
    print("patch-n78: FDTD best match {0:.2f} dB at {1:.4f} GHz (design "
          "{2:.3f} GHz)".format(s11_min, f_min / 1e9, F0_HZ / 1e9))
    print("patch-n78: run took {0:.1f} s in {1}".format(
        result.meta.get("duration_s", -1), result.meta.get("workdir", "?")))

    # --- gates: resonance within the TL model's stated +/-5 % of f0 ---------
    check("resonance within the TL model's +/-{0:.0%} of the {1:.3f} GHz "
          "design ({2:.4f}-{3:.4f} GHz)".format(
              patch_tl.TL_ACCURACY, F0_HZ / 1e9, lo / 1e9, hi / 1e9),
          lo <= f_min <= hi, "{0:.4f} GHz".format(f_min / 1e9))
    check("S11 dips below -10 dB", s11_min < -10.0, "{0:.2f} dB".format(s11_min))

    # The solved resonance must ALSO be in n78. This does not follow from the
    # assert above by arithmetic alone once someone edits F0_HZ or the window,
    # and it is the claim a user actually cares about, so it is checked
    # directly rather than inferred.
    check("the solved resonance is inside n78", N78_LO_HZ <= f_min <= N78_HI_HZ,
          "{0:.4f} GHz".format(f_min / 1e9))

    # --- -10 dB bandwidth: reported, loosely bounded ------------------------
    # Deliberately wide. The figure that matters is printed, not gated: a tight
    # bandwidth window would be gating the mesh, and the honest conclusion (one
    # thin patch is a channel in n78, not the band) is a fact about microstrip,
    # not a tolerance this project can tighten by trying harder.
    db = result.s11_db()
    freqs = result.freq
    in_band = [f for f, d in zip(freqs, db) if d <= -10.0]
    check("some frequency reaches -10 dB", bool(in_band),
          "{0} samples".format(len(in_band)))
    if in_band:
        bw_hz = max(in_band) - min(in_band)
        frac = bw_hz / f_min
        print("patch-n78: -10 dB bandwidth {0:.1f} MHz ({1:.2%} fractional), "
              "{2:.4f}-{3:.4f} GHz — {4:.0%} of n78's 500 MHz".format(
                  bw_hz / 1e6, frac, min(in_band) / 1e9, max(in_band) / 1e9,
                  bw_hz / (N78_HI_HZ - N78_LO_HZ)))
        # ⛳ THIS is the gated form of the tutorial's central limitation: one
        # patch on this board is a CHANNEL in n78, not the band. Asserted
        # against n78's own 500 MHz width rather than a hand-picked figure, so
        # the day a wider element makes the claim false the gate goes red and
        # the tutorial must be rewritten — which is the correct outcome, not a
        # regression. Measured 21 MHz against 500 MHz: a 24x margin, so this
        # is robust to mesh and machine.
        check("-10 dB bandwidth is narrower than n78's 500 MHz (tutorial 34: "
              "one patch is a channel, not the band)",
              bw_hz < (N78_HI_HZ - N78_LO_HZ), "{0:.1f} MHz".format(bw_hz / 1e6))
        # ⚠ Absurdity guard only, and deliberately loose. The -10 dB bandwidth
        # of a MARGINALLY matched patch is set by how far past -10 dB the dip
        # goes, so a tight window here would be gating the match depth twice
        # and would fail on mesh noise. The 0.62 % measured on a dip that
        # reaches only -10.7 dB is real and expected; see the match-depth note
        # in the docstring.
        check("fractional bandwidth is patch-class (0.2-8 %)",
              0.002 <= frac <= 0.08, "{0:.2%}".format(frac))

    # --- far-field gates ----------------------------------------------------
    ff = getattr(result, "farfield", None)
    check("openEMS produced a far field", ff is not None)
    if ff is not None:
        g_peak, th_peak, _ = ff.peak()
        print("patch-n78: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(
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
        raise SystemExit("patch-n78 validation failed")
    sys.exit(0)
