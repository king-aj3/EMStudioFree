# SPDX-License-Identifier: LGPL-2.1-or-later
"""ITU-R P.1546-6 point-to-area field-strength prediction (ROADMAP §6-D).

Thin EMStudio face over the vendored **WP3K reference implementation**
(``emstudio/vendor/py1546`` — Py1546 by Ivica Stevanovic, OFCOM; permissive
license, see PROVENANCE.md there). This is the engine slice (the house
engine-then-dialog pattern); the coverage-dialog wiring is a follow-up.

Validity (per the Recommendation): 30 MHz - 4000 MHz, path 1 - 1000 km,
effective transmit height <= 3000 m, time percentage 1 - 50 %. Empirical
curve-interpolation model for BROADCAST-style point-to-area prediction over
land/sea/mixed paths — complementary to the deterministic terrain-diffraction
methods (Deygout/Causebrook/EP/Bullington) and the Hata/COST-231 clutter
models already shipped. Out of validity the vendored engine raises — inputs
are NOT extrapolated.

Gate: ``tests/validation/p1546.py`` replays the official ITU-R WP3K P.1546-6
validation examples (24 SG3 profiles) through the vendored engine and matches
the official reference outputs.
"""
from __future__ import annotations


def field_strength_dbuv_m(freq_mhz, time_pct, heff_m, h2_m, d_km,
                          area="Rural", r2_m=10.0, path="Land",
                          pathinfo=0, erp_kw=1.0, **kwargs):
    """Field strength E (dBµV/m) and basic transmission loss L (dB).

    Wraps the reference ``P1546.bt_loss`` with scalar-friendly arguments:
    ``d_km``/``path`` may be scalars (single-zone path) or aligned lists for
    mixed land/sea paths ('Land', 'Sea', 'Warm', 'Cold'). ``area`` is the
    receiver surrounding ('Rural', 'Suburban', 'Urban', 'Dense Urban', 'Sea'),
    ``r2_m`` its representative clutter height. Optional keyword arguments
    ``q``, ``wa``, ``ha``, ``hb``, ``R1``, ``tca``, ``htter``, ``hrter``,
    ``eff1``, ``eff2`` map onto the Recommendation's corrections (the vendored
    engine takes them as ORDERED positional varargs — this wrapper fills the
    chain with NaN placeholders up to the last one you set, the upstream
    convention for "not specified"). Returns ``(E_dbuv_m, L_db)``; E is scaled
    to ``erp_kw`` (the reference curves are for 1 kW e.r.p.).
    """
    import numpy as np

    from emstudio.vendor.py1546 import P1546

    d_v = np.atleast_1d(np.asarray(d_km, dtype=float))
    path_c = [path] if isinstance(path, str) else list(path)
    # the upstream engine only WARNS out of validity and then extrapolates —
    # EMStudio's policy is no silent extrapolation, so enforce here
    d_tot = float(np.sum(d_v))
    if not 30.0 <= float(freq_mhz) <= 4000.0:
        raise ValueError("P.1546 validity is 30-4000 MHz (got {0:g} MHz); "
                         "below 30 MHz use the ground-wave/ionospheric "
                         "models".format(freq_mhz))
    if not 1.0 <= float(time_pct) <= 50.0:
        raise ValueError("P.1546 time percentage must be 1-50% (got "
                         "{0:g}%)".format(time_pct))
    if not 1.0 <= d_tot <= 1000.0:
        raise ValueError("P.1546 path length must be 1-1000 km (got "
                         "{0:g} km)".format(d_tot))
    if float(heff_m) > 3000.0:
        raise ValueError("P.1546 effective height must be <= 3000 m")
    order = ("q", "wa", "PTx", "ha", "hb", "R1", "tca", "htter", "hrter",
             "eff1", "eff2")
    values = {"q": 50.0, "wa": float(kwargs.pop("wa", 500.0)),
              "PTx": float(erp_kw)}
    values.update({k: float(v) for k, v in kwargs.items()})
    unknown = set(values) - set(order)
    if unknown:
        raise TypeError("unknown P.1546 arguments: {0}".format(sorted(unknown)))
    last = max(order.index(k) for k in values)
    chain = [values.get(k, float("nan")) for k in order[:last + 1]]
    return P1546.bt_loss(float(freq_mhz), float(time_pct), float(heff_m),
                         float(h2_m), float(r2_m), str(area), d_v, path_c,
                         int(pathinfo), *chain)
