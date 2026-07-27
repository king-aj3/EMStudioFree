# SPDX-License-Identifier: LGPL-2.1-or-later
"""Radial-ground-system loss estimator for VLF/LF verticals (ROADMAP §4).

The classic H-field zone-integral method for the ground-system resistance
R_g of an electrically short vertical of effective current height h over a
radial-wire screen of N wires and radius a, beyond which bare earth of
conductivity sigma extends: the near field is split into region 1
(rho < h, H ~ I/2*pi*rho) and region 2 (h < rho < lambda/2*pi,
H ~ I*h/2*pi*rho^2), each annulus contributing
dR_H = (2*pi/I^2) * integral(R'_H * H^2 * rho drho) with the local surface
resistance R'_H — bare earth sqrt(pi*f*mu0/sigma), or the radial-wire grid
value that grows as rho^2/N^2 (wire spacing s = 2*pi*rho/N) and as
f^(3/2)*sigma^(1/2) (a reactive grid shunted by lossy earth).

Standard public physics (the lineage runs through the classic 1937 BSTJ
radial-ground measurements and the NBS/Wait grid-impedance papers); every
coefficient verified from the reference page images with EXACT identity
cross-checks (0.366 = ln10/2pi; 3.66e-7 = 1e-6*ln10/2pi; the region-2
earth term derives exactly from sqrt(pi*f*mu0/sigma)) — see
docs/upstream/watt-topload-anchors.md. Validity: the closed forms assume
2 m < s < 100 m over the wired zones and [log10(s/pi/d)]^2 ~ 12 (typical
radial-wire sizes); outside that the wired-zone terms are approximate.

Pure-python, Qt-free, FreeCAD-free. SI units throughout.
"""
from __future__ import annotations

import math

MU0 = 4.0e-7 * math.pi
C0 = 299792458.0

#: Grid surface-resistance coefficient (ohms) for R'_H =
#: GRID_COEFF * rho^2 * N^-2 * f^(3/2) * sigma^(1/2) — verified.
GRID_COEFF = 1.0e-6
#: ln(10)/(2*pi) — the "0.366" of the constant-R'_H annulus.
LN10_OVER_2PI = math.log(10.0) / (2.0 * math.pi)


def earth_surface_resistance(f_hz, sigma_s_per_m):
    """Bare-earth surface resistance sqrt(pi*f*mu0/sigma) (ohms/square)."""
    if f_hz <= 0 or sigma_s_per_m <= 0:
        raise ValueError("frequency and conductivity must be positive")
    return math.sqrt(math.pi * f_hz * MU0 / sigma_s_per_m)


def grid_surface_resistance(rho_m, n_wires, f_hz, sigma_s_per_m):
    """Radial-wire-grid surface resistance at radius rho (ohms/square)."""
    if rho_m <= 0 or n_wires < 1:
        raise ValueError("need positive radius and at least one wire")
    return (GRID_COEFF * rho_m ** 2 / float(n_wires) ** 2
            * f_hz ** 1.5 * math.sqrt(sigma_s_per_m))


