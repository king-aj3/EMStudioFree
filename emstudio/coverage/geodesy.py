# SPDX-License-Identifier: LGPL-2.1-or-later
"""Spherical-earth geodesy for coverage/propagation (ROADMAP §6, phase B).

Great-circle distance, bearing, destination and interpolation on a sphere, plus
the effective-earth-radius (4/3) bulge used to fold earth curvature into a terrain
path profile. Enough for tx->grid-point path sampling over a DEM; the WGS84
ellipsoid refinement is not needed at coverage-map accuracy (< 0.5 % vs the
haversine sphere over the ~100 km ranges these maps cover).

Pure-python, Qt-free, FreeCAD-free. Angles in degrees, distances in metres.
Transmitter/receiver locations are user-supplied; no specific sites referenced.
"""
from __future__ import annotations

import math

# IUGG mean earth radius (m). The one radius used everywhere so distances,
# bulge and grid spacing stay mutually consistent.
R_EARTH = 6371008.8


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance (m) between two lat/lon points on the mean sphere."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2.0) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2)
    return 2.0 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing (compass degrees, 0 = North, clockwise)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def destination_point(lat, lon, bearing_deg, dist_m):
    """Point (lat, lon) reached from (lat, lon) along ``bearing_deg`` for ``dist_m``."""
    d = float(dist_m) / R_EARTH
    br = math.radians(bearing_deg)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d)
                   + math.cos(p1) * math.sin(d) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0


def intermediate_point(lat1, lon1, lat2, lon2, fraction):
    """Point a ``fraction`` (0..1) of the way along the great circle (slerp)."""
    p1, l1 = math.radians(lat1), math.radians(lon1)
    p2, l2 = math.radians(lat2), math.radians(lon2)
    d = haversine_m(lat1, lon1, lat2, lon2) / R_EARTH
    if d < 1e-12:
        return float(lat1), float(lon1)
    a = math.sin((1.0 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return (math.degrees(math.atan2(z, math.hypot(x, y))),
            math.degrees(math.atan2(y, x)))


def sample_great_circle(lat1, lon1, lat2, lon2, n_samples):
    """``n_samples+1`` evenly-spaced points from end 1 to end 2.

    Returns a list of ``(lat, lon, distance_m_from_end1)`` including both endpoints.
    """
    n = max(int(n_samples), 1)
    d_tot = haversine_m(lat1, lon1, lat2, lon2)
    out = []
    for i in range(n + 1):
        f = i / n
        la, lo = intermediate_point(lat1, lon1, lat2, lon2, f)
        out.append((la, lo, f * d_tot))
    return out


def earth_bulge_m(d1_m, d2_m, k_factor=4.0 / 3.0):
    """Height (m) the curved earth rises above the straight tx-rx chord at a point
    ``d1``/``d2`` from the two ends: d1*d2/(2*k*Re). ``k_factor`` is the effective-
    earth-radius factor (4/3 for standard atmospheric refraction; use a large value
    to disable curvature). Added to terrain elevations so a flat-earth diffraction
    model accounts for the horizon."""
    if k_factor <= 0:
        return 0.0
    return float(d1_m) * float(d2_m) / (2.0 * k_factor * R_EARTH)


def meters_per_degree(lat_deg):
    """(m per degree latitude, m per degree longitude) at ``lat_deg`` — for turning
    a coverage radius in metres into a lat/lon grid half-extent."""
    lat_m = math.pi * R_EARTH / 180.0
    lon_m = lat_m * math.cos(math.radians(lat_deg))
    return lat_m, lon_m
