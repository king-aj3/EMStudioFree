# EMStudio User Manual

**Version 0.3 — 2026-07-05**

> ⚠️ **Disclaimer:** every number, plot, report, and spec EMStudio produces is an
> engineering **estimate** that can be wrong. Independently verify all results
> (measurement, prototyping, qualified engineering review) before manufacture,
> purchase, deployment, or any other reliance. Provided AS IS with no warranty;
> the authors and the AJJ³ project accept no liability for damage, injury,
> interference, or loss of any kind. Regulatory and RF-safety compliance is the
> user's sole responsibility. Full text: [DISCLAIMER](../DISCLAIMER.md).

EMStudio is a FreeCAD workbench for RF / electromagnetic analysis and simulation. Its
goal: make antenna, RF, and wire/cable engineering **as simple as possible** — real-world
calculations, professional tools and visualization, with minimal effort and minimal
prerequisite theory — and produce results you can hand to a build house: specs, BOMs,
plots, and exportable data.

Everything in this manual has an automated validation test behind it; the numbers shown
are real results from those tests, not illustrations.

---

## 1. Installation

1. Install FreeCAD 0.21 or newer (1.x recommended).
2. Install EMStudio through the FreeCAD **Add-on Manager** (Tools → Addon Manager →
   search "EMStudio" → Install). To install manually instead:
   ```bash
   git clone https://github.com/king-aj3/EMStudioFree.git \
     ~/.local/share/FreeCAD/Mod/EMStudio        # FreeCAD <= 1.0
   git clone https://github.com/king-aj3/EMStudioFree.git \
     ~/.local/share/FreeCAD/v1-1/Mod/EMStudio   # FreeCAD 1.1+
   ```
   (FreeCAD ≥ 1.1 uses version-suffixed directories — install into both if unsure.
   Install into **one** Mod directory per FreeCAD version: two copies both put a
   package named `emstudio` on `sys.path`, and which one loads is not the order
   you would guess.)
3. Restart FreeCAD and pick **EMStudio** from the workbench dropdown.
4. Click **Detect / Install Solvers** (the wizard also offers itself automatically
   the first time you activate the workbench with solvers missing). It shows what
   was found, gives you **one copy-paste `sudo apt` line** for everything apt can
   provide (EMStudio never runs sudo itself), and **builds the from-source
   backends for you** — openEMS, FastHenry, Palace — with the compiler output
   streaming live in the dialog and no sudo needed. Build prerequisites are
   checked *before* compiling, so a missing library stops you up front with the
   exact package name, not 40 minutes into a build.

   | Solver | Used for | Install |
   |---|---|---|
   | NEC2 (`nec2c`) | wire antennas (instant) | in the apt one-liner |
   | Gmsh + Elmer | induction heating, WPT coupling (FEM) | apt one-liner (Elmer via CSC PPA) |
   | openEMS | 3-D antennas, S-parameters, patterns | wizard **Build…** button (~15–60 min) |
   | FastHenry | wire/litz bundle impedance | wizard **Build…** button (~1 min) |
   | Palace | Phase-4 full-wave FEM | wizard **Build…** button (~30–90 min) |

You can start with only NEC2 installed — the dipole tutorial needs nothing else.

---

## 2. Tutorial: your first antenna in 2 minutes (wire dipole)

1. **EMStudio → Template: Wire Dipole.** A complete, ready-to-run analysis appears:
   a 475 mm wire, a PEC wire material, a center feed port, a 200–400 MHz sweep, and a
   NEC2 solver.
2. **Click Run Solver.** The solve takes well under a second.
3. A results window opens with four tabs:
   - **S11** — the match vs frequency; expect the dip near **296 MHz**.
   - **VSWR** — the same information the way transmitter specs quote it.
   - **Impedance** — R and X vs frequency. At resonance (X = 0) you should read
     **R ≈ 72 Ω** — the textbook half-wave dipole feedpoint resistance.
   - **Pattern** — polar gain plot: the classic dipole donut, **2.13 dBi** peak
     broadside, deep nulls off the wire ends.
4. **Export Touchstone** saves an industry-standard `.s1p` file for any RF tool.

*What just happened:* EMStudio extracted the wire from your document, wrote a NEC2
(Method-of-Moments) deck, ran it, computed a second radiation-pattern pass at the
resonant frequency, and normalized everything into one results view.

---

## 3. Tutorial: microstrip patch antenna (full-wave FDTD)

Requires openEMS (see README for the one-time build).

1. **EMStudio → Template: Patch Antenna.** You get a 32×40 mm patch on a
   60×60×1.524 mm εr = 3.38 substrate with ground plane and feed — the openEMS
   reference antenna.
2. **Run Solver.** A progress dialog appears; the full-wave FDTD solve takes seconds
   to a few minutes depending on your CPU (solver output streams into FreeCAD's
   Report view).
3. Expected results: S11 dip of about **−29 dB at 2.435 GHz**, input impedance
   ≈ 47 Ω at the dip, and a **6.6 dBi** boresight pattern in the Pattern tab.

---

## 4. Tutorial: simulate your own geometry

1. Model or import your structure (Part workbench, or any FreeCAD geometry).
2. **New EM Analysis** — creates the container that holds everything.
3. Select the metal parts (solids or faces) → **EM Material** → in the property
   editor set Category = `Metal (PEC)`.
4. Select dielectric solids → **EM Material** → Category = `Dielectric`, set
   `RelPermittivity` (and `LossTangent` if you know it).
5. Draw a short line (Part → Line) across the feed gap — from ground to the driven
   conductor. Select it → **Lumped Port**. Set `Direction` to the axis the line runs
   along (e.g. `+Z` for a vertical feed).
6. Set the frequency sweep on the Analysis object (`FrequencyStart` / `FrequencyStop`).
7. **Add openEMS Solver** (3-D structures) or **Add NEC2 Solver** (wire-only
   structures) → **Run Solver**.

Meshing is automatic: EMStudio sizes the simulation domain, grids metal edges with
the thirds rule, and discretizes thin substrates. Override density via the analysis'
`MeshResolution` (lines per wavelength, default 20).

## 5. Tutorial: analyzing an STL file

Imported STL meshes work directly — no conversion to solids needed:

1. **File → Import** your `.stl` (it arrives as a Mesh object).
2. Select it → **EM Material** → set its category (metal or dielectric) as usual.
3. Proceed exactly as in Tutorial 4 (port, sweep, solver, run).

EMStudio passes the triangles straight to the solver's native STL reader. The
validation suite proves this path: the reference patch antenna with an STL substrate
resonates at the identical frequency as the parametric version.

---

## 6. Tutorial: designing a Litz cable (Types 1–9)

Open the **Cable Designer** (called the Litz / Wire Designer before v0.37) and keep
the top-level **Construction** selector on **Litz / stranded**. The taxonomy is the
industry-standard New England Wire
classification — all nine types, from simple bunched (Type 1) through cored and served
constructions to rectangular (7/8) and coax-style (9).

Worked example — a 100-strand Type 2 for a 100 kHz application:

1. **Litz type**: `Type 2 — round; Type-1 bunches cabled together`.
2. **Strand size**: `38` with unit `AWG` (you can also work in mm or mil).
3. **Operations table** (innermost first): level 1 = `20` members, level 2 = `5`
   members. Leave Lay = `auto` (12× level diameter) and Dir = `auto` (alternating
   S/Z, per industry practice) — or set exact lay lengths and directions your wire
   house quotes. The **Core Ø** column marks which operations wrap a fiber core
   (`none`, `auto` = snug single-ring core sized to the member count, or an exact
   mm value).

   **Hierarchical example — Type 6** (n × m × X × Y): a Type 6 is Y Type-4 cables
   tightly packed around a larger fiber core, where each Type 4 is X Type-2 cables
   around its own core, each Type 2 is m Type-1 bunches, each of n strands. Enter
   one row per operation, innermost first:

   | Row | Members | Core Ø | Produces |
   |---|---|---|---|
   | 1 | n = 20 | none | Type-1 bunch |
   | 2 | m = 4 | none | Type 2 |
   | 3 | X = 5 | **auto** | Type 4 (its own fiber core) |
   | 4 | Y = 6 | **auto** | Type 6 (the larger core) |

   Selecting the litz type pre-fills this layout with the cores marked. The
   cross-section view then shows all Y + 1 fiber cores in place, and the spec sheet
   lists core size and OD after every level.

   **Wraps and jacket.** Real composite constructions carry insulation build-up, and
   EMStudio models it: the **Member wrap** column sets the insulation wrapped on each
   member *before* that operation cables them (Type 6 default: 2-mil polyester tape
   on the Type-2s and again on the Type-4s; choose PTFE/kapton tape or nylon serve,
   and append a thickness in mm to override — e.g. `PTFE tape 0.1`). The **Overall
   jacket** box sets the finished cable's jacket — Type 6 defaults to **PVC with a
   1/8″ (3.175 mm) wall**, industry-typical range 1/8″–1/4″; set the exact wall in
   mm. Wraps grow the packing geometry (cores and ODs resize correctly), the
   cross-section draws the tape rings and jacket, and the spec sheet quotes both
   the conductor OD and the finished OD over the jacket (with inches).
