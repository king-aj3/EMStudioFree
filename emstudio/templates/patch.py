# SPDX-License-Identifier: LGPL-2.1-or-later
"""Microstrip patch antenna template.

Mirrors the official openEMS Python tutorial ``Simple_Patch_Antenna.py`` (Liebig,
openEMS project) so the validation gate has a published reference: 32 x 40 mm patch on
a 60 x 60 x 1.524 mm, epsR = 3.38 substrate, lumped-port feed 6 mm off-center, MUR
boundaries, 1-3 GHz sweep -> expected S11 dip near 2.4 GHz.
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs


def makePatch(doc=None):
    """Create the tutorial patch antenna analysis. Returns the analysis object."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    patch_w, patch_l = 32.0, 40.0          # mm (x, y)
    sub_w, sub_l, sub_h = 60.0, 60.0, 1.524
    feed_x = -6.0

    substrate = doc.addObject("Part::Box", "Substrate")
    substrate.Length = sub_w   # x
    substrate.Width = sub_l    # y
    substrate.Height = sub_h   # z
    substrate.Placement.Base = FreeCAD.Vector(-sub_w / 2, -sub_l / 2, 0)

    patch = doc.addObject("Part::Feature", "Patch")
    patch.Shape = Part.makePlane(
        patch_w, patch_l, FreeCAD.Vector(-patch_w / 2, -patch_l / 2, sub_h)
    )
    gnd = doc.addObject("Part::Feature", "GroundPlane")
    gnd.Shape = Part.makePlane(sub_w, sub_l, FreeCAD.Vector(-sub_w / 2, -sub_l / 2, 0))

    feed = doc.addObject("Part::Feature", "FeedLine")
    feed.Shape = Part.makeLine(
        FreeCAD.Vector(feed_x, 0, 0), FreeCAD.Vector(feed_x, 0, sub_h)
    )
    feed.Label = "Feed (port span)"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Patch Antenna Analysis"
    ana.FrequencyStart = "1 GHz"
    ana.FrequencyStop = "3 GHz"
    ana.FrequencyPoints = 401
    # MUR boundaries are the analysis default (tutorial-faithful)

    m_metal = material_mod.makeMaterial(doc, ana, name="PatchPEC", category="Metal (PEC)")
    m_metal.Label = "Patch + Ground (PEC)"
    m_metal.References = [(patch, ""), (gnd, "")]
    m_metal.Priority = 10

    m_sub = material_mod.makeMaterial(doc, ana, name="SubstrateMat", category="Dielectric")
    m_sub.Label = "Substrate (Ro4003-like)"
    m_sub.References = [(substrate, "")]
    m_sub.RelPermittivity = 3.38
    m_sub.LossTangent = 1e-3
    m_sub.Priority = 0

    port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort", direction="+Z")
    port.Label = "Feed Port"
    port.References = [(feed, "Edge1")]

    solver_objs.makeSolverOpenEMS(doc, ana)

    doc.recompute()
    return ana


def makePatchDesign(doc=None, f0_hz=2.4e9, er=3.38, h_mm=1.524,
                    target_z_ohm=50.0, margin_mm=15.0):
    """Create a SYNTHESIZED microstrip-patch analysis (Element Designer E4).

    Dimensions come from the gated ``emstudio.antenna.patch_tl`` engine: the
    resonant length L lies along X (the feed-offset axis), the radiating width W
    along Y, an inset probe feed offset along X for ``target_z_ohm``. Substrate/
    ground extend ``margin_mm`` beyond the patch on each side. openEMS solver +
    an f0-bracketing sweep — Run (or Verify) for the FDTD resonance/gain.

    ``makePatch`` (the openEMS tutorial reference) is left untouched.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    from emstudio.antenna import patch_tl

    des = patch_tl.design_patch(f0_hz, er, h_mm / 1000.0,
                                target_z_ohm=target_z_ohm)
    l_mm = des["length_m"] * 1000.0        # resonant length, along X
    w_mm = des["width_m"] * 1000.0         # radiating width, along Y
    off_mm = des["feed_offset_m"] * 1000.0  # feed offset from centre, along X
    sub_x = l_mm + 2.0 * margin_mm
    sub_y = w_mm + 2.0 * margin_mm
    sub_h = h_mm
    feed_x = -off_mm

    substrate = doc.addObject("Part::Box", "Substrate")
    substrate.Length = sub_x
    substrate.Width = sub_y
    substrate.Height = sub_h
    substrate.Placement.Base = FreeCAD.Vector(-sub_x / 2, -sub_y / 2, 0)

    patch = doc.addObject("Part::Feature", "Patch")
    patch.Shape = Part.makePlane(
        l_mm, w_mm, FreeCAD.Vector(-l_mm / 2, -w_mm / 2, sub_h))
    gnd = doc.addObject("Part::Feature", "GroundPlane")
    gnd.Shape = Part.makePlane(sub_x, sub_y,
                               FreeCAD.Vector(-sub_x / 2, -sub_y / 2, 0))

    feed = doc.addObject("Part::Feature", "FeedLine")
    feed.Shape = Part.makeLine(
        FreeCAD.Vector(feed_x, 0, 0), FreeCAD.Vector(feed_x, 0, sub_h))
    feed.Label = "Feed (port span)"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Patch Design ({0:.3g} GHz, er {1:g})".format(f0_hz / 1e9, er)
    ana.FrequencyStart = "{0} GHz".format(f0_hz / 1e9 * 0.6)
    ana.FrequencyStop = "{0} GHz".format(f0_hz / 1e9 * 1.4)
    ana.FrequencyPoints = 401

    m_metal = material_mod.makeMaterial(doc, ana, name="PatchPEC",
                                        category="Metal (PEC)")
    m_metal.Label = "Patch + Ground (PEC)"
    m_metal.References = [(patch, ""), (gnd, "")]
    m_metal.Priority = 10

    m_sub = material_mod.makeMaterial(doc, ana, name="SubstrateMat",
                                      category="Dielectric")
    m_sub.Label = "Substrate"
    m_sub.References = [(substrate, "")]
    m_sub.RelPermittivity = er
    m_sub.LossTangent = 1e-3
    m_sub.Priority = 0

    port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort", direction="+Z")
    port.Label = "Feed Port"
    port.References = [(feed, "Edge1")]

    solver_objs.makeSolverOpenEMS(doc, ana)

    doc.recompute()
    return ana
