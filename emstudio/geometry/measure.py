# SPDX-License-Identifier: LGPL-2.1-or-later
"""Solver-independent size measurements on a solid.

Kept OUT of any solver package on purpose. This started life inside
``solvers/openems/geometry.py``, where it served the FDTD grid-resolution
guard — but "how small is the thing I have to resolve?" is a question every
mesher asks, and importing it from there drags
``solvers.openems`` -> ``runner`` -> ``writer`` -> ``objects.analysis`` ->
``import FreeCAD``. The Elmer mesh-size default needs the same number, and a
validation gate needs to check it without FreeCAD present.

FreeCAD-free by construction: the only interface used is ``.Volume`` and
``.Area`` on whatever object is passed, so a plain stub works in tests.
"""
from __future__ import annotations


def min_feature_mm(shape=None, mesh=None, bbox=None):
    """The smallest dimension a mesh has to resolve, in mm.

    An axis-aligned box announces its own smallest side, but a swept or
    tessellated body does not: a 6-turn helix has a 320 mm bounding box and a
    20 mm conductor, and only the second number tells you whether a grid can
    represent it. Volume/surface recovers it without any topology work —

        thin plate, thickness t:  V/A -> t/2
        long rod, radius r:       V/A -> r/2

    so ``2*V/A`` is the plate's thickness exactly and the rod's RADIUS (i.e.
    half its diameter). Taking the smaller reading is deliberate: this figure
    gates a refusal, and under-estimating errs toward warning the user.
    Measured on a real octagonal helix: 2V/A = 9.22 mm against a true 19.98 mm
    across-flats — the conservative half, as intended.

    Falls back to the smallest bounding-box side when there is no usable
    volume (sheets, open shells, meshes without a closed volume).
    """
    vol = area = 0.0
    if shape is not None:
        try:
            vol, area = float(shape.Volume), float(shape.Area)
        except Exception:                                    # noqa: BLE001
            vol = area = 0.0
    elif mesh is not None:
        try:
            vol, area = abs(float(mesh.Volume)), float(mesh.Area)
        except Exception:                                    # noqa: BLE001
            vol = area = 0.0
    if vol > 0.0 and area > 0.0:
        return 2.0 * vol / area
    if bbox is not None:
        lo, hi = bbox
        sides = [hi[i] - lo[i] for i in range(3) if hi[i] - lo[i] > 0.0]
        if sides:
            return min(sides)
    return 0.0
