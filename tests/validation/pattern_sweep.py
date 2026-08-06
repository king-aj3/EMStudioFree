#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — a radiation pattern PER SWEPT FREQUENCY.

WHAT THIS IS FOR
----------------
A solve produced exactly ONE pattern, at the best-match frequency, because
``write_nec_farfield`` pinned its deck to ``FR 0,1,...``. That was a choice,
not a limitation, and the cost of lifting it was badly mis-estimated at first
("one extra deck run per frequency" — wrong).

MEASURED 2026-08-06, and it is what makes the feature reasonable:

* NEC2 runs the ``RP`` card at **every step of the ``FR`` card**, so N patterns
  cost **ONE run**. 201 points -> 201 pattern blocks in **7.18 s**.
* The real cost is OUTPUT: ~0.33 MB per frequency (65.4 MB at 201 points).
  Hence a COUNT the user picks, not "always all of them".
* On the shipped dipole: `PatternFrequencies = 11` took 1.01 s against 0.52 s
  for the default, and gave 11 patterns from 200 to 400 MHz with peak gain
  rising 1.92 -> 2.50 dBi (a fixed-length dipole grows more directive with
  frequency — the trend is physics, not an artifact).

THE TRAP THIS GATE EXISTS TO HOLD
---------------------------------
``parse_radiation_patterns`` pours every sample it finds into ONE theta/phi
grid. Run it on a multi-frequency file and each frequency overwrites the last,
returning a single perfectly plausible pattern that belongs to no frequency at
all — no error, no warning. ``parse_radiation_patterns_all`` splits on the
frequency marker instead, and this gate pins the difference.

Pass: exit 0 and 'PATTERN SWEEP GATE PASSED'.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

FAILURES = []


def check(label, ok, detail=""):
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:96] + "]") if detail else ""))


#: Two frequency blocks, each with its own 2x2 pattern. The gains are chosen so
#: a parser that merges them cannot look right: merged, the 200 MHz values are
#: entirely replaced by the 400 MHz ones.
_TWO_BLOCK = """
                               --------- FREQUENCY --------
                               FREQUENCY=  2.0000E+02 MHZ
                               WAVELENGTH= 1.5

                       - - - RADIATION PATTERNS - - -
  THETA   PHI    VERT   HOR    TOTAL
  0.00    0.00   -3.00  -99.0  -3.00
  0.00   90.00   -3.00  -99.0  -3.00
 90.00    0.00    1.00  -99.0   1.00
 90.00   90.00    1.00  -99.0   1.00

                               --------- FREQUENCY --------
                               FREQUENCY=  4.0000E+02 MHZ
                               WAVELENGTH= 0.75

                       - - - RADIATION PATTERNS - - -
  THETA   PHI    VERT   HOR    TOTAL
  0.00    0.00   -6.00  -99.0  -6.00
  0.00   90.00   -6.00  -99.0  -6.00
 90.00    0.00    5.00  -99.0   5.00
 90.00   90.00    5.00  -99.0   5.00

"""


def gate_parser():
    import tempfile

    from emstudio.solvers.nec2 import parser

    path = os.path.join(tempfile.mkdtemp(), "case_ff.out")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_TWO_BLOCK)

    ffs = parser.parse_radiation_patterns_all(path)
    check("both frequency blocks are recovered, not merged",
          len(ffs) == 2, len(ffs))
    if len(ffs) != 2:
        return
    check("each pattern carries its OWN frequency",
          [round(f.freq / 1e6) for f in ffs] == [200, 400],
          [f.freq for f in ffs])
    check("each pattern carries its OWN gains",
          (round(float(ffs[0].gain.max()), 2),
           round(float(ffs[1].gain.max()), 2)) == (1.0, 5.0),
          [float(f.gain.max()) for f in ffs])
    check("results come back sorted by frequency",
          [f.freq for f in ffs] == sorted(f.freq for f in ffs))

    # The trap: the single-block parser on the SAME file returns one pattern
    # whose gains are the LAST frequency's, labelled with whatever frequency it
    # was told. It is not wrong-looking, which is the whole problem.
    merged = parser.parse_radiation_patterns(path, 200e6)
    check("the single-block parser DOES silently merge (why _all exists)",
          abs(float(merged.gain.max()) - 5.0) < 1e-9
          and abs(merged.freq - 200e6) < 1.0,
          "gain {0} labelled {1:.0f} MHz".format(float(merged.gain.max()),
                                                 merged.freq / 1e6))


