# SPDX-License-Identifier: LGPL-2.1-or-later
"""Palace eigenmode pipeline: Prepare -> Mesh -> Solve -> Results.

Pipeline::

    msh    = gmsh_box.mesh_box(size_mm, workdir)      # 3-D tet mesh (msh2.2)
    config = writer.build_eigenmode_config(...)        # config.json
    palace -np 1 config.json                           # solve
    modes  = parser.parse_eigenvalues(postpro/eig.csv) # results

Palace is invoked through its MPI wrapper (``palace -np N config.json``);
the binary is resolved via ``emstudio.setup.solvers.find_backend("palace")``.
FreeCAD-free ``run_cavity`` for gates; ``run`` for the FreeCAD analysis.
"""
from __future__ import annotations

import math
import os

from emstudio.meshing import gmsh_box, gmsh_brep, gmsh_coax
from emstudio.setup import solvers as solver_setup
from emstudio.solvers import progress
from emstudio.solvers.base import SolverError, SolverJob, make_workdir

from . import parser, writer

_SOLVE_TIMEOUT_S = 3600
_C0 = 299792458.0


def _estimate_target_ghz(size_mm, eps_r=1.0):
    """Rough TE101-ish frequency (GHz) for the shift-invert target.

    Uses the two largest box dimensions (the fundamental has one node across
    each). Only needs to be in the right ballpark to seed the eigensolver.
    """
    dims_m = sorted(s * 1e-3 for s in size_mm)
    a, d = dims_m[-1], dims_m[-2]  # two largest
    f = (_C0 / (2.0 * math.sqrt(eps_r))) * math.sqrt((1.0 / a) ** 2 + (1.0 / d) ** 2)
    return f / 1e9


def run_cavity(size_mm, n_modes=8, order=2, elem_mm=None, eps_r=1.0, mu_r=1.0,
               loss_tan=0.0, target_ghz=None, workdir=None, line_callback=None,
               mesh_refinement=0, refinement_tol=0.01):
    """Solve the resonant modes of a rectangular PEC cavity. Returns EigenModeResult.

    :param size_mm: (dx, dy, dz) cavity dimensions in mm.
    :param order: FEM polynomial order. 2 is the default (well under 1% on a
        coarse tet mesh, and much faster than 3 — the order-3 geometric
        multigrid preconditioner setup dominates wall-clock); raise to 3-4 for
        spectral-quality accuracy.
    :param mesh_refinement: AMR iterations (0 = off; adaptive refinement re-solves
        on a mesh refined where the error indicator is largest).
    """
    import time

    t0 = time.time()
    workdir = _prepare_workdir(workdir)
    msh = gmsh_box.mesh_box(size_mm, workdir, elem_mm=elem_mm,
                            line_callback=line_callback)
    if target_ghz is None:
        target_ghz = _estimate_target_ghz(size_mm, eps_r) * 0.95  # just below the fundamental
    return _solve_eigenmodes(
        msh, workdir, t0, n_modes=n_modes, order=order, eps_r=eps_r, mu_r=mu_r,
        loss_tan=loss_tan, target_ghz=target_ghz,
        extra_meta={"size_mm": tuple(size_mm)}, line_callback=line_callback,
        mesh_refinement=mesh_refinement, refinement_tol=refinement_tol)


def run_cavity_brep(brep_path, target_ghz, n_modes=8, order=2, eps_r=1.0, mu_r=1.0,
                    loss_tan=0.0, elem_mm=None, workdir=None, line_callback=None,
                    mesh_refinement=0, refinement_tol=0.01):
    """Solve the resonant modes of a general PEC-walled solid (BREP). Returns EigenModeResult.

    The whole outer boundary of the imported solid is the PEC wall — any single
    closed solid works (cylinder, sphere, chamfered box, …), not just a box.

    :param brep_path: BREP file of the cavity interior (mm).
    :param target_ghz: shift-invert target just below the fundamental (the
        caller seeds it from the geometry bounding box — a raw BREP carries no
        size for the box heuristic).
    :param mesh_refinement: AMR iterations (0 = off; adaptive refinement re-solves
        on a mesh refined where the error indicator is largest).
    """
    import time

    t0 = time.time()
    workdir = _prepare_workdir(workdir)
    msh = gmsh_brep.mesh_brep(brep_path, workdir, elem_mm=elem_mm,
                              line_callback=line_callback)
    return _solve_eigenmodes(
        msh, workdir, t0, n_modes=n_modes, order=order, eps_r=eps_r, mu_r=mu_r,
        loss_tan=loss_tan, target_ghz=float(target_ghz),
        extra_meta={"geometry": "brep"}, line_callback=line_callback,
        mesh_refinement=mesh_refinement, refinement_tol=refinement_tol)


