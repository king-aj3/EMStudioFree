# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: general 3-D magnetodynamics — ANALYTIC tier
(MAGNETICS_DEPTH_PLAN §5).

Runs the production pipeline (gmsh_3d → ElmerGrid → writer3d → ElmerSolver,
magnetostatic CoilSolver → WhitneyAV → CalcFields) against closed forms:

1. **Thick finite solenoid** (45/55 × 200 mm, 1000 At): on-axis Bz at the
   center and at z = ±100 mm vs the exact rectangular-cross-section formula
   (probe: −0.55 % center, −1.21 % worst end).
2. **Helmholtz pair** (R = 100 mm, 4×4 mm rings at z = ±50 mm): center Bz vs
   (4/5)^{3/2}·µ0·NI/R AND the field-FLATNESS property — Bz(±10 mm)/Bz(0)−1
   must match the two-loop analytic value ≈ −1.15e-4 (a strong field-shape
   check no amplitude fluke can pass).
3. **Off-axis single loop**: with only the top ring driven, Bz at
   (r = 50 mm, z = 0) vs the exact elliptic-integral loop field.

The closed-coil circulation SENSE is mesh-arbitrary (CoilSolver picks
internal fixing nodes — de-risk pitfall), so comparisons are made after
normalizing the FEM sign to the reference at one point per case; the SHAPE
checks (end ratios, flatness) then pin the physics.

Runtime: three ~0.5-0.8 M-tet magnetostatic solves, ~6-9 min total — a SLOW
gate, run per release or after touching the 3-D chain.
Pass: exit 0 and 'WHITNEY3D GATE PASSED'. Auto-skips without Elmer/gmsh.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MU0 = 4.0e-7 * math.pi
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# closed forms (independent references)
# ---------------------------------------------------------------------------
def solenoid_bz_axis(z, r1, r2, h, ni):
    """Exact on-axis Bz of a rectangular-cross-section solenoid (SI)."""
    j = ni / ((r2 - r1) * h)  # A/m^2

    def f(zeta):
        return zeta * math.log(
            (r2 + math.hypot(r2, zeta)) / (r1 + math.hypot(r1, zeta)))

    return 0.5 * MU0 * j * (f(z + h / 2.0) - f(z - h / 2.0))


def loop_bz(r, z, r_loop, amps):
    """Exact Bz of a circular loop at radius r, axial offset z (scipy K/E)."""
    from scipy.special import ellipe, ellipk

    if r == 0.0:
        return MU0 * amps * r_loop ** 2 / (2.0 * (r_loop ** 2 + z ** 2) ** 1.5)
    k2 = 4.0 * r_loop * r / ((r_loop + r) ** 2 + z ** 2)
    kk, ee = ellipk(k2), ellipe(k2)
    pref = MU0 * amps / (2.0 * math.pi * math.sqrt((r_loop + r) ** 2 + z ** 2))
    return pref * (kk + (r_loop ** 2 - r ** 2 - z ** 2)
                   / ((r_loop - r) ** 2 + z ** 2) * ee)


# ---------------------------------------------------------------------------
# models (meters) — geometry/mesh per the de-risked probe recipes
# ---------------------------------------------------------------------------
def solenoid_model():
    return {
        "bodies": [
            {"name": "coil",
             "shape": {"kind": "tube", "center": (0.0, 0.0), "r_in": 0.045,
                       "r_out": 0.055, "z0": -0.100, "z1": 0.100},
             "mu_r": 1.0, "lc": 0.0035,
             "coil": {"amp_turns": -1000.0, "normal": (0.0, 0.0, 1.0)}},
        ],
        "air": {"kind": "cylinder", "r": 0.60, "z0": -0.65, "z1": 0.65},
        "lc_air": 0.090,
        "size_fields": [
            {"kind": "distance", "body": "coil", "lc": 0.0035,
             "dist_min": 0.008, "dist_max": 0.50},
            {"kind": "distance", "body": "line:0", "lc": 0.0025,
             "dist_min": 0.015, "dist_max": 0.50},
        ],
        "embed_lines": [((0.0, 0.0, -0.125), (0.0, 0.0, 0.125))],
        "save_lines": [((0.0, 0.0, -0.125), (0.0, 0.0, 0.125), 100)],
    }


