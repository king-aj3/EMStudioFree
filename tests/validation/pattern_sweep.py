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


def _dipole_analysis(doc):
    """A minimal, real half-wave dipole analysis. Returns ``(analysis, solver)``.

    Deliberately the simplest thing the deck writer will accept: one straight
    wire, one PEC material, one centre feed. The point is a REAL deck to read
    cards back out of, not a physically interesting antenna — the physics is
    `dipole_nec2`'s job.
    """
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    wire = doc.addObject("Part::Feature", "DipoleWire")
    wire.Shape = Part.makePolygon([FreeCAD.Vector(0, 0, -250),
                                   FreeCAD.Vector(0, 0, 250)])
    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = "200 MHz"
    ana.FrequencyStop = "400 MHz"
    ana.FrequencyPoints = 21
    mat = material_mod.makeMaterial(doc, ana, name="FFPEC",
                                    category="Metal (PEC)")
    mat.References = [(wire, "")]
    mat.WireRadius = "1 mm"
    port = ports_mod.makeLumpedPort(doc, ana, name="FFFeed")
    port.References = [(wire, "Edge1")]
    solver = solver_objs.makeSolverNEC2(doc, ana)
    doc.recompute()
    return ana, solver


def gate_writer():
    """The multi-frequency deck, and the byte-identical single-frequency one.

    ⚠ **REWRITTEN 2026-08-20 — this used to read `writer.py` and assert it
    CONTAINED four literal lines.** That tests what the file SAYS. It now
    writes REAL DECKS and reads the cards back, which is the artefact nec2c
    actually consumes — the same standard `team7_elmer` applies to its `.sif`.

    Needs FreeCAD for a real analysis (the deck is built from geometry), so it
    skips under plain python exactly as `gate_polyline_deck` does.
    """
    try:
        import FreeCAD
    except Exception:                                           # noqa: BLE001
        print("  skip  writer deck — needs FreeCAD (run under freecadcmd)")
        return

    import tempfile

    import FreeCAD
    import Part

    from emstudio.solvers.nec2 import writer

    doc = FreeCAD.newDocument("ff_writer_gate")
    try:
        ana, solver = _dipole_analysis(doc)
        tmp = tempfile.mkdtemp()

        one = os.path.join(tmp, "one.nec")
        writer.write_nec_farfield(ana, solver, one, 300e6)
        d1 = open(one, encoding="utf-8").read()
        fr1 = [l for l in d1.splitlines() if l.startswith("FR ")]
        check("npts=1 emits exactly ONE FR card [%d]" % len(fr1), len(fr1) == 1)
        check("...in the one-point form every frozen deck expects [%s]"
              % (fr1[0] if fr1 else "-"),
              bool(fr1) and fr1[0] == "FR 0,1,0,0,300.000000,0.")

        many = os.path.join(tmp, "many.nec")
        writer.write_nec_farfield(ana, solver, many, 200e6, npts=5, f2_hz=400e6)
        d5 = open(many, encoding="utf-8").read()
        fr5 = [l for l in d5.splitlines() if l.startswith("FR ")]
        check("the swept form emits ONE N-point FR card [%s]"
              % (fr5[0] if fr5 else "-"),
              len(fr5) == 1 and fr5[0].startswith("FR 0,5,0,0,200.000000,"))
        # The step must be real and correct: (400-200)/(5-1) = 50 MHz. A step
        # of 0 emits five patterns at ONE frequency — five copies of the same
        # answer, labelled as a sweep, which is exactly the plausible-looking
        # failure this whole feature can produce.
        step = float(fr5[0].split(",")[-1]) if fr5 else -1.0
        check("...with the REAL step, not 0 [%g MHz]" % step,
              abs(step - 50.0) < 1e-6)

        # An FR sweep with no RP card emits no patterns at all — how the first
        # probe of this feature measured zero.
        for label, deck in (("single", d1), ("swept", d5)):
            rp = [l for l in deck.splitlines() if l.startswith("RP ")]
            check("the %s deck still carries an RP card [%d]" % (label, len(rp)),
                  len(rp) >= 1)
    finally:
        FreeCAD.closeDocument(doc.Name)


