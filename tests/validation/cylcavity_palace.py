# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace CYLINDRICAL-cavity eigenmodes vs Bessel theory.

Pass: exit 0 and 'CYLCAVITY GATE PASSED'.

This exercises the general-3-D-geometry (BREP) path: a solid that is NOT a box
(a circular cylinder) is meshed by exporting it to a BREP and tagging its whole
boundary as PEC. An air-filled cylindrical PEC cavity of radius R, height H has
exact modes
    TM_mnp: f = (c0/2pi) sqrt((x_mn/R)^2 + (p*pi/H)^2),  x_mn = n-th zero of J_m,  p>=0
    TE_mnp: f = (c0/2pi) sqrt((xp_mn/R)^2 + (p*pi/H)^2), xp_mn = n-th zero of J_m', p>=1
The fundamental is TM010 = c0*2.404826/(2*pi*R), independent of H.

Gate A (pure python3): generate a cylinder BREP with gmsh, solve via
run_cavity_brep, match every computed mode to its NEAREST analytic mode
(degenerate TE/TM pairs make index-pairing wrong).
    Reference run 2026-07-07 (Palace Order 2, R=30/H=40 mm, elem 6 mm, ~61 s):
    TM010 3.8344 GHz (+0.25% vs analytic 3.8248), first 6 modes <0.5% nearest.

Gate B (freecadcmd only): the Cylindrical Cavity template runs the full FreeCAD
path (Part::Cylinder -> exportBrep -> gmsh Merge -> Palace).
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

C0 = 299792458.0
R_MM, H_MM = 30.0, 40.0
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def analytic_modes(radius_mm, height_mm, nmax=4, pmax=3):
    """Sorted list of (freq_ghz, name) for a circular cylindrical PEC cavity."""
    from scipy.special import jn_zeros, jnp_zeros

    R, H = radius_mm * 1e-3, height_mm * 1e-3
    out = []
    for m in range(nmax):
        for n, x in enumerate(jn_zeros(m, nmax), 1):       # TM: J_m zeros, p>=0
            for p in range(0, pmax):
                f = C0 / (2 * math.pi) * math.sqrt((x / R) ** 2 + (p * math.pi / H) ** 2)
                out.append((f / 1e9, "TM{0}{1}{2}".format(m, n, p)))
        for n, x in enumerate(jnp_zeros(m, nmax), 1):      # TE: J_m' zeros, p>=1
            for p in range(1, pmax):
                f = C0 / (2 * math.pi) * math.sqrt((x / R) ** 2 + (p * math.pi / H) ** 2)
                out.append((f / 1e9, "TE{0}{1}{2}".format(m, n, p)))
    out.sort()
    return out


def _target_seed_ghz():
    """Shift-invert seed from the bbox (the box heuristic model.py uses)."""
    dims = sorted([R_MM * 2, R_MM * 2, H_MM])  # cylinder bounding box, mm
    a, d = dims[-1] * 1e-3, dims[-2] * 1e-3
    f = (C0 / 2.0) * math.sqrt((1.0 / a) ** 2 + (1.0 / d) ** 2)
    return f / 1e9 * 0.9


def _cylinder_brep(radius_mm, height_mm, workdir):
    """Generate a cylinder BREP with gmsh (FreeCAD-free). Returns the .brep path."""
    from emstudio.setup import solvers as solver_setup
    from emstudio.solvers.base import SolverJob

    info = solver_setup.find_backend("gmsh")
    if not info.found:
        raise RuntimeError("gmsh not found — needed to generate the test BREP")
    geo = os.path.join(workdir, "gen_cyl.geo")
    brep = os.path.join(workdir, "gen_cyl.brep")
    with open(geo, "w", encoding="utf-8") as fh:
        fh.write('SetFactory("OpenCASCADE");\n')
        fh.write("Cylinder(1) = {{0,0,0, 0,0,{0:.9g}, {1:.9g}}};\n".format(
            height_mm, radius_mm))
        fh.write('Save "{0}";\n'.format(brep))
    try:
        SolverJob([info.path, geo, "-0"], cwd=workdir).run_blocking(timeout=120)
    except Exception:
        pass  # gmsh may exit non-zero after Save; the .brep is what matters
    if not os.path.isfile(brep):
        raise RuntimeError("gmsh did not produce a BREP at {0}".format(brep))
    return brep


def gate_a_pure():
    import tempfile

    from emstudio.solvers.palace import run_cavity_brep

    workdir = tempfile.mkdtemp(prefix="emstudio_cylgate_")
    brep = _cylinder_brep(R_MM, H_MM, workdir)
    res = run_cavity_brep(brep, target_ghz=_target_seed_ghz(), n_modes=6, order=2,
                          elem_mm=6.0)
    ana = analytic_modes(R_MM, H_MM)
    ana_f = [f for f, _ in ana]

    check("Palace returned modes", len(res.modes) >= 5, "{0} modes".format(len(res.modes)))
    dom = res.dominant_ghz()
    tm010 = C0 * 2.404825558 / (2 * math.pi * R_MM * 1e-3) / 1e9
    check("fundamental vs analytic TM010 (<1%)", abs(dom / tm010 - 1) < 0.01,
          "{0:.5f} GHz vs {1:.5f} GHz ({2:+.3%})".format(dom, tm010, dom / tm010 - 1))
    worst = 0.0
    for m in res.modes[:6]:
        f = m["freq_ghz"]
        nearest = min(ana_f, key=lambda a: abs(a - f))
        worst = max(worst, abs(f / nearest - 1))
    check("first modes match nearest analytic (<1.5%)", worst < 0.015,
          "worst {0:.3%}".format(worst))
    print("  (workdir: {0}, {1:.0f} s)".format(res.meta["workdir"], res.meta["duration_s"]))


def gate_b_template():
    import FreeCAD

    from emstudio.solvers import palace
    from emstudio.templates import cylcavity

    doc = FreeCAD.newDocument("CylCavityGate")
    try:
        ana = cylcavity.makeCylCavity(doc, radius_mm=R_MM, height_mm=H_MM, num_modes=6)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverPalace"][0]
        result = palace.run(ana, solver)
        dom = result.dominant_ghz()
        tm010 = C0 * 2.404825558 / (2 * math.pi * R_MM * 1e-3) / 1e9
        check("template fundamental vs analytic TM010 (FreeCAD BREP path)",
              abs(dom / tm010 - 1) < 0.01,
              "{0:.5f} GHz vs {1:.5f} GHz ({2:+.3%})".format(dom, tm010, dom / tm010 - 1))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio cylindrical-cavity eigenmode validation gate (Palace, BREP geometry)")
    tm010 = C0 * 2.404825558 / (2 * math.pi * R_MM * 1e-3) / 1e9
    print("analytic TM010 = {0:.4f} GHz (R={1:.0f} mm)".format(tm010, R_MM))
    print("Gate A: cylinder BREP -> Palace eigenmodes vs Bessel theory")
    gate_a_pure()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD cylindrical-cavity template end-to-end")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("CYLCAVITY GATE FAILED: {0}".format(FAILURES))
        return 1
    print("CYLCAVITY GATE PASSED")
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
        raise SystemExit("cylcavity validation failed")
    sys.exit(0)
