#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — 3-D coil INDUCTANCE from stored energy, and the
delivered-ampere-turns guard.

What this pins
--------------
1. ``L = 2W/I^2`` against the analytic self-inductance of a circular loop,

       L = mu0 * R * [ ln(8R / a_gmd) - 2 ],   a_gmd = 0.44705 c  (square c x c)

   accurate to ~1 % for R/c >> 1. Ring: R = 100 mm, 4 x 4 mm section, 1000 A.
   MEASURED 2026-08-05 on ElmerSolver 26.2: -1.74 %.

2. The GUARD. ``Coil Closed = Logical True`` is an ASSERTION the deck makes on
   the user's behalf — Elmer prints "Assuming that all coils are closed!" and
   believes it. An OPEN conductor therefore solves cleanly, warns about
   nothing, and returns a field wildly below theory (measured on a real user
   helix: 5.17 delivered ampere-turns against 100 requested — 5.2 % — and an
   axial field ~160x under the finite-solenoid value). The guard compares
   delivered against requested, and delivered is exact because the half-plane
   section counts every turn.

   The pure half is gated here without a solver — but the VERDICT is asked of
   the product: ``_guard_verdict`` drives ``model3d.run3d``'s own guard with
   the measured pair and asserts what IT returns. Re-deriving the band here
   from literals (what this file used to do) tests nothing: no edit to the
   real guard could fail it. A topological (Euler/genus)
   test is deliberately NOT used and must not be reintroduced: it reports
   EMStudio's own closed template tube as genus-0, because OCC's seam edges
   break the naive V-E+F count (measured, same day).
