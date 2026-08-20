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

## 12. A resonant cavity, and the mode you can compute by hand

**Needs:** **Palace**.

⛳ **Why a cavity is the fairest test a full-wave solver ever faces.** A closed
rectangular box has an *exact* analytic answer — no approximation, no fitted
constant, no measurement uncertainty:

> f(m,n,p) = (c/2)·√[ (m/a)² + (n/b)² + (p/d)² ]

There is nowhere for a solver to hide. If it cannot land on that, nothing it
tells you about a geometry you *cannot* solve by hand is worth much.

**Do**
1. **Templates ▸ Template: Resonant Cavity**, or open
   `examples/cavity_rect.FCStd`. It is a PEC box **40 × 20 × 60 mm**.
2. **Run Solver**. Around a minute and a half for ten modes.

**You should see** the fundamental land on TE101, and every mode agree with its
closed form:

| quantity | gate window | reference run |
|---|---|---|
| fundamental (TE101) | < 1 % | **4.50386 GHz** vs analytic 4.50382 GHz (**+0.001 %**) |
| all ten modes vs nearest analytic | < 1 % | worst **0.020 %** |

**Read the ordering, not just the first number.** With a = 40, b = 20, d = 60 mm
the lowest mode uses the two LONGEST dimensions and puts no variation across the
short one — that is TE101, and it should come out first. If your fundamental
arrives somewhere else, suspect the geometry or the units before the solver:
a cavity mis-scaled by 10× is still a perfectly self-consistent cavity, and it
will report beautifully converged nonsense.

⛳ **Try breaking it.** Double `a` and the fundamental must fall — not by half,
because the mode depends on the *sum of squares* of the reciprocals. Predict the
new value with the formula above before you re-run, then check. Getting that
prediction right is worth more than the solve.

⛳ **A cylindrical companion ships too** (`examples/cavity_cyl.FCStd`,
**Templates ▸ Template: Cylindrical Cavity**), whose modes fall out of Bessel
zeros rather than a sum of squares — the same exactness on a geometry with
curvature, which is where a mesher's quality actually shows.

**Prove it** — `tests/validation/cavity_palace.py` (SOLVER tier). Gate A solves
this exact box and asserts both rows above against the closed form; a second
gate runs the same geometry through the FreeCAD template path under
`freecadcmd`. ⛳ The 39 GHz and 57 GHz cavities in tutorial 6 are the same check
carried up to mmWave — same physics, same window, two decades higher.

## 15. An antenna far too small for its wavelength (VLF/LF)

**Needs:** nothing. This one is closed-form physics, and it runs instantly.

⛳ **Why this tutorial exists.** Below about 500 kHz nobody has a half-wave
antenna — a half wave at 30 kHz is 5 km. Everything you build is *electrically
small*, and electrically small antennas obey rules that feel wrong if your
intuition was formed at VHF: the radiation resistance collapses, the reactance
is enormous, and efficiency becomes an accounting problem rather than a design
flourish.

**Do**
1. **Tools ▸ Small-Antenna Designer (VLF/LF)**.
2. Enter a **100 m** vertical at **30 kHz** — a real, large VLF mast.

**You should see** numbers that look alarming and are correct:

| quantity | value | why |
|---|---|---|
| h / λ | **0.0100** | the mast is one hundredth of a wavelength |
| Radiation resistance | **0.03953 Ω** | R_r = 40π²(h/λ)² — tens of milliohms |
| Q | **4.04e3** | which is why VLF bandwidth is measured in tens of hertz |
| Loading inductance to resonate | **0.0485 H** | 48.5 mH, a physically large coil |

**The lesson is the ratio, not any one figure.** With R_r at 0.0395 Ω, a ground
system of even 1 Ω throws away **96 %** of your transmitter power as heat.
That is why VLF stations spend their money on radials and loading coils rather
than on the mast: efficiency is R_r/(R_r + R_loss), and you cannot raise R_r
much, so the entire engineering effort goes into driving R_loss down.

⛳ **Check it against the textbook** — the designer uses the standard forms and
the gate pins them: a short dipole at **R_r = 20π²(L/λ)² = 1.9739 Ω**, a short
monopole at exactly **twice** that for the same L/λ, and the Chu limit
**Q_min = 1/(ka)³ + 1/(ka) = 10.0000 at ka = 0.5**. A small loop follows
**R_r = 31171(A/λ²)²** and scales as **N²** — ten turns is a hundred times the
radiation resistance.

