# SPDX-License-Identifier: LGPL-2.1-or-later
"""Common solver-run machinery.

``SolverJob`` wraps one external solver process: it launches the command in a working
directory, streams stdout/stderr lines to a callback (Report view, log file, test
capture), supports abort, and reports the exit code. Backends build on it with a
functional pipeline mirroring FEM's Machine states:

    workdir = make_workdir(...)
    write_inputs(analysis, solver, workdir)     # Prepare  (backend writer)
    job = SolverJob(cmd, cwd=workdir, ...)      # Solve
    rc = job.run_blocking()
    result = read_results(workdir)              # Results  (backend reader)

Threaded GUI execution wraps the same pipeline in a QThread later; tests call it
blocking. Qt-free by design.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time

from emstudio import procutil


class SolverError(RuntimeError):
    """Raised when a solver run fails; message carries the tail of its output."""


def make_workdir(prefix, base=None):
    """Create (or wipe-and-recreate) a working directory for a solver run."""
    if base:
        path = os.path.abspath(base)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)
        return path
    return tempfile.mkdtemp(prefix=prefix)


def nec2_argv(exe, deck, out):
    """argv for one nec2c run, using BASENAMES — pass ``cwd=dirname(deck)``.

    nec2c has a fixed-size input-filename buffer and aborts with
    ``nec2c: Input file name too long - aborting`` (exit 255) past it. Absolute
    paths used to be passed here, which fit on Linux (`/tmp/emstudio_nec2_xxxx/
    case.nec`, ~36 chars) and did NOT on macOS, where tempfile yields
    `/var/folders/9k/8lz3v_hd6yq5h4y7_4x2f3rw0000gn/T/...` and the same deck is
    ~80 chars. Reported from macOS 26.5 on 2026-08-02, after the reporter had
    built nec2c himself — the run got all the way to the solver and died there.

    Every caller already sets ``cwd`` to the deck's directory, so the basename
    is sufficient and is what Elmer, FastHenry and Palace were already doing.
    """
    d_dir, d_name = os.path.split(os.path.abspath(deck))
    o_dir, o_name = os.path.split(os.path.abspath(out))
    if d_dir != o_dir:
        raise ValueError(
            "nec2 deck and output must share a directory (cwd is set to it): "
            "%r vs %r" % (d_dir, o_dir))
    return [exe, "-i", d_name, "-o", o_name]


#: Variables a FreeCAD host exports for ITS OWN embedded interpreter. A child
#: that is a DIFFERENT python (the openEMS venv) must not inherit them.
#: ⛳ MEASURED 2026-10-17: the 1.1.4 AppImage's AppRun exports
#: ``PYTHONHOME=$APPDIR/usr`` for GUI and --console alike (and FreeCAD leaves
#: ``PYTHONPATH=''``), and the openEMS venv python launched under it died
#: before the deck's first line with "No module named encodings" — it went
#: looking for its standard library inside the AppImage mount. That AppRun
#: has its LD_LIBRARY_PATH export COMMENTED OUT and FreeCAD 1.1.4 on macOS
#: sets none of the three, so LD_LIBRARY_PATH is filtered rather than
#: dropped: only entries inside an AppImage mount ($APPDIR) go, because a
#: user's own entry may be exactly what lets their openEMS build load.
_HOST_PYTHON_HOME = "PYTHONHOME"


def _under(path, roots):
    p = os.path.normcase(os.path.abspath(path))
    for r in roots:
        r = os.path.normcase(os.path.abspath(r))
        if p == r or p.startswith(r.rstrip(os.sep) + os.sep):
            return True
    return False


def foreign_python_env(environ):
    """``environ`` made safe for a python that is NOT FreeCAD's own.

    * ``PYTHONHOME`` is dropped: it names the HOST's standard library, and a
      venv given another interpreter's stdlib cannot even import ``encodings``.
    * ``PYTHONPATH`` keeps the user's own entries and drops only empty ones and
      those inside the host (the AppImage mount, the host's PYTHONHOME) — a
      user who points PYTHONPATH at a hand-built openEMS module keeps it.
    * ``LD_LIBRARY_PATH`` loses only entries inside an AppImage mount.

    Pure: takes and returns a mapping, so a gate can test it without spawning.
    """
    env = dict(environ)
    host_home = env.pop(_HOST_PYTHON_HOME, None)
    appdir = env.get("APPDIR") or ""
    py_roots = [r for r in (appdir, host_home) if r]

    def _filtered(name, roots):
        raw = env.get(name)
        if raw is None:
            return
        keep = [p for p in raw.split(os.pathsep)
                if p and not (roots and _under(p, roots))]
        if keep:
            env[name] = os.pathsep.join(keep)
        else:
            del env[name]

    _filtered("PYTHONPATH", py_roots)
    _filtered("LD_LIBRARY_PATH", [appdir] if appdir else [])
    return env


#: Protocol lines an EMStudio-generated deck prints, kept OUTSIDE the rolling
#: tail because the lines that matter most scroll out of it first: the
#: preflight prints its grid line BEFORE openEMS builds the polyhedra, and a
#: real model then prints hundreds of "Trying reverse order" warnings (466 on
#: the forum J-pole) before the crash the grid line explains.
REFUSED_PREFIX = "EMStudio: REFUSED"
GRID_PREFIX = "EMStudio: FDTD grid"

#: Plain words for the signals a solver dies of. A FACT about how the process
#: ended, never a diagnosis: the same over-limit openEMS grid ends -11, -6, -9
#: or exit 1 depending on OS, memory caps and openEMS version, so the cause is
#: told by the numbers the deck printed (GRID_PREFIX), not by this table.
_SIGNAL_WORDS = {
    "SIGSEGV": "segmentation fault in the solver",
    "SIGABRT": "the solver aborted itself",
    "SIGKILL": "the solver was killed from outside, e.g. by the system",
    "SIGBUS": "bus error in the solver",
    "SIGILL": "illegal instruction in the solver",
    "SIGFPE": "arithmetic fault in the solver",
    "SIGTERM": "the solver was asked to terminate",
}

#: Windows has no signals: a crashed process exits with an NTSTATUS, which
#: Python reports as a large POSITIVE code (0xC0000005 -> 3221225477).
_NTSTATUS_WORDS = {
    0xC0000005: "STATUS_ACCESS_VIOLATION: the solver crashed",
    0xC00000FD: "STATUS_STACK_OVERFLOW: the solver crashed",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN / fail-fast: the solver aborted",
    0xC0000017: "STATUS_NO_MEMORY: the solver ran out of memory",
}


def describe_exit(returncode):
    """' (SIGSEGV: segmentation fault in the solver)' or '' — for a headline."""
    try:
        rc = int(returncode)
    except (TypeError, ValueError):
        return ""
    if rc < 0:
        import signal
        try:
            name = signal.Signals(-rc).name
        except (ValueError, AttributeError):
            return " (killed by signal {0})".format(-rc)
        words = _SIGNAL_WORDS.get(name)
        return " ({0}: {1})".format(name, words) if words else " ({0})".format(name)
    words = _NTSTATUS_WORDS.get(rc & 0xFFFFFFFF) if rc > 0xFFFF else None
    return " (0x{0:08X} {1})".format(rc & 0xFFFFFFFF, words) if words else ""


class SolverJob:
    """One external solver process with line-streamed output and abort support."""

    def __init__(self, cmd, cwd, env=None, line_callback=None, env_filter=None):
        self.cmd = list(cmd)
        self.cwd = cwd
        self.env = env
        # ``env_filter(mapping) -> mapping`` runs on the FINAL environment
        # (os.environ + ``env``). ``env`` can only add or replace; dropping a
        # host variable such as PYTHONHOME needs this — see foreign_python_env.
        self.env_filter = env_filter
        self.line_callback = line_callback or (lambda line: None)
        self.process = None
        self.output_tail = []  # last lines, for error reporting
        #: Last line seen for each protocol prefix (REFUSED_PREFIX, GRID_PREFIX).
        self.protocol_lines = {}
        self._abort = threading.Event()
        self.returncode = None
        self.duration_s = 0.0

    def abort(self):
        self._abort.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def run_blocking(self, timeout=None):
        """Run to completion. Returns the exit code; raises SolverError on failure."""
        t0 = time.time()
        env = dict(os.environ)
        if self.env:
            env.update(self.env)
        if self.env_filter is not None:
            env = self.env_filter(env)
        try:
            self.process = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=procutil.CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise SolverError("could not start {0}: {1}".format(self.cmd[0], exc))

        deadline = (time.time() + timeout) if timeout else None
        try:
            for line in self.process.stdout:
                line = line.rstrip("\n")
                self.output_tail.append(line)
                if len(self.output_tail) > 60:
                    self.output_tail.pop(0)
                for _pfx in (REFUSED_PREFIX, GRID_PREFIX):
                    if line.startswith(_pfx):
                        self.protocol_lines[_pfx] = line
                try:
                    self.line_callback(line)
                except Exception:
                    pass
                if deadline and time.time() > deadline:
                    self.abort()
                    raise SolverError("solver timed out after {0:.0f}s".format(timeout))
                if self._abort.is_set():
                    break
        finally:
            self.process.wait()
            self.duration_s = time.time() - t0
            self.returncode = self.process.returncode

        if self._abort.is_set():
            raise SolverError("solver run aborted")
        if self.returncode != 0:
            raise SolverError(self._failure_message())
        return self.returncode

    def _failure_message(self):
        """Headline first: the deck's own refusal, else how the process ended.

        ⚠ A refused deck exits 1 with its reason as the LAST line, and until
        v1.14.0 the user read "python exited with code 1" above a tail they had
        to scroll — the reason was there and was not the headline. A crash
        reads "exited with code -11" plus the signal's name, and then the
        deck's grid line (cells, GB needed, GB present) even when hundreds of
        geometry warnings pushed it out of the tail, because that line — not
        the signal — is what says whether the grid was the cause.
        """
        exe = os.path.basename(self.cmd[0])
        tail_lines = self.output_tail[-15:]
        head = "{0} exited with code {1}{2}".format(
            exe, self.returncode, describe_exit(self.returncode))
        refused = self.protocol_lines.get(REFUSED_PREFIX)
        if refused:
            head = "{0}\n({1})".format(refused, head)
            tail_lines = [ln for ln in tail_lines if ln != refused]
        else:
            grid = self.protocol_lines.get(GRID_PREFIX)
            if grid and grid not in tail_lines:
                head = "{0}\n{1}".format(head, grid)
        return "{0}\n--- output tail ---\n{1}".format(head, "\n".join(tail_lines))
