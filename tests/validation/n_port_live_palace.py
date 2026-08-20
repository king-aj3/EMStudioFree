# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: a LIVE 3-port solve, driven by ports the DOCUMENT declares.

Everything else about N-port is already pinned somewhere: ``n_port_smatrix``
covers the Touchstone writer and the mesh-attribute arithmetic on a synthetic
fixture, and ``declared_ports`` covers the selection logic with FreeCAD's
lookups stubbed. **Neither of them runs a solver.** Until this gate existed the
project could say N-port was *built* but not that it had ever *produced a
3-port answer*, and those are different claims.

This one closes that: a real WR-90 **T-junction**, three real waveguide mouths,
three ``EMStudio::LumpedPort`` objects naming three faces, and Palace solving
one excitation per port.

**Why a T-junction rather than a box with three faces relabelled.** A 3-port
answer is only meaningful if the structure genuinely has three ports. A box has
two ends; calling a side wall "port 3" would mesh a port onto a PEC surface and
the resulting matrix would be a fixture, not a result. The T also gives a
physical check nothing else here can: the junction must be **reciprocal** and,
being lossless and air-filled, **passive**.

⚠ **What this gate does NOT assert.** It does not claim a validated T-junction
S-matrix against published data — no reference exists in the repo for these
dimensions, and inventing a window would be exactly the "cherry-picked
headline" this project keeps catching. What it asserts is that the N-port PATH
runs end to end and that the matrix it returns obeys the physics any passive
reciprocal junction must obey. That is a real claim and a modest one.

