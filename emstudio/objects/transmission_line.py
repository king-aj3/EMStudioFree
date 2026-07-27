# SPDX-License-Identifier: LGPL-2.1-or-later
"""Ideal transmission-line network element (NEC2 ``TL`` card).

A ``TransmissionLine`` connects two wire segments with a lossless ideal line of
given characteristic impedance — NEC2 solves the network without the line
radiating. The canonical user is the LPDA's crossed (transposed) boom feeder
(slice E5): consecutive dipole centers are chained with ``Crossed = True``
lines, which the NEC2 writer emits as negative-Z0 ``TL`` cards (the standard
NEC crossed-line convention, reported as ``CROSSED`` in nec2c's NETWORK DATA
table). The §7 System Designer will reuse this object for general feed
networks.

Semantics (mirrors the NEC2 TL card, verified live on nec2c 1.3.1):

* ``References`` — exactly two wire edges; the line runs between the CENTER
  segments of the two wires (their segment counts are forced odd).
* ``Z0`` — characteristic impedance (always positive here; ``Crossed`` adds
  the 180° phase reversal via the card's sign convention).
* ``LineLength`` — electrical length in meters; 0 = use the straight-line
  distance between the two connection segments (NEC2's default).
* ``Y1Real``/``Y1Imag``/``Y2Real``/``Y2Imag`` — optional fixed shunt
  admittances (S) across end 1 / end 2 of the line.
"""

from __future__ import annotations

import FreeCAD

_GROUP = "EMStudio"


class TransmissionLine:
    """Proxy for an ideal (non-radiating) transmission-line connection."""

    Type = "EMStudio::TransmissionLine"

    def __init__(self, obj):
        obj.Proxy = self
        self._ensure_properties(obj)

    def _ensure_properties(self, obj):
        props = obj.PropertiesList
        if "EMStudioType" not in props:
            obj.addProperty("App::PropertyString", "EMStudioType", _GROUP, "EMStudio type tag")
            obj.EMStudioType = self.Type
            obj.setEditorMode("EMStudioType", 1)
        if "References" not in props:
            obj.addProperty(
                "App::PropertyLinkSubList",
                "References",
                _GROUP,
                "Exactly two wire edges; the line connects their center segments",
            )
        if "Z0" not in props:
            obj.addProperty(
                "App::PropertyElectricalResistance",
                "Z0",
                _GROUP,
                "Characteristic impedance of the line (positive; use Crossed "
                "for the 180-degree transposition)",
            )
            obj.Z0 = "50 Ohm"
        if "Crossed" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "Crossed",
                _GROUP,
                "Crossed (transposed) line — 180-degree phase reversal between "
                "ends (the LPDA feeder convention; NEC2 negative-Z0 card)",
            )
            obj.Crossed = False
        if "LineLength" not in props:
            obj.addProperty(
                "App::PropertyLength",
                "LineLength",
                _GROUP,
                "Electrical line length; 0 = straight-line distance between "
                "the connection segments (NEC2 default)",
            )
            obj.LineLength = "0 mm"
        for name, doc in (
            ("Y1Real", "Shunt admittance across end 1, real part (S)"),
            ("Y1Imag", "Shunt admittance across end 1, imaginary part (S)"),
            ("Y2Real", "Shunt admittance across end 2, real part (S)"),
            ("Y2Imag", "Shunt admittance across end 2, imaginary part (S)"),
        ):
            if name not in props:
                obj.addProperty("App::PropertyFloat", name, _GROUP, doc)
                setattr(obj, name, 0.0)

    def onDocumentRestored(self, obj):
        self._ensure_properties(obj)

    def execute(self, obj):
        return

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


class ViewProviderTransmissionLine:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def getIcon(self):
        from emstudio.resources import icon_path

        return icon_path("emstudio_port.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def makeTransmissionLine(doc=None, analysis=None, name="EMTransmissionLine",
                         references=None, z0_ohm=50.0, crossed=False):
    """Create a transmission-line connection between two wire edges."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    TransmissionLine(obj)
    obj.Z0 = "{0} Ohm".format(float(z0_ohm))
    obj.Crossed = bool(crossed)
    if references:
        obj.References = references
    if FreeCAD.GuiUp:
        ViewProviderTransmissionLine(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj
