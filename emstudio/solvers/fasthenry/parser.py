# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parse FastHenry Zc.mat output.

Format (verified against FastHenry 3.0.1 on 2026-07-05):

    Row 1:  n1  to  n2
    Impedance matrix for frequency = 1000 1 x 1
       0.000549422  +0.000570115j
    Impedance matrix for frequency = 10000 1 x 1
       ...
"""

from __future__ import annotations

import math
import re

_FREQ_RE = re.compile(r"Impedance matrix for frequency\s*=\s*([0-9.eE+-]+)")
_Z_RE = re.compile(r"([+-]?[0-9.]+(?:[eE][+-]?[0-9]+)?)\s*([+-]\s*[0-9.]+(?:[eE][+-]?[0-9]+)?)j")


class FastHenryParseError(RuntimeError):
    pass


def parse_zc(path):
    """Returns (freqs_hz, R_ohm, L_henry) lists for a 1-port Zc.mat."""
    freqs, mats = parse_zc_matrix(path)
    rs = [m[0][0].real for m in mats]
    ls = [m[0][0].imag / (2.0 * math.pi * f) for f, m in zip(freqs, mats)]
    return freqs, rs, ls


def parse_zc_matrix(path):
    """Full N x N parse: returns (freqs_hz, list of NxN complex matrices)."""
    freqs, mats = [], []
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _FREQ_RE.search(line)
            if m:
                if rows:
                    mats.append(rows)
                rows = []
                freqs.append(float(m.group(1)))
                continue
            entries = _Z_RE.findall(line)
            if entries and freqs:
                rows.append(
                    [complex(float(re_z), float(im_z.replace(" ", "")))
                     for re_z, im_z in entries]
                )
    if rows:
        mats.append(rows)
    if not freqs or len(mats) != len(freqs):
        raise FastHenryParseError("no/incomplete impedance data in {0}".format(path))
    return freqs, mats
