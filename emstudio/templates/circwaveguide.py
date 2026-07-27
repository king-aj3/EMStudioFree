# SPDX-License-Identifier: LGPL-2.1-or-later
"""Circular-waveguide S-parameter template (Palace FEM, general-BREP driven ports).

Creates a ready-to-run driven analysis on a CIRCULAR CYLINDER — a non-box solid,
so it exercises the general-geometry driven path (BREP export + slab-tagged end
faces as wave ports) rather than the box mesher. The dominant mode of a circular
waveguide of radius R is TE11 with cutoff fc = 1.8412 * c / (2*pi*R); for the
default R=30 mm that is 2.928 GHz, so the default 3.0-3.8 GHz sweep sits in the
single-mode TE11 band (below TM01 cutoff 3.83 GHz) where a matched uniform guide
gives |S11| ~ 0 and |S21| ~ 0 dB. Run Solver returns S11/S21.
"""
from __future__ import annotations

import FreeCAD


def makeCircWaveguide(doc=None, radius_mm=30.0, length_mm=80.0,
                      f1_ghz=3.0, f2_ghz=3.8, points=9, eps_r=1.0):
    """Create a complete circular-waveguide driven S-parameter analysis.

    Returns the analysis. The cylinder axis is Z (its longest dimension when
    length > diameter), so the two circular end faces become the wave ports.
    """
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    cyl = doc.addObject("Part::Cylinder", "CircWaveguide")
    cyl.Radius = radius_mm
    cyl.Height = length_mm  # along Z — the propagation axis (ports on the end faces)

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Circular Waveguide"
    ana.FrequencyStart = "{0} GHz".format(f1_ghz)
    ana.FrequencyStop = "{0} GHz".format(f2_ghz)
    ana.FrequencyPoints = int(points)

    mat = material_mod.makeMaterial(doc, ana, name="Air", category="Dielectric")
    mat.RelPermittivity = float(eps_r)
    mat.RelPermeability = 1.0
    mat.LossTangent = 0.0
    mat.References = [(cyl, "")]

    solver = solver_objs.makeSolverPalace(doc, ana)
    solver.AnalysisType = "Driven S-parameters"
    solver.Order = 2  # order 3 is very slow per point on a curved guide
    solver.MeshSize = "5 mm"  # ~R/6; resolves the curved wall, keeps the solve fast
    doc.recompute()
    return ana
