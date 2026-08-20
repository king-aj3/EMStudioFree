# EMStudio Tutorials — start here

Every tutorial below ends in **a number you can check**, and names the
automated test that pins it. That is the point of the series: you should not
have to take anyone's word for what this tool does, least of all mine.

They are ordered by **what you need installed**, not by topic. The first one
needs nothing but the workbench. Nothing here is a video — each is a document
that ships with EMStudio, a button, and a number.

> **New here?** Do #1 and #2 in that order. Together they take about ten
> minutes and they answer "does this thing work" honestly.

---

## How to read a tutorial

Each has the same four parts:

| part | what it is |
|---|---|
| **Needs** | what must be installed. "Nothing" means the workbench alone. |
| **Do** | the clicks, in order. |
| **You should see** | the number, with the range the automated test allows. |
| **Prove it** | the validation gate that asserts the same thing, so you can re-run the check yourself rather than trusting the screenshot. |

⚠ **Ranges, not point values.** A solver on your machine, your mesh and your
version will not reproduce a reference run to the last digit, and a tutorial
that implies it would be lying. Each "you should see" quotes the **gate window**
— the range the project guarantees — and the reference measurement inside it.

⚠ **Run the gates yourself.** Everything in the free workbench is checked by
tests that ship with it:

```bash
git clone https://github.com/king-aj3/EMStudioFree
python3 tests/validation/run_battery.py        # the FAST tier, no solver needed
```

The heavier benchmarks (TEAM Problem 7, the NBS Yagis, the full-wave runs) are
in the **SOLVER tier** and need the backends installed:
`python3 tests/validation/run_battery.py --all`.

---

# The tutorials

## 1. A Yagi from requirements, with no solver at all

**Needs:** nothing. The Element Designer is analytic — no backend, no install.

**Do**
1. **EMStudio ▸ Tools ▸ Element Designer**.
2. Family **Yagi-Uda**, design frequency **400 MHz**, boom **0.8 λ**.
3. Read the table it prints, then **Create** to drop the real geometry into
   your document.

**You should see** a forward gain near **9.2 dBd**. That figure is not ours: it
is the measured gain for a 0.8 λ boom in **NBS Technical Note 688**, the
standard reference for Yagi design, and the synthesiser is built from its
tables. The gate allows **8.3–9.9 dBd** and requires front-to-back **> 10 dB**.

**Prove it** — `tests/validation/yagi_nec2.py`. It solves the synthesised
geometry in NEC2 and checks it against TN-688 across **four boom classes**
(measured 7.1 / 9.2 / 10.2 / 12.25 dBd), agreeing to **±0.25 dB**.

⛳ **Why this is first.** It is the shortest path from "I installed a thing" to
"that is a real number from a real reference", and it needs no solver. If this
does not convince you, stop here and you have lost five minutes.

---

## 2. Your first solve: a half-wave dipole

**Needs:** **NEC2**. On Windows: **EMStudio ▸ Setup ▸ Detect / Install
Solvers** has a one-click install. It is a small download.

**Do**
1. Open `examples/dipole_300MHz.FCStd` (it ships with the addon).
2. Switch to the **EMStudio** workbench.
3. Press **Run Solver**. It takes seconds.

**You should see**, in the results window:

| quantity | gate window | reference run |
|---|---|---|
| resonance | 290–303 MHz | 296.3 MHz |
| feed-point R | 64–79 Ω | 71.9 Ω |
| S11 vs 50 Ω | better than −12 dB | — |
| peak gain | 1.9–2.4 dBi | 2.13 dBi |
| pattern | peak broadside, deep null off the wire ends | — |

The textbook half-wave dipole is **73 Ω** and **2.15 dBi**. You are looking at
a solver reproducing a result you already know, which is the only useful way to
start trusting one.

**Prove it** — `tests/validation/dipole_nec2.py`, which asserts every row above
plus the axial null (< −20 dBi) and that the current peaks at the centre of the
wire, not the ends.

