# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run a test script against the PRO working tree under a chosen FreeCAD.

    python tests/run_pro_freecad.py tests/smoke.py
    python tests/run_pro_freecad.py tests/gui_smoke.py      # offscreen, automatic
    FREECAD_VER=1.0 python tests/run_pro_freecad.py tests/gui_smoke.py

WHY THIS EXISTS
---------------
``tests/run_pro_freecad.sh`` is the canonical POSIX entry point and this script
does not replace it -- on Linux and macOS it simply execs it, so there is exactly
one implementation of the POSIX logic and no untested duplicate.

What it adds is **Windows**, which had no harness at all. That gap is not
academic: ``gui_smoke.py`` went unrun from v0.80.0 to v0.84.0 -- four releases,
during which ``commands.py`` gained a command and ``ALL_COMMANDS``, and
``installer_dialog.py`` was rewritten -- because the only runner was a bash
script looking for a Linux AppImage in ``~/Downloads``.

A PowerShell harness was written first and is NOT viable on the work box:
Cylance Script Control blocks ``.ps1`` execution outright ("Cylance Script
Control has blocked PowerShell from running", exit 34), both as
``powershell -File`` and dot-sourced in an existing session. Inline commands are
allowed, script FILES are not. Python is unrestricted, so the harness is Python.

WHY AN ISOLATED USER HOME
-------------------------
The work box's two FreeCADs see different EMStudio trees::

    FreeCAD 1.0   %APPDATA%\\FreeCAD\\Mod\\EMStudio         junction -> the Pro repo
    FreeCAD 1.1   %APPDATA%\\FreeCAD\\v1-1\\Mod\\EMStudio    a real EMStudioFree clone
                  %APPDATA%\\FreeCAD\\v1-1\\Mod\\EMStudioPro  the customer Pro overlay

So a bare 1.1 run imports the FREE copy: Pro-only code is absent and ``smoke.py``
fails on a version mismatch that is not a bug. FreeCAD honours
``FREECAD_USER_HOME`` on Windows too (measured 2026-08-05), so we hand it a
throwaway user dir whose only ``Mod`` entry links to this repo. Both installs
stay exactly as they are -- in particular the 1.1 clone keeps working as the
customer's-eye view of the free product, which is the whole reason it is there.

A JUNCTION, NOT A SYMLINK: directory symlinks on Windows need
SeCreateSymbolicLinkPrivilege (admin or Developer Mode) and this is a
corporate-locked box. Junctions need neither, and FreeCAD follows them
identically.

Exit code is FreeCAD's own, so this drops straight into a gate chain.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _exec_posix_script(argv):
    """On Linux/macOS defer to the shell script -- one implementation, not two."""
    sh = os.path.join(_HERE, "run_pro_freecad.sh")
    if not os.path.isfile(sh):
        raise SystemExit("run_pro_freecad: missing {0}".format(sh))
    return subprocess.call(["bash", sh] + argv)


def _find_freecad_windows(fcver, gui):
    """Locate FreeCAD's binaries. Returns a path or raises SystemExit.

    Windows installers use TWO-component versions ("FreeCAD 1.1"), unlike the
    AppImage/DMG names the shell script matches ("FreeCAD_1.1.1-...").
    """
    exe = "FreeCAD.exe" if gui else "freecadcmd.exe"
    roots = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "FreeCAD " + fcver, "bin"),
        os.path.join(os.environ.get("ProgramFiles", ""), "FreeCAD " + fcver, "bin"),
        r"C:\tools\FreeCAD-{0}\bin".format(fcver),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "FreeCAD", "bin"),
    ]
    for root in roots:
        cand = os.path.join(root, exe)
        if os.path.isfile(cand):
            return cand
    raise SystemExit(
        "run_pro_freecad: no FreeCAD {0} ({1}) found. Looked in:\n  {2}".format(
            fcver, exe, "\n  ".join(r for r in roots if r)
        )
    )


def _link_tree(link, target):
    """Point ``link`` at ``target`` without needing elevation."""
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(target, link)
    else:
        os.symlink(target, link)


