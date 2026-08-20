# SPDX-License-Identifier: LGPL-2.1-or-later
"""How long is this solve going to take? — answered from measurement, or not at all.

WHY THIS EXISTS
---------------
``solvers/progress.py`` gives a determinate bar and a live ETA once a run is
under way, which is the right answer to "is it hung?". It is the wrong answer
to the question a user actually asks *before* committing: **is this thirty
seconds or forty minutes?** By the time the live ETA has enough evidence to
speak (3 s and 5 % done) the decision has already been made.

WHY IT IS HARDER THAN IT LOOKS, AND WHAT THIS REFUSES TO DO
-----------------------------------------------------------
A cost model from first principles — NEC2 is O(N^3) in segments, openEMS is
timesteps x cells — gives a *shape*, never a duration. The constant is the
machine: cores, clock, memory bandwidth, whether the box is also running a
CFD. Publishing "about 4 minutes" from a formula with an uncalibrated constant
is a confident number with nothing behind it, and this project has a rule
against those.

So the estimate comes from **this machine's own measured history**, and when
there is no history it says so instead of guessing. An honest "no estimate
yet — this is the first run of this size" is worth more than a fabricated
figure, because a user who is told 2 minutes and waits 40 stops believing
every other number the tool prints.

HOW THE HISTORY IS KEYED
------------------------
Runs are bucketed by backend and by a scalar ``work`` measure (segments x
frequency points for MoM, timesteps for FDTD, cells x iterations for CFD —
whatever that backend's runner can cheaply state). Buckets are **logarithmic**,
so a 10 % change in problem size lands in the same bucket and the history
stays dense enough to be useful, while a 10x change does not borrow the
smaller problem's timing.

Within a bucket the estimate is the **median** — one pathological run (a swap
storm, a laptop that slept) should not move it, and a mean would.

Across buckets, a neighbouring bucket is used only with an explicit linear
scale by the work ratio, and the result is labelled EXTRAPOLATED so the caller
can weaken its wording. Two buckets away it declines entirely.

Qt-free and FreeCAD-free on purpose, with the store injected — so the whole
thing is testable from plain python3 with no FreeCAD and no GUI.
"""
from __future__ import annotations

import json
import math

#: Runs kept per bucket. Enough for a stable median, few enough that a machine
#: that genuinely got faster (new CPU) is re-learned within a handful of runs.
HISTORY_PER_BUCKET = 7

#: Ratio between adjacent bucket edges. 2.0 means each bucket spans a doubling
#: of work — coarse enough to gather history, fine enough that a neighbour's
#: scaled timing is still worth quoting.
BUCKET_RATIO = 2.0

#: How far a neighbouring bucket may be borrowed from, in buckets.
MAX_BORROW = 1


def bucket_of(work):
    """Logarithmic bucket index for a scalar work measure. 0 for nonsense."""
    try:
        w = float(work)
    except (TypeError, ValueError):
        return 0
    if not (w > 0.0) or math.isinf(w) or math.isnan(w):
        return 0
    return int(math.floor(math.log(w, BUCKET_RATIO)))


def _key(backend, work):
    return "%s/%d" % (str(backend or "?"), bucket_of(work))


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if not n:
        return None
    m = n // 2
    return s[m] if n % 2 else 0.5 * (s[m - 1] + s[m])


class History(object):
    """Measured solve durations, persisted through an injected store.

    ``store`` needs only ``get(str) -> str`` and ``set(str, str)``; FreeCAD's
    ``ParamGet`` group satisfies that with a two-line adapter, and a dict does
    in tests. Anything unreadable is treated as empty rather than raised — a
    corrupt preference must never be able to block a solve.
    """

    KEY = "SolveHistory"

    def __init__(self, store=None):
        self._store = store if store is not None else {}

    def _load(self):
        try:
            raw = self._store.get(self.KEY) or "{}"
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:                                  # noqa: BLE001
            return {}

    def _save(self, data):
        try:
            self._store.set(self.KEY, json.dumps(data))
        except Exception:                                  # noqa: BLE001
            pass                                           # never fail a solve

    def record(self, backend, work, seconds):
        """Remember one completed solve. Ignores nonsense rather than storing it."""
        try:
            secs = float(seconds)
        except (TypeError, ValueError):
            return
        if not (secs > 0.0) or math.isinf(secs) or math.isnan(secs):
            return
        data = self._load()
        k = _key(backend, work)
        runs = [float(x) for x in data.get(k, []) if isinstance(x, (int, float))]
        runs.append(secs)
        data[k] = runs[-HISTORY_PER_BUCKET:]
        self._save(data)

    def estimate(self, backend, work):
        """Return ``(seconds, basis)``. ``seconds`` is None when unknown.

        ``basis`` is always a sentence fit to show a user, because an estimate
        without its provenance is the thing this module exists to avoid.
        """
        data = self._load()
        b = bucket_of(work)
        own = [float(x) for x in data.get(_key(backend, work), [])]
        if own:
            med = _median(own)
            return med, ("measured here: median of %d previous run%s of this "
                         "size" % (len(own), "" if len(own) == 1 else "s"))

        # Nearest neighbour bucket, scaled by the work ratio and labelled.
        for d in range(1, MAX_BORROW + 1):
            for nb in (b - d, b + d):
                runs = [float(x) for x in data.get("%s/%d" % (backend, nb), [])]
                if not runs:
                    continue
                med = _median(runs)
                # Bucket centres differ by BUCKET_RATIO**(b-nb); scaling by that
                # is linear-in-work, which is optimistic for an O(N^3) backend
                # and stated as approximate for exactly that reason.
                scaled = med * (BUCKET_RATIO ** (b - nb))
                return scaled, ("EXTRAPOLATED from %d run%s of a %s problem — "
                                "treat as a rough order of magnitude"
                                % (len(runs), "" if len(runs) == 1 else "s",
                                   "smaller" if nb < b else "larger"))
        return None, ("no estimate yet — this is the first solve of this size "
                      "on this machine, and a guessed duration would be worse "
                      "than none")


