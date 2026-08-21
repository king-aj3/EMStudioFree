# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: `_lib_present()` on all three platforms, from any one.

**This gate exists because the fix it covers was never run.** The 2026-08-20
audit's HIGH #1 — `_lib_present()` swallowing `ldconfig`'s absence and so
reporting every "lib" prerequisite MISSING on macOS, which blocked the guided
source builds there — was written and reviewed but not executed: the macOS
build host was unreachable. The handoff recorded it as *"reasoned and reviewed,
not run."*

This does not replace running it on a Mac. It pins the **decision logic**,
which is platform-independent and is where the defect actually lived, so a
regression goes red in CI on every push instead of waiting for a Mac to be
reachable. What still needs a real Mac is whether Homebrew's prefix and the
`.dylib` naming are what this code assumes.

**The property that matters, and it is counter-intuitive: a probe that CANNOT
RUN must answer True.** An unprovable prerequisite must not masquerade as a
proven-missing one and block a build that would have worked; a genuinely
missing library still fails the compile with its own accurate error. That is
the exact inversion the original `except: return False` got wrong, so it is
checked on both platforms that can hit it (§D3, §L3).

⛳ **`os.name` is "posix" on macOS AND Linux** — the trap this project has hit
before (Solver Setup once told macOS users to run `sudo apt install`). The
gate therefore drives darwin and linux SEPARATELY and asserts they disagree
where they must, so a branch collapsing into the other cannot pass.

**How it drives the platforms.** It injects the DATA the function reads —
`sys.platform`, `os.name`, `os.path.isdir`, `glob.glob`, and `subprocess.run`
— through proxies that delegate everything else to the real modules. It does
NOT monkeypatch `_lib_present` itself or any helper it calls: patching the
lookup would make the layer under it unobservable, which is the whole point of
the checks below. See the `drift()` / `BalloonScrubber` precedent.

Pass: exit 0 and 'LIB PRESENT PLATFORMS GATE PASSED'. Pure python3, no FreeCAD,
no solver binaries, no network.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " - " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


class _Proxy(object):
    """Delegates every attribute to `real` except those explicitly overridden.

    Used instead of assigning to `sys.platform` / `os.name` directly so the
    real modules are never mutated — a gate that leaves state behind is worse
    than no gate, and this one runs inside a battery of 40 others.
    """

    def __init__(self, real, **overrides):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_over", overrides)

    def __getattr__(self, name):
        over = object.__getattribute__(self, "_over")
        if name in over:
            return over[name]
        return getattr(object.__getattribute__(self, "_real"), name)


class _Run(object):
    """Stands in for subprocess.run. `handler` maps argv -> stdout, or raises."""

    class _Res(object):
        def __init__(self, stdout):
            self.stdout = stdout
            self.returncode = 0

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def run(self, argv, **kw):
        self.calls.append(list(argv))
        return self._Res(self.handler(list(argv)))


