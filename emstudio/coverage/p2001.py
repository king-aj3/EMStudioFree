# SPDX-License-Identifier: LGPL-2.1-or-later
"""ITU-R P.2001-6 wide-range terrestrial propagation model (ROADMAP §6-D).

Thin EMStudio face over the vendored **ITU-R reference implementation**
(``emstudio/vendor/py2001`` — Py2001 by I. Stevanovic/OFCOM + A. Demarez;
permissive license, PROVENANCE.md there). P.2001 is the general-purpose
model: one method covering the full fading AND enhancement distribution
(0-100 % of an average year) — the model behind modern Monte-Carlo spectrum
studies.

The 14 ITU digital map files are NOT bundled — install them once via
:func:`emstudio.coverage.itu_maps.install_p2001_maps` (downloads the
official Recommendation zip, or takes your own copy); until then any call
raises with those instructions.

Validity (Recommendation §1.1): 30 MHz - 50 GHz, path length 3 - 1000 km,
time percentage 0 - 100 % (exclusive). Enforced here — no silent
extrapolation.

Gate: ``tests/validation/p2001.py`` replays the official ITU-R validation
examples (2 profiles / 4430 cases) against the reference Lb.
"""
from __future__ import annotations


def check_validity(freq_ghz, time_pct, d_km):
    """Raise ValueError outside the P.2001-6 validity ranges."""
    if not 0.03 <= float(freq_ghz) <= 50.0:
        raise ValueError("P.2001 validity is 0.03-50 GHz (got {0:g} GHz)"
                         .format(freq_ghz))
    if not 0.0 < float(time_pct) < 100.0:
        raise ValueError("P.2001 time percentage must be inside (0, 100)% "
                         "(got {0:g}%)".format(time_pct))
    if not 3.0 <= float(d_km) <= 1000.0:
        raise ValueError("P.2001 path length should be 3-1000 km (got "
                         "{0:g} km)".format(d_km))


def path_loss_db(freq_ghz, time_pct, x_km, h_amsl_m, zone,
                 htg_m, hrg_m, lat_t, lat_r, lon_t, lon_r,
                 gt_dbi=0.0, gr_dbi=0.0, vertical=True):
    """P.2001-6 basic transmission loss (dB) over a terrain profile.

    :param x_km: profile distances from the transmitter, km (x[0] = 0).
    :param h_amsl_m: terrain heights, m above mean sea level.
    :param zone: per-point zone codes — 1 sea, 3 coastal land, 4 inland
        (scalar 4 = all-inland path; note these differ from the P.452 codes).
    :param time_pct: percentage of an average year for which the loss is not
        exceeded, 0 < Tpc < 100 (covers fades AND enhancements).
    :param lat_t/lon_t, lat_r/lon_r: terminal coordinates, degrees (drive all
        14 radio-climatic map lookups).
    :param vertical: True for vertical polarization, False horizontal.
    :returns: Lb, dB.
    """
    import numpy as np

    d = np.asarray(x_km, dtype=float)
    h = np.asarray(h_amsl_m, dtype=float)
    z = np.zeros_like(h) + np.asarray(zone, dtype=float)
    if d.shape != h.shape or len(d) < 2:
        raise ValueError("profile needs matching x/h vectors (>= 2 points)")
    check_validity(freq_ghz, time_pct, float(d[-1] - d[0]))

    from emstudio.vendor.py2001 import P2001

    lb = P2001.bt_loss(d, h, z, float(freq_ghz), float(time_pct),
                       float(lon_r), float(lat_r), float(lon_t), float(lat_t),
                       float(hrg_m), float(htg_m),
                       float(gr_dbi), float(gt_dbi),
                       1 if vertical else 0)
    return float(lb)
