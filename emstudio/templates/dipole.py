# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wire dipole template.

One click produces a complete, runnable analysis: a straight wire along Z, a PEC wire
material, a center-fed lumped port, sweep settings bracketing the design frequency, and
a NEC2 solver — the '10 minutes to first S11 curve' path.

Geometry notes: a half-wave dipole is resonant slightly short of L = lambda/2; the
classic engineering length is L = 0.475 * lambda0 for thin wires, which puts the
reactance zero-crossing within a few percent of f0.
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs

C0 = 299792458.0


def makeDipole(doc=None, f0_hz=300e6, wire_radius_mm=2.0, length_m=None):
    """Create a complete center-fed dipole analysis. Returns the analysis object.

    :param length_m: optional total-length override (m) from the Element
        Designer synthesis (e.g. the measured-K-curve length). Default None
        keeps the classic L = 0.475 * lambda0 — byte-identical to the gated
        template geometry.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    lam0_mm = C0 / f0_hz * 1000.0
    length_mm = length_m * 1000.0 if length_m else 0.475 * lam0_mm

    wire = doc.addObject("Part::Feature", "DipoleWire")
    wire.Shape = Part.makeLine(
        FreeCAD.Vector(0, 0, -length_mm / 2.0),
        FreeCAD.Vector(0, 0, length_mm / 2.0),
    )
    wire.Label = "Dipole Wire"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Dipole Analysis"
    ana.FrequencyStart = "{0} MHz".format(f0_hz / 1e6 * 2.0 / 3.0)
    ana.FrequencyStop = "{0} MHz".format(f0_hz / 1e6 * 4.0 / 3.0)
    ana.FrequencyPoints = 201

    mat = material_mod.makeMaterial(doc, ana, name="WirePEC", category="Metal (PEC)")
    mat.Label = "Wire (PEC)"
    mat.References = [(wire, "Edge1")]
    mat.WireRadius = "{0} mm".format(wire_radius_mm)

    port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort", direction="+Z")
    port.Label = "Feed Port"
    port.References = [(wire, "Edge1")]

    solver_objs.makeSolverNEC2(doc, ana)

    doc.recompute()
    return ana
