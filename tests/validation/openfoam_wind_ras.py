# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — turbulent wind loading: kOmegaSST on the square cylinder.

SOLVER tier, and the most expensive wind gate: a full URANS shedding solve at
**Re 21,400** through the product's own writer + runner (`run_wind`, serial).
This is the FORCED-convection turbulence anchor that `docs/
WIND_TURBULENCE_ANCHOR.md` de-risked: the sharp-edged square section, where
separation is corner-fixed and the measured Cd curve is FLAT from 1e4 to
1.5e5 (Lyn 2.1 at 21.4k; Norberg ~2.1 at 38k; Fage & Johansen ~2.05 at 150k)
— which is exactly what lets one anchor Reynolds number carry a validation
window.

THE ANCHOR (all read from the papers' own tables — see the de-risk doc):

* Lyn, Einav, Rodi & Park (1995), JFM 304 — LDV experiment, Re 21,400:
  mean Cd **2.1**, St **0.132**.
* Trias, Gorobets & Oliva (2015) — DNS at Re 22,000: Cd 2.18, St 0.132,
  Cl,rms 1.71 (secondary-confirmed digits; not load-bearing here).
* Tian, Ong, Yang & Myrhaug (2013), Ocean Eng. 58 — the same case in
  OpenFOAM 2-D URANS k-omega SST: Cd **2.060**, St **0.138**, Cl,rms 1.492.

TOLERANCES ARE THE PUBLISHED SPREAD, not this box's numbers (the project
rule, same as `openfoam_wind_transient`):

* **St in [0.125, 0.150]** — ASYMMETRIC BY DESIGN: 2-D URANS is
  systematically HIGH on this geometry (+4 % SST to +11 % k-epsilon vs the
  measured 0.130-0.133), so the window runs from just under the measurement
  to just over Bosch & Rodi's k-epsilon 0.146. Reusing the laminar gate's
  symmetric 5 % window would sit half-off the method bias.
* **Cd in [1.95, 2.25]** — covers the experiments (2.05-2.2), the DNS (2.18)
  and every published 2-D URANS (2.05-2.11) with mesh margin; excludes the
  steady/symmetric failure mode (~1.7 and below).
* **Cl amplitude in [1.1, 3.0]** — a shedding-exists floor, deliberately
  loose: published Cl,rms scatters 0.98-1.71 across URANS/LES/DNS
  (near-sinusoid amplitude ~ rms*sqrt(2) ~ 1.4-2.4). Below ~1.1 means the
  wake is not really shedding; a symmetric wake gives ~0.