def _probe(stem, platform, osname, *, brew_prefix=None, dylibs=(),
           libdirs=(), ldconfig=None, ldconfig_raises=False):
    """Call the REAL _lib_present with injected surroundings. Returns
    (answer, the argv list it actually spawned)."""
    from emstudio.setup import solvers

    def handler(argv):
        if argv[:2] == ["brew", "--prefix"]:
            if brew_prefix is None:
                raise OSError("brew not found")
            return brew_prefix
        if argv[:1] == ["ldconfig"]:
            if ldconfig_raises:
                raise FileNotFoundError("ldconfig: not found")
            return ldconfig or ""
        raise AssertionError("unexpected spawn: %r" % (argv,))

    runner = _Run(handler)
    # ⚠ normcase, not a raw string compare. `_lib_present` builds these paths
    # with os.path.join, which emits BACKSLASHES when this gate runs on
    # Windows, while the fixtures are written with forward slashes. fnmatch
    # already normcases internally (which is why the glob checks passed while
    # a raw isdir compare silently answered False for every prefix, inverting
    # D2). Same separator class as the export_free drift() bug.
    _want_dirs = {os.path.normcase(x) for x in libdirs}
    fake_path = _Proxy(os.path,
                       isdir=lambda p: os.path.normcase(p) in _want_dirs)
    saved = {
        "sys": solvers.sys, "os": solvers.os, "subprocess": solvers.subprocess,
        "glob": sys.modules.get("glob"),
    }
    solvers.sys = _Proxy(sys, platform=platform)
    solvers.os = _Proxy(os, name=osname, path=fake_path)
    solvers.subprocess = _Proxy(saved["subprocess"], run=runner.run)
    sys.modules["glob"] = _Proxy(
        saved["glob"], glob=lambda pat: [p for p in dylibs if _fnmatch(p, pat)])
    try:
        return solvers._lib_present(stem), runner.calls
    finally:
        solvers.sys, solvers.os = saved["sys"], saved["os"]
        solvers.subprocess = saved["subprocess"]
        if saved["glob"] is None:
            sys.modules.pop("glob", None)
        else:
            sys.modules["glob"] = saved["glob"]


def _fnmatch(path, pattern):
    import fnmatch as _f
    return _f.fnmatch(path, pattern)


