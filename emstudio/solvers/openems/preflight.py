# SPDX-License-Identifier: LGPL-2.1-or-later
"""Will this FDTD grid fit? — asked BEFORE openEMS is told to build it.

WHY THIS EXISTS
---------------
A forum user (macOS arm64, FreeCAD 1.1.4, 2026-10) set MeshResolution to 2700
on a 1.6 x 1.5 x 3.0 m J-pole domain. The deck built a uniform 0.925 mm grid of
1724 x 1666 x 3283 = 9,429,380,072 cells, openEMS printed "Create FDTD
operator" and the run ended "python exited with code -11". Nothing in EMStudio
had counted the cells first. Two independent limits were both blown:

* **openEMS cannot index it.** Its operator sizes its arrays in 32 bits:
  ``tools/AdrOp.h:119`` declares ``unsigned int uiSize`` and ``AdrOp.cpp:59``
  computes ``uiSize = uiImax*uiJmax*uiKmax``; ``FDTD/operator.cpp:1774-1777``
  allocates the twelve Init_EC arrays of that size and ``Calc_EC_Range`` writes
  through them (``:1844-1851``). Past 2^32 cells the size WRAPS, the arrays are
  too short, and the first write past the end kills the process. The
  3-component ``ArrayNIJK`` arrays wrap even sooner, at 2^32 / 3 cells (size =
  I*J*K*3 truncated to 32 bits — measured against v0.37.0-rc1's own
  ``array_nijk.h``; upstream's changelog says the same: "more than about 1.4
  billion mesh nodes ... corrupted memory"). The default compressed-SSE engine
  EMStudio's decks use is bound by 2^32, but the LOWER bound is the one used
  here: it costs nothing, because a grid that size already needs ~180 GB.
* **the machine cannot hold it.** Peak RSS was measured at about 75-80 MB plus
  97-124 bytes per cell (openEMS v0.37.0-rc1, compressed SSE, float; 0.3 M to
  33.6 M cells on nett's geometry and on an air box — it varies with geometry
  compression and thread count). 9.4e9 cells is ~1.2 TB.

⚠⚠ NEVER KEY A USER MESSAGE ON THE EXIT SIGNAL. The same over-limit deck ends
-11 on the Mac (a write past the wrapped array), -6 on Linux under a memory cap
(``std::bad_alloc`` — ``SetupFDTD`` is not ``except +``), -9 from the Linux OOM
killer uncapped, and exit 1 with a RuntimeError on openEMS master after
2026-10-14. The numbers this module prints — cells, GB needed, GB present —
are the same on every one of them, so they are what the user is told.

TWO LAYERS, ONE IMPLEMENTATION
------------------------------
* **The deck block** (between the ``>>>``/``<<<`` markers below) is PASTED into
  every generated deck by the writer, after the grid is final and before
  openEMS sees it — so FullSMatrix's extra excitations and a user re-running a
  deck by hand are covered too, not just the GUI. It uses only ``os``/``sys``
  (and ``ctypes`` on Windows), because the deck runs under the openEMS venv
  interpreter, never FreeCAD's.
* **The writer's lower bound** (:func:`grid_lower_bound`) refuses a grid that is
  CERTAINLY over a limit before a single STL is written, so the GUI fails in a
  second with the numbers instead of after minutes of tessellation.

FreeCAD-free by design, so the whole thing is testable from plain python3.
"""

from __future__ import annotations

import math
import os
import sys

# >>> EMStudio openEMS preflight (deck block) >>>
# --- EMStudio preflight: count the FDTD grid before openEMS builds it -------
# Pasted verbatim from emstudio/solvers/openems/preflight.py by the writer; see
# that module's docstring for the measurements behind every number here.

#: First cell count EMStudio refuses outright, with no override. openEMS's
#: 3-component arrays size themselves as I*J*K*3 in 32 bits, so they wrap at
#: (2^32 - 1) // 3 = 1,431,655,765 cells; its default engine's own bound is
#: 2^32. The lower one is used because it costs nothing: any grid this big
#: already needs ~180 GB, and past it openEMS corrupts memory or crashes.
OPENEMS_MAX_CELLS = (2 ** 32 - 1) // 3

