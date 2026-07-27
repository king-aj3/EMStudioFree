# Provenance — P.452-18 validation examples

- Source: https://github.com/eeveetza/p452 (Ivica Stevanovic, OFCOM — the
  MATLAB twin of the vendored Py452 reference implementation), directory
  `matlab/validation_examples/`, mirrored 2026-07-10 from commit
  86f8026ce39635fa2b599e50d6d01fe5b0d6bbfe. Same permissive license family
  as the vendored engine (`emstudio/vendor/py452/LICENSE`).
- Upstream describes the set as the CG-3M / WP 3M validation examples for
  Recommendation ITU-R P.452-18 (non-exhaustive, with intermediate and final
  results included expressly for implementation comparison).
- Contents: 17 path-profile CSVs (`profiles/`) + 17 matching result CSVs
  (`results/`, 35 cases each = 595 cases total, 46 columns: the full input
  set incl. terminal coordinates, the geometry intermediates, and the
  reference losses Lb/Lbfsg/Lb0p/Lb0b/Ldsph/Ld50/Ldp/Lbs/Lba). Files are
  byte-for-byte upstream copies.
- Consumed by `tests/validation/p452.py`, which replays every case through
  the vendored engine (needs the ITU digital maps — install once via
  `emstudio.coverage.itu_maps.install_p452_maps()`).
