# EMStudio — RF & Electromagnetic Simulation for FreeCAD

**A free FreeCAD workbench that makes RF / antenna / wire electromagnetic engineering
simple**: guided workflows, real-world calculations, automatic meshing, validated
solvers, professional outputs (Touchstone, radiation patterns, litz build
specs/BOMs). A free alternative to CENOS RF, aiming at the Ansys HFSS feature
vocabulary over time.

> 🎓 **For educational, hobbyist and experimental use — and under active
> development.** EMStudio is a learning and exploration tool, not a certified
> engineering product, and not a substitute for qualified engineering,
> measurement or compliance work. Features, defaults and results may change
> between versions. More to come.

> ⚠️ **No warranty, no liability — verify everything independently.** EMStudio's
> outputs are engineering **estimates** that can be wrong. You are solely
> responsible for independently verifying every result before any reliance, for
> regulatory/RF-safety compliance, and for anything built or operated from these
> outputs. Provided AS IS; the author, contributors and the AJJ³ project accept
> **no responsibility and no liability** for any damage, injury, loss,
> interference or cost. **Read [DISCLAIMER.md](DISCLAIMER.md) before use** — it
> is also in the app under **EMStudio → Help → Legal notice & disclaimer**.

> ™ **Names and branding.** The code is LGPL-2.1-or-later; the **EMStudio** and
> **AJJ³** names, logo and icon set are **not** licensed with it. Forks and
> modified redistributions must rename and remove AJJ³ branding — see
> [TRADEMARK.md](TRADEMARK.md).

