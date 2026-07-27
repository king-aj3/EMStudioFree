# SPDX-License-Identifier: LGPL-2.1-or-later
"""AWS Palace FEM backend: resonant-cavity eigenmode analysis.

Full-wave finite-element eigenmodes of PEC-walled dielectric cavities —
the first slice of the Palace (HFSS-class) backend. Driven / wave-port
S-parameter analyses are a follow-on.
"""
from .runner import (  # noqa: F401
    run,
    run_cavity,
    run_cavity_brep,
    run_coax,
    run_waveguide,
    run_waveguide_brep,
)
