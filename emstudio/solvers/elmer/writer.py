# SPDX-License-Identifier: LGPL-2.1-or-later
"""Elmer .sif writer for 2-D axisymmetric harmonic magnetodynamics.

Writes a complete ``case.sif`` driving ``MagnetoDynamics2DHarmonic`` +
``MagnetoDynamicsCalcFields`` + VTU output + SaveScalars, from a plain
"axi model" dict (no FreeCAD objects — the FreeCAD extraction lives in
``emstudio.solvers.elmer.model``). Verified against ElmerSolver v26.2
(elmerfem-csc 9.0 PPA) on 2026-07-05.

Keyword pitfalls this writer encodes (discovered the hard way — keep them):

* ``Current Density Im`` / ``Potential Re`` / ``Potential Im`` are NOT in
  Elmer's keyword database — they need an explicit ``Real`` type token or
  the sif parser mis-attributes every following line (and still exits 0!).
* ``body int`` in SaveScalars silently yields 0 unless the target Body
  carries ``Save Scalars = Logical True`` (the mask).
* The mesh is in mm; ``Coordinate Scaling = Real 0.001`` converts to SI at
  load and ``Coordinate Scaling Revert`` puts the output VTU back into mm
  so it overlays FreeCAD geometry (FreeCAD's own FEM/Elmer convention).
  MATC boundary expressions therefore see coordinates in METERS.

The axi model dict schema (geometry in mm, materials/sources in SI):

``bodies``
    list of region dicts ``{name, r0, r1, z0, z1, lc, sigma, mu_r}``;
    a coil region additionally carries
    ``coil = {turns, current_a, phase_deg, reversed}`` (current = PEAK
    amplitude; coils are modeled stranded: bulk conductivity forced 0).
    An optional ``sigma_alpha`` (α, 1/K) makes the conductivity
    temperature-dependent, σ(T) = sigma/(1 + α·(T − t_ext)) — the body must
    then also be a thermal body, and the deck becomes two-way coupled
    (see MAGNETICS_DEPTH_PLAN §3).
    An optional ``bh`` — a list of (B [T], H [A/m]) pairs — makes the body a
    nonlinear iron: the table replaces Relative Permeability and the field
    solve gains a real nonlinear block (see MAGNETICS_DEPTH_PLAN §4). Exact
    in static mode; a peak-|B| secant effective-permeability approximation
    in harmonic mode (verified equal to static at σ = 0, de-risk 2026-07-16).
``static``
    top-level flag: ``True`` switches the field solve from the harmonic
    ``MagnetoDynamics2DHarmonic`` to DC magnetostatics
    (``MagnetoDynamics2D``, scalar ``Potential``) — no Frequency keyword,
    plain real sources/BCs, no eddy/Joule quantities, no thermal chain.
``air`` / ``lc_air`` / ``domain_scale``
    air-domain controls, see ``emstudio.meshing.gmsh_axi``.
``bc``
    per outer line group (``router``/``ztop``/``zbottom``/``axis``):
    ``None`` = natural, ``{"re": v, "im": v}`` = Dirichlet constants, or
    ``{"matc_re": expr, "matc_im": expr}`` = MATC expressions of ``tx``
    (= r in meters). Default: A = 0 on router/ztop/zbottom, axis natural
    (r = 0 needs no BC — verified numerically).
"""
from __future__ import annotations

import math

#: default boundary conditions: far-field A = 0, natural axis
DEFAULT_BC = {
    "router": {"re": 0.0, "im": 0.0},
    "ztop": {"re": 0.0, "im": 0.0},
    "zbottom": {"re": 0.0, "im": 0.0},
    "axis": None,
}

MU0 = 4.0e-7 * math.pi
STEFAN_BOLTZMANN = 5.67e-8  # W/m^2K^4 (matches the radiation de-risk gate)

