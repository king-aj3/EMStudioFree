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

HOW MUCH OF IT ACTUALLY RAN
---------------------------
Three of the nine sub-gates need FreeCAD (two of them) or FreeCAD *and* a NEC2
binary (one), so under the plain-python3 FAST battery **63 of the 88 checks
never execute**. Until 2026-08-29 that run printed a bare
``PATTERN SWEEP GATE PASSED`` and ``docs/CAPABILITIES.md`` sold the gate as
"88 checks" — so the headline number and the number a reader could have
watched go by differed by 25, with nothing on screen saying so. That is the
same defect class this repo has now found four times (the four openEMS gates
in 2026-08-05, the eight FreeCAD self-skippers in 2026-08-23): a gate that
reports a pass it did not earn is worse than a gate that is missing.

So every run now ends with an EXECUTED-OF-TOTAL line, every skip is named in
that summary with the number of checks it took with it, and the terminal token
is ``PASSED`` only when all 88 ran — a partial run says ``PARTIAL`` instead.

⚠ A partial run still exits **0**, deliberately. ``run_battery.FAST`` lists
``"pattern_sweep": None`` — no requirement — which is the battery DECLARING
that the python3-reachable 63 must run on every push; making the partial run
non-zero would delete this gate from CI rather than make it honest. Set
``EMSTUDIO_GATE_REQUIRE_ALL=1`` to demand the full 88 (release runs, and any
run where you believe FreeCAD/NEC2 are present): a skip then exits non-zero
with ``PATTERN SWEEP GATE INCOMPLETE``.

The per-tier counts are AUDITED against what really ran, so this coverage
number cannot rot the way the doc's did: add or delete a ``check`` call in a
tier that runs on your interpreter and the gate FAILS until ``TIERS`` is
updated.

⚠ Prose in this file must NOT spell that call with its bracket attached:
``capability_counts`` derives the number CAPABILITIES.md advertises by
counting that exact token TEXTUALLY (comment lines excepted), so a docstring
mentioning it would inflate the very count it describes. Say "a ``check``
call".

Pass: exit 0 and 'PATTERN SWEEP GATE PASSED' (all 88 checks).
Partial: exit 0 and 'PATTERN SWEEP GATE PARTIAL' (a tier could not run).
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

FAILURES = []

#: (tier, checks it would have run, why it could not) — filled by ``_skip``.
SKIPS = []

#: tier name -> how many ``check()`` calls it actually made this run.
EXECUTED = {}

#: The tier ``check()`` should bill its calls to. A list because the gates are
#: plain functions and this is rebound by ``main``'s driver loop, not passed.
_TIER = [None]

#: Sub-gates in RUN ORDER: (function name, checks executed when it runs, what
#: it needs — None = always runnable).
#:
#: ⚠ The count is EXECUTIONS, not source lines, and the two differ on purpose:
#: ``gate_writer`` has five ``check(`` sites but one sits in a two-deck loop
#: (six executions), and ``gate_flat_band`` has nine sites of which exactly
#: EIGHT can run in any one interpreter — its last two are the try/else arms of
#: one statement, the same property proven live under freecadcmd and by AST
#: under python3. Counting source text would therefore report a total no run
#: can reach, which is precisely the kind of unearned number this block exists
#: to stop. ``_audit_coverage`` checks these against reality after the run.
#:
#: ⚠ The static and executed bases AGREE AT 88 BY COINCIDENCE, worth knowing
#: before anyone "simplifies" one into the other: ``capability_counts``
#: re-derives the number CAPABILITIES.md advertises by counting 88 static call
#: sites, and a full run executes 88, only because gate_writer's loop (+1)
#: exactly cancels gate_flat_band's unreachable arm (-1). Move either and the
#: two part company. Note also what that static basis CANNOT see, and what
#: this table exists for: on the python3 battery 25 of those 88 never run.
TIERS = [
    ("gate_parser",           7, None),
    ("gate_flat_band",        8, None),
    ("gate_writer",           6, "FreeCAD"),
    ("gate_wiring",          17, None),
    ("gate_currents_blocks", 11, None),
    ("gate_band",            14, None),
    ("gate_segmentation",     6, None),
    ("gate_polyline_deck",    7, "FreeCAD"),
    ("gate_live",            12, "FreeCAD + a NEC2 backend"),
]

