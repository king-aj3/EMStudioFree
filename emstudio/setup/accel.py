# SPDX-License-Identifier: LGPL-2.1-or-later
"""Accelerator (GPU) and parallel-capability detection.

**Why this module exists.** EMStudio added a ``Device = CPU | GPU`` choice to
the Palace solver, and a choice the product cannot honour is worse than no
choice at all — that is the exact defect class v1.4.0 spent its release notes
on (a settable field the writers silently discarded). Palace's GPU support is a
**compile-time** decision: a binary built without CUDA or HIP accepts
``Solver.Device = "GPU"``, prints a note, and runs on the CPU anyway. The user
sees a solve that "worked" and never learns their GPU was never touched.

So EMStudio must answer two INDEPENDENT questions before it offers GPU:

1. **Is there a GPU here at all**, and which vendor's API drives it?
2. **Was the installed solver BUILT to use it?**

Both are answered by probing, never by assuming — because the machine this
ships to is not the machine it was written on. AJ's box is an AMD RX 7900 XTX
on ROCm 6.4; a user's may be NVIDIA, may be an Apple M-series with neither, may
be a headless server with no GPU, or may have the hardware and a CPU-only
solver build. All four must produce an honest answer.

⛳ **Nothing here installs, builds or changes anything.** It reports. The
decision of what to do about a missing capability belongs to the user, and the
UI's job is to make the situation legible — "you have a GPU but this Palace
build cannot use it" is a far more useful sentence than a silent fallback.

⚠ **A GPU being present says nothing about it being USABLE.** It may be busy
(this box shares its GPU with a local LLM), may lack the runtime, or may be a
display adapter with no compute stack. `detect_gpus` reports what it can see
and labels how it saw it; it does not promise a solve will be faster.
"""

from __future__ import annotations

import os
import subprocess
import sys

from emstudio import procutil

#: How long any probe may take. These run while a dialog is open, so a hung
#: vendor tool must not hang the GUI. Generous enough for a cold `nvidia-smi`
#: (which can take seconds on first call) and short enough not to be noticed.
_PROBE_TIMEOUT_S = 8


def _run(argv):
    """Run a probe, returning stdout or "" — never raising.

    A missing tool is the NORMAL case on most machines and must not be an
    error: a box with no NVIDIA driver has no `nvidia-smi`, and that is
    information, not a fault.
    """
    try:
        out = subprocess.run(argv, capture_output=True, text=True,
                             timeout=_PROBE_TIMEOUT_S,
                             creationflags=procutil.CREATE_NO_WINDOW)
    except Exception:
        return ""
    return (out.stdout or "") + (out.stderr or "")


def detect_gpus():
    """[{vendor, name, arch, api, how}] for every accelerator we can see.

    ``how`` records WHICH probe produced the row, so a surprising answer can be
    traced to its source rather than argued about.
    """
    found = []

    # --- AMD / ROCm -------------------------------------------------------
    # rocminfo carries the gfx architecture, which is what a HIP build must be
    # compiled for -- gfx1100 code does not run on gfx906. Reporting the arch
    # is what lets a user check their Palace was built for THEIR card.
    rocm = _run(["rocminfo"])
    if "gfx" in rocm:
        archs = []
        for line in rocm.splitlines():
            s = line.strip()
            if s.startswith("Name:") and "gfx" in s:
                a = s.split(":", 1)[1].strip()
                if a.startswith("gfx") and a not in archs:
                    archs.append(a)
        names = []
        smi = _run(["rocm-smi", "--showproductname"])
        for line in smi.splitlines():
            if "Card model" in line or "Card series" in line:
                names.append(line.split(":")[-1].strip())
        for i, arch in enumerate(archs):
            found.append({
                "vendor": "AMD",
                "name": names[i] if i < len(names) else "AMD GPU",
                "arch": arch,
                "api": "HIP/ROCm",
                "how": "rocminfo + rocm-smi",
            })

    # --- NVIDIA / CUDA ----------------------------------------------------
    nv = _run(["nvidia-smi",
               "--query-gpu=name,compute_cap",
               "--format=csv,noheader"])
    if nv and "," in nv and "not found" not in nv.lower():
        for line in nv.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and parts[0]:
                found.append({
                    "vendor": "NVIDIA",
                    "name": parts[0],
                    "arch": "sm_" + parts[1].replace(".", ""),
                    "api": "CUDA",
                    "how": "nvidia-smi",
                })
    return found


