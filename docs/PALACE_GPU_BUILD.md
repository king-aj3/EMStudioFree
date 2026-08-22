# Building Palace with GPU support

EMStudio detects a GPU and offers `Device = GPU` on a Palace solver **only when
the Palace binary it resolves is actually linked against a GPU runtime**
(`emstudio/setup/accel.py`). That check is deliberately strict: a `Device = GPU`
request that silently ran on the CPU would be a setting that changes nothing,
and the number it produced would look computed.

Palace's own build is CPU-only by default, so this page is what turns the option
from "offered" into "usable". Everything below was **measured on 2026-08-22**,
not transcribed from documentation.

---

## Which platforms can do this at all — they are NOT alike

⚠⚠ `os.name` is `"posix"` on macOS **and** Linux. This is a case where treating
them alike would ship a falsehood, so all three are stated separately and
`emstudio.setup.solvers.palace_gpu_plan()` branches on all three.

| platform | Palace itself | GPU solving | why |
|---|---|---|---|
| **Linux** | source build | ✅ **CUDA or HIP** | the recipes below; HIP measured on gfx1100 |
| **macOS** | source build (supported) | ❌ **never** | Palace declares only `PALACE_WITH_CUDA` and `PALACE_WITH_HIP` — verified by reading its `CMakeLists.txt`, there is no Metal, SYCL or OpenCL path — and Apple silicon has neither CUDA nor ROCm. **This is a limit of the solver, not a gap waiting to be closed.** Macs use the CPU path, which is fully supported |
| **Windows** | **WSL2 only** — there is no native Windows Palace | ⚠ **inside WSL2** | NVIDIA supports CUDA under WSL2, so the CUDA recipe below applies *within the distribution*. AMD ROCm under WSL2 is **not a route this project has tested** and is therefore not claimed |

⛳ EMStudio does not make you find this out the hard way.
`palace_gpu_plan()` reports, for the machine in front of you, whether a GPU
build is possible, the exact flags, the patch still owed, and **which
prerequisites are missing with how to get each one** — checked *before* a
30–60 minute compile rather than discovered halfway through it.

---

## NVIDIA (CUDA)

```bash
cmake -S ~/opt/palace-src -B ~/opt/palace-src/build \
      -DCMAKE_INSTALL_PREFIX=$HOME/opt/palace \
      -DPALACE_WITH_CUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=<your sm_XX, e.g. 89 for Ada>
cmake --build ~/opt/palace-src/build -j $(nproc)
```

⚠ **UNTESTED HERE, AND SAID SO ON PURPOSE.** There is no NVIDIA card on any
machine this project owns. CUDA is Palace's own well-trodden path and the four
defects documented below are all AMD-specific, so this is expected to work as
written — but "expected" is not "measured", and it must not be described as
validated until somebody runs it.

---

## AMD (HIP/ROCm) — three flags and one patch

**Measured working** on a Radeon RX 7900 XTX (gfx1100, RDNA3) with ROCm 6.4.2:

```bash
ROCM=/opt/rocm-6.4.2                      # the ROOT, not lib/llvm — see (1)

cmake -S ~/opt/palace-src -B ~/opt/palace-src/build-hip \
      -DCMAKE_INSTALL_PREFIX=$HOME/opt/palace \
      -DPALACE_WITH_HIP=ON \
      -DCMAKE_HIP_ARCHITECTURES=gfx1100 \
      -DROCM_DIR=$ROCM \
      -DCMAKE_CXX_COMPILER=$ROCM/lib/llvm/bin/clang++ \
      -DBUILD_SHARED_LIBS=ON \
      -DPALACE_WITH_MAGMA=OFF
cmake --build ~/opt/palace-src/build-hip -j $(nproc)
```

plus **one source patch** (4 lines) described in (2).

### Why each flag is there — every one of these cost a failed build

