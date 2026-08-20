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

Pure python3 — no binaries needed, because the fixtures ARE the binaries'
output. FAST tier.
Pass: exit 0 and 'SOLVER VERSIONS GATE PASSED'.
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
    ("openfoam", "OpenFOAM v2606 (ESI, apt-esi)", "2606"),
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

    if FAILURES:
        print("SOLVER VERSIONS GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("SOLVER VERSIONS GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
