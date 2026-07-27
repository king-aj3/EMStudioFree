# SPDX-License-Identifier: LGPL-2.1-or-later
"""Coil excitation object for magnetics analyses (Elmer backend).

A ``Coil`` marks referenced geometry (a coaxial ring/tube solid) as a
stranded, current-driven winding: N turns carrying a sinusoidal current
of given PEAK amplitude and phase, uniformly distributed over the
cross-section. The Elmer writer turns it into a harmonic
``Current Density`` body force; the region's bulk conductivity is forced
to zero (stranded model — use the Litz Designer for the winding's own
AC-resistance).
"""

from __future__ import annotations

import FreeCAD

_GROUP = "EMStudio"


class Coil:
    """Proxy for a coil excitation."""

    Type = "EMStudio::Coil"

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
                "Coil geometry (a coaxial ring/tube solid centered on the Z axis)",
            )
        if "Turns" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "Turns",
                _GROUP,
                "Number of turns wound through this cross-section",
            )
            obj.Turns = 10
        if "Current" not in props:
            obj.addProperty(
                "App::PropertyElectricCurrent",
                "Current",
                _GROUP,
                "Coil current, PEAK amplitude of the sinusoid",
            )
            obj.Current = "1 A"
        if "PhaseDeg" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "PhaseDeg",
                _GROUP,
                "Current phase in degrees (multi-coil drive)",
            )
            obj.PhaseDeg = 0.0
        if "Reversed" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "Reversed",
                _GROUP,
                "Reverse the winding sense (current flows in -phi)",
            )
            obj.Reversed = False

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


class ViewProviderCoil:
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


def makeCoil(doc=None, analysis=None, name="EMCoil", references=None, turns=10,
             current_a=1.0):
    """Create a coil excitation, optionally adding it to an analysis group."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    Coil(obj)
    if references:
        obj.References = references
    obj.Turns = int(turns)
    obj.Current = "{0} A".format(float(current_a))
    if FreeCAD.GuiUp:
        ViewProviderCoil(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj
