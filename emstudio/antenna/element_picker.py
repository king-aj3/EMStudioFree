# SPDX-License-Identifier: LGPL-2.1-or-later
"""Element-family recommender (Element Designer slice E2).

Deterministic, rule-based scoring over a requirements dict → ranked
``(family, score, rationale)`` candidates, band_picker style: every rule
carries a one-line printable rationale (the "AI" transparency requirement,
ELEMENT_DESIGNER_PLAN §1.3). This is the stable API the §3 AI assistant
(shipped v0.71-v0.73) and the optional LLM intent parser both target.

Requirements schema (plain dict; every key optional except a frequency):

    req = {
        "f0_hz": ...,               # or "f_lo_hz"/"f_hi_hz" for band designs
        "gain_dbi": None,           # target gain (None = don't care) …
        "gain_dbd": None,           # … either scale accepted (dBd = dBi − 2.15)
        "pattern": "omni"|"directional"|None,
        "polarization": "V"|"H"|"CP"|None,   # CP families are post-MVP breadth
        "max_dim_m": None,          # size envelope (drives the Chu guardrail)
        "wire_d_m": None,           # conductor diameter (K-curve correction)
        "er": None, "h_m": None,    # substrate (signals a planar/patch intent)
    }

Family availability is honest, and as of v1.10.0 **every family in
``FAMILIES`` is shipped** — wire, small-antenna, Yagi, patch, LPDA, pyramidal
horn, printed inverted-F and PIFA all carry ``avail=True`` with no ships-in
flag, which the picker gate asserts. (The ships-in machinery is kept for the
next family that is recommended before its page lands.) The Chu-Q guardrail
is the shipped ``small_antenna`` machinery, reused verbatim; the boom-length
hint for the Yagi rule uses the NBS TN-688 boom/gain columns (the full
verified table lives in ``emstudio.antenna.yagi``).

⚠ SHIPPED IS NOT REACHABLE, and the two have to be checked separately. Until
2026-08-29 ``horn``, ``ifa`` and ``pifa`` carried ``avail=True`` while NO rule
in ``recommend_element`` ever scored them, so the loop at the bottom (which
drops anything still at 0.0) removed all three from every result that has ever
been produced: three validated, templated, tutorialised engines that the
recommender built to route users to them could not name. Every family therefore
needs a rule, and the routing rule for each is:

    wire           the default workhorse; demoted when it does not fit
    small_antenna  below 3 MHz, or an envelope under lambda/10, or no room
    yagi           gain target >= 5 dBd, narrow band, TN-688 boom class
    patch          GHz-class, or substrate (er/h) given
    lpda           band ratio above LPDA_RATIO
    horn           gain >= HORN_MIN_GAIN_DBI at/above HORN_MIN_F_HZ
    ifa / pifa     an envelope with no room for a resonant dipole, at or
                   above HANDSET_MIN_F_HZ

Pure-python, Qt-free, FreeCAD-free; results are dicts of plain values
(house rule).
"""
from __future__ import annotations

import math

from emstudio.antenna import (band_picker, horn, ifa, pifa, small_antenna,
                              wire_elements)

#: family key → (label, available now, slice that ships it if not).
FAMILIES = [
    ("wire", "Wire (dipole / monopole / folded)", True, None),
    ("small_antenna", "Small antenna (VLF/LF/MF)", True, None),
    ("yagi", "Yagi-Uda", True, None),
    ("patch", "Microstrip patch", True, None),
    ("lpda", "LPDA (log-periodic)", True, None),
    ("horn", "Pyramidal horn (waveguide-fed, microwave)", True, None),
    ("ifa", "Inverted-F, printed (PCB/handset)", True, None),
    ("pifa", "PIFA (planar inverted-F)", True, None),
]
FAMILY_INFO = {k: (label, avail, ships) for k, label, avail, ships in FAMILIES}

#: NBS TN-688 Table 1 boom/gain columns (dBd, boom in λ). Used here as a
#: boom-size HINT for the gain rule; the full verified table + per-director
#: lengths live in ``emstudio.antenna.yagi`` (the shipped Yagi synthesis).
TN688_BOOM_GAIN = [
    (0.4, 7.1),
    (0.8, 9.2),
    (1.2, 10.2),
    (2.2, 12.25),
    (3.2, 13.4),
    (4.2, 14.2),
]

