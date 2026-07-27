# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: ITU-R P.2001-6 via the vendored reference (Py2001).

Replays the OFFICIAL ITU-R P.2001 validation examples — 2 profiles x 2215
cases = 4430 cases (`tests/validation/data/p2001/`, provenance in the
adjacent PROVENANCE.md; results mirrored gzipped) — through the vendored
engine: the basic transmission loss Lb of every case must match the
reference to <= 1e-6 dB (the upstream harness tolerance). Also gates the
EMStudio wrapper (`emstudio.coverage.p2001.path_loss_db`) against a
reference case and its validity enforcement.

NEEDS the ITU digital maps: install once with
``emstudio.coverage.itu_maps.install_p2001_maps()`` — the gate fails with
instructions when they are absent (they may not be redistributed with the
repo). Runtime ~20-30 s (4430 full-model runs).

Pass: exit 0 and 'P2001 GATE PASSED'. Pure python3 (numpy; no FreeCAD).
"""
import csv
import gzip
import io
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "tests", "validation", "data", "p2001")

TOL = 1e-6

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _read_profile(path, np):
    with open(path) as fh:
        rows = [r for r in list(csv.reader(fh))[9:] if r and r[0].strip()]
    d = np.array([float(r[0]) for r in rows])
    h = np.array([float(r[1]) for r in rows])
    z = np.array([float(r[2]) for r in rows])
    return d, h, z


def _read_results_gz(path):
    with gzip.open(path, "rb") as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8")
        return list(csv.DictReader(text, skipinitialspace=True))


def main():
    import numpy as np

    from emstudio.coverage import itu_maps

    print("EMStudio P.2001-6 validation gate (official ITU-R examples)")

    if itu_maps.find_npz("P2001.npz") is None:
        check("ITU digital maps installed (P2001.npz)", False,
              "run emstudio.coverage.itu_maps.install_p2001_maps() once — "
              "the maps are ITU integral products and cannot ship in-repo")
        print("P2001 GATE FAILED: {0}".format(FAILURES))
        return 1

    from emstudio.vendor.py2001 import P2001

    base = "Validation_examples_ITU-R_P_2001_"
    n_total = 0
    n_over = 0
    worst = 0.0
    worst_case = ""
    for prof in ("b2iseac", "prof4"):
        d, h, z = _read_profile(
            os.path.join(DATA, base + prof + "_profile.csv"), np)
        res = _read_results_gz(
            os.path.join(DATA, base + prof + "_results.csv.gz"))
        for r0 in res:
            lb = P2001.bt_loss(d, h, z, float(r0["GHz"]), float(r0["Tpc"]),
                               float(r0["Phire"]), float(r0["Phirn"]),
                               float(r0["Phite"]), float(r0["Phitn"]),
                               float(r0["Hrg"]), float(r0["Htg"]),
                               float(r0["Grx"]), float(r0["Gtx"]),
                               int(float(r0["FlagVp"])))
            dev = abs(lb - float(r0["Lb"]))
            if not (dev <= TOL):              # NaN counts as a failure
                n_over += 1
            if math.isnan(dev) or dev > worst:   # NaN is sticky
                worst = dev
                worst_case = "{0} GHz={1} Tpc={2}".format(
                    prof, r0["GHz"], r0["Tpc"])
            n_total += 1
    check("all 4430 official cases replayed", n_total == 4430, str(n_total))
    check("Lb matches the reference <= 1e-6 dB on every case",
          n_over == 0,
          "{0} cases over; worst {1:.2e} dB ({2})".format(n_over, worst,
                                                          worst_case))

    # the EMStudio wrapper reproduces the engine + enforces validity
    from emstudio.coverage import p2001 as wrap

    d, h, z = _read_profile(
        os.path.join(DATA, base + "prof4_profile.csv"), np)
    r0 = _read_results_gz(
        os.path.join(DATA, base + "prof4_results.csv.gz"))[0]
    lb_wrap = wrap.path_loss_db(
        float(r0["GHz"]), float(r0["Tpc"]), d, h, z,
        htg_m=float(r0["Htg"]), hrg_m=float(r0["Hrg"]),
        lat_t=float(r0["Phitn"]), lat_r=float(r0["Phirn"]),
        lon_t=float(r0["Phite"]), lon_r=float(r0["Phire"]),
        gt_dbi=float(r0["Gtx"]), gr_dbi=float(r0["Grx"]),
        vertical=bool(int(float(r0["FlagVp"]))))
    check("wrapper reproduces the official case (<= 1e-6 dB)",
          abs(lb_wrap - float(r0["Lb"])) <= TOL,
          "{0:.6f} vs {1}".format(lb_wrap, r0["Lb"]))
    try:
        wrap.path_loss_db(60.0, 50.0, d, h, z, 10.0, 10.0, 0.0, 0.0, 0.0, 1.0)
        oob = False
    except ValueError:
        oob = True
    check("wrapper rejects out-of-validity frequency (60 GHz)", oob)
    try:
        wrap.path_loss_db(1.0, 0.0, d, h, z, 10.0, 10.0, 0.0, 0.0, 0.0, 1.0)
        oob = False
    except ValueError:
        oob = True
    check("wrapper rejects Tpc = 0 (must be inside (0, 100))", oob)

    if FAILURES:
        print("P2001 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("P2001 GATE PASSED")
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
        raise SystemExit("p2001 validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("p2001 validation failed")
    sys.exit(0)
