# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace's far field becomes a pattern, checked against theory.

⭐ THIS IS THE HALF THAT WAS MISSING. ``palace_radiation.py`` already pinned that
EMStudio can HAND Palace an open domain -- the absorbing boundary and the
``Postprocessing.FarField`` block, gated at schema level against the installed
Palace's own ``config-schema.json``. But nothing read the answer back, so
"Palace can radiate" stopped one step short of a pattern anyone could see.
This gate closes it: Palace's ``farfield-rE.csv`` -> ``FarFieldResult`` ->
textbook dipole physics.

WHAT PALACE GIVES YOU, AND WHY IT IS NOT GAIN
----------------------------------------------
The file holds the COMPLEX vector ``r*E(theta, phi)`` -- Palace's docs say
``E`` itself vanishes as 1/r, so ``r*E`` is the finite quantity, "defined up to
a global phase". Radiation intensity is ``U ∝ |r*E|^2``.

⚠⚠ From the pattern alone you can compute **DIRECTIVITY**, not gain. Gain needs
the power ACCEPTED at the port; directivity is the pattern normalised by its own
average over the sphere. They coincide only for a lossless radiator -- PEC in
vacuum, which this model is. ``FarFieldResult`` stores dBi for every backend, so
the number lands in that field and ``meta["quantity"]`` says what it really is.
Anything quoting it must say directivity.

THE ANCHOR IS TEXTBOOK PHYSICS, NOT A STORED NUMBER
----------------------------------------------------
A half-wave dipole has a closed-form pattern and a directivity of **2.151 dBi**.
This gate checks Palace's answer against that, not against a golden file, so it
tests the physics rather than yesterday's bytes.

⚠⚠ **The finding that makes this gate honest: a peak of samples UNDER-READS,
and the naive comparison blames the solver.** Measured on Palace's own
regression data for this dipole (100 spiral points): the ANALYTIC pattern
evaluated at those same 100 points reads **1.489 dBi** against its true
**2.151** -- the sampling alone costs **0.66 dB**. Palace's data through our
parser reads **1.691 dBi**, i.e. **+0.20 dB** against the sampling-matched
figure but **-0.46 dB** against the textbook one. Comparing to 2.151 would have
recorded a solver error that was really a sample-grid artefact. So EMStudio
asks for an explicit GRID (``writer.farfield_grid``), and this gate uses one.

⛳ And on a grid, the BROADSIDE MEAN beats the peak as an estimator. A z-oriented
dipole is omnidirectional in phi, so every phi at theta = 90 is the same physical
answer; their spread is mesh asymmetry. The peak absorbs that spread and reads
high, the mean averages it out. Measured on the fixture: peak +2.47 dBi, mean
+2.22 dBi, against 2.151 analytic.

Pure python3 + numpy -- no Palace, no FreeCAD. The fixture is a REAL Palace run
(v0.17.0, 4 ranks) on Palace's own example geometry; see the data README.
Pass: exit 0 and 'PALACE FARFIELD GATE PASSED'.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                     "palace_farfield")
FIXTURE = os.path.join(_DATA, "halfwave_dipole_grid-rE.csv")

#: Directivity of an ideal half-wave dipole, from the closed form
#: D = 4*pi*U_max / integral(U dOmega) with U ∝ [cos(pi/2 cos t)/sin t]^2.
HALFWAVE_DIPOLE_DBI = 2.151


def _trapz(y, x):
    """Trapezoidal integral, independent of the numpy version.

    ⚠ ``np.trapz`` was REMOVED in numpy 2.0 (renamed ``np.trapezoid``), and
    ``np.trapezoid`` does not exist in numpy 1.x. This project runs on both:
    the dev box here is numpy 1.26, CI and the Windows VM are numpy 2.x. Using
    either name directly means the gate passes on one machine and dies with
    AttributeError on the other -- which is exactly what happened on
    2026-08-26, green locally and red on CI and Windows within the same commit.
    The rule is written out rather than shimmed to a name because three lines of
    trapezoid beats a compatibility branch nobody re-reads.
    """
    import numpy as np

    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    return float(np.sum((y[1:] + y[:-1]) * 0.5 * np.diff(x)))


FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    import numpy as np

    from emstudio.post.farfield import FarFieldResult
    from emstudio.solvers.palace import parser, writer

    check("the fixture exists (a real Palace v0.17.0 run — see the data README)",
          os.path.isfile(FIXTURE), FIXTURE)
    if not os.path.isfile(FIXTURE):
        print("PALACE FARFIELD GATE FAILED")
        return 1

    ff = parser.parse_farfield(FIXTURE)
    check("Palace far field parses into the SHARED FarFieldResult container",
          isinstance(ff, FarFieldResult),
          "{0} theta x {1} phi at {2:.4f} GHz".format(
              ff.theta.size, ff.phi.size, ff.freq / 1e9))

    # ⚠ The container's field is called "gain" for every backend; this one is
    # directivity. If that label is ever lost, a number gets quoted as gain that
    # is not gain, so the label is gated rather than trusted.
    check("the result LABELS itself directivity, not gain",
          ff.meta.get("quantity") == "directivity"
          and ff.meta.get("backend") == "palace",
          str({k: ff.meta.get(k) for k in ("backend", "quantity")}))

    # Pole deduplication: 456 requested angles, 410 rows, and a FULL grid.
    check("Palace's pole deduplication is handled (410 rows fill a 19x24 grid)",
          ff.meta.get("n_samples") == 410 and ff.theta.size == 19
          and ff.phi.size == 24,
          "{0} rows -> {1}x{2}".format(ff.meta.get("n_samples"),
                                       ff.theta.size, ff.phi.size))
    check("no cell of the reassembled grid is empty",
          np.isfinite(ff.gain).all())

    g_peak, th_peak, _ph = ff.peak()

    # --- the physics ------------------------------------------------------
    check("the pattern peaks at BROADSIDE (theta = 90 deg) for a z-dipole",
          abs(th_peak - 90.0) < 1e-6, "theta = {0:.1f} deg".format(th_peak))

    i90 = int(np.argmin(np.abs(ff.theta - 90.0)))
    broadside = ff.gain[i90]
    mean_bs = float(broadside.mean())
    check("broadside directivity matches the closed form within 0.5 dB "
          "(mean over phi, which is the better estimator — see the docstring)",
          abs(mean_bs - HALFWAVE_DIPOLE_DBI) < 0.5,
          "{0:+.3f} dBi vs {1:+.3f} analytic ({2:+.3f} dB)".format(
              mean_bs, HALFWAVE_DIPOLE_DBI, mean_bs - HALFWAVE_DIPOLE_DBI))
    check("the PEAK is within 1 dB too, and reads HIGH of the mean because it "
          "absorbs the phi ripple rather than averaging it",
          abs(g_peak - HALFWAVE_DIPOLE_DBI) < 1.0 and g_peak >= mean_bs,
          "peak {0:+.3f} vs mean {1:+.3f} dBi".format(g_peak, mean_bs))

    # A z-oriented dipole is omnidirectional in phi. Any spread is the mesh,
    # not the antenna, so this is a mesh-quality check with a physical meaning.
    ripple = float(broadside.max() - broadside.min())
    check("the broadside cut is omnidirectional in phi to under 1 dB "
          "(the spread IS the mesh asymmetry, not the antenna)",
          ripple < 1.0, "{0:.4f} dB peak-to-peak".format(ripple))

    # The axial null. A dipole radiates nothing along its own axis; a solver
    # that gets this wrong has not represented the current distribution.
    i0 = int(np.argmin(np.abs(ff.theta - 0.0)))
    null = float(ff.gain[i0].mean())
    check("there is a deep null on the dipole AXIS (theta = 0)",
          null < mean_bs - 20.0,
          "{0:+.2f} dBi, {1:.1f} dB below broadside".format(
              null, mean_bs - null))

    # --- the sampling finding, pinned so it cannot be re-learned the hard way
    thetas = np.radians(ff.theta)

    def u_analytic(t):
        s = np.sin(t)
        out = np.zeros_like(t)
        m = s > 1e-12
        out[m] = (np.cos(np.pi / 2.0 * np.cos(t[m])) / s[m]) ** 2
        return out

    t_dense = np.linspace(1e-9, np.pi - 1e-9, 200001)
    u_dense = u_analytic(t_dense)
    d_true = 10.0 * np.log10(
        4.0 * np.pi * u_dense.max()
        / (_trapz(u_dense * np.sin(t_dense), t_dense) * 2.0 * np.pi))
    check("the closed form really is 2.151 dBi (computed here, not quoted)",
          abs(d_true - HALFWAVE_DIPOLE_DBI) < 0.005,
          "{0:+.4f} dBi".format(d_true))

    # --- the writer asks for a grid, and that is the reason ---------------
    grid = writer.farfield_grid()
    n_theta = len({t for t, _p in grid})
    n_phi = len({p for _t, p in grid})
    check("the writer requests an explicit (theta, phi) GRID, not an NSample "
          "spiral — a spiral cannot become a pattern array",
          n_theta == 19 and n_phi == 24 and len(grid) == 456,
          "{0} pairs = {1} theta x {2} phi".format(len(grid), n_theta, n_phi))
    bnd = writer.radiation_boundaries(4, nsample=0, theta_phis=grid)
    ffc = bnd["Postprocessing"]["FarField"]
    check("the emitted config carries those angles and matches the absorbing "
          "attribute (Palace requires the same surface for both)",
          ffc["Attributes"] == bnd["Absorbing"]["Attributes"]
          and len(ffc["ThetaPhis"]) == 456)

    # --- the two estimators are NOT interchangeable, and this pins it -----
    # ⚠⚠ Written the other way round first: the author asserted the scattered
    # estimator would AGREE with the gridded one, and it does not. The plain
    # mean is the sphere integral only when every sample carries equal solid
    # angle -- true of an NSample spiral, false of a lat/long grid, which
    # crowds the poles where there is least energy. Feeding grid data to the
    # spiral estimator shrinks the denominator and overstates directivity. The
    # mistake is kept here as a GUARD so the two can never be quietly swapped.
    d_sc, th_sc, _p_sc, n_sc = parser.farfield_directivity_scattered(FIXTURE)
    check("both estimators still find broadside", abs(th_sc - 90.0) < 1e-6,
          "theta {0:.1f} from {1} samples".format(th_sc, n_sc))
    check("the SPIRAL estimator overstates by ~1.15 dB on GRID data — it "
          "assumes equal solid angle per sample and a grid does not provide "
          "it; use parse_farfield (sin-theta weighted) for grids",
          0.8 < (d_sc - g_peak) < 1.5,
          "scattered {0:+.3f} vs gridded {1:+.3f} dBi = {2:+.3f} dB".format(
              d_sc, g_peak, d_sc - g_peak))

    if FAILURES:
        print("PALACE FARFIELD GATE FAILED ({0})".format(len(FAILURES)))
        return 1
    print("PALACE FARFIELD GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