#: A two-point sweep whose BEST MATCH is the SECOND point (400 MHz, ~50 ohm)
#: and whose first point is badly mismatched (~75+j10). Deliberate: it makes
#: "the best-match pattern" different from "the first pattern", so a selection
#: that just took farfields[0] is visible. With a matched first point the two
#: answers coincide and the check would prove nothing.
_SWEEP_TWO_POINT = (
    "                        --------- FREQUENCY --------\n"
    "                               FREQUENCY=  2.0000E+02 MHZ\n\n"
    "                        --------- ANTENNA INPUT PARAMETERS ---------\n"
    "  TAG   SEG       VOLTAGE (VOLTS)         CURRENT (AMPS)         "
    "IMPEDANCE (OHMS)        ADMITTANCE (MHOS)     POWER\n"
    "    1    11  1.0000E+00  0.0000E+00  1.3128E-02 -1.7160E-03  "
    "7.4894E+01  9.7899E+00  1.3128E-02 -1.7160E-03  6.5639E-03\n\n"
    "                        --------- FREQUENCY --------\n"
    "                               FREQUENCY=  4.0000E+02 MHZ\n\n"
    "                        --------- ANTENNA INPUT PARAMETERS ---------\n"
    "  TAG   SEG       VOLTAGE (VOLTS)         CURRENT (AMPS)         "
    "IMPEDANCE (OHMS)        ADMITTANCE (MHOS)     POWER\n"
    "    1    11  1.0000E+00  0.0000E+00  2.0000E-02  0.0000E+00  "
    "5.0000E+01  0.0000E+00  2.0000E-02  0.0000E+00  1.0000E-02\n"
)


class _StubSolver:
    """Only the attributes the runner actually reads off a solver object."""

    def __init__(self, n_pat=0, f1=0.0, f2=0.0):
        self.PatternFrequencies = n_pat
        self.PatternFreqStart = f1
        self.PatternFreqStop = f2


class _StubAnalysis:
    Label = "ff-wiring-fixture"


def _drive_runner(n_pat, band=(0.0, 0.0)):
    """Run the REAL runner with only the BINARY and the DECK WRITER stubbed.

    Everything under test — reading ``PatternFrequencies``, resolving the
    pattern band, choosing the multi vs single branch, populating
    ``farfields`` / ``farfield`` / ``currents_all`` — is the shipped code.
    What is replaced is exactly the two things a FAST gate cannot have: nec2c
    itself (a fake job drops canned NEC2 output where the run expects it) and
    the deck writer (it needs real FreeCAD geometry; its own cards are gated
    for real in ``gate_writer``).

    The stub writer RECORDS its arguments, which is how the runner's decisions
    become observable without a solver: if the runner asks for ``npts=1`` when
    five patterns were requested, that is the multi-branch failing, and it
    shows up here as a recorded call rather than as a missing string.

    Returns ``(result, calls)``.
    """
    import tempfile

    from emstudio.solvers.base import SolverJob as _RealJob
    from emstudio.solvers.nec2 import runner

    calls = []

    class _StubInfo:
        found = True
        path = "nec2-stub"
        backend = "nec2"

    class _StubSetup:
        @staticmethod
        def find_backend(_name):
            return _StubInfo()

        @staticmethod
        def install_hint(_backend):
            return ""

    class _StubWriter:
        @staticmethod
        def write_nec(_ana, _solver, path, report=None):
            open(path, "w", encoding="utf-8").write("CM stub deck\nCE\nEN\n")
            if report is not None:
                report["thin_wire"] = {"ok": True, "ratio": 9.0, "segments": 11}
            return None, (200e6, 400e6, 2), 50.0

        @staticmethod
        def write_nec_farfield(_ana, _solver, path, f_hz, npts=1, f2_hz=None):
            calls.append({"f_hz": f_hz, "npts": npts, "f2_hz": f2_hz})
            open(path, "w", encoding="utf-8").write("CM stub ff deck\nCE\nEN\n")

    class _StubJob:
        """Writes the canned output the real binary would have produced."""

        duration_s = 0.0

        def __init__(self, argv, cwd=None, line_callback=None):
            # ⚠ nec2_argv passes BASENAMES and relies on cwd — macOS temp paths
            # overflow nec2c's fixed filename buffer. A stub that ignores cwd
            # writes the canned output into the wrong directory and the run
            # fails with FileNotFoundError, which looks like a parser bug.
            out = [a for a in argv if str(a).endswith(".out")][-1]
            self.out = os.path.join(cwd or ".", os.path.basename(out))

        def run_blocking(self, timeout=None):
            body = (_TWO_BLOCK_CURRENTS
                    if os.path.basename(self.out) == "case_ff.out"
                    else _SWEEP_TWO_POINT)
            open(self.out, "w", encoding="utf-8").write(body)

    saved = (runner.solver_setup, runner.writer, runner.SolverJob)
    try:
        runner.solver_setup = _StubSetup
        runner.writer = _StubWriter
        runner.SolverJob = _StubJob
        result = runner.run(_StubAnalysis(),
                            _StubSolver(n_pat, band[0], band[1]),
                            workdir=tempfile.mkdtemp())
    finally:
        (runner.solver_setup, runner.writer, runner.SolverJob) = saved
        assert runner.SolverJob is _RealJob, "the real SolverJob was not restored"
    return result, calls


