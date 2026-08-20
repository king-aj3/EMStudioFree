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

# The first five

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

⛳ **Why this is in the first five.** EMStudio is not only an antenna tool. The
Cable Designer does litz (Types 1–9), coax, twisted pair and multi-conductor
bundles with crosstalk, ampacity and thermal rise — and it needs no solver
installed at all.

---

# The rest of the series — planned order

Written, but living in [the user manual](USER_MANUAL.md) rather than here yet.
The job is to give each one the four-part shape above and a named gate.

| # | Tutorial | Needs | Anchor it should quote |
|---|---|---|---|
| 6 | Simulate **your own** geometry | openEMS | the workflow, not a number |
| 7 | Analysing an **STL** file | openEMS | same patch, same window, via STL |
| 8 | **Coax** S-parameters | Palace | Z0 ≈ 49.94 Ω air line |
| 9 | **WR-90 waveguide** | Palace | TE10 cutoff 6.56 GHz |
| 10 | **Cavity eigenmodes** | Palace | first six modes, TE101 lowest |
| 11 | **Monopole over ground** (VLF) | NEC2 | what electrically small looks like |
| 12 | **Induction heating** | Elmer | TEAM Problem 7, 2.83 % RMS vs measured |
| 13 | **Wireless power** coil pair | Elmer | L, M and k vs gap |
| 14 | **Litz** cable design | nothing | IEC 60287 worked examples |
| 15 | **Thermal / CFD** on your own solid | OpenFOAM | +4.3 % vs Churchill (sphere) |
| 16 | **Co-site isolation** | NEC2 | port-to-port isolation vs spacing |
| 17 | **Coverage** maps | nothing | ITU-R P.1546 / P.1812 reference runs |

---

## Notes for whoever writes 6–17

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
