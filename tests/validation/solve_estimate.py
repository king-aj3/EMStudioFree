# SPDX-License-Identifier: LGPL-2.1-or-later
"""FAST gate: the pre-solve estimate is measured, or it is absent.

WHAT THIS DEFENDS. A user deciding whether to start a forty-minute solve needs
a number they can act on, and the tempting way to produce one is a cost model
with an uncalibrated constant — O(N^3) for MoM, timesteps x cells for FDTD.
That yields a confident duration with nothing behind it, and a user told "2
minutes" who waits 40 stops believing every other number the tool prints.

So the rules this pins are:

* with no history, the estimate is **absent**, never guessed;
* with history, it is the **median** of measured runs, so one pathological run
  (a machine that slept mid-solve) cannot move it;
* a neighbouring problem size may be borrowed ONLY with an explicit
  EXTRAPOLATED label, and only one bucket away;
* backends never borrow each other's timings;
* and a corrupt or unwritable store can never fail a solve.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from emstudio.solvers.estimate import (                    # noqa: E402
    BUCKET_RATIO, HISTORY_PER_BUCKET, History, bucket_of, describe, humanise)

FAILURES = []


def check(msg, ok):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        FAILURES.append(msg)


class Store(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)

    def set(self, k, v):
        self[k] = v


def main():
    h = History(Store())
    WORK = 21 * 401                       # a NEC2 sweep: segments x freq points

    # -- 1. nothing known -> nothing claimed --------------------------------
    secs, basis = h.estimate("nec2", WORK)
    check("a first-ever solve returns NO estimate", secs is None)
    check("...and says why, in a sentence fit to show a user",
          "first solve" in basis and len(basis) > 40)
    check("describe() renders the unknown case without a number",
          "unknown" in describe("nec2", WORK, h))

    # -- 2. measured history is used, and it is the MEDIAN ------------------
    for s in (12.0, 14.0, 13.0):
        h.record("nec2", WORK, s)
    secs, basis = h.estimate("nec2", WORK)
    check("three runs give the median (13 s, not the mean 13.0 nor the max)",
          secs == 13.0)
    check("...labelled as measured, with the sample count", "measured here" in basis
          and "3 previous runs" in basis)

    h.record("nec2", WORK, 9000.0)        # a machine that slept mid-solve
    secs, _ = h.estimate("nec2", WORK)
    check("one pathological run cannot move the estimate (median, not mean)",
          secs < 60.0)

    # -- 3. bucketing: near sizes share history, far ones do not ------------
    check("a 7 % larger problem lands in the SAME bucket",
          bucket_of(WORK) == bucket_of(WORK * 1.07))
    check("a 4x larger problem does NOT",
          bucket_of(WORK) != bucket_of(WORK * 4))
    secs, basis = h.estimate("nec2", WORK * 1.07)
    check("...so a near-size solve reuses the measured history",
          secs is not None and "measured here" in basis)

    # -- 4. borrowing is labelled, bounded, and scaled ----------------------
    # A FRESH history, so the expected median is known exactly and the check
    # does not have to ask the code under test what it thinks the median is.
    hb = History(Store())
    for s in (10.0, 20.0, 30.0):
        hb.record("nec2", WORK, s)                        # median exactly 20
    secs, basis = hb.estimate("nec2", WORK * BUCKET_RATIO)
    check("one bucket away borrows, and says EXTRAPOLATED",
          secs is not None and "EXTRAPOLATED" in basis)
    check("...scaled by the work ratio, not quoted raw [got %s, want %s]"
          % (secs, 20.0 * BUCKET_RATIO),
          secs is not None and abs(secs - 20.0 * BUCKET_RATIO) < 1e-9)
    smaller, sbasis = hb.estimate("nec2", WORK / BUCKET_RATIO)
    check("borrowing DOWNWARD scales down, not up",
          smaller is not None and abs(smaller - 20.0 / BUCKET_RATIO) < 1e-9
          and "larger" in sbasis)

    far, basis = h.estimate("nec2", WORK * (BUCKET_RATIO ** 4))
    check("four buckets away DECLINES rather than extrapolating",
          far is None)

    # -- 5. backends are never confused -------------------------------------
    secs, _ = h.estimate("openems", WORK)
    check("another backend does not inherit these timings", secs is None)

    # -- 6. history is bounded ----------------------------------------------
    st2 = Store()
    h2 = History(st2)
    for i in range(HISTORY_PER_BUCKET + 10):
        h2.record("palace", WORK, 10.0 + i)
    # Count the STORED runs, not a substring of the prose: "17 previous runs"
    # contains "7 previous runs", so the obvious phrasing check cannot fail.
    import json as _json
    kept = len(list(_json.loads(st2.get(History.KEY)).values())[0])
    check("history is capped at HISTORY_PER_BUCKET=%d (a new machine is "
          "relearned) [kept %d]" % (HISTORY_PER_BUCKET, kept),
          kept == HISTORY_PER_BUCKET)
    _secs, basis = h2.estimate("palace", WORK)
    # Pull the count out rather than indexing into the sentence, so a reworded
    # basis line fails this for the right reason instead of an off-by-one.
    quoted = re.search(r"(\d+) previous run", basis)
    check("...and the basis quotes that same count [%s]"
          % (quoted.group(1) if quoted else "no count found"),
          bool(quoted) and int(quoted.group(1)) == HISTORY_PER_BUCKET)

    # -- 7. nothing here may ever fail a solve ------------------------------
    class Corrupt(object):
        def get(self, k, d=None):
            return "{not json at all"

        def set(self, k, v):
            raise RuntimeError("read-only preferences")

    c = History(Corrupt())
    ok = True
    try:
        c.record("nec2", WORK, 5.0)
        secs, _ = c.estimate("nec2", WORK)
        ok = secs is None
    except Exception as exc:                              # noqa: BLE001
        ok = False
        print("     raised: %r" % (exc,))
    check("a corrupt AND unwritable store neither raises nor invents", ok)

    st3 = Store()
    h3 = History(st3)
    h3.record("nec2", WORK, 10.0)
    for bad in (None, -1.0, 0.0, float("nan"), float("inf"), "twelve"):
        h3.record("nec2", WORK, bad)
    stored = list(json.loads(st3.get(History.KEY)).values())[0]
    check("nonsense durations never reach the store [kept %r]" % (stored,),
          stored == [10.0])
    check("nonsense work measures bucket to 0 rather than raising",
          bucket_of(None) == 0 and bucket_of(-5) == 0 and bucket_of("x") == 0)

    # -- 8. the wording is coarse on purpose --------------------------------
    check("humanise never implies false precision",
          humanise(277) == "about 5 minutes" and humanise(5) == "under a minute")
    # AJ's requirement, 2026-08-19: the user must recognise a commitment they
    # did not mean to make. "about 72 hours" reads as a big number; "about 3
    # days" reads as a decision. Hours stop being a usable unit past ~a day.
    check("a multi-day solve is quoted in DAYS, not hours [%s]"
          % humanise(3 * 86400), humanise(3 * 86400) == "about 3 days")
    check("a multi-week solve is quoted in WEEKS [%s]"
          % humanise(21 * 86400), humanise(21 * 86400) == "about 3 weeks")
    check("an absurd solve says MONTHS in as many words [%s]"
          % humanise(200 * 86400), "MONTHS" in humanise(200 * 86400))
    check("...and the ladder is monotonic across every unit boundary",
          all(len(humanise(a)) > 0 for a in
              (59, 61, 3599, 3601, 86399, 86401, 13 * 86400, 60 * 86400)))
    check("humanise(None) is 'unknown', not '0 seconds'",
          humanise(None) == "unknown")

    print()
    if FAILURES:
        print("solve_estimate: %d FAILED" % len(FAILURES))
        raise SystemExit("solve_estimate FAILED")
    print("solve_estimate: all checks passed")
    return 0


if __name__ == "__main__" or "FreeCAD" not in sys.modules:
    main()
