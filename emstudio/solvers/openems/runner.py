# SPDX-License-Identifier: LGPL-2.1-or-later
"""openEMS backend orchestration: Prepare -> Solve -> Results.

The deck runs under the openEMS *venv* Python (never FreeCAD's interpreter), which
decouples EMStudio from FreeCAD's bundled-Python version differences (0.21 = 3.12
system, 1.1 AppImage = 3.11).
"""

from __future__ import annotations

import os
import re

from emstudio.post.sparams import (NonFiniteResultError, SweepResult,
                                   require_finite)
from emstudio.setup import solvers as solver_setup
from emstudio.solvers import progress
from emstudio.solvers.base import (GRID_PREFIX, SolverError, SolverJob,
                                   foreign_python_env, make_workdir)

from . import writer


#: What openEMS writes (to stderr, openems.cpp RunFDTD) when it stops at NrTS
#: with the field energy still above EndCriteria. Matched on this stable
#: middle of the sentence: the dB figure and the "Warning:" prefix around it
#: are formatted at run time.
_NRTS_HIT = "Max. number of timesteps was reached before the end-criteria"

#: The deck's own banner, which states the timestep cap it was written with.
_NRTS_RE = re.compile(r"EMStudio: starting openEMS run \(NrTS=(\d+), "
                      r"EndCriteria=([0-9.eE+-]+)\)")

#: openEMS's periodic progress line ends "|| Energy: ~7.62e-16 (-30.23dB)" —
#: the decay since the peak, MEASURED. ``setw(5)`` can pad the figure, so
#: whitespace is allowed inside the brackets.
_ENERGY_RE = re.compile(r"Energy:\s*~\s*\S+\s*\(-\s*([0-9.]+)\s*dB\)")

#: openEMS's SetupFDTD states the cap against the excitation pulse's own
#: length: "Max. number of timesteps: 1000 ( --> 0.364829 * Excitation signal
#: length)". Below 3 it warns itself; below 1 the pulse is not even finished.
_EXC_RATIO_RE = re.compile(r"Max\. number of timesteps:\s*\d+\s*\(\s*-->\s*"
                           r"([0-9.eE+-]+)\s*\*\s*Excitation signal length")

#: openEMS's own minimum, from the same SetupFDTD warning ("smaller than three
#: times the excitation"). Below it truncation is CERTAIN, measured or not.
_MIN_EXC_RATIO = 3.0

#: ...and when NrTS is shorter than the pulse itself openEMS CUTS the pulse
#: and then reports the ratio as 1 (measured on the patch at NrTS 1000:
#: "Requested excitation pusle would be 2741 timesteps ... Cutting to max
#: number of timesteps!" — "pusle" is openEMS's own spelling, matched loosely).
_PULSE_CUT_RE = re.compile(r"excitation pu\w*e would be (\d+) timesteps.*Cutting")

#: ⚠⚠ openEMS's words when it could not place a lumped element. They are a
#: WARNING to openEMS: it SKIPS the element (operator.cpp Calc_LumpedElements;
#: the RLC extension prints the same for series RLC), carries on, exits 0, and
#: the deck then prints "openEMS deck finished OK" over a port that was never
#: in the simulation. Measured on the forum J-pole (v0.37.0-rc1): "Operator::
#: Calc_LumpedElements(): Warning: Lumped Element snapping failed! Dimension
#: is: 0 skipping.  ID: 6 @ Property: port_resist_1", and an all-NaN
#: port_1.csv that loaded as a result. The property is named by openEMS's
#: python ports ('port_resist_<n>'), so the PORT NUMBER is in the line.
_LUMPED_FAULT_RE = re.compile(
    r"Lumped (?:Element|RLC) (?:snapping failed|with zero \(snapped\) length)"
    r".*@ Property: port_[A-Za-z]+_(\d+)")

