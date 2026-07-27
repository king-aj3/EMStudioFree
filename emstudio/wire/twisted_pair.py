# SPDX-License-Identifier: LGPL-2.1-or-later
"""Analytic twisted-pair TEM electricals (ROADMAP §2 Cable Designer, phase B).

Differential (balanced) transmission-line properties of two insulated round
wires from the geometry, using the exact two-wire line plus Lefferson's
empirical twist/insulation permittivity model:

  Z0_diff = (eta0/pi) / sqrt(eps_eff) * acosh(s/d)     differential impedance
  eps_eff = eps1 + q (eps_r - eps1)                    effective permittivity
  q       = 0.25 + k * theta_deg^2                     filling factor
            k = 4e-4 (hard film/enamel), 1e-3 (soft insulation, e.g. PTFE)
  theta   = atan(T pi s)  IN DEGREES                   twist pitch angle
  VF      = 1/sqrt(eps_eff)
  C'      = pi eps0 eps_eff / acosh(s/d)               capacitance / length
  L'      = (mu0/pi) acosh(s/d)                        inductance / length

with s = centre-to-centre spacing (= one insulated-wire OD for a tight twist),
d = BARE conductor diameter, T = twists per metre. The acosh form is the exact
electrostatic two-wire solution at ALL spacings (it carries the proximity
charge redistribution); the familiar ln(2s/d)/276-log10 forms are far-spacing
approximations (+5.3 % at s/d = 2) and are NOT used here.

UNITS TRAP (the model's dominant failure mode): theta is in DEGREES in the q
fit. At least two public implementations evaluate it in radians, collapsing q
to ~0.25 and erasing the measured ~30 % Z0 reduction at 45 deg — the gate pins
the degrees-correct value AND rejects the radians one. q exceeds 1 above
43.3 deg (film) / 27.4 deg (soft): an accepted artifact of the empirical fit
(insulation deformation proxy) — flagged, not clamped. Optimum twist 20-45 deg;
wire breaks near ~50.5 deg.

Shielded pair (RDRE thin-wire form, shield inner diameter D):

  Z0_diff = (eta0/pi)/sqrt(eps_eff) * ln[(2s/d) (1-(s/D)^2)/(1+(s/D)^2)]

valid for thin wires (d/s <~ 0.4: +2 % vs the exact Miller solution at 0.4,
+5 % at 0.6 — the gate anchors both); D -> inf recovers the open pair. Modes:
Z_odd = Z_diff/2 (symmetric pair). Conductor loss uses the proximity-exact
two-wire resistance R' = (2 Rs/(pi d)) x/sqrt(x^2-1), x = s/d (Pozar tbl 2.1).

For real cables the honest eps_eff comes from the datasheet NVP
(eps_eff = 1/VF^2) rather than the bulk insulation value — ``analyze(nvp=)``
does that (the Cat5e/Cat6 presets use it), and ``z0_from_c_vf`` gives the
datasheet identity Z0 = 1/(v C') used to gate shielded Belden anchors.

Sources (2026-07-09 de-risk research + adversarial cross-check): P. Lefferson,
"Twisted Magnet Wire Transmission Line," IEEE Trans. Parts, Hybrids & Packaging
PHP-7(4) 1971, DOI 10.1109/TPHP.1971.1136426 (via the convergent Qucs technote
eqs. 13.7-13.11, Keller/Springer 2023 ch. 7, and a paper-in-hand Usenet
reproduction that settled the degrees convention against measurement);
"Reference Data for Radio Engineers" shielded-pair form anchored to Miller's
exact capacitances (BSTJ 51(3) 1972, Table IV); Belden 8262-style primary
datasheets for Cat5e/Cat6 geometry (Belden 1583A/2412, CommScope CS31CM,
construction patents for lay ranges); TIA-568 100 +/- 15 ohm fitted band.

Pure-python (math), Qt-free, FreeCAD-free. SI in (metres, Hz, S/m); dB out.
"""
from __future__ import annotations

import math

C0 = 299792458.0
MU0 = 4.0e-7 * math.pi
EPS0 = 8.8541878128e-12
ETA0 = math.sqrt(MU0 / EPS0)          # ~376.73 ohm (exact -> TEM identities hold)
SIGMA_CU = 5.8e7                      # annealed copper (S/m)

# Lefferson filling-factor coefficients (theta in DEGREES)
Q_COEFF = {"film": 4.0e-4, "soft": 1.0e-3}

