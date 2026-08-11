# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — a cable BUNDLE in an enclosure, where the shipped
correlation is wrong.

``wire/thermal.py`` takes its film coefficient from Churchill-Chu, correct for
an isolated cylinder in unbounded quiescent air. This gate measures what that
assumption costs for the case that actually matters.

WHAT ANCHORS A CASE WITH NO CORRELATION TO CHECK AGAINST
----------------------------------------------------------
The bundle cannot be gated on Churchill-Chu — being wrong there is the whole
point. So the anchor is a LADDER in which each rung changes exactly one thing,
and only the first two rungs are checked against literature:

    1 cable, big box    -> must sit INSIDE the Churchill-Chu/Morgan envelope
    1 cable, small box  -> must sit INSIDE it too (confinement is small)
    3 cables, same box  -> must sit measurably BELOW it

The first two validate the PIPELINE — snappy mesh, flux boundary condition,
patch-value reader — none of which the structured rungs used. If a single
cable meshed by snappy did not reproduce the correlation, nothing this gate
said about a bundle could be separated from a meshing artifact.

⚠ **Each rung changes ONE variable.** Comparing the bundle straight to the big
box would confound the bundle effect with the enclosure size. That confound
has already produced two wrong answers in this project (a fake "+4 % domain
sensitivity" and a fake "not discretisation" at Ra 1e3), both from studies
that moved two things at once.

MEASURED (D 20 mm, trefoil at 30 mm pitch, uniform wall flux 400 K/m):
    1 cable  0.40 m box   Nu 3.9830 @ Ra 5021   CC +6.99 %
    1 cable  0.20 m box   Nu 3.8621 @ Ra 5179   CC +3.01 %
    3 cables 0.20 m box   Nu 3.1542 @ Ra 6341   CC -19.72 %
Confinement costs 3 %; the bundle costs a further 18 %.

⚠ **Ra is an OUTPUT.** The flux is prescribed and dT is solved, so every
correlation comparison is made at the Ra that RESULTED.

⚠ **SCOPE, so the number is not over-read.** One geometry, 2-D, laminar, no
radiation, uniform flux, unweighted mean over patch faces. `solve_steady()`
sheds heat by radiation as well as convection, so this is not a corrected
ampacity — it is the size of the convective error.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from emstudio.solvers import openfoam as ofm                    # noqa: E402
from emstudio.solvers.openfoam import bundle as B               # noqa: E402
from emstudio.setup import openfoam as _setup                   # noqa: E402
from emstudio.wire.thermal import nu_churchill_chu              # noqa: E402

_FAILED = []
PR = 0.71
#: Morgan bands — the same constants tests/validation/thermal.py already
#: cross-checks Churchill-Chu against.
MORGAN = ((1e-2, 1e2, 1.02, 0.148), (1e2, 1e4, 0.850, 0.188),
          (1e4, 1e7, 0.480, 0.250))


def morgan(ra):
    for lo, hi, c, n in MORGAN:
        if lo <= ra < hi:
            return c * ra ** n
    return float("nan")


def check(label, ok, detail=""):
    line = "  {0}  {1}{2}".format("ok   " if ok else "FAIL ", label,
                                  " — {0}".format(detail) if detail else "")
    try:
        import FreeCAD
        FreeCAD.Console.PrintMessage(line + "\n")
    except Exception:
        print(line)
    if not ok:
        _FAILED.append(label)
    return ok


def offline_checks():
    """Everything knowable with no solver."""
    print(" case validation refuses what cannot be meshed:")
    for kw, why in ((dict(centres=[]), "an empty bundle"),
                    (dict(d_cable=0), "zero diameter"),
                    (dict(box_w=0), "zero enclosure width"),
                    (dict(gradient=0.0), "zero wall gradient"),
                    (dict(cells_x=2), "fewer than 4 background cells"),
                    (dict(centres=[(0.0, 0.0), (0.005, 0.0)]),
                     "overlapping cables"),
                    (dict(centres=[(0.099, 0.0)]),
                     "a cable outside the enclosure")):
        try:
            B.BundleCase(**kw)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)

    c = B.BundleCase()
    check("the default is a trefoil of three", c.n_cables == 3)
    check("analytic cable area = n pi D t",
          abs(c.cable_area_m2 - 3 * math.pi * 0.020 * 0.004) < 1e-15,
          "%.6e m^2" % c.cable_area_m2)
    check("analytic fluid volume subtracts the cables",
          abs(c.fluid_volume_m3
              - (0.2 * 0.2 - 3 * math.pi * 0.01 ** 2) * 0.004) < 1e-15,
          "%.6e m^3" % c.fluid_volume_m3)
    nu_f, alpha_f = c.properties
    check("Pr is exactly what was asked for",
          abs(nu_f / alpha_f - PR) < 1e-12)

    print(" the STL is the geometry it claims:")
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "cables.stl")
        B.cable_stl(p, [(0.0, 0.0)], 0.01, -0.004, 0.008, facets=64)
        text = open(p, encoding="ascii").read()
        verts = [tuple(float(x) for x in m)
                 for m in re.findall(
                     r"vertex\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)",
                     text)]
        rim = [v for v in verts if abs(math.hypot(v[0], v[1]) - 0.01) < 1e-9]
        check("every rim vertex lies on the cable circle",
              len(rim) > 0 and all(abs(math.hypot(v[0], v[1]) - 0.01) < 1e-9
                                   for v in rim),
              "%d of %d vertices on r=0.01" % (len(rim), len(verts)))
        zs = sorted({round(v[2], 9) for v in verts})
        check("the cylinder OVERHANGS the domain in z (else snappy cannot cut "
              "it cleanly)", zs[0] < 0.0 and zs[-1] > 0.004, "z span %s" % zs)
        check("facet count is 4 per segment (side x2 + two caps)",
              text.count("facet normal") == 4 * 64,
              "%d facets" % text.count("facet normal"))
        for bad, why in ((4, "fewer than 8 facets"),):
            try:
                B.cable_stl(p, [(0, 0)], 0.01, -1, 1, facets=bad)
                check("%s is rejected" % why, False)
            except ValueError:
                check("%s is rejected" % why, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the written case avoids the three silent traps:")
    tmp = tempfile.mkdtemp()
    try:
        case = B.BundleCase(cells_x=20, iterations=10, write_interval=10)
        B.write_bundle(tmp, case)
        for rel in ("system/blockMeshDict", "system/snappyHexMeshDict",
                    "system/surfaceFeatureExtractDict", "system/controlDict",
                    "system/fvSchemes", "system/fvSolution",
                    "constant/triSurface/cables.stl",
                    "constant/transportProperties",
                    "constant/turbulenceProperties", "constant/g",
                    "0/T", "0/U", "0/p_rgh", "0/alphat"):
            check("writes %s" % rel, os.path.isfile(os.path.join(tmp, rel)))

        def read(rel):
            with open(os.path.join(tmp, rel), encoding="utf-8") as fh:
                return fh.read()

        ctrl, snap = read("system/controlDict"), read("system/snappyHexMeshDict")
        bm, t0 = read("system/blockMeshDict"), read("0/T")
        # TRAP 1 — writePrecision defaults to 6 and snappy ABORTS when the
        # merge tolerance is finer than it. Omission is the failure mode.
        m = re.search(r"writePrecision\s+(\d+)", ctrl)
        mt = re.search(r"mergeTolerance\s+([\d.eE+-]+)", snap)
        check("controlDict emits writePrecision, and it is finer than snappy's "
              "mergeTolerance (snappyHexMesh ABORTS otherwise)",
              bool(m) and bool(mt) and 10.0 ** -int(m.group(1)) <= float(mt.group(1)),
              "precision %s vs mergeTolerance %s"
              % (m and m.group(1), mt and mt.group(1)))
        # TRAP 2 — empty breaks because snappy refines in z; symmetryPlane
        # refuses a non-planar patch (front and back oppose).
        check("front/back is `symmetry` — not `empty` (snappy refines in z, "
              "breaking 2-D) and not `symmetryPlane` (not co-planar)",
              "frontAndBack { type symmetry;" in bm
              and "symmetryPlane" not in bm and "type empty" not in bm)
        # TRAP 3 — fixedGradient writes no `value`, so the result path reads
        # nothing at all.
        check("the cables use `mixed` with valueFraction 0, NOT "
              "`fixedGradient` (which writes no `value` to read)",
              "type mixed" in t0 and "valueFraction" in t0
              and "fixedGradient" not in t0)
        check("the closed enclosure pins the pressure level (pRefCell)",
              "pRefCell" in read("system/fvSolution"))
        check("non-orthogonal correctors are on for the snapped mesh",
              re.search(r"nNonOrthogonalCorrectors\s+([1-9])",
                        read("system/fvSolution")) is not None)
        check("ESI turbulenceProperties, not Foundation's momentumTransport",
              "momentumTransport" not in read("constant/turbulenceProperties"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the patch reader refuses what it cannot honestly read:")
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "T")
        # exactly what fixedGradient writes: no `value` at all
        open(p, "w", encoding="utf-8").write(
            "boundaryField\n{\n    cables\n    {\n"
            "        type            fixedGradient;\n"
            "        gradient        uniform 400;\n    }\n}\n")
        try:
            ofm.read_patch_values(p, "cables")
            check("a patch with NO `value` (i.e. fixedGradient) is an ERROR, "
                  "not an empty reading", False, "it was accepted")
        except ValueError:
            check("a patch with NO `value` (i.e. fixedGradient) is an ERROR, "
                  "not an empty reading", True)
        open(p, "w", encoding="utf-8").write(
            "boundaryField\n{\n    cables\n    {\n        type mixed;\n"
            "        value           nonuniform List<scalar>\n4\n(\n"
            "301 302 303\n)\n;\n    }\n}\n")
        try:
            ofm.read_patch_values(p, "cables")
            check("a TRUNCATED patch list is caught by its own count", False)
        except ValueError:
            check("a TRUNCATED patch list is caught by its own count", True)
        open(p, "w", encoding="utf-8").write(
            "boundaryField\n{\n    cables\n    {\n        type mixed;\n"
            "        value           nonuniform List<scalar>\n3\n(\n"
            "301 302 303\n)\n;\n    }\n}\n")
        vals = ofm.read_patch_values(p, "cables")
        check("a well-formed patch list reads back exactly",
              vals == [301.0, 302.0, 303.0], "%s" % vals)
        try:
            ofm.read_patch_values(p, "nosuchpatch")
            check("a missing patch is an error", False)
        except ValueError:
            check("a missing patch is an error", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(" the Nusselt formula:")
    r = ofm.nusselt_from_patch([302.0] * 8, 0.020, 400.0, 300.0)
    check("Nu_D = D grad / dT, exactly", abs(r.nu_d - 4.0) < 1e-12,
          "%.12f" % r.nu_d)
    check("...and no conductivity is needed — it cancels", r.faces == 8)
    for kw, why in ((dict(values=[]), "no values"),
                    (dict(d_m=0), "zero diameter"),
                    (dict(gradient=0), "zero gradient"),
                    (dict(t_amb=302.0), "a surface at ambient")):
        kw2 = dict(values=[302.0] * 4, d_m=0.02, gradient=400.0, t_amb=300.0)
        kw2.update(kw)
        try:
            ofm.nusselt_from_patch(**kw2)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)
    cold = ofm.nusselt_from_patch([299.0] * 4, 0.02, 400.0, 300.0)
    check("a surface COLDER than ambient warns rather than passing silently",
          any("negative Nu" in w for w in cold.warnings))


def _case(base, name, **kw):
    d = os.path.join(base, name)
    os.makedirs(d)
    return d, B.BundleCase(**kw)


def live_checks():
    """The ladder, on real solves. Requires a usable ESI OpenFOAM."""
    info = _setup.find_openfoam()
    if not info.found or not info.usable:
        raise SystemExit(
            "openfoam_bundle needs a usable ESI OpenFOAM; discovery says: "
            + (info.describe() or "nothing found"))
    print(" live solve (%s):" % info.describe())
    base = tempfile.mkdtemp(prefix="emstudio-bundle-")
    got = {}
    try:
        # ⚠ ONE variable changes between rungs.
        rungs = (("anchor", dict(centres=[(0.0, 0.0)], box_w=0.40, box_h=0.40)),
                 ("solo", dict(centres=[(0.0, 0.0)], box_w=0.20, box_h=0.20)),
                 ("bundle", dict(box_w=0.20, box_h=0.20)))
        for tag, kw in rungs:
            # ⚠ ITERATIONS ARE MEASURED, NOT GUESSED — and 20000 was
            # unaffordable. residualControl fired at 3136 (solo) and 6384
            # (bundle); the anchor never fires it but its Nu is flat to
            # ±0.15 % from iteration 5000 to 20000. So 8000 preserves all
            # three measured values while cutting the gate's cost by ~60 %.
            #
            # This matters: at 20000 a single rung ran 4376 s on 15k cells and
            # was killed under concurrent load, which is not a gate — the
            # SOLVER tier budgets minutes-to-15-minutes per gate, not hours.
            # The mesh is deliberately UNCHANGED, so the ladder measured at
            # cells_x=100 still applies; only the iteration budget moved.
            d, case = _case(base, tag, cells_x=100, iterations=8000,
                            write_interval=2000, **kw)
            rep, res = ofm.run_bundle(d, case)
            if not check("%s: the chain completes (snappy included)" % tag,
                         rep["ok"], rep.get("failed_at", "") or ""):
                continue
            mesh = [s for s in rep["steps"] if s["step"] == "checkMesh"]
            check("%s: checkMesh reports Mesh OK" % tag,
                  bool(mesh) and "Mesh OK" in mesh[0]["tail"])
            check("%s: read the cable surface" % tag, res.faces > 0,
                  "%d patch faces" % res.faces)
            settled = (rep["converged"]
                       or (rep["nu_drift"] is not None
                           and rep["nu_drift"] < 5e-3))
            check("%s: the solve settled (residualControl or Nu drift)" % tag,
                  settled, "converged %s, drift %s"
                  % (rep["converged"],
                     "n/a" if rep["nu_drift"] is None
                     else "%.2e" % rep["nu_drift"]))
            got[tag] = (res.nu_d, res.ra_d)

        # --- the two single-cable rungs validate the PIPELINE ---------------
        for tag in ("anchor", "solo"):
            if tag not in got:
                continue
            nu_d, ra = got[tag]
            cc, mo = nu_churchill_chu(ra, PR), morgan(ra)
            lo, hi = min(cc, mo) * 0.90, max(cc, mo) * 1.10
            check("%s (ONE cable) lies inside the Churchill-Chu/Morgan "
                  "envelope — this is what validates snappy + the flux BC + "
                  "the patch reader" % tag,
                  lo <= nu_d <= hi,
                  "Nu %.4f in [%.4f, %.4f] at Ra %.4g; CC %+.2f %%"
                  % (nu_d, lo, hi, ra, 100 * (nu_d - cc) / cc))

        # --- and the bundle is the finding ---------------------------------
        if "solo" in got and "bundle" in got:
            nu_s, ra_s = got["solo"]
            nu_b, ra_b = got["bundle"]
            drop = 100 * (nu_b - nu_s) / nu_s
            check("the BUNDLE transfers measurably less than one cable in the "
                  "SAME enclosure (mutual heating + shared air)",
                  nu_b < nu_s * 0.95, "%.4f -> %.4f (%+.2f %%)"
                  % (nu_s, nu_b, drop))
            cc_b = nu_churchill_chu(ra_b, PR)
            err = 100 * (nu_b - cc_b) / cc_b
            check("Churchill-Chu OVER-predicts the bundle by more than 10 % — "
                  "the error wire/thermal.surface_h() makes today, in the "
                  "UNSAFE direction",
                  nu_b < cc_b * 0.90,
                  "CFD %.4f vs CC %.4f at Ra %.4g (%+.2f %%)"
                  % (nu_b, cc_b, ra_b, err))
            mo_b = morgan(ra_b)
            check("...and the bundle falls BELOW both correlations, so no "
                  "isolated-cylinder correlation describes it",
                  nu_b < min(cc_b, mo_b),
                  "CFD %.4f vs CC %.4f / Morgan %.4f" % (nu_b, cc_b, mo_b))
        if "anchor" in got and "solo" in got:
            check("confinement alone costs less than the bundle does "
                  "(the ladder separates them)",
                  abs(got["solo"][0] - got["anchor"][0]) / got["anchor"][0]
                  < abs(got["bundle"][0] - got["solo"][0]) / got["solo"][0]
                  if "bundle" in got else True,
                  "anchor %.4f -> solo %.4f -> bundle %s"
                  % (got["anchor"][0], got["solo"][0],
                     "%.4f" % got["bundle"][0] if "bundle" in got else "n/a"))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    print("OPENFOAM-BUNDLE GATE")
    offline_checks()
    live_checks()
    if _FAILED:
        raise SystemExit("OPENFOAM-BUNDLE GATE FAILED: %s" % ", ".join(_FAILED))
    print("OPENFOAM-BUNDLE GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    main()
