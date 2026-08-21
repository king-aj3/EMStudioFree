# SPDX-License-Identifier: LGPL-2.1-or-later
"""Litz-wire constructions (industry Types 1-9) and AC-resistance analytics.

Taxonomy (New England Wire Technologies, https://litzwire.com/types-of-litz-wire/ —
the industry-standard 9-type classification):

  Type 1  round; strands bunched (twisted) together
  Type 2  round; Type-1 bunches cabled together
  Type 3  round; INSULATED Type-2s cabled together
  Type 4  round; Type-2 bunches cabled around a central fiber core
  Type 5  round; insulated Type-2 bundles cabled around a fiber core
  Type 6  round; bundles of insulated Type-4 cabled around a central fiber core
  Type 7  rectangular; film-insulated strands BRAIDED and formed to profile
  Type 8  rectangular; strands twisted and COMPRESSED to profile
  Type 9  coax-style; litz core + controlled dielectric + braid/return conductor

Lay (twist) conventions (Elektrisola litz design data): lay length is the axial
distance of one full 360-degree rotation (typical 0.8-60 mm); direction is S
(counter-clockwise) or Z (clockwise); successive bunching/cabling operations
customarily ALTERNATE direction; good proximity cancellation wants >= 3 twists per
mean turn length of the winding (Sullivan, "Simplified Design Method for Litz Wire").

Loss physics references:
* Exact round-wire skin effect via Kelvin functions (Ramo/Whinnery/Van Duzer).
* Isolated-bundle internal proximity — first-principles derivation, kernel
  H(x) = v*Gk(v)/4 via complex Bessel; low-f limit n^2 (a_s/r_b)^2 x^4/256.
  Constant EMPIRICALLY ANCHORED against FastHenry (0.0% at x=0.76, 2026-07-05;
  see tests/validation/wire_fasthenry.py).
* C.R. Sullivan, IEEE TPEL 14(2) 1999 (n^2 d^6 scaling); J.A. Ferreira, IEE
  Proc.-B 139(2) 1992.

All SI (meters, Hz, ohms); Qt-free and FreeCAD-free (plain pytest-able).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

MU0 = 4.0e-7 * math.pi
SIGMA_CU = 5.8e7  # S/m, annealed copper 20 C
RHO_CU = 1.0 / SIGMA_CU
COPPER_DENSITY = 8960.0  # kg/m^3

LITZ_TYPE_DESCRIPTIONS = {
    1: "round; strands bunched together",
    2: "round; Type-1 bunches cabled together",
    3: "round; insulated Type-2s cabled together",
    4: "round; Type-2 bunches cabled around a fiber core",
    5: "round; insulated Type-2 bundles cabled around a fiber core",
    6: "round; insulated Type-4 bundles cabled around a fiber core",
    7: "rectangular; film-insulated strands braided to profile",
    8: "rectangular; strands twisted and compressed to profile",
    9: "coax-style; litz core, dielectric, braid return",
}

# types whose outermost cabling surrounds a textile/fiber core
CORED_TYPES = (4, 5, 6)
RECTANGULAR_TYPES = (7, 8)


def skin_depth(freq_hz, sigma=SIGMA_CU, mu_r=1.0):
    """Skin depth in meters."""
    return 1.0 / math.sqrt(math.pi * freq_hz * MU0 * mu_r * sigma)


# --------------------------------------------------------------------- skin effect
def round_wire_ac_factor(freq_hz, radius_m, sigma=SIGMA_CU):
    """Exact Rac/Rdc of an isolated round wire (skin effect only).

    Kelvin-function solution with q = sqrt(2)*a/delta; asymptote
    a/(2 delta) + 1/4 + 3 delta/(32 a) beyond a/delta = 10.
    """
    if freq_hz <= 0.0:
        return 1.0
    delta = skin_depth(freq_hz, sigma)
    ratio = radius_m / delta
    if ratio < 1e-3:
        return 1.0
    if ratio > 10.0:
        return ratio / 2.0 + 0.25 + 3.0 / (32.0 * ratio)
    q = math.sqrt(2.0) * ratio
    ber_v, bei_v, berp_v, beip_v = _kelvin(q)
    num = ber_v * beip_v - bei_v * berp_v
    den = berp_v ** 2 + beip_v ** 2
    return (q / 2.0) * num / den


def _kelvin(q):
    """(ber, bei, ber', bei') — scipy when present, else power series (q <~ 12)."""
    try:
        from scipy.special import bei, beip, ber, berp

        return float(ber(q)), float(bei(q)), float(berp(q)), float(beip(q))
    except Exception:
        x = q / 2.0
        ber_v = bei_v = berp_v = beip_v = 0.0
        for k in range(0, 30):
            e = 4 * k
            t = ((-1.0) ** k) * x ** e / (math.factorial(2 * k) ** 2)
            ber_v += t
            if e > 0:
                berp_v += t * e / q
            e2 = 4 * k + 2
            t2 = ((-1.0) ** k) * x ** e2 / (math.factorial(2 * k + 1) ** 2)
            bei_v += t2
            beip_v += t2 * e2 / q
        return ber_v, bei_v, berp_v, beip_v


#: Set once the SciPy-less proximity fallback has warned, so a sweep of a
#: thousand frequencies produces ONE line rather than a thousand.
_PROX_WARNED = False


def _proximity_h(x):
    """Exact transverse-field proximity kernel H(x), x = d_strand/delta.

    H(x) = v*Gk(v)/4, v = x/sqrt(2);
    Gk = -(ber2 ber' + bei2 bei')/(ber^2 + bei^2) via complex Bessel functions.
    Limits: x^4/256 (x << 1), (x-1)/8 (x >> 1). FastHenry-anchored (2026-07-05).
    ⚠ That large-x limit read "~0.166 x" until 2026-08-21 and was WRONG by 33 %.
    Measured on this function's own SciPy branch, the slope converges to
    **0.12500** (1/8) at x = 64..512 and H(x) -> (x-1)/8 to better than 1e-4;
    0.166 is ~1/6. Nothing caught it because no gate ever ran the branch that
    used it — see the fallback below.
    """
    if x <= 0.0:
        return 0.0
    if x < 0.5:
        return x ** 4 / 256.0
    try:
        import cmath

        from scipy.special import jv, jvp

        c = cmath.exp(3j * math.pi / 4.0)
        v = x / math.sqrt(2.0)
        z0 = jv(0, v * c)
        zp = jvp(0, v * c) * c
        z2 = jv(2, v * c)
        gk = -(z2.real * zp.real + z2.imag * zp.imag) / (z0.real ** 2 + z0.imag ** 2)
        return v * gk / 4.0
    except Exception:
        # ⚠⚠ SciPy is missing, so this is the ASYMPTOTIC fallback — and it is
        # not a small approximation. Re-measured 2026-08-21 against this
        # function's own SciPy branch, in a genuinely SciPy-less interpreter:
        #
        #   x = 1.999  ->  0.062375   (small-argument series)   exact 0.056002
        #   x = 2.001  ->  0.125125   (linear asymptote)        exact 0.056203
        #
        # a **2.0x STEP** at the join, and the asymptote is **2.2x above the
        # exact Kelvin value** at x = 2 (exact: 0.056103). Proximity loss is
        # what litz wire EXISTS to control, so an over-estimate of it is a
        # wrong answer about the one number the user came for.
        #
        # ⚠⚠ THE COEFFICIENT ITSELF WAS WRONG UNTIL 2026-08-21, and that was a
        # SECOND defect on top of the step. This branch returned `0.166 * x`.
        # The true slope is **1/8**, not ~1/6: on the SciPy branch it converges
        # to 0.12500 at x = 64..512. `0.166 x` therefore read **33 % high even
        # at x = 512**, where an asymptote should be exact, and 5.9x high at
        # x = 2. Correcting it cuts the worst case from 5.92x to 2.23x and
        # brings x >= 4 inside 1.6 % (+1.541 % at x = 4, the worst point in
        # that range; -0.95 % by x = 5, under 0.1 % by x = 16).
        # ⛳ It survived because NO GATE EVER RAN THIS BRANCH: the battery
        # requires SciPy, so `wire_fasthenry`'s three proximity checks only
        # ever exercised the exact path, and all three (series limit, seam
        # continuity, monotonicity) pass under the fallback too — they cannot
        # tell the two apart. `litz_noscipy` now runs it in a subprocess.
        #
        # It is kept rather than raised, because refusing would break litz
        # analysis entirely on a FreeCAD build without SciPy — but it says so
        # ONCE per session. ⛳ The join is deliberately still DISCONTINUOUS and
        # is NOT moved to where the two branches now cross (~x = 2.7, which
        # would make it nearly continuous): a smooth curve through approximate
        # values looks right and would be just as approximate, and the step is
        # the honest visible signal that this path is in use. The warning is
        # the primary signal; the step is the backstop.
        global _PROX_WARNED
        if not _PROX_WARNED:
            _PROX_WARNED = True
            msg = ("EMStudio: SciPy is not available, so litz proximity loss "
                   "uses an asymptotic fallback that can read ~2.2x high "
                   "just above x = 2 (x = d/delta), converging to within "
                   "2% by x = 4. Install SciPy for the exact "
                   "Kelvin-function result.\n")
            try:
                import FreeCAD
                FreeCAD.Console.PrintWarning(msg)
            except Exception:
                import sys as _sys
                _sys.stderr.write(msg)
        if x < 2.0:
            return x ** 4 / 256.0
        return (x - 1.0) / 8.0


# ------------------------------------------------------------------- constructions
@dataclass
class BunchOp:
    """One bunching/cabling operation.

    :param count: how many members are twisted together in this operation.
    :param lay_m: lay length (axial distance of one full rotation), meters.
                  0 = auto (lay_ratio x the diameter at this level).
    :param direction: 'S' or 'Z'. None = auto (alternating, innermost = 'Z').
    :param insulated: members carry their own wrap/insulation before this op
                      (Type 3/5/6 constructions).
    :param core_m: fiber-core diameter AT THIS OPERATION — the members are packed
                   around its circumference (Type 4/5/6). 0 = no core;
                   AUTO_CORE (-1) = snug single-ring core sized so the members
                   exactly fit around it ("tightly packed around the circumference").
                   Type 6 carries cores at TWO levels: each Type-4 member's own core
                   and the larger final core.
    :param member_wrap: insulation applied to each MEMBER before this operation
                        cables them (e.g. 'polyester tape' on the Type-2s inside a
                        Type 4/6). '' = none.
    :param member_wrap_m: wrap thickness (radial build), meters. AUTO_WRAP (-1) =
                          industry default for the wrap type (tape 0.05 mm ≈ 2 mil,
                          serve 0.08 mm).
    """

    count: int
    lay_m: float = 0.0
    direction: str = ""
    insulated: bool = False
    core_m: float = 0.0
    member_wrap: str = ""
    member_wrap_m: float = 0.0


AUTO_CORE = -1.0
AUTO_WRAP = -1.0

# industry-standard default radial builds
TAPE_WRAP_DEFAULT_M = 0.05e-3   # ~2 mil polyester/PTFE tape wrap
SERVE_WRAP_DEFAULT_M = 0.08e-3  # single nylon/textile serve
JACKET_DEFAULT_M = 3.175e-3     # 1/8 inch — typical PVC jacket on heavy Type-6 cable
                                 # (industry range 1/8 to 1/4 inch)


def _default_wrap_thickness(wrap_name):
    name = (wrap_name or "").lower()
    if "serve" in name:
        return SERVE_WRAP_DEFAULT_M
    if name:
        return TAPE_WRAP_DEFAULT_M
    return 0.0


def snug_core_radius(member_radius_m, count):
    """Exact core radius so `count` members of radius R sit tightly in one ring.

    Adjacent members touch: 2 (rc + R) sin(pi/N) = 2R  ->  rc = R (1/sin(pi/N) - 1).
    For N <= 2 no core is needed (returns 0).
    """
    if count <= 2:
        return 0.0
    return member_radius_m * max(0.0, 1.0 / math.sin(math.pi / count) - 1.0)


@dataclass
class LitzConstruction:
    """A litz construction: strand + recursive bunching/cabling operations."""

    strand_diameter_m: float
    ops: list  # list of BunchOp (bare ints accepted by from_ops/make_type)
    litz_type: int = 1
    sigma: float = SIGMA_CU
    packing_factor: float = 0.75  # copper fraction of the bundle cross-section
    core_diameter_m: float = 0.0  # textile core (Types 4/5/6)
    serve: str = ""  # e.g. 'single nylon serve'
    jacket: str = ""  # overall jacket material, e.g. 'PVC' ('' = none)
    jacket_m: float = 0.0  # jacket wall thickness; AUTO_WRAP = 1/8" default
    lay_ratio: float = 12.0  # auto lay = lay_ratio * level diameter
    name: str = ""
    n_strands: int = field(init=False)

    def __post_init__(self):
        self.ops = [
            op if isinstance(op, BunchOp) else BunchOp(count=int(op)) for op in self.ops
        ]
        n = 1
        for op in self.ops:
            n *= int(op.count)
        self.n_strands = n
        self._resolve_lays()
        if not self.name:
            from . import units

            self.name = "Type {0} litz {1}/{2:.0f} AWG ({3})".format(
                self.litz_type,
                self.n_strands,
                units.m_to_awg(self.strand_diameter_m),
                "x".join(str(op.count) for op in self.ops),
            )

    # -- lay/core resolution -----------------------------------------------------
    def _resolve_lays(self):
        """Resolve auto lays, alternating directions, and per-level fiber cores.

        Level geometry recursion (single source of truth, also used by the
        cross-section layout and the OD):
        * uncored operation: members cluster compactly,
          R_out = R_member * sqrt(count / packing)
        * cored operation ("tightly packed around the circumference"):
          single ring around the core, R_out = r_core + 2 R_member;
          AUTO_CORE resolves to the exact snug radius for the member count.

        Legacy: a construction-level ``core_diameter_m`` (pre multi-core API)
        migrates onto the outermost operation.
        """
        if self.core_diameter_m > 0.0 and self.ops and self.ops[-1].core_m == 0.0:
            self.ops[-1].core_m = self.core_diameter_m

        r_level = self.strand_diameter_m / 2.0
        prev_dir = "S"  # so the innermost auto level comes out 'Z'
        self._level_radii = []
        for op in self.ops:
            # wraps applied to each member BEFORE this operation cables them
            if op.insulated and not op.member_wrap:
                op.member_wrap = "polyester tape"
            if op.member_wrap and op.member_wrap_m in (0.0, AUTO_WRAP):
                op.member_wrap_m = _default_wrap_thickness(op.member_wrap)
            elif not op.member_wrap:
                op.member_wrap_m = 0.0
            r_member = r_level + op.member_wrap_m

            if op.core_m == AUTO_CORE:
                op.core_m = 2.0 * snug_core_radius(r_member, op.count)
            if op.core_m > 0.0:
                r_level = op.core_m / 2.0 + 2.0 * r_member
            else:
                r_level = r_member * math.sqrt(op.count / self.packing_factor)
            self._level_radii.append(r_level)
            if not op.lay_m or op.lay_m <= 0.0:
                op.lay_m = self.lay_ratio * (2.0 * r_level)
            if not op.direction:
                op.direction = "Z" if prev_dir == "S" else "S"
            prev_dir = op.direction

        if self.jacket and self.jacket_m in (0.0, AUTO_WRAP):
            self.jacket_m = JACKET_DEFAULT_M
        elif not self.jacket:
            self.jacket_m = 0.0

    # -- geometry ---------------------------------------------------------------
    @property
    def strand_radius_m(self):
        return self.strand_diameter_m / 2.0

    def copper_area_m2(self):
        return self.n_strands * math.pi * self.strand_radius_m ** 2

    def level_radii_m(self):
        """Outer radius after each operation (innermost first)."""
        return list(self._level_radii)

    def bundle_diameter_m(self):
        """Conductor-assembly OD (over the last cabling op, EXCLUDING the jacket).

        This is the radius used by the proximity model (the copper region).
        """
        if self._level_radii:
            return 2.0 * self._level_radii[-1]
        return self.strand_diameter_m

    def finished_od_m(self):
        """Finished cable OD including the overall jacket."""
        return self.bundle_diameter_m() + 2.0 * self.jacket_m

    def equivalent_awg(self):
        """AWG of a solid wire with the same copper area."""
        from . import units

        d_eq = 2.0 * math.sqrt(self.copper_area_m2() / math.pi)
        return units.m_to_awg(d_eq)

    def copper_weight_kg_per_m(self):
        return self.copper_area_m2() * COPPER_DENSITY * self.twist_length_factor()

    def twist_length_factor(self):
        """Compounded helical strand-length factor from every lay operation.

        Each operation of lay L at mean helix radius (half the level radius for
        compact clusters; ring radius for cored single-ring levels) lengthens
        strands by sqrt(1 + (2 pi r_mean / L)^2).
        """
        factor = 1.0
        r_prev = self.strand_radius_m
        for op, r_level in zip(self.ops, self._level_radii):
            if op.core_m > 0.0:
                r_mean = op.core_m / 2.0 + r_prev  # ring center radius
            else:
                r_mean = r_level / 2.0
            factor *= math.sqrt(1.0 + (2.0 * math.pi * r_mean / op.lay_m) ** 2)
            r_prev = r_level
        return factor

    # -- electrical ---------------------------------------------------------------
    def rdc_per_meter(self, twist_factor=None):
        """DC resistance per meter (twist factor from lays unless overridden)."""
        tf = self.twist_length_factor() if twist_factor is None else twist_factor
        return tf / (self.sigma * self.copper_area_m2())

    def ac_factor(self, freq_hz, h_ext_per_amp=0.0):
        """Rac/Rdc: strand skin + internal proximity (+ optional external field).

        Rac/Rdc = S(x) + n^2 (a_s/r_b)^2 H(x) + 8 pi^2 n^2 a_s^2 H(x) (He/I)^2

        The external term uses the same FastHenry-anchored kernel with the
        winding's field-per-ampere ``h_ext_per_amp`` (A/m per A -> 1/m); for a
        long solenoid interior He/I ~ N_turns/length.

        A SINGLE conductor (n_strands == 1, e.g. a solid wire built with
        ``ops=[]``) has no other strands to bathe it in a transverse field, and
        its own current redistribution IS the Kelvin skin term — so the internal
        proximity term vanishes and Rac/Rdc reduces to the exact isolated-round-
        wire solution (plus the external winding-field term, which still
        applies). Multi-strand constructions are unchanged.
        """
        if freq_hz <= 0.0:
            return 1.0
        a = self.strand_radius_m
        delta = skin_depth(freq_hz, self.sigma)
        x = 2.0 * a / delta
        skin = round_wire_ac_factor(freq_hz, a, self.sigma)
        rb = self.bundle_diameter_m() / 2.0
        hx = _proximity_h(x)
        internal = 0.0
        if self.n_strands > 1:
            internal = (self.n_strands ** 2) * (a / rb) ** 2 * hx
        external = 0.0
        if h_ext_per_amp:
            # F_ext/F_int = He^2 / <He_int^2>, <He_int^2> = I^2/(8 pi^2 rb^2)
            external = 8.0 * math.pi ** 2 * (self.n_strands ** 2) * (a ** 2) * hx * (
                h_ext_per_amp ** 2
            )
        return skin + internal + external

    def rac_per_meter(self, freq_hz, h_ext_per_amp=0.0, twist_factor=None):
        return self.rdc_per_meter(twist_factor) * self.ac_factor(freq_hz, h_ext_per_amp)

    def loss_w_per_m(self, freq_hz, i_rms, h_ext_per_amp=0.0):
        """Dissipated power per meter at RMS current i_rms."""
        return self.rac_per_meter(freq_hz, h_ext_per_amp) * i_rms ** 2

    def ampacity(self, freq_hz, temp_rise_c=30.0, h_w_per_m2k=10.0,
                 h_ext_per_amp=0.0):
        """Continuous-current estimate from a surface heat balance.

        Free-air model: allowable dissipation per meter equals convection off the
        finished surface, P = h * (pi * OD_finished) * dT, so
            I_max = sqrt(P / Rac(f)).
        Defaults are conservative engineering values: dT = 30 K rise, h = 10 W/m^2K
        (still-air natural convection). Bundled-in-a-winding cables cool far worse —
        pass a smaller h (2-5) or use the winding He/I term AND derate. This is a
        sizing estimate, not a substitute for a thermal analysis of the finished
        assembly.
        """
        surface_per_m = math.pi * self.finished_od_m()
        p_allow = h_w_per_m2k * surface_per_m * temp_rise_c
        rac = self.rac_per_meter(freq_hz, h_ext_per_amp)
        return math.sqrt(p_allow / rac)

    # -- reporting -----------------------------------------------------------------
    def spec_dict(self):
        from . import units

        return {
            "name": self.name,
            "litz_type": self.litz_type,
            "type_description": LITZ_TYPE_DESCRIPTIONS.get(self.litz_type, ""),
            "strand_diameter": units.format_diameter(self.strand_diameter_m),
            "n_strands": self.n_strands,
            "operations": [
                {
                    "level": i + 1,
                    "count": op.count,
                    "lay_mm": op.lay_m * 1e3,
                    "direction": op.direction,
                    "insulated_members": op.insulated,
                    "core_mm": op.core_m * 1e3,
                    "member_wrap": op.member_wrap or "—",
                    "member_wrap_mm": op.member_wrap_m * 1e3,
                    "od_after_mm": self._level_radii[i] * 2e3,
                }
                for i, op in enumerate(self.ops)
            ],
            "fiber_core_mm": (self.ops[-1].core_m if self.ops else 0.0) * 1e3,
            "jacket": self.jacket or "none",
            "jacket_mm": self.jacket_m * 1e3,
            "finished_od_mm": self.finished_od_m() * 1e3,
            "serve": self.serve or "none/optional",
            "outer_diameter_mm": self.bundle_diameter_m() * 1e3,
            "copper_area_mm2": self.copper_area_m2() * 1e6,
            "equivalent_awg": round(self.equivalent_awg(), 1),
            "rdc_mohm_per_m": self.rdc_per_meter() * 1e3,
            "copper_weight_g_per_m": self.copper_weight_kg_per_m() * 1e3,
            "ampacity_dc_a": self.ampacity(1.0),
            "packing_factor": self.packing_factor,
            "twist_length_factor": round(self.twist_length_factor(), 4),
        }

    def spec_markdown(self):
        """Build-house-ready construction spec (Markdown)."""
        s = self.spec_dict()
        type_row = "Type {0} — {1}".format(s["litz_type"], s["type_description"])
        if not self.ops:
            type_row = "solid wire (single conductor, no bunching operations)"
        lines = [
            "# {0} construction spec — {1}".format(
                "Wire" if not self.ops else "Litz", s["name"]),
            "",
            "| Item | Value |",
            "|---|---|",
            "| Litz type | {0} |".format(type_row),
            "| Strand | {0} |".format(s["strand_diameter"]),
            "| Total strands | {0} |".format(s["n_strands"]),
            "| Fiber core | {0:.3g} mm |".format(s["fiber_core_mm"]),
            "| Serve | {0} |".format(s["serve"]),
            "| Overall jacket | {0}{1} |".format(
                s["jacket"],
                (", {0:.2f} mm wall ({1:.3f} in)".format(
                    s["jacket_mm"], s["jacket_mm"] / 25.4) if s["jacket_mm"] > 0 else ""),
            ),
            "| Conductor OD | {0:.3f} mm |".format(s["outer_diameter_mm"]),
            "| Finished OD (over jacket) | {0:.3f} mm |".format(s["finished_od_mm"]),
            "| Copper area | {0:.4f} mm² |".format(s["copper_area_mm2"]),
            "| Equivalent solid | AWG {0} |".format(s["equivalent_awg"]),
            "| Rdc | {0:.3f} mΩ/m |".format(s["rdc_mohm_per_m"]),
            "| Copper weight | {0:.2f} g/m |".format(s["copper_weight_g_per_m"]),
            "| Ampacity est. (DC, 30 K rise, still air) | {0:.0f} A |".format(s["ampacity_dc_a"]),
            "",
            "## Bunching / cabling operations (innermost first)",
            "",
            "| Level | Members | Lay length | Direction | Fiber core | Member wrap | OD after |",
            "|---|---|---|---|---|---|---|",
        ]
        for op in s["operations"]:
            wrap = op["member_wrap"]
            if op["member_wrap_mm"] > 0:
                wrap = "{0}, {1:.3f} mm".format(op["member_wrap"], op["member_wrap_mm"])
            lines.append(
                "| {0} | {1} | {2:.2f} mm | {3} | {4} | {5} | {6:.3f} mm |".format(
                    op["level"], op["count"], op["lay_mm"], op["direction"],
                    ("{0:.3f} mm".format(op["core_mm"]) if op["core_mm"] > 0 else "—"),
                    wrap,
                    op["od_after_mm"],
                )
            )
        from emstudio.legal import SPEC_DISCLAIMER

        lines += [
            "",
            "*Generated by EMStudio. Loss model: exact strand skin effect + "
            "FastHenry-anchored internal proximity (see project validation suite).*",
            "",
            SPEC_DISCLAIMER,
        ]
        return "\n".join(lines)


# ------------------------------------------------------------------- factories
def make_type(litz_type, strand_diameter_m, ops, **kw):
    """Construct an industry Type 1-9 litz.

    ``ops`` may be plain counts ([60, 5]) or BunchOp instances for full lay/
    direction/core control. Type-specific defaults (hierarchy per New England Wire):
    * Type 4/5: the FINAL cabling operation packs its members (Type 2s) around a
      fiber core -> ops[-1] gets an AUTO (snug single-ring) core.
    * Type 6: cores at TWO levels — each Type-4 member has its own core
      (ops[-2]) AND the final operation packs those around a larger core
      (ops[-1]). Requires >= 4 operations for the full n x m x X x Y hierarchy
      (strands -> Type-1 bunches -> Type-2s per Type-4 -> Type-4s), though any
      depth >= 2 is accepted.
    * 3/5/6: outermost members marked insulated.
    * 5/6:   served overall (packing slightly reduced).
    * 7/8:   rectangular profile (packing raised — compression/braid).
    * 9:     coax — the given ops describe the CORE litz; braid/dielectric are
             recorded for the spec sheet only (shield modeling is future work).
    Explicit BunchOp.core_m values always win over these defaults.
    """
    if litz_type not in LITZ_TYPE_DESCRIPTIONS:
        raise ValueError("litz_type must be 1..9")
    ops = [op if isinstance(op, BunchOp) else BunchOp(count=int(op)) for op in ops]
    if litz_type in (3, 5, 6) and len(ops) >= 2:
        ops[-1].insulated = True
    if litz_type in (4, 5) and ops and ops[-1].core_m == 0.0:
        ops[-1].core_m = AUTO_CORE
    if litz_type == 6:
        if ops and ops[-1].core_m == 0.0:
            ops[-1].core_m = AUTO_CORE  # the larger final core
        if len(ops) >= 2 and ops[-2].core_m == 0.0:
            ops[-2].core_m = AUTO_CORE  # each Type-4 member's own core
        # industry build-up: tape-wrapped Type-2s AND tape-wrapped Type-4s,
        # PVC jacket overall (1/8" default wall, typically 1/8-1/4")
        if len(ops) >= 2 and not ops[-2].member_wrap:
            ops[-2].member_wrap = "polyester tape"
        if not ops[-1].member_wrap:
            ops[-1].member_wrap = "polyester tape"
        kw.setdefault("jacket", "PVC")
        kw.setdefault("jacket_m", AUTO_WRAP)
    if litz_type in (5, 6) and "serve" not in kw:
        kw["serve"] = "single nylon serve" if litz_type == 5 else ""
        kw.setdefault("packing_factor", 0.70)
    if litz_type in RECTANGULAR_TYPES:
        kw.setdefault("packing_factor", 0.85)  # compressed/braided fill
        kw.setdefault("serve", "tape/extruded (optional)")
    return LitzConstruction(
        strand_diameter_m=strand_diameter_m, ops=ops, litz_type=litz_type, **kw
    )
