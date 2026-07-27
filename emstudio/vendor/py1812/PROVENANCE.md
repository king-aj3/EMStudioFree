# Provenance — vendored Py1812

- Upstream: https://github.com/eeveetza/Py1812 (Ivica Stevanovic, OFCOM) — the
  ITU-R reference implementation of Recommendation P.1812-6.
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
  P.1812-6 validation examples through this vendored copy (final Lb/E and the
  per-equation delta-Bullington intermediates).
