# SPDX-License-Identifier: LGPL-2.1-or-later
"""Subprocess spawning that does not flash console windows on Windows.

FreeCAD.exe is a GUI-subsystem process, so every console-subsystem child it
spawns — nec2++, ElmerSolver, gmsh, ``wsl``, the version probes — gets a brand
new console window unless the spawn says otherwise. During one NEC2 solve that
is at least three black windows blinking over the viewport (deck run, pattern
run, plus any probe), which reads as "something is broken" to exactly the
users the guided installers exist for (AJ, 2026-08-07).

``CREATE_NO_WINDOW`` is the fix and it is Windows-only by definition; on every
other OS this constant is 0 — the parameter's documented default, so passing
it is a no-op there. Keep it a CONSTANT, not a kwargs-builder: every call site
reads ``creationflags=procutil.CREATE_NO_WINDOW`` and the smoke test can
statically sweep for spawn sites that forgot it.

Deliberately no wrapper around subprocess itself: the call sites differ in
capture/timeout/env in ways a wrapper would either freeze or forward
verbatim, and a forwarding wrapper is just subprocess with a second name.
"""

from __future__ import annotations

import os
import subprocess

#: 0 everywhere except Windows, where it is subprocess.CREATE_NO_WINDOW.
#: (getattr because the attribute itself only exists on Windows builds of
#: CPython — referencing it directly would NameError on the Mac/Linux boxes.)
CREATE_NO_WINDOW = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    if os.name == "nt" else 0)
