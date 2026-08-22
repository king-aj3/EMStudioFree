# SPDX-License-Identifier: LGPL-2.1-or-later
"""AWS Palace config-file writer (JSON) for eigenmode cavity analyses.

Writes the ``config.json`` that drives a Palace eigenmode solve of a
PEC-walled dielectric cavity. Verified against Palace (built from source)
on 2026-07-06.

Config conventions this writer encodes (from the working recipe):

* ``Model.L0 = 1e-3`` — mesh coordinates are in mm; Palace scales them to
  metres with L0. Get this wrong and eigenfrequencies come out 1000x off.
* ``Domains.Materials[].Attributes`` / ``Boundaries.PEC.Attributes`` are the
  MFEM attributes = the gmsh physical tags (volume = 1, walls = 2, from
  ``emstudio.meshing.gmsh_box``).
* ``Solver.Eigenmode.Target`` is a frequency in GHz near the modes of
  interest (the shift-invert target); ``N`` is how many modes to return.
* ``Solver.Order`` is the FEM polynomial order (3 gives spectral-quality
  cavity modes on a coarse tet mesh).

Pure JSON via the stdlib; Qt-free and FreeCAD-free.
"""
from __future__ import annotations

import json
import math

from emstudio.meshing.gmsh_box import (
    VOLUME_ATTR,
    WALL_ATTR,
    WG_VOLUME_ATTR,
    wg_port_attr,
    wg_wall_attr,
)
from emstudio.meshing.gmsh_coax import (
    COAX_PORT1_ATTR,
    COAX_PORT2_ATTR,
    COAX_VOLUME_ATTR,
    COAX_WALL_ATTR,
)

ETA0 = 376.730313668  # free-space wave impedance (ohm)


def coax_z0(a_mm, b_mm, eps_r=1.0):
    """TEM characteristic impedance of a coax (ohm): (eta0/2pi)/sqrt(eps)*ln(b/a)."""
    return (ETA0 / (2.0 * math.pi)) / math.sqrt(eps_r) * math.log(b_mm / a_mm)


def _refinement_block(iters, tol=0.01):
    """The ``Model.Refinement`` block: Palace ADAPTIVE MESH REFINEMENT (AMR).

    Palace estimates a per-element error indicator, refines the elements
    carrying the largest fraction of the error, and re-solves — up to
    ``MaxIts`` times or until the global error falls below ``Tol``.

    Placed at MODEL level (not under Solver) so it drives BOTH eigenmode and
    driven analyses identically. ``Nonconformal`` MUST stay ``true`` for gmsh
    tetrahedra: conforming (true-conformal) refinement explodes the element
    count (~3.6x) and runtime (~3x). ``UpdateFraction`` 0.7 marks the elements
    covering 70% of the total error each pass. The FINAL adapted result lands
    in the top-level ``postpro/eig.csv`` / ``port-S.csv`` (so the existing
    ``parse_eigenvalues`` / ``parse_sparams`` read the converged answer with no
    change); per-iteration results live in ``iterationN/`` and the error history
    in ``postpro/error-indicators.csv``.
    """
    return {
        "MaxIts": int(iters),
        "Tol": float(tol),
        "UpdateFraction": 0.7,
        "Nonconformal": True,
    }


def _apply_refinement(config, mesh_refinement, refinement_tol):
    """Inject ``Model.Refinement`` into ``config`` iff AMR is requested.

    When ``mesh_refinement`` is 0 (the default) the config is returned
    UNCHANGED — byte-identical to the pre-AMR writer, so every existing Palace
    gate stays unaffected. Mutates and returns ``config``.
    """
    if mesh_refinement and int(mesh_refinement) > 0:
        config["Model"]["Refinement"] = _refinement_block(mesh_refinement,
                                                          refinement_tol)
    return config


