# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *   EMStudio — FreeCAD RF/electromagnetic simulation workbench            *
# *   GUI init script: registers the workbench, its toolbar and menu.       *
# ***************************************************************************
"""EMStudio GUI init.

Executed by FreeCAD only when the GUI is up. Defines a pure-Python ``Workbench`` whose
``GetClassName`` returns ``"Gui::PythonWorkbench"``.

Hard-learned constraints of the InitGui.py environment:
* ``__file__`` is NOT guaranteed — never touch it here. All paths are resolved through
  the ``emstudio`` package (FreeCAD puts this Mod directory on ``sys.path`` before
  exec'ing init scripts).
* Exceptions raised here are swallowed by FreeCAD and the workbench silently never
  appears — so everything is wrapped and logged to the Console.
"""

import FreeCAD
import FreeCADGui


class EMStudioWorkbench(FreeCADGui.Workbench):
    """RF / electromagnetic modeling and simulation."""

    MenuText = "EMStudio"
    ToolTip = "RF / electromagnetic modeling and simulation (openEMS, NEC2, Elmer, Palace)"

    def __init__(self):
        # Resolve the icon through the package, never through __file__.
        try:
            from emstudio.resources import icon_path

            self.__class__.Icon = icon_path("emstudio_workbench.svg")
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "EMStudio: could not resolve workbench icon: {0}\n".format(exc)
            )

    def Initialize(self):
        """Load commands and build the grouped toolbars/menus. Runs once, lazily."""
        try:
            from emstudio import commands

            commands.register()
            # One toolbar + one EMStudio submenu per logical group, so the (now
            # 28+) commands are presented in sections rather than one long strip.
            for name, cmds in commands.COMMAND_GROUPS:
                group = list(cmds)
                self.appendToolbar("EMStudio " + name, group)
                self.appendMenu(["EMStudio", name], group)
            # Optional paid extension. A SEPARATE top-level module, never a
            # subpackage of this repo — see docs/PRO_IMPLEMENTATION.md.
            #
            # The except is deliberately BROAD. ImportError alone is not
            # enough: a Pro module that raises anything at all during
            # register() would propagate out of Initialize(), FreeCAD would
            # swallow it, and the WHOLE WORKBENCH would silently vanish from
            # the GUI — taking the free core down with it. A paid add-on must
            # never be able to do that.
            try:
                import emstudio_pro

                emstudio_pro.register(self)
                FreeCAD.Console.PrintLog("EMStudio Pro registered.\n")
            except ImportError:
                pass                     # free tier — the normal path
            except Exception as pro_exc:  # noqa: BLE001
                FreeCAD.Console.PrintError(
                    "EMStudio: the Pro extension failed to load and was "
                    "skipped; the free workbench is unaffected: {0}\n".format(
                        pro_exc))
            FreeCAD.Console.PrintLog("EMStudio workbench initialized.\n")
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "EMStudio: workbench initialization failed: {0}\n".format(exc)
            )
            import traceback

            FreeCAD.Console.PrintError(traceback.format_exc() + "\n")

    def Activated(self):
        FreeCAD.Console.PrintLog("EMStudio workbench activated.\n")
        # legal + development-status notice — best-effort, must never break
        # activation. The console line prints EVERY activation; the dialog
        # below fires once per installed version.
        try:
            from emstudio import legal
            from emstudio.version import __version__

            FreeCAD.Console.PrintMessage(legal.console_banner(__version__))
        except Exception:
            pass
        # Once per installed version: the intended-use / under-development /
        # no-liability notice, so an Add-on Manager user who never opens the
        # repo still reads the terms. Reachable afterwards from EMStudio →
        # Help → About / Legal notice.
        try:
            from emstudio.ui.about_dialog import maybe_show_first_run_notice

            # keep a reference so the non-modal dialog is not garbage-collected
            self._notice_dlg = maybe_show_first_run_notice(
                FreeCADGui.getMainWindow()) or getattr(self, "_notice_dlg", None)
        except Exception as exc:
            FreeCAD.Console.PrintLog(
                "EMStudio: first-run notice skipped: {0}\n".format(exc))
        # First activation only: offer the solver-setup wizard when backends
        # are missing. Best-effort — must never break workbench activation.
        try:
            from emstudio.ui.installer_dialog import maybe_show_first_run

            # keep a reference so the non-modal dialog is not garbage-collected
            self._installer_dlg = maybe_show_first_run(
                FreeCADGui.getMainWindow()) or getattr(self, "_installer_dlg", None)
        except Exception as exc:
            FreeCAD.Console.PrintLog(
                "EMStudio: first-run installer check skipped: {0}\n".format(exc)
            )

    def Deactivated(self):
        FreeCAD.Console.PrintLog("EMStudio workbench deactivated.\n")

    def GetClassName(self):
        return "Gui::PythonWorkbench"


try:
    FreeCADGui.addWorkbench(EMStudioWorkbench())
except Exception as _exc:  # pragma: no cover - defensive
    FreeCAD.Console.PrintError("EMStudio: addWorkbench failed: {0}\n".format(_exc))
