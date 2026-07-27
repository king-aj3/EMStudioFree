# SPDX-License-Identifier: LGPL-2.1-or-later
"""Electrically-small antenna analytics (VLF / LF / MF characterization).

At VLF/LF/MF a resonant antenna is kilometres long, so practical antennas are a
tiny fraction of a wavelength — the Chu-Harrington small-antenna regime, where
the full-wave field solvers (openEMS FDTD, Palace FEM) are impractical and the
right tools are closed-form small-antenna models. This module implements the
standard textbook formulas (Balanis, *Antenna Theory*; Kraus; A.D. Watt,
*VLF Radio Engineering*) for a short dipole / short monopole:

* radiation resistance, effective height/length
* radiation efficiency from the loss budget (conductor + ground system)
* the Chu minimum-Q / bandwidth limit (electrically-small guardrail)
* the loading (series inductance) needed to resonate the capacitive reactance

All SI. Pure-python, Qt-free and FreeCAD-free (importable headless). Physical
lengths in metres, frequency in Hz. Results are dicts of plain floats.
"""
from __future__ import annotations

import math

C0 = 299792458.0
ETA0 = 376.730313668  # free-space wave impedance (ohm)
EPS0 = 8.8541878128e-12
MU0 = 1.25663706212e-6


def wavelength_m(freq_hz):
    return C0 / float(freq_hz)


def chu_min_q(radius_m, freq_hz):
    """Chu minimum radiation Q for a single-mode antenna enclosed in a sphere of
    radius ``radius_m`` (the electrically-small guardrail): Q = 1/(ka)^3 + 1/(ka).

    Diverges as (ka)->0 — the physics reason a VLF antenna is inherently narrow
    band. ``ka = 2*pi*radius/lambda``.
    """
    ka = 2.0 * math.pi * float(radius_m) / wavelength_m(freq_hz)
    if ka <= 0:
        return float("inf")
    return 1.0 / ka ** 3 + 1.0 / ka


def fractional_bandwidth(q, vswr=2.0):
    """Matched fractional bandwidth for a resonant antenna of quality factor ``q``
    at a given VSWR threshold: FBW = (S-1)/(Q*sqrt(S))."""
    if q <= 0:
        return float("inf")
    s = float(vswr)
    return (s - 1.0) / (q * math.sqrt(s))


def radiation_efficiency(r_rad, r_loss):
    """eta = Rr / (Rr + Rloss)."""
    denom = float(r_rad) + float(r_loss)
    return (float(r_rad) / denom) if denom > 0 else 0.0


def short_dipole(length_m, freq_hz, r_loss=0.0, radius_m=None, vswr=2.0):
    """Characterize a short (L << lambda) center-fed dipole, triangular current.

    Rr = 20*pi^2*(L/lambda)^2 ; effective length le = L/2 (Balanis short dipole).
    Returns radiation resistance, effective length, ka, Chu Q, bandwidth,
    efficiency, and a small-antenna flag.
    """
    L = float(length_m)
    lam = wavelength_m(freq_hz)
    r_rad = 20.0 * math.pi ** 2 * (L / lam) ** 2
    le = L / 2.0
    a = float(radius_m) if radius_m else L / 2.0  # enclosing-sphere radius
    q = chu_min_q(a, freq_hz)
    return {
        "type": "short_dipole",
        "wavelength_m": lam,
        "length_over_lambda": L / lam,
        "radiation_resistance_ohm": r_rad,
        "effective_length_m": le,
        "ka": 2.0 * math.pi * a / lam,
        "chu_min_q": q,
        "fractional_bandwidth": fractional_bandwidth(q, vswr),
        "radiation_efficiency": radiation_efficiency(r_rad, r_loss),
        "electrically_small": (L / lam) < 0.1,
    }


def short_loop(area_m2, freq_hz, turns=1, r_loss=0.0, radius_m=None, vswr=2.0):
    """Characterize an electrically-small loop (the dual of the short dipole) —
    the classic VLF/LF receive / direction-finding antenna.

    Rr = 31171 * N^2 * (A/lambda^2)^2 (Balanis small loop, = 20*pi^2*(C/lambda)^4
    for a single circular turn); effective height he = 2*pi*N*A/lambda.
    """
    A = float(area_m2)
    N = float(turns)
    lam = wavelength_m(freq_hz)
    r_rad = 31171.0 * N ** 2 * (A / lam ** 2) ** 2
    he = 2.0 * math.pi * N * A / lam
    a = float(radius_m) if radius_m else math.sqrt(A / math.pi)  # equiv. loop radius
    q = chu_min_q(a, freq_hz)
    return {
        "type": "short_loop",
        "wavelength_m": lam,
        "turns": N,
        "radiation_resistance_ohm": r_rad,
        "effective_height_m": he,
        "ka": 2.0 * math.pi * a / lam,
        "chu_min_q": q,
        "fractional_bandwidth": fractional_bandwidth(q, vswr),
        "radiation_efficiency": radiation_efficiency(r_rad, r_loss),
        "electrically_small": (2.0 * math.pi * a / lam) < 0.1,
    }


