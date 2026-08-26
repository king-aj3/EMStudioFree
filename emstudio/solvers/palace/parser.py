# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parsers for Palace output (``postpro/eig.csv``, ``port-S.csv``, ``farfield-rE.csv``).

The eigenvalue table columns (Palace, verified 2026-07-06)::

    m, Re{f} (GHz), Im{f} (GHz), Q, Error (Bkwd.), Error (Abs.)

``Re{f}`` is the resonant frequency in GHz; ``Im{f}`` and ``Q`` describe
the loss (infinite Q for a lossless PEC cavity). FreeCAD-free.
"""
from __future__ import annotations

import cmath
import csv
import math
import os
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


# --------------------------------------------------------------------------
# Far field
# --------------------------------------------------------------------------

#: Palace writes the far field here, inside the run's output directory.
FARFIELD_CSV = "farfield-rE.csv"


def parse_farfield(farfield_csv, freq_hz=None, excitation=None):
    """Read Palace's ``farfield-rE.csv`` into a :class:`FarFieldResult`.

    WHAT PALACE ACTUALLY GIVES YOU, AND WHY THIS IS NOT A ONE-LINER
    ---------------------------------------------------------------
    The file's columns are::

        f (GHz), exc, theta (deg.), phi (deg.),
        r*Re{E_x} (V), r*Im{E_x} (V), r*Re{E_y} (V), r*Im{E_y} (V),
        r*Re{E_z} (V), r*Im{E_z} (V)

    i.e. the COMPLEX vector ``r*E(theta, phi)``, not a gain. Palace's own docs
    say why: ``E`` itself vanishes as 1/r, so ``r*E`` is the finite, well-defined
    quantity, and it is "defined up to a global phase". The radiation intensity
    follows from its magnitude, ``U ∝ |r*E|^2``.

    ⚠⚠ **This returns DIRECTIVITY, not gain, and the difference is not
    pedantic.** Gain needs the power ACCEPTED at the port; directivity needs
    only the pattern, because it is the pattern normalised by its own average
    over the sphere::

        D(theta, phi) = 4*pi*U / (integral of U over the sphere)

    For a lossless radiator -- PEC in vacuum, which is what these models are --
    the two coincide, and for anything with real conductivity or dielectric loss
    they do not. ``FarFieldResult`` stores "gain in dBi" for every backend, so
    the number goes in that field, and ``meta["quantity"] = "directivity"``
    records what it actually is. Anything quoting it must say directivity.

    ⚠ **The samples are not a grid unless you asked for one.** ``NSample``
    scatters points uniformly over the sphere (a spiral), which is excellent for
    integration and useless for a (theta, phi) array. ``ThetaPhis`` adds
    explicit angles. This parser reassembles a regular grid when the angles
    present form one, and otherwise refuses rather than silently interpolating
    -- EMStudio's own decks request an explicit grid for exactly this reason
    (see ``build_farfield_config``).

    ⚠⚠ **A peak-of-samples directivity UNDER-READS, and by more than you would
    guess.** Measured on Palace's own regression data for a half-wave dipole
    (100 spiral points): the ANALYTIC pattern evaluated at those same 100 points
    reads **1.489 dBi** against its true **2.151 dBi** -- the sampling alone
    costs **0.66 dB**. Palace's data through this function reads **1.691 dBi**,
    which is **+0.20 dB** against the sampling-matched analytic figure and
    -0.46 dB against the textbook one. Comparing to the textbook number would
    have blamed the solver for the sample grid. Sample densely, and compare like
    with like.

    :param farfield_csv: path to ``farfield-rE.csv``.
    :param freq_hz: pick this frequency (Hz); default = the first in the file.
    :param excitation: pick this excitation index; default = the first.
    :returns: a :class:`emstudio.post.farfield.FarFieldResult`.
    """
    import numpy as np

    from emstudio.post.farfield import FarFieldResult

    if not os.path.isfile(farfield_csv):
        raise ValueError(
            "no Palace far-field output at {0} — the run needs "
            "Boundaries.Postprocessing.FarField, which only appears when the "
            "mesh has an absorbing (open) boundary".format(farfield_csv))
    raw = np.genfromtxt(farfield_csv, delimiter=",", skip_header=1)
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    if raw.size == 0 or raw.shape[1] < 10:
        raise ValueError(
            "{0} is not a Palace far-field table (expected 10 columns, got "
            "{1})".format(farfield_csv, raw.shape[1] if raw.ndim > 1 else 0))

    f_ghz, exc = raw[:, 0], raw[:, 1]
    if freq_hz is None:
        f_sel = f_ghz[0]
    else:
        f_sel = f_ghz[int(np.argmin(np.abs(f_ghz - float(freq_hz) / 1e9)))]
    if excitation is None:
        e_sel = exc[0]
    else:
        e_sel = float(excitation)
    m = np.isclose(f_ghz, f_sel) & np.isclose(exc, e_sel)
    if not m.any():
        raise ValueError(
            "no rows in {0} at f {1} GHz / excitation {2}".format(
                farfield_csv, f_sel, e_sel))

    th, ph = raw[m, 2], raw[m, 3]
    ex = raw[m, 4] + 1j * raw[m, 5]
    ey = raw[m, 6] + 1j * raw[m, 7]
    ez = raw[m, 8] + 1j * raw[m, 9]
    u = np.abs(ex) ** 2 + np.abs(ey) ** 2 + np.abs(ez) ** 2

    thetas = np.unique(np.round(th, 6))
    phis = np.unique(np.round(ph, 6))
    ti = np.searchsorted(thetas, np.round(th, 6))
    pi_ = np.searchsorted(phis, np.round(ph, 6))
    grid = np.full((thetas.size, phis.size), np.nan, dtype=float)
    grid[ti, pi_] = u

    # ⚠ THE POLES ARE DEDUPLICATED BY PALACE, and that is correct of it.
    # At theta = 0 and theta = 180 every phi names the SAME physical direction,
    # so asking for 19 thetas x 24 phis returns 410 rows, not 456
    # (456 - 2*23). Measured, not guessed. A parser that demanded
    # rows == Nt*Np would reject Palace's correct output as malformed -- which
    # is exactly what the first version of this function did. Broadcast the
    # single pole sample across its row instead.
    for i, t_deg in enumerate(thetas):
        if abs(np.sin(np.radians(t_deg))) < 1e-9:
            row = grid[i]
            known = row[~np.isnan(row)]
            if known.size:
                grid[i] = known[0]

    if np.isnan(grid).any():
        # Refuse rather than interpolate. A scattered spiral sample is a fine
        # thing to integrate and a bad thing to pretend is a grid, and silently
        # gridding it would put invented numbers into a container whose whole
        # job is to be trusted by the plots and the gates.
        missing = int(np.isnan(grid).sum())
        raise ValueError(
            "Palace far-field samples at f {0} GHz do not fill a regular "
            "(theta, phi) grid: {1} rows over {2} theta x {3} phi leaves {4} "
            "cells empty. This is an NSample spiral. Request explicit angles "
            "with ThetaPhis (the EMStudio writer does), or integrate the "
            "scattered samples with farfield_directivity_scattered()."
            .format(f_sel, th.size, thetas.size, phis.size, missing))

    # Directivity, from the pattern alone. The solid-angle weight is sin(theta)
    # -- omitting it is the classic error and it biases the answer toward the
    # poles, where a grid has its densest sampling and least energy.
    w = np.sin(np.radians(thetas))[:, None] * np.ones((1, phis.size))
    denom = float((grid * w).sum())
    if denom <= 0.0:
        raise ValueError(
            "Palace far field integrates to zero power — the structure "
            "radiated nothing, which usually means the boundary was PEC "
            "rather than absorbing")
    d_lin = grid / (denom / float(w.sum()))
    with np.errstate(divide="ignore"):
        d_dbi = 10.0 * np.log10(np.maximum(d_lin, 1e-30))

    return FarFieldResult(
        f_sel * 1e9, thetas, phis, d_dbi,
        meta={"backend": "palace",
              # ⚠ Read by anything that quotes this number. It is NOT gain.
              "quantity": "directivity",
              "source": os.path.basename(farfield_csv),
              "excitation": int(e_sel),
              "n_samples": int(th.size)})


def farfield_directivity_scattered(farfield_csv, freq_hz=None,
                                   excitation=None):
    """Peak directivity (dBi) from SCATTERED samples, without gridding them.

    The companion to :func:`parse_farfield` for the ``NSample`` spiral, which is
    uniform in solid angle and therefore integrates by a plain mean -- but is
    not a grid and cannot become a ``FarFieldResult``. Returns
    ``(peak_dbi, theta_deg, phi_deg, n)``.

    ⚠ This is a PEAK OF SAMPLES: it under-reads the true maximum whenever the
    real peak falls between samples, by 0.66 dB on Palace's own 100-point dipole
    reference. Quote it with its sample count, or grid it and quote that.

    ⚠⚠ **ONLY VALID FOR SOLID-ANGLE-UNIFORM SAMPLES (an ``NSample`` spiral).**
    The plain mean IS the sphere integral only when every sample carries the
    same solid angle. Hand it a lat/long GRID and it reads HIGH, because a grid
    crowds samples at the poles where there is little energy, shrinking the
    denominator: measured on the shipped 19x24 fixture it returns **+3.62 dBi**
    against the correctly sin(theta)-weighted **+2.47 dBi**, a **1.15 dB**
    overstatement on the same data. Use :func:`parse_farfield` for grids -- it
    weights by sin(theta). This trap is pinned by
    ``tests/validation/palace_farfield.py`` so that the two estimators can never
    be quietly swapped.
    """
    import numpy as np

    if not os.path.isfile(farfield_csv):
        raise ValueError("no Palace far-field output at {0}".format(
            farfield_csv))
    raw = np.genfromtxt(farfield_csv, delimiter=",", skip_header=1)
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    f_ghz, exc = raw[:, 0], raw[:, 1]
    f_sel = f_ghz[0] if freq_hz is None else f_ghz[
        int(np.argmin(np.abs(f_ghz - float(freq_hz) / 1e9)))]
    e_sel = exc[0] if excitation is None else float(excitation)
    m = np.isclose(f_ghz, f_sel) & np.isclose(exc, e_sel)
    th, ph = raw[m, 2], raw[m, 3]
    u = (np.abs(raw[m, 4] + 1j * raw[m, 5]) ** 2
         + np.abs(raw[m, 6] + 1j * raw[m, 7]) ** 2
         + np.abs(raw[m, 8] + 1j * raw[m, 9]) ** 2)
    if u.sum() <= 0:
        raise ValueError("Palace far field integrates to zero power")
    d = u.size * u / u.sum()
    i = int(np.argmax(d))
    return (10.0 * np.log10(d[i]), float(th[i]), float(ph[i]), int(u.size))
