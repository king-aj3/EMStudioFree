# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: ITU-R P.452-18 via the vendored reference (Py452).

Replays the OFFICIAL CG-3M P.452-18 validation examples — 17 profile files /
595 cases (`tests/validation/data/p452/`, provenance in the adjacent
PROVENANCE.md) — through the vendored engine:

* per profile: the 21 path-geometry intermediates (ae, hts/hrs, horizon
  angles/distances, hstd/hsrd, path type, dtm/dlm, b0, omega, and the
  map-interpolated DN/N0) against the reference columns;
* per case: the final basic transmission loss Lb AND the eight sub-model
  losses (Lbfsg, Lb0p, Lb0b, Ldsph, Ld50, Ldp, Lbs, Lba);
* the EMStudio wrapper (`emstudio.coverage.p452.path_loss_db`) reproduces the
  direct engine call, and rejects out-of-validity inputs.

The comparison logic is adapted from the upstream harness
``tests/validateP452.py`` (same permissive license; changes: pandas removed
— csv+numpy — and function-ized for gating). NaN-proof comparisons ("not
<=", never ">"). NEEDS the ITU digital maps: install once with
``emstudio.coverage.itu_maps.install_p452_maps()`` — the gate fails with
instructions when they are absent (they may not be redistributed with the
repo).

Pass: exit 0 and 'P452 GATE PASSED'. Pure python3 (numpy; no FreeCAD).
"""
import csv
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "tests", "validation", "data", "p452")

TOL = 1e-6

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _read_profile(path, np):
    with open(path) as fh:
        rows = [r for r in list(csv.reader(fh))[1:] if r and r[0].strip()]
    d = np.array([float(r[0]) for r in rows])
    h = np.array([float(r[1]) for r in rows])
    r_ = np.array([float(r[2]) for r in rows])
    zone = np.array([float(r[4]) for r in rows])
    return d, h, r_, zone


def _read_results(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, skipinitialspace=True))


def _nan_aware_max(values):
    """max() that PROPAGATES NaN (builtin max silently drops mid-list NaN)."""
    vals = list(values)
    if any(math.isnan(v) for v in vals):
        return float("nan")
    return max(vals)


def _run_profile(np, P452, prof_path, res_path):
    """Replay one official profile; returns
    (worst_geom, worst_loss, n_cases, n_cases_over_tol)."""
    d, h, r_, zone = _read_profile(prof_path, np)
    res = _read_results(res_path)

    g = h + r_
    kk = np.where(d < 50.0 / 1000.0)[0]
    g[kk] = h[kk]
    kk = np.where(d > d[-1] - 50.0 / 1000.0)[0]
    g[kk] = h[kk]

    row = res[0]
    dtot = d[-1]

    dtm = P452.longest_cont_dist(d, zone, 12)
    dlm = P452.longest_cont_dist(d, zone, 2)
    phim_e, phim_n, _, _ = P452.great_circle_path(
        float(row["phir_e (deg)"]), float(row["phit_e (deg)"]),
        float(row["phir_n (deg)"]), float(row["phit_n (deg)"]), 6371, 0.5 * dtot)
    DN = P452.interp2(P452.DigitalMaps["DN50"], phim_e, phim_n, 1.5, 1.5)
    N0 = P452.interp2(P452.DigitalMaps["N050"], phim_e, phim_n, 1.5, 1.5)
    b0 = P452.beta0(phim_n, dtm, dlm)
    ae, _ab = P452.earth_rad_eff(DN)
    (hst, hsr, hstd, hsrd, hte, hre, hm, dlt, dlr, theta_t, theta_r, theta,
     pathtype) = P452.smooth_earth_heights(
        d, h, float(row["htg (m)"]), float(row["hrg (m)"]), ae,
        float(row["f (GHz)"]))
    hts = h[0] + float(row["htg (m)"])
    hrs = h[-1] + float(row["hrg (m)"])
    omega = P452.path_fraction(d, zone, 3)

    ref_path = 1 if row["path"].strip().lower() == "line of sight" else 2
    geom = [  # noqa: E501 — (computed, reference) pairs
        (ae, float(row["ae"])), (dtot, float(row["dtot"])),
        (hts, float(row["hts"])), (hrs, float(row["hrs"])),
        (theta_t, float(row["theta_t"])), (theta_r, float(row["theta_r"])),
        (theta, float(row["theta"])), (hm, float(row["hm"])),
        (hte, float(row["hte"])), (hre, float(row["hre"])),
        (hstd, float(row["hstd"])), (hsrd, float(row["hsrd"])),
        (dlt, float(row["dlt"])), (dlr, float(row["dlr"])),
        (pathtype, ref_path), (dtm, float(row["dtm"])),
        (dlm, float(row["dlm"])), (b0, float(row["b0"])),
        (omega, float(row["omega"])), (DN, float(row["DN"])),
        (N0, float(row["N0"])),
    ]
    worst_geom = _nan_aware_max(abs(a - b) for a, b in geom)

    worst_loss = 0.0
    n_over = 0
    for r0 in res:
        f = float(r0["f (GHz)"])
        p = float(r0["p (%)"])
        pol = int(float(r0["pol (1-h/2-v)"]))

        d3d = np.sqrt(dtot ** 2.0 + (hts - hrs) ** 2 / 1e6)
        lbfsg, lb0p, lb0b = P452.pl_los(
            d3d, f, p, b0, omega, float(r0["temp (deg C)"]),
            float(r0["press (hPa)"]), dlt, dlr)
        lbs = P452.tl_tropo(dtot, theta, f, p, float(r0["temp (deg C)"]),
                            float(r0["press (hPa)"]), N0,
                            float(r0["Gt (dBi)"]), float(r0["Gr (dBi)"]))
        lba = P452.tl_anomalous(
            dtot, dlt, dlr, float(r0["dct (km)"]), float(r0["dcr (km)"]),
            dlm, hts, hrs, hte, hre, hm, theta_t, theta_r, f, p,
            float(r0["temp (deg C)"]), float(r0["press (hPa)"]), omega, ae, b0)
        ldsph = P452.dl_se(dtot, hts - hstd, hrs - hsrd, ae, f,
                           omega)[pol - 1]
        ldp_pol, ld50_pol = P452.dl_p(d, g, hts, hrs, hstd, hsrd, f, omega,
                                      p, b0, DN)
        ldp, ld50 = ldp_pol[pol - 1], ld50_pol[pol - 1]
        lb = P452.bt_loss(f, p, d, h, g, zone,
                          float(r0["htg (m)"]), float(r0["hrg (m)"]),
                          float(r0["phit_e (deg)"]), float(r0["phit_n (deg)"]),
                          float(r0["phir_e (deg)"]), float(r0["phir_n (deg)"]),
                          float(r0["Gt (dBi)"]), float(r0["Gr (dBi)"]), pol,
                          float(r0["dct (km)"]), float(r0["dcr (km)"]),
                          float(r0["press (hPa)"]), float(r0["temp (deg C)"]))
        devs = (abs(lbfsg - float(r0["Lbfsg"])), abs(lb0p - float(r0["Lb0p"])),
                abs(lb0b - float(r0["Lb0b"])), abs(ldsph - float(r0["Ldsph"])),
                abs(ld50 - float(r0["Ld50"])), abs(ldp - float(r0["Ldp"])),
                abs(lbs - float(r0["Lbs"])), abs(lba - float(r0["Lba"])),
                abs(lb - float(r0["Lb"])))
        dev = _nan_aware_max(devs)
        if not (dev <= TOL):               # NaN counts as a failure
            n_over += 1
        if math.isnan(dev) or dev > worst_loss:   # NaN is sticky
            worst_loss = dev
    return worst_geom, worst_loss, len(res), n_over


def main():
    import numpy as np

    from emstudio.coverage import itu_maps

    print("EMStudio P.452-18 validation gate (official CG-3M examples)")

    if itu_maps.find_npz("P452.npz") is None:
        check("ITU digital maps installed (P452.npz)", False,
              "run emstudio.coverage.itu_maps.install_p452_maps() once — "
              "the maps are ITU integral products and cannot ship in-repo")
        print("P452 GATE FAILED: {0}".format(FAILURES))
        return 1

    from emstudio.vendor.py452 import P452

    prof_dir = os.path.join(DATA, "profiles")
    files = sorted(f for f in os.listdir(prof_dir) if f.endswith(".csv"))
    check("all 17 official profiles present", len(files) == 17, str(len(files)))

    n_total = 0
    n_over = 0
    n_geom_bad = 0
    worst_g = 0.0
    worst_l = 0.0
    worst_file = ""
    for fn in files:
        wg, wl, n, nov = _run_profile(
            np, P452, os.path.join(prof_dir, fn),
            os.path.join(DATA, "results",
                         fn.replace("test_profile", "test_result")))
        n_total += n
        n_over += nov
        if not (wg <= TOL):                       # NaN counts as a failure
            n_geom_bad += 1
        if math.isnan(wg) or wg > worst_g:        # NaN is sticky
            worst_g = wg
        if math.isnan(wl) or wl > worst_l:
            worst_l = wl
            worst_file = fn
    check("all 595 official cases replayed", n_total == 595, str(n_total))
    check("path-geometry intermediates match <= 1e-6 on every profile",
          n_geom_bad == 0,
          "{0} profiles over; worst {1:.2e}".format(n_geom_bad, worst_g))
    check("Lb + 8 sub-model losses match <= 1e-6 dB on every case",
          n_over == 0,
          "{0} cases over; worst {1:.2e} dB ({2})".format(n_over, worst_l,
                                                          worst_file))

    # the EMStudio wrapper reproduces the engine + enforces validity
    from emstudio.coverage import p452 as wrap

    d, h, r_, zone = _read_profile(
        os.path.join(prof_dir, "test_profile_flat_land_100km.csv"), np)
    r0 = _read_results(os.path.join(
        DATA, "results", "test_result_flat_land_100km.csv"))[0]
    lb_wrap = wrap.path_loss_db(
        float(r0["f (GHz)"]), float(r0["p (%)"]), d, h, zone,
        float(r0["htg (m)"]), float(r0["hrg (m)"]),
        lat_t=float(r0["phit_n (deg)"]), lat_r=float(r0["phir_n (deg)"]),
        lon_t=float(r0["phit_e (deg)"]), lon_r=float(r0["phir_e (deg)"]),
        clutter_m=r_, gt_dbi=float(r0["Gt (dBi)"]),
        gr_dbi=float(r0["Gr (dBi)"]), pol=int(float(r0["pol (1-h/2-v)"])),
        dct_km=float(r0["dct (km)"]), dcr_km=float(r0["dcr (km)"]),
        press_hpa=float(r0["press (hPa)"]), temp_c=float(r0["temp (deg C)"]))
    check("wrapper reproduces the official case (<= 1e-6 dB)",
          abs(lb_wrap - float(r0["Lb"])) <= TOL,
          "{0:.6f} vs {1}".format(lb_wrap, r0["Lb"]))
    try:
        wrap.path_loss_db(60.0, 20.0, d, h, zone, 10.0, 10.0,
                          0.0, 0.0, 0.0, 1.0)
        oob = False
    except ValueError:
        oob = True
    check("wrapper rejects out-of-validity frequency (60 GHz)", oob)

    if FAILURES:
        print("P452 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("P452 GATE PASSED")
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
        raise SystemExit("p452 validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("p452 validation failed")
    sys.exit(0)