def main():
    print("== _lib_present across darwin / windows / linux ==")

    # ---------------------------------------------------------------- darwin
    # D1: Homebrew present and the .dylib is there.
    got, calls = _probe(
        "openblas", "darwin", "posix", brew_prefix="/opt/homebrew",
        dylibs=["/opt/homebrew/lib/libopenblas.0.dylib"],
        libdirs=["/opt/homebrew/lib"])
    check("D1 darwin: brew prefix + dylib present -> True", got is True)
    check("D1 darwin: consulted brew, never ldconfig",
          any(c[:2] == ["brew", "--prefix"] for c in calls)
          and not any(c[:1] == ["ldconfig"] for c in calls),
          "spawned %r" % (calls,))

    # D2: Homebrew IS installed (its lib dir exists) and the library is in
    # NEITHER of the two places Homebrew puts libraries -- see D4 for why that
    # qualifier is load-bearing.
    got, _ = _probe("openblas", "darwin", "posix", brew_prefix="/opt/homebrew",
                    dylibs=[], libdirs=["/opt/homebrew/lib"])
    check("D2 darwin: brew installed, dylib in neither location -> False",
          got is False,
          "a library Homebrew could have provided and did not IS provably "
          "missing, and the user can act on it")

    # D4 ⚠⚠ KEG-ONLY. This is the defect HIGH #1 was actually hiding, and it
    # was invisible to every check above because they all assume Homebrew
    # symlinks into <prefix>/lib. It does not for keg-only formulae -- openblas
    # and lapack collide with Apple's Accelerate framework, so brew installs
    # them under <prefix>/opt/<name>/lib and links nothing.
    # MEASURED on the arm64 build host 2026-08-21, with openblas installed:
    #   /opt/homebrew/lib/libopenblas*.dylib          -> no matches
    #   /opt/homebrew/opt/openblas/lib/libopenblas.dylib -> present
    # and _lib_present("openblas") returned False. The user is then blocked
    # from a guided source build by a prerequisite they have already installed
    # -- the exact failure D3's comment says this branch exists to prevent,
    # arriving through a door D3 does not watch.
    got, _ = _probe(
        "openblas", "darwin", "posix", brew_prefix="/opt/homebrew",
        dylibs=["/opt/homebrew/opt/openblas/lib/libopenblas.dylib"],
        libdirs=["/opt/homebrew/lib"])
    check("D4 darwin: KEG-ONLY dylib under opt/<name>/lib -> True", got is True,
          "brew installed it; it is simply not symlinked into <prefix>/lib")

    # D5: the keg dir is consulted for the RIGHT formula, not any formula.
    # ⚠ THIS IS NOT A HYPOTHETICAL, which is the only reason it is worth a
    # check. MEASURED on the build host: the openblas keg SHIPS ITS OWN
    # liblapack.dylib and libblas.dylib (OpenBLAS bundles a LAPACK), so
    #   /opt/homebrew/opt/openblas/lib/liblapack.dylib
    # exists on a machine where the `lapack` FORMULA is not installed at all.
    # A fix that reached for <prefix>/opt/*/lib instead of <prefix>/opt/<stem>/lib
    # would therefore answer True for lapack off the back of openblas -- naming
    # a prerequisite satisfied by a library sitting in another formula's private
    # keg, which is not on any search path a build would use.
    # ⛳ The first draft of this check used libopenblas.dylib as the intruder
    # and could not fail: the FILENAME glob already discriminates when the stem
    # differs. The mutation caught the check, not the code. The intruder has to
    # be a file whose NAME matches the stem being asked about.
    got, _ = _probe(
        "lapack", "darwin", "posix", brew_prefix="/opt/homebrew",
        dylibs=["/opt/homebrew/opt/openblas/lib/liblapack.dylib",
                "/opt/homebrew/opt/openblas/lib/libopenblas.dylib"],
        libdirs=["/opt/homebrew/lib"])
    check("D5 darwin: another formula's keg does NOT answer for this one "
          "-> False", got is False,
          "openblas bundles liblapack.dylib; the lapack FORMULA is still absent")

    # D3 ⚠ THE INVERSION THE ORIGINAL GOT WRONG.
    got, _ = _probe("openblas", "darwin", "posix", brew_prefix=None,
                    dylibs=[], libdirs=[])
    check("D3 darwin: NO Homebrew at all -> True (unprovable != missing)",
          got is True,
          "returning False here is HIGH #1: it blocked every guided source "
          "build on macOS behind a prerequisite the probe could not evaluate")

    # --------------------------------------------------------------- windows
    got, calls = _probe("openblas", "win32", "nt")
    check("W1 windows: -> True with no probe at all", got is True and not calls,
          "spawned %r" % (calls,))

    # ----------------------------------------------------------------- linux
    got, calls = _probe("openblas", "linux", "posix",
                        ldconfig="\tlibopenblas.so.0 (libc6,x86-64) => /usr/lib")
    check("L1 linux: ldconfig lists it -> True", got is True)
    check("L1 linux: consulted ldconfig, never brew",
          any(c[:1] == ["ldconfig"] for c in calls)
          and not any(c[:2] == ["brew", "--prefix"] for c in calls),
          "spawned %r" % (calls,))

    got, _ = _probe("openblas", "linux", "posix",
                    ldconfig="\tlibsomethingelse.so.2 => /usr/lib")
    check("L2 linux: ldconfig ran and did NOT list it -> False", got is False)

    # L3 ⚠ the second half of the same inversion (musl, a slim container).
    got, _ = _probe("openblas", "linux", "posix", ldconfig_raises=True)
    check("L3 linux: ldconfig missing -> True (unprovable != missing)",
          got is True)

    # ------------------------------------------------- the os.name == posix trap
    # Same os.name, same absent library, DIFFERENT answers. If the darwin
    # branch ever collapses into the posix one (or vice versa) these converge
    # and this check is what notices.
    mac, _ = _probe("openblas", "darwin", "posix", brew_prefix="/opt/homebrew",
                    dylibs=[], libdirs=["/opt/homebrew/lib"])
    lin, _ = _probe("openblas", "linux", "posix", ldconfig_raises=True)
    check("darwin and linux are genuinely separate branches under posix",
          mac is False and lin is True,
          "both are os.name='posix'; they must NOT share a code path "
          "(this project once told macOS users to run `sudo apt install`)")

    # The gate must not have mutated the real modules on the way through.
    from emstudio.setup import solvers
    check("no state left behind",
          solvers.sys is sys and solvers.os is os
          and sys.modules["glob"].__name__ == "glob")

    if FAILURES:
        print("LIB PRESENT PLATFORMS GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("LIB PRESENT PLATFORMS GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
