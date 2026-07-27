# SPDX-License-Identifier: LGPL-2.1-or-later
"""ITU-R P.368-10 LF/MF smooth spherical-earth ground wave (ROADMAP §6, phase D).

The beyond-100-km extension of the shipped flat-earth surface wave: below
30 MHz over a smooth homogeneous earth, the exact solution switches from the
flat-earth Sommerfeld problem (short paths) to the Wait/Hufford residue series
around the curved earth (long paths). This module is a line-for-line Python
port of the **NTIA/ITS LFMF C++ reference implementation** — the software that
Recommendation ITU-R P.368-10 (08/2022) declares an *integral part of the
Recommendation* (the P.368 curves ARE this code's output).

Port provenance & acknowledgment (NTIA requests acknowledgment + change notes):

* Source: https://github.com/NTIA/LFMF v1.1 (commit 57886e9, 2025-01-23) —
  a work of NTIA/ITS employees, public domain in the US (15 USC 105) with a
  worldwide royalty-free derivative-works grant (upstream LICENSE.md; its key
  language is excerpted in ``tests/validation/data/lfmf/PROVENANCE.md``).
* Changes from upstream (2026-07-10): translated C++ -> Python; Hufford's
  bespoke Taylor/asymptotic Airy evaluator (``Airy.cpp``) replaced by
  ``scipy.special.airy`` through the Wait-scaling identities
  ``w1(t) = sqrt(pi)*(Bi(t) - j*Ai(t))`` and
  ``w1'(t) = sqrt(pi)*(Bi'(t) - j*Ai'(t))`` (derived from DLMF 9.2.11 applied
  to the upstream rotation/scale constants); the ACM-680 ``wofz.cpp`` replaced
  by ``scipy.special.wofz`` (the same Faddeeva function). No algorithmic
  changes otherwise. Validated: ``tests/validation/lfmf.py`` replays a dense
  2497-point grid generated from the upstream binary — worst |delta| 3.2e-5 dB.
* References: DeMinco, NTIA Report 99-368 (flat-earth + curve correction);
  Hufford, NTIA Report 87-219 (Airy functions of the third kind); Wait 1956.

Model inputs/validity (enforced, same as upstream ``ValidateInputs.cpp``):
terminal heights 0-50 m, frequency **0.01-30 MHz** (below 10 kHz the ground
wave is ionospheric/waveguide-mode — P.684 territory — and this module
HARD-STOPS rather than extrapolate), distance 0.001-10000 km, eps_r >= 1,
sigma > 0, N_s 250-400 N-units.

Qt-free, FreeCAD-free; needs scipy (present in FreeCAD 0.21/1.1 bundles). SI
units at the API: metres, Hz, watts; internals mirror the C++ (km, MHz).
"""
from __future__ import annotations

import cmath
import math

try:
    from scipy.special import airy as _scipy_airy, wofz as _scipy_wofz
    HAVE_SCIPY = True
except ImportError:                                   # pragma: no cover
    HAVE_SCIPY = False

# Constants — EXACTLY the upstream LFMF.h values. Note epsilon_0 differs from
# the CODATA 8.8541878128e-12 used elsewhere in emstudio: keep the C++ value
# so the port replays the reference implementation to the last digit.
PI = 3.1415926535897932384
EPSILON_0 = 8.854187817e-12
A_0__KM = 6370.0
C = 299792458.0
ETA = 119.9169832 * PI

# Reference antenna gains hard-wired in the upstream model (short vertical
# monopole, 4.77 dBi) — the same reference the P.368 curves are drawn for.
G_TX__DBI = 4.77
G_RX__DBI = 4.77

FLAT_EARTH_CURVE = 0    # SolutionMethod::FLAT_EARTH_CURVE
RESIDUE_SERIES = 1      # SolutionMethod::RESIDUE_SERIES

