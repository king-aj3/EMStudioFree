# SPDX-License-Identifier: LGPL-2.1-or-later
"""Inverted-F antenna (IFA) synthesis — the printed handset/PCB element.

An IFA is ONE element (a single feed port) per the section 1 scope contract. It
is the most common antenna in consumer radio hardware: a trace in the corner of
a PCB with the ground plane cut away beneath it, shorted to ground at one end
and fed a short distance along from that short.

WHAT IS PHYSICS HERE, AND WHAT IS A SCALED SEED
------------------------------------------------
Exactly one relationship in this module is physics, and it is the one that sets
the frequency:

    L_path = h + l                      # short-to-open conductor path (m)
    f_res  = c / (4 * L_path)           # quarter-wave resonance

where ``h`` is the height of the short-circuit stub and ``l`` the length of the
radiating element. Everything else -- feed position, trace widths, ground
clearance -- is produced by scaling the published reference geometry and is
reported in ``warnings`` as a seed rather than a model. Saying which half is
which is the whole point; see docs/upstream/ifa-anchors.md.

VERIFIED against openEMS's OWN published example
------------------------------------------------
``openEMS/matlab/examples/antennas/inverted_f.m`` (shipped with openEMS, so
anyone can re-run it) gives h = 8 mm, l = 22.5 mm on an 80 x 80 x 1.5 mm
epsR 4.3 board. That is L_path = 30.5 mm, implying c/(4*L_path) = **2.4573 GHz**
against the 2.45 GHz its own loss tangent is referenced to -- **0.30 %**. The
rule and the reference agree without either having been fitted to the other.

⚠ Free-space lambda, deliberately. The ground plane is cut AWAY beneath the
element, so the radiator is a trace on a thin slab with no ground under it --
not a microstrip line, and very nearly air-loaded. That is why the free-space
quarter wave works to sub-percent here, and it is also the model's main limit: a
thicker board, a higher permittivity, or a smaller clearance all pull the
resonance DOWN from this rule.

⚠⚠ AN ELEMENT MODEL, NOT A PHONE MODEL. On a real handset the chassis is part of
the radiator and the ground plane resonates in its own right, so board size
changes the answer. This module designs the ELEMENT, on the reference's board.
Finite-chassis effects are a separate, unstarted piece of work and nothing here
should be read as covering them.

Pure-python, Qt-free, FreeCAD-free; results are dicts of plain floats (house
rule). All SI (metres, Hz, ohms).
"""
from __future__ import annotations

import math

C0 = 299792458.0

#: Stated accuracy of the quarter-wave rule on the resonant frequency
#: (fractional). ⚠ This is the CONSERVATIVE figure, not a measured one. We have
#: exactly ONE anchor point (the openEMS reference, 0.30 %), and one point does
#: not establish a tolerance -- especially for a rule that ignores substrate
#: loading entirely. Set equal to the patch engine's TL_ACCURACY so the two
#: analytic families can be read side by side and neither looks better than it
#: has earned.
IFA_ACCURACY = 0.05

#: The published reference, in metres. Kept as ONE dict so the scaling ratios
#: below cannot drift away from the geometry they came from, and so a reader can
#: check them against docs/upstream/ifa-anchors.md without arithmetic.
REFERENCE = {
    "source": "openEMS examples/antennas/inverted_f.m (C) 2013 Stefan Mahr",
    "stub_height_m": 8.0e-3,        # ifa.h
    "radiator_length_m": 22.5e-3,   # ifa.l
    "stub_width_m": 4.0e-3,         # ifa.w1
    "radiator_width_m": 2.5e-3,     # ifa.w2
    "feed_width_m": 1.0e-3,         # ifa.wf
    "feed_offset_m": 4.0e-3,        # ifa.fp, from the short-circuit stub
    "ground_clearance_m": 10.0e-3,  # ifa.e
    # The port gap: the reference excites a 0.5 mm slice at the base of the
    # feed element. It is geometry the solver needs, not a design choice, but
    # it must scale with the rest or a 6 GHz design ends up with a port gap
    # comparable to its own trace width.
    "feed_gap_m": 0.5e-3,
    "board_m": 80.0e-3,             # substrate.width == substrate.length
    "board_thickness_m": 1.5e-3,
    "er": 4.3,
}

#: L_path of the reference (m). Every ratio below is against THIS.
_REF_PATH = REFERENCE["stub_height_m"] + REFERENCE["radiator_length_m"]


def path_length(f0_hz):
    """Short-to-open conductor path for a quarter-wave resonance at f0 (m)."""
    f0 = float(f0_hz)
    if f0 <= 0:
        raise ValueError("need f0 > 0")
    return C0 / (4.0 * f0)


def resonant_frequency(path_len_m):
    """The inverse: resonance implied by a conductor path length (Hz).

    Provided so a caller checking an EXISTING geometry (the gate does exactly
    this against the openEMS reference) does not have to re-derive c/4L and get
    the factor wrong.
    """
    p = float(path_len_m)
    if p <= 0:
        raise ValueError("need path length > 0")
    return C0 / (4.0 * p)


