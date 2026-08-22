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
**2.435 GHz** — that is the patch in tutorial 3, and it is the real ceiling, not
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

⛳ **This one used to have no number, and saying so out loud is what produced
one.** The series' rule is that a capability with no gated figure is a FINDING,
not a licence for vaguer prose — and looking for the finding turned up four
real defects in the column you are about to read.

**Do**
1. **Setup ▸ Detect / Install Solvers**.
2. Read the table. Each backend is **probed**, not guessed from a version
   string: EMStudio runs the binary and checks it actually works.

**You should see** a probed table. **The number to check is the version** —
each one is parsed out of that backend's own `--version` output:

| backend | version shown |
|---|---|
| Elmer | **26.2** |
| Gmsh | **4.12.1** |
| NEC2 (nec2c) | **1.3.1** |
| openEMS | **0.37.0-rc1** |
| FastHenry | **3.0.1** |
| OpenFOAM | **2606** |
| Palace | *(blank — it prints no version, and none is invented)* |

⚠⚠ **Elmer's is the one worth understanding.** `ElmerSolver --version` prints
`ELMER SOLVER (v 26.2) STARTED AT: 2026/08/20 19:15:27` — a **run timestamp**.
Until 2026-08-20 this column showed that string whole, so **the version changed
every time you pressed Re-detect**. A version that is different each time you
look at it is worse than no version: it makes the whole table look untrustworthy.
openEMS prefixed a table pipe, FastHenry ran on into its own help text, and
Palace showed nothing at all.

⛳ **Palace's blank is deliberate.** It genuinely prints no version, so the
column is empty rather than filled with a plausible guess — a wrong version
would be reported back to us as fact.

**And here is what each column means:**

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

⚠ **What is still NOT gated**, said plainly: nothing asserts "the install
worked", because that depends on your machine. What IS gated is the readout —
the version table above, the fork detection and the probe logic.

**Prove it** — `tests/validation/solver_versions.py` (FAST tier). It holds the
**verbatim** `--version` output of all seven backends, captured from the real
binaries, and asserts each normalises to the version in the table — plus that a
timestamp is never read as a version, that an absent version stays absent, and
that a version never runs on into help text. **5/5 mutations caught.**
⛳ **And it re-measures.** A fixture nobody re-runs is just a claim with a date
on it, so the gate also probes every backend **actually installed on your box**
and fails if one no longer reports the version this table quotes. That is not
hypothetical: the Elmer PPA ships dated devel snapshots and drops the previous
one from its pool, so an ordinary `apt upgrade` can move the solver underneath
you without touching a line of EMStudio. A backend you have not installed is
skipped **and said out loud** — the run prints how many of the seven it
actually reached, so "covered 0 of 7" can never read like a clean sweep.
⛳ One of its checks had to be *earned*: the rule "prefer a version marked with
`v`/`version` over a bare dotted number" turned out to give the same answer on
all six real strings, so it was decoration rather than a tested property. It is
now pinned by a tool printing a **dotted** date (`built 2026.08.20, version
1.2.3`), which is the case that separates the two.
Also: `openfoam_setup.py` and `cht_setup.py` pin the fork detection and probe
logic, and `gui_smoke` asserts the guided-install buttons appear on Windows.

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

## 10. Thermal CFD on a shape you drew yourself

**Needs:** **OpenFOAM** (ESI). ⚠ This is the longest-running thing in EMStudio —
tens of minutes, not seconds. The pre-solve estimate will tell you before it
starts; that is precisely why that estimate exists.

⛳ **What is genuinely hard here, and what the gate does about it.** Free
convection has no exact solution for an arbitrary shape, so a CFD result has
nothing to be *right* against. Correlations like Churchill's exist for canonical
bodies and carry their own scatter. So the gate anchors on something stronger
first: a case where the answer is **bounded exactly**.

**Do**
1. Draw a solid — a sphere is the case the gate anchors on — and select it.
2. **Analysis ▸ Solve Convection on Selected Solid (open air)…**
3. Read the estimate, then let it run.

⚠ **There is no example document for this path**, deliberately: the whole point
is that it works on *your* geometry. The gate's own case is a UV sphere in open
air with a fixed heat flux on its surface.

**You should see**, on the conduction rung — the one with an exact answer:

