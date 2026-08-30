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
    """Parse the CURRENTS AND LOCATION table nearest ``freq_hz``.

    nec2c format (verified 2026-07-05):
        SEG TAG   X Y Z (wavelengths)   LENGTH   REAL IMAG MAGN PHASE

    THE COORDINATES ARE IN WAVELENGTHS — NEC-2's convention for this table —
    so parsing needs a frequency to scale them back to metres, and it must be
    the frequency OF THE TABLE IT PARSED. This function used to read the FIRST
    table in the file and scale it with the CALLER'S frequency. On the
    single-frequency decks it was written for, those are the same thing. On a
    multi-frequency pattern deck (the DEFAULT path since the v0.92 pre-run
    dialog) they are not: the first table belongs to the band-start frequency,
    so a 10–100 MHz sweep of a 300 mm helix drew a "Wire currents" overlay
    scaled by lam(67.6 MHz)/lam(10 MHz) — a 44 mm miniature of a 300 mm coil —
    carrying the 10 MHz current VALUES under a best-match label. Both halves
    wrong, neither visibly an error (2026-08-07, AJ's screenshot).

    Now: every currents table is collected with the frequency header that
    precedes it (same ``_FREQ_RE`` discriminator the pattern splitter uses),
    the block NEAREST ``freq_hz`` is chosen, and its coordinates are scaled by
    THAT BLOCK'S OWN wavelength — so the geometry is exact even when the
    nearest solved frequency is not the requested one. A single-frequency file
    has one block and behaves exactly as before. The returned ``freq`` is the
    block's actual frequency, so labels downstream state what the data IS.

    Returns dict: {seg, tag, pos_m (N,3), i_complex, i_mag, freq}.
    """
    import numpy as np

    blocks = _currents_blocks(path)
    if not blocks:
        raise NecParseError("no current data found in {0}".format(path))
    # A block with no frequency header (never seen from nec2c/nec2++, but the
    # format is not ours) can only be scaled by the caller's frequency.
    f_blk, rows = min(blocks,
                      key=lambda fr: abs((fr[0] or freq_hz) - freq_hz))
    return _currents_dict(f_blk or freq_hz, rows)


def parse_currents_all(path):
    """EVERY currents table in the file, one dict per solved frequency.

    The multi-frequency pattern deck carries a CURRENTS AND LOCATION table per
    FR step — the same one-run economics as the patterns — so the current
    distribution can be scrubbed across the band exactly like the balloon
    (AJ's ask, 2026-08-07). Each block is scaled by its own wavelength; the
    list comes back sorted by frequency, matching ``parse_radiation_patterns_
    all``'s ordering so the two index identically in the results dialog.

    Blocks without a frequency header cannot be scaled and are skipped —
    unlike :func:`parse_currents`, there is no caller's frequency to fall
    back on. Returns [] for a file with no currents at all.
    """
    out = [_currents_dict(f, rows) for f, rows in _currents_blocks(path) if f]
    out.sort(key=lambda c: c["freq"])
    return out


def _currents_blocks(path):
    """[(freq_hz_or_None, rows)] for every CURRENTS AND LOCATION table."""
    blocks = []
    cur_f = None
    rows = None
    in_table = False
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _FREQ_RE.search(line)
            if m:
                # the frequency datum precedes its own tables in the output
                cur_f = float(m.group(1)) * 1e6
                in_table = False
                continue
            if "CURRENTS AND LOCATION" in line:
                in_table = True
                rows = []
                blocks.append((cur_f, rows))
                continue
            if in_table:
                nums = _FLOAT_RE.findall(line)
                if len(nums) >= 10:
                    try:
                        seg, tag = int(float(nums[0])), int(float(nums[1]))
                        x, y, z, _l, re_i, im_i, mag, _ph = (float(n) for n in nums[2:10])
                    except ValueError:
                        continue
                    rows.append((seg, tag, x, y, z, re_i, im_i, mag))
                elif rows and not line.strip():
                    in_table = False
    return [(f, r) for f, r in blocks if r]


def _currents_dict(freq_hz, rows):
    """One parsed currents table, wavelength-relative rows -> metres."""
    import numpy as np

    lam = 299792458.0 / freq_hz
    arr = np.asarray(rows, dtype=float)
    return {
        "seg": arr[:, 0].astype(int),
        "tag": arr[:, 1].astype(int),
        "pos_m": arr[:, 2:5] * lam,
        "i_complex": arr[:, 5] + 1j * arr[:, 6],
        "i_mag": arr[:, 7],
        "freq": freq_hz,
    }



