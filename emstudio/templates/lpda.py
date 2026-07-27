# SPDX-License-Identifier: LGPL-2.1-or-later
"""LPDA (log-periodic dipole array) template (Element Designer slice E5).

One call turns a band (f_lo-f_hi) + a gain target (or explicit tau/sigma) into
a complete, runnable NEC2 analysis: N parallel dipoles along the boom axis, a
PEC wire material, the crossed boom feeder as a chain of
``EMStudio::TransmissionLine`` objects (Crossed=True → negative-Z0 NEC2 TL
cards, the standard LPDA convention — see docs/upstream/lpda-carrel-anchors.md),
a lumped feed on the SHORTEST element, a sweep spanning the design band, and a
NEC2 solver. Geometry comes from the gated ``emstudio.antenna.lpda`` engine
(Carrel design equations).

The boom runs along +X with the longest element at x = 0; the beam fires
toward +X (off the short end, where the feed sits). No resistive rear
termination is modeled (it flattens the low-edge VSWR but absorbs ~1.7 dB of
low-edge gain — anchors doc §2); the TransmissionLine objects' shunt-admittance
properties keep that experiment open.
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.antenna import lpda as lpda_engine
from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs
from emstudio.objects import transmission_line as tl_mod


def makeLPDA(doc=None, f_lo_hz=54e6, f_hi_hz=216e6, gain_dbi=None,
             tau=None, sigma=None, wire_radius_mm=5.0, r0_ohm=65.0):
    """Create a complete LPDA analysis. Returns the analysis object.

    :param f_lo_hz: low band edge (default 54 MHz — the classic VHF example).
    :param f_hi_hz: high band edge (default 216 MHz).
    :param gain_dbi: target free-space gain (dBi, corrected contours) —
        picks tau/sigma on the optimum-sigma line. Give this OR explicit
        ``tau`` + ``sigma``; default (all None) designs for 8 dBi (the
        classic worked-example target).
    :param tau: explicit Carrel scale factor (with ``sigma``).
    :param sigma: explicit relative spacing (with ``tau``).
    :param wire_radius_mm: element conductor radius (mm).
    :param r0_ohm: target mean input resistance (drives the feeder Z0).
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    kwargs = {"wire_d_m": 2.0 * wire_radius_mm / 1000.0, "r0_ohm": r0_ohm}
    if tau is not None or sigma is not None:
        kwargs["tau"] = tau
        kwargs["sigma"] = sigma
    else:
        # all-None default: the classic 8 dBi corrected-contour target
        kwargs["gain_dbi"] = 8.0 if gain_dbi is None else gain_dbi
    design = lpda_engine.design_lpda(f_lo_hz, f_hi_hz, **kwargs)

    objs = []
    for e in design["elements"]:
        x_mm = e["position_m"] * 1000.0
        half_mm = e["length_m"] * 1000.0 / 2.0
        w = doc.addObject("Part::Feature", e["name"].replace(" ", ""))
        w.Shape = Part.makeLine(FreeCAD.Vector(x_mm, -half_mm, 0),
                                FreeCAD.Vector(x_mm, half_mm, 0))
        w.Label = e["name"]
        objs.append(w)
    fed_obj = objs[-1]  # shortest element (front)

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "LPDA Analysis ({0:g}-{1:g} MHz)".format(
        f_lo_hz / 1e6, f_hi_hz / 1e6)
    ana.FrequencyStart = "{0} MHz".format(f_lo_hz / 1e6)
    ana.FrequencyStop = "{0} MHz".format(f_hi_hz / 1e6)
    ana.FrequencyPoints = 201

    mat = material_mod.makeMaterial(doc, ana, name="LPDAPEC", category="Metal (PEC)")
    mat.Label = "Elements (PEC)"
    mat.References = [(o, "Edge1") for o in objs]
    mat.WireRadius = "{0} mm".format(wire_radius_mm)

    port = ports_mod.makeLumpedPort(doc, ana, name="Feed", direction="+Y")
    port.Label = "Feed (shortest element)"
    port.References = [(fed_obj, "Edge1")]
    port.Impedance = "{0} Ohm".format(r0_ohm)

    # crossed feeder chain, front (fed) to rear, one TL per adjacent pair
    z0 = design["feeder_z0_ohm"]
    n = len(objs)
    for i in range(n - 1, 0, -1):
        tl = tl_mod.makeTransmissionLine(
            doc, ana, name="Feeder{0}".format(n - i),
            references=[(objs[i], "Edge1"), (objs[i - 1], "Edge1")],
            z0_ohm=z0, crossed=True)
        tl.Label = "Feeder {0}-{1}".format(i + 1, i)

    solver = solver_objs.makeSolverNEC2(doc, ana)
    solver.SegmentsPerWavelength = 20

    doc.recompute()
    return ana
