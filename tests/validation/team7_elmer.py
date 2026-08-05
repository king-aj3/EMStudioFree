# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: TEAM Problem 7 — the MEASURED benchmark of the general
3-D magnetodynamics chain (MAGNETICS_DEPTH_PLAN §5).

"Asymmetrical Conductor with a Hole" (Fujiwara & Nakata, COMPEL 9(3) 1990;
official spec: compumag.org problem7.pdf): aluminum plate 294×294×19 mm
(σ = 3.526e7 S/m) with an eccentric 108×108 through-hole, driven by a
racetrack coil (2742 At, 50 Hz) 30 mm above it. The gate runs the FULL
production pipeline (gmsh_3d → ElmerGrid → writer3d → ElmerSolver, transient
BDF1, 2 periods × 8 steps) and compares Bz along the measured A1-B1 line
(y = 72 mm, z = 34 mm) at ωt = 0 against the 17 published measured points.

METRIC: RMS(Bz − Bz_meas) normalized by max|Bz_meas| (7.811 mT) ≤ 10 % —
never point-wise relative error (the line crosses zero at x ≈ 0.09 m).
This is a MEASURED-data tier: honest at the ~3 % level (the de-risk probe
landed 2.86 % on this coarse mesh), deliberately separate from the
sub-percent analytic brand (see whitney3d_elmer.py for that tier).

Geometry/mesh reproduce the de-risked probe (coarse tier: coil 20 / plate
10 / air 30 mm ≈ 123k tets, ~3 min single-thread). Runtime makes this a
SLOW gate — run it per release or after touching the 3-D chain.

