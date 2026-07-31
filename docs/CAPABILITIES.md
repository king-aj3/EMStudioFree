# EMStudio Capability Matrix

Honest status of every analysis type as of **v0.31.0 (2026-07-08)**. "Validated" means
an automated gate checks it against analytic or published references. Nothing here is
claimed working without a gate behind it.

## Frequency range & validity (DC → mmWave)

**Short version:** EMStudio's **full-wave** engines (openEMS FDTD, NEC2 MoM, Palace
FEM) work from HF through **millimetre-wave** — Palace is **validated sub-0.01 % at
39 GHz and 57 GHz**, so the "DC to 40 GHz and beyond" target is met for full-wave
analyses; the practical upper bound is mesh resolution and memory, not any physics
assumption. The **quasi-static** engines (Elmer magnetics, FastHenry R/L) are
**inherently low-frequency by design** and must not be pushed past their
quasi-static validity — that is the one hard limitation to know.

| Engine | Method | Validated / usable range | Upper-limit cause | Lower-limit cause |
|---|---|---|---|---|
| **Palace** | full-wave FEM | **validated to 57 GHz** (cavity TE101 +0.002 % @ 56.9 GHz, +0.003 % @ 39.0 GHz; WR-22 driven 38–42 GHz, |S11| −106 dB) | mesh element size ∝ λ → memory/time (no physics break) | driven/eigenmode are f > 0; true DC statics is a different formulation |
| **openEMS** | EC-FDTD | broadband in one run; validated point 2.435 GHz (patch); mmWave feasible | grid cell < ~λ/20 → memory/time | very low f needs long settling (~MHz practical floor) |
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
`element_designer.py`; gui_smoke 24 checks / 33 commands.

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
**Geographic coverage/propagation** (§6) remains a design spec — see
[ROADMAP](ROADMAP.md) §5–§6.

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
UI (the dialog is S2). Gate `tests/validation/system_matching.py` (77 checks,
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
(no finite-Q path yet). Engine only — Qt-free, no UI. Gate
`tests/validation/system_filters.py` (35 checks, pure python3) reproduces the
Phase-B anchors to the digit and was mutation-tested (8 deliberate engine
breakages, 8 caught).

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
(command `EMStudio_ArrayDesigner`): N parallel dipoles, named drive
distributions (broadside · end-fire · Hansen-Woodyard · scanned · cardioid
pair), derived target-current table, predicted read-outs, and a live Verify
(N+1 NEC2 runs off-thread) overlaying the achieved azimuth cut with the drive
table — EX voltages, per-element ACTIVE impedance and power, with warnings on
a negative driving-point resistance (superdirective, not passively
realizable) and negative per-element power. Honest behaviour: per-element
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

**Later §7 slices — RF direction finding (S6) and the System group (S7) —
remain planned** (see [ROADMAP](ROADMAP.md)).

## Antennas & RF

| Capability | Status | Backend | Evidence |
|---|---|---|---|
| S11 / reflection | ✅ validated | openEMS, NEC2 | patch −29 dB @ 2.435 GHz vs tutorial |
| VSWR | ✅ | derived | — |
| Input impedance R+jX | ✅ validated | openEMS, NEC2 | dipole 71.9 Ω at resonance |
| Resonance detection | ✅ | derived | dipole 296 MHz |
| Touchstone (.s1p) export | ✅ | — | — |
| **Far-field radiation pattern** | ✅ validated | openEMS NF2FF, NEC2 RP | dipole 2.13 dBi + axial null; patch 6.6 dBi; full sphere 37×72 |
| **3-D pattern balloon (rotate/zoom/pan)** | ✅ validated (v0.72.0) | mplot3d tab + FreeCAD viewport object; reachable from Results, Element Designer and Array Designer | `pattern_vtu.py`: 27 checks — radius follows the gain law pointwise, phase-centre registration, closed-phi wrap, read back by our own VTU parser; mutation-tested 7/7 |
| **3-D currents / field plane in viewport** | ✅ validated (v0.72.0) | FemPostPipeline VTU | `pattern_vtu.py`: polyline cell + m→mm + mA conversion; quad cells, fixed-axis offset, dB self-normalisation |
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
| Nonlinear B-H waveform accuracy (AC), hysteresis | ⛔ planned | harmonic B-H is amplitude-approximation only; transient B-H verified working (BDF2 probe) — exposure is a small future slice; hysteresis (TEAM 32 class) not planned |

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

## Deliverables

| Capability | Status |
|---|---|
| Professional PDF reports (antenna + litz + **magnetics**) | ✅ validated |
| Spec / BOM / construction schedule | ✅ |
| CSV / Touchstone / pattern data export | ✅ |

## Roadmap for the gaps

1. ~~**Trace-aware meshing** → validated PCB/microstrip S-parameters~~ **DONE v0.16.0**
   (notch-filter template on the toolbar, gate green). Next PCB items: general
   microstrip circuits (bends, couplers, multi-stub filters), Zc renormalization,
   Palace **lumped ports** as a second (FEM) PCB S-parameter route.
2. **Palace depth**: the GPU path; lumped ports on general BREP (wave ports already
   do general BREP as of v0.21.0). (Fast frequency sweep, adaptive mesh refinement,
   and general-BREP driven wave ports all shipped.)
3. **Magnetics depth** (v0.51–0.55: radiation BC, k(T), σ(T)-coupled Joule,
   nonlinear B-H + Static-DC, and the general 3-D WhitneyAV ENGINE with the
   TEAM-7 measured gate all shipped): next — 3-D GUI wiring (FreeCAD-solid
   import via BREP, template + command), transient-B-H exposure,
   ferrite/shield WPT variants.
4. Near-field at the resonant frequency (currently the sweep center); 3-D field
   volumes; animated fields.