def radiation_boundaries(attr, nsample=64, order=2, theta_phis=None):
    """Boundaries block for an OPEN (radiating) domain.

    Returns the two pieces Palace needs to let a wave leave and then measure
    where it went:

      * ``Absorbing`` — a farfield absorbing (scattering) boundary. ``Order``
        1 or 2; second order is available for FREQUENCY-DOMAIN DRIVEN
        simulations only, which is the case this is for, so 2 is the default
        and is the better absorber.
      * ``Postprocessing.FarField`` — far-field electric-field extraction on
        the SAME attribute. Palace's schema requires these attributes to
        "enclose the system and be on an external boundary", which is exactly
        what :func:`emstudio.meshing.gmsh_box.write_geo_open` tags.

    ⚠⚠ **This is the piece whose absence made Palace look incapable.** The
    docs recorded that nothing radiating was gated above 2.435 GHz and implied
    a Palace limitation. Palace was never the problem: every mesh EMStudio
    handed it tagged the whole outer boundary ``pec_walls``, i.e. a closed
    metal box, and a closed metal box cannot radiate. Palace has supported both
    of these boundaries all along.

    ``nsample`` discretises the far-field sphere; ``theta_phis`` adds specific
    (theta, phi) pairs in degrees, which is how you pin boresight exactly
    rather than hoping a uniform sample lands on it.
    """
    ff = {"Attributes": [int(attr)], "NSample": int(nsample)}
    if theta_phis:
        ff["ThetaPhis"] = [[float(t), float(p)] for t, p in theta_phis]
    return {
        "Absorbing": {"Attributes": [int(attr)], "Order": int(order)},
        "Postprocessing": {"FarField": ff},
    }


def build_eigenmode_config(mesh_name, n_modes=8, target_ghz=1.0, order=3,
                           eps_r=1.0, mu_r=1.0, loss_tan=0.0, output="postpro",
                           save_modes=0, mesh_refinement=0, refinement_tol=0.01, device="CPU"):
    """Return the Palace eigenmode config as a dict.

    :param mesh_name: mesh filename relative to the config (e.g. "cavity.msh").
    :param target_ghz: shift-invert target near the lowest cavity mode.
    :param mesh_refinement: AMR iterations (0 = off; opt-in adaptive refinement).
    """
    return _apply_refinement({
        "Problem": {
            "Type": "Eigenmode",
            "Verbose": 2,
            "Output": output,
        },
        "Model": {
            "Mesh": mesh_name,
            "L0": 1.0e-3,  # mesh is in mm
        },
        "Domains": {
            "Materials": [
                {
                    "Attributes": [VOLUME_ATTR],
                    "Permeability": float(mu_r),
                    "Permittivity": float(eps_r),
                    "LossTan": float(loss_tan),
                }
            ]
        },
        "Boundaries": {
            "PEC": {"Attributes": [WALL_ATTR]},
        },
        "Solver": {
            "Order": int(order),
            # ⚠ "GPU" needs a Palace BUILT with CUDA or HIP. A CPU-only
            # build does not fail on it — MFEM falls back and says so in
            # the log — so this is safe to set, but "it ran" is NOT proof
            # the GPU was used. Read the Palace banner.
            "Device": str(device),
            "Eigenmode": {
                "N": int(n_modes),
                "Tol": 1.0e-8,
                "Target": float(target_ghz),
                "Save": int(save_modes),
            },
            "Linear": {
                "Type": "Default",
                "KSPType": "GMRES",
                "Tol": 1.0e-8,
                "MaxIts": 100,
            },
        },
    }, mesh_refinement, refinement_tol)


def _driven_block(f1_ghz, f2_ghz, step_ghz, fast_sweep=False, adaptive_tol=1.0e-3):
    """The ``Solver.Driven`` block: a direct point-by-point sweep (default) or
    Palace's ADAPTIVE fast frequency sweep.

    Adaptive: a single ``Samples`` Linear grid IS the dense output grid; Palace
    solves only a few support frequencies to meet ``AdaptiveTol`` and
    interpolates the rest (the whole grid still lands in port-S.csv). Field
    dumps are limited to the band edges. NOTE: the adaptive form REPLACES the
    flat MinFreq/MaxFreq/FreqStep keys — do not mix the two (Palace aborts).
    """
    if not fast_sweep:
        return {
            "MinFreq": float(f1_ghz),
            "MaxFreq": float(f2_ghz),
            "FreqStep": float(step_ghz),
            "SaveStep": 0,  # no per-frequency field dumps (fast)
        }
    return {
        "Samples": [
            {
                "Type": "Linear",
                "MinFreq": float(f1_ghz),
                "MaxFreq": float(f2_ghz),
                "FreqStep": float(step_ghz),
            }
        ],
        "Save": [float(f1_ghz), float(f2_ghz)],  # ParaView dumps at band edges only
        "AdaptiveTol": float(adaptive_tol),
    }


