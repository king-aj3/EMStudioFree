# SPDX-License-Identifier: LGPL-2.1-or-later
"""Microstrip notch-filter template — validated PCB-trace / S-parameter workflow.

Mirrors the openEMS ``MSL_NotchFilter.py`` tutorial: a microstrip line on RO4350B
with a quarter-wave open stub. Two MSL ports produce S11 and S21.

STATUS — VALIDATED (v0.16.0). Trace-aware meshing
(``SolverOpenEMS.MicrostripMeshMode = 'Auto'``) resolves the grid at lambda/50 in
the dielectric, grades it across the strip, and hugs the board so the line
terminates in the PML — so the MSL port self-extracts its characteristic
impedance and the S-parameters are physical (|S| <= 1). The
``tests/validation/msl_notch_openems.py`` gate confirms the S21 notch at
3.66 GHz (analytic quarter-wave 3.68 GHz, openEMS tutorial 3.67 GHz), passive to
-0.03 dB, in ~40 s. Earlier releases left this off the toolbar because the
antenna-scale air gridder under-resolved the sub-mm trace (non-physical |S|>1);
trace-aware meshing fixed that.
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs

MM = 1.0  # this template works in mm (EMStudio's drawing unit)


def makeNotchFilter(doc=None):
    """Create the microstrip notch-filter two-port analysis. Returns the analysis."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    # tutorial dimensions in mm
    msl_len = 50.0
    msl_w = 0.6
    sub_h = 0.254
    sub_epr = 3.66
    stub_len = 12.0
    sub_halfwidth = 15.0 * msl_w

    substrate = doc.addObject("Part::Box", "Substrate")
    substrate.Length = 2 * msl_len
    substrate.Width = 2 * sub_halfwidth + stub_len
    substrate.Height = sub_h
    substrate.Placement.Base = FreeCAD.Vector(-msl_len, -sub_halfwidth, 0)

    # No ground plane is drawn: the microstrip ground is the PEC Zmin domain
    # boundary (set below), with the domain bottom pinned on the substrate
    # bottom by the trace-aware writer. Drawing a coincident metal sheet at z=0
    # is redundant and, combined with the writer's z-min ground pin, only adds a
    # zero-thickness metal that perturbs the near-ground mesh. This matches the
    # openEMS MSL_NotchFilter tutorial (ground = PEC z-min boundary).

    # The microstrip line is formed by the two MSL PORTS (they create the strip),
    # exactly like the openEMS tutorial — drawing a separate line metal here would
    # double the conductor and corrupt the port wave decomposition. We only draw
    # the open stub (the quarter-wave resonator that makes the notch).
    stub = doc.addObject("Part::Feature", "Stub")
    stub.Shape = Part.makePlane(msl_w, stub_len,
                                FreeCAD.Vector(-msl_w / 2, msl_w / 2, sub_h))

    # port reference boxes (line width x feed length x substrate height)
    p1 = doc.addObject("Part::Box", "Port1Box")
    p1.Length = msl_len
    p1.Width = msl_w
    p1.Height = sub_h
    p1.Placement.Base = FreeCAD.Vector(-msl_len, -msl_w / 2, 0)
    p2 = doc.addObject("Part::Box", "Port2Box")
    p2.Length = msl_len
    p2.Width = msl_w
    p2.Height = sub_h
    p2.Placement.Base = FreeCAD.Vector(0, -msl_w / 2, 0)

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Microstrip Notch Filter"
    ana.FrequencyStart = "10 MHz"
    ana.FrequencyStop = "7 GHz"
    ana.FrequencyPoints = 801
    # PML along x (the line axis), MUR elsewhere — tutorial-faithful
    ana.BoundaryXmin = "PML_8"
    ana.BoundaryXmax = "PML_8"
    ana.BoundaryZmin = "PEC"

    m_metal = material_mod.makeMaterial(doc, ana, name="Copper", category="Metal (PEC)")
    m_metal.Label = "Stub (PEC)"
    m_metal.References = [(stub, "")]
    m_metal.Priority = 10

    m_sub = material_mod.makeMaterial(doc, ana, name="RO4350B", category="Dielectric")
    m_sub.Label = "Substrate RO4350B"
    m_sub.References = [(substrate, "")]
    m_sub.RelPermittivity = sub_epr
    m_sub.Priority = 0

    port1 = ports_mod.makeLumpedPort(doc, ana, name="Port1")
    port1.Label = "Port 1 (fed)"
    port1.PortType = "MSL"
    port1.Direction = "-Z"           # E-field from line down to ground
    port1.PropagationDirection = "+X"
    port1.References = [(p1, "")]
    port1.Excited = True

    port2 = ports_mod.makeLumpedPort(doc, ana, name="Port2")
    port2.Label = "Port 2"
    port2.PortType = "MSL"
    port2.Direction = "-Z"
    port2.PropagationDirection = "-X"
    port2.References = [(p2, "")]
    port2.Excited = False

    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    solver.ComputeFarField = False
    solver.NearFieldPlane = "None"
    solver.MicrostripMeshMode = "Auto"  # trace-aware dielectric-lambda/50 grid

    doc.recompute()
    return ana
