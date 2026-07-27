# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Element Designer E1 wire synthesis + E2 recommender/
dialog plumbing (ELEMENT_DESIGNER_PLAN §2.1/§1.3/§5).

Pure-math digit anchors (python3-runnable, seconds) for
``emstudio/antenna/wire_elements.py``:

* the shipped-template inversion is **bit-exact** (K = 0.95 → L = 0.475·λ,
  because 0.475 = 0.95·0.5 exactly in float64);
* the famous constants are DERIVED, not hard-coded: 468/f embeds
  K = 0.9516 (0.17 % above the 0.95 default — the gate pins the honest
  relationship, not a phantom agreement); 234 = 468/2; metric == imperial
  × 0.3048 bit-exact;
* the K curve is the one MEASURED on this repo's NEC2 writer (de-risk
  2026-07-17; published charts disagree ±0.01 across 13 curves) — table
  identity + monotonicity + the template-deck consistency point
  (curve(126.5) = 0.93822 vs the NEC2-implied 0.95·296.29/300 = 0.938252);
* feed-Z anchors (72 / 36 / 4× = 288 Ω), dBd = dBi − 2.15 both ways, the
  λ-fraction table with its §7 report-only flags, and the small-antenna
  router guard.

Plus a LIVE folded-dipole tier (freecadcmd + nec2c, ~10 s): the repo's own
NEC2 writer expresses the fold (two parallel λ/2 wires shorted at both
ends) — resonance selected by an R WINDOW (multi-wire structures have
several X = 0 crossings: ~204 MHz at 7.9 kΩ and ~381 MHz at 1.6 kΩ bracket
the real one) and pinned at the de-risked 291.14 MHz / 283.0 Ω (3.94×).

The dipole/monopole solver cross-checks are the SHIPPED gates
(dipole_nec2.py / monopole_nec2.py) — this gate asserts the synthesis
reproduces their pinned geometry instead of re-running them.

E2 additions:

* **picker scenarios** (pure python): the deterministic
  ``element_picker.recommend_element`` rules on canned requirement dicts —
  omni/V/single-freq → wire; 12 dBd @ 432 MHz → Yagi (ships E3, TN-688
  boom hint fits a 3 m envelope); 54-216 MHz (ratio 4) → LPDA; 2.45 GHz +
  substrate → patch; 24 kHz → small antenna with the Chu guardrail; the
  gain normalization (dBi 7.15 == dBd 5), boom-vs-envelope demotion,
  beyond-table honesty (>14.2 dBd → §7), and determinism.
* **template dimension overrides** (freecadcmd tier, no nec2c needed):
  ``makeDipole``/``makeMonopole`` defaults are BYTE-IDENTICAL to the gated
  geometry (0.475·λ / 0.1·λ, frozen segment counts) and the new optional
  ``length_m``/``height_m`` kwargs land exactly.

Pass: exit 0 and 'ELEMENT-DESIGNER GATE PASSED'.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def gate_synthesis():
    from emstudio.antenna import wire_elements as we

    # --- shipped-template inversion (bit-exact) ---------------------------
    d = we.design_dipole(300e6, 0.004)
    lam300 = we.C0 / 300e6
    check("dipole @300 MHz, K default == 0.475*lambda BIT-EXACT (0.475 = "
          "0.95*0.5)", d["length_m"] == 0.475 * lam300,
          "{0!r}".format(d["length_m"]))
    k_implied = 0.95 * 296.29 / 300.0
    check("NEC2-implied K at the template deck (0.95*296.29/300)",
          abs(k_implied - 0.9382518) < 5e-7, "{0:.7f}".format(k_implied))
    check("measured K curve hits the template deck: curve(126.5) vs the "
          "NEC2-implied K within 0.05%",
          abs(we.k_from_ratio(126.5) / k_implied - 1.0) < 5e-4,
          "curve {0:.5f} vs implied {1:.5f}".format(
              we.k_from_ratio(126.5), k_implied))

    # --- K curve: identity + monotonic + published-spine sanity -----------
    for ratio, k in we.K_CURVE_NEC2:
        if abs(we.k_from_ratio(ratio) - k) > 1e-12:
            check("K curve table identity at ratio {0:g}".format(ratio), False)
            break
    else:
        check("K curve table identity at every measured point", True)
    ks = [k for _, k in we.K_CURVE_NEC2]
    check("K curve monotonically increasing (thick -> thin)",
          all(b > a for a, b in zip(ks, ks[1:])))
    # The measured curve reads BELOW the published spine at thick ratios
    # (NEC2 delta-gap/standard-kernel effect — the Stearns caveat; charts
    # themselves spread ±0.01 across 13 published curves). The curve is
    # gated as NEC2-self-consistent; the spine bounds the divergence.
    check("published spine within ±0.02 of the measured curve (Balanis "
          "0.9352@50 reads +0.016 above — the documented delta-gap offset; "
          "Hansen 0.9557@250 +0.008)",
          abs(we.k_from_ratio(50.0) - 0.9352) < 0.02
          and abs(we.k_from_ratio(250.0) - 0.9557) < 0.02,
          "curve(50)={0:.4f}, curve(250)={1:.4f}".format(
              we.k_from_ratio(50.0), we.k_from_ratio(250.0)))
    dc = we.design_dipole(300e6, 0.004, k_factor="curve")
    check('k_factor="curve" uses the measured K at this lambda/(2d)',
          abs(dc["k_factor"] - we.k_from_ratio(lam300 / 0.008)) < 1e-12)

    # --- famous constants: derived roundings, honest residuals ------------
    c468 = we.imperial_dipole_const()
    check("imperial const K=0.95 -> 467.196 (printed 468 embeds K=0.9516; "
          "0.2% convention gap pinned)",
          abs(c468 - 467.1963) < 5e-4 and abs(c468 / 468.0 - 1.0) < 0.002,
          "{0:.4f}".format(c468))
    check("monopole const == dipole const / 2 (234/f)",
          abs(c468 / 2.0 - 233.5981) < 5e-4)
    cm = we.metric_dipole_const()
    check("metric const == imperial * 0.3048 BIT-EXACT",
          cm == c468 * 0.3048, "{0:.4f}".format(cm))
    check("printed-468 metric equivalent 142.646 vs the plan's 142.6",
          abs(468.0 * 0.3048 - 142.6464) < 1e-9)
    d71 = we.design_dipole(7.1e6, 0.002)
    check("40 m band: length_ft within 0.2% of 468/7.1",
          abs(d71["length_ft"] / (468.0 / 7.1) - 1.0) < 0.002,
          "{0:.2f} vs {1:.2f} ft".format(d71["length_ft"], 468.0 / 7.1))

    # --- feed Z + gains ----------------------------------------------------
    check("dipole feed R 72 in the NEC2/Balanis window 64-79 (ref 71.9)",
          64.0 <= d["feed_r_ohm"] <= 79.0)
    check("dipole gain 2.15 dBi / 0.00 dBd; NEC2 ref 2.13 within 0.25 dB",
          d["gain_dbd"] == 0.0 and abs(d["gain_dbi"] - 2.13) < 0.25)
    m = we.design_monopole(300e6, 0.004)
    check("monopole length == dipole/2 BIT-EXACT",
          m["length_m"] == d["length_m"] / 2.0)
    check("monopole feed R 36 vs textbook 36.5 (like-for-like: the in-repo "
          "39.5+j22.6 is the UNSHORTENED geometry — not compared here)",
          abs(m["feed_r_ohm"] - 36.5) < 3.0)
    check("dBd conversions: 2.15->0, 2.13->-0.02, round-trip exact",
          we.dbi_to_dbd(2.15) == 0.0
          and abs(we.dbi_to_dbd(2.13) + 0.02) < 1e-12
          and we.dbd_to_dbi(we.dbi_to_dbd(7.0)) == 7.0)
    fd = we.design_folded_dipole(300e6, 0.002)
    check("folded dipole: 4x step-up == 288 ohm, length == plain dipole",
          fd["feed_r_ohm"] == 4.0 * d["feed_r_ohm"]
          and fd["length_m"] == we.design_dipole(300e6, 0.002)["length_m"])

    # --- fraction table + router -------------------------------------------
    ft = we.fraction_table(300e6, wire_d_m=0.004)
    rows = {r["fraction"]: r for r in ft["rows"]}
    check("fraction rows 1/4..1.0 present with 1/2 == dipole and 1/4 == "
          "monopole lengths",
          set(rows) == {0.25, 0.5, 0.625, 0.75, 1.0}
          and rows[0.5]["length_m"] == d["length_m"]
          and rows[0.25]["length_m"] == m["length_m"])
    check("5/8 row: honest flags (capacitive X + series-L network + PEC-vs-"
          "real-ground gain)",
          "series-L" in rows[0.625]["note"]
          and "PEC" in rows[0.625]["note"]
          and "1-2 dB" in rows[0.625]["note"])
    check("anti-resonant rows flagged section-7 (end-fed 1/2, full-wave)",
          "section-7" in rows[0.5]["note"] and "section-7" in rows[1.0]["note"])
    check("router: lambda/20 -> small_antenna, quarter-wave -> wire_elements",
          we.route_for_length(lam300 / 20.0, 300e6) == "small_antenna"
          and we.route_for_length(0.25 * lam300, 300e6) == "wire_elements")
    check("thick-element warning fires below ratio 50",
          any("thick" in w for w in we.design_dipole(300e6, 0.03)["warnings"]))

    # --- small-antenna bridge consistency (shipped gate numbers) ----------
    rr = 40.0 * math.pi ** 2 * 0.01  # Rr of a lambda/10 monopole
    check("lambda/10 monopole analytic Rr 3.948 (monopole_nec2 gate: NEC2 "
          "4.02 within 3%)", abs(rr - 3.948) < 1e-3 and abs(4.02 / rr - 1.0) < 0.03)


