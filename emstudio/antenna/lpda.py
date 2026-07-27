# SPDX-License-Identifier: LGPL-2.1-or-later
"""LPDA (log-periodic dipole array) synthesis — Carrel design equations
(Element Designer slice E5).

An LPDA is ONE element (a single feed port) per the §1 scope contract, even
with N dipoles: the crossed boom feeder is part of the element. This module
turns a band (f_lo-f_hi) + a gain target (or explicit tau/sigma) into a fully
dimensioned array: element lengths/positions, apex angle, element count, boom
length, and the crossed-feeder characteristic impedance for a target mean
input resistance.

Sources — standard public physics verified from PRIMARY/OPEN sources (full
provenance + live nec2c experiments in docs/upstream/lpda-carrel-anchors.md;
NO copyrighted book text was used):

* **Carrel (1961)** design equation set: tau/sigma geometry, the optimum
  spacing line sigma_opt = 0.243*tau - 0.051, cot(alpha) = 4*sigma/(1-tau),
  active-region bandwidth B_ar = 1.1 + 7.7*(1-tau)^2*cot(alpha), structure
  bandwidth B_s = B*B_ar, N = 1 + ln(B_s)/ln(1/tau), boom length
  L = (lambda_max/4)*(1 - 1/B_s)*cot(alpha), and the feeder design
  Za = 120*[ln(h/a) - 2.25], sigma' = sigma/sqrt(tau),
  Z0 = R0^2/(8*sigma'*Za) + R0*sqrt[(R0/(8*sigma'*Za))^2 + 1].
* **Butson & Thompson (1976) correction**: Carrel's original contour labels
  read 1.0 dB high (his directivity came from Kraus's beamwidth-product
  approximation); the GAIN_TABLE below carries the CORRECTED calibration
  (the Balanis-figure class), plus the documented h/a thickness
  sensitivity (-0.2 dB per doubling vs the charts' h/a = 125). Verify
  reports the achieved NEC2 gain.
* **Worked-example anchor** (the classic 54-216 MHz VHF design): tau 0.865 /
  sigma 0.158 -> cot(alpha) 4.68, B_ar 1.757, B_s 7.03, N_exact 14.44,
  boom ~5.5-5.6 m — reproduced to the digit by this module and gated in
  ``tests/validation/element_designer.py``; live nec2c lands VSWR(65) <= 1.55
  across the whole band, ~8.3-8.7 dBi mid-band, F/B ~19-20 dB.

Pure-python, Qt-free, FreeCAD-free; results are dicts of plain floats (house
rule). All SI.
"""
from __future__ import annotations

import math

C0 = 299792458.0
DBD_OFFSET = 2.15

#: Carrel chart validity (warn outside; the charts were drawn for these
#: ranges — anchors doc §4: gains 6.5-11 dBi, tau 0.76-0.98, sigma 0.04-0.22).
TAU_MIN, TAU_MAX = 0.76, 0.98
SIGMA_MIN = 0.04

#: Calibration offset between Carrel's ORIGINAL contour labels and the
#: Butson-Thompson CORRECTED contours (Balanis Fig-11.13 class): the same
#: curve geometry labeled exactly 1.0 dB lower (verified curve-for-curve —
#: anchors doc). De Vito-Stracca: the real optimism grows to ~2 dB at the
#: high-gain corner / high Z0 / thin elements (warned below).
BT_DERATE_DB = 1.0

#: Optimum-sigma design line: CORRECTED directivity (dBi, Butson-Thompson
#: calibration) -> tau, ascending. Graph-read contour vertices on the
#: sigma_opt line (+-0.005 in tau), verified from open reproductions of the
#: corrected chart (anchors doc §4). The 8.0 dBi row is the classic
#: worked-example anchor (tau 0.865); live nec2c achieves 8.3-8.7 dBi
#: mid-band for it (free space, ideal TL feeder).
GAIN_TABLE = [
    (7.0, 0.780),
    (7.5, 0.822),
    (8.0, 0.865),
    (8.5, 0.897),
    (9.0, 0.919),
    (9.5, 0.931),
    (10.0, 0.944),
    (10.5, 0.955),
    (11.0, 0.967),
]