# NIST DLMF Table 9.9.1 zeros of Ai' (akp) and Ai (ak) — WiRoot.cpp Newton
# starting points (TZERO/TINFIN in the original GWINT.FOR).
_AKP = (-1.0187929716, -3.2481975822, -4.8200992112, -6.1633073556,
        -7.3721772550, -8.4884867340, -9.5354490524, -10.5276603970,
        -11.4750666335, -12.3847883718, -13.2636395229)
_AK = (-2.3381074105, -4.0879494441, -5.5205698281, -6.7867080901,
       -7.9441335871, -9.0226508533, -10.0401743416, -11.0085243037,
       -11.9360255632, -12.8287867529, -13.6914890352)

# WiRoot phase factor for (kind=WONE, scaling=WAIT): exp(+j*2*pi/3).
_PH = complex(math.cos(2.0 * PI / 3.0), math.sin(2.0 * PI / 3.0))

_SQRT_PI = math.sqrt(PI)

# C++ std::cbrt where the runtime has it (Python >= 3.11; the FreeCAD 1.x
# bundle) — pow(x, 1/3) differs by ~1 ulp, enough to flip the flat/residue
# method switch when d lands exactly on d_test. FreeCAD 0.21 (Python 3.10)
# falls back to pow.
_cbrt = getattr(math, "cbrt", None) or (lambda x: x ** (1.0 / 3.0))


def _csqrt_glibc(z):
    """cmath.sqrt with glibc csqrt's pure-imaginary special case.

    glibc returns EXACTLY (c, copysign(c, imag)) for sqrt(0 + bj); CPython
    computes the parts via different expressions and can be 1 ulp asymmetric.
    That ulp matters: for epsilon == 1 (eta - 1 purely imaginary) it decides
    which side of the sqrt branch cut PI*p lands on in the flat-earth F(p)
    terms — up to 1.7 dB vs the reference binary (adversarial-review find).
    """
    if z.real == 0.0:
        c = math.sqrt(abs(z.imag) / 2.0)
        return complex(c, math.copysign(c, z.imag))
    return cmath.sqrt(z)


def _require_scipy():
    if not HAVE_SCIPY:
        raise RuntimeError(
            "the P.368 spherical-earth ground wave needs scipy "
            "(scipy.special.airy/wofz); scipy was not importable")


def _w1(z):
    """Wait's Airy function of the third kind w1 and w1' at complex z.

    Replaces the upstream ``Airy(z, WONE/DWONE, WAIT)`` pair via
    w1 = sqrt(pi)*(Bi - j*Ai), w1' = sqrt(pi)*(Bi' - j*Ai').
    """
    ai, aip, bi, bip = _scipy_airy(complex(z))
    return (_SQRT_PI * (bi - 1j * ai), _SQRT_PI * (bip - 1j * aip))


def _almost_equal_relative(a, b, max_rel_diff):
    """Port of AlmostEqualRelative (LFMF.cpp)."""
    return abs(a - b) <= max(abs(a), abs(b)) * max_rel_diff


def _wi_root(i, q):
    """i-th complex root of w1'(t) - q*w1(t) = 0 (WiRoot.cpp, WONE/WAIT).

    Newton iteration from the DLMF 9.9 real Airy zeros rotated onto the
    exp(2*pi/3) ray; the small-|q| branch starts from Ai' zeros (+ first
    Newton step q/t0), the large-|q| branch from Ai zeros (+ step 1/q).
    """
    if abs(q) ** 3.0 <= 4 * (i - 1) + 3:
        if i <= 10:
            tt = _AKP[i - 1]
        else:   # NIST DLMF 9.9.1.9 / 9.9.8 asymptotic zero
            t = (3.0 / 8.0) * PI * (4.0 * (i - 1) + 1)
            tt = -1.0 * t ** (2.0 / 3.0) * (1.0 - (7.0 / 48.0) * t ** -2.0
                                            + (35.0 / 288.0) * t ** -4.0)
        ti = tt * _PH
        ti = ti + q / ti
    else:
        if i <= 10:
            tt = _AK[i - 1]
        else:   # NIST DLMF 9.9.1.8 / 9.9.6 asymptotic zero
            t = (3.0 / 8.0) * PI * (4.0 * (i - 1) + 3.0)
            tt = -1.0 * t ** (2.0 / 3.0) * (1.0 + (5.0 / 48.0) * t ** -2.0
                                            - (5.0 / 36.0) * t ** -4.0)
        ti = tt * _PH
        ti = ti + 1.0 / q

    cnt = 0
    eps = 0.5e-6
    while True:
        wi, dwi = _w1(ti)
        a = (dwi - q * wi) / (ti * wi - q * dwi)   # Newton: f(t)/f'(t)
        ti = ti - a
        cnt += 1
        if not (cnt <= 25 and (abs((a / ti).real) + abs((a / ti).imag)) > eps):
            break
    if cnt == 26:
        raise RuntimeError("WiRoot: Newton iteration did not converge "
                           "after 25 steps")
    return ti


