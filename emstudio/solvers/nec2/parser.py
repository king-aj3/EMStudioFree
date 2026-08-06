# SPDX-License-Identifier: LGPL-2.1-or-later
"""Parse nec2c output files into a SweepResult.

Format (verified against nec2c 1.3.1 output on 2026-07-05):

    FREQUENCY : 2.5000E+02 MHz
    ...
    --------- ANTENNA INPUT PARAMETERS ---------
    TAG   SEG    VOLTAGE (VOLTS)   CURRENT (AMPS)   IMPEDANCE (OHMS)   ADMITTANCE  POWER
    No:   No:    REAL  IMAGINARY   REAL  IMAGINARY  REAL  IMAGINARY    ...
      1    11  1.0E+00 0.0E+00  2.6E-03 7.3E-03  4.3188E+01 -1.2203E+02  ...

We take the impedance (columns 7 and 8 of the data row) of the FIRST input-parameters
row after each frequency line.
"""

from __future__ import annotations

import re

from emstudio.post.sparams import SweepResult

# NEC-2 implementations disagree on ONE character here, and it is the only thing
# that stopped EMStudio reading nec2++ output:
#     nec2c   FREQUENCY : 3.0000E+02 MHz
#     nec2++  FREQUENCY=  3.0000E+02 MHZ
# `nec2++` has been in the nec2 backend's `executables` tuple all along, so a
# user with it installed got a solver that DETECTED fine and then died at
# "impedance row before any FREQUENCY line" — a detected-but-unusable engine.
# The separator stays mandatory ([:=], not optional): a banner line like
# "--------- FREQUENCY --------" must not match, and neither must prose.
# IGNORECASE already covers MHz/MHZ.
_FREQ_RE = re.compile(r"FREQUENCY\s*[:=]\s*([0-9.Ee+-]+)\s*MHz", re.IGNORECASE)
_FLOAT_RE = re.compile(r"[-+]?[0-9]*\.?[0-9]+(?:[Ee][-+]?[0-9]+)?")


class NecParseError(RuntimeError):
    pass


def parse_output(path, z0=50.0):
    """Read a nec2c output file; return a SweepResult (Zin per frequency)."""
    freqs = []
    zins = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    current_freq = None
    in_input_params = False
    got_row_for_freq = False
    for line in lines:
        m = _FREQ_RE.search(line)
        if m:
            current_freq = float(m.group(1)) * 1e6
            in_input_params = False
            got_row_for_freq = False
            continue
        if "ANTENNA INPUT PARAMETERS" in line:
            in_input_params = True
            continue
        if in_input_params and not got_row_for_freq:
            nums = _FLOAT_RE.findall(line)
            # data row: TAG SEG + 9 floats (V_re V_im I_re I_im Z_re Z_im Y_re Y_im P)
            if len(nums) >= 11:
                z_re = float(nums[6])
                z_im = float(nums[7])
                if current_freq is None:
                    raise NecParseError("impedance row before any FREQUENCY line")
                freqs.append(current_freq)
                zins.append(complex(z_re, z_im))
                got_row_for_freq = True

    if not freqs:
        raise NecParseError("no input-impedance data found in {0}".format(path))
    return SweepResult(freqs, zins, z0=z0, meta={"backend": "nec2c"})


def parse_port_impedances(path):
    """Parse EVERY row of each ANTENNA INPUT PARAMETERS block (multi-excitation).

    A multi-EX deck prints one row per excited port, in EX-card order.
    ``parse_output`` deliberately keeps only the first row (the historic
    single-port contract and six shipped gates depend on it); an array is
    N-port, so this parser returns them all.

    KEY ROWS BY TAG, never by the printed SEG: the table's SEG column is the
    GLOBAL segment index while EX cards address tag + LOCAL segment (verified
    on nec2c 1.3.1 — tag 2 fed at local segment 14 of a 2x27-segment deck
    prints as ``2 41``).

    Returns a list with one entry per frequency:
    ``{"freq_hz", "rows": [{"tag", "seg", "v", "i", "z", "y", "power_w"}, ...]}``
    (complex v/i/z/y; rows in printed = EX-card order). ``power_w`` can be
    NEGATIVE — an element absorbing power from its neighbours is physical in a
    coupled array; callers decide whether to warn.
    """
    out = []
    current = None          # the dict being filled for the current frequency
    in_block = False
    rows_started = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _FREQ_RE.search(line)
            if m:
                current = {"freq_hz": float(m.group(1)) * 1e6, "rows": []}
                out.append(current)
                in_block = False
                rows_started = False
                continue
            if "ANTENNA INPUT PARAMETERS" in line:
                if current is None:
                    raise NecParseError(
                        "input-parameters block before any FREQUENCY line")
                in_block = True
                rows_started = False
                continue
            if not in_block:
                continue
            nums = _FLOAT_RE.findall(line)
            # data row: TAG SEG + 9 floats (V I Z Y each re/im, then power)
            if len(nums) >= 11:
                current["rows"].append({
                    "tag": int(float(nums[0])),
                    "seg": int(float(nums[1])),
                    "v": complex(float(nums[2]), float(nums[3])),
                    "i": complex(float(nums[4]), float(nums[5])),
                    "z": complex(float(nums[6]), float(nums[7])),
                    "y": complex(float(nums[8]), float(nums[9])),
                    "power_w": float(nums[10]),
                })
                rows_started = True
            elif rows_started:
                # first non-data line after the data rows ends the block
                # (the POWER BUDGET section follows)
                in_block = False

    out = [entry for entry in out if entry["rows"]]
    if not out:
        raise NecParseError("no input-parameters data found in {0}".format(path))
    return out


