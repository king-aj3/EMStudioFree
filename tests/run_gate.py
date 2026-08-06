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

The fix belongs here rather than in forty gate files: this shim tees
``sys.stdout`` into ``FreeCAD.Console`` before running the gate, so every
existing ``print()`` reaches the terminal with no gate edited at all.

The gate's exit code is preserved exactly, so this drops into a gate chain.
"""
from __future__ import annotations

import os
import runpy
import sys


class _Tee(object):
    """stdout that also reaches FreeCAD.Console (which survives exit)."""

    def __init__(self, stream):
        self._stream = stream
        self._buf = ""
        try:
            import FreeCAD

            self._console = FreeCAD.Console
        except Exception:                                       # noqa: BLE001
            self._console = None                # plain python: nothing to tee

    def write(self, text):
        try:
            self._stream.write(text)
        except Exception:                                       # noqa: BLE001
            pass
        if self._console is None:
            return
        # Console.PrintMessage is line-oriented; buffer partial writes so a
        # print(..., end="") does not produce ragged output.
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            try:
                self._console.PrintMessage(line + "\n")
            except Exception:                                   # noqa: BLE001
                pass

    def flush(self):
        if self._console is not None and self._buf:
            try:
                self._console.PrintMessage(self._buf)
            except Exception:                                   # noqa: BLE001
                pass
            self._buf = ""
        try:
            self._stream.flush()
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
        pass                        # older/again-wrapped streams: tee still helps

    tee = _Tee(sys.stdout)
    sys.stdout = tee
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
            tee.write("{0}\n".format(c))        # the failure MESSAGE, not just 1
    except BaseException:                                       # noqa: BLE001
        import traceback

        tee.write(traceback.format_exc())
        code = 1
    finally:
        tee.flush()
        sys.stdout = tee._stream
    return code


if __name__ == "__main__" or "FreeCAD" in sys.modules:
    _args = [a for a in sys.argv[1:] if not a.endswith("run_gate.py")]
    raise SystemExit(main(_args))
