# SPDX-License-Identifier: LGPL-2.1-or-later
"""Read an OpenFOAM field back and turn the cavity's wall gradient into Nusselt.

WHY THIS PARSES THE FIELD INSTEAD OF USING A FUNCTION OBJECT
-------------------------------------------------------------
A ``wallHeatFlux`` function object would be the obvious route, and it is the
one this project has already been burned by twice: Ubuntu's 1912 package
aborts on ANY function object with ``error in IOstream "sha1"``, and the abort
message points at nothing a reader would connect to a function object. A
capability probe exists precisely because that failure is invisible. Reading
the written ``T`` field needs no function-object machinery at all, so the
result path cannot inherit that fault.

THE GRADIENT, AND WHY IT IS EXACT WHERE IT MATTERS
---------------------------------------------------
``blockMesh`` numbers cells x-fastest, then y, then z. For an ``n x n x 1``
block the first ``n`` values are the bottom row, and every ``n``-th value from
index 0 is the column of cells against the hot wall. Those cell centres sit
``dx/2`` from the wall, so the wall-normal gradient is approximated as

    dT/dx|wall ~= (T_wall - T_firstcell) / (dx/2)

which is FIRST ORDER in general — and **exact in the conduction limit**, where
the profile is linear. That is deliberate: the gate's hard anchor is the
Ra -> 0 limit, where Nu is exactly 1 by construction, and a first-order
estimate reproduces it without error. At convective Ra the number carries the
usual near-wall discretisation error and is treated as indicative, not as a
benchmark claim.

    Nu = (L / dT) * <dT/dn>_hot wall

⚠ This is a Nusselt number normalised by the PURE-CONDUCTION solution across
the cavity, which is what makes Nu -> 1 the conduction limit. A Nu defined
against some other reference length is a different number with the same name.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field as _field

__all__ = ["NusseltResult", "read_internal_field", "nusselt_from_field",
           "latest_time_dir", "CylinderNusselt", "nusselt_cylinder_from_field",
           "BundleNusselt", "read_patch_values", "nusselt_from_patch",
           "WindForces", "forces_from_log"]

_NONUNIFORM = re.compile(r"internalField\s+nonuniform\s+List<scalar>\s*\n?\s*(\d+)\s*\(",
                         re.S)
_UNIFORM = re.compile(r"internalField\s+uniform\s+([-\deE.+]+)\s*;")


@dataclass
class NusseltResult:
    """Wall-averaged Nusselt number and the pieces it was built from."""

    nu_avg: float = 0.0              # hot wall
    nu_cold: float = 0.0             # cold wall — must match at steady state
    cells: int = 0
    dx: float = 0.0
    t_wall: float = 0.0
    t_first: tuple = ()
    warnings: list = _field(default_factory=list)

    @property
    def imbalance(self):
        """|Nu_hot - Nu_cold| / Nu_hot. Energy conservation, as a fraction.

        At steady state this is zero up to discretisation and convergence.
        A large value means the run has NOT converged, whatever its residuals
        said, so it is worth more than the residual print.
        """
        if not self.nu_avg:
            return float("inf")
        return abs(self.nu_avg - self.nu_cold) / abs(self.nu_avg)

    @property
    def conduction_limit(self):
        """How far from pure conduction this is. 1.0 = conduction exactly."""
        return self.nu_avg


def latest_time_dir(case_dir):
    """The highest-numbered time directory, or '' if the case never wrote one.

    ⚠ An empty return means the SOLVER PRODUCED NOTHING, which is a different
    failure from "the solver ran and the answer is wrong" — the caller must not
    collapse them, because a silently missing time directory reads as a zero
    result otherwise.
    """
    best, best_name = None, ""
    for name in os.listdir(case_dir):
        if not os.path.isdir(os.path.join(case_dir, name)):
            continue
        try:
            value = float(name)
        except ValueError:
            continue
        if value > 0 and (best is None or value > best):
            best, best_name = value, name
    return best_name


def read_internal_field(path):
    """Parse ``internalField`` out of an OpenFOAM scalar field file.

    Handles both the ``nonuniform List<scalar>`` a solve writes and the
    ``uniform`` form an untouched field keeps. Returns a list of floats.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    m = _NONUNIFORM.search(text)
    if m:
        count = int(m.group(1))
        start = m.end()
        end = text.index(")", start)
        values = [float(tok) for tok in text[start:end].split()]
        if len(values) != count:
            raise ValueError("field claims %d values but carries %d — the "
                             "file is truncated" % (count, len(values)))
        return values
    m = _UNIFORM.search(text)
    if m:
        raise ValueError("internalField is still 'uniform %s' — the solver "
                         "wrote no solution into this field" % m.group(1))
    raise ValueError("no internalField found in %s" % path)