#: Peak RSS per cell, measured 97-124 B (openEMS v0.37.0-rc1, compressed SSE,
#: float) — rounded UP so the estimate errs toward warning, not toward a
#: machine that swaps for hours. Unmeasured on the MSVC and Homebrew builds.
OPENEMS_BYTES_PER_CELL = 125.0

#: Fixed cost of an openEMS process before the grid: interpreter, CSXCAD,
#: numpy and the engine itself (measured ~75-80 MB).
OPENEMS_BASE_BYTES = 80e6

#: Fraction of PHYSICAL RAM a run may plan to use. Above it the OS, FreeCAD
#: and the page cache are squeezed out and the run swaps or is killed; below
#: it a large run is still allowed. Overridable (see allow_large), unlike the
#: index limit, because a box with fast swap may genuinely want to try.
OPENEMS_RAM_FRACTION = 0.8

#: Environment switch that lifts the RAM branch ONLY. The index limit has no
#: override: past it openEMS does not run slowly, it corrupts memory.
OPENEMS_ALLOW_LARGE_ENV = "EMSTUDIO_OPENEMS_ALLOW_LARGE"


def physical_ram_bytes():
    """Physical RAM of this machine in bytes, or None if it cannot be read.

    ⚠ None means UNKNOWN, and the caller then skips the RAM check entirely —
    a guessed figure would refuse good runs on big machines or wave bad ones
    through on small ones, and either is worse than saying nothing.
    Measured 2026-10-17: Linux sysconf = /proc/meminfo MemTotal; macOS
    sysconf = hw.memsize (8589934592 on the 8 GB M1 build host). The Windows
    call returned wmic's TotalPhysicalMemory on the VM in the diagnosis
    prototype this was taken from; ⚠ this exact copy has not yet been run on
    Windows — the FAST gate's "physical RAM" check is the one to run there.
    """
    if sys.platform == "win32":
        # Windows has no os.sysconf at all; GlobalMemoryStatusEx is the
        # documented call and needs nothing beyond the stdlib's ctypes.
        try:
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            ms = _MemStatus()
            ms.dwLength = ctypes.sizeof(_MemStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                return None
            n = int(ms.ullTotalPhys)
        except Exception:
            return None
    elif sys.platform == "darwin":
        # macOS has SC_PHYS_PAGES too (measured: equal to hw.memsize). Its
        # own branch so a future macOS-only change cannot silently land on
        # Linux — `os.name` is "posix" on both, the trap this project shipped.
        try:
            n = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        except (AttributeError, ValueError, OSError, TypeError):
            return None
    else:
        try:
            n = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        except (AttributeError, ValueError, OSError, TypeError):
            return None
    return n if n > 0 else None


def allow_large(environ=None):
    """True if the user has lifted the RAM check (never the index check)."""
    env = os.environ if environ is None else environ
    return str(env.get(OPENEMS_ALLOW_LARGE_ENV, "")).strip().lower() in (
        "1", "true", "yes", "on")


def cell_count(lines):
    """openEMS's own 'FDTD cells': the PRODUCT of the per-axis line counts.

    Python ints, so the product never wraps here the way it does in openEMS.
    """
    n = 1
    for k in lines:
        n *= int(k)
    return n


def bytes_needed(cells):
    """Estimated peak RSS of an openEMS run on a grid of ``cells`` cells."""
    return OPENEMS_BASE_BYTES + OPENEMS_BYTES_PER_CELL * float(cells)


def _gb(nbytes):
    """GB (1e9 B, the unit the model above was measured in), coarsely."""
    v = float(nbytes) / 1e9
    if v >= 100.0:
        return "%.0f" % v
    if v >= 10.0:
        return "%.1f" % v
    return "%.2f" % v


def _grid_text(lines, at_least):
    return "%s%d x %d x %d" % ("at least " if at_least else "",
                               int(lines[0]), int(lines[1]), int(lines[2]))


def grid_line(lines, ram_bytes, at_least=False):
    """The one line every deck prints, refused or not: what this run costs.

    ASCII on purpose: it is a print() to a pipe, and on Windows that pipe is
    encoded in the locale's code page — a character it cannot encode would
    crash the deck inside the check meant to protect it.
    """
    cells = cell_count(lines)
    if ram_bytes:
        have = "this machine has %s GB" % _gb(ram_bytes)
    else:
        have = ("this machine's RAM could not be read, so only the index "
                "limit is checked")
    return "EMStudio: FDTD grid {grid} = {cells:,} cells, needs about {gb} GB " \
        "({have})".format(grid=_grid_text(lines, at_least), cells=cells,
                          gb=_gb(bytes_needed(cells)), have=have)


def refusal(lines, mesh_res_mm, ram_bytes, allow=False, at_least=False):
    """Why this grid must not be handed to openEMS — or None if it may run.

    ``lines`` is (nx, ny, nz) mesh-line counts; ``mesh_res_mm`` is the cell
    the user's MeshResolution produced; ``ram_bytes`` is physical RAM or None
    (unknown: the RAM branch is skipped, never guessed); ``allow`` lifts the
    RAM branch only; ``at_least`` marks a writer-side LOWER BOUND, so the
    message never claims an exact count it did not measure.
    """
    cells = cell_count(lines)
    need = bytes_needed(cells)
    grid = _grid_text(lines, at_least)
    if cells >= OPENEMS_MAX_CELLS:
        # ⚠ No override, by design: past this openEMS does not run slowly,
        # it writes past the end of its own arrays.
        return (
            "EMStudio: REFUSED — grid {grid} = {cells:,} cells; openEMS "
            "cannot index a grid of {lim:,} cells or more (its array sizes are "
            "32-bit and wrap, so it corrupts memory or crashes), and this grid "
            "would need ~{gb} GB of RAM. Lower MeshResolution (now cell = "
            "{cell:.4g} mm).".format(grid=grid, cells=cells,
                                     lim=OPENEMS_MAX_CELLS, gb=_gb(need),
                                     cell=float(mesh_res_mm)))
    if ram_bytes and not allow and need > OPENEMS_RAM_FRACTION * float(ram_bytes):
        return (
            "EMStudio: REFUSED — grid {grid} = {cells:,} cells needs about "
            "{gb} GB of RAM, more than {pct:.0f} % of the {have} GB this "
            "machine has, so it would swap for hours or be killed. Lower "
            "MeshResolution (now cell = {cell:.4g} mm), or set {env}=1 in the "
            "environment FreeCAD is started from to run it anyway.".format(
                grid=grid, cells=cells, gb=_gb(need),
                pct=100.0 * OPENEMS_RAM_FRACTION, have=_gb(ram_bytes),
                cell=float(mesh_res_mm), env=OPENEMS_ALLOW_LARGE_ENV))
    return None
# <<< EMStudio openEMS preflight (deck block) <<<

_BLOCK_BEGIN = "# >>> EMStudio openEMS preflight (deck block) >>>"
_BLOCK_END = "# <<< EMStudio openEMS preflight (deck block) <<<"

#: What the deck RUNS once the block above is pasted. It sits after the
#: smoothing and the _snap SetLines block (so it counts exactly the grid
#: openEMS will build) and before the NF2FF box, the --preview exit and
#: FDTD.Run. The ``_pf_`` prefix keeps these names clear of the deck's own.
#: ⚠ --preview only WARNS: it writes case.xml and never builds the operator,
#: and a preview is how a user (and this project's own diagnosis) inspects an
#: oversized grid in the first place.
DECK_CALL = [
    "_pf_lines = [len(mesh.GetLines(_a)) for _a in 'xyz']",
    "_pf_ram = physical_ram_bytes()",
    "print(grid_line(_pf_lines, _pf_ram), flush=True)",
    "_pf_why = refusal(_pf_lines, mesh_res, _pf_ram, allow_large())",
    "if _pf_why and preview_only:",
    "    print('EMStudio: preview only - a full run of this grid would be "
    "refused: ' + _pf_why.encode('ascii', 'replace').decode('ascii'), "
    "flush=True)",
    "elif _pf_why:",
    "    raise SystemExit(_pf_why)",
]


def deck_block():
    """The source between the markers, read from THIS file.

    Read rather than re-typed, so the deck runs exactly the code the gate
    tests. ⚠ Raises if the markers are missing: a deck written without its
    preflight would be the silent regression this whole module exists to stop.

    ⚠ Read from ``__file__``, not through ``sys.modules[__name__]``: a
    FreeCAD-free caller loads this file BY PATH (importing it through the
    package runs ``openems/__init__`` -> runner -> writer -> ``import
    FreeCAD``), and such a module need not be registered under any name.
    """
    with open(os.path.splitext(os.path.abspath(__file__))[0] + ".py",
              encoding="utf-8") as fh:
        src = fh.read()
    try:
        start = src.index(_BLOCK_BEGIN)
        stop = src.index(_BLOCK_END, start)
    except ValueError:
        raise RuntimeError("emstudio/solvers/openems/preflight.py: the deck "
                           "block markers are missing — refusing to write a "
                           "deck without its grid preflight")
    return src[start:stop + len(_BLOCK_END)].splitlines()


def deck_lines():
    """Every line the writer pastes into a deck: the block, then the call."""
    return deck_block() + [""] + list(DECK_CALL)


# --------------------------------------------------------------------------
# Writer-side LOWER BOUND — the same limits, before any STL is written.
# --------------------------------------------------------------------------
#: Speed of light, m/s — the writer's own constant, repeated so this module
#: stays importable without the writer (which imports FreeCAD).
C0 = 299792458.0

#: Slack on the per-axis line count. SmoothMeshLines guarantees no cell
#: exceeds mesh_res (to 1e-10, CSXCAD SmoothMeshLines.py), so an axis of
#: extent E carries at least E/mesh_res + 1 lines. The deck prints mesh_res to
#: 9 significant digits; 1 % covers that rounding with room to spare, and a
#: bound that is 1 % low can only ever under-refuse, never over-refuse.
_LINE_SLACK = 0.01


def lower_bound_lines(extent_mm, mesh_res_mm):
    """Per-axis line counts the final grid CANNOT be below.

    ``extent_mm`` is the simulation-domain size on each axis. Local
    refinement, metal-edge lines and the absorber guard only ever ADD lines,
    so the product of these is a floor under the real cell count.
    """
    res = float(mesh_res_mm) * (1.0 + _LINE_SLACK)
    out = []
    for e in extent_mm:
        e = max(0.0, float(e))
        out.append(int(math.floor(e / res)) + 1 if res > 0 else 1)
    return tuple(out)


def _hz(q):
    """A FreeCAD frequency Quantity (or a plain number) in Hz."""
    if hasattr(q, "getValueAs"):
        return float(q.getValueAs("Hz"))
    return float(getattr(q, "Value", q))


def _referenced_bbox(analysis, issues=None):
    """(lo, hi) over every part the model will contain, or None.

    The parts are ``query.reference_leaves`` — the SAME call
    geometry.classify_shapes makes, so this counts exactly what the model
    will hold: part picks through a group, each part once, hidden group
    parts left out, and every reference that reaches no geometry (a
    Part::Line, a sketch, an edges-only shape, a stale face) DROPPED — with
    the reason appended to ``issues`` as ``(material label, level, text)``,
    the text classify_shapes would report. Only bounding boxes are read, so
    nothing is tessellated or written. Anything it cannot read is left OUT: a
    smaller box can only make this bound lower, i.e. safer.

    ⚠⚠ Until the v1.14.0 review this re-derived "what counts" from
    ``query.resolved_references``, which keeps a wire-only whole-object
    reference: a 2-3 GHz dipole of 16,758 cells with an 8 m construction
    line in its PEC was REFUSED here at "at least 4,093,427,212 cells" — the
    line's bounding box, for a line the model never contains — and the
    warning saying it was dropped never appeared, because this refusal
    fires before classify_shapes runs. Never re-derive it again: share the
    classification.
    """
    from emstudio.objects import query     # FreeCAD-free (tag matching only)

    inf = float("inf")
    lo, hi = [inf, inf, inf], [-inf, -inf, -inf]
    found = False
    for mat in query.get_materials(analysis):
        leaves, problems = query.reference_leaves(mat)
        if issues is not None:
            label = str(getattr(mat, "Label", "") or "material")
            issues.extend((label, level, text) for level, text in problems)
        for rec in leaves:
            # The record's own cached global box (query._bbox_of): the one
            # de-duplication already computed, so OpenCASCADE is not asked
            # for it twice.
            box = query._bbox_of(rec)
            if box is None:
                continue
            if not all(math.isfinite(float(v)) for v in box):
                continue
            for i in range(3):
                lo[i] = min(lo[i], float(box[i]))
                hi[i] = max(hi[i], float(box[3 + i]))
            found = True
    return (lo, hi) if found else None


def grid_lower_bound(analysis, solver=None):
    """A floor under the grid the writer will build, or None if unknown.

    Returns ``{"lines": (nx, ny, nz), "mesh_res_mm": c, "msl": bool,
    "issues": [(material label, "warning" | "note", text), ...]}`` —
    ``issues`` are the reference problems found while reading the parts
    (:func:`_referenced_bbox`), which a caller that REFUSES on this floor
    must show first: they are the only record of what was left out, and
    the refusal fires before the writer's own pass would report them.
    Computed from bounding boxes and the analysis' own settings exactly as
    write_deck computes them:

    * the cell is ``C0 / f_max / MeshResolution`` (MeshResolution floored at
      6) — the writer's antenna rule. The microstrip branch uses a FINER cell
      (lambda/50 in the substrate), so this is an upper bound on the cell and
      the line counts stay a lower bound there too;
    * the domain is the geometry plus ``DomainPaddingWavelengths`` of the
      centre wavelength on every side — except on the microstrip branch,
      which hugs the geometry, so no padding is counted there. The absorber
      guard can only grow the domain.

    ⚠ This is a FLOOR, not an estimate: the deck's own check counts the real
    lines. The writer refuses on it only when it is already over a limit.
    """
    from emstudio.objects import query

    f1 = _hz(analysis.FrequencyStart)
    f2 = _hz(analysis.FrequencyStop)
    f0 = 0.5 * (f1 + f2)
    fc = 0.5 * (f2 - f1)
    if not (fc > 0.0 and f0 > 0.0):
        return None
    # The writer's exact expression, so "now cell = ..." quotes the same
    # number the deck will print as mesh_res.
    mesh_res = C0 / (f0 + fc) / 1e-3 / max(6, int(analysis.MeshResolution))
    issues = []
    box = _referenced_bbox(analysis, issues)
    if box is None:
        return None
    lo, hi = box
    msl = (any(str(getattr(p, "PortType", "Lumped")) == "MSL"
               for p in query.get_ports(analysis))
           and str(getattr(solver, "MicrostripMeshMode", "Auto")) == "Auto")
    pad = 0.0
    if not msl:
        pad = float(getattr(analysis, "DomainPaddingWavelengths", 0.0)) \
            * (C0 / f0 * 1000.0)
    extent = [max(0.0, (hi[i] - lo[i]) + 2.0 * pad) for i in range(3)]
    return {"lines": lower_bound_lines(extent, mesh_res),
            "mesh_res_mm": mesh_res, "msl": msl, "issues": issues}
