# SPDX-License-Identifier: LGPL-2.1-or-later
"""Empirical land-mobile path-loss models — Okumura-Hata + COST-231-Hata (§6 phase D).

The classic macro-cell clutter models: median path loss over an urban / suburban /
open environment from four numbers (frequency, base height, mobile height,
distance), embodying the Okumura measurement campaign rather than an explicit
terrain solve. This is the coverage engine's "model breadth" slice for the
land-mobile bands — the clutter categories ARE the model (no land-use raster).

Formulas confirmed against the primary sources (Hata 1980; COST 231 Final Report
ch. 4 eqs 4.4.1-4.4.4; Rappaport 2e eqs 3.82-3.87) during the de-risk pass:

  Okumura-Hata urban (150-1500 MHz):
    L = 69.55 + 26.16 log f - 13.82 log hb - a(hm) + (44.9 - 6.55 log hb) log d
  a(hm) small/medium city: (1.1 log f - 0.7) hm - (1.56 log f - 0.8)
  a(hm) large city:  8.29 (log 1.54 hm)^2 - 1.1   (f < 300 MHz)
                     3.2 (log 11.75 hm)^2 - 4.97  (f >= 300 MHz)
    (the large-city split frequency is 200/400 MHz in Hata's paper with the gap
    undefined; the common Rappaport 300 MHz split is used here)
  suburban: L_urban - 2 (log(f/28))^2 - 5.4
  open:     L_urban - 4.78 (log f)^2 + 18.33 log f - 40.94

  COST-231-Hata (1500-2000 MHz; a(hm) is ALWAYS the small/medium form per the
  Final Report, metropolitan handled by Cm):
    L = 46.3 + 33.9 log f - 13.82 log hb - a(hm)
        + (44.9 - 6.55 log hb) log d + Cm,   Cm = 0 (medium/suburban) or 3 (metro)

Validity (stated, not enforced — the guard philosophy is warn/document, never
block): f 150-1500 MHz (Hata) / 1500-2000 MHz (COST-231), hb 30-200 m, hm 1-10 m,
d 1-20 km, macro-cells (base above surrounding rooftops). Outside those ranges the
formulas extrapolate smoothly but are unvalidated.

Pure-python (math), Qt-free, FreeCAD-free. SI in (metres, Hz); dB out.
"""
from __future__ import annotations

import math

# environment keys accepted by the loss functions / the coverage engine
ENVIRONMENTS = ("urban", "urban_large", "suburban", "open")


def hata_mobile_correction_db(freq_mhz, hm_m, large_city=False):
    """Mobile-antenna height correction a(hm) (dB).

    Small/medium city by default; ``large_city`` uses the dense-urban variant
    (split at 300 MHz — see the module docstring for the source discrepancy).
    """
    f = float(freq_mhz)
    hm = float(hm_m)
    if large_city:
        if f < 300.0:
            return 8.29 * math.log10(1.54 * hm) ** 2 - 1.1
        return 3.2 * math.log10(11.75 * hm) ** 2 - 4.97
    lf = math.log10(f)
    return (1.1 * lf - 0.7) * hm - (1.56 * lf - 0.8)


def okumura_hata_loss_db(dist_m, freq_hz, hb_m, hm_m, environment="urban"):
    """Okumura-Hata median path loss (dB). Nominal validity 150-1500 MHz,
    hb 30-200 m, hm 1-10 m, d 1-20 km.

    ``environment``: ``"urban"`` (small/medium city), ``"urban_large"``
    (dense/metropolitan), ``"suburban"``, ``"open"`` (rural, no obstructions).
    """
    if environment not in ENVIRONMENTS:
        raise ValueError("unknown environment: {0}".format(environment))
    f = float(freq_hz) / 1e6
    d = max(float(dist_m), 1.0) / 1e3
    hb = max(float(hb_m), 1.0)
    a_hm = hata_mobile_correction_db(f, hm_m, large_city=(environment == "urban_large"))
    lf = math.log10(f)
    loss = (69.55 + 26.16 * lf - 13.82 * math.log10(hb) - a_hm
            + (44.9 - 6.55 * math.log10(hb)) * math.log10(d))
    if environment == "suburban":
        loss -= 2.0 * math.log10(f / 28.0) ** 2 + 5.4
    elif environment == "open":
        loss -= 4.78 * lf * lf - 18.33 * lf + 40.94
    return loss


def cost231_hata_loss_db(dist_m, freq_hz, hb_m, hm_m, metropolitan=False):
    """COST-231-Hata median path loss (dB), 1500-2000 MHz macro-cells.

    Per the COST 231 Final Report, a(hm) is always the small/medium-city form;
    ``metropolitan`` adds Cm = 3 dB (dense urban centres). Suburban/rural use
    Cm = 0 (the report folds them into the medium-city case; true open-area
    corrections are outside its scope).
    """
    f = float(freq_hz) / 1e6
    d = max(float(dist_m), 1.0) / 1e3
    hb = max(float(hb_m), 1.0)
    a_hm = hata_mobile_correction_db(f, hm_m, large_city=False)
    return (46.3 + 33.9 * math.log10(f) - 13.82 * math.log10(hb) - a_hm
            + (44.9 - 6.55 * math.log10(hb)) * math.log10(d)
            + (3.0 if metropolitan else 0.0))


def empirical_loss_db(dist_m, freq_hz, hb_m, hm_m, environment="urban"):
    """Frequency-dispatched empirical loss (dB): Okumura-Hata below 1500 MHz,
    COST-231-Hata at/above (``urban_large`` maps to metropolitan Cm = 3).

    The 1500 MHz hand-over has a small step (the two models were fitted
    independently) — documented, not smoothed.
    """
    if float(freq_hz) < 1.5e9:
        return okumura_hata_loss_db(dist_m, freq_hz, hb_m, hm_m, environment)
    return cost231_hata_loss_db(dist_m, freq_hz, hb_m, hm_m,
                                metropolitan=(environment == "urban_large"))
