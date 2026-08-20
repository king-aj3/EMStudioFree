# Examples

Ready-to-open FreeCAD documents, generated from the shipped templates. Open
one, switch to the **EMStudio** workbench, and press **Run Solver**.

These are *inputs*, not saved results — nothing here has been solved, so the
files stay small and the numbers you get are your own.

| File | What it is | Solver | Expect |
|---|---|---|---|
| `dipole_300MHz.FCStd` | Centre-fed half-wave dipole | NEC2 | resonance near 300 MHz, feed Z about 72 ohm |
| `monopole_vlf_100kHz.FCStd` | Short lambda/10 base-fed monopole over ground | NEC2 + GN | strongly capacitive Z — this is what electrically small looks like |
| `yagi_400MHz.FCStd` | Yagi-Uda sized from NBS TN-688, 0.8 lambda boom | NEC2 | forward gain about 9.1 dBd with front-to-back in the 13-19 dB band |
| `lpda_54_216MHz.FCStd` | Carrel log-periodic across the VHF-TV band, real TL-card feeder | NEC2 | usable VSWR across the whole 54-216 MHz span, not just at one spot |
| `patch_2p4GHz.FCStd` | Inset-fed microstrip patch synthesised from frequency and substrate | openEMS | S11 dip within the transmission-line model's stated +/-5 % of 2.4 GHz |
| `notch_filter_msl.FCStd` | Microstrip notch filter with trace-aware meshing | openEMS | an S21 notch that matches analytic theory (gated to 0.6 %) |
| `coax_50ohm.FCStd` | Coaxial line section | Palace | characteristic impedance about 50 ohm |
| `waveguide_wr90.FCStd` | WR-90 rectangular waveguide, X-band | Palace | TE10 propagation above the 6.56 GHz cutoff |
| `waveguide_wr22_40GHz.FCStd` | WR-22 rectangular waveguide, Ka-band (mmWave) | Palace | matched TE10 across 38-42 GHz, well above the 26.3 GHz cutoff |
| `circwaveguide.FCStd` | Circular waveguide | Palace | TE11 as the dominant mode — compare with the analytic cutoff |
| `cavity_rect.FCStd` | Rectangular cavity eigenmodes | Palace | the first six modes, TE101 lowest |
| `cavity_cyl.FCStd` | Cylindrical cavity eigenmodes | Palace | the first six modes of a 30 mm-radius can |
| `solenoid_3d.FCStd` | General 3-D solenoid, magnetostatic on a real solid | Elmer | an on-axis B field that tracks the closed form to well under 1 % |
| `induction_billet.FCStd` | Induction heating: steel billet inside a work coil | Elmer | eddy-current power in the billet, plus the thermal chain |
| `wpt_coil_pair.FCStd` | Wireless-power transfer coil pair | Elmer | L, M and the coupling coefficient k for the gap |
| `cosite_pair_300MHz.FCStd` | Two-dipole co-site pair | NEC2 | port-to-port isolation as a function of spacing |

Each needs its solver installed — use **EMStudio → Setup → Detect / Install
Solvers**, which reports what is present and gives you one command for what is
missing. The analytic tools (Element Designer, Cable Designer) need no solver
at all.

You can regenerate any of these from scratch in one click: **EMStudio →
Templates**.

*Engineering estimates only — verify independently. See
[DISCLAIMER.md](../DISCLAIMER.md).*