---

## 3. A PCB patch antenna, full-wave

**Needs:** **openEMS**. It installs separately — **Setup ▸ Detect / Install
Solvers** tells you whether one is present and gives you the instructions if
not (source build on Linux, prebuilt zip on Windows). There is no one-click
path for openEMS on any platform yet; that is a real gap and it is being said
out loud rather than discovered by you.

**Do**
1. Open `examples/patch_2p4GHz.FCStd` — an inset-fed patch on 1.524 mm
   RO4003-class substrate (εr 3.38).
2. **Run Solver**. This is a real FDTD run: minutes, not seconds.

**You should see** an S11 dip **below −10 dB**, landing in **2.30–2.50 GHz**
against a 2.4 GHz design, and a broadside pattern with peak gain in
**4.5–9.5 dBi**.

⚠ **Expect it to be a little off 2.4 GHz, and know why.** The patch is *sized*
by a transmission-line model that is only good to about **±5 %** on resonance.
That is not a bug in the solver — it is the difference between a synthesis
formula and a full-wave answer, and seeing the gap is the lesson. The full-wave
solve is what settles it.

**Prove it** — `tests/validation/patch_openems.py` (and `patch_stl_openems.py`,
which runs the same patch through the STL import path and must land in the same
window).

**Design your own:** **EMStudio ▸ Templates ▸ Template: Patch Antenna** asks
for frequency, dielectric constant and substrate height, works the dimensions
out from the same model, and sets the analysis up so **Run Solver** works
immediately.

---

## 4. S-parameters, and a `.s2p` for your VNA

