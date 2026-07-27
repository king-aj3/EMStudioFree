# SPDX-License-Identifier: LGPL-2.1-or-later
"""Digital-elevation-model (DEM) import + terrain path profiles (ROADMAP §6, phase B).

Reads elevation data with NO heavy geo dependency (no GDAL/rasterio), because the
workbench runs inside FreeCAD's bundled Python where those are usually absent:

* ``.hgt`` — the canonical SRTM / NASADEM format: a square grid of big-endian
  signed 16-bit metres, row 0 = north edge, column 0 = west edge, whose 1-degree
  tile corner is encoded in the filename (``N34W119.hgt`` etc.). Zero dependency
  (numpy only). SRTM3 = 1201x1201 (3 arc-sec), SRTM1/NASADEM = 3601x3601 (1 arc-sec).
* ``.tif`` / ``.tiff`` — a MINIMAL GeoTIFF reader for the common single-strip case
  (uncompressed or DEFLATE via stdlib ``zlib``) with ``ModelPixelScale`` +
  ``ModelTiepoint`` georeferencing (the layout gdal/QGIS write for ASTER-style
  DEMs). LZW / tiled / multi-band GeoTIFFs raise a clear error pointing at ``.hgt``
  or ``gdal_translate -co COMPRESS=DEFLATE`` — we deliberately don't pull in a full
  TIFF stack.

A ``DEM`` mosaics one or more tiles and answers ``elevation(lat, lon)`` by bilinear
interpolation (NaN outside coverage / on voids). ``path_profile`` samples the
great circle from a transmitter to a point, looks up the ground under each sample,
and adds the effective-earth-radius bulge so the shipped ``propagation.
terrain_profile_loss`` (single-edge Deygout) sees the horizon.

Pure-python + numpy, Qt-free, FreeCAD-free. SI: metres, degrees.
"""
from __future__ import annotations

import math
import os
import struct
import zlib

import numpy as np

from emstudio.coverage import geodesy

VOID = float("nan")


class DEMError(ValueError):
    """Raised for an unreadable / unsupported DEM file."""


class DEMTile:
    """A single north-up elevation grid over a lat/lon rectangle.

    ``data`` is shape (rows, cols), row 0 the NORTH edge. ``lat_max``/``lon_min``
    are the top-left cell-centre coordinates (pixel-is-point convention), and
    ``dlat``/``dlon`` the per-pixel step in degrees (positive).
    """

    def __init__(self, data, lat_max, lon_min, dlat, dlon, name=""):
        self.data = np.asarray(data, dtype=np.float64)
        self.rows, self.cols = self.data.shape
        self.lat_max = float(lat_max)
        self.lon_min = float(lon_min)
        self.dlat = float(dlat)
        self.dlon = float(dlon)
        self.name = name or ""
        self.lat_min = self.lat_max - (self.rows - 1) * self.dlat
        self.lon_max = self.lon_min + (self.cols - 1) * self.dlon

    def contains(self, lat, lon):
        return (self.lat_min - 0.5 * self.dlat <= lat <= self.lat_max + 0.5 * self.dlat
                and self.lon_min - 0.5 * self.dlon <= lon <= self.lon_max + 0.5 * self.dlon)

    def elevation(self, lat, lon):
        """Bilinear elevation (m) at (lat, lon); NaN outside the tile or on a void."""
        col = (lon - self.lon_min) / self.dlon
        row = (self.lat_max - lat) / self.dlat
        if col < -1e-9 or col > self.cols - 1 + 1e-9 or \
                row < -1e-9 or row > self.rows - 1 + 1e-9:
            return VOID
        col = min(max(col, 0.0), self.cols - 1)
        row = min(max(row, 0.0), self.rows - 1)
        c0, r0 = int(math.floor(col)), int(math.floor(row))
        c1, r1 = min(c0 + 1, self.cols - 1), min(r0 + 1, self.rows - 1)
        fc, fr = col - c0, row - r0
        v00, v01 = self.data[r0, c0], self.data[r0, c1]
        v10, v11 = self.data[r1, c0], self.data[r1, c1]
        if np.isnan(v00) or np.isnan(v01) or np.isnan(v10) or np.isnan(v11):
            # fall back to the nearest valid corner rather than poisoning the map
            vals = [v for v in (v00, v01, v10, v11) if not np.isnan(v)]
            return float(np.mean(vals)) if vals else VOID
        return float(v00 * (1 - fc) * (1 - fr) + v01 * fc * (1 - fr)
                     + v10 * (1 - fc) * fr + v11 * fc * fr)


