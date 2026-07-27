# SPDX-License-Identifier: LGPL-2.1-or-later
"""EMStudio — a FreeCAD workbench for RF / electromagnetic modeling and simulation.

EMStudio brings a guided, CENOS-style workflow (geometry -> materials -> ports/BCs ->
mesh -> solve -> results) natively into FreeCAD, driving best-of-breed open-source EM
solvers (openEMS, NEC2, Elmer, Palace) as isolated subprocess backends.

This top-level package is import-safe without a running GUI (``freecadcmd`` / plain
CPython for unit tests): nothing here imports ``FreeCADGui`` at module load time.
"""

from .version import __version__

__all__ = ["__version__"]