#: outer coupled-iteration ceiling for σ(T) decks. The loop exits early on the
#: per-solver Steady State Convergence Tolerances (the de-risk probe converged
#: in 5 iterations at α·ΔT ≈ 0.06), so a generous ceiling costs nothing.
COUPLED_MAX_ITERATIONS = 30


class ElmerModelError(ValueError):
    """The axi model cannot be expressed as an Elmer magnetodynamics case."""


def validate_bh_table(pairs, name):
    """Reject malformed B-H tables — Elmer runs them SILENTLY wrong (exit 0).

    De-risk 2026-07-16: a column-swapped (H-then-B) table converges FASTER,
    reads as µr ≈ 1e10 iron, and at knee drive is only +18% high with
    B < B_sat — a post-solve B-max check does NOT catch it. Guard on the
    table itself: units ratio, monotonicity, and B-sampling density (a
    uniform-in-H table under-resolves the knee — 42 % flux-linkage error
    measured on the probe pot-core).
    """
    if len(pairs) < 5:
        raise ElmerModelError(
            "B-H curve on '{0}' has {1} points — need at least 5 (about 40, "
            "sampled roughly uniformly in B)".format(name, len(pairs)))
    bs = [float(p[0]) for p in pairs]
    hs = [float(p[1]) for p in pairs]
    if bs[0] != 0.0 or hs[0] != 0.0:
        raise ElmerModelError(
            "B-H curve on '{0}' must start at (0, 0) — first point is "
            "({1:.4g}, {2:.4g})".format(name, bs[0], hs[0]))
    for seq, col in ((bs, "B"), (hs, "H")):
        if any(b <= a for a, b in zip(seq, seq[1:])):
            raise ElmerModelError(
                "B-H curve on '{0}': the {1} column must be strictly "
                "increasing".format(name, col))
    if bs[-1] > 5.0:
        raise ElmerModelError(
            "B-H curve on '{0}': B reaches {1:.4g} — that is not tesla. "
            "Columns are B [T] FIRST then H [A/m] (a swapped table runs "
            "silently wrong)".format(name, bs[-1]))
    if hs[-1] / bs[-1] < 100.0:
        raise ElmerModelError(
            "B-H curve on '{0}': H_max/B_max = {1:.3g} — real materials are "
            ">> 100 (A/m per tesla). Columns look SWAPPED: B [T] first, "
            "H [A/m] second".format(name, hs[-1] / bs[-1]))
    max_step = max(b - a for a, b in zip(bs, bs[1:]))
    if max_step > 0.25 * bs[-1]:
        raise ElmerModelError(
            "B-H curve on '{0}': the largest B step ({1:.3g} T) spans "
            "{2:.0%} of the range — sample roughly UNIFORMLY IN B (a "
            "uniform-in-H table under-resolves the knee; 42% error "
            "measured)".format(name, max_step, max_step / bs[-1]))


def coil_current_density(body, scale=1.0, current_override=None):
    """Source current density (J_re, J_im) in A/m^2 for a coil region.

    Peak-amplitude convention: ``current_a`` is the peak of the sinusoidal
    coil current; ampere-turns spread uniformly over the rectangle
    cross-section (stranded-coil model).

    ``current_override`` (amps) drives the coil at exactly ``turns * override``
    regardless of ``current_a``/``scale`` — used by the coupling extraction so
    L/M/k come from a nonzero REFERENCE current even when the coil's operating
    current is 0 (an undriven WPT pickup coil).
    """
    coil = body["coil"]
    area_m2 = ((body["r1"] - body["r0"]) * (body["z1"] - body["z0"])) * 1e-6
    if area_m2 <= 0:
        raise ElmerModelError("coil '{0}' has zero cross-section".format(body["name"]))
    if current_override is not None:
        amps = float(coil["turns"]) * float(current_override)
    else:
        amps = float(coil["turns"]) * float(coil["current_a"]) * float(scale)
    if coil.get("reversed"):
        amps = -amps
    phase = math.radians(float(coil.get("phase_deg", 0.0)))
    j = amps / area_m2
    return j * math.cos(phase), j * math.sin(phase)


