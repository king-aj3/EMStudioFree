# SPDX-License-Identifier: LGPL-2.1-or-later
"""OpenFOAM (ESI) discovery and guided-install support.

OpenFOAM breaks every assumption the generic resolver in ``solvers.py`` makes,
which is why it gets its own module rather than another ``Backend`` tuple:

* it is a SUITE of binaries (blockMesh, snappyHexMesh, buoyantSimpleFoam, ...)
  behind a sourced environment, not one executable — nothing is on PATH, and
  running any tool without sourcing ``etc/bashrc`` dies with *"Could not find
  mandatory etc entry 'controlDict'"* (measured on this box, 2026-08-05);
* two unrelated forks share the name. EMStudio's generated cases are
  ESI-flavoured (openfoam.com, versions like ``v2512``); the Foundation fork
  (openfoam.org, versions ``9``..``12``) differs in dictionary names, solver
  names and even utility names (``surfaceFeatureExtract`` exists only in the
  ESI fork), so a Foundation install must be REPORTED, never offered;
* one widely-installed build is defective at runtime: Ubuntu's own
  ``openfoam 1912.200626`` package aborts on ANY function object with
  ``error in IOstream "sha1"`` (reproduced here on OpenFOAM's own pitzDaily
  and on the 1-cell probe below, 2026-08-06). That is a packaging defect, not
  a version boundary — so there is NO version floor in this module; usability
  is PROBED at runtime instead (docs/OPENFOAM_INSTALL.md §1);
* on native Windows there is no install at all: ESI's own wiki advertises a
  mingw binary whose download 404s (measured 2026-08-06, reported upstream),
  so the vendor-preferred route is WSL2 — a different kind of install from
  every other backend, with one honest elevation step.

Discovery therefore answers four questions, not one: WHERE is an install
(bashrc path), WHICH fork/version is it, does it have the REQUIRED tools, and
do its function objects actually WORK. Everything here is Qt-free and
FreeCAD-optional so it runs under plain pytest and ``freecadcmd`` alike.
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import shutil
import subprocess

from emstudio import procutil
import sys
from dataclasses import dataclass, field

# --- what a usable install must provide -------------------------------------
# Read-time HARD requirements of the generated cases (cross-app contract,
# 3D_Coupling_Transformer_Calculator/docs/OPENFOAM_REQUIREMENTS.md rev
# 2026-08-06, folded into docs/OPENFOAM_INSTALL.md §4b): a build missing any
# of these aborts rather than degrading, so discovery checks for them instead
# of only finding an executable.
REQUIRED_TOOLS = ("blockMesh", "surfaceFeatureExtract", "snappyHexMesh",
                  "checkMesh", "buoyantSimpleFoam")
#: Useful but not blocking (parallel runs, renumbering, post-processing).
WANTED_TOOLS = ("decomposePar", "reconstructPar", "renumberMesh", "postProcess")

# --- guided-install facts, all verified live 2026-08-06 ---------------------
#: OpenCFD's own repo-add script (writes openfoam.list + pubkey, runs
#: apt-get update). Fetched and read in full before being named here.
ESI_REPO_SCRIPT_URL = "https://dl.openfoam.com/add-debian-repo.sh"

#: The one apt package that yields a complete working install ("everything
#: installation": runtime + wmake toolchain + tutorials). VERSION-PINNED on
#: purpose: the floating ``openfoam-default`` meta would silently move under
#: users. 2512 is the newest FINAL release in the ESI deb repo (v2606 is
#: still ``2606.0~rc2-1`` there) — verified against the live noble AND jammy
#: Packages indexes, 2026-08-06. Do NOT bump this from memory; re-read the
#: index. And never name the bare Ubuntu-archive ``openfoam`` package as an
#: install target — that is the defective v1912 build this module exists to
#: detect.
APT_PACKAGE = "openfoam2512-default"

#: Where the ESI packages land; confirmed by unpacking the actual .deb
#: (openfoam2606-common carries ./usr/lib/openfoam/openfoam2606/etc/bashrc).
LINUX_BASHRC_GLOBS = (
    ("/usr/lib/openfoam/openfoam*/etc/bashrc", "apt-esi"),
    ("/opt/OpenFOAM-*/etc/bashrc", "source"),
    (os.path.join(os.path.expanduser("~"), "OpenFOAM", "OpenFOAM-*",
                  "etc", "bashrc"), "source"),
    ("/opt/openfoam*/etc/bashrc", "apt-foundation"),   # Foundation layout
    ("/usr/share/openfoam/etc/bashrc", "distro"),      # Ubuntu archive pkg
)

#: macOS: the community "OpenFOAM for macOS" app (gerlero/openfoam-app) is
#: the only realistic native route and packages the ESI fork EXCLUSIVELY
#: (the Foundation fork does not compile natively on macOS — their words).
#: Verified from the repo source 2026-08-06: the app ships a sourceable
#: ``Contents/Resources/etc/bashrc`` shim that quietly mounts the app's
#: case-sensitive disk image and sources the real bashrc inside it, so the
#: same ``bash -c '. <bashrc> && tool'`` pattern works on all three
#: platforms. Current releases are Apple-silicon arm64 only, macOS 14+
#: (Intel Macs cap at v2506 via app release 2.1.2).
MACOS_APP_GLOB = "/Applications/OpenFOAM-v*.app"
#: Homebrew tap command, verified against the app README 2026-08-06 (plain
#: `brew install`, no --cask; homebrew-core itself has NO openfoam formula —
#: formulae.brew.sh/api/formula/openfoam.json is a 404). This is a TAP, not
#: homebrew-core, so it deliberately does NOT go in Backend.brew_package
#: (VERIFIED_BREW_FORMULAE is a core-formula allow-list).
MACOS_BREW_CMD = "brew install gerlero/openfoam/openfoam"

#: Windows, PREFERRED route: ESI's own cross-compiled native build. Measured
#: end-to-end on the Windows VM 2026-08-08 — silent, per-user, NO admin
#: (`/S /D=`, exit 0, manifest is `asInvoker`), ships all five required tools
#: AND its own MSYS2 bash, and passes the capability probe (blockMesh 0,
#: function objects 0).
#:
#: VERSION-PINNED, and the FILENAME CARRIES THE VERSION — that is the whole
#: reason this route was missed for weeks. The wiki advertises an
#: UNVERSIONED `/source/latest/OpenFOAM-windows-mingw.exe` which has 404'd
#: for years (reported four times upstream; ours is
#: openfoam/core/openfoam#3593). Only `/source/<ver>/OpenFOAM-<ver>-windows-
#: mingw.exe` actually exists. Do NOT "simplify" this to `latest`.
#:
#: v2512 and not v2606: v2606 has NO Windows build published at all (both
#: names 404). Re-read the directory listing before bumping — and note the
#: v2512 build stamp is `bd2b6720-20260127`, i.e. it POSTDATES the fix for
#: upstream #3488 (a mingw-only memory-alignment segfault in snappyHexMesh).
#: An older respin would carry that defect.
WIN_NATIVE_VERSION = "v2512"
WIN_NATIVE_URL = ("https://dl.openfoam.com/source/{0}/"
                  "OpenFOAM-{0}-windows-mingw.exe").format(WIN_NATIVE_VERSION)

#: Relative to the install root: the MSYS2 bash the package ships, and the
#: OpenFOAM tree inside its virtual home. `ofuser` is upstream's build-time
#: user and is baked into the package layout.
WIN_NATIVE_BASH = os.path.join("msys64", "usr", "bin", "bash.exe")
WIN_NATIVE_POSIX_PREFIX = "/home/ofuser/OpenFOAM/OpenFOAM-" + WIN_NATIVE_VERSION
WIN_NATIVE_BASHRC = WIN_NATIVE_POSIX_PREFIX + "/etc/bashrc"
#: Where the solver .exes and their DLLs live, relative to the tree.
WIN_NATIVE_BINDIR = os.path.join("msys64", "home", "ofuser", "OpenFOAM",
                                 "OpenFOAM-" + WIN_NATIVE_VERSION,
                                 "platforms", "win64MingwDPInt32Opt", "bin")

#: Windows, FALLBACK route: our own WSL2 distro. EMStudio OWNS this distro
#: (created by ``wsl --import`` below), so installs never touch a user's own
#: distro and uninstall is one honest command:
#: ``wsl --unregister EMStudio-OpenFOAM``.
WSL_DISTRO = "EMStudio-OpenFOAM"
#: Ubuntu's official WSL rootfs. NOTE the /wsl/releases/ path: the sibling
#: /wsl/noble/current/ directory contains ONLY manifests, no tarballs —
#: verified 2026-08-06. SHA256 from the SHA256SUMS file beside the tarball;
#: the download is refused if the digest does not match.
WSL_ROOTFS_URL = ("https://cloud-images.ubuntu.com/wsl/releases/24.04/"
                  "current/ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz")
WSL_ROOTFS_SHA256 = ("8251e27ffff381a4af5f41dcb94d867de3e0d9774a9241908ab3"
                     "4555d99315ea")
#: The WSL2 kernel MSI for the manual (pre-19041) path. aka.ms/wsl2kernel no
#: longer points at the file (it 301s to a docs page now) — this blob URL is
#: what Microsoft's own install-manual page links, HEAD-checked 2026-08-06.
WSL_KERNEL_MSI_URL = ("https://wslstorestorage.blob.core.windows.net/"
                      "wslblob/wsl_update_x64.msi")

_PREF_BASHRC_KEY = "openfoam"            # FreeCAD pref: explicit bashrc path
_PREF_WSL_DISTRO_KEY = "openfoam_wsl_distro"  # FreeCAD pref: distro override


@dataclass
class OpenFoamInfo:
    """Everything discovery learned about the best OpenFOAM candidate."""

    bashrc: str = ""          # sourceable env anchor ('' = nothing found)
    prefix: str = ""          # WM_PROJECT_DIR (parent of etc/)
    version: str = ""         # e.g. "v2512", "v1912", "12"
    fork: str = ""            # "esi" | "foundation" | "unknown"
    source: str = ""          # apt-esi|source|apt-foundation|distro|app|pref|env|wsl:<distro>|win-native:<root>
    wsl_distro: str = ""      # Windows only: distro the install lives in
    native_root: str = ""     # Windows only: root of a native (mingw) install
    #: Windows native only: what pstream_repair did on this detect —
    #: "" (not a native install) | "msmpi-present" | "restored-msmpi" |
    #: "swapped-to-dummy" | "already-serial" | "no-pstream" | "failed: ...".
    #: "already-serial" is the one that means SINGLE-PROCESS runs.
    pstream: str = ""
    missing_required: tuple = ()
    missing_wanted: tuple = ()
    #: "" = not probed; "ok"; "defective-sha1" (the known Ubuntu packaging
    #: bug); "failed" (function objects break some other way); "broken"
    #: (even blockMesh failed).
    function_objects: str = ""

    @property
    def found(self):
        return bool(self.bashrc)

    @property
    def native_bash(self):
        """The MSYS2 bash a native Windows install ships, or ''."""
        if not self.native_root:
            return ""
        return os.path.join(self.native_root, WIN_NATIVE_BASH)

    @property
    def usable(self):
        """Can EMStudio actually drive this install?"""
        return (self.found and self.fork == "esi"
                and not self.missing_required
                and self.function_objects == "ok")

    def describe(self):
        """One line for the Solver Setup table's Details column."""
        if not self.found:
            return ""
        fork = {"esi": "ESI", "foundation": "Foundation",
                "unknown": "unknown fork"}.get(self.fork, self.fork)
        return "OpenFOAM {0} ({1}, {2})".format(self.version or "?", fork,
                                                self.source)


