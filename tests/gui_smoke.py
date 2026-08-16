# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real-GUI smoke test — runs the actual user-facing solve paths headlessly.

    QT_QPA_PLATFORM=offscreen freecad tests/gui_smoke.py

Exit 0 = every GUI-run path works. This exists because the freecadcmd gates use
FreeCAD's EXACT ``Shape.BoundBox``, while the real GUI returns a
TESSELLATION-shrunk box (~0.1 mm inside a curved surface). That divergence hid a
5-version-latent failure: no magnetics analysis could run from the GUI because a
coil ring's bbox no longer matched its radius (fixed v0.13.0). Any code that
reads geometry on a GUI-run path must be exercised HERE, under a real (offscreen)
FreeCAD, not only under freecadcmd.

Covers: workbench registration, the NEC2 and Elmer solve loops end to end (fast
solvers), the openEMS geometry-classification path (flat boxes — no full FDTD),
the WPT gap sweep, and construction of every results dialog. Skips the
minutes-long openEMS FDTD solve (its geometry path is what can diverge, and that
is exercised).
"""
import os
import sys
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_failures = []
_lines = []


def _log(msg):
    _lines.append(msg)
    try:
        import FreeCAD

        FreeCAD.Console.PrintMessage(msg + "\n")
    except Exception:
        pass


def check(name, fn):
    try:
        detail = fn()
        _log("  ok   - {0}{1}".format(name, (" — " + detail) if detail else ""))
    except Exception as exc:  # noqa: BLE001
        _failures.append(name)
        _log("  FAIL - {0}: {1}".format(name, exc))
        _log(traceback.format_exc())


# --- checks -------------------------------------------------------------------
def _registration():
    import FreeCADGui

    from emstudio import commands

    wbs = FreeCADGui.listWorkbenches()
    assert "EMStudioWorkbench" in wbs, "workbench not registered"
    FreeCADGui.activateWorkbench("EMStudioWorkbench")
    listed = set(FreeCADGui.listCommands())
    want = {c for c in commands.ALL_COMMANDS if c != "Separator"}
    missing = want - listed
    assert not missing, "commands missing from the GUI: {0}".format(missing)
    return "{0} commands".format(len(want))


def _nec2_dipole():
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import nec2
    from emstudio.templates import dipole

    doc = FreeCAD.newDocument("gui_dipole")
    try:
        ana = dipole.makeDipole(doc, f0_hz=300e6)
        solver = query.get_solvers(ana)[0]
        result = nec2.run(ana, solver)
        f, s11 = result.min_s11()
        assert 285e6 <= f <= 305e6, "dipole resonance off: {0:.3g} Hz".format(f)
        return "f_res {0:.1f} MHz".format(f / 1e6)
    finally:
        FreeCAD.closeDocument(doc.Name)


def _nec2_monopole():
    """The NEC2 monopole-over-ground solve loop under the GUI (VLF/LF + ground).

    Exercises the ground-writer path (GE 1 / GN 1), the base-feed segment logic,
    and the SolverNEC2 GroundType property round-trip under a real FreeCAD. A
    short lambda/10 mast at 100 kHz over perfect ground must land near the
    analytic radiation resistance (~4 ohm) and be strongly capacitive.
    """
    import FreeCAD

    import numpy as np

    from emstudio.objects import query
    from emstudio.solvers import nec2
    from emstudio.templates import monopole

    doc = FreeCAD.newDocument("gui_monopole")
    try:
        ana = monopole.makeMonopole(doc, f0_hz=100e3, height_frac=0.1,
                                    ground="Perfect (PEC image)")
        solver = query.get_solvers(ana)[0]
        result = nec2.run(ana, solver)
        i = int(np.argmin(np.abs(result.freq - 100e3)))
        z = complex(result.zin[i])
        assert 3.5 <= z.real <= 4.6, "monopole Re(Zin) off: {0:.3f}".format(z.real)
        assert z.imag < -400.0, "monopole not capacitive: {0:.1f}".format(z.imag)
        return "Zin {0:.2f}{1:+.1f}j ohm".format(z.real, z.imag)
    finally:
        FreeCAD.closeDocument(doc.Name)


def _openems_geometry():
    """The openEMS geometry-classification path under the GUI (no FDTD solve).

    Antenna/PCB geometry is flat (boxes/sheets), which tessellate exactly, so
    the PEC patch/ground/substrate must classify as native boxes — not silently
    kicked to STL (which would still 'work' but change meshing/results). This is
    the openEMS analogue of the coil-ring bbox check.
    """
    import tempfile

    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.openems import geometry
    from emstudio.templates import patch

    doc = FreeCAD.newDocument("gui_patch")
    try:
        ana = patch.makePatch(doc)
        workdir = tempfile.mkdtemp(prefix="emstudio_gui_geom_")
        kinds = []
        for mat in query.get_materials(ana):
            for prim in geometry.classify_shapes(mat, workdir, mat.Name):
                kinds.append(prim["kind"])
        assert kinds, "no primitives classified from the patch template"
        # the metal (patch + ground planes) and substrate box must be native
        # boxes; a tessellation-shrunk bbox would have broken the box/sheet test
        n_box = kinds.count("box")
        assert n_box >= 2, "expected native boxes, got kinds {0}".format(kinds)
        return "{0} boxes / {1} stl".format(n_box, kinds.count("stl"))
    finally:
        FreeCAD.closeDocument(doc.Name)


def _openems_msl_geometry():
    """The openEMS microstrip (MSL) path under the GUI: geometry + trace-aware deck.

    Builds the notch-filter template and exercises writer.write_deck WITHOUT the
    minutes-long FDTD solve, confirming under a real (offscreen) FreeCAD that:
      * the stub + substrate + port reference boxes classify as native boxes
        (MSL geometry is flat sheets/boxes, so Shape.BoundBox is exact — no
        tessellation-shrink like the curved coil rings; this guards that),
      * the MSL port branch of _collect_ports runs (AddMSLPort emitted),
      * trace-aware meshing kicks in: mesh_res is the dielectric lambda/50
        (sub-mm), NOT the antenna-scale air value, and the domain hugs the board
        (no pad below z=0 — the ground is the PEC z-min boundary).
    """
    import tempfile

    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.openems import geometry, writer
    from emstudio.templates import msl_filter

    doc = FreeCAD.newDocument("gui_msl")
    try:
        ana = msl_filter.makeNotchFilter(doc)
        workdir = tempfile.mkdtemp(prefix="emstudio_gui_msl_")
        kinds = []
        for mat in query.get_materials(ana):
            for prim in geometry.classify_shapes(mat, workdir, mat.Name):
                kinds.append(prim["kind"])
        assert kinds.count("box") >= 2, "MSL geometry should be native boxes: {0}".format(kinds)

        solver = [o for o in ana.Group
                  if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]
        deck_path, _z0, _nr = writer.write_deck(ana, solver, workdir)
        with open(deck_path, "r", encoding="utf-8") as fh:
            deck = fh.read()
        assert "AddMSLPort" in deck, "MSL deck missing AddMSLPort"
        assert "trace-aware grid" in deck, "MSL deck missing trace-aware mesh block"
        # dielectric lambda/50 at 7 GHz / eps_r 3.66 ~ 0.45 mm (sub-mm); the
        # antenna air grid would be several mm.
        for line in deck.splitlines():
            if line.startswith("mesh_res = "):
                mesh_res = float(line.split("=")[1])
                break
        else:
            raise AssertionError("deck has no mesh_res line")
        assert mesh_res < 1.0, "trace-aware mesh_res not sub-mm: {0}".format(mesh_res)
        # domain bottom pinned on the substrate (z=0), not padded below
        assert "mesh.AddLine('z', [0" in deck, "z-domain not pinned at the ground plane"
        return "{0} boxes, mesh_res {1:.3f} mm".format(kinds.count("box"), mesh_res)
    finally:
        FreeCAD.closeDocument(doc.Name)


def _elmer_induction():
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import elmer
    from emstudio.templates import induction

    doc = FreeCAD.newDocument("gui_induction")
    try:
        ana = induction.makeInduction(doc)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverElmer"][0]
        result = elmer.run(ana, solver)
        case = result.sweep_cases()[0]
        p = case["eddy_power_w"]
        t = list(case["temperature"].values())[0]["t_max"]
        assert p > 1.0, "billet power too low: {0} W".format(p)
        assert t > 293.15, "billet not heated: {0} K".format(t)
        return "P {0:.0f} W, Tmax {1:.0f} K".format(p, t)
    finally:
        FreeCAD.closeDocument(doc.Name)


def _elmer_solenoid3d():
    import os

    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import elmer
    from emstudio.templates import solenoid3d

    doc = FreeCAD.newDocument("gui_solenoid3d")
    try:
        ana = solenoid3d.makeSolenoid3D(doc)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverElmer"][0]
        assert solver.AnalysisType == "3-D Magnetostatic (DC)"
        result = elmer.run(ana, solver)  # dispatches to the WhitneyAV chain
        assert result.meta.get("mode3d"), "3-D result not flagged"
        case = result.sweep_cases()[0]
        assert case["vtu"] and os.path.isfile(case["vtu"]), "no B-field VTU"
        assert not case["solver_warnings"], case["solver_warnings"]
        return "3-D solve ok, VTU {0:.0f} kB".format(
            os.path.getsize(case["vtu"]) / 1024.0)
    finally:
        FreeCAD.closeDocument(doc.Name)


def _elmer_wpt_and_sweep():
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import elmer
    from emstudio.solvers.elmer.model import build_axi_model
    from emstudio.solvers.elmer.sweep import sweep_wpt_gap
    from emstudio.templates import wpt

    doc = FreeCAD.newDocument("gui_wpt")
    try:
        ana = wpt.makeWptPair(doc, gap_mm=20.0)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverElmer"][0]
        result = elmer.run(ana, solver)
        k = list(result.coupling_k().values())[0]
        assert 0.2 < k < 0.35, "WPT k out of range: {0}".format(k)
        # the gap sweep is the command that first exposed the GUI bbox bug
        model = build_axi_model(ana, solver)
        curve = sweep_wpt_gap(model, [15.0, 30.0], freq_hz=100e3)
        assert curve[0]["k"] > curve[1]["k"], "k should fall with gap"
        return "k {0:.3f}; sweep {1:.3f}->{2:.3f}".format(
            k, curve[0]["k"], curve[1]["k"])
    finally:
        FreeCAD.closeDocument(doc.Name)


def _palace_cavity_geometry():
    """The Palace cavity model-extraction path under the GUI (no 54s solve).

    Reads the box's bounding box — flat faces tessellate exactly, so this is
    bbox-safe, but exercising it under the GUI guards the geometry path.
    """
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.palace.model import build_cavity_model
    from emstudio.templates import cavity

    doc = FreeCAD.newDocument("gui_cavity")
    try:
        ana = cavity.makeCavity(doc, size_mm=(40.0, 20.0, 60.0))
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverPalace"][0]
        model = build_cavity_model(ana, solver)
        sx, sy, sz = model["size_mm"]
        assert abs(sx - 40) < 0.01 and abs(sy - 20) < 0.01 and abs(sz - 60) < 0.01, \
            "cavity dims wrong: {0}".format(model["size_mm"])
        cav = "box {0:.0f}x{1:.0f}x{2:.0f} mm".format(sx, sy, sz)
    finally:
        FreeCAD.closeDocument(doc.Name)

    # waveguide model extraction (propagation-axis detection) under the GUI
    from emstudio.solvers.palace.model import build_waveguide_model
    from emstudio.templates import waveguide

    doc2 = FreeCAD.newDocument("gui_wg")
    try:
        ana2 = waveguide.makeWaveguide(doc2)
        solver2 = [s for s in query.get_solvers(ana2)
                   if query.em_type(s) == "EMStudio::SolverPalace"][0]
        wm = build_waveguide_model(ana2, solver2)
        assert wm["axis"] == 2, "WR-90 guide axis should be z (2), got {0}".format(wm["axis"])
        return "{0}; waveguide axis={1}".format(cav, "xyz"[wm["axis"]])
    finally:
        FreeCAD.closeDocument(doc2.Name)


def _palace_coax_geometry():
    """The Palace coax model-extraction path under the GUI (no solve).

    Coax radii come from CylindricalSurface faces (``surf.Radius``), which is
    exactly where a GUI-vs-freecadcmd bbox divergence would bite — the coax
    analogue of the coil-ring guard (a tessellation-shrunk bbox would give the
    wrong inner/outer radius). Extract a/b/L and assert they match the template.
    """
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.palace.model import build_coax_model
    from emstudio.templates import coax

    doc = FreeCAD.newDocument("gui_coax")
    try:
        ana = coax.makeCoax(doc, a_mm=0.5, b_mm=1.15, length_mm=20.0)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverPalace"][0]
        model = build_coax_model(ana, solver)
        assert abs(model["a_mm"] - 0.5) < 0.02, "inner radius wrong: {0}".format(model["a_mm"])
        assert abs(model["b_mm"] - 1.15) < 0.02, "outer radius wrong: {0}".format(model["b_mm"])
        assert abs(model["length_mm"] - 20.0) < 0.05, "length wrong: {0}".format(model["length_mm"])
        return "a={0:.3f} b={1:.3f} L={2:.2f} mm".format(
            model["a_mm"], model["b_mm"], model["length_mm"])
    finally:
        FreeCAD.closeDocument(doc.Name)


def _palace_cylcavity_geometry():
    """The Palace general-3-D (BREP) model-extraction path under the GUI (no solve).

    A cylinder is a NON-box solid, so build_cavity_model must route it to the
    BREP branch and export a BREP under the real GUI. The shift-invert target is
    seeded from the bounding box of a CURVED solid (tessellation-sensitive), so
    it is only checked LOOSELY — the exact modes come from the mesh (the gate),
    not the bbox seed. The BREP export itself writes exact OCC geometry.
    """
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.palace.model import build_cavity_model
    from emstudio.templates import cylcavity

    doc = FreeCAD.newDocument("gui_cylcav")
    try:
        ana = cylcavity.makeCylCavity(doc, radius_mm=30.0, height_mm=40.0)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverPalace"][0]
        model = build_cavity_model(ana, solver)
        assert model.get("kind") == "brep", "cylinder should route to the BREP path"
        assert os.path.isfile(model["brep_path"]), "no BREP exported under the GUI"
        assert 2.5 < model["target_ghz"] < 4.5, \
            "target seed out of band: {0}".format(model["target_ghz"])
        return "brep exported, target seed {0:.2f} GHz".format(model["target_ghz"])
    finally:
        FreeCAD.closeDocument(doc.Name)


def _palace_circwg_geometry():
    """The Palace general-BREP DRIVEN path under the GUI (no solve).

    A circular waveguide (Part::Cylinder + "Driven S-parameters") is a non-box
    solid, so build_waveguide_model must route it to the BREP driven branch and
    export a BREP with the two end faces as ports. The curved solid's bbox is
    tessellation-sensitive, so only the routing + axis are asserted; the exact
    S-params come from the gate.
    """
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.palace.model import build_waveguide_model
    from emstudio.templates import circwaveguide

    doc = FreeCAD.newDocument("gui_circwg")
    try:
        ana = circwaveguide.makeCircWaveguide(doc, radius_mm=30.0, length_mm=80.0)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverPalace"][0]
        model = build_waveguide_model(ana, solver)
        assert model.get("kind") == "brep", \
            "cylinder waveguide should route to the BREP driven path"
        assert os.path.isfile(model["brep_path"]), "no BREP exported under the GUI"
        assert model["axis"] == 2, \
            "guide axis should be z (the cylinder length), got {0}".format(model["axis"])
        assert len(model["bbox_mm"]) == 6, "bbox_mm must be (xmin..zmax)"
        return "brep driven exported, ports on the z end faces"
    finally:
        FreeCAD.closeDocument(doc.Name)


def _palace_amr_option():
    """The AMR opt-in threads from the SolverPalace object to the writer config.

    Under the real GUI: the cavity template's SolverPalace must carry the new
    MeshRefinement (default 0 = off) and RefinementTol (default 0.01) properties;
    setting MeshRefinement must round-trip and make the writer emit a Model-level
    Refinement block (Nonconformal true — mandatory for gmsh tets). No solve.
    """
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.palace import writer
    from emstudio.templates import cavity

    doc = FreeCAD.newDocument("gui_amr")
    try:
        ana = cavity.makeCavity(doc, size_mm=(40.0, 20.0, 60.0))
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverPalace"][0]
        assert int(solver.MeshRefinement) == 0, "AMR must default OFF (MeshRefinement=0)"
        assert abs(float(solver.RefinementTol) - 0.01) < 1e-9, "RefinementTol default 0.01"
        # off -> writer emits NO Refinement (byte-identical); on -> a Refinement block
        off = writer.build_eigenmode_config("cavity.msh", target_ghz=4.0,
                                            mesh_refinement=int(solver.MeshRefinement))
        assert "Refinement" not in off["Model"], "default GUI solver must not add Refinement"
        solver.MeshRefinement = 2
        doc.recompute()
        assert int(solver.MeshRefinement) == 2, "MeshRefinement did not round-trip"
        on = writer.build_eigenmode_config(
            "cavity.msh", target_ghz=4.0, mesh_refinement=int(solver.MeshRefinement),
            refinement_tol=float(solver.RefinementTol))
        ref = on["Model"].get("Refinement")
        assert ref and ref["MaxIts"] == 2 and ref["Nonconformal"] is True, \
            "GUI AMR did not thread into a Model.Refinement block"
        return "AMR opt-in round-trips (MeshRefinement 0->2, Nonconformal true)"
    finally:
        FreeCAD.closeDocument(doc.Name)


def _freq_guard_gui():
    """The quasi-static frequency guard fires on a real GUI magnetics analysis.

    Extract the WPT pair's axisymmetric model under the GUI (curved coil radii —
    the tessellation-sensitive path) and confirm the guard warns at mmWave and is
    silent at the design frequency. No solve.
    """
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import validity
    from emstudio.solvers.elmer.model import build_axi_model
    from emstudio.templates import wpt

    doc = FreeCAD.newDocument("gui_freqguard")
    try:
        ana = wpt.makeWptPair(doc, gap_mm=20.0)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverElmer"][0]
        model = build_axi_model(ana, solver)
        max_dim = validity.axi_model_max_dim_m(model)
        assert max_dim > 0, "no geometry extracted for the guard"
        assert validity.electrical_size_warning(40e9, max_dim), \
            "guard stayed silent on a 40 GHz magnetics analysis"
        assert validity.electrical_size_warning(100e3, max_dim) is None, \
            "guard warned at the 100 kHz design frequency (false alarm)"
        return "warns at 40 GHz, silent at 100 kHz (coil span {0:.0f} mm)".format(
            max_dim * 1e3)
    finally:
        FreeCAD.closeDocument(doc.Name)


def _synthetic_magnetics_result():
    """A REAL MagneticsResult with representative data, built without a solver.

    Deliberately not a mock: it is the shipped class, populated through its own
    constructor with the dict keys the runner actually produces, so
    ``summary_text()`` and ``coil_impedance()`` run for real. If those key names
    drift, this breaks — which is the point. A stub object with a
    ``summary_text`` attribute would construct the dialog and prove nothing.
    """
    from emstudio.post.magnetics import MagneticsResult

    cases = [{
        "tag": "sweep", "freq_hz": 100e3,
        "eddy_power_w": 12.5, "energy_j": 1.4e-4,
        "body_power_w": {"Plate": 12.5},
        # complex flux linkage -> exercises L_eff and R_reflected
        "coil_lambda": {"Coil1": complex(3.2e-5, -1.1e-6),
                        "Coil2": complex(2.9e-5, -0.9e-6)},
        "vtu": "", "rundir": "",
    }]
    coils = [{"name": "Coil1", "turns": 10, "current_a": 5.0},
             {"name": "Coil2", "turns": 10, "current_a": 5.0}]
    return MagneticsResult(cases, coils, ["Plate"], meta={})


def _synthetic_gap_curve():
    """The documented return shape of ``sweep_wpt_gap``: {gap_mm,k,L1_h,L2_h,M_h}."""
    return [
        {"gap_mm": 18.0, "k": 0.42, "L1_h": 6.4e-6, "L2_h": 6.4e-6, "M_h": 2.69e-6},
        {"gap_mm": 32.0, "k": 0.21, "L1_h": 6.4e-6, "L2_h": 6.4e-6, "M_h": 1.34e-6},
    ]


def _pattern_frequency_picker():
    """A multi-pattern result builds a working frequency picker.

    The picker only exists when a sweep produced more than one pattern, so no
    existing gui_smoke path exercised it. Built here from a synthetic result
    rather than a live sweep — the point is the WIDGET, and a real NEC2 sweep
    is already covered by tests/validation/pattern_sweep.py.
    """
    import numpy as np
    from PySide import QtGui as QtWidgets  # noqa: N813

    from emstudio.post.farfield import FarFieldResult
    from emstudio.post.sparams import SweepResult
    from emstudio.ui.results_dialog import SweepResultsDialog

    th = [0.0, 45.0, 90.0, 135.0, 180.0]
    ph = [float(p) for p in range(0, 360, 45)]
    freq = np.linspace(200e6, 400e6, 21)
    s11 = np.full(freq.shape, 0.2 + 0j)
    s11[10] = 0.01 + 0j                       # a best match to anchor on
    res = SweepResult(freq, s11, z0=50.0, meta={"backend": "nec2c"})
    ffs = [FarFieldResult(f, th, ph,
                          np.full((len(th), len(ph)), -3.0 + i * 0.1),
                          meta={"backend": "nec2c"})
           for i, f in enumerate(np.linspace(200e6, 400e6, 5))]
    res.farfields = ffs
    res.farfield = ffs[2]
    # per-frequency CURRENTS ride the same file, so the Currents tab scrubs
    # too (AJ, 2026-08-07 — the one tab that did not move with the slider);
    # distinct i_mag per entry so following can be told from staying put
    pos = np.column_stack([np.zeros(9), np.zeros(9), np.linspace(0, 0.5, 9)])
    cur_all = [{"seg": np.arange(1, 10), "tag": np.ones(9, int),
                "pos_m": pos, "i_complex": np.full(9, 0.1 + 0j),
                "i_mag": np.full(9, 0.1 + 0.01 * i), "freq": ff.freq}
               for i, ff in enumerate(ffs)]
    res.currents_all = cur_all
    res.currents = cur_all[2]

    dlg = SweepResultsDialog(res)
    combos = dlg.findChildren(QtWidgets.QComboBox)
    picks = [c for c in combos if c.count() == len(ffs)]
    assert picks, "no frequency picker built for a 5-pattern result"
    combo = picks[0]
    assert "MHz" in combo.itemText(0), combo.itemText(0)
    # it must OPEN on the pattern the rest of the dialog describes
    assert combo.currentIndex() == 2, combo.currentIndex()
    # 8 phi values -> the 3-D balloon tab exists too; plus the CURRENTS tab
    # registers as a third scrub view now that per-frequency currents exist.
    assert len(picks) == 3, ("expected pickers on both pattern tabs AND the "
                             "Currents tab, got {0}".format(len(picks)))

    # and switching must not raise (the plot is built lazily on demand)
    combo.setCurrentIndex(4)
    # THE COUPLING: every picker, and the far field that "Show in 3D View"
    # exports, must follow. _show_in_3d read result.farfield — pinned to the
    # best match — so the viewport balloon silently disagreed with the tab.
    assert dlg._selected_farfield() is ffs[4], "3-D export did not follow the picker"
    assert all(c.currentIndex() == 4 for c in picks), \
        "pickers out of sync: {0}".format([c.currentIndex() for c in picks])
    picks[1].setCurrentIndex(1)               # drive it from the OTHER tab
    assert dlg._selected_farfield() is ffs[1]
    assert combo.currentIndex() == 1, combo.currentIndex()

    # THE SCRUB SLIDERS (AJ, 2026-08-06): each pattern tab carries a
    # bottom slider spanning the solved band, synced with the combos both
    # ways through the shared selection.
    sliders = [s for s in dlg.findChildren(QtWidgets.QSlider)
               if s.maximum() == len(ffs) - 1]
    assert len(sliders) == 3, \
        "expected a scrub slider on both pattern tabs + Currents, got {0}".format(
            len(sliders))
    sliders[0].setValue(3)
    assert dlg._selected_farfield() is ffs[3]
    assert all(c.currentIndex() == 3 for c in picks), "combo did not follow"
    combo.setCurrentIndex(1)
    assert all(s.value() == 1 for s in sliders), "slider did not follow"

    # the CURRENTS selection follows the shared index by FREQUENCY
    assert dlg._selected_currents() is cur_all[1], \
        "the currents selection did not follow the scrub"
    # and a currents-driven change moves everything else
    dlg._select_frequency(0)
    assert dlg._selected_farfield() is ffs[0]
    assert dlg._selected_currents() is cur_all[0]

    # FREQUENCY CURSORS: the three sweep plots each registered one, and a
    # selection change fires them with the selected pattern's frequency.
    assert len(dlg._freq_cursors) == 3, \
        "expected cursors on S11/VSWR/Z, got {0}".format(
            len(dlg._freq_cursors))
    fired = []
    _orig_cursor = dlg._freq_cursors[0]
    dlg._freq_cursors[0] = lambda hz: (fired.append(hz), _orig_cursor(hz))[1]
    combo.setCurrentIndex(4)
    assert fired and abs(fired[-1] - ffs[4].freq) < 1.0, \
        "cursors did not fire with the selected frequency: {0}".format(fired)
    dlg._freq_cursors[0] = _orig_cursor
    # In-band the readout carries real values; OUTSIDE the sweep it says so
    # instead of clamping to the band edge (np.interp's silent default — a
    # confident wrong number under a wrong label, adversarial review
    # 2026-08-06). A pattern band may legitimately exceed the sweep.
    text_in = _orig_cursor(ffs[2].freq)
    assert text_in and "MHz" in text_in and "outside" not in text_in, text_in
    text_out = _orig_cursor(500e6)          # sweep tops out at 400 MHz
    assert text_out and "outside" in text_out, \
        "out-of-band cursor readout clamps instead of saying so: " \
        "{0!r}".format(text_out)

    # LIVE-FOLLOW (AJ, 2026-08-06): once a balloon exists in the 3-D view,
    # scrolling the picker must retarget it IN PLACE — same object, new
    # pattern and label — never grow a second overlay. Balloon rewrites are
    # THROTTLED (60 ms trailing edge), so the checks spin the event loop.
    # Built through the same vtk_out calls _show_in_3d uses (that method
    # ends in a modal box, which an offscreen run must not open).
    import os as _os
    import tempfile as _tempfile
    import time as _time

    import FreeCAD

    from emstudio.post import vtk_out
    from emstudio.ui.results_dialog import BalloonScrubber, show_sweep_results

    def spin_until(cond, timeout_ms=5000, what="condition"):
        """Pump events until cond() — NEVER a fixed sleep budget.

        A fixed 250 ms spin was flaky on 0.21.2 (~50% of runs): under
        manual processEvents(AllEvents, ms) Qt5's glib dispatcher can
        starve a fresh single-shot timer for a whole spin (adversarial
        review, 2026-08-06, reproduced and instrumented). Plain
        processEvents() delivers them; the deadline is generous and the
        loop exits the moment the condition holds.
        """
        from PySide import QtCore as _QtC
        t_end = _time.time() + timeout_ms / 1000.0
        while _time.time() < t_end:
            QtWidgets.QApplication.processEvents()
            # DEFERRED DELETES need asking for. Qt processes them only when
            # control returns to the event loop that posted them, so a
            # manual processEvents() pump never sees WA_DeleteOnClose
            # through — the dialog stays alive and a lifetime check waits
            # forever (measured on 0.21.2/Qt5, 2026-08-06). Production has a
            # real loop and needs none of this.
            QtWidgets.QApplication.sendPostedEvents(
                None, _QtC.QEvent.DeferredDelete)
            if cond():
                return
            _time.sleep(0.01)
        raise AssertionError("timed out waiting for " + what)

    def _alive(widget):
        try:
            widget.isVisible()
            return True
        except RuntimeError:
            return False

    doc = FreeCAD.newDocument("gui_balloon_follow")
    try:
        wd = _tempfile.mkdtemp(prefix="emstudio_smoke_balloon_")
        p = vtk_out.write_pattern_vtu(ffs[0],
                                      _os.path.join(wd, "pattern3d.vtu"),
                                      radius_mm=100.0,
                                      center_mm=(0.0, 0.0, 0.0))
        dlg._balloon = vtk_out.show_in_freecad(
            p, "Pattern balloon @ 0.200 GHz", doc, transparency=55)
        dlg._balloon_ctx = (p, (0.0, 0.0, 0.0), None)
        n_before = len(doc.Objects)
        n_figs = sum(s.count()
                     for s in dlg.findChildren(QtWidgets.QStackedWidget))
        combo.setCurrentIndex(3)              # 350 MHz
        spin_until(lambda: "0.350" in dlg._balloon.Label, what="balloon@350")
        assert len(doc.Objects) == n_before, \
            "scrolling grew a second overlay"
        # the trailing edge builds the newly-visited pattern figures too —
        # deferred with the balloon, but never skipped
        assert sum(s.count()
                   for s in dlg.findChildren(QtWidgets.QStackedWidget)) \
            > n_figs, "deferred figure build never landed"

        # THE VIEWPORT SCRUBBER: routes through the dialog while it lives
        # (combos + cursors + balloon all move — reachable now that the
        # dialog is NON-MODAL)...
        sc = BalloonScrubber.show_for(ffs, 3, dlg._balloon,
                                      dlg._balloon_ctx,
                                      on_change=dlg._select_frequency)
        sc.slider.setValue(2)
        spin_until(lambda: combo.currentIndex() == 2,
                   what="scrubber driving the dialog")
        spin_until(lambda: "0.300" in dlg._balloon.Label, what="balloon@300")
        # ...stays a SINGLETON (a second Show in 3-D replaces it)...
        sc2 = BalloonScrubber.show_for(ffs, 2, dlg._balloon,
                                       dlg._balloon_ctx)
        assert BalloonScrubber._instance is sc2 and sc2 is not sc
        assert not sc.isVisible(), "replaced scrubber left on screen"
        # ...and scrubs the balloon SOLO with no dialog hook at all.
        sc2.slider.setValue(1)
        spin_until(lambda: "0.250" in dlg._balloon.Label, what="balloon@250")
        # a balloon the user deleted must be dropped, not crashed into:
        # the dialog clears its reference, the scrubber closes itself.
        doc.removeObject(dlg._balloon.Name)
        sc2.slider.setValue(0)
        spin_until(lambda: BalloonScrubber._instance is None,
                   what="scrubber self-close on balloon deletion")
        # a DIFFERENT index than the dialog is on — a no-op set emits no
        # signal and would skip the very path under test
        combo.setCurrentIndex(4)
        spin_until(lambda: dlg._balloon is None,
                   what="dialog dropping the deleted balloon")

        # THE PRODUCTION WIRING (adversarial review, 2026-08-06: the old
        # modal callers made the dead-dialog path unreachable, so the suite
        # was green while the shipped behavior could not happen). A dialog
        # opened the way commands.py/run_gui.py now open it dies FOR REAL on
        # close; the scrubber detects that, goes solo, and still dies with
        # its balloon.
        res2 = SweepResult(freq, s11, z0=50.0, meta={"backend": "nec2c"})
        res2.farfields = ffs
        res2.farfield = ffs[0]
        dlg2 = show_sweep_results(res2)
        p2 = vtk_out.write_pattern_vtu(ffs[0],
                                       _os.path.join(wd, "pattern3d_2.vtu"),
                                       radius_mm=100.0,
                                       center_mm=(0.0, 0.0, 0.0))
        balloon2 = vtk_out.show_in_freecad(
            p2, "Pattern balloon @ 0.200 GHz", doc, transparency=55)
        ctx2 = (p2, (0.0, 0.0, 0.0), None)
        sc3 = BalloonScrubber.show_for(ffs, 0, balloon2, ctx2,
                                       on_change=dlg2._select_frequency)
        dlg2.close()
        spin_until(lambda: not _alive(dlg2),
                   what="WA_DeleteOnClose really deleting the dialog")
        sc3.slider.setValue(3)                # dead hook -> solo retarget
        spin_until(lambda: "0.350" in balloon2.Label,
                   what="solo scrub after dialog death")
        assert sc3.on_change is None, \
            "scrubber kept a hook to a deleted dialog"
        doc.removeObject(balloon2.Name)
        sc3.slider.setValue(1)
        spin_until(lambda: BalloonScrubber._instance is None,
                   what="post-death scrubber self-close")
        # and the shipped callers really use the non-modal path
        import inspect as _inspect

        from emstudio import commands as _cmds2
        from emstudio.ui import run_gui as _rg
        assert "show_sweep_results(" in _inspect.getsource(_rg), \
            "run_gui stopped using the non-modal results path"
        assert ".exec()" not in _inspect.getsource(
            _cmds2._open_results_for), \
            "_open_results_for went modal again"
    finally:
        FreeCAD.closeDocument(doc.Name)

    combo.setCurrentIndex(0)
    dlg.close()
    return "{0} frequencies, sliders + combos + cursors + 3-D export in " \
           "sync, balloon live-follows, scrubber drives it all and " \
           "survives the dialog".format(len(ffs))


def _scrubber_stays_on_the_viewport_screen():
    """The floating scrubber must land on the screen its 3-D view is on.

    ``_position_over_view`` ended in ``move(max(x, 0), max(y, 0))``. That is a
    safety net only on a single-monitor desktop: a Windows monitor placed LEFT
    of or ABOVE the primary has NEGATIVE global coordinates, so with FreeCAD's
    3-D view on such a screen the clamp threw the scrubber onto the PRIMARY
    monitor — a different screen from the viewport it drives. AJ reported it
    "missing" on 2026-08-13; it was on the other screen. Nothing contained it
    against the FAR edges either.

    The offscreen platform reports ONE screen at (0, 0), so the multi-monitor
    layout is INJECTED rather than waited for: the reference widget reports
    globals on a second monitor and answers ``screen()`` with it, which is
    what a real MDI subwindow on that monitor does. Nothing is monkeypatched,
    so the shipped screen lookup runs for real. Two levels, on purpose — the
    arithmetic exactly (``_clamp_into`` is pure), and then the scrubber's OWN
    realised position, because the defect was in what ``move()`` was handed
    and a check that only re-ran the arithmetic would not have seen it.

    Note ``_position_over_view`` swallows everything (positioning is cosmetic).
    That cannot make this pass by accident: a swallowed failure leaves the
    scrubber where it was, and it is parked on the primary screen first.
    """
    from PySide import QtCore
    from PySide import QtGui as QtWidgets  # noqa: N813

    from emstudio.ui import results_dialog as _rd
    from emstudio.ui.results_dialog import BalloonScrubber

    # The offscreen QPA reports frame margins a couple of pixels off the
    # requested move (measured: move(-1500,-200) -> pos (-1498,-198)). Real
    # window managers honour it exactly; allow the platform its slop, which is
    # three orders of magnitude smaller than the ~1900 px this is about.
    slop = 8

    # -- the arithmetic, exactly -------------------------------------------
    # A monitor above-left of the primary: the layout that broke.
    screen = QtCore.QRect(-1920, -360, 1920, 1080)
    assert _rd._clamp_into(screen, -3000, -2000, 320, 44) == (-1920, -360), \
        "off the top-left corner did not clamp to the SCREEN's corner: " \
        "{0}".format(_rd._clamp_into(screen, -3000, -2000, 320, 44))
    assert _rd._clamp_into(screen, 5000, 5000, 320, 44) == (-320, 676), \
        "off the bottom-right corner is not pulled back inside: " \
        "{0}".format(_rd._clamp_into(screen, 5000, 5000, 320, 44))
    assert _rd._clamp_into(screen, -500, 100, 320, 44) == (-500, 100), \
        "a position already inside the screen was moved"
    # wider/taller than the screen pins to its corner rather than shoving the
    # opposite edge out of reach
    assert _rd._clamp_into(screen, 0, 0, 4000, 2000) == (-1920, -360), \
        "a rect too big for the screen was pushed off it: {0}".format(
            _rd._clamp_into(screen, 0, 0, 4000, 2000))

    # -- the screen lookup itself ------------------------------------------
    import FreeCADGui

    mw = FreeCADGui.getMainWindow()
    real = _rd._screen_geometry_for(mw, QtCore.QPoint(0, 0))
    assert real.width() > 0 and real.height() > 0, \
        "no usable screen geometry for the main window: {0}".format(real)

    class _FakeScreen(object):
        def __init__(self, geo):
            self._geo = geo

        def availableGeometry(self):
            return self._geo

    class _OnOtherScreen(object):
        """A widget whose window sits on the injected second monitor."""

        def screen(self):
            return _FakeScreen(screen)

    class _NoScreen(object):
        """A widget binding without QWidget.screen() (pre-Qt 5.14)."""

    class _RaisingScreen(object):
        def screen(self):
            raise RuntimeError("binding without a usable screen()")

    # the WIDGET's screen wins — answering with the primary one regardless is
    # the whole bug, one layer down.
    assert _rd._screen_geometry_for(_OnOtherScreen(),
                                    QtCore.QPoint(0, 0)) == screen, \
        "the reference widget's own screen was ignored"
    # screenAt() returns None for a point on no screen — both fallback arms
    # must still produce a geometry instead of raising into the swallow.
    for stub in (_NoScreen(), _RaisingScreen()):
        fallback = _rd._screen_geometry_for(stub, QtCore.QPoint(-9999, -9999))
        assert fallback.width() > 0, \
            "screen fallback chain produced nothing for {0}".format(stub)

    # -- the realised position ---------------------------------------------
    class _FF(object):
        def __init__(self, freq):
            self.freq = freq

    class _Ref(_OnOtherScreen):
        """Stands in for the MDI subwindow, living on the injected screen."""

        def __init__(self, x, y, w, h):
            self._x, self._y, self._w, self._h = x, y, w, h

        def findChild(self, *_a, **_k):
            return None                   # no MDI area -> ref is this widget

        def mapToGlobal(self, pt):
            return QtCore.QPoint(self._x + pt.x(), self._y + pt.y())

        def width(self):
            return self._w

        def height(self):
            return self._h

    ffs = [_FF(f) for f in (200e6, 300e6, 400e6)]
    sc = BalloonScrubber.show_for(ffs, 1, None, None)
    try:
        for what, ref in (("a view on the negative-coordinate screen",
                           _Ref(-1900, -340, 1200, 300)),
                          ("a view at that screen's bottom-right",
                           _Ref(-500, 400, 1200, 900))):
            sc.move(10, 10)               # park it on the PRIMARY screen first
            QtWidgets.QApplication.processEvents()
            sc._position_over_view(ref)
            QtWidgets.QApplication.processEvents()
            got = sc.pos()
            assert got.x() < 0, \
                "{0}: scrubber clamped to x={1} — that is the PRIMARY monitor, " \
                "not the screen the viewport is on".format(what, got.x())
            placed = QtCore.QRect(got, sc.size())
            room = screen.adjusted(-slop, -slop, slop, slop)
            assert room.contains(placed), \
                "{0}: scrubber at {1} is not inside its own screen {2}".format(
                    what, placed, screen)
        # the first case must also prove the Y axis, which max(y, 0) broke
        # independently of X — otherwise half the clamp is unchecked.
        sc.move(10, 10)
        sc._position_over_view(_Ref(-1900, -340, 1200, 300))
        QtWidgets.QApplication.processEvents()
        assert sc.pos().y() < 0, \
            "scrubber clamped to y={0} — a view ABOVE the primary monitor " \
            "puts it back on the primary".format(sc.pos().y())
    finally:
        sc.close()
    return "clamped to its own screen at {0},{1}, not to (0, 0)".format(
        screen.x(), screen.y())


def _vswr_offscale_is_visible():
    """A VSWR curve above the linear view must still be DRAWN.

    _plot_vswr clamped the axes to 1..10 unconditionally. A real 300 mm helix
    swept 10-100 MHz has a minimum VSWR of 411, so all 51 points sat off the
    top and the tab rendered an empty grid — the data was present and correct
    the whole time. Asserting on the axes rather than on the source, because
    the bug was entirely in the view.
    """
    import numpy as np
    from PySide import QtGui as QtWidgets  # noqa: N813,F401

    from emstudio.post.sparams import SweepResult
    from emstudio.ui.results_dialog import VSWR_VIEW_TOP, SweepResultsDialog

    freq = np.linspace(10e6, 100e6, 51)

    def axes_of(result):
        # SweepResult's second positional is Zin, NOT S11 — these fixtures are
        # impedances, which is also how the real defect presented (R ~ 0.12 ohm
        # against a 50 ohm reference).
        dlg = SweepResultsDialog(result)
        return dlg._plot_vswr()._canvas.figure.axes[0], dlg

    # (a) the measured helix: R ~ 0.12 ohm across the band -> VSWR ~ 400
    bad = SweepResult(freq, np.full(freq.shape, 0.12 + 0j), z0=50.0,
                      meta={"backend": "nec2c"})
    v_min = float(bad.vswr().min())
    assert v_min > VSWR_VIEW_TOP, v_min
    ax, dlg = axes_of(bad)
    lo, hi = ax.get_ylim()
    assert hi >= v_min, "off-scale curve still clipped: ylim {0}..{1} vs min VSWR {2:.0f}".format(
        lo, hi, v_min)
    assert ax.get_yscale() == "log", ax.get_yscale()
    ydata = ax.get_lines()[0].get_ydata()
    assert len(ydata) == 51 and np.isfinite(ydata).all(), len(ydata)
    assert max(ydata) > VSWR_VIEW_TOP, "the real values were clipped away"
    dlg.close()

    # (b) a matched antenna keeps the familiar linear 1..10 view
    zin = np.full(freq.shape, 150.0 + 0j)     # VSWR 3
    zin[25] = 55.0 + 0j                       # VSWR 1.1 at the match
    good = SweepResult(freq, zin, z0=50.0, meta={"backend": "nec2c"})
    assert float(good.vswr().min()) < VSWR_VIEW_TOP
    ax, dlg = axes_of(good)
    assert ax.get_yscale() == "linear", ax.get_yscale()
    assert ax.get_ylim() == (1.0, VSWR_VIEW_TOP), ax.get_ylim()
    dlg.close()

    # (c) a ONE-POINT sweep must draw a visible marker, not an invisible line
    one = SweepResult(np.array([50e6]), np.array([75.0 + 0j]), z0=50.0,
                      meta={"backend": "nec2c"})
    ax, dlg = axes_of(one)
    assert ax.get_lines()[0].get_marker() not in ("", "None"), \
        "single-point sweep drawn with no marker — invisible"
    dlg.close()
    return "off-scale min {0:.0f} on a log axis; matched case unchanged".format(v_min)


def _pattern_frequencies_dialog():
    """The Pattern Frequencies dialog: recommends, edits, and stores exactly
    the band that reproduces the step it showed."""
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers.nec2 import pattern_band
    from emstudio.templates import dipole
    from emstudio.ui.pattern_freq_dialog import PatternFrequenciesDialog

    doc = FreeCAD.newDocument("gui_pattern_freqs")
    try:
        ana = dipole.makeDipole(doc, f0_hz=300e6)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverNEC2"][0]
        f1, f2, npts = 200e6, 400e6, int(ana.FrequencyPoints)
        ana.FrequencyStart = "200 MHz"
        ana.FrequencyStop = "400 MHz"
        doc.recompute()

        dlg = PatternFrequenciesDialog(ana, solver)
        # opens OFF (PatternFrequencies defaults to 0) and pre-filled with the
        # sweep band, so pressing OK unchanged cannot alter an existing run
        assert not dlg.enable.isChecked()
        assert dlg.use_sweep.isChecked()
        assert abs(dlg.start.value() - 200.0) < 1e-6, dlg.start.value()
        assert abs(dlg.stop.value() - 400.0) < 1e-6, dlg.stop.value()
        assert dlg.apply_to_solver() and solver.PatternFrequencies == 0

        # turn it on: the recommended step must land on sweep sample points
        dlg.enable.setChecked(True)
        sweep_step = pattern_band.sweep_step_hz(f1, f2, npts)
        rec = pattern_band.recommend(f1, f2, sweep_step)
        assert abs(dlg.step.value() - rec["step_hz"] / 1e6) < 1e-9, dlg.step.value()
        dlg.apply_to_solver()
        count = int(solver.PatternFrequencies)
        assert count == rec["count"], (count, rec["count"])
        # the whole sweep -> band stays 0/0 ("follow the sweep")
        assert pattern_band.to_hz(solver.PatternFreqStart) == 0.0
        assert pattern_band.to_hz(solver.PatternFreqStop) == 0.0

        # a hand-typed step that does NOT divide the band must still round-trip:
        # whatever is stored has to reproduce the step the dialog displayed.
        dlg.step.setValue(30.0)                       # 30 MHz over 200..400
        n, b1, b2 = dlg.resolved()
        assert n == 7 and abs(b2 - 380e6) < 1.0, (n, b2)
        dlg.apply_to_solver()
        stored = pattern_band.resolve_band(solver, f1, f2)
        got = pattern_band.step_hz(stored[0], stored[1],
                                   int(solver.PatternFrequencies))
        assert abs(got - 30e6) < 1.0, "stored band solves at {0:.4g} MHz, not 30".format(
            got / 1e6)

        # narrowing the band, then handing it back, must clear the override
        dlg.use_sweep.setChecked(False)
        dlg.start.setValue(280.0)
        dlg.stop.setValue(320.0)
        dlg._apply_recommended()
        # "Use recommended" must recommend against the band ON SCREEN. Asserting
        # only that a band got stored let a mutation through that recomputed
        # from the full sweep — it still stored a band, just the wrong step.
        narrow = pattern_band.recommend(280e6, 320e6, sweep_step)
        assert abs(dlg.step.value() - narrow["step_hz"] / 1e6) < 1e-9, \
            "recommended {0} MHz for 280-320, expected {1} MHz".format(
                dlg.step.value(), narrow["step_hz"] / 1e6)
        # and it must still be a whole number of SWEEP steps, not band steps
        assert narrow["on_sweep_points"], narrow
        ratio = narrow["step_hz"] / sweep_step
        assert abs(ratio - round(ratio)) < 1e-9, ratio
        dlg.apply_to_solver()
        assert pattern_band.to_hz(solver.PatternFreqStart) > 0.0
        dlg.use_sweep.setChecked(True)
        dlg._apply_recommended()
        dlg.apply_to_solver()
        assert pattern_band.to_hz(solver.PatternFreqStart) == 0.0, \
            "a narrowed band survived being handed back to the sweep"
        dlg.close()

        # PRE-RUN mode (the Run Solver pop-up, AJ 2026-08-06): on a FRESH
        # solver it must arrive with the recommendation LIVE — enable checked,
        # count = the recommended count — with OK reading "Run Solver" and
        # the mute checkbox present and seeded from the caller.
        solver.PatternFrequencies = 0
        solver.PatternFreqStart = 0.0
        solver.PatternFreqStop = 0.0
        pre = PatternFrequenciesDialog(ana, solver, prerun=True,
                                       ask_on_run=True)
        assert pre.enable.isChecked(), \
            "prerun on a fresh solver must arrive with the suggestion live"
        assert pre.ask_box.isChecked() and pre.ask_on_run()
        n_pre, _pf1, _pf2 = pre.resolved()
        assert n_pre == rec["count"], (n_pre, rec["count"])
        from PySide import QtWidgets as _QtW
        ok_btn = pre.findChild(_QtW.QDialogButtonBox).button(
            _QtW.QDialogButtonBox.Ok)
        assert ok_btn.text().replace("&", "") == "Run Solver", ok_btn.text()
        pre.ask_box.setChecked(False)
        assert not pre.ask_on_run()
        pre.close()
        # ...but a solver with an EXPLICIT prior choice keeps it: prerun must
        # respect count>0 instead of re-suggesting over it.
        solver.PatternFrequencies = 5
        pre2 = PatternFrequenciesDialog(ana, solver, prerun=True)
        assert pre2.enable.isChecked() and pre2.resolved()[0] == 5, \
            pre2.resolved()
        pre2.close()
        # and the Run Solver command actually calls the hook
        import inspect

        from emstudio import commands as _cmds
        src = inspect.getsource(_cmds._RunSolver.Activated)
        # Assert the CALL, not the name: a comment in Activated also says
        # "_pattern_freq_prerun", and matching that let a mutation delete
        # the real call and survive (caught 2026-08-06, first round).
        assert "if not self._pattern_freq_prerun(ana, solver):" in src, \
            "Run Solver no longer consults the pattern-band pop-up"

        # STALE-SOLVER HEALING (AJ's "I click OK and nothing happens",
        # 2026-08-06): an object missing the Pattern properties made
        # apply_to_solver raise AFTER the dialog closed and BEFORE any
        # confirmation. The heal must restore the properties, and both
        # entrances must actually call it.
        for p in ("PatternFrequencies", "PatternFreqStart",
                  "PatternFreqStop"):
            solver.removeProperty(p)
        assert "PatternFrequencies" not in solver.PropertiesList
        _cmds._heal_solver_properties(solver)
        for p in ("PatternFrequencies", "PatternFreqStart",
                  "PatternFreqStop"):
            assert p in solver.PropertiesList, "heal did not restore " + p
        healed = PatternFrequenciesDialog(ana, solver)
        healed.enable.setChecked(True)
        assert healed.apply_to_solver(), "apply failed on a healed solver"
        healed.close()
        assert "_heal_solver_properties(nec2_solvers[0])" in \
            inspect.getsource(_cmds._PatternFrequencies.Activated), \
            "menu entrance no longer heals stale solvers"
        assert "_heal_solver_properties(solver)" in \
            inspect.getsource(_cmds._RunSolver._pattern_freq_prerun), \
            "prerun entrance no longer heals stale solvers"

        return "recommends {0} patterns; hand-typed step round-trips; " \
               "prerun pop-up live; stale solver heals".format(rec["count"])
    finally:
        FreeCAD.closeDocument(doc.Name)


def _dialogs_construct():
    """Every results dialog must import + construct under the GUI (not exec).

    This is a UI check, and it used to require ElmerSolver on the box — it ran a
    full Elmer solve and a two-point gap sweep purely to obtain something to hand
    the dialogs. On any machine without Elmer it failed with "ElmerSolver not
    found", which says nothing about whether the dialogs construct, and it
    reported a missing optional dependency as a product defect. Whether Elmer
    solves is already covered by the dedicated Elmer solve-loop checks, and those
    fail honestly when it is absent.

    Elmer is still used when present, because a real result is better coverage
    than a synthesized one. The detail string says which path ran, so a green
    tick is never ambiguous about what was actually exercised.
    """
    import FreeCAD

    from emstudio.setup import solvers as solver_setup
    from emstudio.ui.magnetics_dialog import MagneticsResultsDialog
    from emstudio.ui.sweep_dialog import GapSweepDialog

    have_elmer = solver_setup.find_backend("elmer").found

    doc = FreeCAD.newDocument("gui_dialogs")
    try:
        if have_elmer:
            from emstudio.objects import query
            from emstudio.solvers import elmer
            from emstudio.solvers.elmer.model import build_axi_model
            from emstudio.solvers.elmer.sweep import sweep_wpt_gap
            from emstudio.templates import wpt

            ana = wpt.makeWptPair(doc, gap_mm=20.0)
            solver = [s for s in query.get_solvers(ana)
                      if query.em_type(s) == "EMStudio::SolverElmer"][0]
            result = elmer.run(ana, solver)
            curve = sweep_wpt_gap(build_axi_model(ana, solver), [18.0, 32.0],
                                  freq_hz=100e3)
            how = "solved"
        else:
            result = _synthetic_magnetics_result()
            curve = _synthetic_gap_curve()
            how = "synthesized (Elmer absent)"

        dlg = MagneticsResultsDialog(result)     # summary + buttons
        sweep_dlg = GapSweepDialog(curve)        # the k/M plot

        # Construction alone is a weak assertion — a dialog that silently
        # rendered nothing would pass. Require the summary to have real content
        # and the plot to have kept every point it was given.
        summary = result.summary_text()
        assert "magnetics results" in summary, \
            "summary_text produced no recognisable report: {0!r}".format(summary[:120])
        assert len(summary.splitlines()) > 4, \
            "summary_text is suspiciously short: {0!r}".format(summary)
        assert len(sweep_dlg.curve) == len(curve), \
            "GapSweepDialog dropped points: {0} of {1}".format(
                len(sweep_dlg.curve), len(curve))
        assert dlg is not None
        return "magnetics + gap-sweep dialogs OK ({0})".format(how)
    finally:
        FreeCAD.closeDocument(doc.Name)


def _small_antenna_dialog():
    """The small-antenna designer dialog constructs + computes under the GUI.

    No document needed — it's an analytic calculator. Constructing it runs a
    full _recalc (short-monopole/dipole/loop analytics + the band->method
    picker + all three matplotlib tabs), so this guards that the whole view
    wires up headlessly, the way the Litz designer is exercised elsewhere.
    """
    from emstudio.ui.small_antenna_dialog import SmallAntennaDialog

    dlg = SmallAntennaDialog()  # __init__ -> _recalc: analytics + picker + plots
    txt = dlg.perf_view.toPlainText()
    assert "radiation R" in txt, "small-antenna performance read-out empty"
    assert "Band" in dlg.banner.text(), "band->method banner empty"
    # a representative VLF-band case: a 24 kHz monopole must be electrically small
    dlg.freq_unit.setCurrentText("kHz")
    dlg.freq.setValue(24.0)
    dlg._recalc()
    assert dlg._res["radiation_resistance_ohm"] > 0, "no Rr computed"
    assert dlg._res["electrically_small"], "24 kHz mast should be electrically small"
    # --- top loading & ground tab (§4 breadth): flat-top + screen ----------
    dlg.tl_hat.setCurrentIndex(dlg.tl_hat.findData("flat"))
    dlg._recalc_topload()
    ttxt = dlg.tl_view.toPlainText()
    assert "hat capacitance" in ttxt and "efficiency" in ttxt \
        and "VOLTAGE-LIMITED" in ttxt, "top-loading read-out malformed"
    assert "ground system Rg" in ttxt, "ground estimator missing"
    # non-monopole types get the honest routing note
    dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("loop"))
    dlg._recalc_topload()
    assert "MONOPOLE" in dlg.tl_view.toPlainText(), \
        "non-monopole must get the routing note"
    dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("monopole"))
    return "computes; banner '{0}'".format(dlg.banner.text()[:32])


def _element_designer_dialog():
    """The Element Designer dialog (§1 slice E2) under the real GUI.

    Construction runs the default 300 MHz dipole synthesis (must equal the
    shipped template's 0.475*lambda inversion); the recommender is exercised
    on the Yagi scenario (ships-in-E3 honesty flag) and the folded page must
    show the gated 288-ohm step-up; the NEC2 verify READ-OUT formatter is
    gated on a synthetic resonance sweep with the R-window selection (the
    real solve is gated in tests/validation/element_designer.py's live tier
    and dipole_nec2.py); Accept -> Generate creates a runnable analysis via
    the dimension-override templates in a scratch document.
    """
    import FreeCAD

    import numpy as np

    from emstudio.ui.element_dialog import ElementDesignerDialog

    dlg = ElementDesignerDialog()  # __init__ -> default 300 MHz dipole recalc
    lam = 299792458.0 / 300e6
    assert abs(dlg.length.value() - 0.475 * lam) < 1e-6, \
        "default synthesis != the shipped-template 0.475*lambda"
    txt = dlg.perf_view.toPlainText()
    assert "PREDICTED" in txt and "dBd" in txt, "predicted read-out empty"
    assert "Band" in dlg.banner.text(), "band->method banner empty"

    # 3-D overlay: the button must be DEAD until a Verify has produced a far
    # field, and pressing it early must add nothing. A live button would offer
    # to show a pattern that does not exist.
    assert not dlg.show3d_btn.isEnabled(), \
        "the 3-D pattern button must start disabled (no verify has run)"
    _n0 = len(FreeCAD.ActiveDocument.Objects) if FreeCAD.ActiveDocument else 0
    dlg._show_in_3d()
    _n1 = len(FreeCAD.ActiveDocument.Objects) if FreeCAD.ActiveDocument else 0
    assert _n0 == _n1, "_show_in_3d with no verify result must add no object"

    # recommender: 12 dBd @ 432 MHz -> Yagi with the honest ships-in flag
    dlg.freq.setValue(432.0)
    dlg.gain_on.setChecked(True)
    dlg.gain.setValue(12.0)
    dlg._recommend()
    rec = dlg.rec_view.toPlainText()
    assert "Yagi" in rec, "Yagi must be recommended for a 12 dBd @ 432 MHz target"

    # folded dipole page: the gated 4x step-up (288 ohm)
    dlg.gain_on.setChecked(False)
    dlg.wtype.setCurrentIndex(dlg.wtype.findData("folded"))
    assert "288.0" in dlg.perf_view.toPlainText(), "folded 288-ohm missing"

    # verify read-out formatter on a synthetic sweep (R-window resonance
    # selection; the E1 anti-resonance lesson)
    dlg.wtype.setCurrentIndex(dlg.wtype.findData("dipole"))
    dlg.freq.setValue(300.0)
    from emstudio.post.sparams import SweepResult

    freq = np.linspace(200e6, 400e6, 201)
    zin = 72.0 + 1j * (freq - 296e6) / 1e6 * 2.0  # X=0 exactly at 296 MHz
    sr = SweepResult(freq, zin, z0=50.0,
                     meta={"duration_s": 1.0, "workdir": "x"})
    design = {"f0_hz": 300e6, "length_used_m": 0.474671,
              "feed_r_ohm": 72.0, "gain_dbi": 2.15}
    msg = dlg._verify_message(sr, design, "dipole")
    assert "296.0000 MHz" in msg and "-1.33%" in msg, \
        "verify formatter missed the 296 MHz resonance: " + msg
    assert "predicted R      : 72.0" in msg, "predicted-vs-achieved R missing"
    msg2 = dlg._verify_message(sr, design, "v58")
    assert "NOT resonant" in msg2, "5/8-wave must be reported non-resonant"

    # --- Yagi family (§1-E3): synthesis, predicted read-out, verify formatter
    dlg.family.setCurrentIndex(dlg.family.findData("yagi"))
    dlg.freq.setValue(144.0)
    dlg.yagi_by.setCurrentIndex(dlg.yagi_by.findData("gain"))
    dlg.yagi_gain.setValue(10.0)
    dlg._recalc()
    yd = dlg._yagi_design
    assert yd is not None and yd["boom_lambda"] == 1.2 and yd["n_directors"] == 4, \
        "Yagi 10 dBd @144MHz must be the 1.2-lambda / 4-director class"
    # a gain above the TN-688 table max (14.2 dBd) must null the design AND
    # disable Verify/Accept (no None-deref / leaked doc) — the E3 review fix
    dlg.yagi_gain.setValue(16.0)
    dlg._recalc()
    assert dlg._yagi_design is None, "out-of-range gain should null the design"
    assert not dlg.verify_btn.isEnabled() and not dlg.accept_btn.isEnabled(), \
        "Verify/Accept must be disabled when the Yagi synthesis fails"
    dlg.yagi_gain.setValue(10.0)
    dlg._recalc()
    assert dlg._yagi_design is not None and dlg.accept_btn.isEnabled(), \
        "a valid gain must restore the design and re-enable Accept"
    ytxt = dlg.perf_view.toPlainText()
    assert "Yagi-Uda" in ytxt and "10.20 dBd" in ytxt and "Director 4" in ytxt, \
        "Yagi predicted read-out malformed"
    # Yagi verify formatter on a synthetic far-field (peak + F/B + predicted)
    from emstudio.post.farfield import FarFieldResult

    th = np.arange(0.0, 181.0, 5.0)
    ph = np.arange(0.0, 360.0, 5.0)
    g = np.full((th.size, ph.size), -20.0)
    j90 = int(np.argmin(np.abs(th - 90.0)))
    g[j90, 0] = 12.35        # forward peak (phi=0) -> 12.35 dBi = 10.2 dBd
    g[j90, ph.size // 2] = -2.65  # back (phi=180) -> F/B 15.0 dB
    ff = FarFieldResult(144e6, th, ph, g)
    ysr = SweepResult(np.array([144e6]), np.array([25 + 30j]), z0=50.0,
                      meta={"duration_s": 2.0})
    ysr.farfield = ff
    ydesign = dict(yd)
    ydesign["f0_hz"] = 144e6
    ymsg = dlg._verify_message_yagi(ysr, ydesign)
    assert "achieved peak    : 12.35 dBi = 10.20 dBd" in ymsg \
        and "front/back       : 15.0 dB" in ymsg, \
        "Yagi verify formatter malformed: " + ymsg

    # Accept -> Generate: dipole (wire) and Yagi both build runnable analyses
    from emstudio.objects import query

    dlg.family.setCurrentIndex(dlg.family.findData("wire"))
    dlg.wtype.setCurrentIndex(dlg.wtype.findData("dipole"))
    dlg.freq.setValue(300.0)
    doc = FreeCAD.newDocument("gui_element_gen")
    try:
        ana = dlg._generate(doc)
        assert doc.getObject("DipoleWire") is not None, "no dipole generated"
        assert query.get_solvers(ana) and query.get_ports(ana), \
            "generated dipole analysis missing solver/port"
    finally:
        FreeCAD.closeDocument(doc.Name)
    dlg.family.setCurrentIndex(dlg.family.findData("yagi"))
    dlg.freq.setValue(144.0)
    dlg._recalc()
    doc = FreeCAD.newDocument("gui_yagi_gen")
    try:
        ana = dlg._generate(doc)
        wires = [o for o in doc.Objects if o.Name.startswith(("Reflector",
                 "Driven", "Director"))]
        assert len(wires) == 6, \
            "Yagi generate should build 6 wires, got {0}".format(len(wires))
        assert query.get_solvers(ana) and query.get_ports(ana), \
            "generated Yagi analysis missing solver/port"
    finally:
        FreeCAD.closeDocument(doc.Name)

    # --- Patch family (§1-E4): synthesis, predicted, openEMS verify formatter
    dlg.family.setCurrentIndex(dlg.family.findData("patch"))
    assert "openEMS" in dlg.verify_btn.text(), \
        "patch Verify button must name openEMS, not NEC2"
    dlg.freq.setValue(2.4)
    dlg.freq_unit.setCurrentText("GHz")
    dlg.patch_er.setValue(3.38)
    dlg.patch_h.setValue(1.524)
    dlg._recalc()
    pd = dlg._patch_design
    assert pd is not None and abs(pd["width_m"] * 1e3 - 42.2) < 0.4 \
        and abs(pd["length_m"] * 1e3 - 33.5) < 0.4, \
        "patch 2.4 GHz on er 3.38/1.524 must be ~42.2 x 33.5 mm"
    ptxt = dlg.perf_view.toPlainText()
    assert "Microstrip patch" in ptxt and "eff. permittivity" in ptxt, \
        "patch predicted read-out malformed"
    # patch verify formatter on a synthetic openEMS result (S11 dip + boresight)
    pfreq = np.linspace(1.44e9, 3.36e9, 401)
    ps11 = 0.85 - 0.80 * np.exp(-((pfreq - 2.35e9) / 3e7) ** 2)  # dip at 2.35 GHz
    psr = SweepResult(pfreq, np.full(pfreq.shape, 50.0 + 0j), z0=50.0,
                      s11=ps11, meta={"duration_s": 13.0, "workdir": "x"})
    pth = np.arange(0.0, 181.0, 5.0)
    pph = np.arange(0.0, 360.0, 5.0)
    pg = np.full((pth.size, pph.size), -15.0)
    pg[0, 0] = 6.88          # boresight (theta=0) peak
    psr.farfield = FarFieldResult(2.35e9, pth, pph, pg)
    pdesign = dict(pd)
    pdesign["f0_hz"] = 2.4e9
    pmsg = dlg._verify_message_patch(psr, pdesign)
    assert "achieved f_res   : 2.35" in pmsg \
        and "achieved gain    : 6.88 dBi" in pmsg \
        and "delta +0.55 dB" in pmsg, \
        "patch verify formatter malformed: " + pmsg
    doc = FreeCAD.newDocument("gui_patch_gen")
    try:
        ana = dlg._generate(doc)
        assert doc.getObject("Patch") is not None \
            and doc.getObject("Substrate") is not None, "patch geometry missing"
        assert query.get_solvers(ana) and query.get_ports(ana), \
            "generated patch analysis missing solver/port"
    finally:
        FreeCAD.closeDocument(doc.Name)

    # --- LPDA family (§1-E5): band inputs, synthesis, verify formatter,
    # crossed-TL generate
    dlg.family.setCurrentIndex(dlg.family.findData("lpda"))
    assert "NEC2" in dlg.verify_btn.text(), "LPDA Verify button must name NEC2"
    dlg.freq_unit.setCurrentText("MHz")
    dlg.freq.setValue(54.0)
    # no band top yet -> the design must null and the buttons disable
    dlg.band_top.setValue(0.0)
    dlg._recalc()
    assert dlg._lpda_design is None and not dlg.accept_btn.isEnabled(), \
        "LPDA without a band top must null the design and disable Accept"
    dlg.band_top_unit.setCurrentText("MHz")
    dlg.band_top.setValue(216.0)
    dlg.lpda_by.setCurrentIndex(dlg.lpda_by.findData("explicit"))
    dlg.lpda_tau.setValue(0.865)
    dlg.lpda_sigma.setValue(0.158)
    dlg._recalc()
    ld = dlg._lpda_design
    assert ld is not None and ld["n_elements"] == 15 \
        and abs(ld["n_exact"] - 14.445) < 0.01, \
        "54-216 MHz tau .865/sigma .158 must give the worked-example N"
    ltxt = dlg.perf_view.toPlainText()
    assert "LPDA" in ltxt and "feeder Z0" in ltxt and "Element 15" in ltxt, \
        "LPDA predicted read-out malformed"
    # verify formatter on a synthetic band sweep + mid-band far field
    lfreq = np.linspace(54e6, 216e6, 201)
    lzin = np.full(lfreq.shape, 65.0 + 0.0j)
    lsr = SweepResult(lfreq, lzin, z0=65.0, meta={"duration_s": 3.0})
    lth = np.arange(0.0, 181.0, 5.0)
    lph = np.arange(0.0, 360.0, 5.0)
    lg = np.full((lth.size, lph.size), -20.0)
    lj90 = int(np.argmin(np.abs(lth - 90.0)))
    lg[lj90, 0] = 8.30                    # forward (phi=0)
    lg[lj90, lph.size // 2] = -12.00      # back -> F/B 20.3 dB
    lsr.farfield = FarFieldResult(108e6, lth, lph, lg)
    ldesign = dict(ld)
    ldesign["f0_hz"] = 54e6
    lmsg = dlg._verify_message_lpda(lsr, ldesign)
    assert "median 1.00" in lmsg and "achieved peak    : 8.30 dBi" in lmsg \
        and "front/back       : 20.3 dB" in lmsg, \
        "LPDA verify formatter malformed: " + lmsg
    doc = FreeCAD.newDocument("gui_lpda_gen")
    try:
        ana = dlg._generate(doc)
        wires = [o for o in doc.Objects if o.Name.startswith("Element")]
        assert len(wires) == 15, \
            "LPDA generate should build 15 wires, got {0}".format(len(wires))
        tls = query.get_transmission_lines(ana)
        assert len(tls) == 14 and all(t.Crossed for t in tls), \
            "LPDA generate should chain 14 crossed transmission lines"
        assert query.get_solvers(ana) and query.get_ports(ana), \
            "generated LPDA analysis missing solver/port"
    finally:
        FreeCAD.closeDocument(doc.Name)

    # --- service presets (E6): auto-fill the requirements schema ----------
    j = dlg.preset.findData("ham_80m")
    assert j > 0, "ham_80m preset missing from the combo"
    dlg.preset.setCurrentIndex(j)  # -> _apply_preset via the signal
    assert dlg.freq_unit.currentText() == "MHz" \
        and abs(dlg.freq.value() - 3.5) < 1e-9 \
        and abs(dlg.band_top.value() - 4.0) < 1e-9, \
        "80 m preset must fill f_lo 3.5 / band top 4.0 MHz"
    assert dlg.polar.currentData() == "H", "80 m preset must set H pol"
    j = dlg.preset.findData("ham_2m")
    dlg.preset.setCurrentIndex(j)
    assert abs(dlg.freq.value() - 145.9863) < 0.001 \
        and dlg.band_top.value() == 0.0, \
        "2 m preset is a SPOT service (geometric centre, no band top)"
    assert "Region" in dlg.rec_view.toPlainText(), \
        "preset must surface its region note"
    dlg.preset.setCurrentIndex(0)
    dlg.family.setCurrentIndex(dlg.family.findData("lpda"))
    dlg.freq_unit.setCurrentText("MHz")
    dlg.freq.setValue(54.0)
    dlg.band_top_unit.setCurrentText("MHz")
    dlg.band_top.setValue(216.0)
    dlg._recalc()

    # --- PDF report path (E6): design enrichment + a real PDF, headless ----
    import os
    import tempfile

    fam, rdesign = dlg._current_report_design()
    assert fam == "lpda" and rdesign is not None \
        and rdesign.get("n_elements") == 15, \
        "_current_report_design must return the live LPDA design"
    from emstudio.report import element_report

    rp = os.path.join(tempfile.gettempdir(), "gui_element_report.pdf")
    element_report(rdesign, rp, family=fam, title="LPDA — Element Design")
    assert os.path.getsize(rp) > 5000, "element report PDF too small"
    os.remove(rp)
    dlg.family.setCurrentIndex(dlg.family.findData("wire"))
    fam_w, rd_w = dlg._current_report_design()
    assert fam_w == "wire" and rd_w is not None and "kind" in rd_w \
        and "length_m" in rd_w, "wire report design must carry kind+length"
    return ("wire + Yagi + patch + LPDA synth/verify/generate + report + "
            "recommender OK")


def _isolation_matrix():
    """The antenna-isolation-matrix NEC2 solve loop under the GUI (§5-A).

    Builds the co-site dipole pair and runs the multi-drive Y-matrix extraction —
    two lambda/2 dipoles at 0.5 lambda must show ~13.8 dB isolation with exact
    reciprocity, guarding the multi-port writer + numpy Z->S path under a real
    FreeCAD.
    """
    import FreeCAD

    import numpy as np

    from emstudio.cosite import isolation
    from emstudio.objects import query
    from emstudio.templates import cosite_pair

    doc = FreeCAD.newDocument("gui_isolation")
    try:
        ana = cosite_pair.makeCositePair(doc, f0_hz=300e6, spacing_frac=0.5)
        solver = query.get_solvers(ana)[0]
        res = isolation.isolation_matrix(ana, solver)
        s21_db = 20.0 * np.log10(abs(res["s"][1, 0]))
        assert -14.8 <= s21_db <= -12.8, "isolation |S21| off: {0:.2f} dB".format(s21_db)
        assert res["reciprocity_err"] < 1e-6, "reciprocity broken"
        return "|S21| {0:.2f} dB ({1} antennas)".format(s21_db, len(res["labels"]))
    finally:
        FreeCAD.closeDocument(doc.Name)


def _array_peak(currents, d_over_lambda):
    """(gamma_peak_deg, |F|max) — a gui_smoke-local peak finder so the dialog's
    scan convention is pinned independently of the engine's own helper."""
    import numpy as np

    from emstudio.system import array_system as A

    gam = np.linspace(0.0, 180.0, 180001)
    f = A.array_factor(currents, d_over_lambda, gam)
    i = int(np.argmax(f))
    return float(gam[i]), float(f[i])


def _array_designer_dialog():
    """The Array Designer dialog (§7 slice S4) under the real GUI.

    Construction derives the default broadside 4-element drive; the named
    distributions produce the right target currents (cardioid forces N=2 and
    quadrature; Hansen-Woodyard notes the enhanced end-fire); the predicted
    read-outs come from the gated engine (exact directivity, HPBW, the
    grating-lobe guard fires for a steered array at d = 1 lambda). No solver —
    the live drive chain is gated in tests/validation/array_nec2.py.
    """
    import math

    try:
        from emstudio.system import array_system as A  # noqa: F401
        from emstudio.ui import array_dialog as ad
    except ImportError:
        # EMStudioFree ships this gate but NOT §7 (Pro-side), so the check
        # stands down on its own. A denied module must never need code
        # surgery in the free repo to keep its tests green -- that
        # maintenance burden is what killed the first, larger tier split.
        return "skipped — the Array Designer is Pro-only and absent in this build"

    # pure helpers first (headless contract)
    c, beta, _note = ad.currents_for("broadside", 4, 0.5)
    assert beta == 0.0 and len(c) == 4 and all(abs(x - 1.0) < 1e-12 for x in c), \
        "broadside currents must be uniform in phase"
    c, beta, _note = ad.currents_for("cardioid", 2, 0.25)
    assert abs(c[0] - 1.0) < 1e-12 and abs(c[1] - complex(0, -1)) < 1e-12, \
        "cardioid pair must be quadrature [1, -1j]"
    c, beta, _note = ad.currents_for("hansen_woodyard", 10, 0.25)
    assert abs(beta + (math.pi / 2.0 + 0.294)) < 1e-12, \
        "HW beta must be -(kd + 2.94/N)"
    txt = ad.predicted_text("broadside", 4, 0.5, *ad.currents_for(
        "broadside", 4, 0.5)[:2])
    assert "directivity" in txt and "beamwidth" in txt, \
        "predicted read-out missing directivity/beamwidth"
    assert "grating-lobe-free" in txt, "broadside d=0.5 must be lobe-free"
    txt = ad.predicted_text("endfire", 4, 1.0, *ad.currents_for(
        "endfire", 4, 1.0)[:2])
    assert "GRATING LOBE" in txt, \
        "end-fire at d = 1 lambda must warn (limit 0.5)"
    assert "phase (deg)" in ad.targets_text([1.0, -1j]), "targets table header"

    # the dialog itself
    dlg = ad.ArrayDesignerDialog()
    assert dlg._currents is not None, "default drive not derived"
    assert "Broadside" in dlg.banner.text(), "banner missing the distribution"
    assert "directivity" in dlg.pred_view.toPlainText(), \
        "predicted pane not populated"

    # 3-D overlay: dead until Verify produces an ACHIEVED far field. The
    # predicted array factor is not a pattern — offering to draw it would show a
    # balloon the solver never computed.
    import FreeCAD

    assert not dlg.show3d_btn.isEnabled(), \
        "the 3-D pattern button must start disabled (no verify has run)"
    _n0 = len(FreeCAD.ActiveDocument.Objects) if FreeCAD.ActiveDocument else 0
    dlg._show_in_3d()
    _n1 = len(FreeCAD.ActiveDocument.Objects) if FreeCAD.ActiveDocument else 0
    assert _n0 == _n1, "_show_in_3d with no verify result must add no object"
    dlg.dist.setCurrentIndex(dlg.dist.findData("cardioid"))
    assert dlg.n_elems.value() == 2 and not dlg.n_elems.isEnabled(), \
        "cardioid must force and lock N = 2"
    tgt = dlg.targets_view.toPlainText()
    assert "-90.00" in tgt and "1.0000" in tgt, \
        "cardioid targets must be unit magnitude at 0 and -90 deg"
    # the quadrature pair is only a cardioid at lambda/4; the dialog's default
    # spacing is 0.5, and the banner must SAY so rather than promise a null
    assert "NOT a cardioid" in dlg.banner.text(), \
        "cardioid banner must flag that d != 0.25 lambda has no rear null"
    dlg.spacing.setValue(0.25)
    assert "EXACT null" in dlg.banner.text(), \
        "at d = 0.25 lambda the banner must state the exact rear null"
    # ...and the cardioid's grating limit is 0.75, not the broadside 1.0
    assert "0.75" in dlg.pred_view.toPlainText(), \
        "cardioid grating-lobe limit must be 0.75 lambda"
    dlg.spacing.setValue(0.8)
    assert "GRATING LOBE" in dlg.pred_view.toPlainText(), \
        "cardioid at 0.8 lambda must warn"
    dlg.spacing.setValue(0.5)

    dlg.dist.setCurrentIndex(dlg.dist.findData("scan"))
    assert dlg.scan.isEnabled() and dlg.n_elems.isEnabled(), \
        "scan mode must enable the angle and unlock N"
    # the dialog measures scan from BROADSIDE, the engine from the AXIS:
    # gamma0 = 90 - scan. A 90+scan transposition would live only here.
    dlg.n_elems.setValue(10)
    dlg.spacing.setValue(0.5)
    dlg.scan.setValue(30.0)
    c30, beta30, _n = ad.currents_for("scan", 10, 0.5, 30.0)
    gpk, _f = _array_peak(c30, 0.5)
    assert abs(gpk - 60.0) < 0.1, \
        "scan +30 deg from broadside must peak at gamma = 60 from the axis, " \
        "got {0:.2f}".format(gpk)
    c_neg, _b, _n2 = ad.currents_for("scan", 10, 0.5, -30.0)
    gneg, _f2 = _array_peak(c_neg, 0.5)
    assert abs(gneg - 120.0) < 0.1, \
        "scan -30 deg must peak at gamma = 120 (the BACK half), got " \
        "{0:.2f}".format(gneg)

    dlg.dist.setCurrentIndex(dlg.dist.findData("broadside"))
    dlg.n_elems.setValue(4)
    assert dlg.verify_btn.isEnabled(), "verify must be armed"

    # ---- S5 amplitude tapers ----
    c_u, _n1 = ad.apply_taper([1.0, 1.0, 1.0, 1.0], "uniform")
    assert list(c_u) == [1.0, 1.0, 1.0, 1.0], "uniform taper must be identity"
    c_b, note_b = ad.apply_taper([1.0] * 5, "binomial")
    assert abs(c_b[2] - 1.0) < 1e-12 and abs(c_b[0] - 1.0 / 6.0) < 1e-12, \
        "binomial 5-element amplitudes must be the 1:4:6 row (peak-normalized)"
    c_d, note_d = ad.apply_taper([1.0] * 10, "dolph", sll_db=26.0)
    assert "d_max" in note_d, "dolph note must carry the d_max limit"
    assert abs(max(abs(x) for x in c_d) - 1.0) < 1e-12 and abs(c_d[0]) < 0.5, \
        "dolph amplitudes must be peak-normalized and edge-tapered"
    try:
        ad.apply_taper([1.0] * 4, "bogus")
        raise AssertionError("unknown taper must raise")
    except ValueError:
        pass

    dlg.n_elems.setValue(10)
    dlg.taper.setCurrentIndex(dlg.taper.findData("dolph"))
    assert dlg.sll.isEnabled() and not dlg.nbar.isEnabled(), \
        "dolph enables SLL, not n-bar"
    pred = dlg.pred_view.toPlainText()
    assert "taper efficiency 0.893" in pred and "dynamic range 2.8:1" in pred, \
        "taper metrics line must carry the RIGHT numbers in the RIGHT order"
    # the SLL spin must actually reach apply_taper (a hardcoded 26.0 passes a
    # bare 'taper efficiency' substring check)
    dlg.sll.setValue(40.0)
    assert "0.1253" in dlg.targets_view.toPlainText(), \
        "SLL spin not wired: 40 dB Dolph edge current must be 1/7.9837"
    dlg.sll.setValue(26.0)
    assert "0.3611" in dlg.targets_view.toPlainText(), \
        "SLL spin not wired back: 26 dB edge current is 1/2.7745"
    tgt = dlg.targets_view.toPlainText()
    assert "1.0000" in tgt and "0.36" in tgt, \
        "dolph targets must show the edge-tapered amplitudes (edge 1/2.7745)"
    dlg.spacing.setValue(0.9)
    assert "exceeds d_max" in dlg.pred_view.toPlainText(), \
        "dolph beyond d_max must warn (design floor violated at the edge)"
    dlg.spacing.setValue(0.5)
    dlg.taper.setCurrentIndex(dlg.taper.findData("taylor"))
    assert dlg.sll.isEnabled() and dlg.nbar.isEnabled(), \
        "taylor enables SLL and n-bar"
    assert "n/a" not in dlg.pred_view.toPlainText().split("first sidelobe")[0], \
        "taylor prediction must populate"
    assert "taper efficiency" in dlg.pred_view.toPlainText(), \
        "the metrics line must appear for EVERY taper, not just Dolph"
    # the n-bar spin must reach apply_taper too
    t_before = dlg.targets_view.toPlainText()
    dlg.nbar.setValue(2)
    assert dlg.targets_view.toPlainText() != t_before, \
        "n-bar spin not wired: changing it must change the currents"
    dlg.nbar.setValue(4)
    # a taper on a tiny aperture must DEGRADE the metrics line, not abort the
    # slot and strand the pane on the previous array's numbers
    dlg.taper.setCurrentIndex(dlg.taper.findData("binomial"))
    dlg.n_elems.setValue(4)
    dlg.spacing.setValue(0.05)
    pred_small = dlg.pred_view.toPlainText()
    assert "N = 4, d = 0.05" in pred_small, \
        "the predicted pane must still describe the CURRENT array"
    assert "n/a" in pred_small or "unavailable" in pred_small, \
        "an unavailable metric must be reported, not raised"
    dlg.spacing.setValue(0.5)
    dlg.n_elems.setValue(10)
    dlg.taper.setCurrentIndex(dlg.taper.findData("taylor"))
    dlg.taper.setCurrentIndex(dlg.taper.findData("uniform"))
    dlg.dist.setCurrentIndex(dlg.dist.findData("cardioid"))
    assert not dlg.taper.isEnabled(), \
        "cardioid must lock the taper (its amplitudes ARE the distribution)"
    dlg.dist.setCurrentIndex(dlg.dist.findData("broadside"))
    assert dlg.taper.isEnabled(), "leaving cardioid must unlock the taper"
    dlg.n_elems.setValue(4)
    assert not dlg.export_btn.isEnabled(), \
        "pattern export must stay disabled until a Verify succeeds"

    # a Verify result must be INVALIDATED by any design edit — exporting a
    # stale far field would feed the §6 coverage tools the wrong array
    from emstudio.post.farfield import FarFieldResult
    import numpy as _np
    _th = list(range(0, 181, 5))
    _ph = list(range(0, 360, 5))
    dlg._result = {"farfield": FarFieldResult(
        300e6, _th, _ph, _np.zeros((len(_th), len(_ph))))}
    dlg.export_btn.setEnabled(True)
    dlg.spacing.setValue(0.6)
    assert dlg._result is None and not dlg.export_btn.isEnabled(), \
        "changing the design must clear the stale Verify result and disarm export"

    # a freshly-constructed dialog greys the taper-only spins
    fresh = ad.ArrayDesignerDialog()
    assert not fresh.sll.isEnabled() and not fresh.nbar.isEnabled(), \
        "SLL/n-bar must start greyed while the taper is Uniform"

    # a very short array has no 3 dB crossing — the panel must degrade one
    # line, not blank out
    dlg.n_elems.setValue(2)
    dlg.spacing.setValue(0.05)
    pred = dlg.pred_view.toPlainText()
    assert "directivity" in pred and "n/a" in pred, \
        "an unavailable HPBW must not blank the whole predicted pane"
    dlg.spacing.setValue(0.5)
    dlg.n_elems.setValue(4)

    # the Verify scratch model: built headlessly here (no solver), and it must
    # honour the dialog's wire radius + be writable by the multi-EX writer
    import FreeCAD
    from emstudio.objects import query as _query
    from emstudio.solvers.nec2 import writer as _writer
    doc = FreeCAD.newDocument("gui_smoke_array")
    try:
        ana = ad._build_array_analysis(doc, 300e6, 4, 0.5,
                                       half_len_frac=0.2389,
                                       wire_radius_mm=0.5)
        mats = _query.get_materials(ana)
        assert abs(float(mats[0].WireRadius.getValueAs("mm")) - 0.5) < 1e-9, \
            "the dialog's wire radius must reach the scratch model"
        pts = _query.get_ports(ana)
        assert len(pts) == 4 and all(p.Excited for p in pts), \
            "every array element needs its own excited port"
        wires, feeds, _sweep = _writer.build_wire_model_multi(
            ana, _query.get_solvers(ana)[0])
        assert len(wires) == 4 and len(feeds) == 4, \
            "the multi-EX writer must see 4 wires and 4 feeds"
    finally:
        FreeCAD.closeDocument(doc.Name)


def _cable_designer_dialog():
    """The Cable Designer dialog computes all five constructions under the GUI.

    No document needed. Constructing it runs the default litz recalc; switching
    the top-level Construction selector to Coax applies the RG-58 primary-
    datasheet preset (must reproduce the gated 50-ohm / 101 pF/m numbers) and
    marshals the Palace full-wave-verify kwargs; Single wire must hit the
    handbook AWG-10 Rdc and the exact-Kelvin Rac identity (ops=[] reuse);
    Twisted pair must hit the Cat6 ~100-ohm anchor (NVP mode) and the
    degrees-correct Lefferson control (89.03, NOT the public radians-bug
    94.90). The Palace solve itself is gated in tests/validation/
    coax_palace.py — here we guard the whole view + parameter wiring headlessly.
    """
    from emstudio.ui.cable_dialog import CableDesignerDialog
    from emstudio.wire import coax as cx
    from emstudio.wire import litz

    dlg = CableDesignerDialog()  # __init__ -> litz recalc: analytics + 3 tabs
    assert "Rdc" in dlg.summary.text(), "litz summary empty"
    assert dlg.sharing_btn.isEnabled(), "current sharing should be on for litz"
    # coax page: RG-58 preset -> the gated numbers
    dlg.construction.setCurrentIndex(1)
    assert not dlg.export_cad_btn.isEnabled(), "CAD export must be off for coax"
    rg58 = [n for n in cx.PRESETS if n.startswith("RG-58")][0]
    dlg.coax_preset.setCurrentText(rg58)  # triggers apply + recalc
    assert abs(dlg._coax["z0_ohm"] - 50.0) < 0.15, "RG-58 Z0 off in the dialog"
    assert abs(dlg._coax["capacitance_pf_m"] - 101.0) < 2.0, "RG-58 C' off"
    assert "Z0" in dlg.spec_view.toPlainText(), "coax spec tab empty"
    p = dlg._fullwave_params()
    assert abs(p["a_mm"] - 0.418) < 1e-6 and abs(p["b_mm"] - 1.4605) < 1e-6, \
        "full-wave verify kwargs don't match the preset geometry"
    # solve-for-Z0 helper (v0.41): exact inversion lands on the datasheet b
    dlg.coax_z0_target.setValue(50.0)
    dlg._solve_coax_b()
    assert abs(dlg.coax_b.value() - 2.9204) < 0.005, \
        "coax solve-2b off: {0:.4f} mm".format(dlg.coax_b.value())
    assert abs(dlg._coax["z0_ohm"] - 50.0) < 0.01, "solved coax Z0 not 50"
    dlg.coax_preset.setCurrentText(rg58)  # restore the preset for later asserts
    assert p["f2_ghz"] >= p["f1_ghz"] and p["step_ghz"] > 0 \
        and abs(p["eps_r"] - 2.25) < 1e-9, "full-wave sweep params malformed"
    # the verify read-out formatter on a synthetic matched-line SweepResult
    # (the real Palace solve is gated in tests/validation/coax_palace.py)
    import numpy as np

    from emstudio.post.sparams import SweepResult

    beta_l = 2.0 * np.pi * 1e9 * np.sqrt(2.25) / 299792458.0 * 0.020
    sr = SweepResult([1e9], [50.0], z0=50.0, s11=[1e-3 + 0j],
                     meta={"duration_s": 1.0, "workdir": "x"})
    sr.s_others = {(2, 1): np.array([np.exp(-1j * beta_l)])}
    txt = dlg._fullwave_message(sr, p)
    assert "full-wave VF = 0.6667" in txt and "worst |S11| = -60.0 dB" in txt, \
        "full-wave verify read-out malformed: " + txt
    # single-wire page: AWG-10 handbook Rdc + exact-Kelvin Rac (ops=[] reuse)
    dlg.construction.setCurrentIndex(2)
    dlg.wire_size.setValue(10.0)  # AWG
    dlg._recalc()
    assert not dlg.sharing_btn.isEnabled(), "current sharing must be off for wire"
    assert abs(dlg._con.rdc_per_meter() * 1e3 - 3.277) < 0.02, "AWG-10 Rdc off"
    assert abs(dlg._con.ac_factor(1e6)
               - litz.round_wire_ac_factor(1e6, dlg._con.strand_radius_m)) < 1e-12, \
        "single-wire Rac/Rdc must equal the exact Kelvin solution"
    # twisted-pair page (§2-B): Cat6 preset -> the gated ~100-ohm anchor, then
    # the degrees-control geometry in Lefferson mode (must NOT be 94.90)
    from emstudio.wire import twisted_pair as tpw

    dlg.construction.setCurrentIndex(3)
    cat6 = [n for n in tpw.PRESETS if n.startswith("Cat6")][0]
    dlg.tp_preset.setCurrentText(cat6)  # triggers apply + recalc
    assert abs(dlg._tp["z0_diff_ohm"] - 99.90) < 0.6, \
        "Cat6 Z0 off in the dialog: {0:.2f}".format(dlg._tp["z0_diff_ohm"])
    assert dlg._tp["eps_eff_source"] == "nvp", "Cat6 preset must use NVP"
    assert "Z0" in dlg.spec_view.toPlainText(), "twisted-pair spec tab empty"
    dlg.tp_preset.setCurrentIndex(0)  # custom
    dlg.tp_d.setValue(0.5)
    dlg.tp_s.setValue(0.8)
    dlg.tp_eps.setValue(4.0)
    dlg.tp_ins.setCurrentIndex(0)     # film
    dlg.tp_lay.setValue(10.0)         # 100 twists/m
    dlg.tp_nvp_on.setChecked(False)   # Lefferson mode
    dlg._recalc()
    assert abs(dlg._tp["z0_diff_ohm"] - 89.03) < 0.05 \
        and abs(dlg._tp["z0_diff_ohm"] - 94.90) > 1.0, \
        "dialog twisted pair not degrees-correct: {0:.2f}".format(
            dlg._tp["z0_diff_ohm"])
    # solve-lay-for-Z0 helper (v0.41): 80 ohm is inside this geometry's window
    dlg.tp_z0_target.setValue(80.0)
    dlg._solve_tp_lay()
    assert abs(dlg._tp["z0_diff_ohm"] - 80.0) < 0.05, \
        "solved TP Z0 off: {0:.2f}".format(dlg._tp["z0_diff_ohm"])
    assert not dlg.tp_nvp_on.isChecked(), "solve must leave Lefferson mode on"
    # bundle page (§2-C): 7 equal members must pack to the exact 3x hex OD,
    # and the last computed construction (the twisted pair above) is grabbable
    dlg.construction.setCurrentIndex(4)
    dlg.bundle_table.setRowCount(0)
    dlg._bundle_add_row("m", 2.5, 7, "wire")
    dlg.bundle_jacket.setCurrentText("PVC")
    dlg.bundle_wall.setValue(1.0)
    dlg._recalc()
    assert abs(dlg._bundle.core_od_m() - 7.5e-3) < 1e-8, \
        "7-hex bundle OD off: {0:.4f} mm".format(dlg._bundle.core_od_m() * 1e3)
    assert abs(dlg._bundle.od_m() - 9.5e-3) < 1e-8, "jacketed OD off"
    assert "Fill factor" in dlg.spec_view.toPlainText(), "bundle spec empty"
    dlg._bundle_grab_last()  # adds the twisted pair (envelope 2s = 1.6 mm)
    got = dlg.bundle_table.cellWidget(dlg.bundle_table.rowCount() - 1, 1).value()
    assert abs(got - 1.6) < 1e-6, "grabbed envelope OD wrong: {0}".format(got)
    # crosstalk estimate (§2-C cont.): the analytic weak-coupling path on
    # three touching wire members (s/rw = 5 -> wide-separation valid); the
    # FastHenry option is gated separately in tests/validation/wire_fasthenry.py
    dlg.bundle_table.setRowCount(0)
    dlg._bundle_add_row("w", 2.5, 3, "wire", 1.0)
    dlg._recalc()
    dlg.xt_gen.setValue(1)
    dlg.xt_rec.setValue(2)
    dlg.xt_ref.setValue(3)
    dlg.xt_fh.setChecked(False)
    # these members are insulated (envelope 2.5 mm > conductor 1.0 mm), so the
    # capacitance takes the MoM insulated route (Paul's method); the L route is
    # still the analytic wide-separation form
    dlg.xt_eps.setValue(3.5)
    dlg._bundle_coupling()
    assert dlg._xtalk["source"].startswith("analytic"), "wrong coupling route"
    assert dlg._xtalk["widesep_ok"], "s/rw=5 triple should be widesep-valid"
    assert dlg._xtalk["lm_h_m"] > 0 and dlg._xtalk["cm_f_m"] > 0, \
        "coupling matrices empty"
    assert "MoM insulated" in dlg._xtalk["c_source"], \
        "insulated members should use the MoM C solve, got {0}".format(
            dlg._xtalk["c_source"])
    assert -120 < dlg._xtalk["vne_db"] < 0, \
        "crosstalk out of range: {0:.1f} dB".format(dlg._xtalk["vne_db"])
    assert "Crosstalk" in dlg.summary.text(), "crosstalk summary missing"
    # bare members (envelope == conductor Ø) take the bare-identity route
    # (the "insulation raises C" magnitude is gated in tests/validation/cable.py)
    dlg.bundle_table.setRowCount(0)
    dlg._bundle_add_row("bare", 2.5, 3, "wire", 2.5)
    dlg._recalc()
    for w, v in ((dlg.xt_gen, 1), (dlg.xt_rec, 2), (dlg.xt_ref, 3)):
        w.setValue(v)
    dlg._bundle_coupling()
    assert dlg._xtalk["c_source"] == "bare identity", \
        "bare members should use the bare identity, got {0}".format(
            dlg._xtalk["c_source"])
    # diff-pair mixed-mode route (v0.49): five insulated members -> the MoM C
    # feeds the congruence reduction; balanced twist improvement is EXACTLY
    # 20 log10(N) (both couplings scale 1/N) — magnitude gated in cable.py
    import math as _m

    dlg.bundle_table.setRowCount(0)
    for i in range(5):
        dlg._bundle_add_row("w{0}".format(i + 1), 1.2, 1, "wire", 0.644)
    dlg._recalc()
    dlg.xt_diff.setChecked(True)
    assert dlg.xt_a1.isEnabled() and not dlg.xt_gen.isEnabled(), \
        "diff toggle must swap the member pickers"
    for w, v in ((dlg.xt_ref, 1), (dlg.xt_a1, 2), (dlg.xt_a2, 3),
                 (dlg.xt_b1, 4), (dlg.xt_b2, 5)):
        w.setValue(v)
    dlg.xt_twist.setValue(21)
    dlg._bundle_coupling()
    xd = dlg._xtalk_diff
    assert xd["c_source"].startswith("MoM insulated"), \
        "insulated members must route the diff C through the MoM solve"
    assert abs(xd["improvement_ne_db"] - 20.0 * _m.log10(21.0)) < 1e-9, \
        "balanced twist improvement must be exactly 20*log10(N)"
    assert abs(xd["k_diff"]) <= 1.0 and xd["cupp_f_m"] != 0.0, \
        "diff-pair k/CUPP read-out insane"
    assert "Diff pair-to-pair" in dlg.summary.text(), \
        "diff-pair summary missing"
    assert "−-" not in dlg.summary.text() and "--" not in dlg.summary.text(), \
        "double-negative rendering in the diff summary (signed-format bug)"
    dlg.xt_diff.setChecked(False)
    # --- the convection button, on a MIXED bundle ------------------------
    # ⚠ This button has been broken twice in ways every headless test passed:
    # once because `convection_dialog` was missing from the free manifest
    # behind a LAZY import, and once because it REFUSED the shipped default
    # mix outright. Both are only visible by pressing it. Nothing is solved —
    # build_dialog is intercepted, so what is asserted is that the handler
    # reaches it with the right geometry instead of bailing to a message box.
    from PySide import QtGui as QtWidgets  # noqa: N813

    from emstudio.ui import convection_dialog as _cvd

    _built, _refused = {}, []
    _real_build, _real_info = _cvd.build_dialog, QtWidgets.QMessageBox.information

    class _FakeConvDialog(QtWidgets.QDialog):
        def exec(self):
            return 0
        exec_ = exec

    def _fake_build(geometry, d_cable, box_w, box_h, parent=None):
        _built["cables"] = _cvd.as_cables(geometry, d_cable)
        _built["box"] = (box_w, box_h)
        _built["plan"] = _cvd.describe_plan(geometry, d_cable, box_w, box_h)
        return _FakeConvDialog()

    _cvd.build_dialog = _fake_build
    QtWidgets.QMessageBox.information = staticmethod(
        lambda *a, **k: _refused.append(a[2] if len(a) > 2 else ""))
    try:
        dlg.bundle_table.setRowCount(0)
        dlg._bundle_add_row("fat", 20.0, 1, "wire", 16.0)
        dlg._bundle_add_row("thin", 10.0, 2, "wire", 8.0)
        dlg._recalc()
        dlg.conv_clearance.setValue(5.0)
        dlg._bundle_convection()
        assert not _refused, \
            "the convection button REFUSED a mixed bundle: {0!r}".format(
                _refused[:1])
        assert "cables" in _built, "the convection dialog was never built"
        _ds = sorted(round(1000.0 * c[2], 4) for c in _built["cables"])
        assert _ds == [10.0, 10.0, 20.0], \
            "the solve got the wrong geometry: {0}".format(_ds)
        assert "2 sizes" in _built["plan"] and "20.0 mm" in _built["plan"], (
            "the plan must name every size, not one diameter the bundle does "
            "not have: {0!r}".format(_built["plan"]))
        # the box must clear the FATTEST cable wherever it sits — sizing on
        # one diameter can build an enclosure an inner cable does not fit
        _reach = max(_m.hypot(c[0], c[1]) + c[2] / 2.0 for c in _built["cables"])
        assert _built["box"][0] > 2.0 * _reach, \
            "the enclosure does not contain the bundle it was sized from"
        # and a UNIFORM bundle must still reach the same door
        _built.clear()
        dlg.bundle_table.setRowCount(0)
        dlg._bundle_add_row("same", 20.0, 3, "wire", 16.0)
        dlg._recalc()
        dlg._bundle_convection()
        assert not _refused and "cables" in _built, \
            "the uniform path regressed while adding mixed support"
        assert len({round(c[2], 9) for c in _built["cables"]}) == 1
        assert all(len(c) == 3 for c in _built["cables"]), \
            "an unloaded bundle must NOT acquire per-cable gradients"

        # --- the per-member CURRENT column ------------------------------
        # ⚠ The column is only real if pressing the button turns it into
        # per-cable flux. Two SAME-SIZE members on different currents is the
        # case that was unreachable from the UI before it existed.
        _built.clear()
        dlg.bundle_table.setRowCount(0)
        dlg._bundle_add_row("feeder A", 20.0, 1, "wire", 10.0, 120.0)
        dlg._bundle_add_row("feeder B", 20.0, 1, "wire", 10.0, 40.0)
        dlg._recalc()
        assert dlg.bundle_table.columnCount() == 6, \
            "the bundle table lost its Current column"
        assert abs(dlg._bundle.members[0].current_a - 120.0) < 1e-9, \
            "the Current cell did not reach the BundleMember"
        dlg._bundle_convection()
        assert not _refused, "the loaded bundle was refused: {0!r}".format(
            _refused[:1])
        _cab = _built["cables"]
        assert all(len(c) == 4 for c in _cab), \
            "a fully-loaded bundle must carry a PER-CABLE gradient: " \
            "{0}".format(_cab)
        _gs = sorted((c[3] for c in _cab), reverse=True)
        assert abs(_gs[0] / _gs[1] - 9.0) < 1e-6, \
            "same size, 120 A vs 40 A must give a flux ratio of I² = 9, " \
            "got {0:.4f}".format(_gs[0] / _gs[1])
        assert "2 sizes" not in _built["plan"], \
            "these are one SIZE on two loads, not two sizes"

        # a HALF-filled column must not silently default the blanks
        _built.clear()
        dlg.bundle_table.setRowCount(0)
        dlg._bundle_add_row("loaded", 20.0, 1, "wire", 10.0, 120.0)
        dlg._bundle_add_row("blank", 20.0, 1, "wire", 10.0, 0.0)
        dlg._recalc()
        dlg._bundle_convection()
        assert not _refused and "cables" in _built, \
            "a partly-filled current column must fall back, not refuse"
        assert all(len(c) == 3 for c in _built["cables"]), \
            "a partly-filled current column must NOT produce per-cable " \
            "gradients — that would put an invented load beside a real one"
    finally:
        _cvd.build_dialog = _real_build
        QtWidgets.QMessageBox.information = _real_info
    # thermal tab (v0.50): wire-page steady/ampacity/transient + the coax
    # RF power curve, headlessly (engine numbers gated in
    # tests/validation/thermal.py — here we guard the tab wiring)
    dlg.construction.setCurrentIndex(2)   # Single Wire (AWG-10 default)
    dlg.th_current.setValue(15.0)
    dlg.th_amb.setValue(30.0)
    dlg._run_thermal()
    tw_rep = dlg._thermal
    assert tw_rep["kind"] == "wire" and not tw_rep.get("runaway"), \
        "wire thermal did not produce a steady solution"
    assert 31.0 < tw_rep["t_conductor_c"] < 60.0, \
        "AWG-10 @15 A conductor T insane: {0:.1f} C".format(
            tw_rep["t_conductor_c"])
    assert 40.0 < tw_rep["ampacity_a"] < 80.0, \
        "AWG-10 105C free-air ampacity insane: {0:.1f} A".format(
            tw_rep["ampacity_a"])
    assert tw_rep["tau_s"] > 1.0 and tw_rep["i_adiabatic_1s_a"] > 100.0, \
        "transient/adiabatic read-outs insane"
    assert "Ampacity" in dlg.th_result.text(), "thermal read-out missing"
    dlg.construction.setCurrentIndex(1)   # Coax (RG-58 preset applied above)
    dlg._run_thermal()
    tc_rep = dlg._thermal
    assert tc_rep["kind"] == "coax" and len(tc_rep["p_max_w"]) == 19, \
        "coax thermal curve missing"
    assert all(p > 0 for p in tc_rep["p_max_w"]) and \
        tc_rep["p_max_w"][0] > tc_rep["p_max_w"][-1], \
        "coax P_max(f) must be positive and decreasing"
    return ("litz + coax (RG-58 {0:.2f} ohm) + wire (AWG-10 {1:.3f} mohm/m) "
            "+ twisted pair (Cat6 ~100 ohm, degrees-correct) "
            "+ bundle (7-hex OD 3x, NE {2:.1f} dB, diff k {3:.1e}) "
            "+ thermal (AWG-10 {4:.0f} A @105°C) OK".format(
                dlg._coax["z0_ohm"], dlg._con.rdc_per_meter() * 1e3,
                dlg._xtalk["vne_db"], xd["k_diff"], tw_rep["ampacity_a"]))


def _cosite_dialog():
    """The co-site interference dialog constructs + analyzes under the GUI.

    No document needed. Constructing it runs a full analyze() over the default
    radio list (IMD products + desense + spectrum plot), guarding that the whole
    view wires up headlessly.
    """
    from emstudio.ui.cosite_dialog import CositeDialog

    dlg = CositeDialog()  # __init__ -> _analyze: engine + report + frequency map
    txt = dlg.report_view.toPlainText()
    assert "CO-SITE INTERFERENCE REPORT" in txt, "co-site report empty"
    # the default list has a 2f1-f2 product landing on the 149 MHz receiver
    hit = [h for h in dlg._rep["imd"] if abs(h["freq_hz"] - 149e6) < 1e3]
    assert hit, "default co-site example should show the 2f1-f2 IMD hit"
    # the frequency-plan optimizer button runs and rewrites the report
    dlg._optimize()
    assert "optimized" in dlg.report_view.toPlainText(), "optimizer report missing"
    # per-pair isolation import (§5 polish, v0.42): applying a matrix re-runs
    # the analysis with the dict and editing the scalar clears it
    dlg._apply_iso_pairs({(0, 2): 60.0, (2, 0): 60.0, (1, 2): 45.0,
                          (2, 1): 45.0}, "test pairs")
    assert dlg._iso_pairs is not None and "per-pair" in dlg.iso_status.text(), \
        "isolation matrix not applied"
    assert "CO-SITE INTERFERENCE REPORT" in dlg.report_view.toPlainText(), \
        "report did not regenerate with the pair matrix"
    dlg.isolation.setValue(31.0)   # scalar edit clears the imported matrix
    assert dlg._iso_pairs is None and "scalar" in dlg.iso_status.text(), \
        "scalar edit did not clear the matrix"
    return "report + map + optimizer + pair-matrix import OK ({0} IMD)".format(
        len(dlg._rep["imd"]))


def _link_budget_dialog():
    """The point-to-point link-budget dialog constructs + computes under the GUI."""
    from emstudio.ui.link_dialog import LinkBudgetDialog

    dlg = LinkBudgetDialog()  # __init__ -> _analyze: propagation models + plot
    txt = dlg.readout.toPlainText()
    assert "LINK BUDGET" in txt, "link-budget read-out empty"
    assert "free-space loss" in txt and "field strength" in txt, "readout incomplete"
    return "link budget + path-loss plot OK"


def _coverage_dialog():
    """The area coverage dialog constructs + computes a footprint under the GUI.

    No document needed. Constructing it runs a full _compute (smooth-earth omni
    heatmap over a lat/lon grid + the map plot + coverage stats), guarding that
    the §6-B engine (geodesy/terrain/heatmap/kml) wires through the view
    headlessly, then flips to the field-strength metric and re-computes.
    """
    import numpy as np

    from emstudio.coverage import propagation as pr
    from emstudio.ui.coverage_dialog import CoverageDialog

    dlg = CoverageDialog()  # __init__ -> _compute: heatmap + draw + summary
    assert dlg._result is not None, "coverage did not compute"
    assert "AREA COVERAGE" in dlg.readout.toPlainText(), "coverage read-out empty"
    assert dlg.export_btn.isEnabled(), "KML export should be enabled after a compute"
    # the smooth-earth omni cell must equal EIRP - FSPL (engine degeneracy)
    res = dlg._result
    ci = res.meta["n"] // 2
    from emstudio.coverage import geodesy as geo
    d = geo.haversine_m(res.meta["tx_lat"], res.meta["tx_lon"],
                        float(res.lats[ci]), float(res.lons[-1]))
    # dialog default keeps 4/3 earth; only assert Prx is finite + falls with range
    assert np.isfinite(res.prx_dbm[ci, -1]), "no Prx at an edge cell"
    assert res.prx_dbm[ci, ci + 1] > res.prx_dbm[ci, -1], "Prx should fall with range"
    dlg.metric_combo.setCurrentIndex(1)  # field strength
    dlg._compute()
    assert "dBuV/m" in dlg.readout.toPlainText(), "field-strength metric did not apply"
    # switch to the LF/MF ground-wave (P.368) model and recompute
    dlg.freq_unit.setCurrentText("MHz")
    dlg.freq.setValue(1.0)
    dlg.pmodel.setCurrentIndex(1)  # ground-wave (flat earth)
    dlg.ground.setCurrentText("Average ground")
    dlg._compute()
    assert dlg._result.meta.get("model") == "ground_wave", "ground-wave model not applied"
    assert dlg._result.meta.get("gw_engine") == "flat", "flat gw engine not applied"
    assert "ground-wave" in dlg.readout.toPlainText(), "ground-wave read-out missing"
    gw_center = dlg._result.field_dbuv_m[ci, ci + 1]
    gw_edge = dlg._result.field_dbuv_m[ci, -1]
    assert gw_center > gw_edge, "ground-wave field should fall with range"
    # the P.368-10 spherical-earth engine (the LFMF port) behind the 3rd entry
    # (needs scipy — skip on scipy-less bundles, like the smoke-test block)
    from emstudio.coverage import lfmf as _lfmf
    if _lfmf.HAVE_SCIPY:
        dlg.pmodel.setCurrentIndex(2)  # ground-wave (P.368-10 spherical)
        dlg._compute()
        assert dlg._result.meta.get("gw_engine") == "p368", \
            "p368 gw engine not applied"
        assert "spherical" in dlg.readout.toPlainText(), \
            "spherical read-out missing"
        assert (dlg._result.field_dbuv_m[ci, ci + 1]
                > dlg._result.field_dbuv_m[ci, -1]), \
            "spherical ground-wave field should fall with range"
    # the terrain diffraction selector + two-ray option are wired (numerics gated
    # separately in tests/validation/coverage.py)
    assert dlg.diffraction.count() == 5, "diffraction-method selector missing options"
    dlg.pmodel.setCurrentIndex(0)          # back to auto
    dlg.diffraction.setCurrentIndex(1)     # multi-edge Deygout
    dlg.ground_refl.setChecked(True)       # two-ray on clear paths
    dlg._compute()
    assert dlg._result is not None, "recompute with a diffraction method failed"
    # the empirical Hata/COST-231 model path (900 MHz suburban)
    dlg.freq.setValue(900.0)
    dlg.pmodel.setCurrentIndex(3)          # Hata / COST-231
    dlg.environment.setCurrentIndex(2)     # suburban
    dlg._compute()
    assert dlg._result.meta.get("model") == "hata" \
        and dlg._result.meta.get("environment") == "suburban", \
        "Hata model/environment not applied"
    assert "Hata" in dlg.readout.toPlainText(), "Hata read-out missing"
    return ("coverage footprint + map + stats + ground-wave flat/P.368-10 + "
            "multi-edge + Hata OK ({0}x{0} grid)".format(res.meta["n"]))


def _multistation_dialog():
    """The multi-station service/interference (D/U) dialog constructs + computes.

    No document needed. Constructing it runs a full _compute (two co-channel MF
    stations composed onto ONE shared grid -> wanted/unwanted D/U + the two-gate
    service classification + the map), guarding that the §6 phase-C multi-station
    engine (multistation.service_contour, reusing heatmap + the §5 D/U logic) wires
    through the view headlessly, then flips to the network best-server metric.
    """
    import numpy as np

    from emstudio.coverage import multistation as ms
    from emstudio.ui.multistation_dialog import MultiStationDialog

    dlg = MultiStationDialog()  # __init__ -> _compute: contours + draw + summary
    assert dlg._result is not None, "multi-station did not compute"
    assert "SERVICE / INTERFERENCE" in dlg.readout.toPlainText(), \
        "multi-station read-out empty"
    assert dlg.export_btn.isEnabled(), "KML export should be enabled after a compute"
    res = dlg._result
    assert res.meta["n_interferers"] == 1, "default example should have one interferer"
    # the wanted side has a high D/U, the interferer side a negative D/U
    assert np.nanmax(res.du_db) > 20.0 and np.nanmin(res.du_db) < -10.0, \
        "D/U map lacks wanted/interferer contrast"
    served = res.fraction(ms.SERVED)
    # the P.368-10 spherical ground-wave engine behind the 2nd combo entry
    # (needs scipy — skip on scipy-less bundles)
    from emstudio.coverage import lfmf as _lfmf
    if _lfmf.HAVE_SCIPY:
        dlg.pmodel.setCurrentIndex(1)
        dlg._compute()
        assert dlg._result.meta.get("gw_engine") == "p368", \
            "spherical gw engine not applied to the multi-station composer"
        assert "spherical" in dlg.readout.toPlainText(), \
            "multi-station spherical read-out missing"
        dlg.pmodel.setCurrentIndex(0)
    # flip to the network best-server metric and recompute
    dlg.metric_combo.setCurrentText("Best server (network)")
    dlg._compute()
    assert dlg._bs is not None, "best-server metric did not compute"
    servers = set(np.unique(dlg._bs["server"]).tolist())
    assert servers <= {-1, 0, 1}, "best-server assigned an invalid station index"
    return "D/U contours + service map + best-server OK ({0:.0%} served)".format(served)


def _system_matching_dialog():
    """The System Matching Designer dialog (§7 slice S2) under the real GUI.

    Construction synthesizes the default typed element (72 ohm) to 50 ohm with
    the lowpass L-match; the schedule + banner read-outs must render; the
    recommender ranks the topologies; switching to pi / quarter-wave re-designs;
    the E-series snap tags the schedule; and _current_report_design returns a
    reportable design. No solver — the live NEC2 ingest is gated in
    tests/validation/system_match_nec2.py.
    """
    try:
        from emstudio.ui.matching_dialog import SystemMatchingDialog
    except ImportError:
        # EMStudioFree ships this gate but NOT §7 (Pro-side), so the check
        # stands down on its own. A denied module must never need code
        # surgery in the free repo to keep its tests green -- that
        # maintenance burden is what killed the first, larger tier split.
        return "skipped — the System Matching Designer is Pro-only and absent in this build"

    dlg = SystemMatchingDialog()          # __init__ -> default 72->50 L-match
    assert dlg._design is not None, "default matching synthesis produced nothing"
    sched = dlg.sched_view.toPlainText()
    assert ("inductor" in sched or "capacitor" in sched), \
        "L-match component schedule empty"
    assert "VSWR" in dlg.banner.text(), "matching banner has no VSWR read-out"

    # recommender ranks the topologies with rationale
    dlg._recommend()
    assert "L-match" in dlg.rec_view.toPlainText(), "recommender read-out empty"

    # pi topology: three elements, chosen loaded Q
    dlg.loaded_q.setValue(5.0)
    dlg.topology.setCurrentIndex(dlg.topology.findData("pi"))
    assert dlg._design is not None and dlg._design["kind"] == "pimatch", \
        "pi-match did not synthesize"

    # quarter-wave transformer: 50->72 -> Zc = sqrt(50*72) = 60 ohm in schedule
    dlg.topology.setCurrentIndex(dlg.topology.findData("quarter_wave"))
    assert "60.0" in dlg.sched_view.toPlainText(), \
        "quarter-wave section impedance missing from schedule"

    # E-series snap tags the schedule on a lumped topology
    dlg.topology.setCurrentIndex(dlg.topology.findData("l_lowpass"))
    dlg.eseries.setCurrentIndex(dlg.eseries.findData(24))
    assert "E24" in dlg.sched_view.toPlainText(), "E-series snap not applied"

    # report design is pure + present
    assert dlg._current_report_design() is not None, "no report design"

    # a REACTIVE element on a real-load-only topology must REFUSE (not report a
    # false perfect match): editing X live re-designs, pi cannot absorb it
    dlg.eseries.setCurrentIndex(dlg.eseries.findData(0))
    dlg.elem_x.setValue(-30.0)            # connected -> live recompute
    dlg.topology.setCurrentIndex(dlg.topology.findData("pi"))
    assert dlg._design is None, "pi must refuse a reactive element, not fake a match"
    assert "Cannot synthesize" in dlg.banner.text(), "no refusal banner shown"
    assert not dlg.report_btn.isEnabled(), "Report enabled on a failed design"
    # and an L-match (which absorbs reactance) recovers cleanly
    dlg.topology.setCurrentIndex(dlg.topology.findData("l_lowpass"))
    assert dlg._design is not None and dlg._design["kind"] == "lmatch", \
        "L-match should absorb the reactive element"
    return ("system matching dialog OK (L/pi/quarter-wave + recommender + E24 "
            "+ reactive-load refusal)")


def _assistant_dock():
    """The Assistant dock builds, is a singleton, and degrades with NO endpoint.

    The important case is the LAST one. This panel is the only feature whose
    backend is optional and off by default, so the failure that matters is not
    "does it work with a model" but "does it stay harmless without one" — a
    dock that raises on construction would break the workbench for every user
    who never configures an endpoint.
    """
    import os
    try:
        from emstudio.ui import assistant_dock as AD
    except ImportError:
        # EMStudioFree ships this gate but NOT the assistant (Pro-side), so the
        # check must stand down on its own. Requiring a manual edit after every
        # export is the exact maintenance burden that killed the first, larger
        # tier split — a denied module must never need code surgery in the free
        # repo to keep its tests green.
        return "skipped — assistant is Pro-only and absent in this build"

    # Point at a dead port for the whole check: gui_smoke must never depend on
    # a running LLM, and this is exactly the state most users start in.
    old = os.environ.get("EMSTUDIO_LLM_ENDPOINT")
    os.environ["EMSTUDIO_LLM_ENDPOINT"] = "http://127.0.0.1:59996/v1"
    try:
        dock = AD.AssistantDock()
        assert dock.objectName() == AD._OBJECT_NAME, "dock objectName not set"
        assert dock.widget() is not None, "dock has no body widget"

        # the controls the command depends on
        for attr in ("question_edit", "answer_view", "ask_btn", "recheck_btn",
                     "status_label", "context_check"):
            assert hasattr(dock, attr), "missing control: {0}".format(attr)

        # Asking with no question must be a no-op, not an exception or a call.
        dock.question_edit.setPlainText("")
        dock._on_ask()

        # With no reachable backend the ask button must be disabled rather than
        # dispatching a request that cannot succeed.
        dock._render_caps({"reachable": False, "notes": ["no endpoint"]})
        dock._set_busy(False)
        assert not dock.ask_btn.isEnabled(), \
            "ask must be disabled while the backend is unreachable"
        assert "unavailable" in dock.status_label.text().lower(), \
            "unreachable backend must say so: {0!r}".format(dock.status_label.text())

        # ...and enabled once a backend reports in.
        dock._caps = {"reachable": True, "model": "m", "tools": True,
                      "json_schema": True, "notes": []}
        dock._render_caps(dock._caps)
        dock._set_busy(False)
        assert dock.ask_btn.isEnabled(), "ask must enable when the backend is up"

        # An answer with no retrieval hits must SAY it is ungrounded rather than
        # presenting itself as documentation-backed.
        dock._render_answer("q", "an answer", [])
        assert "not grounded" in dock.answer_view.toPlainText().lower(), \
            "an ungrounded answer must be labelled as such"

        # ...and with hits, the sources must be shown.
        dock._render_answer("q", "an answer",
                            [{"source": "HELP.md", "heading": "Ports",
                              "text": "x", "score": 1.0}])
        shown = dock.answer_view.toPlainText()
        assert "HELP.md" in shown, "sources must be cited in the answer"

        # An empty model reply must not render as a blank panel.
        dock._render_answer("q", "   ", [])
        assert "empty" in dock.answer_view.toPlainText().lower()

        # ...and it must still report ACTIONS that already happened. The panel
        # returned early on empty content and threw the notes away, so a user
        # who had just approved a document change was told only "empty answer,
        # try rephrasing" -- an invitation to build the same thing twice.
        dock._render_answer("q", "", [], notes=["Done: Create a yagi"])
        _empty = dock.answer_view.toPlainText()
        assert "empty" in _empty.lower(), "the empty-answer wording must survive"
        assert "Create a yagi" in _empty, \
            "actions already carried out must be reported on an empty answer"

        # --- A4: agentic mode is gated on the BACKEND, not on a preference.
        # A model that cannot call tools must never be offered "Let it act" --
        # it would answer in prose and look to the user like it had acted.
        dock._render_caps({"reachable": True, "model": "m", "tools": False,
                           "json_schema": True, "notes": []})
        assert not dock.agentic_check.isEnabled(), \
            "agentic mode must be disabled when the model cannot tool-call"
        assert not dock.agentic_check.isChecked(), \
            "agentic mode must also be unchecked, not merely greyed"
        dock._render_caps({"reachable": True, "model": "m", "tools": True,
                           "json_schema": True, "notes": []})
        assert dock.agentic_check.isEnabled(), \
            "agentic mode must enable when the model can tool-call"

        # A refused tool call must be reported, not silently swallowed, and it
        # must never reach the document.
        from emstudio.assistant import tools as AT   # present iff AD imported
        try:
            AT.prepare("create_template", {"template": "dipole",
                                           "frequency_hz": 435})
            raise AssertionError("435 Hz should have been refused")
        except AT.ToolError:
            pass

        # tree summary is defensive: no document must not raise
        assert isinstance(AD._tree_summary(), str)

        # --- A4: the CONFIRMED mutation path. Nothing in the FAST tier can
        # reach it -- that tier is python3-only and importing FreeCAD raises
        # there -- so the entire transaction contract was uncovered. Poisoning
        # the whole of _create_template left the battery at 23 ok.
        import FreeCAD

        _doc = FreeCAD.newDocument("assistant_txn_gate")
        try:
            _mine = _doc.addObject("App::FeaturePython", "UserObject")
            _before = [o.Name for o in _doc.Objects]
            _plan = AT.prepare("create_template",
                               {"template": "dipole", "frequency_hz": 145e6})
            assert _plan["needs_confirmation"], "a mutation must need confirming"
            AT.execute(_plan, confirmed=True)
            assert len(_doc.Objects) > len(_before), "nothing was created"
            # ONE undoable transaction, named -- not a pile of loose changes.
            assert _doc.UndoNames and "dipole" in _doc.UndoNames[0], \
                "expected one named transaction, got {0}".format(_doc.UndoNames)
            # ...and undoing it must restore EXACTLY the prior document. Without
            # openTransaction, one Ctrl+Z deletes the user's own object instead
            # and leaves the assistant's five behind: real data loss.
            _doc.undo()
            assert [o.Name for o in _doc.Objects] == _before, \
                ("one undo must restore the document exactly; got {0} want {1}"
                 .format([o.Name for o in _doc.Objects], _before))
            assert _mine.Name in [o.Name for o in _doc.Objects], \
                "the user's own object must survive an undo of the assistant's"

            # The no-result branch is only reachable WITH a document. Solver
            # results are never attached to the object, so this fires even after
            # a successful solve -- it must not tell the user to run a solver
            # they just ran.
            _ir = AT.execute(AT.prepare("interpret_results", {}))
            assert "run a solver first" not in _ir.get("error", ""), \
                "interpret_results must not blame the user for a missing result"

            # --- DECLINING must actually decline. The dock calls
            # tools.execute(plan, confirmed=True), so the engine's own refusal
            # guard cannot catch a dock-side regression: dropping the
            # `if plan["needs_confirmation"]` branch leaves BOTH the FAST
            # battery and this file green while No silently means Yes.
            from PySide import QtWidgets as _QtW

            _asked = []
            _real_question = _QtW.QMessageBox.question
            _real_run = AD.run_gui.run_generic_gui

            def _always_no(*a, **k):
                _asked.append(1)
                return _QtW.QMessageBox.No

            _QtW.QMessageBox.question = staticmethod(_always_no)
            AD.run_gui.run_generic_gui = lambda *a, **k: None
            try:
                _n_before = len(_doc.Objects)
                dock._handle_tool_calls(
                    "build me a dipole", [],
                    [{"id": "1", "function": {"name": "create_template",
                                              "arguments":
                                                  '{"template":"dipole",'
                                                  '"frequency_hz":145000000}'}}],
                    [])
                assert len(_asked) == 1, \
                    "the user must be asked exactly once, got {0}".format(len(_asked))
                assert len(_doc.Objects) == _n_before, \
                    ("a DECLINED action changed the document ({0} -> {1})"
                     .format(_n_before, len(_doc.Objects)))
            finally:
                _QtW.QMessageBox.question = _real_question
                AD.run_gui.run_generic_gui = _real_run
        finally:
            FreeCAD.closeDocument(_doc.Name)
    finally:
        if old is None:
            os.environ.pop("EMSTUDIO_LLM_ENDPOINT", None)
        else:
            os.environ["EMSTUDIO_LLM_ENDPOINT"] = old


def _examples_are_visible():
    """Every shipped example opens with its geometry VISIBLE.

    The first generated set was built under freecadcmd, which creates no
    ViewObjects — so the saved documents carried no visibility state and every
    wire opened HIDDEN. A user double-clicking the example saw an empty 3-D view
    and would reasonably conclude the workbench was broken. smoke.py cannot
    catch this: without a GUI there is no ViewObject to ask.
    """
    import glob

    import FreeCAD

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = sorted(glob.glob(os.path.join(here, "examples", "*.FCStd")))
    assert paths, "examples/ contains no .FCStd"
    for path in paths:
        name = os.path.basename(path)
        doc = FreeCAD.openDocument(path)
        try:
            shapes = [o for o in doc.Objects if getattr(o, "Shape", None) is not None]
            assert shapes, "{0} has no shape objects at all".format(name)
            visible = [o for o in shapes
                       if getattr(getattr(o, "ViewObject", None), "Visibility", False)]
            assert visible, \
                ("{0} opens with ALL {1} shapes hidden — an empty viewport"
                 .format(name, len(shapes)))
        finally:
            FreeCAD.closeDocument(doc.Name)
    return "{0} examples open with visible geometry".format(len(paths))


def _pattern_overlay_coloured():
    """A 3-D result overlay arrives COLOURED by its scalar field, not flat grey.

    The colouring line used to read the Field property into a local and throw it
    away, inside a swallowing try/except — so every balloon rendered monochrome
    with a colour legend beside it that explained nothing, which is the one thing
    the overlay exists to show. `Field` is an ENUMERATION: reading it returns the
    CURRENT value, so the choices must come from getEnumerationsOfProperty.
    """
    import numpy as np

    import FreeCAD

    from emstudio.post.farfield import FarFieldResult
    from emstudio.post import vtk_out

    th = np.arange(0.0, 180.1, 10.0)
    ph = np.arange(0.0, 360.0, 10.0)
    gain = 6.0 * np.cos(np.deg2rad(th))[:, None] * np.ones((1, ph.size)) - 3.0
    ff = FarFieldResult(300e6, th, ph, gain)

    doc = FreeCAD.newDocument("emstudio_overlay_gate")
    try:
        obj = vtk_out.show_pattern(ff, "gate balloon", extent_mm=400.0, doc=doc,
                                   transparency=40)
        vo = obj.ViewObject
        assert vo.DisplayMode == "Surface", \
            "overlay must render as a surface, got {0!r}".format(vo.DisplayMode)
        assert vo.Field == "Gain_dBi", \
            "overlay must be coloured by its own field, got {0!r}".format(vo.Field)
        assert int(vo.Transparency) == 40, \
            "transparency was not applied ({0!r})".format(vo.Transparency)
    finally:
        FreeCAD.closeDocument(doc.Name)
    return "overlay coloured by Gain_dBi, transparency honoured"


def _rfdf_dialog():
    """The RFDF dialog constructs and every technique page computes (§7 S6).

    No document and no solver needed for the analytic pages — the four
    techniques are closed-form. Verify (live NEC2) is exercised by
    tests/validation/rfdf_nec2.py, not here.
    """
    try:
        from emstudio.ui import rfdf_dialog as RD
    except ImportError:
        # EMStudioFree ships this gate but NOT §7 (Pro-side), so the check
        # stands down on its own. A denied module must never need code
        # surgery in the free repo to keep its tests green -- that
        # maintenance burden is what killed the first, larger tier split.
        return "skipped — the RFDF designer is Pro-only and absent in this build"

    dlg = RD.RFDFDialog()

    # every technique page must produce a read-out, not an exception
    seen = []
    for i, (key, _label) in enumerate(RD.TECHNIQUES):
        dlg.tech.setCurrentIndex(i)
        assert dlg._key() == key, "technique page {0} mis-wired".format(key)
        txt = dlg.readout.toPlainText()
        assert txt and "cannot compute" not in txt, \
            "{0} page produced no read-out: {1!r}".format(key, txt[:120])
        seen.append(key)
    assert len(seen) == 4, "expected 4 technique pages, got {0}".format(seen)

    # Verify is correlative-only — it is the only page with a live chain
    dlg.tech.setCurrentIndex(3)
    assert dlg.verify_btn.isEnabled(), "Verify must be live on the correlative page"
    dlg.tech.setCurrentIndex(0)
    assert not dlg.verify_btn.isEnabled(), \
        "Verify must be disabled on the analytic-only pages"

    # the honest aperture ladder: lambda/8 ideal, lambda/2 unusable
    ideal = RD.watson_watt_text(0.125)
    dead = RD.watson_watt_text(0.5)
    assert "ideal" in ideal, "R = lambda/8 should read as ideal"
    assert "UNUSABLE" in dead, "R = lambda/2 is the hard ceiling"
    # and the lambda/3 conflation is called out where it belongs
    assert "lambda/3" in RD.doppler_text(150e6, 4, 0.1556), \
        "the lambda/3 rule belongs on the Doppler page"

    # the degeneracy that motivates odd element counts must SHOW
    deg = RD.correlative_text(4, 0.5, 300e6)
    good = RD.correlative_text(5, 0.5, 300e6)
    assert "DEGENERATE" in deg, "a 4-ring at R = lambda/2 must flag degenerate"
    assert "DEGENERATE" not in good, "a 5-ring at the same R must not"

    # an over-long interferometer baseline ratio must be refused, not flattered
    bad = RD.interferometer_text(0.5, 40.0, 20.0, 20.0, 1)
    assert "TOO LARGE" in bad, "an 80:1 ratio at sigma 20 deg must be refused"
    return "RFDF dialog OK (4 technique pages + aperture/degeneracy/ratio guards)"


def _about_and_legal_dialogs():
    """About / Legal must construct with NO document and NO solver, and must
    actually carry the intended-use, liability and brand wording.

    These two are the user's only in-app route to the disclaimer, so a silent
    regression here is a legal problem, not a cosmetic one. The check reads the
    rendered widget text rather than trusting the constructor.
    """
    from emstudio import legal
    from emstudio.ui.about_dialog import (AboutDialog, FirstRunNoticeDialog,
                                          LegalDialog)

    def _all_text(widget):
        from PySide import QtWidgets

        out = []
        for lab in widget.findChildren(QtWidgets.QLabel):
            out.append(lab.text())
        return " ".join(out)

    about = AboutDialog()
    at = _all_text(about)
    assert "EMStudio" in about.windowTitle(), "About window title"
    for must in ("EDUCATIONAL", "ACTIVE DEVELOPMENT", "AJJ"):
        assert must in at.upper(), "About dialog missing {0!r}".format(must)
    assert "NOT LICENSED" in at.upper(), \
        "About dialog missing the trademark notice"

    dlg = LegalDialog()
    lt = _all_text(dlg)
    for title, _text in legal.LEGAL_SECTIONS:
        assert title in lt, "Legal dialog missing section {0!r}".format(title)
    for must in ("NO WARRANTY AND NO LIABILITY", "ENTIRELY AT YOUR OWN RISK",
                 "EDUCATIONAL, HOBBYIST and EXPERIMENTAL"):
        assert must in lt, "Legal dialog missing {0!r}".format(must)

    notice = FirstRunNoticeDialog(version="0.0.0-test")
    nt = _all_text(notice)
    assert "UNDER ACTIVE DEVELOPMENT" in nt, "first-run notice missing status"
    assert "NO RESPONSIBILITY" in nt, "first-run notice missing liability"

    # both commands must be reachable from the menu, not only registered
    from emstudio import commands

    grouped = commands.grouped_commands()
    assert commands.CMD_ABOUT in grouped and commands.CMD_LEGAL in grouped, \
        "About/Legal must be in a COMMAND_GROUPS group (the EMStudio menu)"
    # The invariant is that About + Legal sit at the BOTTOM of the menu, where
    # users look for them and where the disclaimer must always be reachable.
    # This used to assert the Help group held ONLY those two, which was a proxy
    # for the same thing — too strict once §3 put the Assistant in Help (it is
    # help, and it is where a user hunting for help looks). Assert the real
    # property: whatever else is in the group, these two come last.
    help_group = [g for g in commands.COMMAND_GROUPS if g[0] == "Help"]
    assert help_group, "there must be a Help group"
    entries = [c for c in help_group[0][1] if c != "Separator"]
    assert entries[-2:] == [commands.CMD_ABOUT, commands.CMD_LEGAL], \
        ("About + Legal must be the LAST two Help entries so the disclaimer "
         "sits at the bottom of the menu; got {0}".format(entries))
    assert help_group[0][0] == commands.COMMAND_GROUPS[-1][0], \
        "the Help group itself must be last"
    return "about + legal + first-run notice OK (text asserted, Help group)"


def _run_solver_openfoam_dispatch():
    """Run Solver must ROUTE an OpenFOAM solver, not reject it.

    WHY THIS EXISTS: the object is named `SolverOpenFOAM` and sits in the tree
    beside SolverNEC2, so Run Solver is the obvious thing to press — and the
    dispatch table had branches for NEC2 / openEMS / Elmer / Palace only. It
    fell through to `_warn("Unknown solver type: ...")`, which reads like a
    corrupt document rather than "use the other command" (AJ hit it live,
    2026-08-13).

    Asserted BEHAVIOURALLY, by driving Activated() with the convection
    entrance stubbed — not by matching source text. A source match would pass
    on a branch that dispatched to the wrong place, and this project has been
    caught by exactly that (2026-08-06: a comment satisfied the match while
    the real call was deleted).

    The stub is the right seam: the convection command opens a MODAL dialog,
    so calling it for real would hang the suite. What is under test is the
    dispatcher's routing, not the dialog.
    """
    import FreeCAD

    from emstudio import commands as _cmds
    from emstudio.objects import solver_objs

    doc = FreeCAD.newDocument("gui_of_dispatch")
    real_conv, real_warn = _cmds._Convection.Activated, _cmds._warn
    seen = {"solver": None, "calls": 0}
    warnings = []
    try:
        ana = _cmds._active_analysis(create=True)
        solver = solver_objs.makeSolverOpenFOAM(doc, ana)
        doc.recompute()

        def fake_conv(self, solver=None):
            seen["calls"] += 1
            seen["solver"] = solver

        _cmds._Convection.Activated = fake_conv
        _cmds._warn = lambda msg: warnings.append(msg)

        _cmds._RunSolver().Activated()

        assert seen["calls"] == 1, (
            "Run Solver did not route the OpenFOAM solver to the convection "
            "command (calls={0}, warnings={1})".format(seen["calls"], warnings))
        # ROUTED WITH THE RIGHT OBJECT. Passing None would silently fall back
        # to "first SolverOpenFOAM in the document", which is not the same
        # thing once a document holds two of them.
        assert seen["solver"] is solver, (
            "convection was handed {0!r}, not the solver Run Solver "
            "resolved".format(seen["solver"]))
        assert not any("Unknown solver type" in w for w in warnings), \
            "Run Solver still reports OpenFOAM as an unknown solver: {0}".format(
                warnings)
        return "OpenFOAM routes to the convection command with its own solver"
    finally:
        _cmds._Convection.Activated = real_conv
        _cmds._warn = real_warn
        FreeCAD.closeDocument(doc.Name)


def _solver_setup_dialog():
    """Solver Setup must build, and the Windows guided-install branch must
    actually produce Install buttons.

    WHY THIS EXISTS: v0.78.0 rewrote installer_dialog.py's Windows path and
    v0.78.1 followed it, and NOTHING in the gate suite touched the file. It has
    no other caller than a lazy import in commands.py, so a green gui_smoke was
    reported as covering a change it could not see (found 2026-08-04). Worse,
    every changed line is behind ``self._is_win``, so even constructing the
    dialog on Linux exercises none of it -- the Windows branch has to be
    SIMULATED or it is untested on every machine that is not Windows.

    Forces os.name = "nt" with every backend missing, then asserts the table
    the user would actually see.
    """
    import os as _os

    from emstudio.setup import solvers
    from emstudio.ui.installer_dialog import SolverInstallerDialog

    def buttons(dlg):
        out = {}
        for row in range(dlg.table.rowCount()):
            w = dlg.table.cellWidget(row, 3)
            out[dlg.table.item(row, 0).text()] = w.text() if w is not None else None
        return out

    def settle(dlg, timeout_ms=240000):
        """Pump events until the detection sweep lands. Never a fixed sleep.

        ⚠ The bound is GENEROUS on purpose. Detection is real subprocess work
        — a version probe per backend plus an OpenFOAM run — so its wall clock
        depends on what else the machine is doing. At 60 s this flaked exactly
        once, on a run sharing the box with the validation battery, and a
        timeout that fails only under load is a worse gate than no gate: it
        trains you to re-run instead of to read.
        """
        import time as _t
        from PySide import QtWidgets as _QtW
        t_end = _t.time() + timeout_ms / 1000.0
        while _t.time() < t_end:
            _QtW.QApplication.processEvents()
            if (dlg._detect is not None and dlg._detect["done"]
                    and dlg.table.rowCount() >= len(solvers.BACKENDS)):
                return
        raise AssertionError("solver detection did not finish within "
                             "{0} ms".format(timeout_ms))

    def assert_not_blocking(dlg):
        """THE FREEZE GATE (AJ, 2026-08-13).

        Detection is seconds of subprocess work — every backend's version
        probe, WSL queries, and an OpenFOAM discovery that RUNS a solver.
        Run inline from __init__ it froze FreeCAD before the window even
        painted: "takes forever to come up", then Not Responding.

        So immediately after construction the table must hold ONLY the
        placeholder. A table already carrying backend rows here means the
        constructor blocked on detection again.
        """
        assert dlg.table.rowCount() == 1, (
            "solver detection ran inline in the constructor ({0} rows already "
            "populated) — the GUI would freeze".format(dlg.table.rowCount()))
        first = dlg.table.item(0, 0)
        assert first is not None and first.text().startswith("Detecting"), \
            "expected the 'Detecting…' placeholder, got {0!r}".format(
                first.text() if first is not None else None)

    # --- the real platform path ---------------------------------------------
    # The real property is CONDITIONAL: guided-install buttons exist ONLY on
    # native Windows. This used to assert "no Install button" flat, which is
    # the same claim only where the test happened to run — Linux, macOS, and a
    # VM with every backend already installed. On a real Windows box with a
    # missing installable backend (the WORK box: OpenFOAM absent, WSL2
    # blocked) the dialog CORRECTLY offers Install… and the flat assertion
    # called correct behaviour a failure (2026-08-07). The Windows behaviours
    # themselves are pinned by the simulated-Windows branch below.
    dlg = SolverInstallerDialog()
    assert_not_blocking(dlg)
    settle(dlg)
    assert dlg.table.rowCount() >= len(solvers.BACKENDS), "backend rows missing"
    if _os.name != "nt":
        assert "Install…" not in buttons(dlg).values(), \
            "a guided-install button appeared OFF Windows"
    dlg.deleteLater()

    # --- simulated native Windows -------------------------------------------
    real_name, real_detect = _os.name, solvers.detect_all
    real_local = _os.environ.get("LOCALAPPDATA")
    try:
        _os.environ["LOCALAPPDATA"] = r"C:\Users\test\AppData\Local"
        solvers.detect_all = lambda: {
            k: solvers.SolverInfo(solvers.BACKENDS[k], "") for k in solvers.BACKENDS}
        _os.name = "nt"
        wdlg = SolverInstallerDialog()
        assert_not_blocking(wdlg)
        settle(wdlg)
        btns = buttons(wdlg)
        installable = {k for k in solvers.BACKENDS
                       if btns.get(solvers.BACKENDS[k].label) == "Install…"}
        # openfoam's guided install is the WSL2 flow, deliberately NOT a
        # WIN_INSTALL_PLANS zip — so the button contract is plans + openfoam,
        # exactly. A plan entry for openfoam appearing here would shadow the
        # WSL flow; the openfoam_setup gate guards that side.
        expected = set(solvers.WIN_INSTALL_PLANS) | {"openfoam"}
        assert installable == expected, (
            "Install buttons {0} do not match the guided-install set {1}".format(
                sorted(installable), sorted(expected)))
        assert "Build…" not in btns.values(), \
            "a from-source Build button on Windows (no bash, no compiler there)"
        # v0.78.0's actual fix: the log pane used to be hidden on Windows, which
        # would have made every guided install look like it did nothing.
        assert wdlg.log.isVisibleTo(wdlg), \
            "log pane hidden on Windows — install progress would be invisible"
        assert not wdlg.apt_row_widget.isVisibleTo(wdlg), \
            "the sudo apt row must never render on Windows"
        assert not wdlg.abort_btn.isVisibleTo(wdlg), "Abort build shown on Windows"
        wdlg.deleteLater()
    finally:
        _os.name = real_name
        solvers.detect_all = real_detect
        if real_local is None:
            _os.environ.pop("LOCALAPPDATA", None)
        else:
            _os.environ["LOCALAPPDATA"] = real_local
    return "builds; simulated Windows offers Install… for {0}".format(
        ", ".join(sorted(set(solvers.WIN_INSTALL_PLANS) | {"openfoam"})))


def _assistant_settings_dialog():
    """The assistant Settings dialog: prefill from prefs, presets, save-back.

    WHY THIS EXISTS: the endpoint/model/key had NO configuring UI at all —
    env vars or the raw parameter editor — and the work box spent a morning
    on a bare HTTP 404 that this dialog now makes self-diagnosable
    (2026-08-05). Runs against the real (throwaway under run_pro_freecad)
    parameter store and restores every key it touches.
    """
    # Import the MODULE, not names: a from-import of missing names raises
    # ImportError too, which would report a renamed attribute in the PRO tree
    # as a false "free tree" skip (review-fleet finding — same pattern as
    # _assistant_dock above).
    try:
        from emstudio.ui import assistant_dock as AD
    except ImportError:
        return "skipped — Pro assistant not present (free tree)"
    import FreeCAD
    from PySide import QtWidgets

    AssistantSettingsDialog = AD.AssistantSettingsDialog
    _PRESETS = AD._PRESETS
    grp = FreeCAD.ParamGet(AD._PREF_GROUP)
    keys = ("AssistantEndpoint", "AssistantModel", "AssistantApiKey")
    old = {k: grp.GetString(k, "") for k in keys}
    try:
        grp.SetString("AssistantEndpoint", "http://example.invalid:9/v1")
        grp.SetString("AssistantModel", "gate-model")
        grp.SetString("AssistantApiKey", "sk-guitest")
        dlg = AssistantSettingsDialog()
        assert dlg.endpoint_edit.text() == "http://example.invalid:9/v1", \
            "endpoint not prefilled from the preference"
        assert dlg.model_combo.currentText() == "gate-model", \
            "model not prefilled from the preference"
        assert dlg.key_edit.text() == "sk-guitest", \
            "key not prefilled from the preference"
        assert dlg.key_edit.echoMode() == QtWidgets.QLineEdit.Password, \
            "the API key renders in clear text"

        # A preset must fill the endpoint but never clobber a typed model.
        anthropic = next(i for i, p in enumerate(_PRESETS)
                         if "Anthropic" in p[0])
        dlg.preset_combo.setCurrentIndex(anthropic)
        assert dlg.endpoint_edit.text() == "https://api.anthropic.com/v1", \
            "preset did not fill the endpoint"
        assert dlg.model_combo.currentText() == "gate-model", \
            "preset clobbered a model the user had typed"

        # Save writes exactly what the fields hold.
        dlg.endpoint_edit.setText("http://example.invalid:7/v1")
        dlg._save()
        assert grp.GetString("AssistantEndpoint", "") == \
            "http://example.invalid:7/v1", "Save did not persist the endpoint"
        assert grp.GetString("AssistantApiKey", "") == "sk-guitest", \
            "Save did not persist the key"
        dlg.deleteLater()

        # Empty fields must probe the EFFECTIVE configuration — Test lied in
        # env-var setups otherwise (review-fleet finding: an empty key field
        # sent "no key" instead of resolving normally, so Test reported 401
        # against the very setup the dialog recommends).
        from emstudio.assistant import llm as _llm
        dlg2 = AssistantSettingsDialog()
        dlg2.endpoint_edit.clear()
        dlg2.model_combo.setCurrentText("")
        dlg2.key_edit.clear()
        assert dlg2._entered() == (_llm.endpoint_url(), _llm.model_name(),
                                   None), \
            "empty fields must fall back to the effective runtime values"
        dlg2.deleteLater()
    finally:
        for k, v in old.items():
            grp.SetString(k, v)
    return "prefill + preset (no model clobber) + save-back OK"


def main():
    _log("EMStudio real-GUI smoke test")
    _log("----------------------------")
    check("workbench + command registration", _registration)
    check("NEC2 dipole solve loop", _nec2_dipole)
    check("NEC2 monopole-over-ground solve loop (VLF/LF)", _nec2_monopole)
    check("openEMS geometry classification (flat boxes)", _openems_geometry)
    check("openEMS microstrip trace-aware deck", _openems_msl_geometry)
    check("Elmer induction solve loop", _elmer_induction)
    check("Elmer 3-D solenoid solve loop (WhitneyAV)", _elmer_solenoid3d)
    check("Elmer WPT solve + gap sweep", _elmer_wpt_and_sweep)
    check("Palace cavity + waveguide geometry extraction", _palace_cavity_geometry)
    check("Palace coax geometry extraction (curved radii)", _palace_coax_geometry)
    check("Palace cylindrical-cavity BREP export", _palace_cylcavity_geometry)
    check("Palace circular-waveguide BREP driven routing", _palace_circwg_geometry)
    check("Palace AMR opt-in (MeshRefinement property -> writer)", _palace_amr_option)
    check("quasi-static frequency guard (GUI magnetics)", _freq_guard_gui)
    check("small-antenna designer dialog (VLF/LF)", _small_antenna_dialog)
    check("element designer dialog (wire + Yagi + patch + LPDA + recommender, "
          "§1-E2/E3/E4/E5)", _element_designer_dialog)
    check("system matching designer dialog (L/pi/T/transformer/stub + "
          "recommender + E-series, §7-S2)", _system_matching_dialog)
    check("array designer dialog (named drive distributions + predicted "
          "read-outs, §7-S4)", _array_designer_dialog)
    check("cable designer dialog (litz | coax | wire | pair | bundle, §2)",
          _cable_designer_dialog)
    check("co-site interference calculator dialog", _cosite_dialog)
    check("antenna isolation matrix (NEC2 multi-port)", _isolation_matrix)
    check("point-to-point link-budget dialog", _link_budget_dialog)
    check("area coverage map dialog (§6-B)", _coverage_dialog)
    check("multi-station D/U service/interference dialog (§6-C)", _multistation_dialog)
    check("RFDF dialog (Watson-Watt / interferometer / Doppler / correlative, "
          "§7-S6)", _rfdf_dialog)
    check("Assistant dock (§3-A3: builds, degrades with no endpoint, "
          "labels ungrounded answers)", _assistant_dock)
    check("Assistant settings dialog (prefill / presets / save-back)",
          _assistant_settings_dialog)
    check("shipped examples open with VISIBLE geometry", _examples_are_visible)
    check("3-D result overlay is coloured by its field, not flat grey",
          _pattern_overlay_coloured)
    check("pattern frequency picker (multi-frequency sweep)",
          _pattern_frequency_picker)
    check("viewport scrubber stays on the 3-D view's own screen "
          "(negative-coordinate monitors)",
          _scrubber_stays_on_the_viewport_screen)
    check("VSWR plot shows off-scale data instead of an empty grid",
          _vswr_offscale_is_visible)
    check("Pattern Frequencies dialog (band + recommended step + round-trip)",
          _pattern_frequencies_dialog)
    check("results dialogs construct", _dialogs_construct)
    check("About + Legal notice dialogs (intended use / liability / brand)",
          _about_and_legal_dialogs)
    check("Run Solver routes an OpenFOAM solver instead of rejecting it",
          _run_solver_openfoam_dispatch)
    check("Solver Setup dialog + Windows guided-install buttons",
          _solver_setup_dialog)
    _log("----------------------------")
    if _failures:
        _log("GUI SMOKE FAILED: {0}".format(_failures))
        return 1
    _log("GUI SMOKE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    rc = 1
    try:
        rc = main()
    except BaseException as exc:  # noqa: BLE001
        _log("GUI smoke crashed: {0}".format(exc))
        _log(traceback.format_exc())
    # persist the log for the (buffered) offscreen-GUI run
    out = os.environ.get("GUI_SMOKE_LOG")
    if out:
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write("\n".join(_lines) + "\n")
        except Exception:
            pass
    os._exit(rc)