def _bc_lines(name, spec, section_id, target_id, static=False):
    lines = [
        "Boundary Condition {0}".format(section_id),
        '  Name = "{0}"'.format(name),
        "  Target Boundaries(1) = {0}".format(target_id),
    ]
    if static:
        # DC magnetostatics: the scalar Potential has no imaginary part
        if spec.get("im") or spec.get("matc_im"):
            raise ElmerModelError(
                "boundary '{0}': an imaginary Potential is meaningless in "
                "the Static (DC) analysis".format(name))
        if "matc_re" in spec:
            lines.append("  Potential = Variable Coordinate 1")
            lines.append('    Real MATC "{0}"'.format(spec["matc_re"]))
        else:
            lines.append("  Potential = Real {0:.9g}".format(float(spec.get("re", 0.0))))
        lines.append("End")
        lines.append("")
        return lines
    if "matc_re" in spec or "matc_im" in spec:
        re_expr = spec.get("matc_re")
        im_expr = spec.get("matc_im")
        if re_expr is not None:
            lines.append("  Potential Re = Variable Coordinate 1")
            lines.append('    Real MATC "{0}"'.format(re_expr))
        else:
            lines.append("  Potential Re = Real {0:.9g}".format(float(spec.get("re", 0.0))))
        if im_expr is not None:
            lines.append("  Potential Im = Variable Coordinate 1")
            lines.append('    Real MATC "{0}"'.format(im_expr))
        else:
            lines.append("  Potential Im = Real {0:.9g}".format(float(spec.get("im", 0.0))))
    else:
        lines.append("  Potential Re = Real {0:.9g}".format(float(spec.get("re", 0.0))))
        lines.append("  Potential Im = Real {0:.9g}".format(float(spec.get("im", 0.0))))
    lines.append("End")
    lines.append("")
    return lines


