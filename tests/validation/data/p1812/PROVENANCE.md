# Provenance — P.1812-8 official validation data

`profiles/*.csv` (19 SG3 test profiles) and `reference_logs/*_log.csv`
(63 per-dataset logs with per-equation intermediate values) are the official
ITU-R SG3 validation examples for Recommendation P.1812-8 (the in-force
09/2025 revision; this file said "-6, Ver 6.1, 64 logs" until 2026-08-30 —
the count on disk and at the pinned upstream commit is 63 `_log.csv` files,
and ITU's published validation folder holds 64 FILES because it adds one
`combined_results.csv` beside them; the revision label followed the vendored
engine's correction, see emstudio/vendor/py1812/PROVENANCE.md. Set label:
published on the ITU-R SG3 "Software, Data and Validation" page), mirrored via
https://github.com/eeveetza/Py1812 tests/. Reference values are the
WP3K-approved implementation's outputs for these inputs.
