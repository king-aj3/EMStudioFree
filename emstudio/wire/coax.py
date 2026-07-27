# SPDX-License-Identifier: LGPL-2.1-or-later
"""Analytic coaxial-line TEM electricals (ROADMAP §2 Cable Designer, phase A engine).

Closed-form coax theory from the geometry (inner radius ``a``, dielectric/shield
inner radius ``b``, relative permittivity, loss tangent):

  Z0    = (eta0 / 2pi) / sqrt(eps_r) * ln(b/a)          characteristic impedance
  VF    = 1 / sqrt(eps_r)                               velocity factor
  C'    = 2 pi eps0 eps_r / ln(b/a)                     capacitance / length
  L'    = (mu0 / 2pi) ln(b/a)                           (external) inductance / length
  fc    ~ c / (pi (a+b) sqrt(eps_r))                    TE11 cutoff (upper limit of
                                                        pure-TEM operation)
  alpha_c = R'/(2 Z0),  R' = Rs/(2pi) (1/a + 1/b),      conductor (skin) loss
            Rs = sqrt(pi f mu0 / sigma)
  alpha_d = (pi f sqrt(eps_r) / c) tan_delta            dielectric loss

The smooth-solid-conductor loss model UNDER-estimates real braided/stranded cables
(braid weave + stranding add roughly 10-30 %), so datasheet attenuation is gated
with a documented one-sided tolerance, not sub-percent. This is the Qt-free engine
slice of the general Cable Designer (the construction-selector UI comes with §2
phase A proper); the full-wave cross-check is the shipped Palace coax lumped-port
backend (``run_coax``), whose ``coax_z0`` this module matches exactly.

Pure-python (math), Qt-free, FreeCAD-free. SI in (metres, Hz, S/m); dB out.
"""
from __future__ import annotations

import math

C0 = 299792458.0
MU0 = 4.0e-7 * math.pi
EPS0 = 8.8541878128e-12
ETA0 = math.sqrt(MU0 / EPS0)          # ~376.73 ohm
SIGMA_CU = 5.8e7                      # annealed copper (S/m)

# common solid dielectrics: name -> (eps_r, tan_delta) at HF/VHF
DIELECTRICS = {
    "PE (solid polyethylene)": (2.25, 3.0e-4),
    "PTFE (solid)": (2.05, 2.0e-4),
    "Foam PE (typ. 80% VF)": (1.56, 2.0e-4),
    "Air": (1.0006, 0.0),
}

# Cable geometry presets from the PRIMARY datasheets anchoring the validation
# gate (tests/validation/cable.py): Belden 8262 (RG-58C/U) and Belden-UK /
# Pasternack RG-142B/U + MIL-DTL-17. ``a_m`` is the EFFECTIVE electrical radius:
# RG-58's 19x33 stranded centre uses the classic ~0.94x effective diameter
# (0.836 mm) that reproduces both the 50-ohm nominal and the 101 pF/m
# capacitance (the 0.889 mm physical envelope gives 47.5 ohm). ``eps_r`` /
# ``tan_delta`` are per-cable (RG-142's PTFE runs 2.04, not the generic 2.05).
PRESETS = {
    "RG-58C/U (50 ohm, solid PE)": {
        "a_m": 0.418e-3, "b_m": 1.4605e-3, "eps_r": 2.25, "tan_delta": 3.0e-4,
        "dielectric": "PE (solid polyethylene)",
        "note": "Belden 8262. 19x33 stranded centre -> 0.94x effective diameter "
                "0.836 mm (physical envelope 0.889 mm gives 47.5 ohm). "
                "Anchors: 50 ohm, VF 66%, 101 pF/m.",
    },
    "RG-142B/U (50 ohm, PTFE)": {
        "a_m": 0.470e-3, "b_m": 1.475e-3, "eps_r": 2.04, "tan_delta": 2.0e-4,
        "dielectric": "PTFE (solid)",
        "note": "Belden-UK / MIL-DTL-17. Silver-plated copper-clad-steel centre "
                "(copper conductivity assumed at RF). The canonical geometry "
                "honestly gives 48.0 ohm — the bottom of the MIL 50+/-2 window; "
                "vendors print '50 nominal'. VF 70%.",
    },
}


def coax_z0_ohm(a_m, b_m, eps_r=1.0):
    """TEM characteristic impedance (ohm). Matches the shipped Palace
    ``writer.coax_z0`` formula exactly (that one takes mm)."""
    return (ETA0 / (2.0 * math.pi)) / math.sqrt(float(eps_r)) * math.log(b_m / a_m)


