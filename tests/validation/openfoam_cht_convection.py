# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — conjugate NATURAL CONVECTION, run for real.

SOLVER tier (~11 min on the reference box): the buoyant two-region gap —
gravity on, target Ra 1e6 nominal, H/L 4, the 40x60 mesh — through
`chtMultiRegionSimpleFoam`, with the gap Nusselt number recovered by
`cht.gap_nusselt` from the solved solid mean.

WHY THE WINDOW IS [5.5, 8.6] AND NOT A TIGHT PIN. Unlike the g = 0 anchor
(closed form, exact), a convective Nu has no exact answer here, so the
window is deliberately WIDER than every reference. Its job is to catch the
failure this gate exists for — a geometry/physics artifact that parks Nu
near the conduction limit — NOT to certify agreement with a correlation.

References at THIS case (A = H/L = 4, Pr = 0.7, interface Ra ~8.5e5):
  * Berkovsky-Polevikov, Nu = 0.22*(Pr*Ra/(0.2+Pr))^0.28 * A^(-1/4): 6.638
    (the aspect factor MATTERS — without it the same fit reads ~9.5);
  * ElSherbiny-Raithby-Hollands at its nearest VALID aspect (A = 5): 6.411;
  * the incompressible single-region reference on the donor mesh: 6.99.
  ⚠ MacGregor & Emery (~8.4) is NOT quoted as a reference here: it is
    published for 10 < H/L < 40 and 1 < Pr < 2e4, and this case is A = 4,
    Pr = 0.7 — out of range on BOTH, so evaluating it here is a double
    extrapolation, not an evaluation. The 8.6 upper edge is therefore
    deliberate slack, not a correlation value. ⚠ A solve reading ~8.5 would
    PASS this gate while sitting ~28 % above every in-range reference; that
    is accepted, because tightening the top edge around fits this case is
    outside their validity would trade a real guarantee for a false one.

WHAT THIS GATE'S OWN MESH READS, and why it is not "the" answer. The gate
runs 40x60 and measures ~6.85. The 3-grid refinement study
(docs/results/cht_refinement_fixedmesh.txt, 2026-08-19: 40x60 6.8529 ->
60x90 6.6957 -> 80x120 6.6387, all converged) puts the mesh-independent
value at **~6.5** (bracket 6.47-6.56 across defensible GCI conventions),
so **this gate's mesh reads roughly 5 % high**. That is fine for a
pass/fail window, but:
  ⚠ DO NOT quote 6.85 as "the" Nusselt number anywhere user-facing, and do
    not cite it as one of the references that bracket this window — the
    gate's own measurement cannot justify the gate's own bounds.
  ⚠ The scheme is FIRST-ORDER upwind in div(phi,U|h|e), so the formal order
    is 1; the study's observed p = 1.90 is about twice that, which is why
    its extrapolate is reported as a bracket rather than a single value.

⚠ Ra and Nu are INTERFACE-referenced (the fluid never sees the nominal
hot-to-cold drop; the solid takes its share). The conduction limit of this
same recovery is Nu = 1 exactly, gated FAST in `cht_setup`.

WHY THIS GATE PARSES THE SOLVER LOG. Every other runner in the package
publishes ``report["converged"]``; ``run_cht`` publishes no such key, so
``report["ok"]`` — rc == 0, i.e. "it reached endTime and exited" — was the
only thing standing between a solve and a Nusselt number being read off its
field and windowed as physics. It cannot be made to publish one either:
``run_chain`` derives convergence from the string "SIMPLE solution
converged", which only ``Foam::simpleControl::loop()`` prints, and
``chtMultiRegionSimpleFoam`` is built ``#define NO_CONTROL`` over a bare
``runTime.loop()`` — its ``read{Fluid,Solid}MultiRegionSIMPLEControls.H``
read nNonOrthogonalCorrectors, momentumPredictor and frozenFlow, and NOTHING
ELSE. ⚠ So the ``residualControl`` this case writes is never read by the
solver that runs it, the per-step flag is False on every conjugate run
whether or not it converged, and this gate is the only thing in the project
holding the case to the criteria it declares. The evidence is therefore
taken the way docs/results/cht_convergence.py took it for the refinement
study — full iteration budget, residuals against the case's own
residualControl, and the drift of T over the last 1000 iterations.