# --- fork / version classification ------------------------------------------

_VERSION_RE = re.compile(
    r"^\s*(?:export\s+)?WM_PROJECT_VERSION\s*=\s*['\"]?([^'\"\s#]+)",
    re.MULTILINE)


def bashrc_version(path):
    """WM_PROJECT_VERSION as written in an etc/bashrc, or ''.

    A static read, deliberately: classifying a candidate must not require
    RUNNING it (a Foundation bashrc would be sourced just to learn we cannot
    use it). The runtime probe re-reads the version authoritatively later.
    """
    try:
        with open(path, "r", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = _VERSION_RE.search(text)
    return m.group(1) if m else ""


def fork_of(version):
    """'esi' | 'foundation' | 'unknown' from a WM_PROJECT_VERSION string.

    ESI versions are YYMM stamps, usually v-prefixed (v2512, v1912 — even
    Ubuntu's distro build of the ESI fork says v1912, measured here); the
    Foundation counts small integers (9..12). ``dev``/anything else is
    unknown, which downstream treats as not-ESI — refusing to run an
    unidentified build beats guessing.
    """
    v = (version or "").strip()
    if not v:
        return "unknown"
    core = v[1:] if v[:1] in ("v", "V") else v
    if core.isdigit():
        n = int(core)
        if len(core) == 4 and n >= 1606:
            return "esi"
        if n < 100:
            return "foundation"
    return "unknown"


def _version_rank(version):
    """Numeric sort key so v2512 beats v1912 beats '12'."""
    core = (version or "").lstrip("vV")
    return int(core) if core.isdigit() else -1


@dataclass(frozen=True)
class _Candidate:
    bashrc: str
    source: str
    version: str
    fork: str


def _candidate(bashrc, source, version=""):
    ver = version or bashrc_version(bashrc)
    return _Candidate(bashrc, source, ver, fork_of(ver))


def _pick_best(candidates):
    """Best candidate: ESI beats non-ESI, then newest version wins.

    A Foundation or unknown install is still RETURNED when it is all there
    is — the caller reports it honestly instead of pretending nothing is
    installed — it just never wins over any ESI install.
    """
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda c: (c.fork == "esi", _version_rank(c.version)),
        reverse=True)[0]