#: Turns every skip into a failure. For release runs and for anyone who
#: believes the backends ARE installed — a skip then means the environment is
#: not what you thought, which is a result worth an exit code.
REQUIRE_ALL = os.environ.get("EMSTUDIO_GATE_REQUIRE_ALL", "") not in ("", "0")


def check(label, ok, detail=""):
    # Bill the call to the running tier BEFORE anything can go wrong, so the
    # coverage audit sees a truncated tier (an early `return`, a swallowed
    # exception) as the short count it is.
    EXECUTED[_TIER[0]] = EXECUTED.get(_TIER[0], 0) + 1
    if not ok:
        FAILURES.append(label)
    print("  {0} - {1}{2}".format("ok  " if ok else "FAIL", label,
                                  ("   [" + str(detail)[:96] + "]") if detail else ""))


def _skip(reason):
    """Record — not merely print — that the running tier did not run.

    The old code printed a bare ``skip`` line mid-output and returned, so the
    summary and the exit code both behaved as though nothing had been missed.
    Recording it is what lets the summary say 63-of-88 and the token say
    PARTIAL.
    """
    SKIPS.append((_TIER[0], dict((n, c) for n, c, _ in TIERS).get(_TIER[0], 0),
                  reason))
    print("  skip  {0} — {1}".format(_TIER[0], reason))


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

    # ⚠ That check CANNOT fail on _TWO_BLOCK alone — the fixture is already
    # ascending, so ``== sorted(...)`` holds whether the parser sorts or not.
    # Proven blind on 2026-08-20: deleting ``out.sort(key=...)`` from
    # ``parse_radiation_patterns_all`` left this gate exit 0. The identical
    # lesson was learned for the CURRENT parser on 2026-08-07 (see
    # gate_currents_blocks, which builds its fixture descending for exactly
    # this reason) and was never carried across to the far-field parser. The
    # far-field sort is load-bearing for the same reason the current one is:
    # the results dialog aligns currents to far fields BY INDEX.
    half = _TWO_BLOCK.index("                               ---------"
                            " FREQUENCY --------", 100)
    reversed_file = _TWO_BLOCK[half:] + _TWO_BLOCK[:half]
    rpath = os.path.join(tempfile.mkdtemp(), "case_ff_desc.out")
    with open(rpath, "w", encoding="utf-8") as fh:
        fh.write(reversed_file)
    rffs = parser.parse_radiation_patterns_all(rpath)
    check("a file whose blocks arrive DESCENDING still returns ascending",
          [round(f.freq / 1e6) for f in rffs] == [200, 400],
          [f.freq for f in rffs])
    # Sorting the frequencies while leaving the gain arrays where they were
    # would satisfy the check above and silently pair every pattern with the
    # wrong frequency — the one failure mode a frequency-only check cannot see.
    check("and each DESCENDING block keeps its OWN gains through the sort",
          (round(float(rffs[0].gain.max()), 2),
           round(float(rffs[1].gain.max()), 2)) == (1.0, 5.0),
          [float(f.gain.max()) for f in rffs])

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
    skips under plain python exactly as `gate_polyline_deck` does — but the
    skip is RECORDED (see ``_skip``), because six unrun checks that print
    nothing are how "88 checks" came to mean 63.
    """
    try:
        import FreeCAD
    except ImportError:
        # ⚠ NARROWED from `except Exception` on 2026-08-29. The broad form
        # turned ANY failure of the import machinery — a half-installed
        # FreeCAD, a broken numpy under it (0.21.2 on macOS does exactly
        # that), a C-extension ABI clash — into a silent, passing skip. Only
        # "the module is not here" is a legitimate reason not to run; every
        # other exception is a real regression and must reach the caller.
        _skip("needs FreeCAD (run under freecadcmd)")
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
    except ImportError:                     # narrowed 2026-08-29, see gate_writer
        _skip("needs FreeCAD (run under freecadcmd)")
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

    # An explicit probe BEFORE the work, not an `except` around it: "the
    # binary is absent" is the ONLY condition allowed to skip this tier, and
    # a probe cannot accidentally swallow a solver crash the way a try/except
    # over the run would.
    if not solver_setup.find_backend("nec2").found:
        _skip("no NEC2 backend installed")
        return
    try:
        import FreeCAD  # noqa: F401
    except ImportError:                     # narrowed 2026-08-29, see gate_writer
        _skip("needs FreeCAD (run under freecadcmd)")
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


def gate_flat_band():
    """The flat-band guard on pattern-frequency selection, BOTH backends.

    openEMS has carried the guard in its generated deck since v1.5.0 (the
    Ka-band horn picked 28.45 GHz at one mesh and 39.55 at another). NEC2 had
    a bare ``min_s11()`` argmin until 2026-08-24 — and the openEMS writer's
    own comment named that gap out loud. The shared rule now lives in
    ``SweepResult.pattern_frequency()`` with ONE constant in
    ``emstudio.post.sparams``; these checks pin the rule and the unification.

    ⚠ Named coverage hole: the NEC2 runner's CALL SITE (nec2/runner.py) is
    exercised live only by the SOLVER tier, and on a resonant dipole both the
    guarded and unguarded choices agree — so a revert to ``min_s11()`` there
    is caught by none of these checks. The method and the constant are what
    is pinned here; the call site is prose-reviewed.
    """
    print(" flat-band pattern-frequency guard:")
    import numpy as np

    from emstudio.post import sparams
    from emstudio.post.sparams import SweepResult

    f = np.linspace(1e9, 2e9, 41)
    z0 = 50.0

    # a real resonance: |S11| dips tens of dB at 1.4 GHz
    dip = 10.0 ** (-(2.0 + 28.0 * np.exp(-((f - 1.4e9) / 6e7) ** 2)) / 20.0)
    res = SweepResult(f, z0 * (1 + dip) / (1 - dip), z0=z0)
    f_res, note = res.pattern_frequency()
    check("resonant sweep: argmin wins", abs(f_res - 1.4e9) < 30e6,
          "picked %.4g Hz" % f_res)
    check("  ...silently", note == "")
    check("  ...and agrees with min_s11", f_res == res.min_s11()[0])

    # a FLAT band: 0.4 dB of mesh ripple around -18 dB, minimum parked at
    # the band EDGE, where argmin would report it
    rng = np.random.RandomState(7)
    db = -18.0 + 0.2 * rng.standard_normal(f.size)
    db[0] = -18.6                       # the noise minimum, at the edge
    mag = 10.0 ** (db / 20.0)
    flat = SweepResult(f, z0 * (1 + mag) / (1 - mag), z0=z0)
    f_flat, note = flat.pattern_frequency()
    check("flat band: the CENTRE wins, not the edge minimum",
          abs(f_flat - 1.5e9) < 30e6,
          "picked %.4g Hz; bare argmin would say %.4g"
          % (f_flat, flat.min_s11()[0]))
    check("  ...and says so out loud",
          "no resonance" in note and "%.4g" % f_flat in note, note[:70])
    check("  ...deterministically (mesh-independence is the point)",
          flat.pattern_frequency()[0] == f_flat)

    # the span boundary: just ABOVE the threshold argmin must win again
    db2 = np.full(f.size, -10.0)
    db2[10] = -10.0 - (sparams.FLAT_S11_SPAN_DB + 0.1)
    mag2 = 10.0 ** (db2 / 20.0)
    edge = SweepResult(f, z0 * (1 + mag2) / (1 - mag2), z0=z0)
    check("span just above the threshold: argmin again",
          edge.pattern_frequency() == (float(f[10]),
                                       edge.pattern_frequency()[1])
          and edge.pattern_frequency()[1] == "",
          "picked %.4g Hz" % edge.pattern_frequency()[0])

    # ONE constant, ONE rule: the openEMS deck writer must bake the SAME
    # threshold sparams applies, or the two backends drift apart again.
    # Under freecadcmd the LIVE identity is checked; under plain python3 the
    # writer cannot even import (its module chain reaches `import FreeCAD`),
    # so the same property is pinned STRUCTURALLY: an ImportFrom of sparams'
    # name and no local re-assignment — AST, not source text, so a comment
    # cannot defeat it (the solve_confirm_coverage precedent).
    try:
        from emstudio.solvers.openems import writer as ow
    except ModuleNotFoundError:
        import ast
        src = open(os.path.join(_ROOT, "emstudio", "solvers", "openems",
                                "writer.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        imported = any(isinstance(n, ast.ImportFrom)
                       and n.module == "emstudio.post.sparams"
                       and any(a.name == "FLAT_S11_SPAN_DB" for a in n.names)
                       for n in ast.walk(tree))
        assigned = any(isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name)
                               and t.id == "FLAT_S11_SPAN_DB"
                               for t in n.targets)
                       for n in ast.walk(tree))
        check("openEMS writer takes sparams' constant (AST route, python3)",
              imported and not assigned,
              "imported=%s locally-reassigned=%s - a second hand-kept copy "
              "of the threshold is the drift this exists for"
              % (imported, assigned))
    else:
        check("openEMS writer bakes sparams' own constant",
              ow.FLAT_S11_SPAN_DB is sparams.FLAT_S11_SPAN_DB,
              "two hand-kept copies of a threshold is the drift this exists "
              "for")


def _audit_coverage():
    """Did every tier that RAN run all of itself?

    The coverage number is only worth printing if it cannot drift, and there
    are two ways it drifts. A tier can be TRUNCATED — ``gate_parser`` returns
    early when the parser hands back the wrong number of blocks, and a future
    `return` or swallowed exception would do the same silently. Or a
    ``check`` call can be added to (or deleted from) a tier while ``TIERS``
    still quotes the old count, which is exactly how CAPABILITIES.md came to
    advertise a number no run produced. Both are FAILURES here, named.

    Only tiers that actually ran are audited: a skipped tier's shortfall is
    already reported, by name and by count, in the summary.
    """
    skipped = {name for name, _n, _why in SKIPS}
    for name, count, _need in TIERS:
        if name in skipped:
            continue
        got = EXECUTED.get(name, 0)
        if got != count:
            FAILURES.append(
                "{0} ran {1} of its {2} checks — a tier stopped short, or "
                "TIERS is stale".format(name, got, count))
    # A check billed to no tier at all means a check() call was added outside
    # the driver loop, where nothing counts it and the summary would under-
    # report the run.
    stray = set(EXECUTED) - {name for name, _c, _n in TIERS}
    if stray:
        FAILURES.append("check calls billed to no tier: {0}".format(
            sorted(str(s) for s in stray)))


def main():
    print("EMStudio per-frequency radiation-pattern gate")
    total = sum(count for _name, count, _need in TIERS)
    for name, _count, _need in TIERS:
        _TIER[0] = name
        globals()[name]()
    _TIER[0] = None
    _audit_coverage()

    executed = sum(EXECUTED.values())
    print("-------------------")
    print("checks executed: {0} of {1}".format(executed, total))
    for name, count, reason in SKIPS:
        print("  SKIPPED  {0:<20s} {1:2d} checks NOT run — {2}".format(
            name, count, reason))

    if FAILURES:
        raise SystemExit("PATTERN SWEEP GATE FAILED: " + "; ".join(FAILURES))
    if SKIPS:
        if REQUIRE_ALL:
            # The caller asked for the whole gate, so a skip is a failure and
            # gets an exit code that says so.
            raise SystemExit(
                "PATTERN SWEEP GATE INCOMPLETE: {0} of {1} checks ran; "
                "EMSTUDIO_GATE_REQUIRE_ALL is set and {2} tier(s) could not "
                "run: {3}".format(executed, total, len(SKIPS),
                                  "; ".join("{0} ({1})".format(n, r)
                                            for n, _c, r in SKIPS)))
        # Exit 0 — see the module docstring: run_battery tiers this gate FAST
        # with NO requirement, so the python3-reachable subset is meant to run
        # on every push. The token, not the exit code, is what carries the
        # honesty here, and it no longer reads as a full pass.
        print("PATTERN SWEEP GATE PARTIAL — {0} of {1} checks executed, {2} "
              "tier(s) SKIPPED above; run under freecadcmd with a NEC2 "
              "backend for {1}/{1}".format(executed, total, len(SKIPS)))
        return 0
    print("PATTERN SWEEP GATE PASSED — {0} of {1} checks executed".format(
        executed, total))
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    sys.exit(main())
