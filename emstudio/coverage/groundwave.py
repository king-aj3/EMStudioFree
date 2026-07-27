# SPDX-License-Identifier: LGPL-2.1-or-later
"""LF/MF ground-wave (surface-wave) propagation — ITU-R P.368 (ROADMAP §6, phase C).

The band AJ cares about: below ~30 MHz a vertically-polarised wave clings to the
earth and the ground's conductivity/permittivity set how fast the field decays with
distance. This is the ITU-R P.368 / Norton flat-earth surface-wave model, validated
against the ITU Handbook on Ground Wave Propagation (R-HDB-59, 2014) worked chain.

Formulas (ITU Handbook R-HDB-59 §Part 2, eqs 18/40; Norton/Terman):

  complex permittivity   eps_c = eps_r - j*60*lambda*sigma   (= eps_r - j*sigma/(w*eps0))
  numerical distance     rho   = -j*(pi*R/lambda)*(eps_c - 1)/eps_c**2 ,  p = |rho|
  attenuation function   V     = (2 + 0.3*p) / (2 + p + 0.6*p**2)        (|A|, <= 1)
  reference field        E0    = CMF / R    (P.368: 300 V CMF -> 300 mV/m at 1 km)
  ground-wave field      E     = E0 * V

Reference source of the P.368 curves: a short vertical monopole on a perfectly
conducting plane earth radiating 1 kW gives 300 mV/m at 1 km (CMF = 300 V, gain
g = 3 / 4.8 dBi). CMF = sqrt(30*g*P) = sqrt(30*EIRP). Field in dB(uV/m) =
20*log10(E[V/m]) + 120.

Validity: flat-earth surface wave, ~10 kHz–30 MHz, d up to ~100 km — beyond that
curved-earth diffraction takes over and this model over-attenuates. For the full
0.01–30 MHz / up-to-10000-km range use :func:`spherical_field_strength_dbuv_m`
(the ITU-R P.368-10 flat-earth-Sommerfeld + Wait/Hufford residue-series engine in
:mod:`emstudio.coverage.lfmf`, needs scipy). ``millington_field_dbuv_m`` handles
mixed-conductivity (e.g. land/sea) paths via Millington's forward+reverse average
on either engine (``spherical=True`` per P.368-10 Annex 2).

Pure-python (math/cmath), Qt-free, FreeCAD-free. SI: metres, Hz; field in dB(uV/m).
Transmitter locations/ground are user-supplied; no specific sites referenced.
"""
from __future__ import annotations

import cmath
import math

C0 = 299792458.0
EPS0 = 8.8541878128e-12

# ITU-R P.368 Table 2 ground-constant presets: name -> (eps_r, sigma S/m). Sea
# water uses the P.368/GRWAVE curve default eps_r = 70 (Table 2 lists 80; 70 is the
# common code default). "Average ground" (13, 0.005) matches the NEC2 GroundType
# default so the two ground models stay consistent.
GROUND_TYPES = {
    "Sea water": (70.0, 5.0),
    "Fresh water": (80.0, 3.0e-3),
    "Wet ground": (30.0, 1.0e-2),
    "Average ground": (13.0, 5.0e-3),
    "Medium dry ground": (15.0, 1.0e-3),
    "Dry ground": (7.0, 3.0e-4),
    "Very dry ground": (3.0, 1.0e-4),
}

# P.368 reference: short vertical monopole over perfect ground (gain 3 = 4.8 dBi).
P368_REF_GAIN_DBI = 4.77


def complex_permittivity(eps_r, sigma, freq_hz):
    """Complex relative permittivity eps_c = eps_r - j*60*lambda*sigma."""
    lam = C0 / float(freq_hz)
    return float(eps_r) - 1j * 60.0 * lam * float(sigma)


def numerical_distance(dist_m, freq_hz, eps_r, sigma):
    """(|rho|, phase_deg): the ITU Handbook complex numerical distance
    rho = -j*(pi*R/lambda)*(eps_c - 1)/eps_c**2."""
    lam = C0 / float(freq_hz)
    eps_c = complex_permittivity(eps_r, sigma, freq_hz)
    rho = -1j * (math.pi * float(dist_m) / lam) * (eps_c - 1.0) / (eps_c * eps_c)
    return abs(rho), math.degrees(cmath.phase(rho))


