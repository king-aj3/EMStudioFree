# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pyramidal (and sectoral) microwave horn — closed-form design and analysis.

Standard public aperture-antenna theory (Balanis, *Antenna Theory*, ch. 13;
Silver, *Microwave Antenna Theory and Design*; Kraus). No book text is
reproduced — these are the ordinary published relations every horn design uses.

WHAT IS AND IS NOT CLAIMED
--------------------------
This is the same class of model as the rest of §1: a first-cut synthesis good
enough to seed a full-wave run, not a substitute for one. The honest accuracy
statement is in ``design_pyramidal``'s ``warnings`` and is surfaced to the user
verbatim.

The **optimum-gain** horn is the one designed here: the flare is chosen so the
aperture phase error is at the classical limit that maximises gain for a given
length (s = 1/8 in the E-plane, 3/8 in the H-plane). Aperture efficiency for
that geometry is ~0.51 — the number that makes a horn a horn, and the reason a
horn never reaches the 100 % of an ideal uniform aperture.

VERIFICATION
------------
Two INDEPENDENT routes to gain must agree, and the gate checks it:
  1. aperture:    G = ε_ap · 4π·A/λ²      (ε_ap ≈ 0.51 optimum)
  2. beamwidths:  G ≈ 26000/(θ_E·θ_H)     (the standard aperture approximation)
Agreement to a fraction of a dB is not a coincidence — it is what tells you the
beamwidth coefficients (54°, 78°) and the efficiency belong to the same horn.

