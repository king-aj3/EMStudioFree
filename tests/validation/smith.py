#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the Smith-chart map, its grid geometry and its read-outs.

Pass: exit 0 and 'SMITH GATE PASSED'.

⚠⚠ THE TRAP THIS GATE IS WRITTEN AROUND. Almost every statement about a Smith
chart is an IDENTITY, and an identity the implementation satisfies BY
CONSTRUCTION cannot be the only check on it — CLAUDE.md says so, and a chart is
where that bites hardest. "Γ(Z0) = 0" is true of any correct-looking algebra and
also of several wrong ones.

So the load-bearing checks here are the CROSS ones, where two independent routes
must agree:

  * the circle formulas are checked by SAMPLING REAL IMPEDANCES, mapping each
    through ``gamma_from_z``, and confirming the images land on the circle the
    closed form predicts. ``r_circle``/``x_circle`` never touch ``gamma_from_z``,
    so agreement to 1e-12 across thousands of points is evidence, not tautology;
  * VSWR is checked against ``SweepResult.vswr()`` — the number the product has
    ALREADY been showing on its own tab since v0.8.0. If the chart and the VSWR
    tab ever disagree, one of them is lying to the user, and this is where that
    surfaces;
  * return loss is checked to be the EXACT negation of ``SweepResult.s11_db()``.
    Both conventions are in circulation and mixing them is a silent sign error;
  * and both of those are repeated (section 6b) on a WAVEGUIDE fixture, where
    the solver's Γ and a Γ re-derived from the stored ``z0`` are DIFFERENT
    NUMBERS. Section 6 on its own CANNOT FAIL: its ``SweepResult`` derives
    ``s11`` from ``(zin, z0)``, so both sides of every comparison there are the
    same arithmetic and they agree for a chart that quietly recomputes Γ from
    the impedance. That is how a Smith title reading VSWR 1.23 / 19.7 dB
    shipped green beside a VSWR tab reading 1.07 / 29.6 dB for the same solve
    at the same frequency (2026-08-29 audit, findings 29 and 30).
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(label, ok, detail=""):
    print("  %-5s %s%s" % ("PASS" if ok else "FAIL", label,
                           "" if ok else "  -- " + detail))
    if not ok:
        FAILURES.append(label)


