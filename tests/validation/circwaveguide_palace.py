# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace DRIVEN wave ports on a GENERAL solid (BREP).

Pass: exit 0 and 'CIRCWG GATE PASSED'.

Driven S-parameter analyses are no longer limited to axis-aligned boxes: any
closed solid is exported to a BREP, its two end faces are slab-tagged as wave
ports, and the rest is PEC (the driven analogue of the eigenmode BREP path).

Gate A (pure python3), two checks:
  1. **WR-90 box as a BREP** must reproduce the validated box waveguide — the
     control that proves the general-BREP driven mechanism is correct:
     |S11| low (< -40 dB) and |S21| ~ 0 dB across X-band.
  2. **Circular waveguide** (a genuinely non-box solid): a cylinder of radius R
     has dominant mode TE11 with cutoff fc = 1.8412*c/(2*pi*R). Below fc the
     wave port is evanescent (|S21| strongly negative — fully reflected); above
     fc it propagates lossless (|S21| ~ 0 dB). The sharp transition at the
     analytic cutoff is the proof that arbitrary CURVED port faces work.
     Reference run 2026-07-07 (Palace Order 2, R=30/L=80 mm, 5 mm mesh):
     fc 2.928 GHz; 2.5 GHz |S21| -50.8 dB (evanescent); 3.0/3.5 GHz |S21|
     ~0 dB (propagating, -0.0005 dB).

Gate B (freecadcmd only): the Circular Waveguide template (Part::Cylinder ->
BREP driven path) runs the full FreeCAD path in its single-mode TE11 band.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
R_MM, L_MM = 30.0, 80.0
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def te11_cutoff_ghz(radius_mm):
    return 1.8411838 * C0 / (2 * math.pi * radius_mm * 1e-3) / 1e9


def _gmsh_brep(geo_body, workdir, name):
    """Generate a BREP with gmsh (FreeCAD-free). Returns the .brep path."""
    from emstudio.setup import solvers as solver_setup
    from emstudio.solvers.base import SolverJob

    info = solver_setup.find_backend("gmsh")
    if not info.found:
        raise RuntimeError("gmsh not found — needed to generate the test BREP")
    geo = os.path.join(workdir, name + ".geo")
    brep = os.path.join(workdir, name + ".brep")
    with open(geo, "w", encoding="utf-8") as fh:
        fh.write('SetFactory("OpenCASCADE");\n' + geo_body +
                 '\nSave "{0}";\n'.format(brep))
    try:
        SolverJob([info.path, geo, "-0"], cwd=workdir).run_blocking(timeout=120)
    except Exception:
        pass  # gmsh may exit non-zero after Save; the .brep is what matters
    if not os.path.isfile(brep):
        raise RuntimeError("gmsh did not produce a BREP at {0}".format(brep))
    return brep


def gate_a_pure():
    import tempfile

    import numpy as np

    from emstudio.solvers.palace import run_waveguide_brep

    workdir = tempfile.mkdtemp(prefix="emstudio_circwg_")

    # 1. WR-90 box as a BREP -> must reproduce TE10 (the control)
    box = _gmsh_brep("Box(1) = {0,0,0, 22.86,10.16,30};", workdir, "wr90")
    rb = run_waveguide_brep(box, axis=2, bbox_mm=(0, 0, 0, 22.86, 10.16, 30.0),
                            f1_ghz=8.0, f2_ghz=12.0, step_ghz=1.0, order=2)
    s11 = 20 * np.log10(np.maximum(np.abs(rb.s11), 1e-12))
    s21 = 20 * np.log10(np.maximum(np.abs(rb.s_others[(2, 1)]), 1e-12))
    check("WR-90 box-as-BREP reproduces TE10 (|S11| low)", s11.max() < -40.0,
          "max |S11| {0:.1f} dB".format(s11.max()))
    check("WR-90 box-as-BREP |S21| ~ 0 dB", np.abs(s21).max() < 0.05,
          "max dev {0:.3e} dB, {1:.0f}s".format(np.abs(s21).max(), rb.meta["duration_s"]))

    # 2. circular waveguide -> evanescent below TE11 cutoff, propagating above
    fc = te11_cutoff_ghz(R_MM)
    cyl = _gmsh_brep("Cylinder(1) = {{0,0,0, 0,0,{0:.9g}, {1:.9g}}};".format(L_MM, R_MM),
                     workdir, "cyl")
    rc = run_waveguide_brep(cyl, axis=2, bbox_mm=(-R_MM, -R_MM, 0, R_MM, R_MM, L_MM),
                            f1_ghz=2.5, f2_ghz=3.5, step_ghz=0.5, order=2, elem_mm=5.0)
    f = np.array(rc.freq) / 1e9
    s21c = 20 * np.log10(np.maximum(np.abs(rc.s_others[(2, 1)]), 1e-12))
    below = [s for fi, s in zip(f, s21c) if fi < fc]
    above = [s for fi, s in zip(f, s21c) if fi > fc]
    check("circular WG evanescent below TE11 cutoff ({0:.3f} GHz)".format(fc),
          below and max(below) < -20.0,
          "max |S21| below = {0:.1f} dB".format(max(below) if below else float("nan")))
    check("circular WG propagates above cutoff (|S21| ~ 0 dB)",
          above and min(above) > -0.1,
          "min |S21| above = {0:.4f} dB, {1:.0f}s".format(
              min(above) if above else float("nan"), rc.meta["duration_s"]))
    print("  (workdir: {0})".format(rc.meta["workdir"]))


def gate_b_template():
    import numpy as np

    import FreeCAD

    from emstudio.solvers import palace
    from emstudio.templates import circwaveguide

    doc = FreeCAD.newDocument("CircWgGate")
    try:
        ana = circwaveguide.makeCircWaveguide(doc, radius_mm=R_MM, length_mm=L_MM,
                                              f1_ghz=3.0, f2_ghz=3.8, points=5)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverPalace"][0]
        result = palace.run(ana, solver)
        s21 = 20 * np.log10(np.maximum(np.abs(result.s_others[(2, 1)]), 1e-12))
        s11 = 20 * np.log10(np.maximum(np.abs(result.s11), 1e-12))
        check("template circular WG propagates in the TE11 band (FreeCAD BREP path)",
              np.abs(s21).max() < 0.1 and s11.max() < -25.0,
              "|S21| dev {0:.3e} dB, max |S11| {1:.1f} dB".format(
                  np.abs(s21).max(), s11.max()))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio general-BREP driven wave-port validation gate (Palace)")
    print("circular-WG TE11 cutoff = {0:.4f} GHz (R={1:.0f} mm)".format(
        te11_cutoff_ghz(R_MM), R_MM))
    print("Gate A: WR-90-as-BREP vs TE10 + circular waveguide vs TE11 cutoff")
    gate_a_pure()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD Circular Waveguide template end-to-end")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("CIRCWG GATE FAILED: {0}".format(FAILURES))
        return 1
    print("CIRCWG GATE PASSED")
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
        raise SystemExit("circwaveguide validation failed")
    sys.exit(0)
