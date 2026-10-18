#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""SOLVER gate — the openEMS grid preflight, live: real decks, real openEMS.

The pure half (limits, RAM branch, the pasted deck code against a fake grid,
the process plumbing) is ``openems_preflight`` in the FAST tier. This half
proves the parts only a real deck and a real openEMS can:

A. WHERE the writer pastes the check: after the grid is final (the _snap
   SetLines block) and before the NF2FF box, the --preview exit and FDTD.Run
   — and that its names cannot collide with the deck's own.
B. the WRITER's floor refuses an over-limit model before a single STL is
   written (control: the same model at a sane resolution DOES write one), and
   the floor never exceeds the grid openEMS actually builds. And it counts
   only what the MODEL holds (v1.14.0 review): a dipole whose PEC also
   references an 8 m construction line is written, its floor the dipole's
   alone — the floor once kept the line and refused it at "at least
   4,093,427,212 cells" — and when such a model IS over the limit, the
   line's WARNING is said before the refusal and carried in it.
C. a real run through the product runner: the deck's grid line counts EXACTLY
   the grid openEMS reports building; NumThreads reaches openEMS; a run cut
   off at NrTS is reported; and the venv python survives a host PYTHONHOME
   (the 1.1.4 AppImage failure) — with the control that, unscrubbed, it dies.
D. a deck re-run BY HAND on an over-limit grid refuses on its own, in
   seconds, before 'Create FDTD operator' — and the NEGATIVE CONTROL: the same
   deck with the check stripped DOES reach 'Create FDTD operator'.
E. the pre-solve estimate now sees the grid (it scored every openEMS solve
   the same, 201.0, until v1.14.0) — the REFINED grid (v1.14.0 review): on
   the forum's 18/1.2 mm tube its count equals the floor write_deck itself
   budgets, line for line, is a floor of that deck's own grid (within
   10 %), and is what gets priced (57x the bounding-box floor's cells, the
   1.2 mm lines setting the timestep). ⚠ The writer's count is not a floor
   on every model — on the forum J-pole it is 3.85 M against openEMS's
   2.94 M (see writer.grid_estimate) — so that check pins THIS model.
F. a port openEMS could not place, or a result that is not a number, is a
   FAILED run, never "finished OK" (v1.14.0, the forum J-pole: openEMS
   printed "Lumped Element snapping failed! ... skipping", exited 0, and an
   all-NaN port_1.csv loaded as a result). REAL openEMS runs through the
   product runner: a port squeezed into one cell, and one moved outside the
   domain (which only the unused-primitive summary reports), each fail
   naming port 1 — the first stopped before a single port file is written —
   with the CONTROL that the unedited deck runs. A stand-in deck (no FDTD)
   proves an all-NaN, a one-NaN and a NaN-S21 file each fail and a finite
   one loads, including the second excitation of a FullSMatrix run; and the
   watch's reading of openEMS's lines is driven deterministically (a metal
   or dump primitive left unused is NOT a port fault).
G. the v1.14.0 review's fixes that need the product runner. A WR-28 guide
   swept 18-30 GHz (the review's own case: openEMS's waveguide port is NaN
   in the 7 samples below the 21.08 GHz TE10 cut-off, BY DESIGN) returns
   the 18 samples above it, all finite, with the writer's NOTE in
   result.meta — it used to be thrown away whole and blamed on a port
   "never in the simulation". A deck that KEPT those samples is refused as
   below cut-off, never as a missing port (CONTROL: a NaN above cut-off is
   still the missing-port error). The deck's model notes reach
   result.meta['warnings'] / ['notes'] — once per FullSMatrix run, after
   the runner's own timestep note (CONTROL: a deck with none adds no key).
   And the openEMS version probe exits normally, still reporting the
   banner's version: "--version" is no option to openEMS v0.37, which
   aborted on it and left a core per probe.

