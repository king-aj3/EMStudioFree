# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *   EMStudio — FreeCAD RF/electromagnetic simulation workbench            *
# *   Non-GUI init script (runs for both console and GUI sessions).        *
# ***************************************************************************
"""EMStudio App-level init.

Executed by FreeCAD for every session (including headless ``freecadcmd``).

Deliberately minimal and defensive:
* NO use of ``__file__`` — FreeCAD's init machinery does not guarantee it when it
  exec()s this script. FreeCAD adds this Mod directory to ``sys.path`` itself before
  running init scripts, so ``import emstudio`` already resolves.
* Never raise: a failing Init.py can poison the whole module scan. Log instead.
"""

try:
    import emstudio  # noqa: F401  (verifies the package resolves; adds nothing else)
except Exception as exc:  # pragma: no cover - defensive
    try:
        import FreeCAD

        FreeCAD.Console.PrintError("EMStudio Init.py failed: {0}\n".format(exc))
    except Exception:
        pass
