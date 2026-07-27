# SPDX-License-Identifier: LGPL-2.1-or-later
"""Bundle conductor-to-conductor coupling: per-unit-length L/R/C matrices and
weak-coupling crosstalk (ROADMAP §2 Cable Designer, phase C — electrical slice).

Two validated routes, split by the documented validity boundary:

* **Analytic wide-separation** (Paul, *Analysis of Multiconductor Transmission
  Lines* 2e, eq. 5.23; one member is the reference conductor 0)::

    l_ii = (mu0/2pi) ln( d_i0^2 / (r_w0 r_wi) )
    l_ij = (mu0/2pi) ln( d_i0 d_j0 / (d_ij r_w0) )

  and the homogeneous-medium companions C0 = mu0 eps0 inv(L) (eq. 5.24a).
  Valid when EVERY pairwise (separation / conductor radius) >= ~4: the printed
  two-wire error is 5.3 % at s/rw = 4, 2.7 % at 5, ~2 % at Paul's ribbon-cable
  benchmark (whose printed exact matrices gate this module to <= 2.5 % per
  entry). Touching INSULATED wires with wall >= conductor radius satisfy this;
  touching BARE wires do NOT (error grows to > 100 %) — use FastHenry there.

* **FastHenry loop matrices** for any spacing (proximity/skin correct): the
  existing ``per_path`` partial N x N impedance matrix is transformed to loop
  form against a chosen reference conductor,
  ``Zl[i][j] = Zp[i][j] - Zp[i][ref] - Zp[ref][j] + Zp[ref][ref]``
  (verified against explicit-loop decks to 0.01 %), with the equal-area-square
  GMD diagonal correction (+(mu0/2pi) ln(0.792385/0.778801) = +3.458 nH/m per
  self term — the square's self-GMD vs the round wire's a e^-0.25) and
  two-length end-effect subtraction for per-unit-length values.

**C-matrix honesty** (the two documented traps): (1) the identity C =
mu eps inv(L) needs the ELECTROSTATIC-consistent L — the wide-separation/HF
form, never a DC (uniform-current) L, whose internal-inductance content makes
C wrong by ~20 %; this module derives C only from the analytic L. (2) It holds
for a homogeneous medium (bare wires) ONLY: Paul's benchmark shows insulation
raises C entries by 50-66 % with PER-ENTRY effective permittivities (1.664 vs
1.507 — a scalar eps_eff errs ~10 %, a homogeneous eps_r fill ~110 %). For
INSULATED bundles use :mod:`emstudio.wire.electrostatics` (``bundle_c_mom``),
which solves the inhomogeneous electrostatic problem directly by Paul's
method-of-moments (RIBBON.FOR method) — it reproduces Paul's printed insulated
ribbon C to the digit, rather than reporting the bare value with a caveat.

**Crosstalk** — Paul's inductive-capacitive weak-coupling model (MTL 2e eqs.
10.29/10.30/10.34) for a generator/receptor/reference conductor triple with
terminations RS, RL (generator) and RNE, RFE (receptor)::

    VNE/VS = jw [ RNE/(RNE+RFE) lm Lc / (RS+RL)
                  + RNE RFE/(RNE+RFE) cm Lc RL/(RS+RL) ]  (+ common-impedance)
    VFE/VS = jw [ -RFE/(RNE+RFE) lm Lc / (RS+RL)
                  + RNE RFE/(RNE+RFE) cm Lc RL/(RS+RL) ]

with lm the loop mutual inductance, cm = -C[g][r] (positive), Lc the line
length. Valid for electrically short (Lc << lambda), weakly coupled lines.
Gated against Paul's printed ribbon-cable numbers (MNE = 5.5449 ns, -49.16 dB
@ 100 kHz, 46.2/23.1 mV trapezoid peaks, the 1.94 mV common-impedance floor,
the lm/cm dominance rule) and the LearnEMC -23 / -40 / -34 dB examples.

Sources (2026-07-09 de-risk research + adversarial cross-check): Paul MTL 2e
Tables 5.4-5.6 (p. 187-188, verified on page images) + eqs. 5.23/5.24/10.29/
10.30/10.34; RADC-TR-76-101 Vol VII (1977) independent printing; FastHenry
USER'S GUIDE v3.0 + live measurements on fasthenry 3.0.1.

Numpy for the matrix algebra; FreeCAD/Qt-free. SI units.
"""
from __future__ import annotations

import math

import numpy as np

MU0 = 4.0e-7 * math.pi
EPS0 = 8.8541878128e-12
C0_LIGHT = 299792458.0