#: ...and the summary CSXCAD prints after setup (WarnUnusedPrimitves) for
#: every primitive no part of the operator took: for a port that is its
#: excitation ('port_excite_<n>' — no source at all), its resistor
#: ('port_resist_<n>' — an unterminated port 2 makes S21 meaningless) or a
#: probe ('port_ut_<n>', MSL's 'port_ut_<n>A' — nothing measured). It is also
#: the ONLY report for a port outside the domain: openEMS prints no snapping
#: line for that case ("Snap_Dimension == -2 ... probably marked as unused").
#: ⚠ Only ``port_`` properties: an unused metal or field dump is not a port.
_UNUSED_PORT_RE = re.compile(
    r"Unused primitive \(type: \w+\) detected in property: "
    r"port_[A-Za-z]+_(\d+)[A-Za-z]*!")

#: The openEMS python binding's own words when SetupFDTD fails — after which
#: it RETURNS (openEMS.pyx Run) and the deck carries on into post-processing
#: on a run that never happened.
_SETUP_FAILED = "Run: Setup failed, error code"

#: The line openEMS prints once setup is complete and timestepping begins
#: (openems.cpp RunFDTD). Port faults are all printed BEFORE it, so this is
#: where a faulted run is stopped: every fault has been heard, and not one
#: timestep has been spent on a model without its port.
_ENGINE_START = "Running FDTD engine"


