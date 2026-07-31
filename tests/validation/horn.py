"""Validation gate — pyramidal horn (§1 element family). FAST tier, no solver.

The headline check is that TWO INDEPENDENT routes to gain agree:
    aperture:   G = eps_ap * 4*pi*A/lambda^2
    beamwidths: G ~ 26000/(theta_E * theta_H)
The second knows nothing about aperture area, so agreement is corroboration
rather than algebra restated — it is what tells you the beamwidth coefficients
(54, 78), the 26000 constant and the 0.51 efficiency describe the same horn.
A coefficient typo in any one of them breaks the agreement immediately.

Run:  python3 tests/validation/horn.py
"""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from emstudio.antenna import horn as H  # noqa: E402

CHECKS = []


def check(label, cond):
    CHECKS.append((label, bool(cond)))


# --- the independent cross-check, across band and gain ---------------------
worst = 0.0
for f in (3e9, 6e9, 10e9, 18e9, 40e9):
    for g in (12.0, 15.0, 20.0, 25.0, 30.0):
        d = H.design_pyramidal(f, g)
        worst = max(worst, d["gain_check_delta_db"])
        check("design realises its target at %.0f GHz / %.0f dBi" % (f / 1e9, g),
              abs(d["gain_dbi"] - g) < 1e-9)
check("aperture and beamwidth gain routes agree within 0.25 dB everywhere "
      "(worst %.3f dB)" % worst, worst < 0.25)

# --- physical scaling ------------------------------------------------------
a = H.design_pyramidal(10e9, 20.0)
b = H.design_pyramidal(20e9, 20.0)
check("same gain at double the frequency halves the aperture",
      abs(b["aperture_a1_m"] / a["aperture_a1_m"] - 0.5) < 1e-9)

c = H.design_pyramidal(10e9, 23.0103)          # +3.0103 dB = x2 area
check("+3 dB doubles the aperture area",
      abs((c["aperture_a1_m"] * c["aperture_b1_m"])
          / (a["aperture_a1_m"] * a["aperture_b1_m"]) - 2.0) < 1e-6)

check("optimum aspect ratio a1 = 1.5*b1",
      abs(a["aperture_a1_m"] / a["aperture_b1_m"] - 1.5) < 1e-12)
check("flare follows a1 = sqrt(3*lambda*rho_h)",
      abs(a["aperture_a1_m"] - math.sqrt(3 * a["wavelength_m"] * a["flare_rho_h_m"]))
      < 1e-12)
check("flare follows b1 = sqrt(2*lambda*rho_e)",
      abs(a["aperture_b1_m"] - math.sqrt(2 * a["wavelength_m"] * a["flare_rho_e_m"]))
      < 1e-12)

# --- beamwidth sense (the classic E/H mix-up) ------------------------------
e0, h0 = H.beamwidths_deg(0.145, 0.0967, 0.02998)
e1, h1 = H.beamwidths_deg(0.290, 0.0967, 0.02998)      # WIDER a1 only
check("a wider a1 narrows the H-plane", h1 < h0)
check("a wider a1 leaves the E-plane alone", abs(e1 - e0) < 1e-12)
e2, _ = H.beamwidths_deg(0.145, 0.1934, 0.02998)       # taller b1 only
check("a taller b1 narrows the E-plane", e2 < e0)
# THE POINT OF THE 1.5 ASPECT RATIO. With a1 = 1.5*b1 the two beamwidths come
# out nearly equal — theta_H = 78/1.5 = 52*lambda/b1 against theta_E =
# 54*lambda/b1 — so an optimum pyramidal horn radiates a nearly symmetric beam.
# That is the design intent, not a coincidence. (Asserting "E narrower than H"
# here is the intuitive guess and it is WRONG: the H-plane is marginally
# narrower because its 1.5x wider aperture more than offsets its cosine taper.)
check("optimum-horn beamwidths are within 5% of each other (symmetric beam)",
      abs(a["hpbw_e_deg"] - a["hpbw_h_deg"]) / a["hpbw_e_deg"] < 0.05)
check("...and the H-plane is the marginally narrower one (78/1.5 < 54)",
      a["hpbw_h_deg"] < a["hpbw_e_deg"])
check("the ratio is exactly (54*1.5)/78",
      abs(a["hpbw_e_deg"] / a["hpbw_h_deg"] - (54.0 * 1.5 / 78.0)) < 1e-12)

# --- efficiency is not free ------------------------------------------------
lam = H.wavelength_m(10e9)
g_ideal = H.gain_from_aperture(0.145, 0.0967, lam, eps_ap=1.0)
g_real = H.gain_from_aperture(0.145, 0.0967, lam)
check("0.51 efficiency costs 2.92 dB vs an ideal uniform aperture",
      abs((g_ideal - g_real) - 10 * math.log10(1 / 0.51)) < 1e-9)
check("...which is about 2.92 dB", abs((g_ideal - g_real) - 2.9243) < 1e-3)

# --- round trip ------------------------------------------------------------
r = H.analyse_pyramidal(10e9, a["aperture_a1_m"], a["aperture_b1_m"])
check("analyse() reproduces design() gain", abs(r["gain_dbi"] - a["gain_dbi"]) < 1e-12)
check("analyse() reproduces design() beamwidths",
      abs(r["hpbw_e_deg"] - a["hpbw_e_deg"]) < 1e-12)

# --- refusals --------------------------------------------------------------
for bad, why in ((0, "zero"), (-1, "negative")):
    try:
        H.design_pyramidal(bad, 20.0)
        check("frequency %s refused" % why, False)
    except H.HornError:
        check("frequency %s refused" % why, True)
try:
    H.design_pyramidal(10e9, -5.0)
    check("negative gain target refused", False)
except H.HornError:
    check("negative gain target refused", True)
try:
    H.gain_from_beamwidths(0, 10)
    check("zero beamwidth refused", False)
except H.HornError:
    check("zero beamwidth refused", True)

# --- honesty ---------------------------------------------------------------
check("design carries accuracy warnings", bool(a["warnings"]))
check("warnings say to seed a full-wave run, not fabricate",
      any("full-wave" in w or "openEMS" in w for w in a["warnings"]))
tiny = H.design_pyramidal(1e9, 6.0)
check("a sub-wavelength aperture is flagged",
      any("wavelength" in w for w in tiny["warnings"]))


def main():
    bad = [l for l, ok in CHECKS if not ok]
    for label, ok in CHECKS:
        print("  %s %s" % ("ok  " if ok else "FAIL", label))
    print("\n%d/%d checks passed" % (len(CHECKS) - len(bad), len(CHECKS)))
    if bad:
        raise SystemExit("horn gate FAILED: %d check(s)" % len(bad))
    print("HORN GATE PASSED")
    return 0


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    main()