# equal-area square self-GMD correction back to a round conductor (H/m per
# partial SELF inductance term): (mu0/2pi) ln(0.447049*sqrt(pi) / e^-0.25)
GMD_SELF_CORRECTION_H_M = MU0 / (2.0 * math.pi) * math.log(0.792385 / 0.778801)

WIDESEP_MIN_RATIO = 4.0   # printed validity: s/rw >= 4 (5.3 % two-wire error)


def min_separation_ratio(positions, radii):
    """Smallest pairwise (centre separation / larger conductor radius)."""
    worst = float("inf")
    n = len(positions)
    for i in range(n):
        for j in range(i + 1, n):
            s = math.hypot(positions[i][0] - positions[j][0],
                           positions[i][1] - positions[j][1])
            worst = min(worst, s / max(radii[i], radii[j]))
    return worst


def widesep_l_matrix(positions, radii, ref=0):
    """Loop per-unit-length inductance matrix (H/m), Paul eq. 5.23.

    ``positions``/``radii``: conductor centres (m) and CONDUCTOR radii (m);
    conductor ``ref`` is the reference (return). Returns the (n-1) x (n-1)
    matrix over the non-reference conductors in input order. Wide-separation
    validity: every pairwise s/rw >= ~4 (use ``min_separation_ratio``).
    """
    idx = [k for k in range(len(positions)) if k != ref]
    x0, y0 = positions[ref]
    r0 = radii[ref]

    def d(a, b):
        return math.hypot(positions[a][0] - positions[b][0],
                          positions[a][1] - positions[b][1])

    n = len(idx)
    L = np.empty((n, n))
    for a, i in enumerate(idx):
        di0 = d(i, ref)
        L[a][a] = MU0 / (2.0 * math.pi) * math.log(di0 * di0 / (r0 * radii[i]))
        for b, j in enumerate(idx):
            if b <= a:
                continue
            dj0 = d(j, ref)
            L[a][b] = L[b][a] = MU0 / (2.0 * math.pi) * math.log(
                di0 * dj0 / (d(i, j) * r0))
    return L


def c_matrix_from_l(l_matrix, eps_r=1.0):
    """Maxwell C matrix (F/m) via the homogeneous TEM identity mu eps inv(L).

    ``l_matrix`` must be the ELECTROSTATIC-consistent (wide-separation / HF)
    loop inductance matrix — never a DC uniform-current L (its internal-
    inductance content corrupts C by ~20 %). ``eps_r`` is the HOMOGENEOUS
    surrounding medium: bare wires in air = 1.0. Insulated bundles violate
    homogeneity (Paul's benchmark: entries move 50-66 % with per-entry
    effective permittivities) — treat the result as the bare-geometry value.
    """
    return MU0 * EPS0 * float(eps_r) * np.linalg.inv(np.asarray(l_matrix))


def maxwell_mutual_pf_m(c_matrix, i, j):
    """Datasheet 'mutual capacitance' between conductors i, j: -C_ij (>0)."""
    return -float(np.asarray(c_matrix)[i][j]) * 1e12


def reduce_generalized_c(script_c, ref=0):
    """Generalized (free-space-referenced) Maxwell matrix -> TL C (eq. 5.21).

    C_ij = scriptC_ij - rowsum_i * colsum_j / grandtotal, over the
    non-reference conductors. Gated against Paul Table 5.4 -> 5.5.
    """
    sc = np.asarray(script_c, dtype=float)
    idx = [k for k in range(sc.shape[0]) if k != ref]
    tot = sc.sum()
    rows = sc.sum(axis=1)
    cols = sc.sum(axis=0)
    return np.array([[sc[i][j] - rows[i] * cols[j] / tot for j in idx]
                     for i in idx])


def partial_to_loop(z_partial, ref=0):
    """Partial N x N impedance matrix -> loop matrix vs conductor ``ref``.

    ``Zl[i][j] = Zp[i][j] - Zp[i][ref] - Zp[ref][j] + Zp[ref][ref]`` — each
    loop is conductor i out / reference back. Verified against explicit
    FastHenry loop decks to 0.01 %.
    """
    zp = np.asarray(z_partial)
    idx = [k for k in range(zp.shape[0]) if k != ref]
    return np.array([[zp[i][j] - zp[i][ref] - zp[ref][j] + zp[ref][ref]
                      for j in idx] for i in idx])