4. **Update.** Now read the three tabs:
   - **Cross-Section** — the construction drawn to scale: copper strands, dashed
     bundle outlines, overall OD. Visually verify it's the cable you meant.
   - **AC Resistance** — Rac/Rdc and Rac (mΩ/m) vs frequency, from the exact
     skin-effect solution plus the FastHenry-anchored internal proximity model.
   - **Spec / BOM** — the build sheet: strand gauge, operations with lay
     length/direction per level, OD, copper weight, Rdc, equivalent solid AWG.
5. **Winding context**: if the cable will live in a coil, enter the winding field
   per ampere `He/I` (for a long solenoid ≈ turns ÷ length). The dashed curve shows
   the *in-winding* Rac including external proximity — usually the dominant loss.
6. **Current**: enter your RMS current to read dissipation in W/m in the summary.
7. **Save spec / BOM…** writes a Markdown build sheet any litz supplier can quote.
8. **Export → FreeCAD** creates the cross-section as a compound at the XY origin —
   select it plus a path (e.g. Part → Helix) and use **Part → Sweep** to grow real
   3-D cable/coil geometry. Choose the **profile simplification** first: a fully
   detailed profile causes computational and visual problems in downstream sweeps,
   so pick *full strands* (small cables), *bundle outlines* (one circle per
   sub-cable + cores — right for most sweeps), or *envelope* (conductor OD +
   jacket only — ideal for long coil sweeps). *Auto* picks full up to 5,000
   strands, bundle outlines beyond.

---

## 6b. Current sharing and ampacity (Cable Designer, litz page)

- **Current Sharing…** runs a per-bundle analysis of the final cabling level: each
  outer member (e.g. each Type-4) is modeled as an equivalent conductor on its real
  helix, and FastHenry computes how evenly current divides between them. The result
  is an *imbalance* number (1.0 = every bundle carries its proportional share) and a
  bar per bundle. This is your twist-quality check — a large imbalance means the
  construction needs more transposition levels. (Runs FastHenry; takes minutes.)
- The summary shows an **ampacity estimate** — the continuous current for a chosen
  temperature rise, from a free-air surface heat balance. Defaults are conservative
  (30 K rise, still air); a cable buried in a winding cools far worse, so treat it
  as a sizing figure and derate.

## 6b². Coax, single-wire and twisted-pair constructions (Cable Designer, v0.37/0.38)

Flip the top-level **Construction** selector:

- **Coax** — analytic TEM electricals from the geometry: pick an **RG-58C/U or
  RG-142B/U preset** (primary-datasheet geometry — Belden 8262, Belden-UK /
  MIL-DTL-17; a stranded centre is entered as its *effective* electrical
  diameter, ~0.94× the physical envelope) or type your own 2a / 2b / dielectric.
  **Update** computes Z0, velocity factor, C′/L′, the TE11 single-mode cutoff and
  the conductor + dielectric attenuation split at your report frequency; the
  RF-Attenuation tab plots all three curves from 1 MHz to 10 GHz with the cutoff
  marked, and the Spec tab writes a datasheet-style table. Honesty note (also
  printed on the plot): the smooth-solid-conductor loss model under-estimates
  real braided/tinned cables by ~10–45 %; Z0/VF/C′ are geometry-exact.
  **Run full-wave verify** meshes the same (2a, 2b, length) line and solves it
  with the validated Palace lumped-port backend: a matched line must show tiny
  |S11|, and the S21 phase gives the full-wave velocity factor to compare with
  1/√εr (RG-58 reference run: worst |S11| −31 dB, VF −0.09 % from analytic).
  Keep the line under λ/2 at the start frequency so the phase is unambiguous.
- **Single wire** — a solid conductor (AWG/mm/mil) with optional insulation
  (PVC/PE/PTFE/enamel + wall). This reuses the litz analytics with zero bunching
  operations, so Rac/Rdc is the *exact* Kelvin skin-effect solution, and you get
  Rdc, ampacity, the cross-section, spec and the PDF report for free. The
  winding-field (He/I) proximity term still applies if you set it.
- **Twisted pair** (v0.38) — differential transmission-line properties of two
  insulated round wires: bare conductor Ø *d*, insulated OD (= centre spacing
  *s* for a tight twist) and twist lay give the differential and odd-mode Z0,
  velocity factor, C′/L′, wire-length factor and attenuation. Two honest ways
  to get the effective permittivity: **datasheet NVP** (εeff = 1/NVP² — what
  the Cat5e/Cat6 presets use, since real-cable insulation is a mixed air/
  polymer problem) or the **Lefferson twist model** (εeff = 1 + q(εr−1),
  q = 0.25 + k·θ², θ = pitch angle in *degrees*, k for hard-film vs soft
  insulation; optimum twist 20–45°, and the dialog warns above the fit's
  q > 1 boundary and the ~50° breakage angle). **Shielded (STP)** switches to
  the classic shielded-pair form (thin-wire; the dialog flags d/s > 0.4). The
  Z0-vs-lay plot shows how twist rate pulls the impedance down; validated
  against the Cat5e/Cat6 100 Ω primary datasheets, Lefferson's worked
  examples, and the exact shielded-pair solution (see the validation suite).
- **Bundle** (v0.39) — compose a multi-design cable: a member table where each
  row is one design (label, envelope OD, quantity, kind) placed into a compact
  packing around the bundle axis. Envelope rules: wire/litz use the finished
  OD, coax the OD over its shield/jacket build, a twisted pair 2× its spacing
  (the circle the rotating pair sweeps). The packing is deterministic
  largest-first tangency placement re-centered on the minimal enclosing
  circle — the industry classics come out exact (two members side-by-side =
  2× OD, seven equal members = the 3× hex with fill 7/9). **Add last
  construction** imports the envelope of whatever you last computed on the
  other pages. You get the packed cross-section (colored by member kind),
  core and finished OD (with jacket), fill factor and a spec table with every
  member's position. **Estimate crosstalk** (v0.40): give members a
  conductor Ø, pick a generator, receptor and reference (return) member and
  the terminations, and you get near/far-end weak-coupling crosstalk curves
  (Paul's inductive-capacitive model, validated against his printed
  ribbon-cable benchmark), the common-impedance floor, and whether inductive
  or capacitive coupling dominates. The instant estimate uses analytic
  wide-separation L/C matrices — valid while every separation is at least
  4× the conductor radius (the dialog warns otherwise); the **FastHenry**
  option extracts the loop L/R matrix at any spacing (proximity included).
  Honest limits, stated in the dialog: shielded coax members are excluded
  from coupling (their return is their own shield). Insulated members
  (envelope OD > conductor Ø) route the capacitance through a validated
  **method-of-moments dielectric solve** (v0.48 — Paul's RIBBON.FOR method;
  the "Insulation εr" box drives it); bare members keep the exact
  bare-identity C. **Differential pair-to-pair (mixed-mode)** (v0.49): tick
  the checkbox, pick the four pair conductors (A1/A2, B1/B2) plus the
  reference member, and the estimate switches to differential quantities —
  the coupling coefficient k_diff, the ASTM D4566 pair-to-pair capacitance
  unbalance (CUPP, pF/100 m), differential-mode impedances Zdd, and
  differential near/far-end crosstalk curves. Terminations are entered as
  DIFFERENTIAL ohms (50 Ω per wire to reference at an end = 100 Ω). The
  receptor **twist** control applies the RADC-TR-76-101 twisted-pair model:
  improvement is quoted as the conservative odd-N envelope (1/N per
  half-twist count), the capacitive floor survives twisting when the
  receptor is unbalanced, balancing the terminations nulls it, and a
  receptor grounded at both ends gets a warning — that ground loop defeats
  the twist entirely.

## 6b³. Thermal analysis (Thermal tab)

Every Cable Designer page carries a **Thermal** tab (v0.50). Set the load
current, ambient temperature, insulation temperature class and surface
emissivity, press **Analyze thermal**, and for wire/litz constructions you
get four linked views:

- the **construction cross-section colored by temperature** — the conductor
  at its computed temperature, each insulation layer graded through its
  exact conduction drop (IEC 60287-2-1 ladder), with a colorbar;
- the **dissipation field around the cable**: the thin conduction film
  hugging the surface (its thickness is the model's own k/h — thicker than
  intuition suggests) and the **buoyant plume rising above the cable**
  (laminar similarity solution, honestly labeled — quantitative inside the
  film, illustrative in the plume, which in reality sways and turns
  turbulent some ten diameters up);
- **conductor temperature vs current** with the class limit and the
  computed free-air **ampacity** marked;
- the **transient heating curve** with the thermal time constant and, when
  the load exceeds the rating, the time-to-limit.

