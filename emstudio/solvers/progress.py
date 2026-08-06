# SPDX-License-Identifier: LGPL-2.1-or-later
"""Turn a solver's own output into a determinate progress fraction.

WHY THIS EXISTS
---------------
``ui/run_gui.py`` has carried the machinery for a real progress bar since
v0.88.0 — ``_Reporter.progress(done, total, note)``, an ETA estimator, and a
dialog that switches out of indeterminate mode the moment a fraction arrives.
It was wired to exactly ONE caller, and **none of the four solver runners**.
So every actual solve still showed the swinging bar that says nothing except
"not hung", which is precisely what a user watching a ten-minute run does not
need to be told.

The gap was never the UI. It is that a runner has to notice how far along its
backend is, and each backend says so differently:

* **NEC2** prints one ``FREQUENCY :`` line per sweep point, and we know the
  point count because we wrote the ``FR`` card. Counting them is exact.
* **Elmer** we drive ourselves, one case per frequency — there is nothing to
  parse, we simply know which case we are on. Preferred wherever available:
  a number we orchestrate cannot be broken by an upstream format change.
* **openEMS** prints a running timestep against the ``NrTS`` our own writer
  chose.
* **Palace** iterates; see its runner.

DESIGN RULES
------------
1. **Never break a caller.** A ``ProgressReporter`` is callable and forwards
   every line unchanged, so it can be passed anywhere a ``line_callback`` is
   expected — including into ``SolverJob`` — and the callee cannot tell.
2. **Best effort, never a failure path.** If the wrapped callback has no
   ``.progress`` (an engine gate, a test, a headless run), or the pattern
   never matches because a backend changed its wording, the bar simply stays
   as it was. Progress reporting must never be able to fail a solve.
3. **Phases compose.** A run with a sweep pass and a pattern pass maps each
   into a sub-range via ``base``/``span``, so the bar moves monotonically from
   0 to 1 across the whole job rather than resetting per phase.
"""
from __future__ import annotations

import os
import re
import threading


def _emit(cb, fraction, note):
    """Report a 0..1 fraction to a callback that may not accept one."""
    fn = getattr(cb, "progress", None)
    if fn is None:
        return
    try:
        fn(max(0.0, min(1.0, float(fraction))), 1.0, note or "")
    except Exception:                                       # noqa: BLE001
        pass            # a progress bar is never worth failing a solve for


def report(cb, fraction, note=""):
    """Report a 0..1 fraction directly, for a loop the runner orchestrates.

    Preferred over parsing wherever the runner already knows how many pieces
    of work there are: a number we count ourselves cannot be broken by an
    upstream change of wording, and needs no output stream at all — which
    matters, because NEC2 writes nothing to stdout (measured: 0 bytes).
    """
    _emit(cb, fraction, note)


class ProgressReporter(object):
    """A line callback that also drives the progress bar.

    :param cb: the callback to forward lines to (may be ``None``).
    :param pattern: regex whose every match advances one step. ``None`` = the
        caller drives it with :meth:`step` instead.
    :param total: expected number of matches. ``<= 0`` disables counting —
        with no denominator there is no honest fraction to report.
    :param base, span: map this phase onto ``base .. base+span`` of the whole
        job, so multi-pass runs advance monotonically.
    """

    def __init__(self, cb, pattern=None, total=0, note="", base=0.0, span=1.0):
        self._cb = cb
        self._re = re.compile(pattern) if pattern else None
        self._total = int(total or 0)
        self._note = note
        self._base = float(base)
        self._span = float(span)
        self._seen = 0

    # -- callable: indistinguishable from the callback it wraps -------------
    def __call__(self, line):
        if self._cb is not None:
            self._cb(line)
        if self._re is not None and self._total > 0:
            try:
                if self._re.search(line):
                    self._seen += 1
                    self._report(min(self._seen, self._total) / float(self._total))
            except Exception:                               # noqa: BLE001
                pass

    # -- explicit driving, for loops we orchestrate ourselves ---------------
    def step(self, done, total=None, note=None):
        """Report ``done`` of ``total`` directly. Preferred over parsing."""
        tot = int(total if total is not None else self._total)
        if note is not None:
            self._note = note
        if tot > 0:
            self._report(max(0, int(done)) / float(tot))

    def done(self, note=None):
        """Mark this phase complete (its whole span consumed)."""
        if note is not None:
            self._note = note
        self._report(1.0)

    def _report(self, phase_fraction):
        _emit(self._cb, self._base + self._span * phase_fraction, self._note)

    # -- so a ProgressReporter can itself be wrapped/forwarded --------------
    def progress(self, done, total, note=""):
        """Pass an inner runner's own fraction up through this phase's span."""
        try:
            frac = (float(done) / float(total)) if float(total) > 0 else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            return
        _emit(self._cb, self._base + self._span * frac, note or self._note)


def phase(cb, base, span, note, pattern=None, total=0):
    """Convenience constructor; returns ``cb`` untouched when it is None."""
    if cb is None:
        return None
    return ProgressReporter(cb, pattern=pattern, total=total, note=note,
                            base=base, span=span)


