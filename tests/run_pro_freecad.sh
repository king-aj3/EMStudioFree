#!/usr/bin/env bash
# Run a test script against the PRO working tree under a chosen FreeCAD.
#
# WHY THIS EXISTS
# ---------------
# Since the Pro/Free split (2026-07-27), a bare FreeCAD 1.1.x (every 1.1 build
# shares the v1-1 user dir) loads the Add-on-Manager-installed EMStudioFree from
# ~/.local/share/FreeCAD/v1-1/Mod/EMStudio -- NOT this working tree. That is
# correct and deliberate: 1.1.x shows the customer's view of the free product.
# But it means `import emstudio` under 1.1.x resolves to the free copy, so:
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
#   tests/run_pro_freecad.sh tests/gui_smoke.py        # GUI: Linux offscreen, macOS the desktop session
#   FREECAD_VER=1.1.1 tests/run_pro_freecad.sh tests/smoke.py   # an older build
#
# Exit code is the FreeCAD run's own, so this drops straight into a gate chain.
#
# PLATFORMS
# ---------
# Linux: the FreeCAD AppImage in ~/Downloads. One binary takes --console.
# macOS: /Applications/FreeCAD-<ver>.app, installed by hand from the upstream
#   arm64 DMG (the build host carries 0.21.2, 1.1.1, 1.1.3 and 1.1.4 side by
#   side).
#   Two things differ from Linux and both bite:
#     * The real binaries are Contents/Resources/bin/{freecad,freecadcmd}.
#       Contents/MacOS/FreeCAD is a wrapper script that `cat`s the bundle's
#       conda packages.txt to stdout and then BLOCKS -- unusable in a gate.
#     * There is NO version-suffixed user dir on macOS. 0.21.2 and every 1.1.x
#       all report ~/Library/Application Support/FreeCAD/, so they would share
#       one Mod/. FREECAD_USER_HOME isolation is not a convenience there, it is
#       the only way to test a version independently.
#     * gui_smoke must run in the logged-in DESKTOP (Aqua) session, not Qt's
#       `offscreen` platform. macOS offscreen has no OpenGL ("QOpenGLWidget is
#       not supported on this platform"), so the first 3-D view FreeCAD paints
#       segfaults in Coin3D (glMatrixMode under QuarterWidget::paintEvent) --
#       measured 2026-09-30 on 1.1.1, 1.1.3 and 1.1.4 alike, exit 139. A shell
#       over SSH cannot reach the WindowServer, so the GUI run is loaded into
#       the user's launchd GUI domain (gui/<uid>) as a one-shot job limited to
#       the Aqua session; that needs NO sudo, only that this user is the one
#       logged in at the console (a build Mac should auto-log in). The job
#       inherits nothing, so this shell's environment is written out for it,
#       and its exit code comes back through a file; it stops FreeCAD itself if
#       this runner dies (even by SIGKILL). EMSTUDIO_MAC_GUI=offscreen forces the
#       old path, =aqua refuses to fall back, =auto (the default) falls back to
#       offscreen WITH a warning on a Mac with no desktop session; any other
#       value is refused. EMSTUDIO_AQUA_TIMEOUT (whole seconds, default 3600)
#       bounds the run (exit 124). A tree or working directory inside a
#       privacy-protected folder (~/Desktop, ~/Documents, ~/Downloads, iCloud,
#       an external volume) may need that access granted to the job, or use
#       EMSTUDIO_MAC_GUI=offscreen for a non-GUI check.
set -euo pipefail

# Set up before ANY exit path, so an early refusal cannot leak a temp file.
USERHOME=""
AQUA_LABEL=""
AQUA=0
GUI_LOG_OWNED=0
cleanup() {
  # A desktop-session run cut short (Ctrl-C, SIGTERM, SIGHUP) must not leave
  # FreeCAD loaded in the session: bootout ends the job and what it started.
  # Then show how far it got -- the in-terminal path streamed that live.
  if [ -n "$AQUA_LABEL" ]; then
    launchctl bootout "gui/$(id -u)/$AQUA_LABEL" 2>/dev/null || true
    cat "$USERHOME/.aqua/out" 2>/dev/null || true
  fi
  if [ -n "$USERHOME" ]; then rm -rf "$USERHOME"; fi
  if [ "$GUI_LOG_OWNED" = 1 ]; then rm -f "$GUI_SMOKE_LOG"; fi
}
trap cleanup EXIT