The read-out adds the margin to the class limit, the IEC 60949 adiabatic
1-second short-circuit current, and honest warnings (fine-wire regimes run
conservative/hot; thermal runaway is detected, not clamped). Coax pages
show the **matched RF average-power rating vs frequency** (validated
against the published LMR-240 table; the smooth-conductor default loss
makes it optimistic for braided cables — feed datasheet attenuation for
tight numbers). Bundle pages report the NEC 310.15(C)(1) derating for the
member count. All numbers are gated in `tests/validation/thermal.py`;
the model is a single horizontal cable in still air at sea level — trays,
conduit, bundling and solar load need derating on top.

## 6c. Professional PDF reports

The Cable Designer (**PDF Report…**, litz + single-wire pages), every antenna result window, and the
magnetics results window (**Save PDF Report…**) each produce a single
build-house-ready document: title and summary, the construction/geometry drawing,
the result curves or field map (Rac/Rdc for cable; S11 / impedance / radiation
pattern for antennas; r–z cross-section, |B| field map, and powers/L/M/k for
magnetics), and a BOM / construction schedule. Hand it to a wire manufacturer or
fab shop to have your design built.

## 6d. Interactive 3-D visualization

Every results window offers two levels of 3-D:

- **Pattern 3D tab** — the classic gain balloon, colored by dBi. Drag to rotate,
  right-drag or scroll to zoom; every tab also has the matplotlib toolbar for
  pan/zoom/save.
- **Show in 3D View** — puts the results into FreeCAD's own 3-D viewport *next to
  your geometry*, with full native rotate/zoom/pan/tilt navigation: the gain
  balloon, the wire path colored by current magnitude, and the near-field |E|
  plane. Each arrives as a colored surface object in the model tree; select it to
  adjust the color scale in its view properties, toggle visibility with the
  spacebar, or delete it. Because they are ordinary document objects, one camera
  drives geometry and overlay together — there is no separate pattern viewer to
  keep in sync.

The **Element Designer** and the **Array Designer** (Pro) carry the same button,
labelled **Show pattern in 3-D view**. It stays greyed out until a **Verify** has
actually produced a far field: a predicted array factor is not a measured
pattern, and EMStudio will not draw a balloon the solver never computed. The
balloon is sized to the geometry it sits beside, so an eight-element array gets
an array-sized pattern rather than the fixed 100 mm one that suits a single
patch.

One honest limitation on the Array Designer: its Verify builds the array in a
scratch document that is closed when the run finishes, so there is no array
geometry left to attach the pattern to. That overlay is centred on the **origin**
of your active document, not on an antenna. Element Designer patterns and the
Results-dialog overlays are placed relative to the geometry they came from.

## 6e. Tutorial: induction heating & wireless power (Elmer magnetics)

Phase 3 adds low-frequency magnetics: eddy currents, induction heating, and
coil-to-coil coupling, solved by **Elmer FEM** (detected via Detect Solvers;
needs `gmsh` + the CSC `elmerfem-csc` package). The geometry class is
**axisymmetric**: coaxial cylinders, tubes and rings centered on the Z axis —
exactly the round-billet/round-coil class commercial induction tools focus on.

**Induction heating in 60 seconds:**

1. **Template: Induction Heating** — an aluminum billet (r=15 mm) inside a
   20-turn work coil carrying 200 A peak at 2 kHz appears, with the material,
   the Coil Excitation, and the Elmer solver already configured.
2. **Run Solver** (~10 s). The results dialog reports the **billet Joule power
   [W]**, the coil's **effective inductance** and the **reflected resistance**
   (the series resistance the workpiece presents to your tank circuit —
   exactly `2·P/I²`).
3. **Show Fields in 3D** loads the solved B field / current density / Joule
   heating onto the geometry in the viewport (it's a `FemPostPipeline` —
   pick the field and color scale in its view properties).
4. **Save PDF Report** produces a build-house document: the r–z cross-section, the |B| field map, and the powers / coil L·R / temperature (WPT runs get the L1/L2/M/k coupling table).

Edit the billet `Conductivity` (S/m), the coil `Turns`/`Current`
(peak amps), or the sweep frequency and re-run. Set `FrequencyPoints` > 1 to
sweep P(f) and L(f) — points solve in parallel.

**Wireless power / coil coupling:**

1. **Template: WPT Coil Pair** — two 10-turn coils (mean radius 50 mm,
   2×2 mm cross-section) facing across a 20 mm gap.
2. **Run Solver**. With 2+ coils the backend automatically runs per-coil
   excitations and reports the full **inductance matrix (L1, L2, M)** and the
   **coupling coefficient k = M/√(L1·L2)** — the number that sets your
   resonant-link efficiency budget.
3. Move a coil (edit its Placement or re-create with a different gap) and
   re-run for k vs distance — or use **WPT: Sweep Coil Gap** to solve a whole
   range of gaps in one click and get the **k(gap) curve** (with CSV export).
   This is the parametric-study payoff: the physics rides on the geometry, so a
   sweep is just a loop of re-solves.

**Your own geometry:** model coaxial solids (Part Cylinder for billets; the cut
of two cylinders for a coil ring), assign a **Conductor** material (set
`Conductivity`; `RelPermeability` for magnetic parts) to workpieces, mark coil
rings with **Coil Excitation** (turns, peak current), add the **Elmer Magnetics
Solver**, Run. Currents are PEAK amplitudes; powers are time-averaged watts.

**Temperature (steady state):** the induction template also solves the billet
temperature — Joule heating in, convection h·(T−T_ambient) out on the body
surface. `SolveThermal` lives on the Elmer solver (with `AmbientTemperature`
and `ConvectionCoefficient`); the workpiece material needs
`ThermalConductivity` (W/m·K). The dialog reports T_max/T_mean per body and
the temperature field ships in the 3-D viewport VTU. It's the *equilibrium*
temperature: a free-air steady state of a real induction load can be
enormous — that is physics, not a bug; use a realistic cooling h (forced air
~50–300, water ~500–5000 W/m²K).

**Heating over time (transient):** flip `TransientHeating` on the Elmer solver
to get the temperature *rise* curve instead of only the equilibrium — set
`HeatingTime` (seconds) and `HeatingSteps`, and give the workpiece material a
`Density` (kg/m³) and `SpecificHeat` (J/kg·K) (the template ships aluminum
values). The field is solved once and the heat equation is stepped in time
(with σ(T), below, it is re-solved every step); the
report gains a heating-curve page and the results dialog notes the final
temperature and time. This answers "how hot, how fast" for a real IH cycle.

**Thermal depth (optional knobs):** `SurfaceEmissivity` on the Elmer solver
(with `RadiationTemperature`) adds grey-body **radiation** on top of
convection; `ThermalConductivityTempCoeff` (β) on the material makes
**k(T)** = k·(1 + β·(T − ambient)); and `ConductivityTempCoeff` (α) makes the
electrical conductivity temperature-dependent, **σ(T)** = σ/(1 + α·(T −
ambient)) — copper/aluminum α ≈ 0.004/K. σ(T) turns the solve into a genuine
two-way **coupled Joule** problem (the magnetic field and the temperature
iterate to a self-consistent state — a hot workpiece conducts less, so the
heating self-limits); it needs `SolveThermal` on and `ThermalConductivity`
set. All three default to off/0 and change nothing until you set them.

**Nonlinear iron (B-H saturation):** give the material a B-H curve via
`BHCurveB` (tesla) and `BHCurveH` (A/m) — paired lists, **B first**, starting
at 0, strictly increasing, ~40 points sampled roughly *uniformly in B* (the
workbench rejects malformed or column-swapped tables — a swapped table would
otherwise run silently wrong). The curve replaces `RelPermeability`. Two ways
to use it:

- **Static (DC)** — set the Elmer solver's `AnalysisType` to *Static (DC)*:
  exact nonlinear magnetostatics for gapped inductors, chokes and
  electromagnets. You get the B-field map and each coil's inductance **at its
  operating current** (drive it harder and watch L droop as the core
  saturates). The frequency sweep is ignored; there are no eddy currents,
  Joule heating or thermal results at DC (the solver says so if you ask).
- **Harmonic (AC)** — the default chain accepts B-H too, as an
  **effective-permeability approximation**: Elmer adapts the local
  permeability to the *peak* flux-density amplitude each iteration. Power
  and inductance reflect saturation, but the waveform stays sinusoidal — no
  harmonic distortion is modeled. For waveform-accurate saturation use the
  Static mode (or a future transient mode).

*Honest limits:* AC B-H is the peak-|B| effective-µ approximation above (no
waveform distortion, no hysteresis loss). Non-coaxial geometry needs the
3-D mode below (the axisymmetric analyses reject it with a clear message).

