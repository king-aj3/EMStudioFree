# SPDX-License-Identifier: LGPL-2.1-or-later
"""WR-90 waveguide S-parameter template (Palace FEM, driven wave ports).

Creates a ready-to-run driven analysis: a straight air-filled WR-90
rectangular waveguide section (22.86 x 10.16 mm cross-section) with a wave
port on each end, swept across X-band. Run Solver returns S11/S21; the
matched uniform guide gives |S11| ~ 0 and |S21| ~ 0 dB with the TE10 phase.
"""
from __future__ import annotations

import FreeCAD


def makeWaveguide(doc=None, a_mm=22.86, b_mm=10.16, length_mm=30.0,
                  f1_ghz=8.0, f2_ghz=12.0, points=9):
    """Create a complete WR-90 driven S-parameter analysis. Returns the analysis."""
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    box = doc.addObject("Part::Box", "Waveguide")
    box.Length = a_mm       # x (broad wall)
    box.Width = b_mm        # y (narrow wall)
    box.Height = length_mm  # z (propagation axis — the longest dimension)

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "WR-90 Waveguide"
    ana.FrequencyStart = "{0} GHz".format(f1_ghz)
    ana.FrequencyStop = "{0} GHz".format(f2_ghz)
    ana.FrequencyPoints = int(points)

    mat = material_mod.makeMaterial(doc, ana, name="Air", category="Dielectric")
    mat.RelPermittivity = 1.0
    mat.RelPermeability = 1.0
    mat.LossTangent = 0.0
    mat.References = [(box, "")]

    solver = solver_objs.makeSolverPalace(doc, ana)
    solver.AnalysisType = "Driven S-parameters"
    solver.Order = 3
    doc.recompute()
    return ana
