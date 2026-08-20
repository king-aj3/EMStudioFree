# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: every solve launch asks the user first, and honours the answer.

``run_gui.run_generic_gui`` is the generic worker launcher. Most of its callers
spawn a real external solver, and AJ's requirement is that the user must
RECOGNISE a commitment before it starts -- a solve that quietly runs for days is
a commitment nobody agreed to. The pre-solve estimate (``confirm_solve_work`` /
``confirm_solve``) is how that is asked.

**This gate exists because eye-auditing the call sites has failed three times.**
2026-08-19 swept the solver-object paths and missed the three OpenFOAM dialogs,
which launch through ``run_generic_gui`` directly. 2026-08-20 swept those and
missed four more. The 2026-08-20 audit of THAT sweep still missed
``cable_dialog._current_sharing``, which fans one FastHenry process per
frequency across every core. Each sweep was careful and each was incomplete,
because "grep and read" has no way to fail loudly when a NEW caller appears.
This does: an unlisted, unguarded caller is a FAILURE, not an omission.

Two properties are checked, and the second is the one a substring scan cannot do:

1. **A guard precedes the launch** in the same function. Line order matters --
   a confirmation raised after the subprocess is already running is not a
   confirmation, it is a notification.
2. **The answer is acted on.** The guard call must sit in the test of an ``if``
   whose body returns. Calling ``confirm_solve_work`` and discarding its bool
   would satisfy any "is the name present?" check while asking a question whose
   answer is thrown away.

The allowlist is keyed on ``(file, class, function)`` and NOT on line numbers,
so ordinary edits above a call site do not churn it -- the stale ``dist/``
line numbers in the 2026-08-20 handoff are exactly the failure mode that
choice avoids. Every entry carries the reason it is not a solve; an entry with
no reason is a bug waiting to be waved through.

Pure python3 static scan via ``ast`` (no FreeCAD, no Qt, no solver binaries).
Pass: exit 0 and 'SOLVE CONFIRM COVERAGE GATE PASSED'.
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Trees to scan. ``pro/`` is included so a Pro-only dialog cannot slip through;
#: it holds no ``ui/`` today, but ``build_pro_zip`` copies from ``emstudio/ui``
#: and a future Pro-side dialog would otherwise be unscanned.
_TREES = ("emstudio", "pro")

_LAUNCHER = "run_generic_gui"
_GUARDS = ("confirm_solve_work", "confirm_solve")

#: Callers that are NOT solves. Each is (relative path, class, function) with
#: the reason it launches no solver. Keep the reasons -- a bare path list would
#: let a real solve be silenced by someone who only wanted the gate green.
_NOT_A_SOLVE = {
    ("emstudio/commands.py", "_AntennaFromSelection", "Activated"):
        "geometry marshalling only -- fs.build() derives the wire model and then "
        "tells the user to press Run Solver, so it PRECEDES a solve rather than "
        "being one. The solve it leads to is gated at _RunSolver.Activated.",
    ("emstudio/ui/assistant_dock.py", "AssistantDock", "_run_preflight"):
        "LLM endpoint reachability probe -- no solver backend, no estimate history.",
    ("emstudio/ui/assistant_dock.py", "AssistantDock", "_on_ask"):
        "LLM chat completion -- the assistant has its own separate confirmation "
        "for the actions it proposes (covered by gui_smoke).",
    ("emstudio/ui/assistant_dock.py", "AssistantDock", "_handle_tool_calls"):
        "LLM tool-call dispatch -- any solve it triggers goes through a gated "
        "command, and the dock confirms the tool call separately.",
    ("emstudio/ui/assistant_dock.py", "AssistantSettingsDialog", "_fetch_models"):
        "HTTP GET of the endpoint's model list.",
    ("emstudio/ui/assistant_dock.py", "AssistantSettingsDialog", "_test"):
        "HTTP round-trip that tests the configured endpoint.",
}


