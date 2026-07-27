# SPDX-License-Identifier: LGPL-2.1-or-later
"""Top-loading capacitance for VLF/LF vertical antennas (ROADMAP §4 breadth).

The classic static-capacitance set for capacity hats and top-loading wires
over a perfectly conducting ground: parallel-plate hat with fringe, single
horizontal/vertical wires with end-effect constants, flat-top of n parallel
wires with proximity constants, inverted-L and T composites with the mutual
term, n wires in a vertical plane, and wire-to-wire capacitance. This is
standard public physics (the lineage runs through Grover 1926 and Terman's
handbook); every constant and table value below was verified from the page
images of the reference (A.D. Watt, *VLF Radio Engineering*, §2.3 —
eq/table numbers cited in comments; provenance + the exact-identity
cross-checks in docs/upstream/watt-topload-anchors.md). The 24.16 constant
is exactly 2*pi*eps0/ln(10) in pF/m.

All formulas assume a perfectly conducting ground plane; real hats measure
~0-10 % ABOVE the plate+fringe model (the verified scale-model dataset) —
callers get that caveat in ``notes``. Pure-python, Qt-free, FreeCAD-free;
SI in, capacitance out in FARADS (display conversions belong to the UI).
"""
from __future__ import annotations

import math

#: 2*pi*eps0/ln(10) in pF/m — the "24.16" of the classic log10 forms.
C_LOG10_PF_PER_M = 24.16
#: eps0 in pF/m — the "8.85" of the parallel-plate form.
EPS0_PF_PER_M = 8.85

#: End-effect constant k for a single horizontal wire (eq 2.3.7 class,
#: Table 2.3.2): keyed on 2h/l up to 1.0, then on l/2h below it (the two
#: branches meet at 0.336 exactly).
K_HORIZONTAL_2H_OVER_L = [
    (0.0, 0.0), (0.1, 0.042), (0.2, 0.082), (0.3, 0.121), (0.4, 0.157),
    (0.5, 0.191), (0.6, 0.223), (0.7, 0.254), (0.8, 0.283), (0.9, 0.310),
    (1.0, 0.336),
]
K_HORIZONTAL_L_OVER_2H = [
    (0.05, 1.445), (0.10, 1.155), (0.15, 0.990), (0.20, 0.874),
    (0.25, 0.790), (0.30, 0.721), (0.35, 0.664), (0.40, 0.617),
    (0.45, 0.576), (0.50, 0.541), (0.55, 0.510), (0.60, 0.482),
    (0.65, 0.457), (0.70, 0.435), (0.75, 0.414), (0.80, 0.396),
    (0.85, 0.379), (0.90, 0.364), (0.95, 0.350), (1.0, 0.336),
]

#: End-effect constant k' for a single vertical wire (eq 2.3.9 class,
#: Table 2.3.3): keyed on h'/l' (lower-end height / length). The first two
#: rows are the table's own extrapolated values.
K_VERTICAL_HPRIME_OVER_L = [
    (0.005, 0.44), (0.01, 0.42), (0.02, 0.403), (0.04, 0.384),
    (0.06, 0.369), (0.08, 0.356), (0.10, 0.345), (0.15, 0.323),
    (0.20, 0.305), (0.25, 0.291), (0.30, 0.280), (0.4, 0.261),
    (0.5, 0.247), (0.6, 0.236), (0.7, 0.227), (0.8, 0.219), (0.9, 0.213),
    (1.0, 0.207), (2.0, 0.177), (5.0, 0.153), (10.0, 0.144),
]
K_VERTICAL_INF = 0.133

#: Proximity constant k_n for a flat top of n parallel wires (eq 2.3.10
#: class, Table 2.3.4).
K_N_FLAT_TOP = [
    (2, 0.0), (3, 0.067), (4, 0.135), (5, 0.197), (6, 0.252), (7, 0.302),
    (8, 0.347), (9, 0.388), (10, 0.425), (11, 0.460), (12, 0.492),
    (13, 0.522), (14, 0.550), (15, 0.576), (16, 0.601), (17, 0.625),
    (18, 0.647), (19, 0.668), (20, 0.688), (30, 0.847), (40, 0.970),
    (50, 1.063), (100, 1.357),
]