#: Corrected-contour crossings at sigma = 0.06 (gain dBi -> tau) — the
#: below-optimum falloff anchors used to interpolate explicit low-sigma
#: designs (anchors doc §4).
SIGMA006_TABLE = [
    (6.5, 0.852),
    (7.0, 0.887),
    (7.5, 0.920),
    (8.0, 0.939),
    (8.5, 0.957),
]

#: Carrel's charts are drawn for element half-length/radius h/a = 125;
#: directivity shifts ~-0.2 dB per DOUBLING of h/a (valid 50 < h/a < 10000).
HA_REF = 125.0
HA_SLOPE_DB_PER_DOUBLING = -0.2


def sigma_opt(tau):
    """Carrel's optimum relative spacing for a scale factor tau."""
    return 0.243 * float(tau) - 0.051


def _interp(x, pairs, flip=False):
    """Piecewise-linear y(x) over [(x, y), ...] sorted by x; clamped."""
    pts = [(b, a) for a, b in pairs] if flip else list(pairs)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= x <= x2:
            frac = (x - x1) / (x2 - x1) if x2 > x1 else 0.0
            return y1 + frac * (y2 - y1)
    return pts[-1][1]


def _tau_for_gain(gain_dbi, warnings):
    """tau on the optimum-sigma line for a corrected design gain."""
    g = float(gain_dbi)
    lo_g = GAIN_TABLE[0][0]
    hi_g = GAIN_TABLE[-1][0]
    if g > hi_g + 0.25:
        raise ValueError(
            "target {0:g} dBi exceeds the LPDA design contours (max {1:g} "
            "dBi corrected); stacking/arraying is section-7 "
            "territory".format(g, hi_g))
    if g < lo_g - 0.25:
        warnings.append(
            "target {0:g} dBi is below the contour range ({1:g} dBi floor) "
            "— using the lowest-gain optimum design".format(g, lo_g))
    g_used = min(max(g, lo_g), hi_g)
    if g_used >= 9.5:
        warnings.append(
            "high-gain corner: even the corrected contours can read "
            "~0.5-1 dB high there (De Vito-Stracca — worse for high feeder "
            "Z0 / thin elements); solver-verify")
    return _interp(g_used, GAIN_TABLE), g_used


def _gain_for_tau_sigma(tau, sigma, warnings):
    """Corrected design gain for an explicit (tau, sigma): the optimum-line
    value at tau, interpolated down toward the verified sigma = 0.06
    contour crossings when sigma sits below the optimum line."""
    g_opt = _interp(tau, GAIN_TABLE, flip=True)
    s_opt = sigma_opt(tau)
    if sigma >= s_opt - 5e-4:
        return g_opt
    g_006 = _interp(tau, SIGMA006_TABLE, flip=True)
    span = max(s_opt - 0.06, 1e-6)
    frac = min(1.0, max(0.0, (s_opt - sigma) / span))
    g = g_opt + frac * (g_006 - g_opt)
    if sigma < 0.06:
        warnings.append(
            "sigma {0:.3f} is below the verified contour anchors "
            "(0.06) — the design gain is extrapolated; solver-verify".format(
                sigma))
    return g


