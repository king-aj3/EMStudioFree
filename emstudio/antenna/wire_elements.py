# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wire-element synthesis: dipole / monopole / folded dipole / λ-fraction
verticals (Element Designer slice E1).

Design formulas computed from FIRST PRINCIPLES — L = K·c/(2f) — with the
famous ham constants (468/f ft, 234/f ft, ~143/f m) exposed only as derived
display conventions: printed 468 embeds K = 0.9516, our thin-wire default is
K = 0.95 (they differ 0.17 %, both inside the published K-curve spread).

Sources (every anchor multiply-verified 2026-07-17, de-risk in PROJECT
docs/ELEMENT_DESIGNER_PLAN.md §2.1):

* ARRL Antenna Book: 468/f = (491.786/f)·0.9516 end-effect; the K-shortening
  curve vs conductor thickness (~0.98 very thin → ~0.91 thick tube).
  Published K charts DISAGREE by ~±0.01 across 13 curves (Stearns/K6OIK
  survey), so the curve shipped here is the one MEASURED on this repo's own
  NEC2 writer/nec2c 1.3.1 (standard kernel) — self-consistent with the
  shipped dipole/monopole gates and the Verify workflow. The published
  numeric spine (Balanis 4e 0.9352 @ ratio 50; Hansen 0.9557 @ 250,
  0.9812 @ 250k) sits within ~0.02: the measured curve reads BELOW the
  printed charts at thick ratios (the known NEC2 delta-gap effect —
  Stearns/K6OIK).
* Balanis ch. 4: exact thin λ/2 dipole Z = 73.08 + j42.52 Ω (+j = INDUCTIVE
  = slightly LONG — resonance needs shortening); resonant-short R ≈ 68–72 Ω;
  λ/4 monopole over PEC = exactly half (36.5 + j21.25 class).
* Balanis §9.5: equal-diameter folded dipole ≈ 4× step-up (~288 Ω; 280–300
  printed window). LIVE-VERIFIED on this repo's writer: 283.0 Ω at the
  resonance (3.94×), zero nec2c warnings.
* λ/2 dipole gain 2.15 dBi (D = 1.643); gain_dbd = gain_dbi − 2.15 always
  carried BOTH ways (the classic silent-2.15-dB trap).
* 5/8-wave vertical: capacitive feed X (strongly radius-dependent — live:
  62−j259 Ω at r = 0.5 mm vs 48−j170 at 2 mm), needs a series-L base
  network (§7 territory — report-only here); gain 2.85–3 dB over λ/4 ONLY
  over infinite PEC (Ballantine), 1–2 dB typical over real ground.

In-repo ground truth reproduced for free: templates/dipole.py L = 0.475·λ
(= 0.95·λ/2 EXACTLY — bit-identical in float64); dipole_nec2.py reference
f_res 296.29 MHz / 71.9 Ω / 2.13 dBi; monopole_nec2.py 39.5 + j22.6 Ω is
the UNSHORTENED physical λ/4 geometry (do not compare the shortened design
length against it — like-for-like only).

All SI; ``_ft`` keys are US-customary convenience outputs. Pure-python,
Qt-free, FreeCAD-free; results are dicts of plain floats (house rule).
"""
from __future__ import annotations

import math

C0 = 299792458.0          # m/s (exact)
FT_PER_M = 1.0 / 0.3048   # international foot (exact)

K_THIN_WIRE_DEFAULT = 0.95   # thin-wire end-effect default (ARRL class)
DIPOLE_GAIN_DBI = 2.15       # lambda/2 dipole peak gain (0 dBd by definition)
DBD_OFFSET = 2.15            # gain_dbd = gain_dbi - 2.15

# Resonant (X = 0) feed resistances — textbook class values cross-checked
# against the in-repo NEC2 references (71.9 / 39.5-unshortened).
DIPOLE_RES_R_OHM = 72.0
MONOPOLE_RES_R_OHM = 36.0
FOLDED_STEP_UP = 4.0

SMALL_ANTENNA_FRACTION = 0.1  # < lambda/10 -> route to small_antenna.py

#: K vs the HALF-WAVELENGTH-to-diameter ratio (lambda/(2d)) — NOT L/d for
#: non-half-wave elements (the ratio-axis trap: monopoles use their own
#: half-wave ratio). MEASURED on this repo's NEC2 writer (nec2c 1.3.1,
#: standard kernel, 27 segments, X=0 by frequency shift; method cross-checked
#: against a length sweep to 0.033%). The thickest point carries a standard-
#: kernel caveat (EK cross-check reads K 0.6% higher there).
K_CURVE_NEC2 = [
    (21.0, 0.90460),    # thick tube (EK kernel: 0.91015 — honesty note)
    (51.6, 0.91934),
    (126.5, 0.93822),   # the shipped-template deck's ratio (r=2mm @ 300 MHz)
    (200.8, 0.94564),
    (987.1, 0.96172),
    (4892.2, 0.97026),  # very thin wire
]


def wavelength_m(f0_hz):
    return C0 / float(f0_hz)


def k_from_ratio(halfwave_over_d):
    """K (end-effect shortening) vs λ/(2d) — log-linear interp over the
    NEC2-measured curve, clamped at the measured ends."""
    x = math.log10(max(float(halfwave_over_d), 1e-9))
    pts = [(math.log10(r), k) for r, k in K_CURVE_NEC2]
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, k0), (x1, k1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return k0 + (k1 - k0) * (x - x0) / (x1 - x0)
    return K_THIN_WIRE_DEFAULT  # unreachable


def _resolve_k(f0_hz, wire_d_m, k_factor):
    """K per the caller's choice: None = 0.95 default (keeps the shipped
    template inversion bit-exact), "curve" = the NEC2-measured curve at this
    design's λ/(2d), a float = verbatim."""
    if k_factor is None:
        return K_THIN_WIRE_DEFAULT
    if k_factor == "curve":
        if not wire_d_m or float(wire_d_m) <= 0:
            return K_THIN_WIRE_DEFAULT
        return k_from_ratio(wavelength_m(f0_hz) / (2.0 * float(wire_d_m)))
    return float(k_factor)


