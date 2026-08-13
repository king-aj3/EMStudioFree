# SPDX-License-Identifier: LGPL-2.1-or-later
"""Multi-design cable bundle composer (ROADMAP §2 Cable Designer, phase C —
geometric slice).

Packs an ordered list of member constructions (any mix: coax, twisted pair,
single wire, litz — anything with a circular envelope) into a compact bundle
cross-section, and reports the finished OD, fill factor and weight with an
optional overall jacket.

Packing: deterministic largest-first TANGENCY packing — every candidate
position is an exact closed-form tangency point (against one placed member
toward/away from the axis, or the circle-circle intersection against a pair
of placed members), and each member takes the feasible candidate closest to
the bundle axis — followed by MINIMAL-ENCLOSING-CIRCLE recentering. The
classic constructions come out exact: 2 members side-by-side (OD = 2×),
3 in a triangle (2.1547×), 1+6 hex (OD = 3× — fill 7/9); the worst small-n
case (4 members: rhombus vs the optimal square) is a documented +13 % on the
enclosing radius. The layout is nominal (members migrate along the lay), the
same caveat as the litz cross-section.

Envelope rule per member kind (the circle a member sweeps in the bundle):
solid/litz wire → finished OD over insulation/jacket; coax → OD over the
shield/jacket build (the bare engine's 2b EXCLUDES shield+jacket — pass the
real OD); twisted pair → 2 s (the rotating two-wire envelope is a circle of
twice the pair spacing).

Electrical coupling (member-to-member RLGC / crosstalk via FastHenry plus an
electrostatic capacitance solve) is deferred to its own de-risk session —
this slice ships the validated geometry the spec/CAD path needs.

Pure-python (math), Qt-free, FreeCAD-free. SI units (metres).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def _circle_circle(c1, r1, c2, r2):
    """Intersection points of two circles (centers c, radii r)."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    d = math.hypot(dx, dy)
    if d < 1e-15 or d > r1 + r2 or d < abs(r1 - r2):
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h2 = r1 * r1 - a * a
    if h2 < 0.0:
        if h2 < -1e-12:
            return []
        h2 = 0.0
    h = math.sqrt(h2)
    xm, ym = c1[0] + a * dx / d, c1[1] + a * dy / d
    if h == 0.0:
        return [(xm, ym)]
    return [(xm + h * dy / d, ym - h * dx / d),
            (xm - h * dy / d, ym + h * dx / d)]


def pack_circles(radii):
    """Deterministic tangency packing of circles around the origin.

    Members are placed largest-first; each takes the exact tangency candidate
    closest to the origin that overlaps nothing already placed. Returns
    ``[(x, y, r)]`` in INPUT order (not placement order).
    """
    order = sorted(range(len(radii)), key=lambda i: (-radii[i], i))
    placed = []
    out = [None] * len(radii)
    for idx in order:
        r = float(radii[idx])
        if not placed:
            pos = (0.0, 0.0)
        else:
            cands = []
            for (px, py, pr) in placed:
                d = math.hypot(px, py)
                t = pr + r
                if d < 1e-15:
                    cands.append((t, 0.0))    # canonical +x direction
                else:
                    cands.append((px - t * px / d, py - t * py / d))
                    cands.append((px + t * px / d, py + t * py / d))
            n = len(placed)
            for i in range(n):
                for j in range(i + 1, n):
                    ci, cj = placed[i], placed[j]
                    cands.extend(_circle_circle(
                        (ci[0], ci[1]), ci[2] + r, (cj[0], cj[1]), cj[2] + r))
            best = None
            for p in cands:
                if not all(math.hypot(p[0] - q[0], p[1] - q[1])
                           >= q[2] + r - 1e-9 for q in placed):
                    continue
                key = (round(math.hypot(p[0], p[1]), 9),
                       round(math.atan2(p[1], p[0]) % (2.0 * math.pi), 9))
                if best is None or key < best[0]:
                    best = (key, p)
            pos = best[1]
        placed.append((pos[0], pos[1], r))
        out[idx] = (pos[0], pos[1], r)
    return out


def min_enclosing_circle(placed):
    """(cx, cy, R) of the smallest circle containing all ``(x, y, r)`` circles.

    Centroid start + move-toward-farthest refinement with a shrinking step,
    keeping the best center seen — exact on symmetric layouts (the centroid
    IS the optimum there), monotone-improving otherwise.
    """
    cx = sum(c[0] for c in placed) / len(placed)
    cy = sum(c[1] for c in placed) / len(placed)

    def radius_at(px, py):
        return max(math.hypot(x - px, y - py) + r for x, y, r in placed)

    best = (radius_at(cx, cy), cx, cy)
    r0 = best[0]
    for k in range(1, 4000):
        fx, fy, fr = max(placed,
                         key=lambda c: math.hypot(c[0] - cx, c[1] - cy) + c[2])
        d = math.hypot(fx - cx, fy - cy)
        if d < 1e-15:
            break
        step = r0 / (k + 10.0)
        cx += step * (fx - cx) / d
        cy += step * (fy - cy) / d
        rr = radius_at(cx, cy)
        if rr < best[0]:
            best = (rr, cx, cy)
    return best[1], best[2], best[0]


