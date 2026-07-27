# SPDX-License-Identifier: LGPL-2.1-or-later
"""Result container for Elmer magnetics runs (induction heating / WPT).

Not an S-parameter sweep — magnetics runs produce per-frequency scalars
(eddy/Joule power, coil flux linkages) plus field VTUs. Shared by the
runner, the GUI dialog, and the validation gates; Qt-free and
FreeCAD-free.

Conventions (pinned by tests/validation/induction_elmer.py against the
Bessel analytic, 2026-07-05):

* coil currents are PEAK amplitudes; powers are time-averaged watts,
* ``eddy_power_w`` is already the full-circumference value (the raw Elmer
  axisymmetric scalar is per radian — the runner multiplies by 2*pi),
* coil impedance from linkage: Z = j*omega*lambda / I, so
  L_eff = Re(lambda)/I and R_reflected = -omega*Im(lambda)/I (the series
  resistance the eddy losses present to the source; equals 2P/I^2).
"""
from __future__ import annotations

import math


class MagneticsResult:
    """Results of one magnetics analysis (possibly a frequency sweep).

    ``cases`` is a list of dicts, one per (frequency, excitation) solve:
        freq_hz, tag, excitation ({coil: scale}), eddy_power_w, energy_j,
        body_power_w ({body: W}), coil_lambda ({coil: complex Wb-turns}),
        vtu (path), rundir (path).
    ``coils`` is a list of dicts {name, turns, current_a, ...}.
    """

    def __init__(self, cases, coils, bodies, meta=None):
        self.cases = list(cases)
        self.coils = list(coils)
        self.bodies = list(bodies)
        self.meta = dict(meta or {})

    # -- helpers -----------------------------------------------------------

    def _coil(self, name):
        for c in self.coils:
            if c["name"] == name:
                return c
        raise KeyError(name)

    def sweep_cases(self):
        """The all-coils-excited cases, sorted by frequency."""
        out = [c for c in self.cases if c["tag"].startswith("sweep")]
        return sorted(out, key=lambda c: c["freq_hz"])

    def coupling_cases(self):
        """Single-coil-excited cases (coupling extraction)."""
        return [c for c in self.cases if c["tag"].startswith("couple_")]

    # -- derived quantities -------------------------------------------------

    def freqs_hz(self):
        return [c["freq_hz"] for c in self.sweep_cases()]

    def eddy_power_w(self):
        """Total time-averaged eddy/Joule power per sweep frequency (W)."""
        return [c["eddy_power_w"] for c in self.sweep_cases()]

    def coil_impedance(self, coil_name):
        """(freqs, L_eff_H, R_reflected_ohm) for one coil over the sweep.

        L_eff/R are the OPERATING-point values (all coils driven at their own
        currents); undefined (NaN) for an undriven coil (current 0) — use the
        inductance matrix for its self-inductance instead.
        """
        freqs, ls, rs = [], [], []
        current = float(self._coil(coil_name)["current_a"])
        for c in self.sweep_cases():
            lam = c["coil_lambda"][coil_name]
            w = 2.0 * math.pi * c["freq_hz"]
            freqs.append(c["freq_hz"])
            if current == 0:
                ls.append(float("nan"))
                rs.append(float("nan"))
            else:
                ls.append(lam.real / current)
                rs.append(-w * lam.imag / current)
        return freqs, ls, rs

    def inductance_matrix(self):
        """{(exciter, sensed): L in henries} from the coupling cases.

        Normalized by the coupling REFERENCE current the case actually used
        (``ref_current_a``; falls back to the operating current for older
        results), so L/M/k are correct even for an undriven coil.
        """
        out = {}
        for c in self.coupling_cases():
            exciter = c["tag"][len("couple_"):]
            i_exc = c.get("ref_current_a") or float(self._coil(exciter)["current_a"])
            if not i_exc:
                continue  # no reference current — cannot normalize
            for name, lam in c["coil_lambda"].items():
                out[(exciter, name)] = lam.real / i_exc
        return out

    def heating_curve(self):
        """(time_s, T_max_K) lists for the transient heating case, or None."""
        for c in self.cases:
            h = c.get("temp_history")
            if h:
                return h["time_s"], h["t_max_k"]
        return None

    def coupling_k(self):
        """{(coil_i, coil_j): k} for every coil pair (needs coupling cases)."""
        lmat = self.inductance_matrix()
        ks = {}
        names = [c["name"] for c in self.coils]
        for i, ni in enumerate(names):
            for nj in names[i + 1:]:
                try:
                    l1 = lmat[(ni, ni)]
                    l2 = lmat[(nj, nj)]
                    m = 0.5 * (lmat[(ni, nj)] + lmat[(nj, ni)])
                except KeyError:
                    continue
                if l1 > 0 and l2 > 0:
                    ks[(ni, nj)] = abs(m) / math.sqrt(l1 * l2)
        return ks

    # -- reporting -----------------------------------------------------------

    def summary_text(self):
        lines = []
        add = lines.append
        if self.meta.get("mode3d"):
            add("EMStudio magnetics results (Elmer, GENERAL 3-D magnetostatic"
                " — WhitneyAV)")
            add("")
            add("B-field map: use 'Show Fields in 3D'. Coil inductance/flux-")
            add("linkage extraction for 3-D coils is a planned slice; the")
            add("axisymmetric analyses report L/M/k today.")
        else:
            add("EMStudio magnetics results (Elmer, axisymmetric {0})".format(
                "static DC" if self.meta.get("static") else "harmonic"))
        add("")
        sweeps = self.sweep_cases()
        if sweeps:
            add("frequency sweep ({0} point{1}):".format(
                len(sweeps), "" if len(sweeps) == 1 else "s"))
            add("  {0:>12}  {1:>14}  {2}".format("f [Hz]", "eddy P [W]", "per-body [W]"))
            for c in sweeps:
                per = "  ".join("{0}={1:.4g}".format(k, v)
                                for k, v in sorted(c["body_power_w"].items()))
                add("  {0:>12.6g}  {1:>14.6g}  {2}".format(
                    c["freq_hz"], c["eddy_power_w"], per))
            add("")
            for coil in self.coils:
                freqs, ls, rs = self.coil_impedance(coil["name"])
                for f, l_h, r in zip(freqs, ls, rs):
                    if math.isnan(l_h):
                        add("  coil '{0}' @ {1:.6g} Hz:  (undriven — 0 A; see "
                            "inductance matrix)".format(coil["name"], f))
                    else:
                        add("  coil '{0}' @ {1:.6g} Hz:  L_eff = {2:.6g} uH,  "
                            "R_reflected = {3:.6g} mOhm".format(
                                coil["name"], f, l_h * 1e6, r * 1e3))
            add("")
            if any(c.get("temperature") for c in sweeps):
                curve = self.heating_curve()
                kind = "temperatures after {0:.0f} s of heating".format(curve[0][-1]) \
                    if curve else "steady-state temperatures"
                add("{0} (convection surface):".format(kind))
                for c in sweeps:
                    for body, t in sorted((c.get("temperature") or {}).items()):
                        add("  '{0}' @ {1:.6g} Hz:  T_max = {2:.2f} K "
                            "({3:.1f} C), T_mean = {4:.2f} K".format(
                                body, c["freq_hz"], t["t_max"],
                                t["t_max"] - 273.15, t["t_mean"]))
                if curve:
                    add("  (transient: {0} steps, {1:.0f} s total — see the "
                        "heating-curve page)".format(len(curve[0]), curve[0][-1]))
                add("")
        lmat = self.inductance_matrix()
        if lmat:
            add("inductance matrix (from single-coil excitations):")
            for (i, j), l_h in sorted(lmat.items()):
                kind = "L" if i == j else "M"
                add("  {0}({1} -> {2}) = {3:.6g} uH".format(kind, i, j, l_h * 1e6))
            for (ni, nj), k in sorted(self.coupling_k().items()):
                add("  k({0}, {1}) = {2:.5g}".format(ni, nj, k))
            add("")
        if self.meta.get("workdir"):
            add("workdir: {0}".format(self.meta["workdir"]))
        if self.meta.get("duration_s") is not None:
            add("solve time: {0:.1f} s".format(self.meta["duration_s"]))
        return "\n".join(lines)

    def save_summary(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.summary_text() + "\n")
        return path

    def save_csv(self, path):
        """Per-sweep-frequency CSV: powers and coil linkages."""
        cols = ["freq_hz", "eddy_power_w"]
        bodies = sorted({k for c in self.sweep_cases() for k in c["body_power_w"]})
        cols += ["P_{0}_w".format(b) for b in bodies]
        coils = [c["name"] for c in self.coils]
        for n in coils:
            cols += ["re_lambda_{0}".format(n), "im_lambda_{0}".format(n)]
        t_bodies = sorted({k for c in self.sweep_cases()
                           for k in (c.get("temperature") or {})})
        cols += ["Tmax_{0}_k".format(b) for b in t_bodies]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(",".join(cols) + "\n")
            for c in self.sweep_cases():
                row = [c["freq_hz"], c["eddy_power_w"]]
                row += [c["body_power_w"].get(b, 0.0) for b in bodies]
                for n in coils:
                    lam = c["coil_lambda"].get(n, 0j)
                    row += [lam.real, lam.imag]
                row += [(c.get("temperature") or {}).get(b, {}).get("t_max", 0.0)
                        for b in t_bodies]
                fh.write(",".join("{0:.9g}".format(v) for v in row) + "\n")
        return path
