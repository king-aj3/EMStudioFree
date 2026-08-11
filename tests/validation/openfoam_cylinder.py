# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — natural convection from a horizontal cylinder.

This is the ANCHOR rung of the ampacity work: ``wire/thermal.py`` takes its
film coefficient from Churchill-Chu, which is right for an isolated cylinder
and wrong for a bundle in an enclosure, and the plan is to replace it with a
solved ``h``. Before any of that can mean anything, the CFD has to reproduce
the correlation in the regime where the correlation is provably correct. If it
cannot do that, a later disagreement over a bundle would be uninterpretable —
there would be no way to separate a real confinement effect from a meshing
artifact.

WHAT THIS GATE ANCHORS ON
--------------------------
Three tiers, weakest last on purpose:

* **Exact, and needing no citation.** Pure conduction across a concentric
  annulus is Nu_D = 2/ln(r_o/r_i) in closed form (:func:`conduction_nusselt`).
  Checked analytically on a synthetic logarithmic field and live in the
  annulus mode. This is the direct analogue of the cavity's Nu -> 1.
* **Exact discrete prediction.** For an exact log field the first-order wall
  estimator must return (4 r_i/w1) ln(1 + w1/(2 r_i)) / ln(RR) — a closed form
  for what the ESTIMATOR does, as distinct from what the physics is. Matching
  it to machine precision is what proves the O-grid cell indexing, and
  watching it converge first-order onto 2/ln(RR) is what proves the indexing
  is not merely self-consistent with a wrong assumption.
* **Energy conservation and domain independence.** The annulus balances its
  two walls (radius-weighted — the raw gradients differ by the radius ratio
  even for a perfect solve). The far-field mode has no outer wall and
  therefore NO balance available, so it is defended instead by showing the
  answer stops moving as the domain grows, and by the correlation itself.

⚠ **Two traps this gate exists to hold down**, both of which produced a wrong
number during development and neither of which announces itself:

1. **rc == 0 is not convergence.** SIMPLE exits 0 just as happily when it runs
   out of iterations with residuals still falling. An 800-iteration annulus
   run returned Nu 34 % high and exited clean. There is a check below that
   deliberately UNDER-iterates and asserts the detector notices.
2. **Ra_D is built on the diameter; annulus convection is governed by the
   GAP.** Ra_L = Ra_D ((RR-1)/2)^3, so at RR 20 the gap Rayleigh number is
   857x the diameter one and a "low Ra_D" annulus is still convecting
   strongly. The conduction anchor therefore uses a NARROW gap, and the gate
   checks the answer is Ra-independent there to prove it really is conduction.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from emstudio.solvers import openfoam as ofm                    # noqa: E402
from emstudio.solvers.openfoam import cylinder as C             # noqa: E402
from emstudio.setup import openfoam as _setup                   # noqa: E402
from emstudio.wire.thermal import nu_churchill_chu              # noqa: E402

_FAILED = []

PR = 0.71


def check(label, ok, detail=""):
    line = "  {0}  {1}{2}".format("ok   " if ok else "FAIL ", label,
                                  " — {0}".format(detail) if detail else "")
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage(line + "\n")
    except Exception:
        print(line)
    if not ok:
        _FAILED.append(label)
    return ok


def _radii(dict_text):
    """Vertex radii out of a written blockMeshDict, for the geometry check."""
    m = re.search(r"vertices\s*\(\s*(.*?)\n\);", dict_text, re.S)
    out = []
    for xs, ys, _zs in re.findall(
            r"\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)",
            m.group(1)):
        out.append(math.hypot(float(xs), float(ys)))
    return out


