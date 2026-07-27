# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: ITU-R P.1546-6 via the vendored WP3K reference (Py1546).

Replays the OFFICIAL ITU-R WP3K P.1546-6 validation examples — 24 SG3 profile
files (`tests/validation/data/p1546/profiles/`, provenance in the adjacent
PROVENANCE.md) — through the vendored engine and requires every predicted
field strength to match the official reference outputs
(`combined_results_reference.csv`) to 0.01 dB.

The per-dataset preprocessing below (transmit power recovery, land/sea split,
clutter selection, the Annex-5 §1.1 terminal-swap rule, heff/tca/teff1) is
adapted from the upstream validation harness ``tests/validateP1546.py``
(same permissive license; changes: plotting and log-file writing removed,
function-ized for gating — see emstudio/vendor/py1546/PROVENANCE.md).

Pass: exit 0 and 'P1546 GATE PASSED'. Pure python3 (numpy; no FreeCAD).
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "tests", "validation", "data", "p1546")

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _run_profile(P1546, np, path, clutter_code="P1546", wa=500.0):
    """All datasets of one SG3 profile file -> [(dataset, measured, predicted)].

    Faithful port of the upstream harness preprocessing (no plots, no logs).
    """
    sg3db = P1546.read_sg3_measurements2(path, "Fryderyk_csv")
    sg3db.debug = 0
    sg3db.pathinfo = 1

    for kindex in range(0, sg3db.Ndata):
        perp = sg3db.ERPMaxTotal[kindex]
        pkw = 10.0 ** (perp / 10.0) * 1e-3
        if np.isnan(pkw):
            e = sg3db.MeasuredFieldStrength[kindex]
            pl_db = sg3db.BasicTransmissionLoss[kindex]
            f = sg3db.frequency[kindex]
            pdbkw = -137.2217 + e - 20 * np.log10(f) + pl_db
            pkw = 10 ** (pdbkw / 10.0)
        sg3db.TransmittedPower = np.append(sg3db.TransmittedPower, pkw)

    # land/sea split from the radio-met / coverage codes
    dland = dsea = 0.0
    if len(sg3db.radio_met_code) > 0 and len(sg3db.coveragecode) > 0:
        for i in range(0, len(sg3db.x)):
            if i == len(sg3db.x) - 1:
                dinc = (sg3db.x[-1] - sg3db.x[-2]) / 2.0
            elif i == 0:
                dinc = (sg3db.x[1] - sg3db.x[0]) / 2.0
            else:
                dinc = (sg3db.x[i + 1] - sg3db.x[i - 1]) / 2.0
            if sg3db.radio_met_code[i] == 1 or sg3db.radio_met_code[i] == 3:
                dsea += dinc
            else:
                dland += dinc
    elif len(sg3db.radio_met_code) == 0 and len(sg3db.coveragecode) > 0:
        for i in range(0, len(sg3db.x)):
            if i == len(sg3db.x) - 1:
                dinc = (sg3db.x[-1] - sg3db.x[-2]) / 2.0
            elif i == 0:
                dinc = (sg3db.x[1] - sg3db.x[0]) / 2.0
            else:
                dinc = (sg3db.x[i + 1] - sg3db.x[i - 1]) / 2.0
            if sg3db.coveragecode[i] == 2:
                dsea += dinc
            else:
                dland += dinc
    else:
        dland = dsea = float("nan")

    hTx, hRx = sg3db.hTx, sg3db.hRx
    out = []
    for measID in range(0, len(hRx)):
        if len(sg3db.coveragecode) > 0:
            i = sg3db.coveragecode[-1]
            RxClutterCode, RxP1546Clutter, R2external = P1546.clutter(
                i, clutter_code)
            i = sg3db.coveragecode[0]
            TxClutterCode, TxP1546Clutter, R1external = P1546.clutter(
                i, clutter_code)
            if TxP1546Clutter.find("Rural") != -1:
                R1external = 0
            if (np.size(sg3db.h_ground_cover) != 0
                    and clutter_code.find("default") == -1):
                if not np.isnan(sg3db.h_ground_cover[-1]):
                    sg3db.RxClutterHeight = sg3db.h_ground_cover[-1]
                else:
                    sg3db.RxClutterHeight = R2external
                if not np.isnan(sg3db.h_ground_cover[0]):
                    sg3db.TxClutterHeight = sg3db.h_ground_cover[0]
                else:
                    sg3db.TxClutterHeight = R1external
            else:
                sg3db.RxClutterHeight = R2external
                sg3db.TxClutterHeight = R1external
        else:
            RxClutterCode, RxP1546Clutter, R2external = P1546.clutter(
                1, clutter_code)
            TxClutterCode, TxP1546Clutter, R1external = P1546.clutter(
                1, clutter_code)
            sg3db.RxClutterCodeP1546 = RxP1546Clutter
            sg3db.RxClutterHeight = R2external
            sg3db.TxClutterHeight = R1external

        sg3db.LandPath = dland
        sg3db.SeaPath = dsea

        hhRx, hhTx = hRx[measID], hTx[measID]
        x = sg3db.x
        h_gamsl = sg3db.h_gamsl
        x_swapped = x[-1] - x[::-1]
        h_gamsl_swapped = h_gamsl[::-1]

        swap_flag = (sg3db.first_point_transmitter == 0)
        if swap_flag:
            hhRx, hhTx = hhTx, hhRx
            x = x_swapped
            h_gamsl = h_gamsl_swapped
            sg3db.TxClutterHeight, sg3db.RxClutterHeight = \
                sg3db.RxClutterHeight, sg3db.TxClutterHeight
            RxP1546Clutter, TxP1546Clutter = TxP1546Clutter, RxP1546Clutter
            RxClutterCode, TxClutterCode = TxClutterCode, RxClutterCode

        sg3db.h2 = hhRx
        sg3db.ha = hhTx
        sg3db.htter = h_gamsl[0]
        sg3db.hrter = h_gamsl[-1]
        sg3db.RxClutterCodeP1546 = RxP1546Clutter
        sg3db.userChoiceInt = measID

        sg3db.heff = P1546.heffCalc(x, h_gamsl, hhTx)
        sg3db.tca = P1546.tcaCalc(x, h_gamsl, hhRx, hhTx)
        sg3db.eff1 = P1546.teff1Calc(x, h_gamsl, hhTx, hhRx)

        sg3db.fid_log = -1
        sg3db.wa = wa
        sg3db = P1546.Compute(sg3db)
        out.append((measID, float(sg3db.MeasuredFieldStrength[measID]),
                    float(sg3db.PredictedFieldStrength)))
    return out


