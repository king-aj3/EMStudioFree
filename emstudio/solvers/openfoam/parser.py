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
           "latest_time_dir"]

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
