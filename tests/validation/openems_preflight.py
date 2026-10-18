#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""FAST gate — the openEMS grid preflight: refuse with numbers, never a signal.

The defect this pins
--------------------
A forum user (macOS arm64, FreeCAD 1.1.4, 2026-10) followed an EMStudio
refusal to "raise MeshResolution", set 2700, and the deck built a 1724 x 1666
x 3283 = 9,429,380,072-cell grid. openEMS sizes its operator arrays in 32 bits,
so the size wrapped; it printed "Create FDTD operator" and the run ended
"python exited with code -11". Nothing had counted the cells first, and the
only thing the user was told was a signal number — which is not even stable:
the same deck ends -11, -6, -9 or exit 1 depending on OS, memory caps and
openEMS version.

What is pinned (pure python — no FreeCAD, no openEMS, a second or two)
---------------------------------------------------------------------
1. the ABSOLUTE index limit, at (2^32 - 1) // 3 = 1,431,655,765 cells (the
   3-component ArrayNIJK wrap — the lower of openEMS's two 32-bit bounds),
   with a case inside the 1.43e9-4.29e9 window so the choice of bound is a
   decision this gate enforces, not an accident; no override reaches it;
2. the RAM branch: 80 MB + 125 B/cell against 0.8 x physical RAM — refuse,
   pass, skip-when-unknown, and the override lifting THIS branch only;
3. the physical-RAM reader, on this platform, against an independent source
   where the platform has one;
4. the DECK code itself, executed: the exact lines the writer pastes, run
   against a fake grid — the grid line always prints, an over-limit grid
   raises SystemExit with the numbers, --preview only warns;
5. the writer's LOWER BOUND, on duck-typed stand-ins for the document
   objects: it never exceeds the grid it bounds, and it refuses the forum
   grid before a single STL could be written; and it counts only what the
   MODEL holds, through the same reference classification — a wire-only
   reference (an 8 m construction line) is left out and REPORTED (v1.14.0
   review: the floor once kept it and refused a 16,758-cell dipole);
6. the solver-process plumbing in solvers/base.py: a deck's REFUSED line
   becomes the error's headline, a crash's grid line survives the tail, and a
   host PYTHONHOME is scrubbed for a foreign python — proven with a REAL
   child that dies of exactly the AppImage's "No module named encodings"
   when the scrub is skipped (the negative control).

The live half — real decks, real openEMS — is preflight_live_openems (SOLVER).