"""

from __future__ import annotations

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

FAILURES = []


def check(label, ok, detail=""):
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:78] + "]") if detail else ""))


R_M = 0.100
C_M = 0.004
I_A = 1000.0


def analytic_loop_h(radius_m, side_m):
    a = 0.44705 * side_m                      # geometric mean distance
    return 4e-7 * math.pi * radius_m * (math.log(8.0 * radius_m / a) - 2.0)


def ring_model():
    return {
        "bodies": [{
            "name": "ring",
            "shape": {"kind": "tube", "center": (0.0, 0.0),
                      "r_in": R_M - C_M / 2.0, "r_out": R_M + C_M / 2.0,
                      "z0": -C_M / 2.0, "z1": C_M / 2.0},
            "mu_r": 1.0, "lc": 0.0012,
            "coil": {"amp_turns": I_A, "normal": (0.0, 0.0, 1.0),
                     "section_area_m2": C_M * C_M},
        }],
        "air": {"kind": "cylinder", "r": 1.0, "z0": -1.0, "z1": 1.0},
        "lc_air": 0.150,
        "size_fields": [{"kind": "distance", "body": "ring", "lc": 0.0012,
                         "dist_min": 0.005, "dist_max": 0.50}],
    }


#: The measured pair the guard was BUILT from (2026-08-05, ElmerSolver 26.2).
#: Closed ring: J_avg over its half-plane section -> 999.8 of 1000 At.
#: Mis-declared helix: an OPEN conductor whose deck STILL said "Coil Closed"
#: (being wrong about that is the whole defect the guard exists to catch), so
#: it too goes through the closed branch: J_avg over the 6.44-turn half-plane
#: section -> 5.17 of 100 At.
J_CLOSED_A_M2 = 6.2490e7
J_OPEN_A_M2 = 2.8396e3
OPEN_REQ_AT = 100.0
OPEN_SECTION_M2 = 6.43588 * 282.843e-6         # 6.44 turns x 282.843 mm^2


def _coil_model(name, amp_turns, section_m2):
    """The smallest model3d dict the delivery guard reads."""
    return {"bodies": [{"name": name,
                        "coil": {"amp_turns": amp_turns,
                                 "section_area_m2": section_m2}}],
            "notes": []}


def _guard_verdict(model, j_avg_a_m2):
    """Ask the PRODUCT's delivered-ampere-turns guard about one measurement.

    Returns ``(delivered_amp_turns, warnings)`` exactly as ``model3d.run3d``
    computed them.

    WHY the stubs: the guard lives INSIDE ``run3d``, downstream of a FreeCAD
    analysis and a live Elmer run, so the only way to reach it without a
    solver is to hand it those two. They supply INPUT ONLY — the geometry
    dict and the J_avg the solver measured. Everything asserted on is
    computed by ``run3d`` itself: the delivered ampere-turns, and whether the
    band accepted or refused. So widening, narrowing or deleting the band in
    ``emstudio/solvers/elmer/model3d.py`` changes what comes back here.
    Until 2026-08-29 this gate re-implemented ``0.5 <= frac <= 2.0`` from
    literals of its own and never imported ``model3d`` at all, so the four
    checks below could not fail for any edit to the guard they named.

    Both stubs are empty of warnings and notes, so any warning returned is
    one the guard itself raised.
    """
    import shutil
    import tempfile

    from emstudio.solvers.elmer import model3d, runner3d

    res = {"solver_warnings": [], "energy_j": None,
           "j_avg": [float(j_avg_a_m2)], "open_coil_current": [],
           "vtu": None, "workdir": "", "duration_s": 0.0,
           "body_ids": {}, "norms": {}}

    class _Analysis:                    # run3d reads only .Label, for meta
        Label = "coil_inductance_elmer gate"

    base = tempfile.mkdtemp(prefix="emstudio_gate_guard_")
    real_build, real_run = model3d.build_3d_model, runner3d.run_model3d
    model3d.build_3d_model = lambda analysis, solver, workdir: model
    runner3d.run_model3d = lambda m, workdir=None, line_callback=None: res
    try:
        out = model3d.run3d(_Analysis(), None, workdir=base)
    finally:
        # Restore even on failure: a leaked monkeypatch would poison every
        # later import in the same interpreter (the battery runs gates in
        # one process on some paths).
        model3d.build_3d_model = real_build
        runner3d.run_model3d = real_run
        shutil.rmtree(base, ignore_errors=True)
    case = out.cases[0]
    return (case["delivered_amp_turns"] or [None])[0], list(
        case["solver_warnings"])


def gate_pure():
    """No solver needed: the writer emits the keywords, and the guard arithmetic."""
    from emstudio.solvers.elmer import writer3d

    import tempfile

    path = os.path.join(tempfile.mkdtemp(), "case.sif")
    writer3d.write_sif3d(ring_model(), path, {"air": 1, "ring": 2},
                         {"outer": 1})
    deck = open(path, encoding="utf-8").read()

    check("deck asks CalcFields for the field energy (the inductance source)",
          "Calculate Field Energy = Logical True" in deck)
    check("deck asks CoilSolver for the delivered coil current",
          "Calculate Coil Current = Logical True" in deck)
    # The keyword that does NOT exist in Elmer's SOLVER.KEYWORDS. Emitting it
    # would silently do nothing and the energy would never appear.
    check("deck does NOT emit the non-existent 'Calculate Magnetic Field "
          "Energy'", "Calculate Magnetic Field Energy" not in deck)

    # --- the delivered-ampere-turns guard, both directions, no solver ---
    # The numbers below are the MEASUREMENT; the accept/refuse verdict and the
    # delivered ampere-turns come back out of model3d.run3d's real guard.
    # closed ring, measured: J_avg 6.2490e7 A/m^2 over 16 mm^2 -> 999.8 At
    got_closed, warn_closed = _guard_verdict(
        _coil_model("ring", I_A, C_M * C_M), J_CLOSED_A_M2)
    frac_closed = (got_closed / I_A) if got_closed is not None else 0.0
    check("measured CLOSED-ring delivery is within the product's guard band",
          got_closed is not None and not warn_closed,
          "{0} of {1:.0f} At ({2:.2%}); {3}".format(
              "{0:.1f}".format(got_closed) if got_closed is not None
              else "NOTHING", I_A, frac_closed,
              warn_closed[0][:30] if warn_closed else "no warning"))
    check("closed ring delivers essentially all of it (>99 %)",
          frac_closed > 0.99, "{0:.4%}".format(frac_closed))
    # open helix, measured: J_avg 2.8396e3 A/m^2 over 6.44 x 282.843 mm^2
    got_open, warn_open = _guard_verdict(
        _coil_model("helix", OPEN_REQ_AT, OPEN_SECTION_M2), J_OPEN_A_M2)
    frac_open = (got_open / OPEN_REQ_AT) if got_open is not None else 0.0
    # Refusal is not enough: the message must also name the coil and the
    # closed-declaration, because the guard's OTHER branch (a declared-open
    # coil) warns about terminal faces instead and would be the wrong
    # diagnosis for this measurement.
    check("measured OPEN-helix delivery is REFUSED by the product's guard "
          "band, blaming the closed declaration",
          bool(warn_open) and "helix" in warn_open[0]
          and "OPEN conductor" in warn_open[0],
          "{0} of {1:.0f} At ({2:.2%}); {3}".format(
              "{0:.3f}".format(got_open) if got_open is not None
              else "NOTHING", OPEN_REQ_AT, frac_open,
              warn_open[0][:30] if warn_open else "NO WARNING"))
    # 19x on the measured pair (99.98 % vs 5.17 %). Stated as >10x so the gate
    # asserts the SEPARATION it actually has: an earlier draft claimed "three
    # orders of magnitude" from a per-turn area instead of the all-turns
    # half-plane section, and this check caught it.
    check("the two cases are separated by more than 10x",
          frac_open > 0.0 and frac_closed / frac_open > 10.0,
          "ratio {0:.0f}x".format(frac_closed / frac_open)
          if frac_open > 0.0 else "no open-case delivery reported")

    # The rejected alternative, pinned so it cannot come back.
    check("genus/Euler is NOT used to detect closure (it misjudges the "
          "shipped tube)",
          "genus" not in deck.lower())


def gate_live():
    """The real solve: L against the analytic loop."""
    from emstudio.solvers.elmer.runner3d import run_model3d

    try:
        res = run_model3d(ring_model(), workdir=None)
    except Exception as exc:                                    # noqa: BLE001
        print("  skip  live tier — 3-D Elmer run unavailable: {0}".format(exc))
        return

    W = res.get("energy_j")
    check("the run reports a field energy (not the old hard-coded 0.0)",
          W is not None and W > 0.0, W)
    if W is None:
        return
    L_fem = 2.0 * W / (I_A * I_A)
    L_ana = analytic_loop_h(R_M, C_M)
    err = L_fem / L_ana - 1.0
    check("L = 2W/I^2 matches the analytic loop within 5 %",
          abs(err) < 0.05,
          "FEM {0:.6g} H vs {1:.6g} H ({2:+.2%})".format(L_fem, L_ana, err))
    check("the run reports a per-coil average current density",
          len(res.get("j_avg") or []) == 1, res.get("j_avg"))
    # The current is the LIVE solve's; the pass/fail is the product's, for the
    # same reason as gate_pure — a band re-typed here would agree with itself
    # forever. run_model3d sits BELOW the guard (which lives in run3d), so the
    # measured J_avg is handed up to it.
    j = (res.get("j_avg") or [0.0])[0]
    frac = abs(j) * C_M * C_M / I_A
    delivered, warn = _guard_verdict(_coil_model("ring", I_A, C_M * C_M), j)
    check("a CLOSED coil passes the product's delivered-ampere-turns guard",
          delivered is not None and not warn,
          "{0:.2%} delivered; {1}".format(
              frac, warn[0][:40] if warn else "no warning"))
    check("live solve converged cleanly", not res["solver_warnings"],
          "; ".join(res["solver_warnings"][:2]))


def main():
    print("EMStudio 3-D coil inductance + delivery gate")
    gate_pure()
    gate_live()
    print("-------------------")
    if FAILURES:
        raise SystemExit("COIL INDUCTANCE GATE FAILED: " + "; ".join(FAILURES))
    print("COIL INDUCTANCE GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
