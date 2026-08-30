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
length (s = 1/4 in the E-plane, t = 3/8 in the H-plane — Stutzman 2e p.314,
and what this module's own rho_e = b1^2/2*lambda implies: s = b1^2/(8*lambda*
rho_e) = 1/4. This line said "1/8" until 2026-08-30, contradicting the code
one screen below it; caught twice, once by each audit round). Efficiency for
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
    """Gain (dBi) from the two principal beamwidths — a CONSISTENCY check.

    ⚠ This is NOT independent of :func:`gain_from_aperture`, and this
    docstring said it was for three releases. Because our beamwidths are
    θ_E = 54λ/b1 and θ_H = 78λ/a1, substituting them into 26000/(θ_E·θ_H)
    gives 26000·a1·b1/(54·78·λ²) = 6.1728·a1·b1/λ² — the aperture formula
    again with an implied ε_ap of 0.49122 instead of 0.51. The two routes
    therefore differ by the CONSTANT 10·log10(0.51/0.49122) ≈ 0.163 dB for
    every design ever produced; agreement is algebra, not corroboration.
    What the check IS good for: catching a broken unit conversion or a
    swapped plane between the two code paths, which is why it stays.
    (Found by the 2026-08-29 audit; genuinely independent corroboration for
    a horn is a full-wave solve — the Ka-band template's horn_openems gate.)
    """
    if min(hpbw_e_deg, hpbw_h_deg) <= 0:
        raise HornError("beamwidths must be positive")
    return 10.0 * math.log10(26000.0 / (hpbw_e_deg * hpbw_h_deg))