THE CASE is the de-risked configuration, and the DOMAIN IS PART OF THE
BENCHMARK: **radius_ratio 20** — lateral +/-10 d gives Tian's own 5 %
blockage, because the published Cd values sit at ~5-7 % tunnel confinement
(Lyn's rig ~7 % uncorrected) and a lower-blockage domain LEGITIMATELY reads
lower (measured: radius_ratio 40 = 2.5 % blockage completed with Cd 1.847 —
St 0.1330 and Cl amplitude 2.26 right on the published values, drag a few
percent under the band exactly as the de-risk doc predicted; widening the
band to keep that domain would absorb OUR domain choice into the
literature's window — the horn lesson). ⚠ radius_ratio 10 — six recorded
2026-08-23 attempts plus two full re-runs — puts the outlet at 4.5 d, and
the vortex street reaches it at ~1.3x freestream carrying k two orders
above ambient; the freestream patch's inletOutlet switching then blows up
after ~17 healthy cycles (SIGFPE in the pressure solve). At 10 d and beyond
the street decays before the boundary and the solve completes. n_r 160 /
grading 4 puts the first wall cell at y+ ~30 — the classic wall-function
target, and the configuration class the published URANS studies used; the
resolved-wall alternative diverges at the sharp corners (recorded in the
writer). cycles=20 is Tian's own statistics floor (10 vs 20 cycles moved
the answers < 0.01 %).

MUTATIONS (the gate must be able to fail — proven, not assumed):

* laminar (`turbulence=""`) at the EXACT gate configuration (measured
  2026-08-24, 4-rank run of the product-written case): **SIGFPE at step
  ~19,158 (~10 cycles), forces overflowed to ~1e196** — at Re 21,400 a
  laminar 2-D solve cannot hold this flow at all, so the mutation fails at
  "the solve ran". (At radius_ratio 10 it died even earlier, 6.8 cycles,
  continuity errors ~1e91.)
* steady + kOmegaSST: the WRITER refuses it (`ValueError` in
  `WindCase.__post_init__`) — checked live in this gate, because Franke &
  Rodi (1993) showed steady k-epsilon converges to a steady non-shedding
  ARTIFACT on this geometry.
* wallDist dropped / model renamed: the gate reads the WRITTEN case back
  (turbulenceProperties names kOmegaSST; fvSchemes carries the meshWave
  wallDist the v2512 kOmegaSST needs) so a silently-laminar or
  silently-broken case cannot pass on good numbers alone.

Measured here 2026-08-24 (v2512, the exact case above, 4-rank dev run of the
product-written case, all 38,462 steps): **Cd 2.1304 | St 0.1356 |
Cl amplitude 2.4939 | 9.0 cycles** — Cd inside the experimental cluster
(Lyn 2.1 / Tian 2.060 / DNS 2.18), St carrying the expected small URANS
high bias over the measured 0.132. The blockage sensitivity is real and
measured: the identical solve at radius_ratio 40 (2.5 % blockage) read
Cd 1.8472 with St 0.1330 — flow right, confinement different. First green
run of THIS gate (serial product path, 2026-08-24): **Cd 2.1358 |
St 0.1356 | Cl amplitude 2.522 | 9.0 cycles** — within 0.3 % of the 4-rank
dev run, so decomposition and run-to-run scatter sit far inside the bands.
"""
import os
import sys
import tempfile
import shutil

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(label, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", label,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


def main():
    from emstudio.solvers.openfoam import WindCase, run_wind
    from emstudio.solvers.openfoam.wind import RAS_SQUARE_RADIUS_RATIO

    print("EMStudio turbulent wind gate (LIVE kOmegaSST SOLVE, ~3 h serial)")

    # Steady + turbulence must be REFUSED by the writer, not solved badly:
    # steady k-epsilon on this geometry converges to a non-shedding artifact
    # (Franke & Rodi 1993), and a refusal is the only honest answer.
    try:
        WindCase(reynolds=21400.0, geometry="square", transient=False,
                 turbulence="kOmegaSST")
        check("steady+kOmegaSST is refused by the writer", False,
              "constructed without error")
    except ValueError:
        check("steady+kOmegaSST is refused by the writer", True)

    case = WindCase(reynolds=21400.0, geometry="square", transient=True,
                    turbulence="kOmegaSST", st_guess=0.13,
                    # the writer's own benchmark-domain constant, so this gate
                    # and method_is_valid cannot drift apart; the FAST pin in
                    # wind_transient holds the LITERAL 20 against both.
                    fixed_dt_star=0.004, grading=4.0,
                    radius_ratio=RAS_SQUARE_RADIUS_RATIO,
                    n_r=160, cycles=20.0)
    print("  Re %g | U %.5g m/s | dt* 0.004 -> dt %.3g s | end %.4g s "
          "(~%d steps, %d cells)"
          % (case.reynolds, case.u_inf, case.delta_t, case.end_time,
             round(case.end_time / case.delta_t), 4 * case.n_theta * case.n_r))

    tmp = tempfile.mkdtemp(prefix="windras_gate_")
    try:
        report, hist = run_wind(tmp, case, timeout=21600)
        if not report.get("ok"):
            check("the solve ran", False,
                  "{0}: {1}".format(report.get("failed_at"), report.get("error")))
            return 1
        check("the solve ran", True)

        # The WRITTEN case must prove RAS actually ran — good numbers from a
        # silently-laminar case would validate nothing.
        turb = open(os.path.join(tmp, "constant",
                                 "turbulenceProperties")).read()
        check("the written case names kOmegaSST",
              "kOmegaSST" in turb and "RAS" in turb)
        schemes = open(os.path.join(tmp, "system", "fvSchemes")).read()
        check("fvSchemes carries the wallDist method kOmegaSST needs",
              "wallDist" in schemes and "meshWave" in schemes)

        check("whole shedding cycles were measured",
              report["cycles_measured"] >= 8,
              "{0} cycles".format(report["cycles_measured"]))

        cl = report["cl_amplitude"]
        check("lift amplitude {0:.3f} in [1.1, 3.0] (published Cl,rms "
              "0.98-1.71; a symmetric wake gives ~0)".format(cl),
              1.1 <= cl <= 3.0)

        st = report["strouhal"]
        check("Strouhal {0:.4f} in [0.125, 0.150] (measured 0.132; 2-D URANS "
              "reads high by design of the window)".format(st),
              0.125 <= st <= 0.150)

        cd = report["cd"]
        check("mean Cd {0:.4f} in the published [1.95, 2.25]".format(cd),
              1.95 <= cd <= 2.25)
        check("Cd is above the steady/laminar under-read",
              cd > 1.8,
              "steady RANS converges to a non-shedding ~<=1.7 artifact here")

        check("the case carries no validity caveat at Re 21,400",
              not report.get("validity"), report.get("validity", "")[:60])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-WIND-RAS GATE PASSED")
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
        raise SystemExit("openfoam-wind-ras validation failed")
    sys.exit(0)
