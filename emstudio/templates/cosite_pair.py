# SPDX-License-Identifier: LGPL-2.1-or-later
"""Two-antenna co-site pair template (antenna-to-antenna isolation via NEC2).

One click produces a two-port NEC2 analysis: two parallel side-by-side half-wave
dipoles separated by a fraction of a wavelength, each with its own feed port. Run
the **Antenna Isolation Matrix** command on it to extract the coupling/isolation
(|S21|) between them — the device-level input to the co-site interference
calculator.

Default: two lambda/2 dipoles at 300 MHz separated by 0.5 lambda, which reproduces
the Balanis parallel-dipole mutual-impedance result (Z21 ~= -12.5 - j29.9 ohm,
isolation ~13.8 dB).
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs

C0 = 299792458.0


def makeCositePair(doc=None, f0_hz=300e6, spacing_frac=0.5, half_len_frac=0.2389,
                   wire_radius_mm=0.5):
    """Create a two-dipole co-site analysis. Returns the analysis object."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    lam_mm = C0 / f0_hz * 1000.0
    half_mm = half_len_frac * lam_mm
    d_mm = spacing_frac * lam_mm

    w1 = doc.addObject("Part::Feature", "DipoleA")
    w1.Shape = Part.makeLine(FreeCAD.Vector(0, 0, -half_mm),
                             FreeCAD.Vector(0, 0, half_mm))
    w1.Label = "Dipole A"
    w2 = doc.addObject("Part::Feature", "DipoleB")
    w2.Shape = Part.makeLine(FreeCAD.Vector(d_mm, 0, -half_mm),
                             FreeCAD.Vector(d_mm, 0, half_mm))
    w2.Label = "Dipole B"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Co-site Pair Analysis"
    ana.FrequencyStart = "{0} MHz".format(f0_hz / 1e6)
    ana.FrequencyStop = "{0} MHz".format(f0_hz / 1e6)
    ana.FrequencyPoints = 1

    mat = material_mod.makeMaterial(doc, ana, name="DipolesPEC", category="Metal (PEC)")
    mat.Label = "Dipoles (PEC)"
    mat.References = [(w1, "Edge1"), (w2, "Edge1")]
    mat.WireRadius = "{0} mm".format(wire_radius_mm)

    p1 = ports_mod.makeLumpedPort(doc, ana, name="FeedA", direction="+Z")
    p1.Label = "Feed A"
    p1.References = [(w1, "Edge1")]
    p2 = ports_mod.makeLumpedPort(doc, ana, name="FeedB", direction="+Z")
    p2.Label = "Feed B"
    p2.References = [(w2, "Edge1")]

    solver_objs.makeSolverNEC2(doc, ana)

    doc.recompute()
    return ana
