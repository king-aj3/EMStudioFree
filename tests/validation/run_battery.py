# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation-gate battery runner.

Runs the repo's validation gates as subprocesses and fails (exit 1) if any
gate fails — the regression net that used to require typing 17 paths by hand.

    python3 tests/validation/run_battery.py            # FAST tier (~40 s)
    python3 tests/validation/run_battery.py --all      # + the SOLVER tier
    python3 tests/validation/run_battery.py --list     # show the tiers

Tiers (every gate file MUST be listed in exactly one — the runner refuses to
start if a ``tests/validation/*.py`` file is missing from both, so a new gate
cannot be silently left out of the battery):

* FAST — pure python3 + numpy/scipy/matplotlib, no solver binaries, seconds
  each. This is what CI runs on every push. Gates whose local data is absent
  (the ITU digital maps are integral products and cannot ship in-repo) are
  SKIPPED with a reason, not failed.
* SOLVER — need nec2c / openEMS / Elmer / Palace / FastHenry and minutes-to-
  15-minutes each (the release tier). Run with ``--all`` before a release on
  a machine with the backends installed.

python3-only by design (each GATE also runs standalone under freecadcmd where
it applies; the runner itself does not).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))

# gate name -> optional requirement checked before running (None = always run)
FAST = {
    "cable": None,
    "cht_setup": None,
    "cosite": None,
    "coverage": None,
    "element_designer": None,
    "fasthenry_guidance": None,
    "foam_vtk_export": None,
    "freq_guard": None,
    "horn": None,
    "lfmf": None,
    "lib_present_platforms": None,
    "litz_noscipy": None,
    "material_loss": None,
    "openfoam_runner_cancel": None,
    "openfoam_setup": None,
    "p1546": None,
    "p1812": None,
    "p2001": "itu_maps:P2001.npz",
    "p452": "itu_maps:P452.npz",
    "pattern_vtu": None,
    "pattern_sweep": None,
    "propagation": None,
    "small_antenna": None,
    "solid_setup": None,
    "solve_estimate": None,
    "solver_progress": None,
    "thermal": None,
    "touchstone_export": None,
    "two_port_excitation": None,
    "n_port_smatrix": None,
    "wind_transient": None,
    "ui_attr_collisions": None,
    "solve_confirm_coverage": None,
    "tutorials_doc": None,
    "declared_ports": None,
    "solver_versions": None,
}

SOLVER = [
    "amr_palace", "antenna_from_selection", "openfoam_bundle", "openfoam_cavity", "openfoam_cht",
    "openfoam_cht_convection",
    "openfoam_cylinder",
    "openfoam_solid",
    "openfoam_wind",
    "openfoam_wind_transient",
    "bh_elmer", "cavity_palace", "circwaveguide_palace",
    "coax_palace", "coil_inductance_elmer", "curved_wire_nec2",
    "cylcavity_palace", "dipole_nec2",
    "fastsweep_palace",
    "heat_ktemp_elmer", "heat_radiation_elmer", "heat_sigma_elmer",
    "induction_elmer", "isolation_nec2", "isolation_openems",
    "isolation_patch_openems", "lpda_nec2", "mmwave_palace", "monopole_nec2",
    "msl_notch_openems", "open_coil_elmer", "patch_auto_openems",
    "patch_openems",
    "patch_stl_openems", "solenoid3d_elmer",
    "stl_mesh_openems", "n_port_live_palace",
    "team7_elmer", "two_port_openems", "two_port_palace", "waveguide_palace",
    "whitney3d_elmer",
    "wire_current_sharing", "wire_fasthenry", "wire_from_solid", "wpt_elmer",
    "yagi_nec2",
]

_NOT_GATES = {"run_battery", "__init__"}


def _tier_audit():
    """Every tests/validation/*.py file must be tiered exactly once."""
    on_disk = {os.path.splitext(f)[0] for f in os.listdir(_HERE)
               if f.endswith(".py")} - _NOT_GATES
    tiered = set(FAST) | set(SOLVER)
    missing = sorted(on_disk - tiered)
    stale = sorted(tiered - on_disk)
    dupes = sorted(set(FAST) & set(SOLVER))
    if missing or stale or dupes:
        msgs = []
        if missing:
            msgs.append("gate files not tiered (add to FAST or SOLVER in "
                        "run_battery.py): {0}".format(missing))
        if stale:
            msgs.append("tiered names with no file: {0}".format(stale))
        if dupes:
            msgs.append("in both tiers: {0}".format(dupes))
        raise SystemExit("run_battery tier audit FAILED: " + "; ".join(msgs))


#: Requirements for SOLVER-tier gates. A gate that needs a backend the box may
#: not have belongs HERE, not in an `if missing: print("PASSED"); return 0`
#: inside itself.
#:
#: WHY: the four openEMS gates used to self-skip and return 0, so the battery
#: printed "ok" and a standalone run printed "GATE PASSED" — on a box with no
#: openEMS, four gates reported success while testing nothing, and because
#: freecadcmd drops print() on exit the exit code was the ONLY signal a caller
#: saw. Found 2026-08-05 while proving the gates really ran at home; it took a
#: separate probe of find_openems_python() under freecadcmd to tell a pass from
#: a skip, which is precisely the question a gate is supposed to answer itself.
#: Declared here, the battery says "skip" honestly, and running one BY HAND
#: fails loudly when the backend is absent — correct, because you asked for it.
SOLVER_REQS = {
    "n_port_live_palace": "palace",
    "openfoam_cavity": "openfoam",
    "openfoam_cylinder": "openfoam",
    "openfoam_bundle": "openfoam",
    "openfoam_wind": "openfoam",
    "openfoam_cht": "openfoam",
    "openfoam_cht_convection": "openfoam",
    "openfoam_wind_transient": "openfoam",
    "patch_openems": "openems_python",
    "msl_notch_openems": "openems_python",
    "patch_auto_openems": "openems_python",
    "patch_stl_openems": "openems_python",
    "two_port_openems": "openems_python",
}


def _requirement_missing(req):
    """Return a skip reason if the requirement is unavailable, else None."""
    if req is None:
        return None
    kind, _, arg = req.partition(":")
    if kind == "openems_python":
        sys.path.insert(0, _ROOT)
        try:
            from emstudio.setup.solvers import find_openems_python
            if find_openems_python() is None:
                return ("no openEMS python environment — set "
                        "EMSTUDIO_OPENEMS_PYTHON, or install openEMS with its "
                        "venv beside the binary")
        finally:
            sys.path.pop(0)
        return None
    if kind == "openfoam":
        sys.path.insert(0, _ROOT)
        try:
            from emstudio.setup import openfoam as _of
            info = _of.find_openfoam()
            if not info.found:
                return ("no OpenFOAM — install it from Solver Setup "
                        "(Windows: ESI's native build, no admin needed)")
            if not info.usable:
                return ("OpenFOAM found but NOT usable: {0} — {1}".format(
                    info.describe(), _of.status_note() or "probe unhappy"))
        finally:
            sys.path.pop(0)
        return None
    if kind == "itu_maps":
        sys.path.insert(0, _ROOT)
        try:
            from emstudio.coverage import itu_maps
            if itu_maps.find_npz(arg) is None:
                return ("ITU maps not installed ({0}) — integral products, "
                        "never bundled; install_*_maps() once".format(arg))
        finally:
            sys.path.pop(0)
        return None
    raise SystemExit("unknown requirement kind: {0}".format(req))


def _run_gate(name, timeout_s):
    path = os.path.join(_HERE, name + ".py")
    t0 = time.time()
    # Force UTF-8 on the child's stdout. Without it a gate's exit code depends
    # on WHICH SHELL launched the battery: gates print arrows and "±", and on
    # Windows a child inheriting a cp1252 console dies with
    # "'charmap' codec can't encode character '→'" — a UnicodeEncodeError
    # that reads exactly like a physics failure. Measured 2026-08-05:
    # element_designer passed from PowerShell and failed from Git Bash, at the
    # SAME commit. A gate must report on the code, not on the terminal.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run([sys.executable, path], cwd=_ROOT,
                              capture_output=True, text=True, env=env,
                              encoding="utf-8", errors="replace",
                              timeout=timeout_s)
        rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = -1, "TIMEOUT after {0:.0f}s".format(timeout_s)
    return rc, time.time() - t0, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true",
                    help="also run the SOLVER tier (needs the backends)")
    ap.add_argument("--list", action="store_true", help="list tiers and exit")
    ap.add_argument("--fast-timeout", type=float, default=300.0)
    ap.add_argument("--solver-timeout", type=float, default=1800.0)
    args = ap.parse_args(argv)

    _tier_audit()
    if args.list:
        for name in sorted(FAST):
            req = FAST[name]
            print("FAST    {0}{1}".format(name,
                  "  [needs {0}]".format(req) if req else ""))
        for name in SOLVER:
            print("SOLVER  {0}".format(name))
        return 0

    plan = [(n, FAST[n], args.fast_timeout) for n in sorted(FAST)]
    if args.all:
        plan += [(n, SOLVER_REQS.get(n), args.solver_timeout) for n in SOLVER]

    print("EMStudio validation battery — {0} gate(s), tier: {1}".format(
        len(plan), "FAST+SOLVER" if args.all else "FAST"))
    failures, skips = [], []
    t_start = time.time()
    for name, req, timeout_s in plan:
        reason = _requirement_missing(req)
        if reason:
            skips.append(name)
            print("  skip  {0:<24s} — {1}".format(name, reason))
            continue
        rc, dt, out = _run_gate(name, timeout_s)
        if rc == 0:
            print("  ok    {0:<24s} {1:6.1f}s".format(name, dt))
        else:
            failures.append(name)
            print("  FAIL  {0:<24s} {1:6.1f}s (rc={2})".format(name, dt, rc))
            tail = [l for l in out.splitlines() if l.strip()][-12:]
            for line in tail:
                print("        | " + line)
    print("-" * 60)
    print("{0} ok, {1} failed, {2} skipped in {3:.1f}s".format(
        len(plan) - len(failures) - len(skips), len(failures), len(skips),
        time.time() - t_start))
    if failures:
        print("BATTERY FAILED: {0}".format(failures))
        return 1
    print("BATTERY PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
