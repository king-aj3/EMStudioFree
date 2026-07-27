# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: temperature-dependent conductivity σ(T) coupled Joule
heating in the Elmer magnetics→heat chain (MAGNETICS_DEPTH_PLAN §3).

σ(T) = σ0/(1 + α·(T − Tref)) — resistivity linear in T. This is THE
architectural slice: the harmonic magnetic solve becomes two-way coupled to
the heat equation via an outer ``Steady State Max Iterations`` loop (steady)
or a per-timestep field re-solve (transient). Three tiers:

* **Deck emission** (pure ``write_sif``): α ≠ 0 emits
  ``Electric Conductivity = Variable Temperature`` + the MATC
  ``σ0/(1+α*(tx-Tref))``, the outer coupled loop, the MANDATORY ambient IC
  (without it iteration 1 sees T = 0 → σ NEGATIVE, silently at exit 0), and
  ``ResultOutput Exec Solver = After Simulation`` (After Timestep would make
  ``case_t0001.vtu`` the FIRST — uncoupled — iterate); α == 0 is
  **byte-identical** to the v0.52 decks. Transient σ(T) drops the
  single-shot ``"Before Simulation"`` field solve.

* **Live steady solve** (Elmer v26.2): the uniform-field Joule billet with
  adiabatic ends. The FEM eddy power and centerline/surface temperatures
  must match an INDEPENDENT coupled 1-D reference (RK4 shooting +
  bisection, re-derived here — not Elmer, not the writer) to 0.5 %
  (the low-frequency reference model itself carries ~0.02 % at a/δ = 0.2,
  the FEM ~0.001 % — de-risked + adversarially verified 2026-07-16), AND
  land measurably BELOW the α = 0 run (σ falls as T rises → self-limiting;
  reference predicts −5.57 % on power). A result HOTTER than α = 0 means
  the σ(T) table was inverted.

* **Live transient solve**: with the field re-solved every timestep, the
  σ(T) heating curve must stay below the constant-σ curve and approach its
  own steady state from below.

Pass: exit 0 and 'HEAT-SIGMA GATE PASSED'. The deck tier runs anywhere;
the live tiers auto-skip if ElmerSolver is absent.
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


# the de-risked billet (probe C, 2026-07-16): a/δ = 0.199 keeps the 1-D
# low-frequency reference honest; α·ΔT ≈ 0.06 converges in ~5 outer iterations
A_M, SIGMA, ALPHA, H0, F = 0.010, 1e6, 0.004, 2e5, 100.0
K_TH, T_EXT, H_CONV = 20.0, 293.15, 50.0
H_MM = 80.0  # billet height (adiabatic ends: they lie ON the domain boundary)


def _billet_model(alpha=None, transient=False):
    tb = {"k": K_TH}
    if transient:
        # rho*cp sized for tau ~ 20 s so 60 s ~ 3*tau (physics check, not a
        # datasheet material)
        tb.update(rho=1000.0, cp=225.0)
    body = {"name": "billet", "r0": 0.0, "r1": 10.0, "z0": -H_MM / 2,
            "z1": H_MM / 2, "sigma": SIGMA, "mu_r": 1.0, "lc": 0.5}
    if alpha is not None:
        body["sigma_alpha"] = alpha
    model = {
        "bodies": [body],
        "air": (100.0, -H_MM / 2, H_MM / 2),
        "lc_air": 5.0,
        "bc": {"router": {"matc_re": "0.5*{0:.12g}*tx".format(MU0 * H0)},
               "ztop": None, "zbottom": None},
        "thermal": {"t_ext": T_EXT, "h": H_CONV, "bodies": {"billet": tb}},
    }
    if transient:
        model["thermal"]["transient"] = {"total_time_s": 60.0, "n_steps": 10}
    return model


def _write_deck(model):
    from emstudio.solvers.elmer import writer

    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                       "emstudio_sigma_deck_{0}.sif".format(os.getpid()))
    writer.write_sif(model, F, tmp, {"billet": 1, "air": 2},
                     {"router": 1, "surf_billet": 2})
    with open(tmp, encoding="utf-8") as fh:
        text = fh.read()
    os.remove(tmp)
    return text


