# SPDX-License-Identifier: LGPL-2.1-or-later
"""Frequency-validity guard for the QUASI-STATIC solvers (Elmer magnetics,
FastHenry R/L extraction).

These solvers approximate Maxwell's equations by DROPPING the displacement
current (magneto-quasistatic / PEEC). That approximation is trustworthy only
while the modelled structure is ELECTRICALLY SMALL — its largest dimension a
small fraction of a wavelength. Beyond that the near fields radiate and the
quasi-static result becomes non-physical; a full-wave analysis (Palace / openEMS)
is required instead. See docs/CAPABILITIES.md "Frequency range & validity".

This module produces a human-readable warning when an analysis is set up outside
the quasi-static regime. It **never blocks the run** — it only warns, so an
informed user can still proceed. GUI-safe: no Qt/FreeCAD import at module load.
"""
from __future__ import annotations

C0 = 299792458.0

# Quasi-static is trustworthy while the largest dimension L < LAMBDA_FRACTION * λ.
# λ/10 is the conventional "electrically small" boundary.
LAMBDA_FRACTION = 0.1


def electrical_size_warning(freq_hz, max_dim_m,
                            method="magneto-quasistatic (Elmer)"):
    """Warn if the structure is not electrically small at ``freq_hz``.

    Returns a warning string, or ``None`` when the analysis is safely inside the
    quasi-static regime (or the inputs are unknown/degenerate).

    :param freq_hz: highest operating frequency of the analysis (Hz).
    :param max_dim_m: largest structure dimension (m).
    """
    if not freq_hz or freq_hz <= 0 or not max_dim_m or max_dim_m <= 0:
        return None
    wavelength = C0 / float(freq_hz)
    ratio = float(max_dim_m) / wavelength            # size in wavelengths
    if ratio < LAMBDA_FRACTION:
        return None
    f_max_ok = LAMBDA_FRACTION * C0 / float(max_dim_m)  # highest valid f for this size
    return (
        "Frequency out of the quasi-static range: at {0:.4g} GHz the largest "
        "dimension ({1:.4g} mm) is {2:.2f} wavelengths (>= lambda/10). The {3} "
        "solver drops the displacement current and is only trustworthy while the "
        "structure is electrically small (below ~{4:.4g} GHz for this geometry). "
        "Above that, use a full-wave analysis (Palace or openEMS) — the results "
        "shown may be non-physical.".format(
            float(freq_hz) / 1e9, float(max_dim_m) * 1e3, ratio, method,
            f_max_ok / 1e9))


def axi_model_max_dim_m(model):
    """Largest physical dimension (m) of an axisymmetric Elmer model.

    Bodies are (r0, r1, z0, z1) in mm; the revolved solid spans a diameter of
    2*max(r1) and an axial height of max(z1)-min(z0). Returns 0.0 if unknown.
    """
    bodies = (model or {}).get("bodies") or []
    r1s = [b.get("r1", 0.0) for b in bodies if isinstance(b, dict)]
    z0s = [b.get("z0", 0.0) for b in bodies if isinstance(b, dict)]
    z1s = [b.get("z1", 0.0) for b in bodies if isinstance(b, dict)]
    if not r1s:
        return 0.0
    diameter_mm = 2.0 * max(r1s)
    height_mm = (max(z1s) - min(z0s)) if z1s and z0s else 0.0
    return max(diameter_mm, height_mm) * 1e-3


def emit(warning, line_callback=None):
    """Surface a warning (if any) to the FreeCAD report view + the solver log.

    Returns ``warning`` unchanged so callers can also stash it in result meta.
    """
    if not warning:
        return warning
    try:
        import FreeCAD

        FreeCAD.Console.PrintWarning(warning + "\n")
    except Exception:
        pass
    if line_callback:
        try:
            line_callback("WARNING: " + warning)
        except Exception:
            pass
    return warning