#: A band design is "wide" (log-periodic territory) above this f_hi/f_lo.
LPDA_RATIO = 1.5

#: Lowest frequency at which the horn is scored. Not a limit of the shipped
#: engine (``horn.py`` has none) — it is this RECOMMENDER declining to send a
#: user somewhere daft: a 20 dBi horn at 1 GHz already has a mouth over a
#: metre across, on waveguide plumbing to match, and the Yagi/LPDA families
#: own that band with a fraction of the metalwork.
HORN_MIN_F_HZ = 1.0e9

#: Gain target (dBi) at which the horn enters the ranking: the bottom of the
#: classic standard-gain-horn range (15-25 dBi), and well above what a single
#: microstrip patch gives (~7 dBi). The TN-688 Yagi table still reaches
#: 14.2 dBd = 16.35 dBi, so in the 15-16 dBi overlap the horn deliberately
#: does NOT suppress the Yagi — both score, and the user reads both rationales.
HORN_MIN_GAIN_DBI = 15.0

#: Band ratio ONE horn (its feed waveguide, really) covers in one piece.
#: Standard rectangular-waveguide bands are ~1.51:1 — WR-90 is 8.2-12.4 GHz,
#: WR-28 is 26.5-40 GHz — and 1.6 leaves room for a user typing the round
#: numbers (8-12.5 GHz is 1.56:1). Above this the LPDA rule is right and the
#: horn says so in its rationale instead of competing.
HORN_BAND_RATIO = 1.6

#: Lowest frequency at which the IFA/PIFA families are scored. The folded
#: quarter-wave path is c/4f = 250 mm at 300 MHz — already longer than any
#: hand-held device — so a smaller element below this is a LOADED whip (the
#: small-antenna family), not a handset element. Both shipped engines are
#: anchored inside 0.86-2.45 GHz (docs/upstream/{ifa,pifa}-anchors.md).
HANDSET_MIN_F_HZ = 300e6

#: Gain (dBi) above which a single IFA/PIFA is demoted rather than offered.
#: Huynh's Table 5-1 for the shipped PIFA geometry computes 1.24-4.95 dBi
#: across every ground-plane size it tabulates (docs/upstream/pifa-anchors.md),
#: so a target above the TOP of that spread cannot come out of one of these
#: elements on any chassis — the ground plane sets it, not the element.
HANDSET_MAX_GAIN_DBI = 5.0


def normalize_req(req):
    """Fill the schema defaults and derive the design frequency & band ratio.

    ``f0_hz`` wins if given; else the geometric mean of ``f_lo_hz``/``f_hi_hz``.
    Gain is normalized to BOTH scales (dBd = dBi − 2.15, the E1 discipline).
    Raises ``ValueError`` when no frequency is given.
    """
    r = dict(req or {})
    f_lo = float(r["f_lo_hz"]) if r.get("f_lo_hz") else None
    f_hi = float(r["f_hi_hz"]) if r.get("f_hi_hz") else None
    if f_lo and f_hi and f_hi < f_lo:
        f_lo, f_hi = f_hi, f_lo
    if r.get("f0_hz"):
        f0 = float(r["f0_hz"])
    elif f_lo and f_hi:
        f0 = math.sqrt(f_lo * f_hi)  # geometric band centre
    elif f_lo or f_hi:
        f0 = float(f_lo or f_hi)
    else:
        raise ValueError("requirements need f0_hz or f_lo_hz/f_hi_hz")
    b_ratio = (f_hi / f_lo) if (f_lo and f_hi) else 1.0

    gain_dbd = None
    if r.get("gain_dbd") is not None:
        gain_dbd = float(r["gain_dbd"])
    elif r.get("gain_dbi") is not None:
        gain_dbd = wire_elements.dbi_to_dbd(float(r["gain_dbi"]))

    return {
        "f0_hz": f0,
        "f_lo_hz": f_lo,
        "f_hi_hz": f_hi,
        "b_ratio": b_ratio,
        "gain_dbd": gain_dbd,
        "gain_dbi": (wire_elements.dbd_to_dbi(gain_dbd)
                     if gain_dbd is not None else None),
        "pattern": r.get("pattern") or None,
        "polarization": r.get("polarization") or None,
        "max_dim_m": float(r["max_dim_m"]) if r.get("max_dim_m") else None,
        "wire_d_m": float(r["wire_d_m"]) if r.get("wire_d_m") else None,
        "er": float(r["er"]) if r.get("er") else None,
        "h_m": float(r["h_m"]) if r.get("h_m") else None,
    }


