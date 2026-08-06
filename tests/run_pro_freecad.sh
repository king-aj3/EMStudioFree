#!/usr/bin/env bash
# Run a test script against the PRO working tree under a chosen FreeCAD.
#
# WHY THIS EXISTS
# ---------------
# Since the Pro/Free split (2026-07-27), FreeCAD 1.1.1 loads the
# Add-on-Manager-installed EMStudioFree from
# ~/.local/share/FreeCAD/v1-1/Mod/EMStudioFree -- NOT this working tree. That is
# correct and deliberate: 1.1.1 shows the customer's view of the free product.
# But it means `import emstudio` under 1.1.1 resolves to the free copy, so:
#   * Pro-only code (emstudio/assistant/**) is not importable there at all, and
#   * the Pro tree's smoke test compares this package.xml (0.71.0) against the
#     free clone's version.py (0.70.0) and fails on a mismatch that is not a bug.
#
# The fix is NOT to touch the split install -- that would break the free-side
# testing it exists for. FreeCAD honours FREECAD_USER_HOME, so we give FreeCAD a
# throwaway user dir whose only Mod entry is a symlink to this repo. Both
# installs stay exactly as they are.
#
#   tests/run_pro_freecad.sh tests/smoke.py
#   tests/run_pro_freecad.sh tests/gui_smoke.py        # offscreen, auto
#   FREECAD_VER=1.1.3 tests/run_pro_freecad.sh tests/smoke.py
#
# Exit code is the FreeCAD run's own, so this drops straight into a gate chain.
#
# PLATFORMS
# ---------
# Linux: the FreeCAD AppImage in ~/Downloads. One binary takes --console.
# macOS: /Applications/FreeCAD-<ver>.app, installed by hand from the upstream
#   arm64 DMG (the build host carries 0.21.2, 1.1.1 and 1.1.3 side by side).
#   Two things differ from Linux and both bite:
#     * The real binaries are Contents/Resources/bin/{freecad,freecadcmd}.
#       Contents/MacOS/FreeCAD is a wrapper script that `cat`s the bundle's
#       conda packages.txt to stdout and then BLOCKS -- unusable in a gate.
#     * There is NO version-suffixed user dir on macOS. 0.21.2, 1.1.1 and 1.1.3
#       all report ~/Library/Application Support/FreeCAD/, so they would share
#       one Mod/. FREECAD_USER_HOME isolation is not a convenience there, it is
#       the only way to test a version independently.
set -euo pipefail

# Which FreeCAD to run. Default 1.1.1 keeps every existing caller unchanged.
FCVER="${FREECAD_VER:-1.1.1}"

# EMSTUDIO_TREE lets the same runner drive a BUILT FREE TREE under FreeCAD,
# which is the only way to honour "verify every export under FreeCAD, not
# just python3" without installing the export over the real Mod dir:
#   EMSTUDIO_TREE=/path/to/freetree tests/run_pro_freecad.sh tests/gui_smoke.py
REPO="${EMSTUDIO_TREE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# EMSTUDIO_TREE must be ABSOLUTE. The tree is reached through a symlink planted
# in a throwaway user home under $TMPDIR, so a relative path (EMSTUDIO_TREE=../
# EMStudioFree) resolves against THAT directory and dangles. FreeCAD then loads
# no workbench at all and gui_smoke fails on "workbench + command registration"
# — which reads exactly like a real registration regression and is not one.
# Resolve it here and fail loudly instead.
if [ ! -d "$REPO" ]; then
  echo "run_pro_freecad: EMSTUDIO_TREE is not a directory: $REPO" >&2
  exit 2
fi
REPO="$(cd "$REPO" && pwd)"
SCRIPT="${1:?usage: run_pro_freecad.sh <test-script> [more args]}"
shift || true

# gui_smoke needs a real QApplication, so it must run in GUI mode with the
# offscreen platform -- NOT `--console`, which has no QApplication and aborts
# with "QWidget: Must construct a QApplication before a QWidget" (core dumped).
# smoke.py is the opposite: it is headless and wants the console binary.
GUI=0
case "$SCRIPT" in
  *gui_smoke*) GUI=1; export QT_QPA_PLATFORM=offscreen ;;
esac

# In GUI mode FreeCAD routes Console.PrintMessage to the Report View, and on
# macOS that never reaches stdout -- a failing gui_smoke printed nothing at all
# but Qt noise and an exit code. gui_smoke already persists its log when
# GUI_SMOKE_LOG is set, so set it ourselves and echo it afterwards. An explicit
# GUI_SMOKE_LOG from the caller still wins.
GUI_LOG_OWNED=0
if [ "$GUI" = 1 ] && [ -z "${GUI_SMOKE_LOG:-}" ]; then
  GUI_SMOKE_LOG="$(mktemp -t emstudio-gui-smoke-XXXXXX)"
  export GUI_SMOKE_LOG
  GUI_LOG_OWNED=1
fi

MODE=()
case "$(uname -s)" in
  Darwin)
    APP="/Applications/FreeCAD-${FCVER}.app"
    if [ ! -d "$APP" ]; then
      echo "run_pro_freecad: no $APP -- install it from the upstream arm64 DMG" >&2
      exit 2
    fi
    # Resources/bin, NOT Contents/MacOS/FreeCAD -- see PLATFORMS above.
    if [ "$GUI" = 1 ]; then
      FCBIN="$APP/Contents/Resources/bin/freecad"
    else
      FCBIN="$APP/Contents/Resources/bin/freecadcmd"   # already headless; no --console
    fi
    ;;
  *)
    FCBIN="$(ls -1 "$HOME"/Downloads/FreeCAD_${FCVER}-*.AppImage 2>/dev/null | head -1 || true)"
    if [ -z "$FCBIN" ]; then
      echo "run_pro_freecad: no FreeCAD ${FCVER} AppImage in ~/Downloads" >&2
      exit 2
    fi
    [ "$GUI" = 1 ] || MODE=(--console)
    ;;
esac

USERHOME="$(mktemp -d -t emstudio-pro-fc11-XXXXXX)"
cleanup() { rm -rf "$USERHOME"; }
trap cleanup EXIT

mkdir -p "$USERHOME/Mod"
ln -sfn "$REPO" "$USERHOME/Mod/EMStudio"

echo "run_pro_freecad: freecad -> $FCBIN"
echo "run_pro_freecad: tree -> $REPO"
echo "run_pro_freecad: isolated FREECAD_USER_HOME=$USERHOME"
echo "run_pro_freecad: mode $([ "$GUI" = 1 ] && echo gui/offscreen || echo console)"

# macOS ships bash 3.2, where "${MODE[@]}" on an EMPTY array is an unbound
# variable under `set -u` (fixed in bash 4.4). ${MODE[@]+"${MODE[@]}"} expands
# to nothing when unset and to the quoted elements otherwise, on both.
set +e
FREECAD_USER_HOME="$USERHOME" "$FCBIN" ${MODE[@]+"${MODE[@]}"} "$REPO/$SCRIPT" "$@" < /dev/null
rc=$?
set -e

if [ "$GUI_LOG_OWNED" = 1 ] && [ -s "$GUI_SMOKE_LOG" ]; then
  cat "$GUI_SMOKE_LOG"
  rm -f "$GUI_SMOKE_LOG"
fi

echo "run_pro_freecad: exit $rc"
exit $rc
