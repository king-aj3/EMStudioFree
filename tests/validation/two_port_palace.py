# SPDX-License-Identifier: LGPL-2.1-or-later
"""SOLVER gate: a live two-excitation Palace solve really does make a 2-port.

``two_port_excitation`` (FAST) proves the config shape and the merge without
Palace. This proves the thing that one cannot: **that Palace labels its
excitation-2 columns the way ``parser.parse_sparams`` expects.** Until this
ran, a shipped ``.s2p`` rested on an assumption about another project's output
format.

⚠ THE TRAP THIS GATE IS BUILT AROUND. The obvious test — solve a uniform coax
and check the matrix — CANNOT detect a mislabelling, because a uniform line is
electrically symmetric: S11 == S22 and S12 == S21 by physics, so swapping the
columns is invisible. The proof therefore does not come from the values. It
comes from the RAW per-excitation files: exciting port 1 must produce exactly
S[1][1] and S[2][1], exciting port 2 exactly S[1][2] and S[2][2], and the two
sets must be DISJOINT. Those headers name the terms explicitly, so they answer
the question the physics cannot.

The symmetry and reciprocity checks stay, but as what they actually are — a
sanity check on the solve, not evidence about labelling.

Measured 2026-08-19 on Palace v0.17.0 (Linux, ~/opt/palace): a 3-point
2-excitation coax solve takes about 100 s.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np                                            # noqa: E402

FAILURES = []

A_MM, B_MM, L_MM = 0.5, 1.65, 20.0        # ~50 ohm air coax, as coax_palace


def check(msg, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + msg + (" — " + detail if detail else ""))
    if not ok:
        FAILURES.append(msg)


def _terms_in(csv_path):
    """The (observed, excited) pairs a Palace port-S.csv actually reports."""
    import re
    with open(csv_path, encoding="utf-8") as fh:
        header = fh.readline()
    return sorted({(int(a), int(b))
                   for a, b in re.findall(r"\|S\[(\d+)\]\[(\d+)\]\|", header)})


def main():
    from emstudio.solvers.palace import run_coax

    res = run_coax(a_mm=A_MM, b_mm=B_MM, length_mm=L_MM, eps_r=1.0,
                   f1_ghz=2.0, f2_ghz=6.0, step_ghz=2.0, order=2,
                   elem_mm=0.5, full_smatrix=True)
    wd = res.meta["workdir"]
    print("  (workdir: {0}, {1:.0f} s)".format(wd, res.meta["duration_s"]))

    # -- 1. THE LABELLING PROOF: disjoint, correctly-keyed raw output --------
    e1 = os.path.join(wd, "postpro_e1", "port-S.csv")
    e2 = os.path.join(wd, "postpro_e2", "port-S.csv")
    check("each excitation wrote its own port-S.csv",
          os.path.isfile(e1) and os.path.isfile(e2))
    t1, t2 = _terms_in(e1), _terms_in(e2)
    check("exciting port 1 reports exactly column 1 (S11, S21)",
          t1 == [(1, 1), (2, 1)], "got %s" % (t1,))
    check("exciting port 2 reports exactly column 2 (S12, S22)",
          t2 == [(1, 2), (2, 2)], "got %s" % (t2,))
    check("the two runs are DISJOINT — neither could overwrite the other",
          not (set(t1) & set(t2)))

    # -- 2. the merge assembled a complete matrix ---------------------------
    check("the result completes order 2", res.max_complete_ports() == 2,
          "missing %s" % (res.missing_s_terms(2),))
    check("all four terms are present and finite",
          all(res.s_at(i, j) is not None and np.all(np.isfinite(res.s_at(i, j)))
              for i in (1, 2) for j in (1, 2)))

    # -- 3. physics sanity (NOT labelling evidence — see the docstring) -----
    s11, s21 = res.s_at(1, 1), res.s_at(2, 1)
    s12, s22 = res.s_at(1, 2), res.s_at(2, 2)
    s11_db = 20.0 * np.log10(np.maximum(np.abs(s11), 1e-12))
    s21_db = 20.0 * np.log10(np.maximum(np.abs(s21), 1e-12))
    check("|S11| low — the line is matched", s11_db.max() < -20.0,
          "max %.1f dB" % s11_db.max())
    check("|S21| ~ 0 dB — the line is lossless", np.abs(s21_db).max() < 1.0,
          "max dev %.3f dB" % np.abs(s21_db).max())
    check("reciprocal: S12 == S21 (passive structure)",
          np.allclose(s12, s21, rtol=0.02, atol=1e-3),
          "max |diff| %.2e" % np.abs(s12 - s21).max())
    check("symmetric: S11 == S22 (uniform line, both ends alike)",
          np.allclose(s11, s22, rtol=0.05, atol=1e-3),
          "max |diff| %.2e" % np.abs(s11 - s22).max())

    # -- 4. and the point of all of it: a real .s2p -------------------------
    path = os.path.join(tempfile.mkdtemp(), "coax.s2p")
    check("it writes a 2-port Touchstone", res.write_touchstone(path) == 2)
    rows = [l for l in open(path, encoding="utf-8")
            if not l.startswith(("!", "#")) and l.strip()]
    check("...with one row per frequency point", len(rows) == len(res.freq))
    check("...each freq + four RI pairs", all(len(r.split()) == 9 for r in rows))

    print()
    if FAILURES:
        print("two_port_palace: %d FAILED" % len(FAILURES))
        raise SystemExit("two_port_palace FAILED")
    print("two_port_palace: all checks passed")
    return 0


if __name__ == "__main__" or "FreeCAD" not in sys.modules:
    main()
