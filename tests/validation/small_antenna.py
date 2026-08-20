# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: electrically-small antenna analytics vs textbook formulas.

Pass: exit 0 and 'SMALL-ANTENNA GATE PASSED'. Pure python3 (no solver).

Checks the closed-form VLF/LF/MF small-antenna models against the standard
textbook results (Balanis short dipole/monopole; Chu Q limit).
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    from emstudio.antenna import small_antenna as sa

    print("EMStudio electrically-small antenna validation gate (VLF/LF)")
    f = 30e6  # arbitrary; results scale with L/lambda so f cancels
    lam = C0 / f

    # short dipole L = lambda/10: Rr = 20 pi^2 (0.1)^2 = 1.9739 ohm; le = L/2
    d = sa.short_dipole(lam * 0.1, f)
    check("short-dipole Rr = 20 pi^2 (L/lambda)^2 (Balanis)",
          abs(d["radiation_resistance_ohm"] - 20 * math.pi ** 2 * 0.01) < 1e-9,
          "{0:.4f} ohm (expect 1.9739)".format(d["radiation_resistance_ohm"]))
    check("short-dipole effective length = L/2",
          abs(d["effective_length_m"] - lam * 0.05) < 1e-9)

    # short monopole h = lambda/10: Rr = 40 pi^2 (0.1)^2 = 3.9478 ohm; he = h/2
    m = sa.short_monopole(lam * 0.1, f)
    check("short-monopole Rr = 40 pi^2 (h/lambda)^2 (Balanis)",
          abs(m["radiation_resistance_ohm"] - 40 * math.pi ** 2 * 0.01) < 1e-9,
          "{0:.4f} ohm (expect 3.9478)".format(m["radiation_resistance_ohm"]))
    check("short-monopole effective height = h/2",
          abs(m["effective_height_m"] - lam * 0.05) < 1e-9)
    check("monopole Rr is exactly 2x the dipole Rr at same L/lambda",
          abs(m["radiation_resistance_ohm"] - 2 * d["radiation_resistance_ohm"]) < 1e-9)

    # Chu Q: pick a/lambda so ka = 0.5 -> Q = 1/0.125 + 1/0.5 = 10
    a = lam * (0.5 / (2 * math.pi))
    q = sa.chu_min_q(a, f)
    check("Chu min-Q = 1/(ka)^3 + 1/(ka) = 10 at ka=0.5", abs(q - 10.0) < 1e-6,
          "{0:.4f}".format(q))
    check("bandwidth = (S-1)/(Q sqrt(S)); Q=10,S=2 -> 0.0707",
          abs(sa.fractional_bandwidth(10.0, 2.0) - (1.0 / (10 * math.sqrt(2)))) < 1e-9)
    check("efficiency = Rr/(Rr+Rloss); 4/(4+4) = 0.5",
          abs(sa.radiation_efficiency(4.0, 4.0) - 0.5) < 1e-12)

    # honest VLF case: a 100 m monopole at 30 kHz (lambda = 10 km) is tiny + must
    # need loading, with a very small Rr and a very high Chu Q.
    vlf = sa.short_monopole(100.0, 30e3, r_loss=1.0)
    check("VLF 100 m @ 30 kHz is electrically small + needs loading",
          vlf["electrically_small"] and vlf["needs_loading"],
          "h/lambda={0:.4f}, Rr={1:.4g} ohm, Q={2:.3g}".format(
              vlf["height_over_lambda"], vlf["radiation_resistance_ohm"],
              vlf["chu_min_q"]))
    check("VLF loading inductance is finite/positive (resonates the -jXc)",
          vlf["loading_inductance_h"] > 0 and math.isfinite(vlf["loading_inductance_h"]),
          "L_load = {0:.3g} H".format(vlf["loading_inductance_h"]))

    # small loop (dual of the short dipole): Rr = 31171 N^2 (A/lambda^2)^2
    A = lam ** 2 / 1000.0
    lp = sa.short_loop(A, f, turns=1)
    check("small-loop Rr = 31171 (A/lambda^2)^2 (Balanis)",
          abs(lp["radiation_resistance_ohm"] - 31171.0 * (A / lam ** 2) ** 2) < 1e-9,
          "{0:.5g} ohm".format(lp["radiation_resistance_ohm"]))
    check("small-loop Rr scales as N^2 (10 turns -> 100x)",
          abs(sa.short_loop(A, f, turns=10)["radiation_resistance_ohm"]
              - 100.0 * lp["radiation_resistance_ohm"]) < 1e-6)
    check("small-loop effective height = 2 pi N A / lambda",
          abs(lp["effective_height_m"] - 2 * math.pi * A / lam) < 1e-9)

    # --- band -> recommended-method picker ---
    from emstudio.antenna import band_picker as bp

    check("band_of(24 kHz) == VLF",
          bp.band_of(24e3)[0] == "VLF", bp.band_of(24e3)[0])
    check("band_of(10 kHz) == VLF (AJ's VLF floor)",
          bp.band_of(10e3)[0] == "VLF")
    check("band_of(150 kHz) == LF", bp.band_of(150e3)[0] == "LF")
    check("band_of(2.435 GHz) == UHF", bp.band_of(2.435e9)[0] == "UHF")
    check("band_of(40 GHz) == EHF", bp.band_of(40e9)[0] == "EHF")

    r_vlf = bp.recommend_method(24e3, max_dim_m=150.0)
    check("VLF routes to analytic small-antenna + NEC2-with-ground",
          r_vlf["primary"] == "small_antenna" and "nec2_ground" in r_vlf["methods"],
          r_vlf["primary"])
    check("VLF picker flags the 150 m mast as electrically small",
          "electrically small" in (r_vlf.get("size_note") or ""))
    r_hf = bp.recommend_method(300e6, wire_structure=True)
    check("300 MHz wire routes to NEC2 (full-wave MoM)",
          r_hf["primary"] == "nec2" and "openems" in r_hf["methods"], r_hf["primary"])
    r_mm = bp.recommend_method(40e9, wire_structure=False)
    check("40 GHz routes to Palace/openEMS (full-wave FEM/FDTD)",
          r_mm["primary"] == "palace" and "openems" in r_mm["methods"], r_mm["primary"])
    check("summary_text renders a Band/Recommended block",
          "Band:" in bp.summary_text(r_vlf) and "Recommended:" in bp.summary_text(r_vlf))

    # ⚠ The rationale strings are USER-VISIBLE, and one of them printed
    # "10.71 mm m wavelength" at mmWave for as long as the mmWave branch has
    # existed: ``_fmt_wavelength`` already carries its unit and the format
    # string appended a literal " m" after it. Nothing gated the prose, only
    # the routing, so a reader saw it long before a test did. Sweep every
    # decade rather than the one frequency that was reported.
    import re as _re
    _dbl = _re.compile(r"\b(km|m|mm|um)\s+(km|m|mm|um)\b")
    _bad = []
    for _f in (24e3, 3e6, 300e6, 2.4e9, 28e9, 40e9, 100e9):
        _r = bp.recommend_method(_f)
        for _key in ("rationale", "validity"):
            _hit = _dbl.search(_r.get(_key, ""))
            if _hit:
                _bad.append("%g Hz %s: %r" % (_f, _key, _hit.group(0)))
    check("no doubled unit in any band-picker rationale (10.71 mm m)",
          not _bad, "; ".join(_bad[:3]))

    # ================= §4 breadth: top-loading capacitance =================
    # (verified from the reference page images with exact-identity
    # cross-checks — docs/upstream/watt-topload-anchors.md)
    from emstudio.antenna import ground_system as gs
    from emstudio.antenna import topload as tp

    print("- top-loading capacitance (verified set)")
    eps0 = 8.8541878128e-12
    check("24.16 == 2*pi*eps0/ln(10) exactly (pF/m)",
          abs(2 * math.pi * eps0 / math.log(10.0) * 1e12
              - tp.C_LOG10_PF_PER_M) < 1e-2)
    # Brown scale-model reproduction (plate + fringe) — the five
    # internally-consistent models; G excluded (book-internal typo,
    # anchors doc). Components (area, fringe) in in^2; printed calc pF.
    IN2 = 0.0254 ** 2
    h_model = 3.375 * 0.0254
    models = [("A", 52.65, 91.13, 9.55), ("D", 105.30, 151.88, 17.07),
              ("J", 157.95, 151.88 + 30.38, 22.60),  # J eff 340.21 = 157.95+182.26
              ("P", 52.73, 129.60, 12.11), ("Q", 70.30, 157.95, 15.16)]
    for name, area, fringe, printed in models:
        c = tp.plate_hat_c(area * IN2, h_model,
                           perimeter_m=(fringe / 3.375) * 0.0254)
        check("hat model {0}: plate+fringe reproduces the printed calc "
              "({1:g} pF) within 0.5%".format(name, printed),
              abs(c * 1e12 - printed) / printed < 0.005,
              "{0:.3f} pF".format(c * 1e12))
    # coax identity: 24.16/log10(D/d) == the exact TEM C' at eps_r=1
    cw = tp.coax_c_per_m(0.001, 0.005)
    check("air-coax identity vs 2*pi*eps0/ln(D/d) < 0.1%",
          abs(cw - 2 * math.pi * eps0 / math.log(5.0)) / cw < 1e-3)
    # k-table branch continuity at 2h/l = 1 (both branches meet at 0.336)
    check("horizontal k-table branches continuous at 2h/l = 1",
          abs(tp.k_horizontal(2.0, 1.0) - 0.336) < 1e-12
          and abs(tp.k_horizontal(2.0, 1.0 + 1e-9)
                  - tp.k_horizontal(2.0, 1.0 - 1e-9)) < 1e-3)
    # flat-top n=2 equals the printed special form (48.32 numerator)
    l, hh, d, D = 100.0, 15.0, 0.005, 2.0
    c2, w2 = tp.flat_top_c(2, l, hh, d, D)
    k2 = tp.k_horizontal(l, hh)
    c211 = 48.32 * l / (math.log10(4 * hh / d) - 2 * k2
                        + math.log10(2 * hh / D)) * 1e-12
    check("flat-top n=2 == the printed two-wire special form",
          abs(c2 - c211) / c211 < 1e-12 and not w2)
    # validity flag fires when the top is too wide
    _c3, w3 = tp.flat_top_c(8, 40.0, 15.0, 0.005, 2.0)
    check("flat-top width > l/4 raises the validity warning",
          any("l/4" in w for w in w3))
    # T reduces C more than the inverted-L (printed statement)
    cl = tp.inverted_l_c(60.0, 15.0, 15.0, 2.0, 0.005)
    ct = tp.t_antenna_c(60.0, 15.0, 15.0, 2.0, 0.005)
    check("T antenna C < inverted-L C (stronger mutual term)", ct < cl,
          "{0:.1f} vs {1:.1f} pF".format(ct * 1e12, cl * 1e12))
    # vertical-plane curtain: the (n-1)-weight fix (third book typo) must
    # keep C below the physical n-times-isolated-wire bound and monotone
    c1v = tp.vertical_wire_c(100.0, 10.0, 0.005)
    prev = 0.0
    ok_vp = True
    for nn in (2, 3, 4, 6, 8, 12, 20):
        cn = tp.vertical_plane_c(nn, 100.0, 10.0, 0.005, 2.0)
        if cn > nn * c1v or cn < prev:
            ok_vp = False
        prev = cn
    check("vertical-plane C stays under n*C1 and monotone (the (n-1) "
          "weight fix)", ok_vp,
          "n=20 -> {0:.0f} pF vs bound {1:.0f}".format(
              tp.vertical_plane_c(20, 100.0, 10.0, 0.005, 2.0) * 1e12,
              20 * c1v * 1e12))
    # the k_n table obeys its own derivation identity (which assumes the
    # (n-1) weight) — the evidence the printed 2.3.14 weight is a typo
    kn_worst = max(abs(2.0 / n ** 2
                       * sum((n - m) * math.log10(m) for m in range(1, n))
                       - kn) for n, kn in tp.K_N_FLAT_TOP)
    check("k_n table matches the (n-1)-weight identity to <0.005",
          kn_worst < 0.005, "worst {0:.4f}".format(kn_worst))
    # umbrella landmarks
    check("umbrella landmarks pinned (0.35 / x8 / x3)",
          tp.UMBRELLA_HE_MAX_RATIO == 0.35
          and tp.UMBRELLA_07_POWER_FACTOR == 8.0
          and tp.UMBRELLA_07_BANDWIDTH_FACTOR == 3.0)
    # trapezoid effective height: unloaded h/2, fully hat-dominated -> h,
    # equal C -> 3h/4 (the Laport construction endpoints)
    check("top-loaded h_e trapezoid endpoints (h/2, ~h, 3h/4)",
          abs(tp.effective_height_toploaded(150.0, 0.0, 1e-9) - 75.0) < 1e-9
          and tp.effective_height_toploaded(150.0, 1e-6, 1e-9) > 149.0
          and abs(tp.effective_height_toploaded(150.0, 1e-9, 1e-9)
                  - 112.5) < 1e-9)

    # ================= §4 breadth: radial ground estimator =================
    print("- radial-ground estimator (zone integrals)")
    check("0.366 == ln10/2pi exactly",
          abs(gs.LN10_OVER_2PI - math.log(10.0) / (2 * math.pi)) < 1e-15)
    check("earth surface resistance == sqrt(pi f mu0/sigma)",
          abs(gs.earth_surface_resistance(24e3, 0.005)
              - math.sqrt(math.pi * 24e3 * 4e-7 * math.pi / 0.005)) < 1e-12)
    base = gs.ground_resistance(24e3, 150.0, 120, 400.0, 0.005)
    check("representative VLF case lands in the real-system class "
          "(0.05-0.5 ohm)", 0.05 <= base["rg_ohm"] <= 0.5,
          "{0:.4f} ohm".format(base["rg_ohm"]))
    check("Rg regression pin (0.1436 ohm at 24 kHz/150 m/N120/a400/"
          "sigma 5 mS)", abs(base["rg_ohm"] - 0.1436) < 2e-3,
          "{0:.4f}".format(base["rg_ohm"]))
    more_n = gs.ground_resistance(24e3, 150.0, 240, 400.0, 0.005)
    big_a = gs.ground_resistance(24e3, 150.0, 120, 2000.0, 0.005)
    bare = gs.ground_resistance(24e3, 150.0, 0, 0.0, 0.005)
    check("more wires reduce Rg", more_n["rg_ohm"] < base["rg_ohm"])
    check("a bigger screen never increases Rg (crossover-capped)",
          big_a["rg_ohm"] <= base["rg_ohm"] + 1e-12)
    check("any screen beats bare earth", base["rg_ohm"] < bare["rg_ohm"])
    sea = gs.ground_resistance(24e3, 150.0, 120, 400.0, 4.0)
    check("sea water: tiny Rg, screen adds only the near-base benefit",
          sea["rg_ohm"] < 0.1 and sea["rg_ohm"] < base["rg_ohm"])
    check("short-vertical scope guard (h >= lambda/2pi raises)",
          _raises(lambda: gs.ground_resistance(24e3, 3000.0, 100, 500.0,
                                               0.005)))
    opt = gs.optimize_radials(24e3, 150.0, 0.2, 0.005)
    reach = [o for o in opt if o["reachable"]]
    check("optimizer: at least one reachable design, ascending wire cost",
          len(reach) >= 1
          and all(reach[i]["total_wire_m"] <= reach[i + 1]["total_wire_m"]
                  for i in range(len(reach) - 1)))
    # unreachable target: EVERY entry must be flagged unreachable (the
    # precedence-bug regression — the check must actually run here)
    opt_bad = gs.optimize_radials(24e3, 150.0, 1e-4, 0.005)
    check("optimizer: an impossible target yields all-unreachable",
          all(not o["reachable"] for o in opt_bad))
    # bare earth already meets the target -> "no screen needed", radius 0
    opt_sea = gs.optimize_radials(24e3, 100.0, 10.0, 5.0)
    check("optimizer: no-screen-needed when bare earth already meets it",
          len(opt_sea) == 1 and opt_sea[0]["no_screen_needed"]
          and opt_sea[0]["radius_m"] == 0.0)

    # ================= §4 breadth: voltage-limited set ======================
    print("- voltage-limited power/bandwidth (exact coefficients)")
    vl = sa.voltage_limited(24e3, 0.05e-6, 150.0, 200e3, eta_ts=0.5)
    check("Pr coefficient == 640 pi^4/c0^2 (printed 6.95e-13 within 1%)",
          abs(vl["pr_coefficient"] - 640 * math.pi ** 4 / 299792458.0 ** 2)
          < 1e-20 and abs(vl["pr_coefficient"] - 6.95e-13) / 6.95e-13 < 0.01)
    check("bw coefficient == 320 pi^3/c0^2 (printed 1.11e-13 within 1%)",
          abs(vl["bw_coefficient"] - 320 * math.pi ** 3 / 299792458.0 ** 2)
          < 1e-20 and abs(vl["bw_coefficient"] - 1.11e-13) / 1.11e-13 < 0.01)
    # identity: Pr == (2 pi f C V)^2 * Rr with Rr = 160 pi^2 (he/lam)^2
    f, c, he, v = 24e3, 0.05e-6, 150.0, 200e3
    lam = 299792458.0 / f
    rr = 160 * math.pi ** 2 * (he / lam) ** 2
    pr_direct = (2 * math.pi * f * c * v) ** 2 * rr
    check("Pr identity vs (2 pi f C V)^2 * Rr at machine precision",
          abs(vl["radiated_power_w"] - pr_direct) / pr_direct < 1e-12)
    # P*b product vs the INDEPENDENT closed form 7.71e-26 V^2 C^3 he^4 f^8
    # / eta (2.1.13l) — not a self-comparison
    pb_closed = (7.71e-26 * v ** 2 * c ** 3 * he ** 4 * f ** 8 / 0.5)
    check("P*b matches the independent 7.71e-26 closed form within 1%",
          abs(vl["power_bandwidth_w_hz"] - pb_closed) / pb_closed < 0.01,
          "{0:.3g} vs {1:.3g}".format(vl["power_bandwidth_w_hz"], pb_closed))
    vshunt = sa.voltage_limited(24e3, 0.05e-6, 150.0, 200e3,
                                delta_c_farads=0.01e-6)
    check("shunt dC: he and antenna-only bandwidth shrink by C/(C+dC)",
          abs(vshunt["shunt_effective_height_factor"] - 5.0 / 6.0) < 1e-12)
    check("f > f_res/2 warns", any("f_res" in w for w in sa.voltage_limited(
        24e3, 0.05e-6, 150.0, 200e3, f_res_hz=40e3)["warnings"]))

    # ================= §4 breadth: efficiency ladder + h_e utility =========
    print("- efficiency ladder + experimental h_e")
    # anonymized measured (h_e, f) -> Rr end-to-end pairs (scan-verified):
    for he_m, f_kc, rr_meas in ((83.0, 15.79, 0.030), (96.0, 18.0, 0.0524)):
        lamx = 299792458.0 / (f_kc * 1e3)
        rr = 160 * math.pi ** 2 * (he_m / lamx) ** 2
        check("Rr({0:g} m, {1:g} kc/s) reproduces the measured {2:g} ohm "
              "within 2%".format(he_m, f_kc, rr_meas),
              abs(rr - rr_meas) / rr_meas < 0.02, "{0:.4f}".format(rr))
    lad = sa.efficiency_ladder(0.03, r_ground=0.05, r_copper=0.01,
                               r_coil=0.02, r_transmitter=0.03,
                               x_c_ohm=1200.0, freq_hz=15.79e3)
    check("efficiency ladder ordering eta_a > eta_as > eta_ts",
          lad["eta_a"] > lad["eta_as"] > lad["eta_ts"] > 0)
    check("eta_a identity Rr/(Rr+Rl)",
          abs(lad["eta_a"] - 0.03 / (0.03 + 0.06)) < 1e-12)
    check("Q(eta=1) = Xc/Rr and b = f/Q",
          abs(lad["q_eta1"] - 1200.0 / 0.03) < 1e-9
          and abs(lad["bandwidth_eta1_hz"] - 15.79e3 / (1200.0 / 0.03))
          < 1e-9)
    check("suspicious-eta warning fires at low VLF",
          any("re-check" in w for w in sa.efficiency_ladder(
              1.0, r_ground=0.01, freq_hz=15e3)["warnings"]))
    # h_e from field: exact inverse of the forward 2.1.8 field identity
    he0, f0x, i0, d0 = 150.0, 24e3, 100.0, 50e3
    e0 = 4 * math.pi * i0 * f0x * he0 / (1e7 * d0)
    check("effective_height_from_field inverts the field identity exactly",
          abs(sa.effective_height_from_field(e0, d0, i0, f0x) - he0) < 1e-9)
    # and the 300*sqrt(P_kW)/d_km field constant is consistent with Rr:
    # E(mV/m) at 1 km for 1 kW: 300 -> via Pr = E^2 d^2/90 identity
    check("E = 300 sqrt(P_kW)/d_km consistency (Pr = Ez^2 d^2/90)",
          abs(300.0 ** 2 * 1e-6 / 90.0 * 1e6 - 1000.0) < 1e-9)

    if FAILURES:
        print("SMALL-ANTENNA GATE FAILED: {0}".format(FAILURES))
        return 1
    print("SMALL-ANTENNA GATE PASSED")
    return 0


def _raises(fn):
    try:
        fn()
        return False
    except ValueError:
        return True


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
        raise SystemExit("small-antenna validation failed")
    sys.exit(0)
