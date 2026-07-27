# SPDX-License-Identifier: LGPL-2.1-or-later
"""Solver settings objects.

Each backend gets a small document object holding its run parameters. The heavy
machinery (writer, subprocess, reader) lives in ``emstudio.solvers.*``; these objects
are just typed parameter bags inside the analysis group, so settings persist in the
``.FCStd`` file and show in the property editor.
"""

from __future__ import annotations

import FreeCAD

_GROUP = "EMStudio"


class _SolverBase:
    def __init__(self, obj):
        obj.Proxy = self
        self._ensure_properties(obj)

    def _ensure_common(self, obj):
        props = obj.PropertiesList
        if "EMStudioType" not in props:
            obj.addProperty("App::PropertyString", "EMStudioType", _GROUP, "EMStudio type tag")
            obj.EMStudioType = self.Type
            obj.setEditorMode("EMStudioType", 1)
        if "WorkingDirectory" not in props:
            obj.addProperty(
                "App::PropertyPath",
                "WorkingDirectory",
                _GROUP,
                "Solver working directory (empty = temp dir beside nothing, recreated per run)",
            )

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


class SolverOpenEMS(_SolverBase):
    Type = "EMStudio::SolverOpenEMS"

    def _ensure_properties(self, obj):
        self._ensure_common(obj)
        props = obj.PropertiesList
        if "EndCriteriaDB" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "EndCriteriaDB",
                _GROUP,
                "Stop when total energy has decayed this many dB (e.g. -40)",
            )
            obj.EndCriteriaDB = -40.0
        if "MaxTimesteps" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "MaxTimesteps",
                _GROUP,
                "Hard timestep limit (safety stop)",
            )
            obj.MaxTimesteps = 30000
        if "NumThreads" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "NumThreads",
                _GROUP,
                "Solver threads (0 = all cores)",
            )
            obj.NumThreads = 0
        if "ComputeFarField" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "ComputeFarField",
                _GROUP,
                "Record an NF2FF box and compute the radiation pattern at the best-match frequency",
            )
            obj.ComputeFarField = True
        if "NearFieldPlane" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "NearFieldPlane",
                _GROUP,
                "Record a frequency-domain |E| map on a cut plane through the "
                "geometry center (at the sweep center frequency)",
            )
            obj.NearFieldPlane = ["None", "XY", "XZ", "YZ"]
            obj.NearFieldPlane = "XY"
        if "MicrostripMeshMode" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "MicrostripMeshMode",
                _GROUP,
                "Trace-aware meshing for microstrip (MSL) ports: 'Auto' resolves "
                "the grid at lambda/50 IN THE DIELECTRIC and grades it across the "
                "strip width (needed for a physical S-parameter extraction); 'Off' "
                "keeps the antenna-scale air-wavelength grid. No effect unless an "
                "MSL port is present, so antenna analyses are unchanged.",
            )
            obj.MicrostripMeshMode = ["Auto", "Off"]
            obj.MicrostripMeshMode = "Auto"


class SolverNEC2(_SolverBase):
    Type = "EMStudio::SolverNEC2"

    def _ensure_properties(self, obj):
        self._ensure_common(obj)
        props = obj.PropertiesList
        if "SegmentsPerWavelength" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "SegmentsPerWavelength",
                _GROUP,
                "Wire segments per wavelength at the highest sweep frequency (NEC guideline: >= 10)",
            )
            obj.SegmentsPerWavelength = 40
        if "GroundType" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "GroundType",
                _GROUP,
                "Ground plane for monopole / grounded-antenna analyses. 'None' = "
                "free space (dipoles etc., the default). 'Perfect' = infinite PEC "
                "ground (image, lossless — NEC GE 1/GN 1). 'Finite' = real earth "
                "via the Sommerfeld/Norton model (GN 2) using the permittivity and "
                "conductivity below — the physically-correct VLF/LF choice, where "
                "ground loss dominates efficiency. A wire touching z=0 is fed at "
                "its base segment when a ground is present.",
            )
            obj.GroundType = [
                "None (free space)",
                "Perfect (PEC image)",
                "Finite (Sommerfeld)",
            ]
            obj.GroundType = "None (free space)"
        if "GroundEpsilonR" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "GroundEpsilonR",
                _GROUP,
                "Finite-ground relative permittivity (typical: sea water 81, "
                "average/moist ground 13, poor/dry 4). Used only for Finite ground.",
            )
            obj.GroundEpsilonR = 13.0
        if "GroundConductivity" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "GroundConductivity",
                _GROUP,
                "Finite-ground conductivity in S/m (sea water ~5, average ground "
                "~0.005, poor/dry ~0.001). Used only for Finite ground.",
            )
            obj.GroundConductivity = 0.005