def set_excitation(ports, excite_port):
    """Drive exactly ``excite_port``; every other port becomes passive.

    Palace's contract is that ``Excitation`` must equal the port ``Index``, and
    a port with no ``Excitation`` key is a matched termination. A full N-port
    S-matrix therefore takes N solves — one per excitation — because a single
    run yields only the column belonging to the driven port. See
    ``emstudio.post.sparams.merge_excitations`` for the join.

    ⚠ **An unknown port is REFUSED, not ignored.** Clearing every excitation
    and driving none is a config Palace will happily solve, and what comes back
    is a matrix of numbers with nothing behind them. This only became reachable
    once the excitation list stopped being the literal ``[1, 2]``: an off-by-one
    in a loop over N ports asks for port N+1, and silence there would produce
    a plausible, wrong .sNp rather than a stack trace.

    Mutates and returns the list, so a config builder can apply it inline.
    """
    want = int(excite_port)
    known = [int(p.get("Index", 0)) for p in ports]
    if want not in known:
        raise ValueError(
            "cannot excite port {0}: this config has ports {1}. Driving no "
            "port at all would still solve, and the S-column it produced "
            "would mean nothing.".format(want, known))
    for p in ports:
        idx = int(p.get("Index", 0))
        if idx == want:
            p["Excitation"] = idx
        else:
            p.pop("Excitation", None)
    return ports


def build_driven_config(mesh_name, f1_ghz, f2_ghz, step_ghz, order=3,
                        excite_port=1,
                        eps_r=1.0, mu_r=1.0, loss_tan=0.0, output="postpro",
                        fast_sweep=False, adaptive_tol=1.0e-3,
                        mesh_refinement=0, refinement_tol=0.01,
                        n_ports=2, device="CPU"):
    """Return a Palace driven (S-parameter) config for an N-port waveguide.

    Port ``excite_port`` is the driven wave port; every other port is passive.
    All ports absorb the fundamental (Mode 1 = TE10) via their built-in Robin
    impedance BC — no separate absorbing BC. Frequencies are in GHz (Palace's
    Driven sweep unit).

    ``n_ports`` must be the count the MESH was written with: the port and wall
    attributes are derived from it (``gmsh_box.wg_port_attr`` /
    ``wg_wall_attr``), and a config that disagrees with its mesh tags the wrong
    faces. Two is the default because both bundled geometries — the box
    waveguide section and the coax — have exactly two ends.

    :param mesh_refinement: AMR iterations (0 = off; opt-in adaptive refinement).
    :param n_ports: number of ports in the mesh (2 for the box waveguide).
    """
    n = int(n_ports)
    if n < 1:
        raise ValueError("n_ports must be >= 1; got {0}".format(n_ports))
    return _apply_refinement({
        "Problem": {"Type": "Driven", "Verbose": 2, "Output": output},
        "Model": {"Mesh": mesh_name, "L0": 1.0e-3},
        "Domains": {
            "Materials": [
                {
                    "Attributes": [WG_VOLUME_ATTR],
                    "Permeability": float(mu_r),
                    "Permittivity": float(eps_r),
                    "LossTan": float(loss_tan),
                }
            ]
        },
        "Boundaries": {
            # ⚠ The wall attribute MOVES with the port count — see
            # gmsh_box.wg_wall_attr. A literal 4 here would be port 3's
            # attribute on a 3-port mesh, and Palace does not report a face
            # that is both a port and PEC as the error it is.
            "PEC": {"Attributes": [wg_wall_attr(n)]},
            # Exactly one port is driven per solve — see set_excitation().
            "WavePort": set_excitation(
                [{"Index": k, "Attributes": [wg_port_attr(k)], "Mode": 1}
                 for k in range(1, n + 1)], excite_port),
        },
        "Solver": {
            "Order": int(order),
            # ⚠ "GPU" needs a Palace BUILT with CUDA or HIP. A CPU-only
            # build does not fail on it — MFEM falls back and says so in
            # the log — so this is safe to set, but "it ran" is NOT proof
            # the GPU was used. Read the Palace banner.
            "Device": str(device),
            "Driven": _driven_block(f1_ghz, f2_ghz, step_ghz, fast_sweep, adaptive_tol),
            "Linear": {
                "Type": "Default",
                "KSPType": "GMRES",
                "Tol": 1.0e-8,
                "MaxIts": 200,
            },
        },
    }, mesh_refinement, refinement_tol)


