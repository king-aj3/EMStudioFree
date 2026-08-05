#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — TRUE OPEN-COIL support in the Elmer 3-D path.

An open conductor (free ends: a C-shape, a hairpin, a split ring, an
un-joined helix) cannot be driven by declaring ``Coil Closed``. Until
v0.85.0 the writer hard-coded that declaration, so every open conductor was
solved against a false premise — Elmer prints "Assuming that all coils are
closed!" and believes it.

WHAT THIS GATE PINS
-------------------
1. **The physics.** A 324 deg split ring (R = 100 mm, 4x4 mm section, 1000 A)
   has an EXACT closed form for the field at its centre::

       B_z = mu0 * I * phi / (4 * pi * R)

   which reduces to mu0*I/(2R) at phi = 2*pi. MEASURED 2026-08-05 on
   ElmerSolver 26.2: **-0.77 %**. That is a genuinely open conductor solved
   correctly, and it is the whole point of the feature.

2. **The keywords, and one that is deliberately ABSENT.** ``Coil Closed`` is
   DERIVED from the model, and an open coil gets ``Coil Start``/``Coil End``
   Dirichlet conditions on its two terminal faces (Elmer's own
   ``coilsolver.xml``: "Not needed if coil is closed").

   ``Coil Cross Section`` is NOT emitted, and this gate exists partly to keep
   it that way. It is a legal keyword and the obvious thing to reach for, and
   it is a silent-wrong-number generator — measured on this same ring:

   =================  ==================================
   correct area       Bz  -0.77 %
   4x the area        Bz -75.19 %  (exactly a quarter, silently)
   omitted            Bz  -0.79 %  (the same right answer)
   =================  ==================================

   So Elmer derives the section correctly from the mesh and supplying one can
   only override a correct value with our own. It costs a second thing too:
   given an explicit section, CoilSolver stops reporting its own average
   current density — which is exactly the measurement the delivery guard runs
   on. Emitting the keyword would have silently disabled the guard.

3. **The two branches mean different things by ``Desired Coil Current``, and
   the difference is silent.** MEASURED on the real user fixture (a 6.44-turn
   octagonal helix): requesting 100 on the OPEN branch put 100 A in the
   CONDUCTOR, whose 6.44 geometric turns delivered ~644 ampere-turns — the
   field landed 0.72 % from the finite-solenoid closed form for 644, and
   **6.39x above** the one for 100. The closed branch normalizes over a
   half-plane, which counts those turns itself. Hence ``_geometric_turns``
   and the double-count warning.

4. **The delivery guard covers open coils, against the right target.**
   Delivered = J_avg x the half-plane section counts every turn in both
   topologies, but the closed branch normalizes over that same half-plane
   (so expected == requested) while the open branch normalizes over ONE
   conductor cross-section (so expected == requested x geometric turns).
   Applying the closed rule to an open coil would flag a CORRECT 6.44-turn
   helix as 644 % over-delivered.

Pass: exit 0 and 'OPEN COIL GATE PASSED'. Live tier auto-skips without Elmer.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

MU0 = 4.0e-7 * math.pi
FAILURES = []

R_M = 0.100
C_M = 0.004
I_A = 1000.0
ANGLE_DEG = 324.0


def check(label, ok, detail=""):
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:96] + "]") if detail else ""))


def analytic_arc_bz(angle_deg=ANGLE_DEG, current=I_A, radius=R_M):
    """Biot-Savart at the centre of a circular arc. Exact for a filament."""
    return MU0 * current * math.radians(angle_deg) / (4.0 * math.pi * radius)