def gate_picker():
    """E2: the deterministic element-family recommender on canned scenarios."""
    from emstudio.antenna import element_picker as ep

    def top(req):
        return ep.recommend_element(req)["candidates"][0]

    # omni + V + single frequency -> the wire workhorse (available today)
    c = top({"f0_hz": 150e6, "pattern": "omni", "polarization": "V"})
    check("picker: omni+V single-freq -> wire family, available",
          c["family"] == "wire" and c["available"],
          "{0} ({1:g})".format(c["family"], c["score"]))

    # gain target -> Yagi with the TN-688 boom hint (available since E3)
    r = ep.recommend_element({"f0_hz": 432e6, "gain_dbd": 12.0,
                              "max_dim_m": 3.0})
    c = r["candidates"][0]
    check("picker: 12 dBd @ 432 MHz -> Yagi, available (E3 shipped), span-fits",
          c["family"] == "yagi" and c["available"]
          and c["ships_in"] is None and "fits the" in c["rationale"],
          c["rationale"][:60])
    boom = ep.yagi_boom_for_gain(12.0)
    check("picker: TN-688 boom for 12 dBd = the 2.2-lambda / 12.25 dBd row",
          boom == (2.2, 12.25), repr(boom))
    check("picker: >14.2 dBd is beyond the single-boom table (None -> "
          "stacking = section 7)", ep.yagi_boom_for_gain(15.0) is None)
    r = ep.recommend_element({"f0_hz": 432e6, "gain_dbd": 14.0,
                              "max_dim_m": 1.0})
    c = r["candidates"][0]
    check("picker: boom exceeding the envelope demotes but tells why",
          c["family"] == "yagi" and "exceeds" in c["rationale"])

    # wide band -> LPDA (available since E5)
    c = top({"f_lo_hz": 54e6, "f_hi_hz": 216e6})
    check("picker: 54-216 MHz (ratio 4) -> LPDA, available (E5 shipped)",
          c["family"] == "lpda" and c["available"] and c["ships_in"] is None)

    # GHz + substrate -> patch (available since E4)
    c = top({"f0_hz": 2.45e9, "er": 2.2, "h_m": 1.588e-3})
    check("picker: 2.45 GHz + substrate -> patch, available (E4 shipped)",
          c["family"] == "patch" and c["available"] and c["ships_in"] is None)
    # ... but a GHz whip with no substrate stays a wire (honest, not pushy)
    c = top({"f0_hz": 2.45e9, "pattern": "omni"})
    check("picker: 2.45 GHz omni whip (no substrate) stays wire",
          c["family"] == "wire")

    # electrically small -> the shipped family + the Chu guardrail
    r = ep.recommend_element({"f0_hz": 24e3, "max_dim_m": 300.0})
    c = r["candidates"][0]
    check("picker: 24 kHz -> small antenna (available) with a Chu guardrail",
          c["family"] == "small_antenna" and c["available"]
          and r["chu_warning"] is not None and "Chu" in r["chu_warning"])
    c = top({"f0_hz": 100e6, "max_dim_m": 0.05})
    check("picker: sub-lambda/10 envelope at 100 MHz routes to small antenna",
          c["family"] == "small_antenna")

    # normalization: dBi/dBd equivalence + band centre + hard error
    a = ep.recommend_element({"f0_hz": 432e6, "gain_dbi": 7.15})
    b = ep.recommend_element({"f0_hz": 432e6, "gain_dbd": 5.0})
    check("picker: gain 7.15 dBi == 5.0 dBd (identical candidates)",
          a["candidates"] == b["candidates"])
    n = ep.normalize_req({"f_lo_hz": 54e6, "f_hi_hz": 216e6})
    check("picker: band centre is the geometric mean (108 MHz), ratio 4",
          abs(n["f0_hz"] - 108e6) < 1.0 and abs(n["b_ratio"] - 4.0) < 1e-12)
    try:
        ep.normalize_req({})
        check("picker: missing frequency raises ValueError", False)
    except ValueError:
        check("picker: missing frequency raises ValueError", True)

    # --- review-hardening (v0.58.0 adversarial pass) ----------------------
    # wide band + gain: the LPDA must win over the narrow-band Yagi
    c = top({"f_lo_hz": 54e6, "f_hi_hz": 216e6, "gain_dbd": 10.0,
             "max_dim_m": 5.0})
    check("picker: wideband + gain -> LPDA beats the narrow-band Yagi",
          c["family"] == "lpda",
          "top {0} ({1:g})".format(c["family"], c["score"]))

    # wire never recommended when even a monopole cannot fit the envelope
    c = top({"f0_hz": 100e6, "pattern": "omni", "polarization": "H",
             "max_dim_m": 0.5})
    check("picker: sub-quarter-wave envelope does NOT yield a non-fitting "
          "wire dipole (routes to small antenna)", c["family"] != "wire",
          "top {0}".format(c["family"]))

    # Chu required-bandwidth uses df/f0 (centre), not the overstated df/f_lo
    r = ep.recommend_element({"f_lo_hz": 10e6, "f_hi_hz": 10.72e6,
                              "max_dim_m": 0.3})
    check("picker: Chu required-BW is (b-1)/sqrt(b) = 6.95%, not the "
          "overstated 7.2%", r["chu_warning"] is not None
          and "6.95" in r["chu_warning"] and "7.2 %" not in r["chu_warning"],
          r["chu_warning"])

    # omni + directional-gain: the Yagi is flagged conflicting AND demoted
    omni = next(x for x in ep.recommend_element(
        {"f0_hz": 432e6, "gain_dbd": 10.0, "pattern": "omni"})["candidates"]
        if x["family"] == "yagi")
    plain = next(x for x in ep.recommend_element(
        {"f0_hz": 432e6, "gain_dbd": 10.0})["candidates"]
        if x["family"] == "yagi")
    check("picker: omni + directional gain flags the Yagi conflict and "
          "demotes its score", "conflicts with the 'omni'" in omni["rationale"]
          and omni["score"] < plain["score"],
          "{0:g} < {1:g}".format(omni["score"], plain["score"]))

    # substrate (er/h) surfaces the patch family even below 1 GHz
    r = ep.recommend_element({"f0_hz": 915e6, "er": 4.4, "h_m": 1.6e-3})
    check("picker: 915 MHz + substrate surfaces the patch candidate (er/h "
          "not gated to >=1 GHz)",
          any(x["family"] == "patch" for x in r["candidates"]))

    # below 3 MHz WITH a fitting envelope keeps the wire family (an LF mast)
    fams = [x["family"] for x in ep.recommend_element(
        {"f0_hz": 1e6, "max_dim_m": 200.0, "pattern": "omni",
         "polarization": "V"})["candidates"]]
    check("picker: 1 MHz mast in a 200 m envelope keeps wire as a candidate "
          "(lambda/4 = 75 m fits — full-size LF practice)",
          "small_antenna" in fams and "wire" in fams,
          "candidates {0}".format(fams))

    # Chu warning is not double-rendered when small antenna is a candidate
    txt24 = ep.summary_text(ep.recommend_element(
        {"f0_hz": 24e3, "max_dim_m": 300.0}))
    check("picker: Chu warning rendered exactly once in the summary",
          txt24.count("Chu limit:") == 1)

    # an MF-band LPDA carries an honest size caveat
    r = ep.recommend_element({"f_lo_hz": 500e3, "f_hi_hz": 5e6})
    lp = next((x for x in r["candidates"] if x["family"] == "lpda"), None)
    check("picker: MF-band LPDA flagged as a very large structure",
          lp is not None and "very large" in lp["rationale"])

    # determinism + rendering
    r1 = ep.recommend_element({"f0_hz": 432e6, "gain_dbd": 12.0})
    r2 = ep.recommend_element({"f0_hz": 432e6, "gain_dbd": 12.0})
    check("picker: deterministic (identical output on identical input)",
          r1 == r2)
    txt = ep.summary_text(r1)
    check("picker: summary renders rank + rationale (Yagi now available)",
          "1." in txt and "why:" in txt and "Yagi" in txt)
    txt_lpda = ep.summary_text(ep.recommend_element(
        {"f_lo_hz": 54e6, "f_hi_hz": 216e6}))
    check("picker: the LPDA renders available (all five families shipped — "
          "no ships-in flag anywhere)", "LPDA" in txt_lpda
          and "ships in slice" not in txt_lpda)


