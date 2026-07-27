# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: per-strand current sharing (multi-port FastHenry).

Physics-by-symmetry gates:

* A **6-strand ring** (no center strand) is fully symmetric under rigid-rotation
  twisting — every strand must carry the same current at every frequency
  (imbalance -> 1.0). Any significant spread would indicate a solver/plumbing bug.

* A **7-strand bundle** (center + ring) is NOT symmetric: the center strand links
  different internal flux than the ring strands, and rigid bunching cannot transpose
  center against ring. At high frequency the center strand must carry measurably
  different current — the real physical effect (and the reason multi-level Type 2/3
  constructions exist).

Run:  python3 tests/validation/wire_current_sharing.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0} - {1}  {2}".format("ok  " if ok else "FAIL", name, detail))
    if not ok:
        FAILURES.append(name)


def main():
    from emstudio.wire import current_sharing, geometry

    a_s = 0.25e-3
    length = 0.04
    pitch = 0.02

    paths7 = geometry.twisted_bundle_paths(7, a_s, length, pitch, points_per_turn=8)
    paths6 = paths7[1:]  # drop the center strand -> symmetric ring

    print("EMStudio current-sharing validation")
    print("-----------------------------------")

    res6 = current_sharing.analyze_paths(paths6, a_s, fmin=1e4, fmax=1e6, ndec=1, nhinc=5)
    print("  ring workdir:", res6[0]["workdir"])
    for r in res6:
        check(
            "6-ring symmetric sharing @ {0:.0e} Hz".format(r["freq"]),
            r["imbalance"] < 1.02,
            "imbalance {0:.4f}".format(r["imbalance"]),
        )

    res7 = current_sharing.analyze_paths(paths7, a_s, fmin=1e4, fmax=1e6, ndec=1, nhinc=5)
    print("  7-strand workdir:", res7[0]["workdir"])
    hi7 = res7[-1]
    print("  7-strand @ {0:.0e} Hz: imbalance {1:.4f}, currents {2}".format(
        hi7["freq"], hi7["imbalance"],
        " ".join("{0:.3f}".format(c) for c in hi7["currents_norm"])))
    check(
        "7-strand center-strand effect at HF",
        hi7["imbalance"] > 1.03,
        "imbalance {0:.4f} (must exceed ring's)".format(hi7["imbalance"]),
    )
    check(
        "7-strand ring subset still symmetric",
        max(hi7["currents_norm"][1:]) / min(hi7["currents_norm"][1:]) < 1.02,
        "ring strands equal among themselves",
    )

    # --- aggregated (per-bundle/per-cable) view: AJ's EMStudio-wide rescope ---
    from emstudio.solvers.fasthenry.runner import run_parallel_sweep

    freqs, mats, _wd = run_parallel_sweep(paths7, a_s, 5.8e7, 1e6, 1e6, 1, 5, "per_path")
    g = current_sharing.grouped_metrics(mats[0], [[0], [1, 2, 3, 4, 5, 6]])
    print("  grouped @1 MHz: center-group share {0:.3f} (expected {1:.3f}), "
          "ring-group share {2:.3f}".format(g["share"][0], g["expected"][0], g["share"][1]))
    check("grouped: center group under-carries", g["normalized"][0] < 0.5,
          "normalized {0:.3f}".format(g["normalized"][0]))
    check("grouped: ring group compensates", 1.0 < g["normalized"][1] < 1.25,
          "normalized {0:.3f}".format(g["normalized"][1]))

    # --- per-bundle sharing of a construction's final cabling (symmetric ring) ---
    from emstudio.wire import litz, units

    con = litz.make_type(4, units.awg_to_m(30), [7, 5])  # 5 bundles around a core
    res = current_sharing.analyze_construction(con, fmin=1e5, fmax=1e5, ndec=1)
    check("construction per-bundle sharing (symmetric ring)",
          res[0]["imbalance"] < 1.02,
          "imbalance {0:.4f} across {1}".format(res[0]["imbalance"], res[0]["level"]))

    # --- ampacity estimate sanity ---
    big = litz.make_type(6, units.awg_to_m(38), [70, 13, 20])  # AJ's real cable
    i_dc = big.ampacity(1.0)
    i_hf = big.ampacity(1e6)
    print("  ampacity 18,200-strand Type 6: DC {0:.0f} A, 1 MHz {1:.0f} A".format(i_dc, i_hf))
    check("ampacity magnitude sane (DC)", 200.0 <= i_dc <= 2000.0, "{0:.0f} A".format(i_dc))
    check("ampacity decreases with frequency", i_hf < i_dc,
          "DC {0:.0f} A > 1 MHz {1:.0f} A".format(i_dc, i_hf))

    print("-----------------------------------")
    if FAILURES:
        print("CURRENT-SHARING GATE FAILED: {0}".format(FAILURES))
        return 1
    print("CURRENT-SHARING GATE PASSED")
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
        raise SystemExit("current-sharing validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("current-sharing validation failed")
    sys.exit(0)