def split_ring_model(open_coil=True):
    from emstudio.meshing import gmsh_3d

    shape = {"kind": "tube", "center": (0.0, 0.0),
             "r_in": R_M - C_M / 2.0, "r_out": R_M + C_M / 2.0,
             "z0": -C_M / 2.0, "z1": C_M / 2.0, "angle_deg": ANGLE_DEG}
    body = {
        "name": "ring", "shape": shape, "mu_r": 1.0, "lc": 0.0012,
        "coil": {"amp_turns": I_A, "normal": (0.0, 0.0, 1.0),
                 "section_area_m2": C_M * C_M, "closed": not open_coil},
    }
    if open_coil:
        body["terminals"] = gmsh_3d.tube_terminal_boxes(shape)
    return {
        "bodies": [body],
        "air": {"kind": "cylinder", "r": 1.0, "z0": -1.0, "z1": 1.0},
        "lc_air": 0.150,
        "size_fields": [{"kind": "distance", "body": "ring", "lc": 0.0012,
                         "dist_min": 0.005, "dist_max": 0.50}],
        "embed_lines": [((0.0, 0.0, -0.05), (0.0, 0.0, 0.05))],
        "save_lines": [((0.0, 0.0, -0.05), (0.0, 0.0, 0.05), 50)],
    }


def _write(model, boundary_ids, body_ids=None):
    from emstudio.solvers.elmer import writer3d

    path = os.path.join(tempfile.mkdtemp(), "case.sif")
    writer3d.write_sif3d(model, path, body_ids or {"air": 1, "ring": 2},
                         boundary_ids)
    return open(path, encoding="utf-8").read()


OPEN_BCS = {"outer": 1, "ring_start": 2, "ring_end": 3}


# --- geometry tier ----------------------------------------------------------

def gate_terminal_discrimination():
    """A closed tube's flat ends must NOT be mistaken for current terminals.

    ``end_caps`` returns "the smallest pair of equal-area planar faces", and an
    annular tube has exactly such a pair: its flat z-ends. So the shipped 3-D
    Solenoid template — genuinely CLOSED — was reported as having two free
    ends, and gui_smoke went red on it. The discriminator is the NORMAL:
    current crosses a terminal, so a terminal's normal runs along the
    conductor, i.e. roughly perpendicular to the winding axis. A closed tube's
    flat ends point ALONG it.
    """
    from emstudio.solvers.elmer.model3d import (_TERMINAL_AXIS_DOT_MAX,
                                                _faces_look_like_terminals)

    class _N(object):
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z

    class _F(object):
        def __init__(self, n):
            self._n = n

        def normalAt(self, _u, _v):
            return self._n

    axis = (0.0, 0.0, 1.0)
    tube = [(1.0, _F(_N(0, 0, 1))), (1.0, _F(_N(0, 0, -1)))]
    check("a closed tube's flat ends are NOT treated as terminals",
          not _faces_look_like_terminals(tube, axis))

    # a helix's terminal normal is tangential, tilted only by the pitch angle
    ring = [(1.0, _F(_N(0, 1, 0.033))), (1.0, _F(_N(0.59, -0.81, 0.033)))]
    check("a split ring's / helix's terminal faces ARE treated as terminals",
          _faces_look_like_terminals(ring, axis))
    check("one bad face is enough to reject the pair",
          not _faces_look_like_terminals(
              [ring[0], (1.0, _F(_N(0, 0, 1)))], axis))
    check("the threshold sits far from both measured cases "
          "(helix ~0.03, tube 1.0)",
          0.1 < _TERMINAL_AXIS_DOT_MAX < 0.9, _TERMINAL_AXIS_DOT_MAX)
    check("a degenerate axis or normal is rejected, never guessed",
          not _faces_look_like_terminals(ring, (0.0, 0.0, 0.0))
          and not _faces_look_like_terminals([(1.0, _F(_N(0, 0, 0)))], axis))