# --------------------------------------------------------------- .HGT ---------
def _hgt_corner_from_name(path):
    """SW corner (lat, lon) from an SRTM ``N34W119.hgt`` style filename."""
    base = os.path.basename(path).split(".")[0].upper()
    try:
        lat = int(base[1:3]) * (1 if base[0] == "N" else -1)
        lon = int(base[4:7]) * (1 if base[3] == "E" else -1)
    except (ValueError, IndexError):
        raise DEMError(
            "cannot read the tile corner from '{0}' — SRTM .hgt files are named "
            "like N34W119.hgt (the 1-degree SW corner)".format(os.path.basename(path)))
    return lat, lon


def read_hgt(path):
    """Read an SRTM/NASADEM ``.hgt`` tile into a :class:`DEMTile`."""
    n_shorts = os.path.getsize(path) // 2
    size = int(round(math.sqrt(n_shorts)))
    if size * size != n_shorts or size < 2:
        raise DEMError(
            "{0} is not a square .hgt grid ({1} samples)".format(
                os.path.basename(path), n_shorts))
    sw_lat, sw_lon = _hgt_corner_from_name(path)
    arr = np.fromfile(path, dtype=">i2").reshape(size, size).astype(np.float64)
    arr[arr <= -32768] = VOID  # SRTM void marker
    step = 1.0 / (size - 1)     # a 1-degree tile
    return DEMTile(arr, lat_max=sw_lat + 1.0, lon_min=sw_lon,
                   dlat=step, dlon=step, name=os.path.basename(path))


# ------------------------------------------------------------ GeoTIFF ---------
_TIFF_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 12: 8}  # BYTE ASCII SHORT LONG RATIONAL DOUBLE
_TAG = dict(width=256, length=257, bits=258, compression=259, strip_offsets=273,
            samples_per_pixel=277, rows_per_strip=278, strip_byte_counts=279,
            sample_format=339, pixel_scale=33550, tiepoint=33922, tile_width=322)


def read_geotiff(path):
    """Read a minimal single-strip int16/uint16/float32 GeoTIFF into a DEMTile.

    Supports uncompressed and DEFLATE (zlib) compression with pixel-scale +
    tiepoint georeferencing. Anything else (LZW, tiled, multi-band) raises DEMError.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:2] == b"II":
        bo = "<"
    elif data[:2] == b"MM":
        bo = ">"
    else:
        raise DEMError("{0} is not a TIFF (bad byte-order mark)".format(
            os.path.basename(path)))
    (magic,) = struct.unpack(bo + "H", data[2:4])
    if magic != 42:
        raise DEMError("BigTIFF / non-classic TIFF not supported — convert with "
                       "gdal_translate, or use SRTM .hgt")
    (ifd,) = struct.unpack(bo + "I", data[4:8])
    (n_entries,) = struct.unpack(bo + "H", data[ifd:ifd + 2])
    tags = {}
    for i in range(n_entries):
        base = ifd + 2 + i * 12
        tag, typ, cnt = struct.unpack(bo + "HHI", data[base:base + 8])
        size = _TIFF_TYPE_SIZE.get(typ, 1) * cnt
        raw = data[base + 8:base + 12]
        if size > 4:
            (off,) = struct.unpack(bo + "I", raw)
            raw = data[off:off + size]
        if typ == 3:
            tags[tag] = list(struct.unpack(bo + "H" * cnt, raw[:2 * cnt]))
        elif typ == 4:
            tags[tag] = list(struct.unpack(bo + "I" * cnt, raw[:4 * cnt]))
        elif typ == 12:
            tags[tag] = list(struct.unpack(bo + "d" * cnt, raw[:8 * cnt]))
        else:
            tags[tag] = list(raw[:size])

    if _TAG["tile_width"] in tags:
        raise DEMError("tiled GeoTIFF not supported — gdal_translate -co TILED=NO, "
                       "or use SRTM .hgt")
    w = tags[_TAG["width"]][0]
    h = tags[_TAG["length"]][0]
    bits = tags.get(_TAG["bits"], [16])[0]
    sf = tags.get(_TAG["sample_format"], [2])[0]       # 1=uint, 2=int, 3=float
    comp = tags.get(_TAG["compression"], [1])[0]
    spp = tags.get(_TAG["samples_per_pixel"], [1])[0]
    if spp != 1:
        raise DEMError("multi-band GeoTIFF ({0} bands) not supported — extract the "
                       "elevation band, or use .hgt".format(spp))
    offsets = tags.get(_TAG["strip_offsets"])
    counts = tags.get(_TAG["strip_byte_counts"])
    if not offsets or not counts:
        raise DEMError("GeoTIFF has no strip data (unsupported layout)")
    blob = bytearray()
    for off, cnt in zip(offsets, counts):
        chunk = data[off:off + cnt]
        if comp == 8 or comp == 32946:      # DEFLATE (zlib)
            chunk = zlib.decompress(chunk)
        elif comp != 1:
            raise DEMError("unsupported TIFF compression {0} — re-save with "
                           "gdal_translate -co COMPRESS=DEFLATE, or use .hgt".format(comp))
        blob += chunk
    dtype = {(16, 2): "i2", (16, 1): "u2", (32, 3): "f4",
             (32, 2): "i4"}.get((bits, sf))
    if dtype is None:
        raise DEMError("unsupported sample type ({0} bits, format {1})".format(bits, sf))
    arr = np.frombuffer(bytes(blob[:w * h * (bits // 8)]),
                        dtype=bo + dtype).reshape(h, w).astype(np.float64)

    scale = tags.get(_TAG["pixel_scale"])
    tie = tags.get(_TAG["tiepoint"])
    if not scale or not tie:
        raise DEMError("GeoTIFF missing ModelPixelScale/ModelTiepoint — not "
                       "georeferenced; use a DEM export with geo tags or .hgt")
    dlon, dlat = float(scale[0]), float(scale[1])
    # tiepoint: (i, j, k, X, Y, Z); world of pixel (i, j). Shift to the raster origin.
    i0, j0, _k, x0, y0 = tie[0], tie[1], tie[2], tie[3], tie[4]
    lon_min = x0 - i0 * dlon
    lat_max = y0 + j0 * dlat
    return DEMTile(arr, lat_max=lat_max, lon_min=lon_min, dlat=dlat, dlon=dlon,
                   name=os.path.basename(path))


# --------------------------------------------------------------- DEM ----------
def read_tile(path):
    """Read a single DEM file, dispatching on extension (.hgt / .tif|.tiff)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".hgt":
        return read_hgt(path)
    if ext in (".tif", ".tiff"):
        return read_geotiff(path)
    raise DEMError("unknown DEM format '{0}' (expected .hgt / .tif)".format(ext))