class _DeckWatch(object):
    """Pass every line through to ``downstream`` and remember what it said.

    The runner needs facts it can only learn from the stream: the grid line
    the deck's preflight printed, and whether openEMS stopped at its timestep
    CAP instead of at the energy criterion. ⚠ That second one is not an error
    and openEMS still exits 0 — which is exactly why it has to be caught here:
    the run "finishes OK" and the S-parameters may come from a time signal cut
    off while the structure was still ringing.

    ⚠⚠ openEMS's own "Max. number of timesteps was reached" warning is NOT
    proof of truncation. RunFDTD starts with ``change = 1`` and re-measures
    the energy only inside its every-4-seconds progress block (openems.cpp),
    so a run shorter than ~4 s of wall time never measures it at all and
    prints the warning whatever the fields did. Hence the evidence ladder in
    :meth:`warning`: a WARNING when openEMS MEASURED a shortfall, or when the
    cap is under 3x the excitation pulse (truncation certain without any
    measurement — openEMS's own minimum); a NOTE when nothing was measured —
    never a claim the log cannot back.

    ⚠⚠ Since v1.14.0 it also hears openEMS DROP a port: a lumped element it
    could not snap to the grid, any port primitive left unused (the only sign
    of a port outside the domain), or a failed setup. Those are not notes but
    FAILURES (:meth:`fault_error`), and the run is aborted the moment
    timestepping starts, because openEMS itself only warns, exits 0, and
    leaves an all-NaN port file behind.
    """

    def __init__(self, downstream):
        self._down = downstream
        self.grid_line = None
        self.nrts = None
        self.end_criteria = None
        self.nrts_hit = False
        #: Last MEASURED energy decay in dB below the peak (positive), or None.
        self.last_decay_db = None
        #: NrTS as a multiple of the excitation pulse length, or None.
        self.exc_ratio = None
        #: Timesteps the pulse needed when openEMS had to CUT it, or None.
        self.pulse_needed = None
        #: ``(port_nr or None, openEMS line)`` for every fault that means a
        #: port is not in the simulation (or the setup itself failed).
        self.port_faults = []
        #: The SolverJob this watch serves, once the caller attaches it: a
        #: faulted run is ABORTED at the start of timestepping (see
        #: _ENGINE_START) instead of running to NrTS on a portless model.
        self.job = None
        self.stopped_for_fault = False

    def __call__(self, line):
        if line.startswith(GRID_PREFIX):
            self.grid_line = line
        elif _NRTS_HIT in line:
            self.nrts_hit = True
        elif _ENGINE_START in line:
            if self.port_faults and self.job is not None:
                # ⛳ Fail FAST. The forum J-pole at MeshResolution 60 would
                # otherwise have spent its full 30000 timesteps (and a
                # far-field transform) computing a model with no source.
                self.stopped_for_fault = True
                self.job.abort()
        elif _SETUP_FAILED in line:
            self.port_faults.append((None, line.strip()))
        elif "Lumped" in line or "Unused primitive" in line:
            m = _LUMPED_FAULT_RE.search(line) or _UNUSED_PORT_RE.search(line)
            if m:
                self.port_faults.append((int(m.group(1)), line.strip()))
        else:
            for rx, attr in ((_ENERGY_RE, "last_decay_db"),
                             (_EXC_RATIO_RE, "exc_ratio"),
                             (_PULSE_CUT_RE, "pulse_needed")):
                m = rx.search(line)
                if m:
                    try:
                        setattr(self, attr, float(m.group(1)))
                    except ValueError:
                        pass
                    break
            else:
                m = _NRTS_RE.search(line)
                if m:
                    self.nrts = int(m.group(1))
                    self.end_criteria = float(m.group(2))
        if self._down is not None:
            self._down(line)

    def fault_error(self, label=""):
        """A :class:`SolverError` naming the dropped port(s), or None.

        The headline says WHICH port and what that does to the result; the
        openEMS lines follow verbatim (at most six — every one names its
        property, so more add nothing), then what to look at in the model.
        """
        if not self.port_faults:
            return None
        nrs = sorted({nr for nr, _ in self.port_faults if nr is not None})
        if nrs:
            head = (
                "openEMS could not place port{s} {ports}{lbl} on the FDTD grid "
                "and left {it} out of the simulation, so the run has no valid "
                "S-parameters (openEMS itself only warns and carries on to an "
                "all-NaN or meaningless result).".format(
                    s="s" if len(nrs) > 1 else "",
                    ports=", ".join(str(n) for n in nrs), lbl=label,
                    it="them" if len(nrs) > 1 else "it"))
            hint = (
                "Check that each port's edge runs across the feed gap from one "
                "conductor to the other, with both ends ON metal, along the "
                "port's Direction, and inside the simulation domain.")
        else:
            head = "openEMS setup failed{0}; the run did not happen.".format(label)
            hint = "See the openEMS output above for the reason."
        quoted = [ln for _, ln in self.port_faults][:6]
        return SolverError("{0}\nopenEMS said:\n  {1}\n{2}".format(
            head, "\n  ".join(quoted), hint))

    def _crit_db(self, solver):
        import math
        if self.end_criteria and self.end_criteria > 0:
            return 10.0 * math.log10(self.end_criteria)
        return float(getattr(solver, "EndCriteriaDB", -40.0))

    def warning(self, solver, label=""):
        """``("warning" | "note", text)`` for a run that hit NrTS, or None."""
        if not self.nrts_hit:
            return None
        n = self.nrts if self.nrts else "?"
        crit = self._crit_db(solver)
        if self.last_decay_db is not None:
            return "warning", (
                "EMStudio: WARNING - openEMS stopped at its timestep limit{lbl} "
                "(NrTS = {n}, from MaxTimesteps) with the field energy last "
                "measured at -{dec:.1f} dB, short of EndCriteriaDB ({crit:.0f} "
                "dB). The S-parameters come from a truncated time signal and "
                "can be wrong, most of all near a sharp resonance. Raise "
                "MaxTimesteps and re-run.".format(
                    lbl=label, n=n, dec=self.last_decay_db, crit=crit))
        if self.pulse_needed:
            return "warning", (
                "EMStudio: WARNING - openEMS had to CUT its excitation pulse"
                "{lbl}: the pulse alone needs {p:.0f} timesteps and "
                "MaxTimesteps allows {n}. The S-parameters come from a "
                "truncated time signal and are not to be trusted. Raise "
                "MaxTimesteps (openEMS asks for at least {mn:g} x the pulse) "
                "and re-run.".format(lbl=label, p=self.pulse_needed, n=n,
                                     mn=_MIN_EXC_RATIO))
        if self.exc_ratio is not None and self.exc_ratio < _MIN_EXC_RATIO:
            return "warning", (
                "EMStudio: WARNING - openEMS stopped at its timestep limit{lbl} "
                "(NrTS = {n}, from MaxTimesteps), only {r:.2g} x the length of "
                "its own excitation pulse - openEMS asks for at least {mn:g} x. "
                "The S-parameters come from a truncated time signal and are "
                "not to be trusted. Raise MaxTimesteps and re-run.".format(
                    lbl=label, n=n, r=self.exc_ratio, mn=_MIN_EXC_RATIO))
        return "note", (
            "EMStudio: NOTE - openEMS ran all {n} timesteps{lbl} (MaxTimesteps) "
            "without measuring the field energy: it measures only every ~4 s "
            "of run time and this run was shorter, so the EndCriteriaDB "
            "({crit:.0f} dB) decay was not confirmed. If S11 looks rippled or "
            "noisy, raise MaxTimesteps and re-run.".format(
                lbl=label, n=n, crit=crit))


