# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the 3-D viewport overlays (``emstudio/post/vtk_out.py``).

The pattern balloon, the wire-current polyline and the near-field plane are what
the Results dialog loads into FreeCAD's own 3-D view. They shipped UNGATED —
this closes that. The writers are plain XML + numpy, so everything here runs
headlessly under python3; only ``show_in_freecad`` needs FreeCAD and is covered
by gui_smoke instead.

Two things are worth more than the shapes: the geometry must be REGISTERED (a
balloon centred on the origin when the antenna is elsewhere is a picture that
looks right and is wrong), and the radius must actually follow the gain (a
balloon that ignores its scalar field would still render as a plausible blob).

Run:  python3 tests/validation/pattern_vtu.py
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0} - {1}  {2}".format("ok  " if ok else "FAIL", name, detail))
    if not ok:
        FAILURES.append(name)


def _cells(path):
    """(types, offsets, connectivity) straight out of the VTU XML."""
    piece = ET.parse(path).getroot().find(".//Piece")
    out = {}
    for da in piece.find("Cells").iter("DataArray"):
        out[da.get("Name")] = np.array((da.text or "").split(), dtype=int)
    types = np.array(
        [int(v) for v in (piece.find("Cells").find(
            "DataArray[@Name='types']").text or "").split()])
    return types, out["offsets"], out["connectivity"]


def _points(path):
    piece = ET.parse(path).getroot().find(".//Piece")
    da = piece.find("Points").find("DataArray")
    return np.array((da.text or "").split(), dtype=float).reshape(-1, 3)


def _point_data(path):
    piece = ET.parse(path).getroot().find(".//Piece")
    out = {}
    pd = piece.find("PointData")
    for da in pd.iter("DataArray"):
        out[da.get("Name")] = np.array((da.text or "").split(), dtype=float)
    return out


def _pattern(peak_theta=0.0, peak_phi=0.0, step=5.0, peak_dbi=10.0, floor=-40.0):
    """A synthetic single-lobe pattern on a full-sphere grid."""
    from emstudio.post.farfield import FarFieldResult

    theta = np.arange(0.0, 180.0 + 1e-9, step)
    phi = np.arange(0.0, 360.0, step)
    t = np.radians(theta)[:, None]
    p = np.radians(phi)[None, :]
    tp, pp = np.radians(peak_theta), np.radians(peak_phi)
    # angle from the intended peak direction
    cosang = (np.sin(t) * np.cos(p) * np.sin(tp) * np.cos(pp)
              + np.sin(t) * np.sin(p) * np.sin(tp) * np.sin(pp)
              + np.cos(t) * np.cos(tp))
    gain = peak_dbi + floor * (1.0 - np.clip(cosang, 0.0, 1.0)) ** 2
    return FarFieldResult(2.4e9, theta, phi, gain)


