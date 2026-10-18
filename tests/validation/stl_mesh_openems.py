#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — openEMS grid resolution for non-box (STL) bodies.

The defect this pins
--------------------
FDTD is a volume method on a Cartesian grid, so a conductor thinner than one
cell is not *approximated* — it is ABSENT. Until v0.84.0 an STL body received
exactly six grid lines (its bounding-box planes on each axis) and nothing
else, and it never reached ``AddEdges2Grid`` at all, because ``has_solid`` was
set only in the box branch. The cell size inside the body was therefore
whatever the global wavelength rule produced. A 20 mm conductor in a 250 mm
cell simulated cleanly and reported plausible S-parameters and a radiation
pattern for geometry that was not in the grid.

Three behaviours are pinned:

1. **Feature size is measured, not assumed.** ``2*V/A`` recovers the smallest
   dimension of a swept body from volume and surface alone — a plate's
   thickness exactly, a rod's radius (the conservative half of its diameter).
   A bounding box cannot: a 6-turn helix bounds 320 mm and conducts 20 mm.
2. **Affordable cases are refined**, with the extra lines bounded so a helix
   cannot silently request an astronomical grid. (Since v1.14.0 the bound is
   on the WHOLE grid, and a body too large to blanket is refined axis by
   axis — section 9; the blanket decision below is unchanged.)
3. **Hopeless cases are refused with numbers**, not simulated. This is the
   same principle as the NEC2 thin-wire warning at the other end of the scale:
   each solver states where it stops being valid instead of returning a
   confident answer outside its range.

Since v1.14.0 (a forum J-pole — 18 mm tubes with 1.2 mm walls at 80-120 MHz —
that the old refusal steered to MeshResolution 2700 and 9.4e9 cells), four
more are pinned, each against a NEGATIVE CONTROL showing v1.13's behaviour:

4. **The refusal is actionable.** It names the referenced OBJECT (not the
   deck's 'mat1_...'), judges each source SOLID, quotes the MeshResolution
   that would put one cell across the feature and that grid's cell count, and
   — when that is over openEMS's index limit or this machine's RAM — never
   says "raise MeshResolution". A thin-walled hollow body gets "model it as a
   solid rod" (a closed shell: "a solid body"), priced too, but only if its
   bore is far below waveguide cut-off; a solid body never gets it. With more
   than one object refused, a whole-model sentence prices the thinnest part
   LEFT once every fillable part is filled, so the user is not walked round
   refuse-fix-refuse one part at a time.
5. **References reach the model, each part once, never silently not.** A part
   picked through its group ('Group', 'Child.') is exported (v1.13: dropped);
   a group referenced together with its child exports the child ONCE; a
   reference that reaches nothing is a WARNING naming it; a hidden part of a
   referenced group is left out and SAID (unless it is also picked on its
   own, when it is in, and no note says otherwise); the group-brings-in-an-unpicked-part
   case (the forum Back plate) is a NOTE; placements and link instances land
   where they sit.
6. **Two materials tied on Priority over the same volume are warned**, with
   the exact overlap, and the warning reaches the deck's own output — from
   which ``writer.deck_model_notes`` reads it back word for word.
7. **A lumped port's two ends are GRID LINES** on its excitation axis, so
   they sit on the metal they were drawn on at every MeshResolution. openEMS
   snaps each end to the NEAREST line, and until v1.14.0 none was there: on
   a box-bar J-pole (the forum tubes as 15.3 mm bars) the feed end landed
   4.16 mm into air at MR 100 and 2.78 mm at MR 150 (NEGATIVE CONTROLS: the
   same decks with the port-end block cut out). Swept over MR 20-150, both
   ends are lines on their bars and openEMS's own setup places the port (no
   'snapping failed', no unused port primitive — CONTROL: a port squeezed
   into one cell IS dropped, and the same scan sees it). The deck's helper is also
   EXECUTED against a fake grid: a thirds-rule line a hair from an end is
   MOVED onto it rather than leaving a hair-thin cell, a geometry plane never
   moves, and an end outside the domain never grows it. A template whose
   ends were already lines (the patch) keeps its case.xml byte for byte, and
   an MSL deck gets no block at all.

Also since v1.14.0 (the same forum model's export and its refinement), two
more:

8. **Touching solids of one material are FUSED into closed solids.** Two
   boxes touching face to face and a plate on both, as one object (the
   forum Feed group in miniature): the v1.13 single-STL export has
   non-manifold edges and triangles CGAL refuses (NEGATIVE CONTROL, and
   openEMS's own setup refuses them — at least as many as ``stl_topology``
   predicts, its count being a floor); fused it is ONE STL with no defect,
   enclosing exactly the union, and openEMS's setup takes every triangle.
   A fuse that fails, or that would be WORSE than its parts (an edge
   contact), or that runs past its time budget, falls back to one closed
   STL per part and SAYS so; a part touching ITSELF is a WARNING naming it;
   an equal-Priority overlap is still reported against the PART inside a
   fused STL; tessellation deflection is min(diag/200, cell/4, feature/2).
9. **Local refinement is per part, axis by axis, budgeted as a whole.** A
   600 mm, 3 mm rod and a small block: v1.13's per-body cap gave the rod
   NOTHING (CONTROL); now it has lines at its own step across it and at its
   end planes, and stays coarse along its middle; the grading follows
   MeshSmoothRatio with no sliver; the writer's count of the refined grid is
   a true floor of openEMS's; the block sits after the ports and before the
   final smoothing; a refined grid over this machine's RAM is REFUSED with
   the parts that set it (never quietly coarsened); overlapping dielectric
   blankets share one coherent set of lines. Section 4 moved with it: the
   forum's own tube and an equal solid rod are now MESHED, so the refusal is
   exercised on a foil tube whose local refinement cannot fit anywhere.

And since the v1.14.0 review (two defects it upheld in point 4's advice):

10. **A coax is never told to fill, and a tube is measured in its own
    frame.** The bore test was an EMPTY-waveguide cut-off, so a coax shield
    — TEM, no cut-off — around its own inner conductor was told "fill the
    bore". Now anything else inside the bore (a conductor, a dielectric, a
    port; found in the bore's own frame, past an open end's MOUTH) makes it
    "a coax or feed structure, must NOT be filled", through write_deck, in
    the "also too thin" list and in the whole-model verdict alike (CONTROLS:
    a ground plane under the open end, a wire alongside in the box corner,
    a rod only at the mouth — none occupy it). And hollow_envelope read the
    GLOBAL bounding box, so a 45-degree tube read as a closed 1 m shell and
    a sloped-radial ground plane was priced at MeshResolution 211 for a
    filled rod that needs 404: now the tube is measured in the frame its
    faces carry (tilted reads exactly as upright), a body with no exact
    frame (B-spline faces) or whose box is not its cross-section (a flange)
    gets NO description, and the radials' refusal prices the filled rod.

And the rest of the review's fixes (one vacuous check, one false claim, one
defect) plus a follow-up its stages asked for:

11. **The export, the port and the cut-off, on real output.** The v1.14
    tessellation rule had one check, on ``stl_deflection_mm()`` alone, and
    dropping its arguments at the export call sites left this gate green:
    now the STLs ``_collect_materials`` WRITES are measured where the new
    terms bind (a 600 mm-radius disc at a quarter cell, a 400 mm ring at
    half its 2 mm wall), each against a CONTROL showing the v1.13 rule
    sagging past the bound; and the forum tube's STL is pinned byte-
    identical under both rules — the angular deflection sets its facets,
    which is the corrected claim. A lumped port with an end touching no
    metal is a WARNING naming the end, the nearest part and the distance,
    first among the deck's notes (CONTROLS: ends on, or inside, the arms;
    rod arms judged at their own refined cell). And a WR-28 band starting
    below the 21.08 GHz TE10 cut-off keeps its 18 samples above it with a
    NOTE (its radiation-pattern indices shifted onto the kept samples), a
    band wholly below is refused before any STL is written, a band above is
    untouched, and the cut-off is the textbook TE_mn formula.

Exit codes — a run that tested NOTHING must never read as a pass:

  0  all 140 checks ran and passed ('STL-MESH GATE PASSED')
  1  a check failed ('STL-MESH GATE FAILED: ...')
  2  FreeCAD is unavailable, so not one of the 140 checks could run
     ('STL-MESH GATE SKIPPED'). ``run_battery.py`` declares this gate in
     NEEDS_FREECAD and skips it BEFORE spawning on a box with no freecadcmd,
     so this code is only ever reached on a BY-HAND python3 run — where the
     caller explicitly asked for the gate and must be told it proved nothing.
     Until 2026-08-29 that branch printed the PASS token and returned 0: a
     python3 run reported success having executed zero checks.