def gate_geometry():
    from emstudio.meshing import gmsh_3d

    full = {"kind": "tube", "center": (0.0, 0.0), "r_in": 0.098,
            "r_out": 0.102, "z0": -0.002, "z1": 0.002}
    check("a FULL ring has no terminals at all (nothing to drive through)",
          gmsh_3d.tube_terminal_boxes(full) is None)

    arc = dict(full, angle_deg=ANGLE_DEG)
    t = gmsh_3d.tube_terminal_boxes(arc)
    check("a split ring reports exactly two terminals",
          sorted(t or {}) == ["end", "start"], sorted(t or {}))
    # start cap: the plane y = 0, x in [r_in, r_out], z spanning the section
    s = t["start"]
    check("start terminal box is the y=0 face at x in [r_in, r_out]",
          abs(s[0] - 0.098) < 1e-9 and abs(s[3] - 0.102) < 1e-9
          and abs(s[1]) < 1e-9 and abs(s[4]) < 1e-9
          and abs(s[2] + 0.002) < 1e-9 and abs(s[5] - 0.002) < 1e-9, s)
    # end cap: centred on R*cos(phi), R*sin(phi)
    e = t["end"]
    cx = 0.100 * math.cos(math.radians(ANGLE_DEG))
    cy = 0.100 * math.sin(math.radians(ANGLE_DEG))
    check("end terminal box is centred on the arc's far end",
          abs((e[0] + e[3]) / 2.0 - cx) < 1e-6
          and abs((e[1] + e[4]) / 2.0 - cy) < 1e-6,
          "({0:.4f}, {1:.4f}) want ({2:.4f}, {3:.4f})".format(
              (e[0] + e[3]) / 2.0, (e[1] + e[4]) / 2.0, cx, cy))

    # A 270 deg arc reaches -r_out in x even though NEITHER end face does.
    # A naive corners-only bbox misses that and the air domain would clip the
    # body.
    bb = gmsh_3d._shape_bbox(dict(full, angle_deg=270.0))
    check("a 270 deg arc's bbox includes the axis crossing it sweeps past",
          abs(bb[0] + 0.102) < 1e-9, "xmin {0:.6g} want -0.102".format(bb[0]))
    check("a full ring's bbox is unchanged by the angle support",
          gmsh_3d._shape_bbox(full) == (-0.102, -0.102, -0.002,
                                        0.102, 0.102, 0.002))


def gate_geo_deck():
    """The .geo: terminal Physical Surfaces, asserted, and no regression."""
    from emstudio.meshing import gmsh_3d

    d = tempfile.mkdtemp()
    closed_body = [{"name": "ring", "lc": 0.0012,
                    "shape": {"kind": "tube", "center": (0.0, 0.0),
                              "r_in": 0.098, "r_out": 0.102,
                              "z0": -0.002, "z1": 0.002}}]
    geo_closed = open(gmsh_3d.write_geo_3d(
        closed_body, os.path.join(d, "a.geo"),
        {"kind": "pad", "pad": 0.5}, 0.15), encoding="utf-8").read()
    # The full ring must not gain an eighth Cylinder argument, or every
    # existing 3-D deck changes.
    check("a closed body's geo emits no terminal groups",
          "_start" not in geo_closed and "_end" not in geo_closed)
    check("a full ring still emits a SEVEN-argument Cylinder (no regression)",
          "Cylinder(v0o) = {0, 0, -0.002, 0, 0, 0.004, 0.102};" in geo_closed,
          [l for l in geo_closed.splitlines() if "Cylinder(v0o)" in l])

    m = split_ring_model(open_coil=True)
    body = dict(m["bodies"][0])
    geo_open = open(gmsh_3d.write_geo_3d(
        [body], os.path.join(d, "b.geo"),
        {"kind": "pad", "pad": 0.5}, 0.15), encoding="utf-8").read()
    check("an open body's geo tags both terminal faces as Physical Surfaces",
          'Physical Surface("ring_start"' in geo_open
          and 'Physical Surface("ring_end"' in geo_open)
    check("a split ring emits the EIGHTH Cylinder argument (the sweep angle)",
          "0.004, 0.102, 5.65486677646};" in geo_open,
          [l for l in geo_open.splitlines() if "Cylinder(v0o)" in l])
    check("terminal selection is by bounding box, like the volumes",
          geo_open.count("Surface In BoundingBox") == 2)
    # Selecting 0 surfaces would emit an empty group and selecting 2 would
    # drive the wrong face; either way the solve runs and returns a plausible
    # wrong number. Assert IN THE GEO so it dies at mesh time.
    # Compare whole LINES, not substrings: an early draft counted
    # `"Abort;" in geo`, which a mutation commenting the line out to
    # "! Abort;" still satisfied. The mutation test caught that.
    geo_lines = [l.strip() for l in geo_open.splitlines()]
    check("the geo ASSERTS exactly one surface per terminal, and aborts",
          sum(1 for l in geo_lines if l.startswith('w("If (#sT')
              or l.startswith("If (#sT")) == 2
          and geo_lines.count("Abort;") == 2,
          [l for l in geo_lines if "Abort" in l])
    check("the terminal groups do not collide with 'outer' or the volumes",
          len({l.split('"')[1] for l in geo_open.splitlines()
               if l.startswith("Physical ")}) == 5,
          sorted({l.split('"')[1] for l in geo_open.splitlines()
                  if l.startswith("Physical ")}))

    # both ends or neither
    try:
        gmsh_3d.write_geo_3d(
            [dict(body, terminals={"start": body["terminals"]["start"]})],
            os.path.join(d, "c.geo"), {"kind": "pad", "pad": 0.5}, 0.15)
        check("a half-specified terminal pair is refused", False)
    except gmsh_3d.Mesh3DError as exc:
        check("a half-specified terminal pair is refused", True, str(exc)[:60])


