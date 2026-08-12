# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: cable thermal / temperature-rise engine (§2 thermal slice).

Pass: exit 0 and 'THERMAL GATE PASSED'. Pure python3 (no solver, no FreeCAD).

Anchors from the 2026-07-12 de-risk workflow, adversarially recomputed
(60/61, two corrections BAKED IN here): IEC 60287-2-1 T1 worked examples
(QuickField 0.8166061945 — the printed 0.816 is a TRUNCATION, round() gives
0.817, so the gate pins the full-precision value, NOT round()==0.816; E3S
HTRSE-2018 0.4325954273 / KA 0.116); Cengel Ex 9-1 + AHTT Ex 8.4 with each
example's OWN printed film properties injected; AHTT Table A.6 air rows;
IEC 60949 / BS 7671 adiabatic constants and the recomputed 630 mm² rows;
IEC 60853-2 / 60287-1-1 property constants; NEC 310.15(C)(1) exact factors;
ampacity BANDS (NEC 310.17 ±25 %, Multicable ±25 %, MIL-W-5088L §6.7 text
points ±15 %, NASA 1-atm ±15 % soft); the coax dissipation and ½-dielectric
identities (exact) and the Times LMR-240 catalog table (90-125 % with the
datasheet attenuation split and pinned constants — k_foam 0.13 is a DERIVED
parameter, never tuned to centre the band).
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
    from emstudio.wire import thermal as th

    print("EMStudio thermal (§2 thermal slice) validation gate")

    # ============ A. radial conduction (IEC 60287-2-1) ============
    t1_qf = th.layer_t_k_m_w(1.0 / 0.182, 33.7e-3, 26.02e-3)
    check("QuickField HV XLPE worked example: T1 = 0.8166061945 K.m/W "
          "(printed 0.816 is a truncation — round() gives 0.817)",
          abs(t1_qf - 0.8166061944818844) < 1e-9
          and round(t1_qf, 3) == 0.817, "{0:.10f}".format(t1_qf))
    t1_e3s = th.layer_t_k_m_w(5.0, 7.2e-3, 2.6e-3)
    ka = math.pi * 0.0124 * 6.865 * t1_e3s
    check("E3S LV PVC worked example: T1 = 0.4325954273, KA = 0.116",
          abs(t1_e3s - 0.43259542732872325) < 1e-9
          and round(ka, 3) == 0.116 and abs(ka - 0.11568952) < 1e-5)
    d_in, t_w = 9.4e-3, 1.7e-3
    check("ln(1 + 2t/D) == ln(D_out/D_in) identity + thin-wall limit "
          "rho*t/(pi*D)",
          abs(th.layer_t_k_m_w(3.5, d_in, t_w)
              - 3.5 / (2 * math.pi) * math.log((d_in + 2 * t_w) / d_in))
          < 1e-15
          and abs(th.layer_t_k_m_w(5.0, 10e-3, 1e-6)
                  / (5.0 * 1e-6 / (math.pi * 10e-3)) - 1.0) < 5e-4)
    check("IEC 60287-2-1 Table 1 resistivities: PVC 5/6, PE/XLPE/EPR 3.5, "
          "paper 6; PTFE band 2.9-4.2 (datasheet, default 4.0)",
          th.RHO_THERMAL["PVC"] == 5.0
          and th.RHO_THERMAL["PVC (>3 kV)"] == 6.0
          and th.RHO_THERMAL["PE"] == 3.5 and th.RHO_THERMAL["XLPE"] == 3.5
          and th.RHO_THERMAL["EPR"] == 3.5
          and th.RHO_THERMAL["paper (mass-impregnated)"] == 6.0
          and th.RHO_THERMAL["PTFE"] == 4.0)
    check("material normalization: UI vocabulary -> table keys, unknown "
          "-> None (never a silent PVC substitution in the engine)",
          th.normalize_material("enamel") == "enamel"
          and th.normalize_material("silicone") == "silicone rubber"
          and th.normalize_material("polyethylene") == "PE"
          and th.normalize_material("PVC") == "PVC"
          and th.normalize_material("Frobnium-42") is None)

    class _FakeCon(object):
        def __init__(self, jacket, wall):
            self.jacket, self.jacket_m = jacket, wall

        def bundle_diameter_m(self):
            return 2.0e-3

    d_fc, lay_fc, w_fc = th.layers_from_construction(
        _FakeCon("silicone", 0.5e-3))
    d_fu, lay_fu, w_fu = th.layers_from_construction(
        _FakeCon("mystery goo", 0.5e-3))
    check("layers_from_construction: silicone maps to its own table entry "
          "silently; unknown jackets fall back to PVC WITH a warning",
          d_fc == 2.0e-3 and lay_fc[0]["name"] == "silicone rubber"
          and not w_fc and lay_fu[0]["name"] == "PVC" and len(w_fu) == 1)
    cu, al = th.CONDUCTORS["Cu"], th.CONDUCTORS["Al"]
    check("IEC 60287-1-1 conductor constants: Cu 1.7241e-8 / 0.00393 / "
          "3.45e6; Al 2.8264e-8 / 0.00403 / 2.5e6",
          cu["rho20"] == 1.7241e-8 and cu["alpha20"] == 0.00393
          and cu["qv"] == 3.45e6 and al["rho20"] == 2.8264e-8
          and al["alpha20"] == 0.00403 and al["qv"] == 2.5e6)
    check("insulation volumetric heat capacities (IEC 60853-2): PVC 1.7e6, "
          "PE/XLPE 2.4e6, EPR 2.0e6",
          th.QV_INSULATION["PVC"] == 1.7e6
          and th.QV_INSULATION["PE"] == 2.4e6
          and th.QV_INSULATION["XLPE"] == 2.4e6
          and th.QV_INSULATION["EPR"] == 2.0e6)
    check("temperature classes: PVC 70/80/105, XLPE 90, PTFE 200 (MIL), "
          "silicone 180, enamel A105..R220 (IEC 60085 — no letter above R)",
          th.TEMP_CLASSES["PVC 70 °C (IEC 60502-1)"] == 70.0
          and th.TEMP_CLASSES["PVC 80 °C (UL 1007)"] == 80.0
          and th.TEMP_CLASSES["PVC 105 °C (UL 1015)"] == 105.0
          and th.TEMP_CLASSES["PE / XLPE 90 °C (IEC 60502-1)"] == 90.0
          and th.TEMP_CLASSES["PTFE 200 °C (MIL-DTL-16878/4)"] == 200.0
          and th.TEMP_CLASSES["Silicone 180 °C (class H)"] == 180.0
          and th.TEMP_CLASSES["Enamel class A 105 °C"] == 105.0
          and th.TEMP_CLASSES["Enamel class R 220 °C"] == 220.0
          and not any("S 240" in k for k in th.TEMP_CLASSES))

    # ============ B. surface dissipation (Churchill-Chu) ============
    # Cengel Ex 9-1 (D=8 cm, 70/20 C, L=6 m) with the book's printed film
    # properties injected (Tf=318 K): Ra 1.869e6, Nu 17.40, h 5.869,
    # Q 443 W, radiation (eps=1) 553 W
    props_cengel = (0.02699, 1.749e-5, 1.749e-5 / 0.7241, 0.7241)
    sh = th.surface_h(0.08, 70.0, 20.0, props=props_cengel)
    q_conv = sh["h_w_m2k"] * math.pi * 0.08 * 6.0 * 50.0
    q_rad = 1.0 * th.SIGMA_SB * math.pi * 0.08 * 6.0 * (343.0 ** 4
                                                        - 293.0 ** 4)
    check("Cengel Ex 9-1: Ra = 1.869e6, Nu = 17.40, h = 5.869 W/m2K "
          "(printed props injected)",
          abs(sh["ra"] - 1.869e6) / 1.869e6 < 2e-3
          and abs(sh["nu"] - 17.40) / 17.40 < 2e-3
          and abs(sh["h_w_m2k"] - 5.869) / 5.869 < 2e-3,
          "Ra {0:.4g} Nu {1:.4g} h {2:.4g}".format(sh["ra"], sh["nu"],
                                                   sh["h_w_m2k"]))
    check("Cengel Ex 9-1: Q_conv = 443 +- 2 W, Q_rad(eps=1) = 553 +- 1 W",
          abs(q_conv - 442.6) < 2.0 and abs(q_rad - 553.3) < 1.0,
          "{0:.1f} / {1:.1f} W".format(q_conv, q_rad))
    # AHTT Ex 8.4 (D=5 mm fine wire, 127/27 C) printed props (Tf=350 K,
    # v5-era values); 1-g h = 13.84 W/m2K; CC bracket 0.9265
    props_ahtt = (0.0297, 2.073e-5, 2.93e-5, 0.707)
    sh2 = th.surface_h(0.005, 127.0, 27.0, props=props_ahtt)
    bracket = 0.387 * (sh2["ra"] / (1.0 + (0.559 / 0.707) ** (9.0 / 16.0))
                       ** (16.0 / 9.0)) ** (1.0 / 6.0)
    check("AHTT Ex 8.4 (low-Ra fine-wire regime): 1-g h = 13.84 W/m2K, "
          "CC bracket 0.9265",
          abs(sh2["h_w_m2k"] - 13.841) < 0.1 and abs(bracket - 0.9265) < 5e-3,
          "h {0:.3f}, bracket {1:.4f}".format(sh2["h_w_m2k"], bracket))
    check("AHTT Table A.6 air rows exact at 300/350/400/500 K nodes",
          th.air_properties(300.0) == (0.0264, 1.575e-5, 2.23e-5, 0.707)
          and th.air_properties(350.0) == (0.0300, 2.069e-5, 2.95e-5, 0.702)
          and th.air_properties(400.0) == (0.0335, 2.613e-5, 3.74e-5, 0.699)
          and th.air_properties(500.0) == (0.0399, 3.839e-5, 5.50e-5, 0.698))
    k325 = th.air_properties(325.0)[0]
    check("air table interpolation: k(325 K) midway between the 320/330 rows",
          abs(k325 - 0.5 * (0.0279 + 0.0286)) < 1e-12)
    check("polymer jacket emissivity defaults inside [0.88, 0.95]",
          all(0.88 <= th.EMISSIVITY[k] <= 0.95
              for k in ("PVC", "PE", "PTFE", "polyester tape", "enamel")))
    # Morgan power-law cross-check (oracle): CC within +-25% over the cable
    # regime (Ra bands and constants printed in Morgan 1975 / Energies 2021)
    morgan = ((1e-2, 1e2, 1.02, 0.148), (1e2, 1e4, 0.850, 0.188),
              (1e4, 1e7, 0.480, 0.250))
    ok_m = True
    for d_mm, dt in ((1.0, 30.0), (5.0, 40.0), (20.0, 30.0), (50.0, 30.0)):
        s = th.surface_h(d_mm * 1e-3, 25.0 + dt, 25.0)
        for lo, hi, c_m, n_m in morgan:
            if lo <= s["ra"] < hi:
                nu_m = c_m * s["ra"] ** n_m
                ok_m = ok_m and abs(s["nu"] - nu_m) / nu_m < 0.25
    check("Churchill-Chu within +-25% of the Morgan bands over D 1-50 mm",
          ok_m)
    h1 = th.surface_h(1e-3, 55.0, 25.0)["h_w_m2k"]
    h50 = th.surface_h(50e-3, 55.0, 25.0)["h_w_m2k"]
    h012 = th.surface_h(0.12e-3, 65.0, 25.0)["h_w_m2k"]
    check("small-wire h bands: 1 mm/30 K in [24,34]; 50 mm in [5,6.5]; "
          "0.12 mm soft [60,180] W/m2K",
          24.0 <= h1 <= 34.0 and 5.0 <= h50 <= 6.5 and 60.0 <= h012 <= 180.0,
          "{0:.1f} / {1:.2f} / {2:.0f}".format(h1, h50, h012))

    # ============ B2. the CFD bundle factor ============
    # Churchill-Chu is exact for an ISOLATED cylinder and wrong for a BUNDLE in
    # an ENCLOSURE. emstudio/solvers/openfoam/bundle.py measures that error;
    # this is the seam that carries it into the ampacity answer.
    h_bare = th.surface_h(0.02, 60.0, 30.0)
    h_bund = th.surface_h(0.02, 60.0, 30.0, bundle_factor=0.80)
    check("the bundle factor scales h exactly, and defaults to a no-op",
          abs(h_bund["h_w_m2k"] / h_bare["h_w_m2k"] - 0.80) < 1e-12
          and h_bare["bundle_factor"] == 1.0,
          "%.6f -> %.6f" % (h_bare["h_w_m2k"], h_bund["h_w_m2k"]))
    # ⚠ Ra describes the FLOW, not the bundling. Scaling it would corrupt the
    # regime diagnostics (ra_in_range) while looking harmless.
    check("Ra is NOT scaled by the bundle factor — it is a property of the "
          "flow, not of the arrangement",
          abs(h_bund["ra"] - h_bare["ra"]) < 1e-9)
    check("Nu and h stay self-consistent under scaling (Nu = h D / k)",
          abs(h_bund["nu"] / h_bare["nu"] - 0.80) < 1e-12)
    for bad in (0.0, -0.5):
        try:
            th.surface_h(0.02, 60.0, 30.0, bundle_factor=bad)
            check("a non-positive bundle factor (%g) is rejected" % bad, False)
        except ValueError:
            check("a non-positive bundle factor (%g) is rejected" % bad, True)
    # The factor must reach the ANSWER, not just the film coefficient.
    _lay = [{"name": "PVC", "t_m": 0.001}]
    s_bare = th.solve_steady(40.0, 0.0026, _lay, 3.3e-3, tamb_c=30.0)
    s_bund = th.solve_steady(40.0, 0.0026, _lay, 3.3e-3, tamb_c=30.0,
                             bundle_factor=0.80,
                             bundle_provenance="OpenFOAM trefoil 3x20 mm")
    check("a bundle factor RAISES the conductor temperature (less cooling), "
          "and by a sane amount",
          0.5 < s_bund["t_conductor_c"] - s_bare["t_conductor_c"] < 15.0,
          "%.2f -> %.2f C" % (s_bare["t_conductor_c"], s_bund["t_conductor_c"]))
    # ⚠ radiation is NOT scaled, so the temperature shift is smaller than the
    # 25 % error in h alone would imply. A gate that expected the full 25 %
    # would be encoding a misunderstanding.
    check("the rise is SMALLER than scaling every loss term would give — "
          "radiation is unaffected by how the air moves",
          s_bund["t_conductor_c"] - s_bare["t_conductor_c"]
          < 0.25 * (s_bare["t_conductor_c"] - 30.0))
    check("the default path is untouched (no bundle note when factor is 1.0)",
          not any("bundle factor" in w for w in s_bare.get("warnings", [])))
    check("an applied factor is REPORTED to the caller, with its provenance",
          any("bundle factor" in w and "OpenFOAM trefoil" in w
              for w in s_bund.get("warnings", [])))
    # A derated number nobody can trace is worse than an underated one.
    s_anon = th.solve_steady(40.0, 0.0026, _lay, 3.3e-3, tamb_c=30.0,
                             bundle_factor=0.80)
    check("a factor with NO provenance says so, rather than passing quietly",
          any("NO PROVENANCE" in w for w in s_anon.get("warnings", [])))

    # ============ B3. the bundle-factor SOURCE (wire/bundle_convection) ======
    # The seam existed with no producer. This is the producer, driven here with
    # a STUB runner so the arithmetic and the refusals are covered in the FAST
    # tier (CI) while only the physics needs a solver.
    from emstudio.wire import bundle_convection as bc
    from emstudio.wire.bundle import Bundle, BundleMember

    _TREFOIL = [(-0.015, -0.00866), (0.015, -0.00866), (0.0, 0.01732)]

    class _StubRes:
        # the MEASURED trefoil result — Nu 3.1542 at Ra 6341
        nu_d, ra_d = 3.1542, 6341.0

    class _StubCase:
        def __init__(self, **kw):
            self.kw = kw

    def _stub_run(ok=True, converged=True, drift=1.55e-5, res=_StubRes):
        def _run(_d, _case):
            rep = {"ok": ok, "converged": converged, "nu_drift": drift}
            if not ok:
                rep["failed_at"] = "snappyHexMesh"
                return rep, None
            return rep, res()
        return _run

    f = bc.solve_bundle_factor(_TREFOIL, 0.020, box_w=0.2, box_h=0.2,
                               runner=_stub_run(), case_factory=_StubCase,
                               case_dir=".")
    check("bundle factor = Nu_solved / Churchill-Chu at the RESULTING Ra "
          "(0.8028 for the measured trefoil)",
          abs(f.factor - 3.1542 / th.nu_churchill_chu(6341.0, 0.71)) < 1e-12
          and abs(f.factor - 0.8028) < 5e-4, "%.6f" % f.factor)
    check("...and it reports the error the way a user would state it "
          "(Churchill-Chu over-predicts by ~25 %)",
          24.0 < f.correlation_error_pct < 25.5,
          "%+.2f %%" % f.correlation_error_pct)
    check("provenance carries Nu, the correlation, Ra, convergence and drift",
          all(s in f.provenance for s in ("Nu", "Churchill-Chu", "Ra",
                                          "converged", "drift")))
    # ⚠ A failed solve must NOT fall back to a plausible number.
    try:
        bc.solve_bundle_factor(_TREFOIL, 0.020, box_w=0.2, box_h=0.2,
                               runner=_stub_run(ok=False),
                               case_factory=_StubCase, case_dir=".")
        check("a FAILED solve raises rather than returning a factor", False)
    except ValueError:
        check("a FAILED solve raises rather than returning a factor", True)
    f_unconv = bc.solve_bundle_factor(
        _TREFOIL, 0.020, box_w=0.2, box_h=0.2,
        runner=_stub_run(converged=False, drift=0.2),
        case_factory=_StubCase, case_dir=".")
    check("an unsettled solve still returns a factor but WARNS it is "
          "provisional",
          f_unconv.warnings and "provisional" in f_unconv.warnings[0])

    class _TooGood:
        nu_d, ra_d = 9.0, 6341.0
    f_hi = bc.solve_bundle_factor(_TREFOIL, 0.020, box_w=0.2, box_h=0.2,
                                  runner=_stub_run(res=_TooGood),
                                  case_factory=_StubCase, case_dir=".")
    check("a factor above 1 (cools BETTER than a lone cable) is flagged as "
          "needing forced flow",
          any("forced flow" in w for w in f_hi.warnings))

    # geometry key: the thing that notices a cached factor has gone stale
    k1 = bc.geometry_key(_TREFOIL, 0.020, 0.2, 0.2)
    check("the geometry key is order-independent (same arrangement, same key)",
          k1 == bc.geometry_key(list(reversed(_TREFOIL)), 0.020, 0.2, 0.2))
    check("...and changes when spacing or the enclosure changes — which is "
          "exactly what the factor measures",
          k1 != bc.geometry_key(_TREFOIL, 0.020, 0.4, 0.4)
          and k1 != bc.geometry_key([(0, 0)], 0.020, 0.2, 0.2))

    check("Bundle geometry feeds the solve directly (the Cable Designer has "
          "already packed it)",
          bc.centres_from_bundle(Bundle(members=[BundleMember("A", 0.020,
                                                              qty=3)]))[1]
          == 0.020)
    try:
        bc.centres_from_bundle(Bundle(members=[BundleMember("A", 0.020),
                                               BundleMember("B", 0.010)]))
        check("MIXED cable diameters are refused, not averaged", False)
    except ValueError:
        check("MIXED cable diameters are refused, not averaged", True)
    for _kw, _why in ((dict(centres=[]), "no cables"),
                      (dict(d_cable=0.0), "zero diameter"),
                      (dict(clearance_ratio=1.0), "a clearance ratio of 1")):
        _args = dict(centres=_TREFOIL, d_cable=0.020, runner=_stub_run(),
                     case_factory=_StubCase, case_dir=".")
        _args.update(_kw)
        try:
            bc.solve_bundle_factor(**_args)
            check("%s is rejected" % _why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % _why, True)

    # ============ B4. the EM -> thermal (Joule) coupling ============
    # The conductor's I²R loss drives the CFD wall flux. ⚠ NOT fvOptions:
    # snappy carves the cables OUT of the fluid domain, so a volumetric source
    # would heat the air, not the conductor. The loss enters as what it
    # physically is at the fluid boundary — a surface flux.
    q_j = bc.joule_w_per_m(40.0, 3.3e-3, 70.0)
    # the SAME expression solve_steady uses: I² R20 (1 + alpha (Tc - 20))
    _expect = 40.0 ** 2 * 3.3e-3 * (1.0 + th.CONDUCTORS["Cu"]["alpha20"] * 50.0)
    check("Joule loss is I²R(T) and matches the electrical model the ampacity "
          "answer already uses",
          abs(q_j - _expect) < 1e-12, "%.4f W/m" % q_j)
    g_j = bc.gradient_from_joule(q_j, 0.0026)
    _k = th.air_properties(315.0)[0]
    check("gradient = q'/(pi D) / k_air, exactly",
          abs(g_j - (q_j / (math.pi * 0.0026)) / _k) < 1e-9,
          "%.1f K/m" % g_j)
    # ⚠ the k must be AIR's, not copper's — the gradient is taken in the FLUID.
    # Copper's k is ~400 vs air's ~0.027, so the wrong one is 4 orders out and
    # would still look like a plausible number in the dictionary.
    check("...and the conductivity used is AIR's (~0.027), not the "
          "conductor's (~400) — 4 orders of magnitude, and plausible-looking "
          "either way", 0.02 < _k < 0.05, "k = %.4f W/mK" % _k)
    check("a bigger cable spreads the SAME loss over more perimeter, so the "
          "flux falls",
          bc.gradient_from_joule(q_j, 0.0052) < g_j / 1.9,
          "%.0f -> %.0f K/m" % (g_j, bc.gradient_from_joule(q_j, 0.0052)))
    for _bad, _why in ((0.0, "zero Joule loss"), (-1.0, "negative loss")):
        try:
            bc.gradient_from_joule(_bad, 0.0026)
            check("%s is rejected" % _why, False)
        except ValueError:
            check("%s is rejected" % _why, True)
    # driving the solve by Joule loss must be visible in the provenance —
    # "solved at 400 K/m" and "solved at this cable's loss" are different claims
    f_j = bc.solve_bundle_factor(_TREFOIL, 0.020, box_w=0.2, box_h=0.2,
                                 joule_w_per_m=5.0, runner=_stub_run(),
                                 case_factory=_StubCase, case_dir=".")
    check("a Joule-driven solve records WHICH drove the flux, so it cannot be "
          "mistaken for a typed gradient",
          "Joule" in f_j.provenance and "W/m" in f_j.provenance)
    f_g = bc.solve_bundle_factor(_TREFOIL, 0.020, box_w=0.2, box_h=0.2,
                                 runner=_stub_run(), case_factory=_StubCase,
                                 case_dir=".")
    check("...and a gradient-driven one says so instead",
          "gradient" in f_g.provenance and "Joule" not in f_g.provenance)

    # ============ C. steady solve + ampacity bands ============
    # AWG-10 / PVC 105 C hookup (UL1015-class): Multicable row 58 A +-25%
    d10 = 2.588e-3
    rdc10 = 3.277e-3
    pvc = [{"name": "PVC", "t_m": 0.76e-3}]
    amp10 = th.ampacity(d10, pvc, rdc10, 105.0, tamb_c=30.0)
    check("AWG-10 PVC 105 C free-air ampacity in the Multicable 58 A "
          "+-25% band",
          43.5 <= amp10["ampacity_a"] <= 72.5,
          "{0:.1f} A".format(amp10["ampacity_a"]))
    # NEC 310.17 rows (code values with safety margin -> +-25% bands):
    # AWG10 90C: 55 A; AWG2 90C: 190 A (XLPE-class walls)
    amp10n = th.ampacity(d10, [{"name": "XLPE", "t_m": 0.76e-3}], rdc10,
                         90.0, tamb_c=30.0)
    d2 = 6.544e-3
    amp2 = th.ampacity(d2, [{"name": "XLPE", "t_m": 1.14e-3}], 0.5127e-3,
                       90.0, tamb_c=30.0)
    check("NEC 310.17 free-air bands (+-25%): AWG10@90C vs 55 A, "
          "AWG2@90C vs 190 A",
          0.75 * 55.0 <= amp10n["ampacity_a"] <= 1.25 * 55.0
          and 0.75 * 190.0 <= amp2["ampacity_a"] <= 1.25 * 190.0,
          "{0:.1f} / {1:.1f} A".format(amp10n["ampacity_a"],
                                       amp2["ampacity_a"]))
    # MIL-W-5088L §6.7 text points (+-15%): AWG22 16.2 A at 200C wire/60C
    # ambient; AWG12 68 A at 200C/25C (M16878-class PTFE walls)
    a22 = th.ampacity(0.644e-3, [{"name": "PTFE", "t_m": 0.25e-3}],
                      52.96e-3, 200.0, tamb_c=60.0)
    a12 = th.ampacity(2.053e-3, [{"name": "PTFE", "t_m": 0.3e-3}],
                      5.211e-3, 200.0, tamb_c=25.0)
    check("MIL-W-5088L free-air text points (+-15%): AWG22 16.2 A, "
          "AWG12 68 A",
          0.85 * 16.2 <= a22["ampacity_a"] <= 1.15 * 16.2
          and 0.85 * 68.0 <= a12["ampacity_a"] <= 1.15 * 68.0,
          "{0:.1f} / {1:.1f} A".format(a22["ampacity_a"],
                                       a12["ampacity_a"]))
    # NASA 1-atm measured point (SOFT +-15% on the rise): 20 AWG XL-ETFE,
    # 13.99 A -> wire 75.2 C at ~21 C shroud
    rep20 = th.solve_steady(13.99, 0.812e-3, [{"name": "PE", "t_m": 0.2e-3,
                                               "rho_t": 4.0}],
                            33.31e-3, tamb_c=21.0)
    rise = rep20["t_conductor_c"] - 21.0
    # model KNOWN conservative here: at Ra ~ 7 Churchill-Chu reads ~25%
    # below the Morgan measured fit (documented low-Ra bias; Morgan-level h
    # reproduces the measurement) -> band [0.85, 1.30] x measured rise, hot
    # side only expected, plus the engine must SAY so
    check("NASA 1-atm 20 AWG point: rise within [0.85, 1.30] x the "
          "measured 54.2 C (CC fine-wire conservatism documented)",
          0.85 * 54.2 <= rise <= 1.30 * 54.2
          and any("fine-wire" in w for w in rep20["warnings"]),
          "{0:.1f} C".format(rise))
    # physics identities on the steady report
    check("steady identities: Tc - Ts == q*SumT (1e-9), profile monotone "
          "decreasing, q_conv+q_rad == q",
          abs(rep20["t_conductor_c"] - rep20["t_surface_c"]
              - rep20["q_w_m"] * rep20["sum_t_k_m_w"]) < 1e-9
          and all(a[1] >= b[1] - 1e-12 for a, b in
                  zip(rep20["profile"], rep20["profile"][1:]))
          and abs(rep20["q_conv_w_m"] + rep20["q_rad_w_m"]
                  - rep20["q_w_m"]) < 1e-6)
    check("ampacity rises with temperature class (70 < 90 < 105 C)",
          th.ampacity(d10, pvc, rdc10, 70.0)["ampacity_a"]
          < th.ampacity(d10, pvc, rdc10, 90.0)["ampacity_a"]
          < amp10["ampacity_a"])
    check("thermal runaway flagged (huge I into a thickly insulated "
          "fine wire), not silently clamped",
          th.solve_steady(50.0, 0.2e-3, [{"name": "PVC", "t_m": 5e-3}],
                          0.55, tamb_c=30.0)["runaway"])

    # ============ D. transient lump ============
    tr = th.transient(rep20, 0.812e-3)
    check("transient: T(tau) - Ta == (1 - 1/e) * dT_final exactly; "
          "T(0) = Ta; T(5 tau) ~ final",
          abs(tr["t_of"](tr["tau_s"]) - tr["tamb_c"]
              - (1.0 - 1.0 / math.e) * tr["dt_final_c"]) < 1e-9
          and abs(tr["t_of"](0.0) - tr["tamb_c"]) < 1e-12
          and abs(tr["t_of"](5.0 * tr["tau_s"]) - tr["tamb_c"]
                  - tr["dt_final_c"]) / tr["dt_final_c"] < 0.01)
    # C_th pinned by an INDEPENDENT hand computation (not the engine's own
    # helper): Cu disc + PE annulus with the IEC volumetric capacities
    c_hand = (3.45e6 * math.pi * (0.812e-3 / 2.0) ** 2
              + 2.4e6 * math.pi * ((0.812e-3 / 2.0 + 0.2e-3) ** 2
                                   - (0.812e-3 / 2.0) ** 2))
    check("transient lump: C_th equals the hand-computed Cu disc + PE "
          "annulus; tau physical seconds-to-minutes",
          abs(tr["c_th_j_m_k"] - c_hand) / c_hand < 1e-12
          and 1.0 < tr["tau_s"] < 600.0, "tau {0:.1f} s".format(tr["tau_s"]))
    # litz-style metal-area override: filler counted at qv_gap, not as Cu
    tr_lz = th.transient(rep20, 0.812e-3,
                         a_cond_m2=0.5 * math.pi * (0.812e-3 / 2.0) ** 2)
    c_lz_hand = c_hand - (3.45e6 - 2.0e6) * 0.5 * math.pi \
        * (0.812e-3 / 2.0) ** 2
    check("transient a_cond_m2 override: half-copper envelope swaps half "
          "the disc to gap capacity exactly",
          abs(tr_lz["c_th_j_m_k"] - c_lz_hand) / c_lz_hand < 1e-12)

    # heating_curve: the honest overload trajectory (the small-signal
    # exponential undercuts even the adiabatic bound above ~1.5x rating)
    amp_hc = amp10["ampacity_a"]
    hc_half = th.heating_curve(0.5 * amp_hc, d10, pvc, rdc10, tamb_c=30.0,
                               t_end_s=4000.0, n_steps=500)
    rep_half = th.solve_steady(0.5 * amp_hc, d10, pvc, rdc10, tamb_c=30.0)
    check("heating_curve settles on solve_steady's fixed point (0.5x "
          "rating, < 0.3 C)",
          abs(hc_half["t_final_c"] - rep_half["t_conductor_c"]) < 0.3,
          "{0:.2f} vs {1:.2f} C".format(hc_half["t_final_c"],
                                        rep_half["t_conductor_c"]))
    hc_2x = th.heating_curve(2.0 * amp_hc, d10, pvc, rdc10, tamb_c=30.0,
                             t_limit_c=105.0, t_end_s=300.0, n_steps=600)
    r20f_2x = rdc10 * (2.0 * amp_hc) ** 2
    alpha_cu = th.CONDUCTORS["Cu"]["alpha20"]
    t_ad = hc_2x["c_th_j_m_k"] / (r20f_2x * alpha_cu) * math.log(
        (1.0 + alpha_cu * (105.0 - 20.0)) / (1.0 + alpha_cu * (30.0 - 20.0)))
    check("heating_curve at 2x rating: time-to-limit exists and respects "
          "the zero-loss adiabatic lower bound (the exp model violated it)",
          hc_2x["t_hit_s"] is not None and hc_2x["t_hit_s"] >= t_ad * 0.999,
          "t_hit {0:.1f} s >= adiabatic {1:.1f} s".format(
              hc_2x["t_hit_s"], t_ad))
    check("heating_curve monotone rising toward the final temperature",
          all(b >= a - 1e-9 for a, b in zip(hc_2x["temps_c"],
                                            hc_2x["temps_c"][1:])))

    # cold radiative surroundings: the bracket must extend BELOW ambient
    # (the pre-fix solver pinned Ts = tamb and broke its own energy balance)
    rep_cold = th.solve_steady(0.5, d10, pvc, rdc10, tamb_c=30.0,
                               emissivity=0.92, tsur_c=0.0)
    bal = abs(rep_cold["q_w_m"]
              - rep_cold["q_conv_w_m"] - rep_cold["q_rad_w_m"])
    check("tsur < tamb: energy balance holds and Ts settles BELOW ambient",
          bal < 1e-6 and 10.0 < rep_cold["t_surface_c"] < 30.0,
          "Ts {0:.2f} C, balance {1:.1e}".format(rep_cold["t_surface_c"],
                                                 bal))

    # degenerate-input contracts raise instead of returning garbage
    def _raises(fn):
        try:
            fn()
            return False
        except (ValueError, ZeroDivisionError):
            return True

    check("degenerate inputs raise: ampacity at Rdc=0 (limit unreachable), "
          "transient at zero load, coax limit <= ambient, plume q <= 0",
          _raises(lambda: th.ampacity(d10, pvc, 0.0, 105.0, tamb_c=30.0))
          and _raises(lambda: th.transient(
              th.solve_steady(0.0, d10, pvc, rdc10, tamb_c=30.0), d10))
          and _raises(lambda: th.coax_power_w(
              1e9, 0.5e-3, 1.5e-3, 2.25, 3e-4, 40.0, 0.33, tamb_c=40.0))
          and _raises(lambda: th.plume_scales(0.1, 0.0, 320.0)))

    # ============ E. adiabatic short-circuit (IEC 60949 / BS 7671) ============
    j0_cu = th.adiabatic_current_a(1.0, 1.0, 90.0, 250.0, "Cu")
    j0_al = th.adiabatic_current_a(1.0, 1.0, 90.0, 250.0, "Al")
    check("adiabatic J0 (90->250 C, 1 s): Cu 143.08, Al 94.48 A/mm2 "
          "(beta = 234.5 / 228)",
          abs(j0_cu - 143.08) < 0.05 and abs(j0_al - 94.48) < 0.05,
          "{0:.2f} / {1:.2f}".format(j0_cu, j0_al))
    i630 = th.adiabatic_current_a(630.0, 1.0, 90.0, 250.0, "Cu")
    check("630 mm2 Cu XLPE worked rows: 1 s 90.2 kA, 0.5 s 127.6 kA, "
          "2 s 63.8 kA (0.15% — Liban prints beta = 234)",
          abs(i630 - 90216.0) / 90216.0 < 1.5e-3
          and abs(th.adiabatic_current_a(630.0, 0.5, 90.0, 250.0, "Cu")
                  - 127585.0) / 127585.0 < 1.5e-3
          and abs(th.adiabatic_current_a(630.0, 2.0, 90.0, 250.0, "Cu")
                  - 63792.0) / 63792.0 < 1.5e-3)
    check("BS 7671 k-factors: Cu PVC 70->160 = 115, Cu 90->160 = 100, "
          "Cu XLPE 90->250 = 143, Al 70->160 = 76, Al 90->250 = 94 (+-0.5)",
          abs(th.k_factor(70.0, 160.0, "Cu") - 115.0) < 0.5
          and abs(th.k_factor(90.0, 160.0, "Cu") - 100.0) < 0.5
          and abs(th.k_factor(90.0, 250.0, "Cu") - 143.0) < 0.5
          and abs(th.k_factor(70.0, 160.0, "Al") - 76.0) < 0.5
          and abs(th.k_factor(90.0, 250.0, "Al") - 94.0) < 0.5)
    check("adiabatic scales exactly as 1/sqrt(t)",
          abs(th.adiabatic_current_a(50.0, 4.0, 70.0, 160.0)
              * 2.0 - th.adiabatic_current_a(50.0, 1.0, 70.0, 160.0)) < 1e-9)

    # ============ F. NEC bundle adjustment (exact lookup) ============
    check("NEC 310.15(C)(1): 3->1.0, 4-6->0.8, 7-9->0.7, 10-20->0.5, "
          "21-30->0.45, 31-40->0.4, 41+->0.35",
          th.nec_derate(3) == 1.0 and th.nec_derate(4) == 0.8
          and th.nec_derate(6) == 0.8 and th.nec_derate(7) == 0.7
          and th.nec_derate(9) == 0.7 and th.nec_derate(10) == 0.5
          and th.nec_derate(20) == 0.5 and th.nec_derate(21) == 0.45
          and th.nec_derate(30) == 0.45 and th.nec_derate(31) == 0.4
          and th.nec_derate(40) == 0.4 and th.nec_derate(41) == 0.35
          and th.nec_derate(100) == 0.35)

    # ============ G. coax RF average power ============
    check("dissipation identity: (ln10/10) * 8.685889638 dB/Np == 2 "
          "(factor 2 lives with FIELD nepers)",
          abs(th.LN10_10 * (20.0 / math.log(10.0)) - 2.0) < 1e-12)
    # exact 1/2 dielectric-heat factor: numeric integration of the TEM 1/r^2
    # dissipation against the radial ladder == half the full resistance
    a_c, b_c, k_d = 0.71e-3, 1.905e-3, 0.13
    n_i = 200000
    acc = 0.0
    norm = math.log(b_c / a_c)
    for i in range(n_i):
        r = a_c * math.exp((i + 0.5) / n_i * norm)   # log-spaced shells
        w = 1.0 / n_i                                 # 1/r weight, log grid
        acc += w * math.log(b_c / r) / (2.0 * math.pi * k_d)
    r_diel = math.log(b_c / a_c) / (2.0 * math.pi * k_d)
    check("1/2 dielectric-heat factor exact (numeric TEM integration "
          "vs 0.5*R_diel)",
          abs(acc - 0.5 * r_diel) / (0.5 * r_diel) < 1e-4,
          "ratio {0:.6f}".format(acc / r_diel))
    # Times LMR-240 primary band (90-125%): datasheet attenuation split
    # sqrt(f)->conductor / linear->dielectric; pinned constants k_foam 0.13
    # (DERIVED — never tune), k_jkt 0.35, eps 0.9, 100 C inner / 40 C amb;
    # geometry: a 0.71, b 1.905, braid OD 4.52, jacket OD 6.10 mm; Cu inner,
    # Al tape outer
    ft2m = (100.0 / 30.48) / 100.0
    ok_lmr, worst = True, (1.0, 0)
    for f_mhz, p_ds in ((30, 1490), (150, 660), (450, 380), (900, 260),
                        (1800, 180), (5800, 100)):
        rep = th.coax_power_w(
            f_mhz * 1e6, a_c, b_c, 1.42, 0.0, 100.0, 0.13,
            jacket_t_m=(3.05e-3 - 2.26e-3), k_jacket_w_mk=0.35,
            d_shield_m=4.52e-3, tamb_c=40.0, emissivity=0.9,
            atten_cond_db_m=0.242080 * math.sqrt(f_mhz) * ft2m,
            atten_diel_db_m=0.000330 * f_mhz * ft2m,
            sigma_inner=5.8e7, sigma_outer=3.5e7)
        ratio = rep["p_max_w"] / p_ds
        if abs(math.log(ratio)) > abs(math.log(worst[0])):
            worst = (ratio, f_mhz)
        ok_lmr = ok_lmr and 0.90 <= ratio <= 1.25
    check("Times LMR-240 average-power table: model/datasheet in 90-125% "
          "at 30-5800 MHz (datasheet attenuation, pinned constants)",
          ok_lmr, "worst {0:.3f} at {1} MHz".format(*worst))
    # Belden 8262 (RG-58C/U): rating basis unstated -> one-sided soft band
    # (smooth-conductor loss UNDER-estimates -> P_max OVER-estimates)
    from emstudio.wire import coax as cx

    ok_b = True
    for f_mhz, p_ds in ((50, 300), (100, 200), (400, 90), (1000, 55)):
        rep = th.coax_power_w(f_mhz * 1e6, 0.418e-3, 1.4605e-3, 2.25,
                              3e-4, 85.0, 0.33,
                              jacket_t_m=(4.95e-3 - 3.8e-3) / 2.0,
                              k_jacket_w_mk=0.16, d_shield_m=3.8e-3,
                              tamb_c=40.0, emissivity=0.92)
        ok_b = ok_b and 1.0 * p_ds <= rep["p_max_w"] <= 3.0 * p_ds
    check("Belden 8262 power ratings: smooth-conductor model one-sided in "
          "100-300% of the datasheet (basis unstated)", ok_b)
    # Pasternack RG-142B/U 395 W @ 1 GHz (provenance-uncertain -> soft
    # one-sided, their own 42.32 dB/100m attenuation as loss input)
    rep142 = th.coax_power_w(1e9, 0.47e-3, 1.475e-3, 2.04, 0.0, 200.0,
                             0.25, jacket_t_m=(4.95e-3 - 3.96e-3) / 2.0,
                             k_jacket_w_mk=0.21, d_shield_m=3.96e-3,
                             tamb_c=40.0, emissivity=0.92,
                             atten_cond_db_m=42.32 / 100.0 * 0.85,
                             atten_diel_db_m=42.32 / 100.0 * 0.15)
    check("RG-142B/U 395 W @ 1 GHz: soft one-sided 100-200% "
          "(datasheet attenuation)",
          395.0 <= rep142["p_max_w"] <= 2.0 * 395.0,
          "{0:.0f} W".format(rep142["p_max_w"]))
    check("coax thermal-conductivity picks pinned (PE 0.33, PTFE 0.25, "
          "foam 0.13 DERIVED, FEP 0.21)",
          th.K_THERMAL_COAX["PE (solid polyethylene)"] == 0.33
          and th.K_THERMAL_COAX["PTFE (solid)"] == 0.25
          and th.K_THERMAL_COAX["Foam PE (typ. 80% VF)"] == 0.13
          and th.K_THERMAL_COAX["FEP"] == 0.21)

    # ============ H. exterior field: film + buoyant plume ============
    # H-1 (recipe gate G6): an INDEPENDENT fixed-step RK4 shooting solve of
    # the GPS plume equations must re-derive the engine's pinned constants —
    # exact tanh closed form at Pr = 2 (Yih/Fujii), then the Pr = 0.7 pins
    def gps_solve(pr, d_eta=0.002, eta_inf=25.0):
        def deriv(f, fp, fpp, h):
            return (fp, fpp,
                    -(12.0 / 5.0) * f * fpp + (4.0 / 5.0) * fp * fp - h,
                    -(12.0 / 5.0) * pr * f * h)

        def march(fp0):
            f, fp, fpp, h = 0.0, fp0, 0.0, 1.0
            n = int(eta_inf / d_eta)
            i_acc, eta_half, prev = 0.0, None, (0.0, 1.0)
            fh_prev = fp0 * 1.0
            for i in range(n):
                if fp < 0.0:
                    return "crossed", None, None, None
                if fp > 50.0 or f > 1e3:
                    return "blowup", None, None, None
                y = (f, fp, fpp, h)
                k1 = deriv(*y)
                k2 = deriv(*(y[j] + 0.5 * d_eta * k1[j] for j in range(4)))
                k3 = deriv(*(y[j] + 0.5 * d_eta * k2[j] for j in range(4)))
                k4 = deriv(*(y[j] + d_eta * k3[j] for j in range(4)))
                f, fp, fpp, h = (y[j] + d_eta / 6.0
                                 * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j])
                                 for j in range(4))
                fh = fp * h
                i_acc += 0.5 * (fh_prev + fh) * d_eta   # trapezoid
                fh_prev = fh
                eta = (i + 1) * d_eta
                if eta_half is None and h <= 0.5:
                    e0, h0 = prev
                    eta_half = e0 + (0.5 - h0) / (h - h0) * (eta - e0)
                prev = (eta, h)
            return "ok", 2.0 * i_acc, eta_half, f

        lo, hi = 0.2, 2.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            tag = march(mid)[0]
            if tag == "crossed":
                lo = mid
            else:
                hi = mid
        fp0 = 0.5 * (lo + hi)
        _tag, i_full, eta_half, f_inf = march(fp0)
        return fp0, i_full, eta_half, f_inf

    fp2, i2, _eh2, _f2 = gps_solve(2.0)
    a_yih = (125.0 / 576.0) ** 0.25
    check("independent RK4 shoot, Pr = 2: f'(0) == sqrt(5)/4 = 0.55901699 "
          "and I == (16/15)(125/576)^(1/4) (Yih/Fujii closed form)",
          abs(fp2 - 0.55901699) < 1e-4
          and abs(i2 - 16.0 / 15.0 * a_yih) < 3e-4,
          "{0:.7f} / {1:.6f}".format(fp2, i2))
    fp7, i7, eh7, _f7 = gps_solve(0.7)
    g0_id = (64.0 * 0.7 ** 2 * i7 ** 4) ** (-0.2)
    check("independent RK4 shoot, Pr = 0.7: f'(0) = 0.661832, I = 1.211742, "
          "eta_half = 1.1745, G0 identity (64 Pr^2 I^4)^(-1/5) = 0.430523",
          abs(fp7 - th.PLUME_FP0) < 3e-4 and abs(i7 - th.PLUME_I) < 1e-3
          and abs(eh7 - th.PLUME_ETA_T_HALF) < 3e-3
          and abs(g0_id - th.PLUME_G0) < 3e-4,
          "{0:.6f} / {1:.6f} / {2:.5f} / {3:.6f}".format(fp7, i7, eh7,
                                                         g0_id))

    # a 10-mm-class cable operating point for the field gates
    repf = th.solve_steady(120.0, 8e-3, [{"name": "XLPE", "t_m": 1.2e-3}],
                           0.34e-3, tamb_c=25.0)
    fld, meta = th.exterior_field(repf, 25.0)
    rr = repf["d_surface_m"] / 2.0
    # G1 exponent exactness (pure power law in the scales)
    s1 = th.plume_scales(0.05, repf["q_conv_w_m"], repf["t_film_k"])
    s32 = th.plume_scales(0.05 * 32.0, repf["q_conv_w_m"], repf["t_film_k"])
    sq2 = th.plume_scales(0.05, 2.0 * repf["q_conv_w_m"], repf["t_film_k"])
    check("plume power laws exact: dTc ~ z^-3/5, y_half ~ z^2/5, "
          "dTc ~ q'^4/5",
          abs(s32["dt_c"] / s1["dt_c"] - 32.0 ** -0.6) < 1e-12
          and abs(s32["y_scale"] / s1["y_scale"] - 32.0 ** 0.4) < 1e-9
          and abs(sq2["dt_c"] / s1["dt_c"] - 2.0 ** 0.8) < 1e-12)
    # G2 enthalpy-flux conservation with the pinned profile table
    k_f, nu_f, al_f, _pr_f = th.air_properties(repf["t_film_k"])
    rho_cp = k_f / al_f
    ok_e, worst_e = True, 0.0
    for z_od in (2.0, 10.0, 50.0):
        z = z_od * repf["d_surface_m"]
        sc = th.plume_scales(z, repf["q_conv_w_m"], repf["t_film_k"])
        n_y, y_max = 4000, 10.0 * sc["y_scale"]
        acc = 0.0
        for i in range(n_y):
            y = (i + 0.5) / n_y * y_max
            eta = y / sc["y_scale"]
            acc += (rho_cp * sc["u_c"] * th.plume_fprime(eta)
                    * sc["dt_c"] * th.plume_h(eta)) * (y_max / n_y)
        err = abs(2.0 * acc - repf["q_conv_w_m"]) / repf["q_conv_w_m"]
        worst_e = max(worst_e, err)
        ok_e = ok_e and err < 0.01
    check("plume enthalpy flux recovers q'_conv at z = 2/10/50 D (< 1%)",
          ok_e, "worst {0:.3%}".format(worst_e))
    # G3 surface continuity + film/engine consistency
    ok_s = all(abs(fld(rr * math.sin(p), -rr * math.cos(p))
                   - repf["t_surface_c"]) < 1e-9
               for p in (0.0, 0.7, 1.5708, 2.4, 3.1416))
    n_p, acc_f = 720, 0.0
    for i in range(n_p):
        phi = (i + 0.5) / n_p * 2.0 * math.pi
        acc_f += (1.0 + meta["film_c"] * math.cos(phi)) / n_p
    check("field surface continuity T(R, phi) == Ts; asymmetric film "
          "preserves the mean flux exactly; delta == D/Nu (cross-module)",
          ok_s and abs(acc_f - 1.0) < 1e-12
          and abs(meta["delta_bar_m"]
                  - repf["d_surface_m"] / repf["nu"]) < 1e-12)
    # G4 mirror symmetry (bitwise)
    check("field mirror symmetry T(x,z) == T(-x,z) exactly",
          all(fld(x, z) == fld(-x, z)
              for x, z in ((0.001, 0.02), (0.004, 0.05), (0.01, 0.1),
                           (0.002, -0.01))))
    # G5 monotone centreline decay + bounds
    zs = [meta["z_match_m"] * (1.05 + 0.35 * i) for i in range(24)]
    cs = [fld(0.0, z) for z in zs]
    ok_b = True
    for i in range(40):
        for j in range(40):
            x = -6.0 * rr + 12.0 * rr * i / 39.0
            z = -4.0 * rr + 16.0 * rr * j / 39.0
            if math.hypot(x, z) > rr:
                t = fld(x, z)
                ok_b = ok_b and 25.0 - 1e-9 <= t <= repf["t_surface_c"] + 1e-9
    check("centreline strictly decreasing above the match point; exterior "
          "bounded Ta <= T <= Ts",
          all(a > b for a, b in zip(cs, cs[1:])) and ok_b)
    check("plume fed by the CONVECTIVE share only (q_conv < q_total when "
          "radiating) and virtual origin below the match point",
          repf["q_conv_w_m"] < repf["q_w_m"]
          and meta["z0_m"] < meta["z_match_m"] and meta["have_plume"])

    if FAILURES:
        print("THERMAL GATE FAILED: {0}".format(FAILURES))
        return 1
    print("THERMAL GATE PASSED")
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
        raise SystemExit("thermal validation failed")
    sys.exit(0)
