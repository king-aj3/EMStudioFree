# SPDX-License-Identifier: LGPL-2.1-or-later
"""EM port objects.

``EMLumpedPort`` marks where energy enters/leaves the model. One port object serves all
backends:

* **openEMS**: the referenced sub-shape's bounding box defines the port span; the port
  is a lumped R across it, excited along ``Direction``. The usual pattern is a straight
  edge (feed line) or a small rectangular face.
* **NEC2**: the referenced edge identifies the fed wire; the excitation is placed on
  the segment nearest the edge midpoint.

``PortNumber`` orders multi-port results (S11, S21, ...). Exactly one port should be
``Excited`` per single-ended simulation (multi-excitation comes with S-matrix sweeps).
"""

from __future__ import annotations

import FreeCAD

_GROUP = "EMStudio"

DIRECTIONS = ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]


class LumpedPort:
    """Proxy for a lumped port."""

    Type = "EMStudio::LumpedPort"

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
                "Geometry sub-element (edge or small face) spanning the port",
            )
        if "PortNumber" not in props:
            obj.addProperty("App::PropertyInteger", "PortNumber", _GROUP, "Port index (1-based)")
            obj.PortNumber = 1
        if "Direction" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "Direction",
                _GROUP,
                "Excitation direction across the port (openEMS)",
            )
            obj.Direction = DIRECTIONS
            obj.Direction = "+Z"
        if "Impedance" not in props:
            obj.addProperty(
                "App::PropertyElectricalResistance",
                "Impedance",
                _GROUP,
                "Port reference impedance / feed resistance",
            )
            obj.Impedance = "50 Ohm"
        if "Excited" not in props:
            obj.addProperty("App::PropertyBool", "Excited", _GROUP, "Drive this port")
            obj.Excited = True
        # Drive amplitude/phase (§7 S4 multi-excitation). Defaults reproduce the
        # historic unity drive so documents saved before v0.67.0 upgrade to
        # byte-identical decks (the frozen-deck gate pins this).
        if "Amplitude" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "Amplitude",
                _GROUP,
                "Drive voltage amplitude (V). NEC2: the EX-card source voltage; "
                "0 V on an excited port is refused (NEC2 silently rewrites a "
                "zero-volt source to 1 V) — un-tick Excited instead",
            )
            obj.Amplitude = 1.0
        if "PhaseDeg" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "PhaseDeg",
                _GROUP,
                "Drive voltage phase (degrees) for multi-port excitation",
            )
            obj.PhaseDeg = 0.0
        if "PortType" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "PortType",
                _GROUP,
                "Lumped: R across a gap. MSL: microstrip transmission-line port "
                "(reference = a box spanning line width x feed length x substrate "
                "height; Direction = E-field axis, PropagationDirection = along the line)",
            )
            obj.PortType = ["Lumped", "MSL", "RectWaveguide"]
            obj.PortType = "Lumped"
        if "WaveguideMode" not in props:
            obj.addProperty(
                "App::PropertyString", "WaveguideMode", _GROUP,
                "Waveguide mode for a RectWaveguide port, e.g. TE10 (the "
                "dominant mode of a rectangular guide) or TE20/TE11. openEMS "
                "generates the analytic TE_mn profile; only TE modes are "
                "supported. The guide's a and b are taken from the referenced "
                "port FACE, so the mode and the geometry cannot disagree.")
            obj.WaveguideMode = "TE10"
        if "PropagationDirection" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "PropagationDirection",
                _GROUP,
                "Wave propagation direction along the line (MSL ports)",
            )
            obj.PropagationDirection = DIRECTIONS
            obj.PropagationDirection = "+X"

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


class ViewProviderLumpedPort:
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


def _next_port_number(analysis):
    used = []
    if analysis is not None:
        for child in analysis.Group:
            if getattr(child, "EMStudioType", "") == LumpedPort.Type:
                used.append(child.PortNumber)
    n = 1
    while n in used:
        n += 1
    return n


def makeLumpedPort(doc=None, analysis=None, name="EMPort", references=None, direction="+Z"):
    """Create a lumped port, auto-numbering it within the analysis."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    LumpedPort(obj)
    obj.Direction = direction
    obj.PortNumber = _next_port_number(analysis)
    if references:
        obj.References = references
    if FreeCAD.GuiUp:
        ViewProviderLumpedPort(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj
