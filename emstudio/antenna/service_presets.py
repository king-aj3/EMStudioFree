# SPDX-License-Identifier: LGPL-2.1-or-later
"""Service presets for the Element Designer (slice E6).

One verified row per common radio service: band edges, the regional variant
note, and the conventional polarization/pattern an antenna designer would
build for. Selecting a preset in the dialog AUTO-FILLS the requirements
schema (frequency / band top / polarization / pattern) — the user then hits
"Recommend family" or designs directly.

Every band edge was verified from authoritative sources (FCC rule parts,
ITU/ETSI/ARRL band plans) by the E6 de-risk pass — provenance in
docs/upstream/service-presets-anchors.md. US values are primary where
regions differ; the region_note says what changes elsewhere. Frequencies
are stored in MHz (floats) and exposed in Hz.

Pure-python, Qt-free, FreeCAD-free (house rule); gated in
tests/validation/element_designer.py (preset tier).
"""
from __future__ import annotations

#: A preset narrower than this f_hi/f_lo ratio is treated as a SPOT design
#: (the dialog fills the single Frequency with the geometric centre);
#: wider presets fill Frequency = f_lo + Band top = f_hi.
SPOT_RATIO = 1.05

#: Verified service rows (key, label, f_lo/f_hi in MHz, region note,
#: polarization V/H/CP/any, pattern omni/directional/any, design note).
_ROWS = [
    {
        "key": 'fm_broadcast', "label": 'FM broadcast',
        "f_lo_mhz": 88, "f_hi_mhz": 108,
        "polarization": 'H', "pattern": 'any',
        "note": 'Broadcast TX is horizontal or circular; fixed RX antennas are conventionally horizontal - omni folded dipole for local, H-pol Yagi for fringe.',
        "region_note": 'US value used (47 CFR 73.201: 88-108 MHz, 100 channels x 200 kHz, carriers 88.1-107.9). ITU Region 1/EU: 87.5-108 MHz; Japan 76-95 MHz; legacy OIRT 65.8-74 MHz.',
    },
    {
        "key": 'am_broadcast', "label": 'AM broadcast (MF)',
        "f_lo_mhz": 0.535, "f_hi_mhz": 1.705,
        "polarization": 'V', "pattern": 'omni',
        "note": 'Ground-wave service from vertical monopole TX, so signals arrive vertically polarized; RX uses small loops or short verticals - full-size resonant elements are impractical at MF.',
        "region_note": 'US value used (47 CFR 73.14: band 535-1705 kHz; carriers 540-1700 kHz in 10 kHz steps). ITU Region 2 allocation spans 525-1705 kHz; Regions 1/3: 526.5-1606.5 kHz on a 9 kHz raster.',
    },
    {
        "key": 'noaa_wx', "label": 'NOAA weather radio',
        "f_lo_mhz": 162.4, "f_hi_mhz": 162.55,
        "polarization": 'V', "pattern": 'omni',
        "note": 'Narrowband FM broadcast from vertically polarized TX; RX is a vertical whip or ground plane, omni for scanners, small V-pol Yagi only for fringe reception.',
        "region_note": 'US/Canada only: seven 25 kHz channels 162.400/.425/.450/.475/.500/.525/.550 MHz (NWR All Hazards; Canada Weatheradio uses the same set). No EU equivalent.',
    },
    {
        "key": 'airband', "label": 'Airband (AM voice)',
        "f_lo_mhz": 118, "f_hi_mhz": 137,
        "polarization": 'V', "pattern": 'omni',
        "note": 'AM (DSB) voice, vertically polarized on aircraft and ground stations; listener/ground RX is a vertical omni (ground plane or discone covering the full band).',
        "region_note": 'US/ICAO worldwide: VHF aeronautical mobile (R) voice 118.000-136.975 MHz (47 CFR Part 87); ITU allocation starts 117.975 MHz. US 25 kHz spacing; Europe 8.33 kHz channelization. 108-118 MHz below is nav (VOR/ILS), not voice.',
    },
    {
        "key": 'marine_vhf', "label": 'Marine VHF',
        "f_lo_mhz": 156, "f_hi_mhz": 162.025,
        "polarization": 'V', "pattern": 'omni',
        "note": 'FM voice, vertically polarized; shipboard and shore RX antennas are vertical omnis (end-fed half-wave or collinear for gain at masthead).',
        "region_note": 'International per ITU RR Appendix 18 (156.0-162.025 MHz inclusive, 25 kHz channels; Ch 16 distress = 156.800 MHz); US channel set per USCG/FCC differs only in a few duplex/simplex assignments, same band edges.',
    },
    {
        "key": 'ham_80m', "label": '80 m amateur',
        "f_lo_mhz": 3.5, "f_hi_mhz": 4,
        "polarization": 'H', "pattern": 'omni',
        "note": 'Regional/NVIS band; the conventional build is a horizontal wire dipole or inverted-V at modest height, giving near-omni high-angle coverage.',
        "region_note": 'US/ITU Region 2 value used (3.5-4.0 MHz per 47 CFR 97.301); ITU Region 1 is 3.5-3.8 MHz, Region 3 is 3.5-3.9 MHz',
    },
    {
        "key": 'ham_40m', "label": '40 m amateur',
        "f_lo_mhz": 7, "f_hi_mhz": 7.3,
        "polarization": 'H', "pattern": 'omni',
        "note": 'Workhorse day/night band; horizontal half-wave dipole (about 20 m span) is the standard antenna, verticals used where DX low-angle is wanted.',
        "region_note": 'US value used (7.0-7.3 MHz per 47 CFR 97.301); ITU Region 1 amateurs use 7.0-7.2 MHz',
    },
    {
        "key": 'ham_20m', "label": '20 m amateur',
        "f_lo_mhz": 14, "f_hi_mhz": 14.35,
        "polarization": 'H', "pattern": 'directional',
        "note": 'Primary DX band; the classic station antenna is a horizontal 3-element Yagi on a tower, with a horizontal dipole as the common minimum build.',
        "region_note": 'Worldwide allocation, identical in all three ITU regions (14.0-14.35 MHz)',
    },
    {
        "key": 'ham_10m', "label": '10 m amateur',
        "f_lo_mhz": 28, "f_hi_mhz": 29.7,
        "polarization": 'H', "pattern": 'directional',
        "note": 'Wide 1.7 MHz band; DX work uses horizontal Yagis/dipoles, while the 29.5-29.7 MHz FM segment and mobiles use vertical whips.',
        "region_note": 'Worldwide allocation, identical in all three ITU regions (28.0-29.7 MHz)',
    },
    {
        "key": 'ham_6m', "label": '6 m amateur',
        "f_lo_mhz": 50, "f_hi_mhz": 54,
        "polarization": 'H', "pattern": 'directional',
        "note": 'Weak-signal SSB/CW convention is a horizontal Yagi (Es/MS openings); local FM around 52-53 MHz uses vertical omnis.',
        "region_note": 'US value used (50-54 MHz per 47 CFR 97.301); ITU Region 1 is 50-52 MHz (WRC-19), with some R1 countries limited to 50.0-50.5 MHz primary',
    },
    {
        "key": 'ham_2m', "label": '2 m amateur',
        "f_lo_mhz": 144, "f_hi_mhz": 148,
        "polarization": 'V', "pattern": 'omni',
        "note": 'FM/repeater use dominates, so vertical omnis (J-pole, ground plane, collinear) are the standard build; SSB/EME work instead uses horizontal Yagis.',
        "region_note": 'US value used (144-148 MHz per 47 CFR 97.301); ITU Region 1 is 144-146 MHz',
    },
    {
        "key": 'ham_70cm', "label": '70 cm amateur',
        "f_lo_mhz": 420, "f_hi_mhz": 450,
        "polarization": 'V', "pattern": 'omni',
        "note": 'FM/repeater and digital use favor vertical omnis; satellite operators use CP Yagis and weak-signal/ATV work uses directional horizontals.',
        "region_note": 'US value used (420-450 MHz per 47 CFR 97.301); ITU Region 1 is 430-440 MHz',
    },
    {
        "key": 'cb', "label": 'CB (27 MHz)',
        "f_lo_mhz": 26.965, "f_hi_mhz": 27.405,
        "polarization": 'V', "pattern": 'omni',
        "note": 'Mobile whips set the vertical convention, so base antennas are vertical omnis (quarter/five-eighths-wave ground planes) to match polarization.',
        "region_note": 'US 40-channel plan used (ch 1 = 26.965 to ch 40 = 27.405 MHz per 47 CFR 95.963); EU/CEPT is harmonized on the same 40 channels, UK adds a 27.60125-27.99125 MHz block',
    },
    {
        "key": 'ism_433', "label": '433 MHz ISM/SRD',
        "f_lo_mhz": 433.05, "f_hi_mhz": 434.79,
        "polarization": 'V', "pattern": 'omni',
        "note": 'SRD remote-control/telemetry links use short vertical whips or helicals with omni coverage on both ends.',
        "region_note": 'ITU Region 1 ISM band per RR footnotes 5.138/5.280 (center 433.92 MHz; 5.280 names ~11 European countries, 5.138 covers the rest of Region 1); EU SRD use per ETSI EN 300 220 (10 mW ERP, duty-cycle limits). Not a US ISM band — US 433 MHz devices operate under FCC Part 15.231 inside the amateur 420-450 MHz allocation. Band edges given are the ITU R1/ETSI values, which are what 433 MHz hardware uses worldwide.',
    },
    {
        "key": 'lora_868', "label": 'LoRa/SRD 868 (EU)',
        "f_lo_mhz": 863, "f_hi_mhz": 870,
        "polarization": 'V', "pattern": 'omni',
        "note": 'IoT nodes and gateways use vertical omni antennas (whip, ground-plane, or collinear); link budget, not gain, dominates the design.',
        "region_note": 'EU/CEPT-only band (ETSI EN 300 220, ERC Rec 70-03 Annex 1); LoRaWAN EU868 channels sit here with per-sub-band ERP (25-500 mW) and duty-cycle/LBT limits. No US counterpart — the US equivalent service uses 902-928 MHz. Values given are the ETSI band edges.',
    },
    {
        "key": 'lora_915', "label": 'LoRa/ISM 915 (US)',
        "f_lo_mhz": 902, "f_hi_mhz": 928,
        "polarization": 'V', "pattern": 'omni',
        "note": 'LoRaWAN US915 and 900 MHz FHSS gear use vertical omni whips/collinears; 26 MHz width favors moderately broadband elements.',
        "region_note": 'US / ITU Region 2 ISM band (FCC Part 18) with unlicensed digital/FHSS devices under 47 CFR 15.247 (up to 1 W); LoRaWAN US915 plan. Not available in Europe (R1 uses 863-870). Values given are the FCC band edges.',
    },
    {
        "key": 'wifi_24', "label": 'Wi-Fi 2.4 GHz',
        "f_lo_mhz": 2400, "f_hi_mhz": 2483.5,
        "polarization": 'V', "pattern": 'omni',
        "note": 'AP/router sleeve dipoles are vertical omnis; MIMO sets mix polarizations and point-to-point links use directional panels, so V-pol omni is the design default.',
        "region_note": 'Effectively worldwide: FCC 15.247 and ETSI EN 300 328 both specify 2400-2483.5 MHz; Japan alone extends to 2497 MHz (band 2400-2497 MHz; ch 14 center 2484 MHz, DSSS/CCK only) for legacy 802.11b channel 14. US/EU common value given.',
    },
    {
        "key": 'wifi_5', "label": 'Wi-Fi 5 GHz',
        "f_lo_mhz": 5150, "f_hi_mhz": 5850,
        "polarization": 'V', "pattern": 'omni',
        "note": 'Indoor APs use vertical omnis; U-NII-3 outdoor point-to-point CPE uses dual-pol directional panels/dishes, and DFS applies in the 5250-5350/5470-5725 sub-bands.',
        "region_note": 'US 47 CFR 15.407 U-NII sub-bands: U-NII-1 5150-5250, U-NII-2A 5250-5350 (DFS), U-NII-2C 5470-5725 (DFS), U-NII-3 5725-5850. EU (EN 301 893) covers 5150-5350 and 5470-5725 only, with 5725-5875 as separate SRD/BFWA rules. Upper edge 5850 is the US Part 15 value, as given.',
    },
    {
        "key": 'gps_l1', "label": 'GPS L1',
        "f_lo_mhz": 1573.42, "f_hi_mhz": 1577.42,
        "polarization": 'CP', "pattern": 'omni',
        "note": 'Satellite signal is RHCP per the GPS SPS/IS specs, so RX antennas must be RHCP (patch or quadrifilar helix) with upper-hemisphere omni coverage; a linear element loses ~3 dB and all multipath rejection.',
        "region_note": 'Global — one worldwide carrier at 1575.42 MHz (1540 x 1.023 MHz); design band given is center +/-2 MHz, covering the C/A main lobe (+/-1.023 MHz) with margin; full P(Y)/L1C reception widens this to roughly 1563-1587 MHz.',
    },
    {
        "key": 'adsb', "label": 'ADS-B 1090',
        "f_lo_mhz": 1089, "f_hi_mhz": 1091,
        "polarization": 'V', "pattern": 'omni',
        "note": 'Aircraft transponders transmit vertically polarized, so ground RX antennas are vertical omnis (quarter-wave ground-plane or collinear) optimized for low-elevation gain.',
        "region_note": 'Global ICAO standard (Annex 10 Vol IV, 1090 MHz Extended Squitter / Mode S; RTCA DO-260B in the US) — 1090 MHz carrier with +/-1 MHz transponder tolerance everywhere, so 1089-1091 applies in all regions.',
    },
]

PRESETS = _ROWS


def apply_preset(key):
    """Requirements-schema fragment for a preset key.

    Returns a dict with either ``f0_hz`` (spot services) or
    ``f_lo_hz``/``f_hi_hz`` (band services), plus ``polarization`` and
    ``pattern`` (None for 'any'), ``label`` and ``note``. Raises KeyError
    on an unknown key.
    """
    row = next((r for r in PRESETS if r["key"] == key), None)
    if row is None:
        raise KeyError("unknown service preset {0!r}".format(key))
    f_lo = row["f_lo_mhz"] * 1e6
    f_hi = row["f_hi_mhz"] * 1e6
    out = {
        "label": row["label"],
        "note": row["note"],
        "region_note": row["region_note"],
        "polarization": None if row["polarization"] == "any"
        else row["polarization"],
        "pattern": None if row["pattern"] == "any" else row["pattern"],
    }
    if f_hi / f_lo < SPOT_RATIO:
        out["f0_hz"] = (f_lo * f_hi) ** 0.5
    else:
        out["f_lo_hz"] = f_lo
        out["f_hi_hz"] = f_hi
    return out