# --- the runtime capability probe -------------------------------------------
# The smallest case that exercises what version numbers cannot promise: a
# 1-cell blockMesh cube plus ONE function object. On a healthy install the
# whole thing runs in ~1 s; on Ubuntu's defective v1912 build blockMesh and
# checkMesh PASS and postProcess dies with `error in IOstream "sha1"` —
# measured on this box 2026-08-06, which is exactly the signature this probe
# reports. The functions block is the load-bearing part: without a function
# object the defective build looks healthy.

_PROBE_FILES = (
    ("system/controlDict", """\
FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application none; startFrom startTime; startTime 0; stopAt endTime; endTime 1;
deltaT 1; writeControl timeStep; writeInterval 1;
functions { sysinfo { type systemInfo; libs ("libutilityFunctionObjects.so"); } }
"""),
    ("system/blockMeshDict", """\
FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }
scale 1;
vertices ( (0 0 0)(1 0 0)(1 1 0)(0 1 0)(0 0 1)(1 0 1)(1 1 1)(0 1 1) );
blocks ( hex (0 1 2 3 4 5 6 7) (1 1 1) simpleGrading (1 1 1) );
boundary ( walls { type wall; faces ( (0 3 2 1)(4 5 6 7)(0 1 5 4)(2 3 7 6)(0 4 7 3)(1 2 6 5) ); } );
"""),
    ("system/fvSchemes", """\
FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; } gradSchemes { default Gauss linear; }
divSchemes { default none; } laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; } snGradSchemes { default corrected; }
"""),
    ("system/fvSolution",
     "FoamFile { version 2.0; format ascii; class dictionary; "
     "object fvSolution; }\n"),
)


def _probe_script(bashrc):
    """One self-contained bash script: build the case, source, run, report.

    A single script (rather than one subprocess per step) matters on Windows,
    where each ``wsl.exe`` invocation can cost seconds of distro start-up —
    and it keeps the case on the DISTRO's own filesystem, never /mnt/c.
    Markers go to stdout; everything else is discarded. The temp dir is
    removed on every path.
    """
    # NO `set -u` here: OpenFOAM's own bashrc references unset variables, so
    # -u aborts the SOURCING step itself and every marker after it vanishes —
    # which mis-classified the defective-v1912 box as "broken" on the first
    # live run of this probe (2026-08-06). The markers guard each step; a
    # partial transcript already reads as failure.
    lines = ['d=$(mktemp -d) || { echo "OFPROBE:SETUP:1"; exit 0; }',
             'cd "$d" || { echo "OFPROBE:SETUP:1"; exit 0; }',
             "mkdir -p system"]
    for relpath, content in _PROBE_FILES:
        lines.append("cat > {0} <<'EMSOF_EOF'\n{1}EMSOF_EOF".format(
            relpath, content))
    lines += [
        '. "{0}" >/dev/null 2>&1'.format(bashrc),
        'echo "OFPROBE:VERSION:${WM_PROJECT_VERSION:-}"',
        'echo "OFPROBE:PREFIX:${WM_PROJECT_DIR:-}"',
        "for t in " + " ".join(REQUIRED_TOOLS + WANTED_TOOLS) + "; do",
        '  command -v "$t" >/dev/null 2>&1 || echo "OFPROBE:MISSING:$t"',
        "done",
        'blockMesh >/dev/null 2>&1; echo "OFPROBE:BLOCKMESH:$?"',
        'postProcess -constant >/dev/null 2>pp.err; echo "OFPROBE:FUNCOBJ:$?"',
        "grep -qi 'sha1' pp.err && echo 'OFPROBE:SHA1:yes' "
        "|| echo 'OFPROBE:SHA1:no'",
        'cd /; rm -rf "$d"',
    ]
    return "\n".join(lines)


def _decode(raw):
    """Decode subprocess bytes that may be UTF-16-LE (wsl.exe) or UTF-8.

    ``wsl.exe`` writes ITS OWN messages (--list, errors) as UTF-16-LE, while
    a Linux command run THROUGH it writes plain UTF-8 — so the encoding is a
    property of who spoke, not of the platform. NULs are the discriminator.
    """
    if b"\x00" in raw:
        return raw.decode("utf-16-le", "ignore")
    return raw.decode("utf-8", "ignore")


