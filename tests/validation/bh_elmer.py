# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: nonlinear B-H materials in the Elmer magnetics chain
(MAGNETICS_DEPTH_PLAN §4).

The material's B-H table (columns **B [T] then H [A/m]**) replaces
Relative Permeability. Exact in the new **Static (DC)** analysis
(``MagnetoDynamics2D``, scalar Potential); in the **Harmonic (AC)** chain it
is Elmer's amplitude-adaptive secant reluctivity ν = H(|B|)/|B| at the local
PEAK phasor |B| — an effective-permeability approximation (no waveform
distortion), which at σ = 0 and in-phase drive must equal the static
nonlinear solve (de-risk probe: 9 digits). Tiers:

* **Deck emission** (pure ``write_sif``): the H-B table + the real nonlinear
  block (a single nonlinear iteration SILENTLY DISABLES the curve — exit 0,
  linear initial-µ, +93 % λ error at saturation); static solver/BC/source
  keywords; the table guards (a column-swapped table converges FASTER and
  passes a naive B-max check at knee drive — guarded at the table level);
  no-B-H decks byte-stable.

* **Live static solve** (Elmer v26.2): the de-risked gapped pot-core
  (Fröhlich iron, 2 mm gap) at I = 1/6/15 A vs a nonlinear ladder-MEC
  reference (window-leakage permeance ~ gap reluctance — the plain series
  reluctance loop is ~2× wrong on this geometry; ladder derived
  independently of Elmer, landing −2…−5 % signed, fringing-limited) plus
  frozen FEM regression pins; L(I) droop; the linear-µ control ~92 % ABOVE
  the saturated λ (also catches swapped tables, which land above it).

* **Live harmonic solve**: harmonic B-H at σ = 0 == static B-H (machine
  class); saturation droop vs the linear harmonic run; and the exactness
  pin — a straight-line B-H table == plain Relative Permeability.

Pass: exit 0 and 'BH GATE PASSED'. Deck tier runs anywhere; live tiers
auto-skip if ElmerSolver is absent.
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
# the shared de-risked case: Fröhlich iron B(H) = H/(a + b·H),
# initial µr = 1000, B_sat = 2 T; gapped pot-core, N = 200 turns
# ---------------------------------------------------------------------------
FR_A, FR_B = 795.7747, 0.5
TURNS = 200
DRIVES_A = (1.0, 6.0, 15.0)

#: frozen FEM regression pins (probe 2026-07-16, this exact mesh recipe):
#: flux linkage λ [Wb-turns] per drive — L(I) droop 15.3 → 14.0 → 8.0 mH
LAMBDA_PINS = {1.0: 0.015311, 6.0: 0.083852, 15.0: 0.120319}


def froehlich_table(n=40, b_max=1.9487):
    """B-H table sampled UNIFORMLY IN B (uniform-in-H under-resolves the
    knee — 42 % λ error measured on this pot-core)."""
    pts = [(0.0, 0.0)]
    for i in range(1, n):
        b = b_max * i / (n - 1)
        pts.append((b, FR_A * b / (1.0 - FR_B * b)))
    return pts


def linear_table(mu_r=1000.0, n=40, b_max=1.95):
    """A straight-line 'nonlinear' table — must reproduce Relative
    Permeability exactly (the linear-as-table pin)."""
    pts = [(0.0, 0.0)]
    for i in range(1, n):
        b = b_max * i / (n - 1)
        pts.append((b, b / (MU0 * mu_r)))
    return pts


def potcore_model(current_a, bh=None, mu_r=1000.0, static=True):
    """The de-risked pot-core as a production axi-model dict (mm).

    The 2 mm gap is an explicit air body (fine lc) exactly as probed; the
    lc values are the probe's — the regression pins assume this mesh.
    """
    def iron(name, r0, r1, z0, z1, lc):
        b = {"name": name, "r0": r0, "r1": r1, "z0": z0, "z1": z1,
             "sigma": 0.0, "mu_r": mu_r, "lc": lc}
        if bh is not None:
            b["bh"] = bh
        return b

    model = {
        "bodies": [
            iron("plate_bot", 0.0, 25.0, -8.0, 0.0, 2.0),
            iron("post", 0.0, 10.0, 0.0, 38.0, 1.5),
            {"name": "gap", "r0": 0.0, "r1": 10.0, "z0": 38.0, "z1": 40.0,
             "sigma": 0.0, "mu_r": 1.0, "lc": 0.5},
            iron("plate_top", 0.0, 25.0, 40.0, 48.0, 2.0),
            iron("shell", 20.0, 25.0, 0.0, 40.0, 1.5),
            {"name": "coil", "r0": 12.0, "r1": 18.0, "z0": 5.0, "z1": 35.0,
             "sigma": 0.0, "mu_r": 1.0, "lc": 1.5,
             "coil": {"turns": TURNS, "current_a": float(current_a),
                      "phase_deg": 0.0, "reversed": False}},
        ],
        "air": (60.0, -30.0, 70.0),
        "lc_air": 6.0,
    }
    if static:
        model["static"] = True
    return model


