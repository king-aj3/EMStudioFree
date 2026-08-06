# SPDX-License-Identifier: LGPL-2.1-or-later
"""Recover a thin-wire model from a SOLID conductor.

Why this is legitimate physics, not a shortcut
----------------------------------------------
NEC2 is a THIN-WIRE method-of-moments code: its GW card *is* a straight wire
of a given radius, and it has no concept of a surface. That is not a defect —
for a conductor whose cross-section is small against a wavelength, current
lives on the surface and the radiated field cannot distinguish a polygonal bar
from a round wire of the same section. A user's octagonal helix measured
lambda/600 across at its resonance; equal-area and equal-perimeter equivalent
radii differ by 2.7 % there, which moves the impedance ~0.4 % because Z
depends on ln(2l/a). Modelling the solid volumetrically would cost orders of
magnitude more for a difference below manufacturing tolerance.

It stops being legitimate when the conductor is electrically THICK. That is
what :func:`thin_wire_warning` is for — the caller is told, never silently
given a number that no longer means anything.

How the centreline is recovered
-------------------------------
Marching cross-sections. From one end cap, step along the local tangent, cut
the solid with a plane normal to it, take the centroid, update the tangent,
repeat.

The one non-obvious rule, and the reason a naive implementation fails on every
coil: **a cutting plane crosses a multi-turn conductor many times**, so the
section returns SEVERAL disjoint pieces. Taking the largest, or the first,
walks onto a neighbouring turn and produces a centreline that is confidently
wrong. The piece nearest the previous station is the only correct choice, and
a jump beyond a few steps' distance terminates the march rather than guessing.

Measured on a real 6.44-turn octagonal helix (2026-08-05): centreline length
6067 mm against the parametric truth of 6030 mm (+0.61 %), mean section area
282.78 mm^2 against 282.843 (-0.02 %), equivalent radius 9.487 mm against
9.488 mm.
"""

from __future__ import annotations

import math

#: Below this the thin-wire kernel is sound; above it, say so.
#: NEC2's own guidance is that the wire radius must be small against the
#: wavelength; lambda/100 is a conservative line to warn at.
THIN_WIRE_DIAM_OVER_LAMBDA = 0.01


class WireExtractError(ValueError):
    """The solid cannot be expressed as a thin-wire path."""


def _v(x):
    import FreeCAD

    return FreeCAD.Vector(x.x, x.y, x.z)


def end_caps(shape, tol_rel=0.02):
    """The sweep's two end faces: the smallest planar faces of equal area.

    A swept conductor's caps are congruent copies of the generating profile,
    so they are planar and share an area no side face matches. Returns the
    list of (area, face) — length 2 for an open conductor, 0 for a closed
    loop (which legitimately has no caps at all).
    """
    planars = [(f.Area, f) for f in shape.Faces
               if type(f.Surface).__name__ == "Plane"]
    if len(planars) < 2:
        return []
    planars.sort(key=lambda af: af[0])
    a0 = planars[0][0]
    caps = [af for af in planars if abs(af[0] - a0) <= tol_rel * a0]
    return caps if len(caps) == 2 else []


def _section_pieces(shape, point, direction, reach):
    """Connected pieces of the solid cut by a plane. [(centroid, area), ...]"""
    import FreeCAD
    import Part

    n = FreeCAD.Vector(*direction)
    n.normalize()
    seed = FreeCAD.Vector(1.0, 0.0, 0.0)
    if abs(seed.dot(n)) > 0.9:
        seed = FreeCAD.Vector(0.0, 1.0, 0.0)
    u = seed - n * seed.dot(n)
    u.normalize()
    w = n.cross(u)
    half = reach / 2.0
    p = point - u * half - w * half
    face = Part.Face(Part.makePolygon(
        [p, p + u * reach, p + u * reach + w * reach, p + w * reach, p]))
    return [(f.CenterOfMass, f.Area) for f in shape.common(face).Faces]


