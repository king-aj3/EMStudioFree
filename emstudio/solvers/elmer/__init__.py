# SPDX-License-Identifier: LGPL-2.1-or-later
"""Elmer FEM backend: 2-D axisymmetric harmonic magnetodynamics.

Induction heating, eddy currents / Joule heating, and coil-coupling (WPT)
analyses for coaxial geometries — the CENOS IH/WCH problem class.
"""
from .runner import run, run_model  # noqa: F401