# ---------------------------------------------------------------------------
# independent reference: nonlinear 1-D ladder MEC along the post axis.
# dphi/dz = -p_l*psi (window leakage), dpsi/dz = f'(z) - H_post - H_shell,
# psi(0) = -plate_drop(phi(0)); above the post top the center column is the
# fringed air gap. Derived independently of Elmer (de-risk math leg); the
# plain series loop (p_l = 0) is ~2x low on this geometry.
# ---------------------------------------------------------------------------
R_POST, R_SHELL_IN, R_SHELL_MID = 0.010, 0.020, 0.0225
T_PLATE, Z_GAP, L_GAP = 0.008, 0.038, 0.002
Z_C0, Z_C1 = 0.005, 0.035
R_C0, R_C1 = 0.012, 0.018
H_COIL = Z_C1 - Z_C0
A_POST = math.pi * R_POST ** 2
A_SHELL = math.pi * (0.025 ** 2 - R_SHELL_IN ** 2)
P_LEAK = MU0 * 2.0 * math.pi / math.log(R_SHELL_IN / R_POST)


def _h_of_b(b, mu_r=None):
    if mu_r:
        return b / (MU0 * mu_r)
    b = min(abs(b), 1.999)
    return FR_A * b / (1.0 - FR_B * b)


def _plate_drop(phi, mu_r=None):
    import numpy as np

    rr = np.linspace(R_POST, R_SHELL_MID, 120)
    hh = np.array([_h_of_b(phi / (2 * math.pi * r * T_PLATE), mu_r) for r in rr])
    return float(np.trapz(hh, rr))


def ladder_mec(amps, fringe=0.001, mu_r=None):
    """Returns λ [Wb-turns] from the nonlinear ladder (scipy IVP + brentq)."""
    import numpy as np
    from scipy.integrate import solve_ivp
    from scipy.optimize import brentq

    ni = TURNS * amps
    a_gap = math.pi * (R_POST + fringe) ** 2
    z_top = Z_GAP + L_GAP

    def rhs(z, y):
        phi, psi = y
        if z > Z_GAP:
            h_center = (phi / a_gap) / MU0
        else:
            h_center = _h_of_b(phi / A_POST, mu_r)
        fprime = ni / H_COIL if Z_C0 <= z <= Z_C1 else 0.0
        return [-P_LEAK * psi, fprime - h_center - _h_of_b(phi / A_SHELL, mu_r)]

    def shoot(phi0):
        sol = solve_ivp(rhs, (0.0, z_top), [phi0, -_plate_drop(phi0, mu_r)],
                        max_step=2e-4, rtol=1e-10, atol=1e-14,
                        dense_output=True)
        return sol, sol.y[1, -1] - _plate_drop(sol.y[0, -1], mu_r)

    hi = 1.999 * A_POST if mu_r is None else 40.0 * A_POST
    phi0 = brentq(lambda p: shoot(p)[1], 1e-12, hi, xtol=1e-16, rtol=1e-13)
    sol, _ = shoot(phi0)

    # coil linkage: z-uniform turns link phi(z), plus the window-axial flux
    # inside each turn radius (log H_z profile between post and shell)
    zz = np.linspace(Z_C0, Z_C1, 400)
    phis = sol.sol(zz)[0]
    extra = 0.0
    for z, phi in zip(zz, phis):
        hp = _h_of_b(phi / A_POST, mu_r)
        hs = _h_of_b(phi / A_SHELL, mu_r)
        add = 0.0
        turn_radii = np.linspace(R_C0, R_C1, 13)
        for rt in turn_radii:
            rr = np.linspace(R_POST, rt, 25)
            hz = hp + (hs - hp) * np.log(rr / R_POST) / math.log(R_SHELL_IN / R_POST)
            add += float(np.trapz(MU0 * hz * 2 * math.pi * rr, rr))
        extra += add / len(turn_radii)
    return TURNS / H_COIL * float(np.trapz(phis, zz)) + TURNS * extra / len(zz)


