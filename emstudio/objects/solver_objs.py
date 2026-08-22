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

    def _migrate_full_2port(self, obj):
        """Carry a pre-v1.2.0 ``Full2Port`` value onto ``FullSMatrix``, then drop it.

        The switch was named for two ports while two was the only order the
        solvers could do. It never reached a customer — the 2-port work was
        still unreleased when the N-port work landed — so the rename is clean
        rather than a deprecation. What DOES exist is documents saved on the
        dev machines while the 2-port path was being proven, and silently
        resetting their setting to False would turn a full-matrix solve into a
        single-column one with no sign that anything changed.

        Runs from ``onDocumentRestored``, so a restored document is migrated
        before any solve reads the property.
        """
        if "Full2Port" not in obj.PropertiesList:
            return
        try:
            if bool(getattr(obj, "Full2Port", False)):
                obj.FullSMatrix = True
            obj.removeProperty("Full2Port")
        except Exception:                       # noqa: BLE001 - see below
            # A property that cannot be removed (older FreeCAD, read-only doc)
            # is cosmetic clutter; the VALUE is already carried across, which
            # is the part that changes what the solver does. Never let a
            # migration stop a document from opening.
            pass

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
        if "FullSMatrix" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "FullSMatrix",
                _GROUP,
                "Multi-port analyses: run one EXTRA FDTD simulation per "
                "remaining port, giving the complete NxN S-matrix instead of "
                "the single column one excitation gives. Required for a "
                "multi-port Touchstone (.sNp) export — a VNA comparison needs "
                "S12 and S22, and no assumption recovers them from a port-1 "
                "solve. openEMS solves one excitation per run, so this is "
                "genuinely N simulations: roughly N times the time.",
            )
            obj.FullSMatrix = False
        self._migrate_full_2port(obj)
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
                "Record an NF2FF box and compute the radiation pattern",
            )
            obj.ComputeFarField = True
        # ⚠⚠ THESE THREE WERE DECLARED ON NEC2 ONLY, AND THE HORN TEMPLATE HAS
        # BEEN SETTING THEM SINCE 2026-08-22 BEHIND
        # ``if "PatternFrequencies" in solver.PropertiesList:`` — a guard that
        # was always False on an openEMS solver. Measured under freecadcmd on a
        # freshly built horn: PatternFreq props == []. So the "the horn template
        # now pins ~30 GHz" line in the handoff described something that had
        # never executed once. Declaring them here is what makes that true.
        # ⛳ The semantics are NEC2's, deliberately: 0 = one pattern at the
        # default frequency, N > 1 = N patterns across PatternFreqStart..Stop.
        # ⚠ The COST NOTE IS NOT NEC2's. NEC2 pays one extra solver run and
        # ~0.33 MB per frequency; openEMS pays neither. Its NF2FF box is
        # recorded broadband in the time domain, so every extra frequency is one
        # more DFT over data the run already holds — no extra solve, and one
        # small CSV. What it DOES cost is post-processing memory: openEMS holds
        # one complex array per frequency per box face at once.
        # ⚠ Do NOT hoist these into _ensure_common. Palace, Elmer, OpenFOAM and
        # FastHenry would each sprout a field nothing reads, which is the exact
        # defect this is fixing.
        if "PatternFrequencies" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "PatternFrequencies",
                _GROUP,
                "How many radiation patterns to compute across the sweep. "
                "0 = one, at the default frequency (default). Set e.g. 11 to "
                "scroll the pattern across the band in the results dialog. "
                "On openEMS these are extra transforms of one recording, not "
                "extra solver runs, so the run time does not change.",
            )
            obj.PatternFrequencies = 0
        for _name, _doc in (
                ("PatternFreqStart",
                 "First frequency of the radiation-pattern pass. 0 = start "
                 "where the analysis sweep starts (default). Only used when "
                 "PatternFrequencies is 2 or more."),
                ("PatternFreqStop",
                 "Last frequency of the radiation-pattern pass. 0 = stop where "
                 "the analysis sweep stops (default). Only used when "
                 "PatternFrequencies is 2 or more."),
        ):
            if _name not in props:
                obj.addProperty("App::PropertyFrequency", _name, _GROUP, _doc)
                setattr(obj, _name, 0.0)
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
        # How many frequencies get a RADIATION PATTERN.
        #
        # 0 (default) = one pattern, at the best-match frequency — exactly what
        # every existing document produced, so nothing changes unless asked.
        # N > 1 = N patterns evenly spanning the sweep band, which you can then
        # scroll through in the results dialog.
        #
        # This is CHEAP and the number is measured: NEC2 runs the RP card at
        # every step of the FR card, so N patterns cost ONE extra run, not N.
        # 201 points took 7.18 s (2026-08-06). What it does cost is OUTPUT:
        # ~0.33 MB per frequency, 65 MB for 201 — which is why this is a count
        # to be chosen rather than "always all of them".
        if "PatternFrequencies" not in props:
            obj.addProperty(
                "App::PropertyInteger",
                "PatternFrequencies",
                _GROUP,
                "How many radiation patterns to compute across the sweep. "
                "0 = one, at the best-match frequency (default). Set e.g. 11 "
                "to scroll the pattern across the band in the results dialog. "
                "Costs one extra solver run regardless of the count, but about "
                "0.33 MB of output per frequency.",
            )
            obj.PatternFrequencies = 0
        # The BAND the patterns span. Both default to 0 = "follow the analysis
        # sweep", which is what PatternFrequencies did on its own and keeps
        # every existing document byte-identical. Setting them lets the pattern
        # pass cover a NARROWER band than the S11 sweep — the usual want, since
        # patterns cost ~0.33 MB each and the interesting ones cluster around
        # resonance, not across a decade of mismatch.
        #
        # A stop BELOW the start, or a zero span, falls back to the sweep
        # rather than erroring: these are two numbers in a property editor and
        # a half-entered pair must not break a solve.
        for _name, _doc in (
                ("PatternFreqStart",
                 "First frequency of the radiation-pattern pass. 0 = start "
                 "where the analysis sweep starts (default). Only used when "
                 "PatternFrequencies is 2 or more."),
                ("PatternFreqStop",
                 "Last frequency of the radiation-pattern pass. 0 = stop where "
                 "the analysis sweep stops (default). Only used when "
                 "PatternFrequencies is 2 or more."),
        ):
            if _name not in props:
                obj.addProperty("App::PropertyFrequency", _name, _GROUP, _doc)
                setattr(obj, _name, 0.0)
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
        if "GroundRadials" not in props:
            obj.addProperty(
                "App::PropertyInteger", "GroundRadials", "NEC2",
                "Number of radial wires in a ground screen (NEC-2 GN field "
                "I2). 0 = none. A radial screen is what makes a real "
                "ground-mounted vertical work — measured on a 20 m monopole at "
                "3.5 MHz, 16 radials moved gain from -26.56 to -19.71 dB and "
                "the feed reactance from j153 to j33.\n"
                "⚠ Radials REQUIRE the reflection-coefficient ground (GN 0). "
                "See GroundType.")
            obj.GroundRadials = 0
        if "RadialLength" not in props:
            obj.addProperty(
                "App::PropertyLength", "RadialLength", "NEC2",
                "Length of each radial, i.e. the screen radius (NEC-2 GN F3). "
                "Only used when GroundRadials > 0.")
            obj.RadialLength = "10 m"
        if "RadialWireRadius" not in props:
            obj.addProperty(
                "App::PropertyLength", "RadialWireRadius", "NEC2",
                "Radius of the individual radial wires (NEC-2 GN F4). Only "
                "used when GroundRadials > 0.")
            obj.RadialWireRadius = "1 mm"
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
        if "MPIRanks" not in props:
            obj.addProperty(
                "App::PropertyInteger", "MPIRanks", "Palace",
                "MPI processes for the solve (palace -np N). 0 = AUTO, which "
                "picks a sensible fraction of this machine's cores. 1 forces "
                "serial. FEM assembly and the linear solve are the expensive "
                "parts and both parallelise, so this is the single biggest "
                "runtime lever Palace has.")
            obj.MPIRanks = 0
        if "OMPThreads" not in props:
            obj.addProperty(
                "App::PropertyInteger", "OMPThreads", "Palace",
                "OpenMP threads per MPI rank (palace -nt N). Only meaningful "
                "for an OpenMP-enabled Palace build; 1 is safe everywhere. "
                "⚠ Threads MULTIPLY ranks — ranks x threads should not exceed "
                "the core count or the ranks fight each other and it runs "
                "SLOWER than serial.")
            obj.OMPThreads = 1
        if "Device" not in props:
            obj.addProperty(
                "App::PropertyEnumeration", "Device", "Palace",
                "MFEM compute device. GPU needs a Palace BUILT with CUDA or "
                "HIP; on a CPU-only build Palace falls back and says so, it "
                "does not fail. Verify with Solver Setup rather than assuming "
                "the box's GPU is usable.")
            obj.Device = ["CPU", "GPU"]
            obj.Device = "CPU"
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
        if "FullSMatrix" not in props:
            obj.addProperty(
                "App::PropertyBool",
                "FullSMatrix",
                _GROUP,
                "Driven S-parameters only: solve EVERY excitation to get the "
                "complete NxN S-matrix instead of the single column one "
                "excitation gives. Required for a multi-port Touchstone "
                "(.sNp) export — a VNA comparison needs S12 and S22, and no "
                "assumption can recover them from a port-1 solve. Costs one "
                "solve per port on the same mesh, so roughly N times the time.",
            )
            obj.FullSMatrix = False
        self._migrate_full_2port(obj)
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


