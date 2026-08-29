# SPDX-License-Identifier: LGPL-2.1-or-later
"""Litz cross-section layout: recursive circle packing for visualization + CAD export.

Produces the 2-D profile of a construction — every strand circle, per-level bundle
outlines, the fiber core, and the overall OD — used by the designer dialog's
cross-section view and by the FreeCAD profile export (sweep/loft-ready geometry).

Layout is a concentric-ring packing whose ring COUNT and per-ring occupancy are
searched (see :func:`_ring_positions`) and then compressed onto the construction's
own level radii, so nothing is ever drawn outside the OD printed beside it. It is a
nominal representation for visual validation and CAD, not a claim about the exact
strand positions inside a real bunched rope (those migrate along the lay).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Circle:
    x: float
    y: float
    r: float
    kind: str  # 'strand' | 'bundle' | 'core' | 'od' | 'profile'
    level: int = 0


def _ring_counts(total, rings):
    """Split `total` members over `rings` concentric rings, proportional to index.

    Ring k sits at roughly 2 R k, so its circumference — and therefore how many
    members it can hold — grows with k; splitting in proportion to k is what
    keeps the OUTERMOST ring full. That is the whole point: the failure mode of a
    fixed hex sequence is a nearly empty outer ring (at n = 20 it used 1 of the
    18 places on ring 3, and that lone strand set the cluster radius).
    """
    weight = sum(range(1, rings + 1))
    counts = [max(1, int(round(total * k / weight))) for k in range(1, rings + 1)]
    # Settle the rounding drift from the outside in. The running total is carried
    # rather than re-summed: this runs once per candidate ring count per LEVEL, and
    # a re-sum would make a 100k-member level quadratic in the ring count.
    drift = total - sum(counts)
    idx = rings - 1
    while drift:
        if drift > 0:
            counts[idx] += 1
            drift -= 1
        elif counts[idx] > 1:  # never empty a ring; rings <= total guarantees room
            counts[idx] -= 1
            drift += 1
        idx = (idx - 1) % rings
    return counts


def _ring_positions(n, member_r):
    """Centers for n equal circles packed in concentric rings around the origin.

    Returns (positions, cluster_radius).

    The ring structure is SEARCHED, not fixed at the hex sequence (1, 6, 12, 18,
    ... at radius 2 R k). The hex lattice pins every ring at 2 R k, so a member
    count landing just past a complete ring strands the remainder on a nearly
    empty outer ring: 20 members reached 7 R where the construction's own radius
    (litz._resolve_lays, R_member sqrt(count / packing)) says 5.16 R — 1.36x —
    and those strands were then drawn OUTSIDE the OD printed on the same page,
    and cropped off the plot, whose axis limit is derived from that same OD.

    Each candidate ring is sized at the larger of the only two constraints that
    are real: members on the ring must not overlap EACH OTHER (R / sin(pi/count),
    the same rule :func:`_ring_positions_around_core` uses) and the ring must
    clear the ring inside it (2 R). Searching the ring count, and whether one
    member sits at the origin, reproduces the published optimal packings for
    n = 2..9 EXACTLY — 2.000, 2.155, 2.414, 2.701, 3.000, 3.000, 3.305, 3.613 R
    (Graham et al. / Packomania "circles in a circle") — and stays within 13 % of
    optimal above that (worst case n = 30). The hex sequence it replaces ran to
    1.84x the construction's own radius at its worst (2 members).
    """
    if n <= 0:
        return [], 0.0
    if n == 1:
        return [(0.0, 0.0)], member_r

    best = None
    # A member at the origin costs the first ring 2 R of radius but takes one
    # member off the outer ring; which wins depends on n (it wins at 7, loses at
    # 6), so both are tried rather than assumed.
    for centered in (True, False):
        outer = n - 1 if centered else n
        if outer < 1:
            continue
        # Ring k holds ~6k members, so n members never need more than ~sqrt(n)
        # rings; +2 keeps the range inclusive of the useful last case.
        for rings in range(1, int(math.sqrt(n)) + 2):
            if rings > outer:  # a ring must hold at least one member
                break
            counts = _ring_counts(outer, rings)
            radii = []
            r_prev = 0.0
            for idx, count in enumerate(counts):
                clear = (r_prev + 2.0 * member_r) if (centered or idx) else 0.0
                spread = member_r / math.sin(math.pi / count) if count > 1 else 0.0
                r_prev = max(clear, spread)
                radii.append(r_prev)
            reach = radii[-1] + member_r
            if best is None or reach < best[0]:
                best = (reach, centered, counts, radii)

    cluster_r, centered, counts, radii = best
    positions = [(0.0, 0.0)] if centered else []
    for idx, (count, ring_radius) in enumerate(zip(counts, radii)):
        offset = 0.0 if idx % 2 == 0 else math.pi / count  # stagger alternate rings
        for i in range(count):
            ang = 2.0 * math.pi * i / count + offset
            positions.append((ring_radius * math.cos(ang), ring_radius * math.sin(ang)))
    return positions, cluster_r


def _ring_positions_around_core(n, member_r, core_r):
    """Centers for n circles in ONE ring around a central core.

    Cored cabling operations are single-ring by construction ("tightly packed
    around the circumference"), so all n members go on one ring — placement never
    spills members to an outer ring. If the given core is smaller than the snug
    minimum, the ring radius is raised to the non-overlapping minimum
    r_member / sin(pi/n) so the drawing stays physical.
    """
    if n <= 0:
        return [], core_r
    ring_radius = core_r + member_r
    if n > 1:
        ring_radius = max(ring_radius, member_r / math.sin(math.pi / n))
    positions = [
        (ring_radius * math.cos(2.0 * math.pi * i / n),
         ring_radius * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]
    return positions, ring_radius + member_r


def layout_arrays(construction):
    """Vectorized cross-section: numpy arrays instead of per-strand objects.

    Uses the construction's own level radii as the single source of truth (the
    same numbers as the spec sheet): cores, outlines AND member centres are all
    referred to them, so no member is ever drawn outside the radius its own level
    reports. Scales to 100k+ strands in well under a second.

    Returns a dict:
      strands: (N,2) array of centers; strand_r: float
      cores:   ((M,2) array, (M,) radii)
      bundles: list of (centers (K,2), radius, level)
      wraps:   list of (centers (K,2), radius, level)
      od_r, jacket_r (0 if none), profile (half_w, half_h) or None
    """
    import numpy as np

    from . import litz as litz_mod

    con = construction
    level_radii = con.level_radii_m()  # official radius AFTER each op
    radii_before = [con.strand_radius_m] + level_radii[:-1]

    positions = np.zeros((1, 2))
    core_pos = np.zeros((0, 2))
    core_r = np.zeros(0)
    bundles = []
    wraps = []

    for level, op in enumerate(con.ops):
        r_member = radii_before[level] + (op.member_wrap_m or 0.0)
        if op.core_m > 0.0:
            centers, reach = _ring_positions_around_core(op.count, r_member,
                                                         op.core_m / 2.0)
        else:
            centers, reach = _ring_positions(op.count, r_member)
        centers = np.asarray(centers, dtype=float).reshape(-1, 2)

        # RECONCILE the placement with the engine's radius for this level. The
        # placement above is the tightest arrangement of RIGID circles; the
        # engine's radius (litz._resolve_lays, R_member sqrt(count / packing)) is
        # a bulk-DENSITY model, and the two are independent numbers for the same
        # thing. Where the density model is the tighter, the ring radii are
        # compressed onto it — a packing factor of 0.75 is precisely the claim
        # that the members deform and nest tighter than rigid circles can sit, so
        # honouring it is what the spec sheet already asserts. The alternative,
        # letting the drawing exceed the OD printed beside it, COMPOUNDED level
        # over level: Type 3 (20x5x4) drew strands to 1.39x its own stated OD and
        # the dialog's axis limit (1.15x od_r) then cropped 70 of the 400 strands
        # off the plot. Measured on the dialog's own type seeds, the ring radii
        # move by 0.4 % (20 members at packing 0.75) to 8.3 % (Types 7/8, 40
        # members at packing 0.85 — and 0.85 IS the compression those types are
        # named for). Net, this REDUCES drawn strand-on-strand overlap, because
        # the over-running sub-bundles used to interpenetrate far worse: Type 3
        # went from 100 % of a strand diameter to 33 %, Type 2 from 43 % to 33 %.
        # Below ~7 members the density model is geometrically unreachable at all
        # (2 members need 2.00 R, it says 1.63 R) and the drawing shows them
        # visibly overlapping — that is the model being optimistic, said out loud,
        # rather than a silent contradiction of the number on the page.
        #
        # Compress ONLY, never expand: a cluster that already fits is left with
        # its members touching and the packing void as the annulus out to the
        # level radius, because interstitial contact is where a real bunched
        # rope's void actually is. The r_member < r_level guard rejects the
        # degenerate input (packing_factor >= count) whose level radius is
        # smaller than ONE member — scaling onto that would fold the cluster
        # through the origin instead of just being wrong.
        #
        # Cored levels are deliberately EXEMPT. There the engine's radius is a
        # geometric statement, not a density one (r_core + 2 R_member for one
        # ring), and the placement already matches it exactly for every shipped
        # type. The one case that still over-runs is a hand-entered core SMALLER
        # than snug, where _ring_positions_around_core opens the ring on purpose
        # to keep members from overlapping while _resolve_lays does not follow —
        # that mismatch has to be fixed in the engine's level radius, because
        # here it would only be hidden.
        r_level = level_radii[level]
        if op.core_m <= 0.0 and r_member < r_level < reach and len(centers) > 1:
            centers = centers * ((r_level - r_member) / (reach - r_member))

        # replicate existing content (strand positions, cores, and inner-level
        # outlines) into each new member position — nested outlines must appear
        # inside EVERY higher-level member, exactly like cores
        positions = (centers[:, None, :] + positions[None, :, :]).reshape(-1, 2)
        if core_r.size:
            core_pos = (centers[:, None, :] + core_pos[None, :, :]).reshape(-1, 2)
            core_r = np.tile(core_r, len(centers))
        bundles = [
            ((centers[:, None, :] + pos[None, :, :]).reshape(-1, 2), r, lvl)
            for pos, r, lvl in bundles
        ]
        wraps = [
            ((centers[:, None, :] + pos[None, :, :]).reshape(-1, 2), r, lvl)
            for pos, r, lvl in wraps
        ]
        if op.core_m > 0.0:  # this operation's own core at the new center
            core_pos = np.vstack([core_pos, [[0.0, 0.0]]])
            core_r = np.append(core_r, op.core_m / 2.0)

        if level > 0:
            bundles.append((centers.copy(), radii_before[level], level))
        if op.member_wrap_m:
            wraps.append((centers.copy(), r_member, level))

    od_r = con.bundle_diameter_m() / 2.0
    profile = None
    if con.litz_type in litz_mod.RECTANGULAR_TYPES:
        import math as _math

        area = con.copper_area_m2() / con.packing_factor
        half_h = _math.sqrt(area / 8.0)
        profile = (2.0 * half_h, half_h)

    return {
        "strands": positions,
        "strand_r": con.strand_radius_m,
        "cores": (core_pos, core_r),
        "bundles": bundles,
        "wraps": wraps,
        "od_r": od_r,
        "jacket_r": (od_r + con.jacket_m) if con.jacket_m > 0.0 else 0.0,
        "profile": profile,
    }


def layout(construction):
    """Compute the full cross-section of a LitzConstruction.

    Returns a list of Circle (compatibility API over :func:`layout_arrays`).
    Strand circles use the bare-copper radius; bundle outlines wrap each bunching
    level; 'od' is the conductor diameter; 'jacket' the finished OD; rectangular
    types (7/8) get a 'profile' rectangle encoded via (x=half_w, y=half_h, r=0).
    """
    data = layout_arrays(construction)
    circles = []
    for centers, r, level in data["bundles"]:
        for cx, cy in centers:
            circles.append(Circle(float(cx), float(cy), r, "bundle", level))
    for centers, r, level in data["wraps"]:
        for cx, cy in centers:
            circles.append(Circle(float(cx), float(cy), r, "wrap", level))
    for x, y in data["strands"]:
        circles.append(Circle(float(x), float(y), data["strand_r"], "strand"))
    core_pos, core_r = data["cores"]
    for (kx, ky), kr in zip(core_pos, core_r):
        circles.append(Circle(float(kx), float(ky), float(kr), "core"))
    circles.append(Circle(0.0, 0.0, data["od_r"], "od"))
    if data["jacket_r"] > 0.0:
        circles.append(Circle(0.0, 0.0, data["jacket_r"], "jacket"))

    if data["profile"] is not None:
        half_w, half_h = data["profile"]
        circles.append(Circle(half_w, half_h, 0.0, "profile"))
    return circles


# Profile export detail levels (AJ: detailed profiles cause computational and
# visual problems downstream — sweeps/lofts and drawings need simplification).
DETAIL_LEVELS = ("auto", "full", "bundles", "envelope")


def export_to_freecad(construction, doc=None, detail="auto", max_strand_circles=5000):
    """Create a sweep/loft-ready profile object in FreeCAD.

    ``detail`` selects the profile simplification:

    * ``'full'``     — every strand circle + wraps/cores/outlines/OD/jacket.
                       Only sensible for small constructions; heavy in CAD.
    * ``'bundles'``  — per-level bundle outlines + cores + conductor OD + jacket
                       (no individual strands). The right level for most cable
                       sweeps: each Type-2/Type-4 outline can be lofted.
    * ``'envelope'`` — just conductor OD + jacket (and rectangular profile for
                       Types 7/8): the lightest profile, ideal for long helical
                       coil sweeps where only the cable body matters.
    * ``'auto'``     — 'full' up to ``max_strand_circles`` strands, else 'bundles'.

    Returns the created Part::Feature (a compound of circles/wires at the XY
    origin) — use as the profile for Part Sweep/Loft along a path.
    """
    import FreeCAD
    import Part

    if detail not in DETAIL_LEVELS:
        raise ValueError("detail must be one of {0}".format(DETAIL_LEVELS))
    if doc is None:
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()

    if detail == "auto":
        detail = "full" if construction.n_strands <= max_strand_circles else "bundles"
        if detail == "bundles":
            FreeCAD.Console.PrintWarning(
                "EMStudio: {0} strands — auto-simplified profile to bundle "
                "outlines (choose detail='full' to force strands).\n".format(
                    construction.n_strands
                )
            )

    include = {
        "full": {"strand", "wrap", "bundle", "core", "od", "jacket", "profile"},
        "bundles": {"wrap", "bundle", "core", "od", "jacket", "profile"},
        "envelope": {"od", "jacket", "profile"},
    }[detail]

    m_to_mm = 1e3
    edges = []
    for c in layout(construction):
        if c.kind not in include:
            continue
        if c.kind == "profile":
            hw, hh = c.x * m_to_mm, c.y * m_to_mm
            pts = [
                FreeCAD.Vector(-hw, -hh, 0), FreeCAD.Vector(hw, -hh, 0),
                FreeCAD.Vector(hw, hh, 0), FreeCAD.Vector(-hw, hh, 0),
                FreeCAD.Vector(-hw, -hh, 0),
            ]
            edges.append(Part.makePolygon(pts))
        else:
            edges.append(
                Part.makeCircle(
                    c.r * m_to_mm, FreeCAD.Vector(c.x * m_to_mm, c.y * m_to_mm, 0)
                )
            )

    obj = doc.addObject("Part::Feature", "LitzProfile")
    obj.Shape = Part.makeCompound(edges)
    obj.Label = "Litz profile — {0}".format(construction.name)
    doc.recompute()
    return obj