#: Re-exported for every existing caller. The implementation LIVES in
#: ``emstudio.setup.solvers`` because that module is FreeCAD-free, and this one
#: is not: importing it drags in ``writer`` -> ``objects.analysis`` ->
#: ``import FreeCAD``. A gate that only wants to ask "is openEMS available?"
#: must be able to do so without FreeCAD, or it cannot skip cleanly — which is
#: exactly why four openEMS gates were failing instead of skipping.
find_openems_python = solver_setup.find_openems_python


def _run_watched(job, watch, label=""):
    """``job.run_blocking`` — and a dropped port reported as exactly that.

    The watch is attached first, so a port fault STOPS the run as soon as
    openEMS starts timestepping (``_DeckWatch``); the abort then surfaces here
    as "solver run aborted", and the port error replaces it. A fault in a run
    that finished anyway (exit 0, which is what openEMS does) is raised too:
    exit status says nothing about whether the port was in the model.
    """
    watch.job = job
    try:
        job.run_blocking(timeout=4 * 3600)
    except SolverError as exc:
        err = watch.fault_error(label)
        if err is not None:
            raise err from exc
        raise
    err = watch.fault_error(label)
    if err is not None:
        raise err


def _below_cutoff(path, analysis):
    """``(port_nr, mode, cut-off Hz)`` when EVERY non-finite row of a result
    CSV lies at or below a waveguide port's cut-off, else None.

    ⚠⚠ Below its mode's cut-off openEMS's waveguide port returns NaN BY
    DESIGN (beta = sqrt(k^2 - kc^2) on a real array, see
    writer._waveguide_band), and the writer leaves those samples out of the
    deck's grid. This is the backstop for a deck that kept them anyway (one
    edited or re-run by hand, an older EMStudio's, a margin case): such a
    NaN must never be reported as "the port was never in the simulation" —
    the v1.14.0 review caught exactly that message on a WR-28 run whose
    port was fine and whose 18 samples above 21.08 GHz were all finite.
    None (never an exception) when the file cannot be re-read or the
    analysis has no waveguide port: the caller then keeps its own message.
    """
    import numpy as np

    if analysis is None:
        return None
    cuts = writer.waveguide_cutoffs(analysis)
    if not cuts:
        return None
    try:
        data = np.atleast_2d(np.loadtxt(path, delimiter=",", skiprows=1))
    except Exception:                                      # noqa: BLE001
        return None
    bad = ~np.all(np.isfinite(data), axis=1)
    if not bad.any() or not np.all(np.isfinite(data[:, 0])):
        return None
    worst = max(cuts, key=lambda c: c[2])
    # 1e-6 (21 kHz at WR-28's cut-off): far wider than the writer's own
    # 1e-9 margin, far narrower than a real sweep's step — so a NaN even one
    # sample above cut-off is NOT this case and keeps the dropped-port error.
    if float(np.max(data[bad, 0])) <= worst[2] * (1.0 + 1e-6):
        return worst
    return None


def _cutoff_error(what, exc, cut):
    """The SolverError for NaN samples that lie below a waveguide cut-off."""
    nr, mode, fc = cut
    return SolverError(
        "openEMS finished, but {0} has no number below {1:.4g} GHz ({2}). "
        "That is the {3} cut-off of waveguide port {4}: below it the mode "
        "does not propagate and openEMS's waveguide port returns NaN by "
        "design — the port itself is fine. Start the band above {1:.4g} GHz "
        "(EMStudio's own decks leave those samples out; this one kept them)."
        .format(what, fc / 1e9, exc, mode, nr))


