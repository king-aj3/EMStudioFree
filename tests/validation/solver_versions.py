# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the version Solver Setup shows you is a version.

**This gate exists to give Solver Setup a user-visible NUMBER.** It was the one
capability in `docs/TUTORIALS.md` with no anchor — installing a backend has no
measurable output, so its tutorial said so out loud rather than inventing one.
The standing order calls an unanchored capability a FINDING, and this closes it:
the number a user can check is **the version string in the Solver Setup table**.

Writing it found four real defects, all user-visible, none failing any test:

======================  ==================================================
``ElmerSolver``         ``ELMER SOLVER (v 26.2) STARTED AT: 2026/08/20 19:15:27``
``openEMS``             ``| openEMS 64bit -- version v0.37.0-rc1``
``FastHenry``           ``FastHenry Version 3.0.1 (28May12)   see file ...``
``palace``              *(prints no version at all)*
======================  ==================================================

⚠⚠ **Elmer is the bad one.** Its line carries a RUN TIMESTAMP, so the version
column changed every time the user pressed Re-detect. A version that is
different each time you look at it is worse than no version, because it makes
the whole table look untrustworthy — and nothing caught it, because nothing
read that column.

**What is asserted, and why each rule:**

1. **Every backend's REAL ``--version`` output normalises to its true version.**
   The fixtures below are verbatim strings captured from the binaries on
   2026-08-20 — not invented, and not paraphrased.
2. **A timestamp is never mistaken for a version.** Elmer's date is
   ``2026/08/20`` (slashes) and its clock ``19:15:27`` (colons); a looser
   pattern would pick one of them, which is precisely the trap.
3. **An absent version stays absent.** Palace prints none, so the answer is
   ``""``. A plausible-looking invented version is worse than a blank, because
   a user would report it back to us as fact.
4. **Help text is not a version.** Several backends run their version line
   straight into usage output.
5. **The fixtures still match the binaries on THIS box.** Every backend
   actually installed is probed for real and must report the version the
   docs quote — and since 2026-08-29 that half **enforces by default**
   rather than waiting to be switched on. See the long comment at check 6
   for why a fixture alone was not enough, and why an opt-IN was no better
   than no check at all.

Pure python3 — no third-party imports. The parser checks (1-4) need no
binaries, because the fixtures ARE the binaries' output; the live
cross-check (5) probes whatever is installed and says out loud what was
absent. Measured 2026-08-21 with all seven backends present: ~1.5 s, of
which Elmer is ~0.7 s because `ElmerSolver --version` starts the solver.
FAST tier.
Pass: exit 0 and 'SOLVER VERSIONS GATE PASSED'.
Fail: exit 1 and 'SOLVER VERSIONS GATE FAILED'.
Opted out (``EMSTUDIO_VERSION_REFERENCE=0``) **while a live mismatch was
standing**: exit 3 and 'SOLVER VERSIONS GATE SKIPPED' — never the PASS
token, because a run that suppressed a mismatch did not earn one.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


#: VERBATIM ``--version`` output, captured from the real binaries on this
#: project's Linux box, 2026-08-20. Keep them verbatim: the moment one is
#: "tidied up" it stops testing what the tool actually prints, which is the
#: only thing that matters here.
REAL_OUTPUT = [
    ("gmsh", "4.12.1", "4.12.1"),
    ("nec2", "nec2c 1.3.1", "1.3.1"),
    ("elmer", "ELMER SOLVER (v 26.2) STARTED AT: 2026/08/20 19:15:27", "26.2"),
    ("openems", "| openEMS 64bit -- version v0.37.0-rc1", "0.37.0-rc1"),
    ("fasthenry",
     "FastHenry Version 3.0.1 (28May12)        see file default_opts.c for d",
     "3.0.1"),
    # ⚠ 2512, not 2606, and that is DELIBERATE. The resolver was changed to
    # prefer the COMPLETE v2512 tree over the newer-but-hollow
    # `2606.0~rc2-1` stub, so 2512 is what Solver Setup shows a user. This
    # fixture kept quoting 2606 and the live cross-check could not say so,
    # because it only asserted when EMSTUDIO_VERSION_REFERENCE was set and
    # that export lives in ~/.profile — login shells only, so never CI and
    # never an agent run. Corrected 2026-08-29 once the check started
    # enforcing by default and went honestly red.
    ("openfoam", "OpenFOAM v2512 (ESI, apt-esi)", "2512"),
    ("palace", "", ""),
]