class DEM:
    """One or more DEM tiles queried as a single elevation surface."""

    def __init__(self, tiles):
        self.tiles = list(tiles)
        if not self.tiles:
            raise DEMError("a DEM needs at least one tile")

    @classmethod
    def load(cls, path):
        """Load a DEM from a single file, or from a directory of ``.hgt``/``.tif``."""
        if os.path.isdir(path):
            tiles = []
            for name in sorted(os.listdir(path)):
                if os.path.splitext(name)[1].lower() in (".hgt", ".tif", ".tiff"):
                    tiles.append(read_tile(os.path.join(path, name)))
            if not tiles:
                raise DEMError("no .hgt / .tif DEM tiles found in {0}".format(path))
            return cls(tiles)
        return cls([read_tile(path)])

    @property
    def bounds(self):
        """(lat_min, lat_max, lon_min, lon_max) covering every tile."""
        return (min(t.lat_min for t in self.tiles),
                max(t.lat_max for t in self.tiles),
                min(t.lon_min for t in self.tiles),
                max(t.lon_max for t in self.tiles))

    def elevation(self, lat, lon):
        """Elevation (m) at (lat, lon) from the covering tile; NaN outside coverage."""
        for t in self.tiles:
            if t.contains(lat, lon):
                v = t.elevation(lat, lon)
                if not np.isnan(v):
                    return v
        return VOID


def path_profile(dem, tx_lat, tx_lon, rx_lat, rx_lon, n_samples=64,
                 k_factor=4.0 / 3.0, void_fill=0.0):
    """Terrain profile from (tx) to (rx) as ``[(distance_m, elevation_m), ...]``.

    Samples ``n_samples`` intervals along the great circle, looks up the DEM under
    each point, and adds the effective-earth-radius bulge so the single-edge
    Deygout model in :mod:`emstudio.coverage.propagation` accounts for the horizon.
    Voids (outside the DEM / SRTM holes) are filled with ``void_fill`` metres.
    Pass ``dem=None`` for a flat surface (bulge only).
    """
    pts = geodesy.sample_great_circle(tx_lat, tx_lon, rx_lat, rx_lon, n_samples)
    d_tot = pts[-1][2]
    prof = []
    for (la, lo, d) in pts:
        z = dem.elevation(la, lo) if dem is not None else 0.0
        if z is None or (isinstance(z, float) and np.isnan(z)):
            z = void_fill
        bulge = geodesy.earth_bulge_m(d, d_tot - d, k_factor)
        prof.append((d, float(z) + bulge))
    return prof
