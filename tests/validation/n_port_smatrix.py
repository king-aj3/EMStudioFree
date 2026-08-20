# SPDX-License-Identifier: LGPL-2.1-or-later
"""FAST gate: the S-matrix chain works past TWO ports, end to end but solver-free.

WHY THREE PORTS AND NOT TWO. Everything below was written 2-port-first, and a
2-port fixture cannot fail most of these checks:

* a uniform 2-port is electrically symmetric, so S11 == S22 and S12 == S21 by
  physics — a transposed or column-swapped file is INVISIBLE in the values;
* the 2-port Touchstone layout is one line per frequency, so the line-breaking
  rule that only applies from 3 ports up is never exercised;
* the wall MFEM attribute is 4 for a 2-port mesh, which is also the constant
  ``WG_WALL_ATTR`` — so hard-coding the constant looks correct forever, right
  up to the 3-port mesh where 4 is PORT 3's attribute;
* and the excitation list ``[1, 2]`` is right for every 2-port and wrong for
  everything else.

Three is the smallest order that catches all four. The fixture is deliberately
ASYMMETRIC — S_ij carries the recognisable value ``i + j*1j``, so every one of
the nine terms is distinct and any transpose, swap or off-by-one shows up as a
wrong NUMBER rather than as a shape that still parses.

WHAT IS AND IS NOT PROVEN HERE. This gate needs no Palace, no openEMS and no
gmsh: it pins the mesh SCRIPT, the config SHAPE, the join and the file. What it
cannot prove is that Palace labels the columns of a 3-port solve the way the
parser expects — that needs a live 3-port solve on a machine with Palace, the
same way the 2-port claim was only believed after ``two_port_palace`` ran.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np                                            # noqa: E402

from emstudio.meshing import gmsh_brep                        # noqa: E402
from emstudio.meshing.gmsh_box import (                       # noqa: E402
    WG_VOLUME_ATTR, WG_WALL_ATTR, wg_port_attr, wg_wall_attr)
from emstudio.post.sparams import (                           # noqa: E402
    MAX_PAIRS_PER_LINE, SweepResult, merge_excitations)
from emstudio.solvers import estimate                         # noqa: E402
from emstudio.solvers.palace import runner as palace_runner   # noqa: E402
from emstudio.solvers.palace import writer                    # noqa: E402

FAILURES = []

N = 3                      # the fixture's order


def check(msg, ok):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        FAILURES.append(msg)


def _s(i, j):
    """The fixture's S_ij: distinct for every (i, j), and NOT symmetric."""
    return complex(i, j)


def _freq():
    return np.array([1.0e9, 2.0e9])


def _full_matrix():
    """The complete 3x3, as a {(to, from): array} map."""
    f = _freq()
    return {(i, j): np.array([_s(i, j)] * len(f))
            for i in range(1, N + 1) for j in range(1, N + 1)}


def _result(smat):
    f = _freq()
    s11 = smat[(1, 1)]
    z0 = 50.0
    zin = z0 * (1.0 + s11) / (1.0 - s11)
    return SweepResult(f, zin, z0=z0, s11=s11, meta={"backend": "gate"},
                       s_others={k: v for k, v in smat.items() if k != (1, 1)})


def _data_lines(path):
    return [l.rstrip("\n") for l in open(path, encoding="utf-8")
            if not l.startswith(("!", "#")) and l.strip()]


# -- a duck-typed analysis, so the estimator can be exercised FreeCAD-free ----
class _Port:
    EMStudioType = "EMStudio::LumpedPort"

    def __init__(self, number):
        self.PortNumber = number


class _Analysis:
    def __init__(self, n_ports, freq_points=11):
        self.Group = [_Port(k) for k in range(1, n_ports + 1)]
        self.FrequencyPoints = freq_points


class _Solver:
    def __init__(self, full, cells=10):
        self.FullSMatrix = full
        self.CellsPerWavelength = cells


