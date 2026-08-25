# SPDX-License-Identifier: LGPL-2.1-or-later
"""Planar inverted-F antenna (PIFA) synthesis — Hirasawa interpolation.

A PIFA is ONE element (a single feed port) per the section 1 scope contract. It
is the elevated-plate cousin of the printed IFA in ``ifa.py``: a rectangular top
plate held above the ground plane, shorted to it along part of one edge by a
shorting plate, and fed by a pin a short distance from that short.

THE EQUATIONS (Hirasawa and Haneishi, as reproduced in a FREE source)
---------------------------------------------------------------------
Symbols, all lengths in metres; NO permittivity appears -- these are the
air-dielectric forms:

    L1  length of the top plate ALONG the edge carrying the shorting plate
    L2  length of the top plate PERPENDICULAR to it (the resonant length)
    H   height of the top plate above ground (= the shorting plate's height)
    W   width of the shorting plate, along the L1 edge, 0 <= W <= L1

    f1 = c / (4 (L2 + H))                      # W = L1, the full-width short
    f2 = c / (4 (L1 + L2 + H - W))             # the 0 <= W < L1 branch
    r  = W / L1        k = L1 / L2
    fr = r*f1     + (1-r)*f2                   # for L1/L2 <= 1
    fr = r**k *f1 + (1-r**k)*f2                # for L1/L2 >  1

⚠⚠ **Do NOT ship f2 alone**, which is the form the web quotes as though it were
the general answer. On the verified geometry below it reads 1665 MHz against
1980 MHz -- **-15.9 %**, about three times worse than the interpolation. The
interpolation IS the standard form and it is the only one that reproduces the
measured trend of resonance against shorting-plate width.

The set closes on itself, which is the cheapest check that it has been
transcribed correctly: at W = L1, f2 = f1 so fr = f1; at W = 0, r = 0 so
fr = f2 and f2 degenerates to c/(4(L1+L2+H)), the shorting-pin case.

VERIFIED (docs/upstream/pifa-anchors.md)
-----------------------------------------
* 20 x 20 mm top plate, W 5 mm, H 10 mm -> this module computes **1874 MHz**
  against a published method-of-moments value of 1980 MHz (**-5.4 %**) and
  against chamber MEASUREMENTS of 1892 MHz on an 80 mm ground (**-1.0 %**) and
  1886 MHz on a 100 mm ground (**-0.7 %**).
* The published cellular-band worked example (L1 = W = 143.2, L2 = 71.6,
  H = 15.7 mm) -> **858.5 MHz** against its stated 859 MHz.

**Honest accuracy:** no source publishes a blanket tolerance for this closed
form. ``PIFA_ACCURACY`` is set to 5 %, which the three anchor points above
support (worst case -5.4 %) -- but it is THREE POINTS, not a measured tolerance,
and it is stated at the same figure as the patch and IFA engines so no analytic
family here looks better than it has earned.

⚠⚠ AN ELEMENT MODEL, NOT A PHONE MODEL — and for a PIFA this is measurable, not
rhetorical. Published data for the geometry above shows a **+18.3 %** resonance
shift when the ground plane shrinks to 0.156 lambda, with a **2.4:1** spread in
bandwidth and a **3.7 dB** spread in gain across ground-plane size. On a real
handset the chassis IS part of the antenna. Everything here assumes a ground
plane large enough not to dominate, and the dialog and tutorial say so in place.

Pure-python, Qt-free, FreeCAD-free; results are dicts of plain floats (house
rule). All SI (metres, Hz, ohms).
"""
from __future__ import annotations

C0 = 299792458.0

#: Stated accuracy of the Hirasawa interpolation on the resonant frequency
#: (fractional). ⚠ Supported by three anchor points (worst -5.4 %), NOT by a
#: published tolerance -- no source states one. Held equal to the patch engine's
#: TL_ACCURACY and the IFA engine's IFA_ACCURACY deliberately.
PIFA_ACCURACY = 0.05

