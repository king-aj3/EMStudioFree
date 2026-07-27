# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: ITU-R P.1812-6 via the vendored reference (Py1812).

Replays the OFFICIAL ITU-R SG3 P.1812-6 validation examples — 19 profile
files / 63 per-dataset reference logs with per-equation intermediates
(`tests/validation/data/p1812/`, provenance in PROVENANCE.md there) — through
the vendored engine:

* the final basic transmission loss ``Lb`` (Eq 69) and field strength ``Ep``
  (Eq 70) must match every official log to 0.01 dB, and
* the **delta-Bullington diffraction intermediates** (Lbulla/Lbulls/Ldsph,
  Eq 21/27) must match the logs when recomputed through the EMStudio
  ``delta_bullington_loss_db`` wrapper inputs — gating the diffraction
  sub-model in isolation.

The preprocessing (power recovery, GlobCover clutter mapping, coastal dct/dcr)
is adapted from the upstream ``tests/validateP1812.py`` (same permissive
license; plotting/log-writing removed — see the vendor PROVENANCE.md).

Pass: exit 0 and 'P1812 GATE PASSED'. Pure python3 (numpy; no FreeCAD, no
ITU digital maps — DN/N0 come from the official profiles).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "tests", "validation", "data", "p1812")

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _ref_values(log_path):
    """{label: value} for the interesting rows of an official log file."""
    want = {"Lb (dB)": "lb", "Ep (dBuV/m)": "ep", "Lbulla (dB)": "lbulla",
            "Lbulls (dB)": "lbulls", "Ldsph (dB)": "ldsph", "Ldp (dB)": "ldp"}
    out = {}
    with open(log_path) as fh:
        for line in fh:
            parts = [p.strip() for p in line.split(",")]
            if parts and parts[0] in want and want[parts[0]] not in out:
                try:
                    out[want[parts[0]]] = float(parts[3])
                except (ValueError, IndexError):
                    pass
    return out


def _run_dataset(P1812, np, sg3db, measID, clutter_code="GlobCover"):
    """One dataset -> (Lb, Ep), faithful to the upstream harness (no logs)."""
    hhRx = sg3db.hRx[measID]
    hhTx = sg3db.hTx[0]
    sg3db.userChoiceInt = measID

    if not P1812.isempty(sg3db.coveragecode):
        i = sg3db.coveragecode[-1]
        RxClutterCode, RxP1546Clutter, R2external = P1812.clutter(
            i, clutter_code)
        i = sg3db.coveragecode[0]
        TxClutterCode, TxP1546Clutter, R1external = P1812.clutter(
            i, clutter_code)
        sg3db.RxClutterCodeP1546 = RxP1546Clutter
        if not P1812.isempty(sg3db.h_ground_cover):
            if not np.isnan(sg3db.h_ground_cover[-1]):
                if sg3db.h_ground_cover[-1] > 3:
                    sg3db.RxClutterHeight = sg3db.h_ground_cover[-1]
                else:
                    sg3db.RxClutterHeight = R2external
            else:
                sg3db.RxClutterHeight = R2external
            if not np.isnan(sg3db.h_ground_cover[0]):
                if sg3db.h_ground_cover[0] > 3:
                    sg3db.TxClutterHeight = sg3db.h_ground_cover[0]
                else:
                    sg3db.TxClutterHeight = R1external
            else:
                sg3db.TxClutterHeight = R1external
        else:
            sg3db.RxClutterHeight = R2external
            sg3db.TxClutterHeight = R1external

    sg3db.fid_log = -1
    sg3db.dct = 500
    sg3db.dcr = 500
    if sg3db.radio_met_code[0] == 1:
        sg3db.dct = 0
    if sg3db.radio_met_code[-1] == 1:
        sg3db.dcr = 0

    lb, ep = P1812.bt_loss(
        sg3db.frequency[measID] / 1e3, sg3db.TimePercent[measID],
        sg3db.x, sg3db.h_gamsl, sg3db.h_ground_cover, sg3db.radio_met_code,
        sg3db.hTx[measID], sg3db.hRx[measID], sg3db.polHVC[measID],
        sg3db.TxLAT, sg3db.RxLAT, sg3db.TxLON, sg3db.RxLON,
        pL=50, sigmaL=0, Ptx=sg3db.TransmittedPower[measID],
        DN=sg3db.DN, N0=sg3db.N0, dct=sg3db.dct, dcr=sg3db.dcr,
        flag4=0, debug=0, fid_log=-1)
    return float(lb), float(ep)


