# SPDX-License-Identifier: LGPL-2.1-or-later
"""Induction-heating template: coil around a cylindrical billet (Elmer).

Creates a complete ready-to-run axisymmetric induction-heating analysis:
an aluminum billet on the Z axis inside a multi-turn ring coil, a
Conductor material, a Coil excitation, and the Elmer magnetodynamics
solver. Run Solver reports the billet Joule power, the coil's effective
L and reflected R, and loads the B-field / Joule-heating VTU into the
3-D viewport.
"""
from __future__ import annotations

import FreeCAD


def makeInduction(doc=None, billet_r_mm=15.0, billet_h_mm=80.0, gap_mm=5.0,
                  coil_dr_mm=5.0, turns=20, current_a=200.0, f_hz=2000.0,
                  sigma_s_m=3.5e7):
    """Create a complete induction-heating analysis. Returns the analysis.

    Defaults: aluminum billet (sigma = 3.5e7 S/m) r=15 mm, 20-turn coil
    carrying 200 A peak at 2 kHz — a/delta ~ 8, a representative
    induction-heating regime.
    """
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import coil as coil_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    # geometry (mm, centered on z = 0)
    billet = doc.addObject("Part::Feature", "Billet")
    billet.Shape = Part.makeCylinder(
        billet_r_mm, billet_h_mm, FreeCAD.Vector(0, 0, -billet_h_mm / 2.0))
    coil_ri = billet_r_mm + gap_mm
    coil_ro = coil_ri + coil_dr_mm
    ring = Part.makeCylinder(
        coil_ro, billet_h_mm, FreeCAD.Vector(0, 0, -billet_h_mm / 2.0)).cut(
        Part.makeCylinder(coil_ri, billet_h_mm, FreeCAD.Vector(0, 0, -billet_h_mm / 2.0)))
    coil_geo = doc.addObject("Part::Feature", "InductionCoil")
    coil_geo.Shape = ring

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Induction Heating"
    ana.FrequencyStart = "{0} kHz".format(f_hz / 1e3)
    ana.FrequencyStop = "{0} kHz".format(f_hz / 1e3)
    ana.FrequencyPoints = 1

    mat = material_mod.makeMaterial(doc, ana, name="BilletConductor",
                                    category="Conductor")
    mat.Conductivity = sigma_s_m
    mat.ThermalConductivity = 237.0  # aluminum, W/(m*K)
    mat.Density = 2700.0             # aluminum, kg/m^3 (for transient heating)
    mat.SpecificHeat = 900.0         # aluminum, J/(kg*K)
    mat.References = [(billet, "")]

    coil_mod.makeCoil(doc, ana, name="WorkCoil", references=[(coil_geo, "")],
                      turns=turns, current_a=current_a)

    solver = solver_objs.makeSolverElmer(doc, ana)
    # steady-state equilibrium temperature with forced cooling; free-air
    # steady state would run away to unphysical values — real IH is transient
    # (heating curves are a roadmap item)
    solver.SolveThermal = True
    solver.ConvectionCoefficient = 100.0
    doc.recompute()
    return ana