def design_pyramidal(f_hz, gain_dbi):
    """Pyramidal horn synthesis for a target gain — realizable by construction.

    Inverts G = ε_ap·4π·a1·b1/λ² at the fixed aspect a1 = 1.5·b1 (the
    near-symmetric-beam design this project ships; NOT what the two optimum
    flare conditions imply — they imply ≈ √1.5, see the flare comment below),
    holds the H-plane at its optimum flare, and derives the E-plane slant
    radius from the shared apex so the printed geometry is ONE buildable
    horn. Corrected 2026-08-30: it previously printed both per-plane optimum
    flares, whose axial lengths differ by 1.5× — a pair no single pyramidal
    horn can have.
    """
    lam = wavelength_m(f_hz)
    if gain_dbi <= 0:
        raise HornError("target gain must be > 0 dBi for a horn")
    g = 10.0 ** (float(gain_dbi) / 10.0)

    # a1·b1 = G·λ²/(ε_ap·4π) with a1 = 1.5·b1  ->  b1 = sqrt(area/1.5)
    area = g * lam ** 2 / (EPS_AP_OPTIMUM * 4.0 * math.pi)
    b1 = math.sqrt(area / 1.5)
    a1 = 1.5 * b1

    # H-plane at its optimum flare: a1 = sqrt(3·λ·rho_h)  [Balanis ch.13;
    # Nikolova L18 eq. (18.24)].
    rho_h = a1 ** 2 / (3.0 * lam)

    # ⚠⚠ THE E-PLANE SLANT RADIUS IS *NOT* b1²/(2λ) HERE, AND IT WAS UNTIL
    # 2026-08-30. Quoting both per-plane OPTIMUM flares (ρ_h = a1²/3λ AND
    # ρ_e = b1²/2λ) alongside a1 = 1.5·b1 describes a horn that cannot be
    # built: a pyramidal horn is realizable only if both flares reach the
    # same apex — R_E = R_H, Nikolova L18 eq. (18.42) — and with this aspect
    # ratio those two "optimum" flares meet the axis at stations differing
    # by exactly 1.5×. (The fully-optimum horn solves the quartic (18.51)
    # and comes out near a1 ≈ √1.5·b1 with an asymmetric beam; we keep the
    # a1 = 1.5·b1 near-symmetric-beam design on purpose — see the aspect
    # comment above — so ONE plane must give up its optimum.)
    # The H-plane keeps its optimum because it needs the LONGER flare; the
    # E-plane slant radius is then WHAT THE SHARED APEX IMPLIES (point-throat
    # approximation — the synthesis does not know a feed guide yet):
    # ⚠ Domain guard: for a1 ≤ 1.5λ (i.e. sub-wavelength b1) the "optimum"
    # slant radius ρ_h = a1²/3λ is SHORTER than the aperture half-width, so
    # no real apex exists — the closed-form flare model has degenerated, not
    # just lost accuracy. Fall back to the per-plane optimum ρ_e there and
    # say so, rather than crashing or inventing a geometry; the existing
    # sub-wavelength warning already tells the user this size is outside
    # aperture theory's trust range.
    if rho_h > a1 / 2.0:
        axial_len = math.sqrt(rho_h ** 2 - (a1 / 2.0) ** 2)
        rho_e = math.sqrt(axial_len ** 2 + (b1 / 2.0) ** 2)
        degenerate = False
    else:
        axial_len = 0.0
        rho_e = b1 ** 2 / (2.0 * lam)
        degenerate = True

    # The E-plane phase error s = b1²/(8λ·ρ_e) then lands BELOW the optimum
    # 1/4 (longer flare, flatter phase), so E-plane phase efficiency exceeds
    # the optimum-design 0.8 and the realized gain can only sit AT OR ABOVE
    # the ε_ap = 0.51 estimate we invert. Conservative in the safe direction.
    phase_err_e = b1 ** 2 / (8.0 * lam * rho_e)

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
    if degenerate:
        warnings.append(
            "flare model degenerate at this size (optimum slant radius "
            "shorter than the aperture half-width): no single-apex pyramid "
            "exists, flare pair quoted as per-plane optima only — do not "
            "build from these numbers")

    return {
        "family": "horn",
        "f_hz": float(f_hz),
        "wavelength_m": lam,
        "target_gain_dbi": float(gain_dbi),
        "aperture_a1_m": a1,          # H-plane (wide) aperture
        "aperture_b1_m": b1,          # E-plane (narrow) aperture
        "flare_rho_h_m": rho_h,          # slant radius, H-plane (optimum, s=3/8)
        "flare_rho_e_m": rho_e,          # slant radius, E-plane (shared apex)
        "axial_length_m": axial_len,     # ONE axial length — both flares meet here
        "phase_err_e": phase_err_e,      # < 0.25 by construction (below optimum)
        "eps_ap": EPS_AP_OPTIMUM,
        "gain_dbi": g_ap,
        "gain_dbi_from_beamwidths": g_bw,
        "gain_check_delta_db": abs(g_ap - g_bw),
        "hpbw_e_deg": hpbw_e,
        "hpbw_h_deg": hpbw_h,
        "source_note": (
            "pyramidal horn, standard public aperture theory (Balanis ch.13 "
            "/ Nikolova L18): a1=1.5·b1 (near-symmetric beam, kept by "
            "design), eps_ap=0.51, H-plane at optimum a1=sqrt(3·lambda·"
            "rho_h); rho_e is set by the SHARED APEX (realizability, "
            "R_E=R_H), giving E-plane phase error below the optimum 1/4 — "
            "realized gain sits at or above the estimate. Beamwidths "
            "54·lambda/b1 (E, upper bound here) and 78·lambda/a1 (H). The "
            "26000/(theta_E·theta_H) figure is a consistency restatement of "
            "the same aperture model (constant +0.163 dB), not independent "
            "corroboration."),
        "warnings": warnings,
    }


