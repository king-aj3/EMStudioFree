# SPDX-License-Identifier: LGPL-2.1-or-later
"""Area coverage heatmap for one station (ROADMAP §6, phase B).

Predict a transmitter's received-power / field-strength footprint over a lat/lon
grid, built on the shipped, textbook-validated point-to-point models in
:mod:`emstudio.coverage.propagation` and modulated by the antenna azimuth pattern
(:mod:`emstudio.coverage.pattern`). Two modes, one code path:

* **no DEM** (``dem=None``) — the fast analytic footprint: free-space (Friis)
  loss, switching to the two-ray plane-earth (d^4) law beyond the breakpoint.
  Degenerates EXACTLY to a ``link_budget`` over ``free_space_path_loss_db`` for a
  cleared omni link (the gate checks this).
* **with a DEM** — the terrain-aware footprint: a great-circle path profile per
  grid point (:func:`emstudio.coverage.terrain.path_profile`) through the shipped
  single-edge Deygout ``terrain_profile_loss`` (earth-bulge included), so hills
  shadow the map.

Per cell it reports received power (dBm) and field strength (dBuV/m). Pure-python
+ numpy, Qt-free, FreeCAD-free. Transmitter location is user-supplied.
"""
from __future__ import annotations

import numpy as np

from emstudio.coverage import (empirical, geodesy, groundwave,
                               pattern as pattern_mod, propagation, terrain)


class CoverageResult:
    """A coverage grid: metrics over ``lats`` x ``lons`` (both ascending)."""

    def __init__(self, lats, lons, prx_dbm, field_dbuv_m, dist_m, meta=None):
        self.lats = np.asarray(lats, dtype=float)          # (nlat,)
        self.lons = np.asarray(lons, dtype=float)          # (nlon,)
        self.prx_dbm = np.asarray(prx_dbm, dtype=float)    # (nlat, nlon)
        self.field_dbuv_m = np.asarray(field_dbuv_m, dtype=float)
        self.dist_m = np.asarray(dist_m, dtype=float)
        self.meta = dict(meta or {})

    @property
    def bounds(self):
        """(north, south, east, west) for a KML LatLonBox."""
        return (float(self.lats.max()), float(self.lats.min()),
                float(self.lons.max()), float(self.lons.min()))

    def grid(self, metric="prx"):
        return self.field_dbuv_m if metric.startswith("field") else self.prx_dbm

    def coverage_fraction(self, threshold, metric="prx"):
        """Fraction of grid cells at or above ``threshold`` in the chosen metric."""
        g = self.grid(metric)
        valid = ~np.isnan(g)
        if not valid.any():
            return 0.0
        return float(np.count_nonzero(g[valid] >= threshold) / np.count_nonzero(valid))


def _dbm_to_dbw(dbm):
    return dbm - 30.0