def fasthenry_loop_matrices(positions, radii, freq_hz=1.0, length_m=0.5,
                            nhinc=1, sigma_s_per_m=5.8e7, ref=0,
                            workdir=None, line_callback=None):
    """Per-unit-length loop R (ohm/m) + L (H/m) matrices via FastHenry.

    Straight parallel conductors at ``positions`` with CONDUCTOR ``radii``,
    run twice (``length_m`` and ``length_m/2``) in the existing ``per_path``
    partial mode; the two-length subtraction removes end effects, the
    equal-area-square GMD diagonal correction restores round-wire self terms,
    and the partial->loop transform references conductor ``ref``. Accurate at
    ANY spacing (proximity included), unlike the wide-separation forms. Use
    ``nhinc >= 5`` (odd) for skin-effect frequencies; 1 is exact at DC.
    """
    from emstudio.solvers.fasthenry.runner import run_parallel_sweep

    def partial(length):
        paths = [[(x, y, 0.0), (x, y, length)] for x, y in positions]
        freqs, mats, _wd = run_parallel_sweep(
            paths, list(radii), sigma_s_per_m, freq_hz, freq_hz, 1,
            nhinc, "per_path", workdir=workdir, line_callback=line_callback)
        zp = np.asarray(mats[0], dtype=complex)
        # restore round-wire self-GMD on the partial diagonal
        for i in range(zp.shape[0]):
            zp[i, i] += 2j * math.pi * freqs[0] * GMD_SELF_CORRECTION_H_M * length
        return zp

    z_full = partial_to_loop(partial(length_m), ref)
    z_half = partial_to_loop(partial(length_m / 2.0), ref)
    dz = (z_full - z_half) / (length_m / 2.0)
    return dz.real, dz.imag / (2.0 * math.pi * freq_hz)


def bundle_coupling_analytic(positions, radii, ref=0):
    """Wide-separation loop L + identity C over a set of bundle conductors.

    Returns a dict: ``l_matrix`` (H/m), ``c_matrix`` (F/m, Maxwell form,
    bare/homogeneous), ``conductors`` (input indices in matrix order, i.e.
    all except ``ref``), ``min_s_over_rw`` and ``widesep_ok`` (>= 4 — below
    it the closed forms over-estimate L by >= 5 % and FastHenry should supply
    L instead), ``ref_r_dc_ohm_m`` (reference-conductor resistance for the
    common-impedance floor).
    """
    L = widesep_l_matrix(positions, radii, ref)
    ratio = min_separation_ratio(positions, radii)
    return {
        "l_matrix": L,
        "c_matrix": c_matrix_from_l(L),
        "conductors": [k for k in range(len(positions)) if k != ref],
        "min_s_over_rw": ratio,
        "widesep_ok": ratio >= WIDESEP_MIN_RATIO,
        "ref_r_dc_ohm_m": 1.0 / (5.8e7 * math.pi * radii[ref] ** 2),
    }


def crosstalk_weak(lm_h_m, cm_f_m, length_m, rs=50.0, rl=50.0, rne=50.0,
                   rfe=50.0, freq_hz=1e6, r_common_ohm_m=0.0):
    """Paul's inductive-capacitive weak-coupling crosstalk (MTL 2e 10.29/30/34).

    ``lm_h_m``: loop mutual inductance between the generator and receptor
    circuits (H/m); ``cm_f_m``: mutual capacitance = -C[g][r] (F/m, positive);
    ``r_common_ohm_m``: shared-reference-conductor resistance for the
    common-impedance floor. Returns MNE/MFE (s), |VNE/VS|, |VFE/VS| (+ dB),
    the common-impedance term, the lm/cm dominance report, and the
    electrically-short validity length. Weak coupling, Lc << lambda.
    """
    lc = float(length_m)
    div_ne = rne / (rne + rfe)
    div_fe = rfe / (rne + rfe)
    rpar = rne * rfe / (rne + rfe)
    ind_ne = div_ne * lm_h_m * lc / (rs + rl)
    cap = rpar * cm_f_m * lc * rl / (rs + rl)
    mne = ind_ne + cap
    mfe = -div_fe * lm_h_m * lc / (rs + rl) + cap
    w = 2.0 * math.pi * float(freq_hz)
    vne = w * abs(mne)
    vfe = w * abs(mfe)
    v_ci = div_ne * (r_common_ohm_m * lc / (rs + rl))
    z_crit = lm_h_m / cm_f_m if cm_f_m > 0.0 else float("inf")
    return {
        "mne_s": mne,
        "mfe_s": mfe,
        "mne_inductive_s": ind_ne,
        "mne_capacitive_s": cap,
        "vne_over_vs": vne,
        "vfe_over_vs": vfe,
        "vne_db": 20.0 * math.log10(max(vne, 1e-300)),
        "vfe_db": 20.0 * math.log10(max(vfe, 1e-300)),
        "common_impedance_floor": v_ci,
        "inductive_dominant_ne": rfe * rl < z_crit,
        "lm_over_cm_ohm2": z_crit,
        "freq_hz": float(freq_hz),
        "short_line_max_hz": C0_LIGHT / (10.0 * lc),
    }