#: Mutual constant X for wires at right angles (inverted-L / T composites,
#: eq 2.3.12/2.3.13 class, Table 2.3.5): rows l'/l, columns h'/l'.
X_COLS_HPRIME_OVER_LPRIME = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 5.0]
X_ROWS_LPRIME_OVER_L = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9,
                        1.0, 5.0, 10.0]
X_TABLE = [
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.055, 0.064, 0.072, 0.078, 0.083, 0.088, 0.125],
    [0.099, 0.116, 0.129, 0.137, 0.146, 0.155, 0.207],
    [0.135, 0.157, 0.173, 0.184, 0.195, 0.206, 0.262],
    [0.164, 0.189, 0.207, 0.222, 0.233, 0.243, 0.296],
    [0.186, 0.214, 0.233, 0.248, 0.260, 0.269, 0.323],
    [0.204, 0.233, 0.253, 0.267, 0.278, 0.286, 0.340],
    [0.218, 0.247, 0.267, 0.282, 0.293, 0.302, 0.352],
    [0.229, 0.258, 0.278, 0.292, 0.302, 0.311, 0.358],
    [0.237, 0.265, 0.285, 0.298, 0.308, 0.317, 0.362],
    [0.243, 0.271, 0.290, 0.303, 0.313, 0.321, 0.365],
    [0.189, 0.200, 0.207, 0.213, 0.216, 0.218, 0.232],
    [0.130, 0.137, 0.141, 0.144, 0.146, 0.147, 0.155],
]

#: Umbrella top-loading landmarks (Belrose & Thain guyed-umbrella data —
#: figure-accuracy facts, NOT a fitted curve): maximum effective height at
#: insulator ratio h'/h_a ~ 0.35; at h'/h_a = 0.7 the voltage-limited power
#: capability is ~8x and the bandwidth ~3x the unloaded mast.
UMBRELLA_HE_MAX_RATIO = 0.35
UMBRELLA_07_POWER_FACTOR = 8.0
UMBRELLA_07_BANDWIDTH_FACTOR = 3.0


def _interp(x, pairs):
    if x <= pairs[0][0]:
        return pairs[0][1]
    if x >= pairs[-1][0]:
        return pairs[-1][1]
    for (x1, y1), (x2, y2) in zip(pairs, pairs[1:]):
        if x1 <= x <= x2:
            return y1 + (x - x1) / (x2 - x1) * (y2 - y1)
    return pairs[-1][1]


def k_horizontal(l_m, h_m):
    """End-effect k for a horizontal wire of length l at height h."""
    if l_m <= 0 or h_m <= 0:
        raise ValueError("wire length and height must be positive")
    r = 2.0 * h_m / l_m
    if r <= 1.0:
        return _interp(r, K_HORIZONTAL_2H_OVER_L)
    return _interp(1.0 / r, K_HORIZONTAL_L_OVER_2H)


def k_vertical(l_m, h_lower_m):
    """End-effect k' for a vertical wire of length l with its lower end at
    h_lower above ground."""
    if l_m <= 0 or h_lower_m < 0:
        raise ValueError("length must be positive, lower-end height >= 0")
    r = h_lower_m / l_m
    if r >= K_VERTICAL_HPRIME_OVER_L[-1][0]:
        return K_VERTICAL_INF if r > 100.0 else _interp(
            r, K_VERTICAL_HPRIME_OVER_L)
    return _interp(r, K_VERTICAL_HPRIME_OVER_L)


def k_n_flat_top(n):
    """Proximity constant k_n for an n-wire flat top (interpolated between
    the tabulated counts)."""
    if n < 2:
        raise ValueError("a flat top needs n >= 2 wires")
    return _interp(float(n), [(float(a), b) for a, b in K_N_FLAT_TOP])


def x_mutual(lprime_over_l, hprime_over_lprime):
    """Mutual constant X for a horizontal+vertical composite (bilinear)."""
    r = min(max(lprime_over_l, X_ROWS_LPRIME_OVER_L[0]),
            X_ROWS_LPRIME_OVER_L[-1])
    c = min(max(hprime_over_lprime, X_COLS_HPRIME_OVER_LPRIME[0]),
            X_COLS_HPRIME_OVER_LPRIME[-1])
    rows = X_ROWS_LPRIME_OVER_L
    cols = X_COLS_HPRIME_OVER_LPRIME
    i = max(0, min(len(rows) - 2, next(
        (j for j in range(len(rows) - 1) if rows[j + 1] >= r), len(rows) - 2)))
    jx = max(0, min(len(cols) - 2, next(
        (j for j in range(len(cols) - 1) if cols[j + 1] >= c), len(cols) - 2)))
    fr = (r - rows[i]) / (rows[i + 1] - rows[i])
    fc = (c - cols[jx]) / (cols[jx + 1] - cols[jx])
    v00, v01 = X_TABLE[i][jx], X_TABLE[i][jx + 1]
    v10, v11 = X_TABLE[i + 1][jx], X_TABLE[i + 1][jx + 1]
    return ((1 - fr) * (1 - fc) * v00 + (1 - fr) * fc * v01
            + fr * (1 - fc) * v10 + fr * fc * v11)