| quantity | measured here | the exact bound |
|---|---|---|
| Nu_D | **2.5511** | inside **[2.3374, 2.6667]** |
| converged | **yes**, drift 0.0064 | |
| surface temperature spread | **0.147 K** | |

**Why that bracket is the best check in the file.** For a sphere in a still,
conducting medium the Nusselt number is trapped between two exact conduction
solutions — the inscribed and circumscribed limits, 2/(1 − r/r_ins) and
2/(1 − r/r_cir). No correlation, no fit, no measurement uncertainty: a correct
solve **must** land between them.

⚠ **And it fails informatively in both directions**, which is rare and worth
knowing: **an unconverged solve reads HIGH; a lost-flux coupling reads LOW.**
Seeing 2.83 at 8.7 % drift is not a mystery — it is an unconverged run, and the
gate's own comment records exactly that case.

**The second rung** turns the buoyancy on and compares against **Churchill's
sphere correlation**. Measured on this box:

| quantity | measured | reference |
|---|---|---|
| Nu_D | **18.3508** | Churchill **17.3838** → **+5.6 %** |
| at the resulting Ra_D | **1.317e6** | window ±15 % |
| surface temperature spread | **25.92 K** | vs the conduction rung's **0.147 K** |

⛳ **That last row is a check worth copying.** Free convection either happened
or it did not, and a solve where the flow never started would show the
conduction rung's near-uniform surface. Demanding the convective spread exceed
**5×** the conduction spread makes "did the buoyancy actually engage?" a
question the gate answers rather than assumes — a no-flow solve cannot fake it.

⚠ **Treat a correlation comparison as weaker evidence than the sandwich
above.** A few percent against a fitted curve is agreement; a few percent
outside an exact bound is a bug. The project's own full-fidelity run records
**+4.3 %** (Nu 18.1748 vs 17.42) — finer than this gate's mesh, which is why
the gate-fidelity number above is the larger of the two.

⛳ **Ra is an OUTPUT here, not an input.** The surface has a fixed *flux*, so
the temperature rise — and therefore the Rayleigh number — is whatever the
solve produces. Comparing against a correlation at "the same Ra" means reading
Ra back out of the result, not dialling it in.

**Prove it** — `tests/validation/openfoam_solid.py` (SOLVER tier, long), and
`tests/validation/solid_setup.py` (FAST) for the arithmetic, the refusals, the
written case and the gravity direction.

---

## 11. Conjugate heat transfer: solid and fluid solved together

**Needs:** **OpenFOAM** (ESI). Long — plan in tens of minutes.

⛳ **What "conjugate" buys you.** Every thermal case before this imposed a
condition *on* a surface: a temperature, or a flux, that you had to know in
advance. CHT solves the solid and the fluid **at once**, with the interface
temperature falling out of the coupling rather than being assumed. That matters
whenever the thing you want to know *is* the interface temperature.

**Do**
1. **Analysis ▸ Solve Conjugate Heat Transfer (slab + air gap)…**
2. The reference case is a tall air gap, aspect ratio **H/L = 4**, driven to a
   nominal **Ra ≈ 1e6**.

**You should see** a gap Nusselt number of about **6.5**:

| quantity | value |
|---|---|
| mesh-converged Nu — **the answer** | **~6.5** (bracket **6.47–6.56**) |
| the gate's accepted window | **[5.5, 8.6]** |
| the gate's own 40×60 mesh, measured here | **6.8529** at Ra 8.491e5 — **~5 % high** |
| interface temperature | **342.45 K**, below the conduction limit 348.74 K |

⚠⚠ **Quote "~6.5", never a four-digit value, and never the gate's 6.85.**
That is not fussiness. The 6.85 is what the *gate's* deliberately coarse mesh
produces; a three-grid refinement study (40×60 → 60×90 → 80×120, each run to
20 000 iterations and proven frozen) puts the mesh-independent answer at
**6.47–6.56**. Reporting the gate's number to a user would be quoting a
discretisation artefact as physics.

⛳ **Why a bracket and not a single extrapolated figure.** The scheme is
**first-order** in the convected quantities (`bounded Gauss upwind`, cell
Péclet ≈ 23), yet the three grids show an observed order of **p = 1.90** —
about twice the formal order. Per Roache / ASME V&V 20 that is a reason *not*
to trust the standard safety factor, so the result is reported as a range under
both conventions rather than as one confident number.

