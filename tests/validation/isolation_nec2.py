# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: antenna-to-antenna isolation matrix via NEC2 (co-site §5-A).

Two parallel side-by-side half-wave dipoles separated by 0.5 lambda. The extracted
mutual impedance and isolation are checked against the Balanis parallel-dipole
mutual-impedance table (Z21 ~= -12.5 - j29.9 ohm at d = 0.5 lambda) and the
reference nec2c 1.3.1 run.

Run:  freecadcmd tests/validation/isolation_nec2.py
Pass: exit 0 and 'ISOLATION GATE PASSED'.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    import FreeCAD

    import numpy as np

    from emstudio.cosite import isolation
    from emstudio.objects import query
    from emstudio.templates import cosite_pair

    doc = FreeCAD.newDocument("isolation_gate")
    ana = cosite_pair.makeCositePair(doc, f0_hz=300e6, spacing_frac=0.5)
    solver = query.get_solvers(ana)[0]

    res = isolation.isolation_matrix(ana, solver)
    z = res["z"]
    s = res["s"]
    z21 = z[1, 0]
    s21_db = 20.0 * np.log10(abs(s[1, 0]))
    iso_db = res["isolation_db"][0, 1]

    print("isolation: Z11 = {0:.3f}{1:+.3f}j, Z21 = {2:.3f}{3:+.3f}j ohm".format(
        z[0, 0].real, z[0, 0].imag, z21.real, z21.imag))
    print("isolation: |S21| = {0:.3f} dB (isolation {1:.3f} dB), reciprocity err {2:.2e}".format(
        s21_db, iso_db, res["reciprocity_err"]))

    # --- gates (reference nec2c 1.3.1: |S21| -13.78 dB, Z21 -15.1 - j28.0) ---
    # primary: |S21| is the most stable quantity (0.06 dB spread over seg/radius)
    assert -14.8 <= s21_db <= -12.8, \
        "|S21| {0:.2f} dB outside -13.78 +/- 1.0".format(s21_db)
    assert abs(iso_db - (-s21_db)) < 1e-9, "isolation must be -|S21| dB"
    # Z-matrix sanity vs Balanis (-12.5 - j29.9), +/-15% on |Z21|
    mag21 = abs(z21)
    assert 27.0 <= mag21 <= 37.0, "|Z21| {0:.2f} outside 27-37 ohm".format(mag21)
    assert z21.real < 0 and z21.imag < 0, "Z21 sign wrong at 0.5 lambda"
    # driven dipole is resonant: Z11 ~ 72 ohm, near-zero reactance
    assert 66.0 <= z[0, 0].real <= 80.0, "Z11 {0:.1f} not ~72 ohm".format(z[0, 0].real)
    assert abs(z[0, 0].imag) < 8.0, "Z11 reactance {0:.1f} not near zero".format(z[0, 0].imag)
    # reciprocity is a structural self-check (Z12 == Z21)
    assert res["reciprocity_err"] < 1e-6, \
        "reciprocity broken: {0:.2e}".format(res["reciprocity_err"])

    # isolation feeds the interference calculator as a per-pair dict
    pairs = isolation.isolation_pairs_db(res)
    assert abs(pairs[(0, 1)] - iso_db) < 1e-9 and abs(pairs[(1, 0)] - iso_db) < 1e-9, \
        "isolation_pairs_db mismatch"

    print("ISOLATION GATE PASSED")
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
        raise SystemExit("isolation validation failed")
    sys.exit(0)
