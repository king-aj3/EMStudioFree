# SPDX-License-Identifier: LGPL-2.1-or-later
"""Yagi-Uda synthesis from NBS Technical Note 688 (Element Designer slice E3).

A Yagi-Uda is ONE element (a single feed port) per the §1 scope contract, even
with N parasitic wires. This module turns a frequency + a gain (or boom-length)
target into a fully dimensioned Yagi — reflector, driven element, and N directors
— using the verified NBS TN-688 (Viezbicke 1976, public domain) design data.

Sources — every anchor transcribed from the NIST scan PAGE IMAGES and
cross-verified (de-risk 2026-07-18; full provenance in
docs/upstream/tn688-yagi-anchors.md):

* **Table 1** — optimized element lengths for six boom lengths at the reference
  element diameter d/λ = 0.0085, f = 400 MHz, reflector 0.2 λ behind the driven
  element. Encoded VERBATIM in ``TN688_TABLE1`` below (the 0.4 λ director is
  0.424 — NOT the 0.442 that Balanis Table 10.6 mis-prints; primary NBS + our own
  NEC2 both back 0.424).
* **Figure 9** — diameter compensation: elements lengthen as d/λ drops below the
  0.0085 reference. Modeled first-order (director and reflector have different
  d/λ sensitivity); reproduces the 0.8 λ worked example exactly and the 4.2 λ
  example to ~0.004 λ (the graphical arc-transpose curvature, below the paper's
  own 0.003 λ cut tolerance's physical significance — NEC2 gain is unchanged).
* **Figure 10** — supporting-boom correction: a metal boom electrically lengthens
  the parasitics, so they are cut LONGER by an additive amount that is log-linear
  in the boom diameter D/λ. This is a BUILD correction only — it is NOT applied to
  the bare-wire NEC2 model (which has no metal boom); see ``base`` vs ``cut``.

Gains are the NBS **measured** values (dBd, at 400 MHz over a range of lengths);
NEC2 reproduces them to ±0.25 dB (docs/upstream). ``gain_dbd`` and ``gain_dbi``
are always both carried (gain_dbi = gain_dbd + 2.15).

Pure-python, Qt-free, FreeCAD-free; results are dicts of plain floats (house rule).
All SI. The driven-element length reuses the E1 dipole synthesis (``wire_elements``).
"""
from __future__ import annotations

import math

from emstudio.antenna import wire_elements

C0 = 299792458.0
FT_PER_M = 1.0 / 0.3048

#: Reference element diameter-to-wavelength ratio Table 1 is drawn at.
D_REF = 0.0085
#: Diameter-compensation slopes (Δλ per decade of d/λ) — Fig 9, fit to the two
#: worked examples: director curve is steeper than the reflector curve.
K_DIR = 0.048
K_REFL = 0.010
#: Boom-correction line (Fig 10): Δ = max(0, B0 + B_SLOPE·log10((D/λ)/D_REF)).
BOOM_B0 = 0.005
BOOM_SLOPE = 0.03416

DBD_OFFSET = wire_elements.DBD_OFFSET  # 2.15

#: TN-688 Table 1 — VERBATIM. Keyed by boom length in λ. ``directors`` lists the
#: per-director lengths in λ (at d/λ = 0.0085); ``spacing`` is the director
#: spacing in λ; ``reflector`` the reflector length in λ; ``gain_dbd`` the
#: NBS-measured gain over a λ/2 dipole; ``curve`` the Fig 9 design curve.
TN688_TABLE1 = {
    0.4: {"reflector": 0.482, "spacing": 0.20, "gain_dbd": 7.1, "curve": "A",
          "directors": [0.424]},
    0.8: {"reflector": 0.482, "spacing": 0.20, "gain_dbd": 9.2, "curve": "B",
          "directors": [0.428, 0.424, 0.428]},
    1.2: {"reflector": 0.482, "spacing": 0.25, "gain_dbd": 10.2, "curve": "B",
          "directors": [0.428, 0.420, 0.420, 0.428]},
    2.2: {"reflector": 0.482, "spacing": 0.20, "gain_dbd": 12.25, "curve": "C",
          "directors": [0.432, 0.415, 0.407, 0.398, 0.390,
                        0.390, 0.390, 0.390, 0.398, 0.407]},
    3.2: {"reflector": 0.482, "spacing": 0.20, "gain_dbd": 13.4, "curve": "B",
          "directors": [0.428, 0.420, 0.407, 0.398, 0.394, 0.390, 0.386,
                        0.386, 0.386, 0.386, 0.386, 0.386, 0.386, 0.386, 0.386]},
    4.2: {"reflector": 0.475, "spacing": 0.308, "gain_dbd": 14.2, "curve": "D",
          "directors": [0.424, 0.424, 0.420, 0.407, 0.403, 0.398, 0.394,
                        0.390, 0.390, 0.390, 0.390, 0.390, 0.390]},
}
#: Boom classes in ascending order (for gain-target selection).
BOOM_CLASSES = sorted(TN688_TABLE1)


