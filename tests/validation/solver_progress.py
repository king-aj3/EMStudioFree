#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — every solver reports DETERMINATE progress.

WHY THIS GATE EXISTS
--------------------
``ui/run_gui.py`` has carried a real progress bar with ETA since v0.88.0:
``_Reporter.progress(done, total, note)``, and a dialog that leaves
indeterminate mode the instant a fraction arrives. It was wired to exactly
ONE caller and **none of the four solver runners**, so every actual solve
still showed the swinging bar. Nothing failed; the feature was simply not
connected, and no test could tell.

That is the failure mode this gate is aimed at. It asserts the WIRING — that
each runner still calls the progress API — because a bar that silently stops
being fed looks exactly like a bar that was never fed.

MEASURED, on this box (all numbers below are from real runs, not fixtures):

* **NEC2 streams NOTHING.** 0 bytes stdout, 0 bytes stderr; everything goes to
  the ``-o`` file. A line-callback can never see progress, so NEC2 is driven
  by polling that file — which IS written incrementally (marker counts climbed
  9, 19, 30, 41 … during a 4.9 s run). NEC2 needs it: cost is ~cubic in
  segment count, and 6 wires x 151 segments took **104.75 s** against 0.25 s
  for a plain dipole.
* **A real Yagi solve** reported 18.8 % -> 39.4 % -> 59.1 % -> 78.4 % ->
  90 % (pattern) -> 100 %, monotonic.
* **Elmer axisymmetric**, 4 concurrent cases: 5 % -> 28.75 % -> 52.5 % ->
  76.25 % -> 100 %, monotonic, with all 2 461 log lines still forwarded.
* **Elmer 3-D**, analytic ring: gmsh 7.1 s (13 %), ElmerGrid 1.2 s (2 %),
  ElmerSolver 46.7 s (**85 %**). The phase weights encode that split; a first
  cut gave meshing 43 % of the bar for 13 % of the time.

Pass: exit 0 and 'SOLVER PROGRESS GATE PASSED'.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

FAILURES = []


def check(label, ok, detail=""):
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:96] + "]") if detail else ""))


class Rec(object):
    """Stands in for ui.run_gui._Reporter: callable, plus .progress()."""

    def __init__(self):
        self.lines = 0
        self.fr = []

    def __call__(self, line):
        self.lines += 1

    def progress(self, done, total, note=""):
        self.fr.append((done / total if total else 0.0, note))

    @property
    def vals(self):
        return [f for f, _n in self.fr]


class Plain(object):
    """A callback with NO .progress — an engine gate, a test, a headless run."""

    def __init__(self):
        self.lines = 0

    def __call__(self, line):
        self.lines += 1


# --- the reporting primitives -----------------------------------------------

def gate_primitives():
    from emstudio.solvers import progress

    # 1. never break a caller: lines must still be forwarded verbatim
    rec = Rec()
    rp = progress.ProgressReporter(rec, pattern=r"STEP", total=4, note="n")
    for _ in range(4):
        rp("STEP something")
    check("a ProgressReporter forwards every line it is given",
          rec.lines == 4, rec.lines)
    check("counting a marker yields a monotonic 0..1 fraction",
          rec.vals == [0.25, 0.5, 0.75, 1.0], rec.vals)

    # 2. phases compose into one monotonic run
    rec = Rec()
    a = progress.ProgressReporter(rec, pattern=r"S", total=2, base=0.0, span=0.5)
    b = progress.ProgressReporter(rec, pattern=r"S", total=2, base=0.5, span=0.5)
    a("S"); a("S"); b("S"); b("S")
    check("two phases advance monotonically across the whole job",
          rec.vals == [0.25, 0.5, 0.75, 1.0], rec.vals)

    # 3. best effort: a callback without .progress must not explode
    plain = Plain()
    progress.ProgressReporter(plain, pattern=r"S", total=1)("S")
    progress.report(plain, 0.5, "x")
    progress.report(None, 0.5, "x")
    check("a callback with no .progress is tolerated (and still gets lines)",
          plain.lines == 1, plain.lines)

    # 4. no denominator means NO fraction — never invent one
    rec = Rec()
    progress.ProgressReporter(rec, pattern=r"S", total=0)("S")
    check("with total <= 0 nothing is reported rather than a guess",
          rec.fr == [], rec.fr)

    # 5. StreamProgress: learns its total, stays monotonic, silent until ready
    rec = Rec()
    sp = progress.StreamProgress(rec, r"Timestep\s+(\d+)", r"NrTS\s*=\s*(\d+)",
                                 base=0.0, span=0.9)
    sp("[@ 1s] Timestep 250")                    # no total yet
    check("StreamProgress says nothing before it knows the total",
          rec.fr == [], rec.fr)
    sp("EMStudio: starting openEMS run (NrTS=1000, EndCriteria=0.0001)...")
    for ts in (250, 500, 1000):
        sp("[@ 7s] Timestep {0} || Speed: 28.4 MC/s".format(ts))
    sp("Timestep 100 || a restarted counter")
    check("StreamProgress scales the step against the learned total",
          rec.vals == [0.225, 0.45, 0.9], rec.vals)
    check("a counter that restarts never drags the bar backwards",
          all(b >= a for a, b in zip(rec.vals, rec.vals[1:])), rec.vals)