THE FAILURE THIS EXISTS TO CATCH: the swapped-face-sets mesh
(topBottom/frontAndBack exchanged, shipped until `69b65e5`) pinned Nu at
1.86-1.88 at ANY scale and ANY solver route — Hele-Shaw drag from walls one
cell apart, with gravity pointing out of the solved plane. `cht_setup`
catches that structurally (face planes recomputed from vertex coordinates);
this gate is the LIVE confirmation that the physics actually convects.
⚠ Note the honest form of the 08-17 rebuttal: refinement DOES move Nu
  slightly toward the conduction limit (-2.3 %, then -0.85 %) — the same
  SIGN as the broken mesh's -36 %. What distinguishes them is magnitude and
  that the increments shrink. Do not restate this as a direction argument.
"""
import os
import re
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: The correlation window (see the module docstring for each edge's source).
NU_LO, NU_HI = 5.5, 8.6

#: How many of the final iterations the "has it stopped moving?" measurement
#: spans. 1000, not the whole run: a window that reaches back into the
#: transient measures the transient, and a window of a few iterations measures
#: round-off. Deliberately shorter than the 5000 the refinement study quotes,
#: so this stays a statement about the END of the run.
DRIFT_ITERS = 1000

#: Bound on the movement of either extreme of T, in either region, across that
#: window (K). MEASURED 2026-08-29 on this gate's own 40x60 case: a completed
#: 20000-iteration run drifts 1.1e-6 K, and stopping the SAME case at 1500
#: iterations drifts 1.7e-2 K — so the bound sits ~900x above the converged
#: reading and ~17x below the unconverged one, in a gap four orders of
#: magnitude wide. docs/results/cht_refinement_fixedmesh.txt reports 0.0 K and
#: 1.0e-7 K on the finer grids at the full 20000, and the print precision of
#: OpenFOAM's own "Min/max T" line is ~1e-7 K at 350 K, so the converged
#: readings are at the floor of what the log can express.
#: ⚠ 1500 iterations is what makes this bound worth having: by then the
#: residuals ALREADY meet residualControl (8.8e-8) and the recovered Nu is
#: 6.8529, the gate's own headline number, dead inside the window. Residuals
#: alone would have certified a field still moving.
#: For scale, the gap dT this recovery divides by is 42.45 K, so 1e-3 K is
#: ~2e-5 of the signal.
DRIFT_MAX_K = 1.0e-3

#: The residual lines chtMultiRegionSimpleFoam writes, one per equation per
#: region, e.g. "DILUPBiCGStab:  Solving for Ux, Initial residual = 4.6e-03,".
_RES = re.compile(r"Solving for (\w+), Initial residual = ([^,]+),")
#: Which region's block the following lines belong to. Both the fluid and the
#: solid announce themselves this way once per iteration.
_REGION = re.compile(r"^Solving for (?:fluid|solid) region (\S+)")
#: "Min/max T:340.274409 350" — the ONLY per-iteration record of the field
#: itself. ⚠ Anchored, so the "Min/max rho:" line cannot match it.
_MINMAX_T = re.compile(r"^Min/max T:(\S+)\s+(\S+)")
#: OpenFOAM's own iteration marker.
_TIME = re.compile(r"^Time = ")
#: `residualControl { p_rgh 1e-5; U 1e-5; h 1e-6; }` out of a written
#: fvSolution. ⚠ Only bare word keys: the RAS variant writes a quoted regex
#: key ("(k|omega)"), which names no single field and is skipped rather than
#: crashed on.
_RC_BLOCK = re.compile(r"residualControl\s*\{([^}]*)\}")
_RC_ENTRY = re.compile(r"(\w+)\s+([0-9.eE+-]+)\s*;")


def read_solver_log(path):
    """Iterations run, final initial-residual per equation, and T history.

    ⚠ The WHOLE log, deliberately — not the ``tail`` ``run_chain`` keeps on
    the step, which is the last 3000 characters and covers roughly 25 of
    these iterations. A drift measured over 25 iterations of a frozen field
    reports round-off, not convergence, and would pass on anything.

    Residuals and temperatures are both keyed by REGION, because the two
    regions each solve their own ``h`` and an unkeyed reading would silently
    report only whichever was printed last (the solid's, which is the easy
    one — a pure conduction equation that converges early even while the
    fluid is still turning over).
    """
    iterations = 0
    region = None
    residuals = {}
    history = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if _TIME.match(line):
                # A new outer iteration: nothing belongs to a region again
                # until that region announces itself.
                iterations += 1
                region = None
                continue
            match = _REGION.match(line)
            if match:
                region = match.group(1)
                continue
            if region is None:
                continue
            match = _RES.search(line)
            if match:
                residuals["%s/%s" % (region, match.group(1))] = \
                    float(match.group(2))
                continue
            match = _MINMAX_T.match(line)
            if match:
                history.setdefault(region, []).append(
                    (float(match.group(1)), float(match.group(2))))
    return iterations, residuals, history


def declared_residual_control(case_dir, region):
    """The convergence criteria the CASE ITSELF declares, per region.

    Read back out of the written ``system/<region>/fvSolution`` rather than
    restated here, so the bound this gate enforces is the product's own
    number and cannot drift away from it. That matters more than usual here:
    chtMultiRegionSimpleFoam NEVER READS this dictionary (see the block in
    ``main``), so the gate is the only thing in the project that holds the
    case to the criteria it writes down.
    """
    path = os.path.join(case_dir, "system", region, "fvSolution")
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    block = _RC_BLOCK.search(text)
    if not block:
        return {}
    return dict((name, float(value))
                for name, value in _RC_ENTRY.findall(block.group(1)))


def residual_verdict(residuals, criteria):
    """Pair each measured residual with the criterion that governs it.

    Returns ``(offenders, matched)``. ``U 1e-5`` governs the log's ``Ux`` and
    ``Uy``, so a component falls back to its vector's criterion — otherwise
    the momentum residuals, the ones that actually lag on a buoyant case,
    would be measured against nothing at all.
    """
    offenders = []
    matched = set()
    for key in sorted(residuals):
        region, field = key.split("/", 1)
        limit = criteria.get(region, {}).get(field)
        governing = field
        if limit is None and field[-1:] in ("x", "y", "z"):
            governing = field[:-1]
            limit = criteria.get(region, {}).get(governing)
        if limit is None:
            continue
        matched.add("%s/%s" % (region, governing))
        if not residuals[key] <= limit:
            offenders.append("%s %.3e > %.1e" % (key, residuals[key], limit))
    return offenders, matched


def worst_drift(history, span):
    """Largest movement of any extreme of T, in any region, over ``span``.

    BOTH extremes of BOTH regions, because which one is pinned by a boundary
    condition and which one carries the answer is a property of the case, not
    of this measurement: the fluid's min sits on the cold wall and the solid's
    max on the hot one, so reading a single end could report a Dirichlet
    condition holding still and call it convergence.
    """
    worst = None
    for region in sorted(history):
        values = history[region]
        if len(values) <= span:
            continue
        moved = max(abs(values[-1][0] - values[-1 - span][0]),
                    abs(values[-1][1] - values[-1 - span][1]))
        if worst is None or moved > worst[1]:
            worst = (region, moved)
    return worst


def check(label, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", label,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


def main():
    from emstudio.solvers.openfoam import cht
    from emstudio.solvers.openfoam.runner import run_cht, CHT_SOLVE_STEPS

    # The application whose log carries the physics, taken from the runner's
    # own step list rather than spelled again here — a gate that names the
    # solver itself would keep measuring the old one after a swap.
    solve_app = CHT_SOLVE_STEPS[-1].split()[0]

    print("EMStudio conjugate natural-convection gate (LIVE SOLVE, ~11 min)")
    case = cht.ChtCase(gravity=9.81, target_ra=1.0e6, n_y=60, n_fluid=40,
                       iterations=20000)
    if not case.buoyant:
        check("the case is buoyant", False, "gravity+cells contract broke")
        return 1
    print("  nominal Ra %.4g  H/L %.2f  conduction limit q %.4f W/m^2"
          % (case.rayleigh, case.aspect, case.flux))

    tmp = tempfile.mkdtemp(prefix="cht_conv_gate_")
    try:
        report, _means = run_cht(tmp, case, timeout=3600)
        if not report.get("ok"):
            check("the solve ran", False, "{0}: {1}".format(
                report.get("failed_at"), report.get("error")))
            for s in report.get("steps", []):
                if s.get("rc"):
                    print("    last of {0}:\n{1}".format(
                        s["step"], s.get("tail", "")[-600:]))
            return 1
        check("the solve ran", True)

        # ── IS THE FIELD ACTUALLY FINISHED? ──────────────────────────────
        # ⚠ `report["ok"]` is rc == 0 and NOTHING MORE. For this application
        # rc == 0 says only "it reached endTime and exited"; SIMPLE exits 0
        # just as happily with its residuals still falling, which is the very
        # thing `run_chain` grew a per-step `converged` flag to record after
        # it cost a 34 %-wrong Nusselt number.
        #
        # ⚠ AND THAT FLAG IS USELESS HERE — do not "fix" this by asserting
        # it. `run_cylinder`, `run_cavity`, `run_solid` and `run_wind` all
        # publish `report["converged"]`; `run_cht` publishes no such key, and
        # it could not honestly publish one. `run_chain` derives the flag
        # from the string "SIMPLE solution converged", printed ONLY by
        # `Foam::simpleControl::loop()`, and chtMultiRegionSimpleFoam is
        # built `#define NO_CONTROL` over a bare `runTime.loop()` — it never
        # constructs a simpleControl. Read on v2512's own source: its
        # `read{Fluid,Solid}MultiRegionSIMPLEControls.H` take
        # nNonOrthogonalCorrectors, momentumPredictor and frozenFlow and
        # nothing else, so the `residualControl` this case writes is never
        # read by the solver that runs it. The step flag is therefore
        # structurally False on EVERY conjugate run, converged or not
        # (confirmed live: 200 iterations and 20000 both report False), and
        # asserting it would pin this gate red for ever.
        #
        # So the evidence comes from the solver's own log, by the protocol
        # docs/results/cht_convergence.py established for the refinement
        # study: it ran its whole budget, the residuals met the criteria the
        # case declares, and the field stopped moving. Without this, a solve
        # cut short still prints PASSED and its Nusselt number is read off a
        # field that was still in motion.
        # ⚠ NOT a check: "the solve step is present with rc 0" is already
        # guaranteed by the `report["ok"]` guard above — `run_cht` extends
        # the solve chain's steps into the report and clears `ok` if any of
        # them returned non-zero — so asserting it would print an "ok" line
        # that no regression could ever turn red. The log below is the real
        # evidence, and a wrong step name shows up there as a missing file.
        log_path = os.path.join(tmp, "log.%s" % solve_app)
        ran, residuals, history = (0, {}, {})
        if os.path.isfile(log_path):
            ran, residuals, history = read_solver_log(log_path)
        check("the solver log is readable and iteration-marked",
              ran > 0 and bool(residuals) and bool(history),
              "%s: %d iterations, %d residual series, regions %s"
              % (log_path, ran, len(residuals), sorted(history)))

        # This solver cannot stop early — nothing reads residualControl — so
        # anything short of the budget means it died on its feet while still
        # returning 0. ⚠ If chtMultiRegionSimpleFoam ever DOES honour
        # residualControl, this is the assertion to revisit, and it will say
        # so by failing rather than by quietly accepting a short run.
        check("it ran its full {0}-iteration budget".format(case.iterations),
              ran == case.iterations,
              "%d of %d — this application has no early exit, so a short "
              "run is a dead solver, not a converged one"
              % (ran, case.iterations))

        # Both regions must have been measured. A log that names only one of
        # them would let the drift check below pass on whichever region the
        # parse happened to catch.
        check("both regions reported a temperature history",
              set(history) == {cht.FLUID_REGION, cht.SOLID_REGION},
              "saw %s, expected %s" % (sorted(history),
                                       sorted({cht.FLUID_REGION,
                                               cht.SOLID_REGION})))

        criteria = dict(
            (region, declared_residual_control(tmp, region))
            for region in (cht.FLUID_REGION, cht.SOLID_REGION))
        offenders, matched = residual_verdict(residuals, criteria)
        wanted = set("%s/%s" % (region, field)
                     for region, fields in criteria.items()
                     for field in fields)
        # ⚠ Vacuity guard, and it is the whole reason this reads the criteria
        # out of the case instead of restating them: if a log-format or
        # fvSolution change stopped the two sides pairing up, `offenders`
        # would come back empty and an unconverged solve would sail through
        # on a check that measured nothing.
        check("every declared criterion was matched to a measured residual",
              bool(wanted) and matched == wanted,
              "declared %s, matched %s" % (sorted(wanted), sorted(matched)))
        check("the final residuals meet the case's own residualControl",
              not offenders,
              "; ".join(offenders) if offenders else
              ", ".join("%s %.2e" % (k, residuals[k])
                        for k in sorted(residuals)))

        moved = worst_drift(history, DRIFT_ITERS)
        # Residuals establish that the EQUATIONS stopped complaining; this
        # establishes that the QUANTITY stopped moving. The refinement study
        # leaned on exactly this distinction, and the recovery below reads a
        # solid mean, so the solid's own history has to be one of the things
        # standing still.
        check("T stopped moving over the last {0} iterations".format(
                  DRIFT_ITERS),
              moved is not None and moved[1] <= DRIFT_MAX_K,
              "worst %s over the last %d its (bound %.1e K); measured "
              "1.1e-06 K on a converged 20000-iteration run against "
              "1.7e-02 K on the same case stopped at 1500"
              % ("none — fewer than %d samples" % DRIFT_ITERS
                 if moved is None else "%s %.3e K" % moved,
                 DRIFT_ITERS, DRIFT_MAX_K))

        # ⚠ Nothing below here may run on a field the checks above rejected:
        # a Nusselt number recovered from a moving field is a number, and it
        # would be printed and windowed exactly like a real one.
        if FAILURES:
            print("")
            print("FAILED {0} check(s) BEFORE the field was trusted: {1}"
                  .format(len(FAILURES), "; ".join(FAILURES[:5])))
            return 1

        m = cht.gap_nusselt(case, report["t_solid_mean"])
        print("  q %.4f W/m^2  T_int %.4f K  gap dT %.4f K" %
              (m.q, m.t_interface, m.dt_gap))
        print("  MEASURED Nu %.4f at Ra %.4g (interface-referenced)" %
              (m.nu, m.ra))

        check("Nu {0:.4f} inside the correlation window [{1}, {2}]".format(
                  m.nu, NU_LO, NU_HI),
              NU_LO <= m.nu <= NU_HI,
              "in-range refs at A=4, Pr=0.7: Berkovsky-Polevikov 6.638, "
              "ElSherbiny-class (A=5) 6.411, incompressible reference "
              "6.99; mesh-independent value ~6.5 (this gate's 40x60 "
              "mesh reads ~5 % high, which is expected). The window is "
              "deliberately wider than every reference — its job is to "
              "keep the broken-mesh signature 1.86-1.88 dead, not to "
              "certify a correlation")
        # An INDEPENDENT second kill, not a restatement of the Nu window:
        # the conduction limit of this case sits at Ra_int 9.75e5 and a
        # nominal-drop referencing regression returns 1e6 — both FAIL this
        # bound, while any solve convecting inside the Nu window lands at
        # or below ~8.8e5 (more convection = more of the drop taken by the
        # solid = lower interface Ra).
        check("the interface-referenced Ra {0:.4g} stayed in regime".format(
                  m.ra),
              5.0e5 <= m.ra <= 9.0e5,
              "9.0e5 excludes BOTH the conduction limit (9.75e5) and a "
              "nominal-referenced Ra (1e6)")
        # Convection must pull the interface DOWN from the conduction answer
        # — that is what 'the fluid carries more heat' means at the wall.
        check("T_int {0:.2f} K sits below the conduction limit {1:.2f} K"
              .format(m.t_interface, case.t_interface),
              m.t_interface < case.t_interface - 2.0,
              "measured 2026-08-18: 348.74 (conduction) -> 342.45 (fixed "
              "mesh, convecting)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-CHT-CONVECTION GATE PASSED")
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
        raise SystemExit("openfoam-cht-convection validation failed")
    sys.exit(0)