def main():
    print("EMStudio Solver Setup version-readout validation gate")
    from emstudio.setup.solvers import version_number

    # 1. every real string normalises to the version a user would quote
    for key, raw, want in REAL_OUTPUT:
        got = version_number(raw)
        check("%s reports %s" % (key, want or "no version (correctly blank)"),
              got == want, "got %r from %r" % (got, raw[:52]))

    # 2. the Elmer trap, stated as its own check so it cannot regress quietly
    elmer = version_number(
        "ELMER SOLVER (v 26.2) STARTED AT: 2026/08/20 19:15:27")
    check("a RUN TIMESTAMP is never read as a version "
          "(the column used to change every Re-detect)",
          elmer == "26.2" and "2026" not in elmer and ":" not in elmer,
          elmer)

    # 2b. ⚠ THE ORDERING RULE, and it needed a fixture to become real.
    # Measured 2026-08-20: on ALL SIX real backend strings the marked pattern
    # and the bare dotted pattern return the SAME answer, so "try the marked
    # one first" was defensive decoration rather than a tested property — a
    # rule that cannot fail is not a rule. Elmer's date escapes the dotted
    # pattern only because it uses SLASHES; a tool printing a DOTTED date is
    # the case that separates them, and dotted dates are a real convention.
    check("a DOTTED date does not beat the marked version "
          "(this is what makes the ordering rule load-bearing)",
          version_number("built 2026.08.20, version 1.2.3") == "1.2.3",
          version_number("built 2026.08.20, version 1.2.3"))

    # 3. never invent one
    for blank in ("", "   ", "no version information available",
                  "usage: solver [options]"):
        check("no version invented from %r" % blank[:34],
              version_number(blank) == "")

    # 4. help text following the version must not be swallowed into it
    check("a version does not run on into help text",
          version_number("FastHenry Version 3.0.1 (28May12)  see file "
                         "default_opts.c for d") == "3.0.1")

    # 5. a date-only line yields nothing rather than a date
    check("a date-only line yields no version, not a date",
          version_number("built 2026/08/20 19:15:27") == "",
          version_number("built 2026/08/20 19:15:27"))

    # 6. ⚠⚠ THE LIVE CROSS-CHECK. Everything above proves the PARSER is right
    # about strings captured on 2026-08-20. None of it proves those strings are
    # still what the binaries on this box print — and a fixture nobody
    # re-measures is exactly the claim that drifts.
    #
    # It is not theoretical. The Elmer CSC PPA ships DATED DEVEL SNAPSHOTS and
    # drops the previous one from the pool, so a routine `apt upgrade` moves
    # the installed solver underneath us without touching a line of EMStudio.
    # Should a snapshot ever bump the banner past "26.2", SEVEN surfaces quote
    # the old number — REAL_OUTPUT below, the docs/TUTORIALS.md version table,
    # two CHANGELOG lines, the version_number() docstring, the Elmer .sif
    # writer header, and the two live Elmer anchors — and before this check
    # every one of them would have stayed GREEN while going quietly wrong.
    # (⛳ The package version and the banner version are different numbers:
    # apt calls it 9.0-0ppa0-<date>, the solver calls itself 26.2. Only the
    # banner is user-visible, so only the banner is gated here.)
    #
    # A mismatch FAILS, and the message names the remedy: usually "the install
    # legitimately moved, update the fixture and the surfaces", not "the parser
    # broke". A gate that fails without saying what to do just gets muted.
    #
    # ⛳ An ABSENT backend is skipped and SAID OUT LOUD — never silently
    # counted as coverage. It must not fail the gate: FAST tier has to pass on
    # a bare box with no solvers, and checks 1-4 genuinely ran there. But a run
    # that live-checked NOTHING must not read like a run that live-checked
    # everything, so the count is printed either way.
    # ⚠⚠ THE LIVE TABLE DESCRIBES ONE MACHINE, SO ONLY THAT MACHINE MAY FAIL
    # ON IT (AJ's ruling, 2026-08-21).
    #
    # REAL_OUTPUT pins the REFERENCE box's versions — the numbers every doc,
    # tutorial and CHANGELOG quotes. That makes a mismatch mean two completely
    # different things depending on where it runs:
    #
    #   * on the reference box  -> the solver moved under the docs. REAL. Fail.
    #   * anywhere else         -> that developer simply has different solvers.
    #
    # Measured on the Windows work box 2026-08-21: gmsh 4.15.2 (table 4.12.1),
    # nec2 2.3.4 (table 1.3.1), OpenFOAM 2512 (table 2606) — three failures,
    # none of them a defect. Meanwhile CI is GREEN because the runner installs
    # none of these, so all seven skip. The gate therefore passed in CI, passed
    # on the reference box, and failed ONLY on a developer box — the one place
    # a developer actually runs the battery, which is how a red gets muted.
    #
    # ⛳ The parser checks (1-4 above) stay HARD everywhere. They test code, and
    # they are what caught the four user-visible defects this gate was written
    # for. Only the live cross-check is scoped, because only it is about one
    # machine's installed binaries.
    #
    # ⚠⚠ **A check nobody enables is a check that never runs — and this one
    # was never enabled.** (Measured 2026-08-29, and it is why the default
    # below is now the other way round.)
    #
    # The scoping above shipped as an OPT-IN: `EMSTUDIO_VERSION_REFERENCE=1`,
    # exported from the reference box's `~/.profile`. `~/.profile` is read by
    # LOGIN shells only, and `~/.bashrc` returns early when non-interactive —
    # so the variable is absent from every shell that actually runs the
    # battery (CI, a `python3 tests/validation/run_battery.py` from an editor
    # or an agent, a cron job). On the reference box itself, on that date, the
    # live probe read **OpenFOAM 2512 against a table saying 2606**, printed
    # the mismatch as advisory, and exited 0 with 'GATE PASSED'.
    #
    # And the mismatch was REAL, not a foreign developer's install: discovery
    # was deliberately changed to prefer the COMPLETE v2512 tree over the
    # newer-but-hollow `2606.0~rc2-1` stub, so the number Solver Setup shows a
    # user moved — while REAL_OUTPUT here and the docs/TUTORIALS.md version
    # table kept quoting 2606. That is EXACTLY the drift this check was
    # written to catch, standing in the open, reported by the gate, and green.
    # An advisory check plus an opt-in nobody's automation exports is not a
    # weaker check; it is decoration.
    #
    # ⛳ **So the default is now ENFORCE: any backend PRESENT on this box must
    # report the version the table claims.** Absent backends still skip, out
    # loud (FAST tier must stay green on a bare box with no solvers, where
    # checks 1-5 genuinely ran).
    #
    # AJ's one-machine ruling survives as an explicit OPT-OUT — set
    # `EMSTUDIO_VERSION_REFERENCE=0` on a developer box that legitimately
    # carries different solvers (the Windows work box: gmsh 4.15.2, nec2
    # 2.3.4). What it CANNOT do is buy a green: if opting out actually
    # suppressed a mismatch, the gate prints SKIPPED, returns 3, and names the
    # drift, because an exit code that claims success the run did not earn is
    # the entire disease this file exists to treat. Opting out on a box whose
    # solvers DO match the table costs nothing — nothing was hidden, so the
    # pass still stands. `=1` keeps working: it is simply the default now.
    from emstudio.setup.solvers import find_backend

    enforce = os.environ.get("EMSTUDIO_VERSION_REFERENCE", "1") not in ("", "0")

    covered, absent, drift = 0, [], []
    for key, _fixture, want in REAL_OUTPUT:
        info = find_backend(key)
        if not info.found:
            absent.append(key)
            continue
        covered += 1
        got = version_number(info.version)
        ok = (got == want)
        detail = ("reports %r" % got) if ok else (
            "installed reports %r but the table says %r — if the install "
            "legitimately moved, update REAL_OUTPUT above AND every surface "
            "quoting it: docs/TUTORIALS.md version table, CHANGELOG, the "
            "version_number() docstring, and for Elmer also "
            "emstudio/solvers/elmer/writer.py plus the open_coil_elmer / "
            "coil_inductance_elmer anchors" % (got, want))
        if not ok:
            drift.append("%s: installed %r vs table %r" % (key, got, want))
        if enforce:
            check("LIVE %s still reports %s" % (key, want or "no version"),
                  ok, detail)
        else:
            print("  {0}  LIVE {1} {2}".format(
                "ok  " if ok else "....", key, detail))

    if not enforce:
        # (!) not the warning-sign glyph: U+26A0 is outside cp1252, and on a
        # default Windows console this print DIED with UnicodeEncodeError
        # BEFORE the advisory text, the drift list and the PASS banner — the
        # exact safety net this branch exists to provide never printed. The
        # battery masked it by forcing PYTHONIOENCODING=utf-8 for child
        # gates; run STANDALONE the gate was a hard red on any stock
        # PowerShell/cmd console (reproduced on the work box, 2026-08-24).
        # Printed OUTPUT here stays ASCII-safe; docstrings can keep glyphs.
        print("  ....  (!) LIVE CROSS-CHECK OPTED OUT ON THIS BOX — "
              "EMSTUDIO_VERSION_REFERENCE=0, so the %d drift(s) above did NOT "
              "fail the checks. Enforcing is the DEFAULT; unset the variable "
              "to restore it. A suppressed drift still ends this run as "
              "SKIPPED (exit 3), never PASSED." % len(drift))
        if drift:
            print("  ....  drift seen (suppressed): %s" % "; ".join(drift))

    if absent:
        print("  ....  live cross-check SKIPPED (not installed): %s"
              % ", ".join(absent))
    print("  ....  live cross-check covered %d of %d backends%s"
          % (covered, len(REAL_OUTPUT),
             "" if covered else
             " — NONE INSTALLED, so nothing was checked against a real binary "
             "on this box"))

    if FAILURES:
        print("SOLVER VERSIONS GATE FAILED (%d)" % len(FAILURES))
        return 1
    # Only reachable with the opt-out set AND a mismatch it swallowed: with
    # enforcement on, a drift is already a FAILURE above. A skip must never
    # print the PASS token, so this prints its own and returns its own code —
    # distinct from 1 so a caller can tell "your box differs from the
    # reference table" from "the parser broke".
    if drift:
        print("SOLVER VERSIONS GATE SKIPPED (live cross-check opted out while "
              "%d drift(s) stood: %s)" % (len(drift), "; ".join(drift)))
        return 3
    print("SOLVER VERSIONS GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
