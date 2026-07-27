# SPDX-License-Identifier: LGPL-2.1-or-later
"""Multi-station service & interference (D/U) contours (ROADMAP §6, phase C).

Compose two or more single-station coverage grids
(:func:`emstudio.coverage.heatmap.coverage_grid`) onto ONE shared lat/lon grid and,
per cell, threshold the wanted-to-unwanted field-strength ratio (D/U) against an
FCC/ITU protection ratio to classify service the way broadcast/land-mobile
engineers do:

  * **Gate A — coverage (noise-limited):** the wanted station's field is at or above
    a protected/service threshold (dB(uV/m));
  * **Gate B — interference-limited:** ``D/U = E_wanted - E_unwanted >= protection
    ratio``, the unwanted field being the aggregate of the co-channel interferers.

A cell is ``SERVED`` (interference-free) only when BOTH gates pass; passing A but
failing B is ``INTERFERENCE_LIMITED``; failing A is ``NO_SERVICE``. Adjacent-channel
protection ratios are legitimately negative (receiver selectivity lets the undesired
exceed the desired) — the D/U threshold is NOT clamped to positive.

Interferers are aggregated by **incoherent power sum** of field strengths —
``E_comb = 10*log10(sum 10^(E_i/10))`` dB(uV/m), i.e. root-sum-square in power, so
two equal fields add exactly ``10*log10(2) = +3.0103 dB`` (ITU-R BT.2265 eq.13 /
NTIA TM-10-469; the AM rule 47 CFR 73.182(k) is the same operation in linear field
units) — or ``worst_case`` (the single strongest interferer, the FCC OET-69 DTV
pass/fail policy).

Reuses the §5 co-site D/U logic (:mod:`emstudio.cosite.interference` —
``du_ratio_db`` / ``in_band``) and the shipped, textbook-validated field-strength
engine (``heatmap`` / ``groundwave`` / ``propagation``). Pure-python + numpy,
Qt-free, FreeCAD-free. Station locations / frequencies / ground are user-supplied;
no specific sites are referenced.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from emstudio.coverage import geodesy, groundwave, heatmap
from emstudio.cosite import interference as ci

# --- cell classification -----------------------------------------------------
NO_SERVICE = 0            # Gate A fails: below the service/coverage threshold
INTERFERENCE_LIMITED = 1  # in coverage but D/U below the protection ratio
SERVED = 2                # in coverage AND protected (interference-free)


# --- reference protection ratios (D/U, dB) -----------------------------------
# name -> (du_db, primary source). These are REGULATORY/PLANNING reference values,
# NOT universal physical constants — pick the row matching the service and region
# (they are region- and method-dependent; see the notes). All site-name-free.
PROTECTION_RATIOS = {
    "FM co-channel (FCC 73.215)": (20.0, "47 CFR 73.215(a)(2) — contour spacing"),
    "FM 1st-adjacent 200 kHz (FCC)": (6.0, "47 CFR 73.215(a)(2)"),
    "FM 2nd/3rd-adjacent (FCC commercial)": (-40.0, "47 CFR 73.215(a)(2)"),
    "FM co-channel stereo, steady (ITU-R BS.412)": (45.0, "ITU-R BS.412-9 Table 3"),
    "FM co-channel mono, steady (ITU-R BS.412)": (36.0, "ITU-R BS.412-9 Table 3"),
    "AM/MF co-channel (FCC / ITU Region 2)": (26.0, "47 CFR 73.182(r); ITU-R BS.560-4"),
    "AM/MF co-channel (GE75 Regions 1&3)": (30.0, "ITU-R BS.560-4 / GE75 ground-wave"),
    "AM/MF 1st-adjacent 10 kHz (FCC)": (6.0, "47 CFR 73.182(r)"),
    "DTV co-channel (FCC)": (15.0, "47 CFR 73.620 (rounded rule value)"),
    "Analog TV 625-line co-channel, tropospheric (ITU-R BT.655)": (30.0, "ITU-R BT.655-7"),
}

# name -> (protected field dB(uV/m), primary source). The Gate-A service threshold.
SERVICE_THRESHOLDS_DBUV_M = {
    "FM protected contour, most classes (60 dBuV/m)": (60.0, "47 CFR 73.215(a)(1)"),
    "FM Class B (57 dBuV/m)": (57.0, "47 CFR 73.215(a)(1)"),
    "FM Class B1 (54 dBuV/m)": (54.0, "47 CFR 73.215(a)(1)"),
    "AM primary service 2 mV/m (66 dBuV/m)": (66.02, "47 CFR 73.182(d)"),
    "AM protected 0.5 mV/m (54 dBuV/m)": (53.98, "47 CFR 73.182(q)"),
}


@dataclass
class Station:
    """One transmitter for the composite map. Omni in azimuth unless a ``pattern``
    (an :class:`emstudio.coverage.pattern.AzimuthPattern`) is supplied."""
    label: str
    lat: float
    lon: float
    height_m: float = 30.0
    freq_hz: float = 1.0e6
    power_dbm: float = 60.0
    peak_gain_dbi: float = 0.0
    pattern: object = None


# --- field-strength aggregation ---------------------------------------------
def combine_fields_dbuv_m(fields, method="power_sum"):
    """Aggregate interfering field strengths (dB(uV/m)) into one 'unwanted' field.

    ``power_sum`` — incoherent RSS-in-power ``10*log10(sum 10^(E_i/10))`` (ITU-R
    BT.2265 / NTIA; two equal fields add exactly ``10*log10(2)=+3.0103 dB``, N equal
    add ``10*log10(N)``). ``worst_case`` — the single strongest field (the FCC
    OET-69 DTV pass/fail policy: highest per-cell undesired only). A NaN (a station's
    own transmitter cell) propagates, so those few cells stay masked. Returns ``None``
    for an empty list.
    """
    arrs = [np.asarray(f, dtype=float) for f in fields]
    if not arrs:
        return None
    stack = np.stack(arrs, axis=0)          # (k, nlat, nlon)
    if method == "worst_case":
        return np.max(stack, axis=0)        # NaN propagates -> masked tx cells
    if method != "power_sum":
        raise ValueError("method must be 'power_sum' or 'worst_case'")
    return 10.0 * np.log10(np.sum(np.power(10.0, stack / 10.0), axis=0))


def classify(wanted_field, unwanted_field, service_threshold_dbuv_m,
             protection_ratio_db):
    """Per-cell (NO_SERVICE / INTERFERENCE_LIMITED / SERVED, D/U) via the two gates.

    ``unwanted_field=None`` means no interferers (Gate B always passes, D/U=+inf).
    The wanted transmitter cell is NaN, so Gate A fails there -> NO_SERVICE. The D/U
    threshold is applied as written (may be negative for adjacent channels).
    """
    wanted = np.asarray(wanted_field, dtype=float)
    in_cov = wanted >= float(service_threshold_dbuv_m)   # NaN -> False (tx cell)
    if unwanted_field is None:
        du = np.full(wanted.shape, np.inf)
    else:
        du = wanted - np.asarray(unwanted_field, dtype=float)
    protected = du >= float(protection_ratio_db)         # +inf >= x -> True
    cls = np.full(wanted.shape, NO_SERVICE, dtype=np.int8)
    cls[in_cov & ~protected] = INTERFERENCE_LIMITED
    cls[in_cov & protected] = SERVED
    return cls, du


# --- shared grid + per-station fields ---------------------------------------
def _shared_grid(center_lat, center_lon, radius_m, n):
    lat_m, lon_m = geodesy.meters_per_degree(center_lat)
    dlat = radius_m / lat_m
    dlon = radius_m / max(lon_m, 1.0)
    lats = np.linspace(center_lat - dlat, center_lat + dlat, n)
    lons = np.linspace(center_lon - dlon, center_lon + dlon, n)
    return lats, lons


def station_fields(stations, lats, lons, model="auto", ground=None, dem=None,
                   rx_height_m=2.0, k_factor=4.0 / 3.0, gw_engine="flat"):
    """Field-strength grid (dB(uV/m)) for each station on the shared (lats, lons).

    Each station is evaluated on the SAME grid via ``heatmap.coverage_grid``'s
    explicit-grid mode, so the cells line up for a per-cell comparison. All stations
    share one propagation model / ground (the scene's environment). ``gw_engine``
    selects the ground-wave engine — ``"flat"`` (default, byte-identical) or
    ``"p368"`` (the ITU-R P.368-10 spherical earth, the honest choice for the
    hundreds-of-km LF/MF interference distances).
    """
    out = []
    for st in stations:
        res = heatmap.coverage_grid(
            st.lat, st.lon, st.height_m, st.freq_hz, st.power_dbm,
            dem=dem, pattern=st.pattern, peak_gain_dbi=st.peak_gain_dbi,
            rx_height_m=rx_height_m, k_factor=k_factor, model=model, ground=ground,
            lats=lats, lons=lons, gw_engine=gw_engine)
        out.append(res.field_dbuv_m)
    return out


class ServiceResult:
    """A composite service/interference map over ``lats`` x ``lons`` (both ascending).

    ``wanted_field`` / ``unwanted_field`` / ``du_db`` are dB grids; ``classification``
    is the per-cell NO_SERVICE / INTERFERENCE_LIMITED / SERVED code; ``station_fields``
    is the per-station field grid list (for a best-server / audit view).
    """

    def __init__(self, lats, lons, wanted_field, unwanted_field, du_db,
                 classification, station_fields, meta):
        self.lats = np.asarray(lats, dtype=float)
        self.lons = np.asarray(lons, dtype=float)
        self.wanted_field = np.asarray(wanted_field, dtype=float)
        self.unwanted_field = (None if unwanted_field is None
                               else np.asarray(unwanted_field, dtype=float))
        self.du_db = np.asarray(du_db, dtype=float)
        self.classification = np.asarray(classification)
        self.station_fields = station_fields
        self.meta = dict(meta)

    @property
    def bounds(self):
        """(north, south, east, west) for a KML LatLonBox."""
        return (float(self.lats.max()), float(self.lats.min()),
                float(self.lons.max()), float(self.lons.min()))

    def grid(self, metric="du"):
        """Metric grid: ``du`` (D/U dB), ``wanted``/``field``, ``unwanted``,
        ``served``/``class`` (the classification as float)."""
        m = str(metric).lower()
        if m.startswith("du") or m.startswith("d/u"):
            return self.du_db
        if m.startswith("want") or m == "field" or m.startswith("desir"):
            return self.wanted_field
        if m.startswith("unw") or m.startswith("undesir"):
            if self.unwanted_field is None:
                return np.full(self.wanted_field.shape, np.nan)
            return self.unwanted_field
        if m.startswith("serv") or m.startswith("class"):
            return self.classification.astype(float)
        raise ValueError("unknown metric: {0}".format(metric))

    def fraction(self, state=SERVED, over="valid"):
        """Fraction of cells in ``state``. ``over='valid'`` divides by all computed
        cells (finite wanted field); ``over='coverage'`` divides by the in-coverage
        cells (INTERFERENCE_LIMITED + SERVED) — the interference-free share of the
        service area."""
        cls = self.classification
        if over == "coverage":
            denom = int(np.count_nonzero(cls >= INTERFERENCE_LIMITED))
        else:
            denom = int(np.count_nonzero(np.isfinite(self.wanted_field)))
        if denom == 0:
            return 0.0
        return float(np.count_nonzero(cls == state) / denom)

    def served_fraction(self):
        return self.fraction(SERVED, over="valid")


def service_contour(stations, wanted=0, radius_m=50000.0, n=81, center=None,
                    protection_ratio_db=26.0, service_threshold_dbuv_m=54.0,
                    combine="power_sum", channel_bw_hz=None, model="auto",
                    ground=None, dem=None, rx_height_m=2.0, k_factor=4.0 / 3.0,
                    gw_engine="flat"):
    """Compose ``stations`` and classify one wanted station's service vs interference.

    :param wanted: index of the wanted (desired) station; the grid centres on it
        unless ``center`` (lat, lon) is given.
    :param protection_ratio_db: required D/U (see :data:`PROTECTION_RATIOS`; may be
        negative for adjacent-channel cases).
    :param service_threshold_dbuv_m: Gate-A protected field (see
        :data:`SERVICE_THRESHOLDS_DBUV_M`).
    :param combine: ``"power_sum"`` (default) or ``"worst_case"`` interferer aggregation.
    :param channel_bw_hz: if given, only stations within this bandwidth of the wanted
        carrier count as (co-channel) interferers — reuses
        :func:`emstudio.cosite.interference.in_band`; ``None`` treats every other
        station as an interferer (an already-co-channel list).
    :returns: a :class:`ServiceResult`.
    """
    stations = list(stations)
    if not stations:
        raise ValueError("need at least one station")
    if not (0 <= wanted < len(stations)):
        raise ValueError("wanted index {0} out of range".format(wanted))
    if ground is None:
        ground = groundwave.GROUND_TYPES["Average ground"]
    w = stations[wanted]
    if center is None:
        center = (w.lat, w.lon)
    lats, lons = _shared_grid(center[0], center[1], radius_m, n)

    fields = station_fields(stations, lats, lons, model=model, ground=ground,
                            dem=dem, rx_height_m=rx_height_m, k_factor=k_factor,
                            gw_engine=gw_engine)
    wanted_field = fields[wanted]

    # co-channel interferers (reuse the §5 in-band test); None -> all others
    unwanted_idx = []
    for i, st in enumerate(stations):
        if i == wanted:
            continue
        if channel_bw_hz is None or ci.in_band(st.freq_hz, w.freq_hz, channel_bw_hz):
            unwanted_idx.append(i)
    unwanted_field = (combine_fields_dbuv_m([fields[i] for i in unwanted_idx], combine)
                      if unwanted_idx else None)

    cls, du = classify(wanted_field, unwanted_field, service_threshold_dbuv_m,
                       protection_ratio_db)
    meta = {
        "wanted": int(wanted), "wanted_label": w.label,
        "tx_lat": float(w.lat), "tx_lon": float(w.lon), "freq_hz": float(w.freq_hz),
        "center": (float(center[0]), float(center[1])),
        "radius_m": float(radius_m), "n": int(n),
        "protection_ratio_db": float(protection_ratio_db),
        "service_threshold_dbuv_m": float(service_threshold_dbuv_m),
        "combine": combine, "channel_bw_hz": channel_bw_hz, "model": model,
        "gw_engine": gw_engine if model == "ground_wave" else None,
        "n_interferers": len(unwanted_idx),
        "interferers": [stations[i].label for i in unwanted_idx],
        "station_labels": [s.label for s in stations],
        "station_latlon": [(float(s.lat), float(s.lon)) for s in stations],
    }
    return ServiceResult(lats, lons, wanted_field, unwanted_field, du, cls, fields,
                         meta)


def best_server(stations, radius_m=50000.0, n=81, center=None,
                protection_ratio_db=26.0, service_threshold_dbuv_m=54.0,
                model="auto", ground=None, dem=None, rx_height_m=2.0,
                k_factor=4.0 / 3.0, gw_engine="flat"):
    """Network view of a set of co-channel stations: per cell, the strongest station
    is the server and its D/U is measured against the **power sum of all the others**.

    Returns a dict of grids: ``server`` (int index of the serving station, -1 = no
    field), ``best_field`` dB(uV/m), ``du_db``, ``classification``, plus ``lats`` /
    ``lons`` / ``meta``. Assumes all stations are co-channel (a single-frequency
    allotment / SFN-style view); aggregation is power-sum.
    """
    stations = list(stations)
    if len(stations) < 1:
        raise ValueError("need at least one station")
    if ground is None:
        ground = groundwave.GROUND_TYPES["Average ground"]
    if center is None:
        lat0 = float(np.mean([s.lat for s in stations]))
        lon0 = float(np.mean([s.lon for s in stations]))
        center = (lat0, lon0)
    lats, lons = _shared_grid(center[0], center[1], radius_m, n)
    fields = station_fields(stations, lats, lons, model=model, ground=ground,
                            dem=dem, rx_height_m=rx_height_m, k_factor=k_factor,
                            gw_engine=gw_engine)

    stack = np.stack(fields, axis=0)                            # (k, nlat, nlon)
    finite = np.isfinite(stack)
    filled = np.where(finite, stack, -np.inf)
    server = np.argmax(filled, axis=0).astype(np.int16)
    best_field = np.max(filled, axis=0)
    lin = np.where(finite, np.power(10.0, stack / 10.0), 0.0)
    total_power = np.sum(lin, axis=0)
    best_power = np.where(np.isfinite(best_field),
                          np.power(10.0, np.where(np.isfinite(best_field),
                                                  best_field, 0.0) / 10.0), 0.0)
    rest_power = np.clip(total_power - best_power, 0.0, None)
    with np.errstate(divide="ignore"):
        unwanted = 10.0 * np.log10(rest_power)
    du = np.where(rest_power > 0.0, best_field - unwanted, np.inf)

    no_field = ~np.isfinite(best_field)
    server[no_field] = -1
    best_field = np.where(no_field, np.nan, best_field)

    in_cov = np.isfinite(best_field) & (best_field >= float(service_threshold_dbuv_m))
    protected = du >= float(protection_ratio_db)
    cls = np.full(best_field.shape, NO_SERVICE, dtype=np.int8)
    cls[in_cov & ~protected] = INTERFERENCE_LIMITED
    cls[in_cov & protected] = SERVED

    meta = {
        "center": (float(center[0]), float(center[1])),
        "radius_m": float(radius_m), "n": int(n),
        "protection_ratio_db": float(protection_ratio_db),
        "service_threshold_dbuv_m": float(service_threshold_dbuv_m),
        "model": model, "n_stations": len(stations),
        "station_labels": [s.label for s in stations],
        "station_latlon": [(float(s.lat), float(s.lon)) for s in stations],
    }
    return {"server": server, "best_field": best_field, "du_db": du,
            "classification": cls, "lats": lats, "lons": lons, "meta": meta}


def export_service_kml(result, kml_path, metric="du", threshold=None,
                       name="EMStudio service/interference"):
    """Render a :class:`ServiceResult` metric to a KML GroundOverlay (+ PNG).

    Reuses the shipped :mod:`emstudio.coverage.kml` primitives. For ``metric="du"``
    a ``threshold`` (default the protection ratio) masks cells below it so the
    interference-free area is what is drawn; a diverging colour map is used.
    Returns ``(kml_path, png_path)``.
    """
    from emstudio.coverage import kml

    base = os.path.splitext(kml_path)[0]
    png_path = base + ".png"
    m = str(metric).lower()
    if m.startswith("du") and threshold is None:
        threshold = result.meta.get("protection_ratio_db")
    cmap = "RdYlGn" if m.startswith("du") else "jet"
    kml.render_png(result, png_path, metric=metric, threshold=threshold, cmap=cmap)
    north, south, east, west = result.bounds
    desc = ("EMStudio D/U service/interference — wanted '{0}' @ {1:.4g} MHz, "
            "{2} interferer(s), protection {3:g} dB, service {4:g} dBuV/m".format(
                result.meta.get("wanted_label", "?"),
                result.meta.get("freq_hz", 0.0) / 1e6,
                result.meta.get("n_interferers", 0),
                result.meta.get("protection_ratio_db", 0.0),
                result.meta.get("service_threshold_dbuv_m", 0.0)))
    xml = kml.kml_groundoverlay_xml(
        north, south, east, west, os.path.basename(png_path),
        tx_lat=result.meta.get("tx_lat"), tx_lon=result.meta.get("tx_lon"),
        name=name, description=desc)
    with open(kml_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    return kml_path, png_path
