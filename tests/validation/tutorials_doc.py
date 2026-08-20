# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: every tutorial keeps its shape, and names a gate that exists.

``docs/TUTORIALS.md`` is the front door AJ's standing order created — at least
one tutorial for every capability EMStudio ships, so *"there is nothing showing
how to use EMStudio"* stops being true. Its value is entirely that each one
ends in a checkable number and names the automated test that pins it. A
tutorial that quietly loses its "Prove it" line, or names a gate file that was
renamed out from under it, is worse than no tutorial: it makes a promise of
checkability that it no longer keeps.

**Why this gate exists, specifically.** On 2026-08-20 a reply drafted for
r/rfelectronics said *"Five of them"* on the day the sixth shipped — a
duplicated COUNT going stale, in a post whose entire argument was that this
project's claims are checkable. The counts were removed from the prose that
day. This gate stops the structural version of the same rot.

What is checked, and why each one:

1. **Every numbered tutorial has all four parts** — Needs / Do / You should
   see / Prove it. That shape is the contract the file's own preamble states.
2. **Every "Prove it" names at least one gate file, and every named gate file
   EXISTS** in ``tests/validation/``. This is the check that would have caught
   a rename; it is also the only one here that reaches outside the document.
3. **No duplicate tutorial numbers**, and nothing in the outstanding table
   reuses a number already written. The near-term table carried TWO ``#7``
   rows until 2026-08-20 and numbered induction heating as 12 while the
   master list called it 7 — so a reader could not tell which "#7" was meant.
4. **No tutorial COUNT in the prose.** Written as a deny-list of number words
   followed by "tutorial(s)", because that is the exact phrasing that went
   stale twice.

⚠ **What this gate deliberately does NOT check:** whether the anchors are the
RIGHT numbers. It cannot — that needs the solver. The SOLVER-tier gates each
tutorial names are what pin the physics; this pins that the naming is honest.

Pure python3, no FreeCAD, no solvers. Runs in both the Pro and the exported
free tree (the tutorials file is public).
Pass: exit 0 and 'TUTORIALS DOC GATE PASSED'.
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DOC = os.path.join(_ROOT, "docs", "TUTORIALS.md")
_GATES = os.path.join(_ROOT, "tests", "validation")

#: Is this the PRO tree? ``emstudio/system/**`` is the tier boundary and is
#: removed wholesale by ``tools/export_free.py``, so its presence is the
#: cheapest honest test of which tree the gate is running in.
_IS_PRO_TREE = os.path.isdir(os.path.join(_ROOT, "emstudio", "system"))

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


#: The four parts every tutorial must carry, as they appear in the file. The
#: preamble's own table names these, so the gate and the contract cannot drift.
_PARTS = ("**Needs:**", "**Do**", "**You should see**", "**Prove it**")

#: A Pro stub is marked with the padlock in its heading.
_PRO_MARK = "🔒"

#: What a Pro stub MUST carry: what it does, the measured number, the tier it
#: is in (stated, never coy -- a teaser that hides its tier is the
#: "crippled free version" accusation waiting to happen), and the gate.
_STUB_PARTS = ("**What it does.**", "**What it measured.**",
               "**Free alternative:**", "**Gate:**")

#: What a Pro stub must NOT carry. These are the headings that turn a teaser
#: into a walkthrough; their presence means the how-to has leaked out of Pro.
_PRO_FORBIDDEN = ("**Do**", "**You should see**")

#: Number words that have actually appeared in front of "tutorial(s)" here.
#: A deny-list rather than a regex for any digit, because "#12" and "TN-688"
#: are legitimate and a blanket digit rule would fire on every anchor.
_COUNT_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten", "eleven", "twelve", "eighteen", "twenty-one",
                "twenty-seven")


def _sections(text):
    """[(number, title, body)] for each '## N. Title' tutorial section."""
    heads = list(re.finditer(r"^## (\d+)\.\s+(.+)$", text, re.M))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((int(m.group(1)), m.group(2).strip(), text[m.end():end]))
    return out