SOLVER tier. Needs Palace, gmsh and FreeCAD (run through ``tests/run_gate.py``).
Pass: exit 0 and 'N-PORT LIVE GATE PASSED'. Auto-skips without the backends.
"""
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: WR-90, the same section the 2-port waveguide gate uses, so the cross-section
#: is one this project already trusts.
A_MM, B_MM = 22.86, 10.16
MAIN_MM = 60.0          # the through arm, along X
STUB_MM = 25.0          # the side arm, along +Y


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _skip(why):
    print("  skip  {0}".format(why))
    print("N-PORT LIVE GATE PASSED")
    return 0


def _build_tee(doc):
    """A WR-90 T: through arm along X, stub along +Y. Returns the fused solid."""
    import Part

    main = Part.makeBox(MAIN_MM, A_MM, B_MM)
    stub = Part.makeBox(A_MM, STUB_MM, B_MM)
    # Centre the stub on the through arm and start it at the main arm's +Y wall,
    # so the fuse is a clean junction rather than a coincident-face union.
    stub.translate((MAIN_MM / 2.0 - A_MM / 2.0, A_MM, 0.0))
    tee = main.fuse(stub).removeSplitter()
    obj = doc.addObject("Part::Feature", "Tee")
    obj.Shape = tee
    return obj


def _port_faces(obj):
    """The three OPEN mouths of the T, as ``(face_name, description)``.

    Found by geometry rather than by index: face numbering is an Open CASCADE
    implementation detail and reordering it would silently renumber the ports.
    A mouth is a planar face lying wholly in one of the three end planes.
    """
    want = [("x=0 (through, port 1)", lambda bb: abs(bb.XMax - 0.0) < 1e-6),
            ("x=%g (through, port 2)" % MAIN_MM,
             lambda bb: abs(bb.XMin - MAIN_MM) < 1e-6),
            ("y=%g (stub, port 3)" % (A_MM + STUB_MM),
             lambda bb: abs(bb.YMin - (A_MM + STUB_MM)) < 1e-6)]
    out = []
    for label, pred in want:
        hit = None
        for i, face in enumerate(obj.Shape.Faces, start=1):
            bb = face.BoundBox
            if pred(bb):
                hit = "Face%d" % i
                break
        out.append((hit, label))
    return out


def main():
    print("EMStudio LIVE N-port (3-port T-junction) validation gate — Palace")

    from emstudio.setup import solvers as solver_setup
    for backend in ("palace", "gmsh"):
        if not solver_setup.find_backend(backend).found:
            return _skip("%s not found — SOLVER tier" % backend)
    try:
        import FreeCAD
    except ImportError:
        return _skip("needs FreeCAD — run through tests/run_gate.py")

    import Part  # noqa: F401  (Part must import before the shape work)

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs
    from emstudio.solvers import palace
    from emstudio.solvers.palace import model as palace_model

    doc = FreeCAD.newDocument("NPortLive")
    try:
        tee = _build_tee(doc)
        doc.recompute()

        faces = _port_faces(tee)
        named = [f for f, _l in faces if f]
        check("all three mouths of the T were located by geometry",
              len(named) == 3, ", ".join("%s %s" % (f, l) for f, l in faces))
        if len(named) != 3:
            print("N-PORT LIVE GATE FAILED")
            return 1

        ana = analysis_mod.makeAnalysis(doc)
        mat = material_mod.makeMaterial(doc, ana, name="Air")
        mat.References = [(tee, "")]

        # Declare the ports the way a USER would: one per face, in order.
        for n, (face, _label) in enumerate(faces, start=1):
            port = ports_mod.makeLumpedPort(doc, ana, references=[(tee, face)])
            port.PortNumber = n
        doc.recompute()

        # --- the seam this gate exists to prove -------------------------------
        # ⚠ The sweep lives on the ANALYSIS, not the solver — the solver owns
        # only how it is solved (order, mesh, sweep strategy).
        ana.FrequencyStart = "9 GHz"
        ana.FrequencyStop = "10 GHz"
        ana.FrequencyPoints = 2

        solver = solver_objs.makeSolverPalace(doc, ana)
        solver.AnalysisType = "Driven S-parameters"
        solver.Order = 1          # coarse ON PURPOSE: this gate is about the
                                  # PATH running end to end, not about accuracy.
        solver.FullSMatrix = True         # solve EVERY column, not just port 1
        doc.recompute()

        mdl = palace_model.build_waveguide_model(ana, solver)
        check("the model carries THREE declared ports, not two inferred ones",
              mdl.get("ports") is not None and len(mdl["ports"]) == 3,
              "ports=%s" % (None if mdl.get("ports") is None
                            else len(mdl["ports"])))
        check("a declared-port model takes the BREP path (the box mesher "
              "cannot carry ports)", mdl.get("kind") == "brep",
              str(mdl.get("kind")))
        if not mdl.get("ports") or len(mdl["ports"]) != 3:
            print("N-PORT LIVE GATE FAILED")
            return 1

        # --- the live solve ---------------------------------------------------
        result = palace.run(ana, solver)
        n = len(getattr(result, "s_others", {}) or {}) + 1
        check("the solve returned a result object", result is not None)

        # ⚠ These are numpy arrays. `s11 or []` raises "truth value of an array
        # is ambiguous" -- an explicit `is None` test is required, and getting
        # it wrong crashes the gate AFTER a multi-minute solve has succeeded.
        s11 = getattr(result, "s11", None)
        n_freq = 0 if s11 is None else len(s11)
        check("port 1 reflection came back", n_freq > 0,
              "%d frequency point(s)" % n_freq)

        others = getattr(result, "s_others", {}) or {}
        check("transmission terms to the OTHER TWO ports are present",
              len(others) >= 2, "s_others keys: %s" % sorted(others)[:6])

        # PHYSICS, not a fixture: a lossless passive junction cannot emit.
        # ⚠ Passivity is PER COLUMN — sum_i |S_ij|^2 <= 1 for each drive j.
        # Summing the whole matrix instead gives ~N for a lossless N-port, and
        # the first version of this check did exactly that and "failed" at
        # 2.9985 on a solve that was perfectly correct. The measurement was
        # wrong, not the physics; this project's own rule caught it.
        full = {}
        for f_i in range(n_freq):
            full[(1, 1, f_i)] = complex(s11[f_i])
        for (i, j), col in others.items():
            for f_i in range(min(n_freq, len(col))):
                full[(i, j, f_i)] = complex(col[f_i])

        worst_col, best_total = 0.0, None
        for f_i in range(n_freq):
            for j in (1, 2, 3):
                p = sum(abs(full.get((i, j, f_i), 0j)) ** 2 for i in (1, 2, 3))
                worst_col = max(worst_col, p)
            tot = sum(abs(full.get((i, j, f_i), 0j)) ** 2
                      for i in (1, 2, 3) for j in (1, 2, 3))
            best_total = tot if best_total is None else max(best_total, tot)
        check("passivity: no COLUMN radiates more than it is fed "
              "(sum_i |S_ij|^2 <= 1)", worst_col <= 1.05,
              "worst column power %.4f" % worst_col)
        # And the whole matrix should total ~N for a lossless N-port, which is
        # a second, independent read on the same solve.
        check("losslessness: the full 3x3 totals ~3 (air-filled, PEC walls)",
              best_total is not None and abs(best_total - 3.0) < 0.15,
              "total %.4f of an ideal 3.0" % (best_total or 0.0))

        # --- the artefact a user actually takes away --------------------------
        import tempfile
        out = os.path.join(tempfile.mkdtemp(prefix="emstudio_s3p_"), "tee.s3p")
        try:
            result.write_touchstone(out)
            wrote = os.path.isfile(out) and os.path.getsize(out) > 0
        except Exception as exc:                       # noqa: BLE001
            wrote, out = False, "write_touchstone raised: %s" % exc
        check("an .s3p was written", wrote, out)
        if wrote:
            body = [l for l in open(out, encoding="utf-8").read().splitlines()
                    if l and not l.startswith(("!", "#"))]
            # ⚠ From 3 ports up Touchstone puts one matrix ROW per line, so a
            # 3-port frequency entry is THREE lines, not one. This is the
            # format defect fixed on 2026-08-20 — proven here on a real file.
            check("the .s3p has one matrix ROW per line (3 lines per "
                  "frequency), not one long line",
                  len(body) % 3 == 0 and len(body) >= 3,
                  "%d data line(s)" % len(body))
    finally:
        FreeCAD.closeDocument(doc.Name)

    if FAILURES:
        print("N-PORT LIVE GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("N-PORT LIVE GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    rc = main()
    if rc:
        raise SystemExit("n_port_live_palace failed")