> **Status:** v0.68.0 — working and validated. Wire antennas (NEC2), full-wave 3-D
> antennas and S-parameters (openEMS), far-field patterns, STL import, **validated
> microstrip/PCB S-parameters** (trace-aware meshing — a notch-filter template whose
> S21 notch matches analytic theory to 0.6%), a **Cable Designer** (Litz industry
> Types 1–9 with FastHenry-validated loss physics · analytic **coax TEM** vs the
> RG-58/RG-142 primary datasheets with a Palace full-wave verify · single wire
> with exact Kelvin skin effect · **twisted pair** — differential Z0/VF vs the
> Cat5e/Cat6 100 Ω primary datasheets, UTP/STP · **multi-design bundles** —
> exact tangency packing, OD/fill), **Elmer FEM magnetics**
> (induction heating with steady + transient thermal chain — radiation BC,
> k(T), σ(T)-coupled Joule — vs the exact Bessel/1-D
> solutions, **nonlinear B-H iron** with a Static (DC) saturation/L(I) mode,
> wireless-power coil coupling L/M/k vs Grover/Maxwell formulas, and a
> **general 3-D magnetostatics on ANY solid** — one-click 3-D Solenoid
> template, B-field maps in the viewport; validated to −0.6 % against
> closed-form coil fields and **2.8 % RMS against the measured TEAM
> Problem 7 benchmark**),
> and **Palace full-wave FEM** — resonant-cavity eigenmodes (rectangular **and
> cylindrical/general 3-D via BREP**, vs closed-form and Bessel modes), driven
> **wave-port** (waveguide) and **lumped-port** (coax) S-parameters (with an
> **adaptive fast frequency sweep** — a dense band from a handful of full solves —
> and opt-in **adaptive mesh refinement** that spends elements only where the error
> is), all sub-percent vs theory.
>
> Plus a growing set of **system-level** tools, each with an honest validated regime:
> the **Element Designer** — requirements → a recommended family with a printed
> rationale, wire synthesis (dipole/monopole/folded/λ-fractions on an end-effect
> curve **measured on our own NEC2**), **NBS TN-688 Yagi-Uda synthesis** (gain or
> boom length → a dimensioned Yagi, ±0.25 dB vs the measured gains on NEC2), and
> **transmission-line microstrip-patch synthesis** (frequency + substrate → W/L/
> feed, openEMS-verified to −2.8 % / 6.88 dBi at 2.4 GHz), and **Carrel LPDA
> synthesis** (band + gain → a dimensioned log-periodic on the corrected
> Butson-Thompson contours, its crossed feeder modeled with real NEC2 TL cards —
> live-verified VSWR ≤ ~1.2 median across 54-216 MHz, ~8.5 dBi, F/B ~20 dB), an
> in-dialog NEC2/openEMS predicted-vs-achieved verify, and Accept→Generate to a
> runnable analysis, plus **20 source-verified service presets** (broadcast /
> aviation / marine / ham / ISM / LoRa / Wi-Fi / GPS) and **PDF build reports**
> (dimensioned sketch + element schedule);
> the **System Matching Designer** — takes an element's feed Z (typed R+jX or a live
> NEC2 sweep) and synthesizes the impedance-matching network: **L / pi / T /
> quarter-wave / binomial / single-stub / hairpin** topologies with a **recommender**
> that ranks the applicable ones, predicted VSWR/return-loss/insertion-loss curves, a
> live NEC2 **predicted-vs-achieved** verify, **E-series** standard-value snapping, and
> a two-page **PDF matching report**;
> **filter and diplexer synthesis** — Butterworth/Chebyshev lowpass, highpass,
> bandpass and bandstop ladders from a ripple/order or an attenuation spec, plus a
> **contiguous constant-resistance diplexer** (composite common-port impedance is R0 at
> every frequency, to <1e-6 Ω) and a **band-splitting UVSJ diplexer** whose assembled
> 3-port match, through loss and port-to-port isolation are solved rather than
> estimated (0.112 dB / VSWR 1.38 / 34.8 dB isolation on the 144-439 MHz case, the
> regime of measured hardware) — engine today, dialog to come;
> the **Array Designer** — a linear phased array driven the honest way: you specify
> element **currents** (broadside / end-fire / Hansen-Woodyard / scanned / cardioid),
> EMStudio extracts the **mutual-impedance matrix** on live NEC2, solves **V = Z·I**
> for the port voltages, and verifies with one multi-excitation run — achieved
> currents land at the solver's print precision, and a quadrature cardioid measures
> **29.6 dB front-to-back where the naive equal-voltage drive gets 3.4 dB**; with
> per-element active impedance and power, superdirective-drive warnings, and
> predicted-vs-achieved pattern cuts — plus **amplitude tapers** (binomial ·
> exact **Dolph-Chebyshev** · **Taylor n̄**) that measurably work on the live
> solve: the Dolph-tapered steered array reproduces its **−26.0 dB design floor
> to 0.04 dB where the uniform drive shows −12.7 dB**, scan-loss/beam-broadening read-outs, planar and
> circular array factors, and pattern export straight into the coverage tools;
> **VLF/LF/MF small-antenna analytics** (top-loading capacitance — hats,
> flat-tops, T/inverted-L — with measured-model-verified constants, a
> radial-ground-system estimator + radial-count optimizer, voltage-limited
> power/bandwidth design, the canonical efficiency ladder,
> short dipole/monopole/loop Rr, effective
> height, Chu Q/bandwidth) + **NEC2 monopole over ground** (perfect / finite
> Sommerfeld earth) and a band→method picker; **co-site interference / EMC** —
> intermodulation, receiver desensitization, broadband noise, a frequency-plan
> optimizer, and a NEC2 antenna-to-antenna **isolation matrix**; and **geographic
> coverage / propagation** — point-to-point link budgets (free-space, ITU-R P.526
> knife-edge, two-ray plane-earth, field strength), **DEM import** (SRTM `.hgt` +
> GeoTIFF, no GDAL) with terrain-shadowed **area coverage maps** and **KML** export,
> the **LF/MF ground-wave models** (ITU-R P.368 flat earth + the **P.368-10
> spherical-earth NTIA LFMF port** to 10000 km, with Millington mixed paths), and
> the vendored **ITU-R P.1546-6 / P.1812-6 / P.452-18 / P.2001-6 reference
> implementations** (official validation sets replayed to 0.000000 dB /
> 1e-9-dB class; ITU digital maps installed on demand, never bundled).
> A guided solver-install wizard and build-house **PDF reports** (antenna / litz /
> magnetics) round it out.