def _prepare_workdir(workdir):
    info = solver_setup.find_backend("palace")
    if not info.found:
        raise SolverError("Palace not found.\n" + solver_setup.install_hint(info.backend))
    return make_workdir("emstudio_palace_", base=workdir)


def _solve_eigenmodes(msh, workdir, t0, n_modes, order, eps_r, mu_r, loss_tan,
                      target_ghz, extra_meta=None, line_callback=None,
                      mesh_refinement=0, refinement_tol=0.01):
    """Shared eigenmode solve/parse tail for run_cavity and run_cavity_brep.

    Identical config + Palace invocation + parsing for every geometry, so the
    box and BREP paths never diverge.
    """
    import time

    from emstudio.post.eigenmodes import EigenModeResult

    info = solver_setup.find_backend("palace")
    config = writer.build_eigenmode_config(
        os.path.basename(msh), n_modes=n_modes, target_ghz=target_ghz, order=order,
        eps_r=eps_r, mu_r=mu_r, loss_tan=loss_tan, output="postpro",
        mesh_refinement=mesh_refinement, refinement_tol=refinement_tol)
    cfg_path = writer.write_config(config, os.path.join(workdir, "config.json"))

    # PHASE progress only. Palace is one long invocation and is not installed
    # on the machine this was written on, so any regex against its output
    # would be a guess; phase boundaries need no parsing and cannot be wrong.
    # Tighten to a real fraction on a box that has Palace.
    progress.report(line_callback, 0.05, "Solving (Palace)")
    job = SolverJob([info.path, "-np", "1", os.path.basename(cfg_path)],
                    cwd=workdir, line_callback=line_callback)
    job.run_blocking(timeout=_SOLVE_TIMEOUT_S)
    progress.report(line_callback, 0.90, "Reading results")

    eig_csv = os.path.join(workdir, "postpro", "eig.csv")
    if not os.path.isfile(eig_csv):
        raise SolverError("Palace produced no eigenvalues at {0}".format(eig_csv))
    modes = parser.parse_eigenvalues(eig_csv)
    meta = {"backend": "palace", "workdir": workdir, "duration_s": time.time() - t0}
    meta.update(extra_meta or {})
    result = EigenModeResult(modes, meta=meta)
    result.save_csv(os.path.join(workdir, "eigenmodes.csv"))
    return result


def _excitation_list(n_ports, full_smatrix):
    """Which ports to drive: every one for a full matrix, else just port 1.

    ⚠ **Not the literal ``[1, 2]``.** That was correct only while every driven
    geometry had exactly two ends. On a 3-port junction it would solve two
    columns of a 3x3, and the export would then refuse to write anything at all
    — which reads like a solver problem and is in fact a caller bug two files
    away. The count comes from the mesh, so the two cannot disagree.
    """
    n = int(n_ports)
    if n < 1:
        raise SolverError("a driven solve needs at least one port; got %r" % (n_ports,))
    return list(range(1, n + 1)) if full_smatrix else [1]