def _load_port_csv(path, port_nr, label="", analysis=None):
    """``SweepResult.load_csv`` with a NaN result named for the user.

    ⚠ Until v1.14.0 an all-NaN ``port_<n>.csv`` LOADED: numpy parses 'nan'
    happily, and the run read "openEMS deck finished OK" (forum J-pole,
    2026-10-17). load_csv now refuses it; this says which port and why that
    usually happens — and, given the ``analysis``, tells a NaN below a
    waveguide port's cut-off apart from a port that was never there
    (:func:`_below_cutoff`).
    """
    try:
        return SweepResult.load_csv(path, meta={"backend": "openEMS"})
    except NonFiniteResultError as exc:
        cut = _below_cutoff(path, analysis)
        if cut is not None:
            raise _cutoff_error("the result for port {0}{1}".format(
                port_nr, label), exc, cut) from exc
        raise SolverError(
            "openEMS finished, but the result for port {0}{1} is not a "
            "number ({2}). That is what openEMS returns when the port was "
            "never in the simulation (its ends did not reach the grid, or it "
            "lies outside the domain) or carried no signal at all — the "
            "numbers cannot be used.".format(port_nr, label, exc)) from exc


def _load_s_column(path, label="", analysis=None):
    """One ``sparam_<to>_<from>.csv`` transmission column, refused if NaN
    (with the waveguide cut-off told apart, as in :func:`_load_port_csv`)."""
    import numpy as np

    data = np.atleast_2d(np.loadtxt(path, delimiter=",", skiprows=1))
    try:
        require_finite(path, freq=data[:, 0],
                       s=data[:, 1] + 1j * data[:, 2])
    except NonFiniteResultError as exc:
        cut = _below_cutoff(path, analysis)
        if cut is not None:
            raise _cutoff_error("a transmission term{0}".format(label), exc,
                                cut) from exc
        raise SolverError(
            "openEMS finished, but a transmission term{0} is not a number "
            "({1}) — a port of this run was not in the simulation."
            .format(label, exc)) from exc
    return data[:, 1] + 1j * data[:, 2]


def _copy_model_notes(result, deck):
    """The deck's model notes into ``result.meta["warnings"]`` / ``["notes"]``.

    What write_deck said about the MODEL — a reference that reached nothing,
    an STL openEMS will partly refuse, two materials tied on Priority, a
    part refinement had to leave coarse, a port touching no metal, sweep
    samples below a waveguide cut-off — went to the Report view at write
    time and into the deck's own output, where it scrolls away under the
    solver log. The results dialog shows these two lists beside the plots
    (results_dialog._add_run_notes), so the warning sits next to the number
    it qualifies. Read from the DECK (writer.deck_model_notes), the record
    each excitation of a FullSMatrix run carries too; an exact repeat — every
    excitation deck carries the same notes — is not added twice. Same keys,
    same tagged strings, as the timestep notes (:func:`_note_capped`), and
    after them. Not echoed through the line callback: the deck prints its
    notes when it runs, so the log already has them once.
    """
    for kind, text in writer.deck_model_notes(deck):
        items = result.meta.setdefault(
            "warnings" if kind == "warning" else "notes", [])
        if text not in items:
            items.append(text)


def _note_capped(result, watch, solver, line_callback, label):
    """Record and SAY that a run stopped at NrTS rather than at EndCriteria.

    A measured truncation goes into ``result.meta["warnings"]``, an
    unmeasured one into ``result.meta["notes"]`` (lists, so a FullSMatrix run
    can carry one per excitation), and either goes out through the line
    callback, which is the Report view in the GUI. Nothing changes about the
    result itself: the numbers are what openEMS produced; this is what they
    are worth.
    """
    found = watch.warning(solver, label)
    if not found:
        return
    kind, msg = found
    result.meta.setdefault("warnings" if kind == "warning" else "notes",
                           []).append(msg)
    if line_callback is not None:
        try:
            line_callback(msg)
        except Exception:                                  # noqa: BLE001
            pass                        # a broken log sink must not fail a solve