def parse_currents(path, freq_hz):
    """Parse the CURRENTS AND LOCATION table (single-frequency deck).

    nec2c format (verified 2026-07-05):
        SEG TAG   X Y Z (wavelengths)   LENGTH   REAL IMAG MAGN PHASE
    Returns dict: {seg, tag, pos_m (N,3), i_complex, i_mag, freq}.
    """
    import numpy as np

    lam = 299792458.0 / freq_hz
    rows = []
    in_table = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "CURRENTS AND LOCATION" in line:
                in_table = True
                continue
            if in_table:
                nums = _FLOAT_RE.findall(line)
                if len(nums) >= 10:
                    try:
                        seg, tag = int(float(nums[0])), int(float(nums[1]))
                        x, y, z, _l, re_i, im_i, mag, _ph = (float(n) for n in nums[2:10])
                    except ValueError:
                        continue
                    rows.append((seg, tag, x * lam, y * lam, z * lam, re_i, im_i, mag))
                elif rows and not line.strip():
                    break
    if not rows:
        raise NecParseError("no current data found in {0}".format(path))
    arr = np.asarray(rows, dtype=float)
    return {
        "seg": arr[:, 0].astype(int),
        "tag": arr[:, 1].astype(int),
        "pos_m": arr[:, 2:5],
        "i_complex": arr[:, 5] + 1j * arr[:, 6],
        "i_mag": arr[:, 7],
        "freq": freq_hz,
    }


def parse_radiation_complex(path, freq_hz):
    """Parse the RADIATION PATTERNS table keeping the COMPLEX field —
    E(theta) and E(phi) magnitude+phase, which :func:`parse_radiation_patterns`
    discards (it keeps total gain only).

    A DF manifold needs amplitude AND phase per element, so this is the parse
    the §7 S6 correlative-interferometer path uses. nec2c column order
    (verified 2026-07-27): THETA PHI | VERTC HORIZ TOTAL | AXIAL TILT SENSE |
    E(THETA) mag phase | E(PHI) mag phase. The SENSE column is a word
    (LINEAR/RIGHT/LEFT) — absent on null rows, so field offsets are taken from
    the END of the numeric list, never the start.

    Returns ``{"freq_hz", "theta", "phi", "e_theta", "e_phi"}`` with the two
    field arrays complex, shaped (n_theta, n_phi).
    """
    import numpy as np

    rows = []
    in_table = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "RADIATION PATTERNS" in line:
                in_table = True
                continue
            if not in_table:
                continue
            nums = _FLOAT_RE.findall(line)
            # a data row ends with the four field numbers; header rows do not
            if len(nums) < 11:
                if rows and not line.strip():
                    # The blank line after the data block ENDS the table — the
                    # same guard parse_radiation_patterns carries. Without it
                    # nec2c's trailer "DATA CARD No:  4 EN  0 0 0 0 0.0E+00..."
                    # yields 11 numbers whose first two are in the theta/phi
                    # windows, and a spurious all-zero theta = <card no.> row
                    # is injected into the pattern.
                    in_table = False
                continue
            try:
                th, ph = float(nums[0]), float(nums[1])
                et_mag, et_ph, ep_mag, ep_ph = (float(x) for x in nums[-4:])
            except ValueError:
                continue
            if not (-0.01 <= th <= 180.01 and -360.0 <= ph <= 360.0):
                continue
            rows.append((th, ph, et_mag, et_ph, ep_mag, ep_ph))
    if not rows:
        raise NecParseError(
            "no complex radiation-pattern data found in {0}".format(path))
    thetas = sorted(set(r[0] for r in rows))
    phis = sorted(set(r[1] for r in rows))
    t_idx = {v: i for i, v in enumerate(thetas)}
    p_idx = {v: i for i, v in enumerate(phis)}
    e_th = np.zeros((len(thetas), len(phis)), dtype=complex)
    e_ph = np.zeros((len(thetas), len(phis)), dtype=complex)
    for th, ph, etm, etp, epm, epp in rows:
        i, j = t_idx[th], p_idx[ph]
        e_th[i, j] = etm * np.exp(1j * np.radians(etp))
        e_ph[i, j] = epm * np.exp(1j * np.radians(epp))
    return {"freq_hz": float(freq_hz), "theta": np.asarray(thetas, dtype=float),
            "phi": np.asarray(phis, dtype=float), "e_theta": e_th,
            "e_phi": e_ph}


