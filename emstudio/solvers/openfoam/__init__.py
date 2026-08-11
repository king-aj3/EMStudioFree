# SPDX-License-Identifier: LGPL-2.1-or-later
"""OpenFOAM (ESI) — EMStudio's CFD backend.

Until v0.96.0 EMStudio could FIND OpenFOAM and health-check it but could not
run anything with it: ``emstudio/setup/openfoam.py`` was discovery and guided
install only, and there was no ``emstudio/solvers/openfoam`` at all. The
README's "conjugate heat / enclosure airflow" was a promise about the
installer, not a capability. This package is the first solve path.

The first slice is the **differentially-heated square cavity** — buoyancy-
driven flow in a closed box, which is the reduced form of the question an RF
enclosure actually poses: how much heat leaves a hot wall by natural
convection. It meshes with ``blockMesh`` alone (no snappyHexMesh), so the
whole write -> run -> read chain is exercised in seconds rather than the tens
of minutes a real geometry costs.

Subprocess only, like every other backend here: a case is written to a working
directory, the binaries run through :mod:`emstudio.setup.openfoam`'s resolved
install, and the fields are read back. No OpenFOAM code is linked or bundled.
"""

from __future__ import annotations

from emstudio.solvers.openfoam.writer import (      # noqa: F401
    CavityCase, rayleigh, write_cavity,
)
from emstudio.solvers.openfoam.cylinder import (    # noqa: F401
    CylinderCase, conduction_nusselt, first_cell_height, radial_layer_centres,
    rayleigh_d, write_cylinder,
)
from emstudio.solvers.openfoam.parser import (      # noqa: F401
    CylinderNusselt, NusseltResult, read_internal_field,
    nusselt_cylinder_from_field, nusselt_from_field,
)
from emstudio.solvers.openfoam.runner import (      # noqa: F401
    run_cavity, run_chain, run_cylinder,
)

__all__ = ["CavityCase", "rayleigh", "write_cavity",
           "CylinderCase", "conduction_nusselt", "first_cell_height",
           "radial_layer_centres", "rayleigh_d", "write_cylinder",
           "NusseltResult", "CylinderNusselt", "read_internal_field",
           "nusselt_from_field", "nusselt_cylinder_from_field",
           "run_cavity", "run_chain", "run_cylinder"]
