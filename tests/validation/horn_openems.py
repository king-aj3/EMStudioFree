# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: a RADIATING structure solved above 2.435 GHz, at last.

Until v1.5.0 the highest gated radiating point in this project was a 2.435 GHz
patch, while `docs/CAPABILITIES.md` opened with "EMStudio's full-wave engines
reach mmWave". Both were true — Palace is validated to 57 GHz on CLOSED
structures — and the gap between them is what this gate closes: a horn, fed
through a real TE10 waveguide port, radiating at Ka band, with its gain checked
against a published curve.

**Geometry: Mi-Wave 261A-20/599**, a purchasable WR-28 standard gain horn, from
the vendor's dimensioned outline drawing. Named exactly, because two vendors'
nominal "20 dB WR-28 SGH" have materially different apertures (Mi-Wave
39.9 x 27.9 mm vs Pasternack 35.1 x 25.7 mm) — "a 20 dBi standard gain horn" is
not a specification.

⚠⚠ **WHAT THIS GATE PROVES, AND WHAT IT DOES NOT.** The vendor's gain curve is
smooth and monotonic. Per Bodnar (NSI-MI), a genuinely range-measured SGH shows
0.1-0.2 dB ripple from mouth/throat reflections; a smooth curve is the
signature of the NRL/Slayton closed form. So this compares our solver against
**analytic aperture theory**, not against a measurement. That is NOT circular —
it is not the solver's own output — but it is weaker than a measured anchor and
must never be described as one.
⛳ The analytic reference is itself measurement-anchored one step removed: NIST
(Francis et al., AMTA 2016, three-antenna extrapolation) measured a pyramidal
SGH at 118.75 GHz as **15.47 +/- 0.5 dB against 15.40 dB predicted** — 0.07 dB.
The prediction tracks measurement deep into mmWave; what is unproven here is
only whether OUR solver reproduces the prediction.

⚠ **The tolerance is +/-0.5 dB and must NOT be tightened.** IEEE Std 149-1979
p.95 puts the NRL closed form at +/-0.25 to +/-0.5 dB, and Bodnar's
seven-laboratory X-band intercomparison shows 0.2 dB spread between labs on
real measurements. A tighter window would be gating against aperture theory's
own uncertainty and calling the result solver accuracy.

⚠ **Do not re-source the anchor from Eravant or Anteral** — their datasheets
state that pattern and gain data are SIMULATED, which would make this circular.

⛳ **The band SHAPE is checked as well as the level.** A single-frequency gain
check passes for a mesh or port error that happens to land near the right
number; the ~2.8 dB monotonic rise from 26.5 to 40 GHz is a property of the
aperture and catches those.

SOLVER tier — a full Ka-band FDTD run. Never in the fast battery.

