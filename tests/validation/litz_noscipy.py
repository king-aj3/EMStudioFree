# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the SciPy-LESS litz proximity fallback.

**This gate exists because nothing ever ran the code it covers.** The battery
requires SciPy, so `_proximity_h`'s `except ImportError` branch — the one a
FreeCAD build without SciPy actually executes — had never been exercised by any
test. Two defects lived there undisturbed:

1. **A 5.9x over-estimate at x = 2**, fixed 2026-08-20 by warning once per
   session (the step itself is deliberate — see below).
2. **The asymptote's COEFFICIENT was wrong.** The branch returned ``0.166 * x``
   and the docstring stated that as the limit. The true slope is **1/8**: on
   the SciPy branch it converges to 0.12500 at x = 64..512, with
   H(x) -> (x-1)/8 to better than 1e-4. ``0.166 x`` read **33 % high even at
   x = 512**, where an asymptote should be exact. Fixed 2026-08-21.

⚠⚠ **Why `wire_fasthenry` could not catch either.** Its three proximity checks
(series limit, seam continuity at x = 0.5, monotonicity) all pass under the
fallback as readily as under the exact kernel — a monotone wrong curve is still
monotone. **A check that passes on both branches cannot tell you which one
ran.** This gate therefore compares the fallback against the exact kernel
rather than against a shape.

**How it runs the branch.** The battery has SciPy, so the fallback cannot be
reached in-process. A CHILD interpreter is spawned with a `sys.meta_path`
finder that raises ImportError for `scipy` and everything under it. The child
reports its values on stdout and the warning lands on stderr, which is what
keeps the two separable and lets the warning be COUNTED.

⚠ The child blocks the import rather than using a SciPy-less virtualenv. That
is the same failure the code catches (`except Exception` around
`from scipy.special import ...`), and it keeps the gate runnable anywhere. It
was cross-checked once against a real SciPy-less interpreter on 2026-08-21 and
the values were identical.

**What is asserted, and why each rule:**

1. **The child really has no SciPy** — else the whole gate is vacuous and would
   pass while measuring the exact path against itself.
2. **The warning fires EXACTLY ONCE** across 500+ calls. Once is the contract;
   never is the old defect, and per-call would flood a frequency sweep.
3. **The fallback tracks the exact kernel within 2 % for x >= 4.** This is
   the check that kills ``0.166 * x`` — it read 1.80x at x = 4 and 1.33x at
   x = 512, so a revert fails here by a wide margin.
4. **The join at x = 2 is still DISCONTINUOUS.** The step is a deliberate
   design decision, not an oversight: a smooth curve through approximate values
   looks right and is just as approximate, so the discontinuity is kept as the
   visible signal that this path is in use. Moving the crossover to where the
   branches now cross (~x = 2.7) would make it nearly continuous, and this
   check refuses that silently happening.
5. **The worst-case over-estimate is bounded at 2.5x.** Documents the blast
   radius; the old coefficient blew it at 5.92x.

Pass: exit 0 and 'LITZ NOSCIPY GATE PASSED'. Pure python3 (needs scipy for the
reference values; no FreeCAD, no solver binaries).
"""
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: x values probed on both branches. Spans the small-argument series, both
#: sides of the x = 2 join, and far enough out that an asymptote must be exact.
XS = [0.4, 1.0, 1.5, 1.999, 2.001, 2.5, 3.0, 4.0, 8.0, 16.0, 64.0, 512.0]

#: x >= this must agree with the exact kernel to within TOL_FAR.
FAR_X = 4.0
#: 2 %, and the margin is deliberately thin: the measured worst point in this
#: range is +1.541 % at x = 4 itself (it falls to -0.95 % by x = 5 and under
#: 0.1 % by x = 16). A looser bound would still catch `0.166 x`, which is 80 %
#: off at x = 4 — but it would stop catching a smaller coefficient slip.
TOL_FAR = 0.02

#: No x may over-estimate by more than this.
MAX_RATIO = 2.5

#: The join must remain visibly discontinuous.
MIN_STEP = 1.5

_CHILD = r"""
import json, sys

