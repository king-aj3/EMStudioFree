# SPDX-License-Identifier: LGPL-2.1-or-later
"""FastHenry .inp deck writer for parallel wire paths.

Input model: a list of 3-D polylines (meters), all electrically in parallel (their
ends shorted — the Litz-bundle case). Round conductors are represented by FastHenry's
rectangular segments with the equal-area square w = h = r*sqrt(pi); expect a ~5%
high bias in the skin-limited regime (square perimeter vs round), verified against
the exact Bessel solution on 2026-07-05.
"""

from __future__ import annotations

import math

M_TO_MM = 1e3


def write_inp(path, wire_paths, radius_m, sigma_s_per_m, fmin, fmax, ndec, nhinc=9,
              ports="parallel"):
    """Write a FastHenry deck. Returns the deck path.

    :param wire_paths: list of polylines; each polyline is [(x,y,z), ...] in meters.
    :param radius_m: conductor radius (round; converted to equal-area square).
                     A scalar applies to every path; a list gives per-path radii
                     (mixed-conductor bundles).
    :param sigma_s_per_m: conductivity in S/m (deck uses S/mm).
    :param fmin/fmax/ndec: log frequency sweep (Hz, points per decade).
    :param ports: 'parallel' (all paths shorted -> one port) or 'per_path'
                  (one port per path -> N x N Zc for current-sharing /
                  bundle-coupling analysis).
    """
    try:
        radii = [float(r) for r in radius_m]
    except TypeError:
        radii = [float(radius_m)] * len(wire_paths)
    if len(radii) != len(wire_paths):
        raise ValueError("radius_m list must match wire_paths length")
    w_mms = [r * math.sqrt(math.pi) * M_TO_MM for r in radii]  # equal-area squares
    sigma_mm = sigma_s_per_m / 1e3  # S/m -> S/mm

    lines = [
        "* EMStudio generated FastHenry deck ({0} parallel path(s))".format(len(wire_paths)),
        ".Units MM",
        ".Default sigma={0:.6g}".format(sigma_mm),
    ]

    # nodes + segments per path
    for pi, pts in enumerate(wire_paths):
        if len(pts) < 2:
            raise ValueError("wire path {0} needs at least 2 points".format(pi))
        for ni, (x, y, z) in enumerate(pts):
            lines.append(
                "NP{0}_{1} x={2:.6f} y={3:.6f} z={4:.6f}".format(
                    pi, ni, x * M_TO_MM, y * M_TO_MM, z * M_TO_MM
                )
            )
        for si in range(len(pts) - 1):
            lines.append(
                "EP{0}_{1} NP{0}_{1} NP{0}_{2} w={3:.6f} h={3:.6f} nhinc={4} nwinc={4}".format(
                    pi, si, si + 1, w_mms[pi], nhinc
                )
            )

    if ports == "parallel":
        # short all path ends together (parallel bundle), port on path 0's ends
        for pi in range(1, len(wire_paths)):
            lines.append(".Equiv NP0_0 NP{0}_0".format(pi))
            lines.append(".Equiv NP0_{0} NP{1}_{2}".format(
                len(wire_paths[0]) - 1, pi, len(wire_paths[pi]) - 1))
        lines.append(".External NP0_0 NP0_{0}".format(len(wire_paths[0]) - 1))
    elif ports == "per_path":
        # one port per path -> N x N impedance matrix (current-sharing analysis)
        for pi in range(len(wire_paths)):
            lines.append(".External NP{0}_0 NP{0}_{1}".format(pi, len(wire_paths[pi]) - 1))
    else:
        raise ValueError("ports must be 'parallel' or 'per_path'")
    lines.append(".Freq fmin={0:.6g} fmax={1:.6g} ndec={2}".format(fmin, fmax, ndec))
    lines.append(".End")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path