## What you can do today

- **Wire antennas in seconds** — dipole template → S11/VSWR/impedance + polar gain
  pattern. Validated: 71.9 Ω feedpoint, 2.13 dBi (textbook: ~73 Ω, 2.15 dBi).
- **Match an element to your system** — the **System Matching Designer** takes an
  element's feed Z (typed R+jX or a live NEC2 sweep) and synthesizes the
  impedance-matching network: **L / pi / T / quarter-wave / binomial / single-stub /
  hairpin** topologies, a **recommender** that ranks the applicable ones with a printed
  rationale, predicted VSWR/return-loss/insertion-loss curves, a live NEC2
  **predicted-vs-achieved** verify, **E-series** standard-value snapping, and a two-page
  **PDF matching report**. Validated: the shipped 300 MHz dipole (~71.9 Ω) matched to
  50 Ω → achieved VSWR ~1.01 (bare antenna 1.43).
- **Full-wave 3-D simulation** — patch template or your own geometry → automatic
  FDTD meshing → S-parameters + far fields. Validated against the published openEMS
  reference antenna (−29 dB @ 2.435 GHz, 6.6 dBi boresight).
- **Analyze STLs directly** — imported meshes go straight to the solver, no
  conversion. Validated: identical resonance through the STL path.
- **Design cable — Litz, coax, or single wire** in one Cable Designer. Litz: all 9
  industry construction types with true manufacturing
  build-up: AWG/mm/mil sizing, per-level lay length + S/Z direction, **multi-level
  fiber cores** (snug-ring auto sizing), **member tape wraps and overall jacket**
  (Type-6 default 1/8″ PVC), live cross-section drawing, Rac/Rdc curves (exact skin
  effect + FastHenry-anchored proximity, isolated or in-winding), **per-strand
  current-sharing analysis** (twist quality as a number), supplier-ready spec/BOM
  export, and profile export into FreeCAD for sweeps/lofts. **Coax**: analytic TEM
  Z0/VF/C′/L′/TE11-cutoff and conductor+dielectric attenuation, validated against
  the RG-58/RG-142 **primary datasheets** (Belden 8262 50.0 Ω / 101 pF/m via the
  stranded-centre effective diameter), with a one-click **Palace full-wave verify**
  (RG-58 reference: |S11| −31 dB matched, full-wave VF within 0.1 % of 1/√εr).
  **Single wire**: exact Kelvin skin-effect Rac/Rdc, Rdc, insulation, ampacity.
  **Twisted pair**: differential/odd-mode Z0 from the exact two-wire line +
  the Lefferson twist/insulation permittivity model, UTP or shielded (STP),
  validated against the Cat5e/Cat6 primary datasheets (**Cat6 geometry →
  99.9 Ω vs the 100 ± 15 Ω band**), Miller's exact shielded-pair solution and
  the classic Lefferson worked examples. **Bundle**: pack any member mix
  (coax + pairs + wires) with exact tangency packing (7 equal members → OD
  exactly 3×, fill 7/9), jacket, fill/OD/weight report and spec — plus
  **member-to-member crosstalk** (Paul's weak-coupling model, validated to
  the digit against his printed ribbon-cable benchmark) from analytic
  wide-separation L/C matrices or FastHenry loop matrices at any spacing;
  **insulated members use a method-of-moments capacitance solve** (Paul's
  RIBBON.FOR method — reproduces his printed insulated-ribbon C to the digit
  and the independent US-gov GETCAP tables to 4e-8); **differential
  pair-to-pair coupling** (mixed-mode reduction: k_diff, the ASTM D4566
  capacitance unbalance CUPP, Zdd and differential NE/FE crosstalk gated to
  12-digit full-MTL oracle anchors, with the RADC-TR-76-101 twisted-pair
  model — odd-N twist envelope, capacitive floor, balance null).
