# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sweep results shared by every backend.

Whatever the solver (openEMS FDTD, NEC2 MoM, Elmer, Palace), results normalize to
the same container: frequency vector + complex input impedance + complex S11
against a reference impedance. Everything downstream (plots, Touchstone export,
resonance search, validation gates) works off this one type, so backends stay thin.

**Transmission terms** live in ``s_others``, keyed ``(to_port, from_port)`` — so
S21 is ``(2, 1)``. It was an undeclared attribute bolted on after construction by
the openEMS and Palace runners until v1.2.0, which meant every reader had to guess
whether it existed: ``results_dialog`` guarded with ``getattr``, ``cable_dialog``
did not, and a NEC2 or Elmer result reaching that path was an AttributeError
waiting to happen. It is a real field now, defaulting to ``{}``.

⚠ **What is in here is ONE COLUMN of the S-matrix, not the matrix.** Both
full-wave backends solve a single excitation by construction — openEMS refuses
anything else ("the analysis needs exactly one excited port") and Palace's driven
config marks port 1 excited and the rest passive. A port-1 excitation yields S11,
S21, S31 … and says nothing whatever about S12 or S22. Reciprocity does not close
that gap: it gives S12 = S21 for a passive structure but leaves S22 unknown. So a
full 2-port Touchstone needs a SECOND solve, and until one exists
``write_touchstone`` writes ``.s1p`` and refuses to invent the rest.