#: The verified geometry, in metres. Square top plate, quarter-width short.
#: Kept here so the anchor a reader can check is in the code, not only in a doc.
ANCHOR = {
    "source": "Huynh, MS thesis, Virginia Tech 2000, Fig. 5-4 / Table 5-1",
    "l1_m": 20.0e-3,
    "l2_m": 20.0e-3,
    "h_m": 10.0e-3,
    "w_m": 5.0e-3,
    # ⚠ The ground plane is NOT packaging here — it is part of the antenna.
    # The published measurements were taken on 80 mm and 100 mm square
    # grounds and differ BY 6 MHz between them; quoting a PIFA number
    # without a ground size attached is quoting half a number.
    "ground_m": 80.0e-3,
    # ⚠⚠ The shorting plate sits AT THE SIDE EDGE of the top plate, not
    # centred on it. The closed form has no term for this and cannot tell
    # the two apart -- but full-wave can, and it is worth 7.6 %: centred
    # solves at 2.0370 GHz, at the edge 1.8930 GHz, against a measured
    # 1.892 GHz. Getting this wrong is a bigger error than the closed
    # form's own stated accuracy.
    "short_at_edge": True,
    "published_mom_hz": 1980e6,       # IE3D, infinite ground
    "published_meas_80mm_hz": 1892e6,  # chamber, 80 mm square ground
    "published_meas_100mm_hz": 1886e6,  # chamber, 100 mm square ground
}


def branch_full_short(l2_m, h_m):
    """f1 — the full-width-short case (W = L1): a quarter-wave resonator."""
    d = float(l2_m) + float(h_m)
    if d <= 0:
        raise ValueError("need L2 + H > 0")
    return C0 / (4.0 * d)


def branch_partial_short(l1_m, l2_m, h_m, w_m):
    """f2 — the 0 <= W < L1 branch, current path L1 + L2 + H - W."""
    d = float(l1_m) + float(l2_m) + float(h_m) - float(w_m)
    if d <= 0:
        raise ValueError(
            "L1 + L2 + H - W = {0:.4g} m is not positive — the shorting plate "
            "cannot be wider than the plate it shorts".format(d))
    return C0 / (4.0 * d)


def resonant_frequency(l1_m, l2_m, h_m, w_m):
    """Hirasawa interpolated resonance (Hz) for a PIFA of these dimensions.

    This is the FORWARD form. It is what the validation gate uses to predict the
    published anchor, and what :func:`design_pifa` inverts by scaling.
    """
    l1 = float(l1_m)
    l2 = float(l2_m)
    h = float(h_m)
    w = float(w_m)
    if l1 <= 0 or l2 <= 0 or h <= 0:
        raise ValueError("need L1>0, L2>0, H>0")
    if w < 0 or w > l1:
        raise ValueError(
            "shorting-plate width W = {0:.4g} m must be within 0..L1 "
            "({1:.4g} m)".format(w, l1))
    f1 = branch_full_short(l2, h)
    f2 = branch_partial_short(l1, l2, h, w)
    r = w / l1
    if l1 <= l2:
        weight = r
    else:
        # k = L1/L2 > 1 pushes the weight toward f2 for the same r: a plate that
        # is long along the shorted edge behaves less like the full-width short.
        weight = r ** (l1 / l2)
    return weight * f1 + (1.0 - weight) * f2