def _residue_series(k, h_1__km, h_2__km, nu, theta__rad, q):
    """Wait/Hufford residue series (ResidueSeries.cpp) — normalized E, mV/m."""
    gw = 0.0 + 0.0j
    y_high = k * h_2__km / nu
    y_low = k * h_1__km / nu
    x = nu * theta__rad

    for i in range(200):
        ti = _wi_root(i + 1, q)
        w1i, _ = _w1(ti)
        # Height-gain functions H_1(h) — eqn (22) NTIA 99-368
        if h_1__km > 0:
            wi = _w1(ti - y_low)[0] / w1i
            if h_2__km > 0:
                wi *= _w1(ti - y_high)[0] / w1i
        elif h_2__km > 0:
            wi = _w1(ti - y_high)[0] / w1i
        else:
            wi = 1.0 + 0.0j

        wi /= (ti - q * q)                    # eqn (26) NTIA 99-368
        g = wi * cmath.exp(-1.0j * x * ti)
        gw += g

        if i != 0:
            gw2 = gw * gw
            if _almost_equal_relative(abs(gw2.real) + abs(gw2.imag), 0.0, 0.9):
                return 0.0                    # series sum is identically zero
            r = g / gw
            if (abs(r.real) + abs(r.imag)) < 0.0005:
                break                         # converged

    # sqrt(pi)*exp(-j*pi/4) leading factor
    ew = cmath.sqrt(x) * complex(math.sqrt(PI / 2), -math.sqrt(PI / 2)) * gw
    return abs(ew)


def _flat_earth_curve_correction(delta, q, h_1__km, h_2__km, d__km, k,
                                 a_e__km):
    """Flat earth + curvature correction (FlatEarthCurveCorrection.cpp;
    DeMinco 99-368 eqs 28-32 + height-gain eq 36) — normalized E, mV/m."""
    # qi defined as in the original GWFEC.FOR so wofz() serves both uses
    qi = (-0.5 + 0.5j) * math.sqrt(k * d__km) * delta
    p = qi * qi

    p2 = p ** 2
    q3 = q ** 3
    q6 = q ** 6
    q9 = q ** 9

    if abs(q) > 0.1:
        # F(p), eqn (32) NTIA 99-368, then f(x) eqn (31)
        fofp = 1.0 + _SQRT_PI * 1j * qi * _scipy_wofz(qi)
        fofx = fofp + (1.0 - 1j * cmath.sqrt(PI * p)
                       - (1.0 + 2.0 * p) * fofp) / (4.0 * q3)
        fofx = fofx + (1.0 - 1j * cmath.sqrt(PI * p) * (1.0 - p) - 2.0 * p
                       + 5.0 * p2 / 6.0 + (p2 / 2.0 - 1.0) * fofp) / (4.0 * q6)
    else:
        # small |q|: power series in q — DeMinco eqs 28/30
        a = (
            1.0 + 0.0j,
            -1j * _SQRT_PI,
            -2.0 + 0.0j,
            1j * _SQRT_PI * (1.0 + 1.0 / (4.0 * q3)),
            4.0 / 3.0 * (1.0 + 1.0 / (2.0 * q3)),
            -1j * _SQRT_PI / 4.0 * (1.0 + 3.0 / (4.0 * q3)),
            -8.0 / 15.0 * (1.0 + 1.0 / q3 + 7.0 / (32.0 * q6)),
            1j * _SQRT_PI / 6.0 * (1.0 + 5.0 / (4.0 * q3)
                                   + 27.0 / (32.0 * q6)),
            16.0 / 105.0 * (1.0 + 3.0 / (2.0 * q3) + 27.0 / (32.0 * q6)),
            -1j * _SQRT_PI / 24.0 * (1.0 + 7.0 / (4.0 * q3)
                                     + 5.0 / (4.0 * q6)
                                     + 21.0 / (64.0 * q9)),
        )
        x = d__km / a_e__km * (k * a_e__km / 2.0) ** (1.0 / 3.0)
        fofx = 0.0 + 0.0j
        base = cmath.exp(1j * PI / 4.0) * q * x ** 0.5
        for ii in range(10):
            fofx = fofx + a[ii] * base ** ii

    # height-gain: two Taylor terms per antenna (DeMinco eq 36)
    return abs(fofx * (1.0 + 1j * k * h_2__km * delta)
               * (1.0 + 1j * k * h_1__km * delta))