**General 3-D magnetostatics (any solid):** set the Elmer solver's
`AnalysisType` to *3-D Magnetostatic (DC)* and the axisymmetric limit is
gone — every referenced solid is meshed as-is (WhitneyAV chain, validated
against closed-form coil fields at −0.6 % and the measured TEAM Problem 7
benchmark at 2.8 % RMS). Mark any closed-loop coil solid (racetrack, bent,
off-axis — not just rings) with **Coil Excitation**; it is driven by
N·I ampere-turns. Try **Template: 3-D Solenoid (Magnetostatic)** — a tube
coil that solves in ~30 s — then swap in your own coil shape. Results:
the **B-field map** in the 3-D viewport ("Show Fields in 3D"). Notes:
coil bodies must not touch each other or the air boundary; a closed
coil's circulation sense is chosen by the solver, so if the field comes
out inverted simply toggle the Coil's `Reversed`; there are no
eddy/thermal quantities at DC, and 3-D inductance extraction is a
planned slice (the axisymmetric analyses report L/M/k today).

## 6f. Tutorial: resonant-cavity modes (Palace FEM)

Phase 4 adds full-wave finite-element analysis via **AWS Palace** — the first
slice computes the **resonant modes** of a cavity (needs `palace` + `gmsh`; see
Detect / Install Solvers).

1. **Template: Resonant Cavity** — a 40×20×60 mm air-filled box with PEC walls
   and a Palace eigenmode solver appears.
2. **Run Solver** (~1 min at the default FEM order 2). The results table lists
   the resonant **frequencies (GHz)** and **Q** of the lowest modes; the
   fundamental (TE101) is ~4.504 GHz — matching the exact closed-form value to
   0.001 %.
3. Edit the box dimensions (or fill it with a dielectric: set the material's
   permittivity) and re-run — the modes scale as you'd expect.

Set `NumModes` for how many modes to compute and `Order` on the solver for
accuracy (2 is fast and already <1 %; 3–4 is spectral-quality but the
preconditioner setup dominates run time).

**Beyond boxes — general 3-D geometry.** The eigenmode solver is not limited to
rectangular boxes. **Template: Cylindrical Cavity** builds a circular cylinder
(R=30 mm) whose fundamental **TM010** mode is ~3.825 GHz (matching the exact
Bessel-function value to 0.25 %). Any closed solid works the same way — draw a
`Part` solid (cylinder, sphere, chamfered box, a revolved profile, …), assign it a
Dielectric material, add a Palace solver, and Run: EMStudio exports the solid to a
BREP, meshes its whole boundary as the PEC wall, and solves. *Honest limits:*
general geometry is wired for **eigenmodes**; driven S-parameter / wave-port
analyses are still box (waveguide) or coax.

## 6g. Tutorial: waveguide S-parameters (Palace wave ports)

The second Palace slice computes **S-parameters** of a waveguide using
**wave ports** — Palace solves the port cross-section's own modal field, so
there's no analytic mode to specify.

1. **Template: WR-90 Waveguide** — a straight air-filled WR-90 X-band section
   (22.86×10.16 mm, 30 mm long) with a wave port on each end and an X-band
   (8–12 GHz) sweep. The Palace solver's `AnalysisType` is set to
   "Driven S-parameters".
2. **Run Solver** (~1 min at FEM order 2). The S-Parameters tab shows |S11| and
   |S21| vs frequency; the matched uniform guide gives |S11| ≈ −90 dB (no
   reflection) and |S21| ≈ 0 dB (lossless), with the S21 phase tracking the
   TE10 propagation constant to a fraction of a degree.
3. Change the length, cross-section, or fill it with a dielectric and re-run.

The guide axis is auto-detected as the solid's longest dimension (the two faces
perpendicular to it become the wave ports).

**Non-box guides (general 3-D).** Driven S-parameter analyses are not limited to
rectangular boxes: draw **any** closed solid (a **cylinder** for a circular
waveguide, a stepped or tapered guide, …), assign it Air and a "Driven
S-parameters" solver, and EMStudio exports it to a BREP and tags its two end faces
as wave ports automatically. The **Template → Circular Waveguide** starts one for
you — a 30 mm-radius circular guide whose dominant TE11 mode cuts off at 2.93 GHz,
swept in its single-mode band (3.0–3.8 GHz); Palace finds the TE11 mode on the
round face with no extra setup.

**Fast wide-band sweeps.** For a dense S-parameter curve over a wide band, turn on
**`FastSweep`** on the Palace solver (works for both waveguide and coax driven
analyses). Instead of one full solve per frequency point, Palace builds a
reduced-order model from a handful of full solves and interpolates the rest — a
WR-90 41-point sweep needs only ~6 full solves and still matches theory at every
point. Raise `FrequencyPoints` for a smoother curve at almost no extra cost;
tighten `AdaptiveTol` (default 1e-3) for more accuracy at the price of more full
solves.

**Adaptive mesh refinement (AMR).** For more accuracy without hand-tuning the mesh,
set **`MeshRefinement`** on the Palace solver to the number of refinement passes
(default **0 = off**). Palace estimates where the solution error is largest,
refines the mesh only there, and re-solves — so degrees of freedom are spent where
they matter instead of uniformly. It works for **both** eigenmode and driven
analyses. `RefinementTol` (default 0.01) lets refinement stop early once the global
error falls below it. Each pass is a full re-solve, so **1–3 passes** is the useful
range (and pairs well with FEM order 2). Example: an Order-1 cavity's fundamental
goes from 0.32 % to 0.074 % of the exact value with 2 passes (the mesh grows from
~2,000 to ~30,000 elements automatically). Leave it at 0 for the fastest solve.

## 6h. Tutorial: microstrip notch filter (PCB S-parameters)

EMStudio simulates PCB microstrip circuits with **trace-aware meshing** so the
S-parameters are physical — the automatic antenna gridder is too coarse for a
sub-millimetre trace, so microstrip runs switch to a finer, dielectric-aware grid.

1. **Template: Microstrip Notch Filter** — a 50 mm, 0.6 mm-wide microstrip line on
   0.254 mm RO4350B (εr 3.66) with a 12 mm open quarter-wave stub, and two
   microstrip (**MSL**) ports for S11/S21 over 0.01–7 GHz.
2. **Run Solver** (~40 s FDTD). The S-Parameters tab shows a deep **S21 notch near
   3.66 GHz** — where the open stub is a quarter guided-wavelength long and shorts
   the line — with a flat passband either side.
3. Change the stub length to move the notch, or the line width to change the
   impedance, and re-run.

**How it works.** Set the openEMS solver's **`MicrostripMeshMode = Auto`** (the
default) on any analysis with an MSL port: the grid is resolved at λ/50 *in the
dielectric*, graded across the strip (~6 cells), and the simulation box hugs the
board so the line terminates cleanly in the absorbing boundary; the ground is the
PEC bottom boundary. Set it to `Off` to force the antenna-scale grid (for
comparison/debugging). MSL ports carry a `PropagationDirection` (along the line)
in addition to the field `Direction` (down to ground).

*Honest limits:* validated for the single-stub notch filter; general microstrip
circuits (bends, couplers, multi-stub filters) and characteristic-impedance
renormalization are follow-ons.

## 6i. Tutorial: coaxial-line S-parameters (Palace lumped ports)

Palace can also drive a **coaxial line** through a **radial lumped port** at each
end — a second S-parameter method alongside the waveguide wave ports.

1. **Template: Coaxial Line** — an air-filled coax (inner radius 0.5 mm, outer
   1.15 mm → ~50 Ω, 20 mm long) with a lumped port on each annular end face,
   swept 2–6 GHz. The Palace solver's `AnalysisType` is "Driven S-parameters
   (coax)".
2. **Run Solver** (~35 s at FEM order 2). The S-Parameters tab shows |S11| and
   |S21|: a uniform line referenced to its own characteristic impedance is
   matched — |S11| well below −20 dB, |S21| ≈ 0 dB — with the S21 phase advancing
   as −βL (β = 2πf√εr/c, no cutoff).
3. Change the radii (to set the impedance, Z0 = (η0/2π)/√εr·ln(b/a)), the length,
   or fill it with a dielectric and re-run.

The coax must be a true annulus (a tube: an outer cylinder with an inner cylinder
cut out), coaxial with the Z axis; the inner/outer **radii are read from the
cylindrical surfaces**, so they stay exact under the GUI. *Honest limits:*
straight coax for now; microstrip/CPW lumped ports and general 3-D geometry are
the next Palace slices.

## 6i². Tool: Element Designer (requirements → a dimensioned element)

The Element Designer turns stated requirements into **one dimensioned radiating
element** — it reports the element's feed impedance, gain and geometry, and
stops there. Impedance **matching** now ships as its own step: the §7 **System
Matching Designer** (§6i³ below) takes that feed Z and synthesizes the network —
while combiners, arrays and direction-finding remain future §7 slices. Open
**Element Designer** from the toolbar.

