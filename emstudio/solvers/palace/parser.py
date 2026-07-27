# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parser for Palace eigenmode output (``postpro/eig.csv``).

The eigenvalue table columns (Palace, verified 2026-07-06)::

    m, Re{f} (GHz), Im{f} (GHz), Q, Error (Bkwd.), Error (Abs.)

``Re{f}`` is the resonant frequency in GHz; ``Im{f}`` and ``Q`` describe
the loss (infinite Q for a lossless PEC cavity). FreeCAD-free.
"""
from __future__ import annotations

import cmath
import csv
import math
import re


class PalaceParseError(RuntimeError):
    pass


def parse_eigenvalues(eig_csv_path):
    """Read ``eig.csv``. Returns a list of dicts sorted by frequency:

    ``{"index": int, "freq_ghz": float, "imag_ghz": float, "q": float}``.
    """
    rows = []
    with open(eig_csv_path, "r", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        header = None
        for raw in reader:
            cells = [c.strip() for c in raw if c.strip() != ""]
            if not cells:
                continue
            if header is None:
                header = cells
                continue
            try:
                vals = [float(c) for c in cells]
            except ValueError:
                continue
            if len(vals) < 2:
                continue
            rows.append({
                "index": int(vals[0]),
                "freq_ghz": vals[1],
                "imag_ghz": vals[2] if len(vals) > 2 else 0.0,
                "q": vals[3] if len(vals) > 3 else float("inf"),
            })
    if not rows:
        raise PalaceParseError("no eigenvalues parsed from {0}".format(eig_csv_path))
    rows.sort(key=lambda r: r["freq_ghz"])
    return rows


def parse_sparams(port_s_csv):
    """Read Palace's ``port-S.csv`` (driven S-parameters). Returns a dict:

    ``{"freq_hz": [...], "s": {(o, x): [complex, ...]}}`` where (o, x) is the
    (observed, excitation) port pair. Palace writes magnitude in dB and angle
    in degrees; columns are named ``|S[o][x]| (dB)`` and ``arg(S[o][x]) (deg.)``.
    """
    with open(port_s_csv, "r", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        rows = [[c.strip() for c in r] for r in reader if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise PalaceParseError("no S-parameter rows in {0}".format(port_s_csv))
    header = rows[0]
    freq_col = None
    mag_cols = {}  # (o, x) -> column index
    ang_cols = {}
    for i, h in enumerate(header):
        if h.lower().startswith("f "):
            freq_col = i
            continue
        m = re.search(r"\|S\[(\d+)\]\[(\d+)\]\|", h)
        if m:
            mag_cols[(int(m.group(1)), int(m.group(2)))] = i
            continue
        m = re.search(r"arg\(S\[(\d+)\]\[(\d+)\]\)", h)
        if m:
            ang_cols[(int(m.group(1)), int(m.group(2)))] = i
    if freq_col is None or not mag_cols:
        raise PalaceParseError(
            "unrecognized port-S.csv header: {0}".format(header))

    freqs = []
    s = {pair: [] for pair in mag_cols}
    for row in rows[1:]:
        try:
            freqs.append(float(row[freq_col]) * 1e9)  # GHz -> Hz
        except (ValueError, IndexError):
            continue
        for pair, mi in mag_cols.items():
            mag = 10.0 ** (float(row[mi]) / 20.0)  # dB -> linear
            ang = math.radians(float(row[ang_cols[pair]])) if pair in ang_cols else 0.0
            s[pair].append(cmath.rect(mag, ang))
    if not freqs:
        raise PalaceParseError("no numeric rows in {0}".format(port_s_csv))
    return {"freq_hz": freqs, "s": s}