def design_lpda(f_lo_hz, f_hi_hz, gain_dbi=None, tau=None, sigma=None,
                wire_d_m=0.010, r0_ohm=65.0, n_max=40):
    """Synthesize an LPDA from a band + a gain target (or explicit tau/sigma).

    :param f_lo_hz: low band edge (Hz). The longest element is lambda/2 here.
    :param f_hi_hz: high band edge (Hz).
    :param gain_dbi: target free-space directivity (dBi, on the CORRECTED
        Butson-Thompson contour calibration). Picks tau on the
        optimum-sigma line. Use this OR ``tau`` + ``sigma``.
    :param tau: explicit scale factor (0 < tau < 1), with ``sigma``.
    :param sigma: explicit relative spacing d_n/(2*l_n), with ``tau``.
    :param wire_d_m: element conductor diameter (m) — drives Za via h/a.
    :param r0_ohm: target mean input resistance (drives the feeder Z0).
    :param n_max: safety cap on the element count.

    Returns a dict (see the bottom of this function). Raises ``ValueError``
    on a bad request.
    """
    f_lo = float(f_lo_hz)
    f_hi = float(f_hi_hz)
    if f_lo <= 0 or f_hi <= 0:
        raise ValueError("band edges must be positive frequencies")
    if f_hi <= f_lo:
        raise ValueError("f_hi must be above f_lo (got {0:g} <= {1:g} Hz)".format(
            f_hi, f_lo))
    if (gain_dbi is None) == (tau is None and sigma is None):
        raise ValueError("give exactly one of gain_dbi or tau+sigma")

    warnings = []
    if gain_dbi is not None:
        tau, picked_gain = _tau_for_gain(float(gain_dbi), warnings)
        sigma = sigma_opt(tau)
        gain_carrel = picked_gain + BT_DERATE_DB
        gain_out = picked_gain
        on_opt = True
    else:
        if tau is None or sigma is None:
            raise ValueError("explicit designs need BOTH tau and sigma")
        tau = float(tau)
        sigma = float(sigma)
        if not 0.0 < tau < 1.0:
            raise ValueError("tau must be in (0, 1); got {0:g}".format(tau))
        if sigma <= 0.0:
            raise ValueError("sigma must be positive; got {0:g}".format(sigma))
        on_opt = abs(sigma - sigma_opt(tau)) < 5e-4
        gain_out = _gain_for_tau_sigma(tau, sigma, warnings)
        gain_carrel = gain_out + BT_DERATE_DB

    if tau < TAU_MIN or tau > TAU_MAX:
        warnings.append(
            "tau = {0:.3f} is outside the Carrel chart range "
            "({1:g}-{2:g}) — the design equations are extrapolated; "
            "solver-verify".format(tau, TAU_MIN, TAU_MAX))
    if sigma < SIGMA_MIN:
        warnings.append(
            "sigma = {0:.3f} is below the Carrel chart range (>= {1:g}) — "
            "expect reduced gain/F-B; solver-verify".format(sigma, SIGMA_MIN))
    if sigma > sigma_opt(tau) + 5e-4:
        warnings.append(
            "sigma = {0:.3f} exceeds sigma_opt = {1:.3f} — beyond the "
            "optimum line the pattern can break up; solver-verify".format(
                sigma, sigma_opt(tau)))

    B = f_hi / f_lo
    cot_alpha = 4.0 * sigma / (1.0 - tau)
    alpha_deg = math.degrees(math.atan(1.0 / cot_alpha))
    b_ar = 1.1 + 7.7 * (1.0 - tau) ** 2 * cot_alpha
    b_s = B * b_ar
    n_exact = 1.0 + math.log(b_s) / math.log(1.0 / tau)
    # the documented ARRL/Stroobandt rounding rule: fractional part > ~0.3
    # rounds UP, else DOWN (live NEC2 shows N vs N+1 nearly identical at the
    # band edges — anchors doc §2)
    n = int(n_exact) + (1 if (n_exact - int(n_exact)) > 0.3 else 0)
    if n < 2:
        raise ValueError(
            "the requested band/geometry needs fewer than 2 elements — not "
            "an LPDA (B = {0:.3g}); use a dipole/Yagi instead".format(B))
    if n > int(n_max):
        raise ValueError(
            "N = {0} elements exceeds n_max = {1} (tau {2:g} over bandwidth "
            "{3:g}); raise n_max, lower the gain target, or split the "
            "band".format(n, int(n_max), tau, B))

    lam_max = C0 / f_lo
    l1 = lam_max / 2.0
    lengths = [l1 * tau ** k for k in range(n)]
    positions = [0.0]
    for k in range(n - 1):
        positions.append(positions[-1] + 2.0 * sigma * lengths[k])
    boom_span = positions[-1]
    boom_carrel = (lam_max / 4.0) * (1.0 - 1.0 / b_s) * cot_alpha

    # feeder design: Za = 120(ln(h/a) - 2.25) (Carrel/Jordan; h/a == l/d).
    # Carrel assumes h/a CONSTANT along the array (ideal diameter scaling);
    # constant-diameter practice must pick a reading. The LONGEST element's
    # h/a is used here: live nec2c lands the band-mean R on the R0 target
    # with it (65.75 vs 65 target), while the feed-point-element reading the
    # ARRL/Stroobandt texts show overshoots +14% for constant-diameter
    # geometry (anchors doc §2; Carrel's own accuracy claim is +-10%).
    a = float(wire_d_m) / 2.0
    if a <= 0.0:
        raise ValueError("wire_d_m must be positive")
    h_over_a = (l1 / 2.0) / a
    if h_over_a <= math.e ** 2.25:
        raise ValueError(
            "element half-length/radius = {0:.3g} is too thick for the "
            "Za = 120(ln(h/a) - 2.25) model".format(h_over_a))
    za = 120.0 * (math.log(h_over_a) - 2.25)
    sigma_prime = sigma / math.sqrt(tau)
    r0 = float(r0_ohm)
    if r0 <= 0.0:
        raise ValueError("r0_ohm must be positive")
    t = r0 / (8.0 * sigma_prime * za)
    feeder_z0 = r0 * t + r0 * math.sqrt(t * t + 1.0)

    l_over_d = lengths[0] / float(wire_d_m)
    if l_over_d < 50.0:
        warnings.append(
            "longest element L/d = {0:.0f} is very thick — the thin-wire Za "
            "and NEC2 both degrade below ~50; solver-verify".format(l_over_d))

    # chart-thickness sensitivity: the contours are drawn at h/a = 125;
    # directivity shifts ~-0.2 dB per doubling of h/a (50 < h/a < 10000).
    # Applied at the array's central (geometric-mean) element ratio.
    ha_geo = math.sqrt(h_over_a * (lengths[-1] / 2.0) / a)
    ha_adj = HA_SLOPE_DB_PER_DOUBLING * math.log2(ha_geo / HA_REF)
    if not 50.0 <= ha_geo <= 10000.0:
        warnings.append(
            "mean element h/a = {0:.0f} is outside the documented "
            "thickness-sensitivity range (50-10000) — the {1:+.2f} dB "
            "thickness adjustment is extrapolated".format(ha_geo, ha_adj))
    gain_out = gain_out + ha_adj
    gain_carrel = gain_carrel + ha_adj

    elements = []
    for k in range(n):
        elements.append({
            "name": "Element {0}".format(k + 1),
            "kind": "fed" if k == n - 1 else "passive",
            "length_m": lengths[k],
            "position_m": positions[k],
            "length_lambda_lo": lengths[k] / lam_max,
        })

    return {
        "family": "lpda",
        "f_lo_hz": f_lo,
        "f_hi_hz": f_hi,
        "f_mid_hz": math.sqrt(f_lo * f_hi),
        "bandwidth": B,
        "tau": tau,
        "sigma": sigma,
        "sigma_opt": sigma_opt(tau),
        "on_optimum_sigma": on_opt,
        "cot_alpha": cot_alpha,
        "alpha_deg": alpha_deg,
        "b_ar": b_ar,
        "b_s": b_s,
        "n_exact": n_exact,
        "n_elements": n,
        "wavelength_max_m": lam_max,
        "elements": elements,
        "boom_length_m": boom_span,
        "boom_carrel_m": boom_carrel,
        "wire_d_m": float(wire_d_m),
        "l_over_d": l_over_d,
        "za_ohm": za,
        "sigma_prime": sigma_prime,
        "r0_ohm": r0,
        "feeder_z0_ohm": feeder_z0,
        "gain_dbi": gain_out,
        "gain_dbd": gain_out - DBD_OFFSET,
        "gain_dbi_carrel_original": gain_carrel,
        "gain_ha_adj_db": ha_adj,
        "ha_geo": ha_geo,
        "warnings": warnings + [
            "gain is the CORRECTED contour directivity (Butson-Thompson "
            "1976; Carrel's original labels read 1 dB higher) with the "
            "h/a thickness sensitivity applied; Verify reports the "
            "achieved NEC2 gain",
            "at exactly f_lo the active region truncates (gain droops "
            "~1-2 dB, F/B drops) — specify f_lo a step below the real "
            "band edge if the edge matters",
            "no resistive rear termination is modeled: it flattens the "
            "low-edge VSWR but absorbs ~1.7 dB of low-edge gain",
            "narrow VSWR spikes can appear BETWEEN element resonances at "
            "the low-frequency end (documented LPDA 'weak spots'); a tuned "
            "rear stub can move/kill them — stub tuning is section-7",
        ],
        "source_note": (
            "Carrel design equations + Butson-Thompson gain derate "
            "(docs/upstream/lpda-carrel-anchors.md); feeder Z0 for the "
            "target mean R0 via Za/sigma'"),
    }