def gate_wiring():
    """The runner's pattern pass, DRIVEN — not read.

    ⚠⚠ **REWRITTEN 2026-08-20, and the old version was measurably theatre.**
    It opened `runner.py` and asserted it CONTAINED lines like
    `"result.farfields = [result.farfield]"`. Three behaviour-destroying
    mutations were run against it and **all three stayed green**: commenting
    out the farfields population, commenting out the per-frequency currents,
    and — worst — turning `if multi:` into `if False:`, which makes the entire
    multi-frequency branch unreachable while every asserted substring survives
    untouched. A source-text check proves the file SAYS something; only running
    it proves the code DOES it.
    """
    # -- five patterns requested: the MULTI branch --------------------------
    res, calls = _drive_runner(5)
    check("a 5-pattern request reaches the writer as ONE swept deck [%d call(s)]"
          % len(calls), len(calls) == 1)
    got = calls[0] if calls else {}
    check("...asking for 5 points, not 1 [npts=%s]" % got.get("npts"),
          got.get("npts") == 5)
    check("...across the sweep band, so f2 is passed [f2=%s]" % got.get("f2_hz"),
          got.get("f2_hz") is not None and abs(got["f2_hz"] - 400e6) < 1.0)
    check("every frequency block becomes its own pattern [%d]"
          % len(res.farfields), len(res.farfields) == 2)
    check("...each carrying its OWN frequency, not the caller's",
          [round(f.freq / 1e6) for f in res.farfields] == [200, 400],
          [f.freq for f in res.farfields])
    # The fixture's best match is the SECOND point, so "best match" and
    # "the first one" are different objects here — which is the only way
    # this check can see a selection that quietly takes farfields[0].
    check("result.farfield is the BEST-MATCH pattern, not simply the first "
          "[%.0f MHz]" % (res.farfield.freq / 1e6),
          abs(res.farfield.freq - 400e6) < 1.0)
    check("per-frequency currents ride the same run [%d]"
          % len(res.currents_all), len(res.currents_all) == 2)
    check("the deck's thin-wire measurement reaches the result",
          isinstance(res.meta.get("thin_wire"), dict))

    # -- the default: no pattern sweep asked for ----------------------------
    res1, calls1 = _drive_runner(0)
    check("with PatternFrequencies=0 the writer is asked for ONE point "
          "[npts=%s]" % (calls1[0].get("npts") if calls1 else None),
          len(calls1) == 1 and calls1[0].get("npts") == 1)
    check("...and farfields is STILL populated, with exactly one entry [%d]"
          % len(res1.farfields), len(res1.farfields) == 1)
    check("...which is the same object as result.farfield",
          res1.farfields[0] is res1.farfield)

    # -- the band narrows the pattern pass ----------------------------------
    _res2, calls2 = _drive_runner(5, band=(250e6, 350e6))
    b = calls2[0] if calls2 else {}
    check("a narrowed PatternFreqStart/Stop reaches the deck [%s-%s MHz]"
          % (b.get("f_hz", 0) / 1e6, (b.get("f2_hz") or 0) / 1e6),
          abs(b.get("f_hz", 0) - 250e6) < 1.0
          and abs((b.get("f2_hz") or 0) - 350e6) < 1.0)

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
    # Behaviour is covered by gui_smoke (both pickers + the 3-D export move
    # together on a real Qt build); these pin the wiring for the FAST tier.
    check("'Show in 3D View' exports the SELECTED pattern, not the best match",
          "ff = self._selected_farfield()" in ui
          and "ff = getattr(self.result, \"farfield\", None)" not in ui)
    check("the VSWR view is not hard-clamped to 1..10 any more",
          "ax.set_ylim(1, 10)" not in ui and "VSWR_VIEW_TOP" in ui
          and "ax.semilogy(" in ui)
    check("a single-pattern run says WHERE the picker switch lives",
          "Pattern Frequencies" in ui)


