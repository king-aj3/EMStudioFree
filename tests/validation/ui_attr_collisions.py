# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: no dialog attribute shadows a Qt method (the metric() trap).

A QDialog/QWidget subclass that assigns ``self.<name> = QtWidgets.<Widget>(...)``
where ``<name>`` is also an inherited Qt method (e.g. ``metric`` from
QPaintDevice, which Qt calls on EVERY repaint) REPLACES that method with a
non-callable widget. Qt then calls the widget as a function during painting ->
``TypeError: 'QComboBox' object is not callable`` -> and in a GUI build a hard
SIGSEGV (found 2026-07-21: ``self.metric`` in the coverage + multistation
dialogs crashed FreeCAD when a child file dialog forced a repaint).

Pure python3 static scan (no FreeCAD/Qt needed). Pass: exit 0 and
'UI ATTR COLLISION GATE PASSED'.
"""
import glob
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_UI = os.path.join(_ROOT, "emstudio", "ui")

# Inherited Qt method names that Qt itself calls internally (paint / layout /
# event / device-metric / property accessors). Shadowing any of these with a
# widget attribute is a latent crash. Names Qt calls during a normal repaint or
# event dispatch are the dangerous ones.
_QT_METHODS = {
    # QPaintDevice — called on every paint
    "metric", "paintEngine", "devType",
    # QWidget / QObject geometry + property accessors (methods, not fields)
    "font", "palette", "style", "layout", "window", "windowHandle", "cursor",
    "locale", "geometry", "frameGeometry", "rect", "frameSize", "size", "pos",
    "x", "y", "width", "height", "depth", "colorCount", "baseSize", "sizeHint",
    "minimumSizeHint", "parent", "children", "screen", "backingStore",
    "focusWidget", "graphicsEffect", "mask", "actions",
    # QWidget virtuals Qt may invoke
    "heightForWidth", "hasHeightForWidth", "event", "eventFilter",
}

_ASSIGN = re.compile(r"self\.(\w+)\s*=\s*QtWidgets\.\w+\s*\(")


def main():
    failures = []
    for path in sorted(glob.glob(os.path.join(_UI, "*.py"))):
        src = open(path, encoding="utf-8").read()
        for m in _ASSIGN.finditer(src):
            name = m.group(1)
            if name in _QT_METHODS:
                line = src[:m.start()].count("\n") + 1
                failures.append((os.path.relpath(path, _ROOT), line, name))
    for rel, line, name in failures:
        print("  FAIL  {0}:{1}  self.{2} shadows Qt.{2}() — rename it "
              "(e.g. self.{2}_combo)".format(rel, line, name))
    if failures:
        print("UI ATTR COLLISION GATE FAILED: {0} shadowing assignment(s)"
              .format(len(failures)))
        return 1
    print("  ok    no widget attribute shadows a Qt method name "
          "(scanned {0} ui modules)".format(
              len(glob.glob(os.path.join(_UI, "*.py")))))
    print("UI ATTR COLLISION GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("ui attr collision validation failed")
    sys.exit(0)
