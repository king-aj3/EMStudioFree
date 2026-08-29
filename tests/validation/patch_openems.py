# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: microstrip patch antenna via the openEMS backend.

Reference: the official openEMS Python tutorial ``Simple_Patch_Antenna.py`` — the same
geometry (32 x 40 mm patch, 60 x 60 x 1.524 mm epsR 3.38 substrate, feed at x = -6 mm)
produces an S11 dip near 2.4 GHz.

This is the expensive gate (full FDTD run, ~minutes). Not part of the smoke suite.

Run:  freecadcmd tests/validation/patch_openems.py
Pass: exit 0 and 'PATCH GATE PASSED'.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    # A live FDTD run needs the openEMS PYTHON modules, not just the binary.
    # Without them this gate used to die with SolverError -- a FAILURE that
    # says nothing about EMStudio, and that made the battery red on every box
    # where openEMS is not installed. Absence of an optional backend is a
    # SKIP; the same correction the nec2c gates got in v0.83.0. The
    # deck-writing paths stay covered by smoke.py and the STL mesh gate.
    from emstudio.setup.solvers import find_openems_python

    if find_openems_python() is None:
        # NO self-skip-and-pass. This used to print the PASSED banner and
        # return 0, so on a box without openEMS the gate reported success
        # while testing nothing -- and freecadcmd drops print(), so the exit
        # code was the only thing a caller saw. Skipping is the BATTERY's job
        # (run_battery.SOLVER_REQS declares "openems_python" for this gate and
        # prints a real "skip"); running this file BY HAND must fail loudly,
        # because you asked for it specifically.
        raise SystemExit(
            "openEMS is required for this gate and was not found -- set "
            "EMSTUDIO_OPENEMS_PYTHON, or install openEMS with its venv beside "
            "the binary. (The battery skips this gate automatically; a direct "
            "run does not.)")
    import FreeCAD
    import numpy as np

    from emstudio.solvers import openems
    from emstudio.templates import patch

    doc = FreeCAD.newDocument("patch_gate")
    ana = patch.makePatch(doc)
    solver = [
        o for o in ana.Group if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"
    ][0]

    result = openems.run(ana, solver)

    f_min, s11_min = result.min_s11()
    print("patch: best match {0:.2f} dB at {1:.4f} GHz".format(s11_min, f_min / 1e9))
    print("patch: run took {0:.1f} s in {1}".format(
        result.meta.get("duration_s", -1), result.meta.get("workdir", "?")))

    # --- gates ---
    # Tutorial reference: resonance ~2.4 GHz. Window allows for our slightly
    # tighter MUR domain (lambda/4 padding vs the tutorial's fixed 200 mm box).
    assert 2.30e9 <= f_min <= 2.50e9, (
        "patch resonance {0:.3f} GHz outside 2.30-2.50 GHz gate".format(f_min / 1e9)
    )
    assert s11_min < -10.0, "patch should dip below -10 dB (got {0:.1f} dB)".format(s11_min)

    # --- far-field gates ---
    # Typical microstrip patch directivity: 5-9 dBi, boresight (+z, theta=0).
    ff = getattr(result, "farfield", None)
    assert ff is not None, "openEMS run produced no far field"
    g_peak, th_peak, _ = ff.peak()
    print("patch: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(g_peak, th_peak))
    assert 4.5 <= g_peak <= 9.5, "peak gain {0:.2f} dBi outside patch gate".format(g_peak)
    assert th_peak <= 30.0 or th_peak >= 150.0, (
        "patch peak should be near boresight (theta={0:.0f})".format(th_peak)
    )

    # --- near-field map gate ---
    # ⚠ THIS BLOCK USED TO CHECK SHAPE, SIZE AND "not all zero" — AND NOTHING
    # ELSE. ``nf["plane"]`` was PRINTED and never asserted, so every way the
    # map can be WRONG still passed: the XZ cut handed back for an XY request,
    # a constant map, a map off by a stray 1e6. "An array exists and has
    # numbers in it" is a check that the file parsed, not a check on a field.
    # The six below are the field.
    nf = getattr(result, "nearfield", None)
    assert nf is not None, "openEMS run produced no near-field map"
    e = np.asarray(nf["e_mag"], dtype=float)
    assert e.ndim == 2 and e.size > 100, "near-field map malformed: {0}".format(e.shape)
    assert e.max() > 0.0, "near-field map is all zero"

    # (1) THE LABEL IS THE PLANE THAT WAS ASKED FOR. ``NearFieldPlane`` is the
    #     document's request (the patch template leaves it at the "XY"
    #     default); ``nf["plane"]`` is what came back through the deck, the h5
    #     -> npz conversion and the runner.
    want = str(solver.NearFieldPlane)
    got = str(nf.get("plane"))
    assert got == want, (
        "near-field map came back as the {0} plane, but the solver asked for "
        "{1}".format(got, want))

    # (2) AND THE DATA AGREES WITH THE LABEL. The label is COPIED from the
    #     request by the writer, so on its own it can only catch half of the
    #     defect — place the dump box on the wrong axis and it still reads
    #     "XY". The mesh saved beside the map is the dump's OWN grid, so: the
    #     axis normal to the requested plane must be the degenerate one, and
    #     the map's two dimensions must be the two in-plane axes IN ORDER (the
    #     deck squeezes an (nx, ny, nz) array). An XZ cut mislabelled XY has
    #     one y line and shape (nx, nz) — caught here, and nowhere else.
    ax = {"X": np.atleast_1d(np.asarray(nf["x"], dtype=float)),
          "Y": np.atleast_1d(np.asarray(nf["y"], dtype=float)),
          "Z": np.atleast_1d(np.asarray(nf["z"], dtype=float))}
    a1, a2 = want[0], want[1]
    normal = ({"X", "Y", "Z"} - {a1, a2}).pop()
    assert ax[normal].size == 1, (
        "{0} map is not a flat cut: {1} axis carries {2} lines".format(
            want, normal, ax[normal].size))
    assert e.shape == (ax[a1].size, ax[a2].size), (
        "map {0} is not the {1} grid ({2}, {3}) it is labelled with".format(
            e.shape, want, ax[a1].size, ax[a2].size))

    # (3) THE CUT PASSES THROUGH THE STRUCTURE. The deck puts it at the
    #     geometry-bbox centre; the bbox is rebuilt HERE from the document's
    #     own shapes, independently of the writer's ``_geometry_bbox``, so this
    #     is a cross-check and not a restatement of the code under test. Mesh
    #     snapping can move the plane by up to a cell, so this asserts "inside
    #     the structure" (the domain is ±67 mm of air around a 1.524 mm
    #     substrate — there is nothing marginal about the distinction) rather
    #     than an equality on the centre. ⚠ h5 mesh lines are METRES; FreeCAD
    #     is mm — the same 1e3 the results dialog and vtk_out apply.
    bbox = FreeCAD.BoundBox()
    for _o in doc.Objects:
        _shp = getattr(_o, "Shape", None)
        if _shp is not None and not _shp.isNull():
            bbox.add(_shp.BoundBox)
    span = {"X": (bbox.XMin, bbox.XMax), "Y": (bbox.YMin, bbox.YMax),
            "Z": (bbox.ZMin, bbox.ZMax)}
    n_lo, n_hi = span[normal]
    cut_mm = float(ax[normal][0]) * 1e3
    slack = 0.1 * (n_hi - n_lo)
    assert n_lo - slack <= cut_mm <= n_hi + slack, (
        "{0} cut sits at {1} = {2:.3f} mm, outside the geometry "
        "({3:.3f} to {4:.3f} mm)".format(want, normal, cut_mm, n_lo, n_hi))

    # (4) THE MAP HAS STRUCTURE. A CONSTANT array passes every shape and
    #     non-zero test ever written — and a fill value, a broadcast scalar or
    #     a mis-indexed h5 read all look exactly like one. Measured on this
    #     deck: std/mean 3.08, peak/median 115. The gates are an order of
    #     magnitude below both, because they exist to separate "a field" from
    #     "a flat array", not to pin this mesh.
    cv = float(e.std() / e.mean())
    dyn = float(e.max() / max(float(np.median(e)), 1e-300))
    assert cv > 0.5, (
        "near-field map is nearly constant (std/mean = {0:.3f})".format(cv))
    assert dyn > 10.0, (
        "near-field map has no dynamic range (peak/median = {0:.2f})".format(dyn))

    # (5) AND THE STRUCTURE IS THE ANTENNA'S. Mid-substrate at resonance, |E|
    #     belongs under the patch and at the feed — not spread over the
    #     lambda/4 air padding, which is most of the map by area (1044 of 1443
    #     samples). Measured: the mean inside the substrate footprint is 13.6x
    #     the mean outside it, and the peak sample lands at x = -6 mm, y = 0 —
    #     the feed. A rotated, transposed or otherwise scrambled map keeps its
    #     shape, its dynamic range and its magnitude, and fails this.
    c1 = ax[a1] * 1e3
    c2 = ax[a2] * 1e3
    lo1, hi1 = span[a1]
    lo2, hi2 = span[a2]
    inside = ((c1 >= lo1) & (c1 <= hi1))[:, None] & ((c2 >= lo2) & (c2 <= hi2))[None, :]
    assert inside.any() and not inside.all(), (
        "near-field map does not straddle the geometry footprint"
    )
    e_in = float(e[inside].mean())
    e_out = float(e[~inside].mean())
    assert e_in > 3.0 * e_out, (
        "near-field energy is not on the antenna: mean |E| inside the "
        "footprint {0:.3e} vs {1:.3e} outside".format(e_in, e_out))
    i_pk, j_pk = np.unravel_index(int(np.argmax(e)), e.shape)
    assert inside[i_pk, j_pk], (
        "peak |E| is out in the padding at {0} = {1:.1f} mm, {2} = {3:.1f} "
        "mm".format(a1, c1[i_pk], a2, c2[j_pk]))

    # (6) A PHYSICALLY SANE MAGNITUDE. Checks (4) and (5) are RATIOS, so every
    #     one of them survives the whole map being multiplied by 1e6 — the
    #     stray-factor class (a unit mix-up, a double normalisation) is
    #     invisible to all of them. The FD dump's absolute scale is the
    #     backend's own normalisation rather than a physical constant we can
    #     derive (measured 3.4e-9 on this deck), so this is a WIDE window —
    #     three decades either side — deliberately too loose to fire on an
    #     upstream re-normalisation and still tight enough to catch a 1e6.
    assert 1e-12 <= e.max() <= 1e-5, (
        "near-field peak |E| = {0:.3e} is off the physical scale for this "
        "dump (expected ~1e-9)".format(e.max()))

    print("patch: near-field {0} map, plane {1} at {2} = {3:.3f} mm; "
          "std/mean {4:.2f}, peak/median {5:.1f}, in/out {6:.1f}, "
          "peak |E| {7:.3e}".format(
              e.shape, got, normal, cut_mm, cv, dyn, e_in / e_out, e.max()))

    print("PATCH GATE PASSED")
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
        raise SystemExit("patch validation failed")
    sys.exit(0)