def _pattern_blocks(path):
    """Every RADIATION PATTERNS block in the file, with its frequency label.

    Returns ``[(freq_hz_or_None, [raw data-row lines]), ...]`` in file order.
    ONE walker feeds all three pattern parsers so they cannot disagree about
    where a block begins or ends — the disagreement is exactly how the
    2026-08-29 audit's finding 26 happened (three hand-rolled loops, three
    different terminator bugs).

    ⚠ Block-end discipline, measured on real nec2c 1.3.1 output 2026-08-30
    (/tmp fixture regenerated from a live run, 3-frequency dipole sweep):
    * a BLANK line separates the banner from the column header, so "blank
      ends the block" must not arm until a data row has been seen — the old
      per-function loops armed on file-global state and returned the FIRST
      block of a swept file under whatever label the caller asked for;
    * the ``DATA CARD No:  4 EN`` trailer follows the LAST data row with NO
      blank line in between, so a terminator must also break on a line whose
      first token is not a number — counting rows or waiting for a blank
      injects a spurious theta = <card number> row (a measured 39.4 dB peak
      error in the reverted first fix attempt).
    A line is a DATA ROW iff its first token parses as float, it yields >= 5
    floats, and theta/phi land in their windows. After the first data row of
    a block, the first non-data line CLOSES that block; before it, non-data
    lines (the blank + the column headers) are simply skipped.
    """
    blocks = []
    cur_f = None
    rows = None          # None = not in a block; [] = in block, pre-data
    armed = False        # True once the current block has >= 1 data row
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _FREQ_RE.search(line)
            if m:
                cur_f = float(m.group(1)) * 1e6
                rows = None
                armed = False
                continue
            if "RADIATION PATTERNS" in line:
                rows = []
                blocks.append((cur_f, rows))
                armed = False
                continue
            if rows is None:
                continue
            toks = line.split()
            is_data = False
            if toks:
                try:
                    float(toks[0])
                except ValueError:
                    is_data = False      # banners, headers, "DATA CARD No:"
                else:
                    nums = _FLOAT_RE.findall(line)
                    if len(nums) >= 5:
                        try:
                            th, ph = float(nums[0]), float(nums[1])
                        except ValueError:
                            th = ph = None
                        if th is not None and -0.01 <= th <= 180.01 \
                                and -360.0 <= ph <= 360.0:
                            is_data = True
            if is_data:
                rows.append(line)
                armed = True
            elif armed:
                rows = None              # block closed by first non-data line
                armed = False
    return blocks


def _nearest_block(blocks, freq_hz):
    """The block whose frequency label is nearest ``freq_hz``.

    Labelled blocks win over unlabelled ones; with no labels at all the first
    block is returned (a single-block file with no FREQUENCY header — nec2++
    variants). Returns ``(freq_label_or_None, rows)``.
    """
    labelled = [b for b in blocks if b[0] is not None]
    if labelled:
        return min(labelled, key=lambda b: abs(b[0] - float(freq_hz)))
    return blocks[0]