# ---------------------------------------------------------------------------
def _write_deck(model, f_hz=50.0):
    from emstudio.solvers.elmer import writer

    ids = {b["name"]: i + 1 for i, b in enumerate(model["bodies"])}
    ids["air"] = len(model["bodies"]) + 1
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                       "emstudio_bh_deck_{0}.sif".format(os.getpid()))
    writer.write_sif(model, f_hz, tmp, ids,
                     {"router": 1, "ztop": 2, "zbottom": 3})
    with open(tmp, encoding="utf-8") as fh:
        text = fh.read()
    os.remove(tmp)
    return text


def gate_emission():
    from emstudio.solvers.elmer import writer

    BH = froehlich_table()
    plain = _write_deck(potcore_model(6.0, static=False))
    check("no-B-H harmonic deck unchanged (single nonlinear iteration, no "
          "H-B keywords)",
          "MgDyn2DHarmonic" in plain
          and "Nonlinear System Max Iterations = 1\n" in plain
          and "H-B Curve" not in plain)

    hb = _write_deck(potcore_model(6.0, bh=BH, static=False))
    check("harmonic B-H deck: H-B table (Monotone Cubic, B-then-H) + the "
          "REAL nonlinear block (single iteration silently disables the "
          "curve)",
          'H-B Curve = Variable "dummy"' in hb
          and "Real Monotone Cubic" in hb
          and "Nonlinear System Max Iterations = 100" in hb
          and "Nonlinear System Convergence Tolerance = 1.0e-6" in hb
          and "Newton-Raphson Iteration = Logical True" in hb
          and "Frequency = Real 50" in hb)
    iron = hb.split("Material 1")[1].split("End")[0]
    check("B-H iron material has NO Relative Permeability (the curve wins)",
          "Relative Permeability" not in iron and "      0 0" in iron)

    st = _write_deck(potcore_model(6.0, bh=BH, static=True))
    check("static deck: MagnetoDynamics2D + scalar Potential, no Frequency, "
          "plain DC source, single-potential BCs, tol 1e-8",
          '"MagnetoDynamics2D" "MagnetoDynamics2D"' in st
          and 'Variable = "Potential"\n' in st
          and "Frequency" not in st
          and "Current Density Im" not in st
          and "Potential Re" not in st
          and "Nonlinear System Convergence Tolerance = 1.0e-8" in st)
    check("static deck: no eddy/Joule quantities (CalcFields trimmed, "
          "SaveScalars on Potential)",
          "Calculate Joule Heating" not in st
          and "Calculate Magnetic Field Strength = Logical True" in st
          and 'Variable 1 = "Potential"' in st)

    def expect_err(model, tag, needle=""):
        try:
            _write_deck(model)
        except writer.ElmerModelError as exc:
            check("guard: " + tag, needle in str(exc), str(exc)[:70])
        else:
            check("guard: " + tag, False, "deck was written")

    expect_err(potcore_model(6.0, bh=[(h, b) for b, h in BH]),
               "column-swapped table rejected", "not tesla")
    bad = list(BH)
    bad[5] = (bad[6][0], bad[5][1])
    expect_err(potcore_model(6.0, bh=bad), "non-monotone table rejected",
               "strictly increasing")
    coarse = [(0.0, 0.0)] + [(b, FR_A * b / (1 - FR_B * b))
                             for b in (0.97, 1.3, 1.6, 1.8, 1.9487)]
    expect_err(potcore_model(6.0, bh=coarse),
               "uniform-in-H (coarse-in-B) table rejected", "UNIFORMLY IN B")
    thermal_static = potcore_model(6.0, bh=BH, static=True)
    thermal_static["thermal"] = {"t_ext": 293.15, "h": 10.0,
                                 "bodies": {"post": {"k": 20.0}}}
    expect_err(thermal_static, "static + thermal rejected", "thermal chain")


def _lam(res, name="coil"):
    return res.sweep_cases()[0]["coil_lambda"][name]


