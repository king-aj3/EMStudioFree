# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wire-size unit conversions: AWG, mm, mil.

AWG (American Wire Gauge) is the native unit of litz strand specification in North
America (typical litz strands: 30-48 AWG). Standard formula:
    d(mm) = 0.127 * 92^((36 - AWG) / 39)
"""

from __future__ import annotations

import math

MIL_TO_M = 25.4e-6
MM_TO_M = 1e-3


def awg_to_m(awg):
    """Bare-copper diameter of an AWG gauge, in meters (supports fractional AWG)."""
    return 0.127e-3 * 92.0 ** ((36.0 - float(awg)) / 39.0)


def m_to_awg(d_m):
    """Nearest (possibly fractional) AWG for a diameter in meters."""
    return 36.0 - 39.0 * math.log(d_m / 0.127e-3) / math.log(92.0)


def to_meters(value, unit):
    """Convert a wire diameter in ('mm' | 'mil' | 'AWG') to meters."""
    unit = unit.strip().lower()
    if unit == "mm":
        return float(value) * MM_TO_M
    if unit == "mil":
        return float(value) * MIL_TO_M
    if unit == "awg":
        return awg_to_m(value)
    raise ValueError("unknown wire-size unit: " + unit)


def format_diameter(d_m):
    """Human string with all three units: '0.100 mm (3.94 mil, AWG 38.0)'."""
    return "{0:.4g} mm ({1:.3g} mil, AWG {2:.1f})".format(
        d_m * 1e3, d_m / MIL_TO_M, m_to_awg(d_m)
    )