def yagi_boom_for_gain(gain_dbd):
    """Smallest TN-688 boom (λ) whose measured gain meets ``gain_dbd``.

    Returns ``(boom_lambda, table_gain_dbd)`` or ``None`` when the target
    exceeds the single-boom table (stacking is §7 territory).
    """
    for boom, g in TN688_BOOM_GAIN:
        if g >= float(gain_dbd) - 1e-9:
            return boom, g
    return None


def recommend_element(req):
    """Rank the element families for a requirements dict.

    Returns a dict: the normalized ``req``, band info, ``candidates`` (list
    of ``{family, label, score, available, ships_in, rationale}`` sorted by
    score, ties broken by the FAMILIES order), ``notes`` and an optional
    ``chu_warning``. Deterministic pure function → gated on canned scenarios.
    """
    r = normalize_req(req)
    f0 = r["f0_hz"]
    lam = wire_elements.wavelength_m(f0)
    band_key, band_name, _lo, _hi = band_picker.band_of(f0)

    scores = {k: 0.0 for k, _l, _a, _s in FAMILIES}
    why = {k: [] for k in scores}
    notes = []
    chu_warning = None

    # --- electrically-small regime + envelope fit ------------------------
    small = False
    quarter = 0.25 * lam          # a quarter-wave monopole: the smallest resonant element
    half = 0.475 * lam            # a resonant half-wave dipole (K≈0.95)
    wire_fits = (r["max_dim_m"] is None) or (r["max_dim_m"] >= quarter)
    if f0 < 3.0e6:
        small = True
        scores["small_antenna"] += 100.0
        why["small_antenna"].append(
            "below 3 MHz a resonant element is {0:.3g} km long — the "
            "Chu-Harrington small-antenna regime (shipped analytics + "
            "loading design)".format(half / 1e3))
    elif r["max_dim_m"] and r["max_dim_m"] < wire_elements.SMALL_ANTENNA_FRACTION * lam:
        small = True
        scores["small_antenna"] += 80.0
        why["small_antenna"].append(
            "the {0:.3g} m envelope is under lambda/10 ({1:.3g} m) — "
            "electrically small; loading + efficiency budget apply".format(
                r["max_dim_m"], wire_elements.SMALL_ANTENNA_FRACTION * lam))

    if not wire_fits:
        # no full-size resonant wire element fits the stated envelope
        scores["wire"] -= 40.0
        why["wire"].append(
            "the {0:.3g} m envelope is under a quarter-wave ({1:.3g} m) — a "
            "full-size resonant wire element does not fit; it needs loading "
            "(small-antenna family)".format(r["max_dim_m"], quarter))
        if not small:
            small = True
            scores["small_antenna"] += 50.0
            why["small_antenna"].append(
                "no full-size resonant element fits the {0:.3g} m envelope at "
                "{1} — the loading/efficiency budget applies".format(
                    r["max_dim_m"], band_picker._fmt_freq(f0)))
    elif small and r["max_dim_m"]:
        # small regime, but a full-size element actually fits (e.g. an LF mast)
        why["wire"].append(
            "a quarter-wave monopole is {0:.3g} m and fits the {1:.3g} m "
            "envelope (full-size LF/MF practice); the small-antenna family "
            "covers the loading/efficiency budget if you go smaller".format(
                quarter, r["max_dim_m"]))
    elif small:
        # small regime, no envelope given — full-size is impractically large
        scores["wire"] -= 20.0
        why["wire"].append(
            "a full-size resonant wire element is ~{0:.3g} m at this frequency "
            "— impractically large; the small-antenna family (loading) is the "
            "usual answer".format(half))
    elif r["max_dim_m"] and r["max_dim_m"] < half:
        # fits a quarter-wave monopole but not a half-wave dipole
        why["wire"].append(
            "only a quarter-wave monopole ({0:.3g} m, needs a ground plane) "
            "fits the {1:.3g} m envelope — a half-wave dipole ({2:.3g} m) does "
            "not".format(quarter, r["max_dim_m"], half))

    # --- Chu bandwidth guardrail (shipped machinery, reused verbatim) -----
    if r["max_dim_m"]:
        ka = 2.0 * math.pi * (r["max_dim_m"] / 2.0) / lam
        if ka < 0.5:
            q = small_antenna.chu_min_q(r["max_dim_m"] / 2.0, f0)
            fbw = small_antenna.fractional_bandwidth(q)
            # required fractional bandwidth about the geometric CENTRE f0, to
            # match small_antenna.fractional_bandwidth (df/f0) — not df/f_lo,
            # which would overstate the requirement by sqrt(b_ratio).
            need = ((r["b_ratio"] - 1.0) / math.sqrt(r["b_ratio"])
                    if r["b_ratio"] > 1.0 else None)
            chu_warning = (
                "Chu limit: ka = {0:.3g} → minimum Q {1:.3g}, best matched "
                "fractional bandwidth ~{2:.3g} % (VSWR 2)".format(
                    ka, q, fbw * 100.0))
            if need is not None and need > fbw:
                chu_warning += (
                    " — the requested {0:.3g} % band CANNOT fit this "
                    "envelope (physics, not engineering)".format(need * 100.0))
            why["small_antenna"].insert(0, chu_warning)

    # --- wide band → log-periodic ----------------------------------------
    if r["b_ratio"] > LPDA_RATIO:
        scores["lpda"] += 60.0
        why["lpda"].append(
            "band ratio {0:.2f} > {1:g} — a single resonant element cannot "
            "cover it; log-periodic (Carrel synthesis) is the wide-band "
            "wire answer".format(r["b_ratio"], LPDA_RATIO))
        if small:
            why["lpda"].append(
                "NOTE: lambda_max is ~{0:.3g} m here, so an LPDA is a very "
                "large (hundreds-of-metres) structure at this frequency".format(
                    wire_elements.wavelength_m(r["f_lo_hz"] or f0)))
    elif r["b_ratio"] > 1.15:
        notes.append(
            "band ratio {0:.2f}: a single resonant element covers ~a few "
            "percent — expect a compromise design or a matching network "
            "(§7)".format(r["b_ratio"]))

    # --- gain target → Yagi (TN-688 boom hint) ----------------------------
    if r["gain_dbd"] is not None and r["gain_dbd"] >= 5.0 and not small:
        if r["b_ratio"] > LPDA_RATIO:
            # a Yagi is narrow-band — do NOT compete with the LPDA over a wide
            # band (otherwise a tie hands the wide-band job to the wrong family)
            why["yagi"].append(
                "a gain target was set, but the {0:.2f} band ratio needs a "
                "wide-band log-periodic, not a narrow-band Yagi".format(
                    r["b_ratio"]))
        else:
            scores["yagi"] += 50.0
            if r["pattern"] == "omni":
                scores["yagi"] -= 25.0
                why["yagi"].append(
                    "NOTE: a Yagi is directional — it conflicts with the "
                    "'omni' pattern requirement")
            row = yagi_boom_for_gain(r["gain_dbd"])
            if row:
                boom_m = row[0] * lam
                # the antenna's largest dimension is the boom OR, on the short
                # 0.4-lambda boom, the 0.482-lambda reflector
                span_m = max(row[0], 0.482) * lam
                why["yagi"].append(
                    "{0:.3g} dBd target → NBS TN-688 {1:g}-lambda boom class "
                    "({2:.3g} dBd measured; boom ~{3:.2f} m at {4}) — dimensioned "
                    "by the shipped Yagi synthesis, NEC2-verifiable".format(
                        r["gain_dbd"], row[0], row[1], boom_m,
                        band_picker._fmt_freq(f0)))
                if r["max_dim_m"] and span_m > r["max_dim_m"]:
                    scores["yagi"] -= 30.0
                    why["yagi"].append(
                        "element span ~{0:.2f} m (boom or the 0.482-lambda "
                        "reflector) exceeds the {1:.3g} m envelope — the gain "
                        "target does not fit (drop gain or grow the "
                        "envelope)".format(span_m, r["max_dim_m"]))
                elif r["max_dim_m"]:
                    scores["yagi"] += 10.0
                    why["yagi"].append(
                        "element span ~{0:.2f} m fits the {1:.3g} m "
                        "envelope".format(span_m, r["max_dim_m"]))
            else:
                scores["yagi"] -= 30.0
                why["yagi"].append(
                    "{0:.3g} dBd exceeds the TN-688 single-boom table (max "
                    "14.2 dBd at 4.2 lambda) — stacked arrays are section-7 "
                    "System Designer territory".format(r["gain_dbd"]))

    # --- microwave + high gain → pyramidal horn ---------------------------
    # The gain the Yagi rule above cannot reach, at a frequency where an
    # aperture is small enough to hold. Scored from the SHIPPED synthesis
    # rather than a re-derivation, the way the Chu guardrail reuses
    # small_antenna: the aperture printed here is the one the horn page will
    # build, so the two can never quote different hardware.
    if (r["gain_dbi"] is not None and r["gain_dbi"] >= HORN_MIN_GAIN_DBI
            and f0 >= HORN_MIN_F_HZ):
        scores["horn"] += 60.0
        hd = horn.design_pyramidal(f0, r["gain_dbi"])
        span_m = max(hd["aperture_a1_m"], hd["aperture_b1_m"])
        why["horn"].append(
            "{0:.3g} dBi at {1} is aperture territory — an optimum-gain "
            "pyramidal horn (eps_ap {2:g}) needs a {3:.4g} x {4:.4g} mm "
            # ⚠ NOT "openEMS-verifiable" here, unlike the patch and IFA
            # rationales below. _recalc_horn() in element_dialog.py disables
            # BOTH Verify and Accept & Generate for this family on purpose
            # ("neither can take an arbitrary synthesised horn"), so promising
            # a verify the dialog then greys out is a claim the UI contradicts
            # in the same window. The openEMS evidence for horns is the shipped
            # Ka-band template and its horn_openems gate, not this page.
            "mouth, waveguide-fed; shipped synthesis. Verify and Accept are "
            "off for horns here — the Ka-band template and its gate cover "
            "that path".format(
                r["gain_dbi"], band_picker._fmt_freq(f0), hd["eps_ap"],
                hd["aperture_a1_m"] * 1e3, hd["aperture_b1_m"] * 1e3))
        if r["max_dim_m"] and span_m > r["max_dim_m"]:
            scores["horn"] -= 30.0
            why["horn"].append(
                "the {0:.3g} m aperture exceeds the {1:.3g} m envelope — that "
                "gain cannot come out of that opening; G = eps_ap*4*pi*A/"
                "lambda^2 ties the two together".format(
                    span_m, r["max_dim_m"]))
        elif r["max_dim_m"]:
            scores["horn"] += 10.0
            why["horn"].append(
                "the {0:.3g} m aperture fits the {1:.3g} m envelope".format(
                    span_m, r["max_dim_m"]))
        if r["b_ratio"] > LPDA_RATIO:
            if r["b_ratio"] <= HORN_BAND_RATIO:
                # Unlike the Yagi above, a horn does NOT step aside for the
                # LPDA at this width: this IS one waveguide band, the span a
                # horn is built to cover, and a tie on 60 points would hand a
                # Ka-band job to a log-periodic on FAMILIES order alone.
                scores["horn"] += 15.0
                why["horn"].append(
                    "the {0:.2f} band ratio is one rectangular-waveguide band "
                    "(WR-28 is 26.5-40 GHz, 1.51:1) — a horn covers that in a "
                    "single piece, so the width is not a reason to prefer the "
                    "log-periodic here".format(r["b_ratio"]))
            else:
                why["horn"].append(
                    "NOTE: the {0:.2f} band ratio is wider than one waveguide "
                    "band — a single horn and feed cannot cover it (the "
                    "log-periodic candidate is the honest answer)".format(
                        r["b_ratio"]))

    # --- GHz → patch; substrate (er/h) signals patch intent at any band ---
    if f0 >= 1.0e9:
        scores["patch"] += 40.0
        why["patch"].append(
            "GHz-class frequency ({0}) — the microstrip patch is the "
            "planar/low-profile family (transmission-line synthesis, "
            "openEMS-verifiable)".format(band_picker._fmt_freq(f0)))
    if (r["er"] or r["h_m"]) and not small:
        scores["patch"] += 25.0
        why["patch"].append(
            "substrate parameters (er/h) given — a planar patch design is "
            "intended (shipped patch synthesis)")

    # --- no room for a resonant dipole → printed IFA / PIFA ---------------
    # The discriminator is ROOM, not frequency alone: both families fold the
    # quarter-wave path so the FOOTPRINT is a fraction of it, which is exactly
    # what you reach for when a dipole will not fit. ⚠ `small` is deliberately
    # NOT required here (and must not be): the 900 MHz handset case trips the
    # no-full-size-element branch above and sets it, and that case is the
    # PIFA engine's own published cellular example.
    if r["max_dim_m"] and f0 >= HANDSET_MIN_F_HZ and r["max_dim_m"] < half:
        ifa_d = ifa.design_ifa(f0)
        pifa_d = pifa.design_pifa(f0)
        # Largest SINGLE element dimension, the convention max_dim_m is
        # compared against everywhere else here (quarter-wave for the wire,
        # boom span for the Yagi). max() rather than the radiator/plate alone
        # so a future taller stub or plate cannot slip past the fit check.
        ifa_span = max(ifa_d["radiator_length_m"], ifa_d["stub_height_m"])
        pifa_span = max(pifa_d["l1_m"], pifa_d["l2_m"], pifa_d["height_m"])

        scores["ifa"] += 55.0
        why["ifa"].append(
            "the {0:.3g} m envelope has no room for a resonant dipole "
            "({1:.3g} m) at {2} — a printed inverted-F folds the quarter-wave "
            "path ({3:.4g} mm) into the corner of the board as {4:.4g} x "
            "{5:.4g} mm of copper; shipped synthesis, openEMS-verifiable"
            .format(r["max_dim_m"], half, band_picker._fmt_freq(f0),
                    ifa_d["path_length_m"] * 1e3,
                    ifa_d["radiator_length_m"] * 1e3,
                    ifa_d["stub_height_m"] * 1e3))
        scores["pifa"] += 45.0
        why["pifa"].append(
            "the same folded quarter-wave as an elevated plate: {0:.4g} x "
            "{1:.4g} mm at {2:.4g} mm above ground — a smaller footprint than "
            "the printed IFA, bought with vertical room and a ~{3:.3g} mm "
            "ground plane that is PART of the antenna, not packaging".format(
                pifa_d["l1_m"] * 1e3, pifa_d["l2_m"] * 1e3,
                pifa_d["height_m"] * 1e3, pifa_d["ground_m"] * 1e3))

        if ifa_span > r["max_dim_m"]:
            scores["ifa"] -= 30.0
            why["ifa"].append(
                "the {0:.4g} mm radiator still does not fit the {1:.3g} m "
                "envelope — below this the element has to be LOADED "
                "(small-antenna family), not just folded".format(
                    ifa_span * 1e3, r["max_dim_m"]))
        else:
            scores["ifa"] += 10.0
            why["ifa"].append(
                "the {0:.4g} mm radiator fits the {1:.3g} m envelope".format(
                    ifa_span * 1e3, r["max_dim_m"]))
        if pifa_span > r["max_dim_m"]:
            scores["pifa"] -= 30.0
            why["pifa"].append(
                "the {0:.4g} mm plate does not fit the {1:.3g} m envelope — a "
                "shorter plate needs more height, and past that, loading "
                "(small-antenna family)".format(
                    pifa_span * 1e3, r["max_dim_m"]))
        else:
            scores["pifa"] += 10.0
            why["pifa"].append(
                "the {0:.4g} mm plate fits the {1:.3g} m envelope".format(
                    pifa_span * 1e3, r["max_dim_m"]))

        if r["gain_dbi"] is not None and r["gain_dbi"] > HANDSET_MAX_GAIN_DBI:
            # A folded, chassis-coupled element has no gain to give: refusing
            # here is what stops a 12 dBi request being answered with a 40 mm
            # handset antenna just because it fits the box.
            scores["ifa"] -= 30.0
            scores["pifa"] -= 30.0
            conflict = (
                "NOTE: {0:.3g} dBi is above anything a single IFA/PIFA "
                "delivers — the published table for the shipped PIFA geometry "
                "spans 1.2-5.0 dBi across every ground-plane size, and the "
                "chassis sets that, not the element".format(r["gain_dbi"]))
            why["ifa"].append(conflict)
            why["pifa"].append(conflict)

    # --- omni / single-frequency → the wire workhorse ---------------------
    scores["wire"] += 10.0
    why["wire"].append("general-purpose resonant wire element (E1 synthesis, "
                       "NEC2-verifiable today)")
    if (r["pattern"] in (None, "omni") and r["b_ratio"] <= 1.15 and not small
            and (r["gain_dbd"] is None or r["gain_dbd"] < 5.0)):
        scores["wire"] += 35.0
        if r["polarization"] == "V":
            why["wire"].append(
                "omni + vertical polarization + single frequency → a "
                "monopole/vertical (or a vertical dipole)")
        elif r["polarization"] == "H":
            why["wire"].append(
                "omni-ish + horizontal polarization + single frequency → a "
                "horizontal dipole (figure-8 in azimuth)")
        else:
            why["wire"].append(
                "single frequency with no high-gain/wide-band demand → a "
                "dipole/monopole is the simple, honest answer")

    if r["polarization"] == "CP":
        notes.append(
            "circular polarization: the CP families (crossed/patch-CP/helix) "
            "are post-MVP breadth (§1 phase C) — not recommended from this "
            "rule set yet")

    candidates = []
    for key, label, avail, ships in FAMILIES:
        if scores[key] <= 0.0:
            continue
        candidates.append({
            "family": key,
            "label": label,
            "score": scores[key],
            "available": avail,
            "ships_in": ships,
            "rationale": "; ".join(why[key]) if why[key] else "",
        })
    candidates.sort(key=lambda c: -c["score"])  # stable → FAMILIES order ties

    return {
        "req": r,
        "band": band_key,
        "band_name": band_name,
        "wavelength_m": lam,
        "candidates": candidates,
        "notes": notes,
        "chu_warning": chu_warning,
    }