1. Fill the **Requirements** — or pick a **Service preset** first: 20
   verified bands (FM/AM broadcast, airband, marine VHF, NOAA weather, the
   ham bands 80 m-70 cm, CB, 433 ISM, LoRa 868/915, Wi-Fi 2.4/5 GHz, GPS L1,
   ADS-B) auto-fill the frequency/band/polarization/pattern schema, with the
   regional variants noted (US values primary; provenance in
   docs/upstream/service-presets-anchors). Then: frequency (for a BAND
   design this is the low
   edge f_lo), an optional **Band top (f_hi)** (a band ratio above ~1.5 routes
   the recommender to the log-periodic), an optional target gain (dBd or dBi —
   both are always shown, since NBS Yagi tables are dBd while solvers report
   dBi), pattern, polarization, an optional **max dimension**, and the conductor
   diameter.
2. **Recommend family** ranks the element families with a printed one-line
   rationale per rule — e.g. "12 dBd → NBS TN-688 2.2-λ boom class (boom fits
   the 3 m envelope)". All five core families (wire, Yagi, patch, LPDA, small
   antenna) are available; requests that are electrically small get the **Chu
   bandwidth guardrail** up front. **Use top family** switches to the best
   available page.
3. On the **Wire** page pick the type — half-wave dipole, quarter-wave monopole,
   folded dipole, or the 5/8- / 3/4- / full-wave verticals — and the **K
   factor** (thin-wire 0.95, the end-effect curve measured on this repo's own
   NEC2, or custom). The synthesized **length is editable** (a badge shows
   synthesized vs edited; Reset re-synthesizes) and **Length → f₀** inverts a
   known length back to its design frequency. On the **Yagi-Uda** page choose
   "by gain target" (the smallest NBS TN-688 boom that meets it) or a boom
   length directly, and optionally a metal-boom diameter (adds the Fig 10 build
   correction to the physical cut lengths). The Predicted tab lists every
   element with its bare-wire length (what NEC2 models) and its cut length (what
   you build on a metal boom), the boom length, spacing and the measured NBS
   gain in dBd and dBi. Yagi element lengths come from TN-688 Table 1 with the
   diameter/boom corrections — validated on the scanned page images (see
   `docs/upstream/tn688-yagi-anchors.md`). On the **Microstrip patch** page set
   the substrate (εr and h, or pick a laminate preset — RT/duroid, Rogers, FR-4,
   alumina) and the feed impedance; the transmission-line synthesis gives the
   radiating width W, the resonant length L (with the fringing extension), the
   effective permittivity, the radiating-edge resistance and the probe-feed
   offset. The resonant-frequency model is accurate to ~±5 % (the feed offset is
   a rougher estimate); **Verify with openEMS** runs an FDTD solve (~seconds) and
   reports the achieved resonance and gain. Patch equations are standard antenna
   physics, verified against the published 10 GHz example and open sources
   (`docs/upstream/patch-tl-anchors.md`). On the **LPDA** page (a BAND design —
   set Frequency = f_lo and Band top = f_hi first) design by a gain target
   (6.5-11 dBi on the corrected Butson-Thompson contour calibration — Carrel's
   original charts read 1 dB optimistic) or by explicit τ/σ, and set the target
   mean input resistance R0; the Carrel synthesis reports every element length/
   position, the apex angle, boom length, and the **crossed-feeder Z0** that
   centres the input resistance on R0. Generated LPDAs model the transposed
   boom feeder with real NEC2 **TL cards** (`EMStudio::TransmissionLine`
   objects — ideal non-radiating lines, the standard LPDA modeling practice).
   Expect log-periodic ripple around R0, a gain droop at exactly f_lo (the
   active region truncates), and possible narrow VSWR spikes between low-end
   element resonances — documented "weak spots"; a tuned rear stub (§7) can
   move them. Equations verified from the original Carrel paper + open sources
   (`docs/upstream/lpda-carrel-anchors.md`).
4. The right tabs show the dimension-annotated **Schematic**, the **Predicted
   Performance** read-out (feed R ± jX, gain in dBi *and* dBd, honest per-type
   notes — e.g. the 5/8-wave's capacitive feed needs a series-L network, now
   synthesized by the §7 System Matching Designer below),
   and **Verify**.
5. **Verify with NEC2** solves your actual design (edited lengths included)
   through the production writer off-thread and reports **predicted vs
   achieved**: the resonance (picked inside a per-type resistance window —
   multi-wire structures have kΩ anti-resonances that a naive "first X = 0"
   search would hit), feed R, and the pattern peak. For the LPDA it sweeps
   the whole band (median/worst VSWR vs R0, band-mean R) and pins the far
   field at the geometric band centre.
6. **Accept & Generate** creates the runnable analysis (geometry, PEC wire
   material, feed port, NEC2 solver) in the active document — **Run Solver**
   from there as usual.
7. **PDF Report…** saves a two-page build deliverable for the current design:
   a design-summary table (with every caveat/warning spelled out), a
   dimensioned build sketch, and the element schedule (per-element positions
   and lengths — for a Yagi both the bare-wire and metal-boom cut lengths).
   The standard EMStudio engineering disclaimer travels on every page, so the
   document is safe to hand to a build house or supplier as-is.

Note on tiers: the Element Designer as shipped — all five families, service
presets, Verify, PDF reports — is part of the **free** EMStudio core and
stays free. **EMStudio Pro ($149, available now) does not change this dialog**;
it adds the §7 System Designer and the AI assistant. Separately, ideas still
only on the roadmap and promised to nobody — solver-in-the-loop optimization,
exotic families, AI-guided intent — are NOT part of what Pro sells today.

The **Small antenna** family routes to the dedicated VLF/LF/MF designer below
(§6j) — under ~λ/10 the Chu regime rules and that dialog's loading/efficiency
budget is the honest tool.

## 6i³. Tool: System Matching Designer (§7 — element Z → a matching network)

Where the Element Designer stops at the element's feed impedance, the **System
Matching Designer** — the first user-facing slice of the §7 System / Sub-system
Designer — takes that Z and synthesizes the **matching network** that transforms
it to your system impedance. Open **System Matching Designer** from the toolbar.

1. **Element (load) source.** Either type the load directly — **R + jX** at a
   frequency — or ingest a **live NEC2 sweep** of a wire antenna already in the
   document, so the match rides on the element's real swept Z(f).
2. **Target system impedance Z0** (default **50 Ω**).
3. **Topology.** Pick one — **L-match** (lowpass or highpass), **pi**, **T**,
   **quarter-wave transformer**, **binomial** (maximally-flat multisection),
   **single-stub** tuner, or **hairpin** — or press **Recommend** to have
   EMStudio rank the applicable topologies with a printed one-line rationale per
   rule. Honest constraint, enforced in the dialog: the real-load-only
   topologies (pi / T / quarter-wave / binomial / hairpin) **refuse a reactive
   element** — pre-resonate it first — while the **L-match** and **single-stub**
   absorb the load reactance directly.
4. **Read the predicted curves.** The dialog plots predicted **VSWR**, **return
   loss** and **insertion loss** vs frequency, and prints a **component /
   section schedule** (L and C values, or the transformer/stub line impedances
   and lengths).
5. **Snap to E-series (optional).** Tick the standard-value snap
   (**E6 / E12 / E24 / E96**) to round the lumped components to real-world
   parts; the read-out then shows the **post-rounding** match, so you see what
   the buildable network actually achieves rather than the ideal one.
6. **Verify.** Press **Verify** to re-sweep the element live through NEC2
   (off-thread) and plot the **achieved** match against the element's real Z(f) —
   predicted vs achieved, the same discipline as the Element Designer's Verify.
   (Validation run: the shipped 300 MHz dipole ingests at ≈ **71.9 Ω**, matches
   to 50 Ω, and the achieved **VSWR ≈ 1.01** — down from the bare antenna's
   1.43.)
7. **PDF Report…** writes a two-page matching-network deliverable — summary, the
   predicted curves, the schematic, and the component / section schedule — with
   the standard EMStudio engineering disclaimer on every page.

Scope, stated honestly: this slice delivers impedance **matching** only, and it
is part of the **free** EMStudio core. Filter/diplexer synthesis ships as an
engine (S3); the Array Designer ships below (S4); RF direction-finding remains
a future §7 slice.

## 6i⁴. Tool: Array Designer (§7 — a phased array driven by CURRENTS)

A phased array is specified by its element **currents** — but NEC2's EX cards
drive **voltages**, and with strong mutual coupling those are very different
things. Feeding a two-dipole cardioid equal-magnitude quadrature *voltages*
gives ~3 dB front-to-back; solving for the voltages that produce the target
*currents* gives ~30 dB on exactly the same wires. The **Array Designer** does
the second thing, live. Open it from the toolbar.

1. **Array.** Design frequency, **N** parallel dipole elements (2-16), spacing
   in wavelengths, element half-length (default 0.2389 λ — the resonant
   0.478 λ dipole) and wire radius.
2. **Drive distribution.** Pick a named distribution — **Broadside**,
   **End-fire** (either direction), **Hansen-Woodyard** enhanced end-fire,
   **Scanned** (enter the angle from broadside), or the **Cardioid pair**
   (N = 2, quadrature). The derived per-element target currents are shown as a
   read-only table; per-element amplitude **tapers** (binomial /
   Dolph-Chebyshev / Taylor n̄) arrive with the S5 slice.