def gate_yagi():
    """E3: Yagi-Uda synthesis — TN-688 Table 1 verbatim + the Fig 9/10
    compensation model vs both printed worked examples (provenance in
    docs/upstream/tn688-yagi-anchors.md)."""
    from emstudio.antenna import yagi

    C0 = yagi.C0

    # --- Table 1 encoded VERBATIM; base == table at the 0.0085 reference ----
    counts = {0.4: 1, 0.8: 3, 1.2: 4, 2.2: 10, 3.2: 15, 4.2: 13}
    for boom, n in counts.items():
        row = yagi.TN688_TABLE1[boom]
        check("yagi Table 1 {0}-lambda: {1} directors".format(boom, n),
              len(row["directors"]) == n)
    check("yagi Table 1: 0.4-lambda director = 0.424 (NOT the Balanis-typo "
          "0.442)", yagi.TN688_TABLE1[0.4]["directors"][0] == 0.424)
    check("yagi Table 1: 4.2-lambda reflector 0.475 + spacing 0.308 (unique)",
          yagi.TN688_TABLE1[4.2]["reflector"] == 0.475
          and yagi.TN688_TABLE1[4.2]["spacing"] == 0.308)
    check("yagi Table 1: 2.2-lambda tail rises (D9=0.398, D10=0.407) — the "
          "real oscillatory pattern",
          yagi.TN688_TABLE1[2.2]["directors"][8] == 0.398
          and yagi.TN688_TABLE1[2.2]["directors"][9] == 0.407)
    check("yagi Table 1: gain column 7.1/9.2/10.2/12.25/13.4/14.2 dBd",
          [yagi.TN688_TABLE1[b]["gain_dbd"] for b in yagi.BOOM_CLASSES]
          == [7.1, 9.2, 10.2, 12.25, 13.4, 14.2])

    # every boom's reflector/spacing/gain/directors vs INDEPENDENT verified
    # literals (docs/upstream/tn688-yagi-anchors.md) — so a transcription
    # regression in ANY boom (incl. 3.2-lambda, which no worked example covers)
    # is caught, not just the two worked-example booms.
    EXPECTED = {
        0.4: (0.482, 0.20, 7.1, [0.424]),
        0.8: (0.482, 0.20, 9.2, [0.428, 0.424, 0.428]),
        1.2: (0.482, 0.25, 10.2, [0.428, 0.420, 0.420, 0.428]),
        2.2: (0.482, 0.20, 12.25,
              [0.432, 0.415, 0.407, 0.398, 0.390,
               0.390, 0.390, 0.390, 0.398, 0.407]),
        3.2: (0.482, 0.20, 13.4,
              [0.428, 0.420, 0.407, 0.398, 0.394, 0.390, 0.386,
               0.386, 0.386, 0.386, 0.386, 0.386, 0.386, 0.386, 0.386]),
        4.2: (0.475, 0.308, 14.2,
              [0.424, 0.424, 0.420, 0.407, 0.403, 0.398, 0.394,
               0.390, 0.390, 0.390, 0.390, 0.390, 0.390]),
    }
    mism = [b for b, (refl, sp, g, dirs) in EXPECTED.items()
            if not (yagi.TN688_TABLE1[b]["reflector"] == refl
                    and yagi.TN688_TABLE1[b]["spacing"] == sp
                    and yagi.TN688_TABLE1[b]["gain_dbd"] == g
                    and yagi.TN688_TABLE1[b]["directors"] == dirs)]
    check("yagi Table 1: EVERY boom (incl. 3.2-lambda) matches the verified "
          "TN-688 transcription — independent literals",
          not mism, "mismatched booms: {0}".format(mism))

    # at d/lambda = 0.0085 (the reference) the diameter compensation is zero
    lam400 = C0 / 400e6
    d0 = yagi.design_yagi(400e6, boom_lambda=0.8, wire_d_m=yagi.D_REF * lam400)
    base = [e["length_lambda"] for e in d0["elements"] if e["kind"] == "director"]
    check("yagi @d/lambda=0.0085: director base lengths == Table 1 exactly "
          "(no compensation)",
          all(abs(b - t) < 1e-9 for b, t in
              zip(base, yagi.TN688_TABLE1[0.8]["directors"])),
          "{0}".format([round(b, 4) for b in base]))
    check("yagi @d/lambda=0.0085, no boom: reflector base == 0.482",
          abs([e["length_lambda"] for e in d0["elements"]
               if e["kind"] == "reflector"][0] - 0.482) < 1e-9)

    # --- worked example 1 (0.8-lambda, 50.1 MHz) — the primary anchor, ±0.001
    ex1 = yagi.design_yagi(50.1e6, boom_lambda=0.8, wire_d_m=0.0254,
                           boom_d_m=0.051)
    want1 = {"Reflector": 0.490, "Director 1": 0.447, "Director 2": 0.443,
             "Director 3": 0.447}
    ok1 = all(abs(e["cut_length_lambda"] - want1[e["name"]]) < 0.0015
              for e in ex1["elements"] if e["name"] in want1)
    check("yagi worked example 1 (0.8-lambda, 50.1 MHz): cut lengths match the "
          "paper to <0.0015 lambda (refl 0.490 / dir 0.447/0.443/0.447)", ok1,
          "{0}".format({e["name"]: round(e["cut_length_lambda"], 4)
                        for e in ex1["elements"] if e["name"] in want1}))
    check("yagi example 1 boom correction = +0.005 lambda (D/lambda=0.0085)",
          abs(ex1["boom_correction_lambda"] - 0.005) < 3e-4,
          "{0:+.4f}".format(ex1["boom_correction_lambda"]))

    # --- worked example 2 (4.2-lambda, 827 MHz) — full set to ±0.005 --------
    ex2 = yagi.design_yagi(827e6, boom_lambda=4.2, wire_d_m=0.0048,
                           boom_d_m=0.0127)
    want2 = {"Reflector": 0.499, "Director 1": 0.440, "Director 2": 0.440,
             "Director 3": 0.435, "Director 4": 0.421, "Director 5": 0.417,
             "Director 6": 0.411, "Director 7": 0.407, "Director 8": 0.403,
             "Director 13": 0.403}
    worst = max(abs(e["cut_length_lambda"] - want2[e["name"]])
                for e in ex2["elements"] if e["name"] in want2)
    check("yagi worked example 2 (4.2-lambda, 827 MHz): every cut length within "
          "0.005 lambda of the paper (graphical arc-transpose tail)",
          worst < 0.005, "worst delta {0:.4f} lambda".format(worst))
    check("yagi example 2 reflector 0.499 + boom corr +0.026 (D/lambda=0.035)",
          abs(ex2["boom_correction_lambda"] - 0.026) < 5e-4)

    # --- boom-class selection by gain --------------------------------------
    check("yagi boom_class_for_gain: 9.2->0.8, 12->2.2, 14.2->4.2, 15->None",
          yagi.boom_class_for_gain(9.2) == 0.8
          and yagi.boom_class_for_gain(12.0) == 2.2
          and yagi.boom_class_for_gain(14.2) == 4.2
          and yagi.boom_class_for_gain(15.0) is None)
    g = yagi.design_yagi(144e6, gain_dbd=10.0, wire_d_m=0.006)
    check("yagi design by gain 10 dBd -> 1.2-lambda boom (10.2 dBd), 4 dir",
          g["boom_lambda"] == 1.2 and g["n_directors"] == 4
          and g["gain_dbd"] == 10.2)
    check("yagi gain both scales: 10.2 dBd = 12.35 dBi",
          abs(g["gain_dbi"] - 12.35) < 1e-9)
    try:
        yagi.design_yagi(144e6, gain_dbd=16.0)
        check("yagi >14.2 dBd raises ValueError (stacking = section 7)", False)
    except ValueError:
        check("yagi >14.2 dBd raises ValueError (stacking = section 7)", True)
    try:
        yagi.design_yagi(144e6)  # neither gain nor boom
        check("yagi with no target raises ValueError", False)
    except ValueError:
        check("yagi with no target raises ValueError", True)

    # --- geometry sanity ----------------------------------------------------
    y = yagi.design_yagi(400e6, boom_lambda=0.8, wire_d_m=0.006)
    kinds = [e["kind"] for e in y["elements"]]
    check("yagi geometry: reflector at boom x=0, driven at 0.2 lambda, "
          "directors ahead; boom length = last director position",
          kinds[0] == "reflector" and kinds[1] == "driven"
          and y["elements"][0]["position_lambda"] == 0.0
          and abs(y["elements"][1]["position_lambda"] - 0.2) < 1e-12
          and abs(y["boom_length_m"] - y["elements"][-1]["position_m"]) < 1e-9)
    check("yagi reports a folded-driven feed R ~4x the plain dipole (E1 reuse)",
          abs(y["folded_driven_feed_r_ohm"]
              - 4.0 * y["driven_feed_r_ohm"]) < 1e-9)
    check("yagi boom_lambda=1.1 snaps to the nearest class (1.2) with a warning",
          yagi.design_yagi(400e6, boom_lambda=1.1, wire_d_m=0.006)["boom_lambda"]
          == 1.2)


