# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace CPU and GPU answers must AGREE, through the product.

Pass: exit 0 and 'PALACE GPU AGREEMENT GATE PASSED'.

⚠⚠ WHY THIS GATE EXISTS — v1.5.0 published GPU numbers on ajj3.us that the
product's own path could not produce (the product aborted on Palace's default
``/gpu/hip/magma``, which cannot exist on RDNA3; the published numbers came
from a config edited by hand). The CPU-vs-GPU agreement that justified fixing
it was MEASURED, never ENFORCED — and an agreement nobody enforces is exactly
the kind of claim that rots. This gate is that measurement made permanent:

* both legs run through ``run_cavity(solver=<stub>)`` — the product's own
  path, config writer, backend probe and all. No hand-written configs.
* it PROVES the GPU leg really ran on the GPU by reading Palace's own device
  banner. Palace decides GPU support at COMPILE time and a CPU fallback is
  silent, so without this check the gate could compare CPU against CPU and
  pass while testing nothing.

The case is a 40x40x60 mm PEC cavity — small (two legs ~45 s total on the
reference box) and DELIBERATELY square-based: TE101/TE011 are degenerate, and
splitting a degenerate pair is one of the three measured symptoms of the
broken ``/gpu/hip/gen`` backend this gate must catch.

Tolerance: 1e-6 relative, with measured margin on BOTH sides (2026-08-23,
RX 7900 XTX / gfx1100, byte-identical meshes):
  * ``/gpu/hip/shared`` (what the product emits here): worst mode 2.2e-9.
  * ``/gpu/hip/gen`` forced in as a mutation test:      worst mode 4.0e-2,
    BEST mode 1.8e-3 — every single mode fails the gate by 3+ orders.

Skipping: the battery skips this gate (SOLVER_REQS ``palace_gpu``) when no
GPU-linked Palace or no matching GPU exists. Run BY HAND it fails loudly
instead — you asked for it, so a missing backend is an answer, not a skip.
"""
import hashlib
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: Relative eigenfrequency tolerance. Measured good/bad separation is
#: 2.2e-9 vs 1.8e-3 (see module docstring) — three orders of margin each way.
_REL_TOL = 1.0e-6

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


class _StubSolver:
    """The minimal solver object run_cavity reads: Device + rank settings."""

    def __init__(self, device, ranks):
        self.Device = device
        self.MPIRanks = ranks
        self.OMPThreads = 1


def _run_leg(device, ranks):
    """One run_cavity leg. Returns (result, palace_output_lines, config_dict, mesh_sha)."""
    from emstudio.solvers.palace import run_cavity

    lines = []
    res = run_cavity((40.0, 40.0, 60.0), n_modes=6, order=2,
                     solver=_StubSolver(device, ranks),
                     line_callback=lines.append)
    wd = res.meta["workdir"]
    with open(os.path.join(wd, "config.json")) as fh:
        cfg = json.load(fh)
    msh = [f for f in os.listdir(wd) if f.endswith(".msh")][0]
    with open(os.path.join(wd, msh), "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    return res, lines, cfg, sha


def _device_banner(lines):
    """Palace's own 'Device configuration: ...' line — the ground truth of
    which device actually ran, printed by MFEM after device setup."""
    for ln in lines:
        if "Device configuration:" in ln:
            return ln.strip()
    return ""


def main():
    from emstudio.setup import accel

    print("EMStudio Palace CPU-vs-GPU agreement gate")

    gpu_palace = accel.find_gpu_palace()
    check("a GPU-linked Palace build is resolvable", bool(gpu_palace),
          gpu_palace or "none found — build one per docs/PALACE_GPU_BUILD.md")
    if not gpu_palace:
        return 1
    rep = accel.accel_report(gpu_palace)
    check("GPU build + matching GPU on this machine", rep["gpu_usable"], rep["why"])
    if not rep["gpu_usable"]:
        return 1

    # Both legs resolve Palace through find_backend, so point the product at
    # the GPU-capable build for the duration. Same binary for both legs ON
    # PURPOSE: the device is then the ONLY variable, so a disagreement is the
    # backend and nothing else. (This gate runs as its own process, so the
    # environment change dies with it.)
    os.environ["EMSTUDIO_PALACE"] = gpu_palace
    print("  (binary: {0})".format(gpu_palace))

    res_c, lines_c, cfg_c, sha_c = _run_leg("CPU", 4)
    res_g, lines_g, cfg_g, sha_g = _run_leg("GPU", 1)

    # -- the comparison is only valid if both legs solved the SAME matrix ----
    check("both legs meshed byte-identically", sha_c == sha_g,
          "gmsh stopped being deterministic — the physics compare below is "
          "mesh noise, not backend error" if sha_c != sha_g else sha_c[:16])

    # -- prove which device each leg ACTUALLY ran on -------------------------
    # A GPU request a CPU-only build cannot honour falls back SILENTLY inside
    # Palace, so trusting the request would let this gate compare CPU against
    # CPU and pass forever. Palace's own banner is the evidence.
    ban_c, ban_g = _device_banner(lines_c), _device_banner(lines_g)
    check("GPU leg really ran on the GPU",
          ("hip" in ban_g) or ("cuda" in ban_g), ban_g or "no device banner")
    check("CPU leg really ran on the CPU",
          ("cpu" in ban_c) and ("hip" not in ban_c) and ("cuda" not in ban_c),
          ban_c or "no device banner")

    # -- the emitted configs: the product's own output, read back ------------
    check("CPU config emits no Backend key", "Backend" not in cfg_c["Solver"],
          repr(cfg_c["Solver"].get("Backend")))
    check("GPU config Device is GPU", cfg_g["Solver"].get("Device") == "GPU",
          repr(cfg_g["Solver"].get("Device")))
    backend = cfg_g["Solver"].get("Backend", "")
    if backend:
        # An override only ever comes from the probe, and never the JIT-fused
        # backend measured wrong on RDNA3 (83-939 ppm off at 353k unknowns,
        # 4e-2 here) nor the MAGMA default the probe exists to route around.
        allowed = {b for pair in accel.CEED_FALLBACKS.values() for b in pair}
        check("emitted Backend comes from the measured-safe list",
              backend in allowed, backend)
        check("emitted Backend is not a /gen JIT backend",
              not backend.endswith("/gen"), backend)
    else:
        print("  (no Backend override emitted — Palace's own default is "
              "compiled in; that is the correct silence)")

    # -- the physics: every eigenmode agrees ---------------------------------
    fc = sorted(m["freq_ghz"] for m in res_c.modes)
    fg = sorted(m["freq_ghz"] for m in res_g.modes)
    check("both legs returned the same number of modes", len(fc) == len(fg),
          "{0} vs {1}".format(len(fc), len(fg)))
    check("at least the requested modes converged", len(fc) >= 6,
          "{0} modes".format(len(fc)))
    worst = 0.0
    for a, b in zip(fc, fg):
        worst = max(worst, abs(b / a - 1.0))
    check("every mode agrees CPU-vs-GPU (rel < {0:g})".format(_REL_TOL),
          worst < _REL_TOL,
          "worst {0:.3e} over {1} modes (fundamental {2:.6f} GHz)".format(
              worst, min(len(fc), len(fg)), fc[0] if fc else float("nan")))

    if FAILURES:
        print("PALACE GPU AGREEMENT GATE FAILED: {0}".format(FAILURES))
        return 1
    print("PALACE GPU AGREEMENT GATE PASSED")
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
        raise SystemExit("palace gpu agreement validation failed")
    sys.exit(0)