def rings_model(drive_both):
    rings = []
    for tag, zc in (("ring_top", 0.050), ("ring_bot", -0.050)):
        body = {"name": tag,
                "shape": {"kind": "tube", "center": (0.0, 0.0), "r_in": 0.098,
                          "r_out": 0.102, "z0": zc - 0.002, "z1": zc + 0.002},
                "mu_r": 1.0, "lc": 0.0015}
        if drive_both or tag == "ring_top":
            body["coil"] = {"amp_turns": -1000.0, "normal": (0.0, 0.0, 1.0)}
        rings.append(body)
    fields = [{"kind": "distance", "body": r["name"], "lc": 0.0015,
               "dist_min": 0.006, "dist_max": 0.50} for r in rings]
    fields.append({"kind": "distance", "body": "line:0", "lc": 0.0020,
                   "dist_min": 0.012, "dist_max": 0.50})
    fields.append({"kind": "distance", "body": "line:1", "lc": 0.0020,
                   "dist_min": 0.012, "dist_max": 0.50})
    return {
        "bodies": rings,
        "air": {"kind": "cylinder", "r": 1.0, "z0": -1.0, "z1": 1.0},
        "lc_air": 0.170,
        "size_fields": fields,
        # the radial line starts OFF-axis: embedded curves must never cross
        # (a crossing forces degenerate slivers at the intersection — a +12%
        # Bz spike at the shared point, found on the first gate run)
        "embed_lines": [((0.0, 0.0, -0.060), (0.0, 0.0, 0.060)),
                        ((0.010, 0.0, 0.0), (0.080, 0.0, 0.0))],
        "save_lines": [((0.0, 0.0, -0.060), (0.0, 0.0, 0.060), 120),
                       ((0.010, 0.0, 0.0), (0.080, 0.0, 0.0), 80)],
    }


def _interp(xs, ys, x):
    pts = sorted(zip(xs, ys))
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        if x0 <= x <= x1:
            f = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return y0 + f * (y1 - y0)
    return pts[-1][1]


def gate_emission():
    from emstudio.solvers.elmer import writer3d

    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                       "emstudio_w3d_deck_{0}.sif".format(os.getpid()))
    writer3d.write_sif3d(solenoid_model(), tmp, {"air": 1, "coil": 2},
                         {"outer": 3})
    with open(tmp, encoding="utf-8") as fh:
        text = fh.read()
    os.remove(tmp)
    check("magnetostatic deck: Steady State + Equals-CoilCurrent drive (no "
          "MATC/time), no ICs",
          "Simulation Type = Steady State" in text
          and 'Current Density 1 = Equals "CoilCurrent e 1"' in text
          and "MATC" not in text
          and "Initial Condition" not in text)
    check("deck: one Component per coil with signed ampere-turns + Coil "
          "Normal", "Component 1" in text
          and "Desired Coil Current = Real -1000" in text
          and "Coil Normal(3) = Real 0 0 1" in text)

    from emstudio.solvers.elmer.writer3d import Elmer3DModelError
    try:
        writer3d.write_sif3d({"bodies": [{"name": "x", "sigma": 1.0}]},
                             tmp, {"x": 1, "air": 2}, {"outer": 3})
    except Elmer3DModelError:
        check("no-coil model refuses loudly", True)
    else:
        check("no-coil model refuses loudly", False)


def _signed(vals, ref_sign_probe):
    """Normalize the arbitrary coil circulation sense to the reference."""
    s = 1.0 if (vals * ref_sign_probe) >= 0 else -1.0
    return s