def main():
    import numpy as np

    from emstudio.vendor.py1546 import P1546

    print("EMStudio P.1546-6 validation gate (official WP3K examples)")

    # reference: the official combined results (filename, dataset) -> predicted
    ref = {}
    with open(os.path.join(DATA, "combined_results_reference.csv")) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            ref[(parts[1], int(parts[2]))] = (float(parts[3]), float(parts[4]))
    check("official reference table parsed ({0} datasets)".format(len(ref)),
          len(ref) >= 50, str(len(ref)))

    profiles_dir = os.path.join(DATA, "profiles")
    files = sorted(f for f in os.listdir(profiles_dir) if f.endswith(".csv"))
    check("all 24 official profiles present", len(files) == 24, str(len(files)))

    n_match = 0
    worst = 0.0
    worst_case = ""
    n_run = 0
    devs = []
    for fn in files:
        rows = _run_profile(P1546, np, os.path.join(profiles_dir, fn))
        for measID, measured, predicted in rows:
            n_run += 1
            key_variants = [(fn, measID)]
            hit = None
            for kv in key_variants:
                if kv in ref:
                    hit = ref[kv]
                    break
            if hit is None:
                continue
            ref_meas, ref_pred = hit
            n_match += 1
            dev = abs(predicted - ref_pred)
            devs.append(dev)
            if dev > worst:
                worst, worst_case = dev, "{0}#{1}".format(fn, measID)
            # the measured column is data, not physics — but it must round-trip
            if abs(measured - ref_meas) > 0.01:
                check("measured field mismatch in {0}#{1}".format(fn, measID),
                      False, "{0} vs {1}".format(measured, ref_meas))
    check("every official dataset replayed and matched to a reference row",
          n_match == len(ref) and n_run == n_match,
          "{0} matched / {1} run / {2} reference".format(
              n_match, n_run, len(ref)))
    check("predicted field strength matches the official reference <= 0.01 dB",
          bool(devs) and max(devs) <= 0.01,
          "worst {0:.6f} dB ({1})".format(worst, worst_case))

    # the EMStudio wrapper: a plain smooth-path spot call must run in-validity,
    # fall with distance, and reject out-of-validity frequency
    from emstudio.coverage import p1546 as wrap

    e50, l50 = wrap.field_strength_dbuv_m(600.0, 50.0, 75.0, 10.0, 50.0)
    e100, l100 = wrap.field_strength_dbuv_m(600.0, 50.0, 75.0, 10.0, 100.0)
    check("wrapper: field falls / loss grows with distance (600 MHz land)",
          e50 > e100 and l100 > l50,
          "E {0:.1f} -> {1:.1f} dBuV/m".format(e50, e100))
    try:
        wrap.field_strength_dbuv_m(10.0, 50.0, 75.0, 10.0, 50.0)  # 10 MHz
        oob = False
    except Exception:
        oob = True
    check("wrapper: out-of-validity frequency rejected (no extrapolation)", oob)

    if FAILURES:
        print("P1546 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("P1546 GATE PASSED")
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
        raise SystemExit("p1546 validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("p1546 validation failed")
    sys.exit(0)