def summary_text(rec):
    """One-block human-readable rendering of a recommend_element() result."""
    r = rec["req"]
    lines = [
        "ELEMENT RECOMMENDATION  ({0}, band {1})".format(
            band_picker._fmt_freq(r["f0_hz"]), rec["band"]),
    ]
    if r["f_lo_hz"] and r["f_hi_hz"]:
        lines.append("band {0} - {1} (ratio {2:.2f})".format(
            band_picker._fmt_freq(r["f_lo_hz"]),
            band_picker._fmt_freq(r["f_hi_hz"]), r["b_ratio"]))
    lines.append("")
    for i, c in enumerate(rec["candidates"], 1):
        tag = "" if c["available"] else "  [ships in slice {0}]".format(
            c["ships_in"])
        lines.append("{0}. {1}  (score {2:g}){3}".format(
            i, c["label"], c["score"], tag))
        if c["rationale"]:
            lines.append("     why: {0}".format(c["rationale"]))
    for n in rec["notes"]:
        lines.append("note: {0}".format(n))
    # the Chu warning is already shown inside the small-antenna candidate's
    # rationale (inserted at why[...][0]); only add the standalone footer when
    # that candidate is not in the ranked list, to avoid printing it twice.
    small_shown = any(c["family"] == "small_antenna" for c in rec["candidates"])
    if rec["chu_warning"] and not small_shown:
        lines.append("guardrail: {0}".format(rec["chu_warning"]))
    return "\n".join(lines)