# --- writer tier ------------------------------------------------------------

def gate_writer():
    from emstudio.solvers.elmer import writer3d

    closed = _write(split_ring_model(open_coil=False), {"outer": 1})
    check("a CLOSED coil still declares 'Coil Closed = Logical True'",
          "Coil Closed = Logical True" in closed)
    check("a CLOSED coil emits no terminal boundary conditions",
          "Coil Start" not in closed and "Coil End" not in closed)

    op = _write(split_ring_model(open_coil=True), OPEN_BCS)
    check("an OPEN coil declares 'Coil Closed = Logical False'",
          "Coil Closed = Logical False" in op)
    check("an OPEN coil gets a 'Coil Start' Dirichlet BC on its start face",
          "Coil Start = Logical True" in op
          and 'Name = "ring_start"' in op)
    check("an OPEN coil gets a 'Coil End' Dirichlet BC on its end face",
          "Coil End = Logical True" in op and 'Name = "ring_end"' in op)
    check("the terminal BCs target the mesh ids the mesher assigned",
          "Target Boundaries(1) = 2" in op and "Target Boundaries(1) = 3" in op)
    # 'A {e} = 0' on a terminal would short the vector potential across the
    # conductor's own end — a different physical statement entirely.
    term_block = op.split('Name = "ring_start"')[1].split("End")[0]
    check("a terminal BC carries ONLY the CoilSolver flag, not 'A {e} = 0'",
          "A {e}" not in term_block, term_block.strip()[:60])

    # The measured hazard. See the module docstring: 4x the area gave exactly
    # a quarter of the field, silently.
    check("'Coil Cross Section' is NOT emitted for either topology "
          "(measured: a wrong one rescales the field silently)",
          "Coil Cross Section" not in op and "Coil Cross Section" not in closed)

    # 'Coil Closed' is SOLVER-level in SOLVER.KEYWORDS — no per-component
    # form — so one deck cannot describe both.
    mixed = split_ring_model(open_coil=True)
    second = dict(mixed["bodies"][0])
    second = {"name": "ring2", "shape": second["shape"], "mu_r": 1.0,
              "lc": 0.0012,
              "coil": {"amp_turns": I_A, "normal": (0.0, 0.0, 1.0),
                       "section_area_m2": C_M * C_M, "closed": True}}
    mixed["bodies"] = mixed["bodies"] + [second]
    try:
        # body ids must EXIST, or the earlier body check fires first and this
        # would pass for the wrong reason (it did, on the first draft).
        _write(mixed, dict(OPEN_BCS, ring2=4),
               body_ids={"air": 1, "ring": 2, "ring2": 3})
        check("a deck mixing open and closed coils is REFUSED", False)
    except writer3d.Elmer3DModelError as exc:
        check("a deck mixing open and closed coils is REFUSED",
              "mixes open and closed" in str(exc), str(exc)[:70])

    # An open coil whose mesh never got the terminal groups must not fall
    # through to a deck that references boundaries which do not exist.
    try:
        _write(split_ring_model(open_coil=True), {"outer": 1})
        check("an open coil with no terminal boundaries is REFUSED", False)
    except writer3d.Elmer3DModelError as exc:
        check("an open coil with no terminal boundaries is REFUSED", True,
              str(exc)[:70])