- **Per-bundle current sharing** — aggregated twist-quality metric for any
  paralleled conductors; **ampacity estimate** from a surface heat balance.
- **Cable thermal analysis (Thermal tab)** — steady conductor temperature
  and **ampacity** of any wire/litz construction in free air (IEC 60287
  radial ladder + Churchill-Chu convection + radiation, worked-example-
  gated; ampacity lands inside the NEC/MIL/datasheet bands), transient
  heating curves, IEC 60949 adiabatic short-circuit ratings, NEC bundle
  derating, and **coax RF average-power ratings validated 90-125 % against
  the Times LMR-240 catalog table**. Visuals: temperature-colored
  cross-section and a 2-D **film + buoyant-plume field showing how the
  heat dissipates around and rises above the cable** (laminar similarity
  solution, constants re-derived in the validation gate).
- **Induction heating & wireless power** — coil + billet template → workpiece
  Joule power, coil L and reflected R, **steady-state and transient temperature**
  (the heating curve over time), B-field in the 3-D viewport; WPT coil-pair
  template → inductance matrix and coupling k. Elmer FEM (axisymmetric harmonic
  magnetodynamics + heat), validated sub-percent against analytic solutions.
- **VLF/LF/MF small antennas** — the electrically-small regime the field solvers
  can't reach: closed-form radiation resistance, effective height, efficiency, Chu
  Q/bandwidth and loading for short monopoles/dipoles/loops, a NEC2 **monopole over
  ground** (perfect or finite Sommerfeld earth), and a band→method picker that routes
  each frequency to the tool that is actually valid there.
- **Co-site interference / EMC** — over a list of co-located radios: intermodulation
  products + intercept-point levels, receiver desensitization, broadband transmitter
  noise, frequency-plan clashes, a **frequency-plan optimizer**, and a NEC2
  antenna-to-antenna **isolation matrix**.
- **Coverage & propagation** — point-to-point **link budgets** (free-space, ITU-R
  P.526 knife-edge, two-ray plane-earth, field strength), **DEM import** (SRTM
  `.hgt` + GeoTIFF, no GDAL) driving terrain-shadowed **area coverage maps**
  (single- or **multi-edge** Deygout / Epstein–Peterson diffraction, validated vs
  NTIA TR-26-580) with **KML** export, the **LF/MF ground-wave** models (ITU-R P.368 flat earth
  + the **P.368-10 spherical earth** — a validated numpy/scipy port of the NTIA
  LFMF reference implementation, 0.01–30 MHz out to 10000 km — with Millington
  mixed paths), the vendored **ITU-R P.1546-6** point-to-area, **P.1812-6**
  path-specific, **P.452-18** interference and **P.2001-6** wide-range
  reference models (official ITU validation sets replayed at the 1e-6-dB
  class or better; the ITU digital maps install on demand from the official
  itu.int zips — never bundled), the **Okumura-Hata / COST-231** empirical
  land-mobile models, and **multi-station service/interference (D/U) contours** (compose
  transmitters, threshold the wanted/unwanted field ratio against FCC/ITU protection
  ratios → served / interference-limited / no-service + best-server view).
- **Professional PDF reports** — one build-house-ready document per analysis:
  summary, geometry/construction drawing, result curves, and BOM/schedule.
- **Export professional artifacts** — Touchstone `.s1p`, CSV sweeps, pattern data,
  Markdown build sheets, PDF reports.

Results views: **S-parameters** (S11 + multi-port S21), VSWR, impedance, **radiation
pattern**, **current distribution**, and **near-field \|E\| maps** — plus Touchstone,
CSV, and PDF export. See the honest per-feature [capability matrix](docs/CAPABILITIES.md).

