# Provenance — LFMF (ITU-R P.368-10) validation data

- Upstream: https://github.com/NTIA/LFMF — the NTIA/ITS C++ reference
  implementation of the LF/MF smooth-earth ground-wave model. Recommendation
  ITU-R P.368-10 (08/2022) declares its software implementation an *integral
  part of the Recommendation*, and that software is this NTIA code (the files
  in the ITU "integral part" zip are byte-identical to the NTIA release —
  verified during the 2026-07-09 §6-D de-risk).
- License: US-Government work, public domain in the United States
  (15 USC 105), with an explicit worldwide royalty-free grant to publish,
  prepare derivative works and distribute, asking only for acknowledgment and
  change notices. Key upstream `LICENSE.md` language: *"works of NTIA
  employees are not subject to copyright protection within the United
  States"*; *"you are hereby granted the non-exclusive irrevocable and
  unconditional right to print, publish, prepare derivative works and
  distribute the NTIA software, in any medium, … on a royalty-free basis
  throughout the World"*; *"Modified works should carry a notice stating
  that you changed the software and should note the date and nature of any
  such change"*; *"Please provide appropriate acknowledgments of NTIA's
  creation of the software"*. Acknowledgment: LFMF by NTIA/ITS.
- `LFMF_Examples.csv`: byte-for-byte copy of
  `extern/test-data/LFMF_Examples.csv` (NTIA/LFMF-test-data commit d3cc4d6,
  the test-data submodule pinned by the LFMF release) — 5 valid worked
  examples (outputs at 0.1 precision) + 90 input-validation rows covering
  every error return code. LFMF-test-data is likewise a work of NTIA/ITS
  (published under the NTIA/ITS PropLib program with a Zenodo DOI; US-gov
  work, public domain per 15 USC 105; its README's Data Disclaimer notes the
  rows are unit-test vectors, including intentionally invalid rows — exactly
  how the gate uses them).
- `oracle_grid.csv`: generated 2026-07-10 on this project's dev machine by
  driving the upstream library (v1.1, commit 57886e9, built from unmodified
  source with g++ 13 / cmake, Linux x86_64) through its exported C `LFMF()`
  entry point via ctypes at full double precision. 2497 rows spanning
  frequency 0.01-30 MHz x distance 0.001-10000 km x sea/average/very-dry
  ground x terminal heights 0-50 m x both polarizations x N_s 250-400,
  including rows bracketing the flat-earth/residue-series method switch
  (d = 80/cbrt(f_MHz)) and a 128-row epsilon == 1 boundary block (eta - 1
  purely imaginary — the complex-sqrt branch-cut corner an adversarial
  review found the original grid blind to). 1219 flat-earth rows, 1278
  residue-series rows.
  Column layout matches `LFMF_Examples.csv`; outputs printed with %.17g.
  ⚠ **Before regenerating this file** (added 2026-10-17, v1.14.0): the
  block's 32 pol-0 flat-earth rows sit exactly ON F(p)'s sqrt branch cut,
  and their values are those of THIS build (g++ -O2, x86-64, no fused
  multiply-add), which lands on the principal (+j) side. Which side a build
  lands on depends on how it rounds two equal products and a complex sqrt.
  A C++ mirror of the port's qi/p/sqrt lines (a mirror, NOT the upstream
  file) lands on the other side under g++ -march=native (FMA) and under
  Apple clang (libc++'s sqrt is not symmetric there); the upstream source
  itself has only been built here. CPython does the same thing: every
  Python on the macOS arm64 build host fuses its complex multiply, which put
  21 of these 32 rows up to 1.69 dB off until the port's `_cmul_unfused`
  (the gate's section 1b guards it). Regenerate on plain x86-64 g++, or
  expect those rows to move by design.
- Consumed by `tests/validation/lfmf.py`, which replays both files through
  the Python port `emstudio/coverage/lfmf.py`.
