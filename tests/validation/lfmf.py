# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: ITU-R P.368-10 LF/MF ground wave (the LFMF port).

Replays TWO official/oracle datasets through ``emstudio/coverage/lfmf.py``
(the numpy/scipy port of the NTIA LFMF v1.1 reference implementation — the
software that IS Recommendation P.368-10):

1. ``data/lfmf/oracle_grid.csv`` — 2497 full-double-precision rows generated
   from the unmodified upstream binary on this machine (provenance in the
   adjacent PROVENANCE.md): every A_btl / E / P_rx must match to <= 1e-3 dB
   (live reference run of the port: worst 3.2e-5 dB) and every
   flat-earth/residue-series method flag must match exactly.

   1b. the eps_r == 1 / pol 0 branch cut (the 32 flat-earth rows of the
   eps == 1 block): the engine's qi product must NOT be a fused complex
   multiply. One bit there (the sign of a ~1e-16 residue, or of a zero)
   decides which side of the sqrt cut F(p) lands on. It was 21 rows, up to
   1.69 dB, off on FreeCAD 1.1.4 macOS arm64, whose complex '*' is
   FMA-contracted (fixed 2026-10-17, v1.14.0). On x86 the replay above
   CANNOT see a revert, because complex '*' there is unfused too. So 1b
   records the operands the engine really passes, checks them against an
   exact (fractions.Fraction) model of a fused multiply, proves the replay
   would catch the fused result, and checks the source.
2. ``data/lfmf/LFMF_Examples.csv`` — the official NTIA example file: the 5
   valid rows to their printed 0.1 precision, and all 90 input-validation
   rows must be REJECTED for the reason matching their error code.

Also gates the ``groundwave`` spherical wrapper: flat-vs-spherical agreement
at short range, the beyond-100-km divergence, spherical Millington
reciprocity, and the <10 kHz hard-stop.

