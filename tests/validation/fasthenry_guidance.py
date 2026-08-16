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
