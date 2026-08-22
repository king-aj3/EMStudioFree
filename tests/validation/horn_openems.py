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

⛳ **WHERE THE SOLVER ACTUALLY LANDS, MEASURED 2026-08-22 on the shipped deck,
directivity at 30.000 GHz against the vendor's 19.7 dBi.** Read this before
reacting to a red run: the number moves with the mesh by more than the
tolerance, and NOT monotonically.

| MeshResolution | cell | cells | D | vs vendor |
|---|---|---|---|---|
| 20 | 0.3747 mm | 6.08 M | 18.13 dBi | −1.57 |
| **30 (the template)** | 0.2498 mm | 19.97 M | **19.29 dBi** | **−0.41** |
| 40 | 0.1874 mm | 47.05 M | 18.95 dBi | −0.75 |

⚠⚠ **lambda/30 passes and lambda/40 does not, and that is a fact about the
solver, not a licence to pick the mesh that passes.** Run-to-run directivity on
this backend is reproducible to **0.0016 dB** (ten identical decks), so the
0.34 dB between the two is REAL — it is the staircasing of a 13.7-degree slanted
PEC flare on a Cartesian grid, whose error oscillates rather than converging.
The honest reading of this gate is "openEMS reproduces aperture theory for this
horn to within about half a decibel, with roughly 0.3 dB of mesh uncertainty on
top", and the +/-0.5 dB window — which is aperture theory's OWN uncertainty —
is only just wide enough to contain that. ⛳ **RESOLVED (AJ, 2026-08-22): gate the SPREAD instead.** The window stays at
the citable +/-0.5 dB, and the gate now solves a SECOND time at lambda/40 and
asserts the two meshes agree to within 0.50 dB. That turns "green at a mesh that
happens to pass" into a stated, checked bound on the discretisation error — and
it fails if a future change makes the solver MORE mesh-sensitive, which widening
the window would have hidden.

⛳ **Efficiency is NOT reproducible on this backend** — 3.33 % spread over those
same ten runs, which is 0.15 dB of GAIN, because openEMS evaluates its energy
stop criterion on a wall-clock cadence and the far-field DFT is truncated
differently each time. Directivity is a ratio and cancels it. Never tighten a
check on ``eta_rad`` here.

SOLVER tier, and now the most expensive gate in the project: **TWO** Ka-band
FDTD runs, lambda/30 (19.97 M cells, ~9 min) plus lambda/40 (47.05 M cells,
~14 min) — budget ~25 minutes. Reported rather than hidden, because a gate whose
cost surprises you gets skipped.

Run:  freecadcmd tests/validation/horn_openems.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: The SECOND mesh the gate solves, to bound the discretisation error rather
#: than hope it is small. lambda/40 at the band top: 47.05 M cells.
FINE_MESH_RESOLUTION = 40

#: How far the two meshes may disagree. MEASURED 2026-08-22: 19.29 dBi at
#: lambda/30 against 18.95 at lambda/40 — **0.34 dB**. 0.50 leaves ~45 % headroom
#: over that, which is enough to absorb an honest geometry change and tight
#: enough to catch a regression that doubles the solver's mesh sensitivity.
#: ⚠ Do NOT relax this to make a red run green — a wider spread means the
#: lambda/30 number is less trustworthy, not more.
MESH_SPREAD_MAX_DB = 0.50