**(1) `-DROCM_DIR=$ROCM` — and this is the dangerous one, because without it the
build SUCCEEDS and produces a CPU-only libCEED.**
Palace derives `ROCM_DIR` from the HIP compiler's grandparent directory
(`CMakeLists.txt:92-95`). On ROCm ≥ 6 CMake selects
`$ROCM/lib/llvm/bin/clang++`, so the derivation lands on `$ROCM/lib/llvm` —
a directory with **no `lib/libamdhip64.so`**. libCEED's Makefile probes for
exactly that file and, finding nothing, **silently drops every `/gpu/hip/*`
backend** without a warning.

⛳ **Gate this on the artefact, never on the build log**, because the build log
says nothing:

```bash
nm -D --defined-only ~/opt/palace/lib/libceed.so | grep -ci hip     # must be > 0
ldd ~/opt/palace/lib/libceed.so | grep -c libamdhip64               # must be 1
```

Measured: **0 → 14** HIP symbols once `ROCM_DIR` is right.

**(2) The MFEM/rocsparse patch.** ROCm ≥ 6 exports only *namespaced* CMake
targets (`roc::rocsparse`), while MFEM is told to look for the bare name, so its
configure dies with

```
*** rocsparse: unknown target. Please set rocsparse_TARGET_NAMES.
```

There is no user-facing hook to append MFEM options, so this one needs a source
edit. In `cmake/ExternalMFEM.cmake`, inside `if(PALACE_WITH_HIP)`, alongside
`"-DHYPRE_REQUIRED_PACKAGES=rocsparse"`:

```cmake
      "-Drocsparse_TARGET_NAMES=roc::rocsparse"
      "-Dhipblas_TARGET_NAMES=roc::hipblas"
      "-Drocblas_TARGET_NAMES=roc::rocblas"
```

**(3) `-DCMAKE_CXX_COMPILER=$ROCM/lib/llvm/bin/clang++`.** With
`MFEM_USE_HIP=YES`, MFEM compiles its *whole* C++ library as HIP —

```
CXX_FLAGS = -fPIC -O3 -DNDEBUG -std=c++17 -x hip --offload-arch=gfx1100
```

— but the superbuild forwards the top-level `CMAKE_CXX_COMPILER`
(`ExternalMFEM.cmake:87`), which defaults to `/usr/bin/c++`. GNU g++ understands
neither `-x hip` nor `--offload-arch`, so every MFEM source fails with
`unrecognized command-line option '--offload-arch=gfx1100'`. Setting the
top-level compiler fixes MFEM without a patch.

**(4) `-DBUILD_SHARED_LIBS=ON`.** PETSc compiles its HIP sources with its own HIP
compiler, which sees neither `COPTFLAGS` nor `CXXOPTFLAGS` — so the `-fPIC` that
reaches every other object never reaches `cupmcontext.o`. With static libraries
the resulting archive cannot be linked into a PIE and SLEPc dies at its first
link test:

```
relocation R_X86_64_32 against hidden symbol ... can not be used when making a
PIE object   ->   ERROR: Unable to link with PETSc
```