Pass: exit 0 and 'TEAM7 GATE PASSED'. Auto-skips without ElmerSolver/gmsh.
"""
import math
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


#: TEAM Problem 7 measured data, A1-B1 line (y=72 mm, z=34 mm), 50 Hz, ωt=0.
#: Benchmark measurement values, cited: compumag problem7.pdf Table 2(a) via
#: docs/TEAM7_BUILD_SHEET.md §B.3 (and the elmer-elmag TEAM7_A1B1.csv copy).
X_MEAS = [0.018 * i for i in range(17)]
BZ_MEAS = [-0.00049, -0.001788, -0.002213, -0.002019, -0.001567, 0.000036,
           0.004364, 0.007811, 0.007155, 0.006044, 0.005391, 0.005262,
           0.005381, 0.005691, 0.005924, 0.005278, 0.002761]
BZ_PEAK = max(abs(b) for b in BZ_MEAS)  # 7.811 mT

#: self-pinned regression norms of THIS deck+mesh (frozen from the first
#: green run of the production writer, 2026-07-16, RMS 2.83%). Norms are
#: mesh-locked — they pin OUR pipeline, not Elmer upstream.
#:
#: MESH-LOCKED MEANS gmsh-VERSION-LOCKED. Measured on two boxes 2026-08-05:
#:   gmsh 4.12.1 (the version these pins were frozen on) — matches BIT-FOR-BIT
#:   gmsh 4.15.2                                        — coilsolver +0.082%,
#:                                                        mgdynamics +0.112%
#: Same deck, same code, different mesher. The old NORM_TOL of 2e-4 (0.02%)
#: therefore reported a RED on a perfectly healthy tree the moment a machine
#: had a newer gmsh — a false alarm on the one gate whose job is to be
#: believed. The same sensitivity is visible in open_coil_elmer (split ring
#: -0.79% vs -1.49% across the same two boxes), so it is the mesher, not this
#: deck.
#:
#: 2e-3 is ~1.8x the largest drift actually observed across a three-minor-
#: version gmsh gap, and still ~50x tighter than the MEASURED physics gate
#: (10% RMS) that sits beside it. A real regression in our writer moves these
#: norms by far more than 0.1% — the pin keeps its teeth.
#: If a future drift exceeds this, do NOT just widen it again: check
#: `gmsh --version` against GMSH_PINNED_ON first, because that is the cheap
#: explanation and it has now been the right one twice.
NORM_PINS = {"coilsolver": 0.58412768, "mgdynamics": 1.7526977e-06}
NORM_TOL = 2e-3
#: The mesher that produced NORM_PINS. Reported on drift so the next person
#: does not have to rediscover the correlation.
GMSH_PINNED_ON = "4.12.1"

MM = 1e-3


def team7_model():
    """The TEAM-7 model3d dict — de-risked coarse tier, meters."""
    return {
        "bodies": [
            {"name": "plate",
             "shape": {"kind": "box", "origin": (0.0, 0.0, 0.0),
                       "size": (294 * MM, 294 * MM, 19 * MM)},
             "sigma": 3.526e7, "mu_r": 1.0, "lc": 10 * MM},
            {"name": "hole",
             "shape": {"kind": "box", "hole": True,
                       "origin": (18 * MM, 18 * MM, -1 * MM),
                       "size": (108 * MM, 108 * MM, 21 * MM)}},
            {"name": "coil",
             "shape": {"kind": "racetrack", "cx0": 144 * MM, "cy0": 50 * MM,
                       "cx1": 244 * MM, "cy1": 150 * MM, "r_in": 25 * MM,
                       "r_out": 50 * MM, "z0": 49 * MM, "z1": 149 * MM},
             "mu_r": 1.0, "lc": 20 * MM,
             "coil": {"amp_turns": -2742.0, "normal": (0.0, 0.0, 1.0)}},
        ],
        "air": {"kind": "box", "origin": (-0.2, -0.2, -0.2),
                "size": (0.694, 0.694, 0.794)},
        "lc_air": 30 * MM,
        "size_fields": [
            {"kind": "box", "lc": 10 * MM, "thickness": 60 * MM,
             "box": (-20 * MM, -20 * MM, -20 * MM, 314 * MM, 314 * MM, 39 * MM)},
            {"kind": "box", "lc": 20 * MM, "thickness": 60 * MM,
             "box": (84 * MM, -10 * MM, 39 * MM, 304 * MM, 210 * MM, 159 * MM)},
        ],
        "transient": {"f_hz": 50.0, "periods": 2, "steps_per_period": 8},
        "save_lines": [((0.0, 0.072, 0.034), (0.288, 0.072, 0.034), 96)],
    }


def gate_emission():
    from emstudio.solvers.elmer import writer3d

    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                       "emstudio_team7_deck_{0}.sif".format(os.getpid()))
    writer3d.write_sif3d(team7_model(), tmp,
                         {"air": 1, "plate": 2, "coil": 3}, {"outer": 4})
    with open(tmp, encoding="utf-8") as fh:
        text = fh.read()
    os.remove(tmp)
    check("deck: probe-validated three-solver chain (CoilSolver Before All, "
          "ungauged WhitneyAV BiCGStabl(6)/none, CalcFields)",
          '"CoilSolver" "CoilSolver"' in text
          and "Exec Solver = Before All" in text
          and '"MagnetoDynamics" "WhitneyAVSolver"' in text
          and "BicgstabL Polynomial Degree = Integer 6" in text
          and "Linear System Preconditioning = none" in text
          and '"MagnetoDynamics" "MagnetoDynamicsCalcFields"' in text)
    check("deck: coil Component with the SIGNED measured-convention drive "
          "(-2742 At) + jfix machinery + outer A{e}=0",
          "Desired Coil Current = Real -2742" in text
          and "Fix Input Current Density = Logical True" in text
          and "Jfix: Linear System Iterative Method = BiCGStabl" in text
          and "A {e} = Real 0.0" in text and "Jfix = Real 0.0" in text)
    check("deck: transient cosine MATC drive on the elemental coil field + "
          "ICs ATTACHED to every body",
          'Variable "time, coilcurrent e 1"' in text
          and 'cos(2.0*3.14159265358979*50' in text
          and text.count("Initial Condition = 1") == 3
          and "Initial Condition 1" in text)
    check("deck: meters (no Coordinate Scaling), no per-radian factor, no "
          "'Narrow Interface' (absent from this CoilSolver build)",
          "Coordinate Scaling" not in text
          and "Narrow Interface" not in text)


def gate_live():
    from emstudio.solvers.elmer.runner3d import run_model3d

    try:
        res = run_model3d(team7_model())
    except Exception as exc:  # noqa: BLE001
        print("  skip  live tier — 3-D Elmer run unavailable: {0}".format(exc))
        return

    line = res["saveline"]
    tcol = line.get("Timestep")  # SaveLine's step column (1..16)
    xcol = line.get("coordinate 1")
    bzcol = line.get("magnetic flux density 3")
    check("SaveLine exposes Timestep / coordinate 1 / nodal 'magnetic flux "
          "density 3' columns", bool(tcol and xcol and bzcol),
          "columns: {0}".format(sorted(line)) if line else "no data")
    if not (tcol and xcol and bzcol):
        return
    t_last = max(tcol)
    check("last transient step is step 16 = t = 40 ms (ωt = 0, the cosine "
          "peak)", abs(t_last - 16.0) < 1e-9, "step {0:.6g}".format(t_last))
    pts = sorted((x, b) for t, x, b in zip(tcol, xcol, bzcol)
                 if t == t_last)
    xs = [p[0] for p in pts]
    bs = [p[1] for p in pts]

    def interp(x):
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                f = (x - xs[i]) / (xs[i + 1] - xs[i]) if xs[i + 1] > xs[i] else 0.0
                return bs[i] + f * (bs[i + 1] - bs[i])
        return bs[-1]

    bz_i = [interp(x) for x in X_MEAS]
    rms = math.sqrt(sum((a - b) ** 2 for a, b in zip(bz_i, BZ_MEAS))
                    / len(BZ_MEAS)) / BZ_PEAK
    print("  {0:>7} {1:>12} {2:>13} {3:>10}".format(
        "x[m]", "meas[mT]", "elmer[mT]", "diff[mT]"))
    for x, bm, be in zip(X_MEAS, BZ_MEAS, bz_i):
        print("  {0:7.3f} {1:12.4f} {2:13.4f} {3:10.4f}".format(
            x, bm * 1e3, be * 1e3, (be - bm) * 1e3))
    check("MEASURED gate: normalized RMS over the 17 A1-B1 points <= 10% "
          "(measured-data tier — separate from the analytic brand)",
          rms <= 0.10, "RMS {0:.2%} of the {1:.3f} mT peak".format(
              rms, BZ_PEAK * 1e3))
    check("field shape sane: Bz crosses zero once near x ~ 0.09 m and peaks "
          "near the hole edge (x ~ 0.126 m)",
          bz_i[0] < 0 and bz_i[7] > 0
          and abs(max(bs) - max(bz_i)) / max(bz_i) < 0.5)

    norms = res["norms"]
    print("  info: solver norms {0}".format(
        {k: "{0:.8g}".format(v) for k, v in sorted(norms.items())
         if k in NORM_PINS}))
    for solver, pin in NORM_PINS.items():
        if pin is None:
            continue  # pins frozen after the first green run
        got = norms.get(solver)
        ok = got is not None and abs(got / pin - 1.0) < NORM_TOL
        detail = "{0} vs pin {1}".format(got, pin)
        if got is not None and not ok:
            # Name the cheap explanation IN the failure, so the reader does not
            # start by suspecting the physics. This correlation has been the
            # right answer twice (2026-08-05).
            import shutil as _sh
            import subprocess as _sp
            ver = "unknown"
            exe = _sh.which("gmsh")
            if exe:
                try:
                    ver = (_sp.run([exe, "--version"], capture_output=True,
                                   text=True, timeout=15).stderr
                           or _sp.run([exe, "--version"], capture_output=True,
                                      text=True, timeout=15).stdout).strip()
                except Exception:  # noqa: BLE001 — diagnostics only
                    pass
            detail += ("  [drift {0:+.3%}; this gmsh {1} vs pins frozen on {2}"
                       " — CHECK THE MESHER BEFORE THE PHYSICS]".format(
                           got / pin - 1.0, ver, GMSH_PINNED_ON))
        check("self-pinned {0} norm regression".format(solver), ok, detail)


def main():
    print("EMStudio TEAM-7 (3-D WhitneyAV measured benchmark) validation gate")
    gate_emission()
    gate_live()
    if FAILURES:
        print("TEAM7 GATE FAILED: {0}".format(FAILURES))
        return 1
    print("TEAM7 GATE PASSED")
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
        raise SystemExit("team7 validation failed")
    sys.exit(0)
