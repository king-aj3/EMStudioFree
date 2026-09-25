# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: printed inverted-F antenna (IFA) against openEMS's OWN example.

THE ANCHOR IS EXTERNAL, WHICH IS THE POINT
------------------------------------------
This gate rebuilds ``openEMS/matlab/examples/antennas/inverted_f.m`` -- (C) 2013
Stefan Mahr, shipped WITH openEMS so anyone can re-run it -- and solves it
through the product chain. That is the same class of anchor as
``patch_openems.py``, which reproduces openEMS's ``Simple_Patch_Antenna.py``.

⛳ Worth stating next to item A1: the n78 patch gate had no external anchor
available and had to be honest about being a consistency check between two of
our own models. **This one is not that.** The geometry is somebody else's,
published, and freely re-runnable.

⚠ The upstream file publishes NO expected numbers -- no resonance, no S11, no
gain; only the header title "ifa 2.4GHz" and a loss tangent referenced at
2.45 GHz. So the geometry is the reference and the WINDOW comes from the
quarter-wave rule in ``emstudio.antenna.ifa``, exactly as patch_openems takes
its 2.30-2.50 GHz window from the TL model rather than from the tutorial file.

⚠⚠ WHY THIS GATE ASSERTS FEED-POINT IMPEDANCE AND NOT JUST AN S11 DIP
----------------------------------------------------------------------
Because a resonance check alone CANNOT detect the failure this antenna actually
has. At the writer's default lambda/20 mesh the 0.5 mm port gap is not resolved
and the feed element is electrically SHORTED to the ground plane -- measured
**Zin = 0.05 + 9.52j ohm, S11 = -0.02 dB** -- and it *still reports a dip at
2.4524 GHz*, the RIGHT frequency, because the conductor path sets the resonance
whether or not the port is connected. A gate that checked only "is there a dip
near 2.45 GHz" would have passed a shorted antenna. Zin is the quantity that
tells a working antenna from a shorted one, so Zin is gated.

The template therefore sets MeshResolution itself, and this gate re-asserts that
it is still set -- see the convergence table in docs/upstream/ifa-anchors.md.
⚠ The writer's trace-aware refinement cannot help: writer.py:614 gates it on an
MSL port so that lumped-port antenna analyses stay byte-identical, and an IFA is
a lumped-port antenna with microstrip-scale features.

Expensive (full FDTD, ~30 s at the shipped mesh) -- NOT in the smoke suite.
Run:  freecadcmd tests/validation/ifa_openems.py
Pass: exit 0 and 'IFA GATE PASSED'.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: Every bound below prints one "  ok"/"  FAIL" line, so the battery can COUNT
#: what this gate checked. Until 2026-09-25 they were bare asserts: the gate
#: passed with ZERO countable lines, and a run that checked nothing looked the
#: same as one that checked everything. (The v1.13.0 proof log names this gate
#: in its "ZERO per-check lines" warning.)
FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _verdict():
    if FAILURES:
        print("IFA GATE FAILED: {0}".format(FAILURES))
        return 1
    print("IFA GATE PASSED")
    return 0

#: The 2.4 GHz ISM band, in Hz. Named because the headline claim this gate pins
#: is a statement ABOUT this band, and a bare 2.4e9 in an assert would hide what
#: is being compared to what.
ISM_LO_HZ = 2.400e9
ISM_HI_HZ = 2.4835e9

#: Below this the reference geometry does not solve correctly at all (see the
#: docstring). 40 is where the answer first agrees with the converged tail; the
#: template ships 60.
MIN_MESH = 40


