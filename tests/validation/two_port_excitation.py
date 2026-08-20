# SPDX-License-Identifier: LGPL-2.1-or-later
"""FAST gate: two excitations make a real 2-port, and a mismatch is refused.

A driven solve excites ONE port and measures the rest, which yields the single
COLUMN of the S-matrix belonging to that port. A full 2x2 is therefore two
solves on the SAME mesh — one per excitation — joined by
``sparams.merge_excitations``. This gate pins the parts of that chain which do
not need Palace installed:

* the config builders drive exactly one port, with ``Excitation == Index``,
  and write to per-excitation output directories so the second run cannot
  overwrite the first's ``port-S.csv``;
* the merge joins two columns into a complete matrix;
* it REFUSES a frequency mismatch instead of resampling, because two sweeps on
  different grids are two different experiments and interpolating one onto the
  other would fabricate a .s2p that looks measured;
* and the joined result actually writes a 2-port Touchstone, which is the
  whole point of the exercise.

⚠ The live end-to-end solve is SOLVER tier and needs Palace, which is not
installed on the box this was written on. What is proven here is the config
shape and the join; what is NOT proven here is that Palace labels its
excitation-2 columns the way the parser expects. Run the Palace SOLVER gates
on a machine that has it before trusting a shipped .s2p.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np                                            # noqa: E402

from emstudio.post.sparams import (                           # noqa: E402
    SweepResult, merge_excitations)
from emstudio.solvers.palace import writer                    # noqa: E402

FAILURES = []


def check(msg, ok):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        FAILURES.append(msg)


def _exc(ports):
    return [(p["Index"], p.get("Excitation")) for p in ports]


def main():
    # -- 1. set_excitation drives exactly one port --------------------------
    ports = [{"Index": 1}, {"Index": 2}, {"Index": 3}]
    writer.set_excitation(ports, 2)
    check("exactly one port carries Excitation",
          sum(1 for p in ports if "Excitation" in p) == 1)
    check("...it is the requested one, and Excitation == Index",
          ports[1].get("Excitation") == 2)
    writer.set_excitation(ports, 1)
    check("re-driving CLEARS the previous excitation (no two driven ports)",
          _exc(ports) == [(1, 1), (2, None), (3, None)])

    # -- 2. both config builders honour it, into separate outputs -----------
    for label, build, key in (
            ("wave", lambda ep, out: writer.build_driven_config(
                "m.msh", 8.0, 12.0, 0.5, excite_port=ep, output=out),
             "WavePort"),
            ("coax", lambda ep, out: writer.build_lumped_coax_config(
                "m.msh", 1.0, 5.0, 1.0, 1.0, 3.0, excite_port=ep, output=out),
             "LumpedPort")):
        c1 = build(1, "postpro_e1")
        c2 = build(2, "postpro_e2")
        check("%s config: excitation 1 drives port 1 only" % label,
              _exc(c1["Boundaries"][key]) == [(1, 1), (2, None)])
        check("%s config: excitation 2 drives port 2 only" % label,
              _exc(c2["Boundaries"][key]) == [(1, None), (2, 2)])
        check("%s config: the two runs write to DIFFERENT outputs" % label,
              c1["Problem"]["Output"] != c2["Problem"]["Output"])

    # -- 3. the merge builds a complete matrix ------------------------------
    f = np.array([1.0e9, 2.0e9, 3.0e9])
    s11 = np.array([0.11 + 0j, 0.12 + 0j, 0.13 + 0j])
    s21 = np.array([0.21 + 0j, 0.22 + 0j, 0.23 + 0j])
    s12 = np.array([0.31 + 0j, 0.32 + 0j, 0.33 + 0j])
    s22 = np.array([0.41 + 0j, 0.42 + 0j, 0.43 + 0j])
    runA = (f, {(1, 1): s11, (2, 1): s21})      # excite port 1 -> column 1
    runB = (f, {(1, 2): s12, (2, 2): s22})      # excite port 2 -> column 2

    fr, smat = merge_excitations([runA, runB])
    check("merging the two columns gives all four terms",
          sorted(smat.keys()) == [(1, 1), (1, 2), (2, 1), (2, 2)])
    check("...with the frequency grid preserved", np.allclose(fr, f))
    check("...and each term kept its own values (no column crossed over)",
          np.allclose(smat[(2, 1)], s21) and np.allclose(smat[(1, 2)], s12))

    # -- 4. it refuses rather than fabricating ------------------------------
    refused = False
    try:
        merge_excitations([runA, (np.array([1.0e9, 2.0e9, 4.0e9]),
                                  {(2, 2): s22})])
    except ValueError as exc:
        refused = "frequency grid" in str(exc)
    check("a frequency-grid mismatch is REFUSED, not interpolated", refused)

    refused = False
    try:
        merge_excitations([runA, (f[:2], {(2, 2): s22[:2]})])
    except ValueError as exc:
        refused = True
    check("a different point COUNT is refused too", refused)

    refused = False
    try:
        merge_excitations([runA, (f, {(1, 1): s11 * 2.0})])
    except ValueError as exc:
        refused = "not distinct" in str(exc)
    check("two runs claiming the same term (both drove port 1) is refused",
          refused)

    # -- 5. the point of the exercise: it writes a real .s2p ----------------
    z0 = 50.0
    zin = z0 * (1.0 + s11) / (1.0 - s11)
    res = SweepResult(f, zin, z0=z0, s11=s11, meta={"backend": "palace"},
                      s_others={k: v for k, v in smat.items() if k != (1, 1)})
    check("the joined result completes order 2", res.max_complete_ports() == 2)
    check("...with nothing missing", res.missing_s_terms(2) == [])

    path = os.path.join(tempfile.mkdtemp(), "merged.s2p")
    check("it writes a 2-port Touchstone", res.write_touchstone(path) == 2)
    row = [l for l in open(path, encoding="utf-8")
           if not l.startswith(("!", "#")) and l.strip()][0].split()
    check("the row is freq + four RI pairs", len(row) == 9)
    vals = [complex(float(row[1 + 2 * k]), float(row[2 + 2 * k]))
            for k in range(4)]
    check("in Touchstone order S11 S21 S12 S22, values intact",
          all(abs(a - b) < 1e-12
              for a, b in zip(vals, [s11[0], s21[0], s12[0], s22[0]])))

    # -- 6. one excitation must still NOT produce a 2-port ------------------
    only1 = SweepResult(f, zin, z0=z0, s11=s11, meta={},
                        s_others={(2, 1): s21})
    check("a single-excitation run still completes only order 1",
          only1.max_complete_ports() == 1)

    print()
    if FAILURES:
        print("two_port_excitation: %d FAILED" % len(FAILURES))
        raise SystemExit("two_port_excitation FAILED")
    print("two_port_excitation: all checks passed")
    return 0


if __name__ == "__main__" or "FreeCAD" not in sys.modules:
    main()
