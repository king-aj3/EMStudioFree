# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rectangular-cavity eigenmode template (Palace FEM).

Creates a ready-to-run resonant-cavity analysis: an air-filled box with
PEC walls, plus the Palace eigenmode solver. Run Solver returns the
resonant frequencies and Q of the lowest modes. The default 40x20x60 mm
air cavity has its fundamental TE101 mode at ~4.504 GHz (exact analytic).
"""
from __future__ import annotations

import FreeCAD


def makeCavity(doc=None, size_mm=(40.0, 20.0, 60.0), eps_r=1.0, num_modes=6):
    """Create a complete rectangular-cavity eigenmode analysis. Returns the analysis."""
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    dx, dy, dz = size_mm
    box = doc.addObject("Part::Box", "Cavity")
    box.Length = dx
    box.Width = dy
    box.Height = dz

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Cavity Eigenmode"

    mat = material_mod.makeMaterial(doc, ana, name="CavityFill", category="Dielectric")
    mat.RelPermittivity = float(eps_r)
    mat.RelPermeability = 1.0
    mat.LossTangent = 0.0
    mat.References = [(box, "")]

    solver = solver_objs.makeSolverPalace(doc, ana)
    solver.NumModes = int(num_modes)
    doc.recompute()
    return ana