def _parse_probe_output(text):
    """OFPROBE markers -> dict. Unknown lines are ignored (solver chatter)."""
    out = {"version": "", "prefix": "", "missing": [],
           "blockmesh": None, "funcobj": None, "sha1": False, "setup": False}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("OFPROBE:"):
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        key, value = parts[1], parts[2]
        if key == "VERSION":
            out["version"] = value
        elif key == "PREFIX":
            out["prefix"] = value
        elif key == "MISSING":
            out["missing"].append(value)
        elif key == "BLOCKMESH":
            out["blockmesh"] = int(value) if value.isdigit() else 99
        elif key == "FUNCOBJ":
            out["funcobj"] = int(value) if value.isdigit() else 99
        elif key == "SHA1":
            out["sha1"] = (value == "yes")
        elif key == "SETUP":
            out["setup"] = True
    return out


def _classify_probe(parsed):
    """Probe dict -> function_objects state string."""
    if parsed["setup"] or parsed["blockmesh"] is None:
        return "broken"
    if parsed["blockmesh"] != 0:
        return "broken"
    if parsed["funcobj"] == 0:
        return "ok"
    if parsed["sha1"]:
        return "defective-sha1"
    return "failed"


def _run_probe(bashrc, wsl_distro="", bash_exe=""):
    """Execute the capability probe: native POSIX, WSL distro, or bundled bash.

    ``bash_exe`` is the Windows-native route — the MSYS2 bash that ESI's own
    installer ships. It needs a LOGIN shell (``-l``): without it MSYS2's own
    PATH is unset and even ``dirname`` is missing, so sourcing OpenFOAM's
    bashrc dies half-way and every marker after it vanishes (measured
    2026-08-08).
    """
    script = _probe_script(bashrc)
    if bash_exe:
        cmd = [bash_exe, "-lc", script]
    elif wsl_distro:
        cmd = [_wsl_exe(), "-d", wsl_distro, "--", "bash", "-c", script]
    else:
        cmd = ["bash", "-c", script]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=300,
                             creationflags=procutil.CREATE_NO_WINDOW)
    except Exception:
        return None
    return _parse_probe_output(_decode(out.stdout or b""))


# --- the native-Windows MPI repair ------------------------------------------

def pstream_repair(install_root, say=None):
    """Make a no-admin native install RUNNABLE. Returns a status string.

    THE DEFECT, measured on the Windows VM 2026-08-08: ESI's installer ships
    three files — ``libPstream.dll`` plus ``libPstream.dll-msmpi`` and
    ``libPstream.dll-dummy``. It is meant to install the MS-MPI variant only
    when it can also install MS-MPI itself (which needs admin), and the dummy
    otherwise. A SILENT (``/S``) install skips that choice and leaves the
    **msmpi** variant active — 172544 bytes, byte-identical to ``-msmpi`` —
    while ``msmpi.dll`` is nowhere on the system.

    The result is the nastiest possible failure mode: EVERY solver exits
    ``0xC0000135`` (STATUS_DLL_NOT_FOUND) with no message, and ``ldd`` calls
    the whole closure resolved because it never inspects libPstream's own
    imports. That cost an hour, and it is the same lesson as nec2++: measure
    the closure, then NEGATIVE-CONTROL it — swapping the dummy in is what
    proved the diagnosis.

    So: when MS-MPI is absent and the active Pstream is the msmpi build, swap
    in the dummy (keeping a backup). Serial-only — which is all a no-admin
    install could offer anyway.

    And the REVERSE, which this function shipped without for the whole of
    v0.95.0: when MS-MPI is present and the dummy is the active build, put
    the parallel one back. The backup was written and never read by anything
    (measured on the work box 2026-08-10 — ``emstudio-backup-msmpi`` appeared
    in exactly two places, the line that creates it and a gate asserting it
    exists), so a machine that gained MS-MPI *after* EMStudio installed
    OpenFOAM stayed silently serial while this function's own note promised
    the opposite. A backup nothing restores is not a backup; it is a claim.
    """
    def note(msg):
        if say:
            say(msg)

    bindir = os.path.join(install_root, WIN_NATIVE_BINDIR)
    active = os.path.join(bindir, "libPstream.dll")
    dummy = active + "-dummy"
    msmpi = active + "-msmpi"
    backup = active + ".emstudio-backup-msmpi"
    if not os.path.isfile(active) or not os.path.isfile(dummy):
        return "no-pstream"          # layout changed; leave it alone
    if _msmpi_present():
        # Size is the discriminator throughout this function: the dummy is
        # 36864 bytes and the msmpi build 172544, so "active matches dummy"
        # means we (or the vendor) left the serial build in place.
        if os.path.getsize(active) != os.path.getsize(dummy):
            return "msmpi-present"   # the parallel build is already active
        source = next((p for p in (backup, msmpi) if os.path.isfile(p)), "")
        if not source:
            return "msmpi-present"   # serial, and nothing to restore from
        try:
            shutil.copy2(source, active)
        except OSError as exc:
            return "failed: {0}".format(exc)
        note("Microsoft MPI is installed, so the parallel build of "
             "libPstream.dll has been restored — runs are no longer limited "
             "to a single process.")
        return "restored-msmpi"
    try:
        if os.path.isfile(msmpi) and os.path.getsize(active) \
                != os.path.getsize(msmpi):
            return "already-serial"  # dummy (or something else) already in
        if not os.path.exists(backup):
            shutil.copy2(active, backup)
        shutil.copy2(dummy, active)
    except OSError as exc:
        return "failed: {0}".format(exc)
    note("MS-MPI is not installed, so the MPI build of libPstream.dll could "
         "not load and every solver would have exited 0xC0000135 with no "
         "message. Swapped in the serial build shipped beside it — runs are "
         "single-process. Install Microsoft MPI (needs admin) and re-run "
         "Detect Solvers to restore parallel.")
    return "swapped-to-dummy"