def _monopole_capacitance_f(height_m, wire_radius_m):
    """Static capacitance of a thin cylindrical monopole over a perfect ground
    (F): C ~ 2*pi*eps0*h / (ln(2h/a) - 1). An engineering estimate used to size
    the loading coil; the radiated quantities do not depend on it."""
    h = float(height_m)
    a = max(float(wire_radius_m), 1e-6)
    denom = math.log(2.0 * h / a) - 1.0
    if denom <= 0:
        return float("inf")
    return 2.0 * math.pi * EPS0 * h / denom


def short_monopole(height_m, freq_hz, r_loss=0.0, wire_radius_m=0.005,
                   radius_m=None, vswr=2.0):
    """Characterize a short vertical monopole (height h) over a perfect ground.

    Rr = 40*pi^2*(h/lambda)^2 ; effective height he = h/2. Also estimates the
    series loading inductance needed to cancel the (large, capacitive) input
    reactance and resonate the antenna: L_load = 1/(w^2 * C).
    """
    h = float(height_m)
    lam = wavelength_m(freq_hz)
    w = 2.0 * math.pi * float(freq_hz)
    r_rad = 40.0 * math.pi ** 2 * (h / lam) ** 2
    he = h / 2.0
    cap = _monopole_capacitance_f(h, wire_radius_m)
    xc = 1.0 / (w * cap) if cap > 0 else float("inf")
    l_load = 1.0 / (w ** 2 * cap) if cap > 0 else float("inf")  # resonate: wL = Xc
    a = float(radius_m) if radius_m else h  # enclosing-sphere radius ~ height
    q = chu_min_q(a, freq_hz)
    return {
        "type": "short_monopole",
        "wavelength_m": lam,
        "height_over_lambda": h / lam,
        "radiation_resistance_ohm": r_rad,
        "effective_height_m": he,
        "capacitance_f": cap,
        "capacitive_reactance_ohm": xc,
        "loading_inductance_h": l_load,
        "ka": 2.0 * math.pi * a / lam,
        "chu_min_q": q,
        "fractional_bandwidth": fractional_bandwidth(q, vswr),
        "radiation_efficiency": radiation_efficiency(r_rad, r_loss),
        "electrically_small": (h / lam) < 0.1,
        "needs_loading": xc > 10.0 * (r_rad + r_loss),
    }


def voltage_limited(freq_hz, c_farads, h_e_m, v_top_v, eta_ts=1.0,
                    f_res_hz=None, delta_c_farads=0.0):
    """Voltage-limited power capability + bandwidth of a top-loaded short
    vertical (the classic VLF set — §4 breadth, verified from the reference
    page images with exact-identity cross-checks; see
    docs/upstream/watt-topload-anchors.md).

    A VLF antenna is a VOLTAGE-limited device (insulation/corona): for
    f < f_res/2 the radiated power is P_r = (2*pi*f*C*V_t)^2 * R_r with
    R_r = 160*pi^2*(h_e/lambda)^2, i.e. P_r = (640*pi^4/c0^2) * V_t^2 *
    C^2 * h_e^2 * f^4 (the printed engineering constant 6.95e-13 is this
    coefficient with the reference's rounding). The 3-dB bandwidth of the
    resonated system is b = 2*pi*f^2*C*R_r/eta_ts = (320*pi^3/c0^2) *
    h_e^2 * f^4 * C / eta_ts (printed 1.11e-13). Base/stray shunt
    capacity delta_C reduces the apparent effective height by
    C/(C+delta_C) and the antenna-only bandwidth by the same factor,
    while the RESONATED voltage-limited P_r is unchanged.

    :param v_top_v: top-hat potential limit (volts).
    :param eta_ts: transmitting-system efficiency (R_r over the total
        series resistance incl. loss, coil and transmitter).
    :param f_res_hz: optional self-resonant frequency — warns when the
        f < f_res/2 assumption is violated.
    :param delta_c_farads: optional base/stray shunt capacity.
    Returns a dict (powers in watts, bandwidth in Hz).
    """
    f = float(freq_hz)
    c = float(c_farads)
    he = float(h_e_m)
    v = float(v_top_v)
    if f <= 0 or c <= 0 or he <= 0 or v <= 0:
        raise ValueError("frequency, C, h_e and V must be positive")
    if not 0.0 < eta_ts <= 1.0:
        raise ValueError("eta_ts must be in (0, 1]")
    warnings = []
    if f_res_hz is not None and f > 0.5 * float(f_res_hz):
        warnings.append(
            "f > f_res/2 — the simple voltage-limited form ignores the "
            "resonance rise; the true capability near f_res is higher "
            "(and above it needs series-C tuning)")
    pr_coeff = 640.0 * math.pi ** 4 / C0 ** 2      # ~6.94e-13 (printed 6.95e-13)
    bw_coeff = 320.0 * math.pi ** 3 / C0 ** 2      # ~1.10e-13 (printed 1.11e-13)
    p_r = pr_coeff * v ** 2 * c ** 2 * he ** 2 * f ** 4
    b_3db = bw_coeff * he ** 2 * f ** 4 * c / eta_ts
    out = {
        "radiated_power_w": p_r,
        "bandwidth_3db_hz": b_3db,
        "power_bandwidth_w_hz": p_r * b_3db,
        "pr_coefficient": pr_coeff,
        "bw_coefficient": bw_coeff,
        "warnings": warnings,
    }
    dc = float(delta_c_farads)
    if dc > 0.0:
        ratio = c / (c + dc)
        out["shunt_effective_height_factor"] = ratio
        out["shunt_bandwidth_factor_antenna_only"] = ratio
        out["shunt_note"] = (
            "base/stray shunt capacity: apparent h_e and antenna-only "
            "bandwidth shrink by C/(C+dC) = {0:.3f}; the resonated "
            "voltage-limited P_r is unchanged".format(ratio))
    return out