def nusselt_from_field(values, cells, t_wall, t_cold, length=1.0):
    """Wall-averaged Nu on the hot wall from the raw cell values.

    ``values`` is the internal field in blockMesh cell order (x fastest).
    """
    n = int(cells)
    if n < 2:
        raise ValueError("need at least 2 cells per side")
    if len(values) != n * n:
        raise ValueError("expected %d cells for an %dx%d mesh, got %d"
                         % (n * n, n, n, len(values)))
    dt = t_wall - t_cold
    if dt == 0:
        raise ValueError("hot and cold walls are at the same temperature; "
                         "Nusselt number is undefined")
    dx = float(length) / n
    # column against the hot wall (x = 0) = every n-th value from index 0
    first = [values[row * n] for row in range(n)]
    # Nu = (L/dT) * mean( (T_wall - T_cell) / (dx/2) )
    grads = [(t_wall - t) / (dx / 2.0) for t in first]
    nu = (length / dt) * (sum(grads) / len(grads))

    # The COLD wall (x = L) is the last cell of each row. At steady state the
    # heat crossing it must equal the heat entering the hot wall, so the two
    # Nusselt numbers are the same number measured twice. This is a
    # conservation check, not a second opinion: a discretisation or ordering
    # mistake moves one and not the other.
    last = [values[row * n + (n - 1)] for row in range(n)]
    cold_grads = [(t - t_cold) / (dx / 2.0) for t in last]
    nu_cold = (length / dt) * (sum(cold_grads) / len(cold_grads))

    res = NusseltResult(nu_avg=nu, nu_cold=nu_cold, cells=n, dx=dx,
                        t_wall=t_wall, t_first=tuple(first))
    if nu < 0:
        res.warnings.append(
            "negative Nu — heat is flowing INTO the hot wall, so the wall "
            "temperatures or the field ordering are not what this assumed")
    return res


# ---------------------------------------------------------------------------
# The O-grid cylinder (see emstudio/solvers/openfoam/cylinder.py)
# ---------------------------------------------------------------------------

@dataclass
class CylinderNusselt:
    """Circumferentially-averaged Nu_D on the cylinder, and its workings."""

    nu_d: float = 0.0
    t_first: tuple = ()              # wall-adjacent cell temperatures
    first_cell_m: float = 0.0
    wall_cells: int = 0
    q_in_w_per_k: float = 0.0        # inner-wall heat rate / k, per unit length
    q_out_w_per_k: float = 0.0       # outer wall — annulus mode only, else 0
    warnings: list = _field(default_factory=list)

    @property
    def imbalance(self):
        """|q_in - q_out| / q_in across the annulus. Energy conservation.

        ⚠ Meaningful in ANNULUS mode only. In far-field mode there is no outer
        wall to balance against and this returns ``inf`` — deliberately, so a
        caller cannot read a reassuring zero off a check that was never made.
        The far-field mode's anchors are the correlation and domain-size
        convergence instead.
        """
        if not self.q_out_w_per_k or not self.q_in_w_per_k:
            return float("inf")
        return (abs(self.q_in_w_per_k - self.q_out_w_per_k)
                / abs(self.q_in_w_per_k))