def _msmpi_present():
    root = os.environ.get("SystemRoot", r"C:\Windows")
    for cand in (os.path.join(root, "System32", "msmpi.dll"),
                 os.path.join(root, "SysWOW64", "msmpi.dll")):
        if os.path.isfile(cand):
            return True
    return False


# --- per-platform candidate enumeration -------------------------------------

def _pref_string(key):
    try:
        import FreeCAD  # noqa: PLC0415  (intentional lazy import)
    except Exception:
        return ""
    try:
        from emstudio.setup.solvers import PREF_GROUP
        return FreeCAD.ParamGet(PREF_GROUP).GetString(key, "")
    except Exception:
        return ""


def _posix_candidates():
    cands = []
    for pattern, source in LINUX_BASHRC_GLOBS:
        for hit in sorted(glob.glob(pattern)):
            if os.path.isfile(hit):
                cands.append(_candidate(hit, source))
    return cands


_MACOS_APP_VERSION_RE = re.compile(r"OpenFOAM-(v\d{4})\.app$")


def _macos_candidates():
    cands = []
    for app in sorted(glob.glob(MACOS_APP_GLOB)):
        bashrc = os.path.join(app, "Contents", "Resources", "etc", "bashrc")
        if not os.path.isfile(bashrc):
            continue
        # The app's bashrc is a 12-line mount-then-source shim carrying no
        # WM_PROJECT_VERSION of its own — the version is in the app's name.
        m = _MACOS_APP_VERSION_RE.search(app)
        cands.append(_candidate(bashrc, "app", m.group(1) if m else ""))
    # Source builds use the same conventional prefixes as Linux.
    for pattern, source in LINUX_BASHRC_GLOBS:
        if source == "source":
            for hit in sorted(glob.glob(pattern)):
                if os.path.isfile(hit):
                    cands.append(_candidate(hit, source))
    return cands


def _wsl_exe():
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(root, "System32", "wsl.exe")


def wsl_available():
    return os.name == "nt" and os.path.isfile(_wsl_exe())


def wsl_distros():
    """Installed WSL distro names, [] when WSL is absent or empty."""
    if not wsl_available():
        return []
    try:
        out = subprocess.run([_wsl_exe(), "-l", "-q"], capture_output=True,
                             timeout=60,
                             creationflags=procutil.CREATE_NO_WINDOW)
    except Exception:
        return []
    # Exit code is unreliable here (an empty distro list is nonzero on some
    # WSL builds); parse whatever came back instead.
    return [line.strip() for line in _decode(out.stdout or b"").splitlines()
            if line.strip()]


def win_native_root():
    """Per-user root for the guided NATIVE Windows install."""
    from emstudio.setup.solvers import win_install_root
    return os.path.join(win_install_root(), "openfoam")


def _windows_native_candidates():
    """ESI's native (mingw) Windows installs — the PREFERRED Windows route.

    Ours first, then the places a hand-run installer lands. Each candidate
    is identified by the MSYS2 bash beside the tree, because that bash is
    what every later call must go through: the solvers are native .exes but
    their environment only exists inside the shipped shell.
    """
    roots = [win_native_root()]
    for base in (os.environ.get("LOCALAPPDATA", ""),
                 os.environ.get("ProgramFiles", ""),
                 os.path.expanduser("~"), "C:\\"):
        if base:
            roots.extend(sorted(glob.glob(os.path.join(base, "OpenFOAM*"))))
    cands = []
    for root in roots:
        bash = os.path.join(root, WIN_NATIVE_BASH)
        if not os.path.isfile(bash):
            continue
        # The version is in the tree's own directory name; read it from disk
        # rather than assuming our pin, so a hand-installed v2506 is found.
        for tree in sorted(glob.glob(os.path.join(
                root, "msys64", "home", "ofuser", "OpenFOAM",
                "OpenFOAM-v*"))):
            ver = os.path.basename(tree).replace("OpenFOAM-", "")
            posix = "/home/ofuser/OpenFOAM/{0}/etc/bashrc".format(
                os.path.basename(tree))
            cands.append(_Candidate(posix, "win-native:" + root, ver,
                                    fork_of(ver)))
    return cands


def _windows_candidates():
    """Windows: the native install first, then WSL distros.

    Native is preferred because it needs no elevation at all and starts
    instantly; WSL2 remains the fallback (and the only route for parallel
    runs and runtime-compiled code). Probes OUR distro first, then a
    pref-named one, then every other distro — each look is one
    ``wsl -d <distro> bash -c 'ls ...'`` call and a cold distro can take
    seconds to start, so order matters and results are cached by the
    session-level cache in :func:`find_openfoam`.
    """
    native = _windows_native_candidates()
    if any(c.fork == "esi" for c in native):
        return native
    if not wsl_available():
        return native
    ordered = []
    pref = _pref_string(_PREF_WSL_DISTRO_KEY)
    for name in ([WSL_DISTRO] + ([pref] if pref else []) + wsl_distros()):
        if name and name not in ordered:
            ordered.append(name)
    ls_cmd = ("ls -d " + " ".join(p for p, _ in LINUX_BASHRC_GLOBS)
              + " 2>/dev/null")
    cands = []
    for distro in ordered:
        try:
            out = subprocess.run(
                [_wsl_exe(), "-d", distro, "--", "bash", "-c", ls_cmd],
                capture_output=True, timeout=60,
                creationflags=procutil.CREATE_NO_WINDOW)
        except Exception:
            continue
        for line in _decode(out.stdout or b"").splitlines():
            path = line.strip()
            if not path.endswith("etc/bashrc"):
                continue
            source = "wsl:{0}".format(distro)
            # bashrc_version cannot read files inside the distro — fetch the
            # version line through the same wsl call the probe uses later.
            ver = _wsl_bashrc_version(distro, path)
            cands.append(_Candidate(path, source, ver, fork_of(ver)))
        if any(c.fork == "esi" for c in cands):
            break  # a usable-looking install; don't cold-start more distros
    # A non-ESI native install still beats nothing: report it rather than
    # hiding it, exactly as _pick_best does for a Foundation tree.
    return cands + native