⛳ **The gate's window is deliberately wider than every reference** — its job
is to keep a known broken-mesh signature (Nu 1.86–1.88, collapsing toward pure
conduction) dead, **not** to certify a correlation. A window that merely
bracketed the references would pass a mesh that had quietly stopped convecting.

⛳ **T_int below the conduction limit is the second, independent read.** If the
gap were not convecting, the interface would sit at the conduction value of
**348.74 K**; it comes out at **342.45 K**. Convection moves heat, so the
interface must run cooler — a check that needs no correlation at all.

⛳ **The real evidence of convergence is the shrinking difference**, not any
single check: Nu goes 6.8529 → 6.6957 → 6.6387, steps of −0.157 then −0.057,
a ratio of 0.363 — monotone and shrinking. ⚠ An earlier version of that study
claimed an "asymptotic-range check ≈ 1.0" as proof; it was **withdrawn** after
an audit showed the quantity is algebraically identical to f₃/f₂ once *p* is
fitted from the same three points. It had zero degrees of freedom and **could
not fail**. That withdrawal is recorded in the study file itself.

⚠ **Do not cite MacGregor & Emery at A = 4, Pr = 0.7** as a reference for this
case — it does not apply here, and the project has recorded that trap.

**Prove it** — `tests/validation/openfoam_cht_convection.py` (SOLVER tier),
which asserts the window above on a live coupled solve;
`tests/validation/openfoam_cht.py` for the zero-gravity two-region stack, where
both region means must agree to five decimals; and
`tests/validation/cht_setup.py` (FAST) for the case-writing arithmetic. The
refinement study is committed at `docs/results/cht_refinement_fixedmesh.txt` —
including what it got wrong and withdrew.

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

## 28. 🔒 Filter & Diplexer Designer

**What it does.** Synthesises a filter *ladder* — Butterworth or Chebyshev,
low-pass / high-pass / band-pass / band-stop — and hands you the **component
schedule in real part values**, not normalised prototype numbers. It also
designs both diplexer families for splitting one feed into two bands without
either arm detuning the other.

**What it measured.** The contiguous constant-R diplexer holds its composite
input impedance to **under 1e-6 Ω at every order n = 1…7**. The non-contiguous
design assembles to **0.112 dB insertion loss, VSWR 1.38 and 34.8 dB of port
isolation**.

⚠ **This capability was validated for months before anyone could run it.** The
engine and its 35-check gate shipped in v0.66.0; the dialog and menu command
did not exist until 2026-08-20, so none of it was reachable. A validated
capability with no way in is, from the user's side, indistinguishable from one
that was never built.

**Free alternative:** none for synthesis. **Gate:** `system_filters.py`.

---

## 29. A log-periodic that actually works across its band

**Needs:** **NEC2** (`nec2c`) and FreeCAD geometry.

⛳ **Why an LPDA is the honest test of a wire modeller.** A dipole has one
resonance and forgives a lot. An LPDA is a *dozen* coupled dipoles fed by a
crossed transmission line, and it only behaves if the mutual coupling AND the
feeder phase reversal are both right. Get either wrong and you still get a
plausible-looking antenna — just not a log-periodic one.

**Do**
1. **Templates ▸ LPDA**. It builds the classic **Carrel 54–216 MHz** design,
   τ = 0.865 / σ = 0.158.
2. **Run Solver**. About a minute; NEC2 sweeps the band and takes far fields at
   three spot frequencies.

**You should see** gain that holds up across a 4:1 band — which is the entire
point of the geometry:

| quantity | gate window | reference run |
|---|---|---|
| forward gain @ 60 / 120 / 200 MHz | ±0.7 dBi | **8.29 / 8.84 / 8.54 dBi** |
| front-to-back @ the same three | — | **20.2 / 20.8 / 20.0 dB** |
| median VSWR (65 Ω), 41-point sweep | — | **1.215**, 38 of 41 points under 2.0 |

⚠ **Three points in that sweep spike, worst 6.0.** They are documented weak
spots between the low-end element resonances, not a modelling failure — a real
Carrel array does this too. A sweep that came back flawless everywhere would be
the suspicious result.

