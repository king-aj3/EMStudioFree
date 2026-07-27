# SPDX-License-Identifier: LGPL-2.1-or-later
"""Per-strand current-sharing analysis (twist-quality metric).

Litz wire only works if every strand carries (nearly) the same current — that is the
entire purpose of transposition, and the reason Type 2/3 cabled constructions exist.
Imperfect twisting lets outer/inner strands see different flux, driving circulating
currents that quietly destroy the litz advantage.

Method: FastHenry with one port per strand gives the full N x N impedance matrix
Z(f). Paralleling the strands (equal voltage V across all) yields the strand
currents I = Y * 1V with Y = Z^-1. The spread of |I_k| is the twist-quality metric:

    imbalance(f) = max|I_k| / min|I_k|      (1.0 = perfect sharing)
    spread(f)    = std|I_k| / mean|I_k|     (0.0 = perfect sharing)
"""

from __future__ import annotations

import numpy as np

from emstudio.solvers.fasthenry.parser import parse_zc_matrix
from emstudio.solvers.fasthenry.runner import run_wire_paths  # noqa: F401 (re-export convenience)


def strand_currents(z_matrix):
    """Per-strand complex currents for strands paralleled across 1 V."""
    z = np.asarray(z_matrix, dtype=complex)
    y = np.linalg.inv(z)
    return y @ np.ones(z.shape[0], dtype=complex)


def sharing_metrics(z_matrix):
    """(imbalance_ratio, relative_spread, |I_k| normalized to mean)."""
    i = np.abs(strand_currents(z_matrix))
    mean = float(i.mean())
    return float(i.max() / i.min()), float(i.std() / mean), (i / mean).tolist()


def grouped_metrics(z_matrix, groups):
    """Aggregated current sharing per GROUP (bundle/cable) — the EMStudio-wide view.

    Per AJ's rescope: per-strand detail is too much; engineering questions are asked
    at the bundle/cable level ("does each Type-4 carry its share?", "do my two
    paralleled cables split evenly?").

    :param groups: list of index-lists into the port ordering, e.g.
                   [[0,1,2],[3,4,5]] = two bundles of three conductors.
    :returns: dict with per-group complex current share (of total), the
              group imbalance ratio max/min |I_group| normalized by the groups'
              conductor counts (1.0 = every group carries its proportional share),
              and the relative spread.
    """
    import numpy as np

    currents = strand_currents(z_matrix)
    total = currents.sum()
    group_i = np.array([currents[list(g)].sum() for g in groups])
    share = np.abs(group_i) / abs(total)
    counts = np.array([len(g) for g in groups], dtype=float)
    expected = counts / counts.sum()
    norm = share / expected  # 1.0 for every group = proportional sharing
    return {
        "share": share.tolist(),
        "expected": expected.tolist(),
        "normalized": norm.tolist(),
        "imbalance": float(norm.max() / norm.min()),
        "spread": float(norm.std() / norm.mean()),
    }


def bundle_paths_for_construction(construction, length_m, points_per_turn=8):
    """Equivalent-conductor paths of the FINAL cabling operation's members.

    Each outermost member (e.g. each Type-4 in a Type 6) is represented as ONE
    round conductor of its wrapped radius, following its helix at the final lay —
    the right granularity for per-bundle sharing (strand-level at 18k strands is
    neither computable nor useful).

    Returns (paths, member_radius_m).
    """
    import math

    con = construction
    if not con.ops:
        raise ValueError("construction has no cabling operations")
    op = con.ops[-1]
    radii = [con.strand_radius_m] + con.level_radii_m()
    r_member = radii[-2] + (op.member_wrap_m or 0.0)
    ring_r = (op.core_m / 2.0 + r_member) if op.core_m > 0 else max(
        r_member, r_member / math.sin(math.pi / max(op.count, 3)))
    lay = op.lay_m
    turns = length_m / lay if lay > 0 else 0.0
    n_pts = max(2, int(math.ceil(turns * points_per_turn)) + 1)
    paths = []
    for k in range(op.count):
        base = 2.0 * math.pi * k / op.count
        pts = []
        for i in range(n_pts):
            z = length_m * i / (n_pts - 1)
            ang = base + (2.0 * math.pi * z / lay if lay > 0 else 0.0)
            pts.append((ring_r * math.cos(ang), ring_r * math.sin(ang), z))
        paths.append(pts)
    return paths, r_member


def analyze_construction(construction, length_m=None, fmin=1e4, fmax=1e6, ndec=1,
                         nhinc=5, workdir=None, line_callback=None):
    """Per-bundle current sharing of a litz construction's final cabling level.

    Models each outermost member as an equivalent conductor on its helix and runs
    the multi-port analysis; results are per-bundle (aggregation level: the
    construction's top-level members).
    """
    op = construction.ops[-1]
    if length_m is None:
        length_m = 2.0 * op.lay_m  # two full transposition cycles
    paths, r_member = bundle_paths_for_construction(construction, length_m)
    results = analyze_paths(paths, r_member, sigma_s_per_m=construction.sigma,
                            fmin=fmin, fmax=fmax, ndec=ndec, nhinc=nhinc,
                            workdir=workdir, line_callback=line_callback)
    for r in results:
        r["level"] = "final op ({0} members)".format(op.count)
    return results


def analyze_paths(wire_paths, radius_m, sigma_s_per_m=5.8e7,
                  fmin=1e4, fmax=1e6, ndec=1, nhinc=5,
                  workdir=None, line_callback=None):
    """Run the multi-port FastHenry analysis over a frequency sweep.

    Returns list of dicts: {freq, imbalance, spread, currents_norm}.
    """
    from emstudio.solvers.fasthenry.runner import run_parallel_sweep

    # one FastHenry process per frequency, fanned across all CPU cores
    freqs, mats, workdir = run_parallel_sweep(
        wire_paths, radius_m, sigma_s_per_m, fmin, fmax, ndec,
        nhinc, "per_path", workdir=workdir, line_callback=line_callback,
    )
    out = []
    for f, z in zip(freqs, mats):
        imbalance, spread, inorm = sharing_metrics(z)
        out.append({
            "freq": f, "imbalance": imbalance, "spread": spread,
            "currents_norm": inorm, "workdir": workdir,
        })
    return out
