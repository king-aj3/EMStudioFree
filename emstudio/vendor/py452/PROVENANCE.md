# Provenance — vendored Py452

- Upstream: https://github.com/eeveetza/Py452 (Ivica Stevanovic, Swiss
  Federal Office of Communications OFCOM) — the ITU-R reference
  implementation of Recommendation ITU-R P.452-18 (interference prediction
  between stations on the surface of the Earth, 0.1-50 GHz).
- Vendored: 2026-07-10 from upstream commit
  c047331990d35288300d0865802c98123aa21d3c (2025-08-19).
- License: the upstream LICENSE file in this directory (permissive: as-is,
  no warranty, modification + redistribution permitted with change notices
  and acknowledgment). Acknowledgment: Py452 by Ivica Stevanovic (OFCOM).
- Changes from upstream (per the license's change-notice requirement):
  - 2026-07-10: the module-level eager `np.load(files("Py452")/"P452.npz")`
    was replaced by a lazy loader (`_digital_maps()` + `_LazyMaps`) that
    resolves the npz through `emstudio.coverage.itu_maps` — the ITU digital
    maps (DN50.TXT, N050.TXT) are *integral digital products* of the
    Recommendation and may not be redistributed, so EMStudio never bundles
    them; the module now imports cleanly without them and raises a
    download-instruction error only when a computation actually needs them.
  - 2026-07-10: upstream ``__init__.py`` (docstring + ``__version__``)
    replaced by an EMStudio vendoring shim that re-exports the model
    module (``from . import P452``).
  No numerical/algorithmic changes.
- The maps: generate `P452.npz` with `initiate_digital_maps.py` (upstream,
  unmodified) from DN50.TXT/N050.TXT out of the official ITU-R P.452 zip, or
  let `emstudio.coverage.itu_maps.install_p452_maps()` do both steps.
- Validation: `tests/validation/p452.py` replays the official CG-3M P.452-18
  validation examples (mirrored from the upstream MATLAB twin repo
  github.com/eeveetza/p452) through this vendored copy.
