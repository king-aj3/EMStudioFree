# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: LPDA over NEC2 (Element Designer slice E5).

Builds the classic 54-216 MHz Carrel design (tau 0.865 / sigma 0.158) on the
SHIPPED writer (templates.makeLPDA -> crossed-TL feeder cards) and checks the
live band impedance + spot-frequency far fields. Windows set from the de-risk
reference runs (docs/upstream/lpda-carrel-anchors.md): 41-point sweep median
VSWR(65) 1.215 with 38/41 points under 2.0 (three narrow documented 'weak
spot' spikes between low-end element resonances, worst 6.0); fwd gain
8.29/8.84/8.54 dBi at 60/120/200 MHz with F/B 20.2/20.8/20.0 dB; the
UNCROSSED control collapses to F/B 5.7 dB — the negative-Z0 crossed-line
convention is load-bearing and regression-guarded here.

Needs freecadcmd + nec2c; ~1-2 min. Pass: exit 0 and 'LPDA-NEC2 GATE PASSED'.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

R0 = 65.0


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _farfield(ana, solver, f_hz):
    import numpy as np

    from emstudio.setup import solvers as solver_setup
    from emstudio.solvers.base import SolverJob, make_workdir
    from emstudio.solvers.nec2 import parser as nec_parser
    from emstudio.solvers.nec2 import writer as nec_writer

    info = solver_setup.find_backend("nec2")
    wd = make_workdir("emstudio_lpda_ff_")
    ffd, ffo = os.path.join(wd, "ff.nec"), os.path.join(wd, "ff.out")
    nec_writer.write_nec_farfield(ana, solver, ffd, f_hz)
    SolverJob([info.path, "-i", ffd, "-o", ffo], cwd=wd).run_blocking(timeout=300)
    ff = nec_parser.parse_radiation_patterns(ffo, f_hz)
    th, g0 = ff.cut(0.0)
    _, g180 = ff.cut(180.0)
    j90 = int(np.argmin(np.abs(th - 90.0)))
    return g0[j90], g0[j90] - g180[j90]


def main():
    print("EMStudio LPDA NEC2 validation gate (E5)")
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
    import numpy as np

    from emstudio.objects import query
    from emstudio.solvers import nec2
    from emstudio.templates import lpda as lpda_tpl

    doc = FreeCAD.newDocument("lpda_gate")
    try:
        ana = lpda_tpl.makeLPDA(doc, f_lo_hz=54e6, f_hi_hz=216e6,
                                tau=0.865, sigma=0.158, wire_radius_mm=5.0)
        check("template: 15 elements + 14 crossed TLs",
              len(query.get_transmission_lines(ana)) == 14
              and all(t.Crossed for t in query.get_transmission_lines(ana)))
        ana.FrequencyPoints = 41
        doc.recompute()
        solver = query.get_solvers(ana)[0]

        # --- band impedance (production writer + runner + parser) ----------
        result = nec2.run(ana, solver)
        z = np.asarray(result.zin)
        gam = np.minimum(np.abs((z - R0) / (z + R0)), 0.999)
        vswr = (1.0 + gam) / (1.0 - gam)
        med = float(np.median(vswr))
        frac_ok = float(np.mean(vswr < 2.0))
        check("band median VSWR(65) < 1.5 (ref 1.215 — Carrel: ~1.1 at "
              "sigma_opt)", med < 1.5, "{0:.3f}".format(med))
        check(">= 80% of sweep points under VSWR 2.0 (ref 92.7%; narrow "
              "low-end weak-spot spikes are documented)", frac_ok >= 0.80,
              "{0:.1%}".format(frac_ok))
        check("worst VSWR < 10 (ref 6.0 at the 66 MHz weak spot)",
              float(np.max(vswr)) < 10.0, "{0:.2f}".format(float(np.max(vswr))))
        mean_r = float(np.mean(z.real))
        check("band mean R within 65 +- 10 ohm (ref 60.7 — the Za "
              "convention anchor)", 55.0 <= mean_r <= 75.0,
              "{0:.2f} ohm".format(mean_r))

        # --- spot far fields (pattern pinned at explicit frequencies) ------
        # windows: de-risk ref +-0.7 dB (the yagi-gate headroom precedent)
        for f_mhz, ref_fwd in ((60.0, 8.29), (120.0, 8.84), (200.0, 8.54)):
            fwd, fb = _farfield(ana, solver, f_mhz * 1e6)
            check("{0:g} MHz fwd gain {1:.2f}+-0.7 dBi".format(f_mhz, ref_fwd),
                  abs(fwd - ref_fwd) <= 0.7, "{0:.2f} dBi".format(fwd))
            check("{0:g} MHz F/B > 15 dB (ref ~20)".format(f_mhz),
                  fb > 15.0, "{0:.1f} dB".format(fb))

        # --- the crossed-feeder control (sign-convention regression) -------
        for tl in query.get_transmission_lines(ana):
            tl.Crossed = False
        doc.recompute()
        fwd_u, fb_u = _farfield(ana, solver, 120e6)
        check("UNCROSSED control: F/B collapses below 10 dB (ref 5.7 — the "
              "negative-Z0 crossed convention is load-bearing)",
              fb_u < 10.0, "{0:.1f} dB".format(fb_u))
    finally:
        FreeCAD.closeDocument(doc.Name)

    if FAILURES:
        print("LPDA-NEC2 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("LPDA-NEC2 GATE PASSED")
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
        raise SystemExit("lpda-nec2 validation failed")
    sys.exit(0)