def _solve_excitations(info, workdir, build_cfg, ports, line_callback,
                       base=0.05, span=0.85):
    """Run one driven solve per excitation and merge them into one S-matrix.

    ``build_cfg(excite_port, output_dir)`` returns the config for that
    excitation. Every run reuses the SAME MESH — only the driven port changes —
    which is what makes the merged matrix consistent: two solves on different
    discretisations would give an S-matrix whose columns disagree about the
    geometry.

    Each excitation writes to its own ``postpro_eN`` so a later run cannot
    overwrite an earlier one's ``port-S.csv``, and the progress span is divided
    evenly, so an N-port run's bar still moves 0 -> 1 across the whole job
    rather than resetting once per excitation.

    Returns ``(freq_hz, {(observed, excited): array})``.
    """
    from emstudio.post.sparams import merge_excitations

    runs = []
    n = max(1, len(ports))
    for k, ep in enumerate(ports):
        out = "postpro_e%d" % int(ep)
        cfg = build_cfg(int(ep), out)
        cfg_path = writer.write_config(
            cfg, os.path.join(workdir, "config_e%d.json" % int(ep)))
        progress.report(line_callback, base + span * (k / float(n)),
                        "Solving (Palace), excitation %d of %d" % (k + 1, n))
        job = SolverJob([info.path, "-np", "1", os.path.basename(cfg_path)],
                        cwd=workdir, line_callback=line_callback)
        job.run_blocking(timeout=_SOLVE_TIMEOUT_S)

        port_s = os.path.join(workdir, out, "port-S.csv")
        if not os.path.isfile(port_s):
            raise SolverError(
                "Palace produced no S-parameters for excitation {0} at {1}"
                .format(ep, port_s))
        data = parser.parse_sparams(port_s)
        runs.append((data["freq_hz"], data["s"]))
    return merge_excitations(runs)


def run_waveguide(size_mm, axis=2, f1_ghz=8.0, f2_ghz=12.0, step_ghz=0.5, order=3,
                  eps_r=1.0, mu_r=1.0, loss_tan=0.0, elem_mm=None, workdir=None,
                  line_callback=None, fast_sweep=False, adaptive_tol=1.0e-3,
                  mesh_refinement=0, refinement_tol=0.01, full_smatrix=False):
    """Driven S-parameter solve of a 2-port waveguide section. Returns SweepResult.

    :param size_mm: (dx, dy, dz) box dimensions in mm.
    :param axis: propagation axis (0=x, 1=y, 2=z); the two faces perpendicular
        to it are the wave ports.
    :param mesh_refinement: AMR iterations (0 = off; adaptive refinement re-solves
        on a mesh refined where the error indicator is largest).
    """
    import time

    import numpy as np

    from emstudio.post.sparams import SweepResult

    t0 = time.time()
    info = solver_setup.find_backend("palace")
    if not info.found:
        raise SolverError("Palace not found.\n" + solver_setup.install_hint(info.backend))
    workdir = make_workdir("emstudio_palace_", base=workdir)

    msh = gmsh_box.mesh_waveguide(size_mm, workdir, axis=axis, elem_mm=elem_mm,
                                  line_callback=line_callback)
    def build_cfg(excite_port, output):
        return writer.build_driven_config(
            os.path.basename(msh), f1_ghz, f2_ghz, step_ghz, order=order,
            excite_port=excite_port,
            eps_r=eps_r, mu_r=mu_r, loss_tan=loss_tan, output=output,
            fast_sweep=fast_sweep, adaptive_tol=adaptive_tol,
            mesh_refinement=mesh_refinement, refinement_tol=refinement_tol)

    # PHASE progress only. Palace is one long invocation and is not installed
    # on the machine this was written on, so any regex against its output
    # would be a guess; phase boundaries need no parsing and cannot be wrong.
    # Tighten to a real fraction on a box that has Palace.
    # A box section has two ends, so this geometry is a 2-port; the
    # count is stated once here and shared by the mesh and the config.
    n_ports = 2
    ports = _excitation_list(n_ports, full_smatrix)
    freqs, smat = _solve_excitations(info, workdir, build_cfg, ports,
                                     line_callback)
    progress.report(line_callback, 0.90, "Reading results")

    freqs = np.array(freqs)
    n = len(freqs)
    s11 = np.array(smat.get((1, 1), [0j] * n))
    s21 = np.array(smat.get((2, 1), [0j] * n))
    z0 = 50.0  # nominal; wave-port S-params are already modally normalized
    zin = z0 * (1.0 + s11) / (1.0 - s11)
    result = SweepResult(freqs, zin, z0=z0, s11=s11, meta={
        "backend": "palace",
        "workdir": workdir,
        "duration_s": time.time() - t0,
        "analysis_type": "driven",
    })
    result.s_others = {k: np.array(v) for k, v in smat.items() if k != (1, 1)}
    result.save_csv(os.path.join(workdir, "port_1.csv"))
    return result


