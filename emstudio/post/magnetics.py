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
* coil impedance from linkage: Z = j*omega*lambda / I, where I is the coil's
  COMPLEX drive phasor (``current_a`` signed by ``reversed`` and rotated by
  ``phase_deg`` — the sif writer bakes both into the source current density),
  so L_eff = Re(lambda/I) and R_reflected = -omega*Im(lambda/I) (the series
  resistance the eddy losses present to the source; equals 2P/I^2 for a coil
  driven alone).
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

    def _drive_phasor(self, name, magnitude=None):
        """The coil's COMPLEX drive current: +/-I * exp(j*phase_deg).

        ``current_a`` is a MAGNITUDE, but the sif writer drives the coil with
        the sign of ``reversed`` and the rotation of ``phase_deg`` baked into
        the source current density (``writer.coil_current_density``), so the
        flux linkage Elmer hands back is proportional to THIS phasor, not to
        the magnitude. Z = j*omega*lambda/I is the coil impedance only when I
        is the same phasor that produced lambda: dividing by |I| instead made
        a Reversed coil report a NEGATIVE L_eff and R_reflected (and
        ``coupling_k`` then dropped the pair in silence at its l > 0 test),
        and turned a phased multi-coil drive into L and R rotated into each
        other — at 90 deg, R_reflected came out as -omega*L_eff. Found
        2026-08-29; no gate had ever run the Elmer path with the Coil's
        Reversed or PhaseDeg set, and the solver's own AnalysisType tooltip
        tells users to toggle Reversed.

        ``magnitude`` overrides ``current_a`` — the coupling cases drive an
        absolute REFERENCE current, and the writer applies the coil's sign
        and phase to that override too (``current_override``).
        """
        coil = self._coil(name)
        amps = float(coil["current_a"] if magnitude is None else magnitude)
        if coil.get("reversed"):
            amps = -amps
        phase = math.radians(float(coil.get("phase_deg", 0.0) or 0.0))
        return complex(amps * math.cos(phase), amps * math.sin(phase))

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
        current = self._drive_phasor(coil_name)
        for c in self.sweep_cases():
            lam = c["coil_lambda"][coil_name]
            w = 2.0 * math.pi * c["freq_hz"]
            freqs.append(c["freq_hz"])
            if current == 0:
                ls.append(float("nan"))
                rs.append(float("nan"))
            else:
                # Z/(j*omega) = lambda/I: its real part is the effective
                # inductance and its imaginary part carries the loss term.
                # Complex division, NOT lam.real/|I| — see _drive_phasor.
                z_over_jw = lam / current
                ls.append(z_over_jw.real)
                rs.append(-w * z_over_jw.imag)
        return freqs, ls, rs

    def inductance_matrix(self):
        """{(exciter, sensed): L in henries} from the coupling cases.

        Normalized by the coupling REFERENCE current the case actually used
        (``ref_current_a``; falls back to the operating current for older
        results), as the PHASOR the writer drove — the exciter's Reversed and
        PhaseDeg apply to the reference current too, so a magnitude-only
        divide handed back a negative self-inductance. See ``_drive_phasor``.
        """
        out = {}
        for c in self.coupling_cases():
            exciter = c["tag"][len("couple_"):]
            # `or None` keeps the old fallback: a missing/zero ref_current_a
            # means "older result — use the operating current".
            i_exc = self._drive_phasor(exciter, c.get("ref_current_a") or None)
            if not i_exc:
                continue  # no reference current — cannot normalize
            for name, lam in c["coil_lambda"].items():
                out[(exciter, name)] = (lam / i_exc).real
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
            add("B-field map: use 'Show Fields in 3D'.")
            case0 = (self.sweep_cases() or [{}])[0]
            L = case0.get("inductance_h")
            if L is not None:
                add("")
                add("  stored magnetic energy   {0:.6g} J".format(
                    case0.get("energy_j", 0.0)))
                add("  inductance (1-turn equiv) {0:.6g} H".format(L))
                add("  an N-turn winding driven as N*I ampere-turns has "
                    "L = {0:.6g} x N^2 H".format(L))
            # ⚠ Print the delivered ampere-turns ALONE — never as a fraction
            # of the coil's ``amp_turns``. The two are not in the same units
            # on both branches: ``delivered_amp_turns`` always counts every
            # turn, but the REQUEST means ampere-turns on a CLOSED coil and
            # the CONDUCTOR current on an OPEN one (Elmer normalizes one
            # conductor cross-section there). Dividing them multiplies the
            # open branch's ratio by the solid's geometric turns, which is
            # exactly what run3d's guard comment says must not happen: it
            # printed a CORRECT 6.44-turn helix as "643.588 of 100
            # ampere-turns (643.6%)" and sent the user to fix geometry that
            # was already right. Nothing here can tell the branches apart —
            # ``bodies`` carries neither ``closed`` nor ``turns_geometric``.
            # The delivery CHECK belongs where the branch IS known: run3d
            # compares conductor current against conductor current and warns
            # outside 0.5..2.0, and those warnings are printed just below.
            # (2026-08-29)
            got = case0.get("delivered_amp_turns") or []
            for b, d in zip(self.bodies, got):
                if d is not None and b.get("is_coil"):
                    add("  coil '{0}': delivered {1:.6g} ampere-turns".format(
                        b["name"], d))
            # The run's own notes and warnings. This dialog shows nothing but
            # summary_text(), so without this the delivery guard, the
            # double-count note and the terminal-face note reached NOBODY —
            # which is why the fabricated percentage above was the only
            # delivery signal a user ever saw.
            for w in case0.get("solver_warnings") or []:
                add("")
                add("  ⚠ {0}".format(w))
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
