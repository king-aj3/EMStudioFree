# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: temperature-dependent heat conductivity k(T) in the Elmer
magnetics→heat chain (MAGNETICS_DEPTH_PLAN §2).

k(T) = k0·(1 + β·(T − Tref)). Two tiers:

* **Deck emission** (pure ``write_sif``): β ≠ 0 emits
  ``Heat Conductivity = Variable Temperature`` + the MATC expression, plus
  the same nonlinear machinery the radiation slice added (Newton block +
  ambient IC); β == 0 is **byte-identical** to the constant-k deck.

* **Live solve** (Elmer v26.2, freecadcmd): a uniform-field Joule billet
  with adiabatic ends. The **Kirchhoff transform** ``Θ(T) = ∫k dT`` maps the
  nonlinear conduction to the constant-k Poisson problem, so the interior
  heat that must conduct out is source-set and **k-independent**:
  ``∫_{Ts}^{Tc} k(T) dT = σ_e ω² μ0² H0² a⁴ / 128``. The gate reads Tc, Ts
  from the FEM and checks that integral — AND that the raw drop Tc−Ts
  differs measurably from the constant-k value C/k0 (proving k(T) took
  effect rather than being silently ignored).

Pass: exit 0 and 'HEAT-KTEMP GATE PASSED'. The deck tier runs anywhere.
The live tier needs gmsh + ElmerSolver + ElmerGrid, PROBED BEFORE the solve
(``_live_backends_missing``): with them present the solve is un-wrapped, so a
bad SIF / meshing failure / parser change fails loudly; with them absent the
gate prints NO pass token and FAILS (``main`` returns 2, process exit 1),
because you asked for this gate by name and it cannot answer.
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


# strong gradient so k(T) is clearly exercised: high drive, low k0
A_M, SIGMA, H0, F = 0.010, 1e6, 5e5, 100.0
K0, BETA, T_EXT, H_CONV = 1.0, 0.02, 293.15, 5.0


def _billet_model(k_beta=None):
    h_mm = 80.0
    tb = {"k": K0}
    if k_beta is not None:
        tb["k_beta"] = k_beta
    return {
        "bodies": [
            {"name": "billet", "r0": 0.0, "r1": 10.0, "z0": -h_mm / 2,
             "z1": h_mm / 2, "sigma": SIGMA, "mu_r": 1.0, "lc": 0.5},
        ],
        "air": (100.0, -h_mm / 2, h_mm / 2),
        "lc_air": 5.0,
        "bc": {"router": {"matc_re": "0.5*{0:.12g}*tx".format(MU0 * H0)},
               "ztop": None, "zbottom": None},
        "thermal": {"t_ext": T_EXT, "h": H_CONV, "bodies": {"billet": tb}},
    }


def _write_deck(model):
    from emstudio.solvers.elmer import writer

    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                       "emstudio_ktemp_deck_{0}.sif".format(os.getpid()))
    writer.write_sif(model, F, tmp, {"billet": 1, "air": 2},
                     {"router": 1, "surf_billet": 2})
    with open(tmp, encoding="utf-8") as fh:
        text = fh.read()
    os.remove(tmp)
    return text


def gate_emission():
    const_none = _write_deck(_billet_model())          # no k_beta key
    const_zero = _write_deck(_billet_model(k_beta=0.0))
    check("k_beta 0 (and absent key) => byte-identical constant-k deck",
          const_none == const_zero)
    check("constant-k deck: plain 'Heat Conductivity = Real', single heat "
          "iteration, no Newton/IC",
          "Heat Conductivity = Real 1" in const_none
          and "Nonlinear System Max Iterations = 1" in const_none
          and "Variable Temperature" not in const_none
          and "Newton After" not in const_none)

    kt = _write_deck(_billet_model(k_beta=BETA))
    check("k(T) deck emits 'Heat Conductivity = Variable Temperature' + the "
          "MATC k0*(1+beta*(tx-tref))",
          "Heat Conductivity = Variable Temperature" in kt
          and "1*(1+0.02*(tx-293.15))" in kt)
    check("k(T) deck gets the Newton nonlinear block + ambient IC (shared "
          "with the radiation path)",
          "Nonlinear System Max Iterations = 50" in kt
          and "Nonlinear System Newton After Iterations = 5" in kt
          and "Initial Condition 1" in kt
          and "Initial Condition = 1" in kt)
    check("k(T) alone emits NO radiation keywords / Stefan-Boltzmann",
          "Radiation" not in kt and "Stefan Boltzmann" not in kt)


def _live_backends_missing():
    """Binaries the live tier needs that this box does NOT have — probed
    BEFORE any solve is attempted. Empty list == the tier can really run.

    ⚠ WHY THIS EXISTS. The live tier used to be a bare ``except Exception``
    wrapped around ``run_model``, which relabelled EVERY failure — a malformed
    SIF, a meshing failure, a renamed VTU field, a ``parser`` change, a genuine
    k(T) regression — as "Elmer run unavailable", discarded the whole numeric
    half and still printed the unqualified ``HEAT-KTEMP GATE PASSED``. A broken
    conduction chain was therefore indistinguishable from an absent solver, and
    under freecadcmd (which drops ``print`` on exit) the exit code was the ONLY
    signal a caller saw — and it said success. Probing first is what lets the
    ``try`` disappear entirely: past this check, anything that goes wrong is a
    real failure and must reach the traceback at the bottom of this file.

    Resolved through the PRODUCT's own resolver (prefs → env → PATH → platform
    dirs), not a bare ``shutil.which``, so an ``EMSTUDIO_ELMER`` override
    counts and this probe cannot disagree about which binary ``run_model``
    will actually launch. ElmerGrid is probed too rather than assumed: it has
    no registry entry of its own (it is resolved as a sibling of ElmerSolver),
    and the guided Windows install has already produced a real box with
    ElmerSolver found and ElmerGrid "not found" in the same bin directory.
    """
    from emstudio.setup import solvers as solver_setup
    from emstudio.solvers.base import SolverError
    from emstudio.solvers.elmer.runner import find_elmergrid

    missing = []
    if not solver_setup.find_backend("gmsh").found:
        missing.append("gmsh")           # meshes the billet before Elmer runs
    if not solver_setup.find_backend("elmer").found:
        missing.append("ElmerSolver")
    else:
        try:
            find_elmergrid()
        except SolverError:              # ONLY "companion tool absent"
            missing.append("ElmerGrid")
    return missing