#: Two frequency blocks, each with a currents table AND a pattern table.
#: The SAME physical wire (1.5 m along z) appears in both blocks, expressed in
#: each block's OWN wavelengths — so a parser that picks the right block but
#: scales with the wrong lambda cannot return the right geometry, and one that
#: fails to close the currents table swallows pattern rows (>= 10 numbers each)
#: into the currents. The current magnitudes differ per block on purpose.
_TWO_BLOCK_CURRENTS = """
                               --------- FREQUENCY --------
                               FREQUENCY=  2.0000E+02 MHZ
                               WAVELENGTH= 1.49896

                       - - - CURRENTS AND LOCATION - - -

  SEG  TAG    COORDINATES OF SEG CENTER     SEG         - - - CURRENT (AMPS) - - -
  NO.  NO.     X        Y        Z       LENGTH     REAL      IMAG      MAGN     PHASE
    1    1  0.00067  0.00067  0.16678  0.33357  1.00E+00  0.00E+00  1.00E+00     0.00
    2    1  0.00067  0.00067  0.50035  0.33357  2.00E+00  0.00E+00  2.00E+00     0.00
    3    1  0.00067  0.00067  0.83392  0.33357  1.00E+00  0.00E+00  1.00E+00     0.00

                       - - - RADIATION PATTERNS - - -
  0.00    0.00   -3.00  -99.0  -3.00  1.0 2.0 3.0 4.0 5.0 6.0
 90.00    0.00    1.00  -99.0   1.00  1.0 2.0 3.0 4.0 5.0 6.0

                               --------- FREQUENCY --------
                               FREQUENCY=  4.0000E+02 MHZ
                               WAVELENGTH= 0.74948

                       - - - CURRENTS AND LOCATION - - -

  SEG  TAG    COORDINATES OF SEG CENTER     SEG         - - - CURRENT (AMPS) - - -
  NO.  NO.     X        Y        Z       LENGTH     REAL      IMAG      MAGN     PHASE
    1    1  0.00133  0.00133  0.33356  0.66714  4.00E+00  0.00E+00  4.00E+00     0.00
    2    1  0.00133  0.00133  1.00070  0.66714  5.00E+00  0.00E+00  5.00E+00     0.00
    3    1  0.00133  0.00133  1.66784  0.66714  4.00E+00  0.00E+00  4.00E+00     0.00

                       - - - RADIATION PATTERNS - - -
  0.00    0.00   -6.00  -99.0  -6.00  1.0 2.0 3.0 4.0 5.0 6.0
 90.00    0.00    5.00  -99.0   5.00  1.0 2.0 3.0 4.0 5.0 6.0

"""


