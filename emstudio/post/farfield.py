# SPDX-License-Identifier: LGPL-2.1-or-later
"""Far-field radiation pattern results shared by every backend.

Whatever the solver (openEMS NF2FF, NEC2 RP cards, later Palace), patterns normalize to
one container: gain in dBi over a (theta, phi) grid at a single frequency. Cuts and
peak lookup feed the polar plots and the validation gates.

Conventions: theta is measured from +Z (zenith), phi from +X, both in degrees — the
standard spherical antenna convention used by both openEMS and NEC2.

Qt-free and FreeCAD-free: usable from solver decks and plain pytest.
"""

from __future__ import annotations

import numpy as np

# Gain floor used for pattern nulls (NEC2 prints -999.99 dB at exact nulls).
GAIN_FLOOR_DBI = -60.0


class FarFieldResult:
    """Gain pattern G(theta, phi) in dBi at one frequency."""

    def __init__(self, freq_hz, theta_deg, phi_deg, gain_dbi, meta=None):
        self.freq = float(freq_hz)
        self.theta = np.asarray(theta_deg, dtype=float)  # (Nt,)
        self.phi = np.asarray(phi_deg, dtype=float)      # (Np,)
        gain = np.asarray(gain_dbi, dtype=float)         # (Nt, Np)
        if gain.shape != (self.theta.size, self.phi.size):
            raise ValueError(
                "gain shape {0} != (theta {1}, phi {2})".format(
                    gain.shape, self.theta.size, self.phi.size
                )
            )
        self.gain = np.clip(gain, GAIN_FLOOR_DBI, None)
        self.meta = dict(meta or {})

    def peak(self):
        """(gain_dbi, theta_deg, phi_deg) of the pattern maximum."""
        i, j = np.unravel_index(int(np.argmax(self.gain)), self.gain.shape)
        return float(self.gain[i, j]), float(self.theta[i]), float(self.phi[j])

    def cut(self, phi_deg):
        """(theta, gain) cut at the phi column nearest to ``phi_deg``."""
        j = int(np.argmin(np.abs(self.phi - phi_deg)))
        return self.theta, self.gain[:, j]

    # -- persistence (long format CSV) ----------------------------------------
    CSV_HEADER = "freq_hz,theta_deg,phi_deg,gain_dbi"

    def save_csv(self, path):
        rows = []
        for i, th in enumerate(self.theta):
            for j, ph in enumerate(self.phi):
                rows.append((self.freq, th, ph, self.gain[i, j]))
        np.savetxt(path, np.asarray(rows), delimiter=",", header=self.CSV_HEADER, comments="")

    @classmethod
    def load_csv(cls, path, meta=None):
        data = np.atleast_2d(np.loadtxt(path, delimiter=",", skiprows=1))
        freq = data[0, 0]
        theta = np.unique(data[:, 1])
        phi = np.unique(data[:, 2])
        gain = np.full((theta.size, phi.size), GAIN_FLOOR_DBI)
        t_idx = {v: i for i, v in enumerate(theta)}
        p_idx = {v: i for i, v in enumerate(phi)}
        for f, th, ph, g in data:
            gain[t_idx[th], p_idx[ph]] = g
        return cls(freq, theta, phi, gain, meta=meta)