def gate_file_watcher():
    """The NEC2 mechanism: progress polled from a file, not a stream."""
    from emstudio.solvers import progress

    d = tempfile.mkdtemp()
    path = os.path.join(d, "case.out")
    rec = Rec()
    with open(path, "w") as fh:
        fh.write("header\n")
        fh.flush()
        with progress.FileWatcher(path, r"FREQUENCY\s*[:=]", 4, rec,
                                  note="Sweeping", interval=0.05):
            for i in range(4):
                fh.write("--------- FREQUENCY --------\n"
                         "FREQUENCY=  {0}.0E+02 MHZ\n".format(i + 1))
                fh.flush()
                time.sleep(0.15)
    check("a growing file drives the bar to completion",
          rec.vals and abs(rec.vals[-1] - 1.0) < 1e-9, rec.vals[-3:])
    check("file-driven progress is monotonic",
          all(b >= a for a, b in zip(rec.vals, rec.vals[1:])), rec.vals)
    # The file carries TWO "FREQUENCY" strings per point — a banner and a
    # datum. Counting both would report 200 % on a real sweep.
    # 4 points were written, each preceded by a banner -> EIGHT "FREQUENCY"
    # strings in the file. Counting banners too would saturate the bar after
    # two points (0.5, 1.0, 1.0, 1.0); counting only data lines gives four
    # even steps. That difference is the check.
    steps = sorted(v for v in set(rec.vals) if v > 0)
    check("the banner '--------- FREQUENCY --------' is NOT counted",
          steps == [0.25, 0.5, 0.75, 1.0], steps)

    # The REAL marker the NEC2 runner uses — imported, not copied, so this
    # tests what ships. A mutation to a bare "FREQUENCY" survived every other
    # check here: doubling the count just clamps the bar at 1.0 early, which
    # is still monotonic and still "reaches 100 %".
    from emstudio.solvers.nec2.runner import FREQ_MARKER
    marker = re.compile(FREQ_MARKER)
    check("the shipped NEC2 marker matches the datum line",
          bool(marker.search("FREQUENCY=  2.0000E+02 MHZ"))
          and bool(marker.search("FREQUENCY : 3.0000E+02 MHz")),
          FREQ_MARKER)
    check("the shipped NEC2 marker REJECTS the banner (else 100 % at halfway)",
          not marker.search("--------- FREQUENCY --------"), FREQ_MARKER)

    # a watcher with nothing to report to must not start a thread at all
    check("no callback -> no polling thread",
          progress.FileWatcher(path, r"X", 4, None).start()._thread is None)
    check("callback without .progress -> no polling thread",
          progress.FileWatcher(path, r"X", 4, Plain()).start()._thread is None)


# --- the WIRING: each runner must actually call the API ---------------------

def gate_label():
    """The dialog label must carry all FOUR numbers AJ asked for.

    Read out of run_gui.py by source slice rather than imported: that module
    pulls in Qt, and this gate runs on the FAST tier with no GUI.
    """
    import time as _t

    src = open(os.path.join(_ROOT, "emstudio", "ui", "run_gui.py"),
               encoding="utf-8").read()
    ns = {"time": _t}
    exec(src[src.index("def _clock("):src.index("def _apply_progress(")], ns)
    eta = ns["_eta_text"]

    class S(object):
        pass

    st = S()
    st.t_start = _t.time() - 30.0
    txt = eta(st, 0.42, 1.0)
    for field, needle in (("percent done", "42% done"),
                          ("percent TO GO", "58% to go"),
                          ("elapsed time", "elapsed 30 s"),
                          ("an ETA", "left")):
        check("the progress label states {0}".format(field), needle in txt, txt)

    # An extrapolation from almost no evidence is worse than none: it swings
    # wildly and teaches the user to ignore the field. Elapsed is a measured
    # fact and is always shown.
    st.t_start = _t.time() - 0.5
    early = eta(st, 0.01, 1.0)
    check("no ETA is offered before there is evidence for one",
          "left" not in early and "elapsed" in early, early)

    check("durations are human-readable, not raw seconds",
          [ns["_clock"](x) for x in (45, 187, 7325)]
          == ["45 s", "3 min 07 s", "2 h 02 m"],
          [ns["_clock"](x) for x in (45, 187, 7325)])


