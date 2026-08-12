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

⚠ **Uniform cable diameters only, and it REFUSES rather than averaging.** Nu_D
is built on a diameter; a bundle of mixed sizes has no single D, so a mean
would be a number with no defensible definition. Mixed bundles need per-cable
factors, which is not built.

⚠ **This runs a CFD solve — minutes, not milliseconds.** It must never be
called from a property edit or an interactive redraw. `solve_steady` bisects
and calls `surface_h` ~80 times per answer; the factor is a cached scalar for
exactly that reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as _field

from emstudio.wire.thermal import nu_churchill_chu

__all__ = ["BundleFactor", "geometry_key", "centres_from_bundle",
           "solve_bundle_factor"]

PR_AIR = 0.71


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


def geometry_key(centres, d_cable, box_w, box_h):
    """A stable descriptor of what a factor was solved for.

    Used to notice that the design moved out from under a cached factor —
    confinement and spacing are precisely what the factor measures, so it does
    not carry across a geometry change.
    """
    pts = ",".join("%.6g:%.6g" % (x, y) for x, y in sorted(centres))
    return "d%.6g/box%.6gx%.6g/[%s]" % (d_cable, box_w, box_h, pts)


def centres_from_bundle(bundle):
    """(centres, d_cable) from an :class:`emstudio.wire.bundle.Bundle`.

    The Cable Designer has already packed the bundle, so the CFD case consumes
    that geometry rather than asking the user to restate it.

    ⚠ Raises on MIXED diameters instead of averaging them — see the module
    note. Silently substituting a mean is how a number with no definition ends
    up in a report.
    """
    placed, _r_enc = bundle.pack()
    if not placed:
        raise ValueError("this bundle has no members to solve")
    radii = sorted({round(r, 9) for _x, _y, r, _m in placed})
    if len(radii) > 1:
        raise ValueError(
            "This bundle mixes cable diameters (%s mm). A bundle factor is "
            "defined against ONE diameter — Nu_D is built on it — so averaging "
            "unlike cables would produce a Nusselt number with no defensible "
            "definition, and per-cable factors are not implemented.\n\n"
            "What you can do: set the members to a single diameter to solve "
            "this arrangement, or solve each size as its own bundle and apply "
            "the factors separately. The NEC 310.15(C)(1) adjustment remains "
            "available for a mixed install and is the correct fallback."
            % ", ".join("%.4g" % (2000.0 * r) for r in radii))
    return [(x, y) for x, y, _r, _m in placed], 2.0 * radii[0]


def _enclosure_for(centres, d_cable, clearance_ratio):
    """A square enclosure sized from the bundle's own extent.

    ⚠ Enclosure size is a REAL parameter, not packaging: measured, shrinking a
    0.40 m box to 0.20 m around one 20 mm cable cost 3 % of h. Defaulting it
    silently would bury a physical choice, so the ratio is explicit and the
    value lands in the provenance.
    """
    if clearance_ratio <= 1.0:
        raise ValueError("clearance ratio must exceed 1 (it multiplies the "
                         "bundle's own extent)")
    reach = max(math.hypot(x, y) for x, y in centres) + d_cable / 2.0
    return 2.0 * reach * float(clearance_ratio)


def solve_bundle_factor(centres, d_cable, box_w=None, box_h=None,
                        clearance_ratio=5.0, gradient=400.0, runner=None,
                        case_factory=None, case_dir=None, **case_kw):
    """Solve the arrangement and return its :class:`BundleFactor`.

    ``runner`` / ``case_factory`` are injectable so the offline gate can drive
    this with a stub — the arithmetic and the refusals are testable without a
    solver, and only the physics needs one.
    """
    if not centres:
        raise ValueError("no cable centres to solve")
    if d_cable <= 0:
        raise ValueError("cable diameter must be positive")
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

    ra = result.ra_d
    if ra <= 0:
        raise ValueError("the solve reported no Rayleigh number; without it "
                         "the correlation cannot be evaluated at the right "
                         "operating point")
    nu_corr = nu_churchill_chu(ra, PR_AIR)
    out = BundleFactor(
        factor=result.nu_d / nu_corr, nu_solved=result.nu_d,
        nu_correlation=nu_corr, ra_d=ra, d_cable=d_cable,
        n_cables=len(centres), converged=bool(report.get("converged")),
        drift=report.get("nu_drift", float("nan")), geometry=key)
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
