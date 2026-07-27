# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cylindrical-cavity eigenmode template (Palace FEM, general 3-D via BREP).

Creates a ready-to-run resonant-cavity analysis on a CIRCULAR CYLINDER — a
non-box solid, so it exercises the general-geometry (BREP export) path rather
than the box mesher. Run Solver returns the resonant frequencies and Q of the
lowest modes. The default R=30 mm cylinder has its fundamental TM010 mode at
c*2.40483/(2*pi*R) = 3.8248 GHz (exact analytic, independent of height).
"""
from __future__ import annotations

import FreeCAD


def makeCylCavity(doc=None, radius_mm=30.0, height_mm=40.0, eps_r=1.0, num_modes=6):
    """Create a complete cylindrical-cavity eigenmode analysis. Returns the analysis."""
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    cyl = doc.addObject("Part::Cylinder", "CylCavity")
    cyl.Radius = radius_mm
    cyl.Height = height_mm

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Cylindrical Cavity Eigenmode"

    mat = material_mod.makeMaterial(doc, ana, name="CavityFill", category="Dielectric")
    mat.RelPermittivity = float(eps_r)
    mat.RelPermeability = 1.0
    mat.LossTangent = 0.0
    mat.References = [(cyl, "")]

    solver = solver_objs.makeSolverPalace(doc, ana)
    solver.NumModes = int(num_modes)
    solver.MeshSize = "6 mm"  # ~R/5; resolves the curved wall, keeps the solve fast
    doc.recompute()
    return ana
