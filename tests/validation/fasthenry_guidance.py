# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: FastHenry is Automation-only on Windows — say so, don't detect it.

Pass: exit 0 and 'FASTHENRY-GUIDANCE GATE PASSED'.

WHY THIS EXISTS. The FastFieldSolvers Windows bundle installs FastHenry2.exe,
and a user who installs it reasonably expects EMStudio to find it. AJ did,
2026-08-13. It cannot be used: EMStudio drives solvers as SUBPROCESSES, and
FastHenry2.exe is an Automation (COM) application. Their own History.txt,
shipped beside the binary, records version 3.0 (2004/12/10) — "Removed the
possibility to pass arguments to FastHenry when launching from the command
line (must use Automation)". Measured on an installed copy the same day: both
`-help` and a real .inp deck hang with no output and no Zc.mat.

So there are TWO properties here and they pull in opposite directions:

* Detection must NOT learn that binary. Reporting FastHenry "found" would be
  worse than the bug it fixes — every solve would then hang to its timeout.
* The GUIDANCE must explain the situation, because a bare MISSING beside an
  installed program reads as a detection fault. The hint used to make it worse
  by saying "Install it, then point EMStudio at fasthenry.exe", a file that
  bundle does not contain.

Pure logic, no binary and no solver run — FAST tier. The bundle's real install
directory is simulated with a temp dir, so this gate asserts the same thing on
Linux CI as on the Windows box where the bug was found.
"""
import os
import shutil
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
    from emstudio.setup import solvers
    from emstudio.solvers.base import SolverError

    print("EMStudio FastHenry guidance gate")

    # --- detection must NOT be taught the Automation binary ----------------
    print(" detection contract:")
    execs = tuple(solvers.BACKENDS["fasthenry"].executables)
    # Positive form FIRST: pin what the tuple IS, so this cannot pass merely
    # because some spelling of the forbidden name failed to appear.
    check("executables are exactly the CLI name",
          execs == ("fasthenry",),
          "executables={0!r}".format(execs))
    lowered = " ".join(execs).lower()
    check("no FastHenry2 binary in the detection candidates",
          "fasthenry2" not in lowered,
          "detecting it would report FastHenry usable and hang every solve")

    # --- the status note --------------------------------------------------
    print(" status note:")
    real_name, real_dirs = os.name, solvers._FFS_DIRS
    tmp = tempfile.mkdtemp(prefix="ffs_")
    try:
        # (a) a bundle IS installed -> explain, and name where it is
        with open(os.path.join(tmp, "FastHenry2.exe"), "wb") as fh:
            fh.write(b"not a real binary")
        os.name = "nt"
        solvers._FFS_DIRS = (tmp,)
        note = solvers.fasthenry_status_note()
        check("installed bundle produces a note", bool(note))
        check("the note says WHERE it is", tmp in note,
              "a note that does not name the install is not an explanation")
        check("the note gives the REASON", "utomation" in note,
              "note={0!r}".format(note[:80]))

        # (b) nothing installed -> silence, not a phantom diagnosis
        solvers._FFS_DIRS = (os.path.join(tmp, "nope"),)
        check("no bundle -> no note", solvers.fasthenry_status_note() == "")

        # (c) off Windows the bundle cannot exist -> silence
        solvers._FFS_DIRS = (tmp,)
        os.name = "posix"
        check("off Windows -> no note", solvers.fasthenry_status_note() == "")
    finally:
        os.name, solvers._FFS_DIRS = real_name, real_dirs
        try:
            os.remove(os.path.join(tmp, "FastHenry2.exe"))
            os.rmdir(tmp)
        except OSError:
            pass

    # --- the Windows hint -------------------------------------------------
    print(" windows hint:")
    hint = solvers.WINDOWS_HINTS["fasthenry"]
    check("hint explains the Automation limit", "utomation" in hint)
    check("hint offers a route that actually works",
          "WSL2" in hint or "wsl2" in hint or "source" in hint)
    # The exact wrong instruction that shipped, pinned so it cannot return.
    check("hint no longer sends users to a bundle fasthenry.exe",
          "point EMStudio at fasthenry.exe" not in hint)

    # --- the native-Windows source build ----------------------------------
    # The vendor binary can never work, so on Windows the ONLY route to a
    # usable FastHenry is compiling one. That recipe is four measured changes
    # (2026-08-13); each is pinned here because getting one wrong yields a
    # binary that builds and is subtly wrong, not a build that fails.
    print(" windows source build — flags:")
    win = solvers.FASTHENRY_WIN_CFLAGS
    check("windows flags DROP -DFOUR", "-DFOUR" not in win,
          "it pulls <sys/resource.h>, which mingw does not have")
    # Paired positively, so the check above cannot pass by the flag string
    # simply having been emptied or renamed.
    missing = [f for f in solvers.FASTHENRY_REQUIRED_FLAGS if f not in win]
    check("windows flags KEEP every required flag", not missing,
          "missing {0}".format(missing) if missing else win)
    check("windows flags are DERIVED from the POSIX set",
          win == " ".join(f for f in solvers.FASTHENRY_CFLAGS.split()
                          if f != "-DFOUR"),
          "a second hand-written flag list cannot be gated — see "
          "FASTHENRY_CFLAGS on why this is one constant")

    print(" windows source build — patch discipline:")
    real_src = {
        "induct.c": "int matherr(exc)\nstruct exception *exc;\n{ return 0; }\n",
        "parse_command_line.c": "void f(void)\n{\n  long clock;\n  time(&clock);\n}\n",
        "Makefile": solvers.FASTHENRY_WIN_MAKE_ANCHOR + "\n\nfasthenry:\n\techo hi\n",
    }

    def _tree(files):
        d = tempfile.mkdtemp(prefix="fhsrc_")
        for name, body in files.items():
            with open(os.path.join(d, name), "w", encoding="latin-1") as fh:
                fh.write(body)
        return d

    d1 = _tree(real_src)
    try:
        solvers.prepare_fasthenry_win_source(d1)
        got = {n: open(os.path.join(d1, n), encoding="latin-1").read()
               for n in ("induct.c", "parse_command_line.c", "Makefile")}
        check("matherr renamed out of mingw's way",
              "fh_unused_matherr" in got["induct.c"]
              and "int matherr(exc)" not in got["induct.c"])
        check("long clock -> time_t clock (the LLP64 bug)",
              "time_t clock;" in got["parse_command_line.c"]
              and "long clock;" not in got["parse_command_line.c"])
        check("shim linked via NONUNIOBJS", "win_compat.o" in got["Makefile"])
        check("shim source written",
              os.path.isfile(os.path.join(d1, "win_compat.c")))
        # Running twice must not double-patch or throw.
        solvers.prepare_fasthenry_win_source(d1)
        again = open(os.path.join(d1, "Makefile"), encoding="latin-1").read()
        check("re-running is idempotent", again.count("win_compat.o") == 1,
              "a wizard retry must resume, not corrupt the tree")
    finally:
        shutil.rmtree(d1, ignore_errors=True)

    # THE LOAD-BEARING ONE: an anchor that no longer matches exactly once must
    # STOP the build. A patch applied to the wrong line compiles.
    moved = dict(real_src)
    moved["induct.c"] = real_src["induct.c"] + "\nint matherr(exc)\n"
    d2 = _tree(moved)
    try:
        raised = False
        try:
            solvers.prepare_fasthenry_win_source(d2)
        except SolverError:
            raised = True
        check("a duplicated anchor REFUSES to patch", raised,
              "upstream moving the line must fail loudly, not patch blind")
    finally:
        shutil.rmtree(d2, ignore_errors=True)

    d3 = _tree({k: v for k, v in real_src.items() if k != "Makefile"})
    try:
        raised = False
        try:
            solvers.prepare_fasthenry_win_source(d3)
        except SolverError:
            raised = True
        check("a missing Makefile REFUSES", raised)
    finally:
        shutil.rmtree(d3, ignore_errors=True)

    # --- the STAGED self-hosted install plan --------------------------------
    # Redistribution was unblocked 2026-08-13/19 (vendor grant, see
    # docs/launch/fasthenry-2003-licence-resolution.md), but the release asset
    # publishes only after the M.I.T. TLO answers. Until then the plan is
    # STAGED: complete, valid, and deliberately NOT in WIN_INSTALL_PLANS — a
    # live Install button whose URL 404s is worse than none. These checks keep
    # the staged entry ready-to-activate; at activation, move the entry into
    # WIN_INSTALL_PLANS, flip the "not live" check below to membership, and add
    # "Install button" to WINDOWS_HINTS["fasthenry"] (the smoke gate enforces
    # that wording for every live plan).
    print(" staged install plan:")
    staged = solvers.FASTHENRY_WIN_INSTALL_STAGED
    check("staged plan is complete",
          bool(staged.get("url")) and bool(staged.get("estimate"))
          and bool(staged.get("proof")))
    check("staged plan is SELF-hosted",
          staged.get("url", "").startswith(solvers.SELF_HOSTED_PREFIX),
          "we are the distributor; an upstream URL here would be a lie")
    check("proof is the managed-layout binary",
          staged.get("proof") == os.path.join("bin", "fasthenry.exe"),
          "detection probes <root>/fasthenry/bin — a flat zip would install "
          "somewhere detection never looks")
    offer = staged.get("source_offer", "")
    bin_tag = solvers._release_tag(staged.get("url", ""))
    src_tag = solvers._release_tag(offer)
    check("source offer rides the SAME release tag",
          offer.startswith("https://") and bin_tag and bin_tag == src_tag,
          "binary tag {0!r} vs source tag {1!r}".format(bin_tag, src_tag))
    sha = staged.get("sha256", "")
    check("sha256 pin is a real digest",
          len(sha) == 64 and all(c in "0123456789abcdef" for c in sha.lower()),
          "sha256={0!r}".format(sha[:20]))
    check("staged means NOT live",
          "fasthenry" not in solvers.WIN_INSTALL_PLANS,
          "the TLO hold: activation is a deliberate step, not a drive-by — "
          "flip this check to membership when activating")
    # The dist tool and the staged plan must agree on tag and zip name, or the
    # uploaded asset and the pinned URL drift apart. The tool is Pro-repo
    # only — but in the PRO repo (identified by the exporter's presence) its
    # absence must FAIL, not skip: a silent skip is exactly how a rename
    # would disarm these drift guards.
    tool_path = os.path.join(_ROOT, "tools", "build_fasthenry_dist.py")
    if os.path.isfile(os.path.join(_ROOT, "tools", "export_free.py")):
        check("the dist tool exists in the Pro repo",
              os.path.isfile(tool_path),
              "renaming tools/build_fasthenry_dist.py silently disarms the "
              "tag/zip-name drift guards below")
    if os.path.isfile(tool_path):
        sys.path.insert(0, os.path.dirname(tool_path))
        try:
            import build_fasthenry_dist as _bfd
            check("dist tool and staged plan agree on the release tag",
                  bin_tag == _bfd.RELEASE_TAG,
                  "plan {0!r} vs tool {1!r}".format(bin_tag, _bfd.RELEASE_TAG))
            check("dist tool and staged plan agree on the zip name",
                  staged["url"].endswith("/" + _bfd.BIN_ZIP))
        finally:
            sys.path.remove(os.path.dirname(tool_path))

    # --- sha256 verification in run_win_install (nt-only, real pipeline) ----
    # The staged plan is the first pinned one, so the pin must actually bind:
    # a wrong hash refuses BEFORE extraction and leaves nothing behind.
    if os.name == "nt":
        print(" download pinning (run_win_install):")
        import zipfile as _zipfile

        tmp_root = tempfile.mkdtemp(prefix="fh_pin_")
        fake_zip = os.path.join(tmp_root, "fake.zip")
        with _zipfile.ZipFile(fake_zip, "w") as zf:
            zf.writestr("bin/fasthenry.exe", "@echo off\r\n")
        # ⚠ Computed INDEPENDENTLY of solvers._file_sha256 — an expectation
        # produced by the function under test is circular: swap its hashlib
        # algorithm and sha-vs-same-sha still matches, while in production
        # every pinned install would refuse forever against the published
        # 64-hex sha256 literal.
        import hashlib as _hashlib
        with open(fake_zip, "rb") as fh:
            good_sha = _hashlib.sha256(fh.read()).hexdigest()
        base_plan = {
            "estimate": "test",
            "url": "file:///" + fake_zip.replace("\\", "/"),
            "proof": os.path.join("bin", "fasthenry.exe"),
        }
        orig_root = solvers.win_install_root
        orig_pref = solvers._pref_path
        orig_path = os.environ.get("PATH", "")
        orig_env = os.environ.pop("EMSTUDIO_FASTHENRY", None)
        try:
            managed = os.path.join(tmp_root, "managed")
            solvers.win_install_root = lambda: managed
            solvers._pref_path = lambda _key: ""
            os.environ["PATH"] = ""

            # (a) correct pin, UPPERCASE on purpose: comparison must normalise.
            lines = []
            plan = dict(base_plan, sha256=good_sha.upper())
            info = solvers.run_win_install("fasthenry",
                                           line_callback=lines.append,
                                           _plan=plan)
            check("correct pin installs and detection sees it",
                  info.found and info.path.startswith(managed),
                  repr(info))
            check("the pin was actually checked",
                  any("verifying sha256" in ln for ln in lines))
            # Positive anchor for the literal the wrong-pin ordering check
            # below matches against. Without this pairing, rewording
            # say("extracting...") turns that must-NOT-contain check vacuous
            # forever — the exact silent decay the gate conventions forbid.
            check("extraction is logged on the success path",
                  any("extracting" in ln for ln in lines),
                  "if this wording changes, update the ordering check below "
                  "IN THE SAME COMMIT")
            shutil.rmtree(managed, ignore_errors=True)

            # (b) wrong pin refuses, BEFORE extraction, leaving nothing.
            bad = ("0" if good_sha[0] != "0" else "1") + good_sha[1:]
            lines = []
            raised = False
            try:
                solvers.run_win_install("fasthenry",
                                        line_callback=lines.append,
                                        _plan=dict(base_plan, sha256=bad))
            except SolverError:
                raised = True
            check("wrong pin REFUSES to install", raised,
                  "a hash that does not bind is decoration")
            check("refusal happens BEFORE extraction",
                  not any("extracting" in ln for ln in lines),
                  "extraction is the first step that feeds untrusted bytes "
                  "to code; verify-then-extract is the order that matters")
            check("refusal leaves no install behind",
                  not os.path.isdir(os.path.join(managed, "fasthenry")))

            # (c) a plan WITHOUT a pin still installs — elmer/gmsh point at
            # upstream URLs whose bytes legitimately shift; pinning is opt-in.
            lines = []
            info = solvers.run_win_install("fasthenry",
                                           line_callback=lines.append,
                                           _plan=dict(base_plan))
            check("unpinned plans keep working", info.found, repr(info))
        finally:
            solvers.win_install_root = orig_root
            solvers._pref_path = orig_pref
            os.environ["PATH"] = orig_path
            if orig_env is not None:
                os.environ["EMSTUDIO_FASTHENRY"] = orig_env
            shutil.rmtree(tmp_root, ignore_errors=True)

    print(" windows source build — offer only what can run:")
    real_tc = solvers.win_build_toolchain
    try:
        solvers.win_build_toolchain = lambda: (None, None)
        check("no compiler -> no Build button",
              solvers.win_source_build_plan("fasthenry") is None
              if os.name == "nt" else True,
              "an offered button that cannot run is worse than none")
        note = solvers.win_build_toolchain_note()
        check("no compiler -> the note says how to get one",
              ("pacman" in note) if os.name == "nt" else note == "",
              note[:70])
        solvers.win_build_toolchain = lambda: ("cc.exe", "make.exe")
        check("with a compiler -> no complaint",
              solvers.win_build_toolchain_note() == "")
    finally:
        solvers.win_build_toolchain = real_tc

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("FASTHENRY-GUIDANCE GATE PASSED")
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
        raise SystemExit("fasthenry-guidance validation failed")
    sys.exit(0)
