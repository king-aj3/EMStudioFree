# SPDX-License-Identifier: LGPL-2.1-or-later
"""Differential pair-to-pair coupling via mixed-mode reduction (ROADMAP §2
Cable Designer — the diff-pair extra).

Reduces a 4-conductor (+ common reference) per-unit-length system to
mixed-mode quantities and predicts differential-to-differential crosstalk
between two pairs, with the twisted-pair improvement model of RADC-TR-76-101
Vol V (McKnight & Paul). Inputs are the loop inductance matrix and Maxwell
capacitance matrix over the four conductors **(a1, a2, b1, b2)** against one
shared reference — exactly what :func:`coupling.widesep_l_matrix` /
:func:`coupling.c_matrix_from_l` (bare) or
:func:`electrostatics.bundle_c_mom` ``c_tl`` (insulated, inhomogeneous)
produce for a 5-conductor bundle with the reference removed.

**Conventions (pinned by the 2026-07-12 adversarial de-risk — every formula
below was verified to machine precision, 44/44 checks):**

* Mixed-mode variables: ``Vd = V1 - V2``, ``Vc = (V1 + V2)/2``,
  ``Id = (I1 - I2)/2``, ``Ic = I1 + I2`` (Bockelman & Eisenstadt 1995 power
  split). Ordering ``(dA, cA, dB, cB)``. The current transform is the inverse
  transpose of the voltage transform, ``T_I = (T_V^-1)^T`` — the matrices
  transform by CONGRUENCE (``L_mm = T_V L T_V^T``, ``C_mm = T_I C T_I^T``);
  reusing ``T_V`` for currents (a similarity) yields an asymmetric, power-
  violating L_mm (43 % wrong in the de-risk counterexample).
* ``Ldd = L11 + L22 - 2 L12`` is the PAIR-LOOP differential inductance
  (= 2 x the per-wire odd-mode ``L11 - L12`` for identical wires).
* ``Mdd = L13 - L14 - L23 + L24``; in the wide-separation forms every
  reference-conductor distance cancels, leaving
  ``Mdd = (mu0/2pi) ln(d14 d23 / (d13 d24))`` — pair-to-pair coupling is a
  pure geometry ratio.
* ``k_diff = Mdd / sqrt(Ldd_A Ldd_B)`` (general; |k| <= 1). The shortcut
  ``Mdd / (2 L_pair)`` is exact ONLY for identical pairs with ``L_pair`` the
  per-wire odd-mode inductance — up to ~13 % wrong otherwise.
* ``Cdd_AB = (C13 - C14 - C23 + C24) / 4`` (Maxwell entries). Relation to the
  ASTM D4566 pair-to-pair capacitance unbalance (direct/positive mutuals
  ``c_ij = -C_ij``): ``CUPP = (c13 + c24) - (c14 + c23) = -4 Cdd_AB``.
* Invariants (gated): ``Zdd = 2 Zodd``; ``Ldd Cdd = Lodd Codd = mu0 eps0
  eps_r`` for matched definition pairs — MIXED pairings are exactly 2x / 0.5x
  off.
* Crosstalk termination mapping: the diff-diff circuit takes DIFFERENTIAL
  resistances (50 ohm per wire to reference at each end = **100 ohm**
  differential) and the full differential source voltage; the balanced
  circuit has no shared return, so the common-impedance floor is 0.

**Twist model** (RADC-TR-76-101 Vol V, eqs 4-1..4-10/4-26/4-27/4-42/4-43,
verified on page images): the pair is a cascade of N half-twist loops with
abrupt transpositions. Inductive coupling enters the alternating sum
``XI_TWP = I1 - I2 + I3 - ...`` (eq 4-3) — zero for even N, one loop's worth
for odd N. The engine quotes the conservative **odd-N envelope 1/N** (the
even-N ideal null is a manufacturing accident: parity is worth ~70 dB in the
ideal cascade and vanishes with real helical twist). Capacitive unbalance
terms ADD regardless of twist for an unbalanced (grounded) receptor
(eqs 4-8/4-10 — the capacitive floor); BALANCED terminations null the floor
(eq 4-43 with c_G1 = c_G2). A receptor grounded at BOTH ends forms a ground
loop whose pickup twist cannot cancel (de-risk cascade: benefit collapses to
~1 dB) — flagged, not modeled. Model class: electrically short
(< lambda/20), magnitudes add, ~+/-3 dB vs the report's measurements.

Sources: RADC-TR-76-101 Vol V (DTIC ADA053559), McKnight & Paul, equations
and numeric claims verified on page images 2026-07-12 (10.25 dB twist benefit
at 50-ohm loads; ~0 dB at 1 kohm; ~275-ohm inductive/capacitive boundary;
the ~30 dB odd/even contrast is the report's COMPUTED Appendix-C case).
Bockelman & Eisenstadt, IEEE T-MTT 43(7) 1995 (mixed-mode definitions).
Full-MTL oracle: weak-coupling predictions agree with the exact 8x8 chain
solution to 0.010 % (NE) / 0.026 % (FE) at Lc/lambda = 6.7e-4.

Numpy only; FreeCAD/Qt-free. SI units.
"""
from __future__ import annotations