class StreamProgress(object):
    """Progress from a backend that streams "step N of M" style output.

    Unlike :class:`ProgressReporter`, which COUNTS occurrences, this reads the
    step number out of the line — right for a backend that reports an absolute
    position (openEMS prints a running ``Timestep`` against the ``NrTS`` it was
    given) and robust to lines being dropped or batched.

    ``total_pattern`` lets the total be LEARNED from the stream instead of
    passed in. That matters for openEMS: the generated deck already prints
    ``EMStudio: starting openEMS run (NrTS=1000, ...)``, a line *we* emit, so
    the runner picks the total out of its own output rather than duplicating
    ``max(1000, int(solver.MaxTimesteps))`` and risking drift when one changes.

    Callable, forwards every line, and reports nothing at all until it has
    both a total and a step — so an unrecognised dialect leaves the bar
    exactly as it was rather than inventing a fraction.
    """

    def __init__(self, cb, step_pattern, total_pattern=None, total=0, note="",
                 base=0.0, span=1.0):
        self._cb = cb
        self._step = re.compile(step_pattern)
        self._tot_re = re.compile(total_pattern) if total_pattern else None
        self._total = int(total or 0)
        self._note = note
        self._base = float(base)
        self._span = float(span)
        self._last = 0.0

    def __call__(self, line):
        if self._cb is not None:
            self._cb(line)
        try:
            if self._tot_re is not None and self._total <= 0:
                m = self._tot_re.search(line)
                if m:
                    self._total = int(float(m.group(1)))
            if self._total <= 0:
                return
            m = self._step.search(line)
            if not m:
                return
            frac = min(1.0, max(0.0, int(float(m.group(1))) / float(self._total)))
            # monotonic: a backend that restarts a counter (a second port, a
            # re-run) must not drag the bar backwards
            if frac < self._last:
                return
            self._last = frac
            _emit(self._cb, self._base + self._span * frac, self._note)
        except (TypeError, ValueError, IndexError):
            pass

    def progress(self, done, total, note=""):
        """Forward an inner fraction through this phase's span."""
        try:
            frac = (float(done) / float(total)) if float(total) > 0 else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            return
        _emit(self._cb, self._base + self._span * frac, note or self._note)


class FileWatcher(object):
    """Progress from a backend that writes a FILE instead of streaming.

    Some solvers say nothing on stdout. **nec2++ writes ZERO bytes to stdout
    and stderr** (measured 2026-08-05) — every result goes to the ``-o`` file,
    so a line-callback can never see progress no matter how it is wrapped.

    The saving measurement: that file is written **incrementally**. On a
    201-frequency sweep the marker count climbed steadily during the run
    (201 segments / 4.9 s: 9, 19, 30, 41…; 6 wires x 151 segments / 104.8 s:
    1, 2, 3, 4…). So polling it gives a true fraction. And NEC2 genuinely
    needs one — cost is roughly cubic in segment count, and that last model
    took **104.75 s**, while a plain dipole finishes in 0.25 s.

    Counting is INCREMENTAL: only bytes appended since the last poll are
    scanned, with a small carry-over so a marker split across two reads is
    still counted exactly once. Re-reading a megabyte every poll would work
    but scales badly on the long runs that are the whole point.

    Use as a context manager; it always stops, including on an exception::

        with FileWatcher(out, r"FREQUENCY\\s*[:=]", npts, cb, "Sweeping"):
            job.run_blocking(...)
    """

    def __init__(self, path, pattern, total, cb, note="", base=0.0, span=1.0,
                 interval=0.4):
        self._path = path
        self._re = re.compile(pattern)
        self._total = int(total or 0)
        self._cb = cb
        self._note = note
        self._base = float(base)
        self._span = float(span)
        self._interval = float(interval)
        self._stop = threading.Event()
        self._thread = None
        self._pos = 0
        self._carry = ""
        self._count = 0

    def _poll_once(self, final=False):
        """Count markers appended since the last poll.

        ``final`` FLUSHES the carry-over instead of deferring it again. That
        distinction is load-bearing: the tail is held back each poll because a
        marker can straddle two reads, but at end-of-file there is no next
        poll to add it back — so the last match was permanently lost and a
        201-point sweep stopped reporting at 200. The gate caught it by
        asserting the fraction reaches exactly 1.0.
        """
        try:
            size = os.path.getsize(self._path)
            if size <= self._pos and not final:
                return                      # nothing appended (or truncated)
            chunk = ""
            if size > self._pos:
                with open(self._path, "r", encoding="utf-8",
                          errors="replace") as fh:
                    fh.seek(self._pos)
                    chunk = fh.read()
                self._pos = size
            text = self._carry + chunk
            self._count += len(self._re.findall(text))
            if final:
                self._carry = ""            # nothing more can arrive
            else:
                # hold back a short tail so a marker split across two reads is
                # counted exactly once, never zero and never twice
                self._carry = text[-32:] if len(text) > 32 else text
                self._count -= len(self._re.findall(self._carry))
            if self._count < 0:
                self._count = 0
            if self._total > 0:
                _emit(self._cb,
                      self._base + self._span
                      * min(self._count, self._total) / float(self._total),
                      self._note)
        except (OSError, ValueError):
            pass                            # file not created yet, or gone

    def _run(self):
        while not self._stop.wait(self._interval):
            self._poll_once()

    def start(self):
        if self._cb is None or self._total <= 0:
            return self                     # nothing to report to, or no scale
        if getattr(self._cb, "progress", None) is None:
            return self                     # plain callback: no bar to drive
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        """Stop polling — and poll ONCE MORE first.

        The final poll is not tidiness, it is correctness. The loop waits
        ``interval`` between polls, so everything the backend appended after
        the last tick would otherwise never be counted: on a 201-point sweep
        the bar stopped at 199 and the sweep phase never reached its end.
        Caught by the gate, which asserted the fraction reaches exactly 1.0.
        """
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._poll_once(final=True)

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.stop()
        return False                        # never swallow the caller's error
