# Provenance — P.2001 validation examples

- Source: https://github.com/eeveetza/Py2001 (Ivica Stevanovic, OFCOM — the
  ITU-R reference implementation vendored in `emstudio/vendor/py2001`),
  directory `tests/validation_examples/`, mirrored 2026-07-10 from commit
  a4d61a056bad606d1147ff0c441511762ee9fb24. Same permissive license as the
  vendored engine (`emstudio/vendor/py2001/LICENSE`).
- The two official ITU-R validation example profiles (`b2iseac`, `prof4`)
  with their full reference result tables — 2215 cases each (4430 total):
  frequency × time-percentage × height/gain/polarization sweeps, 139 columns
  incl. terminal coordinates and the reference basic transmission loss Lb.
  These are the examples the upstream harness (`validateP2001.py`) replays
  at tolerance 1e-6 dB. (The upstream README labels the set "P.2001-4"; the
  official example set has not been re-issued for later revisions — the
  vendored -6 engine still reproduces it, which the gate demonstrates.)
- The `*_results.csv.gz` files are gzip-compressed byte-for-byte copies of
  the upstream CSVs (~4 MB each uncompressed); profiles are uncompressed
  upstream copies.
- Consumed by `tests/validation/p2001.py` (needs the ITU digital maps —
  install once via `emstudio.coverage.itu_maps.install_p2001_maps()`).