def gate_turns():
    """The N-times-too-big trap, pinned against the measured fixture."""
    from emstudio.solvers.elmer.model3d import (_TURN_SAMPLES,
                                                _turns_from_areas)

    g = _turns_from_areas(6.43588 * 282.843, 282.843)
    check("geometric turns recovered from a section/cap area ratio",
          abs(g - 6.43588) < 1e-6, "{0:.5f} turns".format(g))
    check("a single C-shape reports one geometric turn",
          abs(_turns_from_areas(282.843, 282.843) - 1.0) < 1e-9)
    check("missing areas yield None, never a fabricated turn count",
          _turns_from_areas(None, 282.843) is None
          and _turns_from_areas(1.0, 0.0) is None)

    # ONE half-plane cannot answer this: it is crossed a WHOLE number of
    # times, so a 6.44-turn helix reads 7 at some azimuths and 6 at others.
    # MEASURED on the fixture over 16 uniformly spaced azimuths:
    #   7,6,6,6,6,6,6,6,6,6,7,7,7,7,7,7  -> mean 6.4375 vs truth 6.43588.
    # The first implementation used the single half-plane already computed
    # for the delivery guard and reported "7", an 8.6 % error in a number
    # printed to the user as fact.
    per_azimuth = [7.0] + [6.0] * 9 + [7.0] * 6
    single = per_azimuth[0]
    mean = sum(per_azimuth) / len(per_azimuth)
    check("a SINGLE half-plane quantizes and is wrong by ~8.6 % here",
          abs(single / 6.43588 - 1.0) > 0.05,
          "{0:.0f} vs 6.43588 ({1:+.1%})".format(single, single / 6.43588 - 1))
    check("averaging over azimuth recovers the true turn count",
          abs(mean / 6.43588 - 1.0) < 0.002,
          "{0:.4f} vs 6.43588 ({1:+.3%})".format(mean, mean / 6.43588 - 1))
    # The residue is bounded by half a sample, so the sample count is part of
    # the accuracy claim.
    check("enough azimuths are sampled to bound the residue under 1 %",
          (0.5 / _TURN_SAMPLES) / 6.43588 < 0.01,
          "{0} samples -> <= {1:.2%}".format(
              _TURN_SAMPLES, (0.5 / _TURN_SAMPLES) / 6.43588))

    # MEASURED on the fixture, 2026-08-05: 100 A requested on the open branch,
    # 6.44 geometric turns, field 0.72 % from the closed form for 644 At and
    # 6.39x above the one for 100 At.
    L = 6.43588 * 0.0310758
    ref = lambda ni: MU0 * ni / math.sqrt(L * L + (2 * 0.150) ** 2)  # noqa: E731
    measured = 0.00222700477273
    check("the measured open helix matches the 644-At closed form, not 100",
          abs(measured / ref(644.0) - 1.0) < 0.02
          and measured / ref(100.0) > 6.0,
          "{0:+.2%} vs 644 At; {1:.2f}x vs 100 At".format(
              measured / ref(643.588) - 1.0, measured / ref(100.0)))


# --- live tier --------------------------------------------------------------