def coverage_grid(tx_lat, tx_lon, tx_height_m, freq_hz, tx_power_dbm,
                  dem=None, radius_m=30000.0, n=81, pattern=None,
                  peak_gain_dbi=2.15, rx_height_m=2.0, rx_gain_dbi=0.0,
                  k_factor=4.0 / 3.0, profile_samples=48, model="auto",
                  ground=None, lats=None, lons=None, diffraction="single",
                  ground_reflection=False, environment="urban",
                  gw_engine="flat"):
    """Compute a :class:`CoverageResult` centred on the transmitter.

    :param pattern: an :class:`~emstudio.coverage.pattern.AzimuthPattern` (absolute
        dBi) modulating gain vs bearing, or ``None`` for omni at ``peak_gain_dbi``.
    :param radius_m: half-width of the (square) map, metres.
    :param n: grid points per side.
    :param k_factor: effective-earth-radius factor (4/3 standard; large disables
        curvature). Only affects the terrain/plane-earth horizon, not free space.
    :param model: ``"auto"`` (free-space, switching to two-ray plane-earth beyond the
        breakpoint; terrain-aware when a ``dem`` is given), ``"ground_wave"`` (the
        ITU-R P.368 LF/MF surface-wave over homogeneous ``ground`` — a smooth-earth
        model that ignores the DEM) or ``"hata"`` (the Okumura-Hata / COST-231
        empirical land-mobile clutter model over ``environment`` — also ignores the
        DEM; tx/rx heights are the base/mobile heights).
    :param environment: Hata clutter category for ``model="hata"`` — ``"urban"``,
        ``"urban_large"``, ``"suburban"`` or ``"open"``. Ignored otherwise.
    :param gw_engine: engine for ``model="ground_wave"`` — ``"flat"`` (the Norton
        flat-earth surface wave, valid to ~100 km; default, byte-identical to
        earlier releases) or ``"p368"`` (the ITU-R P.368-10 spherical earth —
        flat-earth Sommerfeld switching to the Wait/Hufford residue series —
        valid 0.01-30 MHz out to 10000 km, ground-based reference terminals;
        needs scipy and raises below 10 kHz rather than extrapolate).
        Ignored otherwise.
    :param ground: ``(eps_r, sigma)`` for the ground-wave model (default average
        ground). Ignored for ``model="auto"``.
    :param lats: optional explicit ascending latitude axis (degrees). When both
        ``lats`` and ``lons`` are given the map is evaluated on that shared grid
        instead of a tx-centred ``radius_m``/``n`` box — this is how the multi-station
        composer (:mod:`emstudio.coverage.multistation`) puts several transmitters on
        one common grid. The transmitter still sits at ``tx_lat``/``tx_lon`` (it need
        not be the grid centre). Omitting them is byte-identical to the tx-centred box.
    :param lons: optional explicit ascending longitude axis (degrees); see ``lats``.
    :param diffraction: terrain diffraction method for the DEM branch — ``"single"``
        (dominant edge, default, byte-identical to earlier releases), ``"deygout"``
        (recursive multi-edge), ``"epstein_peterson"`` or ``"bullington"``.
    :param ground_reflection: with a DEM, apply the two-ray plane-earth switch on
        geometrically CLEAR paths (no terrain above the direct ray) — it REPLACES
        the near-grazing knife-edge term there (which would double-count the
        ground), so a flat DEM degenerates exactly to the smooth-earth footprint;
        obstructed paths keep free-space + diffraction. Default off
        (byte-identical to earlier releases).

    Received power = Ptx + Gtx(bearing) + Grx - path_loss. Field strength uses the
    per-bearing EIRP. NaN where distance is ~0 (the transmitter cell).
    """
    if pattern is None:
        pattern = pattern_mod.omni(peak_gain_dbi)
    if ground is None:
        ground = groundwave.GROUND_TYPES["Average ground"]
    gw_eps_r, gw_sigma = float(ground[0]), float(ground[1])

    if lats is None or lons is None:
        lat_m, lon_m = geodesy.meters_per_degree(tx_lat)
        dlat = radius_m / lat_m
        dlon = radius_m / max(lon_m, 1.0)
        lats = np.linspace(tx_lat - dlat, tx_lat + dlat, n)
        lons = np.linspace(tx_lon - dlon, tx_lon + dlon, n)
    else:
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
    n_lat, n_lon = len(lats), len(lons)

    prx = np.full((n_lat, n_lon), np.nan)
    field = np.full((n_lat, n_lon), np.nan)
    dist = np.full((n_lat, n_lon), np.nan)

    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            d = geodesy.haversine_m(tx_lat, tx_lon, la, lo)
            dist[i, j] = d
            if d < 1.0:
                continue
            bearing = geodesy.initial_bearing_deg(tx_lat, tx_lon, la, lo)
            gtx = pattern.gain_at(bearing)

            if model == "ground_wave":
                # LF/MF surface wave over homogeneous ground; the EIRP (with the
                # per-bearing gain) sets the cymomotive force, the DEM is ignored.
                eirp_w = 10.0 ** (_dbm_to_dbw(tx_power_dbm + gtx) / 10.0)
                cmf = groundwave.cmf_from_eirp(eirp_w)
                if gw_engine == "p368":
                    e = groundwave.spherical_field_strength_dbuv_m(
                        d, freq_hz, gw_eps_r, gw_sigma, cmf_v=cmf)
                else:
                    e = groundwave.field_strength_dbuv_m(d, freq_hz, gw_eps_r,
                                                         gw_sigma, cmf_v=cmf)
                field[i, j] = e
                prx[i, j] = groundwave.field_to_prx_dbm(e, freq_hz, rx_gain_dbi)
                continue

            if model == "hata":
                # empirical land-mobile clutter loss; the DEM is ignored (the
                # environment category IS the clutter model)
                loss = empirical.empirical_loss_db(d, freq_hz, tx_height_m,
                                                   rx_height_m, environment)
                prx[i, j] = tx_power_dbm + gtx + rx_gain_dbi - loss
                eirp_w = 10.0 ** (_dbm_to_dbw(tx_power_dbm + gtx) / 10.0)
                e_free = propagation.field_strength_dbuv_m(eirp_w, d)
                fspl = propagation.free_space_path_loss_db(d, freq_hz)
                field[i, j] = e_free - (loss - fspl)
                continue

            if dem is None:
                fspl = propagation.free_space_path_loss_db(d, freq_hz)
                bp = propagation.plane_earth_breakpoint_m(tx_height_m, rx_height_m,
                                                          freq_hz)
                if k_factor > 0 and d > bp:
                    pe = propagation.plane_earth_loss_db(d, tx_height_m, rx_height_m)
                    path_loss = max(fspl, pe)  # plane-earth governs past breakpoint
                    diff = path_loss - fspl
                else:
                    path_loss = fspl
                    diff = 0.0
            else:
                prof = terrain.path_profile(dem, tx_lat, tx_lon, la, lo,
                                            n_samples=profile_samples,
                                            k_factor=k_factor)
                res = propagation.terrain_profile_loss(prof, tx_height_m,
                                                       rx_height_m, freq_hz,
                                                       method=diffraction)
                path_loss = res["total_loss_db"]
                diff = res["diffraction_db"]
                if ground_reflection:
                    # geometrically CLEAR path (no terrain above the direct ray):
                    # the two-ray plane-earth model REPLACES the near-grazing
                    # knife-edge term (which would double-count the ground) —
                    # mirroring the no-DEM branch exactly, so a flat DEM
                    # degenerates to the smooth-earth footprint. Obstructed paths
                    # keep free-space + diffraction untouched.
                    z_tx = prof[0][1] + tx_height_m
                    z_rx = prof[-1][1] + rx_height_m
                    d_tot = prof[-1][0]
                    clear = True
                    for dd, zz in prof[1:-1]:
                        if zz > z_tx + (z_rx - z_tx) * (dd / d_tot) + 1e-9:
                            clear = False
                            break
                    if clear:
                        path_loss = res["fspl_db"]
                        bp = propagation.plane_earth_breakpoint_m(
                            tx_height_m, rx_height_m, freq_hz)
                        if k_factor > 0 and d > bp:
                            pe = propagation.plane_earth_loss_db(
                                d, tx_height_m, rx_height_m)
                            path_loss = max(path_loss, pe)
                        diff = path_loss - res["fspl_db"]

            prx[i, j] = tx_power_dbm + gtx + rx_gain_dbi - path_loss
            # field strength from the per-bearing EIRP, less any diffraction loss
            eirp_w = 10.0 ** (_dbm_to_dbw(tx_power_dbm + gtx) / 10.0)
            e_free = propagation.field_strength_dbuv_m(eirp_w, d)
            field[i, j] = e_free - diff

    meta = {
        "tx_lat": float(tx_lat), "tx_lon": float(tx_lon),
        "tx_height_m": float(tx_height_m), "freq_hz": float(freq_hz),
        "tx_power_dbm": float(tx_power_dbm), "peak_gain_dbi": float(pattern.peak_dbi()),
        "radius_m": float(radius_m), "n": int(n_lat), "has_dem": dem is not None,
        "k_factor": float(k_factor), "model": model,
        "ground": (gw_eps_r, gw_sigma) if model == "ground_wave" else None,
        "gw_engine": gw_engine if model == "ground_wave" else None,
        "diffraction": diffraction if (dem is not None and model != "ground_wave")
        else None,
        "ground_reflection": bool(ground_reflection) if dem is not None else None,
        "environment": environment if model == "hata" else None,
    }
    return CoverageResult(lats, lons, prx, field, dist, meta=meta)
