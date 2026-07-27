# SPDX-License-Identifier: LGPL-2.1-or-later
"""Coaxial-line S-parameter template (Palace FEM, radial lumped ports).

Creates a ready-to-run driven analysis: a straight coaxial line (an annular
dielectric between an inner and an outer conductor) with a radial lumped port
at each end, swept in frequency. Run Solver returns S11/S21; a uniform line
referenced to its own characteristic impedance is matched (|S11| ~ 0, |S21| ~
0 dB) with the TEM phase advancing as -beta*L.

Defaults: an air line with inner radius 0.5 mm, outer 1.15 mm -> Z0 ~ 50 ohm
(the classic precision air-line impedance standard).
"""
from __future__ import annotations

import FreeCAD


def makeCoax(doc=None, a_mm=0.5, b_mm=1.15, length_mm=20.0, eps_r=1.0,
             f1_ghz=2.0, f2_ghz=6.0, points=5):
    """Create a complete coaxial-line driven S-parameter analysis. Returns the analysis."""
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    # The dielectric annulus = outer cylinder minus inner cylinder (both along
    # +Z, concentric on the axis). Its inner/outer cylindrical faces give the
    # coax radii (read exactly from the surfaces, not the tessellated bbox).
    outer = doc.addObject("Part::Cylinder", "CoaxOuter")
    outer.Radius = b_mm
    outer.Height = length_mm
    inner = doc.addObject("Part::Cylinder", "CoaxInner")
    inner.Radius = a_mm
    inner.Height = length_mm
    tube = doc.addObject("Part::Cut", "CoaxDielectric")
    tube.Base = outer
    tube.Tool = inner
    doc.recompute()

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Coaxial Line"
    ana.FrequencyStart = "{0} GHz".format(f1_ghz)
    ana.FrequencyStop = "{0} GHz".format(f2_ghz)
    ana.FrequencyPoints = int(points)

    mat = material_mod.makeMaterial(doc, ana, name="Dielectric", category="Dielectric")
    mat.RelPermittivity = eps_r
    mat.RelPermeability = 1.0
    mat.LossTangent = 0.0
    mat.References = [(tube, "")]

    solver = solver_objs.makeSolverPalace(doc, ana)
    solver.AnalysisType = "Driven S-parameters (coax)"
    solver.Order = 2
    solver.MeshSize = "0.4 mm"  # ~1.6 tets across the gap; ~35 s at Order 2
    doc.recompute()
    return ana
