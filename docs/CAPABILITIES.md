# EMStudio Capability Matrix

Honest status of every analysis type. "Validated" means an automated gate checks it
against analytic or published references, and **every row names its gate** — so a row
is current exactly as long as the gate it names still passes. Nothing here is claimed
working without a gate behind it.

> ⚠ **No version is pinned here on purpose.** This header read *"as of v0.31.0
> (2026-07-08)"* until 2026-08-20 — roughly forty releases stale, on a public
> document whose entire job is to be trustworthy about status. A version in prose
> is a claim nothing measures; the gate names in each row are checkable, so they
> carry the currency instead. For what shipped when, see [CHANGELOG](../CHANGELOG.md).

## Frequency range & validity (DC → mmWave)

**Short version:** EMStudio's **full-wave** engines reach mmWave, but **which
engine and what kind of structure** both matter, so the honest form is per-engine
rather than one span:

* **Palace (FEM)** — **validated sub-0.01 % at 39 GHz and 57 GHz**, on **closed**
  structures: waveguide and cavity. This is what meets the "DC to 40 GHz and
  beyond" target.
* **openEMS (FDTD)** — the highest gated **radiating** structure is the
  **30 GHz** standard-gain horn (v1.5.0: 19.29 dBi vs the vendor's published
  19.70, −0.41 dB inside the citable ±0.5 dB, with a second λ/40 solve gating
  the mesh spread to 0.5 dB); below it the **3.5 GHz** 5G NR n78 patch
  (v1.10.0: FDTD 3.3950 GHz inside the synthesiser's own ±5 % window and inside
  n78) and the **2.435 GHz** patch; highest gated guided point is the
  **3.68 GHz** microstrip notch filter.
  ⭐ **1.892 GHz — a PIFA against a published anechoic-chamber MEASUREMENT,
  reproduced to +0.22 % (v1.10.0).** This is the project's only radiating
  anchor checked against real measured hardware rather than against a
  computation, and it is the strongest radiating claim available here.
  ⛳ Also **2.45 GHz — a printed inverted-F rebuilt from openEMS's own published
  example** (v1.10.0); external geometry, but that example publishes no
  numbers, so the window comes from a quarter-wave rule.
  ⚠ The radiating rungs are **not equally strong, and the difference matters
  more than the frequency does**. Ranked honestly: 1.892 GHz is against a
  MEASUREMENT; 2.435 GHz reproduces openEMS's own published tutorial geometry
  and 30 GHz compares against a vendor's published *analytic* curve — external,
  but computed; 2.45 GHz (the inverted-F) is an external geometry with no
  published numbers; and **3.5 GHz is weakest of all** — it checks the
  full-wave solver against our own analytic synthesis, a consistency check
  between two of our own models, not a validation against measurement. Quote
  each as what it is.
* **NEC2 (MoM)** — wire antennas, gated at 296 MHz.
* **Palace far field (v1.10.0)** — Palace's `r*E` output now becomes a
  `FarFieldResult` like any other backend's pattern. Checked against the closed
  form for a half-wave dipole: broadside **+2.222 dBi against 2.151 analytic**,
  a 36 dB axial null. ⚠ It is **DIRECTIVITY**, not gain — computable from the
  pattern alone, equal to gain only for a lossless radiator. The chain is gated
  end to end on geometry this project builds itself — `write_geo_dipole_open`
  feeds `palace_dipole_farfield`, broadside **+1.821 dBi against 2.151
  analytic** with a 19.4 dB axial null. ⚠ There is still **no menu entry** that
  builds a radiating Palace domain: it is reachable from the API and from the
  gate, not from Templates.

⚠ The old ceiling here read *"no radiating structure is gated above
2.435 GHz"* — TRUE until v1.5.0, removed by `horn_openems`. What is still NOT
earned: the horn's anchor is the vendor's **analytic** (NRL/Slayton) gain
curve, not a measurement, and the broad mmWave **antenna** claim (28 GHz
patches, handset PIFAs, arrays on substrate) rests on one gated Ka-band horn.
*"One gated point"* is not *"a validated band"*, and this project claims only
the first. The **quasi-static** engines (Elmer magnetics, FastHenry R/L) are
**inherently low-frequency by design** and must not be pushed past their
quasi-static validity — that is the one hard limitation to know.

