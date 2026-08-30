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
# ⚠⚠ REALIZABILITY, not the E-plane optimum. Until 2026-08-30 this line
# asserted b1 = sqrt(2*lambda*rho_e) — the E-plane OPTIMUM flare — which,
# printed beside the H-plane optimum at a1 = 1.5*b1, described a horn whose
# two flares meet the axis 1.5x apart: no single pyramidal horn has that
# geometry (Nikolova L18 eq. 18.42: R_E = R_H). The synthesis now derives
# rho_e from the SHARED APEX, so the load-bearing checks are:
_pe = math.sqrt(a["flare_rho_e_m"] ** 2 - (a["aperture_b1_m"] / 2) ** 2)
_ph = math.sqrt(a["flare_rho_h_m"] ** 2 - (a["aperture_a1_m"] / 2) ** 2)
check("both flares reach ONE apex (p_e/p_h %.6f; buildability)" % (_pe / _ph),
      abs(_pe / _ph - 1.0) < 1e-9)
check("axial_length_m is that shared axial length",
      abs(a["axial_length_m"] - _ph) < 1e-12)
# NEGATIVE CONTROL for the line above: the OLD (wrong) rho_e must FAIL the
# apex condition. If this ever passes, the check above has gone vacuous.
_rho_e_old = a["aperture_b1_m"] ** 2 / (2 * a["wavelength_m"])
_pe_old = math.sqrt(_rho_e_old ** 2 - (a["aperture_b1_m"] / 2) ** 2)
check("negative control: the pre-2026-08-30 rho_e FAILS the apex condition "
      "(old p_e/p_h %.4f, must be visibly NOT 1)" % (_pe_old / _ph),
      abs(_pe_old / _ph - 1.0) > 0.3)
check("E-plane flare longer than its optimum, s_e %.4f in (0, 0.25) — "
      "realized gain >= the eps_ap=0.51 estimate" % a["phase_err_e"],
      a["flare_rho_e_m"] > _rho_e_old
      and 0.0 < a["phase_err_e"] < 0.25)

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


# --- mode (b): the TRUE Balanis optimum (added 2026-08-30) ------------------
# Gated on the IDENTITIES both fetched sources state, never on remembered
# numbers: realizability p_e = p_h is the equation being solved, the gain
# round-trip closes at eps_ap ~ 0.51, and the apex-limit aspect approaches
# sqrt(1.5) — the ratio whose SQUARE (1.5) mode (a) deliberately keeps.
o = H.design_pyramidal_optimum(10e9, 20.0)
check("optimum mode: p_e = p_h EXACTLY (ratio %.12f)" % (
      o["axial_p_e_m"] / o["axial_p_h_m"]),
      abs(o["axial_p_e_m"] / o["axial_p_h_m"] - 1.0) < 1e-9)
check("optimum mode: gain round-trip within 0.05 dB of target "
      "(got %.4f for 20.0)" % o["gain_dbi"],
      abs(o["gain_dbi"] - 20.0) < 0.05)
check("optimum mode, apex limit: aspect a1/b1 %.4f near sqrt(1.5)=1.2247 "
      "— NOT mode (a)'s 1.5" % (o["aperture_a1_m"] / o["aperture_b1_m"]),
      1.20 < o["aperture_a1_m"] / o["aperture_b1_m"] < 1.26)
check("the two modes are genuinely different designs (aspects 1.5 vs ~1.22)",
      abs(a["aperture_a1_m"] / a["aperture_b1_m"]
          - o["aperture_a1_m"] / o["aperture_b1_m"]) > 0.2)
# The classic WR-90 X-band case: identities must survive a REAL throat, and
# the feed guide must actually constrain the result (negative control: the
# apex answer and the WR-90 answer must differ).
w = H.design_pyramidal_optimum(11e9, 22.6, feed_a_m=0.02286, feed_b_m=0.01016)
check("WR-90 22.6 dB: p_e = p_h with a real throat (ratio %.12f)" % (
      w["axial_p_e_m"] / w["axial_p_h_m"]),
      abs(w["axial_p_e_m"] / w["axial_p_h_m"] - 1.0) < 1e-9)
check("WR-90 22.6 dB: gain round-trip %.4f dBi" % w["gain_dbi"],
      abs(w["gain_dbi"] - 22.6) < 0.05)
o11 = H.design_pyramidal_optimum(11e9, 22.6)
check("the feed guide CONSTRAINS the design (WR-90 chi %.4f != apex chi "
      "%.4f)" % (w["chi"], o11["chi"]),
      abs(w["chi"] - o11["chi"]) > 1e-3)

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