def parse_radiation_complex(path, freq_hz):
    """The COMPLEX-field pattern block nearest ``freq_hz`` —
    E(theta) and E(phi) magnitude+phase, which :func:`parse_radiation_patterns`
    discards (it keeps total gain only).

    A DF manifold needs amplitude AND phase per element, so this is the parse
    the §7 S6 correlative-interferometer path uses. nec2c column order
    (verified 2026-07-27): THETA PHI | VERTC HORIZ TOTAL | AXIAL TILT SENSE |
    E(THETA) mag phase | E(PHI) mag phase. The SENSE column is a word
    (LINEAR/RIGHT/LEFT) — absent on null rows, so field offsets are taken from
    the END of the numeric list, never the start.

    ⚠ CORRECTED 2026-08-30 (audit finding 26): like
    :func:`parse_radiation_patterns` this used to return the FIRST block of a
    swept file while echoing the caller's ``freq_hz`` into the result. Block
    selection now goes through :func:`_pattern_blocks` / :func:`_nearest_block`.
    Rows with fewer than 11 numbers (no complex fields) are skipped, as before.

    Returns ``{"freq_hz", "theta", "phi", "e_theta", "e_phi"}`` with the two
    field arrays complex, shaped (n_theta, n_phi).
    """
    import numpy as np

    blocks = [(f, r) for f, r in _pattern_blocks(path) if r]
    if not blocks:
        raise NecParseError(
            "no complex radiation-pattern data found in {0}".format(path))
    _f_label, lines = _nearest_block(blocks, freq_hz)

    rows = []
    for line in lines:
        nums = _FLOAT_RE.findall(line)
        if len(nums) < 11:
            continue                     # a row without the four field numbers
        th, ph = float(nums[0]), float(nums[1])
        et_mag, et_ph, ep_mag, ep_ph = (float(x) for x in nums[-4:])
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

    Built on the same :func:`_pattern_blocks` walker as the single-block
    parsers since 2026-08-30, so all three agree about where a block begins
    and ends (they did not, and the disagreement was audit finding 26).
    ⚠ Known limit, stated rather than hidden: blocks are labelled by nec2c's
    PRINTED frequency (5 significant figures). Two sweep points closer than
    that print identically and merge under one label — do not drive a
    sub-100-kHz-at-GHz sweep through this path.

    Returns a list of ``FarFieldResult`` ordered by frequency (empty if the
    file holds no pattern blocks — an ``RP``-less deck is not an error here).
    """
    from emstudio.post.farfield import FarFieldResult

    import numpy as np

    out = []
    for freq_hz, lines in _pattern_blocks(path):
        if not lines:
            continue
        samples = []
        for line in lines:
            nums = _FLOAT_RE.findall(line)
            th, ph, _v, _h, tot = (float(n) for n in nums[:5])
            samples.append((th, ph, tot))
        thetas = sorted(set(s[0] for s in samples))
        phis = sorted(set(s[1] for s in samples))
        gain = np.full((len(thetas), len(phis)), -999.99)
        t_idx = {v: i for i, v in enumerate(thetas)}
        p_idx = {v: i for i, v in enumerate(phis)}
        for th, ph, tot in samples:
            gain[t_idx[th], p_idx[ph]] = tot
        out.append(FarFieldResult(freq_hz or 0.0, thetas, phis, gain,
                                  meta={"backend": "nec2c"}))
    out.sort(key=lambda f: f.freq)
    return out

def parse_radiation_patterns(path, freq_hz):
    """The pattern block NEAREST ``freq_hz`` as a FarFieldResult.

    nec2c row format (verified 2026-07-05, nec2c 1.3.1):
        THETA  PHI  VERTC(dB)  HORIZ(dB)  TOTAL(dB)  ...
    Nulls print as -999.99; FarFieldResult clips them to its gain floor.

    ⚠ CORRECTED 2026-08-30 (audit finding 26). On a multi-frequency file the
    old loop returned the FIRST block — nec2c's blank line between banner and
    column header killed its collector from block 2 on — while labelling the
    result with the caller's ``freq_hz``: measured on a real 3-block sweep,
    asking for 300 MHz returned the 280 MHz pattern under a confident
    "300 MHz" label. (The module's own docstrings mis-described the failure
    as a last-block merge, and the gate asserted THAT story — a check on the
    wrong claim.) It now selects the block whose FREQUENCY header is nearest
    the request, via the shared :func:`_pattern_blocks` walker.
    """
    from emstudio.post.farfield import FarFieldResult

    blocks = _pattern_blocks(path)
    if not blocks or not any(rows for _f, rows in blocks):
        raise NecParseError("no radiation-pattern data found in {0}".format(path))
    _f_label, lines = _nearest_block(
        [(f, r) for f, r in blocks if r], freq_hz)

    samples = []  # (theta, phi, total_gain_db)
    for line in lines:
        nums = _FLOAT_RE.findall(line)
        th, ph, _v, _h, tot = (float(n) for n in nums[:5])
        samples.append((th, ph, tot))

    import numpy as np

    thetas = sorted(set(s[0] for s in samples))
    phis = sorted(set(s[1] for s in samples))
    gain = np.full((len(thetas), len(phis)), -999.99)
    t_idx = {v: i for i, v in enumerate(thetas)}
    p_idx = {v: i for i, v in enumerate(phis)}
    for th, ph, tot in samples:
        gain[t_idx[th], p_idx[ph]] = tot
    return FarFieldResult(freq_hz, thetas, phis, gain, meta={"backend": "nec2c"})