**Prove it** — `tests/validation/small_antenna.py` (FAST tier, no solver). It
asserts every closed form above against Balanis, plus the band picker that
routes a VLF problem to the analytic path rather than to a field solver.
⛳ **Why it refuses to route VLF to FDTD:** meshing a 10 km wavelength in
λ/20 cells is not a slow calculation, it is an impossible one. The tool says so
instead of letting you start it.

---

## 16. A point-to-point link, and the hill in the way

**Needs:** nothing.

**Do**
1. **Tools ▸ Point-to-Point Link Budget**.
2. Start with the textbook case: **1 km at 300 MHz**, then add a ridge between
   the ends.

**You should see** the standard results, each matching its closed form:

| quantity | value |
|---|---|
| Free-space path loss, 1 km @ 300 MHz | **81.99 dB** |
| Doubling the distance | **+6.02 dB** |
| Knife-edge diffraction at grazing (ν = 0) | **6.03 dB** |
| Knife-edge at ν = 1 / ν = 2.4 | **13.93 dB** / **20.54 dB** |
| Plane-earth, 1 km, 10 m / 10 m antennas | **80.00 dB** |
| Doubling distance, plane-earth region | **+12.04 dB** (the d⁴ law) |
| Field strength, 1 kW EIRP at 1 km | **104.77 dBµV/m** |

**The two numbers worth internalising** are +6.02 and +12.04. In free space,
doubling the range costs 6 dB; once you are far enough out that the ground
reflection dominates, doubling it costs **12** dB, because the field falls as
1/d² rather than 1/d. Everything surprising about real coverage — why the last
few kilometres are so expensive, why raising an antenna helps more than raising
power — falls out of that transition.

⛳ **The 6 dB at ν = 0 is the one people misremember.** An obstruction that
*just* grazes the line of sight does not cost you nothing; it costs about
**6 dB**, because the knife edge blocks half the first Fresnel zone. If your
link budget assumed line-of-sight meant free-space, that 6 dB is already
missing from it.

**Prove it** — `tests/validation/propagation.py` (FAST tier, no solver): Friis,
the ITU-R P.526 knife-edge curve, the two-ray plane-earth d⁴ law, the ITU
field-strength relation and single-edge Deygout terrain diffraction, each
against its closed form.

---

## 20. Two radios on one mast: co-site interference

**Needs:** nothing for the arithmetic. (Pair it with tutorial 19's isolation
matrix, which needs NEC2, when you want the isolation figure to come from your
own geometry rather than from a number you typed.)

⛳ **What this answers.** Two transmitters near each other do not simply
coexist. They mix in each other's front ends and produce products at
frequencies neither of them is using — and the third-order ones land
*inside* your receive band, where no filter can help you.

**Do**
1. **Tools ▸ Co-site Interference Calculator**.
2. Enter two transmitters at **150 MHz** and **151 MHz**, an IP3 of **+30 dBm**
   and a per-tone level of **−10 dBm**.

**You should see** the products and what they cost you:

| product | frequency | why it matters |
|---|---|---|
| 2f₁ − f₂ | **149 MHz** | third order, and only 1 MHz away — in band |
| 2f₂ − f₁ | **152 MHz** | the other third-order product |
| f₁ + f₂ | **301 MHz** | second order, usually filterable |
| \|f₁ − f₂\| | **1 MHz** | second order, far out of band |

| level | value |
|---|---|
| IMD3 at −10 dBm/tone, IP3 +30 dBm | **−90.00 dBm** |
| with unequal tones (0 and −20 dBm) | **−80.00 dBm** |
| Received power, +43 dBm through 60 dB isolation | **−17 dBm** |
| Broadband transmitter noise into a 25 kHz receiver | **−96.02 dBm** |

**Read the slope, because it is the whole design rule.** IMD3 = 2·P₁ + P₂ −
2·IP3. Third-order products fall **3 dB for every 1 dB** you back the tones off
— so 10 dB more isolation buys you 30 dB less interference. That is why
co-site engineering is mostly about antenna separation and filtering rather
than about better receivers.

⛳ **Do not stop at the IMD products.** The **−96.02 dBm** broadband noise figure
above is often the real limit: a transmitter's wideband noise floor lands in
your receive band continuously, not just when two carriers happen to mix. It is
the quiet one that ruins a site.

