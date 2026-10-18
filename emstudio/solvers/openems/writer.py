# SPDX-License-Identifier: LGPL-2.1-or-later
"""openEMS deck writer.

Translates an EM Analysis into a self-contained Python deck (``case_openems.py``) that
runs under the openEMS venv interpreter as a subprocess. The deck mirrors the structure
of the official openEMS Python tutorials (Simple_Patch_Antenna.py):

* geometry as literal CSXCAD boxes (axis-aligned solids/sheets) or STL polyhedra,
* grid built with openEMS's own utilities (AddEdges2Grid thirds-rule for metal edges,
  SmoothMeshLines grading) from parameters computed here,
* one excited lumped port; post-processing writes the shared SweepResult CSV schema.

Everything the deck needs is embedded as literals — the deck never imports FreeCAD.
"""

from __future__ import annotations

import math
import os

from emstudio.objects import query
from emstudio.objects.analysis import Analysis

from . import geometry, preflight

C0 = 299792458.0
EPS0 = 8.8541878128e-12
AXES = "xyz"


def excite_dir_negative(direction):
    """True if a '+X'/'-Z'-style direction string points along the negative axis."""
    return str(direction)[0] == "-"


#: Cells the FDTD grid must put across a body's smallest feature before the
#: geometry means anything. Below 1 the body is thinner than a cell and is
#: represented by nothing at all; below this it is a staircase caricature.
#: Since v1.14.0 this is the rule for DIELECTRIC bodies; metal is refined to
#: :data:`MIN_CELLS_ACROSS_METAL` (see there for why, and what it measured).
MIN_CELLS_ACROSS_FEATURE = 3.0

#: Ceiling on the cells a body may cost to BLANKET — to fill its whole
#: bounding box with lines at a third of its feature. The cost of that is
#: the PRODUCT of its per-axis line counts, not the largest of them:
#: blanketing a 6-turn helix's bounding box at its 20 mm conductor is
#: 105 x 73 x 121 = 927k cells for a single body. A per-axis cap misses that
#: entirely — 121 looks modest until it is multiplied.
#: ⚠ Since v1.14.0 this no longer decides WHETHER a body is refined, only
#: HOW, and only for DIELECTRICS: one under both ceilings is blanketed
#: exactly as before (so every dielectric grid refined before is
#: byte-identical), one over them is refined AXIS BY AXIS (:func:`_axis_zones`)
#: instead of being left unrefined — which is what happened to every body
#: of a forum J-pole, so none of its 1 mm hardware was resolved at any
#: MeshResolution. Metal is always refined by zones (MIN_CELLS_ACROSS_METAL).
#: The total grid is then budgeted as a WHOLE against the preflight's
#: limits (:func:`_budget_refinement`), not body by body.
MAX_REFINEMENT_CELLS = 200000

#: Per-axis bound on a blanket fill, kept alongside the cell budget so a
#: single long axis is refined by its profile rather than blanketed.
MAX_REFINEMENT_LINES = 400

#: Cells across its smallest feature (2V/A) that local refinement gives a
#: METAL body (PEC or a conducting sheet) — ONE, the presence threshold the
#: refusal itself applies (:func:`_refuse_unresolvable` refuses below one
#: cell). Dielectrics keep :data:`MIN_CELLS_ACROSS_FEATURE` (three): the
#: field INSIDE a dielectric is the model, inside metal it is zero.
#: ⚠⚠ v1.14.0 CHANGE — AN OWNER DECISION, MEASURED. Until then metal was
#: refined at three cells too, but only bodies small enough to blanket were
#: refined at all, so it rarely cost much. Once every part is refined (per
#: part, axis by axis, budgeted as a whole), three cells across 2V/A is what
#: sets the run: the smallest cell sets the FDTD timestep (Courant), and on
#: the forum J-pole at MeshResolution 20 (back plate as dielectric) —
#:     three cells, all metal:  21.8 M cells, 0.27 mm lines, dt 0.457 ps;
#:                              438 MC/s on 32 threads, ~14 h to converge;
#:     one cell only for the parts too big to blanket (three for the rest):
#:                              8.6 M cells, dt still ~0.45 ps (the nuts'
#:                              0.33 mm lines set it);
#:     ONE cell, all metal:      3,817,170 cells (0.56 GB), 0.54-1.4 mm
#:                              lines, dt 1.02 ps —
#: the 1 mm hand mesh of the 2026-10-17 investigation, whose answer agreed
#: with a 0.5 mm one. For PEC one cell is also the physics: a wall needs one
#: grid line inside it to be there; electrical accuracy is the global
#: MeshResolution's job (lambda/20 against a 1.2 mm wall is lambda/2000).
#: ⚠ What it costs: a small curved metal STL part (refined at three cells
#: since v0.84.0) is now refined at one — e.g. a solid 1 mm wire gets 2
#: cells across its diameter, not 6. No shipped template or gated solve has
#: such a part (their grids are byte-identical); a wire that thin belongs
#: in NEC2, as the refusal says. Set this to MIN_CELLS_ACROSS_FEATURE to
#: restore three cells for metal everywhere.
MIN_CELLS_ACROSS_METAL = 1.0

#: An axis on which a body needs at most this many lines at its refinement
#: step is filled WHOLE even when the body is refined axis by axis: that is
#: at most ~33 features across, cheap, and it is the safe choice wherever
#: the face analysis might under-read the section (a tube's 18 mm cross-
#: section at its 1.2 mm step is 16 lines; a bolt's every axis is far
#: under; a dielectric's three cells across make it ~33 features).
_THIN_AXIS_LINES = 100


def _stl_refinement(prim, mesh_res_mm):
    """Blanket grid for one STL body: (step_mm, (nx, ny, nz)) or None.

    None means "do not BLANKET": either the global cell already resolves the
    body, or filling its whole bounding box would cost more lines than
    :data:`MAX_REFINEMENT_LINES` on some axis or more than
    :data:`MAX_REFINEMENT_CELLS` in all. Since v1.14.0 the second kind is
    refined axis by axis instead (:func:`_refinement_plan`), and since then
    the plan blankets only DIELECTRICS with it — metal is always refined by
    zones (see :data:`MIN_CELLS_ACROSS_METAL`). Unchanged, so every body it
    accepts keeps the grid it always had.
    """
    feat = float(prim.get("min_feature") or 0.0)
    if feat <= 0.0:
        return None
    step = feat / MIN_CELLS_ACROSS_FEATURE
    if step >= mesh_res_mm:
        return None                     # the global grid already resolves it
    counts = []
    for i in range(3):
        extent = prim["stop"][i] - prim["start"][i]
        if extent <= 0.0:
            counts.append(2)
            continue
        n = int(math.ceil(extent / step)) + 1
        if n > MAX_REFINEMENT_LINES:
            return None                 # degenerate on this axis
        counts.append(max(2, n))
    if counts[0] * counts[1] * counts[2] > MAX_REFINEMENT_CELLS:
        return None                     # unaffordable as a whole
    return step, tuple(counts)


#: The deck's local-refinement helper, as SOURCE. It is pasted into the deck
#: (which runs under the openEMS venv, where EMStudio cannot be imported)
#: AND exec'd by the writer to count the grid it will produce, so the deck
#: and the writer's budget can never disagree about what a zone costs.
#: Pure Python on purpose — no numpy — because the writer side runs inside
#: FreeCAD (whose numpy is broken on 0.21.2 macOS) and needs none.
_REFINE_SRC = r"""
# A cell may exceed its target spacing by at most this factor rather than
# be split into two slivers (see the end of each gap's march below).
_RF_STRETCH = 1.05


def _refine_lines(lines, zones, res, ratio):
    # Lines to ADD so that the spacing at x is at most
    #   s(x) = min(res, min over zones (h + (ratio - 1) * distance(x, [a, b])))
    # for zones (a, b, h): h inside [a, b], growing by ~ratio per cell away
    # from it, capped at the global cell. Existing lines are never moved or
    # removed — each gap between two of them is marched on its own — so no
    # new line can land a hair from an existing one (a hair-thin cell sets
    # the FDTD timestep for the whole run, Courant). ratio is the analysis'
    # MeshSmoothRatio, the grading SmoothMeshLines applies everywhere else.
    g = max(float(ratio) - 1.0, 0.05)
    zs = [(float(a), float(b), float(h)) for a, b, h in zones
          if float(h) > 0.0 and float(b) >= float(a)]
    res = float(res)

    def step(x):
        d = res
        for a, b, h in zs:
            if x < a:
                # A zone AHEAD: the cell must also fit the spacing allowed at
                # its far end, so it stops growing before it reaches the zone.
                c = (h + g * (a - x)) / (1.0 + g)
                if c > a - x:
                    c = h               # the cell reaches into the zone
            elif x <= b:
                c = h
            else:
                c = h + g * (x - b)     # moving away: the spacing may grow
            if c < d:
                d = c
        return d

    pts = sorted(set(float(x) for x in lines))
    new = []
    for x0, x1 in zip(pts[:-1], pts[1:]):
        span = x1 - x0
        if span <= 0.0:
            continue
        xs = [x0]
        x = x0
        while True:
            d = step(x)
            if x + d >= x1 - 1e-9 * max(1.0, abs(x1)):
                break
            x += d
            xs.append(x)
        if len(xs) < 2:
            continue
        # The march ends in a PARTIAL cell (x1 - xs[-1] <= d). If it is a
        # sliver, drop the last line and stretch the gap's cells by at most
        # _RF_STRETCH; otherwise shrink every cell by one factor (<= 1) so the
        # last becomes whole. Either way the march ends exactly on x1 and no
        # cell collapses: shrinking alone split a gap a hair wider than the
        # step (1.5 mm at a 1.497 mm step) into two 0.75 mm cells — a
        # needless small cell, and the smallest cell sets the timestep.
        stretch = span / (xs[-1] - x0)
        if len(xs) >= 2 and stretch <= _RF_STRETCH:
            new.extend(x0 + (xi - x0) * stretch for xi in xs[1:-1])
        else:
            scale = span / ((xs[-1] - x0) + d)
            new.extend(x0 + (xi - x0) * scale for xi in xs[1:])
    return new
"""

_refine_ns = {}
exec(_REFINE_SRC, _refine_ns)                                # noqa: S102
_refine_lines = _refine_ns["_refine_lines"]


def _axis_zones(src, step):
    """{axis: [(lo, hi, step), ...]} — where ONE body needs lines at ``step``.

    A body is refined axis by axis when blanketing its bounding box is too
    expensive (:func:`_stl_refinement` said None). On each axis:
      * a SHORT axis (at most :data:`_THIN_AXIS_LINES` lines at the step) is
        filled whole — a tube's cross-section, every axis of a screw;
      * a LONG axis is resolved only where the body's section CHANGES along
        it, read exactly from its faces (geometry.axis_profile): over every
        face that is not ruled along the axis (a cone, a torus, a cylinder
        lying across it), and in a band of one step either side of each
        plane where the section steps (an end cap, a shoulder). Between
        them the body is an extrusion and the global grid is enough —
        SmoothMeshLines' own grading, here done by the deck's _refine_lines,
        carries the spacing from the step back up to the global cell;
      * no readable topology (an imported mesh, an unreadable solid): filled
        whole, as a blanket would — never less than that.
    """
    zones = {0: [], 1: [], 2: []}
    solid = src.get("solid")
    for i in range(3):
        lo, hi = float(src["start"][i]), float(src["stop"][i])
        ext = hi - lo
        if ext <= 0.0:
            continue                    # a sheet's normal: its plane is a line
        if ext / step + 1.0 <= _THIN_AXIS_LINES:
            zones[i].append((lo, hi, step))
            continue
        prof = geometry.axis_profile(solid, i) if solid is not None else None
        if prof is None:
            zones[i].append((lo, hi, step))
            continue
        fills, planes = prof
        for a, b in fills:
            zones[i].append((max(lo, a), min(hi, b), step))
        for c in planes:
            zones[i].append((c - step, c + step, step))
    return zones


def _refinement_plan(mats, mesh_res_mm):
    """One entry per STL source part that the global grid does not resolve.

    ``{"src", "prim", "mat", "step", "blanket": (nx, ny, nz) | None,
    "zones": {axis: [...]} | None}`` — a blanket entry fills the part's
    bounding box exactly as before v1.14.0; a zone entry is refined axis by
    axis (:func:`_axis_zones`). Judged per SOURCE part (one solid of what the
    user referenced), never per exported STL: a fused STL's 2V/A is a
    surface-weighted average of its parts', and a 1 mm screw fused to a
    1.5 m tube would otherwise be refined at the tube's 2V/A.
    """
    plan = []
    for m in mats:
        for p in m["prims"]:
            if p["kind"] != "stl":
                continue
            for src in p.get("sources") or [
                    {"label": p.get("label"), "min_feature": p.get("min_feature"),
                     "start": p["start"], "stop": p["stop"]}]:
                f = float(src.get("min_feature") or 0.0)
                if f <= 0.0:
                    continue
                metal = m["kind"] in ("metal", "conducting_sheet")
                if not metal:
                    # A DIELECTRIC small enough to blanket is blanketed
                    # exactly as before v1.14.0 (three cells, its own
                    # linspace) — the imported-STL substrate of
                    # patch_stl_openems keeps its grid byte for byte.
                    blanket = _stl_refinement(
                        {"start": src["start"], "stop": src["stop"],
                         "min_feature": f}, mesh_res_mm)
                    if blanket:
                        plan.append({"src": src, "prim": p, "mat": m,
                                     "step": blanket[0],
                                     "blanket": blanket[1], "zones": None})
                        continue
                # Metal is always refined by zones: at one cell across (see
                # MIN_CELLS_ACROSS_METAL) its grid differs from v1.13's
                # anyway, so the blanket's only reason — byte-stability —
                # is gone, and zones put lines only where the part needs
                # them (a plate's thickness, not its whole face), graded.
                step = f / (MIN_CELLS_ACROSS_METAL if metal
                            else MIN_CELLS_ACROSS_FEATURE)
                if step >= mesh_res_mm:
                    continue            # the global grid already holds it
                plan.append({"src": src, "prim": p, "mat": m, "step": step,
                             "blanket": None,
                             "zones": _axis_zones(src, step)})
    _untangle_blankets(plan)
    return plan


def _axis_spans(e, i):
    """The intervals entry ``e`` lays fine lines over on axis ``i``."""
    if e["blanket"] is not None:
        if e["blanket"][i] <= 2:
            return []
        return [(float(e["src"]["start"][i]), float(e["src"]["stop"][i]))]
    return [(a, b) for a, b, _h in e["zones"][i]]


def _untangle_blankets(plan):
    """Hand a blanket axis to the zone generator where it would interleave.

    ⚠⚠ TWO LINSPACES OVER OVERLAPPING SPANS MAKE HAIR-THIN CELLS. Each part's
    blanket is np.linspace over its own bounding box at its own step, and
    lines are global per axis: a screw (6.35 mm across at 0.45 mm) and the
    nut on it (the same 6.35 mm at 0.33 mm) put two unrelated sets of lines
    over one span. MEASURED on the forum J-pole while its screws and nuts
    were still blanketed one by one (during v1.14.0's development; metal is
    now refined by zones, so today this guards dielectric blankets): cells
    of 0.00034 mm on x, 0.0033 mm on y and 0.017 mm on z — the FDTD
    timestep follows the smallest cell (Courant), so that one sliver would
    have multiplied the run's timesteps by ~1000.
    So a blanket axis that overlaps ANY other refined span on that axis is
    turned into a zone at the same step, and the deck's _refine_lines lays
    ONE coherent set of lines for every zone together, subdividing only
    the gaps between lines that exist. A blanket that overlaps nothing —
    every body refined before v1.14.0 that is alone on its axis — keeps
    its linspace, so its grid is byte-identical.
    """
    spans = [[_axis_spans(e, i) for i in range(3)] for e in plan]
    for k, e in enumerate(plan):
        if e["blanket"] is None:
            continue
        counts = list(e["blanket"])
        moved = {0: [], 1: [], 2: []}
        for i in range(3):
            if counts[i] <= 2:
                continue
            lo, hi = float(e["src"]["start"][i]), float(e["src"]["stop"][i])
            if any(a < hi and lo < b
                   for j, other in enumerate(spans) if j != k
                   for a, b in other[i]):
                moved[i].append((lo, hi, e["step"]))
                counts[i] = 2
        if any(moved.values()):
            e["blanket"] = tuple(counts)
            e["zones"] = moved


def _linspace(a, b, n):
    """numpy.linspace(a, b, n) without numpy, for the writer-side count."""
    if n < 2:
        return [float(a)]
    return [a + (b - a) * k / (n - 1.0) for k in range(n)]


#: Slack taken off the writer's own count of the refined grid before it is
#: compared with a limit, so the comparison is a FLOOR: the deck's lines are
#: a superset of what the writer counts (every other line the deck adds can
#: only add cells), and this keeps float rounding at the march's ends from
#: ever lifting the count above the real grid (the preflight floor's own
#: margin, preflight._LINE_SLACK).
_FLOOR_SLACK = 0.01


def _refined_floor(mats, plan, dom_lo, dom_hi, mesh_res_mm, ratio):
    """Lower bound on the grid lines (nx, ny, nz) with ``plan`` refined."""
    anchors = {0: set(), 1: set(), 2: set()}
    zones = {0: [], 1: [], 2: []}
    for m in mats:
        for p in m["prims"]:
            if p["kind"] != "stl":
                continue
            for src in p.get("sources") or [p]:
                for i in range(3):
                    anchors[i].add(float(src["start"][i]))
                    anchors[i].add(float(src["stop"][i]))
    for e in plan:
        for i in range(3):
            if e["blanket"] is not None and e["blanket"][i] > 2:
                anchors[i].update(_linspace(
                    float(e["src"]["start"][i]),
                    float(e["src"]["stop"][i]), e["blanket"][i]))
            if e["zones"] is not None:
                zones[i].extend(e["zones"][i])
    out = []
    for i in range(3):
        lo, hi = float(dom_lo[i]), float(dom_hi[i])
        pts = sorted({lo, hi} | {a for a in anchors[i] if lo <= a <= hi})
        allp = sorted(set(pts) | set(_refine_lines(pts, zones[i],
                                                    mesh_res_mm, ratio)))
        n = len(allp)
        for x0, x1 in zip(allp[:-1], allp[1:]):
            if x1 - x0 > mesh_res_mm * (1.0 + 1e-10):
                # SmoothMeshLines fills every gap wider than the cell
                n += int(math.ceil((x1 - x0) / mesh_res_mm - 1e-9)) - 1
        out.append(max(2, int(n * (1.0 - _FLOOR_SLACK))))
    return tuple(out)


#: How many entries one greedy step may drop when a large assembly's
#: refinement is over openEMS's index limit, so the budget loop costs at most
#: ~16 grid counts however many parts there are.
_DROP_BATCHES = 16


