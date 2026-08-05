# SPDX-License-Identifier: LGPL-2.1-or-later
"""Elmer .sif writer for GENERAL 3-D magnetodynamics (WhitneyAV chain).

Writes a complete ``case.sif`` driving the probe-validated three-solver
chain — **CoilSolver → WhitneyAVSolver → MagnetoDynamicsCalcFields** — from
a plain "model3d" dict (no FreeCAD objects). Validated on ElmerSolver v26.2
(2026-07-16): analytic tier (thick solenoid −0.55 %, Helmholtz −0.30 % +
flatness, off-axis loop +0.13 % vs elliptic integrals) and the TEAM problem 7
measured benchmark (A1-B1 normalized RMS 2.86 % vs the 10 % gate).

Chain facts this writer encodes (all probe-verified — keep them):

* Ungauged A-V: the Krylov solver is REQUIRED (``BiCGStabl`` polynomial
  degree 6, ``Preconditioning = none``) — a direct solver fails on the
  curl-curl null space.
* Coil source pickup: ``Fix Input Current Density = Logical True`` on the
  WhitneyAV solver + the ``Jfix:`` namespace lines; the outer boundary gets
  ``A {e} = 0`` AND ``Jfix = 0``.
* One ``Component`` per coil body (``Coil Type = "test"``,
  ``Desired Coil Current`` = SIGNED ampere-turns). The circulation SENSE a
  closed coil gets is arbitrary (CoilSolver picks internal fixing nodes) —
  the caller must carry a validated sign per coil (TEAM-7's measured
  convention needs −2742 At).
* CoilSolver 'stranded' normalization under-delivers NI on coarse coil
  meshes (−0.5 % at 3.5 mm elements): keep ≥2-3 elements across the coil
  cross-section and validate delivered NI where sub-percent matters.
* Transient drive: ``Current Density i = Variable "time, coilcurrent e i"``
  with a MATC cosine — MATC has NO ``pi`` constant (literal emitted);
  Initial Conditions must be ATTACHED to every body.
* ``Narrow Interface`` is NOT in this build's CoilSolver keyword set — never
  emitted. 3-D Cartesian scalars need NO per-radian 2π factor (that trap is
  axisymmetric-only). Mesh is in METERS → no ``Coordinate Scaling``.

model3d dict schema (geometry handled by ``emstudio.meshing.gmsh_3d``; this
writer only needs the body/physics fields):

``bodies``
    list of ``{name, sigma, mu_r}`` dicts; a driven coil additionally has
    ``coil = {"amp_turns": signed NI, "normal": (nx,ny,nz)}`` (bulk σ is
    forced to the CoilSolver dummy value 1.0 — stranded source).
``transient``
    optional ``{"f_hz": f, "periods": n, "steps_per_period": m}`` — BDF1
    time stepping with the cosine drive; the LAST step lands on the cosine
    peak (ωt = 0). Absent = magnetostatics (DC ampere-turns).
``save_lines``
    optional ``[((x0,y0,z0),(x1,y1,z1), divisions), ...]`` → one SaveLine
    solver writing ``line.dat`` (columns listed in ``line.dat.names``).
    ALWAYS in METERS — Elmer's internal units, even in mm mode.
``units_mm``
    optional flag: the mesh is in millimeters — emits ``Coordinate
    Scaling = Real 0.001`` plus ``Coordinate Scaling Revert`` on the VTU
    so results overlay FreeCAD geometry (the FreeCAD-import path;
    equivalence to the meters decks probe-verified at 0.05 %,
    2026-07-17). The validated engine gates stay in meters.
"""
from __future__ import annotations

MU0 = 1.2566370614e-6  # matches the probe decks digit-for-digit
_PI = "3.14159265358979"  # MATC has no pi constant


class Elmer3DModelError(ValueError):
    """The model3d dict cannot be expressed as a WhitneyAV case."""


