# SPDX-License-Identifier: LGPL-2.1-or-later
"""Planar inverted-F antenna (PIFA) template — the elevated-plate handset element.

The three-dimensional cousin of the printed IFA in ``ifa.py``: a rectangular top
plate held above the ground plane on air, shorted to it along part of one edge
by a vertical plate, and fed by a pin a short way in from that short.

Two factories, the same split ``patch.py`` and ``ifa.py`` use:

* :func:`makePIFA` builds the PUBLISHED anchor geometry verbatim -- the 20 x 20 mm
  plate, W 5 mm, H 10 mm on an 80 mm square ground whose resonance was MEASURED
  in an anechoic chamber (Huynh, Virginia Tech 2000). That is what the gate solves.
* :func:`makePIFADesign` synthesizes one from ``emstudio.antenna.pifa``.

⚠ NO DIELECTRIC. A PIFA of this class stands off the ground on air, so the model
is PEC plates in free space and there is no substrate object at all. That is not
a simplification -- adding one would be modelling a different antenna.

⚠ VERTICAL zero-thickness faces are used for the shorting plate, and that is
supported: the writer recognises an axis-aligned sheet in any orientation and
emits a collapsed-axis box plus the matching edge-to-grid call. They are built
with ``Part.Face(Part.makePolygon([...]))`` -- horn.py's idiom -- and NOT with
``Part.makePlane(..., dirNormal)``, whose local u/v frame does not mean what it
appears to mean for a non-Z normal.

⚠⚠ THE GROUND PLANE IS PART OF THE ANTENNA, not packaging. Published measurements
of the anchor geometry differ by 6 MHz between an 80 mm and a 100 mm ground, and
shrinking it toward 0.156 lambda moves the resonance by +18.3 % with a 2.4:1
bandwidth spread and 3.7 dB of gain spread. On a handset the chassis IS the
ground plane. See docs/upstream/pifa-anchors.md.

Geometry (ground at z = 0, the shorted edge at y = 0):

    ground plane   z = 0, a square of side ``ground``, centred on the origin
    top plate      z = H, x in [-L1/2, L1/2], y in [0, L2]
    shorting plate y = 0, x in [-W/2, W/2],  z in [0, H]   (a vertical face)
    feed pin       x = 0, y = feed_offset,   z in [0, H]   (a line; port on it)
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.antenna import pifa as pifa_engine
from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs


def _face(doc, name, label, pts):
    """A planar face from an explicit point list, closed for you.

    ``Part.Face(Part.makePolygon(...))`` rather than ``Part.makePlane`` so the
    caller states the four corners in world coordinates and the orientation
    follows from them -- which is the only readable way to place a VERTICAL
    sheet.
    """
    vecs = [FreeCAD.Vector(*p) for p in pts]
    vecs.append(vecs[0])
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.Face(Part.makePolygon(vecs))
    obj.Label = label
    return obj


def _build(doc, d, label):
    """Build a PIFA from a dimension dict (metres) and wire up the analysis."""
    mm = 1000.0
    l1 = d["l1_m"] * mm          # along the shorted edge (x)
    l2 = d["l2_m"] * mm          # perpendicular, the resonant length (y)
    h = d["height_m"] * mm       # plate height above ground (z)
    w = d["short_width_m"] * mm  # shorting-plate width (x)
    fo = d["feed_offset_m"] * mm  # feed pin, in from the short (y)
    g = d["ground_m"] * mm
    f0 = d["f0_hz"]

    gnd = _face(doc, "GroundPlane", "Ground plane",
                [(-g / 2.0, -g / 2.0, 0.0), (g / 2.0, -g / 2.0, 0.0),
                 (g / 2.0, g / 2.0, 0.0), (-g / 2.0, g / 2.0, 0.0)])

    plate = _face(doc, "TopPlate", "Top plate",
                  [(-l1 / 2.0, 0.0, h), (l1 / 2.0, 0.0, h),
                   (l1 / 2.0, l2, h), (-l1 / 2.0, l2, h)])

    # The vertical short. Its width W is the parameter the whole Hirasawa
    # interpolation turns on: at W = L1 the antenna is a quarter-wave
    # short-circuited patch, at W -> 0 it is a shorting pin, and the resonance
    # moves between the two.
    # ⚠⚠ AT THE SIDE EDGE, not centred. The Hirasawa closed form has no term
    # for the shorting plate's POSITION along the edge, so it cannot tell these
    # two antennas apart -- but they are not the same antenna. Measured on the
    # anchor geometry: centred solves at 2.0370 GHz, at the edge at 1.8930 GHz,
    # against a published chamber measurement of 1.892 GHz. Centring it is a
    # 7.6 % error, larger than the closed form's own stated accuracy, and it
    # looks perfectly plausible. The literature's standard case is the edge.
    sx = -l1 / 2.0
    short = _face(doc, "ShortingPlate", "Shorting plate (at the side edge)",
                  [(sx, 0.0, 0.0), (sx + w, 0.0, 0.0),
                   (sx + w, 0.0, h), (sx, 0.0, h)])

    # The feed pin sits on the short's own centre-line in x, offset along y
    # toward the open edge: the classic arrangement, and the one the anchor's
    # measured result was obtained with.
    fx = sx + w / 2.0
    feed = doc.addObject("Part::Feature", "FeedPin")
    feed.Shape = Part.makeLine(FreeCAD.Vector(fx, fo, 0.0),
                               FreeCAD.Vector(fx, fo, h))
    feed.Label = "Feed pin (port span)"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = label
    ana.FrequencyStart = "{0} GHz".format(f0 / 1e9 * 0.6)
    ana.FrequencyStop = "{0} GHz".format(f0 / 1e9 * 1.4)
    ana.FrequencyPoints = 401
    # ⛳ NOT the IFA's trap, and the difference is worth understanding rather
    # than copying the warning across. The IFA has a 0.5 mm port gap and a 1 mm
    # trace, so a default lambda/20 grid leaves it electrically SHORTED. This
    # antenna's smallest features are the 5 mm shorting plate and the 10 mm
    # air gap, which the default grid already resolves: measured, mesh 20 gives
    # Zin 32.79 -15.65j and a real -11.18 dB match, not a short.
    # 60 is chosen for accuracy rather than survival. Measured against the
    # published chamber measurement of 1.892 GHz:
    #     mesh 20 -> 1.9149 GHz (+1.21 %)   Zin 32.79 -15.65j   -11.18 dB
    #     mesh 40 -> 1.9037 GHz (+0.62 %)   Zin 36.18 -11.42j   -13.71 dB
    #     mesh 60 -> 1.8962 GHz (+0.22 %)   Zin 38.60  -8.34j   -15.99 dB  <-
    #     mesh 90 -> 1.8849 GHz (-0.37 %)   Zin 43.25  -4.63j   -21.14 dB
    # Every one of those is inside 1.3 % of measured hardware; 60 costs 30 s
    # against 115 s for 90 and sits closest to the measurement.
    ana.MeshResolution = 60

    m_metal = material_mod.makeMaterial(doc, ana, name="PIFAPEC",
                                        category="Metal (PEC)")
    m_metal.Label = "Plate + short + ground (PEC)"
    m_metal.References = [(plate, ""), (short, ""), (gnd, "")]
    m_metal.Priority = 10

    port = ports_mod.makeLumpedPort(doc, ana, name="FeedPort", direction="+Z")
    port.Label = "Feed Port"
    port.References = [(feed, "Edge1")]

    solver_objs.makeSolverOpenEMS(doc, ana)

    doc.recompute()
    return ana


def makePIFA(doc=None, ground_m=None):
    """Build the PUBLISHED anchor PIFA verbatim (20 x 20 mm plate, W 5, H 10).

    Dimensions are the published ones, NOT synthesized -- this is the geometry
    whose resonance was measured in a chamber (1892 MHz on this 80 mm ground),
    so it must not drift with the engine.

    :param ground_m: square ground-plane side in metres. ``None`` keeps the
        anchor's own 80 mm, which is the ground the 1892 MHz measurement was
        taken on. Pass another size to walk the GROUND-PLANE LADDER: Huynh's
        Table 5-1 measured this same antenna on 20/40/60/80/100/120/140 mm
        grounds, and the resonance moves by **29 %** across it. That is not
        packaging tolerance -- on a handset the chassis is part of the radiator
        -- and ``pifa_openems`` gates our agreement with that measured trend.
        ⚠ Everything else stays FIXED when you change this, including the feed
        offset. Huynh RE-MATCHED the probe at every ground size (px 1.7 mm at
        L = 20 up to 3.5 mm at L = 140); we do not, so the resonance stays
        comparable but the MATCH does not -- measured, the 20 mm ground reaches
        only -9.55 dB here. Never gate S11 depth or bandwidth across this
        ladder against Huynh's numbers.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    a = pifa_engine.ANCHOR
    g = a["ground_m"] if ground_m is None else float(ground_m)
    d = {
        "f0_hz": pifa_engine.resonant_frequency(
            a["l1_m"], a["l2_m"], a["h_m"], a["w_m"]),
        "l1_m": a["l1_m"],
        "l2_m": a["l2_m"],
        "height_m": a["h_m"],
        "short_width_m": a["w_m"],
        # A quarter of the way in from the short, the same seed the engine uses.
        "feed_offset_m": 0.25 * a["l2_m"],
        "ground_m": g,
    }
    label = "PIFA (published anchor, 20x20 mm plate)"
    if ground_m is not None:
        label = "PIFA (published anchor, %g mm ground)" % (g * 1000.0)
    return _build(doc, d, label)


def makePIFADesign(doc=None, f0_hz=2.45e9, height_mm=None, l1_over_l2=1.0,
                   short_frac=0.25, target_z_ohm=50.0):
    """Create a SYNTHESIZED PIFA analysis for ``f0_hz``.

    Dimensions come from ``emstudio.antenna.pifa``: the Hirasawa interpolation
    is the physics; the feed offset and the ground-plane size are seeds and the
    engine's warnings say so. ``makePIFA`` (the anchor) is left untouched.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    d = pifa_engine.design_pifa(
        f0_hz, height_m=(None if height_mm is None else height_mm / 1000.0),
        l1_over_l2=l1_over_l2, short_frac=short_frac,
        target_z_ohm=target_z_ohm)
    return _build(doc, d, "PIFA Design ({0:.3g} GHz)".format(f0_hz / 1e9))
