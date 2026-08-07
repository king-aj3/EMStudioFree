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

from emstudio import procutil
import sys
from dataclasses import dataclass, field

# Import-light (stdlib only at module level), so this cannot cycle: the
# openfoam module imports solvers strictly inside functions.
from emstudio.setup import openfoam as _openfoam


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


#: The ONLY definition of FastHenry's build flags. Every hint, plan and doc
#: string must interpolate this rather than spell the flags out.
#:
#: It is a single constant because the flag list had been written out in three
#: separate places, and a constant repeated in three places cannot be gated —
#: moving one copy changes nothing and the gate stays green. That is exactly how
#: this bug reached a user twice: v0.77.2 added the implicit-* pair for Apple
#: clang 15, and Apple clang 21 then made `-Wreturn-mismatch` an error too,
#: which the enumerated gate could not have caught.
#:
#: EXPECT THIS LIST TO GROW. FastHenry is K&R-era C; each compiler generation
#: promotes another legacy diagnostic to an error. Append, do not rewrite.
#:
#: `-std=gnu17` is NOT a suppression and is the reason the pattern above is not
#: quite enough on its own. GCC 15 defaults to **C23**, where an empty parameter
#: list `()` means "takes no parameters" instead of "unspecified". Every K&R
#: call in FastHenry then fails with `too many arguments to function` — a
#: SEMANTIC error that no `-Wno-` flag can reach, so the four suppressions below
#: were necessary but not sufficient. Pinning the dialect is the fix; older
#: GCC and every clang accept the flag, so it is safe everywhere. Found by
#: building on GCC 15.2.0, 2026-08-04.
FASTHENRY_CFLAGS = (
    "-O -DFOUR -m64 -fcommon -std=gnu17 "
    "-Wno-implicit-int "                    # main(argc, argv) with no return type
    "-Wno-implicit-function-declaration "   # calls before declaration
    "-Wno-return-mismatch"                  # bare `return;` from a non-void function
)