def nusselt_cylinder_from_field(values, n_r, n_theta, t_wall, t_amb, d_m,
                                first_cell_m, last_cell_m=None, r_out=None):
    """Nu_D on the cylinder wall of the four-block O-grid.

    ``values`` is the internal field in blockMesh order. The mesh is four
    blocks of ``(n_r, n_theta, 1)``; blockMesh numbers cells x1-fastest WITHIN
    a block and blocks in declaration order, so

        global = block * n_r * n_theta + i_r + n_r * i_theta

    and the wall-adjacent cells are ``i_r = 0``. That indexing is the one real
    assumption in this function, which is why the gate proves it on a synthetic
    conduction field rather than asserting it in a comment.

        Nu_D = D / dT * < (T_wall - T_first) / (first_cell/2) >

    FIRST ORDER, and — unlike the cavity's linear profile — **not exact even in
    the conduction limit**, because conduction across an annulus is
    logarithmic. The gate handles that by predicting what this estimator must
    return for an exact log field and checking the refinement converges on
    2/ln(r_o/r_i), which is a stronger statement than a single tolerance.

    Pass ``last_cell_m`` and ``r_out`` to also measure the OUTER wall, which
    turns on the annulus energy balance. ⚠ The two gradients are compared
    RADIUS-WEIGHTED (q' = k r dT/dr per radian): the raw gradients differ by
    the radius ratio even for a perfect solve, so an unweighted comparison
    would fail on a correct answer.
    """
    n_r, n_theta = int(n_r), int(n_theta)
    if n_r < 2 or n_theta < 1:
        raise ValueError("need at least 2 radial and 1 circumferential cell")
    expect = 4 * n_r * n_theta
    if len(values) != expect:
        raise ValueError("expected %d cells for a 4x(%d x %d) O-grid, got %d"
                         % (expect, n_r, n_theta, len(values)))
    dt = float(t_wall) - float(t_amb)
    if dt == 0:
        raise ValueError("wall and ambient are at the same temperature; "
                         "Nusselt number is undefined")
    if first_cell_m <= 0:
        raise ValueError("first cell height must be positive")

    first = [values[b * n_r * n_theta + n_r * j]
             for b in range(4) for j in range(n_theta)]
    grads = [(float(t_wall) - t) / (first_cell_m / 2.0) for t in first]
    mean_grad = sum(grads) / len(grads)
    nu_d = float(d_m) / dt * mean_grad

    r_in = float(d_m) / 2.0
    q_in = r_in * mean_grad          # per radian, per unit length, divided by k
    q_out = 0.0
    if last_cell_m and r_out:
        last = [values[b * n_r * n_theta + n_r * j + (n_r - 1)]
                for b in range(4) for j in range(n_theta)]
        og = [(t - float(t_amb)) / (float(last_cell_m) / 2.0) for t in last]
        q_out = float(r_out) * (sum(og) / len(og))

    res = CylinderNusselt(nu_d=nu_d, t_first=tuple(first),
                          first_cell_m=float(first_cell_m),
                          wall_cells=len(first), q_in_w_per_k=q_in,
                          q_out_w_per_k=q_out)
    if nu_d < 0:
        res.warnings.append(
            "negative Nu — heat is flowing INTO the cylinder, so the wall "
            "temperature or the cell ordering is not what this assumed")
    return res


# ---------------------------------------------------------------------------
# The bundle (see emstudio/solvers/openfoam/bundle.py)
# ---------------------------------------------------------------------------

_PATCH_NONUNIFORM = re.compile(
    r"value\s+nonuniform\s+List<scalar>\s*\n?\s*(\d+)\s*\(", re.S)
_PATCH_UNIFORM = re.compile(r"value\s+uniform\s+([-\deE.+]+)\s*;")


@dataclass
class BundleNusselt:
    """Nu_D on a flux-heated cable set, and the state it was read from."""

    nu_d: float = 0.0
    t_surface: float = 0.0           # mean over the patch faces
    t_min: float = 0.0
    t_max: float = 0.0
    faces: int = 0
    dt: float = 0.0
    ra_d: float = 0.0                # the Ra that RESULTED, not one requested
    warnings: list = _field(default_factory=list)

    @property
    def spread(self):
        """(t_max - t_min) / dt. How far from isothermal the surface is.

        ⚠ The mean below is UNWEIGHTED across patch faces. snappy's snapped
        faces are near-uniform in size so that is a good approximation, but it
        is an approximation: a large spread means face-area weighting would
        move the answer, and the number should not be used quantitatively
        without it.
        """
        if not self.dt:
            return float("inf")
        return (self.t_max - self.t_min) / abs(self.dt)


