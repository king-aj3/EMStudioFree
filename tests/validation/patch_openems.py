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

#: Every bound below prints one "  ok"/"  FAIL" line, so the battery can COUNT
#: what this gate checked. Until 2026-09-25 they were bare asserts: the gate
#: passed with ZERO countable lines, and a run that checked nothing looked the
#: same as one that checked everything. (The v1.13.0 proof log names this gate
#: in its "ZERO per-check lines" warning.)
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _verdict():
    if FAILURES:
        print("PATCH GATE FAILED: {0}".format(FAILURES))
        return 1
    print("PATCH GATE PASSED")
    return 0


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
    check("resonance within 2.30-2.50 GHz (tutorial ~2.4)",
          2.30e9 <= f_min <= 2.50e9, "{0:.4f} GHz".format(f_min / 1e9))
    check("S11 dips below -10 dB", s11_min < -10.0, "{0:.2f} dB".format(s11_min))

    # --- far-field gates ---
    # Typical microstrip patch directivity: 5-9 dBi, boresight (+z, theta=0).
    ff = getattr(result, "farfield", None)
    check("openEMS produced a far field", ff is not None)
    if ff is not None:
        g_peak, th_peak, _ = ff.peak()
        print("patch: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(g_peak, th_peak))
        check("peak gain within 4.5-9.5 dBi (patch class)", 4.5 <= g_peak <= 9.5,
              "{0:.2f} dBi".format(g_peak))
        check("peak near boresight (theta <= 30 or >= 150 deg)",
              th_peak <= 30.0 or th_peak >= 150.0, "theta={0:.0f}".format(th_peak))

    _nearfield_checks(FreeCAD, np, doc, solver, result)
    return _verdict()


def _nearfield_checks(FreeCAD, np, doc, solver, result):
    """The near-field map checks. Every early RETURN follows a FAIL line for a
    check the code after it reads, so the gate is already red — but the
    checks after that point are NOT run, including any that would not have
    depended on it. Fix the first FAIL, then re-run."""

    # --- near-field map gate ---
    # ⚠ THIS BLOCK USED TO CHECK SHAPE, SIZE AND "not all zero" — AND NOTHING
    # ELSE. ``nf["plane"]`` was PRINTED and never asserted, so every way the
    # map can be WRONG still passed: the XZ cut handed back for an XY request,
    # a constant map, a map off by a stray 1e6. "An array exists and has
    # numbers in it" is a check that the file parsed, not a check on a field.
    # The six below are the field.
    nf = getattr(result, "nearfield", None)
    check("openEMS produced a near-field map", nf is not None)
    if nf is None:
        return
    e = np.asarray(nf["e_mag"], dtype=float)
    check("near-field map is 2-D with > 100 samples",
          e.ndim == 2 and e.size > 100, "shape {0}".format(e.shape))
    if not (e.ndim == 2 and e.size > 100):
        return
    check("near-field map is not all zero", e.max() > 0.0,
          "peak {0:.3e}".format(e.max()))
    if not e.max() > 0.0:
        return                          # the ratios below divide by it

    # (1) THE LABEL IS THE PLANE THAT WAS ASKED FOR. ``NearFieldPlane`` is the
    #     document's request (the patch template leaves it at the "XY"
    #     default); ``nf["plane"]`` is what came back through the deck, the h5
    #     -> npz conversion and the runner.
    want = str(solver.NearFieldPlane)
    got = str(nf.get("plane"))
    check("near-field map is labelled with the plane the solver asked for",
          got == want, "asked {0}, got {1}".format(want, got))

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
    check("{0} map is a flat cut (one {1} line)".format(want, normal),
          ax[normal].size == 1, "{0} lines".format(ax[normal].size))
    if ax[normal].size != 1:
        return                          # the cut position below reads line 0
    check("map shape is the {0} grid it is labelled with".format(want),
          e.shape == (ax[a1].size, ax[a2].size),
          "{0} vs ({1}, {2})".format(e.shape, ax[a1].size, ax[a2].size))
    if e.shape != (ax[a1].size, ax[a2].size):
        return                          # the footprint mask below is that grid

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
    check("the {0} cut passes through the structure".format(want),
          n_lo - slack <= cut_mm <= n_hi + slack,
          "{0} = {1:.3f} mm, geometry {2:.3f} to {3:.3f} mm".format(
              normal, cut_mm, n_lo, n_hi))

    # (4) THE MAP HAS STRUCTURE. A CONSTANT array passes every shape and
    #     non-zero test ever written — and a fill value, a broadcast scalar or
    #     a mis-indexed h5 read all look exactly like one. Measured on this
    #     deck: std/mean 3.08, peak/median 115. The gates are an order of
    #     magnitude below both, because they exist to separate "a field" from
    #     "a flat array", not to pin this mesh.
    cv = float(e.std() / e.mean())
    dyn = float(e.max() / max(float(np.median(e)), 1e-300))
    check("near-field map is not constant (std/mean > 0.5)", cv > 0.5,
          "{0:.3f}".format(cv))
    check("near-field map has dynamic range (peak/median > 10)", dyn > 10.0,
          "{0:.2f}".format(dyn))

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
    check("near-field map straddles the geometry footprint",
          inside.any() and not inside.all(),
          "{0} of {1} samples inside".format(int(inside.sum()), inside.size))
    if not (inside.any() and not inside.all()):
        return                          # both means below need samples
    e_in = float(e[inside].mean())
    e_out = float(e[~inside].mean())
    check("near-field energy is on the antenna (mean |E| inside > 3x outside)",
          e_in > 3.0 * e_out, "{0:.3e} vs {1:.3e}".format(e_in, e_out))
    i_pk, j_pk = np.unravel_index(int(np.argmax(e)), e.shape)
    check("peak |E| is inside the footprint, not in the padding",
          inside[i_pk, j_pk], "{0} = {1:.1f} mm, {2} = {3:.1f} mm".format(
              a1, c1[i_pk], a2, c2[j_pk]))

    # (6) A PHYSICALLY SANE MAGNITUDE. Checks (4) and (5) are RATIOS, so every
    #     one of them survives the whole map being multiplied by 1e6 — the
    #     stray-factor class (a unit mix-up, a double normalisation) is
    #     invisible to all of them. The FD dump's absolute scale is the
    #     backend's own normalisation rather than a physical constant we can
    #     derive (measured 3.4e-9 on this deck), so this is a WIDE window —
    #     three decades either side — deliberately too loose to fire on an
    #     upstream re-normalisation and still tight enough to catch a 1e6.
    check("near-field peak |E| on the physical scale (1e-12 to 1e-5)",
          1e-12 <= e.max() <= 1e-5, "{0:.3e}".format(e.max()))

    print("patch: near-field {0} map, plane {1} at {2} = {3:.3f} mm; "
          "std/mean {4:.2f}, peak/median {5:.1f}, in/out {6:.1f}, "
          "peak |E| {7:.3e}".format(
              e.shape, got, normal, cut_mm, cv, dyn, e_in / e_out, e.max()))


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