def gate_currents_blocks():
    """parse_currents on a multi-frequency file: right block, right lambda.

    THE DEFECT THIS PINS (2026-08-07, found from a screenshot): the parser
    read the FIRST currents table (the band-start frequency) and scaled its
    wavelength-relative coordinates with the CALLER'S frequency. On the
    multi-frequency deck that v0.92 made the default, a 10-100 MHz sweep of a
    300 mm helix drew "Wire currents" as a 44 mm miniature carrying the 10 MHz
    current values under a best-match label. Geometry AND data wrong, neither
    visibly an error.
    """
    import tempfile

    import numpy as np

    from emstudio.solvers.nec2 import parser

    path = os.path.join(tempfile.mkdtemp(), "case_ff.out")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_TWO_BLOCK_CURRENTS)

    # The fixture wire is 1.5 m along z, 3 segments of 0.5 m: centres at
    # 0.25 / 0.75 / 1.25 m (span 1.0 m), expressed in each block's own
    # wavelengths (lambda = 1.49896 m at 200 MHz, 0.74948 m at 400 MHz).
    a = parser.parse_currents(path, 200e6)
    b = parser.parse_currents(path, 400e6)
    check("each request selects the block NEAREST its frequency",
          abs(a["freq"] - 200e6) < 1.0 and abs(b["freq"] - 400e6) < 1.0,
          (a["freq"], b["freq"]))
    check("current VALUES come from the selected block, not the first",
          list(b["i_mag"]) == [4.0, 5.0, 4.0], list(b["i_mag"]))
    za = np.asarray(a["pos_m"])[:, 2]
    zb = np.asarray(b["pos_m"])[:, 2]
    check("both blocks decode to the SAME physical wire (own-lambda scaling)",
          np.allclose(za, zb, rtol=1e-3), (za.tolist(), zb.tolist()))
    check("and it is the real 1 m span, not a first-block miniature",
          abs((za.max() - za.min()) - 1.0) < 0.01, za.max() - za.min())
    check("a 400 MHz request scaled with the caller's lambda would be HALF "
          "size — the old bug — and it is not",
          abs(zb.max() - zb.min() - 1.0) < 0.01, zb.max() - zb.min())
    check("the pattern tables did not pollute the currents (3 segs each)",
          len(a["seg"]) == 3 and len(b["seg"]) == 3,
          (len(a["seg"]), len(b["seg"])))
    check("an off-grid request still lands on the nearest block",
          abs(parser.parse_currents(path, 260e6)["freq"] - 200e6) < 1.0)

    # parse_currents_all — the per-frequency set the Currents tab scrubs
    alls = parser.parse_currents_all(path)
    check("parse_currents_all returns every block, sorted by frequency",
          len(alls) == 2 and [round(c["freq"] / 1e6) for c in alls] == [200, 400],
          [c["freq"] for c in alls])
    check("each entry keeps its own block's values",
          list(alls[0]["i_mag"]) == [1.0, 2.0, 1.0]
          and list(alls[1]["i_mag"]) == [4.0, 5.0, 4.0])
    z0 = np.asarray(alls[0]["pos_m"])[:, 2]
    z1 = np.asarray(alls[1]["pos_m"])[:, 2]
    check("every entry decodes the same physical wire (own-lambda each)",
          np.allclose(z0, z1, rtol=1e-3))

    # The sort must be REAL, not an accident of the file's own order — the
    # dialog aligns currents to far fields BY INDEX, both lists sorted. A
    # mutation that dropped the sort survived on the ascending fixture
    # (2026-08-07), so this one is descending on purpose.
    half = _TWO_BLOCK_CURRENTS.index("                               ---------"
                                     " FREQUENCY --------", 100)
    reversed_file = _TWO_BLOCK_CURRENTS[half:] + _TWO_BLOCK_CURRENTS[:half]
    rpath = os.path.join(tempfile.mkdtemp(), "case_ff_desc.out")
    with open(rpath, "w", encoding="utf-8") as fh:
        fh.write(reversed_file)
    ralls = parser.parse_currents_all(rpath)
    check("a file whose blocks arrive DESCENDING still returns ascending",
          [round(c["freq"] / 1e6) for c in ralls] == [200, 400],
          [c["freq"] for c in ralls])