3. **Predicted** read-outs come from the gated analytic engine: **exact**
   array-factor directivity (numeric visible-region peak — not the textbook
   shortcuts, which fail off-broadside), exact half-power beamwidth, the
   first-sidelobe level, and a **grating-lobe guard** that flags a spacing too
   coarse for the chosen steering.
4. **Verify (live NEC2)** builds a transient N-dipole model and runs the full
   drive chain: N mutual-impedance solves → **V = Z·I** → one multi-excitation
   run. The **Pattern** tab overlays the achieved azimuth cut on the predicted
   one; the **Drive table** tab lists, per element, the EX **voltage** to
   apply, the **active (driving-point) impedance** — what a feed network
   actually sees, NOT the isolated element's Z — the input power, and the
   achieved-vs-target current error (typically ~1e-4, the solver's print
   precision). Warnings appear when a drive is **not passively realizable**
   (negative driving-point resistance — an element absorbing power from its
   neighbours) or when the drive voltage is extreme (anti-resonant elements).

5. **Amplitude taper** (S5). Multiply a taper onto the distribution:
   **Binomial** (zero interior sidelobes, huge dynamic range — impractical
   past ~8-10 elements and the dialog says so), **Dolph-Chebyshev** (pick the
   sidelobe level; the equal-ripple floor is EXACT, and the dialog warns when
   the spacing exceeds the taper's d_max), or **Taylor n̄** (pick level and
   n̄; the realized first lobe is *near* — deliberately not equal to — the
   design level, with far lobes decaying, which is the point of n̄ over
   Chebyshev). Efficiency and dynamic-range read-outs quantify the trade.
   Verified live: the Dolph-tapered steered 8-element array reproduces its
   **−26.0 dB design floor to 0.04 dB on real coupled dipoles**, against
   −12.7 dB for the uniform drive — 13.4 dB bought for 0.58 dB of gain.
6. **Export pattern CSV** (after a Verify) saves the achieved far field in
   the format the §6 Coverage tools load as an antenna pattern — your array
   drives the coverage map (grounded arrays: pick a take-off elevation above
   the horizon).

Honest scope: linear geometry, named distributions, dipole elements. Planar
and circular array factors ship as engine functions (gated) — a 2-D dialog is
future work. TL/corporate feeds are a **different feed model** (one driven
port plus transmission lines — the LPDA pattern) and are refused in the array
chain rather than silently mixed. Part of the **free** EMStudio core.

## 6j. Tool: Small-Antenna Designer (VLF / LF / MF)

At VLF/LF a resonant antenna would be kilometres long, so real antennas are a tiny
fraction of a wavelength — the electrically-small (Chu–Harrington) regime, where the
full-wave field solvers are impractical and closed-form models are the right tool.
Open **Small-Antenna Designer (VLF/LF)** from the toolbar.

1. Pick a **Type**: short monopole (vertical, over ground), short dipole, or small
   loop (the classic VLF receive / direction-finding antenna).
2. Set the **Frequency** — or pick a **band preset** (VLF 20/24 kHz, LF 40 kHz, …)
   from the list.
3. Enter the **Geometry** (mast height / dipole length / loop diameter + turns and
   wire radius) and the **Loss budget** (total loss resistance — at VLF the ground
   system usually dominates and sets efficiency — plus the VSWR bandwidth threshold).
3a. For a serious VLF/LF vertical, open the **Top loading & ground** tab
   (monopole type): pick the hat (flat-top of n wires, T, inverted-L, or a
   solid/mesh plate with area+perimeter), the radial ground screen (N
   radials, screen radius, earth preset from sea water to rocky), and your
   insulation voltage limit. The read-out chains the verified classic
   design set: hat capacitance (the plate+fringe model reproduces the
   published scale-model measurements within ~0.5 %, real hats read
   0-10 % above it), the trapezoid effective height, radiation resistance,
   the ground-system resistance (with the honest note where the screen
   stops beating bare earth), the efficiency ladder, and the
   voltage-limited radiated power / 3-dB bandwidth — the classic
   "VLF antennas are voltage-limited devices" numbers. Umbrella guys:
   maximum effective height occurs near a guy-insulator ratio of 0.35,
   and a 0.7 ratio buys roughly ×8 power capability and ×3 bandwidth.
4. **Update**. The right panel shows:
   - **Predicted Performance** — radiation resistance, effective height/length,
     radiation efficiency, the ka electrical size, the **Chu minimum Q** and the
     resulting fractional bandwidth, and (for a monopole) the static capacitance and
     the **series loading inductance** needed to resonate the large capacitive
     reactance. It ends with the **band → recommended-method** read-out.
   - **Sketch** — a dimension-annotated 2-D drawing with the triangular
     short-antenna current distribution.
   - **Chu Q limit** — the minimum-Q-vs-size curve with your design point marked, the
     hard physics reason a VLF antenna is inherently narrow-band.

The banner at the top routes you to the EMStudio method that is actually valid at
your frequency (analytic + NEC2-with-ground at VLF/LF; the full-wave engines higher
up) — because no single solver honestly spans VLF to mmWave.

## 6k. Tutorial: monopole over ground (VLF/LF via NEC2)

For a wire/monopole structure at VLF/LF you want the actual method-of-moments
solve with a ground — the small-antenna calculator gives the closed-form estimate,
NEC2 gives the modelled impedance including ground loss.

1. **Template: Monopole over Ground (VLF/LF)** — a base-fed short λ/10 vertical
   mast at 100 kHz standing on a ground plane, with a NEC2 solver.
2. **Run Solver** (~1 s). Over the default **perfect ground** the feedpoint
   impedance is ≈ **4 Ω − j570 Ω**: the small real part is the radiation resistance
   (analytic Rr = 40π²(h/λ)² ≈ 3.95 Ω) and the large negative reactance is why a VLF
   monopole needs a base **loading coil** to resonate.
3. Select the **SolverNEC2** and set **GroundType → Finite (Sommerfeld)** in the
   property editor, with `GroundEpsilonR` / `GroundConductivity` for your soil
   (average earth 13 / 0.005 S/m; sea water 81 / 5; poor/dry 4 / 0.001). **Run**
   again: the real part jumps to tens of ohms — that extra resistance is **ground
   loss**, and the radiation efficiency (Rr / R) collapses to a few percent. This is
   the defining VLF reality: without a large radial ground system a short monopole
   over real earth is very inefficient.
4. Change the **height fraction** in the template call (0.25 = a quarter-wave
   monopole, ≈ 36 Ω over perfect ground — the classic matched vertical) or the
   frequency to explore other cases.

*Ground modelling note:* NEC's `GN` card gives the perfect-image or finite-earth
(Sommerfeld) ground; buried radials are beyond nec2c (they need NEC-4) — model a
counterpoise as slightly-elevated wires. See A.D. Watt, *VLF Radio Engineering*
(1967) for the antenna types and ground systems this regime uses.

## 6l. Tool: Co-site Interference Calculator

When several radios share one site their transmitters and receivers interfere. Open
**Co-site Interference Calculator** from the toolbar.

1. Fill the **radio table** — one row per radio, each a transmitter, a receiver, or
   both: label, TX frequency/power, and RX frequency/bandwidth/sensitivity/blocking.
   Use **+ radio / − radio** to size the list. (Labels are your own — the tool ships
   no site data.)
2. Set the **Isolation** (antenna-to-antenna, dB — the same figure the future
   isolation-matrix feature will compute per pair), the **Junction IP3** (the
   third-order intercept of the assumed mixing point — a passive "rusty-bolt"
   junction is far worse than a linear amplifier), and the **Max IMD order**.
3. **Analyze.** The **Report** tab lists:
   - **Intermodulation hits** — mixing products (2f1−f2, f1+f2−f3, …) that land in a
     receiver's passband, with their level from the intercept-point relation and how
     far above the receiver's sensitivity they sit.
   - **Receiver desensitization** — strong off-channel transmitters that exceed a
     victim's front-end blocking level.
   - **Co-channel clashes** — transmit carriers inside a receiver passband, with the
     desired-to-undesired (D/U) ratio.
   - **Broadband-noise** elevations.
   The **Frequency map** tab plots the transmit carriers, receiver passbands and
   intermod products on one frequency axis.
4. **Optimize TX frequencies** searches channel assignments (retuning each
   transmitter within a few channels) that minimise the interference, applies the
   best plan and re-analyses — clearing the frequency-fixable collisions
   (intermod / co-channel). Desensitization is *not* frequency-fixable (a strong
   off-channel signal blocks the front end at any frequency); reduce it with more
   antenna isolation or less transmit power.

This is the deterministic co-site analysis; the antenna-to-antenna isolation it uses
can be a single figure you type in, or computed from geometry (next).

## 6m. Tool: Antenna Isolation Matrix

The isolation the co-site calculator needs — how strongly two antennas couple — can
be extracted from the antennas themselves with NEC2.

