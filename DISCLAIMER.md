# Disclaimer — No Warranty · Use Entirely at Your Own Risk

**READ THIS BEFORE USING EMSTUDIO OR RELYING ON ANYTHING IT PRODUCES.**
By installing, running, or using EMStudio or any of its outputs, you acknowledge
and agree to all of the following. If you do not agree, do not use the software.

> This notice is also available inside FreeCAD at any time:
> **EMStudio → Help → Legal notice & disclaimer**, and a summary is shown once
> per installed version when the workbench is first activated.

## 0. Intended use — educational, hobbyist and experimental

EMStudio is intended for **educational, hobbyist and experimental use**. It is
a learning and exploration tool for students, radio amateurs, makers,
experimenters and engineers who want to build intuition and try ideas.

It is **not** a certified engineering product, **not** a qualified substitute
for professional engineering judgement, measurement, or regulatory compliance
work, and **not** validated for production design sign-off. If a decision
matters — because money, property, spectrum, or safety depend on it — it must
be checked by other means and, where appropriate, by a qualified and licensed
engineer.

EMStudio is also **under active development**. Features are still being added,
refined and re-validated; interfaces, defaults and computed results may change
between versions; and some areas of the workbench are considerably more mature
than others. Treat every version as work in progress.

## 1. No warranty of any kind

EMStudio is provided **"AS IS" and "AS AVAILABLE", without warranty of any
kind**, express or implied, including but not limited to the implied warranties
of **merchantability**, **fitness for a particular purpose**, **accuracy**,
**reliability**, **completeness**, and **non-infringement**. The entire risk as
to the quality, performance, and results of the software is with **you**. This
restates and supplements the warranty disclaimer and limitation of liability in
the software's license (GNU LGPL-2.1, sections 15–16), which governs.

## 2. Simulation results are estimates — never facts

EMStudio is a modeling, simulation, and analysis tool. **Every** number, curve,
field map, report, specification, bill of materials, design suggestion, solver
result, coverage map, crosstalk estimate, ampacity figure, or other output it
produces is an **engineering estimate** that can be wrong — sometimes badly and
silently wrong — due to, among other things:

- software defects in EMStudio itself,
- defects or limitations in the third-party solvers it drives,
- inherent limitations and simplifications of the underlying physical models,
- use of a model outside its validity range,
- meshing, discretization, and numerical error,
- incorrect, incomplete, or unrealistic user inputs,
- differences between idealized models and real materials, tolerances,
  manufacturing variation, and environments.

Statements in the documentation that a feature is **"validated"** mean only
that the specific test cases in the project's validation suite reproduced the
specific reference values cited, on the developer's machine, at the time of
testing. **Validation of a test case is not a guarantee of accuracy for your
case.**

## 3. You must independently verify everything

**You are solely responsible for independently verifying every result before
any reliance on it** — by measurement, prototyping, independent calculation,
established engineering references, and/or review by a qualified (and where
applicable, licensed) engineer. Do not manufacture, purchase, deploy, energize,
transmit, or certify anything based on EMStudio outputs without independent
verification. EMStudio and its documentation are **not professional engineering
advice**, and no engineer–client or advisory relationship is created by their
use.

## 4. No safety-critical, life-critical, or high-risk use

EMStudio is **not designed, intended, tested, or licensed** for use in any
application where failure or inaccuracy could lead to death, personal injury,
or severe physical, property, or environmental damage — including but not
limited to medical or life-support systems, aviation and spaceflight, nuclear
facilities, weapons systems, safety interlocks, or critical infrastructure.
Any such use is entirely at your own risk and against the intended use of the
software.

## 5. Regulatory, legal, and RF-safety compliance is yours

Radio-frequency design and operation are regulated. **You are solely
responsible** for compliance with all applicable laws, regulations, and
standards — including spectrum licensing and authorization, transmitter power
and emission limits, EMC/EMI requirements, human RF-exposure limits (e.g.
FCC/ICNIRP), product-safety and wiring codes (e.g. ampacity and insulation
ratings), and export-control rules — in every jurisdiction where you use the
software or anything derived from it. EMStudio's outputs (e.g. coverage maps,
power levels, ampacity estimates) do **not** establish or imply regulatory
compliance.

## 6. Limitation of liability

To the maximum extent permitted by applicable law, in no event shall the
authors, copyright holders, contributors, maintainers, or the **AJJ³** project
be liable for **any** claim, damages, or other liability — whether in an action
of contract, tort (including negligence), strict liability, or otherwise —
arising from, out of, or in connection with the software, its outputs, or the
use of or inability to use either, including without limitation: personal
injury or death; damage to or destruction of equipment, devices, antennas,
transmitters, receivers, property, or other systems; radio interference caused
to others; data loss; loss of profits, revenue, or business; regulatory fines
or enforcement; and any direct, indirect, incidental, special, exemplary,
punitive, or consequential damages — **even if advised of the possibility of
such damages**. Where a jurisdiction does not allow certain exclusions, the
liability of the above parties is limited to the greatest extent permitted —
and note that the software is provided **free of charge**.

## 7. Assumption of risk and hold harmless

You assume **all** risk arising from your use of the software and its outputs.
To the extent permitted by law, you agree to **hold harmless** the authors,
copyright holders, contributors, maintainers, and the AJJ³ project from any
claims, liabilities, losses, and expenses (including legal fees) arising from
your use of the software or its outputs, including claims brought by third
parties harmed by designs, devices, transmissions, or decisions derived from
them.

## 8. Third-party software

EMStudio drives external solver programs (openEMS, NEC2, Elmer, AWS Palace,
FastHenry, gmsh, and others) as separate, unmodified subprocesses. These are
independent projects under their own licenses and their own disclaimers; the
EMStudio authors make **no warranty whatsoever** for their behavior, accuracy,
or fitness, and are not responsible for defects in or damage caused by them.

## 9. Documentation, examples, and presets

All documentation, tutorials, examples, presets, and reference values (e.g.
cable presets, material properties, protection ratios) are provided for
convenience only, may contain errors, and are subject to the same disclaimers
as the software. Verify them against primary sources before use.

## 10. Names and branding

The source code is licensed under the LGPL; the **EMStudio** and **AJJ³**
names, the AJJ³ logo and icon set, and ajj3.us are **not** licensed with it.
Forks and modified redistributions must rename and remove AJJ³ branding, and
nothing here grants any right to imply endorsement by or affiliation with the
AJJ³ project. See [TRADEMARK](TRADEMARK.md).

---

*This file is a plain-language notice, not legal advice, and does not replace
the software license. The GNU Lesser General Public License v2.1 (see
`LICENSE`) governs the software, including its warranty disclaimer (§15) and
limitation of liability (§16).*
