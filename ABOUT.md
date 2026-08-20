# About EMStudio

> **For educational, hobbyist and experimental use.** EMStudio is a learning
> and exploration tool, not a certified engineering product — and it is
> **under active development**, so features, defaults and results may change
> between versions. More to come.
>
> Inside FreeCAD this page's contents and the full legal notice are always
> available under **EMStudio → Help → About / Legal notice & disclaimer**.

**EMStudio's mission:** make electromagnetic RF / antenna / PCB / wire engineering
analysis and simulation **as simple as possible** — using real-world calculations,
professional tools, and clear visualization — with minimal effort and minimal
prerequisite theory on the user's part.

And then take it one step further: generate **professional deliverables** — reports,
BOMs, build/construction specs, and presentation-quality data and plots — so that
users can hand their ideas to part houses, wire manufacturers, and fabrication
suppliers and have their creations *built for them*, even if they don't have the
means to build in-house.

## What it is

A free, open-source workbench for [FreeCAD](https://www.freecad.org) that wraps
best-of-breed open-source electromagnetic solvers (openEMS, NEC2, FastHenry, Elmer,
and AWS Palace) behind a guided workflow: geometry → materials → ports → automatic
meshing → solve → results. The same category of product as CENOS RF or Ansys
HFSS-class tools — priced at zero, and open. Beyond the field solvers it also carries
**system-level** engineering tools — VLF/LF small-antenna analytics, co-site
interference / EMC, and geographic coverage / propagation (link budgets, terrain
shadowing, LF/MF ground-wave) — each with its own validated regime.

## Principles

1. **Validated, not just plausible.** Every physics feature ships with an automated
   gate against literature, published references, or an independent field solver.
   The dipole reads 71.9 Ω because a dipole *is* ~72 Ω.
2. **Real engineering conventions.** AWG strand gauges, S/Z lay directions,
   New England Wire's litz taxonomy, Touchstone files — the artifacts professionals
   and suppliers already use.
3. **Nothing hidden.** Solver decks, raw outputs, and CSVs stay on disk where you can
   inspect them. The workbench is LGPL; the solvers are invoked as separate processes
   under their own licenses.
4. **Minimal-effort first.** Templates give a validated result in minutes; every
   default is chosen so the first run works.
5. **AI was used to build this, and that changes nothing about principle 1.**
   I used AI assistance heavily — writing code, drafting documentation, working
   through the physics. I am one person doing this in evenings and weekends, and
   it would not exist otherwise. Saying so plainly is better than letting you
   discover it: the GitHub descriptions and an early version of the website read
   like a brochure because of it, and that was a fair thing to call out.
   What the AI did not do is decide what counts as correct. Every number this
   tool prints is checked by a test you can run yourself against published
   references — TEAM Problem 7's measured points, the NBS TN-688 Yagis, closed
   forms, or a second solver. **That is the part that matters, and it is the part
   you should judge it on.** Do not take the prose on trust; run
   `python3 tests/validation/run_battery.py` and take the numbers instead.

## Disclaimer

EMStudio is for **educational, hobbyist and experimental use**, and its outputs
are engineering **estimates** — never guarantees. Users must independently
verify every result before relying on it and are solely responsible for their
designs, for regulatory and RF-safety compliance, and for anything built or
operated from these outputs. The software is provided AS IS with no warranty of
any kind; the author, contributors, and the AJJ³ project accept **no
responsibility and no liability** for any damage, injury, loss, interference or
cost. Read [DISCLAIMER](DISCLAIMER.md) before use.

## Names and branding

The code is LGPL; the **EMStudio** and **AJJ³** names, logo and icon set are
not. Forks must rename and drop AJJ³ branding — see
[TRADEMARK](TRADEMARK.md).

## Credits

Built on the shoulders of: openEMS (Thorsten Liebig), nec2c (N. Kyriazis / Lawrence
Livermore NEC2), FastHenry (MIT / FastFieldSolvers), FreeCAD, Gmsh, and the published
work of C.R. Sullivan, J.A. Ferreira, and A.D. Watt on winding losses.

License: LGPL-2.1-or-later. See [LICENSE](LICENSE).