def pack_and_center(radii):
    """Pack + recenter on the minimal enclosing circle: ([(x, y, r)], R)."""
    placed = pack_circles(radii)
    cx, cy, r_enc = min_enclosing_circle(placed)
    return [(x - cx, y - cy, r) for x, y, r in placed], r_enc


def twisted_pair_envelope_m(s_m):
    """Bundle envelope OD of a twisted pair with centre spacing s: 2 s."""
    return 2.0 * float(s_m)


@dataclass
class BundleMember:
    """One member construction: an envelope circle inside the bundle.

    :param label: display name (e.g. 'RG-58 coax', 'Cat5e pair 1').
    :param od_m: envelope OD (see the module envelope rule per kind).
    :param kind: 'wire' | 'litz' | 'coax' | 'twisted_pair' | 'generic'.
    :param qty: how many identical copies to place.
    :param weight_kg_m: optional per-length weight for the roll-up.
    :param conductor_d_m: bare (or equivalent-solid, for litz) conductor
        diameter — needed by the coupling/crosstalk analysis
        (``emstudio.wire.coupling``); 0 = not available (member excluded).
    :param current_a: load current per copy, amperes. Drives the member's I²R
        loss for the CONVECTION solve, where cables of one size carrying
        different currents run at different temperatures and therefore have
        different convection factors. 0 = not stated; the solve then falls
        back to a single typed wall gradient for every member.

        ⚠ It is PER COPY, not per row. A row with ``qty=3`` places three
        cables each carrying ``current_a`` — the same convention ``qty``
        already uses for every other field.
    """

    label: str
    od_m: float
    kind: str = "generic"
    qty: int = 1
    weight_kg_m: float = 0.0
    conductor_d_m: float = 0.0
    current_a: float = 0.0


@dataclass
class Bundle:
    """A packed multi-design bundle with an optional overall jacket."""

    members: list = field(default_factory=list)   # of BundleMember
    jacket: str = ""                              # '' = none
    jacket_m: float = 0.0                         # wall thickness
    name: str = "bundle"

    def _expanded(self):
        out = []
        for m in self.members:
            out.extend([m] * max(1, int(m.qty)))
        return out

    def pack(self):
        """[(x, y, r, member)] centred on the bundle axis + enclosing radius."""
        exp = self._expanded()
        if not exp:
            return [], 0.0
        placed, r_enc = pack_and_center([m.od_m / 2.0 for m in exp])
        return [(x, y, r, m) for (x, y, r), m in zip(placed, exp)], r_enc

    def core_od_m(self):
        """Packed-members OD (over the enclosing circle, before the jacket)."""
        return 2.0 * self.pack()[1]

    def od_m(self):
        """Finished bundle OD including the overall jacket."""
        return self.core_od_m() + 2.0 * (self.jacket_m if self.jacket else 0.0)

    def fill_factor(self):
        """Member-envelope area / enclosing-circle area (7-hex = 7/9)."""
        placed, r_enc = self.pack()
        if not placed or r_enc <= 0.0:
            return 0.0
        return sum(r * r for _x, _y, r, _m in placed) / (r_enc * r_enc)

    def weight_kg_m(self):
        """Sum of the members' per-length weights (0 entries contribute 0)."""
        return sum(m.weight_kg_m for m in self._expanded())

    def spec_markdown(self):
        placed, r_enc = self.pack()
        lines = [
            "# Bundle spec — {0}".format(self.name),
            "",
            "| Item | Value |",
            "|---|---|",
            "| Members | {0} ({1} placed) |".format(
                len(self.members), len(placed)),
            "| Core OD (packed members) | {0:.3f} mm |".format(
                2e3 * r_enc),
            "| Overall jacket | {0}{1} |".format(
                self.jacket or "none",
                ", {0:.2f} mm wall".format(self.jacket_m * 1e3)
                if self.jacket else ""),
            "| Finished OD | {0:.3f} mm |".format(self.od_m() * 1e3),
            "| Fill factor (envelope/enclosure) | {0:.3f} |".format(
                self.fill_factor()),
            "| Weight (members with data) | {0:.1f} g/m |".format(
                self.weight_kg_m() * 1e3),
            "",
            "## Members (packed largest-first; positions are nominal)",
            "",
            "| # | Label | Kind | Envelope OD | Position (x, y) |",
            "|---|---|---|---|---|",
        ]
        for i, (x, y, r, m) in enumerate(placed):
            lines.append(
                "| {0} | {1} | {2} | {3:.3f} mm | ({4:+.3f}, {5:+.3f}) mm |"
                .format(i + 1, m.label, m.kind, 2e3 * r, x * 1e3, y * 1e3))
        lines += [
            "",
            "*Deterministic tangency packing + minimal-enclosing-circle axis;",
            "exact for 2/3/7-member classics (7 equal members -> OD = 3x, fill",
            "7/9), worst small-n case +13 % vs the theoretical optimum (n = 4).",
            "Twisted-pair members use the rotating envelope 2s. Single-ended",
            "member-to-member RLGC/crosstalk: emstudio.wire.coupling (analytic",
            "wide-separation L/C + Paul weak-coupling model, FastHenry loop",
            "matrices at any spacing); insulated-bundle C matrices and",
            "differential pair-to-pair coupling remain future slices.*",
            "",
        ]
        from emstudio.legal import SPEC_DISCLAIMER

        lines.append(SPEC_DISCLAIMER)
        return "\n".join(lines)
