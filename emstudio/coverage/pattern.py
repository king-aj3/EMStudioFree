# SPDX-License-Identifier: LGPL-2.1-or-later
"""Antenna azimuth pattern for coverage modulation (ROADMAP §6, phase B).

A coverage heatmap is the transmitter's radiated field over the ground, so the
horizontal (azimuth) cut of the antenna pattern modulates it: a directional
antenna paints a lobe, an omni a disc. This turns a full ``FarFieldResult``
gain(theta, phi) into an azimuth cut ``gain(bearing)`` the heatmap can sample.

* ``omni(peak_dbi)`` — a flat azimuth pattern (verticals/monopoles are omni in
  azimuth; the default).
* ``AzimuthPattern.from_farfield(ff, elevation_deg, orientation_deg)`` — the gain
  row at the wanted take-off elevation from a NEC2/openEMS solve, so a real,
  validated pattern drives the map.

Bearing is compass degrees (0 = North, clockwise). ``orientation_deg`` is the
compass bearing the antenna's pattern phi=0 axis points to (how the antenna is
aimed on the ground). Pure-python + numpy, Qt-free, FreeCAD-free.
"""
from __future__ import annotations

import numpy as np


class AzimuthPattern:
    """Absolute gain (dBi) vs azimuth, with a compass orientation.

    ``phi_deg`` (ascending, 0..360) and ``gain_dbi`` are the antenna's own
    horizontal cut; ``orientation_deg`` rotates phi=0 to a compass bearing.
    """

    def __init__(self, phi_deg, gain_dbi, orientation_deg=0.0):
        phi = np.asarray(phi_deg, dtype=float)
        gain = np.asarray(gain_dbi, dtype=float)
        order = np.argsort(phi)
        self.phi = phi[order]
        self.gain = gain[order]
        self.orientation_deg = float(orientation_deg)

    def peak_dbi(self):
        return float(np.max(self.gain))

    def gain_at(self, bearing_deg):
        """Interpolated gain (dBi) toward compass ``bearing_deg`` (0 = North, CW)."""
        rel = (float(bearing_deg) - self.orientation_deg) % 360.0
        # periodic linear interpolation over the (possibly partial) phi samples
        phi = self.phi
        if phi.size == 1:
            return float(self.gain[0])
        # extend the table by one wrapped point so np.interp covers [0,360)
        xp = np.concatenate([phi, [phi[0] + 360.0]])
        fp = np.concatenate([self.gain, [self.gain[0]]])
        return float(np.interp(rel, xp, fp))

    @classmethod
    def from_farfield(cls, ff, elevation_deg=0.0, orientation_deg=0.0):
        """Azimuth cut at a take-off ``elevation_deg`` above the horizon.

        ``ff`` is a :class:`emstudio.post.farfield.FarFieldResult` (gain over
        theta from zenith, phi from +X). theta = 90 - elevation. If the pattern
        only sampled the upper hemisphere the nearest available theta row is used.
        """
        theta_target = 90.0 - float(elevation_deg)
        j = int(np.argmin(np.abs(ff.theta - theta_target)))
        return cls(ff.phi, ff.gain[j, :], orientation_deg=orientation_deg)


def omni(peak_dbi=0.0):
    """A flat (omnidirectional-in-azimuth) pattern at ``peak_dbi``."""
    return AzimuthPattern([0.0, 180.0], [peak_dbi, peak_dbi])