def run_waveguide_brep(brep_path, axis, bbox_mm, f1_ghz=8.0, f2_ghz=12.0,
                       step_ghz=0.5, order=2, eps_r=1.0, mu_r=1.0, loss_tan=0.0,
                       elem_mm=None, workdir=None, line_callback=None,
                       fast_sweep=False, adaptive_tol=1.0e-3, mesh_refinement=0,
                       refinement_tol=0.01, full_smatrix=False, ports=None):
    """Driven S-parameter solve of an N-port waveguide on a GENERAL solid (BREP).

    The general-geometry analogue of :func:`run_waveguide`: any closed solid
    (circular cylinder, tapered/stepped guide, T-junction, …) exported to a
    BREP, with selected faces tagged as wave ports and the rest PEC. Palace's
    ``Mode 1`` wave port finds the dominant mode on each port face
    automatically (e.g. TE11 on a circular face). Returns a SweepResult. Verified
    vs the box waveguide (WR-90) and a circular-waveguide TE11 cutoff 2026-07-07.

    ⚠ **This is the only driven path that can carry more than two ports** — the
    box and coax geometries have two ends and no third face to put a port on.
    An N-port S-matrix therefore means a BREP with ``ports`` given explicitly.

    :param axis: propagation axis (0=x, 1=y, 2=z), used when ``ports`` is not
        given: its two end faces become ports 1 and 2.
    :param bbox_mm: ``(xmin, ymin, zmin, xmax, ymax, zmax)`` of the solid, mm.
    :param order: FEM order — default 2 (order 3 is very slow per point on a
        curved guide, especially at deep-evanescent below-cutoff points).
    :param ports: optional explicit port faces — see
        ``gmsh_brep.normalise_port_faces``. Their ORDER is the port numbering.
    """
    import time

    import numpy as np

    from emstudio.post.sparams import SweepResult

    t0 = time.time()
    info = solver_setup.find_backend("palace")
    if not info.found:
        raise SolverError("Palace not found.\n" + solver_setup.install_hint(info.backend))
    workdir = make_workdir("emstudio_palace_", base=workdir)

    # The port count comes from the SAME normalisation the mesher uses, so the
    # config's port/wall attributes cannot disagree with the mesh's tags. Two
    # sources of truth here is exactly how a wall gets tagged with a port's
    # attribute, which Palace does not report as the error it is.
    faces = gmsh_brep.normalise_port_faces(ports, axis)
    n_ports = len(faces)
    msh = gmsh_brep.mesh_brep_driven(brep_path, workdir, axis, bbox_mm,
                                     elem_mm=elem_mm, line_callback=line_callback,
                                     ports=faces)
    def build_cfg(excite_port, output):
        return writer.build_driven_config(
            os.path.basename(msh), f1_ghz, f2_ghz, step_ghz, order=order,
            excite_port=excite_port,
            eps_r=eps_r, mu_r=mu_r, loss_tan=loss_tan, output=output,
            fast_sweep=fast_sweep, adaptive_tol=adaptive_tol,
            mesh_refinement=mesh_refinement, refinement_tol=refinement_tol,
            n_ports=n_ports)

    # PHASE progress only. Palace is one long invocation and is not installed
    # on the machine this was written on, so any regex against its output
    # would be a guess; phase boundaries need no parsing and cannot be wrong.
    # Tighten to a real fraction on a box that has Palace.
    ports = _excitation_list(n_ports, full_smatrix)
    freqs, smat = _solve_excitations(info, workdir, build_cfg, ports,
                                     line_callback)
    progress.report(line_callback, 0.90, "Reading results")

    freqs = np.array(freqs)
    n = len(freqs)
    s11 = np.array(smat.get((1, 1), [0j] * n))
    s21 = np.array(smat.get((2, 1), [0j] * n))
    z0 = 50.0  # nominal; wave-port S-params are already modally normalized
    zin = z0 * (1.0 + s11) / (1.0 - s11)
    result = SweepResult(freqs, zin, z0=z0, s11=s11, meta={
        "backend": "palace",
        "workdir": workdir,
        "duration_s": time.time() - t0,
        "analysis_type": "driven_brep",
    })
    result.s_others = {k: np.array(v) for k, v in smat.items() if k != (1, 1)}
    result.save_csv(os.path.join(workdir, "port_1.csv"))
    return result