1. **Template: Co-site Antenna Pair** — two parallel half-wave dipoles at 300 MHz,
   half a wavelength apart, each with its own feed port (a two-port analysis).
2. Select the analysis and run **Antenna Isolation Matrix**. EMStudio drives each
   antenna in turn (leaving the others as shorted wires), builds the admittance
   matrix, inverts it to the impedance/scattering matrix and reports the **isolation
   (dB)** between every pair plus the self/mutual impedances. For the default pair
   the isolation is ≈ 13.8 dB (mutual impedance Z ≈ −15 − j28 Ω, matching the
   Balanis parallel-dipole result). Isolation rises as you move the antennas apart.
3. Feed that isolation figure into the **Co-site Interference Calculator** above.

Works for any set of wire antennas with a feed port each (add more dipoles/monopoles
to the analysis). Planar/3-D port-to-port isolation via openEMS/Palace is a later
slice.

## 6n. Tool: Point-to-Point Link Budget

Estimate how a signal propagates between two sites. Open **Point-to-Point Link
Budget** from the toolbar.

1. Enter the **link**: frequency, distance, transmit power, transmit/receive antenna
   gains and heights, and the receiver sensitivity (plus an EIRP for the field-
   strength readout).
2. **Analyze.** The **Link budget** tab shows the **free-space** and **two-ray
   plane-earth** path loss, the **breakpoint** distance (beyond which the d⁴
   plane-earth law governs), the **received power** and **fade margin** (whether the
   link closes), and the free-space **field strength** in dBµV/m. The **Path loss vs
   distance** tab plots both models against distance, marking the breakpoint and your
   link.

The models each state their regime — free-space for an unobstructed line of sight,
plane-earth for a link above a reflecting ground beyond the breakpoint. Terrain
shadowing over a real elevation model now has its own map — see **Area Coverage
Map** below; ground-wave (ITU-R P.368, flat or spherical earth) for LF/MF
broadcast follows.

## 6o. Tool: Area Coverage Map

Predict a transmitter's **coverage footprint** — received power or field strength
over a lat/lon grid — with optional terrain shadowing and antenna-pattern
modulation, then export it to Google Earth. Open **Area Coverage Map** from the
toolbar.

1. **Place the transmitter**: latitude / longitude (you supply the location —
   nothing is preset), height above ground, frequency, transmit power (dBm) and the
   antenna's peak gain (dBi).
2. **Set the grid**: coverage radius (km), grid points per side (finer = slower,
   especially with terrain), receiver height, the **propagation model** (see below),
   the metric (**received power dBm** or **field strength dBµV/m**), a coverage
   **threshold** (cells below it are drawn transparent and excluded from the
   covered-area %), and the earth **k-factor** (4/3 for a standard atmosphere; a
   large value = flat earth).
   - **Propagation model — Auto**: free-space, switching to the two-ray plane-earth
     d⁴ law beyond the breakpoint (terrain-aware when a DEM is loaded).
   - **Propagation model — Ground-wave flat earth (LF/MF, P.368, <100 km)**: the
     vertically-polarised surface wave over homogeneous **ground type** (sea
     water … very dry, ITU-R P.368 Table 2). Sea water carries farthest; dry
     ground least; lower frequencies reach farther. This is a smooth-earth model —
     the DEM and antenna heights are not used, and it is a flat-earth
     approximation valid to roughly **100 km**. Field strength is its natural
     output.
   - **Propagation model — Ground-wave spherical (ITU-R P.368-10)**: the
     **reference** ground-wave model — EMStudio's validated port of the NTIA
     LFMF implementation that is an integral part of Recommendation P.368-10
     (flat-earth Sommerfeld switching to the Wait/Hufford curved-earth residue
     series). Valid **0.01–30 MHz** out to **10000 km**; also a smooth-earth
     model (DEM/heights unused, ground-based reference terminals). Below
     **10 kHz** it refuses to compute — that band is ionospheric (ITU-R P.684),
     and extrapolating a ground-wave model there would be dishonest.
   - **Propagation model — Hata / COST-231 (150 MHz–2 GHz)**: the classic empirical
     land-mobile **clutter** model — pick the **Environment** (urban small/medium,
     urban large/metropolitan, suburban, open/rural; the category *is* the clutter
     model — no land-use raster needed). 150–1500 MHz uses Okumura-Hata, 1500–2000
     MHz COST-231-Hata (formulas validated against the COST 231 Final Report and a
     published worked example). Median loss for macro-cells: TX height 30–200 m
     above rooftops, RX 1–10 m, distances 1–20 km — outside those ranges it
     extrapolates but is unvalidated. The DEM is ignored.
3. **Terrain (optional)**: point **Browse** at an SRTM **.hgt** tile or a
   **GeoTIFF** (or a folder of tiles). With a DEM, each grid point gets a
   great-circle terrain profile through a knife-edge diffraction model with the
   earth-curvature bulge, so hills **shadow** the map. The **Diffraction** selector
   chooses the method: **Single-edge (Deygout)** — the one dominant obstacle, fastest
   (the default); **Multi-edge (Deygout)** — recursively adds the secondary ridges the
   single edge misses; **Multi-edge (Epstein–Peterson)** — the successive-edge sum
   (tends to under-estimate where Deygout over-estimates); **Bullington** — folds all
   edges into one equivalent edge (the classic quick estimate; optimistic on
   multi-obstacle paths). All are validated against the NTIA TR-26-580 worked cases.
   The **Two-ray plane-earth on clear paths** checkbox makes unobstructed terrain
   paths carry the same two-ray (d⁴) ground loss as the smooth-earth mode — a flat
   DEM then matches the no-DEM footprint exactly (on clear paths it replaces the
   near-grazing edge term; shadowed cells are untouched). Leave the DEM empty for a
   smooth-earth footprint (free-space, switching to the two-ray plane-earth d⁴ law
   beyond the breakpoint). *No GDAL/QGIS needed — .hgt is read directly; the GeoTIFF
   reader covers the common uncompressed/DEFLATE single-strip case (LZW/tiled
   GeoTIFFs: re-save with `gdal_translate -co COMPRESS=DEFLATE`, or use .hgt).*
4. **Antenna pattern (optional)**: leave on **Omni (peak gain)**, or choose **From
   pattern CSV** and browse to a far-field pattern exported from a NEC2/openEMS
   antenna solve — the horizontal cut at your take-off **elevation** and antenna
   **orientation** (compass bearing) then shapes the footprint into a real lobe.
5. **Compute coverage** draws the heatmap over the map (transmitter marked) with a
   colour bar and a stats read-out (peak level, covered-area %, ERP). **Export
   KML…** writes a `.kml` GroundOverlay plus its `.png` you can open directly in
   **Google Earth** or **QGIS**.

Honest scope: the terrain mode is free-space + knife-edge diffraction (single-edge,
multi-edge Deygout / Epstein–Peterson, or Bullington) + the effective-earth bulge,
plus — with the checkbox — the two-ray ground loss on clear paths. The multi-edge
Deygout is uncorrected (no Causebrook term), so it over-estimates deep
multi-obstacle shadows, Epstein–Peterson under-estimates, and Bullington is
optimistic. Clutter/land-use modelling is a later slice; the spherical-earth
ground-wave beyond ~100 km shipped as the **Ground-wave spherical (P.368-10)**
model above.

## 6p. Tool: Multi-Station Service / Interference (D/U)

Two or more transmitters on the same channel interfere with each other. This tool
composes their coverage footprints onto **one shared map** and, for a chosen **wanted**
station, shows where it is actually **served** — reachable *and* free of interference —
the way broadcast engineers draw service and interference contours. Open **Multi-Station
Service / Interference** from the toolbar.

1. **List the transmitters** in the table: label, latitude / longitude (you supply
   them), height, frequency (MHz), transmit power (dBm) and antenna peak gain (dBi).
   Use **+ station / − station** to size the list. The default example is a co-channel
   MF pair ~30 km apart.
2. **Pick the wanted station** and its protection: choose a **Protection preset** (or
   type a value) — the required **D/U** (wanted-minus-unwanted, dB): e.g. *FM
   co-channel 20 dB* (FCC 73.215), *AM/MF co-channel 26 dB* (FCC / ITU Region 2), *FM
   stereo 45 dB* (ITU-R BS.412). Adjacent-channel presets are legitimately **negative**
   (receiver selectivity lets the interferer be stronger). Choose a **Service preset**
   for the protected field threshold (e.g. FM 60 dBµV/m, AM 0.5 mV/m = 54 dBµV/m), and
   how interferers combine: **Power sum (RSS)** — the physical sum of interfering powers
   (ITU-R BT.2265) — or **Worst case** — the single strongest (FCC OET-69).
3. **Set propagation & grid**: model (**Ground-wave flat earth** for quick LF/MF
   looks under ~100 km, **Ground-wave spherical (P.368-10)** — the honest engine
   for real broadcast-interference distances — or **Auto** free-space/
   plane-earth), ground type, map radius, grid points, and the **Display** layer.
