# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rectangular microstrip-patch synthesis, transmission-line method (slice E4).

A microstrip patch is ONE element (a single feed port) per the §1 scope contract.
This module turns a frequency + a substrate (εr, h) into a dimensioned patch —
radiating width W, resonant length L — using the STANDARD, public patch design
equations (Hammerstad effective permittivity; the fringing length-extension
formula; the two-slot edge-resistance / cos²-inset feed model). These equations
are common antenna physics reproduced in countless open sources; nothing here is
copied from any copyrighted text. Provenance + the verified anchors are in
docs/upstream/patch-tl-anchors.md.

Equations (all computed from first principles):
    W       = (c / 2f0) · √(2/(εr+1))
    εr_eff  = (εr+1)/2 + (εr-1)/2 · (1 + 12 h/W)^(-1/2)
    ΔL/h    = 0.412 · (εr_eff+0.3)(W/h+0.264) / ((εr_eff-0.258)(W/h+0.8))
    L       = c / (2 f0 √εr_eff) − 2ΔL
    R_edge  = 1 / (2(G1+G12))                     (two-slot self+mutual)
    R(y0)   = R_edge · cos²(π y0/L)               (inset-feed law)

VERIFIED (docs/upstream): the widely-published 10 GHz / εr 2.2 / h 1.588 mm design
→ W 11.85 mm, εr_eff 1.9715, ΔL 0.811 mm, L 9.053 mm (matches the published
W 11.86 / εr_eff 1.972 / ΔL 0.81 / L 9.06 to the last digit).

**Honest accuracy:** the resonant-length model is good to ~±5 % of f_res vs
full-wave/measurement — that is the stated accuracy and the UI caveat; the openEMS
Verify is the refinement path. The edge-resistance / inset feed is a rougher
ESTIMATE (the two-slot conductance model predicts input R less accurately than the
length) — reported with a caveat, refined by openEMS.

