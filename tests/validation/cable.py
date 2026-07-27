# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Cable Designer analytics — coax TEM electricals (§2 phase A engine),
the RG-58/RG-142 geometry PRESETS and the single-wire (ops=[]) litz reuse behind the
Cable Designer UI (exact-Kelvin identity, handbook Rdc, frozen n>=2 regression anchors).

Pass: exit 0 and 'CABLE GATE PASSED'. Pure python3 (no solver, no FreeCAD).

Anchors are the primary datasheets pulled during the de-risk pass (kept as tool
artifacts): Belden 8262 (RG-58C/U type) and Belden UK / Pasternack RG-142B/U +
MIL-DTL-17 cross-checks. Two honest physics notes baked into the tolerances:

  * RG-58's 19x33 stranded centre: the 0.889 mm physical envelope gives 47.5 ohm;
    the classic ~0.94x effective diameter (0.836 mm) reproduces BOTH the 50 ohm
    nominal and the 101 pF/m capacitance — both are gated.
  * The smooth-solid-conductor loss model UNDER-estimates braided/tinned real
    cables, so datasheet attenuation is gated one-sided (model in 55-100 % of the
    published value), plus the exact sqrt(f) conductor-loss scaling.
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


def main():
    from emstudio.wire import coax
    from emstudio.solvers.palace import writer as pwriter

    print("EMStudio cable (§2 phase A — coax engine) validation gate")

    # --- identity with the shipped, Palace-gated Z0 formula ---
    check("coax_z0_ohm matches the shipped Palace coax_z0 (49.94 ohm air line)",
          abs(coax.coax_z0_ohm(0.5e-3, 1.15e-3, 1.0)
              - pwriter.coax_z0(0.5, 1.15, 1.0)) < 1e-6
          and abs(coax.coax_z0_ohm(0.5e-3, 1.15e-3, 1.0) - 49.94) < 0.1)
    # TEM identity: Z0 = sqrt(L'/C') exactly
    z = coax.coax_z0_ohm(0.5e-3, 1.5e-3, 2.1)
    lc = math.sqrt(coax.inductance_h_m(0.5e-3, 1.5e-3)
                   / coax.capacitance_f_m(0.5e-3, 1.5e-3, 2.1))
    check("TEM identity Z0 == sqrt(L'/C')", abs(z - lc) < 1e-9)

    # --- RG-58C/U (Belden 8262): a_eff 0.418 mm / b 1.4605 mm / PE 2.25 ---
    A_EFF, A_PHY, B58 = 0.418e-3, 0.4445e-3, 1.4605e-3
    z_eff = coax.coax_z0_ohm(A_EFF, B58, 2.25)
    z_phy = coax.coax_z0_ohm(A_PHY, B58, 2.25)
    check("RG-58 Z0 = 50.0 ohm with the stranded-centre effective diameter",
          abs(z_eff - 50.0) < 0.15, "{0:.2f} ohm".format(z_eff))
    check("RG-58 physical envelope gives the documented 47.5 ohm",
          abs(z_phy - 47.55) < 0.15, "{0:.2f} ohm".format(z_phy))
    check("RG-58 velocity factor = 66.7% (solid PE 2.25)",
          abs(coax.velocity_factor(2.25) - 2.0 / 3.0) < 1e-9)
    c58 = coax.capacitance_f_m(A_EFF, B58, 2.25) * 1e12
    check("RG-58 capacitance ~= 101 pF/m (Belden 30.8 pF/ft)",
          abs(c58 - 101.0) < 2.0, "{0:.1f} pF/m".format(c58))
    fc58 = coax.cutoff_te11_hz(A_EFF, B58, 2.25)
    check("RG-58 TE11 cutoff lands in the physical 10-60 GHz band",
          10e9 < fc58 < 60e9, "{0:.1f} GHz".format(fc58 / 1e9))

    # attenuation: smooth-conductor model vs the Belden dB/100ft table
    # (published dB/100ft * 3.2808 = dB/100m). Braid/tinning/stranding add
    # ~10-45%, so the smooth model must sit BELOW but within reach.
    for mhz, db100ft in ((10.0, 1.4), (100.0, 4.9), (400.0, 11.5)):
        pub = db100ft * 3.280839895
        got = coax.attenuation_db_per_100m(mhz * 1e6, A_EFF, B58, 2.25, 3e-4)
        check("RG-58 smooth-model attenuation in 55-100% of Belden @ {0:g} MHz"
              .format(mhz), 0.55 * pub <= got <= pub,
              "{0:.1f} vs {1:.1f} dB/100m".format(got, pub))
    ac1 = coax.conductor_loss_db_m(100e6, A_EFF, B58, 2.25)
    ac4 = coax.conductor_loss_db_m(400e6, A_EFF, B58, 2.25)
    check("conductor loss scales exactly as sqrt(f)",
          abs(ac4 / ac1 - 2.0) < 1e-9)

    # --- RG-142B/U (PTFE): a 0.470 mm / b 1.475 mm / eps_r 2.04 ---
    A142, B142 = 0.470e-3, 1.475e-3
    z142 = coax.coax_z0_ohm(A142, B142, 2.04)
    check("RG-142 geometry gives 48.0 ohm (bottom of the MIL 50+/-2 window)",
          abs(z142 - 48.0) < 0.2 and z142 >= 48.0 - 0.2,
          "{0:.2f} ohm".format(z142))
    check("RG-142 velocity factor = 70% (PTFE 2.04)",
          abs(coax.velocity_factor(2.04) - 0.700) < 0.001)
    a142 = coax.attenuation_db_per_100m(400e6, A142, B142, 2.04, 2e-4)
    check("RG-142 smooth model in 55-100% of Belden-UK 30.5 dB/100m @ 400 MHz",
          0.55 * 30.51 <= a142 <= 30.51, "{0:.1f} dB/100m".format(a142))

    # --- analyze() report dict ---
    rep = coax.analyze(A_EFF, B58, 2.25, 3e-4, freq_hz=100e6)
    keys = {"z0_ohm", "velocity_factor", "capacitance_pf_m", "inductance_nh_m",
            "cutoff_te11_hz", "conductor_db_100m", "dielectric_db_100m",
            "attenuation_db_100m"}
    check("analyze() report carries all keys + consistent totals",
          keys <= set(rep) and abs(rep["attenuation_db_100m"]
                                   - rep["conductor_db_100m"]
                                   - rep["dielectric_db_100m"]) < 1e-12)
    check("dielectric presets present (PE / PTFE / foam / air)",
          set(coax.DIELECTRICS) >= {"PE (solid polyethylene)", "PTFE (solid)",
                                    "Foam PE (typ. 80% VF)", "Air"})

    # --- §2 phase A (UI slice): cable geometry PRESETS drive analyze() ---
    rg58 = [coax.PRESETS[k] for k in coax.PRESETS if k.startswith("RG-58")]
    rg142 = [coax.PRESETS[k] for k in coax.PRESETS if k.startswith("RG-142")]
    check("PRESETS carry RG-58 and RG-142 with geometry + dielectric + note",
          len(rg58) == 1 and len(rg142) == 1 and all(
              {"a_m", "b_m", "eps_r", "tan_delta", "dielectric", "note"} <= set(p)
              and p["dielectric"] in coax.DIELECTRICS and p["note"]
              for p in rg58 + rg142))
    if rg58 and rg142:
        p58, p142 = rg58[0], rg142[0]
        r58 = coax.analyze(p58["a_m"], p58["b_m"], p58["eps_r"], p58["tan_delta"])
        check("RG-58 preset reproduces the gated 50.0 ohm / 101 pF/m",
              abs(r58["z0_ohm"] - 50.0) < 0.15
              and abs(r58["capacitance_pf_m"] - 101.0) < 2.0,
              "{0:.2f} ohm, {1:.1f} pF/m".format(r58["z0_ohm"],
                                                 r58["capacitance_pf_m"]))
        r142 = coax.analyze(p142["a_m"], p142["b_m"], p142["eps_r"],
                            p142["tan_delta"])
        check("RG-142 preset reproduces the honest 48.0 ohm / VF 70%",
              abs(r142["z0_ohm"] - 48.0) < 0.2
              and abs(r142["velocity_factor"] - 0.700) < 0.001,
              "{0:.2f} ohm".format(r142["z0_ohm"]))

    # --- §2 phase A (UI slice): single wire = litz analytics with ops=[] ---
    from emstudio.wire import litz, units

    d10 = units.awg_to_m(10)
    wire = litz.LitzConstruction(strand_diameter_m=d10, ops=[],
                                 name="Solid wire AWG 10")
    rdc = wire.rdc_per_meter()
    check("single wire (ops=[]) Rdc == 1/(sigma*A) exactly",
          abs(rdc - 1.0 / (litz.SIGMA_CU * math.pi * (d10 / 2.0) ** 2)) < 1e-15)
    check("AWG-10 solid Rdc matches the handbook 3.277 mohm/m",
          abs(rdc * 1e3 - 3.277) < 0.02, "{0:.4f} mohm/m".format(rdc * 1e3))
    # a lone conductor has NO other strands: Rac/Rdc must reduce to the exact
    # Kelvin isolated-round-wire solution (the internal proximity term vanishes)
    check("single-wire Rac/Rdc == exact Kelvin skin solution (no self-proximity)",
          all(abs(wire.ac_factor(f)
                  - litz.round_wire_ac_factor(f, d10 / 2.0)) < 1e-12
              for f in (1e3, 100e3, 1e6, 10e6)))
    check("single wire in a winding field still sees external proximity",
          wire.ac_factor(1e6, h_ext_per_amp=100.0) > wire.ac_factor(1e6))
    # multi-strand constructions are byte-identical (frozen v0.36 anchors)
    con2 = litz.make_type(2, units.awg_to_m(38), [20, 5])
    check("n>=2 ac_factor unchanged (Type-2 20x5 AWG38 regression anchors)",
          abs(con2.ac_factor(100e3) - 1.0119236849162556) < 1e-12
          and abs(con2.ac_factor(1e6) - 2.148308453330632) < 1e-12)
    ins = litz.LitzConstruction(strand_diameter_m=d10, ops=[], jacket="PVC",
                                jacket_m=0.8e-3, name="AWG 10 / PVC")
    check("insulated single wire: finished OD = d + 2*wall exactly",
          abs(ins.finished_od_m() - (d10 + 1.6e-3)) < 1e-15)
    check("AWG-10 DC ampacity estimate lands in the physical 20-60 A window",
          20.0 < ins.ampacity(1.0) < 60.0, "{0:.1f} A".format(ins.ampacity(1.0)))
    check("single-wire spec is honest (no litz-type row, wire title)",
          "solid wire" in ins.spec_markdown()
          and ins.spec_markdown().startswith("# Wire construction spec"))

    # ================= §2 phase B: twisted pair =================
    from emstudio.wire import twisted_pair as tp

    IN = 25.4e-3

    # exact two-wire kernel: s/d = 2 in air -> 157.926 ohm; the far-spacing
    # ln(2s/d) form is +5.26% here (documented reason we use acosh)
    za = tp.z0_diff_ohm(2.0, 1.0, 1.0)
    check("two-wire kernel: s/d=2 air = 157.926 ohm (exact acosh form)",
          abs(za - 157.926) < 0.02, "{0:.3f}".format(za))
    zln = (tp.ETA0 / math.pi) * math.log(4.0)
    check("far-spacing ln form is +5.26% at s/d=2 (why we use acosh)",
          abs((zln - za) / za - 0.0526) < 0.001)
    # TEM identities (exact by construction)
    e_id = 2.04
    z_id = tp.z0_diff_ohm(0.993e-3, 0.511e-3, e_id)
    check("TEM identity Z0 == sqrt(L'/C')",
          abs(z_id - math.sqrt(tp.inductance_h_m(0.993e-3, 0.511e-3)
                               / tp.capacitance_f_m(0.993e-3, 0.511e-3, e_id)))
          < 1e-9)
    check("TEM identity Z0 * v * C' == 1",
          abs(z_id * (tp.C0 / math.sqrt(e_id))
              * tp.capacitance_f_m(0.993e-3, 0.511e-3, e_id) - 1.0) < 1e-9)

    # Lefferson worked example (30 AWG Kynar, soft insulation, theta=30 deg):
    # q=1.15 (the documented q>1 regime), eps_eff=6.75, Z0 59.4-59.5 ohm
    d30, s30 = 0.010 * IN, 0.0195 * IN
    q30 = tp.q_factor(30.0, "soft")
    ee30 = tp.eps_effective(6.0, 30.0, "soft")
    z30 = tp.z0_diff_ohm(s30, d30, ee30)
    check("Lefferson example: q(30deg soft)=1.15, eps_eff=6.75",
          abs(q30 - 1.15) < 1e-12 and abs(ee30 - 6.75) < 1e-12)
    check("Lefferson example: Z0 = 59.4 ohm (printed 59.5)",
          abs(z30 - 59.43) < 0.6, "{0:.2f} ohm".format(z30))
    check("Lefferson example: VF = 0.385",
          abs(1.0 / math.sqrt(ee30) - 0.3849) < 0.002)
    t30 = math.tan(math.radians(30.0)) / (math.pi * s30)
    check("Lefferson example: required twist = 9.42 turns/inch",
          abs(t30 * IN - 9.42) < 0.05, "{0:.2f} tpi".format(t30 * IN))
    check("twist-angle round trip theta(T(theta)) exact",
          abs(tp.twist_angle_deg(t30, s30) - 30.0) < 1e-9)
    check("Lefferson example at 35 deg: Z0 = 53.4 ohm (printed 53.3)",
          abs(tp.z0_diff_ohm(s30, d30, tp.eps_effective(6.0, 35.0, "soft"))
              - 53.39) < 0.55)

    # DEGREES control (the model's dominant failure mode): Qucs-doc default
    # parameters evaluated degrees-correct = 89.03 ohm; the public radians bug
    # gives 94.90 — a gate matching 94.90 has reproduced the bug.
    th_d = tp.twist_angle_deg(100.0, 0.8e-3)
    ee_d = tp.eps_effective(4.0, th_d, "film")
    z_d = tp.z0_diff_ohm(0.8e-3, 0.5e-3, ee_d)
    check("degrees convention: theta=14.108 deg, q=0.3296, eps_eff=1.9888",
          abs(th_d - 14.1078) < 1e-3
          and abs(tp.q_factor(th_d, "film") - 0.329612) < 1e-5
          and abs(ee_d - 1.988836) < 1e-4)
    check("degrees convention: Z0 = 89.03 ohm, NOT the radians-bug 94.90",
          abs(z_d - 89.03) < 0.05 and abs(z_d - 94.90) > 1.0,
          "{0:.2f} ohm".format(z_d))
    # 45-deg film sanity that settled the units against measurement (~30%)
    red = 1.0 - math.sqrt(tp.eps_effective(3.0, 0.0) / tp.eps_effective(3.0, 45.0))
    check("45 deg film: 30.7% Z0 reduction (measured ~30%; radians give <0.1%)",
          abs(red - 0.307) < 0.005, "{0:.1%}".format(red))
    check("q>1 fit boundary: 43.30 deg (film) / 27.39 deg (soft), flagged",
          abs(math.sqrt(0.75 / 4e-4) - 43.30) < 0.01
          and abs(math.sqrt(0.75 / 1e-3) - 27.39) < 0.01
          and tp.analyze(d30, s30, 6.0, 0.0, t30, "soft")["q_exceeds_1"])

    # magnet-wire regression pin (1PEW 0.20 mm, 1 mm pitch) + Lefferson range
    th_g = tp.twist_angle_deg(1000.0, 235e-6)
    z_g = tp.z0_diff_ohm(235e-6, 200e-6, tp.eps_effective(5.6, th_g, "film"))
    check("magnet-wire pin: theta=36.44 deg -> Z0 = 32.64 ohm",
          abs(th_g - 36.437) < 0.01 and abs(z_g - 32.64) < 0.05,
          "{0:.2f} ohm".format(z_g))
    zs = [tp.z0_diff_ohm(0.75e-3, 0.644e-3, tp.eps_effective(3.5, t, "film"))
          for t in (9.0, 15.0, 25.0, 36.0)]
    check("Z0 falls monotonically with twist, inside Lefferson's 10-85 ohm",
          all(a > b for a, b in zip(zs, zs[1:]))
          and all(10.0 < z < 85.0 for z in zs))

    # Cat5e / Cat6 vs the primary datasheets (eps_eff from NVP 0.70 -> 2.041)
    p5 = tp.PRESETS["Cat5e U/UTP pair (24 AWG, PO)"]
    p6 = tp.PRESETS["Cat6 U/UTP pair (23 AWG, PO)"]
    r5 = tp.analyze(p5["d_m"], p5["s_m"], p5["eps_r"], p5["tan_delta"],
                    1.0 / p5["lay_m"], p5["insulation"], nvp=p5["nvp"])
    r6 = tp.analyze(p6["d_m"], p6["s_m"], p6["eps_r"], p6["tan_delta"],
                    1.0 / p6["lay_m"], p6["insulation"], nvp=p6["nvp"])
    check("Cat5e preset: Z0 in the fitted 100 +/- 15 ohm band (~107.7)",
          abs(r5["z0_diff_ohm"] - 107.74) < 0.6
          and 85.0 <= r5["z0_diff_ohm"] <= 115.0,
          "{0:.2f} ohm".format(r5["z0_diff_ohm"]))
    check("Cat5e long-lay OD variant (0.92 mm) = 100.2 ohm",
          abs(tp.z0_diff_ohm(0.92e-3, 0.511e-3, r5["eps_eff"]) - 100.18) < 0.6)
    check("Cat6 preset: Z0 = 99.9 ohm vs the 100 +/- 15 ohm band",
          abs(r6["z0_diff_ohm"] - 99.90) < 0.6,
          "{0:.2f} ohm".format(r6["z0_diff_ohm"]))
    check("Cat5e C' = 44.2 pF/m, within 15% of Belden's 49.2 (1 kHz value)",
          abs(r5["capacitance_pf_m"] - 44.2) < 0.5
          and abs(r5["capacitance_pf_m"] - 49.2) / 49.2 < 0.15)
    check("Cat5e/Cat6 VF = 0.70 (datasheet NVP window 0.65-0.72)",
          abs(r5["velocity_factor"] - 0.70) < 1e-9
          and 0.65 <= r6["velocity_factor"] <= 0.72)
    check("Cat5e attenuation @100 MHz <= the 22.0 dB/100m datasheet max, "
          "one-sided (smooth model, 55-100%)",
          0.55 * 22.0 <= r5["attenuation_db_100m"] <= 22.0,
          "{0:.1f} dB/100m".format(r5["attenuation_db_100m"]))
    check("Cat6 attenuation @100 MHz <= the 19.8 dB/100m max, one-sided",
          0.55 * 19.8 <= r6["attenuation_db_100m"] <= 19.8,
          "{0:.1f} dB/100m".format(r6["attenuation_db_100m"]))

    # shielded pair (RDRE thin-wire) vs Miller's EXACT capacitance anchors
    # (BSTJ 51(3) 1972 Table IV, air): documented thin-wire error growth
    for s_mm, D_mm, exact, tol, tag in (
            (10.0, 200.0, 358.34, 0.005, "d/s=0.1"),
            (5.0, 50.0, 272.60, 0.006, "d/s=0.2"),
            (2.5, 12.5, 179.72, 0.03, "d/s=0.4"),
            (1.6667, 5.5556, 116.84, 0.06, "d/s=0.6")):
        z_st = tp.z0_shielded_ohm(s_mm * 1e-3, 1e-3, D_mm * 1e-3, 1.0)
        check("shielded pair vs Miller exact {0}: {1:.1f} ohm".format(tag, exact),
              abs(z_st - exact) / exact < tol,
              "{0:.2f} ({1:+.2%})".format(z_st, (z_st - exact) / exact))
    check("shielded form matches the handbook 120*ln evaluation to 0.2%",
          abs(tp.z0_shielded_ohm(10e-3, 1e-3, 200e-3, 1.0) - 358.89) / 358.89
          < 0.002)
    check("shielded pair: homogeneous-dielectric 1/sqrt(eps) scaling exact",
          abs(tp.z0_shielded_ohm(2.5e-3, 1e-3, 12.5e-3, 2.3)
              - tp.z0_shielded_ohm(2.5e-3, 1e-3, 12.5e-3, 1.0)
              / math.sqrt(2.3)) < 1e-9)
    z_inf = tp.z0_shielded_ohm(10e-3, 1e-3, 10.0, 1.0)
    check("shield removal (D -> inf) recovers the open-pair ln form",
          abs(z_inf - (tp.ETA0 / math.pi) * math.log(20.0))
          / z_inf < 0.005)
    check("modes: Z_odd == Z_diff/2 (symmetric pair identity)",
          abs(r5["z0_odd_ohm"] - r5["z0_diff_ohm"] / 2.0) < 1e-12)
    check("thin-wire validity flagged when d/s > 0.4",
          tp.analyze(1e-3, 1.6667e-3, 1.0, 0.0, 0.0,
                     shield_id_m=5.5556e-3)["thin_wire_ok"] is False
          and r5["thin_wire_ok"])

    # shielded 120/78-ohm data-cable anchors via the datasheet C-VF identity
    # (their shield cavities are unpublished, so geometry can't be gated)
    pf_ft = 1e-12 / 0.3048
    check("120-ohm RS-485 cable identity: 1/(0.66c * 12.8 pF/ft) = 120.3 ohm",
          abs(tp.z0_from_c_vf(12.8 * pf_ft, 0.66) - 120.3) < 0.4)
    check("120-ohm foam-PE variant identity: 1/(0.78c * 11 pF/ft) = 118.5 ohm",
          abs(tp.z0_from_c_vf(11.0 * pf_ft, 0.78) - 118.5) < 0.4)
    check("78-ohm twinax identity: 1/(0.66c * 19.7 pF/ft) = 78.2; "
          "sqrt(L/C) = 78.0",
          abs(tp.z0_from_c_vf(19.7 * pf_ft, 0.66) - 78.2) < 0.4
          and abs(math.sqrt(0.12e-6 / 19.7e-12) - 78.0) < 0.1)

    check("length factor: 1/cos(theta), 1.0 untwisted, 1.155 at 30 deg",
          abs(tp.length_factor(0.0) - 1.0) < 1e-12
          and abs(tp.length_factor(30.0) - 1.0 / math.cos(math.radians(30.0)))
          < 1e-12)
    check("analyze() carries the report keys + consistent totals",
          {"z0_diff_ohm", "z0_odd_ohm", "eps_eff", "eps_eff_source",
           "theta_deg", "q", "velocity_factor", "capacitance_pf_m",
           "inductance_nh_m", "attenuation_db_100m"} <= set(r5)
          and abs(r5["attenuation_db_100m"] - r5["conductor_db_100m"]
                  - r5["dielectric_db_100m"]) < 1e-12
          and r5["eps_eff_source"] == "nvp")

    # ================= §2 phase C: bundle composer (geometric slice) ========
    from emstudio.wire import bundle as bn

    def _worst_gap(placed):
        w = 0.0
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                g = math.hypot(placed[i][0] - placed[j][0],
                               placed[i][1] - placed[j][1]) \
                    - (placed[i][2] + placed[j][2])
                w = min(w, g)
        return w

    # exact equal-circle anchors (after minimal-enclosing-circle recentering)
    for n_c, opt, tol in ((1, 1.0, 1e-9), (2, 2.0, 1e-6),
                          (3, 1.0 + 2.0 / math.sqrt(3.0), 1e-4),
                          (7, 3.0, 1e-6)):
        pl, r_enc = bn.pack_and_center([1.0] * n_c)
        check("packing: {0} equal members -> R = {1:.4f} exactly".format(
                  n_c, opt),
              _worst_gap(pl) >= -1e-8 and abs(r_enc - opt) / opt <= tol,
              "R = {0:.6f}".format(r_enc))
    pl4, r4 = bn.pack_and_center([1.0] * 4)
    check("packing: n=4 within the documented +15% of the optimal square",
          _worst_gap(pl4) >= -1e-8
          and 0.0 <= (r4 - (1.0 + math.sqrt(2.0))) / (1.0 + math.sqrt(2.0))
          <= 0.15, "R = {0:.4f} (opt 2.4142)".format(r4))
    pl7, r7 = bn.pack_and_center([1.0] * 7)
    check("packing: 7-hex fill factor = 7/9 exactly",
          abs(7.0 / r7 ** 2 - 7.0 / 9.0) < 1e-6)
    # invariants on unequal mixes: no overlap + containment + determinism
    for radii, tag in (([2.5, 1.5, 1.5, 0.8, 0.8, 0.8, 0.8], "cable mix"),
                       ([5.0] + [1.0] * 7, "1 big + 7 small"),
                       ([1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
                        "stairstep")):
        pl, r_enc = bn.pack_and_center(radii)
        check("packing invariants ({0}): no overlap, all inside R".format(tag),
              _worst_gap(pl) >= -1e-8
              and all(math.hypot(x, y) + r <= r_enc + 1e-8 for x, y, r in pl)
              and sum(r * r for _x, _y, r in pl) / r_enc ** 2 > 0.4)
    check("packing is deterministic + preserves input order",
          bn.pack_and_center([1.5, 1.0, 0.5]) == bn.pack_and_center(
              [1.5, 1.0, 0.5])
          and abs(bn.pack_circles([0.5, 2.0, 1.0])[1][2] - 2.0) < 1e-12)

    # Bundle roll-up: 7 x 2.5 mm members -> core OD 7.5 mm + jacket
    b7 = bn.Bundle(members=[bn.BundleMember("m", 2.5e-3, "wire", qty=7,
                                            weight_kg_m=0.01)],
                   jacket="PVC", jacket_m=1.0e-3, name="7-way")
    check("Bundle: 7 x 2.5 mm -> core OD 7.5 mm, finished 9.5 mm",
          abs(b7.core_od_m() - 7.5e-3) < 1e-8
          and abs(b7.od_m() - 9.5e-3) < 1e-8,
          "{0:.3f} / {1:.3f} mm".format(b7.core_od_m() * 1e3,
                                        b7.od_m() * 1e3))
    check("Bundle: weight roll-up + fill factor 7/9",
          abs(b7.weight_kg_m() - 0.07) < 1e-12
          and abs(b7.fill_factor() - 7.0 / 9.0) < 1e-6)
    check("twisted-pair member envelope = 2 s (rotating pair circle)",
          abs(bn.twisted_pair_envelope_m(0.993e-3) - 1.986e-3) < 1e-12)
    spec_b = b7.spec_markdown()
    check("Bundle spec carries OD/fill/members + the honest coupling note",
          "7.500 mm" in spec_b and "Fill factor" in spec_b
          and "RLGC/crosstalk" in spec_b)

    # ============ §2 optimization helpers: solve-for-Z0 ============
    # coax: exact inversion — RG-58 round trip + the 50-ohm design point
    b_rt = coax.b_for_z0(A_EFF, coax.coax_z0_ohm(A_EFF, B58, 2.25), 2.25)
    check("coax b_for_z0 round-trips the RG-58 geometry exactly",
          abs(b_rt - B58) < 1e-12)
    b50 = coax.b_for_z0(A_EFF, 50.0, 2.25)
    check("coax b_for_z0(50 ohm) lands on the RG-58 datasheet b (+-2 um)",
          abs(b50 - B58) < 2e-6, "{0:.4f} mm".format(b50 * 1e3))
    check("coax a_for_z0 inverse identity",
          abs(coax.a_for_z0(b50, 50.0, 2.25) - A_EFF) < 1e-12)
    # twisted pair: solve lay for the Lefferson worked-example Z0 -> 30 deg
    from emstudio.wire import twisted_pair as tp0

    z_tgt = tp0.z0_diff_ohm(0.0195 * 25.4e-3, 0.010 * 25.4e-3,
                            tp0.eps_effective(6.0, 30.0, "soft"))
    lay_s, th_s = tp0.lay_for_z0(z_tgt, 0.010 * 25.4e-3, 0.0195 * 25.4e-3,
                                 6.0, "soft")
    check("lay_for_z0 recovers the 30-deg Lefferson example (theta +-0.01)",
          abs(th_s - 30.0) < 0.01
          and abs(lay_s - math.pi * 0.0195 * 25.4e-3
                  / math.tan(math.radians(30.0))) < 1e-8,
          "theta {0:.3f} deg, lay {1:.3f} mm".format(th_s, lay_s * 1e3))
    r_chk = tp0.analyze(0.010 * 25.4e-3, 0.0195 * 25.4e-3, 6.0, 0.0,
                        1.0 / lay_s, "soft")
    check("lay_for_z0 round-trip through analyze()",
          abs(r_chk["z0_diff_ohm"] - z_tgt) < 0.01)
    try:
        tp0.lay_for_z0(1000.0, 0.010 * 25.4e-3, 0.0195 * 25.4e-3, 6.0, "soft")
        unreachable = False
    except ValueError:
        unreachable = True
    check("lay_for_z0 rejects unreachable targets (twist can't raise Z0)",
          unreachable)

    # ============ §2 phase C cont.: coupling matrices + crosstalk ============
    import numpy as np

    from emstudio.wire import coupling as cp

    MIL = 25.4e-6
    # Paul MTL 2e ribbon-cable benchmark (Tables 5.5/5.6, outer-wire ref):
    # wide-separation L must match the printed closed-form column exactly and
    # sit within the printed 1.38/2.04/2.04 % of the exact MoM matrix
    pos3 = [(0.0, 0.0), (50 * MIL, 0.0), (100 * MIL, 0.0)]
    rad3 = [7.5 * MIL] * 3
    L_ws = cp.widesep_l_matrix(pos3, rad3, ref=0)
    check("wide-sep L == Paul's printed 0.75885/0.51805/1.0361 uH/m",
          abs(L_ws[0][0] * 1e6 - 0.75885) < 5e-4
          and abs(L_ws[0][1] * 1e6 - 0.51805) < 5e-4
          and abs(L_ws[1][1] * 1e6 - 1.0361) < 1e-3)
    L_mom = np.array([[0.74850e-6, 0.50770e-6], [0.50770e-6, 1.0154e-6]])
    check("wide-sep L within 2.1% of Paul's exact MoM matrix",
          float(np.max(np.abs(L_ws - L_mom) / L_mom)) < 0.021)
    C_id = cp.c_matrix_from_l(L_ws)
    C_mom = np.array([[22.494e-12, -11.247e-12], [-11.247e-12, 16.581e-12]])
    check("C = mu0*eps0*inv(L) within 2.5% of Paul's MoM C0 (bare)",
          float(np.max(np.abs(C_id - C_mom) / np.abs(C_mom))) < 0.025)
    check("printed exact L*C0 = mu0*eps0*I (identity residual < 1e-3)",
          float(np.max(np.abs(L_mom @ C_mom
                              - cp.MU0 * cp.EPS0 * np.eye(2)))
                / (cp.MU0 * cp.EPS0)) < 1e-3)
    Lmid = cp.widesep_l_matrix(pos3, rad3, ref=1)
    check("middle-wire reference change: 0.7589/0.2408 uH/m (printed 12.4)",
          abs(Lmid[0][0] - Lmid[1][1]) < 1e-15
          and abs(Lmid[0][1] * 1e6 - 0.2408) < 2e-3)
    red_c = cp.reduce_generalized_c(
        [[26.2148, -18.0249, -5.03325], [-18.0249, 37.8189, -18.0249],
         [-5.03325, -18.0249, 26.2148]], ref=0)
    check("generalized->TL C reduction reproduces Table 5.5 (+-0.001 pF/m)",
          abs(red_c[0][0] - 37.4317) < 1e-3
          and abs(red_c[0][1] + 18.7158) < 1e-3
          and abs(red_c[1][1] - 24.9819) < 1e-3)
    check("datasheet mutual = -C_ij (row-sum convention)",
          abs(cp.maxwell_mutual_pf_m(C_mom, 0, 1) - 11.247) < 1e-3)
    # wide-separation validity boundary (Paul's printed two-wire error curve;
    # error defined exact-over-widesep, the book's denominator)
    e4 = math.log(4.0) / math.acosh(2.0) - 1.0
    e5 = math.log(5.0) / math.acosh(2.5) - 1.0
    check("wide-sep validity: +5.3% at s/rw=4, +2.7% at 5 (printed curve)",
          abs(e4 - 0.0526) < 0.002 and abs(e5 - 0.0272) < 0.002)
    cpl = cp.bundle_coupling_analytic(pos3, rad3, ref=0)
    check("bundle_coupling_analytic: ratio 6.67 -> widesep_ok, ref Rdc",
          cpl["widesep_ok"] and abs(cpl["min_s_over_rw"] - 50.0 / 7.5) < 1e-9
          and cpl["conductors"] == [1, 2]
          and abs(cpl["ref_r_dc_ohm_m"]
                  - 1.0 / (5.8e7 * math.pi * (7.5 * MIL) ** 2)) < 1e-9)
    check("touching bare wires flagged NOT widesep_ok",
          not cp.bundle_coupling_analytic(
              [(0.0, 0.0), (1.0e-3, 0.0)], [0.5e-3, 0.5e-3])["widesep_ok"])
    # partial -> loop transform (exact algebra; FastHenry-verified to 0.01%)
    zp = np.array([[4.0, 1.0, 0.5], [1.0, 5.0, 1.5], [0.5, 1.5, 6.0]])
    zl = cp.partial_to_loop(zp, ref=0)
    check("partial->loop transform algebra exact",
          abs(zl[0][0] - 7.0) < 1e-14 and abs(zl[0][1] - 4.0) < 1e-14
          and abs(zl[1][1] - 9.0) < 1e-14)

    # Paul's printed crosstalk worked example (MTL 2e sec. 10.3.1: lm/cm from
    # the ribbon tables, 2 m line, all terminations 50 ohm)
    xt = cp.crosstalk_weak(0.5077e-6, 18.716e-12, 2.0, 50.0, 50.0, 50.0, 50.0,
                           freq_hz=1e5, r_common_ohm_m=0.19444)
    check("crosstalk MNE = 5.5449 ns, MFE = -4.6091 ns (printed)",
          abs(xt["mne_s"] - 5.5449e-9) / 5.5449e-9 < 0.005
          and abs(xt["mfe_s"] + 4.6091e-9) / 4.6091e-9 < 0.005)
    check("crosstalk |VNE/VS| = -49.16 dB @ 100 kHz, -50.77 dB far end",
          abs(xt["vne_db"] + 49.16) < 0.05 and abs(xt["vfe_db"] + 50.77) < 0.05)
    check("trapezoid peaks: MNE/tau = 46.2 mV @ 120 ns (printed 45 +-5%), "
          "23.1 mV @ 240 ns (printed 23 +-3%)",
          abs(xt["mne_s"] / 120e-9 - 45e-3) / 45e-3 < 0.05
          and abs(xt["mne_s"] / 240e-9 - 23e-3) / 23e-3 < 0.03)
    check("common-impedance floor = 1.94 mV (printed)",
          abs(xt["common_impedance_floor"] - 1.945e-3) / 1.945e-3 < 0.01)
    check("dominance rule: 50-ohm ribbon is inductive x10.85 (eq. 10.31)",
          xt["inductive_dominant_ne"]
          and abs(xt["mne_inductive_s"] / xt["mne_capacitive_s"] - 10.85) < 0.1)
    # LearnEMC printed wire-over-ground examples (independent source; their
    # crosstalk is referenced to the aggressor LOAD voltage = VS*RL/(RS+RL))
    xt_i = cp.crosstalk_weak(67e-9 / 0.16, 0.0, 0.16, rs=10.0, rl=50.0,
                             rne=10.0, rfe=50.0, freq_hz=10e6)
    v_load_ref = xt_i["vfe_over_vs"] * (10.0 + 50.0) / 50.0
    check("LearnEMC inductive example: -23 dB @ 10 MHz (printed)",
          abs(20 * math.log10(v_load_ref) + 23.07) < 0.15,
          "{0:.2f} dB".format(20 * math.log10(v_load_ref)))
    # capacitive: coupling driven by the aggressor line voltage itself
    # (rs=0 makes the engine's RL/(RS+RL) factor 1); receptor 10 || 150 ohm
    xt_c = cp.crosstalk_weak(0.0, 3.6e-12 / 0.16, 0.16, rs=0.0, rl=50.0,
                             rne=10.0, rfe=150.0, freq_hz=50e6)
    check("LearnEMC capacitive example: -39.5 dB @ 50 MHz (printed -40), "
          "NE == FE when lm = 0",
          abs(xt_c["vne_db"] + 39.49) < 0.15
          and abs(xt_c["vne_over_vs"] - xt_c["vfe_over_vs"]) < 1e-15,
          "{0:.2f} dB".format(xt_c["vne_db"]))

    # ===== §2 extras: insulated-bundle C via MoM (Paul RIBBON.FOR method) =====
    # The homogeneous identity C = mu0*eps0*inv(L) is bare-only; this MoM solves
    # the inhomogeneous (insulated) electrostatic problem directly. Gated vs
    # Paul's printed ribbon-cable numbers + internal identities.
    from emstudio.wire import electrostatics as es

    # 3-wire ribbon, 7.5-mil radius, 10-mil PVC wall, eps_r 3.5 (Paul's case)
    ins = es.bundle_c_mom(pos3, rad3, er=3.5, wall=10 * MIL, ref=1, nf=10)
    c_tl_ins = ins["c_tl"] * 1e12
    check("MoM insulated-ribbon TL C reproduces Paul problem 5.15 "
          "(24.98 / -6.266 pF/m)",
          abs(c_tl_ins[0][0] - 24.98) < 0.01
          and abs(c_tl_ins[0][1] + 6.266) < 0.01
          and abs(c_tl_ins[1][1] - 24.98) < 0.01,
          "{0:.4f}/{1:.4f}".format(c_tl_ins[0][0], c_tl_ins[0][1]))
    # the generalized matrix the shipped reducer test hard-codes is now COMPUTED
    c_gen_ins = ins["c_generalized"] * 1e12
    check("MoM insulated generalized C matches the de-risk literals "
          "(26.2148 / -18.0249 / -5.0333)",
          abs(c_gen_ins[1][1] - 37.8189) < 5e-3
          and abs(c_gen_ins[0][0] - 26.2148) < 5e-3
          and abs(c_gen_ins[0][1] + 18.0249) < 5e-3
          and abs(c_gen_ins[0][2] + 5.0333) < 5e-3)
    # bare ribbon: MoM C + the identity must recover Paul's exact L (0.7485 /
    # 0.2408 uH/m, middle-wire reference) -- closes the C<->L loop
    bare = es.bundle_c_mom(pos3, rad3, ref=1, nf=10)
    L_from_c = cp.MU0 * es.EPS0 * np.linalg.inv(bare["c_tl"])
    check("MoM bare-ribbon C + identity recovers Paul's exact L "
          "(0.7485 / 0.2408 uH/m)",
          abs(L_from_c[0][0] * 1e6 - 0.7485) < 1e-3
          and abs(L_from_c[0][1] * 1e6 - 0.2408) < 1e-3)
    # insulation raises the per-entry effective permittivity 50-66% (Paul's
    # finding -- the exact reason the bare identity is wrong for insulated bundles)
    eps_eff = c_gen_ins[1][1] / (es.bundle_c_mom(pos3, rad3, ref=1,
                                                 nf=10)["c_generalized"][1][1]
                                 * 1e12)
    check("MoM center-wire eps_eff shift in Paul's 50-66% band",
          1.50 <= eps_eff <= 1.66, "{0:.4f}".format(eps_eff))
    # convergence: monotone + settled by nf=7 (entire-domain expansion)
    c7 = es.bundle_c_mom(pos3, rad3, er=3.5, wall=10 * MIL, ref=1,
                         nf=7)["c_tl"][0][0]
    c16 = es.bundle_c_mom(pos3, rad3, er=3.5, wall=10 * MIL, ref=1,
                          nf=16)["c_tl"][0][0]
    check("MoM Fourier convergence: nf=7 within 1e-4 of nf=16",
          abs(c7 - c16) / abs(c16) < 1e-4)
    # bare two-wire pair reproduces the exact acosh line capacitance
    s_pair = 4 * 7.5 * MIL * 1.6
    cg = es.generalized_c([{"x": 0, "y": 0, "rw": 7.5 * MIL},
                           {"x": s_pair, "y": 0, "rw": 7.5 * MIL}], nf=12)
    c_line = (cg[0][0] * cg[1][1] - cg[0][1] ** 2) / (cg[0][0] + cg[1][1]
                                                      + 2 * cg[0][1])
    c_acosh = math.pi * es.EPS0 / math.acosh(s_pair / (2 * 7.5 * MIL))
    check("MoM bare pair == exact acosh line capacitance (machine precision)",
          abs(c_line - c_acosh) / c_acosh < 1e-9)
    # er->1 insulated solver degenerates to the bare solver
    c_e1 = es.generalized_c([{"x": 0, "y": 0, "rw": 7.5 * MIL,
                              "er": 1.0 + 1e-12, "t": 10 * MIL},
                             {"x": s_pair, "y": 0, "rw": 7.5 * MIL,
                              "er": 1.0 + 1e-12, "t": 10 * MIL}], nf=12)
    check("MoM er->1 degenerates to the bare solve (< 1e-6)",
          float(np.max(np.abs(c_e1 - cg)) / np.max(np.abs(cg))) < 1e-6)
    # reciprocity on an asymmetric (triangular) insulated layout (sin harmonics)
    tri = es.generalized_c(
        [{"x": 0, "y": 0, "rw": 7.5 * MIL, "er": 3.5, "t": 10 * MIL},
         {"x": 50 * MIL, "y": 0, "rw": 7.5 * MIL, "er": 3.5, "t": 10 * MIL},
         {"x": 25 * MIL, "y": 43.3 * MIL, "rw": 7.5 * MIL, "er": 3.5,
          "t": 10 * MIL}], nf=10)
    check("MoM reciprocity on an asymmetric insulated triangle (< 1e-12)",
          float(np.max(np.abs(tri - tri.T))) < 1e-12)
    # INDEPENDENT printed anchors: RADC-TR-76-101 Vol II (GETCAP, US-gov public
    # domain — docs/upstream/radc-getcap-anchors.md). Normalized geometry
    # (r_c = 1); the report's period eps0 differs from CODATA in the 8th digit,
    # so compare C/eps0 ratios. Table 9: five-wire BARE TL matrix, sep = 10,
    # END wire reference, GETCAP at its printed precision.
    # (comparisons at 1e-6 relative: the report's period eps0 is only known to
    # ~3e-7, and the replay lands at ~4e-8 — the residual IS that uncertainty)
    pos5 = [(float(i * 10.0), 0.0) for i in range(5)]
    tl5 = es.bundle_c_mom(pos5, [1.0] * 5, ref=0, nf=10)["c_tl"]
    eps0_1976 = 8.854185e-12
    t9 = {(0, 0): 18.87646053717670, (0, 1): -6.851495768047740,
          (0, 2): -2.129410716129314, (0, 3): -1.843114316184374,
          (1, 1): 19.14682911214455, (1, 2): -6.851495768052782,
          (1, 3): -2.721918788019494, (2, 2): 18.87646053717669,
          (2, 3): -8.052439733815269,   # smudged 9th digit = 3, replay-confirmed
          (3, 3): 14.81610887311056}
    worst_t9 = max(abs(tl5[i][j] / es.EPS0 - v * 1e-12 / eps0_1976)
                   / abs(v * 1e-12 / eps0_1976) for (i, j), v in t9.items())
    check("MoM five-wire bare TL matrix matches RADC GETCAP Table 9 "
          "(<= 1e-6 relative, eps0-normalized)", worst_t9 <= 1e-6,
          "worst {0:.1e}".format(worst_t9))
    # Table 8: the SAME NF truncation must reproduce GETCAP's printed NF=5
    # value at the near-touching sep = 2.5 (truncation-behavior identity)
    g2 = es.generalized_c([{"x": 0.0, "y": 0.0, "rw": 1.0},
                           {"x": 2.5, "y": 0.0, "rw": 1.0}],
                          nf=5, use_sin=False)
    c_line2 = (g2[0][0] * g2[1][1] - g2[0][1] ** 2) / (g2[0][0] + g2[1][1]
                                                       + 2 * g2[0][1])
    check("MoM NF=5 truncation reproduces GETCAP Table 8 (sep 2.5: "
          "40.08222 pF/m, eps0-normalized)",
          abs(c_line2 / es.EPS0 - 40.08222038915016e-12 / eps0_1976)
          / (40.08222038915016e-12 / eps0_1976) <= 1e-6)

    # ===== §2 extras: differential pair-to-pair coupling (mixed-mode) =====
    # De-risked 2026-07-12: RADC-TR-76-101 Vol V equations verified on page
    # images; congruence algebra adversarially verified (44/44, <= 1e-13);
    # 12-digit anchors from an independent full-MTL 8x8 chain-matrix oracle.
    from emstudio.wire import mixed_mode as mmx

    tv, ti = mmx.mixed_mode_transforms()
    # pinned LITERALS (not recomputed from the implementation — a mutated
    # transform must fail here): T_V rows (1,-1),(1/2,1/2) per pair and its
    # congruence partner T_I = (T_V^-1)^T rows (1/2,-1/2),(1,1)
    tv_exp = np.array([[1.0, -1.0, 0.0, 0.0], [0.5, 0.5, 0.0, 0.0],
                       [0.0, 0.0, 1.0, -1.0], [0.0, 0.0, 0.5, 0.5]])
    ti_exp = np.array([[0.5, -0.5, 0.0, 0.0], [1.0, 1.0, 0.0, 0.0],
                       [0.0, 0.0, 0.5, -0.5], [0.0, 0.0, 1.0, 1.0]])
    check("mixed-mode transforms match the pinned literals (congruence "
          "pair T_I = (T_V^-1)^T)",
          float(np.max(np.abs(tv - tv_exp))) < 1e-15
          and float(np.max(np.abs(ti - ti_exp))) < 1e-15
          and float(np.max(np.abs(mmx.pair_transform(2) - tv_exp))) < 1e-15)

    # oracle geometry: ref (0,0); A (0,10)+(2,10) mm; B (20,10)+(22,10) mm
    posx = [(0.0, 0.0), (0.0, 10e-3), (2e-3, 10e-3),
            (20e-3, 10e-3), (22e-3, 10e-3)]
    radx = [0.5e-3] * 5
    L4 = cp.widesep_l_matrix(posx, radx, ref=0)
    C4 = cp.c_matrix_from_l(L4)
    mmats = mmx.mixed_mode_matrices(L4, C4)
    check("L_mm / C_mm symmetric + homogeneous identity L_mm@C_mm = "
          "mu0*eps0*I",
          float(np.max(np.abs(mmats["l_mm"] - mmats["l_mm"].T))
                / np.max(np.abs(mmats["l_mm"]))) < 1e-15
          and float(np.max(np.abs(mmats["c_mm"] - mmats["c_mm"].T))
                    / np.max(np.abs(mmats["c_mm"]))) < 1e-15
          and float(np.max(np.abs(mmats["l_mm"] @ mmats["c_mm"]
                                  - cp.MU0 * cp.EPS0 * np.eye(4)))
                    / (cp.MU0 * cp.EPS0)) < 1e-12)
    dq = mmx.diff_pair_coupling(L4, C4)
    check("endpoint identities: Ldd = L11+L22-2L12, Mdd = L13-L14-L23+L24, "
          "Cdd_AB = (C13-C14-C23+C24)/4 (machine)",
          abs(dq["ldd_a"] - (L4[0][0] + L4[1][1] - 2 * L4[0][1])) < 1e-22
          and abs(dq["mdd"] - (L4[0][2] - L4[0][3] - L4[1][2] + L4[1][3]))
          < 1e-22
          and abs(dq["cdd_ab"] - (C4[0][2] - C4[0][3] - C4[1][2]
                                  + C4[1][3]) / 4.0) < 1e-26)
    # reference cancellation closed forms (wide-separation): Ldd depends only
    # on the pair's own geometry; Mdd is the pure distance ratio
    check("reference cancellation: Ldd == (mu0/2pi) ln(s^2/rw^2) exactly",
          abs(dq["ldd_a"] - 2e-7 * math.log((2e-3 / 0.5e-3) ** 2)) < 1e-20
          and abs(dq["ldd_b"] - dq["ldd_a"]) < 1e-20)
    mdd_cf = 2e-7 * math.log((22.0 * 18.0) / (20.0 * 20.0))
    check("Mdd closed form (mu0/2pi) ln(d14 d23/(d13 d24)) = "
          "-2.010067171 nH/m (oracle)",
          abs(dq["mdd"] - mdd_cf) < 1e-20
          and abs(dq["mdd"] + 2.010067171e-9) / 2.010067171e-9 < 1e-9)
    check("Cdd_AB = +86.23466 fF/m and CUPP = -344.939 fF/m (oracle values)",
          abs(dq["cdd_ab"] - 8.623466491e-14) / 8.623466491e-14 < 1e-6
          and abs(dq["cupp_f_m"] + 3.449386596e-13) / 3.449386596e-13 < 1e-6)
    check("polarity normalization: flip makes lm >= 0 AND cm > 0 here",
          dq["polarity_flipped"] and abs(dq["lm_h_m"] - 2.010067171e-9)
          / 2.010067171e-9 < 1e-9
          and abs(dq["cm_f_m"] - 8.623466491e-14) / 8.623466491e-14 < 1e-6)
    # closed-form recompute from raw geometry (mu0/2pi cancels), independent
    # of the engine's Ldd/Mdd values: k = ln(396/400)/ln(16)
    check("k_diff == ln(396/400)/ln(16) = -3.6249e-3 (closed form), |k| <= 1",
          abs(dq["k_diff"] - math.log(396.0 / 400.0) / math.log(16.0)) < 1e-15
          and abs(dq["k_diff"]) <= 1.0)

    # weak-coupling engine vs the full-MTL 8x8 oracle (12-digit anchors,
    # 2 m line, 100-ohm differential terminations = 50 ohm/wire)
    xt1 = mmx.diff_crosstalk(L4, C4, 2.0, 100.0, 100.0, 100.0, 100.0,
                             freq_hz=1e5)
    check("diff NE vs full-MTL oracle @100 kHz: 9.024880838e-6 "
          "(-100.891 dB), weak within 0.05%",
          abs(xt1["untwisted"]["vne_over_vs"] - 9.024880838492e-06)
          / 9.024880838492e-06 < 5e-4)
    check("diff FE vs full-MTL oracle @100 kHz: 3.606597792e-6 "
          "(-108.858 dB), weak within 0.1%",
          abs(xt1["untwisted"]["vfe_over_vs"] - 3.606597792280e-06)
          / 3.606597792280e-06 < 1e-3)
    check("transfer coefficients: MNE = 14.36207 ps (ind 10.05034 + "
          "cap 4.311733), oracle",
          abs(xt1["untwisted"]["mne_s"] - 1.436207e-11) / 1.436207e-11 < 1e-5
          and abs(xt1["untwisted"]["mne_inductive_s"] - 1.005034e-11)
          / 1.005034e-11 < 1e-5
          and abs(xt1["untwisted"]["mne_capacitive_s"] - 4.311733e-12)
          / 4.311733e-12 < 1e-5)
    xt2 = mmx.diff_crosstalk(L4, C4, 2.0, 100.0, 100.0, 100.0, 100.0,
                             freq_hz=1e6)
    check("diff NE/FE vs oracle @1 MHz within the weak-model 1%/2.5% class",
          abs(xt2["untwisted"]["vne_over_vs"] - 9.101022320356e-05)
          / 9.101022320356e-05 < 0.01
          and abs(xt2["untwisted"]["vfe_over_vs"] - 3.682904470188e-05)
          / 3.682904470188e-05 < 0.025)
    check("balanced diff-diff circuit has no common-impedance floor",
          xt1["untwisted"]["common_impedance_floor"] == 0.0)

    # symmetric isolated pair: mode invariants (machine-exact by eigenmodes)
    posp = [(0.0, 0.0), (-2.5e-3, 50e-3), (2.5e-3, 50e-3)]
    L2 = cp.widesep_l_matrix(posp, [0.5e-3] * 3, ref=0)
    C2 = cp.c_matrix_from_l(L2)
    l_odd = L2[0][0] - L2[0][1]
    c_odd = C2[0][0] - C2[0][1]
    ldd2 = L2[0][0] + L2[1][1] - 2 * L2[0][1]
    cdd2 = (C2[0][0] + C2[1][1] - 2 * C2[0][1]) / 4.0
    z_odd = math.sqrt(l_odd / c_odd)
    z_dd = math.sqrt(ldd2 / cdd2)
    check("invariant Zdd == 2*Zodd (symmetric pair)",
          abs(z_dd - 2.0 * z_odd) / z_dd < 1e-12)
    check("invariant Ldd*Cdd == Lodd*Codd == mu0*eps0 (matched pairs only)",
          abs(ldd2 * cdd2 - cp.MU0 * cp.EPS0) / (cp.MU0 * cp.EPS0) < 1e-12
          and abs(l_odd * c_odd - cp.MU0 * cp.EPS0)
          / (cp.MU0 * cp.EPS0) < 1e-12)
    check("factor traps: Ldd*Codd = 2 mu0eps0, Lodd*Cdd = mu0eps0/2 "
          "(definitions must not be mixed)",
          abs(ldd2 * c_odd - 2.0 * cp.MU0 * cp.EPS0)
          / (cp.MU0 * cp.EPS0) < 1e-12
          and abs(l_odd * cdd2 - 0.5 * cp.MU0 * cp.EPS0)
          / (cp.MU0 * cp.EPS0) < 1e-12)

    # geometric selectivity (the physics of differential rejection): pair B
    # placed mirror-symmetric about pair A's plane, reference ON the plane ->
    # Mdd and Cdd_AB null identically; breaking symmetry un-nulls Mdd
    posn = [(-10e-3, 10e-3), (0.0, 10e-3), (2e-3, 10e-3),
            (20e-3, 9e-3), (20e-3, 11e-3)]
    Ln = cp.widesep_l_matrix(posn, radx, ref=0)
    Cn = cp.c_matrix_from_l(Ln)
    dn = mmx.diff_pair_coupling(Ln, Cn)
    check("mirror-symmetric pair B + on-plane reference: Mdd = Cdd = 0 "
          "identically",
          abs(dn["mdd"]) < 1e-20 and abs(dn["cdd_ab"]) < 1e-24)
    posb = [(-10e-3, 10e-3), (0.0, 10e-3), (2e-3, 10e-3),
            (20e-3, 9e-3), (20e-3, 11.5e-3)]
    db = mmx.diff_pair_coupling(
        cp.widesep_l_matrix(posb, radx, ref=0),
        cp.c_matrix_from_l(cp.widesep_l_matrix(posb, radx, ref=0)))
    check("0.5 mm symmetry break un-nulls: Mdd = -72.64 pH/m (oracle)",
          abs(db["mdd"] + 7.264e-11) / 7.264e-11 < 1e-3)

    # twist model (RADC Vol V, page-image-verified): eq 4-3 parity algebra
    # exact at the report's own N = 226/225; lay round-trip; factor semantics
    check("eq 4-3/4-6 sums: XI_TWP(226) = 0, XI_TWP(225) = 1, "
          "XI_SWP(226) = 226 (the report's loop counts)",
          mmx.xi_twp(226) == 0 and mmx.xi_twp(225) == 1
          and mmx.xi_swp(226) == 226)
    check("half_twists_from_lay: 1 m at 100 mm lay -> N = 20",
          mmx.half_twists_from_lay(1.0, 0.1) == 20)
    fi_b, fc_b, w_b = mmx.twist_factors(21, "balanced")
    fi_u, fc_u, w_u = mmx.twist_factors(21, "unbalanced_single_ground")
    fi_g, fc_g, w_g = mmx.twist_factors(21, "unbalanced_ground_loop")
    check("twist factors: balanced 1/N both; unbalanced keeps the capacitive "
          "floor (4-8/4-10); ground loop keeps everything",
          abs(fi_b - 1.0 / 21) < 1e-15 and abs(fc_b - 1.0 / 21) < 1e-15
          and not w_b
          and abs(fi_u - 1.0 / 21) < 1e-15 and fc_u == 1.0 and w_u
          and fi_g == 1.0 and fc_g == 1.0 and w_g)
    # balanced twist: both couplings scale 1/N -> improvement is EXACTLY
    # 20 log10(N) regardless of the inductive/capacitive mix
    xtb = mmx.diff_crosstalk(L4, C4, 2.0, 100.0, 100.0, 100.0, 100.0,
                             freq_hz=1e5, n_half_twists=21,
                             receptor="balanced")
    check("balanced twist improvement == 20 log10(N) exactly (26.444 dB "
          "at N = 21)",
          abs(xtb["improvement_ne_db"] - 20.0 * math.log10(21.0)) < 1e-9
          and abs(xtb["improvement_fe_db"]
                  - 20.0 * math.log10(21.0)) < 1e-9)
    # unbalanced receptor at the oracle's 100-ohm terminations: inductive
    # residue 1/21 + full capacitive floor -> 9.54 dB, inside the report's
    # printed 10.25 dB +/- 3 dB soft band (50-ohm-class loads, low-Z regime)
    xtu = mmx.diff_crosstalk(L4, C4, 2.0, 100.0, 100.0, 100.0, 100.0,
                             freq_hz=1e5, n_half_twists=21,
                             receptor="unbalanced_single_ground")
    check("unbalanced low-Z twist benefit = 9.54 dB, in the RADC "
          "10.25 +/- 3 dB soft band",
          abs(xtu["improvement_ne_db"] - 9.5385) < 0.05
          and 7.25 <= xtu["improvement_ne_db"] <= 13.25)
    # high-impedance (1 kohm) unbalanced: capacitively dominated -> twist
    # buys ~nothing (report: "no effect for high impedance loads", 0 +/- 3 dB)
    xth = mmx.diff_crosstalk(L4, C4, 2.0, 1000.0, 1000.0, 1000.0, 1000.0,
                             freq_hz=1e5, n_half_twists=21,
                             receptor="unbalanced_single_ground")
    check("unbalanced high-Z (1 kohm) twist benefit <= 3 dB (report ~0, "
          "soft band)",
          0.0 <= xth["improvement_ne_db"] <= 3.0
          and not xth["untwisted"]["inductive_dominant_ne"])
    check("ground-loop mode: no improvement + warning",
          mmx.diff_crosstalk(L4, C4, 2.0, freq_hz=1e5, n_half_twists=21,
                             receptor="unbalanced_ground_loop")
          ["improvement_ne_db"] == 0.0 and w_g)

    # MoM insulated C feeds the same reduction: mirror-null survives the
    # inhomogeneous solve; insulation raises the intra-pair diff capacitance
    ci_n = es.bundle_c_mom(posn, radx, er=3.5, wall=0.3e-3, ref=0,
                           nf=10)["c_tl"]
    di_n = mmx.diff_pair_coupling(Ln, ci_n)
    cb_n = mmx.diff_pair_coupling(Ln, cp.c_matrix_from_l(Ln))
    check("MoM insulated C: mirror-symmetric CUPP still nulls (< 1 fF/m) "
          "and Cdd_A rises vs bare",
          abs(di_n["cupp_f_m"]) < 1e-15
          and di_n["cdd_a"] > cb_n["cdd_a"] * 1.2)

    if FAILURES:
        print("CABLE GATE FAILED: {0}".format(FAILURES))
        return 1
    print("CABLE GATE PASSED")
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
        raise SystemExit("cable validation failed")
    sys.exit(0)