#: Individual flags, for gates that need to assert each is present.
FASTHENRY_REQUIRED_FLAGS = (
    "-fcommon",
    "-std=gnu17",
    "-Wno-implicit-int",
    "-Wno-implicit-function-declaration",
    "-Wno-return-mismatch",
)


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
        # nec2c DOES have a version flag -- its own help advertises
        # "-v: print nec2c version number and exit", and it prints "nec2c 1.3".
        # This was "-h" with a comment claiming otherwise, which made
        # _probe_version scrape the help text and report the literal string
        # "-v: print nec2c version number and exit." as the version, straight
        # into the Solver Setup dialog. Measured on the M1 build host 2026-08-03.
        version_args=("-v",),
        apt_package="nec2c",
        homepage="https://www.qsl.net/5b4az/",
        # Same gap Elmer had, found by the same audit (2026-08-03): no Homebrew
        # formula means macOS users ALWAYS source-build this, and it declared no
        # search path at all. The user who reported the macOS bugs escaped it
        # only because he happened to `make install` into /usr/local/bin, which
        # MACOS_PROBE_DIRS covers. Someone building into ~/opt would not have.
        # Both paths are real: autotools with --prefix gives <prefix>/bin, and a
        # plain `make` leaves the binary in the source root (measured).
        extra_dirs=(
            os.path.expanduser("~/opt/nec2c/bin"),
            os.path.expanduser("~/opt/nec2c"),
            # nec2++ (necpp) is the other engine this backend accepts; CMake
            # leaves the binary in the build tree's src/.
            os.path.expanduser("~/opt/necpp-build/src"),
            os.path.expanduser("~/opt/necpp/build/src"),
        ),
    ),
    "fasthenry": Backend(
        key="fasthenry",
        label="FastHenry (quasi-static wire/bundle impedance)",
        method="PEEC/filament",
        executables=("fasthenry",),
        version_args=("-help",),
        # Not packaged in Ubuntu 24.04/Mint 22 — small C source build. FastHenry
        # is K&R-era C and every modern compiler needs the flag set in
        # FASTHENRY_CFLAGS; see that constant for why each entry is there.
        # Each became an ERROR by default one compiler generation apart, which is
        # how a build that worked for years starts failing: Apple clang 15 / GCC 14
        # promoted the implicit-* pair (20 errors in induct.c, reported on macOS
        # 26.5 arm64 2026-08-01), Apple clang 21 then promoted return-mismatch
        # (2 more errors in induct.c, measured on the M1 build host 2026-08-03),
        # and GCC 15 changed the DEFAULT DIALECT to C23, which is not a warning
        # at all (measured 2026-08-04). ADDING A COMPILER IS NOT A FIX: the list
        # only ever grows, so treat a new hard error here as expected
        # maintenance, not a surprise.
        #
        # LICENCE — do NOT restate this as LGPL. It said "LGPL" from the first
        # commit until 2026-08-04 and that was simply wrong. FastHenry2 ships NO
        # licence file; the only licence text in the tree is an M.I.T. 1992/1994
        # header on 18 source files: "Permission to use, copy and modify for
        # internal, noncommercial purposes is hereby granted. Any distribution
        # of this program or any part thereof is strictly prohibited without
        # prior written consent of M.I.T." That is why FastHenry has no guided
        # Windows install and never can have one on these terms: we may not ship
        # the binary, and "any part thereof" covers the source too. The guided
        # SOURCE BUILD is fine — the user compiles their own copy, which is the
        # use-and-modify grant, not distribution.
        manual_hint=(
            "Build from source — M.I.T. licence, internal NONCOMMERCIAL use "
            "only, redistribution prohibited, so you build your own copy: "
            "git clone https://github.com/ediloren/FastHenry2.git "
            "&& cd FastHenry2/src/fasthenry "
            "&& make fasthenry CFLAGS=\"{0}\"".format(FASTHENRY_CFLAGS)
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
                   "K&R-era source, PLUS -Wno-return-mismatch, which Apple clang "
                   "21 turns into a hard error as well"),
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
        prerequisites=(
            Prereq("C/C++/Fortran toolchain", "bin", "gfortran",
                   "build-essential gfortran", brew="gcc"),
            Prereq("CMake", "bin", "cmake", "cmake", brew="cmake"),
            Prereq("git", "bin", "git", "git", brew="git"),
        ),
        # Elmer had no guided build,
        # so on macOS it is always source-built -- and until 2026-08-03 it had no
        # extra_dirs at all, which meant a correctly built Elmer sitting in the
        # conventional ~/opt prefix was INVISIBLE to detection. Every other
        # source-built backend already declared its ~/opt path; Elmer was the
        # holdout, because on Linux `apt install elmerfem-csc` puts it on PATH
        # and the gap never showed. Found by building it on the M1 host and
        # having Detect Solvers still report MISSING.
        extra_dirs=(
            os.path.expanduser("~/opt/elmer/bin"),
            os.path.expanduser("~/opt/elmerfem/bin"),
        ),
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
    # OpenFOAM is NOT resolved by the generic path/probe machinery below —
    # find_backend() delegates it to emstudio.setup.openfoam, which answers
    # the four questions a suite-behind-a-sourced-environment needs (where,
    # which fork, are the required tools there, do function objects WORK).
    # This entry exists so the Solver Setup table, install_plan() and the
    # first-run wizard enumerate it like any other backend.
    "openfoam": Backend(
        key="openfoam",
        label="OpenFOAM (CFD conjugate heat / enclosure airflow)",
        method="FVM",
        executables=("buoyantSimpleFoam",),  # representative only; see above
        version_args=(),
        # apt_package is EMPTY on purpose and must stay that way: the
        # Ubuntu-archive 'openfoam' package is the defective v1912 build
        # whose function objects abort (error in IOstream "sha1", measured
        # 2026-08-06) — it must never join the one-command sudo line. The
        # ESI route needs their repo added first, so it cannot be a plain
        # apt_package either; the two commands live in manual_hint.
        manual_hint=(
            "ESI (openfoam.com) build required — two commands:\n"
            "curl -s {0} | sudo bash\n"
            "sudo apt-get install -y {1}\n"
            "Do NOT install the Ubuntu-archive 'openfoam' package: that is "
            "the v1912 build whose function objects abort at runtime "
            "(EMStudio detects it and explains, but cannot use it)."
            .format(_openfoam.ESI_REPO_SCRIPT_URL, _openfoam.APT_PACKAGE)),
        homepage="https://www.openfoam.com/",
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
    """Best-effort version string: first output line that carries a digit.

    Rejects help text as well as blank lines. The "usage"/"option" filter alone
    was not enough: nec2c's help includes the line

        -v: print nec2c version number and exit.

    which contains a digit (in "nec2c"), says neither "usage" nor "option", and
    was duly reported to the user as the installed version. Any line that starts
    with "-" is a flag being documented, never a version, so it is skipped —
    which makes the heuristic safe even when a backend is pointed at the wrong
    flag. Verified against gmsh, nec2c and ElmerSolver on macOS, none of whose
    real version lines begin with "-".
    """
    try:
        out = subprocess.run(
            [path, *version_args],
            capture_output=True,
            text=True,
            creationflags=procutil.CREATE_NO_WINDOW,
            timeout=10,
        )
        text = (out.stdout or out.stderr or "").strip()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("-"):
                continue
            if any(c.isdigit() for c in line) and "usage" not in line.lower() \
                    and "option" not in line.lower():
                return line[:70]
        return ""
    except Exception:
        return ""


def find_openems_python():
    """Interpreter carrying the openEMS/CSXCAD python modules, or None.

    openEMS is the one backend EMStudio drives through a PYTHON module rather
    than a CLI, so "is openEMS usable?" is a question about an interpreter, not
    an executable. Order: ``EMSTUDIO_OPENEMS_PYTHON`` -> a venv beside the
    detected openEMS binary (the layout the guided install produces) -> None.

    It lives HERE, in the FreeCAD-free resolver, rather than in the openEMS
    runner: importing that runner drags in ``writer`` -> ``objects.analysis``
    -> ``import FreeCAD``, so a caller who only wants to ask whether the
    backend exists could not ask without FreeCAD. That is precisely why four
    openEMS gates FAILED where they should have skipped.

    BOTH venv layouts are probed. Python puts a virtualenv's interpreter at
    ``venv/bin/python`` on POSIX but ``venv\\Scripts\\python.exe`` on Windows,
    and only the POSIX one was ever checked — so a working Windows openEMS
    install could never be found.
    """
    env = os.environ.get("EMSTUDIO_OPENEMS_PYTHON", "")
    if env and os.path.isfile(env):
        return env
    info = find_backend("openems")
    if info.found:
        # <prefix>/bin/openEMS -> <prefix>/venv/{bin/python,Scripts/python.exe}
        prefix = os.path.dirname(os.path.dirname(info.path))
        for parts in (("venv", "bin", "python"),
                      ("venv", "Scripts", "python.exe"),
                      ("venv", "bin", "python.exe")):
            cand = os.path.join(prefix, *parts)
            if os.path.isfile(cand):
                return cand
    return None


def find_backend(key):
    """Locate a single backend by registry key. Returns a :class:`SolverInfo`."""
    backend = BACKENDS[key]

    # OpenFOAM is a suite behind a sourced environment, not an executable —
    # its resolver answers fork/tools/capability questions the generic path
    # below cannot ask. found here means USABLE (right fork, required tools
    # present, function objects actually work); a found-but-unusable install
    # surfaces through openfoam_status_note() instead, so the user learns
    # WHY it is not offered rather than seeing a bare MISSING.
    if key == "openfoam":
        rich = _openfoam.find_openfoam()
        if rich.usable:
            return SolverInfo(backend, rich.bashrc, rich.describe(),
                              rich.source)
        return SolverInfo(backend, "")

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

    # 4) common platform-specific directories (probe .exe/.bat variants on
    #    Windows), plus the per-user managed dirs the guided Windows installer
    #    extracts into — PATH-independent by design, so an install works even
    #    when FreeCAD was launched from a shortcut with a bare environment.
    suffixes = ("", ".exe", ".bat", ".cmd") if os.name == "nt" else ("",)
    for directory in tuple(backend.extra_dirs) + _managed_dirs(key) + _platform_dirs():
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


def openfoam_status_note():
    """The found-but-unusable OpenFOAM diagnostic, or ''. Never raises.

    Surfaced wherever a MISSING row would otherwise hide the real story
    (wrong fork / missing tools / the defective distro build) — the dialog
    and the text report both append it.
    """
    try:
        return _openfoam.status_note()
    except Exception:
        return ""


def openfoam_clear_cache():
    """Forget cached OpenFOAM discovery (Re-detect / post-install)."""
    try:
        _openfoam.clear_cache()
    except Exception:
        pass


def _lib_present(stem):
    """True if a shared library with this stem is registered with the loader."""
    try:
        out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True,
                             timeout=10,
                             creationflags=procutil.CREATE_NO_WINDOW).stdout
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
    "nec2": "No Homebrew formula in homebrew-core for ANY NEC engine (checked: "
            "nec2c, necpp, opennec, xnec2c — none exist). Two engines work, and "
            "EMStudio reads both. nec2++ (necpp) is the better-maintained one and "
            "builds with CMake: git clone https://github.com/tmolteno/necpp.git "
            "~/opt/necpp && cmake -S ~/opt/necpp -B ~/opt/necpp-build "
            "-DCMAKE_BUILD_TYPE=Release && cmake --build ~/opt/necpp-build. "
            "nec2c is the smaller C build (https://www.qsl.net/5b4az/, or the "
            "KJ7LNW fork with autoconf/automake). Measured 2026-08-03 on Apple "
            "Silicon: the two agree to 4 significant figures on the shipped "
            "dipole benchmark (296.28 MHz, 71.92 ohm, 2.13 dBi), so pick either.",
    "fasthenry": "No Homebrew formula. Build from source: git clone "
                 "https://github.com/ediloren/FastHenry2.git && cd "
                 "FastHenry2/src/fasthenry && make fasthenry "
                 "CFLAGS=\"{0}\"  — Apple clang 15+ and GCC 14+ make the "
                 "implicit-* diagnostics errors, Apple clang 21 adds "
                 "return-mismatch, and GCC 15 defaults to C23 (which needs "
                 "-std=gnu17 or every K&R call becomes 'too many arguments'). "
                 "Every flag shown is required, not optional. Note FastHenry "
                 "is licensed by M.I.T. for internal, NONCOMMERCIAL use and "
                 "may not be redistributed — you build your own "
                 "copy.".format(FASTHENRY_CFLAGS),
    "elmer": "No Homebrew formula. CSC publishes macOS builds — see "
             "https://www.elmerfem.org/ (Download → macOS), or build with "
             "brew install cmake open-mpi openblas first.",
    # The tap command below is deliberately NOT in brew_package /
    # VERIFIED_BREW_FORMULAE: those gate homebrew-CORE formulae, and core has
    # no openfoam at all (formulae.brew.sh/api/formula/openfoam.json → 404,
    # checked 2026-08-06). The gerlero tap packages the ESI fork EXCLUSIVELY
    # and ships a sourceable etc/bashrc shim inside the .app — both verified
    # from the repo source the same day.
    "openfoam": "{0}  — the community OpenFOAM.app (ESI fork, exactly what "
                "EMStudio needs; Apple-silicon Macs on macOS 14+; Intel Macs "
                "cap at v2506 via app release 2.1.2). Manual alternative: "
                "download the release zip from "
                "https://github.com/gerlero/openfoam-app and drop the .app "
                "in /Applications (unnotarized: right-click → Open once). "
                "The openfoam.org Foundation fork does NOT work with "
                "EMStudio's cases.".format(_openfoam.MACOS_BREW_CMD),
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
    # VERIFIED on Windows 2026-08-03 (MinGW-w64 GCC 15.2.0 + CMake 4.4.2): the
    # nec2++ output is BYTE-IDENTICAL to the Linux build's on the shipped dipole
    # deck, so Windows finally has a native NEC engine instead of "use WSL2".
    # Two traps, both of which cost real time and neither of which prints
    # anything useful, so they are in the user-facing text:
    #   * a MinGW-built nec2++.exe needs FOUR DLLs beside it: libnecpp.dll —
    #     necpp's OWN shared library, which this list omitted until 2026-08-04
    #     and which no amount of MinGW-runtime hunting would have supplied —
    #     plus libstdc++-6.dll and libgcc_s_seh-1.dll, which pull in
    #     libwinpthread-1.dll transitively. Measured as a full `objdump -p`
    #     import closure, not guessed. Without any one of them it exits
    #     0xC0000135 (STATUS_DLL_NOT_FOUND) with NO message and NO output file.
    #   * `cmake --build` with no target fails at 100% linking nec2++_tests.exe
    #     (`__imp__set_abort_behavior` is MSVC-only CRT). The ENGINE is already
    #     built at that point — build `--target nec2++` and skip the tests.
    "nec2": "One-click guided install available — the Install button downloads "
            "nec2++ 2.3.4 (~1.5 MB, per-user, no admin rights), built from "
            "unmodified upstream source and published by the EMStudio project "
            "because no NEC engine has an official Windows build. Verified "
            "byte-identical to the Linux build on the shipped dipole deck. "
            "Manual alternative: git clone "
            "https://github.com/tmolteno/necpp.git, then cmake -S necpp -B "
            "build -G \"MinGW Makefiles\" -DCMAKE_BUILD_TYPE=Release && cmake "
            "--build build --target nec2++  (use --target nec2++, or the test "
            "executable fails to link at 100% with __imp__set_abort_behavior — "
            "that is MSVC-only CRT and does NOT mean the engine failed). Keep "
            "build/src/nec2++.exe together with libnecpp.dll from the same "
            "build, plus libstdc++-6, libgcc_s_seh-1 and libwinpthread-1 from "
            "your toolchain — miss any one and it exits 0xC0000135 silently, "
            "with no message and no output file.",
    "fasthenry": "FastFieldSolvers ships Windows builds "
                 "(https://www.fastfieldsolvers.com/) — download and install one "
                 "yourself, then point EMStudio at it. There is no Install "
                 "button and there cannot be one: FastHenry carries an M.I.T. "
                 "licence granting internal, noncommercial use only and "
                 "prohibiting redistribution without written consent, so "
                 "EMStudio may not ship the binary for you. WSL2 also works.",
    "elmer": "One-click guided install available — the Install button downloads the "
             "official CSC Windows build (~122 MB zip, per-user, no admin rights) "
             "and EMStudio detects it automatically. Manual alternative: the "
             "official installer at https://www.elmerfem.org/.",
    "palace": "No native Windows support (Linux/macOS only) — use WSL2.",
    # ESI's native mingw Windows binary is advertised in their own wiki and
    # its download 404s at every path (measured 2026-08-06, reported
    # upstream) — so the guided route is the vendor-preferred WSL2 one, and
    # it is honest about the single admin step no installer can skip.
    "openfoam": "Guided install available — the Install button creates "
                "EMStudio's own WSL2 distro ('{0}': Ubuntu rootfs, "
                "SHA256-verified, no Microsoft Store) and installs the "
                "official ESI OpenFOAM packages inside it, all per-user. "
                "ONE-TIME prerequisite that does need Administrator + a "
                "reboot: enabling WSL2 itself (wsl --install "
                "--no-distribution) — the button explains this when needed "
                "instead of failing. Uninstall: wsl --unregister {0}."
                .format(_openfoam.WSL_DISTRO),
    "gmsh": "One-click guided install available — the Install button downloads the "
            "official gmsh Windows zip (~37 MB, per-user, no admin rights). "
            "Manual alternative: https://gmsh.info/.",
}


