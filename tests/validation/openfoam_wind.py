# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — wind loading, the mechanical axis.

Every other OpenFOAM gate here is thermal. This one asks what force the wind
puts on a structure, so it can be sized to survive.

WHY THE ANCHOR IS Re 20-40 AND NOT Cd ~1.2
--------------------------------------------
A circular cylinder's drag is one of the best-characterised numbers in fluid
mechanics, and **steady RANS is bad at it**: above Re ~47 the real flow sheds
vortices, and a steady solve produces a symmetric wake that UNDER-reads drag.
Gating on the familiar Cd ~1.2 at Re 1e5 would gate on a number this method
cannot produce — a check that can only be passed by luck or by tuning.

So the anchor is the low-Re regime where the flow genuinely IS steady, exactly
as the cavity anchored on the conduction limit rather than on a convective
correlation. Prove the method where it is valid; refuse to imply it is valid
elsewhere.

THE ANCHORS, strongest first
-----------------------------
* **Zero lift by symmetry.** A symmetric body at zero incidence has NO lift.
  This is exact, needs no citation, and is the sharpest available check that
  the force integration is oriented and scaled correctly — measured |Cl|/|Cd|
  ~2e-7.
* **Pressure + viscous = total**, componentwise. A conservation check on the
  function object's own arithmetic, again reference-free.
* **Drag falls with Re** through the laminar range, and the viscous SHARE of
  it falls too — at low Re skin friction matters more, which is a physical
  statement the numbers must reproduce rather than a tolerance.
* **The published values**, last and flagged: Cd 2.0646 at Re 20 and 1.5448 at
  Re 40 sit within ~1 % of the classical steady-laminar benchmarks. ⚠ Those
  benchmark numbers are quoted from memory of the standard literature and are
  NOT verified from a primary source here, so they are recorded as context and
  the gate does NOT fail on them. Hard-coding a remembered reference is the
  mistake `foam_run.py` already carries a note about.

⚠ Above Re ~47 the case REFUSES to be read as a wind load — `validity_note()`
says so and the runner surfaces it whether or not the caller asked.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from emstudio.solvers import openfoam as ofm                    # noqa: E402
from emstudio.solvers.openfoam import wind as W                 # noqa: E402
from emstudio.setup import openfoam as _setup                   # noqa: E402

_FAILED = []

#: Context only — see the docstring. NOT gated on.
CLASSICAL = {20.0: 2.05, 40.0: 1.54}


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


def offline_checks():
    print(" case validation:")
    for kw, why in ((dict(reynolds=0), "zero Reynolds number"),
                    (dict(reynolds=-5), "negative Reynolds number"),
                    (dict(d_ref=0), "zero reference diameter"),
                    (dict(radius_ratio=1.5), "a far field inside 2 diameters"),
                    (dict(n_r=2), "fewer than 4 cells")):
        try:
            W.WindCase(**kw)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)

    c = W.WindCase(reynolds=20.0, d_ref=0.02, nu=1.5e-5)
    check("the freestream speed reproduces the requested Re exactly",
          abs(c.u_inf * c.d_ref / c.nu - 20.0) < 1e-12,
          "U = %.6f m/s" % c.u_inf)
    check("q_ref = 1/2 rho U^2 A, so force/q_ref is a coefficient",
          abs(c.q_ref - 0.5 * c.rho * c.u_inf ** 2 * c.a_ref) < 1e-18)

    print(" the shedding guard (where a STEADY solve stops being valid):")
    check("Re 20 and 40 are below the shedding onset — steady is valid",
          W.WindCase(reynolds=20.0).steady_is_valid
          and W.WindCase(reynolds=40.0).steady_is_valid)
    check("Re 1e5 — real antenna loading — is NOT, and says why",
          not W.WindCase(reynolds=1e5).steady_is_valid
          and "UNSTEADY" in W.WindCase(reynolds=1e5).validity_note())
    check("...and a valid case carries no caveat to ignore",
          W.WindCase(reynolds=20.0).validity_note() == "")

    print(" the written case:")
    tmp = tempfile.mkdtemp()
    try:
        W.write_wind(tmp, W.WindCase(reynolds=20.0, n_r=8, n_theta=4,
                                     iterations=5))
        for rel in ("system/blockMeshDict", "system/controlDict",
                    "system/fvSchemes", "system/fvSolution",
                    "constant/transportProperties",
                    "constant/turbulenceProperties", "0/U", "0/p"):
            check("writes %s" % rel, os.path.isfile(os.path.join(tmp, rel)))

        def read(rel):
            with open(os.path.join(tmp, rel), encoding="utf-8") as fh:
                return fh.read()

        ctrl, u0, bm = read("system/controlDict"), read("0/U"), \
            read("system/blockMeshDict")
        check("the forces function object is requested on the cylinder patch",
              "type            forces;" in ctrl and "patches         (cylinder)"
              in ctrl)
        # ⚠ simpleFoam is INCOMPRESSIBLE: its p is kinematic, so without
        # rhoInf the forces come back short by a factor of rho — a plausible
        # number that is simply wrong.
        check("rhoInf is given, because simpleFoam's pressure is KINEMATIC "
              "and forces would otherwise be short by a factor of rho",
              "rho             rhoInf;" in ctrl and "rhoInf          1.2" in ctrl)
        # ⚠ one patch does BOTH inflow and outflow on an external O-grid.
        check("the far field is a freestream boundary, not a fixed inlet "
              "(one patch does both inflow and outflow here)",
              "freestreamVelocity" in u0 and "freestreamPressure" in read("0/p"))
        check("the mesh curves (16 arc edges) — without them blockMesh would "
              "mesh a SQUARE and still solve", bm.count("arc ") == 16)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the force reader:")
    good = ("Sum of forces\n    Total    : (2.0 0.5 0)\n"
            "    Pressure : (1.5 0.4 0)\n    Viscous  : (0.5 0.1 0)\n")
    r = ofm.forces_from_log(good, q_ref=2.0)
    check("Cd and Cl are force/q_ref, exactly",
          abs(r.cd - 1.0) < 1e-12 and abs(r.cl - 0.25) < 1e-12)
    check("pressure + viscous == total is checked, not assumed",
          r.split_exact)
    bad = ("Sum of forces\n    Total    : (2.0 0 0)\n"
           "    Pressure : (1.0 0 0)\n    Viscous  : (0.5 0 0)\n")
    check("...and an inconsistent split is FLAGGED",
          any("does not equal" in w
              for w in ofm.forces_from_log(bad, q_ref=2.0).warnings))
    two = good + "some iterations later\n" + (
        "Sum of forces\n    Total    : (4.0 0 0)\n"
        "    Pressure : (3.0 0 0)\n    Viscous  : (1.0 0 0)\n")
    check("the LAST report is used, not the first (early iterations are not "
          "the answer)", abs(ofm.forces_from_log(two, 2.0).cd - 2.0) < 1e-12)
    for text, why in (("", "an empty log"),
                      ("nothing useful here", "a log with no force block")):
        try:
            ofm.forces_from_log(text, 2.0)
            check("%s raises rather than returning zero" % why, False)
        except ValueError:
            check("%s raises rather than returning zero" % why, True)
    try:
        ofm.forces_from_log(good, q_ref=0.0)
        check("a zero reference pressure is rejected", False)
    except ValueError:
        check("a zero reference pressure is rejected", True)
    back = ("Sum of forces\n    Total    : (-2.0 0 0)\n"
            "    Pressure : (-1.5 0 0)\n    Viscous  : (-0.5 0 0)\n")
    check("negative drag (body pushed UPSTREAM) is flagged, not returned "
          "quietly",
          any("upstream" in w.lower()
              for w in ofm.forces_from_log(back, 2.0).warnings))