**Prove it** — `tests/validation/cosite.py` (FAST tier). It asserts every
product frequency, the IMD3 level for equal and unequal tones, the
isolation arithmetic, D/U, and the broadband-noise integration into a stated
receiver bandwidth.

---

## 17. Coverage over real terrain, against ITU's own reference data

**Needs:** nothing. Terrain tiles are optional — the ITU profiles ship with the
gate.

⛳ **This is the strongest kind of validation a propagation tool can have, and
it is worth understanding why.** ITU-R publishes not just the *methods*
P.1546 and P.1812 but **official reference datasets**: named profiles with the
answer their own implementation produces. A tool either reproduces them or it
does not. There is no window to argue about and no reference run to calibrate
against — it is a spelling test with a published answer key.

**Do**
1. **Tools ▸ Area Coverage Map**.
2. Pick a transmitter site, a power and a frequency, and choose **P.1546**
   (broadcast-style, statistical) or **P.1812** (point-to-area with terrain).

**You should see** contours that agree with ITU's implementation exactly:

| method | official coverage | agreement |
|---|---|---|
| **P.1546** | **52 datasets**, all **24** official profiles | worst **0.000000 dB** |
| **P.1812** | **63 datasets**, all **19** official profiles | worst **0.000000 dB** |

Those are not typos and not rounded-to-zero claims made loosely: the gate
asserts every dataset to **≤ 0.01 dB** and the measured worst case is
**exactly zero to six decimals**, including the delta-Bullington intermediate
values that P.1812 logs step by step.

**What the map is actually telling you.** Both methods are *statistical* — they
predict a field strength exceeded at some percentage of locations and time, not
the field at your friend's house. A P.1546 contour labelled 50 % / 50 % means
half the locations, half the time. Reading it as a fence around guaranteed
service is the single most common way coverage maps mislead people.

⛳ **It refuses to extrapolate, and that is a feature.** Ask either method for a
frequency outside its published validity and it declines rather than returning a
confident number. A propagation model used outside its range does not degrade
gracefully; it just becomes wrong quietly.

**Prove it** — `tests/validation/p1546.py` and `tests/validation/p1812.py`
(FAST tier), which replay every official dataset; plus
`tests/validation/coverage.py` for the geodesy underneath (a degree of longitude
at the equator as **111.195 km**, London–Paris as **343.557 km**, and the `.hgt`
terrain tile read north-up rather than upside down).

---

## 22. Every frequency's pattern, from one solver run

**Needs:** **NEC2**.

⛳ **The thing worth knowing before you start.** A swept NEC2 run already
computes the far field at every frequency it visits — the patterns are sitting
in the output file whether you ask for them or not. Most workflows throw them
away and re-run the solver once per frequency. EMStudio keeps them, so **N
patterns cost ONE run**, and you scrub through them with a slider.

**Do**
1. Open a swept analysis — the dipole from tutorial 2 will do.
2. **Analysis ▸ Pattern Frequencies…**, set a band and a step. The dialog
   recommends a step that lands on the sweep's own sample points, so you are
   not asking the solver to interpolate.
3. **Run Solver**, then drag the slider on either pattern tab.

**You should see** one pattern per requested frequency, each carrying its *own*
gains — and the 3-D balloon following the slider live, including after the
results dialog is closed.

| quantity | gate window | reference run |
|---|---|---|
| patterns returned | one per solved frequency | **11 of 11** |
| current distributions | one per solved pattern frequency | **11** |
| each pattern's frequency | its own, never the band start | asserted per entry |

**The failure this defends against is invisible, which is why it is gated so
hard.** A parser that merges frequency blocks returns *one* pattern wearing
whichever label it was handed — and it looks completely normal. The gate proves
the blocks stay separate, that the results come back sorted by frequency, and
that each block keeps its own gains through that sort. Two of those checks were
added on 2026-08-20 after the sort check was found to be untestable against an
already-ascending fixture.

⛳ **Watch the pattern change shape as you scrub.** On a dipole it stays
recognisable; on anything electrically long it will not, and seeing that happen
is worth more than reading about it.

**Prove it** — `tests/validation/pattern_sweep.py`. Its live tier runs a real
NEC2 sweep and asserts the per-frequency patterns and currents; the FAST tier
pins the band arithmetic and the parser, including a **descending** fixture that
proves the sort is real rather than an accident of file order.

---

## 23. Getting the solvers installed