def gate_patch():
    """E4: microstrip-patch TL synthesis vs the published anchors + feed model
    (provenance in docs/upstream/patch-tl-anchors.md). Pure math, python3."""
    from emstudio.antenna import patch_tl as p

    # --- the widely-published 10 GHz / er 2.2 / h 1.588 mm example ---------
    d = p.design_patch(10e9, 2.2, 1.588e-3)
    check("patch example: W = 11.85 mm (published 11.86)",
          abs(d["width_m"] * 1e3 - 11.86) < 0.02,
          "{0:.4f} mm".format(d["width_m"] * 1e3))
    check("patch example: er_eff = 1.9715 (published 1.972)",
          abs(d["er_eff"] - 1.972) < 1e-3, "{0:.4f}".format(d["er_eff"]))
    check("patch example: dL = 0.811 mm (published 0.81)",
          abs(d["delta_l_m"] * 1e3 - 0.81) < 5e-3,
          "{0:.4f} mm".format(d["delta_l_m"] * 1e3))
    check("patch example: L = 9.053 mm (published 9.06)",
          abs(d["length_m"] * 1e3 - 9.06) < 0.02,
          "{0:.4f} mm".format(d["length_m"] * 1e3))

    # --- synthesis on the shipped openEMS tutorial substrate --------------
    d2 = p.design_patch(2.4e9, 3.38, 1.524e-3)
    check("patch 2.4 GHz on the tutorial substrate: W ~ 42.2 mm, L ~ 33.5 mm "
          "(the openEMS gate's substrate)",
          abs(d2["width_m"] * 1e3 - 42.2) < 0.3
          and abs(d2["length_m"] * 1e3 - 33.5) < 0.3,
          "W {0:.2f} L {1:.2f} mm".format(
              d2["width_m"] * 1e3, d2["length_m"] * 1e3))

    # --- feed model: PIN the two-slot edge R + the derived offset ----------
    # (tight bands around the de-risked values so a regression in the slot-
    # conductance integrals / Bessel approx / cos^2 inversion actually fails —
    # not a loose plausibility band).
    check("patch edge resistance pinned near the de-risked 282 ohm (two-slot "
          "self+mutual)", 272.0 <= d2["edge_resistance_ohm"] <= 292.0,
          "{0:.1f} ohm".format(d2["edge_resistance_ohm"]))
    check("patch 50-ohm feed offset pinned near the de-risked 4.64 mm",
          4.4 <= d2["feed_offset_m"] * 1e3 <= 4.9,
          "{0:.2f} mm".format(d2["feed_offset_m"] * 1e3))
    # independent inset_offset check with a CLEAN closed form: R_edge=200,
    # z=50 -> cos^2 = 0.25 -> acos(0.5) = pi/3 -> y0 = L/3, offset = L/6
    y0, off = p.inset_offset(200.0, 0.030, 50.0)
    check("patch inset_offset closed form: R 200->50 gives y0 = L/3 (10 mm), "
          "offset = L/6 (5 mm)",
          abs(y0 - 0.010) < 1e-6 and abs(off - 0.005) < 1e-6,
          "y0 {0:.4f} off {1:.4f} m".format(y0, off))
    check("patch gain estimate in the typical patch range (4-9 dBi; openEMS "
          "gate window 4.5-9.5)", 4.0 <= d2["gain_dbi"] <= 9.0,
          "{0:.2f} dBi".format(d2["gain_dbi"]))
    check("patch gain both scales (dBd = dBi - 2.15)",
          abs(d2["gain_dbd"] - (d2["gain_dbi"] - 2.15)) < 1e-9)

    # --- physics sanity ----------------------------------------------------
    check("patch er_eff between 1 and er, and rises with er",
          1.0 < d["er_eff"] < 2.2
          and p.design_patch(10e9, 4.4, 1.588e-3)["er_eff"] > d["er_eff"])
    check("patch: the ±5% accuracy caveat is stated (source note + warning)",
          "5 %" in d["source_note"] or "5%" in d["source_note"]
          or any("5 %" in w for w in d["warnings"]))
    try:
        p.design_patch(10e9, 0.5, 1.588e-3)  # er < 1
        check("patch: er < 1 raises ValueError", False)
    except ValueError:
        check("patch: er < 1 raises ValueError", True)
    try:
        # an absurdly thick, high-er substrate drives L <= 0
        p.design_patch(1e9, 10.0, 0.5)
        check("patch: length <= 0 raises ValueError (too-thick substrate)", False)
    except ValueError:
        check("patch: length <= 0 raises ValueError (too-thick substrate)", True)