4. **Compute contours** classifies every cell as **served** (green — covered *and*
   D/U ≥ the protection ratio), **interference-limited** (red — covered but the ratio
   falls short) or **no service** (transparent — below the coverage threshold), and
   reports the served / interfered / covered fractions. Switch **Display** to:
   - **D/U ratio (dB)** — a diverging map with a white contour line at the protection
     ratio (inside it = protected);
   - **Wanted field** / **Interference field** — the raw field-strength layers;
   - **Best server (network)** — for a set of co-channel stations, which transmitter is
     strongest at each cell and whether that server is interference-free.
   **Export KML…** writes the chosen layer as a Google-Earth / QGIS overlay.

Honest scope: the D/U composition inherits each station's shipped physics (Auto =
free-space / plane-earth ± single-edge DEM diffraction; Ground-wave = P.368
flat earth to ~100 km, or the P.368-10 spherical earth to 10000 km). The protection ratios are regulatory/planning **reference values** that are
region- and method-dependent — each preset names its source and context; pick the one
matching your service and regulator rather than assuming one universal number. Station
locations, frequencies and ground are entirely user-supplied.

## 7. Understanding the results

- **S11 (dB)**: reflection at the port; below −10 dB is a usable match.
- **S21 (dB)**: transmission to a second port; ~0 dB passband, deep dip at a notch.
- **VSWR**: the same match expressed as a ratio; 2:1 equals −9.5 dB S11.
- **Impedance**: R + jX at the feed. Resonance = X through zero.
- **Pattern (dBi)**: gain relative to isotropic at the best-match frequency; θ is
  measured from +Z, cuts at φ = 0°/90°.
- **Touchstone (.s1p)**: standard S-parameter exchange format (references your port
  impedance, default 50 Ω).
- All solver artifacts (decks, raw outputs, CSVs) stay in the working directory
  printed in the Report view — nothing is hidden.

## 7b. Windows users — honest status

The **workbench itself and the entire Cable Designer (Litz | Coax | Single Wire) work on Windows FreeCAD**
with no solvers installed (analytics, cross-sections, spec/BOM, ampacity, PDF
reports, CAD profile export). The Addon Manager installs the Python dependencies
(matplotlib, scipy) from this addon's `requirements.txt` automatically.

Simulation backends on native Windows:

| Backend | Native Windows |
|---|---|
| **NEC2** | ✅ **one-click** — Solver Setup → **Install…**. Downloads nec2++ 2.3.4 (~1.5 MB, per-user, no admin rights), built from unmodified upstream source and published by the EMStudio project because no NEC engine has an official Windows build. Verified byte-identical to the Linux build on the shipped dipole deck. |
| **Elmer, Gmsh** | ✅ **one-click** — Solver Setup → **Install…** downloads the official upstream builds (~160 MB and ~37 MB, per-user, no admin). Manual installers at elmerfem.org / gmsh.info still work. |
| openEMS | ⚠️ prebuilt zips exist, but EMStudio's Python-driven pipeline isn't wired for them yet |
| FastHenry | ⚠️ download FastFieldSolvers' own Windows build from fastfieldsolvers.com and point EMStudio at it. There is no Install button and there cannot be one — FastHenry carries an M.I.T. licence granting internal, noncommercial use only and prohibiting redistribution without written consent, so EMStudio may not ship the binary for you. |
| Palace | ❌ no upstream Windows support — WSL2 only |

**The guided installs put binaries in `%LOCALAPPDATA%\EMStudio\solvers\` and
EMStudio finds them without touching `PATH`.** Deleting that folder just means
clicking Install again. If you see *"TLS verification failed (corporate proxy
interception?) — retrying through Windows curl/schannel"*, that is expected on a
managed corporate network and is handled automatically; verification is never
disabled.

**For openEMS and Palace, the route is still WSL2.** Install Ubuntu under WSL2,
install FreeCAD and EMStudio inside it, and every Linux recipe in this manual
applies unchanged — including all six solvers. Detect Solvers is platform-aware
and shows Windows-specific guidance when run on native Windows.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| EMStudio missing from workbench list | Symlink in the wrong Mod dir — FreeCAD ≥1.1 uses `~/.local/share/FreeCAD/v1-1/Mod/` |
| "solver not found" | Run **Detect Solvers** and follow its install hint |
| openEMS runs but no plots | Check Report view; the working dir path is printed there |
| NEC2: "not straight" error | NEC2 needs line segments; curved wires come in a later phase |
| Patch resonance shifted | Increase `MeshResolution`, widen `DomainPaddingWavelengths` |
| Microstrip \|S\| > 1 (non-physical) | The MSL port needs trace-aware meshing — set the openEMS solver's `MicrostripMeshMode = Auto` (default); ensure the ground is the PEC Zmin boundary and a substrate dielectric sits under the strip |

## 9. Validation

Every physics feature ships with an automated gate (`tests/validation/`):
half-wave dipole (feedpoint R and 2.13 dBi pattern vs literature), patch antenna
(resonance vs the published openEMS reference), STL import (identical resonance),
wire analytics (exact-solution self-checks), FastHenry cross-validation of the
litz model (0.0% at the litz design point), **induction heating** (billet eddy
power vs the exact Bessel solution: +0.03% at 1 kHz; solenoid B vs the
current-sheet formula: −0.04%), **WPT coupling** (L/M/k vs Grover/Maxwell
coil formulas: all within 0.5%), the **microstrip notch filter** (S21 notch
3.662 GHz vs the analytic open quarter-wave 3.683 GHz and the openEMS tutorial
3.671 GHz; passive to −0.03 dB), and the **Palace** eigenmodes — rectangular
(TE101 within 0.001%) and **cylindrical via BREP** (TM010 +0.25% vs Bessel) — plus
WR-90 wave-port S-parameters (|S21| 0.00 dB, phase 0.002°) and coaxial-line
lumped-port S-parameters (Z0 49.94 Ω, phase slope 0.043°). For **VLF/LF** the
electrically-small analytics self-check against the textbook closed forms, and the
**monopole over ground** validates NEC2 driven at 100 kHz — a short λ/10 mast over
perfect ground gives Re(Zin) 4.02 Ω vs the analytic radiation resistance 3.95 Ω, a
λ/4 monopole ≈ 36.5 + j21 Ω, and a finite (Sommerfeld) ground drops the radiation
efficiency to a few percent. Run them yourself:

```bash
freecadcmd tests/validation/dipole_nec2.py
freecadcmd tests/validation/monopole_nec2.py        # VLF/LF monopole over ground (NEC2 + GN card)
freecadcmd tests/validation/isolation_nec2.py       # co-site antenna isolation matrix (NEC2 Y-matrix)
freecadcmd tests/validation/patch_openems.py
freecadcmd tests/validation/patch_stl_openems.py
freecadcmd tests/validation/msl_notch_openems.py   # microstrip notch (~40 s)
freecadcmd tests/validation/cavity_palace.py        # Palace box eigenmodes
freecadcmd tests/validation/cylcavity_palace.py     # Palace cylindrical (BREP) eigenmodes
freecadcmd tests/validation/waveguide_palace.py     # Palace wave-port S-params
freecadcmd tests/validation/coax_palace.py          # Palace coax lumped-port S-params
freecadcmd tests/validation/fastsweep_palace.py     # Palace adaptive fast frequency sweep
freecadcmd tests/validation/amr_palace.py           # Palace adaptive mesh refinement (AMR)
freecadcmd tests/validation/circwaveguide_palace.py # Palace general-BREP driven wave ports
python3 tests/validation/mmwave_palace.py           # Palace full-wave at ~40 GHz and up
python3 tests/validation/freq_guard.py              # quasi-static frequency-validity guard
python3 tests/validation/small_antenna.py           # VLF/LF small-antenna analytics + band picker
python3 tests/validation/cosite.py                  # co-site interference (IMD/desense/D-U + optimizer)
python3 tests/validation/propagation.py             # point-to-point path loss (FSPL/knife-edge/plane-earth)
python3 tests/validation/coverage.py                # DEM import + terrain profiles + coverage heatmap + KML + LF/MF ground-wave (P.368) + multi-station D/U contours + multi-edge diffraction + Hata/COST-231
python3 tests/validation/lfmf.py                    # P.368-10 spherical-earth ground wave — 2497-point oracle grid + official NTIA examples
python3 tests/validation/p452.py                    # ITU-R P.452-18 — official CG-3M examples (needs ITU maps: itu_maps.install_p452_maps())
python3 tests/validation/p2001.py                   # ITU-R P.2001-6 — official examples (needs ITU maps: itu_maps.install_p2001_maps())
python3 tests/validation/cable.py                   # §2 Cable Designer — coax/pair/bundle + insulated-bundle MoM C (Paul + GETCAP anchors)
python3 tests/validation/wire_fasthenry.py
python3 tests/validation/wire_current_sharing.py
python3 tests/validation/induction_elmer.py   # or freecadcmd (adds the template path)
python3 tests/validation/wpt_elmer.py         # or freecadcmd (adds the template path)
```