def main():
    from emstudio.setup.solvers import find_openems_python

    if find_openems_python() is None:
        # NO self-skip-and-pass: freecadcmd drops print(), so a gate returning 0
        # from its own skip branch would report a success it never earned and
        # the exit code would be all a caller ever saw. Skipping is the
        # BATTERY's job (run_battery.SOLVER_REQS declares "openems_python");
        # a direct run must fail loudly, because you asked for it specifically.
        raise SystemExit(
            "openEMS is required for this gate and was not found -- set "
            "EMSTUDIO_OPENEMS_PYTHON, or install openEMS with its venv beside "
            "the binary. (The battery skips this gate automatically; a direct "
            "run does not.)")
    import numpy as np
    import FreeCAD

    from emstudio.antenna import ifa as ifa_engine
    from emstudio.solvers import openems
    from emstudio.templates import ifa as ifa_tpl

    # --- the analytic half: no solver needed, so it fails in milliseconds -----
    ref_path = (ifa_engine.REFERENCE["stub_height_m"]
                + ifa_engine.REFERENCE["radiator_length_m"])
    f_rule = ifa_engine.resonant_frequency(ref_path)
    print("ifa: reference path h+l = {0:.3f} mm -> quarter-wave rule "
          "{1:.4f} GHz".format(ref_path * 1e3, f_rule / 1e9))
    # The published geometry must keep implying a 2.4 GHz-class antenna. If the
    # REFERENCE dict is ever edited, this is what says so before a 30 s solve.
    # A FAIL here almost certainly means REFERENCE was edited.
    check("the reference geometry implies a 2.4 GHz ISM-class antenna "
          "(ISM +/-5 %)", ISM_LO_HZ * 0.95 <= f_rule <= ISM_HI_HZ * 1.05,
          "{0:.4f} GHz".format(f_rule / 1e9))

    doc = FreeCAD.newDocument("ifa_gate")
    ana = ifa_tpl.makeIFA(doc)

    # The mesh is load-bearing here in a way it is not for the patch gates.
    check("the template's MeshResolution is at least {0} (coarser solves as "
          "a SHORT that still dips at the right frequency — "
          "docs/upstream/ifa-anchors.md)".format(MIN_MESH),
          int(ana.MeshResolution) >= MIN_MESH,
          "{0}".format(ana.MeshResolution))
    if FAILURES:
        return _verdict()               # don't spend the solve on a known red

    solver = [o for o in ana.Group
              if getattr(o, "EMStudioType", "") == "EMStudio::SolverOpenEMS"][0]
    result = openems.run(ana, solver)

    f_min, s11_min = result.min_s11()
    i = int(np.argmin(result.s11_db()))
    zin = result.zin[i]
    print("ifa: FDTD best match {0:.2f} dB at {1:.4f} GHz ({2:+.2f} % vs the "
          "rule)".format(s11_min, f_min / 1e9, (f_min / f_rule - 1.0) * 100.0))
    print("ifa: feed-point Zin {0:.2f} {1:+.2f}j ohm".format(zin.real, zin.imag))
    print("ifa: run took {0:.1f} s at mesh {1} in {2}".format(
        result.meta.get("duration_s", -1), ana.MeshResolution,
        result.meta.get("workdir", "?")))

    # --- resonance, within the rule's stated +/-5 % --------------------------
    lo = f_rule * (1.0 - ifa_engine.IFA_ACCURACY)
    hi = f_rule * (1.0 + ifa_engine.IFA_ACCURACY)
    check("resonance within +/-{0:.0%} of the quarter-wave rule "
          "({1:.4f}-{2:.4f} GHz)".format(ifa_engine.IFA_ACCURACY,
                                         lo / 1e9, hi / 1e9),
          lo <= f_min <= hi, "{0:.4f} GHz".format(f_min / 1e9))

    # --- THE assertion: a fed antenna, not a shorted one ---------------------
    # Bands are wide on purpose. The point is not to pin 54.76 ohm -- that is a
    # mesh-dependent digit -- it is to separate "matched to a 50 ohm port" from
    # "shorted" (0.05 ohm) and from "badly wrong" (102 + 58j at mesh 30). Both
    # of those real, measured failures fall outside these bands by a wide
    # margin, and any plausible good answer falls inside.
    check("feed-point R is a 50 ohm-class match (30-80 ohm; a SHORTED port "
          "reads ~0)", 30.0 <= zin.real <= 80.0, "{0:.2f} ohm".format(zin.real))
    check("feed-point |X| <= 15 ohm (resonant at its own best match)",
          abs(zin.imag) <= 15.0, "{0:+.2f}j ohm".format(zin.imag))
    check("S11 dips below -10 dB", s11_min < -10.0, "{0:.2f} dB".format(s11_min))

    # --- bandwidth: the headline claim, gated -------------------------------
    # An IFA is a genuinely wideband element, which is exactly why every Wi-Fi
    # and BLE board uses one instead of a patch. The gated form of that
    # sentence is that its -10 dB band COVERS the whole ISM band -- the mirror
    # image of patch_n78_openems, where the assertion is that a thin patch
    # canNOT cover n78.
    db = result.s11_db()
    in_band = [x for x, d in zip(result.freq, db) if d <= -10.0]
    check("some frequency reaches -10 dB", bool(in_band),
          "{0} samples".format(len(in_band)))
    if in_band:
        b_lo, b_hi = min(in_band), max(in_band)
        bw = b_hi - b_lo
        print("ifa: -10 dB bandwidth {0:.1f} MHz ({1:.2f} %), {2:.4f}-{3:.4f} GHz"
              .format(bw / 1e6, bw / f_min * 100.0, b_lo / 1e9, b_hi / 1e9))
        check("the -10 dB band covers the whole 2.4 GHz ISM band "
              "({0:.4f}-{1:.4f} GHz; tutorial 35 says an IFA does)".format(
                  ISM_LO_HZ / 1e9, ISM_HI_HZ / 1e9),
              b_lo <= ISM_LO_HZ and b_hi >= ISM_HI_HZ,
              "{0:.4f}-{1:.4f} GHz".format(b_lo / 1e9, b_hi / 1e9))

    # --- far field: IFA-class, and NOT patch-like ---------------------------
    ff = getattr(result, "farfield", None)
    check("openEMS produced a far field", ff is not None)
    if ff is not None:
        g_peak, th_peak, _ = ff.peak()
        print("ifa: peak gain {0:.2f} dBi at theta={1:.0f} deg".format(
            g_peak, th_peak))
        check("peak gain within 0-6 dBi (a printed IFA on a small board is "
              "low-gain)", 0.0 <= g_peak <= 6.0, "{0:.2f} dBi".format(g_peak))

    return _verdict()


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("ifa validation failed")
    sys.exit(0)
