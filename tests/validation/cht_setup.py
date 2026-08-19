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

    print(" the Nu recovery (gap_nusselt):")
    # Fed the EXACT conduction solid mean, the recovery must return the
    # closed-form conduction state: q = case.flux, T_int = case.t_interface,
    # and Nu = 1 by definition (actual flux equals the pure-conduction flux).
    # This is the identity that catches a factor slip or a swapped resistance
    # in the recovery formulas the SOLVER gate and the dialog both lean on.
    cond = cht.ChtCase(gravity=9.81, n_y=60, n_fluid=40, target_ra=1.0e6)
    m = cht.gap_nusselt(cond, cond.t_solid_mean)
    check("exact conduction mean recovers q = case.flux",
          abs(m.q - cond.flux) / cond.flux < 1e-12,
          "q {0:.6g} vs flux {1:.6g}".format(m.q, cond.flux))
    check("  ...and T_int = case.t_interface",
          abs(m.t_interface - cond.t_interface) < 1e-9)
    check("  ...and Nu = 1 exactly (conduction is the definition of Nu 1)",
          abs(m.nu - 1.0) < 1e-12, "Nu {0:.12f}".format(m.nu))
    check("  ...and Ra is interface-referenced, so BELOW the nominal Ra",
          0 < m.ra < cond.rayleigh,
          "Ra_int {0:.4g} vs nominal {1:.4g} — the solid takes part of the "
          "drop".format(m.ra, cond.rayleigh))
    # Order alone cannot catch a dt-scaling slip (Ra from dt/2 still sits
    # below nominal — proven by mutation). Ra is LINEAR in dt at fixed
    # written properties, and the round-trip check above pins the nominal
    # exactly, so this pins the interface Ra to machine precision.
    want_ra = cond.rayleigh * m.dt_gap / (cond.t_hot - cond.t_cold)
    check("  ...and Ra scales EXACTLY linearly with the recovered gap dT",
          abs(m.ra - want_ra) <= 1e-9 * want_ra,
          "Ra_int {0:.10g} vs nominal*dt_gap/dt_nominal {1:.10g}".format(
              m.ra, want_ra))
    # A COLDER solid mean means MORE flux left the solid: convection. The
    # recovery must move Nu UP for it, and refuse an unphysical mean.
    m2 = cht.gap_nusselt(cond, cond.t_solid_mean - 1.0)
    check("a colder solid mean reads as MORE convection", m2.nu > m.nu,
          "Nu {0:.4f} -> {1:.4f}".format(m.nu, m2.nu))
    raised = False
    try:
        # A solid mean this cold implies the interface AT/BELOW the cold face
        # (q*R_solid >= the whole drop) — no steady conjugate state does that.
        cht.gap_nusselt(cond, 320.0)
    except ValueError:
        raised = True
    check("an unphysical solid mean REFUSES rather than returning a number",
          raised)

    print(" the dialog's headless contract (ui.cht_dialog):")
    from emstudio.ui import cht_dialog

    dlg_case = cht_dialog.make_case(t_hot=350.0, t_cold=300.0,
                                    l_solid_m=0.020, k_solid=0.10,
                                    l_fluid_m=0.005, height_m=0.020,
                                    buoyant=True)
    check("the dialog's buoyant case IS buoyant", dlg_case.buoyant)
    # ⚠ The gates derive an artificial mu to HIT a target Ra; the dialog
    # must solve REAL air and report the Ra that results. A derived mu here
    # would make every user answer quietly wrong for their actual gap.
    check("the dialog solves REAL air — mu is never derived",
          dlg_case.target_ra == 0.0 and dlg_case.mu == dlg_case.mu_fluid,
          "mu {0:.3g} vs air {1:.3g}".format(dlg_case.mu, dlg_case.mu_fluid))
    cond_case = cht_dialog.make_case(t_hot=350.0, t_cold=300.0,
                                     l_solid_m=0.020, k_solid=0.10,
                                     l_fluid_m=0.005, height_m=0.020,
                                     buoyant=False)
    check("buoyancy OFF gives the exact-conduction shape",
          not cond_case.buoyant and cond_case.n_y == 1
          and cond_case.gravity == 0.0,
          "gravity or cells left on would break the closed-form claim")

    prose = cht_dialog.describe_case(cond_case)
    check("the plan says it does NOT read the document",
          "NOT read from the document" in prose,
          "the reference-trefoil lesson: a parametric solve must say so")
    check("the plan carries the exact conduction reference",
          ("%.3f" % cond_case.flux) in prose
          and ("%.2f" % cond_case.t_interface) in prose,
          "prose that does not show the numbers cannot be checked against "
          "them")
    check("the buoyant plan names the nominal Ra",
          ("%.3g" % dlg_case.rayleigh) in cht_dialog.describe_case(dlg_case))

    check("no note inside the validated envelope",
          cht_dialog.regime_note(dlg_case, ra=8.5e5) == "")
    # ⚠ On a case whose ASPECT IS OFF-RANGE, or coincidence passes this:
    # a conduction stack with aspect 4 returns "" through the fall-through
    # path whether or not the not-buoyant guard exists (proven by mutation
    # in review — the guard was deletable). The closed form applies at any
    # aspect, so conduction must stay silent even where buoyant would warn.
    check("conduction mode never warns — even at an off-range aspect",
          cht_dialog.regime_note(cht_dialog.make_case(
              t_hot=350.0, t_cold=300.0, l_solid_m=0.020, k_solid=0.10,
              l_fluid_m=0.005, height_m=0.100, buoyant=False)) == "")
    note = cht_dialog.regime_note(dlg_case, ra=1.0e8)
    check("beyond-laminar Ra is called UNVALIDATED", "UNVALIDATED" in note,
          note[:60])
    wide = cht_dialog.make_case(t_hot=350.0, t_cold=300.0,
                                l_solid_m=0.020, k_solid=0.10,
                                l_fluid_m=0.005, height_m=0.100,
                                buoyant=True)
    check("an off-range aspect is named (H/L 20)",
          "aspect" in cht_dialog.regime_note(wide, ra=8.5e5))

    # Straddle every envelope edge — a bound only tested far from itself
    # can drift 9x and still pass (proven by mutation in review).
    check("Ra edge: 1.01e7 warns, 0.99e7 is silent",
          "UNVALIDATED" in cht_dialog.regime_note(dlg_case, ra=1.01e7)
          and cht_dialog.regime_note(dlg_case, ra=0.99e7) == "")

    def _at_height(h_m, buoyant=True):
        return cht_dialog.make_case(t_hot=350.0, t_cold=300.0,
                                    l_solid_m=0.020, k_solid=0.10,
                                    l_fluid_m=0.005, height_m=h_m,
                                    buoyant=buoyant)
    check("aspect LOW edge: 1.9 warns, 2.1 is silent",
          "aspect" in cht_dialog.regime_note(_at_height(0.0095), ra=8.5e5)
          and cht_dialog.regime_note(_at_height(0.0105), ra=8.5e5) == "")
    check("aspect HIGH edge: 10.1 warns, 9.9 is silent",
          "aspect" in cht_dialog.regime_note(_at_height(0.0505), ra=8.5e5)
          and cht_dialog.regime_note(_at_height(0.0495), ra=8.5e5) == "")

    # The temperature axis — the review's high finding: 300 K constants
    # under a UI that accepts 1000 K.
    hot_film = cht_dialog.make_case(t_hot=420.0, t_cold=360.0,
                                    l_solid_m=0.020, k_solid=0.10,
                                    l_fluid_m=0.005, height_m=0.020,
                                    buoyant=True)
    check("a film far from 300 K names the property drift",
          "air properties" in cht_dialog.regime_note(hot_film, ra=8.5e5))
    raised = False
    try:
        cht_dialog.make_case(t_hot=700.0, t_cold=300.0,
                             l_solid_m=0.020, k_solid=0.10,
                             l_fluid_m=0.005, height_m=0.020, buoyant=True)
    except ValueError:
        raised = True
    check("a hot face past the Boussinesq limit REFUSES",
          raised, "rho0*(1-beta*(T-300)) hits zero at ~603 K — a solve "
          "there prints confident numbers from negative-density air")
    check("  ...but the SAME temperatures are fine as pure conduction",
          not cht_dialog.make_case(t_hot=700.0, t_cold=300.0,
                                   l_solid_m=0.020, k_solid=0.10,
                                   l_fluid_m=0.005, height_m=0.020,
                                   buoyant=False).buoyant,
          "the EOS limit is a buoyancy problem; conduction has no EOS")

    # The instrument floor: a near-zero-resistance solid leaves gap_nusselt
    # dividing solver noise (the anchor's solid takes 2.6 % — measurable).
    metal = cht_dialog.make_case(t_hot=350.0, t_cold=300.0,
                                 l_solid_m=0.0001, k_solid=500.0,
                                 l_fluid_m=0.005, height_m=0.020,
                                 buoyant=True)
    check("an unmeasurably conductive solid is named",
          "noise" in cht_dialog.regime_note(metal, ra=8.5e5))

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

        # ⚠ THE CHECK ABOVE ASSERTS A LABEL, AND A LABEL CANNOT FAIL: the
        # writer shipped with the empty faces on the Y-planes (gravity's own
        # direction OUT of the solved plane, the z-walls one no-slip cell
        # apart — Hele-Shaw drag, Nu pinned at ~1.9 at ANY Ra and ANY scale)
        # and this gate stayed green for four days of misdiagnosis, because
        # the string "frontAndBack { type empty;" was present either way.
        # So verify the GEOMETRY: recompute every face's plane from the
        # vertex coordinates.
        import re as _re
        verts = [tuple(float(x) for x in m.groups())
                 for m in _re.finditer(
                     r"\(\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*\)",
                     bm.split("vertices", 1)[1].split(");", 1)[0])]

        def _face_axis(idx):
            """The axis (0=x,1=y,2=z) all four corners share, or None."""
            pts = [verts[i] for i in idx]
            for ax in range(3):
                if len({p[ax] for p in pts}) == 1:
                    return ax
            return None

        def _faces(patch):
            blk = _re.search(patch + r"\s*\{[^}]*faces\s*\(([^;]*)\);", bm,
                             _re.S).group(1)
            return [[int(i) for i in m.group(1).split()]
                    for m in _re.finditer(r"\(([\d\s]+)\)", blk)]

        for f in _faces("frontAndBack"):
            check("empty face %s lies on a Z-plane (the 1-cell direction)"
                  % f, _face_axis(f) == 2,
                  "it lies on axis %s — gravity or the flow plane is wrong"
                  % _face_axis(f))
        for f in _faces("topBottom"):
            check("wall face %s lies on a Y-plane (closing the cell)"
                  % f, _face_axis(f) == 1,
                  "it lies on axis %s" % _face_axis(f))
        for f in _faces("hot") + _faces("cold"):
            check("driven face %s lies on an X-plane" % f,
                  _face_axis(f) == 0, "axis %s" % _face_axis(f))
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
