# EMStudio — Quick Help

Full manual with step-by-step tutorials: [docs/USER_MANUAL](docs/USER_MANUAL.md)

> 🎓 **For educational, hobbyist and experimental use — and under active
> development.** More to come; features, defaults and results may change
> between versions.

> ⚠️ **All results are engineering estimates — independently verify everything
> before any reliance.** No warranty and no liability; use at your own risk;
> you are solely responsible for verification, regulatory/RF-safety compliance,
> and anything built from these outputs. See [DISCLAIMER](DISCLAIMER.md) —
> or read it in the app under **EMStudio → Help → Legal notice & disclaimer**.

> **EMStudio Pro ($149, available now)** adds the System Designer — matching,
> filters/diplexers, phased arrays with tapers, and RF direction finding — plus
> the AI assistant. The assistant talks to *your* model server: its
> **Settings…** button carries presets for local Ollama / LM Studio /
> CentralBrain and hosted OpenAI / Anthropic (any OpenAI-compatible endpoint
> works), with Fetch-models and a Test probe so a wrong model name is caught
> before you ask a question. Buy at
> [ajj3us.gumroad.com](https://ajj3us.gumroad.com) and install it from
> **EMStudio → Help → EMStudio Pro — install / activate**.
> See [docs/PRO](docs/PRO.md).

## Toolbar commands

EMStudio's commands are presented in six grouped toolbars/menus — **Analysis**,
**Templates**, **Tools**, **System**, **Setup**, **Help**. **Tools** designs ONE
thing; **System** designs a system of them. Every command has its own icon.

### Analysis
| Command | What it does |
|---|---|
| **Antenna from Selection** | **Start here for an antenna.** Select the conductor you drew — a **solid** or a **curve** — and this builds the whole runnable NEC2 analysis: wire model, PEC material, centre feed, a sweep around the conductor's own half-wave resonance, and the solver. A solid has its equivalent radius measured from its cross-section; a curve has no thickness, so you are asked for it. It tells you what it assumed **and why** before creating anything |
| **New EM Analysis** | Container for one simulation (sweep, boundaries, mesh settings live on it) |
| **EM Material** | Assign PEC/dielectric to the selected geometry (works on solids, faces, wires, imported STL meshes) |
| **Lumped Port** | Feed point on the selected edge/face; set Direction + Impedance |
| **Coil Excitation** | Mark the selected solid as an N-turn current-driven winding (magnetics). **Set `Axis` to the real winding axis** (+X/+Y/+Z — the direction the current circulates *around*); a wrong axis silently corrupts the drive. 3-D runs report the stored energy, the coil **inductance**, and the ampere-turns actually delivered — a delivery far from 100 % means the current is not circulating as asked |
| **Add NEC2 / openEMS / Elmer / Palace Solver** | Attach a solver: NEC2 wire MoM · openEMS full-wave FDTD · Elmer FEM magnetics · Palace FEM full-wave |
| **Run Solver** | Solve + open results (S11 / VSWR / Impedance / Pattern tabs, Touchstone export; magnetics: powers, L/M/k, fields in 3-D) |
| **WPT: Sweep Coil Gap** | Parametric study: coupling k across a range of coil gaps, plotted k(gap) |

### Templates (ready-to-run)
| Command | What it does |
|---|---|
| **Template: Wire Dipole** | 300 MHz dipole (NEC2) |
| **Template: Monopole over Ground (VLF/LF)** | Short λ/10 base-fed monopole over ground at 100 kHz (NEC2 + GN card; perfect or finite earth) |
| **Template: Patch Antenna** | 2.4 GHz microstrip patch (openEMS reference design) |
| **Template: Co-site Antenna Pair** | Two λ/2 dipoles at 0.5λ (NEC2, two ports) — feed the Isolation Matrix |
| **Template: Resonant / Cylindrical Cavity** | Rectangular (~4.5 GHz) and cylindrical (BREP, TM010 ~3.8 GHz) eigenmodes (Palace) |
| **Template: WR-90 / Circular Waveguide** | Waveguide S-parameters (Palace wave ports; rectangular X-band + circular via BREP) |
| **Template: Coaxial Line** | ~50 Ω coax S-parameters (Palace radial lumped ports) |
| **Template: Microstrip Notch Filter** | Two-port S-params with a quarter-wave open stub (openEMS trace-aware meshing; notch ~3.7 GHz) |
| **Template: Induction Heating** | Coil + aluminum billet (Elmer, ~10 s) |
| **Template: WPT Coil Pair** | Coupled-coil pair: L1/L2/M + coupling k (Elmer) |
| **Template: 3-D Solenoid (Magnetostatic)** | GENERAL 3-D magnetostatics: any closed coil solid, B-field map (Elmer WhitneyAV, ~30 s; TEAM-7-validated chain) |

### Tools (calculators & designers)
| Command | What it does |
|---|---|
| **Cable Designer** | Litz \| Coax \| Single Wire \| Twisted Pair \| Bundle. Litz Types 1–9: cross-section, Rac/Rdc curves, spec/BOM, FreeCAD profile export. Coax: analytic TEM Z0/VF/C′/L′/TE11-cutoff/attenuation with RG-58/RG-142 datasheet presets + a Palace full-wave verify. Single wire: exact Kelvin skin effect, Rdc, ampacity, insulation. Twisted pair: differential/odd-mode Z0 + VF (UTP/STP) with Cat5e/Cat6 presets. Bundle: pack any member mix — exact tangency packing, OD/fill/jacket, member-to-member crosstalk (insulated members via a validated method-of-moments capacitance solve) and differential pair-to-pair coupling (k_diff, CUPP pF/100 m, Zdd, differential NE/FE with the RADC twist model — terminations in differential Ω). **Thermal tab**: steady conductor/surface temperature, ampacity per insulation class, transient heating and adiabatic short-circuit — with a temperature-colored cross-section, a 2-D film + rising-plume dissipation view, rise-vs-current and heating-curve plots; coax pages get the matched RF average-power rating P_max(f) |
| **Element Designer** | Design one radiating element from requirements: **20 verified service presets** (FM/AM broadcast, airband, marine, NOAA WX, eight ham bands, CB, 433 ISM, LoRa 868/915, Wi-Fi 2.4/5, GPS L1, ADS-B) that auto-fill the band/polarization/pattern schema, a rule-based family recommender with printed rationale (wire · **Yagi-Uda** · **microstrip patch** · **LPDA** · small antenna — all five core families), wire synthesis (dipole / monopole / folded / λ-fraction verticals), **NBS TN-688 Yagi synthesis** (gain or boom length → reflector/driven/N-director dimensions), **transmission-line patch synthesis** (f0 + substrate εr/h → W, L, feed offset — laminate presets), and **Carrel LPDA synthesis** (Frequency = f_lo + Band top = f_hi, gain target on the corrected Butson-Thompson contours or explicit τ/σ → elements, boom, crossed-feeder Z0 for a target R0; the feeder is real NEC2 TL cards), editable dimensions, predicted feed Z + gain (dBi **and** dBd), an off-thread **Verify** (NEC2 for wire/Yagi/LPDA — band VSWR stats + mid-band pattern for the LPDA — openEMS FDTD for the patch) predicted-vs-achieved read-out, **Accept & Generate** → a runnable analysis, **PDF Report…** → a build-house deliverable (design summary + dimensioned sketch + element schedule, disclaimer on every page), and **Show pattern in 3-D view** → the verified far field as a gain balloon in FreeCAD's own 3-D viewport beside your geometry (spacebar toggles it, one camera drives both; greyed out until a Verify has actually produced a pattern). Reports the element only — matching/combining is the §7 System Designer. *Everything shipped here is part of the free core and stays free. EMStudio Pro ($149) does not change this dialog — it adds the §7 System Designer and the AI assistant. A solver-in-the-loop optimizer, exotic families and AI-guided intent are roadmap ideas, promised to nobody and NOT part of Pro today* |
| **System Matching Designer** | Take an element's feed impedance and design the matching network to a target system Z0 (§7 System Designer). **Element (load) source**: typed R + jX, **or** a live NEC2 sweep of a wire antenna already in the document (uses its swept Z(f)). **Topology picker**: L-match (lowpass / highpass), **pi**, **T**, **quarter-wave transformer**, **binomial (maximally-flat) multisection**, **single-stub** (open/short), **hairpin** — plus a **Recommend** button that ranks the applicable topologies with a printed rationale. Predicted **VSWR / return-loss / insertion-loss** curves vs frequency and a component/section schedule; an optional **E-series** (E6/E12/E24/E96) standard-value snap on lumped parts that shows the real-world post-rounding match. Off-thread **Verify** re-sweeps the element live (NEC2) and plots the ACHIEVED match against its real Z(f). **PDF Report…** → a two-page matching-network deliverable (summary + predicted curves + schematic + component/section schedule, disclaimer on every page). Honest behaviour: the real-load-only topologies (pi / T / quarter-wave / binomial / hairpin) refuse a reactive element — pre-resonate it first — while the L-match and single-stub absorb reactance directly. ***EMStudio Pro** — §7 is the paid tier; the free workbench does not include this dialog* |
| **Array Designer** | Design a linear phased array driven the honest way (§7 System Designer, S4). Pick **N parallel dipoles**, spacing and a **named drive distribution** — broadside · end-fire (either direction) · **Hansen-Woodyard** enhanced end-fire · scanned (progressive phase) · **cardioid pair** — and the dialog derives the per-element **target CURRENTS** (the §7 design rule: currents steer; voltages are just what NEC2 takes), with predicted **exact directivity, half-power beamwidth, first-sidelobe** and a **grating-lobe guard** from the gated analytic engine. **Verify (live NEC2)** builds a transient N-dipole model, extracts the **mutual-impedance matrix** (N solves), solves **V = Z·I** for the port voltages, runs ONE multi-excitation deck, and overlays the ACHIEVED azimuth cut on the predicted one — plus the **drive table**: EX voltages, per-element **active impedance** and power, achieved-vs-target current error, and warnings when a drive is not passively realizable (negative driving-point resistance) or an element absorbs power. **Amplitude tapers** (S5): binomial · exact Dolph-Chebyshev (sidelobe-level spin; d_max guard) · Taylor n̄ (SLL + n̄ spins; realized level is NEAR design by construction) multiply onto the distribution, with taper-efficiency and dynamic-range read-outs; **Export pattern CSV** hands the achieved far field to the §6 coverage tools as an antenna pattern. TL/corporate feeds are a different feed model and are refused here. **Show pattern in 3-D view** loads the ACHIEVED far field into FreeCAD's own 3-D viewport as a gain balloon (spacebar to toggle, native rotate/pan/zoom); it stays greyed out until Verify has produced a real pattern, and is centred on the document origin because the verified array lives in a scratch document. ***EMStudio Pro** — §7 is the paid tier; the free workbench does not include this dialog* |
| **RF Direction Finding** | Watson-Watt/Adcock aperture + octantal error, multi-baseline interferometer ambiguity/accuracy/CRLB, pseudo-Doppler ring sizing, and the correlative manifold built live from NEC2 element patterns. ***EMStudio Pro** — §7 is the paid tier; the free workbench does not include this dialog* |
| **Small-Antenna Designer (VLF/LF)** | Electrically-small analytics: Rr, effective height, efficiency, Chu Q/bandwidth, loading + a band→method picker. The **Top loading & ground** tab designs the classic VLF vertical: hat capacitance (flat-top n-wires / T / inverted-L / plate — measured-model-verified constants), trapezoid effective height, a radial-ground-screen loss estimator (N radials, screen radius, four earth presets) with the honest grid-vs-earth crossover, the η efficiency ladder, and voltage-limited radiated power / bandwidth at your insulation limit |
| **Antenna Isolation Matrix** | NEC2 Y-matrix isolation/coupling between 2+ wire antennas (the co-site coupling input) |
| **Co-site Interference Calculator** | IMD products, receiver desensitization, broadband noise, frequency-plan clashes + a frequency-plan optimizer |
| **Point-to-Point Link Budget** | Path loss (free-space + two-ray plane-earth), received power, fade margin, field strength |
| **Area Coverage Map** | Received-power / field-strength footprint over a lat/lon grid with optional DEM terrain shadowing (single- or multi-edge Deygout / Epstein–Peterson diffraction), antenna-pattern modulation, LF/MF ground-wave (P.368 flat earth or the P.368-10 spherical-earth LFMF port, 0.01–30 MHz to 10000 km), Okumura-Hata / COST-231 clutter environments, and KML export |
| **Multi-Station Service / Interference** | Compose ≥2 transmitters onto one grid; per-cell wanted/unwanted D/U vs an FCC/ITU protection ratio → served / interference-limited / no-service, best-server view, and KML |

### System
| Command | What it does |
|---|---|
| **Antenna Isolation Matrix** | NEC2 multi-port |S21| between every antenna pair — the coupling number every other system tool needs |
| **Co-site Interference** | Intermodulation products, receiver desensitization, broadband noise, and a frequency-plan optimizer |

*EMStudio Pro adds impedance matching, phased arrays and RF direction finding
to this same group — see [docs/PRO](docs/PRO.md).*

### Setup
| Command | What it does |
|---|---|
| **Detect / Install Solvers** | Setup wizard: backend status, one-line install command (apt on Linux, brew on macOS), guided no-sudo source builds with live output — and on Windows, one-click Install buttons that download prebuilt binaries (NEC2, Elmer, gmsh; per-user, no admin rights) |

### Help
| Command | What it does |
|---|---|
| **About EMStudio** | Version, development status, what the workbench is, how results are validated, the solver backends and their licences, credits, and the brand notice |
| **Legal notice & disclaimer** | Intended use (educational / hobbyist / experimental), no warranty and no liability, your duty to verify every result, the no-safety-critical exclusion, and the EMStudio / AJJ³ brand terms. Opens the Disclaimer / Trademark notice / Licence |

Both are always available — no document and no solver needed. A summary of the
same terms is shown once per installed version when you first activate the
workbench.

## Typical workflow

Geometry → select metal → **EM Material** (PEC) → select dielectric → **EM Material**
(εr) → line across the feed gap → **Lumped Port** → sweep on the Analysis →
**Add … Solver** → **Run Solver**.

## Solver quick notes

- **NEC2**: straight wire edges only; feed = the port's edge; second pass computes the
  radiation pattern automatically.
- **openEMS**: automatic domain + mesh (thirds-rule metal edges, substrate
  discretization); runs in a separate process — cancel anytime; artifacts stay in the
  working dir printed in the Report view.
- **FastHenry**: used by the wire toolkit for bundle impedance cross-checks.
- **Elmer (magnetics)** results include a **Save PDF Report** button (cross-section, |B| field map, powers/L/M/k + BOM).
- **Elmer (magnetics)**: axisymmetric — coaxial cylinders/tubes/rings centered on the
  Z axis; coil currents are PEAK amplitudes, powers time-averaged watts; needs `gmsh`
  + the CSC `elmerfem-csc` package (Detect Solvers shows the install line).

## Cable Designer in 30 seconds

Pick the top-level **Construction** first — **Litz / stranded**, **Coax**, or
**Single wire**:

- **Coax**: pick an RG-58/RG-142 preset (primary-datasheet geometry; stranded
  centres use the effective electrical diameter) or enter 2a/2b + dielectric →
  **Update** → Z0, VF, C′/L′, TE11 cutoff, conductor+dielectric attenuation
  curves and a spec table. **Run full-wave verify** re-solves the same line with
  the Palace lumped-port backend (matched |S11| + full-wave VF vs 1/√εr).
  Attenuation is the smooth-solid-conductor model — real braided cables run
  ~10–45 % higher (stated on the plot and in the spec).
- **Single wire**: conductor size (AWG/mm/mil) + insulation → exact Kelvin
  Rac/Rdc, Rdc, ampacity estimate, spec + PDF.
- **Twisted pair**: bare conductor Ø + insulated OD (= wire spacing) + twist
  lay → differential/odd-mode Z0, VF, C′/L′ and attenuation. Pick a
  **Cat5e/Cat6 preset** (primary-datasheet geometry; εeff honestly from the
  datasheet NVP) or uncheck NVP for the Lefferson twist/insulation model
  (hard-film vs soft insulation classes; the pitch angle is computed for you —
  optimum 20–45°). Check **Shielded (STP)** and give the shield Ø for the
  shielded form (best for d/s ≤ 0.4 — the dialog flags the limit).
- **Bundle**: a member table (label, envelope OD, qty, kind, conductor Ø)
  packs any mix — coax + twisted pairs + wires — largest-first at exact
  tangency positions around the bundle axis (7 equal members give the classic
  OD = 3× hex, fill 7/9). **Add last construction** grabs the envelope of
  whatever you just computed on another page. Reports core/finished OD, fill
  factor and a spec. **Estimate crosstalk**: pick generator/receptor/reference
  members + terminations → near/far-end weak-coupling curves with the
  common-impedance floor and inductive/capacitive dominance (analytic L/C
  when separations/conductor-radius ≥ 4, or the FastHenry option at any
  spacing). Bare/single-ended conductors in this slice — shielded coax and
  differential pairs are excluded by design.
- **Litz / stranded** (below):

Type (1–9, New England Wire taxonomy) → strand size (AWG/mm/mil) → operations table:
one row per bunching/cabling operation, innermost first — members, lay length, S/Z
direction, **fiber core Ø** (`auto` = snug ring; Type 6 = cores at the last TWO
levels), and **member wrap** (tape/serve + thickness) — plus the **overall jacket**
(Type-6 default: PVC 1/8″ wall). `auto` everywhere follows industry practice.
**Update** → tabs: Cross-Section (strands, cores, tape rings, jacket — visual
check), AC Resistance (isolated + in-winding curves, W/m at your current),
Spec/BOM (build-house cabling schedule with conductor + finished ODs). Export:
Markdown spec; FreeCAD profile compound for Part Sweep/Loft along a helix.
Per-strand current sharing (twist quality): the **Current Sharing…** button
(runs FastHenry — minutes) or the `emstudio.wire.current_sharing` API +
`tests/validation/wire_current_sharing.py`.

## Where results live

Every run's working directory (deck, raw solver output, `port_1.csv`,
`port_1.s1p`, `farfield_port_1.csv`) is printed in the Report view.

## Troubleshooting

- Workbench missing → check the Mod symlink; FreeCAD ≥ 1.1 reads
  `~/.local/share/FreeCAD/v1-1/Mod/`.
- Solver missing → **Detect Solvers** prints exact install commands.
- Wrong resonance → raise `MeshResolution` / `DomainPaddingWavelengths` on the
  Analysis object.