def gate_band():
    """The band/step arithmetic the dialog and the runner share."""
    from emstudio.solvers.nec2 import pattern_band as pb

    # The user's real case: 10-100 MHz, 51 points -> a 1.8 MHz sweep step.
    sweep_step = pb.sweep_step_hz(10e6, 100e6, 51)
    check("the sweep step is derived, not assumed",
          abs(sweep_step - 1.8e6) < 1.0, sweep_step)
    rec = pb.recommend(10e6, 100e6, sweep_step)
    check("the recommendation is a whole number of sweep steps",
          rec["on_sweep_points"]
          and abs(rec["step_hz"] / sweep_step
                  - round(rec["step_hz"] / sweep_step)) < 1e-9,
          "{0:.4g} MHz vs sweep step {1:.4g} MHz".format(
              rec["step_hz"] / 1e6, sweep_step / 1e6))
    check("and its last pattern lands exactly on the band edge",
          abs(10e6 + (rec["count"] - 1) * rec["step_hz"] - 100e6) < 1.0,
          10e6 + (rec["count"] - 1) * rec["step_hz"])
    check("it recommends a sane count, not one pattern and not all 51",
          2 < rec["count"] < 51, rec["count"])
    check("output size is reported, because that is the real cost",
          abs(rec["mb"] - rec["count"] * pb.MB_PER_PATTERN) < 1e-9, rec["mb"])

    # A NARROWED band is the case that broke the first implementation: it
    # derived the grid from the band it was handed, so as soon as the band
    # stopped being the sweep, "lands on sweep points" silently stopped being
    # true. The sweep step is an argument for exactly this reason.
    narrow = pb.recommend(50e6, 68e6, sweep_step)     # 10 sweep steps wide
    ratio = narrow["step_hz"] / sweep_step
    check("a NARROWED band still lands on the sweep's own sample points",
          narrow["on_sweep_points"] and abs(ratio - round(ratio)) < 1e-9,
          "{0:.4g} MHz = {1:.4g} sweep steps".format(
              narrow["step_hz"] / 1e6, ratio))
    check("and the narrowed recommendation spans that band exactly",
          abs(50e6 + (narrow["count"] - 1) * narrow["step_hz"] - 68e6) < 1.0,
          narrow["count"])
    # A band that is NOT a whole number of sweep steps must not claim it is.
    off = pb.recommend(50e6, 68.9e6, sweep_step)
    check("a band off the sweep grid says so rather than claiming alignment",
          not off["on_sweep_points"], off["note"])

    # A step the user types by hand rarely divides the band. NEC2 will run an
    # FR card straight off the end of it, so the count must stop SHORT of the
    # stop frequency, never past it.
    check("a step that does not divide the band stops short, never past it",
          pb.count_for_step(200e6, 400e6, 30e6) == 7,
          pb.count_for_step(200e6, 400e6, 30e6))
    check("200 + 6*30 = 380 MHz is inside the requested band",
          200e6 + 6 * 30e6 <= 400e6)

    class _Solver:
        PatternFreqStart = 0.0
        PatternFreqStop = 0.0

    s = _Solver()
    check("0/0 follows the analysis sweep (every pre-0.91 document)",
          pb.resolve_band(s, 1e6, 2e6) == (1e6, 2e6))
    s.PatternFreqStart, s.PatternFreqStop = 1.2e6, 1.8e6
    check("a real band overrides the sweep",
          pb.resolve_band(s, 1e6, 2e6) == (1.2e6, 1.8e6))
    # Half-entered pairs are the normal state of two property-editor fields.
    s.PatternFreqStart, s.PatternFreqStop = 1.8e6, 1.2e6
    check("an INVERTED band falls back to the sweep rather than erroring",
          pb.resolve_band(s, 1e6, 2e6) == (1e6, 2e6))
    s.PatternFreqStart, s.PatternFreqStop = 1.2e6, 0.0
    check("a half-entered band falls back to the sweep",
          pb.resolve_band(s, 1e6, 2e6) == (1e6, 2e6))