**[→ User Manual with step-by-step tutorials](docs/USER_MANUAL.md)** ·
[Capabilities](docs/CAPABILITIES.md) · [Quick help](HELP.md) ·
[About/mission](ABOUT.md) · [Changelog](CHANGELOG.md)

## Install (development)

Requires FreeCAD 0.21+ (1.x recommended). Link the repo into FreeCAD's user
`Mod` directory, then restart FreeCAD. FreeCAD ≥ 1.1 uses version-suffixed user
dirs (`v1-1`), so each installed FreeCAD version needs its own link.

**Linux:**

```bash
ln -sfn "$PWD" ~/.local/share/FreeCAD/Mod/EMStudio          # FreeCAD <= 1.0
ln -sfn "$PWD" ~/.local/share/FreeCAD/v1-1/Mod/EMStudio     # FreeCAD 1.1 (versioned dirs)
```

**Windows** (PowerShell — a directory *junction*, which needs no admin rights.
A desktop shortcut/`.lnk` does NOT work; FreeCAD ignores it):

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\FreeCAD\Mod", "$env:APPDATA\FreeCAD\v1-1\Mod" | Out-Null
New-Item -ItemType Junction -Path "$env:APPDATA\FreeCAD\Mod\EMStudio"      -Target "$PWD"   # FreeCAD <= 1.0
New-Item -ItemType Junction -Path "$env:APPDATA\FreeCAD\v1-1\Mod\EMStudio" -Target "$PWD"   # FreeCAD 1.1
```

(Copying the repo folder into `Mod\EMStudio` also works, but a junction keeps
the checkout live-editable.)

Pick **EMStudio** from the workbench dropdown and click **Detect Solvers** — it
reports what's installed and how to add what's missing, with per-platform
guidance (apt/source builds on Linux; native installers or WSL2 on Windows).

### Solver backends

EMStudio never links or bundles solver code — it writes input decks and runs each
solver as a subprocess (the same licensing model CENOS uses commercially).

| Backend | Method | Use | Install (Linux) | Install (Windows) |
|---|---|---|---|---|
| **NEC2** (`nec2c`) | MoM | wire antennas | `sudo apt install nec2c` | WSL2 (no official native build) |
| **openEMS** | EC-FDTD | 3-D antennas, S-params, patterns | source build¹ | prebuilt zip from openems.de, or WSL2 |
| **FastHenry** | PEEC | wire/litz bundle impedance | source build² | FastFieldSolvers Windows build |
| **Elmer** + **Gmsh** | FEM | magnetics (induction, WPT coupling) | `elmerfem-csc` | native installers (elmerfem.org, gmsh.info) |
| **Palace** | FEM | full-wave (eigenmodes, driven S-params, AMR) | source/Spack build | WSL2 only |

¹ openEMS was dropped from Ubuntu 24.04+ archives:
`git clone --recursive https://github.com/thliebig/openEMS-Project.git`, then
`./update_openEMS.sh ~/opt/openEMS --python` inside a venv (build deps: see
`Detect Solvers` hint or docs/USER_MANUAL.md).

² `git clone https://github.com/ediloren/FastHenry2.git && cd FastHenry2/src/fasthenry
&& make fasthenry CFLAGS="-O -DFOUR -m64 -fcommon"`

## Validation-first

Every physics feature lands with an automated gate (real numbers, honest exit codes):