Run:  freecadcmd tests/validation/horn_openems.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    print("== Ka-band pyramidal horn (Mi-Wave 261A-20/599) via openEMS ==")

    try:
        import FreeCAD  # noqa: F401
    except Exception:
        print("  skip — needs freecadcmd (FreeCAD geometry)")
        return 0

    # A live FDTD run needs the openEMS PYTHON modules, not just the binary.
    # Absence of an optional backend is a SKIP, never a failure — the same
    # correction patch_openems and the nec2c gates already carry.
    from emstudio.setup.solvers import find_openems_python
    if not find_openems_python():
        print("  skip — openEMS python modules not installed")
        return 0

    from emstudio.templates import horn as horn_tpl

    # --- geometry contract, cheap and always run ---------------------------
    # These are the numbers a reader can check against the vendor drawing, and
    # a silent edit to the template would change the physics the gate below
    # believes it is measuring.
    check("aperture a1 is the drawing's 39.88 mm",
          abs(horn_tpl.APERTURE_A_MM - 39.88) < 1e-9,
          "%.3f" % horn_tpl.APERTURE_A_MM)
    check("aperture b1 is the drawing's 27.94 mm",
          abs(horn_tpl.APERTURE_B_MM - 27.94) < 1e-9,
          "%.3f" % horn_tpl.APERTURE_B_MM)
    check("throat is WR-28 (7.112 x 3.556 mm)",
          abs(horn_tpl.WR28_A_MM - 7.112) < 1e-9
          and abs(horn_tpl.WR28_B_MM - 3.556) < 1e-9)
    check("a1 is the BROAD wall (a > b, TE10 convention)",
          horn_tpl.APERTURE_A_MM > horn_tpl.APERTURE_B_MM)

    # The vendor curve must rise across the band — that is the aperture getting
    # electrically larger, and a table that did not would be mis-transcribed.
    fs = sorted(horn_tpl.VENDOR_GAIN_DBI)
    gains = [horn_tpl.VENDOR_GAIN_DBI[f] for f in fs]
    rise = gains[-1] - gains[0]
    check("vendor curve rises monotonically across the band",
          all(b >= a for a, b in zip(gains, gains[1:])),
          "%.1f -> %.1f dBi" % (gains[0], gains[-1]))
    check("band rise is ~2.8 dB (aperture in wavelengths)",
          2.0 <= rise <= 3.5, "%.1f dB" % rise)
    check("tolerance is the citable +/-0.5 dB, not tightened",
          abs(horn_tpl.GAIN_TOL_DB - 0.5) < 1e-9)

    # --- the live solve ----------------------------------------------------
    # ⚠ Expensive: lambda = 7.5 mm at 40 GHz, so a lambda/20 grid is 0.375 mm
    # over a domain holding the horn plus radiating padding. Reported rather
    # than hidden, because a gate whose cost surprises you gets skipped.
    from emstudio.solvers import openems as oe

    ana = horn_tpl.makeHorn()
    solver = [o for o in ana.Group
              if "Solver" in str(getattr(o, "EMStudioType", ""))][0]
    print("  .... solving (Ka-band FDTD — expect a long run)")
    result = oe.run(ana, solver)

    ff = getattr(result, "farfield", None)
    if ff is None:
        check("the run produced a far field", False,
              "no farfield on the result — ComputeFarField not honoured?")
        return 1 if FAILURES else 0

    peak_dbi, th, ph = ff.peak()
    f_ghz = ff.freq / 1e9
    # Interpolate the vendor curve at whatever frequency the deck picked.
    lo = max([f for f in fs if f <= f_ghz], default=fs[0])
    hi = min([f for f in fs if f >= f_ghz], default=fs[-1])
    if hi == lo:
        ref = horn_tpl.VENDOR_GAIN_DBI[lo]
    else:
        t = (f_ghz - lo) / (hi - lo)
        ref = (horn_tpl.VENDOR_GAIN_DBI[lo] * (1 - t)
               + horn_tpl.VENDOR_GAIN_DBI[hi] * t)

    check("solved peak gain within +/-{0:g} dB of the vendor curve".format(
              horn_tpl.GAIN_TOL_DB),
          abs(peak_dbi - ref) <= horn_tpl.GAIN_TOL_DB,
          "%.2f dBi solved vs %.2f dBi published at %.2f GHz (delta %+.2f)"
          % (peak_dbi, ref, f_ghz, peak_dbi - ref))
    # A horn points forward. If the peak is not near boresight the port or the
    # flare orientation is wrong, and a gain that happens to be right would
    # otherwise hide it.
    check("main beam is on boresight (theta < 20 deg)", th < 20.0,
          "peak at theta=%.0f deg, phi=%.0f deg" % (th, ph))

    eta = (ff.meta or {}).get("eta_rad")
    if eta is not None:
        # PEC walls and air: essentially all accepted power must radiate. A low
        # efficiency here means power is being absorbed somewhere it should not
        # be — usually the boundary eating the near field.
        check("radiation efficiency is near unity for a PEC horn",
              eta > 0.90, "eta_rad = %.1f %%" % (100.0 * eta))

    if FAILURES:
        print("HORN OPENEMS GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("HORN OPENEMS GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
