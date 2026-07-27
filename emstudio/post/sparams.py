# SPDX-License-Identifier: LGPL-2.1-or-later
"""One-port sweep results shared by every backend.

Whatever the solver (openEMS FDTD, NEC2 MoM, later Elmer/Palace), Phase-1 results
normalize to the same container: frequency vector + complex input impedance + complex
S11 against a reference impedance. Everything downstream (plots, Touchstone export,
resonance search, validation gates) works off this one type, so backends stay thin.

Qt-free and FreeCAD-free on purpose: usable from plain pytest and from solver decks.
"""

from __future__ import annotations

import numpy as np


class SweepResult:
    """One-port frequency sweep: Zin(f) and S11(f) vs a reference impedance."""

    def __init__(self, freq_hz, zin, z0=50.0, s11=None, meta=None):
        self.freq = np.asarray(freq_hz, dtype=float)
        self.zin = np.asarray(zin, dtype=complex)
        self.z0 = float(z0)
        if s11 is None:
            s11 = (self.zin - self.z0) / (self.zin + self.z0)
        self.s11 = np.asarray(s11, dtype=complex)
        self.meta = dict(meta or {})  # backend name, solve time, etc.

    # -- derived quantities ---------------------------------------------------
    def s11_db(self):
        mag = np.abs(self.s11)
        mag = np.where(mag <= 0, 1e-30, mag)
        return 20.0 * np.log10(mag)

    def vswr(self):
        mag = np.clip(np.abs(self.s11), 0.0, 0.999999)
        return (1.0 + mag) / (1.0 - mag)

    def min_s11(self):
        """(frequency, S11_dB) at the best match point."""
        db = self.s11_db()
        i = int(np.argmin(db))
        return float(self.freq[i]), float(db[i])

    def resonances(self):
        """Frequencies where the reactance Im(Zin) crosses zero (interpolated)."""
        x = np.imag(self.zin)
        crossings = []
        for i in range(len(x) - 1):
            if x[i] == 0.0:
                crossings.append(float(self.freq[i]))
            elif x[i] * x[i + 1] < 0.0:
                # linear interpolation between the two samples
                f = self.freq[i] + (self.freq[i + 1] - self.freq[i]) * (
                    -x[i] / (x[i + 1] - x[i])
                )
                crossings.append(float(f))
        return crossings

    def r_at(self, freq_hz):
        """Interpolated input resistance at a frequency."""
        return float(np.interp(freq_hz, self.freq, np.real(self.zin)))

    def x_at(self, freq_hz):
        """Interpolated input reactance at a frequency."""
        return float(np.interp(freq_hz, self.freq, np.imag(self.zin)))

    # -- persistence ------------------------------------------------------------
    CSV_HEADER = "freq_hz,re_zin,im_zin,re_s11,im_s11,z0"

    def save_csv(self, path):
        rows = np.column_stack(
            [
                self.freq,
                np.real(self.zin),
                np.imag(self.zin),
                np.real(self.s11),
                np.imag(self.s11),
                np.full_like(self.freq, self.z0),
            ]
        )
        np.savetxt(path, rows, delimiter=",", header=self.CSV_HEADER, comments="")

    @classmethod
    def load_csv(cls, path, meta=None):
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        data = np.atleast_2d(data)
        freq = data[:, 0]
        zin = data[:, 1] + 1j * data[:, 2]
        s11 = data[:, 3] + 1j * data[:, 4]
        z0 = float(data[0, 5])
        return cls(freq, zin, z0=z0, s11=s11, meta=meta)

    def write_touchstone(self, path):
        """Write a 1-port Touchstone (.s1p) file, RI format, Hz."""
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("! EMStudio one-port sweep ({0})\n".format(self.meta.get("backend", "?")))
            fh.write("# Hz S RI R {0:g}\n".format(self.z0))
            for f, s in zip(self.freq, self.s11):
                fh.write("{0:.9e} {1:.9e} {2:.9e}\n".format(f, s.real, s.imag))