def efficiency_ladder(r_r, r_ground=0.0, r_copper=0.0, r_dielectric=0.0,
                      r_coil=0.0, r_transmitter=0.0, x_c_ohm=None,
                      freq_hz=None):
    """The canonical VLF efficiency ladder (verified §2.1.12 chain):
    eta_a = Rr/Ra (antenna only, Ra = Rr + Rsd + Rc + Rg), eta_as =
    Rr/(Ra+Ri) (antenna + load coil), eta_ts = Rr/(Ra+Ri+Rt) (transmitting
    system — the one to use for system bandwidth). Optionally reports the
    100%%-efficiency floor pair Q(eta=1) = Xc/Rr and b(eta=1) = f/Q.

    Historical plausibility: real VLF monopole system efficiencies run
    ~10-70%% (rising roughly as f^1.2-1.7) — a computed eta_ts above ~85%%
    at low VLF for a modest antenna deserves suspicion (warned)."""
    if r_r <= 0:
        raise ValueError("radiation resistance must be positive")
    for name, v in (("r_ground", r_ground), ("r_copper", r_copper),
                    ("r_dielectric", r_dielectric), ("r_coil", r_coil),
                    ("r_transmitter", r_transmitter)):
        if v < 0:
            raise ValueError(name + " cannot be negative")
    r_l = r_dielectric + r_copper + r_ground
    r_a = r_r + r_l
    out = {
        "r_loss_ohm": r_l,
        "r_antenna_ohm": r_a,
        "eta_a": r_r / r_a,
        "eta_as": r_r / (r_a + r_coil),
        "eta_ts": r_r / (r_a + r_coil + r_transmitter),
        "warnings": [],
    }
    if x_c_ohm is not None and freq_hz is not None and x_c_ohm > 0:
        q_min = x_c_ohm / r_r
        out["q_eta1"] = q_min
        out["bandwidth_eta1_hz"] = float(freq_hz) / q_min
    if freq_hz is not None and freq_hz < 40e3 and out["eta_ts"] > 0.85:
        out["warnings"].append(
            "eta_ts = {0:.0%} at {1:.3g} kHz — real VLF systems run "
            "~10-70%; re-check the loss budget (ground system usually "
            "dominates)".format(out["eta_ts"], freq_hz / 1e3))
    return out


def effective_height_from_field(e_v_per_m, d_m, i_a, freq_hz):
    """Experimental effective height from a measured field (the standard
    determination — verified eq 2.1.8b): h_e = 1e7 * E * d / (4*pi*I*f).
    Measure E in the radiation zone over uniform ground, at several
    distances (the fields must obey 1/d), clear of conductivity
    discontinuities."""
    if min(e_v_per_m, d_m, i_a, freq_hz) <= 0:
        raise ValueError("all inputs must be positive")
    return 1.0e7 * e_v_per_m * d_m / (4.0 * math.pi * i_a * freq_hz)