"""

from __future__ import annotations

import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

FAILURES = []

#: Exit code for "the prerequisite the BATTERY declares is absent". Distinct
#: from 1 (a real failure) so a caller can tell "nothing ran" from "the physics
#: moved", and non-zero so a by-hand run can never read as success.
_RC_SKIPPED = 2


def check(label, ok, detail=""):
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:76] + "]") if detail else ""))


def main():
    print("EMStudio openEMS STL-resolution gate")
    try:
        import FreeCAD  # noqa: F401
        import Part
    except ImportError:
        # ImportError ONLY. A bare `except Exception` here (what this was)
        # would swallow a REAL regression raised DURING FreeCAD's own import —
        # a broken .so, a bad user config, a half-installed Mod dir — and
        # relabel it "no FreeCAD on this box": a regression laundered into a
        # skip.
        #
        # The openEMS writer imports FreeCAD at module scope, so not one of
        # the 140 checks below is reachable without it. run_battery.py DECLARES
        # this gate in NEEDS_FREECAD, so the battery skips it honestly before
        # ever spawning it and never reaches here; the only way in is a
        # BY-HAND python3 run. That must not read as success — print the
        # SKIPPED token (never the PASS token) and return a distinct non-zero
        # code.
        print("  skip  needs FreeCAD — run under freecadcmd")
        print("STL-MESH GATE SKIPPED — no FreeCAD in this interpreter, so "
              "0 of 140 checks ran; nothing was tested, this is NOT a pass")
        return _RC_SKIPPED

    from emstudio.solvers.openems import writer as wr

    # ---- 1. the refinement decision, pure ------------------------------
    # The helix that motivated all this: 105 x 73 x 121 = 927k cells to
    # blanket at its own conductor size. A per-axis cap would wave that
    # through (121 looks modest); the CELL budget is what catches it.
    helix = {"kind": "stl", "start": (-160.0, -210.0, -184.0),
             "stop": (160.0, 10.0, 184.0), "min_feature": 9.22}
    check("a thin body in a huge bbox declines a BLANKET fill (cell budget)",
          wr._stl_refinement(helix, 250.0) is None,
          "would cost ~927k cells for one body")

    # The case the affordability ceiling actually exists for: resolvable
    # enough to escape the refusal, but too large to blanket with a local grid.
    huge = {"kind": "stl", "start": (0.0, 0.0, 0.0),
            "stop": (10000.0, 400.0, 400.0), "min_feature": 30.0}
    check("a resolvable body too large to blanket declines the blanket",
          wr._stl_refinement(huge, 20.0) is None,
          "would need {0:.0f} lines on x".format(10000.0 / (30.0 / 3.0)))
    check("...and that same body is NOT refused (it IS resolvable)",
          wr._refuse_unresolvable(
              [{"name": "huge", "kind": "metal", "priority": 10,
                "prims": [huge]}], 20.0) is None)

    # A small body with the same feature: affordable, so refine.
    patch = {"kind": "stl", "start": (0.0, 0.0, 0.0),
             "stop": (40.0, 30.0, 2.0), "min_feature": 2.0}
    ref = wr._stl_refinement(patch, 10.0)
    check("a small body with a fine feature IS refined", ref is not None)
    if ref:
        step, counts = ref
        check("the refinement step resolves the feature",
              abs(step - 2.0 / wr.MIN_CELLS_ACROSS_FEATURE) < 1e-9,
              "{0:.4g} mm".format(step))
        check("refinement stays under both ceilings",
              max(counts) <= wr.MAX_REFINEMENT_LINES
              and counts[0] * counts[1] * counts[2] <= wr.MAX_REFINEMENT_CELLS,
              counts)

    # Already-resolved bodies must NOT be refined (no needless lines).
    check("a body the global grid already resolves is left alone",
          wr._stl_refinement({"kind": "stl", "start": (0.0, 0.0, 0.0),
                              "stop": (40.0, 30.0, 20.0),
                              "min_feature": 20.0}, 1.0) is None)
    check("a body with no measured feature is left alone",
          wr._stl_refinement({"kind": "stl", "start": (0, 0, 0),
                              "stop": (1, 1, 1), "min_feature": 0.0},
                             10.0) is None)

    # ---- 2. the refusal ------------------------------------------------
    mats = [{"name": "helix", "kind": "metal", "priority": 10,
             "prims": [helix]}]
    try:
        wr._refuse_unresolvable(mats, 250.0)
        check("a body thinner than one cell is REFUSED", False)
    except wr.OpenEMSModelError as exc:
        msg = str(exc)
        check("a body thinner than one cell is REFUSED", True)
        check("the refusal quotes the feature size", "9.22" in msg, msg[:60])
        check("the refusal quotes the cell size", "250" in msg)
        check("the refusal names the NEC2 alternative", "NEC2" in msg)
    # ... and must NOT fire once the grid resolves it
    try:
        wr._refuse_unresolvable(mats, 2.0)
        check("a resolved body is NOT refused", True)
    except wr.OpenEMSModelError as exc:
        check("a resolved body is NOT refused", False, str(exc)[:60])

    # ---- 3. the feature measure ----------------------------------------
    from emstudio.solvers.openems import geometry as geo

    # A rod: 2V/A is its RADIUS (documented conservative half-diameter).
    r, L = 5.0, 400.0
    rod = Part.makeCylinder(r, L)
    feat = geo.min_feature_mm(shape=rod)
    check("2V/A on a rod returns its radius (conservative half-diameter)",
          abs(feat / r - 1.0) < 0.05, "{0:.4g} vs {1:.4g} mm".format(feat, r))

    # A plate: 2V/A is its thickness exactly.
    t = 1.5
    plate = Part.makeBox(200.0, 150.0, t)
    featp = geo.min_feature_mm(shape=plate)
    check("2V/A on a thin plate returns its thickness",
          abs(featp / t - 1.0) < 0.10, "{0:.4g} vs {1:.4g} mm".format(featp, t))

    # The bounding box CANNOT do this — the point of the whole measure.
    bb_min = min(200.0, 150.0, t)
    check("the bbox alone would have agreed on a plate but not a helix",
          abs(bb_min - t) < 1e-9)
    helix_solid = Part.makeCylinder(9.5, 60.0)   # stand-in wire-like body
    bb = helix_solid.BoundBox
    bbox_feat = min(bb.XLength, bb.YLength, bb.ZLength)
    vol_feat = geo.min_feature_mm(shape=helix_solid)
    check("2V/A reads a wire-like body finer than its bounding box",
          vol_feat < bbox_feat,
          "{0:.4g} vs bbox {1:.4g} mm".format(vol_feat, bbox_feat))

    # Zero-volume sheet falls back to the bbox rather than dividing by zero.
    sheet = Part.makePlane(50.0, 40.0)
    fs = geo.min_feature_mm(shape=sheet,
                            bbox=((0.0, 0.0, 0.0), (50.0, 40.0, 0.0)))
    check("a zero-volume sheet falls back to the bbox without raising",
          fs > 0.0, "{0:.4g} mm".format(fs))

    import shutil
    import tempfile
    work = tempfile.mkdtemp(prefix="emstudio_stlgate_")
    try:
        _refusal_section(wr, work)
        _reference_section(wr, work)
        _overlap_section(wr, work)
        _port_line_section(wr, work)
        _watertight_section(wr, work)
        _refine_section(wr, work)
        _coax_tilt_section(wr, work)
        _review_fix_section(wr, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("-------------------")
    if FAILURES:
        raise SystemExit("STL-MESH GATE FAILED: " + "; ".join(FAILURES))
    print("STL-MESH GATE PASSED")
    return 0


# =========================================================================
# v1.14.0 — the forum J-pole (a forum user, macOS arm64, FreeCAD 1.1.4)
# =========================================================================
# Three defects met in ONE model. The refusal below told him to "raise
# MeshResolution until the cell is under 0.9475 mm" — the 2V/A of a whole
# GROUP, named by its deck id 'mat1_EMMaterial001', with no cost — so he set
# 2700 and built 9,429,380,072 cells. His sixteen part picks ('Feed > Mount',
# each screw and nut) were dropped in silence because Shape.getElement
# cannot read 'Body004.'. And the whole 'Feed' group he ALSO referenced
# carried a Back plate he never picked, which shorted his feed.

#: The tube in the brief: an 18 mm OD radiator tube with a 1.2 mm wall,
#: 1450 mm long, swept 80-120 MHz — the forum model's own numbers.
_TUBE_OD, _TUBE_WALL, _TUBE_LEN = 18.0, 1.2, 1450.0
#: A FOIL tube (OD, wall): since v1.14.0 the tube above is MESHED — local
#: refinement puts one cell across its wall and its wall only — so the
#: refusal is exercised on a body whose local refinement genuinely cannot
#: fit: 10,000 lines across each of x and y at one cell per 0.01 mm wall,
#: ~1e10 cells, over openEMS's index limit on EVERY machine (never decided
#: by this machine's RAM).
_FOIL_OD, _FOIL_WALL = 100.0, 0.01
#: ...and a foil SHEET's thickness, for the parts tilted so that no axis
#: runs along them (each then needs lines across its whole extent).
_SHEET_FOIL = 0.05
_C0 = 299792458.0


def _analysis(doc, f1, f2, mr=20, port_line=None):
    """A bare openEMS analysis: frequencies, one lumped port, one solver."""
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = "{0} Hz".format(f1)
    ana.FrequencyStop = "{0} Hz".format(f2)
    ana.FrequencyPoints = 41
    ana.MeshResolution = mr
    feed = doc.addObject("Part::Feature", "FeedLine")
    a, b = port_line
    feed.Shape = Part.makeLine(FreeCAD.Vector(*a), FreeCAD.Vector(*b))
    port = ports_mod.makeLumpedPort(doc, ana, name="P1", direction="+X")
    port.References = [(feed, "Edge1")]
    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    return ana, solver


def _deck_or_fail(wr, ana, solver, workdir, label):
    """(deck path, text) — or a FAIL line naming ``label`` and (None, "")
    when the writer refuses: a refused deck must read as a failed check,
    never as a traceback that hides every check after it."""
    os.makedirs(workdir, exist_ok=True)
    try:
        deck, _z, _n = wr.write_deck(ana, solver, workdir)
    except wr.OpenEMSModelError as exc:
        check(label, False, "the writer REFUSED it: " + str(exc)[:60])
        return None, ""
    with open(deck, encoding="utf-8") as fh:
        return deck, fh.read()


def _refusal_of(wr, ana, solver, workdir):
    os.makedirs(workdir, exist_ok=True)
    try:
        wr.write_deck(ana, solver, workdir)
    except wr.OpenEMSModelError as exc:
        return str(exc)
    return None


def _refusal_section(wr, work):
    """4. The refusal names the OBJECT, prices the fix, and offers the right one."""
    import re

    import FreeCAD
    import Part

    from emstudio.objects import material as material_mod
    from emstudio.solvers.openems import geometry as geo
    from emstudio.solvers.openems import preflight

    doc = FreeCAD.newDocument("stlgate_tube")
    r_out = _TUBE_OD / 2.0
    tube_shape = Part.makeCylinder(r_out, _TUBE_LEN).cut(
        Part.makeCylinder(r_out - _TUBE_WALL, _TUBE_LEN))
    tube = doc.addObject("Part::Feature", "Tube")
    tube.Shape = tube_shape
    tube.Label = "Radiator tube"
    ana, solver = _analysis(doc, 80e6, 120e6, mr=20,
                            port_line=((r_out, 0, _TUBE_LEN / 2.0),
                                       (r_out + 15.0, 0, _TUBE_LEN / 2.0)))
    feedline = doc.getObject("FeedLine")
    metal = material_mod.makeMaterial(doc, ana, name="TubePEC",
                                      category="Metal (PEC)")
    metal.Label = "Tube metal"
    metal.References = [(tube, "")]
    doc.recompute()
    lam_min = _C0 / 120e6 * 1e3
    pad = 0.25 * _C0 / 100e6 * 1e3          # DomainPaddingWavelengths default

    def _feed_at(r):
        feedline.Shape = Part.makeLine(
            FreeCAD.Vector(r, 0, _TUBE_LEN / 2.0),
            FreeCAD.Vector(r + 15.0, 0, _TUBE_LEN / 2.0))
        doc.recompute()

    # SINCE v1.14.0 THE FORUM'S OWN TUBE IS MESHED. Local refinement is per
    # part and axis by axis, so its 1.2 mm wall costs ~16 lines across each
    # of x and y and two graded end planes along z — where v1.13 tried to
    # blanket its 1450 mm bounding box, hit the per-body cap, refined
    # nothing and refused it. (CONTROL: that cap still says no.)
    d_u = os.path.join(work, "tube_meshed")
    msg_u = _refusal_of(wr, ana, solver, d_u)
    deck_u = os.path.join(d_u, "case_openems.py")
    txt_u = ""
    if msg_u is None and os.path.isfile(deck_u):
        with open(deck_u, encoding="utf-8") as fh:
            txt_u = fh.read()
    feat_u = 2.0 * tube_shape.Volume / tube_shape.Area
    old_cap = wr._stl_refinement(
        {"start": (-r_out, -r_out, 0.0), "stop": (r_out, r_out, _TUBE_LEN),
         "min_feature": feat_u}, lam_min / 20)
    check("4u. the forum's own 18/1.2 mm tube at 80-120 MHz (MR 20) is now "
          "MESHED, not refused: refined across x and y, two planes along z "
          "(CONTROL: v1.13's per-body cap refines nothing for it)",
          msg_u is None and old_cap is None
          and "# Radiator tube: " in txt_u
          and "x across -9..9; y across -9..9; z at 2 place(s)" in txt_u,
          (msg_u or "")[:70])

    # The REFUSAL is therefore exercised on a body whose local refinement
    # genuinely cannot fit: a FOIL tube, OD 100 mm with a 0.01 mm wall —
    # one cell across that wall is 10,000 lines on each of x and y, ~1e10
    # cells, over openEMS's index limit on every machine (so the test is
    # machine-independent: the RAM limit never decides it).
    r_foil = _FOIL_OD / 2.0
    foil_shape = Part.makeCylinder(r_foil, _TUBE_LEN).cut(
        Part.makeCylinder(r_foil - _FOIL_WALL, _TUBE_LEN))
    tube.Shape = foil_shape
    _feed_at(r_foil)
    msg = _refusal_of(wr, ana, solver, os.path.join(work, "tube"))
    check("4a. a 100 mm foil tube with a 0.01 mm wall at 80-120 MHz (MR 20) "
          "is REFUSED", msg is not None)
    msg = msg or ""
    check("4v. ...because LOCAL refinement cannot hold it: the refusal says "
          "so, with the refined grid's count, over the index limit, and "
          "names the tube as the part left at the global cell",
          "Local refinement could not resolve every thin part" in msg
          and "more than openEMS can index" in msg
          and "left at the global cell: 'Radiator tube'" in msg, msg[:90])
    # The per-body text follows that sentence (it quotes its OWN grid).
    body = msg.split("left at the global cell: ", 1)[-1]

    # Every number the checks need is derived HERE from the shape and the
    # band, never read back from the writer: 2V/A of the tube is its wall;
    # the cell is lambda_min / MeshResolution (lambda at 120 MHz).
    feat = 2.0 * foil_shape.Volume / foil_shape.Area
    mr_need = int(math.ceil(lam_min / feat))
    ext = (_FOIL_OD + 2 * pad, _FOIL_OD + 2 * pad, _TUBE_LEN + 2 * pad)
    cell = lam_min / mr_need
    est = 1
    for e in ext:
        est *= int(e / cell) + 1

    def names_object(t):
        return "'Radiator tube'" in t and "mat1_" not in t

    def offers_rod(t):
        return "solid rod" in t

    def quotes_mr(t):
        return "MeshResolution {0}".format(mr_need) in t

    def quotes_cells(t):
        # The writer quotes the preflight's FLOOR, which takes 1 % off the
        # line count per axis (preflight._LINE_SLACK) — about 3 % under this
        # plain estimate — so the window is 5 %, and one-sided enough to
        # catch a count from the wrong grid (the MR 20 one is 0.002 % of it).
        m = re.search(r"= ([\d,]+) cells", t)
        return bool(m) and abs(int(m.group(1).replace(",", "")) / est - 1) < 0.05

    def no_raise(t):
        return bool(t) and "raise meshresolution" not in t.lower()

    check("4b. the refusal names the OBJECT ('Radiator tube'), not 'mat1_...'",
          names_object(msg), msg[:70])
    check("4c. ...offers the solid-rod model of a thin-walled tube",
          offers_rod(body))
    check("4d. ...quotes the MeshResolution that would resolve it "
          "(MeshResolution {0})".format(mr_need), quotes_mr(body))
    check("4e. ...quotes that grid's cell count (~{0:.3g}, within 5 %)".format(
          float(est)), quotes_cells(body))
    check("4f. ...that count is over openEMS's index limit, and it says so",
          est >= preflight.OPENEMS_MAX_CELLS
          and "more than openEMS can index" in body)
    check("4g. ...and never says 'raise MeshResolution' (over budget)",
          no_raise(msg))
    check("4h. ...keeps naming NEC2, the right tool for a wire this thin",
          "NEC2" in body)
    # The solid-rod alternative is PRICED too: 2V/A of a filled rod of
    # diameter D, length L is D*L/(2L + D).
    rod_feat = _FOIL_OD * _TUBE_LEN / (2 * _TUBE_LEN + _FOIL_OD)
    mr_rod = int(math.ceil(lam_min / rod_feat))
    check("4i. ...and prices the solid rod (MeshResolution {0} is enough)"
          .format(mr_rod),
          "MeshResolution {0} is enough".format(mr_rod) in body)
    # NEGATIVE CONTROL: the v1.13 text for this very body, verbatim in form.
    # If the four predicates did not all FAIL on it they would prove nothing.
    old = ("'mat1_TubePEC' has a smallest feature of {0:.4g} mm, but the FDTD "
           "cell is {1:.4g} mm — {2:.3g} cells across it, so this body would "
           "be absent from the grid and the run would still report "
           "plausible-looking results. Either raise MeshResolution until the "
           "cell is under {0:.4g} mm (the domain is wavelength-sized, so check "
           "the cell count first), or model this conductor with the NEC2 wire "
           "backend, which is the accurate method for a conductor this thin "
           "against the wavelength.").format(feat, lam_min / 20,
                                             feat / (lam_min / 20))
    check("4j. CONTROL: the v1.13 refusal fails all four (object, solid rod, "
          "MeshResolution, no 'raise')",
          not names_object(old) and not offers_rod(old)
          and not quotes_mr(old) and not no_raise(old))

    # A SOLID 18 mm rod at the same band: v1.13 refused it too (9 mm radius
    # in a 125 mm cell, too long to blanket); now it is meshed like the tube.
    tube.Shape = Part.makeCylinder(r_out, _TUBE_LEN)
    _feed_at(r_out)
    check("4x. a SOLID 18 mm rod at the same band (MR 20) is MESHED too — "
          "v1.13 refused it",
          _refusal_of(wr, ana, solver, os.path.join(work, "rod")) is None)
    # The message builder's AFFORDABLE branch is still the right text where
    # it applies — a part the global grid cannot hold, whose one-cell fix
    # fits. Called the pre-v1.14.0 way (no refinement plan): the rod judged
    # at the global cell, priced with write_deck's own cost terms.
    d_r = os.path.join(work, "rod_direct")
    os.makedirs(d_r, exist_ok=True)
    mats_r = wr._collect_materials(ana, d_r)
    cost_r = {"wavelength_mm": lam_min, "mr_floor": 6,
              "extent_mm": [_TUBE_OD + 2 * pad, _TUBE_OD + 2 * pad,
                            _TUBE_LEN + 2 * pad],
              "f_max_hz": 120e6, "ram_bytes": preflight.physical_ram_bytes(),
              "allow": False}
    try:
        wr._refuse_unresolvable(mats_r, lam_min / 20, cost=cost_r)
        msg_rod = ""
    except wr.OpenEMSModelError as exc:
        msg_rod = str(exc)
    rfeat = 2.0 * tube.Shape.Volume / tube.Shape.Area
    mr_r = int(math.ceil(lam_min / rfeat))
    check("4k. an affordable fix IS offered: 'Raise MeshResolution to {0}'"
          .format(mr_r),
          "Raise MeshResolution to {0} or more".format(mr_r) in msg_rod,
          msg_rod[:70])
    check("4l. ...and a SOLID body gets no thin-walled-tube advice",
          bool(msg_rod) and "solid rod" not in msg_rod)

    # The hollow test itself: a closed ring around a bore, not merely "thin".
    # The L-bracket is thin with its box centre in AIR (rays escape); the "+"
    # cross is thin with its centre in METAL, where every ray starts inside
    # the material and "hits" — only the centre-inside test rejects it.
    lbr = Part.makeBox(50, 30, 2).fuse(Part.makeBox(2, 30, 50))
    cross = Part.makeBox(50, 2, 50, FreeCAD.Vector(0, 24, 0)).fuse(
        Part.makeBox(2, 50, 50, FreeCAD.Vector(24, 0, 0)))
    tfeat = 2.0 * tube_shape.Volume / tube_shape.Area
    h_tube = geo.hollow_envelope(tube_shape, tfeat)
    check("4m. hollow_envelope: tube -> hollow about its long (z) axis",
          bool(h_tube) and h_tube["axis"] == 2
          and abs(min(h_tube["outline_mm"]) - _TUBE_OD) < 1e-6, h_tube)
    check("4n. ...solid rod, L-bracket and a thin '+' cross -> not hollow",
          geo.hollow_envelope(Part.makeCylinder(r_out, _TUBE_LEN), rfeat) is None
          and geo.hollow_envelope(lbr, 2 * lbr.Volume / lbr.Area) is None
          and geo.hollow_envelope(cross, 2 * cross.Volume / cross.Area) is None)
    # A bore that carries fields in the band must NEVER be told to fill.
    big = {"axis": 2, "wall_mm": 1.0, "outline_mm": (60.0, 60.0),
           "length_mm": 300.0}
    t_hi, ok_hi = wr._fill_advice(big, {"f_max_hz": 3.0e9})
    t_lo, ok_lo = wr._fill_advice(big, {"f_max_hz": 120e6})
    check("4o. a 58 mm bore at 3 GHz (near its cut-off) is NOT to be filled; "
          "at 120 MHz it may be; with NO band known it is never told to",
          ok_hi is False and "must NOT be filled" in (t_hi or "")
          and "solid rod" not in (t_hi or "") and ok_lo is True
          and wr._fill_advice(big, None) == (None, False)
          and wr._fill_advice(big, {}) == (None, False))

    # A CLOSED shell (an enclosure drawn with 1 mm walls) is hollow too, but
    # "rod" is the wrong picture — and its cut-off is set by its LONGEST
    # inside dimension: 98 mm here (c/2a = 1.53 GHz), not the 48 mm
    # cross-section (3.12 GHz). At 1.5 GHz the cross-section alone would
    # wrongly say "fill it" (1.5 < 3.12/2); the length says no (1.5 > 0.76).
    shell = Part.makeBox(50, 50, 100).cut(
        Part.makeBox(48, 48, 98, FreeCAD.Vector(1, 1, 1)))
    h_shell = geo.hollow_envelope(shell, 2 * shell.Volume / shell.Area)
    check("4q. hollow_envelope: a closed 1 mm shell is hollow AND closed; the "
          "open tube is not closed",
          bool(h_shell) and h_shell.get("closed") is True
          and bool(h_tube) and h_tube.get("closed") is False,
          (h_shell, (h_tube or {}).get("closed")))
    t_sh, ok_sh = wr._fill_advice(h_shell or {}, {"f_max_hz": 150e6}) \
        if h_shell else (None, False)
    t_sh2, ok_sh2 = wr._fill_advice(h_shell or {}, {"f_max_hz": 1.5e9}) \
        if h_shell else (None, False)
    check("4r. ...at 150 MHz it may be filled as a 'solid body' (not 'rod'); "
          "at 1.5 GHz its 98 mm LENGTH forbids it",
          ok_sh is True and "solid body" in (t_sh or "")
          and "rod" not in (t_sh or "") and ok_sh2 is False
          and "must NOT be filled" in (t_sh2 or ""), (t_sh or "")[:60])

    # WHOLE MODEL. The worst body's own fix is not the model's: add a FOIL
    # REFLECTOR (a 600 mm, 0.05 mm sheet, tilted 30 degrees so no axis runs
    # along it and every one needs lines across the whole sheet) beside the
    # foil tube. Both are over openEMS's index on their own, so local
    # refinement drops both; filled, the tube needs only MR 52, but the
    # foil still needs one cell across its 0.05 mm in a 3 m domain — over
    # the index limit — and the refusal must say so instead of sending the
    # user to fill the tube only to be refused on the foil.
    tube.Shape = foil_shape
    _feed_at(r_foil)
    foil = Part.makeBox(600.0, 600.0, _SHEET_FOIL)
    foil.rotate(FreeCAD.Vector(300, 300, 0), FreeCAD.Vector(0, 1, 0), 30)
    fb = foil.BoundBox
    foil.translate(FreeCAD.Vector(r_foil + 200.0 - fb.XMin, -300.0 - fb.YMin,
                                  300.0 - fb.ZMin))
    guy = doc.addObject("Part::Feature", "Foil")
    guy.Shape = foil
    guy.Label = "Reflector foil"
    metal.References = [(tube, ""), (guy, "")]
    doc.recompute()
    msg_w = _refusal_of(wr, ana, solver, os.path.join(work, "whole")) or ""
    gfeat = 2.0 * guy.Shape.Volume / guy.Shape.Area
    mr_guy = int(math.ceil(lam_min / gfeat))
    whole_w = (msg_w.split("For the model as a whole", 1)[1]
               if "For the model as a whole" in msg_w else "")
    check("4s. two refused objects: a whole-model verdict names the FOIL "
          "(the thinnest part once the tube is filled) and its "
          "MeshResolution {0}, over the index limit".format(mr_guy),
          whole_w.startswith(" (with every hollow part filled)")
          and "the thinnest part left is 'Reflector foil'" in whole_w
          and "MeshResolution {0}:".format(mr_guy) in whole_w
          and "more than openEMS can index" in whole_w, msg_w[-90:])
    check("4t. CONTROL: one refused object -> no whole-model sentence (the "
          "per-body text already is the answer)",
          bool(msg) and "For the model as a whole" not in msg)
    FreeCAD.closeDocument(doc.Name)

    # PER-SOLID judging. One object holding a 200 mm block and a 1 mm sheet:
    # its 2V/A as a whole is ~50 mm (surface-weighted, the block dominates),
    # five cells at 1.0-1.5 GHz MR 20 (cell 10 mm), so v1.13 refined nothing
    # and anchored only the OBJECT's planes (z 0 and 301) — the sheet, a
    # tenth of a cell thick, was simply not in the grid. Now each solid is
    # its own part: the sheet gets both of its faces as lines.
    doc2 = FreeCAD.newDocument("stlgate_multisolid")
    combo = Part.makeCompound([
        Part.makeBox(200, 200, 200),
        Part.makeBox(200, 200, 1, FreeCAD.Vector(0, 0, 300))])
    both = doc2.addObject("Part::Feature", "Combo")
    both.Shape = combo
    both.Label = "Block and sheet"
    ana2, solver2 = _analysis(doc2, 1.0e9, 1.5e9, mr=20,
                              port_line=((-5, 100, 100), (-1, 100, 100)))
    m2 = material_mod.makeMaterial(doc2, ana2, name="ComboPEC",
                                   category="Metal (PEC)")
    m2.References = [(both, "")]
    doc2.recompute()
    cell2 = _C0 / 1.5e9 * 1e3 / 20
    whole = 2.0 * combo.Volume / combo.Area
    d_w = os.path.join(work, "combo_sheet")
    msg_s = _refusal_of(wr, ana2, solver2, d_w)
    txt_w = ""
    if msg_s is None:
        with open(os.path.join(d_w, "case_openems.py"), encoding="utf-8") as fh:
            txt_w = fh.read()
    check("4w. a 1 mm sheet inside a multi-solid object is now its OWN part: "
          "not refused, both its faces are grid lines (z 300 and 301) "
          "(CONTROL: the whole object reads {0:.3g} cells, so v1.13 refined "
          "nothing and anchored z 0 and 301 only)".format(whole / cell2),
          msg_s is None and whole / cell2 >= 1.0
          and wr._stl_refinement({"start": (0, 0, 0), "stop": (200, 200, 301),
                                  "min_feature": whole}, cell2) is None
          and "mesh.AddLine('z', [300, 301])" in txt_w, (msg_s or "")[:70])
    # ...and a part inside such an object that local refinement CANNOT
    # hold (a tilted 0.05 mm foil) is refused BY SOLID, by name.
    foil2 = Part.makeBox(600.0, 600.0, _SHEET_FOIL)
    foil2.rotate(FreeCAD.Vector(300, 300, 0), FreeCAD.Vector(0, 1, 0), 30)
    fb2 = foil2.BoundBox
    foil2.translate(FreeCAD.Vector(-fb2.XMin, -fb2.YMin, 260.0 - fb2.ZMin))
    both.Shape = Part.makeCompound([Part.makeBox(200, 200, 200), foil2])
    doc2.recompute()
    whole2 = 2.0 * both.Shape.Volume / both.Shape.Area
    msg2 = _refusal_of(wr, ana2, solver2, os.path.join(work, "combo")) or ""
    check("4p. a 0.05 mm foil inside a multi-solid object is REFUSED, by "
          "solid (CONTROL: the whole object reads {0:.3g} cells, which v1.13 "
          "passed)".format(whole2 / cell2),
          whole2 / cell2 >= 1.0 and "'Block and sheet (solid 2 of 2)'" in msg2,
          msg2[:70])
    FreeCAD.closeDocument(doc2.Name)


def _prims_by_label(prims):
    out = {}
    for p in prims:
        out[p.get("label")] = out.get(p.get("label"), 0) + 1
    return out


def _reference_section(wr, work):
    """5. Part picks are honoured, each part ONCE, and nothing drops silently."""
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import query
    from emstudio.solvers.openems import geometry as geo

    doc = FreeCAD.newDocument("stlgate_refs")
    ana = analysis_mod.makeAnalysis(doc)
    grp = doc.addObject("App::DocumentObjectGroup", "Grp")
    grp.Label = "Feed"
    child = doc.addObject("Part::Feature", "Child")
    child.Shape = Part.makeCylinder(3.0, 20.0)      # not a box: the STL path
    child.Label = "Mount"
    plate = doc.addObject("Part::Feature", "Plate")
    plate.Shape = Part.makeBox(30.0, 30.0, 2.0, FreeCAD.Vector(-15, -15, 25))
    plate.Label = "Back plate"
    grp.addObject(child)
    grp.addObject(plate)
    mat = material_mod.makeMaterial(doc, ana, name="RefPEC",
                                    category="Metal (PEC)")
    mat.Label = "PEC"
    doc.recompute()

    def classify(refs, tag):
        mat.References = refs
        doc.recompute()
        notes = []
        d = os.path.join(work, tag)
        os.makedirs(d, exist_ok=True)
        return geo.classify_shapes(mat, d, tag, notes=notes), notes

    # (i) a part picked THROUGH its group
    mat.References = [(grp, ("Child.",))]
    doc.recompute()
    old = [s for _o, s, _sub in query.resolved_references(mat)]
    check("5a. CONTROL: the v1.13 resolver reads ('Feed', 'Child.') as NOTHING",
          old == [None], old)
    prims, notes = classify([(grp, ("Child.",))], "pick")
    by = _prims_by_label(prims)
    bb = child.Shape.BoundBox
    check("5b. ...now that pick exports the child exactly ONCE",
          by == {"Feed > Mount": 1}, by)
    check("5c. ...as an STL at the child's own place",
          len(prims) == 1 and prims[0]["kind"] == "stl"
          and os.path.isfile(prims[0]["path"])
          and all(abs(a - b) < 1e-6 for a, b in zip(
              prims[0]["start"] + prims[0]["stop"],
              (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))))

    # (ii) the group AND the child: reached twice, exported once
    reached = sum(1 for sub in ("", "Child.")
                  for r in query._resolve_one(grp, sub)[0]
                  if r["leaf"] is child)
    prims, notes = classify([(grp, ("", "Child."))], "both")
    by = _prims_by_label(prims)
    check("5d. group + child: the child is REACHED twice (without de-dup: 2)",
          reached == 2, reached)
    check("5e. ...and EXPORTED once (and the plate once)",
          by == {"Feed > Mount": 1, "Feed > Back plate": 1}, by)
    check("5f. ...with a NOTE that the group also brings in the unpicked "
          "'Feed > Back plate'",
          any("NOTE" in n and "ALSO brings in 'Feed > Back plate'" in n
              for n in notes), notes)

    # (iii) references that reach NOTHING are warnings naming them
    fp = doc.addObject("App::FeaturePython", "NoShape")
    fp.Label = "Annotation"
    prims, notes = classify([(grp, ("Nope.",)), (plate, ("Face99",)),
                             (fp, "")], "dead")
    warns = [n for n in notes if n.startswith("EMStudio: WARNING - ")]
    check("5g. three dead references: nothing exported, three WARNINGS",
          prims == [] and len(warns) == 3, notes)
    check("5h. ...each naming its reference ('Feed'/'Nope.', 'Back plate'/"
          "'Face99', 'Annotation')",
          any("'Feed' / 'Nope.'" in w for w in warns)
          and any("'Back plate' / 'Face99'" in w for w in warns)
          and any("'Annotation'" in w for w in warns), warns)
    edge_prims, edge_notes = classify([(child, ("Edge1",))], "edge")
    check("5i. a bare edge in an openEMS material is a WARNING, not a silent "
          "skip", edge_prims == [] and any(
              "only edges or points" in n for n in edge_notes), edge_notes)

    # (iv) a hidden part of a referenced group is left out — and SAID
    plate.Visibility = False
    prims, notes = classify([(grp, ("",))], "hidden")
    plate.Visibility = True
    check("5j. a hidden part of a referenced group is left out (FreeCAD's rule)",
          _prims_by_label(prims) == {"Feed > Mount": 1})
    check("5k. ...with a NOTE naming it", any(
        "hidden" in n and "'Feed > Back plate'" in n for n in notes), notes)
    # ...but a hidden part ALSO picked on its own IS in the model: exported
    # once, and no "left out" note claiming otherwise.
    plate.Visibility = False
    prims, notes = classify([(grp, ("",)), (plate, "")], "hidden_picked")
    plate.Visibility = True
    check("5q. a hidden part that is ALSO picked on its own: exported once, "
          "no false 'left out' note",
          sorted(_prims_by_label(prims).values()) == [1, 1]
          and len(prims) == 2
          and not any("hidden" in n for n in notes), notes)

    # (v) placement: through a placed App::Part; link instances in two places
    asm = doc.addObject("App::Part", "Asm")
    asm.Label = "Assembly"
    bolt = doc.addObject("Part::Feature", "Bolt")
    bolt.Shape = Part.makeCylinder(1.0, 6.0)
    bolt.Label = "Bolt"
    asm.addObject(bolt)
    asm.Placement.Base = FreeCAD.Vector(0, 100, 0)
    lk = doc.addObject("App::Link", "BoltCopy")
    lk.LinkedObject = child
    lk.Placement.Base = FreeCAD.Vector(0, 0, 500)
    doc.recompute()
    prims, notes = classify([(asm, ("Bolt.",)), (asm, ("",))], "placed")
    check("5l. a pick inside a placed App::Part lands at its GLOBAL place, once",
          len(prims) == 1 and abs(prims[0]["start"][1] - 99.0) < 1e-6
          and abs(prims[0]["stop"][1] - 101.0) < 1e-6,
          [(p["label"], p["start"]) for p in prims])
    prims, notes = classify([(grp, ("Child.",)), (lk, "")], "links")
    check("5m. the same body as an App::Link in ANOTHER place is a second "
          "part (2 exports)", len(prims) == 2
          and sorted(round(p["start"][2]) for p in prims) == [0, 500],
          [(p["label"], p["start"]) for p in prims])

    # (vi) a port edge picked through a group resolves (it used to be refused)
    pgrp = doc.addObject("App::DocumentObjectGroup", "PortGrp")
    line = doc.addObject("Part::Feature", "Line")
    line.Shape = Part.makeLine(FreeCAD.Vector(0, 0, 0),
                               FreeCAD.Vector(0, 0, 5))
    pgrp.addObject(line)
    port = ports_mod.makeLumpedPort(doc, ana, name="P9", direction="+Z")
    port.References = [(pgrp, ("Line.Edge1",))]
    doc.recompute()
    old = [s for _o, s, _sub in query.resolved_references(port)]
    try:
        span = wr._port_span(port)
    except wr.OpenEMSModelError as exc:
        span = str(exc)
    check("5n. a port edge picked through a group gives the port its span "
          "(v1.13: None, refused)", old == [None] and span == (
              (0.0, 0.0, 0.0), (0.0, 0.0, 5.0)), (old, span))

    # (vii) an imported mesh inside a placed App::Part: obj.Mesh carries only
    # its OWN placement, so the container's must be added — read the STL back.
    import Mesh
    masm = doc.addObject("App::Part", "MeshAsm")
    masm.Placement.Base = FreeCAD.Vector(0, 100, 0)
    mf = doc.addObject("Mesh::Feature", "Imported")
    mf.Mesh = Mesh.Mesh(Part.makeBox(1, 1, 1).tessellate(0.1))
    mf.Placement.Base = FreeCAD.Vector(0, 0, 7)
    mf.Label = "Imported STL"
    masm.addObject(mf)
    doc.recompute()
    prims, notes = classify([(masm, ("Imported.",))], "mesh")
    back = (Mesh.Mesh(prims[0]["path"]).BoundBox
            if len(prims) == 1 and os.path.isfile(prims[0]["path"]) else None)
    check("5o. a mesh in a placed App::Part is written at its GLOBAL place "
          "(y 100..101, z 7..8)", back is not None
          and abs(back.YMin - 100) < 1e-6 and abs(back.YMax - 101) < 1e-6
          and abs(back.ZMin - 7) < 1e-6 and abs(back.ZMax - 8) < 1e-6, back)
    FreeCAD.closeDocument(doc.Name)

    # (viii) a model whose only material reaches nothing: the refusal carries
    # the REASON. v1.13 tessellated a wire into an STL with no facets and ran
    # an "antenna" that was a port in empty space.
    doc3 = FreeCAD.newDocument("stlgate_wireonly")
    ana3, solver3 = _analysis(doc3, 1.0e9, 2.0e9, mr=20,
                              port_line=((0, 0, -1), (0, 0, 1)))
    wire = doc3.addObject("Part::Feature", "Wire")
    wire.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, 1),
                                   FreeCAD.Vector(0, 0, 70)])
    wire.Label = "Dipole wire"
    m3 = material_mod.makeMaterial(doc3, ana3, name="WirePEC",
                                   category="Metal (PEC)")
    m3.References = [(wire, "")]
    doc3.recompute()
    d3 = os.path.join(work, "wireonly")
    os.makedirs(d3, exist_ok=True)
    try:
        wr.write_deck(ana3, solver3, d3)
        why3 = ""
    except wr.OpenEMSModelError as exc:
        why3 = str(exc)
    check("5p. a wire-only model is refused WITH the reason ('Dipole wire' "
          "is only edges)", "no material with usable geometry" in why3
          and "'Dipole wire'" in why3 and "only edges" in why3, why3[:70])
    FreeCAD.closeDocument(doc3.Name)


def _overlap_section(wr, work):
    """6. Two materials tied on Priority over the same space are WARNED."""
    import FreeCAD
    import Part

    from emstudio.objects import material as material_mod

    doc = FreeCAD.newDocument("stlgate_overlap")
    # The port runs across the 2 mm rod the deck checks (6e-6g) end up with,
    # both ends ON its surface. ⚠ It used to run (-5..-1, 0, 5) — one end
    # 3 mm out in air — and since the v1.14.0 review fixes such a port is
    # itself a model WARNING (section 11), so 6g's "a model with no notes"
    # would no longer have been one. Nothing else here reads the port.
    ana, solver = _analysis(doc, 2.0e9, 3.0e9, mr=20,
                            port_line=((-2, 0, 5), (2, 0, 5)))
    a = doc.addObject("Part::Feature", "BlockA")
    a.Shape = Part.makeBox(10, 10, 10)
    a.Label = "Mount block"
    b = doc.addObject("Part::Feature", "BlockB")
    b.Shape = Part.makeBox(10, 10, 10, FreeCAD.Vector(5, 5, 5))
    b.Label = "Back plate"
    metal = material_mod.makeMaterial(doc, ana, name="OvPEC",
                                      category="Metal (PEC)")
    metal.Label = "PEC"
    metal.References = [(a, "")]
    diel = material_mod.makeMaterial(doc, ana, name="OvDiel",
                                     category="Dielectric")
    diel.Label = "Plastic"
    diel.References = [(b, "")]
    metal.Priority = diel.Priority = 10
    doc.recompute()

    def warned(tag):
        d = os.path.join(work, tag)
        os.makedirs(d, exist_ok=True)
        mats = wr._collect_materials(ana, d)
        return [n for n in wr._overlap_notes(mats) if "same Priority" in n]

    w = warned("ov_tie")
    check("6a. PEC and a dielectric overlapping at the SAME Priority: warned",
          len(w) == 1 and "'Mount block'" in w[0] and "'Back plate'" in w[0]
          and "'PEC'" in w[0] and "'Plastic'" in w[0]
          and "125 mm^3" in w[0], w)
    diel.Priority = 0
    doc.recompute()
    check("6b. CONTROL: different Priorities (the user chose) -> no warning",
          warned("ov_prio") == [])
    diel.Priority = 10
    b.Shape = Part.makeBox(10, 10, 10, FreeCAD.Vector(10, 0, 0))
    doc.recompute()
    check("6c. CONTROL: blocks that only TOUCH -> no warning",
          warned("ov_touch") == [])
    # An STL body inside a box: the exact (boolean) overlap, not the bbox's.
    b.Shape = Part.makeBox(40, 40, 40, FreeCAD.Vector(-20, -20, -20))
    a.Shape = Part.makeCylinder(2.0, 10.0)
    doc.recompute()
    w = warned("ov_stl")
    vol = math.pi * 2.0 ** 2 * 10.0
    check("6d. a rod inside a block: warned with the EXACT overlap "
          "({0:.4g} mm^3, not the bbox's 160)".format(vol),
          len(w) == 1 and "{0:.4g} mm^3".format(vol) in w[0], w)
    # Past the exact-test time budget the pair must still be WARNED, on its
    # bounding boxes — a budget that silently dropped the warning would trade
    # a slow writer for the very silence this section exists to end.
    saved = wr._EXACT_OVERLAP_BUDGET_S
    wr._EXACT_OVERLAP_BUDGET_S = 0.0
    try:
        w0 = warned("ov_budget")
    finally:
        wr._EXACT_OVERLAP_BUDGET_S = saved
    check("6h. past the exact-test time budget the pair is still warned, on "
          "its bounding boxes ('may overlap', 160 mm^3)",
          len(w0) == 1 and "may overlap" in w0[0] and "160 mm^3" in w0[0], w0)
    # End to end: the warning reaches the DECK (so the solver log) as an
    # ASCII print, and the deck still compiles.
    d = os.path.join(work, "ov_deck")
    deck, text = _deck_or_fail(wr, ana, solver, d,
                               "6e. the overlap model writes a deck")
    # (repr() picks the quote character, so either may open the literal)
    pl = [ln for ln in text.splitlines()
          if ln.startswith("print(") and "EMStudio: WARNING - " in ln
          and "same Priority" in ln]
    try:
        compile(text, deck or "<refused>", "exec")
        compiles = bool(text)
    except SyntaxError:
        compiles = False
    check("6e. ...and is printed by the deck itself, ASCII-only, deck compiles",
          len(pl) == 1 and all(ord(c) < 128 for c in pl[0]) and compiles, pl)
    # The runner reads the notes back FROM the deck (deck_model_notes) to put
    # them in result.meta: it must return exactly what the deck prints — the
    # ASCII text, at warning level — and nothing for a deck with no notes.
    back = wr.deck_model_notes(deck) if deck else []
    import ast
    printed = [ast.literal_eval(ln[len("print("):-len(", flush=True)")])
               for ln in pl]
    check("6f. deck_model_notes reads the warning back from the deck, at "
          "warning level, word for word",
          back == [("warning", printed[0])] if printed else False, back)
    diel.Priority = 0
    doc.recompute()
    d2 = os.path.join(work, "ov_deck_clean")
    deck2, text2 = _deck_or_fail(wr, ana, solver, d2,
                                 "6g. the clean overlap model writes a deck")
    check("6g. CONTROL: no notes -> no notes block in the deck, and "
          "deck_model_notes returns []",
          bool(deck2) and wr.MODEL_NOTES_MARK not in text2
          and wr.deck_model_notes(deck2) == [],
          wr.deck_model_notes(deck2) if deck2 else "refused")
    FreeCAD.closeDocument(doc.Name)


# =========================================================================
# 7. A lumped port's two ends are GRID LINES (v1.14.0)
# =========================================================================
# openEMS snaps each end of a lumped element to the NEAREST grid line and
# nothing put a line there: the thirds rule sets lines a third of a cell
# inside and two thirds outside each metal face, never on it. On a box-bar
# J-pole through EMStudio's own runner the feed end landed 4.16 mm off its
# bar at MeshResolution 100 (VSWR 22.3 at 85 MHz against 2.5 at MR 20-60)
# and 2.78 mm at 150; on the forum J-pole both ends collapsed onto one line
# and openEMS dropped the port ("Lumped Element snapping failed! Dimension
# is: 0 skipping") while the run "finished OK".

#: The box-bar J-pole: two 15.3 mm square bars (the forum tubes' equivalent
#: section), a shorting box between them, fed across a 38.7 mm gap at
#: z = 451.7 mm — the model the 2026-10-17 investigation ran through the
#: product runner. The GAP is what makes the two bars' thirds-rule lines
#: interleave around each face.
_BAR, _GAP, _FEED_Z = 15.3, 38.7, 451.7
#: The sweep the brief names: the J-pole's sane range and the two
#: resolutions at which the v1.13 grid put an end off its metal.
_PORT_MRS = (20, 40, 60, 100, 150)


def _box_jpole(doc, mr):
    """(analysis, solver, port ends on x, the two bars' x extents)."""
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    V = FreeCAD.Vector
    h = _BAR / 2.0
    xs = h + _GAP + h                   # the stub's centre line
    zb = 17.5 - h

    def box(name, x0, z0, dx, dz):
        o = doc.addObject("Part::Box", name)
        o.Length, o.Width, o.Height = dx, _BAR, dz
        o.Placement.Base = V(x0, -h, z0)
        return o
    rad = box("Radiator", -h, zb, _BAR, 1450.9 - zb)
    stub = box("Stub", xs - h, zb, _BAR, 1095.0 - zb)
    short = box("Short", h, zb, _GAP, _BAR)
    feed = doc.addObject("Part::Feature", "FeedGap")
    feed.Shape = Part.makeLine(V(h, 0, _FEED_Z), V(xs - h, 0, _FEED_Z))
    doc.recompute()
    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = "80 MHz"
    ana.FrequencyStop = "120 MHz"
    ana.FrequencyPoints = 201
    ana.MeshResolution = mr
    m = material_mod.makeMaterial(doc, ana, name="PEC", category="Metal (PEC)")
    m.References = [(rad, ""), (stub, ""), (short, "")]
    port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort", direction="+X")
    port.References = [(feed, "Edge1")]
    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    solver.ComputeFarField = False
    solver.NearFieldPlane = "None"
    doc.recompute()
    return ana, solver, (h, xs - h), ((-h, h), (xs - h, xs + h))


def _snap_index(lines, c):
    """openEMS ``Operator::SnapToMeshLine`` (dualMesh=false), verbatim in
    effect: the first line whose DUAL line (the midpoint to the next) is at
    or beyond ``c`` — the nearest line, a tie going to the lower one."""
    if c < lines[0]:
        return 0
    for n in range(len(lines) - 1):
        if c <= 0.5 * (lines[n] + lines[n + 1]):
            return n
    return len(lines) - 1


def _grid_lines(xml, ax):
    import re
    m = re.search(r"<%sLines[^>]*>([^<]*)</%sLines>" % (ax.upper(), ax.upper()),
                  xml)
    return [float(v) for v in m.group(1).split(",")] if m else []


#: The marker the writer opens its port-end block with; the NEGATIVE CONTROL
#: below cuts that block out to recreate the v1.13 deck.
_PORT_BLOCK = "# --- lumped ports: both ends ON the grid"


def _strip_port_block(deck):
    """The v1.13 deck: this one with its port-end block cut out (unchanged if
    there is none — then the controls below fail, as they should)."""
    a = deck.find(_PORT_BLOCK)
    if a < 0 or "_port_end('" not in deck[a:]:
        return deck
    b = deck.index("\n\n", deck.index("_port_end('", a))
    return deck[:a] + deck[b + 2:]


def _preview(python, d, text, setup=False):
    """Run ``text`` as the deck in ``d`` with --preview: (x lines, xml text).
    ``setup``: ALSO run openEMS's own setup on it (operator, lumped elements,
    the unused-primitive summary — no timesteps) and return its output."""
    import subprocess

    from emstudio.solvers.base import foreign_python_env
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "case_openems.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    env = foreign_python_env(dict(os.environ))
    subprocess.run([python, p, "--preview"], cwd=d, capture_output=True,
                   text=True, env=env, timeout=600)
    with open(os.path.join(d, "case.xml"), encoding="utf-8") as fh:
        xml = fh.read()
    out = ""
    if setup:
        # setup_only is openEMS's own switch (openEMS.pyx Run): the operator
        # is built — which is where lumped elements are snapped and dropped —
        # and Run returns before the first timestep. Harness-only edit.
        st = text.replace("FDTD.Run(sim_path, cleanup=False)",
                          "FDTD.Run(sim_path, cleanup=False, setup_only=True)"
                          "\nsys.exit(0)")
        p2 = os.path.join(d, "case_setup.py")
        with open(p2, "w", encoding="utf-8") as fh:
            fh.write(st)
        r = subprocess.run([python, p2], cwd=d, capture_output=True, text=True,
                           env=env, timeout=600)
        out = (r.stdout or "") + (r.stderr or "")
    return _grid_lines(xml, "x"), xml, out


class _FakeMesh(object):
    """Just the two CSRectGrid calls the deck's port-end helper makes."""

    def __init__(self, lines):
        self.lines = {a: list(v) for a, v in lines.items()}

    def GetLines(self, ax):
        return sorted(set(self.lines[ax]))

    def SetLines(self, ax, vals):
        self.lines[ax] = list(vals)


def _port_line_section(wr, work):
    """7. A lumped port's ends are grid lines, on its metal at every MR."""
    import FreeCAD

    from emstudio.setup.solvers import find_openems_python

    doc = FreeCAD.newDocument("stlgate_ports")
    ana, solver, ends, bars = _box_jpole(doc, 100)
    d0 = os.path.join(work, "port_mr100")
    os.makedirs(d0, exist_ok=True)
    deck0, _z, _n = wr.write_deck(ana, solver, d0)
    with open(deck0, encoding="utf-8") as fh:
        text0 = fh.read()

    # -- the deck's helper, EXECUTED against a fake grid (pure, no openEMS) --
    # (A deck without it is a FAIL on every case below, not a crash.)
    a = text0.find("def _port_end(")
    helper = text0[a:text0.index("\n\n", a)] if a >= 0 else ""

    def run(lines, v, fixed, res=25.0):
        ns = {"mesh": _FakeMesh({"x": lines})}
        try:
            exec(helper, ns)                               # noqa: S102
            ns["_port_end"]("x", v, fixed, res)
        except Exception as exc:                           # noqa: BLE001
            return "deck helper missing or broken: %r" % (exc,)
        return ns["mesh"].lines["x"]
    got = run([-700.0, 3.486, 11.814, 15.98, 700.0], 7.65, [7.65])
    check("7a. an end 4.16 mm from its nearest lines BECOMES a line; no "
          "other line moves", got == [-700.0, 3.486, 7.65, 11.814, 15.98, 700.0],
          got)
    got = run([-700.0, 3.486, 7.66, 15.0, 700.0], 7.65, [7.65])
    check("7b. an end 0.01 mm from a thirds-rule HELPER line moves that line "
          "onto it - no 0.01 mm cell (it would cut the timestep by hundreds)",
          got == [-700.0, 3.486, 7.65, 15.0, 700.0], got)
    got = run([-700.0, 3.486, 7.66, 15.0, 700.0], 7.65, [7.65, 7.66])
    check("7c. ...but a GEOMETRY plane is never moved (zero-thickness metal "
          "would fall out of the grid): the end is added beside it",
          got == [-700.0, 3.486, 7.65, 7.66, 15.0, 700.0], got)
    got = run([-700.0, 3.486, 7.6500004, 15.0, 700.0], 7.65, [7.65])
    check("7d. an end already on a line (within 1e-6 mm) changes nothing",
          got == [-700.0, 3.486, 7.6500004, 15.0, 700.0], got)
    got = run([-700.0, 3.486, 15.0, 700.0], 800.0, [800.0])
    check("7e. an end OUTSIDE the domain never grows the box",
          got == [-700.0, 3.486, 15.0, 700.0], got)

    python = find_openems_python()
    if not python:
        check("7f-7t. live half NOT RUN: needs the openEMS python "
              "(EMSTUDIO_OPENEMS_PYTHON) for the deck's own --preview", False)
        FreeCAD.closeDocument(doc.Name)
        return

    # -- the sweep: every MR, both ends ON a line, on METAL, and placed -------
    for mr in _PORT_MRS:
        ana.MeshResolution = mr
        doc.recompute()
        d = os.path.join(work, "port_mr%d" % mr)
        os.makedirs(d, exist_ok=True)
        deck, _z, _n = wr.write_deck(ana, solver, d)
        with open(deck, encoding="utf-8") as fh:
            text = fh.read()
        xl, _xml, out = _preview(python, os.path.join(d, "v114"), text,
                                setup=True)
        rep, ok = [], bool(xl)
        for e in ends:
            on = any(abs(x - e) <= 1e-9 for x in xl)
            pos = xl[_snap_index(xl, e)] if xl else float("nan")
            metal = any(lo - 1e-9 <= pos <= hi + 1e-9 for lo, hi in bars)
            ok = ok and on and metal
            rep.append("%g->%s" % (e, "line" if on else "%.4g" % pos))
        faults = [ln for ln in out.splitlines()
                  if "snapping failed" in ln or "zero (snapped) length" in ln
                  or ("Unused primitive" in ln and "port_" in ln)]
        built = "Create FDTD operator" in out and "FDTD simulation size" in out
        check("7%s. MR %d: both port ends are grid lines, on their bars [%s]"
              % ("fghij"[_PORT_MRS.index(mr)], mr, ", ".join(rep)), ok)
        check("7%s. MR %d: openEMS builds the operator and places the port "
              "(no 'snapping failed', no unused port primitive)"
              % ("klmno"[_PORT_MRS.index(mr)], mr),
              built and not faults, faults[:1] or ("" if built else out[-90:]))
        if mr in (100, 150):
            # NEGATIVE CONTROL: the same deck with the block cut out is the
            # v1.13 deck. Its ends must land OFF the metal by the measured
            # amount — else the checks above prove nothing at this MR.
            xs, _x, _o = _preview(python, os.path.join(d, "v113"),
                                  _strip_port_block(text))
            miss = []
            for e in ends:
                pos = xs[_snap_index(xs, e)]
                if not any(lo - 1e-9 <= pos <= hi + 1e-9 for lo, hi in bars):
                    miss.append(abs(pos - e))
            want = {100: 4.16, 150: 2.78}[mr]
            check("7%s. CONTROL: the v1.13 deck at MR %d puts a port end %.3g "
                  "mm into AIR (measured %s)"
                  % ("p" if mr == 100 else "q", mr, want,
                     ", ".join("%.3g" % m for m in miss) or "none"),
                  bool(miss) and all(abs(m - want) < 0.01 for m in miss))
        if mr == 20:
            # NEGATIVE CONTROL for 7k-7o: the box bars never collapsed a port
            # even in v1.13, so "no 'snapping failed'" above would pass on any
            # grid unless the scan is shown to SEE one. Squeeze the port into
            # one cell (both ends within 2 mm, between lines) in a deck with
            # no port-end block: openEMS must drop it, and say so.
            import re as _re
            squeezed = _re.sub(
                r"AddLumpedPort\(1, 50, \[[^]]*\], \[[^]]*\]",
                "AddLumpedPort(1, 50, [20, 0, %g], [22, 0, %g]" % (
                    _FEED_Z, _FEED_Z), _strip_port_block(text))
            _xq, _x, outq = _preview(python, os.path.join(d, "squeezed"),
                                     squeezed, setup=True)
            seen = [ln for ln in outq.splitlines()
                    if "snapping failed" in ln
                    or ("Unused primitive" in ln and "port_" in ln)]
            check("7t. CONTROL: a port squeezed into one cell IS dropped, and "
                  "the same scan sees it (%d openEMS lines)" % len(seen),
                  any("snapping failed" in ln for ln in seen)
                  and any("port_excite_1" in ln for ln in seen),
                  seen[:1])

    # -- templates whose ends were already lines keep their grid -----------
    from emstudio.templates import msl_filter, patch as patch_tpl
    pdoc = FreeCAD.newDocument("stlgate_ports_patch")
    pana = patch_tpl.makePatch(pdoc)
    psol = [o for o in pana.Group
            if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]
    dp = os.path.join(work, "port_patch")
    os.makedirs(dp, exist_ok=True)
    pdeck, _z, _n = wr.write_deck(pana, psol, dp)
    with open(pdeck, encoding="utf-8") as fh:
        ptext = fh.read()
    _a, xml_new, _o = _preview(python, os.path.join(dp, "new"), ptext)
    _b, xml_old, _o = _preview(python, os.path.join(dp, "v113"),
                               _strip_port_block(ptext))
    check("7r. the patch template's port ends were already lines: its grid "
          "(the whole case.xml) is IDENTICAL with and without the block",
          _PORT_BLOCK in ptext and xml_new == xml_old)
    ndoc = FreeCAD.newDocument("stlgate_ports_msl")
    nana = msl_filter.makeNotchFilter(ndoc)
    nsol = [o for o in nana.Group
            if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]
    dn = os.path.join(work, "port_msl")
    os.makedirs(dn, exist_ok=True)
    ndeck, _z, _n = wr.write_deck(nana, nsol, dn)
    with open(ndeck, encoding="utf-8") as fh:
        check("7s. a microstrip (MSL-port) deck gets NO port-end block - its "
              "gated grid is not this fix's to move",
              "_port_end(" not in fh.read())
    for d_ in (doc, pdoc, ndoc):
        FreeCAD.closeDocument(d_.Name)


# =========================================================================
# 8-9. v1.14.0 — watertight export, per-part axis-by-axis refinement
# =========================================================================
# The forum J-pole again. Each referenced object was ONE STL, however many
# solids it held: its Feed group (two clamps and a back plate touching face
# to face) came out with 240 edges shared by four triangles and 78
# duplicated triangles, and CGAL refused 458 of them ("Trying reverse
# order... failed"), so openEMS filled the body by ray parity through the
# holes. And local refinement blanketed each body's bounding box at a third
# of its feature, capped at 400 lines an axis and 200k cells a body: every
# body of that model crossed a cap, so NOTHING was refined, at any
# MeshResolution.


def _stl_volume(path):
    """|Volume| enclosed by an STL, by the divergence theorem (mm^3)."""
    from emstudio.solvers.openems import geometry as geo
    tris = geo._read_stl_triangles(path) or []
    v = 0.0
    for a, b, c in tris:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1])
              - a[1] * (b[0] * c[2] - b[2] * c[0])
              + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return abs(v)