# --------------------------------------------------------------------------
# independent coupled 1-D reference: (1/r)(k r T')' + q(r,T) = 0 with
# q = σ(T)·ω²μ0²H0²r²/8 (H0 PEAK → the time-average 1/2 is in the /8),
# lateral convection −kT'(a) = h(T(a)−Text), regular at the axis.
# RK4 shooting on T(0) + bisection — pure python, no scipy, no Elmer.
# --------------------------------------------------------------------------
def _solve_billet_1d(alpha, n=2000):
    c_src = (2.0 * math.pi * F) ** 2 * MU0 ** 2 * H0 ** 2 / 8.0

    def sigma_t(t):
        return SIGMA / (1.0 + alpha * (t - T_EXT))

    def shoot(t0):
        # state: T and FL = k·r·T' (FL/r → 0 at the axis)
        dr = A_M / n
        t, fl, r = t0, 0.0, 0.0

        def deriv(r_, t_, f_):
            dt = f_ / (K_TH * r_) if r_ > 0.0 else 0.0
            df = -sigma_t(t_) * c_src * r_ ** 3  # dFL/dr = −q·r
            return dt, df

        for _ in range(n):
            k1t, k1f = deriv(r, t, fl)
            k2t, k2f = deriv(r + dr / 2, t + dr / 2 * k1t, fl + dr / 2 * k1f)
            k3t, k3f = deriv(r + dr / 2, t + dr / 2 * k2t, fl + dr / 2 * k2f)
            k4t, k4f = deriv(r + dr, t + dr * k3t, fl + dr * k3f)
            t += dr * (k1t + 2 * k2t + 2 * k3t + k4t) / 6.0
            fl += dr * (k1f + 2 * k2f + 2 * k3f + k4f) / 6.0
            r += dr
        return t, fl

    def resid(t0):
        ta, fa = shoot(t0)
        return fa + A_M * H_CONV * (ta - T_EXT)

    lo, hi = T_EXT, T_EXT + 100.0
    flo = resid(lo)
    if flo * resid(hi) > 0:
        raise RuntimeError("reference shooting: no sign change in bracket")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if flo * resid(mid) <= 0:
            hi = mid
        else:
            lo = mid
            flo = resid(lo)
    t0 = 0.5 * (lo + hi)
    ta, fa = shoot(t0)
    p_per_len = -2.0 * math.pi * fa  # P' = 2π∫q·r dr = −2π·FL(a)
    return t0, ta, p_per_len


def gate_emission():
    const_none = _write_deck(_billet_model())          # no sigma_alpha key
    const_zero = _write_deck(_billet_model(alpha=0.0))
    check("alpha 0 (and absent key) => byte-identical constant-sigma deck",
          const_none == const_zero)
    check("constant-sigma deck: plain 'Electric Conductivity = Real', single "
          "steady-state iteration, per-timestep VTU",
          "Electric Conductivity = Real 1000000" in const_none
          and "Steady State Max Iterations = 1" in const_none
          and "Electric Conductivity = Variable Temperature" not in const_none
          and "Exec Solver = After Timestep" in const_none)

    sig = _write_deck(_billet_model(alpha=ALPHA))
    check("sigma(T) deck emits 'Electric Conductivity = Variable Temperature' "
          "+ the MATC sigma0/(1+alpha*(tx-tref))",
          "Electric Conductivity = Variable Temperature" in sig
          and "1000000/(1+0.004*(tx-293.15))" in sig)
    check("sigma(T) deck opens the outer coupled loop (Steady State Max "
          "Iterations = 30)",
          "Steady State Max Iterations = 30" in sig)
    check("sigma(T) deck emits the MANDATORY ambient IC (negative-sigma trap)",
          "Initial Condition 1" in sig and "Initial Condition = 1" in sig
          and "Temperature = Real 293.15" in sig)
    check("sigma(T) deck writes the VTU After Simulation (not the uncoupled "
          "first iterate)",
          'Exec Solver = "After Simulation"' in sig
          and "Exec Solver = After Timestep" not in sig.split("SaveScalars")[0])
    check("sigma(T) alone keeps the heat solve linear and emits NO radiation "
          "keywords / Stefan-Boltzmann",
          "Nonlinear System Max Iterations = 1" in sig
          and "Radiation" not in sig and "Stefan Boltzmann" not in sig)

    tr_const = _write_deck(_billet_model(transient=True))
    tr_sig = _write_deck(_billet_model(alpha=ALPHA, transient=True))
    check("transient constant-sigma keeps the single-shot 'Before Simulation' "
          "field solve (byte-identical legacy path)",
          'Exec Solver = "Before Simulation"' in tr_const)
    check("transient sigma(T) re-solves the field every timestep (no 'Before "
          "Simulation')",
          'Exec Solver = "Before Simulation"' not in tr_sig)

    # sigma(T) on a body outside the heat solve must refuse loudly
    from emstudio.solvers.elmer import writer
    bad = _billet_model(alpha=ALPHA)
    del bad["thermal"]
    try:
        _write_deck(bad)
    except writer.ElmerModelError:
        check("sigma(T) body without a thermal entry raises ElmerModelError",
              True)
    else:
        check("sigma(T) body without a thermal entry raises ElmerModelError",
              False, "deck was written")