def centreline(shape, step_mm=None, max_steps=200000, progress_cb=None):
    """March the conductor's centreline. Returns (points, section_area_mm2).

    Raises :class:`WireExtractError` when the solid is not a single open
    wire-like conductor — refusing beats returning a path that silently
    skipped a turn.
    """
    caps = end_caps(shape)
    if not caps:
        raise WireExtractError(
            "no pair of end faces found — this is either a CLOSED loop (which "
            "has no ends to start from) or not a swept conductor. Cut the loop "
            "at the feed point and extract the open path.")
    (_a0, f0), (_a1, f1) = caps
    section_area = float(_a0)

    # A step near the conductor's own width follows curvature closely without
    # the cut plane re-intersecting the SAME piece it started from.
    ds = float(step_mm) if step_mm else math.sqrt(section_area) * 0.75
    if ds <= 0.0:
        raise WireExtractError("degenerate step size")
    # The cut face only has to span the CONDUCTOR, not the whole model. Sizing
    # it to the bounding-box diagonal made every step a boolean against a
    # half-metre plane: 137 s on a 6 m helix. Sized to the section it is ~4 s,
    # and it also stops the plane reaching neighbouring turns in the first
    # place (the nearest-piece rule below still stands as the guarantee).
    reach = max(3.0 * math.sqrt(section_area), 3.0 * ds)

    start = f0.CenterOfMass
    nrm = f0.normalAt(0, 0)
    if not shape.isInside(start + nrm * (ds * 0.25), 1e-6, True):
        nrm = nrm * -1.0
    pts = [start]
    tangent = _v(nrm)
    tangent.normalize()
    end_pt = f1.CenterOfMass

    # A REAL progress denominator. The march does not know its own path length
    # in advance, but the solid does: volume / section area IS the centreline
    # length for a swept conductor, to within the end-cap fudge. That turns a
    # meaningless swinging bar into a percentage, which on a multi-minute
    # extraction is the difference between "is this hung?" and "40 s to go".
    try:
        total_len = float(shape.Volume) / section_area
    except Exception:                       # noqa: BLE001 — progress only
        total_len = 0.0
    travelled = 0.0
    every = 25                              # ~1 report per 25 boolean cuts

    for _step in range(max_steps):
        pieces = _section_pieces(shape, pts[-1] + tangent * ds, tangent, reach)
        if not pieces:
            break
        # NEAREST piece — never the largest, never the first. See module docs.
        cen, _area = min(pieces, key=lambda ca: (ca[0] - pts[-1]).Length)
        if (cen - pts[-1]).Length > 3.0 * ds:
            break                       # would jump turns: stop honestly
        pts.append(cen)
        travelled += (pts[-1] - pts[-2]).Length
        if progress_cb is not None and total_len > 0.0 and _step % every == 0:
            progress_cb(min(travelled, total_len), total_len,
                        "Following the conductor's centreline")
        t = pts[-1] - pts[-2]
        if t.Length < 1e-9:
            break
        tangent = _v(t)
        tangent.normalize()
        if (pts[-1] - end_pt).Length < ds * 1.2:
            pts.append(end_pt)
            break
    else:
        raise WireExtractError("centreline march did not terminate")

    if len(pts) < 3:
        raise WireExtractError(
            "centreline collapsed to {0} point(s) — the solid does not look "
            "like a swept conductor".format(len(pts)))
    return pts, section_area


def polyline_length_mm(pts):
    return sum((pts[i + 1] - pts[i]).Length for i in range(len(pts) - 1))