**Needs:** nothing to read it.

⚠ **This is the only entry in the series with no number, and it says so.**
Every other one ends in a measured figure with a gate behind it. Installing a
backend has no user-visible output to pin — the honest anchor is *"the probe
reports found"*, which is a state, not a measurement. Rather than invent a
figure, this one documents the workflow and names what IS checked.

**Do**
1. **Setup ▸ Detect / Install Solvers**.
2. Read the table. Each backend is **probed**, not guessed from a version
   string: EMStudio runs the binary and checks it actually works.

**You should see** a probed table — and here is what each answer means:

| column | what it tells you |
|---|---|
| where | the resolved path, so you know *which* copy was found |
| which fork | ESI vs Foundation for OpenFOAM — they are not interchangeable |
| tools present | the helpers a backend needs, not just the solver itself |
| do function objects work | a ~1 s runtime probe |

⛳ **The probe exists because a version number lies.** Ubuntu's own OpenFOAM
v1912 package *installs perfectly* and then aborts with a `sha1` IOstream error
the moment a function object runs. No version floor would catch that — only
running it does. The dialog reports the failure and says what to install
instead.

⛳ **On Windows, Elmer, gmsh, NEC2 and OpenFOAM have guided install buttons.**
The single step that needs Administrator is explained rather than automated —
EMStudio will not silently ask your machine for privileges.

**What pins it** — there is no single gate that asserts "the install worked",
because that depends on your machine. What is gated: `openfoam_setup.py` and
`cht_setup.py` pin the fork detection and the probe logic (FAST tier), and
`gui_smoke` builds the dialog and asserts the guided-install buttons appear for
elmer, gmsh, nec2 and openfoam on a simulated Windows. **Prove it** —
`tests/validation/openfoam_setup.py`.

---

## 13. Litz wire: why stranding it changes anything

**Needs:** nothing for the construction and thermal work. **FastHenry** if you
want the current-sharing solve at the end.

⛳ **The question this answers.** Litz wire is expensive and fiddly, and at DC
it is electrically identical to a solid conductor of the same copper area. So
why use it? Because at frequency the current stops using the middle of a
conductor — and *which* strands carry the current is something you can compute
rather than assume.

**Do**
1. **Tools ▸ Cable Designer**, Litz page. Build a construction: EMStudio
   supports the standard **Types 1–9**.
2. Compare a **6-strand ring** against a **7-strand** bundle — the same wire,
   except the 7-strand has one strand in the *centre*.

**You should see** the centre strand behave completely differently:

| construction | current imbalance (max/min) | reading |
|---|---|---|
| 6-strand ring, 10 kHz | **1.0000** | perfect sharing — every strand equivalent |
| 6-strand ring, 100 kHz & 1 MHz | **1.0003** | still essentially perfect |
| **7-strand with a centre strand, HF** | **9.6272** | one strand carrying ~10× another |

And when the strands are grouped rather than individual:

| group | normalised current |
|---|---|
| centre group | **0.119** — barely conducting |
| ring group | **1.149** — carrying the difference |

**That 9.63 is the whole argument for litz.** A centre strand is surrounded by
the magnetic field of every strand around it, so proximity effect pushes current
out of it. It still costs you copper, weight and money, and it carries almost
nothing. Real litz constructions **transpose** the strands so each one spends
equal time in the middle — which is exactly why the ring stays at 1.0000 and the
naive bundle does not.

⛳ **The symmetric case is the control, and it matters as much as the
interesting one.** A 6-ring must come back at 1.0000 because every strand is
geometrically equivalent; if it did not, the solver would be wrong and the
9.6272 would mean nothing.

**Then check the thermal side**, on the same page — because current sharing
decides where the heat goes:

| quantity | value | reference |
|---|---|---|
| AWG-10 PVC, 105 °C class, free air | **66.6 A** | inside the Multicable 58 A ±25 % band |
| Joule loss at that operating point | **6.3175 W/m** | I²R(T), the same R the electrical model uses |

⚠ **Ampacity is a temperature answer, not a current answer.** It is the current
at which the conductor reaches its insulation's class limit — so the same wire
is rated differently in PVC (70/80/105 °C), XLPE (90 °C) and PTFE (200 °C).
The tool uses the IEC 60287-2-1 Table 1 thermal resistivities and the
IEC 60287-1-1 conductor constants rather than a lookup table, so a construction
nobody has tabulated still gets an answer.