⚠⚠ SAFETY. An over-limit grid is never run uncapped on this shared box: every
deck that could reach openEMS's operator runs under RLIMIT_AS 4 GiB, with
RLIMIT_CORE = 1 (the kernel's own "no core for a piped core_pattern" value —
0 is passed to systemd-coredump, which this box's core_pattern overrides),
OPENBLAS_NUM_THREADS=1 and MALLOC_ARENA_MAX=2 (on a 128-core box OpenBLAS's
per-thread buffers alone exhaust a 4 GiB address space and the interpreter
HANGS in a futex before the deck's first line — measured 2026-10-17), and is
SIGKILLed the moment it prints 'Create FDTD operator'. Where RLIMIT_AS does
not exist (Windows) section D does not run, and says so.

Exit codes: 0 pass, 1 a check failed, 2 FreeCAD absent (nothing ran — the
battery declares this gate in NEEDS_FREECAD, so only a by-hand python3 run
gets here, and it must not read as a pass).

Mutations proven to fail this gate (2026-10-17): the writer's deck call
removed; the writer-side floor check removed; the limit at (2^33-1)//3;
NumThreads not passed; the NrTS watch removed; the runner's env_filter
removed; estimate.work_of's openEMS branch removed.
v1.14.0 review fixes: the floor re-deriving its parts from
resolved_references; the dropped reference's warning not said before the
refusal; not carried in it; openems_work pricing the bounding-box floor;
the timestep proxy back to the line count; grid_estimate dropping solids.
Section G (v1.14.0 review fixes, track B): the writer's below-cut-off slice
removed; the cut-off NOTE kept out of the deck; the runner's cut-off
backstop disabled; the model notes not copied into result.meta, copied
without de-duplication, and copied before the runner's own note; the
openEMS probe back to "--version".
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []
_RC_SKIPPED = 2

#: openEMS's own report of the operator it built (openems.cpp SetupFDTD).
_SIZE_RE = re.compile(r"FDTD simulation size: (\d+)x(\d+)x(\d+) --> (\d+) FDTD cells")
_GRID_RE = re.compile(r"EMStudio: FDTD grid (\d+) x (\d+) x (\d+) = ([\d,]+) cells")

#: Over-limit cell for the hand-edited deck: the patch domain (~135 x 135 x 77
#: mm) at 0.09 mm is ~1.9e9 cells — inside the 1.43e9..4.29e9 window, so the
#: deck-level refusal also proves the LOWER of openEMS's two 32-bit bounds is
#: the one in force. (0.07 mm measured 1938 x 1939 x 1097 = 4.12e9.)
_OVER_RES_MM = 0.09


def check(msg, ok, detail=""):
    detail = " | ".join(str(detail).split("\n")) if detail else ""
    print(("  ok   " if ok else "  FAIL ") + msg
          + (("   [" + detail[:160] + "]") if detail else ""))
    if not ok:
        FAILURES.append(msg)


def _solver(ana):
    return [o for o in ana.Group
            if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]


def _metal(ana):
    return [o for o in ana.Group
            if getattr(o, "EMStudioType", "") == "EMStudio::Material"
            and str(o.Category).startswith("Metal")][0]


def _capped_run(python, deck, kill_at=None, timeout=120):
    """Run a deck under the safety caps. Returns (rc, seconds, output, killed).

    ``kill_at``: SIGKILL the child the moment a line contains it (no core,
    no allocation). POSIX only — the caller checks for ``resource`` first.

    ⚠ The caps are set by a one-line LAUNCHER (the venv python capping itself,
    then exec'ing the deck), not by ``preexec_fn``: this gate runs inside
    freecadcmd, a threaded process, where Python documents preexec_fn as
    unsafe. ⚠ RLIMIT_CORE must be exactly 1 BYTE — a shell's ``ulimit -c 1``
    is 1 KiB or 512 B and would not trigger the kernel's special case.
    """
    from emstudio.solvers.base import foreign_python_env
    env = foreign_python_env(dict(os.environ, OPENBLAS_NUM_THREADS="1",
                                  OMP_NUM_THREADS="1", MALLOC_ARENA_MAX="2"))
    launcher = ("import os, resource, sys; "
                "resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30)); "
                "resource.setrlimit(resource.RLIMIT_CORE, (1, 1)); "
                "os.execv(sys.argv[1], sys.argv[1:])")
    t0 = time.time()
    proc = subprocess.Popen([python, "-c", launcher, python, deck],
                            cwd=os.path.dirname(deck),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", env=env)
    out, killed = [], False
    deadline = t0 + timeout
    for line in proc.stdout:
        out.append(line.rstrip("\n"))
        if kill_at and kill_at in line:
            proc.kill()
            killed = True
            break
        if time.time() > deadline:
            proc.kill()
            out.append("GATE: TIMEOUT after %.0f s" % timeout)
            break
    rc = proc.wait(timeout=60)
    return rc, time.time() - t0, "\n".join(out), killed


def main():
    print("EMStudio openEMS grid-preflight gate (live)")
    try:
        import FreeCAD
        import Part
    except ImportError:
        print("  skip  needs FreeCAD — run under freecadcmd")
        print("PREFLIGHT LIVE GATE SKIPPED — no FreeCAD in this interpreter; "
              "nothing was tested, this is NOT a pass")
        return _RC_SKIPPED

    from emstudio.setup.solvers import find_openems_python
    python = find_openems_python()
    if not python:
        raise SystemExit("openEMS is required for this gate and was not found "
                         "— set EMSTUDIO_OPENEMS_PYTHON. (The battery skips "
                         "this gate automatically; a direct run does not.)")

    from emstudio.solvers import base, estimate
    from emstudio.solvers.openems import preflight, runner, writer
    from emstudio.templates import patch as patch_tpl

    work = tempfile.mkdtemp(prefix="emstudio_pflive_")
    try:
        _sections(FreeCAD, Part, python, base, estimate, preflight, runner,
                  writer, patch_tpl, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("-------------------")
    if FAILURES:
        raise SystemExit("PREFLIGHT LIVE GATE FAILED: " + "; ".join(FAILURES))
    print("PREFLIGHT LIVE GATE PASSED")
    return 0


def _sections(FreeCAD, Part, python, base, estimate, preflight, runner, writer,
              patch_tpl, work):
    doc = FreeCAD.newDocument("pflive")
    ana = patch_tpl.makePatch(doc)
    solver = _solver(ana)

    # == A. where the check sits in the deck ================================
    d_a = os.path.join(work, "a")
    os.makedirs(d_a)
    deck_path, _z0, _nr = writer.write_deck(ana, solver, d_a)
    with open(deck_path, encoding="utf-8") as fh:
        deck = fh.read()
    lines = deck.splitlines()
    begin = preflight._BLOCK_BEGIN
    check("the deck carries the preflight block exactly once",
          lines.count(begin) == 1)
    call = list(preflight.DECK_CALL)
    i_call = next((i for i in range(len(lines))
                   if lines[i:i + len(call)] == call), -1)
    check("...and the call that runs it, verbatim", i_call >= 0)
    i_block = lines.index(begin) if begin in lines else -1
    i_snap = max([i for i, ln in enumerate(lines)
                  if ln.startswith("mesh.SetLines(") and "_snap(" in ln] or [-1])
    after = [i for i, ln in enumerate(lines)
             if ln.startswith("nf2ff_box =") or ln == "if preview_only:"
             or ln.startswith("FDTD.Run(")]
    check("...placed AFTER the final grid (_snap) and BEFORE NF2FF / --preview "
          "/ FDTD.Run [snap %d < block %d < call %d < %s]"
          % (i_snap, i_block, i_call, min(after) if after else None),
          0 <= i_snap < i_block < i_call and after and i_call < min(after))

    # Name hygiene: the block is pasted into the deck's namespace, so a name
    # it defines must not be one the deck (or a later writer change) assigns.
    tree = ast.parse(deck)
    blk = ast.parse("\n".join(preflight.deck_lines()))

    def _bound(t):
        names = set()
        for node in t.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for tg in targets:
                    for n in ast.walk(tg):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
        return names
    ours = _bound(blk)
    theirs = _bound(tree) - ours
    # Anything the deck binds that the block also binds would show up as a
    # duplicate binding count, so count bindings rather than diff sets.
    dup = sorted(n for n in ours if sum(
        1 for node in tree.body
        if (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == n)
        or (isinstance(node, ast.Assign) and any(
            isinstance(x, ast.Name) and x.id == n
            for tg in node.targets for x in ast.walk(tg)))) > 1)
    check("the block's %d names collide with none of the deck's %d" %
          (len(ours), len(theirs)), not dup, dup)

    check("NumThreads 0 leaves the Run line byte-identical to v1.13.x",
          "FDTD.Run(sim_path, cleanup=False)" in lines)
    solver.NumThreads = 2
    d_a2 = os.path.join(work, "a2")
    os.makedirs(d_a2)
    p2, _z, _n = writer.write_deck(ana, solver, d_a2)
    with open(p2, encoding="utf-8") as fh:
        check("NumThreads 2 reaches the deck as numThreads=2",
              "FDTD.Run(sim_path, cleanup=False, numThreads=2)"
              in fh.read().splitlines())

    # == B. the writer's floor ==============================================
    doc_b = FreeCAD.newDocument("pflive_b")
    ana_b = patch_tpl.makePatch(doc_b)
    rod = doc_b.addObject("Part::Feature", "Rod")
    rod.Shape = Part.makeCylinder(2.0, 20.0, FreeCAD.Vector(20.0, 20.0, 1.524))
    metal = _metal(ana_b)
    refs = list(metal.References)
    refs.append((rod, ""))
    metal.References = refs                     # append-reassign, or nothing
    doc_b.recompute()
    d_ok = os.path.join(work, "b_ok")
    os.makedirs(d_ok)
    writer.write_deck(ana_b, _solver(ana_b), d_ok)
    check("CONTROL: this model DOES export an STL body at MeshResolution 20",
          any(f.endswith(".stl") for f in os.listdir(d_ok)),
          sorted(os.listdir(d_ok)))
    ana_b.MeshResolution = 3000
    d_big = os.path.join(work, "b_big")
    os.makedirs(d_big)
    t0 = time.time()
    msg = ""
    try:
        writer.write_deck(ana_b, _solver(ana_b), d_big)
    except writer.OpenEMSModelError as exc:
        msg = str(exc)
    dt = time.time() - t0
    check("at MeshResolution 3000 the WRITER refuses (%.2f s)" % dt,
          msg.startswith("EMStudio: REFUSED") and "cannot index" in msg
          and "at least" in msg and dt < 10.0, msg[:110])
    check("...before writing a single file (no STL, no deck)",
          os.listdir(d_big) == [], os.listdir(d_big))

    # The floor counts what the MODEL holds (v1.14.0 review). A 2-3 GHz
    # dipole (two 2 x 2 x 28 mm PEC arms) whose PEC also references an 8 m
    # construction LINE: the model drops the line (a wire, with a WARNING),
    # so its grid is the dipole's — but the floor once re-derived "what
    # counts", kept the line's 8 m box and refused this 16,758-cell model at
    # "at least 4,093,427,212 cells", before the warning could say why.
    _wire_floor_checks(FreeCAD, Part, preflight, writer, work)

    # == C. a real run through the product runner ===========================
    solver.MaxTimesteps = 1000          # the writer floors NrTS at 1000
    solver.EndCriteriaDB = -200.0       # never reached: the cap MUST bind
    solver.ComputeFarField = False
    solver.NearFieldPlane = "None"
    solver.NumThreads = 2
    seen = []
    poison = os.path.join(work, "no-such-python-home")
    saved = os.environ.get("PYTHONHOME")
    os.environ["PYTHONHOME"] = poison   # what the 1.1.4 AppImage exports
    err, res = None, None
    try:
        res = runner.run(ana, solver, workdir=os.path.join(work, "c"),
                         line_callback=seen.append)
    except Exception as exc:                               # noqa: BLE001
        err = exc
    finally:
        if saved is None:
            os.environ.pop("PYTHONHOME", None)
        else:
            os.environ["PYTHONHOME"] = saved
    check("the runner completes with a host PYTHONHOME set (F8 scrub)",
          res is not None, repr(err)[-150:] if err else "")
    # CONTROL: the same interpreter, same PYTHONHOME, no filter, dies.
    died = ""
    try:
        base.SolverJob([python, "-c", "import numpy"], cwd=work,
                       env={"PYTHONHOME": poison}).run_blocking(timeout=60)
    except base.SolverError as exc:
        died = str(exc)
    check("CONTROL: unscrubbed, the openEMS venv python dies of it",
          "encodings" in died, died[-100:] if died else "it ran")
    if res is None:
        return
    grid = [m for m in (_GRID_RE.match(ln) for ln in seen) if m]
    size = [m for m in (_SIZE_RE.search(ln) for ln in seen) if m]
    check("the deck printed exactly one grid line", len(grid) == 1, len(grid))
    check("openEMS reported the operator it built", len(size) == 1, len(size))
    if grid and size:
        g, s = grid[0], size[0]
        same = (tuple(int(g.group(k)) for k in (1, 2, 3))
                == tuple(int(s.group(k)) for k in (1, 2, 3))
                and int(g.group(4).replace(",", "")) == int(s.group(4)))
        check("the preflight counted EXACTLY the grid openEMS built [%s vs %s]"
              % (g.group(0)[20:], s.group(0)), same)
        floor = preflight.grid_lower_bound(ana, solver)
        real = tuple(int(g.group(k)) for k in (1, 2, 3))
        check("the writer's floor %r never exceeds that grid %r"
              % (floor["lines"], real),
              all(a <= b for a, b in zip(floor["lines"], real)))
        res_deck = float([ln.split("=")[1] for ln in lines
                          if ln.startswith("mesh_res =")][0])
        check("...and uses the deck's own cell [%.9g vs %.9g mm]"
              % (floor["mesh_res_mm"], res_deck),
              abs(floor["mesh_res_mm"] / res_deck - 1.0) < 1e-8)
    full = [ln for ln in seen if ln.startswith("EMStudio: FDTD grid")]
    check("the result carries the grid line (meta['fdtd_grid'])",
          bool(full) and res.meta.get("fdtd_grid") == full[-1],
          res.meta.get("fdtd_grid"))
    check("nothing was refused", not any("REFUSED" in ln for ln in seen))
    check("NumThreads reached openEMS ('fixed number of threads: 2')",
          any("fixed number of threads: 2" in ln for ln in seen))
    # 1000 steps is shorter than this patch's own excitation pulse (2741
    # steps at MeshResolution 20), so openEMS CUTS the pulse: truncation is
    # CERTAIN without any energy measurement — and the result shows it: best
    # "match" -2.2 dB at the band edge (measured under the 1.1.4 AppImage,
    # 2026-10-17).
    warned = res.meta.get("warnings") or []
    check("a run cut off at NrTS is a WARNING, in the result and the log",
          len(warned) == 1 and "CUT its excitation pulse" in warned[0]
          and "allows 1000" in warned[0] and warned[0] in seen
          and not res.meta.get("notes"),
          warned[0][:110] if warned else "nothing reported")
    # The wordings, driven deterministically: openEMS measures the energy
    # only every ~4 s of wall time, so which evidence a live run carries
    # depends on this box's speed — the CLASSIFICATION must not.
    hit = ("RunFDTD: Warning: Max. number of timesteps was reached before "
           "the end-criteria of -40dB was reached... ")
    banner = "EMStudio: starting openEMS run (NrTS=30000, EndCriteria=0.0001)..."
    long_cap = ("Max. number of timesteps: 30000 ( --> 10.9449 * Excitation "
                "signal length)")
    w = runner._DeckWatch(None)
    for ln in (banner, long_cap,
               "[@        4s] Timestep:         9321 || Speed:  104.0 MC/s "
               "(4.301e-04 s/TS) || Energy: ~7.62e-16 (-30.23dB)", hit):
        w(ln)
    kind, text = w.warning(solver)
    check("a MEASURED shortfall is a WARNING quoting the decay",
          kind == "warning" and "-30.2 dB" in text and "-40 dB" in text, text[:100])
    w2 = runner._DeckWatch(None)
    for ln in (banner, long_cap, hit):
        w2(ln)
    kind2, text2 = w2.warning(solver)
    check("UNMEASURED with a cap of 10.9 pulses (a run under ~4 s) is a NOTE, "
          "claiming no decay", kind2 == "note" and "not confirmed" in text2)
    w3 = runner._DeckWatch(None)
    for ln in (banner, "Max. number of timesteps: 5000 ( --> 1.82 * "
               "Excitation signal length)", hit):
        w3(ln)
    kind3, text3 = w3.warning(solver)
    check("UNMEASURED but under openEMS's own 3-pulse minimum is a WARNING",
          kind3 == "warning" and "1.8 x" in text3, text3[:100])
    check("a run that never hit NrTS reports nothing",
          runner._DeckWatch(None).warning(solver) is None)

    # == D. the deck refuses on its own =====================================
    try:
        import resource  # noqa: F401
    except ImportError:
        print("  note section D NOT RUN on %s: no RLIMIT_AS to cap an "
              "over-limit openEMS on a shared machine" % sys.platform)
        resource = None
    d_d = os.path.join(work, "d")
    os.makedirs(d_d)
    big = re.sub(r"(?m)^mesh_res = .*$", "mesh_res = %g" % _OVER_RES_MM, deck)
    big_deck = os.path.join(d_d, "case_openems.py")
    with open(big_deck, "w", encoding="utf-8") as fh:
        fh.write(big)
    refused_ok = False
    if resource is not None:
        rc, dt, out, killed = _capped_run(python, big_deck,
                                          kill_at="Create FDTD operator")
        m = _GRID_RE.search(out)
        cells = int(m.group(4).replace(",", "")) if m else 0
        refused_ok = rc != 0 and "EMStudio: REFUSED" in out
        check("a hand-edited deck (cell %g mm) refuses ITSELF [rc %d, %.1f s]"
              % (_OVER_RES_MM, rc, dt),
              refused_ok and "cannot index" in out and dt < 60.0
              and not killed, out[-120:])
        check("...after printing its grid: %s cells, inside the 1.43e9..4.29e9 "
              "window" % (m.group(4) if m else "?"),
              preflight.OPENEMS_MAX_CELLS <= cells < 2 ** 32)
        check("...and openEMS never started building ('Create FDTD operator' "
              "ABSENT)", "Create FDTD operator" not in out)

        # NEGATIVE CONTROL — the same deck, check stripped. If this does NOT
        # reach the operator, the ABSENT above proves nothing.
        a = big.index(preflight._BLOCK_BEGIN)
        tail = preflight.DECK_CALL[-1]
        b = big.index(tail, a) + len(tail)
        bare = os.path.join(d_d, "case_bare.py")
        with open(bare, "w", encoding="utf-8") as fh:
            fh.write(big[:a] + "# (preflight stripped: negative control)\n"
                     + big[b:])
        rc, dt, out, killed = _capped_run(python, bare,
                                          kill_at="Create FDTD operator")
        check("NEGATIVE CONTROL: stripped of its check, the same deck DOES "
              "reach 'Create FDTD operator' [rc %d, %s]"
              % (rc, "killed there" if killed else "died there"),
              "Create FDTD operator" in out and "EMStudio: REFUSED" not in out,
              out[-120:])

    # End to end through SolverJob — ONLY once the capped run proved the deck
    # refuses: SolverJob applies no memory cap, and an over-limit deck that
    # did NOT refuse would allocate ~90 GB on a shared machine.
    if refused_ok:
        head = ""
        try:
            base.SolverJob([python, big_deck], cwd=d_d,
                           env_filter=base.foreign_python_env).run_blocking(120)
        except base.SolverError as exc:
            head = str(exc).splitlines()[0]
        check("through SolverJob the error's HEADLINE is the refusal",
              head.startswith("EMStudio: REFUSED") and "cannot index" in head,
              head[:100])
    elif resource is not None:
        check("through SolverJob the error's HEADLINE is the refusal "
              "(NOT RUN: the capped run did not refuse, so running it "
              "uncapped would be unsafe)", False)

    # == E. the pre-solve estimate sees the grid ============================
    ana.MeshResolution = 20
    w20 = estimate.work_of(ana, solver)
    ana.MeshResolution = 60
    w60 = estimate.work_of(ana, solver)
    ana.MeshResolution = 2700
    w2700 = estimate.work_of(ana, solver)
    ana.MeshResolution = 20
    ratio = w60 / w20 if w20 else 0.0
    check("the openEMS work measure follows the grid: MR 60 / MR 20 = %.0f "
          "(cells x steps ~ MR^4 = 81)" % ratio, 40.0 <= ratio <= 160.0)
    check("...so MR 20 and MR 2700 no longer share a history bucket "
          "[%d vs %d]" % (estimate.bucket_of(w20), estimate.bucket_of(w2700)),
          estimate.bucket_of(w2700) - estimate.bucket_of(w20) >= 20)
    solver.FullSMatrix = False
    check("...and is NOT the frequency-point count the generic path gives "
          "[%g]" % w20, w20 != float(ana.FrequencyPoints))
    _refined_price_checks(FreeCAD, Part, python, estimate, preflight, writer,
                          work)

    _fault_section(FreeCAD, python, runner, writer, doc, ana, solver, work)
    _review_fix_section(FreeCAD, Part, python, runner, writer, patch_tpl,
                        work)


def _refined_price_checks(FreeCAD, Part, python, estimate, preflight, writer,
                          work):
    """E, the v1.14.0 review's follow-up: a LOCALLY REFINED model is priced
    at its refined grid, not at the bounding-box floor at the global cell.

    The forum's own 18 mm tube with a 1.2 mm wall, 1450 mm long, swept
    80-120 MHz at MeshResolution 20: the global cell is 125 mm, so the whole
    grid of that floor is ~13 x 13 x 24 — while the deck refines the wall
    to one cell across it, and its 1.2 mm lines set the timestep.
    """
    import subprocess

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs
    from emstudio.solvers.base import foreign_python_env

    V = FreeCAD.Vector
    doc = FreeCAD.newDocument("pflive_refined")
    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = "80e6 Hz"
    ana.FrequencyStop = "120e6 Hz"
    ana.FrequencyPoints = 41
    ana.MeshResolution = 20
    tube = doc.addObject("Part::Feature", "Tube")
    tube.Shape = Part.makeCylinder(9.0, 1450.0).cut(
        Part.makeCylinder(7.8, 1450.0))
    tube.Label = "Radiator tube"
    feed = doc.addObject("Part::Feature", "FeedLine")
    feed.Shape = Part.makeLine(V(9.0, 0, 725.0), V(24.0, 0, 725.0))
    port = ports_mod.makeLumpedPort(doc, ana, name="P1", direction="+X")
    port.References = [(feed, "Edge1")]
    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    mat = material_mod.makeMaterial(doc, ana, name="TubePEC",
                                    category="Metal (PEC)")
    mat.References = [(tube, "")]
    doc.recompute()

    t0 = time.time()
    # (getattr: on a tree without the count this is a FAIL line, never a
    # traceback that hides every check after it)
    why = ""
    try:
        grid = (writer.grid_estimate(ana, solver)
                if hasattr(writer, "grid_estimate") else None)
    except Exception as exc:                               # noqa: BLE001
        grid, why = None, "grid_estimate raised %r" % (exc,)
    dt = time.time() - t0
    # What write_deck ITSELF budgets, captured from inside it: the floor
    # _budget_refinement returns is the grid the writer refuses on.
    seen = []
    real_budget = writer._budget_refinement

    def _spy(*a, **k):
        out = real_budget(*a, **k)
        seen.append(out)
        return out
    writer._budget_refinement = _spy
    d_e = os.path.join(work, "e_refined")
    os.makedirs(d_e)
    try:
        deck, _z, _n = writer.write_deck(ana, solver, d_e)
    finally:
        writer._budget_refinement = real_budget
    deck_floor = tuple(seen[-1][3]) if seen else None
    check("the estimate's count of the REFINED grid is the floor write_deck "
          "itself budgets, line for line %r vs %r (counted in %.2f s, "
          "nothing written)" % ((grid or {}).get("lines"), deck_floor, dt),
          bool(grid) and grid["lines"] == deck_floor and grid["refined"] >= 1,
          why)
    floor = preflight.grid_lower_bound(ana, solver)
    cells_r = 1.0
    for n in (grid or {}).get("lines", (0, 0, 0)):
        cells_r *= n
    cells_f = float(floor["lines"][0] * floor["lines"][1] * floor["lines"][2])
    w = estimate.work_of(ana, solver)
    want = (cells_r * max(grid["extent_mm"]) / grid["min_cell_mm"]
            if grid else -1.0)
    w_floor = cells_f * max(floor["lines"])
    check("the pre-solve estimate PRICES that refined grid — %.0f cells, not "
          "the bounding-box floor's %.0f — with the timestep its finest "
          "(%.3g mm) lines set: %.3g, %d history buckets above the floor's"
          % (cells_r, cells_f, (grid or {}).get("min_cell_mm", 0), w,
             estimate.bucket_of(w) - estimate.bucket_of(w_floor)),
          abs(w / want - 1.0) < 1e-9 and cells_r > 2.0 * cells_f
          and estimate.bucket_of(w) - estimate.bucket_of(w_floor) >= 5)
    # Honest, not just bigger: a true FLOOR of the grid openEMS is handed —
    # the deck's own grid line, printed by its --preview.
    real = None
    if deck:
        r = subprocess.run([python, deck, "--preview"], cwd=d_e,
                           capture_output=True, text=True, timeout=600,
                           env=foreign_python_env(dict(os.environ)))
        m = _GRID_RE.search((r.stdout or "") + (r.stderr or ""))
        real = tuple(int(m.group(k)) for k in (1, 2, 3)) if m else None
    check("...and that count is a true floor of the deck's own grid, within "
          "10 %% on every axis %r vs %r" % ((grid or {}).get("lines"), real),
          bool(grid) and real is not None
          and all(0.9 * b <= a <= b for a, b in zip(grid["lines"], real)))
    FreeCAD.closeDocument(doc.Name)


def _dipole(FreeCAD, Part, name, mr, with_line):
    """The review's dipole: 2-3 GHz, two 2 x 2 x 28 mm PEC arms fed across a
    2 mm gap — plus, ``with_line``, an 8 m construction line in its PEC."""
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    V = FreeCAD.Vector
    doc = FreeCAD.newDocument(name)
    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = "2e9 Hz"
    ana.FrequencyStop = "3e9 Hz"
    ana.FrequencyPoints = 11
    ana.MeshResolution = mr
    feed = doc.addObject("Part::Feature", "FeedLine")
    feed.Shape = Part.makeLine(V(0, 0, -1), V(0, 0, 1))
    port = ports_mod.makeLumpedPort(doc, ana, name="P1", direction="+Z")
    port.References = [(feed, "Edge1")]
    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    arm1 = doc.addObject("Part::Feature", "Arm1")
    arm1.Shape = Part.makeBox(2, 2, 28, V(-1, -1, 1))
    arm2 = doc.addObject("Part::Feature", "Arm2")
    arm2.Shape = Part.makeBox(2, 2, 28, V(-1, -1, -29))
    refs = [(arm1, ""), (arm2, "")]
    if with_line:
        line = doc.addObject("Part::Feature", "GuideLine")
        line.Label = "Construction line"
        line.Shape = Part.makeLine(V(0, 0, 0), V(8000, 8000, 8000))
        refs.append((line, ""))
    mat = material_mod.makeMaterial(doc, ana, name="M",
                                    category="Metal (PEC)")
    mat.References = refs
    doc.recompute()
    return doc, ana, solver


def _wire_floor_checks(FreeCAD, Part, preflight, writer, work):
    """B, the v1.14.0 review's false refusal: the floor and the model agree."""
    doc0, ana0, s0 = _dipole(FreeCAD, Part, "pflive_dip0", 20, False)
    doc1, ana1, s1 = _dipole(FreeCAD, Part, "pflive_dip1", 20, True)
    f0 = preflight.grid_lower_bound(ana0, s0)
    f1 = preflight.grid_lower_bound(ana1, s1)
    msg = ""
    d_w = os.path.join(work, "b_wire")
    os.makedirs(d_w)
    try:
        deck, _z, _n = writer.write_deck(ana1, s1, d_w)
    except writer.OpenEMSModelError as exc:
        deck, msg = None, str(exc)
    check("a dipole whose PEC also references an 8 m construction LINE is "
          "NOT refused at MeshResolution 20: the floor is the dipole's "
          "alone %r, as without the line %r"
          % ((f1 or {}).get("lines"), (f0 or {}).get("lines")),
          deck is not None and bool(f0) and bool(f1)
          and f1["lines"] == f0["lines"], msg[:100])
    notes = writer.deck_model_notes(deck) if deck else []
    check("...and the deck carries the WARNING that the line is NOT in the "
          "model", any(lvl == "warning" and "'Construction line'" in t
                       and "NOT in the model" in t for lvl, t in notes),
          notes[:1])
    # A GENUINELY over-limit grid (MeshResolution 3000) with the same line:
    # the refusal stands, and the line's WARNING is said FIRST — in the
    # Report view (captured from writer._say) and in the refusal itself.
    ana1.MeshResolution = 3000
    said = []
    real_say = writer._say
    writer._say = lambda notes: said.extend(notes or ())
    d_w2 = os.path.join(work, "b_wire_big")
    os.makedirs(d_w2)
    msg2 = ""
    try:
        writer.write_deck(ana1, s1, d_w2)
    except writer.OpenEMSModelError as exc:
        msg2 = str(exc)
    finally:
        writer._say = real_say
    check("over the index limit it IS refused, and the dropped line's "
          "WARNING is said BEFORE the refusal (Report view) and carried in "
          "it", msg2.startswith("EMStudio: REFUSED")
          and any("'Construction line'" in n and n.startswith(
              "EMStudio: WARNING") for n in said)
          and "NOT in the model: " in msg2 and "'Construction line'" in msg2,
          msg2[-110:])
    for d in (doc0, doc1):
        FreeCAD.closeDocument(d.Name)


#: A stand-in deck for the runner tests that need no FDTD: it writes the
#: CSVs a real deck writes, says what a real deck says, and exits 0 — which is
#: exactly what an openEMS run that DROPPED its port looks like from outside.
_FAKE_DECK = r'''
import os, sys
import numpy as np
here = os.path.dirname(os.path.abspath(__file__))
f = np.linspace(2.0e9, 3.0e9, 11)
s11 = np.full(f.shape, 0.2 + 0.1j)
zin = 50.0 * (1 + s11) / (1 - s11)
bad = {bad!r}
if bad == "all":
    s11 = s11 * np.nan
    zin = zin * np.nan
elif bad == "one":
    s11[4] = np.nan
np.savetxt(os.path.join(here, "port_{nr}.csv"),
           np.column_stack([f, zin.real, zin.imag, s11.real, s11.imag,
                            np.full_like(f, 50.0)]),
           delimiter=",", header="freq_hz,re_zin,im_zin,re_s11,im_s11,z0",
           comments="")
if {s21!r}:
    s21 = np.full(f.shape, 0.05 + 0j) * (np.nan if bad == "s21" else 1.0)
    np.savetxt(os.path.join(here, "sparam_{other}_{nr}.csv"),
               np.column_stack([f, s21.real, s21.imag]), delimiter=",",
               header="freq_hz,re_s,im_s", comments="")
print("EMStudio: openEMS deck finished OK", flush=True)
'''


def _fault_section(FreeCAD, python, runner, writer, doc, ana, solver, work):
    """F. A port openEMS did not place, or a result that is not a number, is a
    FAILED run — never "finished OK".

    openEMS treats a lumped element it cannot snap to the grid as a WARNING:
    it skips it, exits 0, and the deck writes an all-NaN port file, which
    SweepResult.load_csv used to accept (the forum J-pole, 2026-10-17).
    """
    from emstudio.objects import ports as ports_mod
    from emstudio.solvers.base import SolverError

    real_write = runner.writer.write_deck

    def through_runner(deck_text, tag, full=False, fake=None):
        """runner.run with write_deck swapped for one that returns
        ``deck_text`` (or, with ``fake``, a per-excitation stand-in)."""
        state = {}

        def write(analysis, solv, workdir, excite_port=None):
            nr = int(excite_port or 1)
            text = fake(nr) if fake else deck_text
            p = os.path.join(workdir, "case_openems.py")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p, 50.0, nr
        seen = []
        runner.writer.write_deck = write
        t0 = time.time()
        try:
            state["res"] = runner.run(ana, solver,
                                      workdir=os.path.join(work, "f_" + tag),
                                      line_callback=seen.append,
                                      full_smatrix=full)
        except SolverError as exc:
            state["err"] = str(exc)
        except Exception as exc:                           # noqa: BLE001
            # Anything else escaping the runner is itself a failure of the
            # contract (a NaN must arrive as a SolverError): recorded so the
            # check says so, instead of the gate dying on it.
            state["err"] = "NOT a SolverError: %r" % (exc,)
        finally:
            runner.writer.write_deck = real_write
        state["dt"] = time.time() - t0
        state["seen"] = seen
        state["files"] = sorted(os.listdir(os.path.join(work, "f_" + tag)))
        return state

    # A real deck of this model, capped at 1000 steps (section C's settings).
    d_f = os.path.join(work, "f_deck")
    os.makedirs(d_f)
    deck_path, _z, _n = real_write(ana, solver, d_f)
    with open(deck_path, encoding="utf-8") as fh:
        good = fh.read()
    port_re = re.compile(r"AddLumpedPort\(1, 50, \[[^]]*\], \[[^]]*\]")
    if not port_re.search(good):
        check("F. the patch deck carries the expected lumped port line", False)
        return

    # 1. REAL openEMS: the port squeezed into one cell — the forum failure.
    squeezed = port_re.sub("AddLumpedPort(1, 50, [-6, 0, 0.05], [-6, 0, 0.15]",
                           good)
    st = through_runner(squeezed, "squeezed")
    err = st.get("err", "")
    check("F1. a port openEMS DROPS ('snapping failed') fails the run, naming "
          "port 1 and quoting openEMS", "could not place port 1" in err
          and "snapping failed" in err, err[:110] or "it ran and returned")
    check("F2. ...and is stopped when timestepping starts: no port_1.csv was "
          "written [%.1f s]" % st["dt"], err and "port_1.csv" not in st["files"]
          and any("Running FDTD engine" in ln for ln in st["seen"]),
          st["files"])
    # 2. REAL openEMS: the port moved outside the domain. openEMS prints NO
    #    snapping line for that (Snap_Dimension -2) — only the unused-
    #    primitive summary, which is the only evidence there is.
    #    ⚠ Moved along its EXCITATION axis (z): ``edges2grid='xy'`` ADDS the
    #    port's x and y as grid lines, so a port moved out along x simply
    #    drags the domain out to meet it (measured: it then runs).
    outside = port_re.sub("AddLumpedPort(1, 50, [-6, 0, 500], [-6, 0, 501.524]",
                          good)
    st = through_runner(outside, "outside")
    err = st.get("err", "")
    check("F3. a port outside the domain (only 'Unused primitive ... "
          "port_excite_1' says so) fails the run, naming port 1",
          "could not place port 1" in err and "Unused primitive" in err
          and "snapping failed" not in err, err[:110] or "it ran and returned")
    # CONTROL: the unedited deck through the very same path runs.
    st = through_runner(good, "good")
    res = st.get("res")
    check("F4. CONTROL: the unedited deck through the same path returns a "
          "result", res is not None, st.get("err", "")[:110])

    # 3. The NaN file itself (no FDTD needed): what a dropped port leaves.
    def fake(bad, s21=False):
        return lambda nr: _FAKE_DECK.format(
            bad=bad if nr == 1 or bad == "exc2" else "",
            nr=nr, s21=s21, other=2 if nr == 1 else 1)
    st = through_runner(None, "nan_all", fake=fake("all"))
    err = st.get("err", "")
    check("F5. an all-NaN port_1.csv behind 'openEMS deck finished OK' is a "
          "failed run, naming port 1", "port 1" in err and "not a number" in err
          and "s11 at 11 of 11" in err, err[:110] or "it LOADED")
    st = through_runner(None, "nan_one", fake=fake("one"))
    err = st.get("err", "")
    check("F6. ...and so is ONE NaN sample (s11 at 1 of 11, first at 2.4 GHz)",
          "the result for port 1" in err
          and "s11 at 1 of 11 points, first at 2.4e+09 Hz" in err,
          err[:110] or "it LOADED")
    st = through_runner(None, "nan_ok", fake=fake(""))
    res = st.get("res")
    import numpy as np
    check("F7. CONTROL: the same stand-in with finite numbers loads (11 points)",
          res is not None and len(res.freq) == 11
          and bool(np.all(np.isfinite(res.s11))), st.get("err", "")[:110])
    st = through_runner(None, "nan_s21", fake=fake("s21", s21=True))
    err = st.get("err", "")
    check("F8. a NaN transmission column (sparam_2_1.csv) fails the run, "
          "naming S21", "S21" in err and "not a number" in err,
          err[:110] or "it LOADED")
    # FullSMatrix: the second excitation's own file is NaN.
    p2 = ports_mod.makeLumpedPort(doc, ana, name="P2", direction="+Z")
    p2.PortNumber = 2
    p2.Excited = False
    p2.References = list(_port_refs(ana))
    doc.recompute()
    st = through_runner(None, "nan_exc2", full=True,
                        fake=lambda nr: _FAKE_DECK.format(
                            bad="all" if nr == 2 else "", nr=nr, s21=False,
                            other=1))
    err = st.get("err", "")
    check("F9. FullSMatrix: a NaN port_2.csv from the excitation of port 2 "
          "fails the run, naming that excitation",
          "port 2 (excitation of port 2)" in err and "not a number" in err,
          err[:110] or "it LOADED")
    doc.removeObject(p2.Name)
    doc.recompute()
    # A fault in a run that ended ON ITS OWN (exit 0, no "Running FDTD
    # engine" to stop it at — an openEMS that words its banner differently)
    # must still fail: the after-the-run check, not the abort, catches it.
    tail = ('\nprint("Operator::Calc_LumpedElements(): Warning: Lumped Element '
            'snapping failed! Dimension is: 0 skipping.  ID: 6 @ Property: '
            'port_resist_1", flush=True)\n')
    st = through_runner(None, "fault_noabort",
                        fake=lambda nr: _FAKE_DECK.format(
                            bad="", nr=nr, s21=False, other=2) + tail)
    err = st.get("err", "")
    check("F13. a dropped port in a run that finished by itself (exit 0, no "
          "engine banner) still fails, naming port 1",
          "could not place port 1" in err, err[:110] or "it ran and returned")
    setup = '\nprint("Run: Setup failed, error code: 2", flush=True)\n'
    st = through_runner(None, "setup_failed",
                        fake=lambda nr: _FAKE_DECK.format(
                            bad="", nr=nr, s21=False, other=2) + setup)
    err = st.get("err", "")
    check("F14. openEMS's 'Run: Setup failed' (after which the deck carries "
          "on) fails the run", "openEMS setup failed" in err,
          err[:110] or "it ran and returned")

    # 4. The watch's reading of openEMS, deterministic (no FDTD).
    lumped = ("Operator::Calc_LumpedElements(): Warning: Lumped Element "
              "snapping failed! Dimension is: 0 skipping.  ID: 6 @ Property: "
              "port_resist_1")
    w = runner._DeckWatch(None)
    for ln in (lumped,
               "Warning: Unused primitive (type: Box) detected in property: "
               "port_excite_3!",
               "Warning: Unused primitive (type: Box) detected in property: "
               "port_ut_2A!",
               "Operator::Calc_LumpedElements(): Warning: Lumped Element with "
               "zero (snapped) length is invalid! skipping.  ID: 9 @ Property: "
               "port_resist_4"):
        w(ln)
    check("F10. the watch names the port in each openEMS form (resist 1, "
          "excite 3, MSL probe 2A, zero-length 4)",
          [nr for nr, _ in w.port_faults] == [1, 3, 2, 4], w.port_faults)
    w = runner._DeckWatch(None)
    w("Warning: Unused primitive (type: Box) detected in property: "
      "mat1_PEC!")
    w("Warning: Unused primitive (type: Box) detected in property: Ef_fd!")
    check("F11. CONTROL: an unused METAL or dump primitive is not a port "
          "fault", w.port_faults == [] and w.fault_error() is None,
          w.port_faults)

    class _Job(object):
        aborted = 0

        def abort(self):
            self.aborted += 1
    w, j = runner._DeckWatch(None), _Job()
    w.job = j
    w(lumped)
    w("Running FDTD engine... this may take a while... grab a cup of coffee?!?")
    w2, j2 = runner._DeckWatch(None), _Job()
    w2.job = j2
    w2("Running FDTD engine... this may take a while... grab a cup of coffee?!?")
    check("F12. a faulted run is aborted when timestepping starts; a healthy "
          "one is not (CONTROL)", j.aborted == 1 and j2.aborted == 0
          and w.stopped_for_fault and not w2.stopped_for_fault,
          (j.aborted, j2.aborted))


def _wr28(FreeCAD, Part, doc, f1, f2):
    """The v1.14.0 review's WR-28 probe: a 20 mm PEC section of WR-28 (the
    shipped horn's feed), a RectWaveguide TE10 port 2 mm in, 25 samples."""
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
    solver.MaxTimesteps = 20000
    doc.recompute()
    return ana, solver


#: A stand-in deck for G (no FDTD): writes port_<nr>.csv over the WR-28
#: probe's own 25 samples with S11 / z0 NaN where ``bad`` (a numpy mask
#: expression in ``f``) says — what a deck that KEPT the below-cut-off
#: samples leaves — and, with ``notes``, carries a model-notes block.
_G_FAKE = r'''
import os
import numpy as np
here = os.path.dirname(os.path.abspath(__file__))
{notes}
{nrts}
f = np.linspace({f1!r}, {f2!r}, 25)
s11 = np.full(f.shape, 0.2 + 0.1j)
z0 = np.full(f.shape, 500.0)
bad = {bad}
s11[bad] = np.nan
z0[bad] = np.nan
zin = 500.0 * (1 + 0.2 + 0.1j) / (1 - 0.2 - 0.1j) + 0 * f
np.savetxt(os.path.join(here, "port_{nr}.csv"),
           np.column_stack([f, zin.real, zin.imag, s11.real, s11.imag, z0]),
           delimiter=",", header="freq_hz,re_zin,im_zin,re_s11,im_s11,z0",
           comments="")
print("EMStudio: openEMS deck finished OK", flush=True)
'''


def _review_fix_section(FreeCAD, Part, python, runner, writer, patch_tpl,
                        work):
    """G. The v1.14.0 review fixes that only a run through the product
    runner can prove: a WAVEGUIDE band that starts below cut-off, the
    deck's model notes in the result, and an openEMS probe that no longer
    crashes the binary."""
    import numpy as np

    from emstudio.objects import ports as ports_mod
    from emstudio.solvers.base import SolverError

    real_write = runner.writer.write_deck

    def run(ana, solver, tag, fake=None, full=False):
        """runner.run — with ``fake(nr)`` (a stand-in deck's text) in place
        of write_deck when given. Returns (result or None, error text)."""
        if fake is not None:
            def write(analysis, solv, workdir, excite_port=None):
                nr = int(excite_port or 1)
                p = os.path.join(workdir, "case_openems.py")
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(fake(nr))
                return p, 50.0, nr
            runner.writer.write_deck = write
        try:
            return runner.run(ana, solver,
                              workdir=os.path.join(work, "g_" + tag),
                              full_smatrix=full), ""
        except SolverError as exc:
            return None, str(exc)
        except Exception as exc:                           # noqa: BLE001
            return None, "NOT a SolverError: %r" % (exc,)
        finally:
            runner.writer.write_deck = real_write

    # -- G1. the review's own case, REAL openEMS through the product runner --
    # WR-28 swept 18-30 GHz: openEMS's waveguide port is NaN in the 7
    # samples 18-21 GHz (TE10 cut-off 21.08 GHz) and finite in the other
    # 18. Since v1.14.0's NaN refusal the whole run was thrown away and
    # blamed on a port "never in the simulation" (review, reproduced).
    doc = FreeCAD.newDocument("pflive_wg")
    ana, solver = _wr28(FreeCAD, Part, doc, "18 GHz", "30 GHz")
    res, err = run(ana, solver, "wr28")
    want = np.linspace(18e9, 30e9, 25)[7:]
    notes = list((res.meta.get("notes") if res is not None else None) or [])
    check("G1. WR-28 swept 18-30 GHz through the REAL runner returns the 18 "
          "samples above the 21.08 GHz cut-off (21.5-30 GHz, exactly the "
          "sweep's own), every S11 and z0 finite",
          res is not None and len(res.freq) == 18
          and np.array_equal(np.asarray(res.freq), want)
          and bool(np.all(np.isfinite(res.s11)))
          and bool(np.all(np.isfinite(res.z0_f))),
          err[:110] or "%d samples" % len(res.freq))
    check("G2. ...and the result itself carries the writer's NOTE naming the "
          "cut-off and the 7 samples left out (result.meta['notes'], what "
          "the results dialog shows)",
          any("cut-off of 21.08 GHz" in n and "the 7 frequency sample(s)" in n
              for n in notes), notes[:1] or err[:80])

    # -- G3. the runner's backstop: a deck that KEPT those samples ----------
    def wg_fake(bad):
        return lambda nr: _G_FAKE.format(notes="", nrts="", f1=18e9, f2=30e9,
                                         bad=bad, nr=nr)
    res, err = run(ana, solver, "wr28_kept",
                   fake=wg_fake("f <= 21.0e9 + 1.0"))
    check("G3. a deck that KEPT the below-cut-off samples (NaN 18-21 GHz) is "
          "refused as BELOW CUT-OFF, naming the 21.08 GHz TE10 cut-off of "
          "port 1 — never as a port 'never in the simulation'",
          res is None and "21.08 GHz" in err and "cut-off" in err
          and "TE10" in err and "never in the simulation" not in err,
          err[:110] or "it LOADED")
    res, err = run(ana, solver, "wr28_hole",
                   fake=wg_fake("np.isclose(f, 25e9)"))
    check("G4. CONTROL: a NaN ABOVE cut-off (25 GHz) on the same model is "
          "still the dropped-port error, not explained away as a cut-off",
          res is None and "never in the simulation" in err
          and "cut-off" not in err, err[:110] or "it LOADED")
    FreeCAD.closeDocument(doc.Name)

    # -- G5. the deck's model notes reach result.meta (F-a) ------------------
    # O2's notes channel (writer.deck_model_notes) existed, but the runner
    # never copied it into the result, so the results dialog — which shows
    # meta['warnings'] / ['notes'] beside the plots — never saw a dropped
    # part, an STL defect or a port in air. FullSMatrix: every excitation's
    # deck carries the same notes, and the result must carry them ONCE.
    doc = FreeCAD.newDocument("pflive_notes")
    ana = patch_tpl.makePatch(doc)
    solver = _solver(ana)
    p2 = ports_mod.makeLumpedPort(doc, ana, name="P2", direction="+Z")
    p2.PortNumber = 2
    p2.Excited = False
    p2.References = list(_port_refs(ana))
    doc.recompute()
    w_txt = "EMStudio: WARNING - stand-in model warning (gate G5)"
    n_txt = "EMStudio: NOTE - stand-in model note (gate G5)"
    block = "\n".join([writer.MODEL_NOTES_MARK + " (gate G5)",
                       "print({0!r}, flush=True)".format(w_txt),
                       "print({0!r}, flush=True)".format(n_txt), ""])
    # openEMS's own "ran all NrTS" line (run 1 only): the runner's own NOTE
    # (_note_capped) must stay FIRST, the deck's model notes after it.
    nrts = ('print("EMStudio: starting openEMS run (NrTS=1000, '
            'EndCriteria=1e-05)...", flush=True)\nprint("Max. number of '
            'timesteps was reached before the end-criteria of -50dB was '
            'reached...", flush=True)')

    def notes_fake(nr):
        return _G_FAKE.format(notes=block, nrts=nrts if nr == 1 else "",
                              f1=2.0e9, f2=3.0e9, bad="f < 0", nr=nr)
    res, err = run(ana, solver, "notes", fake=notes_fake, full=True)
    meta = res.meta if res is not None else {}
    ws, ns = meta.get("warnings") or [], meta.get("notes") or []
    check("G5. the deck's model WARNING and NOTE reach result.meta "
          "['warnings'] / ['notes'] word for word, ONCE although both "
          "excitation decks of the FullSMatrix run carry them",
          res is not None and ws.count(w_txt) == 1 and ns.count(n_txt) == 1,
          err[:110] or (ws, ns))
    check("G6. ...after the runner's own timestep NOTE, which stays first",
          len(ns) >= 2 and "timesteps" in ns[0] and ns.index(n_txt) > 0, ns)
    res, err = run(ana, solver, "nonotes",
                   fake=lambda nr: _G_FAKE.format(
                       notes="", nrts="", f1=2.0e9, f2=3.0e9, bad="f < 0",
                       nr=nr))
    meta = res.meta if res is not None else {"x": 1}
    check("G7. CONTROL: a deck with no notes adds neither key (the results "
          "dialog then shows nothing extra)", res is not None
          and "warnings" not in meta and "notes" not in meta,
          err[:110] or sorted(meta))
    FreeCAD.closeDocument(doc.Name)

    # -- G8. the openEMS version probe no longer crashes openEMS (F-b) -------
    # "openEMS --version" is an unknown option to v0.37's program_options:
    # banner, then an uncaught throw -> SIGABRT, and systemd-coredump kept
    # one core per Detect Solvers / gate run (hundreds in the v1.14.0 gate
    # runs). Run here with RLIMIT_CORE = 1 BYTE, so even a regression adds
    # no core (0 would not: this box's core_pattern overrides it).
    from emstudio.setup import solvers as solver_setup
    info = solver_setup.find_backend("openems")
    args = list(solver_setup.BACKENDS["openems"].version_args)
    if not info.found:
        check("G8. the openEMS binary is found for the probe check", False)
        return
    if os.name == "nt":
        rc = subprocess.run([info.path] + args, capture_output=True,
                            timeout=30).returncode
        # MSVC abort(): exit 3, or the fail-fast status 0xC0000409.
        crashed = rc in (3, 0xC0000409, -1073740791)
    else:
        launcher = ("import os, resource, sys; "
                    "resource.setrlimit(resource.RLIMIT_CORE, (1, 1)); "
                    "os.execv(sys.argv[1], sys.argv[1:])")
        rc = subprocess.run([python, "-c", launcher, info.path] + args,
                            capture_output=True, timeout=30).returncode
        crashed = rc < 0                    # killed by a signal (SIGABRT -6)
    # (find_backend has just probed it with these very arguments: its
    # .version IS what Solver Setup shows.)
    ver = info.version
    check("G8. the openEMS version probe (%s) exits normally (rc %d), not "
          "by a crash" % (" ".join(args), rc), not crashed, rc)
    check("G9. ...and still reports the banner's version line, never help "
          "text [%s]" % ver, ver.startswith("| openEMS")
          and " -- version v" in ver
          and solver_setup.version_number(ver) != "", ver)


def _port_refs(ana):
    """The patch template's own port reference, reused for a second port."""
    for o in ana.Group:
        if getattr(o, "EMStudioType", "") == "EMStudio::LumpedPort":
            return o.References
    return []


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    _rc = main()
    sys.exit(_rc)