def write_sif3d(model, path, body_ids, boundary_ids, mesh_dir="mesh",
                results_dir="results", vtu_name="case"):
    """Write ``case.sif`` for the 3-D chain. Returns ``path``.

    :param body_ids: {body_name: elmer_body_id} incl. ``air`` — parsed from
        ``mesh.names`` (ElmerGrid renumbers; never assume).
    :param boundary_ids: must contain ``outer`` (the far A=0 skin).
    """
    # hole entries are geometry-only (subtracted by the mesher) — no physics
    bodies = [b for b in model["bodies"]
              if not (b.get("shape") or {}).get("hole")]
    coils = [b for b in bodies if b.get("coil")]
    if not coils:
        raise Elmer3DModelError("no coil body — the WhitneyAV chain needs at "
                                "least one driven closed coil")
    if "outer" not in boundary_ids:
        raise Elmer3DModelError("mesh has no 'outer' boundary group")
    for b in bodies:
        if b["name"] not in body_ids:
            raise Elmer3DModelError("mesh has no body '{0}'".format(b["name"]))
    transient = model.get("transient")
    if transient:
        for key in ("f_hz", "periods", "steps_per_period"):
            if not transient.get(key):
                raise Elmer3DModelError("transient needs '{0}'".format(key))
    save_lines = model.get("save_lines") or []

    L = []
    w = L.append
    w("! EMStudio — general 3-D magnetodynamics (CoilSolver -> WhitneyAV -> CalcFields)")
    w("! mesh in METERS (no unit rescaling); generated deck")
    w("Header")
    w("  CHECK KEYWORDS Warn")
    w('  Mesh DB "." "{0}"'.format(mesh_dir))
    w('  Results Directory "{0}"'.format(results_dir))
    w("End")
    w("")
    w("Simulation")
    w("  Max Output Level = 5")
    w("  Coordinate System = Cartesian")
    if transient:
        f_hz = float(transient["f_hz"])
        n_steps = int(transient["periods"]) * int(transient["steps_per_period"])
        dt = 1.0 / (f_hz * int(transient["steps_per_period"]))
        w("  Simulation Type = Transient")
        w("  Timestepping Method = BDF")
        w("  BDF Order = 1")
        w("  Timestep Sizes = {0:.12g}".format(dt))
        w("  Timestep Intervals = {0}".format(n_steps))
        w("  Output Intervals = 1")
    else:
        w("  Simulation Type = Steady State")
    w("  Steady State Max Iterations = 1")
    if model.get("units_mm"):
        w("  Coordinate Scaling = Real 0.001  ! mesh is in mm")
    w("End")
    w("")
    w("Constants")
    w("  Permeability of Vacuum = Real {0}".format(MU0))
    w("End")
    w("")

    # ---------- bodies ----------
    # equation 1 = field+calc (air, conductors); equation 2 = coil (+CoilSolver)
    mat_id = {}
    next_mat = 1
    for b in bodies:
        mat_id[b["name"]] = next_mat
        next_mat += 1
    air_mat = next_mat

    def _body_section(section, name, eq, mat, force=None):
        w("Body {0}".format(section))
        w('  Name = "{0}"'.format(name))
        w("  Target Bodies(1) = {0}".format(body_ids[name]))
        w("  Equation = {0}".format(eq))
        w("  Material = {0}".format(mat))
        if force:
            w("  Body Force = {0}".format(force))
        if transient:
            # transient AV starts uninitialized unless the IC is ATTACHED
            w("  Initial Condition = 1")
        w("End")
        w("")

    section = 1
    _body_section(section, "air", 1, air_mat)
    for b in bodies:
        section += 1
        if b.get("coil"):
            _body_section(section, b["name"], 2, mat_id[b["name"]], force=1)
        else:
            _body_section(section, b["name"], 1, mat_id[b["name"]])

    w("Equation 1")
    w('  Name = "field+calc"')
    w("  Active Solvers(2) = 2 3")
    w("End")
    w("")
    w("Equation 2")
    w('  Name = "coil+field+calc"')
    w("  Active Solvers(3) = 1 2 3")
    w("End")
    w("")

    # ---------- coil components ----------
    for i, b in enumerate(coils):
        coil = b["coil"]
        normal = coil.get("normal", (0.0, 0.0, 1.0))
        w("Component {0}".format(i + 1))
        w('  Name = "{0}"'.format(b["name"]))
        w('  Coil Type = String "test"')
        w("  Master Bodies(1) = Integer {0}".format(
            2 + bodies.index(b)))  # Body section number (air is section 1)
        w("  Desired Coil Current = Real {0:.9g}".format(
            float(coil["amp_turns"])))
        w("  Coil Normal(3) = Real {0:.9g} {1:.9g} {2:.9g}".format(*normal))
        w("End")
        w("")

    # ---------- solvers ----------
    w("Solver 1")
    w('  Equation = "CoilSolver"')
    w('  Procedure = "CoilSolver" "CoilSolver"')
    w("  Exec Solver = Before All")
    w("  Coil Closed = Logical True")
    w("  Normalize Coil Current = Logical True")
    # Report the current the solver actually DELIVERED. Requested-vs-delivered
    # is the only reliable open-coil detector: 'Coil Closed = True' above is an
    # ASSERTION Elmer trusts ("CoilSolver: Assuming that all coils are
    # closed!"), and an open conductor silently under-delivers — measured
    # 5.17 against 100 ampere-turns on a 6.4-turn open helix, 2026-08-05.
    # Topology cannot substitute: an Euler/genus test calls EMStudio's own
    # closed template tube genus-0, because OCC seam edges break the count.
    w("  Calculate Coil Current = Logical True")
    w("  Calculate Elemental Fields = Logical True")
    w("  Fix Input Current Density = Logical False")
    w("  Linear System Solver = Iterative")
    w("  Linear System Iterative Method = idrs")
    w("  Idrs Parameter = Integer 4")
    w("  Linear System Preconditioning = ILU0")
    w("  Linear System Max Iterations = 2000")
    w("  Linear System Convergence Tolerance = 1.0e-8")
    w("  Linear System Residual Output = 100")
    w("End")
    w("")
    w("Solver 2")
    w('  Equation = "MGDynamics"')
    w('  Procedure = "MagnetoDynamics" "WhitneyAVSolver"')
    w('  Variable = "A"')
    w("  Fix Input Current Density = Logical True")
    w("  Jfix: Linear System Solver = Iterative")
    w("  Jfix: Linear System Iterative Method = BiCGStabl")
    w("  Jfix: BicgstabL Polynomial Degree = Integer 4")
    w("  Jfix: Linear System Preconditioning = ILU0")
    w("  Jfix: Linear System Convergence Tolerance = 1.0e-10")
    w("  Jfix: Linear System Max Iterations = 3000")
    w("  Jfix: Linear System Residual Output = 200")
    w("  Jfix: Linear System Abort Not Converged = False")
    w("  Nonlinear System Max Iterations = 1")
    w("  Nonlinear System Consistent Norm = Logical True")
    w("  ! ungauged A-V: Krylov REQUIRED (curl-curl null space), NO preconditioning")
    w("  Linear System Solver = Iterative")
    w("  Linear System Iterative Method = BiCGStabl")
    w("  BicgstabL Polynomial Degree = Integer 6")
    w("  Linear System Preconditioning = none")
    w("  Linear System Convergence Tolerance = 1.0e-7")
    w("  Linear System Max Iterations = 5000")
    w("  Linear System Residual Output = 100")
    w("  Linear System Abort Not Converged = False")
    w("End")
    w("")
    w("Solver 3")
    w('  Equation = "MGDynamicsCalc"')
    w('  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"')
    if transient:
        w("  Exec Solver = After Timestep")
    w('  Potential Variable = String "A"')
    w("  Calculate Magnetic Field Strength = Logical True")
    w("  Calculate Current Density = Logical True")
    # Magnetic field energy -> the coil INDUCTANCE, L = 2W/I^2. The keyword is
    # 'Calculate Field Energy'; 'Calculate Magnetic Field Energy' does NOT
    # exist in this build (checked against share/elmersolver/lib/
    # SOLVER.KEYWORDS before emitting — the brew-tinyxml rule).
    w("  Calculate Field Energy = Logical True")
    w("  Calculate Nodal Fields = Logical True")
    w("  Calculate Elemental Fields = Logical True")
    w("  Linear System Solver = Iterative")
    w("  Linear System Iterative Method = CG")
    w("  Linear System Preconditioning = ILU0")
    w("  Linear System Max Iterations = 3000")
    w("  Linear System Convergence Tolerance = 1.0e-9")
    w("  Linear System Residual Output = 100")
    w("End")
    w("")
    next_solver = 4
    if save_lines:
        coords = []
        divisions = []
        for p0, p1, div in save_lines:
            coords.append(p0)
            coords.append(p1)
            divisions.append(int(div))
        w("Solver {0}".format(next_solver))
        w('  Equation = "SaveLine"')
        w('  Procedure = "SaveData" "SaveLine"')
        w("  Exec Solver = {0}".format("After Timestep" if transient else "After All"))
        w('  Filename = "line.dat"')
        # Polyline Coordinates on ONE line — sif line continuation breaks it
        w("  Polyline Coordinates({0},3) = {1}".format(
            len(coords), " ".join("{0:.9g} {1:.9g} {2:.9g}".format(*p)
                                  for p in coords)))
        w("  Polyline Divisions({0}) = {1}".format(
            len(divisions), " ".join(str(d) for d in divisions)))
        w("End")
        w("")
        next_solver += 1
    w("Solver {0}".format(next_solver))
    w('  Equation = "ResultOutput"')
    w('  Procedure = "ResultOutputSolve" "ResultOutputSolver"')
    w("  Exec Solver = After Simulation")
    w('  Output File Name = "{0}"'.format(vtu_name))
    w("  Vtu Format = Logical True")
    w("  Save Geometry Ids = Logical True")
    if model.get("units_mm"):
        w("  Coordinate Scaling Revert = Logical True  ! VTU back in mm, overlays geometry")
    w("End")
    w("")

    # ---------- materials ----------
    for b in bodies:
        w("Material {0}".format(mat_id[b["name"]]))
        w('  Name = "{0}"'.format(b["name"]))
        w("  Relative Permeability = Real {0:.9g}".format(float(b.get("mu_r", 1.0))))
        w("  Relative Permittivity = Real 1.0")
        if b.get("coil"):
            # stranded source: CoilSolver's dummy potential needs SOME sigma;
            # Normalize Coil Current makes its value irrelevant
            w("  Electric Conductivity = Real 1.0")
        elif float(b.get("sigma", 0.0)) > 0.0:
            w("  Electric Conductivity = Real {0:.9g}".format(float(b["sigma"])))
        w("End")
        w("")
    w("Material {0}".format(air_mat))
    w('  Name = "air"')
    w("  Relative Permeability = Real 1.0")
    w("  Relative Permittivity = Real 1.0")
    w("End")
    w("")

    # ---------- coil drive ----------
    w("Body Force 1")
    w('  Name = "coil-drive"')
    if transient:
        # cosine drive scaling the normalized CoilSolver elemental field;
        # the LAST step is the cosine peak (wt = 0 report instant)
        for i in (1, 2, 3):
            w('  Current Density {0} = Variable "time, coilcurrent e {0}"'.format(i))
            w('    Real MATC "cos(2.0*{0}*{1:.9g}*tx(0))*tx(1)"'.format(
                _PI, float(transient["f_hz"])))
    else:
        for i in (1, 2, 3):
            w('  Current Density {0} = Equals "CoilCurrent e {0}"'.format(i))
    w("End")
    w("")

    # ---------- BCs / ICs ----------
    w("Boundary Condition 1")
    w('  Name = "outer"')
    w("  Target Boundaries(1) = {0}".format(boundary_ids["outer"]))
    w("  A {e} = Real 0.0")
    w("  Jfix = Real 0.0")
    w("End")
    w("")
    if transient:
        w("Initial Condition 1")
        w("  A {e} = Real 0.0")
        w("  A = Real 0.0")
        w("  Jfix = Real 0.0")
        w("End")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path
