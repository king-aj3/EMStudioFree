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

⚠ **Mixed DIAMETERS, not mixed LOADING.** The result is keyed by size, so two
surfaces of the same diameter on different wall fluxes cannot be told apart by
it and the solve is REFUSED rather than silently dropping one. The case writer
below it handles that split correctly — cables of one size at different fluxes
really are different patches — so this is a limit of the per-size factor, and
lifting it means keying the result by patch, not re-meshing anything.

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
    converged: bool = False
    drift: float = float("nan")
    geometry: str = ""
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
    """One :class:`BundleFactor` per cable SIZE, from a single solve.

    The sizes were solved TOGETHER — they share an enclosure and heat each
    other, which is the whole reason a per-size factor is not the same as
    solving each size in its own bundle.
    """

    by_size: dict = _field(default_factory=dict)      # d_cable (m) -> BundleFactor
    geometry: str = ""
    converged: bool = False
    drift: float = float("nan")
    warnings: list = _field(default_factory=list)

    @property
    def sizes(self):
        """Diameters in metres, largest first."""
        return sorted(self.by_size, reverse=True)

    @property
    def factor(self):
        raise ValueError(
            "this bundle mixes %d cable sizes and has %d factors, not one: "
            "%s. Ask for the size you are rating with factor_for(d), or take "
            "`.worst` if you must apply a single conservative number."
            % (len(self.by_size), len(self.by_size),
               ", ".join("%.4g mm -> %.4f" % (1000.0 * d, f.factor)
                         for d, f in sorted(self.by_size.items(),
                                            reverse=True))))

    def factor_for(self, d_cable, tol=1e-9):
        """The factor for the size being rated. Refuses a size not solved.

        ⚠ Deliberately not nearest-match. Interpolating between solved sizes
        would hand back a factor for a cable that was never in the enclosure,
        and it would look exactly like one that was.
        """
        for d, f in self.by_size.items():
            if abs(d - float(d_cable)) <= tol:
                return f
        raise ValueError(
            "no factor was solved for a %.4g mm cable; this bundle carries %s"
            % (1000.0 * float(d_cable),
               ", ".join("%.4g mm" % (1000.0 * d) for d in self.sizes)))

    @property
    def worst(self):
        """The most pessimistic size's factor — for a caller needing ONE.

        ⚠ This is a stated conservatism, not the bundle's factor. Applying it
        to a size that solved better under-rates that cable; applying anything
        else to the worst size over-rates it, which is the unsafe direction.
        """
        return min(self.by_size.values(), key=lambda f: f.factor)

    @property
    def spread_pct(self):
        """How far apart the sizes' factors are, as a percentage of the worst.

        Small means one number would do; large means the sizes genuinely cool
        differently and a single factor throws that away.
        """
        vals = [f.factor for f in self.by_size.values()]
        if not vals or min(vals) <= 0:
            return float("nan")
        return 100.0 * (max(vals) - min(vals)) / min(vals)

    @property
    def provenance(self):
        state = "converged" if self.converged else "NOT CONVERGED"
        drift = ("drift %.1e" % self.drift) if self.drift == self.drift \
            else "drift unknown"
        return ("OpenFOAM mixed bundle %s (%s, %s): %s"
                % (self.geometry, state, drift,
                   "; ".join(
                       "%.4g mm -> factor %.4f (Nu %.4f vs Churchill-Chu "
                       "%.4f at Ra %.4g)"
                       % (1000.0 * d, f.factor, f.nu_solved, f.nu_correlation,
                          f.ra_d)
                       for d, f in sorted(self.by_size.items(), reverse=True))))


def geometry_key(centres, d_cable, box_w, box_h):
    """A stable descriptor of what a factor was solved for.

    Used to notice that the design moved out from under a cached factor —
    confinement and spacing are precisely what the factor measures, so it does
    not carry across a geometry change.
    """
    pts = ",".join("%.6g:%.6g" % (x, y) for x, y in sorted(centres))
    return "d%.6g/box%.6gx%.6g/[%s]" % (d_cable, box_w, box_h, pts)


