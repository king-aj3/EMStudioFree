# SPDX-License-Identifier: LGPL-2.1-or-later
"""The EM Analysis container object.

An *EM Analysis* is the root of every EMStudio simulation. Like FreeCAD FEM's
``Fem::FemAnalysis``, it is a **group** that owns the child objects of a study
(solver settings, material assignments, ports, boundary conditions, mesh, results).
We implement it as a scripted ``App::DocumentObjectGroupPython`` via the Proxy pattern,
because the C++ analysis type cannot be subclassed from Python.

Design notes
------------
* GUI-safe: the ViewProvider is only defined/attached when ``FreeCAD.GuiUp`` is true,
  so this module imports cleanly under ``freecadcmd`` and plain pytest.
* Serialization uses the FreeCAD 1.x ``dumps``/``loads`` protocol with ``__getstate__``/
  ``__setstate__`` shims so the same code loads under 0.21.x.
* ``makeAnalysis`` is the public factory the command layer and tests call.
"""

from __future__ import annotations

import FreeCAD

# Property group label shown in the FreeCAD property editor.
_GROUP = "EMStudio"
_GROUP_FREQ = "Frequency Sweep"
_GROUP_DOMAIN = "Simulation Domain"
_GROUP_MESH = "Mesh"

# openEMS boundary condition names (applied per domain face).
BOUNDARY_CONDITIONS = ["PML_8", "MUR", "PEC", "PMC"]


class Analysis:
    """Proxy for an EMStudio EM Analysis group object."""

    Type = "EMStudio::Analysis"

    def __init__(self, obj):
        obj.Proxy = self
        self._ensure_properties(obj)

    # -- property setup -----------------------------------------------------
    def _ensure_properties(self, obj):
        """Add EMStudio properties idempotently (safe on reload/migration)."""
        props = obj.PropertiesList
        if "EMStudioType" not in props:
            obj.addProperty(
                "App::PropertyString",
                "EMStudioType",
                _GROUP,
                "Object type tag used by EMStudio to identify this object",
            )
            obj.EMStudioType = self.Type
            obj.setEditorMode("EMStudioType", 1)  # read-only in the editor
        if "SchemaVersion" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "SchemaVersion",
                _GROUP,
                "EMStudio data-schema version, for forward migration",
            )
            obj.SchemaVersion = 1
            obj.setEditorMode("SchemaVersion", 1)
        # Frequency sweep
        if "FrequencyStart" not in props:
            obj.addProperty(
                "App::PropertyFrequency",
                "FrequencyStart",
                _GROUP_FREQ,
                "Sweep start frequency",
            )
            obj.FrequencyStart = "100 MHz"
        if "FrequencyStop" not in props:
            obj.addProperty(
                "App::PropertyFrequency",
                "FrequencyStop",
                _GROUP_FREQ,
                "Sweep stop frequency",
            )
            obj.FrequencyStop = "1 GHz"
        if "FrequencyPoints" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "FrequencyPoints",
                _GROUP_FREQ,
                "Number of frequency points in post-processed sweeps",
            )
            obj.FrequencyPoints = 201
        # Simulation domain (openEMS)
        for bc_name, default in (
            ("BoundaryXmin", "MUR"), ("BoundaryXmax", "MUR"),
            ("BoundaryYmin", "MUR"), ("BoundaryYmax", "MUR"),
            ("BoundaryZmin", "MUR"), ("BoundaryZmax", "MUR"),
        ):
            if bc_name not in props:
                obj.addProperty(
                    "App::PropertyEnumeration",
                    bc_name,
                    _GROUP_DOMAIN,
                    "Absorbing/reflecting boundary on this domain face (openEMS)",
                )
                setattr(obj, bc_name, BOUNDARY_CONDITIONS)
                setattr(obj, bc_name, default)
        if "DomainPaddingWavelengths" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "DomainPaddingWavelengths",
                _GROUP_DOMAIN,
                "Air padding around the geometry, in wavelengths at the center frequency",
            )
            obj.DomainPaddingWavelengths = 0.25
        # Mesh (openEMS FDTD grid)
        if "MeshResolution" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "MeshResolution",
                _GROUP_MESH,
                "Target mesh lines per wavelength at the highest sweep frequency",
            )
            obj.MeshResolution = 20
        if "MeshSmoothRatio" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "MeshSmoothRatio",
                _GROUP_MESH,
                "Maximum ratio between neighboring mesh cell sizes",
            )
            obj.MeshSmoothRatio = 1.4

    # -- typed sweep accessors (Hz floats, for writers) ----------------------
    @staticmethod
    def freq_range_hz(obj):
        """Return (f_start, f_stop, n_points) in plain Hz floats."""
        f1 = float(obj.FrequencyStart.getValueAs("Hz"))
        f2 = float(obj.FrequencyStop.getValueAs("Hz"))
        return f1, f2, int(obj.FrequencyPoints)

    @staticmethod
    def boundary_list(obj):
        """openEMS boundary list [xmin, xmax, ymin, ymax, zmin, zmax]."""
        return [
            obj.BoundaryXmin, obj.BoundaryXmax,
            obj.BoundaryYmin, obj.BoundaryYmax,
            obj.BoundaryZmin, obj.BoundaryZmax,
        ]

    # -- lifecycle hooks ----------------------------------------------------
    def onDocumentRestored(self, obj):
        # Re-assert properties for documents saved by older EMStudio versions.
        self._ensure_properties(obj)

    def execute(self, obj):
        # The container itself computes nothing; children carry the work.
        return

    # -- serialization (1.x dumps/loads + 0.21 getstate/setstate) ----------
    def dumps(self):
        return None

    def loads(self, state):
        return None

    # 0.21 fallback names
    __getstate__ = dumps
    __setstate__ = loads


class ViewProviderAnalysis:
    """Minimal ViewProvider so the analysis shows an icon and acts as active study."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def getIcon(self):
        from emstudio.resources import icon_path

        return icon_path("emstudio_analysis.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def makeAnalysis(doc=None, name="EMAnalysis"):
    """Create and return a new EM Analysis in ``doc`` (active document by default)."""
    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()
    obj = doc.addObject("App::DocumentObjectGroupPython", name)
    Analysis(obj)
    if FreeCAD.GuiUp:
        ViewProviderAnalysis(obj.ViewObject)
    obj.Label = "EM Analysis"
    return obj
