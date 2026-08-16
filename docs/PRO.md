# EMStudio Pro — available now, $149

EMStudio (this workbench) is free, open-source and stays that way. **EMStudio
Pro** is a separate add-on that adds the **System Designer**: the tools for
when you stop designing *one* antenna and start designing a *system* of them.

> **$149, one-time. Perpetual licence, no subscription, no account, no
> telemetry.** Buy it at **[ajj3us.gumroad.com](https://ajj3us.gumroad.com)** —
> you get a zip and a licence key. Not sure yet? **Try everything free for 14
> days**: the $0 trial download at the same store is the same zip — install
> it and press *Start free trial* instead of entering a key (no account;
> buying later simply replaces the trial). **Pro is an add-on, not a
> standalone workbench: install the free EMStudio workbench first** (FreeCAD →
> Tools → Addon manager → "EMStudio"), then install the zip from inside
> FreeCAD: **EMStudio → Help → EMStudio Pro — install / activate**. The
> numbers on this page are measured by the validation gates, not projected.

## Where the line falls

| | |
|---|---|
| **EMStudio (free)** | Design and validate **one** antenna, cable or coil. All four solvers, all templates, the complete Element Designer, the Cable Designer, magnetics, coverage, co-site — and every validation gate for it. |
| **EMStudio Pro** | Design a **system**: match it, filter it, phase it into an array, and find bearings with it. |

## What Pro adds

Each of these is measured on live solver runs, in an automated gate that runs
before every release.

**Impedance matching synthesis.** Your dipole reads 71.9 Ω; your radio wants
50 Ω. Pro synthesizes the network — L / π / T / quarter-wave / binomial
multisection / single-stub / hairpin — recommends the topology, snaps to E6-E96
standard values, and shows the VSWR you will actually get after that rounding.
Live-verified end to end: the shipped 71.9 Ω dipole matched to **VSWR 1.010**.

**Filter and diplexer synthesis.** Butterworth and Chebyshev ladders, LP→BP/BS
transforms, and both diplexer families. The contiguous constant-R diplexer holds
its composite input impedance to **under 1e-6 Ω at every order n = 1…7**; the
non-contiguous design assembles to **0.112 dB insertion loss, VSWR 1.38 and
34.8 dB port isolation**.

**Phased arrays that actually steer.** Arrays specify element *currents*, but
NEC2 drives *voltages* — Pro solves V = Z·I through the real mutual-impedance
matrix. The difference is not subtle: a cardioid pair measures **29.6 dB
front-to-back through the current solve versus 3.4 dB** for the naive
equal-voltage drive on the same wires. With amplitude tapers (binomial,
Dolph-Chebyshev, Taylor n̄), a steered 8-element Dolph array reproduces its
**−26.02 dB Chebyshev sidelobe floor to 0.04 dB on real coupled dipoles**,
against −12.7 dB for the uniform control — **13.4 dB of measured suppression
for 0.58 dB of peak gain.**

**RF direction finding.** Watson-Watt/Adcock with the octantal spacing error
*computed* from the exact crossed-pair response rather than assumed away;
multi-baseline interferometry with ambiguity resolution; pseudo-Doppler ring
sizing; and a correlative-interferometer manifold built from per-element NEC2
patterns, so mutual coupling and platform scattering are in it. That manifold
**decodes an independent receive simulation at 0.00° bearing error, correlation
1.000000** — and it quantifies what assuming ideal elements costs you: **1.78°**.

## Why the free version is not crippled

Because a free tier that does not work is not marketing, it is a demo. The free
workbench keeps every solver, every template, the entire Element Designer, the
Cable Designer, the full magnetics arc, coverage, co-site — **and all of its
validation gates.** The gates are the point: they are why you can believe any of
the numbers above.

Pro is not "the useful half". It is the part you need when one antenna becomes a
system.

## Questions

Ask on the [issue tracker](https://github.com/king-aj3/EMStudioFree/issues) or
through [ajj3.us](https://ajj3.us).

*EMStudio and EMStudio Pro are for educational, hobbyist and experimental use.
Engineering estimates only — verify independently. See
[DISCLAIMER](../DISCLAIMER.md).*