def resample(pts, chord_mm):
    """Even-chord resampling of a polyline, endpoints preserved."""
    if chord_mm <= 0.0:
        raise WireExtractError("chord length must be positive")
    total = polyline_length_mm(pts)
    n = max(1, int(round(total / float(chord_mm))))
    out = [pts[0]]
    target = total / n
    acc = 0.0
    i = 0
    pos = pts[0]
    while len(out) < n:
        seg = pts[i + 1] - pos
        seg_len = seg.Length
        if acc + seg_len >= target - 1e-9:
            t = (target - acc) / seg_len
            pos = pos + seg * t
            out.append(pos)
            acc = 0.0
        else:
            acc += seg_len
            pos = pts[i + 1]
            i += 1
            if i >= len(pts) - 1:
                break
    out.append(pts[-1])
    return out


#: Any legitimate equivalent radius is bounded BELOW by the equal-area radius.
#: That is Polya's inequality: of all simply-connected sections of a given
#: area, the disc has the SMALLEST logarithmic capacity. It is a theorem, not
#: a heuristic, and it is cheap — which makes it a real check on a claimed
#: "better" radius rather than a matter of taste.
#:
#: It has already earned its place. A Schwarz-Christoffel derivation of the
#: conformal radius attempted here returned 9.4422 mm for the fixture octagon
#: (area 282.843 mm^2, circumradius exactly 10 mm), which is BELOW the
#: equal-area 9.4885 mm and therefore impossible. The bound caught it
#: immediately; without it the number looked entirely plausible.
def polya_lower_bound_mm(section_area_mm2):
    """Smallest equivalent radius any section of this area can have."""
    if section_area_mm2 <= 0.0:
        raise WireExtractError("non-positive section area")
    return math.sqrt(section_area_mm2 / math.pi)


def equivalent_radius_mm(section_area_mm2, mode="area", perimeter_mm=None):
    """Round-wire radius equivalent to a polygonal section.

    ``area`` (default) matches the cross-sectional area — the right choice for
    DC/low-frequency resistance and the conventional RF choice.

    ``perimeter`` matches the surface, which is where RF current actually
    flows. Requires ``perimeter_mm``: a section AREA alone does not determine
    a perimeter, and inferring one would mean silently assuming a shape.

    ON THE "CONFORMAL RADIUS" (logarithmic capacity), deliberately NOT offered
    -------------------------------------------------------------------------
    It is the physically principled choice for a thin-wire equivalent, and a
    value of 9.535349 mm for this project's fixture octagon is recorded in
    docs/NEXT_SESSION.md. It is **not implemented, on purpose**:

    * No derivation for it exists anywhere in this repo — the figure is
      second-hand.
    * It could not be reproduced here. A Schwarz-Christoffel construction gave
      9.4422 mm, which :func:`polya_lower_bound_mm` proves is IMPOSSIBLE, and
      no standard Gamma-function closed form tested reproduced 9.535349
      either. So BOTH candidate numbers are unverified, and one is provably
      wrong.
    * The suspicious part: the recorded value sits **+0.49 %** from the
      equal-area radius while the failed SC value sits **-0.49 %** from it.
      Symmetric about the shipped answer is what a sign error looks like.
    * And the stake is small. Equal-area 9.4885 and equal-perimeter 9.7450
      bracket any admissible answer, a 2.7 % spread; this module's own
      measurement is that 2.7 % moves the impedance ~0.4 %, so the 0.49 %
      under discussion moves it ~0.07 % — an order of magnitude inside the
      manufacturing tolerance of the conductor it describes.

    **Implementing it would mean shipping an unverifiable number to gain
    0.07 %.** If it is ever wanted, derive it independently first and check it
    against :func:`polya_lower_bound_mm`.
    """
    if section_area_mm2 <= 0.0:
        raise WireExtractError("non-positive section area")
    if mode == "area":
        return math.sqrt(section_area_mm2 / math.pi)
    if mode == "perimeter":
        if not perimeter_mm or perimeter_mm <= 0.0:
            raise WireExtractError(
                "equal-perimeter radius needs the section PERIMETER; an area "
                "alone does not determine one without assuming a shape")
        return float(perimeter_mm) / (2.0 * math.pi)
    if mode == "conformal":
        raise WireExtractError(
            "the conformal (logarithmic-capacity) radius is not implemented: "
            "the recorded 9.535349 mm figure has no derivation in this repo "
            "and could not be reproduced, and the gain over equal-area is "
            "~0.07 % of impedance. See equivalent_radius_mm.__doc__.")
    raise WireExtractError("unknown equivalent-radius mode: %r" % (mode,))


