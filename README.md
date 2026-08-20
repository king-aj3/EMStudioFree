# EMStudio — RF & Electromagnetic Simulation for FreeCAD

**A free FreeCAD workbench that makes RF / antenna / wire electromagnetic
engineering approachable**: guided workflows, real calculations, automatic
meshing, validated solvers, and professional outputs (Touchstone, radiation
patterns, build specs and BOMs).

> 🎓 **For educational, hobbyist and experimental use — and under active
> development.** EMStudio is a learning and exploration tool, not a certified
> engineering product, and not a substitute for qualified engineering,
> measurement or compliance work. Features, defaults and results may change
> between versions.

> ⚠️ **No warranty, no liability — verify everything independently.** EMStudio's
> outputs are engineering **estimates** that can be wrong. You are solely
> responsible for independently verifying every result before any reliance, for
> regulatory/RF-safety compliance, and for anything built or operated from these
> outputs. Provided AS IS; the author, contributors and the AJJ³ project accept
> **no responsibility and no liability** for any damage, injury, loss,
> interference or cost. **Read [DISCLAIMER](DISCLAIMER.md) before use** — it
> is also in the app under **EMStudio → Help → Legal notice & disclaimer**.

> ™ **Names and branding.** The code is LGPL-2.1-or-later; the **EMStudio** and
> **AJJ³** names, logo and icon set are **not** licensed with it. Forks and
> modified redistributions must rename and remove AJJ³ branding — see
> [TRADEMARK](TRADEMARK.md).

---

## What it does

A guided workflow — **geometry → materials → ports/boundaries → mesh → solve →
results** — driving established open-source solvers as isolated subprocesses.
No solver code is linked or bundled; each runs under its own licence.

| Backend | Method | Used for |
|---|---|---|
| **nec2c** | MoM | wire antennas, ground models, transmission lines |
| **openEMS** | FDTD | full-wave 3-D antennas, PCB/microstrip S-parameters |
| **Elmer** | FEM | magnetics (2-D axisymmetric + general 3-D), thermal |
| **AWS Palace** | FEM | cavity eigenmodes, driven wave/lumped ports |

### Antennas and elements
The **Element Designer** turns requirements into a dimensioned design: a
rule-based family recommender with printed rationale, then synthesis for
**wire** (dipole / monopole / folded / λ-fractions on an end-effect curve
measured on our own NEC2), **Yagi-Uda** (NBS TN-688 — within ±0.25 dB of the
paper's measured gains on live NEC2), **microstrip patch** (transmission-line
synthesis, openEMS-verified to −2.8 % at 2.4 GHz) and **LPDA** (Carrel on the
corrected Butson-Thompson contours, crossed feeder modeled with real NEC2 TL
cards). Plus 20 source-verified service presets, an in-dialog
predicted-vs-achieved verify, Accept→Generate to a runnable analysis, and PDF
build reports with a dimensioned sketch and element schedule.

Also: **VLF/LF/MF small-antenna analytics** — top-loading capacitance (hats,
flat-tops, T/inverted-L), a radial-ground estimator with radial-count
optimizer, voltage-limited power/bandwidth design, the efficiency ladder, Chu
Q/bandwidth — and NEC2 monopoles over perfect or finite Sommerfeld earth.

### Cables and wire
The **Cable Designer** covers litz (industry Types 1–9, FastHenry-validated
loss physics), coax (analytic TEM vs the RG-58/RG-142 datasheets, with a Palace
full-wave verify), single wire (exact Kelvin skin effect), twisted pair
(differential Z₀/VF vs the Cat5e/Cat6 datasheets) and multi-design bundles
(exact tangency packing, method-of-moments crosstalk). With a thermal tab:
steady and transient temperature, ampacity per insulation class, and adiabatic
short-circuit.

### Magnetics
The full Elmer arc — induction heating with a steady and transient thermal
chain (radiation BC, k(T), σ(T)-coupled Joule), nonlinear B-H iron with a
Static DC saturation mode, wireless-power coil coupling L/M/k, and **general
3-D magnetostatics on any solid — closed OR open**. A conductor with free
ends (a C-shape, a hairpin, an un-joined helix) is driven through its two
terminal faces, which EMStudio finds and then tells you about. Validated to
−0.6 % against closed-form coil fields, **2.83 % RMS against the measured
TEAM Problem 7 benchmark**, and −0.79 % for an open split ring against the
exact arc field.

