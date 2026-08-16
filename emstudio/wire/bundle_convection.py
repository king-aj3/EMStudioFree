# SPDX-License-Identifier: LGPL-2.1-or-later
"""Derive a convection bundle factor by SOLVING the user's own geometry.

`thermal.surface_h` accepts a ``bundle_factor`` but nothing produced one: the
seam existed with no source. This is the source.

    factor = Nu_solved / Nu_ChurchillChu(Ra_that_resulted)

Churchill-Chu is exact for an isolated cylinder in unbounded still air and
wrong for a bundle in an enclosure; the factor is exactly that error, measured
for THIS arrangement instead of read off a table of conductor counts. Measured
for the reference trefoil (three 20 mm cables at 30 mm pitch in a 200 mm box):
**0.80** — the correlation over-predicts the film coefficient by about 25 %, in
the unsafe direction.

⚠ **The factor is measured at ONE operating point.** The flux boundary
condition makes dT — and therefore Ra — an OUTPUT, so the comparison is made at
the Ra the solve produced. A factor derived at one power level is applied at
others on the assumption that the RATIO moves far less than either Nusselt
number does. That assumption is stated here rather than hidden: it is the
reason the provenance records the Ra it was solved at.

**MIXED DIAMETERS: one factor PER SIZE, still never an average.** Nu_D is built
on a diameter, so a bundle of unlike cables has no single factor — and the
first version refused one outright. That refusal was correct and useless: the
shipped default cable mix is mixed, so the button refused on first click.

What makes it answerable is that the question was the wrong shape. A mixed
bundle does not need ONE factor; it needs one per size, each solved against its
own diameter, in the SAME solve — the whole point is that the sizes cool each
other. `solve_mixed_bundle_factor` writes one snappy patch per size and returns
a :class:`MixedBundleFactor`; ask it for the size you are rating. Nothing is
averaged across unlike cables at any point.

MEASURED, on the trefoil's own centres in a 200 mm enclosure with two of the
three cables shrunk to 10 mm:

    1 x 20 mm   factor 0.9479   (Nu 3.6097 vs Churchill-Chu 3.8082 @ Ra 5541)
    2 x 10 mm   factor 0.8438   (Nu 1.9997 vs Churchill-Chu 2.3699 @ Ra  625)

**12.3 % apart** — which is the reason this returns a set and not a number.

⚠ **A mixed bundle has no single number to print, and this module will not
invent one.** :attr:`MixedBundleFactor.worst` exists for the caller who must
apply ONE factor to a whole bundle, and it is the most pessimistic size on
purpose — but it is a stated conservatism, not a bundle factor, and it says so
in its own provenance.

**MIXED LOADING within one diameter, too.** A group is one diameter at one wall
flux, because that is what a single snappy patch can carry — so two same-size
cables dissipating different losses are two groups with two factors, and the
result is keyed by **patch**, not by diameter.

⚠ This was keyed by SIZE in v0.97.0, which meant a same-size pair collided and
one was silently dropped; it had to REFUSE the arrangement instead. Nothing
about the mesh changed to fix it — the case writer had always split those
cables onto separate patches correctly. It was bookkeeping, and the bug it
caused was the dangerous kind: a lost group is a cable rated on somebody else's
number.

``factor_for(d)`` still answers directly whenever a diameter is unambiguous —
the common case did not get harder. It refuses, naming the fluxes, only when
one diameter really does carry several groups.

⚠ **This runs a CFD solve — minutes, not milliseconds.** It must never be
called from a property edit or an interactive redraw. `solve_steady` bisects
and calls `surface_h` ~80 times per answer; the factor is a cached scalar for
exactly that reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as _field

from emstudio.wire.thermal import nu_churchill_chu

__all__ = ["BundleFactor", "MixedBundleFactor", "geometry_key", "cables_key",
           "centres_from_bundle", "cables_from_bundle",
           "cable_loads_from_bundle", "bundle_has_currents",
           "rdc20_from_diameter",
           "solve_bundle_factor", "solve_mixed_bundle_factor",
           "gradient_from_joule", "joule_w_per_m"]

PR_AIR = 0.71


def joule_w_per_m(i_a, rdc20_ohm_m, t_cond_c, material="Cu", rac_factor=1.0):
    """I²R(T) per metre — the same loss `thermal.solve_steady` computes.

    Shared rather than re-derived so the CFD case is fed by the SAME electrical
    model the ampacity answer uses. Two independent loss expressions would
    eventually disagree, and the CFD would then be solving a cable the product
    is not rating.
    """
    from emstudio.wire.thermal import CONDUCTORS
    con = CONDUCTORS[material]
    r_t = float(rdc20_ohm_m) * float(rac_factor) * (
        1.0 + con["alpha20"] * (float(t_cond_c) - 20.0))
    return float(i_a) ** 2 * r_t


def gradient_from_joule(q_w_per_m, d_cable, t_film_k=315.0):
    """Wall temperature gradient (K/m) equivalent to a Joule loss per metre.

    THIS is the EM -> thermal coupling on this geometry, and it is NOT
    ``fvOptions``. snappy CARVES THE CABLES OUT of the fluid domain, so there
    is no solid region in the mesh: a volumetric source would heat the AIR, not
    the conductor. The conductor's loss enters as what it physically is at the
    fluid boundary — a surface heat flux.

        q'' = q' / (pi D)          W/m^2, spread over the wetted perimeter
        dT/dn = q'' / k_air        K/m, the prescribed-gradient BC

    ⚠ ``k`` is the AIR conductivity at the film temperature, because the
    gradient is taken in the fluid. Using the conductor's k here would be a
    factor of ~10^4 wrong and would look plausible in the dictionary.

    ⚠ A true SOLID-side Joule source — conduction inside the conductor, with
    the loss distributed through its cross-section — needs
    ``chtMultiRegionFoam`` and a meshed solid region. That is a fidelity
    upgrade, not a correction: for a good conductor the cross-section is very
    nearly isothermal, which is the assumption IEC 60287 already makes.
    """
    from emstudio.wire.thermal import air_properties
    if d_cable <= 0:
        raise ValueError("cable diameter must be positive")
    if q_w_per_m <= 0:
        raise ValueError("a non-positive Joule loss deposits no heat; the "
                         "convection problem would be undefined")
    k_air = air_properties(float(t_film_k))[0]
    q_flux = float(q_w_per_m) / (math.pi * float(d_cable))
    return q_flux / k_air


@dataclass
class BundleFactor:
    """A solved convection factor and everything needed to re-check it."""

    factor: float = 1.0
    nu_solved: float = 0.0
    nu_correlation: float = 0.0
    ra_d: float = 0.0
    d_cable: float = 0.0
    n_cables: int = 0
    #: Wall gradient (K/m) this group was solved at. Together with ``d_cable``
    #: it IDENTIFIES the group: one diameter can carry several, because
    #: same-size cables on different losses run at different temperatures.
    #: 0.0 on a uniform bundle, where there is nothing to disambiguate.
    gradient: float = 0.0
    #: The snappy patch this came off, when there was more than one.
    patch: str = ""
    converged: bool = False
    drift: float = float("nan")
    geometry: str = ""
    #: The OpenFOAM case this came out of, so the solved FIELDS can be found
    #: again — the factor is one number distilled from a whole temperature and
    #: velocity field, and without this the field is unreachable the moment the
    #: solve returns. Empty when the caller supplied no case (pure-python
    #: tests, cached factors reloaded from a document).
    case_dir: str = ""
    warnings: list = _field(default_factory=list)

    @property
    def provenance(self):
        """One line carrying every fact needed to judge or re-run this.

        ⚠ A factor nobody can trace is worse than no factor: it looks
        authoritative and cannot be re-checked. `solve_steady` prints this
        alongside the temperature it produced.
        """
        state = "converged" if self.converged else "NOT CONVERGED"
        drift = ("drift %.1e" % self.drift) if self.drift == self.drift \
            else "drift unknown"
        return ("OpenFOAM %s: Nu %.4f vs Churchill-Chu %.4f at Ra %.4g "
                "(%s, %s)" % (self.geometry, self.nu_solved,
                              self.nu_correlation, self.ra_d, state, drift))

    @property
    def correlation_error_pct(self):
        """How wrong the bare correlation is, as the user would say it:
        POSITIVE means Churchill-Chu over-predicts the cooling."""
        if not self.factor:
            return float("nan")
        return 100.0 * (1.0 / self.factor - 1.0)


@dataclass
class MixedBundleFactor:
    """One :class:`BundleFactor` per solved GROUP, from a single solve.

    The groups were solved TOGETHER — they share an enclosure and heat each
    other, which is the whole reason a per-group factor is not the same as
    solving each group in its own bundle.

    A group is one diameter at one wall flux, because that is what one snappy
    patch can carry. So this is keyed by PATCH, not by diameter: two cables of
    the same size dissipating different losses run at different temperatures
    and genuinely have different factors, and keying by size would have made
    one of them silently overwrite the other. That is not hypothetical — the
    first version of this class was keyed by size and had to REFUSE the case
    rather than lose a group.

    Most bundles have one group per size, so :attr:`by_size` and
    ``factor_for(d)`` still answer directly; they refuse only when a diameter
    is genuinely ambiguous.
    """

    by_group: dict = _field(default_factory=dict)     # patch -> BundleFactor
    geometry: str = ""
    converged: bool = False
    drift: float = float("nan")
    #: The OpenFOAM case every group was solved in — ONE case, because the
    #: groups share an enclosure. See :attr:`BundleFactor.case_dir`.
    case_dir: str = ""
    warnings: list = _field(default_factory=list)

    @property
    def groups(self):
        """Patch names, in solve order — largest diameter, hottest first."""
        return list(self.by_group)

    @property
    def sizes(self):
        """Distinct diameters in metres, largest first."""
        return sorted({f.d_cable for f in self.by_group.values()}, reverse=True)

    @property
    def by_size(self):
        """``{diameter: BundleFactor}`` — the common case, keyed by size.

        ⚠ RAISES when one diameter carries more than one group, rather than
        dropping one. A bundle where two same-size cables run at different
        losses has two answers for that size and no way to key them apart by
        diameter; ask :meth:`factor_for` with the gradient, or read
        :attr:`by_group`.
        """
        out = {}
        for f in self.by_group.values():
            if f.d_cable in out:
                raise ValueError(
                    "%.4g mm carries %d groups at different wall fluxes "
                    "(%s K/m), so this bundle cannot be keyed by size. Use "
                    "factor_for(d, gradient=...) or by_group."
                    % (1000.0 * f.d_cable,
                       sum(1 for g in self.by_group.values()
                           if g.d_cable == f.d_cable),
                       ", ".join("%.4g" % g.gradient
                                 for g in self.by_group.values()
                                 if g.d_cable == f.d_cable)))
            out[f.d_cable] = f
        return out

    @property
    def factor(self):
        raise ValueError(
            "this bundle has %d solved groups and %d factors, not one: %s. "
            "Ask for the cable you are rating with factor_for(d[, gradient]), "
            "or take `.worst` if you must apply a single conservative number."
            % (len(self.by_group), len(self.by_group),
               ", ".join("%.4g mm @ %.4g K/m -> %.4f"
                         % (1000.0 * f.d_cable, f.gradient, f.factor)
                         for f in self.by_group.values())))

    def factor_for(self, d_cable, gradient=None, tol=1e-9):
        """The factor for the cable being rated.

        ``gradient`` is only needed when one diameter carries several groups —
        i.e. same-size cables on different losses. Without it, an ambiguous
        diameter RAISES and names the fluxes rather than picking one.

        ⚠ Deliberately not nearest-match on either axis. Interpolating would
        hand back a factor for a cable that was never in the enclosure, and it
        would look exactly like one that was.
        """
        hits = [f for f in self.by_group.values()
                if abs(f.d_cable - float(d_cable)) <= tol]
        if not hits:
            raise ValueError(
                "no factor was solved for a %.4g mm cable; this bundle carries "
                "%s" % (1000.0 * float(d_cable),
                        ", ".join("%.4g mm" % (1000.0 * d) for d in self.sizes)))
        if gradient is not None:
            exact = [f for f in hits
                     if abs(f.gradient - float(gradient)) <= 1e-9]
            if not exact:
                raise ValueError(
                    "no %.4g mm group was solved at %.4g K/m; that size was "
                    "solved at %s K/m"
                    % (1000.0 * float(d_cable), float(gradient),
                       ", ".join("%.4g" % f.gradient for f in hits)))
            return exact[0]
        if len(hits) > 1:
            raise ValueError(
                "%.4g mm carries %d groups, solved at %s K/m — say which with "
                "factor_for(d, gradient=...). Same-size cables on different "
                "losses run at different temperatures and do not share a "
                "factor."
                % (1000.0 * float(d_cable), len(hits),
                   ", ".join("%.4g" % f.gradient for f in hits)))
        return hits[0]

    @property
    def worst(self):
        """The most pessimistic group's factor — for a caller needing ONE.

        ⚠ This is a stated conservatism, not the bundle's factor. Applying it
        to a group that solved better under-rates that cable; applying anything
        else to the worst group over-rates it, which is the unsafe direction.
        """
        return min(self.by_group.values(), key=lambda f: f.factor)

    @property
    def spread_pct(self):
        """How far apart the groups' factors are, as a percentage of the worst.

        Small means one number would do; large means the groups genuinely cool
        differently and a single factor throws that away.
        """
        vals = [f.factor for f in self.by_group.values()]
        if not vals or min(vals) <= 0:
            return float("nan")
        return 100.0 * (max(vals) - min(vals)) / min(vals)

    @property
    def provenance(self):
        state = "converged" if self.converged else "NOT CONVERGED"
        drift = ("drift %.1e" % self.drift) if self.drift == self.drift \
            else "drift unknown"
        # ⚠ The flux is named per group, not just the diameter. On a bundle
        # with two same-size groups the diameter alone does not identify which
        # answer is which, and a provenance that cannot be traced back to one
        # cable is the thing this whole class exists to avoid.
        return ("OpenFOAM mixed bundle %s (%s, %s): %s"
                % (self.geometry, state, drift,
                   "; ".join(
                       "%.4g mm @ %.4g K/m -> factor %.4f (Nu %.4f vs "
                       "Churchill-Chu %.4f at Ra %.4g)"
                       % (1000.0 * f.d_cable, f.gradient, f.factor,
                          f.nu_solved, f.nu_correlation, f.ra_d)
                       for f in self.by_group.values())))


def geometry_key(centres, d_cable, box_w, box_h):
    """A stable descriptor of what a factor was solved for.

    Used to notice that the design moved out from under a cached factor —
    confinement and spacing are precisely what the factor measures, so it does
    not carry across a geometry change.
    """
    pts = ",".join("%.6g:%.6g" % (x, y) for x, y in sorted(centres))
    return "d%.6g/box%.6gx%.6g/[%s]" % (d_cable, box_w, box_h, pts)


def cables_key(cables, box_w, box_h):
    """Geometry key for ``(x, y, d)`` or ``(x, y, d, gradient)`` cables.

    ⚠ A UNIFORM set produces the byte-identical string :func:`geometry_key`
    always produced, so adding mixed support does not silently stale every
    factor already cached in a user's document. A set that differs only in
    DIAMETER keeps the diameter-keyed form for the same reason.

    ⚠ The gradients enter the key as soon as they differ. Which cable carries
    which loss changes every group's answer, and a "100..400 K/m" summary in
    the provenance cannot distinguish an arrangement from its mirror — a
    staleness check that cannot see a change is not a staleness check.
    """
    norm = [(float(c[0]), float(c[1]), float(c[2]),
             float(c[3]) if len(c) > 3 else None) for c in cables]
    ds = {round(d, 12) for _x, _y, d, _g in norm}
    gs = {round(g, 12) for _x, _y, _d, g in norm if g is not None}
    if len(gs) > 1:
        pts = ",".join("%.6g:%.6g:%.6g:%.6g" % (d, g, x, y)
                       for d, g, x, y in sorted((d, g, x, y)
                                                for x, y, d, g in norm))
        return "mixedload/box%.6gx%.6g/[%s]" % (box_w, box_h, pts)
    if len(ds) == 1:
        return geometry_key([(x, y) for x, y, _d, _g in norm], ds.pop(),
                            box_w, box_h)
    pts = ",".join("%.6g:%.6g:%.6g" % (d, x, y)
                   for d, x, y in sorted((d, x, y) for x, y, d, _g in norm))
    return "mixed/box%.6gx%.6g/[%s]" % (box_w, box_h, pts)


def cables_from_bundle(bundle):
    """``[(x, y, d)]`` from an :class:`emstudio.wire.bundle.Bundle`.

    The Cable Designer has already packed the bundle, so the CFD case consumes
    that geometry rather than asking the user to restate it. Mixed diameters
    are carried through, not refused — each size becomes its own patch and its
    own Nusselt number.
    """
    placed, _r_enc = bundle.pack()
    if not placed:
        raise ValueError("this bundle has no members to solve")
    return [(x, y, 2.0 * r) for x, y, r, _m in placed]


def rdc20_from_diameter(d_conductor_m, material="Cu"):
    """DC resistance per metre at 20 °C of a solid round conductor.

    ⚠ For a LITZ or stranded member ``conductor_d_m`` is the equivalent-SOLID
    diameter, so this is the DC value and carries no strand or skin effect.
    That is the right input here: the convection case wants the heat the cable
    actually dissipates, and `joule_w_per_m` takes an ``rac_factor`` for the
    AC part rather than hiding it in the geometry.
    """
    from emstudio.wire.thermal import CONDUCTORS
    if d_conductor_m <= 0:
        raise ValueError("conductor diameter must be positive")
    if material not in CONDUCTORS:
        raise ValueError("unknown conductor material %r; this module knows %s"
                         % (material, ", ".join(sorted(CONDUCTORS))))
    area = math.pi * (float(d_conductor_m) / 2.0) ** 2
    return CONDUCTORS[material]["rho20"] / area


def cable_loads_from_bundle(bundle, t_cond_c=90.0, material="Cu",
                            rac_factor=1.0, t_film_k=315.0):
    """``[(x, y, d, gradient)]`` — the packed bundle WITH each cable's own flux.

    This is what makes mixed LOADING reachable: every member's stated
    ``current_a`` becomes its own I²R loss, its own wall flux, and therefore
    its own patch and its own convection factor. Cables of one size on
    different currents stop sharing an answer.

    ⚠ **Two different diameters are in play and conflating them is the trap.**
    The resistance uses ``conductor_d_m`` — the metal that dissipates — while
    the flux is spread over the ENVELOPE ``od_m``, because that is the surface
    the air actually touches. Using one for both would be wrong in opposite
    directions for a thin conductor in a thick jacket.

    ⚠ ``t_cond_c`` is an ASSUMPTION, and a circular one if taken too seriously:
    R rises with temperature, and the temperature is what the thermal solve is
    for. It defaults to 90 °C — a typical insulation class — and the caller is
    expected to state it. The error is second-order (Cu drifts ~0.4 %/K on R,
    and the FACTOR is a ratio in which most of it cancels), but it is an
    assumption and not a measurement.

    Raises when a member states a current but no conductor diameter: without
    the metal's cross-section there is no resistance, and inventing one would
    put a fabricated heat load into a CFD case.
    """
    placed, _r_enc = bundle.pack()
    if not placed:
        raise ValueError("this bundle has no members to solve")
    out = []
    for x, y, r, m in placed:
        i_a = float(getattr(m, "current_a", 0.0) or 0.0)
        if i_a <= 0:
            raise ValueError(
                "member %r states no current, so its heat load is unknown. "
                "Give every member a current to solve the bundle by load, or "
                "leave them all at zero to solve it at one typed wall "
                "gradient — a default applied to half a bundle is worse than "
                "no default." % getattr(m, "label", "?"))
        d_cond = float(getattr(m, "conductor_d_m", 0.0) or 0.0)
        if d_cond <= 0:
            raise ValueError(
                "member %r carries %.4g A but states no conductor diameter, "
                "so its I²R loss cannot be computed. Enter the bare (or "
                "equivalent-solid) conductor Ø, or clear the current."
                % (getattr(m, "label", "?"), i_a))
        q = joule_w_per_m(i_a, rdc20_from_diameter(d_cond, material),
                          t_cond_c, material=material, rac_factor=rac_factor)
        out.append((x, y, 2.0 * r,
                    gradient_from_joule(q, 2.0 * r, t_film_k=t_film_k)))
    return out


def bundle_has_currents(bundle):
    """True when EVERY member states a load current.

    ⚠ Deliberately all-or-nothing. A bundle where some members are loaded and
    others are blank is an incomplete answer, not a mixed one, and quietly
    giving the blanks a default flux would put an invented heat load beside
    measured ones — indistinguishable in the result.
    """
    members = list(getattr(bundle, "members", []) or [])
    if not members:
        return False
    return all(float(getattr(m, "current_a", 0.0) or 0.0) > 0
               for m in members)


def centres_from_bundle(bundle):
    """(centres, d_cable) from a bundle, for the UNIFORM path only.

    ⚠ Still raises on MIXED diameters, and deliberately: its contract is one
    diameter and a caller holding that contract must not be handed a bundle it
    cannot describe. The mixed path is :func:`cables_from_bundle` plus
    :func:`solve_mixed_bundle_factor`.
    """
    cables = cables_from_bundle(bundle)
    ds = sorted({round(d, 9) for _x, _y, d in cables})
    if len(ds) > 1:
        raise ValueError(
            "This bundle mixes cable diameters (%s mm), so it has no single "
            "diameter to build Nu_D on. Solve it with "
            "solve_mixed_bundle_factor(), which gives each size its own patch "
            "and its own factor."
            % ", ".join("%.4g" % (1000.0 * d) for d in ds))
    return [(x, y) for x, y, _d in cables], ds[0]


def _enclosure_for(centres, d_cable, clearance_ratio):
    """A square enclosure sized from the bundle's own extent.

    ⚠ Enclosure size is a REAL parameter, not packaging: measured, shrinking a
    0.40 m box to 0.20 m around one 20 mm cable cost 3 % of h. Defaulting it
    silently would bury a physical choice, so the ratio is explicit and the
    value lands in the provenance.

    ``centres`` may be ``(x, y)`` with a scalar ``d_cable``, or ``(x, y, d)``
    with ``d_cable`` ignored — the reach is then taken per cable, because on a
    mixed bundle the outermost centre is not always the one that reaches
    furthest.
    """
    if clearance_ratio <= 1.0:
        raise ValueError("clearance ratio must exceed 1 (it multiplies the "
                         "bundle's own extent)")
    reach = max(math.hypot(c[0], c[1])
                + (c[2] if len(c) > 2 else d_cable) / 2.0 for c in centres)
    return 2.0 * reach * float(clearance_ratio)


def solve_bundle_factor(centres, d_cable, box_w=None, box_h=None,
                        clearance_ratio=5.0, gradient=400.0, runner=None,
                        case_factory=None, case_dir=None,
                        joule_w_per_m=None, t_film_k=315.0, **case_kw):
    """Solve the arrangement and return its :class:`BundleFactor`.

    Pass ``joule_w_per_m`` to drive the wall flux from the cable's ACTUAL I²R
    loss instead of a typed gradient — the EM -> thermal coupling. It overrides
    ``gradient`` and the provenance records which was used, because "solved at
    400 K/m" and "solved at this cable's 5.3 W/m" are different claims and a
    reader must be able to tell them apart.

    ``runner`` / ``case_factory`` are injectable so the offline gate can drive
    this with a stub — the arithmetic and the refusals are testable without a
    solver, and only the physics needs one.
    """
    if not centres:
        raise ValueError("no cable centres to solve")
    if d_cable <= 0:
        raise ValueError("cable diameter must be positive")
    driven_by = "gradient %.4g K/m" % gradient
    if joule_w_per_m is not None:
        gradient = gradient_from_joule(joule_w_per_m, d_cable,
                                       t_film_k=t_film_k)
        driven_by = ("Joule %.4g W/m -> gradient %.4g K/m"
                     % (joule_w_per_m, gradient))
    if box_w is None or box_h is None:
        side = _enclosure_for(centres, d_cable, clearance_ratio)
        box_w = box_w or side
        box_h = box_h or side

    if runner is None or case_factory is None:          # pragma: no cover
        from emstudio.solvers.openfoam import BundleCase as _BC
        from emstudio.solvers.openfoam import run_bundle as _run
        case_factory = case_factory or _BC
        runner = runner or _run
    if case_dir is None:
        import tempfile
        case_dir = tempfile.mkdtemp(prefix="emstudio-bundlefactor-")

    case = case_factory(centres=list(centres), d_cable=d_cable,
                        box_w=box_w, box_h=box_h, gradient=gradient, **case_kw)
    report, result = runner(case_dir, case)
    key = geometry_key(centres, d_cable, box_w, box_h)
    if not report.get("ok") or result is None:
        raise ValueError(
            "the convection solve did not complete (%s); no factor was "
            "produced — a failed solve must not fall back to a plausible "
            "number" % (report.get("failed_at") or report.get("error") or
                        "unknown step"))

    factor = _factor_from(result, d_cable, len(centres),
                          "%s | %s" % (key, driven_by), report)
    factor.case_dir = case_dir
    return factor


def _factor_from(result, d_cable, n_cables, geometry, report,
                 gradient=0.0, patch=""):
    """Nu_solved / Churchill-Chu(Ra_resulting), with the same refusals.

    Shared by the uniform and the per-group paths so a mixed bundle's factors
    are formed by exactly the expression a uniform one's is — two copies would
    eventually disagree, and the disagreement would be invisible.

    ``gradient``/``patch`` identify the group on a mixed bundle. They default
    to empty because a uniform bundle has nothing to disambiguate, which keeps
    the single-diameter path's result byte-comparable with what it returned
    before groups existed.
    """
    ra = result.ra_d
    if ra <= 0:
        raise ValueError("the solve reported no Rayleigh number; without it "
                         "the correlation cannot be evaluated at the right "
                         "operating point")
    nu_corr = nu_churchill_chu(ra, PR_AIR)
    out = BundleFactor(
        factor=result.nu_d / nu_corr, nu_solved=result.nu_d,
        nu_correlation=nu_corr, ra_d=ra, d_cable=d_cable,
        n_cables=n_cables, gradient=float(gradient), patch=str(patch),
        converged=bool(report.get("converged")),
        drift=report.get("nu_drift", float("nan")), geometry=geometry)
    if not out.converged and not (out.drift == out.drift and out.drift < 5e-3):
        out.warnings.append(
            "this factor came from a solve that neither converged nor showed "
            "a settled Nusselt number — treat it as provisional")
    if out.factor > 1.0:
        out.warnings.append(
            "the solved factor exceeds 1, i.e. this arrangement sheds heat "
            "BETTER than an isolated cable in still air. That needs forced "
            "flow to be physical; check the enclosure size and the boundary "
            "conditions before using it")
    return out


def _per_cable_gradients(cables, gradient, joule_w_per_m, t_film_k,
                         explicit=None):
    """(gradients, description) for ``[(x, y, d)]`` — the flux each cable sees.

    ``explicit`` is a per-cable gradient list taken straight from 4-tuple
    input and wins over everything: the caller has already said what each
    cable dissipates.

    Otherwise ``joule_w_per_m`` may be ``None`` (use the typed gradient on
    every cable), a scalar (every cable dissipates the SAME loss per metre, so
    the thinner one sees the higher flux density), or one value per cable.

    ⚠ A scalar GRADIENT on a mixed bundle is equal flux DENSITY, which means
    the fat cable is dissipating proportionally more W/m. That is a real case
    but rarely the intended one, so the description says which was used and
    the provenance carries it.
    """
    n = len(cables)
    if explicit is not None:
        if joule_w_per_m is not None:
            raise ValueError(
                "per-cable gradients were given in the cable list AND a "
                "joule_w_per_m; they set the same thing and there is no "
                "defensible order of precedence. Pass one or the other")
        lo, hi = min(explicit), max(explicit)
        return list(explicit), ("gradient %.4g K/m on every cable" % lo
                                if lo == hi else
                                "per-cable gradient %.4g..%.4g K/m" % (lo, hi))
    if joule_w_per_m is None:
        return [float(gradient)] * n, "gradient %.4g K/m on every size" % gradient
    scalar = not hasattr(joule_w_per_m, "__len__")
    qs = ([float(joule_w_per_m)] * n if scalar
          else [float(q) for q in joule_w_per_m])
    if len(qs) != n:
        raise ValueError(
            "joule_w_per_m has %d entries for %d cables; give one loss per "
            "cable or a single value for all of them" % (len(qs), n))
    grads = [gradient_from_joule(q, c[2], t_film_k=t_film_k)
             for q, c in zip(qs, cables)]
    if scalar:
        return grads, ("Joule %.4g W/m on every cable -> %.4g..%.4g K/m"
                       % (qs[0], min(grads), max(grads)))
    return grads, ("Joule %.4g..%.4g W/m per cable -> %.4g..%.4g K/m"
                   % (min(qs), max(qs), min(grads), max(grads)))


def solve_mixed_bundle_factor(cables, box_w=None, box_h=None,
                              clearance_ratio=5.0, gradient=400.0, runner=None,
                              case_factory=None, case_dir=None,
                              joule_w_per_m=None, t_film_k=315.0, **case_kw):
    """Solve a bundle of unlike cables and return a :class:`MixedBundleFactor`.

    ``cables`` is ``[(x, y, d)]`` in metres — :func:`cables_from_bundle` gets
    it straight from the Cable Designer's own packing.

    Every size is solved in ONE case, sharing the enclosure, because that is
    the physics: the sizes heat each other, and solving each alone would
    measure a different problem and then quietly call it this one.

    ⚠ A UNIFORM set is allowed and returns a one-entry result. It runs the
    identical case the single-diameter path writes, so the two agree by
    construction rather than by coincidence.
    """
    if not cables:
        raise ValueError("no cables to solve")
    # ⚠ (x, y, d) or (x, y, d, gradient) — the SAME two shapes BundleCase
    # takes, so a caller does not have to learn a second convention to say
    # that two same-size cables carry different losses.
    explicit, norm = [], []
    for c in cables:
        if len(c) == 4:
            norm.append((float(c[0]), float(c[1]), float(c[2])))
            explicit.append(float(c[3]))
        elif len(c) == 3:
            norm.append((float(c[0]), float(c[1]), float(c[2])))
        else:
            raise ValueError("a cable is (x, y, diameter) or "
                             "(x, y, diameter, gradient); got %d values"
                             % len(c))
    if explicit and len(explicit) != len(norm):
        raise ValueError(
            "some cables carry a gradient and some do not; give every cable "
            "one or none, because a default silently applied to half a bundle "
            "is worse than no default")
    cables = norm
    for _x, _y, d in cables:
        if d <= 0:
            raise ValueError("cable diameter must be positive")
    grads, driven_by = _per_cable_gradients(cables, gradient, joule_w_per_m,
                                            t_film_k,
                                            explicit=explicit or None)
    if box_w is None or box_h is None:
        side = _enclosure_for(cables, 0.0, clearance_ratio)
        box_w = box_w or side
        box_h = box_h or side

    if runner is None or case_factory is None:          # pragma: no cover
        from emstudio.solvers.openfoam import BundleCase as _BC
        from emstudio.solvers.openfoam import run_bundle as _run
        case_factory = case_factory or _BC
        runner = runner or _run
    if case_dir is None:
        import tempfile
        case_dir = tempfile.mkdtemp(prefix="emstudio-mixedfactor-")

    case = case_factory(cables=[(x, y, d, g)
                                for (x, y, d), g in zip(cables, grads)],
                        box_w=box_w, box_h=box_h, gradient=gradient, **case_kw)
    report, result = runner(case_dir, case)
    # ⚠ The key is built from the RESOLVED gradients, not the raw input, so a
    # Joule-driven solve and a typed-gradient one that happen to produce the
    # same fluxes share a cached factor — which is correct, they solved the
    # same case — while any change in who carries what stales it.
    key = cables_key([(x, y, d, g) for (x, y, d), g in zip(cables, grads)],
                     box_w, box_h)
    if not report.get("ok") or result is None:
        raise ValueError(
            "the convection solve did not complete (%s); no factor was "
            "produced — a failed solve must not fall back to a plausible "
            "number" % (report.get("failed_at") or report.get("error") or
                        "unknown step"))

    geometry = "%s | %s" % (key, driven_by)
    out = MixedBundleFactor(
        geometry=geometry, converged=bool(report.get("converged")),
        drift=report.get("nu_drift", float("nan")), case_dir=case_dir)
    # A uniform set comes back as a plain BundleNusselt, exactly as it always
    # did; a mixed one carries a reading per patch. ⚠ The key is the PATCH, not
    # the diameter: one diameter can carry several groups when same-size cables
    # run at different losses, and keying by size dropped one of them silently
    # until this was fixed.
    per_patch = getattr(result, "by_patch", None)
    if per_patch is None:
        readings = [("cables", round(cables[0][2], 12), grads[0], result)]
    else:
        diam = getattr(result, "diameter", {})
        grad_of = getattr(result, "gradient", {})
        readings = [(patch, round(float(diam.get(patch, 0.0)), 12),
                     float(grad_of.get(patch, 0.0)), res)
                    for patch, res in per_patch.items()]
    for patch, d, grad, res in readings:
        n = sum(1 for (x, y, dc), g in zip(cables, grads)
                if abs(dc - d) <= 1e-9 and abs(g - grad) <= 1e-9)
        out.by_group[patch] = _factor_from(res, d, n, geometry, report,
                                           gradient=grad, patch=patch)
    for patch, f in out.by_group.items():
        for w in f.warnings:
            note = "%.4g mm @ %.4g K/m: %s" % (1000.0 * f.d_cable,
                                               f.gradient, w)
            if note not in out.warnings:
                out.warnings.append(note)
    if len(out.by_group) > 1 and out.spread_pct > 5.0:
        out.warnings.append(
            "the groups' factors differ by %.1f %%, so ONE factor cannot "
            "describe this bundle — rate each cable with its own"
            % out.spread_pct)
    # ⚠ Same size, different loss is a REAL arrangement and it is now solved
    # rather than refused — but it is also the case a reader is most likely to
    # collapse back into "the 20 mm factor", so say it out loud.
    dupes = sorted({f.d_cable for f in out.by_group.values()
                    if sum(1 for g in out.by_group.values()
                           if g.d_cable == f.d_cable) > 1})
    for d in dupes:
        same = [f for f in out.by_group.values() if f.d_cable == d]
        out.warnings.append(
            "%.4g mm carries %d groups on different wall fluxes (%s K/m -> "
            "factors %s). They are the same SIZE and not the same cable "
            "thermally; do not quote one of them as \"the %.4g mm factor\""
            % (1000.0 * d, len(same),
               ", ".join("%.4g" % f.gradient for f in same),
               ", ".join("%.4f" % f.factor for f in same), 1000.0 * d))
    return out