def _clean(topo):
    return all(topo.get(k) == 0 for k in
               ("open", "nonmanifold", "pinched", "duplicate", "degenerate",
                "refused"))


def _builder_lines(out):
    """openEMS's own polyhedron-builder complaints (NOT the deck's notes,
    which quote the phrase in their advice)."""
    return [ln for ln in out.splitlines()
            if ln.startswith("Polyhedron_Builder")]


def _watertight_section(wr, work):
    """8. Touching solids of one material are fused into CLOSED solids."""
    import FreeCAD
    import MeshPart
    import Part

    from emstudio.objects import material as material_mod
    from emstudio.setup.solvers import find_openems_python
    from emstudio.solvers.openems import geometry as geo

    V = FreeCAD.Vector
    doc = FreeCAD.newDocument("stlgate_fuse")
    # Two boxes touching face to face (x = 10) and a plate on both (z = 10),
    # as ONE object — the forum Feed group's shape, in miniature. The plate
    # overhangs, so the object does not fill its bounding box and takes the
    # STL path, not the native box one.
    parts = [Part.makeBox(10, 10, 10), Part.makeBox(10, 10, 10, V(10, 0, 0)),
             Part.makeBox(30, 10, 1, V(0, 0, 10))]
    clamp = doc.addObject("Part::Feature", "Clamp")
    clamp.Shape = Part.makeCompound(parts)
    clamp.Label = "Clamp assembly"
    ana, solver = _analysis(doc, 1.0e9, 2.0e9, mr=20,
                            port_line=((-5, 5, 5), (0, 5, 5)))
    solver.ComputeFarField = False
    solver.NearFieldPlane = "None"
    m = material_mod.makeMaterial(doc, ana, name="ClampPEC",
                                  category="Metal (PEC)")
    m.Label = "Clamp metal"
    m.References = [(clamp, "")]
    doc.recompute()

    def classify(tag):
        d = os.path.join(work, tag)
        os.makedirs(d, exist_ok=True)
        notes = []
        prims = geo.classify_shapes(m, d, tag, notes=notes)
        return [p for p in prims if p["kind"] == "stl"], notes

    # CONTROL: the v1.13 export, exactly — one STL of the whole object at
    # 0.5 % of its diagonal.
    old_p = os.path.join(work, "fuse_v113.stl")
    sh = clamp.Shape
    MeshPart.meshFromShape(
        Shape=sh, LinearDeflection=max(sh.BoundBox.DiagonalLength, 1.0) * 0.005,
        AngularDeflection=0.35, Relative=False).write(old_p)
    t_old = geo.stl_topology(old_p)
    check("8a. CONTROL: the v1.13 export (one STL for the object) of two "
          "touching boxes and a plate has non-manifold edges and triangles "
          "CGAL refuses",
          t_old.get("nonmanifold", 0) > 0 and t_old.get("refused", 0) > 0,
          {k: t_old.get(k) for k in ("nonmanifold", "duplicate", "refused")})
    stls, notes = classify("fused")
    check("8b. now ONE STL: the three solids fused into one solid that keeps "
          "the object's name and its three parts",
          len(stls) == 1 and len(stls[0].get("parts") or []) == 3
          and stls[0]["label"] == "Clamp assembly",
          [(p["label"], len(p.get("parts") or [])) for p in stls])
    t_new = geo.stl_topology(stls[0]["path"]) if stls else {}
    check("8c. ...0 open, 0 non-manifold, 0 pinched, 0 duplicated, 0 "
          "degenerate and 0 refused triangles", _clean(t_new),
          {k: t_new.get(k) for k in ("open", "nonmanifold", "pinched",
                                     "duplicate", "refused")})
    vol = _stl_volume(stls[0]["path"]) if stls else 0.0
    check("8d. ...enclosing exactly the union (2300 mm^3; measured %.4f)" % vol,
          abs(vol - 2300.0) < 0.01)
    check("8e. ...and nothing to warn about", not any(
        n.startswith("EMStudio: WARNING") for n in notes), notes)

    python = find_openems_python()
    if python:
        d = os.path.join(work, "fuse_deck")
        _deck, text = _deck_or_fail(wr, ana, solver, d,
                                    "8f. the fused model writes a deck")
        _x, _xml, out = (_preview(python, d, text, setup=True) if text
                         else ([], "", ""))
        built = "FDTD simulation size" in out
        check("8f. openEMS's own setup of that deck builds the operator and "
              "takes every triangle (no 'Trying reverse order')",
              built and not _builder_lines(out), _builder_lines(out)[:1])
        # CONTROL: the same deck reading the v1.13 STL. openEMS must refuse
        # triangles — and exactly as many as stl_topology predicted, which
        # is what lets the writer warn BEFORE openEMS runs.
        stl_names = [f for f in os.listdir(d) if f.endswith(".stl")]
        dc = os.path.join(work, "fuse_deck_v113")
        os.makedirs(dc, exist_ok=True)
        import shutil
        for f in stl_names:
            shutil.copyfile(old_p, os.path.join(dc, f))
        _x, _xml, outc = (_preview(python, dc, text, setup=True) if text
                          else ([], "", ""))
        failed = [ln for ln in _builder_lines(outc) if ln.endswith("failed")]
        # stl_topology's count is a FLOOR (it replays CGAL's halfedge rule,
        # not its vertex rules): never above openEMS's, never zero when
        # openEMS refuses any.
        check("8g. CONTROL: the same deck reading the v1.13 STL makes openEMS "
              "refuse %d triangle(s); stl_topology's floor said at least %d"
              % (len(failed), t_old.get("refused", -1)),
              len(failed) > 0
              and 0 < t_old.get("refused", 0) <= len(failed))
    else:
        check("8f-8g. live half NOT RUN: needs the openEMS python", False)

    # FALLBACKS. A fuse that fails, or the time budget running out, must
    # still give closed solids — one per part — and SAY so.
    orig_fuse, orig_budget = geo._fuse, geo._FUSE_BUDGET_S
    try:
        geo._fuse = lambda members, tol: (None, "simulated failure")
        stls_f, notes_f = classify("fuse_failed")
    finally:
        geo._fuse = orig_fuse
    check("8h. a fuse that fails: one closed STL per part, and a NOTE naming "
          "the parts and the reason",
          len(stls_f) == 3
          and all(_clean(geo.stl_topology(p["path"])) for p in stls_f)
          and any("could not be fused" in n and "simulated failure" in n
                  and "'Clamp assembly (solid 1 of 3)'" in n
                  for n in notes_f), notes_f)
    try:
        geo._FUSE_BUDGET_S = -1.0
        stls_b, notes_b = classify("fuse_budget")
    finally:
        geo._FUSE_BUDGET_S = orig_budget
    check("8i. past the fusing time budget: part by part, closed, and a NOTE "
          "says so", len(stls_b) == 3 and any(
              "took longer than" in n for n in notes_b), notes_b)

    # NEVER SHIP A FUSE WORSE THAN ITS PARTS. Two boxes touching only along
    # an EDGE, bridged by a plate: fused, they are one solid with a
    # non-manifold edge (the forum fuse had 18, where a tube's bore edge
    # rests on the mast junction); exported part by part, each is clean.
    bridge = [Part.makeBox(10, 10, 10), Part.makeBox(10, 10, 10, V(10, 10, 0)),
              Part.makeBox(10, 10, 2, V(5, 5, 10))]
    clamp.Shape = Part.makeCompound(bridge)
    doc.recompute()
    stls_e, notes_e = classify("edge_contact")
    check("8j. an edge contact the fuse cannot make manifold: exported part "
          "by part, every STL clean, a NOTE and no WARNING",
          len(stls_e) == 3
          and all(_clean(geo.stl_topology(p["path"])) for p in stls_e)
          and any(n.startswith("EMStudio: NOTE") and "fused into one solid"
                  in n and "part by part" in n for n in notes_e)
          and not any(n.startswith("EMStudio: WARNING") for n in notes_e),
          notes_e)
    # ...and a SINGLE part that touches itself along that edge cannot be
    # helped by exporting part by part: it is a WARNING, by name, with the
    # counts openEMS will print.
    one = bridge[0].fuse([bridge[1], bridge[2]])
    clamp.Shape = one
    doc.recompute()
    stls_w, notes_w = classify("self_contact")
    t_w = geo.stl_topology(stls_w[0]["path"]) if stls_w else {}
    check("8k. a part touching itself along an edge is a WARNING naming it "
          "('Clamp assembly') with the triangles openEMS will refuse",
          len(stls_w) == 1 and t_w.get("refused", 0) > 0 and any(
              n.startswith("EMStudio: WARNING") and "'Clamp assembly'" in n
              and "at least {0} triangle(s) openEMS will refuse".format(
                  t_w["refused"]) in n for n in notes_w),
          (t_w.get("refused"), notes_w[:1]))

    # A surface that touches itself at a single POINT has no bad edge at all
    # — every edge is shared by exactly two triangles — yet CGAL refuses it
    # (its vertex rule). An imported mesh of two cubes meeting at a corner.
    import Mesh
    cubes = Part.makeBox(10, 10, 10).tessellate(0.1)
    pts = list(cubes[0]) + [p_ + V(10, 10, 10) for p_ in cubes[0]]
    tri = [tuple(t) for t in cubes[1]] + [
        tuple(i + len(cubes[0]) for i in t) for t in cubes[1]]
    mf = doc.addObject("Mesh::Feature", "Corner")
    mf.Mesh = Mesh.Mesh([[pts[i] for i in t] for t in tri])
    mf.Label = "Corner cubes"
    m.References = [(mf, "")]
    doc.recompute()
    stls_p, notes_p = classify("pinched")
    t_p = geo.stl_topology(stls_p[0]["path"]) if stls_p else {}
    check("8n. two cubes meeting at ONE corner (an imported mesh): no bad "
          "edge, one pinched point — and a WARNING that says so",
          t_p.get("nonmanifold") == 0 and t_p.get("open") == 0
          and t_p.get("pinched") == 1 and any(
              n.startswith("EMStudio: WARNING") and "'Corner cubes'" in n
              and "1 point(s) where the surface touches itself" in n
              for n in notes_p),
          ({k: t_p.get(k) for k in ("nonmanifold", "open", "pinched")},
           notes_p[:1]))
    # An imported "solid" with a HOLE (one triangle missing): nothing is
    # refused, so CSXCAD marks the open surface 2-D and openEMS counts no
    # grid point inside it — the body is NOT in the grid at all. The
    # warning must say THAT, not "touching".
    box_m = Part.makeBox(10, 10, 10, V(50, 0, 0)).tessellate(0.1)
    holed = doc.addObject("Mesh::Feature", "Holed")
    holed.Mesh = Mesh.Mesh([[box_m[0][i] for i in t] for t in box_m[1][1:]])
    holed.Label = "Holed box"
    m.References = [(holed, "")]
    doc.recompute()
    stls_o, notes_o = classify("holed")
    t_o = geo.stl_topology(stls_o[0]["path"]) if stls_o else {}
    check("8o. an imported mesh with a hole: open edges, nothing refused, "
          "and a WARNING that the body is NOT in the model at all",
          t_o.get("open", 0) > 0 and t_o.get("refused") == 0 and any(
              n.startswith("EMStudio: WARNING") and "'Holed box'" in n
              and "is NOT in the model at all" in n for n in notes_o),
          ({k: t_o.get(k) for k in ("open", "refused")}, notes_o[:1]))
    # A mesh too large to check (2,000,000 triangles; here the limit is
    # lowered to 10) is SAID to be unchecked — never a silent pass.
    orig_max = geo._TOPOLOGY_MAX_TRIANGLES
    try:
        geo._TOPOLOGY_MAX_TRIANGLES = 10
        stls_q, notes_q = classify("unchecked")
    finally:
        geo._TOPOLOGY_MAX_TRIANGLES = orig_max
    check("8p. an STL too large to check gets a NOTE that it was not "
          "checked (and no claim either way)",
          len(stls_q) == 1 and any(
              n.startswith("EMStudio: NOTE") and "'Holed box'" in n
              and "was not checked" in n for n in notes_q)
          and not any(n.startswith("EMStudio: WARNING") for n in notes_q),
          notes_q[:1])
    m.References = [(clamp, "")]

    # A tie on Priority with ONE PART of a fused STL is reported against
    # that part, not against the fused solid.
    clamp.Shape = Part.makeCompound(parts)
    blk = doc.addObject("Part::Feature", "Pad")
    blk.Shape = Part.makeBox(4, 4, 4, V(24, 3, 8))     # straddles the plate
    blk.Label = "Rubber pad"
    diel = material_mod.makeMaterial(doc, ana, name="Pad",
                                     category="Dielectric")
    diel.Label = "Rubber"
    diel.RelPermittivity = 3.0
    diel.References = [(blk, "")]
    diel.Priority = m.Priority
    doc.recompute()
    dd = os.path.join(work, "fuse_overlap")
    os.makedirs(dd, exist_ok=True)
    mats = wr._collect_materials(ana, dd)
    ov = wr._overlap_notes(mats)
    exact = parts[2].common(blk.Shape).Volume      # the plate's 16 mm^3
    check("8m. an equal-Priority overlap with a fused STL names the PART it "
          "overlaps ('Clamp assembly (solid 3 of 3)'), with its exact "
          "volume (%.4g mm^3)" % exact,
          any("'Clamp assembly (solid 3 of 3)'" in n and "'Rubber pad'" in n
              and "overlap by about {0:.4g} mm^3".format(exact) in n
              for n in ov), ov)
    FreeCAD.closeDocument(doc.Name)

    # DEFLECTION: min(diag * 0.005, mesh_res / 4, feature / 2). For the
    # forum's 1450.9 mm tube (18 mm OD, 1.2 mm wall) the v1.13 LINEAR term
    # was 7.25 mm, six times its wall — but that term never faceted it: the
    # 0.35 rad angular deflection (geometry._ANGULAR_DEFLECTION) sets those
    # facets, its STLs are byte-identical under both rules, and the real sag
    # is 0.034 mm (geometry.stl_deflection_mm's docstring; section 11
    # measures sag on the written STLs). This check pins the rule's terms,
    # not a faceting fix for that tube.
    diag = math.sqrt(18.0 ** 2 * 2 + 1450.9 ** 2)
    check("8l. tessellation deflection: the v1.13 rule with nothing known "
          "(%.4g mm), half the wall for the forum tube (0.6 mm), a quarter "
          "cell where that is finer" % (diag * 0.005),
          abs(geo.stl_deflection_mm(diag) - diag * 0.005) < 1e-12
          and abs(geo.stl_deflection_mm(diag, 124.9, 1.2) - 0.6) < 1e-12
          and abs(geo.stl_deflection_mm(diag, 2.0, 1.2) - 0.5) < 1e-12)