# UTP geometry presets from the primary datasheets/patents behind the gate
# (Belden 1583A / 2412 NVP + 24/23 AWG conductors; insulated-conductor ODs from
# the Belden construction patent embodiment and the CommScope CS31CM sheet).
# eps_eff comes from the datasheet NVP (nvp key), NOT bulk insulation eps_r —
# the fitted-impedance band is 100 +/- 15 ohm (superseded TIA/EIA-568-B.2
# requirement still printed by manufacturers). Shielded 120/78-ohm data cables
# (RS-485 / twinax) are NOT geometry presets: their published constructions
# omit the shield cavity, so they gate the z0_from_c_vf identity instead.
PRESETS = {
    "Cat5e U/UTP pair (24 AWG, PO)": {
        "d_m": 0.511e-3, "s_m": 0.993e-3, "eps_r": 2.3, "tan_delta": 2.0e-4,
        "insulation": "film", "nvp": 0.70, "lay_m": 15e-3,
        "note": "24 AWG solid Cu, polyolefin/HDPE; insulated OD 0.993 mm "
                "(Belden construction patent), NVP 0.70 (Belden 1583A) -> "
                "eps_eff 2.04. Fitted impedance 100 +/- 15 ohm (1-100 MHz); "
                "geometry model lands ~108 ohm (high side of the band; the "
                "long-lay 0.92 mm OD variant gives ~100). Per-pair lays "
                "~9-23 mm.",
    },
    "Cat6 U/UTP pair (23 AWG, PO)": {
        "d_m": 0.573e-3, "s_m": 1.029e-3, "eps_r": 2.3, "tan_delta": 2.0e-4,
        "insulation": "film", "nvp": 0.70, "lay_m": 12e-3,
        "note": "23 AWG solid Cu; diameter-over-insulated-conductor 1.029 mm "
                "(CommScope CS31CM), NVP 0.70 (Belden 2412) -> eps_eff 2.04. "
                "Geometry model = 99.9 ohm vs the 100 +/- 15 ohm band — the "
                "cleanest single anchor.",
    },
}


def twist_angle_deg(twists_per_m, s_m):
    """Pitch angle theta = atan(T pi s), in DEGREES (T = twists per metre)."""
    return math.degrees(math.atan(float(twists_per_m) * math.pi * float(s_m)))


def q_factor(theta_deg, insulation="film"):
    """Lefferson filling factor q = 0.25 + k theta_deg^2 (k per insulation).

    theta_deg MUST be in degrees. q > 1 (theta above ~43.3 deg film /
    ~27.4 deg soft) is the fit's documented unphysical-looking regime
    (eps_eff can exceed the insulation's own eps_r) — returned as-is.
    """
    return 0.25 + Q_COEFF[insulation] * float(theta_deg) ** 2


def eps_effective(eps_r, theta_deg, insulation="film", eps_medium=1.0):
    """Effective permittivity eps1 + q (eps_r - eps1) of the twisted pair."""
    return float(eps_medium) + q_factor(theta_deg, insulation) * (
        float(eps_r) - float(eps_medium))


def z0_diff_ohm(s_m, d_m, eps_eff):
    """Differential Z0 (ohm): exact two-wire acosh form, homogeneous eps_eff."""
    return (ETA0 / math.pi) / math.sqrt(float(eps_eff)) * math.acosh(s_m / d_m)


def z0_shielded_ohm(s_m, d_m, shield_id_m, eps_eff):
    """Differential Z0 of a symmetric pair inside a shield (RDRE thin-wire).

    Valid for d/s <~ 0.4 (+2 % vs exact; +5 % at d/s = 0.6). The shield
    factor < 1 lowers Z0; shield_id_m -> inf recovers the open-pair ln form.
    """
    sigma2 = (s_m / shield_id_m) ** 2
    arg = (2.0 * s_m / d_m) * (1.0 - sigma2) / (1.0 + sigma2)
    return (ETA0 / math.pi) / math.sqrt(float(eps_eff)) * math.log(arg)


def capacitance_f_m(s_m, d_m, eps_eff):
    """Capacitance per length (F/m): pi eps0 eps_eff / acosh(s/d)."""
    return math.pi * EPS0 * float(eps_eff) / math.acosh(s_m / d_m)


def inductance_h_m(s_m, d_m):
    """(External) inductance per length (H/m): (mu0/pi) acosh(s/d)."""
    return MU0 / math.pi * math.acosh(s_m / d_m)


def length_factor(theta_deg):
    """Wire length per unit line length, 1/cos(theta) (1.0 untwisted)."""
    return 1.0 / math.cos(math.radians(float(theta_deg)))


def z0_from_c_vf(c_f_m, vf):
    """Datasheet identity Z0 = 1/(v C') — how shielded cables are gated."""
    return 1.0 / (float(vf) * C0 * float(c_f_m))