def _analysis_port_numbers(analysis):
    """The port numbers this analysis carries, ascending.

    ⚠ These are the document's own ``PortNumber`` values, NOT ``1..N``. A user
    who deletes a port leaves 1 and 3 behind, and a loop over ``range(1, n+1)``
    would then ask the writer for a port 2 that does not exist and re-run port 1
    under the wrong label. Drive the numbers that are actually there.
    """
    from emstudio.objects import query

    return [int(p.PortNumber) for p in query.get_ports(analysis)]


def _add_excitations(analysis, solver, workdir, python, result, line_callback,
                     port_numbers):
    """Drive each remaining port in its own subdirectory and merge its column in.

    Kept as an EXTENSION of the single-excitation path rather than a rewrite of
    it: run 1 still writes exactly what it always did, in exactly the same
    place, so nothing about the default behaviour moves. Each later run lives in
    ``excN/`` because every run writes ``port_<n>.csv`` and a shared directory
    would have them treading on each other.

    From the run driving port k the NEW terms are Skk (that port's own
    reflection, in ``port_k.csv``) and the ``sparam_<to>_k.csv`` column. Terms
    an earlier run already produced are deliberately not re-read.

    ``port_numbers`` is every port EXCEPT the one run 1 drove — the caller owns
    that decision, because run 1's driven port comes from the document's own
    ``Excited`` flag and is not necessarily port 1.
    """
    import glob

    import numpy as np

    if not port_numbers:
        return
    for i, nr in enumerate(port_numbers):
        sub = os.path.join(workdir, "exc{0}".format(int(nr)))
        os.makedirs(sub, exist_ok=True)
        deck, _z0, driven = writer.write_deck(analysis, solver, sub,
                                              excite_port=int(nr))

        # The extra excitations share the last 8 % of the bar between them, so
        # a 4-port run does not reset the bar three times.
        frac = 0.92 + 0.08 * (i / float(len(port_numbers)))
        progress.report(line_callback, frac,
                        "Excitation {0} of {1} (port {2})".format(
                            i + 2, len(port_numbers) + 1, driven))
        watch = _DeckWatch(line_callback)
        job = SolverJob([python, deck], cwd=sub, line_callback=watch,
                        env_filter=foreign_python_env)
        label = " (excitation of port {0})".format(driven)
        _run_watched(job, watch, label)
        _note_capped(result, watch, solver, line_callback,
                     " on the excitation of port {0}".format(driven))

        own = os.path.join(sub, "port_{0}.csv".format(driven))
        if not os.path.isfile(own):
            raise SolverError(
                "openEMS excitation of port {0} produced no results file: {1}"
                .format(driven, own))
        rk = _load_port_csv(own, driven, label, analysis=analysis)
        _copy_model_notes(result, deck)
        if len(rk.freq) != len(result.freq) or not np.allclose(
                rk.freq, result.freq, rtol=1e-9):
            raise SolverError(
                "openEMS: excitation of port {0} swept different frequencies "
                "({1} vs {2} points) — every excitation must share one grid, "
                "and resampling here would fabricate the S-matrix."
                .format(driven, len(rk.freq), len(result.freq)))

        result.s_others[(driven, driven)] = np.asarray(rk.s11, dtype=complex)
        for path in sorted(glob.glob(os.path.join(sub, "sparam_*_*.csv"))):
            base = os.path.basename(path)[len("sparam_"):-len(".csv")]
            try:
                to_port, from_port = (int(t) for t in base.split("_"))
            except ValueError:
                continue
            result.s_others[(to_port, from_port)] = _load_s_column(
                path, " S{0}{1}{2}".format(to_port, from_port, label),
                analysis=analysis)
        result.meta["duration_s"] = (
            result.meta.get("duration_s", 0.0) + job.duration_s)
    result.meta["excitations"] = 1 + len(port_numbers)


