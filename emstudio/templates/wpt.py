# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wireless-power-transfer template: coaxial coil pair (Elmer).

Two identical multi-turn ring coils facing each other across an axial
gap. Run Solver extracts the inductance matrix (L1, L2, M) and the
coupling coefficient k = M / sqrt(L1*L2) via per-coil excitations, plus
the field picture in the 3-D viewport. Edit the gap (move a coil) or the
radii and re-run to study k vs geometry.
"""
from __future__ import annotations

import FreeCAD


def makeWptPair(doc=None, radius_mm=50.0, cross_mm=2.0, turns=10, gap_mm=20.0,
                current_a=1.0, f_hz=100e3):
    """Create a complete WPT coil-pair analysis. Returns the analysis.

    ``gap_mm`` is the CENTROID-to-centroid axial separation; each coil's
    cross-section is ``cross_mm`` square at mean radius ``radius_mm``.
    """
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import coil as coil_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    half = cross_mm / 2.0
    ri = radius_mm - half
    ro = radius_mm + half

    def _ring(z_center, label):
        ring = Part.makeCylinder(
            ro, cross_mm, FreeCAD.Vector(0, 0, z_center - half)).cut(
            Part.makeCylinder(ri, cross_mm, FreeCAD.Vector(0, 0, z_center - half)))
        obj = doc.addObject("Part::Feature", label)
        obj.Shape = ring
        return obj

    tx_geo = _ring(-gap_mm / 2.0, "TxCoil")
    rx_geo = _ring(gap_mm / 2.0, "RxCoil")

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "WPT Coil Pair"
    ana.FrequencyStart = "{0} kHz".format(f_hz / 1e3)
    ana.FrequencyStop = "{0} kHz".format(f_hz / 1e3)
    ana.FrequencyPoints = 1

    coil_mod.makeCoil(doc, ana, name="TxWinding", references=[(tx_geo, "")],
                      turns=turns, current_a=current_a)
    coil_mod.makeCoil(doc, ana, name="RxWinding", references=[(rx_geo, "")],
                      turns=turns, current_a=current_a)

    solver = solver_objs.makeSolverElmer(doc, ana)
    solver.ExtractCoupling = True
    doc.recompute()
    return ana
