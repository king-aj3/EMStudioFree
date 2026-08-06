# SPDX-License-Identifier: LGPL-2.1-or-later
"""Which frequencies get a radiation pattern, and how many.

Qt-free and FreeCAD-free on purpose: the runner, the Pattern Frequencies
dialog and the validation gate all need this arithmetic, and only one of the
three can import FreeCAD.

The band comes from the solver (``PatternFreqStart`` / ``PatternFreqStop``,
0 = follow the analysis sweep). The COUNT is what the user picks; the step is
derived, because NEC2's ``FR`` card takes a count and a step and the count is
the thing that costs output.
"""

from __future__ import annotations

#: Measured 2026-08-06: a full-sphere ``RP 0,37,72,...`` pattern block is about
#: 0.33 MB of nec2++ output (201 frequencies produced 65.4 MB). Solve time is
#: NOT the constraint — 201 patterns came from ONE run in 7.18 s — so this is
#: the only number worth showing the user before they commit to a count.
MB_PER_PATTERN = 0.33

#: Default number of patterns to suggest. Enough to watch a pattern evolve
#: across a band without the output becoming the reason not to use the feature
#: (11 x 0.33 MB = 3.6 MB).
DEFAULT_TARGET_PATTERNS = 11

#: Refuse to recommend more than this. Not a hard limit on what the user may
#: type — it is their disk — just a limit on what this module suggests.
MAX_RECOMMENDED = 101


def to_hz(value):
    """Hz as a float, from a FreeCAD Quantity, a number, or None."""
    if value is None:
        return 0.0
    try:
        return float(value.getValueAs("Hz"))
    except AttributeError:
        return float(value)


def resolve_band(solver, sweep_f1_hz, sweep_f2_hz):
    """(f1, f2) for the pattern pass, honouring the solver's band override.

    Falls back to the sweep whenever the override is absent, zero, or does not
    describe a real ascending band. Two numbers typed into a property editor
    are half-finished most of the time they are read; that must not break a
    solve, and silently using the sweep is the behaviour the user had before
    the properties existed.
    """
    f1 = to_hz(getattr(solver, "PatternFreqStart", 0.0))
    f2 = to_hz(getattr(solver, "PatternFreqStop", 0.0))
    if f1 <= 0.0 or f2 <= 0.0 or f2 <= f1:
        return float(sweep_f1_hz), float(sweep_f2_hz)
    return f1, f2


def step_hz(f1_hz, f2_hz, count):
    """The FR-card step for ``count`` patterns spanning f1..f2 inclusive."""
    if count is None or int(count) < 2:
        return 0.0
    return (float(f2_hz) - float(f1_hz)) / (int(count) - 1)


def count_for_step(f1_hz, f2_hz, step, minimum=2):
    """How many patterns a given step yields across f1..f2.

    Inclusive of both ends when the step divides the span; otherwise the last
    pattern lands short of f2 rather than past it — NEC2 will happily run an FR
    card off the end of the band the user asked for, and that is not what
    "stop at" means.
    """
    span = float(f2_hz) - float(f1_hz)
    if span <= 0.0 or float(step) <= 0.0:
        return minimum
    return max(minimum, int(span / float(step) + 1e-9) + 1)


def sweep_step_hz(f1_hz, f2_hz, points):
    """The analysis sweep's own spacing, in Hz. 0 if it has none."""
    n = int(points) - 1
    if n < 1:
        return 0.0
    return (float(f2_hz) - float(f1_hz)) / n


def recommend(f1_hz, f2_hz, sweep_step, target=DEFAULT_TARGET_PATTERNS):
    """Recommend a pattern count/step across ``f1..f2``.

    The recommendation prefers a step that is an INTEGER MULTIPLE of the
    analysis sweep step, so every pattern frequency coincides with a frequency
    the S11 / VSWR / impedance curves were actually sampled at. Without that
    the picker shows a pattern at, say, 63.4 MHz while every other tab's
    nearest datum is 62.2 — a mismatch the user has no way to see and every
    reason to be misled by.

    ``sweep_step`` is the SWEEP's spacing (:func:`sweep_step_hz`), not the
    band's. Those differ the moment the user narrows the pattern band to part
    of the sweep, and deriving the grid from the band instead — as this did at
    first — quietly loses the very alignment the function exists for.

    Falls back to a plain even division when the band does not sit on the sweep
    grid at all. Returns: count, step_hz, stride, on_sweep_points, mb, note.
    """
    f1 = float(f1_hz)
    f2 = float(f2_hz)
    span = f2 - f1
    target = max(2, int(target))
    if span <= 0.0:
        return {"count": 1, "step_hz": 0.0, "stride": 0, "mb": MB_PER_PATTERN,
                "on_sweep_points": False,
                "note": "the band has no width — one pattern is all it can hold"}

    step = float(sweep_step or 0.0)
    intervals = int(round(span / step)) if step > 0.0 else 0
    # Only trust the grid if the band really is a whole number of sweep steps
    # wide; otherwise "every Nth sweep point" would be a claim, not a fact.
    aligned = intervals >= 1 and abs(intervals * step - span) <= 1e-6 * span
    if aligned:
        # Every divisor of `intervals` gives a stride whose last pattern lands
        # exactly on f2. Pick the one closest to the requested target; ties go
        # to the SMALLER count, because the cost is per pattern.
        divisors = [d for d in range(1, intervals + 1) if intervals % d == 0]
        counts = [(intervals // d) + 1 for d in divisors]
        usable = [(c, d) for c, d in zip(counts, divisors)
                  if 2 <= c <= MAX_RECOMMENDED]
        if usable:
            count, stride = min(usable, key=lambda cd: (abs(cd[0] - target), cd[0]))
            return {
                "count": count,
                "step_hz": step * stride,
                "stride": stride,
                "on_sweep_points": True,
                "mb": count * MB_PER_PATTERN,
                "note": ("every {0}th sweep point — pattern frequencies line up "
                         "with the S11 samples".format(stride) if stride > 1
                         else "one pattern at every sweep point"),
            }

    count = max(2, min(target, MAX_RECOMMENDED))
    return {"count": count, "step_hz": span / (count - 1), "stride": 0,
            "on_sweep_points": False, "mb": count * MB_PER_PATTERN,
            "note": "evenly spaced across the band"}


def describe(f1_hz, f2_hz, count):
    """One human-readable line for a chosen count — used by the dialog."""
    n = int(count)
    if n < 2:
        return ("One pattern, at the best-match frequency "
                "(~{0:.1f} MB).".format(MB_PER_PATTERN))
    st = step_hz(f1_hz, f2_hz, n)
    return ("{0} patterns, {1:.4g} MHz apart, {2:.4g} - {3:.4g} MHz "
            "(~{4:.1f} MB of solver output, one extra run).".format(
                n, st / 1e6, f1_hz / 1e6, f2_hz / 1e6, n * MB_PER_PATTERN))