def main():
    from emstudio.post import vtk_out
    from emstudio.solvers.elmer import parser

    print("EMStudio 3-D overlay (VTU) validation")
    print("-------------------------------------")
    tmp = tempfile.mkdtemp(prefix="emstudio_vtu_")

    # ---------------------------------------------------------- pattern balloon
    ff = _pattern()
    nt, npn = ff.theta.size, ff.phi.size
    p = vtk_out.write_pattern_vtu(ff, os.path.join(tmp, "pattern.vtu"),
                                  radius_mm=100.0, floor_db=-30.0)
    pts = _points(p)
    types, offsets, conn = _cells(p)
    check("balloon point count is the (theta, phi) grid",
          pts.shape == (nt * npn, 3), str(pts.shape))
    check("balloon cells are all VTK triangles (type 5)",
          types.size > 0 and set(types.tolist()) == {5}, str(set(types.tolist())))
    # phi spans the full 360 with a wrap, so the surface CLOSES: every theta band
    # contributes npn quads, not npn-1. An unclosed balloon has a visible seam.
    check("balloon closes in phi (2 triangles per full band)",
          types.size == 2 * (nt - 1) * npn,
          "{0} vs {1}".format(types.size, 2 * (nt - 1) * npn))
    check("balloon connectivity indexes only real points",
          conn.max() == nt * npn - 1 and conn.min() == 0,
          "max {0}".format(conn.max()))

    pd = _point_data(p)
    check("balloon carries Gain_dBi point data", "Gain_dBi" in pd, str(list(pd)))
    check("balloon scalars ARE the input gain (not the radius)",
          np.allclose(pd["Gain_dBi"], ff.gain.reshape(-1), atol=1e-3))

    # radius must follow gain: peak at full radius, floor collapsed to zero
    r = np.linalg.norm(pts, axis=1)
    g = pd["Gain_dBi"]
    check("peak gain sits at the full balloon radius",
          abs(r[int(np.argmax(g))] - 100.0) < 1e-6, "{0:.6f} mm".format(r.max()))
    below = g <= (g.max() - 30.0)
    check("everything at or below the -30 dB floor collapses to r = 0",
          below.any() and np.all(r[below] < 1e-9), "{0} points".format(int(below.sum())))
    check("no negative radii (the floor clamps, it does not reflect)",
          np.all(r >= 0.0), "min {0:.6g}".format(r.min()))
    # The exact radius law, point by point — the property a blob that ignored
    # its own scalar field would fail. Checked directly rather than as
    # monotonicity, which the writer's %.6g output can invert between two
    # nearly-equal gains without anything being wrong.
    want = 100.0 * np.clip((g - (g.max() - 30.0)) / 30.0, 0.0, 1.0)
    check("radius follows the gain law exactly at every point",
          np.allclose(r, want, atol=2e-3),
          "max error {0:.2e} mm".format(float(np.max(np.abs(r - want)))))

    # our own reader must accept our own writer's output
    mesh = parser.parse_vtu(p)
    check("the project's VTU parser reads the balloon back",
          mesh["points"].shape == (nt * npn, 3)
          and mesh["triangles"].shape[0] == 2 * (nt - 1) * npn
          and "Gain_dBi" in mesh["point_data"],
          "{0} pts, {1} tris".format(mesh["points"].shape[0],
                                     mesh["triangles"].shape[0]))

    # a coarse 2-column pattern must NOT be treated as closed
    from emstudio.post.farfield import FarFieldResult

    two = FarFieldResult(2.4e9, ff.theta, np.array([0.0, 90.0]),
                         np.zeros((nt, 2)))
    p2 = vtk_out.write_pattern_vtu(two, os.path.join(tmp, "two.vtu"))
    t2, _, _ = _cells(p2)
    check("a pattern that does not span 360 in phi is left OPEN",
          t2.size == 2 * (nt - 1) * 1, str(t2.size))

    # ------------------------------------------------- registration (center_mm)
    ctr = (12.0, -34.0, 56.0)
    pc = vtk_out.write_pattern_vtu(ff, os.path.join(tmp, "pattern_c.vtu"),
                                   radius_mm=100.0, floor_db=-30.0,
                                   center_mm=ctr)
    ptsc = _points(pc)
    check("center_mm translates the whole balloon, shape unchanged",
          np.allclose(ptsc - np.asarray(ctr), pts, atol=1e-4))
    rc = np.linalg.norm(ptsc - np.asarray(ctr), axis=1)
    check("radii are measured from the given centre, not the origin",
          abs(rc.max() - 100.0) < 1e-6, "{0:.6f} mm".format(rc.max()))
    check("default centre is still the origin (unchanged behaviour)",
          np.allclose(_points(p), pts))

    # ------------------------------------------------------------- auto radius
    check("auto_radius_mm scales with the geometry it must sit beside",
          vtk_out.auto_radius_mm(450.0) > vtk_out.auto_radius_mm(40.0))
    check("auto_radius_mm on a 450 mm array is array-sized, not 100 mm",
          vtk_out.auto_radius_mm(450.0) >= 225.0,
          "{0:.1f} mm".format(vtk_out.auto_radius_mm(450.0)))
    check("auto_radius_mm refuses a degenerate extent rather than returning 0",
          vtk_out.auto_radius_mm(0.0) > 0.0,
          "{0:.1f} mm".format(vtk_out.auto_radius_mm(0.0)))

    # --------------------------------------------------------- wire currents
    pos = np.column_stack([np.zeros(21), np.zeros(21), np.linspace(-0.24, 0.24, 21)])
    cur = {"pos_m": pos, "i_mag": np.abs(np.cos(np.linspace(-1.5, 1.5, 21)))}
    p3 = vtk_out.write_currents_vtu(cur, os.path.join(tmp, "currents.vtu"))
    t3, off3, conn3 = _cells(p3)
    check("currents are ONE VTK polyline (type 4)",
          t3.tolist() == [4], str(t3.tolist()))
    check("the polyline walks every sample once",
          conn3.tolist() == list(range(21)) and off3.tolist() == [21])
    pts3 = _points(p3)
    check("current positions convert m -> mm for the FreeCAD view",
          abs(pts3[:, 2].max() - 240.0) < 1e-6, "{0:.3f} mm".format(pts3[:, 2].max()))
    pd3 = _point_data(p3)
    check("current magnitude is in mA",
          abs(pd3["Current_mA"].max() - 1000.0) < 1e-3,
          "{0:.3f} mA".format(pd3["Current_mA"].max()))

    # ------------------------------------------------------- near-field plane
    x = np.linspace(-0.05, 0.05, 11)
    y = np.linspace(-0.04, 0.04, 9)
    e = np.outer(np.cos(x * 20.0) ** 2 + 0.01, np.ones_like(y))
    nf = {"plane": "XY", "x": x, "y": y, "z": np.array([0.003]), "e_mag": e}
    p4 = vtk_out.write_field_plane_vtu(nf, os.path.join(tmp, "nf.vtu"))
    t4, _, _ = _cells(p4)
    check("near-field plane is VTK quads (type 9)",
          set(t4.tolist()) == {9}, str(set(t4.tolist())))
    check("one quad per grid cell",
          t4.size == (x.size - 1) * (y.size - 1), str(t4.size))
    pts4 = _points(p4)
    check("the fixed axis really is fixed, at the plane's own offset",
          np.allclose(pts4[:, 2], 3.0), "z {0}".format(np.unique(pts4[:, 2])))
    pd4 = _point_data(p4)
    check("plane carries both linear and dB fields",
          {"E_mag", "E_dB_rel_max"} <= set(pd4), str(sorted(pd4)))
    check("dB field is relative to its own max (peak = 0 dB, nothing above)",
          abs(pd4["E_dB_rel_max"].max()) < 1e-6 and pd4["E_dB_rel_max"].min() < -1.0,
          "max {0:.6g}".format(pd4["E_dB_rel_max"].max()))

    print("-------------------------------------")
    if FAILURES:
        print("PATTERN-VTU GATE FAILED: {0}".format(FAILURES))
        return 1
    print("PATTERN-VTU GATE PASSED")
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
        raise SystemExit("pattern-vtu validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("pattern-vtu validation failed")
    sys.exit(0)