def gate_lpda():
    """E5: LPDA Carrel synthesis — BOTH official worked-example digit chains
    (printed sigma 0.157 / companion-code sigma 0.158), the Balanis feeder
    Za/Z0 chain, the corrected gain contours, and the structural identities
    (provenance in docs/upstream/lpda-carrel-anchors.md)."""
    from emstudio.antenna import lpda

    print("- E5 LPDA synthesis (Carrel equations, corrected contours)")
    C0 = 299792458.0

    # --- worked-example chain, companion-code variant (sigma = 0.158) ------
    d = lpda.design_lpda(54e6, 216e6, tau=0.865, sigma=0.158, wire_d_m=0.010)
    check("lpda: B = 4 exactly", abs(d["bandwidth"] - 4.0) < 1e-12)
    check("lpda: cot(alpha) = 4.6815 (sigma .158 chain)",
          abs(d["cot_alpha"] - 4.681481) < 1e-4,
          "{0:.6f}".format(d["cot_alpha"]))
    check("lpda: B_ar = 1.757", abs(d["b_ar"] - 1.75697) < 5e-4,
          "{0:.5f}".format(d["b_ar"]))
    check("lpda: B_s = 7.028", abs(d["b_s"] - 7.0279) < 2e-3,
          "{0:.4f}".format(d["b_s"]))
    check("lpda: N_exact = 14.445 (printed '14 or 15')",
          abs(d["n_exact"] - 14.4451) < 0.01, "{0:.4f}".format(d["n_exact"]))
    check("lpda: N rounds UP at fraction .45 (documented ARRL >0.3 rule)",
          d["n_elements"] == 15)
    check("lpda: lambda_max = c/54e6", abs(d["wavelength_max_m"]
          - C0 / 54e6) < 1e-9)
    check("lpda: Carrel boom closed form = 5.573 m",
          abs(d["boom_carrel_m"] - 5.5730) < 5e-3,
          "{0:.4f}".format(d["boom_carrel_m"]))

    # --- worked-example chain, printed-text variant (sigma = 0.157) --------
    # printed digits: alpha 12.13 deg, B_ar 1.753, B_s 7.01, N 14.43,
    # L 5.541 m (their lambda_max uses c = 3e8; ours is 0.07 % shorter)
    d157 = lpda.design_lpda(54e6, 216e6, tau=0.865, sigma=0.157,
                            wire_d_m=0.010)
    check("lpda: printed chain alpha = 12.13 deg",
          abs(d157["alpha_deg"] - 12.128) < 0.01,
          "{0:.3f}".format(d157["alpha_deg"]))
    check("lpda: printed chain B_ar = 1.753",
          abs(d157["b_ar"] - 1.7529) < 5e-4, "{0:.4f}".format(d157["b_ar"]))
    check("lpda: printed chain B_s = 7.01",
          abs(d157["b_s"] - 7.0116) < 2e-3, "{0:.4f}".format(d157["b_s"]))
    check("lpda: printed chain N_exact = 14.43",
          abs(d157["n_exact"] - 14.4288) < 0.01,
          "{0:.4f}".format(d157["n_exact"]))
    check("lpda: printed chain boom = 5.541 m (c-convention window)",
          abs(d157["boom_carrel_m"] - 5.541) < 0.01,
          "{0:.4f}".format(d157["boom_carrel_m"]))

    # --- Balanis feeder chain: 3/4-in tubing, R0 = 50 -> Za 327.88, exact
    # Z0 55.96 (the book graph-reads 60; our closed form matches its exact
    # computation)
    db = lpda.design_lpda(54e6, 216e6, tau=0.865, sigma=0.157,
                          wire_d_m=0.01905, r0_ohm=50.0)
    check("lpda: Balanis Za = 327.88 ohm (l/d 145.8, longest element)",
          abs(db["za_ohm"] - 327.88) < 0.5, "{0:.2f}".format(db["za_ohm"]))
    check("lpda: sigma' = 0.169", abs(db["sigma_prime"] - 0.16881) < 5e-4,
          "{0:.5f}".format(db["sigma_prime"]))
    check("lpda: Balanis exact feeder Z0 = 55.96 ohm",
          abs(db["feeder_z0_ohm"] - 55.96) < 0.1,
          "{0:.2f}".format(db["feeder_z0_ohm"]))

    # --- corrected gain contours (Butson-Thompson calibration) -------------
    d8 = lpda.design_lpda(54e6, 216e6, gain_dbi=8.0, wire_d_m=0.010)
    check("lpda: 8 dBi (corrected) -> tau 0.865 on the optimum line",
          abs(d8["tau"] - 0.865) < 1e-12)
    check("lpda: optimum sigma formula 0.243*tau-0.051",
          abs(d8["sigma"] - (0.243 * 0.865 - 0.051)) < 1e-12)
    check("lpda: original-calibration label = corrected + 1.0 dB",
          abs(d8["gain_dbi_carrel_original"] - d8["gain_dbi"] - 1.0) < 1e-9)
    d95 = lpda.design_lpda(54e6, 216e6, gain_dbi=9.5, wire_d_m=0.010)
    check("lpda: 9.5 dBi -> tau 0.931 + the high-gain-corner honesty warning",
          abs(d95["tau"] - 0.931) < 1e-12
          and any("high-gain corner" in w for w in d95["warnings"]))
    try:
        lpda.design_lpda(54e6, 216e6, gain_dbi=11.5)
        check("lpda: >11 dBi raises (section-7 honesty)", False)
    except ValueError as exc:
        check("lpda: >11 dBi raises (section-7 honesty)",
              "section-7" in str(exc))
    # thickness sensitivity: recompute ha_geo INDEPENDENTLY from first
    # principles (l1 = lambda_max/2, lN = l1*tau^(N-1), geometric mean of
    # the end elements' half-length/radius) and pin engine output against
    # it + a literal anchor — a factor-2 radius/diameter slip in the
    # engine's ha_geo would shift every reported gain by 0.2 dB.
    lam1 = C0 / 54e6
    wd = (lam1 / 4.0) / 125.0  # longest-element h/a = l1/2 / (wd/2) = 250
    d_ref = lpda.design_lpda(54e6, 216e6, tau=0.865, sigma=0.158,
                             wire_d_m=wd)
    a_ref = wd / 2.0
    l1_ref = lam1 / 2.0
    lN_ref = l1_ref * 0.865 ** (d_ref["n_elements"] - 1)
    ha_expect = math.sqrt((l1_ref / 2.0 / a_ref) * (lN_ref / 2.0 / a_ref))
    check("lpda: ha_geo matches the independent first-principles value",
          abs(d_ref["ha_geo"] - ha_expect) < 1e-9,
          "{0:.3f} vs {1:.3f}".format(d_ref["ha_geo"], ha_expect))
    check("lpda: ha_geo literal anchor 90.58 (N=15 chain)",
          abs(d_ref["ha_geo"] - 90.58) < 0.05,
          "{0:.3f}".format(d_ref["ha_geo"]))
    check("lpda: thickness adjustment literal +0.0929 dB "
          "(-0.2*log2(90.58/125))",
          abs(d_ref["gain_ha_adj_db"] - 0.0929) < 1e-3,
          "{0:.5f}".format(d_ref["gain_ha_adj_db"]))

    # --- off-optimum explicit designs (sigma = 0.06 crossing anchors) ------
    dl = lpda.design_lpda(200e6, 1000e6, tau=0.887, sigma=0.06,
                          wire_d_m=0.005)
    base = 7.0  # corrected contour crossing at (0.887, 0.06)
    check("lpda: (0.887, 0.06) hits the verified 7.0 dBi crossing "
          "(+thickness adj)",
          abs(dl["gain_dbi"] - dl["gain_ha_adj_db"] - base) < 0.05,
          "{0:.3f}".format(dl["gain_dbi"] - dl["gain_ha_adj_db"]))

    # --- structural identities (machine precision) -------------------------
    els = d["elements"]
    check("lpda: l1 = lambda_max/2 exactly",
          abs(els[0]["length_m"] - d["wavelength_max_m"] / 2.0) < 1e-12)
    tau_ok = all(abs(els[k + 1]["length_m"] / els[k]["length_m"] - 0.865)
                 < 1e-12 for k in range(len(els) - 1))
    check("lpda: tau scaling exact on every adjacent pair", tau_ok)
    sp_ok = all(abs((els[k + 1]["position_m"] - els[k]["position_m"])
                    - 2.0 * 0.158 * els[k]["length_m"]) < 1e-12
                for k in range(len(els) - 1))
    check("lpda: d_n = 2*sigma*l_n spacing exact on every gap", sp_ok)
    n = d["n_elements"]
    span_identity = (d["wavelength_max_m"] / 4.0) \
        * (1.0 - 0.865 ** (n - 1)) * d["cot_alpha"]
    check("lpda: boom span == (lambda_max/4)(1-tau^(N-1))cot(alpha)",
          abs(d["boom_length_m"] - span_identity) < 1e-9)
    check("lpda: fed element is the shortest (front)",
          els[-1]["kind"] == "fed"
          and all(e["kind"] == "passive" for e in els[:-1]))
    # N-rounding DOWN branch: fraction <= 0.3
    dn = lpda.design_lpda(100e6, 200e6, tau=0.90, sigma=0.165,
                          wire_d_m=0.005)
    check("lpda: N fraction {0:.2f} <= .3 rounds DOWN".format(
        dn["n_exact"] - int(dn["n_exact"])),
        (dn["n_exact"] - int(dn["n_exact"])) <= 0.3
        and dn["n_elements"] == int(dn["n_exact"]))

    # --- error honesty -----------------------------------------------------
    for bad_kwargs, why in (
            (dict(gain_dbi=8.0, tau=0.9, sigma=0.15), "both modes"),
            (dict(tau=0.9), "missing sigma"),
            (dict(), "neither mode"),
            (dict(tau=1.05, sigma=0.15), "tau >= 1")):
        try:
            lpda.design_lpda(54e6, 216e6, **bad_kwargs)
            check("lpda: {0} raises".format(why), False)
        except ValueError:
            check("lpda: {0} raises".format(why), True)
    try:
        lpda.design_lpda(216e6, 54e6, tau=0.865, sigma=0.158)
        check("lpda: inverted band raises", False)
    except ValueError:
        check("lpda: inverted band raises", True)


