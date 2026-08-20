# SPDX-License-Identifier: LGPL-2.1-or-later
"""Band → recommended-analysis-method picker (the honest multi-method router).

No single EM engine spans VLF (kHz) to mmWave (tens of GHz); each band has a
different *right* method, and pretending otherwise would be dishonest (see
docs/CAPABILITIES.md "Frequency range & validity" and docs/ROADMAP.md §4). This
module routes a frequency (and, optionally, the antenna's physical size) to the
EMStudio method that is actually valid there, with a one-line rationale and the
validity caveat stated up front. It is the deterministic core that both the
small-antenna dialog and (later) the §3 AI assistant call.

Pure-python, Qt-free and FreeCAD-free (importable headless). Frequencies in Hz.
"""
from __future__ import annotations

C0 = 299792458.0

# ITU radio-band table: (key, human name, f_lo_hz, f_hi_hz). Edges are the
# conventional decade boundaries. ELF/SLF/ULF are included for honesty — a few
# operational transmitters and navigation/beacon systems sit in the tens-of-Hz to
# ~10 kHz range, and the VLF band we care about reaches down to ~10 kHz.
BANDS = [
    ("ELF", "Extremely Low Frequency", 3.0, 30.0),
    ("SLF", "Super Low Frequency", 30.0, 300.0),
    ("ULF", "Ultra Low Frequency", 300.0, 3.0e3),
    ("VLF", "Very Low Frequency", 3.0e3, 30.0e3),
    ("LF", "Low Frequency", 30.0e3, 300.0e3),
    ("MF", "Medium Frequency", 300.0e3, 3.0e6),
    ("HF", "High Frequency", 3.0e6, 30.0e6),
    ("VHF", "Very High Frequency", 30.0e6, 300.0e6),
    ("UHF", "Ultra High Frequency", 300.0e6, 3.0e9),
    ("SHF", "Super High Frequency", 3.0e9, 30.0e9),
    ("EHF", "Extremely High Frequency", 30.0e9, 300.0e9),
]

# Human labels for the EMStudio methods a recommendation can point at.
METHOD_LABELS = {
    "small_antenna": "analytic small-antenna models (this dialog)",
    "nec2": "NEC2 wire MoM",
    "nec2_ground": "NEC2 wire MoM with a ground/counterpoise model",
    "openems": "openEMS FDTD (full-wave)",
    "palace": "Palace FEM (full-wave)",
    "elmer": "Elmer magneto-quasistatic FEM",
    "fasthenry": "FastHenry PEEC R/L extraction",
}


def wavelength_m(freq_hz):
    return C0 / float(freq_hz)


def band_of(freq_hz):
    """Return (key, name, f_lo_hz, f_hi_hz) for the ITU band containing ``freq_hz``.

    Clamps to the nearest edge band outside the tabulated span so the picker
    always yields an answer.
    """
    f = float(freq_hz)
    for key, name, lo, hi in BANDS:
        if lo <= f < hi:
            return key, name, lo, hi
    if f < BANDS[0][2]:
        return BANDS[0][:4]
    return BANDS[-1][:4]