def _wsl_bashrc_version(distro, path):
    try:
        out = subprocess.run(
            [_wsl_exe(), "-d", distro, "--", "bash", "-c",
             "grep -m1 '^ *export *WM_PROJECT_VERSION' '{0}' "
             "2>/dev/null".format(path)],
            creationflags=procutil.CREATE_NO_WINDOW,
            capture_output=True, timeout=60)
    except Exception:
        return ""
    m = _VERSION_RE.search(_decode(out.stdout or b""))
    return m.group(1) if m else ""


# --- discovery entry point ---------------------------------------------------

_cache = None


def clear_cache():
    """Forget cached discovery (called by the dialog's Re-detect)."""
    global _cache
    _cache = None


def find_openfoam(refresh=False):
    """Locate and health-check the best OpenFOAM install. Cached per session.

    The capability probe RUNS a solver (~1-2 s natively, longer through a
    cold WSL distro), so results are cached; ``refresh=True`` (or
    :func:`clear_cache`) re-detects — the dialog does that on Re-detect and
    after an install.
    """
    global _cache
    if _cache is not None and not refresh:
        return _cache

    # 1) explicit overrides: FreeCAD pref, then environment. Both name a
    #    bashrc PATH (posix platforms; on Windows the pref names a distro,
    #    handled in _windows_candidates).
    cands = []
    for value, source in ((_pref_string(_PREF_BASHRC_KEY), "pref"),
                          (os.environ.get("EMSTUDIO_OPENFOAM", ""), "env")):
        if value and os.name != "nt" and os.path.isfile(value):
            cands.append(_candidate(value, source))
    if not cands:
        if os.name == "nt":
            cands = _windows_candidates()
        elif sys.platform == "darwin":
            cands = _macos_candidates()
        else:
            cands = _posix_candidates()

    best = _pick_best(cands)
    if best is None:
        _cache = OpenFoamInfo()
        return _cache

    info = OpenFoamInfo(
        bashrc=best.bashrc,
        prefix=os.path.dirname(os.path.dirname(best.bashrc)),
        version=best.version,
        fork=best.fork,
        source=best.source,
        wsl_distro=best.source.split(":", 1)[1]
        if best.source.startswith("wsl:") else "",
    )

    # A native Windows install is driven through the MSYS2 bash it ships;
    # `source` carries the install root so the bash (and the Pstream repair)
    # can be located from the info alone.
    if best.source.startswith("win-native:"):
        info.native_root = best.source.split(":", 1)[1]
        info.prefix = info.native_root
        # Repair BEFORE the probe, for the same reason the installer does
        # (see pstream_repair): a tree whose Pstream cannot load makes the
        # probe report `broken` and teaches nothing about the install.
        #
        # This call is what makes "install MS-MPI, then Re-detect" true.
        # pstream_repair used to run ONLY from run_windows_native_install, so
        # a box that gained MS-MPI after the install had no path back to the
        # parallel build short of a 200 MB reinstall. Re-detect lands here.
        # It writes at most one file, and only when the two builds disagree
        # with what the machine can actually load.
        info.pstream = pstream_repair(info.native_root)

    # 2) runtime probe — ESI candidates only. Sourcing a Foundation bashrc
    #    just to watch our probe fail teaches nothing we don't already know.
    if info.fork == "esi":
        parsed = _run_probe(info.bashrc, info.wsl_distro, info.native_bash)
        if parsed is None:
            info.function_objects = "broken"
        else:
            if parsed["version"]:
                info.version = parsed["version"]
                info.fork = fork_of(parsed["version"])
            if parsed["prefix"]:
                info.prefix = parsed["prefix"]
            info.missing_required = tuple(
                t for t in REQUIRED_TOOLS if t in parsed["missing"])
            info.missing_wanted = tuple(
                t for t in WANTED_TOOLS if t in parsed["missing"])
            info.function_objects = _classify_probe(parsed)

    _cache = info
    return info


def status_note():
    """One user-facing sentence about a found-but-unusable install, or ''.

    This is what turns a puzzling MISSING row into an actionable one: the
    difference between "no OpenFOAM" and "your OpenFOAM is the build whose
    function objects abort" is exactly the difference between running an
    installer and filing a bug on us.
    """
    info = find_openfoam()
    if not info.found or info.usable:
        return ""
    where = "{0} at {1}".format(info.describe(), info.prefix or info.bashrc)
    if info.fork != "esi":
        return ("{0} is the {1} fork — EMStudio's cases need the ESI "
                "(openfoam.com) build; see the install guidance."
                .format(where, "Foundation" if info.fork == "foundation"
                        else "an unidentified"))
    if info.missing_required:
        return ("{0} lacks required tools: {1} — install the complete "
                "'{2}' package.".format(where,
                                        ", ".join(info.missing_required),
                                        APT_PACKAGE))
    if info.function_objects == "defective-sha1":
        return ("{0} aborts on any function object (error in IOstream "
                "\"sha1\" — a known distro packaging defect, not your "
                "setup); install the ESI build instead."
                .format(where))
    if info.function_objects in ("failed", "broken"):
        return ("{0} failed the runtime probe ({1}) — reinstall or point "
                "the '{2}' preference at a working etc/bashrc."
                .format(where, info.function_objects, _PREF_BASHRC_KEY))
    return ""


# --- guided install: Linux / macOS guidance ---------------------------------

def linux_install_lines():
    """The two sudo commands of the ESI route (EMStudio never runs sudo)."""
    return ("curl -s {0} | sudo bash".format(ESI_REPO_SCRIPT_URL),
            "sudo apt-get install -y {0}".format(APT_PACKAGE))


# --- guided install: Windows (WSL2) -----------------------------------------