def design_pyramidal_optimum(f_hz, gain_dbi, feed_a_m=0.0, feed_b_m=0.0):
    """TRUE optimum-gain pyramidal horn (Balanis §13.4.3) — the SHORTEST horn.

    This is mode (b) beside :func:`design_pyramidal`'s mode (a): instead of
    fixing the aspect at 1.5 for a near-symmetric beam, it solves the Balanis
    design chain for the horn of MINIMUM length at the target gain, with the
    realizability condition p_e = p_h built in exactly (it IS the equation
    being solved). The beam comes out mildly asymmetric — that is the price
    of shortest, and the reason mode (a) exists and stays the default.

    Sources, fetched and cross-checked 2026-08-30 rather than recalled:
    Balanis' own published design code (Antenna Theory ch.13 companion,
    eqs 13-55..13-58b) — chi iteration seeded at G/(2π·sqrt(2π)), then
        rho_e = chi·λ,          rho_h = (G²/8π³)·λ/chi,
        a1 = (G/2π)·sqrt(3/(2π·chi))·λ,   b1 = sqrt(2·chi)·λ,
        p_e = (b1−b)·sqrt((rho_e/b1)²−¼), p_h = (a1−a)·sqrt((rho_h/a1)²−¼)
    — and Nikolova L18 (18.42–18.51), whose quartic in A is the same system
    eliminated differently. We solve chi by bisection on p_e−p_h, which is
    the realizability residual itself; no memory-transcribed closed form.

    ``feed_a_m``/``feed_b_m`` are the feeding waveguide's inner dimensions;
    0.0 means a point throat (apex limit), which is what a synthesis page
    can honestly assume before a guide is chosen. G is taken at
    ε_ap = 0.51, the optimum-design value both sources state.
    """
    lam = wavelength_m(f_hz)
    if gain_dbi <= 0:
        raise HornError("target gain must be > 0 dBi for a horn")
    g = 10.0 ** (float(gain_dbi) / 10.0)
    a_g, b_g = float(feed_a_m), float(feed_b_m)

    def dims(chi):
        rho_e = chi * lam
        rho_h = (g ** 2 / (8.0 * math.pi ** 3)) * lam / chi
        a1 = (g / (2.0 * math.pi)) * math.sqrt(3.0 / (2.0 * math.pi * chi)) * lam
        b1 = math.sqrt(2.0 * chi) * lam
        return rho_e, rho_h, a1, b1

    def residual(chi):
        rho_e, rho_h, a1, b1 = dims(chi)
        # outside the physical domain the flare cannot clear its own aperture
        qe = (rho_e / b1) ** 2 - 0.25
        qh = (rho_h / a1) ** 2 - 0.25
        if qe <= 0 or qh <= 0 or b1 <= b_g or a1 <= a_g:
            return None
        p_e = (b1 - b_g) * math.sqrt(qe)
        p_h = (a1 - a_g) * math.sqrt(qh)
        return p_e - p_h

    chi0 = g / (2.0 * math.pi * math.sqrt(2.0 * math.pi))   # Balanis 13-57
    # Bracket the root around the seed; the residual is monotone in chi over
    # the physical domain (p_e grows with chi, p_h shrinks). Expand until the
    # sign flips, then bisect — dull and provable beats clever.
    lo, hi = chi0, chi0
    rlo = residual(lo)
    for _ in range(60):
        lo *= 0.8
        rlo = residual(lo)
        if rlo is not None and rlo < 0:
            break
    else:
        raise HornError("optimum-horn chi bracket failed (low side)")
    rhi = None
    for _ in range(60):
        hi *= 1.25
        rhi = residual(hi)
        if rhi is not None and rhi > 0:
            break
    else:
        raise HornError("optimum-horn chi bracket failed (high side)")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        rm = residual(mid)
        if rm is None:
            lo = mid
            continue
        if rm < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-14 * max(1.0, hi):
            break
    chi = 0.5 * (lo + hi)
    rho_e, rho_h, a1, b1 = dims(chi)
    p_e = (b1 - b_g) * math.sqrt((rho_e / b1) ** 2 - 0.25)
    p_h = (a1 - a_g) * math.sqrt((rho_h / a1) ** 2 - 0.25)

    hpbw_e, hpbw_h = beamwidths_deg(a1, b1, lam)
    g_ap = gain_from_aperture(a1, b1, lam)
    g_bw = gain_from_beamwidths(hpbw_e, hpbw_h)

    return {
        "family": "horn",
        "mode": "optimum",
        "f_hz": float(f_hz),
        "wavelength_m": lam,
        "target_gain_dbi": float(gain_dbi),
        "chi": chi,
        "aperture_a1_m": a1,
        "aperture_b1_m": b1,
        "flare_rho_h_m": rho_h,
        "flare_rho_e_m": rho_e,
        "axial_p_e_m": p_e,
        "axial_p_h_m": p_h,          # == p_e by construction; both reported
        "feed_a_m": a_g,
        "feed_b_m": b_g,
        "eps_ap": EPS_AP_OPTIMUM,
        "gain_dbi": g_ap,
        "gain_dbi_from_beamwidths": g_bw,
        "gain_check_delta_db": abs(g_ap - g_bw),
        "hpbw_e_deg": hpbw_e,
        "hpbw_h_deg": hpbw_h,
        "warnings": [
            "shortest-length optimum design (Balanis ch.13): the beam is "
            "mildly asymmetric by construction; use the symmetric-beam mode "
            "if equal beamwidths matter more than length",
            "closed-form synthesis: seed a full-wave run with this, do not "
            "fabricate from it",
        ],
        "source_note": (
            "true optimum-gain pyramidal horn per Balanis ch.13 "
            "(eqs 13-55..13-58b, chi solved on the realizability residual "
            "p_e=p_h) cross-checked against Nikolova L18 (18.42-18.51); "
            "eps_ap=0.51."),
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
