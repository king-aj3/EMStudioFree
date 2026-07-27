# Examples

Ready-to-open FreeCAD documents, generated from the shipped templates. Open
one, switch to the **EMStudio** workbench, and press **Run Solver**.

| File | What it is | Solver | Expect |
|---|---|---|---|
| `dipole_300MHz.FCStd` | Centre-fed half-wave dipole | NEC2 | resonance near 300 MHz, feed Z ≈ 72 Ω |
| `monopole_vlf_100kHz.FCStd` | Short λ/10 base-fed monopole over ground | NEC2 + GN | strongly capacitive Z — this is what "electrically small" looks like |
| `patch_2p4GHz.FCStd` | Microstrip patch on a 2.4 GHz substrate | openEMS | S11 dip near 2.4 GHz |
| `coax_50ohm.FCStd` | Coaxial line section | Palace | ≈ 50 Ω characteristic impedance |

Each needs its solver installed — use **EMStudio → Setup → Detect / Install
Solvers**, which reports what is present and gives you one command for what is
missing. The analytic tools (Element Designer, Cable Designer) need no solver
at all.

You can regenerate any of these from scratch in one click: **EMStudio →
Templates**.

*Engineering estimates only — verify independently. See
[DISCLAIMER.md](../DISCLAIMER.md).*
