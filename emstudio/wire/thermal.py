# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cable thermal / temperature-rise analysis (ROADMAP §2 Cable Designer —
the thermal slice).

Steady conductor-temperature model for insulated wires and cables in FREE
AIR: I²R(T) conductor loss (IEC 60287-1-1 resistance-temperature
correction), radial conduction through concentric dielectric layers
(IEC 60287-2-1), and free-convection + radiation surface dissipation from a
horizontal cylinder (Churchill-Chu all-Ra correlation on the AHTT Table A.6
dry-air properties). Plus: ampacity inverse solve for an insulation
temperature class, NEC bundle adjustment factors, a lumped-capacitance
transient rise, the IEC 60949 adiabatic short-circuit rating, and a coax RF
average-power rating built on the repo's attenuation split.

**Model composition (per unit length, horizontal, still air, sea level):**

* conductor loss  ``q = I² R_dc20 (1 + alpha20 (Tc - 20)) (Rac/Rdc)`` —
  linear in q once the surface temperature is fixed, since
  ``Tc = Ts + q ΣT_k``; a non-positive denominator = THERMAL RUNAWAY
  (flagged, never silently clamped);
* each dielectric layer ``T_k = (rho_k / 2π) ln(1 + 2 t_k / D_in,k)``
  (IEC 60287-2-1 §4.1.2.1; metallic layers are isothermal nodes) — exact
  for concentric circular layers; bundles need the homogenized caveat;
* surface ``q = h_c π D (Ts - Ta) + eps sigma π D (Ts⁴ - Tsur⁴)`` with
  ``h_c = Nu k_f / D`` from Churchill-Chu, film properties interpolated in
  the AHTT dry-air table (250-600 K), ``beta = 1/T_f``.

**Validity/limits (documented, not clamped):** horizontal single cable,
unconfined still air, sea level, gray-diffuse radiation to large
surroundings. Vertical runs, trays, conduit, touching bundles, solar load
and altitude all change the answer — the NEC/MIL derating helpers cover the
bundle case empirically. The Churchill-Chu printed range is Ra 1e-6..1e12
(warned outside). This module does NOT replace ``litz.ampacity`` (the
deliberately conservative fixed-h sizing estimate, gate-frozen); it is the
honest full model behind the Thermal tab.

Sources (2026-07-12 de-risk workflow, adversarially recomputed 60/61 with
two corrections applied here): IEC 60287-2-1:2015/2023 official previews
(T1 formula verbatim; worked examples recomputed to 1e-9: QuickField HV
XLPE T1 = 0.8166061945 — the printed 0.816 is a TRUNCATION, round() gives
0.817; E3S HTRSE-2018 LV PVC T1 = 0.4325954273, KA = 0.116); IEC 60287-1-1
conductor constants (Cu 1.7241e-8 / 0.00393, Al 2.8264e-8 / 0.00403; Qc
3.45e6 / 2.5e6 J/m³K); IEC 60287-2-1 Table 1 thermal resistivities (PVC 5.0
≤3 kV / 6.0 above, PE/XLPE/EPR 3.5, paper 6.0; PTFE 4.0 is a DATASHEET band
2.9-4.2, not IEC); Churchill-Chu (AHTT eq. 8.29 = Cengel 9-25) gated to
Cengel Ex 9-1 (Ra 1.869e6, Nu 17.40, h 5.869) and AHTT Ex 8.4 (fine-wire
low-Ra rows) with each example's own printed film properties; AHTT Table
A.6 air rows 250-600 K (exact printed digits); IEC 60949 / BS 7671
adiabatic constants (Cu K = 226, beta = 234.5; Al K = 148, beta = 228; k
table 115/100/143/76/94); IEC 60853-2 volumetric heat capacities; NEC
310.15(C)(1) adjustment factors; ampacity BANDS from NEC 310.17, the
Multicable hookup table, MIL-W-5088L §6.7 text points and NASA 1-atm
measurements; coax dissipation identity p' = (ln10/10) A[dB/m] P (the
factor 2 belongs to FIELD nepers — verified exactly) with the EXACT 1/2
dielectric-heat factor for the TEM 1/r² profile, banded 90-125 % against
the Times LMR-240 catalog table. Temperature classes: IEC 60502-1 Tables
3/4, UL 758 styles, MIL-DTL-16878/4, IEC 60085 (numeric above R 220 —
"S 240" is UL 1446/NEMA usage, not IEC).