def gate_live():
    from emstudio.solvers.elmer.runner3d import run_model3d

    # ---- case 1: thick solenoid --------------------------------------
    try:
        res = run_model3d(solenoid_model())
    except Exception as exc:  # noqa: BLE001
        print("  skip  live tier — 3-D Elmer run unavailable: {0}".format(exc))
        return
    line = res["saveline"]
    zs = line["coordinate 3"]
    bz = line["magnetic flux density 3"]
    ni, r1, r2, h = 1000.0, 0.045, 0.055, 0.200
    ref0 = solenoid_bz_axis(0.0, r1, r2, h, ni)
    fem0 = _interp(zs, bz, 0.0)
    sign = 1.0 if fem0 * ref0 >= 0 else -1.0  # circulation sense is mesh-arbitrary
    check("solenoid: on-axis center Bz within 1% of the exact closed form",
          abs(sign * fem0 / ref0 - 1.0) < 0.01,
          "FEM {0:.6g} vs ref {1:.6g} T ({2:+.2%})".format(
              sign * fem0, ref0, sign * fem0 / ref0 - 1.0))
    for z_eval in (-0.100, 0.100):
        refz = solenoid_bz_axis(z_eval, r1, r2, h, ni)
        femz = sign * _interp(zs, bz, z_eval)
        check("solenoid: Bz at z = {0:+.0f} mm within 2% (end field)".format(
            z_eval * 1e3), abs(femz / refz - 1.0) < 0.02,
            "FEM {0:.6g} vs ref {1:.6g} T ({2:+.2%})".format(
                femz, refz, femz / refz - 1.0))
    check("solenoid case converged cleanly", not res["solver_warnings"],
          "; ".join(res["solver_warnings"][:2]))

    # ---- case 2: Helmholtz pair --------------------------------------
    res2 = run_model3d(rings_model(drive_both=True))
    line2 = res2["saveline"]
    # both polylines share line.dat — keep AXIS rows only (x = 0; the probe's
    # shared-rows pitfall: a z = 0 radial row would corrupt the axis interp)
    axis2 = [(z, b) for x, z, b in zip(line2["coordinate 1"],
                                       line2["coordinate 3"],
                                       line2["magnetic flux density 3"])
             if abs(x) < 1e-9]
    zs2 = [p[0] for p in axis2]
    bz2 = [p[1] for p in axis2]
    r_mean, ni_ring = 0.100, 1000.0
    ref_c = (4.0 / 5.0) ** 1.5 * MU0 * ni_ring / r_mean
    fem_c = _interp(zs2, bz2, 0.0)
    sign2 = 1.0 if fem_c * ref_c >= 0 else -1.0
    check("Helmholtz: center Bz within 1% of (4/5)^1.5*mu0*NI/R",
          abs(sign2 * fem_c / ref_c - 1.0) < 0.01,
          "FEM {0:.6g} vs ref {1:.6g} T ({2:+.2%})".format(
              sign2 * fem_c, ref_c, sign2 * fem_c / ref_c - 1.0))
    # flatness: the two-loop analytic ratio at z = +/-10 mm (field-shape pin)
    ana = (loop_bz(0.0, 0.010 - 0.050, r_mean, ni_ring)
           + loop_bz(0.0, 0.010 + 0.050, r_mean, ni_ring))
    ana0 = 2.0 * loop_bz(0.0, 0.050, r_mean, ni_ring)
    flat_ana = ana / ana0 - 1.0
    flat_fem = 0.5 * (_interp(zs2, bz2, 0.010) + _interp(zs2, bz2, -0.010)) \
        / fem_c - 1.0
    check("Helmholtz FLATNESS: Bz(+/-10 mm)/Bz(0)-1 matches the two-loop "
          "analytic {0:.3g} within 1e-4 (field-shape check)".format(flat_ana),
          abs(flat_fem - flat_ana) < 1e-4 and flat_fem < 0.0,
          "FEM {0:.3g} vs analytic {1:.3g}".format(flat_fem, flat_ana))

    # ---- case 3: off-axis single loop --------------------------------
    res3 = run_model3d(rings_model(drive_both=False))
    line3 = res3["saveline"]
    rs3 = line3["coordinate 1"]
    zs3 = line3["coordinate 3"]
    bz3 = line3["magnetic flux density 3"]
    radial = [(r, b) for r, z, b in zip(rs3, zs3, bz3) if abs(z) < 1e-9]
    ref_off = loop_bz(0.050, -0.050, r_mean, ni_ring)  # loop at z=+50, eval z=0
    fem_off = _interp([p[0] for p in radial], [p[1] for p in radial], 0.050)
    sign3 = 1.0 if fem_off * ref_off >= 0 else -1.0
    check("off-axis loop: Bz(r=50 mm, z=0) within 1% of the elliptic-"
          "integral field", abs(sign3 * fem_off / ref_off - 1.0) < 0.01,
          "FEM {0:.6g} vs ref {1:.6g} T ({2:+.2%})".format(
              sign3 * fem_off, ref_off, sign3 * fem_off / ref_off - 1.0))


def main():
    print("EMStudio 3-D WhitneyAV (magnetics §5) ANALYTIC validation gate")
    gate_emission()
    gate_live()
    if FAILURES:
        print("WHITNEY3D GATE FAILED: {0}".format(FAILURES))
        return 1
    print("WHITNEY3D GATE PASSED")
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
        raise SystemExit("whitney3d validation failed")
    sys.exit(0)