class SolverElmer(_SolverBase):
    Type = "EMStudio::SolverElmer"

    def _ensure_properties(self, obj):
        self._ensure_common(obj)
        props = obj.PropertiesList
        _ELMER_MODES = ["Harmonic (AC)", "Static (DC)", "3-D Magnetostatic (DC)"]
        if "AnalysisType" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "AnalysisType",
                _GROUP,
                "Harmonic (AC) = the frequency-domain axisymmetric chain "
                "(eddy currents, thermal; nonlinear B-H as a peak-|B| "
                "effective-permeability approximation). Static (DC) = "
                "axisymmetric magnetostatics — exact nonlinear B-H, "
                "inductance at the operating current. 3-D Magnetostatic "
                "(DC) = ARBITRARY solids (WhitneyAV chain): closed coils "
                "driven by ampere-turns, B-field maps; no eddy/thermal at "
                "DC. If a 3-D coil's field comes out inverted, toggle the "
                "Coil's Reversed (the circulation sense is mesh-arbitrary).",
            )
            obj.AnalysisType = _ELMER_MODES
            obj.AnalysisType = "Harmonic (AC)"
        elif "3-D Magnetostatic (DC)" not in obj.getEnumerationsOfProperty("AnalysisType"):
            # documents saved before v0.56: extend the enum, keep the choice
            current = obj.AnalysisType
            obj.AnalysisType = _ELMER_MODES
            obj.AnalysisType = current
        if "DomainScale" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "DomainScale",
                _GROUP,
                "Air-domain radius as a multiple of the largest body extent "
                "(bigger = less far-field truncation error, slower)",
            )
            obj.DomainScale = 8.0
        if "MeshSizeBodies" not in props:
            obj.addProperty(
                "App::PropertyLength",
                "MeshSizeBodies",
                _GROUP,
                "Target mesh size inside bodies (0 = automatic, skin-depth aware)",
            )
            obj.MeshSizeBodies = "0 mm"
        if "ExtractCoupling" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "ExtractCoupling",
                _GROUP,
                "With 2+ coils: run per-coil excitations to extract L, M and "
                "the coupling coefficient k",
            )
            obj.ExtractCoupling = True
        if "SolveThermal" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "SolveThermal",
                _GROUP,
                "Also solve steady-state temperature (Joule heating as source, "
                "convection on body surfaces) in bodies whose material has "
                "ThermalConductivity > 0",
            )
            obj.SolveThermal = False
        if "AmbientTemperature" not in props:
            obj.addProperty(
                "App::PropertyTemperature",
                "AmbientTemperature",
                _GROUP,
                "Ambient/coolant temperature for the convection boundary",
            )
            obj.AmbientTemperature = "293.15 K"
        if "ConvectionCoefficient" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "ConvectionCoefficient",
                _GROUP,
                "Surface heat-transfer coefficient h in W/(m^2*K) "
                "(~5-10 free air, ~50-300 forced air, ~500-5000 water)",
            )
            obj.ConvectionCoefficient = 10.0
        if "SurfaceEmissivity" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "SurfaceEmissivity",
                _GROUP,
                "Grey-body surface emissivity for RADIATION off the body "
                "surfaces (0 = convection only; ~0.1-0.3 bright metal, "
                "~0.8 oxidized/painted). Stacks with convection; makes the "
                "heat solve nonlinear.",
            )
            obj.SurfaceEmissivity = 0.0
        if "RadiationTemperature" not in props:
            obj.addProperty(
                "App::PropertyTemperature",
                "RadiationTemperature",
                _GROUP,
                "Enclosure temperature the surfaces radiate to "
                "(default = AmbientTemperature when 0)",
            )
            obj.RadiationTemperature = "0 K"
        if "TransientHeating" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "TransientHeating",
                _GROUP,
                "Solve the temperature RISE over time (needs Density + "
                "SpecificHeat on the material) instead of only the steady state",
            )
            obj.TransientHeating = False
        if "HeatingTime" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "HeatingTime",
                _GROUP,
                "Total heating time to simulate, in seconds (transient)",
            )
            obj.HeatingTime = 60.0
        if "HeatingSteps" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "HeatingSteps",
                _GROUP,
                "Number of time steps for the transient heating solve",
            )
            obj.HeatingSteps = 30