def gate_segmentation():
    """The thin-wire guard: a polyline link is a chord, not a lone wire."""
    from emstudio.solvers.nec2 import writer

    src = open(os.path.join(_ROOT, "emstudio", "solvers", "nec2", "writer.py"),
               encoding="utf-8").read()
    check("a polyline link does not take the lone-wire 3-segment floor",
          "min_seg = 1 if is_polyline else 3" in src)
    check("segment counts are capped at the thin-wire ratio",
          "n_thin = max(1, int(length / (THIN_WIRE_MIN_SEG_RADII * radius_m)))"
          in src)

    # Behavioural, on the numbers the GW cards encode. 100 mm of 10 mm-radius
    # wire: one segment is 10 radii (fine), five segments is 2 (not).
    w = {"p1": (0.0, 0.0, 0.0), "p2": (0.0, 0.0, 0.1), "radius": 0.01,
         "nseg": 1}
    rep = writer.thin_wire_report([w])
    check("thin_wire_report measures d/a off the built wires",
          abs(rep["ratio"] - 10.0) < 1e-9 and rep["ok"], rep)
    rep = writer.thin_wire_report([dict(w, nseg=5)])
    check("and it FAILS a deck under NEC-2's guideline",
          abs(rep["ratio"] - 2.0) < 1e-9 and not rep["ok"], rep)
    check("the guideline it reports against is 8 radii (Burke & Poggio)",
          abs(writer.THIN_WIRE_MIN_SEG_RADII - 8.0) < 1e-9,
          writer.THIN_WIRE_MIN_SEG_RADII)
    check("a radius-less wire cannot be measured and is not guessed at",
          writer.thin_wire_report([dict(w, radius=0.0)]) is None)