# Which FreeCAD to run. Since 2026-09-30 (AJ's call) the default is the NEWEST
# 1.1.x, because that is what a customer downloads: 1.1.4. (It had stayed on
# 1.1.1 although 1.1.3 was out from 2026-07-25.) 1.1.4 passed smoke +
# gui_smoke on Linux, Windows and macOS (there in the desktop session -- macOS
# OFFSCREEN crashes on every 1.1.x build, see PLATFORMS). Linux wants the AppImage in
# ~/Downloads, macOS /Applications/FreeCAD-<ver>.app.
# This line is the SINGLE SOURCE of the default: the Pro repo's
# tools/check_installed.py and tools/release.py read it, in exactly this
# FCVER="${FREECAD_VER:-X}" form.
FCVER="${FREECAD_VER:-1.1.4}"

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

# gui_smoke needs a real QApplication, so it must run in GUI mode (Qt's
# offscreen platform on Linux; on macOS the desktop session, see PLATFORMS) --
# NOT `--console`, which has no QApplication and aborts
# with "QWidget: Must construct a QApplication before a QWidget" (core dumped).
# smoke.py is the opposite: it is headless and wants the console binary.
GUI=0
case "$SCRIPT" in
  *gui_smoke*) GUI=1; export QT_QPA_PLATFORM=offscreen ;;
esac

# In GUI mode FreeCAD routes Console.PrintMessage to the Report View, and under
# macOS offscreen that never reached stdout -- a failing gui_smoke printed
# nothing but Qt noise and an exit code (in the desktop session the lines DO
# reach the captured output, so a passing run shows each check twice: count
# distinct checks, not lines). gui_smoke already persists its log when
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
      # The desktop session, not offscreen -- see PLATFORMS above.
      MACGUI="${EMSTUDIO_MAC_GUI:-auto}"
      case "$MACGUI" in
        auto|aqua|offscreen) ;;
        *) echo "run_pro_freecad: EMSTUDIO_MAC_GUI must be auto, aqua or offscreen (got '$MACGUI')" >&2; exit 2 ;;
      esac
      AQUA_TIMEOUT="${EMSTUDIO_AQUA_TIMEOUT:-3600}"
      case "$AQUA_TIMEOUT" in
        ''|*[!0-9]*) echo "run_pro_freecad: EMSTUDIO_AQUA_TIMEOUT must be whole seconds (got '$AQUA_TIMEOUT')" >&2; exit 2 ;;
      esac
      if [ "$MACGUI" != offscreen ] \
         && [ "$(stat -f %Su /dev/console 2>/dev/null)" = "$(id -un)" ] \
         && launchctl print "gui/$(id -u)" >/dev/null 2>&1; then
        AQUA=1
        unset QT_QPA_PLATFORM
      elif [ "$MACGUI" = aqua ]; then
        echo "run_pro_freecad: EMSTUDIO_MAC_GUI=aqua, but $(id -un) has no desktop session on this Mac (console: $(stat -f %Su /dev/console 2>/dev/null))" >&2
        exit 2
      elif [ "$MACGUI" = auto ]; then
        echo "run_pro_freecad: WARNING: no desktop session for $(id -un) -- falling back to Qt offscreen, where FreeCAD's 3-D view has no OpenGL and gui_smoke segfaults (exit 139)" >&2
      fi
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

# macOS only: run FreeCAD inside the logged-in desktop session as a one-shot
# launchd job (see PLATFORMS). Returns FreeCAD's own exit code, 124 on a timeout
# (EMSTUDIO_AQUA_TIMEOUT, validated above) and 2 if the job cannot be loaded.
run_in_aqua() {
  local d="$USERHOME/.aqua" uid fc a deadline stale rcv
  uid="$(id -u)"
  mkdir -p "$d"
  case "$d" in
    *[\&\<\>]*)
      echo "run_pro_freecad: temp path '$d' holds an XML-special character; set TMPDIR to a plain path" >&2
      return 2 ;;
  esac
  # A runner killed outright (SIGKILL) cannot boot its job out. Its label ends
  # in its PID, so clear any such leftover whose runner is gone before loading.
  launchctl list 2>/dev/null \
    | awk '$3 ~ /^com\.ajj3\.emstudio\.run_pro_freecad\.[0-9]+$/ {print $3}' \
    | while read -r stale; do
        kill -0 "${stale##*.}" 2>/dev/null \
          || launchctl bootout "gui/$uid/$stale" 2>/dev/null || true
      done
  AQUA_LABEL="com.ajj3.emstudio.run_pro_freecad.$$"
  # The job starts with launchd's bare environment, so hand it this shell's
  # (PATH for the Homebrew solvers, GUI_SMOKE_LOG, PYTHONIOENCODING...) minus
  # the offscreen platform and the SSH plumbing. Unset in a subshell, then
  # `export -p`: filtering its LINES would split a multi-line value.
  ( for a in $(compgen -e); do
      case "$a" in QT_QPA_PLATFORM|SSH_*) unset "$a" 2>/dev/null || true ;; esac
    done
    export -p ) > "$d/env.sh"
  fc="FREECAD_USER_HOME=$(printf %q "$USERHOME") $(printf %q "$FCBIN") $(printf %q "$REPO/$SCRIPT")"
  for a in "$@"; do fc="$fc $(printf %q "$a")"; done
  cat > "$d/run.sh" <<EOF