def main():
    import numpy as np
    from emstudio.post import smith
    from emstudio.post.sparams import SweepResult

    Z0 = 50.0

    # -- 1. the three landmarks, and the one that needs a limit ---------------
    check("matched load -> chart centre",
          abs(smith.gamma_from_z(Z0, Z0)) < 1e-15)
    check("short (Z=0) -> Gamma = -1",
          abs(complex(smith.gamma_from_z(0.0, Z0)) + 1.0) < 1e-15)
    g_open = complex(smith.gamma_from_z(1e15, Z0))
    check("open (Z->inf) -> Gamma -> +1", abs(g_open - 1.0) < 1e-12,
          "got %r" % g_open)

    # -- 2. a lossless load cannot absorb power, so |Gamma| = 1 EXACTLY -------
    xs = np.array([1e-6, 0.5, 5.0, 50.0, 137.3, 5.0e4])
    g = smith.gamma_from_z(1j * xs, Z0)
    check("pure reactance lies ON the unit circle",
          np.max(np.abs(np.abs(g) - 1.0)) < 1e-12,
          "worst |Gamma| error %.2e" % np.max(np.abs(np.abs(g) - 1.0)))

    # -- 3. CROSS-CHECK: sampled impedances land on the predicted R-circles ---
    #    Not by construction — the circle formula and the map are independent.
    worst_r = 0.0
    for r in (0.0, 0.2, 1.0, 3.0, 7.5, 50.0):
        Z = Z0 * (r + 1j * np.linspace(-500.0, 500.0, 5001))
        gg = smith.gamma_from_z(Z, Z0)
        (cx, cy), rad = smith.r_circle(r)
        err = np.max(np.abs(np.abs(gg - complex(cx, cy)) - rad))
        worst_r = max(worst_r, err)
    check("constant-R circles match the mapped impedances (6 values of r)",
          worst_r < 1e-12, "worst radial error %.2e" % worst_r)

    worst_x = 0.0
    for x in (-5.0, -1.0, -0.2, 0.2, 1.0, 5.0):
        Z = Z0 * (np.linspace(0.0, 1000.0, 5001) + 1j * x)
        gg = smith.gamma_from_z(Z, Z0)
        (cx, cy), rad = smith.x_circle(x)
        err = np.max(np.abs(np.abs(gg - complex(cx, cy)) - rad))
        worst_x = max(worst_x, err)
    check("constant-X arcs match the mapped impedances (6 values of x)",
          worst_x < 1e-12, "worst radial error %.2e" % worst_x)

    # -- 4. inductive above the axis, capacitive below -----------------------
    check("inductive load sits in the UPPER half",
          complex(smith.gamma_from_z(50 + 30j, Z0)).imag > 0)
    check("capacitive load sits in the LOWER half",
          complex(smith.gamma_from_z(50 - 30j, Z0)).imag < 0)
    check("a real load sits ON the real axis",
          abs(complex(smith.gamma_from_z(120 + 0j, Z0)).imag) < 1e-15)

    # -- 5. round trip -------------------------------------------------------
    Z = np.array([73.1 + 42.5j, 12.0 - 300.0j, 50.0 + 0j, 200.0 + 5.0j])
    back = smith.z_from_gamma(smith.gamma_from_z(Z, Z0), Z0)
    check("z -> Gamma -> z round trip", np.allclose(back, Z, atol=1e-9),
          "worst %.2e" % np.max(np.abs(back - Z)))

    # -- 6. CROSS-CHECK against what the product ALREADY shows ---------------
    #    ⚠ This fixture's ``s11`` is DERIVED by ``SweepResult`` from
    #    ``(zin, z0)``, so the checks below can only prove that the two modules
    #    agree on the MAP. They cannot prove the chart reads the solver's Γ
    #    instead of recomputing one — both routes are the same arithmetic here.
    #    Section 6b carries that promise; do not add a "nothing re-derived"
    #    check to this block, it would be an identity that always passes.
    freq = np.linspace(1e9, 2e9, 51)
    zin = 30.0 + 40.0 * np.sin(np.linspace(0, 3, 51)) + \
        1j * (60.0 * np.cos(np.linspace(0, 3, 51)))
    res = SweepResult(freq, zin, z0=Z0)
    check("chart VSWR == the VSWR tab's own numbers",
          np.allclose(smith.vswr_from_gamma(res.s11), res.vswr(), rtol=0, atol=1e-12),
          "the chart and the VSWR tab would show different numbers")
    check("return loss is the EXACT negation of the S11 tab's dB",
          np.allclose(smith.return_loss_db(res.s11), -res.s11_db(), atol=1e-12),
          "sign convention has drifted between the two read-outs")
    # Two independent spellings of one map: sparams.py forms (zin − ref) /
    # (zin + ref) directly, smith.py normalises first and then applies
    # (z − 1)/(z + 1). Agreement is worth having — it is NOT, however, the
    # "nothing re-derived" promise, which needs a Γ the class did not compute.
    check("SweepResult's own s11 derivation matches the chart's map",
          np.allclose(smith.gamma_from_z(res.zin, res.z0), res.s11, atol=1e-15))

    # -- 6b. the same cross-checks, on a fixture where they can FAIL ---------
    #    ⚠⚠ THE PORT TYPE THAT BREAKS THE PROMISE. A lumped, coax or microstrip
    #    port references the whole band to ONE impedance, which is why section 6
    #    cannot fail. A WAVEGUIDE port cannot: its reference is the modal
    #    impedance Z_TE(f) = eta0 / sqrt(1 − (fc/f)^2) (Pozar, *Microwave
    #    Engineering*, §3.3), which across the shipped Ka-band horn's WR-28
    #    (broad wall a = 7.112 mm, so fc = 21.077 GHz) runs 621.5 ohm at
    #    26.5 GHz down to 443.3 ohm at 40 GHz. ``SweepResult`` keeps that
    #    column in ``z0_f`` and carries ONE band-summary number in ``z0``, so
    #    here the solver's Γ and a Γ re-derived from ``z0`` really are different
    #    numbers — which is what turns the checks below from algebra into
    #    evidence. This is the shape every openEMS RectWaveguide run produces.
    eta0 = 376.730313668                       # free-space wave impedance, ohm
    fc_wr28 = 299792458.0 / (2.0 * 7.112e-3)   # TE10 cutoff = c / 2a, WR-28
    f_ka = np.linspace(26.5e9, 40.0e9, 51)     # the shipped horn's own band
    z0_col = eta0 / np.sqrt(1.0 - (fc_wr28 / f_ka) ** 2)
    zin_wg = z0_col * (1.03 + 0.06j)           # a well-matched horn
    # Γ as the RUNNER supplies it — referenced per frequency, and formed HERE
    # so the fixture does not borrow the arithmetic it is about to check.
    s11_wg = (zin_wg - z0_col) / (zin_wg + z0_col)
    wg = SweepResult(f_ka, zin_wg, z0=z0_col, s11=s11_wg)

    # The negative control on the fixture itself. If a future change to
    # SweepResult collapsed the reference column back to a scalar, every check
    # below would go on passing while testing nothing — this is what says so.
    # 0.05 in Γ is ~0.1 of VSWR and several dB of return loss: visible on screen.
    spread = float(np.max(np.abs(smith.gamma_from_z(wg.zin, wg.z0) - wg.s11)))
    check("waveguide fixture DISCRIMINATES a re-derived Gamma", spread > 0.05,
          "only %.4f apart — this fixture has decayed into section 6's and the "
          "checks below prove nothing" % spread)
    check("chart VSWR == the VSWR tab's, on a SUPPLIED Gamma",
          np.allclose(smith.vswr_from_gamma(wg.s11), wg.vswr(), rtol=0,
                      atol=1e-12),
          "the chart and the VSWR tab would show different numbers")
    check("return loss == -(S11 tab dB), on a SUPPLIED Gamma",
          np.allclose(smith.return_loss_db(wg.s11), -wg.s11_db(), atol=1e-12),
          "sign convention has drifted between the two read-outs")

    i = int(np.argmin(wg.s11_db()))            # the bin the star marker sits on
    ro = smith.readout(wg.zin[i], wg.z0, gamma=wg.s11[i])
    check("the star's read-out IS the solve's Gamma (nothing re-derived)",
          abs(ro["gamma"] - complex(wg.s11[i])) < 1e-15
          and abs(ro["vswr"] - float(wg.vswr()[i])) < 1e-12
          and abs(ro["return_loss_db"] + float(wg.s11_db()[i])) < 1e-12,
          "chart says VSWR %.4f / %.3f dB where the tabs say %.4f / %.3f dB"
          % (ro["vswr"], ro["return_loss_db"], wg.vswr()[i], -wg.s11_db()[i]))
    # A read-out normalised at ONE frequency has to reach for z0_at(f), never
    # the band label z0 — and this is what proves z0_at returns the reference
    # the runner's Γ was actually taken against, rather than a plausible
    # interpolation of the wrong column.
    g_at = complex(smith.gamma_from_z(wg.zin[i], wg.z0_at(wg.freq[i])))
    check("z0_at(f) is the reference the supplied Gamma was taken against",
          abs(g_at - complex(wg.s11[i])) < 1e-12,
          "off by %.2e" % abs(g_at - complex(wg.s11[i])))

    # -- 7. VSWR rings invert cleanly ----------------------------------------
    for s in (1.2, 1.5, 2.0, 5.0):
        rad = smith.gamma_radius_for_vswr(s)
        check("VSWR %.1f ring radius inverts back to %.1f" % (s, s),
              abs(float(smith.vswr_from_gamma(rad)) - s) < 1e-12)

    # -- 8. the refusals ------------------------------------------------------
    for label, fn, arg in (("negative r", smith.r_circle, -0.5),
                           ("x = 0 (a line, not a circle)", smith.x_circle, 0.0),
                           ("VSWR below 1", smith.gamma_radius_for_vswr, 0.5)):
        try:
            fn(arg)
        except ValueError:
            check("refuses %s" % label, True)
        else:
            check("refuses %s" % label, False, "returned instead of refusing")

    # -- 9. the read-out a user actually reads -------------------------------
    r = smith.readout(73.1 + 42.5j, Z0)
    check("readout: VSWR 2.18 on the classic 73+42j load",
          abs(r["vswr"] - 2.1819) < 5e-4, "got %.4f" % r["vswr"])
    check("readout: return loss 8.60 dB", abs(r["return_loss_db"] - 8.6023) < 5e-4,
          "got %.4f" % r["return_loss_db"])
    check("readout: names the reactance sign", r["reactance"] == "inductive")
    check("readout: carries z0 (a chart without it is half a number)",
          r["z0_ohm"] == Z0)

    if FAILURES:
        print("SMITH GATE FAILED (%d): %s" % (len(FAILURES), FAILURES[:4]))
        return 1
    print("SMITH GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