def plate_hat_c(area_m2, height_m, perimeter_m=0.0):
    """Solid/mesh top hat as a parallel plate with the fringe correction:
    C = eps0*(A + height*perimeter)/height. Real hats measure ~0-10 % above
    this (the verified scale-model dataset)."""
    if area_m2 <= 0 or height_m <= 0:
        raise ValueError("hat area and height must be positive")
    a_eff = area_m2 + height_m * max(0.0, perimeter_m)
    return EPS0_PF_PER_M * a_eff / height_m * 1e-12


def horizontal_wire_c(l_m, h_m, d_m):
    """Single horizontal wire of length l, height h, diameter d."""
    if d_m <= 0 or h_m <= d_m:
        raise ValueError("need diameter > 0 and height > diameter")
    denom = math.log10(4.0 * h_m / d_m) - k_horizontal(l_m, h_m)
    if denom <= 0:
        raise ValueError("geometry outside the thin-wire model (log term)")
    return C_LOG10_PF_PER_M * l_m / denom * 1e-12


def vertical_wire_c(l_m, h_lower_m, d_m):
    """Single vertical wire of length l, lower end h_lower above ground."""
    if d_m <= 0 or l_m <= d_m:
        raise ValueError("need diameter > 0 and length > diameter")
    denom = math.log10(2.0 * l_m / d_m) - k_vertical(l_m, h_lower_m)
    if denom <= 0:
        raise ValueError("geometry outside the thin-wire model (log term)")
    return C_LOG10_PF_PER_M * l_m / denom * 1e-12


def flat_top_c(n, l_m, h_m, d_m, spacing_m):
    """Flat top of n parallel horizontal wires (length l, height h,
    diameter d, spacing D between centres). Returns (C_farads, warnings).
    Validity: total width (n-1)*D <= l/4."""
    n = int(n)
    if n < 2:
        raise ValueError("a flat top needs n >= 2 wires (use "
                         "horizontal_wire_c for one)")
    if spacing_m <= d_m:
        raise ValueError("wire spacing must exceed the wire diameter")
    warnings = []
    if (n - 1) * spacing_m > l_m / 4.0:
        warnings.append(
            "flat-top width ({0:.3g} m) exceeds l/4 ({1:.3g} m) — the k_n "
            "proximity table is outside its stated validity; treat C as "
            "approximate".format((n - 1) * spacing_m, l_m / 4.0))
    k = k_horizontal(l_m, h_m)
    kn = k_n_flat_top(n)
    denom = (math.log10(4.0 * h_m / d_m) - n * k
             + (n - 1) * math.log10(2.0 * h_m / spacing_m) - n * kn)
    if denom <= 0:
        raise ValueError("geometry outside the flat-top model (log terms)")
    return C_LOG10_PF_PER_M * n * l_m / denom * 1e-12, warnings


def inverted_l_c(l_m, lprime_m, h_m, hprime_m, d_m):
    """Inverted-L: horizontal top of length l at height h + vertical of
    length l' whose lower end is h' above ground."""
    if l_m <= 0 or lprime_m <= 0:
        raise ValueError("both sections need positive length")
    total = l_m + lprime_m
    wl = l_m / total
    wv = lprime_m / total
    x = x_mutual(lprime_m / l_m, hprime_m / lprime_m)
    denom = (wl * (math.log10(4.0 * h_m / d_m) - k_horizontal(l_m, h_m))
             + wv * (math.log10(2.0 * lprime_m / d_m)
                     - k_vertical(lprime_m, hprime_m)) + x)
    if denom <= 0:
        raise ValueError("geometry outside the composite model (log terms)")
    return C_LOG10_PF_PER_M * total / denom * 1e-12


