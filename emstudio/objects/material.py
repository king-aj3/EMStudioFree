# SPDX-License-Identifier: LGPL-2.1-or-later
"""EM material assignment object.

An ``EMMaterial`` attaches electromagnetic material properties to one or more geometry
objects (or sub-elements) via a ``References`` LinkSubList. Solver writers walk the
analysis group, collect these, and emit backend-specific material definitions
(CSXCAD metal/material properties for openEMS, GW wire cards for NEC2, ...).

Categories (MVP):
* ``Metal (PEC)`` — perfect electric conductor. ``WireRadius`` is used when the
  referenced geometry is wire-like edges consumed by the NEC2 backend.
* ``Dielectric`` — relative permittivity + loss (as conductivity kappa or loss tangent).
* ``Conductor`` — finite conductivity metal (openEMS conducting sheet / lossy metal),
  reserved; treated as PEC by writers until Phase 2.
"""

from __future__ import annotations

import FreeCAD

_GROUP = "EMStudio"

CATEGORIES = ["Metal (PEC)", "Dielectric", "Conductor"]

# The library lives in material_library.py so it can be imported (and gated)
# without FreeCAD. Re-exported here so every existing import keeps working.
from emstudio.objects.material_library import (  # noqa: F401
    MATERIAL_LIBRARY, PEC_PRESET, PRESETS, apply_preset,
)


class Material:
    """Proxy for an EM material assignment."""

    Type = "EMStudio::Material"

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
                "Geometry (objects or faces/edges) this material applies to",
            )
        if "Category" not in props:
            obj.addProperty(
                "App::PropertyEnumeration", "Category", _GROUP, "Material category"
            )
            obj.Category = CATEGORIES
            obj.Category = "Metal (PEC)"
        if "RelPermittivity" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "RelPermittivity",
                _GROUP,
                "Relative permittivity (dielectrics)",
            )
            obj.RelPermittivity = 1.0
        if "LossTangent" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "LossTangent",
                _GROUP,
                "Dielectric loss tangent tan(d) at the analysis center frequency",
            )
            obj.LossTangent = 0.0
        if "Preset" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "Preset",
                _GROUP,
                "Named material from the EMStudio library (CST/HFSS-style). "
                "Selecting one fills in this material's properties and sets "
                "its Category. 'Custom' leaves your typed values alone. "
                "Library values are NOMINAL at 20 C — see MATERIAL_LIBRARY; "
                "for anything you will build, use the vendor's number.",
            )
            obj.Preset = PRESETS
            obj.Preset = PEC_PRESET
        if "Conductivity" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "Conductivity",
                _GROUP,
                "Electric conductivity in S/m (Conductor category)",
            )
            obj.Conductivity = 0.0
        if "ConductivityTempCoeff" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "ConductivityTempCoeff",
                _GROUP,
                "Temperature coefficient α of electrical resistivity, per K: "
                "σ(T) = Conductivity / (1 + α·(T − ambient)). 0 = constant σ "
                "(default). Needs the Elmer solver's SolveThermal and this "
                "material's ThermalConductivity — the magnetic solve then "
                "iterates two-way with the heat equation (coupled Joule).",
            )
            obj.ConductivityTempCoeff = 0.0
        if "RelPermeability" not in props:
            obj.addProperty(
                "App::PropertyFloat", "RelPermeability", _GROUP, "Relative permeability"
            )
            obj.RelPermeability = 1.0
        if "BHCurveB" not in props:
            obj.addProperty(
                "App::PropertyFloatList",
                "BHCurveB",
                _GROUP,
                "Nonlinear B-H curve: flux-density points B in tesla, paired "
                "1:1 with BHCurveH. Empty = linear (RelPermeability). Start "
                "at 0, strictly increasing, ~40 points sampled roughly "
                "UNIFORMLY IN B (a uniform-in-H table under-resolves the "
                "knee). Used by the Elmer magnetics solver: exact in the "
                "Static (DC) analysis; effective-permeability (peak-|B| "
                "secant) approximation in Harmonic (AC).",
            )
            obj.BHCurveB = []
        if "BHCurveH" not in props:
            obj.addProperty(
                "App::PropertyFloatList",
                "BHCurveH",
                _GROUP,
                "Nonlinear B-H curve: field-strength points H in A/m, paired "
                "1:1 with BHCurveB (B first, H second — Elmer's table order). "
                "Start at 0, strictly increasing.",
            )
            obj.BHCurveH = []
        if "Priority" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "Priority",
                _GROUP,
                "Overlap priority (higher wins where volumes overlap)",
            )
            obj.Priority = 10
        if "ThermalConductivity" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "ThermalConductivity",
                _GROUP,
                "Heat conductivity in W/(m*K) — enables the thermal chain on "
                "this body when the Elmer solver's SolveThermal is on "
                "(0 = body excluded from the heat solve)",
            )
            obj.ThermalConductivity = 0.0
        if "ThermalConductivityTempCoeff" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "ThermalConductivityTempCoeff",
                _GROUP,
                "Temperature coefficient β of heat conductivity, per K: "
                "k(T) = ThermalConductivity·(1 + β·(T − ambient)). "
                "0 = constant k (default). Makes the steady heat solve "
                "nonlinear (Newton).",
            )
            obj.ThermalConductivityTempCoeff = 0.0
        if "Density" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "Density",
                _GROUP,
                "Mass density in kg/m^3 (transient heating only)",
            )
            obj.Density = 0.0
        if "SpecificHeat" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "SpecificHeat",
                _GROUP,
                "Specific heat capacity in J/(kg*K) (transient heating only)",
            )
            obj.SpecificHeat = 0.0
        if "SheetThickness" not in props:
            obj.addProperty(
                "App::PropertyLength",
                "SheetThickness",
                _GROUP,
                "Modelled metal thickness for the finite-conductivity SHEET "
                "model (openEMS AddConductingSheet). Default 35 um = 1 oz "
                "copper, the PCB standard. Only used when Category is "
                "Conductor; ignored for PEC.",
            )
            obj.SheetThickness = "0.035 mm"
        if "WireRadius" not in props:
            obj.addProperty(
                "App::PropertyLength",
                "WireRadius",
                _GROUP,
                "Wire radius used when edges of this material feed the NEC2 backend",
            )
            obj.WireRadius = "1 mm"

    def onChanged(self, obj, prop):
        """Apply a library material the moment the user picks one.

        ⚠ Guarded three ways, because onChanged also fires while properties are
        being CREATED and while a document is being RESTORED. Without the
        guards, opening a saved file would re-apply the preset over whatever
        the user had customised since — silently reverting their numbers on
        load, which is a far nastier bug than the one this feature fixes.
        """
        if prop != "Preset":
            return
        if getattr(self, "_applying", False):
            return
        doc = getattr(obj, "Document", None)
        if doc is not None and getattr(doc, "Restoring", False):
            return
        if "Conductivity" not in obj.PropertiesList:
            return                      # still mid-construction
        name = str(getattr(obj, "Preset", "Custom"))
        if name == "Custom":
            return
        self._applying = True
        try:
            apply_preset(obj, name)
        finally:
            self._applying = False

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


class ViewProviderMaterial:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def getIcon(self):
        from emstudio.resources import icon_path

        return icon_path("emstudio_material.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def makeMaterial(doc=None, analysis=None, name="EMMaterial", category="Metal (PEC)", references=None):
    """Create an EM material, optionally adding it to an analysis group."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    Material(obj)
    obj.Category = category
    if references:
        obj.References = references
    if FreeCAD.GuiUp:
        ViewProviderMaterial(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj
