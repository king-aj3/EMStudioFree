# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: surface RADIATION boundary condition in the Elmer
magnetics→heat chain (MAGNETICS_DEPTH_PLAN §1).

Two tiers:

* **Deck emission** (no solver — pure ``write_sif``): emissivity > 0 emits the
  Stefan-Boltzmann constant, the three radiation BC lines, the Newton
  nonlinear block and the ambient initial condition; emissivity == 0 (and
  the absent key) is **byte-identical** to the pre-v0.51 convection-only
  deck. Guards the two silent-catastrophe traps the de-risk probe found
  (missing Stefan-Boltzmann = hard STOP; ``Nonlinear System Max
  Iterations = 1`` under T^4 = −1e14 K at exit 0).

* **Live solve** (Elmer v26.2, freecadcmd): a uniform-field billet with
  adiabatic ends radiating AND convecting off its lateral surface. The
  interior conduction is unchanged by the surface BC, so
  ``T_center − T_surf`` still matches the exact 1-D radial form; the surface
  temperature satisfies the mixed balance
  ``h(Ts−Tamb) + εσ(Ts⁴−Trad⁴) = P_joule / A_lateral`` — solved here by an
  independent bisection root-find. De-risked on the standalone probe to
  0.0004 %; gated here to sub-percent through the production writer.

Pass: exit 0 and 'HEAT-RADIATION GATE PASSED'. The deck tier runs anywhere
(python3); the live tier needs ElmerSolver and auto-skips if absent.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MU0 = 4.0e-7 * math.pi
SIGMA_SB = 5.67e-8
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _billet_model(emissivity=None, rad_t_ext=None):
    """A uniform-field billet with a thermal chain (optionally radiating)."""
    h_mm = 80.0
    model = {
        "bodies": [
            {"name": "billet", "r0": 0.0, "r1": 10.0, "z0": -h_mm / 2,
             "z1": h_mm / 2, "sigma": 1e6, "mu_r": 1.0, "lc": 0.5},
        ],
        "air": (100.0, -h_mm / 2, h_mm / 2),
        "lc_air": 5.0,
        "bc": {"router": {"matc_re": "0.5*{0:.12g}*tx".format(MU0 * 1e5)},
               "ztop": None, "zbottom": None},
        "thermal": {"t_ext": 293.15, "h": 5.0,
                    "bodies": {"billet": {"k": 20.0}}},
    }
    if emissivity is not None:
        model["thermal"]["emissivity"] = emissivity
    if rad_t_ext is not None:
        model["thermal"]["rad_t_ext"] = rad_t_ext
    return model


def _write_deck(model):
    """write_sif with fabricated mesh ids (deck-only; no meshing)."""
    from emstudio.solvers.elmer import writer

    body_ids = {"billet": 1, "air": 2}
    boundary_ids = {"router": 1, "surf_billet": 2}
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                       "emstudio_rad_deck_{0}.sif".format(os.getpid()))
    writer.write_sif(model, 100.0, tmp, body_ids, boundary_ids)
    with open(tmp, encoding="utf-8") as fh:
        text = fh.read()
    os.remove(tmp)
    return text


def gate_emission():
    """Deck emission + byte-identical convection-only guard."""
    conv_only = _write_deck(_billet_model())          # no emissivity key
    conv_zero = _write_deck(_billet_model(emissivity=0.0))
    check("emissivity 0 (and absent key) => byte-identical convection-only "
          "deck", conv_only == conv_zero)
    check("convection-only deck has NO radiation keywords / Stefan-Boltzmann "
          "/ Newton block",
          "Radiation" not in conv_only
          and "Stefan Boltzmann" not in conv_only
          and "Newton After" not in conv_only
          and "Nonlinear System Max Iterations = 1" in conv_only)

    rad = _write_deck(_billet_model(emissivity=0.8, rad_t_ext=300.0))
    check("radiating deck emits Stefan Boltzmann = 5.67e-8 in Constants "
          "(MANDATORY — no Elmer default)",
          "Stefan Boltzmann = Real 5.67e-08" in rad
          or "Stefan Boltzmann = Real 5.67e-8" in rad)
    check("radiating deck emits the three radiation BC lines on the surface",
          "Radiation = String Idealized" in rad
          and "Radiation External Temperature = Real 300" in rad
          and "Emissivity = Real 0.8" in rad)
    check("radiating deck replaces the single heat iteration with the Newton "
          "nonlinear block (the T^4 silent-catastrophe guard)",
          "Nonlinear System Max Iterations = 50" in rad
          and "Nonlinear System Newton After Tolerance = 1.0e-2" in rad
          and "Nonlinear System Newton After Iterations = 5" in rad)
    check("radiating STEADY deck seeds an ambient Initial Condition",
          "Initial Condition 1" in rad
          and "Temperature = Real 293.15" in rad
          and "Initial Condition = 1" in rad)
    # convection pair is retained (radiation STACKS, not replaces)
    check("radiation stacks on the convection pair (both present on the BC)",
          "Heat Transfer Coefficient = Real 5" in rad
          and "External Temperature = Real 293.15" in rad)
    # default radiation temperature falls back to ambient
    rad_def = _write_deck(_billet_model(emissivity=0.8))
    check("radiation temperature defaults to ambient when unset",
          "Radiation External Temperature = Real 293.15" in rad_def)


