# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — conjugate NATURAL CONVECTION, run for real.

SOLVER tier (~11 min on the reference box): the buoyant two-region gap —
gravity on, target Ra 1e6 nominal, H/L 4, the 40x60 mesh — through
`chtMultiRegionSimpleFoam`, with the gap Nusselt number recovered by
`cht.gap_nusselt` from the solved solid mean.

WHY THE WINDOW IS [5.5, 8.6] AND NOT A TIGHT PIN. Unlike the g = 0 anchor
(closed form, exact), a convective Nu has no exact answer here, so the
window is deliberately WIDER than every reference. Its job is to catch the
failure this gate exists for — a geometry/physics artifact that parks Nu
near the conduction limit — NOT to certify agreement with a correlation.

References at THIS case (A = H/L = 4, Pr = 0.7, interface Ra ~8.5e5):
  * Berkovsky-Polevikov, Nu = 0.22*(Pr*Ra/(0.2+Pr))^0.28 * A^(-1/4): 6.638
    (the aspect factor MATTERS — without it the same fit reads ~9.5);
  * ElSherbiny-Raithby-Hollands at its nearest VALID aspect (A = 5): 6.411;
  * the incompressible single-region reference on the donor mesh: 6.99.
  ⚠ MacGregor & Emery (~8.4) is NOT quoted as a reference here: it is
    published for 10 < H/L < 40 and 1 < Pr < 2e4, and this case is A = 4,
    Pr = 0.7 — out of range on BOTH, so evaluating it here is a double
    extrapolation, not an evaluation. The 8.6 upper edge is therefore
    deliberate slack, not a correlation value. ⚠ A solve reading ~8.5 would
    PASS this gate while sitting ~28 % above every in-range reference; that
    is accepted, because tightening the top edge around fits this case is
    outside their validity would trade a real guarantee for a false one.

WHAT THIS GATE'S OWN MESH READS, and why it is not "the" answer. The gate
runs 40x60 and measures ~6.85. The 3-grid refinement study
(docs/results/cht_refinement_fixedmesh.txt, 2026-08-19: 40x60 6.8529 ->
60x90 6.6957 -> 80x120 6.6387, all converged) puts the mesh-independent
value at **~6.5** (bracket 6.47-6.56 across defensible GCI conventions),
so **this gate's mesh reads roughly 5 % high**. That is fine for a
pass/fail window, but:
  ⚠ DO NOT quote 6.85 as "the" Nusselt number anywhere user-facing, and do
    not cite it as one of the references that bracket this window — the
    gate's own measurement cannot justify the gate's own bounds.
  ⚠ The scheme is FIRST-ORDER upwind in div(phi,U|h|e), so the formal order
    is 1; the study's observed p = 1.90 is about twice that, which is why
    its extrapolate is reported as a bracket rather than a single value.

⚠ Ra and Nu are INTERFACE-referenced (the fluid never sees the nominal
hot-to-cold drop; the solid takes its share). The conduction limit of this
same recovery is Nu = 1 exactly, gated FAST in `cht_setup`.

THE FAILURE THIS EXISTS TO CATCH: the swapped-face-sets mesh
(topBottom/frontAndBack exchanged, shipped until `69b65e5`) pinned Nu at
1.86-1.88 at ANY scale and ANY solver route — Hele-Shaw drag from walls one
cell apart, with gravity pointing out of the solved plane. `cht_setup`
catches that structurally (face planes recomputed from vertex coordinates);
this gate is the LIVE confirmation that the physics actually convects.
⚠ Note the honest form of the 08-17 rebuttal: refinement DOES move Nu
  slightly toward the conduction limit (-2.3 %, then -0.85 %) — the same
  SIGN as the broken mesh's -36 %. What distinguishes them is magnitude and
  that the increments shrink. Do not restate this as a direction argument.
"""
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: The correlation window (see the module docstring for each edge's source).
NU_LO, NU_HI = 5.5, 8.6

def check(label, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", label,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


def main():
    from emstudio.solvers.openfoam import cht
    from emstudio.solvers.openfoam.runner import run_cht

    print("EMStudio conjugate natural-convection gate (LIVE SOLVE, ~11 min)")
    case = cht.ChtCase(gravity=9.81, target_ra=1.0e6, n_y=60, n_fluid=40,
                       iterations=20000)
    if not case.buoyant:
        check("the case is buoyant", False, "gravity+cells contract broke")
        return 1
    print("  nominal Ra %.4g  H/L %.2f  conduction limit q %.4f W/m^2"
          % (case.rayleigh, case.aspect, case.flux))

    tmp = tempfile.mkdtemp(prefix="cht_conv_gate_")
    try:
        report, _means = run_cht(tmp, case, timeout=3600)
        if not report.get("ok"):
            check("the solve ran", False, "{0}: {1}".format(
                report.get("failed_at"), report.get("error")))
            for s in report.get("steps", []):
                if s.get("rc"):
                    print("    last of {0}:\n{1}".format(
                        s["step"], s.get("tail", "")[-600:]))
            return 1
        check("the solve ran", True)

        m = cht.gap_nusselt(case, report["t_solid_mean"])
        print("  q %.4f W/m^2  T_int %.4f K  gap dT %.4f K" %
              (m.q, m.t_interface, m.dt_gap))
        print("  MEASURED Nu %.4f at Ra %.4g (interface-referenced)" %
              (m.nu, m.ra))

        check("Nu {0:.4f} inside the correlation window [{1}, {2}]".format(
                  m.nu, NU_LO, NU_HI),
              NU_LO <= m.nu <= NU_HI,
              "in-range refs at A=4, Pr=0.7: Berkovsky-Polevikov 6.638, "
              "ElSherbiny-class (A=5) 6.411, incompressible reference "
              "6.99; mesh-independent value ~6.5 (this gate's 40x60 "
              "mesh reads ~5 % high, which is expected). The window is "
              "deliberately wider than every reference — its job is to "
              "keep the broken-mesh signature 1.86-1.88 dead, not to "
              "certify a correlation")
        # An INDEPENDENT second kill, not a restatement of the Nu window:
        # the conduction limit of this case sits at Ra_int 9.75e5 and a
        # nominal-drop referencing regression returns 1e6 — both FAIL this
        # bound, while any solve convecting inside the Nu window lands at
        # or below ~8.8e5 (more convection = more of the drop taken by the
        # solid = lower interface Ra).
        check("the interface-referenced Ra {0:.4g} stayed in regime".format(
                  m.ra),
              5.0e5 <= m.ra <= 9.0e5,
              "9.0e5 excludes BOTH the conduction limit (9.75e5) and a "
              "nominal-referenced Ra (1e6)")
        # Convection must pull the interface DOWN from the conduction answer
        # — that is what 'the fluid carries more heat' means at the wall.
        check("T_int {0:.2f} K sits below the conduction limit {1:.2f} K"
              .format(m.t_interface, case.t_interface),
              m.t_interface < case.t_interface - 2.0,
              "measured 2026-08-18: 348.74 (conduction) -> 342.45 (fixed "
              "mesh, convecting)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-CHT-CONVECTION GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("openfoam-cht-convection validation failed")
    sys.exit(0)
