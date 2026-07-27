# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: co-site interference calculator vs textbook EMC formulas.

Pass: exit 0 and 'COSITE GATE PASSED'. Pure python3 (no solver).

Checks the intermodulation product frequencies, the intercept-point IMD level
relation, receiver desensitization, broadband-noise coupling and the frequency-plan
clash / D-U logic against their closed-form definitions.
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


def _find_product(products, freq_hz, tol=1.0):
    for p in products:
        if abs(p["freq_hz"] - freq_hz) <= tol:
            return p
    return None


def main():
    from emstudio.cosite import interference as ci

    print("EMStudio co-site interference validation gate")

    # --- intermodulation product frequencies (two-tone) ---
    f1, f2 = 150e6, 151e6
    prods = ci.intermod_products([f1, f2], max_order=3)
    p_lo = _find_product(prods, 2 * f1 - f2)   # 149 MHz, 3rd order
    p_hi = _find_product(prods, 2 * f2 - f1)   # 152 MHz, 3rd order
    check("two-tone 3rd-order 2f1-f2 = 149 MHz present",
          p_lo is not None and p_lo["order"] == 3,
          "{0:.6g} MHz".format(p_lo["freq_hz"] / 1e6) if p_lo else "missing")
    check("two-tone 3rd-order 2f2-f1 = 152 MHz present",
          p_hi is not None and p_hi["order"] == 3)
    check("2nd-order sum f1+f2 = 301 MHz present",
          _find_product(prods, f1 + f2) is not None)
    check("2nd-order difference |f1-f2| = 1 MHz present",
          _find_product(prods, f2 - f1) is not None)

    # three-tone third order f1+f2-f3
    f3 = 155e6
    prods3 = ci.intermod_products([f1, f2, f3], max_order=3)
    check("three-tone 3rd-order f1+f2-f3 = 146 MHz present",
          _find_product(prods3, f1 + f2 - f3) is not None,
          "146 MHz")

    # --- IMD level via the intercept-point relation ---
    # classic two-tone third order: equal -10 dBm tones, OIP3 +30 -> IMD3 -90 dBm
    lvl = ci.imd_level_dbm(p_lo, [-10.0, -10.0], 30.0)
    check("IMD3 level 2*P1+P2-2*IP3 = -90 dBm (P=-10, IP3=+30)",
          abs(lvl - (-90.0)) < 1e-9, "{0:.3f} dBm".format(lvl))
    # unequal tones: 2f1-f2 with P1=0, P2=-20, IP3=+30 -> 2*0 + (-20) - 60 = -80
    lvl2 = ci.imd_level_dbm(p_lo, [0.0, -20.0], 30.0)
    check("IMD3 unequal tones 2*0 + (-20) - 2*30 = -80 dBm",
          abs(lvl2 - (-80.0)) < 1e-9, "{0:.3f} dBm".format(lvl2))

    # --- coupling / noise book-keeping ---
    check("received power = tx - isolation (+43 dBm, 60 dB -> -17)",
          abs(ci.received_power_dbm(43.0, 60.0) - (-17.0)) < 1e-9)
    check("D/U = desired - undesired (-110 vs -7 -> -103 dB)",
          abs(ci.du_ratio_db(-110.0, -7.0) - (-103.0)) < 1e-9)
    # broadband noise: 40 - 150 + 10log10(25000) - 30
    expect = 40.0 - 150.0 + 10.0 * math.log10(25000.0) - 30.0
    check("broadband tx noise into 25 kHz rx (= {0:.2f} dBm)".format(expect),
          abs(ci.broadband_noise_at_rx_dbm(40.0, -150.0, 25e3, 30.0) - expect) < 1e-9)
    check("in_band: 149.99 MHz within 150 MHz +/- 25 kHz",
          ci.in_band(150e6 - 5e3, 150e6, 25e3) and not ci.in_band(150e6 - 20e3, 150e6, 25e3))

    # --- whole-site analysis ---
    Radio = ci.Radio
    # Two 10 W (+40 dBm) transmitters whose 2f1-f2 lands on a victim receiver.
    site = [
        Radio("TX-A", tx_freq_hz=150e6, tx_power_dbm=40.0),
        Radio("TX-B", tx_freq_hz=151e6, tx_power_dbm=40.0),
        Radio("RX-C", rx_freq_hz=149e6, rx_bw_hz=25e3, rx_sens_dbm=-110.0,
              rx_blocking_dbm=-20.0),
    ]
    rep = ci.analyze_site(site, isolation_db=30.0, junction_ip3_dbm=20.0, max_order=3)
    # power at the junction per carrier = 40 - 30 = 10 dBm; IMD3 = 2*10+10-2*20 = -10 dBm
    hit = [h for h in rep["imd"] if abs(h["freq_hz"] - 149e6) < 1e3]
    check("site IMD: 2f1-f2 hits RX-C at 149 MHz",
          len(hit) == 1 and hit[0]["victim"] == "RX-C", str(len(hit)))
    check("site IMD level -10 dBm, 100 dB over -110 sensitivity",
          hit and abs(hit[0]["level_dbm"] - (-10.0)) < 1e-6
          and abs(hit[0]["margin_db"] - 100.0) < 1e-6,
          "{0:.2f} dBm".format(hit[0]["level_dbm"]) if hit else "none")

    # desensitization: a strong off-channel tx blocks a nearby rx
    site2 = [
        Radio("BIG-TX", tx_freq_hz=150e6, tx_power_dbm=43.0),
        Radio("VICTIM", rx_freq_hz=160e6, rx_bw_hz=25e3, rx_blocking_dbm=-20.0),
    ]
    rep2 = ci.analyze_site(site2, isolation_db=40.0)
    des = [d for d in rep2["desense"] if d["desensed"]]
    # interferer at rx = 43 - 40 = 3 dBm; blocking -20 -> margin -23 (desensed)
    check("desense: +3 dBm interferer past -20 dBm blocking (margin -23)",
          len(des) == 1 and abs(des[0]["interferer_dbm"] - 3.0) < 1e-9
          and abs(des[0]["margin_db"] - (-23.0)) < 1e-9)
    # per-pair isolation dict (the NEC2 isolation-matrix import path): the
    # same site with {(0,1): 40} must reproduce the scalar-40 report exactly,
    # and {(0,1): 60} must lower the interferer by exactly 20 dB
    rep2d = ci.analyze_site(site2, isolation_db={(0, 1): 40.0})
    des_d = [d for d in rep2d["desense"] if d["desensed"]]
    check("per-pair dict == scalar for the matching pair value",
          len(des_d) == 1
          and abs(des_d[0]["interferer_dbm"] - des[0]["interferer_dbm"]) < 1e-12)
    rep2e = ci.analyze_site(site2, isolation_db={(0, 1): 60.0})
    check("per-pair 60 dB pair drops the interferer by exactly 20 dB",
          abs(rep2e["desense"][0]["interferer_dbm"] - (-17.0)) < 1e-9)

    # co-channel clash + D/U
    site3 = [
        Radio("CO-TX", tx_freq_hz=150e6, tx_power_dbm=43.0),
        Radio("CO-RX", rx_freq_hz=150e6, rx_bw_hz=25e3, rx_sens_dbm=-110.0),
    ]
    rep3 = ci.analyze_site(site3, isolation_db=50.0)
    cc = rep3["cochannel"]
    # interferer = 43 - 50 = -7 dBm; D/U = -110 - (-7) = -103 dB
    check("co-channel clash detected with D/U -103 dB",
          len(cc) == 1 and abs(cc[0]["du_db"] - (-103.0)) < 1e-9,
          "{0:.1f} dB".format(cc[0]["du_db"]) if cc else "none")

    check("summary_text renders a report block",
          "CO-SITE INTERFERENCE REPORT" in ci.summary_text(rep))

    # --- frequency-plan optimizer (phase C) ---
    # Two tunable transmitters whose 2f1-f2 lands on a fixed victim receiver; the
    # optimizer should retune them so no product hits the receiver. The victim has a
    # robust front end (high blocking level) so the ONLY interference is the IMD
    # product landing in-band — a frequency-fixable problem (desensitization is not,
    # it needs more isolation, so we keep it out of this test).
    plan_site = [
        Radio("TX-A", tx_freq_hz=150e6, tx_power_dbm=40.0),
        Radio("TX-B", tx_freq_hz=151e6, tx_power_dbm=40.0),
        Radio("RX-C", rx_freq_hz=149e6, rx_bw_hz=25e3, rx_sens_dbm=-110.0,
              rx_blocking_dbm=20.0),
    ]
    base = ci.analyze_site(plan_site, isolation_db=30.0, junction_ip3_dbm=20.0)
    base_cost = ci.plan_cost(base)
    check("baseline plan is dirty (2f1-f2 hits the victim, cost > 0)",
          base_cost > 0.0, "cost {0:.2f}".format(base_cost))
    opt = ci.optimize_frequency_plan(
        plan_site, tunable=[0, 1],
        candidates=[150e6, 150.5e6, 155e6, 160e6], isolation_db=30.0,
        junction_ip3_dbm=20.0)
    check("optimizer is exhaustive over the small space",
          opt["method"] == "exhaustive" and opt["evaluated"] == 16)
    check("optimizer finds a cleaner plan than the baseline",
          opt["cost"] < base_cost, "opt {0:.2f} < base {1:.2f}".format(
              opt["cost"], base_cost))
    check("optimized plan is interference-free (cost 0)",
          abs(opt["cost"]) < 1e-9, "cost {0:.3f}".format(opt["cost"]))
    # the winning assignment must actually move at least one carrier off 150/151
    check("optimizer reassigned a transmit frequency",
          opt["assignment"] != {0: 150e6, 1: 151e6})

    if FAILURES:
        print("COSITE GATE FAILED: {0}".format(FAILURES))
        return 1
    print("COSITE GATE PASSED")
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
        raise SystemExit("cosite validation failed")
    sys.exit(0)
