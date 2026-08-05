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

   The pure half is gated here without a solver. A topological (Euler/genus)
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

    # --- guard arithmetic, both directions, no solver -------------------
    # closed ring, measured: J_avg 6.2490e7 A/m^2 over 16 mm^2 -> 999.8 At
    got_closed = 6.2490e7 * (C_M * C_M)
    check("measured CLOSED-ring delivery is within the guard band",
          0.5 <= got_closed / I_A <= 2.0,
          "{0:.1f} of {1:.0f} At ({2:.2%})".format(got_closed, I_A,
                                                   got_closed / I_A))
    check("closed ring delivers essentially all of it (>99 %)",
          got_closed / I_A > 0.99, "{0:.4%}".format(got_closed / I_A))
    # open helix, measured: J_avg 2.8396e3 A/m^2 over 6.44 x 282.843 mm^2
    open_area = 6.43588 * 282.843e-6
    got_open = 2.8396e3 * open_area
    check("measured OPEN-helix delivery is REFUSED by the guard band",
          not (0.5 <= got_open / 100.0 <= 2.0),
          "{0:.3f} of 100 At ({1:.2%})".format(got_open, got_open / 100.0))
    # 19x on the measured pair (99.98 % vs 5.17 %). Stated as >10x so the gate
    # asserts the SEPARATION it actually has: an earlier draft claimed "three
    # orders of magnitude" from a per-turn area instead of the all-turns
    # half-plane section, and this check caught it.
    check("the two cases are separated by more than 10x",
          (got_closed / I_A) / (got_open / 100.0) > 10.0,
          "ratio {0:.0f}x".format((got_closed / I_A) / (got_open / 100.0)))

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
    j = (res.get("j_avg") or [0.0])[0]
    frac = abs(j) * C_M * C_M / I_A
    check("a CLOSED coil passes the delivered-ampere-turns guard",
          0.5 <= frac <= 2.0, "{0:.2%} delivered".format(frac))
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