# --- Windows guided installs ------------------------------------------------
# The Linux/macOS guided path COMPILES from source through bash. Native Windows
# has no bash, usually no compiler and often no admin rights, so its guided
# path is different in kind: DOWNLOAD the official prebuilt binaries into a
# per-user managed directory and extract them with the stdlib — no shell, no
# NSIS installer, no UAC prompt. Only backends whose upstream publishes real
# Windows binaries belong here; the rest keep their honest WINDOWS_HINTS
# (fastfieldsolvers.com gates downloads behind a form; openEMS zips exist but
# the python-driven run pipeline is not wired on native Windows, so installing
# one would produce a "found" solver that cannot run — worse than honesty).

def win_install_root():
    """Per-user root for guided Windows installs (%LOCALAPPDATA%/EMStudio/solvers)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "EMStudio", "solvers")


def _managed_dirs(key):
    """Probe dirs for guided Windows installs. Empty off Windows."""
    if os.name != "nt":
        return ()
    root = os.path.join(win_install_root(), key)
    return (os.path.join(root, "bin"), root)


#: Guided Windows installs: official prebuilt archives only, from the
#: publisher's own distribution point (funet is CSC's mirror — CSC writes
#: Elmer; gmsh.info is gmsh's home).
#:
#: The Elmer URL is RELEASE-PINNED as of 2026-08-06, and the rolling
#: "current build" name must not come back: CSC's NIGTLY_BUILD_IS_BROKEN.txt
#: (funet, 2026-08-05, citing our ElmerCSC/elmerfem#858) says the nightly
#: zips had AGAIN stopped bundling the MinGW runtime DLLs, the nightly is
#: abandoned ("we will not try to repair"), the rolling names now hold a
#: restored July-1 build, and fresh builds live behind a GitHub login
#: (Actions artifacts) — unusable for unattended installs. The rel26.1/
#: subdir is the release-pinned alternative: stable name AND stable content.
#: VERIFIED before switching (2026-08-06, the exact zip below, downloaded
#: and inspected): 3819 entries, bin/ElmerSolver.exe + bin/ElmerGrid.exe,
#: 296 DLLs in bin/ including every runtime DLL in the completion list —
#: which stays anyway, because it is free on a complete zip and repairs an
#: incomplete one.
#: Elmer gui/nompi is deliberate on BOTH axes: nompi because EMStudio drives
#: a headless serial ElmerSolver and MS-MPI needs its own admin installer;
#: gui — NOT nogui — because when this was chosen the nogui zip shipped no
#: MinGW runtime DLLs at all (only static .a archives in its stripped
#: toolchain), so its ElmerSolver.exe died 0xC0000135 before printing a
#: byte. CSC's 2026-08-05 rebuild fixed the runtime across the board, but
#: gui stays: it is the variant actually verified end to end here, and a
#: rolling "current build" URL is not the place to switch variants on the
#: strength of one upstream rebuild.
WIN_INSTALL_PLANS = {
    "elmer": {
        "estimate": "3-15 min (a ~210 MB download; no compile)",
        "url": "https://www.nic.funet.fi/pub/sci/physics/elmer/bin/windows/"
               "rel26.1/ElmerFEM-gui-nompi-Windows-AMD64-rel26.1.zip",
        # The file that proves extraction found the real tree, relative to it.
        "proof": os.path.join("bin", "ElmerSolver.exe"),
        # UPSTREAM FIXED THIS — the completion step below is now normally a
        # NO-OP. When ElmerCSC/elmerfem#858 was filed the Windows zips shipped
        # NO MinGW runtime DLLs and ElmerSolver.exe died 0xC0000135 before
        # printing a byte. CSC refreshed the funet build on **2026-08-05** and
        # it now carries 316 DLLs in bin/, beside the exe. VERIFIED on the
        # Windows VM the same day: extracted the refreshed zip, stripped PATH
        # to C:\Windows, ran NO completion step — ElmerSolver reached "ELMER
        # SOLVER FINISHED" (exit 0) and ElmerGrid ran (exit 0). It is genuinely
        # self-contained.
        #
        # The completion path is KEPT as a fallback, because the zip is a
        # rolling "current build" URL: if CSC ever rebuilds without the
        # runtime, this silently repairs it instead of handing the user a
        # 0xC0000135 with no message. `need` is computed per-DLL, so on a
        # complete zip nothing is downloaded at all.
        #
        # **libgomp-1.dll was REMOVED from this list on 2026-08-05.** It was
        # here because MSYS2's OpenBLAS is an OpenMP build — but CSC's own
        # libopenblas is not, so the refreshed zip neither ships it nor needs
        # it. Leaving it listed made `need` permanently non-empty, which fired
        # the MSYS2 download on every install of an already-complete tree and
        # turned a working install into a hard failure on any box whose
        # tar.exe cannot read zstd. A VERIFY list must describe what the
        # binary actually imports, or it stops being a check and becomes a
        # trigger.
        #
        # MSYS2 package names, measured against the live index 2026-08-04:
        # libgcc_s_seh-1 + libquadmath-0 come from gcc-libs, libgfortran-5
        # from gcc-LIBGFORTRAN, libwinpthread-1 from libwinpthread (the old
        # "-git" suffixed name is GONE from the index). GCC's Windows runtime
        # is backward-compatible — libgfortran so-version 5 covers GCC 8
        # through current — so a newer runtime under a GCC 10-built Elmer is
        # the supported direction.
        "runtime_dlls": ("libgfortran-5.dll", "libgcc_s_seh-1.dll",
                         "libquadmath-0.dll", "libwinpthread-1.dll",
                         "libopenblas.dll"),
        "runtime_pkgs": ("mingw-w64-x86_64-gcc-libs",
                         "mingw-w64-x86_64-gcc-libgfortran",
                         "mingw-w64-x86_64-libwinpthread",
                         "mingw-w64-x86_64-openblas"),
    },
    "gmsh": {
        "estimate": "1-3 min (a ~37 MB download; no compile)",
        "url": "https://gmsh.info/bin/Windows/gmsh-stable-Windows64.zip",
        "proof": "gmsh.exe",
    },
    # The one SELF-HOSTED entry, and the only one that needs justifying: every
    # other plan points at the publisher's own distribution point, because the
    # button rule is "official prebuilt binaries only". NOBODY publishes a
    # Windows build of any NEC engine — checked upstream for nec2c, necpp,
    # opennec and xnec2c — so Windows had no NEC engine at all short of WSL2,
    # while nec2++ itself runs natively and correctly there. So we build and
    # publish it ourselves, from UNMODIFIED upstream source, as a release asset
    # on the public EMStudioFree repo:
    #
    #   https://github.com/king-aj3/EMStudioFree/releases/tag/nec2pp-2.3.4-win64
    #
    # necpp is GPL-2, so that same release carries the complete corresponding
    # source (`nec2pp-source-46f7fbd.zip`, a verbatim git archive of the exact
    # commit, plus BUILD-WINDOWS.txt) — that is the section 3 offer, and it must
    # stay published for as long as this URL is live. Bump BOTH together.
    #
    # The URL is version-pinned rather than a floating "current build" name,
    # unlike elmer/gmsh: we control this one, so a rebuild gets a new tag and an
    # explicit edit here, which is auditable instead of silently shifting under
    # users.
    #
    # NO runtime_dlls: that key exists to COMPLETE a deficient upstream zip from
    # MSYS2 (CSC's Elmer zips ship none). Ours ships its own complete set and was
    # clean-room verified with PATH stripped to C:\Windows, so there is nothing
    # to complete — and libnecpp.dll has no MSYS2 package anyway, so a fallback
    # attempt could only fail confusingly.
    #
    # The zip carries FIVE files that must travel together. nec2++.exe imports
    # libnecpp.dll (necpp's OWN shared library, easy to miss — the DLL list in
    # WINDOWS_HINTS omitted it until 2026-08-04) plus libstdc++-6 and
    # libgcc_s_seh-1, which pull in libwinpthread-1 transitively. Measured as a
    # full import closure with `objdump -p`, then negative-controlled: delete
    # libnecpp.dll and the run exits -1073741515 (0xC0000135) writing nothing
    # at all — no message, no output file.
    "nec2": {
        "estimate": "1-2 min (a ~1.5 MB download; no compile)",
        "url": "https://github.com/king-aj3/EMStudioFree/releases/download/"
               "nec2pp-2.3.4-win64/nec2pp-win64.zip",
        "proof": "nec2++.exe",
        # The GPL-2 section 3 offer. This is not documentation — the smoke gate
        # REQUIRES it for any self-hosted plan and requires it to sit in the
        # same release tag as the binary, so a rebuild cannot ship new binaries
        # against a stale source zip.
        "source_offer": "https://github.com/king-aj3/EMStudioFree/releases/"
                        "download/nec2pp-2.3.4-win64/nec2pp-source-46f7fbd.zip",
    },
}

#: Host we publish our own solver builds from. A plan whose URL points here is
#: SELF-HOSTED: we are the distributor, so the licence obligations are ours and
#: the smoke gate enforces the source offer.
SELF_HOSTED_PREFIX = "https://github.com/king-aj3/EMStudioFree/releases/"


def is_self_hosted(plan):
    """True when WE publish this backend's Windows binary rather than upstream."""
    return plan.get("url", "").startswith(SELF_HOSTED_PREFIX)


