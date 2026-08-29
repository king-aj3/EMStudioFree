# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: unsteady cross-flow — vortex shedding at a real Reynolds number.

Pass: exit 0 and 'WIND-TRANSIENT GATE PASSED'.

WHY THIS EXISTS. The steady wind case is anchored at Re 20 and Re 40, BELOW the
onset of vortex shedding (~47), because a steady solve cannot represent a
shedding wake at all — it produces a symmetric one and under-reads drag. That
left every Reynolds number worth calling "wind" out of reach.

This is the next rung: `pimpleFoam`, unsteady, laminar. It is anchored on the
2-D circular cylinder, which is one of the most thoroughly measured flows in
fluid mechanics, and on THREE independent quantities rather than one:

  * **Strouhal number** — the signature of shedding. Williamson's correlation
    (J. Fluid Mech. 1988; the standard fit for the laminar shedding regime),
        St = -3.3265/Re + 0.1816 + 1.6e-4 * Re
    gives St = 0.1643 at Re 100 and 0.1834 at Re 150.
  * **Mean drag** — published 2-D laminar values cluster at Cd ~1.32-1.37 at
    Re 100 (Braza 1.364, Liu 1.35, Park 1.33).
  * **Lift amplitude** — ~0.32-0.34 at Re 100.

⚠ St is the sharp one. Cd is forgiving of a coarse mesh and a short run;
the shedding FREQUENCY is not, and it is what proves the solve is resolving
the physics rather than merely running.

MEASURED ONCE, BY A LIVE SOLVE THAT IS NOT THIS GATE (v2512, O-grid 80x30,
40 diameters, 40 cycles, half discarded):

    Re 100   Cd 1.3411   St 0.1647   Cl amp 0.3275   15 cycles
    Re 150   see WIND_ANCHORS below

⚠ **NOTHING IS SOLVED IN THIS FILE, AND NO NUMBER HERE IS RE-MEASURED.**
Those are a RECORD of a past run. The live re-measurement is the SOLVER gate
`openfoam_wind_transient` (~9 min) and it runs **Re 100 ONLY** — so the Re 150
row is re-measured by no gate on any tier and must be read as a recorded
observation, not a continuously verified one.

⚠ Until 2026-08-29 the anchor block was worse than that: all eight of its
checks read literals declared in THIS file and judged them with a closed form
declared in THIS file, importing nothing from `emstudio`, so any sabotage of
the product left every one of them green. It now carries two real ties — the
fixture is pinned digit-for-digit to the anchor table the PRODUCT module
publishes, and every published-range verdict is passed on numbers the
product's own `force_history_from_log` RECOVERS from a replay of the record,
never on the literal itself.

⚠ **ABOVE Re ~190 THE REAL WAKE GOES THREE-DIMENSIONAL** (mode A/B). A 2-D
laminar solve above that is modelling an idealisation, not the flow, so
`TURBULENT_RE` refuses it. Real antenna loading is Re 1e5-1e6 and needs a
validated turbulence model — which IS now built for SQUARE sections
(kOmegaSST URANS vs the measured Lyn experiment, `openfoam_wind_ras`,
Re <= 1.5e5; circles stay refused; this docstring said "NOT built" until
2026-08-24, one release after it shipped). This gate pins the laminar rung
and the refusal above it.

