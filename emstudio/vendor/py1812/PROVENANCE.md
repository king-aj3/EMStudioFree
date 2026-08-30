# Provenance — vendored Py1812

- Upstream: https://github.com/eeveetza/Py1812 (Ivica Stevanovic, OFCOM) — the
  ITU-R reference implementation of Recommendation P.1812-8.
  ⚠ REVISION LABEL CORRECTED 2026-08-30: this file (and every EMStudio surface
  quoting it) said "-6", but the pinned commit a5205e6 postdates upstream's
  p1812-8 merge and its own README states P.1812-8 — which is the revision IN
  FORCE (09/2025) per itu.int, where -6 is Superseded. Note upstream's
  P1812.py docstring line ~50 still says "-6" at that commit; that is
  upstream's stale line and stays as vendored (pristine-copy rule).
- Vendored: 2026-07-09 from upstream commit
  a5205e6a65db27391a8ba79bd5a365e5391f9fdf (2026-05-18).
- License: the upstream LICENSE in this directory (permissive: as-is, no
  warranty, modification + redistribution permitted with change notices and
  acknowledgment). Acknowledgment: Py1812 by Ivica Stevanovic (OFCOM).
- Changes from upstream (per the license's change-notice requirement):
  - 2026-07-09: the module-level load of the ITU digital-maps file
    (`P1812.npz`) was made LAZY and its absence given a clear error. The maps
    are NOT redistributed with EMStudio (ITU data): pass `DN=`/`N0=` to
    `bt_loss` (the official validation path), or generate `P1812.npz` from
    the official ITU zips using `initiate_digital_maps.py` (vendored
    unmodified) and drop it in this directory.
  - 2026-07-10 (notice added retroactively): upstream ``__init__.py``
    was replaced at vendoring time by an EMStudio shim that re-exports
    the model module (``from . import P1812``).
  No numerical/algorithmic changes.
- Validation: `tests/validation/p1812.py` replays the official ITU-R
  P.1812-8 validation examples through this vendored copy (final Lb/E and the
  per-equation delta-Bullington intermediates).

## SPDX confirmation

Asked upstream 2026-08-23 — one issue covering all four vendored repos
(the LICENSE text is byte-identical):
https://github.com/eeveetza/Py1812/issues/13 — awaiting the author's
one-line characterisation; record the answer here when it lands and
re-export the free tree.