def _release_tag(url):
    """The release tag inside a GitHub release-download URL, or ''."""
    marker = "/releases/download/"
    if marker not in url:
        return ""
    return url.split(marker, 1)[1].split("/", 1)[0]


def win_install_plan(key):
    """The guided Windows install for a backend, or None (always None off nt)."""
    if os.name != "nt":
        return None
    return WIN_INSTALL_PLANS.get(key)


_MSYS2_MINGW64 = "https://mirror.msys2.org/mingw/mingw64/"


def _zstd_tar():
    """Windows' built-in bsdtar IF it can read zstd, else None.

    MSYS2 packages are .pkg.tar.zst. libarchive gained zstd recently, so a
    Windows 10-era tar.exe cannot read them — capability is PROBED, never
    assumed, and the caller degrades to an honest error.
    """
    tar = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                       "System32", "tar.exe")
    if not os.path.isfile(tar):
        return None
    try:
        out = subprocess.run([tar, "--version"], capture_output=True,
                             text=True, timeout=15,
                             creationflags=procutil.CREATE_NO_WINDOW)
    except Exception:
        return None
    return tar if "libzstd" in (out.stdout or "") else None


def _install_msys2_dlls(bin_dir, pkgs, dlls, say):
    """Copy MinGW runtime DLLs from MSYS2's official repo into ``bin_dir``.

    The package index (mingw64.db, a stable name) resolves current package
    filenames, so nothing here goes stale with MSYS2 releases. Extraction is
    Windows' own tar.exe — no shell scripts, no execution of anything
    downloaded, no admin rights.
    """
    import re as _re
    import tempfile

    from emstudio.solvers.base import SolverError

    tar = _zstd_tar()
    if tar is None:
        raise SolverError(
            "this install needs MinGW runtime DLLs ({0}) and this Windows' "
            "tar.exe cannot read zstd — run the official installer instead "
            "(see Details).".format(", ".join(dlls)))

    tmp = tempfile.mkdtemp(dir=win_install_root())
    try:
        db = os.path.join(tmp, "mingw64.db")
        _download_archive(_MSYS2_MINGW64 + "mingw64.db", db, say)
        listing = subprocess.run([tar, "-tf", db], capture_output=True,
                                 text=True, timeout=120,
                                 creationflags=procutil.CREATE_NO_WINDOW)
        if listing.returncode != 0:
            raise SolverError("cannot read the MSYS2 package index: "
                              + (listing.stderr or "")[:200])
        wanted = {}
        for line in listing.stdout.splitlines():
            top = line.strip("/").split("/")[0]
            for p in pkgs:
                # dir is <pkg>-<version>-<rel>; requiring a digit after the
                # hyphen stops gcc-libs from matching gcc-libs-multilib etc.
                rest = top[len(p) + 1:] if top.startswith(p + "-") else ""
                if rest[:1].isdigit():
                    wanted[p] = top
        missing_pkgs = [p for p in pkgs if p not in wanted]
        if missing_pkgs:
            raise SolverError(
                "the MSYS2 index lacks {0}".format(", ".join(missing_pkgs)))

        for p in pkgs:
            desc = subprocess.run([tar, "-xOf", db, wanted[p] + "/desc"],
                                  capture_output=True, text=True, timeout=60,
                                  creationflags=procutil.CREATE_NO_WINDOW)
            m = _re.search(r"%FILENAME%\s*\n(\S+)", desc.stdout or "")
            fname = m.group(1) if m else wanted[p] + "-any.pkg.tar.zst"
            arch = os.path.join(tmp, fname)
            say("fetching runtime package " + fname)
            _download_archive(_MSYS2_MINGW64 + fname, arch, say)
            ex = subprocess.run([tar, "-xf", arch, "-C", tmp],
                                capture_output=True, text=True, timeout=300,
                                creationflags=procutil.CREATE_NO_WINDOW)
            if ex.returncode != 0:
                raise SolverError("cannot extract {0}: {1}".format(
                    fname, (ex.stderr or "")[:200]))
        # Copy EVERY DLL the runtime packages ship, not just the declared
        # list — cherry-picking invited whack-a-mole (libopenblas turned out
        # to want libgomp-1, found via the import closure). The declared
        # list is the post-condition below.
        src_bin = os.path.join(tmp, "mingw64", "bin")
        for f in sorted(os.listdir(src_bin) if os.path.isdir(src_bin) else ()):
            if f.lower().endswith(".dll"):
                shutil.copy2(os.path.join(src_bin, f),
                             os.path.join(bin_dir, f))
                say("  + " + f)
        remaining = [d for d in dlls
                     if not os.path.isfile(os.path.join(bin_dir, d))]
        if remaining:
            raise SolverError("runtime DLLs not found in the MSYS2 packages: "
                              + ", ".join(sorted(remaining)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _download_archive(url, dest, say):
    """Download ``url`` to the file path ``dest``, streaming progress via say().

    urllib first (works everywhere TLS is honest, and carries the smoke gate's
    file:// fixture). Corporate networks that intercept TLS re-sign traffic
    with a private CA whose INTERMEDIATE OpenSSL cannot chase, so urllib dies
    with CERTIFICATE_VERIFY_FAILED even though the CA is in the Windows store
    — measured on the work-network box this feature was built for (2026-08-04;
    git on the same box works because Windows git speaks schannel). Fallback:
    Windows' built-in curl.exe, whose schannel backend trusts the Windows
    certificate store and chases intermediates. TLS verification is NEVER
    disabled — a failure past both routes is reported, not worked around.
    """
    import ssl
    import urllib.error
    import urllib.request

    from emstudio.solvers.base import SolverError

    try:
        with urllib.request.urlopen(url, timeout=60) as resp, \
                open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done, next_mark = 0, 16 << 20
            while True:
                chunk = resp.read(512 << 10)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if done >= next_mark:
                    say("  {0} MB{1}".format(
                        done >> 20,
                        " / ~{0} MB".format(total >> 20) if total else ""))
                    next_mark += 16 << 20
        return
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if not isinstance(reason, ssl.SSLCertVerificationError):
            raise SolverError("download failed: {0}".format(exc))
        say("  TLS verification failed (corporate proxy interception?) — "
            "retrying through Windows curl/schannel...")

    curl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "curl.exe")
    if not os.path.isfile(curl):
        raise SolverError(
            "the network intercepts TLS and curl.exe is unavailable — "
            "download {0} manually and extract it under {1}".format(
                url, win_install_root()))
    say("  (curl shows no progress until it finishes)")
    job = subprocess.run(
        [curl, "-fsSL", "--connect-timeout", "30", "--retry", "2",
         "-o", dest, url],
        capture_output=True, text=True, timeout=1800,
        creationflags=procutil.CREATE_NO_WINDOW)
    if job.returncode != 0:
        raise SolverError("curl download failed (exit {0}): {1}".format(
            job.returncode, (job.stderr or "").strip()[:300]))
    say("  downloaded via curl ({0} MB)".format(os.path.getsize(dest) >> 20))


def run_win_install(key, line_callback=None, _plan=None):
    """Download + extract a backend's official Windows build. Returns SolverInfo.

    Stdlib + Windows built-ins only: no shell scripts, no installer, no admin
    rights. The archive is extracted into a temp dir and moved into place only
    after the proof executable is found, so an interrupted download can never
    leave a half-install that probing would trust. ``_plan`` exists for the
    smoke gate, which feeds a file:// URL — everything downstream of the URL
    is exactly the shipping path.
    """
    import tempfile
    import zipfile as _zipfile

    from emstudio.solvers.base import SolverError

    def say(line):
        if line_callback:
            line_callback(line)

    plan = _plan if _plan is not None else win_install_plan(key)
    if plan is None:
        raise SolverError(
            "no guided Windows install for '{0}' on this platform".format(key))

    root = win_install_root()
    target = os.path.join(root, key)
    os.makedirs(root, exist_ok=True)

    say("downloading " + plan["url"])
    fd, tmp_zip = tempfile.mkstemp(suffix=".zip", dir=root)
    os.close(fd)
    tmp_dir = None
    try:
        _download_archive(plan["url"], tmp_zip, say)
        say("extracting...")
        tmp_dir = tempfile.mkdtemp(dir=root)
        try:
            with _zipfile.ZipFile(tmp_zip) as zf:
                zf.extractall(tmp_dir)
        except _zipfile.BadZipFile as exc:
            raise SolverError("corrupt download: {0}".format(exc))
    finally:
        try:
            os.unlink(tmp_zip)
        except OSError:
            pass

    # The zip may or may not carry a top-level folder — find the tree that
    # actually contains the proof executable rather than assuming a layout.
    tree = None
    for dirpath, _dirs, _files in os.walk(tmp_dir):
        if os.path.isfile(os.path.join(dirpath, plan["proof"])):
            tree = dirpath
            break
    if tree is None:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise SolverError(
            "archive did not contain {0} — upstream layout changed; "
            "report this".format(plan["proof"]))

    if os.path.isdir(target):
        say("replacing the previous install...")
        shutil.rmtree(target)
    shutil.move(tree, target)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    say("installed to " + target)

    dlls = plan.get("runtime_dlls")
    if dlls:
        bin_dir = os.path.dirname(os.path.join(target, plan["proof"]))
        need = tuple(d for d in dlls
                     if not os.path.isfile(os.path.join(bin_dir, d)))
        if need:
            say("completing the tree with MinGW runtime DLLs "
                "(the upstream zip ships none)...")
            _install_msys2_dlls(bin_dir, plan["runtime_pkgs"], need, say)

    info = find_backend(key)
    if not info.found:
        raise SolverError(
            "installed to {0} but detection cannot see it — report this".format(target))
    say("detected: {0}{1}".format(
        info.path, (" — " + info.version) if info.version else ""))
    return info


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
        note = openfoam_status_note()
        if note:
            lines += ["", "  note: " + note]
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
        note = openfoam_status_note()
        if note:
            lines += ["", "  note: " + note]
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
    note = openfoam_status_note()
    if note:
        lines += ["", "  note: " + note]
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
            ("build (K&R-era C: needs -fcommon + three diagnostic suppressions)",
             ["bash", "-c",
              "cd ~/opt/FastHenry2/src/fasthenry && "
              "make fasthenry CFLAGS=\"{0}\"".format(FASTHENRY_CFLAGS)]),
        ],
    },
    "elmer": {
        # Measured on an 8-core M1 (8 GB): ~18 min at -j8.
        "estimate": "15–35 min (CMake; all cores)",
        "prefix": os.path.join(_HOME, "opt", "elmer"),
        "steps": [
            # release-26.2.1 is a git TAG, not a branch — Elmer publishes no
            # release-X.Y.Z branches at all (full branch list checked
            # 2026-08-06). `git clone -b` resolves tags, so this works; any
            # future change fetching refs/heads/release-* explicitly would
            # not. The PPA is a different beast again: it ships dated devel
            # snapshots versioned 9.0-0ppa0-<date>, never "26.2.1".
            ("clone Elmer (release tag)",
             ["bash", "-c",
              "test -d ~/opt/elmerfem || git clone --depth 1 "
              "-b release-26.2.1 https://github.com/ElmerCSC/elmerfem.git "
              "~/opt/elmerfem"]),
            # WITH_OpenMP=OFF is NOT a style choice: Apple clang ships no OpenMP
            # runtime, and CMake dies at "Could NOT find OpenMP_C (missing:
            # OpenMP_C_FLAGS OpenMP_C_LIB_NAMES)" before writing a Makefile.
            # ELMERGUI=OFF avoids pulling Qt for a solver we drive headlessly;
            # MPI=OFF keeps it to the plain ElmerSolver the runner invokes.
            ("configure (GUI/MPI/OpenMP off — see comment: OpenMP breaks on Apple clang)",
             ["bash", "-c",
              "cmake -S ~/opt/elmerfem -B ~/opt/elmer-build "
              "-DCMAKE_INSTALL_PREFIX=$HOME/opt/elmer "
              "-DWITH_ELMERGUI=OFF -DWITH_MPI=OFF -DWITH_OpenMP=OFF "
              "-DCMAKE_BUILD_TYPE=Release"]),
            ("build (the long step)",
             ["bash", "-c",
              "cmake --build ~/opt/elmer-build "
              "-j $(nproc 2>/dev/null || sysctl -n hw.ncpu)"]),
            ("install to ~/opt/elmer",
             ["bash", "-c", "cmake --install ~/opt/elmer-build"]),
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
    if backend is None:
        return None
    # A backend can be package-managed on one platform and source-built on
    # another. Elmer is `apt install elmerfem-csc` on Linux but has NO Homebrew
    # formula, so on macOS the guided build is the only route there is. Gating
    # purely on the source_build flag forced a bad choice: leave it False and
    # macOS never gets a Build button, or flip it True and `elmerfem-csc` drops
    # out of the LINUX apt line (see install_plan's `apt_package and not
    # source_build`). Deciding per platform avoids both.
    offers_build = backend.source_build or (_is_mac() and not backend.brew_package)
    if not offers_build:
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