def design_pifa(f0_hz, height_m=None, l1_over_l2=1.0, short_frac=0.25,
                height_frac=0.5, target_z_ohm=50.0):
    """Synthesize a PIFA for ``f0_hz``.

    The forward equation has four free lengths, so synthesis fixes the SHAPE and
    solves for the scale. Every term in the resonance is a length, so the
    frequency scales exactly as 1/size: the shape is evaluated at unit scale and
    then scaled once. That is exact, not iterative.

    :param f0_hz: design (resonant) frequency (Hz).
    :param height_m: top-plate height above ground (m). ``None`` derives it from
        ``height_frac``; pass a value when the handset's z-stack fixes it, and
        the plate absorbs the difference.
    :param l1_over_l2: aspect ratio of the top plate (L1/L2). 1.0 is square.
    :param short_frac: shorting-plate width as a fraction of L1 (W/L1), 0..1.
    :param height_frac: H as a fraction of L2, used only when ``height_m`` is None.
    :param target_z_ohm: feed impedance the feed offset is seeded for.

    Returns a dict of plain floats plus ``warnings`` and a cited ``source_note``.
    Raises ValueError on inputs that cannot produce a geometry.
    """
    f0 = float(f0_hz)
    if f0 <= 0:
        raise ValueError("need f0 > 0")
    ratio = float(l1_over_l2)
    sf = float(short_frac)
    hf = float(height_frac)
    if ratio <= 0:
        raise ValueError("need L1/L2 > 0")
    if not 0.0 <= sf <= 1.0:
        raise ValueError("short_frac (W/L1) must be within 0..1")

    # Unit shape: L2 = 1, everything else relative to it.
    u_l2 = 1.0
    u_l1 = ratio
    u_h = hf if height_m is None else 1.0   # placeholder when H is pinned
    if height_m is not None:
        # H is fixed in absolute terms, so the shape is not scale-free until we
        # know the scale. Solve it directly: with L2 = s, L1 = ratio*s, W =
        # sf*L1 and H fixed, the resonance is monotonic in s, so bisect.
        h_fixed = float(height_m)
        if h_fixed <= 0:
            raise ValueError("need height > 0")
        lo, hi = 1e-6, 10.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            f = resonant_frequency(ratio * mid, mid, h_fixed, sf * ratio * mid)
            if f > f0:
                lo = mid          # too small -> resonates high -> grow it
            else:
                hi = mid
        l2 = 0.5 * (lo + hi)
        l1 = ratio * l2
        h = h_fixed
    else:
        if hf <= 0:
            raise ValueError("need height_frac > 0")
        u_w = sf * u_l1
        f_unit = resonant_frequency(u_l1, u_l2, u_h, u_w)
        scale = f_unit / f0            # metres per unit
        l2 = u_l2 * scale
        l1 = u_l1 * scale
        h = u_h * scale
    w_short = sf * l1

    f_check = resonant_frequency(l1, l2, h, w_short)
    lam0 = C0 / f0

    # The feed sits between the short and the open edge; moving it away from the
    # short raises Rin. A quarter of the way is the usual starting point and is
    # a SEED, not a model -- the same status the IFA engine's feed offset has.
    feed_offset = 0.25 * l2

    # Ground plane, at the anchor's own ratio (80 mm square under a 20 mm
    # plate = 4x). Returned rather than assumed because it MOVES THE ANSWER:
    # see the ground-plane spread in the warnings below.
    ground = 4.0 * max(l1, l2)

    warnings = [
        "resonant frequency is the Hirasawa closed form, accurate to ~±5 % vs "
        "full-wave/measurement — use Verify with openEMS for the achieved "
        "f_res and gain",
        "the feed offset ({0:.2f} mm from the short) is a SEED, not an "
        "impedance model: it starts the geometry near {1:.0f} ohm and is meant "
        "to be moved and re-solved".format(feed_offset * 1e3,
                                           float(target_z_ohm)),
        "the shorting plate is placed AT THE SIDE EDGE of the top plate. "
        "⚠ Its POSITION along that edge is NOT in the closed form and is worth "
        "~7.6 % in resonance (measured: centred 2.0370 GHz vs at-edge 1.8930 "
        "GHz on the anchor geometry) — larger than the form's own stated "
        "accuracy. Move the short and you must re-solve; the equation will not "
        "tell you.",
        "ELEMENT model, not a phone model: published data for this geometry "
        "shows +18.3 % resonance shift, a 2.4:1 bandwidth spread and 3.7 dB of "
        "gain spread as the ground plane shrinks toward 0.156·lambda. A PIFA on "
        "a real handset is a chassis problem, and the chassis is not modelled "
        "here.",
    ]
    if h > 0.1 * lam0:
        warnings.append(
            "height {0:.3g} mm is > 0.1·lambda0 ({1:.3g} mm): this is no longer "
            "a low-profile PIFA and the closed form is extrapolated".format(
                h * 1e3, 0.1 * lam0 * 1e3))
    if sf < 0.05:
        warnings.append(
            "W/L1 = {0:.3g} is close to the shorting-PIN limit, where the "
            "interpolation reduces to its f2 branch and is at its least "
            "accurate".format(sf))

    return {
        "family": "pifa",
        "f0_hz": f0,
        "f_check_hz": f_check,
        "wavelength_m": lam0,
        "l1_m": l1,
        "l2_m": l2,
        "height_m": h,
        "short_width_m": w_short,
        "short_frac": sf,
        "l1_over_l2": ratio,
        "feed_offset_m": feed_offset,
        "ground_m": ground,
        "f1_full_short_hz": branch_full_short(l2, h),
        "f2_partial_short_hz": branch_partial_short(l1, l2, h, w_short),
        "target_z_ohm": float(target_z_ohm),
        "warnings": warnings,
        "source_note": (
            "PIFA Hirasawa interpolation (see docs/upstream/pifa-anchors.md): "
            "f1 = c/4(L2+H), f2 = c/4(L1+L2+H-W), fr = r·f1 + (1-r)·f2 with "
            "r = W/L1 (exponent k = L1/L2 when L1 > L2). L1 {0:.3f} / L2 "
            "{1:.3f} / H {2:.3f} / W {3:.3f} mm. ±5 % accuracy (three anchor "
            "points, not a published tolerance); feed offset is a SEED."
            .format(l1 * 1e3, l2 * 1e3, h * 1e3, w_short * 1e3)),
    }
