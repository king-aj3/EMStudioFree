# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Elmer WPT coil coupling vs analytic coil formulas.

Pass: exit 0 and 'WPT GATE PASSED'.

Reference case: two identical coaxial 10-turn coils, mean radius 50 mm,
2 x 2 mm square cross-section, uniform current density (stranded model).

Analytics (verified numerically 2026-07-05, scripts in the decision log):
* Self-inductance — Maxwell/Grover GMD formula for a circular coil of
  rectangular cross-section: L = N^2*mu0*R*(ln(8R/g) - 2) with
  g = 0.44705*s the exact self-GMD of a square (this form already
  contains the internal energy; it matches the exact uniform-J
  cross-section integral to 0.01%): L_ref = 25.782448 uH.
* Mutual — Maxwell's coaxial-filament formula with complete elliptic
  integrals, x N1*N2 (filament-at-centroid error < 0.02% here).
* k = M/sqrt(L1*L2).

    Reference FEM run 2026-07-05 (Elmer v26.2): L -0.4%, M -0.2%, k +0.2%.

Gate B (only under freecadcmd): the WPT template runs the same geometry
through the FreeCAD path (ring solids -> classification -> pipeline) and
must reproduce k at gap 20 mm.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MU0 = 4e-7 * math.pi

#: geometry of the reference case (mm / turns)
R_MEAN, CROSS, TURNS = 50.0, 2.0, 10

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


# --- analytic references ------------------------------------------------------

def l_self_gmd():
    """Grover GMD self-inductance of the square-section coil [H]."""
    g = 0.4470491 * (CROSS * 1e-3)          # exact self-GMD of a square side s
    r = R_MEAN * 1e-3
    return TURNS ** 2 * MU0 * r * (math.log(8 * r / g) - 2.0)


def m_mutual(gap_mm):
    """Maxwell coaxial-filament mutual x N^2 [H] (scipy ellipk/e take m=k^2)."""
    from scipy.special import ellipe, ellipk

    r1 = r2 = R_MEAN * 1e-3
    d = gap_mm * 1e-3
    m = 4.0 * r1 * r2 / ((r1 + r2) ** 2 + d ** 2)
    k = math.sqrt(m)
    m_fil = MU0 * math.sqrt(r1 * r2) * ((2.0 / k - k) * ellipk(m) - (2.0 / k) * ellipe(m))
    return TURNS ** 2 * m_fil


def _pair_model(gap_mm):
    half = CROSS / 2.0
    return {
        "bodies": [
            {"name": "coil1", "r0": R_MEAN - half, "r1": R_MEAN + half,
             "z0": -gap_mm / 2 - half, "z1": -gap_mm / 2 + half,
             "sigma": 0.0, "mu_r": 1.0, "lc": 0.25,
             "coil": {"turns": TURNS, "current_a": 1.0}},
            {"name": "coil2", "r0": R_MEAN - half, "r1": R_MEAN + half,
             "z0": gap_mm / 2 - half, "z1": gap_mm / 2 + half,
             "sigma": 0.0, "mu_r": 1.0, "lc": 0.25,
             "coil": {"turns": TURNS, "current_a": 1.0}},
        ],
        "domain_scale": 10.0,
    }