def gate_wiring():
    """Assert every runner still reports. This is the check that was missing.

    Deliberately source-level: three of the four backends cannot run on every
    machine, and the defect being guarded against is *not calling the API at
    all* — which source inspection catches everywhere, including on a box with
    no solvers installed.
    """
    wired = {
        "nec2/runner.py": ["progress.FileWatcher", "progress.report"],
        "elmer/runner.py": ["progress.report"],
        "elmer/runner3d.py": ["progress.report"],
        "openems/runner.py": ["progress.StreamProgress", "progress.report"],
        "palace/runner.py": ["progress.report"],
    }
    for rel, needles in sorted(wired.items()):
        src = open(os.path.join(_ROOT, "emstudio", "solvers", rel),
                   encoding="utf-8").read()
        missing = [n for n in needles if n not in src]
        check("{0} reports progress".format(rel), not missing, missing)

    # NEC2 must NOT try to count lines: it emits none (measured, 0 bytes).
    src = open(os.path.join(_ROOT, "emstudio", "solvers", "nec2", "runner.py"),
               encoding="utf-8").read()
    check("NEC2 uses the FILE watcher, not a line counter "
          "(it streams 0 bytes)",
          "FileWatcher" in src and "ProgressReporter" not in src)

    # Elmer's sweep counts COMPLETIONS under a lock — cases finish out of
    # order in the thread pool, so an index-based count would be wrong.
    src = open(os.path.join(_ROOT, "emstudio", "solvers", "elmer", "runner.py"),
               encoding="utf-8").read()
    check("Elmer counts case COMPLETIONS under a lock (the pool finishes "
          "out of order)",
          "_plock" in src and "with _plock:" in src)
    # Two reports are required: the phase start AND the per-case completion.
    # Grepping for "progress.report" anywhere passed with the in-loop call
    # deleted, because the phase-start call still matched.
    check("Elmer reports EACH case completion, not just the phase start",
          src.count("progress.report(") >= 2, src.count("progress.report("))

    # The 3-D phase weights must match the measured split, not a guess.
    src = open(os.path.join(_ROOT, "emstudio", "solvers", "elmer",
                            "runner3d.py"), encoding="utf-8").read()
    fracs = [float(m) for m in
             re.findall(r"progress\.report\(line_callback,\s*([0-9.]+)", src)]
    check("3-D phases are monotonic and leave the solve the largest share",
          fracs == sorted(fracs) and len(fracs) >= 4
          and (fracs[-1] - fracs[2]) > (fracs[1] - fracs[0]),
          fracs)


def gate_live_nec2():
    """A real NEC2 solve really does move the bar."""
    from emstudio.setup import solvers as solver_setup

    if not solver_setup.find_backend("nec2").found:
        print("  skip  live tier — no NEC2 backend installed")
        return
    try:
        import FreeCAD  # noqa: F401
    except Exception:                                           # noqa: BLE001
        print("  skip  live tier — needs FreeCAD (run under freecadcmd)")
        return

    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import nec2
    from emstudio.templates import dipole

    doc = FreeCAD.newDocument("progress_gate")
    try:
        ana = dipole.makeDipole(doc, f0_hz=300e6)
        solver = query.get_solvers(ana)[0]
        rec = Rec()
        nec2.run(ana, solver, line_callback=rec)
        check("a real NEC2 solve reports progress at all", bool(rec.fr),
              len(rec.fr))
        check("it is monotonic and reaches 100 %",
              rec.vals == sorted(rec.vals)
              and abs(max(rec.vals) - 1.0) < 1e-9 if rec.vals else False,
              rec.vals[-3:] if rec.vals else None)
        check("the pattern pass is reported separately from the sweep",
              any("pattern" in n.lower() for _f, n in rec.fr),
              sorted({n for _f, n in rec.fr}))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio solver-progress validation gate")
    gate_primitives()
    gate_file_watcher()
    gate_label()
    gate_wiring()
    gate_live_nec2()
    print("-------------------")
    if FAILURES:
        raise SystemExit("SOLVER PROGRESS GATE FAILED: " + "; ".join(FAILURES))
    print("SOLVER PROGRESS GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