def live_checks():
    info = _setup.find_openfoam()
    if not info.found or not info.usable:
        raise SystemExit(
            "openfoam_wind needs a usable ESI OpenFOAM; discovery says: "
            + (info.describe() or "nothing found"))
    print(" live solve (%s):" % info.describe())
    base = tempfile.mkdtemp(prefix="emstudio-wind-")
    got = {}
    try:
        for re_n in (20.0, 40.0):
            d = os.path.join(base, "re%g" % re_n)
            os.makedirs(d)
            rep, res = ofm.run_wind(d, W.WindCase(reynolds=re_n,
                                                  iterations=3000))
            if not check("Re %g: the chain completes" % re_n, rep["ok"],
                         rep.get("failed_at", "") or ""):
                continue
            mesh = [s for s in rep["steps"] if s["step"] == "checkMesh"]
            check("Re %g: checkMesh reports Mesh OK" % re_n,
                  bool(mesh) and "Mesh OK" in mesh[0]["tail"])
            got[re_n] = res
            # THE exact anchor: a symmetric body at zero incidence has no lift.
            check("Re %g: ZERO LIFT by symmetry — exact, and the sharpest "
                  "check that the force integration is oriented right" % re_n,
                  res.lift_to_drag < 1e-4,
                  "|Cl|/|Cd| = %.2e (Cd %.4f)" % (res.lift_to_drag, res.cd))
            check("Re %g: pressure + viscous == total" % re_n, res.split_exact)
            check("Re %g: drag is positive (the body is pushed downstream)"
                  % re_n, res.cd > 0, "Cd %.4f" % res.cd)
            check("Re %g: no validity caveat — steady is valid here" % re_n,
                  "validity" not in rep)

        if len(got) == 2:
            cd20, cd40 = got[20.0].cd, got[40.0].cd
            check("drag FALLS with Reynolds number through the laminar range",
                  cd40 < cd20, "Cd %.4f -> %.4f" % (cd20, cd40))
            # physical, not a tolerance: skin friction matters more at low Re.
            s20 = got[20.0].viscous[0] / got[20.0].total[0]
            s40 = got[40.0].viscous[0] / got[40.0].total[0]
            check("...and the VISCOUS share of drag falls too — skin friction "
                  "matters more at low Re",
                  s40 < s20, "%.1f %% -> %.1f %%" % (100 * s20, 100 * s40))
            # context only; NOT gated on (see the docstring).
            for re_n in (20.0, 40.0):
                print("      Re %-4g Cd %.4f   (classical steady-laminar value "
                      "~%.2f — context, NOT gated: second-hand)"
                      % (re_n, got[re_n].cd, CLASSICAL[re_n]))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    print("OPENFOAM-WIND GATE")
    offline_checks()
    live_checks()
    if _FAILED:
        raise SystemExit("OPENFOAM-WIND GATE FAILED: %s" % ", ".join(_FAILED))
    print("OPENFOAM-WIND GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    main()
