# SPDX-License-Identifier: LGPL-2.1-or-later
"""Vertical monopole-over-ground template (VLF/LF characterization via NEC2).

One click produces a runnable NEC2 analysis for an electrically-short vertical
monopole standing on a ground plane — the canonical VLF/LF antenna, where the
antenna is a tiny fraction of a wavelength and the ground system dominates
efficiency. The wire base sits on z=0 and is fed at its base segment; the NEC2
solver carries the ground model (perfect PEC image by default; switch to Finite
for real earth loss). Physics per A.D. Watt, *VLF Radio Engineering* (Pergamon,
1967) and Balanis.

Default case: a short monopole h = lambda/10 at 100 kHz (lambda ~= 3 km, so
h ~= 300 m). Over perfect ground its feedpoint resistance approaches the analytic
radiation resistance Rr = 40*pi^2*(h/lambda)^2 ~= 3.95 ohm, and it is strongly
capacitive (needs a base loading coil to resonate). Electrically-short structures
need many segments *per structure* (segments-per-wavelength under-resolves them),
so the solver's SegmentsPerWavelength is set high enough that the short mast gets
~130 segments.
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs

C0 = 299792458.0


def makeMonopole(doc=None, f0_hz=100e3, height_frac=0.1, wire_radius_m=0.1,
                 ground="Perfect (PEC image)", height_m=None):
    """Create a complete monopole-over-ground analysis. Returns the analysis object.

    :param f0_hz: design frequency (default 100 kHz).
    :param height_frac: monopole height as a fraction of the wavelength
        (0.1 = a short lambda/10 monopole; 0.25 = a quarter-wave monopole).
    :param wire_radius_m: mast conductor radius (m).
    :param ground: NEC2 GroundType — "Perfect (PEC image)" or "Finite (Sommerfeld)".
    :param height_m: optional absolute-height override (m) from the Element
        Designer synthesis (K-shortened lengths, lambda-fraction verticals).
        Default None keeps height = height_frac * lambda — byte-identical to
        the gated template geometry. The segment sizing follows the ACTUAL
        electrical height either way.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    lam0_mm = C0 / f0_hz * 1000.0
    if height_m is not None:
        height_mm = height_m * 1000.0
        height_frac = height_mm / lam0_mm  # drives the segment sizing below
    else:
        height_mm = height_frac * lam0_mm

    wire = doc.addObject("Part::Feature", "MonopoleWire")
    wire.Shape = Part.makeLine(
        FreeCAD.Vector(0, 0, 0),                 # base ON the ground plane (z=0)
        FreeCAD.Vector(0, 0, height_mm),
    )
    wire.Label = "Monopole Wire"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Monopole Analysis"
    ana.FrequencyStart = "{0} kHz".format(f0_hz / 1e3 * 0.9)
    ana.FrequencyStop = "{0} kHz".format(f0_hz / 1e3 * 1.1)
    ana.FrequencyPoints = 5

    mat = material_mod.makeMaterial(doc, ana, name="MastPEC", category="Metal (PEC)")
    mat.Label = "Mast (PEC)"
    mat.References = [(wire, "Edge1")]
    mat.WireRadius = "{0} mm".format(wire_radius_m * 1000.0)

    port = ports_mod.makeLumpedPort(doc, ana, name="BaseFeed", direction="+Z")
    port.Label = "Base Feed"
    port.References = [(wire, "Edge1")]

    solver = solver_objs.makeSolverNEC2(doc, ana)
    solver.GroundType = ground
    # Electrically-short mast: resolve it finely (segments-per-wavelength badly
    # under-resolves a lambda/10 wire). At height_frac=0.1 this yields ~130 segs.
    solver.SegmentsPerWavelength = max(40, int(round(130.0 / max(height_frac, 1e-3))))

    doc.recompute()
    return ana