def t_antenna_c(l_m, lprime_m, h_m, hprime_m, d_m):
    """T antenna: horizontal top of TOTAL length l at height h, centre-fed
    by a vertical of length l' reaching to h' above ground. The mutual term
    is weighted (l+2l')/(l+l') — stronger than the inverted-L because both
    top halves flank the vertical."""
    if l_m <= 0 or lprime_m <= 0:
        raise ValueError("both sections need positive length")
    total = l_m + lprime_m
    wl = l_m / total
    wv = lprime_m / total
    x = x_mutual(lprime_m / l_m, hprime_m / lprime_m)
    denom = (wl * (math.log10(4.0 * h_m / d_m) - k_horizontal(l_m, h_m))
             + wv * (math.log10(2.0 * lprime_m / d_m)
                     - k_vertical(lprime_m, hprime_m))
             + (l_m + 2.0 * lprime_m) / total * x)
    if denom <= 0:
        raise ValueError("geometry outside the composite model (log terms)")
    return C_LOG10_PF_PER_M * total / denom * 1e-12


def vertical_plane_c(n, lprime_m, hprime_m, d_m, spacing_m):
    """n parallel vertical wires, equally spaced in a vertical plane
    (downlead curtains).

    NOTE — third book-internal typo (review-verified): the PRINTED eq
    weights the mutual log by (n-1)/n, which makes the denominator
    collapse for modest n (capacitance above the physical n-times-
    isolated-wire bound, then negative). The k_n table itself obeys the
    identity k_n = (2/n^2)*sum_{m=1..n-1}(n-m)*log10(m) to every printed
    digit — an identity DERIVED under the full (n-1) weight (the same
    structure as the sibling flat-top form) — so the (n-1) weight is
    used here; provenance in watt-topload-anchors.md."""
    n = int(n)
    if n < 2:
        raise ValueError("use vertical_wire_c for a single wire")
    if spacing_m <= d_m:
        raise ValueError("wire spacing must exceed the wire diameter")
    kp = k_vertical(lprime_m, hprime_m)
    kn = k_n_flat_top(n)
    denom = (math.log10(2.0 * lprime_m / d_m)
             + (n - 1) * math.log10(lprime_m / spacing_m)
             - n * (kp + kn))
    if denom <= 0:
        raise ValueError("geometry outside the vertical-plane model")
    return C_LOG10_PF_PER_M * lprime_m * n / denom * 1e-12


def wire_to_wire_c_per_m(spacing_m, d_m):
    """Capacitance per metre BETWEEN two parallel wires remote from ground:
    half the wire-to-plane value; ~ 12.08/log10(2D/d) pF/m."""
    if spacing_m <= d_m:
        raise ValueError("spacing must exceed the wire diameter")
    arg = (spacing_m + math.sqrt(spacing_m ** 2 - d_m ** 2)) / d_m
    return (C_LOG10_PF_PER_M / 2.0) / math.log10(arg) * 1e-12


def coax_c_per_m(inner_d_m, outer_d_m):
    """Air-dielectric coax C per metre — 24.16/log10(D/d) pF/m; identical
    to the exact TEM C' at eps_r = 1 (cross-gate identity)."""
    if outer_d_m <= inner_d_m:
        raise ValueError("outer diameter must exceed inner")
    return C_LOG10_PF_PER_M / math.log10(outer_d_m / inner_d_m) * 1e-12


def effective_height_toploaded(h_a_m, c_hat_f, c_mast_f):
    """Effective height of a top-loaded vertical via the trapezoidal
    current profile (the classic Laport construction): the mast current
    tapers linearly from I at the base to I*C_hat/(C_hat+C_mast) at the
    top, so h_e = h_a*(1 + r)/2 with r = C_hat/(C_hat+C_mast). Unloaded
    (r=0) this is the classic h_a/2; a huge hat drives h_e toward h_a.
    The reference gives no closed form for this — the trapezoid is the
    standard engineering construction (documented approximate)."""
    if h_a_m <= 0:
        raise ValueError("mast height must be positive")
    if c_hat_f < 0 or c_mast_f < 0 or (c_hat_f + c_mast_f) <= 0:
        raise ValueError("capacitances must be non-negative, not both zero")
    r = c_hat_f / (c_hat_f + c_mast_f)
    return h_a_m * (1.0 + r) / 2.0
