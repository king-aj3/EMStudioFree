# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: kOmegaSST natural convection vs Betts & Bokhari (measured).

Pass: exit 0 and 'OPENFOAM RAS CAVITY GATE PASSED'.

**The anchor.** Betts & Bokhari (2000), "Experiments on turbulent natural
convection in an enclosed tall cavity", IJHFF 21(6) — a 0.076 m x 2.18 m
differentially heated air cavity at Ra = 8.6e5 (the lower, 19.6 K case).
The digitised measured profiles ship INSIDE the ESI v2512 tree beside its
own ``buoyantCavity`` tutorial, so the case, the model and the experimental
comparison data all come from the solver vendor — this gate reads them from
the installed tree rather than vendoring a copy.

**What is validated: T2 of docs/OPENFOAM_TURBULENCE_PLAN.md** — the RAS
plumbing EMStudio's cavity writer emits (kOmegaSST, wall functions on
k/omega/nut/alphat, wallDist) — through the product's own writer and runner,
never a hand-edited case. 2-D at the midplane, against the experiment's z=0
data: B&B chose the 0.52 m depth to make the midplane near-2-D, which is why
2-D RANS is the standard way this benchmark is solved.

**Measured 2026-08-23 (35x150 cells, the tutorial's own in-plane resolution;
converged at iteration 8071 of a 30000 cap):**

    temperature, worst height:   RMS 0.92 K on a 19.6 K span  = 4.8 %
    vertical velocity, worst:    RMS 0.024 m/s on 0.28 m/s    = 8.7 %

Tolerances below are those measurements with ~1.4x headroom for run-to-run
and platform variation — quoted FROM the comparison, not chosen.

**The mutation that proves the model matters (dev-run 2026-08-23, same case
with ``turbulence=""``):** the laminar solve at this Ra NEVER converges
(30000 iterations, residuals still moving — the flow is turbulent and a
steady laminar solve hunts) and lands at worst T 17.2 % / worst V 50.6 % of
span — every number fails this gate's windows several times over. That is
the measured gap between "laminar-only" and "validated RAS".

⚠ Velocity scale systematic, stated: the writer derives nu/alpha from the
requested (Ra, Pr) with its fixed BETA = 3.3e-3, while real 293 K air has
beta ~= 3.41e-3 — the dimensional velocity scale differs by ~2 %. Inside
the window, and the temperature comparison is scale-exact (same dT, same
absolute wall temperatures as the experiment).
"""
import math
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

# The experiment, in its own numbers (tutorial README + data headers).
W_M, H_M = 0.076, 2.18
T_HOT, T_COLD = 307.75, 288.15         # 34.6 / 15.0 degC — the tutorial's own
RA = 8.6e5                             # the data files' own header
NX, NY = 35, 150                       # the tutorial's in-plane resolution
HEIGHTS = (10, 30, 50, 70, 90)         # y/H percentages with measured data

#: Measured worst 4.8 % (T) and 8.7 % (V) of span — see module docstring.
TOL_T_SPAN = 0.07
TOL_V_SPAN = 0.12

ITER_CAP = 30000                       # converged at 8071 when measured


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _expt_dir(info):
    root = os.path.dirname(os.path.dirname(info.bashrc))
    return os.path.join(root, "tutorials", "heatTransfer",
                        "buoyantSimpleFoam", "buoyantCavity", "validation",
                        "exptData")


def _read_expt(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split()
            rows.append((float(p[0]), float(p[1])))
    return rows


def _read_vector_field(path):
    """U's internalField — the scalar reader in parser.py cannot parse it."""
    with open(path) as fh:
        txt = fh.read()
    m = re.search(r"internalField\s+nonuniform\s+List<vector>\s*\n?\s*(\d+)"
                  r"\s*\n?\s*\((.*?)^\)", txt, re.S | re.M)
    if not m:
        raise ValueError("no vector internalField in " + path)
    vecs = re.findall(r"\(([^)]+)\)", m.group(2))
    if len(vecs) != int(m.group(1)):
        raise ValueError("vector count mismatch in " + path)
    return [tuple(float(x) for x in v.split()) for v in vecs]


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            f = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] * (1 - f) + ys[i + 1] * f


def _rms_against(expt, xs, prof, conv, mirror):
    """RMS of (solved - measured). ``mirror`` maps the data's cold-wall-origin
    x onto the writer's hot-wall-origin axis; passing False exists ONLY for
    the in-gate orientation control."""
    errs = []
    for x_mm, val in expt:
        x = (W_M - x_mm * 1e-3) if mirror else (x_mm * 1e-3)
        errs.append(conv(_interp(x, xs, prof)) - val)
    return math.sqrt(sum(e * e for e in errs) / len(errs))