**Prove it** — `tests/validation/wire_current_sharing.py` for the sharing
figures (FastHenry), `tests/validation/thermal.py` for the ampacity and every
IEC constant it rests on, and `tests/validation/cable.py` for the coax geometry
underneath (FAST tier).

---

## 14. Cable bundles: skin, proximity, and what FastHenry adds

**Needs:** **FastHenry** for the solved numbers; the closed forms need nothing.

⛳ **Two effects, and only one of them has a formula.** *Skin* effect — current
crowding to a conductor's own surface — has an exact Bessel solution for an
isolated round wire. *Proximity* effect — one conductor pushing current around
inside its neighbour — does not, for a real bundle. That is the boundary this
tutorial is about, and it is why a field solver earns its place here.

**Do**
1. **Tools ▸ Cable Designer**, Bundle page. Lay out two or more conductors.
2. Read the analytic skin/proximity factors, then run the **FastHenry** solve
   and compare.

**You should see** the analytics exact where they should be, and FastHenry
tracking them with a mesh-driven error that *grows with frequency*:

| check | value |
|---|---|
| skin low-frequency expansion | exact **1.00130** vs series **1.00130** |
| skin asymptote at a/δ = 4 | exact **2.2738** vs asymptotic **2.2734** |
| skin asymptote at a/δ = 10.5 | exact **5.5089** vs **5.5089** |
| proximity seam continuity | **2.439e-04** vs **2.442e-04** |

| FastHenry vs the exact Bessel R_ac/R_dc | FH | exact | error |
|---|---|---|---|
| 1 kHz | 1.001 | 1.001 | **0.0 %** |
| 10 kHz | 1.109 | 1.101 | **0.8 %** |
| 100 kHz | 2.818 | 2.662 | **5.9 %** |
| 1 MHz | 8.369 | 7.822 | **7.0 %** |

⚠ **Read that error column as a mesh statement, not a solver indictment.**
FastHenry discretises each conductor into filaments; as frequency rises the
skin depth shrinks until the outermost filament is thicker than the layer the
current actually flows in, and the solver reports slightly too much conductor.
The fix is more filaments (`nhinc`), which costs time — so the honest workflow
is: **trust the closed form where one exists, and use FastHenry for the
geometries where none does.**

⛳ **The proximity series is checked for seam continuity on purpose.** It is a
piecewise fit, and a discontinuity at the join would be invisible in any single
evaluation while producing a step in a swept plot. It matches to four digits
across the seam, and the gate asserts monotonicity across six decades besides.

**Prove it** — `tests/validation/wire_fasthenry.py` (SOLVER tier for the
FastHenry rows, analytic rows FAST), and `tests/validation/cable.py` for the
geometry underneath.

---

## 18. Two transmitters, one service area: where does each one win?

**Needs:** nothing.

⛳ **What "coverage" leaves out.** Tutorial 17 draws where a transmitter is
strong enough. It does not ask whether *another* transmitter is also strong
there — and a receiver in that overlap may hear neither cleanly. Service is a
**ratio**, not a level.

**Do**
1. **Tools ▸ Multi-Station Service / Interference**.
2. Place a wanted station and one or more interferers, set a service threshold
   and a protection ratio.

**You should see** each cell classified rather than merely shaded:

| case | result |
|---|---|
| desired 50, threshold 41, undesired 38 dBµV/m | **interference-limited** (D/U 12 dB) |
| desired 50, undesired 34 → D/U 16 dB vs a 15.27 dB ratio | **served** |
| below the service threshold | **no service** — no interferer needed |
| in coverage, no interferer | **served**, D/U = +∞ |
| a real two-station map | wanted **+28.3 dB**, toward the interferer **−27.9 dB** |

**How interferers combine**, which is the part people get wrong:

| combination | result |
|---|---|
| two equal 60 dBµV/m signals | **63.0103 dBµV/m** — a **power** sum, +3.01 dB |
| N equal signals | **+10·log₁₀(N)** (three → +4.771 dB) |
| 34 and 33 dBµV/m | **36.539 dBµV/m** — matches **ITU-R BT.2265** |

⚠ **Interferers add in power, not in voltage, and never as "the worst one".**
The tool reports both the power sum and the worst-case single interferer, and
the power sum is always the larger — planning against the strongest interferer
alone quietly under-counts a site with several moderate ones.

