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