def offline_checks():
    """Everything knowable with no solver installed."""
    print(" case algebra:")
    for ra in (1e2, 1e3, 1e4, 1e5):
        c = C.CylinderCase(ra_d=ra, pr=PR)
        check("Ra_D %.0e round-trips through the derived nu/alpha" % ra,
              abs(c.ra_written - ra) / ra < 1e-9,
              "written %.6e" % c.ra_written)
    c = C.CylinderCase(ra_d=1e4, pr=PR)
    check("Pr is exactly what was asked for",
          abs(c.nu / c.alpha - PR) < 1e-12)
    for kw, why in ((dict(ra_d=0), "Ra 0"), (dict(pr=0), "Pr 0"),
                    (dict(ra_d=-1), "negative Ra"), (dict(d_m=0), "zero D"),
                    (dict(dt=0.0), "zero dT")):
        try:
            C.CylinderCase(**kw).nu
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)
    try:
        C.CylinderCase(mode="banana")
        check("an unknown mode is rejected", False, "no error raised")
    except ValueError:
        check("an unknown mode is rejected", True)

    print(" the annulus conduction limit is a closed form:")
    check("Nu_D = 2/ln(RR): RR 2 -> 2.885390, RR 20 -> 0.667616",
          abs(C.conduction_nusselt(2.0) - 2.0 / math.log(2.0)) < 1e-12
          and abs(C.conduction_nusselt(20.0) - 0.6676164) < 1e-6,
          "%.6f / %.6f" % (C.conduction_nusselt(2.0),
                           C.conduction_nusselt(20.0)))
    for bad in (1.0, 0.5, 0.0):
        try:
            C.conduction_nusselt(bad)
            check("radius ratio %g is rejected" % bad, False)
        except ValueError:
            check("radius ratio %g is rejected" % bad, True)

    print(" the radial grading is what OpenFOAM's simpleGrading means:")
    L, n, g = 0.01, 40, 10.0
    w1 = C.first_cell_height(L, n, g)
    r = g ** (1.0 / (n - 1))
    widths = [w1 * r ** k for k in range(n)]
    check("uniform grading gives L/n exactly",
          abs(C.first_cell_height(L, n, 1.0) - L / n) < 1e-15)
    check("the graded widths sum to the full span",
          abs(sum(widths) - L) / L < 1e-12, "sum %.10e" % sum(widths))
    check("simpleGrading's ratio is last/first, and this reproduces it",
          abs(widths[-1] / widths[0] - g) / g < 1e-12)
    for kw, why in (((L, 1, g), "fewer than 2 cells"), ((0.0, n, g), "zero span"),
                    ((L, n, 0.0), "zero grading")):
        try:
            C.first_cell_height(*kw)
            check("%s is rejected" % why, False)
        except ValueError:
            check("%s is rejected" % why, True)
    r_i, r_o = 0.01, 0.02
    lc = C.radial_layer_centres(r_i, r_o, n, g)
    check("layer centres: n of them, strictly increasing, first and last "
          "half a cell inside their walls",
          len(lc) == n and all(a < b for a, b in zip(lc, lc[1:]))
          and abs(lc[0] - (r_i + widths[0] / 2.0)) < 1e-15
          and abs(lc[-1] - (r_o - widths[-1] / 2.0)) < 1e-12)

    print(" the estimator, against an exact logarithmic conduction field:")
    RR, D, dt, t_amb = 20.0, 0.020, 30.0, 300.0
    t_w = t_amb + dt
    r_i, r_o = D / 2.0, D / 2.0 * RR
    exact = C.conduction_nusselt(RR)
    errs = []
    for n_r in (30, 60, 120, 240):
        w1 = C.first_cell_height(r_o - r_i, n_r, 1.0)
        centres = C.radial_layer_centres(r_i, r_o, n_r, 1.0)
        n_t = 5
        field = [t_w - dt * math.log(rr / r_i) / math.log(RR)
                 for _b in range(4) for _j in range(n_t) for rr in centres]
        res = ofm.nusselt_cylinder_from_field(field, n_r, n_t, t_w, t_amb, D, w1)
        pred = (4.0 * r_i / w1) * math.log(1.0 + w1 / (2.0 * r_i)) / math.log(RR)
        if n_r == 60:
            check("the estimator equals its closed form to machine precision "
                  "(this is what proves the O-grid cell indexing)",
                  abs(res.nu_d - pred) < 1e-12 * abs(pred),
                  "%.12f vs %.12f" % (res.nu_d, pred))
        errs.append(abs(res.nu_d - exact) / exact)
    ratios = [b / a for a, b in zip(errs, errs[1:])]
    check("...and refining halves the error — first order onto 2/ln(RR), "
          "which the estimator does not know",
          all(0.45 < q < 0.65 for q in ratios),
          "errors " + " -> ".join("%.4f%%" % (100 * e) for e in errs))
    check("the approach to the exact value is from BELOW (a first-order "
          "wall gradient under-reads a convex profile)",
          all(e > 0 for e in errs))

    print(" the reader refuses what it cannot honestly read:")
    good = [300.0] * (4 * 10 * 5)
    for kw, why in (
            (dict(values=[300.0] * 17, n_r=10, n_theta=5),
             "a field whose length does not match the O-grid"),
            (dict(values=good, n_r=1, n_theta=5), "fewer than 2 radial cells"),
            (dict(values=good, n_r=10, n_theta=5, t_amb=330.0),
             "equal wall and ambient temperatures"),
            (dict(values=good, n_r=10, n_theta=5, first_cell_m=0.0),
             "a non-positive first cell")):
        kw2 = dict(n_r=10, n_theta=5, t_wall=330.0, t_amb=300.0, d_m=0.02,
                   first_cell_m=1e-4, values=good)
        kw2.update(kw)
        try:
            ofm.nusselt_cylinder_from_field(**kw2)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)
    res = ofm.nusselt_cylinder_from_field(good, 10, 5, 330.0, 300.0, 0.02, 1e-4)
    check("with no outer wall the imbalance is inf, not a reassuring zero",
          res.imbalance == float("inf"))

    print(" the written case, in both modes:")
    for mode in ("annulus", "farfield"):
        tmp = tempfile.mkdtemp()
        try:
            case = C.CylinderCase(mode=mode, radius_ratio=4.0, n_r=8,
                                  n_theta=4, iterations=10)
            C.write_cylinder(tmp, case)
            for rel in ("system/blockMeshDict", "system/controlDict",
                        "system/fvSchemes", "system/fvSolution",
                        "constant/transportProperties",
                        "constant/turbulenceProperties", "constant/g",
                        "0/T", "0/U", "0/p_rgh", "0/alphat"):
                check("%s: writes %s" % (mode, rel),
                      os.path.isfile(os.path.join(tmp, rel)))

            def read(rel):
                with open(os.path.join(tmp, rel), encoding="utf-8") as fh:
                    return fh.read()

            bm = read("system/blockMeshDict")
            # Without arc edges blockMesh joins the vertices with straight
            # lines and meshes a SQUARE — silently, and it still solves.
            check("%s: the blockMeshDict curves (16 arc edges, 4 per circle "
                  "per z-level)" % mode, bm.count("arc ") == 16,
                  "%d found" % bm.count("arc "))
            rad = _radii(bm)
            check("%s: all 16 vertices lie on the two circles" % mode,
                  len(rad) == 16
                  and sum(1 for v in rad if abs(v - case.r_in) < 1e-12) == 8
                  and sum(1 for v in rad if abs(v - case.r_out) < 1e-12) == 8,
                  "radii %s" % sorted({round(v, 6) for v in rad}))
            check("%s: ESI turbulenceProperties, not Foundation's "
                  "momentumTransport" % mode,
                  "momentumTransport" not in read("constant/turbulenceProperties"))

            t, p, fvsol = read("0/T"), read("0/p_rgh"), read("system/fvSolution")
            if mode == "annulus":
                check("annulus: outer boundary is a WALL at ambient",
                      "farfield { type wall;" in bm and "fixedValue" in t)
                check("annulus: the closed domain pins the pressure level "
                      "(pRefCell)", "pRefCell" in fvsol)
            else:
                check("farfield: outer boundary is an open PATCH",
                      "farfield { type patch;" in bm)
                check("farfield: T is inletOutlet (a fixedValue would drag "
                      "the plume back to ambient on the way OUT)",
                      "inletOutlet" in t)
                check("farfield: p_rgh is totalPressure", "totalPressure" in p)
                check("farfield: the OPEN domain does NOT also pin the "
                      "pressure — that would over-constrain it",
                      "pRefCell" not in fvsol)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def live_checks():
    """The physics, on real solves. Requires a usable ESI OpenFOAM."""
    info = _setup.find_openfoam()
    if not info.found or not info.usable:
        raise SystemExit(
            "openfoam_cylinder needs a usable ESI OpenFOAM; discovery says: "
            + (info.describe() or "nothing found"))
    print(" live solve (%s):" % info.describe())
    base = tempfile.mkdtemp(prefix="emstudio-cyl-")
    try:
        _live_conduction(base)
        _live_convergence_detector(base)
        _live_farfield(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _case_dir(base, name):
    d = os.path.join(base, name)
    os.makedirs(d)
    return d


def _live_conduction(base):
    """Annulus, narrow gap, low Ra -> the exact conduction limit."""
    print("  annulus conduction limit (narrow gap, so Ra_L really is low):")
    got = {}
    for ra in (1e-2, 1e2):
        case = C.CylinderCase(ra_d=ra, pr=PR, mode="annulus", radius_ratio=2.0,
                              n_r=40, n_theta=20, grading=10.0,
                              iterations=10000)
        rep, res = ofm.run_cylinder(_case_dir(base, "cond%g" % ra), case)
        if not check("Ra_D %.0e: the chain completes" % ra, rep["ok"],
                     rep.get("failed_at", "") or ""):
            continue
        check("Ra_D %.0e: residualControl actually fired" % ra,
              rep["converged"])
        got[ra] = res.nu_d
        exact = case.conduction_nu
        check("Ra_D %.0e recovers Nu_D = 2/ln(RR) = %.6f within 0.5 %%"
              % (ra, exact), abs(res.nu_d - exact) / exact < 5e-3,
              "Nu %.6f (%+.3f %%)" % (res.nu_d,
                                      100 * (res.nu_d - exact) / exact))
        check("Ra_D %.0e: the two walls balance (radius-weighted)" % ra,
              res.imbalance < 2e-2, "imbalance %.2e" % res.imbalance)
    if len(got) == 2:
        a, b = got[1e-2], got[1e2]
        check("the answer is Ra-INDEPENDENT here, which is what makes it a "
              "conduction limit rather than a coincidence",
              abs(a - b) / a < 1e-3, "%.6f vs %.6f" % (a, b))


def _live_convergence_detector(base):
    """A gate check that must FAIL to converge — testing the detector itself.

    rc == 0 is not convergence, and an under-iterated run is the exact shape
    that produced a 34 %-wrong Nusselt number during development. If this
    check ever reports converged, the detector has stopped working and every
    "converged" elsewhere in this gate is worthless.
    """
    print("  the convergence detector (deliberately under-iterated):")
    case = C.CylinderCase(ra_d=1e2, pr=PR, mode="annulus", radius_ratio=2.0,
                          n_r=40, n_theta=20, grading=10.0, iterations=200)
    rep, res = ofm.run_cylinder(_case_dir(base, "under"), case)
    if not check("the under-iterated run still exits cleanly (rc 0)",
                 rep["ok"], rep.get("failed_at", "") or ""):
        return
    check("...and is reported as NOT converged", not rep["converged"])
    check("...and says so in a warning rather than only in a flag",
          any("residualControl" in w for w in res.warnings))
    exact = case.conduction_nu
    check("...and it is indeed wrong, which is why the flag matters",
          abs(res.nu_d - exact) / exact > 5e-3,
          "Nu %.4f vs %.4f exact" % (res.nu_d, exact))


def _live_farfield(base):
    """Open domain against the ENVELOPE of both published correlations.

    ⚠ **Gating on Churchill-Chu alone would be gating on the wrong number.**
    The two standard correlations for this exact case disagree by 4-17 % over
    the cable regime — measured here: CC reads 17.4 % below Morgan at Ra 1e2,
    8.9 % below at 1e4, 4.2 % below at 1e6 — and `wire/thermal.py`'s own
    docstring already records that CC "reads slightly LOW vs Morgan at low Ra
    (conservative for ampacity)". A solve cannot be validated to better than
    the literature disagrees with itself, so the band IS the envelope, and
    pretending otherwise would either fail a correct solve or hide a wrong one.

    Measured, converged, at RR 20 (Nu / CC err / Morgan err):
        Ra 1e2   1.9197   +14.97 %   -4.98 %
        Ra 1e3   3.0000   +14.88 %   -3.68 %
        Ra 1e4   4.8207   +10.23 %   +0.43 %
        Ra 1e5   7.9788    +2.59 %   -6.52 %
    i.e. inside the envelope at three of four, and 0.43 % over Morgan at the
    fourth. The MARGIN below is not tuned to make that pass — it is the sum of
    two measured systematics: the first-order wall gradient (-0.7 % at this
    resolution, from the conduction case) and the domain-size sensitivity
    (below 1 % over a 4x domain).

    ⚠ **Note what the numbers do NOT support.** The CFD tracks Morgan closely
    at the bottom of the cable regime and Churchill-Chu at the top — its
    position inside the envelope MOVES with Ra. So "the CFD agrees with
    Morgan" is not a claim this data licenses, and a check asserting it was
    written, failed at Ra 1e5, and was replaced. The defensible statement is
    the weaker one: the CFD agrees with both correlations to within the
    correlations' own mutual disagreement.

    ⚠ **The domain is PINNED at RR 20**, and the sensitivity is small once
    measured properly. The first sweep held `n_r` fixed while growing the
    domain, which coarsened the wall cell 4x — so it read +4.04 % at RR 80 and
    attributed to the DOMAIN what was mostly RESOLUTION. Re-run with the wall
    spacing held constant (RR 40 at n_r 126, RR 80 at n_r 254, w1 within 1.5 %
    of each other throughout):

        RR 20  n_r  60   Nu 4.82074   (reference)
        RR 40  n_r 126   Nu 4.84071   +0.41 %
        RR 80  n_r 254   Nu 4.86274   +0.87 %   (drift 9.8e-3 — not fully
                                                 settled, so an upper bound)

    So RR 20 is within about 1 % of a domain four times larger. RR stays part
    of the case definition and every number is quoted at RR 20, but the earlier
    "real domain sensitivity" reading was an artifact of a confounded sweep.
    *A convergence study that moves two things at once measures neither.*
    """
    print("  far field vs the correlation ENVELOPE:")

    def morgan(ra):
        """Morgan power-law bands — the same constants tests/validation/
        thermal.py already cross-checks Churchill-Chu against."""
        for lo, hi, c_m, n_m in ((1e-2, 1e2, 1.02, 0.148),
                                 (1e2, 1e4, 0.850, 0.188),
                                 (1e4, 1e7, 0.480, 0.250)):
            if lo <= ra < hi:
                return c_m * ra ** n_m
        return None

    #: first-order wall gradient (-0.7 %) + domain sensitivity (~1 %/doubling),
    #: rounded up. Stated as a mechanism, not fitted to the observations.
    MARGIN = 0.05

    got = {}
    for ra in (1e2, 1e3, 1e4, 1e5):
        case = C.CylinderCase(ra_d=ra, pr=PR, mode="farfield",
                              radius_ratio=20.0, n_r=60, n_theta=30,
                              grading=40.0, iterations=6000,
                              write_interval=3000)
        rep, res = ofm.run_cylinder(_case_dir(base, "ff%g" % ra), case)
        if not check("Ra_D %.0e: the chain completes" % ra, rep["ok"],
                     rep.get("failed_at", "") or ""):
            continue
        # residualControl is unreachable on the open domain (measured: Nu flat
        # to 0.01 % from iteration 2500 to 30000 while residuals sat near
        # 1e-3), so convergence is judged on the quantity of interest.
        check("Ra_D %.0e: Nu has stopped moving between snapshots" % ra,
              rep["nu_drift"] is not None and rep["nu_drift"] < 5e-3,
              "drift %.2e" % (rep["nu_drift"] if rep["nu_drift"] is not None
                              else float("nan")))
        got[ra] = res.nu_d
        cc, mo = nu_churchill_chu(ra, PR), morgan(ra)
        lo, hi = min(cc, mo) * (1 - MARGIN), max(cc, mo) * (1 + MARGIN)
        check("Ra_D %.0e lies inside the Churchill-Chu/Morgan envelope "
              "(+-%.0f %% for the known systematics)" % (ra, MARGIN * 100),
              lo <= res.nu_d <= hi,
              "Nu %.4f in [%.4f, %.4f]; CC %.4f (%+.2f %%), Morgan %.4f "
              "(%+.2f %%)" % (res.nu_d, lo, hi, cc, 100 * (res.nu_d - cc) / cc,
                              mo, 100 * (res.nu_d - mo) / mo))
        # The envelope is 4-17 % wide, so "inside it" alone would survive a
        # sizeable regression — this tightens it without inventing a claim.
        #
        # ⚠ A "sits nearer Morgan" check was written here first and was
        # WRONG. It holds at Ra 1e2/1e3/1e4 and FAILS at 1e5, where the CFD is
        # 2.59 % from Churchill-Chu and 6.52 % from Morgan. The position
        # inside the envelope MOVES with Ra — near Morgan at the bottom of the
        # cable regime, near Churchill-Chu at the top — so there is no
        # directional invariant to gate on, and asserting one meant asserting
        # something the sweep output already contradicted.
        #
        # Distance from the envelope MIDPOINT is the symmetric statement that
        # survives. Measured: +4.05 %, +4.78 %, +5.10 %, -2.18 % at
        # 1e2/1e3/1e4/1e5, so 8 % is the measured maximum plus headroom.
        mid = 0.5 * (cc + mo)
        check("Ra_D %.0e sits within 8 %% of the envelope MIDPOINT" % ra,
              abs(res.nu_d - mid) / mid < 0.08,
              "%+.2f %% of midpoint %.4f (CC %.4f / Morgan %.4f)"
              % (100 * (res.nu_d - mid) / mid, mid, cc, mo))

    if len(got) >= 3:
        seq = [got[k] for k in sorted(got)]
        check("Nu increases monotonically with Ra",
              all(b > a for a, b in zip(seq, seq[1:])),
              " -> ".join("%.4f" % v for v in seq))


def main():
    print("OPENFOAM-CYLINDER GATE")
    offline_checks()
    live_checks()
    if _FAILED:
        raise SystemExit("OPENFOAM-CYLINDER GATE FAILED: %s"
                         % ", ".join(_FAILED))
    print("OPENFOAM-CYLINDER GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    main()