def windows_wsl_state():
    """('ready'|'not-operational'|'no-wsl', detail_text) — never truncated.

    'ready' means ``wsl --status`` ran and exited 0; anything it printed on
    a failure is passed through IN FULL — a truncated ``wsl --status`` is
    how this project once mis-diagnosed a machine (docs/OPENFOAM_INSTALL.md
    §3).
    """
    if not wsl_available():
        return "no-wsl", ""
    try:
        out = subprocess.run([_wsl_exe(), "--status"], capture_output=True,
                             timeout=60,
                             creationflags=procutil.CREATE_NO_WINDOW)
    except Exception as exc:
        return "not-operational", str(exc)
    text = (_decode(out.stdout or b"") + "\n"
            + _decode(out.stderr or b"")).strip()
    if "invalid command line option" in text.lower():
        # Pre-2004 inbox WSL has no --status AT ALL — it prints its usage and
        # exits 0 (measured on 18362.1256, 2026-08-06), and the parse error
        # fires before any subsystem check, so that answer proves nothing in
        # either direction. Ask something every build answers instead:
        # `wsl -l -q` fails with an "optional component is not enabled"
        # message when the features are off, and a bare "no installed
        # distributions" (exit 1) is still READY — import creates ours.
        try:
            probe = subprocess.run([_wsl_exe(), "-l", "-q"],
                                   capture_output=True, timeout=60,
                                   creationflags=procutil.CREATE_NO_WINDOW)
        except Exception as exc:
            return "not-operational", str(exc)
        ptext = (_decode(probe.stdout or b"") + "\n"
                 + _decode(probe.stderr or b"")).strip()
        if "optional component" in ptext.lower():
            return "not-operational", ptext
        return "ready", ptext
    if out.returncode == 0 and "unable to start" not in text.lower():
        return "ready", text
    return "not-operational", text


def windows_guidance(detail=""):
    """Honest, build-aware text for the one step EMStudio cannot do itself.

    Every other Windows backend unpacks into %LOCALAPPDATA% with no admin
    at all. OpenFOAM cannot: ESI's native Windows binary is advertised but
    its download 404s (measured 2026-08-06, reported upstream), so the
    vendor-preferred WSL2 route is the guided path — and ENABLING WSL2 is
    an Administrator step with a reboot. EMStudio never elevates itself
    (the same rule as never running sudo): it states the command and the
    user runs it. Everything after that step is per-user, no admin.
    """
    try:
        build = sys.getwindowsversion().build
    except Exception:
        build = 0
    lines = ["OpenFOAM on Windows runs inside WSL2 (the vendor's preferred "
             "route; their native Windows download is currently missing "
             "upstream)."]
    if build >= 19041:
        lines += [
            "One-time setup (Administrator + one reboot):",
            "  1. In an elevated PowerShell:  wsl --install --no-distribution",
            "  2. Reboot, reopen FreeCAD, and press Install again.",
            "EMStudio never elevates itself; after this step the install is "
            "per-user with no admin.",
        ]
    elif build >= 18362:
        lines += [
            "This Windows build ({0}) predates the one-command WSL install. "
            "In an elevated PowerShell:".format(build),
            "  1. dism.exe /online /enable-feature "
            "/featurename:Microsoft-Windows-Subsystem-Linux /all /norestart",
            "  2. dism.exe /online /enable-feature "
            "/featurename:VirtualMachinePlatform /all /norestart",
            "  3. Reboot, then install the WSL2 kernel update: "
            + WSL_KERNEL_MSI_URL,
            "  4. wsl --set-default-version 2",
            "Note: WSL2 on Windows 10 1903/1909 needs build 18362.1049 or "
            "later (x64) — run Windows Update first if yours is older.",
            "Then press Install again.",
        ]
    else:
        lines += [
            "This Windows build ({0}) cannot run WSL2 at all (18362+ "
            "required) — update Windows, or run EMStudio's OpenFOAM path "
            "on another machine.".format(build),
        ]
    if detail:
        lines += ["", "wsl --status said:", detail]
    return "\n".join(lines)


def run_windows_native_install(line_callback=None):
    """Download + silently install ESI's native Windows build. Per-user.

    THE PREFERRED Windows route, and the only one needing no elevation at
    all. Measured end-to-end on the Windows VM 2026-08-08: `/S /D=` returns
    exit 0 with no wizard and no UAC prompt (the installer's manifest is
    `asInvoker`), and the probe then passes.

    Two traps this had to learn, both of which produce silent nonsense:

    * **The `/D=` argument must be LAST and UNQUOTED** — NSIS's own rule.
      Passing the command as a LIST lets Python quote it (``"/D=C:\\..."``)
      and NSIS then ignores the target directory entirely, so the install
      lands somewhere else while still reporting success. Hence the single
      command STRING below.
    * **A silent install leaves an unusable tree** until
      :func:`pstream_repair` runs — see that function. Do not reorder it
      after the probe; the probe would simply report ``broken``.
    """
    from emstudio.setup import solvers as _solvers
    from emstudio.solvers.base import SolverError

    def say(line):
        if line_callback:
            line_callback(line)

    if os.name != "nt":
        raise SolverError("the native Windows install only exists on Windows")

    root = win_native_root()
    os.makedirs(os.path.dirname(root), exist_ok=True)
    installer = os.path.join(os.path.dirname(root),
                             "OpenFOAM-{0}-windows-mingw.exe".format(
                                 WIN_NATIVE_VERSION))
    say("downloading ESI's native Windows build (~200 MB)...")
    _solvers._download_archive(WIN_NATIVE_URL, installer, say)

    say("installing silently to {0} (no admin needed)...".format(root))
    # NSIS: /D last, unquoted, absolute. A string, NOT a list — see above.
    cmd = '"{0}" /S /D={1}'.format(installer, root)
    try:
        job = subprocess.run(cmd, capture_output=True, timeout=3600,
                             creationflags=procutil.CREATE_NO_WINDOW)
    except Exception as exc:
        raise SolverError("the installer could not be run: {0}".format(exc))
    if job.returncode != 0:
        raise SolverError(
            "the installer exited {0} — nothing was installed".format(
                job.returncode))
    try:
        os.unlink(installer)
    except OSError:
        pass

    # The repair MUST precede detection (see pstream_repair's docstring).
    status = pstream_repair(root, say)
    if status.startswith("failed"):
        raise SolverError(
            "installed, but the MPI shim could not be repaired ({0}); every "
            "solver would exit 0xC0000135".format(status))

    info = find_openfoam(refresh=True)
    if not info.usable:
        raise SolverError(
            "installed to {0} but the runtime probe is not happy: {1} — "
            "report this".format(root, status_note() or "nothing detected"))
    say("detected: {0}".format(info.describe()))
    if status == "swapped-to-dummy":
        say("NOTE: this install runs SERIAL only. Installing Microsoft MPI "
            "(needs admin) and pressing Re-detect restores parallel runs.")
    return info