### Propagation, coverage and EMC
Point-to-point link budgets (free-space, ITU-R P.526 knife-edge, two-ray
plane-earth), DEM import (SRTM `.hgt` and GeoTIFF, no GDAL) with
terrain-shadowed area coverage maps and KML export, LF/MF ground-wave (ITU-R
P.368 flat earth plus the P.368-10 spherical-earth NTIA LFMF port with
Millington mixed paths), the vendored **ITU-R P.1546-6 / P.1812-6 / P.452-18 /
P.2001-6** reference implementations, multi-station D/U service planning, and
**co-site interference** — intermodulation, receiver desensitization, a
frequency-plan optimizer and a NEC2 antenna-to-antenna isolation matrix.

## Validated, not just plausible

Every physics feature ships with an automated gate against literature,
closed-form results, or an independent solver — and **those gates are in this
repository**, not held back. The dipole reads 71.9 Ω because a dipole *is*
~72 Ω.

```bash
python3 tests/smoke.py                        # Qt-free subset
freecadcmd tests/smoke.py                     # full, under FreeCAD
python3 tests/validation/run_battery.py       # the FAST validation tier
```

A gate passing means those specific cases reproduced those specific reference
values, on the developer's machine, at that time. It is **not** a guarantee of
accuracy for your case — see [DISCLAIMER](DISCLAIMER.md).

## Install

Requires FreeCAD 0.21 or newer (1.x recommended). Install through the FreeCAD
**Add-on Manager**, or manually:

```bash
git clone https://github.com/king-aj3/EMStudioFree.git \
  ~/.local/share/FreeCAD/Mod/EMStudio
```

Restart FreeCAD and pick **EMStudio** from the workbench dropdown. Then use
**EMStudio → Setup → Detect / Install Solvers** — it reports what is present
and gives you a single install command for what is missing. The workbench runs
without any solver installed; the analytic tools work regardless.

Solver Setup is platform-aware: `apt` on Debian/Ubuntu/Mint, `brew` on macOS,
and on **Windows a one-click Install… button** for the backends whose binaries
can be distributed — **NEC2, Elmer and Gmsh**. Those download into
`%LOCALAPPDATA%\EMStudio\solvers\`, per-user, with no admin rights and no
shell, and are detected without touching `PATH`. openEMS and Palace still need
WSL2; FastHenry is built from source — Solver Setup's **Build…** button
automates the compile when a MinGW toolchain is present (FastFieldSolvers'
own Windows bundle ships a GUI/Automation FastHenry2 that EMStudio cannot
drive as a subprocess). Its licensing is resolved — the 2003 M.I.T.
re-release permits redistribution and FastFieldSolvers state their
modifications are LGPL — and a one-click Install of an EMStudio-built CLI
binary is prepared, shipping once M.I.T.'s licensing office confirms the
2003 re-release.

**On macOS**, run `xcode-select --install` first — several solvers have no
Homebrew formula and are built from source. Detection looks in
`/opt/homebrew/bin` (Apple Silicon), `/usr/local/bin` (Intel) and
`/opt/local/bin` (MacPorts) as well as on `PATH`, so a brew-installed solver is
found even though FreeCAD launched from Finder does not inherit your shell
profile. If something is installed somewhere else entirely, set its path
explicitly in the preferences or via `EMSTUDIO_<BACKEND>`.

## Documentation

[docs/TUTORIALS](docs/TUTORIALS.md) — **start here**: tutorials that each end in a number you can check ·
[HELP](HELP.md) — every command, at a glance ·
[docs/USER_MANUAL](docs/USER_MANUAL.md) — the full reference ·
[ABOUT](ABOUT.md) — what this is for ·
[CONTRIBUTING](CONTRIBUTING.md) — how to help, and the CLA ·
[DISCLAIMER](DISCLAIMER.md) · [TRADEMARK](TRADEMARK.md)

## EMStudio Pro — available now, $149

A separate add-on adds the **System Designer**: impedance-matching synthesis,
filter and diplexer design, phased arrays with amplitude tapers, and RF
direction finding, plus the AI assistant. **This workbench stays free and keeps
all of its validation gates** — Pro is what you need when one antenna becomes a
*system*, not "the useful half".

**$149 one-time, perpetual, no subscription and no account.** Buy at
[ajj3us.gumroad.com](https://ajj3us.gumroad.com), then install it from
**EMStudio → Help → EMStudio Pro — install / activate**. Details and the
measured numbers behind it: [docs/PRO](docs/PRO.md) · [ajj3.us](https://ajj3.us)

## Licence

LGPL-2.1-or-later — see [LICENSE](LICENSE). The solvers it drives are separate,
unmodified programs under their own licences. An **AJJ³** project.