def attenuation_factor(p):
    """Ground-wave attenuation |A| = V from the numerical distance p (ITU Handbook
    eq 40): (2 + 0.3p) / (2 + p + 0.6p^2). ->1 for p<<1, ->1/(2p) for p>>1."""
    p = float(p)
    return max((2.0 + 0.3 * p) / (2.0 + p + 0.6 * p * p), 1e-12)


def attenuation_db(dist_m, freq_hz, eps_r, sigma):
    """Excess ground-wave loss (dB) beyond the inverse-distance field: -20log10|A|."""
    p, _ = numerical_distance(dist_m, freq_hz, eps_r, sigma)
    return -20.0 * math.log10(attenuation_factor(p))


def cmf_from_eirp(eirp_w):
    """Cymomotive force (V) from EIRP: CMF = sqrt(30*EIRP). 1 kW * gain 3 -> 300 V."""
    return math.sqrt(30.0 * max(float(eirp_w), 0.0))


def cmf_from_power(power_w, gain_dbi=P368_REF_GAIN_DBI):
    """CMF (V) from radiated power + antenna gain (P.368 default = monopole 4.8 dBi)."""
    return cmf_from_eirp(power_w * 10.0 ** (float(gain_dbi) / 10.0))


def field_strength_dbuv_m(dist_m, freq_hz, eps_r, sigma, cmf_v=300.0):
    """Ground-wave field strength (dB(uV/m)) at ``dist_m`` for a source of ``cmf_v``
    cymomotive force (default 300 V = the P.368 1 kW reference)."""
    d = max(float(dist_m), 1.0)
    p, _ = numerical_distance(d, freq_hz, eps_r, sigma)
    e_vm = (float(cmf_v) / d) * attenuation_factor(p)   # E0 = CMF/R, then * |A|
    return 20.0 * math.log10(max(e_vm, 1e-30) * 1e6)


def field_to_prx_dbm(field_dbuv_m, freq_hz, rx_gain_dbi=0.0):
    """Received power (dBm) into a matched antenna from a field strength (dB(uV/m)):
    Prx = E - 20log10(f_MHz) + G - 77.2 (standard field-to-power conversion)."""
    return (float(field_dbuv_m) - 20.0 * math.log10(freq_hz / 1e6)
            + float(rx_gain_dbi) - 77.2)


def spherical_field_strength_dbuv_m(dist_m, freq_hz, eps_r, sigma,
                                    cmf_v=300.0, n_s=301.0):
    """Spherical-earth ground-wave field strength (dB(uV/m)) — ITU-R P.368-10.

    The beyond-~100-km replacement for :func:`field_strength_dbuv_m`: drives the
    :mod:`emstudio.coverage.lfmf` engine (the numpy/scipy port of the NTIA LFMF
    reference implementation that IS Recommendation P.368-10) with ground-based
    terminals — the P.368 reference-curve geometry. Valid 0.01–30 MHz and
    0.001–10000 km; frequencies below 10 kHz raise (ionospheric/P.684 band —
    the engine refuses to extrapolate). Needs scipy.
    """
    from emstudio.coverage import lfmf
    return lfmf.field_strength_dbuv_m(dist_m, freq_hz, eps_r, sigma,
                                      cmf_v=cmf_v, n_s=n_s)


def millington_field_dbuv_m(segments, freq_hz, cmf_v=300.0, spherical=False):
    """Mixed-path ground-wave field (dB(uV/m)) via Millington's method.

    ``segments`` = ``[(length_m, eps_r, sigma), ...]`` in tx->rx order. Millington's
    forward + reverse average makes the result reciprocal (tx<->rx swap gives the
    same field) and models the coastline 'recovery' when a better-conducting section
    lies toward the receiver. With ``spherical=True`` the homogeneous engine under
    the walk is the P.368-10 spherical earth (P.368-10 Annex 2; needs scipy);
    the default remains the flat-earth engine, byte-identical to prior releases.
    """
    field = (spherical_field_strength_dbuv_m if spherical
             else field_strength_dbuv_m)

    def walk(segs):
        total_db = 0.0
        d_prev = 0.0
        for (length, eps_r, sigma) in segs:
            d_now = d_prev + float(length)
            e_now = field(d_now, freq_hz, eps_r, sigma, cmf_v)
            if d_prev <= 0.0:
                total_db += e_now
            else:
                total_db += e_now - field(d_prev, freq_hz, eps_r, sigma, cmf_v)
            d_prev = d_now
        return total_db

    fwd = walk(list(segments))
    rev = walk(list(reversed(segments)))
    return 0.5 * (fwd + rev)