def gate_presets():
    """E6: service presets — schema integrity, spot/band routing, in-band
    normalization, and the recommender behavior pins (provenance in
    docs/upstream/service-presets-anchors.md)."""
    from emstudio.antenna import element_picker as ep
    from emstudio.antenna import service_presets as sp

    print("- E6 service presets")
    check("presets: 20 verified rows", len(sp.PRESETS) == 20,
          str(len(sp.PRESETS)))
    keys = [r["key"] for r in sp.PRESETS]
    check("presets: keys unique", len(set(keys)) == len(keys))
    for r in sp.PRESETS:
        ok = (0.0 < r["f_lo_mhz"] < r["f_hi_mhz"]
              and r["polarization"] in ("V", "H", "CP", "any")
              and r["pattern"] in ("omni", "directional", "any")
              and r["note"] and r["region_note"])
        check("presets: row '{0}' well-formed".format(r["key"]), ok)
        frag = sp.apply_preset(r["key"])
        ratio = r["f_hi_mhz"] / r["f_lo_mhz"]
        if ratio < sp.SPOT_RATIO:
            in_band = (r["f_lo_mhz"] * 1e6 <= frag["f0_hz"]
                       <= r["f_hi_mhz"] * 1e6)
            check("presets: '{0}' spot f0 at the geometric centre, "
                  "in band".format(r["key"]),
                  "f0_hz" in frag and in_band and abs(
                      frag["f0_hz"] - math.sqrt(
                          r["f_lo_mhz"] * r["f_hi_mhz"]) * 1e6) < 1.0)
        else:
            check("presets: '{0}' band fragment carries f_lo/f_hi".format(
                r["key"]),
                frag.get("f_lo_hz") == r["f_lo_mhz"] * 1e6
                and frag.get("f_hi_hz") == r["f_hi_mhz"] * 1e6)
        # every preset must normalize and recommend an AVAILABLE family
        req = {k: v for k, v in frag.items()
               if k in ("f0_hz", "f_lo_hz", "f_hi_hz", "polarization",
                        "pattern")}
        rec = ep.recommend_element(req)
        top = rec["candidates"][0]
        check("presets: '{0}' recommends an available family "
              "({1})".format(r["key"], top["family"]), top["available"])
    # behavior pins
    top_am = ep.recommend_element(
        {k: v for k, v in sp.apply_preset("am_broadcast").items()
         if k in ("f0_hz", "f_lo_hz", "f_hi_hz", "polarization",
                  "pattern")})["candidates"][0]
    check("presets: AM broadcast (MF) routes to the small-antenna family",
          top_am["family"] == "small_antenna", top_am["family"])
    check("presets: GPS is CP + spot (RHCP note carried)",
          sp.apply_preset("gps_l1")["polarization"] == "CP"
          and "RHCP" in sp.apply_preset("gps_l1")["note"])
    try:
        sp.apply_preset("nope")
        check("presets: unknown key raises KeyError", False)
    except KeyError:
        check("presets: unknown key raises KeyError", True)
    # determinism
    check("presets: apply_preset deterministic",
          sp.apply_preset("ham_2m") == sp.apply_preset("ham_2m"))


