# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: STL-imported geometry solves end-to-end (openEMS backend).

Same patch antenna as ``patch_openems.py``, but the substrate is a triangle-mesh STL
object (``Mesh::Feature``) instead of a parametric solid — exercising the
CSXCAD ``AddPolyhedronReader`` path that real imported-STL workflows use. Expected
result: the same ~2.4 GHz resonance as the native-geometry gate.

Run:  freecadcmd tests/validation/patch_stl_openems.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    import FreeCAD
    import Mesh
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs
    from emstudio.solvers import openems

    doc = FreeCAD.newDocument("patch_stl_gate")
    sub_w, sub_l, sub_h = 60.0, 60.0, 1.524
    patch_w, patch_l = 32.0, 40.0
    feed_x = -6.0

    # substrate as a triangle mesh (the imported-STL case)
    mesh = Mesh.createBox(sub_w, sub_l, sub_h)  # centered at origin
    mesh.translate(0, 0, sub_h / 2.0)  # sit on z=0 like the native template
    substrate = doc.addObject("Mesh::Feature", "SubstrateSTL")
    substrate.Mesh = mesh

    patch = doc.addObject("Part::Feature", "Patch")
    patch.Shape = Part.makePlane(
        patch_w, patch_l, FreeCAD.Vector(-patch_w / 2, -patch_l / 2, sub_h)
    )
    gnd = doc.addObject("Part::Feature", "GroundPlane")
    gnd.Shape = Part.makePlane(sub_w, sub_l, FreeCAD.Vector(-sub_w / 2, -sub_l / 2, 0))
    feed = doc.addObject("Part::Feature", "FeedLine")
    feed.Shape = Part.makeLine(FreeCAD.Vector(feed_x, 0, 0), FreeCAD.Vector(feed_x, 0, sub_h))

    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = "1 GHz"
    ana.FrequencyStop = "3 GHz"
    ana.FrequencyPoints = 401

    m_metal = material_mod.makeMaterial(doc, ana, category="Metal (PEC)")
    m_metal.References = [(patch, ""), (gnd, "")]
    m_metal.Priority = 10
    m_sub = material_mod.makeMaterial(doc, ana, category="Dielectric")
    m_sub.References = [(substrate, "")]
    m_sub.RelPermittivity = 3.38
    m_sub.LossTangent = 1e-3
    m_sub.Priority = 0

    port = ports_mod.makeLumpedPort(doc, ana, direction="+Z")
    port.References = [(feed, "Edge1")]
    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    doc.recompute()

    result = openems.run(ana, solver)
    f_min, s11_min = result.min_s11()
    print("patch-stl: best match {0:.2f} dB at {1:.4f} GHz".format(s11_min, f_min / 1e9))

    # --- gates: same resonance as the native gate, wider tolerance for the
    #     stair-cased STL dielectric ---
    assert 2.30e9 <= f_min <= 2.55e9, (
        "STL patch resonance {0:.3f} GHz outside gate".format(f_min / 1e9)
    )
    assert s11_min < -10.0, "STL patch should dip below -10 dB (got {0:.1f})".format(s11_min)

    print("PATCH-STL GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    # freecadcmd exits 0 on uncaught exceptions (verified 2026-07-05) — convert
    # EVERY failure into SystemExit, which does propagate a non-zero exit code.
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("STL patch validation failed")
    sys.exit(0)