def design_ifa(f0_hz, er=4.3, board_thickness_m=1.5e-3, stub_height_m=None,
               target_z_ohm=50.0):
    """Synthesize a printed inverted-F antenna for ``f0_hz``.

    :param f0_hz: design (resonant) frequency (Hz).
    :param er: board relative permittivity (default 4.3, the reference's FR-4).
    :param board_thickness_m: board thickness (m). Does NOT scale with frequency
        -- it is a manufacturing choice, so it is an input rather than an output.
    :param stub_height_m: height of the short-circuit stub (m). ``None`` takes
        the reference's proportion, which is the sensible default; pass a value
        when the available board keep-out dictates the height, and the radiator
        length absorbs the difference.
    :param target_z_ohm: feed impedance the feed offset is seeded for (default 50).

    Returns a dict of plain floats plus ``warnings`` and a cited ``source_note``.
    Raises ValueError on inputs that cannot produce a geometry.
    """
    f0 = float(f0_hz)
    er = float(er)
    t = float(board_thickness_m)
    if f0 <= 0 or er < 1.0 or t <= 0:
        raise ValueError("need f0>0, er>=1, board_thickness>0")

    l_path = path_length(f0)
    lam0 = C0 / f0

    # The stub height is the one free split in the quarter-wave path: the
    # radiator takes whatever is left. Default to the reference's proportion.
    if stub_height_m is None:
        h = l_path * (REFERENCE["stub_height_m"] / _REF_PATH)
    else:
        h = float(stub_height_m)
        if h <= 0:
            raise ValueError("need stub_height > 0")
    radiator = l_path - h
    if radiator <= 0:
        # A stub taller than the whole quarter-wave path leaves no radiator.
        # Refused rather than returned as a negative length, because a negative
        # length silently builds an inside-out geometry that meshes and solves
        # and answers the wrong question.
        raise ValueError(
            "stub height {0:.3g} mm is >= the whole quarter-wave path "
            "({1:.3g} mm) at {2:.4g} GHz — no radiator length is left".format(
                h * 1e3, l_path * 1e3, f0 / 1e9))

    scale = l_path / _REF_PATH
    w_stub = REFERENCE["stub_width_m"] * scale
    w_rad = REFERENCE["radiator_width_m"] * scale
    w_feed = REFERENCE["feed_width_m"] * scale
    feed_off = REFERENCE["feed_offset_m"] * scale
    clearance = REFERENCE["ground_clearance_m"] * scale
    feed_gap = REFERENCE["feed_gap_m"] * scale
    board = REFERENCE["board_m"] * scale

    warnings = [
        "resonant frequency is a quarter-wave rule accurate to ~±5 % vs "
        "full-wave — use Verify with openEMS for the achieved f_res and gain",
        "the feed offset ({0:.2f} mm from the short) is a SCALED SEED, not an "
        "impedance model: it reproduces the published reference's ratio so the "
        "geometry starts near {1:.0f} ohm, and it is a rougher estimate than "
        "even the patch engine's inset. Move it and re-solve to match."
        .format(feed_off * 1e3, float(target_z_ohm)),
        "trace widths and the ground clearance are scaled from the reference "
        "too — they set bandwidth and the exact match, not the resonance",
        "ELEMENT model, not a phone model: on a real handset the chassis "
        "radiates and the ground plane resonates, so board size changes the "
        "answer. This is the element on a {0:.0f} mm board.".format(board * 1e3),
    ]
    if t > 0.02 * lam0:
        warnings.append(
            "board thickness {0:.3g} mm is > 0.02·lambda0 ({1:.3g} mm): the "
            "element is no longer nearly air-loaded and the free-space quarter-"
            "wave rule will read HIGH — expect the solved resonance below the "
            "design".format(t * 1e3, 0.02 * lam0 * 1e3))
    if er > 6.0:
        warnings.append(
            "er {0:g} is well above the reference's 4.3 — the cut-away ground "
            "keeps the element mostly air-loaded, but the rule degrades as the "
            "slab gets more slab-like".format(er))

    return {
        "family": "ifa",
        "f0_hz": f0,
        "er": er,
        "wavelength_m": lam0,
        "path_length_m": l_path,
        "stub_height_m": h,
        "radiator_length_m": radiator,
        "stub_width_m": w_stub,
        "radiator_width_m": w_rad,
        "feed_width_m": w_feed,
        "feed_offset_m": feed_off,
        "ground_clearance_m": clearance,
        "feed_gap_m": feed_gap,
        "board_m": board,
        "board_thickness_m": t,
        "target_z_ohm": float(target_z_ohm),
        "scale_vs_reference": scale,
        "warnings": warnings,
        "source_note": (
            "IFA quarter-wave synthesis (see docs/upstream/ifa-anchors.md): "
            "L_path = h + l = c/4f = {0:.4f} mm, split h {1:.4f} / l {2:.4f} mm "
            "on er {3:g} / {4:.3g} mm board. Anchored to openEMS's own "
            "examples/antennas/inverted_f.m (h 8 / l 22.5 mm -> 2.4573 GHz, "
            "0.30 % from its 2.45 GHz reference). ±5 % f_res accuracy "
            "(conservative — one anchor point); widths and feed offset are "
            "SCALED SEEDS, not models.".format(
                l_path * 1e3, h * 1e3, radiator * 1e3, er, t * 1e3)),
    }