def wavelength_m(f0_hz):
    return C0 / float(f0_hz)


def boom_class_for_gain(gain_dbd):
    """Smallest TN-688 boom (λ) whose measured gain meets ``gain_dbd``.

    Returns the boom-length key, or ``None`` when the target exceeds the table's
    14.2 dBd (stacking is §7 System Designer territory).
    """
    for boom in BOOM_CLASSES:
        if TN688_TABLE1[boom]["gain_dbd"] >= float(gain_dbd) - 1e-9:
            return boom
    return None


def nearest_boom_class(boom_lambda):
    """The tabulated boom length closest to ``boom_lambda``."""
    return min(BOOM_CLASSES, key=lambda b: abs(b - float(boom_lambda)))


def diameter_compensation(d_over_lambda, kind):
    """Fig 9 length shift (λ) for an element at ``d_over_lambda`` vs the 0.0085
    reference. ``kind`` is "director" or "reflector". Positive = longer (thinner).
    """
    if not d_over_lambda or d_over_lambda <= 0:
        return 0.0
    k = K_DIR if kind == "director" else K_REFL
    return -k * math.log10(float(d_over_lambda) / D_REF)


def boom_correction(boom_d_over_lambda):
    """Fig 10 additive length increase (λ) for a metal support boom of diameter
    ratio ``boom_d_over_lambda``. 0 when there is no (or a negligible) boom."""
    if not boom_d_over_lambda or boom_d_over_lambda <= 0:
        return 0.0
    return max(0.0, BOOM_B0 + BOOM_SLOPE * math.log10(
        float(boom_d_over_lambda) / D_REF))


def _gain_pack(gain_dbd):
    return {"gain_dbd": float(gain_dbd),
            "gain_dbi": float(gain_dbd) + DBD_OFFSET}


def compensated_lengths(boom_lambda, d_over_lambda, boom_d_over_lambda=0.0):
    """Table 1 lengths (λ) for ``boom_lambda`` with the Fig 9 diameter
    compensation and the Fig 10 boom correction applied.

    Returns a dict with, per element, the ``base`` length (Table 1 + diameter
    compensation — the BARE-WIRE length for a NEC2 model) and the ``cut`` length
    (base + boom correction — the physical length to cut for a metal boom).
    """
    row = TN688_TABLE1[boom_lambda]
    dboom = boom_correction(boom_d_over_lambda)
    d_refl = diameter_compensation(d_over_lambda, "reflector")
    d_dir = diameter_compensation(d_over_lambda, "director")

    refl_base = row["reflector"] + d_refl
    directors = []
    for L in row["directors"]:
        base = L + d_dir
        directors.append({"table": L, "base": base, "cut": base + dboom})
    return {
        "reflector": {"table": row["reflector"], "base": refl_base,
                      "cut": refl_base + dboom},
        "directors": directors,
        "boom_correction_lambda": dboom,
        "diameter_shift_director_lambda": d_dir,
        "diameter_shift_reflector_lambda": d_refl,
    }


