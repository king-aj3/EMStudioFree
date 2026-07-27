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


def _dialogs_construct():
    """Every results dialog must import + construct under the GUI (not exec)."""
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import elmer
    from emstudio.solvers.elmer.sweep import sweep_wpt_gap
    from emstudio.solvers.elmer.model import build_axi_model
    from emstudio.templates import wpt
    from emstudio.ui.magnetics_dialog import MagneticsResultsDialog
    from emstudio.ui.sweep_dialog import GapSweepDialog

    doc = FreeCAD.newDocument("gui_dialogs")
    try:
        ana = wpt.makeWptPair(doc, gap_mm=20.0)
        solver = [s for s in query.get_solvers(ana)
                  if query.em_type(s) == "EMStudio::SolverElmer"][0]
        result = elmer.run(ana, solver)
        MagneticsResultsDialog(result)  # constructs the summary + buttons
        curve = sweep_wpt_gap(build_axi_model(ana, solver), [18.0, 32.0],
                              freq_hz=100e3)
        GapSweepDialog(curve)  # constructs the k/M plot
        return "magnetics + gap-sweep dialogs OK"
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
    help_group = [g for g in commands.COMMAND_GROUPS if g[0] == "Help"]
    assert help_group and set(help_group[0][1]) == {commands.CMD_ABOUT,
                                                    commands.CMD_LEGAL}, \
        "the Help group must hold exactly About + Legal"
    return "about + legal + first-run notice OK (text asserted, Help group)"


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
    check("cable designer dialog (litz | coax | wire | pair | bundle, §2)",
          _cable_designer_dialog)
    check("co-site interference calculator dialog", _cosite_dialog)
    check("antenna isolation matrix (NEC2 multi-port)", _isolation_matrix)
    check("point-to-point link-budget dialog", _link_budget_dialog)
    check("area coverage map dialog (§6-B)", _coverage_dialog)
    check("multi-station D/U service/interference dialog (§6-C)", _multistation_dialog)
    check("results dialogs construct", _dialogs_construct)
    check("About + Legal notice dialogs (intended use / liability / brand)",
          _about_and_legal_dialogs)
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