import math

import numpy as np

from emstudio.wire.coupling import crosstalk_weak

def pair_transform(n_pairs=2):
    """Voltage transform for ``n_pairs`` pairs, ordered (d1, c1, d2, c2, ...).

    Block-diagonal ``[[1, -1], [1/2, 1/2]]`` per pair; the matching current
    transform is ALWAYS ``(T_V^-1)^T`` (congruence — never reuse T_V for
    currents). This slice ships the 2-pair reduction; a future n-pair system
    tool (ROADMAP §7) inherits the convention from here.
    """
    t = np.zeros((2 * n_pairs, 2 * n_pairs))
    for p in range(n_pairs):
        t[2 * p, 2 * p] = 1.0
        t[2 * p, 2 * p + 1] = -1.0
        t[2 * p + 1, 2 * p] = 0.5
        t[2 * p + 1, 2 * p + 1] = 0.5
    return t


# voltage transform (dA, cA, dB, cB) <- (V1, V2, V3, V4); T_I = inv(T_V).T
_T_V = pair_transform(2)
_T_I = np.linalg.inv(_T_V).T

RECEPTOR_MODES = ("balanced", "unbalanced_single_ground",
                  "unbalanced_ground_loop")


def mixed_mode_transforms():
    """(T_V, T_I) with ``V_mm = T_V V``, ``I_mm = T_I I``, T_I = (T_V^-1)^T."""
    return _T_V.copy(), _T_I.copy()


def mixed_mode_matrices(l4, c4):
    """Congruence-transform 4x4 L (loop) and C (Maxwell) to mixed-mode form.

    Returns ``{"l_mm", "c_mm"}`` ordered (dA, cA, dB, cB). Both stay symmetric
    and, in a homogeneous medium, satisfy ``l_mm @ c_mm = mu0 eps0 eps_r I``.
    """
    l4 = np.asarray(l4, dtype=float)
    c4 = np.asarray(c4, dtype=float)
    if l4.shape != (4, 4) or c4.shape != (4, 4):
        raise ValueError("mixed-mode reduction needs 4x4 L and C matrices")
    return {"l_mm": _T_V @ l4 @ _T_V.T, "c_mm": _T_I @ c4 @ _T_I.T}


def diff_pair_coupling(l4, c4):
    """Differential quantities for pairs A=(1,2), B=(3,4) over a reference.

    Returns a dict of plain floats: ``ldd_a``/``ldd_b`` (H/m), ``mdd`` (H/m,
    as-given polarity), ``k_diff`` (geometric-mean normalization),
    ``cdd_a``/``cdd_b``/``cdd_ab`` (F/m), ``cupp_f_m`` (= -4 cdd_ab, ASTM
    direct convention), ``zdd_a_ohm``/``zdd_b_ohm`` (sqrt(Ldd/Cdd) TEM
    estimates), and the crosstalk-ready couplings ``lm_h_m`` (>= 0) /
    ``cm_f_m`` with ``polarity_flipped`` recording whether pair B was
    relabeled (b1<->b2) to make the inductive coupling positive.
    """
    mm = mixed_mode_matrices(l4, c4)
    l_mm, c_mm = mm["l_mm"], mm["c_mm"]
    ldd_a, ldd_b = float(l_mm[0][0]), float(l_mm[2][2])
    mdd = float(l_mm[0][2])
    cdd_a, cdd_b = float(c_mm[0][0]), float(c_mm[2][2])
    cdd_ab = float(c_mm[0][2])
    flip = mdd < 0.0
    sign = -1.0 if flip else 1.0
    return {
        "ldd_a": ldd_a,
        "ldd_b": ldd_b,
        "mdd": mdd,
        "k_diff": mdd / math.sqrt(ldd_a * ldd_b),
        "cdd_a": cdd_a,
        "cdd_b": cdd_b,
        "cdd_ab": cdd_ab,
        "cupp_f_m": -4.0 * cdd_ab,
        "zdd_a_ohm": math.sqrt(ldd_a / cdd_a) if cdd_a > 0.0 else float("inf"),
        "zdd_b_ohm": math.sqrt(ldd_b / cdd_b) if cdd_b > 0.0 else float("inf"),
        "lm_h_m": sign * mdd,
        "cm_f_m": -sign * cdd_ab,
        "polarity_flipped": flip,
    }


def xi_twp(n_half_twists):
    """Eq 4-3 alternating segment sum for unit currents: 0 even, 1 odd."""
    n = int(n_half_twists)
    if n < 0:
        raise ValueError("half-twist count must be >= 0")
    return n % 2


def xi_swp(n_segments):
    """Straight-pair same-sign segment sum for unit currents (eq 4-6): N."""
    n = int(n_segments)
    if n < 0:
        raise ValueError("segment count must be >= 0")
    return n