def thin_wire_warning(radius_mm, freq_hz):
    """Warn when the conductor stops being electrically thin, else None."""
    if not freq_hz or freq_hz <= 0.0:
        return None
    lam_mm = 299792458.0 / float(freq_hz) * 1000.0
    ratio = (2.0 * radius_mm) / lam_mm
    if ratio > THIN_WIRE_DIAM_OVER_LAMBDA:
        return ("the conductor is {0:.3g} wavelengths across at {1:.4g} MHz "
                "(lambda/{2:.0f}); the thin-wire model is only accurate for "
                "electrically THIN conductors — use a full-wave solver on the "
                "solid instead".format(ratio, freq_hz / 1e6, lam_mm /
                                       (2.0 * radius_mm)))
    return None


def extract(shape, chord_mm=None, freq_hz=None, step_mm=None,
            progress_cb=None):
    """Full extraction. Returns a dict describing the derived wire model.

    Every derived number is reported alongside HOW it was derived — this
    project's rule is that a derived quantity states its provenance, and a
    wire model silently standing in for a solid is exactly the kind of thing
    a user must be able to audit.
    """
    pts, section_area = centreline(shape, step_mm=step_mm,
                                   progress_cb=progress_cb)
    length = polyline_length_mm(pts)
    # Volume/length is a second, independent read of the section: if it
    # disagrees with the end-cap area the sweep is not uniform and the single
    # equivalent radius is a lie.
    area_from_volume = float(shape.Volume) / length if length > 0 else 0.0
    disagree = (abs(area_from_volume - section_area) / section_area
                if section_area > 0 else 1.0)
    radius = equivalent_radius_mm(section_area)

    if chord_mm is None:
        chord_mm = max(8.0 * radius, length / 400.0)
    wire = resample(pts, chord_mm)

    notes = []
    if disagree > 0.10:
        notes.append(
            "the end-cap section ({0:.4g} mm^2) and volume/length ({1:.4g} "
            "mm^2) disagree by {2:.0%} — the conductor's cross-section is not "
            "uniform, so ONE equivalent radius cannot represent it"
            .format(section_area, area_from_volume, disagree))
    w = thin_wire_warning(radius, freq_hz)
    if w:
        notes.append(w)
    if len(wire) < 8:
        notes.append("only {0} chords — increase the resolution if the path "
                     "is curved".format(len(wire) - 1))

    return {
        "points": wire,
        "dense_points": pts,
        "length_mm": length,
        "chord_mm": chord_mm,
        "chords": len(wire) - 1,
        "section_area_mm2": section_area,
        "section_area_from_volume_mm2": area_from_volume,
        "radius_mm": radius,
        "radius_mode": "equal-area",
        "method": "marching cross-sections",
        "notes": notes,
    }


def describe(info):
    """One human-readable provenance block for the extraction."""
    lines = [
        "Wire model derived from a solid conductor",
        "  method            {0}".format(info["method"]),
        "  centreline        {0:.1f} mm over {1} chord(s) of {2:.1f} mm".format(
            info["length_mm"], info["chords"], info["chord_mm"]),
        "  section area      {0:.4g} mm^2 (end caps); {1:.4g} mm^2 from "
        "volume/length".format(info["section_area_mm2"],
                               info["section_area_from_volume_mm2"]),
        "  equivalent radius {0:.4g} mm ({1})".format(
            info["radius_mm"], info["radius_mode"]),
    ]
    for n in info["notes"]:
        lines.append("  NOTE: " + n)
    return "\n".join(lines)