def main():
    if not os.path.isfile(_DOC):
        print("FAIL - docs/TUTORIALS.md is missing")
        print("TUTORIALS DOC GATE FAILED")
        return 1

    text = open(_DOC, encoding="utf-8").read()
    secs = _sections(text)
    check("the file contains numbered tutorials at all", bool(secs),
          "%d found" % len(secs))
    if not secs:
        print("TUTORIALS DOC GATE FAILED")
        return 1

    # 1. shape -- and Pro STUBS have their own, stricter contract.
    #
    # ⚠ A 🔒 stub is NOT a tutorial with parts missing. AJ's 2026-08-20 ruling
    # is that the Pro four get a public taste of WHAT the capability does and
    # WHAT IT MEASURED, with the steps Pro-side: "if a stub would let someone
    # reproduce the result without Pro, it has gone too far." So the absence of
    # a "Do" section is the POINT, and this gate enforces that absence rather
    # than tolerating it -- otherwise the paywall erodes one helpful edit at a
    # time and nobody notices until it is published.
    for num, title, body in secs:
        if _PRO_MARK in title:
            leaked = [p for p in _PRO_FORBIDDEN if p in body]
            check("#%d (Pro stub) gives the WHAT, never the HOW" % num,
                  not leaked, title[:40] if not leaked else
                  "leaks " + ", ".join(leaked))
            missing = [p for p in _STUB_PARTS if p not in body]
            check("#%d (Pro stub) keeps the stub contract" % num, not missing,
                  title[:40] if not missing else "missing " + ", ".join(missing))
            continue
        missing = [p for p in _PARTS if p not in body]
        check("#%d keeps the four-part shape" % num, not missing,
              title[:44] if not missing else "missing " + ", ".join(missing))

    # 2. every named gate file exists
    for num, title, body in secs:
        if _PRO_MARK in title:
            # Stubs name their gate on a "**Gate:**" line instead.
            m = re.search(r"\*\*Gate:\*\*(.+?)(?=\n\n|\n---|\Z)", body, re.S)
        else:
            m = re.search(r"\*\*Prove it\*\*(.+?)(?=\n---|\Z)", body, re.S)
        if not m:
            continue                      # already reported by the shape check
        named = set(re.findall(r"`?tests/validation/([A-Za-z0-9_]+\.py)`?",
                               m.group(1)))
        named |= set(re.findall(r"`([A-Za-z0-9_]+\.py)`", m.group(1)))
        check("#%d names a gate" % num, bool(named), ", ".join(sorted(named)))
        for g in sorted(named):
            present = os.path.isfile(os.path.join(_GATES, g))
            # ⚠ A 🔒 stub names a PRO gate, and this file is EXPORTED: the free
            # tree legitimately has no `system_*.py` or `assistant.py`, because
            # the export strips them. Demanding their presence there failed the
            # whole free battery the first time these stubs shipped.
            # ⛳ Strictness is kept exactly where it can be kept: in the PRO
            # tree every named gate must exist, so a rename is still caught at
            # the source of truth. Only the tier-stripped tree forgives it, and
            # only for stubs.
            if not present and _PRO_MARK in title and not _IS_PRO_TREE:
                print("  skip  #%d's gate %s — Pro-only, absent in the free "
                      "tree by design" % (num, g))
                continue
            check("#%d's gate %s exists" % (num, g), present)

    # 3. numbering is unambiguous, written vs planned
    nums = [n for n, _t, _b in secs]
    check("no duplicate tutorial numbers", len(nums) == len(set(nums)),
          str(nums))

    planned = set()
    for row in re.finditer(r"^\|\s*(\d+)\s*\|\s*[^|]+\|\s*"
                           r"(?:Analysis|Templates|Tools|System|Setup|Help)\s*\|",
                           text, re.M):
        planned.add(int(row.group(1)))
    clash = sorted(planned & set(nums))
    check("nothing planned reuses a written tutorial's number", not clash,
          "clashes: %s" % clash if clash else "%d still planned" % len(planned))

    # 4. no count in the prose
    bad = []
    for m in re.finditer(r"(\w+)?\s*([A-Za-z\-]+)\s+tutorials?\b", text, re.I):
        prev, word = (m.group(1) or "").lower(), m.group(2).lower()
        # "at LEAST one tutorial for every capability" is the standing order
        # itself -- a policy, not a count of what exists, and it cannot go
        # stale. Only a bare count can.
        if word in _COUNT_WORDS and prev != "least":
            line = text[:m.start()].count("\n") + 1
            bad.append("line %d: %r" % (line, m.group(0).strip()))
    check("no tutorial COUNT in the prose (it goes stale — it already did)",
          not bad, "; ".join(bad[:3]))

    if FAILURES:
        print("TUTORIALS DOC GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("TUTORIALS DOC GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
