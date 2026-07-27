# SPDX-License-Identifier: LGPL-2.1-or-later
"""Geographic coverage & propagation (ROADMAP §6).

The deployment-level view: take a designed antenna's pattern and predict its
real-world coverage over terrain. This package starts with:

* ``propagation`` — the analytic point-to-point path-loss models, each with a
  stated valid range: free-space, single knife-edge diffraction (ITU-R P.526),
  plane-earth two-ray, and the ITU field-strength relation for broadcast, plus a
  terrain-path-profile (single-edge Deygout) loss. Pure-python, Qt-free,
  textbook-validated. (Phase A.)
* ``geodesy`` — great-circle distance/bearing/interpolation + earth-bulge. (Phase B.)
* ``terrain`` — DEM import (SRTM ``.hgt`` + minimal GeoTIFF, no GDAL) and
  tx->point great-circle terrain path profiles. (Phase B.)
* ``pattern`` — antenna azimuth-cut gain from a NEC2/openEMS ``FarFieldResult``,
  modulating the map. (Phase B.)
* ``heatmap`` — the one-station area coverage grid (received power / field
  strength), built on ``propagation`` + ``terrain`` + ``pattern``, with an opt-in
  ground-wave model. (Phase B/C.)
* ``kml`` — Google-Earth ``GroundOverlay`` export of a coverage grid. (Phase B.)
* ``groundwave`` — the LF/MF surface-wave model (ITU-R P.368 / Norton: complex
  numerical distance + attenuation function, field strength, and Millington
  mixed-path), for the band below ~30 MHz. (Phase C.)
* ``lfmf`` — the ITU-R P.368-10 spherical-earth ground wave (the validated
  numpy/scipy port of the NTIA LFMF reference implementation: flat-earth
  Sommerfeld + Wait/Hufford residue series, 0.01-30 MHz to 10000 km) behind
  ``groundwave.spherical_field_strength_dbuv_m`` and the coverage dialogs'
  opt-in ``gw_engine="p368"``. (Phase D.)
* ``multistation`` — multi-station service/interference (D/U) contours. (Phase C.)
* ``empirical`` — Okumura-Hata / COST-231 clutter models. (Phase D.)
* ``p1546`` / ``p1812`` — wrappers over the vendored official ITU-R reference
  implementations (P.1546-6 point-to-area, P.1812-6 path-specific), each gated
  against the official ITU validation sets at 0.000000 dB. (Phase D.)
* ``p452`` / ``p2001`` — wrappers over the vendored official ITU-R reference
  implementations (P.452-18 interference prediction, P.2001-6 wide-range
  model), gated against the official validation examples (595 + 4430 cases).
  Their ITU digital maps are NEVER bundled — ``itu_maps`` downloads the
  official Recommendation zips (or takes a user-supplied copy) and builds
  the npz archives the engines load lazily. (Phase D.)

Transmitter locations/ground are user-supplied; no specific sites are referenced.
"""