def _budget_refinement(mats, plan, dom_lo, dom_hi, mesh_res_mm, ratio):
    """(kept, dropped, floor_all, floor_kept) — the refinement that fits.

    ⚠⚠ THE WHOLE GRID IS WHAT COSTS, NOT ANY ONE BODY. Lines are global on a
    Cartesian grid: a 0.4 mm line laid for a tube's wall runs through the
    whole domain, so the price of refining a body depends on every other
    body's lines. Before v1.14.0 each body was capped on its own (400 lines
    an axis, 200k cells) and a capped body was simply NOT refined — silently
    absent if thinner than the global cell. Now the whole refined grid is
    counted (:func:`_refined_floor`) and only if it is more than openEMS
    can INDEX (preflight.OPENEMS_MAX_CELLS) is refinement taken away — from
    the finest parts first, then given back to any that fit again — and the
    parts left unrefined go to :func:`_refuse_unresolvable`, which refuses
    the ones the global grid cannot represent and names them.
    ⚠ Only the index limit, never this machine's RAM: dropping refinement on
    an 8 GB Mac that a 192 GB box keeps would make the SAME document a
    different model on each machine. A grid over the RAM limit is refused
    by the caller instead, with the parts that drive it named — except a
    DIELECTRIC part refined axis by axis, which v1.13 never refined and ran,
    so the caller gives that machine v1.13's model back, with a NOTE.
    """
    def cells(fl):
        return fl[0] * fl[1] * fl[2]

    floor_all = _refined_floor(mats, plan, dom_lo, dom_hi, mesh_res_mm, ratio)
    if cells(floor_all) < preflight.OPENEMS_MAX_CELLS:
        return list(plan), [], floor_all, floor_all
    kept = list(plan)
    dropped = []
    order = sorted(plan, key=lambda e: (e["step"], -max(
        float(e["src"]["stop"][i]) - float(e["src"]["start"][i])
        for i in range(3))))
    batch = max(1, len(order) // _DROP_BATCHES)
    floor = floor_all
    # (Membership by IDENTITY throughout: an entry holds OpenCASCADE shapes,
    # and list.remove's == would compare them by value.)
    while order and cells(floor) >= preflight.OPENEMS_MAX_CELLS:
        gone = order[:batch]
        kept = [k for k in kept if not any(k is g for g in gone)]
        dropped.extend(gone)
        order = order[batch:]
        floor = _refined_floor(mats, kept, dom_lo, dom_hi, mesh_res_mm, ratio)
    if len(dropped) <= _DROP_BATCHES:
        # Give refinement back to whatever still fits, coarsest first: the
        # batch that tipped the grid under the limit may hold parts it never
        # needed to give up.
        for e in sorted(dropped, key=lambda e: -e["step"]):
            fl = _refined_floor(mats, kept + [e], dom_lo, dom_hi,
                                mesh_res_mm, ratio)
            if cells(fl) < preflight.OPENEMS_MAX_CELLS:
                kept.append(e)
                dropped = [k for k in dropped if k is not e]
                floor = fl
    return kept, dropped, floor_all, floor


def _plan_label(e):
    return e["src"].get("label") or e["prim"].get("label") or e["mat"]["name"]


def _finest_text(plan, n=3):
    """'A' (0.276 mm lines), 'B' (0.33 mm) — the parts whose refinement
    sets a grid, finest first."""
    seen = []
    for e in sorted(plan, key=lambda e: e["step"]):
        lab = _plan_label(e)
        if lab in [s for s, _h in seen]:
            continue
        seen.append((lab, e["step"]))
        if len(seen) == n:
            break
    return ", ".join("'{0}' ({1:.3g} mm{2})".format(
        lab, h, " lines" if k == 0 else "") for k, (lab, h) in
        enumerate(seen))


class OpenEMSModelError(ValueError):
    """The analysis cannot be expressed as an openEMS model."""


#: How flat |S11| has to be across the sweep before "the best match" stops
#: meaning anything. Below this span the deck takes the pattern at the sweep
#: CENTRE instead of at argmin|S11| and says so.
#:
#: ⚠ This number decides which existing documents move, so it is chosen to move
#: none of them that had a defensible answer. Any antenna with a usable
#: resonance has far more than 3 dB of |S11| range — the shipped patch, dipole
#: and notch gates are tens of dB — while the Ka-band horn, which is matched
#: right across 26.5-40 GHz, has essentially none and picked 28.45 GHz at one
#: mesh and 39.55 GHz at another. The branch fires on exactly the second kind.
#:
#: ⛳ The VALUE lives in emstudio.post.sparams since 2026-08-24 — ONE constant,
#: ONE rule — because NEC2 now applies the same guard through
#: SweepResult.pattern_frequency() and two hand-kept copies of a threshold is
#: exactly the drift this project keeps cataloguing. The local name is kept so
#: every existing reference (and the generated-deck format strings below)
#: stays put.
from emstudio.post.sparams import FLAT_S11_SPAN_DB  # noqa: E402


def _pattern_indices(solver, f1_hz, f2_hz, npts):
    """Indices into the deck's own frequency grid that get a radiation pattern.

    Empty means "one pattern, frequency chosen at run time" — the default rule
    needs S11, which does not exist until the run is over.

    Returns INDICES rather than frequencies on purpose: ``port.P_acc`` is
    indexed on that same ``np.linspace(f1, f2, npts)`` grid, and the efficiency
    is only right if the pattern and the accepted power are read at the same
    sample. Snapping also means every pattern lands on a frequency the S11 /
    VSWR / impedance curves were actually computed at, so the results dialog's
    cursor and its pattern picker agree — the reason NEC2 snaps too.
    """
    from emstudio.solvers.nec2 import pattern_band

    n = int(getattr(solver, "PatternFrequencies", 0) or 0)
    if n < 2:
        return []
    b1, b2 = pattern_band.resolve_band(solver, f1_hz, f2_hz)
    f1, f2 = float(f1_hz), float(f2_hz)
    span = f2 - f1
    if span <= 0.0 or int(npts) < 2:
        return []
    step = span / (int(npts) - 1)
    idx = []
    for k in range(n):
        target = b1 + (b2 - b1) * k / float(n - 1)
        i = int(round((target - f1) / step))
        i = max(0, min(int(npts) - 1, i))
        if i not in idx:
            idx.append(i)
    return sorted(idx)


def _nf2ff_bc(boundaries):
    """(bc_size, directions, mirror) for a hand-built NF2FF box.

    A verbatim replication of ``openEMS.CreateNF2FFBox``'s own rule
    (openEMS.pyx), because that method decides ``directions`` itself and so
    cannot be told to drop a face. Getting this wrong moves the recording
    surface, which moves every far-field number, so it is written to match the
    engine line for line rather than to look tidy:

      PEC  -> face OFF, mirrored as PEC (1), no inset
      PMC  -> face OFF, mirrored as PMC (2), no inset
      MUR  -> 2 lines in
      PML_N-> N + 1 lines in    <- the "+1" is the engine's, not a safety margin

    ⚠ An unparseable ``PML_`` is REFUSED here rather than defaulted to 8.
    openEMS does not default either — ``int('PML_'.strip('PML_'))`` raises
    ValueError inside SetBoundaryCond — and a guard that quietly assumed 8
    would disagree with the engine it is meant to mirror.
    """
    bc_size = [0] * 6
    directions = [1] * 6
    mirror = [0] * 6
    for n, bc in enumerate(boundaries):
        bc = str(bc)
        if bc == "PEC":
            directions[n], mirror[n] = 0, 1
        elif bc == "PMC":
            directions[n], mirror[n] = 0, 2
        elif bc == "MUR":
            bc_size[n] = 2
        elif bc.startswith("PML_"):
            try:
                bc_size[n] = int(bc[4:]) + 1
            except ValueError:
                raise OpenEMSModelError(
                    "boundary {0} is '{1}': a PML needs a cell count, e.g. "
                    "'PML_8'. openEMS rejects this too.".format(n, bc))
        else:
            raise OpenEMSModelError(
                "boundary {0} is '{1}', which openEMS does not accept "
                "(PEC, PMC, MUR or PML_<n>)".format(n, bc))
    return bc_size, directions, mirror


#: How many further unresolvable bodies the refusal names after the worst
#: one. A model with sixteen thin parts must not be fixed one refusal at a
#: time (the forum J-pole had tubes, clamps, a junction and twelve screws and
#: nuts, every one under a cell), but a wall of names helps nobody either.
_REFUSAL_LIST_MAX = 8

#: A hollow body may be filled for the model only if its bore is far below
#: waveguide cut-off across the whole band: then the fields inside decay
#: within a fraction of a bore length and nothing outside can tell a tube
#: from a rod. The cut-off is bounded from BELOW by a rectangular guide of the
#: bore's largest inner dimension a (TE10, c / 2a — a circular bore of
#: diameter a cuts off higher, at c / 1.706a), and the band must stay under
#: HALF of it, where the evanescent decay is ~47 dB per cut-off wavelength
#: of tube. ⚠ A horn feed or a waveguide fails this and must never be told
#: to fill itself: its inside IS the model.
#: ⚠⚠ A COAX SHIELD DOES NOT FAIL IT — this is the cut-off of an EMPTY
#: bore, and a coax carries TEM, which has none. That case is caught before
#: this test ever runs, by what is IN the bore (geometry.bore_occupant: an
#: inner conductor, a port, a dielectric), never by the band. Until the
#: v1.14.0 review this comment claimed the cut-off excluded coax shields;
#: it did not, and a coax shield was told to fill itself.
_FILL_CUTOFF_MARGIN = 0.5


def _gb_text(nbytes):
    """GB (1e9 B) the way the preflight prints it, so the two never disagree."""
    v = float(nbytes) / 1e9
    if v >= 100.0:
        return "%.0f" % v
    if v >= 10.0:
        return "%.1f" % v
    return "%.2f" % v


def _grid_for_feature(feat_mm, cost):
    """What resolving a ``feat_mm`` feature with the GLOBAL cell would cost.

    ``cost`` (built by write_deck) holds ``wavelength_mm`` and ``mr_floor``
    (the writer's own cell rule: cell = wavelength_mm / max(mr_floor,
    MeshResolution)), the domain ``extent_mm`` before any absorber growth,
    ``ram_bytes`` and ``allow``. The grid is the preflight's own FLOOR
    (preflight.lower_bound_lines), so "at least" is literally true and the
    affordability verdict is the one the deck itself would reach.

    One cell across the feature is the bar quoted: it is the line this
    refusal draws (below it the body is absent), not an accurate model — a
    staircase still — and the message says so.
    """
    lam = float(cost["wavelength_mm"])
    mr = max(int(cost.get("mr_floor", 6)),
             int(math.ceil(lam / float(feat_mm) - 1e-9)))
    cell = lam / mr
    lines = preflight.lower_bound_lines(cost["extent_mm"], cell)
    cells = preflight.cell_count(lines)
    ram = cost.get("ram_bytes")
    over = None
    if preflight.refusal(lines, cell, ram, allow=bool(cost.get("allow")),
                         at_least=True):
        over = "index" if cells >= preflight.OPENEMS_MAX_CELLS else "ram"
    return {"mr": mr, "cell": cell, "lines": lines, "cells": cells,
            "bytes": preflight.bytes_needed(cells), "over": over, "ram": ram}


def _cost_text(g):
    return "at least {0} x {1} x {2} = {3:,} cells, about {4} GB".format(
        g["lines"][0], g["lines"][1], g["lines"][2], g["cells"],
        _gb_text(g["bytes"]))


def _over_text(g):
    if g["over"] == "index":
        return "more than openEMS can index ({0:,} cells)".format(
            preflight.OPENEMS_MAX_CELLS)
    return "more than {0:.0f} % of the {1} GB this machine has".format(
        100.0 * preflight.OPENEMS_RAM_FRACTION, _gb_text(g["ram"]))


def _bore_candidates(mats, ports=()):
    """Everything that could sit INSIDE a refused tube's bore.

    One entry per source solid (a fused STL's parts one by one — the tube
    itself is among them and :func:`geometry.bore_occupant` skips it by
    identity), per box / sheet / shell / mesh primitive, and per port span
    (``ports``: ``(name, start, stop)``), in the form bore_occupant takes.
    Metal and dielectric alike: a PTFE sleeve in a shield is as much "the
    inside is the model" as the inner conductor it surrounds.
    """
    out = []
    for m in mats:
        for p in m["prims"]:
            solids = [s for s in (p.get("sources") or ())
                      if s.get("solid") is not None]
            if solids:
                out.extend({"name": "'{0}'".format(
                    s.get("label") or p.get("label") or m["name"]),
                    "geo": s["solid"]} for s in solids)
            elif p.get("shape") is not None or p.get("mesh") is not None:
                out.append({"name": "'{0}'".format(
                    p.get("label") or m.get("label") or m["name"]),
                    "geo": p.get("shape") if p.get("shape") is not None
                    else p["mesh"]})
    for name, start, stop in ports:
        out.append({"name": name, "segment": (start, stop)})
    return out


def _hollow_of(body):
    """The hollow-envelope description of a refused body, or None.

    Run only HERE, on bodies already being refused — it casts rays at the
    solid, which costs milliseconds per body and is pointless for the rest.
    A bore with anything else in it (``body["others"]``, see
    :func:`_bore_candidates`) carries ``"occupant"``: the name of what is in
    there, so :func:`_fill_advice` can say why it must not be filled.
    """
    solid = body["src"].get("solid")
    if solid is None:
        return None
    if "hollow" not in body["src"]:
        h = geometry.hollow_envelope(solid, body["feat"])
        if h and "box" in h:
            occ = geometry.bore_occupant(solid, h, body.get("others") or ())
            if occ:
                h = dict(h, occupant=occ)
        body["src"]["hollow"] = h
    return body["src"]["hollow"]


def _fill_advice(hollow, cost):
    """(sentence, fill_ok) about a hollow body, or (None, False).

    ``fill_ok`` False means the sentence WARNS against filling it: the bore
    carries fields in this band, or holds another part (``"occupant"``), so
    its inside is part of the model.
    """
    occ = hollow.get("occupant")
    if occ:
        # ⚠⚠ A COAX IS NOT AN EMPTY WAVEGUIDE. The cut-off test below is for
        # a bore with NOTHING in it; a shield with a conductor (or a port, or
        # a dielectric) inside carries a TEM wave, which has no cut-off at
        # any frequency, so no band makes filling it safe — and "fill the
        # bore" would delete the feed line. MEASURED (v1.14.0 review): a
        # 400 mm, 6 mm coax shield around a 1 mm inner conductor, PTFE and a
        # lumped port, at 400-600 MHz, was told to fill. Said before the
        # band test on purpose: it holds with no band known too.
        return ("It is thin-walled and hollow, but {occ} lies inside it, so "
                "it is a coax or feed structure, not an empty tube: the "
                "field between its conductors is a TEM wave, which has no "
                "cut-off, so its inside IS part of the model and it must NOT "
                "be filled. To resolve its wall, thicken it OUTWARD to at "
                "least one cell (keeping the inside diameter keeps the line's "
                "impedance), or feed the model with a lumped port where the "
                "line ends and leave the line out.".format(occ=occ)), False
    t = float(hollow["wall_mm"])
    a, b = hollow["outline_mm"]
    across = min(a, b)
    # The largest INNER dimension sets the lowest cut-off. A tube's is its
    # bore across; a closed shell's can be its LENGTH (a long box enclosure),
    # so all three sides count there — never the smaller cross-section, which
    # would put the cut-off too high and let a resonant cavity be "filled".
    outer = max(a, b, float(hollow["length_mm"])) if hollow.get("closed") \
        else max(a, b)
    bore = outer - 2.0 * t
    if bore <= 0.0:
        return None, False
    f_cut = C0 / (2.0 * bore * 1e-3)
    f_max = (cost or {}).get("f_max_hz")
    if f_max is None:
        # No band, no cut-off test — and "fill it" without that test is the
        # one piece of advice here that could wreck a model (a waveguide).
        return None, False
    if f_max > _FILL_CUTOFF_MARGIN * f_cut:
        return ("It looks thin-walled and hollow, but its {0:.3g} mm bore is "
                "large enough to carry fields in this band (cut-off near "
                "{1:.3g} GHz), so it must NOT be filled — its inside is part "
                "of the model.".format(bore, f_cut / 1e9)), False
    filled = _filled_feature(hollow)
    if hollow.get("closed"):
        # A closed shell (an enclosure drawn with 1 mm walls): "rod" would be
        # the wrong picture, the physics is the same — the inside of a closed
        # conductor is screened from everything outside it.
        text = ("It looks like a thin-walled closed shell: walls about {t:.2g} "
                "mm thick around an outline {d:.3g} mm across. A closed PEC "
                "shell and a solid body of the same outline are identical from "
                "outside — the RF current flows on the outer skin, and the "
                "{bore:.3g} mm inside is far below its waveguide cut-off "
                "(about {fc:.3g} GHz) — so model it as a solid body (fill "
                "it){tail}.")
    else:
        text = ("It looks thin-walled and hollow: walls about {t:.2g} mm thick "
                "around an outline {d:.3g} mm across. A PEC tube and a solid "
                "rod of the same OD are identical from outside — the RF "
                "current flows on the outer skin, and the {bore:.3g} mm bore "
                "is far below its waveguide cut-off (about {fc:.3g} GHz) — so "
                "model it as a solid rod (fill the bore){tail}.")
    tail = ""
    if cost and cost.get("wavelength_mm") and filled > 0.0:
        g = _grid_for_feature(filled, cost)
        # "for this part": the price of ONE body. Other parts may still need
        # more — the whole-model sentence (_whole_model_text) says so, so a
        # user is never sent to fill one part only to be refused on the next.
        tail = ": then MeshResolution {0} is enough for this part ({1}{2})".format(
            g["mr"], _cost_text(g),
            "" if g["over"] is None else " — still " + _over_text(g))
    return text.format(t=t, d=across, bore=bore, fc=f_cut / 1e9,
                       tail=tail), True


def _filled_feature(hollow):
    """2V/A of a hollow body's FILLED envelope (a box/cylinder of its outline).

    For a rod of diameter D and length L it is D*L/(2L + D), close to the
    radius — the same conservative half-thickness 2V/A gives any solid.
    """
    a, b = hollow["outline_mm"]
    span = float(hollow["length_mm"])
    den = (a + b) * span + a * b
    return (a * b * span) / den if den > 0.0 else 0.0


def _fillable(body, cost):
    """True when a refused body is hollow AND may be filled in this band."""
    h = _hollow_of(body)
    return bool(h) and _fill_advice(h, cost)[1]


#: Refused bodies the whole-model verdict ray-tests for hollowness. Each test
#: is a few distToShape calls; past this a body counts as NOT fillable, which
#: can only make the verdict ask for MORE resolution, never promise too much.
_WHOLE_MODEL_HOLLOW_MAX = 64


def _whole_model_text(bodies, cost):
    """One sentence: what the model as a WHOLE needs, or None.

    WHY. The worst body's own fix is not the model's fix. Measured on the
    forum J-pole BEFORE local refinement (v1.14.0's O4): the worst body was a
    hollow junction that filled to an affordable grid (MeshResolution 297,
    1.6 GB), yet the solid 92 mm 'Feed > Mount' beside it still needed a
    cell under 1.4 mm across a 3 m domain (2.8e9 cells, over the index
    limit). Superseded for that model: with each part refined locally it
    now meshes at MeshResolution 20 in 2,939,116 cells. The reasoning still
    holds wherever several parts are refused (thin parts local refinement
    cannot hold): telling the user only about the worst body
    sends him round the refuse-fix-refuse loop one part at a time. This takes
    every refused body at the feature it would have AFTER the advice above
    (filled if it may be filled, as drawn otherwise), finds the thinnest, and
    prices one global cell across it with the same preflight floor.

    Said only when more than one OBJECT is refused — with one, the sentences
    above already are the whole-model answer.
    """
    if cost is None or not cost.get("wavelength_mm"):
        return None
    if len({b["object"] for b in bodies}) < 2:
        return None
    limit, limit_feat, any_filled = None, None, False
    for i, b in enumerate(bodies):
        feat = b["feat"]
        if i < _WHOLE_MODEL_HOLLOW_MAX and _fillable(b, cost):
            feat = _filled_feature(_hollow_of(b))
            any_filled = True
        if limit_feat is None or feat < limit_feat:
            limit, limit_feat = b, feat
    g = _grid_for_feature(limit_feat, cost)
    head = ("For the model as a whole{0}, the thinnest part left is '{1}' "
            "({2:.3g} mm), which needs MeshResolution {3}: {4}").format(
                " (with every hollow part filled)" if any_filled else "",
                limit["object"], limit_feat, g["mr"], _cost_text(g))
    if g["over"] is None:
        return head + "."
    # ⚠ Name no culprit beyond the measured one. On the forum J-pole the
    # M3 screws and nuts were NOT the problem (small, so local refinement
    # takes them); the limit was a 92 mm sheet-metal mount — a guess like
    # "small hardware" would have pointed at the wrong parts.
    return (head + " — " + _over_text(g) + ". Thicken or simplify the "
            "parts this thin, leave them out, or use NEC2.")


def _unresolvable_text(bodies, cost):
    """The refusal for the worst body, then the others by name."""
    worst = bodies[0]
    who = "'{0}'".format(worst["label"])
    if worst["material"] and worst["material"] != worst["label"]:
        who += " (material '{0}')".format(worst["material"])
    parts = [
        "{who} has a smallest feature of {feat:.4g} mm, but the FDTD cell is "
        "{cell:.4g} mm — {cells:.3g} cells across it, so this body would be "
        "absent from the grid and the run would still report "
        "plausible-looking results.".format(
            who=who, feat=worst["feat"], cell=worst["cell"],
            cells=worst["cells"])]
    if cost is not None:
        g = _grid_for_feature(worst["feat"], cost)
        if g["over"] is None:
            # Only claim it fits when that was MEASURED against this
            # machine: unreadable RAM, or the ALLOW_LARGE override, lets a
            # grid through the preflight without the RAM test saying yes.
            if not g["ram"]:
                fits = " (this machine's RAM could not be read)"
            elif g["bytes"] <= preflight.OPENEMS_RAM_FRACTION * g["ram"]:
                fits = ", within this machine's {0} GB".format(
                    _gb_text(g["ram"]))
            else:
                fits = (", more than this machine's {0} GB can comfortably "
                        "hold — allowed only by {1}".format(
                            _gb_text(g["ram"]),
                            preflight.OPENEMS_ALLOW_LARGE_ENV))
            parts.append(
                "Raise MeshResolution to {mr} or more (cell {cell:.4g} mm, one "
                "cell across it — the bare minimum, still a staircase): the "
                "grid is then {cost}{fits}.".format(
                    mr=g["mr"], cell=g["cell"], cost=_cost_text(g),
                    fits=fits))
        else:
            # ⚠⚠ NEVER "raise MeshResolution" when that cannot work. Until
            # v1.14.0 this said "raise MeshResolution until the cell is under
            # 0.9475 mm" with no cost attached; a forum user did exactly
            # that, chose 2700, and built 9,429,380,072 cells.
            parts.append(
                "Resolving it would take MeshResolution {mr} (cell {cell:.4g} "
                "mm, one cell across it): {cost} — {over}, so {verdict}."
                .format(mr=g["mr"], cell=g["cell"], cost=_cost_text(g),
                        over=_over_text(g),
                        verdict="no MeshResolution can fix this body as drawn"
                        if g["over"] == "index" else
                        "raising MeshResolution cannot fix it on this "
                        "machine ({0}=1 lifts the RAM check only, at the "
                        "risk of hours of swapping)".format(
                            preflight.OPENEMS_ALLOW_LARGE_ENV)))
    else:
        parts.append(
            "A cell under {0:.4g} mm would resolve it, but MeshResolution sets "
            "the cell across the WHOLE domain, so count the cells before "
            "raising it.".format(worst["feat"]))
    hollow = _hollow_of(worst)
    advice, fill_ok = _fill_advice(hollow, cost) if hollow else (None, False)
    if advice:
        parts.append(advice)
    if fill_ok:
        parts.append("Or use NEC2 for wire-like antennas — the accurate "
                     "method for a conductor this thin against the "
                     "wavelength.")
    else:
        parts.append("Or simplify or leave out this part, or model this "
                     "conductor with the NEC2 wire backend, which is the "
                     "accurate method for a conductor this thin against the "
                     "wavelength.")
    # The rest, ONE entry per referenced object (its thinnest solid — the
    # list is sorted), skipping the object already named above: "Mast >
    # junction (solid 1 of 2)" after "Mast > junction (solid 2 of 2)" tells
    # the user nothing new. "hollow, may be filled" only where the bore test
    # above would say so too — a hollow part whose bore carries fields gets
    # no tag, because "hollow" beside it would read as "fill it".
    others, seen = [], {worst["object"]}
    for b in bodies[1:]:
        if b["object"] in seen:
            continue
        seen.add(b["object"])
        fill = _fillable(b, cost) if len(others) < _REFUSAL_LIST_MAX else False
        others.append("'{0}' ({1:.3g} mm{2})".format(
            b["object"], b["feat"], ", hollow, may be filled" if fill else ""))
    if others:
        shown = others[:_REFUSAL_LIST_MAX]
        parts.append("Also too thin for this grid: {0}{1}.".format(
            ", ".join(shown),
            " and {0} more".format(len(others) - len(shown))
            if len(others) > len(shown) else ""))
    whole = _whole_model_text(bodies, cost)
    if whole:
        parts.append(whole)
    return " ".join(parts)


def _refuse_unresolvable(mats, mesh_res_mm, cost=None, refined=None):
    """Refuse a body the grid cannot represent at all, with the numbers.

    FDTD is a volume method on a Cartesian grid: a conductor thinner than one
    cell is not "approximate", it is ABSENT, and the run still produces
    S-parameters and a radiation pattern that look perfectly plausible. Local
    refinement (:func:`_stl_refinement`) rescues the affordable cases; this
    catches the ones no refinement can, and says why in the user's own units.

    The classic example is exactly the geometry that motivated it: a 6-turn
    helix, 20 mm conductor, resonating near 25 MHz. lambda is 12 m there, so
    the default grid cell is ~250 mm — the conductor is 0.04 of a cell. No
    mesh setting fixes that; a lambda/600 conductor in a lambda-sized domain is
    what thin-wire codes exist for, and the message says so.

    Since v1.14.0 (a forum J-pole that this message steered to MeshResolution
    2700): bodies are judged PER SOURCE SOLID and named by the object the
    user referenced ('Mast > junction', not 'mat1_EMMaterial001'); with
    ``cost`` (write_deck always passes it) the message quotes the
    MeshResolution that would put one cell across the feature and what that
    grid costs, via the preflight's own floor — and when that is more than
    openEMS can index or this machine can hold it says so instead of telling
    the user to raise MeshResolution. A thin-walled hollow body gets the
    'solid rod' advice, guarded by its bore's waveguide cut-off.

    ``refined`` (write_deck passes it since v1.14.0): ``{id(source): step}``
    for every source part the refinement plan resolves locally, after the
    budget — each such part is judged against its OWN step, and every other
    part against the global cell. None keeps the pre-v1.14.0 rule (a body is
    judged against its blanket step if :func:`_stl_refinement` would blanket
    it, else the global cell), for direct callers.
    """
    bodies = []
    for m in mats:
        # SCOPE, and every exclusion is load-bearing — an earlier draft of this
        # check refused EMStudio's own validated 2.4 GHz patch template:
        #  * DIELECTRICS are excluded: a thin substrate already gets explicit
        #    lines across its thickness further down (_dielectric_thin_axis_lines),
        #    so 0.3 global cells across a 1.524 mm Rogers laminate is fine and
        #    is exactly how the published reference design is meshed.
        #  * BOXES and SHEETS are excluded: thin metal is modelled as a
        #    zero-thickness sheet, the openEMS-canonical form, and gets the
        #    metal-edge thirds rule rather than volume cells.
        # What is left is the real hazard: a metal STL body with genuine
        # thickness that no local refinement rescued.
        if m["kind"] != "metal":
            continue
        for p in m["prims"]:
            if p["kind"] != "stl":
                continue
            feat = float(p.get("min_feature") or 0.0)
            if feat <= 0.0:
                continue
            # A refined body is judged against ITS OWN step (feature / 3), so
            # a single-solid body that refinement takes is never refused —
            # exactly as before — while a much thinner solid hidden inside a
            # multi-solid body still is.
            if refined is None:
                ref = _stl_refinement(p, mesh_res_mm)
                cell = ref[0] if ref is not None else mesh_res_mm
            for src in (p.get("sources")
                        or [{"label": None, "min_feature": feat}]):
                f = float(src.get("min_feature") or 0.0)
                if refined is not None:
                    cell = refined.get(id(src), mesh_res_mm)
                if f <= 0.0 or f / cell >= 1.0:
                    continue
                label = src.get("label") or p.get("label") or m["name"]
                bodies.append({
                    "cells": f / cell, "feat": f, "cell": cell, "src": src,
                    "label": label,
                    "object": src.get("object") or p.get("label") or label,
                    "material": m.get("label") or m["name"]})
    if not bodies:
        return
    # What could sit in a refused tube's bore — every part of the model and
    # every port (``cost["ports"]``, which write_deck fills) — so the fill
    # advice never tells a coax shield to swallow its own inner conductor.
    others = _bore_candidates(mats, (cost or {}).get("ports") or ())
    for b in bodies:
        b["others"] = others
    bodies.sort(key=lambda b: b["cells"])
    raise OpenEMSModelError(_unresolvable_text(bodies, cost))


def _physics(m):
    """What a material IS to the solver — equal tuples fill space identically."""
    return (m["kind"], m.get("epsR"), m.get("tanD"), m.get("kappa"),
            m.get("mu"), m.get("sigma"), m.get("thickness_m"))


def _box_overlap(pa, pb):
    """Volume (mm^3) where two primitives' bounding boxes overlap; 0 if they
    only touch. A zero-thickness sheet never overlaps anything."""
    vol = 1.0
    for i in range(3):
        d = min(pa["stop"][i], pb["stop"][i]) - max(pa["start"][i], pb["start"][i])
        if d <= 1e-6:
            return 0.0
        vol *= d
    return vol


#: Exact (boolean) overlap tests per deck. Each is an OpenCASCADE common()
#: of two solids — milliseconds for simple parts, far more for threaded
#: hardware — so beyond this the bounding-box overlap is reported as
#: "may overlap" rather than letting a large assembly stall the writer.
_MAX_EXACT_OVERLAPS = 200

#: ...and a wall-clock budget for all of them together, for the same reason:
#: a count cap alone still lets 200 helical-thread booleans take minutes
#: (the diagnosis review's warning about Fasteners solids). Past it, the
#: remaining pairs are reported on their bounding boxes. One common() already
#: running cannot be interrupted, so this bounds the START of each test.
_EXACT_OVERLAP_BUDGET_S = 10.0


def _overlap_notes(mats):
    """Warn when two DIFFERENT materials fill the same space at the SAME Priority.

    ⚠ openEMS has no rule for that tie. It takes, at each point, the first
    primitive in a list CSXCAD sorts by priority with ``std::sort`` — not a
    stable sort (ContinuousStructure::GetAllPrimitives, used by the
    operator's GetPrimitivesByBoundBox) — so which material fills the
    overlap is not decided by anything the user can see. Found in review of
    the forum J-pole: giving its Back plate a dielectric material at the
    default Priority 10 ties with the PEC 'Feed' group that still contains
    the plate, and the "fix" then silently may or may not apply.
    WARN ONLY: the documents this fires on run today, and the user is the
    one who knows which material should win.

    Materials whose physics are identical (two PEC materials) are skipped:
    whichever wins, the cell is the same.
    """
    import time

    out = []
    exact_left = _MAX_EXACT_OVERLAPS
    deadline = time.monotonic() + _EXACT_OVERLAP_BUDGET_S
    for i in range(len(mats)):
        for j in range(i + 1, len(mats)):
            a, b = mats[i], mats[j]
            if a["priority"] != b["priority"] or _physics(a) == _physics(b):
                continue
            found = []
            for pa in _overlap_parts(a):
                for pb in _overlap_parts(b):
                    vol = _box_overlap(pa, pb)
                    if vol <= 0.0:
                        continue
                    exact = None
                    both_boxes = (pa["kind"] == "box" and pb["kind"] == "box"
                                  and pa.get("sheet_axis") is None
                                  and pb.get("sheet_axis") is None)
                    if both_boxes:
                        exact = vol         # a solid box IS its bounding box
                    elif (exact_left > 0 and time.monotonic() < deadline
                          and pa.get("shape") is not None
                          and pb.get("shape") is not None):
                        exact_left -= 1
                        try:
                            exact = float(pa["shape"].common(pb["shape"]).Volume)
                        except Exception:                      # noqa: BLE001
                            exact = None
                    if exact is not None:
                        floor = 1e-6 * min(
                            _prim_volume(pa) or vol, _prim_volume(pb) or vol)
                        if exact <= max(1e-9, floor):
                            continue        # touching, not overlapping
                    found.append((pa, pb, exact, vol))
            for pa, pb, exact, vol in found[:5]:
                how = ("overlap by about {0:.4g} mm^3".format(exact)
                       if exact is not None else
                       "may overlap (their bounding boxes share {0:.4g} mm^3; "
                       "the exact test was not run)".format(vol))
                out.append(
                    "EMStudio: WARNING - '{la}' (material '{ma}') and '{lb}' "
                    "(material '{mb}') {how} at the same Priority {p}. openEMS "
                    "has no rule for that tie: CSXCAD orders primitives by "
                    "priority with an unstable sort, so which material fills "
                    "the overlap is not set by anything in the model. Give the "
                    "one that should win a higher Priority (higher wins)."
                    .format(la=pa.get("label") or a["name"],
                            ma=a.get("label") or a["name"],
                            lb=pb.get("label") or b["name"],
                            mb=b.get("label") or b["name"], how=how,
                            p=a["priority"]))
            if len(found) > 5:
                out.append(
                    "EMStudio: WARNING - ... and {0} more overlapping pair(s) "
                    "between materials '{1}' and '{2}' at Priority {3}.".format(
                        len(found) - 5, a.get("label") or a["name"],
                        b.get("label") or b["name"], a["priority"]))
    return out


def _overlap_parts(m):
    """A material's primitives as the overlap check should see them: a fused
    STL is broken back into its source parts (each with its own bounding box
    and solid), so a tie is reported against the part the user drew — 'Feed
    > Back plate', not a 21-part fused solid — and its exact overlap is
    computed on that part alone. Unfused primitives pass through as they are,
    so every message this check printed before v1.14.0 is unchanged."""
    for p in m["prims"]:
        parts = p.get("parts")
        if not parts:
            yield p
            continue
        for q in parts:
            yield {"kind": "stl", "start": q["start"], "stop": q["stop"],
                   "label": q.get("label"), "shape": q.get("solid")}


def _prim_volume(p):
    try:
        return float(p["shape"].Volume) if p.get("shape") is not None else None
    except Exception:                                        # noqa: BLE001
        return None


def _ascii(text):
    """A deck print() must be ASCII: on Windows the pipe is encoded in the
    locale's code page, and a label it cannot encode would crash the deck on
    the line meant to inform the user (the same rule as the preflight)."""
    return (str(text).replace("—", "-").replace("–", "-")
            .encode("ascii", "replace").decode("ascii"))


#: The comment that opens a deck's model-notes block — the anchor
#: :func:`deck_model_notes` reads back. The emitter and the reader both use
#: this constant, so they cannot drift apart.
MODEL_NOTES_MARK = "# EMStudio model notes"


def deck_model_notes(deck_path):
    """The model notes a written deck carries: ``[("warning"|"note", text)]``.

    For a caller that holds the deck but not the writer's state — the runner,
    which puts them into ``result.meta["warnings"]`` / ``["notes"]`` beside
    its own, so the results dialog can show what was left out of the model
    and why. Read from the deck because the deck IS the record: a FullSMatrix
    excitation, or a deck re-run by hand, carries the same block.
    Empty (never an exception) for a deck with no notes or that cannot be read.
    """
    import ast

    out = []
    try:
        with open(deck_path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    inside = False
    for ln in lines:
        if not inside:
            inside = ln.startswith(MODEL_NOTES_MARK)
            continue
        if not (ln.startswith("print(") and ln.endswith(", flush=True)")):
            break                       # the blank line that ends the block
        try:
            text = ast.literal_eval(ln[len("print("):-len(", flush=True)")])
        except (ValueError, SyntaxError):
            continue
        out.append(("warning" if str(text).startswith("EMStudio: WARNING")
                    else "note", str(text)))
    return out


def _say(notes):
    """Put the model notes in FreeCAD's Report view, now, at deck-write time.

    The deck prints them again when it runs, so they also reach the solver
    log the runner captures; this copy is the one a refused model still
    shows (a refusal raises before any deck exists).
    """
    if not notes:
        return
    try:
        import FreeCAD
    except Exception:                                        # noqa: BLE001
        return
    for msg in notes:
        try:
            (FreeCAD.Console.PrintWarning if "WARNING" in msg[:20]
             else FreeCAD.Console.PrintMessage)(msg + "\n")
        except Exception:                                    # noqa: BLE001
            pass


# --------------------------------------------------------------------------- helpers
def _fmt_v(v):
    return "[{0:.9g}, {1:.9g}, {2:.9g}]".format(*v)


def _collect_materials(analysis, workdir, notes=None, export=True):
    """Returns list of dicts: {name, label, kind: metal|dielectric, params, prims, priority}.

    ``notes`` collects the reference warnings/notes geometry.classify_shapes
    raises (None: they go straight to FreeCAD's Report view). ``label`` is
    the material as the USER named it — ``name`` is the deck identifier
    ('mat1_EMMaterial001'), which no message should show a user.
    ``export=False`` writes nothing (``workdir`` unused): the classification
    only, for :func:`grid_estimate` — see geometry.classify_shapes.
    """
    mats = []
    # The global cell, for the tessellation's mesh_res/4 deflection cap
    # (geometry.stl_deflection_mm). The AIR rule, because the microstrip
    # branch's finer dielectric cell needs the materials read first; that
    # branch is boards of boxes, and a part's own feature/2 cap is the one
    # that binds on anything thin anyway.
    f1, f2, _n = Analysis.freq_range_hz(analysis)
    tess_res = C0 / f2 / 1e-3 / max(6, int(analysis.MeshResolution))
    for i, mat in enumerate(query.get_materials(analysis)):
        prims = geometry.classify_shapes(mat, workdir, "mat{0}".format(i + 1),
                                         notes=notes, mesh_res_mm=tess_res,
                                         export=export)
        if not prims:
            continue
        category = str(mat.Category)
        entry = {
            "name": "mat{0}_{1}".format(i + 1, "".join(c for c in mat.Label if c.isalnum()) or "m"),
            "label": str(mat.Label),
            "prims": prims,
            "priority": int(mat.Priority),
        }
        if category.startswith("Conductor") and float(mat.Conductivity) > 0.0:
            # ⚠⚠ UNTIL 2026-08-22 THIS FELL INTO THE "metal" BRANCH AND THE
            # USER'S SIGMA WAS DISCARDED — a settable field that changed
            # nothing, on a backend that reported the resulting lossless gain
            # as fact. openEMS models finite-conductivity metal with a SURFACE
            # IMPEDANCE sheet, which is the only tractable choice: resolving a
            # real skin depth (2 um in copper at 1 GHz) on an FDTD grid is not
            # affordable, and a lossy VOLUME material would demand exactly that.
            entry["kind"] = "conducting_sheet"
            entry["sigma"] = float(mat.Conductivity)
            try:
                entry["thickness_m"] = float(
                    mat.SheetThickness.getValueAs("m"))
            except Exception:
                entry["thickness_m"] = 35e-6      # 1 oz copper
        elif category.startswith("Metal") or category.startswith("Conductor"):
            entry["kind"] = "metal"
        else:
            entry["kind"] = "dielectric"
            entry["epsR"] = float(mat.RelPermittivity)
            entry["tanD"] = float(mat.LossTangent)
            entry["kappa"] = float(mat.Conductivity)
            entry["mu"] = float(mat.RelPermeability)
        mats.append(entry)
    if not mats:
        # ⚠ Carry the REASONS: when every reference reached nothing, the
        # warnings that say why went to the Report view a moment ago, and a
        # dialog that showed only this line would hide them behind it.
        why = [n[len("EMStudio: WARNING - "):] for n in (notes or ())
               if n.startswith("EMStudio: WARNING - ")]
        raise OpenEMSModelError(
            "no material with usable geometry found in the analysis"
            + (" — " + " ".join(why[:4])
               + (" (and {0} more)".format(len(why) - 4) if len(why) > 4
                  else "") if why else ""))
    return mats


def _port_span(port):
    """Port span (start, stop) in mm from the referenced sub-shape's bbox.

    ``subobjects=True``: an edge picked THROUGH a group in the 3-D view
    ('Grp.Sketch.Edge2') resolves too. Until v1.14.0 it came back None and the
    port was refused as having "no usable geometry reference" although the
    user had picked one. (No de-duplication question here: the first usable
    reference is the span, as it always was.)
    """
    for _, shape, _sub in query.resolved_references(port, subobjects=True):
        if shape is None:
            continue
        bb = shape.BoundBox
        return (bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)
    raise OpenEMSModelError(
        "port '{0}' has no usable geometry reference (needs an edge/face spanning "
        "the feed gap)".format(port.Label)
    )


#: How many mesh cells an EXCITED waveguide port spans between its
#: excitation plane and its probe plane. Upstream's Rect_Waveguide
#: tutorial uses four for its excited port; one is already enough
#: (measured, see the comment in _collect_ports), so four is margin.
_WG_PORT_CELLS = 4


def _collect_ports(analysis, excite_port=None, cell_mm=None):
    ports = []
    for port in query.get_ports(analysis):
        start, stop = _port_span(port)
        direction = str(port.Direction)  # e.g. "+Z"
        axis = direction[-1].lower()
        excite = 1.0 if direction[0] == "+" else -1.0
        edges2grid = "".join(a for a in AXES if a != axis)
        ptype = str(getattr(port, "PortType", "Lumped"))
        prop_dir = str(getattr(port, "PropagationDirection", "+X"))
        entry = {
            "nr": int(port.PortNumber),
            "R": float(port.Impedance.getValueAs("Ohm")),
            "start": start,
            "stop": stop,
            "axis": axis,
            # ``excite_port`` overrides the document's own Excited flags so a
            # caller can drive each port in turn for a full S-matrix. openEMS
            # solves ONE excitation per run, so an N-port needs N runs.
            "excite": excite if (
                int(port.PortNumber) == int(excite_port) if excite_port
                else port.Excited) else 0.0,
            "edges2grid": edges2grid,
            "type": ptype,
        }
        if ptype == "RectWaveguide":
            # ⛳ a and b come from the referenced FACE's own bounding box, not
            # from user-typed numbers, so the mode profile and the geometry
            # cannot disagree. openEMS wants them in METRES; the document is in
            # mm, which is exactly the units slip that made a cavity "converge
            # beautifully" on nonsense once before.
            entry["prop_axis"] = prop_dir[-1].lower()
            entry["prop_sign"] = 1.0 if prop_dir[0] == "+" else -1.0
            pi = AXES.index(entry["prop_axis"])
            # ⚠⚠ a AND b ARE BOUND TO AXES, NOT TO SIZE. ``RectWGPort.__init__``
            # sets ny_P = (prop+1)%3 and ny_PP = (prop+2)%3, then writes the mode
            # functions as sin(M*pi/a * <ny_P>) and sin(N*pi/b * <ny_PP>)
            # (openEMS/ports.py). So ``a`` MUST be the span on ny_P and ``b`` the
            # span on ny_PP, whatever their relative size — the docstring there
            # says it too: "a : dimension along the first transverse axis".
            # ⚠⚠ UNTIL 2026-08-29 THIS SORTED THEM BY SIZE ("a is the BROAD
            # wall"), which is right only when the broad wall happens to land on
            # ny_P. MEASURED on four WR-28 faces: broad-wall-on-Y with prop +Z,
            # and the CONVENTIONAL broad-wall-on-X drawing whenever prop is +/-Y
            # (there ny_P is z), both got a and b swapped — a half-sine of
            # period 2a imposed across an aperture of width b, i.e. peak field ON
            # the PEC wall, polarised along the wrong transverse axis. Not a mode
            # at all, and SILENT: kc below is unchanged, so cutoff, beta and the
            # modal ZL all still look right and the run returns a complete,
            # meaningless S11 / Zin / gain / pattern set.
            i_P, i_PP = (pi + 1) % 3, (pi + 2) % 3
            span_P = abs(stop[i_P] - start[i_P])
            span_PP = abs(stop[i_PP] - start[i_PP])
            entry["wg_a_m"] = span_P * 1e-3
            entry["wg_b_m"] = span_PP * 1e-3
            mode = str(getattr(port, "WaveguideMode", "TE10") or "TE10")
            # ⛳ ...and the MODE NAME is translated into that axial convention,
            # which is what keeps the old promise — "the port works whatever way
            # round the face was drawn" — without lying to the engine about which
            # axis is which. The user types the textbook spelling, where a is the
            # BROAD wall, so "TE10" means the dominant mode however the face was
            # drawn. When the broad wall lands on ny_PP the SAME physical mode is
            # spelled with the indices swapped (TE10 -> TE01: E along ny_P,
            # half-sine along ny_PP). kc = sqrt((M*pi/a)^2 + (N*pi/b)^2) is
            # invariant under swapping (M,a) with (N,b), so cutoff, beta and the
            # modal reference impedance are untouched by this whole block — only
            # the field axes move, which is the defect.
            # ⚠ Guarded on the 4-character form openEMS itself requires
            # ('Invalid mode definition' otherwise); anything else is passed
            # through unaltered so the engine raises its own error, not ours.
            if span_PP > span_P and len(mode) == 4 and mode[2:].isdigit():
                mode = mode[:2] + mode[3] + mode[2]
            entry["wg_mode"] = mode
            # ⚠⚠ AN EXCITED WAVEGUIDE PORT MAY NOT BE ZERO-LENGTH along the
            # propagation axis — openEMS raises "Port length in excitation
            # direction may not be zero if port is excited!". A port FACE is
            # naturally zero-thickness, so it must be given depth here or every
            # excited waveguide run dies at deck time.
            #
            # ⚠⚠ AND THE DEPTH IS NOT COSMETIC — IT IS THE DISTANCE BETWEEN THE
            # SOURCE AND THE PROBES. openEMS puts the mode excitation on the
            # ``start`` plane and the voltage/current probes on the ``stop``
            # plane (openEMS/ports.py, WaveguidePort.__init__), so this span is
            # how far downstream the port measures. Too close and the probes sit
            # inside the source's own near field and report nonsense.
            #
            # This used to be ``min(a, b) / 20``, a fraction of the guide's
            # NARROW WALL with no relation to the grid, described in a comment
            # as "exactly ONE mesh cell". On WR-28 at Ka band it delivers
            # 0.1778 mm against a 0.3747 mm cell — **0.48 of a cell**.
            # ⛳ MEASURED on a straight PEC-walled WR-28 section terminated in
            # PML (tests/validation/waveguide_port_openems.py), where the right
            # answer is |S11| ~ 0 and P_acc/P_inc = 1:
            #     0.48 cells -> |S11| = 0.00 dB, P_acc/P_inc = 0.0004  (dead)
            #     1, 2, 4, 8, 16 cells -> |S11| = -45..-53 dB, P_acc/P_inc = 1.0000
            # One cell is already enough; four is what upstream's own
            # Rect_Waveguide tutorial gives its EXCITED port (z(11) -> z(15)).
            # ⚠ The one-cell span in that tutorial belongs to port 2, which is
            # NOT excited — copying it onto the excited port was the mistake.
            # ⚠ This assumes at least four cells of STRAIGHT guide behind the
            # face; a port placed within lambda/5 of a flare or a bend will
            # measure inside the discontinuity.
            plo, phi = start[pi], stop[pi]
            if abs(phi - plo) < 1e-12:
                depth = max(_WG_PORT_CELLS * float(cell_mm or 0.0), 1e-3)
                st, sp = list(start), list(stop)
                if entry["prop_sign"] >= 0:
                    sp[pi] = plo + depth
                else:
                    sp[pi] = plo - depth
                entry["start"], entry["stop"] = tuple(st), tuple(sp)
            if entry["wg_a_m"] <= 0.0 or entry["wg_b_m"] <= 0.0:
                raise OpenEMSModelError(
                    "waveguide port '{0}' needs a FACE with two non-zero "
                    "transverse dimensions; got a={1:g} b={2:g} mm".format(
                        port.Label, entry["wg_a_m"] * 1e3, entry["wg_b_m"] * 1e3))
        if ptype == "MSL":
            entry["prop_axis"] = prop_dir[-1].lower()
            entry["prop_sign"] = 1.0 if prop_dir[0] == "+" else -1.0
            # For AddMSLPort the box span encodes two directions that MUST match the
            # physics (bbox min->max is not enough):
            #  * E-field / exc axis: span runs strip->ground, i.e. ALONG the field
            #    Direction (Direction '-Z' => start at top h, stop at 0).
            #  * propagation axis: span runs along PropagationDirection; openEMS
            #    puts the feed at 'start' and the wave leaves toward 'stop'.
            s, e = list(entry["start"]), list(entry["stop"])
            ei = AXES.index(axis)
            lo, hi = min(s[ei], e[ei]), max(s[ei], e[ei])
            if excite_dir_negative(direction):
                s[ei], e[ei] = hi, lo  # field points to -axis: start high, stop low
            else:
                s[ei], e[ei] = lo, hi
            pi = AXES.index(entry["prop_axis"])
            plo, phi = min(s[pi], e[pi]), max(s[pi], e[pi])
            if entry["prop_sign"] < 0:
                s[pi], e[pi] = phi, plo
            else:
                s[pi], e[pi] = plo, phi
            entry["start"], entry["stop"] = tuple(s), tuple(e)
        ports.append(entry)
    # ⚠ "exactly one" has to be COUNTED, not tested with `any`. Every port
    # created through the GUI carries Excited=True by default
    # (``LumpedPort._ensure_properties``), so a user who adds a second port the
    # obvious way gets a deck that drives BOTH — and openEMS accepts it. The
    # post-processing below then computes s11 = uf_ref/uf_inc for port 1 as if
    # it were the only source, so port 1's incident wave is contaminated by
    # port 2's drive and the S-parameters are silently wrong. No exception, no
    # warning, a plausible-looking answer. Reproduced live 2026-08-20.
    # The shipped templates are unaffected — msl_filter sets port2.Excited =
    # False explicitly — and FullSMatrix is unaffected too, because its runner
    # drives one port per excitation and clears the rest.
    n_excited = sum(1 for p in ports if p["excite"])
    if n_excited > 1:
        raise OpenEMSModelError(
            "openEMS solves ONE excitation per run, but {0} ports are marked "
            "Excited: {1}. Un-tick Excited on all but one, or use the "
            "FullSMatrix option, which drives each port in turn and merges "
            "the columns into a full S-matrix.".format(
                n_excited,
                ", ".join("port {0}".format(p.get("nr", "?"))
                          for p in ports if p["excite"])))
    if not any(p["excite"] for p in ports):
        raise OpenEMSModelError(
            "the analysis needs exactly one excited port"
            + ("" if not excite_port else
               " — port {0} was requested but the analysis has no such port"
               .format(excite_port)))
    return ports


#: Relative margin above a waveguide mode's cut-off below which a sample is
#: treated as cut off. openEMS's own test is exact (beta = sqrt(k^2 - kc^2):
#: NaN below, 0 AT cut-off, where ZL = k*Z0/beta is infinite), and this
#: writer repeats it in double precision — 1e-9 only absorbs the last-bit
#: difference between this module's frequency samples and np.linspace's, so
#: a sample sitting exactly on cut-off can never slip through as infinity.
#: Physically nothing is lost: 1e-9 above cut-off beta is ~4e-5 of k, and a
#: guide that close to cut-off has no meaningful port impedance either.
_WG_CUTOFF_MARGIN = 1e-9


def _wg_cutoff_hz(p):
    """Cut-off frequency (Hz) of a RectWaveguide port entry's mode, or None.

    EXACTLY openEMS's own rule (openEMS/ports.py, RectWGPort.__init__ and
    WaveguidePort.CalcPort): kc = sqrt((M*pi/a)^2 + (N*pi/b)^2) with a and b
    in METRES, the guide treated as AIR (``ref_index = 1`` is hard-wired
    there), and beta = sqrt(k^2 - kc^2) — so below this frequency openEMS's
    beta, its modal ZL and every S-parameter referred to it are NaN. It
    reads the entry AFTER _collect_ports' axis translation (a on ny_P, b on
    ny_PP, the mode indices swapped with them), which is what the deck hands
    openEMS; kc is invariant under that swap, so the textbook figure (TE10
    of WR-28: c / 2a = 21.08 GHz) comes out either way round.
    None for a mode string openEMS itself would reject — the deck then
    raises openEMS's own error, as it always did.
    """
    mode = str(p.get("wg_mode", ""))
    if len(mode) != 4 or not mode[2:].isdigit():
        return None
    a, b = float(p["wg_a_m"]), float(p["wg_b_m"])
    if a <= 0.0 or b <= 0.0:
        return None
    m, n = float(mode[2]), float(mode[3])
    kc = math.sqrt((m * math.pi / a) ** 2 + (n * math.pi / b) ** 2)
    return kc * C0 / (2.0 * math.pi)


def _wg_user_mode(p):
    """(mode, a mm, b mm) as the USER spells them — the broad wall first.

    The entry carries openEMS's axis-bound form (TE10 becomes TE01 when the
    broad wall lands on ny_PP, see _collect_ports), which a message quoting
    it would only make look wrong.
    """
    a_mm, b_mm = p["wg_a_m"] * 1e3, p["wg_b_m"] * 1e3
    mode = str(p["wg_mode"])
    if b_mm > a_mm and len(mode) == 4:
        mode, a_mm, b_mm = mode[:2] + mode[3] + mode[2], b_mm, a_mm
    return mode, a_mm, b_mm


def _sweep_samples(f1, f2, npts):
    """The deck's ``np.linspace(f1, f2, npts)``, in plain Python.

    numpy builds it as ``start + i * step`` and pins the last sample to
    ``stop``; so does this, so the samples counted here are the samples the
    deck computes (to the last bit, which _WG_CUTOFF_MARGIN covers anyway).
    """
    n = int(npts)
    if n < 2:
        return [float(f1)] if n == 1 else []
    step = (float(f2) - float(f1)) / (n - 1)
    out = [float(f1) + i * step for i in range(n - 1)]
    out.append(float(f2))
    return out


def _waveguide_band(ports, f1, f2, npts):
    """Which leading sweep samples lie below a waveguide port's cut-off.

    ⚠⚠ BELOW CUT-OFF openEMS GIVES NaN, NOT A NUMBER TO DISTRUST. Its
    WaveguidePort.CalcPort takes beta = sqrt(k^2 - kc^2) on a REAL numpy
    array, so every sample under the mode's cut-off comes back NaN in S11
    and in the modal reference impedance (and in every transmission term
    referred to that port's incident wave). Since v1.14.0 a NaN refuses the
    whole result (sparams.require_finite) — so a WR-28 run swept 18-30 GHz,
    whose 18 samples from 21.5 GHz up were finite, was thrown away entire,
    and the runner blamed a port "never in the simulation" (v1.14.0 review,
    reproduced through runner.run: NaN in exactly the 7 rows 18-21 GHz,
    TE10 cut-off 21.08 GHz).
    The writer knows a, b and the mode, so it decides here, before the run:
    the samples below the HIGHEST cut-off of any waveguide port in the
    model are left out of the post-processing grid. Highest, because any
    waveguide port's NaN spoils the terms referred to it, and one cut for
    the whole model keeps every FullSMatrix excitation on one frequency
    grid (the runner refuses excitations that disagree).

    Returns None when nothing is cut off (no waveguide port, or the whole
    band above every cut-off — then the deck is byte-identical to before);
    else ``{"drop": samples left out (a leading run, since f ascends and
    the test is monotone), "npts": total, "fc_hz": the cut-off that sets
    it, "nr": its port, "mode": the textbook mode name the user typed,
    "a_mm"/"b_mm": its face, "f_first"/"f_last_drop"/"f_first_keep":
    Hz (f_first_keep None when nothing is left)}``. ``drop == npts`` means
    the whole band is cut off.
    """
    worst = None
    for p in ports:
        if p.get("type") != "RectWaveguide":
            continue
        fc = _wg_cutoff_hz(p)
        if fc is not None and (worst is None or fc > worst[0]):
            worst = (fc, p)
    if worst is None:
        return None
    fc, p = worst
    samples = _sweep_samples(f1, f2, npts)
    drop = sum(1 for f in samples if f <= fc * (1.0 + _WG_CUTOFF_MARGIN))
    if not drop:
        return None
    mode, a_mm, b_mm = _wg_user_mode(p)
    return {"drop": drop, "npts": len(samples), "fc_hz": fc,
            "nr": p["nr"], "mode": mode, "a_mm": a_mm, "b_mm": b_mm,
            "f_first": samples[0] if samples else None,
            "f_last_drop": samples[drop - 1],
            "f_first_keep": samples[drop] if drop < len(samples) else None}


def _ghz(f_hz):
    """'21.08 GHz' — four figures, as the messages quote a cut-off."""
    return "{0:.4g} GHz".format(f_hz / 1e9)


def _cutoff_refusal(cut, f1, f2):
    """The refusal for a band that lies ENTIRELY below a waveguide cut-off."""
    return (
        "waveguide port {nr} ({mode}, face {a:.4g} x {b:.4g} mm) is cut off "
        "below {fc}, and the whole band, {f1} to {f2}, lies below that: the "
        "mode does not propagate there, and openEMS's waveguide port returns "
        "no number at any frequency of it (NaN, not a poor match). Sweep "
        "above {fc}, or check the port face's size and its WaveguideMode."
        .format(nr=cut["nr"], mode=cut["mode"], a=cut["a_mm"],
                b=cut["b_mm"], fc=_ghz(cut["fc_hz"]), f1=_ghz(f1),
                f2=_ghz(f2)))


def _cutoff_note(cut):
    """The NOTE for a band that STARTS below a waveguide cut-off."""
    return (
        "EMStudio: NOTE - waveguide port {nr} ({mode}, face {a:.4g} x {b:.4g} "
        "mm) only carries its mode above its cut-off of {fc}, so the {n} "
        "frequency sample(s) from {lo} to {hi} are left out of the result: "
        "below cut-off openEMS's waveguide port returns no number (NaN). The "
        "result runs from {keep} ({k} samples). Start the band above {fc} to "
        "keep every sample.".format(
            nr=cut["nr"], mode=cut["mode"], a=cut["a_mm"], b=cut["b_mm"],
            fc=_ghz(cut["fc_hz"]), n=cut["drop"], lo=_ghz(cut["f_first"]),
            hi=_ghz(cut["f_last_drop"]), keep=_ghz(cut["f_first_keep"]),
            k=cut["npts"] - cut["drop"]))


#: A lumped-port end counts as ON metal within this fraction of the local
#: cell. A TENTH: the same tenth the deck's _port_end treats as one place
#: for a resolution helper line. The warning below is for a port drawn
#: CLEAR of its metal (an end left floating mm away, a gap drawn edge to
#: edge in the wrong plane), not for float slop or an import's tolerance,
#: which sit orders of magnitude under a tenth of any cell.
_PORT_CONTACT_FRACTION = 0.1


def _box_gap(lo1, hi1, lo2, hi2):
    """Distance between two axis-aligned boxes (0 when they touch) — a
    LOWER bound on the distance between anything inside them."""
    return math.sqrt(sum(max(0.0, lo2[i] - hi1[i], lo1[i] - hi2[i]) ** 2
                         for i in range(3)))


def _port_contact_warnings(ports, mats, mesh_res_mm, kept=()):
    """WARNINGs for lumped ports with an end that touches no metal.

    ⚠⚠ SINCE v1.14.0 A PORT IS SIMULATED EXACTLY WHERE IT IS DRAWN. Each
    lumped-port end is a grid line (the deck's _port_end), which is what
    fixed the box-bar J-pole whose feed end openEMS used to snap 4.16 mm
    into air. The flip side: an end drawn in air is no longer dropped by
    openEMS (which once surfaced as an all-NaN result, now a failed run) —
    it is simulated as drawn, a source driving into a sliver of air, and
    the run returns finite, plausible, MEANINGLESS S11 and impedance with
    no word from anyone (v1.14.0 stage O3's open issue). This says it.

    Each end is the face of the port's box at that end of its excitation
    axis — the box IS the port openEMS builds (AddLumpedPort takes the
    reference's bounding box), so a slanted edge is judged as simulated —
    and is tested against every METAL part's own source shape
    (distToShape: 0 on or inside it), nearest boxes first, stopping at the
    first contact. Tolerance: _PORT_CONTACT_FRACTION of the local cell
    (the finest refinement step of a part around the end, else the global
    cell). A part this cannot measure exactly (an imported mesh, or an OCC
    call that throws) counts as touching wherever its box does: a missed
    warning, never a false one.
    """
    import FreeCAD
    import Part

    lumped = [p for p in ports if p["type"] not in ("MSL", "RectWaveguide")]
    if not lumped:
        return []
    cands = []                       # (lo, hi, shape or None, label)
    for m in mats:
        if m["kind"] not in ("metal", "conducting_sheet"):
            continue
        for p in m["prims"]:
            srcs = [s for s in (p.get("sources") or ()) if s.get("solid")]
            if p["kind"] == "stl" and srcs:
                # Per SOURCE part, so the message names 'Feed > Mount', not
                # the fused STL it went into.
                cands.extend((s["start"], s["stop"], s["solid"], s["label"])
                             for s in srcs)
            else:
                cands.append((p["start"], p["stop"], p.get("shape"),
                              p["label"]))
    out = []
    for p in lumped:
        ai = AXES.index(p["axis"])
        lo = [min(p["start"][i], p["stop"][i]) for i in range(3)]
        hi = [max(p["start"][i], p["stop"][i]) for i in range(3)]
        afloat = []
        for v in sorted({lo[ai], hi[ai]}):
            e_lo, e_hi = list(lo), list(hi)
            e_lo[ai] = e_hi[ai] = v
            local = float(mesh_res_mm)
            for e in kept:
                s = e["src"]
                if _box_gap(e_lo, e_hi, s["start"], s["stop"]) <= mesh_res_mm:
                    local = min(local, float(e["step"]))
            tol = max(_PORT_CONTACT_FRACTION * local, 1e-6)
            # The end as OCC geometry: a point, a segment or a rectangle,
            # by how many of its two other axes have extent.
            V = FreeCAD.Vector
            span = [i for i in range(3) if i != ai and e_hi[i] - e_lo[i] > 0]
            try:
                if not span:
                    end = Part.Vertex(V(*e_lo))
                elif len(span) == 1:
                    end = Part.makeLine(V(*e_lo), V(*e_hi))
                else:
                    j, k = span
                    c = []
                    for a, b in ((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)):
                        q = list(e_lo)
                        q[j] = (e_lo[j], e_hi[j])[a]
                        q[k] = (e_lo[k], e_hi[k])[b]
                        c.append(V(*q))
                    end = Part.Face(Part.makePolygon(c))
            except Exception:                              # noqa: BLE001
                continue                     # cannot build it: no claim
            best = None                      # (distance, label)
            touched = False
            for gap, _c_lo, _c_hi, shape, label in sorted(
                    ((_box_gap(e_lo, e_hi, c[0], c[1]),) + tuple(c)
                     for c in cands), key=lambda t: t[0]):
                if best is not None and gap >= best[0]:
                    break        # a box gap is a lower bound: none is nearer
                d = gap
                if shape is not None:
                    try:
                        d = float(end.distToShape(shape)[0])
                    except Exception:                      # noqa: BLE001
                        d = gap              # unmeasurable: its box decides
                if best is None or d < best[0]:
                    best = (d, label)
                if d <= tol:
                    touched = True
                    break
            if not touched:
                afloat.append((v, best, local))
        if not afloat:
            continue
        where = "; ".join(
            "at {ax} = {v:.6g} mm {near}".format(
                ax=p["axis"], v=v,
                near=("the nearest metal, '{0}', is {1:.3g} mm away".format(
                    b[1], b[0]) if b else "there is no metal in the model"))
            for v, b, _l in afloat)
        out.append(
            "EMStudio: WARNING - port {nr} touches no metal at {which}: "
            "{where} (local cell {cell:.3g} mm). openEMS simulates a lumped "
            "port exactly where it is drawn, so an end in air feeds nothing "
            "there, and this port's S11 and impedance do not describe the "
            "antenna. Draw the port edge across the feed gap from one "
            "conductor to the other, with both ends ON the metal.".format(
                nr=p["nr"],
                which=("either end" if len(afloat) == 2 else "one end"),
                where=where, cell=min(l for _v, _b, l in afloat)))
    return out


def waveguide_cutoffs(analysis):
    """``[(port_nr, mode, cut-off Hz)]`` of the analysis' waveguide ports.

    For the runner, which must not call a NaN below a cut-off "a port never
    in the simulation" (runner._load_port_csv). Empty — never an exception —
    for an analysis whose ports cannot be read: write_deck has already said
    why, and this only chooses between two error messages.
    """
    try:
        ports = _collect_ports(analysis)
    except Exception:                                      # noqa: BLE001
        return []
    out = []
    for p in ports:
        if p.get("type") == "RectWaveguide":
            fc = _wg_cutoff_hz(p)
            if fc is not None:
                out.append((p["nr"], _wg_user_mode(p)[0], fc))
    return out


#: Real air the guard insists on between the geometry and the ABSORBER, as a
#: fraction of the centre wavelength, when it has to step in. Upstream's own
#: horn tutorial uses lambda/2 to the sides and front and lambda/4 behind, on
#: top of its PML allowance (Horn_Antenna.py); a quarter wavelength is the
#: smaller of the two and is what a rescue should restore — enough for the
#: reactive near field to form before it is absorbed, without silently
#: inflating a domain by more than the situation demands.
MIN_ABSORBER_CLEARANCE_WAVELENGTHS = 0.25


def _geometry_bbox(mats):
    """Tight bounding box over every emitted primitive."""
    inf = float("inf")
    lo = [inf, inf, inf]
    hi = [-inf, -inf, -inf]
    for m in mats:
        for p in m["prims"]:
            for i in range(3):
                lo[i] = min(lo[i], p["start"][i])
                hi[i] = max(hi[i], p["stop"][i])
    return lo, hi


def absorber_depth_mm(boundary, mesh_res_mm):
    """How much of a face's padding the ABSORBER occupies, in mm.

    ⚠ PML_N eats N cells of mesh, and openEMS then places the NF2FF recording
    surface one line further in (``CreateNF2FFBox``: ``BC_size = PML_size + 1``),
    so the depth that matters to a radiating model is **N + 1**, not N. Using N
    leaves the recording surface itself inside the structure, which is the
    failure that produced a -60 dBi pattern floor with eta = nan.

    MUR costs 2 lines by the same rule and PEC/PMC cost none (those faces are
    mirrored, not recorded). Returning 0 for them is what keeps this guard from
    touching the shipped MUR templates.
    """
    bc = str(boundary)
    if bc.startswith("PML_"):
        try:
            return (int(bc[4:]) + 1) * float(mesh_res_mm)
        except ValueError:
            return 0.0            # _nf2ff_bc refuses this properly, with a message
    if bc == "MUR":
        return 2.0 * float(mesh_res_mm)
    return 0.0


def _domain(analysis, mats, lam_c_mm, mesh_res_mm=None, boundaries=None):
    """(geo_lo, geo_hi, dom_lo, dom_hi, notes).

    Simulation box = geometry bbox + ``DomainPaddingWavelengths`` on every side
    — and then, if an ABSORBING boundary would start inside that padding, the
    face is pushed out far enough to clear it.

    ⚠⚠ WHY THE GUARD EXISTS. ``DomainPaddingWavelengths`` defaults to 0.25,
    which was chosen for MUR — a one-cell condition, so 0.25 lambda of padding
    is 0.25 lambda of air. PML_8 is EIGHT cells deep (nine, counting the NF2FF
    surface), and its depth is set by the MESH, not by the wavelength. At Ka
    band on the shipped horn that is 3.373 mm against 2.254 mm of padding:
    MEASURED, the absorber's inner face lands 0.372 mm INSIDE the geometry on
    all six sides, and the NF2FF surface 0.745 mm inside. The first horn run
    done that way returned the -60 dBi pattern floor with eta = nan, because
    the port accepted no power at all.
    ⛳ Upstream sizes its domain the same way and says so:
    ``bc_offset = 9  # PML_8 + 1 cell, matches CreateNF2FFBox placement`` then
    ``margin = lam0/2 + bc_offset*max_res`` (Horn_Antenna.py).

    ⚠ IT ENLARGES, IT DOES NOT RAISE. Refusing would break documents that run
    today and produce a plausible answer; growing the box costs cells and says
    so in the deck and in ``notes``. It fires ONLY when the absorber would
    otherwise start at or inside the geometry, so a model with adequate padding
    — including every shipped MUR template and the horn at its own 1.0 lambda —
    is untouched, byte for byte.
    """
    lo, hi = _geometry_bbox(mats)
    pad = float(analysis.DomainPaddingWavelengths) * lam_c_mm
    dom_lo = [c - pad for c in lo]
    dom_hi = [c + pad for c in hi]
    grown, thin = [], []
    if mesh_res_mm is None or boundaries is None:
        return lo, hi, dom_lo, dom_hi, (grown, thin)
    floor = MIN_ABSORBER_CLEARANCE_WAVELENGTHS * lam_c_mm
    for i in range(3):
        for side, (bc, box, sign) in enumerate((
                (boundaries[2 * i], dom_lo, -1.0),
                (boundaries[2 * i + 1], dom_hi, +1.0))):
            # ⚠ ``depth`` is an UPPER BOUND, not a measurement: SmoothMeshLines
            # guarantees only that no cell EXCEEDS mesh_res, so the outer N+1
            # cells are at most (N+1)*mesh_res and are smaller wherever grading
            # has begun (measured on this horn: 96.2 % of the bound). Say
            # "needs up to", never "is" — quoting a bound as a measurement is
            # the same defect this guard exists to catch.
            depth = absorber_depth_mm(bc, mesh_res_mm)
            if depth <= 0.0:
                continue
            air = pad - depth
            face = "{0}{1}".format(AXES[i], "min" if sign < 0 else "max")
            if air > floor:
                continue
            if air > 0.0:
                # Thin, but the absorber is still outside the structure. Moving
                # the domain here would change results for models that run
                # correctly today, so this only tells the truth about itself.
                # ⚠ ADVISE ONLY FOR A REAL ABSORBER. MUR's two lines are where
                # openEMS places the NF2FF surface, not an absorbing depth —
                # a one-cell condition has no clearance to be short of. Warning
                # about it would put six lines of noise on the validated patch
                # template, whose padding is entirely adequate.
                if not bc.startswith("PML_"):
                    continue
                thin.append(
                    "{face}: {bc} plus its recording surface needs up to "
                    "{depth:.4g} mm of the {pad:.4g} mm padding, leaving about "
                    "{air:.4g} mm ({lam:.3g} lambda) of clear air. That works, "
                    "but a radiating model wants nearer {want:g} lambda — raise "
                    "DomainPaddingWavelengths if the pattern looks "
                    "boundary-limited.".format(
                        face=face, bc=bc, depth=depth, pad=pad, air=air,
                        lam=air / lam_c_mm,
                        want=MIN_ABSORBER_CLEARANCE_WAVELENGTHS))
                continue
            want = depth + floor
            box[i] = (lo[i] - want) if sign < 0 else (hi[i] + want)
            grown.append(
                "{face}: {bc} plus its recording surface needs up to "
                "{depth:.4g} mm, but the padding is only {pad:.4g} mm — the "
                "absorber would start inside the geometry. Domain pushed out "
                "to {want:.4g} mm on this face ({clear:g} lambda of clear "
                "air).".format(face=face, bc=bc, depth=depth, pad=pad,
                               want=want,
                               clear=MIN_ABSORBER_CLEARANCE_WAVELENGTHS))
    return lo, hi, dom_lo, dom_hi, (grown, thin)


def _dielectric_thin_axis_lines(prim):
    """(axis, min, max) of the thinnest axis of a dielectric box (substrate)."""
    dims = [prim["stop"][i] - prim["start"][i] for i in range(3)]
    axis = int(min(range(3), key=lambda i: dims[i] if dims[i] > 0 else float("inf")))
    return axis, prim["start"][axis], prim["stop"][axis]


def grid_estimate(analysis, solver=None):
    """The REFINED grid write_deck will build, counted without writing it.

    Returns ``{"lines": (nx, ny, nz), "mesh_res_mm": global cell,
    "min_cell_mm": finest refinement step kept (the global cell if none),
    "extent_mm": (ex, ey, ez), "refined": parts refined}``, or None (no
    band). Raises what write_deck raises for a model it cannot read (no
    usable geometry); the caller (estimate.openems_work) falls back then.

    WHY. The pre-solve "how long?" dialog keyed openEMS work on the
    bounding-box floor at the GLOBAL cell (preflight.grid_lower_bound),
    which ignores local refinement entirely — and since v1.14.0 refinement,
    not MeshResolution, is what sets a detailed model's grid: the forum
    J-pole at MeshResolution 20 builds 2.94 M cells (stage O4, measured)
    where that floor counts a fraction of it, and its 1.15 ps timestep is
    set by the 0.7-1.4 mm lines at its hardware, not by the 125 mm global
    cell. A run priced like a tenth of itself lands in a cheaper model's
    history bucket and borrows ITS timing.
    So this is write_deck's own sequence — the same cell rule, domain
    (absorber guard and microstrip hug included), refinement plan, index
    budget and RAM shedding — on the same classification with nothing
    tessellated, fused or written (geometry.classify_shapes(export=False)).
    ⚠ It mirrors write_deck's PROLOGUE rather than sharing it, so the two
    are held equal by a gate, not by construction: preflight_live_openems
    checks this count against the floor write_deck itself budgets, line for
    line, on a locally refined model. Change one, change both.
    ⚠ It is exactly the count write_deck budgets on — NOT always a floor of
    openEMS's grid. MEASURED on the forum J-pole (1.1.4, back plate as a
    dielectric): 156 x 92 x 268 = 3.85 M at MeshResolution 20 and
    170 x 105 x 294 at 40, against the deck's own 142 x 79 x 262 =
    2.94 M and 156 x 93 x 287 (0.27 s to count, nothing written). For a
    history key a third high is harmless (a bucket spans a doubling, and the
    same model always gets the same key); the bounding-box floor it replaces
    was 13 x 13 x 25 — 700 times low.
    """
    f1, f2, _n = Analysis.freq_range_hz(analysis)
    f0 = 0.5 * (f1 + f2)
    fc = 0.5 * (f2 - f1)
    if fc <= 0:
        return None
    # notes=[]: collected and DROPPED — the deck write that follows says
    # them; an estimate must not put a second copy in the Report view.
    mats = _collect_materials(analysis, None, notes=[], export=False)
    msl_mesh = (any(str(getattr(p, "PortType", "Lumped")) == "MSL"
                    for p in query.get_ports(analysis))
                and str(getattr(solver, "MicrostripMeshMode", "Auto"))
                == "Auto")
    lam_c_mm = C0 / f0 * 1000.0
    if msl_mesh:
        eps_max = max([m["epsR"] for m in mats if m["kind"] == "dielectric"]
                      or [1.0])
        n_lines = max(50, int(analysis.MeshResolution))
        mesh_res_mm = C0 / f2 / math.sqrt(eps_max) / 1e-3 / n_lines
    else:
        mesh_res_mm = C0 / (f0 + fc) / 1e-3 / max(6, int(
            analysis.MeshResolution))
    geo_lo, geo_hi, dom_lo, dom_hi, _pad = _domain(
        analysis, mats, lam_c_mm,
        mesh_res_mm=None if msl_mesh else mesh_res_mm,
        boundaries=None if msl_mesh else Analysis.boundary_list(analysis))
    if msl_mesh:
        sub_th = geo_hi[2] - geo_lo[2]
        dom_lo = list(geo_lo)
        dom_hi = list(geo_hi)
        dom_hi[2] = geo_hi[2] + max(12.0 * sub_th, 1.0)
    ratio = float(analysis.MeshSmoothRatio)
    plan = _refinement_plan(mats, mesh_res_mm)
    kept, _dropped, _all, floor = _budget_refinement(
        mats, plan, dom_lo, dom_hi, mesh_res_mm, ratio)
    ram, allow = preflight.physical_ram_bytes(), preflight.allow_large()
    shed = [e for e in kept
            if e["zones"] is not None and e["mat"]["kind"] == "dielectric"]
    if shed and preflight.refusal(floor, mesh_res_mm, ram, allow=allow,
                                  at_least=True):
        kept2 = [e for e in kept if not any(e is d for d in shed)]
        fl2 = _refined_floor(mats, kept2, dom_lo, dom_hi, mesh_res_mm, ratio)
        if not preflight.refusal(fl2, mesh_res_mm, ram, allow=allow,
                                 at_least=True):
            kept, floor = kept2, fl2
    return {"lines": tuple(floor), "mesh_res_mm": mesh_res_mm,
            "min_cell_mm": min([e["step"] for e in kept] + [mesh_res_mm]),
            "extent_mm": tuple(float(dom_hi[i]) - float(dom_lo[i])
                               for i in range(3)),
            "refined": len(kept)}


# --------------------------------------------------------------------------- writer
def write_deck(analysis, solver, workdir, excite_port=None):
    """Write case_openems.py + geometry files. Returns (deck_path, z0)."""
    f1, f2, npts = Analysis.freq_range_hz(analysis)
    f0 = 0.5 * (f1 + f2)
    fc = 0.5 * (f2 - f1)
    if fc <= 0:
        raise OpenEMSModelError("FrequencyStop must be greater than FrequencyStart")

    # ⚠ A BAND WHOLLY BELOW A WAVEGUIDE PORT'S CUT-OFF has no answer at all:
    # openEMS returns NaN at every sample (see _waveguide_band), so refuse it
    # NOW, naming the cut-off — before any tessellation, and long before a
    # run that could only end in "not a number". Ports are bounding boxes and
    # cheap to read; one that cannot be read is left to the real
    # _collect_ports call below, which raises in its usual place (this only
    # adds a refusal, it never reorders another).
    try:
        _early = _collect_ports(analysis, excite_port=excite_port)
    except Exception:                                      # noqa: BLE001
        _early = None
    _cut = _waveguide_band(_early, f1, f2, npts) if _early else None
    if _cut and _cut["drop"] >= _cut["npts"]:
        raise OpenEMSModelError(_cutoff_refusal(_cut, f1, f2))

    # ⚠⚠ COUNT THE GRID BEFORE WRITING A SINGLE STL. Until v1.14.0 nothing did:
    # a forum user's MeshResolution 2700 built 9,429,380,072 cells, which
    # openEMS cannot index, and the run died "-11" right after "Create FDTD
    # operator" with no number anywhere saying why. This is a FLOOR under the
    # real grid (bounding boxes + padding at the global cell — see
    # preflight.grid_lower_bound), so it refuses only what is CERTAINLY over a
    # limit, in a second, instead of after minutes of tessellation. The deck
    # repeats the check on the exact grid (preflight.deck_lines, pasted below).
    # ⚠ An estimate that cannot be read is skipped, never fatal: the deck's
    # own check still runs, so a model this cannot read loses nothing.
    try:
        _floor = preflight.grid_lower_bound(analysis, solver)
    except Exception:                                      # noqa: BLE001
        _floor = None
    if _floor is not None:
        _why = preflight.refusal(_floor["lines"], _floor["mesh_res_mm"],
                                 preflight.physical_ram_bytes(),
                                 allow=preflight.allow_large(), at_least=True)
        if _why:
            # ⚠ SAY WHAT WAS LEFT OUT FIRST. This refusal fires before
            # _collect_materials, whose pass is what normally reports a
            # reference that reaches no geometry — so without this the
            # WARNING that explains a dropped part never appeared at all
            # (v1.14.0 review). The floor read the parts through the same
            # reference_leaves call, so its issues are word for word what
            # that pass would have said; the Report view gets them all and
            # the refusal itself carries the warnings, because a dialog
            # showing only the refusal would hide them behind it.
            _pre = []
            for _lab, _lvl, _txt in _floor.get("issues") or ():
                geometry._emit(_pre, _lvl, "material '{0}': {1}".format(
                    _lab, _txt))
            _say(_pre)
            _warn = [_n[len("EMStudio: WARNING - "):] for _n in _pre
                     if _n.startswith("EMStudio: WARNING - ")]
            if _warn:
                _why += (" Not counted, because NOT in the model: "
                         + " ".join(_warn[:2])
                         + (" (and {0} more in the Report view)".format(
                             len(_warn) - 2) if len(_warn) > 2 else ""))
            raise OpenEMSModelError(_why)

    # Model notes: references that reach nothing, hidden parts left out of a
    # referenced group, a group that brings in parts nobody picked, two
    # materials tied on Priority over the same space. Said NOW on the
    # console (so a model refused a few lines below still shows them) and
    # printed again by the deck when it runs (so they reach the solver log).
    # Until v1.14.0 the first two were silent skips.
    # ⚠ Console ONCE per solve: FullSMatrix re-writes the deck for every
    # further port (excite_port set), and repeating every note N times in
    # the Report view would bury it; each of those decks still prints them.
    model_notes = []
    mats = _collect_materials(analysis, workdir, notes=model_notes)
    model_notes.extend(_overlap_notes(mats))
    if excite_port is None:
        _say(model_notes)
    # ⚠ An excited waveguide port's probe plane must clear its excitation
    # plane by whole mesh cells, so _collect_ports needs the cell size
    # BEFORE the mesh block below computes it. The microstrip branch can
    # only make the grid FINER, so this plain-air value is a safe lower
    # bound for the one port type that depends on it.
    cell_mm = C0 / (f0 + fc) / 1e-3 / max(6, int(analysis.MeshResolution))
    ports = _collect_ports(analysis, excite_port=excite_port,
                           cell_mm=cell_mm)
    z0 = [p["R"] for p in ports if p["excite"]][0]
    # A band that STARTS below a waveguide port's cut-off: the samples under
    # it are left out of the post-processing grid (the "f = f[N:]" line
    # below), and said — a result that silently began 3.5 GHz later than
    # asked would be the same class of defect as one that silently vanished.
    # (The whole-band case was refused above; repeated here only because
    # the early read of the ports may have failed and this one did not.)
    wg_cut = _waveguide_band(ports, f1, f2, npts)
    if wg_cut and wg_cut["drop"] >= wg_cut["npts"]:
        raise OpenEMSModelError(_cutoff_refusal(wg_cut, f1, f2))
    if wg_cut:
        _n = _cutoff_note(wg_cut)
        model_notes.append(_n)
        if excite_port is None:
            _say([_n])

    # Trace-aware meshing for microstrip (MSL) ports: resolve the grid in the
    # DIELECTRIC (lambda/50) rather than in air, and grade it across the narrow
    # strip, so the port can self-extract its characteristic impedance. Without
    # this the sub-mm trace gets <1 cell and S-params come out non-physical
    # (|S|>1). Gated so antenna analyses (lumped ports) stay byte-identical.
    has_msl = any(p["type"] == "MSL" for p in ports)
    msl_mesh = has_msl and str(getattr(solver, "MicrostripMeshMode", "Auto")) == "Auto"

    # Critical grid coordinates that MUST survive smoothing bit-exactly: every
    # primitive/port boundary plane. openEMS's SmoothMeshLines can return fixed
    # lines perturbed by ~1 ULP (observed: 1.524 -> 1.524000000000001, v0.37.0-rc1),
    # which silently drops zero-thickness metal from the simulation. The deck snaps
    # the smoothed grid back onto these values (see _snap in the generated deck).
    criticals = {0: set(), 1: set(), 2: set()}
    for m in mats:
        for p in m["prims"]:
            for i in range(3):
                criticals[i].add(p["start"][i])
                criticals[i].add(p["stop"][i])
            # A FUSED STL's parts keep their own planes: the joint between
            # a horn's flare and its feed section is a geometry plane even
            # once the two are one solid (for an unfused STL these are the
            # prim's own planes, already in the set).
            if p["kind"] == "stl":
                for src in p.get("sources") or ():
                    for i in range(3):
                        criticals[i].add(src["start"][i])
                        criticals[i].add(src["stop"][i])
    for p in ports:
        for i in range(3):
            criticals[i].add(p["start"][i])
            criticals[i].add(p["stop"][i])

    lam_c_mm = C0 / f0 * 1000.0
    if msl_mesh:
        # lambda/50 in the highest-permittivity dielectric (the substrate).
        eps_max = max([m["epsR"] for m in mats if m["kind"] == "dielectric"] or [1.0])
        n_lines = max(50, int(analysis.MeshResolution))
        mesh_res_mm = C0 / f2 / math.sqrt(eps_max) / 1e-3 / n_lines
    else:
        mesh_res_mm = C0 / (f0 + fc) / 1e-3 / max(6, int(analysis.MeshResolution))
    # What the refusal needs to price "resolve it with MeshResolution": the
    # cell rule above as (wavelength, floor) — cell = wavelength / max(floor,
    # MeshResolution) — and the domain FLOOR exactly as preflight.
    # grid_lower_bound counts it (geometry + padding; none on the microstrip
    # branch, which hugs the board), so the refusal and the deck's own check
    # can never disagree about what is affordable.
    _lo, _hi = _geometry_bbox(mats)
    _pad = 0.0 if msl_mesh else (
        float(analysis.DomainPaddingWavelengths) * lam_c_mm)
    refusal_cost = {
        "wavelength_mm": (C0 / f2 / math.sqrt(eps_max) / 1e-3) if msl_mesh
        else C0 / (f0 + fc) / 1e-3,
        "mr_floor": 50 if msl_mesh else 6,
        "extent_mm": [max(0.0, (_hi[i] - _lo[i]) + 2.0 * _pad)
                      for i in range(3)],
        "f_max_hz": f2,
        "ram_bytes": preflight.physical_ram_bytes(),
        "allow": preflight.allow_large(),
        # Port spans, for the bore test: a port INSIDE a tube makes it a
        # feed structure, which the fill advice must never tell to fill.
        "ports": [("port {0}".format(p["nr"]), p["start"], p["stop"])
                  for p in ports],
    }
    boundaries = Analysis.boundary_list(analysis)
    # ⚠ The absorber guard is skipped on the microstrip path DELIBERATELY: that
    # branch below throws the padded box away and hugs the geometry so the line
    # runs INTO the PML, which is what makes the termination matched. Giving it
    # air would strand the line end short of the absorber — the |S| > 1 failure
    # the branch's own comment describes.
    geo_lo, geo_hi, dom_lo, dom_hi, (pad_grown, pad_thin) = _domain(
        analysis, mats, lam_c_mm,
        mesh_res_mm=None if msl_mesh else mesh_res_mm,
        boundaries=None if msl_mesh else boundaries)
    if msl_mesh:
        # A microstrip is a GUIDED (not radiating) structure, so the antenna-
        # style 0.25-wavelength air padding is wrong on every face:
        #  * in the propagation/transverse plane it strands the line end in open
        #    air short of the PML, breaking the matched termination (|S|>1), and
        #  * below z=0 it detaches the strip from the PEC-Zmin ground plane.
        # Hug the geometry: the substrate/line run to the absorbing boundary
        # (PML on the line axis, MUR transverse), the domain bottom sits on the
        # ground (z-min), and only a thin air lid caps the top for the fringing
        # field. This also cuts the cell count ~10x vs the padded box.
        sub_th = geo_hi[2] - geo_lo[2]
        dom_lo = list(geo_lo)
        dom_hi = list(geo_hi)
        dom_hi[2] = geo_hi[2] + max(12.0 * sub_th, 1.0)

    # LOCAL REFINEMENT PLAN, then the budget, then the refusal — in that
    # order, because whether a thin part is "unresolvable" now depends on
    # whether the whole refined grid fits (see _budget_refinement).
    smooth_ratio = float(analysis.MeshSmoothRatio)
    plan = _refinement_plan(mats, mesh_res_mm)
    kept, dropped, floor_all, floor_kept = _budget_refinement(
        mats, plan, dom_lo, dom_hi, mesh_res_mm, smooth_ratio)
    drop_text = ""
    if dropped:
        drop_text = (
            "Local refinement could not resolve every thin part: resolving "
            "them all needs a grid of at least {0} x {1} x {2} = {3:,} "
            "cells, more than openEMS can index ({4:,}), so the finest were "
            "left at the global cell: {5}.".format(
                floor_all[0], floor_all[1], floor_all[2],
                floor_all[0] * floor_all[1] * floor_all[2],
                preflight.OPENEMS_MAX_CELLS, _finest_text(dropped)))
    # ...and the RAM half of the budget. Never degrade METAL per machine (an
    # 8 GB Mac and a 192 GB box would build different models of one
    # document): refuse, with the preflight's numbers and the parts that set
    # them. ⚠ EXCEPT a dielectric part refined axis by axis: v1.13 never
    # refined such a part (too large to blanket) and RAN the model, so on a
    # machine too small for its new lines it gets exactly v1.13's model back
    # — said in a NOTE — instead of a refusal of a document that used to run.
    _ram = preflight.physical_ram_bytes()
    _allow = preflight.allow_large()
    _why = preflight.refusal(floor_kept, mesh_res_mm, _ram, allow=_allow,
                             at_least=True)
    shed = [e for e in kept
            if e["zones"] is not None and e["mat"]["kind"] == "dielectric"]
    if _why and shed:
        _kept2 = [e for e in kept if not any(e is d for d in shed)]
        _fl2 = _refined_floor(mats, _kept2, dom_lo, dom_hi, mesh_res_mm,
                              smooth_ratio)
        if not preflight.refusal(_fl2, mesh_res_mm, _ram, allow=_allow,
                                 at_least=True):
            _n = ("EMStudio: NOTE - local refinement of the dielectric "
                  "part(s) {0} was left out: it needs a grid of at least "
                  "{1} x {2} x {3} cells, more than this machine's RAM can "
                  "hold, and without it the model is meshed as before "
                  "v1.14.0. Set {4}=1 before starting FreeCAD to keep it."
                  .format(_finest_text(shed, n=4), floor_kept[0],
                          floor_kept[1], floor_kept[2],
                          preflight.OPENEMS_ALLOW_LARGE_ENV))
            model_notes.append(_n)
            _say([_n])
            kept, floor_kept, _why = _kept2, _fl2, None
    if _why and kept:
        raise OpenEMSModelError(
            _why + " Local refinement of the thin parts sets this grid — the "
            "finest are " + _finest_text(kept) + " — so a lower "
            "MeshResolution will not shrink it much: thicken or simplify "
            "those parts, model a thin-walled tube whose bore carries no "
            "field as a solid rod, leave them out, or use NEC2 for wire-like "
            "conductors.")
    refined = {id(e["src"]): e["step"] for e in kept}
    try:
        _refuse_unresolvable(mats, mesh_res_mm, cost=refusal_cost,
                             refined=refined)
    except OpenEMSModelError as exc:
        if drop_text:
            raise OpenEMSModelError(drop_text + " " + str(exc))
        raise
    if dropped:
        # Every dropped part the refusal let through IS present in the
        # global grid (at least one cell across), just coarsely: say so —
        # a part resolved worse than the user's other parts must not look
        # like the same model.
        _n = ("EMStudio: NOTE - " + drop_text + " The grid still holds each "
              "of them (at least one cell across), but coarsely; thicken or "
              "simplify them for a finer model.")
        model_notes.append(_n)
        _say([_n])
    # A lumped port with an end in AIR (see _port_contact_warnings). Here,
    # after the refusals, so a refused model's message is unchanged, and
    # with the refinement plan known, which sets the local cell. FIRST in
    # the deck's notes: it is the one note that says the whole result is
    # meaningless, and the results dialog shows only the first few.
    _air = _port_contact_warnings(ports, mats, mesh_res_mm, kept)
    if _air:
        model_notes[:0] = _air
        if excite_port is None:
            _say(_air)
    end_criteria = 10.0 ** (float(solver.EndCriteriaDB) / 10.0)
    nr_ts = max(1000, int(solver.MaxTimesteps))

    L = []
    w = L.append
    w("# Auto-generated by EMStudio — openEMS FDTD deck")
    w("# Analysis: {0}".format(analysis.Label))
    w("import os, sys")
    # Windows DLL wiring, and it must come BEFORE the CSXCAD import: the
    # upstream wheels do NOT bundle their DLLs (measured 2026-08-24 on
    # v0.37.0-rc1: a fresh venv import dies "DLL load failed while importing
    # CSXCAD"), and Python >= 3.8 no longer consults PATH for the dependent
    # DLLs of extension modules — os.add_dll_directory is the only sanctioned
    # route. The venv-beside-binary convention (the same one
    # find_openems_python probes) puts the DLLs three levels above the
    # interpreter (<root>\venv\Scripts\python.exe -> <root>); the env var
    # covers hand layouts that break the convention. Probing for CSXCAD.dll
    # rather than trusting the shape keeps a POSIX-style venv, or a moved
    # tree, from registering a junk directory.
    w("if sys.platform == 'win32':")
    w("    for _d in (os.environ.get('EMSTUDIO_OPENEMS_DLL_DIR', ''),")
    w("               os.path.dirname(os.path.dirname(os.path.dirname(")
    w("                   os.path.abspath(sys.executable))))):")
    w("        if _d and os.path.isfile(os.path.join(_d, 'CSXCAD.dll')):")
    w("            os.add_dll_directory(_d)")
    w("import numpy as np")
    w("from CSXCAD import ContinuousStructure")
    w("from openEMS import openEMS")
    w("")
    w("sim_path = os.path.dirname(os.path.abspath(__file__))")
    w("preview_only = '--preview' in sys.argv")
    w("")
    if model_notes:
        # Only when there is something to say, so every model without a
        # note keeps a byte-identical deck. flush=True for the same reason as
        # the starting banner below: stdout is a pipe, and these lines must
        # reach the runner's log before openEMS starts writing to the fd.
        w(MODEL_NOTES_MARK + " (also shown in FreeCAD's Report view when "
          "this deck was written)")
        for _n in model_notes:
            w("print({0!r}, flush=True)".format(_ascii(_n)))
        w("")
    w("FDTD = openEMS(NrTS={0}, EndCriteria={1:.6g})".format(nr_ts, end_criteria))
    w("FDTD.SetGaussExcite({0:.9g}, {1:.9g})".format(f0, fc))
    w("FDTD.SetBoundaryCond({0!r})".format(list(boundaries)))
    w("")
    w("CSX = ContinuousStructure()")
    w("FDTD.SetCSX(CSX)")
    w("mesh = CSX.GetGrid()")
    w("mesh.SetDeltaUnit(1e-3)  # drawing unit: mm")
    w("mesh_res = {0:.9g}".format(mesh_res_mm))
    w("")
    for _n in pad_grown + pad_thin:
        # A domain that grew for a reason the user cannot see is the same class
        # of defect as a field that changes nothing: say it in the deck, and say
        # it again on stdout so it reaches the solver log the runner captures.
        w("# EMStudio absorber guard — " + _n)
    if pad_grown:
        w("print({0!r})".format(
            "EMStudio: domain ENLARGED so the absorbing boundary clears the "
            "geometry — " + " ".join(pad_grown)))
    for _n in pad_thin:
        # Advisory only: nothing moved, so it must not claim anything did.
        w("print({0!r})".format("EMStudio: absorber clearance is thin — " + _n))
    if pad_grown or pad_thin:
        w("")
    w("# simulation domain")
    w("mesh.AddLine('x', [{0:.9g}, {1:.9g}])".format(dom_lo[0], dom_hi[0]))
    w("mesh.AddLine('y', [{0:.9g}, {1:.9g}])".format(dom_lo[1], dom_hi[1]))
    w("mesh.AddLine('z', [{0:.9g}, {1:.9g}])".format(dom_lo[2], dom_hi[2]))
    w("")

    by_src = {id(e["src"]): e for e in kept}
    for m in mats:
        w("# --- material: {0} ({1}) ---".format(m["name"], m["kind"]))
        if m["kind"] == "metal":
            w("{0} = CSX.AddMetal('{0}')".format(m["name"]))
        elif m["kind"] == "conducting_sheet":
            # ⛳ CSPropConductingSheet is documented "Only 2D primitives
            # (sheets) should be added to this property". A solid handed to it
            # is not a supported model, so we say so and fall back to PEC
            # LOUDLY rather than emit something openEMS will interpret in a way
            # nobody predicted. Silence here would recreate the exact defect
            # this branch exists to fix.
            solid = any(p["kind"] != "box" or p["sheet_axis"] is None
                        for p in m["prims"])
            if solid:
                w("print('EMStudio: WARNING - material {0} is a SOLID; the "
                  "finite-conductivity sheet model needs a 2-D sheet, so it "
                  "is modelled as PEC (lossless). Gain/Q will be optimistic.')"
                  .format(m["name"]))
                w("{0} = CSX.AddMetal('{0}')".format(m["name"]))
            else:
                w("{0} = CSX.AddConductingSheet('{0}', conductivity={1:.9g}, "
                  "thickness={2:.9g})".format(m["name"], m["sigma"],
                                              m["thickness_m"]))
        else:
            kappa = m["kappa"]
            if kappa <= 0 and m["tanD"] > 0:
                kappa = m["tanD"] * 2 * math.pi * f0 * EPS0 * m["epsR"]
            extra = ""
            if kappa > 0:
                extra += ", kappa={0:.9g}".format(kappa)
            if m["mu"] not in (0.0, 1.0):
                extra += ", mue={0:.9g}".format(m["mu"])
            w("{0} = CSX.AddMaterial('{0}', epsilon={1:.9g}{2})".format(m["name"], m["epsR"], extra))
        sheet_dirs = set()
        has_solid = False
        for p in m["prims"]:
            if p["kind"] == "box":
                w(
                    "{0}.AddBox(priority={1}, start={2}, stop={3})".format(
                        m["name"], m["priority"], _fmt_v(p["start"]), _fmt_v(p["stop"])
                    )
                )
                if p["sheet_axis"] is None:
                    has_solid = True
                else:
                    sheet_dirs.add("".join(a for i, a in enumerate(AXES) if i != p["sheet_axis"]))
            else:  # stl
                w(
                    "{0}.AddPolyhedronReader(r'{1}', priority={2}).ReadFile()".format(
                        m["name"], os.path.basename(p["path"]), m["priority"]
                    )
                )
                # Anchor each PART's bbox in the grid on all axes (for an
                # STL of one part, exactly the six lines it always had; a
                # fused STL keeps every part's planes).
                for src in (p.get("sources") or [p]):
                    for i, a in enumerate(AXES):
                        w(
                            "mesh.AddLine('{0}', [{1:.9g}, {2:.9g}])".format(
                                a, src["start"][i], src["stop"][i]
                            )
                        )
                    # LOCAL REFINEMENT. Until v0.84.0 an STL body got these
                    # six bounding-box lines and nothing else, so the only
                    # thing sizing the cells inside it was the global
                    # mesh_res — a body thinner than one cell was represented
                    # by no cells at all, silently. A part whose bounding box
                    # is cheap to BLANKET gets a grid across it fine enough
                    # to resolve its smallest feature, here, exactly as
                    # before; a part too large for that is refined axis by
                    # axis in the local-refinement block further down.
                    ent = by_src.get(id(src))
                    if (ent is not None and ent["blanket"] is not None
                            and max(ent["blanket"]) > 2):
                        counts = ent["blanket"]
                        w("# resolve this body's own {0:.4g} mm feature "
                          "({1} x {2} x {3} lines at {4:.4g} mm)".format(
                              src.get("min_feature") or 0.0, counts[0],
                              counts[1], counts[2], ent["step"]))
                        for i, a in enumerate(AXES):
                            if counts[i] <= 2:
                                continue
                            w("mesh.AddLine('{0}', np.linspace({1:.9g}, "
                              "{2:.9g}, {3:d}).tolist())".format(
                                  a, src["start"][i], src["stop"][i],
                                  counts[i]))
                has_solid = True    # an STL body is a solid: it wants the
                                    # metal-edge thirds rule like any other
        # ⚠⚠ A CONDUCTING SHEET IS METAL AND GETS THE METAL-EDGE THIRDS RULE.
        # ``conducting_sheet`` is the SAME geometry as ``metal`` with a surface
        # impedance on it — the only difference is the CSX property. Gating the
        # refinement on kind == "metal" meant that ticking Category=Conductor to
        # account for copper loss ALSO coarsened the grid at every metal edge,
        # which is the refinement this writer's own docstring and
        # _refuse_unresolvable both call necessary. MEASURED on the shipped
        # 2.4 GHz patch template, changing only the metal's Category:
        #     Metal (PEC) -> 37 x 39 x 31 grid lines (41 040 cells)
        #     Conductor   -> 29 x 29 x 31 grid lines (23 520 cells), no
        #                    AddEdges2Grid line anywhere in the deck
        # The resulting shift in resonance and bandwidth would be read as
        # conductor loss when most of it is mesh.
        # ⛳ AddEdges2Grid is property-type agnostic — it calls
        # ``properties.GetAllPrimitives()`` and takes the hint from each BOX
        # (openEMS.pyx / automesh.py), so a CSPropConductingSheet works exactly
        # like a CSPropMetal here. It also covers the solid fall-back a few lines
        # above, which emits AddMetal and is therefore literally PEC.
        # ⚠ Nothing is lost by leaving the dielectric branch below: a conducting
        # sheet is not a substrate, and on the zero-thickness sheet that branch
        # above insists on, its guard `0 < (a2 - a1)` is false, so it emitted
        # nothing. That is precisely why the coarsening was invisible.
        if m["kind"] in ("metal", "conducting_sheet"):
            if has_solid:
                w("FDTD.AddEdges2Grid(dirs='all', properties={0}, metal_edge_res=mesh_res/2)".format(m["name"]))
            for dirs in sorted(sheet_dirs):
                w("FDTD.AddEdges2Grid(dirs='{0}', properties={1}, metal_edge_res=mesh_res/2)".format(dirs, m["name"]))
        else:
            # discretize thin dielectrics (substrates) across their thickness —
            # bbox-based, so it applies to STL-imported substrates as well.
            # ⚠ Per PART (v1.14.0): a FUSED STL's box is the union of its
            # parts', so a shank and the ring on it would get lines across
            # the pair's 5.5 mm instead of each its own thickness — and those
            # landed 0.125 mm from the shank's own face (measured: a sliver).
            # A prim of one part is its own source, so its lines are as
            # before, byte for byte.
            for p in [q for pr in m["prims"]
                      for q in ((pr.get("sources") or [pr])
                                if pr["kind"] == "stl" else [pr])]:
                axis, a1, a2 = _dielectric_thin_axis_lines(p)
                if 0 < (a2 - a1) < mesh_res_mm * 2:
                    w(
                        "mesh.AddLine('{0}', np.linspace({1:.9g}, {2:.9g}, 5).tolist())".format(
                            AXES[axis], a1, a2
                        )
                    )
        w("")

    # ⚠⚠ A LUMPED PORT'S TWO ENDS MUST BE GRID LINES ON ITS EXCITATION AXIS.
    # openEMS does not place a lumped element where it is drawn: it SNAPS each
    # end to the NEAREST grid line (Operator::SnapBox2Mesh), and until v1.14.0
    # nothing put a line there. ``edges2grid`` covers only the two OTHER axes,
    # the metal's thirds rule puts lines a third of a cell INSIDE and two
    # thirds OUTSIDE each metal face — never ON it — and the _snap block below
    # only corrects lines that already lie within 1e-6 mm. So where an end
    # landed depended on MeshResolution. MEASURED (2026-10-17, EMStudio's own
    # runner, a box-bar J-pole fed across a 38.7 mm gap): at MR 100 the feed
    # end snapped 4.16 mm into AIR (VSWR 22.3 at 85 MHz against 2.5 at MR
    # 20-60), at MR 150 2.78 mm, no warning either time; on the forum J-pole
    # both ends snapped to the SAME line and openEMS printed "Lumped Element
    # snapping failed! Dimension is: 0 skipping" — the port was dropped and
    # the run still "finished OK" with an all-NaN port_1.csv.
    # ⛳ The deck adds each end as a line BEFORE any SmoothMeshLines (which
    # keeps every existing line fixed and only grades around it), so the
    # port's metal-to-metal span is exact at every MeshResolution.
    # ⚠ Only on the excitation axis, only for lumped ports (an MSL or
    # waveguide port is built from its own box and probes, and moving its
    # grid would move every gated microstrip / horn number), and only for an
    # end INSIDE the domain: a line beyond the outermost one would silently
    # GROW the simulation box. A port outside the box is not placed at all —
    # openEMS then reports its primitives unused, and the runner fails the
    # run on that (runner._DeckWatch).
    lumped = [p for p in ports if p["type"] not in ("MSL", "RectWaveguide")]
    if lumped:
        w("# --- lumped ports: both ends ON the grid (excitation axis) ---")
        w("# openEMS snaps a lumped element's ends to the NEAREST lines; without")
        w("# these a port end can land in air beside the metal it was drawn on.")
        w("def _port_end(ax, v, fixed, res):")
        # ⚠ An end that already sits on a line (within the 1e-6 mm _snap
        # treats as the same plane: a sheet, an STL face, a substrate face)
        # is left alone — that is every shipped template, whose grids stay
        # byte-identical.
        w("    lines = sorted(set(float(x) for x in mesh.GetLines(ax)))")
        w("    if not (lines[0] < v < lines[-1]):")
        w("        return  # outside the domain: never grow the box for a port")
        w("    k = min(range(len(lines)), key=lambda n: abs(lines[n] - v))")
        w("    d = abs(lines[k] - v)")
        w("    if d <= 1e-6:")
        w("        return  # already a line (same plane within float noise)")
        # ⚠⚠ A HAIR-THIN CELL IS A TIME BOMB. FDTD's timestep is set by the
        # smallest cell (Courant), so an end 0.01 mm from a line would force a
        # 0.01 mm cell and multiply the run's timesteps by hundreds — openEMS
        # then hits MaxTimesteps and the result is truncated. When the
        # nearest line is only a RESOLUTION HELPER (a thirds-rule or local-
        # refinement line, not a geometry plane: not in ``fixed``, not a
        # domain wall) and lies within a tenth of the local spacing, that
        # line is MOVED onto the end instead. Moving the nearest line never
        # makes a cell smaller than half the one it sat in, and a helper
        # line nudged by a tenth of a cell changes nothing it was there for.
        # A geometry plane is never moved — that is how zero-thickness metal
        # falls out of the grid (the reason for _snap below) — so near one,
        # the end is added and the cell is the model's own feature.
        w("    below = [x for x in lines if x < v]")
        w("    above = [x for x in lines if x > v]")
        w("    local = min(min(above) - max(below), res)")
        w("    helper = (0 < k < len(lines) - 1")
        w("              and all(abs(lines[k] - c) > 1e-6 for c in fixed))")
        w("    if helper and d < 0.1 * local:")
        w("        lines[k] = v")
        w("    else:")
        w("        lines.append(v)")
        w("    mesh.SetLines(ax, sorted(set(lines)))")
        w("")
        for p in lumped:
            ai = AXES.index(p["axis"])
            fixed = "[" + ", ".join("{0:.9g}".format(v)
                                    for v in sorted(criticals[ai])) + "]"
            for v in sorted({p["start"][ai], p["stop"][ai]}):
                w("_port_end('{0}', {1:.9g}, {2}, mesh_res)  # port {3}".format(
                    p["axis"], v, fixed, p["nr"]))
        w("")

    if msl_mesh:
        # Build the trace-aware grid BEFORE AddMSLPort: the strip width gets a
        # thirds-rule refinement, the propagation axis and substrate thickness
        # are graded to mesh_res. AddMSLPort requires >=5 lines already present
        # along the line, and the port's Zc extraction needs the strip resolved.
        w("# --- trace-aware grid for microstrip (MSL) ports ---")
        for p in ports:
            if p["type"] != "MSL":
                continue
            prop_axis = p["prop_axis"]
            exc_i = AXES.index(p["axis"])
            prop_i = AXES.index(prop_axis)
            width_i = ({0, 1, 2} - {prop_i, exc_i}).pop()
            width_axis = AXES[width_i]
            w_lo = min(p["start"][width_i], p["stop"][width_i])
            w_hi = max(p["start"][width_i], p["stop"][width_i])
            w("third = mesh_res / 3.0")
            w("mesh.AddLine('{0}', [{1:.9g}+2*third/4, {1:.9g}-third/4, "
              "{2:.9g}+2*third/4, {2:.9g}-third/4])".format(width_axis, w_lo, w_hi))
            w("mesh.SmoothMeshLines('{0}', mesh_res/4)".format(width_axis))
            w("mesh.SmoothMeshLines('{0}', mesh_res)".format(prop_axis))
        w("mesh.SmoothMeshLines('z', mesh_res)")
        w("")

    w("# --- ports ---")
    w("ports = {}")
    needs_port_pec = any(p["type"] == "MSL" for p in ports)
    if needs_port_pec:
        w("port_pec = CSX.AddMetal('port_pec')")
    for p in ports:
        if p["type"] == "MSL":
            # feed/measure offsets along the line. CRITICAL: the feed must sit well
            # BEFORE the measurement plane, else the incident-wave estimate is taken
            # downstream of the source and S-params come out non-physical (>0 dB).
            # With EMStudio's coarser antenna-scale mesh, 10*mesh_res (tutorial value
            # for its fine mesh) can exceed MeasPlaneShift — so cap the feed shift.
            i = AXES.index(p["prop_axis"])
            span = abs(p["stop"][i] - p["start"][i])
            meas = span / 3.0
            w(
                "ports[{nr}] = FDTD.AddMSLPort({nr}, port_pec, {start}, {stop}, "
                "'{pax}', '{eax}', excite={excite:.1f}, "
                "FeedShift=min(10*mesh_res, {feed:.9g}), MeasPlaneShift={mps:.9g}, "
                "priority=10)".format(
                    nr=p["nr"], start=_fmt_v(p["start"]), stop=_fmt_v(p["stop"]),
                    pax=p["prop_axis"], eax=p["axis"], excite=p["excite"],
                    feed=meas / 2.0, mps=meas,
                )
            )
        elif p["type"] == "RectWaveguide":
            # AddRectWaveGuidePort builds the analytic TE_mn profile (Pozar) and
            # imposes it on the port plane. Unlike a lumped port it is a real
            # modal excitation, which is what a horn or a filter fed from guide
            # actually needs — and what EMStudio had no way to express until
            # v1.5.0, leaving antenna/horn.py's design_pyramidal a designer with
            # no solver that could feed it.
            w(
                "ports[{nr}] = FDTD.AddRectWaveGuidePort({nr}, {start}, {stop}, "
                "'{pax}', {a:.9g}, {b:.9g}, '{mode}', excite={excite:.1f})".format(
                    nr=p["nr"], start=_fmt_v(p["start"]), stop=_fmt_v(p["stop"]),
                    pax=p["prop_axis"], a=p["wg_a_m"], b=p["wg_b_m"],
                    mode=p["wg_mode"], excite=p["excite"],
                )
            )
        else:
            w(
                "ports[{nr}] = FDTD.AddLumpedPort({nr}, {R:.9g}, {start}, {stop}, "
                "'{axis}', excite={excite:.1f}, priority=5, edges2grid='{e2g}')".format(
                    nr=p["nr"], R=p["R"], start=_fmt_v(p["start"]), stop=_fmt_v(p["stop"]),
                    axis=p["axis"], excite=p["excite"], e2g=p["edges2grid"],
                )
            )
    w("")
    compute_ff = bool(getattr(solver, "ComputeFarField", False))
    # MSL ports need the mesh resolved across the narrow strip width (thirds rule)
    # and along the line — the antenna auto-gridder doesn't know the strip exists
    # (it is created by AddMSLPort, not drawn as metal).
    for p in ports:
        if p["type"] != "MSL":
            continue
        prop_i = AXES.index(p["prop_axis"])
        exc_i = AXES.index(p["axis"])
        width_i = ({0, 1, 2} - {prop_i, exc_i}).pop()
        width_axis = AXES[width_i]
        w_lo = min(p["start"][width_i], p["stop"][width_i])
        w_hi = max(p["start"][width_i], p["stop"][width_i])
        w("# MSL port {0}: thirds-rule mesh across the {1}-width strip".format(p["nr"], width_axis))
        w("third = mesh_res / 3.0")
        w("mesh.AddLine('{0}', [{1:.9g}+2*third/4, {1:.9g}-third/4, {2:.9g}+2*third/4, {2:.9g}-third/4])".format(
            width_axis, w_lo, w_hi))
        w("mesh.SmoothMeshLines('{0}', mesh_res/4)".format(width_axis))
    w("")
    zoned = [e for e in kept if e["zones"] is not None]
    if zoned:
        # ⚠⚠ LOCAL REFINEMENT, AXIS BY AXIS — LAST, after every other line
        # (materials, port ends, the ports' own edges2grid lines, MSL
        # strips): the helper only ever SUBDIVIDES the gaps between lines
        # that already exist, so it cannot land a line a hair from one of
        # them, and a hair-thin cell would set the timestep for the whole
        # run. Before SmoothMeshLines (which then finds no gap wider than
        # the cell near a part, and grades the rest as always) and before
        # the _snap block and the pasted preflight, which must count the
        # FINAL grid. Only decks with such a part carry this block, so every
        # other deck is byte-identical.
        w("# --- local refinement, axis by axis: where each thin part's section changes ---")
        for _ln in _REFINE_SRC.strip("\n").splitlines():
            w(_ln)
        w("")
        w("def _refine(ax, zones):")
        w("    _new = _refine_lines(mesh.GetLines(ax), zones, mesh_res, {0:.9g})"
          .format(smooth_ratio))
        w("    if _new:")
        w("        mesh.AddLine(ax, _new)")
        w("")
        per_axis = {0: [], 1: [], 2: []}
        for e in zoned:
            what = []
            for i, a in enumerate(AXES):
                zs = e["zones"][i]
                per_axis[i].extend(zs)
                lo, hi = e["src"]["start"][i], e["src"]["stop"][i]
                if not zs:
                    continue
                if len(zs) == 1 and abs(zs[0][0] - lo) < 1e-9 \
                        and abs(zs[0][1] - hi) < 1e-9:
                    what.append("{0} across {1:.6g}..{2:.6g}".format(a, lo, hi))
                else:
                    what.append("{0} at {1} place(s)".format(a, len(zs)))
            w("# {0}: {1:.4g} mm feature, {2:.4g} mm lines — {3}".format(
                _ascii(_plan_label(e)), e["src"].get("min_feature") or 0.0,
                e["step"], "; ".join(what) or "nothing"))
        for i, a in enumerate(AXES):
            if not per_axis[i]:
                continue
            w("_refine('{0}', [{1}])".format(a, ", ".join(
                "({0:.9g}, {1:.9g}, {2:.9g})".format(*z)
                for z in sorted(per_axis[i]))))
        w("")
    w("mesh.SmoothMeshLines('all', mesh_res, {0:.4g})".format(float(analysis.MeshSmoothRatio)))
    w("")
    w("# Snap smoothed lines back onto critical geometry planes (SmoothMeshLines can")
    w("# perturb fixed lines by ~1 ULP, silently dropping zero-thickness metal).")
    w("def _snap(vals, criticals, tol=1e-6):")
    w("    vals = list(vals)")
    w("    for i, v in enumerate(vals):")
    w("        for c in criticals:")
    w("            if abs(v - c) <= tol:")
    w("                vals[i] = c")
    w("                break")
    w("    return sorted(set(vals))")
    w("")
    for i, ax in enumerate(AXES):
        vals = sorted(criticals[i])
        w("mesh.SetLines('{0}', _snap(mesh.GetLines('{0}'), {1}))".format(
            ax, "[" + ", ".join("{0:.9g}".format(v) for v in vals) + "]"))
    w("")
    # THE GRID IS FINAL HERE — smoothed and snapped — so this is the first
    # point at which its exact size is known, and the last before openEMS is
    # asked to build an operator for it. The preflight is PASTED (not
    # imported: the deck runs under the openEMS venv, which has no EMStudio)
    # so every route into openEMS is covered: the GUI, FullSMatrix's extra
    # excitations, and a user re-running the deck by hand. It prints the
    # cell count and RAM need on every run, and refuses a grid openEMS cannot
    # index (no override) or this machine cannot hold (EMSTUDIO_OPENEMS_ALLOW_
    # LARGE=1 lifts that one only) — with the numbers, never a bare signal.
    # ⚠ Before the NF2FF box: its line lookups are cheap, but nothing after
    # this point should run on a grid that is about to be refused.
    for _ln in preflight.deck_lines():
        w(_ln)
    w("")
    if compute_ff:
        wg_exc = next((p for p in ports
                       if p["excite"] and p["type"] == "RectWaveguide"), None)
        if wg_exc is None:
            # Every other analysis keeps openEMS's own automatic box, byte for
            # byte. The deviation below is confined to waveguide-fed models on
            # purpose: it is the only port type that launches a wave BACKWARDS
            # out of the structure.
            w("nf2ff_box = FDTD.CreateNF2FFBox()")
        else:
            # ⚠⚠ THE NF2FF BOX MUST NOT ENCLOSE A WAVEGUIDE PORT'S BACKWARD
            # WAVE. openEMS's waveguide port is a SOFT source on a plane
            # (CSX.AddExcitation with a zero-thickness box, openEMS/ports.py),
            # so it launches the mode in BOTH directions. The forward half feeds
            # the antenna; the backward half runs out of the guide's open end and
            # is absorbed by the boundary — but ``CreateNF2FFBox`` wraps all six
            # faces, so that half crosses the recording surface and is counted as
            # RADIATED POWER. Directivity is 4*pi*U_max/P_rad, so inflating P_rad
            # deflates the reported directivity.
            # ⛳ MEASURED on the shipped Ka-band horn, one run and two recording
            # boxes over identical fields:
            #     all six faces   D = 16.113 dBi, 40.7 % of P_rad going BACKWARDS
            #     -z face off     D = 18.252 dBi,  4.1 %
            # 2.14 dB, and it is most of the "~3 dB low" the horn gate was red
            # for. ⚠ It is NOT aperture illumination: the same run's aperture
            # dump matches the analytic cosine to 2.35 % RMS.
            # ⛳ This is upstream's own convention — Horn_Antenna.m passes
            # ``'Directions',[1 1 1 1 0 1]`` for exactly this reason. The python
            # Horn_Antenna.py can keep all six only because its guide is closed
            # by a back-short and has no backward wave to lose.
            # ⚠ CreateNF2FFBox passes ``directions=`` itself, so it cannot be
            # overridden through **kw — the box has to be built by hand, which
            # means replicating its start/stop rule (below) exactly.
            bc_size, dirs, mirror = _nf2ff_bc(boundaries)
            pi = AXES.index(wg_exc["prop_axis"])
            back_is_min = wg_exc["prop_sign"] >= 0
            dirs[2 * pi + (0 if back_is_min else 1)] = 0
            # ...and pull that face up to the excitation plane, so the whole
            # backward region is outside the box rather than merely unrecorded
            # on one face. Measured: back-hemisphere power 4.1 % -> 2.2 %.
            plane = wg_exc["start"][pi]
            w("from openEMS.nf2ff import nf2ff as _NF2FF")
            w("# NF2FF surface: openEMS places it PML_N+1 lines in (MUR: 2, "
              "PEC/PMC: 0 with mirroring) — CreateNF2FFBox's own rule.")
            w("_bc_size = {0!r}".format(bc_size))
            w("_lines = [list(mesh.GetLines(_a)) for _a in 'xyz']")
            w("_nf_start = [_lines[_n][_bc_size[2*_n]] for _n in range(3)]")
            w("_nf_stop = [_lines[_n][-_bc_size[2*_n+1]-1] for _n in range(3)]")
            w("# the face behind the excited waveguide port, clamped to its "
              "excitation plane and switched off")
            if back_is_min:
                w("_nf_start[{0}] = max(_nf_start[{0}], {1:.9g})".format(pi, plane))
            else:
                w("_nf_stop[{0}] = min(_nf_stop[{0}], {1:.9g})".format(pi, plane))
            w("if _nf_start[{0}] >= _nf_stop[{0}]:".format(pi))
            w("    raise SystemExit('EMStudio: the NF2FF box collapsed along "
              "{0} — the waveguide port plane is outside the recording "
              "region'.format('{0}'))".format(AXES[pi]))
            w("nf2ff_box = _NF2FF(CSX, 'nf2ff', _nf_start, _nf_stop, "
              "directions={0!r}, mirror={1!r})".format(dirs, mirror))
            w("print('EMStudio: NF2FF box %r -> %r, face %d off (waveguide "
              "port backward wave)' % (_nf_start, _nf_stop, {0}))".format(
                  2 * pi + (0 if back_is_min else 1)))
        w("")
    nf_plane = str(getattr(solver, "NearFieldPlane", "None"))
    if nf_plane in ("XY", "XZ", "YZ"):
        # FD |E| dump on a cut plane through the geometry-bbox center, recorded at
        # the sweep center frequency (FD dumps need the frequency before Run).
        # ⚠ The real geometry bbox, not dom -/+ padding. That reconstruction
        # was only ever correct when the padding was uniform; the guard above
        # can now enlarge one face and not its opposite, and the microstrip
        # branch discards the padding altogether.
        center = [(geo_lo[i] + geo_hi[i]) / 2.0 for i in range(3)]
        flat_axis = {"XY": 2, "XZ": 1, "YZ": 0}[nf_plane]
        d_start = list(dom_lo)
        d_stop = list(dom_hi)
        d_start[flat_axis] = d_stop[flat_axis] = center[flat_axis]
        w("# near-field FD |E| dump ({0} plane at geometry center, f0)".format(nf_plane))
        w("nf_dump = CSX.AddDump('Ef_fd', dump_type=10, file_type=1, frequency=[{0:.9g}])".format(f0))
        w("nf_dump.AddBox({0}, {1})".format(_fmt_v(d_start), _fmt_v(d_stop)))
        w("")
    w("if preview_only:")
    w("    CSX.Write2XML(os.path.join(sim_path, 'case.xml'))")
    w("    print('CSX geometry written to case.xml (open with AppCSXCAD)')")
    w("    sys.exit(0)")
    w("")
    # flush=True is load-bearing: the runner's determinate progress bar learns
    # its TOTAL from this line (total_pattern "NrTS="), but the deck's stdout
    # is a PIPE, so python block-buffers it while openEMS's C++ engine writes
    # its Timestep lines straight through the same fd. Without the flush the
    # total arrives only when the buffer happens to drain — measured on the
    # 2026-08-24 native-Windows capture, where the banner and Timestep lines
    # preceded this print in the stream — and the bar sits indeterminate.
    w("print('EMStudio: starting openEMS run (NrTS={0}, EndCriteria={1:.3g})...', flush=True)".format(nr_ts, end_criteria))
    # SolverOpenEMS.NumThreads shipped as a property that NOTHING read until
    # v1.14.0: openEMS always took every core. ``numThreads`` is a documented
    # Run() keyword in both python APIs this project meets — v0.0.35/36 call
    # SetNumberOfThreads(), v0.37 passes --numThreads to the engine, which
    # prints "openEMS - fixed number of threads: N" when it takes effect
    # (openems.cpp). 0 keeps the engine's own default (all cores), and the
    # deck line stays byte-identical to every earlier release in that case.
    n_threads = int(getattr(solver, "NumThreads", 0) or 0)
    if n_threads > 0:
        w("FDTD.Run(sim_path, cleanup=False, numThreads={0:d})".format(n_threads))
    else:
        w("FDTD.Run(sim_path, cleanup=False)")
    w("")
    w("# --- post-processing: S-parameters in the shared EMStudio CSV schema ---")
    w("f = np.linspace({0:.9g}, {1:.9g}, {2})".format(f1, f2, npts))
    if wg_cut:
        # Only in a deck whose band starts below a waveguide cut-off, so
        # every other deck stays byte-identical. Sliced, not re-spaced: the
        # samples kept are exactly the ones the user's sweep asked for.
        w("# EMStudio: the first {0} sample(s) lie at or below the {1} cut-off "
          "of waveguide port {2} ({3:.6g} Hz), where openEMS's port returns "
          "NaN - left out (see the model notes)".format(
              wg_cut["drop"], wg_cut["mode"], wg_cut["nr"], wg_cut["fc_hz"]))
        w("f = f[{0}:]".format(wg_cut["drop"]))
    excited = [p for p in ports if p["excite"]][0]
    wg_nrs = sorted(p["nr"] for p in ports if p["type"] == "RectWaveguide")
    if wg_nrs:
        # ⚠⚠ A WAVEGUIDE PORT MUST KEEP ITS OWN MODAL IMPEDANCE.
        # ``WaveguidePort.CalcPort`` computes the analytic TE wave impedance
        # ZL(f) = k*Z0/beta and uses it as the reference — unless a caller hands
        # it one, in which case ``Port.CalcPort`` overwrites it. This writer used
        # to hand EVERY port the excited port's ``R`` (50 ohm), which for WR-28
        # at 30 GHz replaces 529 ohm with 50 and destroys the incident/reflected
        # split.
        # ⛳ MEASURED on a straight PEC-walled WR-28 section terminated in PML —
        # a PERFECTLY MATCHED line, where the answer must be |S11| ~ 0 and
        # P_acc/P_inc = 1 (tests/validation/waveguide_port_openems.py):
        #     ref_impedance=50    -> |S11| = -1.64 dB, P_acc/P_inc = 0.314
        #     ref_impedance=None  -> |S11| = -50.9 dB, P_acc/P_inc = 1.0000
        # This is where ``P_rad/P_acc = 1642 %`` came from: with the power split
        # wrong, P_acc is not the accepted power and the efficiency it feeds is
        # not an efficiency.
        # ⚠ A lumped or MSL port still gets its own R — do not widen this.
        w("_WG_PORTS = {0!r}  # modal Z_ref, never 50 ohm".format(wg_nrs))
        w("for _nr, _p in ports.items():")
        w("    _p.CalcPort(sim_path, f, ref_impedance=("
          "None if _nr in _WG_PORTS else {0:.9g}))".format(z0))
    else:
        w("for _p in ports.values():")
        w("    _p.CalcPort(sim_path, f, ref_impedance={0:.9g})".format(z0))
    w("port = ports[{0}]".format(excited["nr"]))
    w("s11 = port.uf_ref / port.uf_inc")
    w("zin = port.uf_tot / port.if_tot")
    if excited["nr"] in wg_nrs:
        # The z0 COLUMN must say what the S-parameters are actually referenced
        # to, or the row is self-contradictory: zin ~ 530 ohm beside a 50 in the
        # reference column invites every reader to recompute s11 and get a
        # different answer. A waveguide's modal impedance varies with frequency,
        # and the column is per-row, so it can carry it exactly.
        # ⚠ Touchstone cannot: ``SweepResult`` keeps the FIRST row's value
        # (post/sparams.py) and ``write_touchstone`` emits one ``R`` for the
        # whole file. That is a Touchstone limitation, not a new inaccuracy —
        # but do not read the .s1p's R as valid across the band.
        w("z0_col = np.real(np.ravel(port.ZL))  # modal TE impedance, per frequency")
    else:
        w("z0_col = np.full_like(f, {0:.9g})".format(z0))
    w("rows = np.column_stack([f, zin.real, zin.imag, s11.real, s11.imag, z0_col])")
    w("np.savetxt(os.path.join(sim_path, 'port_{0}.csv'.format({0})), rows, delimiter=',',".format(excited["nr"]))
    w("           header='freq_hz,re_zin,im_zin,re_s11,im_s11,z0', comments='')")
    for p in ports:
        if p["nr"] == excited["nr"]:
            continue
        w("s_t = ports[{0}].uf_ref / port.uf_inc  # S{0}{1}".format(p["nr"], excited["nr"]))
        w("np.savetxt(os.path.join(sim_path, 'sparam_{0}_{1}.csv'),".format(p["nr"], excited["nr"]))
        w("           np.column_stack([f, s_t.real, s_t.imag]), delimiter=',',")
        w("           header='freq_hz,re_s,im_s', comments='')")
    if compute_ff:
        # Radiator phase center: middle of the domain bbox. CalcNF2FF's ``center``
        # is in METERS, not drawing units (the tutorial passes [0,0,1e-3] for a
        # point 1 mm up) — passing mm values puts the center far outside the
        # recording box and yields NaN directivity (observed 2026-07-05).
        center = [(dom_lo[i] + dom_hi[i]) / 2.0 * 1e-3 for i in range(3)]
        # WHICH frequencies get a pattern. PatternFrequencies / PatternFreqStart
        # / PatternFreqStop mean here exactly what they mean on NEC2 — 0 = one
        # pattern at the default frequency, N > 1 = N across the band — so the
        # same dialog and the same results picker serve both backends.
        # ⚠ On openEMS the COST IS NOT NEC2's. The NF2FF box is recorded
        # broadband in the time domain, so every extra frequency is one more
        # transform of data the run already holds: no extra solve, no extra
        # solver output. One CalcNF2FF call takes the whole list.
        pat_idx = _pattern_indices(solver, f1, f2, npts)
        if wg_cut and pat_idx:
            # Indices into the FULL sweep, and the deck's f (and P_acc) now
            # starts wg_cut["drop"] samples in: shift them, and a pattern
            # asked for below cut-off lands on the first kept sample — the
            # same clamping _pattern_indices gives one asked for outside
            # the band.
            pat_idx = sorted({max(0, i - wg_cut["drop"]) for i in pat_idx})
        w("")
        w("# --- far field (NF2FF) ---")
        w("s11_db = 20*np.log10(np.maximum(np.abs(s11), 1e-30))")
        if pat_idx:
            w("ff_idx = {0!r}".format(pat_idx))
        else:
            # ⚠⚠ argmin|S11| IS ONLY MEANINGFUL IF THERE IS A RESONANCE TO
            # FIND. On a broadband, well-matched antenna S11 is flat and the
            # argmin lands on numerical noise: measured, the SAME Ka-band horn
            # chose 28.45 GHz at one mesh density and 39.55 GHz at another,
            # which makes any comparison against a published gain curve
            # accidental.
            # ⛳ The fallback is the sweep CENTRE, and specifically that: it is
            # already the Gaussian excitation centre a few lines above, so it
            # is the best-conditioned bin in the recording; it is already the
            # near-field dump frequency; and it is deterministic and
            # mesh-independent.
            # ⚠ Resonant documents are UNTOUCHED. A patch, dipole or notch has
            # far more than {flat:g} dB of S11 range, so the branch below never
            # fires on them and their reported frequency does not move.
            w("if float(s11_db.max() - s11_db.min()) < {flat:g}:".format(
                flat=FLAT_S11_SPAN_DB))
            w("    i_ff = int(np.argmin(np.abs(f - {0:.9g})))".format(f0))
            w("    print('EMStudio: S11 varies by only %.2f dB across the band"
              " — there is no resonance to pick, so the pattern is taken at the"
              " sweep centre %.4g Hz. Set PatternFrequencies to choose your"
              " own.' % (float(s11_db.max() - s11_db.min()), f[i_ff]))")
            w("else:")
            w("    i_ff = int(np.argmin(s11_db))")
            w("ff_idx = [i_ff]")
        w("f_ff_list = [float(f[_i]) for _i in ff_idx]")
        w("f_ff = f_ff_list[0]")
        w("# full sphere for 3-D balloon plots (phi=0/90 columns feed the 2-D cuts)")
        w("theta = np.arange(0.0, 180.1, 5.0)")
        w("phi = np.arange(0.0, 360.0, 5.0)")
        w("ff = nf2ff_box.CalcNF2FF(sim_path, f_ff_list, theta, phi, center={0})".format(_fmt_v(center)))
        # ⚠⚠ ``ff.Dmax`` IS DIRECTIVITY, NOT GAIN. Until 2026-08-22 this block
        # wrote Dmax straight into a column headed ``gain_dbi``, and
        # emstudio/post/farfield.py documents that column as "Gain pattern
        # G(theta, phi) in dBi". They are equal ONLY for a lossless antenna.
        # This writer emits lossy dielectrics (kappa synthesised from
        # tan(delta) a few lines above), so every lossy model shipped a number
        # that OVERSTATED gain by exactly the radiation efficiency — the
        # dangerous direction, in a product whose whole claim is checkable
        # numbers.
        # ⛳ G = D * eta_rad, with eta_rad = P_radiated / P_accepted. openEMS
        # gives both directly: nf2ff carries Prad, and CalcPort leaves P_acc on
        # the port. No extra simulation is needed — the numbers were already in
        # the run and simply never read.
        # One iteration per requested pattern frequency. ``ff.*`` is already
        # indexed per frequency (openEMS/nf2ff.py builds a list per entry of the
        # freq array), so this loop only had to stop hard-coding [0]; and
        # ``port.P_acc`` is indexed on the deck's own f grid, which is why the
        # frequencies were resolved to INDICES rather than to Hz.
        w("_meta_rows = []")
        w("for _k, _i in enumerate(ff_idx):")
        w(" f_ff = float(f[_i])")
        w(" Dmax_dbi = 10.0*np.log10(ff.Dmax[_k])")
        w(" E_norm = ff.E_norm[_k] / np.max(ff.E_norm[_k])")
        w(" dir_dbi = 20.0*np.log10(np.maximum(E_norm, 1e-8)) + Dmax_dbi  # DIRECTIVITY")
        w(" p_acc = float(np.real(np.ravel(port.P_acc)[_i]))")
        w(" p_rad = float(np.real(np.ravel(ff.Prad)[_k]))")
        w(" eta = (p_rad / p_acc) if p_acc > 0 else float('nan')")
        # ⚠⚠ AN EFFICIENCY ABOVE 1 IS NOT A NUMBER, IT IS A FAILED POWER
        # BUDGET. A passive antenna cannot radiate more than it accepts, so
        # eta > 1 means p_acc is not the accepted power at this port — measured
        # with a rectangular WAVEGUIDE port, where CalcPort's modal
        # normalisation differs from a lumped port's: eta came back at 1642 %
        # and would have SCALED GAIN UP BY 12 dB. That is worse than the
        # directivity-as-gain defect this whole block was written to fix, so it
        # must never be applied silently.
        # ⛳ Falling back to DIRECTIVITY is the honest choice: it is a real,
        # well-defined quantity, it is what the code reported before v1.4.0,
        # and it is an UPPER BOUND on gain — erring toward the conservative
        # reading rather than the flattering one. The deck says so out loud.
        w(" if not (eta == eta) or not (0.0 < eta <= 1.05):")
        w("     print('EMStudio: WARNING - power budget did not close "
          "(P_rad/P_acc = %r). Reporting DIRECTIVITY, not gain; the true gain "
          "is at or below this.' % (eta,))")
        w("     eta_db = 0.0")
        w("     eta = float('nan')")
        w(" else:")
        w("     eta_db = 10.0*np.log10(min(eta, 1.0))")
        w(" gain_dbi = dir_dbi + eta_db  # (Nt, Np) TRUE GAIN (or directivity"
          " if the budget failed)")
        w(" ff_rows = []")
        w(" for i_t, th in enumerate(theta):")
        w("     for i_p, ph in enumerate(phi):")
        w("         ff_rows.append((f_ff, th, ph, gain_dbi[i_t, i_p]))")
        # ⚠ ONE CSV PER FREQUENCY, never one CSV holding several. Pouring two
        # frequencies into one grid is exactly the trap NEC2's pattern pass hit:
        # the file parses, and the pattern it returns belongs to no frequency.
        w(" _stem = 'farfield_port_{0}' + ('_%d' % _k if len(ff_idx) > 1 else '')".format(excited["nr"]))
        w(" np.savetxt(os.path.join(sim_path, _stem + '.csv'), np.asarray(ff_rows),")
        w("            delimiter=',', header='freq_hz,theta_deg,phi_deg,gain_dbi', comments='')")
        w(" _meta_rows.append((f_ff, Dmax_dbi, eta, p_acc, p_rad))")
        w(" print('EMStudio: far field at %.4g Hz, D = %.2f dBi, eta_rad = %.1f %%, "
          "G = %.2f dBi' % (f_ff, Dmax_dbi, 100.0*eta, Dmax_dbi + eta_db))")
        # A sidecar, not a 5th column: post.farfield.load_csv unpacks exactly
        # four fields, and NEC2's save_csv writes the same four. Widening the
        # pattern CSV would break both for a scalar that belongs beside it.
        # ⛳ ONE ROW PER FREQUENCY, in the same order as the CSVs, so the runner
        # can pair them without re-deriving anything.
        w("np.savetxt(os.path.join(sim_path, 'farfield_meta_{0}.csv'),".format(excited["nr"]))
        w("           np.asarray(_meta_rows), delimiter=',',")
        w("           header='freq_hz,directivity_dbi,eta_rad,p_acc_w,p_rad_w', comments='')")
        # The single-frequency name is kept as THE pattern for every existing
        # caller (the PDF report, the 3-D balloon, horn_openems). With several,
        # the DEFAULT one is written under both names: the picker reads the
        # numbered files, everything else keeps reading the plain one.
        # ⛳ THE DEFAULT IS THE MIDDLE OF THE BAND THE USER ASKED FOR, not the
        # first entry. NEC2 used to pick the entry nearest a bare
        # argmin|S11| — exactly the choice that has no meaning on a flat
        # band; since 2026-08-24 it shares this guard through
        # SweepResult.pattern_frequency(), so both backends land mid-band on
        # a matched device. The horn template asks for three patterns around
        # 30 GHz precisely so the reported one IS 30 GHz. First-of-list
        # would report 29.5.
        w("if len(ff_idx) > 1:")
        w("    import shutil as _sh")
        w("    _default_k = len(ff_idx) // 2")
        w("    _sh.copyfile(os.path.join(sim_path, 'farfield_port_{0}_%d.csv' % _default_k),".format(excited["nr"]))
        w("                 os.path.join(sim_path, 'farfield_port_{0}.csv'))".format(excited["nr"]))
        w("    print('EMStudio: %d patterns; the reported one is %.4g Hz'"
          " % (len(ff_idx), f[ff_idx[_default_k]]))")
    if nf_plane in ("XY", "XZ", "YZ"):
        w("")
        w("# --- near-field h5 -> npz (|E| map; venv has h5py, FreeCAD may not) ---")
        w("try:")
        w("    import glob")
        w("    import h5py")
        w("    h5s = sorted(glob.glob(os.path.join(sim_path, 'Ef_fd*.h5')))")
        w("    with h5py.File(h5s[0], 'r') as h5:")
        w("        # /FieldData/FD/f0 is complex (3, nx, ny, nz): components x,y,z")
        w("        e = np.array(h5['/FieldData/FD/f0'])")
        w("        ax_x = np.array(h5['/Mesh/x']); ax_y = np.array(h5['/Mesh/y']); ax_z = np.array(h5['/Mesh/z'])")
        w("    e_mag = np.sqrt((np.abs(e) ** 2).sum(axis=0))  # -> (nx, ny, nz)")
        w("    e_mag = np.squeeze(e_mag)                      # 2-D on the cut plane")
        w("    np.savez(os.path.join(sim_path, 'nearfield.npz'),")
        w("             e_mag=e_mag, x=ax_x, y=ax_y, z=ax_z,")
        w("             plane='{0}', freq={1:.9g})".format(nf_plane, f0))
        w("    print('EMStudio: near-field map saved (nearfield.npz), shape %s' % (e_mag.shape,))")
        w("except Exception as _exc:")
        w("    print('EMStudio: near-field conversion failed: %r' % (_exc,))")
    w("print('EMStudio: openEMS deck finished OK')")
    w("")

    deck_path = os.path.join(workdir, "case_openems.py")
    with open(deck_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return deck_path, z0, excited["nr"]