def parse_radiation_patterns_all(path):
    """EVERY radiation-pattern block in the file, one FarFieldResult each.

    A single NEC2 run with a multi-frequency ``FR`` card and an ``RP`` card
    emits one pattern PER FREQUENCY — measured 2026-08-06: 201 sweep points
    produced 201 pattern blocks in 7.18 s, one process. So per-frequency
    patterns cost one run, not N runs.

    :func:`parse_radiation_patterns` cannot be used for that file: it pours
    every sample it finds into ONE theta/phi grid, so a multi-frequency output
    would silently overwrite each frequency with the next and return a single
    plausible-looking pattern that belongs to no frequency at all. This splits
    on the frequency marker instead.

    Returns a list of ``FarFieldResult`` ordered by frequency (empty if the
    file holds no pattern blocks — an ``RP``-less deck is not an error here).
    """
    from emstudio.post.farfield import FarFieldResult

    import numpy as np

    blocks = []          # [[freq_hz, samples], ...]
    cur_f = None
    samples = None
    in_table = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _FREQ_RE.search(line)
            if m:
                # NEC2 prints the frequency header BEFORE that frequency's
                # pattern block, so this always precedes its own samples.
                cur_f = float(m.group(1)) * 1e6
                in_table = False
                continue
            if "RADIATION PATTERNS" in line:
                samples = []
                blocks.append([cur_f, samples])
                in_table = True
                continue
            if in_table:
                nums = _FLOAT_RE.findall(line)
                if len(nums) >= 5:
                    try:
                        th, ph, _v, _h, tot = (float(n) for n in nums[:5])
                    except ValueError:
                        continue
                    if -0.01 <= th <= 180.01 and -360.0 <= ph <= 360.0:
                        samples.append((th, ph, tot))
                elif samples and line.strip() == "":
                    in_table = False

    out = []
    for freq_hz, samp in blocks:
        if not samp or freq_hz is None:
            continue
        thetas = sorted(set(s[0] for s in samp))
        phis = sorted(set(s[1] for s in samp))
        gain = np.full((len(thetas), len(phis)), -999.99)
        t_idx = {v: i for i, v in enumerate(thetas)}
        p_idx = {v: i for i, v in enumerate(phis)}
        for th, ph, tot in samp:
            gain[t_idx[th], p_idx[ph]] = tot
        out.append(FarFieldResult(freq_hz, thetas, phis, gain,
                                  meta={"backend": "nec2c"}))
    out.sort(key=lambda ff: ff.freq)
    return out


def parse_radiation_patterns(path, freq_hz):
    """Parse the RADIATION PATTERNS table into a FarFieldResult.

    nec2c row format (verified 2026-07-05, nec2c 1.3.1):
        THETA  PHI  VERTC(dB)  HORIZ(dB)  TOTAL(dB)  ...
    Nulls print as -999.99; FarFieldResult clips them to its gain floor.
    """
    from emstudio.post.farfield import FarFieldResult

    samples = []  # (theta, phi, total_gain_db)
    in_table = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "RADIATION PATTERNS" in line:
                in_table = True
                continue
            if in_table:
                nums = _FLOAT_RE.findall(line)
                if len(nums) >= 5:
                    try:
                        th, ph, _v, _h, tot = (float(n) for n in nums[:5])
                    except ValueError:
                        continue
                    # header lines contain no leading angle floats; data rows do
                    if -0.01 <= th <= 180.01 and -360.0 <= ph <= 360.0:
                        samples.append((th, ph, tot))
                elif samples and line.strip() == "":
                    # blank line after data block ends the table
                    in_table = False

    if not samples:
        raise NecParseError("no radiation-pattern data found in {0}".format(path))

    import numpy as np

    thetas = sorted(set(s[0] for s in samples))
    phis = sorted(set(s[1] for s in samples))
    gain = np.full((len(thetas), len(phis)), -999.99)
    t_idx = {v: i for i, v in enumerate(thetas)}
    p_idx = {v: i for i, v in enumerate(phis)}
    for th, ph, tot in samples:
        gain[t_idx[th], p_idx[ph]] = tot
    return FarFieldResult(freq_hz, thetas, phis, gain, meta={"backend": "nec2c"})