class _NoScipy:
    def find_module(self, name, path=None):
        return self.find_spec(name, path)
    def find_spec(self, name, path=None, target=None):
        if name == "scipy" or name.startswith("scipy."):
            raise ImportError("scipy blocked by litz_noscipy gate")
        return None

sys.meta_path.insert(0, _NoScipy())
sys.path.insert(0, %(root)r)

import importlib.util
try:
    importlib.util.find_spec("scipy")
    blocked = False
except ImportError:
    blocked = True

from emstudio.wire import litz

vals = [litz._proximity_h(x) for x in %(xs)r]
for i in range(500):                     # the warning must still be ONE line
    litz._proximity_h(2.5 + i * 0.01)

json.dump({"blocked": blocked, "values": vals,
           "warned": litz._PROX_WARNED}, sys.stdout)
"""


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " - " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    import json

    from emstudio.wire import litz

    # The reference values come from the EXACT branch, in this process, which
    # has SciPy. If it does not, the gate cannot compare anything and says so
    # rather than passing vacuously.
    try:
        import scipy  # noqa: F401
    except ImportError:
        print("  ....  SKIP: this interpreter has no SciPy, so there is no "
              "exact kernel to compare the fallback against")
        print("LITZ NOSCIPY GATE SKIPPED")
        return 0

    exact = [litz._proximity_h(x) for x in XS]
    check("exact branch ran in-process (warning flag untouched)",
          not litz._PROX_WARNED,
          "SciPy present, so the fallback must not have been reached")

    src = _CHILD % {"root": _ROOT, "xs": XS}
    proc = subprocess.run([sys.executable, "-c", src],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        check("child interpreter ran", False,
              "exit %d; stderr: %s" % (proc.returncode, proc.stderr[-400:]))
        print("LITZ NOSCIPY GATE FAILED (1)")
        return 1

    got = json.loads(proc.stdout)
    fallback = got["values"]

    # 1. the branch under test is genuinely the SciPy-less one
    check("child has NO scipy (gate is not vacuous)", got["blocked"],
          "scipy was importable in the child, so it ran the EXACT path")
    check("child took the fallback (warned flag set)", got["warned"])

    # 2. the warning fires exactly once, on stderr
    n_warn = proc.stderr.count("SciPy is not available")
    check("warning fires EXACTLY once in 512 calls", n_warn == 1,
          "saw %d occurrences" % n_warn)
    check("warning goes to stderr, not stdout",
          "SciPy is not available" not in proc.stdout)

    # 3. far field: an asymptote must actually be asymptotic
    for x, e, f in zip(XS, exact, fallback):
        if x < FAR_X:
            continue
        rel = abs(f - e) / e
        check("x=%g fallback within %.1f%% of exact" % (x, TOL_FAR * 100),
              rel <= TOL_FAR,
              "fallback %.6f vs exact %.6f (%.1f%% off)" % (f, e, rel * 100))

    # 4. the join stays visibly discontinuous (deliberate)
    lo = fallback[XS.index(1.999)]
    hi = fallback[XS.index(2.001)]
    check("join at x=2 is still discontinuous", hi / lo >= MIN_STEP,
          "h(2.001)/h(1.999) = %.2fx; the step is the visible signal that "
          "this path is in use and must not be smoothed away" % (hi / lo))

    # 5. bounded blast radius everywhere
    worst_x, worst = None, 0.0
    for x, e, f in zip(XS, exact, fallback):
        if e > 0 and f / e > worst:
            worst, worst_x = f / e, x
    check("worst over-estimate <= %.1fx" % MAX_RATIO, worst <= MAX_RATIO,
          "worst is %.2fx at x=%g" % (worst, worst_x))

    print("  ....  worst fallback error %.2fx at x=%g; far-field (x>=%g) "
          "max %.2f%%" % (worst, worst_x, FAR_X,
                          100 * max(abs(f - e) / e for x, e, f
                                    in zip(XS, exact, fallback) if x >= FAR_X)))

    if FAILURES:
        print("LITZ NOSCIPY GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("LITZ NOSCIPY GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