def main():
    import shutil
    import tempfile

    from emstudio.setup import openfoam as ofsetup
    from emstudio.solvers.openfoam import runner as ofr
    from emstudio.solvers.openfoam.parser import read_internal_field
    from emstudio.solvers.openfoam.writer import CavityCase, write_cavity

    print("EMStudio RAS cavity gate (kOmegaSST vs Betts & Bokhari, "
          "through the product's own writer+runner)")

    info = ofsetup.find_openfoam()
    check("a usable ESI OpenFOAM is present", info.found and info.usable,
          info.describe() or "nothing found")
    if FAILURES:
        return 1
    expt_dir = _expt_dir(info)
    check("the install ships the buoyantCavity experimental data",
          os.path.isdir(expt_dir),
          expt_dir if os.path.isdir(expt_dir) else
          "%s missing — an incomplete (rc?) tree; discovery should have "
          "preferred a COMPLETE install" % expt_dir)
    if FAILURES:
        return 1

    case = CavityCase(ra=RA, pr=0.71, cells=NX, cells_y=NY, width=W_M,
                      height=H_M, t_hot=T_HOT, t_cold=T_COLD,
                      iterations=ITER_CAP, turbulence="kOmegaSST")
    check("Ra round trip from the WRITTEN properties",
          abs(case.ra_written / RA - 1) < 1e-9,
          "%.6g" % case.ra_written)

    base = tempfile.mkdtemp(prefix="emstudio-ras-cavity-")
    try:
        write_cavity(base, case)
        # The product's own output, read back: the case must genuinely be RAS.
        with open(os.path.join(base, "constant",
                               "turbulenceProperties")) as fh:
            tp = fh.read()
        check("written case declares RAS kOmegaSST",
              "RAS" in tp and "kOmegaSST" in tp)
        for f in ("k", "omega", "nut"):
            check("written case carries 0/%s" % f,
                  os.path.isfile(os.path.join(base, "0", f)))

        rep = ofr.run_chain(base, info=info, timeout=3600)
        check("the chain completes", rep["ok"],
              rep.get("failed_at", "") or "")
        if not rep["ok"]:
            return 1
        solve = [s for s in rep["steps"] if s["step"].startswith("buoyant")]
        check("residualControl actually fired (steady RAS converged)",
              bool(solve and solve[0]["converged"]),
              "" if solve and solve[0]["converged"] else
              "residuals still falling after %d iterations" % ITER_CAP)

        td = ofr.latest_time_dir(base)
        T = read_internal_field(os.path.join(base, td, "T"))
        U = _read_vector_field(os.path.join(base, td, "U"))
        check("field sizes match the mesh",
              len(T) == NX * NY and len(U) == NX * NY,
              "T %d, U %d, expected %d" % (len(T), len(U), NX * NY))
        if FAILURES:
            return 1

        xs = [(i + 0.5) * W_M / NX for i in range(NX)]
        worst_t = worst_v = 0.0
        mirror_margin = []
        for hh in HEIGHTS:
            row = min(NY - 1, max(0, int(round(hh / 100.0 * NY - 0.5))))
            tprof = [T[row * NX + i] for i in range(NX)]
            vprof = [U[row * NX + i][1] for i in range(NX)]
            for kind, prof, conv in (("mt", tprof, lambda v: v - 273.15),
                                     ("mv", vprof, lambda v: v)):
                expt = _read_expt(os.path.join(
                    expt_dir, "%s_z0_%d_lo.dat" % (kind, hh)))
                rms = _rms_against(expt, xs, prof, conv, mirror=True)
                span = (max(v for _, v in expt) - min(v for _, v in expt))
                frac = rms / span
                if kind == "mt":
                    worst_t = max(worst_t, frac)
                    # Orientation control (see below) on the temperature
                    # profiles — they are monotone wall-to-wall, so a flipped
                    # axis is maximally wrong and the margin is huge.
                    mirror_margin.append(
                        _rms_against(expt, xs, prof, conv, mirror=False) / rms)
                else:
                    worst_v = max(worst_v, frac)
                print("    %s y/H=0.%02d  rms %.4f / span %.3f = %.1f %%"
                      % (kind, hh, rms, span, 100 * frac))

        check("every T profile within %.0f %% of span (measured worst 4.8 %%)"
              % (100 * TOL_T_SPAN), worst_t < TOL_T_SPAN,
              "worst %.1f %%" % (100 * worst_t))
        check("every V profile within %.0f %% of span (measured worst 8.7 %%)"
              % (100 * TOL_V_SPAN), worst_v < TOL_V_SPAN,
              "worst %.1f %%" % (100 * worst_v))
        # ⛳ In-gate negative control: the experiment's x runs from the COLD
        # wall and the writer's from the HOT wall, so the comparison contains
        # a mirror. Feeding the data UN-mirrored must be much worse — if it
        # ever is not, the comparison machinery (not the physics) has broken,
        # which is exactly the class of silent bug a green gate hides.
        check("orientation control: un-mirrored comparison is >= 2x worse",
              min(mirror_margin) >= 2.0,
              "min ratio %.2f" % min(mirror_margin))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if FAILURES:
        print("OPENFOAM RAS CAVITY GATE FAILED: {0}".format(FAILURES))
        return 1
    print("OPENFOAM RAS CAVITY GATE PASSED")
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
        raise SystemExit("openfoam ras cavity validation failed")
    sys.exit(0)
