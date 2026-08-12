# SPDX-License-Identifier: LGPL-2.1-or-later
"""OpenFOAM (ESI) — EMStudio's CFD backend.

Until v0.96.0 EMStudio could FIND OpenFOAM and health-check it but could not
run anything with it: ``emstudio/setup/openfoam.py`` was discovery and guided
install only, and there was no ``emstudio/solvers/openfoam`` at all. The
README's "conjugate heat / enclosure airflow" was a promise about the
installer, not a capability. This package is the first solve path.

There are four case writers, each with its own gate, and they are a LADDER —
every rung anchored where its answer is independently known, so a disagreement
further up is interpretable rather than merely surprising:

===========  ==============  ==================================================
module       gate            what it anchors on
===========  ==============  ==================================================
``writer``   cavity          the conduction limit, Nu -> 1 (exact)
``cylinder`` cylinder        annulus conduction Nu = 2/ln(RR) (exact), then the
                             Churchill-Chu/Morgan envelope where CC is right
``bundle``   bundle          single-cable rungs INSIDE that envelope, which is
                             what validates snappy + the flux BC + the patch
                             reader before the bundle result is believed
``wind``     wind            zero lift by symmetry (exact), at Re 20-40 where
                             steady RANS is actually valid
===========  ==============  ==================================================

**``bundle`` is the one that reaches a user.** Churchill-Chu assumes ONE cable
in unbounded still air, and ``wire/thermal.py`` ships it; measured here it
over-predicts a trefoil's film coefficient by ~20 %, in the unsafe direction.
Mixed-diameter bundles get one Nusselt number PER SIZE — see ``bundle``.

⚠ The cavity is kept as a benchmark rather than generalised away. It meshes
with ``blockMesh`` alone, so it exercises write -> run -> read in seconds, and
smearing a benchmark fixture into a geometry pipeline would cost that.

Subprocess only, like every other backend here: a case is written to a working
directory, the binaries run through :mod:`emstudio.setup.openfoam`'s resolved
install, and the fields are read back. No OpenFOAM code is linked or bundled.
"""

from __future__ import annotations

from emstudio.solvers.openfoam.writer import (      # noqa: F401
    CavityCase, rayleigh, write_cavity,
)
from emstudio.solvers.openfoam.bundle import (      # noqa: F401
    BundleCase, SizeGroup, TREFOIL, cable_stl, group_cables, write_bundle,
)
from emstudio.solvers.openfoam.wind import (        # noqa: F401
    WindCase, SHEDDING_RE, write_wind,
)
from emstudio.solvers.openfoam.cylinder import (    # noqa: F401
    CylinderCase, conduction_nusselt, first_cell_height, radial_layer_centres,
    rayleigh_d, write_cylinder,
)
from emstudio.solvers.openfoam.parser import (      # noqa: F401
    BundleNusselt, CylinderNusselt, MixedBundleNusselt,
    NusseltResult, read_internal_field,
    nusselt_cylinder_from_field, nusselt_from_field,
    nusselt_from_patch, read_patch_values,
    WindForces, forces_from_log,
)
from emstudio.solvers.openfoam.runner import (      # noqa: F401
    run_bundle, run_cavity, run_chain, run_cylinder, run_wind,
)

__all__ = ["CavityCase", "rayleigh", "write_cavity",
           "CylinderCase", "conduction_nusselt", "first_cell_height",
           "radial_layer_centres", "rayleigh_d", "write_cylinder",
           "NusseltResult", "CylinderNusselt", "read_internal_field",
           "nusselt_from_field", "nusselt_cylinder_from_field",
           "BundleCase", "SizeGroup", "TREFOIL", "cable_stl", "group_cables",
           "write_bundle",
           "BundleNusselt", "MixedBundleNusselt",
           "nusselt_from_patch", "read_patch_values",
           "WindCase", "SHEDDING_RE", "write_wind", "WindForces",
           "forces_from_log",
           "run_bundle", "run_cavity", "run_chain", "run_cylinder",
           "run_wind"]