#: Shared-library names that prove a binary was LINKED against a GPU runtime.
#: This is the honest test: a CPU-only build simply does not carry them.
_GPU_LIBS = {
    "HIP": ("libamdhip64", "libhipblas", "librocsparse"),
    "CUDA": ("libcudart", "libcublas", "libcusparse"),
}


def solver_gpu_backend(binary_path):
    """"HIP", "CUDA" or "" — what GPU runtime this binary is linked against.

    ⚠⚠ **This is the question that actually matters**, and it is NOT the same
    as "is a GPU present". Palace, MFEM and hypre all decide GPU support at
    COMPILE time. A stock CPU build accepts ``Device = GPU``, notes the
    fallback in its log and solves on the CPU — so asking the config, or asking
    the hardware, both give the wrong answer. Asking the BINARY does not.

    Uses `ldd` on posix. On Windows there is no equivalent that is worth
    trusting, so the answer is "" (unknown) and the UI must say so rather than
    guess — an unprovable capability must not masquerade as an absent one, the
    same rule `_lib_present` follows.
    """
    if not binary_path or not os.path.isfile(binary_path):
        return ""
    if os.name == "nt" or sys.platform == "darwin":
        return ""
    # Palace ships a wrapper script plus a real ELF beside it; probe both, and
    # anything the wrapper obviously points at.
    candidates = [binary_path]
    d = os.path.dirname(binary_path)
    for extra in ("palace-x86_64.bin", "palace-arm64.bin"):
        p = os.path.join(d, extra)
        if os.path.isfile(p):
            candidates.append(p)
    for path in candidates:
        out = _run(["ldd", path])
        for api, libs in _GPU_LIBS.items():
            if any(lib in out for lib in libs):
                return api
    return ""


def accel_report(binary_path=None):
    """One dict describing what this machine can actually accelerate.

    Consumed by Solver Setup and by the Palace solver's Device property. Keys:
      gpus            — list from :func:`detect_gpus`
      solver_backend  — "HIP" / "CUDA" / "" from :func:`solver_gpu_backend`
      gpu_usable      — True only when BOTH a GPU and a matching solver build
                        were found. Anything less is False, deliberately.
      why             — a sentence a user can act on.
      cpu_count       — cores, for the MPI-rank default.
    """
    gpus = detect_gpus()
    backend = solver_gpu_backend(binary_path) if binary_path else ""
    try:
        cores = os.cpu_count() or 1
    except Exception:
        cores = 1

    if not gpus and not backend:
        why = ("No GPU detected and the solver is a CPU build — CPU solving "
               "is the only option, which is normal and fine.")
        usable = False
    elif gpus and not backend:
        why = ("A {0} ({1}) is present, but this solver binary is NOT built "
               "with GPU support, so Device=GPU would silently run on the CPU. "
               "Rebuild the solver with CUDA or HIP enabled to use it."
               .format(gpus[0]["vendor"], gpus[0]["name"]))
        usable = False
    elif backend and not gpus:
        why = ("The solver is built with {0}, but no GPU was detected here. "
               "It will fall back to CPU.".format(backend))
        usable = False
    else:
        vendors = {g["vendor"] for g in gpus}
        match = ("HIP" in backend and "AMD" in vendors) or \
                ("CUDA" in backend and "NVIDIA" in vendors)
        usable = bool(match)
        why = ("{0} ({1}, {2}) with a {3} solver build — GPU solving is "
               "available.".format(gpus[0]["name"], gpus[0]["arch"],
                                   gpus[0]["api"], backend)) if match else \
              ("Solver is built with {0} but the GPU present is {1}. These do "
               "not match, so it will run on the CPU."
               .format(backend, "/".join(sorted(vendors))))
    return {"gpus": gpus, "solver_backend": backend, "gpu_usable": usable,
            "why": why, "cpu_count": cores}


def default_ranks(cores=None):
    """A safe default MPI rank count for this machine.

    Half the cores, at least 1, capped at 16. Deliberately NOT every core:
    solvers are memory-hungry per rank, the box is usually also running FreeCAD
    (and here, an LLM on the GPU), and an oversubscribed run is SLOWER than a
    serial one because ranks contend for bandwidth. Past ~16 ranks FEM scaling
    is usually bounded by memory bandwidth rather than cores anyway.
    """
    if cores is None:
        try:
            cores = os.cpu_count() or 1
        except Exception:
            cores = 1
    return max(1, min(16, int(cores) // 2))