Pass: exit 0 and 'LFMF GATE PASSED'. Pure python3 (scipy; no FreeCAD).
"""
import ast
import csv
import math
import os
import sys
from fractions import Fraction

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "tests", "validation", "data", "lfmf")

FAILURES = []

# upstream ReturnCode -> a keyword the port's ValueError message must contain
ERROR_CODE_KEYWORDS = {
    32: "TX height",
    33: "RX height",
    34: "frequency",
    35: "power",
    36: "refractivity",
    37: "distance",
    38: "permittivity",
    39: "conductivity",
    40: "pol",
}


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _row_inputs(row):
    return (float(row["h_tx__meter"]), float(row["h_rx__meter"]),
            float(row["f__mhz"]), float(row["P_tx__watt"]),
            float(row["N_s"]), float(row["d__km"]),
            float(row["epsilon"]), float(row["sigma"]), int(row["pol"]))


def _row_dev_db(got, row):
    """Worst |port - oracle| over A_btl / E / P_rx, dB (NaN propagates)."""
    return max(abs(got["A_btl__db"] - float(row["A_btl__db"])),
               abs(got["E_dBuVm"] - float(row["E_dBuVm"])),
               abs(got["P_rx__dbm"] - float(row["P_rx__dbm"])))


# The oracle-grid replay tolerance, dB. ONE constant because section 1b's
# negative control must fail rows at exactly the tolerance the replay check
# uses: loosen this and the control stops seeing the arm64 flips and FAILS,
# so it guards the tolerance too. The replay check's NAME quotes "1e-3 dB"
# (docs quote that name); change both together.
GRID_TOL_DB = 1e-3

# The number of eps == 1 / pol 0 / flat-earth rows in oracle_grid.csv (its
# 128-row eps == 1 block = 2 pol x 2 methods x 32). Pinned so section 1b
# cannot go vacuous if the grid is ever regenerated without that block.
N_CUT_ROWS = 32

# How many of those 32 rows FAILED the <= 1e-3 dB replay on real arm64
# hardware with the unfixed engine (FreeCAD 1.1.4's bundled Python 3.11 on
# the M1 build host, 2026-10-17). The negative control below must reproduce
# it EXACTLY with the fused model swapped in. That ties the model to
# measured hardware, not to the number under test: the model is written
# from the disassembly, and the 21 came from running the Mac (re-confirmed
# 2026-10-17 by this gate's pre-fix version there: 21 rows, worst 1.69 dB).
N_CUT_ROWS_FAILED_ON_ARM64 = 21


def _cmul_fused_model(a, b):
    """EXACT model of an FMA-contracted CPython complex multiply.

    FreeCAD 1.1.4's macOS arm64 libpython3.11 compiles ``_Py_c_prod`` to
    ``fnmul`` + ``fmadd``: ``Re = fma(a.r, b.r, -round(a.i*b.i))``, i.e. the
    a.r*b.r product is never rounded. ``Fraction`` makes the product exact
    and ``float()`` rounds the sum ONCE (CPython's int/int true division is
    correctly rounded), which is what an FMA does. Verified on the M1
    (2026-10-17): its native complex '*' equals this model bit-for-bit, both
    parts, on all 32 cut rows (section 1b prints that as "FUSED" there), and
    the swapped-in model reproduces its 21 failing rows. The Re order
    matters: the opposite order flips the residue's SIGN, and so which rows
    fail. The Im order cannot be told apart on these rows (its two products
    are equal, so both orders give the same bits) and does not matter:
    Im(qi) is a SUM there and nothing cancels.
    """
    re = float(Fraction(a.real) * Fraction(b.real) - Fraction(a.imag * b.imag))
    im = float(Fraction(a.real) * Fraction(b.imag) + Fraction(a.imag * b.real))
    return complex(re, im)


def _cmul_separate_model(a, b):
    """Exact model of the UNFUSED multiply: each product rounded to double,
    then the sum rounded once. This is x86 CPython and the reference binary."""
    re = float(Fraction(a.real * b.real) - Fraction(a.imag * b.imag))
    im = float(Fraction(a.real * b.imag) + Fraction(a.imag * b.real))
    return complex(re, im)


def _source_checks(lfmf_mod):
    """AST checks on the engine source.

    Returns ``(helper_ok, helper_detail, call_ok, call_detail)``.

    A value check cannot catch a revert to complex '*' on x86 (unfused there
    too), so the property is pinned in the source:
    * _cmul_unfused: EVERY multiplication has a ``.real``/``.imag`` attribute
      on both sides (float x float, so it cannot be a complex multiply), there
      are exactly the 4 such products, and the only call is ``complex(...)``.
      That catches ``return a * b``, ``complex(a) * b``, ``a.__mul__(b)``,
      ``operator.mul`` and ``math.fma`` alike.
    * _flat_earth_curve_correction: exactly one assignment to ``qi``, and it
      is ``qi = _cmul_unfused(<anything>, delta)``.
    """
    with open(lfmf_mod.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    funcs = {n.name: n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)}

    helper_ok = False
    fn = funcs.get("_cmul_unfused")
    if fn is None:
        helper_detail = "no _cmul_unfused in the engine"
    else:
        def _is_part(node):
            return (isinstance(node, ast.Attribute)
                    and node.attr in ("real", "imag"))
        mults = [n for n in ast.walk(fn) if isinstance(n, ast.BinOp)
                 and isinstance(n.op, ast.Mult)]
        bad = [ast.dump(m) for m in mults
               if not (_is_part(m.left) and _is_part(m.right))]
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        bad_calls = [ast.dump(c.func) for c in calls
                     if not (isinstance(c.func, ast.Name)
                             and c.func.id == "complex")]
        helper_ok = not bad and not bad_calls and len(mults) == 4
        helper_detail = ("{0} float products, {1} non-float, {2} foreign "
                         "call(s)".format(len(mults) - len(bad), len(bad),
                                          len(bad_calls)))

    call_ok = False
    fn = funcs.get("_flat_earth_curve_correction")
    if fn is None:
        call_detail = "no _flat_earth_curve_correction in the engine"
    else:
        assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "qi"
                           for t in n.targets)]
        aug = [n for n in ast.walk(fn) if isinstance(n, (ast.AugAssign,
                                                         ast.AnnAssign))
               and isinstance(n.target, ast.Name) and n.target.id == "qi"]
        if len(assigns) == 1 and not aug:
            v = assigns[0].value
            call_ok = (isinstance(v, ast.Call)
                       and isinstance(v.func, ast.Name)
                       and v.func.id == "_cmul_unfused"
                       and len(v.args) == 2 and not v.keywords
                       and isinstance(v.args[1], ast.Name)
                       and v.args[1].id == "delta")
        call_detail = "{0} assignment(s) to qi, {1}".format(
            len(assigns) + len(aug),
            "via _cmul_unfused(..., delta)" if call_ok else "NOT via the helper")
    return helper_ok, helper_detail, call_ok, call_detail


def main():
    from emstudio.coverage import groundwave, lfmf

    print("EMStudio P.368-10 LFMF validation gate")

    # ---- 1. the dense full-precision oracle grid ----
    worst = 0.0
    worst_case = ""
    n = 0
    n_bad = 0            # rows over tolerance — NaN-safe (not dev <= tol)
    n_method_bad = 0
    with open(os.path.join(DATA, "oracle_grid.csv")) as fh:
        for row in csv.DictReader(fh):
            got = lfmf.lfmf(*_row_inputs(row))
            # _row_dev_db is shared with section 1b's negative control, so
            # the control measures exactly what this check measures
            dev = _row_dev_db(got, row)
            if got["method"] != int(row["method"]):
                n_method_bad += 1
            # NaN-proof: a NaN dev must FAIL, so compare via "not <=", never ">"
            if not (dev <= GRID_TOL_DB):
                n_bad += 1
            if math.isnan(dev) or dev > worst:
                worst = dev
                worst_case = "f={0} MHz d={1} km eps={2} sigma={3} pol={4}".format(
                    row["f__mhz"], row["d__km"], row["epsilon"], row["sigma"],
                    row["pol"])
            n += 1
    check("oracle grid fully replayed (2497 rows, both methods)", n == 2497,
          str(n))
    check("A_btl/E/P_rx match the reference binary <= 1e-3 dB on EVERY row",
          n_bad == 0,
          "{0} rows over; worst {1:.2e} dB ({2})".format(n_bad, worst,
                                                         worst_case))
    check("flat-earth/residue method switch matches on every row",
          n_method_bad == 0, "{0} mismatches".format(n_method_bad))

    # ---- 1b. the eps_r == 1 / pol 0 cut: qi must not be a fused multiply ----
    # The check above is what failed on the Mac (21 rows, up to 1.69 dB), but
    # on x86 it cannot fail for this defect: a revert to complex '*' gives
    # the same bits there. So: (a) record the operands the engine REALLY
    # passes to _cmul_unfused on the 32 cut rows (never re-derive k / delta
    # here; a re-derivation would check our copy, not the engine) and prove
    # the helper's result is the unfused value with Re == +0.0 while an
    # exact fused model leaves a residue; (b) a negative control: with the
    # fused model swapped in, the replay above would fail on exactly the
    # rows arm64 failed; (c) the source must keep both halves of the fix.
    with open(os.path.join(DATA, "oracle_grid.csv")) as fh:
        cut_rows = [r for r in csv.DictReader(fh)
                    if float(r["epsilon"]) == 1.0 and int(r["pol"]) == 0
                    and int(r["method"]) == lfmf.FLAT_EARTH_CURVE]
    helper = getattr(lfmf, "_cmul_unfused", None)

    def _bits(z):
        # bitwise identity: '==' calls -0.0 equal to +0.0, but a -0.0 in
        # Re(qi) flips the sqrt branch exactly as a negative residue does
        return (z.real.hex(), z.imag.hex())

    per_row = []                 # the helper calls each cut row made
    if helper is not None:
        rec = []

        def _recording(a, b):
            out = helper(a, b)
            rec.append((a, b, out))
            return out

        lfmf._cmul_unfused = _recording
        try:
            for row in cut_rows:
                del rec[:]
                lfmf.lfmf(*_row_inputs(row))
                per_row.append(list(rec))
        finally:
            lfmf._cmul_unfused = helper
    one_call = [calls[0] for calls in per_row if len(calls) == 1]
    n_exact = sum(1 for a, b, out in one_call
                  if _bits(out) == _bits(_cmul_separate_model(a, b))
                  and _bits(out)[0] == (0.0).hex())
    fused_re = [_cmul_fused_model(a, b).real for a, b, _ in one_call]
    n_fused_nz = sum(1 for x in fused_re if x != 0.0)
    neg_rows = {i for i, calls in enumerate(per_row) if len(calls) == 1
                and _cmul_fused_model(calls[0][0], calls[0][1]).real < 0.0}
    # informational only (platform-dependent, so NOT asserted): which model
    # this interpreter's own complex '*' matches on these operands. x86
    # prints "unfused"; the FreeCAD 1.1.4 M1 bundle prints "FUSED".
    n_nat_sep = sum(1 for a, b, _ in one_call
                    if _bits(a * b) == _bits(_cmul_separate_model(a, b)))
    n_nat_fused = sum(1 for a, b, _ in one_call
                      if _bits(a * b) == _bits(_cmul_fused_model(a, b)))
    if one_call and n_nat_sep == len(one_call):
        native = "unfused"
    elif one_call and n_nat_fused == len(one_call):
        native = "FUSED (matches the FMA model bit-for-bit)"
    else:
        native = "mixed: {0} unfused / {1} fused-model of {2}".format(
            n_nat_sep, n_nat_fused, len(one_call))
    check("eps_r=1/pol 0 cut: all {0} rows send qi through _cmul_unfused, "
          "Re(qi) == +0.0 exactly; an exact FMA model of the same operands "
          "leaves Re != 0 on every row".format(N_CUT_ROWS),
          len(cut_rows) == N_CUT_ROWS and len(one_call) == N_CUT_ROWS
          and n_exact == N_CUT_ROWS and n_fused_nz == N_CUT_ROWS,
          "{0} rows, {1} with exactly one helper call, {2} exact unfused "
          "+0.0; fused model Re != 0 on {3} ({4} negative); this "
          "interpreter's complex '*': {5} (informational)".format(
              len(cut_rows), len(one_call), n_exact, n_fused_nz,
              len(neg_rows), native))

    # (b) the negative control: swap the FMA model in for the helper and
    # replay the cut rows against the oracle, at the SAME tolerance and the
    # SAME deviation measure as the replay check above.
    lfmf._cmul_unfused = _cmul_fused_model
    try:
        over_rows = {i for i, row in enumerate(cut_rows)
                     if not (_row_dev_db(lfmf.lfmf(*_row_inputs(row)), row)
                             <= GRID_TOL_DB)}
    finally:
        if helper is None:
            del lfmf._cmul_unfused
        else:
            lfmf._cmul_unfused = helper
    check("negative control: with the FMA model swapped in, the replay "
          "fails exactly the {0} cut rows arm64 failed, each one a negative "
          "fused residue".format(N_CUT_ROWS_FAILED_ON_ARM64),
          len(over_rows) == N_CUT_ROWS_FAILED_ON_ARM64
          and over_rows == neg_rows,
          "{0} rows over {1:g} dB, {2} negative residues, sets {3}".format(
              len(over_rows), GRID_TOL_DB, len(neg_rows),
              "equal" if over_rows == neg_rows else "DIFFER"))

    # (c) the source: the only check that sees a revert on x86
    helper_ok, helper_detail, call_ok, call_detail = _source_checks(lfmf)
    check("source: _cmul_unfused multiplies only .real/.imag floats "
          "(no complex '*', call or fma)", helper_ok, helper_detail)
    check("source: the qi product is computed as _cmul_unfused(..., delta)",
          call_ok, call_detail)

    # ---- 2. the official NTIA examples file ----
    n_valid = 0
    n_err = 0
    ok_valid = True
    ok_err = True
    with open(os.path.join(DATA, "LFMF_Examples.csv")) as fh:
        for row in csv.DictReader(fh):
            rtn = int(row["rtn"])
            if rtn == 0:
                got = lfmf.lfmf(*_row_inputs(row))
                dev = max(abs(got["A_btl__db"] - float(row["A_btl__db"])),
                          abs(got["E_dBuVm"] - float(row["E_dBuVm"])),
                          abs(got["P_rx__dbm"] - float(row["P_rx__dbm"])))
                # NaN-safe: "not <=" fails on NaN where "> 0.05" would pass
                if not (dev <= 0.05) or got["method"] != int(row["method"]):
                    ok_valid = False
                    check("official example row f={0} d={1}".format(
                        row["f__mhz"], row["d__km"]), False,
                        "dev {0:.3f} dB".format(dev))
                n_valid += 1
            else:
                keyword = ERROR_CODE_KEYWORDS[rtn]
                try:
                    lfmf.lfmf(*_row_inputs(row))
                    ok_err = False
                    check("error row (code {0}) not rejected".format(rtn),
                          False)
                except ValueError as exc:
                    if keyword.lower() not in str(exc).lower():
                        ok_err = False
                        check("error row (code {0}) wrong reason".format(rtn),
                              False, str(exc))
                n_err += 1
    check("all 5 official worked examples match to their printed 0.1 digit",
          ok_valid and n_valid == 5, "{0} rows".format(n_valid))
    check("all 90 official error rows rejected for the coded reason",
          ok_err and n_err == 90, "{0} rows".format(n_err))

    # ---- 3. the groundwave module wrappers ----
    # flat vs spherical agree at short range (both are the Sommerfeld flat
    # earth at 50 km; the |A| interpolation differs from the exact wofz by
    # ~1 dB there, so this is a sanity band, not a digit gate)
    e_flat = groundwave.field_strength_dbuv_m(50e3, 1e6, 13.0, 5e-3)
    e_sph = groundwave.spherical_field_strength_dbuv_m(50e3, 1e6, 13.0, 5e-3)
    check("flat vs P.368-10 agree at 50 km / 1 MHz (within 1.5 dB)",
          abs(e_flat - e_sph) < 1.5,
          "flat {0:.2f} vs spherical {1:.2f} dBuV/m".format(e_flat, e_sph))

    # beyond 100 km the flat model UNDER-predicts the loss growth rate on a
    # curved earth: at 1000 km the spherical field must be far below flat
    e_flat_1000 = groundwave.field_strength_dbuv_m(1000e3, 1e6, 13.0, 5e-3)
    e_sph_1000 = groundwave.spherical_field_strength_dbuv_m(
        1000e3, 1e6, 13.0, 5e-3)
    check("spherical earth attenuates far more at 1000 km / 1 MHz",
          e_sph_1000 < e_flat_1000 - 30.0,
          "flat {0:.1f} vs spherical {1:.1f} dBuV/m".format(
              e_flat_1000, e_sph_1000))

    # spherical field must fall monotonically with distance (sea, 500 kHz)
    ds = [100e3, 300e3, 1000e3, 3000e3]
    es = [groundwave.spherical_field_strength_dbuv_m(d, 5e5, 70.0, 5.0)
          for d in ds]
    check("spherical field falls monotonically 100->3000 km over sea",
          all(es[i] > es[i + 1] for i in range(len(es) - 1)),
          " > ".join("{0:.1f}".format(e) for e in es))

    # sea > average > very dry at 500 km / 1 MHz (the P.368 ordering)
    e_sea = groundwave.spherical_field_strength_dbuv_m(500e3, 1e6, 70.0, 5.0)
    e_avg = groundwave.spherical_field_strength_dbuv_m(500e3, 1e6, 13.0, 5e-3)
    e_dry = groundwave.spherical_field_strength_dbuv_m(500e3, 1e6, 3.0, 1e-4)
    check("ground ordering sea > average > very dry at 500 km",
          e_sea > e_avg > e_dry,
          "{0:.1f} / {1:.1f} / {2:.1f} dBuV/m".format(e_sea, e_avg, e_dry))

    # CMF normalization: E -> CMF/d as attenuation -> 1 (short sea path,
    # low frequency), matching the flat module's reference convention
    d_ref = 1e3
    e_ref = groundwave.spherical_field_strength_dbuv_m(d_ref, 1e4, 70.0, 5.0)
    e_ideal = 20.0 * math.log10((300.0 / d_ref) * 1e6)
    check("spherical CMF reference: 300 V -> ~300 mV/m at 1 km (sea, 10 kHz)",
          abs(e_ref - e_ideal) < 0.1,
          "{0:.3f} vs {1:.3f} dBuV/m".format(e_ref, e_ideal))

    # Millington on the spherical engine stays reciprocal
    segs = [(100e3, 13.0, 5e-3), (150e3, 70.0, 5.0)]
    m_fwd = groundwave.millington_field_dbuv_m(segs, 1e6, spherical=True)
    m_rev = groundwave.millington_field_dbuv_m(list(reversed(segs)), 1e6,
                                               spherical=True)
    check("spherical Millington mixed path is reciprocal",
          abs(m_fwd - m_rev) < 1e-9,
          "{0:.3f} vs {1:.3f} dBuV/m".format(m_fwd, m_rev))
    # ... and the mixed path lies between the homogeneous extremes
    e_all_land = groundwave.spherical_field_strength_dbuv_m(250e3, 1e6,
                                                            13.0, 5e-3)
    e_all_sea = groundwave.spherical_field_strength_dbuv_m(250e3, 1e6,
                                                           70.0, 5.0)
    check("spherical Millington lies between homogeneous land and sea",
          e_all_land < m_fwd < e_all_sea,
          "{0:.1f} < {1:.1f} < {2:.1f}".format(e_all_land, m_fwd, e_all_sea))

    # the VLF hard-stop: 9 kHz must raise, never extrapolate
    try:
        groundwave.spherical_field_strength_dbuv_m(100e3, 9e3, 70.0, 5.0)
        stopped = False
    except ValueError:
        stopped = True
    check("below 10 kHz the spherical model HARD-STOPS (P.684 band)", stopped)

    # ---- 4. the heatmap opt-in wiring ----
    import numpy as np

    from emstudio.coverage import heatmap

    res_flat = heatmap.coverage_grid(40.0, -100.0, 10.0, 1e6, 60.0,
                                     radius_m=150e3, n=11,
                                     model="ground_wave")
    res_flat2 = heatmap.coverage_grid(40.0, -100.0, 10.0, 1e6, 60.0,
                                      radius_m=150e3, n=11,
                                      model="ground_wave", gw_engine="flat")
    check("heatmap default gw_engine is byte-identical to explicit 'flat'",
          np.array_equal(res_flat.field_dbuv_m, res_flat2.field_dbuv_m, equal_nan=True))

    res_sph = heatmap.coverage_grid(40.0, -100.0, 10.0, 1e6, 60.0,
                                    radius_m=150e3, n=11,
                                    model="ground_wave", gw_engine="p368")
    check("heatmap meta records the ground-wave engine",
          res_flat.meta.get("gw_engine") == "flat"
          and res_sph.meta.get("gw_engine") == "p368")
    # the far corner (~212 km) must show the spherical-earth extra loss
    d_far = np.nanmax(res_sph.dist_m)
    i, j = np.unravel_index(np.nanargmax(res_sph.dist_m),
                            res_sph.dist_m.shape)
    check("heatmap far cell (>{0:.0f} km) spherical << flat".format(
        d_far / 1e3 - 1),
          res_sph.field_dbuv_m[i, j] < res_flat.field_dbuv_m[i, j] - 3.0,
          "flat {0:.1f} vs p368 {1:.1f} dBuV/m".format(
              float(res_flat.field_dbuv_m[i, j]), float(res_sph.field_dbuv_m[i, j])))

    if FAILURES:
        print("LFMF GATE FAILED: {0}".format(FAILURES))
        return 1
    print("LFMF GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback

        traceback.print_exc()
        raise SystemExit("lfmf validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("lfmf validation failed")
    sys.exit(0)
