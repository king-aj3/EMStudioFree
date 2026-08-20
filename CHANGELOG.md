# Changelog

All notable changes to EMStudio are recorded here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — worked 2026-08-20, in no tag yet

> ⚠ **Rename this heading to the version that ships it.** A section sat here
> titled "Unreleased" through the whole of 1.0.0 once already — see the note on
> that section below.

### Added
* **A gate that ENFORCES "every solve asks first", instead of re-auditing it by
  eye.** `tests/validation/solve_confirm_coverage.py` (FAST tier) AST-walks
  every `run_generic_gui` call site and fails unless a `confirm_solve_work` /
  `confirm_solve` guard **precedes** it in the same function **and its answer is
  acted on** — the guard call must sit in the test of an `if` whose body
  returns, so asking the question and discarding the bool cannot pass. Callers
  that launch no solver are allowlisted by `(file, class, function)` with a
  written reason, never by line number; and an allowlist entry whose function
  has stopped calling the launcher is itself a failure, so an exemption cannot
  outlive the code it exempted. **5/5 mutations caught**, including a guard
  moved to AFTER the launch and a brand-new unguarded caller.
  ⛳ It exists because eye-auditing this failed three times running: 2026-08-19
  swept the solver-object paths and missed the three OpenFOAM dialogs, which
  launch directly; 2026-08-20 swept those and found four more; the audit OF
  that sweep still missed a fifth (below). Every sweep was careful and every
  one was incomplete, because reading has no way to fail loudly when a NEW
  caller appears.

* **Three more tutorials, and the anchors were re-measured rather than copied.**
  **#7 induction heating** against TEAM Problem 7 — the only anchor in the
  series compared to a *bench measurement* rather than a formula: RMS error
  **2.83 %** of the 7.811 mT measured peak, window ≤ 10 %. **#8 wireless power**
  — L, M and k against Grover's GMD and Maxwell's elliptic-integral formulas
  independently (k = **0.26243** vs 0.26195 at a 20 mm gap), plus the k-vs-gap
  sweep. **#9 the 3-D solenoid** — the general solids path, centre Bz **−1.26 %**
  against the exact closed form on the template's fast mesh.
  ⚠ Each tutorial states the trap that would otherwise mislead: TEAM 7's metric
  is an RMS normalised by the measured PEAK, never point-wise, because the
  A1-B1 line crosses zero at x ≈ 0.09 m; #9's "< 1 %" belongs to the ENGINE
  tier and the template tier is gated at 4 %; and a closed coil's field SIGN is
  mesh-arbitrary, so the gate compares magnitudes on purpose.
* **Tutorial #12 — a resonant cavity, the fairest test a full-wave solver
  faces.** A closed PEC box has an exact analytic answer with no fitted
  constant and no measurement uncertainty: fundamental TE101 **4.50386 GHz**
  vs 4.50382 GHz analytic (**+0.001 %**), and all ten modes within **0.020 %**
  of their nearest closed form, against a 1 % window. Measured live on this
  box. The tutorial spends as much space on the mode ORDERING as on the
  number — a cavity mis-scaled by 10x is still self-consistent and will report
  beautifully converged nonsense.
* **N-port is user-reachable — the document can now say which face is port 3.**
  The engine has been N-port end to end since v1.2.0 (mesh attributes, config,
  excitation loop, merge, `.sNp`), but the driven Palace path inferred **two**
  ports from the longest bounding-box axis, so every GUI-driven solve was a
  2-port. It turned out nothing was missing but the reading: an
  `EMStudio::LumpedPort` has always carried `References` and a 1-based
  `PortNumber`. `declared_port_boxes()` now orders them by `PortNumber`,
  resolves each face to its bounding box, inflates it into a slab and hands
  back the 6-tuples `normalise_port_faces` already accepted. The runner needed
  **no change** — its own comment had predicted exactly this.
  ⚠ Deliberately conservative: fewer than two usable port FACES, an `Edge`
  reference, or an incomplete declaration all fall back to inferring, so no
  document that worked before behaves differently. Declared ports force the
  BREP path even for a plain box, because the fast box mesher takes no `ports`
  argument and would drop the declaration silently.
  **Gate `declared_ports` (FAST), 11 checks, 5/5 mutations** on an asymmetric
  3-port fixture.
* **A LIVE 3-port solve — the claim is now earned, not projected.**
  `n_port_live_palace` (SOLVER) builds a real **WR-90 T-junction**, declares its
  three mouths as ports and has Palace solve one excitation each. Measured:
  passivity **0.9996** on the worst column, the full 3×3 totalling **2.9985** of
  an ideal 3.0 (air-filled, PEC walls), and an **`.s3p` with 6 data lines** —
  3 matrix ROWS × 2 frequencies, which proves the row-per-line Touchstone fix
  against a genuine file rather than a fixture.
  ⚠ It does NOT claim a validated T-junction S-matrix — no published reference
  exists for these dimensions, and inventing a window would be the
  cherry-picked-headline defect this project keeps catching.
* **One-click N-port: Analysis ▸ Wave Ports from Selection.** Creates one wave
  port per selected FACE, numbered in **selection order** — port 1 is the first
  face you clicked, because only the user knows which physical connector that
  should be. A single face is refused with a pointer to Lumped Port, and
  non-face selections are ignored rather than meshed as a mouth.
* **Seven more tutorials, every anchor measured on the box that wrote them.**
  **#13 litz** — why stranding changes anything: a 6-strand ring shares current
  at an imbalance of **1.0000**, while a 7-strand bundle with a CENTRE strand
  reaches **9.6272**, one strand carrying ~10x another, which is the whole
  argument for transposition. **#15 small antennas** — a 100 m VLF mast at
  30 kHz is h/λ = **0.0100** with R_r = **0.03953 Ω** and Q = **4.04e3**, so
  1 Ω of ground loss throws away 96 % of the power. **#16 link budget** — FSPL
  **81.99 dB** at 1 km / 300 MHz, and the **+6.02 → +12.04 dB** transition that
  explains why the last few kilometres cost what they do. **#17 coverage** —
  the strongest anchor in the series: ITU's own official reference datasets,
  **52 for P.1546 and 63 for P.1812, worst deviation 0.000000 dB** against a
  0.01 dB window. **#20 co-site** — the third-order products that land in band
  and the 3-dB-per-1-dB slope that makes isolation worth more than a better
  receiver. **#22 pattern-per-frequency** — N patterns from ONE solver run.
  **#23 solver setup** — ⚠ deliberately the only entry with NO number: it says
  so out loud rather than inventing an anchor, and names what IS gated instead.
* **The four Pro capabilities get public stubs, and the paywall is now
  machine-checked.** Per AJ's ruling, #24 Matching, #25 Array Designer, #26
  RFDF and #27 the Assistant each get a public stub giving the WHAT and the
  MEASURED NUMBER, with the steps Pro-side — VSWR **1.010** on the shipped
  71.9 Ω dipole; cardioid **29.6 dB F/B against 3.4 dB** on the same wires;
  a Dolph floor of **−26.02 dB held to 0.04 dB**; a manifold decoding an
  independent receive run at **0.00° bearing error**. Every figure was already
  public in `PRO.md` and on the product page, so the stubs leak nothing.
  ⛳ **The ruling is enforced rather than trusted:** `tutorials_doc` now applies
  a separate contract to any 🔒 section — it must carry *What it does*, *What it
  measured*, the free alternative (stating the tier plainly, never coyly) and
  its gate, and it must **NOT** contain a *Do* or *You should see* section.
  A leaked walkthrough now fails the battery. **3/3 mutations.**
  ⛳ #27 is the split AJ called for: the sentence that matters — **the Assistant
  does not validate anything, the gates do** — is public, because it is what
  makes every other number in the file mean something.
* ⭐ **THE TUTORIAL STANDING ORDER IS MET — all 27 capabilities covered.**
  Every solver and every capability EMStudio ships now has at least one
  tutorial ending in a checkable number and naming the gate that pins it, and
  the four Pro capabilities carry public stubs. *"There is nothing showing how
  to use EMStudio"* is factually unavailable.
  Final additions: **#10 thermal CFD on your own solid** — anchored on an
  **exact** bound rather than a correlation (Nu_D **2.5511** inside the
  conduction sandwich **[2.3374, 2.6667]**, measured live), which also fails
  informatively in both directions: an unconverged solve reads HIGH, a
  lost-flux coupling reads LOW. Its convection rung is measured too —
  **Nu 18.3508** at Ra **1.317e6** vs Churchill **17.3838** (**+5.6 %**), with
  a buoyancy signature of **25.92 K** surface spread against the conduction
  rung's **0.147 K**, so *"did the flow actually start?"* is a question the
  gate answers rather than assumes. And **#11 conjugate heat transfer** — gap Nu
  **~6.5** (bracket **6.47–6.56**), ⚠ deliberately NOT the gate mesh's 6.85,
  which reads roughly 5 % high; the tutorial explains why the answer is a
  bracket (the scheme is formally first-order yet the three grids show
  p = 1.90, so the standard safety factor is not trusted) and records that an
  earlier "asymptotic-range check ≈ 1.0" was **withdrawn** because it was
  algebraically identical to f₃/f₂ and could not fail.
* **A gate for the tutorials themselves.** `tests/validation/tutorials_doc.py`
  (FAST) asserts every numbered tutorial keeps the four-part shape, that each
  "Prove it" names a gate file **that exists**, that no number is used twice
  between the written and the planned lists, and that **no tutorial COUNT
  appears in the prose**. **5/5 mutations caught.** The near-term table had
  carried two `#7` rows and numbered induction heating as 12 while the master
  list called it 7.

### Fixed
* **A reply went out with a stale count, and the counts are now gone.** A
  drafted r/rfelectronics reply said *"Five of them"* on the day the sixth
  tutorial shipped — in a post whose whole argument was that this project's
  claims are checkable. Counts removed from `HELP.md`, the public README and
  `TUTORIALS.md`; the new gate above stops them coming back.
* **mmWave was overstated in two reader-facing documents.** `CAPABILITIES.md`
  and `ROADMAP.md` both said the full-wave engines "work from HF through
  millimetre-wave" as one span, citing only Palace's validation. The honest
  form is per engine and per structure class, and it is now written that way:
  **Palace sub-0.01 % at 39 and 57 GHz on CLOSED structures**; **openEMS gated
  to 3.68 GHz** (microstrip notch) and **2.45 GHz radiating** (patch); **NEC2
  at 296 MHz**. ⚠ **Nothing radiating is gated above 2.45 GHz** — tutorial 6
  said "above 6 GHz", which was true but generous, and is corrected to the real
  ceiling. The ROADMAP already applied exactly this standard to VLF
  ("unproven until gated") two paragraphs earlier.
* **`band_picker` printed a doubled unit at mmWave** — *"10.71 mm m
  wavelength"*, because `_fmt_wavelength` already carries its unit and the
  format string appended another. User-visible, and present for as long as the
  mmWave branch has existed, because the gate checked the ROUTING and never the
  prose. Now swept across seven decades in `small_antenna.py`, mutation-proven.
* **The v1.2.0 tutorial-6 runtime is a band, not a stopwatch reading.** "About
  45 seconds" was measured on one machine and is roughly half what this one
  takes. Wall-clock is machine-dependent and was deleted rather than re-stated
  once already this month; the same rule now applies here.
* **A fifth solve path started FastHenry without asking.** The Cable Designer's
  **current sharing** (`_current_sharing`) called `run_generic_gui` with no
  pre-solve estimate anywhere in the method, while its four siblings in the
  same dialog were all gated. It is a real external solve —
  `analyze_construction` -> `analyze_paths` -> `run_parallel_sweep`, one
  FastHenry process per frequency fanned across every core. Its measure is
  `conductors x nhinc` with **no** factor of two, because this path passes
  `fmin == fmax` with `ndec=1`, so `sweep_frequencies` yields a single
  frequency — ONE run, where the bundle-coupling siblings genuinely make two.
  Keyed under `fasthenry` so all three paths feed one measured history rather
  than each starting cold.
* **A far-field check that could not fail.** `pattern_sweep`'s *"results come
  back sorted by frequency"* asserted `== sorted(...)` against a fixture that
  was **already ascending**, so it held whether or not the parser sorted:
  deleting `out.sort(...)` from `parse_radiation_patterns_all` left the entire
  gate green. The identical lesson had already been learned for the CURRENT
  parser on 2026-08-07 — `gate_currents_blocks` builds its fixture descending
  for exactly this reason — and was never carried across to the far-field one.
  The sort is now proven on a DESCENDING file, plus a second check that each
  block keeps its OWN gains through the sort: sorting the frequencies while
  leaving the gain arrays where they were would satisfy a frequency-only check
  and silently pair every pattern with the wrong frequency. **3/3 mutations
  caught** — and that third mutation is caught ONLY by the gains check.
* **`CLAUDE.md` documented an `export_free.py` invocation that does not run.**
  `--check DIR` exits 2 with *unrecognized arguments* (`--check` is
  `store_true`); the working form is `--out DIR --check`. The next session
  would have copied the broken line straight out of the file — and the correct
  form immediately earned itself by catching that the new gate above was
  untracked and would have been silently missing from the free export.
* **Gate counts re-derived, not trusted.** 88 gate files -> **89**, FAST 38 ->
  **39** (`CLAUDE.md`, `README.md`), and the public `CAPABILITIES.md` claim for
  `pattern_sweep.py` corrected from *54 checks* to **79** — it had gone stale
  across two rewrites while nothing measured it.

## [1.2.0] — 2026-08-20 — a real `.sNp`: every port solved, and every solve priced first

### Added
* **A pre-solve time estimate, measured or absent — never guessed.** A solve
  asks first, showing what it is expected to cost and letting you back out; the dialog also states that progress is a live percentage with an
  ETA and that Cancel works, because "how long" and "can I stop it" are the
  same question asked twice. Muteable per-user with *Don't ask again*.
  `solvers/progress.py` already answered "is it hung?" once a run was under
  way, but its live ETA needs 3 s and 5 % done before it will speak — by which
  time the decision is made. The tempting fix is a cost model (NEC2 is O(N³)
  in segments, openEMS is timesteps × cells); that gives a shape, never a
  duration, because the constant is the machine. So estimates come from **this
  machine's own measured history**, bucketed logarithmically per backend by a
  scalar work measure, taken as the **median** so one run on a machine that
  slept cannot move it, and borrowed from a neighbouring size only one bucket
  away, only scaled by the work ratio, and only labelled EXTRAPOLATED. With no
  history it says so. Wired into all four solver paths — NEC2 and openEMS via
  `run_solver_gui`, Elmer and Palace at their own call sites (not inside
  `run_generic_gui`, which also serves non-solve work like fetching a model
  list). ⚠ It can never block a solve: every error path returns "proceed",
  because a broken estimate stopping real work would be the worse bug. New
  FAST gate `solve_estimate`, 8 mutations caught.
* **The full 2-port solve — two excitations (Palace AND openEMS).** Both
  backends solve ONE excitation per run by construction, so the complete 2x2
  S-matrix is two solves. Both solver objects gain **`FullSMatrix`**, off by
  default. (It was called `Full2Port` while two ports were the only order the
  solvers could do; see the N-port entry below for the rename.)
  * **Palace** takes it as a config parameter: `set_excitation()` drives
    exactly one port and clears any other (its contract is `Excitation ==
    Index`, and a port without the key is a matched termination). Every
    excitation runs against the **same mesh** — the property that makes the
    merged matrix mean anything — and writes to its own `postpro_eN`.
  * **openEMS** takes its excitation from the port object's `Excited` flag, so
    `_collect_ports()` gained an override that drives the requested port
    regardless of the document. The second FDTD run lives in `exc2/` and only
    its two NEW terms are taken (S22 from its driven-port file, S12 from
    `sparam_1_2.csv`); run 1 still writes exactly what it always did, in
    exactly the same place. ⚠ Fixed on the way past: the runner hardcoded a
    `.s1p` filename, which would have written a genuine 2-port matrix into a
    file named `.s1p`.
  `merge_excitations()` joins the columns and **refuses** rather than guessing:
  a frequency-grid mismatch is refused instead of resampled (two sweeps on
  different grids are two different experiments, and interpolating one onto
  the other manufactures a `.s2p` that looks measured), and two runs claiming
  the same term are refused because that means the excitations were not
  distinct. ⚠ **Costs a second solve**, and the pre-solve estimate counts it.
  New FAST gate `two_port_excitation` (5 mutations) plus live SOLVER gates
  `two_port_palace` (|S11| −28.0 dB, |S21| within 0.334 dB of 0, S12−S21
  4.2e−08) and `two_port_openems` (worst |S| 1.0053, S12−S21 7.0e−07,
  S11−S22 4.2e−07) — **both measured on real solves, not asserted**.

  ⚠ **Both live gates are built around a trap worth knowing.** A uniform coax
  and a symmetric filter both give S11 == S22 and S12 == S21 *by physics*, so
  a swapped-column mislabelling is INVISIBLE in the values. The proof is
  structural instead — each excitation's own output must carry its own column
  and the sets must be disjoint. Palace names the terms in its CSV header;
  openEMS names them in its filenames.
* **Touchstone export follows what was actually solved.** `write_touchstone`
  now writes `.sNp` for whatever order the solve COMPLETED and refuses
  otherwise, naming the missing terms. Both full-wave backends excite exactly
  one port by construction — openEMS refuses anything else, Palace marks port
  1 excited with the rest passive — so a run yields one **column** of the
  S-matrix. S11 and S21 are real; S12 and S22 do not exist anywhere, and
  reciprocity does not close the gap (it gives S12 = S21 and leaves S22
  unknown). A `.s2p` written today would have a fabricated half, and a VNA
  comparison would read it as measurement. ⚠ The default order is the largest
  **complete** matrix, not the largest port index mentioned — without that,
  today's S11+S21 result would have stopped writing the `.s1p` it always has.
  New FAST gate `touchstone_export`, 5 mutations caught including a transposed
  S11/S21/S12/S22 column order, which is the format's own trap.
* **N ports, not two.** The S-matrix chain was written 2-port-first and had
  four places where "two" was a literal rather than a count. All four now
  derive it, so a 3-port junction or a 4-port coupler runs the same path a
  2-port does:
  * **Mesh attributes are derived** (`gmsh_box.wg_port_attr` /
    `wg_wall_attr`): interior 1, ports 2..N+1, walls N+2. For N = 2 that is
    exactly the historical `interior=1, port1=2, port2=3, walls=4`, so every
    existing mesh and config is byte-identical. ⚠ **The wall attribute moves
    with the port count**, and the old constant `WG_WALL_ATTR` is 4 — which is
    PORT 3's attribute on a 3-port mesh. Tagging walls with it would hand
    Palace a face that is both a port and PEC, which it does not report as the
    error it is. The gate pins that collision so the constant cannot creep
    back.
  * **The BREP mesher takes N port faces** (`gmsh_brep.normalise_port_faces`),
    either as `(axis, at_max)` — the same slab query the 2-port path always
    used, which covers T and Y junctions and crosses — or as an explicit
    bounding box for what that shorthand cannot say. `ports=None` still means
    the two ends of `axis`, so nothing existing moves.
  * **`build_driven_config` takes `n_ports`** and builds that many wave ports.
  * **The excitation list follows the mesh** instead of being `[1, 2]`, and
    `set_excitation` now **refuses** an unknown port rather than clearing every
    excitation and driving none — a config Palace solves happily, returning a
    column of numbers with nothing behind them. Only reachable once the list
    stopped being a literal, which is precisely when an off-by-one becomes
    possible.
  * **openEMS loops** over the remaining ports (`exc<N>/` each) instead of
    hardcoding port 2, driving the document's own port NUMBERS — a user who
    deletes a port leaves 1 and 3 behind, and `range(1, n+1)` would ask for a
    port 2 that does not exist.
  * **The estimate prices N solves**, not two. It multiplied by 2 for a full
    matrix, which is right only for a 2-port and would have been the largest
    under-estimate in the product on a 4-port. ⚠ It falls back to **1**, not to
    a port count invented here, when an analysis cannot be counted.
  `Full2Port` is renamed **`FullSMatrix`** to match. Renamed outright rather
  than deprecated because it never reached a customer — the 2-port work is
  still unreleased — but documents saved while it was being proven are
  migrated on restore, since silently resetting the switch would turn a
  full-matrix solve back into a single column with nothing to show for it.
  New FAST gate `n_port_smatrix` (49 checks, **10 mutations caught**) built on
  a deliberately ASYMMETRIC 3-port fixture, plus a migration check in the
  FreeCAD smoke (1 mutation). ⚠ **Three is the smallest order that can catch
  any of this**: a uniform 2-port is symmetric, so a transpose is invisible in
  the values; the 2-port file is one line, so the layout rule never fires; and
  4 is the correct wall attribute for a 2-port, so the constant looks right
  forever.
  ⚠ **Scope, stated rather than implied:** the engine is N-port end to end
  (mesh → config → excitation loop → merge → `.sNp`), but the DOCUMENT still
  has no way to say which face is port 3 — `build_waveguide_model` infers two
  ports from the longest bounding-box axis, so every solve driven from the GUI
  is still a 2-port. The seam is wired; the face picker is not built.

### Fixed
* **Four more solve paths now ask before they start.** The v1.2.0 pre-solve
  estimate was wired into the four solver paths and the parametric CFD
  dialogs; a deliberate audit found four more that launch real solvers
  **directly** through `run_generic_gui`, which is why the earlier sweep — it
  looked at solver-object paths — could not see them. `confirm_solve` appeared
  nowhere in either file:
  * the **RFDF correlative manifold**, which is *N* NEC2 far-field solves, one
    per array element, sized from a ring count the user just typed;
  * the Cable Designer's **full-wave verify**, a real Palace FEM solve — the
    longest thing that dialog can start;
  * the Cable Designer's **FastHenry bundle coupling**, two runs, on both the
    coupling and the diff pages.
  ⚠ Each states its own work measure, matched to the backend it uses, so the
  new paths share that backend's measured history instead of each starting a
  private bucket. The cable dialog's OpenFOAM path was already covered — it
  delegates to `convection_dialog`, which confirms.
* **A validation gate that could not fail, and is now proven to fail.**
  `pattern_sweep`'s `gate_wiring` and `gate_writer` (18 checks) asserted that
  `runner.py` and `writer.py` **CONTAINED literal lines** — they tested what
  the files SAY, not what they DO. Measured: **three behaviour-destroying
  mutations all stayed green**, including turning `if multi:` into
  `if False:`, which makes the entire multi-frequency branch — the feature the
  gate exists to defend — unreachable while every asserted substring survives.
  Both are rewritten to drive the real code: `gate_writer` writes REAL DECKS
  and reads the FR/RP cards back (the artefact nec2c consumes, the same
  standard the Elmer gates apply to their `.sif`), and `gate_wiring` runs the
  REAL runner with only the binary and the deck writer stubbed, asserting on
  the `SweepResult` it returns. The same three mutations are now caught 3/3.
* **`export_free.py --check` was blind to renamed files.** `drift()` compared
  every file at its SOURCE path and never applied the manifest's rename map,
  so `docs/README.free.md` was reported *missing* for ever, its published copy
  `README.md` was reported *extra* for ever, and — the part that bites — the
  public README **was never compared against its source at all**. Real drift in
  the first file any visitor reads would not have shown up. Two permanent false
  positives also train the reader to skim the checker.
* **`SweepResult` declares its optional extras.** `farfield`, `farfields`,
  `currents`, `currents_all` and `nearfield` were bolted on after construction
  by the NEC2 and openEMS runners and declared by no `__init__`, so every
  reader had to guess whether the attribute existed. `s_others` was given a
  real field for exactly this reason and its four siblings were left behind.
  `None` / `[]` now says "this run produced none", which a reader can act on,
  where a missing attribute is only a question.
* **A `.s3p` was written as one long line, and that is not the format.**
  Touchstone puts a whole frequency entry on one line for 1 and 2 ports, but
  from **3 ports up it is one matrix ROW per line**, wrapped at four pairs per
  line from 5 ports up. The writer emitted every order as a single line, so
  any `.s3p` it produced was non-compliant — other tools reject it or, worse,
  misparse it. Nothing consumed a `.s3p` yet, which is exactly why no gate
  caught it. 1- and 2-port files are unchanged, quirk column order included.
* **`s_others` is a real field now.** The transmission terms were an
  undeclared attribute bolted on after construction by the openEMS and Palace
  runners, so every reader had to guess whether it existed —
  `results_dialog` guarded with `getattr`, `cable_dialog` did not, and a NEC2
  or Elmer result reaching that path was an AttributeError waiting for a user
  to find.

## [1.1.0] — 2026-08-19 — CFD on what you select, and FastHenry's licence resolved

### Added
* **FastHenry redistribution — unblocked, built, and STAGED.** The licence
  question that kept Windows users compiling their own FastHenry is resolved
  in writing: the M.I.T.-copyrighted material is governed by the 2003
  re-release (distribution permitted, notice must travel), and
  FastFieldSolvers' own modifications are LGPL per their General Manager's
  statement of 2026-08-13 ("you can redistribute the binaries"). The release
  assets exist and are verified — `tools/build_fasthenry_dist.py` compiles
  fasthenry.exe through the shipping build path, packages it with both
  licence texts and the complete corresponding source (exact patched tree,
  upstream commit 363e43e), and then proves the SHIPPED zip solves a
  closed-form copper bar on a bare PATH before it may ship. The guided
  Install plan is staged (`FASTHENRY_WIN_INSTALL_STAGED`), deliberately not
  live until the M.I.T. TLO answers the confirmation request; the activation
  checklist rides with the constant. Downloads verify a pinned **sha256**
  now: `run_win_install` gained optional per-plan hash pinning (verify
  before extraction, refuse loudly on mismatch) — pinned for self-hosted
  assets, deliberately absent for upstream URLs whose bytes legitimately
  refresh — and **self-hosted now IMPLIES pinned**: the smoke gate requires
  a sha256 on every self-hosted plan, and the existing nec2++ asset is
  pinned from the live zip. Gate: `fasthenry_guidance` grew 16 checks
  (staged-plan shape + the pinning behaviour end to end through the real
  installer, with the hash expectation computed independently of the code
  under test); 6 mutations caught, two of them found by adversarial review
  (a hashlib-algorithm swap and a log-wording drift that silently disarmed
  the ordering check). Stale user-facing licence text repeating the
  superseded "noncommercial, no redistribution" reading is corrected in
  Solver Setup hints, README, the free README and the user manual.
* **Conjugate natural convection — measured, anchored, gated (ROADMAP §8c,
  first rung).** `cht.gap_nusselt()` turns a solved buoyant CHT case into
  (q, T_interface, Nu, Ra) via the validated solid-mean recovery — an
  engine function, so the coming dialog and the gates measure through one
  door. New SOLVER gate `openfoam_cht_convection`: the 40x60 gap at
  interface Ra ~8.5e5 must land Nu in **[5.5, 8.6]** — a window deliberately
  wider than every in-range reference (Berkovsky-Polevikov 6.64 at A=4,
  ElSherbiny-class 6.41), because its job is to keep a geometry artifact
  near the conduction limit dead rather than to certify a correlation; the
  gate's 40×60 mesh measures 6.85, and the
  interface-referenced Ra in [5e5, 9e5] (independently kills both the
  conduction limit and a nominal-drop referencing slip), and the interface
  temperature must drop below the conduction answer. FAST identity checks
  in `cht_setup` (conduction mean → exactly Nu 1, q, T_int; Ra linearity);
  4 mutations caught. ⚠ A citation correction that outlived three session
  notes: the "Berkovsky-Polevikov 8.549" reference was MacGregor & Emery —
  B-P with its aspect factor gives 6.6-6.9 here.
  **And the mesh is no longer suspect.** A refinement pass on the FIXED
  mesh gives 40×60 → 60×90 = Nu **6.8529 → 6.6957 (−2.3 %)**, both proven
  converged from the solver log (max-T drift ~0 over the last 1000
  iterations, residuals ~1e-8). That kills the 08-17 data point which had
  refinement collapsing Nu 1.8768 → 1.2001 *toward* the conduction limit —
  that was the swapped-face-set geometry artifact, not resolution, and the
  signature is now gone. 6.6957 lands inside Berkovsky-Polevikov's own
  6.6-6.9 band.
* **Analysis ▸ Solve Conjugate Heat Transfer (slab + air gap)… — the §8c
  dialog.** A solid layer against a vertical air gap, the two regions
  COUPLED, so the interface temperature is solved rather than assumed.
  Parametric and honest about it (the dialog states it does NOT read the
  document — the reference-trefoil lesson). Buoyancy off reproduces the
  closed form to 5 decimals live; buoyancy on reports the gap Nu,
  through-flux, solved interface temperature and interface-referenced Ra —
  solved with **real air near 300 K** (`make_case` pins `target_ra = 0`; a
  tuned viscosity is for gates, not users — gate-enforced), with regime
  warnings when the case leaves the validated envelope: Ra beyond laminar,
  aspect outside 2–10, a film temperature far off the 300 K property
  constants, or a solid too conductive for the Nu recovery to measure —
  and an outright REFUSAL of hot faces the Boussinesq air model cannot
  represent (its linearised density reaches zero at ~603 K). Worker thread + REAL Cancel (`run_cht` grew the same
  `cancel` contract as `run_solid`), and *Show gap field in 3-D view* via
  new multi-region VTK support (`vtk_export` `region=` — `foamToVTK
  -region` layout MEASURED on v2512, verified end to end on a live case).
  10 new FAST checks in `cht_setup` (the dialog's headless contract);
  3 more mutations caught (derived-mu, dead regime warning, dropped
  honesty phrase).
* **CFD on the solid you SELECT — Analysis ▸ Solve Convection on Selected
  Solid (open air)… (ROADMAP §8a).** Select any solid in the document — a
  coil, a PCB, a housing — enter its dissipated power, and OpenFOAM solves
  its natural convection: the solid is tessellated AS-IS (document
  orientation, gravity −z), immersed in an open-air box (far walls at
  ambient — the honest reading of "no enclosure in the model"), the power
  becomes a surface heat flux, and the result is the surface temperature
  rise, the mean film coefficient, and the solved field loadable into the
  3-D view. Long solves run on a worker thread with a real Cancel.
  **Anchored on a sphere, both ways, measured live (cells_bg 32):**
  * conduction (g = 0): Nu_D **2.5575** inside the EXACT two-sided
    sandwich **[2.3374, 2.6667]** (concentric-shell closed forms bracket
    the box domain by Dirichlet monotonicity — citation-free);
  * free convection: Nu_D **18.17** at the resulting Ra_D 1.33e6 vs
    Churchill's sphere correlation 17.42 — **+4.3 %**, inside the
    correlation's own scatter, beside the bundle ladder's cylinder rungs.
  New gates: `solid_setup` (FAST, offline — 6 mutations caught) and
  `openfoam_solid` (SOLVER, the live sphere rungs). Scope stated in the
  dialog: laminar, constant properties at a film temperature (the dialog
  warns when the solved film strays), no enclosure geometry read yet, no
  radiation. Wind on structures remains ROADMAP §8b, blocked on a
  turbulence anchor.

### Fixed
* **The convection solve can now actually be cancelled — and no longer
  freezes FreeCAD.** The Convection Designer ran its multi-minute CFD
  synchronously on the GUI thread, so the whole window went Not Responding
  and the Close button, while visibly present, could not be serviced until
  the very solve it was meant to stop had finished. The solve now runs on a
  worker thread (the installer dialog's proven idiom) with a **Cancel
  solve** button that kills the running OpenFOAM chain — the whole process
  group, not just the wrapping shell, so no orphaned solver keeps burning
  CPU behind a cancelled dialog. Closing the dialog mid-solve cancels too.
  New FAST gate `openfoam_runner_cancel` (prompt return, `cancelled=True`
  report, child-process-dead), 3 mutations caught.
* **The OpenFOAM menu command now says it solves the built-in REFERENCE
  trefoil.** "Solve Convection" read as "solve my document": a user with a
  helical coil in the viewport was told a CFD was running "on three cables"
  with no way to know those cables were a built-in reference geometry
  (three 20 mm at 30 mm pitch) and that nothing in the 3-D view is ever
  read by that path. The menu entry, tooltip and dialog now say so in as
  many words, and point at the Cable Designer's Bundle tab — the door that
  solves YOUR bundle. (The wider principle this surfaced — CFD should
  attach to the thing you select, thermal on a coil or PCB, wind on a
  structure — is now a designed roadmap item; see ROADMAP §8.)

## [1.0.0] — 2026-08-16 — one-point-oh, and a free 14-day trial

The roadmap that started this project is complete — every planned section
shipped and gated (§1 Element Designer, §3 AI assistant, §4 Watt breadth,
§5 co-site, §6 coverage, §7 System Designer, the OpenFOAM thermal arc), the
first user bug reports have been fixed and verified on all three OSes, and
the free/Pro split has been public since v0.77.0. This release marks it.

### Added
* **A free 14-day trial of EMStudio Pro.** The blind leap was the last wall
  in the funnel: $149 on faith from an unknown brand. The trial is the SAME
  Pro zip, offered as a $0 download at the same store: install it and press
  **Start free trial** in Help ▸ EMStudio Pro — no key, no account. After 14
  days the Pro commands stand down and the free workbench continues
  untouched; entering a purchased key at any time simply replaces the trial.
  * Serverless like everything else in the licence path:
    `licence.start_trial()` / `trial_status()` keep a dated record beside the
    activation cache. It is HMAC-stamped so a casual text edit reads as
    expired rather than fresh — and deliberately no stronger (deleting the
    file re-trials; the person determined enough was never a lost sale, and
    clock-tamper paranoia costs more goodwill than it protects revenue).
  * Precedence is absolute: a licence key always outranks trial state, so a
    refunded purchase can never keep working behind a leftover trial record.
  * The licence dialog gains **Start free trial**; the Pro teaser dialogs
    gain **Try free for 14 days…**; About/Help/PRO.md copy carries the offer.
  * Gate `pro_licence` grew 12 trial checks (fresh start = 14 days, expiry,
    tamper-reads-as-expired, no restart, key-over-trial precedence — including
    the decisive case: an ACTIVE trial must not mask a key Gumroad REFUSES).
    Mutation-proven: dropping the MAC check, inverting key/trial precedence
    and stretching the window were each caught.

### Notes
* Versions 0.99.0/0.99.1 are included; see their entries below. The teaser
  entries in the free build (v0.99.1) now offer the trial as their soft CTA.

## [0.99.1] — 2026-08-16 — the free build points at Pro instead of hiding it

### Fixed
* **gui_smoke's two reds from the v0.99.0 session are green again.** Both
  pre-dated the teaser work (verified by stashing it and re-running HEAD):
  * **The viewport scrubber could still land on the wrong monitor.** The
    v0.99.0 `_clamp_into` fix computed the right target, but the window
    system delivers a moveEvent AT the requested point and only THEN the
    adjustment that yanks a freshly shown tool window to the primary screen
    — so the first placement onto a negative-coordinate monitor ended at
    (0, 0) anyway, and neither a synchronous check nor a zero-delay timer
    could see it (pos() reports the requested point until the adjustment
    lands). The scrubber now records its intended position and re-asserts
    it ONCE from `moveEvent`, synchronously, inside a half-second watch
    window — long enough to outlive placement churn, far shorter than a
    human reaching for the title bar, so a drag is never fought.
  * **The Solver Setup gate still asserted "no Build button on Windows",**
    which was the truth until v0.99.0 made it false deliberately: FastHenry
    has no usable Windows binary, so `win_source_build_plan()` compiles it
    with the machine's own toolchain (and returns None without one). The
    gate now asserts the real contract — a Build button only where a
    Windows source-build plan exists, and `build_plan()` (the POSIX bash
    recipe) still None everywhere under nt.

### Added
* **The free workbench now SHOWS the paid features it does not have.** Until
  now `export_free.py` deleted the Pro commands outright, so a free user's
  System menu simply had a hole in it and the only mentions of Pro were an
  About section and a Help entry that reads like an install chore. Measured
  the day this shipped: **145 estimated installs, 111 page views, 1 star and
  0 sales** — nobody buys a room they never learn exists.

  The four entries (Matching Designer, Array Designer, RF Direction Finding,
  AI Assistant) now stay in their menus marked "(Pro)" with a badge icon, and
  clicking one opens a single explainer — what the feature does, what it was
  MEASURED against, and the price. New `emstudio/ui/pro_teaser.py` (public;
  strings and a dialog, no paid logic) plus a new `emstudio_pro.svg` badge.
  The four real Pro icons stay denied, so browsing the public repo still does
  not enumerate the paid surface.

  Deliberately not nagware: nothing ever pops up on its own, every dialog is
  opened by a click the user chose, and every claim is a measured number from
  a validation gate with its comparison (29.6 dB vs 3.4 dB front-to-back;
  −26.02 dB Chebyshev floor to 0.04 dB; 0.00° manifold decode).
* **A matching pointer at the one moment it is useful** — the sweep-results
  dialog shows `legal.PRO_TEASER_MATCHING` as one quiet grey line **only**
  when the run says the element is not matched (`VSWR_min > VSWR_ACCEPT`) and
  **never** to someone who already has Pro installed. That string and
  `PRO_TEASER_ARRAY` had existed since v0.77.0, written for exactly this
  ("shown WHERE THE NEED APPEARS rather than as a nag"), and had never been
  displayed anywhere. The rule lives in `legal.pro_hint_applies()` — policy,
  GUI-free, so the gate can test it without PySide.
* Gate `pro_teaser` (FAST, Pro-side only — it imports the exporter, which is
  denied to the public tree). Mutation-proven four ways: inverting the rule,
  a manifest key with no FEATURES entry, a menu entry that loses its "(Pro)"
  marker, and a feature that loses its evidence were each caught.

### Changed
* `strip_commands_src` → **`teaser_commands_src`**, and the manifest's
  `strip_commands` list → a `[teaser_commands]` id→key table. Only two of the
  five places a command id lives now change on export: the paid class is
  deleted and its `addCommand` is re-pointed at `_ProTeaser("<key>")`. The
  constant, the id list and the menu row stay. The exporter refuses a key
  with no `FEATURES` entry — that would ship a menu item which RAISES when a
  buyer clicks it — and the audit now checks the teaser module and its icon
  actually reach the public tree.
* Fixed in passing: the old strip left a **stray leading separator** at the
  top of the free build's System menu (it removed trailing ones only). With
  the entries restored the separator is doing its job again.

## [1.0.0] — 2026-08-16 — engine work released in one-point-oh

> Heading corrected 2026-08-19: this section was still titled
> "Unreleased" although its content shipped in 1.0.0 — `cht.py`
> was added 2026-08-14, between 0.99.0 and the 1.0.0 tag.

### Added
* **Conjugate heat transfer** (`solvers/openfoam/cht.py`, `run_cht`). Every
  thermal case before this imposed a condition on the cable surface — a wall
  temperature or a wall flux — which is an assumption about the answer. CHT
  solves solid and fluid together and lets the interface temperature come out
  of the solve. Anchored where the answer is EXACT: with `g = 0` the stack is
  conduction in series, and a linear profile's cell-average equals its analytic
  mean on uniform cells, so both region means are exact AND mesh-insensitive —
  **solved 337.29278 / 312.29278 K against closed-form 337.29278 / 312.29278,
  +0.00000 K**. Gates `cht_setup` (FAST) + `openfoam_cht` (SOLVER).
* **Buoyancy for CHT** — 2-D mesh, `Boussinesq` equation of state and a derived
  Rayleigh number. ⚠ `rhoConst` makes buoyancy IMPOSSIBLE (constant density
  cannot answer temperature, so gravity is inert and the case silently returns
  the conduction answer), and one cell up the cavity leaves a convection cell
  nowhere to turn over — `buoyant` therefore requires BOTH. Proven at the
  conduction limit: gravity ON at Ra 100 returns the closed form to
  **+0.00007 K**. Convection itself is NOT yet validated — see below.
* **Unsteady wind loading** (`WindCase(transient=True)` → `pimpleFoam`), which
  reaches the Reynolds numbers where the flow actually sheds. Anchored on three
  independent quantities: **Re 100 → Cd 1.3411, St 0.1647, Cl amp 0.3275** and
  **Re 150 → Cd 1.3283, St 0.1835, Cl amp 0.5202**, against Williamson's
  laminar correlation (0.2 % and 0.04 %). ⚠ A transient solve does not
  legitimise a high Reynolds number: above ~190 the wake goes 3-D and
  `TURBULENT_RE` refuses it. Real antenna loading still needs a turbulence
  model, which is not built.
* **The solved OpenFOAM field in the 3-D view** — Analysis ▸ Show Convection
  Field in 3-D View. The bundle factor is one number distilled from a whole
  field; the case directory is now carried out of the solve so the field can be
  opened. Volume opaque, boundary patches at 78 % transparency (the enclosure
  encloses the volume, so an opaque patch hides what the view exists to show).
* **A Build button for FastHenry on native Windows**, compiling from source —
  it is the one backend with no usable Windows binary. Appears only when a
  compiler is actually present; EMStudio never bootstraps a toolchain.

### Fixed
* **Run Solver rejected the OpenFOAM solver** with "Unknown solver type",
  which reads like a corrupt document. It now delegates to the convection
  command (delegates, not duplicates — mixed bundles store per-group factors
  through a different door).
* **Solver Setup froze FreeCAD.** Detection ran on the GUI thread from
  `__init__`, so the freeze happened BEFORE the window painted. Now a worker
  thread plus a polling timer, with a "Detecting…" placeholder.
* **FastHenry guidance was a dead end.** The FastFieldSolvers bundle ships no
  `fasthenry.exe`, and its `FastHenry2.exe` is Automation-only — their own
  release notes record that command-line arguments were REMOVED in 2004, and it
  hangs when given any. Detection is deliberately NOT taught that binary
  (reporting it found would hang every solve); the hint and a new status note
  explain the situation instead.
* **`CMD_CONVECTION_FIELD` was registered but missing from `ALL_COMMANDS`**, so
  smoke's GUI registration contract failed under FreeCAD. It shipped CI-green
  because CI runs `python3 smoke`, which skips that contract.
* **Conjugate buoyant runs took the better part of an hour.**
  `momentumPredictor no` on a buoyancy-driven flow leaves velocity to be
  updated only through the pressure correction, so GAMG hit its 1000-iteration
  cap every step while the energy residual was already ~1e-8. With the
  predictor on, tuned GAMG and `residualControl`, **4000 iterations run in
  155 s, ~25x faster** — and the exact conduction case is unchanged.
* **The Rayleigh length scale was the cavity height.** A side-heated vertical
  gap is governed by the GAP WIDTH, with H/L entering separately. A case asking
  for Ra 1e6 really had a width-based Ra of 1.56e4 and returned Nu 1.014 — not
  a wrong solve so much as an answer to a different question.

### Fixed (was a Known limitation)
* **Conjugate natural convection now reproduces the references** — the deficit
  (Nu 1.9 where correlations say ~7-8.5) was `write_cht`'s blockMeshDict with
  the `topBottom`/`frontAndBack` face sets SWAPPED: the empty faces sat on
  gravity's own Y-planes and the Z-planes became no-slip walls one cell apart,
  a scale-invariant Hele-Shaw drag. Found when a 200x scale-up left Nu
  identical to four figures. Fixed and verified: the coupled two-region 5 mm
  gap gives **Nu 6.85** vs the incompressible single-region reference 6.99
  (2 %) and the vertical-slot correlations' 6-8.5 band; T_int and q respond
  to convection exactly as they should. Along the way the shipped cavity was
  validated against de Vahl Davis at Ra 1e4/1e5/1e6 (+0.3/+0.9/+3.0 %) in BOTH
  solver paths — a convective-regime validation the cavity gate never claimed.
  The setup gate now verifies mesh GEOMETRY from vertex coordinates rather
  than patch labels, and fails on the exact shipped bug (mutation-proven).

### Fixed
* **The floating pattern scrubber landed on the wrong MONITOR.**
  `BalloonScrubber._position_over_view` computed its position from the active
  3-D view correctly and then ended in `move(max(x, 0), max(y, 0))`. A Windows
  monitor placed left of or above the primary has NEGATIVE global coordinates,
  so with FreeCAD on such a screen that clamp threw the scrubber onto the
  PRIMARY monitor — a different screen from the viewport it drives. Reported as
  "missing" (AJ, 2026-08-13); it was on the other screen. It is now contained by
  the geometry of the screen the 3-D view is actually on
  (`ref.screen().availableGeometry()`, then `screenAt`, then the primary), in
  BOTH directions — the old line had no far-edge containment either, so a view
  near a screen's bottom-right pushed it off just as invisibly. Positioning
  stays cosmetic and still fails silently by design. Gated in `gui_smoke` with
  the second monitor injected through the reference widget (the offscreen
  platform reports one screen at (0, 0)); 7/7 mutations caught, 7 distinct
  signatures.

## [0.99.0] — 2026-08-12 — a current per member, and FastHenry's licence resolved

### Added
* **A per-member Current (A) column in the Cable Designer's bundle table**, so
  mixed LOADING is reachable without the API. Each member's stated current
  becomes its own I²R loss, its own wall flux, its own snappy patch and its own
  convection factor — the v0.98.0 capability, now usable.
  ⚠ **Two different diameters are in play and conflating them is the trap:**
  the resistance uses `conductor_d_m` (the metal that dissipates), the flux is
  spread over the ENVELOPE `od_m` (the surface the air touches). Gated as one
  pinned expression, and both directions of the swap are caught.
  ⚠ Current is **per copy**, matching what `qty` already means everywhere else.
  ⚠ **All-or-nothing.** A part-filled column is an incomplete answer, not a
  mixed one; the bundle falls back to a single typed gradient rather than
  defaulting the blanks, because an invented heat load standing beside measured
  ones is indistinguishable in the result. Forcing the loaded path on a
  part-filled bundle raises, as does a current with no conductor diameter.
  ⚠ `t_cond_c` for R(T) is an ASSUMPTION and a circular one taken too
  seriously; the dialog takes the Thermal tab's own insulation-class limit so
  the two pages at least assume the same thing.
* **Fixed while building it:** `build_dialog` decided "mixed" from the SIZE
  count, so a one-diameter bundle whose cables carried different currents would
  have gone down the single-diameter path and collapsed both loads into one
  answer. Keyed on GROUP count now. `describe_plan` likewise unpacked 3-tuples
  and would have raised on the loaded path — the one it most needs to describe.

### Fixed
* **FastHenry's licence position, corrected from PRIMARY SOURCE.** Enrico Di
  Lorenzo (FastFieldSolvers) answered, and the 2003 M.I.T. re-release is
  reproduced verbatim in his own `WinMSVS` `license_for_sources_4.0.txt`: it
  grants "use, copy, modify, **sell and/or distribute** … for any purpose".
  The 1994 "distribution strictly prohibited" header still on 18 `master`
  files is **superseded** — backporting dropped the newer notice, which he
  confirmed. ⚠ **The letter to the M.I.T. TLO is moot; do not send it.**
* ⚠ **Downloading FastHenry was never restricted for a USER.** Every
  restriction discussed was about EMStudio hosting the binary. README's
  footnote now leads with that instead of implying otherwise.
* **The Windows hint linked a page that lists no files.**
  `fastfieldsolvers.com/download.htm` is a registration form; the real file
  list is `dwnld02.htm`, and it is not gated — probed: HTTP 200,
  `application/octet-stream`, 27,202,233 bytes for
  `fastfieldsolvers_bundle_5.2.0_setup_x64.exe` (FastHenry2 + FastCap2 +
  FasterCap + FastModel). The hint now names the bundle and links that page,
  and the source comment claiming the site gates downloads behind a form is
  corrected. FastHenry stays out of the guided installs on the LICENCE
  question alone, not on availability.
  ⚠ Still open, and the only thing blocking an Install button: the licence on
  FastFieldSolvers' OWN 64-bit modifications — his email says LGPL, their
  licence file's §2 grants only a right to use.
* **Mutation harness, third fault of one family.** A mutation that made the
  gate raise `KeyError` scored as a SURVIVOR, because the harness read an empty
  accumulator without asking whether the gate finished. It now treats a raised
  exception as a failure, on top of running both gates, reading either
  accumulator name, and refusing a gate that produced no check output.
  **32/32 caught.** The one duplicate failure signature was investigated, not
  waved through: the two "which diameter goes where" mutations are two
  spellings of one conflation, and a check broken by one but not the other is
  not constructible — both diameters appear multiplicatively in one expression.

## [0.98.0] — 2026-08-12 — same size, different current, different factor

The v0.97.0 per-size result was keyed by DIAMETER, so two cables of one size on
different losses collided and the solve had to be refused. The key was simply
wrong — a group is *(diameter, wall flux)* — and fixing it turned out to expose
the bigger of the two effects: **18.3 % between two identical cables**, against
12.3 % for a 20/10 mm diameter mix.

### Added
* **MIXED LOADING within one diameter — two same-size cables on different
  losses now get their own factors instead of being refused.** v0.97.0 keyed
  the per-size result by DIAMETER, so a same-size pair collided and one was
  silently dropped; it had to refuse the arrangement rather than lose a group.
  A group is really **(diameter, wall flux)** — that is what one snappy patch
  can carry — so the result is now keyed by **patch**. Nothing about the mesh
  changed: the case writer had always split those cables onto separate patches
  correctly. It was bookkeeping, and the bug it caused was the dangerous kind,
  because a lost group is a cable rated on somebody else's number.
* **MEASURED — and it is a bigger effect than the diameter mix.** Two 20 mm
  cables, same size, same 0.20 m enclosure, only the flux differs:

      20 mm @ 400 K/m   dT 2.14349   Nu 3.7322 @ Ra 5359   factor 0.9876
      20 mm @ 100 K/m   dT 0.79277   Nu 2.5228 @ Ra 1982   factor 0.8346

  **18.3 % apart for two cables of the SAME SIZE** — against 12.3 % for the
  20/10 mm diameter mix. The LIGHTLY loaded cable is the worse cooled: its own
  driving dT is small and it sits in its neighbour's warm field, so the
  correlation flatters it most. Quoting "the 20 mm factor" for that bundle is
  wrong by 18 % for one of them.
  ⚠ The dT ratio is **2.70 for a 4:1 flux ratio** — neither the 1.0 a shared
  boundary condition would give nor the ~3.0 of two uncoupled cables. That is
  what two cables genuinely heating each other in one enclosure looks like,
  and it is the gate's proof that this is ONE coupled solve.
* `factor_for(d)` still answers directly whenever a diameter is unambiguous, so
  the common case did not get harder; it refuses, **naming the fluxes**, only
  when one diameter really does carry several groups. `by_size` likewise
  refuses rather than dropping a group. `SizeFactors` keys ambiguous sizes as
  `<mm>@<K/m>` and leaves unambiguous ones bare, so documents written by
  v0.97.0 read back identically.
* ⚠ **The staleness key now sees the loading.** Which cable carries which loss
  changes every group's answer, and the provenance's "100..400 K/m" range
  summary cannot tell an arrangement from its mirror. A staleness check that
  cannot see a change is not a staleness check.
* **The assistant gained the rule that would otherwise have gone silent.** A
  bundle of ONE diameter has `sizes == 1`, so the mixed-diameter note never
  fires — and yet its cables have different factors. `thermal_advice` rule 6b
  fires on GROUPS, before any CFD, and the free tier carries the same warning
  in plainer words.
* ⚠ **API-level for now.** The Cable Designer's bundle table has no per-member
  current column, so the UI cannot yet build a mixed-loading case; the dialog
  and the advice already handle it for the day it can.
* **Gated**: `openfoam_bundle` grows a live `load` rung — two 20 mm cables,
  identical geometry, only the flux differing, which makes it the sharpest
  attribution test here (the mixed-DIAMETER rung cannot say this, because
  there D and the flux both change at once). 12 488 cells, **175 s**.
  Equal face counts are an EQUALITY, not a band. `thermal` covers the per-group
  arithmetic and every refusal in the FAST tier; `assistant` covers rule 6b;
  `smoke` covers the `@`-keyed document round-trip.
  **Mutations: 25/25 caught with 25 DISTINCT failure signatures.**
  ⚠ Two harness faults found and fixed on the way, both of which had scored
  real mutations as survivors: the harness ran only ONE of the two gates, and
  it read `_FAILED` when the thermal gate accumulates into `FAILURES`. It now
  runs both and **refuses to score a gate that produced no check output** —
  a green from a gate that never ran is not a green.

## [0.97.0] — 2026-08-12 — a CFD number for the bundle you actually have

Three OpenFOAM slices land together: the **mixed-diameter bundle** (the one
that makes the convection button useful on the shipped default cable mix), the
**Joule coupling** that drives the wall flux from the conductor's own I²R, and
**wind loading** — the first mechanical axis this workbench has ever had. Plus
a retraction: the `fvOptions` blocker was mine, not OpenFOAM's.

### Added
* **MIXED-DIAMETER BUNDLES — the convection button no longer refuses on first
  click.** The shipped default cable mix is mixed, so the feature that landed
  with phases A+B was honest and useless: `Nu_D` is built on a diameter, a mean
  of unlike cables has no defensible definition, so it raised. What makes it
  answerable is that the question was the wrong shape — **a mixed bundle does
  not need ONE Nusselt number, it needs one per size.**
  Each size group is written as its own STL solid, becomes its own snappy
  geometry entry and therefore its own **patch**; the solve reports a separate
  mean surface temperature per size, and each size gets
  `Nu_D = D_i (dT/dn)_i / (T_i - T_inf)` against **its own** diameter and its
  own solved dT. Verified live on v2512: snappy emitted `cables_g0_d20p0` and
  `cables_g1_d10p0` as two `wall` patches, checkMesh **Mesh OK**.
  Nothing is averaged across unlike cables at any point.
* **MEASURED — and the measurement is the argument for the feature.** Fourth
  rung of the same ladder: same three centres, same 0.20 m enclosure, same
  400 K/m, two of the three cables shrunk 20 mm -> 10 mm, nothing else moved.

      1 x 20 mm   Nu 3.6097 @ Ra 5541   Churchill-Chu  -5.21 %   factor 0.9479
      2 x 10 mm   Nu 1.9997 @ Ra  625   Churchill-Chu -15.62 %   factor 0.8438

  **The two sizes' factors are 12.3 % apart** — one factor for this bundle is
  wrong by 12 % for one of its sizes. Both still sit BELOW their own
  correlation, so the bundle penalty is per size, not a property of one
  diameter. And the 20 mm cable recovers most of the penalty when its
  neighbours shrink: **Nu 3.1542 -> 3.6097 (+14.4 %)**, Churchill-Chu error
  **-19.72 % -> -5.21 %**, because smaller neighbours dump less heat into the
  same air. ⚠ `converged` is False on both (residualControl never fires on
  this domain, as on the cylinder); Nu drift between the last two snapshots is
  **4.1e-5 and 2.6e-4**, which is the honest test.
* **`BundleCase(cables=[(x, y, d)])`** beside the original
  `centres=`/`d_cable=`; **`MixedBundleNusselt`** (per-patch readings, and it
  REFUSES a single `nu_d`); **`solve_mixed_bundle_factor()` ->
  `MixedBundleFactor`** with `factor_for(d)`, `worst` and `spread_pct`;
  `SolverOpenFOAM.SizeFactors` caches the per-size answers on the document.
* ⚠ **The uniform case is byte-for-byte UNCHANGED, and that is asserted, not
  assumed.** One size means one group named `cables`, exactly as before. The
  gate writes the same bundle through both the old `centres`/`d_cable` contract
  and the new per-cable list and compares **sha256 over all 14 files** — the
  measured ladder (Nu 3.9826 / 3.8621 / 3.1542) is this gate's only anchor, and
  a change that quietly re-meshed it would have invalidated every number in the
  docstring while every other check still passed.
* ⚠ **Smaller cables are refined HARDER, deliberately.** snappy's levels are
  relative to the background cell, so at one level a 10 mm cable gets half the
  faces of a 20 mm one and its boundary layer is resolved half as well — its Nu
  would carry a discretisation bias the large one does not.
  `refine_match_perimeter` adds `ceil(log2(d_max/d_i))` levels to the smaller
  groups. It is on by default; off is a fidelity choice, not a free saving.
  ⚠ It is not free in cells either: the 20/10/10 case meshes to **52 174 cells
  against the uniform trefoil's ~15 000**, so a mixed solve costs several times
  a uniform one.
* ⚠ **Per-size GRADIENTS, because cables of different sizes rarely carry the
  same loss.** A scalar gradient is equal flux DENSITY (the fat cable then
  dissipates proportionally more W/m) and the provenance says so;
  `joule_w_per_m` accepts one loss per cable so each size is driven by its own
  I²R. A per-cable list of the wrong length is refused rather than recycled.
* ⚠ **One fluid, one (nu, alpha)** — fixed from the LARGEST cable's nominal dT.
  Per-group properties would be a different fluid around each cable, which is
  not a physical case. Every group's `Ra_D` is then formed from those shared
  properties with its own D and its own solved dT, and the gate pins that as an
  exact identity (`Ra_i/Ra_j == dT_i D_i^3 / dT_j D_j^3`) — a shared D would
  read 8x out on a 2:1 size ratio.
* ⚠ **No single number is invented.** `MixedBundleFactor.factor` raises and
  names the sizes; `factor_for()` refuses a diameter that was never in the
  enclosure rather than nearest-matching (an interpolated factor looks exactly
  like a solved one). `worst` exists for a caller who must have one number and
  is the most pessimistic size on purpose — over-rating the size the
  correlation flatters least is the unsafe direction. `SolverOpenFOAM` stores
  `worst` in the scalar `BundleFactor` and says in the provenance that it is a
  floor.
* **Gated.** `openfoam_bundle` grows ~70 offline checks and a live MIXED rung;
  `thermal` grows the per-size factor arithmetic and its refusals in the FAST
  tier, so CI covers them; `smoke` pins the document round-trip (including
  that re-solving as uniform CLEARS the stale per-size map); and `gui_smoke`
  now **presses the convection button on a mixed bundle** — a gap that had let
  this button ship broken once already behind a lazy import.
  ⚠ The live rung is a MECHANISM check by design and says so: full fidelity
  costs ~50 min, so the gate runs **cells_x=60 / 3000 it in 542 s** and is
  PINNED against the recorded full-fidelity Nu at 3 % (measured deviation
  +0.34 % / +0.90 %; the band comes from the known error mechanism, since
  coarsening and under-iteration both read high). It is deliberately
  under-iterated — drift 4.9e-3 and 1.6e-2 — and the gate asserts it does NOT
  claim convergence it has not earned.
  ⚠ It is NOT compared against the uniform `bundle` rung: different mesh, and
  a study that moves two things at once measures neither. The +14.4 % ladder
  figure is printed with that caveat, not gated.
  **Mutations: 16/16 caught with 16 DISTINCT failure signatures** (fresh
  subprocess per mutation and a control after every restore — a leaking
  harness once scored itself 8/8 here on one mutation caught eight times, and
  the tell was that every mutation broke the identical checks), plus two
  targeted ones proving the smoke and gui_smoke additions can fail.
* **The assistant fires on the SHAPE of the design again** (`thermal_advice`
  rules 6 and 7): a mixed bundle is warned about before any CFD is run, and
  after a solve the spread between the sizes is reported — wide means one
  factor cannot describe the bundle, narrow says so too rather than staying
  silent. The free tier gets the same warning in plainer words, as always.
* **`emstudio/solvers/openfoam/wind.py` — wind loading, the MECHANICAL axis.**
  Every other OpenFOAM case here is thermal. This one asks what force the wind
  puts on a structure so it can be sized to survive: `simpleFoam` + the
  `forces` function object on an open O-grid, reusing geometry the document
  already holds and producing loads FreeCAD's FEM workbench can consume.
* **Anchored at Re 20–40, deliberately NOT at the familiar Cd ~1.2.** Above
  Re ~47 a cylinder sheds vortices and a STEADY solve produces a symmetric
  wake that under-reads drag — gating on Cd ~1.2 at Re 1e5 would gate on a
  number this method cannot produce. Measured, live: **Cd 2.0646 at Re 20 and
  1.5448 at Re 40**, with |Cl|/|Cd| ~2e-7 (zero lift by symmetry — exact,
  citation-free, and the sharpest check that force integration is oriented
  right), pressure + viscous == total, and the viscous SHARE of drag falling
  40.3 % → 34.9 % because skin friction matters more at low Re.
  The classical benchmark values (~2.05 / ~1.54) are printed as CONTEXT and
  **not gated on** — they are quoted from memory, not verified from a primary
  source, and hard-coding a remembered reference is the mistake the cavity
  gate exists to avoid.
* **The case refuses to be misread.** `validity_note()` fires above the
  shedding onset and `run_wind` surfaces it whether or not the caller asks.
  ⚠ Real antenna loading is Re 1e5–1e6, well above this: what is built is the
  pipeline, its anchor and the guard. Structural loads at real wind speeds
  need an unsteady solve (`pimpleFoam`) or a validated turbulence model.
* ⚠ **First result path in this package to use a FUNCTION OBJECT.** The
  thermal cases avoid them (`wallHeatFlux` aborts on Ubuntu's 1912 build);
  forces would otherwise mean reconstructing face areas and normals from
  polyMesh. Defensible because discovery's probe already REQUIRES a function
  object to pass — but it makes this case depend on that probe.
  ⚠ And measured: on v2512 `forces` reports to the **log** and writes no
  `postProcessing` files under this configuration, so `forces_from_log()`
  matches the Total/Pressure/Viscous block STRUCTURALLY and raises rather than
  returning zeros — a zero force is a physical claim, "could not read it" is not.
  ⚠ `simpleFoam`'s pressure is KINEMATIC, so without `rhoInf` the forces come
  back short by a factor of rho — plausible-looking and simply wrong. Gated.

### Fixed
* **RETRACTED: "`buoyantBoussinesqSimpleFoam` silently ignores `fvOptions`".**
  That finding was wrong and it was load-bearing — it was written up as the
  reason the Joule coupling was blocked and needed a fourth case writer. The
  probe wrote `system/fvOptions` with **no `FoamFile` header**; OpenFOAM warns
  on a headerless dictionary, treats it as empty ("No finite volume options
  present"), and said so in the log. The "decisive" garbage-type test proved
  only that an EMPTY dict contains no bad types, and the warning was missed by
  grepping for `FATAL`/`error` — which does not match a **FOAM Warning**.
  Measured with a header: the garbage type aborts, and a real source moves
  max T **300.4854 → 315.7984** (Boussinesq) and **316.4405 → 347.1201**
  (`buoyantSimpleFoam`). No fourth writer is needed for a volumetric source.

### Added
* **`emstudio/wire/bundle_convection.py` — the bundle factor now has a SOURCE.**
  The seam existed with nothing producing a factor. This solves the user's own
  arrangement and returns `factor = Nu_solved / Churchill-Chu(Ra_resulting)` —
  **0.8028** for the measured trefoil. It consumes `Bundle.pack()`, so the
  Cable Designer's own packing feeds the case rather than the user restating
  geometry. It **refuses** mixed diameters instead of averaging them (Nu_D is
  defined against one diameter), **refuses** to invent a factor when the solve
  fails, and flags a factor above 1 as needing forced flow to be physical.
  ⚠ The factor is measured at ONE operating point and the provenance records
  the Ra it was solved at — the flux BC makes Ra an output.
* **`SolverOpenFOAM` document object + Analysis-group commands.** Unlike every
  other solver object this one CACHES a result, because the factor is consumed
  inside `solve_steady`'s ~80-evaluation bisection — re-solving there would be
  thousands of CFD runs. So it stores the factor, its provenance, its
  convergence state, and the geometry it was solved for. `factor_stale()`
  returns **True when no geometry is recorded**: "cannot be shown to match"
  must never read as "matches".
* **`emstudio/ui/convection_dialog.py` — question-shaped, not a CFD panel.**
  FreeCAD already has general CFD front ends and a generic panel only helps
  someone who already decided to run CFD; the user who needs this never opens
  it and just reads an optimistic ampacity. So the dialog states what the
  ampacity uses today, quotes the measured magnitude BEFORE the user spends
  minutes, warns that a real solve is starting, and reports the factor with
  provenance plus the assistant's advice. `advice_for()` falls back to the same
  warnings in plainer words without Pro — a tier boundary must never become a
  correctness difference.
* **Wired into the Cable Designer's bundle page.** The moment a user builds a
  bundle there, the thermal answer elsewhere in that same dialog is optimistic;
  that is where they can be told. Geometry comes from `_bundle_model()`, the
  SAME packing the page already reports, so the factor is solved for the bundle
  on screen. ⚠ The shipped default mix is MIXED-diameter, so the button refuses
  on first use and names the options (uniform members, per-size solves, or the
  NEC table). Mixed bundles are the common case and need per-cable patches in
  snappy — real work, not a tweak, and not done.
* **`emstudio/solvers/openfoam/bundle.py` — the cable BUNDLE in an enclosure,
  and the first OpenFOAM result that changes a number the product prints.**
  A fourth case writer (snappyHexMesh, an STL written from parameters, a
  prescribed-flux boundary condition). Measured ladder, each rung changing ONE
  variable so confinement and bundling are separated rather than blended:

  | case | cables | box | Nu_D | Ra_D | vs Churchill-Chu |
  |---|---|---|---|---|---|
  | anchor | 1 | 0.40 m | 3.9830 | 5021 | +6.99 % |
  | solo | 1 | 0.20 m | 3.8621 | 5179 | +3.01 % |
  | bundle | 3 | 0.20 m | 3.1542 | 6341 | **−19.72 %** |

  The single-cable rungs land INSIDE the Churchill-Chu/Morgan envelope, which
  is what validates the pipeline — snappy mesh, flux BC and patch reader, none
  of which the structured rungs used. The bundle lands decisively BELOW it:
  **Churchill-Chu over-predicts a trefoil's film coefficient by ~25 %, in the
  unsafe direction** (over-predicted cooling → over-predicted ampacity).
  Confinement alone costs 3 %; the bundle a further 18 %.
* **A result path that needs no cell indexing and no function objects.**
  snappy destroys the predictable cell ordering rungs 1–2 relied on, so the
  boundary condition is inverted: prescribe the wall FLUX (what Joule heating
  physically gives a cable) and read the surface temperature OpenFOAM writes
  into the `boundaryField`. `Nu_D = D·(dT/dn)/(T_s − T_amb)` — conductivity
  cancels. ⚠ Ra becomes an OUTPUT, so correlation comparisons are made at the
  Ra the solve produced.
* **The ampacity seam: `bundle_factor` through `surface_h()` /
  `surface_loss_w_m()` / `solve_steady()`.** A dimensionless correction on
  Churchill-Chu rather than an absolute `h`, because `solve_steady` bisects and
  calls `surface_h` ~80 times per answer (an absolute h would discard the
  correlation's dT behaviour; a callback would mean 80 CFD runs), and because
  it is the same shape as the `NEC_ADJUSTMENT` table already here — measured
  for the actual geometry instead of read off conductor counts. Default 1.0 is
  bit-identical to previous behaviour. Measured effect: a 40 A cable moves
  **56.55 → 59.75 °C**. ⚠ Ra is not scaled (it describes the flow), and
  radiation is not scaled (it does not care how air moves), so the temperature
  shift is smaller than 25 % on `h` alone implies.
* **`emstudio/assistant/thermal_advice.py` (Pro) — the assistant as the
  guardrail.** Exposing CFD in a GUI only helps someone who already decided to
  run it; the user who needs the warning is the one who never opens that dialog
  and just reads an optimistic ampacity. So the rules fire on the SHAPE OF THE
  DESIGN, cost nothing, and work before any CFD exists: a bundle sized on the
  bare correlation, a factor with no provenance, a factor solved for a
  different arrangement, a factor from an unconverged solve, and — the one most
  likely to bite — **double-counting a solved factor against NEC 310.15(C)(1)**,
  since both derate the same physics. A lone cable in free air draws no advice
  at all; advice that fires when it should not is advice users learn to ignore.
* **`emstudio/solvers/openfoam/cylinder.py` — natural convection from a
  horizontal cylinder, the ampacity ANCHOR case.** `wire/thermal.py` takes its
  film coefficient from Churchill-Chu, which is right for an isolated cylinder
  and wrong for a bundle in an enclosure; the plan is to replace it with a
  solved `h`. This is the rung that makes that meaningful — if the CFD cannot
  reproduce the correlation for a lone cylinder, nothing it later says about a
  bundle is interpretable. Two modes: `annulus` (closed, and the mode that
  carries the exact conduction anchor) and `farfield` (open, comparable to the
  correlations). A THIRD case writer beside the cavity, deliberately not a
  generalisation of it.
* **No snappyHexMesh — the decision's cost note is corrected.** A cylinder in
  a concentric far field is an O-grid and `blockMesh` does arc edges: 3200
  cells, `checkMesh` "Mesh OK", max non-orthogonality 1.5e-6, skewness 0.095,
  about a second, volume within 0.1 % of the analytic annulus. snappy is
  deferred to the bundle, which genuinely needs it.
* **`run_chain` now records CONVERGENCE separately from exit code**, and
  `run_cylinder` reports `nu_drift` between snapshots. Both exist because
  `rc == 0` is not convergence — see Fixed.

### Testing
* **`tests/validation/openfoam_cylinder.py`** (SOLVER tier, requires
  OpenFOAM) — 60 offline checks plus the live physics. Anchors, weakest last:
  the exact annulus conduction limit **Nu_D = 2/ln(r_o/r_i)** (live: 2.888547
  vs 2.885390 exact, **+0.11 %**, and Ra-independent across four decades,
  which is what proves it is a conduction limit and not a coincidence); a
  closed-form prediction of what the ESTIMATOR must return on an exact
  logarithmic field, matched to ~1e-14, which is what proves the O-grid cell
  indexing; first-order convergence of that estimator onto a value it does not
  know; radius-weighted energy conservation between the two walls.
* **Gated on the ENVELOPE of both published correlations, not on one.**
  Churchill-Chu and Morgan disagree by 4–17 % over the cable regime (measured:
  17.4 % at Ra 1e2, 8.9 % at 1e4, 4.2 % at 1e6), and `thermal.py` already
  records that Churchill-Chu reads low. A solve cannot be validated to better
  than the literature disagrees with itself. Measured at RR 20: Ra 1e2 → 1.9197,
  1e3 → 3.0000, 1e4 → 4.8207, 1e5 → 7.9788 — inside the envelope at three of
  four and 0.43 % over Morgan at the fourth. Tightened by a distance-from-
  envelope-midpoint check (measured +4.05 / +4.78 / +5.10 / −2.18 %, gated at
  8 %), because the envelope alone is 4–17 % wide.
  ⚠ A "sits nearer Morgan at every Ra" check was written first and was **wrong**
  — true at Ra 1e2/1e3/1e4, false at 1e5 (2.59 % from Churchill-Chu vs 6.52 %
  from Morgan). The CFD's position inside the envelope MOVES with Ra, so there
  is no directional invariant to gate on. The gate caught the overclaim.
* **Mutations: 8/8 caught**, each breaking a different and relevant check —
  the conduction closed form, the grading/wall distance, the O-grid cell index
  (caught by the machine-precision estimator check written for exactly that),
  `pRefCell`, `inletOutlet`, the arc edges, the radius-weighted balance (live)
  and the convergence detector itself (live).
  ⚠ The FIRST harness reported 8/8 and was worthless — one mutation caught
  eight times, because monkeypatches leaked through `sys.modules` across gate
  reloads. Every mutation failing the IDENTICAL checks was the tell. See
  PROJECT_MEMORY: controls must run after EVERY mutation, and `from x import y`
  means patching `x.y` reaches nothing.
* **The domain is PINNED at RR 20**, with a measured sensitivity under 1 % —
  after a method error worth remembering. Growing the radius ratio at fixed
  `n_r` also coarsens the wall cell 4x, which read **+4.04 %** at RR 80 and
  attributed to the domain what was mostly resolution. With the wall spacing
  held constant (n_r 126 / 254): **+0.41 % at RR 40, +0.87 % at RR 80**.
  *A convergence study that moves two things at once measures neither.*

### Fixed
* **`run_cavity` now reports convergence, and the cavity gate had NEVER
  converged.** The flag existed in `run_chain` and was wired into
  `run_cylinder` — because under-iteration had already produced a 34 %-wrong
  Nusselt number there — but was never wired through the cavity path. Adding
  it showed the gate's shipped 1200 iterations converged **nothing**, at any
  Rayleigh number, while its docstring attributed the residual to
  discretisation error. Raised to **4000**, chosen from measurement: every Ra
  fires `residualControl` there and 8000 returns byte-identical Nu, so it has
  margin rather than sitting on an edge. The gate now asserts convergence per
  case.
  The answers barely moved (all under 0.5 %) and every band still held, so
  nothing shipped wrong — but the quoted v0.96.0 figures were unconverged and
  are corrected throughout: Ra 1e2 1.0022 → **1.00146**, 1e4 2.2459 →
  **2.25648**, 1e5 4.6053 → **4.60562**.
  ⚠ `docs/results/cavity_fields_v0.96.0.json` and the recorded cavity page
  still carry the unconverged numbers — a dated v0.96.0 record, left alone
  deliberately rather than silently rewritten.
* **`imbalance` is necessary for convergence, not sufficient — PROJECT_MEMORY
  claimed otherwise.** It called the hot/cold wall balance "a convergence check
  worth more than the residual print". A symmetric half-converged field
  balances perfectly well, and measurably did: **imbalance 9.7e-5 at Ra 1e4 on
  a run that had not converged**. Corrected, with the counterexample recorded.
* **Ra 1e3 is now exercised, and it is the best agreement of the set.** It was
  tabulated in `DE_VAHL_DAVIS` and never checked. On unconverged runs it looked
  like a 4.5 % disagreement that *widened* with mesh refinement — which was
  refinement without a matching iteration budget, not a mesh effect. Converged:
  **+0.14 %** at 40 cells, +0.08 % at 80.
* **Ra 1e6 stays ungated, but with a measurement instead of silence.** At the
  gate's 40x40 it converges and still reads **+6.31 %**; at 80 cells, +1.64 %.
  The mesh is the binding error there, so a real check needs ≥80 cells and its
  own budget. Widening the band to ~7 % would gate the coarseness, not the
  physics.
* **`rc == 0` is not convergence, and it cost a 34 %-wrong answer.** An
  800-iteration annulus run exited cleanly and returned Nu 34 % high; the
  energy-balance check caught it, nothing else would have. `run_chain` now
  records whether `residualControl` actually fired, and the gate contains a
  check that deliberately under-iterates and asserts the detector notices —
  a check that must FAIL to converge, so the detector cannot rot silently.
* **`residualControl` is the wrong test for the open domain.** Measured: Nu
  held at 4.821 ±0.01 % from iteration 2500 to 30000 while residuals sat near
  1e-3 and the control (1e-6/1e-7) never fired — the floor comes from the open
  boundary. Convergence is now judged on the quantity of interest via
  `nu_drift`, which also cut the gate's far-field cost from 40000 iterations
  to 6000.
* `radial_centres` renamed **`radial_layer_centres`**: it returns layer
  mid-heights, never centroid radii. The mesh is faceted, so the wall-normal
  distance is to the CHORD — the trapezoid centroid predicts 1.0023948e-2
  against a measured 1.002395e-2, while the layer mid-height is 1.0031658e-2.
  Reading it as a radius is what made a correct `first_cell_height` look broken.

## [0.96.0] — 2026-08-10 — EMStudio can finally SOLVE something with OpenFOAM

### Added
* **`emstudio/solvers/openfoam/` — the first OpenFOAM solve path.** Until now
  EMStudio could find OpenFOAM, install it and health-check it, but there was
  no `emstudio/solvers/openfoam` at all: the README's "conjugate heat /
  enclosure airflow" described the *installer*, not a capability. The first
  slice is the **differentially-heated square cavity** — buoyancy-driven flow
  in a closed box, which is the reduced form of the question an RF enclosure
  actually poses. `writer.py` emits the case, `runner.py` drives
  blockMesh → checkMesh → buoyantBoussinesqSimpleFoam through whichever
  install discovery resolved (native Windows / WSL2 / POSIX), `parser.py`
  reads the field back and returns a wall-averaged Nusselt number.
* **Physical properties are DERIVED from (Ra, Pr), not typed.** Ra and Pr fix
  the flow; `nu` and `alpha` are solved for exactly, and `ra_written`
  recomputes Ra from the numbers actually emitted so the round trip is
  assertable. Hand-tuning is how a case ends up quietly at Ra 9.4e4 while the
  report says 1e5.
* **The result path uses no function objects.** A `wallHeatFlux` function
  object would be the obvious route and is the one that aborts on Ubuntu's
  1912 build with `error in IOstream "sha1"` — the failure the capability
  probe exists to catch. Reading the written `T` field needs none of that
  machinery, so the result cannot inherit the fault.

### Testing
New `openfoam_cavity` gate (SOLVER tier, requirement declared in
`SOLVER_REQS` so a box without OpenFOAM **skips honestly** instead of
self-passing). 36 checks: the Ra round trip, rejection of Ra/Pr ≤ 0, a
truncated field caught by its own count, an unsolved `uniform` field treated
as an error rather than a reading, and the ESI-flavour dictionaries.

Its anchors are deliberately **not** literature values. The obvious reference
is de Vahl Davis (1983), and those numbers could not be verified from a
primary or open source while this was written — only that the benchmark
exists. This repo already carries the scar of the alternative: `foam_run.py`
once hard-coded "v2212+ restores function objects" as a release boundary, and
the note beside it now reads *"the number was plausible and invented."* So the
gate anchors on things needing no citation — **the conduction limit is exact**
(Nu is normalised by the pure-conduction solution, so Ra → 0 gives 1 by
construction), **energy conservation** (hot-wall and cold-wall Nusselt numbers
are the same number measured at opposite ends), and **monotonicity in Ra**.
⚠ OWED: add the published Nu comparison once someone has the paper.

Live on a native Windows v2512 install: Ra 100 → Nu 1.0022 (conduction limit
recovered), Ra 1e4 → 2.2459, Ra 1e5 → 4.6053, wall-to-wall imbalance below
2e-4 throughout.

## [0.95.1] — 2026-08-10 — the MS-MPI backup is finally read back

### Fixed
* **`pstream_repair()` wrote a backup that nothing ever restored**, so
  installing MS-MPI after EMStudio installed OpenFOAM left the machine
  silently serial while the UI said parallel had been restored. Found on a
  work machine while verifying the native tier: `emstudio-backup-msmpi`
  appeared in exactly two places in the whole tree — the line that creates it
  and a gate asserting it exists. Three faults compounded:
  the function had no reverse swap at all (with MS-MPI present it returned
  `msmpi-present` and did nothing); its only production caller was
  `run_windows_native_install`, so **Re-detect never reached it**; and both
  the user-facing note and the docstring promised the opposite. The only
  route back to parallel was a 200 MB reinstall.

  `pstream_repair()` now restores the parallel build when MS-MPI is present
  and the serial dummy is active (`restored-msmpi`), and `find_openfoam()`
  calls it for native installs *before* probing — the same ordering rule the
  installer follows — so Re-detect is now the documented, working route.
  `OpenFoamInfo.pstream` carries the outcome.

### Testing
The old gate could not see this: it overwrote the active DLL with the msmpi
bytes and *then* asserted nothing changed, setting up the already-correct
state. It now tests MS-MPI-present-with-the-dummy-active — what a machine
actually looks like after the user installs MS-MPI. **4/4 mutations caught**
(restore deleted, restore copies the dummy, restore silent, restore not
idempotent). Verified live on a company-controlled Windows box: dummy →
parallel build via `clear_cache()` + `find_openfoam()`, then a real
`mpiexec -n 2 simpleFoam -parallel` run — `nProcs : 2`, 20 timesteps, exit 0.

Also verified there, closing the native tier's open question: AppLocker
allows the unsigned ESI installer, `%LOCALAPPDATA%` execution is permitted,
and the download needs no TLS workaround on that network. Note for any future
parallel driving: `mpiexec` is **not** on the shipped MSYS2 shell's PATH and
`MSMPI_BIN`/`MSMPI_ROOT` are empty there, so it must be resolved absolutely.
EMStudio drives OpenFOAM serially today, so nothing in the product depends on
this yet.

## [0.95.0] — 2026-08-08 — the native Windows tier: the installer that existed all along

### Added
* **OpenFOAM on Windows now installs natively — no elevation at all.** ESI
  publishes a cross-compiled Windows build after all; we had concluded it did
  not exist because their wiki advertises an **unversioned** filename that has
  404'd for years (reported upstream four times before ours,
  openfoam/core/openfoam#3593). The real artifacts are versioned:
  `/source/v2512/OpenFOAM-v2512-windows-mingw.exe`. Measured end-to-end on a
  Windows box: `/S /D=` installs silently, per-user, exit 0, no UAC (the
  manifest is `asInvoker`), it ships all five required tools **and its own
  MSYS2 bash**, and the capability probe passes (blockMesh 0, function
  objects 0). It is now the **preferred** Windows route; WSL2 remains the
  fallback for what it cannot do — parallel runs and runtime-compiled code
  (EMStudio's own cases use neither).
* **`pstream_repair()` — the fix for a trap that makes every solver die
  silently.** ESI's installer ships `libPstream.dll` in MPI and dummy
  flavours and is meant to choose between them by whether it can also
  install MS-MPI (which needs admin). A **silent** install skips that choice
  and leaves the MPI build active with no `msmpi.dll` on the machine, so
  every solver exits `0xC0000135` (STATUS_DLL_NOT_FOUND) with no message —
  and `ldd` calls the closure fully resolved, because it never inspects
  libPstream's own imports. EMStudio now detects this and swaps in the
  serial build, keeping the MPI one as a backup. *(That backup was never
  read back — "installing MS-MPI later restores parallel" was not true
  until 0.95.1; see below.)* Proven by negative control, then gated (13 checks,
  4 mutations caught).

## [0.94.0] — 2026-08-07 — the Currents tab scrubs too, and no more console flashes

### Added
* **The Current Distribution scrubs with everything else.** AJ's follow-up to
  the v0.93.1 fix: four tabs moved with the frequency slider and one silently
  stayed put — quietly showing a *different* frequency than the scrubbed
  plots. The per-frequency currents were already in the same one-run output
  as the per-frequency patterns; `parse_currents_all()` now returns them all
  (each block scaled by its own wavelength, sorted by frequency), the runner
  carries `result.currents_all`, and the Currents tab registers as a third
  scrub view — combo + slider, synced through the shared selection. Watching
  the helix's distribution morph from a uniform loop current at 10 MHz to
  three counter-phased lobes through resonance is the physics lesson the
  static tab was hiding.
* **The 3-D wire-currents overlay live-follows the scrub** exactly like the
  balloon (same VTU-rewrite mechanism, same trailing-edge coalescing), and
  the floating viewport scrubber carries BOTH after the dialog closes.

### Fixed
* **No more black console windows flashing over the viewport.** FreeCAD.exe
  is a GUI-subsystem process, so every console-subsystem child it spawned —
  nec2++, ElmerSolver, gmsh, `wsl`, every version probe — opened its own
  console window. One NEC2 solve flashed three. All **17 spawn sites** now
  pass `creationflags=procutil.CREATE_NO_WINDOW` (a constant that is 0 off
  Windows, so nothing branches); a smoke check statically sweeps every
  `subprocess.*` call in the package so a future spawn cannot regress it.

### Testing
Gate: parse_currents_all checks including a **descending-block fixture**
(a sort-dropping mutation survived the ascending one — a check that cannot
fail is not a check) and live: 11 entries, same wire to 0.2 mm, peak |I|
sweeping 3.7 → 13.7 → 3.5 mA/V through resonance. **5/5 parser mutations
caught**; the no-console smoke check mutation-verified; gui_smoke asserts
three synced scrub views and the currents/farfield selection coupling.

## [0.93.1] — 2026-08-07 — the Wire currents overlay is coil-sized again

### Fixed
* **"Wire currents" drew a miniature of the antenna on multi-frequency
  pattern runs** — found from a user screenshot: a 300 mm helix with a 44 mm
  currents overlay. NEC-2's CURRENTS AND LOCATION table lists coordinates
  **in wavelengths**; `parse_currents` read the FIRST table in the file (the
  band-START frequency) and scaled it with the CALLER'S wavelength (the best
  match). On the single-frequency decks it was written for those coincide; on
  the multi-frequency deck the v0.92 pre-run dialog made the default, they do
  not — a 10–100 MHz sweep drew the coil at λ(67.6 MHz)/λ(10 MHz) = **1/6.8
  scale**, and — the worse half — the |I| values shown were the **10 MHz
  distribution under a best-match label**. `parse_currents` now collects every
  currents table with the frequency header that precedes it (the same
  discriminator the pattern splitter uses), picks the block **nearest the
  requested frequency**, and scales with **that block's own wavelength**; the
  returned `freq` is the block's actual frequency, so the tab title, the
  viewport label and the data finally agree. Single-frequency files have one
  block — behaviour identical, frozen gates untouched.
* **gui_smoke's Solver Setup check was platform-blind**: it asserted "no
  Install… button" on the real platform path, which is only the correct claim
  OFF Windows. On a real Windows box with a missing installable backend (this
  one: OpenFOAM absent, WSL2 blocked) the dialog *correctly* offers Install…
  and the check called that a failure. Green on Linux, macOS and a
  fully-provisioned VM never covered it. Now conditional on `os.name`; the
  Windows behaviours stay pinned by the simulated-Windows branch.

### Testing
`pattern_sweep.py` +9 checks (a two-block currents fixture in each block's own
wavelengths — same trap-pinning shape as the pattern `_TWO_BLOCK` — plus live
checks that the multi-run currents match the single-run geometry to 0.1 mm and
carry the best-match block's frequency); **4/4 mutations caught** (first-block
regression, caller's-lambda regression, wrong label, unterminated table).
Verified against real output both ways: the v0.90 single-frequency file parses
byte-identically, and yesterday's 91-block file returns the full-size helix at
every requested frequency.

## [0.93.0] — 2026-08-06 — scrub the band: sliders, frequency cursors, and a scrubber on the viewport

### Added
* **A scrub slider on both pattern tabs.** Drag through the solved
  frequencies and the 2-D cut, the 3-D matplotlib balloon and the FreeCAD
  viewport balloon all change in real time. Balloon rewrites are coalesced
  (~16 fps, trailing edge guaranteed) so dragging stays smooth.
* **Frequency cursors on the sweep plots.** S-Parameters, VSWR and
  Impedance each carry a vertical cursor with intersection markers and a
  live readout (S11 dB / VSWR:1 / R + X Ω), interpolated at the exact
  selected frequency — the whole dialog moves as one as you slide.
* **A floating scrubber on the 3-D viewport.** "Show in 3D View" now spawns
  a small slider window over the view itself. While the results dialog is
  open it drives everything (tabs, cursors, balloon); after the dialog
  closes it keeps scrubbing the balloon on its own, and it closes itself if
  the balloon is deleted. One at a time — a new Show in 3D View replaces it.
### Changed
* **Sweep-results dialogs are now NON-MODAL and really close.** The
  three-lens adversarial review of this feature found the modal `exec()`
  callers broke it structurally: the floating scrubber was input-blocked
  while the dialog was open, and closing a parented dialog only HID it —
  post-close scrubs drove the hidden dialog, lazily building up to two
  matplotlib figures per visited frequency in a window the user believed
  gone, and the scrubber's dead-dialog/solo path was unreachable.
  `show_sweep_results()` (non-modal + WA_DeleteOnClose) fixes all of it,
  and you can now rotate the 3-D view while the plots are up.
* **Scrub costs are trailing-edge only.** Dragging across 201 frequencies
  used to build (and cache forever) a polar + 3-D figure pair for every
  index the thumb crossed — multi-second freezes. Figure builds now ride
  the same 60 ms coalescing as the balloon; only dwelled-on indices build.
* **The frequency cursor refuses to lie out of band.** A pattern band may
  exceed the S11 sweep; `np.interp` would clamp and print the band-edge
  value under the wrong frequency on three plots at once. Outside the sweep
  (or on a one-point sweep) the readout now says so instead.

  Verified: gui_smoke drives sliders, combos, cursors, balloon and scrubber
  end-to-end — including the real non-modal close path (the review showed
  the old test exercised a wiring production never creates) — green 3×
  consecutively on 0.21.2 (a fixed-budget event spin was ~50% flaky there;
  waits are now condition-based with deferred-delete pumping) and on 1.1.1;
  8 mutations caught; 9 review findings confirmed, all fixed.

## [0.92.0] — 2026-08-06 — OpenFOAM on three OSes, and the pattern choice that rides the Run click

### Fixed
* **"I click OK and nothing happens" in Pattern Frequencies.** On a solver
  object predating v0.91.0's properties (possible in mixed-install sessions,
  e.g. an Add-on-Manager copy updating underneath an open document), storing
  the choice raised `AttributeError` *after* the dialog closed and *before*
  any confirmation — invisible outside the Report view. Both entrances now
  re-run the proxy's idempotent property migration on the live object first,
  and any failure past OK is SHOWN, never swallowed. Reproduced against a
  stripped solver before fixing; gui_smoke pins the heal and both call
  sites (2 mutations caught).

### Added
* **OpenFOAM joins Solver Setup — discovery that answers the right questions,
  and a guided install on all three platforms.** OpenFOAM is a suite behind a
  sourced environment, two forks share its name, and one widely-installed
  distro build is broken at runtime — so `emstudio/setup/openfoam.py` reports
  WHERE an install is (its `etc/bashrc`), WHICH fork/version it is (ESI
  required; a Foundation install is reported, never offered), whether the
  five required tools are present, and whether its **function objects
  actually work** — a ~1 s runtime probe (1-cell blockMesh + one function
  object), not a version floor. Ubuntu's own `openfoam` 1912 package fails
  that probe with `error in IOstream "sha1"` (a packaging defect, measured);
  Solver Setup now says exactly that instead of a bare MISSING.
  Guided routes, each verified against the live source on 2026-08-06:
  Linux = OpenCFD's repo script + `openfoam2512-default` (the newest FINAL
  release in their repo; v2606 is still rc2 there); macOS = the community
  OpenFOAM.app via `brew install gerlero/openfoam/openfoam` (ESI fork only,
  Apple-silicon, verified usable end-to-end on the M1 host); Windows = an
  Install button that creates **EMStudio's own WSL2 distro**
  (`EMStudio-OpenFOAM`, SHA256-pinned Ubuntu rootfs, no Microsoft Store) and
  installs the ESI packages inside it — per-user except the one honest
  Administrator step (enabling WSL2), which the button explains instead of
  failing. Gate: `openfoam_setup` (FAST), 8 engine + 3 GUI mutations caught.
* **The Pattern Frequencies choice now rides the Run Solver click.** Pressing
  Run on a NEC2 solver with a real sweep pops the dialog pre-filled — on a
  fresh solver the recommendation arrives LIVE (band, step, count) and OK
  reads **Run Solver** — so the scrollable per-frequency patterns are one
  keypress away instead of parked in a menu nobody finds. A checkbox mutes
  the pop-up; Analysis ▸ Pattern Frequencies… re-enables it.
* **The 3-D pattern balloon follows the frequency picker live.** Once "Show
  in 3D View" has placed a balloon, scrolling the picker rewrites and
  re-reads it in place — same object, new pattern and label — instead of
  needing another button press per frequency.

### Changed
* **Elmer's Windows Install button now downloads the release-pinned
  `rel26.1` zip** instead of the rolling "current build" name. CSC abandoned
  the funet nightly on 2026-08-05 (their `NIGTLY_BUILD_IS_BROKEN.txt`, citing
  our #858: the nightlies had again shipped without the MinGW runtime DLLs);
  the pinned zip was downloaded and inspected before switching — 296 DLLs in
  `bin/`, every runtime DLL present. The MSYS2 completion fallback stays.

## [0.91.0] — 2026-08-06 — the picker you can find, and a plot that draws its data

Everything here came from one user session on a real model — a 300 mm solid
helix swept 10–100 MHz. Two of the four defects were **invisible failures**:
correct data that the UI declined to show.

### Fixed
* **The VSWR tab drew nothing when nothing matched.** `_plot_vswr` clamped the
  axes to `ylim(1, 10)` unconditionally. The helix's minimum VSWR is **411**, so
  all 51 points sat ~40× above the ceiling and the tab rendered an empty grid on
  a run whose data was present and correct throughout. It now keeps the familiar
  linear 1–10 view (with the 2:1 acceptance line) when the curve fits, and
  switches to a **log axis with the minimum annotated** when it does not. A
  one-point sweep now gets a marker — with a bare line style it drew nothing at
  all, for want of a second vertex.
* **"Show in 3D View" ignored the frequency picker.** It read
  `result.farfield`, which is pinned to the best match, so scrolling to another
  frequency and pressing the button added a balloon for a *different* frequency
  — carrying the right frequency in its own label, so nothing looked wrong. Both
  pattern tabs and the 3-D export now share **one** selection. The wire-currents
  overlay is labelled with its own frequency, since currents are still solved
  only at resonance.
* **Polyline wires were segmented past NEC-2's thin-wire limit.** `Antenna from
  Selection` builds its wire with `Part.makePolygon`, so a curve arrives as N
  *straight* edges and every one of them took the 3-segment floor meant for a
  lone straight radiator — the `min_seg = 1` branch written to protect the
  segment-length-to-radius ratio only ever fired for genuinely curved edges.
  Measured on the helix: 240 segments of 25 mm on a 9.49 mm radius, **d/a =
  2.63** against Burke & Poggio's ≳ 8. A polyline link is now treated as the
  chord it is, and segment counts are capped at `THIN_WIRE_MIN_SEG_RADII`. The
  same model is now 80 segments at **d/a = 7.90**.
* **A single-pattern result now says why there is no picker**, and names the
  command that turns it on.

### Added
* **Pattern Frequencies… (Analysis group)** — the dialog this needed from the
  start. `PatternFrequencies` shipped in 0.90.0 as a solver property with no UI,
  and a user who wanted a swept pattern could not find it. The dialog offers the
  analysis sweep as the band, lets both ends be edited, **recommends a step**,
  and lets that be edited too.
* **`SolverNEC2.PatternFreqStart` / `PatternFreqStop`** — the pattern band. Both
  default to 0 = *follow the analysis sweep*, so every pre-0.91 document is
  unchanged. Inverted or half-entered pairs fall back to the sweep rather than
  erroring; two numbers in a property editor are half-finished most of the time
  they are read.
* **`emstudio/solvers/nec2/pattern_band.py`** — Qt-free and FreeCAD-free, shared
  by the runner, the dialog and the gate.
* **`writer.thin_wire_report()`** and a thin-wire warning under the results
  plots. NEC-2 returns a number whether or not its kernel applies, and says
  nothing either way; the run now tells you which side of the line it is on.

### Measured
The recommender prefers a step that is an **integer multiple of the sweep step**
so every pattern frequency coincides with a point the S11 curve was actually
sampled at — otherwise the picker shows a pattern at 63.4 MHz while the nearest
S11 datum is 62.2, a mismatch nothing on screen reveals. On 10–100 MHz / 51
points that gives **11 patterns, 9 MHz apart, landing exactly on 100 MHz**.

The helix's ~0.12 Ω feed resistance was checked for numerical origin and is
**converged physics, not an artifact**: across d/a = 7.9 / 2.6 / 1.6 / 0.9 it
moved 0.1246 → 0.1239 Ω, and the extended thin-wire kernel (`EK`) shifted it by
0.1 %. The current distribution shows two phase reversals along a 1.35 λ wire —
three counter-phased lobes on a 0.045 λ-tall helix, which is why the radiation
resistance collapses.

### Testing
`tests/validation/pattern_sweep.py` grew from 21 to 54 checks, including a live
72-chord polyline deck that asserts the thin-wire guideline is met and that the
`EX` card still names a segment that exists — lowering a fed wire's count can
otherwise point the source past the end of it, and nec2++ then writes an output
file with zero frequency blocks and exits 0. **11/11 FAST-tier and 5/5 GUI-tier
mutations caught**; gui_smoke gained three checks (picker/3-D coupling, the VSWR
autoscale, and the new dialog's round-trip). One GUI mutation survived the first
round, and the reason was a real bug, not a weak check: `recommend()` derived
its grid from the band it was handed, so narrowing the pattern band silently
broke the lands-on-sweep-points guarantee. It now takes the sweep step as an
explicit argument.

## [0.90.0] — 2026-08-06 — a pattern at every frequency you swept

A solve produced exactly ONE radiation pattern, at the best-match frequency,
so there was nothing to scroll through. The cost of changing that was
mis-estimated at first as "one extra deck run per frequency" — wrong, and the
measurement is what made this worth building.

### Added
* **`SolverNEC2.PatternFrequencies`** — how many patterns to compute across the
  sweep. **0 (default) = one at the best match**, exactly as before, so every
  existing document is unchanged. Set 11 and the results dialog grows a
  **frequency picker** on both the Pattern and Pattern 3D tabs.
* **`result.farfields`** — the per-frequency set. `result.farfield` still holds
  the single best-match pattern, so the 2-D cuts, the 3-D balloon, the PDF
  report and gui_smoke are all untouched.
* `parse_radiation_patterns_all()` — splits a multi-frequency output on the
  frequency marker.

### Measured
NEC2 runs the `RP` card at **every step of the `FR` card**, so N patterns cost
**one run, not N**: 201 points produced 201 pattern blocks in **7.18 s**. On the
shipped dipole, `PatternFrequencies = 11` took 1.01 s against 0.52 s for the
default and gave 11 patterns from 200–400 MHz with peak gain rising
1.92 → 2.50 dBi — a fixed-length dipole growing more directive with frequency,
which is physics rather than an artifact.

The real cost is **output**: ~0.33 MB per frequency, 65.4 MB at 201 points.
That is why this is a count the user chooses rather than "always all of them".

### The trap this had to avoid
`parse_radiation_patterns()` pours every sample it finds into ONE theta/phi
grid. Run it on a multi-frequency file and each frequency silently overwrites
the last, returning a perfectly plausible pattern that belongs to no frequency
at all — no error, no warning. The gate pins that difference explicitly.

### Testing
`tests/validation/pattern_sweep.py` — 21 checks, **7/7 mutations caught**, plus
a gui_smoke check that builds the picker under a real Qt and asserts it opens
on the best-match frequency. One mutation exposed a substring check in the gate
that a commented-out constructor still satisfied.

## [0.89.0] — 2026-08-06 — the progress bar tells you where you are

The determinate bar with ETA has existed since v0.88.0. It was wired to exactly
ONE caller and **none of the four solver runners**, so every real solve still
showed the indeterminate bar that says nothing except "not hung". Nothing
failed; the feature was simply never connected, and no test could tell.

### Added
* **Every solver now reports real progress**, and the dialog states all four
  things: **percent done, percent to go, elapsed time, and an ETA** —
  `42% done · 58% to go · elapsed 30 s · about 40 s left`. The ETA is withheld
  until there is evidence for it (3 s and 5 % done) because an extrapolation
  from 1 % swings wildly and teaches users to ignore the field; elapsed is a
  measured fact and is always shown.
* `emstudio/solvers/progress.py` — one shared reporter. Everything is callable
  and forwards lines unchanged, so it drops into any `line_callback` slot
  invisibly, and every path is best-effort: a callback without `.progress`, an
  unrecognised dialect, or a missing denominator leaves the bar exactly as it
  was. **Progress reporting can never fail a solve.**

### How each backend is driven, and why they differ
* **NEC2 — polled from its OUTPUT FILE.** Measured: nec2++ writes **0 bytes to
  stdout and stderr**; everything goes to the `-o` file, so a line callback can
  never see progress. That file IS written incrementally (marker counts climbed
  9, 19, 30, 41 … during a 4.9 s run), so it is polled instead. NEC2 needs it —
  cost is ~cubic in segment count: a dipole takes 0.25 s, 6 wires × 151
  segments took **104.75 s**. A real Yagi reported 18.8 → 39.4 → 59.1 → 78.4 →
  90 (pattern) → 100 %.
* **Elmer sweep — counts the cases WE orchestrate**, under a lock, because the
  thread pool completes them out of order. No parsing, so no upstream wording
  can break it. Measured on 4 concurrent cases: 5 → 28.75 → 52.5 → 76.25 →
  100 %, with all 2 461 log lines still forwarded.
* **Elmer 3-D — phase weights, MEASURED not guessed.** On the analytic ring:
  gmsh 7.1 s (13 %), ElmerGrid 1.2 s (2 %), ElmerSolver 46.7 s (**85 %**). A
  first cut gave meshing 43 % of the bar for 13 % of the time, which raced to
  45 % then crawled — a worse ETA than none.
* **openEMS — its own timestep counter**, with the total LEARNED from a line
  our generated deck already prints (`NrTS=`), so the runner never duplicates
  the writer's `max(1000, int(solver.MaxTimesteps))`. Not verifiable on the box
  this was written on; if the wording does not match, nothing is reported and
  behaviour is exactly as today.
* **Palace — phase boundaries only.** Not installed here, so any regex against
  its output would be a guess.

### Fixed
* **A gate's verdict could depend on which SHELL launched the battery.** Gates
  print arrows and `±`; a child inheriting a cp1252 console dies with
  `'charmap' codec can't encode character '→'`, which reads exactly like a
  physics failure. Measured: `element_designer` PASSED from PowerShell and
  FAILED from Git Bash **at the same commit**. `run_battery` now forces UTF-8
  on the child, and smoke pins it.
* The file watcher lost the final marker at EOF (a 201-point sweep stopped
  reporting at 200) — the carry-over held back to survive a split read was
  never flushed. Caught by the gate asserting the fraction reaches exactly 1.0.

### Testing
`tests/validation/solver_progress.py` — 30 checks, **7/7 mutations caught**.
Two mutations exposed real weaknesses in the gate itself: a wiring check that
grepped for `progress.report` anywhere still passed with the in-loop call
deleted, and a NEC2 marker mutated to count the `--------- FREQUENCY --------`
banner survived because doubling the count merely clamps the bar at 1.0 early —
still monotonic, still "reaches 100 %". The marker is now a named constant the
gate tests behaviourally rather than a copy that could drift.

## [0.88.1] — 2026-08-05 — the real cause: a PartDesign Origin is 2e100 mm across

v0.88.0 blamed a feedback loop between successive overlays. **That was wrong.**
The user's own object list showed it:

    MODEL X-axis     2.0e100 x 0.0 x 0.0
    MODEL XY-plane   2.0e100 x 2.0e100 x 0.0

A **PartDesign Body brings an Origin** whose X/Y/Z axes and XY/XZ/YZ planes are
INFINITE shapes; FreeCAD reports bounding boxes of ~2e100 mm and they pass
`isValid()`. `geometry_extent_mm` measured them as geometry, so the balloon was
written with coordinates of 1.99e+100 — outside the Float32 the VTU uses, read
back as infinity, overlay in the tree drawing nothing.

**Every earlier reproduction used a plain `Part::Feature`, which has no
Origin** — which is precisely why none of them reproduced it, and why three
diagnoses in a row were wrong.

### Fixed
- Datum/construction shapes are rejected **per object** (any bbox dimension
  over 1 km is not a model). v0.88.0 rejected the whole *measurement* when it
  looked absurd, which fell back to the fixed 100 mm default and drew a
  **200 mm balloon around a 325 mm coil** — undersized, and still wrong.
  With the real object list the extent is now 325 mm and the balloon 650 mm.
- **The balloon centres on the antenna that produced the result**, via the
  analysis' own material/port references, instead of the bounding box of every
  object in the document. A second analysis or a leftover body previously moved
  the pattern off its own radiator. The result meta carries the analysis
  *label*, not the object, so it is resolved through the document — reading it
  directly would have silently fallen back to whole-document behaviour and
  looked like it worked.

### Note on what the balloon means
Gain is dimensionless: a far-field pattern has **no size in mm**, and every EM
tool draws it at an arbitrary scale. The SHAPE is the true normalized pattern
(radius linear in dB above a −30 dB floor, peak at full radius) and the
**colour scalar is real `Gain_dBi`**. The overall diameter is a drawing
convention — now one that clears the geometry instead of hiding inside it.


## [0.88.0] — 2026-08-05 — the 3-D pattern sized itself from its own last overlay

*"When I add the 3D pattern to the model it is not shown, even if I change what
to show."* It worked at the office and not at home, which made it look like a
FreeCAD or driver problem. It was neither.

### Fixed
- **The pattern balloon compounded on every click until it left Float32.**
  `geometry_extent_mm` walked EVERY object in the document — including the
  pattern balloons it had itself created — and a balloon is deliberately
  *bigger* than the geometry. So each "Show in 3D View" sized the new balloon
  from the previous one. The user's own `pattern3d.vtu` on disk had every
  coordinate at **1.99e+100 mm**: VTK reads that as infinity, so the overlay
  loaded with **no field (`choices ['None']`) and the FLT_MAX sentinel bounding
  box** — present in the tree, drawing nothing. **It works the FIRST time and
  degrades on every click after**, which is exactly what made it look
  intermittent and version-dependent. Result overlays are now excluded from the
  measurement, and both `geometry_extent_mm` and `auto_radius_mm` refuse a
  non-finite or absurd extent rather than writing coordinates that read back as
  infinity. Verified by clicking five times: radius identical each time.
- **A degenerate far field silently produced an empty overlay.** A single theta
  row yields points and ZERO cells, which loads without error and draws
  nothing. `write_pattern_vtu` now refuses a grid below 2×2 and the results
  dialog explains it instead of leaving a dead object; the gate only ever
  checked `phi`, never `theta`.
- **A single NaN gain wrote NaN COORDINATES into the file** — the same silent
  nothing. Non-finite samples now drop to the floor.
- The balloon is sized to **enclose** the model (radius = one full extent, was
  half) and drawn at 55% transparency, so it no longer shares the model's own
  volume.

### Added
- **Show Results** — reopen the last solve's results without re-solving. The
  dialog was previously reachable only from the run that produced it, so
  closing it meant paying for the whole solve again to reach the plots,
  Touchstone export, PDF report or Show in 3D View.

### Method note
Three wrong diagnoses preceded the right one (balloon size, FreeCAD version,
degenerate grid), each argued from code and object properties. The answer came
from the user's own console output and then from **reading the actual bytes of
the file on disk**. Object properties describe intent; the artefact is evidence.


## [0.87.0] — 2026-08-05 — "ERROR, ERROR, ERROR" is not an answer

A user drew a **solid helix coil**, attached a material, a lumped port on a
face and a NEC2 solver, pressed Run Solver, and got:

    port 'EMPort' must reference a wire edge for the NEC2 backend

Every step they took was reasonable. NEC2 simply cannot solve a body — it is a
thin-wire method: centre line plus radius. The workbench **already knew how to
derive exactly that from a solid**, so refusing was a choice, not a limitation.
Nothing on screen mentioned "Antenna from Selection", so from the outside the
tool just looked broken. Their words: *"If I was a new user I would quit and
de-install this crap."* Fair.

### Fixed
- **Run Solver now offers to fix it instead of refusing.** Before a NEC2 run
  it builds the wire model (cheap — the run does it first anyway). If that
  fails *and* the analysis references a solid, it explains the problem in
  plain language and offers **"Build the wire model and run (recommended)"**
  as the default button. Accepting derives the centreline and radius from the
  body, re-points the material and the feed at the derived wire, **keeps the
  user's solver, sweep and port impedance**, reports every change, and runs.
  Nothing they set up is discarded.
- **The error message itself now prescribes a cure.** It names the offending
  object, says *why* a solid cannot be used, and gives the concrete next
  action. It also detects the solid through a **face** reference by checking
  the parent shape — a port on `Face1` resolves to a Face, which has no
  `.Solids`, so testing only the resolved sub-shape missed the exact case the
  message exists for.
- The wrong-solver assist runs on this path too: if the repaired conductor is
  electrically thick, the openEMS recommendation appears here as well.

### Fixed (continued)
- **"Show in 3D View" drew the pattern balloon INSIDE the antenna.**
  `auto_radius_mm` used `fraction=0.5`, so the balloon's RADIUS was half the
  model's largest dimension — its **diameter exactly equalled the model's own
  size**. Drawn centred on the geometry, it therefore shared the same volume,
  and on a solid helix the coil wraps around it and hides it. Reported as
  *"when I add the 3D pattern to the model it is not shown, even if I change
  what to show"* — the object was there, visible, correctly coloured by
  `Gain_dBi`, and buried. The docstring had even recorded that the older fixed
  100 mm balloon "disappears inside its own antenna"; the fix only got halfway.
  The radius is now one full extent, so the balloon sits outside the geometry's
  bounding sphere, and the results dialog draws it at 55% transparency so it
  does not hide the model it describes. Gated at four model sizes.

### Gated
`antenna_from_selection` gains 12 checks reproducing that exact document —
solid helix, material, port on `Face1`, NEC2 — asserting the message is
actionable (names the object, says why, prescribes an action, is not a
one-liner) and that the repair produces a runnable model with a centre feed
(62 wires, feed index 31 of 62) whose radius came from the solid (6 mm), with
the user's own solver kept.


## [0.86.0] — 2026-08-05 — the workbench now tells you when you picked the wrong solver, and offers to fix it

### Added
- **Wrong-solver assist.** "Antenna from Selection" now checks whether the
  conductor is electrically thin enough for NEC2 **at the frequency it will
  actually be swept at**, and when it is not, says so in plain language and
  offers the fix as the **default button**: *Use openEMS (recommended)* /
  *Keep NEC2 anyway* / *Cancel*. Accepting builds the full-wave analysis on
  the **solid**, not on the derived centreline — modelling a filament in a
  full-wave solver would discard the very thickness that made NEC2 invalid.
  Mutation-tested 4/4, including a "cries wolf on every conductor" mutation:
  an assist that always fires is one users learn to click past.
- **Progress bars that carry information.** The dialogs were
  `QProgressDialog(…, 0, 0, …)` — indeterminate, so they said only "not hung".
  The worker's log callback is now a reporter that is *still callable* (all 24
  existing call sites unchanged) with a `.progress(done, total, note)` method.
  The centreline march reports against a real denominator — `volume /
  section_area` **is** the centreline length of a swept conductor, known
  before the march begins — so you get a true percentage plus a coarse ETA.
  The estimate is withheld until it would be meaningful rather than printing a
  jittering guess.

### Fixed
- **The thin-wire guard was dead.** It was evaluated inside
  `wire_extract.extract()` against `plan()`'s *optional* `freq_hz`, which the
  GUI command never passes — so it saw `None` and returned `None` every time,
  while the real sweep frequency (`f_res`, derived from the conductor length)
  was not computed until afterwards. A conductor of **any** thickness passed
  silently at its own half-wave resonance. Now evaluated after `f_res` is known.
- **`antenna_from_selection` had never passed.** It unpacked
  `build_wire_model()` (single-excitation: `wires, feed_INDEX, sweep`) using
  `build_wire_model_multi`'s signature and called `len()` on an int, raising
  `TypeError` before its first assertion. It is SOLVER tier and the work box
  runs FAST, so nobody had run it. The gate for v0.84.0's headline feature.
- **Four openEMS gates reported PASSED when they SKIPPED.** They printed the
  pass banner and returned 0 on the no-openEMS path, so on a box without
  openEMS they reported success while testing nothing — and because
  `freecadcmd` drops `print()` on exit, the exit code was the only signal a
  caller ever saw. Skipping is now the battery's job (`SOLVER_REQS` declares
  `openems_python`); running one by hand fails loudly, because you asked for it.
- **Elmer's guided Windows install fired an unnecessary MSYS2 download.** CSC
  refreshed the funet build on 2026-08-05 (~160 MB → 219 MB) and it now ships
  its runtime DLLs, closing
  [#858](https://github.com/ElmerCSC/elmerfem/issues/858). Our `runtime_dlls`
  VERIFY list still named `libgomp-1.dll` — correct only for MSYS2's OpenMP
  OpenBLAS, not CSC's — so it was permanently "missing" and triggered the
  completion step on every install of an already-complete tree, which would
  hard-fail on any box whose `tar.exe` cannot read zstd. **A VERIFY list must
  describe what the binary actually imports, or it stops being a check and
  becomes a trigger.** Verified end to end on a Windows VM.

### Changed
- `team7_elmer` `NORM_TOL` 2e-4 → **2e-3**, with the mesher named in any
  failure. The pins are **gmsh-version-locked**: measured on two boxes
  2026-08-05, gmsh 4.12.1 reproduces them bit-for-bit while 4.15.2 drifts
  +0.082 % / +0.112 %, so the old tolerance reported RED on a healthy tree.
  2e-3 is ~1.8× the observed drift and still ~50× tighter than the measured
  physics gate beside it. The same sensitivity appears in `open_coil_elmer`
  (split ring −0.79 % vs −1.49 % across the same two boxes), so **a sub-1 %
  FEM number is not portable across gmsh minor versions**.

## [0.85.0] — 2026-08-05 — a conductor may now have two ends

Until now every coil in the Elmer 3-D path was declared closed, because the
writer hard-coded `Coil Closed = Logical True`. Elmer trusts that declaration —
it prints "Assuming that all coils are closed!" and believes it — so a
conductor with free ends was solved against a false premise. There was no way
to express one at all.

### Added
* **True open-coil support.** `EMCoil` gains **`Closed`** (default True, so
  every existing document and frozen deck is byte-identical) plus optional
  `StartFace`/`EndFace`. Untick it and the two terminal faces are found
  automatically, tagged through gmsh as named boundaries, and driven with
  Elmer's `Coil Start` / `Coil End` Dirichlet conditions.
  **Validated against an exact closed form**: a 324° split ring (R = 100 mm,
  4×4 mm section, 1000 A) lands **−0.79 %** from Biot-Savart's
  `B = µ0·I·φ/(4πR)`, and delivers **99.98 %** of the requested current.
  On the real user helix the field lands **−0.72 %** from the
  finite-solenoid closed form.
  The chosen faces are always REPORTED, never picked silently.
* **`gmsh_3d` partial tubes** — `angle_deg` on a `tube` gives a split ring, the
  canonical open conductor. The geo now ASSERTS that each terminal bounding box
  selects exactly one surface and aborts if not: selecting none would emit an
  empty group and selecting two would drive the wrong face, and either way the
  solve would run and return a plausible wrong number.
* **A geometric-turns measurement, and a double-count warning.** The two Elmer
  branches mean different things by `Desired Coil Current` — the closed one
  normalizes over a half-plane (which counts the turns itself), the open one
  over ONE conductor cross-section (so the solid's own winding multiplies in).
  Measured: 100 A requested on the open branch through a 6.44-turn helix
  delivers ~644 ampere-turns, **6.39× above** what the same request means
  closed. EMStudio now measures that winding count and says so, and warns when
  `Turns > 1` would multiply it a second time.

### Fixed
* **`MeshSizeBodies` defaulted from the bounding box** — ~22 mm on the user's
  helix, COARSER than the 20 mm conductor it was meshing. It now sizes from the
  body's own smallest feature (2V/A = 9.22 mm there), putting ~2 elements
  across the conductor. It can only refine the old default, never coarsen it.
* **Four openEMS gates FAILED where they should have skipped.** Absence of an
  optional backend is not a defect. They now skip, the same correction the
  nec2c gates got in v0.83.0.
* **`find_openems_python` only knew the POSIX venv layout** (`venv/bin/python`),
  so a working Windows openEMS install could never be detected. It now probes
  `venv\Scripts\python.exe` too, and lives in the FreeCAD-free resolver so a
  gate can ask "is openEMS available?" without importing FreeCAD.
* **CoilSolver's own warnings were being discarded** — only "did not converge"
  was scanned for, so "Crappy potentials in coil 1" and "No negative current
  sources on coil 1 end!" (exactly what a mis-declared topology produces) never
  reached the user.
* **`elmer_env()` now sets `ELMER_Fortran_COMPILER`** on a Windows zip layout
  that ships its own compiler. This changes nothing that currently runs —
  EMStudio ships no Elmer user function — but it disarms a landmine before we
  can step on it: `elmerf90` has the BUILD HOST's compiler path baked in, so on
  any other machine it compiles nothing (measured: exit 127, no output). With
  the variable pointed at the `stripped_gfortran` the zip already ships, it
  builds a real `USE DefUtils` UDF (95 812-byte DLL, exit 0). A user's own
  setting always wins. Found via Juha Ruokolainen on
  [ElmerCSC/elmerfem#858](https://github.com/ElmerCSC/elmerfem/issues/858),
  who flagged the override as untested; we tested it.

### Measured, and deliberately NOT done
* **`Coil Cross Section` is not emitted.** It is a legal keyword and the
  obvious thing to reach for, and it is a silent-wrong-number generator: on the
  split ring, the correct area gave −0.77 %, **4× the area gave −75.19 %** —
  exactly a quarter, with no warning — and omitting it gave the same right
  answer, because Elmer derives the section correctly from the mesh. It also
  suppresses the average-current-density report the delivery guard runs on.
* **Testing.** `tests/validation/open_coil_elmer.py` — 38 checks, **10/10
  mutations caught**. Two of those mutations found real weaknesses in the gate
  itself (a substring `Abort;` check that a commented-out line still satisfied,
  and an unfalsifiable branch in the venv-layout probe).

### Also
* **`tests/run_pro_freecad.py`** — the Windows leg of the test harness. There
  was none, which is why `gui_smoke` went unrun from v0.80.0 to v0.84.0 while
  `commands.py` and `installer_dialog.py` changed underneath it. A PowerShell
  version was written first and is not viable: Cylance Script Control blocks
  `.ps1` execution outright on the work box. gui_smoke now passes on native
  Windows (32 checks, FreeCAD 1.0 and 1.1).

## [0.84.0] — 2026-08-05 — "Antenna from Selection", and openEMS says when it cannot

Driven by a real session: a user drew a coil, tried to simulate it, and hit a
different refusal at every step — "port must reference a wire edge" on a solid,
then "edge is not straight" on a curve. Each message named a symptom and not a
cure. The audience for this workbench is a hobbyist before it is an RF
engineer, so a tool that is correct but unusable is not correct enough.

### Added
- **"Antenna from Selection"** (Analysis group). Select the conductor — a
  SOLID or a curve — and get a runnable NEC2 analysis: wire model, PEC
  material, centre feed on the middle edge, a sweep centred on the conductor's
  own half-wave resonance, and the solver. It replaces four objects created in
  a specific order under a selection rule that was not discoverable (material
  wants the whole object; port wants a named EdgeN picked in the 3-D VIEW).
  A solid has its radius MEASURED from its cross-section; a curve is only a
  centre line and carries no thickness, so the radius is asked for.
- **It explains itself.** The confirmation states what was derived AND why:
  that NEC2 models a conductor by centre line plus radius because RF current
  is a surface effect and the far field cannot distinguish a polygonal bar
  from a round wire of equal section; how thin the conductor is against the
  wavelength (and a warning when it stops being thin); why the sweep sits
  where it does; and what S11, impedance and pattern each mean when the run
  finishes. Teaching the *why* is the point, not decoration.
- Gate `tests/validation/antenna_from_selection.py`: both source kinds end to
  end, the measured-vs-asked radius rule, the half-wave sweep, the centre-feed
  edge, that the NEC2 writer accepts what was built, and that the explanation
  actually contains its teaching.

### Fixed
- **`discretize(Deflection=...)` cannot be trusted, and v0.83.0 trusted it.**
  On a B-spline built by interpolation OCC ignores the request outright.
  MEASURED, budget 2.372 mm on a spline through a 150 mm helix:

      Deflection       108 pts   achieved 124.481 mm   (52x over; one 296 mm chord)
      QuasiDeflection  129 pts   achieved   1.868 mm
      Number=640       640 pts   achieved   0.076 mm

  while the same path as an ANALYTIC helix honours it (2.151 mm). 124 mm on a
  9.5 mm conductor puts the modelled wire thirteen radii outside the metal,
  silently. The writer now MEASURES the achieved deflection, retries by a
  method that holds, and raises rather than returning a path it cannot verify.
  Found by an adversarial design review, then reproduced independently before
  being believed.
- **openEMS: an STL body could be absent from the grid and still "simulate".**
  A non-box body got six grid lines (its bounding-box planes) and never
  reached `AddEdges2Grid` at all, because `has_solid` was set only in the box
  branch. Cells inside it were whatever the global wavelength rule gave. Now:
  the body's smallest feature is measured (`2*V/A` — a plate's thickness
  exactly, a rod's radius; a bounding box cannot see it, since a 6-turn helix
  bounds 320 mm and conducts 20 mm), affordable bodies get a local grid, and a
  body the grid cannot represent is REFUSED with its numbers and pointed at
  the NEC2 wire backend. The refusal is scoped to metal STL bodies —
  dielectrics already get explicit lines across a thin substrate, and thin
  metal is a zero-thickness sheet by design. An earlier, broader draft refused
  EMStudio's own validated 2.4 GHz patch template, which is why the scope is
  written down.
- The refinement budget counts CELLS (the product of per-axis line counts),
  not lines per axis: 121 lines/axis looks modest until it is multiplied into
  927k cells for one body.
- Gate `tests/validation/stl_mesh_openems.py`.

## [0.83.0] — 2026-08-05 — NEC2 solves CURVED wires

### Added
- **Automatic discretization of curved wire edges** — the "Phase-2 item" the
  writer had carried since it was written. A helix, loop or spiral drawn as a
  real curve was previously refused outright ("edge is not straight"), so the
  only route was hand-building a polyline. NEC2 has no curved primitive (a GW
  card *is* a straight wire), so a curve becomes chords.

  Chord density is set by a **deflection bound expressed in wire radii**, and
  the default was MEASURED rather than chosen. Against a loop whose radiation
  resistance is analytic (300 mm loop, 3 mm wire, 20 MHz):

      deflection    chords    R [ohm]    vs converged
        1.00 r        23       0.05713      -4.3 %
        0.25 r        45       0.05870      -1.7 %   <- shipped default
        0.02 r       158       0.05966       ref

  `CHORD_DEFLECTION_FRAC = 0.25` sits at the knee. Refinement moves
  monotonically away from the leading-order small-loop formula and then stops
  ~21 % above it — that gap is the formula's own idealization (uniform
  current, infinitely thin wire), not a discretization error, which is why
  the gate pins CONVERGENCE and uses the analytic value only as a sanity
  bound. Any chord still longer than lambda/10 is split.

  Cross-checked three independent ways on a 6 m helix: a hand-built 103-chord
  polyline resonated at 18.65 / 25.78 MHz, the solid extractor's 80-chord
  model at 18.89 / 25.4 MHz, and the same helix as a SMOOTH curve now at
  18.4 / 24.49 MHz — agreement to a few percent across three segmentation
  strategies.

- **The straight-wire path is untouched, deliberately.** A straight edge takes
  the original code path and emits the identical card, because the frozen
  dipole/monopole/yagi/lpda decks depend on it. Chords do NOT inherit the
  3-segment floor that gives a lone straight wire its centre segment: each
  chord already IS a straight wire, and thirding every chord would drive the
  segment-length-to-radius ratio under NEC2's thin-wire limit.

- The feed (and any transmission-line end) lands on the chord nearest the
  EDGE midpoint — where the excitation sat when a curved edge was one wire.
  A curve now contributes many wires under one key, so `_tl_cards` was
  indexing whichever chord came last; it now picks the centre chord.

- Gate `tests/validation/curved_wire_nec2.py` (SOLVER tier): the straight path
  is unchanged, chords carry no 3-segment floor, every chord midpoint lies
  within the deflection bound of the true curve, the feed placement rule, the
  chord count responds to the deflection setting, and the live loop solve.

### Fixed
- **Three Pro validation gates could not run on Windows at all**
  (`array_nec2`, `array_taper_nec2`, `rfdf_nec2`): each looked up the solver
  with a bare `shutil.which("nec2c")`, hard-coding one engine by name, while
  the supported Windows engine is nec2++ (since v0.77.8) and no nec2c build
  exists there. They now use EMStudio's own `find_backend("nec2")`, which
  honours the preference/env/PATH/managed-dir chain the product uses. All
  three pass on Windows for the first time.

## [0.82.0] — 2026-08-05 — draw a SOLID conductor, simulate it as an antenna

### Added
- **`emstudio/geometry/wire_extract.py` — thin-wire model from a 3-D solid.**
  Until now nothing converted a solid conductor into something NEC2 could
  solve: a user with a swept helix had to measure the centreline and pick an
  equivalent radius BY HAND (and the first hand attempt used the wrong
  cross-section, which is the argument for automating it).

  The centreline is recovered by **marching cross-sections** — step along the
  local tangent, cut with a plane normal to it, take the section centroid,
  update the tangent. The one rule that makes it work on a coil: a cutting
  plane crosses a multi-turn conductor MANY times, so the section returns
  several disjoint pieces, and only the piece NEAREST the previous station is
  correct. Taking the largest or the first walks onto a neighbouring turn and
  yields a confidently wrong path; a jump beyond a few steps terminates the
  march instead of guessing.

  Measured on a real 6.44-turn octagonal helix: centreline **6067 mm against
  the parametric truth of 6030 mm (+0.61 %)**, section area 282.78 vs
  282.843 mm^2 (**-0.02 %**), equivalent radius **9.487 vs 9.488 mm**. Driven
  straight into NEC2 the extracted model resonates at **18.89 / 25.4 MHz**
  against **18.65 / 25.78 MHz** for a hand-built 103-chord model.

- **Provenance, not a silent substitution.** `describe()` reports the method,
  the chord count, both independent reads of the cross-section (end caps and
  volume/length), and which equivalent-radius convention was used. When the
  two section reads disagree by >10 % the sweep is not uniform and one
  equivalent radius cannot represent it — the extractor says so.

- **The validity boundary is enforced, not assumed.** Thin-wire modelling of a
  solid is the ACCURATE method while the conductor is electrically thin (the
  helix is lambda/600 across at its resonance); it stops being true when the
  section approaches a fraction of a wavelength. `thin_wire_warning()` flags
  that case rather than returning a number that no longer means anything.

- **Refusals.** A CLOSED loop has no end caps to march from and is refused
  with that explanation, not approximated. A collapsed or non-terminating
  march raises rather than returning a partial path.

- Gate `tests/validation/wire_from_solid.py` (SOLVER tier): a straight rod and
  a swept helix against closed-form answers, the closed-loop refusal, the
  electrically-thick warning, resampling invariants, and that the provenance
  block is actually emitted.

## [0.81.0] — 2026-08-05 — 3-D coils: the winding axis, inductance, and a delivery guard

Found by a user driving a real 6.44-turn octagonal-conductor helix through the
3-D magnetostatic path and getting an axial field **160x below theory**, with
no warning of any kind.

### Fixed
- **The 3-D magnetostatic path hard-coded a +Z coil normal** (`model3d.py`),
  so any coil wound about X or Y handed Elmer's CoilSolver an axis
  perpendicular to the real one. The solver picks its current-fixing nodes
  from that vector, so the drive was wrong and nothing said so. **This was the
  dominant cause of the 160x error** — not the coil's open topology, which was
  the first hypothesis. `EMCoil` now carries an **`Axis`** property (+X/+Y/+Z,
  default +Z so every existing document and frozen deck is byte-identical).
  Measured on the user's helix: axial B went from 1.28e-5 T to **3.18e-4 T**,
  against **3.485e-4 T** from the finite-solenoid closed form — within 9 %,
  the residual being the mesh coarseness the writer already warns about.

### Added
- **Coil inductance for general 3-D coils** — the "planned slice" that
  `model3d.py` used to fill with a hard-coded `energy_j = 0.0`. The deck now
  asks `MagnetoDynamicsCalcFields` for `Calculate Field Energy` and the result
  carries `energy_j` plus `inductance_h` (L = 2W/I^2), reported in the
  magnetics summary. **Validated against the analytic circular-loop formula
  L = mu0*R*[ln(8R/a_gmd) - 2] at -1.75 %** (ring R = 100 mm, 4 x 4 mm
  section). The keyword matters: `Calculate Magnetic Field Energy` does NOT
  exist in Elmer and would have silently done nothing — the real name was
  taken from `share/elmersolver/lib/SOLVER.KEYWORDS` before emitting, per the
  never-name-a-keyword-from-memory rule.
- **Delivered-ampere-turns guard.** `Coil Closed = Logical True` is an
  assertion the deck makes on the user's behalf ("CoilSolver: Assuming that
  all coils are closed!"), so a mis-driven coil solves cleanly and lies. The
  deck now asks for `Calculate Coil Current`, and the result compares
  delivered against requested ampere-turns, warning outside 0.5-2.0x.
  Delivered is exact because it is measured across a half-plane through the
  winding axis, which every turn crosses exactly once. Measured separation:
  a healthy closed ring 99.98 %, the mis-driven helix 5.2 % — 19x apart.
  **A topological (Euler/genus) test was tried first and rejected**: it reports
  EMStudio's own closed template tube as genus-0, because OCC's seam edges
  break the naive V-E+F count. The gate pins that it is not reintroduced.
- Gate `tests/validation/coil_inductance_elmer.py` (SOLVER tier): the analytic
  loop inductance, both guard directions from measured data, and the three
  deck keywords — including that the non-existent one is never emitted.

## [0.80.0] — 2026-08-05 — the assistant gets a Settings dialog (Pro)

### Added
- **Assistant Settings dialog** (Pro): endpoint, model and API key get a real
  UI — previously they were environment variables or the raw parameter
  editor, and a wrong model name surfaced only as a bare HTTP 404 at question
  time (measured on a real machine, 2026-08-05). Provider **presets**: local
  Ollama / LM Studio / **CentralBrain** (AJJ³'s own private AI server,
  default `http://127.0.0.1:8765/v1` per its documented port) and hosted
  **OpenAI** / **Anthropic (Claude)** — the latter through Anthropic's
  OpenAI-compatible layer; both endpoints verified live (401-not-404 without
  a key). **Fetch models** fills the model list from the server's own
  `GET /models` answer — no more guessed names — and **Test** runs the full
  capability preflight (reachable / model served / tool calling / constrained
  JSON) against the values **as typed**, before Save.
- `llm.api_key()`: the key now also resolves from the `AssistantApiKey`
  preference (env still wins; the dialog warns per-field when an env var
  overrides it, and states plainly that the preference is stored in plain
  text — prefer the env var on shared machines). An explicit key parameter
  threads through every network call so Test probes exactly what was typed;
  gate-covered with the parameter-beats-env and empty-key-sends-no-header
  cases, mutation-proven (reverting the plumbing fails 2 checks).
- gui_smoke: the settings dialog is constructed for real — prefill from
  preferences, preset application (which must never clobber a typed model),
  password echo on the key field, empty-field probe semantics, and save-back
  are all asserted.

### Fixed — an adversarial review fleet (9 agents, per-finding refutation)
confirmed 5 distinct findings in the first cut; all fixed before shipping:
- **Test/Fetch probed the wrong configuration when env vars were in play**:
  empty fields fell back to compile-time defaults instead of the effective
  env→pref→default resolution, and an empty key field meant "send no key" —
  so Test reported 401 in the dialog's own recommended setup (key in the env
  var). Empty fields now probe exactly what the assistant will use.
- **The Bearer key was forwarded on HTTP redirects to whatever host the
  Location header named** (reproduced live with two loopback servers). The
  key now rides an *unredirected* header, which urllib never copies; a
  redirecting endpoint fails with an honest 401 instead of leaking the key.
- **A key containing a stray CR/LF leaked verbatim into message boxes** via
  http.client's "Invalid header value" repr. Keys are stripped and control
  characters refused with a message that never echoes the key.
- **Cancelling a Fetch/Test/preflight progress dialog stranded the UI**
  (button or dock permanently disabled — the worker's completion is never
  delivered after a cancel). Every run_generic_gui call in the dock now
  passes on_cancel.
- **The gui_smoke self-skip was over-broad**: a from-import of three names
  would report a renamed Pro attribute as a false "free tree" skip. Module
  import + attribute access now, matching the _assistant_dock precedent.
- Bonus, from AJ updating Pro live: **the licence dialog told updaters to
  enter their key while the status line said "active"**. An update install
  with an empty key now says the activation is kept (it always was — the
  activation file survives module updates by design) and reminds about the
  restart. The intro states it too.

## [0.79.0] — 2026-08-04 — Windows gets a NEC engine by one click, and a licence claim that was wrong from day one

### Added
- **Guided Windows install for NEC2.** Solver Setup now shows **Install…** for
  the NEC2 backend on Windows, alongside Elmer and gmsh. Windows previously had
  no NEC engine at all short of WSL2, because *nobody* publishes a Windows build
  of any NEC engine (checked upstream: nec2c, necpp, opennec, xnec2c). So this
  is the first **self-hosted** entry in `WIN_INSTALL_PLANS`: EMStudio builds
  nec2++ 2.3.4 from **unmodified** upstream source and publishes it as a release
  asset on the public repo, with the GPL-2 §3 complete-corresponding-source zip
  in the same release.
  [`nec2pp-2.3.4-win64`](https://github.com/king-aj3/EMStudioFree/releases/tag/nec2pp-2.3.4-win64)
- **The gate now enforces the licence obligation, not just the plan shape.**
  Any self-hosted plan must carry a `source_offer`, and its release tag must
  MATCH the binary's — so a rebuild cannot ship new binaries against a stale
  source zip. Being the distributor is what creates the duty, so
  `is_self_hosted()` is what triggers the check. Mutation-tested 2/2 (offer
  deleted; offer left at an older tag).
- **`gui_smoke` finally covers `installer_dialog.py`.** It never had a check for
  it — v0.78.0 and v0.78.1 both rewrote that file and the suite could not see
  either change, so a green run was reported as verification it did not perform.
  Worse, every changed line sits behind `self._is_win`, so the Windows branch is
  untested on any machine that is not Windows unless it is simulated. The new
  check forces `os.name = "nt"` with all backends missing and asserts the table
  the user would see: Install buttons for **exactly** the `WIN_INSTALL_PLANS`
  keys, no Build buttons, log pane visible, sudo row hidden. Mutation-tested
  3/3, including re-hiding the log pane (the v0.78.0 regression) and adding a
  plan that never reaches a button.

### Fixed
- **FastHenry was documented as LGPL. It is not, and never was.** FastHenry2
  ships **no licence file**; the only licence text in the tree is an M.I.T.
  1992/1994 header on **18 source files**: *"Permission to use, copy and modify
  for internal, noncommercial purposes is hereby granted. Any distribution of
  this program or any part thereof is strictly prohibited without prior written
  consent of M.I.T."* `grep -rn -iE "LGPL|GNU Lesser|General Public"` over the
  whole tree returns zero hits. The `manual_hint` had said "Build from source
  (LGPL)" since the backend was written — shipped in the **public** repo and
  shown to users in Solver Setup. Now states the real terms, including the
  noncommercial restriction, so a commercial user can make an informed choice.
  **Consequence: FastHenry can never have an Install button on these terms** —
  we may not ship the binary, and "any part thereof" covers the source too. The
  guided *source build* is unaffected: the user compiles their own copy, which
  is the use-and-modify grant, not distribution.
- **The nec2++ Windows DLL list was incomplete, in the text AND in reality.**
  It named the three MinGW runtime DLLs and omitted **`libnecpp.dll`** —
  necpp's own shared library, which no amount of MinGW-runtime hunting would
  have supplied. A user following those instructions hits `0xC0000135`
  (STATUS_DLL_NOT_FOUND) with no message and no output file, exactly the trap
  the text was written to prevent. Found by measuring the full `objdump -p`
  import closure instead of trusting the note; negative-controlled by deleting
  `libnecpp.dll` and confirming exit `-1073741515` with nothing written.
- **`FASTHENRY_CFLAGS` gained `-std=gnu17`, and it is not a suppression.**
  **GCC 15 defaults to C23**, where an empty parameter list `()` means "takes no
  parameters" rather than "unspecified". Every K&R call in FastHenry then fails
  with `too many arguments to function` — a *semantic* error that no `-Wno-`
  flag can reach, so the four existing suppressions were necessary but not
  sufficient. This affects Linux and macOS guided builds on GCC 15 too, not just
  Windows. The ratchet in the gate moved 4 → 5 with it; leaving it at 4 would
  have let a flag be dropped in silence, which is the exact failure this check
  exists for. Mutation-tested.

### Verified
- `nec2++.exe` (SHA256 `dbac0e68…cd3de1c4`) built from necpp `46f7fbde` with
  MinGW-W64 GCC 15.2.0 / CMake 4.4.2. Output on the shipped 300 MHz dipole is
  **byte-identical to the Linux build** — `7.4897E+01 + 9.8011E+00j` ohm.
  Extracted into an empty directory and run with `PATH` stripped to
  `C:\Windows`, from an unrelated working directory: it needs nothing else
  installed.
- The published asset was re-downloaded **anonymously** (no token) and re-hashed
  before the plan URL was committed, because the URL a customer hits is the only
  one that matters.

## [0.78.1] — 2026-08-04 — a Gumroad 404 is a verdict, not a network failure

### Fixed
- **Pro licence activation misreported an invalid key as "Could not reach
  Gumroad (HTTP Error 404: Not Found)".** Gumroad's verify API answers HTTP
  404 *by design* when a key does not exist for the product; urllib raises
  that as an exception and the blanket handler labelled it connectivity
  trouble (found live during AJ's own 0.78.0 re-activation). Two harms, both
  fixed: the buyer never saw Gumroad's actual message ("That license does
  not exist for the provided product."), and `check()` — which deliberately
  keeps a cached activation alive when Gumroad is unreachable — treated the
  refusal as unreachable, so an invalid key could stay active forever. HTTP
  error bodies are now parsed as verdicts; only genuine transport failures
  read "could not reach". The licence gate grew six mocked-network checks
  covering both directions (a refused key stops working; a no-network buyer
  keeps working), mutation-proven against the old behaviour (4 checks fail).

## [0.78.0] — 2026-08-04 — guided solver install arrives on native Windows

### Added
- **One-click guided solver installs on native Windows** (Elmer and gmsh
  first). The Linux/macOS wizard compiles from source through bash; Windows
  has no bash, often no compiler and no admin rights, so its guided path
  **downloads the official prebuilt binaries** instead — stdlib urllib +
  zipfile into `%LOCALAPPDATA%\EMStudio\solvers\<backend>`, no shell, no NSIS
  installer, no UAC prompt. Solver Setup shows an **Install** button for these
  backends and streams download/extract progress into the log pane (which was
  previously hidden on Windows). Detection probes the managed directory
  automatically, PATH-independent — a FreeCAD launched from a bare-environment
  shortcut still finds the result.
  - **Elmer**: CSC's own `gui/nompi` Windows build (~122 MB) — the entire
    magnetics arc now installs on Windows with one button. nompi is
    deliberate (EMStudio drives a headless serial ElmerSolver, and MS-MPI
    would need its own admin installer); gui — NOT nogui — is a measured
    call: the nogui zip ships **no MinGW runtime DLLs at all** (only static
    `.a` archives in its stripped toolchain), so its ElmerSolver.exe exits
    0xC0000135 before printing a byte. The gui zip is 11 MB larger and
    self-contained.
  - **gmsh**: the official `gmsh-stable-Windows64.zip` (~37 MB), for FreeCAD
    builds that do not bundle gmsh.
  - Only backends whose upstream publishes real Windows binaries get the
    button. The rest keep honest guidance: nec2++ still builds from source,
    FastFieldSolvers gates its downloads behind a form, openEMS full runs
    still want WSL2, and Palace has no Windows support at all.
- Smoke gate: the plan table must be https + well-formed on every platform
  (Linux CI guards a bad URL from shipping); on Windows a fake archive served
  over `file://` runs the REAL download → extract → nested-topdir discovery →
  move-into-place pipeline, and `find_backend` must then locate the result
  through the managed-dir probe with PATH stripped.

### Fixed
- Three Windows defects the live install run caught, each invisible from
  Linux (all three then gated):
  - **`find_elmergrid` missed `ElmerGrid.exe`** sitting in the same bin
    directory as the detected ElmerSolver — the sibling lookup built the
    bare name with no suffix. The smoke gate now requires ElmerGrid to
    resolve beside the managed ElmerSolver.
  - **A zip-layout Elmer needs its documented environment** (`ELMER_HOME`,
    `ELMER_LIB`, PATH additions per CSC's Readme1st.txt) or ElmerSolver
    dies 0xC0000135 with no output. Every Elmer/ElmerGrid spawn (2-D, 3-D,
    sweep) now derives that environment from the executable's own location
    (`elmer_env`), so a hand-unzipped tree works identically.
  - **Corporate TLS interception broke urllib downloads**
    (CERTIFICATE_VERIFY_FAILED: OpenSSL cannot chase a private CA's
    intermediates). The downloader now falls back to Windows' built-in
    curl.exe, whose schannel backend trusts the Windows certificate store —
    verification is never disabled. Measured live: funet was intercepted
    and fell back; gmsh.info streamed straight through urllib.
- `tests/smoke.py`'s version-probe check faked its solver with a `#!/bin/sh`
  script, which cannot execute on native Windows — the check failed on every
  Windows box. The fake is now platform-aware (a `.cmd` that types a sidecar
  file, because cmd.exe would eat the help text's `<angle brackets>` if
  echoed). Mutation-tested on Windows: the pre-0.77.7 any-digit-line probe
  mutation is still caught.

## [0.77.9] — 2026-08-03 — Windows has a native NEC engine, verified

v0.77.8 shipped saying nec2++ on Windows was "promising rather than proven".
It is now proven, so that text is replaced rather than left to age.

### Verified
- **nec2++ builds and runs natively on Windows** (MinGW-w64 GCC 15.2.0 +
  CMake 4.4.2) and its output on the shipped dipole deck is **byte-identical**
  to the Linux build's — same `7.4897E+01 / 9.8011E+00` impedance row. Windows
  goes from "no NEC engine exists, use WSL2" to a working native one. All three
  platforms now agree.

### Changed
- The Windows hint now carries the two traps, because neither prints anything
  useful and both cost real time:
  - a MinGW-built `nec2++.exe` needs `libstdc++-6.dll`, `libgcc_s_seh-1.dll` and
    `libwinpthread-1.dll` on `PATH`, or it exits **0xC0000135**
    (STATUS_DLL_NOT_FOUND) with **no message and no output file**;
  - `cmake --build` with no target fails at 100% linking `nec2++_tests.exe`
    (`__imp__set_abort_behavior` is MSVC-only CRT). **The engine is already
    built at that point** — use `--target nec2++`. A user seeing that error
    would reasonably conclude the build failed. It did not.

## [0.77.8] — 2026-08-03 — a second NEC engine that already half-worked, and a guided Elmer build for macOS

### Fixed
- **EMStudio could detect `nec2++` and then fail to read it.** `nec2++` has been
  in the NEC2 backend's `executables` tuple since the backend was written, so the
  workbench has always advertised support — but the frequency regex demanded a
  colon and nec2++ writes an equals sign:

      nec2c   FREQUENCY : 3.0000E+02 MHz
      nec2++  FREQUENCY=  3.0000E+02 MHZ

  A user with nec2++ installed therefore got a solver that detected fine and then
  died at *"impedance row before any FREQUENCY line"*. One character.

### Added
- **A guided Elmer build for macOS.** Elmer has no Homebrew formula, so macOS
  users must build it — and there was no recipe. `build_plan()` is now decided
  per platform rather than by the `source_build` flag alone, because Elmer is
  `apt install elmerfem-csc` on Linux and source-only on macOS; flipping the flag
  would have dropped `elmerfem-csc` out of the **Linux** apt line. Verified by
  running the plan from scratch through `run_build()` on the M1 host: 3.5 min
  (warm ccache; ~18 cold), ending at a detected `~/opt/elmer/bin/ElmerSolver`.
  **`-DWITH_OpenMP=ON` fails** — Apple clang ships no OpenMP and CMake dies at
  `Could NOT find OpenMP_C` before writing a Makefile. The recipe pins it OFF.
- `nec2` now declares `~/opt/necpp-build/src` and `~/opt/necpp/build/src` so a
  CMake-built nec2++ is found.

### Evaluated — three NEC engines on Apple Silicon, measured not assumed
No NEC engine is in homebrew-core at all (checked `nec2c`, `necpp`, `opennec`,
`xnec2c` — all 404), so the "no formula" guidance was correct for every one.

| Engine | Verdict |
|---|---|
| **nec2c** (KJ7LNW) | Baseline. Reproduces the shipped reference exactly. GPL-3.0, 13 stars, last push 2024-12-17. |
| **nec2++** (necpp) | **Works, and now supported.** Builds clean on macOS arm64 under Apple clang 21. Matches nec2c to 4 s.f. on the dipole gate — 296.283 vs 296.287 MHz, both 71.92 ohm, both 2.13 dBi, both −15.18 dB. GPL-2.0, 303 stars, actively maintained. |
| **OpenNEC** | **Not viable today.** It is MIT (GitHub reports `NOASSERTION` only because the LICENSE is markdown with a badge — the licence is not ambiguous). But it does not compute: it echoes the deck and cards, reports `TOTAL RUN TIME: 0 msec`, and emits no `ANTENNA INPUT PARAMETERS` — **including for its own bundled example deck**, with `-f nec2c` and `-l lf` set. Its deck parsing and format conversion are genuinely strong; the solver is not usable as a backend. Worth re-checking later. |

Both working engines drive the *same* subprocess contract, so this costs nothing
in coupling — which is the point of the isolated-backend design.

**Windows may benefit most, and is NOT yet verified.** nec2c has no Windows
build at all, so Windows has always been the weakest platform for this backend
(the guidance was "use WSL2 or MSYS2"). nec2++ builds with CMake, carries an
explicit MSVC branch, and its upstream CI covers `windows-latest` — so it is
plausibly a *native* Windows engine. EMStudio has **not** tested that, and the
hint says so in those words rather than implying support.

### Changed
- **`results dialogs construct` no longer requires ElmerSolver.** It is a UI
  check, but it ran a full Elmer solve and a two-point gap sweep purely to obtain
  something to hand the dialogs — so on any machine without Elmer it failed with
  "ElmerSolver not found", which says nothing about whether the dialogs construct
  and reports a missing optional dependency as a product defect. Whether Elmer
  solves is already covered by the dedicated solve-loop checks, which fail
  honestly when it is absent.
  Elmer is still used **when present** (a real result is better coverage than a
  synthesized one) and the detail string now says which path ran, so a green tick
  is never ambiguous about what was exercised. The fallback builds a **real**
  `MagneticsResult` through its own constructor with the dict keys the runner
  produces — not a mock — so `summary_text()` and `coil_impedance()` still run
  for real and key drift still breaks it.
  Construction alone was also a weak assertion (a dialog that rendered nothing
  would have passed), so the check now requires the summary to have real content
  and the plot to keep every point it was given. Mutation-tested 2/2.
  Measured on the M1 host: with Elmer hidden, gui_smoke goes from 4 failures to
  3, and all 3 remaining are the genuine Elmer solve loops.

## [0.77.7] — 2026-08-03 — two backends were undiscoverable, and one reported its help text as a version

Both found by the macOS build host that landed in 0.77.6, and both fixed against
it rather than reasoned about.

### Fixed
- **Elmer and NEC2 declared no search paths at all**, so a correctly source-built
  copy was invisible to Detect Solvers. Neither has a Homebrew formula, which
  means macOS users *always* build them from source — and every other
  formula-less backend already declared its `~/opt` prefix. These two were the
  holdouts, hidden on Linux because `apt` puts both on `PATH`. Elmer built
  cleanly into `~/opt/elmer` and detection still said MISSING. `elmer` now
  declares `~/opt/elmer/bin` and `~/opt/elmerfem/bin`; `nec2` declares
  `~/opt/nec2c/bin` and `~/opt/nec2c` (a plain `make` leaves the binary in the
  source root — measured, not guessed).
- **NEC2 reported `-v: print nec2c version number and exit.` as its version.**
  `version_args` was `-h`, carrying a comment asserting nec2c had no version
  flag. It has one: `nec2c -v` prints `nec2c 1.3`. The help output's third line
  contains a digit (in "nec2c") and says neither "usage" nor "option", so the
  probe returned the whole sentence and Solver Setup displayed it.
- **`_probe_version` now refuses any line beginning with `-`.** A documented flag
  is never a version, so pointing a backend at the wrong argument degrades to "no
  version" instead of to a plausible-looking lie.

### Changed
- The gate states the **invariant**, not the instances: every backend whose macOS
  hint says "No Homebrew formula" must declare `extra_dirs`. Written that way so
  the *next* formula-less backend cannot repeat this. Mutation-tested 3/3,
  including a mutation that makes `_probe_version` always return `""` — the lazy
  pass that a one-sided assertion would have missed.

### Tooling
- `tests/run_pro_freecad.sh` now resolves `EMSTUDIO_TREE` to an absolute path and
  refuses a non-directory. The tree is reached through a symlink planted in a
  throwaway user home under `$TMPDIR`, so a relative value dangled, FreeCAD
  loaded no workbench, and gui_smoke failed on **"workbench + command
  registration"** — which reads exactly like a registration regression and is
  not one. It cost a real false alarm during this release.

### Known
- `ElmerSolver --version` starts the solver and emits a timestamped banner, so
  the reported version string varies between probes. Cosmetic; it does contain
  `(v 26.2)`.

## [0.77.6] — 2026-08-03 — FastHenry still would not build; found on real hardware

**The first release verified on a Mac.** Everything from 0.77.1 to 0.77.5 rested
on gates and simulation. A headless M1 build host now carries FreeCAD 0.21.2,
1.1.1 and 1.1.3, and the whole macOS path was run there.

### Fixed
- **The guided FastHenry build still failed on current macOS**, one compiler
  generation past the bug it was supposed to fix. v0.77.2 added
  `-Wno-implicit-int` and `-Wno-implicit-function-declaration` for Apple clang
  15; **Apple clang 21 promotes `-Wreturn-mismatch` to a hard error as well**,
  so `induct.c` still died — `131 warnings and 2 errors generated`. Adding
  `-Wno-return-mismatch` builds it clean (verified: a 417 KB binary, on the
  build host, not in a simulation).
- **The flags now have exactly one definition**, `solvers.FASTHENRY_CFLAGS`,
  interpolated into the build plan, the manual hint and the macOS hint. They had
  been spelled out in three places, and a constant repeated in three places
  cannot be gated — moving one copy changes nothing and the gate stays green.

### Changed
- The FastHenry gate **no longer enumerates the flags it knows about**, which is
  precisely why the second wave got through: it tested the list that was already
  correct. It now reads `solvers.FASTHENRY_REQUIRED_FLAGS` and checks all
  **three** user-facing surfaces — the macOS hint was absent from the old check
  and could have drifted silently. Mutation-tested 2/2.
- Maintainer metadata in `package.xml` is now the brand (`ajj3.us` /
  `support@ajj3.us`).

### Verified on macOS hardware (previously simulation only)
- Solver Setup reports **(macOS)**, leads with `xcode-select --install`, offers a
  `brew install` line, and contains **no `apt` anywhere**.
- The 0.77.4 Homebrew probe **works**: with `/opt/homebrew/bin` off `PATH`,
  `shutil.which("nec2c")` returns `None` while `find_backend` still resolves
  `/opt/homebrew/bin/nec2c` with `source='probe'`.
- The 0.77.5 basename fix **works**: all three NEC2 solve loops complete through
  real `/var/folders/…` temp paths — dipole `f_res 294.0 MHz`, monopole
  `Zin 4.02−570.1j Ω`, isolation `|S21| −13.78 dB`.
- Palace's `$(nproc 2>/dev/null || sysctl -n hw.ncpu)` resolves (`nproc` is
  genuinely absent on a stock Mac).
- Pro installs and activates its namespace injection on 1.1.1 and 1.1.3.

### Known — upstream, not EMStudio
- **FreeCAD 0.21.2 on macOS arm64 cannot import numpy at all.** Its bundled
  `libgfortran.5.dylib` carries duplicate `LC_RPATH` entries, which modern dyld
  rejects, so `libopenblas` fails to load. It fails identically through the real
  `.app`, and no `DYLD_*` variable can repair a malformed load command. On that
  version smoke drops to 13 ok / 3 fail. **1.1.1 and 1.1.3 are unaffected** —
  use those on macOS.

## [0.77.5] — 2026-08-02 — nec2c aborted on macOS: input filename too long

### Fixed
- **Every NEC2 run failed on macOS with `nec2c: Input file name too long -
  aborting` (exit 255).** nec2c has a fixed-size input-filename buffer, and
  EMStudio passed it absolute paths. Those fit on Linux
  (`/tmp/emstudio_nec2_xxxx/case.nec`, ~36 chars) and do not on macOS, where
  `tempfile` yields `/var/folders/<hash>/T/…` and the same deck runs ~80.
  Reported by *ap_engineering* on macOS 26.5 after he built nec2c from source
  himself — so the run reached the solver and died there, which is why the
  earlier fixes did not surface it.
- Every caller already passed `cwd=<deck's directory>`, so the basename was
  always sufficient — and is what the Elmer, FastHenry and Palace runners were
  already doing. NEC2 was the lone holdout. All **seven** invocations now go
  through one helper, `emstudio.solvers.base.nec2_argv()`, which also refuses a
  deck and output in different directories rather than silently truncating.
- **This affected Pro as well as Free** — `system/array_system.py` (Array
  Designer) and `system/rfdf.py` (RF direction finding) each build NEC2 decks,
  so both were broken on macOS. **Pro needs a rebuild and re-upload**, unlike
  0.77.1-0.77.4 which touched only free-tier files.
- Gated: the helper's behaviour plus a static scan that refuses any hand-built
  `[exe, "-i", …]` argv anywhere under `emstudio/`. Mutation-tested 4/4,
  including a deliberate regression in the Pro call site.

## [0.77.4] — 2026-08-02 — look where Homebrew puts things

### Fixed
- **A solver installed with Homebrew could still report MISSING on macOS.**
  Detection probed PATH plus a few source-build directories, and **FreeCAD
  launched from Finder does not inherit your shell PATH** — so `brew install
  gmsh` could succeed while Solver Setup insisted gmsh was absent. 0.77.1
  shipped this as *advice* ("put Homebrew's bin on PATH before starting
  FreeCAD"); telling the user to work around it was the wrong answer when the
  fix is to look in the right place. `MACOS_PROBE_DIRS` now adds
  `/opt/homebrew/bin` (Apple Silicon), `/usr/local/bin` (Intel) and
  `/opt/local/bin` (MacPorts — nec2c has a port there and no Homebrew formula)
  to the probe for every backend, on macOS only.
- New gate, found by auditing rather than by a report. Note the first version
  of the gate asserted the *constant* existed, and a mutation that deleted
  `_platform_dirs()` from the actual search loop **survived it** — asserting a
  value is not the same as asserting the behaviour. It now plants a real binary
  in a fake Homebrew directory and requires `find_backend` to locate it.
  Mutation-tested 4/4.

## [0.77.3] — 2026-08-02 — `brew install tinyxml` does not exist

### Fixed
- **The macOS guidance named a Homebrew formula that is not real.** `tinyxml`
  was added to the openEMS prerequisites from memory; homebrew-core carries only
  `tinyxml2`, which is a **different API** — openEMS needs v1, so substituting it
  would produce a build that fails later and deeper. The prerequisite now
  declares no formula and says why, and the openEMS macOS hint tells you to
  build TinyXML v1 from source or use a tap.
  This is the *exact* failure the 0.77.1 fix existed to prevent — a confident
  command that cannot run — reintroduced two versions later by trusting memory
  over a lookup. Every other formula named in the file was checked against
  `formulae.brew.sh/api/formula/<name>.json`: gmsh, cmake, git, hdf5, vtk,
  boost, cgal, gmp, open-mpi, openblas and gcc all exist; nec2c, openems,
  fasthenry, elmerfem and palace do not, and were already documented as having
  none.
- New gate: `VERIFIED_BREW_FORMULAE` is an explicit allow-list, and the smoke
  test refuses any `brew=` / `brew_package` outside it, plus any attempt to
  smuggle `tinyxml`/`tinyxml2` back through the prose hints. Adding a formula
  now requires curling the API and updating the set in the same commit.
  Mutation-tested 2/2.
- README's macOS column no longer lists `tinyxml` in the brew line, and the
  status line said v0.77.0 three releases after it stopped being true.

## [0.77.2] — 2026-08-02 — the FastHenry build works on a modern compiler

### Fixed
- **The guided FastHenry build failed on macOS with ~20 errors in `induct.c`** —
  the second half of the same forum report, which 0.77.1 missed. FastHenry is
  K&R-era C (`main(argc, argv)` with no return type, calls before declaration).
  **Apple clang 15+ and GCC 14+ promoted `-Wimplicit-int` and
  `-Wimplicit-function-declaration` from warnings to hard errors**, so a build
  that had worked for years now dies at the first file. The CFLAGS everywhere
  they are quoted — the build plan, the manual hint and the macOS hint — are now
  `-O -DFOUR -m64 -fcommon -Wno-implicit-int -Wno-implicit-function-declaration`.
  Verified by reproducing the failure with `-Werror=implicit-int
  -Werror=implicit-function-declaration` and confirming the added flags clear it.
  This is not macOS-specific: it lands on Linux too as soon as GCC 14 arrives,
  which is why the build machine's GCC 13 never saw it.
- New gate: every place that quotes the FastHenry CFLAGS must carry all three
  flags. Mutation-tested 2/2.

## [0.77.1] — 2026-08-01 — Solver Setup works on macOS

### Fixed
- **Solver Setup gave macOS users Debian `apt` commands, so it could not be
  followed at all.** Reported on the FreeCAD forum by *ap_engineering* on
  macOS 26.x — the first bug report EMStudio has received, and a fair one.
  `emstudio/setup/solvers.py` branched on `os.name == "nt"` and treated
  everything else as Debian; macOS is `posix`, so a Mac fell into the Linux
  path and was told to run `sudo apt install -y cmake libhdf5-dev …`. There is
  now a third branch:
  - `install_hint()`, `install_plan()` and `install_report_text()` each have a
    macOS path. The report is headed "(macOS)", leads with
    `xcode-select --install`, and explains that Homebrew's bin directory must
    be on `PATH` before FreeCAD starts or detection cannot see the solvers.
  - `install_plan()` returns a **`brew_line`** — one `brew install …` covering
    every missing prerequisite — and `apt_line` is now empty on macOS as well
    as on Windows. Exactly one of the two is ever non-empty.
  - `Prereq` gained a `brew` field and `Backend` a `brew_package`. These are
    filled in **only where a homebrew-core formula genuinely exists**; where
    none does (openEMS, NEC2, FastHenry, Elmer, Palace) the guidance says so
    and points at the source build instead of inventing a formula name.
  - The Solver Setup dialog relabels its command row "brew step:" and copies
    the brew command; the per-backend detail column shows macOS guidance.
  - The Palace build step used `$(nproc)`, which does not exist on a stock
    macOS, so even a correctly-prepared Mac would have failed mid-build. It is
    now `$(nproc 2>/dev/null || sysctl -n hw.ncpu)`.
- The platform-segregation gate in `tests/smoke.py` covered Windows and Linux
  only — which is exactly why this shipped. It now covers macOS too, forces a
  known-missing prerequisite so the assertion cannot pass by accident of what
  the build machine has installed, and asserts no build step depends on
  `nproc`. Mutation-tested: 4/4 deliberate regressions caught, including
  deletion of the whole macOS branch.

### Changed
- README's backend table gained an **Install (macOS)** column.

## [0.77.0] — 2026-07-31 — EMStudio Pro is on sale

### Added
- **EMStudio Pro is purchasable — $149 one-time, perpetual, no subscription and
  no account.** The paid tier adds the §7 System Designer (impedance matching,
  filter and diplexer synthesis, phased arrays with amplitude tapers, RF
  direction finding) and the §3 AI assistant. This workbench stays free, LGPL,
  and keeps every solver, template, designer and validation gate it has today.
- **New command: EMStudio → Help → EMStudio Pro — install / activate.** Installs
  the purchased zip and activates it, with no terminal and no pip. It unpacks
  into `Mod/EMStudioPro`, a *sibling* of `Mod/EMStudio` — the Add-on Manager
  owns the latter and overwrites it on every update, which would silently delete
  a paid module installed inside it. Archive members are validated before
  extraction (absolute paths, `..` traversal and symlinks are all refused), and
  the dialog reports install/activation state rather than making you guess.

### Changed
- Every surface that said EMStudio Pro was "in development" now states the
  price and how to buy it: `docs/PRO.md`, the free README, `HELP.md`,
  `emstudio/legal.py` (the single source the dialogs and report footers read),
  and the About dialog.
- The Element Designer's tier note used to point at "a future Pro tier
  (solver-in-the-loop optimizer, exotic families, AI intent)". With Pro now on
  sale that read as a promise about what a buyer had just paid for. It now says
  plainly that Pro does not change that dialog, and that those ideas are
  roadmap only and part of nothing that is sold today.

### Note
- The Pro module itself is not in this repository, by design. Nothing here
  verifies a licence: a check shipped in LGPL code is deleted in thirty seconds,
  entirely within the user's rights, so all verification lives in the paid
  module where it means something.

## [0.76.0] — 2026-07-31 — the balloon sits on the antenna, and the examples are visible

### Changed
- **Pattern overlays are centred on the geometry, not the origin** (AJ's call).
  A far field is referenced to the SOLVER's origin, and a template built from
  x=0 puts that origin at one END of the structure — the shipped 400 MHz Yagi
  hung its balloon off the reflector instead of covering the array. Only where
  the plot is DRAWN moves; the directions it shows are unchanged, which is why
  this is presentation rather than physics. New `vtk_out.geometry_extent_mm()`
  returns the bounding-box centre and span, and both the Element Designer and
  the Results dialog now pass them. It is explicitly NOT the phase centre — the
  solvers do not report one — and it returns `(None, None)` when there is no
  geometry, so a caller falls back rather than centring on an invented point.
  The Array Designer still draws at the origin, because its Verify builds the
  array in a scratch document that is closed before the overlay exists.

### Fixed
- **Every shipped example opened with its geometry HIDDEN.** `gen_examples.py`
  ran under `freecadcmd`, which creates no ViewObjects, so the saved documents
  carried no visibility state and all 15 examples opened to an **empty 3-D
  view** — the first thing a new user double-clicks, looking like a broken
  workbench. This shipped in v0.74.0 and v0.75.0. The generator now runs under
  GUI FreeCAD, sets visibility explicitly, refuses to write a document with no
  visible shape, and exits cleanly instead of leaving FreeCAD open forever.

### Added
- Headless gate for `geometry_extent_mm` (bbox centre not origin, multiple
  objects unioned, shapeless objects skipped, `(None, None)` rather than a
  guess) — mutation-tested three ways.
- gui_smoke check that every shipped example opens with visible geometry.
  Mutation-tested by hiding one: "opens with ALL 1 shapes hidden — an empty
  viewport". `smoke.py` cannot catch this; without a GUI there is no ViewObject
  to ask.

### Known
- v0.74.0 and v0.75.0 are public with the hidden-geometry examples.

## [0.75.0] — 2026-07-31 — the 3-D overlays were never actually coloured

### Fixed
- **Every 3-D result overlay rendered flat grey with a colour legend beside it
  that explained nothing.** `show_in_freecad` read the `Field` property into a
  local variable and threw it away — a dead line inside a swallowing
  `try/except`, under a comment claiming it coloured by the default field.
  Compounding it: `Field` is an **enumeration**, so reading it returns the
  CURRENT value (a string), and `list()` on that yields the string's
  *characters*; the choices only come from `getEnumerationsOfProperty`. Gain
  balloons, wire-current paths and near-field planes were all monochrome.
  **This shipped in v0.74.0** — found while taking a screenshot for the launch
  post, which is the first time anyone had looked at the output.
- `show_pattern` / `show_in_freecad` gained a `transparency` argument, so a
  balloon can be seen through to the geometry it belongs to.

### Added
- A gui_smoke check asserting an overlay arrives coloured by its own field and
  with transparency honoured. Mutation-tested: restoring the dead line fails it
  with `got 'None'`. Colouring is GUI-side, so the headless `pattern_vtu` gate
  structurally could not have caught this — the VTU it writes was always correct.

### Known
- v0.74.0 was public for about a day with the grey overlays. **Fixed and
  re-released as EMStudioFree v0.75.0 the same day**, verified as a product
  before the push: the built tree's own battery 16 ok, FreeCAD smoke and
  gui_smoke exit 0, and the new overlay check proven to discriminate INSIDE the
  exported tree (mutating it there turns gui_smoke red).
- The overlay is still centred on the **origin**, which for a NEC2 wire antenna
  built from x=0 puts a Yagi's pattern at the reflector end rather than over the
  array. Physically the far field IS referenced to that origin, so this is a
  presentation question, not a correctness one — left as an open decision rather
  than changed silently.

## [0.74.0] — 2026-07-30 — LAUNCH: accepted into the FreeCAD Addon Index, examples ship, the export is one command

### The submission was ACCEPTED
[FreeCAD/Addons#101](https://github.com/FreeCAD/Addons/issues/101) closed as
completed on 2026-07-30: *"We don't prohibit Open Core addons, so there's no
problem in that regard. This addon looks like a clean, well-considered addition,
I have no requested changes."* **EMStudioFree is in the DEFAULT Add-on Manager
listing** — users install it without adding a custom repository, and a bot
refreshes addons.freecad.org roughly every 6 hours.

### Added — `examples/`, generated rather than hand-made
- **`tools/gen_examples.py` builds 15 ready-to-open `.FCStd` documents**, one
  per shipped template, by calling the SAME public `makeX()` the Templates menu
  calls. Nothing is solved: they are inputs, so they stay small (4.5-13 KB) and
  the numbers a user gets are their own.
- **This repairs an inverted export direction.** Four hand-made examples had
  been committed straight into the PUBLIC EMStudioFree repo, where the tier
  split says content must never originate — the next export would have deleted
  them. `examples` appeared nowhere in the manifest. The four published names
  are regenerated byte-for-byte in size from source, and `examples/**` is now
  exported.
- **A smoke check opens every one of them** and asserts it carries a real
  `EMStudio::Analysis`. These are the first thing a new user double-clicks and
  were the one shipped artifact with no regression net; a document that opens
  empty reads as "this workbench is broken" before anything has been run.

### Changed — the export is one command again
The three post-export hand edits are gone. They had grown to 12 gate names, 4
command ids and 3 dialog checks, and every export left the free tree's tier
audit RED until someone remembered all of it.
- **`commands.py` is stripped on the way out.** A command id lives in five
  places, and leaving any behind puts a menu entry in the free workbench for a
  feature it does not have — the built tree was logging `Cannot find icon:
  emstudio_matching.svg` for exactly that reason. Now zero such warnings. A
  renamed id fails the export rather than shipping a half-stripped file.
- **`run_battery.py`'s tiers are stripped from `exclude_tests`**, not from a
  second hand-maintained list — the two must agree, so one is computed from the
  other. Both the FAST dict and the SOLVER list forms are handled; missing the
  list form is what left four names behind on the first attempt.
- **The three Pro `gui_smoke` checks now self-skip** on ImportError, the pattern
  already proven by the §3 check. A denied module must never need code surgery
  in the free repo to keep its tests green.
- **`tests/run_pro_freecad.sh` takes `EMSTUDIO_TREE`**, so "verify every export
  under FreeCAD, not just python3" is one command against a built tree.

### Validation
- The BUILT free tree, verified as a product rather than as a file list: its own
  battery **16 ok / 0 failed**, `smoke.py` under FreeCAD PASSED including the GUI
  registration contract, `gui_smoke.py` exit 0 with **zero missing-icon
  warnings**. Pro side unchanged: assistant 131/131, FAST battery 23/23.

## [0.73.0] — 2026-07-30 — §3 A6: the adversarial review, and §3 is CLOSED

The four-dimension review with per-finding refutation (29 agents: correctness,
safety/tier, honesty of claims, test quality). 24 findings went to refutation,
**17 survived, 7 were refuted, 10 distinct after dedup** — the Yagi unit error
was found independently three times. Zero high-severity findings survived: every
"high" was revised down because §3 is Pro-only, off by default, and behind an
explicit modal confirmation.

### Fixed — the assistant was measuring over unordered sets
- **Front-to-back was not a front-to-back ratio.** It searched
  `(theta + 180) % 360` inside the peak's own phi cut, but the true antipode is
  `(180 - theta, phi + 180)` — a different phi COLUMN. Every grid the workbench
  emits stops at theta 180, so the search clamped to the last theta sample: a
  real over-ground dipole run through nec2c reported **68.2 dB against a
  −60 dBi null**. It now measures the true antipode, and where that direction is
  not sampled — which is every over-ground run — it reports **nothing** rather
  than quoting the grid edge.
- **HPBW measured lobe SEPARATION, not lobe width.** `max(half) - min(half)`
  over a non-contiguous set: a horizontal dipole one wavelength up read **50°
  for a 10° lobe**. Now the contiguous run containing the peak. This inverts the
  handoff's "coarse-grid lower bound" framing — it was an unbounded
  *over*statement on any multi-lobe cut.
- **10 dB bandwidth merged disjoint bands.** First-to-last sub-threshold sample
  with no contiguity test: the shipped LPDA template's own default sweep
  reported **"200–600 MHz (100 %)" with a −8.61 dB point inside the claim**. Now
  the contiguous run containing the best match. The acceptance line is one
  constant (`interpret.BW_ACCEPT_DB`) because it lived in three places and
  moving one changed nothing.

### Fixed — the assistant built the wrong antenna
- **A silent dBi→dBd relabel.** `gain_dbi` was mapped straight onto
  `makeYagi(gain_dbd=…)`: "12 dBi at 435 MHz" built a **2.2 λ boom / 12 elements
  / 14.40 dBi** where 12 dBi = 9.85 dBd means 1.2 λ / 6 elements — 0.83 m became
  1.52 m. Worse, `recommend_element` converted the identical argument correctly,
  and the dock re-offers tools so the model chains recommend→build: **the
  assistant could state one boom length and build another in one conversation.**
  The registry gained a converter slot so adding a parameter forces the units
  question at the point of declaration.
- **An LPDA's band could not be expressed.** Both `f_lo_hz` and `f_hi_hz` were
  mapped from the single `frequency_hz` key, making `f_lo == f_hi` and turning
  every supplied frequency into a guaranteed failure; the only LPDA that worked
  was one where the model named no frequency at all. `f_lo_hz`/`f_hi_hz` are now
  in the schema and `gain_dbi` is forwarded instead of silently dropped. A lone
  `frequency_hz` still does NOT pick a band — that would replace a loud refusal
  with a quiet wrong answer.

### Fixed — honesty and robustness
- `llm.available()` and `preflight()` promise they never raise, and both raised
  on a scheme-less endpoint (`localhost/v1`) because `Request()` was built
  outside the try. Guarded before the request, with its own error rather than
  the misleading "unparseable JSON".
- `plausibility.RANGES` was missing `f_lo_hz`/`f_hi_hz` — the band twin of the
  gemma4 unit error passed cleanly and reached the picker as 108 Hz / band SLF.
- The dock discarded `notes` on an empty model answer, so a **confirmed document
  mutation was reported as nothing** — an invitation to build it twice.
- `interpret_results` told users to "run a solver first" **after a successful
  solve**, because nothing attaches results to the document object. It now says
  results are not persisted and points at the Results dialog.
- Docstrings corrected where they overstated: `facts_block` is not what the model
  receives (it has no shipped caller), `summarise()` is not a no-model fallback,
  the tool surface does contain a `getattr` (the property is that no
  MODEL-supplied string becomes code), and "the same makeX() the toolbar uses"
  is not literally true — there is no toolbar button for yagi or lpda.

### Fixed — three gate checks that could not fail
- Bandwidth was asserted as `is not None` plus a re-derivation using the
  implementation's own formula: moving the acceptance line −10 → −6 dB kept the
  gate green while the number shown to the user went 5.57 % → 9.76 %. Now pinned
  to the closed form (5.657 % ± one sample spacing) plus a dual-band fixture.
- `db_at_target` was asserted by key presence: replacing it with the dip value —
  the exact bug the code comment warns about — survived. Now pinned by value AND
  by being ≥20 dB above the dip, which is the clause that distinguishes them.
- The confirmed-mutation path had **no test anywhere**. Deleting
  `doc.openTransaction()` means one Ctrl+Z destroys the user's own pre-existing
  object while leaving the assistant's behind — real data loss — and the battery
  still reported 23 ok. Now gated in gui_smoke, which is the only tier that can
  reach it (the FAST tier is python3-only and importing FreeCAD raises there).

### Added — gate checks
Assistant gate **111 → 131 checks**, plus four new FreeCAD-tier checks in
gui_smoke: the transaction/undo contract, a DECLINED action changing nothing
(dropping the confirmation branch had left both the battery and gui_smoke
green), actions still reported on an empty answer, and the honest
`interpret_results` message. Retrieval floors were tightened from bounds that
could not fail (`len(corpus) > 20` survived losing 89 % of the corpus; the
budget check asserted an EMPTY block was under 900 chars). Ranking quality is
now pinned against a synthetic corpus rather than a shipped doc heading, so
documentation edits do not break the gate. **16 mutations applied across the
slice, all caught.**

### Validation
- Assistant gate 131/131, FAST battery 23/23, smoke ×3, offscreen gui_smoke ×2.
- Verified counts, measured not quoted: corpus **189 chunks** from 5 files (the
  docs said 188), 57 gate files + the runner, 38 GUI commands, FAST tier 23.

### Known / deliberately not done
- **`_interpret_results` is dead in the shipped app** — nothing sets
  `obj.Proxy.result`, so the tool cannot read a solve. AJ's call was to make the
  message honest now and treat persistence as its own decision. The three
  measurement fixes above had to land first regardless.
- **`facts_block` is not wired** into what the model receives (it gets
  `json.dumps(result)[:4000]`). Wiring it changes what every model sees and
  needs its own gate on the shipped content.
- 20 lower-ranked findings were never refutation-tested (per-dimension cap of
  6): the retrieval tokenizer degrading recall, a stale agentic tooltip after a
  capability refresh, and `context_block` citing more sources than it sends.

## [0.72.0] — 2026-07-30 — 3-D result overlays: gated, registered, and reachable from the designers

The VTU overlay path (results as objects in FreeCAD's own 3-D view) shipped in an
earlier release **with no validation gate at all** and was reachable only from
the Results and Magnetics dialogs. This closes both gaps and fixes a resonance
read-out that could put fabricated numbers in a shipped PDF.

### Added
- **`tests/validation/pattern_vtu.py` — 27 checks, the first gate for
  `emstudio/post/vtk_out.py`.** The balloon, the wire-current polyline and the
  near-field plane were user-facing and ungated. The two checks that matter most
  are not the shapes: the radius must follow the gain law at **every** point (a
  balloon that ignored its own scalar field would still render as a plausible
  blob), and the geometry must be **registered** — an overlay centred on the
  origin when the antenna is elsewhere is a picture that looks right and is
  wrong. Our own VTU parser reads our own writer's output back as a
  cross-check. Mutation-tested seven ways, all caught.
- **`vtk_out.auto_radius_mm(extent_mm)`** — sizes a balloon against the geometry
  it sits beside. The fixed 100 mm is right for a patch and invisible inside a
  450 mm eight-element array.
- **`vtk_out.write_pattern_vtu(..., center_mm=...)`** — phase-centre
  registration. Defaults to the origin, which is where NEC2 patterns belong.
- **`vtk_out.show_pattern(...)`** — write-and-show in one call, so a dialog
  needs no overlay logic of its own. This is what keeps the tier split clean:
  the builder is free-side, only the wiring is Pro.
- **"Show pattern in 3-D view" in the Element Designer (free) and the Array
  Designer (Pro).** Enabled only once a Verify has actually produced a far
  field; the predicted array factor is not a pattern, and offering to draw it
  would show a balloon the solver never computed. Both are gated in gui_smoke,
  including that pressing the button early adds no object.

### Fixed
- **`SweepResult.resonances()` on a purely resistive load reported one
  "resonance" per sample** — 400 of them on a 401-point sweep, because every
  `Im(Z)` is exactly 0. `pdf_report` printed the first three into the report
  summary table, so a flat load produced **three fabricated resonances in a
  document the user hands to someone else**. A flat sweep now returns `[]`, and
  a run of consecutive exact zeros collapses to ONE crossing at its midpoint.
  The flat test is relative to the resistance, so a 1e-12 Ω residue on a 70 Ω
  feed still reads as flat. Five checks in `report_pdf.py`, mutation-tested
  three ways. `interpret.py` keeps its own guard as belt-and-braces.
- The Element Designer **discarded its verify result** — it built a text message
  and dropped the object. Retained now, which is what let the 3-D button exist.

### Decisions
- **`resonances()` fixed at the source, not per caller** (AJ, 2026-07-30). Two
  copies of the same guard would have let the next caller reintroduce the bug.
- **Caller-supplied function calling in CentralBrain's `/v1` stays UNGATED**
  (AJ, 2026-07-30). It relays a schema and returns `tool_calls` verbatim — the
  server executes nothing, so it is protocol compatibility, not a capability.
  Server-side MCP execution remains gated by `_mcp_licensed()`. Gating it would
  have coupled EMStudio Pro's agentic mode to CentralBrain's licence.
- **Overlay tier: builder free, array wiring Pro** (AJ, 2026-07-30). `vtk_out`
  already shipped free and single-element patterns are §1.
- **`rfdf_dialog` deliberately gets NO 3-D button** — it has no far field at
  all. Bearing curves and manifolds are not a radiation solid.

### Validation
- FAST battery **23 ok / 0 failed** in 44.3 s. smoke green ×3 (python3,
  freecadcmd 0.21.2, the Pro tree under 1.1.1); offscreen gui_smoke green on
  0.21.2 and on the Pro tree under 1.1.1. Free tree BUILT and grepped — the new
  gate exports and runs there, no new leak.
- 58 files under `tests/validation/` (57 gates + the runner), 38 GUI commands.

### Known
- The export post-steps are **still manual**, and the strip list has grown to 11
  Pro gate names in `run_battery.py` plus the matching/array/rfdf/assistant
  checks in `gui_smoke.py` and four command ids in `commands.py`. Every export
  leaves the free battery's tier audit failing until that is done by hand.
  Automating it in `export_free.py` is overdue.
- The openEMS runner does not record the NF2FF phase centre — the writer
  computes it and discards it — so dialogs pass a geometry-derived centre
  instead of the number the far field is actually referenced to. Persisting it
  is the correct fix and is not done here.

## [0.71.0] — 2026-07-27 — §7 System Designer S7: the System group, and the cumulative system report

Completes §7. Slices S1-S7 are done; the epic is closed.

### Added
- **A `System` command group.** Commands are now grouped by the question being
  asked: **Tools** designs ONE thing (element, cable, small antenna, link,
  coverage), **System** designs a system of them. The group spans the tier
  boundary deliberately — the free workbench gets the isolation matrix and
  co-site calculator, and EMStudio Pro adds matching, arrays and RFDF to the
  SAME group through the extension point, so a Pro user sees one coherent
  System menu rather than two disconnected ones.
- **`pdf_report.system_report()`** — the cumulative system deliverable. It
  **does not recompute anything**: each caller hands in a finished section, and
  the report renders it. That is deliberate — a system report that re-derived
  its own numbers could disagree with the dialog the user just read them from,
  and the user would have no way to tell which was right. Partial systems still
  produce a document (unknown keys are skipped, empty sections are labelled),
  but an EMPTY section list is refused: a system report with nothing in it
  looks like a complete design.
- Two gate checks for it, including the empty-list refusal and a section whose
  field key is absent.

### Validation
- Report gate green including the two new checks; smoke green on python3 and
  0.21.2; gui_smoke 37 commands green.

## [0.70.0] — 2026-07-27 — §7 System Designer S6 COMPLETE: RF direction finding

The RFDF dialog lands, completing slice S6 (its engine, digit gate and live
manifold gate shipped in 0.69.0). §7 is now S1-S6 done, S7 remaining.

### Added
- **RF Direction Finding dialog** (`emstudio/ui/rfdf_dialog.py`, command 37,
  Tools group) — four technique pages on one pinned bearing convention
  (compass azimuth, 0° = +Y, clockwise):
  - **Watson-Watt / Adcock** — the honest aperture ladder (ideal ≤ λ/8,
    small-aperture class < 0.2, hard ceiling λ/2) with the octantal spacing
    error **computed** from the exact crossed-pair response, and plotted
    against true bearing;
  - **Phase interferometer** — the λ/2 unambiguous limit, ambiguity count and
    lobe spacing per baseline, the **3.3σ patent criterion** on the long/short
    ratio (refused when too large), the σ_θ = λσ_Δφ/(2πd·cosθ) mapping plotted
    across scan angle, and the CRLB;
  - **Pseudo-Doppler** — ring sizing against spatial Nyquist, with the
    **"λ/3" rule stated where it actually belongs** (the ring's element
    spacing, not a Watson-Watt aperture — a common conflation), plus the
    modulation index and the demodulated tone;
  - **Correlative interferometer** — manifold conditioning and the degeneracy
    verdict, with **Verify** building the manifold LIVE from one NEC2
    far-field run per element and reporting what assuming ideal isotropic
    elements actually costs in bearing.
- **`rfdf.manifold_from_nec2()`** and **`rfdf.ring_positions()`** — the live
  manifold chain is now **engine code**, not gate code.

### Changed
- `tests/validation/rfdf_nec2.py` now calls the shipped
  `manifold_from_nec2()` for the shorted-neighbour case instead of its own
  copy of the chain. A gate that reimplements what it tests proves only that
  it agrees with itself. Same 12 checks, identical measured numbers.
- **CLAUDE.md documents a SPLIT INSTALL** (AJ's call): the 0.21.2 user dir
  keeps the dev symlink (live edits, gui_smoke), while the 1.1 user dir is
  left **empty on purpose** so its Add-on Manager can install EMStudio from a
  custom repository — the two FreeCADs use separate user directories, so
  development and the real distribution flow run side by side.

### Added — docs
- **`docs/ADDON_PUBLISHING.md`** — how EMStudio reaches the Add-on Manager,
  and a correction: the roadmap's "PR to FreeCAD/Addons" was **stale on two
  counts**. `FreeCAD/FreeCAD-addons` is legacy (FreeCAD < 1.0 only), and the
  current index at `FreeCAD/Addons` takes an **issue** ("Addon - Addition"),
  not a pull request. Includes the pre-submission checklist — the repo still
  needs the `freecad` and `addon` GitHub topics and a release tag, both
  outward-facing and left for AJ — and a draft submission.

### Validation
- gui_smoke **28 checks / 37 commands** green on FreeCAD 0.21.2 **and** the
  1.1.1 AppImage. The new RFDF check asserts behaviour, not just construction:
  λ/8 reads "ideal" and λ/2 reads "UNUSABLE"; a 4-ring at R = λ/2 flags
  DEGENERATE while a 5-ring does not; an 80:1 baseline ratio at σ = 20° is
  refused; Verify is enabled only on the page that has a live chain.
- smoke green on python3 + 0.21.2; FAST battery 20/20; `rfdf_nec2` 12/12 live.

## [0.69.0] — 2026-07-27 — Deployable build: About & Legal in-app, brand protection, a real icon set

The release that makes EMStudio fit to hand to someone. Three user-facing
changes — an in-app identity and legal notice, honest "under development"
signalling, and 38 purpose-drawn toolbar icons replacing five generic ones —
plus the §7 S6 correlative-DF manifold proven live on NEC2.

**Note on numbering:** §7 S6 was scheduled to ship as 0.69.0. Its engine, both
gates and the live manifold proof are here; the **RFDF dialog is not**, so S6
completes at 0.70.0 and this number went to the deploy work instead.

### Added
- **In-app About and Legal notice** — `EMStudio → Help → About EMStudio` and
  `→ Legal notice & disclaimer` (`emstudio/ui/about_dialog.py`, commands 35
  and 36). Both are always enabled, with no document open and no solver
  installed: a user must be able to reach the disclaimer from a cold start.
  About carries the version, development status, what the workbench is, how
  results are checked, the solver backends **with their own licences**, credits
  and the brand notice.
- **Once-per-installed-version first-run notice** on workbench activation —
  intended use, development status, the duty to verify, no-liability and the
  safety exclusion. Keyed on the version string, so it reappears after an
  upgrade and the terms travel with whatever was just installed. Non-modal, so
  it can never block activation.
- **Console banner on every activation** naming the version, the
  educational/hobbyist/experimental scope and the under-development status.
- **[TRADEMARK](TRADEMARK.md)** — full brand reservation. The code is
  LGPL; **EMStudio**, **AJJ³**, the logo/icon set and ajj3.us are not. Says
  plainly what needs no permission (use, nominative reference, unmodified
  redistribution) and what requires renaming (any modified redistribution),
  plus no-endorsement and third-party-marks sections. Flagged as a to-do in
  `docs/BUSINESS_MODEL.md` since the business-model pass; now written.
- **38 purpose-drawn SVG icons** — one per command, replacing a set of five
  generic glyphs shared across 34 commands. Drawn to a measured spec:
  content spans ≥54 of the 64-unit canvas (was ~44), primary strokes 5 units,
  and **no shape depends on the near-black ink** — rendered through FreeCAD's
  own Qt at 16/24/32 px on both themes, the old `#1a1a2e` structure
  *disappeared* on the dark theme (the port icon lost both pads, the workbench
  icon lost its mast).
- **§7 S6 live manifold gate** (`tests/validation/rfdf_nec2.py`, 12 checks) —
  the empty registered placeholder is now a real gate. Headline: a manifold
  built from five single-excitation NEC2 transmit runs **decodes a genuine
  receive simulation** (incident plane wave, short-circuit feed currents) with
  **0.00° bearing error and correlation 1.000000** — the chain is proven
  against physics, not against itself. Also pins, live: the exp(+j k p·û)
  phase convention (the conjugate hypothesis refuted 0.74 vs 0.19); NEC's
  `EX 1` angles as the **arrival** direction (the propagation reading is
  exactly 180° wrong); mutual coupling costing the ideal-isotropic assumption
  **1.78° worst / 1.24° rms**; the parabolic peak fit recovering off-grid
  bearings to 0.005° where the raw grid pick is out by 2.50°; and that a
  manifold belongs to the array **and its terminations** (shorted vs
  50 Ω-loaded columns correlate 0.946).
- **Four `parse_radiation_complex` checks in the FAST tier**
  (`system_rfdf.py`, now 37 checks) on a synthetic nec2c fixture — the
  function shipped in the S6 WIP commit with **zero** coverage.

### Fixed
- **`parse_radiation_complex` never terminated the pattern table.** nec2c's
  trailer line `DATA CARD No: 4 EN 0 0 0 0 0.00000E+00 …` yields 11 numeric
  tokens whose first two (4.0, 0.0) sit inside the theta/phi windows, so a
  spurious **all-zero row at theta = <card number>** was appended. On a
  single-theta azimuth cut that row sorted *first*, every manifold column came
  out all-zero, and `manifold_from_patterns` refused the lot. The sibling
  `parse_radiation_patterns` already carried the blank-line guard; the S6
  addition had dropped it. Found by writing the live gate.

### Changed
- Intended use is now stated first, everywhere: `DISCLAIMER.md` gains a §0
  (educational / hobbyist / experimental, and under active development) and a
  §10 (names and branding); `README.md`, `ABOUT.md` and every generated PDF /
  spec / BOM footer carry the same wording. All of it is composed from
  `emstudio/legal.py`, which is the single source of truth — the dialogs,
  report footers and markdown cannot drift apart.
- The degeneracy gate now pins the **failure mode** rather than an error rate.
  A noiseless decode does *not* expose a degenerate manifold (an exact
  measurement still picks the true one of a tied pair). Under a small 0.2 rad
  phase perturbation the degenerate 4-element ring **reverses — 180° worst
  error** — while the 5-element ring degrades gracefully at 3.7°. Measured
  across a noise sweep; the first version of this check compared gross-error
  *rates* and separated them by only 5 points.

### Validation
- smoke green on python3 and FreeCAD 0.21.2; gui_smoke **26 checks / 36
  commands** green, including a new About/Legal check that asserts the
  *rendered widget text* carries the intended-use, liability and brand
  wording — a silent regression there is a legal problem, not a cosmetic one.
- FAST battery 20/20; `rfdf_nec2` 12/12 live; `system_rfdf` 37/37.
- The new parser checks were mutation-tested: removing the table-termination
  guard fails 4 checks.

## [0.68.0] — 2026-07-26 — §7 System Designer S5: tapers, scan read-outs, 2-D arrays

The fifth §7 slice: amplitude tapers on the S4 drive chain, scan-behavior
read-outs, and 2-D array factors. Live-proven on NEC2: an 8-element
Dolph-Chebyshev ULA steered 20° off broadside lands its beam at exactly the
commanded angle and reproduces the **−26.02 dB Chebyshev floor to 0.04 dB**
(measured −26.06/−26.28/−26.21/−26.06) against the uniform control's
−12.7 dB — **13.4 dB of live suppression for 0.58 dB of peak gain.**

### Added
- **Taper synthesis** (`emstudio/system/tapers.py`):
  - **binomial** (Pascal rows) — zero INTERIOR sidelobes at every spacing
    (the classic "for d ≤ λ/2" caveat is imprecise: what grows above λ/2 is
    an end-fire shoulder, −40.8 dB at 0.6λ → 0 dB at 1.0λ), with the
    dynamic-range impracticality flagged (70:1 at N=9);
  - **Dolph-Chebyshev** by exact Schelkunoff root placement — N=10 R0=20
    reproduces the two-method-verified set 1 : 1.357047 : 1.970907 :
    2.482990 : 2.774537 with a flat −26.0206 dB floor, plus
    `d_max_over_lambda` (the design floor survives to d = 0.873 λ and is
    violated at the visible-region edge above). The API takes **either**
    `r0` (voltage ratio) or `sll_db` — they are DIFFERENT designs in the
    last digits, and both conventions are gated;
  - **Taylor n̄** by pattern-ZERO placement (Orfanidis `taylornb`) — chosen
    over aperture sampling, which lands 4–7 dB below design; zero-placed
    tracks the line source (N=33: −20.59/−20.26/−20.09 vs line-source
    −20.63/−20.29/−20.12 for n̄ = 3/5/8). Realized SLL ≠ design BY DESIGN —
    property-gated, per the de-risk's refutation of digit-gating;
  - `taper_metrics` — exact directivity/HPBW, realized SLL of the actual
    drive, aperture efficiency, dynamic range.
- **Scan read-outs**: 1/cos beam broadening (refuses end-fire), the exact
  two-arccos scanned HPBW (cross-checked against the S4 numeric-exact
  machinery to 0.006°), and `scan_loss_db` with the cos^q element exponent
  **exposed** — q is a modeling convention, not physics.
- **2-D array factors**: planar rectangular (direct double sum; separability
  onto two linear AFs gated to machine precision against an independent
  recompute) and the exact circular-ring sum with cophasal steering (the
  steered value equals Σ|I| exactly — gated to 1e-9).
- **Array Designer taper picker**: Uniform / Binomial / Dolph (SLL spin) /
  Taylor (SLL + n̄ spins) composing multiplicatively with the S4 named
  distributions; taper-efficiency and dynamic-range read-outs; a Dolph
  beyond-d_max warning; the cardioid locks the taper (its amplitudes ARE the
  distribution). **Export pattern CSV** saves the achieved far field in the
  format the §6 coverage tools load as an antenna pattern.
- **Validation gates**: `tests/validation/system_tapers.py` (FAST, 30
  checks, mutation-tested 12/12 — the wrong forms are kept as traps:
  binomial's exact 3.6571 vs the printed 3.958, Dolph's exact 2.7745 center
  vs Balanis's rounded 2.798, and a pin that FAILS any implementation faking
  "Taylor SLL == design") and `tests/validation/array_taper_nec2.py`
  (SOLVER: the live Dolph-vs-uniform steered ULA, with sidelobes measured at
  actual lobe maxima in γ-space — a φ-space search finds the beam's own ±φ
  mirror at 0 dB, and an angular exclusion window around the beam clips its
  own skirt and reports that as the floor).

### Fixed (adversarial review — 24 findings raised, 24 confirmed, all fixed)
- **Taper efficiency was computed on the STEERED currents** with the
  coherent-sum numerator |ΣI|², so any scanned or end-fire drive with a taper
  displayed nonsense in the Array Designer — a Dolph-tapered end-fire array
  read **"−120.00 dB gain cost"**. Taper efficiency is a property of the
  amplitude distribution: the numerator is now (Σ|I|)², verified against the
  ground truth D_tapered/D_uniform (0.8925 at every steering).
- **`taper_metrics` raised out of the dialog's read-out path.** It guarded the
  sidelobe lookup but not the beamwidth, and `hpbw_exact_deg` raises for the
  same too-flat patterns (47 reachable N/spacing/taper combinations, including
  the default 4-element binomial at 0.1 λ). Both metrics now degrade to
  ``None``, and the dialog's metrics block is guarded — an unavailable number
  can no longer abort the Qt slot and strand the pane on the *previous*
  array's figures.
- **The live gate measured the main-beam skirt, not the sidelobe floor.** A
  ±25° exclusion window around the steered beam clipped its own skirt and
  reported −24.3 dB, which the gate then explained with a fabricated "real
  elements and coupling cost ~1.7 dB". Measuring at actual lobe maxima shows
  the truth is better: **−26.06/−26.28/−26.21/−26.06 dB against the analytic
  −26.02** — the taper does on coupled dipoles what it does on paper.
- **Export pattern CSV stayed armed after the design changed**, so editing N,
  spacing or the taper and exporting silently handed the §6 coverage tools the
  *previous* array's far field. Any design edit now clears the Verify result
  and disarms the button.
- **Dolph/Taylor root synthesis returned garbage past ~55 elements** —
  `np.poly` loses precision on many unit-circle roots and the final `abs()`
  actively masked the sign-flipped result. Both now verify symmetry and
  positivity and refuse. Also: `binomial_taper` overflowed silently past
  n ≈ 1030 (now capped at 64), `circular_array_factor` silently ignored
  `steer_phi_deg` without `steer_theta_deg` (now refused), the SLL/n̄ spins
  were editable while the taper was Uniform, and the scanned-HPBW guard blamed
  "near end-fire" for an array that was merely too short.
- **Gate gaps closed** (`system_tapers` 30 → 38 checks): the efficiency
  numerator, `sll_db`, planar `alpha_x`/`alpha_y` steering, the circular
  `currents` argument, the Taylor revert-boundary (a `k < n̄−1` off-by-one
  moved the currents 4.3 % while the realized-level pins moved 0.04 dB — now
  pinned by NULL PLACEMENT), and the np.poly conditioning guard all had zero
  failing coverage. `gui_smoke` never touched the SLL/n̄ spinboxes, so a
  hardcoded value would have passed. Re-mutation-tested: 10/10 caught.

## [0.67.0] — 2026-07-26 — §7 System Designer S4: multi-excitation + array drive

The fourth §7 slice: NEC2 multi-excitation and the phased-array drive chain.
The pinned §7 design rule is now enforced end-to-end — arrays specify element
CURRENTS, NEC2 EX cards drive VOLTAGES, so the chain is mutual-impedance
matrix (the shipped §5 isolation machinery) → V = Z·I → ONE multi-EX verify
run. Measured on the shipped pair geometry: cardioid front-to-back **29.6 dB**
via the current solve vs **3.4 dB** for the naive equal-voltage drive — the
26 dB that justifies the slice. De-risked by a 6-agent recon + 3-agent
independent anchor recompute (12 Phase-C corrections banked in the anchors
doc §5), then hardened by a 4-dimension adversarial review.

### Added
- **NEC2 multi-excitation** (`solvers/nec2/writer.py`): one EX card per
  excited port in PortNumber order via `build_wire_model_multi()`. A
  single-port unity-drive analysis produces a **byte-identical** historic deck
  (the frozen-deck gate compares text). Refused outright: a 0 V excited port
  (nec2c silently rewrites a zero-volt EX card to 1 V — verified live), two
  ports on one wire edge, and duplicate edge references under multi-excitation
  (the Z-extraction path dedupes; the decks must agree on GW numbering).
- **`Amplitude` / `PhaseDeg` on `EMLumpedPort`** — drive voltage per port,
  added in `_ensure_properties` so documents saved before v0.67.0 upgrade on
  load; defaults reproduce the historic unity drive. Exact 90° phases snap
  the cosine float noise to a clean 0 in the deck.
- **`parser.parse_port_impedances()`** — every port row of every ANTENNA
  INPUT PARAMETERS block (a multi-EX run prints one per excited port), keyed
  by TAG because the printed SEG column is GLOBAL while EX cards address
  tag + local segment. `parse_output()` is untouched: six shipped gates
  depend on its first-row-only contract.
- **The array drive engine** (`emstudio/system/array_system.py`):
  - analytic tier — ULA array factor, steering (broadside / end-fire both
    ways / Hansen-Woodyard `−(kd + 2.94/N)` / scanned), **EXACT directivity**
    (visible-region numeric peak over the closed double-sum average — the
    `|Σaₙ|²` shortcut is 81× wrong for a 45°-scanned array), exact numeric
    HPBW, grating-lobe guard, first-sidelobe level, the induced-EMF mutual
    impedance of parallel λ/2 dipoles, and pattern multiplication onto a
    measured element pattern;
  - live tier — `drive_array()`: mutual-Z at the design frequency (passed
    explicitly; the isolation default is the sweep stop), wire-direction
    sign normalization (an element drawn upside-down otherwise radiates
    ENDFIRE with every isolation metric looking fine), `V = Z·(s∘I)`, one
    multi-EX deck built from the SAME wire model as the Z-extraction decks
    (mismatched segmentation caps a broadside null at −47 dB) with a GW-line
    tripwire, achieved-vs-target currents, per-port active impedance and
    power split with negative-power warnings, and the far field PINNED at
    the design frequency (an array is unmatched by definition — min-S11
    frequency selection is meaningless).
  - `solve_drive()` warns on a NEGATIVE driving-point resistance
    (superdirective drive — no passive splitter/phaser can realise it).
- **Array Designer dialog** (`emstudio/ui/array_dialog.py`, command
  `EMStudio_ArrayDesigner`, 33→34): linear array of parallel dipoles with
  NAMED drive distributions (broadside · end-fire · Hansen-Woodyard · scanned
  · cardioid pair), the derived per-element target-current table, predicted
  exact-directivity / HPBW / sidelobe / grating-lobe read-outs, and a live
  **Verify** — transient N-dipole document, N+1 NEC2 runs off-thread,
  achieved-vs-predicted azimuth cut overlay plus the drive table (EX
  voltages, active impedances, per-element power). Per-element tapers
  (binomial / Dolph-Chebyshev / Taylor n̄) are the S5 slice.
- **Validation gates** (both wired into the battery tiers):
  `tests/validation/system_arrays.py` (FAST) pins the S4 de-risk's CORRECTED
  Phase-C anchors — HW directivity 17.9565 (not the printed 17.89), end-fire
  HPBW 69.419° exact / 69.249° closed-form (the flawed small-angle form's
  48.22° is gated as a trap — off by exactly √2), first SLL −12.966 dB at
  N=10, mutual-Z at six spacings with the d→0 j42.139-not-j42.211 trap —
  plus the drive-solve identities and 12 input guards. Mutation-tested: 10
  deliberate engine breakages, 10 caught. `tests/validation/array_nec2.py`
  (SOLVER) runs the live chain: Z pinned to the digit, currents at the 1e-4
  print floor, NEC-vs-analytic AF to 0.03 dB, the λ/2 axis null at
  −82.05 dBi RAW (88 dB contrast, read from the .out because FarFieldResult
  clips at −60), the wire-direction trap, cardioid 29.57 vs 3.35 dB, and
  reciprocity as a RELATIVE bound (an absolute 1e-6 only ever passes by
  mirror symmetry).

### Fixed
- **`system/network.py` silently truncated N-port matrices**: every 2-port
  conversion read only the top-left 2×2 of whatever it was given, so a 3-port
  Z produced plausible, wrong S-parameters. `_unpack` now refuses non-2×2
  input (N-port conversions live in `cosite.isolation.z_to_s`).

### Fixed (adversarial review — 25 findings raised, 24 confirmed, all fixed)
- **The Array Designer's cardioid read-outs were wrong away from λ/4.** The
  quadrature pair is only a cardioid at d = λ/4, but the dialog printed "beam
  toward the lagging element, null behind" and a broadside grating limit of
  1.0 λ at *every* spacing — including its own 0.5 λ default, where the
  front-to-back ratio is actually 0 dB and the beam sits 60° off the axis.
  The note is now spacing-aware (it states the true beam angle and the lost
  null), and the cardioid's grating limit is its real 0.75 λ.
- **The first-sidelobe read-out ignored the steering**, reporting the
  broadside table for every distribution — flattering a Hansen-Woodyard array
  by 3.4 dB (−12.97 shown vs −9.61 dB real). New `first_sidelobe_of()`
  computes it from the actual currents; `first_sidelobe_db()` keeps the
  broadside-table contract.
- **The Array Designer's wire-radius control was silently ignored** — every
  Verify ran on 1 mm wires regardless of the value shown, so the mutual-Z,
  drive voltages, active impedances and powers were all for the wrong
  conductor.
- **A grating lobe exactly at the visible-region edge read as "lobe-free"**
  (end-fire at the default 0.5 λ, broadside at 1.0 λ) — now reported as its
  own case rather than by an inequality that excluded the boundary.
- **A very short array blanked the whole predicted panel.** With no 3 dB
  crossing the HPBW raises, which discarded the directivity, sidelobe and
  grating read-outs too; each line is now computed independently.
- **`_port_drive` accepted a non-finite drive** — NaN slips past the
  zero-volt guard, and nec2c parses `nan` as 0 V and then silently rewrites
  it to 1 V, which is exactly what that guard exists to prevent. Its
  quadrature float-noise snap also used the signed amplitude, so it never
  fired for a negative (180°-equivalent) amplitude.
- **`drive_array` validated its arguments after the N solver runs** and
  accepted `f_hz <= 0`, on which nec2c spins forever — a bad call could burn
  every run's 1200 s timeout. All argument checks are now front-loaded, per
  the `matching.py` refuse-early contract.
- **The GW-consistency tripwire silently disabled itself** when the
  Z-extraction deck was missing, instead of refusing — the module documents
  that tripwire as its defense against a segmentation mismatch.
- **Gate gaps closed** (`system_arrays` 41→50 checks): the back half of the
  visible region (90–180°) was completely unpinned, so truncating the peak
  search to [0,90] passed the entire gate while breaking both dialog-reachable
  back-half beams; `endfire_back` had zero coverage anywhere (its sign is
  invisible to directivity and beamwidth, which are mirror-symmetric);
  `cond_z`, the anti-resonant voltage warning, `drive_summary_text` and the
  pre-v0.67 legacy-port fallback were all unfalsifiable. `gui_smoke` also
  carried a literally-tautological `assert … or True`. Every new check was
  mutation-tested — 10 deliberate breakages, 10 caught.

### Changed
- The drive table is plain ASCII (`|I| (A)  ph (deg)`) — it is echoed to the
  FreeCAD console, where the previous `∠`/`°` were the repo's only occurrence.

## [0.66.1] — 2026-07-26 — validation battery runner + CI + NumPy 2.0 fix

### Added
- **`tests/validation/run_battery.py`** — one command for the regression net
  that previously required typing 17 paths by hand. Default = the FAST tier
  (17 solver-free gates, ~40 s, pure python3 + numpy/scipy/matplotlib);
  `--all` adds the 31-gate SOLVER tier (nec2c/openEMS/Elmer/Palace/FastHenry,
  the pre-release battery); `--list` shows the tiers. A tier audit refuses to
  start if any `tests/validation/*.py` file is missing from both tiers, so a
  new gate cannot be silently left out. Gates whose local data is absent
  (the ITU digital maps are integral products, never bundled) SKIP with a
  printed reason instead of failing.
- **GitHub Actions CI** (`.github/workflows/ci.yml`): python3 smoke + the FAST
  battery on every push/PR, Linux runners only (free for the public repo; no
  macOS jobs by design). p452/p2001 skip in CI (no ITU maps there); they still
  run in the local battery.

### Fixed
- **The vendored ITU-R P.1546 reference implementation failed on NumPy ≥ 2.0**
  (`np.mat` was removed in the 2.0 release), breaking the P.1546 engine and
  its gate on any modern NumPy — invisible on the dev machine's 1.26.4 and
  caught by running the new battery in a clean NumPy 2.5.1 venv. The two call
  sites now use `np.asmatrix`, NumPy's documented drop-in alias; change notice
  in `emstudio/vendor/py1546/PROVENANCE.md`. Verified by replaying the
  official WP3K validation set at 0.000000 dB worst error under BOTH NumPy
  1.26.4 and 2.5.1. No other NumPy-2.0-removed API is used anywhere in the
  repo (audited).

## [0.66.0] — 2026-07-26 — §7 System Designer S3: filter + diplexer synthesis

The third §7 slice: closed-form lumped filter and diplexer synthesis on the
frozen S1 network core. Engine + digit gate only — no new GUI command (the
count stays 33), the same shape as S1. Anchors were re-verified anchors-first
by a 5-agent independent recompute before the build, then the slice was
hardened by a 4-dimension adversarial review (27 findings, 21 confirmed after
independent refutation, all fixed).

### Added
- **Filter/diplexer engine** (`emstudio/system/filters.py`): Butterworth
  g-coefficients (closed form) and Chebyshev g (recursive closed form,
  including the even-order `coth²(β/4)` termination); attenuation and minimum
  order for both; the lowpass→bandpass and lowpass→bandstop frequency
  transforms on the geometric-mean centre, so every transformed arm resonates
  exactly at the band centre; lowpass/highpass ladders; `response` through the
  S1 ABCD core; the contiguous constant-resistance diplexer (a
  singly-terminated Butterworth exact-dual pair whose composite common-port
  impedance is R0 at every frequency); the non-contiguous UVSJ band-splitting
  diplexer; and a 3-port nodal `diplexer_sparams` solver.
- **`prototype_load_ohms`** — the load an even-order Chebyshev ladder actually
  requires (`R0·g[n+1]` series-first, `R0/g[n+1]` shunt-first), and
  **`response(..., z_load=)`** to evaluate against it.
- **`chebyshev_3db_hz`** — the 3.01 dB frequency of a Chebyshev whose ripple
  band edge is `fc`, because passing a "3 dB cutoff" spec straight in as `fc`
  is the classic convention error (1.167× for n=3 at 0.5 dB ripple).
- **Validation gate** `tests/validation/system_filters.py` (35 checks, pure
  python3, seconds). Reproduces every Phase-B anchor with the §5 audit
  corrections applied: bandpass 55.5 nH / 0.0800 pF at ω0 = 2.388 GHz;
  Chebyshev T_n(2) = 196.51 → N = 5; the contiguous N6RK LP shunt C = 424.4 pF;
  the bandstop anchor digits 795.8 nH / 3.183 pF / 15.92 nH / 159.2 pF; and
  constant-R |Zin − 50| < 1e-6 Ω at every prototype order n = 1..7. Every new
  check was mutation-tested — eight deliberate breakages of the engine, eight
  caught.

### Fixed (all found by the adversarial review, before any of this shipped in a UI)
- **The singly-terminated Butterworth prototype rows n=4, 6 and 7 carried
  transcription errors** from the 5th significant figure. Regenerated as the
  exact Cauer expansion of Bₙ(s) at 50 digits; the corrected n=7 row now
  reproduces the HA8ET printed values to all five printed decimals. The wrong
  digits had degraded the documented constant-resistance property to 3.3e-3 /
  1.4e-3 / 1.6e-2 Ω — all past the gate's own 1e-3 tolerance, invisible because
  only n=3 was ever built.
- **Even-order Chebyshev ladders were built for one load and evaluated against
  another.** `chebyshev_g` returned the `coth²(β/4)` term correctly, but every
  consumer discarded it and `response` terminated both ends in Z0, misreporting
  a 0.5 dB-ripple n=4 design as **1.81 dB** (1.312 dB error).
- **Evaluating a bandstop filter at its own notch centre raised
  `ZeroDivisionError`** — the single most natural query of a notch, and an
  exact degeneracy because the transforms set L·C = 1/ω0² to the last bit.
  Ideal open/short arms are now handled in the limit: infinite rejection with
  total reflection.
- **The non-contiguous diplexer synthesized the wrong branch prototype.** Two
  independently-designed doubly-terminated ladders paralleled at a common node
  load each other (each presents |Z| ≈ R0 out of band, not an open), giving
  1.67 dB assembled loss at VSWR 3.6 — with a structural floor of ~1.69 dB
  across every cutoff pair, so it could never reach the measured builds the
  anchors cite. Branches are now synthesized from the **singly-terminated**
  prototype by default: **0.112 dB assembled at VSWR 1.38** with 34.8 dB
  isolation. `prototype="doubly"` is retained for comparison. The docstring's
  claim that per-branch loss equals the branch's own passband loss was false
  and is corrected.
- **`filters.py` validated no input at all**, against the sibling `matching.py`
  contract of refusing an impossible request. It now raises on a non-positive
  or non-integer order, non-positive ripple, an unmeetable order spec (As ≤ Ap,
  or a stopband below the ripple), swapped band edges (which silently produced
  negative L and C whose response curve is numerically identical to the correct
  filter), `bw_frac ≥ 2`, non-positive frequencies or resistances, an
  unrecognised `first` string (which silently built the dual ladder — a
  different BOM), an unknown arm topology, overlapping diplexer passbands, and
  an unknown prototype name.

### Changed
- Three anchor corrections recorded in
  `docs/upstream/system-designer-anchors.md` §5 (non-contiguous branch
  prototype; the singly-terminated table digits; the even-order Chebyshev load
  mapping). These supersede the Phase-B wording.
- `response` now documents that elements are ideal — the reported insertion
  loss is a lossless ladder's reflective loss, not a build's dissipative loss.
  A finite-Q path (the S1/S2 honesty feature) is a future addition.

## [0.65.1] — 2026-07-21 — fix: dialog crash from a Qt method-name collision

### Fixed
- **The Coverage and Multi-station dialogs crashed FreeCAD** when browsing for a
  terrain (DEM) file. Root cause was a Qt method-name collision, NOT the file
  dialog: `self.metric = QComboBox()` shadowed the inherited
  `QPaintDevice.metric()` that Qt calls on every repaint, so opening the
  file-browse dialog (which forces a repaint) tried to call the combo as a
  function → `TypeError: 'QComboBox' object is not callable` → SIGSEGV (crash in
  `QWidget::initPainter` → `QFont(QPaintDevice)` → `metric()`). Renamed the
  attribute to `self.metric_combo` in both dialogs.
- Added `tests/validation/ui_attr_collisions.py`, a static gate that fails if
  any `emstudio/ui/` widget attribute shadows an inherited Qt method name —
  gui_smoke misses this class of bug because it constructs dialogs but never
  paints them.

## [0.65.0] — 2026-07-21 — §7 System Designer S2: Matching Designer dialog + live verify

The second §7 slice puts a GUI on the S1 matching engine: the **System
Matching Designer** dialog (32→33 commands). Consumes an element as an
impedance, synthesizes a matching network, shows predicted vs achieved
performance, and exports a report. De-risked by a 5-agent reconnaissance of
the dialog/command/NEC2/PDF/gate patterns, then hardened by a 3-dimension
adversarial review whose 9 confirmed findings were all fixed.

### Added
- **System Matching Designer dialog** (`emstudio/ui/matching_dialog.py`,
  command `EMStudio_SystemMatching`): element source (typed R+jX or a live
  NEC2 sweep of a document antenna), a topology picker with a deterministic
  recommender, predicted VSWR / return-loss / insertion-loss curves, a
  component schedule with E-series (E6/E12/E24/E96) standard-value snap, a
  PDF report, and a Verify that re-sweeps the element live and plots the
  ACHIEVED match against its real Z(f).
- **Matching engine additions** (`emstudio/system/matching.py`): a
  `synthesize()` dispatcher over every topology; element-based designs for the
  distributed transformers/stub (`quarter_wave_design` / `binomial_design` /
  `single_stub_design`); `evaluate_swept` (frequency-dependent element load);
  the topology recommender (`recommend_matching` + `matching_summary_text`);
  and E-series snapping (`nearest_e_series` / `snap_to_e_series`).
- **`matching_report`** (`emstudio/report/pdf_report.py`): a two-page design
  report (summary + predicted curves + schematic + component/section schedule).
- **Gates**: the digit gate grows to 77 checks (recommender, E-series,
  dispatcher, distributed designs, swept eval); a `_system_matching_dialog`
  gui_smoke check (offscreen, both FreeCADs); a matching-report block in the
  report gate (one PDF per topology + snapped + through); and a live
  `tests/validation/system_match_nec2.py` — ingest the shipped 300 MHz dipole
  (71.9 Ω), match it to 50 Ω, and confirm the achieved VSWR (1.010 vs the bare
  antenna's 1.434).

### Fixed (from the S2 adversarial review)
- **`synthesize()` no longer discards load reactance** for the real-load-only
  topologies (pi / T / quarter-wave / binomial / hairpin) — it now RAISES on a
  reactive element instead of silently reporting a false perfect match; the
  dialog surfaces the refusal and L-match / single-stub (which absorb reactance)
  are recommended instead.
- E-series snapping now rolls over the top of a decade (9.7 → 10, not 9.1) and
  keeps the schedule's reactance consistent with the snapped component value;
  editing any primary dialog input now recomputes live; a failed synthesis
  clears the plots; and `evaluate`/`evaluate_swept` handle generators and reject
  a frequency/load length mismatch.

## [0.64.0] — 2026-07-21 — §7 System Designer S1: network core + matching engines

The first build slice of the §7 System / Sub-system Designer epic — the
linear two-port network core and the impedance-matching synthesis engine.
Engine + digit gate only (the dialog is S2); no new GUI command yet.
De-risked anchors-first (a 7-agent independent re-verification of the
Phase-A anchor set) and hardened by a 4-dimension adversarial review whose
19 confirmed findings were all fixed — including a real physics correction
to the pi/T insertion-loss model.

### Added
- **Two-port network core** (`emstudio/system/network.py`): the cascadable
  ABCD primitive with S / Z / Y conversions (real-Z0 traveling-wave S),
  series/shunt/transmission-line builders (lossless and lossy), finite-Q
  lumped elements (series-R model), input impedance, VSWR / return loss /
  mismatch loss, and both transducer and dissipation insertion loss. Every
  identity holds to machine precision (det = 1, S↔ABCD round-trip, lossless
  ⇒ unitary S, cascade associativity).
- **Impedance-matching synthesis** (`emstudio/system/matching.py`):
  - **L-match** — both lossless forms via a direct conjugate-match solve
    that handles complex terminations exactly (presents `conj(Z_source)` by
    construction); the L-network Q is fixed by the resistance ratio.
  - **pi / T-match** — chosen-loaded-Q designs decomposed through a virtual
    resistance (pi below, T above both terminations).
  - **Quarter-wave** and **binomial** (maximally-flat, ln-recursion)
    multisection transformers with honest bandwidth.
  - **Single-stub** shunt tuner (open/short, both solutions), **hairpin**
    (exact L-match) and **gamma** match (flagged empirical starting point),
    a rule-based **balun type picker** (plus the half-wave 4:1 and Guanella
    section-impedance identities), and a topology-correct finite-Q
    **insertion-loss** estimator.
- **Validation gate** `tests/validation/system_matching.py` (59 checks,
  python3): the re-verified Phase-A anchors to the digit, with the §5 audit
  corrections applied (quarter-wave `gamma_m` 8.17 % vs 9.0 %; binomial N=5
  gated against the ln-recursion row, not the doc's exact-synthesis row),
  conjugate-match-by-construction for complex terminations, and an
  end-to-end cross-check that the network dissipation equals the closed-form
  insertion loss.

### Fixed
- **pi/T insertion loss** now uses the correct sum-of-section-Q dissipation
  (`estimate_insertion_loss_db`, exact via the rebuilt lossy network); the
  single-loaded-Q closed form under-predicted pi/T loss by 20–35 % and is
  now documented as exact only for a 2-element L-section. Correction
  recorded in `docs/upstream/system-designer-anchors.md` §5.
- Edge-case hardening from the adversarial review: pi/T reject complex
  (non-pre-resonated) terminations and the `Q == Q_min` degeneracy (was a
  0 F-capacitor crash); L-match returns a single "through" for already-
  matched ports and labels form from both element kinds; single-stub emits
  both solutions when `Re(Z_L) = Z0`; and the core conversions raise clear
  `ValueError`s instead of leaking `ZeroDivisionError` on degenerate inputs.

## [0.63.0] — 2026-07-20 — §4 Watt breadth UNBLOCKED: top-loading, radial grounds, voltage-limited design

The long-blocked §4 breadth shipped the day the reference PDF arrived —
every constant verified from the PAGE IMAGES (the OCR text layer is bad)
with exact-identity cross-checks, and the whole 728-page book scanned and
triaged for everything else applicable
(`docs/upstream/watt-topload-anchors.md` + `watt-scan-map.md`).

### Added
- **Top-loading capacitance engine** (`emstudio/antenna/topload.py`): the
  classic verified set — plate hat + fringe (8.85·A_eff/h, reproduced the
  five internally-consistent Brown scale models within 0.5 % and exposed
  TWO typos in the book's own table), single horizontal/vertical wires
  with the end-effect k/k′ tables (24.16 = 2πε₀/ln10 exactly), flat-top
  of n wires with the k_n proximity table + validity flag (the n = 2
  special form matches at machine precision), inverted-L and T composites
  with the bilinear X mutual table, vertical-plane curtains, wire-to-wire
  C, an air-coax identity that cross-gates against the §2 TEM engine, the
  umbrella landmarks (max h_e at guy-insulator ratio ≈ 0.35; ratio 0.7 →
  ×8 power / ×3 bandwidth), and the Laport-trapezoid effective height
  h_e = h(1+r)/2, r = C_hat/(C_hat+C_mast).
- **Radial-ground-system estimator**
  (`emstudio/antenna/ground_system.py`): H-field zone integrals over a
  radial screen (regions ρ<h and h<ρ<λ/2π; grid surface resistance
  ∝ ρ²N⁻²f^{3/2}σ^{1/2}, bare earth √(πfµ₀/σ); 0.366 = ln10/2π and
  3.66×10⁻⁷ constants exact), with the grid-vs-earth CROSSOVER radius so
  screens are only credited where they beat earth (monotone in N, screen
  radius and σ — including the honest sea-water result), plus a
  wire-economy `optimize_radials` that reproduces the classic
  N ≈ 100-150 optimum flavor. E-field/base losses documented as not
  included (the follow-up map has the verified formulas).
- **Voltage-limited design set** (`small_antenna.voltage_limited`): the
  VLF power-capability physics — P_r = 640π⁴/c₀²·V²C²h_e²f⁴ (printed
  6.95×10⁻¹³), 3-dB bandwidth 320π³/c₀²·h_e²f⁴C/η (printed 1.11×10⁻¹³),
  P·b product, shunt-ΔC effects (h_e and antenna-only bandwidth shrink
  by C/(C+ΔC); resonated P_r unchanged), f<f_r/2 honesty warning — all
  coefficients derived exactly and pinned against the printed
  conventions.
- **Efficiency ladder** (`small_antenna.efficiency_ladder`): the
  canonical η_a / η_as / η_ts chain over R_r + R_sd + R_c + R_g (+ coil
  + transmitter), the Q(η=1)/bandwidth floor pair, and a plausibility
  warning (real VLF systems run ~10-70 %); gated against two anonymized
  measured (h_e, f) → R_r pairs. **Experimental h_e utility**
  (`effective_height_from_field`): the standard field-measurement
  determination, exact inverse of the 300·√P/d field identity.
- **Small-Antenna Designer "Top loading & ground" tab**: hat type
  (flat-top/T/inverted-L/plate), radial screen (N, radius, four earth
  presets), voltage limit → C, trapezoid h_e, R_r, R_g (vs bare earth),
  efficiency, voltage-limited P_r/bandwidth, with every validity warning
  surfaced.

### Validation
- `tests/validation/small_antenna.py` grows ~45 checks across four §4
  tiers: the five Brown-model reproductions, exact-constant identities,
  table continuity, the two-wire special form, T-vs-L ordering, ground
  monotonicity + the 0.1436 Ω regression pin + the scope guard, exact
  voltage-limited coefficients + the machine-precision P_r identity, the
  measured R_r pairs, ladder identities and both honesty warnings.
  gui_smoke exercises the new tab (both FreeCADs green).
- The full-book scan (15 readers over all 728 pages + synthesis, one
  46-page gap noted) produced the triaged follow-up map with verified
  formulas + anchors for the next §4 items (E-field ground term, corona
  checker, umbrella curve families, sizing advisor, Austin-Cohen) — see
  `docs/upstream/watt-scan-map.md`.

## [0.62.0] — 2026-07-19 — Element Designer E6: service presets + PDF build reports (§1 EPIC COMPLETE)

### Added
- **20 verified service presets** (`emstudio/antenna/service_presets.py`):
  FM/AM broadcast, NOAA weather, airband, marine VHF, the ham bands
  80 m/40 m/20 m/10 m/6 m/2 m/70 cm, CB, 433 ISM/SRD, LoRa 868 (EU) /
  915 (US), Wi-Fi 2.4/5 GHz, GPS L1 (RHCP), ADS-B 1090. A **Service
  preset** combo in the Element Designer auto-fills the requirements
  schema (frequency/band-top/polarization/pattern) and surfaces the
  design note + regional variants. Narrow services fill a spot frequency
  (geometric band centre); wide ones fill the band. Every band edge was
  verified from authoritative sources (FCC eCFR, ITU RR, ETSI, ARRL) by
  a three-agent verification pass + an adversarial full-table audit —
  provenance in `docs/upstream/service-presets-anchors.md`.
- **Element Designer PDF build reports** (`element_report` in
  `emstudio/report/pdf_report.py` + a **PDF Report…** button): a
  two-page build-house deliverable for any of the four design families —
  design-summary table, every warning/caveat spelled out, a dimensioned
  build sketch, and the element schedule (per-element positions/lengths;
  Yagi carries both bare-wire and metal-boom cut lengths). The standard
  engineering disclaimer travels on every page.
- **Loading flag up front** for reactive λ-fraction verticals: the
  predicted-performance read-out now leads with ">>> LOADING REQUIRED"
  when the selected fraction is not resonant (matching is §7).
- **Honest tier note** (HELP/USER_MANUAL): everything shipped in the
  Element Designer is part of the free core and stays free; a future Pro
  tier (optimizer, exotic families, AI intent) comes via the AJJ³
  project.

### Validation
- `element_designer.py` grows a **preset tier** (~70 checks): row
  integrity, unique keys, spot-vs-band routing (geometric-centre f0 in
  band), every preset normalizes + recommends an AVAILABLE family,
  AM-broadcast→small-antenna routing pin, GPS CP/RHCP pin, KeyError +
  determinism. `report_pdf.py` renders element reports for all four
  families + the monopole sketch branch. `gui_smoke.py` exercises the
  preset combo (band fill, spot fill, region note) and the headless
  report path. Still 23 checks / 32 commands, green on 0.21.2 + 1.1.1.

## [0.61.0] — 2026-07-19 — Element Designer E5: LPDA (Carrel) — all five core families shipped

### Added
- **LPDA synthesis engine** (`emstudio/antenna/lpda.py`, ELEMENT_DESIGNER_PLAN
  slice E5 — the LAST core family): the Carrel (1961) design equation set —
  τ/σ geometry, the optimum-spacing line σ_opt = 0.243τ − 0.051,
  cot α = 4σ/(1−τ), active-region bandwidth B_ar = 1.1 + 7.7(1−τ)²cot α,
  structure bandwidth, element count with the documented ARRL rounding rule,
  element lengths/positions (l₁ = λ_max/2, τ-scaled), boom length, and the
  feeder design Za/σ′/Z0 chain for a target mean input resistance. Gain uses
  the **Butson-Thompson CORRECTED contour calibration** (Carrel's original
  labels read 1 dB high) with the documented h/a thickness sensitivity
  (−0.2 dB per doubling vs the charts' h/a = 125). Every equation verified
  from primary/open sources (the original Carrel paper scan, ARRL,
  Stroobandt, SDSMT + the official Balanis companion materials) — full
  provenance in `docs/upstream/lpda-carrel-anchors.md`.
- **`EMStudio::TransmissionLine` document object**
  (`emstudio/objects/transmission_line.py`): an ideal non-radiating line
  between two wire edges (Z0, Crossed, auto/explicit length, optional shunt
  admittances). The NEC2 writer emits it as a **`TL` card** between the
  wires' center segments — `Crossed = True` uses NEC2's negative-Z0
  crossed-line convention (primary-source-confirmed from the official NEC-2
  User's Guide + the nec2c source; nec2c labels the lines `CROSSED`).
  Analyses without TL objects produce **byte-identical decks**. The §7
  System Designer will reuse this object for general feed networks.
- **`makeLPDA` template** (`emstudio/templates/lpda.py`): N dipoles along
  the boom + the crossed-feeder TL chain + feed on the shortest element +
  a band-spanning sweep. No resistive rear termination (live-measured: it
  flattens the low edge but absorbs ~1.7 dB of low-edge gain).
- **LPDA family in the Element Designer dialog**: a shared **Band top
  (f_hi)** requirements input (also unlocks the recommender's wide-band
  rule), design by gain target (corrected contours) or explicit τ/σ, target
  R0, predicted read-out + schematic, **Verify with NEC2** (band VSWR
  statistics vs R0 + far field pinned at the geometric band centre), and
  Accept → Generate. The recommender's LPDA family is now **available** —
  all five §1 core families are shipped.

### Validation
- `tests/validation/element_designer.py` grows an **LPDA digit tier** (35
  checks): BOTH official worked-example chains for the classic 54-216 MHz
  design (printed σ 0.157: α 12.13°, B_ar 1.753, B_s 7.01, N 14.43, boom
  5.541 m; companion-code σ 0.158: 4.681/1.757/7.03/14.45/5.573-5.577 m),
  the Balanis feeder chain to the digit (Za 327.88 Ω, exact Z0 55.96 Ω),
  the corrected gain contours (8 dBi ↔ τ 0.865; the σ = 0.06 crossings;
  the +1.0 dB original-calibration identity), machine-precision structural
  identities (τ-scaling, d_n = 2σl_n, the boom-span Σd identity), the
  N-rounding rule both ways, and error honesty.
- **New live gate `tests/validation/lpda_nec2.py`** (freecadcmd + nec2c,
  ~1-2 min) through the PRODUCTION writer: 41-point band sweep — median
  VSWR(65) < 1.5 (ref 1.215), ≥80 % of points under 2.0 (ref 92.7 %; three
  narrow documented low-end "weak spot" spikes, worst 6.0), band mean R
  65 ± 10 Ω (ref 60.7 — the Za-convention anchor); spot far fields at
  60/120/200 MHz (ref 8.29/8.84/8.54 dBi ± 0.7, F/B > 15); and the
  **uncrossed control** — flipping the TL objects to uncrossed must
  collapse F/B below 10 dB (ref 5.7), regression-guarding the sign
  convention end to end.
- `tests/smoke.py` adds the TransmissionLine object round-trip;
  `tests/gui_smoke.py`'s element-designer check grows the LPDA section
  (band inputs, synthesis, verify formatter, crossed-TL generate) — still
  23 checks / 32 commands, green on 0.21.2 + 1.1.1.

## [0.60.0] — 2026-07-18 — Element Designer E4: microstrip patch (TL synthesis)

### Added
- **Microstrip-patch synthesis engine** (`emstudio/antenna/patch_tl.py`,
  ELEMENT_DESIGNER_PLAN slice E4): the standard public transmission-line
  design — radiating width W, Hammerstad effective permittivity, the
  fringing length extension ΔL, resonant length L, the two-slot
  radiating-edge resistance, and the cos² probe-feed placement.
  `design_patch(f0, er, h, target_z)` → the full geometry + a directivity
  estimate + warnings. Verified from first principles (docs/upstream/
  patch-tl-anchors.md) against the widely-published 10 GHz / εr 2.2 example
  (W 11.85 vs 11.86, εr_eff 1.9715 vs 1.972, ΔL 0.811 vs 0.81, L 9.053 vs
  9.06 mm) and cross-checked against independent open academic sources.
- **`makePatchDesign` template** (`emstudio/templates/patch.py`): builds a
  synthesized patch (substrate/patch/ground/probe feed) + openEMS solver.
  The openEMS tutorial reference `makePatch` is unchanged.
- **Patch family in the Element Designer dialog**: an f0 / substrate (εr, h
  with common-laminate presets) / feed-impedance page, a top-view
  schematic, the predicted read-out (W, L, εr_eff, edge R, feed offset,
  gain estimate), and **Verify with openEMS** (FDTD, ~seconds). The
  recommender's patch family is now **available**; a GHz request with a
  substrate routes there.

### Validation
- `tests/validation/element_designer.py` grows a **patch digit tier**: the
  10 GHz example (W/εr_eff/ΔL/L), the 2.4 GHz tutorial-substrate synthesis
  (W 42.2, L 33.5 mm), the cos² feed self-consistency, the ±5 % caveat, and
  the ValueError paths.
- New live gate `tests/validation/patch_auto_openems.py` (openEMS FDTD,
  ~seconds, non-smoke): the 2.4 GHz synthesis resonates at **2.333 GHz
  (−2.8 %, inside the model's ±5 %)** with **6.88 dBi** boresight gain — the
  analytic gain estimate (6.3 dBi) landed within 0.6 dB.
- `tests/gui_smoke.py` exercises the patch family (synthesis, predicted
  read-out, the openEMS verify formatter on a synthetic FDTD result,
  Accept→Generate) — 23 checks / 32 commands green on 0.21.2 and 1.1.1.

### Honest limits
- The TL model is accurate to ~±5 % on the resonant frequency (openEMS
  Verify refines it); the two-slot edge-resistance / feed offset is a
  rougher order-of-magnitude estimate (cos² is the probe-feed law; etched
  inset notches trend toward cos⁴) — a seed for full-wave tuning, stated in
  the UI and the source note.

### Hardened (adversarial review pass before commit)
- The Verify button, its tooltip, the Accept & Generate tooltip and its
  confirmation now name the **actual per-family solver** (openEMS for the
  patch, NEC2 for wire/Yagi) — they previously all said "NEC2" even on the
  openEMS-backed patch. The window title and dialog docstring list the patch
  family; the recommender rationale no longer says patch "ships in slice E4".
- The patch feed gate now **pins** the two-slot edge resistance (≈282 Ω)
  and the derived offset (≈4.64 mm) in tight bands plus an independent
  closed-form inset check (R 200→50 Ω ⇒ y0 = L/3), replacing a tautological
  self-consistency check that a wrong edge-R model would have passed.

## [0.59.0] — 2026-07-18 — Element Designer E3: Yagi-Uda (NBS TN-688)

### Added
- **Yagi-Uda synthesis engine** (`emstudio/antenna/yagi.py`,
  ELEMENT_DESIGNER_PLAN slice E3): NBS Technical Note 688 (Viezbicke 1976,
  public domain) Table 1 encoded VERBATIM (six boom classes 0.4–4.2 λ,
  every per-director length), plus the Fig 9 diameter-compensation and
  Fig 10 boom-correction models. `design_yagi(f0, gain_dbd | boom_lambda,
  wire_d_m, boom_d_m)` selects the smallest boom meeting a gain target (or
  a boom length directly) and returns the fully dimensioned element set —
  reflector, driven, N directors — with both the **bare-wire** length (for
  the NEC2 model) and the physical **cut** length (with the metal-boom
  correction), positions along the boom, gain in dBd **and** dBi, and a
  cited source note. The driven element reuses the E1 dipole synthesis.
  De-risked from the scan **page images** (docs/upstream/tn688-yagi-anchors.md);
  caught (and did not import) the Balanis Table 10.6 typo at the 0.4 λ
  director (0.442 vs the true 0.424).
- **`makeYagi` template** (`emstudio/templates/yagi.py`): one call builds
  the boom + N parallel wires + PEC material + driven feed + NEC2 solver.
- **Yagi family in the Element Designer dialog**: a third family page
  (design by gain target or boom length; metal-boom-diameter input), a
  top-view schematic, the predicted element table (bare-wire + cut
  lengths, gain, boom length), and **Verify with NEC2** — the far-field is
  pinned at the design frequency (the de-risk lesson: the runner's default
  best-match frequency wanders when the driven isn't matched). The
  recommender's Yagi family is now **available** (flipped from the E3
  placeholder); "state 12 dBd → get a dimensioned Yagi" works end to end.

### Validation
- `tests/validation/element_designer.py` grows a **Yagi digit tier** (28
  checks): Table 1 reproduced verbatim, both TN-688 worked examples
  (0.8 λ / 50.1 MHz to <0.0015 λ; 4.2 λ / 827 MHz full set to <0.005 λ —
  the graphical arc-transpose tail), the 0.424 (not the Balanis 0.442)
  cell, boom-class selection, and the ValueError paths.
- New live gate `tests/validation/yagi_nec2.py` (freecadcmd + nec2c): the
  0.8 λ design reads **9.09 dBd** (window [8.3, 9.9]), F/B 12.7 dB at the
  design frequency, sane driven R; plus a four-boom regression
  (0.4/0.8/1.2/2.2 λ) each within **±0.25 dB** of the measured
  7.1/9.2/10.2/12.25 dBd.
- `tests/gui_smoke.py` exercises the Yagi family (synthesis, predicted
  read-out, the verify formatter on a synthetic far-field, Accept→Generate
  building all 6 wires) — 23 checks / 32 commands green on 0.21.2 and 1.1.1.

### Hardened (adversarial review pass before commit)
- A Yagi gain target above the TN-688 table max (14.2 dBd) now cleanly
  disables **Verify** and **Accept & Generate** (they previously stayed
  enabled and dereferenced a null design → a cryptic error and a leaked
  empty document); the verify/generate paths also guard the null design,
  and Accept closes a freshly-created scratch document if generation fails.
- The Yagi "Boom length" combo starts correctly disabled in the default
  "by gain target" mode.
- The **digit gate now pins every boom's element values** against
  independent verified literals (previously the 3.2 λ boom — covered by no
  worked example — had no value-level check, so a transcription regression
  there would have passed); the live regression window tightened from
  ±1.0 dB to ±0.5 dB (the de-risk demonstrated ±0.25 dB).
- Recommender rationale and docstrings updated now that the Yagi family
  ships (no more "ships in slice E3").

## [0.58.0] — 2026-07-18 — Element Designer E2: designer dialog + family recommender

### Added
- **Element Designer dialog** (`emstudio/ui/element_dialog.py`, command
  `EMStudio_ElementDesigner` → **32 GUI commands**; ELEMENT_DESIGNER_PLAN
  slice E2 — the designer-shell is now proven end-to-end on the cheapest
  family; every later slice adds a family page): top-level Element-family
  selector (Wire · Small antenna; Yagi/patch/LPDA pages appear as E3-E5
  ship) over shared Schematic / Predicted-Performance / Verify tabs, with
  the band→method banner. The wire page drives the gated E1 synthesis
  (dipole / monopole / folded / 5/8- 3/4- full-wave verticals) with the
  K-factor choice (0.95 default · the NEC2-measured curve · custom), an
  **editable synthesized length** (synthesized/edited badge + Reset) and
  the cheap **Length → f₀ inverse**. The Small-antenna family routes to
  the shipped VLF/LF/MF designer.
- **Element-family recommender** (`emstudio/antenna/element_picker.py` —
  the requirements schema + deterministic weighted rules, every rule with
  a one-line printable rationale; the stable API the §3 AI assistant will
  target): omni+V+single-freq → wire; gain ≥ 5 dBd → Yagi with the NBS
  TN-688 boom-class hint (honestly flagged "ships in slice E3", demoted
  with the reason when the boom exceeds the size envelope); band ratio
  > 1.5 → LPDA (E5); GHz + substrate → patch (E4); < 3 MHz or a
  sub-λ/10 envelope → the shipped small-antenna family with the **Chu
  bandwidth guardrail** (reused verbatim from `small_antenna`).
- **Verify with NEC2** (off-thread, production writer): solves the ACTUAL
  design — including user-edited lengths — and reports predicted vs
  achieved (f_res by the R-window rule, feed R, peak gain dBi+dBd);
  disabled with a hint when nec2c is missing. **Accept & Generate**
  creates the runnable analysis via the templates.
- `templates.makeDipole(length_m=…)` / `makeMonopole(height_m=…)` —
  optional dimension overrides for the designer; **defaults are
  byte-identical** (re-proven this release: dipole_nec2 / monopole_nec2
  green, plus new frozen-geometry checks in the gate).
- `run_gui.run_generic_gui` gains optional `on_error` / `on_cancel`
  callbacks (existing callers unaffected) so the designer releases its
  transient verify document on **every** exit path.

### Hardened (adversarial review pass before commit)
- **Verify lifecycle**: the transient `ElementVerify` document is now
  cleaned up on success, error, cancel AND dialog dismissal (the finished
  signal — Esc/reject never fires `closeEvent`); the verify build restores
  the previously-active document, and Accept & Generate never targets the
  verify doc — closing a data-loss path where a failed verify then a
  generate then a second verify silently destroyed the user's analysis.
- **Recommender honesty**: the wire family is demoted (and small-antenna
  surfaced) when even a quarter-wave will not fit the size envelope; a
  wide-band + gain request now prefers the LPDA over a narrow-band Yagi;
  an omni + directional-gain request flags the pattern conflict and demotes
  the Yagi; substrate (er/h) surfaces the patch family below 1 GHz too; the
  Chu required-bandwidth is computed about the geometric centre (df/f0, not
  the overstated df/f_lo); and the Yagi envelope test uses the element span
  (boom or the 0.482-λ reflector). All pinned by new gate checks.

### Validation
- `tests/validation/element_designer.py` grows the **picker scenario
  tier** (16 checks: rule outcomes, TN-688 boom row selection, envelope
  demotion, beyond-table honesty → §7, dBi/dBd normalization, geometric
  band centre, determinism, rendering) and the **template-override tier**
  (freecadcmd: frozen default geometry/sweeps/segment counts; overrides
  land exactly). Live folded tier re-run green (291.0 MHz / 282.7 Ω).
- `tests/gui_smoke.py` **23 checks / 32 commands**: the new element-
  designer check exercises synthesis, the recommender honesty flags, the
  288 Ω folded read-out, the verify formatter on a synthetic sweep
  (R-window resonance selection) and Accept→Generate — green on 0.21.2
  and 1.1.1. `tests/smoke.py` gains the Qt-free recommender check.

## [0.57.0] — 2026-07-17 — Element Designer E1: wire-element synthesis engine (§1 epic opens)

### Added
- **Wire-element synthesis engine** (`emstudio/antenna/wire_elements.py`,
  ELEMENT_DESIGNER_PLAN slice E1 — the §1 Element Designer epic opens,
  engine-first per the house pattern; the designer dialog is slice E2):
  dipole / monopole / folded-dipole design plus the λ-fraction vertical
  table, all computed from first principles (L = K·c/2f) with the famous
  ham constants (468/f, 234/f, ~143/f) exposed as DERIVED display
  conventions — printed 468 embeds K = 0.9516 vs the 0.95 thin-wire
  default, a pinned 0.17 % convention gap, not a phantom disagreement.
- **The K (end-effect) curve MEASURED on our own solver**: published charts
  disagree by ±0.01 across 13 curves (Stearns/K6OIK survey), so
  `k_from_ratio()` interpolates the six-point curve measured live on this
  repo's NEC2 writer (ratio λ/2d 21 → 4892, K 0.905 → 0.970; method
  cross-checked two ways to 0.03 %), honestly documented as reading below
  the printed charts at thick ratios (the NEC2 delta-gap effect). Feed-Z
  anchors (72 / 36 / 4× → 288 Ω), gain_dbd = gain_dbi − 2.15 carried both
  ways, §7 report-only flags on 5/8-wave (capacitive X, series-L network)
  and the anti-resonant fractions, < λ/10 routing to the shipped
  small-antenna engine.

### Validation
- New gate `tests/validation/element_designer.py` (python3 + freecadcmd):
  25 digit anchors — the shipped-template inversion is **bit-exact**
  (0.475 = 0.95·0.5 in float64), the measured K curve hits the template
  deck's NEC2-implied K (0.93822 vs 0.938252), derived-constant/metric
  round-trips bit-exact, dBd pins, fraction-table flags, router guards —
  plus a **live folded-dipole tier** through the production NEC2 writer
  (resonance selected by R-window — the fold has kΩ anti-resonances at
  204/381 MHz around the real one): **291.0 MHz / 282.7 Ω** vs the
  de-risked 291.14 / 283.0 (Balanis 4× step-up window hit; zero nec2c
  warnings). De-risked first (3 probes + adversarial verification):
  seven anchor families multiply-sourced, six-point live K-curve, and a
  27-check scratch prototype — pitfalls pinned in PROJECT_MEMORY (nec2c
  path-length abort, EK-kernel honesty, R-window resonance selection,
  like-for-like monopole bookkeeping). dipole_nec2/monopole_nec2 re-run
  green as cross-checks. Green on 0.21.2 + 1.1.1 + python3.

## [0.56.0] — 2026-07-17 — 3-D magnetics in the GUI: any FreeCAD solid, one click (MAGNETICS_DEPTH_PLAN §5 wiring)

### Added
- **The 3-D engine is now a user-facing feature**: set
  `SolverElmer.AnalysisType = "3-D Magnetostatic (DC)"` and every
  referenced solid is exported as a BREP and meshed CONFORMALLY as-is
  (`gmsh_3d` gains Merge + Dilate import with TAG-STABLE re-identification
  — OCC bounding boxes of curved imports are loose (B-spline control
  points reach ~2R), so fragments-preserve-uncut-tool-tags is the
  mechanism, probe-verified). New `solvers/elmer/model3d.py` extracts
  Coil (signed N·I ampere-turns via `Reversed`) and Material solids into
  the model; decks run in mm with `Coordinate Scaling` + VTU Revert so
  the B-field overlays the geometry (equivalence to the validated meters
  decks probed at 0.05 %). `elmer.run()` dispatches on AnalysisType; the
  magnetics dialog, 3-D viewport ("Show Fields in 3D") and PDF report
  work unchanged (mode-honest headers; 3-D L/λ extraction is a planned
  slice).
- **Template: 3-D Solenoid (Magnetostatic)** (31st GUI command) — an
  air-core tube coil at 500 At that solves in ~30 s; swap in any closed
  coil solid (racetrack, bent, non-coaxial). Older documents' AnalysisType
  enum is upgraded in place on restore.

### Validation
- New freecadcmd gate `tests/validation/solenoid3d_elmer.py`: the FULL
  FreeCAD path (template solids → BREP export → conformal mm mesh →
  WhitneyAV) lands **−1.26 %** vs the exact thick-solenoid closed form on
  the fast template mesh (engine gates pin −0.55 % on fine meshes), plus
  the extraction (+500 At, padded air) and the dialog-facing
  MagneticsResult wrapper. `smoke.py` covers the new mode/enum-upgrade
  and 3-D headless writers; `gui_smoke.py` gains the **real 3-D solve
  loop** (22 checks / 31 commands) — green offscreen on BOTH FreeCADs.
  Green on 0.21.2 + 1.1.1 + python3.

## [0.55.0] — 2026-07-16 — General 3-D magnetodynamics engine + TEAM-7 measured benchmark (MAGNETICS_DEPTH_PLAN §5)

### Added
- **General 3-D magnetodynamics engine** — the WhitneyAV chain
  (**CoilSolver → WhitneyAVSolver → MagnetoDynamicsCalcFields**), breaking
  the axisymmetric-only limit of the magnetics backend. New modules
  (engine slice, per the coax/ITU precedent — GUI wiring is the next
  slice): `emstudio/meshing/gmsh_3d.py` (multi-body CONFORMAL tet meshing
  via OpenCASCADE `BooleanFragments`; box/tube/racetrack primitives +
  hole subtraction; per-body size fields — Box and Distance/Threshold
  styles — with the load-bearing `MeshSizeExtendFromBoundary = 0`;
  non-physical embedded evaluation curves; post-fragment body
  re-identification by bounding box), `emstudio/solvers/elmer/writer3d.py`
  (magnetostatic + transient-sinusoidal decks; one `Component` per coil
  with SIGNED ampere-turns; ungauged A-V — BiCGStabl(6), **no
  preconditioning**, a direct solver fails on the curl-curl null space;
  `Fix Input Current Density` + the Jfix namespace; MATC cosine drive on
  the elemental coil field; meters, no `Coordinate Scaling`),
  `emstudio/solvers/elmer/runner3d.py` (pipeline + SaveLine/norm parsing,
  `ERROR::`/non-convergence scanning).

### Validation
- **TEAM Problem 7 — EMStudio's first MEASURED benchmark gate**
  (`tests/validation/team7_elmer.py`): the full production pipeline builds
  the official "Asymmetrical Conductor with a Hole" (294×294×19 mm Al
  plate, σ = 3.526e7, eccentric 108×108 hole, racetrack coil 2742 At,
  50 Hz transient) from its own license-clean deck and lands **2.83 %
  normalized RMS** against the 17 published measured Bz points on the
  A1-B1 line (gate ≤ 10 % — a measured-data tier, deliberately separate
  from the sub-percent analytic brand). CoilSolver/WhitneyAV norms
  self-pinned as regression numbers.
- **Analytic tier** (`tests/validation/whitney3d_elmer.py`): thick finite
  solenoid on-axis Bz vs the exact closed form (**−0.55 %** center,
  −0.10/−0.03 % at the ends), Helmholtz pair center vs
  (4/5)^{3/2}µ0NI/R (**−0.62 %**) plus the field-FLATNESS shape check
  (−1.8e-4 vs analytic −1.1e-4), and off-axis loop Bz vs the exact
  elliptic-integral field (**−0.78 %**). Both are SLOW release-tier gates
  (~5-15 min each, live Elmer).
- De-risked first on live ElmerSolver v26.2 (both probes adversarially
  verified with full re-runs): pitfalls pinned in PROJECT_MEMORY — the
  coil circulation SENSE is mesh-arbitrary (verify + flip per coil),
  `A {e} = 0` truncation UNDERESTIMATES (−0.22·(R_coil/R_box)²; use ≥10×
  boxes), CoilSolver normalization under-delivers NI on coarse coil
  meshes, gate on NODAL fields (elemental/DG is pointwise noisy), embedded
  evaluation curves must NEVER cross (degenerate slivers at the
  intersection — found by the gate itself), `Narrow Interface` absent
  from this CoilSolver build. `smoke.py` gains a headless 3-D
  writer/mesher check. Green on 0.21.2 + 1.1.1 + python3.

### Added
- **Nonlinear B-H materials** in the Elmer magnetics chain: new
  `Material.BHCurveB` / `BHCurveH` float-list properties (columns **B [T]
  then H [A/m]**, ~40 points sampled uniformly in B) replace
  `RelPermeability` when set. Works in BOTH analysis modes: **exact** in
  the new Static (DC) mode; in the Harmonic (AC) chain it is Elmer's
  amplitude-adaptive secant reluctivity ν = H(|B|)/|B| at the local PEAK
  phasor |B| — an honestly-labeled **effective-permeability
  approximation** (no waveform distortion/harmonics; source- and
  behaviorally-verified: at σ = 0 it equals the static nonlinear solve
  bit-exactly). When a B-H body is present the writer emits a REAL
  nonlinear block — the old hard-coded single nonlinear iteration (also
  Elmer's default) **silently disables the curve** (exit 0, linear
  initial-µ result, +93 % flux-linkage error at deep saturation).
- **Static (DC) analysis mode**: `SolverElmer.AnalysisType`
  (Harmonic (AC) default | Static (DC)) — DC magnetostatics via
  `MagnetoDynamics2D` (scalar Potential): inductance at the operating
  current (L(I) saturation droop), B-field maps; frequency sweep ignored,
  no eddy/Joule/thermal quantities (clear errors), coupling extraction
  skipped (no superposition with nonlinear iron).
- **B-H table guards** (a malformed table runs SILENTLY wrong at exit 0):
  strict monotonicity, (0,0) start, B ≤ 5 T, units-ratio check (a
  column-swapped table converges FASTER and passes a naive B-max check at
  knee drive: +18.5 % λ with B < B_sat — guarded at the table level), and
  B-sampling density (a uniform-in-H table under-resolves the knee — 42 %
  λ error measured).
- Banked for the next slice: [docs/TEAM7_BUILD_SHEET](docs/TEAM7_BUILD_SHEET.md)
  — the complete, cited TEAM problem 7 (3-D WhitneyAV) build sheet
  (geometry, three-solver chain, mesh guidance, 17 measured A1-B1 Bz
  points, ≤10 % RMS gate, license-clean strategy); Elmer's own `mgdyn_bh`
  Reference Norm was investigated and **deferred** (mesh-locked, 3-D
  Cartesian — not portable to our writer), so §4 self-pins its FEM values.

### Fixed
- `emstudio/version.py` was left at 0.52.0 by the v0.53.0 release
  (package.xml-only bump; the smoke battery ran before the bump). Both now
  read 0.54.0.

### Validation
- New gate `tests/validation/bh_elmer.py` (28 checks): deck-emission tier
  (H-B table + nonlinear block; static solver/BC/source keywords; all
  guards; no-B-H decks unchanged) plus live tiers on the de-risked gapped
  pot-core (Fröhlich iron, 2 mm gap, N=200): static λ at 1/6/15 A vs an
  **independent nonlinear ladder-MEC** (+2.0…+3.8 %, fringing-limited —
  the plain series reluctance loop is ~2× wrong: window leakage ≈ gap
  reluctance) + frozen FEM regression pins (−0.001 %); L(I) droop
  15.3→14.0→8.0 mH; linear-µ control 1.93× above saturated λ;
  **harmonic B-H == static B-H at σ = 0 bit-exactly (0.0e+00)** at all
  three drives; harmonic saturation droop 0.520; and the
  linear-as-table == RelPermeability exactness pin (2e-9). De-risked
  first on live ElmerSolver v26.2 (static probe +2–5 % vs MEC with
  column-trap demonstration; the 30-minute harmonic probe settled
  SHIP-EFFECTIVE-MU with source citations; transient B-H BDF2 verified
  working — banked). `smoke.py` asserts the new properties/enum; the
  σ(T)/ktemp/radiation/induction/WPT gates re-run green. Green on
  0.21.2 + 1.1.1 + python3.

## [0.53.0] — 2026-07-16 — Magnetics σ(T) coupled Joule heating (MAGNETICS_DEPTH_PLAN §3)

### Added
- **Temperature-dependent electrical conductivity σ(T) = σ0/(1 + α·(T −
  ambient))** in the Elmer magnetics→heat chain — *the architectural slice*:
  a new `Material.ConductivityTempCoeff` (α, per K) turns the one-way
  Joule→heat chain into a genuine **two-way coupled** solve. Steady decks
  gain an outer `Steady State Max Iterations = 30` loop (the solvers already
  `Exec Always`; the loop exits early on the per-solver steady-state
  tolerances — 5 iterations at the gate's coupling strength, **no
  relaxation**: the de-risk probes proved it slows this monotone iteration).
  Transient decks drop the single-shot `"Before Simulation"` field solve and
  re-solve the field every timestep (one-step-lagged coupling). α = 0 (the
  default) is byte-identical to the v0.52 decks.
- Two silent-catastrophe traps found by the de-risk and encoded in the
  writer: (1) the **ambient Initial Condition is MANDATORY** with σ(T) —
  without it iteration 1 evaluates T = 0 and the conductivity goes
  **negative** for any metal (α·T_ref > 1), silently at exit 0; (2) coupled
  decks must write the VTU **`After Simulation`** — with the outer loop,
  `After Timestep` makes `case_t0001.vtu` the *first* (uncoupled, constant-σ)
  iterate. The runner also now collects ComputeChange **"did not converge"
  warnings** (`solver_warnings` per case) — Elmer's only signal of a stalled
  coupling loop or genuine thermal runaway (it exits 0).

### Validation
- New gate `tests/validation/heat_sigma_elmer.py`: a deck-emission tier
  (byte-identical α=0 guard; the `Variable Temperature` MATC; the coupled
  loop + mandatory IC + `After Simulation` VTU; transient exec-model switch;
  the non-thermal-body error path) plus live Elmer tiers — the coupled
  billet vs an **independent 1-D RK4-shooting reference** (eddy power
  −0.015 %, centerline/surface temperatures <0.01 K) with the **−5.57 %
  self-limiting delta** vs constant-σ landing exactly on the reference
  (feedback provably took effect, with the right sign — an inverted σ table
  lands hotter), and a transient tier (σ(T) heating curve below constant-σ,
  monotone approach). De-risked first on live ElmerSolver v26.2: closed-form
  runaway-cylinder (Bessel-J0, +0.017 %, runaway limit mR→2.4048
  characterized), Kohlrausch rod two-way loop (+0.001 %, feedback +22 % on
  resistance), and the production harmonic chain (−0.0008 % vs reference) —
  every probe adversarially re-verified. `smoke.py` asserts the property
  exists and defaults off; the ktemp/radiation/induction/WPT gates re-run
  green. Green on 0.21.2 + 1.1.1 + python3.

## [0.52.0] — 2026-07-12 — Magnetics temperature-dependent k(T) (MAGNETICS_DEPTH_PLAN §2)

### Added
- **Temperature-dependent heat conductivity** k(T) = k0·(1 + β·(T − ambient))
  in the Elmer magnetics→heat chain: a new `Material.ThermalConductivity`
  `TempCoeff` (β, per K) makes the writer emit
  `Heat Conductivity = Variable Temperature` with the MATC expression
  instead of a constant. β = 0 (the default) is byte-identical to the
  constant-k decks. The nonlinear conduction reuses the Newton block +
  ambient IC added for radiation (generalized `heat_nonlinear` = radiating
  or k(T)); the writer's old hard-coded single heat iteration is now lifted
  for both.

### Validation
- New gate `tests/validation/heat_ktemp_elmer.py`: a deck-emission tier
  (byte-identical constant-k guard; the `Variable Temperature` MATC; the
  shared Newton block + IC; no stray radiation keywords) plus a live Elmer
  tier using the **Kirchhoff transform** — a Joule billet with k(T) where
  the interior heat integral `∫k(T)dT` is source-set and k-independent, so
  it must equal `σω²μ0²H0²a⁴/128` (FEM +0.10 %); the raw drop demonstrably
  collapses (k rising ~20× at the hot interior) proving k(T) took effect;
  and the surface temperature stays k-independent (convection balance).
  `smoke.py` asserts the property exists and defaults off; the radiation /
  induction / WPT gates re-run green. Green on 0.21.2 + 1.1.1 + python3.

## [0.51.0] — 2026-07-12 — Magnetics surface radiation BC (MAGNETICS_DEPTH_PLAN §1)

### Added
- **Grey-body surface radiation** in the Elmer magnetics→heat chain
  (`solvers/elmer/writer.py`): a new `SolverElmer.SurfaceEmissivity`
  (+ optional `RadiationTemperature`) adds `Radiation = Idealized` /
  `Radiation External Temperature` / `Emissivity` on the body-surface BC,
  **stacking additively** with the existing convection pair. Emissivity 0
  (the default) is byte-identical to the pre-v0.51 convection-only decks.
  The T⁴ term makes the heat solve nonlinear, so when radiating the writer
  also emits the mandatory `Stefan Boltzmann` constant, a Newton-after-
  Picard nonlinear block, and an ambient initial condition — the two
  silent-catastrophe traps the de-risk probe found (missing Stefan-
  Boltzmann is a hard STOP; the old hard-coded single heat iteration
  returned T ≈ −1e14 K at exit 0 under T⁴).

### Validation
- New gate `tests/validation/heat_radiation_elmer.py`: a deck-emission tier
  (pure `write_sif` — the byte-identical convection-only guard, the
  Stefan-Boltzmann constant, the three radiation BC lines, the Newton block
  and the ambient IC) plus a live Elmer tier (a radiating+convecting billet:
  surface temperature vs an independent bisection root-find of
  `h(Ts−Tamb) + εσ(Ts⁴−Trad⁴) = P/A` at −0.00 %, interior dT unchanged at
  +0.07 %, and radiation demonstrably cooling the surface 315.6 K vs
  332.1 K). `smoke.py` asserts the new properties exist and default off;
  the induction/WPT convection-only gates are unchanged. Green on 0.21.2 +
  1.1.1 + python3.

## [0.50.0] — 2026-07-12 — Cable thermal / temperature-rise analysis + visuals

### Added
- **Cable thermal engine** (`emstudio/wire/thermal.py`, Qt-free): steady
  conductor temperature of a horizontal cable in free air — I²R(T) loss
  (IEC 60287-1-1 ρ(T), thermal-runaway detection, never clamped), the
  IEC 60287-2-1 radial ladder `T = (ρ/2π)ln(1+2t/D)` over any layer stack,
  and Churchill-Chu free convection + radiation on the AHTT dry-air table
  (250-600 K printed rows); **ampacity** inverse solve per insulation
  temperature class (IEC 60502-1 / UL 758 / MIL-DTL-16878 / IEC 60085
  classes — "S 240" is UL/NEMA, not IEC, per the adversarial correction);
  NEC 310.15(C)(1) bundle adjustment; first-order **transient** rise
  (τ = C_th/G_th, IEC 60853-2 heat capacities); **IEC 60949 adiabatic
  short-circuit** (Cu K=226/β=234.5, Al 148/228); and a **coax RF
  average-power rating** with the exact `p' = (ln10/10)·A·P` dissipation
  identity, Rs/a-vs-Rs/b conductor split (per-conductor σ) and the exact
  ½-dielectric-heat factor for the TEM 1/r² profile.
- **Exterior 2-D temperature field** (`thermal.exterior_field`): the
  "how heat rises and dissipates" view — exact interior radial ladder →
  conduction film `δ = k_f/h = D/Nu` (the engine's own correlation) with
  the flux-preserving Eckert-Soehngen asymmetry → **laminar plane-plume
  similarity solution rising above the cable** (Gebhart-Pera-Schorr /
  Liñán-Kurdyumov; pinned Pr = 0.7 constants f′(0) = 0.661832,
  I = 1.211742, G0 = 0.430523, η_½ = 1.17454; Gebhart-form centreline so
  enthalpy closure is exact by construction; plume fed by the convective
  heat share only; virtual origin matched to the film). Honestly labeled:
  similarity model, still air — illustrative outside the film.
- **Thermal tab in the Cable Designer** (wire/litz pages): load / ambient /
  temperature-class / emissivity controls; four visuals — temperature-
  colored construction cross-section with colorbar, the film + rising-plume
  exterior field with isotherms, conductor-rise-vs-current with the class
  limit and ampacity intercept, and the transient heating curve with
  time-to-limit; read-out with margin, ampacity, τ, adiabatic 1-s rating
  and honest validity warnings (fine-wire Churchill-Chu conservatism,
  Ra range, runaway). Coax page: matched average-power P_max(f) curve.
  Bundle page: NEC derating read-out. The deliberately conservative
  `litz.ampacity` sizing estimate is untouched (gate-frozen).

### Changed (pre-ship adversarial review pass, 8 finder angles + a physics
adversary that recomputed the engine to machine precision)
- **Overload heating honesty**: the small-signal exponential undercut even
  the zero-loss adiabatic bound above ~1.5× rating — the tab now plots an
  ODE-integrated `heating_curve` (quasi-static ladder + the engine's own
  surface model; gated to settle on `solve_steady`'s fixed point and to
  respect the adiabatic lower bound at 2× rating); `transient` is
  re-labeled small-signal. Litz C_th no longer counts packing filler as
  solid copper (metal-area override, ~30 % τ correction).
- **Cold-surroundings bracket**: `solve_steady` with `tsur_c < tamb_c`
  silently pinned the surface at ambient and broke its own energy balance —
  the bracket now extends below ambient (gated with the adversary's probe).
- **Material names**: engine-side `normalize_material`/
  `layers_from_construction` replace the dialog's incomplete map (enamel
  and silicone were silently rated as PVC; unknown names now warn).
- Guards instead of garbage: class limit ≤ ambient (friendly message, and
  `coax_power_w` raises rather than returning negative watts), ampacity
  raises when the limit is unreachable (Rdc ≈ 0), transient raises at zero
  load; the wire path always re-analyzes LIVE page inputs and echoes the
  construction name; AC loads use the page's own Rac/Rdc via a new
  frequency control (was DC-only with a footnote); bare-conductor
  emissivity warning; the cross-section pane now colors from the gated
  field sampler (no UI copy of the ladder formula); the coax headline
  reads the plotted curve (1 GHz is a grid point); named coax-build
  defaults (`SHIELD_OD_FACTOR`, `k_thermal_from_eps_r`) shared by curve,
  read-out and future callers.

### Validation
- New gate `tests/validation/thermal.py` (51 checks, python3 + freecadcmd),
  every anchor from the adversarially recomputed de-risk (60/61, both
  corrections baked in): IEC T1 worked examples to 1e-9 (QuickField
  0.8166061945 — round() gives 0.817, the printed 0.816 is a truncation;
  E3S 0.4325954273/KA 0.116); Cengel Ex 9-1 (Ra 1.869e6 / Nu 17.40 /
  h 5.869 / 443 W / 553 W) and AHTT Ex 8.4 (fine-wire, h 13.84) with each
  book's own printed film properties injected; AHTT air rows exact;
  Churchill-Chu within ±25 % of the Morgan bands; ampacity BANDS — NEC
  310.17 ±25 %, Multicable AWG-10 105 °C 58 A ±25 % (model 66.6 A), MIL-W-
  5088L §6.7 text points ±15 % (15.2/71.2 A vs 16.2/68), NASA 1-atm point
  within the documented Churchill-Chu fine-wire conservatism (+25 % hot,
  warned by the engine); adiabatic J0 143.08/94.48, the 630 mm² datasheet
  rows to 0.15 %, BS 7671 k table ±0.5; the dissipation and ½-factor
  identities to 1e-12/1e-4; **Times LMR-240 catalog table within 90-125 %
  (worst 1.092) with the datasheet attenuation split**; Belden 8262 /
  RG-142 one-sided soft bands; and the exterior field — an **independent
  RK4 shooting solve re-derives the plume constants** (Pr = 2 closed form
  √5/4 and I = (16/15)(125/576)^¼ to the digit; Pr = 0.7 pins + the
  G0 = (64Pr²I⁴)^(−1/5) identity), power-law exponents exact, enthalpy
  flux recovered to 0.23 % worst, surface continuity/flux preservation
  exact, bitwise mirror symmetry, monotone bounded decay. `smoke.py` adds
  the Qt-free T1 + adiabatic pins; `gui_smoke.py`'s cable check exercises
  the Thermal tab (wire steady/ampacity/transient + coax P_max curve)
  headlessly — still 21 checks / 30 commands. Green on 0.21.2 + 1.1.1 +
  python3.

## [0.49.0] — 2026-07-12 — Differential pair-to-pair coupling (mixed-mode)

### Added
- **Mixed-mode diff-pair engine** (`emstudio/wire/mixed_mode.py`): reduces a
  4-conductor (+ reference) bundle to differential modes by the
  Bockelman-Eisenstadt congruence (`T_I = (T_V⁻¹)ᵀ` — pinned; a similarity
  transform is 43 % wrong) and reports `Ldd`, `Mdd`, the general
  `k_diff = Mdd/√(Ldd_A·Ldd_B)`, `Cdd_AB` and the **ASTM D4566 pair-to-pair
  capacitance unbalance CUPP = −4·Cdd_AB**, plus Zdd estimates and
  differential NE/FE weak-coupling crosstalk (terminations are DIFFERENTIAL
  ohms; the balanced circuit has no common-impedance floor). Wide-separation
  closed forms: the reference conductor cancels exactly out of both `Ldd`
  and `Mdd = (µ0/2π)·ln(d14·d23/(d13·d24))`.
- **RADC-TR-76-101 Vol V twist model** (McKnight & Paul, DTIC ADA053559 —
  equations 4-1…4-10/4-26/4-27/4-42/4-43 verified on page images, see
  `docs/upstream/radc-vol5-twist-anchors.md`): eq 4-3 alternating loop sum
  (even-N inductive cancellation, conservative **odd-N envelope 1/N**
  quoted), the twist-independent capacitive floor for unbalanced receptors
  (4-8/4-10), the balance null (4-43), and a documented ground-loop warning
  (twist buys ~1 dB when the receptor is grounded at both ends).
  Page-image correction to the old plan: the printed 10.25 dB benefit is at
  **50 Ω** loads, not 1 Ω.
- **Bundle-page differential mode** (`ui/cable_dialog.py`): a "Differential
  pair-to-pair (mixed-mode)" toggle swaps the member pickers to
  A1/A2/B1/B2 + reference, adds receptor twist (half-twist count) and
  termination-topology controls, plots untwisted + twisted differential
  NE/FE curves, and reads out k_diff / CUPP (pF/100 m) / Zdd with the twist
  improvement and honest validity warnings. Insulated members route C
  through the v0.48 MoM solve; the FastHenry L option works in diff mode.

### Changed (pre-ship adversarial review pass, 8 finder angles)
- Signed twist read-out (a worsening twist case rendered "−-2.9 dB"; the
  change is now printed as "{:+.1f} dB vs untwisted" — it CAN be positive:
  with opposite-sign lm/cm the untwisted terms partially cancel), the Mdd
  read-out shows the SIGNED value plus a "(pair B relabeled)" note when the
  polarity was normalized, engine warnings are HTML-escaped, and the
  terminations row is relabeled "differential Ω" in diff mode.
- FastHenry + bare tight bundles now keep an explicit C-side caveat (the
  bare-identity C deliberately derives from the analytic wide-separation L
  on BOTH routes — a uniform-current L corrupts C; the MoM insulated C is
  spacing-exact and carries no caveat). Member pickers are labeled
  "packed #" (qty-expanded indices) and the empty-bundle path warns instead
  of raising. Shared helpers replace four copies of the validity warning,
  two of the C-source block and two member pickers; `diff_crosstalk` always
  returns a distinct twisted dict (no n=0 aliasing); the transform ships a
  `pair_transform(n_pairs)` builder pinning the congruence pattern for §7.

### Validation
- `tests/validation/cable.py` +24 checks: congruence/endpoint identities and
  the homogeneous `L_mm·C_mm = µ0ε0·I` at machine precision; reference
  cancellation and the `Mdd` closed form; **12-digit anchors from an
  independent full-MTL 8×8 chain-matrix oracle** (diff NE −100.891 dB / FE
  −108.858 dB at 100 kHz — the weak engine lands within 0.011 %/0.026 %);
  mode invariants `Zdd = 2·Zodd`, `Ldd·Cdd = Lodd·Codd = µ0ε0` **plus the
  2×/0.5× mixed-definition traps**; the mirror-symmetry null (`Mdd = Cdd = 0`
  identically) and its 0.5 mm un-null; eq 4-3 parity algebra at the report's
  own N = 225/226; balanced twist improvement exactly 20·log10(N); the
  unbalanced low-Z benefit **9.54 dB inside the report's printed
  10.25 ± 3 dB soft band** and the high-Z ≤ 3 dB band (report: "no effect");
  the MoM-insulated C preserving the symmetry null. `smoke.py` adds the
  Qt-free oracle + parity check; `gui_smoke.py`'s cable check now exercises
  the diff route (MoM C + exact 20·log10(N)) — still 21 checks / 30
  commands. Green on 0.21.2 + 1.1.1 + python3.

## [0.48.0] — 2026-07-10 — Insulated-bundle C (MoM) + openEMS isolation gates

### Added
- **Insulated-bundle capacitance by method-of-moments**
  (`emstudio/wire/electrostatics.py`): Clayton Paul's RIBBON.FOR / GETCAP
  method (MTL 2e §5.2.2 bare + §5.2.2.1 dielectric) — an entire-domain
  Fourier surface-charge expansion per conductor plus a bound-charge layer at
  each insulation surface, point-matched (potential rows on conductors,
  normal-D-continuity rows on dielectric interfaces; the singular-avoiding
  A.4 match-point rotation), solved for the generalized capacitance matrix.
  This **replaces the "bare value only" caveat** the coupling module carried
  for insulated bundles: `bundle_c_mom(positions, radii, er, wall, ref)`
  returns the generalized and transmission-line C for a real inhomogeneous
  (insulated) cable. Pure numpy, Qt-free.
- **Bundle-page crosstalk now uses the MoM C when members are insulated**
  (`ui/cable_dialog.py`): when the picked generator/receptor/reference
  members have insulation (envelope OD > conductor Ø), the mutual capacitance
  for the weak-coupling crosstalk comes from the MoM insulated solve instead
  of the bare identity — a new "Insulation εr" control drives it, and the
  read-out states which C source was used. Bare members keep the bare-identity
  path byte-identical.

### Validation
- `tests/validation/cable.py` adds 9 MoM checks: the insulated ribbon TL C
  reproduces **Paul problem 5.15 (24.98 / -6.266 pF/m)** to the printed digit;
  the computed generalized matrix matches the de-risk literals
  (26.2148 / -18.0249 / -5.0333); the bare-ribbon C + the mu0·eps0·inv(C)
  identity recovers **Paul's exact L (0.7485 / 0.2408 µH/m)**; the center-wire
  effective-permittivity shift lands in Paul's printed 50-66 % band (1.6465);
  Fourier convergence (nf=7 within 1e-4 of nf=16); a bare two-wire pair equals
  the exact acosh line capacitance to machine precision; the εr→1 insulated
  solve degenerates to the bare solve; and reciprocity holds on an asymmetric
  insulated triangle. `smoke.py` adds a Qt-free anchor; `gui_smoke.py`
  exercises both the MoM-insulated and bare crosstalk routes (still 21 checks
  / 30 commands). Green on 0.21.2 + 1.1.1 + python3. Additionally anchored to
  the INDEPENDENT US-government printing (RADC-TR-76-101 Vol II "GETCAP",
  DTIC ADA025029, public domain — tables banked in
  `docs/upstream/radc-getcap-anchors.md`): the five-wire bare TL matrix
  (Table 9, ten 16-digit entries) replays at **3.8e-8 relative** and the NF=5
  truncation reproduces the printed near-touching convergence entry (Table 8)
  — the replay even confirms the scan's smudged digit.
- **openEMS co-site isolation gates** (§5, a second solver alongside the
  shipped NEC2 isolation): `tests/validation/isolation_openems.py` — two
  parallel strip dipoles at 0.5 λ → **|S21| −13.82 dB, matching Balanis
  eq. 8-71 exactly and the shipped NEC2 gate (−13.78 dB) to 0.04 dB** (the
  cross-solver agreement is the validation); and
  `tests/validation/isolation_patch_openems.py` (release tier) — the
  **Jedlicka-Poe-Carver coupled microstrip patches** (IEEE AP-29 1981, via
  the Kwan & Newman build sheet): E-plane |S21| −23.6 dB (published −24.0),
  H-plane −30.9 dB (published −33.5), reproducing the measured trend
  (H-plane coupling ~7 dB weaker than E-plane). Both are FreeCAD-free,
  on-demand gates (need the openEMS venv), NOT in the fast smoke suite.

## [0.47.0] — 2026-07-10 — ITU-R P.452-18 + P.2001-6 adoption (§6-D complete)

### Added
- **P.452-18 interference prediction** and **P.2001-6 wide-range propagation**
  via the vendored **ITU-R reference implementations**
  (`emstudio/vendor/py452`, `emstudio/vendor/py2001` — Py452/Py2001 by
  I. Stevanovic/OFCOM, permissive licenses + PROVENANCE.md; vendoring
  changes per package, all noticed there: the module-level ITU-map load made
  lazy, and ``__init__.py`` replaced by the EMStudio re-export shim). EMStudio faces
  `emstudio/coverage/p452.py` (`path_loss_db` — LoS + diffraction +
  troposcatter + ducting interference loss, validity-enforced 0.1–50 GHz /
  0.001–50 %) and `emstudio/coverage/p2001.py` (`path_loss_db` — the
  general-purpose 0–100 %-of-year model, validity-enforced 30 MHz–50 GHz /
  3–1000 km).
- **ITU digital-map installer** `emstudio/coverage/itu_maps.py`: the maps
  (DN50/N050 for P.452; the 14 radio-climatic files for P.2001) are
  *integral ITU products* that may not be redistributed — EMStudio never
  bundles them. `install_p452_maps()` / `install_p2001_maps()` download the
  OFFICIAL Recommendation zips from itu.int (or take a user-supplied
  zip/directory as the offline fallback), extract the map files (nested
  zips handled) and build the npz archives into a per-user maps dir
  (`EMSTUDIO_ITU_MAPS_DIR` overridable); the vendored engines find them
  lazily — the workbench imports and runs fine without them, and only an
  actual P.452/P.2001 computation asks for them (with install instructions
  in the error).

### Validation
- New gate `tests/validation/p452.py`: replays the **official CG-3M
  P.452-18 validation examples** (17 profiles / 595 cases, mirrored with
  provenance) — the 21 path-geometry intermediates, the final Lb AND eight
  sub-model losses (Lbfsg/Lb0p/Lb0b/Ldsph/Ld50/Ldp/Lbs/Lba) all match the
  reference ≤ 1e-6 (live worst: losses 5.0e-9 dB, geometry 5.0e-7); the
  wrapper reproduces an official case and rejects out-of-validity input.
- New gate `tests/validation/p2001.py`: replays the **official ITU-R P.2001
  validation examples** (2 profiles / 4430 cases, results mirrored gzipped)
  — every Lb ≤ 1e-6 dB (live worst **1.2e-12 dB**); wrapper + validity
  checks. ~20 s.
- `smoke.py` adds a Qt-free block: both vendored engines import WITHOUT the
  ITU maps, both wrappers enforce validity, and the installer knows its
  maps dir. Green on 0.21.2 + 1.1.1 + python3; gui_smoke still 21 checks /
  30 commands (engine slice — no new GUI).

## [0.46.0] — 2026-07-10 — ITU-R P.368-10 spherical-earth ground wave (§6-D)

### Added
- **Spherical-earth LF/MF ground wave — the beyond-100-km extension**
  (`emstudio/coverage/lfmf.py`): a line-for-line Python port of the **NTIA/ITS
  LFMF v1.1 C++ reference implementation** — the software ITU-R P.368-10
  declares an *integral part of the Recommendation* (US-gov public domain +
  worldwide derivative-works grant; acknowledgment + change notes in the
  module docstring and `tests/validation/data/lfmf/PROVENANCE.md`). Flat-earth
  Sommerfeld with curvature correction (DeMinco 99-368, `scipy.special.wofz`
  Faddeeva) auto-switching at d = 80/∛f to the **Wait/Hufford residue series**
  (Hufford's bespoke Airy evaluator replaced by `scipy.special.airy` through
  the derived Wait-scaling identity `w1 = √π·(Bi − j·Ai)`; Newton root search
  from the DLMF 9.9 Airy zeros). Validity enforced 0.01–30 MHz / 0.001–10000
  km / heights 0–50 m; **below 10 kHz it HARD-STOPS** (ionospheric — ITU-R
  P.684 territory, no extrapolation).
- `groundwave.spherical_field_strength_dbuv_m` (same CMF reference convention
  as the shipped flat-earth model) and `millington_field_dbuv_m(...,
  spherical=True)` — Millington mixed paths on the spherical engine
  (P.368-10 Annex 2).
- **Opt-in coverage wiring** (defaults byte-identical): `heatmap.coverage_grid
  (..., gw_engine="p368")`, threaded through `multistation.station_fields` /
  `service_contour` / `best_server`; the Area Coverage Map dialog gains a
  **Ground-wave spherical (ITU-R P.368-10)** propagation-model entry and the
  Multi-Station dialog gains the same engine choice (the honest engine for
  hundreds-of-km LF/MF interference distances).

### Validation
- New gate `tests/validation/lfmf.py` (python3 + freecadcmd): replays a
  **2497-point full-double-precision oracle grid** generated from the
  unmodified upstream binary (0.01–30 MHz × 0.001–10000 km × sea/average/
  very-dry ground × heights × both polarizations × N_s 250–400, bracketing
  the method switch) — **worst |Δ| 3.2e-5 dB** across A_btl/E/P_rx with the
  flat/residue method flag matching on every row; the official
  `LFMF_Examples.csv` (5 worked rows to their printed digit + all 90
  validation rows rejected for the coded reason); the spherical wrapper
  physics (flat≈spherical at 50 km, −52 dB spherical correction at 1000 km /
  1 MHz, monotonic decay, sea>average>dry ordering, exact 1-km CMF reference,
  spherical-Millington reciprocity, the <10 kHz hard-stop) and the heatmap
  opt-in (default byte-identical, meta records the engine, far-cell check).
  `smoke.py` adds a Qt-free P.368-10 block; `gui_smoke.py` exercises both new
  dialog paths (**still 21 checks / 30 commands**). Green on 0.21.2 + 1.1.1 +
  python3.
- **Adversarially hardened before ship** (17-agent refutation-verified
  review): fixed a **1.7 dB silent branch-cut divergence at ε = 1 +
  horizontal polarization** (CPython `cmath.sqrt` 1-ulp asymmetry on
  pure-imaginary arguments vs glibc `csqrt` — `_csqrt_glibc` mirrors the
  glibc special case; a 128-row ε = 1 oracle block added, red→green proven);
  made the gate loop NaN-proof; matched `std::cbrt` exactly on Python 3.11+
  (a method-switch ulp); and kept scipy-less FreeCAD bundles green
  (HAVE_SCIPY-guarded smoke checks; requirements.txt now states scipy is
  required for the spherical engine only — the workbench and the flat model
  run without it).

## [0.45.0] — 2026-07-09 — ITU-R P.1812-6 + delta-Bullington diffraction (§6-D)

### Added
- **P.1812-6 path-specific propagation** via the vendored **ITU-R reference
  implementation** (`emstudio/vendor/py1812/`, permissive license +
  PROVENANCE.md; one vendoring change: the ITU digital-maps load made lazy —
  the maps are NOT redistributed; pass DN/N0 or generate `P1812.npz` with the
  vendored initializer). EMStudio face `emstudio/coverage/p1812.py`:
  `path_loss_db` (full model: LoS + diffraction + troposcatter + ducting,
  validity-enforced 30-6000 MHz / 0.25-3000 km / 1-50 %) and
  **`delta_bullington_intermediates`** — the §4.3.4 delta-Bullington
  diffraction sub-model over a terrain profile with the exact reference input
  construction (median ld50 + the Eq-21/27 intermediates at the β0 radius,
  polarization-aware).

### Validation
- `tests/validation/p1812.py` replays the **official ITU-R SG3 P.1812-6
  validation examples** — 19 profiles / **63 datasets** (vendored with
  provenance): final **Lb and field strength Ep match every official log to
  0.000000 dB**, and the **delta-Bullington intermediates
  (Lbulla/Lbulls/Ldsph) match the official per-equation logs to
  0.000000 dB** on the sampled cases. Debugging the gate surfaced two
  reference-implementation subtleties now documented in the wrapper: the
  official logs record the β0-radius (Eq 7b) diffraction intermediates
  (dl_p's last call) and the log's Eq-70 Ep is 1-kW-normalized. `smoke.py`
  Qt-free map-free-import + spot + validity checks. Green on python3; smoke
  green on 0.21.2 + 1.1.1.

## [0.44.0] — 2026-07-09 — ITU-R P.1546-6 point-to-area prediction (§6-D)

### Added
- **P.1546-6 field-strength prediction** via the vendored **ITU-R WP3K
  reference implementation** (`emstudio/vendor/py1546/` — Py1546 by
  I. Stevanovic/OFCOM, permissive license + PROVENANCE.md; one vendoring
  change: matplotlib made lazy). EMStudio face:
  `emstudio/coverage/p1546.py::field_strength_dbuv_m` (scalar-friendly args,
  mixed land/sea paths, ERP scaling, the Recommendation's optional correction
  chain) with **hard validity enforcement** — 30-4000 MHz / 1-50 % / 1-1000 km
  / heff ≤ 3000 m raise instead of extrapolating (the upstream engine only
  warns). Engine slice (house pattern); coverage-dialog wiring is a follow-up.

### Validation
- `tests/validation/p1546.py` replays the **official ITU-R WP3K P.1546-6
  validation examples** — all 24 SG3 profiles / **52 datasets** (data vendored
  with provenance from the official set, file-verified during the de-risk) —
  through the vendored engine with the harness preprocessing faithfully
  ported: **every predicted field strength matches the official reference to
  0.000000 dB**. Plus wrapper monotonicity + no-extrapolation checks and a
  Qt-free smoke spot check. Green on python3; smoke green on 0.21.2 + 1.1.1.

## [0.43.0] — 2026-07-09 — Causebrook-corrected Deygout diffraction (§6-D)

### Added
- **`deygout_causebrook_loss_db`** (`emstudio/coverage/propagation.py`) — the
  Deygout multiple-edge construction with the **Causebrook & Davis interaction
  correction** (BBC Research Department Report 1971/43 eqs. 13-15, extracted
  from the primary source during the §6-D de-risk): per sub-edge side at the
  top-level split only (recursive application is the classic
  mis-implementation), Ci = max(0, (6 − A1 + Ai)·cos aᵢ) with the eq. 14/15
  distance cosines — countering Deygout's documented over-prediction on
  close/many edges (measured comparisons: Lee & Park IJAP 2018). New
  `method="deygout_causebrook"` in `terrain_profile_loss` /
  `coverage_grid(diffraction=…)` and a 5th Diffraction option in the Area
  Coverage dialog. All other methods byte-identical.

### Validation
- `coverage.py` +6 checks: an exact **by-construction 3-edge fixture**
  (symmetric a=b=c=e geometry → cos a = √⅓; formula reproduced to 1e-9);
  degenerate single edge == uncorrected Deygout exactly; corrections bounded
  (≤ 6 dB/side, Causebrook ≤ Deygout — NTIA 6-edge 34.15 vs 39.42 dB, 4-edge
  98.65 vs 99.88); reversal symmetry; dispatcher wiring. Green on 0.21.2 +
  1.1.1 + python3; still 21 GUI-smoke checks / 30 commands.

## [0.42.1] — 2026-07-09 — Legal disclaimers on every surface and artifact

### Added
- **DISCLAIMER.md**: comprehensive plain-language notice — no warranty (AS IS,
  supplementing LGPL-2.1 §15–16); all outputs are engineering ESTIMATES;
  mandatory independent verification before any reliance; no safety-critical
  use; regulatory/RF-safety compliance is the user's sole responsibility;
  limitation of liability (injury, equipment/property damage, interference,
  fines, all damage classes) for the authors/contributors/AJJ³; assumption of
  risk + hold-harmless; third-party solver disclaimers; "validated" defined
  honestly as specific-test-case reproduction only.
- `emstudio/legal.py` — shared notice strings, embedded where they matter
  most: **every page of every generated PDF report** (the documents that
  travel to build houses) and **every spec/BOM export** (litz, coax, twisted
  pair, bundle), plus a console notice on workbench activation and prominent
  disclaimer blocks in README/HELP/USER_MANUAL/ABOUT.

### Validation
- `smoke.py` guards the layer: DISCLAIMER.md ships, the PDF footer and spec
  exports carry the notice. All gates green on 0.21.2 + 1.1.1 + python3.

## [0.42.0] — 2026-07-09 — Co-site dialog: per-pair NEC2 isolation import (§5 polish)

### Added
- **"From NEC2 matrix…"** in the co-site calculator: runs the shipped
  antenna-isolation-matrix solve on the active document's EM Analysis and
  applies the computed **per-pair** isolation (`isolation_pairs_db` →
  `analyze_site(isolation_db={(i,j): dB})`) to the interference report AND
  the frequency-plan optimizer, replacing the all-pairs scalar; a status line
  shows which source is active and editing the scalar clears the matrix.
  Antenna order maps to the radio-table row order (documented in-dialog).

### Validation
- `cosite.py` +2 checks: the per-pair dict reproduces the scalar report
  exactly for a matching value, and a 60-dB pair drops the interferer by
  exactly 20 dB. `gui_smoke.py` exercises apply → per-pair report → scalar-
  edit clears. Still 21 checks / 30 commands; green 0.21.2 + 1.1.1 + python3.

## [0.41.0] — 2026-07-09 — §2 optimization helpers: solve-for-Z0 (Cable Designer complete)

### Added
- **Coax target-Z0 solver**: `coax.b_for_z0` / `a_for_z0` (exact closed-form
  inversion b = a·exp(2π·Z0·√εr/η0)) + a **"Solve 2b"** row on the coax page.
  Gate: round-trips the RG-58 geometry exactly; b_for_z0(50 Ω) lands on the
  datasheet 1.4605 mm within 2 µm.
- **Twisted-pair target-Z0 solver**: `twisted_pair.lay_for_z0` — bisection on
  the gated monotonic Lefferson Z0(θ) curve, rejecting unreachable targets
  (twist only lowers Z0; 50° manufacturing limit) + a **"Solve lay"** row on
  the pair page (switches εeff off NVP mode, since the solve is a twist-model
  result). Gate: recovers the 30° Lefferson worked example to 0.01°, round-
  trips through `analyze()`, rejects impossible targets.
- The third ROADMAP helper (auto-pack min-OD) shipped with the v0.39 packer.
  With this, **§2 Cable Designer is complete** including its optimization
  helpers; the remaining §2 extras (insulated-bundle C, differential pair
  coupling) are queued behind their own de-risk (research in flight).

### Validation
- `cable.py` +6 checks; `gui_smoke.py` exercises both solve buttons in-dialog
  (coax → exactly 50.00 Ω; pair → 80.00 Ω, NVP mode off) — still 21 checks /
  30 commands. Green on 0.21.2 + 1.1.1 + python3.

## [0.40.0] — 2026-07-09 — Bundle coupling & crosstalk (§2 phase C, electrical slice)

### Added
- **Coupling engine** (`emstudio/wire/coupling.py`): per-unit-length
  multiconductor **L/R/C matrices + weak-coupling crosstalk** for bundle
  conductors, on two validated routes with an explicit validity split:
  the **analytic wide-separation** loop L (Paul MTL 2e eq. 5.23, reference-
  conductor form) + the homogeneous TEM identity **C = μ0ε0·inv(L)** — valid
  when every pairwise separation/conductor-radius ≥ 4 (the printed 5.3 %-at-4
  boundary is gated and flagged) — and **FastHenry loop matrices at any
  spacing**: the existing `per_path` partial N×N matrix with a per-path-radii
  writer extension, the equal-area-square **GMD diagonal correction**
  (+3.458 nH/m per self term), the **partial→loop transform**
  (Zl = Zp[i][j] − Zp[i][ref] − Zp[ref][j] + Zp[ref][ref]) and two-length
  end-effect subtraction. **Crosstalk**: Paul's inductive-capacitive
  weak-coupling model (eqs. 10.29/10.30/10.34) with near/far-end transfer,
  common-impedance floor, the lm/cm dominance rule and the electrically-short
  validity limit. C-matrix honesty documented: identity-C needs the
  electrostatic-consistent L (never DC L, ~20 % error) and holds for bare/
  homogeneous only (insulation shifts entries 50–66 % with per-entry εeff —
  a future dielectric-solve slice).
- **Bundle page crosstalk UI**: a Cond. Ø member column, generator/receptor/
  reference pickers, terminations, run length, report frequency, an
  **analytic instant estimate** (with the s/rw ≥ 4 validity warning) or the
  **FastHenry option** off the GUI thread; NE/FE curves + common-impedance
  floor on the RF tab, lm/cm + dB + dominance in the summary. "Add last
  construction" now carries the conductor Ø (litz = equivalent solid,
  documented; coax/pairs excluded by design in this single-ended slice).

### Validation
- **De-risked first**: a 4-agent workflow fetched Paul's MTL 2e pages
  (Tables 5.4-5.6 verified on page images + an independent 1977 RADC
  printing), the C=μεL⁻¹ identity + conventions, printed crosstalk examples,
  and ran **live FastHenry experiments** (loop-vs-partial equivalence 0.01 %,
  GMD bias curve, Zc.mat format contract); the adversarial cross-check
  recomputed ~40 values, fixed two convention slips, and quantified the
  wide-separation blow-up at touching spacings (+14 % → +136 %) that fixed
  the analytic/FastHenry split. Scratch prototypes reproduced every anchor.
- `cable.py` +19 checks (wide-sep L == printed closed forms and within the
  printed 1.38-2.04 % of Paul's exact MoM; identity-C within 2.5 %; the
  reference-change 0.2408 µH/m; Table 5.4→5.5 reduction to 0.001 pF/m;
  validity curve; **MNE 5.5449 ns / −49.16 dB / 46.2-23.1 mV peaks / 1.94 mV
  CI floor / ×10.85 dominance** vs Paul's printed example; LearnEMC −23 /
  −39.5 dB). `wire_fasthenry.py` gains **gate D** (7 checks): the FastHenry
  loop route lands on the round-wire DC analytics to ±0.02-0.3 % incl. a
  mixed-radius pair (the new per-path radii plumbing). `smoke.py` Qt-free
  anchors; `gui_smoke.py` exercises the in-dialog analytic crosstalk path —
  still **21 checks / 30 commands**. Green on 0.21.2 + 1.1.1 + python3.

## [0.39.0] — 2026-07-09 — Multi-design bundle composer, geometric slice (§2 phase C)

### Added
- **Bundle engine** (`emstudio/wire/bundle.py`, pure math, Qt-free): packs an
  ordered list of member constructions (any mix — coax, twisted pair, single
  wire, litz; each a circular envelope) into a compact bundle cross-section:
  deterministic largest-first **tangency packing** (every candidate position is
  a closed-form tangency point — no scanning) + **minimal-enclosing-circle
  recentering**. Exact on the classic constructions (2 side-by-side → OD 2×,
  3 triangle → 2.1547×, 1+6 hex → OD 3× with fill 7/9); the worst small-n case
  (n = 4 rhombus vs the optimal square) is a documented +13 %. `Bundle` dataclass
  with qty expansion, overall jacket, core/finished OD, fill factor, weight
  roll-up and a spec table. Envelope rules per member kind (twisted pair = 2s,
  its rotating circle). Member-to-member **RLGC/crosstalk is explicitly
  deferred** to its own FastHenry + electrostatic-C de-risk session — this
  slice ships the validated geometry.
- **Bundle page in the Cable Designer** (5th Construction entry): a member
  table (label / envelope OD / qty / kind), an **"Add last construction"**
  button that grabs the envelope of whatever was last computed on the other
  pages (litz/wire finished OD, coax 2b with a no-jacket note, twisted pair
  2s), jacket controls, the packed cross-section (colored by member kind),
  core/finished OD + fill summary and the spec tab.

### Validation
- Packing **de-risked in scratch first**: the naive first-member-at-origin +
  angular-scan approach measured n = 2 at R = 3 (lopsided) and took 5 s for 40
  members; the shipped tangency + MEC algorithm is exact for n = 1/2/3/7 and
  packs 40 members in 0.06 s. `cable.py` grows 15 checks: exact equal-circle
  anchors (R = 1/2/2.1547/3), the n = 4 +15 % compactness bound, 7-hex fill
  = 7/9, no-overlap + containment invariants on three unequal mixes,
  determinism + input-order mapping, the 7×2.5 mm Bundle roll-up (core 7.5 /
  finished 9.5 mm), the twisted-pair 2s envelope rule and the spec's honest
  coupling note. `smoke.py` Qt-free 7-hex check; `gui_smoke.py` cable check
  extended to the bundle page (7-hex OD in-dialog + the grab-last-construction
  flow) — still **21 GUI-smoke checks / 30 commands**. Green on 0.21.2 +
  1.1.1 + python3.

## [0.38.0] — 2026-07-09 — Twisted-pair analytics — Cat5e/Cat6-anchored (§2 phase B)

### Added
- **Twisted-pair engine** (`emstudio/wire/twisted_pair.py`, pure math, Qt-free):
  differential/odd-mode Z0 from the **exact two-wire acosh line** (valid at all
  spacings — the familiar ln(2s/d)/276·log10 forms are +5.3 % at s/d = 2 and are
  not used) + **Lefferson (1971) twist/insulation effective permittivity**
  (εeff = 1 + q(εr−1), q = 0.25 + k·θ², k = 4e-4 film / 1e-3 soft, **θ in
  DEGREES** — the model's dominant failure mode; two public implementations
  evaluate radians and erase the measured ~30 % Z0 reduction at 45°, and the
  gate pins the degrees value AND rejects the radians one), θ = atan(T·π·s),
  VF/C′/L′, wire-length factor 1/cos θ, proximity-exact two-wire conductor loss
  (R′ = (2Rs/πd)·x/√(x²−1)) + dielectric loss, the **RDRE shielded-pair form**
  (thin-wire, d/s ≤ 0.4 flagged) and the datasheet identity `z0_from_c_vf`.
  `analyze()` report dict with an honest `eps_eff_source` (datasheet **NVP**
  mode vs the Lefferson model). **Cat5e/Cat6 U/UTP presets** from primary
  datasheets (24/23 AWG, insulated ODs 0.993/1.029 mm, NVP 0.70).
- **Twisted Pair page in the Cable Designer** (4th Construction entry):
  geometry + insulation class + twist lay + NVP/Lefferson εeff switch +
  optional shield (STP), Z0-vs-lay and attenuation-vs-f plots, two-wire
  cross-section, spec table, and explicit warnings (q > 1 fit regime,
  thin-wire limit, > 50° breakage).

### Validation
- **De-risked first** (per methodology): a 4-agent research workflow pulled the
  Lefferson model (IEEE Trans. PHP-7(4) 1971 via convergent reproductions: the
  Qucs technote eqs. 13.7-13.11, Keller/Springer 2023, a paper-in-hand Usenet
  thread that settled the DEGREES convention against measurement), Cat5e/Cat6
  primary datasheets/patents, printed test vectors, and the RDRE shielded-pair
  form anchored to **Miller's exact BSTJ capacitance tables**; an adversarial
  cross-check recomputed ~40 anchors, found the radians bug in two public
  implementations (gated against), and confirmed the Cat5e geometry lands in
  the 100 ± 15 Ω band only with NVP-derived εeff. A scratch prototype
  reproduced every anchor before repo code.
- `tests/validation/cable.py` grows 30 checks: two-wire kernel 157.926 Ω;
  TEM identities exact; the Lefferson worked example (59.4 Ω / 9.42 tpi /
  VF 0.385, 35° → 53.4 Ω); the degrees control (**89.03 Ω, NOT 94.90**);
  45°-film 30.7 % reduction; q>1 boundary flags; magnet-wire pin 32.64 Ω +
  monotonicity in Lefferson's 10-85 Ω range; **Cat5e 107.7 Ω / Cat6 99.9 Ω in
  the 100 ± 15 Ω fitted band**, C′ 44.2 pF/m vs Belden 49.2 ± 15 %, VF 0.70,
  attenuation one-sided ≤ 22.0/19.8 dB/100 m; shielded form vs **Miller exact**
  at d/s = 0.1/0.2/0.4/0.6 (+0.08/+0.41/+2.1/+5.1 %), 1/√ε scaling exact,
  D→∞ limit, mode identity Z_odd = Z_diff/2, thin-wire flag; the 120/78-Ω
  data-cable C·VF identities (120.3/118.5/78.2 Ω). `smoke.py` Qt-free Cat6 +
  degrees checks; `gui_smoke.py` cable check extended to the twisted-pair page
  (Cat6 preset in-dialog + degrees-correct custom geometry) — still **21
  GUI-smoke checks / 30 commands**. Green on 0.21.2 + 1.1.1 + python3.

## [0.37.0] — 2026-07-09 — Cable Designer UI: Litz | Coax | Single Wire (§2 phase A)

### Added
- **Cable Designer dialog** (`emstudio/ui/cable_dialog.py`) — the Litz / Wire
  Designer shell generalized with a top-level **Construction selector**
  (Litz / stranded Types 1–9 · Coax · Single wire) over the shared
  Cross-Section / RF-AC / Spec tabs. The litz page is the existing designer,
  unchanged. Command id stays `EMStudio_LitzDesigner` (saved toolbars keep
  working); menu text is now **Cable Designer**; `emstudio/ui/litz_dialog.py`
  remains as a back-compat shim. Still **30 commands**.
- **Coax page** — drives the v0.36 analytic TEM engine (`wire/coax.py`):
  Z0/VF/C′/L′/TE11-cutoff + conductor/dielectric attenuation at a report
  frequency, an annulus cross-section, log-log attenuation curves (1 MHz–10 GHz,
  cutoff marked) and a datasheet-style spec table. **RG-58C/U and RG-142B/U
  geometry presets** (`coax.PRESETS`, primary-datasheet values incl. the 0.94×
  stranded-centre effective diameter) and dielectric presets. **Run full-wave
  verify** submits the same (2a, 2b, L) line to the shipped Palace coax
  lumped-port backend (`run_coax`) off the GUI thread and reports the
  matched-line |S11| + the S21-phase velocity factor vs 1/√εr. RG-58 reference
  run: **worst |S11| −31.2 dB, full-wave VF 0.6660 vs analytic 0.6667 (−0.09 %)**.
- **Single-wire page** — solid conductor (AWG/mm/mil) + insulation
  (PVC/PE/PTFE/enamel + wall), reusing the litz analytics with **`ops=[]`**:
  Rdc, exact-Kelvin Rac/Rdc, ampacity, cross-section, spec and the PDF report.

### Fixed
- **Single-conductor Rac/Rdc** (`wire/litz.py`): the internal-proximity term now
  correctly **vanishes for n_strands == 1** — a lone conductor has no other
  strands to bathe it in a transverse field, and its own current redistribution
  IS the Kelvin skin term (the old formula over-reported a solid wire's Rac by
  ~47 % at 1 MHz). The external winding-field term still applies. No shipped
  construction could reach n = 1, and multi-strand results are byte-identical
  (frozen v0.36 regression anchors in the gate).
- Honest spec sheet for `ops=[]`: titled "Wire construction spec" with a
  "solid wire" type row (no litz-type claim). HELP's stale "(dialog button
  coming)" for current sharing removed — the button shipped long ago.

### Validation
- `tests/validation/cable.py` grows 11 checks: PRESETS reproduce the gated
  RG-58 50.0 Ω / 101 pF/m and RG-142 48.0 Ω / VF 70 % numbers; single-wire
  Rdc == 1/(σA) exactly + the **AWG-10 handbook 3.277 mΩ/m** anchor;
  Rac/Rdc == `round_wire_ac_factor` to 1e-12 across 1 kHz–10 MHz; the external
  proximity term still applies at n=1; **frozen Type-2 20×5 AWG-38 anchors**
  prove n≥2 byte-identical; finished OD identity; 20–60 A AWG-10 ampacity
  window; honest wire spec. `report_pdf.py` renders an `ops=[]` wire PDF.
  `smoke.py` adds Qt-free preset + single-wire checks. `gui_smoke.py` adds the
  **cable-designer dialog check** (litz summary → RG-58 preset in-dialog →
  full-wave kwargs marshaling → the verify read-out formatter on a synthetic
  matched line → AWG-10 wire): **21 GUI-smoke checks / 30 commands**, green on
  0.21.2 + 1.1.1 + python3. The end-to-end Palace verify path was additionally
  exercised for real with the RG-58 preset (the −31 dB / −0.09 % numbers above);
  `coax_palace.py` re-run green.

## [0.36.0] — 2026-07-09 — Cable Designer coax analytics engine (§2 phase A start)

### Added
- **Coax TEM analytics engine** (`emstudio/wire/coax.py`) — the Qt-free engine
  slice of the §2 Cable Designer (engine-then-dialog, the §4 small-antenna
  precedent): Z0, velocity factor, C′/L′ per length, TE11 cutoff, and skin-effect
  conductor + dielectric attenuation (dB/100 m) from the geometry
  (a, b, ε_r, tanδ), plus an `analyze()` report dict and a dielectric preset table
  (solid PE / PTFE / foam PE / air). `coax_z0_ohm` matches the shipped,
  Palace-gated `writer.coax_z0` to <1e-6 Ω.

### Validation
- New gate `tests/validation/cable.py` (python3 + freecadcmd) anchored on the
  **primary datasheets** pulled in a de-risk research pass (Belden 8262 RG-58C/U;
  Belden UK / Pasternack RG-142B/U; MIL-DTL-17 cross-checks): RG-58 Z0 = 50.0 Ω
  via the classic **0.94× stranded-centre effective diameter** (physical envelope
  = the documented 47.5 Ω — both gated), VF 66.7 %, C = 100.1 vs 101 pF/m, TE11
  cutoff ~34 GHz; RG-142 geometry = **48.0 Ω** (honestly at the bottom of the MIL
  50 ± 2 window — the canonical 0.037″/0.116″ dimensions do not give exactly 50);
  smooth-conductor attenuation in **55–100 %** of the braided datasheet values at
  10/100/400 MHz (the smooth model under-estimates braid/tinning — documented,
  one-sided gate) with exact √f conductor-loss scaling; TEM identity
  Z0 = √(L′/C′). `smoke.py` adds a Qt-free RG-58 check. Green on 0.21.2 + 1.1.1 +
  python3 (30 commands / 20 GUI-smoke checks — engine slice, no new command).

### Notes
- §2 phase A continues next: the Construction-selector UI (Litz | Coax | Single
  Wire …), single-wire construction (near-free reuse of the litz analytics), the
  "Full-wave verify" hook into the shipped Palace `run_coax`, and the RG-58/RG-142
  presets in the dialog. tanδ values are standard-reference (no datasheet
  publishes them) — documented in the module.

## [0.35.0] — 2026-07-08 — Okumura-Hata / COST-231 empirical models (§6 phase D cont.)

### Added
- **Empirical land-mobile path-loss models** (`emstudio/coverage/empirical.py`) —
  the classic macro-cell clutter models, formulas confirmed against the primary
  sources during a de-risk research pass (Hata 1980; **COST 231 Final Report ch. 4
  eqs 4.4.1–4.4.4**; Rappaport 2e): **Okumura-Hata** (150–1500 MHz; urban
  small/medium + large-city a(hm) variants, suburban −2(log f/28)²−5.4 and open
  −4.78(log f)²+18.33 log f−40.94 corrections) and **COST-231-Hata** (1500–2000 MHz;
  a(hm) always the small/medium form per the Final Report, metropolitan via
  Cm = 3 dB). `empirical_loss_db` dispatches by frequency; validity ranges stated,
  not enforced (warn-don't-block philosophy).
- **`coverage_grid(model="hata", environment=…)`** — a third coverage mode (urban /
  urban_large / suburban / open; the environment category IS the clutter model; DEM
  ignored). The **Area Coverage Map dialog** gains the "Hata / COST-231
  (150 MHz–2 GHz)" model + an **Environment** picker.

### Validation
- `tests/validation/coverage.py` adds: a(hm) small/medium = 1.291 dB @ 900 MHz/2 m;
  the large-city a(hm) ≈ 0 at the 1.5 m reference height; the **externally verified
  worked example** 900 MHz/100 m/2 m/4 km urban → **137.05 dB** (arithmetic
  re-verified against the published calculator example); the distance slope
  (44.9−6.55 log hb)·log 2 (the Patwari 35.2249 coefficient); the environment
  vector 151.02/141.08/122.52 dB + the urban > suburban > open ordering; three
  COST-231 primary-formula regression vectors (139.20/149.45/158.28 dB); the
  frequency dispatch; and the heatmap wiring (probe cell == Ptx − L(d) **exactly**;
  suburban stronger than urban everywhere). `smoke.py` Qt-free check; `gui_smoke.py`
  exercises the Hata model + environment path. Green on 0.21.2 + 1.1.1 + python3
  (30 commands / 20 GUI-smoke checks).

### Notes
- Honest scope: median (50%) loss, macro-cells (hb above rooftops), d 1–20 km;
  outside the fitted ranges the formulas extrapolate but are unvalidated; the
  1500 MHz Hata↔COST-231 hand-over has a small documented step. No land-use raster
  — the environment category is the clutter model. Remaining phase D: Causebrook /
  delta-Bullington, P.1546/P.452/P.2001, spherical-earth ground-wave (GRWAVE
  oracle). Site-name-free.

## [0.34.0] — 2026-07-08 — Bullington diffraction + two-ray on clear terrain paths (§6 phase D cont.)

### Added
- **Bullington equivalent-knife-edge diffraction** (`propagation.bullington_loss_db`)
  — the classic construction: extend the horizon ray from each terminal (to its
  worst-slope obstruction), and their intersection forms ONE equivalent edge whose
  `J(v)` is the path's loss. Deliberately optimistic on multi-obstacle paths
  (documented). `terrain_profile_loss(method="bullington")` +
  `coverage_grid(diffraction="bullington")` + a 4th dialog Diffraction option.
- **Two-ray plane-earth on clear terrain paths** —
  `coverage_grid(ground_reflection=True)` (+ a dialog checkbox): on geometrically
  CLEAR paths (no terrain above the direct ray) the two-ray plane-earth switch
  **replaces** the near-grazing knife-edge term (which would double-count the
  ground), exactly mirroring the smooth-earth branch — closing the documented
  phase-B inconsistency ("terrain and smooth-earth modes disagree over flat
  ground"). Obstructed paths keep free-space + diffraction untouched. Default off
  (byte-identical).

### Validation
- `tests/validation/coverage.py` adds: Bullington vs **NTIA TR-26-580** (Case 23
  2-edge 43.17 dB, Case 13 4-edge 46.22 dB, single-obstacle → J(v)=39.91,
  under-predicts vs EP, reversal symmetry, clear-path → 0); the **NTIA 6-edge
  near-grazing fixture for all three methods** (Bullington 9.767 / EP 38.04 /
  Deygout 39.42 dB); and the two-ray checks — **flat DEM + ground_reflection ==
  smooth-earth footprint EXACTLY (0.00 dB delta, plane-earth governing)** and
  shadowed (diffracted) cells unchanged. `smoke.py` adds a Qt-free Bullington
  anchor. Green on 0.21.2 + 1.1.1 + python3 (30 commands / 20 GUI-smoke checks).

### Notes
- Remaining phase D: Causebrook/delta-Bullington corrections, P.1546/P.452/P.2001 +
  clutter model breadth, and the deferred spherical-earth ground-wave (GRWAVE
  oracle). Site-name-free.

## [0.33.0] — 2026-07-08 — Multi-edge terrain diffraction (§6 phase D)

### Added
- **Multi-edge terrain diffraction** (`emstudio/coverage/propagation.py`) — the
  phase-B terrain mode used only the single dominant (Deygout) knife edge; a real
  profile has several. Adds the **recursive Deygout** method
  (`deygout_multiedge_loss_db` — pick the edge of largest diffraction parameter over
  the tx–rx chord, add its `J(v)`, then recurse on the two sub-paths, each
  re-referenced to its own chord) and the **Epstein–Peterson** method
  (`epstein_peterson_loss_db` — each interior edge diffracts over the chord joining
  its two neighbours). Both **reuse the shipped, already-validated single-edge kernel
  `knife_edge_loss_db` (ITU-R P.526 J(v)) byte-for-byte** — no new special functions.
- **`terrain_profile_loss(..., method=)`** dispatches `"single"` (default — the
  dominant single edge, byte-identical to earlier releases), `"deygout"` (recursive
  multi-edge) or `"epstein_peterson"`.
- **`heatmap.coverage_grid(..., diffraction="single")`** threads the method into the
  DEM terrain footprint; default `"single"` is byte-identical to v0.32.0 (existing
  coverage gate unchanged). The **Area Coverage Map dialog** gains a **Diffraction**
  selector (Single-edge / Multi-edge Deygout / Epstein–Peterson) in the Terrain group.

### Validation
- `tests/validation/coverage.py` adds the multi-edge chain gated against the **NTIA
  TR-26-580** worked cases (λ=0.2 m): the J(v) kernel (J(0)=6.0, J(1)=13.9,
  J(2.4)=20.5, J(−0.78)=0); a degenerate single obstacle → J(22.45)=39.91 dB (Deygout
  **and** EP), and equal to the shipped single-edge loss; **Case 23** (2-edge) Deygout
  73.29 dB / EP 70.52 dB; **Case 13** (4-edge) Deygout 99.88 dB / EP 95.71 dB; the
  Deygout≥EP ordering; **reversal symmetry** (tx↔rx); a cleared path → 0 dB; and the
  DEM wiring (multi-edge loss ≥ single-edge everywhere, strictly more behind two
  ridges). `tests/smoke.py` adds a Qt-free multi-edge check. Green on FreeCAD 0.21.2 +
  1.1.1 + python3 (still 30 commands / 20 GUI-smoke checks).
- **De-risked first** (per methodology): a research pass compared this slice against
  the spherical-earth ground-wave extension; multi-edge was chosen because it is
  cleanly gate-able against published worked examples and reuses the shipped J(v),
  whereas the spherical-earth-over-sea residue solver has no printed test vector
  (needs a bundled GRWAVE oracle — deferred). A scratch prototype reproduced every
  NTIA anchor before repo code.

### Notes
- Deygout here is **uncorrected** (no Causebrook term) — it over-estimates deep
  multi-edge shadows, Epstein–Peterson under-estimates; each method is gated against
  its own tabulated value, not a single "true" number. The default terrain mode stays
  single-edge. Deferred phase-D work: the spherical-earth ground-wave beyond ~100 km
  (needs a GRWAVE oracle to gate), two-ray ground reflection, and the P.1546/P.452/
  P.2001 + clutter model breadth. Bullington / Causebrook / delta-Bullington are a
  follow-up.

## [0.32.0] — 2026-07-08 — Multi-station service & interference (D/U) contours (§6 phase C cont.)

### Added
- **Multi-station D/U contours** (`emstudio/coverage/multistation.py`) — composes two
  or more single-station coverage footprints (the shipped `heatmap.coverage_grid`)
  onto **one shared lat/lon grid** and, per cell, thresholds the wanted-to-unwanted
  field-strength ratio (D/U) against an FCC/ITU protection ratio, classifying each
  cell **NO_SERVICE / INTERFERENCE_LIMITED / SERVED** by the standard **two gates**:
  Gate A (wanted field ≥ a protected/service threshold) and Gate B (D/U ≥ protection
  ratio). Adjacent-channel ratios may be negative (receiver selectivity) — D/U is not
  clamped.
- **Interferer aggregation** — `combine_fields_dbuv_m` offers **incoherent power sum**
  (`E = 10·log10(Σ 10^(Eᵢ/10))` dBµV/m; two equal fields add exactly `10·log10(2) =
  +3.0103 dB` — ITU-R BT.2265 / NTIA) and **worst-case** (the single strongest
  interferer — FCC OET-69 DTV policy).
- **Reference protection-ratio & service-threshold libraries** — source-tagged
  `PROTECTION_RATIOS` (FM co-channel 20 dB FCC 73.215; ITU-R BS.412 stereo 45 dB;
  AM/MF co-channel 26 dB FCC/Region 2; GE75 30 dB; DTV 15 dB; analog-TV 30 dB; …) and
  `SERVICE_THRESHOLDS_DBUV_M` (FM 60/57/54 dBµV/m; AM 66/54 dBµV/m). Region/method-
  dependent — presets, not hard-coded universals.
- **`service_contour`** (a wanted station vs its co-channel interferers) and
  **`best_server`** (a network view: each cell served by its strongest station, D/U vs
  the power-sum of the rest). Co-channel selection reuses the **§5 co-site** logic
  (`interference.in_band` / `du_ratio_db`). KML export of any D/U layer via the shipped
  `coverage.kml` primitives (`export_service_kml`).
- **Multi-Station Service / Interference dialog + command** (`EMStudio_MultiCoverage`,
  Tools group → **30 GUI commands**): an editable transmitter table, wanted-station +
  protection/service presets, power-sum/worst-case combine, ground-wave/auto model,
  and a map with Service-classified / D/U-ratio / field / best-server layers + KML.
- **`heatmap.coverage_grid`** gains an opt-in explicit-grid mode (`lats=`/`lons=`) so
  several stations can be evaluated on one common grid. Omitting them is **byte-
  identical** to the tx-centred box (existing gate unchanged).

### Validation
- `tests/validation/coverage.py` adds the multi-station chain: the power-sum combine
  anchors (two equal → +3.0103 dB, N → 10·log10(N), ITU-R BT.2265 34,33 → 36.539), the
  two-gate classify (an FCC OET-69 served/interfered worked cell), the source-tagged
  protection-ratio library (FM 20 dB, AM 26 dB = 20:1), an end-to-end two-station D/U
  map (high toward wanted / negative toward interferer; served + interference-limited
  cells), **D/U reciprocity** (swap wanted↔interferer → sign flip), power-sum ≤
  worst-case ordering, co-channel `channel_bw_hz` filtering, the best-server split, and
  KML export.
- `tests/smoke.py` adds a Qt-free multi-station check (power-sum combine + two-gate
  classify + protection-ratio library). `tests/gui_smoke.py` exercises the new dialog
  end to end (**20 checks**). Green on FreeCAD 0.21.2 + 1.1.1 + python3.
- **De-risked first** (per methodology): five parallel research agents pulled the exact
  FCC/ITU protection ratios + the field power-sum method from primary sources
  (47 CFR 73.182/73.215/73.509/73.620, ITU-R BS.412/BS.560/BT.655/BT.2265, NTIA), and a
  scratch prototype reproduced the composition math before any repo code.

### Notes
- Honest scope: the D/U composition inherits its per-station physics from the shipped
  footprints (auto = free-space/plane-earth ± DEM diffraction; ground-wave = P.368
  flat-earth, ~100 km). Protection ratios are regulatory/planning reference values,
  region- and method-dependent (documented per preset). Station locations/frequencies/
  ground are user-supplied; no specific sites are referenced.

## [0.31.0] — 2026-07-07 — LF/MF ground-wave propagation (ITU-R P.368) (§6 phase C)

### Added
- **LF/MF ground-wave (surface-wave) model** (`emstudio/coverage/groundwave.py`) — the
  band below ~30 MHz AJ called out, where a vertically-polarised wave clings to the
  earth and the ground's conductivity/permittivity set the decay rate. Implements the
  **ITU-R P.368 / Norton flat-earth** theory exactly as in the ITU *Handbook on Ground
  Wave Propagation* (R-HDB-59, 2014): complex permittivity `ε_c = ε_r − j·60λσ`, the
  complex **numerical distance** `ρ = −j(πR/λ)(ε_c−1)/ε_c²`, the attenuation function
  `|A| = (2+0.3ρ)/(2+ρ+0.6ρ²)`, and the P.368 field reference (a short vertical
  monopole over perfect ground radiating 1 kW → **300 mV/m at 1 km**, CMF 300 V).
  Ground presets are **ITU-R P.368 Table 2** (sea water … very dry ground).
- **Millington mixed-path method** (`groundwave.millington_field_dbuv_m`) — combines
  homogeneous-path fields over segments of different conductivity (e.g. land/sea) by
  the forward+reverse (reciprocity) average, so a land↔sea swap gives the same field
  and a better-conducting far segment "recovers" the field.
- **Ground-wave coverage mode** — `heatmap.coverage_grid(model="ground_wave",
  ground=(ε_r, σ))` produces an LF/MF field-strength footprint over homogeneous
  ground (a smooth-earth model — the DEM/heights are not used). Default `model="auto"`
  is byte-identical to v0.30.0 (existing gate unchanged).
- **Coverage dialog** gains a **Propagation model** selector (Auto vs Ground-wave
  LF/MF) and a **Ground type** picker (P.368 Table 2), with the map title/stats noting
  the model.

### Validation
- `tests/validation/coverage.py` now also gates the ground-wave model against the ITU
  Handbook's own worked chain: worked example 1 (σ=5e-5, ε_r=15, 2 MHz, 20 km → |ρ|≈26,
  |A|≈0.0226) and example 2 (1 MHz, medium ground, 100 km → |ρ|≈43.5, field ≈31.6
  dBµV/m); the `|A|→1` (ρ→0) and `|A|→1/(2ρ)` (ρ→∞) asymptotes; the P.368 300 mV/m /
  300 V normalization; the sea > wet > dry and lower-frequency-goes-farther orderings;
  and Millington single-segment degeneracy + reciprocity + bracketing. `tests/smoke.py`
  gains a Qt-free ground-wave check; `tests/gui_smoke.py` exercises the ground-wave
  dialog path. Green on FreeCAD 0.21.2 + 1.1.1 (headless + offscreen GUI) and python3.
  *(De-risked first: five parallel research agents nailed the ITU-R/Norton formulas +
  worked examples from primary sources; a scratch prototype reproduced them before any
  repo code was written.)*

### Scope / honesty
- Flat-earth surface wave, valid to ~100 km; beyond that curved-earth diffraction
  dominates and this model over-attenuates (a spherical-earth residue series is a later
  slice). Ground-wave mode is smooth-homogeneous-earth; it does not use terrain.

## [0.30.0] — 2026-07-07 — Area coverage maps: DEM import, terrain shadowing & KML (§6 phase B)

### Added
- **DEM import with no heavy geo dependency** (`emstudio/coverage/terrain.py`).
  Reads SRTM/NASADEM **`.hgt`** tiles directly (big-endian int16, north-up, 1° tile
  corner from the filename; SRTM3 1201² / SRTM1 3601²) and a **minimal pure-python
  GeoTIFF** reader for the common single-strip uncompressed/DEFLATE case
  (`ModelPixelScale` + `ModelTiepoint` georeferencing; stdlib `zlib`). A `DEM`
  mosaics one or more tiles and answers `elevation(lat, lon)` by bilinear
  interpolation. LZW/tiled/multi-band GeoTIFFs raise a clear "use .hgt or
  `gdal_translate`" message — no GDAL/rasterio needed (they're absent from FreeCAD's
  bundled Python).
- **Great-circle geodesy** (`emstudio/coverage/geodesy.py`): haversine distance,
  initial bearing, destination, slerp interpolation, path sampling, and the
  effective-earth-radius (4/3) **bulge**.
- **Terrain path-profile extraction** (`terrain.path_profile`): samples the great
  circle from the transmitter to a point, looks up the DEM under each sample, and
  adds the earth bulge, feeding the shipped `propagation.terrain_profile_loss`
  (single-edge Deygout) so hills shadow the result.
- **Antenna-pattern modulation** (`emstudio/coverage/pattern.py`): `AzimuthPattern`
  takes the horizontal cut from a NEC2/openEMS `FarFieldResult` (at a take-off
  elevation + a compass orientation), or omni at the peak gain.
- **Area coverage heatmap for one station** (`emstudio/coverage/heatmap.py`):
  `coverage_grid` computes received power (dBm) and field strength (dBµV/m) over a
  lat/lon grid. Two modes on one path — **smooth earth** (no DEM: free-space
  switching to two-ray plane-earth d⁴ beyond the breakpoint; degenerates *exactly*
  to a link budget over free-space loss) and **terrain-aware** (with a DEM). Reports
  coverage-fraction above a threshold.
- **KML export** (`emstudio/coverage/kml.py`): a Google-Earth `GroundOverlay` — a
  colour-mapped PNG (matplotlib, lazy-imported) draped over the grid's lat/lon box
  with a transmitter placemark. The KML document is a pure-string build (gate-checked
  without any image library).
- **Area Coverage Map dialog + command** (`EMStudio_Coverage`, in the Tools group →
  **29 GUI commands**): transmitter placement, grid/metric/threshold/k-factor,
  optional DEM browse, optional far-field-pattern CSV, a heatmap map view with
  colour bar + stats, and Export-KML. Transmitter location is user-supplied; no
  specific sites referenced.

### Validation
- New gate `tests/validation/coverage.py` (python3): synthesizes DEM fixtures (a
  Gaussian hill in `.hgt` and in uncompressed **and** DEFLATE GeoTIFF), then checks
  geodesy vs known values (incl. London–Paris 343.5 km), `.hgt`/GeoTIFF round-trip +
  bilinear-vs-analytic (<1.5 m), the hill as the controlling Deygout edge, earth
  bulge increasing loss, the **exact EIRP−FSPL degeneracy** of a cleared omni link,
  plane-earth governing beyond the breakpoint, a **DEM ridge shadowing** cells behind
  it, directional-pattern lobing, and a well-formed KML GroundOverlay + PNG.
- `tests/smoke.py` gains a Qt-free coverage-engine check (geodesy + `.hgt` round-trip
  + heatmap degeneracy + KML XML); `tests/gui_smoke.py` gains the coverage-dialog
  path → **19 checks**. Green on FreeCAD 0.21.2 + 1.1.1 (headless smoke + offscreen
  GUI) and python3.

## [0.29.0] — 2026-07-07 — Grouped toolbars/menus + expanded antenna-builder scope

### Changed
- **Toolbar & menu reorganised into logical groups.** The 28 commands are no longer
  one long strip: `commands.COMMAND_GROUPS` drives one toolbar + one EMStudio submenu
  per group — **Analysis** (analysis/material/port/coil, solvers, run/sweep),
  **Templates** (antennas · waveguide & RF · magnetics, separated), **Tools** (Litz,
  Small-Antenna, Isolation, Co-site, Link Budget), **Setup** (Detect/Install). InitGui
  builds them from that single source of truth; a smoke guard asserts the groups cover
  exactly the registered commands (no orphans, no command in two groups). Green on
  FreeCAD 0.21.2 + 1.1.1.

### Roadmap (spec only — no code)
- **Expanded the §1 AI-Antenna-Builder type library** at AJ's request: **phased &
  steered arrays** (geometry/spacing/taper/scan-angle, mutual-coupling via the shipped
  isolation matrix); a first-class **RFDF** subsystem (Adcock/Watson-Watt amplitude
  comparison; **linear / circular / correlative interferometry**; pseudo-Doppler /
  **commutated CDAA**; ambiguity & accuracy); **multi-band / multi-frequency** antennas
  and — as AJ asked — a **combiner / diplexer matching-network recommender** for
  feeding several band-specific antennas (e.g. VHF+UHF HDTV) on one line, reporting
  per-branch insertion loss / isolation / combined VSWR; plus **fractal**, **slot**,
  **cone/biconical/discone**, spiral/Vivaldi/DRA/leaky-wave/Luneburg families. Recorded
  in ROADMAP §1 (phasing C/D/E). *(One term, "lebaric", is read tentatively as Luneburg
  lens — flagged for confirmation.)* The antenna builder remains the LAST epic per AJ's
  build order (so it wraps the finished feature set); these are captured now.

## [0.28.0] — 2026-07-07 — Point-to-point propagation / link budget (§6, phase A)

### Added (validated)
- **Propagation models** (`emstudio/coverage/propagation.py`, new `coverage`
  package): the analytic point-to-point path-loss library, each with its stated
  valid regime — **free-space** (Friis), **single knife-edge diffraction** (ITU-R
  P.526 J(v) + the Fresnel diffraction parameter), **two-ray plane-earth** (d⁴ law +
  breakpoint), the **ITU field-strength** relation from EIRP (dBµV/m, for broadcast
  contours), a **terrain-profile** loss via the first-order (Deygout) dominant knife
  edge, and a **link budget** (received power + fade margin). Pure-python, Qt-free.
- **Point-to-Point Link Budget** dialog + toolbar command
  (`emstudio/ui/link_dialog.py`, `EMStudio_LinkBudget`): link inputs → path loss
  (free-space vs plane-earth, breakpoint-aware), received power, fade margin and
  field strength, with a path-loss-vs-distance plot. **28 GUI commands.**

### Validated / gated
- **New gate `tests/validation/propagation.py`** (python3): FSPL 81.98 dB @ 1 km/
  300 MHz; knife-edge J(0)=6.0 / J(1)=13.9 / J(2.4)=20.6 dB and clear-path 0;
  plane-earth d⁴ (+12 dB per doubling, 80 dB @ 1 km/10 m/10 m); field strength
  104.8 dBµV/m @ 1 kW EIRP/1 km (matches P_EIRP(dBW)+74.8−20log10(d_km)); terrain
  single-edge diffraction over a synthetic hill; link budget. `tests/smoke.py` adds
  a Qt-free engine check; `tests/gui_smoke.py` (now **18 checks**) adds the dialog.
  Green on FreeCAD 0.21.2 + 1.1.1.

### Notes
- Starts **ROADMAP §6 (geographic coverage / propagation)** with the analytic
  point-to-point core. Next: phase B — DEM import (SRTM/ASTER), path-profile
  extraction over real terrain, and area coverage heatmaps + KML; then LF/MF
  ground-wave (ITU-R P.368) and the model library. Transmitter locations are
  user-supplied; no specific sites are referenced.

## [0.27.0] — 2026-07-07 — Frequency-plan optimizer (§5, phase C — §5 complete)

### Added (validated)
- **Frequency-plan optimizer** (`emstudio/cosite/interference.py`): searches
  transmit-channel assignments that minimise co-site interference. `plan_cost()`
  scores a plan (weighted IMD hits + desensitization + co-channel clashes, plus a
  severity term); `optimize_frequency_plan()` retunes the tunable transmitters over
  candidate channel lists — exhaustive when the space is small, greedy
  coordinate-descent otherwise — and returns the best plan with before/after cost.
- **"Optimize TX frequencies"** button in the Co-site Interference Calculator: grids
  each transmitter ±8 channels around its current frequency, applies the best plan
  to the table and re-analyses, showing the retune and the cost drop.

### Validated / gated
- `tests/validation/cosite.py` extended: a dirty plan (2f1−f2 landing on a robust
  victim) is driven to **cost 0** by the exhaustive optimizer (16 plans evaluated),
  which reassigns a carrier off the collision. `tests/smoke.py` adds an optimizer
  check; `tests/gui_smoke.py` exercises the dialog's Optimize button. Green on
  FreeCAD 0.21.2 + 1.1.1.

### Notes
- Completes **ROADMAP §5 (co-site interference)** — phase A isolation matrix
  (v0.26.0) + phase B interference calculator (v0.25.0) + phase C frequency-plan
  optimizer (this). Next epic: §6 geographic coverage / propagation (a large new
  subsystem — de-risk a propagation model vs an ITU worked example first). Radio
  sets stay generic / user-supplied.

## [0.26.0] — 2026-07-07 — Antenna isolation matrix from NEC2 (§5, phase A)

### Added (validated)
- **Antenna-to-antenna isolation/coupling matrix** (`emstudio/cosite/isolation.py`):
  the device-level input to the co-site calculator, extracted from NEC2 with the
  **Y-matrix method** — drive each of N wire antennas in turn with a 1 V source and
  leave the others as continuous (shorted) wires, read each feed-segment current →
  a column of the admittance matrix Y; invert Y → Z, convert Z → S, isolation
  `= -20log10|S_ij|`. Reciprocity (`Z_ij == Z_ji`) is a built-in self-check.
  Honours the solver's GroundType. `isolation_pairs_db()` feeds the result straight
  into `interference.analyze_site(isolation_db=...)`.
- **Co-site Antenna Pair template** + **Antenna Isolation Matrix** command
  (`emstudio/templates/cosite_pair.py`, `EMStudio_TemplateCositePair` /
  `EMStudio_IsolationMatrix`): two parallel λ/2 dipoles at 0.5 λ, with a one-click
  isolation extraction that pops the matrix + mutual impedances. **27 GUI commands.**

### Validated / gated
- **New gate `tests/validation/isolation_nec2.py`** (freecadcmd): two λ/2 dipoles at
  0.5 λ → **|S21| −13.78 dB** (isolation 13.8 dB), **Z21 −15.0 − j28.0 Ω** vs the
  Balanis parallel-dipole table (−12.5 − j29.9 Ω, ~10%), driven-element Z11 ≈ 72 Ω,
  and **reciprocity error 1e-14**. `tests/gui_smoke.py` (now **17 checks**) adds the
  isolation solve loop. All green on FreeCAD 0.21.2 + 1.1.1.

### Notes
- Completes ROADMAP §5 phases A + B: the isolation matrix (this) now supplies the
  per-pair coupling the interference calculator (v0.25.0) consumes. Next: §5 phase C
  (frequency-plan optimizer) or §6 coverage/propagation. Radio lists / antenna sets
  are generic / user-supplied.

## [0.25.0] — 2026-07-07 — Co-site interference calculator (§5, phase B)

### Added (validated)
- **Co-site interference engine** (`emstudio/cosite/interference.py`): the
  deterministic system-level EMC calculator. Over a list of co-located radios
  (each a transmitter and/or receiver) plus the antenna-to-antenna isolation it
  computes the four classic co-site mechanisms — **intermodulation** (product
  frequencies at integer combinations of the carriers + levels via the
  intercept-point relation `P = Σ|aᵢ|Pᵢ − (N−1)·IPₙ`), **receiver
  desensitization** (strong off-channel carrier past the front-end blocking
  level), **broadband transmitter noise** into a victim's passband, and
  **frequency-plan clashes** (co-channel carriers with a D/U ratio). Pure-python,
  Qt-free.
- **Co-site Interference Calculator** dialog + toolbar command
  (`emstudio/ui/cosite_dialog.py`, `EMStudio_Cosite`): an editable radio table +
  isolation/junction-IP3/order inputs → a text report and a **frequency-map** plot
  (transmit carriers, receiver passbands, and intermod products at a glance).
  **25 GUI commands.**

### Validated / gated
- **New gate `tests/validation/cosite.py`** (python3): IMD product frequencies
  (two-tone 2f1−f2/2f2−f1, sum/difference, three-tone f1+f2−f3); the
  intercept-point IMD level (two equal −10 dBm tones, OIP3 +30 → IMD3 −90 dBm;
  unequal tones); received power = tx − isolation; broadband-noise integration;
  and the whole-site analysis (a 2f1−f2 product landing on a victim receiver,
  desensitization margin, co-channel D/U).
- `tests/smoke.py` adds a Qt-free co-site engine check; `tests/gui_smoke.py`
  (now **16 checks**) adds the calculator dialog construct/analyze. All green on
  FreeCAD 0.21.2 + 1.1.1.

### Notes
- ROADMAP §5 phase B (the deterministic interference calculator). Phase A — the
  antenna-to-antenna **isolation matrix** from the multi-port field solvers — is
  de-risked (nec2c Y-matrix method: two λ/2 dipoles at 0.5λ → |S21| −13.78 dB vs
  the Balanis mutual-impedance table) and is the next slice; its output feeds this
  calculator's per-pair isolation. Radio lists are generic / user-supplied.

## [0.24.0] — 2026-07-07 — NEC2 monopole over ground: VLF/LF characterization (§4)

### Added (validated)
- **NEC2 ground modeling** (`emstudio/solvers/nec2/writer.py`): the NEC2 backend
  can now drive a **monopole/antenna over a ground plane** at LF/VLF. New
  `SolverNEC2.GroundType` — *None (free space)* (default, unchanged), *Perfect
  (PEC image)* (`GE 1`/`GN 1`), or *Finite (Sommerfeld)* (`GN 2` with
  `GroundEpsilonR`/`GroundConductivity` — real earth loss). A wire whose base sits
  on z=0 is **fed at its base segment** when a ground is present (monopole
  convention); free-space analyses keep the center feed and are **byte-identical**
  to before.
- **Monopole-over-ground template** + toolbar command (`Template: Monopole over
  Ground (VLF/LF)`, `emstudio/templates/monopole.py`): a base-fed short λ/10
  vertical mast at 100 kHz, perfect ground by default (switch the solver's
  `GroundType` to *Finite* for earth loss). **24 GUI commands.**

### Validated / gated
- **New gate `tests/validation/monopole_nec2.py`** (freecadcmd) — the first
  **VLF/LF** NEC2 validation (the prior NEC2 point was 296 MHz free-space):
  - short λ/10 monopole, **perfect ground → Re(Zin) 4.02 Ω** (analytic radiation
    resistance Rr = 40π²(h/λ)² = 3.95 Ω), strongly capacitive (−570 Ω);
  - λ/4 monopole, perfect ground → **39.5 + j22.6 Ω** (textbook 36.5 + j21);
  - short λ/10 monopole, **finite average ground (εr 13, σ 0.005 S/m) → Re 79.6 Ω,
    radiation efficiency ≈ 5 %** — the defining VLF ground-loss reality.
- `tests/smoke.py` adds a Qt-free ground-card unit check (proves free space stays
  `GE 0`/center-feed byte-identical; ground opt-in emits `GE 1`/`GN` + base feed).
- `tests/gui_smoke.py` (now **14 checks**) adds the monopole-over-ground solve loop
  under a real (offscreen) FreeCAD. Dipole gate re-run green (no regression). All
  green on FreeCAD 0.21.2 + 1.1.1.

### Notes
- Completes the core of ROADMAP §4 (VLF/LF → mmWave honest multi-method span):
  analytic small-antenna models + dialog + band→method picker (v0.22–0.23) **and**
  NEC2-with-ground for the wire/monopole structure (v0.24). De-risked against nec2c
  1.3.1. Buried radials need NEC-4/`GD` (nec2c lacks it) — model counterpoises as
  slightly-elevated wires. Next: §5 co-site interference.

## [0.23.0] — 2026-07-07 — Small-Antenna Designer dialog + band→method picker (§4)

### Added (validated)
- **Small-Antenna Designer** dialog + toolbar command (`Small-Antenna Designer
  (VLF/LF)`, `emstudio/ui/small_antenna_dialog.py`): the analytic analogue of the
  Litz designer for the electrically-small regime. Left column — antenna type
  (short monopole / dipole / small loop), frequency (with representative VLF/LF/MF
  band presets, e.g. VLF 24 kHz / LF 40 kHz), geometry, and the loss
  budget. Right tabs — Predicted Performance (Rr, effective height, efficiency,
  Chu Q/bandwidth, monopole loading), a dimension-annotated **2-D sketch** with the
  triangular current distribution, and the **Chu Q-limit** plot with the design
  point marked. Wraps the Qt-free `small_antenna.py` analytics (23 GUI commands).
- **Band → recommended-method picker** (`emstudio/antenna/band_picker.py`): the
  honest multi-method router. Maps a frequency (and optional antenna size) to the
  EMStudio method that is actually valid there — VLF/LF/MF → analytic small-antenna
  + NEC2-with-ground; HF→low-µW → NEC2 (wire) / openEMS / Palace; µW→mmWave →
  Palace / openEMS — each with a one-line rationale and the validity caveat stated
  up front. Full ITU band table (ELF…EHF). Deterministic core the dialog shows in a
  banner and the future §3 AI assistant will call.

### Validated / gated
- `tests/validation/small_antenna.py` extended: band classification (VLF/LF/UHF/EHF
  edges, 10 kHz floor), VLF→small-antenna+ground routing, 300 MHz→NEC2, 40 GHz→Palace,
  electrically-small size note, summary rendering.
- `tests/gui_smoke.py` (now 13 checks): the Small-Antenna Designer constructs and
  computes under a real (offscreen) FreeCAD on both 0.21.2 and 1.1.1 — a 24 kHz
  VLF-band monopole is confirmed electrically small with the band→method banner.

### Notes
- Continues ROADMAP §4 (VLF/LF → mmWave). Still pure analytic. The NEC2-driven LF
  monopole-over-ground capability (de-risked this session against nec2c: perfect
  ground `GE 1`/`GN 1` short-monopole Re(Zin) 4.03 Ω vs analytic Rr 3.95 Ω;
  finite-ground `GN 2` efficiency 100%→17%→4% for sea/avg/poor soil) is the next slice.

## [0.22.1] — 2026-07-07 — Small loop antenna (completes the small-antenna trio)

### Added (validated)
- **Electrically-small loop** in `small_antenna.short_loop` (the VLF/LF receive /
  direction-finding antenna; dual of the short dipole): Rr = 31171·N²·(A/λ²)²,
  effective height 2πNA/λ, Chu Q/efficiency. Gate checks the Balanis constant, the
  N² turns scaling, and he — completing the dipole/monopole/loop set.

## [0.22.0] — 2026-07-07 — VLF/LF electrically-small antenna analytics (§4 MVP)

### Added (validated)
- **Electrically-small antenna module** (`emstudio/antenna/small_antenna.py`) for
  **VLF/LF/MF characterization**, where antennas are a tiny fraction of a wavelength
  and the full-wave field solvers are impractical (the Chu-Harrington regime). Closed
  forms (Balanis/Kraus/Watt): short **dipole** and **monopole** radiation resistance
  (Rr = 20π²(L/λ)² / 40π²(h/λ)²), effective length/height, radiation efficiency from
  the loss budget, the **Chu minimum-Q / bandwidth** small-antenna guardrail, and the
  **series loading inductance** needed to resonate the capacitive reactance.
- **Gate** (`tests/validation/small_antenna.py`): matches the textbook results
  (short-dipole Rr 1.9739 Ω and monopole 3.9478 Ω at L=λ/10; monopole Rr = 2× dipole;
  Chu Q = 10 at ka=0.5; bandwidth (S−1)/(Q√S)). Honest VLF case: a 100 m monopole at
  30 kHz is electrically tiny (Rr 0.04 Ω, Chu Q ≈ 4040, needs a 48.5 mH loading coil).

### Notes
- First slice of ROADMAP §4 (VLF/LF → mmWave). Pure analytic, no solver. Follow-ons:
  NEC2 driven at LF with a ground/counterpoise model, a small-antenna dialog, and a
  band→recommended-method picker.

## [0.21.0] — 2026-07-07 — Palace general-BREP DRIVEN ports (circular waveguide)

### Added (validated)
- **General 3-D geometry for DRIVEN S-parameter analyses** — wave ports on
  **arbitrary closed solids**, not just axis-aligned boxes (the driven analogue of
  the v0.18.0 eigenmode BREP path). Any solid is exported to a BREP; its two end
  faces (perpendicular to the longest axis) are slab-tagged as wave ports and the
  rest is PEC. A non-box solid on a "Driven S-parameters" analysis now routes to
  this path automatically. **New Circular Waveguide template** on the toolbar
  (**22 GUI commands**).
- **Gate** (`tests/validation/circwaveguide_palace.py`): (1) a **WR-90 box exported
  as a BREP reproduces the validated box waveguide** — |S11| −68.9 dB, |S21|
  deviation 1.3e-4 dB across X-band (the control proving the mechanism); (2) a
  **circular waveguide** (R=30 mm, TE11 cutoff 2.928 GHz) is **evanescent below
  cutoff** (|S21| −50.8 dB at 2.5 GHz) and **propagates lossless above**
  (−0.0005 dB at 3.0/3.5 GHz) — the analytic proof that arbitrary CURVED port
  faces work. Palace's Mode-1 wave port finds the TE11 mode on the circular face
  automatically.

### Notes
- Additive / non-regression: `build_waveguide_model` falls back to the BREP path
  only for non-box solids (mirrors `build_cavity_model`); `run()` dispatches on
  `model["kind"]`, so the box waveguide and coax lumped-port paths run identical
  code. The BREP-driven mesher emits the SAME physical-group attributes (interior=1,
  port1=2, port2=3, walls=4) as the box mesher, so `build_driven_config` and
  `parse_sparams` are unchanged. Default FEM order for the BREP driven path is 2
  (order 3 is very slow per point on a curved guide, worst at below-cutoff points).
  All existing Palace gates re-ran green.

## [0.20.2] — 2026-07-07 — Quasi-static frequency-validity guard (auto-warn)

### Added
- **Auto-warn guard** (`emstudio/solvers/validity.py`): the magneto-quasistatic
  Elmer path now warns — via a report-view message, the solver log, and a banner in
  the Magnetics Results dialog — when a magnetics analysis is set up **outside the
  electrically-small regime** (largest dimension ≥ λ/10 at the operating frequency),
  where the quasi-static approximation (displacement current dropped) is no longer
  physical. The warning names the highest valid frequency for that geometry and
  points to the full-wave path (Palace/openEMS). It **never blocks** the run.
- **Gate** (`tests/validation/freq_guard.py`): the guard is silent for a 10 cm coil
  at 100 kHz–1 MHz, warns at 40 GHz, and the λ/10 boundary is physically correct
  (~300 MHz ceiling for a 0.10 m object). gui_smoke exercises it through the real
  GUI magnetics geometry path.

### Notes
- Honest scoping (see CAPABILITIES "Frequency range"): "DC → 40 GHz+" applies to the
  **full-wave** analyses (Palace gated to 57 GHz; openEMS/NEC2 broadband). The
  magnetics (Elmer) and cable-R/L (FastHenry) tools are quasi-static **by design** and
  low-frequency only — this guard makes that limit visible to the user rather than
  silently returning non-physical numbers.

## [0.20.1] — 2026-07-07 — Frequency-range validation (mmWave) + limitations documented

### Added (validated)
- **mmWave gate** (`tests/validation/mmwave_palace.py`): backs the "DC to 40 GHz and
  beyond" claim for the full-wave path. Palace reproduces closed-form cavity TE101 at
  **39.03 GHz (+0.003 %)** and **56.91 GHz (+0.002 %)**, and a WR-22 waveguide driven
  over **38–42 GHz** looks like a matched TE10 line (|S21| dev 5.4e-6 dB, |S11|
  −106 dB). The upper bound on full-wave analyses is mesh/memory, not a physics break.

### Documentation
- **`docs/CAPABILITIES.md` → "Frequency range & validity (DC → mmWave)"**: an honest
  per-engine table. Full-wave engines (openEMS FDTD, NEC2 MoM, Palace FEM) span HF→
  mmWave; the **quasi-static** engines (Elmer magnetics ~DC–few MHz, FastHenry R/L
  ~DC–low-GHz) are low-frequency **by design** and must not be used for radiating /
  electrically-large problems — the one hard limitation to know.
- **`docs/ROADMAP.md` → AI antenna builder "LLM backend"**: decision + recommended
  open-weight models for ajj3-brain (Free/Standard/Pro tiers), the "reliability comes
  from grammar-constrained decoding, not model size" note, and why we do **not** train
  a bespoke model (the LLM only maps text↔fields + writes explanations; all physics is
  deterministic).

## [0.20.0] — 2026-07-07 — Palace adaptive mesh refinement (AMR)

### Added (validated)
- **Adaptive mesh refinement (AMR)** for the Palace backend. Palace estimates a
  per-element error indicator, refines the elements carrying the largest share of
  the error, and re-solves — more accuracy per degree of freedom. Model-level, so
  it works for **eigenmode AND driven** analyses. Opt-in via two new `SolverPalace`
  properties: **`MeshRefinement`** (iterations, default **0 = off**) and
  **`RefinementTol`** (target error, default 0.01). Non-conformal refinement is
  used (mandatory for gmsh tetrahedra). The final adapted result lands in the same
  top-level `postpro/eig.csv` / `port-S.csv`, so the parsers are unchanged. Still
  21 GUI commands.
- **Gate** (`tests/validation/amr_palace.py`): on an Order-1 rectangular cavity
  (exact geometry → the coarse error is pure field discretization, the honest thing
  AMR reduces), turning AMR on moves the fundamental from **4.48927 GHz (0.32% vs
  the closed-form TE101 4.5038 GHz) to 4.50047 GHz (0.074% — 4.3× closer)** while
  the mesh grows from **2039 to 30151 elements** (element growth scraped from
  Palace's refinement log), ~58 s. Gate B runs the full FreeCAD cavity-template
  path with AMR enabled. (Cross-checked on the curved-wall cylindrical BREP cavity:
  coarse 0.36% → AMR 0.10%, unknowns 3931 → 37690 — AMR helps on curved geometry
  too.)

### Notes
- Opt-in and **byte-identical when off** (proven): all three config writers route
  through one `_apply_refinement` helper that injects `Model.Refinement` **only**
  when `MeshRefinement > 0`; with it 0 (the default) the config is unchanged, and
  all five existing Palace gates (`cavity`, `cylcavity`, `waveguide`, `coax`,
  `fastsweep`) re-ran green. `gui_smoke.py` gains an AMR opt-in round-trip check
  (11 checks).

## [0.19.0] — 2026-07-07 — Palace adaptive fast frequency sweep (driven S-parameters)

### Added (validated)
- **Adaptive fast frequency sweep** for the Palace driven analyses (waveguide
  wave ports + coax lumped ports). Palace builds a reduced-order model from a few
  full solves and interpolates a **dense** S-parameter grid — much faster over
  wide bands. Opt-in via two new `SolverPalace` properties: **`FastSweep`**
  (default off) and **`AdaptiveTol`** (default 1e-3). Still 21 GUI commands.
- **Gate** (`tests/validation/fastsweep_palace.py`): a WR-90 waveguide swept over
  a dense **41-point** grid (8–12 GHz) with FastSweep on reproduces the TE10
  S-parameters at **every** point — |S11| −94.7 dB, |S21| deviation 5.5e-6 dB,
  S21 phase slope vs −βL 0.0002° — from just **6 full solves** (scraped from
  Palace's "converged with N frequency samples" log), in ~60 s. The solve count
  is essentially independent of grid density, so the speedup grows with denser
  sweeps (~6× at 41 points).

### Notes
- Opt-in and **byte-identical when off**: both driven config writers route their
  `Solver.Driven` block through one `_driven_block` helper that returns the exact
  flat `{MinFreq,MaxFreq,FreqStep,SaveStep}` block by default; only `FastSweep=on`
  emits the `{Samples:[…], Save:[…], AdaptiveTol}` block. The adaptive form
  **replaces** the flat keys (mixing them makes Palace abort). `parse_sparams`,
  `SweepResult`, and the runners need no change — the dense curve lands in the
  same `port-S.csv` schema. `waveguide_palace.py` + `coax_palace.py` re-ran green.

## [0.18.0] — 2026-07-07 — Palace general 3-D geometry (BREP): cylindrical-cavity eigenmodes

### Added (validated)
- **General 3-D geometry** on the Palace eigenmode path via **BREP export** —
  cavities are no longer limited to rectangular boxes. Any closed solid whose
  boundary is the PEC wall (cylinder, sphere, chamfered box, …) is exported to a
  BREP, meshed by gmsh, and solved. A **Cylindrical Cavity** template and a
  `gmsh_brep` mesher. **21 GUI commands.**
- Pipeline: `build_cavity_model` routes a box to the fast box mesher (unchanged)
  and any non-box solid to `shape.exportBrep()` → `gmsh_brep` (`Merge` the BREP,
  tag the interior volume=1 and its whole boundary `Abs(Boundary{Volume{:}})` as
  PEC=2) → the **existing** `build_eigenmode_config` (same attributes) → Palace.
  The eigenmode result container, parser, and dialog are reused unchanged.
- **Gate** (`tests/validation/cylcavity_palace.py`): a cylindrical air cavity
  (R=30 mm) vs the exact Bessel-zero modes — fundamental **TM010 = 3.834 GHz vs
  analytic 3.8248 (+0.25%)**, and the first modes (TE111, TM011, TM110/TE211
  degenerate pairs) match nearest-analytic to **<0.3%**, in ~60 s. Gate A
  (FreeCAD-free, gmsh-generated BREP) and Gate B (template) both green.

### Notes
- Coax radii and cylinder modes come from real geometry (surfaces/mesh), not the
  tessellation-shrunk bbox; the bbox is used only to SEED the shift-invert target
  (which just needs to sit below the fundamental) — `gui_smoke` checks the BREP
  export under a real GUI and only loosely bounds the seed.
- Recipe (verified vs the analytic cylindrical modes): `Merge` the BREP under the
  OpenCASCADE kernel; `Physical Volume("interior",1)={Volume{:}}`; `Physical
  Surface("pec_walls",2)={Abs(Boundary{Volume{:}})}` (the `Abs()` strips the
  boundary orientation sign); cap the mesh size so curved faces are resolved.
- The **box cavity path is byte-identical** — `run_cavity(size_mm)` and the box
  mesher are untouched; the shared solve tail was factored into `_solve_eigenmodes`
  and `cavity_palace.py` re-ran green (TE101 +0.001%, unchanged) before the BREP
  branch was added.

## [0.17.0] — 2026-07-07 — Palace lumped ports: validated coaxial-line S-parameters

### Added (validated)
- **Coaxial-line S-parameters** on the Palace backend via **radial lumped ports**
  (`Direction "+R"`) — the second driven-analysis path (after wave ports). A new
  `Driven S-parameters (coax)` value on the Palace solver's `AnalysisType`, a
  **Coaxial Line** template (a ~50 Ω air line), and the coax meshing +
  lumped-port config. **20 GUI commands.**
- Pipeline: `gmsh_coax` writes an annular-tube `.geo` (outer disk − inner disk,
  extruded along z) with deterministic physical groups (dielectric=1, PEC
  walls=2, port1=3, port2=4) → Palace Driven solve with two `LumpedPort`s
  referenced to the analytic coax Z0 → S11/S21. Reuses the existing S-parameter
  parser, `SweepResult`, and results dialog unchanged.
- **Gate** (`tests/validation/coax_palace.py`): a matched air coax (inner 0.5 mm,
  outer 1.15 mm) vs TEM theory — **Z0 = 49.94 Ω** (analytic 49.94), **|S11| <
  −29 dB** (matched), **|S21| = +0.34 dB** (lossless; the small offset is
  lumped-port normalization, not gain), and the **S21 phase slope matches −βL to
  0.043°** (β = 2πf√ε/c; the slope check is reference-plane-independent). Gate A
  (FreeCAD-free) and Gate B (template path) both green in ~35 s.

### Notes
- The coax radii are read from the **cylindrical-face radii**, never
  `Shape.BoundBox` — a coax is curved, so the GUI bbox is tessellation-shrunk
  (the coil-ring lesson); `gui_smoke` guards this under a real offscreen GUI.
- Meshing recipe (verified vs the AWS Palace `coaxial` example): the two conductor
  walls fall out as `Abs(Boundary{Volume}) − ports` (the `Abs()` strips the
  orientation sign or the subtraction silently fails and Palace aborts); ports are
  the flat annular end faces picked by z-slab bounding boxes; `Direction "+R"`
  (radial) needs no `VoltagePath`; use `LossTan` not `Conductivity` for Driven.
- The validated **waveguide (wave-port) path is byte-identical** — dispatch keys
  on the new `AnalysisType` string, and `build_driven_config` / `run_waveguide` /
  `write_geo_waveguide` are untouched (re-ran `waveguide_palace.py` green).

## [0.16.0] — 2026-07-07 — Trace-aware meshing: validated microstrip/PCB S-parameters

### Added (validated)
- **Trace-aware meshing** for microstrip (MSL) ports on the openEMS backend, so
  automatic PCB/microstrip S-parameter runs are physical. New
  `SolverOpenEMS.MicrostripMeshMode` (Auto | Off). In **Auto** (default), when an
  MSL port is present the writer resolves the grid at **λ/50 in the dielectric**
  (not the antenna-scale air wavelength), grades a thirds-rule mesh across the
  strip (~6 cells), and **hugs the board** — the substrate/line run to the PML,
  the domain bottom sits on the PEC-Zmin ground (no pad below z=0). This lets the
  MSL port self-extract its characteristic impedance; without it the sub-mm trace
  got <1 cell and S-parameters came out non-physical (|S| > 1).
- **Template: Microstrip Notch Filter** is now on the toolbar (was off, kept as
  an experimental scaffold). A 50 mm, 0.6 mm-wide microstrip line on 0.254 mm
  RO4350B with a 12 mm open quarter-wave stub → two-port S11/S21. **19 GUI
  commands.**
- **Gate** (`tests/validation/msl_notch_openems.py`): the S21 notch lands at
  **3.662 GHz** vs the analytic open-quarter-wave prediction **3.683 GHz**
  (Hammerstad-Jensen ε_eff 2.876; −0.6%) and the openEMS `MSL_NotchFilter`
  tutorial **3.671 GHz** (−0.24%); the result is **passive to −0.03 dB**
  (max |S| ≤ +0.2 dB), the notch is −42 dB deep, and the passband S21 is
  −0.41 dB — in **~40 s**.

### Notes
- The trace-aware path is gated on `PortType == 'MSL'` (+ `MicrostripMeshMode ==
  'Auto'`); the validated patch (lumped port) and dipole (NEC2) paths are
  **byte-for-byte unchanged** (proven by diffing the generated deck and re-running
  patch_openems / patch_stl_openems). Antenna analyses keep the air-wavelength
  grid.
- Lesson: antenna-style 0.25-wavelength domain padding is wrong for a *guided*
  structure — it strands the line end in open air short of the PML (breaking the
  matched termination, |S| >> 1) and inflated runtime ~40×. Microstrip domains
  must hug the geometry.

## [0.15.0] — 2026-07-06 — Palace driven S-parameters (wave ports, WR-90)

### Added (validated)
- **Driven S-parameter analysis** on the Palace backend, with **wave ports** —
  Palace solves the port cross-section's modal field (no analytic mode assumed).
  Pipeline: gmsh 3-D mesh with the two end faces as separate port groups →
  Palace Driven solve over the frequency sweep → S11/S21. A **WR-90 Waveguide**
  template (straight X-band section) and an `AnalysisType` switch on the Palace
  solver (Eigenmode | Driven); results reuse the S-parameter plots dialog.
- **Gate**: a matched WR-90 section vs TE10 waveguide theory — **|S11| < −94 dB**
  (no reflection), **|S21| = 0.000 dB** (lossless), and the **S21 phase slope
  matches −β·L to 0.002°** (β from the TE10 dispersion; the slope check is
  immune to the wave-port reference plane). Full FreeCAD template path gated too.

### Notes
- Wave-port recipe encoded: the two port faces MUST be separate physical
  surface groups (attrs 2, 3) with the walls a third group (attr 4) — a face in
  two groups makes Palace abort ("non-periodic face … multiple boundary
  elements"); select each face explicitly by bounding box (no list
  subtraction). Driven port sets `Excitation` = its `Index`; the passive port
  omits it; the ports self-impose an absorbing Robin BC (no separate absorbing
  boundary). Frequencies in GHz. Next: general 3-D geometry, lumped ports,
  adaptive mesh / fast frequency sweep.

## [0.14.0] — 2026-07-06 — Phase 4: Palace FEM eigenmodes (resonant cavities)

### Added (validated)
- **AWS Palace backend** (`emstudio/solvers/palace/`) — the full-wave FEM path,
  first slice: **resonant-cavity eigenmodes**. Pipeline: gmsh 3-D tetrahedral
  mesh (msh2.2) → Palace eigenmode solve (JSON config) → resonant frequencies +
  Q. A **Resonant Cavity** template (air box, PEC walls, Palace solver) and an
  "Add Palace Solver" command; results in a modes table (frequency + Q, CSV
  export). New `SolverPalace` object (NumModes, Order, MeshSize).
- **Gate**: the 40×20×60 mm air cavity's FEM eigenfrequencies match the exact
  closed-form modes f_mnp = (c₀/2)·√((m/a)²+(n/b)²+(p/d)²) — fundamental TE101
  within **0.001 %**, all 10 computed modes within **0.02 %** (nearest-analytic
  pairing; Palace correctly returns the degenerate doublets). Full FreeCAD
  template path gated too. Runs at FEM order 2 (~55 s); raise Order for
  spectral accuracy.

### Notes
- Recipe pitfalls encoded: Palace's `Model.L0` must be 1e-3 for a mm mesh (its
  default is µm → 1000× off); the mesh must be gmsh **msh2.2** (msh4 passes
  `--dry-run` but aborts at runtime); gmsh physical tags become MFEM attributes
  (volume 1, walls 2). Driven / wave-port S-parameters are the next Palace slice.

## [0.13.2] — 2026-07-06 — Platform-pure install instructions

### Fixed
- The **Detect / Install Solvers** wizard mixed Linux and Windows instructions
  on Windows (a `sudo apt install` line and source-build commands shown next to
  the Windows guidance — confusing, reported by a Windows user). Install text is
  now strictly platform-segregated: on Windows the apt one-liner, the build log,
  the abort button, and all `sudo`/source-build commands are gone — only native
  installer / WSL2 guidance shows; on Linux, unchanged (apt + guided builds, no
  Windows/WSL2 text). `install_plan` (no apt line on Windows), `install_hint`
  (Windows hints on Windows), and the wizard UI all respect the platform.
  Regression-guarded in the smoke test (renders both platforms via os.name).

## [0.13.1] — 2026-07-06 — Real-GUI smoke hardening

### Added
- **`tests/gui_smoke.py`** — a real-GUI test (`QT_QPA_PLATFORM=offscreen freecad
  tests/gui_smoke.py`) that runs the actual user-facing solve loops end to end:
  NEC2 dipole, Elmer induction + WPT, the WPT gap sweep, the openEMS
  geometry-classification path, and construction of every results dialog. This
  closes the blind spot that hid the v0.13.0 bbox bug — the freecadcmd gates use
  FreeCAD's EXACT `Shape.BoundBox`, but the real GUI returns a tessellation-shrunk
  box, so GUI-only failures never reached a gate. Green on 0.21.2 and 1.1.1.
- Confirmed the openEMS geometry path is NOT affected by the tessellation issue:
  antenna geometry is flat (boxes/sheets), which tessellate exactly, so the
  patch's PEC/substrate classify as native boxes (3 boxes / 0 STL) under the GUI.

## [0.13.0] — 2026-07-06 — WPT gap-sweep parametric study + GUI magnetics fix

### Added (validated)
- **Parametric gap sweep** (`WPT: Sweep Coil Gap` command): solve the coupling
  coefficient across a range of coil-pair gaps and plot **k(gap)** with the
  mutual M on a twin axis — EMStudio's "native parametric CAD" differentiator
  made concrete. Pure engine `sweep_wpt_gap(model, gaps)` moves one coil and
  re-solves each point; CSV export from the plot dialog. **Gate**: swept k(gap)
  vs the Maxwell analytic at every gap — **within 0.24 %, monotonic** across
  8–55 mm.

### Fixed
- **Magnetics analyses failed from the FreeCAD GUI** (latent since v0.8): the
  coil/billet "full solid of revolution" check compared `Shape.BoundBox` to the
  outer radius with a µm-tight tolerance, but `Shape.BoundBox` is
  tessellation-dependent — under the GUI it sits ~0.1 mm inside the true radius,
  so every coil ring was wrongly rejected with "not a full solid of revolution".
  The freecadcmd/python3 gates use the exact box, which hid it. The tolerance is
  now a generous 5 % of the radius (still rejects partial revolutions/arcs);
  headless smoke guard added, and a real-GUI induction run verified
  (102.9 W / 408.8 K, matching the gate).

## [0.12.0] — 2026-07-06 — Transient induction heating curves

### Added (validated)
- **Transient heating**: the workpiece temperature RISE over time, not just the
  steady state. The harmonic field is solved ONCE (constant in time) and the
  Elmer HeatSolver is time-stepped (BDF2) with the Joule heating as source and
  convection at the surface. Enable with `TransientHeating` on the Elmer solver
  (`HeatingTime` seconds, `HeatingSteps`); the workpiece material needs
  `Density` (kg/m³) and `SpecificHeat` (J/kg·K). The induction template ships
  aluminum values so it's one checkbox away.
- Results carry the T(t) curve (`heating_curve()`), shown as a dedicated
  **heating-curve page** in the magnetics PDF report and summarized in the
  results dialog. The final-state field/temperature VTU still loads in the 3-D
  viewport.
- **Gate E** (pure python3): thermally-thin billet (Biot ≈ 0.01) heating curve
  vs the exact lumped-capacitance exponential T(t) = T_ss − (T_ss−T0)·e^(−t/τ) —
  **worst 0.91 % of local rise after BDF startup, final within 0.45 %**, eddy
  power constant; plus the full FreeCAD-path transient (data model → sif → curve).

### Known limitations (honest)
- Constant material properties (no σ(T)/k(T)); linear magnetics; the coil/air
  are not heated (workpiece-only heat domain). Radiation is not modeled.

## [0.11.0] — 2026-07-06 — Magnetics PDF report (build-house deliverable)

### Added
- **Magnetics report** (`magnetics_report`, "Save PDF Report…" in the magnetics
  results dialog): a professional document for induction-heating and WPT runs —
  summary, an r–z **cross-section drawing** (coil vs conductor, mirrored about
  the axis), the solved **|B| field map** in the r–z plane (from the VTU, body
  outlines overlaid), and results/BOM tables (per-body σ/µr/k/power/temperature,
  coil turns/current/L/reflected-R, and the L1/L2/M/k coupling matrix for WPT).
  A frequency-sweep page (P(f), L(f)) is added when the run has ≥3 points.
- Completes the EMStudio-wide PDF report pillar (litz + antenna + magnetics).

### Fixed / consistency
- Per-body power in the report is the nodal decomposition **rescaled to the
  field-integrated total**, so a lone conductor's power equals the headline
  total instead of reading a few % low (nodal skin-peak bias).
- Coil "L" in the report is the true **self-inductance** from the coupling
  extraction when available (WPT), not the in-phase apparent L+M from the
  all-coils sweep — it now matches the coupling matrix's L1/L2.
- Result carries body geometry (r0/r1/z0/z1, role, turns, k) so the report is
  self-describing.
- **Undriven coil (0 A) no longer crashes** the report/summary (was a
  `ZeroDivisionError`, found in adversarial review): coupling extraction now
  drives each coil at a nonzero reference current (identical results for driven
  coils; L/M/k stay correct for an undriven WPT pickup), and the operating-point
  coil impedance reports "—" when a coil carries no current. Regression-tested.

## [0.10.0] — 2026-07-06 — Thermal chain: induction heating temperatures

### Added (validated)
- **Steady-state temperature solve** on top of the magnetics solution
  (Elmer HeatSolver in the same case): Joule heating as the source via
  Elmer's built-in `Joule Heat` coupling (energy-consistent — do NOT swap it
  for a nodal `Heat Source = Equals`, which loses 3–8% of the power),
  convection h·(T−T_amb) on the body surfaces, adiabatic where a body meets
  the domain boundary. Enable with `SolveThermal` on the Elmer solver;
  per-body `ThermalConductivity` on the material; `AmbientTemperature` +
  `ConvectionCoefficient` on the solver.
- Results: per-body T_max/T_mean and convected power in the summary/CSV;
  temperature field in the viewport VTU. Induction template now solves
  temperature by default (forced cooling h=100 → billet ≈ 409 K at the
  2 kHz/200 A defaults).
- Mesher: per-region `surf_<name>` boundary groups (body/air interfaces) for
  the convection BCs; skin-depth mesh rule tightened to δ/4.
- **Gate D** (pure python3): full-height billet (adiabatic ends) in a uniform
  100 Hz field — the steady radial profile is exact analytically:
  **energy balance −0.00%, ΔT(center−surface) +0.07%, surface rise −0.02%**;
  template gate adds the FreeCAD-path thermal balance (+0.00%, T_max 408.8 K).

### Known limitations (honest)
- Steady state only (equilibrium temperature) — transient heating curves,
  temperature-dependent σ(T)/k(T), and radiation are roadmap items; free-air
  steady state of a real IH load can legitimately reach unphysical-looking
  equilibria (that's why the template defaults to forced cooling).

## [0.9.0] — 2026-07-06 — Guided solver installer (first-run wizard)

### Added
- **Solver Setup wizard** (`Detect / Install Solvers`, also auto-offered ONCE on
  first workbench activation when backends are missing): per-backend status
  table, ONE copy-button `sudo apt` line covering every missing package and
  build prerequisite (EMStudio never runs sudo itself), and **guided no-sudo
  source builds** for openEMS / FastHenry / Palace with compiler output
  streamed into the dialog and an Abort button.
- Build recipes are the exact commands that produced the working installs on
  the reference machine (openEMS umbrella clone + PEP-668 venv +
  `update_openEMS.sh --python`; FastHenry `-fcommon`; Palace CMake superbuild)
  — idempotent, so a retry resumes instead of failing on an existing clone.
- Prerequisites are preflighted BEFORE any compile starts (the Palace/OpenBLAS
  lesson): the Build button is disabled with the needed apt packages until the
  sudo step is done.
- Windows: build buttons are replaced by the per-backend native-installer /
  WSL2 guidance.
- Smoke check: build recipes must be well-formed and sudo-free.

## [0.8.0] — 2026-07-05 — Phase 3: Elmer magnetics (induction heating + WPT)

### Added (validated)
- **Elmer FEM backend** (`emstudio/solvers/elmer/`): 2-D axisymmetric **harmonic
  magnetodynamics** for coaxial geometries (cylinders/tubes/rings on the Z axis)
  — the CENOS induction-heating / wireless-charging problem class. Pipeline:
  gmsh (OpenCASCADE rz-plane mesh, distance-graded sizing, skin-depth-aware) →
  `ElmerGrid 14 2` → `ElmerSolver` (`MagnetoDynamics2DHarmonic` +
  `MagnetoDynamicsCalcFields`), frequency sweeps parallelized across processes.
- **Coil Excitation object**: turns × peak current × phase on a ring solid,
  written as a stranded-coil harmonic current density.
- **Induction heating**: billet Joule power, per-body loss decomposition, coil
  effective inductance and **reflected resistance** (R = 2P/I², verified to
  +0.01% by energy conservation), B/J/Joule-heating fields as VTU in the 3-D
  viewport. **Gate:** billet in a uniform axial field matches the exact Bessel
  (Davies) solution to **+0.03% at 1 kHz / +1.3% at 10 kHz** (power) and the
  center B-field to 0.1–1.8%; air-core solenoid center B matches the
  current-sheet formula to **−0.04%**.
- **Wireless power transfer**: inductance matrix (L1, L2, M) and coupling
  coefficient k from per-coil excitations (flux-linkage extraction). **Gate:**
  vs Grover/Maxwell analytic coil formulas — **L within 0.5%, M within 0.4%,
  k within 0.3%** across 10/20/50 mm gaps.
- **Templates**: *Induction Heating* (aluminum billet + 20-turn coil) and
  *WPT Coil Pair* (two 10-turn coils, editable gap) — both ready-to-run.
- **Magnetics results dialog**: engineering summary + one-click field display
  in the 3-D viewport (`Fem::FemPostPipeline`).
- New gates `tests/validation/{induction_elmer,wpt_elmer}.py` run under BOTH
  plain python3 (physics, no FreeCAD) and freecadcmd (template path); smoke
  suite extended (Elmer solver/coil round-trip, headless-import guard).

### Known limitations (honest)
- Axisymmetric only (coaxial solids of revolution about Z); general 3-D
  magnetodynamics (WhitneyAV + CoilSolver) is a roadmap item.
- Linear materials only (constant µr — no B-H curves / saturation yet); no
  thermal chain yet (Joule power is reported, not temperature).

## [0.7.1] — 2026-07-05 — Install-knowledge engine + Windows awareness

### Added
- **Install-plan engine** (`emstudio.setup.solvers`): every backend now declares
  machine-checkable build prerequisites (`Prereq`: binary/library/python probes,
  each with its apt package and the pitfall it prevents — OpenBLAS for Palace,
  `-fcommon` for FastHenry, PEP-668 venv for openEMS, Elmer's CSC PPA).
  `install_plan()` preflights them and emits ONE combined `sudo apt install` line
  for everything missing; `install_report_text()` renders the full guided report.
  Detect Solvers now shows the one-liner + per-backend source-build steps.
- **Windows awareness**: platform-aware Detect Solvers report (native installer
  URLs for Elmer/Gmsh, honest WSL2 pointers for NEC2/FastHenry/Palace),
  `.exe`/`.bat` probing in install-location scans, `requirements.txt` so the
  FreeCAD Addon Manager auto-installs matplotlib/scipy on platforms whose FreeCAD
  bundles lack them, and a frank "Windows users" section in the manual.
- Guided installer GUI promoted to roadmap item 0 (adoption-critical).

## [0.7.0] — 2026-07-05 — Interactive 3-D visualization

### Added
- **Full-sphere far-field sampling** (both solvers: theta 0–180° × phi 0–355°, 5°)
  — validated peaks unchanged (dipole 2.13 dBi, patch 6.64 dBi).
- **"Pattern 3D" tab**: rotatable/zoomable 3-D gain balloon (drag to rotate,
  right-drag/scroll to zoom) colored by dBi.
- **Matplotlib navigation toolbar on every results tab** (pan/zoom/save).
- **"Show in 3D View"**: loads results into FreeCAD's own 3-D viewport as colored
  `Fem::FemPostPipeline` surfaces — full native rotate/zoom/pan/tilt alongside your
  geometry: the **gain balloon**, the **wire path colored by |I|**, and the
  **near-field |E| plane**. Backed by a dependency-free VTU writer
  (`emstudio/post/vtk_out.py`), verified headlessly end-to-end.

## [0.6.0] — 2026-07-05 — Near field, current distribution, multi-port S-params

### Added (validated)
- **Near-field |E| maps**: frequency-domain field dump on an XY/XZ/YZ cut plane
  (`NearFieldPlane` on the openEMS solver), rendered as a heatmap "Near Field" tab.
- **Current distribution** (NEC2): per-segment |I| along wires, "Currents" tab.
  Gate: half-wave dipole shows the textbook half-sine (peak at center feed, ~0.10x
  at the ends).
- **Multi-port S-parameters**: S21/transmission for multi-port openEMS analyses
  (per-port CalcPort, `sparam_<to>_<from>.csv`), plotted alongside S11 in the
  renamed "S-Parameters" tab. Adds an **MSL (microstrip) port type** and a
  propagation-direction property.

### Experimental (NOT validated — off the toolbar)
- **Microstrip notch-filter PCB template** (`templates/msl_filter.py`): the S21/PCB
  scaffold. openEMS MSL ports need per-design calibration and a trace-fine mesh that
  the automatic antenna-scale gridder does not yet provide, so its S-parameters are
  currently non-physical. Kept as the basis for a trace-aware-meshing follow-up; the
  multi-port S-parameter infrastructure itself is correct for hand-tuned setups.

## [0.5.0] — 2026-07-05 — Aggregated current sharing, ampacity, PDF reports

### Added
- **Aggregated current sharing** (EMStudio-wide, per AJ's rescope): `grouped_metrics`
  reports per-bundle / per-cable current share vs proportional expectation (no
  per-strand detail); `analyze_construction` gives per-bundle sharing of a litz
  construction's final cabling level (each member = equivalent conductor on its
  helix). Gate: 7-strand grouped [center]/[ring] @1 MHz → 0.119 / 1.149.
- **Ampacity estimate** (`LitzConstruction.ampacity`): free-air surface heat balance
  (I_max = sqrt(h·π·OD·ΔT / Rac)); shown in the Litz Designer summary and spec/BOM.
  AJ's 18,200-strand Type 6: 609 A DC → 99 A @ 1 MHz.
- **Current Sharing command** — EMStudio-wide: analyzes paralleled conductors in the
  active analysis (or a selected litz construction), aggregated per bundle/cable.
- **Professional PDF report generator** (EMStudio-wide report pillar): one
  build-house-ready document per analysis — title/summary, geometry or litz
  cross-section drawing, result curves (S11/VSWR/impedance/pattern, or Rac/Rdc),
  and a BOM/construction schedule. **Generate Report** command + Litz Designer button.

## [0.4.1] — 2026-07-05 — 18,200-strand stress test: geometry fixes + performance

Stress-tested with AJ's real cable (Type 6: 70×13×20 = 18,200 strands, tape wraps,
1/8" PVC jacket).

### Fixed
- **Cross-section geometry single-source bug**: the layout computed its own cluster
  radii while cores were sized from the construction's radii — at deep hierarchies
  the ring-capacity check spilled a member ("out-of-place Type-4") and the central
  core drew under-scale. Cored operations now place exactly N members on the snug
  ring from the construction's own level radii; verified: 20 Type-4s at radius
  spread 3e-18, central core 31.46 mm (exact snug value).
- **Nested outline replication**: inner-level bundle/wrap outlines now replicate
  into every higher-level member (previously drew once near the origin — the
  mystery cluster in the middle of exported profiles).

### Performance ("use all the cores")
- Layout vectorized (numpy): 18,200 strands in 0.05 s.
- Rendering via matplotlib EllipseCollection: 18k strands 0.09 s, 109k 0.33 s.
- **FastHenry parallelized across frequencies** (one process per sweep point, up
  to all CPU cores) for both Rac sweeps and current-sharing.
- openEMS already saturates all cores (multi-threaded SIMD engine). GPU: no current
  backend supports it; planned via Palace (Phase 4).

### Added
- **Profile simplification for the FreeCAD export** (and dialog selector):
  full strands / bundle outlines / envelope (OD+jacket) / auto. AJ's cable:
  envelope = 2 edges, bundles = 583, vs 18,483 for full.
- Flexible-depth ops guidance (a real Type 6 like 70×13×20 is 3 rows; presets are
  examples only).

### Plan rescope (AJ)
- Current sharing is EMStudio-wide, presented aggregated (per-bundle/per-cable,
  no per-strand bars), feeding the ampacity/thermal estimate.
- The PDF report pillar is EMStudio-wide (drawing + curves + BOM per analysis);
  the litz cross-section is the Litz Designer's contribution.

## [0.4.0] — 2026-07-05 — Buildable litz constructions + current sharing

Driven by AJ's manufacturing-accuracy review of the Litz Designer.

### Added
- **Per-strand current-sharing analysis** (`emstudio.wire.current_sharing`):
  multi-port FastHenry (one port per strand) → N×N impedance matrix → strand-current
  imbalance/spread = a twist-quality number. Symmetry-based validation gate
  (5/5): a 6-strand ring shares to 1.0000–1.0003 across 10 kHz–1 MHz; a 7-strand
  bundle at 1 MHz shows imbalance 9.63 — the center strand carries 0.12× mean, the
  quantitative demonstration of why multi-level Type 2/3 constructions exist.
- **Multi-level fiber cores**: cores per cabling operation (not just outermost) —
  Type 6 correctly builds as Y Type-4s (each around its OWN core) around a larger
  final core. `auto` = exact snug single-ring core, rc = R(1/sin(π/N) − 1)
  ("tightly packed around the circumference"). Cross-section shows every core;
  spec sheet lists core Ø and OD after each level; dialog gains a Core Ø column
  with type-aware seeding.
- **Member wraps + overall jacket**: insulation build-up per operation
  (polyester/PTFE/kapton tape, nylon serve; default tape 0.05 mm ≈ 2 mil) and a
  finished-cable jacket (PVC/PE/silicone/PTFE; Type-6 default **1/8" PVC wall**,
  industry range 1/8"–1/4"). Wrapped-member radius feeds the packing geometry;
  proximity model keeps the conductor region; spec/BOM quotes conductor OD and
  finished OD (mm + inches); cross-section draws tape rings + jacket.

### Changed
- Level-geometry recursion is the single source of truth for ODs, lays, twist
  factor, layout and exports. Uncored/unwrapped constructions are numerically
  identical to 0.3.0 (FastHenry anchors re-verified).

## [0.3.0] — 2026-07-05 — Phase 2: far fields + Wire & Cable toolkit

### Added
- **Far-field radiation patterns**, both backends: openEMS NF2FF (recording box in the
  deck, pattern at the best-match frequency, gain in dBi) and NEC2 RP second-pass
  decks; polar "Pattern" tab in the results dialog; shared `FarFieldResult` container.
  Validated: dipole 2.13 dBi peak at theta=90 with clean axial null (literature:
  2.15 dBi); patch 6.64 dBi boresight, ~16 dB front-to-back.
- **Wire & Cable toolkit**: full industry **Type 1-9** litz taxonomy (New England
  Wire classification — bunched/cabled/insulated-member/fiber-cored/served round
  constructions, braided + compressed rectangular, coax-style), per-level **lay
  length and S/Z direction** (auto = 12x level OD, alternating), strand sizing in
  **AWG / mm / mil**; exact Kelvin-function strand skin effect; internal proximity
  with first-principles n^2 scaling and exact complex-Bessel kernel; **external
  (winding) proximity** via He/I context (solenoid ~ turns/length); Rdc with
  compounded helical lay correction; copper weight + equivalent-AWG; **Litz / Wire
  Designer** dialog with live **cross-section visualization**, isolated/in-winding
  Rac curves, W/m at operating current, **supplier-ready spec/BOM export
  (Markdown)** and **profile export to FreeCAD** (strand-circle compound for
  Part Sweep/Loft coil modeling).
- **FastHenry backend** (magneto-quasistatic PEEC): source build support (-fcommon fix
  for modern GCC, detection + install hint), .inp writer for parallel 3-D wire paths,
  Zc.mat parser, twisted hex-packed bundle path generator.
- **Wire validation gate** (13 checks, plain python3): analytics self-consistency,
  FastHenry vs exact Bessel round wire (<=7% incl. known square-section bias), and
  7-strand twisted litz bundle — Rdc within 1.1%, Rac/Rdc **0.0% at the litz design
  point** (10 kHz, x=0.76), 15% conservative in the deep transition region.

### Fixed
- openEMS NF2FF `center` argument is in meters, not drawing units — mm values put the
  phase center outside the recording box and produced all-NaN patterns.
- **Validation-integrity**: freecadcmd exits 0 on uncaught exceptions (verified) — all
  validation scripts now convert failures to SystemExit so CI exit codes are honest.
  One prior gate "pass" was invalidated and re-verified for real.

## [0.2.0] — 2026-07-05 — Phase 1 core: first validated simulations

EMStudio now runs real, validated electromagnetic simulations end-to-end inside
FreeCAD: geometry → materials → port → auto-mesh → solve → S11/VSWR/impedance plots →
Touchstone export.

### Added
- **EM data model**: `EMMaterial` (PEC/dielectric/conductor, geometry references,
  priorities, wire radius), `EMLumpedPort` (direction, impedance, auto-numbering),
  solver settings objects, frequency-sweep/boundary/mesh settings on the analysis.
- **NEC2 backend** (wire MoM): straight-edge wire extraction, `.nec` deck writer,
  output parser, feed placement on the port's edge.
- **openEMS backend** (EC-FDTD): Python deck generation run under the openEMS venv
  interpreter as a subprocess; axis-aligned solids/sheets become native CSXCAD boxes,
  everything else exports to STL (`AddPolyhedronReader`) — including direct
  `Mesh::Feature` (imported STL) support; automatic domain sizing, metal-edge
  thirds-rule gridding, substrate discretization, grid smoothing.
- **Grid ULP snap fix**: works around openEMS `SmoothMeshLines` returning fixed lines
  perturbed by ~1 ULP (which silently drops zero-thickness metal); the deck snaps the
  smoothed grid back onto all critical geometry planes. (Upstream-reportable bug.)
- **Shared results model** (`SweepResult`): Zin/S11 per frequency, VSWR, resonance
  search, CSV persistence, Touchstone `.s1p` export.
- **GUI**: Run Solver command with background thread + progress dialog + Report-view
  streaming; tabbed results dialog (S11/VSWR/impedance, matplotlib) with Touchstone
  export; Material/Port-from-selection commands; solver-object commands.
- **Templates**: wire dipole (NEC2) and 2.4 GHz microstrip patch (openEMS, mirrors the
  official openEMS tutorial).
- **Validation gates** (all passing): dipole f_res 296.3 MHz / R 71.9 Ω (textbook
  ~73 Ω); patch S11 −29.5 dB at 2.435 GHz (tutorial reference ~2.4 GHz); STL-substrate
  patch −34.0 dB at 2.435 GHz (identical resonance through the STL path).

## [0.1.0] — 2026-07-05 — Phase 0: skeleton

Initial workbench scaffold. Not yet capable of simulation; this release establishes the
structure every later phase builds on.

### Added
- FreeCAD workbench registration (`Init.py`, `InitGui.py`, `package.xml`) — pure-Python
  workbench (`GetClassName` → `Gui::PythonWorkbench`), loads under FreeCAD 0.21.2 and 1.1.1.
- `emstudio` package: version, resources/icon helper, three SVG icons.
- **EM Analysis** document object — a scripted `App::DocumentObjectGroupPython` container
  (Proxy pattern), GUI-safe, with save/reload round-trip support across 0.21/1.x.
- **Detect Solvers** command + `emstudio.setup.solvers` — Qt-free discovery of openEMS,
  NEC2, Elmer, Palace, Gmsh via preferences → env → PATH → common dirs, with per-platform
  install hints. Never raises on a missing solver.
- Headless smoke test (`tests/smoke.py`) — 6 checks (package import, version/manifest
  agreement, solver detection, icon XML validity, analysis round-trip, and a GUI
  registration contract that execs `InitGui.py` against a recorder). Runs under
  `freecadcmd` and plain CPython; propagates non-zero exit for CI.
- Research report and phased plan under `docs/`.

### Notes
- No backend solvers are required at this stage; `Detect Solvers` will report them all
  missing on a fresh machine — that is expected.