def run_coax(a_mm, b_mm, length_mm, f1_ghz=1.0, f2_ghz=5.0, step_ghz=1.0, order=2,
             eps_r=1.0, mu_r=1.0, loss_tan=0.0, elem_mm=None, workdir=None,
             line_callback=None, fast_sweep=False, adaptive_tol=1.0e-3,
             mesh_refinement=0, refinement_tol=0.01, full_smatrix=False):
    """Driven S-parameter solve of a 2-port coaxial line (radial lumped ports).

    Returns a SweepResult. A default run excites port 1 only, giving S11 and
    S21 — one COLUMN of the S-matrix. Pass ``full_smatrix=True`` to excite each
    port in turn on the SAME mesh and get the complete 2x2, which is what a
    .s2p export needs; it costs a second solve. The port reference
    impedance is the analytic coax Z0, so a uniform line is matched.

    :param a_mm: inner conductor radius (mm); :param b_mm: outer radius (mm).
    :param mesh_refinement: AMR iterations (0 = off; adaptive refinement re-solves
        on a mesh refined where the error indicator is largest).
    """
    import time

    import numpy as np

    from emstudio.post.sparams import SweepResult

    t0 = time.time()
    info = solver_setup.find_backend("palace")
    if not info.found:
        raise SolverError("Palace not found.\n" + solver_setup.install_hint(info.backend))
    workdir = make_workdir("emstudio_palace_", base=workdir)

    msh = gmsh_coax.mesh_coax(a_mm, b_mm, length_mm, workdir, elem_mm=elem_mm,
                              line_callback=line_callback)
    def build_cfg(excite_port, output):
        return writer.build_lumped_coax_config(
            os.path.basename(msh), f1_ghz, f2_ghz, step_ghz, a_mm, b_mm,
            order=order, excite_port=excite_port,
            eps_r=eps_r, mu_r=mu_r, loss_tan=loss_tan, output=output,
            fast_sweep=fast_sweep, adaptive_tol=adaptive_tol,
            mesh_refinement=mesh_refinement, refinement_tol=refinement_tol)

    # PHASE progress only. Palace is one long invocation and is not installed
    # on the machine this was written on, so any regex against its output
    # would be a guess; phase boundaries need no parsing and cannot be wrong.
    # Tighten to a real fraction on a box that has Palace.
    # A coaxial section has two ends — see build_lumped_coax_config.
    n_ports = 2
    ports = _excitation_list(n_ports, full_smatrix)
    freqs, smat = _solve_excitations(info, workdir, build_cfg, ports,
                                     line_callback)
    progress.report(line_callback, 0.90, "Reading results")

    freqs = np.array(freqs)
    n = len(freqs)
    s11 = np.array(smat.get((1, 1), [0j] * n))
    s21 = np.array(smat.get((2, 1), [0j] * n))
    z0 = writer.coax_z0(a_mm, b_mm, eps_r)  # analytic coax impedance
    zin = z0 * (1.0 + s11) / (1.0 - s11)
    result = SweepResult(freqs, zin, z0=z0, s11=s11, meta={
        "backend": "palace",
        "workdir": workdir,
        "duration_s": time.time() - t0,
        "analysis_type": "driven_coax",
        "z0_ohm": z0,
    })
    result.s_others = {k: np.array(v) for k, v in smat.items() if k != (1, 1)}
    result.save_csv(os.path.join(workdir, "port_1.csv"))
    return result


def _is_coax(solver):
    return str(getattr(solver, "AnalysisType", "Eigenmode")) == \
        "Driven S-parameters (coax)"


def _is_driven(solver):
    return str(getattr(solver, "AnalysisType", "Eigenmode")) == "Driven S-parameters"


