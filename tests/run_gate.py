#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run a validation gate under freecadcmd and actually SEE its output.

    freecadcmd tests/run_gate.py tests/validation/antenna_from_selection.py

WHY THIS EXISTS
---------------
``freecadcmd`` buffers and DROPS ``print()`` on exit — even redirected to a
file. Only ``FreeCAD.Console`` and stderr survive. Every gate in this repo
prints (about forty of them), and none of them route through the Console, so
under freecadcmd a failing gate produces **exit 1 and a zero-byte stderr**.

That is not a hypothetical. ``antenna_from_selection`` failed exactly that way
on 2026-08-06, and the silence cost two wrong conclusions in a row: first that
it was some unrelated defect, then — worse — that it was PRE-EXISTING, because
with no message there was nothing to contradict the assumption. It was in fact
a regression introduced hours earlier in the same session. **A gate that cannot
say why it failed will be mis-attributed, and the mis-attribution is more
expensive than the bug.**

The fix belongs here rather than in forty gate files: this shim routes
``sys.stdout`` into ``FreeCAD.Console`` before running the gate, so every
existing ``print()`` reaches the terminal with no gate edited at all.

EXACTLY ONE COPY — Console only, never both (2026-09-25)
--------------------------------------------------------
Until 2026-09-25 this shim TEED: it wrote each line to the original stream
AND to the Console. Measured on FreeCAD 0.21.2 (Linux, macOS), 1.1.1 and 1.1.3
(macOS) and 1.1.3 (Windows), with stdout piped exactly as ``run_battery``
captures it:

* the dropped ``print()`` is Python's stdout BUFFER never being flushed when
  a freecadcmd script ends in ``sys.exit`` / ``SystemExit`` (a script that
  simply falls off its end keeps it) — so the ``flush()`` in ``main()``'s
  ``finally`` revived the stream copy, and the Console copy was ALSO there:
  every line appeared TWICE. ``run_battery --all`` counted both, so every
  published ``--all`` total (3,524 / 3,535 / 3,536) was ~9 % high;
* it was not even a clean doubling. Console-routed lines (``two_port_openems``
  writes its checks there itself) appeared once, and once the output passed
  the C stdio buffer (4 KiB; seen from ~9 KiB of output) the two writers'
  flushes landed inside each other's lines, splicing two check lines into
  one the counter could not read;
* the Console is ONE writer that carries FreeCAD's own lines too, so routing
  everything through it gives exactly one copy, in order, with no splices,
  and the failure message still arrives. A stream-only variant was measured
  and rejected: it splices against the gate's own Console lines and buries
  the failure tail under FreeCAD's exit banner.

DURABLE PER LINE: the Console writes through C stdio, which a NORMAL exit
flushes and a crash does not — so after every line the shim calls the C
runtime's ``fflush(NULL)`` (``_c_fflush``). Measured on the same five builds:
the whole transcript now survives ``os._exit`` with nothing flushed, a
segfault and an ``abort()`` — the old tee lost everything on ``os._exit``
(Linux and macOS) and on a segfault on macOS.
(On a runtime ctypes cannot reach, that flush is a no-op and only a clean
exit is guaranteed.) The Console is used only when this process IS FreeCAD:
FreeCAD imported as a library into a plain python has no Console observer on
stdout, so there the original stream is used. If ``Console.PrintMessage``
ever raises, that line goes to the stream instead — once, in order.