def gate_live_static():
    from emstudio.solvers.elmer import run_model

    BH = froehlich_table()
    try:
        runs = {i: run_model(potcore_model(i, bh=BH), [0.0],
                             extract_coupling=False) for i in DRIVES_A}
    except Exception as exc:  # noqa: BLE001
        print("  skip  live static tier — Elmer run unavailable: {0}".format(exc))
        return None
    lams = {i: _lam(runs[i]) for i in DRIVES_A}

    for i in DRIVES_A:
        ref = ladder_mec(i)
        err = lams[i].real / ref - 1.0
        check("static B-H λ({0:g} A) within 7% of the independent ladder MEC "
              "(fringing-limited)".format(i),
              abs(err) < 0.07,
              "FEM {0:.6g} vs MEC {1:.6g} Wb-t ({2:+.2%})".format(
                  lams[i].real, ref, err))
        pin = LAMBDA_PINS[i]
        check("static B-H λ({0:g} A) regression pin".format(i),
              abs(lams[i].real / pin - 1.0) < 0.01,
              "FEM {0:.6g} vs pin {1:.6g} ({2:+.3%})".format(
                  lams[i].real, pin, lams[i].real / pin - 1.0))
        check("static λ({0:g} A) is purely real (DC)".format(i),
              lams[i].imag == 0.0)
        check("static case({0:g} A) converged cleanly".format(i),
              not runs[i].sweep_cases()[0].get("solver_warnings"),
              "; ".join(runs[i].sweep_cases()[0].get("solver_warnings") or []))

    l_of = {i: lams[i].real / i for i in DRIVES_A}
    check("L(I) droop: L(1A) {0:.4g} > L(6A) {1:.4g} > L(15A) {2:.4g} mH".format(
        l_of[1.0] * 1e3, l_of[6.0] * 1e3, l_of[15.0] * 1e3),
        l_of[1.0] > l_of[6.0] > l_of[15.0])

    lin = run_model(potcore_model(15.0, mu_r=1000.0), [0.0],
                    extract_coupling=False)
    ratio = _lam(lin).real / lams[15.0].real
    check("linear µr=1000 control sits ~92% ABOVE saturated λ(15 A) — "
          "saturation active (a swapped table lands above the control)",
          1.75 < ratio < 2.10, "ratio {0:.3f}".format(ratio))
    return lams


def gate_live_harmonic(static_lams):
    from emstudio.solvers.elmer import run_model

    BH = froehlich_table()
    try:
        h_runs = {i: run_model(potcore_model(i, bh=BH, static=False), [50.0],
                               extract_coupling=False) for i in DRIVES_A}
    except Exception as exc:  # noqa: BLE001
        print("  skip  live harmonic tier — Elmer run unavailable: {0}".format(exc))
        return
    for i in DRIVES_A:
        lam_h = _lam(h_runs[i])
        if static_lams:
            rel = abs(lam_h.real / static_lams[i].real - 1.0)
            check("harmonic B-H (σ=0, peak-|B| secant) == static B-H at "
                  "{0:g} A (machine class)".format(i),
                  rel < 1e-6,
                  "harmonic {0:.9g} vs static {1:.9g} ({2:.1e})".format(
                      lam_h.real, static_lams[i].real, rel))

    lin_h = run_model(potcore_model(15.0, mu_r=1000.0, static=False), [50.0],
                      extract_coupling=False)
    droop = _lam(h_runs[15.0]).real / _lam(lin_h).real
    check("harmonic saturation droop at 15 A: λ_BH/λ_linear ≈ 0.52",
          0.48 < droop < 0.56, "{0:.3f}".format(droop))

    # exactness pin: a straight-line B-H table == plain Relative Permeability
    lin_tab = run_model(potcore_model(15.0, bh=linear_table(), static=False),
                        [50.0], extract_coupling=False)
    rel = abs(_lam(lin_tab).real / _lam(lin_h).real - 1.0)
    check("linear-as-table == Relative Permeability (exactness pin)",
          rel < 1e-6, "{0:.1e}".format(rel))


def main():
    print("EMStudio nonlinear B-H (magnetics §4) validation gate")
    gate_emission()
    static_lams = gate_live_static()
    gate_live_harmonic(static_lams)
    if FAILURES:
        print("BH GATE FAILED: {0}".format(FAILURES))
        return 1
    print("BH GATE PASSED")
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
        raise SystemExit("bh validation failed")
    sys.exit(0)
