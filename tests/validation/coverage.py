# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: DEM import + terrain profiles + coverage heatmap + KML (§6 phase B).

Pass: exit 0 and 'COVERAGE GATE PASSED'. Pure python3 (numpy + matplotlib; no
solver, no FreeCAD). Synthesizes DEM fixtures (a Gaussian hill in .hgt and in a
minimal GeoTIFF) so the whole chain is validated against known analytic geometry
with no network / no real tiles:

  * geodesy   — great-circle distance/bearing/interpolation vs known values;
  * .hgt      — round-trip + bilinear elevation vs the analytic hill (<1 m);
  * GeoTIFF   — uncompressed AND DEFLATE round-trip + georeferencing;
  * profile   — the hill is the controlling Deygout edge; earth bulge adds loss;
  * heatmap   — a cleared omni link degenerates EXACTLY to EIRP - FSPL; a hill
                shadows cells behind it; a directional pattern paints a lobe;
  * KML       — well-formed GroundOverlay (N>S, E>W, href, tx placemark) + PNG.
"""
import io
import math
import os
import struct
import sys
import tempfile
import zlib

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


# ------------------------------------------------------------ DEM fixtures ----
def _hill(lat, lon, hlat, hlon, peak, sigma_deg):
    dd = ((lat - hlat) ** 2 + (lon - hlon) ** 2) / (sigma_deg ** 2)
    return peak * math.exp(-dd)


def write_hgt(path, size, sw_lat, sw_lon, fn):
    """Synthesize an SRTM .hgt tile (big-endian int16, row0=north, col0=west)."""
    step = 1.0 / (size - 1)
    arr = np.empty((size, size), dtype=">i2")
    for r in range(size):
        lat = sw_lat + 1.0 - r * step
        for c in range(size):
            arr[r, c] = int(round(fn(lat, sw_lon + c * step)))
    arr.tofile(path)


_TT = {3: 2, 4: 4, 12: 8}


def write_geotiff(path, arr, lat_max, lon_min, dlat, dlon, compress=False):
    """Minimal single-strip int16 little-endian GeoTIFF with geo tags."""
    h, w = arr.shape
    raw = arr.astype("<i2").tobytes()
    comp = 1
    if compress:
        raw = zlib.compress(raw)
        comp = 8
    entries = []

    def add(tag, typ, values):
        if typ == 3:
            packed = b"".join(struct.pack("<H", v) for v in values)
        elif typ == 4:
            packed = b"".join(struct.pack("<I", v) for v in values)
        else:
            packed = b"".join(struct.pack("<d", v) for v in values)
        entries.append([tag, typ, len(values), packed])

    add(256, 4, [w]); add(257, 4, [h]); add(258, 3, [16]); add(259, 3, [comp])
    add(262, 3, [1]); add(273, 4, [0]); add(277, 3, [1]); add(278, 4, [h])
    add(279, 4, [len(raw)]); add(339, 3, [2])
    add(33550, 12, [dlon, dlat, 0.0])
    add(33922, 12, [0, 0, 0, lon_min, lat_max, 0.0])
    add(34735, 3, [1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 1, 2048, 0, 1, 4326])
    entries.sort(key=lambda e: e[0])

    n = len(entries)
    ext_base = 8 + 2 + n * 12 + 4
    ext = io.BytesIO()
    ifd = []
    strip_i = None
    for i, (tag, typ, cnt, packed) in enumerate(entries):
        size = _TT[typ] * cnt
        if size <= 4:
            val = packed + b"\x00" * (4 - size)
        else:
            val = struct.pack("<I", ext_base + ext.tell())
            ext.write(packed)
            if len(packed) % 2:
                ext.write(b"\x00")
        ifd.append([tag, typ, cnt, val])
        if tag == 273:
            strip_i = i
    strip_off = ext_base + ext.tell()
    ifd[strip_i][3] = struct.pack("<I", strip_off)

    out = io.BytesIO()
    out.write(b"II" + struct.pack("<H", 42) + struct.pack("<I", 8))
    out.write(struct.pack("<H", n))
    for tag, typ, cnt, val in ifd:
        out.write(struct.pack("<HHI", tag, typ, cnt) + val)
    out.write(struct.pack("<I", 0))
    out.write(ext.getvalue())
    out.write(raw)
    with open(path, "wb") as fh:
        fh.write(out.getvalue())


# ------------------------------------------------------------------ checks ----
def main():
    from emstudio.coverage import geodesy as geo
    from emstudio.coverage import terrain, heatmap, kml, pattern as pat
    from emstudio.coverage import groundwave as gw
    from emstudio.coverage import multistation as ms
    from emstudio.coverage import propagation as pr
    from emstudio.cosite import interference as cosite

    print("EMStudio coverage (§6 phase B) validation gate")
    C0 = 299792458.0
    tmp = tempfile.mkdtemp(prefix="emstudio_coverage_gate_")

    # --- geodesy ---
    d_eq = geo.haversine_m(0, 0, 0, 1)
    check("1 deg lon @ equator ~= 111.32 km", abs(d_eq - 111195.0) < 300,
          "{0:.0f} m".format(d_eq))
    check("bearing due east = 90", abs(geo.initial_bearing_deg(0, 0, 0, 1) - 90) < 1e-6)
    check("bearing due north = 0", abs(geo.initial_bearing_deg(0, 0, 1, 0)) < 1e-6)
    mid = geo.intermediate_point(0, 0, 0, 2, 0.5)
    check("great-circle midpoint (0,0)-(0,2) = (0,1)",
          abs(mid[0]) < 1e-6 and abs(mid[1] - 1) < 1e-6)
    d_lp = geo.haversine_m(51.5074, -0.1278, 48.8566, 2.3522)  # London-Paris
    check("London-Paris great circle ~= 343.5 km", abs(d_lp - 343556) < 4000,
          "{0:.0f} m".format(d_lp))
    dst = geo.destination_point(0, 0, 90, 111195.0)
    check("destination E 111.2 km -> ~(0,1)", abs(dst[0]) < 1e-6 and abs(dst[1] - 1) < 0.01)

    # --- .hgt import ---
    hgt = os.path.join(tmp, "N00E000.hgt")
    HL, HO, PEAK, SIG = 0.5, 0.5, 300.0, 0.1
    write_hgt(hgt, 241, 0, 0, lambda la, lo: _hill(la, lo, HL, HO, PEAK, SIG))
    tile = terrain.read_hgt(hgt)
    check(".hgt shape 241x241", tile.data.shape == (241, 241))
    check(".hgt north-up corner (lat_max=1, lon_min=0)",
          abs(tile.lat_max - 1.0) < 1e-9 and abs(tile.lon_min) < 1e-9)
    vpk = tile.elevation(HL, HO)
    check(".hgt bilinear peak ~= 300 m", abs(vpk - PEAK) < 2.0, "{0:.2f} m".format(vpk))
    errs = [abs(tile.elevation(la, lo) - _hill(la, lo, HL, HO, PEAK, SIG))
            for (la, lo) in [(0.3, 0.3), (0.55, 0.5), (0.6, 0.45), (0.2, 0.8)]]
    check(".hgt bilinear matches analytic hill (<1.5 m)", max(errs) < 1.5,
          "maxerr {0:.3f} m".format(max(errs)))
    check(".hgt out-of-tile -> NaN", math.isnan(tile.elevation(5.0, 5.0)))

    # --- GeoTIFF import (uncompressed + DEFLATE) ---
    size = 201
    lat_max, lon_min, dl = 35.0, -119.0, 1.0 / (size - 1)
    src = np.array([[int(round(_hill(lat_max - r * dl, lon_min + c * dl,
                                     34.5, -118.5, 500.0, 0.15)))
                     for c in range(size)] for r in range(size)], dtype=np.int16)
    for comp in (False, True):
        tif = os.path.join(tmp, "dem_{0}.tif".format("z" if comp else "u"))
        write_geotiff(tif, src, lat_max, lon_min, dl, dl, compress=comp)
        gt = terrain.read_geotiff(tif)
        tag = "DEFLATE" if comp else "raw"
        check("GeoTIFF {0} array round-trip".format(tag),
              np.array_equal(gt.data.astype(np.int16), src))
        check("GeoTIFF {0} georeferencing".format(tag),
              abs(gt.lat_max - lat_max) < 1e-9 and abs(gt.lon_min - lon_min) < 1e-9
              and abs(gt.dlat - dl) < 1e-12)
    # bilinear vs analytic through the DEM abstraction
    dem = terrain.DEM.load(tif)
    v = dem.elevation(34.5, -118.5)
    check("GeoTIFF DEM peak elevation ~= 500 m", abs(v - 500.0) < 3.0, "{0:.2f} m".format(v))

    # --- DEM directory mosaic ---
    dem_dir = os.path.join(tmp, "tiles")
    os.makedirs(dem_dir)
    write_hgt(os.path.join(dem_dir, "N00E000.hgt"), 121, 0, 0,
              lambda la, lo: _hill(la, lo, HL, HO, PEAK, SIG))
    dem_hgt = terrain.DEM.load(dem_dir)
    check("DEM.load(dir) mosaics tiles + dispatches elevation",
          abs(dem_hgt.elevation(HL, HO) - PEAK) < 3.0)

    # --- terrain path profile (great circle + bulge + Deygout) ---
    prof = terrain.path_profile(dem_hgt, HL, 0.2, HL, 0.8, n_samples=120,
                                k_factor=1e12)  # curvature off to isolate the hill
    zmax = max(z for _, z in prof)
    check("path profile crosses the hill (~300 m)", abs(zmax - PEAK) < 4.0,
          "{0:.1f} m".format(zmax))
    res = pr.terrain_profile_loss(prof, 2.0, 2.0, 300e6)
    check("hill is the controlling Deygout edge (diff>10 dB)",
          res["edge_index"] is not None and res["diffraction_db"] > 10.0,
          "diff {0:.1f} dB".format(res["diffraction_db"]))
    # earth bulge adds loss over a long flat path
    flat_no = terrain.path_profile(None, 0.0, 0.0, 0.0, 0.6, n_samples=120, k_factor=1e12)
    flat_k = terrain.path_profile(None, 0.0, 0.0, 0.0, 0.6, n_samples=120)  # k=4/3
    r_no = pr.terrain_profile_loss(flat_no, 10, 10, 100e6)
    r_k = pr.terrain_profile_loss(flat_k, 10, 10, 100e6)
    check("earth bulge (4/3) increases loss over a long flat path",
          r_k["total_loss_db"] >= r_no["total_loss_db"] + 1.0,
          "{0:.1f} -> {1:.1f} dB".format(r_no["total_loss_db"], r_k["total_loss_db"]))

    # --- multi-edge terrain diffraction (Deygout recursive + Epstein-Peterson) ---
    # vs the NTIA TR-26-580 worked cases (lambda=0.2 m = 1500 MHz, zero ant heights)
    F15 = C0 / 0.2
    check("knife-edge J(v) kernel: J(0)=6.0, J(1)=13.9, J(2.4)=20.5, J(-0.78)=0",
          abs(pr.knife_edge_loss_db(0.0) - 6.03) < 0.02
          and abs(pr.knife_edge_loss_db(1.0) - 13.93) < 0.02
          and abs(pr.knife_edge_loss_db(2.4) - 20.54) < 0.02
          and pr.knife_edge_loss_db(-0.78) == 0.0)
    # degenerate single edge (dT=1600, dR=4000, h=240 -> v=22.45 -> J=39.91)
    p_1 = [(0.0, 0.0), (1600.0, 240.0), (5600.0, 0.0)]
    d1e = pr.deygout_multiedge_loss_db(p_1, 0.0, 0.0, F15)
    e1e = pr.epstein_peterson_loss_db(p_1, 0.0, 0.0, F15)
    check("multi-edge single obstacle reduces to J(v)=39.91 dB (Deygout + EP)",
          abs(d1e - 39.91) < 0.05 and abs(e1e - 39.91) < 0.05,
          "deygout {0:.2f} / EP {1:.2f}".format(d1e, e1e))
    single_d = pr.terrain_profile_loss(p_1, 0.0, 0.0, F15)["diffraction_db"]
    check("shipped single-edge loss == deygout multi-edge for one obstacle",
          abs(single_d - d1e) < 1e-9)
    # NTIA Case 23 (2 edges): Deygout 73.29, Epstein-Peterson 70.52
    p_2 = [(0.0, 0.0), (1600.0, 240.0), (4000.0, 200.0), (5600.0, 0.0)]
    d2e = pr.deygout_multiedge_loss_db(p_2, 0.0, 0.0, F15)
    e2e = pr.epstein_peterson_loss_db(p_2, 0.0, 0.0, F15)
    check("NTIA Case 23 2-edge Deygout ~= 73.29 dB", abs(d2e - 73.292) < 0.1,
          "{0:.3f}".format(d2e))
    check("NTIA Case 23 2-edge Epstein-Peterson ~= 70.52 dB", abs(e2e - 70.517) < 0.2,
          "{0:.3f}".format(e2e))
    # NTIA Case 13 (4 edges): Deygout 99.88, Epstein-Peterson 95.71
    p_4 = [(0.0, 0.0), (1200.0, 140.0), (2800.0, 260.0), (4400.0, 200.0),
           (5800.0, 220.0), (6600.0, 0.0)]
    d4e = pr.deygout_multiedge_loss_db(p_4, 0.0, 0.0, F15)
    e4e = pr.epstein_peterson_loss_db(p_4, 0.0, 0.0, F15)
    check("NTIA Case 13 4-edge Deygout ~= 99.88 dB", abs(d4e - 99.884) < 0.2,
          "{0:.3f}".format(d4e))
    check("NTIA Case 13 4-edge Epstein-Peterson ~= 95.71 dB", abs(e4e - 95.706) < 0.2,
          "{0:.3f}".format(e4e))
    check("Deygout (over-est) >= Epstein-Peterson (under-est) on multi-edge paths",
          d2e > e2e and d4e > e4e)
    # Bullington equivalent single edge (deliberately optimistic)
    b1e = pr.bullington_loss_db(p_1, 0.0, 0.0, F15)
    check("Bullington single obstacle reduces to J(v)=39.91 dB",
          abs(b1e - 39.91) < 0.05, "{0:.2f}".format(b1e))
    b2e = pr.bullington_loss_db(p_2, 0.0, 0.0, F15)
    check("NTIA Case 23 2-edge Bullington ~= 43.17 dB", abs(b2e - 43.168) < 0.1,
          "{0:.3f}".format(b2e))
    b4e = pr.bullington_loss_db(p_4, 0.0, 0.0, F15)
    check("NTIA Case 13 4-edge Bullington ~= 46.22 dB", abs(b4e - 46.215) < 0.1,
          "{0:.3f}".format(b4e))
    check("Bullington under-predicts vs Epstein-Peterson on multi-edge paths",
          b2e < e2e and b4e < e4e)
    # NTIA 6-edge fixture (near-grazing small edges): all three methods
    p_6 = [(0.0, 0.0), (1000.0, 1.6), (2200.0, 2.2), (3000.0, 3.4), (4200.0, 3.0),
           (5000.0, 2.6), (5400.0, 1.7), (6400.0, 0.0)]
    b6e = pr.bullington_loss_db(p_6, 0.0, 0.0, F15)
    e6e = pr.epstein_peterson_loss_db(p_6, 0.0, 0.0, F15)
    d6e = pr.deygout_multiedge_loss_db(p_6, 0.0, 0.0, F15)
    check("NTIA 6-edge Bullington ~= 9.77 dB", abs(b6e - 9.767) < 0.05,
          "{0:.3f}".format(b6e))
    check("NTIA 6-edge Epstein-Peterson ~= 38.04 dB", abs(e6e - 38.038) < 0.1,
          "{0:.3f}".format(e6e))
    check("NTIA 6-edge Deygout ~= 39.42 dB", abs(d6e - 39.421) < 0.1,
          "{0:.3f}".format(d6e))
    check("Bullington clear path (edge below LOS) -> 0 dB",
          pr.bullington_loss_db([(0.0, 0.0), (2000.0, -30.0), (5000.0, 0.0)],
                                0, 0, F15) == 0.0)
    # reversal symmetry (tx<->rx swap gives the same total) — chord-convention guard
    def _rev(p):
        d = p[-1][0]
        return [(d - x, h) for (x, h) in reversed(p)]
    check("multi-edge diffraction is reversal-symmetric (tx<->rx)",
          abs(pr.deygout_multiedge_loss_db(_rev(p_4), 0, 0, F15) - d4e) < 1e-9
          and abs(pr.epstein_peterson_loss_db(_rev(p_4), 0, 0, F15) - e4e) < 1e-9
          and abs(pr.bullington_loss_db(_rev(p_4), 0, 0, F15) - b4e) < 1e-9)
    check("cleared multi-edge path -> 0 dB (no protruding edge)",
          pr.deygout_multiedge_loss_db([(0.0, 50.0), (5000.0, 50.0)], 0, 0, F15) == 0.0)

    # --- Causebrook correction (BBC RD 1971/43 eqs 13-15) on Deygout ---
    # by-construction fixture: symmetric 3-edge path, a=b=c=e=1000 m ->
    # cos a2 = cos a3 = sqrt(a(c+e)/((a+b)(b+c+e))) = sqrt(2000/6000) = sqrt(1/3)
    p_c = [(0.0, 0.0), (1000.0, 20.0), (2000.0, 30.0), (3000.0, 20.0),
           (4000.0, 0.0)]
    a1_c = pr.knife_edge_loss_db(pr.fresnel_v(30.0, 2000.0, 2000.0, F15))
    a2p_c = pr.knife_edge_loss_db(pr.fresnel_v(
        20.0 - 15.0, 1000.0, 1000.0, F15))          # e2 over the tx-main chord
    a2_c = pr.knife_edge_loss_db(pr.fresnel_v(
        20.0 - 0.0, 1000.0, 3000.0, F15))           # e2 ALONE on the full chord
    cosang = math.sqrt(1.0 / 3.0)
    expect_c = (a1_c + 2.0 * a2p_c
                - 2.0 * max(0.0, (6.0 - a1_c + a2_c) * cosang))
    got_c = pr.deygout_causebrook_loss_db(p_c, 0.0, 0.0, F15)
    check("Causebrook by-construction 3-edge fixture (eqs 13-15 exact)",
          abs(got_c - expect_c) < 1e-9,
          "{0:.3f} vs {1:.3f} dB".format(got_c, expect_c))
    check("Causebrook <= uncorrected Deygout, corrections <= 6 dB/side",
          got_c <= pr.deygout_multiedge_loss_db(p_c, 0.0, 0.0, F15) + 1e-12
          and pr.deygout_multiedge_loss_db(p_c, 0.0, 0.0, F15) - got_c
          <= 12.0 + 1e-12)
    check("Causebrook degenerate single edge == uncorrected Deygout exactly",
          abs(pr.deygout_causebrook_loss_db(p_1, 0.0, 0.0, F15) - d1e) < 1e-12)
    c6e = pr.deygout_causebrook_loss_db(p_6, 0.0, 0.0, F15)
    c4e = pr.deygout_causebrook_loss_db(p_4, 0.0, 0.0, F15)
    check("Causebrook on the NTIA fixtures: bounded below Deygout",
          c6e <= d6e + 1e-12 and d6e - c6e <= 12.0
          and c4e <= d4e + 1e-12 and d4e - c4e <= 12.0,
          "6-edge {0:.2f} (Deygout {1:.2f}); 4-edge {2:.2f} ({3:.2f})".format(
              c6e, d6e, c4e, d4e))
    check("Causebrook is reversal-symmetric (tx<->rx)",
          abs(pr.deygout_causebrook_loss_db(_rev(p_c), 0, 0, F15) - got_c) < 1e-9
          and abs(pr.deygout_causebrook_loss_db(_rev(p_4), 0, 0, F15) - c4e)
          < 1e-9)
    check("terrain_profile_loss dispatches deygout_causebrook",
          abs(pr.terrain_profile_loss(p_c, 0.0, 0.0, F15,
                                      method="deygout_causebrook")
              ["diffraction_db"] - got_c) < 1e-12)

    # multi-edge wired into the coverage terrain mode (opt-in). By construction the
    # recursive Deygout adds the secondary edges the single dominant edge misses, so
    # its loss is >= single-edge everywhere and strictly greater behind two ridges.
    ridge2 = os.path.join(tmp, "N41E011.hgt")

    def _two_bump(la, lo):
        return (700.0 * math.exp(-((lo - 11.20) ** 2) / (0.02 ** 2))
                + 700.0 * math.exp(-((lo - 11.33) ** 2) / (0.02 ** 2)))
    write_hgt(ridge2, 241, 41, 11, _two_bump)
    dem_2b = terrain.DEM.load(ridge2)
    kw2b = dict(tx_height_m=15.0, freq_hz=300e6, tx_power_dbm=50.0, radius_m=30000.0,
                n=31, peak_gain_dbi=2.15, rx_height_m=2.0)
    cov_s = heatmap.coverage_grid(41.5, 11.05, dem=dem_2b, diffraction="single", **kw2b)
    cov_m = heatmap.coverage_grid(41.5, 11.05, dem=dem_2b, diffraction="deygout", **kw2b)
    vv = np.isfinite(cov_s.prx_dbm) & np.isfinite(cov_m.prx_dbm)
    check("multi-edge coverage loss >= single-edge everywhere (adds secondary edges)",
          bool(np.all(cov_m.prx_dbm[vv] <= cov_s.prx_dbm[vv] + 1e-6))
          and cov_m.meta["diffraction"] == "deygout")
    check("multi-edge coverage shadows strictly more behind two ridges",
          bool(np.any(cov_s.prx_dbm[vv] - cov_m.prx_dbm[vv] > 1.0)))

    # --- coverage heatmap: no-DEM analytic degeneracy ---
    tx = (40.0, -100.0)
    freq = 300e6
    cov = heatmap.coverage_grid(tx[0], tx[1], 200.0, freq, tx_power_dbm=50.0,
                                dem=None, radius_m=20000.0, n=41, peak_gain_dbi=0.0,
                                rx_height_m=200.0, k_factor=1e12)
    ci = 20
    check("coverage decreases with distance (center > edge)",
          cov.prx_dbm[ci, ci + 1] > cov.prx_dbm[ci, -1],
          "{0:.1f} -> {1:.1f} dBm".format(cov.prx_dbm[ci, ci + 1], cov.prx_dbm[ci, -1]))
    d_edge = geo.haversine_m(tx[0], tx[1], cov.lats[ci], cov.lons[-1])
    fspl = pr.free_space_path_loss_db(d_edge, freq)
    exp = 50.0 - fspl
    check("cleared omni cell == EIRP - FSPL (exact link-budget degeneracy)",
          abs(cov.prx_dbm[ci, -1] - exp) < 0.05,
          "{0:.3f} vs {1:.3f} dBm".format(cov.prx_dbm[ci, -1], exp))
    # field strength cross-check: E = P_EIRP(dBW) + 74.8 - 20log10(d_km)
    e_exp = (50.0 - 30.0) + 74.8 - 20.0 * math.log10(d_edge / 1e3)
    check("cleared omni field strength matches ITU relation",
          abs(cov.field_dbuv_m[ci, -1] - e_exp) < 0.1,
          "{0:.2f} vs {1:.2f} dBuV/m".format(cov.field_dbuv_m[ci, -1], e_exp))

    # plane-earth governs beyond the breakpoint (low antennas, curvature on)
    covpe = heatmap.coverage_grid(tx[0], tx[1], 10.0, freq, tx_power_dbm=50.0,
                                  dem=None, radius_m=40000.0, n=41, peak_gain_dbi=0.0,
                                  rx_height_m=10.0)
    d_far = geo.haversine_m(tx[0], tx[1], covpe.lats[ci], covpe.lons[-1])
    pe = pr.plane_earth_loss_db(d_far, 10.0, 10.0)
    fspl_far = pr.free_space_path_loss_db(d_far, freq)
    if d_far > pr.plane_earth_breakpoint_m(10.0, 10.0, freq) and pe > fspl_far:
        check("plane-earth governs beyond the breakpoint",
              abs(covpe.prx_dbm[ci, -1] - (50.0 - pe)) < 0.05,
              "{0:.2f} vs {1:.2f} dBm".format(covpe.prx_dbm[ci, -1], 50.0 - pe))
    else:
        check("plane-earth governs beyond the breakpoint", True, "geometry inside bp")

    # --- coverage heatmap: DEM hill shadow ---
    # Controlled experiment: a ridge tile vs a FLAT tile through the SAME terrain
    # branch, so the only difference is the ridge (comparing to the no-DEM branch
    # would mix propagation modes: terrain diffraction vs smooth-earth two-ray).
    ridge = os.path.join(tmp, "N40E010.hgt")
    flatt = os.path.join(tmp, "flat", "N40E010.hgt")
    os.makedirs(os.path.dirname(flatt))

    def ridge_fn(la, lo):
        return 800.0 * math.exp(-((lo - 10.30) ** 2) / (0.02 ** 2))
    write_hgt(ridge, 241, 40, 10, ridge_fn)
    write_hgt(flatt, 241, 40, 10, lambda la, lo: 0.0)
    dem_r = terrain.DEM.load(ridge)
    dem_f = terrain.DEM.load(flatt)
    txr = (40.5, 10.1)
    kw = dict(tx_height_m=15.0, freq_hz=100e6, tx_power_dbm=50.0, radius_m=25000.0,
              n=31, peak_gain_dbi=2.15, rx_height_m=2.0)
    covr = heatmap.coverage_grid(txr[0], txr[1], dem=dem_r, **kw)
    covf = heatmap.coverage_grid(txr[0], txr[1], dem=dem_f, **kw)
    # east edge, same row as the tx: behind the ridge
    row = 15
    shadow = covr.prx_dbm[row, -1]
    open_ = covf.prx_dbm[row, -1]
    check("DEM ridge shadows a cell behind it (< flat-DEM path)",
          shadow < open_ - 5.0,
          "shadow {0:.1f} < open {1:.1f} dBm".format(shadow, open_))

    # --- two-ray ground reflection on clear terrain paths (opt-in) ---
    # with curvature off (no bulge edge), a FLAT DEM + ground_reflection must
    # degenerate EXACTLY to the smooth-earth (no-DEM) footprint, cell for cell
    cov_nd = heatmap.coverage_grid(txr[0], txr[1], dem=None, k_factor=1e12, **kw)
    cov_fg = heatmap.coverage_grid(txr[0], txr[1], dem=dem_f, k_factor=1e12,
                                   ground_reflection=True, **kw)
    dmax = float(np.nanmax(np.abs(cov_fg.prx_dbm - cov_nd.prx_dbm)))
    check("flat DEM + two-ray reflection == smooth-earth footprint (exact)",
          dmax < 1e-6, "max |delta| {0:.2e} dB".format(dmax))
    # plane-earth must actually govern somewhere for the degeneracy to bite
    fspl_only = 50.0 + 2.15 - pr.free_space_path_loss_db(
        geo.haversine_m(txr[0], txr[1], float(cov_nd.lats[row]),
                        float(cov_nd.lons[-1])), 100e6)
    check("two-ray degeneracy bites (plane-earth governs at the map edge)",
          cov_nd.prx_dbm[row, -1] < fspl_only - 1.0,
          "{0:.1f} vs FSPL-only {1:.1f} dBm".format(cov_nd.prx_dbm[row, -1],
                                                    fspl_only))
    # behind the ridge diffraction governs: the reflection option changes nothing
    covr_g = heatmap.coverage_grid(txr[0], txr[1], dem=dem_r,
                                   ground_reflection=True, **kw)
    check("ground-reflection option leaves diffracted (shadowed) cells unchanged",
          abs(covr_g.prx_dbm[row, -1] - shadow) < 1e-9
          and covr_g.meta["ground_reflection"] is True)

    # --- antenna pattern modulation ---
    from emstudio.post.farfield import FarFieldResult
    theta = np.arange(0, 181, 5.0)
    phi = np.arange(0, 360, 5.0)
    # a cardioid-ish azimuth pattern peaked toward phi=90, at the horizon (theta=90)
    g = np.zeros((theta.size, phi.size))
    for jj, ph in enumerate(phi):
        g[:, jj] = 8.0 * math.cos(math.radians(ph - 90.0)) - 4.0
    ff = FarFieldResult(100e6, theta, phi, g)
    azp = pat.AzimuthPattern.from_farfield(ff, elevation_deg=0.0, orientation_deg=0.0)
    check("pattern azimuth cut peaks toward phi=90",
          azp.gain_at(90.0) > azp.gain_at(270.0) + 8.0,
          "{0:.1f} vs {1:.1f} dBi".format(azp.gain_at(90.0), azp.gain_at(270.0)))
    covd = heatmap.coverage_grid(tx[0], tx[1], 200.0, freq, tx_power_dbm=50.0,
                                 dem=None, radius_m=20000.0, n=41, pattern=azp,
                                 rx_height_m=200.0, k_factor=1e12)
    # bearing 90 = due east (max col), bearing 270 = due west (min col)
    check("directional pattern paints an east lobe (east > west)",
          covd.prx_dbm[ci, -1] > covd.prx_dbm[ci, 0] + 8.0,
          "E {0:.1f} > W {1:.1f} dBm".format(covd.prx_dbm[ci, -1], covd.prx_dbm[ci, 0]))
    check("omni pattern is azimuthally uniform (east ~= west)",
          abs(cov.prx_dbm[ci, -1] - cov.prx_dbm[ci, 0]) < 0.5)

    # --- coverage fraction ---
    frac = cov.coverage_fraction(exp - 1.0, metric="prx")
    check("coverage_fraction in [0,1] and > 0 above a low threshold",
          0.0 < frac <= 1.0, "{0:.2f}".format(frac))

    # --- LF/MF ground-wave (ITU-R P.368 / Norton) vs the ITU Handbook worked chain ---
    # worked example 1 (Terman/Basrah): sigma=5e-5, eps_r=15, f=2 MHz, d=20 km
    p1, _ = gw.numerical_distance(20e3, 2e6, 15.0, 5e-5)
    check("ground-wave |rho| ~= 26 (worked ex1)", abs(p1 - 26.0) < 1.5,
          "{0:.2f}".format(p1))
    check("ground-wave |A| ~= 0.0226 (worked ex1)",
          abs(gw.attenuation_factor(p1) - 0.0226) < 0.003,
          "{0:.4f}".format(gw.attenuation_factor(p1)))
    # worked example 2 (ITU Handbook): 1 MHz, medium ground eps_r=15 sigma=1e-3, 100 km
    p2, _ = gw.numerical_distance(100e3, 1e6, 15.0, 1e-3)
    check("ground-wave |rho| ~= 43.5 (ITU Handbook ex2)", abs(p2 - 43.5) < 1.5,
          "{0:.2f}".format(p2))
    e2 = gw.field_strength_dbuv_m(100e3, 1e6, 15.0, 1e-3)
    check("ground-wave field ~= 31.6 dBuV/m (ITU Handbook ex2, 1 kW)",
          abs(e2 - 31.6) < 1.5, "{0:.2f}".format(e2))
    # asymptotes + P.368 normalization
    check("|A|->1 as rho->0", abs(gw.attenuation_factor(1e-6) - 1.0) < 1e-4)
    check("|A|->1/(2rho) as rho->inf",
          abs(gw.attenuation_factor(200.0) - 1.0 / 400.0) < 5e-4)
    check("P.368 sea @ 1 km ~= 109.5 dBuV/m (300 mV/m ref)",
          abs(gw.field_strength_dbuv_m(1000.0, 1e6, 70.0, 5.0) - 109.54) < 1.0,
          "{0:.2f}".format(gw.field_strength_dbuv_m(1000.0, 1e6, 70.0, 5.0)))
    check("CMF(1 kW, monopole 4.8 dBi) ~= 300 V",
          abs(gw.cmf_from_power(1000.0) - 300.0) < 3.0,
          "{0:.1f} V".format(gw.cmf_from_power(1000.0)))
    # qualitative P.368 orderings
    dd, ff = 100e3, 1e6
    e_sea = gw.field_strength_dbuv_m(dd, ff, *gw.GROUND_TYPES["Sea water"])
    e_wet = gw.field_strength_dbuv_m(dd, ff, *gw.GROUND_TYPES["Wet ground"])
    e_dry = gw.field_strength_dbuv_m(dd, ff, *gw.GROUND_TYPES["Dry ground"])
    check("ground-wave field: sea > wet > dry (100 km, 1 MHz)",
          e_sea > e_wet > e_dry,
          "sea {0:.0f} wet {1:.0f} dry {2:.0f} dBuV/m".format(e_sea, e_wet, e_dry))
    e_lf = gw.field_strength_dbuv_m(dd, 100e3, 13.0, 5e-3)
    e_mf = gw.field_strength_dbuv_m(dd, 1e6, 13.0, 5e-3)
    check("ground-wave: lower frequency propagates farther", e_lf > e_mf,
          "100 kHz {0:.0f} > 1 MHz {1:.0f}".format(e_lf, e_mf))

    # ground-wave coverage MODE in the heatmap engine
    covg = heatmap.coverage_grid(40.0, -100.0, 30.0, 1e6, tx_power_dbm=60.0,
                                 model="ground_wave",
                                 ground=gw.GROUND_TYPES["Average ground"],
                                 radius_m=80000.0, n=31, peak_gain_dbi=0.0)
    cg = 15
    check("ground-wave coverage falls off (center > edge)",
          covg.field_dbuv_m[cg, cg + 1] > covg.field_dbuv_m[cg, -1])
    check("ground-wave coverage meta records the model + ground",
          covg.meta["model"] == "ground_wave" and covg.meta["ground"] is not None)

    # --- empirical land-mobile models: Okumura-Hata + COST-231-Hata (§6 phase D) ---
    from emstudio.coverage import empirical as emp

    check("Hata a(hm) small/medium city (900 MHz, 2 m) = 1.291 dB",
          abs(emp.hata_mobile_correction_db(900.0, 2.0) - 1.2907) < 1e-3)
    check("Hata large-city a(hm) ~ 0 at the 1.5 m reference height",
          abs(emp.hata_mobile_correction_db(900.0, 1.5, large_city=True)) < 0.01)
    # externally verified worked example (RF calculator, arithmetic re-verified)
    l_ex = emp.okumura_hata_loss_db(4000.0, 900e6, 100.0, 2.0, "urban")
    check("Okumura-Hata verified example (900 MHz/100 m/2 m/4 km) = 137.05 dB",
          abs(l_ex - 137.048) < 0.05, "{0:.3f}".format(l_ex))
    # distance slope = 44.9 - 6.55 log10(hb) dB/decade (Patwari coefficient check)
    slope = (emp.okumura_hata_loss_db(2000.0, 850e6, 30.0, 1.5)
             - emp.okumura_hata_loss_db(1000.0, 850e6, 30.0, 1.5))
    b_hata = 44.9 - 6.55 * math.log10(30.0)   # = 35.2249 (the Patwari coefficient)
    check("Hata distance slope = (44.9 - 6.55 log10 hb) log10(2) for hb=30 m",
          abs(slope - b_hata * math.log10(2.0)) < 1e-9
          and abs(b_hata - 35.2249) < 1e-4, "{0:.4f} dB".format(slope))
    # environment corrections (primary-formula regression vector, 900/30/1.5/5 km)
    l_u = emp.okumura_hata_loss_db(5000.0, 900e6, 30.0, 1.5, "urban")
    l_s = emp.okumura_hata_loss_db(5000.0, 900e6, 30.0, 1.5, "suburban")
    l_o = emp.okumura_hata_loss_db(5000.0, 900e6, 30.0, 1.5, "open")
    check("Hata environment vector: urban 151.02 / suburban 141.08 / open 122.52",
          abs(l_u - 151.024) < 0.03 and abs(l_s - 141.082) < 0.03
          and abs(l_o - 122.518) < 0.03,
          "{0:.2f}/{1:.2f}/{2:.2f}".format(l_u, l_s, l_o))
    check("Hata clutter ordering: urban > suburban > open", l_u > l_s > l_o)
    # COST-231-Hata (primary-formula regression vectors)
    c1 = emp.cost231_hata_loss_db(1000.0, 1.8e9, 30.0, 1.5, metropolitan=True)
    c2 = emp.cost231_hata_loss_db(3000.0, 1.8e9, 40.0, 2.0)
    c3 = emp.cost231_hata_loss_db(5000.0, 2.0e9, 50.0, 1.5)
    check("COST-231 vectors: 139.20 / 149.45 / 158.28 dB",
          abs(c1 - 139.197) < 0.02 and abs(c2 - 149.446) < 0.02
          and abs(c3 - 158.284) < 0.02,
          "{0:.2f}/{1:.2f}/{2:.2f}".format(c1, c2, c3))
    check("empirical_loss_db dispatches Hata <1.5 GHz, COST-231 >=1.5 GHz",
          abs(emp.empirical_loss_db(5000.0, 900e6, 30.0, 1.5) - l_u) < 1e-12
          and abs(emp.empirical_loss_db(3000.0, 1.8e9, 40.0, 2.0) - c2) < 1e-12)

    # Hata coverage MODE in the heatmap engine
    covh = heatmap.coverage_grid(40.0, -100.0, 30.0, 900e6, tx_power_dbm=50.0,
                                 model="hata", environment="urban",
                                 radius_m=10000.0, n=31, peak_gain_dbi=0.0,
                                 rx_height_m=1.5)
    ch = 15
    d_probe = geo.haversine_m(40.0, -100.0, covh.lats[ch], covh.lons[-1])
    exp_prx = 50.0 - emp.okumura_hata_loss_db(d_probe, 900e6, 30.0, 1.5, "urban")
    check("Hata coverage cell == Ptx - L(d) (engine wiring exact)",
          abs(covh.prx_dbm[ch, -1] - exp_prx) < 1e-9
          and covh.meta["environment"] == "urban")
    covs = heatmap.coverage_grid(40.0, -100.0, 30.0, 900e6, tx_power_dbm=50.0,
                                 model="hata", environment="suburban",
                                 radius_m=10000.0, n=31, peak_gain_dbi=0.0,
                                 rx_height_m=1.5)
    vh = np.isfinite(covh.prx_dbm)
    check("suburban Hata coverage stronger than urban everywhere",
          bool(np.all(covs.prx_dbm[vh] > covh.prx_dbm[vh])))

    # --- Millington mixed-path ---
    SEA = gw.GROUND_TYPES["Sea water"]
    LAND = gw.GROUND_TYPES["Dry ground"]
    single = gw.millington_field_dbuv_m([(100e3, LAND[0], LAND[1])], 1e6)
    homog = gw.field_strength_dbuv_m(100e3, 1e6, LAND[0], LAND[1])
    check("Millington single-segment == homogeneous field",
          abs(single - homog) < 1e-6, "{0:.3f} vs {1:.3f}".format(single, homog))
    seg_ls = [(50e3, LAND[0], LAND[1]), (50e3, SEA[0], SEA[1])]
    seg_sl = [(50e3, SEA[0], SEA[1]), (50e3, LAND[0], LAND[1])]
    m_ls = gw.millington_field_dbuv_m(seg_ls, 1e6)
    m_sl = gw.millington_field_dbuv_m(seg_sl, 1e6)
    check("Millington reciprocity: land->sea == sea->land",
          abs(m_ls - m_sl) < 1e-6, "{0:.2f} vs {1:.2f}".format(m_ls, m_sl))
    all_land = gw.field_strength_dbuv_m(100e3, 1e6, LAND[0], LAND[1])
    all_sea = gw.field_strength_dbuv_m(100e3, 1e6, SEA[0], SEA[1])
    check("Millington mixed path brackets between all-land and all-sea",
          all_land - 0.5 <= m_ls <= all_sea + 0.5,
          "land {0:.1f} <= mix {1:.1f} <= sea {2:.1f}".format(all_land, m_ls, all_sea))

    # --- multi-station service/interference (D/U) contours (§6 phase C cont.) ---
    # incoherent power-sum aggregation (ITU-R BT.2265 / NTIA) worked anchors
    e60 = np.array([[60.0]])
    c2 = float(ms.combine_fields_dbuv_m([e60, e60])[0, 0])
    check("D/U combine: two equal 60 dBuV/m -> +3.0103 dB (power sum)",
          abs(c2 - 63.0103) < 1e-3, "{0:.4f}".format(c2))
    c3 = float(ms.combine_fields_dbuv_m([e60, e60, e60])[0, 0])
    check("D/U combine: N equal add 10log10(N) (3 -> +4.771)",
          abs(c3 - (60.0 + 10.0 * math.log10(3.0))) < 1e-9)
    cbt = float(ms.combine_fields_dbuv_m([np.array([[34.0]]),
                                          np.array([[33.0]])])[0, 0])
    check("D/U combine matches ITU-R BT.2265 (34,33 -> 36.539 dBuV/m)",
          abs(cbt - 36.539) < 1e-2, "{0:.3f}".format(cbt))
    a2 = np.array([[50.0, 55.0]])
    b2 = np.array([[52.0, 40.0]])
    wc = ms.combine_fields_dbuv_m([a2, b2], "worst_case")
    ps = ms.combine_fields_dbuv_m([a2, b2])
    check("D/U combine: worst_case = strongest, power_sum >= worst_case",
          np.allclose(wc, np.array([[52.0, 55.0]])) and bool(np.all(ps >= wc - 1e-9)))

    # the two-gate classification (an FCC OET-69 served/interfered worked cell)
    cls, du = ms.classify(np.array([[50.0]]), np.array([[38.0]]), 41.0, 15.27)
    check("classify: desired 50 / thr 41 / undesired 38 -> interference-limited (D/U 12)",
          cls[0, 0] == ms.INTERFERENCE_LIMITED and abs(du[0, 0] - 12.0) < 1e-9)
    cls2, _ = ms.classify(np.array([[50.0]]), np.array([[34.0]]), 41.0, 15.27)
    check("classify: undesired 34 -> D/U 16 >= 15.27 -> served", cls2[0, 0] == ms.SERVED)
    cls3, _ = ms.classify(np.array([[30.0]]), None, 41.0, 15.27)
    check("classify: below service threshold -> no service", cls3[0, 0] == ms.NO_SERVICE)
    cls4, du4 = ms.classify(np.array([[50.0]]), None, 41.0, 15.27)
    check("classify: no interferer + in coverage -> served (D/U=+inf)",
          cls4[0, 0] == ms.SERVED and math.isinf(du4[0, 0]))
    check("D/U reuses the §5 co-site du_ratio_db (wanted - unwanted)",
          abs(cosite.du_ratio_db(50.0, 38.0) - du[0, 0]) < 1e-9)

    # protection-ratio library: present, source-tagged, known regulatory values
    check("FCC FM co-channel protection ratio = 20 dB",
          ms.PROTECTION_RATIOS["FM co-channel (FCC 73.215)"][0] == 20.0)
    check("AM/MF co-channel protection ratio = 26 dB (= 20:1 voltage)",
          abs(ms.PROTECTION_RATIOS["AM/MF co-channel (FCC / ITU Region 2)"][0]
              - 20.0 * math.log10(20.0)) < 0.03)
    check("protection ratios are all source-tagged",
          all(isinstance(v[1], str) and v[1] for v in ms.PROTECTION_RATIOS.values()))

    # end-to-end: two co-channel MF stations (generic coords, no site names)
    A = ms.Station("Wanted", 40.0, -100.0, height_m=100.0, freq_hz=1e6, power_dbm=70.0)
    B = ms.Station("Interferer", 40.0, -99.65, height_m=100.0, freq_hz=1e6,
                   power_dbm=70.0)
    svc = ms.service_contour([A, B], wanted=0, radius_m=40000.0, n=61,
                             protection_ratio_db=26.0, service_threshold_dbuv_m=40.0,
                             model="ground_wave")
    n2 = svc.meta["n"]
    rr = n2 // 2 + 3
    jW = int(np.argmin(np.abs(svc.lons - A.lon)))
    jB = int(np.argmin(np.abs(svc.lons - B.lon)))
    check("service D/U: high toward wanted, negative toward interferer",
          svc.du_db[rr, jW] > 20.0 and svc.du_db[rr, jB] < -10.0,
          "wanted {0:.1f} / interf {1:.1f} dB".format(svc.du_db[rr, jW],
                                                      svc.du_db[rr, jB]))
    check("service map has both served + interference-limited cells",
          0.0 < svc.fraction(ms.SERVED) < 1.0
          and svc.fraction(ms.INTERFERENCE_LIMITED) > 0.0,
          "{0:.0%} served".format(svc.fraction(ms.SERVED)))
    # reciprocity on a fixed shared centre: swapping wanted flips the D/U sign
    ca = ms.service_contour([A, B], wanted=0, center=(40.0, -99.825),
                            radius_m=40000.0, n=41)
    cb = ms.service_contour([A, B], wanted=1, center=(40.0, -99.825),
                            radius_m=40000.0, n=41)
    check("service D/U reciprocity (wanted<->interferer flips sign)",
          np.allclose(ca.du_db, -cb.du_db, equal_nan=True))
    # power-sum aggregates louder than worst-case -> a lower (stricter) D/U
    Cst = ms.Station("Int2", 39.8, -99.7, height_m=100.0, freq_hz=1e6, power_dbm=70.0)
    sp = ms.service_contour([A, B, Cst], wanted=0, radius_m=40000.0, n=31,
                            combine="power_sum", service_threshold_dbuv_m=40.0)
    sw = ms.service_contour([A, B, Cst], wanted=0, radius_m=40000.0, n=31,
                            combine="worst_case", service_threshold_dbuv_m=40.0)
    mm = np.isfinite(sp.du_db) & np.isfinite(sw.du_db)
    check("multi-interferer power-sum D/U <= worst-case D/U",
          bool(np.all(sp.du_db[mm] <= sw.du_db[mm] + 1e-9)))
    # co-channel filtering removes an off-channel station from the unwanted set
    Boff = ms.Station("OffCh", 40.0, -99.65, height_m=100.0, freq_hz=1.2e6,
                      power_dbm=70.0)
    sfc = ms.service_contour([A, Boff], wanted=0, radius_m=40000.0, n=21,
                             channel_bw_hz=50e3, service_threshold_dbuv_m=40.0)
    check("channel_bw_hz drops the off-channel interferer (§5 in_band reuse)",
          sfc.meta["n_interferers"] == 0 and sfc.unwanted_field is None)

    # network best-server view: strongest station serves each cell, splits at midline
    bs = ms.best_server([A, B], radius_m=40000.0, n=61, service_threshold_dbuv_m=40.0,
                        protection_ratio_db=26.0)
    srv = bs["server"]
    check("best_server: only valid station indices (or -1)",
          set(np.unique(srv).tolist()) <= {-1, 0, 1})
    west = srv[:, :n2 // 3]
    east = srv[:, -(n2 // 3):]
    check("best_server splits: wanted serves the west, interferer the east",
          (west == 0).sum() > (west == 1).sum()
          and (east == 1).sum() > (east == 0).sum())

    # KML export of a D/U layer through the shipped kml primitives
    svc_kml = os.path.join(tmp, "service.kml")
    kp2, pp2 = ms.export_service_kml(svc, svc_kml, metric="du")
    check("export_service_kml writes .kml + .png",
          os.path.getsize(kp2) > 0 and os.path.getsize(pp2) > 0)

    # --- KML export ---
    kml_xml = kml.kml_groundoverlay_xml(1.0, 0.0, 2.0, 0.5, "coverage.png",
                                        tx_lat=0.5, tx_lon=1.0)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(kml_xml)
    ns = "{http://www.opengis.net/kml/2.2}"
    box = root.find(".//{0}LatLonBox".format(ns))
    n_, s_ = float(box.find(ns + "north").text), float(box.find(ns + "south").text)
    e_, w_ = float(box.find(ns + "east").text), float(box.find(ns + "west").text)
    check("KML LatLonBox north>south, east>west", n_ > s_ and e_ > w_)
    href = root.find(".//{0}href".format(ns))
    check("KML GroundOverlay href references the PNG",
          href is not None and href.text.endswith(".png"))
    check("KML has a transmitter placemark",
          root.find(".//{0}Placemark".format(ns)) is not None)
    kpath = os.path.join(tmp, "cov.kml")
    kp, pp = kml.export_coverage_kml(cov, kpath, metric="prx")
    check("export_coverage_kml writes .kml + .png",
          os.path.getsize(kp) > 0 and os.path.getsize(pp) > 0)

    if FAILURES:
        print("COVERAGE GATE FAILED: {0}".format(FAILURES))
        return 1
    print("COVERAGE GATE PASSED")
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
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("coverage validation failed")
    sys.exit(0)