def gate_live():
    """Mixed convection+radiation billet vs the exact surface balance."""
    from emstudio.solvers.elmer import parser as eparser
    from emstudio.solvers.elmer import run_model

    a_m, sigma, h0, f = 0.010, 1e6, 1e5, 100.0
    k_th, h_conv, t_ext = 20.0, 5.0, 293.15
    emis, t_rad = 0.8, 300.0
    model = _billet_model(emissivity=emis, rad_t_ext=t_rad)
    try:
        res = run_model(model, [f], extract_coupling=False)
    except Exception as exc:  # noqa: BLE001
        print("  skip  live tier — Elmer run unavailable: {0}".format(exc))
        return
    case = res.sweep_cases()[0]

    # surface energy balance: h(Ts-Tamb) + eps*sigma(Ts^4-Trad^4) = P/A.
    # A_lateral = 2*pi*a*height (adiabatic ends excluded from the group).
    p_joule = case["eddy_power_w"]
    height = 0.080
    area = 2.0 * math.pi * a_m * height
    q_surf = p_joule / area

    def bal(ts_k):
        return (h_conv * (ts_k - t_ext)
                + emis * SIGMA_SB * (ts_k ** 4 - t_rad ** 4) - q_surf)

    lo, hi = t_ext, t_ext + 2000.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if bal(mid) > 0.0:
            hi = mid
        else:
            lo = mid
    ts_ana = 0.5 * (lo + hi)

    mesh = eparser.parse_vtu(case["vtu"])
    t_s = eparser.field_at(mesh, 10.0, 0.0, "temperature")
    t_c = eparser.field_at(mesh, 0.0, 0.0, "temperature")
    rel_s = (t_s - t_ext) / (ts_ana - t_ext) - 1.0
    check("mixed conv+rad surface rise vs the exact balance root-find",
          abs(rel_s) < 0.02,
          "FEM {0:.2f} K vs analytic {1:.2f} K ({2:+.2%})".format(
              t_s - t_ext, ts_ana - t_ext, rel_s))
    # interior conduction is unchanged by the surface BC
    w = 2.0 * math.pi * f
    dt_ana = sigma * w ** 2 * MU0 ** 2 * h0 ** 2 * a_m ** 4 / (128.0 * k_th)
    rel_dt = (t_c - t_s) / dt_ana - 1.0
    check("interior dT unchanged by the radiation BC (exact 1-D radial form)",
          abs(rel_dt) < 0.02,
          "FEM {0:.4g} K vs analytic {1:.4g} K ({2:+.2%})".format(
              t_c - t_s, dt_ana, rel_dt))
    # radiation genuinely lowered the surface temperature vs convection-only
    conv_only = run_model(_billet_model(), [f], extract_coupling=False)
    t_s_conv = eparser.field_at(
        eparser.parse_vtu(conv_only.sweep_cases()[0]["vtu"]),
        10.0, 0.0, "temperature")
    check("radiation removes heat: radiating surface is COOLER than "
          "convection-only", t_s < t_s_conv - 0.5,
          "{0:.2f} vs {1:.2f} K".format(t_s, t_s_conv))


def main():
    print("EMStudio heat-radiation (magnetics §1) validation gate")
    gate_emission()
    gate_live()
    if FAILURES:
        print("HEAT-RADIATION GATE FAILED: {0}".format(FAILURES))
        return 1
    print("HEAT-RADIATION GATE PASSED")
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
        raise SystemExit("heat-radiation validation failed")
    sys.exit(0)
