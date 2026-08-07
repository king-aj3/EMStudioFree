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


class SolverJob:
    """One external solver process with line-streamed output and abort support."""

    def __init__(self, cmd, cwd, env=None, line_callback=None):
        self.cmd = list(cmd)
        self.cwd = cwd
        self.env = env
        self.line_callback = line_callback or (lambda line: None)
        self.process = None
        self.output_tail = []  # last lines, for error reporting
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
            tail = "\n".join(self.output_tail[-15:])
            raise SolverError(
                "{0} exited with code {1}\n--- output tail ---\n{2}".format(
                    os.path.basename(self.cmd[0]), self.returncode, tail
                )
            )
        return self.returncode