def _gain_pack(gain_dbi):
    return {"gain_dbi": float(gain_dbi), "gain_dbd": float(gain_dbi) - DBD_OFFSET}


def design_dipole(f0_hz, wire_d_m, k_factor=None):
    """Half-wave dipole synthesis: total length L = K · c / (2 · f0).

    ``k_factor``: None → thin-wire 0.95 (L = 0.475 λ exactly, the shipped
    template length); ``"curve"`` → the NEC2-measured K at this λ/(2d);
    float → verbatim.
    """
    f0 = float(f0_hz)
    k = _resolve_k(f0, wire_d_m, k_factor)
    length_m = k * C0 / (2.0 * f0)
    warnings = []
    ratio = wavelength_m(f0) / (2.0 * float(wire_d_m)) if wire_d_m else float("inf")
    if ratio < 50.0:
        warnings.append(
            "lambda/2d = {0:.0f} is thick-element territory: the 0.95 default "
            "is a thin-wire value (measured curve -> ~0.90 there, and NEC2's "
            "standard kernel itself reads ~0.6% low vs the extended kernel); "
            'use k_factor="curve" and solver-verify'.format(ratio))
    out = {
        "length_m": length_m,
        "length_ft": length_m * FT_PER_M,
        "k_factor": k,
        "halfwave_over_d": ratio,
        "feed_r_ohm": DIPOLE_RES_R_OHM,
        "feed_x_ohm": 0.0,  # resonant by construction (design length)
        "warnings": warnings,
        "source_note": (
            "L = K*c/(2f), K={0:g} (ARRL 468/f embeds K=0.9516); Balanis ch.4 "
            "resonant R~72 ohm; in-repo NEC2 ref: 0.475*lambda at 300 MHz -> "
            "f_res 296.29 MHz, R 71.9 ohm, 2.13 dBi".format(k)),
    }
    out.update(_gain_pack(DIPOLE_GAIN_DBI))
    return out


def design_monopole(f0_hz, wire_d_m, k_factor=None):
    """Quarter-wave monopole over ground: height = half the dipole length
    (the 234/f consistency); feed Z = half the dipole's (~36 Ω resonant;
    textbook 36.5 + j21.25 at the exact λ/4 physical length)."""
    dip = design_dipole(f0_hz, wire_d_m, k_factor=k_factor)
    out = {
        "length_m": dip["length_m"] / 2.0,
        "length_ft": dip["length_ft"] / 2.0,
        "k_factor": dip["k_factor"],
        "halfwave_over_d": dip["halfwave_over_d"],
        "feed_r_ohm": MONOPOLE_RES_R_OHM,
        "feed_x_ohm": 0.0,
        "warnings": list(dip["warnings"]) + [
            "assumes a good ground plane / radial system; finite ground adds "
            "series loss R (see the monopole_nec2.py finite-ground leg)"],
        "source_note": (
            "234/f ft (= 468/f halved, bit-exact); Balanis: Z(monopole) = "
            "Z(dipole)/2 -> 36.5+j21 class at exactly lambda/4; in-repo NEC2 "
            "ref (UNSHORTENED physical 0.25*lambda over PEC): 39.5+j22.6"),
    }
    out.update(_gain_pack(DIPOLE_GAIN_DBI + 3.0))  # 5.15 dBi class over PEC
    return out