class SolverPalace(_SolverBase):
    Type = "EMStudio::SolverPalace"

    def _ensure_properties(self, obj):
        self._ensure_common(obj)
        props = obj.PropertiesList
        if "AnalysisType" not in props:
            obj.addProperty(
                "App::PropertyEnumeration",
                "AnalysisType",
                _GROUP,
                "Eigenmode (resonant-cavity modes), Driven S-parameters "
                "(waveguide wave ports) or Driven S-parameters (coax) — a "
                "coaxial line with radial lumped ports, over the frequency sweep",
            )
            obj.AnalysisType = [
                "Eigenmode",
                "Driven S-parameters",
                "Driven S-parameters (coax)",
            ]
            obj.AnalysisType = "Eigenmode"
        if "NumModes" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "NumModes",
                _GROUP,
                "Number of resonant modes (eigenvalues) to compute",
            )
            obj.NumModes = 6
        if "Order" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "Order",
                _GROUP,
                "FEM polynomial order (2 = fast + <1%; 3-4 = spectral accuracy, "
                "much slower preconditioner setup)",
            )
            obj.Order = 2
        if "MeshSize" not in props:
            obj.addProperty(
                "App::PropertyLength",
                "MeshSize",
                _GROUP,
                "Target tetrahedral element size (0 = automatic, smallest "
                "dimension / 4)",
            )
            obj.MeshSize = "0 mm"
        if "FastSweep" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "FastSweep",
                _GROUP,
                "Driven S-parameters only: adaptive fast frequency sweep — Palace "
                "solves a few full frequencies and interpolates the dense grid "
                "(much faster over wide bands). Off = one full solve per point.",
            )
            obj.FastSweep = False
        if "AdaptiveTol" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "AdaptiveTol",
                _GROUP,
                "Fast-sweep interpolation error tolerance (smaller = more full "
                "solves, higher accuracy). Only used when FastSweep is on.",
            )
            obj.AdaptiveTol = 1.0e-3
        if "MeshRefinement" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "MeshRefinement",
                _GROUP,
                "Adaptive mesh refinement (AMR): number of refinement iterations "
                "(0 = off). Palace estimates the discretization error, refines the "
                "elements carrying the most error, and re-solves — more accuracy "
                "per degree of freedom. Works for eigenmode AND driven analyses; "
                "each iteration is a full re-solve, so 1-3 is typical.",
            )
            obj.MeshRefinement = 0
        if "RefinementTol" not in props:
            obj.addProperty(
                "App::PropertyFloat",
                "RefinementTol",
                _GROUP,
                "AMR target relative error: refinement stops early once the global "
                "error indicator falls below this. Only used when MeshRefinement > 0.",
            )
            obj.RefinementTol = 0.01


class _ViewProviderSolver:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def getIcon(self):
        from emstudio.resources import icon_path

        return icon_path("emstudio_solverdetect.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def makeSolverOpenEMS(doc=None, analysis=None, name="SolverOpenEMS"):
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    SolverOpenEMS(obj)
    if FreeCAD.GuiUp:
        _ViewProviderSolver(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj


def makeSolverNEC2(doc=None, analysis=None, name="SolverNEC2"):
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    SolverNEC2(obj)
    if FreeCAD.GuiUp:
        _ViewProviderSolver(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj


def makeSolverElmer(doc=None, analysis=None, name="SolverElmer"):
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    SolverElmer(obj)
    if FreeCAD.GuiUp:
        _ViewProviderSolver(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj


def makeSolverPalace(doc=None, analysis=None, name="SolverPalace"):
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    SolverPalace(obj)
    if FreeCAD.GuiUp:
        _ViewProviderSolver(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj
