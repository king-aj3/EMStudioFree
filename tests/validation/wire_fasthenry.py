# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gates: wire analytics + FastHenry backend.

Runs under plain python3 (no FreeCAD needed):  python3 tests/validation/wire_fasthenry.py

Gate A — analytics self-consistency:
  * exact skin factor matches the low-frequency expansion (a/delta = 0.5) and the
    high-frequency asymptote (a/delta = 4 and 10),
  * proximity kernel H(x) matches its series limit and is monotonic.

Gate B — FastHenry vs exact Bessel skin effect, straight round wire:
  tolerance 10% (equal-area square cross-section carries a known ~5% high bias in
  the skin-limited regime; verified 2026-07-05).

Gate C — 7-strand Type-1 litz bundle, FastHenry vs the analytic bundle model:
  Rdc within 3%; Rac/Rdc within 25% in the transition region (the analytic model is
  an isolated-bundle approximation; FastHenry resolves the true strand fields).
"""

import math
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


def gate_a_analytics():
    from emstudio.wire import litz

    a = 1e-3
    # low-frequency expansion 1 + (a/delta)^4/48 at a/delta = 0.5
    delta = a / 0.5
    f = 1.0 / (math.pi * litz.MU0 * litz.SIGMA_CU * delta ** 2)
    exact = litz.round_wire_ac_factor(f, a)
    approx = 1.0 + 0.5 ** 4 / 48.0
    check("skin low-f expansion", abs(exact - approx) / approx < 0.001,
          "exact {0:.5f} vs {1:.5f}".format(exact, approx))

    # high-frequency asymptote at a/delta = 4 and 10
    for ratio in (4.0, 10.5):
        delta = a / ratio
        f = 1.0 / (math.pi * litz.MU0 * litz.SIGMA_CU * delta ** 2)
        exact = litz.round_wire_ac_factor(f, a)
        asym = ratio / 2.0 + 0.25 + 3.0 / (32.0 * ratio)
        check("skin asymptote a/d={0:g}".format(ratio),
              abs(exact - asym) / asym < 0.01,
              "exact {0:.4f} vs asym {1:.4f}".format(exact, asym))

    # proximity kernel: series limit + monotonicity + continuity at the x=0.5 seam
    h_series = litz._proximity_h(0.4)
    check("prox series limit", abs(h_series - 0.4 ** 4 / 256.0) < 1e-12)
    seam_lo, seam_hi = litz._proximity_h(0.4999), litz._proximity_h(0.5001)
    check("prox seam continuity", abs(seam_hi - seam_lo) / seam_lo < 0.05,
          "{0:.3e} vs {1:.3e}".format(seam_lo, seam_hi))
    xs = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
    hs = [litz._proximity_h(x) for x in xs]
    check("prox monotonic", all(h2 > h1 for h1, h2 in zip(hs, hs[1:])),
          " ".join("{0:.3g}".format(h) for h in hs))


def gate_b_round_wire():
    from emstudio.solvers import fasthenry
    from emstudio.wire import litz

    a = 1e-3
    length = 0.1
    path = [[(0.0, 0.0, 0.0), (length, 0.0, 0.0)]]
    freqs, rs, _ls, workdir = fasthenry.run_wire_paths(
        path, a, fmin=1e3, fmax=1e6, ndec=1, nhinc=11
    )
    rdc = length / (litz.SIGMA_CU * math.pi * a ** 2)
    print("  round wire workdir:", workdir)
    for f, r in zip(freqs, rs):
        fh_factor = r / rdc
        bessel = litz.round_wire_ac_factor(f, a)
        err = abs(fh_factor - bessel) / bessel
        check(
            "FastHenry vs Bessel @ {0:.0e} Hz".format(f),
            err < 0.10,
            "FH {0:.3f} vs exact {1:.3f} ({2:.1%})".format(fh_factor, bessel, err),
        )


def gate_c_litz_bundle():
    from emstudio.solvers import fasthenry
    from emstudio.wire import geometry, litz

    # 7 x 0.5 mm strands, 20 mm twist pitch, 40 mm sample (2 full twists).
    # Discretization chosen for tractability: 8 pts/turn, 7x7 filaments — the
    # dense-coupled problem grows brutally with segment x filament count.
    a_s = 0.25e-3
    n = 7
    length = 0.04
    paths = geometry.twisted_bundle_paths(
        n, a_s, length, twist_pitch_m=0.02, points_per_turn=8
    )
    freqs, rs, _ls, workdir = fasthenry.run_wire_paths(
        paths, a_s, fmin=1e4, fmax=3e5, ndec=1, nhinc=7
    )
    print("  litz bundle workdir:", workdir)

    # helical strand length correction for Rdc comparison
    c0 = geometry.hex_positions(n, 2 * a_s * 1.05)
    import statistics

    twist_factors = []
    for cx, cy in c0:
        r = math.hypot(cx, cy)
        helix_len = math.sqrt(1.0 + (2 * math.pi * r / 0.02) ** 2)
        twist_factors.append(helix_len)
    tf = statistics.mean(twist_factors)

    con = litz.LitzConstruction(strand_diameter_m=2 * a_s, ops=[n], packing_factor=0.78)
    rdc_model = con.rdc_per_meter(twist_factor=tf) * length
    err_dc = abs(rs[0] / con.ac_factor(freqs[0]) - rdc_model) / rdc_model
    check("litz Rdc vs model", err_dc < 0.03,
          "FH-derived {0:.3e} vs model {1:.3e}".format(rs[0] / con.ac_factor(freqs[0]), rdc_model))

    for f, r in zip(freqs, rs):
        fh_factor = r / (rs[0] / con.ac_factor(freqs[0]))
        model = con.ac_factor(f)
        err = abs(fh_factor - model) / model
        check(
            "litz Fac @ {0:.0e} Hz".format(f),
            err < 0.25,
            "FH {0:.3f} vs model {1:.3f} ({2:.1%})".format(fh_factor, model, err),
        )


def gate_d_bundle_coupling():
    """Gate D — FastHenry loop L/R matrices for bundle coupling (§2-C).

    Three parallel round wires at 0/2/4 mm (a = 0.5 mm), wire 0 = reference,
    DC (1 Hz): the per_path partial matrix, GMD diagonal correction and
    partial->loop transform + two-length end-effect subtraction must land on
    the round-wire uniform-current analytics (Grover/Paul):
      L11' = (mu0/pi)(ln(d10/a) + 1/4);  M12' = (mu0/2pi)(ln(d10*d20/(d12*a)) + 1/4)
    (the acosh form is the HF limit and must NOT be the DC reference — the
    2026-07-09 de-risk measured these on fasthenry 3.0.1 to +-0.02-0.07 %).
    """
    import numpy as np

    from emstudio.wire import coupling as cp

    pos = [(0.0, 0.0), (2e-3, 0.0), (4e-3, 0.0)]
    rad = [0.5e-3] * 3
    R, L = cp.fasthenry_loop_matrices(pos, rad, freq_hz=1.0, length_m=0.5,
                                      nhinc=1)
    mu0 = 4e-7 * math.pi
    l11 = mu0 / math.pi * (math.log(2.0 / 0.5) + 0.25)
    l22 = mu0 / math.pi * (math.log(4.0 / 0.5) + 0.25)
    m12 = mu0 / (2 * math.pi) * (math.log(2.0 * 4.0 / (2.0 * 0.5)) + 0.25)
    check("loop L11' vs round-wire DC analytic (0.3%)",
          abs(L[0][0] - l11) / l11 < 0.003,
          "{0:.5g} vs {1:.5g} H/m".format(L[0][0], l11))
    check("loop L22' vs analytic (0.3%)", abs(L[1][1] - l22) / l22 < 0.003)
    check("loop M12' vs analytic (0.5%)", abs(L[0][1] - m12) / m12 < 0.005,
          "{0:.5g} vs {1:.5g} H/m".format(L[0][1], m12))
    check("loop matrix symmetric", abs(L[0][1] - L[1][0]) / L[0][1] < 1e-6)
    rdc = 1.0 / (5.8e7 * math.pi * 0.5e-3 ** 2)
    check("loop R' diag = 2x wire Rdc (0.5%)",
          abs(R[0][0] - 2 * rdc) / (2 * rdc) < 0.005)
    check("loop R' off-diag = shared-reference Rdc (0.5%)",
          abs(R[0][1] - rdc) / rdc < 0.005,
          "{0:.5f} vs {1:.5f} ohm/m".format(R[0][1], rdc))
    # per-path radii plumbing: a mixed-radius pair must break the symmetry
    R2, L2 = cp.fasthenry_loop_matrices([(0.0, 0.0), (3e-3, 0.0)],
                                        [0.5e-3, 1.0e-3], freq_hz=1.0,
                                        length_m=0.5, nhinc=1)
    l_mixed = mu0 / (2 * math.pi) * (math.log(3.0 / 0.5) + math.log(3.0 / 1.0)
                                     + 0.5)
    check("mixed-radius pair loop L' vs analytic (0.5%)",
          abs(L2[0][0] - l_mixed) / l_mixed < 0.005,
          "{0:.5g} vs {1:.5g} H/m".format(L2[0][0], l_mixed))


def main():
    print("EMStudio wire/FastHenry validation")
    print("----------------------------------")
    gate_a_analytics()
    gate_b_round_wire()
    gate_c_litz_bundle()
    gate_d_bundle_coupling()
    print("----------------------------------")
    if FAILURES:
        print("WIRE GATE FAILED: {0}".format(FAILURES))
        return 1
    print("WIRE GATE PASSED")
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
        raise SystemExit("wire validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("wire validation failed")
    sys.exit(0)