def _unlink_tree(link):
    """Remove the reparse point WITHOUT following it.

    ``shutil.rmtree`` on a directory containing a junction can descend through
    it and delete the TARGET's contents -- here, the working tree. ``os.rmdir``
    on a junction removes only the reparse point.
    """
    if os.path.isdir(link) and not os.path.islink(link):
        os.rmdir(link)          # junction: removes the link, never the target
    elif os.path.lexists(link):
        os.unlink(link)


def main(argv):
    if not argv:
        raise SystemExit("usage: run_pro_freecad.py <test-script> [more args]")
    if os.name != "nt":
        return _exec_posix_script(argv)

    script, rest = argv[0], argv[1:]

    # EMSTUDIO_TREE drives a BUILT FREE TREE under FreeCAD -- the only way to
    # honour "verify every export under FreeCAD, not just python3" without
    # installing the export over a real Mod dir. It must be ABSOLUTE: the tree
    # is reached through a link planted in a throwaway user home, so a relative
    # path resolves against THAT directory and dangles. FreeCAD then loads no
    # workbench at all and gui_smoke fails on "workbench + command
    # registration" -- which reads exactly like a real registration regression
    # and is not one. Resolve it here and fail loudly instead.
    repo = os.environ.get("EMSTUDIO_TREE") or _ROOT
    if not os.path.isdir(repo):
        raise SystemExit("run_pro_freecad: EMSTUDIO_TREE is not a directory: " + repo)
    repo = os.path.abspath(repo)

    # gui_smoke needs a real QApplication, so it runs the GUI binary with the
    # offscreen platform -- NOT freecadcmd, which has no QApplication and aborts
    # with "QWidget: Must construct a QApplication before a QWidget". smoke.py is
    # the opposite: headless, so freecadcmd. (Windows freecadcmd is already
    # headless and takes no --console flag.)
    gui = "gui_smoke" in os.path.basename(script)
    fcver = os.environ.get("FREECAD_VER", "1.1")
    fcbin = _find_freecad_windows(fcver, gui)

    env = dict(os.environ)
    # In GUI mode FreeCAD routes Console.PrintMessage to the Report View, which
    # does not reach stdout reliably -- a failing gui_smoke can emit nothing but
    # Qt noise and an exit code. gui_smoke persists its log when GUI_SMOKE_LOG is
    # set, so set it ourselves and echo it afterwards. A caller's own value wins.
    log_owned = False
    if gui:
        env["QT_QPA_PLATFORM"] = "offscreen"
        if not env.get("GUI_SMOKE_LOG"):
            fd, path = tempfile.mkstemp(prefix="emstudio-gui-smoke-", suffix=".log")
            os.close(fd)
            env["GUI_SMOKE_LOG"] = path
            log_owned = True

    user_home = tempfile.mkdtemp(prefix="emstudio-pro-fc-")
    link = os.path.join(user_home, "Mod", "EMStudio")
    rc = 1
    try:
        os.makedirs(os.path.dirname(link))
        _link_tree(link, repo)
        env["FREECAD_USER_HOME"] = user_home

        print("run_pro_freecad: freecad -> " + fcbin)
        print("run_pro_freecad: tree    -> " + repo)
        print("run_pro_freecad: isolated FREECAD_USER_HOME=" + user_home)
        print("run_pro_freecad: mode " + ("gui/offscreen" if gui else "console"))
        sys.stdout.flush()

        rc = subprocess.call([fcbin, os.path.join(repo, script)] + rest, env=env)

        if log_owned and os.path.getsize(env["GUI_SMOKE_LOG"]):
            # gui_smoke writes UTF-8; decode it as such rather than the console
            # codepage, or every em-dash in every line comes back mojibake.
            with open(env["GUI_SMOKE_LOG"], "r", encoding="utf-8") as fh:
                sys.stdout.write(fh.read())
    finally:
        if log_owned and os.path.exists(env.get("GUI_SMOKE_LOG", "")):
            os.unlink(env["GUI_SMOKE_LOG"])
        _unlink_tree(link)
        shutil.rmtree(user_home, ignore_errors=True)

    print("run_pro_freecad: exit {0}".format(rc))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