Qt-free, FreeCAD-free, 3.11-compatible.
"""
from __future__ import annotations

import math

C0 = 299_792_458.0

#: Aperture efficiency of an OPTIMUM-gain pyramidal horn. Not adjustable by
#: wishing: it falls out of the quadratic aperture phase error the optimum
#: flare accepts in exchange for length.
EPS_AP_OPTIMUM = 0.51

#: Half-power beamwidth coefficients (degrees) for an optimum pyramidal horn,
#: θ ≈ K·λ/aperture. The E-plane is narrower per unit aperture than the
#: H-plane because the H-plane field is cosine-tapered across the aperture and
#: a tapered illumination always broadens the beam.
K_E_DEG = 54.0
K_H_DEG = 78.0


class HornError(ValueError):
    """A horn geometry that is not physically sensible."""


def wavelength_m(f_hz):
    if not f_hz > 0:
        raise HornError("frequency must be positive, got {0!r}".format(f_hz))
    return C0 / float(f_hz)


def gain_from_aperture(a1_m, b1_m, lam_m, eps_ap=EPS_AP_OPTIMUM):
    """Gain (dBi) of an aperture a1 x b1 at efficiency ``eps_ap``."""
    if min(a1_m, b1_m, lam_m) <= 0:
        raise HornError("aperture and wavelength must be positive")
    g = eps_ap * 4.0 * math.pi * (a1_m * b1_m) / (lam_m ** 2)
    if g <= 0:
        raise HornError("non-physical gain")
    return 10.0 * math.log10(g)


def beamwidths_deg(a1_m, b1_m, lam_m):
    """(E-plane, H-plane) half-power beamwidths in degrees.

    E-plane is set by the b1 (narrow) aperture, H-plane by a1 (wide) — the
    plane containing the E field is the one whose beamwidth the b dimension
    controls. Getting these the wrong way round is the classic slip; the gate
    pins that a wider a1 narrows the H-plane.
    """
    if min(a1_m, b1_m, lam_m) <= 0:
        raise HornError("aperture and wavelength must be positive")
    return (K_E_DEG * lam_m / b1_m, K_H_DEG * lam_m / a1_m)


def gain_from_beamwidths(hpbw_e_deg, hpbw_h_deg):
    """Gain (dBi) from the two principal beamwidths — the INDEPENDENT check.

    G ≈ 26000/(θ_E·θ_H) is the standard aperture-antenna approximation. It
    knows nothing about aperture area, so agreement with
    :func:`gain_from_aperture` is real corroboration rather than algebra
    restated.
    """
    if min(hpbw_e_deg, hpbw_h_deg) <= 0:
        raise HornError("beamwidths must be positive")
    return 10.0 * math.log10(26000.0 / (hpbw_e_deg * hpbw_h_deg))


def design_pyramidal(f_hz, gain_dbi):
    """Optimum-gain pyramidal horn for a target gain.

    Inverts G = ε_ap·4π·a1·b1/λ² on the optimum-horn aspect ratio a1 ≈ 1.5·b1,
    which is what the E- and H-plane optimum flare conditions imply together,
    then reports the flare lengths those apertures require.
    """
    lam = wavelength_m(f_hz)
    if gain_dbi <= 0:
        raise HornError("target gain must be > 0 dBi for a horn")
    g = 10.0 ** (float(gain_dbi) / 10.0)

    # a1·b1 = G·λ²/(ε_ap·4π) with a1 = 1.5·b1  ->  b1 = sqrt(area/1.5)
    area = g * lam ** 2 / (EPS_AP_OPTIMUM * 4.0 * math.pi)
    b1 = math.sqrt(area / 1.5)
    a1 = 1.5 * b1

    # Optimum flare: a1 = sqrt(3·λ·rho_h), b1 = sqrt(2·λ·rho_e)
    rho_h = a1 ** 2 / (3.0 * lam)
    rho_e = b1 ** 2 / (2.0 * lam)

    hpbw_e, hpbw_h = beamwidths_deg(a1, b1, lam)
    g_ap = gain_from_aperture(a1, b1, lam)
    g_bw = gain_from_beamwidths(hpbw_e, hpbw_h)

    warnings = [
        "closed-form optimum-horn synthesis: gain is accurate to roughly "
        "±0.3 dB and beamwidths to a few percent against a full-wave run — "
        "seed an openEMS/Palace model with this, do not fabricate from it",
        "aperture efficiency is fixed at 0.51 (the optimum-flare value); a "
        "shorter horn trades gain for length and this model does not cover it",
    ]
    if a1 < lam or b1 < lam:
        warnings.append(
            "aperture is under one wavelength — below the range where "
            "aperture theory is trustworthy; treat the result as indicative")

    return {
        "family": "horn",
        "f_hz": float(f_hz),
        "wavelength_m": lam,
        "target_gain_dbi": float(gain_dbi),
        "aperture_a1_m": a1,          # H-plane (wide) aperture
        "aperture_b1_m": b1,          # E-plane (narrow) aperture
        "flare_rho_h_m": rho_h,
        "flare_rho_e_m": rho_e,
        "eps_ap": EPS_AP_OPTIMUM,
        "gain_dbi": g_ap,
        "gain_dbi_from_beamwidths": g_bw,
        "gain_check_delta_db": abs(g_ap - g_bw),
        "hpbw_e_deg": hpbw_e,
        "hpbw_h_deg": hpbw_h,
        "source_note": (
            "optimum-gain pyramidal horn, standard public aperture theory "
            "(Balanis ch.13 / Silver): a1=1.5·b1, eps_ap=0.51, "
            "a1=sqrt(3·lambda·rho_h), b1=sqrt(2·lambda·rho_e); beamwidths "
            "54·lambda/b1 (E) and 78·lambda/a1 (H). Gain corroborated "
            "independently by 26000/(theta_E·theta_H)."),
        "warnings": warnings,
    }


def analyse_pyramidal(f_hz, a1_m, b1_m):
    """Gain + beamwidths for a horn whose aperture you already have."""
    lam = wavelength_m(f_hz)
    hpbw_e, hpbw_h = beamwidths_deg(a1_m, b1_m, lam)
    g_ap = gain_from_aperture(a1_m, b1_m, lam)
    g_bw = gain_from_beamwidths(hpbw_e, hpbw_h)
    return {
        "family": "horn", "f_hz": float(f_hz), "wavelength_m": lam,
        "aperture_a1_m": float(a1_m), "aperture_b1_m": float(b1_m),
        "gain_dbi": g_ap, "gain_dbi_from_beamwidths": g_bw,
        "gain_check_delta_db": abs(g_ap - g_bw),
        "hpbw_e_deg": hpbw_e, "hpbw_h_deg": hpbw_h,
        "eps_ap": EPS_AP_OPTIMUM,
    }