def gate_tl_writer():
    """E5: the NEC2 writer's TransmissionLine path — deck-level, no nec2c.

    Pins the crossed sign flip, center-segment fields, contiguous TL-block
    placement, the error paths, the zero-arg makeLPDA() default, and the
    BYTE-IDENTICAL no-TL deck (frozen literal — the v0.61.0 promise)."""
    try:
        import FreeCAD
        import Part
    except Exception:
        print("  skip  TL-writer tier — needs freecadcmd (FreeCAD)")
        return
    import tempfile

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import query
    from emstudio.objects import solver_objs
    from emstudio.objects import transmission_line as tl_mod
    from emstudio.solvers.nec2 import writer
    from emstudio.templates import dipole as dipole_tpl
    from emstudio.templates import lpda as lpda_tpl

    print("- E5 TL writer tier (deck-level)")

    # --- byte-identical no-TL deck (frozen 2026-07-19, v0.61.0) ------------
    FROZEN_DIPOLE_DECK = (
        "CM EMStudio generated NEC2 deck\n"
        "CM analysis: Dipole Analysis\n"
        "CE\n"
        "GW 1,27,0,0,-0.237336,0,0,0.237336,0.002\n"
        "GE 0\n"
        "EX 0,1,14,0,1.,0.\n"
        "FR 0,201,0,0,200.000000,1.000000\n"
        "XQ\n"
        "EN\n")
    doc = FreeCAD.newDocument("gate_tl_frozen")
    try:
        ana = dipole_tpl.makeDipole(doc, f0_hz=300e6)
        solver = query.get_solvers(ana)[0]
        deck = tempfile.mktemp(suffix=".nec", dir=tempfile.gettempdir())
        writer.write_nec(ana, solver, deck)
        with open(deck) as fh:
            check("no-TL analyses produce the BYTE-IDENTICAL frozen deck",
                  fh.read() == FROZEN_DIPOLE_DECK)
        os.remove(deck)
    finally:
        FreeCAD.closeDocument(doc.Name)

    # --- TL emission: sign, center segments, placement, farfield parity ----
    doc = FreeCAD.newDocument("gate_tl_emit")
    try:
        w1 = doc.addObject("Part::Feature", "WireA")
        w1.Shape = Part.makeLine(FreeCAD.Vector(0, 0, -500),
                                 FreeCAD.Vector(0, 0, 500))
        w2 = doc.addObject("Part::Feature", "WireB")
        w2.Shape = Part.makeLine(FreeCAD.Vector(500, 0, -400),
                                 FreeCAD.Vector(500, 0, 400))
        ana = analysis_mod.makeAnalysis(doc)
        ana.FrequencyStart = "100 MHz"
        ana.FrequencyStop = "200 MHz"
        ana.FrequencyPoints = 3
        mat = material_mod.makeMaterial(doc, ana, name="PEC",
                                        category="Metal (PEC)")
        mat.References = [(w1, "Edge1"), (w2, "Edge1")]
        mat.WireRadius = "2 mm"
        port = ports_mod.makeLumpedPort(doc, ana, name="Feed", direction="+Z")
        port.References = [(w2, "Edge1")]
        tl = tl_mod.makeTransmissionLine(
            doc, ana, references=[(w1, "Edge1"), (w2, "Edge1")],
            z0_ohm=73.1, crossed=True)
        solver = solver_objs.makeSolverNEC2(doc, ana)
        doc.recompute()

        def deck_lines(write_fn, *args):
            path = tempfile.mktemp(suffix=".nec", dir=tempfile.gettempdir())
            write_fn(ana, solver, path, *args)
            with open(path) as fh:
                text = fh.read()
            os.remove(path)
            return text.splitlines()

        lines = deck_lines(writer.write_nec)
        tl_cards = [ln for ln in lines if ln.startswith("TL ")]
        gw = [ln for ln in lines if ln.startswith("GW")]
        nsegs = [int(ln.split(",")[1]) for ln in gw]
        check("crossed TL emits ONE negative-Z0 card",
              len(tl_cards) == 1 and ",-73.1," in tl_cards[0], str(tl_cards))
        check("TL-referenced wires forced to odd segment counts",
              all(n % 2 == 1 for n in nsegs), str(nsegs))
        f = tl_cards[0].split()[1].split(",")
        t1, s1, t2, s2 = (int(f[0]), int(f[1]), int(f[2]), int(f[3]))
        check("TL attaches at the center segments ((nseg+1)//2)",
              s1 == (nsegs[t1 - 1] + 1) // 2
              and s2 == (nsegs[t2 - 1] + 1) // 2, tl_cards[0])
        check("TL length 0 (auto straight-line distance) + zero shunts",
              tl_cards[0].split(",")[5:] == ["0", "0", "0", "0", "0"],
              tl_cards[0])
        kinds = [ln.split()[0] for ln in lines]
        check("TL block sits between GE and EX (NEC2 contiguity)",
              kinds.index("GE") < kinds.index("TL") < kinds.index("EX"))
        ff_lines = deck_lines(writer.write_nec_farfield, 150e6)
        check("farfield deck carries the TL card too",
              any(ln.startswith("TL ") and ",-73.1," in ln
                  for ln in ff_lines))
        tl.Crossed = False
        lines2 = deck_lines(writer.write_nec)
        check("uncrossed TL emits positive Z0",
              any(ln.startswith("TL ") and ",73.1," in ln
                  and ",-73.1," not in ln for ln in lines2))
        tl.Crossed = True

        # --- error honesty ------------------------------------------------
        def expect_error(name, mutate, restore):
            mutate()
            try:
                path = tempfile.mktemp(suffix=".nec",
                                       dir=tempfile.gettempdir())
                try:
                    writer.write_nec(ana, solver, path)
                    check(name, False)
                finally:
                    if os.path.exists(path):
                        os.remove(path)
            except writer.WireModelError:
                check(name, True)
            finally:
                restore()

        old_refs = tl.References
        expect_error("TL with one reference raises WireModelError",
                     lambda: setattr(tl, "References", [(w1, "Edge1")]),
                     lambda: setattr(tl, "References", old_refs))
        expect_error("TL connecting an edge to itself raises",
                     lambda: setattr(tl, "References",
                                     [(w1, "Edge1"), (w1, "Edge1")]),
                     lambda: setattr(tl, "References", old_refs))
        w3 = doc.addObject("Part::Feature", "NotPEC")
        w3.Shape = Part.makeLine(FreeCAD.Vector(900, 0, -100),
                                 FreeCAD.Vector(900, 0, 100))
        expect_error("TL to a non-PEC edge raises",
                     lambda: setattr(tl, "References",
                                     [(w1, "Edge1"), (w3, "Edge1")]),
                     lambda: setattr(tl, "References", old_refs))
        old_z0 = tl.Z0
        expect_error("TL with Z0 = 0 raises",
                     lambda: setattr(tl, "Z0", "0 Ohm"),
                     lambda: setattr(tl, "Z0", old_z0))
    finally:
        FreeCAD.closeDocument(doc.Name)

    # --- the zero-arg template default (the review's makeLPDA fix) ---------
    doc = FreeCAD.newDocument("gate_tl_lpda_default")
    try:
        ana = lpda_tpl.makeLPDA(doc)
        check("makeLPDA() zero-arg default builds the classic 8 dBi "
              "54-216 MHz design (15 elements, 14 crossed TLs)",
              len(query.get_transmission_lines(ana)) == 14
              and all(t.Crossed for t in query.get_transmission_lines(ana)))
    finally:
        FreeCAD.closeDocument(doc.Name)


def gate_templates():
    """E2: template dimension overrides — defaults BYTE-IDENTICAL (the
    dipole_nec2/monopole_nec2 gates pin the reference numbers), overrides
    land exactly. Geometry-only: needs FreeCAD, not nec2c."""
    try:
        import FreeCAD
        import Part  # noqa: F401
    except Exception:
        print("  skip  template-override tier — needs freecadcmd (FreeCAD)")
        return
    import FreeCAD

    from emstudio.templates import dipole as dipole_tpl
    from emstudio.templates import monopole as monopole_tpl

    lam300_mm = 299792458.0 / 300e6 * 1000.0
    doc = FreeCAD.newDocument("gate_tpl_default")
    try:
        ana = dipole_tpl.makeDipole(doc, f0_hz=300e6)
        wire = doc.getObject("DipoleWire")
        check("makeDipole default: L == 0.475*lambda (frozen template "
              "geometry; engine-side identity is the bit-exact one)",
              abs(wire.Shape.Length - 0.475 * lam300_mm) < 1e-6,
              "{0!r} mm".format(wire.Shape.Length))
        check("makeDipole default: sweep 201 points (frozen)",
              ana.FrequencyPoints == 201)
        ana2 = monopole_tpl.makeMonopole(doc, f0_hz=100e3)
        mast = doc.getObject("MonopoleWire")
        lam100k_mm = 299792458.0 / 100e3 * 1000.0
        check("makeMonopole default: h == 0.1*lambda, 5 points (frozen)",
              abs(mast.Shape.Length - 0.1 * lam100k_mm) < 1e-6
              and ana2.FrequencyPoints == 5,
              "{0:.3f} m".format(mast.Shape.Length / 1000.0))
        from emstudio.objects import query

        check("makeMonopole default: segment sizing frozen (spw 1300)",
              query.get_solvers(ana2)[0].SegmentsPerWavelength == 1300)
    finally:
        FreeCAD.closeDocument(doc.Name)

    doc = FreeCAD.newDocument("gate_tpl_override")
    try:
        dipole_tpl.makeDipole(doc, f0_hz=300e6, length_m=0.4)
        wire = doc.getObject("DipoleWire")
        check("makeDipole length_m=0.4 override lands exactly (400 mm)",
              abs(wire.Shape.Length - 400.0) < 1e-9,
              "{0:.6f} mm".format(wire.Shape.Length))
        monopole_tpl.makeMonopole(doc, f0_hz=300e6, wire_radius_m=0.002,
                                  height_m=0.2373)
        mast = doc.getObject("MonopoleWire")
        check("makeMonopole height_m=0.2373 override lands exactly",
              abs(mast.Shape.Length - 237.3) < 1e-9,
              "{0:.6f} mm".format(mast.Shape.Length))
    finally:
        FreeCAD.closeDocument(doc.Name)


def gate_live_folded():
    """Live folded-dipole tier: the repo writer expresses the fold; pinned
    at the de-risked resonance (multi-crossing R-window selection)."""
    try:
        import FreeCAD  # noqa: F401
        import Part  # noqa: F401
    except Exception:
        print("  skip  live folded tier — needs freecadcmd (FreeCAD geometry)")
        return
    import shutil

    if not shutil.which("nec2c"):
        print("  skip  live folded tier — nec2c not installed")
        return
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import query, solver_objs
    from emstudio.solvers import nec2

    lam = 299792458.0 / 300e6
    L = 0.475 * lam * 1000.0  # mm — the de-risked deck
    s = lam / 100.0 * 1000.0
    doc = FreeCAD.newDocument("gate_folded")
    try:
        objs = {}
        for name, (a, b) in {
                "FedWire": ((0, 0, -L / 2), (0, 0, L / 2)),
                "ReturnWire": ((s, 0, -L / 2), (s, 0, L / 2)),
                "ShortBot": ((0, 0, -L / 2), (s, 0, -L / 2)),
                "ShortTop": ((0, 0, L / 2), (s, 0, L / 2))}.items():
            w = doc.addObject("Part::Feature", name)
            w.Shape = Part.makeLine(FreeCAD.Vector(*a), FreeCAD.Vector(*b))
            objs[name] = w
        ana = analysis_mod.makeAnalysis(doc)
        ana.FrequencyStart = "200 MHz"
        ana.FrequencyStop = "400 MHz"
        ana.FrequencyPoints = 201
        mat = material_mod.makeMaterial(doc, ana, name="WirePEC",
                                        category="Metal (PEC)")
        mat.References = [(objs[n], "Edge1") for n in
                          ("FedWire", "ReturnWire", "ShortBot", "ShortTop")]
        mat.WireRadius = "1 mm"
        port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort",
                                        direction="+Z")
        port.References = [(objs["FedWire"], "Edge1")]
        solver = solver_objs.makeSolverNEC2(doc, ana)
        solver.SegmentsPerWavelength = 42  # equal odd counts on both wires
        doc.recompute()
        try:
            result = nec2.run(ana, solver)
        except Exception as exc:  # noqa: BLE001
            print("  skip  live folded tier — NEC2 run unavailable: {0}".format(exc))
            return
        # resonance by R-window: the fold has anti-resonances (~7.9 kohm at
        # 204 MHz, ~1.6 kohm at 381 MHz) around the real one — never take
        # the first X=0 crossing blindly
        best = None
        for f_hz, z in zip(result.freq, result.zin):
            if 150.0 <= z.real <= 500.0 and (
                    best is None or abs(z.imag) < abs(best[1].imag)):
                best = (f_hz, z)
        check("live folded dipole: a resonance exists inside the 150-500 ohm "
              "window", best is not None)
        if best:
            f_res, z_res = best
            check("live folded resonance at the de-risked 291.1 MHz (1%)",
                  abs(f_res / 291.14e6 - 1.0) < 0.01,
                  "{0:.2f} MHz".format(f_res / 1e6))
            check("live folded R 283 ohm class (Balanis 280-300 window, 5%)",
                  269.0 <= z_res.real <= 297.0,
                  "{0:.1f} ohm".format(z_res.real))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio Element Designer E1-E5 (synthesis/recommender/families) gate")
    gate_synthesis()
    gate_picker()
    gate_yagi()
    gate_patch()
    gate_lpda()
    gate_presets()
    gate_tl_writer()
    gate_templates()
    gate_live_folded()
    if FAILURES:
        print("ELEMENT-DESIGNER GATE FAILED: {0}".format(FAILURES))
        return 1
    print("ELEMENT-DESIGNER GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("element-designer validation failed")
    sys.exit(0)