def _py_files(tree_root):
    """Every .py under a tree, __pycache__ excluded, in a stable order."""
    out = []
    for dirpath, dirs, files in os.walk(tree_root):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".py"):
                out.append(os.path.join(dirpath, name))
    return out


def _guard_lines(func):
    """Line numbers of guards inside ``func`` whose ANSWER is acted on.

    A guard qualifies only when its call sits in the test of an ``if`` whose
    body returns -- that is the shape every real call site uses
    (``if not run_gui.confirm_solve_work(...): return``, sometimes with a
    cleanup call before the return). Anything else asks a question and ignores
    the reply, which is worse than not asking: it teaches the user their answer
    matters when it does not.
    """
    lines = []
    for node in ast.walk(func):
        if not isinstance(node, ast.If):
            continue
        named = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in _GUARDS
            for n in ast.walk(node.test)
        )
        if named and any(isinstance(n, ast.Return) for n in ast.walk(node)):
            lines.append(node.lineno)
    return lines


def _launch_lines(func):
    """Line numbers of ``run_generic_gui`` calls directly inside ``func``."""
    return [
        n.lineno for n in ast.walk(func)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == _LAUNCHER
    ]


def _scan(path, rel):
    """(failures, seen_keys) for one file."""
    failures, seen = [], set()
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    except SyntaxError as exc:
        return ["{0}: does not parse ({1})".format(rel, exc)], seen

    # Walk classes so the allowlist key can name one. Five different command
    # classes in commands.py all define ``Activated``; a function-name-only key
    # would silence four call sites while meaning to silence one.
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for func in ast.walk(cls):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            launches = _launch_lines(func)
            if not launches:
                continue
            key = (rel, cls.name, func.name)
            seen.add(key)
            if key in _NOT_A_SOLVE:
                continue
            guards = _guard_lines(func)
            for line in launches:
                if not any(g < line for g in guards):
                    failures.append(
                        "{0}:{1} {2}.{3} launches {4} with no acted-on "
                        "{5} before it".format(
                            rel, line, cls.name, func.name, _LAUNCHER,
                            " / ".join(_GUARDS)))
    return failures, seen


def main():
    failures, seen = [], set()
    scanned_files = set()
    checked = 0
    for tree_name in _TREES:
        root = os.path.join(_ROOT, tree_name)
        if not os.path.isdir(root):
            continue
        for path in _py_files(root):
            rel = os.path.relpath(path, _ROOT).replace(os.sep, "/")
            f, s = _scan(path, rel)
            failures.extend(f)
            seen |= s
            scanned_files.add(rel)
            checked += 1

    # A launcher that no longer exists must not sit in the allowlist forever
    # granting silent permission -- that is how an exemption outlives the
    # reason for it and covers a rewritten function that DOES solve.
    #
    # ⚠ But "the file is not here" is NOT "the exemption is stale". This gate is
    # EXPORTED and runs in the free tree too, where the Pro-only files are
    # stripped out entirely -- ``assistant_dock.py`` is Pro, so all five of its
    # entries would read as stale there and fail a tree that is perfectly
    # correct. (Measured: the free battery failed exactly that way the first
    # time this gate was exported.) An entry is stale only when its file IS
    # present and its function has stopped calling the launcher; an absent file
    # means the entry does not apply to this tier.
    for key in sorted(_NOT_A_SOLVE):
        if key[0] not in scanned_files:
            continue
        if key not in seen:
            failures.append(
                "allowlist entry {0} no longer calls {1} -- remove it".format(
                    key, _LAUNCHER))

    print("solve-confirm coverage: {0} files, {1} launch site(s) in {2} "
          "function(s), {3} allowlisted".format(
              checked, sum(1 for _ in seen), len(seen), len(_NOT_A_SOLVE)))
    if failures:
        for msg in failures:
            print("FAIL - {0}".format(msg))
        print("SOLVE CONFIRM COVERAGE GATE FAILED")
        return 1
    print("SOLVE CONFIRM COVERAGE GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