def run_windows_install(line_callback=None):
    """Create/complete the EMStudio-owned WSL distro and install OpenFOAM.

    Stages, each idempotent so a retry resumes instead of failing:
      1. WSL2 operational check (raises with :func:`windows_guidance` if
         not — the honest elevation step).
      2. ``wsl --import`` of the pinned Ubuntu rootfs into
         %LOCALAPPDATA%/EMStudio/wsl (per-user, no admin, no Store). The
         download's SHA256 is verified against the pinned digest.
      3. Inside the distro (root by default — no sudo dance): OpenCFD's own
         repo script, then ``apt-get install {APT_PACKAGE}``.
      4. Re-detection with the runtime probe; failure here raises.

    The distro belongs to EMStudio; ``wsl --unregister {WSL_DISTRO}``
    removes it completely.
    """
    from emstudio.setup import solvers as _solvers
    from emstudio.solvers.base import SolverError

    def say(line):
        if line_callback:
            line_callback(line)

    if os.name != "nt":
        raise SolverError("the WSL2 guided install only exists on Windows")

    state, detail = windows_wsl_state()
    if state != "ready":
        raise SolverError(windows_guidance(detail))

    if WSL_DISTRO in wsl_distros():
        say("WSL distro '{0}' already exists — reusing it".format(WSL_DISTRO))
    else:
        root = _solvers.win_install_root()
        os.makedirs(root, exist_ok=True)
        tarball = os.path.join(root, "ubuntu-wsl-rootfs.tar.gz")
        say("downloading Ubuntu WSL rootfs (~340 MB)...")
        _solvers._download_archive(WSL_ROOTFS_URL, tarball, say)
        digest = hashlib.sha256()
        with open(tarball, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != WSL_ROOTFS_SHA256:
            os.unlink(tarball)
            raise SolverError(
                "rootfs download failed its SHA256 check (got {0}) — "
                "refusing to import it; re-run to retry".format(
                    digest.hexdigest()[:16]))
        say("importing as WSL distro '{0}' (no admin needed)...".format(
            WSL_DISTRO))
        distro_dir = os.path.join(os.path.dirname(root), "wsl", "openfoam")
        os.makedirs(distro_dir, exist_ok=True)
        job = subprocess.run(
            [_wsl_exe(), "--import", WSL_DISTRO, distro_dir, tarball],
            capture_output=True, timeout=1800,
            creationflags=procutil.CREATE_NO_WINDOW)
        try:
            os.unlink(tarball)
        except OSError:
            pass
        if job.returncode != 0:
            msg = (_decode(job.stdout or b"") + "\n"
                   + _decode(job.stderr or b"")).strip()
            hint = ""
            if "0x80370102" in msg:
                hint = ("\n\nError 0x80370102 means the WSL2 utility VM "
                        "could not start — on a virtual machine, nested "
                        "virtualization must be enabled on the host.")
            raise SolverError("wsl --import failed:\n" + msg + hint)

    say("installing OpenFOAM inside the distro (OpenCFD's own apt repo; "
        "this is the long step)...")
    in_distro = (
        "set -e\n"
        "if ls -d /usr/lib/openfoam/openfoam*/etc/bashrc >/dev/null 2>&1; "
        "then echo 'OpenFOAM already present'; exit 0; fi\n"
        "export DEBIAN_FRONTEND=noninteractive\n"
        "if ! command -v curl >/dev/null 2>&1; then apt-get update -q; "
        "apt-get install -y -q curl ca-certificates; fi\n"
        # Acquire::Retries matters here: dl.openfoam.com 302s every .deb to
        # SourceForge's rotating mirrors, and a single dead mirror
        # (cfhcable, 2026-08-06 — measured failing on TWO machines the same
        # hour) fails the whole transaction without it. Retries re-hit the
        # redirector, which can hand out a live mirror.
        "curl -s {0} | bash\n"
        "apt-get -o Acquire::Retries=3 install -y -q {1}\n".format(
            ESI_REPO_SCRIPT_URL, APT_PACKAGE))
    job = SolverJobStream([_wsl_exe(), "-d", WSL_DISTRO, "--", "bash", "-c",
                           in_distro], say)
    rc = job.run(timeout=3600)
    if rc != 0:
        raise SolverError(
            "OpenFOAM install inside '{0}' failed (exit {1}) — scroll the "
            "log above; re-running resumes where it left off".format(
                WSL_DISTRO, rc))

    info = find_openfoam(refresh=True)
    if not info.usable:
        raise SolverError(
            "install finished but the runtime probe is not happy: {0} — "
            "report this".format(status_note() or "no install detected"))
    say("detected: {0}".format(info.describe()))
    return info


class SolverJobStream:
    """Minimal line-streaming runner for install steps.

    ``SolverJob`` (solvers/base) assumes UTF-8 text mode; ``wsl.exe`` output
    needs the NUL-sniffing decode above, so this small runner reads raw
    bytes per line and decodes each. Not for solver runs — installs only.
    """

    def __init__(self, cmd, say):
        self.cmd = cmd
        self.say = say

    def run(self, timeout):
        proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                creationflags=procutil.CREATE_NO_WINDOW)
        try:
            import threading
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
            try:
                for raw in iter(proc.stdout.readline, b""):
                    line = _decode(raw).rstrip()
                    if line:
                        self.say(line)
            finally:
                timer.cancel()
            return proc.wait()
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
