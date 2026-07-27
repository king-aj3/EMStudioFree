# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Yagi-Uda over NEC2 (Element Designer slice E3).

Builds the TN-688 Yagi designs on the SHIPPED writer (via templates.makeYagi)
and checks the live gain/F-B/impedance against TN-688's MEASURED gains. Windows
set from the de-risk reference runs (docs/upstream/tn688-yagi-anchors.md — the
0.8λ primary anchor read 9.08 dBd / 11.23 dBi, F/B 12.9 dB at 400 MHz; the four
boom classes reproduced the measured 7.1/9.2/10.2/12.25 dBd to ±0.25 dB).

The far-field is pinned at the DESIGN frequency (400 MHz) — the runner's default
uses the min-S11 frequency, which wanders when the driven element is not matched.
Needs freecadcmd + nec2c; ~10-60 s. Pass: exit 0 and 'YAGI-NEC2 GATE PASSED'.
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


def _solve_yagi(doc, boom_lambda):
    """Build a TN-688 Yagi at d/λ=0.0085, 400 MHz; return (peak_dbi, fb_db, zin)."""
    import numpy as np

    from emstudio.objects import query
    from emstudio.solvers import nec2
    from emstudio.solvers.base import SolverJob, make_workdir
    from emstudio.solvers.nec2 import parser as nec_parser
    from emstudio.solvers.nec2 import writer as nec_writer
    from emstudio.setup import solvers as solver_setup
    from emstudio.templates import yagi as yagi_tpl

    f0 = 400e6
    lam_mm = 299792458.0 / f0 * 1000.0
    radius_mm = 0.0085 / 2.0 * lam_mm  # d/λ = 0.0085 (the Table 1 basis)
    ana = yagi_tpl.makeYagi(doc, f0_hz=f0, boom_lambda=boom_lambda,
                            wire_radius_mm=radius_mm)
    solver = query.get_solvers(ana)[0]
    result = nec2.run(ana, solver)
    freq = np.asarray(result.freq)
    z = np.asarray(result.zin)[int(np.argmin(np.abs(freq - f0)))]

    info = solver_setup.find_backend("nec2")
    wd = make_workdir("emstudio_yagi_ff_")
    ffd, ffo = os.path.join(wd, "ff.nec"), os.path.join(wd, "ff.out")
    nec_writer.write_nec_farfield(ana, solver, ffd, f0)
    SolverJob([info.path, "-i", ffd, "-o", ffo], cwd=wd).run_blocking(timeout=300)
    ff = nec_parser.parse_radiation_patterns(ffo, f0)
    g_peak, _th, _ph = ff.peak()
    th, g0 = ff.cut(0.0)
    _, g180 = ff.cut(180.0)
    j90 = int(np.argmin(np.abs(th - 90.0)))
    return g_peak, g0[j90] - g180[j90], z


def main():
    print("EMStudio Yagi-Uda NEC2 validation gate (E3)")
    try:
        import FreeCAD  # noqa: F401
        import Part  # noqa: F401
    except Exception:
        print("  skip — needs freecadcmd (FreeCAD geometry)")
        return 0
    import shutil

    if not shutil.which("nec2c"):
        print("  skip — nec2c not installed")
        return 0
    import FreeCAD

    # --- primary anchor: the 0.8λ design at 400 MHz ------------------------
    doc = FreeCAD.newDocument("yagi_gate")
    try:
        g_dbi, fb, z = _solve_yagi(doc, 0.8)
        g_dbd = g_dbi - 2.15
        check("0.8λ Yagi peak gain 8.3-9.9 dBd (TN-688 measured 9.2; de-risk "
              "ref 9.08)", 8.3 <= g_dbd <= 9.9,
              "{0:.2f} dBi = {1:.2f} dBd".format(g_dbi, g_dbd))
        check("0.8λ Yagi F/B > 10 dB at the design frequency",
              fb > 10.0, "{0:.1f} dB".format(fb))
        check("0.8λ Yagi driven-element Re(Zin) sane (5-80 ohm)",
              5.0 <= z.real <= 80.0,
              "{0:.1f}{1}j{2:.1f}".format(
                  z.real, "+" if z.imag >= 0 else "-", abs(z.imag)))
    finally:
        FreeCAD.closeDocument(doc.Name)

    # --- regression: four boom classes vs measured -------------------------
    # The de-risk demonstrated ±0.25 dB agreement, BYTE-IDENTICAL across
    # FreeCAD 0.21.2 and 1.1.1; gate at ±0.5 dB (2x the demonstrated worst
    # case for mesh/segmentation headroom) so a real 0.5+ dB regression fails.
    measured = {0.4: 7.1, 0.8: 9.2, 1.2: 10.2, 2.2: 12.25}
    for boom, meas in measured.items():
        doc = FreeCAD.newDocument("yagi_gate_{0}".format(boom))
        try:
            g_dbi, fb, _z = _solve_yagi(doc, boom)
            g_dbd = g_dbi - 2.15
            check("{0}λ Yagi within 0.5 dB of the measured {1:g} dBd "
                  "(F/B {2:.1f} dB)".format(boom, meas, fb),
                  abs(g_dbd - meas) <= 0.5,
                  "{0:.2f} dBd (delta {1:+.2f})".format(g_dbd, g_dbd - meas))
        finally:
            FreeCAD.closeDocument(doc.Name)

    if FAILURES:
        print("YAGI-NEC2 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("YAGI-NEC2 GATE PASSED")
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
        raise SystemExit("yagi-nec2 validation failed")
    sys.exit(0)