⛳ **Try breaking it — and this one is worth doing.** Feed the array with an
*uncrossed* line instead of the crossed one. Front-to-back collapses from
20 dB to **5.7 dB**: the antenna still radiates, still looks converged, and is
no longer a log-periodic. The negative-Z0 crossed-line convention is
load-bearing, and the gate regression-guards exactly that control.

**Prove it** — `tests/validation/lpda_nec2.py`, which pins the band impedance
and all three spot-frequency far fields against
`docs/upstream/lpda-carrel-anchors.md`.

## 30. Ground-wave coverage at LF/MF, where the ground is the circuit

**Needs:** nothing — the ground-wave engines are pure Python (SciPy for the
spherical one).

⛳ **Why this band is different.** Above VHF you reason about line of sight and
obstacles. At LF/MF the wave is *attached to the ground* and the ground's
conductivity is a circuit element: the same transmitter over sea water and over
dry inland soil are two different antennas.

**Do**
1. **Analysis ▸ Area Coverage Map**.
2. Set the frequency into the **kHz** range, then pick a **Propagation model**:
   *Ground-wave flat earth (LF/MF, P.368, <100 km)* or *Ground-wave spherical
   (ITU-R P.368-10)*.
3. **Compute**.

**You should see** the mixed-path answer bracketed by the two homogeneous ones,
which is the physical sanity check that matters:

| quantity | reference run |
|---|---|
| homogeneous **land** | **20.9 dBµV/m** |
| **Millington mixed path** | **41.5 dBµV/m** |
| homogeneous **sea** | **57.6 dBµV/m** |

A mixed land/sea path must land *between* the two pure cases. If it does not,
the mixing is wrong, and no amount of agreement at the endpoints will tell you.

⛳ **The two engines disagree on purpose, and where they disagree is the
lesson.** Beyond about 212 km the flat-earth model reads **28.0 dBµV/m** while
the spherical P.368-10 reference reads **22.6 dBµV/m** — flat earth is
optimistic because it has no horizon. Inside ~100 km they agree; that is the
flat model's stated validity, and this is what leaving it silently is worth.

⚠ **Below 10 kHz the spherical model hard-stops** rather than extrapolating —
that is P.684's band, not P.368's. A model that answers outside its validity is
worse than one that refuses.

**Prove it** — `tests/validation/lfmf.py`.

## 31. Will my station interfere with theirs? (ITU-R P.452)

**Needs:** the **ITU P.452 digital maps** (`emstudio.coverage.itu_maps.install_p452_maps()`
— they are integral ITU products EMStudio may not redistribute, so you install
them once yourself).

⛳ **What P.452 is for.** It is the *coordination* model: basic transmission
loss between two terrestrial stations, evaluated at a **small percentage of
time**, because interference is a worst-case question. You are not asking "how
does this link usually behave" — you are asking "how good does the path get on
the rare occasions that hurt me".

**Do**
1. **Analysis ▸ Point-to-Point Link Budget**.
2. Set frequency, distance and antenna heights, then under **ITU-R terrestrial
   models** choose **ITU-R P.452-18**.
3. Set the **time percentage** and the **radio zone**, enter TX/RX latitude and
   longitude (they drive the digital-map lookups), and press **Analyze**.

**You should see** a basic transmission loss well above free space, and — this
is the part worth understanding — a loss that *falls* as the time percentage
falls:

| time % | inland | coastal | sea |
|---|---|---|---|
| 50 | 165.67 | 165.67 | 165.68 dB |
| 1 | 142.42 | 137.00 | **131.78 dB** |
| 0.01 | 128.07 | 127.05 | 126.30 dB |

*(2 GHz, 50 km, smooth earth — the run behind this table.)*

⛳ **Read the 50 % row before the others.** The radio zone changes nothing there
(0.01 dB), and changes it by **10.64 dB** at p = 1 %. That is not a bug: the
zone drives the ducting/anomalous term, which is simply not active half the
time. Ducting over **sea** is why a coastal interference path is the one that
bites — the rare hours are the ones that matter, and they are exactly the hours
the 50 % figure hides.

⚠ **Radio-zone codes are not shared between Recommendations** — P.452 numbers
them 1 coastal / 2 inland / 3 sea, P.2001 uses 1 sea / 3 coastal / 4 inland.
EMStudio gives you one human label and maps it. A wrong zone never raises; it
returns a believable loss for the wrong ground.

