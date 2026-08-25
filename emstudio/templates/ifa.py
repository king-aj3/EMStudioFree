# SPDX-License-Identifier: LGPL-2.1-or-later
"""Inverted-F antenna (IFA) template — the printed handset/PCB element.

Two factories, the same split ``patch.py`` uses and for the same reason:

* :func:`makeIFA` builds the PUBLISHED reference geometry verbatim — openEMS's
  own ``examples/antennas/inverted_f.m`` ((C) 2013 Stefan Mahr), which ships with
  openEMS so anyone can re-run it. This is what the validation gate solves, so
  the gate is anchored OUTSIDE this project.
* :func:`makeIFADesign` synthesizes one for an arbitrary frequency from
  ``emstudio.antenna.ifa``. This is what the Element Designer creates.

⚠ Every conductor is COPLANAR, at z = board thickness. That is not a
simplification we made: an IFA really is a flat trace with the ground plane cut
away beneath it, which is why it costs a PCB layer and nothing else. It also
means no vertical metal is needed anywhere in this template.

⚠⚠ ELEMENT model, not a phone model. On a real handset the chassis radiates and
the ground plane resonates in its own right, so the board size in these
documents is part of the answer, not a container for it. See
docs/upstream/ifa-anchors.md.

Geometry, in the reference's own names (all in the z = thickness plane, with the
board centred on the origin and the ground cut back from the +Y edge):

    ground      spans y from -board/2 to +board/2 - e
    (origin of the element = x 0, y = board/2 - e, the ground edge)
    short stub  x in [-(fp+w1), -fp],      y in [0, h]
    radiator    x in [-(fp+w1), -(fp+w1)+l], y in [h - w2, h]
    feed        x in [0, wf],              y in [gap, h]
    port        a gap-high line at x = wf/2, y in [0, gap], excited +Y
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.antenna import ifa as ifa_engine
from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs


def _plane(doc, name, label, x0, y0, z, dx, dy):
    """One coplanar rectangular conductor, as a zero-thickness face.

    Zero thickness is the same idiom ``patch.py`` uses for the patch and ground:
    the openEMS writer meshes a face as PEC, and giving printed copper a real
    35 um thickness would force a mesh line pair 35 um apart across the whole
    element -- a large cost for a detail that does not move the resonance.
    """
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makePlane(dx, dy, FreeCAD.Vector(x0, y0, z))
    obj.Label = label
    return obj


def _build(doc, d, label):
    """Build an IFA from a dimension dict (metres) and wire up the analysis."""
    mm = 1000.0
    board = d["board_m"] * mm
    t = d["board_thickness_m"] * mm
    e = d["ground_clearance_m"] * mm
    h = d["stub_height_m"] * mm
    l_rad = d["radiator_length_m"] * mm
    w1 = d["stub_width_m"] * mm
    w2 = d["radiator_width_m"] * mm
    wf = d["feed_width_m"] * mm
    fp = d["feed_offset_m"] * mm
    gap = d["feed_gap_m"] * mm
    f0 = d["f0_hz"]

    substrate = doc.addObject("Part::Box", "Substrate")
    substrate.Length = board
    substrate.Width = board
    substrate.Height = t
    substrate.Placement.Base = FreeCAD.Vector(-board / 2.0, -board / 2.0, 0.0)

    # The ground stops short of the +Y edge by the clearance: that cleared strip
    # is where the element lives, and removing the ground under it is what makes
    # the trace air-loaded rather than microstrip. Get this wrong -- run the
    # ground the full length -- and the element is shorted flat to the plane and
    # radiates nothing.
    gnd = _plane(doc, "GroundPlane", "Ground plane (cut back)",
                 -board / 2.0, -board / 2.0, t, board, board - e)

    y0 = board / 2.0 - e          # the ground edge; the element's own origin
    stub = _plane(doc, "ShortStub", "Short-circuit stub",
                  -(fp + w1), y0, t, w1, h)
    rad = _plane(doc, "Radiator", "Radiating element",
                 -(fp + w1), y0 + h - w2, t, l_rad, w2)
    feed = _plane(doc, "FeedElement", "Feed element",
                  0.0, y0 + gap, t, wf, h - gap)

    port_line = doc.addObject("Part::Feature", "FeedLine")
    port_line.Shape = Part.makeLine(
        FreeCAD.Vector(wf / 2.0, y0, t),
        FreeCAD.Vector(wf / 2.0, y0 + gap, t))
    port_line.Label = "Feed (port span)"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = label
    # Wide enough to show the resonance moving if the geometry is wrong, and to
    # carry the second (3/4-wave) mode into view rather than cropping it out.
    ana.FrequencyStart = "{0} GHz".format(f0 / 1e9 * 0.6)
    ana.FrequencyStop = "{0} GHz".format(f0 / 1e9 * 1.4)
    ana.FrequencyPoints = 401
    # ⚠⚠ THE MESH IS NOT OPTIONAL HERE, AND GETTING IT WRONG LOOKS RIGHT.
    # An IFA's features are millimetres -- a 0.5 mm port gap and a 1 mm feed
    # trace -- while the default lambda/20 grid is ~4 mm at 2.45 GHz. At the
    # default the port gap is not resolved at all and the feed element is
    # electrically SHORTED to the ground plane: measured Zin = 0.05 + 9.52j ohm,
    # S11 = -0.02 dB. The lethal part is that it still reports a dip at
    # 2.4524 GHz -- the RIGHT frequency, because the conductor path sets that
    # regardless -- so a coarse run looks like a working antenna that merely
    # matches badly, and is in fact an antenna that accepts no power at all.
    # Measured convergence on the reference geometry (see
    # docs/upstream/ifa-anchors.md for the full table):
    #     mesh 20 -> Zin   0.05 +  9.52j   S11  -0.02 dB   (a short)
    #     mesh 30 -> Zin 102.08 + 58.08j   S11  -6.39 dB   (still wrong)
    #     mesh 40 -> Zin  51.16 +  0.76j   S11 -37.24 dB
    #     mesh 60 -> Zin  54.72 +  1.38j   S11 -26.57 dB   <- chosen
    #     mesh 80 -> Zin  53.13 +  1.29j   S11 -29.68 dB
    #     mesh100 -> Zin  53.65 +  0.93j   S11 -28.79 dB
    # 60 is the cheapest value that agrees with the converged 80/100 tail in
    # BOTH resonance and impedance (30 s against 117 s and 217 s). 40 matches
    # best but sits ~1 % high on frequency against that tail, so it is not the
    # value to standardise on.
    # ⚠ The writer's trace-aware refinement (MicrostripMeshMode) cannot help:
    # writer.py:614 gates it on an MSL port, explicitly so that lumped-port
    # antenna analyses stay byte-identical. An IFA is a lumped-port antenna with
    # microstrip-scale features, which is precisely the case that falls between
    # the two.
    ana.MeshResolution = 60

    m_metal = material_mod.makeMaterial(doc, ana, name="IFAPEC",
                                        category="Metal (PEC)")
    m_metal.Label = "Element + ground (PEC)"
    m_metal.References = [(stub, ""), (rad, ""), (feed, ""), (gnd, "")]
    m_metal.Priority = 10

    m_sub = material_mod.makeMaterial(doc, ana, name="SubstrateMat",
                                      category="Dielectric")
    m_sub.Label = "Board (er {0:g})".format(d["er"])
    m_sub.References = [(substrate, "")]
    m_sub.RelPermittivity = d["er"]
    m_sub.LossTangent = 1.0e-3
    m_sub.Priority = 0

    # +Y: the port bridges the gap between the ground edge and the foot of the
    # feed element, which runs in +Y. The reference excites [0 1 0] here.
    port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort", direction="+Y")
    port.Label = "Feed Port"
    port.References = [(port_line, "Edge1")]

    solver_objs.makeSolverOpenEMS(doc, ana)

    doc.recompute()
    return ana


def makeIFA(doc=None):
    """Build the PUBLISHED openEMS reference IFA verbatim (2.45 GHz class).

    Dimensions are the reference's own, NOT synthesized — this is the geometry
    the validation gate reproduces, so it must not drift with the engine.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    r = ifa_engine.REFERENCE
    d = {
        "f0_hz": ifa_engine.resonant_frequency(
            r["stub_height_m"] + r["radiator_length_m"]),
        "er": r["er"],
        "board_m": r["board_m"],
        "board_thickness_m": r["board_thickness_m"],
        "ground_clearance_m": r["ground_clearance_m"],
        "stub_height_m": r["stub_height_m"],
        "radiator_length_m": r["radiator_length_m"],
        "stub_width_m": r["stub_width_m"],
        "radiator_width_m": r["radiator_width_m"],
        "feed_width_m": r["feed_width_m"],
        "feed_offset_m": r["feed_offset_m"],
        "feed_gap_m": r["feed_gap_m"],
    }
    return _build(doc, d, "IFA (openEMS reference, 2.45 GHz)")


def makeIFADesign(doc=None, f0_hz=2.45e9, er=4.3, board_thickness_mm=1.5,
                  stub_height_mm=None, target_z_ohm=50.0):
    """Create a SYNTHESIZED inverted-F analysis for ``f0_hz``.

    Dimensions come from ``emstudio.antenna.ifa``: the quarter-wave path
    h + l = c/4f is physics; the widths, feed offset and clearance are scaled
    from the published reference and are labelled as seeds in the engine's own
    warnings. ``makeIFA`` (the reference geometry) is left untouched.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    d = ifa_engine.design_ifa(
        f0_hz, er=er, board_thickness_m=board_thickness_mm / 1000.0,
        stub_height_m=(None if stub_height_mm is None
                       else stub_height_mm / 1000.0),
        target_z_ohm=target_z_ohm)
    return _build(doc, d, "IFA Design ({0:.3g} GHz, er {1:g})".format(
        f0_hz / 1e9, er))
