# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: conjugate heat transfer — the case setup and its anchor.

Pass: exit 0 and 'CHT-SETUP GATE PASSED'.

WHY THIS EXISTS. Every thermal case before this one imposes a condition on the
cable surface — a wall temperature or a wall flux — which is an assumption
about the answer. Conjugate heat transfer solves the solid and the fluid
together and lets the interface temperature come out of the solve.

The anchor is exact. With gravity ZERO the fluid cannot convect, so a
two-region stack is conduction in series:

    q     = (T_hot - T_cold) / (L_s/k_s + L_f/k_f)
    T_int = T_hot - q * L_s/k_s

and for a linear profile on uniform cells the cell-average equals the analytic
mean, so mean(T_solid) = (T_hot + T_int)/2 exactly — a MESH-INSENSITIVE check.
The live solve matched both means to 5 decimal places (`openfoam_cht`).

⚠ g = 0 is what makes the answer exact AND what removes the buoyancy the real
cable problem needs. This validates the COUPLING, not convection. A gate that
let gravity in would be checking a different, non-exact thing — which is why
the written `constant/g` is asserted here.

FAST tier: arithmetic, guard rails, and what the writer emits. The solve is
`openfoam_cht` (SOLVER).
"""
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


BOUNDARY = """\
FoamFile { version 2.0; format ascii; class polyBoundaryMesh; object boundary; }
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

