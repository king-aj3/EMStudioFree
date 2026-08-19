# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — the open-air solid-convection SETUP (§8a), offline.

FAST tier: no OpenFOAM, no FreeCAD, no Qt. Checks the arithmetic the live
sphere anchor stands on, the refusals, and the written case — the same
split every other openfoam-family feature uses (cht_setup, wind_transient):
the mechanism is cheap to check exhaustively; the physics costs a solver
and lives in the SOLVER-tier gate.

The sharp checks:

* the conduction SANDWICH is exact mathematics — both bounds are asserted
  against the closed form AND against each other (lower < upper, both -> 2
  as the box grows);
* the prescribed gradient is flux over the AIR conductivity — the
  same-file trap the bundle documents (a solid's k here would be ~1e4
  wrong and look plausible in the dictionary);
* gravity is written along −z — the DOCUMENT's down. A −y case (the
  bundle's 2-D convention) would convect sideways across the user's
  geometry and still converge beautifully.
"""
import math
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(label, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", label,
                                 " - " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


def refuses(label, fn):
    try:
        fn()
    except ValueError as exc:
        check(label, True, str(exc)[:60])
    else:
        check(label, False, "no ValueError raised")


def main():
    from emstudio.solvers.openfoam.solid import (SolidCase, SolidResult,
                                                 solid_stl, uv_sphere,
                                                 write_solid)
    from emstudio.ui.solid_convection_dialog import describe_solid, film_note
    from emstudio.wire.thermal import air_properties

    print("EMStudio solid-convection setup gate (offline)")
    r = 0.05
    tris = uv_sphere(r, n_theta=24, n_phi=48)

    # --- geometry arithmetic ----------------------------------------------
    case = SolidCase(triangles=tris, power_w=0.5)
    exact = 4.0 * math.pi * r * r
    check("UV-sphere area within 1% of 4*pi*r^2",
          abs(case.area_m2 - exact) / exact < 0.01,
          "%.6f vs %.6f" % (case.area_m2, exact))
    check("polyhedron area reads LOW, never high (inscribed vertices)",
          case.area_m2 < exact, "%.6f" % case.area_m2)
    check("bounding radius is r", abs(case.bounding_radius - r) < 1e-12)
    check("box half-extent = open_air * bounding radius",
          abs(case.box_half - case.open_air * r) < 1e-12)
    check("centre recovered at the origin",
          max(abs(c) for c in case.centre) < 1e-9, str(case.centre))

    # --- flux and gradient: real watts, real air ---------------------------
    k_air = air_properties(case.t_film_k)[0]
    check("flux = P / A_triangulated",
          abs(case.flux_w_m2 - 0.5 / case.area_m2) < 1e-12)
    check("gradient = flux / k_AIR (the fluid's k, nobody else's)",
          abs(case.gradient - case.flux_w_m2 / k_air) < 1e-9,
          "k_air %.5f" % k_air)
    check("beta is ideal-gas at the film temperature",
          abs(case.beta - 1.0 / case.t_film_k) < 1e-15)

    # --- the sandwich ------------------------------------------------------
    lo, up = case.conduction_nu_bounds(r)
    r_ins, r_cir = case.box_half, case.box_half * math.sqrt(3.0)
    check("lower bound is the CIRCUMSCRIBED shell",
          abs(lo - 2.0 / (1.0 - r / r_cir)) < 1e-12, "%.6f" % lo)
    check("upper bound is the INSCRIBED shell",
          abs(up - 2.0 / (1.0 - r / r_ins)) < 1e-12, "%.6f" % up)
    check("sandwich is ordered and above the textbook 2",
          2.0 < lo < up, "[%.4f, %.4f]" % (lo, up))
    big = SolidCase(triangles=tris, power_w=0.5, open_air=8.0)
    blo, bup = big.conduction_nu_bounds(r)
    check("a bigger box TIGHTENS the sandwich toward 2",
          2.0 < blo < lo and 2.0 < bup < up,
          "[%.4f, %.4f] at open_air 8" % (blo, bup))
    refuses("bounds refuse a sphere outside the box",
            lambda: case.conduction_nu_bounds(case.box_half * 1.1))

    # --- refusals ----------------------------------------------------------
    refuses("no triangles", lambda: SolidCase(triangles=[]))
    refuses("zero power", lambda: SolidCase(triangles=tris, power_w=0.0))
    refuses("negative power (a heat sink is not this model)",
            lambda: SolidCase(triangles=tris, power_w=-1.0))
    refuses("open_air below 1.5 is an enclosure study",
            lambda: SolidCase(triangles=tris, open_air=1.2))
    refuses("degenerate zero-area triangulation",
            lambda: SolidCase(triangles=[((0, 0, 0), (0, 0, 0), (0, 0, 0))]))
    refuses("a write_interval that does not divide iterations (the final "
            "state would never be written)",
            lambda: SolidCase(triangles=tris, write_interval=5000))
    stray = tempfile.mkdtemp(prefix="emstudio-sgate-")
    try:
        refuses("write_solid refuses to invent a default geometry",
                lambda: write_solid(stray))
    finally:
        shutil.rmtree(stray, ignore_errors=True)

    # --- the written case --------------------------------------------------
    wd = tempfile.mkdtemp(prefix="emstudio-solidgate-")
    try:
        write_solid(wd, case)
        stl = os.path.join(wd, "constant", "triSurface", "solid.stl")
        with open(stl) as fh:
            stl_text = fh.read()
        check("STL written with every facet",
              stl_text.count("facet normal") == len(tris),
              "%d facets" % stl_text.count("facet normal"))

        with open(os.path.join(wd, "0", "T")) as fh:
            t_text = fh.read()
        check("solid patch is a PURE prescribed gradient that writes values",
              "mixed" in t_text and "valueFraction uniform 0" in t_text
              and ("refGradient uniform %.10g" % case.gradient) in t_text)
        walls_block = t_text.split("walls", 1)[1][:120]
        check("walls are ambient fixedValue",
              "fixedValue" in walls_block
              and ("%.10g" % case.t_amb) in walls_block,
              walls_block.strip()[:50])

        with open(os.path.join(wd, "constant", "g")) as fh:
            g_text = fh.read()
        check("gravity acts along -z (the DOCUMENT's down)",
              "(0 0 -9.81)" in g_text, g_text.splitlines()[-1].strip())

        with open(os.path.join(wd, "system", "snappyHexMeshDict")) as fh:
            snappy = fh.read()
        loc_line = [ln for ln in snappy.splitlines()
                    if "locationInMesh" in ln][0]
        nums = loc_line.split("(")[1].split(")")[0].split()
        loc = tuple(float(x) for x in nums)
        loc_r = math.sqrt(sum((a - b) ** 2
                              for a, b in zip(loc, case.centre)))
        check("locationInMesh is in the FLUID (outside the solid, in the box)",
              case.bounding_radius < loc_r
              and all(abs(a - b) < case.box_half
                      for a, b in zip(loc, case.centre)),
              "r %.4f, solid %.4f, half %.4f"
              % (loc_r, case.bounding_radius, case.box_half))

        with open(os.path.join(wd, "system", "controlDict")) as fh:
            check("application is the buoyant Boussinesq steady solver",
                  "buoyantBoussinesqSimpleFoam" in fh.read())

        # conduction variant writes g = 0 exactly
        wd2 = os.path.join(wd, "cond")
        write_solid(wd2, SolidCase(triangles=tris, power_w=0.5, gravity=0.0))
        with open(os.path.join(wd2, "constant", "g")) as fh:
            check("gravity 0 writes an exact zero vector (the anchor case)",
                  "(0 0 -0)" in fh.read())
    finally:
        shutil.rmtree(wd, ignore_errors=True)

    # --- results object ----------------------------------------------------
    res = SolidResult(t_mean=320.0, t_min=318.0, t_max=324.0, t_amb=300.0,
                      flux_w_m2=100.0, k_fluid=k_air, nu_fluid=1.7e-5,
                      alpha_fluid=2.4e-5, beta=1.0 / 315.0, gravity=9.81,
                      faces=100)
    check("h = flux / dT", abs(res.h_w_m2k - 100.0 / 20.0) < 1e-12)
    check("Nu on a caller-chosen length", abs(
        res.nu_for(0.1) - (100.0 / 20.0) * 0.1 / k_air) < 1e-9)
    check("Ra uses the solved dT",
          abs(res.ra_for(0.1) - 9.81 * (1 / 315.0) * 20.0 * 1e-3
              / (1.7e-5 * 2.4e-5)) / res.ra_for(0.1) < 1e-9)
    refuses("Nu refuses a non-positive length", lambda: res.nu_for(0.0))

    # --- dialog prose ------------------------------------------------------
    prose = describe_solid(tris, "Coil")
    check("describe_solid names the geometry and the open-air honesty",
          "Coil" in prose and str(len(tris)) in prose
          and "no enclosure" in prose.lower(), prose[:70])
    check("describe_solid states the physics scope (laminar, no radiation)",
          "laminar" in prose.lower() and "radiation" in prose.lower()
          and "film" in prose.lower(),
          "the dialog is the surface the user reads; the scope lives there")
    check("film note is silent near the assumed film",
          film_note(320.0, 300.0) == "")
    check("film note fires when the solved film strays",
          "re-run" in film_note(420.0, 300.0))

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("SOLID-SETUP GATE PASSED")
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
        raise SystemExit("solid-setup validation failed")
    sys.exit(0)
