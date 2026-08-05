# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD GUI command definitions for EMStudio.

Only imported when the GUI is up (from ``InitGui.py``). Commands stay thin: they
delegate to the Qt-free logic in ``emstudio.objects`` / ``emstudio.solvers`` /
``emstudio.setup`` so behavior is unit-testable headlessly.

Selection-driven workflow (CENOS-style, no task panels yet): select geometry, then
click Material/Port — the selection becomes the object's ``References``.
"""

from __future__ import annotations

import FreeCAD
import FreeCADGui

from emstudio.resources import icon_path

CMD_ANALYSIS = "EMStudio_Analysis"
CMD_ANTENNA_FROM_SEL = "EMStudio_AntennaFromSelection"
CMD_MATERIAL = "EMStudio_Material"
CMD_PORT = "EMStudio_LumpedPort"
CMD_COIL = "EMStudio_Coil"
CMD_SOLVER_NEC2 = "EMStudio_SolverNEC2"
CMD_SOLVER_OPENEMS = "EMStudio_SolverOpenEMS"
CMD_SOLVER_ELMER = "EMStudio_SolverElmer"
CMD_SOLVER_PALACE = "EMStudio_SolverPalace"
CMD_RUN = "EMStudio_RunSolver"
CMD_TPL_DIPOLE = "EMStudio_TemplateDipole"
CMD_TPL_MONOPOLE = "EMStudio_TemplateMonopole"
CMD_TPL_PATCH = "EMStudio_TemplatePatch"
CMD_TPL_INDUCTION = "EMStudio_TemplateInduction"
CMD_TPL_WPT = "EMStudio_TemplateWpt"
CMD_TPL_SOLENOID3D = "EMStudio_TemplateSolenoid3D"
CMD_TPL_CAVITY = "EMStudio_TemplateCavity"
CMD_TPL_CYLCAVITY = "EMStudio_TemplateCylCavity"
CMD_TPL_WAVEGUIDE = "EMStudio_TemplateWaveguide"
CMD_TPL_CIRCWG = "EMStudio_TemplateCircWaveguide"
CMD_TPL_COAX = "EMStudio_TemplateCoax"
CMD_TPL_MSL = "EMStudio_TemplateMsl"
CMD_SWEEP_GAP = "EMStudio_SweepGap"
# the Cable Designer keeps the historical id so saved user toolbars stay valid
CMD_LITZ = "EMStudio_LitzDesigner"
CMD_ELEMENT = "EMStudio_ElementDesigner"
CMD_SMALL_ANTENNA = "EMStudio_SmallAntenna"
CMD_TPL_COSITE_PAIR = "EMStudio_TemplateCositePair"
CMD_ISOLATION = "EMStudio_IsolationMatrix"
CMD_COSITE = "EMStudio_Cosite"
CMD_LINK = "EMStudio_LinkBudget"
CMD_COVERAGE = "EMStudio_Coverage"
CMD_MULTICOVERAGE = "EMStudio_MultiCoverage"
CMD_DETECT = "EMStudio_DetectSolvers"
CMD_ABOUT = "EMStudio_About"
CMD_LEGAL = "EMStudio_Legal"
CMD_LICENCE = "EMStudio_Licence"

ALL_COMMANDS = [
    CMD_ANTENNA_FROM_SEL,
    CMD_ANALYSIS,
    CMD_MATERIAL,
    CMD_PORT,
    CMD_COIL,
    CMD_SOLVER_NEC2,
    CMD_SOLVER_OPENEMS,
    CMD_SOLVER_ELMER,
    CMD_SOLVER_PALACE,
    CMD_RUN,
    "Separator",
    CMD_TPL_DIPOLE,
    CMD_TPL_MONOPOLE,
    CMD_TPL_PATCH,
    CMD_TPL_INDUCTION,
    CMD_TPL_WPT,
    CMD_TPL_SOLENOID3D,
    CMD_TPL_CAVITY,
    CMD_TPL_CYLCAVITY,
    CMD_TPL_WAVEGUIDE,
    CMD_TPL_CIRCWG,
    CMD_TPL_COAX,
    CMD_TPL_MSL,
    CMD_TPL_COSITE_PAIR,
    CMD_SWEEP_GAP,
    CMD_LITZ,
    CMD_ELEMENT,
    CMD_SMALL_ANTENNA,
    CMD_ISOLATION,
    CMD_COSITE,
    CMD_LINK,
    CMD_COVERAGE,
    CMD_MULTICOVERAGE,
    "Separator",
    CMD_DETECT,
    "Separator",
    CMD_LICENCE,
    CMD_ABOUT,
    CMD_LEGAL,
]

# Logical groupings for the toolbar and menu. FreeCAD toolbars are flat, so each
# group becomes its OWN toolbar ("EMStudio Analysis", "EMStudio Templates", …) —
# that is how a workbench presents grouped/sectioned tools — and its own submenu
# under the EMStudio menu. ``COMMAND_GROUPS`` is the single source of truth for the
# GUI layout; a smoke check asserts it covers exactly the registered commands.
COMMAND_GROUPS = [
    ("Analysis", [
        CMD_ANTENNA_FROM_SEL, "Separator",
        CMD_ANALYSIS, CMD_MATERIAL, CMD_PORT, CMD_COIL, "Separator",
        CMD_SOLVER_NEC2, CMD_SOLVER_OPENEMS, CMD_SOLVER_ELMER, CMD_SOLVER_PALACE,
        "Separator", CMD_RUN, CMD_SWEEP_GAP,
    ]),
    ("Templates", [
        # antennas
        CMD_TPL_DIPOLE, CMD_TPL_MONOPOLE, CMD_TPL_PATCH, CMD_TPL_COSITE_PAIR,
        "Separator",
        # waveguide / resonator / transmission-line RF
        CMD_TPL_CAVITY, CMD_TPL_CYLCAVITY, CMD_TPL_WAVEGUIDE, CMD_TPL_CIRCWG,
        CMD_TPL_COAX, CMD_TPL_MSL,
        "Separator",
        # magnetics
        CMD_TPL_INDUCTION, CMD_TPL_WPT, CMD_TPL_SOLENOID3D,
    ]),
    # §1 and §2: designing ONE thing.
    ("Tools", [
        CMD_LITZ, CMD_ELEMENT, CMD_SMALL_ANTENNA,
        CMD_LINK, CMD_COVERAGE, CMD_MULTICOVERAGE,
    ]),
    # §7 and §5: designing a SYSTEM of them. Grouped together (S7) because the
    # user question is different — not "what shape is this antenna" but "how do
    # these pieces work together". In EMStudioFree the matching/array/RFDF
    # entries are absent and this group holds the co-site pair; EMStudio Pro
    # adds them back through the emstudio_pro extension point.
    ("System", [
        "Separator",
        CMD_ISOLATION, CMD_COSITE,
    ]),
    ("Setup", [
        CMD_DETECT,
    ]),
    # Help is LAST so About / Legal sit at the bottom of the EMStudio menu
    # where users look for them. Both are always enabled — a user must be able
    # to reach the disclaimer with no document open and no solver installed.
    ("Help", [
        CMD_LICENCE, "Separator",
        CMD_ABOUT, CMD_LEGAL,
    ]),
]


def grouped_commands():
    """Every command placed in a toolbar/menu group (separators dropped)."""
    out = []
    for _name, cmds in COMMAND_GROUPS:
        out += [c for c in cmds if c != "Separator"]
    return out


# --- helpers -----------------------------------------------------------------
def _selection_references():
    """Current selection as a References LinkSubList value."""
    refs = []
    for sel in FreeCADGui.Selection.getSelectionEx():
        subs = tuple(s for s in sel.SubElementNames if s) or ("",)
        refs.append((sel.Object, subs))
    return refs


def _active_analysis(create=False):
    """The analysis to operate on: selected one, else first in document."""
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import query

    doc = FreeCAD.ActiveDocument
    if doc is None:
        return None
    for sel in FreeCADGui.Selection.getSelection():
        if query.is_em_type(sel, "EMStudio::Analysis"):
            return sel
        parent = query.get_parent_analysis(sel)
        if parent is not None:
            return parent
    analyses = query.find_analyses(doc)
    if analyses:
        return analyses[0]
    if create:
        return analysis_mod.makeAnalysis(doc)
    return None


def _warn(text):
    from PySide import QtWidgets

    QtWidgets.QMessageBox.warning(FreeCADGui.getMainWindow(), "EMStudio", text)


# --- commands ------------------------------------------------------------------
class _AntennaFromSelection:
    """One click: selection -> a runnable NEC2 wire-antenna analysis.

    Exists because assembling this by hand needs four objects created in the
    right order under a selection rule that is not discoverable (the material
    wants the whole object, the port wants a named EdgeN picked in the 3-D
    view). Getting it wrong yields "port must reference a wire edge", which
    states the symptom and not the cure.
    """

    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_antenna_from_selection.svg"),
            "MenuText": "Antenna from Selection",
            "ToolTip": "Turn the selected conductor — a SOLID or a curve — "
                       "into a runnable NEC2 antenna: wire model, PEC "
                       "material, centre feed, sweep and solver, with every "
                       "derived value reported",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from PySide import QtWidgets

        from emstudio.antenna import from_selection as fs

        sel = FreeCADGui.Selection.getSelectionEx()
        if not sel:
            _warn("Select the conductor first — the solid you drew, or its "
                  "path as a curve/polyline.")
            return
        obj = sel[0].Object
        shape = getattr(obj, "Shape", None)
        if shape is None:
            _warn("'{0}' has no shape to work from.".format(obj.Label))
            return

        # A SOLID carries its own cross-section, so the radius is measured. A
        # CURVE does not — it is already only a centre line — so it has to be
        # asked for rather than invented. Ask BEFORE the worker starts, since
        # a dialog cannot be raised from the worker thread.
        radius_mm = None
        if fs.classify(shape) == "wire":
            guess = max(sum(e.Length for e in shape.Edges) / 2000.0, 0.5)
            val, ok = QtWidgets.QInputDialog.getDouble(
                FreeCADGui.getMainWindow(),
                "EMStudio — conductor radius",
                "A curve is only a centre line, so it carries no thickness.\n"
                "What is the conductor's radius?\n\n"
                "For a round wire this is its radius; for a bar or tube use\n"
                "the equal-area radius, sqrt(cross-section area / pi).",
                guess, 0.0001, 1e6, 4)
            if not ok:
                return
            radius_mm = float(val)

        # Extraction from a solid is a boolean march and can take minutes on a
        # large body, so it never runs on the GUI thread.
        from emstudio.ui import run_gui

        def work(_a, _b, _log):
            return fs.plan(shape, radius_mm=radius_mm)

        def done(p):
            text = fs.describe(p)
            ans = QtWidgets.QMessageBox.question(
                FreeCADGui.getMainWindow(), "EMStudio — antenna from selection",
                text + "\n\nCreate this analysis?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes)
            if ans != QtWidgets.QMessageBox.Yes:
                return
            try:
                ana, _wire = fs.build(FreeCAD.ActiveDocument, obj, p)
            except Exception as exc:                     # noqa: BLE001
                _warn("Could not build the analysis: {0}".format(exc))
                return
            FreeCAD.ActiveDocument.recompute()
            FreeCAD.Console.PrintMessage("EMStudio: " + text + "\n")
            QtWidgets.QMessageBox.information(
                FreeCADGui.getMainWindow(), "EMStudio",
                "'{0}' is ready — press Run Solver.\n\n{1}".format(
                    ana.Label, text))

        def failed(exc):
            _warn("Could not read that selection as a conductor:\n\n{0}"
                  .format(exc))

        run_gui.run_generic_gui("Deriving the wire model", work, done,
                                parent=FreeCADGui.getMainWindow(),
                                on_error=failed)


class _CreateAnalysis:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_analysis.svg"),
            "MenuText": "New EM Analysis",
            "ToolTip": "Create an EMStudio electromagnetic analysis container",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        FreeCADGui.addModule("emstudio.objects.analysis")
        FreeCADGui.doCommand("emstudio.objects.analysis.makeAnalysis(FreeCAD.ActiveDocument)")
        FreeCAD.ActiveDocument.recompute()


class _CreateMaterial:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_material.svg"),
            "MenuText": "EM Material",
            "ToolTip": "Assign an EM material (PEC/dielectric) to the selected geometry",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import material

        ana = _active_analysis(create=True)
        obj = material.makeMaterial(FreeCAD.ActiveDocument, ana, references=_selection_references())
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(obj)
        FreeCAD.ActiveDocument.recompute()


class _CreatePort:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_port.svg"),
            "MenuText": "Lumped Port",
            "ToolTip": "Create a lumped port on the selected edge/face (the feed point)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import ports

        ana = _active_analysis(create=True)
        obj = ports.makeLumpedPort(FreeCAD.ActiveDocument, ana, references=_selection_references())
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(obj)
        FreeCAD.ActiveDocument.recompute()


class _CreateCoil:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_coil.svg"),
            "MenuText": "Coil Excitation",
            "ToolTip": "Mark the selected ring/tube solid as a current-driven "
                       "coil winding (Elmer magnetics)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import coil

        ana = _active_analysis(create=True)
        obj = coil.makeCoil(FreeCAD.ActiveDocument, ana, references=_selection_references())
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(obj)
        FreeCAD.ActiveDocument.recompute()


class _AddSolverNEC2:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_solver_nec2.svg"),
            "MenuText": "Add NEC2 Solver",
            "ToolTip": "Add a NEC2 (wire MoM) solver to the analysis",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import solver_objs

        ana = _active_analysis(create=True)
        solver_objs.makeSolverNEC2(FreeCAD.ActiveDocument, ana)
        FreeCAD.ActiveDocument.recompute()


class _AddSolverOpenEMS:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_solver_openems.svg"),
            "MenuText": "Add openEMS Solver",
            "ToolTip": "Add an openEMS (FDTD) solver to the analysis",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import solver_objs

        ana = _active_analysis(create=True)
        solver_objs.makeSolverOpenEMS(FreeCAD.ActiveDocument, ana)
        FreeCAD.ActiveDocument.recompute()


class _AddSolverElmer:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_solver_elmer.svg"),
            "MenuText": "Add Elmer Magnetics Solver",
            "ToolTip": "Add an Elmer (FEM magnetodynamics) solver: induction "
                       "heating, eddy currents, coil coupling (axisymmetric)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import solver_objs

        ana = _active_analysis(create=True)
        solver_objs.makeSolverElmer(FreeCAD.ActiveDocument, ana)
        FreeCAD.ActiveDocument.recompute()


class _AddSolverPalace:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_solver_palace.svg"),
            "MenuText": "Add Palace Solver",
            "ToolTip": "Add an AWS Palace (FEM full-wave) solver: resonant-cavity "
                       "eigenmodes",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import solver_objs

        ana = _active_analysis(create=True)
        solver_objs.makeSolverPalace(FreeCAD.ActiveDocument, ana)
        FreeCAD.ActiveDocument.recompute()


class _RunSolver:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_run.svg"),
            "MenuText": "Run Solver",
            "ToolTip": "Run the selected solver (or the analysis' only solver) and plot results",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import query
        from emstudio.ui import run_gui

        ana = _active_analysis()
        if ana is None:
            _warn("No EM Analysis in this document yet.")
            return
        # selected solver wins; else the analysis' single solver
        solver = None
        for sel in FreeCADGui.Selection.getSelection():
            if query.em_type(sel).startswith("EMStudio::Solver"):
                solver = sel
                break
        if solver is None:
            solvers = query.get_solvers(ana)
            if len(solvers) == 1:
                solver = solvers[0]
            elif not solvers:
                _warn("Add a solver to the analysis first (NEC2 or openEMS).")
                return
            else:
                _warn("Multiple solvers present — select the one to run.")
                return

        stype = query.em_type(solver)
        if stype == "EMStudio::SolverNEC2":
            from emstudio.solvers import nec2

            def run_fn(a, s, cb):
                return nec2.run(a, s, line_callback=cb)
        elif stype == "EMStudio::SolverOpenEMS":
            from emstudio.solvers import openems

            def run_fn(a, s, cb):
                return openems.run(a, s, line_callback=cb)
        elif stype == "EMStudio::SolverElmer":
            # magnetics result is not an S11 sweep — generic runner + own dialog
            from emstudio.solvers import elmer

            def run_elmer(_a, _s, cb):
                return elmer.run(ana, solver, line_callback=cb)

            def on_success(result):
                from emstudio.ui.magnetics_dialog import MagneticsResultsDialog

                FreeCAD.Console.PrintMessage(
                    "EMStudio: magnetics solve finished in {0:.1f}s "
                    "(results in {1})\n".format(
                        result.meta.get("duration_s", -1.0),
                        result.meta.get("workdir", "?")))
                MagneticsResultsDialog(result, parent=FreeCADGui.getMainWindow()).exec()

            run_gui.run_generic_gui("Running {0}".format(solver.Label), run_elmer,
                                    on_success, parent=FreeCADGui.getMainWindow())
            return
        elif stype == "EMStudio::SolverPalace":
            from emstudio.solvers import palace

            driven = str(getattr(solver, "AnalysisType", "Eigenmode")).startswith(
                "Driven S-parameters")  # wave (waveguide) or coax (lumped) ports

            def run_palace(_a, _s, cb):
                return palace.run(ana, solver, line_callback=cb)

            if driven:
                # S-parameter sweep — reuse the antenna results dialog
                def on_success(result):
                    from emstudio.ui.results_dialog import SweepResultsDialog

                    f_min, s11_min = result.min_s11()
                    FreeCAD.Console.PrintMessage(
                        "EMStudio: Palace S-parameter solve finished in {0:.1f}s "
                        "(results in {1})\n".format(
                            result.meta.get("duration_s", -1.0),
                            result.meta.get("workdir", "?")))
                    SweepResultsDialog(result, parent=FreeCADGui.getMainWindow()).exec()
            else:
                def on_success(result):
                    from emstudio.ui.eigenmode_dialog import EigenModeResultsDialog

                    FreeCAD.Console.PrintMessage(
                        "EMStudio: eigenmode solve finished in {0:.1f}s — "
                        "fundamental {1:.5f} GHz (results in {2})\n".format(
                            result.meta.get("duration_s", -1.0),
                            result.dominant_ghz() or 0.0,
                            result.meta.get("workdir", "?")))
                    EigenModeResultsDialog(result, parent=FreeCADGui.getMainWindow()).exec()

            run_gui.run_generic_gui("Running {0}".format(solver.Label), run_palace,
                                    on_success, parent=FreeCADGui.getMainWindow())
            return
        else:
            _warn("Unknown solver type: {0}".format(stype))
            return

        run_gui.run_solver_gui(ana, solver, run_fn, parent=FreeCADGui.getMainWindow())


class _TemplateDipole:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_dipole.svg"),
            "MenuText": "Template: Wire Dipole",
            "ToolTip": "Create a ready-to-run center-fed half-wave dipole (NEC2)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.dipole")
        FreeCADGui.doCommand("emstudio.templates.dipole.makeDipole()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateMonopole:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_monopole.svg"),
            "MenuText": "Template: Monopole over Ground (VLF/LF)",
            "ToolTip": "Create a ready-to-run vertical monopole over a ground plane "
                       "(NEC2): a short lambda/10 mast at 100 kHz — base-fed, "
                       "perfect ground by default (switch the solver's GroundType "
                       "to Finite for real earth loss / efficiency)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.monopole")
        FreeCADGui.doCommand("emstudio.templates.monopole.makeMonopole()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplatePatch:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_patch.svg"),
            "MenuText": "Template: Patch Antenna",
            "ToolTip": "Create a ready-to-run 2.4 GHz microstrip patch antenna (openEMS)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.patch")
        FreeCADGui.doCommand("emstudio.templates.patch.makePatch()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateSolenoid3D:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_solenoid3d.svg"),
            "MenuText": "Template: 3-D Solenoid (Magnetostatic)",
            "ToolTip": "Create a ready-to-run GENERAL 3-D magnetostatic "
                       "analysis: an air-core tube coil solved by the "
                       "WhitneyAV chain (Elmer) — swap in any closed coil "
                       "solid",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.solenoid3d")
        FreeCADGui.doCommand("emstudio.templates.solenoid3d.makeSolenoid3D()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateInduction:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_induction.svg"),
            "MenuText": "Template: Induction Heating",
            "ToolTip": "Create a ready-to-run induction-heating analysis: "
                       "coil + aluminum billet (Elmer, axisymmetric)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.induction")
        FreeCADGui.doCommand("emstudio.templates.induction.makeInduction()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateWpt:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_wpt.svg"),
            "MenuText": "Template: WPT Coil Pair",
            "ToolTip": "Create a ready-to-run wireless-power coil pair: "
                       "L, M and coupling k (Elmer, axisymmetric)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.wpt")
        FreeCADGui.doCommand("emstudio.templates.wpt.makeWptPair()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateCavity:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_cavity.svg"),
            "MenuText": "Template: Resonant Cavity",
            "ToolTip": "Create a ready-to-run rectangular-cavity eigenmode "
                       "analysis (Palace FEM); fundamental ~4.5 GHz",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.cavity")
        FreeCADGui.doCommand("emstudio.templates.cavity.makeCavity()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateCylCavity:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_cylcavity.svg"),
            "MenuText": "Template: Cylindrical Cavity",
            "ToolTip": "Create a ready-to-run cylindrical-cavity eigenmode "
                       "analysis (Palace FEM, general 3-D geometry via BREP); "
                       "fundamental TM010 ~3.82 GHz",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.cylcavity")
        FreeCADGui.doCommand("emstudio.templates.cylcavity.makeCylCavity()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateWaveguide:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_waveguide.svg"),
            "MenuText": "Template: WR-90 Waveguide",
            "ToolTip": "Create a ready-to-run WR-90 waveguide S-parameter "
                       "analysis (Palace FEM, wave ports, X-band)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.waveguide")
        FreeCADGui.doCommand("emstudio.templates.waveguide.makeWaveguide()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateCircWaveguide:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_circwg.svg"),
            "MenuText": "Template: Circular Waveguide",
            "ToolTip": "Create a ready-to-run circular-waveguide S-parameter "
                       "analysis (Palace FEM, general-BREP wave ports on a "
                       "cylinder); dominant TE11, cutoff ~2.93 GHz at R=30 mm",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.circwaveguide")
        FreeCADGui.doCommand("emstudio.templates.circwaveguide.makeCircWaveguide()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateCoax:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_coax.svg"),
            "MenuText": "Template: Coaxial Line",
            "ToolTip": "Create a ready-to-run coaxial-line S-parameter analysis "
                       "(Palace FEM, radial lumped ports); ~50 ohm air line",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.coax")
        FreeCADGui.doCommand("emstudio.templates.coax.makeCoax()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateMsl:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_msl.svg"),
            "MenuText": "Template: Microstrip Notch Filter",
            "ToolTip": "Create a ready-to-run microstrip notch filter: two-port "
                       "S-parameters with a quarter-wave open stub (openEMS, "
                       "trace-aware meshing); notch ~3.7 GHz",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.msl_filter")
        FreeCADGui.doCommand("emstudio.templates.msl_filter.makeNotchFilter()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _TemplateCositePair:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_tpl_cosite_pair.svg"),
            "MenuText": "Template: Co-site Antenna Pair",
            "ToolTip": "Create two parallel half-wave dipoles (NEC2, two ports) at "
                       "0.5-wavelength spacing — run 'Antenna Isolation Matrix' on "
                       "it to extract the coupling/isolation between them",
        }

    def IsActive(self):
        return True

    def Activated(self):
        FreeCADGui.addModule("emstudio.templates.cosite_pair")
        FreeCADGui.doCommand("emstudio.templates.cosite_pair.makeCositePair()")
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            doc.recompute()
        if FreeCAD.GuiUp:
            FreeCADGui.SendMsgToActiveView("ViewFit")


class _IsolationMatrix:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_isolation.svg"),
            "MenuText": "Antenna Isolation Matrix",
            "ToolTip": "Extract the antenna-to-antenna isolation/coupling matrix of "
                       "the active analysis (needs 2+ ports on wire antennas; NEC2 "
                       "Y-matrix, one solve per port) — the co-site coupling input",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import query
        from emstudio.ui import run_gui

        ana = _active_analysis()
        if ana is None:
            _warn("No EM Analysis in this document yet.")
            return
        if len(query.get_ports(ana)) < 2:
            _warn("Antenna isolation needs at least two ports (one feed per "
                  "antenna). Try Template: Co-site Antenna Pair.")
            return
        solvers = [s for s in query.get_solvers(ana)
                   if query.em_type(s) == "EMStudio::SolverNEC2"]
        if not solvers:
            _warn("Add a NEC2 solver to the analysis first.")
            return
        solver = solvers[0]

        def run_iso(_a, _s, cb):
            from emstudio.cosite import isolation

            return isolation.isolation_matrix(ana, solver, line_callback=cb)

        def on_success(result):
            from emstudio.cosite import isolation
            from PySide import QtGui, QtWidgets

            FreeCAD.Console.PrintMessage(
                "EMStudio: isolation matrix ({0} antennas) in {1}\n".format(
                    len(result["labels"]), result.get("workdir", "?")))
            dlg = QtWidgets.QDialog(FreeCADGui.getMainWindow())
            dlg.setWindowTitle("EMStudio — Antenna Isolation")
            lay = QtWidgets.QVBoxLayout(dlg)
            view = QtWidgets.QPlainTextEdit()
            view.setReadOnly(True)
            view.setFont(QtGui.QFont("Monospace"))
            view.setPlainText(isolation.summary_text(result))
            lay.addWidget(view)
            btn = QtWidgets.QPushButton("Close")
            btn.clicked.connect(dlg.accept)
            lay.addWidget(btn)
            dlg.resize(520, 380)
            dlg.exec()

        run_gui.run_generic_gui("Antenna isolation matrix", run_iso, on_success,
                                parent=FreeCADGui.getMainWindow())


class _SweepGap:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_sweep.svg"),
            "MenuText": "WPT: Sweep Coil Gap",
            "ToolTip": "Parametric study: solve coupling k across a range of "
                       "coil-pair gaps and plot k(gap) (Elmer, needs 2 coils)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from emstudio.objects import query
        from emstudio.solvers.elmer.model import build_axi_model
        from emstudio.solvers.elmer.sweep import sweep_wpt_gap
        from emstudio.ui import run_gui

        ana = _active_analysis()
        if ana is None:
            _warn("No EM Analysis in this document yet.")
            return
        solvers = [s for s in query.get_solvers(ana)
                   if query.em_type(s) == "EMStudio::SolverElmer"]
        if not solvers:
            _warn("Add an Elmer Magnetics Solver and two coils first.")
            return
        try:
            model = build_axi_model(ana, solvers[0])
        except Exception as exc:  # noqa: BLE001 — surface the model error
            _warn("Cannot build the magnetics model:\n{0}".format(exc))
            return
        coils = [b for b in model["bodies"] if b.get("coil")]
        if len(coils) != 2:
            _warn("Gap sweep needs exactly two coils (found {0}).".format(len(coils)))
            return
        # current centroid separation, then a range around it (clamped so the
        # coils never overlap)
        cz = sorted(0.5 * (b["z0"] + b["z1"]) for b in coils)
        gap0 = cz[1] - cz[0]
        min_gap = max(b["z1"] - b["z0"] for b in coils) * 1.2
        gaps = [max(min_gap, gap0 * f) for f in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)]
        gaps = sorted(set(round(g, 3) for g in gaps))

        def run_fn(_a, _s, cb):
            return sweep_wpt_gap(model, gaps, line_callback=cb)

        def on_success(curve):
            from emstudio.ui.sweep_dialog import GapSweepDialog

            GapSweepDialog(curve, parent=FreeCADGui.getMainWindow()).exec()

        run_gui.run_generic_gui("WPT gap sweep ({0} points)".format(len(gaps)),
                                run_fn, on_success,
                                parent=FreeCADGui.getMainWindow())


class _CableDesigner:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_cable.svg"),
            "MenuText": "Cable Designer",
            "ToolTip": "Cable Designer: Litz constructions (Types 1-9, AC "
                       "resistance), coax TEM analytics (Z0/VF/attenuation + "
                       "Palace full-wave verify), single-wire skin "
                       "effect/ampacity, and twisted-pair differential Z0 "
                       "(UTP/STP, Cat5e/Cat6 presets)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.cable_dialog import CableDesignerDialog

        dlg = CableDesignerDialog(parent=FreeCADGui.getMainWindow())
        dlg.exec()


class _ElementDesigner:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_element.svg"),
            "MenuText": "Element Designer",
            "ToolTip": "Design one radiating element from requirements: "
                       "recommended family with rationale, wire synthesis "
                       "(dipole/monopole/folded/fraction verticals, measured "
                       "K curve), predicted Z/gain, NEC2 verify, and "
                       "Accept -> Generate a runnable analysis (ROADMAP "
                       "section 1; Yagi/patch/LPDA families follow)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.element_dialog import ElementDesignerDialog

        dlg = ElementDesignerDialog(parent=FreeCADGui.getMainWindow())
        dlg.exec()


class _SmallAntennaDesigner:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_small_antenna.svg"),
            "MenuText": "Small-Antenna Designer (VLF/LF)",
            "ToolTip": "Electrically-small antenna analytics: short monopole/dipole/"
                       "loop radiation resistance, effective height, efficiency, "
                       "Chu Q/bandwidth, loading — with a band->method picker",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.small_antenna_dialog import SmallAntennaDialog

        dlg = SmallAntennaDialog(parent=FreeCADGui.getMainWindow())
        dlg.exec()


class _CositeCalculator:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_cosite.svg"),
            "MenuText": "Co-site Interference Calculator",
            "ToolTip": "Co-site EMC: intermodulation products, receiver "
                       "desensitization, broadband noise and frequency-plan "
                       "clashes over a list of co-located radios",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.cosite_dialog import CositeDialog

        dlg = CositeDialog(parent=FreeCADGui.getMainWindow())
        dlg.exec()


class _LinkBudget:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_link.svg"),
            "MenuText": "Point-to-Point Link Budget",
            "ToolTip": "Propagation path loss (free-space + two-ray plane-earth), "
                       "received power, fade margin and field strength for a "
                       "point-to-point link (ROADMAP §6 coverage/propagation)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.link_dialog import LinkBudgetDialog

        dlg = LinkBudgetDialog(parent=FreeCADGui.getMainWindow())
        dlg.exec()


class _Coverage:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_coverage.svg"),
            "MenuText": "Area Coverage Map",
            "ToolTip": "Predict a transmitter's coverage footprint (received power / "
                       "field strength) over a lat/lon grid, with optional DEM "
                       "terrain shadowing and antenna-pattern modulation, and "
                       "export to a Google-Earth KML (ROADMAP §6 coverage)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.coverage_dialog import CoverageDialog

        dlg = CoverageDialog(parent=FreeCADGui.getMainWindow())
        dlg.exec()


class _MultiStationCoverage:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_multicoverage.svg"),
            "MenuText": "Multi-Station Service / Interference",
            "ToolTip": "Compose two or more transmitters' coverage into wanted/"
                       "unwanted (D/U) service & interference contours: per cell "
                       "threshold on the wanted-to-unwanted field ratio against an "
                       "FCC/ITU protection ratio (served / interference-limited / "
                       "no-service), plus a best-server view and KML (ROADMAP §6)",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.multistation_dialog import MultiStationDialog

        dlg = MultiStationDialog(parent=FreeCADGui.getMainWindow())
        dlg.exec()


class _DetectSolvers:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_solverdetect.svg"),
            "MenuText": "Detect / Install Solvers",
            "ToolTip": "Solver setup wizard: detect openEMS / NEC2 / FastHenry / "
                       "Elmer / Palace / Gmsh, one-line apt command, guided "
                       "no-sudo source builds",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.setup import solvers

        report = solvers.install_report_text()
        FreeCAD.Console.PrintMessage(report + "\n")

        from emstudio.ui.installer_dialog import SolverInstallerDialog

        SolverInstallerDialog(parent=FreeCADGui.getMainWindow()).exec()


class _Licence:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_licence.svg"),
            "MenuText": "EMStudio Pro — install / activate",
            "ToolTip": "Install the EMStudio Pro module from the zip you "
                       "downloaded after purchase, and enter your licence key. "
                       "Also shows whether Pro is currently active.",
        }

    def IsActive(self):
        # Always available: a user must be able to reach this with no document
        # open, and BEFORE Pro is installed — that is the whole point of it.
        return True

    def Activated(self):
        from emstudio.ui.licence_dialog import show_licence_dialog

        show_licence_dialog(FreeCADGui.getMainWindow())


class _About:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_about.svg"),
            "MenuText": "About EMStudio",
            "ToolTip": "What EMStudio is, its version and development status, "
                       "the solver backends it drives, and credits",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.about_dialog import show_about

        show_about(FreeCADGui.getMainWindow())


class _Legal:
    def GetResources(self):
        return {
            "Pixmap": icon_path("emstudio_legal.svg"),
            "MenuText": "Legal notice && disclaimer",
            "ToolTip": "Intended use (educational / hobbyist / experimental), "
                       "no warranty, no liability, your duty to verify every "
                       "result, and the EMStudio / AJJ3 brand notice",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from emstudio.ui.about_dialog import show_legal

        show_legal(FreeCADGui.getMainWindow())


def register():
    """Register all EMStudio commands with FreeCADGui (idempotent)."""
    FreeCADGui.addCommand(CMD_ANTENNA_FROM_SEL, _AntennaFromSelection())
    FreeCADGui.addCommand(CMD_ANALYSIS, _CreateAnalysis())
    FreeCADGui.addCommand(CMD_MATERIAL, _CreateMaterial())
    FreeCADGui.addCommand(CMD_PORT, _CreatePort())
    FreeCADGui.addCommand(CMD_COIL, _CreateCoil())
    FreeCADGui.addCommand(CMD_SOLVER_NEC2, _AddSolverNEC2())
    FreeCADGui.addCommand(CMD_SOLVER_OPENEMS, _AddSolverOpenEMS())
    FreeCADGui.addCommand(CMD_SOLVER_ELMER, _AddSolverElmer())
    FreeCADGui.addCommand(CMD_SOLVER_PALACE, _AddSolverPalace())
    FreeCADGui.addCommand(CMD_RUN, _RunSolver())
    FreeCADGui.addCommand(CMD_TPL_DIPOLE, _TemplateDipole())
    FreeCADGui.addCommand(CMD_TPL_MONOPOLE, _TemplateMonopole())
    FreeCADGui.addCommand(CMD_TPL_PATCH, _TemplatePatch())
    FreeCADGui.addCommand(CMD_TPL_INDUCTION, _TemplateInduction())
    FreeCADGui.addCommand(CMD_TPL_WPT, _TemplateWpt())
    FreeCADGui.addCommand(CMD_TPL_SOLENOID3D, _TemplateSolenoid3D())
    FreeCADGui.addCommand(CMD_TPL_CAVITY, _TemplateCavity())
    FreeCADGui.addCommand(CMD_TPL_CYLCAVITY, _TemplateCylCavity())
    FreeCADGui.addCommand(CMD_TPL_WAVEGUIDE, _TemplateWaveguide())
    FreeCADGui.addCommand(CMD_TPL_CIRCWG, _TemplateCircWaveguide())
    FreeCADGui.addCommand(CMD_TPL_COAX, _TemplateCoax())
    FreeCADGui.addCommand(CMD_TPL_MSL, _TemplateMsl())
    FreeCADGui.addCommand(CMD_TPL_COSITE_PAIR, _TemplateCositePair())
    FreeCADGui.addCommand(CMD_ISOLATION, _IsolationMatrix())
    FreeCADGui.addCommand(CMD_SWEEP_GAP, _SweepGap())
    FreeCADGui.addCommand(CMD_LITZ, _CableDesigner())
    FreeCADGui.addCommand(CMD_ELEMENT, _ElementDesigner())

    FreeCADGui.addCommand(CMD_SMALL_ANTENNA, _SmallAntennaDesigner())
    FreeCADGui.addCommand(CMD_COSITE, _CositeCalculator())
    FreeCADGui.addCommand(CMD_LINK, _LinkBudget())
    FreeCADGui.addCommand(CMD_COVERAGE, _Coverage())
    FreeCADGui.addCommand(CMD_MULTICOVERAGE, _MultiStationCoverage())

    FreeCADGui.addCommand(CMD_DETECT, _DetectSolvers())
    FreeCADGui.addCommand(CMD_ABOUT, _About())
    FreeCADGui.addCommand(CMD_LEGAL, _Legal())
    FreeCADGui.addCommand(CMD_LICENCE, _Licence())
