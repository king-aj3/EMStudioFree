# SPDX-License-Identifier: LGPL-2.1-or-later
"""SOLVER gate: a live two-excitation openEMS run really does make a 2-port.

The openEMS counterpart of ``two_port_palace``. openEMS solves ONE excitation
per FDTD run by construction, so a full 2x2 is two simulations: run 1 drives
port 1 in the workdir (exactly as a normal run always has), run 2 drives port 2
in ``exc2/``.

⚠ SAME TRAP AS THE PALACE GATE. The notch filter is a symmetric two-port, so
S11 == S22 and S12 == S21 by physics and a swapped-column mislabelling would
be INVISIBLE in the values. The proof is therefore structural: run 1's
directory must contain the column-1 files and run 2's the column-2 files, and
those sets must be disjoint. openEMS names them ``sparam_<to>_<from>.csv``, so
the filenames answer what the numbers cannot.

Geometry is the same notch filter as ``msl_notch_openems`` — see that gate for
why trace-aware meshing is what makes these numbers physical at all.

⚠ Two FDTD runs. Expect roughly twice that gate's wall time.
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

FAILURES = []


def check(msg, ok, detail=""):
    line = ("  ok   " if ok else "  FAIL ") + msg + (" — " + detail if detail else "")
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage(line + "\n")
    except Exception:                                          # noqa: BLE001
        print(line)
    if not ok:
        FAILURES.append(msg)


def _sparams_in(d):
    out = []
    for path in sorted(glob.glob(os.path.join(d, "sparam_*_*.csv"))):
        base = os.path.basename(path)[len("sparam_"):-len(".csv")]
        try:
            out.append(tuple(int(t) for t in base.split("_")))
        except ValueError:
            pass
    return sorted(out)


def main():
    import numpy as np
    import FreeCAD

    from emstudio.solvers import openems
    from emstudio.templates import msl_filter

    doc = FreeCAD.newDocument("msl_2port_gate")
    try:
        ana = msl_filter.makeNotchFilter(doc)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]
        result = openems.run(ana, solver, full_smatrix=True)
    finally:
        FreeCAD.closeDocument(doc.Name)

    wd = result.meta["workdir"]
    check("the run reports two excitations",
          result.meta.get("excitations") == 2)

    # -- 1. THE STRUCTURAL PROOF -------------------------------------------
    sub = os.path.join(wd, "exc2")
    check("the second excitation ran in its own directory", os.path.isdir(sub))
    check("run 1 kept the original workdir layout (port_1.csv)",
          os.path.isfile(os.path.join(wd, "port_1.csv")))
    check("run 2 wrote its own driven-port file (exc2/port_2.csv)",
          os.path.isfile(os.path.join(sub, "port_2.csv")))

    t1, t2 = _sparams_in(wd), _sparams_in(sub)
    check("run 1 produced column-1 transmission only (2,1)", t1 == [(2, 1)],
          "got %s" % (t1,))
    check("run 2 produced column-2 transmission only (1,2)", t2 == [(1, 2)],
          "got %s" % (t2,))
    check("the two runs are DISJOINT — neither overwrote the other",
          not (set(t1) & set(t2)))

    # -- 2. the merged matrix ----------------------------------------------
    check("the result completes order 2", result.max_complete_ports() == 2,
          "missing %s" % (result.missing_s_terms(2),))
    for k in ((1, 1), (2, 1), (1, 2), (2, 2)):
        v = result.s_at(*k)
        check("S%d%d present and finite" % k,
              v is not None and np.all(np.isfinite(v)))

    # -- 3. physics sanity (NOT labelling evidence) ------------------------
    s11, s21 = result.s_at(1, 1), result.s_at(2, 1)
    s12, s22 = result.s_at(1, 2), result.s_at(2, 2)
    worst = max(np.abs(s11).max(), np.abs(s21).max(),
                np.abs(s12).max(), np.abs(s22).max())
    check("PASSIVE — no |S| term exceeds ~0 dB", worst <= 1.03,
          "worst |S| %.4f" % worst)
    check("reciprocal: S12 ~ S21", np.allclose(s12, s21, rtol=0.10, atol=0.02),
          "max |diff| %.3e" % np.abs(s12 - s21).max())
    check("symmetric: S11 ~ S22 (the filter is end-to-end alike)",
          np.allclose(s11, s22, rtol=0.15, atol=0.03),
          "max |diff| %.3e" % np.abs(s11 - s22).max())

    # -- 4. the deliverable -------------------------------------------------
    s2p = os.path.join(wd, "port_1.s2p")
    check("the run wrote a 2-port Touchstone, not a mislabelled .s1p",
          os.path.isfile(s2p), s2p)
    if os.path.isfile(s2p):
        rows = [l for l in open(s2p, encoding="utf-8")
                if not l.startswith(("!", "#")) and l.strip()]
        check("...one row per frequency, freq + four RI pairs",
              len(rows) == len(result.freq)
              and all(len(r.split()) == 9 for r in rows))

    if FAILURES:
        raise SystemExit("two_port_openems FAILED: %d check(s)" % len(FAILURES))
    try:
        import FreeCAD as _F
        _F.Console.PrintMessage("two_port_openems: all checks passed\n")
    except Exception:                                          # noqa: BLE001
        print("two_port_openems: all checks passed")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    main()