def run(analysis, solver, workdir=None, line_callback=None):
    """Run the Palace pipeline for a FreeCAD analysis (eigenmode or driven).

    Eigenmode -> EigenModeResult (cavity modes). Driven -> SweepResult
    (waveguide S-parameters). Dispatch on the solver's ``AnalysisType``.
    """
    from emstudio.objects.analysis import Analysis

    fast_sweep = bool(getattr(solver, "FastSweep", False))
    adaptive_tol = float(getattr(solver, "AdaptiveTol", 1.0e-3))
    mesh_refinement = int(getattr(solver, "MeshRefinement", 0))
    refinement_tol = float(getattr(solver, "RefinementTol", 0.01))
    full_smatrix = bool(getattr(solver, "FullSMatrix", False))

    if _is_coax(solver):
        from .model import build_coax_model

        model = build_coax_model(analysis, solver)
        f1, f2, npts = Analysis.freq_range_hz(analysis)
        f1_ghz, f2_ghz = f1 / 1e9, f2 / 1e9
        step_ghz = (f2_ghz - f1_ghz) / max(npts - 1, 1) if npts > 1 else 0.5
        result = run_coax(
            model["a_mm"], model["b_mm"], model["length_mm"],
            f1_ghz=f1_ghz, f2_ghz=f2_ghz, step_ghz=step_ghz,
            order=int(getattr(solver, "Order", 2)),
            eps_r=model.get("eps_r", 1.0), mu_r=model.get("mu_r", 1.0),
            loss_tan=model.get("loss_tan", 0.0),
            elem_mm=(model.get("elem_mm") or None),
            workdir=workdir, line_callback=line_callback,
            fast_sweep=fast_sweep, adaptive_tol=adaptive_tol,
            mesh_refinement=mesh_refinement, refinement_tol=refinement_tol,
            full_smatrix=full_smatrix)
        result.meta["analysis"] = analysis.Label
        return result

    if _is_driven(solver):
        from .model import build_waveguide_model

        model = build_waveguide_model(analysis, solver)
        f1, f2, npts = Analysis.freq_range_hz(analysis)
        f1_ghz, f2_ghz = f1 / 1e9, f2 / 1e9
        step_ghz = (f2_ghz - f1_ghz) / max(npts - 1, 1) if npts > 1 else 0.5
        common = dict(
            f1_ghz=f1_ghz, f2_ghz=f2_ghz, step_ghz=step_ghz,
            order=int(getattr(solver, "Order", 3)),
            eps_r=model.get("eps_r", 1.0), mu_r=model.get("mu_r", 1.0),
            loss_tan=model.get("loss_tan", 0.0),
            elem_mm=(model.get("elem_mm") or None),
            workdir=workdir, line_callback=line_callback,
            fast_sweep=fast_sweep, adaptive_tol=adaptive_tol,
            mesh_refinement=mesh_refinement, refinement_tol=refinement_tol,
            full_smatrix=full_smatrix)
        if model.get("kind") == "brep":
            # ⚠ SCOPE, stated rather than implied: the ENGINE below is N-port
            # (mesher, config, excitation loop, merge, .sNp). What is not built
            # is a way for the DOCUMENT to say which face is port 3 —
            # build_waveguide_model still infers two ports from the longest
            # bounding-box axis, so `ports` is None here and every solve driven
            # from the GUI is a 2-port. The seam is live: the day the model
            # dict carries port faces, N-port runs from the tree with no
            # further change here.
            result = run_waveguide_brep(
                model["brep_path"], model["axis"], model["bbox_mm"],
                ports=model.get("ports"), **common)
        else:
            result = run_waveguide(model["size_mm"], axis=model["axis"], **common)
        result.meta["analysis"] = analysis.Label
        return result

    from .model import build_cavity_model

    model = build_cavity_model(analysis, solver)
    common = dict(
        n_modes=int(getattr(solver, "NumModes", 8)),
        order=int(getattr(solver, "Order", 3)),
        elem_mm=(model.get("elem_mm") or None),
        eps_r=model.get("eps_r", 1.0), mu_r=model.get("mu_r", 1.0),
        loss_tan=model.get("loss_tan", 0.0),
        workdir=workdir, line_callback=line_callback,
        mesh_refinement=mesh_refinement, refinement_tol=refinement_tol)
    if model.get("kind") == "brep":
        result = run_cavity_brep(model["brep_path"], model["target_ghz"], **common)
    else:
        result = run_cavity(model["size_mm"], **common)
    result.meta["analysis"] = analysis.Label
    return result
