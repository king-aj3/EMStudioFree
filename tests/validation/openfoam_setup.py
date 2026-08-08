# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: OpenFOAM discovery, classification and install guidance.

Pass: exit 0 and 'OPENFOAM-SETUP GATE PASSED'.

OpenFOAM is the backend where being WRONG is quiet: the two forks share a
name, a widely-installed distro build passes every existence check and then
aborts on its first function object, and the Windows story lives inside WSL2
where nothing is directly inspectable. So this gate pins the CLASSIFIERS
(fork, version, probe-output triage), the guidance text (the exact commands a
user will paste), and the registry integration — all pure logic, no solver
run, FAST tier. When an install IS present the gate additionally asserts the
live discovery agrees with itself (found-in-the-table == usable), which on
this project's own dev box exercises the defective-v1912 path against the
real defective build.
"""
import os
import re
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    from emstudio.setup import openfoam as of
    from emstudio.setup import solvers

    print("EMStudio OpenFOAM setup gate")

    # --- fork / version classification ------------------------------------
    print(" fork and version classification:")
    for ver, want in (("v2606", "esi"), ("v2512", "esi"), ("v1912", "esi"),
                      ("1912", "esi"), ("2506", "esi"),
                      ("12", "foundation"), ("9", "foundation"),
                      ("v12", "foundation"),
                      ("", "unknown"), ("dev", "unknown")):
        got = of.fork_of(ver)
        check("fork_of({0!r}) == {1}".format(ver, want), got == want,
              "got {0}".format(got))
    check("version rank orders v2512 > v1912 > 12",
          of._version_rank("v2512") > of._version_rank("v1912")
          > of._version_rank("12"))

    # --- bashrc static version parse --------------------------------------
    print(" bashrc parsing:")
    cases = (("export WM_PROJECT_VERSION=v2512\n", "v2512"),
             ("WM_PROJECT_VERSION=v1912\n", "v1912"),
             ("  export WM_PROJECT_VERSION='12'\n", "12"),
             ("# a bashrc with no version line at all\n", ""))
    with tempfile.TemporaryDirectory() as td:
        for i, (content, want) in enumerate(cases):
            p = os.path.join(td, "bashrc{0}".format(i))
            with open(p, "w") as fh:
                fh.write("# preamble\n" + content)
            got = of.bashrc_version(p)
            check("bashrc_version parses {0!r}".format(content.strip()[:40]),
                  got == want, "got {0!r}".format(got))
        check("bashrc_version('' / missing file) == ''",
              of.bashrc_version(os.path.join(td, "nope")) == "")

    # --- candidate ranking -------------------------------------------------
    print(" candidate ranking:")
    esi_new = of._Candidate("/a/etc/bashrc", "apt-esi", "v2512", "esi")
    esi_old = of._Candidate("/b/etc/bashrc", "distro", "v1912", "esi")
    foundation = of._Candidate("/c/etc/bashrc", "apt-foundation", "12",
                               "foundation")
    check("ESI v2512 beats ESI v1912",
          of._pick_best([esi_old, esi_new]) is esi_new)
    check("any ESI beats the Foundation fork",
          of._pick_best([foundation, esi_old]) is esi_old)
    check("a lone Foundation install is still REPORTED (not hidden)",
          of._pick_best([foundation]) is foundation)
    check("no candidates -> None", of._pick_best([]) is None)

    # --- probe transcript triage -------------------------------------------
    # These transcripts are the three real behaviours measured on 2026-08-06:
    # a healthy install, Ubuntu's defective v1912 build (blockMesh PASSES,
    # postProcess dies with the sha1 IOstream error), and outright breakage.
    print(" probe output triage:")

    def triage(text):
        return of._classify_probe(of._parse_probe_output(text))

    healthy = ("OFPROBE:VERSION:v2512\nOFPROBE:PREFIX:/usr/lib/openfoam/"
               "openfoam2512\nOFPROBE:BLOCKMESH:0\nOFPROBE:FUNCOBJ:0\n"
               "OFPROBE:SHA1:no\n")
    defective = ("OFPROBE:VERSION:v1912\nOFPROBE:PREFIX:/usr/share/openfoam\n"
                 "OFPROBE:BLOCKMESH:0\nOFPROBE:FUNCOBJ:1\nOFPROBE:SHA1:yes\n")
    other_fail = ("OFPROBE:VERSION:v2406\nOFPROBE:BLOCKMESH:0\n"
                  "OFPROBE:FUNCOBJ:1\nOFPROBE:SHA1:no\n")
    broken = "OFPROBE:VERSION:v2406\nOFPROBE:BLOCKMESH:1\nOFPROBE:FUNCOBJ:1\n"
    check("healthy transcript -> ok", triage(healthy) == "ok",
          triage(healthy))
    check("the measured v1912 signature -> defective-sha1",
          triage(defective) == "defective-sha1", triage(defective))
    check("function objects failing without sha1 -> failed",
          triage(other_fail) == "failed", triage(other_fail))
    check("blockMesh failing -> broken", triage(broken) == "broken",
          triage(broken))
    parsed = of._parse_probe_output(
        healthy + "OFPROBE:MISSING:snappyHexMesh\nOFPROBE:MISSING:postProcess\n"
        "solver chatter that must be ignored\n")
    check("MISSING markers parsed", parsed["missing"]
          == ["snappyHexMesh", "postProcess"], str(parsed["missing"]))
    check("probe version wins over the static guess",
          parsed["version"] == "v2512")

    # wsl.exe speaks UTF-16-LE; a Linux tool through it speaks UTF-8. The
    # NUL-sniffing decoder must read both.
    utf16 = "Ubuntu\r\nEMStudio-OpenFOAM\r\n".encode("utf-16-le")
    check("UTF-16-LE wsl output decodes",
          "EMStudio-OpenFOAM" in of._decode(utf16))
    check("plain UTF-8 output decodes", of._decode(b"v2512\n") == "v2512\n")

    # --- the probe case itself ---------------------------------------------
    print(" probe case content:")
    files = dict(of._PROBE_FILES)
    cd = files.get("system/controlDict", "")
    check("controlDict carries a functions block (the load-bearing part — "
          "without a function object the defective build looks healthy)",
          "functions" in cd and "systemInfo" in cd)
    check("probe case is complete (controlDict/blockMeshDict/fvSchemes/"
          "fvSolution)",
          set(files) == {"system/controlDict", "system/blockMeshDict",
                         "system/fvSchemes", "system/fvSolution"})
    script = of._probe_script("/x/etc/bashrc")
    check("probe script sources the given bashrc", '"/x/etc/bashrc"' in script)
    check("probe script checks every required tool",
          all(t in script for t in of.REQUIRED_TOOLS))
    check("probe script cleans up its temp dir", "rm -rf" in script)

    # --- install guidance --------------------------------------------------
    print(" install guidance:")
    check("REQUIRED_TOOLS is the documented five (OPENFOAM_REQUIREMENTS.md)",
          of.REQUIRED_TOOLS == ("blockMesh", "surfaceFeatureExtract",
                                "snappyHexMesh", "checkMesh",
                                "buoyantSimpleFoam"))
    check("APT_PACKAGE is version-pinned openfoamVVVV-default",
          re.fullmatch(r"openfoam\d{4}-default", of.APT_PACKAGE) is not None,
          of.APT_PACKAGE)
    l1, l2 = of.linux_install_lines()
    check("line 1 pipes OpenCFD's own repo script through sudo",
          of.ESI_REPO_SCRIPT_URL in l1 and "sudo" in l1, l1)
    check("line 2 installs the pinned package", of.APT_PACKAGE in l2, l2)
    bare = re.compile(r"apt(-get)?\s+install\s+(-y\s+)?openfoam(\s|$)")
    check("guidance never names the defective bare 'openfoam' package",
          not bare.search(l1) and not bare.search(l2)
          and not bare.search(solvers.BACKENDS["openfoam"].manual_hint))
    check("rootfs SHA256 is pinned (64 hex chars)",
          re.fullmatch(r"[0-9a-f]{64}", of.WSL_ROOTFS_SHA256) is not None)
    check("rootfs URL is https and on the /wsl/releases/ path (the sibling "
          "/wsl/<name>/current/ dirs hold no tarballs — verified 2026-08-06)",
          of.WSL_ROOTFS_URL.startswith("https://")
          and "/wsl/releases/" in of.WSL_ROOTFS_URL)
    check("WSL distro name is wsl-argument-safe (no spaces)",
          " " not in of.WSL_DISTRO and of.WSL_DISTRO)

    # --- the native Windows tier (measured on the VM 2026-08-08) -----------
    print(" native Windows tier:")
    check("the native URL carries the VERSION in the FILENAME — the "
          "unversioned name the wiki advertises has 404'd for years",
          "OpenFOAM-{0}-windows-mingw.exe".format(of.WIN_NATIVE_VERSION)
          in of.WIN_NATIVE_URL, of.WIN_NATIVE_URL)
    check("native URL is version-pinned, never /latest/ (v2606 has NO "
          "Windows build; 'latest' is exactly what breaks)",
          "/source/latest/" not in of.WIN_NATIVE_URL
          and of.WIN_NATIVE_VERSION in of.WIN_NATIVE_URL)
    check("the bundled MSYS2 bash path is where the package puts it",
          of.WIN_NATIVE_BASH.replace("\\", "/")
          == "msys64/usr/bin/bash.exe", of.WIN_NATIVE_BASH)
    check("the posix bashrc path matches the pinned version",
          of.WIN_NATIVE_BASHRC
          == "/home/ofuser/OpenFOAM/OpenFOAM-{0}/etc/bashrc".format(
              of.WIN_NATIVE_VERSION), of.WIN_NATIVE_BASHRC)
    check("native_bash is derived from the install root",
          of.OpenFoamInfo(native_root=os.path.join("X", "Y")).native_bash
          == os.path.join("X", "Y", of.WIN_NATIVE_BASH))
    check("no native_root -> no native bash (posix installs are unaffected)",
          of.OpenFoamInfo(bashrc="/usr/lib/openfoam/openfoam2512/etc/bashrc")
          .native_bash == "")

    # THE PSTREAM REPAIR. A silent install leaves the MPI-linked Pstream
    # active with no MS-MPI on the box, so every solver exits 0xC0000135
    # with no message. Exercised against a FIXTURE tree, because the bug is
    # a file-size/identity question, not a Windows question.
    print(" Pstream repair (the 0xC0000135 trap):")
    with tempfile.TemporaryDirectory() as td:
        bindir = os.path.join(td, of.WIN_NATIVE_BINDIR)
        os.makedirs(bindir)
        active = os.path.join(bindir, "libPstream.dll")
        msmpi_b = b"M" * 172544          # the sizes measured on the VM
        dummy_b = b"D" * 36864
        for name, data in (("libPstream.dll", msmpi_b),
                           ("libPstream.dll-msmpi", msmpi_b),
                           ("libPstream.dll-dummy", dummy_b)):
            with open(os.path.join(bindir, name), "wb") as fh:
                fh.write(data)
        real_probe, of._msmpi_present = of._msmpi_present, lambda: False
        try:
            said = []
            res = of.pstream_repair(td, said.append)
            check("with no MS-MPI, the msmpi Pstream is swapped for the dummy",
                  res == "swapped-to-dummy", res)
            check("the active Pstream is now the dummy",
                  os.path.getsize(active) == len(dummy_b))
            check("the msmpi build is kept as a backup (parallel is "
                  "recoverable once MS-MPI is installed)",
                  os.path.isfile(active + ".emstudio-backup-msmpi"))
            check("the swap is EXPLAINED, not silent", bool(said))
            check("re-running is idempotent",
                  of.pstream_repair(td) == "already-serial")
            # ...and it must NOT touch a machine that really has MS-MPI.
            of._msmpi_present = lambda: True
            with open(active, "wb") as fh:
                fh.write(msmpi_b)
            check("with MS-MPI present, the msmpi build is LEFT ALONE",
                  of.pstream_repair(td) == "msmpi-present"
                  and os.path.getsize(active) == len(msmpi_b))
        finally:
            of._msmpi_present = real_probe
    with tempfile.TemporaryDirectory() as td2:
        check("a tree with no Pstream files is left alone, not crashed on",
              of.pstream_repair(td2) == "no-pstream")

    # --- registry integration ----------------------------------------------
    print(" registry integration:")
    check("'openfoam' is a registered backend", "openfoam" in solvers.BACKENDS)
    check("apt_package stays EMPTY (the defective distro package must never "
          "join the one-command sudo line)",
          solvers.BACKENDS["openfoam"].apt_package == "")
    hint = solvers.WINDOWS_HINTS.get("openfoam", "")
    check("Windows hint names the Install button and the honest admin step",
          "Install button" in hint and "Administrator" in hint)
    mac = solvers.MACOS_HINTS.get("openfoam", "")
    check("macOS hint carries the verified tap and the fork warning",
          "gerlero/openfoam" in mac and "Foundation" in mac)
    check("openfoam is NOT a WIN_INSTALL_PLANS zip (its dialog flow is the "
          "WSL one; a plan entry here would shadow it)",
          "openfoam" not in solvers.WIN_INSTALL_PLANS)
    check("Elmer's Windows zip is release-pinned (the rolling funet nightly "
          "was abandoned upstream 2026-08-05)",
          "rel26.1" in solvers.WIN_INSTALL_PLANS["elmer"]["url"])

    # --- live discovery self-consistency ------------------------------------
    # Environment-independent assertions: they hold on a box with no
    # OpenFOAM, a healthy ESI install, OR the defective distro build (this
    # project's dev box — where this path exercises the sha1 triage against
    # the real defective binary).
    print(" live discovery self-consistency:")
    rich = of.find_openfoam(refresh=True)
    table = solvers.find_backend("openfoam")
    check("Solver Setup 'found' means USABLE, exactly",
          table.found == rich.usable,
          "table={0} usable={1}".format(table.found, rich.usable))
    if rich.found and not rich.usable:
        note = of.status_note()
        check("a found-but-unusable install explains itself", bool(note),
              "" if note else "status_note() is empty")
    if rich.usable:
        check("a usable install carries fork=esi and a version",
              rich.fork == "esi" and bool(rich.version))

    # --- Windows-only surface refuses elsewhere -----------------------------
    if os.name != "nt":
        try:
            of.run_windows_install()
            check("run_windows_install refuses off Windows", False,
                  "did not raise")
        except Exception as exc:
            check("run_windows_install refuses off Windows",
                  "Windows" in str(exc), str(exc)[:60])

    if FAILURES:
        print("OPENFOAM-SETUP GATE FAILED: {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("OPENFOAM-SETUP GATE PASSED")
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
        raise SystemExit("openfoam-setup validation failed")
    sys.exit(0)