⚠ **The profile is smooth earth at 0 m AMSL, not your terrain**, and the
readout says so. It is a real member of the official validation set — but a
site answer needs a site profile.

**Prove it** — `tests/validation/p452.py`, which replays **595 official ITU
validation cases** (worst basic-transmission-loss deviation **5.0e-09 dB**) and
checks the wrapper reproduces the reference case to **194.249746 dB** vs the
official 194.24974628. It also confirms the engine refuses 60 GHz, outside
P.452's 0.1–50 GHz validity.

## 32. The whole distribution, not one number (ITU-R P.2001)

**Needs:** the **ITU P.2001 digital maps**
(`emstudio.coverage.itu_maps.install_p2001_maps()`).

⛳ **Why a second terrestrial model.** P.452 answers a worst-case coordination
question. **P.2001 answers a statistical one**: it is a general-purpose model,
30 MHz–50 GHz, valid at *any* time percentage from ~0.00001 % to 99.99999 %, so
it gives you the **distribution** of path loss — fades and enhancements both.
That is what a Monte-Carlo sharing study needs, and it is why the two models
exist side by side rather than one superseding the other.

**Do**
1. **Analysis ▸ Point-to-Point Link Budget**, then **ITU-R P.2001-6**.
2. Sweep the **time percentage** and watch the loss move. That sweep *is* the
   model's output.

**You should see** the same ordering as P.452 but a stronger zone effect, and —
the useful cross-check — near-identical agreement with P.452 at 50 %:

| quantity | reference run |
|---|---|
| P.2001 vs P.452 at p = 50 % | **165.67 dB both** — two independent engines |
| sea − inland at p = 1 % | **−23.06 dB** |
| sea − inland at p = 0.01 % | **−13.92 dB** |

⛳ **Two independently vendored implementations landing on the same 165.67 dB is
worth more than either number alone.** They share no code path.

⚠ **Validity is enforced, not assumed**: 0.03–50 GHz, path length 3–1000 km,
and 0 < Tpc < 100. Ask for Tpc = 0 and it refuses — "never exceeded" is not a
percentage, and a model that quietly returned a number there would be inventing
one.

**Prove it** — `tests/validation/p2001.py`, which replays **4,430 official ITU
validation cases** (worst deviation **1.17e-12 dB**) and reproduces the
reference case to **101.263441 dB** vs the official 101.2634406454913.

# Coverage — the standing order is met

> ✅ **Tutorials are available for every capability.** Every solver and every
> capability EMStudio ships is covered, and the four Pro ones carry public stubs
> giving what they do and the number they measured, with the walkthrough
> Pro-side. *"There is nothing showing how to use EMStudio"* is now factually
> unavailable — which was the entire point.

⚠ **Do not quote a tutorial COUNT in prose anywhere** — not in a post, not in a
README, not here. It goes stale the day the next one lands, and it already has:
a reply drafted on 2026-08-20 said "five" on the day the sixth shipped, in a
post whose whole argument was that this project's claims are checkable.
`tests/validation/tutorials_doc.py` fails the battery if one comes back.

**The numbering is stable and is the project's master list** — a tutorial keeps
its number everywhere it is referred to, so #12 is the cavity eigenmode one
wherever you see it cited.

🔒 marks a **Pro** capability. ⚠ Their stubs are held to a machine-checked
contract: what it does, what it measured, the free alternative with the tier
stated plainly, and its gate — and **no *Do* or *You should see* section**, so
a helpful edit cannot quietly turn a teaser into the paid walkthrough.

⛳ **Every entry now ends in a gated number — #23 was the last without one.**
Installing a backend has no measurable output, so the fix was to gate the
**readout** instead: the version each backend reports in the Solver Setup
table. ⚠ Looking for that anchor is what found the defects behind it, including
an Elmer "version" that carried a run timestamp and so changed every time the
user pressed Re-detect. **A capability with no anchor is a finding about the
capability** — and acting on the finding, rather than writing around it, is
what produced both a number and four fixes.

⛳ **What is still weaker than the rest, said plainly:** #10's Churchill rung is
a correlation rather than the exact conduction bound its first rung uses, and
#11's mesh-independent value is an extrapolation from three grids rather than a
single measurement — which no single run could be. Both say so in place.

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
