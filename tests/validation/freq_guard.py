# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the quasi-static frequency-validity guard.

Pass: exit 0 and 'FREQ-GUARD GATE PASSED'.

The Elmer magnetics and FastHenry R/L solvers are magneto-quasistatic / PEEC:
they drop the displacement current and are only valid while the structure is
electrically small (largest dimension < lambda/10). This gate checks that the
guard (emstudio.solvers.validity) stays SILENT inside that regime and WARNS
outside it, and that the physics of the threshold is correct.

Pure python3 — no solver run.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    from emstudio.solvers import validity

    print("EMStudio quasi-static frequency-validity guard gate")

    # A 10 cm coil at a typical WPT/induction frequency is deeply quasi-static.
    L = 0.10  # m
    w = validity.electrical_size_warning(100e3, L)
    check("silent for a 10 cm coil at 100 kHz (deeply quasi-static)", w is None,
          "" if w is None else "unexpected warning")
    w = validity.electrical_size_warning(1e6, L)
    check("silent for a 10 cm coil at 1 MHz", w is None,
          "" if w is None else "unexpected warning")

    # The same coil at microwave/mmWave is electrically large -> must warn.
    w40 = validity.electrical_size_warning(40e9, L)
    check("WARNS for a 10 cm coil at 40 GHz (electrically huge)", bool(w40),
          "warning present" if w40 else "no warning!")
    check("warning explains the quasi-static limit + points to full-wave",
          bool(w40) and "quasi-static" in w40 and
          ("Palace" in w40 or "openEMS" in w40),
          (w40 or "")[:80] + "…")

    # The lambda/10 boundary is physically correct: for a 0.10 m object the
    # ceiling is c/(10*L) = ~299.8 MHz. Silent just below, warns just above.
    f_ceiling = C0 / (10.0 * L)  # ~2.998e8 Hz
    below = validity.electrical_size_warning(f_ceiling * 0.9, L)
    above = validity.electrical_size_warning(f_ceiling * 1.1, L)
    check("silent just below the lambda/10 ceiling ({0:.1f} MHz)".format(f_ceiling / 1e6),
          below is None, "" if below is None else "warned too early")
    check("warns just above the lambda/10 ceiling", bool(above),
          "boundary at ~{0:.1f} MHz for 0.10 m".format(f_ceiling / 1e6))

    # Degenerate / unknown inputs never warn (no false alarms).
    check("no warning for unknown geometry (max_dim=0)",
          validity.electrical_size_warning(40e9, 0.0) is None)
    check("no warning for zero frequency",
          validity.electrical_size_warning(0.0, L) is None)

    # Axisymmetric model -> max dimension: a body with r1=50 mm is a 100 mm dia.
    dim = validity.axi_model_max_dim_m(
        {"bodies": [{"r0": 40.0, "r1": 50.0, "z0": -20.0, "z1": 20.0}]})
    check("axi max-dim = diameter (2*r1) when it dominates",
          abs(dim - 0.100) < 1e-9, "{0:.4f} m".format(dim))
    dim2 = validity.axi_model_max_dim_m(
        {"bodies": [{"r0": 1.0, "r1": 5.0, "z0": -60.0, "z1": 60.0}]})
    check("axi max-dim = axial height when it dominates",
          abs(dim2 - 0.120) < 1e-9, "{0:.4f} m".format(dim2))

    if FAILURES:
        print("FREQ-GUARD GATE FAILED: {0}".format(FAILURES))
        return 1
    print("FREQ-GUARD GATE PASSED")
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
        raise SystemExit("freq-guard validation failed")
    sys.exit(0)