def design_folded_dipole(f0_hz, wire_d_m, k_factor=None):
    """Folded dipole (equal-diameter two-wire fold): plain-dipole length,
    ~4× feed-R step-up → ~288 Ω (280–300 printed window). LIVE-verified on
    this repo's NEC2 writer: 283.0 Ω (3.94×) at the fold's resonance."""
    dip = design_dipole(f0_hz, wire_d_m, k_factor=k_factor)
    out = dict(dip)
    out["feed_r_ohm"] = FOLDED_STEP_UP * DIPOLE_RES_R_OHM
    out["feed_x_ohm"] = 0.0
    out["warnings"] = list(dip["warnings"])
    out["source_note"] = (
        "Balanis 9.5 equal-diameter fold: ~4x step-up -> ~288 ohm (280-300 "
        "window); live NEC2 verification on this writer: 283 ohm, 3.94x. "
        "Unequal-diameter folds give other ratios (out of this slice)")
    return out


def fraction_table(f0_hz, wire_d_m=None, k_factor=None):
    """λ-fraction vertical table: electrical fraction → physical length via
    the same K. Honest per-row notes (5/8 and the anti-resonant rows need §7
    matching — report-only here); < λ/10 routes to small_antenna.py."""
    f0 = float(f0_hz)
    lam = wavelength_m(f0)
    k = _resolve_k(f0, wire_d_m, k_factor)
    spec = [
        (0.25, "quarter-wave vertical",
         "resonant, ~36 ohm class over good ground; the workhorse", 5.15),
        (0.5, "half-wave (dipole if center-fed)",
         "center-fed = the lambda/2 dipole (~72 ohm); END-fed half-wave is "
         "high-Z (kohm class) and needs a transformer (section-7 territory)",
         2.15),
        (0.625, "5/8-wave vertical",
         "max broadside-gain vertical: 2.85-3 dB over lambda/4 over infinite "
         "PEC (Ballantine), 1-2 dB typical over real ground; NOT resonant — "
         "capacitive feed X (radius-dependent; live: 62-j259 ohm at r=0.5mm) "
         "NEEDS a series-L base network (section-7)", 8.15),
        (0.75, "3/4-wave vertical",
         "resonant again but feed R rises and the pattern grows high-angle "
         "lobes", 5.15),
        (1.0, "full-wave",
         "current minimum at the feed: very high feed Z; impractical fed "
         "against ground without matching (section-7)", 3.15),
    ]
    rows = []
    for frac, name, note, gain_dbi in spec:
        length_m = k * frac * lam
        row = {
            "fraction": frac,
            "name": name,
            "electrical_len_m": frac * lam,
            "length_m": length_m,
            "length_ft": length_m * FT_PER_M,
            "k_factor": k,
            "note": note,
            "route": "wire_elements",
        }
        row.update(_gain_pack(gain_dbi))
        rows.append(row)
    return {
        "f0_hz": f0,
        "lambda_m": lam,
        "rows": rows,
        "route_below_note": (
            "fractions < {0:g} lambda ({1:.3g} m here) are electrically "
            "small: route to small_antenna.py (Chu-Q guardrail + loading-"
            "coil design, shipped)".format(
                SMALL_ANTENNA_FRACTION, SMALL_ANTENNA_FRACTION * lam)),
    }


def route_for_length(length_m, f0_hz):
    """Router guard: physical length below λ/10 → the small-antenna family."""
    if float(length_m) < SMALL_ANTENNA_FRACTION * wavelength_m(f0_hz):
        return "small_antenna"
    return "wire_elements"


def dbi_to_dbd(gain_dbi):
    return float(gain_dbi) - DBD_OFFSET


def dbd_to_dbi(gain_dbd):
    return float(gain_dbd) + DBD_OFFSET


# --- famous-constant cross-checks (derived, never hard-coded) --------------
def imperial_dipole_const(k_factor=K_THIN_WIRE_DEFAULT):
    """L(ft) = const/f(MHz): K·(c_ft/2)/1e6. K=0.95 → 467.196 (printed 468
    embeds K=0.951634 — a round-number convention 0.17 % above the default)."""
    return k_factor * (C0 * FT_PER_M / 1e6) / 2.0


def metric_dipole_const(k_factor=K_THIN_WIRE_DEFAULT):
    """L(m) = const/f(MHz): K·(c/2)/1e6. K=0.95 → 142.401 (printed-468
    equivalent 142.646; the common ham 143 embeds K≈0.954)."""
    return k_factor * C0 / 2.0 / 1e6
