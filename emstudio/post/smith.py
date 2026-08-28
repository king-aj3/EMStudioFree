# SPDX-License-Identifier: LGPL-2.1-or-later
"""Smith-chart geometry and read-outs — the impedance plane on the unit disc.

Qt-free and numpy-only by the house rule, so the whole thing is gated headlessly
(``tests/validation/smith.py``) and the drawing code in ``ui/results_dialog.py``
is left with nothing to decide but colours.

WHY THIS IS HAND-ROLLED AND NOT A DEPENDENCY
--------------------------------------------
Three maintained packages draw Smith charts (``pysmithchart``, ``scikit-rf``,
``mpl-smithchart``) and **none of them is present in FreeCAD's bundled Python**,
so any of them becomes an install-time dependency for every user, on three
platforms whose FreeCAD bundles differ — the exact risk ``requirements.txt``
already argues about for scipy. scikit-rf additionally pulls **pandas** in, to
draw a chart. Against that cost, the mathematics below is a Möbius transform and
two circle formulas, all exact, and the engine is worth more gated than
delegated: you cannot mutation-test somebody else's matplotlib projection.
(Checked 2026-08-27. ``docs/PLAN.md`` named scikit-rf for "S-params/Smith" at
the very start of this project and it was never adopted; this records why.)

THE MAP
-------
Normalise by the port's reference impedance, then send the right half-plane to
the unit disc::

    z = Z / Z0
    Γ = (z − 1) / (z + 1)          and back:   Z = Z0 (1 + Γ) / (1 − Γ)

That map is conformal, and it is why the chart works on paper: the straight
constant-R and constant-X lines of the impedance plane become CIRCLES.

    constant R:   centre ( r/(1+r), 0 )     radius 1/(1+r)
    constant X:   centre ( 1, 1/x )         radius |1/x|

⚠ Γ IS ALREADY IN THE RESULT. ``SweepResult.s11`` is exactly this Γ — the class
computes ``(zin − z0)/(zin + z0)`` when a runner does not supply it. Nothing
here re-derives what the solver already returned; ``gamma_from_z`` exists for
callers holding a bare impedance (the matching designer's typed load, a cable
model), not to second-guess a solve.

⚠⚠ THE CHART IS NORMALISED, SO A CHART WITHOUT ITS Z0 IS HALF A NUMBER. The
centre means "matched to THIS port", not "50 Ω". Every read-out below carries
``z0`` for that reason, and the dialog prints it on the axes.
"""
from __future__ import annotations

import numpy as np

#: Radii a VSWR ring is worth drawing at. |Γ| = (S−1)/(S+1), so these sit at
#: 0.333, 0.2 and 0.0909 — the rings an RF engineer actually looks for.
DEFAULT_VSWR_RINGS = (2.0, 1.5, 1.2)

#: Normalised resistances/reactances the grid is drawn at. The classic chart's
#: printed set; dense enough to read, sparse enough not to smear at screen size.
DEFAULT_R_GRID = (0.0, 0.2, 0.5, 1.0, 2.0, 5.0)
DEFAULT_X_GRID = (0.2, 0.5, 1.0, 2.0, 5.0)


def gamma_from_z(z_ohm, z0=50.0):
    """Reflection coefficient Γ for impedance(s) ``z_ohm`` against ``z0``.

    ⚠ An OPEN circuit is Z = ∞, which no float carries. Callers wanting the
    open should pass a large real impedance and read Γ → +1; this function does
    not special-case it, because silently mapping an overflow to +1 would hide
    a caller that had computed a nonsense impedance.
    """
    z = np.asarray(z_ohm, dtype=complex) / float(z0)
    return (z - 1.0) / (z + 1.0)


def z_from_gamma(gamma, z0=50.0):
    """Impedance for reflection coefficient(s) — the inverse map.

    ⚠ Γ = +1 (a perfect open) sends this to infinity, and numpy will warn and
    return inf rather than raise. That is the honest answer, not an error.
    """
    g = np.asarray(gamma, dtype=complex)
    return float(z0) * (1.0 + g) / (1.0 - g)


def r_circle(r):
    """Constant-resistance circle for normalised ``r``: ``((cx, cy), radius)``.

    r = 0 gives the unit circle (all reactance, no loss); r → ∞ collapses onto
    the chart centre, which is the matched point.
    """
    r = float(r)
    if r < 0.0:
        raise ValueError("normalised resistance cannot be negative (got %r) — "
                         "a negative-R point is outside the chart and usually "
                         "means an active or mis-de-embedded device" % r)
    return (r / (1.0 + r), 0.0), 1.0 / (1.0 + r)


def x_circle(x):
    """Constant-reactance arc for normalised ``x``: ``((cx, cy), radius)``.

    Positive x is inductive and arcs across the TOP half; negative x is
    capacitive and arcs across the bottom. x = 0 is the real axis, a straight
    line rather than a circle, which is why it is not in ``DEFAULT_X_GRID``.
    """
    x = float(x)
    if x == 0.0:
        raise ValueError("x = 0 is the real axis, a LINE not a circle — draw "
                         "it directly rather than asking for its centre")
    return (1.0, 1.0 / x), abs(1.0 / x)


def vswr_from_gamma(gamma):
    """VSWR from |Γ|. Clipped just under 1 so a total reflection is a big
    number rather than a divide-by-zero — the same clip ``SweepResult.vswr``
    uses, deliberately, so the chart and the VSWR tab cannot disagree."""
    m = np.clip(np.abs(np.asarray(gamma, dtype=complex)), 0.0, 0.999999)
    return (1.0 + m) / (1.0 - m)


def gamma_radius_for_vswr(vswr):
    """|Γ| of a VSWR ring: the inverse of :func:`vswr_from_gamma`."""
    s = float(vswr)
    if s < 1.0:
        raise ValueError("VSWR is >= 1 by definition (got %r)" % s)
    return (s - 1.0) / (s + 1.0)


def return_loss_db(gamma):
    """Return loss in dB, POSITIVE by convention (20·log10(1/|Γ|)).

    ⚠ The S11 tab plots 20·log10|Γ|, which is the same number NEGATED. Both
    conventions are in common use and mixing them silently is a classic
    off-by-a-sign; the dialog labels this one "return loss" and that one "S11".
    """
    m = np.abs(np.asarray(gamma, dtype=complex))
    m = np.where(m <= 0, 1e-30, m)
    return -20.0 * np.log10(m)


def readout(zin, z0=50.0):
    """Everything the chart says at one point, as a dict.

    Kept as a pure function so ``gui_smoke`` can assert the numbers a user
    reads without opening a dialog, and so the PDF report and the tab cannot
    print different values for the same solve.
    """
    z = complex(zin)
    g = complex(gamma_from_z(z, z0))
    return {
        "z0_ohm": float(z0),
        "z_ohm": z,
        "z_norm": z / float(z0),
        "gamma": g,
        "gamma_mag": abs(g),
        "gamma_deg": float(np.degrees(np.angle(g))),
        "vswr": float(vswr_from_gamma(g)),
        "return_loss_db": float(return_loss_db(g)),
        # What a reader wants next: which way is the match, and is the load
        # inductive or capacitive? Both are one-liners off the same numbers and
        # both are what the chart is actually FOR.
        "reactance": ("inductive" if z.imag > 0 else
                      "capacitive" if z.imag < 0 else "resonant"),
        "half": ("upper" if g.imag > 0 else
                 "lower" if g.imag < 0 else "real axis"),
    }
