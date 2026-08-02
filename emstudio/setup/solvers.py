# SPDX-License-Identifier: LGPL-2.1-or-later
"""Backend solver discovery.

EMStudio drives external open-source solvers as isolated subprocesses (the CENOS
licensing model: we never link or bundle GPL solver code). Before a backend can run we
must locate its executable. This module is deliberately Qt-free and GUI-free so it can
be exercised headlessly (``freecadcmd``, plain pytest) and reused by the preferences
page and the guided installer later.

Resolution order for each binary:

1. An explicit path saved in FreeCAD preferences
   (``User parameter:BaseApp/Preferences/Mod/EMStudio/<key>``), when FreeCAD is present.
2. The ``EMSTUDIO_<KEY>`` environment variable.
3. A plain ``shutil.which`` lookup on ``PATH``.
4. A short list of common platform install locations.

Nothing here raises on a missing solver; callers inspect the returned
:class:`SolverInfo` and surface guidance through the UI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


def _is_mac():
    """True on macOS. Read at CALL time so tests can patch ``sys.platform``.

    macOS is ``os.name == "posix"``, so every ``if os.name == "nt" ... else``
    in this module used to hand Mac users Debian apt commands. That is not a
    cosmetic wording bug: `sudo apt install …` cannot run on macOS at all, so
    Solver Setup was unusable there. Reported on the FreeCAD forum, 2026-08-01.
    """
    return sys.platform == "darwin"

#: Directories worth probing on macOS regardless of which backend we are after.
#: Homebrew installs to /opt/homebrew (Apple Silicon) or /usr/local (Intel), and
#: **FreeCAD launched from Finder does not inherit your shell PATH** — so
#: `brew install gmsh` could succeed while Detect Solvers still said MISSING.
#: Telling the user to fix their PATH was the 0.77.1 answer; looking in the
#: right place is the better one. MacPorts' /opt/local/bin is here for the same
#: reason (nec2c has a MacPorts port but no Homebrew formula).
MACOS_PROBE_DIRS = (
    "/opt/homebrew/bin",        # Homebrew, Apple Silicon
    "/usr/local/bin",           # Homebrew, Intel
    "/opt/local/bin",           # MacPorts
)


def _platform_dirs():
    """Extra probe directories that apply to every backend on this platform."""
    return MACOS_PROBE_DIRS if _is_mac() else ()


# Preferences group used for per-backend binary overrides.
PREF_GROUP = "User parameter:BaseApp/Preferences/Mod/EMStudio"


@dataclass(frozen=True)
class Prereq:
    """A build/runtime prerequisite that must exist before installing a backend.

    ``kind`` selects the probe:
      * ``bin``  — an executable on PATH (``token`` = program name).
      * ``lib``  — a shared library (``token`` = library stem, e.g. ``openblas``).
      * ``pip``  — an importable python module (``token`` = module name).
    ``apt`` is the Debian/Ubuntu/Mint package that provides it, ``brew`` the
    Homebrew formula; ``why`` explains the failure it prevents (these are the
    install pitfalls learned the hard way). Leave ``brew`` empty when no
    formula is known — an invented formula name is worse than silence, because
    the user runs it, it fails, and they no longer trust any of the guidance.
    """

    name: str
    kind: str  # 'bin' | 'lib' | 'pip'
    token: str
    apt: str = ""
    why: str = ""
    brew: str = ""


@dataclass(frozen=True)
class Backend:
    """Static description of a solver backend EMStudio can drive."""

    key: str  # stable identifier, e.g. "openems"
    label: str  # human name, e.g. "openEMS (FDTD)"
    method: str  # numerical method, e.g. "FDTD"
    executables: tuple  # candidate binary names, first found wins
    version_args: tuple = ("--version",)
    # Package hints for the guided installer, per platform family.
    apt_package: str = ""
    brew_package: str = ""  # Homebrew formula, ONLY where one really exists
    pip_package: str = ""
    manual_hint: str = ""  # free-text instructions when no package exists
    homepage: str = ""
    # Extra directories to probe beyond PATH (platform-specific install spots).
    extra_dirs: tuple = ()
    # Source-build prerequisites, checked BEFORE a build so failures like the
    # missing-OpenBLAS one surface up front instead of mid-compile.
    prerequisites: tuple = ()
    # True when there is no distro package — the backend is built from source.
    source_build: bool = False


@dataclass
class SolverInfo:
    """Result of probing a :class:`Backend` on this machine."""

    backend: Backend
    path: str = ""  # resolved absolute path, or "" if not found
    version: str = ""  # first line of `--version` output, best effort
    source: str = ""  # how it was found: pref | env | path | probe
    found: bool = field(init=False, default=False)

    def __post_init__(self):
        self.found = bool(self.path)


# --- Backend registry ------------------------------------------------------
# Phase 1 ships openEMS + NEC2; Elmer/Palace are declared now so the preferences
# page and installer enumerate the full roadmap, even before their writers exist.

BACKENDS = {
    "openems": Backend(
        key="openems",
        label="openEMS (FDTD)",
        method="EC-FDTD",
        executables=("openEMS", "openEMS.sh", "openems"),
        version_args=("--version",),
        # Dropped from Ubuntu 24.04+/Mint 22 archives — source build is the
        # official path on modern Linux; Windows has prebuilt zips.
        manual_hint=(
            "Linux: build from source — git clone --recursive "
            "https://github.com/thliebig/openEMS-Project.git && "
            "./update_openEMS.sh ~/opt/openEMS --python\n"
            "Windows: prebuilt zip from https://www.openems.de/"
        ),
        homepage="https://www.openems.de/",
        extra_dirs=(
            os.path.expanduser("~/opt/openEMS/bin"),
            r"C:\opt\openEMS",
            r"C:\openEMS",
        ),
        source_build=True,
        prerequisites=(
            Prereq("C++ toolchain", "bin", "g++", "build-essential"),
            Prereq("CMake", "bin", "cmake", "cmake", brew="cmake"),
            Prereq("git", "bin", "git", "git", brew="git"),
            Prereq("HDF5 dev", "lib", "hdf5", "libhdf5-dev", brew="hdf5"),
            Prereq("VTK 9 dev", "lib", "vtkCommonCore", "libvtk9-dev", brew="vtk"),
            Prereq("Boost dev", "lib", "boost_system", "libboost-all-dev", brew="boost"),
            Prereq("CGAL dev", "lib", "gmp", "libcgal-dev libgmp-dev", brew="cgal gmp"),
            # NO brew formula: homebrew-core dropped TinyXML v1 and carries only
            # tinyxml2, which is a DIFFERENT API — openEMS wants v1, so naming
            # tinyxml2 here would produce a build that fails later and further in.
            Prereq("TinyXML dev", "lib", "tinyxml", "libtinyxml-dev",
                   why="macOS: not in homebrew-core (only tinyxml2, a different "
                       "API) — build TinyXML v1 from source or use a tap"),
            Prereq("python venv", "bin", "python3", "python3-venv python3-setuptools cython3",
                   "PEP 668: python modules must install into a venv on Ubuntu 24.04+"),
        ),
    ),
    "nec2": Backend(
        key="nec2",
        label="NEC2 (MoM wire antennas)",
        method="MoM",
        executables=("nec2c", "nec2", "nec2++"),
        version_args=("-h",),  # nec2c has no --version; -h returns quickly
        apt_package="nec2c",
        homepage="https://www.qsl.net/5b4az/",
    ),
    "fasthenry": Backend(
        key="fasthenry",
        label="FastHenry (quasi-static wire/bundle impedance)",
        method="PEEC/filament",
        executables=("fasthenry",),
        version_args=("-help",),
        # Not packaged in Ubuntu 24.04/Mint 22 — small C source build. FastHenry
        # is K&R-era C and needs THREE suppressions on any modern compiler:
        #   -fcommon                          legacy common-symbol linkage (GCC >= 10)
        #   -Wno-implicit-int                 `main(argc, argv)` with no return type
        #   -Wno-implicit-function-declaration  calls before declaration
        # The last two became ERRORS by default in Apple clang 15 / GCC 14, which
        # is how a build that worked for years starts failing: 20 errors in
        # induct.c. Reported on macOS 26.5 (arm64, clang) 2026-08-01.
        manual_hint=(
            "Build from source (LGPL): git clone "
            "https://github.com/ediloren/FastHenry2.git && cd FastHenry2/src/fasthenry "
            "&& make fasthenry CFLAGS=\"-O -DFOUR -m64 -fcommon -Wno-implicit-int -Wno-implicit-function-declaration\""
        ),
        homepage="https://www.fastfieldsolvers.com/",
        extra_dirs=(os.path.expanduser("~/opt/FastHenry2/bin"),),
        source_build=True,
        prerequisites=(
            Prereq("C toolchain", "bin", "cc", "build-essential"),
            Prereq("git", "bin", "git", "git", brew="git"),
            # the hard-won one: default -fno-common in GCC>=10 breaks the link
            Prereq("(build flag)", "bin", "cc", "",
                   "MUST compile with CFLAGS containing -fcommon (GCC >= 10, or the "
                   "link fails with 'multiple definition of timestuff') PLUS "
                   "-Wno-implicit-int -Wno-implicit-function-declaration, which "
                   "Apple clang 15+ and GCC 14+ turn into hard errors on this "
                   "K&R-era source"),
        ),
    ),
    "elmer": Backend(
        key="elmer",
        label="Elmer (FEM magnetodynamics / VectorHelmholtz)",
        method="FEM",
        executables=("ElmerSolver", "ElmerSolver_mpi"),
        version_args=("--version",),
        apt_package="elmerfem-csc",
        manual_hint=(
            "Needs the official CSC PPA first:\n"
            "sudo add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa && "
            "sudo apt update && sudo apt install -y elmerfem-csc"
        ),
        homepage="https://www.elmerfem.org/",
    ),
    "palace": Backend(
        key="palace",
        label="Palace (FEM full-wave, eigenmode, AMR)",
        method="FEM",
        executables=("palace",),
        version_args=("--help",),
        # No distro package — CMake superbuild, no sudo needed:
        manual_hint=(
            "Build from source (Apache-2.0): git clone "
            "https://github.com/awslabs/palace.git ~/opt/palace-src && cmake -S "
            "~/opt/palace-src -B ~/opt/palace-src/build "
            "-DCMAKE_INSTALL_PREFIX=$HOME/opt/palace && cmake --build "
            "~/opt/palace-src/build -j $(nproc)"
        ),
        homepage="https://github.com/awslabs/palace",
        extra_dirs=(
            os.path.expanduser("~/opt/palace/bin"),
            os.path.expanduser("~/opt/palace-src/build/bin"),
        ),
        source_build=True,
        prerequisites=(
            Prereq("C++/Fortran toolchain", "bin", "gfortran", "build-essential gfortran",
                       brew="gcc"),
            Prereq("CMake >= 3.21", "bin", "cmake", "cmake", brew="cmake"),
            Prereq("git", "bin", "git", "git", brew="git"),
            Prereq("MPI", "bin", "mpicc", "libopenmpi-dev openmpi-bin", brew="open-mpi"),
            # the one that bit us: Palace's superbuild requires OpenBLAS
            # specifically, not the reference BLAS
            Prereq("OpenBLAS", "lib", "openblas", "libopenblas-dev",
                   why="Palace's configure fails with 'Could NOT find BLAS' unless "
                       "OpenBLAS (not reference BLAS) is installed",
                   brew="openblas"),
        ),
    ),
    # Meshing/support tools, discovered the same way.
    "gmsh": Backend(
        key="gmsh",
        label="Gmsh (mesh generator)",
        method="mesh",
        executables=("gmsh",),
        version_args=("--version",),
        apt_package="gmsh",
        brew_package="gmsh",
        pip_package="gmsh",
        homepage="https://gmsh.info/",
    ),
}


def _pref_path(key):
    """Return a user-configured binary path from FreeCAD prefs, or ''.

    Import of FreeCAD is done lazily so this module stays usable without it.
    """
    try:
        import FreeCAD  # noqa: PLC0415  (intentional lazy import)
    except Exception:
        return ""
    try:
        params = FreeCAD.ParamGet(PREF_GROUP)
        return params.GetString(key, "")
    except Exception:
        return ""


def _probe_version(path, version_args):
    """Best-effort version string: first output line that carries a digit."""
    try:
        out = subprocess.run(
            [path, *version_args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        text = (out.stdout or out.stderr or "").strip()
        for line in text.splitlines():
            line = line.strip()
            if line and any(c.isdigit() for c in line) and "usage" not in line.lower() \
                    and "option" not in line.lower():
                return line[:70]
        return ""
    except Exception:
        return ""


def find_backend(key):
    """Locate a single backend by registry key. Returns a :class:`SolverInfo`."""
    backend = BACKENDS[key]

    # 1) explicit FreeCAD preference
    pref = _pref_path(key)
    if pref and os.path.isfile(pref) and os.access(pref, os.X_OK):
        return SolverInfo(backend, pref, _probe_version(pref, backend.version_args), "pref")

    # 2) environment override
    env = os.environ.get("EMSTUDIO_" + key.upper(), "")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return SolverInfo(backend, env, _probe_version(env, backend.version_args), "env")

    # 3) PATH lookup on each candidate name
    for name in backend.executables:
        hit = shutil.which(name)
        if hit:
            return SolverInfo(backend, hit, _probe_version(hit, backend.version_args), "path")

    # 4) common platform-specific directories (probe .exe/.bat variants on Windows)
    suffixes = ("", ".exe", ".bat", ".cmd") if os.name == "nt" else ("",)
    for directory in tuple(backend.extra_dirs) + _platform_dirs():
        for name in backend.executables:
            for sfx in suffixes:
                cand = os.path.join(directory, name + sfx)
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    return SolverInfo(
                        backend, cand, _probe_version(cand, backend.version_args), "probe"
                    )

    return SolverInfo(backend, "")


def detect_all():
    """Probe every registered backend. Returns ``{key: SolverInfo}``.

    CAUTION for future preferences UI: detected paths may be EPHEMERAL. Inside the
    FreeCAD AppImage, PATH exposes bundled tools under /tmp/.mount_FreeCAxxxx/ (e.g.
    gmsh), and that mount point changes every launch. Detected paths are safe to USE
    within the current session but must never be auto-persisted to preferences —
    re-detect each session; only user-entered paths belong in prefs.
    """
    return {key: find_backend(key) for key in BACKENDS}


def is_ephemeral_path(path):
    """True if a detected path lives in a transient location (AppImage mount)."""
    return path.startswith("/tmp/.mount_")


def _lib_present(stem):
    """True if a shared library with this stem is registered with the loader."""
    try:
        out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True,
                             timeout=10).stdout
        return ("lib" + stem) in out
    except Exception:
        return False


def check_prereqs(backend):
    """Probe a backend's build prerequisites. Returns list of (Prereq, ok: bool).

    Advisory entries (empty apt AND a why-note, like FastHenry's -fcommon flag)
    always report ok=True — they are surfaced as notes, not blockers.
    """
    results = []
    for p in backend.prerequisites:
        if not p.apt and p.why:
            results.append((p, True))  # advisory note
            continue
        if p.kind == "bin":
            ok = shutil.which(p.token) is not None
        elif p.kind == "lib":
            ok = _lib_present(p.token)
        elif p.kind == "pip":
            try:
                __import__(p.token)
                ok = True
            except Exception:
                ok = False
        else:
            ok = False
        results.append((p, ok))
    return results


def install_plan():
    """Complete machine-readable install report — the guided installer's engine.

    Returns dict:
      found:    [SolverInfo, ...]
      missing:  [{info, apt_line or '', steps, prereqs_ok, missing_prereqs,
                  advisories}, ...]
      apt_line: one combined 'sudo apt install ...' covering every missing
                apt-installable backend AND every missing build prerequisite,
                so a user gets ONE command for the sudo part. Empty off Linux.
      brew_line: the macOS equivalent, 'brew install ...'. Empty off macOS.
    """
    is_win = os.name == "nt"
    is_mac = _is_mac()
    found, missing = [], []
    apt_pkgs = []
    brew_pkgs = []
    for info in detect_all().values():
        if info.found:
            found.append(info)
            continue
        b = info.backend
        if is_mac:
            # macOS: Homebrew for what has a formula, source builds for the
            # rest. Never apt — that was the reported bug.
            prereqs = check_prereqs(b)
            missing_prereqs = [p for p, ok in prereqs if not ok]
            for p in missing_prereqs:
                brew_pkgs.extend(p.brew.split())
            if b.brew_package:
                brew_pkgs.extend(b.brew_package.split())
            missing.append({
                "info": info,
                "steps": install_hint(b),
                "prereqs_ok": not missing_prereqs,
                "missing_prereqs": missing_prereqs,
                "advisories": [p for p, ok in prereqs if ok and p.why and not p.apt],
            })
            continue
        if is_win:
            # Windows: no apt, no from-source build prerequisites — native
            # installers / WSL2 only. Keep the entry free of Linux concepts.
            missing.append({
                "info": info,
                "steps": install_hint(b),
                "prereqs_ok": True,
                "missing_prereqs": [],
                "advisories": [],
            })
            continue
        prereqs = check_prereqs(b)
        missing_prereqs = [p for p, ok in prereqs if not ok]
        advisories = [p for p, ok in prereqs if ok and p.why and not p.apt]
        for p in missing_prereqs:
            apt_pkgs.extend(p.apt.split())
        if b.apt_package and not b.source_build:
            apt_pkgs.extend(b.apt_package.split())
        missing.append({
            "info": info,
            "steps": install_hint(b),
            "prereqs_ok": not missing_prereqs,
            "missing_prereqs": missing_prereqs,
            "advisories": advisories,
        })
    # dedupe, keep order
    seen = set()
    apt_pkgs = [p for p in apt_pkgs if not (p in seen or seen.add(p))]
    seen = set()
    brew_pkgs = [p for p in brew_pkgs if not (p in seen or seen.add(p))]
    return {
        "found": found,
        "missing": missing,
        # apt is a Debian concept — never surfaced on Windows OR macOS
        "apt_line": "" if (is_win or is_mac) else (
            ("sudo apt install -y " + " ".join(apt_pkgs)) if apt_pkgs else ""),
        # ...and brew is a macOS one. Exactly one of these is ever non-empty.
        "brew_line": ("brew install " + " ".join(brew_pkgs))
                     if (is_mac and brew_pkgs) else "",
    }


#: Every Homebrew formula named anywhere in this file, VERIFIED to exist in
#: homebrew-core (checked against formulae.brew.sh/api/formula/<name>.json on
#: 2026-08-02). A gate in tests/smoke.py refuses any `brew=` or `brew_package`
#: outside this set. This exists because `tinyxml` was added here from memory,
#: shipped, and does not exist — the exact failure the macOS fix was FOR: a
#: confident command that cannot run. If you add a formula, curl the API first
#: and add it here in the same commit.
VERIFIED_BREW_FORMULAE = {
    "gmsh", "cmake", "git", "hdf5", "vtk", "boost", "cgal", "gmp",
    "open-mpi", "openblas", "gcc",
}

# macOS install guidance per backend. Homebrew where a formula really exists,
# an honest "build it / see the docs" where it does not. Deliberately NOT a
# copy of the Linux text with apt swapped for brew: most of these have no
# formula at all, and inventing one is how a user ends up with a command that
# fails and guidance they stop believing.
MACOS_HINTS = {
    "openems": "No Homebrew formula. Build from source: xcode-select --install, then "
               "brew install cmake hdf5 vtk boost cgal gmp  (TinyXML v1 is NOT in "
               "homebrew-core — only tinyxml2, a different API — so build it from "
               "source or use a tap), then git clone "
               "--recursive https://github.com/thliebig/openEMS-Project.git && "
               "./update_openEMS.sh ~/opt/openEMS --python",
    "nec2": "No Homebrew formula in homebrew-core. Build the C source (small, quick): "
            "https://www.qsl.net/5b4az/ — or check MacPorts for nec2c.",
    "fasthenry": "No Homebrew formula. Build from source: git clone "
                 "https://github.com/ediloren/FastHenry2.git && cd "
                 "FastHenry2/src/fasthenry && make fasthenry "
                 "CFLAGS=\"-O -DFOUR -m64 -fcommon -Wno-implicit-int "
                 "-Wno-implicit-function-declaration\"  — Apple clang 15+ and GCC 14+ "
                 "make the implicit-* diagnostics errors, so all three flags are "
                 "required, not optional.",
    "elmer": "No Homebrew formula. CSC publishes macOS builds — see "
             "https://www.elmerfem.org/ (Download → macOS), or build with "
             "brew install cmake open-mpi openblas first.",
    "palace": "No Homebrew formula. macOS IS supported by the CMake superbuild: "
              "xcode-select --install, brew install cmake open-mpi openblas gcc, then "
              "git clone https://github.com/awslabs/palace.git ~/opt/palace-src && "
              "cmake -S ~/opt/palace-src -B ~/opt/palace-src/build "
              "-DCMAKE_INSTALL_PREFIX=$HOME/opt/palace && cmake --build "
              "~/opt/palace-src/build -j $(sysctl -n hw.ncpu)",
    "gmsh": "brew install gmsh  — or the official .dmg from https://gmsh.info/",
}

# Windows install guidance per backend (native installers where they exist,
# honest WSL pointers where they don't).
WINDOWS_HINTS = {
    "openems": "Prebuilt Windows zip: https://www.openems.de/ (unzip to C:\\opt\\openEMS). "
               "Python-driven runs are not wired up on native Windows yet — use WSL2 "
               "for the full pipeline.",
    "nec2": "No official Windows build of nec2c — install via WSL2 (sudo apt install "
            "nec2c) or MSYS2.",
    "fasthenry": "FastFieldSolvers ships Windows builds (https://www.fastfieldsolvers.com/), "
                 "but EMStudio's command-line integration currently targets the Linux "
                 "build — use WSL2 for wire/litz cross-checks.",
    "elmer": "Official Windows installer: https://www.elmerfem.org/ (ElmerFEM release "
             "with ElmerSolver + ElmerGrid).",
    "palace": "No native Windows support (Linux/macOS only) — use WSL2.",
    "gmsh": "Official Windows binaries: https://gmsh.info/ — add gmsh.exe to PATH.",
}


def install_report_text():
    """Human-readable installation report (Detect Solvers, docs, CLI).

    Platform-aware: on Windows the apt line is replaced by per-backend Windows
    guidance (native installers where they exist, WSL2 pointers where they don't).
    """
    plan = install_plan()
    if os.name == "nt":
        lines = ["EMStudio solver installation report (Windows)", ""]
        for info in plan["found"]:
            ver = (" — " + info.version) if info.version else ""
            lines.append("  [OK]      {0}: {1}{2}".format(info.backend.label, info.path, ver))
        for m in plan["missing"]:
            b = m["info"].backend
            lines.append("  [MISSING] {0}".format(b.label))
        lines += ["", "Windows install guidance:"]
        for m in plan["missing"]:
            b = m["info"].backend
            lines.append("  {0}: {1}".format(
                b.label, WINDOWS_HINTS.get(b.key, b.homepage or "see documentation")))
        lines += ["", "For the complete 6-backend experience on Windows, install "
                      "FreeCAD + EMStudio inside WSL2 (Ubuntu) — every Linux recipe "
                      "then applies unchanged."]
        return "\n".join(lines)

    if _is_mac():
        lines = ["EMStudio solver installation report (macOS)", ""]
        for info in plan["found"]:
            ver = (" — " + info.version) if info.version else ""
            lines.append("  [OK]      {0}: {1}{2}".format(
                info.backend.label, info.path, ver))
        for m in plan["missing"]:
            lines.append("  [MISSING] {0}".format(m["info"].backend.label))
        if plan["brew_line"]:
            lines += ["", "Homebrew packages (one command):", "  " + plan["brew_line"]]
        lines += ["", "Per-backend guidance:"]
        for m in plan["missing"]:
            b = m["info"].backend
            lines.append("  {0}: {1}".format(
                b.label, MACOS_HINTS.get(b.key, b.homepage or "see documentation")))
        lines += ["", "A compiler is required for the source builds: "
                      "xcode-select --install", ""]
        lines += ["Homebrew itself: https://brew.sh — Apple Silicon installs under "
                  "/opt/homebrew, Intel under /usr/local; make sure that bin "
                  "directory is on PATH before FreeCAD starts."]
        return "\n".join(lines)

    lines = ["EMStudio solver installation report", ""]
    for info in plan["found"]:
        ver = (" — " + info.version) if info.version else ""
        lines.append("  [OK]      {0}: {1}{2}".format(info.backend.label, info.path, ver))
    for m in plan["missing"]:
        b = m["info"].backend
        lines.append("  [MISSING] {0}".format(b.label))
    if plan["apt_line"]:
        lines += ["", "One command covers all missing packages/prerequisites:",
                  "  " + plan["apt_line"]]
    for m in plan["missing"]:
        b = m["info"].backend
        lines += ["", "Then for {0}:".format(b.label),
                  "  " + m["steps"].replace("\n", "\n  ")]
        for p in m["missing_prereqs"]:
            note = (" — " + p.why) if p.why else ""
            mgr, pkg = ("brew", p.brew) if _is_mac() else ("apt", p.apt)
            lines.append("  requires first: {0}{1}{2}".format(
                p.name, (" ({0}: {1})".format(mgr, pkg)) if pkg else "", note))
        for p in m["advisories"]:
            lines.append("  note: {0}".format(p.why))
    return "\n".join(lines)


def install_hint(backend):
    """Return a human-readable install suggestion for a missing backend.

    Platform-segregated: on Windows this returns ONLY the Windows guidance
    (native installer / WSL2), on macOS ONLY the Homebrew/source recipe, and on
    Linux ONLY the apt/pip/source-build recipe. Callers never mix the two.
    """
    if os.name == "nt":
        win = WINDOWS_HINTS.get(backend.key)
        if win:
            return win
        return "Docs:  " + backend.homepage if backend.homepage else \
            "See the backend's documentation to install it."
    if _is_mac():
        parts = []
        if backend.brew_package:
            parts.append("Homebrew:  brew install " + backend.brew_package)
        mac = MACOS_HINTS.get(backend.key)
        if mac:
            parts.append(mac)
        if backend.pip_package:
            parts.append("pip:  pip install " + backend.pip_package)
        if backend.homepage:
            parts.append("Docs:  " + backend.homepage)
        return "\n".join(parts) if parts else \
            "See the backend's documentation to install it."
    parts = []
    if backend.apt_package:
        parts.append("Debian/Ubuntu/Mint:  sudo apt install " + backend.apt_package)
    if backend.pip_package:
        parts.append("pip:  pip install " + backend.pip_package)
    if backend.manual_hint:
        parts.append(backend.manual_hint)
    if backend.homepage:
        parts.append("Docs:  " + backend.homepage)
    return "\n".join(parts) if parts else "See the backend's documentation to install it."


# --- guided source builds ----------------------------------------------------
# Machine-runnable, NO-SUDO build recipes for the source-built backends — the
# exact commands that produced the working installs on the reference machine
# (2026-07-05): openEMS at ~/opt/openEMS (+ sibling PEP-668 venv), FastHenry at
# ~/opt/FastHenry2/bin (the -fcommon build), Palace superbuild ~/opt/palace-src
# -> ~/opt/palace. Steps are idempotent (`test -d || git clone`) so a wizard
# retry resumes instead of failing on an existing clone.

_HOME = os.path.expanduser("~")

BUILD_PLANS = {
    "openems": {
        "estimate": "15–60 min (large C++ build; all cores)",
        "prefix": os.path.join(_HOME, "opt", "openEMS"),
        "steps": [
            ("clone openEMS-Project (recursive)",
             ["bash", "-c",
              "test -d ~/opt/openEMS-Project || git clone --recursive "
              "https://github.com/thliebig/openEMS-Project.git ~/opt/openEMS-Project"]),
            ("create PEP-668-safe python venv",
             ["bash", "-c",
              "mkdir -p ~/opt/openEMS && python3 -m venv --system-site-packages "
              "~/opt/openEMS/venv"]),
            ("build openEMS + python modules (this is the long step)",
             ["bash", "-c",
              "source ~/opt/openEMS/venv/bin/activate && cd ~/opt/openEMS-Project "
              "&& ./update_openEMS.sh ~/opt/openEMS --python"]),
        ],
    },
    "fasthenry": {
        "estimate": "~1 min",
        "prefix": os.path.join(_HOME, "opt", "FastHenry2"),
        "steps": [
            ("clone FastHenry2",
             ["bash", "-c",
              "test -d ~/opt/FastHenry2 || git clone "
              "https://github.com/ediloren/FastHenry2.git ~/opt/FastHenry2"]),
            ("build (K&R-era C: needs -fcommon + the two implicit-* suppressions)",
             ["bash", "-c",
              "cd ~/opt/FastHenry2/src/fasthenry && "
              "make fasthenry CFLAGS=\"-O -DFOUR -m64 -fcommon -Wno-implicit-int -Wno-implicit-function-declaration\""]),
        ],
    },
    "palace": {
        "estimate": "30–90 min (CMake superbuild; all cores)",
        "prefix": os.path.join(_HOME, "opt", "palace"),
        "steps": [
            ("clone Palace",
             ["bash", "-c",
              "test -d ~/opt/palace-src || git clone "
              "https://github.com/awslabs/palace.git ~/opt/palace-src"]),
            ("configure superbuild",
             ["bash", "-c",
              "cmake -S ~/opt/palace-src -B ~/opt/palace-src/build "
              "-DCMAKE_INSTALL_PREFIX=$HOME/opt/palace"]),
            ("build + install (the long step)",
             ["bash", "-c",
              # nproc is coreutils and does not exist on a stock macOS; fall
              # back to sysctl so the same recipe builds on both.
              "cmake --build ~/opt/palace-src/build "
              "-j $(nproc 2>/dev/null || sysctl -n hw.ncpu)"]),
        ],
    },
}


def build_plan(key):
    """The no-sudo source-build recipe for a backend, or None.

    None when the backend is not source-built, has no recipe, or the platform
    has no bash (native Windows — use WINDOWS_HINTS there).
    """
    if os.name == "nt":
        return None
    backend = BACKENDS.get(key)
    if backend is None or not backend.source_build:
        return None
    return BUILD_PLANS.get(key)


def run_build(key, line_callback=None, job_slot=None):
    """Run a backend's source build, streaming output lines. Returns SolverInfo.

    Preflights :func:`check_prereqs` FIRST and raises ``SolverError`` with the
    missing packages (and the apt one-liner) before any compile starts — the
    Palace/OpenBLAS lesson. ``job_slot``, when given, receives each live
    ``SolverJob`` so a GUI can abort the current step.
    """
    from emstudio.solvers.base import SolverError, SolverJob

    plan = build_plan(key)
    if plan is None:
        raise SolverError("no guided build available for '{0}' on this platform".format(key))
    backend = BACKENDS[key]

    missing = [p for p, ok in check_prereqs(backend) if not ok]
    if missing:
        if _is_mac():
            pkgs = " ".join(dict.fromkeys(" ".join(p.brew for p in missing).split()))
            install_cmd = ("  brew install {0}".format(pkgs) if pkgs else
                           "  xcode-select --install   (and see https://brew.sh)")
        else:
            pkgs = " ".join(dict.fromkeys(" ".join(p.apt for p in missing).split()))
            install_cmd = "  sudo apt install -y {0}".format(pkgs)
        raise SolverError(
            "build prerequisites missing for {0}:\n{1}\n\nInstall them first:\n"
            "{2}".format(
                backend.label,
                "\n".join("  - {0}{1}".format(p.name, (" — " + p.why) if p.why else "")
                          for p in missing),
                install_cmd))

    emit = line_callback or (lambda line: None)
    for desc, cmd in plan["steps"]:
        emit("==> {0}".format(desc))
        job = SolverJob(cmd, cwd=_HOME, line_callback=line_callback)
        if job_slot is not None:
            job_slot(job)
        job.run_blocking(timeout=4 * 3600)

    info = find_backend(key)
    if not info.found:
        raise SolverError(
            "build finished but {0} was not detected afterwards — check the log; "
            "expected under {1}".format(backend.label, plan["prefix"]))
    emit("==> {0} installed: {1}".format(backend.label, info.path))
    return info