def gate_writer():
    """The multi-frequency deck, and the byte-identical single-frequency one."""
    import tempfile

    from emstudio.solvers.nec2 import writer

    src = open(os.path.join(_ROOT, "emstudio", "solvers", "nec2", "writer.py"),
               encoding="utf-8").read()
    check("write_nec_farfield can sweep (npts/f2_hz)",
          "def write_nec_farfield(analysis, solver, path, f_hz, npts=1, "
          "f2_hz=None):" in src)
    check("npts=1 still emits the one-point FR card every frozen deck expects",
          'lines.append("FR 0,1,0,0,{0:.6f},0.".format(f_hz / 1e6))' in src)
    check("the swept form emits an N-point FR card with a real step",
          'lines.append("FR 0,{0:d},0,0,{1:.6f},{2:.6f}".format(' in src)
    # The RP card must still be there — an FR sweep with no RP emits no
    # patterns at all, which is how the first probe of this measured zero.
    check("an RP card is still emitted (FR without RP yields NO patterns)",
          '"RP 0,37,72,1000,0.,0.,5.,5."' in src
          and '"RP 0,19,72,1000,0.,0.,5.,5."' in src)


def gate_wiring():
    src = open(os.path.join(_ROOT, "emstudio", "solvers", "nec2", "runner.py"),
               encoding="utf-8").read()
    check("the runner reads the solver's PatternFrequencies",
          'getattr(solver, "PatternFrequencies", 0)' in src)
    check("a swept run parses with the PER-FREQUENCY parser",
          "parse_radiation_patterns_all" in src)
    check("result.farfield stays the single best-match pattern (compat)",
          "result.farfield = min(result.farfields," in src)
    check("result.farfields is always populated, even for one pattern",
          "result.farfields = [result.farfield]" in src)

    props = open(os.path.join(_ROOT, "emstudio", "objects", "solver_objs.py"),
                 encoding="utf-8").read()
    check("PatternFrequencies defaults to 0 (every old document unchanged)",
          "obj.PatternFrequencies = 0" in props)

    ui = open(os.path.join(_ROOT, "emstudio", "ui", "results_dialog.py"),
              encoding="utf-8").read()
    # Match the CONSTRUCTOR CALL, not the bare class name: a mutation that
    # replaced it with "combo = None  # QComboBox" satisfied a substring check
    # and survived. Behaviour is covered by gui_smoke's picker check (a real
    # Qt build, 5 frequencies, opens on the best match); this only pins that
    # the wiring is still present for the FAST tier, which has no Qt.
    check("the results dialog builds a frequency picker",
          "_pattern_tab" in ui and "QtWidgets.QComboBox(holder)" in ui)
    check("with a single pattern the picker is NOT built (tab unchanged)",
          "if len(self._farfields) < 2:" in ui)


def gate_live():
    """A real solve really does produce N patterns for one extra run."""
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

    doc = FreeCAD.newDocument("pattern_sweep_gate")
    try:
        ana = dipole.makeDipole(doc, f0_hz=300e6)
        solver = query.get_solvers(ana)[0]

        solver.PatternFrequencies = 0
        doc.recompute()
        res = nec2.run(ana, solver)
        check("default (0) still yields exactly ONE pattern",
              len(res.farfields) == 1, len(res.farfields))
        check("and it is still the 2.13 dBi dipole the literature gate pins",
              abs(float(res.farfield.gain.max()) - 2.13) < 0.05,
              float(res.farfield.gain.max()))

        solver.PatternFrequencies = 11
        doc.recompute()
        res = nec2.run(ana, solver)
        check("11 requested -> 11 patterns", len(res.farfields) == 11,
              len(res.farfields))
        freqs = [f.freq for f in res.farfields]
        check("they span the whole sweep band, in order",
              freqs == sorted(freqs) and abs(freqs[0] - 200e6) < 1e6
              and abs(freqs[-1] - 400e6) < 1e6,
              [round(f / 1e6) for f in freqs])
        check("every pattern carries its own gain (not one value repeated)",
              len({round(float(f.gain.max()), 3) for f in res.farfields}) > 5,
              sorted({round(float(f.gain.max()), 2) for f in res.farfields}))
        # a fixed-length dipole grows more directive as frequency rises
        gains = [float(f.gain.max()) for f in res.farfields]
        check("peak gain rises monotonically across the band (physics, not "
              "noise)", all(b >= a - 1e-6 for a, b in zip(gains, gains[1:])),
              [round(g, 2) for g in gains])
        check("result.farfield is still the best-match pattern",
              abs(res.farfield.freq - min(
                  freqs, key=lambda f: abs(f - res.min_s11()[0]))) < 1.0)
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio per-frequency radiation-pattern gate")
    gate_parser()
    gate_writer()
    gate_wiring()
    gate_live()
    print("-------------------")
    if FAILURES:
        raise SystemExit("PATTERN SWEEP GATE FAILED: " + "; ".join(FAILURES))
    print("PATTERN SWEEP GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