FAST tier: the SOLVE is a SOLVER-tier gate (`openfoam_wind`); everything here
is the case setup, the guard rails and the history arithmetic, which is where
the errors that produce plausible wrong numbers live.
"""
import math
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: Re -> measured here, and the PUBLISHED ranges to judge it against.
#:
#: ⚠ The ranges are the literature's spread, NOT a window drawn around our own
#: numbers. A tolerance fitted to what we measured passes by construction and
#: catches nothing.
#:
#: ⚠ Lift amplitude is strongly Re-dependent (~0.33 at Re 100, ~0.52 at
#: Re 150) — one range across both would have to be so wide it asserts
#: nothing, which is why these are per-Re.
WIND_ANCHORS = {
    100.0: {"cd": 1.3411, "st": 0.1647, "clamp": 0.3275,
            "cd_range": (1.30, 1.40), "clamp_range": (0.28, 0.38)},
    150.0: {"cd": 1.3283, "st": 0.1835, "clamp": 0.5202,
            "cd_range": (1.26, 1.40), "clamp_range": (0.44, 0.60)},
}


def williamson_st(reynolds):
    """St(Re) for the laminar shedding regime (Williamson 1988)."""
    return -3.3265 / reynolds + 0.1816 + 1.6e-4 * reynolds


#: How the PRODUCT module records the same anchors in its own docstring:
#:     Re 100  Cd 1.3411   St 0.1647   Cl amp 0.3275   15 cycles
#: Parsed rather than eyeballed, because a fixture nobody compares against the
#: product is a fixture that drifts — and a drifted one still passes every
#: check it makes about itself. The STEADY rows ("Re 20   Cd 2.0646   Cl
#: -5.1e-07") carry no Strouhal number and deliberately do not match.
_ANCHOR_ROW = re.compile(
    r"Re\s+([0-9.]+)\s+Cd\s+([0-9.]+)\s+St\s+([0-9.]+)\s+Cl amp\s+([0-9.]+)")


def recorded_anchors(doc):
    """{Re: (Cd, St, Cl amplitude)} exactly as the product module records it."""
    return dict((float(m.group(1)),
                 (float(m.group(2)), float(m.group(3)), float(m.group(4))))
                for m in _ANCHOR_ROW.finditer(doc or ""))


def replay_anchor(case, cd_mean, st, cl_amp, reader, cycles=24.0, per_cycle=200):
    """Write the force log this anchor's OWN numbers imply, and read it BACK
    through the product.

    This is what stops the anchor block being a fixture talking to itself. The
    log is synthetic — no solve happens — but the Cd, Strouhal and lift
    amplitude the caller then judges come out of `force_history_from_log`,
    which is product code, at the anchor's own operating point rather than at
    the round numbers the arithmetic section below uses. Drag is written
    oscillating at 2f, as the real thing does, so a reader that keys on drag
    returns double the Strouhal number and fails against Williamson here too.

    `reader` is passed in because the gate imports emstudio inside main().
    """
    f = st * case.u_inf / case.d_ref          # the anchor's shedding frequency
    dt = 1.0 / (f * per_cycle)                # per_cycle samples per cycle
    n = int(cycles * per_cycle)
    q = case.q_ref
    out = []
    for i in range(n):
        t = i * dt
        cd = cd_mean + 0.02 * cd_mean * math.sin(4.0 * math.pi * f * t)
        cl = cl_amp * math.sin(2.0 * math.pi * f * t)
        out.append("Time = %.10g\n" % t)
        out.append("Sum of forces\n  Total    : (%.10g %.10g 0)\n"
                   "  Pressure : (%.10g %.10g 0)\n"
                   "  Viscous  : (0 0 0)\n" % (cd * q, cl * q, cd * q, cl * q))
    return reader("".join(out), q, case.d_ref, case.u_inf,
                  settle_time=n * dt * 0.5)


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    from emstudio.solvers.openfoam import wind as wind_mod
    from emstudio.solvers.openfoam.parser import force_history_from_log
    from emstudio.solvers.openfoam.wind import (RAS_SQUARE_RADIUS_RATIO,
                                                SHEDDING_RE, TURBULENT_RE,
                                                WindCase, write_wind)

    print("EMStudio unsteady wind gate")

    # --- the RECORDED anchors, replayed through the product ----------------
    # ⚠ NO SOLVE HAPPENS HERE and nothing below re-measures the flow. These
    # numbers came out of ONE past live run; the live re-measurement is the
    # SOLVER gate `openfoam_wind_transient`, which runs **Re 100 only** — the
    # Re 150 row is re-measured by no gate on any tier.
    #
    # What a FAST gate CAN do is refuse to be a fixture talking to itself.
    # Until 2026-08-29 every check in this block compared literals declared in
    # this file against a closed form declared in this file, imported nothing
    # from emstudio, and therefore stayed green through any product sabotage.
    # Two real ties replace that, and the labels say which is which:
    #
    #   RECORDED  — the fixture must equal, digit for digit, the anchor table
    #               `emstudio/solvers/openfoam/wind.py` publishes in its own
    #               docstring. Neither copy can now drift without the other.
    #   RECOVERED — each anchor is replayed as the force history its numbers
    #               imply and read BACK through `force_history_from_log`. The
    #               Williamson and published-range verdicts are then passed on
    #               what the PRODUCT returns, at the anchor's own Reynolds
    #               number, not on the literal.
    print(" recorded anchors (replayed through the product — nothing is solved):")
    recorded = recorded_anchors(wind_mod.__doc__)
    check("wind.py publishes a transient anchor table to pin the fixture to",
          set(recorded) == set(WIND_ANCHORS) and len(recorded) == len(WIND_ANCHORS),
          "parsed Re {0} from wind.py, fixture holds Re {1}".format(
              sorted(recorded), sorted(WIND_ANCHORS)))

    got_st, got_clamp = {}, {}
    for reynolds, a in sorted(WIND_ANCHORS.items()):
        cd, st, clamp = a["cd"], a["st"], a["clamp"]
        check("Re {0:g}: RECORDED — the fixture IS wind.py's own row".format(reynolds),
              recorded.get(reynolds) == (cd, st, clamp),
              "wind.py records {0}, fixture holds {1}".format(
                  recorded.get(reynolds), (cd, st, clamp)))

        # Replay -> the product's reader. Every number judged below is ITS
        # output; sabotage the reader and these go red.
        hist = replay_anchor(WindCase(reynolds=reynolds, transient=True),
                             cd, st, clamp, force_history_from_log)
        r_st, r_cd, r_clamp = hist.strouhal, hist.cd_mean, hist.cl_amplitude
        got_st[reynolds], got_clamp[reynolds] = r_st, r_clamp
        check("Re {0:g}: the product reads the record back unchanged".format(reynolds),
              abs(r_st - st) < 1e-5 and abs(r_cd - cd) < 1e-4
              and abs(r_clamp - clamp) < 1e-4 and hist.cycles_measured >= 5,
              "St {0:.5f} Cd {1:.5f} Cl {2:.5f} over {3} cycles".format(
                  r_st, r_cd, r_clamp, hist.cycles_measured))

        want = williamson_st(reynolds)
        err = abs(r_st - want) / want * 100.0
        check("Re {0:g}: RECOVERED St {1:.4f} vs Williamson {2:.4f}".format(
                  reynolds, r_st, want),
              err < 3.0, "{0:.2f} % — St is the sharp check".format(err))
        lo, hi = a["cd_range"]
        check("Re {0:g}: RECOVERED Cd {1:.4f} in the published {2}-{3}".format(
                  reynolds, r_cd, lo, hi),
              lo <= r_cd <= hi)
        lo, hi = a["clamp_range"]
        check("Re {0:g}: RECOVERED lift amplitude {1:.4f} in {2}-{3}".format(
                  reynolds, r_clamp, lo, hi),
              lo <= r_clamp <= hi,
              "a symmetric wake would give ~0, so this also proves shedding")

    # The TREND across the two anchors, which no single point can check: the
    # shedding frequency rises with Re, and so does the lift amplitude. Taken
    # from the RECOVERED values, so a reader that returned a constant — or
    # keyed on the time step rather than the flow — breaks the trend as well.
    res = sorted(got_st)
    check("RECOVERED Strouhal RISES with Reynolds number across the anchors",
          len(res) >= 2 and all(got_st[a] < got_st[b]
                                for a, b in zip(res, res[1:])),
          "{0}".format(["{0:.4f}".format(got_st[r]) for r in res]))
    check("RECOVERED lift amplitude rises with Reynolds number too",
          len(res) >= 2 and all(got_clamp[a] < got_clamp[b]
                                for a, b in zip(res, res[1:])),
          "0.33 at Re 100 -> 0.52 at Re 150")

    # --- the guard rails ---------------------------------------------------
    print(" guard rails:")
    steady_ok = WindCase(reynolds=20.0)
    check("steady below shedding onset is valid", steady_ok.method_is_valid)
    check("  ...and says nothing", steady_ok.validity_note() == "")

    steady_bad = WindCase(reynolds=100.0)
    check("steady ABOVE shedding onset is refused", not steady_bad.method_is_valid)
    note = steady_bad.validity_note()
    check("  ...and explains why", "UNDER-reads" in note and "transient" in note,
          note[:70])

    trans_ok = WindCase(reynolds=100.0, transient=True)
    check("transient above the onset is valid", trans_ok.method_is_valid)
    check("  ...and says nothing", trans_ok.validity_note() == "")

    # THE ONE THAT MATTERS MOST: transient does NOT make high Re legitimate.
    trans_hi = WindCase(reynolds=1.0e5, transient=True)
    check("transient at Re 1e5 is REFUSED", not trans_hi.method_is_valid,
          "no time-stepping scheme substitutes for a turbulence model")
    hi_note = trans_hi.validity_note()
    check("  ...and says it is the turbulence, not the time stepping",
          "turbulen" in hi_note.lower() and "not a wind load" in hi_note,
          hi_note[:70])
    check("the two guard rails are ordered", SHEDDING_RE < TURBULENT_RE)

    # --- the RAS-square benchmark domain is part of the definition ----------
    # Ruling 2026-08-23: radius_ratio 20 is part of the BENCHMARK, not a
    # knob — the r40 control COMPLETED cleanly and still read Cd 1.847,
    # below the published 1.95 floor. Until 2026-08-24 nothing enforced
    # this: a RAS square case built on the DEFAULT domain (40) reported
    # method_is_valid=True and the runner stamped it into the report as
    # though it were the validated configuration.
    print(" RAS-square domain pin:")
    ras_ok = WindCase(reynolds=21400.0, geometry="square", transient=True,
                      turbulence="kOmegaSST",
                      radius_ratio=RAS_SQUARE_RADIUS_RATIO)
    check("RAS square on the anchor domain is valid", ras_ok.method_is_valid)
    check("  ...and says nothing", ras_ok.validity_note() == "")
    ras_wide = WindCase(reynolds=21400.0, geometry="square", transient=True,
                        turbulence="kOmegaSST")  # DEFAULT radius_ratio
    check("RAS square on any OTHER domain is refused",
          not ras_wide.method_is_valid,
          "the r40 scout completed and still read Cd 1.847 vs the 1.95 floor")
    wide_note = ras_wide.validity_note()
    check("  ...and names the domain",
          "radius_ratio" in wide_note and "unvalidated" in wide_note,
          wide_note[:70])
    check("the anchor-domain constant IS the benchmark's 20",
          RAS_SQUARE_RADIUS_RATIO == 20.0,
          "+-10 d = Tian's 5% blockage; the SOLVER gate consumes this "
          "constant, so this literal is what pins BOTH to the benchmark")
    check("the laminar default stays the laminar-validated 40",
          WindCase().radius_ratio == 40.0,
          "the circle anchors (Re 20/100/150) ran at the DEFAULT domain; "
          "'helpfully' aligning it to the square benchmark un-validates them")

    # --- time-step and run-length sizing -----------------------------------
    print(" transient sizing:")
    c = WindCase(reynolds=100.0, transient=True, cycles=40.0)
    check("run length is the requested number of shedding periods",
          abs(c.end_time - 40.0 * c.shed_period) < 1e-9)
    check("one period is resolved by ~400 starting steps",
          abs(c.shed_period / c.delta_t - 400.0) < 1e-6,
          "a period resolved by a few steps returns the TIME STEP's Strouhal")
    check("half the run is discarded as startup",
          abs(c.settle_time - 0.5 * c.end_time) < 1e-9)
    check("shed period tracks the freestream, not the diameter alone",
          abs(c.shed_period - c.d_ref / (c.st_guess * c.u_inf)) < 1e-12)

    # --- the written case ---------------------------------------------------
    print(" what gets written:")
    import tempfile
    import shutil as _sh
    d = tempfile.mkdtemp(prefix="windt_")
    try:
        write_wind(d, WindCase(reynolds=100.0, transient=True))
        cd_txt = open(os.path.join(d, "system", "controlDict")).read()
        sch = open(os.path.join(d, "system", "fvSchemes")).read()
        sol = open(os.path.join(d, "system", "fvSolution")).read()
        check("transient runs pimpleFoam", "application     pimpleFoam;" in cd_txt)
        check("time derivative is not steadyState",
              "steadyState" not in sch and "backward" in sch,
              "a steadyState ddt in a transient run silently solves the "
              "steady problem")
        check("PIMPLE controls present, SIMPLE gone",
              "PIMPLE" in sol and "SIMPLE\n" not in sol)
        check("forces are reported EVERY step",
              "writeControl    timeStep;" in cd_txt
              and "writeInterval   1;" in cd_txt,
              "sampling coarsely would alias the shedding period")
        check("the time step adapts to a Courant limit",
              "adjustTimeStep  yes;" in cd_txt and "maxCo" in cd_txt)

        steady_txt_dir = tempfile.mkdtemp(prefix="winds_")
        try:
            write_wind(steady_txt_dir, WindCase(reynolds=20.0))
            s_cd = open(os.path.join(steady_txt_dir, "system", "controlDict")).read()
            s_sch = open(os.path.join(steady_txt_dir, "system", "fvSchemes")).read()
            check("the steady path is UNCHANGED",
                  "application     simpleFoam;" in s_cd
                  and "default steadyState;" in s_sch,
                  "its Re 20 / Re 40 anchors must still mean what they meant")
        finally:
            _sh.rmtree(steady_txt_dir, ignore_errors=True)
    finally:
        _sh.rmtree(d, ignore_errors=True)

    # --- the history arithmetic --------------------------------------------
    # A synthetic log: a known frequency in, the same frequency out. This is
    # where a plausible wrong answer would come from — a factor of two, or a
    # phase-dependent mean.
    print(" history arithmetic (synthetic log, known answer):")
    import math
    d_ref, u_inf, q = 0.02, 0.075, 2.0
    st_true = 0.2
    f = st_true * u_inf / d_ref
    lines = []
    n = 4000
    dt = 1.0 / (f * 200.0)                       # 200 samples per cycle
    for i in range(n):
        t = i * dt
        # Drag oscillates at 2f about its mean; lift at f. If the reader keys
        # on drag it returns DOUBLE the true Strouhal number.
        cd = 1.4 + 0.02 * math.sin(4.0 * math.pi * f * t)
        cl = 0.35 * math.sin(2.0 * math.pi * f * t)
        lines.append("Time = %.10g\n" % t)
        lines.append("Sum of forces\n  Total    : (%.10g %.10g 0)\n"
                     "  Pressure : (%.10g %.10g 0)\n"
                     "  Viscous  : (0 0 0)\n" % (cd * q, cl * q, cd * q, cl * q))
    log = "".join(lines)
    hist = force_history_from_log(log, q, d_ref, u_inf, settle_time=n * dt * 0.5)
    check("Strouhal recovered from a known signal",
          abs(hist.strouhal - st_true) / st_true < 0.01,
          "got {0:.5f}, true {1:.5f}".format(hist.strouhal, st_true))
    check("  ...and NOT double it (that would be drag's frequency)",
          abs(hist.strouhal - 2.0 * st_true) / st_true > 0.5)
    check("mean drag recovered", abs(hist.cd_mean - 1.4) < 0.01,
          "got {0:.5f}".format(hist.cd_mean))
    check("lift amplitude recovered", abs(hist.cl_amplitude - 0.35) < 0.01,
          "got {0:.5f}".format(hist.cl_amplitude))
    check("whole cycles were measured", hist.cycles_measured >= 5,
          "{0} cycles".format(hist.cycles_measured))

    # A log with no shedding at all must SAY so, not report St 0 as a fact.
    flat = "".join("Time = %.10g\nSum of forces\n  Total    : (2.8 0 0)\n"
                   "  Pressure : (2.8 0 0)\n  Viscous  : (0 0 0)\n" % (i * 0.01)
                   for i in range(50))
    quiet = force_history_from_log(flat, q, d_ref, u_inf)
    check("a steady (non-shedding) history reports NO Strouhal",
          quiet.strouhal == 0.0 and any("not measured" in w.lower()
                                        or "no complete" in w.lower()
                                        for w in quiet.warnings),
          str(quiet.warnings[:1]))

    # An empty log must raise, not return zeros — a zero force is a claim.
    raised = False
    try:
        force_history_from_log("no forces here", q, d_ref, u_inf)
    except ValueError:
        raised = True
    check("an unreadable log RAISES", raised)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("WIND-TRANSIENT GATE PASSED")
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
        raise SystemExit("wind-transient validation failed")
    sys.exit(0)
