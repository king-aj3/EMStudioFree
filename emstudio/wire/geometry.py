# SPDX-License-Identifier: LGPL-2.1-or-later
"""Strand-path generation for twisted wire bundles (Litz Type 1, hex packing).

Generates the 3-D polylines of individually twisted strands: hexagonal ring packing
(1, 7, 19, 37, 61... strands) rotating rigidly about the bundle axis with a given
twist pitch. These paths feed the FastHenry backend directly (no CAD geometry needed)
and can later be swept into visual FreeCAD geometry.
"""

from __future__ import annotations

import math

HEX_COUNTS = [1, 7, 19, 37, 61, 91, 127]


def hex_positions(n_strands, strand_pitch_m):
    """(x, y) centers for n_strands hex-packed strands with center spacing.

    Supports the standard hex numbers (1, 7, 19, 37, ...); raises otherwise.
    """
    if n_strands not in HEX_COUNTS:
        raise ValueError(
            "hex packing supports {0} strands, not {1}".format(HEX_COUNTS, n_strands)
        )
    pts = [(0.0, 0.0)]
    ring = 1
    while len(pts) < n_strands:
        # ring k has 6k strands at radius k*pitch, corners of a hexagon + edges
        for i in range(6 * ring):
            angle_step = 2.0 * math.pi / (6 * ring)
            ang = i * angle_step
            pts.append((ring * strand_pitch_m * math.cos(ang),
                        ring * strand_pitch_m * math.sin(ang)))
        ring += 1
    return pts[:n_strands]


def twisted_bundle_paths(
    n_strands,
    strand_radius_m,
    length_m,
    twist_pitch_m,
    points_per_turn=16,
    spacing_factor=1.05,
):
    """3-D strand polylines of a Type-1 bunched litz.

    Every strand follows a helix around the bundle axis (z), all with the same pitch
    (rigid-rotation bunching — the Type-1 construction). ``spacing_factor`` leaves a
    little room for strand insulation.
    Returns list of [(x, y, z), ...] in meters.
    """
    centers = hex_positions(n_strands, 2.0 * strand_radius_m * spacing_factor)
    turns = length_m / twist_pitch_m if twist_pitch_m > 0 else 0.0
    n_pts = max(2, int(math.ceil(turns * points_per_turn)) + 1)
    paths = []
    for cx, cy in centers:
        pts = []
        for i in range(n_pts):
            z = length_m * i / (n_pts - 1)
            ang = 2.0 * math.pi * (z / twist_pitch_m) if twist_pitch_m > 0 else 0.0
            x = cx * math.cos(ang) - cy * math.sin(ang)
            y = cx * math.sin(ang) + cy * math.cos(ang)
            pts.append((x, y, z))
        paths.append(pts)
    return paths
