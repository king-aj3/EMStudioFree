# SPDX-License-Identifier: LGPL-2.1-or-later
"""ITU-R P.1812-6 path-specific propagation + delta-Bullington (ROADMAP §6-D).

Thin EMStudio face over the vendored **ITU-R reference implementation**
(``emstudio/vendor/py1812`` — Py1812 by I. Stevanovic/OFCOM; permissive
license, PROVENANCE.md there). Two entry points:

* :func:`path_loss_db` — the full P.1812-6 basic transmission loss / field
  strength for a terrain profile (LoS+diffraction+troposcatter+ducting).
  ``dn``/``n0`` must be supplied (the ITU digital maps are NOT bundled;
  DN ~ 45 N-units/km and N0 ~ 325 are mid-latitude typicals — pass real
  values for your region, or install the maps per the vendor PROVENANCE).
* :func:`delta_bullington_intermediates` — the **delta-Bullington diffraction
  sub-model** (§4.3.4: complete Bullington on the real profile + on the
  smooth profile + spherical-earth term), exposed with the exact input
  construction ``bt_loss`` uses; returns Ld and the Eq-21/27 intermediates.

Validity (Recommendation §1): 30 MHz - 6 GHz, 0.25 - 3000 km, time
percentage 1 - 50 %. Enforced here — no silent extrapolation.

Gate: ``tests/validation/p1812.py`` replays the official ITU-R SG3 P.1812-6
validation examples (19 profiles / 63 datasets) — final Lb/Ep to 0.01 dB and
the delta-Bullington intermediates against the official per-equation logs.
"""
from __future__ import annotations


def check_validity(freq_mhz, time_pct, d_km):
    """Raise ValueError outside the P.1812-6 validity ranges."""
    if not 30.0 <= float(freq_mhz) <= 6000.0:
        raise ValueError("P.1812 validity is 30-6000 MHz (got {0:g} MHz)"
                         .format(freq_mhz))
    if not 1.0 <= float(time_pct) <= 50.0:
        raise ValueError("P.1812 time percentage must be 1-50% (got {0:g}%)"
                         .format(time_pct))
    if not 0.25 <= float(d_km) <= 3000.0:
        raise ValueError("P.1812 path length must be 0.25-3000 km (got "
                         "{0:g} km)".format(d_km))


def delta_bullington_intermediates(x_km, h_amsl_m, clutter_m, zone,
                                   htg_m, hrg_m, freq_ghz, dn=45.0, pol=1):
    """Delta-Bullington diffraction (P.1812-6 §4.3.4) over a profile.

    Inputs mirror the Recommendation: profile distances (km) + terrain
    heights (m amsl) + representative clutter heights (m; scalar or vector;
    endpoints are zeroed per §3.2) + zone codes (vector; 1 = sea, 3 =
    coastal, 4 = inland — a scalar 4 means an all-inland path), antenna
    heights above ground, frequency (GHz), the refractivity lapse DN and the
    polarization (1 horizontal, 2 vertical — affects the spherical-earth
    term over sea). Returns a dict: ``ld50_db`` — the MEDIAN combined
    delta-Bullington loss (Eq 39, effective earth radius ae of Eq 7a; the
    quantity to use as "the" delta-Bullington diffraction loss) — plus
    ``lbulla``/``lbulls``/``ldsph`` (Eq 21/27) evaluated at the β0 effective
    radius ab (Eq 7b), which is what the reference ``dl_p`` computes last and
    the official validation logs record, and ``omega``.
    """
    import numpy as np

    from emstudio.vendor.py1812 import P1812

    d = np.asarray(x_km, dtype=float)
    h = np.asarray(h_amsl_m, dtype=float)
    r = np.zeros_like(h) + np.asarray(clutter_m, dtype=float)
    z = np.zeros_like(h) + np.asarray(zone, dtype=float)
    if d.shape != h.shape or len(d) < 2:
        raise ValueError("profile needs matching x/h vectors (>= 2 points)")
    ip = int(pol) - 1
    if ip not in (0, 1):
        raise ValueError("pol must be 1 (horizontal) or 2 (vertical)")

    ae, ab = P1812.earth_rad_eff(float(dn))
    omega = P1812.path_fraction(d, z, 1)
    (_hst_n, _hsr_n, _hst, _hsr, hstd, hsrd, _hte, _hre, _hm, _dlt, _dlr,
     _tht, _thr, _th, _ptype) = P1812.smooth_earth_heights(
        d, h, r, float(htg_m), float(hrg_m), ae, float(freq_ghz))

    hts = h[0] + float(htg_m)
    hrs = h[-1] + float(hrg_m)
    g = h + r
    g[0] = h[0]
    g[-1] = h[-1]

    def _pick(v):
        v = np.atleast_1d(v)
        return float(v[ip]) if v.size > 1 else float(v[0])

    ld50, _la, _ls, _lsp = P1812.dl_delta_bull(
        d, g, hts, hrs, hstd, hsrd, ae, float(freq_ghz), omega, 0)
    _ldb, lbulla, lbulls, ldsph = P1812.dl_delta_bull(
        d, g, hts, hrs, hstd, hsrd, ab, float(freq_ghz), omega, 0)
    return {
        "ld50_db": _pick(ld50),
        "lbulla": _pick(lbulla),
        "lbulls": _pick(lbulls),
        "ldsph": _pick(ldsph),
        "omega": float(omega),
    }


def path_loss_db(freq_mhz, time_pct, x_km, h_amsl_m, clutter_m, zone,
                 htg_m, hrg_m, lat_t, lat_r, lon_t, lon_r, dn=45.0, n0=325.0,
                 pol=1, erp_kw=1.0, **kwargs):
    """Full P.1812-6 basic transmission loss (dB) + field strength (dBµV/m).

    ``pol``: 1 horizontal, 2 vertical. ``dn``/``n0``: refractivity lapse and
    sea-level surface refractivity for the path region (the ITU digital maps
    are not bundled — see the module docstring). Extra keyword arguments
    (``dct``, ``dcr``, ``pL``, ``sigmaL``, ``flag4``…) pass through to the
    vendored ``bt_loss``.
    """
    import numpy as np

    d = np.asarray(x_km, dtype=float)
    check_validity(freq_mhz, time_pct, float(d[-1] - d[0]))
    h = np.asarray(h_amsl_m, dtype=float)
    r = np.zeros_like(h) + np.asarray(clutter_m, dtype=float)
    z = np.zeros_like(h) + np.asarray(zone, dtype=float)

    from emstudio.vendor.py1812 import P1812

    lb, ep = P1812.bt_loss(
        float(freq_mhz) / 1e3, float(time_pct), d, h, r, z,
        float(htg_m), float(hrg_m), int(pol),
        float(lat_t), float(lat_r), float(lon_t), float(lon_r),
        DN=float(dn), N0=float(n0), Ptx=float(erp_kw),
        debug=0, fid_log=-1, **kwargs)
    return float(lb), float(ep)
