# SPDX-License-Identifier: LGPL-2.1-or-later
"""AWS Palace FEM backend: eigenmode AND driven full-wave analysis.

Full-wave finite-element eigenmodes of PEC-walled dielectric cavities were the
first slice; driven wave-port and lumped-port S-parameter sweeps followed and
are re-exported below (``run_waveguide``, ``run_waveguide_brep``, ``run_coax``),
along with adaptive fast sweeps, adaptive mesh refinement and — v1.10.0 — the
far field, read back after every driven excitation.
"""
from .runner import (  # noqa: F401
    run,
    run_cavity,
    run_cavity_brep,
    run_coax,
    run_waveguide,
    run_waveguide_brep,
)