def b_for_z0(a_m, z0_ohm, eps_r=1.0):
    """Dielectric radius b for a target Z0 at given inner radius (exact
    inversion of ``coax_z0_ohm``): b = a exp(2 pi Z0 sqrt(eps_r) / eta0)."""
    return a_m * math.exp(2.0 * math.pi * float(z0_ohm)
                          * math.sqrt(float(eps_r)) / ETA0)


def a_for_z0(b_m, z0_ohm, eps_r=1.0):
    """Inner radius a for a target Z0 at given dielectric radius (exact)."""
    return b_m / math.exp(2.0 * math.pi * float(z0_ohm)
                          * math.sqrt(float(eps_r)) / ETA0)


def velocity_factor(eps_r):
    """Phase-velocity fraction of c: 1/sqrt(eps_r)."""
    return 1.0 / math.sqrt(float(eps_r))


def capacitance_f_m(a_m, b_m, eps_r):
    """Capacitance per length (F/m): 2 pi eps0 eps_r / ln(b/a)."""
    return 2.0 * math.pi * EPS0 * float(eps_r) / math.log(b_m / a_m)


def inductance_h_m(a_m, b_m):
    """External inductance per length (H/m): (mu0/2pi) ln(b/a)."""
    return MU0 / (2.0 * math.pi) * math.log(b_m / a_m)


def cutoff_te11_hz(a_m, b_m, eps_r=1.0):
    """Approximate TE11 (first higher-order mode) cutoff: c/(pi (a+b) sqrt(eps_r)).
    Above this the line is no longer single-mode TEM."""
    return C0 / (math.pi * (a_m + b_m) * math.sqrt(float(eps_r)))


def surface_resistance_ohm(freq_hz, sigma=SIGMA_CU, mu_r=1.0):
    """Skin-effect surface resistance Rs = sqrt(pi f mu / sigma) (ohm/square)."""
    return math.sqrt(math.pi * float(freq_hz) * MU0 * float(mu_r) / float(sigma))


def conductor_loss_db_m(freq_hz, a_m, b_m, eps_r=1.0, sigma_inner=SIGMA_CU,
                        sigma_outer=SIGMA_CU):
    """Conductor (skin-effect) attenuation (dB/m) of a smooth solid coax."""
    rs_a = surface_resistance_ohm(freq_hz, sigma_inner)
    rs_b = surface_resistance_ohm(freq_hz, sigma_outer)
    r_per_m = (rs_a / a_m + rs_b / b_m) / (2.0 * math.pi)
    alpha = r_per_m / (2.0 * coax_z0_ohm(a_m, b_m, eps_r))   # nepers/m
    return 8.685889638 * alpha


def dielectric_loss_db_m(freq_hz, eps_r, tan_delta):
    """Dielectric attenuation (dB/m): 8.686 * (pi f sqrt(eps_r)/c) tan_delta."""
    alpha = math.pi * float(freq_hz) * math.sqrt(float(eps_r)) / C0 * float(tan_delta)
    return 8.685889638 * alpha


def attenuation_db_per_100m(freq_hz, a_m, b_m, eps_r, tan_delta,
                            sigma_inner=SIGMA_CU, sigma_outer=SIGMA_CU):
    """Total smooth-conductor attenuation (dB per 100 m) = conductor + dielectric."""
    return 100.0 * (conductor_loss_db_m(freq_hz, a_m, b_m, eps_r,
                                        sigma_inner, sigma_outer)
                    + dielectric_loss_db_m(freq_hz, eps_r, tan_delta))


def analyze(a_m, b_m, eps_r, tan_delta, freq_hz=100e6, sigma_inner=SIGMA_CU,
            sigma_outer=SIGMA_CU):
    """One-call coax report dict: Z0, VF, C'/L', TE11 cutoff, per-loss attenuation.

    Keys: ``z0_ohm``, ``velocity_factor``, ``capacitance_pf_m``,
    ``inductance_nh_m``, ``cutoff_te11_hz``, ``conductor_db_100m``,
    ``dielectric_db_100m``, ``attenuation_db_100m`` (at ``freq_hz``).
    """
    ac = 100.0 * conductor_loss_db_m(freq_hz, a_m, b_m, eps_r,
                                     sigma_inner, sigma_outer)
    ad = 100.0 * dielectric_loss_db_m(freq_hz, eps_r, tan_delta)
    return {
        "z0_ohm": coax_z0_ohm(a_m, b_m, eps_r),
        "velocity_factor": velocity_factor(eps_r),
        "capacitance_pf_m": capacitance_f_m(a_m, b_m, eps_r) * 1e12,
        "inductance_nh_m": inductance_h_m(a_m, b_m) * 1e9,
        "cutoff_te11_hz": cutoff_te11_hz(a_m, b_m, eps_r),
        "conductor_db_100m": ac,
        "dielectric_db_100m": ad,
        "attenuation_db_100m": ac + ad,
        "freq_hz": float(freq_hz),
    }