def run(analysis, solver, workdir=None, line_callback=None, full_smatrix=False):
    """Run the full openEMS pipeline for an analysis. Returns a SweepResult.

    ``full_smatrix`` adds one FDTD run per remaining port, so the result carries
    the complete NxN S-matrix instead of the single column one excitation
    gives. openEMS solves one excitation per run by construction, so this is
    genuinely N simulations and roughly N times the time — required for a
    .sNp, because no assumption recovers Skk from a port-1 solve.
    """
    python = find_openems_python()
    if not python:
        info = solver_setup.find_backend("openems")
        raise SolverError(
            "openEMS python environment not found.\n"
            + solver_setup.install_hint(info.backend)
            + "\n(or set EMSTUDIO_OPENEMS_PYTHON to a python with the openEMS module)"
        )

    workdir = make_workdir("emstudio_openems_", base=workdir)
    deck, z0, port_nr = writer.write_deck(analysis, solver, workdir)

    # A determinate bar from openEMS's own timestep counter. The TOTAL is
    # learned from a line the GENERATED DECK prints ("EMStudio: starting
    # openEMS run (NrTS=..., ...)"), so the runner never duplicates the
    # writer's `max(1000, int(solver.MaxTimesteps))` and the two cannot drift.
    #
    # VERIFIED AGAINST A LIVE RUN 2026-08-24 (openEMS v0.37.0-rc1, native
    # Windows console capture):
    #     [@        4s] Timestep:          585 || Speed:    6.2 MC/s ...
    # The real line has a COLON after "Timestep", which the original
    # documentation-derived pattern (r"Timestep\s+(\d+)") could never match —
    # exactly the silent no-report failure the old comment predicted, on every
    # platform, for as long as this bar has existed. `:?` accepts both the
    # measured line and the colon-less wording the docs show.
    #
    # FDTD gets 0..90 %; the far-field / near-field post-processing the deck
    # does afterwards is the last 10 %.
    cb = progress.StreamProgress(
        line_callback,
        step_pattern=r"Timestep:?\s+(\d+)",
        total_pattern=r"NrTS\s*=\s*(\d+)",
        note="Running FDTD", base=0.0, span=0.90)
    watch = _DeckWatch(cb if line_callback is not None else None)
    # ⚠ foreign_python_env: the deck runs under the openEMS VENV python, not
    # FreeCAD's. Inherited unfiltered, the 1.1.4 AppImage's PYTHONHOME killed
    # that interpreter before the deck's first line ("No module named
    # encodings", exit 1) — measured 2026-10-17 under --console. Only this
    # child is filtered; Windows' EMSTUDIO_OPENEMS_DLL_DIR passes through.
    job = SolverJob([python, deck], cwd=workdir, line_callback=watch,
                    env_filter=foreign_python_env)
    # ⚠ Not a bare run_blocking: openEMS exits 0 after DROPPING a port it
    # could not place, so the exit code cannot be the whole verdict.
    _run_watched(job, watch)
    progress.report(line_callback, 0.90, "Reading results")

    csv_path = os.path.join(workdir, "port_{0}.csv".format(port_nr))
    if not os.path.isfile(csv_path):
        raise SolverError("openEMS deck produced no results file: " + csv_path)
    result = _load_port_csv(csv_path, port_nr, analysis=analysis)
    result.meta.update(
        {"workdir": workdir, "duration_s": job.duration_s, "analysis": analysis.Label}
    )
    if watch.grid_line:
        # The preflight's own line — cells, GB needed, GB present — kept with
        # the result so a report or a bug report can quote what was solved.
        result.meta["fdtd_grid"] = watch.grid_line
    _note_capped(result, watch, solver, line_callback, "")
    _copy_model_notes(result, deck)
    # (Touchstone is written at the end, once the port count is known.)

    # optional far field written by the deck (ComputeFarField)
    result.farfield = None
    result.farfields = []
    ff_path = os.path.join(workdir, "farfield_port_{0}.csv".format(port_nr))
    if os.path.isfile(ff_path):
        import glob as _glob

        import numpy as _np

        from emstudio.post.farfield import FarFieldResult

        # The deck writes directivity and radiation efficiency BESIDE the
        # pattern (see writer.py): the pattern CSV stays four columns because
        # post.farfield.load_csv and NEC2's save_csv both depend on that shape.
        # Carrying eta here is what lets a report say "gain 6.1 dBi at 94 %
        # efficiency" instead of quoting directivity and calling it gain.
        # ⛳ ONE META ROW PER PATTERN FREQUENCY, in the deck's own order, so a
        # multi-frequency run pairs each pattern with ITS OWN efficiency
        # instead of stamping the first one on all of them.
        meta_path = os.path.join(workdir,
                                 "farfield_meta_{0}.csv".format(port_nr))
        meta_rows = []
        if os.path.isfile(meta_path):
            meta_rows = list(_np.atleast_2d(
                _np.loadtxt(meta_path, delimiter=",", skiprows=1)))

        def _meta_for(freq_hz):
            m = {"backend": "openEMS"}
            if not len(meta_rows):
                return m
            row = min(meta_rows, key=lambda r: abs(float(r[0]) - freq_hz))
            m.update({
                "directivity_dbi": float(row[1]),
                "eta_rad": float(row[2]),
                "p_acc_w": float(row[3]),
                "p_rad_w": float(row[4]),
            })
            return m

        # PatternFrequencies > 1 writes farfield_port_<n>_<k>.csv per frequency
        # and copies the middle one to the plain name. ``.farfield`` therefore
        # stays the single pattern every existing caller already reads — the
        # 2-D cuts, the 3-D balloon, the PDF report, horn_openems — and
        # ``.farfields`` is what the results dialog's picker needs.
        # ⚠ Sorted by FREQUENCY, not by filename: '_10' sorts before '_2'.
        numbered = _glob.glob(os.path.join(
            workdir, "farfield_port_{0}_*.csv".format(port_nr)))
        for path in numbered:
            ff = FarFieldResult.load_csv(path)
            ff.meta = _meta_for(ff.freq)
            result.farfields.append(ff)
        result.farfields.sort(key=lambda ff: ff.freq)

        default_ff = FarFieldResult.load_csv(ff_path)
        default_ff.meta = _meta_for(default_ff.freq)
        if result.farfields:
            # ⚠ THE SAME OBJECT, not an equal one. The plain-named CSV is a COPY
            # of one of the numbered files, so loading it separately would give
            # ``.farfield`` a twin that is equal to an entry of ``.farfields``
            # and is not it — and anything that pairs them by identity (a
            # picker index, a shared selection) would silently disagree. NEC2
            # takes the same care (``min(result.farfields, key=...)``).
            result.farfield = min(result.farfields,
                                  key=lambda ff: abs(ff.freq - default_ff.freq))
        else:
            result.farfield = default_ff
            result.farfields = [default_ff]

    # optional transmission S-parameters (multi-port): sparam_<to>_<from>.csv
    import glob

    import numpy as np

    result.s_others = {}
    for path in sorted(glob.glob(os.path.join(workdir, "sparam_*_*.csv"))):
        base = os.path.basename(path)[len("sparam_"):-len(".csv")]
        try:
            to_port, from_port = (int(t) for t in base.split("_"))
        except ValueError:
            continue
        result.s_others[(to_port, from_port)] = _load_s_column(
            path, " S{0}{1}".format(to_port, from_port), analysis=analysis)

    # -- optional REMAINING excitations, for a complete N-port ---------------
    # Run 1 drove `port_nr` (the document's own Excited port, which need not be
    # port 1), so the runs still owed are every OTHER port. Subtracting the one
    # already driven is what keeps a 2-port at two solves rather than three.
    if full_smatrix:
        others = [nr for nr in _analysis_port_numbers(analysis) if nr != port_nr]
        _add_excitations(analysis, solver, workdir, python, result,
                         line_callback, others)

    # The order is decided by the DATA: .s1p for one excitation, .s2p once the
    # matrix is complete. Writing a fixed .s1p would have mislabelled the file
    # the moment full_smatrix produced four terms.
    n = result.max_complete_ports()
    result.write_touchstone(
        os.path.join(workdir, "port_{0}.s{1}p".format(port_nr, n)), n_ports=n)

    # optional near-field |E| map (NearFieldPlane)
    result.nearfield = None
    nf_path = os.path.join(workdir, "nearfield.npz")
    if os.path.isfile(nf_path):
        result.nearfield = dict(np.load(nf_path, allow_pickle=False))
    progress.report(line_callback, 1.0, "Done")
    return result
