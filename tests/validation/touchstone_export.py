# SPDX-License-Identifier: LGPL-2.1-or-later
"""FAST gate: the Touchstone writer exports what was solved and nothing more.

WHAT THIS DEFENDS. Both full-wave backends excite exactly ONE port per run —
openEMS refuses otherwise and Palace's driven config marks port 1 excited with
the rest passive. That yields one COLUMN of the S-matrix: S11, S21, S31 … and
no information at all about S12 or S22. Reciprocity does not close the gap
either; it would give S12 = S21 for a passive structure and still leave S22
unknown.

So the failure this gate exists to prevent is a plausible one: someone sees
S21 plotted beside S11, concludes a 2-port file is a formatting change away,
and ships a .s2p whose last two columns are zeros or a mirrored S21. A VNA
comparison would read those as measured data. The writer must REFUSE.

The second thing it defends is the opposite mistake. The order must be chosen
from the largest COMPLETE matrix, not the largest port index mentioned —
otherwise today's S11+S21 result (which mentions port 2) would stop writing
the .s1p it has always written.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np                                            # noqa: E402

from emstudio.post.sparams import SweepResult                 # noqa: E402

FAILURES = []


def check(msg, ok):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        FAILURES.append(msg)


def _result(**kw):
    f = np.array([1.0e9, 2.0e9, 3.0e9])
    z = np.array([50 + 0j, 60 + 5j, 45 - 3j])
    return SweepResult(f, z, meta={"backend": "gate"}, **kw)


def _cols(path):
    for line in open(path, encoding="utf-8"):
        if line.startswith(("!", "#")) or not line.strip():
            continue
        return line.split()
    return []


def main():
    tmp = tempfile.mkdtemp()

    # -- 1. the field exists unconditionally ---------------------------------
    r = _result()
    so = getattr(r, "s_others", None)          # getattr ON PURPOSE: the whole
    check("s_others exists on a bare result (no AttributeError path)",
          isinstance(so, dict) and so == {})   # point is that it need not be

    # -- 2. one-port stays one-port -----------------------------------------
    p = os.path.join(tmp, "one.s1p")
    n = r.write_touchstone(p)
    check("S11 alone writes a 1-port file", n == 1)
    check("1-port row is freq + one RI pair (3 columns)", len(_cols(p)) == 3)

    # -- 3. TODAY'S CASE: S11 + S21, one excitation --------------------------
    s21 = np.array([0.10 + 0.01j, 0.20 + 0.02j, 0.30 + 0.03j])
    r = _result(s_others={(2, 1): s21})
    check("a one-excitation 2-port MENTIONS port 2", r.s_matrix_ports() == 2)
    check("...but only COMPLETES order 1", r.max_complete_ports() == 1)
    check("missing terms are exactly S12 and S22",
          r.missing_s_terms(2) == [(1, 2), (2, 2)])

    p = os.path.join(tmp, "today.s1p")
    try:
        wrote = r.write_touchstone(p)          # must not raise: this is the
    except Exception as exc:                   # path the export button takes
        wrote = "raised %s: %s" % (type(exc).__name__, exc)
    check("unqualified export still writes 1-port (no regression) [got %s]"
          % wrote, wrote == 1)

    bad = os.path.join(tmp, "bad.s2p")
    refused, why = False, "it returned normally and WROTE THE FILE"
    try:
        r.write_touchstone(bad, n_ports=2)
    except ValueError as exc:
        refused = "S12" in str(exc) and "S22" in str(exc)
        why = "ValueError, terms named: %s" % refused
    except Exception as exc:                   # a TypeError from indexing a
        why = ("raised %s, not a clean refusal: %s"    # None column means it
               % (type(exc).__name__, exc))            # TRIED to write it
    check("an explicit 2-port request is REFUSED, naming the missing terms "
          "[%s]" % why, refused)
    check("...and no partial file is left behind", not os.path.exists(bad))

    # -- 4. a complete matrix writes a real .s2p -----------------------------
    s12 = np.array([0.11 + 0.01j, 0.21 + 0.02j, 0.31 + 0.03j])
    s22 = np.array([0.40 + 0.04j, 0.50 + 0.05j, 0.60 + 0.06j])
    r = _result(s_others={(2, 1): s21, (1, 2): s12, (2, 2): s22})
    check("a full matrix completes order 2", r.max_complete_ports() == 2)
    p = os.path.join(tmp, "full.s2p")
    check("it writes a 2-port file", r.write_touchstone(p) == 2)

    cols = _cols(p)
    check("2-port row is freq + four RI pairs (9 columns)", len(cols) == 9)

    # Column ORDER is the classic Touchstone trap: S11 S21 S12 S22, with S21
    # BEFORE S12. Reading the file back and comparing against the distinct
    # values above is the only way to catch a transpose.
    vals = [complex(float(cols[1 + 2 * k]), float(cols[2 + 2 * k]))
            for k in range(4)]
    expect = [r.s11[0], s21[0], s12[0], s22[0]]
    check("column order is S11, S21, S12, S22 (S21 before S12)",
          all(abs(a - b) < 1e-12 for a, b in zip(vals, expect)))

    # A transpose would swap columns 2 and 3; prove the check can see it.
    check("...and S21 != S12 in this fixture, so the order check has teeth",
          abs(s21[0] - s12[0]) > 1e-9)

    # -- 5. the header declares the reference impedance ----------------------
    hdr = [l for l in open(p, encoding="utf-8") if l.startswith("#")][0]
    check("header carries the R reference", "R 50" in hdr)

    print()
    if FAILURES:
        print("touchstone_export: %d FAILED" % len(FAILURES))
        raise SystemExit("touchstone_export FAILED")
    print("touchstone_export: all checks passed")
    return 0


if __name__ == "__main__" or "FreeCAD" not in sys.modules:
    main()
