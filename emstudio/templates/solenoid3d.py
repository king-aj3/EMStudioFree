# SPDX-License-Identifier: LGPL-2.1-or-later
"""3-D solenoid template: an air-core tube coil solved by the WhitneyAV chain.

One click produces a runnable **3-D Magnetostatic (DC)** analysis — the first
GUI entry into the general 3-D magnetodynamics engine (v0.55, TEAM-7
validated). A tube coil (annular cylinder) carrying N·I ampere-turns is
meshed conformally inside an auto-sized air domain and solved by
CoilSolver → WhitneyAVSolver → CalcFields; Run Solver loads the B-field
VTU into the 3-D viewport.

Unlike the axisymmetric templates this geometry is a REAL 3-D solid — swap
it for any closed-loop coil shape (racetrack, bent, non-coaxial) and the
same chain solves it. The engine gate pins this class of case against the
exact thick-solenoid closed form at −0.55 % (center); the template's fast
default mesh lands within a few percent (tighten MeshSizeBodies to
converge). If the field comes out inverted, toggle the Coil's ``Reversed``
— a closed coil's circulation sense is mesh-arbitrary.
"""
from __future__ import annotations

import FreeCAD


def makeSolenoid3D(doc=None, r_in_mm=20.0, r_out_mm=25.0, height_mm=60.0,
                   turns=25, current_a=20.0):
    """Create a complete 3-D solenoid analysis. Returns the analysis.

    Defaults: 20/25 × 60 mm tube coil at 500 ampere-turns — solves in
    seconds on the auto mesh (center Bz ≈ 8.4 mT analytic).
    """
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import coil as coil_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    tube = Part.makeCylinder(
        r_out_mm, height_mm, FreeCAD.Vector(0, 0, -height_mm / 2.0)).cut(
        Part.makeCylinder(
            r_in_mm, height_mm + 2.0, FreeCAD.Vector(0, 0, -height_mm / 2.0 - 1.0)))
    coil_geo = doc.addObject("Part::Feature", "SolenoidCoil")
    coil_geo.Shape = tube

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "3-D Solenoid"
    # frequency is ignored at DC but the Analysis carries a range regardless
    ana.FrequencyStart = "1 kHz"
    ana.FrequencyStop = "1 kHz"
    ana.FrequencyPoints = 1

    coil_mod.makeCoil(doc, ana, name="SolenoidWinding",
                      references=[(coil_geo, "")], turns=turns,
                      current_a=current_a)

    solver = solver_objs.makeSolverElmer(doc, ana)
    solver.AnalysisType = "3-D Magnetostatic (DC)"
    solver.MeshSizeBodies = "4 mm"  # wall 5 mm: >= 2-3 elements keeps NI honest
    doc.recompute()
    return ana