def recommend_method(freq_hz, max_dim_m=None, wire_structure=True):
    """Recommend the EMStudio analysis method(s) valid at ``freq_hz``.

    :param freq_hz: operating frequency (Hz).
    :param max_dim_m: largest antenna dimension (m), if known — used only to add
        an electrical-size note (size in wavelengths); never changes the band.
    :param wire_structure: True for wire/monopole/dipole geometry (favours NEC2),
        False for planar/3-D solids (favours openEMS/Palace).

    Returns a dict: band, band_name, band_range_hz, wavelength_m, primary,
    methods (ordered keys), method_labels, rationale, validity, size_note.
    """
    f = float(freq_hz)
    key, name, lo, hi = band_of(f)
    lam = wavelength_m(f)

    if f < 3.0e6:
        # VLF/LF/MF and below: antennas are a tiny fraction of a wavelength
        # (lambda/4 at 30 kHz is ~2.5 km) — the Chu-Harrington small-antenna
        # regime. Full-wave FDTD/FEM is impractical (domain-in-cells explodes);
        # ground conductivity + the radial/counterpoise system dominate
        # efficiency, so a ground model is required.
        methods = ["small_antenna", "nec2_ground"]
        primary = "small_antenna"
        rationale = (
            "Electrically-small regime: at {0} the wavelength is {1:.3g} km, so a "
            "practical antenna is a tiny fraction of lambda. Use closed-form "
            "small-antenna models for radiation resistance, effective height, "
            "efficiency and the Chu Q/bandwidth limit; use NEC2 with a "
            "ground/counterpoise model for the wire/monopole structure. Ground "
            "conductivity and the radial system dominate efficiency here.".format(
                _fmt_freq(f), lam / 1e3))
        validity = (
            "Full-wave FDTD/FEM (openEMS/Palace) is impractical at these "
            "frequencies — the meshed domain in wavelength-fraction cells is "
            "astronomically large. Analytic + MoM-with-ground is the honest path.")
    elif f < 3.0e9:
        # HF -> low microwave: full-wave engines apply. Wire favours NEC2;
        # planar/3-D favours openEMS/Palace.
        if wire_structure:
            methods = ["nec2", "openems", "palace"]
            primary = "nec2"
        else:
            methods = ["openems", "palace", "nec2"]
            primary = "openems"
        rationale = (
            "Full-wave band: the antenna is an appreciable fraction of a "
            "wavelength ({0:.3g} m at {1}). NEC2 (wire MoM) is fastest for "
            "wire/monopole/Yagi structures; openEMS (FDTD) and Palace (FEM) cover "
            "planar and general 3-D geometry.".format(lam, _fmt_freq(f)))
        validity = (
            "NEC2 wires must stay above ~lambda/10 segment length with sane "
            "radius/length ratios; openEMS/Palace cost scales with (size/lambda)^3 "
            "in memory. Validated points: NEC2 dipole 296 MHz, openEMS patch "
            "2.435 GHz.")
    else:
        # microwave -> mmWave: FDTD / FEM full-wave.
        methods = ["palace", "openems"]
        primary = "palace"
        rationale = (
            # ``_fmt_wavelength`` already carries the unit ("10.71 mm"), so a
            # literal " m" after it printed "10.71 mm m wavelength" at mmWave.
            "Microwave/mmWave band ({0} wavelength at {1}). Use the full-wave "
            "FEM/FDTD engines: Palace (FEM) is validated to 57 GHz for "
            "cavities/waveguides/driven S-parameters; openEMS (FDTD) covers "
            "planar/antenna geometry.".format(_fmt_wavelength(lam), _fmt_freq(f)))
        validity = (
            "Mesh element size scales with lambda, so memory/time grow at high "
            "frequency (no physics break). Palace validated sub-0.01% at 39 and "
            "57 GHz.")

    out = {
        "freq_hz": f,
        "band": key,
        "band_name": name,
        "band_range_hz": (lo, hi),
        "wavelength_m": lam,
        "primary": primary,
        "primary_label": METHOD_LABELS[primary],
        "methods": methods,
        "method_labels": [METHOD_LABELS[m] for m in methods],
        "rationale": rationale,
        "validity": validity,
        "size_note": None,
    }
    if max_dim_m and max_dim_m > 0:
        frac = float(max_dim_m) / lam
        if frac < 0.1:
            out["size_note"] = (
                "The {0:.3g} m structure is {1:.4g} wavelengths (electrically "
                "small, < lambda/10) — analytic + MoM is appropriate.".format(
                    float(max_dim_m), frac))
        elif frac < 1.0:
            out["size_note"] = (
                "The {0:.3g} m structure is {1:.3g} wavelengths (resonant "
                "scale) — a full-wave method is appropriate.".format(
                    float(max_dim_m), frac))
        else:
            out["size_note"] = (
                "The {0:.3g} m structure is {1:.3g} wavelengths (electrically "
                "large) — full-wave, and mind the mesh/segment cost.".format(
                    float(max_dim_m), frac))
    return out


def summary_text(rec):
    """One-block human-readable rendering of a recommend_method() result."""
    lines = [
        "Band: {0} ({1})  —  {2}".format(
            rec["band"], rec["band_name"], _fmt_freq(rec["freq_hz"])),
        "Wavelength: {0}".format(_fmt_wavelength(rec["wavelength_m"])),
        "Recommended: {0}".format(rec["primary_label"]),
        "Also: " + ", ".join(rec["method_labels"][1:]) if len(rec["methods"]) > 1
        else "",
        "",
        "Why: " + rec["rationale"],
        "",
        "Validity: " + rec["validity"],
    ]
    if rec.get("size_note"):
        lines += ["", "Size: " + rec["size_note"]]
    return "\n".join(l for l in lines if l is not None)


def _fmt_freq(f):
    f = float(f)
    if f >= 1e9:
        return "{0:.4g} GHz".format(f / 1e9)
    if f >= 1e6:
        return "{0:.4g} MHz".format(f / 1e6)
    if f >= 1e3:
        return "{0:.4g} kHz".format(f / 1e3)
    return "{0:.4g} Hz".format(f)


def _fmt_wavelength(lam):
    lam = float(lam)
    if lam >= 1e3:
        return "{0:.4g} km".format(lam / 1e3)
    if lam >= 1.0:
        return "{0:.4g} m".format(lam)
    if lam >= 1e-3:
        return "{0:.4g} mm".format(lam * 1e3)
    return "{0:.4g} um".format(lam * 1e6)


def _fmt_wavelength_short(lam):  # kept for callers wanting the bare value
    return _fmt_wavelength(lam)