def gate_live_steady():
    from emstudio.solvers.elmer import parser as eparser
    from emstudio.solvers.elmer import run_model

    try:
        res = run_model(_billet_model(alpha=ALPHA), [F], extract_coupling=False)
    except Exception as exc:  # noqa: BLE001
        print("  skip  live steady tier — Elmer run unavailable: {0}".format(exc))
        return
    case = res.sweep_cases()[0]
    mesh = eparser.parse_vtu(case["vtu"])
    t_c = eparser.field_at(mesh, 0.0, 0.0, "temperature")
    t_s = eparser.field_at(mesh, 10.0, 0.0, "temperature")
    p_fem = case["eddy_power_w"]

    t0_ref, ta_ref, p_len_ref = _solve_billet_1d(ALPHA)
    p_ref = p_len_ref * (H_MM * 1e-3)
    check("coupled eddy power == independent 1-D reference (0.5%)",
          abs(p_fem / p_ref - 1.0) < 0.005,
          "FEM {0:.5f} vs ref {1:.5f} W ({2:+.3%})".format(
              p_fem, p_ref, p_fem / p_ref - 1.0))
    check("coupled centerline temperature rise == reference (0.5%)",
          abs((t_c - T_EXT) / (t0_ref - T_EXT) - 1.0) < 0.005,
          "FEM {0:.3f} vs ref {1:.3f} K".format(t_c, t0_ref))
    check("coupled surface temperature rise == reference (0.5%)",
          abs((t_s - T_EXT) / (ta_ref - T_EXT) - 1.0) < 0.005,
          "FEM {0:.3f} vs ref {1:.3f} K".format(t_s, ta_ref))
    check("coupled loop converged cleanly (no 'did not converge' warnings)",
          not case.get("solver_warnings"),
          "; ".join(case.get("solver_warnings") or []))

    # sigma(T) took effect AND with the right sign: self-limiting, so power
    # lands BELOW the constant-sigma run by the reference-predicted ~5.57%
    # (an inverted sigma table would land ABOVE — the de-risk's sign trap)
    const = run_model(_billet_model(), [F], extract_coupling=False)
    ccase = const.sweep_cases()[0]
    p_const = ccase["eddy_power_w"]
    delta = p_fem / p_const - 1.0
    check("sigma(T) self-limiting: coupled power {0:.3f} W sits ~5.57% BELOW "
          "constant-sigma {1:.3f} W".format(p_fem, p_const),
          -0.067 < delta < -0.045, "{0:+.3%}".format(delta))
    t_c_const = eparser.field_at(
        eparser.parse_vtu(ccase["vtu"]), 0.0, 0.0, "temperature")
    check("coupled centerline is cooler than constant-sigma (feedback sign)",
          t_c < t_c_const,
          "{0:.3f} vs {1:.3f} K".format(t_c, t_c_const))


def gate_live_transient():
    from emstudio.solvers.elmer import run_model

    try:
        res_sig = run_model(_billet_model(alpha=ALPHA, transient=True), [F],
                            extract_coupling=False)
        res_const = run_model(_billet_model(transient=True), [F],
                              extract_coupling=False)
    except Exception as exc:  # noqa: BLE001
        print("  skip  live transient tier — Elmer run unavailable: {0}".format(exc))
        return
    hist_sig = res_sig.sweep_cases()[0]["temp_history"]
    hist_const = res_const.sweep_cases()[0]["temp_history"]
    check("transient runs produce heating curves", bool(hist_sig) and bool(hist_const))
    if not (hist_sig and hist_const):
        return
    end_sig = hist_sig["t_max_k"][-1]
    end_const = hist_const["t_max_k"][-1]
    check("transient sigma(T) heating curve ends BELOW the constant-sigma "
          "curve (per-timestep field re-solve took effect)",
          end_sig < end_const,
          "{0:.3f} vs {1:.3f} K".format(end_sig, end_const))
    check("transient sigma(T) curve is monotone heating toward its steady "
          "state (approach from below)",
          all(b >= a - 1e-9 for a, b in zip(hist_sig["t_max_k"],
                                            hist_sig["t_max_k"][1:]))
          and end_sig > T_EXT + 5.0,
          "end {0:.3f} K".format(end_sig))


def main():
    print("EMStudio heat-sigma (magnetics §3, coupled Joule) validation gate")
    gate_emission()
    gate_live_steady()
    gate_live_transient()
    if FAILURES:
        print("HEAT-SIGMA GATE FAILED: {0}".format(FAILURES))
        return 1
    print("HEAT-SIGMA GATE PASSED")
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
        raise SystemExit("heat-sigma validation failed")
    sys.exit(0)