⚠ `--with-pic=1` is **refused** alongside `--with-shared-libraries=0` — PETSc
tells you to supply the flag via `CFLAGS`/`CXXFLAGS` instead. Shared libraries
sidestep the whole problem. (If you must build static, patch
`cmake/ExternalSLEPc.cmake` to append `"HIPFLAGS+=-fPIC"` — the `+=` form
*appends* to PETSc's defaults rather than replacing them.)

**(5) `-DPALACE_WITH_MAGMA=OFF`, and it is not optional on RDNA3.** MAGMA's
`VALID_GFXS` list stops at **gfx1033**, so gfx1100 is not supported on any
released MAGMA. Leaving MAGMA on produces a configure that appends no
`--offload-arch` and quietly builds nothing useful.

### ⚠ Consequence of (5): the default libCEED backend will abort

Palace's default backend on HIP is `/gpu/hip/magma` (`palace/main.cpp:88-91`),
which does not exist in a MAGMA-less build. A run dies with:

```
Backend not currently compiled: /gpu/hip/magma
```

Set the backend explicitly in the Palace config:

```json
"Solver": { "Device": "GPU", "Backend": "/gpu/hip/shared" }
```

⚠⚠ **DO NOT hard-code that string into a generated config.** Palace chooses the
backend from the device it detects — CUDA → `/gpu/cuda/magma`, HIP →
`/gpu/hip/magma`, otherwise `/cpu/self` — so a literal `/gpu/hip/shared` would
**abort on a CPU-only or NVIDIA machine** and would discard the tuned backend on
a CDNA/MI card where MAGMA works. If EMStudio ever emits it, it must be from a
probe of the installed binary's available backends, never a constant.

**Which HIP backend to use, measured on the upstream `cylinder/cavity_pec`
example at 353 208 unknowns, against the same case on CPU:**

| backend | agreement with CPU | note |
|---|---|---|
| `/gpu/hip/gen` (Palace's default shape) | **83–939 ppm WRONG**, backward error 1e-5 vs 1e-10, and it **splits a degenerate pair** | broken on RDNA3 |
| `/gpu/hip/ref` | **exact** — 12 significant figures | reference implementation |
| `/gpu/hip/shared` | **exact** — 12 significant figures | the one to use |

---

## Verifying the build actually uses the GPU

Three checks, in order of how easily each is faked:

```bash
# 1. the artefact carries HIP at all (this is the one that fails silently)
nm -D --defined-only ~/opt/palace/lib/libceed.so | grep -ci hip

# 2. the solver binary links the runtime
ldd ~/opt/palace/bin/palace-x86_64.bin | grep -E 'libamdhip64|libcudart'

# 3. a real run says so
palace -np 1 case.json | grep -E 'Detected .* device|Device configuration|libCEED backend'
#   Detected 1 HIP device
#   Device configuration: hip,cpu
#   libCEED backend: /gpu/hip/shared
```

⛳ And the check that matters most: **solve the same case on CPU and GPU and
compare.** A GPU build that runs is not a GPU build that is right — that is
exactly how `/gpu/hip/gen` was caught.

---

## What to expect for performance — read this before promising anything

Measured on this box: Threadripper 3990X (64 cores / 128 threads) + RX 7900 XTX,
`cylinder/cavity_pec`, order 3, 353 208 ND unknowns, 5 eigenmodes.
GPU on 1 rank against CPU on 16 ranks:

| | GPU (1 rank) | CPU (16 ranks) |
|---|---|---|
| preconditioner (the dominant solver cost) | **67.4 s** | 158.9 s |
| **total, solve only** | **165.1 s** | 199.6 s |
| peak memory | **2.3 GB** | 36.7 GB |
| ParaView field write (same case, `Save` on) | 127.6 s | 9.0 s |
| total *with* field output | 292.1 s | **208.2 s** |

* **On the solve itself the GPU wins**: 1.21× faster overall and **2.4× faster
  on the preconditioner**, against SIXTEEN ranks of a 64-core Threadripper.
* **And it uses 16× less memory** — 2.3 GB against 36.7 GB, because each MPI
  rank carries its own copy. On a memory-constrained machine that is the
  difference between a case running and not running at all.
* ⚠ **With ParaView field output enabled the GPU LOSES overall**, 292 s to
  208 s, entirely to a 127 s field write that costs the CPU 9 s. That is
  device→host transfer, not solver speed — but it is real, and a user who
  writes fields on every run will not see the solve-time win.

⚠ **These ratios are a property of THIS machine and do not generalise.** A
64-core Threadripper is an unusually strong CPU opponent — the GPU beating 16 of
its ranks is a stronger result than it looks, and a user with 8 cores and the
same card would see a much larger margin. But the reverse is also true: never
quote a speed-up without naming the CPU it was measured against.
⛳ The claim EMStudio can make safely is capability, not a multiplier: GPU
solving is detected, offered when it can be honoured, and refused with a reason
when it cannot.
