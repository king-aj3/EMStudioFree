# SPDX-License-Identifier: LGPL-2.1-or-later
"""FAST gate: the GPU build advice is honest on all three platforms.

**Why this gate exists.** `Device = GPU` has been offered on a Palace solver
since v1.4.0, and `emstudio/setup/accel.py` correctly refuses it unless the
resolved binary is linked against a GPU runtime. But until v1.5.0 nothing told a
user how to GET such a binary — EMStudio's own guided build had no GPU flags at
all — so the option was reachable in theory and unreachable in practice. That is
the shape this project keeps finding: a setting that cannot be honoured.

:func:`palace_gpu_plan` closes it by answering, for THIS machine, what a GPU
build would take. This gate keeps that answer honest.

⚠⚠ **THE THREE PLATFORMS GENUINELY DIFFER — one branch does not cover two.**
`os.name` is `"posix"` on macOS AND Linux, and this is a case where treating
them alike would ship a falsehood:

| platform | GPU solve | why |
|---|---|---|
| **Linux** | ✅ CUDA or HIP | measured: HIP on gfx1100 |
| **macOS** | ❌ **never** | Palace declares only `PALACE_WITH_CUDA` / `PALACE_WITH_HIP`; Apple silicon has neither. Not a gap — a limit |
| **Windows** | ⚠ WSL2 only | Palace has no native Windows build; CUDA-in-WSL2 is NVIDIA's route, ROCm-in-WSL2 is untested here |

⛳ **The flags are compared against `docs/PALACE_GPU_BUILD.md`.** A recipe that
lives in two places drifts; this makes the doc unable to be wrong without the
gate going red. That is the rule this project adopted after a flag list drifted
by three flags in an ungated README copy.

⚠ **It must never claim CUDA is validated.** No machine this project owns has an
NVIDIA card. The plan says so in its own reason string, and the gate asserts it
keeps saying so.

FAST tier — pure python, no GPU, no solver, no FreeCAD.

Run:  python3 tests/validation/palace_gpu_plan.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from emstudio.setup.solvers import (                          # noqa: E402
    BACKENDS, PALACE_GPU_DOC, palace_gpu_plan)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []

AMD = [{"vendor": "AMD", "arch": "gfx1100", "name": "Navi 31"}]
NVIDIA = [{"vendor": "NVIDIA", "arch": "sm_89", "name": "RTX 4090"}]
INTEL = [{"vendor": "Intel", "arch": "xe", "name": "Arc"}]


def check(msg, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + msg + (" — " + detail if detail else ""))
    if not ok:
        FAILURES.append(msg)


def main():
    print("== Palace GPU build advice, all three platforms ==")

    # --- 1. macOS: a LIMIT, not a gap ------------------------------------
    mac = palace_gpu_plan(gpus=AMD, platform="darwin")
    check("macOS reports GPU as unsupported", not mac["supported"])
    check("...and does NOT dangle it as coming later",
          "not yet" not in mac["reason"].lower()
          and "future" not in mac["reason"].lower(),
          "a promise nobody can keep is worse than a plain no")
    check("...and names the real cause (Palace has no Metal/SYCL path)",
          "CUDA" in mac["reason"] and "HIP" in mac["reason"])
    check("...and still points macOS users at the CPU path",
          "CPU" in mac["reason"])

    # ⚠ NEGATIVE CONTROL on the platform split: macOS must not be reached by
    # the Linux branch just because os.name says "posix" on both.
    lin = palace_gpu_plan(gpus=AMD, platform="linux")
    check("NEGATIVE CONTROL: the same GPU on Linux IS supported",
          lin["supported"] and not mac["supported"],
          "proves the darwin branch is a real branch, not dead code")

    # --- 2. Windows: WSL2, and honest about what is untested --------------
    win = palace_gpu_plan(gpus=NVIDIA, platform="nt")
    check("Windows reports GPU as not directly supported", not win["supported"])
    check("...and explains it is a WSL2 route", "WSL2" in win["reason"])
    check("...and does not claim ROCm under WSL2",
          "not a route" in win["reason"] or "not tested" in win["reason"]
          or "untested" in win["reason"])

    # --- 3. no GPU, and an unsupported vendor ------------------------------
    none = palace_gpu_plan(gpus=[], platform="linux")
    check("no GPU detected -> unsupported, with a reason",
          not none["supported"] and bool(none["reason"]))
    intel = palace_gpu_plan(gpus=INTEL, platform="linux")
    check("a non-CUDA/non-HIP vendor is refused by NAME",
          not intel["supported"] and "Intel" in intel["reason"])

    # --- 4. NVIDIA: flags offered, validation NOT claimed ------------------
    nv = palace_gpu_plan(gpus=NVIDIA, platform="linux")
    check("NVIDIA on Linux is supported", nv["supported"])
    check("...with the CUDA flag and the arch",
          any("PALACE_WITH_CUDA=ON" in f for f in nv["flags"])
          and any("CUDA_ARCHITECTURES=89" in f for f in nv["flags"]),
          " ".join(nv["flags"][-2:]))
    check("...and says plainly that CUDA is UNVALIDATED here",
          "NOT been run on hardware" in nv["reason"],
          "no NVIDIA card exists on any machine this project owns")

    # --- 5. AMD: the exact flags that were PROVEN to work ------------------
    amd = palace_gpu_plan(gpus=AMD, platform="linux")
    check("AMD on Linux is supported", amd["supported"])
    need = ["-DPALACE_WITH_HIP=ON", "-DCMAKE_HIP_ARCHITECTURES=gfx1100",
            "-DBUILD_SHARED_LIBS=ON", "-DPALACE_WITH_MAGMA=OFF"]
    for f in need:
        check("AMD flags include " + f, f in amd["flags"])
    check("AMD sets ROCM_DIR to the ROOT, never lib/llvm",
          any(f.startswith("-DROCM_DIR=") and not f.endswith("/lib/llvm")
              for f in amd["flags"]),
          "this is the defect that produces a CPU-only libCEED SILENTLY")
    check("AMD overrides the C++ compiler with ROCm's clang++",
          any("CMAKE_CXX_COMPILER=" in f and "clang++" in f for f in amd["flags"]),
          "MFEM compiles itself as HIP; GNU g++ cannot")
    check("AMD still declares the source patch it cannot express as a flag",
          bool(amd["patch"]) and "rocsparse" in amd["patch"])

    # --- 6. THE ANTI-DRIFT CHECK: flags must appear in the doc -------------
    doc_path = os.path.join(_ROOT, PALACE_GPU_DOC)
    check("the recipe document exists where the code says it is",
          os.path.isfile(doc_path), PALACE_GPU_DOC)
    if os.path.isfile(doc_path):
        doc = open(doc_path, encoding="utf-8").read()
        missing = [f.split("=")[0] for f in amd["flags"]
                   if f.split("=")[0] not in doc]
        check("every AMD flag the code emits is documented",
              not missing, "undocumented: %r" % (missing,) if missing else "")
        missing_nv = [f.split("=")[0] for f in nv["flags"]
                      if f.split("=")[0] not in doc]
        check("every NVIDIA flag the code emits is documented",
              not missing_nv, "undocumented: %r" % (missing_nv,) if missing_nv else "")
        check("the doc records the artefact check, not just the build log",
              "nm -D" in doc and "libamdhip64" in doc,
              "a HIP build that succeeded can still be CPU-only")
        check("the doc says CUDA is untested here",
              "UNTESTED" in doc.upper())
        check("the doc covers all three platforms",
              "macOS" in doc and "Windows" in doc.replace("windows", "Windows"))

    # --- 7. the installer hint must lead a user to it ---------------------
    hint = BACKENDS["palace"].manual_hint
    check("the Palace install hint warns the default build is CPU-ONLY",
          "CPU-ONLY" in hint.upper())
    check("...and names both GPU flags",
          "PALACE_WITH_CUDA" in hint and "PALACE_WITH_HIP" in hint)
    check("...and points at the recipe", PALACE_GPU_DOC in hint)

    # --- 8. missing prerequisites are REPORTED, not discovered mid-build ---
    # The plan probes for hipcc/rocminfo/nvcc up front. On a box without them
    # the list must be non-empty AND each entry must say how to get it — a bare
    # "missing" that does not help is the failure this whole function prevents.
    for plan in (amd, nv):
        for what, how in plan["missing"]:
            check("missing prerequisite '%s' comes with a fix" % what,
                  bool(how) and len(how) > 20, how[:60])
    print("  ..    prerequisites missing on this box: %d (0 is normal here)"
          % (len(amd["missing"]) + len(nv["missing"])))

    if FAILURES:
        print("PALACE GPU PLAN GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("PALACE GPU PLAN GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
