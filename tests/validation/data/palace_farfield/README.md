# Palace far-field fixture

`halfwave_dipole_grid-rE.csv` is the **output of a real Palace run on this
project's own machine**, produced 2026-08-26 with Palace **v0.17.0-67-g9b9d6524d**
(schema 1-0-0), 4 MPI ranks.

* **Geometry**: the half-wave dipole from Palace's own
  `examples/antenna/antenna_halfwave_dipole.json` and its `mesh/antenna.msh`
  (Copyright Amazon.com, Inc. or its affiliates; Apache-2.0). Driven at
  **74.9 MHz**, second-order absorbing boundary on attribute 4.
* **What we changed**: only the far-field sampling. The upstream example asks
  for `NSample: 100` (a spiral) plus one explicit angle. This run asked for an
  explicit **regular grid** — theta every 10 deg, phi every 15 deg — because
  `FarFieldResult` holds a pattern on a grid and a spiral is not one. See
  `emstudio/solvers/palace/writer.py:farfield_grid`.
* **Why a fixture at all**: it lets `palace_farfield.py` check the parser and
  the radiation physics **against textbook dipole theory** in milliseconds, on
  any machine, with no Palace installed. The live re-run is the SOLVER-tier
  half.

⚠ 456 angles were requested and **410 rows** came back. That is correct: Palace
deduplicates the poles, where every phi names the same direction
(456 - 2*23 = 410). A reader that demands `rows == Ntheta*Nphi` rejects valid
output.