def main():
    tmp = tempfile.mkdtemp()

    # == 1. MFEM attributes are DERIVED, and the old constant is now a trap ==
    attrs = [wg_port_attr(k) for k in range(1, N + 1)]
    check("port attributes are consecutive from the interior: %r" % (attrs,),
          attrs == [2, 3, 4])
    check("the 3-port wall attribute is past every port [%d]" % wg_wall_attr(N),
          wg_wall_attr(N) == 5 and wg_wall_attr(N) not in attrs)
    # This is the whole reason wg_wall_attr exists. If it ever stops being
    # true, the constant is safe again and this check has stopped mattering.
    check("...and the 2-port CONSTANT collides with port 3, which is the trap",
          WG_WALL_ATTR == wg_port_attr(N))
    check("2-port numbering is unchanged, so existing meshes still match",
          (wg_port_attr(1), wg_port_attr(2), wg_wall_attr(2)) == (2, 3, 4))
    check("every attribute is distinct from the interior's",
          WG_VOLUME_ATTR not in attrs + [wg_wall_attr(N)])

    # == 2. the mesh SCRIPT tags three port faces and keeps walls separate ===
    brep = os.path.join(tmp, "junction.brep")
    open(brep, "w", encoding="utf-8").write("(dummy: the geo writer only stats it)\n")
    geo = os.path.join(tmp, "junction.geo")
    # A T-junction: through-arm at both x ends, side arm at +y.
    faces = [(0, False), (0, True), (1, True)]
    gmsh_brep.write_geo_brep_driven(brep, geo, bbox_mm=(0, 0, 0, 40, 20, 10),
                                    ports=faces)
    src = open(geo, encoding="utf-8").read()
    for k in range(1, N + 1):
        check("geo declares Physical Surface port%d on attribute %d"
              % (k, wg_port_attr(k)),
              'Physical Surface("port%d", %d)' % (k, wg_port_attr(k)) in src)
    check("geo tags the walls with the DERIVED attribute, not the constant",
          'Physical Surface("walls", %d)' % wg_wall_attr(N) in src)
    check("...and never with %d, which is port 3's" % WG_WALL_ATTR,
          'Physical Surface("walls", %d)' % WG_WALL_ATTR not in src)
    check("every port is subtracted from the wall set (no face in two groups)",
          all("walls() -= port%d();" % k in src for k in range(1, N + 1)))
    # Compare the SELECTION BOXES, not the whole lines. `port1() = ...` and
    # `port2() = ...` differ in their left-hand side whatever they select, so a
    # line-wise comparison here reports three distinct slabs even when all
    # three query the SAME face. Measured: written that way, this check could
    # not fail, which is worse than not having it.
    boxes = [l.split("=", 1)[1].strip()
             for l in src.splitlines() if l.startswith("port")]
    check("the %d port slabs are DIFFERENT boxes (not one face tagged %dx)"
          % (N, N), len(boxes) == N and len(set(boxes)) == N)

    # the two spellings, and a refusal
    check("ports=None still means the historical two ends of `axis`",
          gmsh_brep.normalise_port_faces(None, 2) == [(2, False), (2, True)])
    check("an explicit 6-tuple box is passed through as given",
          gmsh_brep.normalise_port_faces([(0, 0, 0, 1, 1, 1)])
          == [(0.0, 0.0, 0.0, 1.0, 1.0, 1.0)])
    refused = False
    try:
        gmsh_brep.normalise_port_faces([(0, 1, 2)])
    except gmsh_brep.BrepMeshError:
        refused = True
    check("a port spec that is neither shape is REFUSED", refused)

    # == 3. the Palace config carries N ports, one driven =====================
    cfgs = {}
    for ep in range(1, N + 1):
        cfgs[ep] = writer.build_driven_config(
            "m.msh", 8.0, 12.0, 0.5, excite_port=ep,
            output="postpro_e%d" % ep, n_ports=N)
    wp = cfgs[1]["Boundaries"]["WavePort"]
    check("the config declares all %d ports" % N, len(wp) == N)
    check("...with Index 1..N in order", [p["Index"] for p in wp] == [1, 2, 3])
    check("...each on its own derived attribute",
          [p["Attributes"] for p in wp] == [[2], [3], [4]])
    check("PEC is the derived wall attribute, not the 2-port constant",
          cfgs[1]["Boundaries"]["PEC"]["Attributes"] == [wg_wall_attr(N)])
    for ep, cfg in cfgs.items():
        ports = cfg["Boundaries"]["WavePort"]
        driven = [p["Index"] for p in ports if "Excitation" in p]
        check("excitation %d drives exactly that port and no other" % ep,
              driven == [ep] and all(p["Excitation"] == p["Index"]
                                     for p in ports if "Excitation" in p))
    check("the %d runs write to %d DIFFERENT outputs" % (N, N),
          len({c["Problem"]["Output"] for c in cfgs.values()}) == N)

    # An unknown port used to clear every excitation and drive NOTHING, which
    # Palace solves happily. Only reachable once the list stopped being [1, 2].
    refused = False
    try:
        writer.set_excitation([{"Index": 1}, {"Index": 2}], 3)
    except ValueError as exc:
        refused = "cannot excite port 3" in str(exc)
    check("driving a port the config does not have is REFUSED, not ignored",
          refused)

    # == 4. the excitation list follows the mesh, not a literal ==============
    check("a full %d-port matrix drives every port" % N,
          palace_runner._excitation_list(N, True) == [1, 2, 3])
    check("...and it is NOT the old [1, 2]",
          palace_runner._excitation_list(N, True) != [1, 2])
    check("without a full matrix it is still one solve",
          palace_runner._excitation_list(N, False) == [1])

    # == 5. the merge joins N columns ========================================
    f = _freq()
    smat = _full_matrix()
    runs = [(f, {(i, j): smat[(i, j)] for i in range(1, N + 1)})
            for j in range(1, N + 1)]          # one run per EXCITED port j
    fr, merged = merge_excitations(runs)
    check("merging %d columns gives all %d terms" % (N, N * N),
          len(merged) == N * N)
    check("...with the frequency grid preserved", np.allclose(fr, f))
    check("...and every term kept its own value (nothing crossed over)",
          all(np.allclose(merged[(i, j)], _s(i, j))
              for i in range(1, N + 1) for j in range(1, N + 1)))

    # == 6. the file: order, layout, and a transpose it can actually see =====
    res = _result(merged)
    check("the joined result completes order %d" % N, res.max_complete_ports() == N)
    check("...with nothing missing", res.missing_s_terms(N) == [])

    p3 = os.path.join(tmp, "junction.s3p")
    check("it writes a %d-port Touchstone" % N, res.write_touchstone(p3) == N)
    lines = _data_lines(p3)
    check("one matrix ROW per line: %d lines for %d frequencies"
          % (len(lines), len(f)), len(lines) == N * len(f))
    check("the frequency appears once per entry, on the first line only",
          sum(1 for l in lines if not l.startswith(" ")) == len(f))

    # Row-major order, read back and compared against the asymmetric fixture.
    # This is the check a symmetric 2-port could not have.
    ok_order = True
    for fi in range(len(f)):
        for i in range(N):
            toks = lines[fi * N + i].split()
            if i == 0:
                toks = toks[1:]                # drop the frequency
            got = [complex(float(toks[2 * j]), float(toks[2 * j + 1]))
                   for j in range(N)]
            want = [_s(i + 1, j + 1) for j in range(N)]
            if got != want:
                ok_order = False
    check("row i of line i is S_i1 S_i2 S_i3 (row-major, no transpose)", ok_order)
    check("...and the fixture is asymmetric, so that check has teeth",
          _s(1, 2) != _s(2, 1))
    check("wrapping only bites past %d pairs, so a 3-port row is one line"
          % MAX_PAIRS_PER_LINE, N <= MAX_PAIRS_PER_LINE)

    # 2-port files must NOT have moved: same one-line layout, same quirk order.
    two = {(i, j): np.array([_s(i, j)] * len(f))
           for i in range(1, 3) for j in range(1, 3)}
    p2 = os.path.join(tmp, "pair.s2p")
    _result(two).write_touchstone(p2, n_ports=2)
    row2 = _data_lines(p2)[0].split()
    check("a 2-port entry is still ONE line of freq + 4 pairs", len(row2) == 9)
    check("...still in the S11 S21 S12 S22 quirk order",
          [complex(float(row2[1 + 2 * k]), float(row2[2 + 2 * k]))
           for k in range(4)]
          == [_s(1, 1), _s(2, 1), _s(1, 2), _s(2, 2)])

    # == 7. an incomplete N-port refuses, exactly as the 2-port one does =====
    partial = {k: v for k, v in merged.items() if k[1] != N}   # no port-N column
    res_p = _result(partial)
    # Two of three excitations leave the 2x2 sub-matrix of ports 1 and 2
    # genuinely COMPLETE, so the honest answer is order 2 — not 1, and not the
    # 3 that was asked for. Worth pinning: a user who cancels the last run of a
    # 3-port sweep still has a real .s2p, and refusing it would be as wrong as
    # fabricating the .s3p.
    check("two of three excitations still complete order 2 [%d]"
          % res_p.max_complete_ports(), res_p.max_complete_ports() == 2)
    bad = os.path.join(tmp, "bad.s3p")
    refused, named = False, False
    try:
        res_p.write_touchstone(bad, n_ports=N)
    except ValueError as exc:
        refused, named = True, ("S13" in str(exc) and "S33" in str(exc))
    check("...and an explicit 3-port request is REFUSED", refused)
    check("...naming the missing terms", named)
    check("...leaving no partial file behind", not os.path.exists(bad))

    # == 8. the pre-solve estimate prices N solves, not two ==================
    ana = _Analysis(N)
    one = estimate.work_of(ana, _Solver(full=False))
    full = estimate.work_of(ana, _Solver(full=True))
    check("a full %d-port is priced at %dx a single excitation [%g vs %g]"
          % (N, N, full, one), abs(full - N * one) < 1e-9)
    check("...and NOT at 2x, which was right only for a 2-port",
          abs(full - 2.0 * one) > 1e-9)
    check("a 4-port is priced at 4x", abs(
        estimate.work_of(_Analysis(4), _Solver(full=True))
        - 4.0 * estimate.work_of(_Analysis(4), _Solver(full=False))) < 1e-9)
    check("an analysis whose ports cannot be counted falls back to 1, not 2",
          estimate.excitation_count(object(), _Solver(full=True)) == 1)
    check("...and the switch off means one solve whatever the port count",
          estimate.excitation_count(ana, _Solver(full=False)) == 1)

    print()
    if FAILURES:
        print("n_port_smatrix: %d FAILED" % len(FAILURES))
        raise SystemExit("n_port_smatrix FAILED")
    print("n_port_smatrix: all checks passed")
    return 0


if __name__ == "__main__" or "FreeCAD" not in sys.modules:
    main()