def gate_live():
    from emstudio.solvers.elmer import parser as eparser
    from emstudio.solvers.elmer import run_model

    # NO try/except here, deliberately. _live_backends_missing() has already
    # proved every binary this needs is present, so the only things left that
    # can raise are REGRESSIONS — and a regression must not be able to dress
    # itself up as "solver unavailable" and take the pass token with it.
    res = run_model(_billet_model(k_beta=BETA), [F],
                    extract_coupling=False)
    case = res.sweep_cases()[0]
    mesh = eparser.parse_vtu(case["vtu"])
    t_c = eparser.field_at(mesh, 0.0, 0.0, "temperature")
    t_s = eparser.field_at(mesh, 10.0, 0.0, "temperature")

    # source-set interior heat integral (k-independent): the second moment of
    # the q(r) ~ r^2 Joule distribution over the adiabatic-ended billet
    w = 2.0 * math.pi * F
    c_flux = SIGMA * w ** 2 * MU0 ** 2 * H0 ** 2 * A_M ** 4 / 128.0

    def theta(t_k):  # Kirchhoff potential integral_{Tref}^{T} k(T') dT'
        return K0 * ((t_k - T_EXT) + 0.5 * BETA * (t_k - T_EXT) ** 2)

    kirchhoff = theta(t_c) - theta(t_s)
    rel_k = kirchhoff / c_flux - 1.0
    check("Kirchhoff integral ∫k(T)dT over the interior == source-set flux "
          "constant (k(T) conduction correct)", abs(rel_k) < 0.02,
          "FEM {0:.5g} vs analytic {1:.5g} W/m ({2:+.2%})".format(
              kirchhoff, c_flux, rel_k))

    # k(T) genuinely took effect: the RAW drop differs from the constant-k0
    # value by more than the tolerance (k rises with T -> hotter interior
    # conducts better -> smaller drop than C/k0)
    dt_const = c_flux / K0
    dt_raw = t_c - t_s
    check("k(T) took effect: raw drop {0:.3g} K is smaller than the "
          "constant-k drop {1:.3g} K by >5% (rising k)".format(dt_raw,
                                                               dt_const),
          dt_raw < dt_const * 0.95 and dt_raw > 0.0,
          "{0:+.1%}".format(dt_raw / dt_const - 1.0))

    # surface convection balance is k-independent -> Ts unchanged vs const-k
    const = run_model(_billet_model(), [F], extract_coupling=False)
    t_s_const = eparser.field_at(
        eparser.parse_vtu(const.sweep_cases()[0]["vtu"]),
        10.0, 0.0, "temperature")
    check("surface temperature is k-independent (convection balance) — "
          "k(T) matches constant-k Ts",
          abs(t_s - t_s_const) < 0.05,
          "{0:.3f} vs {1:.3f} K".format(t_s, t_s_const))


def main():
    print("EMStudio heat-ktemp (magnetics §2) validation gate")
    gate_emission()
    missing = _live_backends_missing()
    if not missing:
        gate_live()
    else:
        print("  skip  live tier NOT RUN — missing: {0}".format(
            ", ".join(missing)))
    if FAILURES:
        print("HEAT-KTEMP GATE FAILED: {0}".format(FAILURES))
        return 1
    if missing:
        # ⚠ NOT `return 0`, and NOT the PASS token. The deck tier alone does
        # not earn a pass: the numeric half — the Kirchhoff integral, the
        # "k(T) actually took effect" drop and the k-independent surface
        # temperature — is the only part that tests the SOLVE, and none of it
        # ran. Returns 2 rather than 1 so a PROGRAMMATIC caller can tell
        # "could not run" from "ran and was wrong"; the auto-run block at the
        # bottom of this file collapses every non-zero into
        # SystemExit("heat-ktemp validation failed") == process exit 1, which
        # is left alone on purpose (it is this repo's convention, and
        # freecadcmd makes sys.exit(code) unreliable). Either way, non-zero.
        #
        # ⛳ NOTE FOR THE BATTERY, not fixable from inside this file:
        # run_battery.py tiers heat_ktemp_elmer as SOLVER but declares NO
        # requirement for it (it is absent from SOLVER_REQS, and there is no
        # `elmer` kind in _requirement_missing). Until `"heat_ktemp_elmer":
        # "elmer"` is declared there, `--all` on a solver-less box will now
        # report this gate RED instead of printing a vacuous "ok" — which is
        # the honest answer of the two, but the battery skip is the right one.
        print("HEAT-KTEMP GATE FAILED: live tier could not run ({0}) — the "
              "deck tier alone proves nothing about the k(T) solve".format(
                  ", ".join(missing)))
        return 2
    print("HEAT-KTEMP GATE PASSED")
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
        raise SystemExit("heat-ktemp validation failed")
    sys.exit(0)
