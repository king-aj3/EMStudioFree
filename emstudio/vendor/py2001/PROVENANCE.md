# Provenance — vendored Py2001

- Upstream: https://github.com/eeveetza/Py2001 (Ivica Stevanovic, Swiss
  Federal Office of Communications OFCOM; contributions by Adrien Demarez) —
  the ITU-R reference implementation of Recommendation ITU-R P.2001-6 (the
  general-purpose wide-range terrestrial propagation model, 30 MHz-50 GHz,
  0-100 % of an average year).
- Vendored: 2026-07-10 from upstream commit
  a4d61a056bad606d1147ff0c441511762ee9fb24 (2025-11-21).
- License: the upstream LICENSE file in this directory (permissive: as-is,
  no warranty, modification + redistribution permitted with change notices
  and acknowledgment). Acknowledgment: Py2001 by Ivica Stevanovic (OFCOM).
- Changes from upstream (per the license's change-notice requirement):
  - 2026-07-10: the module-level eager `np.load(files("Py2001")/"P2001.npz")`
    was replaced by a lazy loader (`_digital_maps()` + `_LazyMaps`) that
    resolves the npz through `emstudio.coverage.itu_maps` — the 14 ITU
    digital map files are *integral digital products* of the Recommendation
    and may not be redistributed, so EMStudio never bundles them; the module
    now imports cleanly without them and raises a download-instruction error
    only when a computation actually needs them.
  - 2026-07-10: upstream ``__init__.py`` (docstring + ``__version__``)
    replaced by an EMStudio vendoring shim that re-exports the model
    module (``from . import P2001``).
  No numerical/algorithmic changes.
- The maps: generate `P2001.npz` with `initiate_digital_maps.py` (upstream,
  unmodified) from the 14 map .txt files out of the official ITU-R P.2001
  zip, or let `emstudio.coverage.itu_maps.install_p2001_maps()` do both
  steps.
- Validation: `tests/validation/p2001.py` replays the official ITU-R P.2001
  validation examples (profile + per-case reference results mirrored in the
  upstream repo's `tests/validation_examples/`) through this vendored copy.
