# SPDX-License-Identifier: LGPL-2.1-or-later
"""ITU-R P.452-18 interference prediction (ROADMAP §6-D).

Thin EMStudio face over the vendored **ITU-R reference implementation**
(``emstudio/vendor/py452`` — Py452 by I. Stevanovic/OFCOM; permissive
license, PROVENANCE.md there). P.452 predicts the basic transmission loss
not exceeded for ``p`` % of time between two stations on the surface of the
Earth (the interference-coordination model: LoS + diffraction + troposcatter
+ anomalous ducting/layer-reflection, with gaseous absorption).

The ITU digital maps (DN50/N050) are NOT bundled — install them once via
:func:`emstudio.coverage.itu_maps.install_p452_maps` (downloads the official
Recommendation zip, or takes your own copy of it); until then any call
raises with those instructions.

Validity (Recommendation §1): ~0.1 - 50 GHz, time percentage 0.001 - 50 %.
Enforced here — no silent extrapolation.

Gate: ``tests/validation/p452.py`` replays the official CG-3M validation
examples (17 profiles / 595 cases) — final Lb and eight sub-model losses.
"""
from __future__ import annotations


def check_validity(freq_ghz, time_pct):
    """Raise ValueError outside the P.452-18 validity ranges."""
    if not 0.1 <= float(freq_ghz) <= 50.0:
        raise ValueError("P.452 validity is 0.1-50 GHz (got {0:g} GHz)"
                         .format(freq_ghz))
    if not 0.001 <= float(time_pct) <= 50.0:
        raise ValueError("P.452 time percentage must be 0.001-50% (got "
                         "{0:g}%)".format(time_pct))


def path_loss_db(freq_ghz, time_pct, x_km, h_amsl_m, zone,
                 htg_m, hrg_m, lat_t, lat_r, lon_t, lon_r,
                 clutter_m=0.0, gt_dbi=0.0, gr_dbi=0.0, pol=1,
                 dct_km=500.0, dcr_km=500.0, press_hpa=1013.25, temp_c=15.0):
    """P.452-18 basic transmission loss (dB) over a terrain profile.

    :param x_km: profile distances from the interferer, km (ascending, x[0]=0).
    :param h_amsl_m: terrain heights, m above mean sea level.
    :param zone: per-point radio-zone codes — 1 coastal land, 2 inland, 3 sea
        (scalar 2 = all-inland path).
    :param htg_m / hrg_m: interferer / interfered-with antenna heights above
        ground, m.
    :param lat_t/lon_t, lat_r/lon_r: terminal coordinates, degrees (drive the
        DN50/N050 digital-map lookups at the path midpoint).
    :param clutter_m: representative ground-cover height, m (scalar or
        per-point vector; the P.452-18 §4.5 additional clutter losses come
        from the height-gain model built into the reference implementation;
        endpoints within 50 m of the terminals are zeroed per the harness).
    :param pol: 1 horizontal, 2 vertical (spherical-earth term over sea).
    :param dct_km / dcr_km: distance of each terminal from the coast along
        the path, km (500 = deep inland, the Recommendation default).
    :param press_hpa / temp_c: surface pressure and temperature (gaseous
        absorption).
    :returns: Lb, dB (basic transmission loss not exceeded for time_pct %).
    """
    import numpy as np

    check_validity(freq_ghz, time_pct)
    d = np.asarray(x_km, dtype=float)
    h = np.asarray(h_amsl_m, dtype=float)
    z = np.zeros_like(h) + np.asarray(zone, dtype=float)
    r = np.zeros_like(h) + np.asarray(clutter_m, dtype=float)
    if d.shape != h.shape or len(d) < 2:
        raise ValueError("profile needs matching x/h vectors (>= 2 points)")
    if int(pol) not in (1, 2):
        raise ValueError("pol must be 1 (horizontal) or 2 (vertical)")

    # radio profile g: terrain + cover, with the terminal 50-m ends cleared
    # (the official harness's Step-4 construction)
    g = h + r
    kk = np.where(d < 50.0 / 1000.0)[0]
    g[kk] = h[kk]
    kk = np.where(d > d[-1] - 50.0 / 1000.0)[0]
    g[kk] = h[kk]

    from emstudio.vendor.py452 import P452

    lb = P452.bt_loss(float(freq_ghz), float(time_pct), d, h, g, z,
                      float(htg_m), float(hrg_m),
                      float(lon_t), float(lat_t), float(lon_r), float(lat_r),
                      float(gt_dbi), float(gr_dbi), int(pol),
                      float(dct_km), float(dcr_km),
                      float(press_hpa), float(temp_c))
    return float(lb)
