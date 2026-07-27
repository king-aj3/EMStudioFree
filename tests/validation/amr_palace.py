# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace ADAPTIVE MESH REFINEMENT (AMR) beats the coarse solve.

Pass: exit 0 and 'AMR GATE PASSED'.

AMR estimates a per-element error indicator, refines the elements carrying the
largest share of the error, and re-solves — more accuracy per degree of freedom.
This gate proves AMR actually helps: from the SAME coarse mesh, turning AMR on
must (a) move the computed fundamental CLOSER to the exact answer and (b) grow
the element count (so refinement genuinely happened, not just a re-solve).

The demo is a rectangular PEC cavity at **Order 1**. That choice is deliberate:
a box has EXACT geometry (flat faces), so the coarse error is pure field
discretization — exactly what AMR reduces, with no curved-wall faceting confound
that non-conformal refinement cannot fix. Order 1 leaves a large coarse error
for AMR to bite into, giving a robust margin. The exact fundamental is the
closed-form TE101 of the a x b x d cavity.

    Reference run 2026-07-07 (Palace Order 1, 40x20x60 mm, MaxIts=2, ~58 s):
    coarse  4.48927 GHz  (0.33% vs TE101 4.5039 GHz),  2039 elements  ->
    AMR     4.50047 GHz  (0.076%, 4.3x better),       30151 elements.
    (Cross-check, cylindrical curved-wall BREP at Order 1: coarse 0.36% ->
    AMR 0.10%, 3931 -> 37690 unknowns — AMR helps on curved geometry too.)

Gate A (pure python3): run_cavity coarse (mesh_refinement=0) vs AMR
(mesh_refinement=2); assert AMR error < coarse error, the element count grew
(scraped from Palace's "initial = X ... final = Y" refinement log), the AMR
result still identifies TE101, and the coarse control did zero refinement.

Gate B (freecadcmd only): the cavity template with MeshRefinement set runs the
full FreeCAD path (GUI object -> writer -> Palace) and still lands on TE101 with
a grown mesh — the AMR opt-in threads all the way through.
"""
import math
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
SIZE_MM = (40.0, 20.0, 60.0)
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def analytic_te101(size_mm):
    """Closed-form fundamental (GHz): the two LARGEST cavity dimensions, m=p=1."""
    dims = sorted(s * 1e-3 for s in size_mm)  # ascending
    x, y = dims[-1], dims[-2]                 # two largest -> lowest mode
    return (C0 / 2.0) * math.sqrt((1.0 / x) ** 2 + (1.0 / y) ** 2) / 1e9


def _amr_iters(log_lines):
    """Iterations Palace reported completing (0 when AMR is off)."""
    for line in log_lines:
        m = re.search(r"Completed\s+(\d+)\s+iterations of adaptive mesh refinement",
                      line)
        if m:
            return int(m.group(1))
    return None


def _amr_element_growth(log_lines):
    """(initial, final) element counts from Palace's non-conforming AMR log.

    Palace prints, per refinement pass:
    ``Nonconforming mesh refinement added N elements (initial = X, final = Y)``.
    The first ``initial`` is the coarse mesh; the last ``final`` is the fully
    adapted mesh.
    """
    init = final = None
    for line in log_lines:
        m = re.search(r"initial\s*=\s*(\d+),\s*final\s*=\s*(\d+)", line)
        if m:
            if init is None:
                init = int(m.group(1))
            final = int(m.group(2))
    return init, final


def gate_a_pure():
    from emstudio.solvers.palace import run_cavity

    te101 = analytic_te101(SIZE_MM)

    coarse_log = []
    coarse = run_cavity(SIZE_MM, n_modes=4, order=1, mesh_refinement=0,
                        line_callback=coarse_log.append)
    amr_log = []
    amr = run_cavity(SIZE_MM, n_modes=4, order=1, mesh_refinement=2,
                     refinement_tol=0.01, line_callback=amr_log.append)

    ce = abs(coarse.dominant_ghz() / te101 - 1)
    ae = abs(amr.dominant_ghz() / te101 - 1)

    # the coarse run is a genuine control: AMR off -> zero refinement iterations
    check("coarse control ran with AMR OFF (0 iterations)",
          _amr_iters(coarse_log) == 0,
          "reported {0} iterations".format(_amr_iters(coarse_log)))
    check("AMR ran the requested iterations",
          (_amr_iters(amr_log) or 0) >= 1,
          "{0} iterations".format(_amr_iters(amr_log)))

    init, final = _amr_element_growth(amr_log)
    check("AMR refined the mesh (element count grew)",
          init is not None and final is not None and final > init,
          "{0} -> {1} elements".format(init, final))

    check("AMR is strictly more accurate than the coarse solve",
          ae < ce,
          "coarse {0:.3%} -> AMR {1:.3%} ({2:.1f}x closer)".format(
              ce, ae, (ce / ae) if ae > 0 else float("inf")))
    check("AMR fundamental still identifies TE101 (<1%)", ae < 0.01,
          "{0:.5f} GHz vs {1:.5f} GHz ({2:+.3%})".format(
              amr.dominant_ghz(), te101, amr.dominant_ghz() / te101 - 1))
    print("  (coarse {0:.0f} s, AMR {1:.0f} s; workdir {2})".format(
        coarse.meta["duration_s"], amr.meta["duration_s"], amr.meta["workdir"]))


def gate_b_template():
    import FreeCAD

    from emstudio.solvers import palace
    from emstudio.templates import cavity

    doc = FreeCAD.newDocument("AmrGate")
    try:
        ana = cavity.makeCavity(doc, size_mm=SIZE_MM, num_modes=4)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverPalace"][0]
        solver.Order = 1
        solver.MeshRefinement = 1  # one pass is enough to prove the wiring (faster)
        log = []
        result = palace.run(ana, solver, line_callback=log.append)
        dom = result.dominant_ghz()
        te101 = analytic_te101(SIZE_MM)
        check("template AMR fundamental vs TE101 (FreeCAD path)",
              abs(dom / te101 - 1) < 0.01,
              "{0:.5f} GHz vs {1:.5f} GHz ({2:+.3%})".format(
                  dom, te101, dom / te101 - 1))
        init, final = _amr_element_growth(log)
        check("template AMR grew the mesh (opt-in threaded through)",
              init is not None and final is not None and final > init,
              "{0} -> {1} elements".format(init, final))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio adaptive-mesh-refinement validation gate (Palace)")
    print("analytic TE101 = {0:.4f} GHz (40x20x60 mm cavity)".format(
        analytic_te101(SIZE_MM)))
    print("Gate A: Order-1 cavity, coarse vs coarse+AMR (accuracy + element growth)")
    gate_a_pure()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD cavity template with AMR enabled end-to-end")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("AMR GATE FAILED: {0}".format(FAILURES))
        return 1
    print("AMR GATE PASSED")
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
        raise SystemExit("amr validation failed")
    sys.exit(0)