def read_patch_values(path, patch):
    """The ``value`` list OpenFOAM wrote for one patch of a scalar field.

    ⚠ A patch only HAS a written ``value`` if its boundary condition writes
    one. ``fixedGradient`` does NOT — it emits ``type`` and ``gradient`` and
    nothing else, so a result path built on it silently has nothing to read.
    ``mixed`` (valueFraction 0) is the same condition and does write ``value``.
    That is measured, not assumed, and it is why this raises rather than
    returning an empty list.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    m = re.search(r"^\s*%s\s*\n\s*\{(.*?)\n\s*\}" % re.escape(patch),
                  text, re.S | re.M)
    if not m:
        raise ValueError("patch %r is not in %s" % (patch, path))
    body = m.group(1)
    nu = _PATCH_NONUNIFORM.search(body)
    if nu:
        count = int(nu.group(1))
        start = nu.end()
        end = body.index(")", start)
        values = [float(tok) for tok in body[start:end].split()]
        if len(values) != count:
            raise ValueError("patch %r claims %d values but carries %d — the "
                             "file is truncated" % (patch, count, len(values)))
        return values
    un = _PATCH_UNIFORM.search(body)
    if un:
        return [float(un.group(1))]
    raise ValueError(
        "patch %r has no `value` entry — its boundary condition wrote none "
        "(fixedGradient does this; use mixed with valueFraction 0)" % patch)


def nusselt_from_patch(values, d_m, gradient, t_amb, nu=None, alpha=None,
                       g=9.81, t_ref=300.0):
    """Nu_D from a prescribed wall gradient and the resulting surface values.

        Nu_D = D * (dT/dn)_wall / (T_surface - T_ambient)

    Dimensionless, so no conductivity is needed — it cancels. Pass ``nu`` and
    ``alpha`` to also get the Ra that RESULTED from the solved dT; Ra is an
    output of this case, not an input.
    """
    if not values:
        raise ValueError("no patch values to average")
    if d_m <= 0:
        raise ValueError("cable diameter must be positive")
    if gradient == 0:
        raise ValueError("a zero wall gradient deposits no heat; Nu undefined")
    ts = sum(values) / len(values)
    dt = ts - float(t_amb)
    if dt == 0:
        raise ValueError("the surface sits at ambient; Nusselt number is "
                         "undefined")
    res = BundleNusselt(nu_d=float(d_m) * float(gradient) / dt, t_surface=ts,
                        t_min=min(values), t_max=max(values),
                        faces=len(values), dt=dt)
    if nu and alpha:
        res.ra_d = g * (1.0 / t_ref) * abs(dt) * float(d_m) ** 3 / (nu * alpha)
    if res.nu_d < 0:
        res.warnings.append(
            "negative Nu — the surface is COLDER than ambient, so the "
            "prescribed gradient sign or the ambient value is not what this "
            "assumed")
    return res


# ---------------------------------------------------------------------------
# Wind loading (see emstudio/solvers/openfoam/wind.py)
# ---------------------------------------------------------------------------

_FORCE_BLOCK = re.compile(
    r"Sum of forces\s*\n\s*Total\s*:\s*\(([^)]*)\)\s*\n"
    r"\s*Pressure\s*:\s*\(([^)]*)\)\s*\n\s*Viscous\s*:\s*\(([^)]*)\)")


@dataclass
class WindForces:
    """Force on the body, split the way the solver computed it."""

    total: tuple = (0.0, 0.0, 0.0)
    pressure: tuple = (0.0, 0.0, 0.0)
    viscous: tuple = (0.0, 0.0, 0.0)
    cd: float = 0.0
    cl: float = 0.0
    warnings: list = _field(default_factory=list)

    @property
    def split_exact(self):
        """pressure + viscous == total, componentwise. A conservation check
        on the function object's own arithmetic, free of any reference value."""
        return all(abs((p + v) - t) <= 1e-9 * max(1.0, abs(t))
                   for t, p, v in zip(self.total, self.pressure, self.viscous))

    @property
    def lift_to_drag(self):
        """|Cl|/|Cd|. For a symmetric body at zero incidence this must be ~0 —
        an EXACT expectation needing no citation, and the sharpest check
        available on whether the force integration is oriented correctly."""
        if not self.cd:
            return float("inf")
        return abs(self.cl) / abs(self.cd)


def forces_from_log(text, q_ref):
    """Parse the LAST force report out of a solver log.

    ⚠ Read from the LOG, not from ``postProcessing/forces``: measured on
    v2512, this function object reports to the log and writes no files under
    the configuration used here. Parsing the log is version-fragile, so the
    block is matched STRUCTURALLY (Total/Pressure/Viscous triplet) rather than
    by line offsets, and an unparsable log raises instead of returning zeros —
    a zero force is a physical claim and "could not read it" is not.
    """
    blocks = _FORCE_BLOCK.findall(text or "")
    if not blocks:
        raise ValueError(
            "no 'Sum of forces' block in the solver log — the forces function "
            "object did not report. Check it was constructed (the log names it "
            "at startup) and that the patch name matches.")
    if q_ref <= 0:
        raise ValueError("reference dynamic pressure must be positive")
    tot, pre, vis = [tuple(float(x) for x in b.split()) for b in blocks[-1]]
    res = WindForces(total=tot, pressure=pre, viscous=vis,
                     cd=tot[0] / q_ref, cl=tot[1] / q_ref)
    if not res.split_exact:
        res.warnings.append(
            "pressure + viscous does not equal the total force — the log was "
            "misread or the function object reported inconsistently")
    if res.cd <= 0:
        res.warnings.append(
            "non-positive drag: the body is being pushed UPSTREAM, so the "
            "freestream direction or the force orientation is not what this "
            "assumed")
    return res