def ground_resistance(f_hz, h_e_m, n_wires, screen_radius_m,
                      sigma_s_per_m, rho_min_m=None):
    """Ground-system resistance R_g of a short vertical over a radial
    screen. Returns a dict with the per-zone terms and warnings.

    :param h_e_m: effective (current) height of the vertical (m).
    :param n_wires: radial count N (0 = bare earth everywhere).
    :param screen_radius_m: radius a of the wired screen (m).
    :param sigma_s_per_m: earth conductivity (S/m).
    :param rho_min_m: inner integration edge (default 0.01*h — the base
        zone under the mast usually gets special heavy mesh; the classic
        treatment starts the integral there).
    """
    f = float(f_hz)
    h = float(h_e_m)
    a = float(screen_radius_m)
    n = int(n_wires)
    sigma = float(sigma_s_per_m)
    if h <= 0:
        raise ValueError("effective height must be positive")
    lam = C0 / f
    rho_rad = lam / (2.0 * math.pi)
    warnings = []
    if h >= rho_rad:
        raise ValueError(
            "h >= lambda/2pi — not an electrically short vertical; the "
            "zone-integral model does not apply")
    rho1 = 0.01 * h if rho_min_m is None else float(rho_min_m)
    r_earth = earth_surface_resistance(f, sigma)

    # the grid's rho^2-growing surface resistance crosses the earth's at
    # rho_x = sqrt(R_earth/c); wires only help INSIDE that radius (over sea
    # water rho_x is tiny — a screen buys almost nothing, correctly)
    c = (GRID_COEFF / float(n) ** 2 * f ** 1.5 * math.sqrt(sigma)) \
        if n >= 1 else None
    rho_x = math.sqrt(r_earth / c) if c else 0.0
    wired_to = min(a, rho_x) if n >= 1 else 0.0
    if n >= 1 and rho_x < a:
        warnings.append(
            "beyond rho = {0:.0f} m the {1}-wire grid's surface resistance "
            "exceeds bare earth (spacing too wide) — the outer screen is "
            "counted as earth; more wires would extend the useful "
            "radius".format(rho_x, n))

    terms = {}
    # ---- region 1 (rho1 .. h): H ~ I/2pi rho -----------------------------
    # wired part: dR = R'(rho)/(2 pi rho) drho with R' = c*rho^2 -> closed
    # form c*(rho2^2-rho1^2)/(4 pi); bare part: 0.366*R'*log10(rho2/rho1)
    r1_grid_hi = min(h, wired_to)
    if r1_grid_hi > rho1:
        terms["region1_grid"] = c * (r1_grid_hi ** 2 - rho1 ** 2) \
            / (4 * math.pi)
    r1_earth_lo = max(rho1, r1_grid_hi)
    if h > r1_earth_lo:
        terms["region1_earth"] = LN10_OVER_2PI * r_earth \
            * math.log10(h / r1_earth_lo)

    # ---- region 2 (h .. lambda/2pi): H ~ I h/2pi rho^2 -------------------
    r2_grid_hi = min(max(wired_to, h), rho_rad)
    if r2_grid_hi > h:
        # wired annulus: dR = h^2 R'(rho)/(2 pi rho^3) drho with
        # R' = c rho^2 -> h^2 c ln(rho2/rho1)/(2 pi)
        terms["region2_grid"] = (h ** 2 * c / (2 * math.pi)
                                 * math.log(r2_grid_hi / h))
    edge = max(r2_grid_hi, h)
    # bare earth from the useful screen edge outward:
    # h^2 R'/(4 pi) (1/e^2 - 1/r^2)
    if rho_rad > edge:
        terms["region2_earth"] = (h ** 2 * r_earth / (4 * math.pi)
                                  * (1.0 / edge ** 2 - 1.0 / rho_rad ** 2))

    # ---- validity notes ---------------------------------------------------
    if n >= 1:
        s_edge = 2.0 * math.pi * a / n
        if not 2.0 <= s_edge <= 100.0:
            warnings.append(
                "wire spacing at the screen edge is {0:.1f} m — outside "
                "the 2-100 m validity of the grid closed form; the wired "
                "terms are approximate".format(s_edge))
    rg = sum(terms.values())
    return {
        "rg_ohm": rg,
        "terms_ohm": terms,
        "earth_surface_r_ohm": r_earth,
        "lambda_m": lam,
        "radiation_zone_m": rho_rad,
        "rho_inner_m": rho1,
        "warnings": warnings,
        "source_note": (
            "H-field zone integrals over a radial screen (regions rho<h "
            "and h<rho<lambda/2pi; grid R' ~ rho^2 N^-2 f^1.5 sigma^0.5, "
            "earth sqrt(pi f mu0/sigma)) — coefficients exact-verified; "
            "docs/upstream/watt-topload-anchors.md. E-field/base losses "
            "and buried-depth effects are NOT included."),
    }


def optimize_radials(f_hz, h_e_m, target_rg_ohm, sigma_s_per_m,
                     n_choices=(50, 100, 150, 200, 300),
                     max_radius_factor=8.0):
    """For each N, the smallest screen radius meeting the R_g target (or
    None if unreachable inside max_radius_factor*h), with the total wire
    length — the classic wire-economy comparison. Returns a list of dicts
    sorted by total wire length."""
    out = []
    h = float(h_e_m)
    # honest pre-check: if bare earth already meets the target, NO screen
    # is needed — report that instead of the bisection floor artifact
    if ground_resistance(f_hz, h, 0, 0.0, sigma_s_per_m)["rg_ohm"] \
            <= target_rg_ohm:
        return [{"n_wires": 0, "radius_m": 0.0, "total_wire_m": 0.0,
                 "reachable": True, "no_screen_needed": True}]
    for n in n_choices:
        lo, hi = 0.05 * h, max_radius_factor * h
        best = None
        if ground_resistance(f_hz, h, n, hi, sigma_s_per_m)["rg_ohm"] \
                <= target_rg_ohm:
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                rg = ground_resistance(f_hz, h, n, mid,
                                       sigma_s_per_m)["rg_ohm"]
                if rg > target_rg_ohm:
                    lo = mid
                else:
                    hi = mid
            best = hi
        out.append({
            "n_wires": int(n),
            "radius_m": best,
            "total_wire_m": (best * n) if best is not None else None,
            "reachable": best is not None,
            "no_screen_needed": False,
        })
    reachable = [o for o in out if o["reachable"]]
    reachable.sort(key=lambda o: o["total_wire_m"])
    unreachable = [o for o in out if not o["reachable"]]
    return reachable + unreachable