def humanise(seconds):
    """A duration a user can act on, deliberately coarse.

    Rounded hard, because the precision of the underlying estimate does not
    justify "4 m 37 s" and quoting it would imply it does.
    """
    if seconds is None:
        return "unknown"
    s = float(seconds)
    if s < 45:
        return "under a minute"
    if s < 90:
        return "about a minute"
    if s < 3600:
        mins = int(round(s / 60.0))
        if mins < 10:
            return "about %d minutes" % mins
        return "about %d minutes" % (5 * int(round(mins / 5.0)))
    hours = s / 3600.0
    if hours < 2:
        return "about an hour"
    if hours < 36:
        return "about %d hours" % int(round(hours))
    # Past a day and a half, HOURS stop being a unit anyone reasons with:
    # "about 72 hours" reads as a big number, "about 3 days" reads as a
    # decision. The whole point of asking first is that the user recognises
    # a commitment they did not intend to make.
    days = hours / 24.0
    if days < 14:
        return "about %d days" % int(round(days))
    weeks = days / 7.0
    if weeks < 9:
        return "about %d weeks" % int(round(weeks))
    return "MONTHS — over %d weeks" % int(weeks)


def describe(backend, work, history):
    """One user-facing sentence: the estimate and where it came from."""
    secs, basis = history.estimate(backend, work)
    if secs is None:
        return "Estimated time: unknown (%s)." % basis
    return "Estimated time: %s (%s)." % (humanise(secs), basis)


# --- integration helpers ----------------------------------------------------
#: Preference key holding the JSON history. Lives in EMStudio's own group.
PREF_GROUP = "User parameter:BaseApp/Preferences/Mod/EMStudio"


def freecad_history():
    """A :class:`History` backed by FreeCAD's preference store.

    Returns an in-memory history when FreeCAD is unavailable (tests, engine
    gates, a headless deck), so callers never have to branch on it.
    """
    try:
        import FreeCAD

        params = FreeCAD.ParamGet(PREF_GROUP)

        class _P(object):
            def get(self, k, d=None):
                return params.GetString(k, "") or d

            def set(self, k, v):
                params.SetString(k, v)

        return History(_P())
    except Exception:                                      # noqa: BLE001
        return History({})


def work_of(analysis, solver_obj=None):
    """A cheap scalar standing in for how much work a solve is.

    It does NOT need to be a time, or even the same units across backends —
    history is keyed per backend, so it only has to be monotonic in cost and
    computable without touching the solver. Frequency points times whatever
    per-frequency size the analysis exposes is enough for that.

    Returns 0 when nothing can be read, which buckets to 0 and simply means
    "no useful history key" rather than an error.
    """
    def _num(obj, name, default=0.0):
        try:
            v = getattr(obj, name, None)
            if v is None:
                return default
            return float(getattr(v, "Value", v))
        except (TypeError, ValueError):
            return default

    pts = _num(analysis, "FrequencyPoints", 1.0) or 1.0
    # Whichever of these the analysis carries; absent ones contribute nothing.
    size = 1.0
    for name in ("SegmentsPerWavelength", "CellsPerWavelength", "MeshOrder"):
        v = _num(solver_obj, name, 0.0) or _num(analysis, name, 0.0)
        if v > 0:
            size *= v
    # A full S-matrix solves every excitation on the same mesh, so it is
    # genuinely N runs. Counting it as one would quote a fraction of the time
    # for the option whose whole cost IS the extra solves — and counting it as
    # TWO, which this did until v1.2.0, is right only for a 2-port: it quoted
    # half the truth for a 4-port and would have been the largest
    # under-estimate in the product.
    size *= excitation_count(analysis, solver_obj)
    return float(pts * size)


def excitation_count(analysis, solver_obj=None):
    """How many solver runs one "solve" actually is. 1 unless a full matrix.

    Both full-wave backends excite ONE port per run by construction, so a full
    NxN S-matrix is N solves. The count is the analysis's own port count, not a
    number the user typed, because the geometry is what decides it.

    Ports are counted through ``objects.query``, which matches on the
    ``EMStudioType`` tag and imports nothing from FreeCAD — so this module stays
    FreeCAD-free and testable from plain python, as the rest of it is.

    ⚠ **Falls back to 1, not to 2.** An analysis whose ports cannot be counted
    is one this estimator knows nothing about; multiplying by a port count
    invented here would be exactly the confident-number-with-nothing-behind-it
    this module exists to refuse. An estimate that is too low by the port count
    is still recognisably an estimate; the fallback keeps the work measure
    equal to the single-excitation case it can actually stand behind.
    """
    if not bool(getattr(solver_obj, "FullSMatrix", False)):
        return 1
    try:
        from emstudio.objects import query

        n = len(query.get_ports(analysis))
    except Exception:
        return 1
    return max(1, n)
