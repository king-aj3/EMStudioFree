# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: point-to-point propagation models vs textbook formulas.

Pass: exit 0 and 'PROPAGATION GATE PASSED'. Pure python3 (no solver).

Checks free-space (Friis) loss, the ITU-R P.526 knife-edge diffraction curve, the
two-ray plane-earth d^4 law, the ITU field-strength relation, and the terrain
single-edge (Deygout) diffraction against their closed forms.
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
    from emstudio.coverage import propagation as pr

    print("EMStudio point-to-point propagation validation gate")

    # --- free-space (Friis) path loss ---
    # 1 km, 300 MHz -> 32.44 + 20log10(1 km) + 20log10(300 MHz) = 81.98 dB
    fspl = pr.free_space_path_loss_db(1000.0, 300e6)
    check("FSPL 1 km @ 300 MHz = 81.98 dB", abs(fspl - 81.98) < 0.05,
          "{0:.3f} dB".format(fspl))
    # doubling distance adds 6.02 dB
    check("FSPL doubles distance -> +6.02 dB",
          abs((pr.free_space_path_loss_db(2000.0, 300e6) - fspl) - 6.0206) < 1e-3)

    # --- knife-edge diffraction (ITU-R P.526) ---
    check("knife-edge J(0) ~= 6.0 dB (grazing)",
          abs(pr.knife_edge_loss_db(0.0) - 6.02) < 0.1,
          "{0:.3f} dB".format(pr.knife_edge_loss_db(0.0)))
    check("knife-edge J(1) ~= 13.9 dB",
          abs(pr.knife_edge_loss_db(1.0) - 13.93) < 0.1,
          "{0:.3f} dB".format(pr.knife_edge_loss_db(1.0)))
    check("knife-edge J(2.4) ~= 20.6 dB",
          abs(pr.knife_edge_loss_db(2.4) - 20.6) < 0.2,
          "{0:.3f} dB".format(pr.knife_edge_loss_db(2.4)))
    check("knife-edge J(v<-0.78) = 0 (clear)",
          pr.knife_edge_loss_db(-1.0) == 0.0)
    # diffraction parameter formula
    v = pr.fresnel_v(30.0, 1000.0, 1000.0, 300e6)
    lam = 299792458.0 / 300e6
    v_expect = 30.0 * math.sqrt(2.0 / lam * (1.0 / 1000.0 + 1.0 / 1000.0))
    check("fresnel v = h*sqrt(2/lambda(1/d1+1/d2))", abs(v - v_expect) < 1e-9,
          "v={0:.4f}".format(v))

    # --- plane-earth two-ray (d^4) ---
    pe1 = pr.plane_earth_loss_db(1000.0, 10.0, 10.0)
    pe2 = pr.plane_earth_loss_db(2000.0, 10.0, 10.0)
    check("plane-earth doubling distance -> +12.04 dB (d^4)",
          abs((pe2 - pe1) - 12.041) < 1e-2, "{0:.3f} dB".format(pe2 - pe1))
    # PL = 40log10(1000) - 20log10(10) - 20log10(10) = 120 - 20 - 20 = 80 dB
    check("plane-earth 1 km, 10 m/10 m = 80 dB", abs(pe1 - 80.0) < 1e-6,
          "{0:.3f} dB".format(pe1))
    bp = pr.plane_earth_breakpoint_m(50.0, 5.0, 100e6)
    check("plane-earth breakpoint 4*ht*hr/lambda",
          abs(bp - 4.0 * 50.0 * 5.0 / (299792458.0 / 100e6)) < 1e-6)

    # --- field strength from EIRP ---
    # 1 kW EIRP at 1 km -> E = sqrt(30000)/1000 V/m -> 104.77 dBuV/m
    e = pr.field_strength_dbuv_m(1000.0, 1000.0)
    check("field strength 1 kW EIRP @ 1 km = 104.8 dBuV/m",
          abs(e - 104.77) < 0.1, "{0:.3f} dBuV/m".format(e))
    # ITU cross-check: E(dBuV/m) = P_EIRP(dBW) + 74.8 - 20log10(d_km); 30 dBW, 1 km
    check("field strength matches P_EIRP(dBW)+74.8-20log10(d_km)",
          abs(e - (30.0 + 74.8)) < 0.1)

    # --- terrain single-edge (Deygout) diffraction ---
    # flat ends (antenna tops both at 20 m), a 50 m hill at mid-path -> obstructed
    prof = [(0.0, 0.0), (1000.0, 50.0), (2000.0, 0.0)]
    res = pr.terrain_profile_loss(prof, ht_m=20.0, hr_m=20.0, freq_hz=300e6)
    check("terrain: mid-path hill is the controlling edge",
          res["edge_index"] == 1 and res["diffraction_db"] > 15.0,
          "v={0:.2f}, diff={1:.1f} dB".format(res["v_max"], res["diffraction_db"]))
    check("terrain total = FSPL + diffraction",
          abs(res["total_loss_db"] - (res["fspl_db"] + res["diffraction_db"])) < 1e-9)
    # a low hill (below the line of sight) -> clear line of sight, no diffraction
    clear = pr.terrain_profile_loss([(0.0, 0.0), (1000.0, 0.0), (2000.0, 0.0)],
                                    ht_m=20.0, hr_m=20.0, freq_hz=300e6)
    check("terrain: clear path -> no diffraction loss",
          clear["edge_index"] is None and clear["diffraction_db"] == 0.0)

    # --- link budget ---
    lb = pr.link_budget(43.0, path_loss_db=100.0, tx_gain_dbi=10.0, rx_gain_dbi=3.0,
                        rx_sens_dbm=-95.0)
    # 43 + 10 + 3 - 100 = -44 dBm; margin -44 - (-95) = 51 dB
    check("link budget rx power = Ptx+Gtx+Grx-PL", abs(lb["rx_power_dbm"] - (-44.0)) < 1e-9)
    check("link budget fade margin = rx - sens", abs(lb["fade_margin_db"] - 51.0) < 1e-9)

    if FAILURES:
        print("PROPAGATION GATE FAILED: {0}".format(FAILURES))
        return 1
    print("PROPAGATION GATE PASSED")
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
        raise SystemExit("propagation validation failed")
    sys.exit(0)