def gate_live():
    from emstudio.setup import solvers as solver_setup
    from emstudio.solvers.elmer.runner3d import run_model3d

    # Skip only when the BACKENDS ARE ABSENT. Catching every exception as
    # "unavailable" would turn a broken solve into a silent pass, which is
    # exactly what a mutation test needs to be able to fail — and this gate's
    # whole claim lives in the live tier.
    missing = [k for k in ("elmer", "gmsh")
               if not solver_setup.find_backend(k).found]
    if missing:
        print("  skip  live tier — backend(s) not installed: {0}".format(
            ", ".join(missing)))
        return
    res = run_model3d(split_ring_model(open_coil=True), workdir=None)

    line = res["saveline"]
    pts = sorted(zip(line["coordinate 3"], line["magnetic flux density 3"]))
    i = min(range(len(pts)), key=lambda k: abs(pts[k][0]))
    bz = abs(pts[i][1])
    ref = analytic_arc_bz()
    err = bz / ref - 1.0
    check("an OPEN split ring's centre field matches the exact arc closed "
          "form within 3 %", abs(err) < 0.03,
          "FEM {0:.6g} T vs {1:.6g} T ({2:+.2%})".format(bz, ref, err))
    check("the open branch reports a normalized coil current",
          len(res.get("open_coil_current") or []) == 1,
          res.get("open_coil_current"))
    got = (res.get("open_coil_current") or [0.0])[0]
    check("that current is the one requested", abs(got / I_A - 1.0) < 0.01,
          "{0:.6g} A of {1:.0f}".format(got, I_A))

    # The delivered-ampere-turns guard DOES cover open coils — but only
    # because 'Coil Cross Section' is not emitted. With it, CoilSolver takes
    # the section as given and stops reporting its own average current
    # density, and this measurement disappears (observed 2026-08-05). That is
    # a second, independent reason never to emit it.
    j = res.get("j_avg") or []
    check("the open branch still reports an average current density (it does "
          "NOT when 'Coil Cross Section' is emitted)", len(j) == 1, j)
    if j:
        frac = abs(j[0]) * (C_M * C_M) / I_A
        check("a correctly driven OPEN coil passes the delivered-ampere-turns "
              "guard", 0.5 <= frac <= 2.0, "{0:.2%} delivered".format(frac))
        check("and it delivers essentially all of it (>99 %)", frac > 0.99,
              "{0:.4%}".format(frac))
    check("live solve converged cleanly and CoilSolver did not complain",
          not res["solver_warnings"], "; ".join(res["solver_warnings"][:2]))


def gate_mesh_default():
    """The auto mesh size must RESOLVE the conductor, not its bounding box."""
    from emstudio.solvers.elmer.model3d import _auto_lc_mm

    # The real fixture, measured: bbox 320 x 220 x 368 mm, conductor 19.98 mm
    # across flats, 2V/A = 9.22 mm.
    bbox = (-159.988, -209.988, -184.025, 159.988, 9.988, 184.025)
    envelope = max(min(bbox[3] - bbox[0], bbox[4] - bbox[1],
                       bbox[5] - bbox[2]) / 10.0, 1.0)
    check("the OLD bounding-box default is coarser than the 20 mm conductor "
          "it meshes", envelope > 19.98,
          "{0:.3g} mm vs a 19.98 mm conductor".format(envelope))

    # No FreeCAD here, so drive the helper with a stub exposing Volume/Area —
    # that is the whole interface min_feature_mm uses.
    class _Solid(object):
        Volume = 1715632.8162
        Area = 2.0 * 1715632.8162 / 9.22        # -> 2V/A == 9.22 mm

    lc, feat = _auto_lc_mm(_Solid(), bbox)
    check("the default is now sized from the conductor's own feature",
          feat is not None and abs(feat - 9.22) < 0.05, feat)
    check("and it puts at least 2 elements across the 19.98 mm conductor",
          lc > 0 and 19.98 / lc >= 2.0,
          "lc {0:.3g} mm -> {1:.2f} elements across".format(lc, 19.98 / lc))
    check("the auto size can only REFINE the old default, never coarsen it",
          lc <= envelope, "{0:.3g} <= {1:.3g}".format(lc, envelope))

    # A body with no usable volume (sheet/shell) must still get a size.
    class _Sheet(object):
        Volume = 0.0
        Area = 100.0

    lc2, feat2 = _auto_lc_mm(_Sheet(), bbox)
    check("a body with no volume falls back to the bounding box, not a crash",
          feat2 is None and abs(lc2 - envelope) < 1e-9, (lc2, feat2))


def main():
    print("EMStudio open-coil (Elmer 3-D) validation gate")
    gate_mesh_default()
    gate_terminal_discrimination()
    gate_geometry()
    gate_geo_deck()
    gate_writer()
    gate_turns()
    gate_live()
    print("-------------------")
    if FAILURES:
        raise SystemExit("OPEN COIL GATE FAILED: " + "; ".join(FAILURES))
    print("OPEN COIL GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