#!/bin/bash
# ALL of this job's output goes where the runner prints it from -- launchd
# would discard it, so a failure before FreeCAD starts would read as a bare 1.
exec < /dev/null > $(printf %q "$d/out") 2>&1
. $(printf %q "$d/env.sh")
unset QT_QPA_PLATFORM
cd $(printf %q "$PWD") || { echo 1 > $(printf %q "$d/rc"); exit 1; }
$fc &
fcpid=\$!
# End with the runner (PID $$): a runner killed outright -- a Python
# subprocess timeout sends SIGKILL -- would otherwise leave FreeCAD running
# in the desktop session with no time limit at all.
while kill -0 \$fcpid 2>/dev/null; do
  if ! kill -0 $$ 2>/dev/null; then
    kill -TERM \$fcpid 2>/dev/null; sleep 10; kill -KILL \$fcpid 2>/dev/null
    rm -rf $(printf %q "$USERHOME")
    exit 1
  fi
  sleep 2
done
wait \$fcpid
echo \$? > $(printf %q "$d/rc")
EOF
  cat > "$d/job.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$AQUA_LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$d/run.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
</dict></plist>
EOF
  if ! launchctl bootstrap "gui/$uid" "$d/job.plist"; then
    echo "run_pro_freecad: could not load the run into gui/$uid (launchctl bootstrap failed)" >&2
    AQUA_LABEL=""
    return 2
  fi
  deadline=$((SECONDS + 10#$AQUA_TIMEOUT))
  while [ ! -s "$d/rc" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 2; done
  launchctl bootout "gui/$uid/$AQUA_LABEL" 2>/dev/null || true
  AQUA_LABEL=""
  if [ -f "$d/out" ]; then cat "$d/out"; fi
  if [ -s "$d/rc" ]; then
    rcv="$(cat "$d/rc")"
    case "$rcv" in ''|*[!0-9]*) return 1 ;; esac
    return "$rcv"
  fi
  echo "run_pro_freecad: timed out after $AQUA_TIMEOUT s in the desktop session" >&2
  return 124
}

mkdir -p "$USERHOME/Mod"
ln -sfn "$REPO" "$USERHOME/Mod/EMStudio"

echo "run_pro_freecad: freecad -> $FCBIN"
echo "run_pro_freecad: tree -> $REPO"
echo "run_pro_freecad: isolated FREECAD_USER_HOME=$USERHOME"
if [ "$GUI" = 1 ] && [ "$AQUA" = 1 ]; then
  echo "run_pro_freecad: mode gui/aqua (the logged-in desktop session, gui/$(id -u))"
else
  echo "run_pro_freecad: mode $([ "$GUI" = 1 ] && echo gui/offscreen || echo console)"
fi

# macOS ships bash 3.2, where "${MODE[@]}" on an EMPTY array is an unbound
# variable under `set -u` (fixed in bash 4.4). ${MODE[@]+"${MODE[@]}"} expands
# to nothing when unset and to the quoted elements otherwise, on both.
rc=1       # never unset, whatever happens below
set +e
if [ "$GUI" = 1 ] && [ "$AQUA" = 1 ]; then
  run_in_aqua "$@"
  rc=$?
else
  FREECAD_USER_HOME="$USERHOME" "$FCBIN" ${MODE[@]+"${MODE[@]}"} "$REPO/$SCRIPT" "$@" < /dev/null
  rc=$?
fi
set -e

if [ "$GUI_LOG_OWNED" = 1 ] && [ -s "$GUI_SMOKE_LOG" ]; then
  cat "$GUI_SMOKE_LOG"
  rm -f "$GUI_SMOKE_LOG"
fi

echo "run_pro_freecad: exit $rc"
exit $rc