def lay_for_z0(z0_target_ohm, d_m, s_m, eps_r, insulation="film",
               theta_max_deg=50.0):
    """Twist lay (m/turn) that hits a target differential Z0 (Lefferson mode).

    Z0 falls monotonically with twist angle (gated), so bisect theta in
    (0, theta_max_deg]. Raises ValueError when the target is outside the
    achievable [Z0(theta_max), Z0(0)] window for this geometry/insulation
    (more twist can't raise Z0, and ~50 deg is the manufacturing limit).
    Returns (lay_m, theta_deg).
    """
    z0 = float(z0_target_ohm)
    z_hi = z0_diff_ohm(s_m, d_m, eps_effective(eps_r, 0.0, insulation))
    z_lo = z0_diff_ohm(s_m, d_m, eps_effective(eps_r, theta_max_deg, insulation))
    if not (z_lo <= z0 <= z_hi):
        raise ValueError(
            "target {0:.1f} ohm outside the achievable {1:.1f}-{2:.1f} ohm "
            "window (0-{3:g} deg twist)".format(z0, z_lo, z_hi, theta_max_deg))
    lo, hi = 0.0, float(theta_max_deg)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if z0_diff_ohm(s_m, d_m, eps_effective(eps_r, mid, insulation)) > z0:
            lo = mid   # not enough twist yet — Z0 still above target
        else:
            hi = mid
    theta = 0.5 * (lo + hi)
    lay = math.pi * s_m / math.tan(math.radians(theta)) if theta > 1e-12 \
        else float("inf")
    return lay, theta


def conductor_loss_db_m(freq_hz, s_m, d_m, eps_eff, sigma=SIGMA_CU):
    """Conductor attenuation (dB/m): proximity-exact two-wire resistance
    R' = (2 Rs/(pi d)) x/sqrt(x^2-1), x = s/d; alpha_c = R'/(2 Z0)."""
    rs = math.sqrt(math.pi * float(freq_hz) * MU0 / float(sigma))
    x = s_m / d_m
    r_per_m = (2.0 * rs / (math.pi * d_m)) * x / math.sqrt(x * x - 1.0)
    alpha = r_per_m / (2.0 * z0_diff_ohm(s_m, d_m, eps_eff))   # nepers/m
    return 8.685889638 * alpha


def dielectric_loss_db_m(freq_hz, eps_eff, tan_delta):
    """Dielectric attenuation (dB/m): 8.686 (pi f sqrt(eps_eff)/c) tan_delta."""
    alpha = math.pi * float(freq_hz) * math.sqrt(float(eps_eff)) / C0 \
        * float(tan_delta)
    return 8.685889638 * alpha


def attenuation_db_per_100m(freq_hz, s_m, d_m, eps_eff, tan_delta,
                            sigma=SIGMA_CU):
    """Total smooth-conductor attenuation (dB per 100 m)."""
    return 100.0 * (conductor_loss_db_m(freq_hz, s_m, d_m, eps_eff, sigma)
                    + dielectric_loss_db_m(freq_hz, eps_eff, tan_delta))


def analyze(d_m, s_m, eps_r, tan_delta, twists_per_m, insulation="film",
            shield_id_m=0.0, nvp=None, freq_hz=100e6, sigma=SIGMA_CU):
    """One-call twisted-pair report dict.

    eps_eff source: ``nvp`` (datasheet velocity, eps_eff = 1/nvp^2 — the
    honest route for real cables) when given, else the Lefferson twist model
    from (eps_r, twist angle, insulation). ``shield_id_m`` > 0 switches Z0 to
    the RDRE shielded form (same eps_eff).

    Keys: ``z0_diff_ohm``, ``z0_odd_ohm``, ``eps_eff``, ``eps_eff_source``,
    ``theta_deg``, ``q``, ``q_exceeds_1``, ``velocity_factor``,
    ``capacitance_pf_m``, ``inductance_nh_m``, ``length_factor``,
    ``conductor_db_100m``, ``dielectric_db_100m``, ``attenuation_db_100m``,
    ``shielded``, ``thin_wire_ok``, ``freq_hz``.
    """
    theta = twist_angle_deg(twists_per_m, s_m)
    q = q_factor(theta, insulation)
    if nvp:
        e_eff = 1.0 / float(nvp) ** 2
        source = "nvp"
    else:
        e_eff = eps_effective(eps_r, theta, insulation)
        source = "lefferson"
    shielded = shield_id_m and shield_id_m > 0.0
    if shielded:
        z0 = z0_shielded_ohm(s_m, d_m, shield_id_m, e_eff)
    else:
        z0 = z0_diff_ohm(s_m, d_m, e_eff)
    ac = 100.0 * conductor_loss_db_m(freq_hz, s_m, d_m, e_eff, sigma)
    ad = 100.0 * dielectric_loss_db_m(freq_hz, e_eff, tan_delta)
    return {
        "z0_diff_ohm": z0,
        "z0_odd_ohm": z0 / 2.0,
        "eps_eff": e_eff,
        "eps_eff_source": source,
        "theta_deg": theta,
        "q": q,
        "q_exceeds_1": q > 1.0,
        "velocity_factor": 1.0 / math.sqrt(e_eff),
        "capacitance_pf_m": capacitance_f_m(s_m, d_m, e_eff) * 1e12,
        "inductance_nh_m": inductance_h_m(s_m, d_m) * 1e9,
        "length_factor": length_factor(theta),
        "conductor_db_100m": ac,
        "dielectric_db_100m": ad,
        "attenuation_db_100m": ac + ad,
        "shielded": bool(shielded),
        "thin_wire_ok": (not shielded) or (d_m / s_m <= 0.4),
        "freq_hz": float(freq_hz),
    }