```bash
freecadcmd tests/smoke.py                        # workbench health (Qt-free engine checks)
python3 tests/validation/run_battery.py          # the FAST gate battery (17 gates, ~40 s — CI runs this on every push)
python3 tests/validation/run_battery.py --all    # + the SOLVER tier (needs the backends; pre-release)
freecadcmd tests/validation/dipole_nec2.py       # 71.9 ohm / 2.13 dBi vs literature
freecadcmd tests/validation/monopole_nec2.py     # VLF/LF monopole over ground (NEC2 + GN card)
freecadcmd tests/validation/isolation_nec2.py    # co-site antenna isolation matrix (NEC2 Y-matrix)
freecadcmd tests/validation/patch_openems.py     # 2.435 GHz vs published reference
freecadcmd tests/validation/patch_stl_openems.py # STL path, same resonance
freecadcmd tests/validation/msl_notch_openems.py # microstrip notch S21 vs analytic (~40 s)
python3   tests/validation/wire_fasthenry.py     # litz model vs FastHenry field solver
~/opt/openEMS/venv/bin/python tests/validation/isolation_openems.py        # co-site isolation, openEMS vs Balanis + NEC2 (on-demand)
~/opt/openEMS/venv/bin/python tests/validation/isolation_patch_openems.py  # coupled-patch benchmark (release tier, on-demand)
python3   tests/validation/wire_current_sharing.py  # sharing + ampacity gates
python3   tests/validation/induction_elmer.py       # eddy power / temperature / heating curve vs analytic
python3   tests/validation/wpt_elmer.py             # coil L/M/k vs Grover/Maxwell
python3   tests/validation/report_pdf.py            # PDF report generation
python3   tests/validation/cavity_palace.py         # Palace box cavity modes vs closed form
python3   tests/validation/cylcavity_palace.py      # Palace cylindrical (BREP) eigenmodes vs Bessel
python3   tests/validation/waveguide_palace.py      # Palace WR-90 S-params vs TE10 theory
python3   tests/validation/coax_palace.py           # Palace coax lumped-port S-params (Z0 49.94 ohm)
python3   tests/validation/fastsweep_palace.py      # Palace adaptive fast frequency sweep
freecadcmd tests/validation/amr_palace.py           # Palace adaptive mesh refinement (AMR)
freecadcmd tests/validation/circwaveguide_palace.py # Palace general-BREP driven wave ports
python3   tests/validation/mmwave_palace.py         # Palace full-wave at ~40 GHz and up
python3   tests/validation/freq_guard.py            # quasi-static frequency-validity guard
python3   tests/validation/small_antenna.py         # VLF/LF small-antenna analytics + band picker
python3   tests/validation/cosite.py                # co-site interference (IMD/desense/D-U + optimizer)
python3   tests/validation/propagation.py           # point-to-point path loss (FSPL/knife-edge/plane-earth)
python3   tests/validation/coverage.py              # DEM import + coverage heatmap + KML + LF/MF ground-wave + multi-station D/U
python3   tests/validation/lfmf.py                  # P.368-10 spherical-earth ground wave (2497-pt oracle grid + official examples)
python3   tests/validation/p1546.py                 # ITU-R P.1546-6 official validation set (0.000000 dB)
python3   tests/validation/p1812.py                 # ITU-R P.1812-6 + delta-Bullington official validation set (0.000000 dB)
python3   tests/validation/p452.py                  # ITU-R P.452-18 official CG-3M validation set (595 cases; needs ITU maps installed)
python3   tests/validation/p2001.py                 # ITU-R P.2001-6 official validation set (4430 cases; needs ITU maps installed)
QT_QPA_PLATFORM=offscreen freecad tests/gui_smoke.py # real-GUI solve loops (bbox-safe)
```

## License

[LGPL-2.1-or-later](LICENSE). Solver backends keep their upstream licenses and run
as separate processes.

## Documentation map

[docs/USER_MANUAL.md](docs/USER_MANUAL.md) — tutorials ·
[docs/PLAN.md](docs/PLAN.md) — phased implementation plan ·
[docs/ROADMAP.md](docs/ROADMAP.md) — big-ticket epics (§1 element designer … §7 system designer) ·
[docs/RESEARCH_REPORT.md](docs/RESEARCH_REPORT.md) — competitive research ·
[docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md) — decision log