def cables_key(cables, box_w, box_h):
    """Geometry key for a possibly-mixed set of ``(x, y, d)`` cables.

    ⚠ A UNIFORM set produces the byte-identical string :func:`geometry_key`
    always produced, so adding mixed support does not silently stale every
    factor already cached in a user's document.
    """
    ds = {round(float(d), 12) for _x, _y, d in cables}
    if len(ds) == 1:
        return geometry_key([(x, y) for x, y, _d in cables], ds.pop(),
                            box_w, box_h)
    pts = ",".join("%.6g:%.6g:%.6g" % (d, x, y)
                   for d, x, y in sorted((d, x, y) for x, y, d in cables))
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

    return _factor_from(result, d_cable, len(centres),
                        "%s | %s" % (key, driven_by), report)


def _factor_from(result, d_cable, n_cables, geometry, report):
    """Nu_solved / Churchill-Chu(Ra_resulting), with the same refusals.

    Shared by the uniform and the per-size paths so a mixed bundle's factors
    are formed by exactly the expression a uniform one's is — two copies would
    eventually disagree, and the disagreement would be invisible.
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
        n_cables=n_cables, converged=bool(report.get("converged")),
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


def _per_cable_gradients(cables, gradient, joule_w_per_m, t_film_k):
    """(gradients, description) for ``[(x, y, d)]`` — the flux each cable sees.

    ``joule_w_per_m`` may be ``None`` (use the typed gradient on every cable),
    a scalar (every cable dissipates the SAME loss per metre, so the thinner
    one sees the higher flux density), or one value per cable.

    ⚠ A scalar GRADIENT on a mixed bundle is equal flux DENSITY, which means
    the fat cable is dissipating proportionally more W/m. That is a real case
    but rarely the intended one, so the description says which was used and
    the provenance carries it.
    """
    n = len(cables)
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
    cables = [(float(x), float(y), float(d)) for x, y, d in cables]
    for _x, _y, d in cables:
        if d <= 0:
            raise ValueError("cable diameter must be positive")
    grads, driven_by = _per_cable_gradients(cables, gradient, joule_w_per_m,
                                            t_film_k)
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
    key = cables_key(cables, box_w, box_h)
    if not report.get("ok") or result is None:
        raise ValueError(
            "the convection solve did not complete (%s); no factor was "
            "produced — a failed solve must not fall back to a plausible "
            "number" % (report.get("failed_at") or report.get("error") or
                        "unknown step"))

    geometry = "%s | %s" % (key, driven_by)
    out = MixedBundleFactor(
        geometry=geometry, converged=bool(report.get("converged")),
        drift=report.get("nu_drift", float("nan")))
    # A uniform set comes back as a plain BundleNusselt, exactly as it always
    # did; a mixed one carries a reading per patch.
    per_patch = getattr(result, "by_patch", None)
    if per_patch is None:
        counts = {round(cables[0][2], 12): len(cables)}
        readings = {round(cables[0][2], 12): result}
    else:
        diam = getattr(result, "diameter", {})
        readings, counts = {}, {}
        for patch, res in per_patch.items():
            d = round(float(diam.get(patch, 0.0)), 12)
            # ⚠ THIS RESULT IS KEYED BY SIZE, so two patches of the SAME
            # diameter would collide and one would be silently dropped. The
            # case writer supports that split — cables of one size on
            # different fluxes are legitimately different patches — but
            # "mixed loading within a size" is a second axis this factor API
            # does not model, and dropping a group quietly is exactly the
            # class of failure this module exists to avoid.
            if d in readings:
                raise ValueError(
                    "this solve produced two surfaces of the same %.4g mm "
                    "diameter (different wall fluxes), and a per-SIZE factor "
                    "cannot key them apart. Mixed DIAMETERS are supported; "
                    "mixed LOADING within one diameter is not. Give the "
                    "cables of each size the same loss, or solve the "
                    "differently-loaded ones as their own bundle."
                    % (1000.0 * d))
            readings[d] = res
            counts[d] = sum(1 for c in cables if abs(c[2] - d) <= 1e-9)
    for d, res in readings.items():
        out.by_size[d] = _factor_from(res, d, counts.get(d, 0), geometry,
                                      report)
    for d, f in out.by_size.items():
        for w in f.warnings:
            note = "%.4g mm: %s" % (1000.0 * d, w)
            if note not in out.warnings:
                out.warnings.append(note)
    if len(out.by_size) > 1 and out.spread_pct > 5.0:
        out.warnings.append(
            "the sizes' factors differ by %.1f %%, so ONE factor cannot "
            "describe this bundle — rate each size with its own"
            % out.spread_pct)
    return out