def build_lumped_coax_config(mesh_name, f1_ghz, f2_ghz, step_ghz, a_mm, b_mm,
                             excite_port=1,
                             order=2, eps_r=1.0, mu_r=1.0, loss_tan=0.0,
                             r_ohm=None, output="postpro",
                             fast_sweep=False, adaptive_tol=1.0e-3,
                             mesh_refinement=0, refinement_tol=0.01, device="CPU"):
    """Return a Palace driven (S-parameter) config for a 2-port coaxial line.

    Radial lumped ports (``Direction "+R"``) at each annular end face; port 1
    (attr {port1}) is driven, port 2 (attr {port2}) is passive. The reference
    impedance defaults to the analytic coax Z0 so the uniform line is matched
    (S11 measures only discretization). Frequencies in GHz. Verified against the
    AWS Palace ``coaxial`` example on 2026-07-07.

    ⚠ **This one stays 2-port on purpose, unlike ``build_driven_config``.** A
    coaxial section has two ends and there is no third face to put a port on;
    an ``n_ports`` argument here could only ever be given a 2, or be given a 3
    and produce a config naming a mesh attribute ``gmsh_coax`` never wrote. The
    excitation still loops — either end can be driven — which is all a full
    2x2 needs.

    :param mesh_refinement: AMR iterations (0 = off; opt-in adaptive refinement).
    """
    if r_ohm is None:
        r_ohm = coax_z0(a_mm, b_mm, eps_r)
    return _apply_refinement({
        "Problem": {"Type": "Driven", "Verbose": 2, "Output": output},
        "Model": {"Mesh": mesh_name, "L0": 1.0e-3},
        "Domains": {
            "Materials": [
                {
                    "Attributes": [COAX_VOLUME_ATTR],
                    "Permeability": float(mu_r),
                    "Permittivity": float(eps_r),
                    "LossTan": float(loss_tan),
                }
            ]
        },
        "Boundaries": {
            "PEC": {"Attributes": [COAX_WALL_ATTR]},
            # Exactly one port is driven per solve — see set_excitation().
            "LumpedPort": set_excitation([
                {"Index": 1, "Attributes": [COAX_PORT1_ATTR], "R": float(r_ohm),
                 "Direction": "+R"},    # coaxial radial lumped port
                {"Index": 2, "Attributes": [COAX_PORT2_ATTR], "R": float(r_ohm),
                 "Direction": "+R"},
            ], excite_port),
        },
        "Solver": {
            "Order": int(order),
            # ⚠ "GPU" needs a Palace BUILT with CUDA or HIP. A CPU-only
            # build does not fail on it — MFEM falls back and says so in
            # the log — so this is safe to set, but "it ran" is NOT proof
            # the GPU was used. Read the Palace banner.
            "Device": str(device),
            "Driven": _driven_block(f1_ghz, f2_ghz, step_ghz, fast_sweep, adaptive_tol),
            "Linear": {
                "Type": "Default",
                "KSPType": "GMRES",
                "Tol": 1.0e-8,
                "MaxIts": 200,
            },
        },
    }, mesh_refinement, refinement_tol)


def write_config(config, path):
    """Write a Palace config dict to ``path`` as JSON. Returns ``path``."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
    return path