def write_sif(model, f_hz, path, body_ids, boundary_ids, excitation=None,
              ref_currents=None, mesh_dir="mesh", vtu_name="case"):
    """Write ``case.sif`` for one frequency / excitation. Returns ``path``.

    :param body_ids: {region_name: elmer_body_id} incl. ``air`` — parsed
        from ``mesh.names`` (ElmerGrid renumbers; never assume).
    :param boundary_ids: {line_group_name: elmer_boundary_id}.
    :param excitation: {coil_name: scale} — coils absent from the dict are
        driven at scale 0 (present but unexcited). None = all coils at 1.
    :param ref_currents: {coil_name: amps} — drive these coils at an absolute
        reference current (coupling extraction), overriding excitation/current_a.

    Returns ``(path, bc_sections)`` where ``bc_sections`` maps boundary-group
    name -> sif BC section number. The VTU tags boundary line elements with
    GeometryIds = 100 + BC section number (untagged boundaries lump into 100;
    verified Elmer v26.2) — needed for surface integrals over a specific group.
    """
    bodies = model["bodies"]
    coils = [b for b in bodies if b.get("coil")]
    if excitation is None:
        excitation = {b["name"]: 1.0 for b in coils}
    bc = dict(DEFAULT_BC)
    bc.update(model.get("bc") or {})

    if not coils and not any(_has_field_bc(spec) for spec in bc.values()):
        raise ElmerModelError(
            "nothing drives the field: add a coil excitation or a non-zero "
            "boundary potential"
        )

    # optional thermal chain: steady-state (or transient) heat conduction in
    # selected bodies, Joule heating as the source, convection on body surfaces.
    thermal = model.get("thermal") or {}
    thermal_bodies = thermal.get("bodies") or {}
    for name in thermal_bodies:
        if not any(b["name"] == name for b in bodies):
            raise ElmerModelError("thermal body '{0}' is not a model body".format(name))
    # optional surface radiation (grey-body to a fixed enclosure): stacks on
    # the convection BC. emissivity <= 0 => byte-identical to the pre-v0.51
    # convection-only decks. Makes the heat equation NONLINEAR (T^4) — the
    # solver gains a Newton block, and the Stefan-Boltzmann constant becomes
    # MANDATORY (no Elmer default; omitting it is a hard STOP). De-risked on
    # Elmer v26.2: closed-form radiating-cylinder gate reproduced to 0.0004%.
    emissivity = float(thermal.get("emissivity", 0.0)) if thermal_bodies else 0.0
    radiating = emissivity > 0.0
    rad_t_ext = float(thermal.get("rad_t_ext", thermal.get("t_ext", 293.15)))
    # temperature-dependent conductivity k(T) = k0*(1 + beta*(T - t_ref))
    # (MAGNETICS_DEPTH_PLAN §2) — also makes the steady heat solve nonlinear
    k_temp_dep = thermal_bodies and any(
        float(tb.get("k_beta", 0.0)) != 0.0 for tb in thermal_bodies.values())
    heat_nonlinear = radiating or k_temp_dep
    k_tref = float(thermal.get("t_ext", 293.15))
    # temperature-dependent electric conductivity σ(T) = σ0/(1 + α·(T − t_ext))
    # (MAGNETICS_DEPTH_PLAN §3) — the harmonic magnetic solve becomes two-way
    # coupled to the heat equation: steady decks gain an outer
    # Steady State Max Iterations loop (the solvers already Exec Always);
    # transient decks drop the single-shot "Before Simulation" field solve and
    # re-solve every timestep (one-step-lagged coupling, de-risked 2026-07-16).
    sigma_t_bodies = [b["name"] for b in bodies
                      if not b.get("coil") and float(b.get("sigma_alpha", 0.0)) != 0.0]
    for name in sigma_t_bodies:
        if name not in thermal_bodies:
            raise ElmerModelError(
                "'{0}' has sigma_alpha (σ(T)) but is not a thermal body — the "
                "conductivity MATC reads Temperature, so give the body a "
                "thermal entry (k > 0)".format(name))
    sigma_coupled = bool(sigma_t_bodies)

    # DC magnetostatics mode (MAGNETICS_DEPTH_PLAN §4): scalar-Potential
    # MagnetoDynamics2D, plain real sources/BCs, no eddy/Joule quantities
    static = bool(model.get("static"))
    if static and thermal_bodies:
        raise ElmerModelError(
            "Static (DC) analysis has no eddy currents or Joule heating — "
            "the thermal chain needs Harmonic (AC)")
    if static:
        for b in coils:
            if float(b["coil"].get("phase_deg", 0.0)) % 360.0 != 0.0:
                raise ElmerModelError(
                    "coil '{0}': phase is meaningless at DC — set PhaseDeg 0 "
                    "for the Static analysis".format(b["name"]))

    # nonlinear B-H bodies (MAGNETICS_DEPTH_PLAN §4): the table replaces
    # Relative Permeability, and Solver 1 gains a REAL nonlinear block —
    # the hard-coded single iteration silently disables the curve (exit 0,
    # linear initial-µ result, +93% flux linkage at deep saturation)
    bh_bodies = []
    for b in bodies:
        if b.get("coil") or not b.get("bh"):
            continue
        validate_bh_table(b["bh"], b["name"])
        bh_bodies.append(b["name"])
    if bh_bodies and sigma_coupled:
        raise ElmerModelError(
            "nonlinear B-H and σ(T) in the same model is not yet validated "
            "together — drop ConductivityTempCoeff or the B-H curve")
    # transient heating: {total_time_s, n_steps, rho, cp}. The harmonic field is
    # constant in time (linear, temperature-independent σ) so it is solved ONCE
    # ("Before Simulation") and the heat equation is time-stepped.
    transient = thermal.get("transient") if thermal_bodies else None
    if transient:
        for key in ("total_time_s", "n_steps"):
            if not transient.get(key):
                raise ElmerModelError("transient thermal needs '{0}'".format(key))
        for name, tb in thermal_bodies.items():
            if not tb.get("rho") or not tb.get("cp"):
                raise ElmerModelError(
                    "transient heating needs Density and SpecificHeat on the "
                    "material of '{0}'".format(name))

    L = []
    w = L.append
    w("! EMStudio — axisymmetric harmonic magnetodynamics (generated)")
    w("! f = {0:.9g} Hz; bodies: {1}".format(
        f_hz, ", ".join("{0}={1}".format(n, i) for n, i in sorted(body_ids.items(), key=lambda kv: kv[1]))))
    w('Check Keywords "Warn"')
    w("")
    w("Header")
    w('  Mesh DB "." "{0}"'.format(mesh_dir))
    w("End")
    w("")
    w("Simulation")
    w('  Coordinate System = "Axi Symmetric"')
    if transient:
        dt = float(transient["total_time_s"]) / int(transient["n_steps"])
        w("  Simulation Type = Transient")
        w("  Timestepping Method = BDF")
        w("  BDF Order = 2")
        w("  Timestep Intervals(1) = {0}".format(int(transient["n_steps"])))
        w("  Timestep Sizes(1) = Real {0:.9g}".format(dt))
        w("  Steady State Max Iterations = 1")
    else:
        w("  Simulation Type = Steady State")
        if sigma_coupled:
            # outer σ(T) coupling loop; exits early on the per-solver
            # steady-state tolerances (probe: 5 iterations; NO relaxation —
            # it provably slows this monotone iteration)
            w("  Steady State Max Iterations = {0}".format(COUPLED_MAX_ITERATIONS))
        else:
            w("  Steady State Max Iterations = 1")
    w("  Output Intervals = 1")
    w("  Coordinate Scaling = Real 0.001  ! mesh is in mm")
    w("End")
    w("")
    w("Constants")
    w("  Permeability of Vacuum = Real {0:.12g}".format(MU0))
    if radiating:
        # MANDATORY when radiating — no Elmer default (ListGetConstReal STOP)
        w("  Stefan Boltzmann = Real {0:.9g}".format(STEFAN_BOLTZMANN))
    w("End")
    w("")

    # ---------- bodies / materials / body forces ----------
    mat_id = {}
    force_id = {}
    next_mat = 1
    next_force = 1
    for b in bodies:
        mat_id[b["name"]] = next_mat
        next_mat += 1
        if b.get("coil") or b["name"] in thermal_bodies:
            force_id[b["name"]] = next_force
            next_force += 1
    air_mat = next_mat  # air gets its own material section

    for b in bodies:
        w("Body {0}".format(body_ids[b["name"]]))
        w('  Name = "{0}"'.format(b["name"]))
        w("  Equation = {0}".format(2 if b["name"] in thermal_bodies else 1))
        w("  Material = {0}".format(mat_id[b["name"]]))
        if b["name"] in force_id:
            w("  Body Force = {0}".format(force_id[b["name"]]))
        if (transient or heat_nonlinear or sigma_coupled) and b["name"] in thermal_bodies:
            w("  Initial Condition = 1")
        if float(b.get("sigma", 0.0)) > 0.0:
            w("  Save Scalars = Logical True  ! mask: include in 'body int' totals")
        w("End")
        w("")
    w("Body {0}".format(body_ids["air"]))
    w('  Name = "air"')
    w("  Equation = 1")
    w("  Material = {0}".format(air_mat))
    w("End")
    w("")

    w("Equation 1")
    w("  Active Solvers(2) = 1 2")
    w("End")
    w("")
    if thermal_bodies:
        w("Equation 2  ! magnetics + heat (thermal bodies)")
        w("  Active Solvers(3) = 1 2 3")
        w("End")
        w("")

    # ---------- solvers ----------
    # Transient: solve the (time-constant) field once, before time-stepping —
    # unless σ(T) couples the field back to temperature; then it re-solves
    # every timestep (weak/lagged coupling, verified stable in the probe).
    once = ('  Exec Solver = "Before Simulation"'
            if (transient and not sigma_coupled) else None)
    w("Solver 1")
    if static:
        w('  Equation = "MgDyn2D"')
        w('  Procedure = "MagnetoDynamics2D" "MagnetoDynamics2D"')
        w('  Variable = "Potential"')
    else:
        w('  Equation = "MgDyn2DHarmonic"')
        w('  Procedure = "MagnetoDynamics2D" "MagnetoDynamics2DHarmonic"')
        w('  Variable = "Potential[Potential Re:1 Potential Im:1]"')
        w("  Frequency = Real {0:.9g}".format(f_hz))
    if once:
        w(once)
    w("  Linear System Solver = Direct")
    w("  Linear System Direct Method = UMFPACK")
    if bh_bodies:
        # a single nonlinear iteration SILENTLY DISABLES the H-B curve in
        # both solvers (Elmer's own default; exit 0, no diagnostics).
        # Newton auto-enables from iteration 2 on v26.2 — the keyword is
        # insurance. Harmonic's σ>0 fixed point stalls near 1.2e-6, hence
        # the looser harmonic tolerance (both probed 2026-07-16).
        w("  Nonlinear System Max Iterations = 100")
        w("  Nonlinear System Convergence Tolerance = 1.0e-{0}".format(
            8 if static else 6))
        w("  Newton-Raphson Iteration = Logical True")
    else:
        w("  Nonlinear System Max Iterations = 1")
    w("  Steady State Convergence Tolerance = 1e-6")
    w("End")
    w("")
    w("Solver 2")
    w('  Equation = "CalcFields"')
    w('  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"')
    w('  Potential Variable = "Potential"')
    if not static:
        # Joule heating / current density are eddy quantities — meaningless
        # (and unavailable) in DC magnetostatics
        w("  Calculate Joule Heating = Logical True")
    w("  Calculate Magnetic Field Strength = Logical True")
    if not static:
        w("  Calculate Current Density = Logical True")
    if once:
        w(once)
    w("  Linear System Solver = Iterative")
    w("  Linear System Iterative Method = CG")
    w("  Linear System Max Iterations = 1000")
    w("  Linear System Convergence Tolerance = 1e-8")
    w("End")
    w("")
    next_solver = 3
    if thermal_bodies:
        w("Solver 3")
        w('  Equation = "Heat Equation"')
        w('  Procedure = "HeatSolve" "HeatSolver"')
        w('  Variable = "Temperature"')
        w("  Steady State Convergence Tolerance = 1e-6")
        if heat_nonlinear:
            # A nonlinear heat equation (radiation T^4 and/or k(T)): a
            # hard-coded single iteration is SILENTLY CATASTROPHIC for
            # radiation (Elmer v26.2 returned T ~ -1e14 K at exit 0) and
            # simply wrong for k(T). Newton-after-Picard converges from a
            # cold start in ~12 iterations (de-risk probe).
            w("  Nonlinear System Max Iterations = 50")
            w("  Nonlinear System Convergence Tolerance = 1.0e-8")
            w("  Nonlinear System Newton After Tolerance = 1.0e-2")
            w("  Nonlinear System Newton After Iterations = 5")
            w("  Nonlinear System Relaxation Factor = Real 1.0")
        else:
            w("  Nonlinear System Max Iterations = 1")
        w("  Linear System Solver = Direct")
        w("  Linear System Direct Method = UMFPACK")
        w("End")
        w("")
        next_solver = 4
    w("Solver {0}".format(next_solver))
    w('  Equation = "ResultOutput"')
    # transient: one final-state VTU (After Simulation) instead of per-timestep.
    # σ(T) coupled decks MUST also use After Simulation: with the outer loop,
    # After Timestep writes one VTU per iteration and case_t0001.vtu would be
    # the FIRST (uncoupled, constant-σ) field — silent garbage for the reader.
    w("  Exec Solver = {0}".format(
        '"After Simulation"' if (transient or sigma_coupled) else "After Timestep"))
    w('  Procedure = "ResultOutputSolve" "ResultOutputSolver"')
    w('  Output File Name = "{0}"'.format(vtu_name))
    w("  Vtu Format = Logical True")
    w("  Ascii Output = Logical True")
    w("  Save Geometry Ids = Logical True")
    w("  Coordinate Scaling Revert = Logical True  ! VTU back in mm, overlays geometry")
    w("End")
    w("")
    w("Solver {0}".format(next_solver + 1))
    w('  Equation = "SaveScalars"')
    w("  Exec Solver = After Timestep")
    w('  Procedure = "SaveData" "SaveScalars"')
    w('  Filename = "scalars.dat"')
    if transient:
        # per-timestep heating curve: time + max temperature (+ auto-injected
        # eddy-current-power/field-energy columns the runner also reads)
        w('  Variable 1 = "Time"')
        w('  Variable 2 = "Temperature"')
        w('  Operator 2 = "max"')
    elif static:
        # DC: no Joule Heating field exists — save a variable that always
        # does, so scalars.dat stays parseable (flux linkage comes from VTU)
        w('  Variable 1 = "Potential"')
        w('  Operator 1 = "max"')
    else:
        w('  Variable 1 = "Joule Heating"')
        w('  Operator 1 = "body int"')
    w("End")
    w("")

    # ---------- materials ----------
    for b in bodies:
        sigma = 0.0 if b.get("coil") else float(b.get("sigma", 0.0))
        sigma_alpha = 0.0 if b.get("coil") else float(b.get("sigma_alpha", 0.0))
        w("Material {0}".format(mat_id[b["name"]]))
        w('  Name = "{0}"'.format(b["name"]))
        if b["name"] in bh_bodies:
            # nonlinear iron: the H-B table REPLACES Relative Permeability
            # (columns B [T] then H [A/m] — swapped runs silently wrong)
            w('  H-B Curve = Variable "dummy"')
            w("    Real Monotone Cubic")
            for b_t, h_am in b["bh"]:
                w("      {0:.9g} {1:.9g}".format(float(b_t), float(h_am)))
            w("    End")
        else:
            w("  Relative Permeability = Real {0:.9g}".format(float(b.get("mu_r", 1.0))))
        if sigma_alpha != 0.0:
            # σ(T) = σ0/(1 + α·(T − t_ref)) — resistivity linear in T; tx = T
            # in K. The ambient Initial Condition emitted below is MANDATORY:
            # without it iteration 1 evaluates T = 0, the denominator goes
            # negative for any metal (α·T_ref > 1) and Elmer proceeds on a
            # NEGATIVE conductivity silently at exit 0 (de-risk 2026-07-16).
            w("  Electric Conductivity = Variable Temperature")
            w('    Real MATC "{0:.9g}/(1+{1:.9g}*(tx-{2:.9g}))"'.format(
                sigma, sigma_alpha, k_tref))
        else:
            w("  Electric Conductivity = Real {0:.9g}".format(sigma))
        if b.get("coil"):
            w("  ! stranded coil: bulk conductivity forced 0 (litz/wound source)")
        if b["name"] in thermal_bodies:
            tb_k = thermal_bodies[b["name"]]
            k0 = float(tb_k["k"])
            beta = float(tb_k.get("k_beta", 0.0))
            if beta != 0.0:
                # k(T) = k0*(1 + beta*(T - t_ref)); tx = Temperature (K)
                w('  Heat Conductivity = Variable Temperature')
                w('    Real MATC "{0:.9g}*(1+{1:.9g}*(tx-{2:.9g}))"'.format(
                    k0, beta, k_tref))
            else:
                w("  Heat Conductivity = Real {0:.9g}".format(k0))
            if transient:
                # rho and c_p give the transient heat-capacity term rho*c*dT/dt
                tb = thermal_bodies[b["name"]]
                w("  Density = Real {0:.9g}".format(float(tb["rho"])))
                w("  Heat Capacity = Real {0:.9g}".format(float(tb["cp"])))
        w("End")
        w("")
    w("Material {0}".format(air_mat))
    w('  Name = "air"')
    w("  Relative Permeability = Real 1.0")
    w("  Electric Conductivity = Real 0.0")
    w("End")
    w("")

    # ---------- initial condition (start at ambient) ----------
    # Transient needs it for t=0; the nonlinear steady solve (radiation
    # and/or k(T)) gets one too — the de-risk probe found Picard-only
    # diverges without an ambient seed (Newton is robust from cold, but the
    # seed is free insurance and matches the validated deck). σ(T) decks
    # REQUIRE it: iteration 1 must see ambient T, or σ evaluates on T = 0
    # and goes negative silently (see the material-section comment).
    if transient or heat_nonlinear or sigma_coupled:
        w("Initial Condition 1")
        w('  Name = "ambient"')
        w("  Temperature = Real {0:.9g}".format(float(thermal.get("t_ext", 293.15))))
        w("End")
        w("")

    # ---------- body forces (coil source currents + Joule heat coupling) ----------
    for b in bodies:
        if b["name"] not in force_id:
            continue
        w("Body Force {0}".format(force_id[b["name"]]))
        w('  Name = "{0}_force"'.format(b["name"]))
        if b.get("coil"):
            override = (ref_currents or {}).get(b["name"])
            if override is not None:
                j_re, j_im = coil_current_density(b, current_override=override)
            else:
                j_re, j_im = coil_current_density(b, excitation.get(b["name"], 0.0))
            w("  Current Density = Real {0:.9g}".format(j_re))
            if not static:
                # DC has no imaginary part (phase validated 0 above)
                w("  Current Density Im = Real {0:.9g}".format(j_im))
        if b["name"] in thermal_bodies:
            # Elmer's built-in EM->heat coupling: HeatSolver integrates the
            # Joule source consistently from the harmonic solution. Do NOT
            # replace with 'Heat Source = Equals "Joule Heating"' — the nodal
            # projection loses 3-8% of the power at practical meshes
            # (energy balance verified to -0.00% on 2026-07-06)
            w("  Joule Heat = Logical True")
        w("End")
        w("")

    # ---------- boundary conditions ----------
    bc_sections = {}
    section = 1
    for name in ("router", "ztop", "zbottom", "axis"):
        spec = bc.get(name)
        if spec is None:
            continue  # natural boundary
        if name not in boundary_ids:
            raise ElmerModelError("mesh has no boundary group '{0}'".format(name))
        L.extend(_bc_lines(name, spec, section, boundary_ids[name], static=static))
        bc_sections[name] = section
        section += 1
    if thermal_bodies:
        h = float(thermal.get("h", 10.0))
        t_ext = float(thermal.get("t_ext", 293.15))
        for name in thermal_bodies:
            group = "surf_" + name
            if group not in boundary_ids:
                raise ElmerModelError(
                    "mesh has no '{0}' boundary group — thermal bodies must not "
                    "touch the domain boundary".format(group))
            w("Boundary Condition {0}".format(section))
            w('  Name = "{0}"'.format(group))
            w("  Target Boundaries(1) = {0}".format(boundary_ids[group]))
            w("  Heat Transfer Coefficient = Real {0:.9g}".format(h))
            w("  External Temperature = Real {0:.9g}".format(t_ext))
            if radiating:
                # grey-body radiation to a fixed enclosure at rad_t_ext;
                # stacks additively with the convection pair above
                w("  Radiation = String Idealized")
                w("  Radiation External Temperature = Real {0:.9g}".format(
                    rad_t_ext))
                w("  Emissivity = Real {0:.9g}".format(emissivity))
            w("End")
            w("")
            bc_sections[group] = section
            section += 1

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path, bc_sections


def _has_field_bc(spec):
    if not spec:
        return False
    return any(spec.get(k) for k in ("re", "im", "matc_re", "matc_im"))