def half_twists_from_lay(length_m, lay_m):
    """Half-twist loop count N over ``length_m`` at lay (full-twist) pitch."""
    if lay_m <= 0.0:
        raise ValueError("lay length must be positive")
    return max(int(round(2.0 * float(length_m) / float(lay_m))), 0)


def twist_factors(n_half_twists, receptor="balanced"):
    """(f_ind, f_cap, warnings): coupling multipliers for N half-twist loops.

    Conservative odd-N envelope: one uncancelled half-twist section survives,
    so the inductive term scales by 1/N (the even-N ideal zero is parity luck
    — ~70 dB in the abrupt-transposition cascade — and is NOT quoted).
    ``receptor``:

    * ``"balanced"`` — differential (floating/balanced) terminations: the
      capacitive unbalance term alternates too (eq 4-43) -> same 1/N.
    * ``"unbalanced_single_ground"`` — one wire grounded at ONE end: the
      grounded wire shorts alternate charge sources (eq 4-8) -> the
      capacitive floor keeps its full straight-pair value (eqs 4-10/4-26).
    * ``"unbalanced_ground_loop"`` — grounded at BOTH ends: the ground loop's
      common-mode pickup is untouched by twist (de-risk cascade: ~1 dB total
      benefit) -> no reduction at all, warning issued.
    """
    if receptor not in RECEPTOR_MODES:
        raise ValueError("receptor must be one of {0}".format(RECEPTOR_MODES))
    n = int(n_half_twists)
    if n < 0:
        raise ValueError("half-twist count must be >= 0")
    warnings = []
    env = 1.0 if n == 0 else 1.0 / n
    if receptor == "balanced":
        f_ind, f_cap = env, env
    elif receptor == "unbalanced_single_ground":
        f_ind, f_cap = env, 1.0
        if n > 0:
            warnings.append(
                "unbalanced receptor: twist cannot reduce the capacitive "
                "floor (RADC Vol V eqs 4-8/4-10) — balance the terminations "
                "to null it (eq 4-43)")
    else:
        f_ind, f_cap = 1.0, 1.0
        if n > 0:
            warnings.append(
                "receptor grounded at both ends: the ground loop's pickup is "
                "not reduced by twisting (de-risk cascade: ~1 dB) — use a "
                "single-point ground or balanced terminations")
    return f_ind, f_cap, warnings


def diff_crosstalk(l4, c4, length_m, rs=100.0, rl=100.0, rne=100.0,
                   rfe=100.0, freq_hz=1e6, n_half_twists=0,
                   receptor="balanced"):
    """Differential-to-differential weak-coupling crosstalk between pairs.

    ``rs``/``rl``/``rne``/``rfe`` are DIFFERENTIAL terminations (ohm): 50 ohm
    per wire to reference at each end of a pair = 100 ohm differential. The
    ratios are referenced to the full differential source voltage. The
    balanced diff-diff circuit has no shared return conductor, so no
    common-impedance term. Twist (``n_half_twists`` half-twist loops on the
    receptor pair, ``receptor`` mode) applies :func:`twist_factors` to the
    couplings; results carry both the untwisted and twisted predictions plus
    the improvement in dB. Validity: weak coupling, electrically short line
    (the report's low-frequency model class, ~+/-3 dB; the full-MTL oracle
    puts the untwisted formulas at 0.01-0.03 % of exact for
    Lc/lambda <= 1e-3).
    """
    cq = diff_pair_coupling(l4, c4)
    base = crosstalk_weak(cq["lm_h_m"], cq["cm_f_m"], length_m, rs, rl,
                          rne, rfe, freq_hz, r_common_ohm_m=0.0)
    f_ind, f_cap, warnings = twist_factors(n_half_twists, receptor)
    out = dict(cq)
    out.update({
        "untwisted": base,
        "n_half_twists": int(n_half_twists),
        "receptor": receptor,
        "f_inductive": f_ind,
        "f_capacitive": f_cap,
        "warnings": warnings,
        "short_line_max_hz": base["short_line_max_hz"],
    })
    # computed unconditionally: at n = 0 the factors are exactly 1.0, so the
    # twisted dict EQUALS base numerically but is a distinct object (an
    # in-place consumer edit must never corrupt the untwisted record).
    # improvement can be NEGATIVE: with opposite-sign lm/cm couplings the
    # untwisted terms partially cancel and shrinking only lm makes NE worse.
    tw = crosstalk_weak(cq["lm_h_m"] * f_ind, cq["cm_f_m"] * f_cap,
                        length_m, rs, rl, rne, rfe, freq_hz,
                        r_common_ohm_m=0.0)
    out["twisted"] = tw
    out["improvement_ne_db"] = base["vne_db"] - tw["vne_db"]
    out["improvement_fe_db"] = base["vfe_db"] - tw["vfe_db"]
    return out