⛳ **The protection ratios are source-tagged, not invented**: FM co-channel
**20 dB**, AM/MF co-channel **26 dB** (a 20:1 voltage ratio). The gate asserts
the tag as well as the number, so a figure cannot lose its provenance.

⛳ **Do not go looking for a `multistation` gate file — there isn't one.** Gate
files here are named after the physics, not the capability, and this one's
checks live inside the coverage gate. *"No gate exists"* has to be established
by reading gate bodies, because under the rules of this series it changes what a
tutorial is allowed to claim.

**Prove it** — `tests/validation/coverage.py` (FAST tier), which covers the D/U
combination arithmetic, the classification rules, the protection-ratio table and
a real two-station service map.

---

## 19. How much does one antenna hear of another?

**Needs:** **NEC2**.

**Do**
1. **Templates ▸ Template: Co-site Antenna Pair**, or place two antennas in one
   analysis.
2. **Analysis ▸ Antenna Isolation Matrix**. It runs one NEC2 solve per element
   and assembles the mutual-impedance matrix.

**You should see**, for the shipped pair:

| quantity | value |
|---|---|
| Z₁₁ | **72.210 − 0.496j Ω** |
| Z₂₁ | **−15.014 − 27.996j Ω** |
| \|S₂₁\| | **−13.780 dB** → **13.78 dB of isolation** |
| reciprocity error | **1.07e-14** |

**That reciprocity figure is the one to look at first.** Z₂₁ must equal Z₁₂ for
any passive structure — it is physics, not a modelling choice — so the residual
is a direct read on whether the solve is trustworthy. At **1e-14** it is at
floating-point noise. If it were 1e-3 you would stop and find out why before
believing anything else in the matrix.

⚠ **13.78 dB is not much isolation**, and that is the lesson rather than a
disappointment. Feed tutorial 20 with it: a +43 dBm transmitter through 13.78 dB
lands **+29 dBm** in the neighbouring receiver, which is well past where any
front end stays linear. Isolation is the number co-site design lives on, and
close-spaced antennas do not give you much of it for free.

**Prove it** — `tests/validation/isolation_nec2.py` (SOLVER tier). ⚠ It needs
FreeCAD, so run it through the gate runner — `freecadcmd tests/run_gate.py
tests/validation/isolation_nec2.py`. Run directly under plain `python3` it dies
on a missing `FreeCAD` module, which looks like a defect and is not one.

---

## 21. Turning a shape you drew into a wire antenna

**Needs:** **NEC2**.

⛳ **What this bridges.** NEC2 models *thin wires*: segments with a radius. A
FreeCAD sketch is a curve or a solid with no such notion. **Analysis ▸ Antenna
from Selection** does that translation, and it is stricter than you might
expect — deliberately.

**Do**
1. Draw a curve or a solid rod. Select it.
2. **Analysis ▸ Antenna from Selection**.

**You should see** it either build a wire model or **refuse with a reason**:

| selection | result |
|---|---|
| a solid | classified **solid** — its radius is *measured*, never asked for |
| a curve with a radius | classified **wire**, segmented for NEC2 |
| a curve with **no** radius | **refused** — it has no cross-section, so there is no d/a to check |
| an empty selection | **refused** |

⚠ **The refusals are the feature.** NEC2's thin-wire kernel is only valid while
the segment length / radius ratio stays sane; feed it a curve with no radius and
it would happily return numbers that mean nothing. The tool declines instead,
and reports the **d/a ratio** it achieved so you can judge the model yourself.

⛳ **The bug this path once had is worth knowing, because the symptom was
silence.** `Part.makePolygon` delivers a curve as N *straight* edges, so every
chord took a 3-segment floor meant for a lone radiator — segmenting a curve far
past NEC-2's thin-wire limit (**240 segments at d/a 2.63**, where **80 at
d/a 7.90** is correct). The guard written to protect d/a could never fire on the
path that needed it. Nothing looked wrong; the numbers were simply outside the
kernel's validity.

**Prove it** — `tests/validation/antenna_from_selection.py` (SOLVER tier, runs
under `freecadcmd`). It asserts the classification of solids and curves, every
refusal above, and that a solid's radius is measured from geometry rather than
requested from the user.

---

# 🔒 The Pro capabilities — what they measure

These four are **EMStudio Pro**. The stubs below say what each one does and the
number it measured, so you can judge whether it is worth anything to you; the
step-by-step walkthroughs ship with Pro.