def gate_polyline_deck():
    """A real polyline wire must not be chopped under the thin-wire limit.

    This is the defect as it actually shipped: `Antenna from Selection` hands
    NEC2 a `Part.makePolygon`, so a curve arrives as N STRAIGHT edges and every
    one of them took the lone-wire 3-segment floor. Measured on a 300 mm helix:
    240 segments of 25 mm on a 9.49 mm radius, d/a = 2.63.
    """
    try:
        import FreeCAD
    except Exception:                                           # noqa: BLE001
        print("  skip  polyline deck — needs FreeCAD (run under freecadcmd)")
        return

    import math

    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs
    from emstudio.solvers.nec2 import writer

    doc = FreeCAD.newDocument("polyline_seg_gate")
    try:
        # A helix with the user's proportions: fat wire, short chords.
        radius_mm, height_mm, turns, n = 150.0, 200.0, 6.0, 72
        pts = []
        for i in range(n + 1):
            t = i / float(n)
            a = 2.0 * math.pi * turns * t
            pts.append(FreeCAD.Vector(radius_mm * math.cos(a),
                                      radius_mm * math.sin(a),
                                      height_mm * t))
        wire = doc.addObject("Part::Feature", "PolyWire")
        wire.Shape = Part.makePolygon(pts)
        doc.recompute()
        check("the fixture really is a many-edged POLYLINE of straight edges",
              len(wire.Shape.Edges) == n
              and all(type(e.Curve).__name__ == "Line"
                      for e in wire.Shape.Edges), len(wire.Shape.Edges))

        ana = analysis_mod.makeAnalysis(doc)
        ana.FrequencyStart = "10 MHz"
        ana.FrequencyStop = "100 MHz"
        ana.FrequencyPoints = 51
        mat = material_mod.makeMaterial(doc, ana, name="PolyPEC",
                                        category="Metal (PEC)")
        mat.References = [(wire, "")]
        mat.WireRadius = "9.4885 mm"
        port = ports_mod.makeLumpedPort(doc, ana, name="PolyFeed")
        port.References = [(wire, "Edge{0}".format(n // 2))]
        solver = solver_objs.makeSolverNEC2(doc, ana)
        doc.recompute()

        wires, _feeds, _sweep = writer.build_wire_model_multi(ana, solver)
        rep = writer.thin_wire_report(wires)
        check("the polyline deck now satisfies NEC-2's thin-wire guideline",
              rep is not None and rep["ok"],
              "d/a {0:.2f}, {1} segments".format(rep["ratio"], rep["segments"])
              if rep else None)
        # The floor was the whole defect: with it, EVERY chord got 3 segments.
        unfed = [w for w in wires if not w["fed"]]
        check("an unfed chord is ONE segment, not the lone-wire floor of 3",
              unfed and all(w["nseg"] == 1 for w in unfed),
              sorted({w["nseg"] for w in unfed}))
        check("total segments fell to ~1 per chord (was 3)",
              rep["segments"] <= n + 4, rep["segments"])

        # THE failure mode a segment-count change causes, and it is silent:
        # the EX card names a segment by INDEX, so lowering a fed wire's count
        # can leave the source pointing past the end of it. nec2++ then emits
        # an output file with ZERO frequency blocks and exit 0 — measured while
        # investigating this very helix. Assert the deck is self-consistent.
        import tempfile

        deck = os.path.join(tempfile.mkdtemp(), "poly.nec")
        writer.write_nec(ana, solver, deck)
        lines = open(deck, encoding="utf-8").read().splitlines()
        gw = {}
        for ln in lines:
            if ln.startswith("GW"):
                f = [x.strip() for x in ln.split(",")]
                gw[int(f[0].split()[1])] = int(f[1])
        ex = [ln for ln in lines if ln.startswith("EX")]
        check("the deck emits exactly one EX card", len(ex) == 1, ex)
        f = [x.strip() for x in ex[0].split(",")]
        tag, seg = int(f[1]), int(f[2])
        check("the EX card names a segment that EXISTS on its wire",
              tag in gw and 1 <= seg <= gw[tag],
              "EX tag {0} seg {1}; that wire has {2} segments".format(
                  tag, seg, gw.get(tag)))
        check("and it is the centre segment of that wire",
              seg == gw[tag] // 2 + 1,
              "seg {0} of {1}".format(seg, gw.get(tag)))
    finally:
        FreeCAD.closeDocument(doc.Name)


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
        import numpy as _np
        pos0 = _np.asarray(res.currents["pos_m"])
        span0 = float((pos0.max(0) - pos0.min(0)).max())

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
        # THE 2026-08-07 DEFECT, live: on the multi-frequency file the
        # currents used to come from the FIRST block (band start) scaled with
        # the best-match wavelength — same wire, wrong size, wrong values.
        pos1 = _np.asarray(res.currents["pos_m"])
        span1 = float((pos1.max(0) - pos1.min(0)).max())
        check("multi-run currents geometry matches the single-run's "
              "(the 44 mm-miniature bug)",
              abs(span1 - span0) < 0.01 * max(span0, 1e-9),
              "single {0:.4f} m vs multi {1:.4f} m".format(span0, span1))
        check("and the currents carry the best-match block's frequency, "
              "not the band start's",
              abs(res.currents["freq"] - res.farfield.freq) < 1.0
              and abs(res.currents["freq"] - 200e6) > 1e6,
              res.currents["freq"])
        # per-frequency currents: one per pattern, same frequencies, same
        # physical wire, physically DIFFERENT distributions across the band
        alls = getattr(res, "currents_all", [])
        check("currents_all has one entry per solved pattern frequency",
              len(alls) == len(res.farfields)
              and all(abs(c["freq"] - f.freq) < 1.0
                      for c, f in zip(alls, res.farfields)), len(alls))
        spans = [float((_np.asarray(c["pos_m"]).max(0)
                        - _np.asarray(c["pos_m"]).min(0)).max()) for c in alls]
        check("every entry spans the same physical wire",
              max(spans) - min(spans) < 0.01 * max(spans), (min(spans), max(spans)))
        peaks = [float(_np.asarray(c["i_mag"]).max()) for c in alls]
        check("the distributions really differ across the band (not one "
              "table repeated)", len({round(p, 6) for p in peaks}) > 5,
              [round(p, 4) for p in peaks])
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio per-frequency radiation-pattern gate")
    gate_parser()
    gate_writer()
    gate_wiring()
    gate_currents_blocks()
    gate_band()
    gate_segmentation()
    gate_polyline_deck()
    gate_live()
    print("-------------------")
    if FAILURES:
        raise SystemExit("PATTERN SWEEP GATE FAILED: " + "; ".join(FAILURES))
    print("PATTERN SWEEP GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