def main():
    import numpy as np

    from emstudio.vendor.py1812 import P1812

    print("EMStudio P.1812-6 validation gate (official SG3 examples)")

    profiles_dir = os.path.join(DATA, "profiles")
    logs_dir = os.path.join(DATA, "reference_logs")
    files = sorted(f for f in os.listdir(profiles_dir) if f.endswith(".csv"))
    check("all 19 official profiles present", len(files) == 19, str(len(files)))

    n_cases = 0
    worst_lb = worst_ep = 0.0
    diff_checked = 0
    worst_diff = 0.0
    for fn in files:
        sg3db = P1812.read_sg3_measurements2(
            os.path.join(profiles_dir, fn), "Fryderyk_csv")
        sg3db.debug = 0
        sg3db.pathinfo = 1
        for kindex in range(0, sg3db.Ndata):
            pkw = 10.0 ** (sg3db.ERPMaxTotal[kindex] / 10.0) * 1e-3
            if np.isnan(pkw):
                e = sg3db.MeasuredFieldStrength[kindex]
                pl_db = sg3db.BasicTransmissionLoss[kindex]
                f = sg3db.frequency[kindex]
                pdbkw = -137.2217 + e - 20 * np.log10(f) + pl_db
                pkw = 10 ** (pdbkw / 10.0)
            sg3db.TransmittedPower = np.append(sg3db.TransmittedPower, pkw)
        sg3db.ClutterCode = []

        for measID in range(0, len(sg3db.hRx)):
            log_path = os.path.join(
                logs_dir, fn[:-4] + "_" + str(measID) + "_log.csv")
            if not os.path.isfile(log_path):
                continue
            ref = _ref_values(log_path)
            lb, ep = _run_dataset(P1812, np, sg3db, measID)
            n_cases += 1
            worst_lb = max(worst_lb, abs(lb - ref["lb"]))
            # the log's Eq-70 Ep is normalized to 1 kW e.r.p.; bt_loss
            # returns the Ptx-scaled value
            ep_1kw = ep - 10.0 * np.log10(sg3db.TransmittedPower[measID])
            worst_ep = max(worst_ep, abs(ep_1kw - ref["ep"]))
            if worst_lb > 0.01:
                check("Lb mismatch in {0}#{1}".format(fn, measID), False,
                      "{0:.4f} vs {1:.4f}".format(lb, ref["lb"]))
                return 1

            # delta-Bullington sub-model in isolation (every 4th case, for
            # runtime): rebuild the diffraction inputs exactly as bt_loss
            # does at median and match Lbulla/Lbulls/Ldsph
            if all(k in ref for k in ("lbulla", "lbulls", "ldsph")) \
                    and n_cases % 4 == 1:
                from emstudio.coverage import p1812 as wrap

                got = wrap.delta_bullington_intermediates(
                    sg3db.x, sg3db.h_gamsl, sg3db.h_ground_cover,
                    sg3db.radio_met_code, sg3db.hTx[measID],
                    sg3db.hRx[measID], sg3db.frequency[measID] / 1e3,
                    dn=sg3db.DN, pol=int(sg3db.polHVC[measID]))
                for key in ("lbulla", "lbulls", "ldsph"):
                    worst_diff = max(worst_diff, abs(got[key] - ref[key]))
                diff_checked += 1

    check("all 63 official datasets replayed", n_cases == 63, str(n_cases))
    check("final Lb matches every official log <= 0.01 dB",
          worst_lb <= 0.01, "worst {0:.6f} dB".format(worst_lb))
    check("field strength Ep matches every official log <= 0.01 dB",
          worst_ep <= 0.01, "worst {0:.6f} dB".format(worst_ep))
    check("delta-Bullington intermediates match the logs (sampled cases)",
          diff_checked >= 10 and worst_diff <= 0.01,
          "{0} cases, worst {1:.6f} dB".format(diff_checked, worst_diff))

    # wrapper validity enforcement (no silent extrapolation)
    from emstudio.coverage import p1812 as wrap

    try:
        wrap.check_validity(10.0, 50.0, 100.0)
        oob = False
    except ValueError:
        oob = True
    check("wrapper rejects out-of-validity frequency", oob)

    if FAILURES:
        print("P1812 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("P1812 GATE PASSED")
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
        raise SystemExit("p1812 validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("p1812 validation failed")
    sys.exit(0)