**EMStudio Pro is $149, one-time, perpetual — no subscription and no account.**
That is the last you will hear about the price in this file.

⛳ **Every number below is already public** — it is in [PRO.md](PRO.md), on the
product page, and in the automated gates that run before each release. Nothing
here is a claim you are being asked to take on trust; they are all measured on
live solver runs, and each names the gate that pins it.

---

## 24. 🔒 System Matching Designer

**What it does.** Your dipole reads 71.9 Ω and your radio wants 50 Ω. It
synthesises the network — L, π, T, quarter-wave, binomial multisection,
single-stub, hairpin — recommends a topology, snaps the values to real E6–E96
parts, and then shows the VSWR you will get **after** that rounding rather than
before it.

**What it measured.** The shipped 71.9 Ω dipole, matched end to end and
verified on a live sweep: **VSWR 1.010**.

**Free alternative:** none for synthesis — but the free tier gives you the
dipole's impedance in the first place (tutorial 2), which is the input this
needs. **Gate:** `system_matching.py`.

---

## 25. 🔒 Array Designer

**What it does.** An array is specified in element *currents*; NEC2 drives
*voltages*. Pro solves **V = Z·I** through the real mutual-impedance matrix, so
the pattern you asked for is the pattern you get.

**What it measured.** The difference is not subtle, and it is the same wires and
the same solver both times: a cardioid pair reaches **29.6 dB front-to-back
through the current solve, against 3.4 dB** for the naive equal-voltage drive.
With amplitude tapers, a steered 8-element Dolph–Chebyshev array holds its
**−26.02 dB sidelobe floor to 0.04 dB on real coupled dipoles** — against
−12.7 dB for the uniform control, i.e. **13.4 dB of measured suppression for
0.58 dB of peak gain**.

**Free alternative:** the free tier models any array you can draw as wires and
gives you its pattern; what it will not do is solve the drive currents for you.
**Gate:** `system_arrays.py`, `system_tapers.py`.

---

## 26. 🔒 RF Direction Finding

**What it does.** Watson-Watt / Adcock with the octantal spacing error
*computed* from the exact crossed-pair response rather than assumed away;
multi-baseline interferometry with ambiguity resolution; pseudo-Doppler ring
sizing; and a correlative-interferometer manifold built from per-element NEC2
patterns — so mutual coupling and platform scattering are inside the manifold
instead of being wished away.

**What it measured.** That manifold decodes an independent receive simulation at
**0.00° bearing error, correlation 1.000000** — and it also prices the
alternative: assuming ideal elements costs you **1.78°**.

**Free alternative:** none. **Gate:** `system_rfdf.py`.

---

## 27. 🔒 The AI Assistant — and the one thing worth saying in public

⚠ **The Assistant does not validate anything. The gates do.**

That sentence belongs in the open, not behind a paywall, because it is what
makes every other number in this file mean something. Everything trustworthy in
EMStudio is trustworthy because a validation gate re-measures it before every
release — that is what the "Prove it" line on every tutorial above points at,
and the Assistant is **not** in that chain.

**What it does.** Helps you set a case up, explains what a control does, and
points you at the right template — inside the workbench, with the document in
front of it. It has **no** privileged access to the physics, it does not check
results, and nothing it says has been verified by anything. If it hands you a
number, that number is worth exactly what an unchecked number is worth: run the
gate.

**What it measured.** Nothing about the physics, and that is the honest answer.
What *is* measured is its plumbing: **167 checks, 16 mutations proven** — that
it refuses what it should refuse and cannot silently act on your document.

**Free alternative:** all of it, in the sense that matters — the gates, the
templates and the tutorials are free, and they are the part that is checked.
**Gate:** `assistant.py`.

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

⛳ **Gate files are named after the PHYSICS, not the capability — search by
content before concluding one is missing.** There is no `link_budget.py`, and
it is easy to conclude the Link Budget tool is ungated; the anchors it needs
(Friis FSPL, ITU-R P.526 knife-edge, the two-ray d⁴ law, the ITU field-strength
relation) are all in `propagation.py`, measured and green. Likewise litz has no
`litz.py` — it lives in `cable.py` and `thermal.py`. ⚠ *"No gate exists"* is a
FINDING about a capability and it changes what a tutorial may claim, so it must
be established by grepping the gate bodies, not by looking for a filename.