#: The fine mesh is NOT held to the +/-0.5 dB anchor tolerance, because it does
#: not meet it (-0.75 dB, measured) and pretending otherwise is the whole thing
#: this section exists to avoid. It IS held to a wider window, so a fine-mesh
#: run that collapses is still caught.
FINE_TOL_DB = 1.0


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
    # ⚠⚠ NaN IS THE DECK SAYING "I DECLINED", NOT A FAILURE — and a naive
    # ``eta > 0.90`` reads it as one, because every comparison against NaN is
    # False. When the power budget does not close the deck deliberately reports
    # DIRECTIVITY and prints why (writer.py); the gate's job then is to confirm
    # that the number it is holding is that conservative fallback, not to fail
    # an arithmetic test the deck never claimed to pass.
    # ⛳ It does not close on this model, and the reason is understood and
    # MEASURED. openEMS's waveguide port is a soft source on a plane, so it
    # launches the mode BOTH ways; the backward half leaves the guide's open
    # end at z = -15 and part of it re-enters through the NF2FF box's side
    # faces, which begin at that same plane. P_rad therefore exceeds the
    # forward power the port delivers. Measured at lambda/20: P_rad/P_acc =
    # 1.22 — down from **16.42** before the port's reference impedance and span
    # were fixed, and the residual is this geometric artefact, not the port.
    # ⚠ For a PEC horn D and G are equal anyway, so the reported number is the
    # right one either way; what would NOT be acceptable is applying a
    # 22 %-too-large efficiency and calling the result gain.
    if eta is not None and eta == eta:              # not NaN
        # PEC walls and air: essentially all accepted power must radiate. A low
        # efficiency here means power is being absorbed somewhere it should not
        # be — usually the boundary eating the near field.
        check("radiation efficiency is near unity for a PEC horn",
              eta > 0.90, "eta_rad = %.1f %%" % (100.0 * eta))
    else:
        p_acc = (ff.meta or {}).get("p_acc_w")
        p_rad = (ff.meta or {}).get("p_rad_w")
        ratio = (p_rad / p_acc) if (p_acc and p_rad) else float("nan")
        check("the power budget is declared open, and by a KNOWN margin",
              1.0 < ratio < 1.5,
              "P_rad/P_acc = %.3f (was 16.42 before the port fixes); the "
              "reported figure is DIRECTIVITY" % ratio)

    # --- 2. THE MESH SENSITIVITY IS GATED, NOT HIDDEN --------------------
    # ⚠⚠ WHY THIS SECOND SOLVE EXISTS, AND IT IS THE POINT OF THE WHOLE GATE.
    # The check above passes at the template's lambda/30 and would FAIL at
    # lambda/40 (18.95 dBi, -0.75). Leaving it there would mean the gate was
    # green at a mesh chosen partly because it is green — a tolerance the
    # solver only meets on one grid, presented as if it met it generally.
    # ⛳ So the SPREAD is the thing gated. Run-to-run directivity on this
    # backend is reproducible to 0.0016 dB (ten byte-identical decks), so the
    # difference between two meshes is deterministic and a real property of the
    # discretisation — the staircasing of a 13.7-degree slanted PEC flare on a
    # Cartesian grid, whose error oscillates rather than converging. Gating it
    # turns "we got lucky" into "we know how big the luck is".
    # ⚠ AJ's call, 2026-08-22, in preference to widening the +/-0.5 dB window:
    # that window is aperture theory's OWN uncertainty (IEEE Std 149-1979,
    # Bodnar) and must not be made to absorb ours.
    print("  .... second solve at MeshResolution %d for the mesh-sensitivity "
          "check (this is the expensive half)" % FINE_MESH_RESOLUTION)
    fine = horn_tpl.makeHorn(doc=FreeCAD.newDocument("horn_fine"))
    fine.MeshResolution = FINE_MESH_RESOLUTION
    fine_solver = [o for o in fine.Group
                   if "Solver" in str(getattr(o, "EMStudioType", ""))][0]
    fine_ff = getattr(oe.run(fine, fine_solver), "farfield", None)
    if fine_ff is None:
        check("the fine-mesh run produced a far field", False)
    else:
        fine_peak, fine_th, _ = fine_ff.peak()
        spread = abs(fine_peak - peak_dbi)
        check("the two meshes agree to within {0:g} dB".format(MESH_SPREAD_MAX_DB),
              spread <= MESH_SPREAD_MAX_DB,
              "%.2f dBi at lambda/%d vs %.2f at lambda/%d -> %.2f dB "
              "(measured 0.34 dB on 2026-08-22)"
              % (fine_peak, FINE_MESH_RESOLUTION, peak_dbi,
                 int(ana.MeshResolution), spread))
        # ...and the fine mesh must still be in the right postcode. The spread
        # check alone would pass on two meshes that agree with each other and
        # not with physics.
        check("the fine mesh is still within {0:g} dB of the vendor curve"
              .format(FINE_TOL_DB),
              abs(fine_peak - ref) <= FINE_TOL_DB,
              "%.2f dBi vs %.2f published" % (fine_peak, ref))
        check("the fine mesh also points forward", fine_th < 20.0,
              "peak at theta=%.0f deg" % fine_th)

    if FAILURES:
        print("HORN OPENEMS GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("HORN OPENEMS GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