Mutations proven to fail this gate (2026-10-17): the limit at (2^33-1)//3;
the 0.8 dropped from the RAM test; the RAM reader returning None; the
REFUSED-line lift removed from base.py; the PYTHONHOME scrub removed;
the floor's parts re-derived from resolved_references (v1.14.0 review).
"""

from __future__ import annotations

import io
import math
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

FAILURES = []


def check(msg, ok, detail=""):
    # One line per check, always: a multi-line detail (a child's traceback)
    # would put text on lines the battery's check counter then has to parse.
    detail = " | ".join(str(detail).split("\n")) if detail else ""
    print(("  ok   " if ok else "  FAIL ") + msg
          + (("   [" + detail[:150] + "]") if detail else ""))
    if not ok:
        FAILURES.append(msg)


def _load_preflight():
    """The module, loaded through the same FreeCAD-free route the product uses.

    ``from emstudio.solvers.openems import preflight`` cannot work here: the
    package __init__ imports the runner -> writer -> ``import FreeCAD``.
    """
    from emstudio.solvers import estimate
    return estimate.openems_preflight()


# --- duck-typed stand-ins for the FreeCAD document objects -----------------
class _BB(object):
    def __init__(self, lo, hi):
        self.XMin, self.YMin, self.ZMin = lo
        self.XMax, self.YMax, self.ZMax = hi


class _Shape(object):
    """A Part shape as the shared classification reads it.

    ``kind`` "solid" carries one solid and its faces, "wire" none of either
    (a Part::Line, a sketch, an edges-only shape) — what
    query.reference_leaves keys on. ⚠ The topology is load-bearing since
    the v1.14.0 review: the writer's floor reads the parts through that
    SAME call (it once re-derived "what counts" and kept wire-only
    references the model drops), so a stand-in without it would be read as
    a wire and dropped — the bare-Edge check below passing for the wrong
    reason.
    """

    def __init__(self, lo, hi, kind="solid"):
        self.BoundBox = _BB(lo, hi)
        self.Solids = [self] if kind == "solid" else []
        self.Faces = [self] * 6 if kind == "solid" else []

    def isNull(self):
        return False

    def getElement(self, sub):
        # An element spans its parent (a FLOOR is safe), and an EDGE or a
        # VERTEX is a wire: no face, no solid.
        kind = "wire" if sub.startswith(("Edge", "Vertex")) else "solid"
        return _Shape((self.BoundBox.XMin, self.BoundBox.YMin,
                       self.BoundBox.ZMin),
                      (self.BoundBox.XMax, self.BoundBox.YMax,
                       self.BoundBox.ZMax), kind)


class _Obj(object):
    def __init__(self, lo, hi, kind="solid", label="Obj"):
        self.Shape = _Shape(lo, hi, kind)
        self.Label = label


class _Q(object):
    def __init__(self, hz):
        self._hz = float(hz)

    def getValueAs(self, unit):
        assert unit == "Hz"
        return self._hz


class _Mat(object):
    EMStudioType = "EMStudio::Material"

    def __init__(self, refs):
        self.References = refs


class _Port(object):
    EMStudioType = "EMStudio::LumpedPort"

    def __init__(self, ptype="Lumped", nr=1):
        self.PortType = ptype
        self.PortNumber = nr


class _Analysis(object):
    def __init__(self, members, f1, f2, mr, pad=0.25):
        self.Group = members
        self.FrequencyStart = _Q(f1)
        self.FrequencyStop = _Q(f2)
        self.MeshResolution = mr
        self.DomainPaddingWavelengths = pad
        self.FrequencyPoints = 201


class _FakeMesh(object):
    """Only what the deck call touches: GetLines on 'x', 'y', 'z'."""

    def __init__(self, nx, ny, nz):
        self._n = {"x": nx, "y": ny, "z": nz}

    def GetLines(self, a):
        return [float(i) for i in range(self._n[a])]


def _exec_deck(pf, lines, preview=False, environ=None):
    """Run the EXACT deck lines the writer pastes. Returns (stdout, exit msg)."""
    src = "\n".join(pf.deck_lines())
    ns = {"__name__": "__deck__", "os": os, "sys": sys,
          "mesh": _FakeMesh(*lines), "mesh_res": 0.925,
          "preview_only": preview}
    buf = io.StringIO()
    exit_msg = None
    saved = dict(os.environ)
    try:
        if environ is not None:
            os.environ.clear()
            os.environ.update(environ)
        with redirect_stdout(buf):
            try:
                exec(compile(src, "<deck preflight>", "exec"), ns)
            except SystemExit as exc:
                exit_msg = str(exc)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return buf.getvalue(), exit_msg


def main():
    print("EMStudio openEMS grid-preflight gate (pure)")
    pf = _load_preflight()

    # == 1. the absolute index limit ========================================
    lim = pf.OPENEMS_MAX_CELLS
    check("the index limit is (2^32 - 1) // 3 = 1,431,655,765 cells [%d]" % lim,
          lim == 1431655765 == (2 ** 32 - 1) // 3)
    # Exact counts by factorisation: 2 x 2 x 357,913,941 = limit - 1, and
    # 5 x 1 x 286,331,153 = the limit itself.
    below, at = (2, 2, 357913941), (5, 1, 286331153)
    check("1,431,655,764 cells is ALLOWED (unknown RAM)",
          pf.cell_count(below) == lim - 1
          and pf.refusal(below, 1.0, None) is None)
    msg = pf.refusal(at, 1.0, None) or ""
    check("1,431,655,765 cells is REFUSED", pf.cell_count(at) == lim
          and msg.startswith("EMStudio: REFUSED"), msg[:90])
    check("...and the refusal states the cell count and 'cannot index'",
          "1,431,655,765 cells;" in msg and "cannot index" in msg)
    # The deliberate choice: openEMS's default engine is bound by 2^32, its
    # 3-component arrays by 2^32/3. A grid between the two must be refused,
    # or the bound has quietly become the weaker one.
    window = (2000, 1000, 1000)
    check("a 2.0e9-cell grid (inside the 1.43e9..4.29e9 window) is REFUSED",
          bool(pf.refusal(window, 1.0, None)))
    nett = (1724, 1666, 3283)
    msg = pf.refusal(nett, 0.925, 32e9) or ""
    check("the forum grid 1724 x 1666 x 3283 is REFUSED with its numbers",
          "1724 x 1666 x 3283" in msg and "9,429,380,072" in msg
          and "GB" in msg and "MeshResolution" in msg and "0.925 mm" in msg,
          msg[:120])
    need_gb = (80e6 + 125.0 * 9429380072) / 1e9          # 1178.8, independent
    check("...quoting ~%.0f GB of RAM" % need_gb,
          "~%.0f GB" % need_gb in msg)
    check("the index refusal has NO override (allow=True, unknown RAM, huge RAM)",
          all(pf.refusal(nett, 0.925, ram, allow=True)
              for ram in (None, 1e15)))
    check("...and the environment switch does not reach it either",
          bool(pf.refusal(nett, 0.925, None,
                          allow=pf.allow_large(
                              {"EMSTUDIO_OPENEMS_ALLOW_LARGE": "1"}))))

    # == 2. the RAM branch ==================================================
    # An 8 GB machine (8.00e9 B): the line is 0.8 x 8e9 = 6.4e9 B, i.e.
    # 80e6 + 125 N > 6.4e9  <=>  N > 50,560,000 cells.
    ram8 = 8e9
    over, under = (1000, 1000, 52), (1000, 1000, 50)     # 6.58 GB / 6.33 GB
    msg = pf.refusal(over, 2.0, ram8) or ""
    check("52 M cells on an 8 GB machine is REFUSED (6.58 GB > 0.8 x 8 GB)",
          msg.startswith("EMStudio: REFUSED"), msg[:90])
    check("...naming the cells, the GB needed and the GB present",
          "52,000,000 cells" in msg and "6.58 GB" in msg and "8.00 GB" in msg,
          msg[:160])
    check("...and how to lift it (the env switch) and what to lower",
          "EMSTUDIO_OPENEMS_ALLOW_LARGE=1" in msg and "MeshResolution" in msg)
    check("50 M cells on the same machine PASSES (6.33 GB < 6.4 GB)",
          pf.refusal(under, 2.0, ram8) is None)
    check("unknown RAM SKIPS the branch, never guesses (52 M and 1.0e9 cells)",
          pf.refusal(over, 2.0, None) is None
          and pf.refusal((1000, 1000, 1000), 2.0, None) is None)
    check("the override lifts the RAM branch",
          pf.refusal(over, 2.0, ram8, allow=True) is None)
    check("allow_large reads only an explicit yes",
          pf.allow_large({"EMSTUDIO_OPENEMS_ALLOW_LARGE": "1"})
          and pf.allow_large({"EMSTUDIO_OPENEMS_ALLOW_LARGE": " Yes "})
          and not pf.allow_large({"EMSTUDIO_OPENEMS_ALLOW_LARGE": "0"})
          and not pf.allow_large({}))

    # == 3. the RAM reader, on THIS platform ================================
    ram = pf.physical_ram_bytes()
    check("physical RAM reads as a plausible positive int on %s [%r]"
          % (sys.platform, ram),
          isinstance(ram, int) and ram > (256 << 20))
    ref, src = None, None
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/meminfo") as fh:
                for ln in fh:
                    if ln.startswith("MemTotal:"):
                        ref, src = int(ln.split()[1]) * 1024, "/proc/meminfo"
        except OSError:
            pass
    elif sys.platform == "darwin":
        try:
            ref = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"],
                                              text=True).strip())
            src = "sysctl hw.memsize"
        except (OSError, ValueError, subprocess.CalledProcessError):
            pass
    if ref:
        check("...and agrees with %s to 2 %% [%d vs %d]" % (src, ram or 0, ref),
              bool(ram) and abs(ram - ref) <= 0.02 * ref)
    else:
        print("  note no independent RAM source on %s; the read is checked "
              "for plausibility only" % sys.platform)

    # == 4. the deck lines, executed ========================================
    src = "\n".join(pf.deck_lines())
    try:
        compile(src, "<deck preflight>", "exec")
        compiled = True
    except SyntaxError as exc:
        compiled = False
        print("     %r" % (exc,))
    check("the pasted deck lines compile on their own", compiled)
    import ast
    imports = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    # The deck runs under the openEMS venv: no EMStudio, maybe no numpy yet.
    check("...and import nothing but ctypes (os/sys come from the deck) %r"
          % sorted(imports), imports <= {"ctypes"})

    out, why = _exec_deck(pf, (37, 39, 31))
    check("a small grid prints the grid line and is NOT refused",
          "EMStudio: FDTD grid 37 x 39 x 31 = 44,733 cells" in out
          and why is None, out.strip()[:110])
    out, why = _exec_deck(pf, nett)
    check("the forum grid raises SystemExit with the REFUSED message",
          bool(why) and why.startswith("EMStudio: REFUSED")
          and "9,429,380,072" in why, (why or "")[:90])
    check("...AFTER printing its grid line (cells and GB, always)",
          "EMStudio: FDTD grid 1724 x 1666 x 3283 = 9,429,380,072 cells, "
          "needs about 1179 GB" in out)
    out, why = _exec_deck(pf, nett, preview=True)
    check("--preview only WARNS (case.xml is still written for inspection)",
          why is None and "preview only" in out and "refused" in out)
    check("...in plain ASCII (a pipe on Windows is the locale's code page)",
          all(ord(c) < 128 for c in out))

    # The RAM branch inside the deck can only be exercised where its window
    # (0.8 x RAM .. the index limit) exists — every machine under ~224 GB.
    if ram:
        n_thr = (pf.OPENEMS_RAM_FRACTION * ram * 1.02
                 - pf.OPENEMS_BASE_BYTES) / pf.OPENEMS_BYTES_PER_CELL
        if n_thr < lim:
            side = int(math.ceil(n_thr ** (1.0 / 3.0)))
            big = (side, side, side)
            base_env = {k: v for k, v in os.environ.items()
                        if k != pf.OPENEMS_ALLOW_LARGE_ENV}
            _o, why = _exec_deck(pf, big, environ=base_env)
            check("the deck refuses a grid this machine cannot hold %r" % (big,),
                  bool(why) and "of RAM" in why, (why or "")[:90])
            _o, why = _exec_deck(pf, big, environ=dict(
                base_env, EMSTUDIO_OPENEMS_ALLOW_LARGE="1"))
            check("...and EMSTUDIO_OPENEMS_ALLOW_LARGE=1 in the deck's own "
                  "environment lets it through", why is None)
        else:
            print("  note this machine's RAM puts 0.8 x RAM above the index "
                  "limit; the deck-level RAM branch is unreachable here")

    # == 5. the writer's lower bound ========================================
    # nett's padded domain, 1591 x 1536 x 3030 mm at the 0.925 mm cell the
    # 2700 produced; the deck's own --preview measured 1724 x 1666 x 3283.
    lb = pf.lower_bound_lines((1591.0, 1536.0, 3030.0), 0.925)
    check("the lower bound never exceeds the measured grid on any axis %r" % (lb,),
          all(a <= b for a, b in zip(lb, nett)))
    frac = float(pf.cell_count(lb)) / 9429380072.0
    check("...and is tight enough to matter (%.1f %% of it)" % (100 * frac),
          0.90 <= frac <= 1.0)
    msg = pf.refusal(lb, 0.925, None, at_least=True) or ""
    check("...so the WRITER refuses the forum grid, saying 'at least'",
          msg.startswith("EMStudio: REFUSED") and "at least 1" in msg, msg[:80])

    # The same through grid_lower_bound on stand-ins for the document: a
    # 3 m radiator, swept 80-120 MHz (lambda_min 2.498 m), 0.25 lambda pad.
    rod = _Obj((0.0, 0.0, 0.0), (20.0, 20.0, 3000.0))
    edge = _Obj((-5000.0, -5000.0, -5000.0), (5000.0, 5000.0, 5000.0))
    mat = _Mat([(rod, ("",)), (edge, ("Edge1",))])
    ana = _Analysis([mat, _Port()], 80e6, 120e6, 20)
    g = pf.grid_lower_bound(ana, None)
    want_res = 299792458.0 / 120e6 / 1e-3 / 20
    check("grid_lower_bound uses the writer's cell, C0 / f_max / MR [%.6g mm]"
          % g["mesh_res_mm"], abs(g["mesh_res_mm"] / want_res - 1) < 1e-12)
    pad = 0.25 * 299792458.0 / 100e6 * 1000.0
    want_x = int(math.floor((20.0 + 2 * pad) / (want_res * 1.01))) + 1
    check("...pads the geometry by DomainPaddingWavelengths at f0, and "
          "IGNORES a bare Edge reference (the writer skips those) %r"
          % (g["lines"],), g["lines"][0] == want_x and not g["msl"])
    ana2 = _Analysis([mat, _Port()], 80e6, 120e6, 2700)
    g2 = pf.grid_lower_bound(ana2, None)
    msg = pf.refusal(g2["lines"], g2["mesh_res_mm"], None, at_least=True) or ""
    check("MeshResolution 2700 on that 3 m radiator is refused at the writer",
          "cannot index" in msg and "at least" in msg, msg[:80])
    ana3 = _Analysis([mat, _Port("MSL")], 80e6, 120e6, 20)
    g3 = pf.grid_lower_bound(ana3, None)
    check("a microstrip analysis (domain hugs the board) counts NO padding",
          g3["msl"] and g3["lines"][0]
          == int(math.floor(20.0 / (want_res * 1.01))) + 1)
    check("an analysis with no readable geometry gives None, not a guess",
          pf.grid_lower_bound(_Analysis([_Port()], 80e6, 120e6, 20)) is None)

    # A WIRE-ONLY whole-object reference — an 8 m construction line in the
    # same metal — is NOT in the model (the shared classification drops it
    # with a WARNING), so it must not be in the floor either. v1.14.0
    # review: the floor once re-derived "what counts" and kept it, refusing
    # a 16,758-cell dipole at "at least 4,093,427,212 cells".
    cline = _Obj((0.0, 0.0, 0.0), (8000.0, 8000.0, 8000.0), kind="wire",
                 label="Construction line")
    mat4 = _Mat([(rod, ("",)), (cline, ("",))])
    g4 = pf.grid_lower_bound(_Analysis([mat4, _Port()], 80e6, 120e6, 20))
    check("a wire-only whole-object reference (an 8 m construction line) is "
          "NOT counted: the floor is the rod's alone %r"
          % ((g4 or {}).get("lines"),),
          bool(g4) and g4["lines"] == g["lines"])
    warned = [t for _m, lvl, t in (g4 or {}).get("issues", ())
              if lvl == "warning"]
    check("...and the floor REPORTS it, as the WARNING the model pass would "
          "give (for a refusal to say first)",
          len(warned) == 1 and "'Construction line'" in warned[0]
          and "NOT in the model" in warned[0], warned[:1])
    from emstudio.objects import query
    old = [s for _o, s, sub in query.resolved_references(mat4)
           if s is not None and not sub.startswith(("Edge", "Vertex"))]
    check("CONTROL: the route the floor used to take "
          "(query.resolved_references) DOES yield the line's 8 m box",
          any(s.BoundBox.XMax >= 8000.0 for s in old))

    # == 6. solvers/base.py: the solver-process plumbing ====================
    from emstudio.solvers import base

    ex = base.describe_exit(-11)
    check("exit -11 is named: %r" % ex, "SIGSEGV" in ex and "segmentation" in ex)
    check("a Windows access violation is named: %r" % base.describe_exit(0xC0000005),
          "ACCESS_VIOLATION" in base.describe_exit(0xC0000005))
    check("an ordinary exit code is left alone", base.describe_exit(1) == "")

    host = {"PYTHONHOME": "/tmp/.mount_FreeCA/usr",
            "PYTHONPATH": os.pathsep.join(["", "/tmp/.mount_FreeCA/usr/lib",
                                           "/home/u/openems/python"]),
            "LD_LIBRARY_PATH": os.pathsep.join(["/tmp/.mount_FreeCA/usr/lib",
                                                "/opt/openEMS/lib"]),
            "APPDIR": "/tmp/.mount_FreeCA",
            "EMSTUDIO_OPENEMS_DLL_DIR": r"C:\opt\openEMS"}
    clean = base.foreign_python_env(host)
    check("foreign_python_env drops PYTHONHOME", "PYTHONHOME" not in clean)
    check("...keeps the user's own PYTHONPATH entry, drops the host's and ''",
          clean.get("PYTHONPATH") == "/home/u/openems/python")
    check("...drops only the AppImage's LD_LIBRARY_PATH entries",
          clean.get("LD_LIBRARY_PATH") == "/opt/openEMS/lib")
    check("...passes EMSTUDIO_OPENEMS_DLL_DIR through and mutates nothing",
          clean.get("EMSTUDIO_OPENEMS_DLL_DIR") == r"C:\opt\openEMS"
          and host["PYTHONHOME"] == "/tmp/.mount_FreeCA/usr")
    check("...and deletes a PYTHONPATH that was only host entries",
          "PYTHONPATH" not in base.foreign_python_env(
              {"PYTHONPATH": "", "PYTHONHOME": "/x"}))

    tmp = tempfile.mkdtemp(prefix="emstudio_pfgate_")
    py = sys.executable
    # A REAL foreign python under a poisoned PYTHONHOME — the AppImage's
    # failure, reproduced without the AppImage. Negative control first: if
    # this child does NOT die, the scrub below proves nothing.
    poison = {"PYTHONHOME": os.path.join(tmp, "no-such-python-home")}
    job = base.SolverJob([py, "-c", "print('child ok')"], cwd=tmp, env=poison)
    died = None
    try:
        job.run_blocking(timeout=60)
    except base.SolverError as exc:
        died = str(exc)
    check("NEGATIVE CONTROL: a python child given a host PYTHONHOME dies "
          "('encodings')", bool(died) and "encodings" in died,
          (died or "it ran")[-90:])
    seen = []
    job = base.SolverJob([py, "-c", "print('child ok')"], cwd=tmp, env=poison,
                         line_callback=seen.append,
                         env_filter=base.foreign_python_env)
    try:
        rc = job.run_blocking(timeout=60)
    except base.SolverError as exc:
        rc = str(exc)[-90:]
    check("...and with env_filter=foreign_python_env it runs [%r]" % (rc,),
          rc == 0 and "child ok" in seen)

    # A refused deck: grid line, 80 lines of noise, the refusal, exit 1.
    refused_line = ("EMStudio: REFUSED \u2014 grid 9 x 9 x 9 = 729 cells; "
                    "openEMS cannot index ...")
    script = os.path.join(tmp, "deck.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("import sys\n"
                 "print('EMStudio: FDTD grid 9 x 9 x 9 = 729 cells, needs "
                 "about 0.08 GB (this machine has 8.00 GB)', flush=True)\n"
                 "for i in range(80):\n"
                 "    print('Face %d: Trying reverse order... failed' % i, "
                 "flush=True)\n"
                 "if sys.argv[1] == 'refuse':\n"
                 "    raise SystemExit(" + repr(refused_line) + ")\n"
                 "sys.exit(3)\n")
    # ⚠ Matched on the ASCII parts only. The em dash crosses a pipe, and on
    # Windows the child's encoding (PYTHONIOENCODING, which run_battery sets
    # to utf-8) and the parent's locale decode can differ — the prefix the
    # lift keys on is ASCII precisely so that cannot break it.
    err = ""
    try:
        base.SolverJob([py, script, "refuse"], cwd=tmp).run_blocking(60)
    except base.SolverError as exc:
        err = str(exc)
    head = err.splitlines() if err else ["no error", ""]
    check("a deck's REFUSED line becomes the error HEADLINE",
          head[0].startswith("EMStudio: REFUSED") and "729 cells" in head[0],
          head[0][:80])
    check("...with the exit code beneath it, and not repeated in the tail",
          "exited with code 1" in head[1]
          and err.count("EMStudio: REFUSED") == 1)
    err = ""
    try:
        base.SolverJob([py, script, "crash"], cwd=tmp).run_blocking(60)
    except base.SolverError as exc:
        err = str(exc)
    check("a crash keeps the deck's GRID line though 80 lines scrolled it out",
          "exited with code 3" in err.splitlines()[0]
          and err.splitlines()[1].startswith("EMStudio: FDTD grid 9 x 9 x 9"),
          " | ".join(err.splitlines()[:2])[:120])

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print("-------------------")
    if FAILURES:
        print("OPENEMS PREFLIGHT GATE FAILED (%d)" % len(FAILURES))
        raise SystemExit("OPENEMS PREFLIGHT GATE FAILED: " + "; ".join(FAILURES))
    print("OPENEMS PREFLIGHT GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" not in sys.modules:
    main()
