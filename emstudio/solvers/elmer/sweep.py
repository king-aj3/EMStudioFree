# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parametric sweeps over an axisymmetric magnetics model.

EMStudio's differentiator vs export-only plugins is that the physics lives on
parametric geometry — editing a dimension and re-solving is cheap. This module
drives that for the WPT coil-pair case: sweep the axial gap between two coils
and collect the coupling coefficient k(gap), each point a full FEM solve.

Pure (FreeCAD-free): operates on the plain axi-model dict, so it is validated
headlessly against the Maxwell analytic. FreeCAD commands build the base model,
then call in here.
"""
from __future__ import annotations

import copy


class SweepError(ValueError):
    """The model cannot be swept as requested."""


def _coils(model):
    return [b for b in model["bodies"] if b.get("coil")]


def _with_gap(model, ref_name, mov_name, gap_mm):
    """A model copy with ``mov`` coil's centroid ``gap_mm`` from ``ref``.

    The reference coil stays put; the moving coil keeps its height and radii and
    is translated in z so the centroid separation equals ``gap_mm``. Direction
    preserves the original sign (moving coil stays on its own side of ref). Any
    fixed ``air`` override is dropped so the domain re-autosizes per gap.
    """
    m = copy.deepcopy(model)
    m.pop("air", None)
    ref = next(b for b in m["bodies"] if b["name"] == ref_name)
    mov = next(b for b in m["bodies"] if b["name"] == mov_name)
    ref_c = 0.5 * (ref["z0"] + ref["z1"])
    mov_c = 0.5 * (mov["z0"] + mov["z1"])
    sign = 1.0 if mov_c >= ref_c else -1.0
    dz = (ref_c + sign * abs(gap_mm)) - mov_c
    mov["z0"] += dz
    mov["z1"] += dz
    return m


def sweep_wpt_gap(model, gaps_mm, freq_hz=100e3, line_callback=None):
    """Solve k(gap) for a two-coil model over a list of axial gaps.

    Returns a list of dicts (in the given gap order):
    ``{gap_mm, k, L1_h, L2_h, M_h}``. The first coil (lowest centroid) is held
    fixed; the second is moved to each gap. Each point is an independent FEM
    solve with coupling extraction. (k is frequency-independent for
    non-conducting coils, so ``freq_hz`` only sets the solve point.)
    """
    from .runner import run_model

    coils = _coils(model)
    if len(coils) != 2:
        raise SweepError(
            "gap sweep needs exactly 2 coils, found {0}".format(len(coils)))
    ref, mov = sorted(coils, key=lambda b: 0.5 * (b["z0"] + b["z1"]))
    ref_name, mov_name = ref["name"], mov["name"]

    out = []
    for gap in gaps_mm:
        if line_callback is not None:
            line_callback("gap sweep: {0:.3g} mm".format(gap))
        variant = _with_gap(model, ref_name, mov_name, gap)
        result = run_model(variant, [freq_hz], line_callback=line_callback,
                           extract_coupling=True)
        lmat = result.inductance_matrix()
        ks = result.coupling_k()
        k = ks.get((ref_name, mov_name)) or ks.get((mov_name, ref_name))
        if k is None:
            k = next(iter(ks.values()), None)
        m_h = 0.5 * (lmat[(ref_name, mov_name)] + lmat[(mov_name, ref_name)])
        out.append({
            "gap_mm": float(gap),
            "k": k,
            "L1_h": lmat[(ref_name, ref_name)],
            "L2_h": lmat[(mov_name, mov_name)],
            "M_h": m_h,
        })
    return out