Qt-free and FreeCAD-free on purpose: usable from plain pytest and from solver decks.
"""

from __future__ import annotations

import numpy as np

#: Touchstone allows at most four network-parameter pairs on one line. It only
#: bites from 5 ports up, where a single matrix ROW no longer fits on a line
#: and has to be continued on the next — below that a row is always shorter
#: than the limit, so the wrap never fires and 1/2-port files are unaffected.
MAX_PAIRS_PER_LINE = 4

#: Continuation lines are indented to sit under the first pair rather than
#: under the frequency. The format is whitespace-insensitive, so this buys
#: nothing mechanically — it is for the human reading a .s5p, who otherwise
#: cannot see where one frequency entry ends and the next begins. 16 = the
#: width of a "%.9e" frequency plus its separating space.
_CONT_INDENT = " " * 16


class SweepResult:
    """One-port frequency sweep: Zin(f) and S11(f) vs a reference impedance."""

    def __init__(self, freq_hz, zin, z0=50.0, s11=None, meta=None,
                 s_others=None):
        self.freq = np.asarray(freq_hz, dtype=float)
        self.zin = np.asarray(zin, dtype=complex)
        self.z0 = float(z0)
        if s11 is None:
            s11 = (self.zin - self.z0) / (self.zin + self.z0)
        self.s11 = np.asarray(s11, dtype=complex)
        self.meta = dict(meta or {})  # backend name, solve time, etc.
        #: Transmission terms, ``(to_port, from_port) -> complex array``.
        #: Declared so every reader can rely on it existing; the runners that
        #: have such terms still assign it after construction, which is the
        #: same thing one line later.
        self.s_others = dict(s_others or {})
        # The optional extras the NEC2 and openEMS runners bolt on when their
        # run produced them. Declared for the same reason ``s_others`` is: an
        # attribute that exists only if a particular runner happened to run
        # makes every reader guess, and the day one forgets to guess is an
        # AttributeError on a result from a DIFFERENT backend. That is not
        # hypothetical — it is exactly how ``cable_dialog`` read ``s_others``
        # bare while ``results_dialog`` guarded it. Palace, Elmer and NEC2
        # driven results legitimately have none of these; ``None`` / ``[]``
        # says "this run produced none", which is a fact a reader can act on,
        # where a missing attribute is only a question.
        #: Best-match radiation pattern (``FarFieldResult``), or None.
        self.farfield = None
        #: One pattern per swept frequency; ``[]`` when the run made none.
        self.farfields = []
        #: Current distribution at the best-match frequency, or None.
        self.currents = None
        #: One current distribution per swept frequency.
        self.currents_all = []
        #: Near-field |E| map (openEMS ``NearFieldPlane``), or None.
        self.nearfield = None

    # -- derived quantities ---------------------------------------------------
    def s11_db(self):
        mag = np.abs(self.s11)
        mag = np.where(mag <= 0, 1e-30, mag)
        return 20.0 * np.log10(mag)

    def vswr(self):
        mag = np.clip(np.abs(self.s11), 0.0, 0.999999)
        return (1.0 + mag) / (1.0 - mag)

    def min_s11(self):
        """(frequency, S11_dB) at the best match point."""
        db = self.s11_db()
        i = int(np.argmin(db))
        return float(self.freq[i]), float(db[i])

    def resonances(self):
        """Frequencies where the reactance Im(Zin) crosses zero (interpolated).

        Two degenerate cases are answered honestly rather than literally:

        * A PURELY RESISTIVE load has Im(Z) == 0 at every sample. Counting each
          exact zero as a crossing would report one "resonance" per frequency
          point (400 of them on a 401-point sweep) — technically true and
          completely useless, because a flat load has no DISTINCT resonance.
          Such a sweep returns []. Callers that print the first few (the PDF
          summary table) would otherwise show confident nonsense.
        * A RUN of consecutive exact zeros is ONE crossing, not one per sample;
          it is reported at the midpoint of the run.

        The flat test is relative to the resistance, so a numerical residue of
        1e-12 ohm on a 70-ohm feed still counts as flat.
        """
        x = np.imag(self.zin)
        n = len(x)
        if n == 0:
            return []
        scale = float(np.max(np.abs(np.real(self.zin))))
        if float(np.max(np.abs(x))) <= 1e-9 * max(scale, 1.0):
            return []
        crossings = []
        i = 0
        while i < n - 1:
            if x[i] == 0.0:
                j = i
                while (j < n - 1) and (x[j + 1] == 0.0):
                    j += 1
                crossings.append(0.5 * (float(self.freq[i]) + float(self.freq[j])))
                i = j + 1
                continue
            if x[i] * x[i + 1] < 0.0:
                # linear interpolation between the two samples
                f = self.freq[i] + (self.freq[i + 1] - self.freq[i]) * (
                    -x[i] / (x[i + 1] - x[i])
                )
                crossings.append(float(f))
            i += 1
        return crossings

    def r_at(self, freq_hz):
        """Interpolated input resistance at a frequency."""
        return float(np.interp(freq_hz, self.freq, np.real(self.zin)))

    def x_at(self, freq_hz):
        """Interpolated input reactance at a frequency."""
        return float(np.interp(freq_hz, self.freq, np.imag(self.zin)))

    # -- persistence ------------------------------------------------------------
    CSV_HEADER = "freq_hz,re_zin,im_zin,re_s11,im_s11,z0"

    def save_csv(self, path):
        rows = np.column_stack(
            [
                self.freq,
                np.real(self.zin),
                np.imag(self.zin),
                np.real(self.s11),
                np.imag(self.s11),
                np.full_like(self.freq, self.z0),
            ]
        )
        np.savetxt(path, rows, delimiter=",", header=self.CSV_HEADER, comments="")

    @classmethod
    def load_csv(cls, path, meta=None):
        data = np.loadtxt(path, delimiter=",", skiprows=1)
        data = np.atleast_2d(data)
        freq = data[:, 0]
        zin = data[:, 1] + 1j * data[:, 2]
        s11 = data[:, 3] + 1j * data[:, 4]
        z0 = float(data[0, 5])
        return cls(freq, zin, z0=z0, s11=s11, meta=meta)

    # -- Touchstone -----------------------------------------------------------
    def s_matrix_ports(self):
        """Highest port index this result mentions. 1 when nothing else is set."""
        n = 1
        for (to_p, from_p) in self.s_others:
            n = max(n, int(to_p), int(from_p))
        return n

    def s_at(self, to_port, from_port):
        """One S-term, or None when this solve did not produce it.

        ``S11`` comes from the dedicated field; everything else from
        ``s_others``. Nothing is inferred — see ``missing_s_terms``.
        """
        if (to_port, from_port) == (1, 1):
            return self.s11
        return self.s_others.get((to_port, from_port))

    def max_complete_ports(self):
        """Largest N for which the full N-port matrix is present.

        This — not :meth:`s_matrix_ports` — is what an unqualified export
        should use. A one-excitation 2-port solve MENTIONS port 2 (it has S21)
        while only COMPLETING order 1, and an export that read the mentioned
        count would refuse to write the 1-port file it has always written.
        """
        n = 1
        while not self.missing_s_terms(n + 1):
            n += 1
            if n > 64:                        # nothing real, and not a loop
                break
        return n

    def missing_s_terms(self, n_ports=None):
        """Which terms of the full n-port matrix this solve does NOT have.

        Returns a sorted list of ``(to, from)``. Empty means the matrix is
        complete and a Touchstone of that order can be written honestly.
        """
        n = int(n_ports or self.s_matrix_ports())
        return sorted((i, j) for i in range(1, n + 1) for j in range(1, n + 1)
                      if self.s_at(i, j) is None)

    def write_touchstone(self, path, n_ports=None):
        """Write a Touchstone file, RI format, Hz. Order follows the data.

        Writes ``.sNp`` for whatever order the solve actually COMPLETED: 1-port
        from S11 alone, 2-port only when all four of S11/S21/S12/S22 are
        present, and so on.

        ⚠ **It refuses rather than fills gaps.** Asking for an order this solve
        cannot support raises ``ValueError`` naming the missing terms, because
        the alternative — writing zeros, or mirroring S21 into S12 and guessing
        S22 — produces a file a VNA comparison would treat as measured data.
        A single excitation gives one COLUMN of the matrix; the rest needs a
        second solve, not a convention.

        ⚠ 2-port Touchstone column order is ``S11 S21 S12 S22`` — S21 before
        S12, unlike every other order, which is a genuine quirk of the format
        and the classic way to write a transposed file nobody notices.

        ⚠ **LINE LAYOUT IS PART OF THE FORMAT, not cosmetics.** 1-port and
        2-port put a whole frequency entry on ONE line; from 3 ports up the
        spec puts **one matrix ROW per line**, and from 5 ports up it wraps
        each row at :data:`MAX_PAIRS_PER_LINE` pairs. A reader recovers the
        order from the file extension and then counts values per line, so a
        ``.s3p`` written as one long line is not a formatting preference —
        it is a file other tools reject or, worse, misparse. This wrote one
        long line for every order until v1.2.0; nothing consumed an ``.s3p``
        yet, which is exactly why no gate caught it.
        """
        n = int(n_ports or self.max_complete_ports())
        if n < 1:
            raise ValueError("n_ports must be >= 1")
        missing = self.missing_s_terms(n)
        if missing:
            raise ValueError(
                "cannot write a {0}-port Touchstone: this solve has no {1}. "
                "Both full-wave backends excite ONE port per run, which gives "
                "one column of the S-matrix — a full {0}-port file needs an "
                "excitation per port. Export the 1-port file, or run the "
                "remaining excitation(s) first.".format(
                    n, ", ".join("S%d%d" % t for t in missing)))

        if n == 2:
            order = [(1, 1), (2, 1), (1, 2), (2, 2)]     # the format's quirk
        else:
            order = [(i, j) for i in range(1, n + 1) for j in range(1, n + 1)]
        cols = [self.s_at(i, j) for (i, j) in order]

        def pair(col, k):
            v = complex(col[k])
            return "{0:.9e} {1:.9e}".format(v.real, v.imag)

        with open(path, "w", encoding="utf-8") as fh:
            fh.write("! EMStudio {0}-port sweep ({1})\n".format(
                n, self.meta.get("backend", "?")))
            if n == 2:
                fh.write("! Column order is S11 S21 S12 S22 "
                         "(Touchstone 2-port convention).\n")
            elif n > 2:
                fh.write("! One matrix ROW per line, row-major "
                         "(S11 S12 S13 ... / S21 S22 S23 ...), wrapped at "
                         "{0} pairs per line.\n".format(MAX_PAIRS_PER_LINE))
            fh.write("# Hz S RI R {0:g}\n".format(self.z0))
            for k, f in enumerate(self.freq):
                if n <= 2:
                    # 1- and 2-port entries are a single line, by the spec.
                    fh.write("{0:.9e} {1}\n".format(
                        float(f), " ".join(pair(c, k) for c in cols)))
                    continue
                # n > 2: one ROW per line. `cols` is row-major here, so row i
                # is the slice [i*n : (i+1)*n] — the frequency is written once,
                # on the first line of the entry, and every later line of the
                # same entry is a continuation.
                first = True
                for i in range(n):
                    row = [pair(cols[i * n + j], k) for j in range(n)]
                    for c0 in range(0, n, MAX_PAIRS_PER_LINE):
                        chunk = " ".join(row[c0:c0 + MAX_PAIRS_PER_LINE])
                        if first:
                            fh.write("{0:.9e} {1}\n".format(float(f), chunk))
                            first = False
                        else:
                            fh.write("{0}{1}\n".format(_CONT_INDENT, chunk))
        return n

def merge_excitations(runs, rtol=1.0e-9):
    """Join per-excitation solves into one S-matrix.

    A driven solve excites ONE port and measures the rest, which yields the
    single COLUMN of the S-matrix belonging to that port. A full N-port matrix
    is therefore N solves, and this is the join.

    ``runs`` is a sequence of ``(freq_hz, {(observed, excited): array})`` — one
    entry per solve, in any order. Returns ``(freq_hz, {(o, x): array})``.

    ⚠ **It refuses on a frequency mismatch rather than interpolating.** Two
    sweeps that do not share a grid are two different experiments; silently
    resampling one onto the other would produce a .s2p that looks measured and
    is not, which is the failure this whole path exists to avoid. Re-run with
    matching sweep settings instead.

    ⚠ It also refuses when two runs both claim the same ``(o, x)`` term with
    different values — that means the excitations were not distinct, which is
    a configuration bug worth stopping on rather than silently taking one.
    """
    runs = [r for r in runs if r is not None]
    if not runs:
        raise ValueError("merge_excitations: nothing to merge")

    freq0 = np.asarray(runs[0][0], dtype=float)
    merged = {}
    for k, (freq, terms) in enumerate(runs):
        f = np.asarray(freq, dtype=float)
        if f.shape != freq0.shape or not np.allclose(f, freq0, rtol=rtol):
            raise ValueError(
                "merge_excitations: run %d sweeps %d point(s) that do not match "
                "run 0's %d — the excitations must share one frequency grid. "
                "Re-run them with identical sweep settings; resampling here "
                "would fabricate data."
                % (k, f.size, freq0.size))
        for key, arr in (terms or {}).items():
            a = np.asarray(arr, dtype=complex)
            if key in merged and not np.allclose(merged[key], a, rtol=1e-6,
                                                 atol=1e-12):
                raise ValueError(
                    "merge_excitations: two runs disagree on S%d%d — the "
                    "excitations were not distinct (check that each solve "
                    "drove a different port)." % key)
            merged[key] = a
    return freq0, merged