def design_yagi(f0_hz, gain_dbd=None, boom_lambda=None, wire_d_m=0.006,
                boom_d_m=0.0, driven_k=None):
    """Synthesize a Yagi-Uda from a frequency + a gain (or boom-length) target.

    :param f0_hz: design frequency (Hz).
    :param gain_dbd: target gain over a λ/2 dipole (dBd). Selects the smallest
        TN-688 boom that meets it. Use this OR ``boom_lambda``.
    :param boom_lambda: explicit boom length in λ (snapped to the nearest
        tabulated class). Use this OR ``gain_dbd``.
    :param wire_d_m: parasitic-element conductor diameter (m) → the d/λ that
        drives the Fig 9 diameter compensation.
    :param boom_d_m: metal support-boom diameter (m); 0 = no boom correction
        (e.g. a non-conductive boom or wires in free space).
    :param driven_k: end-effect K for the driven element (see wire_elements);
        None = the thin-wire 0.95 default.

    Returns a dict: boom class + gain (dBd & dBi), the ordered element list
    (reflector, driven, directors) with positions along the boom and both the
    bare-wire ``length_m`` (for NEC2) and the physical ``cut_length_m``, plus the
    boom length, spacing, d/λ ratios, warnings and a source note. Raises
    ``ValueError`` on a bad request.
    """
    f0 = float(f0_hz)
    lam = wavelength_m(f0)
    if (gain_dbd is None) == (boom_lambda is None):
        raise ValueError("give exactly one of gain_dbd or boom_lambda")

    warnings = []
    if gain_dbd is not None:
        boom = boom_class_for_gain(gain_dbd)
        if boom is None:
            raise ValueError(
                "{0:g} dBd exceeds the TN-688 single-boom table (max 14.2 dBd "
                "at the 4.2-lambda boom); stacking arrays is section-7 "
                "territory".format(float(gain_dbd)))
        if TN688_TABLE1[boom]["gain_dbd"] > float(gain_dbd) + 1e-9:
            warnings.append(
                "no boom yields exactly {0:g} dBd; using the {1:g}-lambda class "
                "({2:g} dBd)".format(
                    float(gain_dbd), boom, TN688_TABLE1[boom]["gain_dbd"]))
    else:
        req = float(boom_lambda)
        boom = nearest_boom_class(req)
        if abs(boom - req) > 1e-9:
            warnings.append(
                "boom {0:g} lambda snapped to the nearest tabulated class "
                "{1:g} lambda".format(req, boom))

    row = TN688_TABLE1[boom]
    d_over_lam = float(wire_d_m) / lam if wire_d_m else 0.0
    boom_d_over_lam = float(boom_d_m) / lam if boom_d_m else 0.0
    comp = compensated_lengths(boom, d_over_lam, boom_d_over_lam)
    spacing = row["spacing"]

    if d_over_lam and (d_over_lam < 0.001 or d_over_lam > 0.04):
        warnings.append(
            "d/lambda = {0:.4f} is outside the TN-688 measured range "
            "(0.001-0.04); the diameter compensation is extrapolated — "
            "solver-verify".format(d_over_lam))
    if boom_d_over_lam and boom_d_over_lam > 0.04:
        warnings.append(
            "boom d/lambda = {0:.4f} exceeds the Fig 10 range (0.04); the boom "
            "correction is extrapolated".format(boom_d_over_lam))

    # driven element: NOT in Table 1 — reuse the E1 dipole synthesis (a resonant
    # ~0.475-lambda dipole), tunable; a folded driven gives a 4x-higher feed R.
    driven = wire_elements.design_dipole(f0, wire_d_m, k_factor=driven_k)
    driven_len_lam = driven["length_m"] / lam

    # positions along the boom (x, in lambda): reflector at 0, driven 0.2 behind
    # it, directors from the driven at the tabulated spacing.
    elements = [{
        "name": "Reflector", "kind": "reflector",
        "position_lambda": 0.0,
        "length_lambda": comp["reflector"]["base"],
        "cut_length_lambda": comp["reflector"]["cut"],
    }, {
        "name": "Driven", "kind": "driven",
        "position_lambda": 0.2,
        "length_lambda": driven_len_lam,
        "cut_length_lambda": driven_len_lam,   # driven has no boom correction here
    }]
    for i, dd in enumerate(comp["directors"], 1):
        elements.append({
            "name": "Director {0}".format(i), "kind": "director",
            "position_lambda": 0.2 + i * spacing,
            "length_lambda": dd["base"],
            "cut_length_lambda": dd["cut"],
        })
    for e in elements:
        e["position_m"] = e["position_lambda"] * lam
        e["length_m"] = e["length_lambda"] * lam
        e["cut_length_m"] = e["cut_length_lambda"] * lam

    boom_length_lam = elements[-1]["position_lambda"]  # reflector -> last director
    out = {
        "family": "yagi",
        "f0_hz": f0,
        "wavelength_m": lam,
        "boom_lambda": boom,
        "boom_length_m": boom_length_lam * lam,
        "n_directors": len(row["directors"]),
        "n_elements": len(elements),
        "director_spacing_lambda": spacing,
        "director_spacing_m": spacing * lam,
        "reflector_spacing_lambda": 0.2,
        "d_over_lambda": d_over_lam,
        "boom_d_over_lambda": boom_d_over_lam,
        "boom_correction_lambda": comp["boom_correction_lambda"],
        "driven_length_m": driven["length_m"],
        "driven_feed_r_ohm": driven["feed_r_ohm"],
        "folded_driven_feed_r_ohm": driven["feed_r_ohm"] * wire_elements.FOLDED_STEP_UP,
        "elements": elements,
        "warnings": warnings + [
            "gain is the NBS TN-688 MEASURED value (400 MHz); use Verify with "
            "NEC2 for the achieved gain/pattern at your frequency",
            "the driven element (~{0:.3g} lambda) is a starting point — tune it "
            "or use a folded driven (~{1:.0f} ohm) + balun for 50/200 ohm; "
            "matching is section-7".format(
                driven_len_lam, driven["feed_r_ohm"] * wire_elements.FOLDED_STEP_UP),
        ],
        "source_note": (
            "NBS TN-688 Table 1 ({0:g}-lambda boom, {1} directors, {2:g} dBd "
            "measured) + Fig 9 diameter compensation + Fig 10 boom correction; "
            "reflector 0.2 lambda behind driven, directors spaced {3:g} lambda. "
            "d/lambda={4:.4f}. Bare-wire lengths for NEC2; add the boom "
            "correction ({5:+.4f} lambda) for a metal boom.".format(
                boom, len(row["directors"]), row["gain_dbd"], spacing,
                d_over_lam, comp["boom_correction_lambda"])),
    }
    out.update(_gain_pack(row["gain_dbd"]))
    return out
