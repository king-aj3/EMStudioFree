# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: ITU-R P.368-10 LF/MF ground wave (the LFMF port).

Replays TWO official/oracle datasets through ``emstudio/coverage/lfmf.py``
(the numpy/scipy port of the NTIA LFMF v1.1 reference implementation — the
software that IS Recommendation P.368-10):

1. ``data/lfmf/oracle_grid.csv`` — 2497 full-double-precision rows generated
   from the unmodified upstream binary on this machine (provenance in the
   adjacent PROVENANCE.md): every A_btl / E / P_rx must match to <= 1e-3 dB
   (live reference run of the port: worst 3.2e-5 dB) and every
   flat-earth/residue-series method flag must match exactly.
2. ``data/lfmf/LFMF_Examples.csv`` — the official NTIA example file: the 5
   valid rows to their printed 0.1 precision, and all 90 input-validation
   rows must be REJECTED for the reason matching their error code.

Also gates the ``groundwave`` spherical wrapper: flat-vs-spherical agreement
at short range, the beyond-100-km divergence, spherical Millington
reciprocity, and the <10 kHz hard-stop.

Pass: exit 0 and 'LFMF GATE PASSED'. Pure python3 (scipy; no FreeCAD).
"""
import csv
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "tests", "validation", "data", "lfmf")

FAILURES = []

# upstream ReturnCode -> a keyword the port's ValueError message must contain
ERROR_CODE_KEYWORDS = {
    32: "TX height",
    33: "RX height",
    34: "frequency",
    35: "power",
    36: "refractivity",
    37: "distance",
    38: "permittivity",
    39: "conductivity",
    40: "pol",
}


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _row_inputs(row):
    return (float(row["h_tx__meter"]), float(row["h_rx__meter"]),
            float(row["f__mhz"]), float(row["P_tx__watt"]),
            float(row["N_s"]), float(row["d__km"]),
            float(row["epsilon"]), float(row["sigma"]), int(row["pol"]))


def main():
    from emstudio.coverage import groundwave, lfmf

    print("EMStudio P.368-10 LFMF validation gate")

    # ---- 1. the dense full-precision oracle grid ----
    worst = 0.0
    worst_case = ""
    n = 0
    n_bad = 0            # rows over tolerance — NaN-safe (not dev <= tol)
    n_method_bad = 0
    with open(os.path.join(DATA, "oracle_grid.csv")) as fh:
        for row in csv.DictReader(fh):
            got = lfmf.lfmf(*_row_inputs(row))
            dev = max(abs(got["A_btl__db"] - float(row["A_btl__db"])),
                      abs(got["E_dBuVm"] - float(row["E_dBuVm"])),
                      abs(got["P_rx__dbm"] - float(row["P_rx__dbm"])))
            if got["method"] != int(row["method"]):
                n_method_bad += 1
            # NaN-proof: a NaN dev must FAIL, so compare via "not <=", never ">"
            if not (dev <= 1e-3):
                n_bad += 1
            if math.isnan(dev) or dev > worst:
                worst = dev
                worst_case = "f={0} MHz d={1} km eps={2} sigma={3} pol={4}".format(
                    row["f__mhz"], row["d__km"], row["epsilon"], row["sigma"],
                    row["pol"])
            n += 1
    check("oracle grid fully replayed (2497 rows, both methods)", n == 2497,
          str(n))
    check("A_btl/E/P_rx match the reference binary <= 1e-3 dB on EVERY row",
          n_bad == 0,
          "{0} rows over; worst {1:.2e} dB ({2})".format(n_bad, worst,
                                                         worst_case))
    check("flat-earth/residue method switch matches on every row",
          n_method_bad == 0, "{0} mismatches".format(n_method_bad))

    # ---- 2. the official NTIA examples file ----
    n_valid = 0
    n_err = 0
    ok_valid = True
    ok_err = True
    with open(os.path.join(DATA, "LFMF_Examples.csv")) as fh:
        for row in csv.DictReader(fh):
            rtn = int(row["rtn"])
            if rtn == 0:
                got = lfmf.lfmf(*_row_inputs(row))
                dev = max(abs(got["A_btl__db"] - float(row["A_btl__db"])),
                          abs(got["E_dBuVm"] - float(row["E_dBuVm"])),
                          abs(got["P_rx__dbm"] - float(row["P_rx__dbm"])))
                # NaN-safe: "not <=" fails on NaN where "> 0.05" would pass
                if not (dev <= 0.05) or got["method"] != int(row["method"]):
                    ok_valid = False
                    check("official example row f={0} d={1}".format(
                        row["f__mhz"], row["d__km"]), False,
                        "dev {0:.3f} dB".format(dev))
                n_valid += 1
            else:
                keyword = ERROR_CODE_KEYWORDS[rtn]
                try:
                    lfmf.lfmf(*_row_inputs(row))
                    ok_err = False
                    check("error row (code {0}) not rejected".format(rtn),
                          False)
                except ValueError as exc:
                    if keyword.lower() not in str(exc).lower():
                        ok_err = False
                        check("error row (code {0}) wrong reason".format(rtn),
                              False, str(exc))
                n_err += 1
    check("all 5 official worked examples match to their printed 0.1 digit",
          ok_valid and n_valid == 5, "{0} rows".format(n_valid))
    check("all 90 official error rows rejected for the coded reason",
          ok_err and n_err == 90, "{0} rows".format(n_err))

    # ---- 3. the groundwave module wrappers ----
    # flat vs spherical agree at short range (both are the Sommerfeld flat
    # earth at 50 km; the |A| interpolation differs from the exact wofz by
    # ~1 dB there, so this is a sanity band, not a digit gate)
    e_flat = groundwave.field_strength_dbuv_m(50e3, 1e6, 13.0, 5e-3)
    e_sph = groundwave.spherical_field_strength_dbuv_m(50e3, 1e6, 13.0, 5e-3)
    check("flat vs P.368-10 agree at 50 km / 1 MHz (within 1.5 dB)",
          abs(e_flat - e_sph) < 1.5,
          "flat {0:.2f} vs spherical {1:.2f} dBuV/m".format(e_flat, e_sph))

    # beyond 100 km the flat model UNDER-predicts the loss growth rate on a
    # curved earth: at 1000 km the spherical field must be far below flat
    e_flat_1000 = groundwave.field_strength_dbuv_m(1000e3, 1e6, 13.0, 5e-3)
    e_sph_1000 = groundwave.spherical_field_strength_dbuv_m(
        1000e3, 1e6, 13.0, 5e-3)
    check("spherical earth attenuates far more at 1000 km / 1 MHz",
          e_sph_1000 < e_flat_1000 - 30.0,
          "flat {0:.1f} vs spherical {1:.1f} dBuV/m".format(
              e_flat_1000, e_sph_1000))

    # spherical field must fall monotonically with distance (sea, 500 kHz)
    ds = [100e3, 300e3, 1000e3, 3000e3]
    es = [groundwave.spherical_field_strength_dbuv_m(d, 5e5, 70.0, 5.0)
          for d in ds]
    check("spherical field falls monotonically 100->3000 km over sea",
          all(es[i] > es[i + 1] for i in range(len(es) - 1)),
          " > ".join("{0:.1f}".format(e) for e in es))

    # sea > average > very dry at 500 km / 1 MHz (the P.368 ordering)
    e_sea = groundwave.spherical_field_strength_dbuv_m(500e3, 1e6, 70.0, 5.0)
    e_avg = groundwave.spherical_field_strength_dbuv_m(500e3, 1e6, 13.0, 5e-3)
    e_dry = groundwave.spherical_field_strength_dbuv_m(500e3, 1e6, 3.0, 1e-4)
    check("ground ordering sea > average > very dry at 500 km",
          e_sea > e_avg > e_dry,
          "{0:.1f} / {1:.1f} / {2:.1f} dBuV/m".format(e_sea, e_avg, e_dry))

    # CMF normalization: E -> CMF/d as attenuation -> 1 (short sea path,
    # low frequency), matching the flat module's reference convention
    d_ref = 1e3
    e_ref = groundwave.spherical_field_strength_dbuv_m(d_ref, 1e4, 70.0, 5.0)
    e_ideal = 20.0 * math.log10((300.0 / d_ref) * 1e6)
    check("spherical CMF reference: 300 V -> ~300 mV/m at 1 km (sea, 10 kHz)",
          abs(e_ref - e_ideal) < 0.1,
          "{0:.3f} vs {1:.3f} dBuV/m".format(e_ref, e_ideal))

    # Millington on the spherical engine stays reciprocal
    segs = [(100e3, 13.0, 5e-3), (150e3, 70.0, 5.0)]
    m_fwd = groundwave.millington_field_dbuv_m(segs, 1e6, spherical=True)
    m_rev = groundwave.millington_field_dbuv_m(list(reversed(segs)), 1e6,
                                               spherical=True)
    check("spherical Millington mixed path is reciprocal",
          abs(m_fwd - m_rev) < 1e-9,
          "{0:.3f} vs {1:.3f} dBuV/m".format(m_fwd, m_rev))
    # ... and the mixed path lies between the homogeneous extremes
    e_all_land = groundwave.spherical_field_strength_dbuv_m(250e3, 1e6,
                                                            13.0, 5e-3)
    e_all_sea = groundwave.spherical_field_strength_dbuv_m(250e3, 1e6,
                                                           70.0, 5.0)
    check("spherical Millington lies between homogeneous land and sea",
          e_all_land < m_fwd < e_all_sea,
          "{0:.1f} < {1:.1f} < {2:.1f}".format(e_all_land, m_fwd, e_all_sea))

    # the VLF hard-stop: 9 kHz must raise, never extrapolate
    try:
        groundwave.spherical_field_strength_dbuv_m(100e3, 9e3, 70.0, 5.0)
        stopped = False
    except ValueError:
        stopped = True
    check("below 10 kHz the spherical model HARD-STOPS (P.684 band)", stopped)

    # ---- 4. the heatmap opt-in wiring ----
    import numpy as np

    from emstudio.coverage import heatmap

    res_flat = heatmap.coverage_grid(40.0, -100.0, 10.0, 1e6, 60.0,
                                     radius_m=150e3, n=11,
                                     model="ground_wave")
    res_flat2 = heatmap.coverage_grid(40.0, -100.0, 10.0, 1e6, 60.0,
                                      radius_m=150e3, n=11,
                                      model="ground_wave", gw_engine="flat")
    check("heatmap default gw_engine is byte-identical to explicit 'flat'",
          np.array_equal(res_flat.field_dbuv_m, res_flat2.field_dbuv_m, equal_nan=True))

    res_sph = heatmap.coverage_grid(40.0, -100.0, 10.0, 1e6, 60.0,
                                    radius_m=150e3, n=11,
                                    model="ground_wave", gw_engine="p368")
    check("heatmap meta records the ground-wave engine",
          res_flat.meta.get("gw_engine") == "flat"
          and res_sph.meta.get("gw_engine") == "p368")
    # the far corner (~212 km) must show the spherical-earth extra loss
    d_far = np.nanmax(res_sph.dist_m)
    i, j = np.unravel_index(np.nanargmax(res_sph.dist_m),
                            res_sph.dist_m.shape)
    check("heatmap far cell (>{0:.0f} km) spherical << flat".format(
        d_far / 1e3 - 1),
          res_sph.field_dbuv_m[i, j] < res_flat.field_dbuv_m[i, j] - 3.0,
          "flat {0:.1f} vs p368 {1:.1f} dBuV/m".format(
              float(res_flat.field_dbuv_m[i, j]), float(res_sph.field_dbuv_m[i, j])))

    if FAILURES:
        print("LFMF GATE FAILED: {0}".format(FAILURES))
        return 1
    print("LFMF GATE PASSED")
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
        raise SystemExit("lfmf validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("lfmf validation failed")
    sys.exit(0)
