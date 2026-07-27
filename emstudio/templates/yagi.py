# SPDX-License-Identifier: LGPL-2.1-or-later
"""Yagi-Uda template (Element Designer slice E3).

One call turns a frequency + a gain (or boom-length) target into a complete,
runnable NEC2 analysis: the boom laid along X, reflector + driven + N director
wires parallel to Z, a PEC wire material, a lumped feed on the driven element,
a sweep bracketing the design frequency, and a NEC2 solver. Geometry and the
per-element lengths come from the gated ``emstudio.antenna.yagi`` engine
(NBS TN-688 Table 1 + the Fig 9/10 compensation model).

The wires carry the **bare-wire** (diameter-compensated) lengths — the metal-boom
correction is a physical build allowance and is NOT modeled here (NEC2 has no
metal boom). Reported far-field gain must be read at the DESIGN frequency, not the
runner's default best-match frequency (which wanders when the driven element is
not matched); the Element Designer's Verify path and the yagi_nec2 gate pin it.
"""

from __future__ import annotations

import FreeCAD
import Part

from emstudio.antenna import yagi as yagi_engine
from emstudio.objects import analysis as analysis_mod
from emstudio.objects import material as material_mod
from emstudio.objects import ports as ports_mod
from emstudio.objects import solver_objs


def makeYagi(doc=None, f0_hz=400e6, gain_dbd=None, boom_lambda=0.8,
             wire_radius_mm=3.0, driven_k=None):
    """Create a complete Yagi-Uda analysis. Returns the analysis object.

    :param f0_hz: design frequency (default 400 MHz, TN-688's own).
    :param gain_dbd: target gain over a dipole (dBd) — selects the boom class.
        Give this OR ``boom_lambda``; ``gain_dbd`` wins when both are set.
    :param boom_lambda: boom length in wavelengths (snapped to a TN-688 class).
    :param wire_radius_mm: parasitic-element conductor radius (mm).
    :param driven_k: end-effect K for the driven element (wire_elements).
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    wire_d_m = 2.0 * wire_radius_mm / 1000.0
    kwargs = {"wire_d_m": wire_d_m, "boom_d_m": 0.0, "driven_k": driven_k}
    if gain_dbd is not None:
        kwargs["gain_dbd"] = gain_dbd
    else:
        kwargs["boom_lambda"] = boom_lambda
    design = yagi_engine.design_yagi(f0_hz, **kwargs)

    objs = []
    driven_obj = None
    for e in design["elements"]:
        x_mm = e["position_m"] * 1000.0
        half_mm = e["length_m"] * 1000.0 / 2.0  # bare-wire length (no boom corr)
        w = doc.addObject("Part::Feature", e["name"].replace(" ", ""))
        w.Shape = Part.makeLine(FreeCAD.Vector(x_mm, 0, -half_mm),
                                FreeCAD.Vector(x_mm, 0, half_mm))
        w.Label = e["name"]
        objs.append(w)
        if e["kind"] == "driven":
            driven_obj = w

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Yagi Analysis ({0:g}λ, {1:g} dBd)".format(
        design["boom_lambda"], design["gain_dbd"])
    ana.FrequencyStart = "{0} MHz".format(f0_hz / 1e6 * 2.0 / 3.0)
    ana.FrequencyStop = "{0} MHz".format(f0_hz / 1e6 * 4.0 / 3.0)
    ana.FrequencyPoints = 201

    mat = material_mod.makeMaterial(doc, ana, name="YagiPEC", category="Metal (PEC)")
    mat.Label = "Elements (PEC)"
    mat.References = [(o, "Edge1") for o in objs]
    mat.WireRadius = "{0} mm".format(wire_radius_mm)

    port = ports_mod.makeLumpedPort(doc, ana, name="Feed", direction="+Z")
    port.Label = "Driven Feed"
    port.References = [(driven_obj, "Edge1")]

    solver = solver_objs.makeSolverNEC2(doc, ana)
    solver.SegmentsPerWavelength = 40

    doc.recompute()
    return ana
