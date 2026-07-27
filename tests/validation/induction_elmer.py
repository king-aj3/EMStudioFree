# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Elmer induction heating vs analytic references.

Pass: exit 0 and 'INDUCTION GATE PASSED'.

Gate A — eddy-current physics (pure python3, no FreeCAD): a solid
conducting cylinder in a uniform axial harmonic field H0. The exact
solution is the classic Bessel one (Davies, "Conduction and Induction
Heating"): H(r) = H0*J0(kr)/J0(ka), k = sqrt(-j*w*mu0*sigma); dissipated
power per unit length from the Poynting flux. The FEM model imposes the
uniform field via the vector-potential Dirichlet value A = B0*r/2 at
r = R_out (R_out = 10a; top/bottom NATURAL so the z-independent 1-D
solution is exact up to the known flux-clamping bias, +0.9% at 10 kHz).
This gate pins every convention in the backend: the per-radian
axisymmetric scalar (x 2*pi), peak-amplitude currents, time-averaged
watts, MATC coordinates in meters, and B_z as component 1 of the VTU
flux density.
    Reference run 2026-07-05 (Elmer v26.2, gmsh 4.12.1):
    P(1 kHz) = +0.03% of analytic, P(10 kHz) = +1.26%, Bz(0) to 5 digits.

Gate B — coil excitation path (pure python3): a long thin air-core
solenoid; B at the center vs the exact current-sheet formula
B = mu0*n*I*(L/2)/sqrt((L/2)^2 + R^2). Validates the stranded-coil
Current Density body force end to end.

Gate C — FreeCAD template (only under freecadcmd): the induction-heating
template runs the full FreeCAD path (geometry classification -> gmsh ->
ElmerGrid -> ElmerSolver): billet power positive, coil L positive, and
the reflected resistance consistent with the billet power (R = 2P/I^2,
energy conservation).
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MU0 = 4e-7 * math.pi

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


# --- analytic references ------------------------------------------------------

def power_per_length(a, sigma, f, h0_peak):
    """Time-avg dissipated power per unit length [W/m], PEAK convention."""
    import numpy as np
    from scipy.special import jv

    w = 2 * math.pi * f
    k = np.sqrt(-1j * w * MU0 * sigma)
    ephi_a = (k * h0_peak / sigma) * jv(1, k * a) / jv(0, k * a)
    return float(-math.pi * a * np.real(ephi_a * np.conj(h0_peak)))


def bz_center(a, sigma, f, h0_peak):
    """Complex peak B_z on the cylinder axis."""
    import numpy as np
    from scipy.special import jv

    w = 2 * math.pi * f
    k = np.sqrt(-1j * w * MU0 * sigma)
    return MU0 * h0_peak / jv(0, k * a)


# --- gates ---------------------------------------------------------------------

def gate_a_billet():
    """Uniform-field billet vs Bessel analytic."""
    from emstudio.solvers.elmer import parser as eparser
    from emstudio.solvers.elmer import run_model

    a_m, sigma, h0 = 0.010, 1e6, 1000.0
    b0 = MU0 * h0
    h_mm, r_out_mm = 80.0, 100.0  # R_out = 10a keeps flux clamping < 1%

    model = {
        "bodies": [
            {"name": "billet", "r0": 0.0, "r1": 10.0, "z0": -h_mm / 2,
             "z1": h_mm / 2, "sigma": sigma, "mu_r": 1.0, "lc": 1.0},
        ],
        "air": (r_out_mm, -h_mm / 2, h_mm / 2),
        "lc_air": 5.0,
        "bc": {
            # A_phi = B0*r/2 on the outer radius (MATC tx = r in METERS);
            # top/bottom natural => solution is exactly z-independent
            "router": {"matc_re": "0.5*{0:.12g}*tx".format(b0)},
            "ztop": None,
            "zbottom": None,
        },
    }
    res = run_model(model, [1000.0, 10000.0], extract_coupling=False)

    windows = {1000.0: 0.015, 10000.0: 0.03}  # incl. known +0.9% clamp at 10 kHz
    for case in res.sweep_cases():
        f = case["freq_hz"]
        p_ana = power_per_length(a_m, sigma, f, h0) * (h_mm * 1e-3)
        rel = case["eddy_power_w"] / p_ana - 1
        check("billet power @ {0:.0f} Hz vs Bessel analytic".format(f),
              abs(rel) < windows[f],
              "FEM {0:.6g} W vs analytic {1:.6g} W ({2:+.2%})".format(
                  case["eddy_power_w"], p_ana, rel))
        mesh = eparser.parse_vtu(case["vtu"])
        # B = (B_r, B_z, 0) in the rz plane -> B_z is component 1
        b_re = eparser.field_at(mesh, 0.0, 0.0, "magnetic flux density re")[1]
        b_im = eparser.field_at(mesh, 0.0, 0.0, "magnetic flux density im")[1]
        b_fem = complex(b_re, b_im)
        b_ana = bz_center(a_m, sigma, f, h0)
        rel_b = abs(b_fem - b_ana) / abs(b_ana)
        check("Bz at billet center @ {0:.0f} Hz".format(f), rel_b < 0.02,
              "FEM {0:.4g}{1:+.4g}j T vs analytic {2:.4g}{3:+.4g}j T "
              "({4:.2%})".format(b_fem.real, b_fem.imag, b_ana.real,
                                 b_ana.imag, rel_b))
    print("  (workdir: {0})".format(res.meta["workdir"]))


def gate_b_solenoid():
    """Air-core solenoid center field vs the exact current-sheet formula."""
    from emstudio.solvers.elmer import parser as eparser
    from emstudio.solvers.elmer import run_model

    turns, current, r_mean_mm, len_mm = 100, 1.0, 30.5, 200.0
    model = {
        "bodies": [
            {"name": "solenoid", "r0": 30.0, "r1": 31.0, "z0": -len_mm / 2,
             "z1": len_mm / 2, "sigma": 0.0, "mu_r": 1.0, "lc": 0.5,
             "coil": {"turns": turns, "current_a": current}},
        ],
        "domain_scale": 8.0,
    }
    res = run_model(model, [1000.0], extract_coupling=False)
    case = res.sweep_cases()[0]
    mesh = eparser.parse_vtu(case["vtu"])
    bz = eparser.field_at(mesh, 0.0, 0.0, "magnetic flux density re")[1]
    half_m = len_mm / 2 * 1e-3
    r_m = r_mean_mm * 1e-3
    n_per_m = turns * current / (len_mm * 1e-3)
    b_ana = MU0 * n_per_m * half_m / math.sqrt(half_m ** 2 + r_m ** 2)
    rel = bz / b_ana - 1
    check("solenoid center B vs current-sheet analytic", abs(rel) < 0.02,
          "FEM {0:.6g} T vs analytic {1:.6g} T ({2:+.2%})".format(bz, b_ana, rel))


def gate_d_thermal():
    """Thermal chain vs the exact 1-D radial solution (pure python3).

    Full-height billet (adiabatic ends — the surface group excludes edges on
    the domain boundary) in a uniform 100 Hz field: q(r) ~ r^2 to 0.04%, so
    the steady radial profile is exact:
      T_surf - T_ext          = sigma*w^2*mu0^2*H0^2*a^3 / (32*h)
      T_center - T_surf       = sigma*w^2*mu0^2*H0^2*a^4 / (128*k)
    The convected power must equal the Joule power (energy conservation) —
    Elmer's built-in 'Joule Heat' coupling integrates the source consistently.
        Reference run 2026-07-06 (lc=0.5, Joule Heat = Logical True):
        balance -0.00%, dT +0.07%, T_surf rise -0.02%.
    """
    from emstudio.solvers.elmer import parser as eparser
    from emstudio.solvers.elmer import run_model

    a_m, sigma, h0, f = 0.010, 1e6, 1e5, 100.0
    k_th, h_conv, t_ext = 20.0, 5.0, 293.15
    b0 = MU0 * h0
    h_mm = 80.0
    model = {
        "bodies": [
            {"name": "billet", "r0": 0.0, "r1": 10.0, "z0": -h_mm / 2,
             "z1": h_mm / 2, "sigma": sigma, "mu_r": 1.0, "lc": 0.5},
        ],
        "air": (100.0, -h_mm / 2, h_mm / 2),
        "lc_air": 5.0,
        "bc": {
            "router": {"matc_re": "0.5*{0:.12g}*tx".format(b0)},
            "ztop": None,
            "zbottom": None,
        },
        "thermal": {"t_ext": t_ext, "h": h_conv, "bodies": {"billet": {"k": k_th}}},
    }
    res = run_model(model, [f], extract_coupling=False)
    case = res.sweep_cases()[0]
    t = case["temperature"]["billet"]

    rel = t["conv_power_w"] / case["eddy_power_w"] - 1
    check("thermal energy balance (convected vs Joule power)", abs(rel) < 0.01,
          "conv {0:.5g} W vs eddy {1:.5g} W ({2:+.2%})".format(
              t["conv_power_w"], case["eddy_power_w"], rel))

    w = 2 * math.pi * f
    mesh = eparser.parse_vtu(case["vtu"])
    t_c = eparser.field_at(mesh, 0.0, 0.0, "temperature")
    t_s = eparser.field_at(mesh, 10.0, 0.0, "temperature")
    dt_ana = sigma * w ** 2 * MU0 ** 2 * h0 ** 2 * a_m ** 4 / (128.0 * k_th)
    rel_dt = (t_c - t_s) / dt_ana - 1
    check("radial dT profile vs exact 1-D solution", abs(rel_dt) < 0.02,
          "FEM {0:.5g} K vs analytic {1:.5g} K ({2:+.2%})".format(
              t_c - t_s, dt_ana, rel_dt))
    rise_ana = sigma * w ** 2 * MU0 ** 2 * h0 ** 2 * a_m ** 3 / (32.0 * h_conv)
    rel_rise = (t_s - t_ext) / rise_ana - 1
    check("surface temperature rise vs analytic", abs(rel_rise) < 0.02,
          "FEM {0:.4f} K vs analytic {1:.4f} K ({2:+.2%})".format(
              t_s - t_ext, rise_ana, rel_rise))

    # PDF report from a real solved result (exercises the |B| field map path)
    import tempfile

    from emstudio.report import magnetics_report

    pdf = os.path.join(tempfile.mkdtemp(prefix="emstudio_magrep_"), "induction.pdf")
    magnetics_report(res, pdf, title="Induction Heating", author="gate")
    ok_pdf = (os.path.isfile(pdf) and os.path.getsize(pdf) >= 5000
              and open(pdf, "rb").read(5) == b"%PDF-")
    check("magnetics PDF report (with field map) is valid", ok_pdf, pdf)


def gate_e_transient():
    """Transient heating curve vs the lumped-capacitance exponential (python3).

    Thermally-thin billet (Biot ~ 0.01, so the lumped model is exact): the
    temperature rise follows T(t) = T_ss - (T_ss - T0)·exp(-t/tau), with
    tau = rho·c·V/(h·A) and T_ss the steady rise. The harmonic field is solved
    ONCE (constant in time) and the heat equation is time-stepped. Compared at
    settled times (>= 0.5 tau; the first BDF step has larger startup error).
        Reference run 2026-07-06: final T within 0.1 K of analytic; worst
        settled error 0.91% of the local rise; eddy power constant at 0.979 W.
    """
    from emstudio.solvers.elmer import run_model

    a_m, sigma, h0, f = 0.010, 1e6, 1e5, 100.0
    k_th, h_conv, t_ext = 237.0, 500.0, 293.15
    rho, cp = 2700.0, 900.0  # aluminum
    b0 = MU0 * h0
    h_mm, total_t, nsteps = 80.0, 75.0, 30
    model = {
        "bodies": [
            {"name": "billet", "r0": 0.0, "r1": 10.0, "z0": -h_mm / 2,
             "z1": h_mm / 2, "sigma": sigma, "mu_r": 1.0, "lc": 1.0},
        ],
        "air": (100.0, -h_mm / 2, h_mm / 2),
        "lc_air": 5.0,
        "bc": {"router": {"matc_re": "0.5*{0:.12g}*tx".format(b0)},
               "ztop": None, "zbottom": None},
        "thermal": {
            "t_ext": t_ext, "h": h_conv,
            "bodies": {"billet": {"k": k_th, "rho": rho, "cp": cp}},
            "transient": {"total_time_s": total_t, "n_steps": nsteps},
        },
    }
    res = run_model(model, [f], extract_coupling=False)
    curve = res.heating_curve()
    check("transient run produced a heating curve", curve is not None,
          "{0} points".format(len(curve[0]) if curve else 0))
    if not curve:
        return
    t_arr, temp = curve

    # analytic lumped model
    import numpy as np
    from scipy.special import jv

    w = 2 * math.pi * f
    k = np.sqrt(-1j * w * MU0 * sigma)
    p_len = float(-math.pi * a_m * np.real(
        (k * h0 / sigma) * jv(1, k * a_m) / jv(0, k * a_m) * np.conj(h0)))
    h_m = h_mm * 1e-3
    p_tot = p_len * h_m
    vol = math.pi * a_m ** 2 * h_m
    area = 2 * math.pi * a_m * h_m
    t_ss = t_ext + p_tot / (h_conv * area)
    tau = rho * cp * vol / (h_conv * area)

    worst = 0.0
    for ti, tf in zip(t_arr, temp):
        if ti < 0.5 * tau:
            continue  # skip BDF startup transient
        ta = t_ss - (t_ss - t_ext) * math.exp(-ti / tau)
        rel = (tf - t_ext) / (ta - t_ext) - 1
        worst = max(worst, abs(rel))
    check("heating curve vs lumped exponential (t >= 0.5 tau)", worst < 0.02,
          "worst {0:.2%} of local rise (tau = {1:.1f} s)".format(worst, tau))
    # asymptote: the last sample must approach the analytic value at that time
    ta_end = t_ss - (t_ss - t_ext) * math.exp(-t_arr[-1] / tau)
    rel_end = (temp[-1] - t_ext) / (ta_end - t_ext) - 1
    check("final temperature vs analytic", abs(rel_end) < 0.02,
          "FEM {0:.4f} K vs analytic {1:.4f} K ({2:+.2%})".format(
              temp[-1], ta_end, rel_end))
    # curve must be monotonically rising toward steady state
    monotone = all(temp[i + 1] >= temp[i] - 1e-6 for i in range(len(temp) - 1))
    check("heating curve is monotonic", monotone,
          "T0={0:.3f} -> Tend={1:.3f} K".format(temp[0], temp[-1]))


def gate_c_template():
    """FreeCAD induction template end-to-end (freecadcmd only)."""
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import elmer
    from emstudio.templates import induction

    doc = FreeCAD.newDocument("InductionGate")
    try:
        ana = induction.makeInduction(doc)
        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverElmer"][0]
        assert query.get_coils(ana), "template created no coil"
        result = elmer.run(ana, solver)
        case = result.sweep_cases()[0]
        p_billet = case["eddy_power_w"]
        check("template billet power positive", p_billet > 1.0,
              "P = {0:.6g} W".format(p_billet))
        coil_name = result.coils[0]["name"]
        current = result.coils[0]["current_a"]
        freqs, ls, rs = result.coil_impedance(coil_name)
        check("template coil L positive", ls[0] > 0,
              "L_eff = {0:.6g} uH".format(ls[0] * 1e6))
        r_expected = 2.0 * p_billet / current ** 2
        rel = rs[0] / r_expected - 1
        check("reflected R consistent with billet power (2P/I^2)",
              abs(rel) < 0.05,
              "R_reflected {0:.6g} Ohm vs 2P/I^2 {1:.6g} Ohm ({2:+.2%})".format(
                  rs[0], r_expected, rel))
        temps = case.get("temperature") or {}
        check("template solves temperature (SolveThermal on)", bool(temps),
              "bodies: {0}".format(sorted(temps)))
        if temps:
            t = list(temps.values())[0]
            rel_t = t["conv_power_w"] / p_billet - 1
            check("template thermal energy balance", abs(rel_t) < 0.02,
                  "conv {0:.5g} W vs Joule {1:.5g} W ({2:+.2%}); "
                  "T_max = {3:.1f} K".format(
                      t["conv_power_w"], p_billet, rel_t, t["t_max"]))

        # transient heating through the full FreeCAD path (data model -> sif)
        solver.TransientHeating = True
        solver.HeatingTime = 30.0
        solver.HeatingSteps = 12
        doc.recompute()
        tres = elmer.run(ana, solver)
        curve = tres.heating_curve()
        ok = (curve is not None and len(curve[0]) == 12
              and curve[1][-1] > curve[1][0])  # temperature rose
        check("template transient heating curve (FreeCAD path)", ok,
              "{0} pts, T {1:.1f}->{2:.1f} K".format(
                  len(curve[0]) if curve else 0,
                  curve[1][0] if curve else 0, curve[1][-1] if curve else 0))
    finally:
        FreeCAD.closeDocument(doc.Name)


def main():
    print("EMStudio induction-heating validation gate (Elmer)")
    print("Gate A: billet in uniform field vs Bessel analytic")
    gate_a_billet()
    print("Gate B: solenoid coil excitation vs current-sheet analytic")
    gate_b_solenoid()
    print("Gate D: thermal chain vs exact 1-D radial solution")
    gate_d_thermal()
    print("Gate E: transient heating curve vs lumped exponential")
    gate_e_transient()
    try:
        import FreeCAD  # noqa: F401
        have_freecad = True
    except ImportError:
        have_freecad = False
    if have_freecad:
        print("Gate C: FreeCAD induction template end-to-end")
        gate_c_template()
    else:
        print("Gate C skipped (no FreeCAD — run under freecadcmd for the template path)")
    if FAILURES:
        print("INDUCTION GATE FAILED: {0}".format(FAILURES))
        return 1
    print("INDUCTION GATE PASSED")
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
        raise SystemExit("induction validation failed")
    sys.exit(0)