3
(
    hot
    {
        type            wall;
        nFaces          1;
    }
    sides
    {
        type            wall;
        nFaces          80;
    }
    slab_to_gap
    {
        type            mappedWall;
        sampleRegion    gap;
        samplePatch     gap_to_slab;
    }
)
"""


def main():
    from emstudio.solvers.openfoam import cht

    print("EMStudio conjugate heat transfer gate")

    # --- the analytic anchor ------------------------------------------------
    print(" the exact answer:")
    c = cht.ChtCase()
    check("fluid conductivity is Cp*mu/Pr, not a second number to disagree",
          abs(c.k_fluid - c.cp_fluid * c.mu_fluid / c.pr_fluid) < 1e-15,
          "kappa = {0:.6g} W/m/K".format(c.k_fluid))
    check("flux is the series-resistance result",
          abs(c.flux - (c.t_hot - c.t_cold) / (c.r_solid + c.r_fluid)) < 1e-12)
    check("the same flux crosses BOTH layers",
          abs((c.t_hot - c.t_interface) / c.r_solid
              - (c.t_interface - c.t_cold) / c.r_fluid) < 1e-9,
          "this is what a coupling that passes T but not flux breaks")
    check("interface temperature lies between the two faces",
          c.t_cold < c.t_interface < c.t_hot,
          "T_int = {0:.4f} K".format(c.t_interface))
    check("solid mean is the midpoint of its linear profile",
          abs(c.t_solid_mean - 0.5 * (c.t_hot + c.t_interface)) < 1e-12)
    check("fluid mean likewise",
          abs(c.t_fluid_mean - 0.5 * (c.t_interface + c.t_cold)) < 1e-12)

    # The resistances must be COMPARABLE or the interface check asserts almost
    # nothing — with copper the solid drop is ~0.006 % of the total.
    ratio = c.r_solid / c.r_fluid
    check("the two resistances are comparable, so T_int is sensitive",
          0.2 < ratio < 5.0, "R_solid/R_fluid = {0:.3f}".format(ratio))

    print(" guard rails:")
    for kw, why in (({"t_hot": 300.0, "t_cold": 350.0}, "hot face colder"),
                    ({"l_solid": 0.0}, "zero thickness"),
                    ({"k_solid": -1.0}, "negative conductivity")):
        try:
            cht.ChtCase(**kw)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)

    # --- patch discovery ----------------------------------------------------
    # ⚠ splitMeshRegions GENERATES the interface patch name; nothing in the
    # case declares it. A writer that hard-codes it produces a field whose
    # interface entry matches nothing, leaving the coupled BC at its default —
    # a solve that runs and answers a different problem.
    print(" interface patch discovery:")
    d = tempfile.mkdtemp(prefix="chtb_")
    try:
        p = os.path.join(d, "constant", "slab", "polyMesh")
        os.makedirs(p)
        with open(os.path.join(p, "boundary"), "w") as fh:
            fh.write(BOUNDARY)
        names = cht.region_patches(d, "slab")
        check("every patch is found, in file order",
              names == ["hot", "sides", "slab_to_gap"], str(names))
        check("the generated interface patch is among them",
              any(n.startswith("slab_to_") for n in names))
        raised = False
        try:
            cht.region_patches(d, "nosuchregion")
        except ValueError:
            raised = True
        check("a missing region RAISES rather than returning nothing", raised)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # --- what the writer emits ---------------------------------------------
    # --- buoyancy: what makes it real, and what silently makes it fake -----
    print(" buoyancy:")
    still = cht.ChtCase()
    check("the default case is NOT buoyant", not still.buoyant)
    check("  ...and reports Ra 0 rather than a number", still.rayleigh == 0.0)

    # ⚠ BOTH conditions, and each alone is a case that LOOKS buoyant and
    # returns the conduction answer: gravity with one cell up the cavity has
    # nowhere to convect, and cells with no gravity have nothing to drive them.
    check("gravity with ONE cell up the cavity is not buoyant",
          not cht.ChtCase(gravity=9.81, n_y=1).buoyant,
          "a convection cell needs somewhere to turn over")
    check("cells with NO gravity are not buoyant",
          not cht.ChtCase(gravity=0.0, n_y=40).buoyant)
    hot = cht.ChtCase(gravity=9.81, n_y=40)
    check("gravity AND cells is buoyant", hot.buoyant)

    ra = cht.ChtCase(gravity=9.81, n_y=40, target_ra=1.0e5)
    check("mu is derived so Ra comes out EXACTLY as asked",
          abs(ra.rayleigh - 1.0e5) / 1.0e5 < 1e-9,
          "round trip: asked 1e5, written {0:.6g}".format(ra.rayleigh))
    check("  ...and kappa follows that same mu, not a stale number",
          abs(ra.k_fluid - ra.cp_fluid * ra.mu / ra.pr_fluid) < 1e-15)

    print(" the written case:")
    d = tempfile.mkdtemp(prefix="chtw_")
    try:
        cht.write_cht(d, cht.ChtCase())
        g = open(os.path.join(d, "constant", "g")).read()
        # THE ONE THAT MATTERS MOST: gravity is what makes the anchor exact.
        check("gravity is ZERO, which is what makes the answer exact",
              "(0 0 0)" in g,
              "with buoyancy the stack is no longer pure conduction and the "
              "closed form does not apply")
        rp = open(os.path.join(d, "constant", "regionProperties")).read()
        check("both regions are declared, one fluid one solid",
              "fluid       ({0})".format(cht.FLUID_REGION) in rp
              and "solid       ({0})".format(cht.SOLID_REGION) in rp)
        cd = open(os.path.join(d, "system", "controlDict")).read()
        check("the STEADY conjugate solver is used",
              "application     chtMultiRegionSimpleFoam;" in cd,
              "chtMultiRegionFoam is transient and demands a PIMPLE block")
        solid = open(os.path.join(
            d, "constant", cht.SOLID_REGION, "thermophysicalProperties")).read()
        check("the solid carries the requested conductivity",
              "kappa   {0:.10g}".format(cht.ChtCase().k_solid).strip()
              .split()[-1] in solid.replace("kappa", "kappa "),
              "k_solid = {0}".format(cht.ChtCase().k_solid))
        check("the solid uses heSolidThermo", "heSolidThermo" in solid)
        fluid = open(os.path.join(
            d, "constant", cht.FLUID_REGION, "thermophysicalProperties")).read()
        check("the fluid states mu and Pr, from which kappa follows",
              "mu " in fluid and "Pr " in fluid)
        check("the fluid is laminar",
              "laminar" in open(os.path.join(
                  d, "constant", cht.FLUID_REGION,
                  "turbulenceProperties")).read())
        check("a cellZone is created per region",
              cht.SOLID_REGION in open(os.path.join(
                  d, "system", "topoSetDict")).read())
        # ⚠ THE EQUATION OF STATE IS WHAT DECIDES WHETHER BUOYANCY EXISTS.
        # rhoConst means density cannot answer temperature, so gravity is
        # inert and a "buoyant" case silently returns the conduction answer.
        check("a still case uses rhoConst", "rhoConst" in fluid
              and "Boussinesq" not in fluid)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    d = tempfile.mkdtemp(prefix="chtb2_")
    try:
        cht.write_cht(d, cht.ChtCase(gravity=9.81, n_y=40, target_ra=1.0e5))
        g = open(os.path.join(d, "constant", "g")).read()
        check("a buoyant case writes NON-zero gravity, along -y",
              "(0 -9.81 0)" in g, g.strip().splitlines()[-1])
        fl = open(os.path.join(
            d, "constant", cht.FLUID_REGION, "thermophysicalProperties")).read()
        check("a buoyant case uses Boussinesq, not rhoConst",
              "Boussinesq" in fl and "equationOfState rhoConst" not in fl,
              "with rhoConst the density cannot respond to T and gravity does "
              "nothing at all")
        check("  ...carrying rho0, T0 and beta", all(
            k in fl for k in ("rho0", "T0", "beta")))
        bm = open(os.path.join(d, "system", "blockMeshDict")).read()
        check("the buoyant mesh is 2-D (cells up the cavity)",
              " 40 1) simpleGrading" in bm,
              "one cell up the cavity cannot convect")
        check("front and back are EMPTY, so it is a 2-D solve",
              "frontAndBack { type empty;" in bm)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("CHT-SETUP GATE PASSED")
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
        raise SystemExit("cht-setup validation failed")
    sys.exit(0)