Pure math + numpy-free; FreeCAD/Qt-free. SI units unless suffixed.
"""
from __future__ import annotations

import math

SIGMA_SB = 5.67e-8          # W/m^2K^4 (matches the gate examples' 5.67e-8)
G_ACCEL = 9.80665

# IEC 60287-1-1: rho20 (ohm.m), alpha20 (1/K), volumetric heat capacity
# (J/m^3K), IEC 60949 adiabatic K (A.s^0.5/mm^2), beta (K)
CONDUCTORS = {
    "Cu": {"rho20": 1.7241e-8, "alpha20": 0.00393, "qv": 3.45e6,
           "k_adiabatic": 226.0, "beta": 234.5},
    "Al": {"rho20": 2.8264e-8, "alpha20": 0.00403, "qv": 2.5e6,
           "k_adiabatic": 148.0, "beta": 228.0},
}

# IEC 60287-2-1 Table 1 thermal resistivities, K.m/W (voltage-class split
# kept); PTFE/enamel/PET are DATASHEET bands (default pinned, band gated)
RHO_THERMAL = {
    "PVC": 5.0,
    "PVC (>3 kV)": 6.0,
    "PE": 3.5,
    "XLPE": 3.5,
    "EPR": 3.5,
    "EPR (>3 kV)": 5.0,
    "paper (mass-impregnated)": 6.0,
    "PTFE": 4.0,                 # datasheet band 2.9-4.2 (k ~ 0.25 W/m.K)
    "silicone rubber": 5.0,      # datasheet band 4.5-7
    "enamel": 4.0,               # magnet-wire film, datasheet band 2.5-5
    "polyester tape": 5.0,       # PET film, datasheet band 4-6.7
}

# volumetric heat capacities of insulations at 20 C, J/(K.m^3)
# (IEC 60853-2 for PVC/PE/XLPE/EPR; PTFE/PET datasheet-class)
QV_INSULATION = {
    "PVC": 1.7e6, "PVC (>3 kV)": 1.7e6,
    "PE": 2.4e6, "XLPE": 2.4e6,
    "EPR": 2.0e6, "EPR (>3 kV)": 2.0e6,
    "paper (mass-impregnated)": 2.0e6,
    "PTFE": 2.1e6, "silicone rubber": 2.0e6,
    "enamel": 2.0e6, "polyester tape": 1.4e6,
}

# conductor temperature limits, C — IEC 60502-1 / UL 758 / MIL-DTL-16878 /
# IEC 60085 magnet-wire classes (numeric above R 220 per the corrected map)
TEMP_CLASSES = {
    "PVC 70 °C (IEC 60502-1)": 70.0,
    "PVC 80 °C (UL 1007)": 80.0,
    "PVC 105 °C (UL 1015)": 105.0,
    "PE / XLPE 90 °C (IEC 60502-1)": 90.0,
    "EPR 90 °C (IEC 60502-1)": 90.0,
    "PTFE 200 °C (MIL-DTL-16878/4)": 200.0,
    "Silicone 180 °C (class H)": 180.0,
    "Polyester 105 °C": 105.0,
    "Enamel class A 105 °C": 105.0,
    "Enamel class E 120 °C": 120.0,
    "Enamel class B 130 °C": 130.0,
    "Enamel class F 155 °C": 155.0,
    "Enamel class H 180 °C": 180.0,
    "Enamel class N 200 °C": 200.0,
    "Enamel class R 220 °C": 220.0,
}

# jacket emissivity defaults (polymer jackets; band [0.88, 0.95] gated)
EMISSIVITY = {"PVC": 0.92, "PE": 0.92, "PTFE": 0.92,
              "polyester tape": 0.90, "enamel": 0.90, "none (bare Cu)": 0.30}

# AHTT Table A.6, dry air at 1 atm — exact printed rows (250-600 K):
# T (K), k (W/m.K), nu (m^2/s), alpha (m^2/s), Pr
AIR_TABLE = (
    (250.0, 0.0226, 1.135e-5, 1.59e-5, 0.715),
    (260.0, 0.0233, 1.218e-5, 1.71e-5, 0.713),
    (270.0, 0.0241, 1.304e-5, 1.83e-5, 0.711),
    (280.0, 0.0249, 1.392e-5, 1.96e-5, 0.710),
    (290.0, 0.0256, 1.482e-5, 2.09e-5, 0.708),
    (300.0, 0.0264, 1.575e-5, 2.23e-5, 0.707),
    (310.0, 0.0271, 1.670e-5, 2.37e-5, 0.706),
    (320.0, 0.0279, 1.766e-5, 2.51e-5, 0.705),
    (330.0, 0.0286, 1.865e-5, 2.65e-5, 0.704),
    (340.0, 0.0293, 1.966e-5, 2.80e-5, 0.703),
    (350.0, 0.0300, 2.069e-5, 2.95e-5, 0.702),
    (400.0, 0.0335, 2.613e-5, 3.74e-5, 0.699),
    (450.0, 0.0368, 3.204e-5, 4.59e-5, 0.698),
    (500.0, 0.0399, 3.839e-5, 5.50e-5, 0.698),
    (550.0, 0.0430, 4.515e-5, 6.45e-5, 0.700),
    (600.0, 0.0460, 5.232e-5, 7.44e-5, 0.703),
)

# NEC 310.15(C)(1) adjustment factors (count includes spares)
NEC_ADJUSTMENT = ((3, 1.00), (6, 0.80), (9, 0.70), (20, 0.50),
                  (30, 0.45), (40, 0.40), (10 ** 9, 0.35))

# UI/material-name vocabulary -> RHO_THERMAL/QV_INSULATION keys (single
# source of truth for the name mapping — the combos are editable, so
# normalize_material returns None for anything unknown and CALLERS must
# surface that instead of silently substituting)
MATERIAL_ALIASES = {
    "pvc": "PVC", "polyethylene": "PE", "pe": "PE", "xlpe": "XLPE",
    "ptfe": "PTFE", "polyester tape": "polyester tape",
    "enamel": "enamel", "silicone": "silicone rubber",
    "silicone rubber": "silicone rubber", "epr": "EPR",
}

DEFAULT_TEMP_CLASS = "PVC 105 °C (UL 1015)"


def normalize_material(name):
    """RHO_THERMAL key for a UI material name, or None if unknown."""
    return MATERIAL_ALIASES.get(str(name).strip().lower())


def layers_from_construction(con):
    """(d_cond_m, layers, warnings) for a litz/wire construction object.

    Duck-types on ``bundle_diameter_m()``/``jacket``/``jacket_m`` — the one
    shared mapping for the Thermal tab, PDF reports and the future §7 tool.
    The conductor node is the bare cabled envelope (isothermal metal); the
    overall jacket is the single dielectric layer. Unknown jacket names get
    PVC properties WITH a warning (never silently).
    """
    warnings = []
    layers = []
    if getattr(con, "jacket", "") and getattr(con, "jacket_m", 0.0) > 0.0:
        mat = normalize_material(con.jacket)
        if mat is None:
            mat = "PVC"
            warnings.append(
                "unknown jacket material '{0}' — modeled as PVC "
                "(rho_T 5.0, qv 1.7e6)".format(con.jacket))
        layers.append({"name": mat, "t_m": con.jacket_m})
    return con.bundle_diameter_m(), layers, warnings


def air_properties(t_film_k):
    """(k, nu, alpha, Pr) of dry air, linear interpolation in AHTT A.6.

    Clamped to the 250-600 K table span; callers should surface a warning
    when the film temperature leaves it (the steady solver does).
    """
    t = min(max(float(t_film_k), AIR_TABLE[0][0]), AIR_TABLE[-1][0])
    for i in range(len(AIR_TABLE) - 1):
        t0, t1 = AIR_TABLE[i][0], AIR_TABLE[i + 1][0]
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(AIR_TABLE[i][j] + f * (AIR_TABLE[i + 1][j]
                                                - AIR_TABLE[i][j])
                         for j in range(1, 5))
    return tuple(AIR_TABLE[-1][j] for j in range(1, 5))


def nu_churchill_chu(ra_d, pr):
    """Churchill-Chu all-Ra horizontal-cylinder Nusselt number.

    Nu = {0.60 + 0.387 [Ra / (1 + (0.559/Pr)^(9/16))^(16/9)]^(1/6)}^2 —
    single smooth expression (AHTT eq. 8.29 = Cengel 9-25), printed range
    Ra 1e-6..1e12. Reads slightly LOW vs Morgan at low Ra (conservative for
    ampacity; gated within ±25 % of the Morgan bands over the cable regime).
    """
    if ra_d < 0.0:
        raise ValueError("Rayleigh number must be >= 0")
    f = (1.0 + (0.559 / pr) ** (9.0 / 16.0)) ** (16.0 / 9.0)
    return (0.60 + 0.387 * (ra_d / f) ** (1.0 / 6.0)) ** 2


def surface_h(d_m, ts_c, tamb_c, props=None):
    """Free-convection film coefficient h_c (W/m^2K) + diagnostics dict.

    ``props`` overrides (k, nu, alpha, Pr) — the worked-example gates inject
    each textbook's own printed film properties (AHTT Ex 8.4 uses v5-era
    values that differ from the v6 table in the 4th digit).
    """
    tf_k = (float(ts_c) + float(tamb_c)) / 2.0 + 273.15
    k, nu, alpha, pr = props if props is not None else air_properties(tf_k)
    dt = abs(float(ts_c) - float(tamb_c))
    ra = G_ACCEL * (1.0 / tf_k) * dt * d_m ** 3 / (nu * alpha)
    nu_d = nu_churchill_chu(ra, pr)
    return {
        "h_w_m2k": nu_d * k / d_m,
        "ra": ra,
        "nu": nu_d,
        "t_film_k": tf_k,
        "ra_in_range": 1e-6 <= ra <= 1e12,
        "film_in_table": AIR_TABLE[0][0] <= tf_k <= AIR_TABLE[-1][0],
    }


def surface_loss_w_m(d_m, ts_c, tamb_c, emissivity, tsur_c=None, props=None):
    """Convective + radiative dissipation per metre off the finished surface."""
    tsur = tamb_c if tsur_c is None else tsur_c
    sh = surface_h(d_m, ts_c, tamb_c, props=props)
    q_conv = sh["h_w_m2k"] * math.pi * d_m * (ts_c - tamb_c)
    q_rad = (emissivity * SIGMA_SB * math.pi * d_m
             * ((ts_c + 273.15) ** 4 - (tsur + 273.15) ** 4))
    return {"q_conv_w_m": q_conv, "q_rad_w_m": q_rad,
            "q_total_w_m": q_conv + q_rad, **sh}


def layer_t_k_m_w(rho_t, d_in_m, t_m):
    """One dielectric layer's thermal resistance (IEC 60287-2-1 §4.1.2.1).

    T = (rho_T / 2π) ln(1 + 2 t / D_in) — identical to
    (rho_T / 2π) ln(D_out / D_in); thin-wall limit rho·t/(π·D).
    """
    if t_m <= 0.0:
        return 0.0
    return rho_t / (2.0 * math.pi) * math.log(1.0 + 2.0 * t_m / d_in_m)


def _stack(d_cond_m, layers):
    """[(name, rho_t, qv, r_in, r_out, T_k)] from conductor OD outward."""
    out = []
    d = float(d_cond_m)
    for lay in layers:
        t = float(lay.get("t_m", 0.0))
        rho = float(lay.get("rho_t", RHO_THERMAL.get(lay.get("name"), 5.0)))
        qv = float(lay.get("qv", QV_INSULATION.get(lay.get("name"), 2.0e6)))
        out.append((lay.get("name", "layer"), rho, qv, d / 2.0,
                    d / 2.0 + t, layer_t_k_m_w(rho, d, t)))
        d += 2.0 * t
    return out, d


def solve_steady(i_a, d_cond_m, layers, rdc20_ohm_m, material="Cu",
                 rac_factor=1.0, tamb_c=30.0, emissivity=0.92, tsur_c=None):
    """Steady temperatures of a horizontal insulated conductor in free air.

    ``layers``: [{"name", "t_m", "rho_t"?, "qv"?}, ...] from the conductor
    outward (rho_t/qv default from the material tables by name).
    ``rac_factor``: Rac/Rdc at the operating frequency (1.0 = DC; feed the
    litz/skin engines' value for AC). Returns a dict with ``t_conductor_c``,
    ``t_surface_c``, ``q_w_m``, the surface diagnostics, a ``profile`` of
    (r_m, T_c) breakpoints through every layer (for the cross-section
    view), ``runaway`` and ``warnings``. Bisection on the surface
    temperature; the conductor loss is linear in q at fixed Ts:
    q (1 - I²R20 f alpha ΣT) = I²R20 f (1 + alpha (Ts - 20)) — a
    non-positive left factor is thermal runaway.
    """
    con = CONDUCTORS[material]
    stack, d_surf = _stack(d_cond_m, layers)
    sum_t = sum(s[5] for s in stack)
    r20f = float(rdc20_ohm_m) * float(rac_factor) * float(i_a) ** 2
    alpha = con["alpha20"]
    warnings = []

    denom = 1.0 - r20f * alpha * sum_t
    if denom <= 0.0:
        return {"runaway": True, "warnings": [
            "thermal runaway: I²R(T) growth exceeds the insulation's "
            "conductive capability (denominator {0:.3f} <= 0)".format(denom)],
            "d_surface_m": d_surf}

    def q_gen(ts_c):
        return r20f * (1.0 + alpha * (ts_c - 20.0)) / denom

    def residual(ts_c):
        sl = surface_loss_w_m(d_surf, ts_c, tamb_c, emissivity, tsur_c)
        return q_gen(ts_c) - sl["q_total_w_m"]

    # bracket from BELOW ambient when the radiative surroundings are colder
    # (Ts can equilibrate under Ta then; at Ts = min(Ta, Tsur) the surface
    # LOSES nothing net while generation >= 0, so the residual is positive)
    lo = min(float(tamb_c), float(tamb_c if tsur_c is None else tsur_c))
    hi = lo + 10.0
    for _ in range(20):
        if residual(hi) < 0.0:
            break
        hi = lo + (hi - lo) * 2.0
    else:
        return {"runaway": True, "warnings": [
            "no steady state below {0:.0f} °C — treat as runaway".format(hi)],
            "d_surface_m": d_surf}
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if residual(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    ts = 0.5 * (lo + hi)
    q = q_gen(ts)
    sl = surface_loss_w_m(d_surf, ts, tamb_c, emissivity, tsur_c)
    tc = ts + q * sum_t
    if not sl["ra_in_range"]:
        warnings.append("Ra {0:.1e} outside the Churchill-Chu printed range "
                        "1e-6..1e12".format(sl["ra"]))
    if not sl["film_in_table"]:
        warnings.append("film temperature outside the 250-600 K air table "
                        "(clamped)")
    if sl["ra"] < 1e2:
        warnings.append(
            "fine-wire regime (Ra {0:.1f} < 1e2): Churchill-Chu reads up to "
            "~25% below the Morgan measured fit — temperatures are "
            "conservative (hot); NASA 1-atm data sits at the Morgan "
            "level".format(sl["ra"]))

    # radial profile breakpoints: conductor isothermal, then each layer's
    # exact log profile endpoints (the UI draws ln-interpolated arcs)
    profile = [(0.0, tc), (d_cond_m / 2.0, tc)]
    t_here = tc
    for name, rho, qv, r_in, r_out, t_k in stack:
        t_here -= q * t_k
        profile.append((r_out, t_here))
    return {
        "t_conductor_c": tc,
        "t_surface_c": ts,
        "q_w_m": q,
        "d_surface_m": d_surf,
        "sum_t_k_m_w": sum_t,
        "stack": stack,
        "profile": profile,
        "runaway": False,
        "warnings": warnings,
        **{k: sl[k] for k in ("q_conv_w_m", "q_rad_w_m", "h_w_m2k", "ra",
                              "nu", "t_film_k")},
    }


def ampacity(d_cond_m, layers, rdc20_ohm_m, t_limit_c, material="Cu",
             rac_factor=1.0, tamb_c=30.0, emissivity=0.92, tsur_c=None):
    """Continuous current that lands the CONDUCTOR at ``t_limit_c``.

    Bisection on I over the steady solver. Returns the current plus the full
    steady report at the rating.
    """
    if t_limit_c <= tamb_c:
        raise ValueError("temperature limit must exceed ambient")

    def tc(i_a):
        rep = solve_steady(i_a, d_cond_m, layers, rdc20_ohm_m, material,
                           rac_factor, tamb_c, emissivity, tsur_c)
        return float("inf") if rep["runaway"] else rep["t_conductor_c"]

    lo, hi = 0.0, 10.0
    for _ in range(30):
        if tc(hi) > t_limit_c:
            break
        hi *= 2.0
    else:
        raise ValueError(
            "temperature limit unreachable at any current — check the DC "
            "resistance (Rdc ~ 0?) and the geometry")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if tc(mid) > t_limit_c:
            hi = mid
        else:
            lo = mid
    i_rated = 0.5 * (lo + hi)
    rep = solve_steady(i_rated, d_cond_m, layers, rdc20_ohm_m, material,
                       rac_factor, tamb_c, emissivity, tsur_c)
    return dict(rep, ampacity_a=i_rated, t_limit_c=t_limit_c)


def nec_derate(n_conductors):
    """NEC 310.15(C)(1) adjustment factor (exact lookup; spares count)."""
    n = int(n_conductors)
    if n < 1:
        raise ValueError("conductor count must be >= 1")
    for hi, f in NEC_ADJUSTMENT:
        if n <= hi:
            return f
    return 0.35


def _c_th_j_m_k(steady_report, d_cond_m, material, a_cond_m2=None,
                qv_gap=2.0e6):
    """Lumped heat capacity per metre. ``a_cond_m2`` = true METAL area (litz:
    ``copper_area_m2()``); the rest of the conductor envelope is filler at
    ``qv_gap`` (enamel/air class) instead of being counted as solid metal."""
    con = CONDUCTORS[material]
    a_env = math.pi * (d_cond_m / 2.0) ** 2
    a_metal = a_env if a_cond_m2 is None else min(float(a_cond_m2), a_env)
    c_th = con["qv"] * a_metal + qv_gap * (a_env - a_metal)
    for name, rho, qv, r_in, r_out, t_k in steady_report["stack"]:
        c_th += qv * math.pi * (r_out ** 2 - r_in ** 2)
    return c_th


def transient(steady_report, d_cond_m, material="Cu", a_cond_m2=None):
    """SMALL-SIGNAL lumped heating: tau and the exponential rise sampler.

    Honest scope: the exponential is the small-signal linearization about
    the final steady point — good near/below the rating. At OVERLOAD the
    linearization is badly optimistic on speed (it can undercut even the
    adiabatic bound) — use :func:`heating_curve` for the real trajectory
    and any time-to-limit read-out. ``a_cond_m2``: true metal area (litz
    envelopes are ~44 % filler; counting them as solid copper reads tau
    ~30 % high). tens-of-% class either way; the exact-by-construction
    curve identity T(tau) - Ta = 0.632 dT is gated.
    """
    if steady_report.get("runaway"):
        raise ValueError("no steady state — transient lump undefined")
    if steady_report["q_w_m"] <= 0.0:
        raise ValueError("zero dissipation — transient undefined at no load")
    c_th = _c_th_j_m_k(steady_report, d_cond_m, material, a_cond_m2)
    tamb = _ambient_from(steady_report)
    dt_final = steady_report["t_conductor_c"] - tamb
    g_th = steady_report["q_w_m"] / max(dt_final, 1e-12)
    tau = c_th / g_th

    def t_of(t_s):
        return tamb + dt_final * (1.0 - math.exp(-t_s / tau))

    return {"tau_s": tau, "c_th_j_m_k": c_th, "g_th_w_m_k": g_th,
            "dt_final_c": dt_final, "tamb_c": tamb, "t_of": t_of}


def heating_curve(i_a, d_cond_m, layers, rdc20_ohm_m, material="Cu",
                  rac_factor=1.0, tamb_c=30.0, emissivity=0.92,
                  tsur_c=None, a_cond_m2=None, t_limit_c=None,
                  t_end_s=None, n_steps=400):
    """Quasi-static heating trajectory Tc(t) by midpoint integration.

    The honest overload curve (the small-signal exponential undercuts even
    the adiabatic bound above ~1.5x rating): lump state = conductor
    temperature; at each step the surface temperature solves the
    instantaneous ladder+surface balance, and
    ``C_th dTc/dt = q_gen(Tc) - q_out(Tc)`` with the engine's own loss and
    surface models. Returns times/temps lists, ``t_hit_s`` (first crossing
    of ``t_limit_c``, None if never) and the final temperature. The steady
    fixed point equals :func:`solve_steady`'s Tc (gated); at overload the
    time-to-limit respects the adiabatic lower bound (gated).
    """
    con = CONDUCTORS[material]
    stack, d_surf = _stack(d_cond_m, layers)
    sum_t = sum(s[5] for s in stack)
    r20f = float(rdc20_ohm_m) * float(rac_factor) * float(i_a) ** 2
    rep0 = {"stack": stack, "q_w_m": 1.0}   # shape for _c_th_j_m_k
    c_th = _c_th_j_m_k(rep0, d_cond_m, material, a_cond_m2)

    def q_out(tc):
        # Ts from tc via the instantaneous ladder: tc = ts + q_out*sum_t and
        # q_out = surface_loss(ts) — bisection on ts
        lo = min(tamb_c, tamb_c if tsur_c is None else tsur_c)
        hi = tc
        if hi <= lo:
            return 0.0
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            q_s = surface_loss_w_m(d_surf, mid, tamb_c, emissivity,
                                   tsur_c)["q_total_w_m"]
            if mid + q_s * sum_t > tc:
                hi = mid
            else:
                lo = mid
        return surface_loss_w_m(d_surf, 0.5 * (lo + hi), tamb_c, emissivity,
                                tsur_c)["q_total_w_m"]

    def dtc_dt(tc):
        q_gen = r20f * (1.0 + con["alpha20"] * (tc - 20.0))
        return (q_gen - q_out(tc)) / c_th

    if t_end_s is None:
        # scale from the small-signal constant at ambient
        g0 = max(r20f * con["alpha20"], 1e-12)
        t_end_s = 6.0 * c_th / max(
            surface_loss_w_m(d_surf, tamb_c + 10.0, tamb_c, emissivity,
                             tsur_c)["q_total_w_m"] / 10.0 - g0, g0)
    dt = float(t_end_s) / int(n_steps)
    tc = float(tamb_c)
    times, temps = [0.0], [tc]
    t_hit = None
    for i in range(int(n_steps)):
        k1 = dtc_dt(tc)
        tc_new = tc + dt * dtc_dt(tc + 0.5 * dt * k1)   # midpoint
        t_now = (i + 1) * dt
        if (t_limit_c is not None and t_hit is None
                and temps[-1] < t_limit_c <= tc_new):
            f = (t_limit_c - temps[-1]) / (tc_new - temps[-1])
            t_hit = times[-1] + f * dt
        tc = tc_new
        times.append(t_now)
        temps.append(tc)
    return {"times_s": times, "temps_c": temps, "t_hit_s": t_hit,
            "t_final_c": tc, "c_th_j_m_k": c_th, "t_end_s": t_end_s}


def _ambient_from(rep):
    """Ambient recovered from the steady report's surface balance."""
    d = rep["d_surface_m"]
    h = rep["h_w_m2k"]
    return rep["t_surface_c"] - rep["q_conv_w_m"] / (h * math.pi * d)


def adiabatic_current_a(s_mm2, t_s, ti_c, tf_c, material="Cu"):
    """IEC 60949 adiabatic short-circuit current (no heat loss, t <= 5 s).

    I = K (S/√t) √ln((beta + tf)/(beta + ti)); Cu K = 226, beta = 234.5;
    Al K = 148, beta = 228 (A·s^0.5/mm²). The BS 7671 k-factors follow from
    the same constants (Cu PVC 70→160: 115; Cu XLPE 90→250: 143 — gated).
    """
    con = CONDUCTORS[material]
    if t_s <= 0.0 or tf_c <= ti_c:
        raise ValueError("need t > 0 and final temperature above initial")
    return (con["k_adiabatic"] * float(s_mm2) / math.sqrt(float(t_s))
            * math.sqrt(math.log((con["beta"] + tf_c)
                                 / (con["beta"] + ti_c))))


def k_factor(ti_c, tf_c, material="Cu"):
    """BS 7671-style k (A·s^0.5/mm²) from the IEC 60949 constants."""
    con = CONDUCTORS[material]
    return con["k_adiabatic"] * math.sqrt(
        math.log((con["beta"] + tf_c) / (con["beta"] + ti_c)))


# ---------------------------------------------------------------------------
# coax RF average-power rating
# ---------------------------------------------------------------------------

LN10_10 = math.log(10.0) / 10.0    # dB -> local power dissipation density

# dielectric/jacket thermal conductivities for the coax network, W/m.K
# (documented picks with ranges; k_foam is a Maxwell-Eucken-DERIVED
# parameter — never tune it to centre a gate)
K_THERMAL_COAX = {"PE (solid polyethylene)": 0.33, "PTFE (solid)": 0.25,
                  "Foam PE (typ. 80% VF)": 0.13, "Air": 0.026,
                  "FEP": 0.21, "PVC jacket": 0.16, "PE jacket": 0.35}

# generic-build allowance when the real shield OD is unknown: braid/tape
# stack over the dielectric (the LMR-240 gate passes the REAL 4.52 mm OD)
SHIELD_OD_FACTOR = 1.3


def k_thermal_from_eps_r(eps_r):
    """(k_diel, diel label, k_jacket, jacket label) inferred from eps_r.

    The classifier for coax builds where only the electrical model is
    known: air / foam PE / PTFE (with its usual FEP jacket) / solid PE
    (PVC jacket). One shared classification for the Thermal tab, PDF
    reports and §7 — boundary cases belong HERE, not in UI copies.
    """
    e = float(eps_r)
    if e <= 1.2:
        return (K_THERMAL_COAX["Air"], "air",
                K_THERMAL_COAX["PVC jacket"], "PVC")
    if e <= 1.9:
        return (K_THERMAL_COAX["Foam PE (typ. 80% VF)"],
                "foam PE (derived 0.13)",
                K_THERMAL_COAX["PE jacket"], "PE")
    if e <= 2.15:
        return (K_THERMAL_COAX["PTFE (solid)"], "PTFE 0.25",
                K_THERMAL_COAX["FEP"], "FEP")
    return (K_THERMAL_COAX["PE (solid polyethylene)"], "solid PE 0.33",
            K_THERMAL_COAX["PVC jacket"], "PVC")


def coax_power_w(f_hz, a_m, b_m, eps_r, tan_delta, t_inner_limit_c,
                 k_diel_w_mk, jacket_t_m=1.0e-3, k_jacket_w_mk=0.16,
                 d_shield_m=None, tamb_c=40.0, emissivity=0.92,
                 atten_cond_db_m=None, atten_diel_db_m=None,
                 sigma_inner=5.8e7, sigma_outer=5.8e7):
    """Matched-line average power rating P_max(f) of a coax (W).

    Dissipation density at the INPUT (worst case): p' = (ln10/10)·A[dB/m]·P
    — the factor 2 belongs to FIELD nepers and is already inside this
    identity (gated to 1e-12). The conductor attenuation splits inner/outer
    by the Rs/a vs Rs/b surface-resistance weights; the dielectric's
    distributed heat crosses HALF the dielectric resistance (exact for the
    TEM 1/r² profile — gated to 1e-10):

        ΔT_inner = (p'_a + ½ p'_d) R_diel + p'_tot (R_jkt + R_surf)

    with R_diel = ln(b/a)/(2π k_d). Defaults: attenuation from the repo's
    smooth-conductor coax model — it UNDER-estimates loss for braided real
    cables, so P_max is OVER-estimated (rate one-sided: model ≥ datasheet;
    the LMR-240 gate feeds the DATASHEET attenuation instead and lands in
    90-125 %). Conditions: VSWR 1.0, sea level, still air, no solar.
    ``sigma_inner``/``sigma_outer`` shift only the inner/outer HEAT SPLIT —
    when the outer conductor is not copper, pass a consistent
    ``atten_cond_db_m`` too (the default smooth model assumes copper both
    sides). ``d_shield_m=None`` uses the generic-build allowance
    ``2b * SHIELD_OD_FACTOR``.
    """
    from emstudio.wire import coax as cx

    if t_inner_limit_c <= tamb_c:
        raise ValueError("inner-conductor temperature limit must exceed "
                         "ambient")

    a_c = (cx.conductor_loss_db_m(f_hz, a_m, b_m, eps_r)
           if atten_cond_db_m is None else float(atten_cond_db_m))
    a_d = (cx.dielectric_loss_db_m(f_hz, eps_r, tan_delta)
           if atten_diel_db_m is None else float(atten_diel_db_m))
    # inner/outer conductor split by Rs/a : Rs/b (Rs ∝ 1/sqrt(sigma) — a
    # copper centre under an aluminium-tape shield shifts the split)
    wa_raw = 1.0 / (math.sqrt(sigma_inner) * a_m)
    wb_raw = 1.0 / (math.sqrt(sigma_outer) * b_m)
    w_a = wa_raw / (wa_raw + wb_raw)
    c_a = LN10_10 * a_c * w_a          # W/m per W at the input, inner
    c_d = LN10_10 * a_d
    c_tot = LN10_10 * (a_c + a_d)
    r_diel = math.log(b_m / a_m) / (2.0 * math.pi * k_diel_w_mk)
    d_sh = (2.0 * b_m * SHIELD_OD_FACTOR if d_shield_m is None
            else float(d_shield_m))
    d_jkt = d_sh + 2.0 * jacket_t_m
    r_jkt = math.log(d_jkt / d_sh) / (2.0 * math.pi * k_jacket_w_mk)

    dt_lim = t_inner_limit_c - tamb_c
    ts = tamb_c + 0.7 * dt_lim
    p_max = 0.0
    for _ in range(50):
        sl = surface_loss_w_m(d_jkt, ts, tamb_c, emissivity)
        h_tot = sl["q_total_w_m"] / (math.pi * d_jkt
                                     * max(ts - tamb_c, 1e-9))
        r_surf = 1.0 / (h_tot * math.pi * d_jkt)
        p_new = dt_lim / ((c_a + 0.5 * c_d) * r_diel
                          + c_tot * (r_jkt + r_surf))
        ts_new = tamb_c + p_new * c_tot * r_surf
        if abs(p_new - p_max) < 1e-9 * max(p_new, 1.0):
            p_max = p_new
            ts = ts_new
            break
        p_max = p_new
        ts = 0.5 * (ts + ts_new)
    else:
        # loop exhausted: report the surface temperature CONSISTENT with
        # the returned p_max, not the damped iterate
        ts = tamb_c + p_max * c_tot * r_surf
    return {"p_max_w": p_max, "t_surface_c": ts,
            "atten_cond_db_m": a_c, "atten_diel_db_m": a_d,
            "r_diel_k_m_w": r_diel, "r_jacket_k_m_w": r_jkt,
            "d_jacket_m": d_jkt}


# ---------------------------------------------------------------------------
# exterior 2-D temperature field: conduction film + buoyant plume
# (the cross-section "how the heat rises and dissipates" view)
# ---------------------------------------------------------------------------
#
# Laminar plane-plume similarity (Gebhart-Pera-Schorr, IJHMT 13 (1970);
# Linan & Kurdyumov, JFM 362 (1998) 199-227, open access):
#   f''' + (12/5) f f'' - (4/5) f'^2 + h = 0 ;  h' + (12/5) Pr f h = 0
#   dT(x,z) = dTc(z) h(eta), eta = (x/z)(Gr_z/4)^(1/4), u = (4 nu/z)
#   (Gr_z/4)^(1/2) f'(eta); dTc = N z^(-3/5),
#   N = [q'^4 / (64 g beta (rho cp)^4 nu^2 I^4)]^(1/5)   (Gebhart form —
#   enthalpy closure int rho cp u dT dx = q' is then EXACT by construction).
# Pinned Pr = 0.7 constants (2026-07-12 de-risk, verified three ways incl.
# the exact Fujii/Yih tanh closed forms at Pr = 2 and 5/9 to 2e-14, a direct
# solve of Linan's own equations to 6 digits, and Linan's printed F_inf
# correlation within its stated 2.5 %); identity G0 = (64 Pr^2 I^4)^(-1/5).
# The film thickness is the engine's OWN correlation: delta = k_f/h = D/Nu
# (Churchill-Chu), rendered with the Eckert-Soehngen asymmetry pattern
# delta(phi) = delta_bar/(1 + c cos phi_from_bottom) which preserves the
# mean surface flux EXACTLY for any c. Plume fed by the CONVECTIVE heat
# share only (radiation does not carry plume enthalpy). Honest label:
# laminar similarity, still air, Boussinesq — illustrative outside the
# film; real plumes sway and transition ~10-20 diameters up at cable-class
# heat rates (Sadhana 19(5) review: flux-Ra onset 7e7-8e8); measured
# centerline dT runs 15-20 % below theory near the source.

PLUME_PR = 0.7
PLUME_FP0 = 0.661832
PLUME_I = 1.211742          # full-line integral of f'(eta) h(eta)
PLUME_G0 = 0.430523         # Linan-form centreline constant
PLUME_ETA_T_HALF = 1.17454  # h(eta) = 1/2
FILM_ASYMMETRY = 0.35       # illustrative (isotherm pattern); flux-exact

# (eta, f'(eta), h(eta)) at Pr = 0.7 — generated by the de-risk shooting
# solve (rtol 1e-11); the gate re-derives these by an independent RK4 shoot
PLUME_PROFILE = (
    (0.0, 0.661832, 1.000000),
    (0.2, 0.649004, 0.978079),
    (0.4, 0.612409, 0.915935),
    (0.6, 0.557150, 0.823244),
    (0.8, 0.490133, 0.712789),
    (1.0, 0.418433, 0.597173),
    (1.2, 0.348006, 0.486434),
    (1.4, 0.283050, 0.387060),
    (1.6, 0.225951, 0.302171),
    (1.8, 0.177597, 0.232333),
    (2.0, 0.137824, 0.176508),
    (2.4, 0.080613, 0.099285),
    (2.8, 0.045856, 0.054623),
    (3.2, 0.025607, 0.029674),
    (3.6, 0.014122, 0.016007),
    (4.0, 0.007722, 0.008601),
    (4.5, 0.003602, 0.003945),
    (5.0, 0.001670, 0.001807),
    (6.0, 0.000355, 0.000378),
    (7.0, 0.000075, 0.000079),
    (8.0, 0.000016, 0.000017),
)


def plume_fprime(eta):
    """Velocity similarity profile f'(eta) (pinned Pr = 0.7 table)."""
    return _plume_interp(eta, 1)


def plume_h(eta):
    """Temperature similarity profile h(eta) (pinned Pr = 0.7 table)."""
    return _plume_interp(eta, 2)


def _plume_interp(eta, col):
    """Linear interpolation in the pinned profile table (0 beyond eta=8)."""
    e = abs(eta)
    if e >= PLUME_PROFILE[-1][0]:
        return 0.0
    for i in range(len(PLUME_PROFILE) - 1):
        e0, e1 = PLUME_PROFILE[i][0], PLUME_PROFILE[i + 1][0]
        if e <= e1:
            f = (e - e0) / (e1 - e0)
            return (PLUME_PROFILE[i][col]
                    + f * (PLUME_PROFILE[i + 1][col] - PLUME_PROFILE[i][col]))
    return 0.0


def plume_scales(z_eff_m, q_conv_w_m, tf_k):
    """Similarity scales at height ``z_eff_m`` above the (virtual) origin.

    Gebhart-form N with the pinned Pr = 0.7 profile: the enthalpy closure
    is exact by construction. Returns dt_c (K), y_scale (m, so
    eta = |x|/y_scale), u_c (m/s), n_const (K.m^0.6), gr_z.
    """
    if q_conv_w_m <= 0.0:
        raise ValueError("plume undefined without convective heat")
    k, nu, alpha, _pr = air_properties(tf_k)
    rho_cp = k / alpha
    beta = 1.0 / tf_k
    n_const = (q_conv_w_m ** 4
               / (64.0 * G_ACCEL * beta * rho_cp ** 4 * nu ** 2
                  * PLUME_I ** 4)) ** 0.2
    z = max(float(z_eff_m), 1e-9)
    dt_c = n_const * z ** (-0.6)
    gr_z = G_ACCEL * beta * dt_c * z ** 3 / nu ** 2
    y_scale = z * (gr_z / 4.0) ** (-0.25)
    u_c = 4.0 * nu / z * (gr_z / 4.0) ** 0.5
    return {"dt_c": dt_c, "y_scale": y_scale, "u_c": u_c,
            "n_const": n_const, "gr_z": gr_z}


def exterior_field(report, tamb_c):
    """2-D temperature sampler around the analyzed cross-section.

    ``report`` is a :func:`solve_steady` result. Returns
    ``(sample(x_m, z_m) -> T_c, meta)`` with x horizontal, z UP from the
    cable axis. Composite: exact interior radial ladder -> film annulus
    ``T = Ta + (Ts - Ta) exp(-(r-R)/delta(phi))`` with the flux-preserving
    asymmetric thickness -> GPS/Linan similarity plume above, virtual
    origin pinned so the centreline matches the film at
    ``z_match = R + delta_top`` -> blend ``max(film, plume)``; even in x
    by construction. Illustrative outside the film (see module notes);
    every underlying number (Ts, q, h, layer temps) is the gated engine's.
    """
    if report.get("runaway"):
        raise ValueError("no steady state — field undefined")
    r_surf = report["d_surface_m"] / 2.0
    ts = report["t_surface_c"]
    tamb = float(tamb_c)
    dt_s = ts - tamb
    k_f = air_properties(report["t_film_k"])[0]
    delta_bar = k_f / report["h_w_m2k"]        # == D/Nu identically
    c = FILM_ASYMMETRY
    delta_top = delta_bar / (1.0 - c)
    z_match = r_surf + delta_top
    q_conv = report["q_conv_w_m"]
    have_plume = q_conv > 1e-9 and dt_s > 1e-9
    if have_plume:
        dt_match = dt_s * math.exp(-1.0)
        n_const = plume_scales(1.0, q_conv, report["t_film_k"])["n_const"]
        z0 = z_match - (n_const / dt_match) ** (5.0 / 3.0)
    else:
        z0 = 0.0

    stack = report["stack"]
    t_cond = report["t_conductor_c"]
    q = report["q_w_m"]
    r_cond = stack[0][3] if stack else r_surf

    def sample(x_m, z_m):
        x = abs(float(x_m))            # mirror symmetry by construction
        z = float(z_m)
        r = math.hypot(x, z)
        if r <= r_cond:
            return t_cond
        if r <= r_surf + 1e-15:
            t_here = t_cond
            for name, rho, qv, r_in, r_out, t_k in stack:
                if r <= r_out:
                    return t_here - q * rho / (2.0 * math.pi) \
                        * math.log(r / r_in)
                t_here -= q * t_k
            return ts
        cos_phi = -z / r               # phi from DOWNWARD vertical
        delta = delta_bar / (1.0 + c * cos_phi)
        dt_film = dt_s * math.exp(-(r - r_surf) / delta)
        dt_pl = 0.0
        if have_plume and z > z_match:
            sc = plume_scales(z - z0, q_conv, report["t_film_k"])
            dt_pl = min(sc["dt_c"], dt_s) * _plume_interp(x / sc["y_scale"],
                                                          2)
        return tamb + max(dt_film, dt_pl)

    return sample, {"delta_bar_m": delta_bar, "delta_top_m": delta_top,
                    "z_match_m": z_match, "z0_m": z0,
                    "have_plume": have_plume, "film_c": c}
