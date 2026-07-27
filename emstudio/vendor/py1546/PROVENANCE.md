# Provenance — vendored Py1546

- Upstream: https://github.com/eeveetza/Py1546 (Ivica Stevanovic, Swiss
  Federal Office of Communications OFCOM) — the ITU-R WP3K-approved reference
  implementation of Recommendation ITU-R P.1546-6.
- Vendored: 2026-07-09 from upstream commit
  e235629009ab1a12a33fc4a8fb5612f2883ecb5b (2025-08-19).
- License: the upstream LICENSE file in this directory (permissive: as-is, no
  warranty, modification + redistribution permitted with change notices and
  acknowledgment). Acknowledgment: Py1546 by Ivica Stevanovic (OFCOM).
- Changes from upstream (per the license's change-notice requirement):
  - 2026-07-09: the module-level `import matplotlib.pyplot` was made lazy
    (moved into the two optional debug-plot helpers `plotTca`/`plotTeff1`) so
    the engine imports headlessly without matplotlib's Qt backends.
  - 2026-07-10 (notice added retroactively): upstream ``__init__.py``
    was replaced at vendoring time by an EMStudio shim that re-exports
    the model module (``from . import P1546``).
  - 2026-07-26: the two ``np.mat(...)`` calls in ``P1546.py`` (lines ~259 and
    ~1247) were changed to ``np.asmatrix(...)``. ``np.mat`` was an alias of
    ``np.asmatrix`` and was removed in NumPy 2.0, which broke import on any
    NumPy >= 2 system; ``asmatrix`` is NumPy's documented drop-in. Verified by
    replaying the official validation set (``tests/validation/p1546.py``,
    0.000000 dB worst error) under BOTH NumPy 1.26.4 and 2.5.1.
  No numerical/algorithmic changes.
- Validation: `tests/validation/p1546.py` replays the official ITU-R WP3K
  P.1546-6 validation examples (v6.2 set; the profile CSVs + reference results
  mirrored from the same upstream repo, file-verified against the official ITU
  zip during the 2026-07-09 de-risk) through this vendored copy.