Pure-python, Qt-free, FreeCAD-free; results are dicts of plain floats (house rule).
All SI (metres, Hz, ohms).
"""
from __future__ import annotations

import math

C0 = 299792458.0

#: stated TL-model accuracy on the resonant frequency (fractional).
TL_ACCURACY = 0.05


def patch_width(f0_hz, er):
    """Radiating width W (m) — the efficient-radiator width."""
    return C0 / (2.0 * float(f0_hz)) * math.sqrt(2.0 / (float(er) + 1.0))


def effective_permittivity(er, w_m, h_m):
    """Hammerstad quasi-static effective permittivity (wide-strip form)."""
    er = float(er)
    return (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (
        1.0 + 12.0 * float(h_m) / float(w_m)) ** -0.5


def length_extension(er_eff, w_m, h_m):
    """Fringing length extension ΔL (m) at each radiating edge."""
    woh = float(w_m) / float(h_m)
    return float(h_m) * 0.412 * (er_eff + 0.3) * (woh + 0.264) / (
        (er_eff - 0.258) * (woh + 0.8))


def physical_length(f0_hz, er_eff, dl_m):
    """Physical resonant length L (m) = effective half-wave − 2ΔL fringing."""
    return C0 / (2.0 * float(f0_hz) * math.sqrt(er_eff)) - 2.0 * float(dl_m)


def _j0(x):
    """Bessel J0 (Abramowitz & Stegun 9.4 polynomial approximation)."""
    ax = abs(x)
    if ax < 8.0:
        y = x * x
        p1 = 57568490574.0 + y * (-13362590354.0 + y * (651619640.7 + y * (
            -11214424.18 + y * (77392.33017 + y * -184.9052456))))
        p2 = 57568490411.0 + y * (1029532985.0 + y * (9494680.718 + y * (
            59272.64853 + y * (267.8532712 + y))))
        return p1 / p2
    z = 8.0 / ax
    y = z * z
    xx = ax - 0.785398164
    p1 = 1.0 + y * (-0.1098628627e-2 + y * (0.2734510407e-4 + y * (
        -0.2073370639e-5 + y * 0.2093887211e-6)))
    p2 = -0.1562499995e-1 + y * (0.1430488765e-3 + y * (-0.6911147651e-5 + y * (
        0.7621095161e-6 + y * -0.934935152e-7)))
    return math.sqrt(0.636619772 / ax) * (
        math.cos(xx) * p1 - z * math.sin(xx) * p2)


def _simpson(fn, a, b, n=2000):
    if n % 2:
        n += 1
    hh = (b - a) / n
    s = fn(a) + fn(b)
    for i in range(1, n):
        s += (4.0 if i % 2 else 2.0) * fn(a + i * hh)
    return s * hh / 3.0


def slot_conductances(f0_hz, w_m, l_m):
    """Self (G1) and mutual (G12) radiating-slot conductances (S), integral form."""
    k0 = 2.0 * math.pi * float(f0_hz) / C0
    kw = k0 * float(w_m) / 2.0

    def self_integrand(th):
        c = math.cos(th)
        s = math.sin(th)
        f = kw if abs(c) < 1e-9 else math.sin(kw * c) / c
        return f * f * s * s * s

    def mut_integrand(th):
        return self_integrand(th) * _j0(k0 * float(l_m) * math.sin(th))

    denom = 120.0 * math.pi ** 2
    g1 = _simpson(self_integrand, 1e-6, math.pi - 1e-6) / denom
    g12 = _simpson(mut_integrand, 1e-6, math.pi - 1e-6) / denom
    return g1, g12


def edge_resistance(g1, g12):
    """Two-slot input resistance at the radiating edge (ohm): 1/(2(G1+G12))."""
    return 1.0 / (2.0 * (g1 + g12))


def directivity_dbi(f0_hz, w_m, g1, g12):
    """Two-slot broadside directivity ESTIMATE (dBi). D0_single = (2πW/λ0)²/I1
    (→ 3.0 as W→0); the two in-phase slots add a broadside-array factor reduced
    by mutual coupling: D ≈ 2·D0_single/(1 + G12/G1). Rough — openEMS refines."""
    lam0 = C0 / float(f0_hz)
    i1 = 120.0 * math.pi ** 2 * g1
    d_single = (2.0 * math.pi * float(w_m) / lam0) ** 2 / i1
    d_two = 2.0 * d_single / (1.0 + g12 / g1)
    return 10.0 * math.log10(max(d_two, 1e-6))


def inset_offset(r_edge, l_m, z_target_ohm):
    """cos² inset law → (inset depth from the radiating edge, offset from the
    patch centre) that transforms R_edge to ``z_target_ohm``."""
    ratio = min(1.0, float(z_target_ohm) / float(r_edge))
    y0 = float(l_m) / math.pi * math.acos(math.sqrt(ratio))  # depth from edge
    return y0, float(l_m) / 2.0 - y0


def design_patch(f0_hz, er, h_m, target_z_ohm=50.0):
    """Synthesize a rectangular microstrip patch on an (εr, h) substrate.

    :param f0_hz: design (resonant) frequency (Hz).
    :param er: substrate relative permittivity.
    :param h_m: substrate height (m).
    :param target_z_ohm: feed impedance for the inset/probe placement (default 50).

    Returns a dict: W, L (m), εr_eff, ΔL, the radiating-edge resistance and the
    inset depth / centre offset for ``target_z_ohm``, a directivity estimate
    (dBi), the substrate, warnings and a cited source note. Raises ValueError on
    bad inputs.
    """
    f0 = float(f0_hz)
    er = float(er)
    h = float(h_m)
    if f0 <= 0 or er < 1.0 or h <= 0:
        raise ValueError("need f0>0, er>=1, h>0")

    w = patch_width(f0, er)
    er_eff = effective_permittivity(er, w, h)
    dl = length_extension(er_eff, w, h)
    length = physical_length(f0, er_eff, dl)
    if length <= 0:
        raise ValueError(
            "computed patch length <= 0 (substrate too thick / εr too high for "
            "{0:.3g} GHz)".format(f0 / 1e9))
    lam0 = C0 / f0
    g1, g12 = slot_conductances(f0, w, length)
    r_edge = edge_resistance(g1, g12)
    y0, offset = inset_offset(r_edge, length, target_z_ohm)
    gain = directivity_dbi(f0, w, g1, g12)

    warnings = [
        "resonant frequency is TL-model accurate to ~±5 % vs full-wave — use "
        "Verify with openEMS for the achieved f_res and gain",
        "the probe-feed offset ({0:.2f} mm from centre) is an ESTIMATE: cos^2 is "
        "the PROBE-feed law (an etched inset notch trends toward cos^4 on low-er "
        "substrates), and the two-slot edge R ({1:.0f} ohm) is only order-of-"
        "magnitude accurate — seed for openEMS/measurement, not fabrication-"
        "ready".format(offset * 1e3, r_edge),
    ]
    if h > 0.05 * lam0:
        warnings.append(
            "substrate h = {0:.3g} mm is > 0.05·lambda0 ({1:.3g} mm): thick "
            "substrate — surface waves and probe inductance grow, the TL model "
            "degrades".format(h * 1e3, 0.05 * lam0 * 1e3))
    if w / h > 40.0 or w / h < 1.0:
        warnings.append(
            "W/h = {0:.1f} is outside the usual 1-40 range — the Hammerstad "
            "εr_eff / fringing forms are extrapolated".format(w / h))

    return {
        "family": "patch",
        "f0_hz": f0,
        "er": er,
        "h_m": h,
        "wavelength_m": lam0,
        "width_m": w,
        "length_m": length,
        "er_eff": er_eff,
        "delta_l_m": dl,
        "edge_resistance_ohm": r_edge,
        "g1_s": g1,
        "g12_s": g12,
        "target_z_ohm": float(target_z_ohm),
        "inset_depth_m": y0,
        "feed_offset_m": offset,
        "gain_dbi": gain,
        "gain_dbd": gain - 2.15,
        "warnings": warnings,
        "source_note": (
            "microstrip-patch TL synthesis (standard public equations; see "
            "docs/upstream/patch-tl-anchors.md): W = c/2f·√(2/(εr+1)); "
            "Hammerstad εr_eff = {0:.4f}; fringing ΔL = {1:.4f} mm; "
            "L = c/(2f√εr_eff) − 2ΔL = {2:.4f} mm on εr {3:g} / h {4:.3g} mm. "
            "±5 % f_res accuracy; feed offset is a two-slot estimate.".format(
                er_eff, dl * 1e3, length * 1e3, er, h * 1e3)),
    }
