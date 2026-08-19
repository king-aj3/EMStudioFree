# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — conjugate NATURAL CONVECTION, run for real.

SOLVER tier (~11 min on the reference box): the buoyant two-region gap —
gravity on, target Ra 1e6 nominal, H/L 4, the 40x60 mesh — through
`chtMultiRegionSimpleFoam`, with the gap Nusselt number recovered by
`cht.gap_nusselt` from the solved solid mean.

WHY THE WINDOW IS [5.5, 8.6] AND NOT A TIGHT PIN. Unlike the g = 0 anchor
(closed form, exact), a convective Nu has no exact answer at this Ra; the
honest references bracket it — each evaluated AT THIS CASE (A = H/L = 4,
Pr = 0.7, interface-referenced Ra ~8.5e5):

  * Berkovsky-Polevikov, Nu = 0.22*(Pr*Ra/(0.2+Pr))^0.28 * A^(-1/4):
    6.6-6.9 across Ra 8.5e5-1e6 (the aspect factor MATTERS — without it
    the same fit reads ~9.5);
  * MacGregor & Emery, Nu = 0.42*Ra^(1/4)*Pr^0.012*A^(-0.3): 8.4 at the
    interface Ra, 8.7 at the nominal 1e6 — the HIGH reference, and the
    fit earlier session notes misattributed to "Berkovsky 8.549";
  * ElSherbiny-class vertical-slot fits (A = 5 nearest tabulated): ~6;
  * the incompressible single-region reference on the donor mesh: 6.99;
  * this exact coupled case, measured 2026-08-18 on the FIXED mesh: 6.8529.

The window contains every one of those and EXCLUDES the one number this
gate exists to keep dead: the swapped-face-sets mesh (topBottom/frontAndBack
exchanged, shipped until `69b65e5`) pinned Nu at 1.86-1.88 at ANY scale and
ANY solver route — Hele-Shaw drag from walls one cell apart, with gravity
pointing out of the solved plane. `cht_setup` catches that bug structurally
(face planes recomputed from vertex coordinates); this gate is the LIVE
confirmation that the physics actually convects.

⚠ Ra and Nu are INTERFACE-referenced (the fluid never sees the nominal
hot-to-cold drop; the solid takes its share). The conduction limit of this
same recovery is Nu = 1 exactly, gated FAST in `cht_setup`.

MESH SENSITIVITY, MEASURED 2026-08-19 on the fixed mesh (refinement study,
`docs/results/cht_refinement_fixedmesh.txt`): 40x60 -> 60x90 moves Nu
6.8529 -> 6.6957, **-2.3 %**, both fully converged (drift ~0, residuals
~1e-8). So this gate's window must stay wide enough to tolerate a couple of
percent of mesh sensitivity — do not tighten it around the 40x60 value.
⚠ Contrast the BROKEN-mesh era, where refinement collapsed Nu 1.8768 ->
1.2001 toward the conduction limit; that signature is what a geometry
artifact looks like, and it is now dead.
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
              "at A=4, interface Ra: Berkovsky-Polevikov 6.6-6.9, "
              "MacGregor-Emery ~8.4, ElSherbiny-class ~6; measured refs "
              "6.85 (this case, fixed mesh) / 6.99 (incompressible "
              "reference); the broken-mesh signature 1.86-1.88 must stay "
              "dead")
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
