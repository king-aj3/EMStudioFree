# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the solved OpenFOAM field reaches the 3-D view.

Pass: exit 0 and 'FOAM-VTK-EXPORT GATE PASSED'.

WHY THIS EXISTS. The convection solve distils a whole temperature and velocity
field into ONE number, the bundle factor. Until now that field was unreachable:
the case directory was created inside `solve_bundle_factor` and never returned,
so the moment the solve finished nobody could find it. A number you cannot go
back and look at is a number you have to take on faith — and this one is
surprising often enough (a trefoil is ~25 % off the Churchill-Chu correlation,
in the unsafe direction) that being able to open it matters.

Three properties, all pure logic — FAST tier, no solver run:

* the case directory SURVIVES the solve, on both the uniform and mixed paths;
* the newest time directory is picked by TIME, not by lexical name
  (`_1000` sorts before `_300`, so a lexical max returns an old field —
  silently, since both are valid files);
* the converter REFUSES clearly when there is no case, rather than producing
  an empty view.
"""
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _fake_vtk_tree(case, times):
    """A case with VTK output for each of ``times``."""
    for t in times:
        d = os.path.join(case, "VTK", "case_%s" % t)
        os.makedirs(os.path.join(d, "boundary"), exist_ok=True)
        with open(os.path.join(d, "internal.vtu"), "w") as fh:
            fh.write("<VTKFile/>")
        for patch in ("hot", "cold"):
            with open(os.path.join(d, "boundary", patch + ".vtp"), "w") as fh:
                fh.write("<VTKFile/>")


def main():
    from emstudio.solvers.base import SolverError
    from emstudio.solvers.openfoam import vtk_export
    from emstudio.wire import bundle_convection as bc

    print("EMStudio OpenFOAM VTK-export gate")

    # --- the case dir survives the solve ----------------------------------
    print(" case directory is carried out of the solve:")
    check("BundleFactor has a case_dir field",
          "case_dir" in bc.BundleFactor.__dataclass_fields__)
    check("MixedBundleFactor has a case_dir field",
          "case_dir" in bc.MixedBundleFactor.__dataclass_fields__)

    # Drive the real solve function with a stub runner: no OpenFOAM needed,
    # and it proves the plumbing rather than the dataclass default.
    class _Res:
        nu_d = 4.0
        ra_d = 1.0e5
        warnings = []

    def _runner(case_dir, case):
        return {"ok": True, "converged": True, "nu_drift": 0.0}, _Res()

    def _case_factory(**kw):
        return object()

    tmp_case = tempfile.mkdtemp(prefix="gatecase_")
    try:
        f = bc.solve_bundle_factor(
            [(0.0, 0.0), (0.03, 0.0)], 0.02, box_w=0.2, box_h=0.2,
            gradient=400.0, runner=_runner, case_factory=_case_factory,
            case_dir=tmp_case)
        check("the uniform solve returns the case it used",
              f.case_dir == tmp_case,
              "got {0!r}".format(f.case_dir))
    except Exception as exc:                    # noqa: BLE001
        check("the uniform solve returns the case it used", False, str(exc))
    finally:
        shutil.rmtree(tmp_case, ignore_errors=True)

    # --- newest-by-TIME, not by name --------------------------------------
    print(" newest time directory:")
    case = tempfile.mkdtemp(prefix="vtkpick_")
    try:
        # 1000 is the newest field but sorts BEFORE 300 lexically. A max() on
        # the name returns case_300 — a real, older field, so nothing looks
        # wrong. This is the check that catches it.
        _fake_vtk_tree(case, ["300", "1000"])
        got = vtk_export.find_internal_vtu(case)
        check("picks the latest TIME, not the lexical max",
              os.path.basename(os.path.dirname(got)) == "case_1000",
              "got {0}".format(os.path.basename(os.path.dirname(got))))
        check("boundary patches found beside it",
              len(vtk_export.boundary_vtps(case)) == 2,
              str([os.path.basename(p) for p in vtk_export.boundary_vtps(case)]))
    finally:
        shutil.rmtree(case, ignore_errors=True)

    empty = tempfile.mkdtemp(prefix="vtkempty_")
    try:
        check("no VTK output -> empty string, not a crash",
              vtk_export.find_internal_vtu(empty) == "")
        check("no VTK output -> no patches",
              vtk_export.boundary_vtps(empty) == [])
    finally:
        shutil.rmtree(empty, ignore_errors=True)

    # --- refuse clearly, never show an empty view -------------------------
    print(" the converter refuses rather than showing nothing:")
    for label, path in (("a path that does not exist",
                         os.path.join(tempfile.gettempdir(), "no_such_case_x")),
                        ("a directory that is not a case", tempfile.gettempdir())):
        raised = ""
        try:
            vtk_export.convert(path)
        except SolverError as exc:
            raised = str(exc)
        except Exception as exc:                # noqa: BLE001
            raised = "WRONG TYPE: " + type(exc).__name__
        check(label + " -> SolverError",
              bool(raised) and not raised.startswith("WRONG TYPE"),
              raised[:80])

    # --- volume + boundary patches reach the view -------------------------
    # show_in_freecad() imports FreeCAD INSIDE the function, so the module is
    # importable headless and the orchestration can be gated without a GUI.
    print(" what gets loaded, and how:")
    from emstudio.post import vtk_out

    calls = []
    real_show = vtk_out.show_in_freecad
    try:
        def _rec(path, label, doc=None, transparency=0):
            calls.append({"path": path, "label": label,
                          "transparency": transparency})
            return "obj:" + os.path.basename(path)

        vtk_out.show_in_freecad = _rec
        objs = vtk_out.show_foam_case(
            "/case/VTK/c_300/internal.vtu",
            ["/case/VTK/c_300/boundary/cold.vtp",
             "/case/VTK/c_300/boundary/hot.vtp"])
        check("volume and every patch are loaded", len(calls) == 3 and len(objs) == 3,
              "{0} calls".format(len(calls)))
        check("the VOLUME goes first", calls[0]["path"].endswith("internal.vtu"),
              "it carries the answer; the patches are context")
        check("the volume is OPAQUE", calls[0]["transparency"] == 0)
        # THE LOAD-BEARING ONE: the enclosure patch wraps the volume, so an
        # opaque patch hides the field the view exists to show.
        check("patches are TRANSPARENT",
              all(c["transparency"] >= 50 for c in calls[1:]),
              "got {0}".format([c["transparency"] for c in calls[1:]]))
        check("patches are named after their patch",
              [c["label"].rsplit("— ", 1)[-1] for c in calls[1:]] == ["cold", "hot"],
              str([c["label"] for c in calls[1:]]))

        # A patch that will not load must not cost us the field.
        calls[:] = []

        def _flaky(path, label, doc=None, transparency=0):
            calls.append(path)
            if path.endswith(".vtp"):
                raise RuntimeError("no reader for this patch")
            return "obj"

        vtk_out.show_in_freecad = _flaky
        objs = vtk_out.show_foam_case("/case/internal.vtu", ["/case/b/x.vtp"])
        check("a failed patch does not lose the field", objs == ["obj"],
              "got {0!r}".format(objs))
    finally:
        vtk_out.show_in_freecad = real_show

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("FOAM-VTK-EXPORT GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("foam-vtk-export validation failed")
    sys.exit(0)