The gate's exit code is preserved exactly, so this drops into a gate chain.
"""
from __future__ import annotations

import os
import runpy
import sys


def _c_fflush():
    """A callable that flushes every C stdio output stream (``fflush(NULL)``),
    or None where no C runtime answers. FreeCAD's Console writes through C
    stdio, which holds up to 4 KiB on a pipe and is written out only by a
    NORMAL exit — so without this a crash in FreeCAD's exit teardown, or an
    ``os._exit`` after the gate's own flush, loses the whole transcript (the
    review of 2026-09-25 measured exactly that). Best-effort: a runtime that
    is not the one FreeCAD links flushes nothing, and nothing breaks."""
    try:
        import ctypes

        if os.name == "nt":
            for name in ("ucrtbase", "msvcrt"):     # FreeCAD 1.x links ucrt
                try:
                    return ctypes.CDLL(name).fflush
                except OSError:
                    continue
            return None
        return ctypes.CDLL(None).fflush
    except Exception:                                           # noqa: BLE001
        return None


class _ConsoleStdout(object):
    """stdout that goes to FreeCAD.Console — and ONLY there when this process
    IS FreeCAD — so every line reaches the terminal exactly once (see WHY
    above). Otherwise (plain python) the original stream, unchanged."""

    def __init__(self, stream):
        self._stream = stream
        self._buf = ""
        # INSIDE FreeCAD (freecadcmd has already imported it) — never import
        # it here. FreeCAD imported as a LIBRARY into a plain python has no
        # Console observer on stdout, so routing there would drop every line
        # silently (measured by the 2026-09-25 review).
        mod = sys.modules.get("FreeCAD")
        self._console = getattr(mod, "Console", None) if mod else None
        self._fflush = _c_fflush() if self._console is not None else None

    def _to_stream(self, text):
        try:
            self._stream.write(text)
            self._stream.flush()        # in order with the Console lines
        except Exception:                                       # noqa: BLE001
            pass

    def _durable(self):
        if self._fflush is not None:
            try:
                self._fflush(None)
            except Exception:                                   # noqa: BLE001
                self._fflush = None

    def _to_console(self, text):
        try:
            self._console.PrintMessage(text)
        except Exception:                                       # noqa: BLE001
            self._durable()             # what the Console already holds first
            self._to_stream(text)       # never lose a line, never write two
            return
        self._durable()                 # on the pipe NOW, not at a clean exit

    def write(self, text):
        if self._console is None:
            try:
                self._stream.write(text)
            except Exception:                                   # noqa: BLE001
                pass
            return len(text)
        # Console.PrintMessage is line-oriented; buffer partial writes so a
        # print(..., end="") does not produce ragged output.
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._to_console(line + "\n")
        return len(text)

    def flush(self):
        if self._console is not None and self._buf:
            self._to_console(self._buf)
            self._buf = ""
        self._durable()
        try:
            self._stream.flush()        # anything a gate wrote past us (.buffer)
        except Exception:                                       # noqa: BLE001
            pass

    def __getattr__(self, name):                # isatty, encoding, fileno …
        return getattr(self._stream, name)


def main(argv):
    if not argv:
        raise SystemExit("usage: run_gate.py <gate.py> [args…]")
    target = argv[0]
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), target)
    if not os.path.isfile(target):
        raise SystemExit("run_gate: no such gate: " + target)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    # Force UTF-8 before anything prints. Gates emit omega, arrows and "+-",
    # and on a cp1252 console the interpreter raises UnicodeEncodeError —
    # which surfaces as a FAILED GATE. Measured 2026-08-06: team7_elmer exits
    # 1 direct from Git Bash and 0 with PYTHONIOENCODING=utf-8, same commit,
    # same physics. run_battery already forces this for the gates it spawns;
    # this closes the same hole for a gate run BY HAND, which is exactly when
    # someone is debugging and least wants a phantom failure.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                           # noqa: BLE001
        pass                        # older/again-wrapped streams: Console still helps

    out = _ConsoleStdout(sys.stdout)
    sys.stdout = out
    sys.argv = [target] + list(argv[1:])
    code = 0
    try:
        # run_name="__main__" so the gate's own auto-run guard fires once,
        # exactly as it does when freecadcmd executes it directly.
        runpy.run_path(target, run_name="__main__")
    except SystemExit as exc:
        c = exc.code
        code = 0 if c is None else (c if isinstance(c, int) else 1)
        if not isinstance(c, int) and c is not None:
            out.write("{0}\n".format(c))        # the failure MESSAGE, not just 1
    except BaseException:                                       # noqa: BLE001
        import traceback

        out.write(traceback.format_exc())
        code = 1
    finally:
        out.flush()
        sys.stdout = out._stream
    return code


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    _args = [a for a in sys.argv[1:] if not a.endswith("run_gate.py")]
    raise SystemExit(main(_args))
