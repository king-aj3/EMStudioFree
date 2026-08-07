# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless smoke test for the EMStudio workbench.

Runs under FreeCAD's console interpreter:

    freecadcmd tests/smoke.py

Exit code 0 means the Phase-0 skeleton is healthy. It checks:
  * the workbench package imports (no GUI required),
  * version strings agree between version.py and package.xml,
  * an EM Analysis object can be created in a document and is a proper group,
  * the object survives a save/reload round-trip,
  * solver detection runs and returns the full backend registry.

The script is defensive about being run outside FreeCAD (plain python) so it can also be
imported by pytest for the Qt-free parts.
"""

import os
import sys
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_failures = []


def _log(msg):
    """Emit a line that survives freecadcmd.

    Plain ``print`` output is buffered and can be dropped when a freecadcmd script
    exits, so when FreeCAD is present we write through its C++ console (unbuffered).
    We also print+flush for the plain-python/pytest paths.
    """
    line = str(msg)
    try:
        import FreeCAD

        FreeCAD.Console.PrintMessage(line + "\n")
        return  # console handled it; avoid double output on stdout
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        print(line)


def check(name, fn):
    try:
        fn()
        _log("  ok   - {0}".format(name))
    except Exception as exc:  # noqa: BLE001  (smoke test wants every failure)
        _failures.append((name, exc))
        _log("  FAIL - {0}: {1}".format(name, exc))
        traceback.print_exc()


# --- Qt-free checks (work in plain python too) -----------------------------
def _import_package():
    import emstudio  # noqa: F401
    from emstudio import version

    assert version.__version__, "version string empty"


def _version_matches_package_xml():
    from emstudio import version

    xml = os.path.join(_ROOT, "package.xml")
    with open(xml, "r", encoding="utf-8") as fh:
        text = fh.read()
    tag = "<version>{0}</version>".format(version.__version__)
    assert tag in text, "package.xml <version> != version.py ({0})".format(version.__version__)


def _package_xml_subdirectory_guard():
    """Regression guard for the invisible-workbench bug (2026-07-05).

    With package.xml present, FreeCAD runs Init/InitGui ONLY from the workbench
    content item's subdirectory — which defaults to the workbench NAME, i.e.
    Mod/EMStudio/EMStudio/. Our init scripts live at the addon root, so package.xml
    MUST carry the SINGULAR element <subdirectory>./</subdirectory> (0.21 parses the
    singular form; a plural <subdirectories> is silently ignored). Without it the
    workbench never appears in the GUI while every headless check still passes.
    """
    xml = os.path.join(_ROOT, "package.xml")
    with open(xml, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "<subdirectory>./</subdirectory>" in text, (
        "package.xml lost <subdirectory>./</subdirectory> — the workbench will "
        "silently vanish from the FreeCAD GUI (FreeCAD looks in Mod/EMStudio/EMStudio/)"
    )


def _solver_detection_runs():
    from emstudio.setup import solvers

    results = solvers.detect_all()
    assert set(results) == set(solvers.BACKENDS), "detect_all missing backends"
    for key, info in results.items():
        # Found-ness varies by machine; the contract is that it never raises and
        # every entry is a well-formed SolverInfo.
        assert hasattr(info, "found"), "SolverInfo malformed for " + key
        assert info.backend.key == key


def _elmer_env_fortran_compiler():
    """A zip-layout Elmer gets ELMER_Fortran_COMPILER when it ships a compiler.

    `elmerf90` (which builds Elmer USER FUNCTIONS) has the BUILD HOST's compiler
    path baked in, so on any other machine it compiles nothing — measured exit
    127, no output. `ELMER_Fortran_COMPILER` is the runtime override, and the
    Windows zip already ships a working GNU Fortran 10.2.0 under
    `stripped_gfortran/`. Pointing one at the other makes UDFs work with no user
    configuration (measured: a real `USE DefUtils` UDF, 95 812-byte DLL).

    EMStudio ships no UDF today, so this changes nothing that runs — which is
    exactly why it needs a check, or it would rot unnoticed until the first
    user function fails for a reason nobody would connect to a compiler path.
    """
    import tempfile

    from emstudio.solvers.elmer import runner

    if os.name != "nt":
        return "skipped off Windows (elmer_env returns None by design)"

    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "share", "elmersolver", "lib"))
    os.makedirs(os.path.join(root, "bin"))
    exe = os.path.join(root, "bin", "ElmerSolver.exe")
    open(exe, "w").close()

    # no shipped compiler -> the variable must NOT be invented
    env = runner.elmer_env(exe)
    assert env and env.get("ELMER_HOME") == root, "elmer_env broke"
    assert "ELMER_Fortran_COMPILER" not in env, \
        "pointed at a compiler that is not there"

    # shipped compiler present -> wired up
    gf = os.path.join(root, "stripped_gfortran", "bin",
                      "x86_64-w64-mingw32-gfortran.exe")
    os.makedirs(os.path.dirname(gf))
    open(gf, "w").close()
    env = runner.elmer_env(exe)
    assert env.get("ELMER_Fortran_COMPILER") == gf, \
        "shipped gfortran not wired: {0}".format(env.get("ELMER_Fortran_COMPILER"))

    # a user's own choice always wins
    os.environ["ELMER_Fortran_COMPILER"] = "C:/mine/gfortran.exe"
    try:
        env = runner.elmer_env(exe)
        assert "ELMER_Fortran_COMPILER" not in env, \
            "overrode the user's own ELMER_Fortran_COMPILER"
    finally:
        os.environ.pop("ELMER_Fortran_COMPILER", None)
    return "wired to the shipped stripped_gfortran"


def _gate_runner_tees_to_console():
    """A gate run under freecadcmd must be able to say WHY it failed.

    freecadcmd drops print() on exit, so a failing gate produced exit 1 and a
    ZERO-BYTE stderr. That silence caused a real mis-diagnosis on 2026-08-06:
    antenna_from_selection was called pre-existing when it was a regression
    introduced hours earlier, because there was no message to contradict the
    assumption. tests/run_gate.py tees stdout into FreeCAD.Console, which
    survives exit, so no gate needed editing.
    """
    src = open(os.path.join(_ROOT, "tests", "run_gate.py"),
               encoding="utf-8").read()
    assert "Console.PrintMessage" in src, "run_gate no longer tees to Console"
    assert "runpy.run_path" in src, "run_gate no longer runs the gate"
    # the exit code must survive, or the shim is worse than the silence
    assert "code = 0 if c is None else" in src,         "run_gate no longer preserves the gate's exit code"


def _battery_forces_utf8():
    """The gate battery must not let the CONSOLE decide a gate's exit code.

    Gates print arrows and "±". On Windows a child inheriting a cp1252 console
    dies with "'charmap' codec can't encode character '→'" — a
    UnicodeEncodeError indistinguishable, from the outside, from a physics
    failure. Measured 2026-08-05: element_designer PASSED from PowerShell and
    FAILED from Git Bash at the same commit.
    """
    src = open(os.path.join(_ROOT, "tests", "validation", "run_battery.py"),
               encoding="utf-8").read()
    assert 'PYTHONIOENCODING="utf-8"' in src,         "run_battery does not force the child's stdout encoding"
    assert 'encoding="utf-8"' in src,         "run_battery does not decode gate output as UTF-8"


def _openems_python_resolver():
    """openEMS's interpreter is found on BOTH venv layouts, and asks no FreeCAD.

    openEMS is the one backend driven through a python module rather than a
    CLI, so "is it usable?" is a question about an interpreter. Two things are
    pinned here:

    1. The resolver must be importable WITHOUT FreeCAD. It used to live in
       ``solvers/openems/runner.py``, whose import chain reaches
       ``objects.analysis`` -> ``import FreeCAD`` — so a gate could not ask
       whether openEMS existed without FreeCAD, and four openEMS gates FAILED
       where they should have skipped.
    2. Windows puts a virtualenv's interpreter at ``venv\\Scripts\\python.exe``,
       not ``venv/bin/python``. Only the POSIX layout was probed, so a working
       Windows install could never be detected.
    """
    import subprocess
    import tempfile

    from emstudio.setup import solvers

    # (1) FreeCAD-free: prove it in a CHILD interpreter, because this one may
    # already have FreeCAD imported.
    #
    # Compare BEFORE and AFTER rather than asserting absence: under freecadcmd
    # `sys.executable` IS freecadcmd, so the child has FreeCAD loaded by
    # construction and a bare "not in sys.modules" fails on a correct resolver.
    # (It did — caught by running the free export under FreeCAD, which is the
    # whole reason that rule exists.) The check is strict under `python3
    # smoke`, which is what CI runs, and degrades to a no-op under freecadcmd.
    probe = ("import sys; sys.path.insert(0, {0!r});"
             "before = 'FreeCAD' in sys.modules;"
             "import emstudio.setup.solvers as s;"
             "after = 'FreeCAD' in sys.modules;"
             "assert before or not after, 'importing the resolver pulled in FreeCAD';"
             "assert callable(s.find_openems_python)").format(_ROOT)
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True)
    assert out.returncode == 0, \
        "find_openems_python is not FreeCAD-free: " + (out.stderr or "")[-200:]

    # (2) both venv layouts, against a synthetic install tree.
    # The fake binary is made EXECUTABLE: find_backend's env override requires
    # os.access(.., X_OK), which a bare empty file fails on POSIX. An earlier
    # draft tolerated a None result instead, and that branch was unfalsifiable
    # — deleting the Windows layout still passed. Assert the exact path.
    root = tempfile.mkdtemp()
    for parts in (("venv", "bin", "python"), ("venv", "Scripts", "python.exe")):
        tree = os.path.join(root, parts[1])
        exe = os.path.join(tree, "bin", "openEMS")
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        open(exe, "w").close()
        os.chmod(exe, 0o755)
        cand = os.path.join(tree, *parts)
        os.makedirs(os.path.dirname(cand), exist_ok=True)
        open(cand, "w").close()
        os.environ["EMSTUDIO_OPENEMS"] = exe
        try:
            got = solvers.find_openems_python()
        finally:
            os.environ.pop("EMSTUDIO_OPENEMS", None)
        assert got == cand, \
            "venv layout {0} not resolved: got {1}".format("/".join(parts), got)

    # the env override always wins and needs no install tree at all
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as fh:
        fake = fh.name
    os.environ["EMSTUDIO_OPENEMS_PYTHON"] = fake
    try:
        assert solvers.find_openems_python() == fake
    finally:
        os.environ.pop("EMSTUDIO_OPENEMS_PYTHON", None)
        os.unlink(fake)


def _openems_gates_skip_without_openems():
    """The four live-FDTD gates SKIP a missing backend; they must not fail.

    Absence of an optional backend is not a defect in EMStudio. These four
    raised SolverError instead, turning every openEMS-less machine's battery
    red — the same correction the nec2c gates got in v0.83.0.
    """
    gates = ("patch_openems", "msl_notch_openems", "patch_auto_openems",
             "patch_stl_openems")
    for name in gates:
        path = os.path.join(_ROOT, "tests", "validation", name + ".py")
        src = open(path, encoding="utf-8").read()
        assert "from emstudio.setup.solvers import find_openems_python" in src, \
            name + " does not probe openEMS through the FreeCAD-free resolver"
        head = src.split("def main():", 1)[1].split("import FreeCAD", 1)[0]
        assert "find_openems_python() is None" in head, \
            name + " probes openEMS only AFTER importing FreeCAD, so it cannot skip"
        assert "return 0" in head, name + " does not return 0 on the skip path"


def _installer_build_plans():
    """Guided-build recipes are well-formed and never touch sudo."""
    from emstudio.setup import solvers

    source_built = [k for k, b in solvers.BACKENDS.items() if b.source_build]
    assert source_built, "no source-built backends registered"
    for key in source_built:
        plan = solvers.BUILD_PLANS.get(key)
        assert plan, "source-built backend '{0}' has no BUILD_PLANS recipe".format(key)
        assert plan.get("estimate") and plan.get("prefix"), key
        assert plan["steps"], "empty build steps for " + key
        for desc, cmd in plan["steps"]:
            assert desc and isinstance(cmd, list) and cmd, (key, desc)
            joined = " ".join(cmd)
            assert "sudo" not in joined, "build step must not use sudo: " + joined
    # non-source backends must have no recipe; build_plan() filters them
    assert solvers.build_plan("nec2") is None
    if os.name != "nt":
        assert solvers.build_plan(source_built[0]) is not None


def _elmer3d_backend_headless():
    """The 3-D WhitneyAV backend imports headless and writes .geo + .sif."""
    import tempfile

    from emstudio.meshing import gmsh_3d
    from emstudio.solvers.elmer import runner3d, writer3d  # noqa: F401

    bodies = [
        {"name": "coil",
         "shape": {"kind": "tube", "center": (0.0, 0.0), "r_in": 0.045,
                   "r_out": 0.055, "z0": -0.1, "z1": 0.1},
         "mu_r": 1.0, "lc": 0.005,
         "coil": {"amp_turns": -100.0, "normal": (0.0, 0.0, 1.0)}}]
    geo = os.path.join(tempfile.gettempdir(), "emstudio_smoke_3d.geo")
    gmsh_3d.write_geo_3d(bodies, geo,
                         air={"kind": "cylinder", "r": 0.5, "z0": -0.5,
                              "z1": 0.5}, lc_air=0.08)
    with open(geo, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "BooleanFragments" in text, "3-D .geo missing conformal fragments"
    assert 'Physical Volume("coil"' in text and 'Physical Volume("air", 1)' in text
    assert 'Physical Surface("outer"' in text, "3-D .geo missing outer skin"
    assert "Mesh.MeshSizeExtendFromBoundary = 0" in text, "size tiering off"
    sif = os.path.join(tempfile.gettempdir(), "emstudio_smoke_3d.sif")
    writer3d.write_sif3d({"bodies": bodies}, sif, {"air": 1, "coil": 2},
                         {"outer": 3})
    with open(sif, "r", encoding="utf-8") as fh:
        deck = fh.read()
    assert '"MagnetoDynamics" "WhitneyAVSolver"' in deck
    assert "Linear System Preconditioning = none" in deck, "ungauged AV needs Krylov"
    assert "Desired Coil Current = Real -100" in deck
    for p in (geo, sif):
        try:
            os.remove(p)
        except OSError:
            pass


def _elmer_backend_headless():
    """The magnetics backend imports without FreeCAD/Qt and writes a .geo."""
    import tempfile

    from emstudio.meshing import gmsh_axi
    from emstudio.post import magnetics  # noqa: F401
    from emstudio.solvers.elmer import parser, runner, sweep, writer  # noqa: F401

    regions = [{"name": "billet", "r0": 0.0, "r1": 10.0, "z0": -20.0, "z1": 20.0,
                "lc": 2.0}]
    path = os.path.join(tempfile.gettempdir(), "emstudio_smoke_axi.geo")
    gmsh_axi.write_geo(regions, path)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert 'Physical Surface("billet", 1)' in text, ".geo missing body group"
    assert 'Physical Curve("router"' in text, ".geo missing boundary group"
    try:
        os.remove(path)
    except OSError:
        pass

    # Palace backend imports headless + writes a valid box .geo / config
    from emstudio.meshing import gmsh_box
    from emstudio.post import eigenmodes  # noqa: F401
    from emstudio.solvers.palace import parser as pparser  # noqa: F401
    from emstudio.solvers.palace import runner, writer  # noqa: F401

    box_geo = os.path.join(tempfile.gettempdir(), "emstudio_smoke_box.geo")
    gmsh_box.write_geo((40.0, 20.0, 60.0), box_geo)
    with open(box_geo, "r", encoding="utf-8") as fh:
        btext = fh.read()
    assert 'Physical Volume("interior", 1)' in btext, "box .geo missing volume group"
    assert 'Physical Surface("pec_walls", 2)' in btext, "box .geo missing wall group"
    cfg = writer.build_eigenmode_config("cavity.msh", n_modes=6, target_ghz=4.0)
    assert cfg["Model"]["L0"] == 1e-3, "Palace L0 must be 1e-3 for a mm mesh"
    assert cfg["Boundaries"]["PEC"]["Attributes"] == [2], "PEC must be attribute 2"
    # adaptive mesh refinement (AMR) is OPT-IN: default off = NO Model.Refinement
    # key (byte-identical to the pre-AMR writer); on = a Model-level Refinement
    # block with Nonconformal true (mandatory for gmsh tets).
    assert "Refinement" not in cfg["Model"], \
        "default eigenmode config must NOT carry Model.Refinement (no regression)"
    cfg_amr = writer.build_eigenmode_config("cavity.msh", n_modes=6, target_ghz=4.0,
                                            mesh_refinement=2, refinement_tol=0.01)
    ref = cfg_amr["Model"].get("Refinement")
    assert ref and ref["MaxIts"] == 2 and ref["Nonconformal"] is True \
        and ref["Tol"] == 0.01 and ref["UpdateFraction"] == 0.7, \
        "AMR on must emit Model.Refinement with MaxIts + Nonconformal true"
    assert "Refinement" not in writer.build_driven_config("wg.msh", 8.0, 12.0, 0.5)["Model"], \
        "default driven config must NOT carry Model.Refinement (no regression)"
    assert "Refinement" in writer.build_driven_config(
        "wg.msh", 8.0, 12.0, 0.5, mesh_refinement=1)["Model"], \
        "driven AMR on must emit Model.Refinement (AMR works for driven too)"
    try:
        os.remove(box_geo)
    except OSError:
        pass

    # Palace driven (waveguide) writer/mesher: 4 physical groups, WavePort config
    wg_geo = os.path.join(tempfile.gettempdir(), "emstudio_smoke_wg.geo")
    gmsh_box.write_geo_waveguide((22.86, 10.16, 30.0), wg_geo, axis=2)
    with open(wg_geo, "r", encoding="utf-8") as fh:
        wtext = fh.read()
    for grp in ('Physical Surface("port1", 2)', 'Physical Surface("port2", 3)',
                'Physical Surface("walls", 4)'):
        assert grp in wtext, "waveguide .geo missing " + grp
    dcfg = writer.build_driven_config("wg.msh", 8.0, 12.0, 0.5)
    assert dcfg["Problem"]["Type"] == "Driven"
    wp = dcfg["Boundaries"]["WavePort"]
    assert wp[0]["Excitation"] == 1 and "Excitation" not in wp[1], \
        "driven: port 1 excited, port 2 passive"
    # adaptive fast frequency sweep is OPT-IN: default off = flat direct sweep,
    # on = a Samples grid + AdaptiveTol (Palace interpolates the dense band).
    assert "Samples" not in dcfg["Solver"]["Driven"], \
        "default driven sweep must be the flat direct block (no regression)"
    dfast = writer.build_driven_config("wg.msh", 8.0, 12.0, 0.1, fast_sweep=True)
    dsw = dfast["Solver"]["Driven"]
    assert "Samples" in dsw and "MinFreq" not in dsw and dsw["AdaptiveTol"] == 1e-3 \
        and dsw["Samples"][0]["Type"] == "Linear", "fast sweep must emit Samples+AdaptiveTol"
    try:
        os.remove(wg_geo)
    except OSError:
        pass

    # Palace coax (lumped-port) mesher/writer: annulus .geo with 4 physical
    # groups, LumpedPort config (driven "+R" port + passive port)
    from emstudio.meshing import gmsh_coax

    coax_geo = os.path.join(tempfile.gettempdir(), "emstudio_smoke_coax.geo")
    gmsh_coax.write_geo_coax(0.5, 1.15, 20.0, coax_geo)
    with open(coax_geo, "r", encoding="utf-8") as fh:
        ctext = fh.read()
    for name in ('"dielectric"', '"pec"', '"port1"', '"port2"'):
        assert name in ctext, "coax .geo missing physical group " + name
    assert "Abs( Boundary" in ctext, "coax .geo lost the Abs() wall selection"
    ccfg = writer.build_lumped_coax_config("coax.msh", 2.0, 6.0, 1.0, 0.5, 1.15)
    assert ccfg["Problem"]["Type"] == "Driven", "coax config not Driven"
    lp = ccfg["Boundaries"]["LumpedPort"]
    assert lp[0]["Excitation"] == lp[0]["Index"] and "Excitation" not in lp[1], \
        "coax: port 1 driven (Excitation==Index), port 2 passive"
    assert lp[0]["Direction"] == "+R", "coax lumped port must be radial (+R)"
    assert "Samples" not in ccfg["Solver"]["Driven"], "coax default sweep must be flat"
    ccfg_fast = writer.build_lumped_coax_config("coax.msh", 2.0, 6.0, 0.1, 0.5, 1.15,
                                                fast_sweep=True)
    assert "Samples" in ccfg_fast["Solver"]["Driven"], "coax fast sweep must emit Samples"
    assert abs(writer.coax_z0(0.5, 1.15, 1.0) - 49.94) < 0.1, "coax Z0 formula drift"
    try:
        os.remove(coax_geo)
    except OSError:
        pass

    # Palace general-3D BREP mesher: tags any imported solid's interior=1 and
    # its whole boundary=2 (PEC), so build_eigenmode_config is reused unchanged.
    from emstudio.meshing import gmsh_brep

    dummy_brep = os.path.join(tempfile.gettempdir(), "emstudio_smoke_dummy.brep")
    open(dummy_brep, "w").close()  # write_geo_brep only needs the path to exist
    brep_geo = os.path.join(tempfile.gettempdir(), "emstudio_smoke_brep.geo")
    gmsh_brep.write_geo_brep(dummy_brep, brep_geo, elem_mm=4.0)
    with open(brep_geo, "r", encoding="utf-8") as fh:
        btext = fh.read()
    assert "Merge" in btext, "BREP .geo missing Merge"
    assert 'Physical Volume ("interior", 1)' in btext, "BREP .geo missing interior=1"
    assert 'Physical Surface("pec_walls", 2)' in btext, "BREP .geo missing pec_walls=2"
    assert "Abs(Boundary" in btext, "BREP .geo lost the Abs(Boundary) wall selection"
    # general-BREP DRIVEN mesher: same solid tagged with TWO ports + PEC walls
    # (reuses the box waveguide's attr numbers so the driven config is unchanged)
    drv_geo = os.path.join(tempfile.gettempdir(), "emstudio_smoke_brepdrv.geo")
    gmsh_brep.write_geo_brep_driven(dummy_brep, drv_geo, axis=2,
                                    bbox_mm=(0, 0, 0, 20.0, 10.0, 40.0), elem_mm=4.0)
    with open(drv_geo, "r", encoding="utf-8") as fh:
        dtext = fh.read()
    assert 'Physical Surface("port1", 2)' in dtext, "BREP-driven .geo missing port1=2"
    assert 'Physical Surface("port2", 3)' in dtext, "BREP-driven .geo missing port2=3"
    assert 'Physical Surface("walls", 4)' in dtext, "BREP-driven .geo missing walls=4"
    assert "walls() -= port1();" in dtext and "Abs( Boundary" in dtext, \
        "BREP-driven .geo must subtract ports from Abs(Boundary) walls"
    for _p in (dummy_brep, brep_geo, drv_geo):
        try:
            os.remove(_p)
        except OSError:
            pass

    # Quasi-static frequency-validity guard: silent when electrically small,
    # warns (never blocks) when the structure is >= lambda/10.
    from emstudio.solvers import validity

    assert validity.electrical_size_warning(100e3, 0.10) is None, \
        "guard must stay silent for a 10 cm coil at 100 kHz (quasi-static)"
    _w = validity.electrical_size_warning(40e9, 0.10)
    assert _w and "quasi-static" in _w, \
        "guard must warn for a 10 cm structure at 40 GHz"
    assert abs(validity.axi_model_max_dim_m(
        {"bodies": [{"r0": 0.0, "r1": 50.0, "z0": -20.0, "z1": 20.0}]}) - 0.10) < 1e-9, \
        "axi max-dim must be the 100 mm diameter"

    # electrically-small (VLF/LF) antenna analytics: short-monopole Rr formula
    import math as _math

    from emstudio.antenna import small_antenna as _sa

    _lam = 299792458.0 / 30e6
    _m = _sa.short_monopole(_lam * 0.1, 30e6)
    assert abs(_m["radiation_resistance_ohm"] - 40 * _math.pi ** 2 * 0.01) < 1e-9, \
        "short-monopole Rr formula drift"

    # element-family recommender (Element Designer E2): deterministic rules,
    # Qt-free — 24 kHz must route to the small-antenna family
    from emstudio.antenna import element_picker as _ep

    _rec = _ep.recommend_element({"f0_hz": 24e3})
    assert _rec["candidates"][0]["family"] == "small_antenna", \
        "24 kHz must route to the small-antenna family"


def _nec2_ground_cards():
    """NEC2 ground writer: free space byte-identical; ground/base-feed opt-in works."""
    from emstudio.solvers.nec2 import writer

    class _S:  # minimal stand-in for the SolverNEC2 object
        def __init__(self, **kw):
            self.__dict__.update(kw)

    # default / free space -> GE 0, no GN, inactive (byte-identical to pre-ground)
    ge, gn, active = writer._ground_cards(_S(GroundType="None (free space)"))
    assert ge == "GE 0" and gn is None and active is False, "free-space ground drift"
    # a free-space (vertical, off-ground) wire keeps the CENTER feed
    w = {"nseg": 11, "p1": (0, 0, 1.0), "p2": (0, 0, -1.0)}
    assert writer._feed_segment(w, False) == 6, "free-space feed must be centered"
    # perfect ground -> GE 1 / GN 1
    ge, gn, active = writer._ground_cards(_S(GroundType="Perfect (PEC image)"))
    assert ge == "GE 1" and gn == "GN 1" and active, "perfect ground cards wrong"
    # finite ground -> GE 1 / GN 2 with eps,sigma
    ge, gn, active = writer._ground_cards(
        _S(GroundType="Finite (Sommerfeld)", GroundEpsilonR=13.0,
           GroundConductivity=0.005))
    assert ge == "GE 1" and gn.startswith("GN 2,0,0,0,13,0.005") and active, \
        "finite ground GN card wrong: {0}".format(gn)
    # a grounded monopole (base at z=0) is fed at its BASE segment
    mono = {"nseg": 21, "p1": (0, 0, 0.0), "p2": (0, 0, 300.0)}
    assert writer._feed_segment(mono, True) == 1, "grounded monopole must feed at base"


def _cosite_engine():
    """Co-site interference engine: IMD products + intercept-point level (Qt-free)."""
    from emstudio.cosite import interference as ci

    prods = ci.intermod_products([150e6, 151e6], max_order=3)
    lo = [p for p in prods if abs(p["freq_hz"] - 149e6) < 1.0]
    assert lo and lo[0]["order"] == 3, "two-tone 2f1-f2 (149 MHz) product missing"
    # classic: two -10 dBm tones, IP3 +30 -> IMD3 -90 dBm
    assert abs(ci.imd_level_dbm(lo[0], [-10.0, -10.0], 30.0) - (-90.0)) < 1e-9, \
        "IMD3 intercept-point level drift"
    site = [ci.Radio("A", tx_freq_hz=150e6, tx_power_dbm=40.0),
            ci.Radio("B", tx_freq_hz=151e6, tx_power_dbm=40.0),
            ci.Radio("C", rx_freq_hz=149e6, rx_bw_hz=25e3, rx_sens_dbm=-110.0,
                     rx_blocking_dbm=20.0)]
    rep = ci.analyze_site(site, isolation_db=30.0, junction_ip3_dbm=20.0)
    assert any(abs(h["freq_hz"] - 149e6) < 1e3 for h in rep["imd"]), \
        "analyze_site missed the 2f1-f2 IMD hit on the victim receiver"
    # the frequency-plan optimizer clears the (frequency-fixable) IMD hit
    opt = ci.optimize_frequency_plan(site, tunable=[0, 1],
                                     candidates=[150e6, 155e6, 160e6],
                                     isolation_db=30.0, junction_ip3_dbm=20.0)
    assert opt["cost"] < ci.plan_cost(rep), "optimizer did not improve the plan"


def _propagation_engine():
    """Point-to-point propagation models (Qt-free): FSPL + knife-edge + plane-earth."""
    from emstudio.coverage import propagation as pr

    assert abs(pr.free_space_path_loss_db(1000.0, 300e6) - 81.98) < 0.05, "FSPL drift"
    assert abs(pr.knife_edge_loss_db(0.0) - 6.02) < 0.1, "knife-edge J(0) drift"
    assert pr.knife_edge_loss_db(-1.0) == 0.0, "clear path must be 0 dB"
    # plane-earth d^4: doubling the range adds 12 dB
    a = pr.plane_earth_loss_db(1000.0, 10.0, 10.0)
    b = pr.plane_earth_loss_db(2000.0, 10.0, 10.0)
    assert abs((b - a) - 12.041) < 1e-2, "plane-earth d^4 law drift"
    assert abs(pr.field_strength_dbuv_m(1000.0, 1000.0) - 104.77) < 0.1, \
        "field-strength relation drift"
    res = pr.terrain_profile_loss([(0.0, 0.0), (1000.0, 50.0), (2000.0, 0.0)],
                                  ht_m=20.0, hr_m=20.0, freq_hz=300e6)
    assert res["edge_index"] == 1 and res["diffraction_db"] > 15.0, \
        "terrain single-edge diffraction drift"
    # multi-edge diffraction (Deygout recursive + Epstein-Peterson) vs NTIA TR-26-580
    _F15 = 299792458.0 / 0.2  # lambda 0.2 m = 1500 MHz
    _p2 = [(0.0, 0.0), (1600.0, 240.0), (4000.0, 200.0), (5600.0, 0.0)]
    assert abs(pr.deygout_multiedge_loss_db(_p2, 0, 0, _F15) - 73.292) < 0.1, \
        "Deygout multi-edge drift (NTIA Case 23)"
    assert abs(pr.epstein_peterson_loss_db(_p2, 0, 0, _F15) - 70.517) < 0.2, \
        "Epstein-Peterson multi-edge drift (NTIA Case 23)"
    _p1 = [(0.0, 0.0), (1600.0, 240.0), (5600.0, 0.0)]
    assert abs(pr.deygout_multiedge_loss_db(_p1, 0, 0, _F15)
               - pr.terrain_profile_loss(_p1, 0, 0, _F15)["diffraction_db"]) < 1e-9, \
        "multi-edge single obstacle must equal the shipped single-edge loss"
    assert abs(pr.bullington_loss_db(_p2, 0, 0, _F15) - 43.168) < 0.1, \
        "Bullington equivalent-edge drift (NTIA Case 23)"
    # empirical Okumura-Hata / COST-231 (verified example + clutter ordering)
    from emstudio.coverage import empirical as emp

    assert abs(emp.okumura_hata_loss_db(4000.0, 900e6, 100.0, 2.0) - 137.048) < 0.05, \
        "Okumura-Hata verified-example drift"
    _lu = emp.okumura_hata_loss_db(5000.0, 900e6, 30.0, 1.5, "urban")
    _ls = emp.okumura_hata_loss_db(5000.0, 900e6, 30.0, 1.5, "suburban")
    _lo = emp.okumura_hata_loss_db(5000.0, 900e6, 30.0, 1.5, "open")
    assert _lu > _ls > _lo, "Hata clutter ordering broken"
    assert abs(emp.cost231_hata_loss_db(1000.0, 1.8e9, 30.0, 1.5, metropolitan=True)
               - 139.197) < 0.02, "COST-231-Hata drift"
    # §2 Cable Designer coax engine: RG-58 anchors (Belden 8262)
    from emstudio.wire import coax as _cx

    assert abs(_cx.coax_z0_ohm(0.418e-3, 1.4605e-3, 2.25) - 50.0) < 0.15, \
        "coax RG-58 Z0 drift"
    assert abs(_cx.velocity_factor(2.25) - 2.0 / 3.0) < 1e-9, "coax VF drift"
    assert abs(_cx.capacitance_f_m(0.418e-3, 1.4605e-3, 2.25) * 1e12 - 101.0) < 2.0, \
        "coax capacitance drift"
    # §2 phase A UI slice: RG presets + single-wire (ops=[]) litz reuse
    assert any(k.startswith("RG-58") for k in _cx.PRESETS) \
        and any(k.startswith("RG-142") for k in _cx.PRESETS), "coax PRESETS missing"
    _p58 = [_cx.PRESETS[k] for k in _cx.PRESETS if k.startswith("RG-58")][0]
    assert abs(_cx.analyze(_p58["a_m"], _p58["b_m"], _p58["eps_r"],
                           _p58["tan_delta"])["z0_ohm"] - 50.0) < 0.15, \
        "RG-58 preset Z0 drift"
    from emstudio.wire import litz as _lz
    from emstudio.wire import units as _un

    _w = _lz.LitzConstruction(strand_diameter_m=_un.awg_to_m(10), ops=[])
    assert abs(_w.rdc_per_meter() * 1e3 - 3.277) < 0.02, "solid AWG-10 Rdc drift"
    assert abs(_w.ac_factor(1e6)
               - _lz.round_wire_ac_factor(1e6, _w.strand_radius_m)) < 1e-12, \
        "single-wire Rac/Rdc must equal the exact Kelvin solution"
    # §2 phase B: twisted pair — Cat6 primary anchor + the degrees control
    from emstudio.wire import twisted_pair as _tp

    assert abs(_tp.z0_diff_ohm(1.029e-3, 0.573e-3, 1.0 / 0.70 ** 2)
               - 99.90) < 0.6, "Cat6 twisted-pair Z0 drift"
    _th = _tp.twist_angle_deg(100.0, 0.8e-3)
    _zd = _tp.z0_diff_ohm(0.8e-3, 0.5e-3, _tp.eps_effective(4.0, _th, "film"))
    assert abs(_zd - 89.03) < 0.05 and abs(_zd - 94.90) > 1.0, \
        "twisted-pair theta must be DEGREES (89.03), not the radians bug (94.90)"
    # §2 phase C: bundle packing — the exact 7-hex anchor
    from emstudio.wire import bundle as _bn

    _pl, _re = _bn.pack_and_center([1.0] * 7)
    assert abs(_re - 3.0) < 1e-6, "7-hex packing drift"
    assert all(
        (( _pl[i][0] - _pl[j][0]) ** 2 + (_pl[i][1] - _pl[j][1]) ** 2) ** 0.5
        >= _pl[i][2] + _pl[j][2] - 1e-8
        for i in range(7) for j in range(i + 1, 7)), "bundle members overlap"
    # §2 phase C cont.: coupling — Paul ribbon L anchor + crosstalk MNE
    from emstudio.wire import coupling as _cp

    _MIL = 25.4e-6
    _L = _cp.widesep_l_matrix([(0.0, 0.0), (50 * _MIL, 0.0), (100 * _MIL, 0.0)],
                              [7.5 * _MIL] * 3)
    assert abs(_L[0][0] * 1e6 - 0.75885) < 5e-4, "coupling wide-sep L drift"
    _xt = _cp.crosstalk_weak(0.5077e-6, 18.716e-12, 2.0)
    assert abs(_xt["mne_s"] - 5.5449e-9) / 5.5449e-9 < 0.005, \
        "Paul crosstalk MNE drift"
    # §2 extras: insulated-bundle C via MoM reproduces Paul problem 5.15
    from emstudio.wire import electrostatics as _es

    _ct = _es.bundle_c_mom([(0.0, 0.0), (50 * _MIL, 0.0), (100 * _MIL, 0.0)],
                           [7.5 * _MIL] * 3, er=3.5, wall=10 * _MIL, ref=1)
    assert abs(_ct["c_tl"][0][0] * 1e12 - 24.98) < 0.01 \
        and abs(_ct["c_tl"][0][1] * 1e12 + 6.266) < 0.01, \
        "insulated-bundle MoM C drift (Paul 5.15 24.98/-6.266 pF/m)"
    # §2 extras: diff-pair mixed-mode — oracle closed form + eq 4-3 parity
    from emstudio.wire import mixed_mode as _mmx

    _L4 = _cp.widesep_l_matrix(
        [(0.0, 0.0), (0.0, 10e-3), (2e-3, 10e-3),
         (20e-3, 10e-3), (22e-3, 10e-3)], [0.5e-3] * 5)
    _dq = _mmx.diff_pair_coupling(_L4, _cp.c_matrix_from_l(_L4))
    assert abs(_dq["mdd"] + 2.010067171e-9) / 2.010067171e-9 < 1e-6, \
        "diff-pair Mdd drift (full-MTL oracle closed form)"
    assert _mmx.xi_twp(226) == 0 and _mmx.xi_twp(225) == 1 \
        and _mmx.xi_swp(226) == 226, "eq 4-3/4-6 twist parity algebra broken"
    # §2 thermal slice: IEC 60287-2-1 T1 worked example (full precision —
    # the printed 0.816 is a truncation) + IEC 60949 adiabatic J0
    from emstudio.wire import thermal as _th

    assert abs(_th.layer_t_k_m_w(1.0 / 0.182, 33.7e-3, 26.02e-3)
               - 0.8166061944818844) < 1e-9, "IEC 60287-2-1 T1 drift"
    assert abs(_th.adiabatic_current_a(1.0, 1.0, 90.0, 250.0, "Cu")
               - 143.08) < 0.05 \
        and abs(_th.k_factor(90.0, 250.0, "Cu") - 143.0) < 0.5, \
        "IEC 60949 adiabatic constants drift"
    # §6-D P.1546-6: the vendored WP3K reference engine imports headlessly
    # (lazy matplotlib) and the wrapper computes + enforces validity
    from emstudio.coverage import p1546 as _p15

    _e, _l = _p15.field_strength_dbuv_m(600.0, 50.0, 75.0, 10.0, 50.0)
    assert 0.0 < _e < 120.0 and _l > 50.0, "P.1546 wrapper spot value insane"
    try:
        _p15.field_strength_dbuv_m(10.0, 50.0, 75.0, 10.0, 50.0)
        raise AssertionError("P.1546 wrapper must reject 10 MHz (no "
                             "extrapolation)")
    except ValueError:
        pass
    # §6-D P.1812-6: the vendored engine imports WITHOUT the ITU digital maps
    # (lazy load) and the delta-Bullington wrapper computes + guards validity
    from emstudio.coverage import p1812 as _p18

    _db = _p18.delta_bullington_intermediates(
        [0.0, 5.0, 10.0], [0.0, 120.0, 0.0], 0.0, 4, 10.0, 10.0, 0.6)
    assert _db["ld50_db"] > 0.0 and _db["lbulla"] > 0.0, \
        "delta-Bullington spot value insane"
    try:
        _p18.check_validity(10.0, 50.0, 100.0)
        raise AssertionError("P.1812 wrapper must reject 10 MHz")
    except ValueError:
        pass
    # legal notices: DISCLAIMER.md ships, and generated artifacts carry the
    # disclaimer (spec/BOM exports + PDF report footer)
    from emstudio import legal as _lg

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.isfile(os.path.join(_root, "DISCLAIMER.md")), \
        "DISCLAIMER.md missing"
    assert "verify" in _lg.SHORT_DISCLAIMER and "WARRANT" in \
        _lg.SHORT_DISCLAIMER.upper(), "short disclaimer text malformed"
    assert "DISCLAIMER" in _lz.LitzConstruction(
        strand_diameter_m=_un.awg_to_m(10), ops=[]).spec_markdown(), \
        "wire spec export lost the disclaimer footer"
    from emstudio.report import pdf_report as _pr

    assert _lg.SHORT_DISCLAIMER in _pr.FOOTER, "PDF footer lost the disclaimer"


def _coverage_engine():
    """Coverage §6-B engine (Qt-free): geodesy + .hgt round-trip + heatmap + KML."""
    import math as _math
    import tempfile

    import numpy as np

    from emstudio.coverage import geodesy as geo
    from emstudio.coverage import groundwave as gw
    from emstudio.coverage import heatmap, kml, terrain
    from emstudio.coverage import propagation as pr

    # geodesy: 1 deg of longitude at the equator, bearing due east
    assert abs(geo.haversine_m(0, 0, 0, 1) - 111195.0) < 400.0, "haversine drift"
    assert abs(geo.initial_bearing_deg(0, 0, 0, 1) - 90.0) < 1e-6, "bearing drift"

    # .hgt round-trip: a small tile with a central bump, bilinear at the peak
    size = 61
    step = 1.0 / (size - 1)
    arr = np.zeros((size, size), dtype=">i2")
    arr[size // 2, size // 2] = 100  # peak at tile centre (lat 0.5, lon 0.5)
    path = os.path.join(tempfile.gettempdir(), "emstudio_smoke_N00E000.hgt")
    # name encodes the SW corner; write then read back through the engine
    hgt = os.path.join(tempfile.gettempdir(), "N00E000.hgt")
    arr.tofile(hgt)
    tile = terrain.read_hgt(hgt)
    assert tile.data.shape == (size, size), "hgt shape wrong"
    assert abs(tile.lat_max - 1.0) < 1e-9 and abs(tile.lon_min) < 1e-9, "hgt corner wrong"
    assert tile.elevation(0.5, 0.5) > 50.0, "hgt bilinear lost the central peak"
    assert _math.isnan(tile.elevation(9.0, 9.0)), "hgt out-of-tile must be NaN"
    for _p in (path, hgt):
        try:
            os.remove(_p)
        except OSError:
            pass

    # heatmap: a cleared omni link degenerates EXACTLY to EIRP - FSPL
    cov = heatmap.coverage_grid(40.0, -100.0, 200.0, 300e6, tx_power_dbm=50.0,
                                dem=None, radius_m=20000.0, n=21, peak_gain_dbi=0.0,
                                rx_height_m=200.0, k_factor=1e12)
    ci = 10
    d = geo.haversine_m(40.0, -100.0, cov.lats[ci], cov.lons[-1])
    exp = 50.0 - pr.free_space_path_loss_db(d, 300e6)
    assert abs(cov.prx_dbm[ci, -1] - exp) < 0.05, \
        "heatmap cleared-omni cell != EIRP - FSPL ({0} vs {1})".format(
            cov.prx_dbm[ci, -1], exp)

    # LF/MF ground-wave (ITU-R P.368): the ITU Handbook worked example
    p_gw, _ = gw.numerical_distance(20e3, 2e6, 15.0, 5e-5)
    assert abs(p_gw - 26.0) < 1.5, "ground-wave numerical distance drift: {0}".format(p_gw)
    assert abs(gw.attenuation_factor(p_gw) - 0.0226) < 0.003, "ground-wave |A| drift"
    assert abs(gw.field_strength_dbuv_m(1000.0, 1e6, 70.0, 5.0) - 109.54) < 1.0, \
        "P.368 300 mV/m-at-1-km reference drift"
    # Millington reciprocity (land<->sea swap gives the same field)
    _ls = gw.millington_field_dbuv_m([(50e3, 5.0, 1e-3), (50e3, 70.0, 5.0)], 1e6)
    _sl = gw.millington_field_dbuv_m([(50e3, 70.0, 5.0), (50e3, 5.0, 1e-3)], 1e6)
    assert abs(_ls - _sl) < 1e-6, "Millington reciprocity broken"

    # vendored ITU-R P.452-18 / P.2001-6 reference engines: must import
    # WITHOUT the ITU digital maps (they are never bundled), enforce their
    # validity ranges, and the map installer must know where maps live.
    # (Full official-set replays live in tests/validation/{p452,p2001}.py.)
    from emstudio.coverage import itu_maps as _im
    from emstudio.coverage import p2001 as _p2001w
    from emstudio.coverage import p452 as _p452w
    from emstudio.vendor.py2001 import P2001 as _P2001  # noqa: F401
    from emstudio.vendor.py452 import P452 as _P452  # noqa: F401

    assert _im.maps_dir(), "itu_maps.maps_dir() empty"
    assert "install_p452_maps" in _im.missing_message("P452"), \
        "P452 missing-maps message lost its install instructions"
    for _bad in (lambda: _p452w.check_validity(60.0, 20.0),
                 lambda: _p452w.check_validity(1.0, 80.0),
                 lambda: _p2001w.check_validity(60.0, 50.0, 100.0),
                 lambda: _p2001w.check_validity(1.0, 0.0, 100.0)):
        try:
            _bad()
            raise AssertionError("P.452/P.2001 validity must be enforced")
        except ValueError:
            pass

    # P.368-10 spherical earth (the LFMF port): the same 1-km CMF reference,
    # far more loss than flat earth at 1000 km, and the <10 kHz hard-stop.
    # scipy-less FreeCAD bundles skip this block (the spherical engine needs
    # scipy.special; requirements.txt says so, and the workbench + flat model
    # keep working without it) — full numerics live in tests/validation/lfmf.py.
    from emstudio.coverage import lfmf as _lfmf
    if _lfmf.HAVE_SCIPY:
        _e1 = gw.spherical_field_strength_dbuv_m(1000.0, 1e4, 70.0, 5.0)
        assert abs(_e1 - 109.54) < 0.1, \
            "P.368-10 1-km CMF reference drift: {0}".format(_e1)
        _ef = gw.field_strength_dbuv_m(1000e3, 1e6, 13.0, 5e-3)
        _es = gw.spherical_field_strength_dbuv_m(1000e3, 1e6, 13.0, 5e-3)
        assert _es < _ef - 30.0, \
            "spherical earth must out-attenuate flat at 1000 km"
        try:
            gw.spherical_field_strength_dbuv_m(100e3, 9e3, 70.0, 5.0)
            raise AssertionError("<10 kHz must hard-stop (P.684 band)")
        except ValueError:
            pass

    # multi-station D/U: incoherent power-sum combine (+3.0103 dB) + the two-gate
    # classify + the source-tagged protection-ratio library (§6 phase C cont.)
    from emstudio.coverage import multistation as ms

    _e60 = np.array([[60.0]])
    assert abs(ms.combine_fields_dbuv_m([_e60, _e60])[0, 0] - 63.0103) < 1e-3, \
        "D/U field power-sum combine drift (two equal fields must add 10log10(2))"
    _cls, _du = ms.classify(np.array([[50.0]]), np.array([[38.0]]), 41.0, 15.27)
    assert _cls[0, 0] == ms.INTERFERENCE_LIMITED and abs(_du[0, 0] - 12.0) < 1e-9, \
        "two-gate D/U classify drift"
    assert ms.PROTECTION_RATIOS["FM co-channel (FCC 73.215)"][0] == 20.0 \
        and ms.PROTECTION_RATIOS["AM/MF co-channel (FCC / ITU Region 2)"][0] == 26.0, \
        "protection-ratio reference library drift"

    # KML GroundOverlay xml is well-formed (N>S, E>W, href, placemark)
    import xml.etree.ElementTree as ET

    xml = kml.kml_groundoverlay_xml(1.0, 0.0, 2.0, 0.5, "coverage.png",
                                    tx_lat=0.5, tx_lon=1.0)
    root = ET.fromstring(xml)
    ns = "{http://www.opengis.net/kml/2.2}"
    box = root.find(".//{0}LatLonBox".format(ns))
    assert box is not None, "KML missing LatLonBox"
    assert float(box.find(ns + "north").text) > float(box.find(ns + "south").text), \
        "KML north must exceed south"


def _nec2_filename_length():
    """nec2c aborts on a long input filename — pass basenames, not abs paths.

    nec2c has a fixed-size input-filename buffer and exits 255 with
    "Input file name too long - aborting". Absolute paths fit on Linux
    (/tmp/emstudio_nec2_xxxx/case.nec, ~36 chars) and do NOT on macOS, where
    tempfile yields /var/folders/<hash>/T/... and the same deck runs ~80.
    Reported 2026-08-02 from macOS 26.5 by a user who had built nec2c himself,
    so the run reached the solver and died there.

    Two checks: the helper behaves, and no call site bypasses it.
    """
    import re
    from emstudio.solvers.base import nec2_argv

    argv = nec2_argv("/usr/local/bin/nec2c",
                     "/var/folders/9k/8lz3v_hd6yq5h4y7_4x2f3rw0000gn/T/"
                     "emstudio_nec2_a1b2c3d4/case.nec",
                     "/var/folders/9k/8lz3v_hd6yq5h4y7_4x2f3rw0000gn/T/"
                     "emstudio_nec2_a1b2c3d4/case.out")
    assert argv[1:] == ["-i", "case.nec", "-o", "case.out"], argv
    for a in argv[1:]:
        assert os.sep not in a, "nec2 argv must carry basenames only: %r" % a
    # a deck and output in different directories cannot both be reached from
    # one cwd — that must be refused loudly, not silently truncated
    try:
        nec2_argv("nec2c", "/tmp/a/case.nec", "/tmp/b/case.out")
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched deck/out directories must raise")

    # No call site may build the argv by hand again.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = []
    pat = re.compile(r'\[\s*[\w.]+\s*,\s*"-i"')
    for dirpath, dirs, files in os.walk(os.path.join(root, "emstudio")):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            # solvers/base.py DEFINES the helper; its own return line is the
            # one legitimate place the argv is built literally.
            if os.path.relpath(full, root) == os.path.join(
                    "emstudio", "solvers", "base.py"):
                continue
            with open(full, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if pat.search(line):
                        bad.append("%s:%d" % (os.path.relpath(full, root), i))
    assert not bad, ("nec2 argv built by hand instead of via nec2_argv() at: %s"
                     % ", ".join(bad))


def _nec_parser_reads_both_dialects():
    """The NEC2 parser must read nec2c AND nec2++ output.

    `nec2++` has been in the nec2 backend's ``executables`` tuple since the
    backend was written, so EMStudio has always claimed to support it — but the
    frequency regex required a colon, and nec2++ writes an equals sign:

        nec2c   FREQUENCY : 3.0000E+02 MHz
        nec2++  FREQUENCY=  3.0000E+02 MHZ

    A user with nec2++ installed therefore got a solver that DETECTED fine and
    then died at "impedance row before any FREQUENCY line". Measured 2026-08-03
    against a real nec2++ build: with the separator accepted, it reproduces
    nec2c to 4 significant figures on the shipped dipole gate (296.283 vs
    296.287 MHz, both 71.92 ohm).

    The banner assertion matters as much as the two positive ones: the same
    output contains a "--------- FREQUENCY --------" rule, and relaxing the
    separator to optional would match it and parse a frequency of nothing.
    """
    import tempfile as _tempfile
    from emstudio.solvers.nec2 import parser as necparser

    # The deck's CM comments are ECHOED into the output ABOVE the real frequency
    # line, so a comment mentioning a frequency is the actual hazard here — not
    # the banner rule, which carries no "MHz" and can never match. A user whose
    # deck says "CM Yagi FREQUENCY 144 MHz" must still get 300 MHz.
    comment = ("                     - - - - COMMENTS - - - -\n"
               "                     Yagi FREQUENCY 144 MHz design\n\n")
    header = (comment +
              "                        --------- FREQUENCY --------\n"
              "{0}\n\n"
              "                        --------- ANTENNA INPUT PARAMETERS ---------\n"
              "  TAG   SEG       VOLTAGE (VOLTS)         CURRENT (AMPS)         "
              "IMPEDANCE (OHMS)        ADMITTANCE (MHOS)     POWER\n"
              "    1    11  1.0000E+00  0.0000E+00  1.3128E-02 -1.7160E-03  "
              "7.4894E+01  9.7899E+00  1.3128E-02 -1.7160E-03  6.5639E-03\n")
    dialects = {
        "nec2c":  "                                FREQUENCY : 3.0000E+02 MHz",
        "nec2++": "                               FREQUENCY=  3.0000E+02 MHZ",
    }
    for name, freq_line in dialects.items():
        fd, path = _tempfile.mkstemp(suffix=".out")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(header.format(freq_line))
            res = necparser.parse_output(path, z0=50.0)
            assert len(res.freq) == 1, \
                "{0}: expected 1 frequency, got {1}".format(name, len(res.freq))
            assert abs(res.freq[0] - 300e6) < 1e3, \
                "{0}: frequency {1} != 300 MHz".format(name, res.freq[0])
            assert abs(res.zin[0].real - 74.894) < 0.01, \
                "{0}: R {1} != 74.894".format(name, res.zin[0].real)
            assert abs(res.zin[0].imag - 9.7899) < 0.01, \
                "{0}: X {1} != 9.7899".format(name, res.zin[0].imag)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    # Assert the regex property directly. Scope, stated honestly: end-to-end the
    # comment's value would be OVERWRITTEN by the real FREQUENCY line that always
    # follows it, so this is a defensive property of the pattern rather than a
    # demonstrated wrong answer. It is kept because it costs nothing and the
    # alternative invites a whole class of prose matching.
    # (An earlier version asserted the "--------- FREQUENCY --------" banner rule
    # instead. That can never match — it carries no "MHz" — so the assertion
    # could not fail. Mutation testing is the only reason that was caught.)
    assert not necparser._FREQ_RE.search("Yagi FREQUENCY 144 MHz design"), \
        "a frequency mentioned in a deck COMMENT must not parse as the run frequency"


def _version_probe_rejects_help_text():
    """`_probe_version` must return a version, or nothing — never help text.

    nec2's `version_args` was `-h`, with a comment asserting nec2c had no version
    flag. It does (`-v` -> "nec2c 1.3"). The help output's third line is

        -v: print nec2c version number and exit.

    which carries a digit (in "nec2c") and says neither "usage" nor "option", so
    the probe returned it verbatim and Solver Setup displayed that whole sentence
    as the installed version. Measured on the M1 build host, 2026-08-03.

    Both halves matter. Asserting only that help is rejected would pass if
    `_probe_version` were mutated to always return "" — so a real version string
    must still come back.
    """
    import stat as _stat
    import tempfile as _tempfile
    from emstudio.setup import solvers

    made = []

    def _fake(body):
        if os.name == "nt":
            # A shebang script cannot execute on native Windows, and cmd.exe
            # would eat the help text's <angle brackets> if echoed — so the
            # fake is a batch file that types a sidecar text file verbatim.
            fd, txt = _tempfile.mkstemp(suffix=".txt")
            with os.fdopen(fd, "w") as fh:
                fh.write(body + "\n")
            fd, path = _tempfile.mkstemp(suffix=".cmd")
            with os.fdopen(fd, "w") as fh:
                fh.write('@type "{0}"\r\n'.format(txt))
            made.extend([txt, path])
            return path
        fd, path = _tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as fh:
            fh.write("#!/bin/sh\ncat <<'EOF'\n{0}\nEOF\n".format(body))
        os.chmod(path, os.stat(path).st_mode | _stat.S_IEXEC)
        made.append(path)
        return path

    help_like = _fake(
        "usage: nec2c [-i<input-file-name>] [-o<output-file-name>]\n"
        "       -h: print this usage information and exit.\n"
        "       -v: print nec2c version number and exit.")
    real_like = _fake("nec2c 1.3")
    try:
        got = solvers._probe_version(help_like, ())
        assert got == "", (
            "help text was reported as a version: %r" % got)
        got = solvers._probe_version(real_like, ())
        assert got == "nec2c 1.3", (
            "a real version line must still be returned, got %r" % got)
    finally:
        for p in made:
            try:
                os.unlink(p)
            except OSError:
                pass


def _win_guided_install_contract():
    """Guided Windows installs: plans well-formed; the pipeline installs + probes.

    The structural half runs on every platform (CI is Linux, so this is what
    guards a bad URL from shipping): every plan names a real backend, an https
    URL and a proof file. The behavioral half is Windows-only, because the
    feature is nt-only by design: a fake archive served over file:// goes
    through the REAL ``run_win_install`` — download, extract, nested-topdir
    discovery, move-into-place — and then ``find_backend`` must locate the
    result through the managed-dir probe with PATH stripped and the install
    root redirected to a temp dir. Asserting the VALUE (the plan table exists)
    instead of this behaviour is the exact mistake the 0.77.4 probe gate made.
    """
    import shutil as _shutil
    import tempfile as _tempfile
    import zipfile as _zipfile

    from emstudio.setup import solvers

    assert solvers.WIN_INSTALL_PLANS, "the guided Windows install table is empty"
    for key, plan in solvers.WIN_INSTALL_PLANS.items():
        assert key in solvers.BACKENDS, "plan for unknown backend %r" % key
        assert plan["url"].startswith("https://"), "non-https URL for %r" % key
        assert plan["proof"] and plan["estimate"], "incomplete plan for %r" % key
        if plan.get("runtime_dlls"):
            assert plan.get("runtime_pkgs"), (
                "runtime_dlls without runtime_pkgs for %r" % key)
        # A backend that HAS a button must say so where the user looks. The
        # Windows hint is the only text shown in the Details column, and it
        # used to describe a manual build for backends that now install
        # themselves — stale guidance reads as "there is no button".
        hint = solvers.WINDOWS_HINTS.get(key, "")
        assert "Install button" in hint, (
            "%r has a guided install but its WINDOWS_HINTS text never mentions "
            "the Install button" % key)
        # SELF-HOSTED plans carry licence obligations that upstream ones do not:
        # we are the distributor. nec2++ is GPL-2, so section 3 requires the
        # complete corresponding source to be offered alongside the binary, and
        # a source zip from a DIFFERENT release than the binary is not that.
        # Tying the two tags together is what makes "bump both" enforceable
        # rather than a comment someone has to remember.
        if solvers.is_self_hosted(plan):
            offer = plan.get("source_offer", "")
            assert offer.startswith("https://"), (
                "self-hosted %r ships no source_offer — we are the distributor "
                "here, so the source offer is not optional" % key)
            bin_tag = solvers._release_tag(plan["url"])
            src_tag = solvers._release_tag(offer)
            assert bin_tag and src_tag, (
                "cannot read release tags for %r (%r / %r)" % (key, bin_tag, src_tag))
            assert bin_tag == src_tag, (
                "%r binary is published under tag %r but its source offer points "
                "at %r — a rebuild left the source zip behind"
                % (key, bin_tag, src_tag))
    if os.name != "nt":
        return

    tmp_root = _tempfile.mkdtemp(prefix="emstudio_wininst_")
    fake_zip = os.path.join(tmp_root, "fake.zip")
    with _zipfile.ZipFile(fake_zip, "w") as zf:
        zf.writestr("Fake-Elmer-1.0/bin/ElmerSolver.exe", "@echo off\r\n")
        zf.writestr("Fake-Elmer-1.0/bin/ElmerGrid.exe", "@echo off\r\n")
    plan = {
        "estimate": "test",
        "url": "file:///" + fake_zip.replace("\\", "/"),
        "proof": os.path.join("bin", "ElmerSolver.exe"),
    }
    orig_root = solvers.win_install_root
    orig_path = os.environ.get("PATH", "")
    orig_env = os.environ.pop("EMSTUDIO_ELMER", None)
    lines = []
    try:
        solvers.win_install_root = lambda: os.path.join(tmp_root, "managed")
        os.environ["PATH"] = ""
        info = solvers.run_win_install("elmer", line_callback=lines.append,
                                       _plan=plan)
        assert info.found and info.source == "probe", (
            "guided install not found via the managed-dir probe: %r" % (info,))
        assert info.path.startswith(os.path.join(tmp_root, "managed")), info.path
        assert os.path.isfile(os.path.join(
            tmp_root, "managed", "elmer", "bin", "ElmerGrid.exe")), (
            "sibling files were not moved with the tree")
        assert any("installed to" in ln for ln in lines), "no progress lines"
        # ElmerGrid must resolve as a SIBLING of the managed ElmerSolver —
        # the bare name missed ElmerGrid.exe on Windows (caught live
        # 2026-08-04: solver detected, companion "not found" from the same
        # bin directory).
        from emstudio.solvers.elmer import runner as _elmer_runner
        grid = _elmer_runner.find_elmergrid()
        assert grid.startswith(os.path.join(tmp_root, "managed")), (
            "ElmerGrid not resolved beside the managed ElmerSolver: %r" % grid)
    finally:
        solvers.win_install_root = orig_root
        os.environ["PATH"] = orig_path
        if orig_env is not None:
            os.environ["EMSTUDIO_ELMER"] = orig_env
        _shutil.rmtree(tmp_root, ignore_errors=True)


def _install_text_platform_segregation():
    """Install instructions must be platform-pure: no Linux commands on Windows.

    A Windows user must never see a standalone `sudo apt install` line or a
    Linux source-build recipe mixed in with Windows guidance (that confusing
    mix was reported 2026-07-06). Forces two backends missing and renders each
    platform via a monkeypatched os.name / sys.platform.

    macOS was added 2026-08-01 after a forum report: `os.name` is "posix" on a
    Mac, so it fell through the Windows check into the Debian branch and Solver
    Setup told Mac users to run `sudo apt install`. The Windows half of this
    check passed the whole time — testing two of three platforms is what let
    it ship.
    """
    import sys as _sys
    from emstudio.setup import solvers

    real_detect = solvers.detect_all
    real_os = os.name
    real_platform = _sys.platform
    linux_only = ["sudo apt install -y", "./update_openEMS", "make fasthenry", "-fcommon"]
    try:
        def fake_detect():
            res = real_detect()
            for key in ("openems", "nec2"):  # a source-build + an apt backend
                res[key] = solvers.SolverInfo(solvers.BACKENDS[key], "")
            return res
        solvers.detect_all = fake_detect

        os.name = "nt"
        plan = solvers.install_plan()
        blob = solvers.install_report_text() + "\n".join(m["steps"] for m in plan["missing"])
        assert plan["apt_line"] == "", "Windows must not offer an apt line"
        leaked = [s for s in linux_only if s in blob]
        assert not leaked, "Linux commands leaked into Windows install text: {0}".format(leaked)
        assert "WSL2" in blob, "Windows guidance should mention WSL2"

        os.name = "posix"
        _sys.platform = "linux"
        plan = solvers.install_plan()
        rpt = solvers.install_report_text()
        assert plan["apt_line"].startswith("sudo apt install"), "Linux should offer apt"
        assert plan["brew_line"] == "", "Linux must not offer a brew line"
        assert "WSL2" not in rpt, "WSL2 (Windows-only) must not appear on Linux"

        # macOS: posix like Linux, but apt does not exist there.
        _sys.platform = "darwin"
        plan = solvers.install_plan()
        rpt = solvers.install_report_text()
        blob = rpt + "\n".join(m["steps"] for m in plan["missing"])
        assert plan["apt_line"] == "", "macOS must not offer an apt line"
        assert "sudo apt" not in blob, \
            "apt commands leaked into the macOS install text"
        assert "WSL2" not in blob, "WSL2 (Windows-only) must not appear on macOS"
        # What THIS machine happens to have installed must not decide whether
        # the check can fail, so force a known-missing prerequisite. Without
        # this the whole macOS branch of install_plan() could be deleted and
        # every other assertion here would still pass (proved by mutation).
        # Pin BOTH inputs: which backends are missing AND which prereqs are
        # missing. Forcing only the prereqs was not enough — install_plan also
        # folds in each missing backend's own brew_package, so on a machine
        # WITHOUT gmsh the line became "brew install vtk gmsh" and on one WITH
        # gmsh it was "brew install vtk". That shipped, red, four times: it
        # passed here and failed every CI run, because CI has no gmsh. An
        # assertion whose result depends on the host is not a gate — which is
        # the exact lesson this block was written to enforce.
        real_prereqs = solvers.check_prereqs
        real_detect_p = solvers.detect_all
        try:
            vtk = [p for p in solvers.BACKENDS["openems"].prerequisites
                   if p.brew == "vtk"][0]
            solvers.check_prereqs = lambda b: [(vtk, False)]
            # exactly one missing backend, and one with no brew_package of its
            # own, so the only formula in the line comes from the prereq
            assert solvers.BACKENDS["openems"].brew_package == "", \
                "this check assumes openems has no brew formula"
            solvers.detect_all = lambda: {
                "openems": solvers.SolverInfo(solvers.BACKENDS["openems"], "")}
            forced = solvers.install_plan()
            assert forced["brew_line"] == "brew install vtk", (
                "macOS must roll missing prerequisites into ONE brew command, got: %r"
                % forced["brew_line"])
            assert forced["apt_line"] == "", "still no apt on macOS"
        finally:
            solvers.check_prereqs = real_prereqs
            solvers.detect_all = real_detect_p

        assert (not plan["brew_line"]) or plan["brew_line"].startswith("brew install"), \
            "a non-empty brew line must be a brew command: " + plan["brew_line"]
        gmsh_hint = solvers.install_hint(solvers.BACKENDS["gmsh"])
        assert "brew install gmsh" in gmsh_hint, \
            "macOS gmsh guidance should use Homebrew, got: " + gmsh_hint
        assert "apt" not in gmsh_hint, "apt leaked into macOS gmsh guidance"
        assert "macOS" in rpt, "the macOS report should say so"
        assert "xcode-select" in rpt, \
            "macOS needs the compiler step; the source builds are useless without it"
        # nproc is coreutils — absent on a stock Mac. The Palace build step must
        # not depend on it.
        for plan_steps in (solvers.BUILD_PLANS.get("palace") or {}).get("steps", []):
            cmd = " ".join(plan_steps[1])
            assert "$(nproc)" not in cmd, \
                "build step uses bare $(nproc), which fails on macOS: " + cmd

        # FastHenry is K&R-era C, and each compiler generation promotes another
        # of its legacy diagnostics to a hard error:
        #   Apple clang 15 / GCC 14 -> implicit-int + implicit-function-declaration
        #                              (~20 errors in induct.c; reported by a user
        #                               on macOS 26.5 arm64, 2026-08-01)
        #   Apple clang 21          -> return-mismatch (2 more; measured on the M1
        #                              build host 2026-08-03, AFTER the first fix
        #                              had shipped and was believed complete)
        #
        # This check used to ENUMERATE the flags it knew about, which is why the
        # second wave got through: the list it tested was the list that was
        # already right. It now reads solvers.FASTHENRY_REQUIRED_FLAGS, so adding
        # a compiler's flag to that tuple makes every surface below required to
        # carry it — and forgetting one surface is what turns this red.
        required = solvers.FASTHENRY_REQUIRED_FLAGS
        # Raise this with the tuple. It is a ratchet, so leaving it at the old
        # count lets a flag be dropped again in silence — which is the exact
        # failure mode this whole check exists for. 5 as of 0.79.0 (-std=gnu17,
        # for GCC 15's C23 default).
        assert len(required) >= 5, \
            "FASTHENRY_REQUIRED_FLAGS shrank; flags are appended, never removed"
        # The single definition and the assertion list must agree, or the
        # constant silently stops meaning anything.
        for flag in required:
            assert flag in solvers.FASTHENRY_CFLAGS, \
                "FASTHENRY_CFLAGS is missing a required flag: " + flag

        fh_cmds = [" ".join(st[1])
                   for st in (solvers.BUILD_PLANS.get("fasthenry") or {}).get("steps", [])
                   if "make fasthenry" in " ".join(st[1])]
        assert fh_cmds, "no FastHenry compile step found to check"
        # All THREE user-facing surfaces, not just the two checked before: the
        # macOS hint was missing from this list and could have drifted silently.
        surfaces = [("build step", c) for c in fh_cmds]
        surfaces.append(("manual_hint", solvers.BACKENDS["fasthenry"].manual_hint))
        surfaces.append(("MACOS_HINTS", solvers.MACOS_HINTS["fasthenry"]))
        for label, text in surfaces:
            for flag in required:
                assert flag in text, \
                    "FastHenry {0} is missing {1}: {2}".format(label, flag, text)

        # FOURTH SURFACE, found 2026-08-04: README.md carried its own copy of the
        # flags and had drifted by THREE of them, because the three checks above
        # never looked at a doc. The fix is not "add README to the list" -- a doc
        # that restates the flags will drift again. It must POINT at the constant
        # instead, so this asserts no shipped doc spells a flag list out at all.
        docs_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for doc in ("README.md", "HELP.md", "docs/USER_MANUAL.md"):
            path = os.path.join(docs_root, doc)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            assert "-DFOUR" not in body, (
                "{0} spells out the FastHenry CFLAGS. That list grows with every "
                "compiler generation and has already drifted once -- point at "
                "solvers.FASTHENRY_CFLAGS instead of restating it.".format(doc))

        # A backend with no Homebrew formula is ALWAYS source-built on macOS, so
        # it must declare where it lands — PATH cannot be relied on (FreeCAD from
        # Finder does not inherit it) and MACOS_PROBE_DIRS only covers the three
        # package-manager prefixes. Elmer and nec2 both declared NOTHING until
        # 2026-08-03: Elmer built correctly into ~/opt/elmer and Detect Solvers
        # still said MISSING. This is stated as the invariant rather than as
        # "elmer must have extra_dirs", because the point is that the NEXT
        # formula-less backend must not repeat it.
        for _k, _b in solvers.BACKENDS.items():
            if "No Homebrew formula" in solvers.MACOS_HINTS.get(_k, ""):
                assert _b.extra_dirs, (
                    "{0} has no Homebrew formula, so macOS users source-build it "
                    "— it must declare extra_dirs or it is undiscoverable".format(_k))

        # Homebrew's bin dirs must be PROBED, not merely mentioned in prose.
        # FreeCAD launched from Finder does not inherit the shell PATH, so
        # `brew install gmsh` can succeed while detection still says MISSING.
        # 0.77.1 shipped that as advice to the user; probing is the actual fix.
        assert "/opt/homebrew/bin" in solvers.MACOS_PROBE_DIRS, \
            "Apple Silicon Homebrew bin dir must be probed"
        assert "/usr/local/bin" in solvers.MACOS_PROBE_DIRS, \
            "Intel Homebrew bin dir must be probed"
        assert solvers._platform_dirs() == solvers.MACOS_PROBE_DIRS, \
            "macOS probe dirs are not being applied on darwin"
        _sys.platform = "linux"
        assert solvers._platform_dirs() == (), \
            "macOS probe dirs must NOT leak onto Linux"
        _sys.platform = "darwin"

        # ...and the SEARCH must actually consult them. Asserting the constant
        # exists is not enough: deleting `_platform_dirs()` from the probe loop
        # left every other assertion here green (proved by mutation). Plant a
        # binary in a fake Homebrew dir and require find_backend to locate it.
        import shutil as _sh
        import stat as _stat
        import tempfile as _tf
        _probe_dir = _tf.mkdtemp(prefix="emstudio-brewprobe-")
        _real_dirs = solvers.MACOS_PROBE_DIRS
        _real_backends = dict(solvers.BACKENDS)
        try:
            fake_exe = "emstudio-probe-canary"
            assert _sh.which(fake_exe) is None, "canary must not be on PATH"
            planted = os.path.join(_probe_dir, fake_exe)
            with open(planted, "w") as fh:
                fh.write("#!/bin/sh\nexit 0\n")
            os.chmod(planted, os.stat(planted).st_mode | _stat.S_IEXEC)
            solvers.MACOS_PROBE_DIRS = (_probe_dir,)
            solvers.BACKENDS["_canary"] = solvers.Backend(
                key="_canary", label="canary", method="none",
                executables=(fake_exe,), version_args=("--version",))
            info = solvers.find_backend("_canary")
            assert info.found and info.source == "probe", (
                "a binary in a Homebrew-style dir was not found on macOS — the "
                "probe loop is ignoring MACOS_PROBE_DIRS (found=%r source=%r)"
                % (info.found, info.source))
        finally:
            solvers.MACOS_PROBE_DIRS = _real_dirs
            solvers.BACKENDS.clear()
            solvers.BACKENDS.update(_real_backends)
            _sh.rmtree(_probe_dir, ignore_errors=True)

        # Every Homebrew formula we name must be one someone actually verified
        # exists. `tinyxml` was added from memory, shipped, and is not in
        # homebrew-core (only tinyxml2, a different API) — which is precisely
        # the failure the macOS fix existed to stop: a confident command that
        # cannot run. Offline check against a curated set; verify with
        # formulae.brew.sh/api/formula/<name>.json before adding to it.
        named = set()
        for b in solvers.BACKENDS.values():
            named.update(b.brew_package.split())
            for pq in b.prerequisites:
                named.update(pq.brew.split())
        unverified = named - solvers.VERIFIED_BREW_FORMULAE
        assert not unverified, (
            "unverified Homebrew formula name(s): %s — curl "
            "formulae.brew.sh/api/formula/<name>.json, then add to "
            "VERIFIED_BREW_FORMULAE" % sorted(unverified))
        # ...and the prose hints must not smuggle one past that check.
        for key, hint in solvers.MACOS_HINTS.items():
            for tok in hint.split():
                if tok in ("tinyxml", "tinyxml2"):
                    raise AssertionError(
                        "MACOS_HINTS[%r] names %s as if installable; TinyXML v1 "
                        "is not in homebrew-core" % (key, tok))
    finally:
        solvers.detect_all = real_detect
        os.name = real_os
        _sys.platform = real_platform


def _axi_revolution_tolerance():
    """The full-revolution guard accepts tessellation-shrunk boxes, rejects arcs.

    Regression for the GUI bbox bug (2026-07-06): Shape.BoundBox is
    tessellation-dependent and sits ~0.1 mm inside the true radius under the
    GUI, so a tight tolerance rejected valid coil rings for GUI users while the
    freecadcmd gates (exact box) stayed green.
    """
    from emstudio.solvers.elmer.model import AxiModelError, _check_full_revolution

    # a valid 51 mm ring whose displayed bbox shrank ~0.1 mm (facet chords)
    _check_full_revolution(51.0, (51.0, 50.90, 50.98, 50.98), "ring")  # must not raise
    # a partial revolution (half ring: one extent collapses toward the axis)
    try:
        _check_full_revolution(51.0, (51.0, 0.0, 51.0, 51.0), "half")
    except AxiModelError:
        pass
    else:
        raise AssertionError("partial revolution was not rejected")


# --- FreeCAD-dependent checks ----------------------------------------------
def _examples_open():
    """Every shipped example opens and contains a real EMStudio analysis.

    These are the first thing a new user double-clicks, and they are the one
    shipped artifact with no other regression net: a document that opens empty,
    or fails to open at all, reads as "this workbench is broken" before the user
    has run anything. Regenerate with ``freecadcmd tools/gen_examples.py``.
    """
    import glob

    import FreeCAD

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = sorted(glob.glob(os.path.join(here, "examples", "*.FCStd")))
    assert paths, "examples/ contains no .FCStd — run tools/gen_examples.py"
    for path in paths:
        name = os.path.basename(path)
        doc = FreeCAD.openDocument(path)
        try:
            assert len(doc.Objects) >= 2, \
                "{0} opened with {1} object(s)".format(name, len(doc.Objects))
            assert any(getattr(o, "EMStudioType", "") == "EMStudio::Analysis"
                       for o in doc.Objects), \
                "{0} has no EMStudio::Analysis — it would open as inert geometry".format(name)
        finally:
            FreeCAD.closeDocument(doc.Name)
    return "{0} examples open with an analysis".format(len(paths))


def _analysis_roundtrip():
    import FreeCAD

    from emstudio.objects import (analysis, coil, material, ports, query,
                                  solver_objs, transmission_line)

    doc = FreeCAD.newDocument("emstudio_smoke")
    obj = analysis.makeAnalysis(doc)
    assert obj is not None, "makeAnalysis returned None"
    assert obj.EMStudioType == "EMStudio::Analysis"
    assert obj.isDerivedFrom("App::DocumentObjectGroupPython"), "analysis is not a group"

    # data-model members survive alongside the container
    _mat = material.makeMaterial(doc, obj, category="Dielectric")
    # k(T) coefficient (v0.52) exists on the material, defaults to constant k
    assert "ThermalConductivityTempCoeff" in _mat.PropertiesList \
        and abs(_mat.ThermalConductivityTempCoeff) < 1e-12, \
        "Material ThermalConductivityTempCoeff missing or non-zero default"
    # σ(T) coefficient (v0.53) exists on the material, defaults to constant σ
    assert "ConductivityTempCoeff" in _mat.PropertiesList \
        and abs(_mat.ConductivityTempCoeff) < 1e-12, \
        "Material ConductivityTempCoeff missing or non-zero default"
    # B-H curve lists (v0.54) exist and default EMPTY (= linear material)
    assert "BHCurveB" in _mat.PropertiesList and "BHCurveH" in _mat.PropertiesList \
        and not list(_mat.BHCurveB) and not list(_mat.BHCurveH), \
        "Material BHCurveB/BHCurveH missing or non-empty default"
    ports.makeLumpedPort(doc, obj)
    solver_objs.makeSolverNEC2(doc, obj)
    solver_elmer = solver_objs.makeSolverElmer(doc, obj)
    # radiation BC (v0.51): the emissivity/radiation-temp properties exist
    # and default OFF (convection-only, byte-identical decks)
    assert "SurfaceEmissivity" in solver_elmer.PropertiesList \
        and abs(solver_elmer.SurfaceEmissivity) < 1e-12, \
        "SolverElmer SurfaceEmissivity missing or non-zero default"
    assert "RadiationTemperature" in solver_elmer.PropertiesList, \
        "SolverElmer RadiationTemperature property missing"
    # analysis-type enum (v0.54 static DC + v0.56 3-D): harmonic default
    _modes = solver_elmer.getEnumerationsOfProperty("AnalysisType")
    assert solver_elmer.AnalysisType == "Harmonic (AC)" \
        and "Static (DC)" in _modes \
        and "3-D Magnetostatic (DC)" in _modes, \
        "SolverElmer AnalysisType missing, wrong default, or missing modes"
    solver_pal = solver_objs.makeSolverPalace(doc, obj)
    solver_oe = solver_objs.makeSolverOpenEMS(doc, obj)
    # coax lumped-port analysis type (v0.17.0) is available on the Palace solver
    assert "Driven S-parameters (coax)" in \
        solver_pal.getEnumerationsOfProperty("AnalysisType"), \
        "SolverPalace missing the coax AnalysisType"
    coil_obj = coil.makeCoil(doc, obj, turns=42, current_a=2.5)
    # transmission line (v0.61, LPDA feeder): maker args land; LineLength
    # defaults to 0 (auto distance) and the shunt admittances to zero
    tl_obj = transmission_line.makeTransmissionLine(doc, obj, z0_ohm=73.0,
                                                    crossed=True)
    assert tl_obj.EMStudioType == "EMStudio::TransmissionLine"
    assert abs(float(tl_obj.Z0.getValueAs("Ohm")) - 73.0) < 1e-9
    assert tl_obj.Crossed is True
    assert abs(float(tl_obj.LineLength.getValueAs("m"))) < 1e-12, \
        "TransmissionLine LineLength must default to 0 (auto distance)"
    assert all(abs(getattr(tl_obj, p)) < 1e-12
               for p in ("Y1Real", "Y1Imag", "Y2Real", "Y2Imag")), \
        "TransmissionLine shunt admittances must default to 0"
    assert len(query.get_materials(obj)) == 1
    assert len(query.get_ports(obj)) == 1
    assert len(query.get_coils(obj)) == 1
    assert len(query.get_transmission_lines(obj)) == 1
    assert len(query.get_solvers(obj)) == 4
    # trace-aware mesh mode (v0.16.0) defaults to Auto — a no-op unless an MSL
    # port is present, so antenna analyses are unaffected.
    assert solver_oe.MicrostripMeshMode == "Auto", "MicrostripMeshMode default changed"
    assert coil_obj.Turns == 42
    assert abs(float(coil_obj.Current.getValueAs("A")) - 2.5) < 1e-9
    f1, f2, npts = analysis.Analysis.freq_range_hz(obj)
    assert f1 < f2 and npts > 1, "bad default frequency sweep"

    # Save/reload round-trip through a temp file.
    import tempfile

    path = os.path.join(tempfile.gettempdir(), "emstudio_smoke.FCStd")
    doc.saveAs(path)
    FreeCAD.closeDocument(doc.Name)
    doc2 = FreeCAD.openDocument(path)
    restored = doc2.Objects[0]
    assert restored.EMStudioType == "EMStudio::Analysis", "type lost on reload"
    assert restored.Proxy is not None, "proxy not reattached on reload"
    FreeCAD.closeDocument(doc2.Name)
    try:
        os.remove(path)
    except OSError:
        pass


def _no_console_windows_on_spawn():
    """Every subprocess spawn passes creationflags (CREATE_NO_WINDOW).

    FreeCAD.exe is a GUI-subsystem process, so each console-subsystem child
    it spawns flashes a NEW black console over the viewport unless the spawn
    says creationflags=procutil.CREATE_NO_WINDOW. One NEC2 solve was three
    such windows; a user read it as "something is broken" (AJ, 2026-08-07).
    The constant is 0 off Windows, so there is no branching at call sites --
    which is what makes this statically checkable: EVERY spawn must carry it.
    """
    import glob
    import re

    bad = []
    for p in glob.glob(os.path.join(_ROOT, "emstudio", "**", "*.py"),
                       recursive=True):
        src = open(p, encoding="utf-8").read()
        for m in re.finditer(
                r"subprocess\.(Popen|run|check_output|check_call|call)\(",
                src):
            depth, i = 1, m.end()
            while depth and i < len(src):
                depth += {"(": 1, ")": -1}.get(src[i], 0)
                i += 1
            if "creationflags" not in src[m.start():i]:
                bad.append("{0}:{1}".format(
                    os.path.relpath(p, _ROOT),
                    src[:m.start()].count(chr(10)) + 1))
    assert not bad, (
        "subprocess spawns without creationflags (each pops a console "
        "window on Windows under the GUI): " + ", ".join(bad))


def _icons_parse_as_xml():
    import xml.dom.minidom as minidom

    from emstudio.resources import ICON_DIR

    icons = [f for f in os.listdir(ICON_DIR) if f.endswith(".svg")]
    assert icons, "no SVG icons found in resources/icons"
    for name in icons:
        path = os.path.join(ICON_DIR, name)
        minidom.parse(path)  # raises on malformed XML


def _gui_registration_contract():
    """Exercise InitGui.py registration against a recorder standing in for FreeCADGui.

    freecadcmd's FreeCADGui is a stub without addWorkbench/addCommand/Workbench, so we
    inject minimal recorders, exec the real InitGui.py, run Initialize(), and assert the
    workbench + commands register correctly. This covers the whole GUI wiring path except
    the actual on-screen render (which needs a display and is confirmed by a human).
    """
    import FreeCADGui

    from emstudio import commands

    reg = {"commands": [], "workbenches": [], "toolbars": [], "menus": []}

    class _FakeBase:
        def appendToolbar(self, name, cmds):
            reg["toolbars"].append((name, list(cmds)))

        def appendMenu(self, name, cmds):
            reg["menus"].append((name, list(cmds)))

    # Save any real attrs so we restore the stub afterwards.
    saved = {k: getattr(FreeCADGui, k, None) for k in
             ("Workbench", "addCommand", "addWorkbench", "addModule", "doCommand")}
    try:
        FreeCADGui.Workbench = _FakeBase
        FreeCADGui.addCommand = lambda name, obj: reg["commands"].append((name, obj))
        FreeCADGui.addWorkbench = lambda wb: reg["workbenches"].append(wb)
        FreeCADGui.addModule = lambda m: None
        FreeCADGui.doCommand = lambda c: None

        initgui = os.path.join(_ROOT, "InitGui.py")
        with open(initgui, "r", encoding="utf-8") as fh:
            code = fh.read()
        # Deliberately do NOT provide __file__: real FreeCAD does not guarantee it when
        # exec'ing InitGui.py, so the workbench must never rely on it. This namespace
        # mirrors the worst case.
        ns = {"__name__": "InitGui"}
        exec(compile(code, initgui, "exec"), ns)  # noqa: S102 (executing our own file)

        assert reg["workbenches"], "InitGui did not call addWorkbench"
        wb = reg["workbenches"][0]
        assert wb.GetClassName() == "Gui::PythonWorkbench", "wrong GetClassName"
        assert type(wb).MenuText == "EMStudio", "wrong MenuText"
        assert os.path.isfile(type(wb).Icon), "workbench Icon path missing: " + str(type(wb).Icon)

        wb.Initialize()
        got_cmds = {name for name, _ in reg["commands"]}
        expected = {c for c in commands.ALL_COMMANDS if c != "Separator"}
        assert got_cmds == expected, (
            "registered commands {0} != ALL_COMMANDS {1}".format(got_cmds, expected)
        )
        assert reg["toolbars"], "no toolbar appended"
        assert reg["menus"], "no menu appended"
        # every registered command must live in exactly one toolbar/menu group,
        # and no group may reference an unregistered command (no orphans).
        grouped = commands.grouped_commands()
        assert len(grouped) == len(set(grouped)), "a command is in two groups"
        assert set(grouped) == expected, (
            "COMMAND_GROUPS must cover exactly the registered commands "
            "(missing {0}, extra {1})".format(expected - set(grouped),
                                               set(grouped) - expected))
        # a toolbar (+ submenu) was appended per group
        assert len(reg["toolbars"]) == len(commands.COMMAND_GROUPS), \
            "expected one toolbar per command group"

        # Every command exposes a valid GetResources() with an existing icon.
        for _, cmd in reg["commands"]:
            res = cmd.GetResources()
            for key in ("Pixmap", "MenuText", "ToolTip"):
                assert key in res, "command missing GetResources key: " + key
            assert os.path.isfile(res["Pixmap"]), "command icon missing: " + res["Pixmap"]
    finally:
        for k, v in saved.items():
            if v is None:
                try:
                    delattr(FreeCADGui, k)
                except AttributeError:
                    pass
            else:
                setattr(FreeCADGui, k, v)


def main():
    _log("EMStudio smoke test")
    _log("-------------------")
    check("import emstudio package", _import_package)
    check("version.py matches package.xml", _version_matches_package_xml)
    check("package.xml keeps <subdirectory>./</subdirectory>", _package_xml_subdirectory_guard)
    check("solver detection runs", _solver_detection_runs)
    check("Elmer zip layout wires ELMER_Fortran_COMPILER (UDFs on Windows)",
          _elmer_env_fortran_compiler)
    check("gate runner tees to FreeCAD.Console (a failing gate must say "
          "why)", _gate_runner_tees_to_console)
    check("gate battery forces UTF-8 (the console must not decide a "
          "gate's verdict)", _battery_forces_utf8)
    check("openEMS python resolver: FreeCAD-free, both venv layouts",
          _openems_python_resolver)
    check("openEMS gates SKIP a missing backend (never fail)",
          _openems_gates_skip_without_openems)
    check("icons parse as valid XML/SVG", _icons_parse_as_xml)
    check("no spawn can flash a console window (creationflags everywhere)",
          _no_console_windows_on_spawn)
    check("installer build plans well-formed (no sudo)", _installer_build_plans)
    check("install text is platform-segregated (Win/Linux)", _install_text_platform_segregation)
    check("version probe returns a version, never help text",
          _version_probe_rejects_help_text)
    check("guided Windows install: plans + install/probe pipeline",
          _win_guided_install_contract)
    check("NEC2 parser reads both nec2c and nec2++ output",
          _nec_parser_reads_both_dialects)
    check("nec2 argv uses basenames (macOS temp paths overflow nec2c)",
          _nec2_filename_length)
    check("Elmer magnetics backend imports headless + writes .geo", _elmer_backend_headless)
    check("Elmer 3-D WhitneyAV backend headless (.geo + .sif)", _elmer3d_backend_headless)
    check("axisymmetric full-revolution tolerance (GUI bbox guard)", _axi_revolution_tolerance)
    check("NEC2 ground-card writer (free-space byte-identical + monopole base feed)",
          _nec2_ground_cards)
    check("co-site interference engine (IMD products + intercept-point level)",
          _cosite_engine)
    check("propagation engine (FSPL + knife-edge + plane-earth + field strength)",
          _propagation_engine)
    check("coverage engine (geodesy + .hgt DEM + heatmap + KML)", _coverage_engine)

    have_freecad = False
    try:
        import FreeCAD  # noqa: F401

        have_freecad = True
    except Exception:
        _log("  skip - FreeCAD not importable; skipping document checks")

    if have_freecad:
        check("EM Analysis create + save/reload round-trip", _analysis_roundtrip)
        check("GUI registration contract (InitGui + commands)", _gui_registration_contract)
        check("shipped examples open and carry an EMStudio analysis",
              _examples_open)

    _log("-------------------")
    if _failures:
        _log("SMOKE TEST FAILED: {0} failure(s)".format(len(_failures)))
        return 1
    _log("SMOKE TEST PASSED")
    return 0


# Decide whether to auto-run. Three launch paths, one rule:
#   * plain ``python tests/smoke.py``      -> __name__ == "__main__"
#   * ``freecadcmd tests/smoke.py``        -> __name__ == "smoke" (module basename),
#                                             FreeCAD present, pytest absent
#   * pytest collection                    -> do NOT auto-run (let test_* wrappers call)
# freecadcmd does not honor ``sys.exit`` codes reliably, so on failure we also raise
# to guarantee a non-zero process exit for CI.
_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
_INVOKED_DIRECTLY = (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST)

if _INVOKED_DIRECTLY:
    _rc = main()
    if _rc != 0:
        raise SystemExit("EMStudio smoke test failed ({0} failure(s))".format(len(_failures)))
    sys.exit(0)