class SolverOpenFOAM(_SolverBase):
    """Convection solve for a cable bundle in an enclosure.

    ⚠ **This solver takes MINUTES, which makes it unlike every other object
    here.** The others are parameter bags read at run time; this one CACHES a
    result, because the number it produces (``BundleFactor``) is consumed
    inside `thermal.solve_steady`'s bisection — ~80 evaluations per ampacity
    answer. Re-solving there would be thousands of CFD runs.

    So the object holds the solved factor AND the geometry it was solved for.
    `FactorStale` compares them, because confinement and spacing are precisely
    what the factor measures: it does not survive a geometry change, and a
    silently-carried-over factor is worse than none.
    """

    Type = "EMStudio::SolverOpenFOAM"

    def _ensure_properties(self, obj):
        self._ensure_common(obj)
        props = obj.PropertiesList
        if "EnclosureClearance" not in props:
            obj.addProperty(
                "App::PropertyFloat", "EnclosureClearance", _GROUP,
                "Enclosure size as a multiple of the bundle's own extent. "
                "NOT packaging: measured, 0.40 m -> 0.20 m around one 20 mm "
                "cable cost 3 % of h",
            )
            obj.EnclosureClearance = 5.0
        if "WallGradient" not in props:
            obj.addProperty(
                "App::PropertyFloat", "WallGradient", _GROUP,
                "Prescribed wall temperature gradient, K/m. Flux is the "
                "physical condition for a Joule-heated cable; the surface "
                "temperature is then an OUTPUT",
            )
            obj.WallGradient = 400.0
        if "Iterations" not in props:
            obj.addProperty(
                "App::PropertyInteger", "Iterations", _GROUP,
                "Maximum SIMPLE iterations (residualControl may stop earlier)",
            )
            obj.Iterations = 8000
        if "BackgroundCells" not in props:
            obj.addProperty(
                "App::PropertyInteger", "BackgroundCells", _GROUP,
                "Background mesh cells across the enclosure before snappy "
                "refinement",
            )
            obj.BackgroundCells = 100
        # --- solved results, read-only: these are MEASUREMENTS, not settings
        if "BundleFactor" not in props:
            obj.addProperty(
                "App::PropertyFloat", "BundleFactor", _GROUP,
                "Solved convection factor on Churchill-Chu (1.0 = the bare "
                "correlation). Feeds wire/thermal.solve_steady",
            )
            obj.BundleFactor = 1.0
            obj.setEditorMode("BundleFactor", 1)
        if "FactorProvenance" not in props:
            obj.addProperty(
                "App::PropertyString", "FactorProvenance", _GROUP,
                "What produced the factor: Nu, the correlation, Ra, and "
                "whether it converged. A factor nobody can trace is worse "
                "than no factor",
            )
            obj.FactorProvenance = ""
            obj.setEditorMode("FactorProvenance", 1)
        if "SolvedGeometry" not in props:
            obj.addProperty(
                "App::PropertyString", "SolvedGeometry", _GROUP,
                "Geometry key the factor was solved for (staleness check)",
            )
            obj.SolvedGeometry = ""
            obj.setEditorMode("SolvedGeometry", 1)
        if "FactorConverged" not in props:
            obj.addProperty(
                "App::PropertyBool", "FactorConverged", _GROUP,
                "Did the solve that produced the factor actually converge? "
                "rc == 0 is not convergence",
            )
            obj.FactorConverged = False
            obj.setEditorMode("FactorConverged", 1)
        if "SizeFactors" not in props:
            obj.addProperty(
                "App::PropertyString", "SizeFactors", _GROUP,
                "Per-SIZE factors on a mixed-diameter bundle, as "
                "'<diameter mm>:<factor>' pairs. Empty on a uniform bundle, "
                "which has only the one factor. Nu_D is built on a diameter, "
                "so a mixed bundle genuinely has one factor per size",
            )
            obj.SizeFactors = ""
            obj.setEditorMode("SizeFactors", 1)

    @staticmethod
    def format_size_factors(mixed):
        """The solved groups as text: ``'20:0.947900; 10:0.843800'``.

        ⚠ A diameter carrying more than one group gets its WALL FLUX in the
        key — ``'20@400:0.947900; 20@100:0.981200'`` — because same-size cables
        on different losses have different factors and the diameter alone
        cannot tell them apart. Sizes that are unambiguous keep the bare form,
        so documents written before groups existed still read back identically.
        """
        counts = {}
        for f in mixed.by_group.values():
            counts[f.d_cable] = counts.get(f.d_cable, 0) + 1
        parts = []
        for f in mixed.by_group.values():
            key = ("%.4g" % (1000.0 * f.d_cable) if counts[f.d_cable] == 1
                   else "%.4g@%.6g" % (1000.0 * f.d_cable, f.gradient))
            parts.append("%s:%.6f" % (key, f.factor))
        return "; ".join(parts)

    @staticmethod
    def parse_group_factors(text):
        """``[(diameter_m, gradient_or_None, factor)]`` — every solved group.

        ⚠ Raises on anything it cannot read rather than returning a partial
        list. A silently-short reading would hand the caller the bare
        correlation for a cable that was actually solved.
        """
        out = []
        for part in (p.strip() for p in str(text or "").split(";")):
            if not part:
                continue
            try:
                key, f = part.split(":")
                if "@" in key:
                    d_mm, grad = key.split("@")
                    out.append((float(d_mm) / 1000.0, float(grad), float(f)))
                else:
                    out.append((float(key) / 1000.0, None, float(f)))
            except ValueError:
                raise ValueError(
                    "cannot read %r as a '<diameter mm>[@<K/m>]:<factor>' "
                    "entry" % part)
        return out

    @classmethod
    def parse_size_factors(cls, text):
        """``{diameter_m: factor}`` — the common case, keyed by size.

        ⚠ RAISES when one diameter carries several groups, rather than losing
        one. Use :meth:`parse_group_factors` there.
        """
        out = {}
        for d, grad, f in cls.parse_group_factors(text):
            if d in out:
                raise ValueError(
                    "%.4g mm carries more than one solved group, so this "
                    "cannot be keyed by size — read parse_group_factors()"
                    % (1000.0 * d))
            out[d] = f
        return out

    def store_factor(self, obj, factor):
        """Record a solved :class:`BundleFactor` on the object."""
        obj.BundleFactor = float(factor.factor)
        obj.FactorProvenance = str(factor.provenance)
        obj.SolvedGeometry = str(factor.geometry)
        obj.FactorConverged = bool(factor.converged)
        obj.SizeFactors = ""

    def store_mixed_factors(self, obj, mixed):
        """Record a solved ``MixedBundleFactor`` — one factor per solved GROUP.

        A group is one diameter at one wall flux, so a bundle where two
        same-size cables run at different losses has two entries for that size
        and ``SizeFactors`` keys them by ``<mm>@<K/m>``.

        ⚠ ``BundleFactor`` is set to the WORST group's factor, deliberately.
        Something will read that scalar without knowing the bundle is mixed,
        and of the two ways to be wrong, under-rating the cables that cool well
        is the safe one — over-rating the one that does not is how a cable
        runs hot. The provenance says out loud that it is a floor, not the
        bundle's factor, and ``SizeFactors`` carries the real answers.
        """
        obj.BundleFactor = float(mixed.worst.factor)
        obj.FactorProvenance = (
            "%s || the scalar BundleFactor above is the WORST group's "
            "(%.4g mm at %.4g K/m), applied as a conservative floor — the "
            "per-group factors in SizeFactors are the answers"
            % (mixed.provenance, 1000.0 * mixed.worst.d_cable,
               mixed.worst.gradient))
        obj.SolvedGeometry = str(mixed.geometry)
        obj.FactorConverged = bool(mixed.converged)
        obj.SizeFactors = self.format_size_factors(mixed)

    def factor_for(self, obj, d_cable, gradient=None, tol=1e-9):
        """The cached factor for one cable.

        Falls through to the single ``BundleFactor`` when the bundle was
        uniform. On a mixed bundle it REFUSES a cable that was not solved
        rather than handing back the conservative floor dressed as that
        cable's own measurement — and refuses an ambiguous diameter rather
        than picking one of its groups.
        """
        groups = self.parse_group_factors(getattr(obj, "SizeFactors", ""))
        if not groups:
            return float(obj.BundleFactor)
        hits = [g for g in groups if abs(g[0] - float(d_cable)) <= tol]
        if not hits:
            raise ValueError(
                "no factor was solved for a %.4g mm cable; this bundle "
                "carries %s"
                % (1000.0 * float(d_cable),
                   ", ".join("%.4g mm" % (1000.0 * d)
                             for d in sorted({g[0] for g in groups},
                                             reverse=True))))
        if gradient is not None:
            exact = [g for g in hits
                     if g[1] is not None and abs(g[1] - float(gradient)) <= 1e-9]
            if not exact:
                raise ValueError(
                    "no %.4g mm group was solved at %.4g K/m; that size was "
                    "solved at %s"
                    % (1000.0 * float(d_cable), float(gradient),
                       ", ".join("%.4g K/m" % g[1] if g[1] is not None
                                 else "an unrecorded flux" for g in hits)))
            return exact[0][2]
        if len(hits) > 1:
            raise ValueError(
                "%.4g mm carries %d solved groups (%s K/m) — say which with "
                "factor_for(obj, d, gradient=...). Same-size cables on "
                "different losses do not share a factor."
                % (1000.0 * float(d_cable), len(hits),
                   ", ".join("%.4g" % g[1] for g in hits if g[1] is not None)))
        return hits[0][2]

    def factor_stale(self, obj, geometry_key):
        """True when the cached factor was solved for a DIFFERENT design.

        ⚠ Returns True for an EMPTY SolvedGeometry too: no recorded geometry
        means the factor cannot be shown to match, and "cannot be shown to
        match" must not read as "matches".
        """
        if not getattr(obj, "SolvedGeometry", ""):
            return True
        return obj.SolvedGeometry != geometry_key


def makeSolverOpenFOAM(doc=None, analysis=None, name="SolverOpenFOAM"):
    if doc is None:
        doc = FreeCAD.ActiveDocument
    obj = doc.addObject("App::FeaturePython", name)
    SolverOpenFOAM(obj)
    if FreeCAD.GuiUp:
        _ViewProviderSolver(obj.ViewObject)
    if analysis is not None:
        analysis.addObject(obj)
    return obj