def lfmf(h_tx__meter, h_rx__meter, f__mhz, p_tx__watt, n_s, d__km,
         epsilon, sigma, pol):
    """P.368-10 ground-wave prediction — port of ``LFMF_CPP`` (LFMF.cpp).

    :param h_tx__meter: transmitter terminal height, m (0-50).
    :param h_rx__meter: receiver terminal height, m (0-50).
    :param f__mhz: frequency, MHz (0.01-30; <10 kHz HARD-STOPS — P.684 band).
    :param p_tx__watt: transmitter power, W (> 0).
    :param n_s: surface refractivity, N-units (250-400; 301 standard).
    :param d__km: great-circle path distance, km (0.001-10000).
    :param epsilon: ground relative permittivity (>= 1).
    :param sigma: ground conductivity, S/m (> 0).
    :param pol: 0 horizontal, 1 vertical.
    :returns: dict — ``A_btl__db`` basic transmission loss, ``E_dBuVm`` field
        strength, ``P_rx__dbm`` received power (into the 4.77 dBi reference
        antenna), ``method`` (0 flat-earth+curve-correction, 1 residue series).
    :raises ValueError: on out-of-range input (mirrors upstream return codes).
    """
    _require_scipy()
    if not 0 <= h_tx__meter <= 50:
        raise ValueError("TX height out of range [0, 50] m")
    if not 0 <= h_rx__meter <= 50:
        raise ValueError("RX height out of range [0, 50] m")
    if not 0.01 <= f__mhz <= 30:
        raise ValueError("frequency out of range [0.01, 30] MHz — below "
                         "10 kHz the path is ionospheric (ITU-R P.684), "
                         "not P.368 ground wave")
    if p_tx__watt <= 0:
        raise ValueError("TX power must be positive")
    if not 250 <= n_s <= 400:
        raise ValueError("surface refractivity out of range [250, 400]")
    if not 0.001 <= d__km <= 10000:
        raise ValueError("distance out of range [0.001, 10000] km")
    if epsilon < 1:
        raise ValueError("ground relative permittivity must be >= 1")
    if sigma <= 0:
        raise ValueError("ground conductivity must be positive")
    if pol not in (0, 1):
        raise ValueError("pol must be 0 (horizontal) or 1 (vertical)")

    f__hz = f__mhz * 1e6
    lambda__meter = C / f__hz

    h_1__km = min(h_tx__meter, h_rx__meter) / 1000.0
    h_2__km = max(h_tx__meter, h_rx__meter) / 1000.0

    # effective earth radius from surface refractivity
    a_e__km = A_0__KM * 1 / (1 - 0.04665 * math.exp(0.005577 * n_s))
    theta__rad = d__km / a_e__km

    k = 2.0 * PI * 1000 / lambda__meter          # wavenumber, rad/km
    nu = _cbrt(a_e__km * k / 2.0)                # C++ std::cbrt

    # dielectric ground constant, DeMinco 99-368 eq (17)
    eta = complex(epsilon, -sigma / (EPSILON_0 * 2 * PI * f__hz))

    # surface impedance, DeMinco 99-368 eq (15); glibc-faithful sqrt for the
    # epsilon == 1 pure-imaginary boundary (see _csqrt_glibc)
    delta = _csqrt_glibc(eta - 1.0)
    if pol == 1:
        delta /= eta

    q = -nu * 1j * delta

    # method switch — SG3 Groundwave Handbook eq 15 (C++ std::cbrt)
    d_test__km = 80 / _cbrt(f__mhz)

    if d__km < d_test__km:
        e_gw = _flat_earth_curve_correction(delta, q, h_1__km, h_2__km,
                                            d__km, k, a_e__km)
        method = FLAT_EARTH_CURVE
    else:
        e_gw = _residue_series(k, h_1__km, h_2__km, nu, theta__rad, q)
        method = RESIDUE_SERIES

    g_tx = 10 ** (G_TX__DBI / 10)

    # un-normalize the field strength: E_0 = sqrt(ETA*EIRP/(4*pi))/d [mV/m]
    e_0 = math.sqrt(ETA * (p_tx__watt * g_tx) / (4.0 * PI)) / d__km
    e_gw = e_gw * e_0

    if e_gw == 0.0:
        # mirrors the C++ log10(0) = -inf path (residue series summed to 0)
        return {"A_btl__db": math.inf, "E_dBuVm": -math.inf,
                "P_rx__dbm": -math.inf, "method": method}

    # basic transmission loss via the Friis/field-strength identity
    a_btl__db = (10 * math.log10(p_tx__watt * g_tx)
                 + 10 * math.log10(ETA * 4 * PI) + 20 * math.log10(f__hz)
                 - 20 * math.log10(e_gw / 1000) - 20 * math.log10(C))
    e_dbuvm = 60 + 20 * math.log10(e_gw)         # mV/m -> dB(uV/m)
    p_rx__dbm = e_dbuvm + G_RX__DBI - 20.0 * math.log10(f__hz) + 42.8

    return {"A_btl__db": a_btl__db, "E_dBuVm": e_dbuvm,
            "P_rx__dbm": p_rx__dbm, "method": method}


def field_strength_dbuv_m(dist_m, freq_hz, eps_r, sigma, cmf_v=300.0,
                          n_s=301.0, h_tx_m=0.0, h_rx_m=0.0, pol=1):
    """Spherical-earth ground-wave field strength, dB(uV/m) — the P.368-10
    counterpart of :func:`emstudio.coverage.groundwave.field_strength_dbuv_m`.

    ``cmf_v`` is the cymomotive force (300 V = the P.368 1-kW reference). The
    CMF convention rounds sqrt(ETA/4pi) to sqrt(30); this wrapper converts the
    CMF to EIRP with the same sqrt(30) convention and drives the LFMF engine,
    so the two modules share one source normalization.
    """
    eirp_w = float(cmf_v) ** 2 / 30.0
    g_tx = 10 ** (G_TX__DBI / 10)
    res = lfmf(h_tx_m, h_rx_m, float(freq_hz) / 1e6, eirp_w / g_tx,
               n_s, float(dist_m) / 1000.0, eps_r, sigma, pol)
    # correct the ~0.003 dB sqrt(30) vs sqrt(ETA/4pi) reference mismatch so
    # E -> CMF/d exactly as attenuation -> 1 (matching the flat-earth module)
    e_ref_exact = math.sqrt(ETA * eirp_w / (4.0 * PI))
    return res["E_dBuVm"] + 20.0 * math.log10(
        float(cmf_v) / e_ref_exact)
