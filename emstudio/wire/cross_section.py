# SPDX-License-Identifier: LGPL-2.1-or-later
"""Litz cross-section layout: recursive circle packing for visualization + CAD export.

Produces the 2-D profile of a construction — every strand circle, per-level bundle
outlines, the fiber core, and the overall OD — used by the designer dialog's
cross-section view and by the FreeCAD profile export (sweep/loft-ready geometry).

Layout is the standard concentric-ring packing (1, 6, 12, 18, ... per ring). It is a
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


def _ring_positions(n, member_r):
    """Centers for n equal circles packed in concentric rings around the origin.

    Returns (positions, cluster_radius).
    """
    if n <= 0:
        return [], 0.0
    if n == 1:
        return [(0.0, 0.0)], member_r
    positions = [(0.0, 0.0)]
    ring = 1
    while len(positions) < n:
        ring_radius = 2.0 * member_r * ring
        capacity = max(6 * ring, 1)
        remaining = n - len(positions)
        count = min(capacity, remaining)
        offset = 0.0 if ring % 2 else math.pi / count  # stagger alternate rings
        for i in range(count):
            ang = 2.0 * math.pi * i / count + offset
            positions.append((ring_radius * math.cos(ang), ring_radius * math.sin(ang)))
        ring += 1
    cluster_r = 2.0 * member_r * (ring - 1) + member_r
    return positions[:n], cluster_r


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
    same numbers as the spec sheet), so cores, outlines and members always agree.
    Scales to 100k+ strands in well under a second.

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
            centers, _ = _ring_positions_around_core(op.count, r_member, op.core_m / 2.0)
        else:
            centers, _ = _ring_positions(op.count, r_member)
        centers = np.asarray(centers, dtype=float).reshape(-1, 2)

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