def gate_a_pure():
    from emstudio.solvers.elmer import run_model

    l_ref = l_self_gmd()
    for gap in (10.0, 20.0, 50.0):
        res = run_model(_pair_model(gap), [1000.0], extract_coupling=True)
        lmat = res.inductance_matrix()
        l11 = lmat[("coil1", "coil1")]
        l22 = lmat[("coil2", "coil2")]
        m_fem = 0.5 * (lmat[("coil1", "coil2")] + lmat[("coil2", "coil1")])
        m_ref = m_mutual(gap)
        k_fem = res.coupling_k()[("coil1", "coil2")]
        k_ref = m_ref / l_ref
        check("L1 @ gap {0:.0f} mm vs Grover GMD".format(gap),
              abs(l11 / l_ref - 1) < 0.015,
              "{0:.6g} uH vs {1:.6g} uH ({2:+.2%})".format(
                  l11 * 1e6, l_ref * 1e6, l11 / l_ref - 1))
        check("L2 symmetric with L1 @ gap {0:.0f} mm".format(gap),
              abs(l22 / l11 - 1) < 0.005,
              "{0:+.3%}".format(l22 / l11 - 1))
        check("M @ gap {0:.0f} mm vs Maxwell filament".format(gap),
              abs(m_fem / m_ref - 1) < 0.015,
              "{0:.6g} uH vs {1:.6g} uH ({2:+.2%})".format(
                  m_fem * 1e6, m_ref * 1e6, m_fem / m_ref - 1))
        check("k @ gap {0:.0f} mm".format(gap),
              abs(k_fem / k_ref - 1) < 0.02,
              "{0:.5g} vs {1:.5g} ({2:+.2%})".format(k_fem, k_ref, k_fem / k_ref - 1))
        if gap == 20.0:
            # PDF report from a real WPT result (coupling-matrix flavor + field map)
            import tempfile

            from emstudio.report import magnetics_report

            pdf = os.path.join(tempfile.mkdtemp(prefix="emstudio_wptrep_"), "wpt.pdf")
            magnetics_report(res, pdf, title="WPT Coil Pair", author="gate")
            ok_pdf = (os.path.isfile(pdf) and os.path.getsize(pdf) >= 5000
                      and open(pdf, "rb").read(5) == b"%PDF-")
            check("magnetics PDF report (WPT coupling) is valid", ok_pdf, pdf)


def gate_c_gap_sweep():
    """Parametric k-vs-gap sweep (moving-coil engine) vs Maxwell at each gap."""
    from emstudio.solvers.elmer.sweep import sweep_wpt_gap

    model = _pair_model(10.0)  # base gap; the engine repositions per point
    gaps = [8.0, 18.0, 35.0, 55.0]
    curve = sweep_wpt_gap(model, gaps, freq_hz=100e3)
    check("gap sweep returned a point per gap", len(curve) == len(gaps),
          "{0} points".format(len(curve)))
    l_ref = l_self_gmd()
    worst = 0.0
    ks = []
    for pt in curve:
        k_ref = m_mutual(pt["gap_mm"]) / l_ref
        rel = pt["k"] / k_ref - 1
        worst = max(worst, abs(rel))
        ks.append(pt["k"])
        check("swept k @ gap {0:.0f} mm vs Maxwell".format(pt["gap_mm"]),
              abs(rel) < 0.02,
              "{0:.5g} vs {1:.5g} ({2:+.2%})".format(pt["k"], k_ref, rel))
    # k must fall monotonically with increasing gap
    mono = all(ks[i + 1] < ks[i] for i in range(len(ks) - 1))
    check("k decreases monotonically with gap", mono,
          "k = {0}".format(["{0:.4f}".format(k) for k in ks]))


def gate_b_template():
    import FreeCAD

    from emstudio.solvers import elmer
    from emstudio.templates import wpt

    gap = 20.0
    doc = FreeCAD.newDocument("WptGate")
    try:
        ana = wpt.makeWptPair(doc, radius_mm=R_MEAN, cross_mm=CROSS,
                              turns=TURNS, gap_mm=gap)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverElmer"][0]
        result = elmer.run(ana, solver)
        ks = result.coupling_k()
        assert len(ks) == 1, "expected one coil pair, got {0}".format(ks)
        k_fem = list(ks.values())[0]
        k_ref = m_mutual(gap) / l_self_gmd()
        check("template k @ gap {0:.0f} mm (FreeCAD path)".format(gap),
              abs(k_fem / k_ref - 1) < 0.03,
              "{0:.5g} vs {1:.5g} ({2:+.2%})".format(k_fem, k_ref, k_fem / k_ref - 1))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio WPT coil-coupling validation gate (Elmer)")
    print("Gate A: coil pair L/M/k vs Grover/Maxwell analytics")
    gate_a_pure()
    print("Gate C: parametric k-vs-gap sweep vs Maxwell")
    gate_c_gap_sweep()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate B: FreeCAD WPT template end-to-end")
        gate_b_template()
    else:
        print("Gate B skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("WPT GATE FAILED: {0}".format(FAILURES))
        return 1
    print("WPT GATE PASSED")
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
        raise SystemExit("wpt validation failed")
    sys.exit(0)