| Engine | Method | Validated / usable range | Upper-limit cause | Lower-limit cause |
|---|---|---|---|---|
| **Palace** | full-wave FEM | **validated to 57 GHz** (cavity TE101 +0.002 % @ 56.9 GHz, +0.003 % @ 39.0 GHz; WR-22 driven 38–42 GHz, |S11| −106 dB) | mesh element size ∝ λ → memory/time (no physics break) | driven/eigenmode are f > 0; true DC statics is a different formulation |
| **openEMS** | EC-FDTD | broadband in one run; **validated radiating points 1.892 GHz (PIFA, v1.10.0, +0.22 % vs a published anechoic-chamber MEASUREMENT — the only measured anchor here), 2.435 GHz (patch), 2.45 GHz (printed inverted-F, v1.10.0, rebuilt from openEMS's own published example), 3.5 GHz (5G NR n78 patch, v1.10.0 — ⚠ consistency against our own synthesis, NOT an external anchor) and 30 GHz (standard-gain horn, v1.5.0, −0.41 dB vs the vendor curve + λ/40 mesh-spread gate)** — ⚠ between and above those points is *feasible*, not *validated*; Palace remains the validated route for closed structures above 6 GHz | grid cell < ~λ/20 → memory/time | very low f needs long settling (~MHz practical floor) |
| **NEC2** | MoM (wire) | validated **100 kHz VLF/LF (monopole over ground)** → 296 MHz (dipole); HF→low-microwave in practice | segments must be < ~λ/10 **and** obey radius/length ratios → sub-mm wires above ~a few GHz are impractical (not a solver break) | none (thin-wire quasi-static kernel valid to low f; ground image via GN card) |
| **Elmer** | magneto-quasi-static | **DC → ~few MHz** (validated: induction 0.03 %, WPT k <0.5 % @ 100 kHz) | **hard**: eddy-current/A-V formulation assumes the object is electrically small and displacement current is negligible — **not full-wave; do not use for radiating/electrically-large problems** | true DC magnetostatics is a sub-case |
| **FastHenry** | PEEC (quasi-static R/L) | DC → ~low-GHz for per-unit-length R(f)/L(f) of electrically-small conductors | quasi-static: no radiation/full-wave; valid while the structure ≪ λ | DC (Rdc) is the f→0 limit |

**Rule of thumb.** Pick a **full-wave** analysis (antenna, S-parameter, cavity) for
anything where the object is an appreciable fraction of a wavelength or radiates —
those cover DC-ish to mmWave. Reserve **Elmer/FastHenry** for **magnetics, eddy
heating, wireless-power, and low-frequency conductor impedance**, where the
quasi-static assumption holds (roughly DC to a few MHz for magnetics). EMStudio
**auto-warns** when a quasi-static analysis (Elmer magnetics) is set up outside the
electrically-small regime — if the largest dimension reaches λ/10 at the operating
frequency, a banner + report-view warning explains that the result may be
non-physical and points to the full-wave path (never blocks the run; see
`emstudio/solvers/validity.py`, gate `tests/validation/freq_guard.py`).

**VLF/LF/MF small-antenna analytics — ✅ validated (v0.22.0):** closed-form short
dipole/monopole/loop Rr, effective height, efficiency, Chu min-Q/bandwidth, and loading
(`emstudio/antenna/small_antenna.py`, gate `tests/validation/small_antenna.py`) — the
electrically-small regime where the full-wave field solvers don't apply. Exposed in a
**Small-Antenna Designer dialog** (v0.23.0, `emstudio/ui/small_antenna_dialog.py`):
type/frequency (VLF/LF/MF band presets)/geometry inputs, a predicted-performance
read-out, a dimension-annotated 2-D sketch, and the Chu Q-limit plot.

**Wire-element synthesis (Element Designer E1) — ✅ validated (v0.57.0):**
dipole/monopole/folded-dipole design + λ-fraction verticals from first principles
(`emstudio/antenna/wire_elements.py`, gate `tests/validation/element_designer.py`):
the shipped-template inversion is bit-exact; the K end-effect curve is MEASURED on
this repo's own NEC2 (published charts disagree ±0.01); live folded-dipole
verification 282.7 Ω at the fold's resonance (Balanis 4× window). Famous constants
(468/f etc.) exposed as derived conventions with their embedded-K residuals pinned.

**Element Designer dialog + family recommender (E2) — ✅ validated (v0.58.0):**
the designer shell (`emstudio/ui/element_dialog.py`, command
`EMStudio_ElementDesigner`) — family selector (Wire · Small antenna; Yagi/patch/
LPDA pages arrive with E3-E5) over Schematic / Predicted / Verify tabs; editable
synthesized lengths with the Length → f₀ inverse; off-thread NEC2 verify
(predicted-vs-achieved, R-window resonance selection); Accept & Generate through
the templates (new optional dimension overrides, defaults byte-identical). The
deterministic requirements→family recommender (`emstudio/antenna/element_picker.py`)
carries a printable rationale per rule, the NBS TN-688 boom-class hint for gain
targets, honest ships-in-E4/E5 flags for unbuilt families, and the Chu
bandwidth guardrail. Gates: picker scenario tier + template-override tier in
`element_designer.py`; gui_smoke 40 checks / 50 commands. (Check counts throughout this file are STATIC `check(` call sites in the named gate file — the derivable basis — gated by `capability_counts`.)

**Yagi-Uda synthesis (Element Designer E3) — ✅ validated (v0.59.0):**
`emstudio/antenna/yagi.py` + `templates/yagi.py` + the Yagi dialog family — NBS
Technical Note 688 (Viezbicke 1976, public domain) Table 1 encoded verbatim (six
boom classes) with the Fig 9 diameter-compensation + Fig 10 boom-correction
models (de-risked from the scan page images —
`docs/upstream/tn688-yagi-anchors.md`). State a gain (or boom length) → a fully
dimensioned reflector/driven/N-director Yagi with feed Z and gain dBd+dBi;
Verify with NEC2 (far-field pinned at the design frequency). Gates: the digit
tier reproduces Table 1 + both worked examples (0.8 λ <0.0015 λ, 4.2 λ <0.005 λ);
the live `yagi_nec2.py` reproduces the measured 7.1/9.2/10.2/12.25 dBd across
four boom classes to **±0.25 dB** (0.8 λ anchor 9.09 dBd, F/B 12.7 dB).

**Microstrip patch (Element Designer E4) — ✅ validated (v0.60.0):**
`emstudio/antenna/patch_tl.py` + `templates.makePatchDesign` + the patch dialog
family — the standard transmission-line design (W, Hammerstad εr_eff, ΔL
fringing, L, two-slot edge R, cos² probe feed) from a frequency + substrate
(εr, h; laminate presets). Verified against the published 10 GHz example
(W 11.85 / εr_eff 1.9715 / ΔL 0.811 / L 9.053 mm vs 11.86/1.972/0.81/9.06) and
open academic sources (`docs/upstream/patch-tl-anchors.md`). Verify with openEMS
FDTD: the 2.4 GHz synthesis resonated at **2.333 GHz (−2.8 %, inside the model's
±5 %)**, gain **6.88 dBi** — the analytic estimate landed within 0.6 dB. Gates:
the digit tier + the live `patch_auto_openems.py` FDTD gate.

**LPDA — Carrel log-periodic (Element Designer E5) — ✅ validated (v0.61.0 —
ALL FIVE core §1 families shipped):** `emstudio/antenna/lpda.py` +
`templates.makeLPDA` + the LPDA dialog family — the Carrel (1961) equation
set (σ_opt line, cot α, B_ar, B_s, N with the documented ARRL rounding rule,
l₁ = λ_max/2 τ-scaled elements, boom, and the Za/σ′/Z0 feeder design for a
target mean R0), with gain on the **Butson-Thompson corrected contour
calibration** (+ the −0.2 dB/doubling h/a thickness sensitivity). The crossed
boom feeder is modeled with the new **`EMStudio::TransmissionLine`** object →
NEC2 **TL cards** (negative-Z0 crossed convention, primary-source-confirmed;
no-TL analyses byte-identical). Both official worked-example digit chains for
the classic 54-216 MHz design are gated (incl. Za 327.88 Ω / exact Z0
55.96 Ω); the live `lpda_nec2.py` gate runs the production writer across the
band — median VSWR(65) 1.215, mean R 60.7 Ω vs the 65 Ω target, fwd gain
8.29/8.84/8.54 dBi at 60/120/200 MHz with F/B ~20 dB, and the uncrossed
control collapsing to 5.7 dB F/B (the sign-convention regression guard).
Full provenance + live weak-spot/stub experiments:
`docs/upstream/lpda-carrel-anchors.md`.

**Service presets + PDF build reports (Element Designer E6) — ✅ validated
(v0.62.0 — the §1 epic is COMPLETE, E1-E6):** 20 service presets
(`emstudio/antenna/service_presets.py` — broadcast/aviation/marine/eight ham
bands/CB/ISM/LoRa/Wi-Fi/GPS/ADS-B) auto-fill the requirements schema; every
band edge verified from FCC/ITU/ETSI/ARRL sources with an adversarial
full-table audit (`docs/upstream/service-presets-anchors.md`). The **PDF
Report** button renders a two-page build-house deliverable (summary +
dimensioned sketch + element schedule, disclaimer on every page) for all
four design families via `element_report`. Gates: the preset tier (~70
checks) + element-report renders in `report_pdf.py` + the gui_smoke preset/
report paths.

**§4 Watt breadth — top-loading / radial grounds / voltage-limited design —
✅ validated (v0.63.0):** `emstudio/antenna/topload.py` (plate+fringe hats —
reproduces the five consistent published scale-model measurements within
0.5 %; horizontal/vertical/flat-top/inverted-L/T/curtain capacitance with
the classic end-effect and proximity tables; umbrella landmarks; Laport
trapezoid h_e), `ground_system.py` (H-field zone-integral radial-ground
estimator with the grid-vs-earth crossover — monotone, exact ln10/2π-class
constants — and a wire-economy radial-count optimizer), and the
`small_antenna` voltage-limited set (P_r = 640π⁴/c₀²·V²C²h_e²f⁴, 3-dB
bandwidth, P·b product, shunt-ΔC effects, the η_a/η_as/η_ts efficiency
ladder gated against anonymized measured R_r pairs, experimental-h_e
utility). Exposed in the Small-Antenna Designer's **Top loading & ground**
tab. Every constant verified from the reference page images with
exact-identity cross-checks (`docs/upstream/watt-topload-anchors.md`); the
whole 728-page reference scanned + triaged for follow-ups
(`docs/upstream/watt-scan-map.md`).

**Band → recommended-method picker — ✅ validated (v0.23.0):** the honest
multi-method router (`emstudio/antenna/band_picker.py`) — no single engine spans
VLF→mmWave, so it maps a frequency (and optional size) to the method that is actually
valid there (VLF/LF/MF → analytic + NEC2-with-ground; HF→µW → NEC2/openEMS/Palace;
µW→mmWave → Palace/openEMS), each with its validity caveat. Shown as a banner in the
dialog; gated in `tests/validation/small_antenna.py`.

**NEC2 monopole over ground — ✅ validated (v0.24.0):** NEC2 driven at **VLF/LF**
with a ground model (`SolverNEC2.GroundType` = perfect PEC image / finite
Sommerfeld earth; base-fed monopole; `emstudio/templates/monopole.py`, gate
`tests/validation/monopole_nec2.py`). Short λ/10 monopole over perfect ground
Re(Zin) 4.02 Ω vs analytic Rr 3.95 Ω; λ/4 → 39.5+j22.6 Ω (textbook 36.5+j21);
finite average ground → radiation efficiency ≈ 5 % (the VLF ground-loss reality).
This completes the core of §4 (analytic + dialog + picker + NEC2-with-ground).

**Co-site interference calculator — ✅ validated (v0.25.0):** the deterministic
system-level EMC engine (`emstudio/cosite/interference.py`, dialog
`emstudio/ui/cosite_dialog.py`, gate `tests/validation/cosite.py`) — intermodulation
products + intercept-point levels, receiver desensitization, broadband-noise
coupling and frequency-plan/D-U clashes over a list of co-located radios, fed by the
antenna-to-antenna **isolation matrix** (v0.26.0, `emstudio/cosite/isolation.py`,
gate `tests/validation/isolation_nec2.py`) extracted from NEC2 (Y-matrix,
drive-one-of-N; two λ/2 dipoles at 0.5λ → |S21| −13.78 dB vs Balanis, reciprocity
1e-14) and a **frequency-plan optimizer** (v0.27.0) that retunes transmitters to
clear IMD/desense/co-channel collisions. **§5 co-site is complete (phases A+B+C).**
**Geographic coverage/propagation (§6) SHIPPED** — ITU-R P.1546, P.1812, P.452,
P.2001, LF/MF ground wave, terrain profiles and multi-station D/U, all gated
against **ITU's own official reference datasets**: 52 datasets for P.1546 and 63
for P.1812, worst deviation **0.000000 dB**. Gates: `p1546.py`, `p1812.py`,
`p452.py`, `p2001.py`, `lfmf.py`, `coverage.py`.

> ⚠ **This paragraph said §6 "remains a design spec" until 2026-08-20**, long
> after it shipped — the second understatement found in this file the same day,
> and it also linked to `ROADMAP.md`, which is **not exported**, so the link was
> dead for every public reader. ⛳ Two failure modes in one sentence: a status
> claim nothing re-checked, and a link to a file the audience cannot see.

**§7 System Designer — network core + matching synthesis (S1) — ✅ validated
(v0.64.0):** the linear two-port network core (`emstudio/system/network.py`) —
the cascadable ABCD primitive with S / Z / Y conversions (real-Z0
traveling-wave S), lossless and lossy transmission-line sections, finite-Q
lumped elements, input impedance, VSWR / return loss / mismatch loss, and both
transducer and dissipation insertion loss (every identity holds to machine
precision: det = 1, S↔ABCD round-trip, lossless ⇒ unitary S, cascade
associativity) — plus the impedance-matching synthesis engine
(`emstudio/system/matching.py`): L-match (lowpass & highpass, exact for complex
loads via a direct conjugate-match solve), pi- and T-match (chosen loaded Q),
quarter-wave and binomial (maximally-flat) multisection transformers,
single-stub (open/short) tuner, hairpin (exact L-match), gamma match (flagged
EMPIRICAL starting point), a rule-based balun type picker, a deterministic
topology recommender, E-series (E6/E12/E24/E96) standard-value snapping, and a
topology-correct finite-Q insertion-loss estimator. Engine only — Qt-free, no
UI (the dialog is S2). Gate `tests/validation/system_matching.py` (76 checks,
pure python3) reproduces the re-verified Phase-A anchors to the digit
(`docs/upstream/system-designer-anchors.md`) and cross-checks that the network
dissipation equals the closed-form insertion loss.

**§7 System Matching Designer dialog (S2) — ✅ validated (v0.65.0):** the
**System Matching Designer** (`emstudio/ui/matching_dialog.py`, command
`EMStudio_SystemMatching`) puts a GUI on the S1 engine — the §1 Element Designer
reports an element's feed Z and stops; this takes that Z and designs the
matching network. Element (load) source is typed R + jX OR a live NEC2 sweep of
a wire antenna already in the document (uses its swept Z(f)); target system
impedance Z0 (default 50 Ω); a topology picker (L-match lowpass/highpass · pi ·
T · quarter-wave · binomial · single-stub · hairpin) with a **Recommend** button
that ranks the applicable topologies with a printed rationale; predicted VSWR /
return-loss / insertion-loss curves and a component/section schedule; an
optional E-series standard-value snap on lumped components (showing the
real-world post-rounding match); a **Verify** that re-sweeps the element live
(NEC2, off-thread) and plots the ACHIEVED match against its real Z(f); and a
two-page **PDF Report**. Honest behaviour: the real-load-only topologies (pi / T
/ quarter-wave / binomial / hairpin) REFUSE a reactive element (it must be
pre-resonated first); the L-match and single-stub absorb reactance directly.
Gates: a `_system_matching_dialog` gui_smoke check (offscreen, both FreeCADs) +
a live `tests/validation/system_match_nec2.py` (ingest the shipped 300 MHz
dipole ~71.9 Ω, match to 50 Ω → achieved VSWR ~1.01 vs the bare antenna's 1.43).
**§7 filter + diplexer synthesis (S3) — ✅ validated (v0.66.0):** the
filter/diplexer engine (`emstudio/system/filters.py`) on the same S1 network
core — Butterworth and Chebyshev lowpass prototype g-coefficients in closed
form (including the even-order `coth²(β/4)` termination that makes equal
source/load resistances unrealizable, and the load mapping that goes with it),
attenuation and minimum-order curves for both, the lowpass→bandpass and
lowpass→bandstop transforms on the geometric-mean band centre (so every
transformed arm resonates exactly at the centre), lowpass/highpass ladders, a
frequency response through the verified ABCD path, the **contiguous
constant-resistance diplexer** (a singly-terminated Butterworth exact-dual pair
whose composite common-port impedance is R0 at *every* frequency — machine
precision, |Zin − 50| < 1e-6 Ω at every order n = 1..7), the **non-contiguous
UVSJ band-splitting diplexer**, and a **3-port nodal S-parameter solve** giving
the assembled common-port match, both through paths and port-to-port isolation
(power-conserving to 3e-16 on a lossless 3-port). Honest behaviour: the
non-contiguous branches are synthesized from the **singly-terminated**
prototype, which assembles to 0.112 dB through loss at VSWR 1.38 with 34.8 dB
isolation for the 144/439 MHz case — the regime of measured UVSJ hardware;
the doubly-terminated construction is retained under `prototype="doubly"` but
assembles to 1.67 dB at VSWR 3.6, and a **branch evaluated alone is never the
diplexer's loss**. Contiguous isolation collapses to ~6 dB at the crossover, so
it splits spectrum rather than combining transmitters. Elements are ideal
unless you give them a Q (see below). **Reachable from the GUI since
2026-08-20** — **System ▸ Filter & Diplexer Designer** (Pro) drives both pages
and reports the component schedule in real part values; the free build shows a
teaser in its place.
⭐ **Finite-Q loss (v1.10.0)**: the ladder's elements are no longer forced
ideal. Give the designer a component Q and it builds the same filter from
physical parts carrying series `R = |X|/Q_u`, and reports the DISSIPATED loss
separately from the reflective part. Anchored to the standard midband estimate
`IL ≈ 4.343·Σg/(Q_res·FBW)` — agreement 0.7 % at Q 100 improving to 0.02 % at
Q 5000, which is the convergence signature of a first-order formula.
⚠ `Q_res` is the RESONATOR Q, not the component Q: every band-pass arm holds
both an L and a C, so equal component Qs halve it and double the loss.
⚠ Finite Q also abolishes infinite rejection — a real notch has a depth.
⛳ Opt-in: with no Q given the response is byte-identical to the lossless
ladder it always was.
Gates: `tests/validation/system_filters.py` (43 checks, pure python3,
mutation-tested 8/8) reproduces the Phase-B anchors to the digit, and a
`_filter_designer_dialog` gui_smoke check drives the dialog itself.

> ⚠ **This row read "Engine only — Qt-free, no UI" for four months.** The
> engine and its gate shipped in v0.66.0 and nothing reached them — a fully
> validated capability that no user could run, recorded accurately here and in
> `ROADMAP` §7.2 and then never acted on. ⛳ **An "engine only" note is a
> FINDING, not a status.** The gui_smoke check above exists so this particular
> gap cannot reopen silently.

**§7 array drive chain + Array Designer (S4) — ✅ validated (v0.67.0):**
NEC2 **multi-excitation** (one EX card per excited port; `Amplitude`/`PhaseDeg`
on every port; single-port decks byte-identical to the historic writer) and
the **phased-array drive chain** (`emstudio/system/array_system.py`) enforcing
the §7 design rule end-to-end: element CURRENTS in → mutual-impedance matrix
(the shipped §5 isolation machinery, wire-direction sign-normalized) →
V = Z·I → ONE multi-EX verify run. Live-validated on the shipped pair
geometry: achieved currents at the 1e-4 print-precision ceiling, NEC pattern
vs the analytic array factor to 0.03 dB, the λ/2 broadside axis null at
−82 dBi raw (88 dB contrast), and the headline **cardioid F/B 29.6 dB via the
current solve vs 3.4 dB for the naive equal-voltage drive**. The analytic
tier ships the corrected Phase-C forms: EXACT directivity (visible-region
numeric peak — the |Σaₙ|² shortcut is 81× wrong for a scanned array), exact
HPBW, Hansen-Woodyard `−(kd + 2.94/N)` (D = 17.9565 at N=10, d=λ/4 — the
printed 17.89 is low), grating-lobe guard, first-sidelobe level, induced-EMF
mutual impedance, pattern multiplication. The **Array Designer** dialog
(command `EMStudio_ArrayDesigner`): N parallel dipoles in **linear**,
**planar** (Nx×Ny grid) or **circular** (ring) geometry — the 2-D pair added in
v1.10.0 over the `planar_array_factor` / `circular_array_factor` engines gated
since S5, with 2-D steering (θ₀, φ₀), per-axis or around-the-ring tapering and
a grating-lobe warning when the ring's arc spacing exceeds λ/2 — named drive
distributions (broadside · end-fire · Hansen-Woodyard · scanned · cardioid
pair), derived target-current table, predicted read-outs, and a live Verify
(N+1 NEC2 runs off-thread) overlaying the achieved azimuth cut with the drive
table — EX voltages, per-element ACTIVE impedance and power, with warnings on
a negative driving-point resistance (superdirective, not passively
realizable) and negative per-element power. ⚠⚠ The live NEC2 Verify, the 3-D
overlay and the pattern CSV export each build a LINEAR row of dipoles, so all
three are disabled **and refuse if called anyway** for the planar and circular
geometries — verifying a linear array and reporting it as the planar one on
screen is the wrong-answer-that-looks-right class, and a slot stays reachable
from a script even when its button is grey. Honest behaviour: per-element
tapers are the S5 slice; TransmissionLine feeds are refused (a corporate/TL
feed is a different feed model); deep nulls beyond −60 dBi are read from the
raw NEC2 output. Gates: `tests/validation/system_arrays.py` (FAST battery,
mutation-tested) + `tests/validation/array_nec2.py` (SOLVER tier, live chain
under python3 AND freecadcmd) + an `_array_designer_dialog` gui_smoke check
(offscreen, both FreeCADs).

**§7 tapers / scan read-outs / 2-D arrays (S5) — ✅ validated (v0.68.0):**
amplitude-taper synthesis (`emstudio/system/tapers.py`) on the S4 drive
chain — **binomial** (Pascal rows; zero interior sidelobes at every spacing,
end-fire shoulder honestly reported above λ/2, dynamic-range impracticality
flagged), **Dolph-Chebyshev** by exact Schelkunoff root placement (the
two-method-verified N=10 set to 1e-5, flat −26.0206 dB realized floor, dual
`r0`/`sll_db` spec because the two conventions genuinely differ, and
`d_max` with the edge-lobe violation gated), and **Taylor n̄** by pattern-zero
placement (tracks the ideal line source to ~0.04 dB at N=33; realized SLL is
near — not equal to — design BY DESIGN, and is property-gated per the
de-risk's refutation of digit-gating). Scan read-outs: 1/cos beam broadening,
the exact two-arccos scanned HPBW (0.006° vs the numeric-exact machinery),
and cos^q scan loss with **q exposed** (a convention, not physics). 2-D array
factors: planar rectangular (separability gated to machine precision) and
the exact circular-ring sum (cophasal steering exact to 1e-9). The Array
Designer gains the taper picker + read-outs and **Export pattern CSV** (the
§6 coverage antenna-pattern format). **Live-validated** on the S4 chain: an
8-element Dolph R0=20 ULA steered 20° off broadside lands at exactly the
commanded angle and reproduces the **−26.02 dB equal-ripple floor to
0.04 dB** on real coupled dipoles (measured −26.06/−26.28/−26.21/−26.06)
against the uniform control's −12.7 dB — 13.4 dB of suppression for 0.58 dB
of gain. Gates: `tests/validation/system_tapers.py` (FAST, mutation-tested
12/12) + `tests/validation/array_taper_nec2.py` (SOLVER, live).

**§7 is COMPLETE (S1–S7).** RF direction finding (S6) ships — Watson-Watt /
Adcock, multi-baseline interferometry, pseudo-Doppler ring sizing and a
correlative manifold built from per-element NEC2 patterns, gated by
`tests/validation/system_rfdf.py`; its manifold decodes an independent receive
simulation at **0.00° bearing error**. The System group (S7) ships too, and is
the menu that spans the tier boundary: Isolation Matrix and Co-site are free,
Matching / Array / RFDF are Pro.

> ⚠ **This paragraph said both "remain planned" until 2026-08-20**, long after
> both shipped — an **understatement** in a public document, and it flatly
> contradicted `PRO.md`, which sells RFDF on that same 0.00° figure. Overstating
> is the failure everyone watches for; understating hides work that was paid
> for and is just as wrong. ⛳ Neither doc was checked against the other, which
> is the same "nobody measures it" class as every other drift found this week.

## Antennas & RF

| Capability | Status | Backend | Evidence |
|---|---|---|---|
| S11 / reflection | ✅ validated | openEMS, NEC2 | patch −29 dB @ 2.435 GHz vs tutorial |
| VSWR | ✅ | derived | — |
| Input impedance R+jX | ✅ validated | openEMS, NEC2 | dipole 71.9 Ω at resonance |
| Resonance detection | ✅ | derived | dipole 296 MHz |
| Touchstone (`.sNp`) export | ✅ validated | order follows what was SOLVED; refuses an order it cannot support, naming the missing terms | `touchstone_export` + `n_port_smatrix`: 1/2/3/5-port layouts, row-major wrap, S11 S21 S12 S22 quirk order |
| **Far-field radiation pattern** | ✅ validated | openEMS NF2FF, NEC2 RP, **Palace `r*E` (v1.10.0)** | dipole 2.13 dBi + axial null; patch 6.6 dBi; full sphere 37×72; Palace's own radiating dipole +1.821 dBi vs 2.151 analytic (⚠ directivity, not gain) |
| **3-D pattern balloon (rotate/zoom/pan)** | ✅ validated (v0.72.0) | mplot3d tab + FreeCAD viewport object; reachable from Results, Element Designer and Array Designer | `pattern_vtu.py`: 43 checks — radius follows the gain law pointwise, phase-centre registration, closed-phi wrap, read back by our own VTU parser; mutation-tested 7/7 |
| **3-D currents / field plane in viewport** | ✅ validated (v0.72.0) | FemPostPipeline VTU | `pattern_vtu.py`: polyline cell + m→mm + mA conversion; quad cells, fixed-axis offset, dB self-normalisation |
| **Pattern per swept frequency + picker** | ✅ validated (v0.90.0–0.91.0), openEMS added 2026-08-22 | NEC2 multi-frequency `FR`+`RP`; **openEMS from one broadband NF2FF recording — no extra solve at all**; **Pattern Frequencies…** dialog with editable band + a recommended step landing on S11 sample points; both pattern tabs and the 3-D export share one selection | `pattern_sweep.py`: 88 checks — N patterns from ONE run (201 in 7.18 s), per-frequency gains pinned, band round-trip, the far-field sort proven on a DESCENDING file, and the flat-band pattern-frequency guard now shared by BOTH backends (NEC2 had a bare argmin until 2026-08-24; one constant in `emstudio.post.sparams`); 11/11 + 5/5 + 3/3 + 2/2 mutations caught |
| **NEC-2 thin-wire validity check** | ✅ validated (v0.91.0) | `thin_wire_report()` from the GW cards actually written; warning under the result plots when d/a < 8 (Burke & Poggio) | polyline chords freed of the lone-wire 3-seg floor: real 72-chord helix 240→80 segments, d/a 2.63→8.19; dipole frozen deck byte-identical (2.13 dBi) |
| **Near-field \|E\| map** | ✅ validated | openEMS FD dump | patch XY-plane map |
| **Current distribution** | ✅ validated | NEC2 | dipole half-sine |
| **Monopole over ground (VLF/LF)** | ✅ validated | NEC2 (GN card) | short λ/10 Re 4.02 Ω vs Rr 3.95 Ω; λ/4 39.5+j22.6 Ω; finite-ground efficiency ≈5% |
| **Electrically-small analytics (VLF/LF/MF)** | ✅ validated | analytic | short dipole/monopole/loop Rr, effective height, Chu Q/BW, loading |
| **Band → method picker** | ✅ validated | analytic | routes VLF→mmWave to the valid engine |
| STL-geometry import | ✅ validated | openEMS | patch via STL substrate |
| **Multi-port S21 / coupling** | ⚙️ infrastructure | openEMS | plumbing correct; needs well-posed ports |

## PCB / microstrip

| Capability | Status | Notes |
|---|---|---|
| Microstrip (MSL) port type | ✅ present | selectable on any port |
| Two-port S11 + S21 pipeline | ✅ validated | notch filter S11/S21 below |
| **Trace-aware meshing (microstrip)** | ✅ validated | λ/50 in the dielectric + thirds-rule strip mesh + board-hugging domain; `SolverOpenEMS.MicrostripMeshMode = Auto` |
| **Automatic PCB notch-filter template** | ✅ validated | S21 notch 3.662 GHz vs analytic 3.683 GHz (−0.6%) and openEMS tutorial 3.671 GHz (−0.24%); passive to −0.03 dB; ~40 s. On the toolbar. |

## Wire & cable (Litz)

| Capability | Status | Evidence |
|---|---|---|
| Skin effect (exact) | ✅ validated | Kelvin solution vs expansions |
| Internal proximity | ✅ validated | FastHenry-anchored, 0.0% at design point |
| External (winding) proximity | ✅ | He/I context |
| DC/AC resistance, Q | ✅ | — |
| Types 1–9, cores, wraps, jacket | ✅ | build schedule |
| Cross-section drawing + CAD export | ✅ | 18,200-strand verified |
| Per-bundle current sharing | ✅ validated | symmetry gates |
| Ampacity estimate | ✅ | surface heat balance |
| **Coax TEM analytics (§2 Cable Designer engine)** | ✅ validated | Z0/VF/C′/L′/TE11-cutoff/attenuation vs Belden 8262 RG-58 (50.0 Ω via the 0.94× stranded-centre correction; 100.1 vs 101 pF/m) + RG-142 (48.0 Ω, bottom of the MIL 50±2 window); smooth-conductor loss 55–100 % of braided datasheet (documented); matches the Palace-gated coax_z0 |
| **Cable Designer UI (construction selector)** | ✅ validated (v0.37.0) | Litz \| Coax \| Single Wire in one shell; RG-58/RG-142 primary-datasheet presets reproduce the gated numbers in-dialog; Palace full-wave verify (RG-58: worst \|S11\| −31 dB, full-wave VF 0.6660 vs 1/√εr 0.6667 = −0.09 %); GUI-smoke exercised on both FreeCADs |
| **Single wire (ops=[] litz reuse)** | ✅ validated (v0.37.0) | Rac/Rdc == exact Kelvin solution (single-conductor internal-proximity term correctly vanishes); AWG-10 Rdc 3.277 mΩ/m handbook anchor; OD/ampacity/spec/PDF |
| **Twisted pair (§2-B)** | ✅ validated (v0.38.0) | Exact two-wire acosh line + Lefferson 1971 εeff (θ in DEGREES — the degrees control 89.03 Ω is gated against the public radians bug 94.90); Cat5e 107.7 / Cat6 99.9 Ω vs the 100±15 Ω primary-datasheet band; C′ 44.2 vs Belden 49.2 pF/m; RDRE shielded form vs Miller's exact BSTJ solution (+0.08 % at d/s 0.1 → +5.1 % at 0.6, flagged); 120/78-Ω data-cable C·VF identities |
| **Multi-design bundle (§2-C, geometric)** | ✅ validated (v0.39.0) | Tangency packing + minimal-enclosing-circle axis: exact for 2/3/7-member classics (7 equal → OD 3×, fill 7/9 exactly), n=4 documented ≤+15 %; no-overlap/containment invariants on unequal mixes; deterministic; core/finished OD + fill + weight + spec |
| **Bundle coupling & crosstalk (§2-C, electrical)** | ✅ validated (v0.40.0) | Wide-separation L == Paul's printed closed forms, within his printed 1.4-2 % of the exact MoM matrices; identity-C within 2.5 % (bare, s/rw ≥ 4 flagged); FastHenry loop route (GMD-corrected, partial→loop, two-length) hits round-wire DC analytics to ±0.02-0.3 % incl. mixed radii; Paul's printed crosstalk example to the digit (MNE 5.5449 ns, −49.16 dB, 46.2/23.1 mV, 1.94 mV CI floor, ×10.85 dominance) + LearnEMC −23/−39.5 dB |
| **Insulated-bundle capacitance (MoM)** | ✅ validated (v0.48.0) | Paul's RIBBON.FOR method-of-moments (entire-domain Fourier charge + bound-charge layers, point-matched): the inhomogeneous insulated ribbon TL C reproduces Paul problem 5.15 (24.98 / -6.266 pF/m) to the digit, the bare C+identity recovers Paul's exact L (0.7485 / 0.2408 µH/m), εeff shift in the printed 50-66 % band; wired into the Bundle-page crosstalk (insulated members use the MoM C, bare keep the identity) |
| **Differential pair-to-pair coupling (mixed-mode)** | ✅ validated (v0.49.0) | Bockelman-Eisenstadt congruence reduction (T_I = (T_V⁻¹)ᵀ pinned): Ldd/Mdd/k_diff, Cdd_AB and the ASTM D4566 CUPP = −4·Cdd_AB; diff NE/FE weak crosstalk within 0.011 %/0.026 % of an independent full-MTL 8×8 oracle (12-digit anchors); invariants Zdd = 2·Zodd, Ldd·Cdd = µ0ε0 + the 2×/0.5× mixed-definition traps; mirror-symmetry null exact; RADC-TR-76-101 Vol V twist model (page-image-verified eqs 4-3/4-8/4-10/4-43) — odd-N envelope 1/N, capacitive floor for unbalanced receptors, balance null, ground-loop warning; the 9.54 dB low-Z benefit sits inside the report's printed 10.25 ± 3 dB band |
| **Cable thermal / ampacity (§2 thermal)** | ✅ validated (v0.50.0) | IEC 60287-2-1 radial ladder (worked examples to 1e-9) + Churchill-Chu free convection on the printed AHTT air table (Cengel Ex 9-1 / AHTT Ex 8.4 to the digit, ±25 % of Morgan) + radiation; ρ(T) loss with runaway detection; ampacity vs NEC 310.17 / Multicable / MIL-W-5088L bands (AWG-10 105 °C: 66.6 A vs the 58 A ±25 % row); IEC 60949 adiabatic (J0 143.08/94.48, 630 mm² rows 0.15 %, BS 7671 k ±0.5); NEC 310.15(C)(1) derating exact; transient τ = C/G lump |
| **Coax RF average power (§2 thermal)** | ✅ validated (v0.50.0) | Exact dissipation identity p′ = (ln10/10)·A·P and the exact ½-dielectric-heat factor (TEM 1/r²); Rs/a-vs-Rs/b split with per-conductor σ; **Times LMR-240 catalog table reproduced within 90-125 % (worst 1.092, 30-5800 MHz)** with the datasheet attenuation split; Belden 8262 / RG-142 one-sided (smooth-conductor loss ⇒ optimistic rating, stated) |
| **Thermal cross-section + heat-rise view (§2 thermal)** | ✅ validated (v0.50.0) | Exterior 2-D field: exact interior ladder → flux-preserving film δ = k_f/h = D/Nu → laminar plane-plume similarity above (GPS/Liñán, Pr 0.7 pins re-derived in-gate by an independent RK4 shoot incl. the Pr = 2 closed form √5/4); enthalpy closure 0.23 % worst, power-law exponents exact, bitwise mirror symmetry, bounded monotone decay; honestly labeled illustrative outside the film |
| **SOLVED convection on a SELECTED solid — open air (§8a)** | ✅ validated (v1.1.0) | Any document solid, tessellated as-is (gravity −z), dissipated power as surface flux, open-air far-wall box; returns surface ΔT + mean h + the field in the 3-D view. Sphere anchors, live at cells_bg 32 (re-measured 2026-08-23 on the T1 layered mesh): conduction Nu_D 2.5613 inside the EXACT sandwich [2.3374, 2.6667] (two-sided, citation-free); free convection Nu_D 17.9709 vs Churchill 17.4656 (**+2.9 %**, was +4.3 % unlayered) at the resulting Ra_D 1.35e6. The SOLVER gate self-pins its own cells_bg 24 fidelity (2.5548 / 17.8471, re-pinned 2026-08-23 on the T1 layered mesh — the layers moved convection −2.7 % and took its Churchill agreement from +4.9 % to +2.0 %). ⚠ laminar, constant film-T properties (dialog warns on drift), no enclosure geometry read yet, no radiation. **Laminar-ONLY: unvalidated above Ra_D ≈ 1e8** — from the product's own air table that is crossed near D ≈ 0.5 m at ΔT = 30 K (Ra_D 1.8e7 at 0.2 m, 2.2e9 at 1 m); the dialog computes Ra and says so |
| **SOLVED bundle convection — CFD replaces the correlation (§2 thermal)** | ✅ validated (v0.97.0; re-measured 2026-08-23 on the T1 layered mesh, every rung moved < 0.11 %) | Ladder, each rung changing ONE variable, on the native ESI v2512: 1 cable/0.40 m box Nu 3.9787 and 1 cable/0.20 m Nu 3.8651 both INSIDE the Churchill-Chu/Morgan envelope (this is what validates snappyHexMesh + the flux BC + the patch reader), then 3 cables/0.20 m Nu 3.1563 — **Churchill-Chu over-predicts a trefoil's film coefficient by 19.66 %, in the UNSAFE direction** (confinement 3 %, bundling a further 18 %). Feeds `surface_h`/`solve_steady` as a dimensionless `bundle_factor` (default 1.0 = bit-identical to the correlation); a 40 A cable moves 56.55 → 59.75 °C (worked with the pre-T1 factor; the T1 move is < 0.05 K, far under the solver's own ~2 K run-to-run floor). ⚠ 2-D, laminar, no radiation, one operating point; Ra is an OUTPUT (flux BC), so every comparison is made at the Ra that resulted |
| **Mixed LOADING within one diameter — one factor per (size, load) (§2 thermal)** | ✅ validated (v0.98.0) | A group is one diameter at one wall flux, because that is what one snappy patch carries; the result is keyed by PATCH, so two same-size cables on different losses get their own factors instead of one silently overwriting the other. Measured (2 × 20 mm, 0.20 m box, 400 vs 100 K/m; re-measured 2026-08-23 on the T1 layered mesh at the same recorded configuration, cells_x 50 / 1500 it): **Nu 3.8112 / 2.6886 → factors 1.0134 / 0.9018, 12.4 % apart — as large an effect as the diameter mix**, and the LIGHTLY loaded cable is still the worse cooled (small driving dT, sitting in its neighbour's warm field; the heavily loaded one now reads a hair ABOVE the correlation at this cheap fidelity). ⚠ dT ratio **2.82 for a 4:1 flux ratio** — neither the 1.0 of a shared BC nor the ~3.0 of two uncoupled cables, which is the gate's proof that this is ONE coupled solve. Face counts are an exact equality (928 == 928) since the geometry is identical. Reachable from the UI since v0.99.0 via the bundle table's per-member **Current (A)** column — resistance from the CONDUCTOR Ø, flux over the ENVELOPE Ø, all-or-nothing so a part-filled column falls back rather than inventing a load |
| **Mixed-diameter bundles — one Nusselt number PER SIZE (§2 thermal)** | ✅ validated (v0.97.0) | Nu_D is built on a diameter, so unlike cables are never averaged: each size is its own STL solid → its own snappy geometry entry → its own **patch**, solved together in one enclosure because the sizes cool each other. Measured (1 × 20 mm + 2 × 10 mm, 0.20 m box, 400 K/m; re-measured 2026-08-23 on the T1 layered mesh at full fidelity — moves +0.06 % / +0.18 %): **Nu 3.6119 / 2.0033 → factors 0.9486 / 0.8456, 12.2 % apart**, both below their OWN Churchill-Chu (−5.14 % / −15.44 %); the 20 mm recovers Nu 3.1563 → 3.6119 (+14.4 %) when its neighbours shrink. Uniform bundles are byte-identical to the single-patch writer (sha256 over all 14 files) so the ladder above still describes what runs; smaller cables get ceil(log2(d_max/d)) extra refinement levels so their Nu is not a mesh artifact. ⚠ Mixed DIAMETERS only — mixed LOADING within one diameter is refused, not merged |
| **Wind loading on a structure (§2 mechanical)** | ✅ validated → **Re 1.5e5 for square sections** (v1.8.0) | Three validated rungs, each anchored on published numbers: **steady** `simpleFoam` at Re 20–40 (Cd 2.0646 / 1.5448, \|Cl\|/\|Cd\| ~2e-7 — zero lift by symmetry, exact and citation-free); **transient laminar** `pimpleFoam` at Re 100/150 (St 0.1647 vs Williamson 0.1643, Cd 1.3411 in the published 1.30–1.40); and — new in v1.8.0 — **transient kOmegaSST URANS on the sharp-edged SQUARE section** at Re 21,400 against the Lyn (1995) LDV experiment and Tian (2013) same-code OpenFOAM study (`openfoam_wind_ras`: St window 0.125–0.150 asymmetric over the known 2-D URANS high bias, Cd 1.95–2.25 spanning experiment+DNS+URANS, shedding proven by lift amplitude). Valid to **Re 1.5e5** on the square's flat measured Cd plateau (Fage & Johansen 1927); **circular sections above Re 200 still refuse** — their drag crisis is transition-location physics no single-Re anchor transfers across, and `validity_note()` says so instead of letting a plausible number ship. ⚠ Domain is part of the benchmark: lateral ±10 d reproduces the sources' ~5 % tunnel blockage (a 2.5 %-blockage domain legitimately reads Cd a few % lower — measured), and at 4.5 d the vortex street reaches the freestream boundary at full strength and the solve diverges (measured, ADDENDUM 2 of the anchor doc). ✅ **THE DOOR EXISTS since v1.9.0** (AJ's order 2026-08-24, the day after the anchor went green — the B6 anchor-first ordering honoured): **Analysis ▸ Solve Wind Loading…** chooses the method from the physics automatically (the T4 pattern — steady below shedding, transient laminar to Re 200, the validated kOmegaSST square configuration to Re 1.5e5) and REFUSES un-anchored configurations before the button with the engine's own note — a circular mast in real wind cannot be run, only explained. Reports Cd (+St/Cl/cycles on the transient rungs), drag per metre and total over the member length; the RAS rung states its hours up front; Cancel is real (`run_wind` grew the same cancel contract as the thermal chains) |

**Turbulence position (all OpenFOAM cases, stated once — REWRITTEN for
v1.8.0; the previous "everything is laminar" text had been false since
v1.6.0 and survived two releases, which is why this paragraph now states
per-writer facts instead of one sweeping claim.** Four writers take
`turbulence="kOmegaSST"` and are **validated in the turbulent regime through
the product's own path**: the cavity (Betts & Bokhari Ra 8.6e5 measured
profiles, worst T 4.8 % of span — `openfoam_ras_cavity`), the §8a solid
(sphere at resulting Ra 2.08e9, Nu +8.7 % of Churchill with the settle
criterion as the laminar discriminator — `openfoam_ras_solid`), CHT (the
compressible wall-function set from the v2512 tree's own tutorials, chain
green at Ra 2e8), and — v1.8.0 — wind (square-section URANS vs the Lyn/Tian
Re-21,400 anchor — `openfoam_wind_ras`). The §8a/§8c dialogs **choose** RAS
above Ra 1e8 and NAME the model in every result; below the thresholds every
laminar case is byte-identical to the pre-RAS writers (sha256-proven).
Prism boundary layers are ON by default for both snappyHexMesh paths
(`wall_layers=3`; 0 reproduces the old mesh byte-for-byte). Unknown model
names are REFUSED, and steady+kOmegaSST on the wind path is refused too
(steady k-ε converges to a non-shedding artifact on the square — Franke &
Rodi 1993).

## Magnetics / low-frequency (Phase 3 — Elmer FEM, axisymmetric)

| Capability | Status | Evidence |
|---|---|---|
| Inductance / R(f) of arbitrary conductors | ✅ FastHenry (PEEC) | wire gate |
| **Eddy currents / induction heating (harmonic)** | ✅ validated | billet power vs exact Bessel solution: +0.03% @ 1 kHz, +1.3% @ 10 kHz; B-field to 0.1% |
| **Coil excitation (stranded, N×I, phase)** | ✅ validated | solenoid center B vs current-sheet analytic: −0.04% |
| **Coil L_eff + reflected R (loss referred to coil)** | ✅ validated | R_reflected = 2P/I² energy-conservation cross-check: +0.01% |
| **Wireless power transfer: L, M, coupling k** | ✅ validated | vs Grover/Maxwell coil formulas: L ±0.5%, M ±0.4%, k ±0.3% (3 gaps) |
| **B / J / Joule-heating fields in 3-D viewport** | ✅ | VTU → FemPostPipeline (mm-aligned overlay) |
| Geometry class | ✅ axisymmetric (full chain) + general 3-D magnetostatics (v0.56.0) | 2-D: coaxial cylinders/tubes/rings about Z (the CENOS IH/WCH class, eddy/thermal/B-H); 3-D: ANY FreeCAD solids via the AnalysisType = 3-D Magnetostatic (DC) mode (BREP → conformal mesh → WhitneyAV; B-field maps; no eddy/thermal at DC) |
| **General 3-D magnetodynamics (CoilSolver + WhitneyAV)** | ✅ validated (v0.55-0.56) | engine: thick solenoid on-axis −0.55% (ends −0.10/−0.03%), Helmholtz center −0.62% + flatness field-shape check, off-axis loop vs elliptic integrals −0.78%; FreeCAD GUI path (BREP import, template mesh): −1.26% vs the same closed form |
| **TEAM Problem 7 (measured benchmark, 3-D eddy currents)** | ✅ validated (v0.55.0) | ⚠️ MEASURED-data tier: 2.83% normalized RMS vs the 17 published Bz points (A1-B1, 50 Hz, ωt=0; gate ≤10%) — own license-clean deck/mesh, self-pinned norms |
| **Thermal chain (Joule → steady-state temperature)** | ✅ validated | energy balance −0.00%; radial ΔT vs exact 1-D solution +0.07% |
| **Surface radiation BC (grey-body, stacks on convection)** | ✅ validated (v0.51.0) | mixed conv+radiation surface temperature vs an independent bisection root-find of h(Ts−Tamb)+εσ(Ts⁴−Trad⁴)=P/A: −0.00%; interior ΔT unchanged +0.07%; emissivity 0 = byte-identical convection-only decks; the T⁴ nonlinearity gets a Newton block + mandatory Stefan-Boltzmann constant |
| **Temperature-dependent conductivity k(T)** | ✅ validated (v0.52.0) | k(T)=k0(1+β(T−ambient)) via a Variable-Temperature MATC + Newton block; the Kirchhoff-transform interior heat integral ∫k(T)dT vs the source-set constant σω²μ0²H0²a⁴/128: +0.10%; β=0 = byte-identical constant-k decks |
| **Temperature-dependent conductivity σ(T) — coupled Joule** | ✅ validated (v0.53.0) | σ(T)=σ0/(1+α(T−ambient)); the harmonic solve iterates two-way with the heat equation in an outer steady-state loop (transient: field re-solved every timestep); coupled billet vs an independent 1-D RK4-shooting reference: power −0.015%, temperatures <0.01 K; the −5.57% self-limiting delta vs constant-σ matches the reference; α=0 = byte-identical decks |
| **Transient heating curve T(t)** | ✅ validated | vs lumped-capacitance exponential: 0.9% of local rise, final +0.45% |
| **Parametric k-vs-gap sweep (WPT)** | ✅ validated | swept k(gap) vs Maxwell: within 0.24%, monotonic 8–55 mm |
| **Nonlinear B-H materials + Static (DC) mode** | ✅ validated (v0.54.0) | Material BHCurveB/H table (B-then-H, guarded against silent column-swap/coarse sampling); Static (DC): exact — gapped pot-core λ(1/6/15 A) vs an independent nonlinear ladder MEC +2.0…+3.8% (fringing-limited), L(I) droop 15.3→8.0 mH, linear control 1.93× above saturated λ; Harmonic (AC): peak-\|B\| secant effective-µ — equals static bit-exactly at σ=0, droop 0.520, linear-as-table == RelPermeability at 2e-9. NOT waveform-accurate in AC (no harmonic distortion) |
| Nonlinear B-H waveform accuracy (AC), hysteresis | ⛔ planned | harmonic B-H is amplitude-approximation only; transient B-H verified working (BDF2 probe). ⚠ **Sized 2026-08-26, since a public soft commitment should not float unsized**: exposing it is a solver-writer switch plus a dialog rung plus one gate — a day's work — and it is **deferred, not scheduled**, because nothing gates transient B-H against a measured waveform yet and this project does not ship an un-anchored number. **Re-open trigger: a published measured AC B-H waveform for a named material.** Hysteresis (TEAM 32 class) remains not planned |

## Full-wave FEM (Phase 4 — Palace)

| Capability | Status | Evidence |
|---|---|---|
| **Resonant-cavity eigenmodes (box)** | ✅ validated | rectangular cavity f_mnp vs closed form: TE101 within 0.001%, all modes <0.02% |
| **Eigenmodes, general 3-D geometry (BREP)** | ✅ validated | cylindrical cavity vs Bessel modes: TM010 +0.25%, first modes <0.3% (any closed solid → BREP export) |
| Mode Q / loss | ✅ | from Palace (∞ for lossless PEC) |
| **Driven S-parameters (wave ports)** | ✅ validated | WR-90 waveguide vs TE10: |S11|<−94 dB, |S21|=0.00 dB, S21 phase slope vs −βL to 0.002° |
| **Driven S-parameters (coax, lumped ports)** | ✅ validated | matched air coax vs TEM: Z0 49.94 Ω, |S11|<−29 dB, |S21|=+0.34 dB, S21 phase slope vs −βL to 0.043° |
| **Adaptive fast frequency sweep** | ✅ validated | WR-90 dense 41-pt sweep from 6 full solves; matches TE10 at every point (`SolverPalace.FastSweep`) |
| **Adaptive mesh refinement (AMR)** | ✅ validated | Order-1 cavity: coarse 0.32% → AMR 0.074% vs TE101 (4.3× closer), mesh grown 2039→30151 elements; works eigenmode + driven (`SolverPalace.MeshRefinement`) |
| **Driven S-parameters, general 3-D (BREP)** | ✅ validated | wave ports on ANY closed solid: WR-90-as-BREP reproduces TE10 (|S11| −68.9 dB); circular waveguide evanescent below the TE11 cutoff (2.928 GHz), lossless above (Circular Waveguide template) |
| **Far field from a driven solve** | ✅ validated (v1.10.0) | Palace's `farfield-rE.csv` parsed into the same `FarFieldResult` every other backend returns, on an explicit angle GRID rather than an `NSample` spiral; and `write_geo_dipole_open` meshes the radiating domain that feeds it (two arms, a flat gap rectangle as the lumped port, an absorbing sphere). Checked against the closed form for a half-wave dipole: broadside **+1.821 dBi vs 2.151 analytic**, a 19.4 dB axial null, 0.083 dB φ ripple (`palace_dipole_farfield`). ⚠ **DIRECTIVITY**, not gain. ⚠ API and gate only — no Templates entry builds one |
| Geometry class | ✅ box + coax + general BREP (eigenmode **and driven**) | every closed solid works for eigenmode and driven wave-port analyses |

## Co-site interference / EMC (systems — §5)

| Capability | Status | Evidence |
|---|---|---|
| **Intermodulation products + levels** | ✅ validated | product frequencies (2f1−f2, f1+f2−f3, …) + intercept-point level `Σ|aᵢ|Pᵢ−(N−1)IPₙ`; two −10 dBm tones, OIP3 +30 → IMD3 −90 dBm |
| **Receiver desensitization** | ✅ validated | interferer at rx = tx − isolation vs front-end blocking; margin |
| **Broadband transmitter noise** | ✅ validated | tx noise (dBc/Hz) integrated over rx BW − isolation vs sensitivity |
| **Frequency-plan clash / D-U** | ✅ validated | co-channel carrier in a victim passband → D/U ratio |
| **Frequency-map visualization** | ✅ | dialog plot: tx carriers, rx passbands, IMD products |
| **Frequency-plan optimizer** | ✅ validated | retunes transmitters to minimise IMD/desense/co-channel; drives a dirty plan to cost 0 (exhaustive / greedy) |
| **Antenna-to-antenna isolation matrix** | ✅ validated | NEC2 Y-matrix (drive-one-of-N, invert Y→Z→S): 2 λ/2 dipoles @ 0.5λ → |S21| −13.78 dB, Z21 −15.0−j28.0 Ω vs Balanis −12.5−j29.9 Ω, reciprocity 1e-14 |

## Geographic coverage / propagation (systems — §6)

| Capability | Status | Evidence |
|---|---|---|
| **Free-space (Friis) path loss** | ✅ validated | 81.98 dB @ 1 km / 300 MHz |
| **Knife-edge diffraction (ITU-R P.526)** | ✅ validated | J(0)=6.0, J(1)=13.9, J(2.4)=20.6 dB; clear-path 0 |
| **Two-ray plane-earth (d⁴)** | ✅ validated | +12 dB per doubling; 80 dB @ 1 km/10 m/10 m; breakpoint |
| **Field strength from EIRP** | ✅ validated | 104.8 dBµV/m @ 1 kW EIRP / 1 km (= P(dBW)+74.8−20log10 d_km) |
| **Terrain single-edge (Deygout) diffraction** | ✅ validated | dominant knife edge over a supplied profile |
| **Link budget (rx power + fade margin)** | ✅ validated | Ptx+Gtx+Grx−PL, margin vs sensitivity; dialog + plot |
| **DEM import (SRTM .hgt + GeoTIFF)** | ✅ validated | `.hgt` + minimal uncompressed/DEFLATE GeoTIFF (no GDAL); bilinear vs analytic hill <1.5 m |
| **Terrain path profile (great circle + earth bulge)** | ✅ validated | tx→point sampling; hill = controlling Deygout edge; 4/3-earth bulge |
| **Area coverage heatmap (one station)** | ✅ validated | Prx/field over a grid; smooth-earth mode degenerates *exactly* to EIRP−FSPL; DEM ridge shadows behind it; azimuth-pattern lobing |
| **KML GroundOverlay export** | ✅ validated | Google-Earth/QGIS PNG overlay + tx placemark; well-formed LatLonBox |
| **LF/MF ground-wave (ITU-R P.368 / Norton)** | ✅ validated | complex numerical distance + attenuation vs the ITU Handbook worked examples (|ρ|≈26→\|A\|0.0226; |ρ|≈43.5→31.6 dBµV/m); 300 mV/m-at-1-km ref; sea>wet>dry; valid to ~100 km |
| **Spherical-earth LF/MF ground-wave (ITU-R P.368-10 / NTIA LFMF port)** | ✅ validated | numpy/scipy port of the NTIA LFMF v1.1 reference (the software integral to P.368-10): flat-earth Sommerfeld + curvature correction auto-switching to the Wait/Hufford residue series; replays a 2497-point full-precision oracle grid from the upstream binary to worst 3.2e-5 dB + the official examples; 0.01–30 MHz, 0.001–10000 km; <10 kHz hard-stops (P.684 band); opt-in `gw_engine="p368"` in the coverage/multi-station dialogs |
| **Millington mixed-path (land/sea)** | ✅ validated | forward+reverse average; reciprocity + bracketing gated |
| **Multi-station service/interference contours (D/U)** | ✅ validated | composes N single-station footprints on one grid; two-gate served/interference-limited/no-service; power-sum (+3.0103 dB) or worst-case aggregation; source-tagged FCC/ITU protection ratios (FM 20 dB, AM 26 dB, BS.412 45 dB…); D/U reciprocity; best-server network view; KML |
| **Multi-edge terrain diffraction (Deygout recursive + Epstein–Peterson + Bullington)** | ✅ validated | vs NTIA TR-26-580 worked cases (Case 23 2-edge Deygout 73.29 / EP 70.52 / Bullington 43.17 dB; Case 13 4-edge 99.88 / 95.71 / 46.22 dB; 6-edge near-grazing 39.42 / 38.04 / 9.77 dB); reuses the shipped ITU-R P.526 J(v); opt-in in the coverage terrain mode (single-edge default byte-identical) |
| **Two-ray plane-earth on clear terrain paths** | ✅ validated | opt-in `ground_reflection`: flat DEM degenerates EXACTLY (0.00 dB) to the smooth-earth footprint; replaces the near-grazing edge on clear paths only; shadowed cells untouched |
| **Okumura-Hata / COST-231 empirical models** | ✅ validated | formulas confirmed vs COST 231 Final Report ch.4 + Rappaport; externally verified example 900 MHz/100 m/2 m/4 km urban = 137.05 dB; environment vector 151.0/141.1/122.5 dB (urban/suburban/open); COST-231 regression vectors; coverage mode + Environment picker; heatmap wiring exact |
| **P.1546-6 point-to-area field strength** | ✅ validated | vendored ITU-R WP3K reference (Py1546, permissive + PROVENANCE); replays ALL 24 official profiles / 52 datasets to 0.000000 dB; wrapper `coverage/p1546.py` with hard validity enforcement |
| **P.1812-6 path-specific propagation + delta-Bullington** | ✅ validated | vendored ITU-R reference (py1812, lazy ITU maps — never bundled); replays ALL 19 official profiles / 63 datasets (Lb, Ep AND the Eq-21/27 delta-Bullington intermediates) to 0.000000 dB |
| **P.452-18 interference prediction** | ✅ validated | vendored ITU-R reference (Py452, lazy ITU maps — never bundled; official-zip downloader/manual fallback in `itu_maps`); replays ALL 17 official CG-3M profiles / 595 cases — Lb + 8 sub-model losses to 5e-9 dB, geometry intermediates to 5e-7 |
| **P.2001-6 wide-range propagation (0-100 % of year)** | ✅ validated | vendored ITU-R reference (Py2001, lazy ITU maps); replays ALL official examples — 2 profiles / 4430 cases to 1.2e-12 dB |

## Performance — parallel CPU and GPU

Every figure here is measured on named hardware. A speed-up without a machine
beside it is not a claim, it is a mood.

| capability | status | evidence |
|---|---|---|
| **Palace MPI (multi-core)** | ✅ measured | **18.9×** on a 40×20×60 mm cavity — 346.4 s at 1 rank, 18.3 s at 16. Until v1.4.0 every Palace solve in this project's history ran on ONE core (`-np 1` was hard-coded) |
| **OpenFOAM MPI** | ✅ measured | first parallel path in the product: `decomposePar` → `mpirun -parallel` → `reconstructPar`, scotch partitioning. ⚠ Not monotonic — **5.9× for 64× the cores** on a 4.096 M-cell case, knee at 8–16, memory-bandwidth bound, and ~103 s of serial decompose/reconstruct overhead makes 64 ranks SLOWER than 32 on a short run |
| **Elmer sweep concurrency** | ✅ capped | was `os.cpu_count()` (128 here), now bounded — 128 concurrent solvers is not 128× |
| **GPU solving (Palace, CUDA/HIP)** | ✅ **detected, offered, and reachable** | see below |
| **GPU on macOS** | ❌ **not possible** | Palace declares only `PALACE_WITH_CUDA`/`PALACE_WITH_HIP` and Apple silicon has neither. A limit of the solver, not a gap. Macs use the CPU path |
| **GPU on Windows** | ⚠ **WSL2 only** | no native Windows Palace exists. NVIDIA's CUDA-under-WSL2 route applies; AMD ROCm under WSL2 is untested here and is not claimed |

### GPU, measured — THROUGH THE PRODUCT'S OWN PATH

⚠ An earlier version of this table quoted 165.1 vs 199.6 s at 353 208
unknowns ("1.21× faster") — numbers measured through a HAND-EDITED Palace
config the product could not produce, the exact v1.5.0 sin. Removed
2026-08-23 and re-measured through EMStudio's own generated run
(`run_cavity`, order 3, 145 155 unknowns), Radeon RX 7900 XTX (gfx1100,
ROCm 6.4.2) against **16 MPI ranks** of a Threadripper 3990X:

| | GPU (1 rank) | CPU (16 ranks) |
|---|---|---|
| whole product call | 53.3 s | 52.2 s |
| peak memory (Palace's own log) | **2.3 GB** | 36.6 GB |

**Wall-clock parity at this size and 16× less memory** — the memory headroom
is what lets bigger problems fit on one card — with the same fundamental to
every printed digit, and CPU-vs-GPU agreement ENFORCED to 1e-6 per mode by
`palace_gpu_agreement` (measured margin 2.2e-9).

⚠ **Caveats, all load-bearing.** Field output moves the balance further
against the GPU (device-to-host transfer on every write — observed in the
retired hand-config runs and not re-quoted as a number). The comparison is
only meaningful with the CPU named: sixteen ranks of a 64-core Threadripper
is a strong opponent, and parity against it still means the GPU carries the
same solve in a sixteenth of the memory. And Palace's default build is
CPU-only: `docs/PALACE_GPU_BUILD.md` is the recipe, and `palace_gpu_plan()`
tells you on YOUR machine what is missing and how to get it, before a
30–60 minute compile rather than during one.

⛳ EMStudio refuses `Device = GPU` when the resolved binary is not linked
against a GPU runtime, with a reason naming the card. A GPU request that
silently ran on the CPU would be a setting that changes nothing.

## Deliverables

| Capability | Status |
|---|---|
| Professional PDF reports (antenna + litz + **magnetics**) | ✅ validated |
| Spec / BOM / construction schedule | ✅ |
| CSV / Touchstone / pattern data export | ✅ |

## §3 AI Assistant — what is wired and what is engine-only

The chat assistant (A1–A6, Pro) shipped in v0.73.0 and is gated by the
164-check assistant battery. **Three engine pieces have NO shipped caller and
are recorded here so nobody discovers it the hard way** (the filter/diplexer
precedent — "engine only" is a finding, not a status): `facts_block` renders a
document-state block nothing sends to the model; `_interpret_results` cannot
read a finished solve because solver results are never persisted on the
analysis object; and `intent.py` (the A5 natural-language intent slice) has no
shipped caller either. All three work in isolation and reach no user. Wiring
them is roadmap work, not a bug fix — but a capability matrix that omitted
them would be selling the assistant on plumbing it does not have.

## Roadmap for the gaps

1. ~~**Trace-aware meshing** → validated PCB/microstrip S-parameters~~ **DONE v0.16.0**
   (notch-filter template on the toolbar, gate green). Next PCB items: general
   microstrip circuits (bends, couplers, multi-stub filters), Zc renormalization,
   Palace **lumped ports** as a second (FEM) PCB S-parameter route.
2. **Palace depth**: lumped ports on general BREP (wave ports already do general
   BREP as of v0.21.0). ~~The GPU path~~ **SHIPPED v1.5.1** — Device switch,
   linkage-probed libCEED backend, and the CPU-vs-GPU agreement enforced by
   `palace_gpu_agreement`. (Fast frequency sweep, adaptive mesh refinement,
   and general-BREP driven wave ports all shipped earlier.)
   ~~Far-field extraction~~ **SHIPPED v1.10.0, END TO END** — Palace's
   `farfield-rE.csv` becomes a `FarFieldResult` like every other backend's
   pattern, checked against the closed form for a half-wave dipole, and
   `write_geo_dipole_open` builds the radiating domain that feeds it (two arms,
   a flat gap rectangle as the lumped port, an absorbing sphere).
   `palace_dipole_farfield` runs mesh → config → Palace → parser against the
   closed form: broadside **+1.821 dBi vs 2.151 analytic**, a 19.4 dB axial
   null, 0.083 dB of φ ripple. Palace radiates, end to end, from geometry this
   project builds itself. ⚠ API and gate only — no Templates entry builds one,
   so this is not yet a button a user can press.
3. **Magnetics depth** (v0.51–0.55: radiation BC, k(T), σ(T)-coupled Joule,
   nonlinear B-H + Static-DC, and the general 3-D WhitneyAV ENGINE with the
   TEAM-7 measured gate all shipped; ~~3-D GUI wiring~~ **SHIPPED v0.56.0** —
   `AnalysisType = "3-D Magnetostatic (DC)"` exports every referenced solid as
   a BREP and meshes it conformally, with a **Template: 3-D Solenoid** command
   landing −1.26 % against the exact thick-solenoid closed form): next —
   transient-B-H exposure (sized in v1.10.0 as a day's work, deferred not
   scheduled — nothing gates transient B-H against a measured waveform yet),
   ferrite/shield WPT variants.
4. Near-field at the resonant frequency (currently the sweep center); 3-D field
   volumes; animated fields.
