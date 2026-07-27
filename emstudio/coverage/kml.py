# SPDX-License-Identifier: LGPL-2.1-or-later
"""KML export of a coverage heatmap (ROADMAP §6, phase B).

Writes a Google-Earth ``GroundOverlay``: a colour-mapped PNG of the coverage grid
draped over its lat/lon box, plus a transmitter placemark. The KML document itself
is a pure-string build (validated by the gate without any image library); the PNG
is rendered with matplotlib, imported lazily so this module stays GUI-safe and
import-clean headless.

SI in / degrees; ``metric`` selects received power (dBm) or field strength
(dBuV/m). Transmitter location is user-supplied; no specific sites referenced.
"""
from __future__ import annotations

import os

import numpy as np

_KML_NS = "http://www.opengis.net/kml/2.2"


def _color_ramp():
    """(name, KML abgr color) legend stops, low->high — a blue->red 'jet'-ish ramp."""
    return [("weak", "ffff0000"), ("fair", "ffffff00"), ("good", "ff00ff00"),
            ("strong", "ff0000ff")]


def kml_groundoverlay_xml(north, south, east, west, png_href,
                          tx_lat=None, tx_lon=None, name="EMStudio coverage",
                          description=""):
    """Return a well-formed KML string draping ``png_href`` over the lat/lon box."""
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="{0}">'.format(_KML_NS),
             '  <Document>',
             '    <name>{0}</name>'.format(esc(name))]
    if description:
        parts.append('    <description>{0}</description>'.format(esc(description)))
    parts += [
        '    <GroundOverlay>',
        '      <name>{0}</name>'.format(esc(name)),
        '      <Icon><href>{0}</href></Icon>'.format(esc(png_href)),
        '      <LatLonBox>',
        '        <north>{0:.8f}</north>'.format(north),
        '        <south>{0:.8f}</south>'.format(south),
        '        <east>{0:.8f}</east>'.format(east),
        '        <west>{0:.8f}</west>'.format(west),
        '      </LatLonBox>',
        '    </GroundOverlay>']
    if tx_lat is not None and tx_lon is not None:
        parts += [
            '    <Placemark>',
            '      <name>Transmitter</name>',
            '      <Point><coordinates>{0:.8f},{1:.8f},0</coordinates></Point>'.format(
                tx_lon, tx_lat),
            '    </Placemark>']
    parts += ['  </Document>', '</kml>', '']
    return "\n".join(parts)


def render_png(result, png_path, metric="prx", vmin=None, vmax=None, cmap="jet",
               dpi=100, threshold=None):
    """Render the coverage grid to a transparent PNG (matplotlib, lazy import).

    Rows/cols follow ``result.lats``/``lons`` ascending; the image is drawn with
    ``origin='lower'`` so north is up, matching the KML LatLonBox. Cells below
    ``threshold`` (and NaN) are left transparent.
    """
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    g = np.array(result.grid(metric), dtype=float)
    if threshold is not None:
        g = np.where(g >= threshold, g, np.nan)
    masked = np.ma.masked_invalid(g)
    fig = plt.figure(figsize=(6, 6), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    cmap_obj = plt.get_cmap(cmap).copy()
    cmap_obj.set_bad(alpha=0.0)
    ax.imshow(masked, origin="lower", cmap=cmap_obj, vmin=vmin, vmax=vmax,
              interpolation="bilinear", aspect="auto")
    fig.savefig(png_path, transparent=True, dpi=dpi)
    plt.close(fig)
    return png_path


def export_coverage_kml(result, kml_path, metric="prx", vmin=None, vmax=None,
                        cmap="jet", threshold=None, name="EMStudio coverage"):
    """Render the heatmap PNG and write the KML GroundOverlay next to it.

    Returns ``(kml_path, png_path)``. Google Earth / QGIS open the .kml directly.
    """
    base = os.path.splitext(kml_path)[0]
    png_path = base + ".png"
    render_png(result, png_path, metric=metric, vmin=vmin, vmax=vmax, cmap=cmap,
               threshold=threshold)
    north, south, east, west = result.bounds
    unit = "field strength (dBuV/m)" if metric.startswith("field") else "Prx (dBm)"
    desc = "EMStudio {0} coverage — {1:.4g} MHz, {2:g} W ERP peak".format(
        unit, result.meta.get("freq_hz", 0.0) / 1e6,
        10.0 ** ((result.meta.get("tx_power_dbm", 0.0)
                  + result.meta.get("peak_gain_dbi", 0.0) - 30.0) / 10.0))
    xml = kml_groundoverlay_xml(
        north, south, east, west, os.path.basename(png_path),
        tx_lat=result.meta.get("tx_lat"), tx_lon=result.meta.get("tx_lon"),
        name=name, description=desc)
    with open(kml_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    return kml_path, png_path