def _refine_section(wr, work):
    """9. Local refinement: per part, axis by axis, budgeted as a whole."""
    import FreeCAD
    import Part

    from emstudio.objects import material as material_mod
    from emstudio.objects.analysis import Analysis
    from emstudio.setup.solvers import find_openems_python
    from emstudio.solvers.openems import geometry as geo
    from emstudio.solvers.openems import preflight

    V = FreeCAD.Vector
    # -- the section profile, exact from the faces -------------------------
    rod_s = Part.makeCylinder(1.5, 600.0)
    pz, px = geo.axis_profile(rod_s, 2), geo.axis_profile(rod_s, 0)
    check("9a. axis_profile: a straight rod changes only at its two end "
          "planes ALONG its length, and over its whole width ACROSS it",
          pz is not None and pz[0] == [] and pz[1] == [0.0, 600.0]
          and px is not None and len(px[0]) == 1
          and abs(px[0][0][0] + 1.5) < 1e-9 and abs(px[0][0][1] - 1.5) < 1e-9,
          (pz, px))
    cone = Part.makeCone(5.0, 2.0, 50.0)
    tilt = Part.makeBox(100.0, 10.0, 2.0)
    tilt.rotate(V(0, 0, 0), V(0, 1, 0), 20)
    pc, pt = geo.axis_profile(cone, 2), geo.axis_profile(tilt, 0)
    check("9b. ...a cone along its axis and a tilted plate along its length "
          "are NOT extrusions: their whole extent is resolved",
          pc is not None and pc[0] == [(0.0, 50.0)]
          and pt is not None and len(pt[0]) == 1
          and pt[0][0][1] - pt[0][0][0] > 0.99 * tilt.BoundBox.XLength,
          (pc, pt))

    # -- the deck's line helper, pure: a gap a hair over the step is ONE
    # cell (stretched <= 5 %), never two half cells — a needless small cell
    # sets the timestep for the whole run (Courant).
    lines = [-376.0, -3.0, -1.5, 376.0]
    hair = wr._refine_lines(lines, [(-3.0, -1.5, 1.497)], 50.0, 1.4)
    wide = wr._refine_lines(lines, [(-3.0, -1.5, 1.4)], 50.0, 1.4)
    check("9k. the line helper: a 1.5 mm gap at a 1.497 mm step stays ONE "
          "cell (no line inside it); at 1.4 mm (7 % over) it is split",
          not [x for x in hair if -3.0 < x < -1.5]
          and len([x for x in wide if -3.0 < x < -1.5]) == 1,
          ([x for x in hair if -3.0 < x < -1.5],
           [x for x in wide if -3.0 < x < -1.5]))

    # -- a long thin rod and a small block, through the real writer -------
    doc = FreeCAD.newDocument("stlgate_refine")
    rod = doc.addObject("Part::Feature", "Rod")
    rod.Shape = rod_s
    rod.Label = "Long rod"
    blk_s = Part.makeBox(6, 6, 4, V(97, -3, 298))
    blk_s = blk_s.makeChamfer(1.0, [blk_s.Edges[0]])    # not a native box
    blk = doc.addObject("Part::Feature", "Block")
    blk.Shape = blk_s
    blk.Label = "Small block"
    ana, solver = _analysis(doc, 100e6, 300e6, mr=20,
                            port_line=((1.5, 0, 300), (97, 0, 300)))
    solver.ComputeFarField = False
    solver.NearFieldPlane = "None"
    m = material_mod.makeMaterial(doc, ana, name="RodPEC",
                                  category="Metal (PEC)")
    m.References = [(rod, ""), (blk, "")]
    doc.recompute()
    res = _C0 / 300e6 * 1e3 / 20                # the global cell, 50 mm
    f_rod = 2.0 * rod_s.Volume / rod_s.Area
    f_blk = 2.0 * blk_s.Volume / blk_s.Area
    h_rod, h_blk = f_rod, f_blk         # metal: one cell per 2V/A
    d = os.path.join(work, "refine")
    _deck, text = _deck_or_fail(wr, ana, solver, d,
                                "9c. the rod + block model writes a deck")
    python = find_openems_python()
    if text and python:
        # (in the deck's own directory: the deck reads its STLs from there)
        _x, xml, out = _preview(python, d, text)
        xs, zs = _grid_lines(xml, "x"), _grid_lines(xml, "z")

        def gaps(v, lo, hi):
            return [b - a for a, b in zip(v[:-1], v[1:])
                    if a >= lo - 1e-9 and b <= hi + 1e-9]
        across = gaps(xs, -1.5, 1.5)
        across_b = gaps(xs, 97.0, 103.0)
        # CONTROL: v1.13's per-body cap refused to refine this rod at all
        # (1,201 lines along its length at a third of its feature).
        capped = wr._stl_refinement(
            {"start": (-1.5, -1.5, 0.0), "stop": (1.5, 1.5, 600.0),
             "min_feature": f_rod}, res) is None
        # (within the 5 % a cell may stretch rather than split in two:
        # writer._RF_STRETCH, in the deck's own helper)
        tol = 1.05 * (1 + 1e-9)
        # METAL IS REFINED TO PRESENCE: one cell per 2V/A (the refusal's own
        # threshold), so the 3 mm rod (2V/A 1.5 mm) is TWO cells across —
        # three cells per feature, the dielectric rule, would be six.
        check("9c. lines at the rod's own %.3g mm ACROSS it — exactly 2 cells "
              "over its 3 mm, one per 2V/A — and at the block's %.3g mm "
              "across it (CONTROL: v1.13's cap gave this rod nothing)"
              % (h_rod, h_blk),
              capped and len(across) == 2 and max(across) <= h_rod * tol
              and across_b and max(across_b) <= h_blk * tol,
              (across, max(across_b or [0])))
        mid = gaps(zs, 120.0, 240.0) + gaps(zs, 360.0, 480.0)
        check("9d. ...but ALONG the rod, away from its ends and the block, "
              "the grid stays coarse (every cell >= 10 mm; measured >= %.3g)"
              % min(mid or [0]), mid and min(mid) >= 10.0)
        ends = gaps(zs, -h_rod, h_rod) + gaps(zs, 600.0 - h_rod, 600.0 + h_rod)
        near_b = gaps(zs, 298.0, 302.0)
        check("9e. ...fine at the rod's two end planes and through the "
              "block's height (<= its step)",
              ends and max(ends) <= h_rod * tol
              and near_b and max(near_b) <= h_blk * tol,
              (max(ends or [0]), max(near_b or [0])))
        ratio = float(ana.MeshSmoothRatio)
        worst = 1.0
        small = float("inf")
        for v in (xs, _grid_lines(xml, "y"), zs):
            g = [b - a for a, b in zip(v[:-1], v[1:])]
            small = min(small, min(g))
            worst = max(worst, max(max(g[i] / g[i + 1], g[i + 1] / g[i])
                                   for i in range(len(g) - 1)))
        # The grading is MeshSmoothRatio (1.4) wherever the helper lays the
        # lines; at an existing line (a part's plane, a port line) a gap can
        # only be cut where it is, so the jump there can reach ~2 — the thirds
        # rule's own 1:2. Without grading it is ~30 (1.5 mm against 50 mm).
        check("9f. graded: no cell more than 2.25x its neighbour (measured "
              "%.3g; %.3g away from existing lines) and none a sliver "
              "(smallest %.3g mm >= half the finest step)"
              % (worst, ratio, small),
              worst <= 2.25 and small >= 0.5 * min(h_rod, h_blk))
        got = [len(_grid_lines(xml, a)) for a in "xyz"]
        os.makedirs(os.path.join(d, "floor"), exist_ok=True)
        mats = wr._collect_materials(ana, os.path.join(d, "floor"))
        plan = wr._refinement_plan(mats, res)
        lam_c = _C0 / 200e6 * 1e3
        _g0, _g1, dlo, dhi, _nn = wr._domain(
            ana, mats, lam_c, mesh_res_mm=res,
            boundaries=Analysis.boundary_list(ana))
        floor = wr._refined_floor(mats, plan, dlo, dhi, res, ratio)
        cells = got[0] * got[1] * got[2] if got else 0
        check("9g. the whole refined grid is budgeted, and the writer's count "
              "is a true FLOOR within 10 %% of openEMS's (%s vs %s; %s cells, "
              "under the index limit)" % (list(floor), got, format(cells, ",")),
              got and all(floor[i] <= got[i] for i in range(3))
              and all(floor[i] >= 0.9 * got[i] for i in range(3))
              and 0 < cells < preflight.OPENEMS_MAX_CELLS)
        a = text.find("# --- local refinement, axis by axis")
        check("9h. the refinement block comes after the ports and before the "
              "final smoothing (so it only subdivides existing gaps, and the "
              "preflight counts the final grid)",
              0 < text.rfind("AddLumpedPort(") < a
              < text.find("mesh.SmoothMeshLines('all'") < text.find("_snap("))
    elif text:
        check("9c-9h. live half NOT RUN: needs the openEMS python", False)

    # -- RAM: refuse, never degrade per machine ----------------------------
    # A machine whose RAM lies BETWEEN what the bounding-box floor needs
    # (O1's check at the top of write_deck, which must pass) and what the
    # refined grid needs (this check, which must refuse) — derived here from
    # both counts, so the test does not depend on this box's RAM.
    dr = os.path.join(d, "ram_floor")
    os.makedirs(dr, exist_ok=True)
    mats_r = wr._collect_materials(ana, dr)
    _g0, _g1, dlo_r, dhi_r, _nn = wr._domain(
        ana, mats_r, _C0 / 200e6 * 1e3, mesh_res_mm=res,
        boundaries=Analysis.boundary_list(ana))
    fl_r = wr._refined_floor(mats_r, wr._refinement_plan(mats_r, res),
                             dlo_r, dhi_r, res, float(ana.MeshSmoothRatio))
    b_ref = preflight.bytes_needed(preflight.cell_count(fl_r))
    b_box = preflight.bytes_needed(preflight.cell_count(
        preflight.grid_lower_bound(ana, solver)["lines"]))
    fake_ram = 0.5 * (b_box + b_ref) / preflight.OPENEMS_RAM_FRACTION
    orig_ram = wr.preflight.physical_ram_bytes
    try:
        wr.preflight.physical_ram_bytes = lambda: fake_ram
        for sub in ("ram", "ram_allowed"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        try:
            wr.write_deck(ana, solver, os.path.join(d, "ram"))
            why = ""
        except wr.OpenEMSModelError as exc:
            why = str(exc)
        os.environ[preflight.OPENEMS_ALLOW_LARGE_ENV] = "1"
        try:
            wr.write_deck(ana, solver, os.path.join(d, "ram_allowed"))
            why_ok = ""
        except wr.OpenEMSModelError as exc:
            why_ok = str(exc)
    finally:
        wr.preflight.physical_ram_bytes = orig_ram
        os.environ.pop(preflight.OPENEMS_ALLOW_LARGE_ENV, None)
    check("9i. a refined grid over this machine's RAM (a %.3g MB box: the "
          "box floor fits, the refined grid does not) is REFUSED with the "
          "parts that set it, never quietly coarsened; the override lets it "
          "run" % (fake_ram / 1e6),
          b_box < b_ref and "needs about" in why
          and "Local refinement of the thin parts sets this grid" in why
          and "'Long rod'" in why and not why_ok,
          (why[:60], why_ok[:60]))
    FreeCAD.closeDocument(doc.Name)

    # -- ...but a DIELECTRIC part v1.13 never refined (too large to blanket)
    # and RAN is not refused for RAM: that machine gets v1.13's model back
    # (its axis-by-axis refinement left out), with a NOTE. A tilted 2 mm
    # dielectric plate, 300 mm across: three cells per 2 mm across both of
    # its inclined axes is ~6 M cells; the box floor is a few thousand.
    doc3 = FreeCAD.newDocument("stlgate_shed")
    slab_s = Part.makeBox(300.0, 300.0, 2.0)
    slab_s.rotate(V(150, 150, 0), V(0, 1, 0), 30)
    slab = doc3.addObject("Part::Feature", "Slab")
    slab.Shape = slab_s
    slab.Label = "Tilted radome panel"
    ana3, solver3 = _analysis(doc3, 100e6, 300e6, mr=20,
                              port_line=((-200, 150, 0), (-190, 150, 0)))
    solver3.ComputeFarField = False
    solver3.NearFieldPlane = "None"
    dm3 = material_mod.makeMaterial(doc3, ana3, name="Radome",
                                    category="Dielectric")
    dm3.RelPermittivity = 3.0
    dm3.References = [(slab, "")]
    doc3.recompute()
    d3 = os.path.join(work, "shed")
    os.makedirs(os.path.join(d3, "f"), exist_ok=True)
    mats3 = wr._collect_materials(ana3, os.path.join(d3, "f"))
    _g0, _g1, dlo3, dhi3, _nn = wr._domain(
        ana3, mats3, _C0 / 200e6 * 1e3, mesh_res_mm=res,
        boundaries=Analysis.boundary_list(ana3))
    plan3 = wr._refinement_plan(mats3, res)
    fl3 = wr._refined_floor(mats3, plan3, dlo3, dhi3, res,
                            float(ana3.MeshSmoothRatio))
    b3_ref = preflight.bytes_needed(preflight.cell_count(fl3))
    b3_box = preflight.bytes_needed(preflight.cell_count(
        preflight.grid_lower_bound(ana3, solver3)["lines"]))
    ram3 = 0.5 * (b3_box + b3_ref) / preflight.OPENEMS_RAM_FRACTION
    zoned3 = [e for e in plan3 if e["zones"] is not None]
    orig_ram = wr.preflight.physical_ram_bytes
    try:
        wr.preflight.physical_ram_bytes = lambda: ram3
        d3w = os.path.join(d3, "w")
        os.makedirs(d3w, exist_ok=True)
        try:
            deck3, _z, _n = wr.write_deck(ana3, solver3, d3w)
            notes3 = wr.deck_model_notes(deck3)
            why3 = ""
        except wr.OpenEMSModelError as exc:
            notes3, why3 = [], str(exc)
    finally:
        wr.preflight.physical_ram_bytes = orig_ram
    check("9l. a dielectric part refined axis by axis that this machine's RAM "
          "(a %.3g MB box) cannot hold: NOT refused — its refinement is left "
          "out (v1.13's model) and a NOTE says so" % (ram3 / 1e6),
          len(zoned3) == 1 and b3_box < b3_ref and not why3 and any(
              lvl == "note" and "'Tilted radome panel'" in t
              and "was left out" in t for lvl, t in notes3),
          (why3[:60], [t[:60] for _l, t in notes3]))
    FreeCAD.closeDocument(doc3.Name)

    # -- overlapping dielectric blankets never interleave ------------------
    doc2 = FreeCAD.newDocument("stlgate_untangle")
    shank = doc2.addObject("Part::Feature", "Shank")
    shank.Shape = Part.makeCylinder(1.5, 12.0, V(0, 0, 0))
    ring = doc2.addObject("Part::Feature", "Ring")
    ring.Shape = Part.makeCylinder(2.75, 2.4, V(0, 0, 6)).cut(
        Part.makeCylinder(1.5, 2.4, V(0, 0, 6)))
    ana2, solver2 = _analysis(doc2, 2.0e9, 3.0e9, mr=20,
                              port_line=((-10, 0, 3), (-1.5, 0, 3)))
    solver2.ComputeFarField = False
    solver2.NearFieldPlane = "None"
    dm = material_mod.makeMaterial(doc2, ana2, name="Nylon",
                                   category="Dielectric")
    dm.RelPermittivity = 3.0
    dm.References = [(shank, ""), (ring, "")]
    doc2.recompute()
    d2 = os.path.join(work, "untangle")
    _deck2, text2 = _deck_or_fail(wr, ana2, solver2, d2,
                                  "9j. the shank + ring model writes a deck")
    f_ring = 2.0 * ring.Shape.Volume / ring.Shape.Area
    if python and text2:
        _x, xml2, _o = _preview(python, d2, text2)
        small2 = min(min(b - a for a, b in zip(v[:-1], v[1:]))
                     for v in (_grid_lines(xml2, a) for a in "xyz"))
        check("9j. two overlapping dielectric parts (a shank and the ring on "
              "it) blanketed at their own steps share ONE coherent set of "
              "lines: no sliver (smallest cell %.3g mm, the finer step %.3g)"
              % (small2, f_ring / wr.MIN_CELLS_ACROSS_FEATURE),
              small2 >= 0.5 * f_ring / wr.MIN_CELLS_ACROSS_FEATURE)
    elif not python:
        check("9j. live half NOT RUN: needs the openEMS python", False)
    FreeCAD.closeDocument(doc2.Name)


# =========================================================================
# v1.14.0 review — the fill advice: a coax is not a tube, a tilted tube is
# =========================================================================
def _coax_tilt_section(wr, work):
    """10. The fill advice never tells a coax to fill, and measures a tube
    in its own frame (the two defects the v1.14.0 review upheld)."""
    import FreeCAD
    import Part

    from emstudio.objects import material as material_mod
    from emstudio.solvers.openems import geometry as geo

    V = FreeCAD.Vector

    def _tube(r_out, wall, length):
        return Part.makeCylinder(r_out, length).cut(
            Part.makeCylinder(r_out - wall, length))

    # -- the bore test itself, on the review's own small coax ---------------
    # 6 mm shield with a 0.3 mm wall (400 mm), a 1 mm inner conductor
    # (550 mm: it runs out of the top as a monopole), PTFE between them.
    sh = _tube(3.0, 0.3, 400.0)
    inner = Part.makeCylinder(0.5, 550.0)
    ptfe = Part.makeCylinder(2.7, 400.0).cut(Part.makeCylinder(0.5, 400.0))
    h = geo.hollow_envelope(sh, 2.0 * sh.Volume / sh.Area)

    def occ(*others):
        # (getattr: on a tree without the bore test this is a FAIL line,
        # never a traceback that hides every check after it)
        fn = getattr(geo, "bore_occupant", None)
        return fn(sh, h, list(others)) if (h and fn) else "no bore test"

    check("10a. a coax shield's bore holds its inner conductor, its PTFE, "
          "and a port at mid-length — each found ON ITS OWN",
          bool(h) and occ({"name": "'Inner'", "geo": inner}) == "'Inner'"
          and occ({"name": "'PTFE'", "geo": ptfe}) == "'PTFE'"
          and occ({"name": "port 1", "segment": ((0.5, 0, 200.0),
                                                 (2.7, 0, 200.0))})
          == "port 1", h)
    gnd = Part.makeBox(200.0, 200.0, 2.0, V(-100.0, -100.0, -2.0))
    # A wire running ALONGSIDE the shield, outside it but inside its square
    # bounding box (the corner the round tube does not fill): only the
    # ring test — rays escaping on the far side — says it is not inside.
    beside = Part.makeCylinder(0.3, 400.0, V(2.6, 2.6, 0.0))
    check("10b. CONTROL: the empty shield standing on a ground plane (its "
          "open end ON the plane), a wire running alongside it in its box "
          "corner, and the shield itself are NOT occupants",
          occ({"name": "'Ground'", "geo": gnd}) is None
          and occ({"name": "'Beside'", "geo": beside}) is None
          and occ({"name": "'Shield'", "geo": sh}) is None)
    # The MOUTH of an open end is not its inside (four sloped radials meet
    # at a hub and poke ~11 mm into each other's 9 mm bores): a rod reaching
    # one bore-width in is at the mouth; three widths in, it is inside.
    bore = 2 * (3.0 - 0.3)
    poke1 = Part.makeCylinder(0.5, 50.0 + 1.0 * bore, V(0, 0, -50.0))
    poke3 = Part.makeCylinder(0.5, 50.0 + 3.0 * bore, V(0, 0, -50.0))
    check("10c. a rod reaching 1 bore-width into the open mouth is NOT "
          "inside; 3 widths in, it IS",
          occ({"name": "'Rod'", "geo": poke1}) is None
          and occ({"name": "'Rod'", "geo": poke3}) == "'Rod'")
    # The same coax tilted 45 degrees: found in the bore's OWN frame.
    rot = (V(0, 0, 0), V(0, 1, 0), 45.0)
    sh_t, in_t = sh.copy(), inner.copy()
    sh_t.rotate(*rot)
    in_t.rotate(*rot)
    h_t = geo.hollow_envelope(sh_t, 2.0 * sh_t.Volume / sh_t.Area)
    check("10d. ...and tilted 45 degrees, the inner conductor is still "
          "found inside its shield",
          bool(h_t) and getattr(geo, "bore_occupant", None) is not None
          and geo.bore_occupant(
              sh_t, h_t, [{"name": "'Inner'", "geo": in_t}]) == "'Inner'",
          h_t)

    # -- through write_deck: a coax shield is NEVER told to fill ------------
    # A FOIL shield (OD 100 mm, 0.01 mm wall — the 4a tube, which local
    # refinement cannot hold on any machine), a 43 mm inner conductor (a
    # 50-ohm air line) and the feed port across the gap at mid-length.
    doc = FreeCAD.newDocument("stlgate_coax")
    r_s, r_i = _FOIL_OD / 2.0, 21.5
    shield = doc.addObject("Part::Feature", "Shield")
    shield.Shape = _tube(r_s, _FOIL_WALL, _TUBE_LEN)
    shield.Label = "Coax shield"
    core = doc.addObject("Part::Feature", "Core")
    core.Shape = Part.makeCylinder(r_i, _TUBE_LEN)
    core.Label = "Coax inner"
    ana, solver = _analysis(doc, 80e6, 120e6, mr=20,
                            port_line=((r_i, 0, _TUBE_LEN / 2.0),
                                       (r_s - _FOIL_WALL, 0,
                                        _TUBE_LEN / 2.0)))
    metal = material_mod.makeMaterial(doc, ana, name="CoaxPEC",
                                      category="Metal (PEC)")
    metal.References = [(shield, ""), (core, "")]
    doc.recompute()
    msg = _refusal_of(wr, ana, solver, os.path.join(work, "coax")) or ""
    body = msg.split("left at the global cell: ", 1)[-1]
    check("10e. a foil coax shield around its inner conductor is refused "
          "BY NAME and told it is a coax that must NOT be filled — never "
          "'fill the bore' (CONTROL: 4c, the same foil tube EMPTY, is "
          "offered the solid rod)",
          "'Coax shield'" in body and "coax or feed structure" in body
          and "TEM" in body and "must NOT be filled" in body
          and "solid rod" not in body and "fill the bore" not in body,
          body[:90])
    # Only the PORT in the bore (the inner conductor taken out of the
    # model): the port alone makes it a feed structure — which proves the
    # ports reach the refusal's bore test, not just the materials.
    metal.References = [(shield, "")]
    doc.recompute()
    msg_p = _refusal_of(wr, ana, solver, os.path.join(work, "coax_port")) or ""
    check("10f. ...and with only the feed PORT inside it, still: 'port 1' "
          "lies inside it, must NOT be filled",
          "port 1 lies inside it" in msg_p and "solid rod" not in msg_p,
          msg_p[-90:])
    # WHOLE MODEL: beside a foil reflector, the coax shield is NOT counted
    # as fillable — the thinnest part left is the shield, as drawn.
    foil = Part.makeBox(600.0, 600.0, _SHEET_FOIL)
    foil.rotate(V(300, 300, 0), V(0, 1, 0), 30)
    fb = foil.BoundBox
    foil.translate(V(r_s + 200.0 - fb.XMin, -300.0 - fb.YMin,
                     300.0 - fb.ZMin))
    refl = doc.addObject("Part::Feature", "Foil")
    refl.Shape = foil
    refl.Label = "Reflector foil"
    metal.References = [(shield, ""), (core, ""), (refl, "")]
    doc.recompute()
    msg_w = _refusal_of(wr, ana, solver, os.path.join(work, "coax_w")) or ""
    whole = (msg_w.split("For the model as a whole", 1)[1]
             if "For the model as a whole" in msg_w else "")
    check("10g. two refused objects: the whole-model verdict does NOT fill "
          "the coax — its thinnest part left is 'Coax shield' itself",
          bool(whole) and "(with every hollow part filled)" not in whole
          and "the thinnest part left is 'Coax shield'" in whole,
          msg_w[-90:])
    FreeCAD.closeDocument(doc.Name)

    # -- a tube is measured in its OWN frame --------------------------------
    r_t = _TUBE_OD / 2.0
    tb = _tube(r_t, _TUBE_WALL, _TUBE_LEN)
    f_t = 2.0 * tb.Volume / tb.Area
    tilt = tb.copy()
    tilt.rotate(V(0, 0, 0), V(0, 1, 0), 45.0)
    h0 = geo.hollow_envelope(tb, f_t)
    h45 = geo.hollow_envelope(tilt, f_t)

    def _same(a, b):
        return (bool(a) and bool(b) and abs(a["length_mm"] - b["length_mm"])
                < 1e-6 and a["closed"] == b["closed"]
                and all(abs(x - y) < 1e-6 for x, y in
                        zip(sorted(a["outline_mm"]), sorted(b["outline_mm"]))))
    check("10h. the forum's 18/1.2 mm, 1450 mm tube tilted 45 degrees reads "
          "exactly as it does upright: outline 18 x 18, length 1450, an "
          "OPEN tube (the global box read it as a CLOSED 1038 mm shell)",
          _same(h0, h45) and (h0 or {}).get("frame", 0) is None
          and (h45 or {}).get("frame") is not None
          and (h45 or {}).get("closed") is False,
          (h45 or {}).get("outline_mm"))
    flange = tb.fuse(Part.makeCylinder(50.0, 5.0)).removeSplitter()
    check("10i. a tube with a 100 mm flange is NOT described (its box is "
          "not its cross-section: no advice rather than a 100 mm 'rod'); "
          "CONTROL: the same tube without it is",
          geo.hollow_envelope(flange, 2.0 * flange.Volume / flange.Area)
          is None and bool(h0))
    nurbs = tilt.toNurbs()
    nurbs0 = tb.toNurbs()
    check("10j. a tube whose faces carry no exact axis (B-splines) gets NO "
          "description, tilted or upright — no frame can be READ, so no "
          "advice — never one measured in the global box",
          geo.hollow_envelope(nurbs, 2.0 * nurbs.Volume / nurbs.Area) is None
          and geo.hollow_envelope(nurbs0, 2.0 * nurbs0.Volume / nurbs0.Area)
          is None)

    # -- through write_deck: the review's sloped-radial ground plane --------
    # Four 10 mm radials sloping down at 45 degrees from a hub, 140-150 MHz.
    # The refusal names a radial — and its fill price must be the FILLED
    # 10 mm rod's: 2V/A = D L / (2 L + D) = 4.95 mm, MeshResolution 404
    # (lambda_min 1998.6 mm), never the 211 the global box's 10 x 375 mm
    # "closed shell" priced it at (a user who followed that was refused
    # again). ⚠ FOIL walls (0.05 mm), not the review's 0.5 mm: with 0.5 mm
    # the index budget drops ONE radial and the other three still need
    # ~939 M cells (~117 GB) — under this 192 GB box's RAM limit, so the
    # per-part refusal (and its advice) fires here, but OVER an 8 GB Mac's,
    # where the RAM refusal fires instead and gives no per-part advice at
    # all (measured on the macOS build host). At 0.05 mm each radial alone
    # is over openEMS's index on every machine, so every machine reaches
    # the per-part refusal; the filled rod's price does not depend on the
    # wall. (The review's own 0.5 mm model reads "MeshResolution 404 is
    # enough" on this box too — its probe, re-run after the fix.)
    doc2 = FreeCAD.newDocument("stlgate_radials")
    refs = []
    for k, (axv, ang) in enumerate(((V(0, 1, 0), 135), (V(0, 1, 0), -135),
                                    (V(1, 0, 0), 135), (V(1, 0, 0), -135))):
        s = _tube(5.0, _SHEET_FOIL, 520.0)
        s.rotate(V(0, 0, 0), axv, ang)
        o = doc2.addObject("Part::Feature", "Radial%d" % k)
        o.Shape = s
        o.Label = "Radial %d" % (k + 1)
        refs.append((o, ""))
    # The port only has to exist: along +X (_analysis' direction), above
    # the hub, clear of every radial.
    ana2, solver2 = _analysis(doc2, 140e6, 150e6, mr=20,
                              port_line=((0, 0, 20), (10, 0, 20)))
    m2 = material_mod.makeMaterial(doc2, ana2, name="RadialPEC",
                                   category="Metal (PEC)")
    m2.References = refs
    doc2.recompute()
    msg_r = _refusal_of(wr, ana2, solver2, os.path.join(work, "radials")) or ""
    lam2 = _C0 / 150e6 * 1e3
    mr_rod = int(math.ceil(lam2 / (10.0 * 520.0 / (2 * 520.0 + 10.0))))
    check("10k. sloped tube radials: the refusal offers the solid ROD at its "
          "filled price, 'MeshResolution {0} is enough' — not a 'closed "
          "shell' priced from the global box".format(mr_rod),
          "solid rod" in msg_r and "closed shell" not in msg_r
          and "MeshResolution {0} is enough".format(mr_rod) in msg_r,
          msg_r[-120:])
    FreeCAD.closeDocument(doc2.Name)


# =========================================================================
# 11. The v1.14.0 review's export, port and cut-off fixes
# =========================================================================

def _rim_sag(path, z, r, cx=0.0, cy=0.0):
    """(triangles, rim vertices, worst chord sag in mm) of the circle of
    radius ``r`` about (cx, cy) at height ``z`` in a WRITTEN STL.

    From the largest angular GAP between consecutive rim vertices, not from
    triangle edges: a disc's cap is triangulated with chords ACROSS it,
    whose 'sag' would read as most of the radius (the trap an edge-based
    measure fell into on a probe of this very fix).
    """
    from emstudio.solvers.openems import geometry as geo
    tris = geo._read_stl_triangles(path) or []
    angs = set()
    for t in tris:
        for q in t:
            if abs(q[2] - z) < 1e-3 and abs(
                    math.hypot(q[0] - cx, q[1] - cy) - r) < 1e-3:
                angs.add(round(math.atan2(q[1] - cy, q[0] - cx), 9))
    a = sorted(angs)
    if len(a) < 3:
        return len(tris), len(a), float("inf")
    gap = max([y - x for x, y in zip(a[:-1], a[1:])]
              + [a[0] + 2.0 * math.pi - a[-1]])
    return len(tris), len(a), r * (1.0 - math.cos(gap / 2.0))


def _wr28(doc, f1, f2):
    """The review's WR-28 probe: a 20 mm PEC section of WR-28 (the shipped
    horn's feed), a RectWaveguide TE10 port 2 mm in, 25 samples, PML."""
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    V = FreeCAD.Vector
    a, b, t, length = 7.112, 3.556, 0.5, 20.0

    def rect(w, h, z):
        return Part.makePolygon([V(-w / 2, -h / 2, z), V(w / 2, -h / 2, z),
                                 V(w / 2, h / 2, z), V(-w / 2, h / 2, z),
                                 V(-w / 2, -h / 2, z)])
    feed = doc.addObject("Part::Feature", "Feed")
    feed.Shape = Part.Face(rect(a + 2 * t, b + 2 * t, 0)).extrude(
        V(0, 0, length)).cut(Part.Face(rect(a, b, -1)).extrude(
            V(0, 0, length + 2)))
    face = doc.addObject("Part::Feature", "PortFace")
    face.Shape = Part.Face(rect(a, b, 2.0))
    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = f1
    ana.FrequencyStop = f2
    ana.FrequencyPoints = 25
    ana.MeshResolution = 15
    ana.DomainPaddingWavelengths = 0.5
    for s in ("Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"):
        setattr(ana, "Boundary" + s, "PML_8")
    m = material_mod.makeMaterial(doc, ana, name="WGPEC")
    m.References = [(feed, "")]
    port = ports_mod.makeLumpedPort(doc, ana, name="WGPort", direction="+Y")
    port.PortType = "RectWaveguide"
    port.WaveguideMode = "TE10"
    port.PropagationDirection = "+Z"
    port.References = [(face, "")]
    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    solver.ComputeFarField = False
    solver.NearFieldPlane = "None"
    doc.recompute()
    return ana, solver


def _review_fix_section(wr, work):
    """11. Tessellation on a REAL export, a port drawn in air, and a band
    below a waveguide cut-off (the v1.14.0 review's upheld defects and the
    follow-ups its stages asked for)."""
    import FreeCAD
    import Part

    from emstudio.objects import material as material_mod
    from emstudio.solvers.openems import geometry as geo

    V = FreeCAD.Vector

    # -- V1: the deflection rule on the STLs the deck writer WRITES --------
    # The only check on the v1.14 rule was 8l, on stl_deflection_mm() alone:
    # dropping mesh_res_mm / feature_mm at the export call sites left this
    # gate 115/115 green (review mutations). These two bodies are where the
    # new terms BIND — large radii, where the angular deflection's 36 facets
    # sag more than the bound — written through _collect_materials, the
    # writer's own export path. 2-3 GHz at MeshResolution 20: a 4.997 mm
    # cell, so cell/4 = 1.249 mm.
    doc = FreeCAD.newDocument("stlgate_tess")
    ana, _s = _analysis(doc, 2.0e9, 3.0e9, mr=20,
                        port_line=((-605, 0, 20), (-601, 0, 20)))
    disc = doc.addObject("Part::Feature", "Disc")
    disc.Shape = Part.makeCylinder(600.0, 40.0)
    disc.Label = "Big disc"
    ring_shape = Part.makeCylinder(400.0, 60.0, V(2000, 0, 0)).cut(
        Part.makeCylinder(398.0, 60.0, V(2000, 0, 0)))
    ring = doc.addObject("Part::Feature", "Ring")
    ring.Shape = ring_shape
    ring.Label = "Thin ring"
    m = material_mod.makeMaterial(doc, ana, name="TessPEC",
                                  category="Metal (PEC)")
    m.References = [(disc, ""), (ring, "")]
    doc.recompute()
    d = os.path.join(work, "tess")
    os.makedirs(d, exist_ok=True)
    mats = wr._collect_materials(ana, d, notes=[])
    paths = {p["label"]: p.get("path") for mm in mats for p in mm["prims"]}
    cell4 = _C0 / 3.0e9 / 1e-3 / 20 / 4.0
    feat2 = geo.min_feature_mm(shape=ring_shape) / 2.0
    ctl = os.path.join(work, "tess_v113")
    os.makedirs(ctl, exist_ok=True)
    disc_old = geo.export_stl(disc.Shape, os.path.join(ctl, "disc.stl"))
    ring_old = geo.export_stl(ring_shape, os.path.join(ctl, "ring.stl"))
    got = (_rim_sag(paths["Big disc"], 0.0, 600.0) if paths.get("Big disc")
           else (0, 0, float("inf")))
    old = _rim_sag(disc_old, 0.0, 600.0)
    check("11a. the 600 mm-radius disc's WRITTEN STL sags at most a quarter "
          "cell ({0:.4g} mm): mesh_res reaches the export".format(cell4),
          got[2] <= cell4, "sag %.3f mm, %d rim facets, %d triangles"
          % (got[2], got[1], got[0]))
    check("11b. CONTROL: under the v1.13 rule the same disc sags MORE than "
          "that (the term binds here, so 11a can fail)", old[2] > cell4,
          "sag %.3f mm, %d rim facets" % (old[2], old[1]))
    got = (_rim_sag(paths["Thin ring"], 0.0, 400.0, 2000.0) if
           paths.get("Thin ring") else (0, 0, float("inf")))
    old = _rim_sag(ring_old, 0.0, 400.0, 2000.0)
    check("11c. the 400 mm ring with a 2 mm wall: its WRITTEN STL sags at "
          "most half its 2V/A ({0:.4g} mm): the part's feature reaches the "
          "export".format(feat2), got[2] <= feat2,
          "sag %.3f mm, %d rim facets, %d triangles" % (got[2], got[1],
                                                        got[0]))
    check("11d. CONTROL: under the v1.13 rule the ring sags more than that",
          old[2] > feat2, "sag %.3f mm, %d rim facets" % (old[2], old[1]))
    # The corrected claim (B5): the forum tube's facets are set by the
    # ANGULAR deflection, so its STL never changed. If this ever fails, the
    # docstring of stl_deflection_mm and the CHANGELOG line are wrong again.
    tube = Part.makeCylinder(_TUBE_OD / 2.0, 1450.9).cut(
        Part.makeCylinder(_TUBE_OD / 2.0 - _TUBE_WALL, 1450.9))
    t_old = geo.export_stl(tube, os.path.join(ctl, "tube_v113.stl"))
    t_new = geo.export_stl(tube, os.path.join(ctl, "tube_v114.stl"),
                           mesh_res_mm=124.9,
                           feature_mm=geo.min_feature_mm(shape=tube))
    with open(t_old, "rb") as f_a, open(t_new, "rb") as f_b:
        same = f_a.read() == f_b.read()
    check("11e. the forum's 18/1.2 mm tube writes the SAME STL under both "
          "rules (36 rim facets, 0.034 mm sag): the new terms never bound it",
          same, "%d rim facets, sag %.3f mm" % _rim_sag(t_new, 0.0, 9.0)[1:])
    FreeCAD.closeDocument(doc.Name)

    # -- F-c: a lumped port with an end in AIR is a WARNING -----------------
    # A dipole along x: two 2 x 2 x 28 mm PEC arms with a 2 mm gap; then the
    # same with ROD arms (curved, so STL prims refined per part).
    doc = FreeCAD.newDocument("stlgate_air")
    ana, solver = _analysis(doc, 2.0e9, 3.0e9, mr=20,
                            port_line=((-1, 0, 0), (1, 0, 0)))
    feed = doc.getObject("FeedLine")
    arm_a = doc.addObject("Part::Feature", "ArmA")
    arm_a.Shape = Part.makeBox(28, 2, 2, V(1, -1, -1))
    arm_a.Label = "Arm A"
    arm_b = doc.addObject("Part::Feature", "ArmB")
    arm_b.Shape = Part.makeBox(28, 2, 2, V(-29, -1, -1))
    arm_b.Label = "Arm B"
    m = material_mod.makeMaterial(doc, ana, name="AirPEC",
                                  category="Metal (PEC)")
    m.References = [(arm_a, ""), (arm_b, "")]
    doc.recompute()

    def notes_for(tag, a, b):
        feed.Shape = Part.makeLine(V(*a), V(*b))
        doc.recompute()
        said = []
        real_say = wr._say
        wr._say = lambda n: said.extend(n or ())
        try:
            dk, _txt = _deck_or_fail(wr, ana, solver,
                                     os.path.join(work, "air_" + tag),
                                     "11. the dipole deck '%s' writes" % tag)
        finally:
            wr._say = real_say
        back = wr.deck_model_notes(dk) if dk else []
        return ([t for lvl, t in back if lvl == "warning"
                 and "touches no metal" in t], back, said)

    w, back, said = notes_for("short", (-1, 0, 0), (0, 0, 0))
    check("11f. a port whose end stops 1 mm short of its arm: a WARNING in "
          "the deck naming port 1, that end (x = 0), the nearest metal "
          "('Arm A') and the 1 mm, FIRST among the model notes, and said in "
          "the Report view", len(w) == 1 and "port 1" in w[0]
          and "one end" in w[0] and "x = 0 mm" in w[0] and "'Arm A'" in w[0]
          and "1 mm away" in w[0] and back[:1] == [("warning", w[0])]
          and any("touches no metal" in n for n in said), (w or back)[:1])
    w, back, said = notes_for("beside", (-1, 5, 0), (1, 5, 0))
    check("11g. a port drawn BESIDE the gap (4 mm off both arms): one WARNING "
          "naming both ends and both arms", len(w) == 1 and "either end" in w[0]
          and "'Arm A'" in w[0] and "'Arm B'" in w[0]
          and w[0].count("4 mm away") == 2, w[:1])
    w, back, said = notes_for("across", (-1, 0, 0), (1, 0, 0))
    w2, back2, _s2 = notes_for("inside", (-3, 0, 0), (3, 0, 0))
    check("11h. CONTROL: drawn arm to arm (ends ON the faces), or with both "
          "ends INSIDE the arms: no port WARNING", w == [] and w2 == []
          and back == [], (w + w2 + back)[:1])
    # Curved (STL) arms, refined per part: the contact test reads each
    # PART's own solid (distToShape 0 on its surface), names the part, and
    # judges by the part's local refinement step, not the 5 mm global cell.
    arm_a.Shape = Part.makeCylinder(1.0, 28.0, V(1, 0, 0), V(1, 0, 0))
    arm_b.Shape = Part.makeCylinder(1.0, 28.0, V(-29, 0, 0), V(1, 0, 0))
    # (r = 1 mm, 28 mm: 2V/A 0.966 mm, refined at one cell across it, so the
    # local tolerance is 0.097 mm against the global cell's 0.4997 mm.)
    w, back, _s = notes_for("rods", (-1, 0.9, 0), (1, 0.9, 0))
    w2, back2, _s2 = notes_for("rods_off", (-1, 1.3, 0), (1, 1.3, 0))
    check("11i. rod arms: ends on the rods' end faces touch (no WARNING); "
          "0.3 mm outside them — under a tenth of the 5 mm global cell, over "
          "a tenth of the rods' own refined cell — they do NOT, named by part",
          w == [] and len(w2) == 1 and "'Arm A'" in w2[0]
          and "'Arm B'" in w2[0] and w2[0].count("0.3 mm away") == 2,
          (w or w2 or back2)[:1])
    FreeCAD.closeDocument(doc.Name)

    # -- B4: a band below a waveguide port's cut-off -------------------------
    # openEMS's waveguide port returns NaN below its mode's cut-off; since
    # v1.14.0 a NaN refuses a whole result, so the writer must keep those
    # samples out (live, through openEMS: preflight_live_openems G).
    for f1, f2 in (("18 GHz", "30 GHz"), ("10 GHz", "20 GHz"),
                   ("26 GHz", "40 GHz")):
        doc = FreeCAD.newDocument("stlgate_wg")
        ana, solver = _wr28(doc, f1, f2)
        tag = "wg_" + f1.split()[0]
        d = os.path.join(work, tag)
        os.makedirs(d, exist_ok=True)
        try:
            deck, _z, _n = wr.write_deck(ana, solver, d)
            with open(deck, encoding="utf-8") as fh:
                text = fh.read()
            notes, why = wr.deck_model_notes(deck), ""
        except wr.OpenEMSModelError as exc:
            text, notes, why = "", [], str(exc)
        except Exception as exc:                           # noqa: BLE001
            # Anything else is a FAIL line below, never a traceback that
            # would hide every check after it.
            text, notes, why = "", [], "%s: %s" % (type(exc).__name__, exc)
        slices = [ln for ln in text.splitlines() if ln.startswith("f = f[")]
        nts = [t for lvl, t in notes if lvl == "note" and "cut-off" in t]
        if f1 == "18 GHz":
            check("11j. WR-28 swept 18-30 GHz (25 samples, TE10 cut-off "
                  "21.08 GHz): the deck keeps exactly the 18 samples above "
                  "cut-off ('f = f[7:]') and a NOTE names the cut-off, the 7 "
                  "samples dropped, 18 to 21 GHz, and the 21.5 GHz start",
                  not why and slices == ["f = f[7:]"] and len(nts) == 1
                  and "21.08 GHz" in nts[0] and "the 7 frequency sample(s) "
                  "from 18 GHz to 21 GHz" in nts[0]
                  and "from 21.5 GHz (18 samples)" in nts[0],
                  why[:80] or (nts or slices or notes)[:1])
        elif f1 == "10 GHz":
            stls = [f for f in os.listdir(d) if f.endswith(".stl")]
            check("11k. WR-28 swept 10-20 GHz, wholly below cut-off: REFUSED "
                  "at write time naming the 21.08 GHz cut-off and the band, "
                  "before a single STL is written", "21.08 GHz" in why
                  and "10 GHz to 20 GHz" in why and "cut off" in why
                  and stls == [], why[:90] or "it wrote a deck")
        else:
            check("11l. CONTROL: WR-28 swept 26-40 GHz (all above cut-off): "
                  "no slice, no note — the deck as before",
                  not why and slices == [] and nts == []
                  and "f = np.linspace(2.6e+10, 4e+10, 25)" in text,
                  why[:80] or (slices or nts)[:1])
        if f1 == "18 GHz":
            # Patterns are deck INDICES into f (and port.P_acc), so once f
            # starts 7 samples in they must shift with it: three asked for
            # across 18-30 GHz are samples 0, 12, 24 of the full sweep — and
            # 24 would be past the end of the 18 kept, an IndexError after
            # the whole FDTD run. The one asked for below cut-off lands on
            # the first kept sample, as one asked for outside the band does.
            solver.ComputeFarField = True
            solver.PatternFrequencies = 3
            doc.recompute()
            d2 = os.path.join(work, tag + "_ff")
            os.makedirs(d2, exist_ok=True)
            try:
                deck2, _z, _n = wr.write_deck(ana, solver, d2)
                with open(deck2, encoding="utf-8") as fh:
                    idx = [ln for ln in fh.read().splitlines()
                           if ln.startswith("ff_idx = ")]
            except Exception as exc:                       # noqa: BLE001
                idx = ["refused: %s" % str(exc)[:60]]
            check("11n. ...with 3 patterns asked across 18-30 GHz the deck's "
                  "pattern indices are into the KEPT samples: [0, 5, 17] "
                  "(21.5, 24 and 30 GHz), not the full sweep's [0, 12, 24]",
                  idx == ["ff_idx = [0, 5, 17]"], idx)
        FreeCAD.closeDocument(doc.Name)
    # The cut-off itself, against the textbook (c/2) * sqrt((m/a)^2 +
    # (n/b)^2), on the entry form _collect_ports hands it — a and b bound to
    # the AXES, so a broad wall on ny_PP arrives as TE01 with a, b swapped.
    a_m, b_m = 7.112e-3, 3.556e-3

    def fc(m_, n_):
        return 0.5 * _C0 * math.sqrt((m_ / a_m) ** 2 + (n_ / b_m) ** 2)
    rows = [({"wg_mode": "TE10", "wg_a_m": a_m, "wg_b_m": b_m}, fc(1, 0)),
            ({"wg_mode": "TE01", "wg_a_m": b_m, "wg_b_m": a_m}, fc(1, 0)),
            ({"wg_mode": "TE11", "wg_a_m": a_m, "wg_b_m": b_m}, fc(1, 1)),
            ({"wg_mode": "TE20", "wg_a_m": a_m, "wg_b_m": b_m}, fc(2, 0))]
    cut = getattr(wr, "_wg_cutoff_hz", None)   # absent: a FAIL line, never
    got = [cut(e) if cut else None for e, _w in rows]      # a traceback
    check("11m. the cut-off is the textbook TE_mn formula: WR-28 TE10 "
          "21.08 GHz drawn either way round, TE11 47.13, TE20 42.15 GHz",
          all(g is not None and abs(g / want - 1.0) < 1e-12
              for g, (_e, want) in zip(got, rows)),
          ["%.6g" % (g or 0) for g in got])


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    _rc = main()
    # _RC_SKIPPED fires only when FreeCAD is ABSENT, i.e. under plain python3,
    # where sys.exit IS reliable — freecadcmd's "sys.exit is unreliable"
    # caveat cannot apply, since freecadcmd always has FreeCAD. A real failure
    # has already left main() through `raise SystemExit(...)` above, which
    # freecadcmd does honour.
    sys.exit(_rc)
