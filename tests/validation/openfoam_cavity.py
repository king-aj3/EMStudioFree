# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate — EMStudio's first OpenFOAM calculation.

Two halves. The first needs no solver and checks the algebra and the field
reader against states whose answers are known exactly. The second runs the
whole write -> blockMesh -> checkMesh -> buoyantBoussinesqSimpleFoam -> read
chain and checks the physics.

WHAT THIS GATE ANCHORS ON
--------------------------
It was written WITHOUT the de Vahl Davis values, on purpose: they could not be
verified from a source on the first pass, and this project has a specific scar
from filling that gap from memory — `foam_run.py` once hard-coded "v2212+
restores function objects" as though it were a release boundary, and the note
beside it now reads *"the number was plausible and invented"*. A reference
value that is remembered rather than read is worse than none, because it looks
authoritative and is never re-checked.

The values were then located properly and ARE here (`DE_VAHL_DAVIS`), with
their provenance recorded. They did not replace the citation-free anchors, they
joined them — a literature band can be satisfied by a wrong solve that happens
to land inside it, whereas none of the following can:

* **The conduction limit is EXACT.** Nu is normalised by the pure-conduction
  solution across the cavity, so as Ra -> 0 the answer is 1 by construction,
  not by measurement. Checked twice: analytically on a synthetic linear field
  (where the two-point wall gradient is exact, so it must be 1 to rounding),
  and live at Ra = 100, where convection is negligible.
* **Energy conservation.** At steady state the heat entering the hot wall
  equals the heat leaving the cold wall, so the two Nusselt numbers are the
  same number measured at opposite ends of the box. A discretisation or
  cell-ordering mistake moves one and not the other.
* **Monotonicity in Ra.** More buoyancy transports more heat.
* **The Ra round trip.** The written nu and alpha must reproduce the requested
  Rayleigh number, so a case cannot quietly sit at Ra 9.4e4 while the report
  says 1e5.

⚠ Not covered, and deliberately: the 1e3 and 1e6 table entries below are NOT
exercised — the live sweep is 1e2/1e4/1e5.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from emstudio.solvers import openfoam as ofm                    # noqa: E402
from emstudio.solvers.openfoam import writer as W               # noqa: E402
from emstudio.setup import openfoam as _setup                   # noqa: E402

_FAILED = []

#: Average Nusselt number on the hot wall, air (Pr = 0.71), normalised by the
#: pure-conduction solution across the cavity.
#:
#: PROVENANCE, because a reference value nobody can trace is not a reference:
#: these are column "Ref. [3]" of Table 5 in Wan, Patnaik & Wei, *A New
#: Benchmark Quality Solution for the Buoyancy-Driven Cavity by Discrete
#: Singular Convolution* (Numerical Heat Transfer Part B), whose reference [3]
#: is *D. de Vahl Davis, Natural Convection of Air in a Square Cavity: A Bench
#: Mark Solution*, Int. J. Numer. Methods Fluids 3:249-264 (1983). The [3] ->
#: de Vahl Davis mapping was read out of that paper's own bibliography, not
#: assumed.
#:
#: ⚠ SECOND-HAND: read from a citing paper, not the 1983 original. Good enough
#: to gate against, and said out loud rather than dressed up as primary.
#: ⚠ For Ra >= 1e7 the usual reference is Le Quere, not de Vahl Davis, and the
#: same table shows the citing literature disagreeing by >15 % up there. Do not
#: extend this dict upward without reading a source.
#:
#: ⚠ **1e6 IS NOT GATED, and here is the measurement rather than silence.**
#: Ra 1e3/1e4/1e5 are checked below; 1e6 is not, because the gate's uniform
#: 40x40 cannot resolve it. The thermal boundary layer thins as Ra rises, and
#: at 1e6 the mesh — not the iteration count — is the binding error. Measured
#: 2026-08-11, every run CONVERGED (residualControl fired):
#:     40 cells 9.37372 +6.31 % · 80 cells 8.96193 +1.64 % · 120 cells
#:     8.88629 +0.79 %
#: That is a clean monotone grid convergence onto the published value, so the
#: chain is validated at 1e6 even though the GATE does not check it — the
#: measurement is recorded here precisely so "ungated" does not read as
#: "unknown". A real 1e6 check needs >= 80 cells and its own iteration budget.
#: Widening the band to ~7 % so 40 cells passes would be gating the mesh
#: coarseness, not the physics, which is the opposite of what a gate is for.
DE_VAHL_DAVIS = {1e3: 1.12, 1e4: 2.243, 1e5: 4.52, 1e6: 8.8}

