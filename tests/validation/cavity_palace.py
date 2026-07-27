# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace cavity eigenmodes vs the exact closed-form modes.

Pass: exit 0 and 'CAVITY GATE PASSED'.

An air-filled rectangular cavity a x b x d with PEC walls has exact
resonant frequencies f_mnp = (c0/2)*sqrt((m/a)^2 + (n/b)^2 + (p/d)^2)
(at least two non-zero indices). Palace's FEM eigenmodes must match the
lowest of these.

Gate A (pure python3): solve the 40x20x60 mm cavity and match every
computed mode to its NEAREST analytic mode — degenerate pairs (Palace
returns two eigenvalues per geometric degeneracy) make index-pairing
wrong, so nearest-pairing is the correct comparison.
    Reference run 2026-07-06 (Palace, Order 2): all modes <0.02%.

Gate B (freecadcmd only): the cavity template runs the full FreeCAD path
(box geometry -> gmsh 3-D -> Palace) and its fundamental matches TE101.
"""
import itertools
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def analytic_modes(a_m, b_m, d_m, nmax=4, eps_r=1.0):
    """Sorted list of (freq_ghz, (m,n,p)) for a rectangular cavity."""
    out = []
    scale = 1.0 / math.sqrt(eps_r)
    for m, n, p in itertools.product(range(nmax + 1), repeat=3):
        if sum(1 for i in (m, n, p) if i > 0) < 2:
            continue
        f = (C0 / 2.0) * scale * math.sqrt((m / a_m) ** 2 + (n / b_m) ** 2 + (p / d_m) ** 2)
        out.append((f / 1e9, (m, n, p)))
    out.sort()
    return out


def gate_a_pure():
    from emstudio.solvers.palace import run_cavity

    size = (40.0, 20.0, 60.0)
    res = run_cavity(size, n_modes=8, order=2)
    ana = analytic_modes(0.040, 0.020, 0.060)
    ana_f = [f for f, _ in ana]

    check("Palace returned modes", len(res.modes) >= 6,
          "{0} modes".format(len(res.modes)))
    # dominant mode vs TE101
    dom = res.dominant_ghz()
    te101 = ana_f[0]
    check("fundamental mode vs analytic TE101", abs(dom / te101 - 1) < 0.01,
          "{0:.5f} GHz vs {1:.5f} GHz ({2:+.3%})".format(dom, te101, dom / te101 - 1))
    # every computed mode matches its NEAREST analytic mode
    worst = 0.0
    for m in res.modes:
        f = m["freq_ghz"]
        nearest = min(ana_f, key=lambda a: abs(a - f))
        rel = f / nearest - 1
        worst = max(worst, abs(rel))
    check("all modes match nearest analytic (<1%)", worst < 0.01,
          "worst {0:.3%} over {1} modes".format(worst, len(res.modes)))
    print("  (workdir: {0}, {1:.0f} s)".format(res.meta["workdir"], res.meta["duration_s"]))


def gate_b_template():
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import palace
    from emstudio.templates import cavity

    doc = FreeCAD.newDocument("CavityGate")
    try:
        ana = cavity.makeCavity(doc, size_mm=(40.0, 20.0, 60.0), num_modes=4)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverPalace"][0]
        result = palace.run(ana, solver)
        dom = result.dominant_ghz()
        te101 = analytic_modes(0.040, 0.020, 0.060)[0][0]
        check("template fundamental vs analytic TE101 (FreeCAD path)",
              abs(dom / te101 - 1) < 0.01,
              "{0:.5f} GHz vs {1:.5f} GHz ({2:+.3%})".format(dom, te101, dom / te101 - 1))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio cavity-eigenmode validation gate (Palace)")
    print("Gate A: 40x20x60 mm cavity modes vs closed-form")
    gate_a_pure()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD cavity template end-to-end")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("CAVITY GATE FAILED: {0}".format(FAILURES))
        return 1
    print("CAVITY GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    # freecadcmd exits 0 on uncaught exceptions (verified 2026-07-05) — convert
    # EVERY failure into SystemExit, which does propagate a non-zero exit code.
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("cavity validation failed")
    sys.exit(0)