**Needs:** **openEMS** (as #3).

**Do**
1. Open `examples/notch_filter_msl.FCStd` — a 50 mm, 0.6 mm-wide microstrip
   line on 0.254 mm RO4350B (εr 3.66) with a quarter-wave stub.
2. On the solver object, tick **`FullSMatrix`**. *(Leave it off and you get a
   correct `.s1p`; see below.)*
3. **Run Solver**, then **Export Touchstone** in the results window.

**You should see** an S21 notch near **3.66 GHz**. The analytic quarter-wave
prediction is **3.683 GHz**; the reference run measured **3.662 GHz**, i.e.
**−0.6 %**. The gate allows **±8 %** against the analytic value and **±3 %**
against the stored reference, and separately requires the result to be
**passive** (max |S| ≤ +0.2 dB) — a full-wave run that quietly produces gain is
the classic silent failure.

⚠ **Read the export button.** It is labelled with the order it can actually
write — `Export Touchstone (.s2p)…` once all four terms exist, `.s1p` when they
do not. Both backends excite **one port per run**, so one excitation gives one
*column* of the S-matrix: S11 and S21, and nothing about S12 or S22.
`FullSMatrix` runs the second excitation. Ask for an order the solve cannot
support and it **refuses and names the missing terms**, rather than mirroring
S21 and zeroing S22 into a file you would then compare against a measurement.

⛳ **It costs one solve per port**, and the run tells you roughly what that will
be before it starts.

**Prove it** — `tests/validation/msl_notch_openems.py` for the notch and
passivity, `touchstone_export.py` and `n_port_smatrix.py` for the export rules
(including that an incomplete matrix is refused).

---

## 5. RG-58, checked against its own datasheet

**Needs:** nothing. The Cable Designer is analytic.

**Do**
1. **EMStudio ▸ Tools ▸ Cable Designer**, **Coax** page.
2. In the preset dropdown (it opens on *Custom geometry*), choose
   **`RG-58C/U (50 ohm, solid PE)`**.

**You should see** numbers you can check against any Belden datasheet without
leaving your chair:

| quantity | what EMStudio reports | the datasheet |
|---|---|---|
| Z0 | **50.0 Ω** (stranded-centre effective diameter) | 50 Ω |
| velocity factor | **66.7 %** | 66 % (solid PE, εr 2.25) |
| capacitance | **≈ 101 pF/m** | Belden 30.8 pF/ft |

⚠ **The physical envelope gives 47.5 Ω, and that is not an error.** RG-58's
centre conductor is *stranded*; using the outer envelope of the strands instead
of the effective diameter is what moves 50.0 to 47.5. The tool reports both,
because the discrepancy is the useful part.

**Prove it** — `tests/validation/cable.py`, which pins all three rows above,
the TEM identity Z0 = √(L′/C′), attenuation scaling exactly as √f, and the same
treatment for RG-142 against its MIL window.

⛳ **Why this one comes early.** EMStudio is not only an antenna tool. The
Cable Designer does litz (Types 1–9), coax, twisted pair and multi-conductor
bundles with crosstalk, ampacity and thermal rise — and it needs no solver
installed at all.

---

## 6. Millimetre wave: a WR-22 waveguide at 40 GHz

**Needs:** **Palace**. **EMStudio ▸ Setup ▸ Detect / Install Solvers** reports
whether one is present.

⚠ **Read this before the numbers, because it is the part people get wrong.**
EMStudio is validated to **57 GHz for CLOSED STRUCTURES** — waveguides and
cavities. It is **not** validated for *antennas* up there: the highest-frequency
radiating structure with a gate behind it is the **2.435 GHz patch** in
tutorial 3. Full-wave Maxwell has no physics break at mmWave — the only real
cost is a finer mesh — but "no reason it should fail" is not the same as
"checked", and this project only claims the second. If you are here for a 28 GHz
patch, this tutorial shows you the solver is sound at that frequency; it does
not show you that we have validated an antenna there.

**Do**
1. Open `examples/waveguide_wr22_40GHz.FCStd`. It is the same waveguide template
   as the WR-90 example, at Ka-band dimensions: **a = 5.69 mm, b = 2.845 mm**,
   10 mm long, swept **38–42 GHz**.
2. **Run Solver**. Palace order 2; expect **under a couple of minutes** on a
   desktop core. ⚠ A single wall-clock figure is wrong on somebody's machine,
   so this series quotes a band rather than a stopwatch reading.

**You should see** a section that behaves like a matched TE10 line:

| quantity | gate window | reference run |
|---|---|---|
| \|S21\| deviation from 0 dB | < 0.05 dB | **5.4e-6 dB** |
| \|S11\| across the band | < −30 dB | **−106 dB** |

**Why those are the right numbers.** WR-22's TE10 cutoff is *c*/2*a* =
**26.34 GHz**, so at 38–42 GHz you are well into propagation: a uniform,
correctly-terminated guide should pass essentially everything and reflect
essentially nothing. \|S21\| ≈ 0 dB and \|S11\| far down is not an impressive
result — it is the *only* correct one, which is exactly what makes it a good
check. A solver that is meshing badly at 5 mm wavelengths cannot fake it.

⛳ **Try breaking it, because that is where the learning is.** Drop the
frequency sweep below 26.34 GHz and re-run: \|S21\| should collapse, because the
guide is now evanescent. The cutoff is a hard physical edge and the solver
should find it without being told.

**Prove it** — `tests/validation/mmwave_palace.py`. It runs this exact geometry
and asserts both rows above, and alongside it solves **two PEC cavities** whose
TE101 must match the closed form to better than 0.1 %: measured
**39.0255 GHz (+0.003 %)** and **56.9092 GHz (+0.002 %)**. The 57 GHz point is
there specifically to prove headroom past 40 GHz.

⛳ **What is still missing, said plainly.** No radiating structure is gated above
**2.45 GHz** — that is the patch in tutorial 3, and it is the real ceiling, not
the 6 GHz this file used to quote. So mmWave *antenna* work — 28 GHz patches,
handset PIFAs, arrays — is not something this project has earned the right to
claim yet. It is the next gate
being sought, and it needs a published, *measured* reference to anchor to.

## 7. Induction heating, against measured laboratory data

**Needs:** **Elmer** and **gmsh**. **EMStudio ▸ Setup ▸ Detect / Install
Solvers** reports whether both are present.

⛳ **This is the strongest number in the project, and it is worth saying why.**
Every other anchor in this series compares a solver against a *formula*. This
one compares it against a **bench measurement** — TEAM Problem 7,
*"Asymmetrical Conductor with a Hole"* (Fujiwara & Nakata, COMPEL 9(3) 1990),
a standard the computational-electromagnetics community published precisely so
that codes could be checked against reality rather than against each other.

**Do**
1. **Templates ▸ Template: Induction Heating**, or open
   `examples/induction_billet.FCStd`.
2. **Run Solver.** The TEAM 7 geometry is an aluminium plate 294 × 294 × 19 mm
   (σ = 3.526e7 S/m) with an off-centre 108 × 108 mm through-hole, driven by a
   racetrack coil of **2742 ampere-turns at 50 Hz** sitting 30 mm above it.
   Expect **a few minutes** — it meshes to roughly 123 000 tetrahedra and runs
   two full periods as a transient.

**You should see** the vertical flux density along the measured **A1-B1 line**
(y = 72 mm, z = 34 mm) tracking the published points:

| quantity | gate window | reference run |
|---|---|---|
| RMS(Bz − Bz_measured), normalised by max\|Bz_measured\| = 7.811 mT | ≤ **10 %** | **2.83 %** |

⚠ **Read that metric carefully, because the obvious one is wrong here.** It is
an RMS error normalised by the *peak* of the measured curve — **not** a
point-by-point percentage. The A1-B1 line **crosses zero at x ≈ 0.09 m**
(the measured value there is 0.036 mT), so a relative error at that point
divides by almost nothing and explodes to a meaningless number. Any tool that
quotes you a point-wise percentage on a curve that changes sign is telling you
about its arithmetic, not its physics.

**What the curve should look like**, so you can sanity-check the shape before
you trust the number: Bz is negative under the solid part of the plate, crosses
zero once near x ≈ 0.09 m, and peaks near the **hole edge** at x ≈ 0.126 m
(measured 7.811 mT). Eddy currents cannot flow through the hole, so they crowd
around it — that peak is the whole point of the benchmark.

⛳ **The companion gate is the analytic tier.** `induction_elmer.py` puts the
same solver against the exact Bessel-function solution for a billet in a
uniform field: **+0.03 % at 1 kHz** and **+1.26 % at 10 kHz**. Sub-percent
against a formula, ~3 % against a laboratory — that ordering is what you should
expect from any honest FEM chain, and if you ever see it reversed, be
suspicious.

**Prove it** — `tests/validation/team7_elmer.py` (SOLVER tier). It runs the
full production pipeline (gmsh → ElmerGrid → writer → ElmerSolver) and asserts
the window above against all 17 published points. ⚠ Its self-pinned solver
norms are **gmsh-version-locked**: gmsh 4.12.1 reproduces them bit-for-bit,
4.15.2 moves them ~0.1 %. Same deck, same code, different mesher — which is
itself worth knowing before you blame a solver for a number that moved.

---

## 8. Wireless power: two coils, and the coupling between them

**Needs:** **Elmer** and **gmsh**.

**Do**
1. **Templates ▸ Template: WPT Coil Pair**, or open
   `examples/wpt_coil_pair.FCStd`. Two identical coaxial coils: **10 turns,
   mean radius 50 mm, 2 × 2 mm square cross-section**.
2. **Run Solver** for a single gap, or **Analysis ▸ WPT: Sweep Coil Gap** to
   get the curve that actually matters to a designer.

**You should see**, at a **20 mm** gap:

| quantity | gate window | reference run | compared against |
|---|---|---|---|
| L₁ (self-inductance) | 1.5 % | **25.6827 µH** (−0.39 %) | Maxwell/Grover GMD, 25.782448 µH |
| M (mutual) | 1.5 % | **6.7392 µH** (−0.21 %) | Maxwell's coaxial-filament formula |
| k = M/√(L₁L₂) | 2 % | **0.26243** (+0.18 %) | 0.26195 |

And from the sweep, k falling monotonically as the coils separate:

| gap | 8 mm | 18 mm | 35 mm | 55 mm |
|---|---|---|---|---|
| k | **0.4712** | **0.2851** | **0.1525** | **0.0832** |

**Why this is the useful check.** Coupling coefficient is the number a wireless
power link lives or dies on, and it is brutally sensitive to geometry — which
makes it a much sharper test than inductance alone. Note the two analytics are
independent: the self-inductance comes from Grover's GMD formula, the mutual
from Maxwell's elliptic-integral filament formula. Agreeing with both to a few
tenths of a percent is not one lucky calibration.

⛳ **A third check runs for free**: L₂ must equal L₁, because the coils are
identical. The gate asserts they match to **0.02 %**. A mesh that treated the
two solids differently would show up here first, and it is the cheapest
sanity check in the file.

**Prove it** — `tests/validation/wpt_elmer.py` (SOLVER tier). Gate A does the
analytics above at 10, 20 and 50 mm; Gate C re-runs the sweep through the same
parametric command the menu uses, so the number you get from the GUI is the
number that was gated.

---

## 9. A 3-D solenoid on your own geometry

**Needs:** **Elmer**, **gmsh**, and FreeCAD (this one goes through the solid
modeller, not a wire model).

⛳ **What makes this different from #7 and #8.** Those run a prepared template.
This one is the **general 3-D path**: you hand EMStudio *solids*, it exports
them as BREPs, meshes them conformally, and solves the WhitneyAV chain. It is
the route by which any coil you can draw becomes a magnetostatic model.

**Do**
1. **Templates ▸ Template: 3-D Solenoid (Magnetostatic)**, or open
   `examples/solenoid_3d.FCStd`.
2. **Run Solver**. About **30 seconds** on the template's default mesh.

**You should see** the on-axis centre flux density matching the exact
thick-solenoid closed form:

| quantity | gate window | reference run |
|---|---|---|
| centre Bz, template default mesh | **4 %** | **8.27277 mT** vs exact 8.37806 mT (**−1.26 %**) |

⚠ **Two things about that window, because they are easy to misread.**

1. **4 % is the *template* tier, not the engine's accuracy.** The template
   meshes fast so the tutorial finishes in half a minute. The same physics on a
   fine mesh is gated at **−0.55 % at the centre** and −1.21 % at the worst
   end point (`whitney3d_elmer.py`). If you refine, you should move toward the
   tighter figure — and if you do not, your mesh is the problem, not the solver.
2. **The sign of Bz is mesh-arbitrary and the gate ignores it.** A closed coil
   has no intrinsic "up": the circulation sense falls out of how the mesh
   happens to orient the conductor loop. If your result comes back negative,
   nothing is wrong. The gate compares magnitudes on purpose, and that is
   recorded rather than silently absorbed.

**The drive is worth checking too** — the template sets **+500 ampere-turns**
(25 turns × 20 A). Ampere-turns, not amps, is what a magnetostatic solve
actually consumes, and getting that distinction wrong is the single most common
way a coil model comes out by an exact integer factor.

**Prove it** — `tests/validation/solenoid3d_elmer.py` (SOLVER tier, runs under
`freecadcmd` because it needs the BREP export) for the template path, and
`tests/validation/whitney3d_elmer.py` for the engine tier: a thick finite
solenoid, a Helmholtz pair whose on-axis flatness is asserted at
Bz(±10 mm)/Bz(0) − 1 ≈ −1.15e-4, and an off-axis loop against the
elliptic-integral field.

---

# The rest of the series — planned order

> **The goal is COMPLETE COVERAGE: at least one tutorial for every solver and
> every capability EMStudio ships**, so "there is nothing showing how to use
> EMStudio" stops being true. The ones above are written; everything below is
> not yet. ⚠ **Do not quote a tutorial COUNT anywhere** — not in a post, not in
> a README, not here. It goes stale the day the next one lands, and it already
> has: a reply drafted on 2026-08-20 said "five" on the day the sixth shipped.

**The numbering below is the project's master list, so a tutorial keeps the
same number everywhere it is referred to** — #12 is the cavity eigenmode one
whether it is written yet or not. Each names the anchor it must quote — a
measured number with a gate behind it — because a tutorial without one is not
allowed (see the notes below).

🔒 marks a **Pro** capability. Those get a short public stub here saying what
it does and what it measured, with the full walkthrough Pro-side; the free
alternative is named where one exists.

| # | Tutorial | Group | Tier | Anchor it should quote |
|---|---|---|---|---|
| 10 | **OpenFOAM — CFD on your own solid** | Analysis | free | +4.3 % vs Churchill (sphere anchor) |
| 11 | **OpenFOAM — CHT** | Analysis | free | Nu ≈ 6.56 ± 1.5 % (⚠ NOT the gate's 6.85) |
| 12 | **Palace — cavity eigenmodes** | Templates | free | first six modes, TE101 lowest |
| 13 | **Cable Designer — litz** | Tools | free | IEC 60287 worked examples |
| 14 | **Cable Designer — bundles/crosstalk** | Tools | free | MoM insulated-C, mixed-mode pairs |
| 15 | **Small-Antenna Designer (VLF/LF)** | Tools | free | Watt §4 — efficiency ladder, Chu Q |
| 16 | **Link Budget** | Tools | free | FSPL + knife-edge closed forms |
| 17 | **Coverage maps** | Tools | free | ITU-R P.1546 / P.1812 official profiles |
| 18 | **Multi-station D/U** | Tools | free | service/interference contours |
| 19 | **Isolation Matrix** | System | free | port-to-port isolation vs spacing |
| 20 | **Co-site / EMC** | System | free | IMD products, intercept levels |
| 21 | **Antenna from Selection** | Analysis | free | thin-wire d/a report on a real curve |
| 22 | **Pattern Frequencies / scrubbing** | Analysis | free | N patterns from ONE run (201 in 7.18 s) |
| 23 | **Solver Setup / install** | Setup | free | the workflow, not a number |
| 24 | 🔒 **System Matching Designer** 🔒 | System | **Pro** | predicted-vs-achieved curves |
| 25 | 🔒 **Array Designer** 🔒 | System | **Pro** | cardioid 3.4 → 29.6 dB F/B; Dolph −26.02 dB to 0.04 dB |
| 26 | 🔒 **RF Direction Finding** 🔒 | System | **Pro** | manifold decode at 0.00° error |
| 27 | 🔒 **The AI Assistant** 🔒 | Help | **Pro** | ⚠ **AJ NAMED THIS ONE EXPLICITLY** — see below |

⚠ **#23 (Solver Setup) is the one exception** — it documents a workflow, not a
number, because installing a backend has no measurable output to pin. It says
so out loud rather than inventing an anchor.

---

## Notes for whoever writes the rest

⛳ **Do not write a tutorial without a number and a gate.** If a feature has no
gate that pins a user-visible figure, that is a finding about the feature, not
a reason to write vaguer prose.

⛳ **Quote the gate window, not the reference run alone.** A tutorial that says
"you will see 2.13 dBi" is wrong for everyone whose mesh differs. Say the
window and put the reference inside it.

⛳ **Name what does not work yet.** #3 says openEMS has no one-click install on
any platform. A limitation the reader finds themselves costs far more than one
you volunteered.

⛳ **Order by install burden.** Every tutorial that needs nothing installed
should come before every tutorial that needs a backend.