#: ⚠ Was 1200, and 1200 CONVERGED NOTHING. Measured 2026-08-11 once
#: ``run_cavity`` learned to report ``residualControl``: at 1200 iterations
#: every Ra reported converged=False, and the residual was being described in
#: this gate as discretisation error. At 4000 all of Ra 1e2/1e3/1e4/1e5 fire
#: the control, and 8000 returns byte-identical Nu — so the control fires
#: before 4000 and this budget has margin rather than being the edge of one.
#:
#: What it changed, converged vs the 1200-iteration readings:
#:     Ra 1e2  1.00218 -> 1.00146      Ra 1e4  2.24594 -> 2.25648
#:     Ra 1e3  1.09567 -> 1.11858      Ra 1e5  4.60527 -> 4.60562
#: Ra 1e3 moved -1.91 % -> +0.14 %, which is the whole reason it is now
#: exercised: on the unconverged runs it looked like a 4.5 % disagreement that
#: got WORSE with mesh refinement, and that was refinement without a matching
#: iteration budget, not a mesh effect at all.
ITERATIONS = 4000



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
    """Everything that can be known without a solver."""
    print(" case algebra:")
    for ra in (1e3, 1e4, 1e5, 1e6):
        c = W.CavityCase(ra=ra, pr=0.71)
        check("Ra %.0e round-trips through the derived nu/alpha" % ra,
              abs(c.ra_written - ra) / ra < 1e-9,
              "written %.6e" % c.ra_written)
    c = W.CavityCase(ra=1e5, pr=0.71)
    check("Pr is exactly what was asked for",
          abs(c.nu / c.alpha - 0.71) < 1e-12)
    for bad, why in ((dict(ra=0), "Ra 0"), (dict(pr=0), "Pr 0"),
                     (dict(ra=-1), "negative Ra")):
        try:
            W.CavityCase(**bad).nu
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)

    print(" the conduction limit is exact, not approximate:")
    n, length = 40, W.L
    th, tc = 300.5, 299.5
    dx = length / n
    linear = [th - (th - tc) * ((col + 0.5) * dx) / length
              for _row in range(n) for col in range(n)]
    r = ofm.nusselt_from_field(linear, n, th, tc, length=length)
    check("a LINEAR field (pure conduction) gives Nu = 1",
          abs(r.nu_avg - 1.0) < 1e-9, "%.12f" % r.nu_avg)
    check("...and the cold wall agrees with the hot one",
          r.imbalance < 1e-9, "imbalance %.2e" % r.imbalance)

    print(" the reader refuses what it cannot honestly read:")
    for values, cells, why in (
            ([1.0] * 9, 4, "a field whose length does not match the mesh"),
            ([1.0] * 4, 1, "a mesh below 2 cells a side")):
        try:
            ofm.nusselt_from_field(values, cells, 301.0, 299.0)
            check("%s is rejected" % why, False, "no error raised")
        except ValueError:
            check("%s is rejected" % why, True)
    try:
        ofm.nusselt_from_field([1.0] * 16, 4, 300.0, 300.0)
        check("equal wall temperatures are rejected (Nu undefined)", False)
    except ValueError:
        check("equal wall temperatures are rejected (Nu undefined)", True)

    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "T")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("internalField   uniform 300;\n")
        try:
            ofm.read_internal_field(path)
            check("an unsolved 'uniform' field is an ERROR, not a reading",
                  False, "it was accepted")
        except ValueError:
            check("an unsolved 'uniform' field is an ERROR, not a reading",
                  True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("internalField   nonuniform List<scalar>\n4\n(\n1 2 3\n)\n;\n")
        try:
            ofm.read_internal_field(path)
            check("a TRUNCATED field is caught by its own count", False,
                  "3 values accepted where the header said 4")
        except ValueError:
            check("a TRUNCATED field is caught by its own count", True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    tmp = tempfile.mkdtemp()
    try:
        ofm.write_cavity(tmp, W.CavityCase(ra=1e4, cells=8, iterations=10))
        for rel in ("system/blockMeshDict", "system/controlDict",
                    "system/fvSchemes", "system/fvSolution",
                    "constant/transportProperties",
                    "constant/turbulenceProperties", "constant/g",
                    "0/T", "0/U", "0/p_rgh", "0/alphat"):
            check("writes %s" % rel,
                  os.path.isfile(os.path.join(tmp, rel)))
        with open(os.path.join(tmp, "constant/turbulenceProperties"),
                  encoding="utf-8") as fh:
            body = fh.read()
        check("emits the ESI turbulenceProperties, not Foundation's "
              "momentumTransport", "momentumTransport" not in body)
        with open(os.path.join(tmp, "system/fvSolution"), encoding="utf-8") as fh:
            fvsol = fh.read()
        check("pins the pressure level (a closed cavity is singular in p "
              "without pRefCell)", "pRefCell" in fvsol)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def live_checks():
    """The physics, on a real solve. Requires an ESI OpenFOAM."""
    info = _setup.find_openfoam()
    if not info.found or not info.usable:
        raise SystemExit(
            "openfoam_cavity needs a usable ESI OpenFOAM; discovery says: "
            + (info.describe() or "nothing found"))
    print(" live solve (%s):" % info.describe())

    base = tempfile.mkdtemp(prefix="emstudio-cavity-")
    results = {}
    try:
        for ra in (1e2, 1e3, 1e4, 1e5):
            d = os.path.join(base, "ra%g" % ra)
            os.makedirs(d)
            rep, res = ofm.run_cavity(
                d, W.CavityCase(ra=ra, cells=40, iterations=ITERATIONS))
            if not check("Ra %.0e: the chain completes" % ra, rep["ok"],
                         rep.get("failed_at", "") or ""):
                continue
            # ⚠ THE CHECK THIS GATE SHIPPED WITHOUT. Until 2026-08-11 it ran
            # 1200 iterations and never asked whether they were enough — they
            # were not, at ANY Ra, and the residual was then described in this
            # docstring as discretisation error.
            # ⚠ The detail string is printed whether the check passes or
            # fails, so it must not assert the failure case unconditionally —
            # a passing line reading "not converged in 4000 iterations" says
            # the opposite of its own verdict, which is exactly the misreading
            # this check exists to prevent.
            check("Ra %.0e: residualControl actually fired" % ra,
                  rep["converged"],
                  "" if rep["converged"]
                  else "residuals still falling after %d iterations"
                       % ITERATIONS)
            results[ra] = res
            # ⚠ Necessary, NOT sufficient — measured: imbalance was 9.7e-5 at
            # Ra 1e4 on a run that was demonstrably unconverged. A symmetric
            # half-converged field balances just fine.
            check("Ra %.0e: hot and cold walls balance (steady state)" % ra,
                  res.imbalance < 5e-3,
                  "imbalance %.2e" % res.imbalance)

        if 1e2 in results:
            nu = results[1e2].nu_avg
            check("Ra 100 recovers the CONDUCTION LIMIT Nu = 1",
                  abs(nu - 1.0) < 0.02, "Nu %.4f" % nu)
        if len(results) >= 2:
            ordered = [results[r].nu_avg for r in sorted(results)]
            check("Nu increases with Ra",
                  all(b > a for a, b in zip(ordered, ordered[1:])),
                  " -> ".join("%.4f" % v for v in ordered))
        # THE LITERATURE COMPARISON (see DE_VAHL_DAVIS above for provenance).
        # Tolerances come from the KNOWN error mechanism rather than being
        # tuned until they passed: the wall gradient is two-point across the
        # first cell, so it is first order, and the thermal boundary layer
        # thins as Ra rises, so the coarse-mesh bias GROWS with Ra. Measured
        # on a uniform 40x40 at ITERATIONS, all converged:
        #     Ra 1e3  -0.13 %      Ra 1e4  +0.60 %      Ra 1e5  +1.89 %
        # The bands sit just outside those, so a real regression trips them
        # while the expected discretisation error does not — and the trend
        # with Ra is the mechanism's own signature, which is why it is worth
        # more than three isolated tolerances.
        #
        # ⚠ The earlier readings quoted here (+0.13 % at 1e4, +1.9 % at 1e5)
        # were taken on UNCONVERGED runs and called discretisation error. They
        # are replaced above. Ra 1e3 was tabulated but never exercised, and on
        # unconverged runs it looked like a 4.5 % disagreement widening with
        # refinement; converged it is -0.13 % here and +0.08 % at 80 cells.
        for ra, tol in ((1e3, 0.02), (1e4, 0.03), (1e5, 0.05)):
            if ra not in results:
                continue
            ref = DE_VAHL_DAVIS[ra]
            nu = results[ra].nu_avg
            err = abs(nu - ref) / ref
            check("Ra %.0e matches de Vahl Davis within %.0f%%" % (ra, tol * 100),
                  err < tol, "Nu %.4f vs %.4g published (%+.2f%%)"
                  % (nu, ref, 100.0 * (nu - ref) / ref))
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    print("OPENFOAM-CAVITY GATE")
    offline_checks()
    live_checks()
    if _FAILED:
        raise SystemExit("OPENFOAM-CAVITY GATE FAILED: %s" % ", ".join(_FAILED))
    print("OPENFOAM-CAVITY GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    main()
