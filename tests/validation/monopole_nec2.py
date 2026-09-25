# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: VLF/LF monopole over ground via the NEC2 backend.

Proves NEC2 driven at LF WITH a ground model — the §4 VLF slice (the prior NEC2
validated point was 296 MHz free-space; low frequency + ground was unproven).

Physics references (A.D. Watt, *VLF Radio Engineering*, 1967; Balanis):
* Short monopole h = lambda/10 over PERFECT ground: feedpoint R approaches the
  radiation resistance Rr = 40*pi^2*(h/lambda)^2 = 3.948 ohm, strongly capacitive.
  (nec2c 1.3.1 lands ~4.0 ohm at ~130 segments — the numerical current sum sits a
  couple percent above the ideal-triangular-current closed form; gate on measured.)
* Quarter-wave monopole (h = lambda/4) over perfect ground: Zin ~= 36.5 + j21 ohm
  (half the 73 + j42.5 ohm dipole).
* Over FINITE (Sommerfeld) ground, ground loss adds series resistance, so the
  feedpoint R rises far above Rr and the radiation efficiency Rr/Re(Zin) collapses
  — the defining VLF reality (a real antenna needs a large radial ground system).

Run:  freecadcmd tests/validation/monopole_nec2.py
Pass: exit 0 and 'MONOPOLE GATE PASSED'.
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


def _zin_at(result, f_hz):
    import numpy as np

    i = int(np.argmin(np.abs(result.freq - f_hz)))
    return complex(result.zin[i])


def main():
    import FreeCAD

    from emstudio.objects import query
    from emstudio.solvers import nec2
    from emstudio.templates import monopole

    C0 = 299792458.0
    f0 = 100e3
    rr_analytic = 40.0 * 3.141592653589793 ** 2 * 0.1 ** 2  # h=lambda/10 -> 3.948 ohm

    # --- 1. short lambda/10 monopole over PERFECT ground ---
    doc = FreeCAD.newDocument("mono_perfect")
    ana = monopole.makeMonopole(doc, f0_hz=f0, height_frac=0.1,
                                ground="Perfect (PEC image)")
    solver = query.get_solvers(ana)[0]
    res = nec2.run(ana, solver)
    z = _zin_at(res, f0)
    r_perfect = z.real
    print("short monopole (perfect): Zin = {0:.3f}{1:+.3f}j ohm "
          "(analytic Rr {2:.3f})".format(z.real, z.imag, rr_analytic))
    check("lambda/10 over perfect ground: Re(Zin) within 3.75-4.30 ohm "
          "(nec2c ~4.0, Rr 3.948)", 3.75 <= r_perfect <= 4.30,
          "{0:.3f} ohm".format(r_perfect))
    check("lambda/10 over perfect ground is strongly capacitive "
          "(Im(Zin) < -400 ohm)", z.imag < -400.0, "{0:.1f} ohm".format(z.imag))
    FreeCAD.closeDocument(doc.Name)

    # --- 2. quarter-wave monopole over PERFECT ground (~36.5 + j21 ohm) ---
    doc = FreeCAD.newDocument("mono_quarter")
    ana = monopole.makeMonopole(doc, f0_hz=f0, height_frac=0.25,
                                ground="Perfect (PEC image)")
    solver = query.get_solvers(ana)[0]
    res = nec2.run(ana, solver)
    zq = _zin_at(res, f0)
    print("quarter-wave monopole (perfect): Zin = {0:.3f}{1:+.3f}j ohm "
          "(textbook 36.5 + j21)".format(zq.real, zq.imag))
    check("lambda/4 over perfect ground: Re(Zin) within 33-43 ohm "
          "(textbook 36.5)", 33.0 <= zq.real <= 43.0,
          "{0:.2f} ohm".format(zq.real))
    check("lambda/4 over perfect ground: Im(Zin) within +5..+32 ohm "
          "(textbook +21)", 5.0 <= zq.imag <= 32.0, "{0:+.2f} ohm".format(zq.imag))
    FreeCAD.closeDocument(doc.Name)

    # --- 3. short monopole over FINITE (average) ground: efficiency collapses ---
    doc = FreeCAD.newDocument("mono_finite")
    ana = monopole.makeMonopole(doc, f0_hz=f0, height_frac=0.1,
                                ground="Finite (Sommerfeld)")
    solver = query.get_solvers(ana)[0]  # default eps_r 13, sigma 0.005 (avg ground)
    res = nec2.run(ana, solver)
    zf = _zin_at(res, f0)
    r_finite = zf.real
    efficiency = rr_analytic / r_finite if r_finite > 0 else 0.0
    print("short monopole (finite avg ground): Zin = {0:.2f}{1:+.2f}j ohm, "
          "efficiency ~= {2:.1%}".format(zf.real, zf.imag, efficiency))
    check("finite ground adds loss resistance (R > perfect + 5 ohm)",
          r_finite > r_perfect + 5.0,
          "{0:.2f} vs perfect {1:.2f} ohm".format(r_finite, r_perfect))
    check("ground-loss efficiency within the VLF range (0.5-40 %)",
          0.005 <= efficiency <= 0.40, "{0:.1%}".format(efficiency))
    FreeCAD.closeDocument(doc.Name)

    if FAILURES:
        print("MONOPOLE GATE FAILED: {0}".format(FAILURES))
        return 1
    print("MONOPOLE GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    # freecadcmd exits 0 on uncaught exceptions — convert every failure to
    # SystemExit, which does propagate a non-zero exit code.
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("monopole validation failed")
    sys.exit(0)
