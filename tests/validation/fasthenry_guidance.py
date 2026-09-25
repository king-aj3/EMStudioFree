# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: FastHenry is Automation-only on Windows — say so, don't detect it.

Pass: exit 0 and 'FASTHENRY-GUIDANCE GATE PASSED'.

WHY THIS EXISTS. The FastFieldSolvers Windows bundle installs FastHenry2.exe,
and a user who installs it reasonably expects EMStudio to find it. AJ did,
2026-08-13. It cannot be used: EMStudio drives solvers as SUBPROCESSES, and
FastHenry2.exe is an Automation (COM) application. Their own History.txt,
shipped beside the binary, records version 3.0 (2004/12/10) — "Removed the
possibility to pass arguments to FastHenry when launching from the command
line (must use Automation)". Measured on an installed copy the same day: both
`-help` and a real .inp deck hang with no output and no Zc.mat.

So there are TWO properties here and they pull in opposite directions:

* Detection must NOT learn that binary. Reporting FastHenry "found" would be
  worse than the bug it fixes — every solve would then hang to its timeout.
* The GUIDANCE must explain the situation, because a bare MISSING beside an
  installed program reads as a detection fault. The hint used to make it worse
  by saying "Install it, then point EMStudio at fasthenry.exe", a file that
  bundle does not contain.

Pure logic, no binary and no solver run — FAST tier. The bundle's real install
directory is simulated with a temp dir, so this gate asserts the same thing on
Linux CI as on the Windows box where the bug was found. The Windows-only
sections take that further and fake ``os.name`` (the technique gui_smoke
already uses for the Solver Setup dialog), so nothing here is asserted on one
platform and quietly unasserted on the others.
"""
import os
import pathlib
import shutil
import sys
import tempfile
# Imported HERE, at module scope, ON PURPOSE — before anything fakes os.name.
# urllib.request chooses its url2pathname at IMPORT time from os.name, so a
# FIRST import taken while os.name is faked to "nt" binds nturl2path, and the
# pinning block's real /tmp/... file:// fixture is then read back as the UNC
# path \\tmp\... and fails to open. Binding it against the REAL platform
# first keeps the fixture readable while os.name is faked below. (Measured:
# without this the download step raises before a single pin is checked.)
import urllib.request  # noqa: F401  — imported for its import-time binding

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    from emstudio.setup import solvers
    from emstudio.solvers.base import SolverError

    print("EMStudio FastHenry guidance gate")

    # --- detection must NOT be taught the Automation binary ----------------
    print(" detection contract:")
    execs = tuple(solvers.BACKENDS["fasthenry"].executables)
    # Positive form FIRST: pin what the tuple IS, so this cannot pass merely
    # because some spelling of the forbidden name failed to appear.
    check("executables are exactly the CLI name",
          execs == ("fasthenry",),
          "executables={0!r}".format(execs))
    lowered = " ".join(execs).lower()
    check("no FastHenry2 binary in the detection candidates",
          "fasthenry2" not in lowered,
          "detecting it would report FastHenry usable and hang every solve")

    # --- the status note --------------------------------------------------
    print(" status note:")
    real_name, real_dirs = os.name, solvers._FFS_DIRS
    tmp = tempfile.mkdtemp(prefix="ffs_")
    try:
        # (a) a bundle IS installed -> explain, and name where it is
        with open(os.path.join(tmp, "FastHenry2.exe"), "wb") as fh:
            fh.write(b"not a real binary")
        os.name = "nt"
        solvers._FFS_DIRS = (tmp,)
        note = solvers.fasthenry_status_note()
        check("installed bundle produces a note", bool(note))
        check("the note says WHERE it is", tmp in note,
              "a note that does not name the install is not an explanation")
        check("the note gives the REASON", "utomation" in note,
              "note={0!r}".format(note[:80]))

        # (b) nothing installed -> silence, not a phantom diagnosis
        solvers._FFS_DIRS = (os.path.join(tmp, "nope"),)
        check("no bundle -> no note", solvers.fasthenry_status_note() == "")

        # (c) off Windows the bundle cannot exist -> silence
        solvers._FFS_DIRS = (tmp,)
        os.name = "posix"
        check("off Windows -> no note", solvers.fasthenry_status_note() == "")
    finally:
        os.name, solvers._FFS_DIRS = real_name, real_dirs
        try:
            os.remove(os.path.join(tmp, "FastHenry2.exe"))
            os.rmdir(tmp)
        except OSError:
            pass

    # --- the Windows hint -------------------------------------------------
    print(" windows hint:")
    hint = solvers.WINDOWS_HINTS["fasthenry"]
    check("hint explains the Automation limit", "utomation" in hint)
    # The Install button is gated below (and by smoke.py); this pins the
    # FALLBACK route. "source" alone would be satisfied by the provenance phrase
    # "the exact source it was compiled from", so require the build verb too.
    check("hint offers a fallback route that actually works",
          "WSL2" in hint or "wsl2" in hint
          or ("source build" in hint and "make" in hint))
    # The exact wrong instruction that shipped, pinned so it cannot return.
    check("hint no longer sends users to a bundle fasthenry.exe",
          "point EMStudio at fasthenry.exe" not in hint)

    # --- the native-Windows source build ----------------------------------
    # The vendor binary can never work, so on Windows the ONLY route to a
    # usable FastHenry is compiling one. That recipe is four measured changes
    # (2026-08-13); each is pinned here because getting one wrong yields a
    # binary that builds and is subtly wrong, not a build that fails.
    print(" windows source build — flags:")
    win = solvers.FASTHENRY_WIN_CFLAGS
    check("windows flags DROP -DFOUR", "-DFOUR" not in win,
          "it pulls <sys/resource.h>, which mingw does not have")
    # Paired positively, so the check above cannot pass by the flag string
    # simply having been emptied or renamed.
    missing = [f for f in solvers.FASTHENRY_REQUIRED_FLAGS if f not in win]
    check("windows flags KEEP every required flag", not missing,
          "missing {0}".format(missing) if missing else win)
    check("windows flags are DERIVED from the POSIX set",
          win == " ".join(f for f in solvers.FASTHENRY_CFLAGS.split()
                          if f != "-DFOUR"),
          "a second hand-written flag list cannot be gated — see "
          "FASTHENRY_CFLAGS on why this is one constant")

    print(" windows source build — patch discipline:")
    real_src = {
        "induct.c": "int matherr(exc)\nstruct exception *exc;\n{ return 0; }\n",
        "parse_command_line.c": "void f(void)\n{\n  long clock;\n  time(&clock);\n}\n",
        "Makefile": solvers.FASTHENRY_WIN_MAKE_ANCHOR + "\n\nfasthenry:\n\techo hi\n",
    }

    def _tree(files):
        d = tempfile.mkdtemp(prefix="fhsrc_")
        for name, body in files.items():
            with open(os.path.join(d, name), "w", encoding="latin-1") as fh:
                fh.write(body)
        return d

    d1 = _tree(real_src)
    try:
        solvers.prepare_fasthenry_win_source(d1)
        got = {n: open(os.path.join(d1, n), encoding="latin-1").read()
               for n in ("induct.c", "parse_command_line.c", "Makefile")}
        check("matherr renamed out of mingw's way",
              "fh_unused_matherr" in got["induct.c"]
              and "int matherr(exc)" not in got["induct.c"])
        check("long clock -> time_t clock (the LLP64 bug)",
              "time_t clock;" in got["parse_command_line.c"]
              and "long clock;" not in got["parse_command_line.c"])
        check("shim linked via NONUNIOBJS", "win_compat.o" in got["Makefile"])
        check("shim source written",
              os.path.isfile(os.path.join(d1, "win_compat.c")))
        # Running twice must not double-patch or throw.
        solvers.prepare_fasthenry_win_source(d1)
        again = open(os.path.join(d1, "Makefile"), encoding="latin-1").read()
        check("re-running is idempotent", again.count("win_compat.o") == 1,
              "a wizard retry must resume, not corrupt the tree")
    finally:
        shutil.rmtree(d1, ignore_errors=True)

    # THE LOAD-BEARING ONE: an anchor that no longer matches exactly once must
    # STOP the build. A patch applied to the wrong line compiles.
    moved = dict(real_src)
    moved["induct.c"] = real_src["induct.c"] + "\nint matherr(exc)\n"
    d2 = _tree(moved)
    try:
        raised = False
        try:
            solvers.prepare_fasthenry_win_source(d2)
        except SolverError:
            raised = True
        check("a duplicated anchor REFUSES to patch", raised,
              "upstream moving the line must fail loudly, not patch blind")
    finally:
        shutil.rmtree(d2, ignore_errors=True)

    d3 = _tree({k: v for k, v in real_src.items() if k != "Makefile"})
    try:
        raised = False
        try:
            solvers.prepare_fasthenry_win_source(d3)
        except SolverError:
            raised = True
        check("a missing Makefile REFUSES", raised)
    finally:
        shutil.rmtree(d3, ignore_errors=True)

    # --- the LIVE self-hosted install plan ----------------------------------
    # Redistribution was unblocked 2026-08-13/19 (vendor grant) and the 2003
    # M.I.T. re-release was confirmed accurate by M.I.T.'s Technology
    # Licensing Office on 2026-09-15 (record: docs/launch/
    # fasthenry-2003-licence-resolution.md). The plan sat STAGED outside
    # WIN_INSTALL_PLANS until that confirmation; it is LIVE now, and these
    # checks keep it honest: self-hosted, managed layout, source offer on the
    # same tag, a real pin, and membership in the live table (the "staged"
    # check this replaced asserted the opposite — flipped on activation, as
    # the checklist said).
    print(" live install plan:")
    plan = solvers.WIN_INSTALL_PLANS.get("fasthenry", {})
    check("Install plan is LIVE (member of WIN_INSTALL_PLANS)",
          "fasthenry" in solvers.WIN_INSTALL_PLANS,
          "the TLO confirmed 2026-09-15; the button ships — a missing entry "
          "here is a regression, not a hold")
    check("live plan is complete",
          bool(plan.get("url")) and bool(plan.get("estimate"))
          and bool(plan.get("proof")))
    check("live plan is SELF-hosted",
          plan.get("url", "").startswith(solvers.SELF_HOSTED_PREFIX),
          "we are the distributor; an upstream URL here would be a lie")
    check("proof is the managed-layout binary",
          plan.get("proof") == os.path.join("bin", "fasthenry.exe"),
          "detection probes <root>/fasthenry/bin — a flat zip would install "
          "somewhere detection never looks")
    offer = plan.get("source_offer", "")
    bin_tag = solvers._release_tag(plan.get("url", ""))
    src_tag = solvers._release_tag(offer)
    check("source offer rides the SAME release tag",
          offer.startswith("https://") and bin_tag and bin_tag == src_tag,
          "binary tag {0!r} vs source tag {1!r}".format(bin_tag, src_tag))
    sha = plan.get("sha256", "")
    check("sha256 pin is a real digest",
          len(sha) == 64 and all(c in "0123456789abcdef" for c in sha.lower()),
          "sha256={0!r}".format(sha[:20]))
    check("the Windows hint tells the user about the button",
          "Install button" in solvers.WINDOWS_HINTS.get("fasthenry", ""),
          "a backend that HAS a button must say so where the user looks")
    # The dist tool and the live plan must agree on tag and zip name, or the
    # uploaded asset and the pinned URL drift apart. The tool is Pro-repo
    # only — but in the PRO repo (identified by the exporter's presence) its
    # absence must FAIL, not skip: a silent skip is exactly how a rename
    # would disarm these drift guards.
    tool_path = os.path.join(_ROOT, "tools", "build_fasthenry_dist.py")
    if os.path.isfile(os.path.join(_ROOT, "tools", "export_free.py")):
        check("the dist tool exists in the Pro repo",
              os.path.isfile(tool_path),
              "renaming tools/build_fasthenry_dist.py silently disarms the "
              "tag/zip-name drift guards below")
    if os.path.isfile(tool_path):
        sys.path.insert(0, os.path.dirname(tool_path))
        try:
            import build_fasthenry_dist as _bfd
            check("dist tool and live plan agree on the release tag",
                  bin_tag == _bfd.RELEASE_TAG,
                  "plan {0!r} vs tool {1!r}".format(bin_tag, _bfd.RELEASE_TAG))
            check("dist tool and live plan agree on the zip name",
                  plan.get("url", "").endswith("/" + _bfd.BIN_ZIP))
            # ⚠ THE SOURCE OFFER IS THE THING THAT GOES STALE SILENTLY. The
            # builder used to download the MOVING branch ref, so a rebuild
            # under the same release tag would compile a different tree and
            # name its source zip after a different commit, while the shipped
            # plan kept offering the old filename — a binary whose
            # "corresponding source" no longer corresponds, which is the one
            # thing the licence obligation actually requires. Pinned
            # 2026-09-23; the checks below are what keep the pin, the fetch
            # and the published offer from drifting apart unnoticed.
            check("dist tool's pinned commit matches the published "
                  "source_offer filename",
                  plan.get("source_offer", "").endswith(
                      "/fasthenry-source-{0}.zip".format(_bfd.SRC_COMMIT[:7])),
                  "source_offer {0!r} vs tool pin {1}".format(
                      plan.get("source_offer", ""), _bfd.SRC_COMMIT))
            # ⚠ CHECK THE CALL, NOT THE CONSTANT. The first version of this
            # check read _bfd.SRC_URL — and with the REAL pre-patch line put
            # back (download_source() fetching solvers.FASTHENRY_WIN_SRC_URL,
            # the moving ref) it stayed green while the tool fetched master
            # and PROVENANCE printed the pinned URL it never used. Measured
            # 2026-09-24 by an adversarial review; the earlier negative
            # control had only edited the constant, a regression that never
            # existed. So drive download_source() itself with the network
            # swapped for a recorder, and read what it actually REQUESTED.
            # Offline and platform-neutral: the recorder writes a tiny zip
            # carrying a GitHub-style archive comment (the commit id).
            import zipfile as _zf
            requested = []
            recorded = [_bfd.SRC_COMMIT]

            def _fake_download(url, dest, say):
                requested.append(url)
                with _zf.ZipFile(dest, "w") as z:
                    z.writestr("FastHenry2-fixture/README", "fixture")
                    z.comment = recorded[0].encode("ascii")

            real_dl, real_out = solvers._download_archive, _bfd.OUT_DIR
            scratch = tempfile.mkdtemp(prefix="fh_pin_gate_")
            try:
                solvers._download_archive = _fake_download
                _bfd.OUT_DIR = scratch
                _zip, got = _bfd.download_source()
                check("the builder FETCHES the pinned commit, not a moving "
                      "branch ref",
                      requested == [_bfd.SRC_URL]
                      and _bfd.SRC_COMMIT in requested[0]
                      and "refs/heads" not in requested[0]
                      and got == _bfd.SRC_COMMIT,
                      "requested {0}, recorded commit {1}".format(
                          requested, got))
                # The gate's own negative control, run every time: an archive
                # that records a DIFFERENT commit must be refused, never
                # published under the pinned id.
                recorded[0] = "0" * 40
                try:
                    _bfd.download_source()
                    refused = ""
                except SystemExit as exc:
                    refused = str(exc)
                check("an archive recording a different commit is REFUSED",
                      "does not match the pin" in refused,
                      refused or "download_source() returned normally")
                # ...and so is one recording NO commit. It used to be handed
                # the pin, putting an id nobody read into PROVENANCE and the
                # source zip's name (owner ruling 2026-09-24: refuse).
                recorded[0] = ""
                try:
                    _bfd.download_source()
                    refused = ""
                except SystemExit as exc:
                    refused = str(exc)
                check("an archive recording NO commit is REFUSED, not given "
                      "the pin",
                      "records no commit" in refused,
                      refused or "download_source() returned normally")
                # The naming step guards itself too, so a future caller that
                # skips download_source() cannot put an unread id into the
                # published filename. The guard fires before any argument is
                # touched, so placeholders are enough. ⚠ THREE bad values, not
                # one: the first version tried only "", and a guard weakened to
                # `if not commit` stayed green (review 2026-09-24). A wrong
                # full sha and the bare 7-char short id must refuse too.
                let_through = []
                for bad in ("", "0" * 40, _bfd.SRC_COMMIT[:7]):
                    try:
                        _bfd.build_source_zip(scratch, bad, "", "")
                        let_through.append(bad or "(empty)")
                    except SystemExit as exc:
                        if "not the pin" not in str(exc):
                            let_through.append("{0!r}: {1}".format(bad, exc))
                check("the source-zip naming step REFUSES every commit but the "
                      "pin (empty, a wrong sha, the bare short id)",
                      not let_through,
                      "let through: {0}".format(let_through))

                # ⚠ The builder must refuse the tag the SHIPPED plan pins:
                # rebuilt zips never hash the same, and every install pins
                # the binary's sha256, so a same-tag upload breaks Install…
                # everywhere. main() is driven for real; the download is
                # swapped for a tripwire so that, on a Windows box with the
                # refusal removed, the gate stops at the fetch instead of
                # building. On Linux a removed refusal shows up as the
                # "Windows-only" message instead — either way, not the refusal.
                class _Reached(Exception):
                    pass

                def _tripwire(url, dest, say):
                    raise _Reached(url)

                solvers._download_archive = _tripwire
                try:
                    _bfd.main([])
                    outcome = "main() returned normally"
                except SystemExit as exc:
                    outcome = str(exc)
                except _Reached as exc:
                    outcome = "main() went on to DOWNLOAD " + str(exc)
                check("the builder REFUSES to build for a tag that has "
                      "already shipped",
                      "has already SHIPPED" in outcome, outcome)

                # refuse_live_tag() probed directly under controlled
                # conditions. Each probe restores the tool tag and the plan.
                def _probe(tool_tag, plan_url=None):
                    saved_tag = _bfd.RELEASE_TAG
                    saved_plan = solvers.WIN_INSTALL_PLANS.get("fasthenry")
                    try:
                        _bfd.RELEASE_TAG = tool_tag
                        if plan_url is not None:
                            solvers.WIN_INSTALL_PLANS["fasthenry"] = dict(
                                saved_plan, url=plan_url)
                        _bfd.refuse_live_tag()
                        return ""
                    except SystemExit as exc:
                        return str(exc)
                    finally:
                        _bfd.RELEASE_TAG = saved_tag
                        solvers.WIN_INSTALL_PLANS["fasthenry"] = saved_plan

                fresh = "fasthenry-gate-probe-never-shipped"
                # Positive control: without it, a stub that refuses EVERY tag
                # would pass the check above (review 2026-09-24).
                got = _probe(fresh)
                check("...and does NOT refuse a genuinely new tag",
                      got == "", got or "returned normally")
                # Fails CLOSED: an unreadable plan tag must not wave a build
                # through — the first version returned quietly here.
                got = _probe(fresh, plan_url="")
                check("an unreadable shipped-plan tag REFUSES (fails closed)",
                      "cannot read the shipped plan" in got,
                      got or "refuse_live_tag() returned normally")
                # Retired tags stay protected: once the plan moves on, the old
                # tag is still pinned by every install that shipped with it.
                moved = plan.get("url", "").replace(
                    "/" + bin_tag + "/", "/" + fresh + "-next/")
                got = _probe(_bfd.PUBLISHED_TAGS[0], plan_url=moved)
                check("a RETIRED shipped tag stays refused after the plan "
                      "moves on",
                      "has already SHIPPED" in got,
                      got or "refuse_live_tag() returned normally")
                check("PUBLISHED_TAGS records the live plan's tag",
                      bin_tag in _bfd.PUBLISHED_TAGS,
                      "live {0!r} vs {1!r} — a release that moved the plan "
                      "must append its tag".format(bin_tag,
                                                   _bfd.PUBLISHED_TAGS))

                # ⚠ THE BINARY SIDE OF THE PIN (2026-09-25). Everything above
                # proves the builder FETCHES the pinned commit; nothing proved
                # the binary is COMPILED from that download. main() hands
                # download_source()'s archive to build_binary(), which must
                # pass it on as run_fasthenry_win_build(src_zip=...), which
                # must extract THAT archive and never download. True today,
                # but it is two hops into solvers.py — the SHIPPING Build…
                # path — and a refactor there that dropped src_zip would
                # compile a fresh fetch of the MOVING ref under a provenance
                # claim naming the pinned commit, with every check above
                # still green. Driven for real under a faked Windows: the
                # compiler lookup and install root are stubbed, the download
                # is the tripwire above, and the fixture archive has no
                # induct.c, so the build stops just AFTER extraction — past
                # the point where a download would have happened.
                fixture = os.path.join(scratch, "fh-src-fixture.zip")
                with _zf.ZipFile(fixture, "w") as z:
                    z.writestr("FastHenry2-fixture/README", "no induct.c here")
                said = []

                def _drive(build, dl=None):
                    saved = (os.name, solvers.win_build_toolchain,
                             solvers.win_install_root, _bfd.say)
                    solvers._download_archive = dl or _tripwire
                    solvers.win_build_toolchain = (
                        lambda: ("cc-stub.exe", "make-stub.exe"))
                    solvers.win_install_root = (
                        lambda: os.path.join(scratch, "winroot"))
                    _bfd.say = said.append
                    os.name = "nt"
                    try:
                        build()
                        return "returned normally"
                    except _Reached as exc:
                        return "went on to DOWNLOAD " + str(exc)
                    except SystemExit as exc:   # fail(): a named FAIL, not an abort
                        return "exited: {0}".format(exc)
                    except Exception as exc:    # SolverError is the expected stop
                        return "stopped: {0}".format(exc)
                    finally:
                        (os.name, solvers.win_build_toolchain,
                         solvers.win_install_root, _bfd.say) = saved

                out = _drive(lambda: _bfd.build_binary(fixture))
                check("the builder COMPILES its pinned download: "
                      "build_binary() hands the archive to the shipping build "
                      "path, and nothing is fetched",
                      "DOWNLOAD" not in out and "induct.c" in out
                      and ("using provided source archive " + fixture) in said,
                      out)
                # ...and the FIRST hop, main() → build_binary(): driven for
                # real on a never-shipped tag with the network swapped for the
                # recorder. Exactly ONE download — the pinned one — and that
                # archive is the one compiled. A refactor to build_binary(None)
                # used to stay green (review 2026-09-25): the build would then
                # fetch the MOVING ref a second time and be recorded here.
                requested[:] = []
                recorded[0] = _bfd.SRC_COMMIT
                said[:] = []
                saved_tag, _bfd.RELEASE_TAG = _bfd.RELEASE_TAG, fresh
                try:
                    out = _drive(lambda: _bfd.main([]), dl=_fake_download)
                finally:
                    _bfd.RELEASE_TAG = saved_tag
                check("...and main() hands download_source()'s archive to "
                      "build_binary() (one download, the pinned one, compiled)",
                      requested == [_bfd.SRC_URL]
                      and any(line.startswith("using provided source archive ")
                              for line in said)
                      and "induct.c" in out,
                      "requested {0}; {1}".format(requested, out))
                # POSITIVE control: the same build given NO archive must
                # reach the download — otherwise a build path that never
                # downloads anything at all would pass the check above.
                said[:] = []
                out = _drive(lambda: solvers.run_fasthenry_win_build(
                    line_callback=said.append))
                check("...and the same build WITHOUT an archive does reach "
                      "the download (the tripwire is live)",
                      out == "went on to DOWNLOAD "
                      + solvers.FASTHENRY_WIN_SRC_URL, out)
            finally:
                solvers._download_archive = real_dl
                _bfd.OUT_DIR = real_out
                shutil.rmtree(scratch, ignore_errors=True)
            # The tool must be DENIED, not merely left out of the include list
            # — a future "tools/**" include glob would silently publish it.
            # Asked of the EXPORTER's own loader and matcher, not a second
            # copy of the rule: a re-implemented matcher is an assumption
            # that can drift from what the export actually does.
            # ⚠ Asked of plan() — the function the export RUNS — over the
            # real tracked-file list. The first version called _matches()
            # plus _is_exported(), whose second half merely followed from the
            # first and never touched plan() (review 2026-09-24).
            import export_free as _ef
            _man = _ef._load_manifest(_ef.MANIFEST)
            _rel = "tools/build_fasthenry_dist.py"
            _chosen, _denied, _skipped = _ef.plan(_man, _ef._tracked_files())
            _by = dict(_denied).get(_rel)
            check("the free manifest explicitly DENIES the dist tool "
                  "(the exporter's own plan())",
                  bool(_by) and _rel not in _chosen,
                  "denied by {0!r}".format(_by) if _by else
                  "plan() does not deny it — only an include omission, which "
                  "a future include glob would undo")
        finally:
            sys.path.remove(os.path.dirname(tool_path))
    else:
        # The FREE tree: the dist tool is manifest-DENIED on purpose (it
        # orchestrates the private repo's release; explicitly denied since
        # 2026-09-24, and the Pro branch above asserts it), so the drift
        # guards cannot run and say so — a silent absence would read as
        # coverage.
        print("  skip  dist-tool drift checks — tools/build_fasthenry_dist.py is "
              "Pro-repo only (manifest-denied in the free export)")

    # --- sha256 verification in run_win_install (real pipeline, faked nt) --
    # The live plan is the first pinned one, so the pin must actually bind:
    # a wrong hash refuses BEFORE extraction and leaves nothing behind.
    #
    # ⚠ This whole block used to sit behind `if os.name == "nt":` with no
    # else. Off Windows — which is CI, and every run on the box the gate is
    # developed on — SEVEN checks silently did not execute, nothing printed to
    # say so, and the gate still printed its PASS token. So os.name is FAKED
    # instead, exactly as gui_smoke does for the Windows Solver Setup dialog,
    # and the pinning contract is asserted on every platform. Faking the
    # platform means neutering the ambient sources that only exist off it;
    # each is spelled out at the point it is applied below.
    print(" download pinning (run_win_install, simulated Windows):")
    import dataclasses as _dc
    import zipfile as _zipfile

    tmp_root = tempfile.mkdtemp(prefix="fh_pin_")
    fake_zip = os.path.join(tmp_root, "fake.zip")
    with _zipfile.ZipFile(fake_zip, "w") as zf:
        zf.writestr("bin/fasthenry.exe", "@echo off\r\n")
    # ⚠ Computed INDEPENDENTLY of solvers._file_sha256 — an expectation
    # produced by the function under test is circular: swap its hashlib
    # algorithm and sha-vs-same-sha still matches, while in production
    # every pinned install would refuse forever against the published
    # 64-hex sha256 literal.
    import hashlib as _hashlib
    with open(fake_zip, "rb") as fh:
        good_sha = _hashlib.sha256(fh.read()).hexdigest()
    base_plan = {
        "estimate": "test",
        # pathlib builds the file:// form THIS platform's url2pathname
        # reads back. Hand-rolling "file:///" + the path was fine on
        # Windows (the path starts "C:") but yields FOUR slashes for a
        # POSIX path, whose reading is platform-dependent — not something
        # to leave to luck now that the block runs everywhere.
        "url": pathlib.Path(fake_zip).as_uri(),
        "proof": os.path.join("bin", "fasthenry.exe"),
    }
    orig_name = os.name
    orig_access = os.access
    orig_backend = solvers.BACKENDS["fasthenry"]
    orig_root = solvers.win_install_root
    orig_pref = solvers._pref_path
    orig_path = os.environ.get("PATH", "")
    orig_env = os.environ.pop("EMSTUDIO_FASTHENRY", None)
    try:
        managed = os.path.join(tmp_root, "managed")
        os.name = "nt"
        # Windows' os.access IGNORES X_OK — every existing file answers
        # yes — while zipfile.extractall does NOT restore mode bits, so
        # on POSIX the extracted proof lands at 0644 and detection's
        # os.access(cand, X_OK) says no. The shim is that Windows rule
        # and nothing else: drop X_OK, pass every other mode through. On
        # real Windows it is the identity, so this is one code path.
        os.access = lambda _p, _m, *a, **kw: orig_access(
            _p, _m & ~os.X_OK, *a, **kw)
        # The fourth ambient source, and the one that bites at home:
        # extra_dirs is ~/opt/FastHenry2/bin, a REAL FastHenry on the
        # dev box, and it is probed AHEAD of the managed dir — so
        # "detection sees the managed install" would have been answered
        # by a binary this gate never installed. That path cannot exist
        # on Windows, where the tuple is inert, so emptying it here is
        # the Windows condition, not a weakened one.
        solvers.BACKENDS["fasthenry"] = _dc.replace(orig_backend,
                                                    extra_dirs=())
        solvers.win_install_root = lambda: managed
        solvers._pref_path = lambda _key: ""
        os.environ["PATH"] = ""

        # (a) correct pin, UPPERCASE on purpose: comparison must normalise.
        lines = []
        plan = dict(base_plan, sha256=good_sha.upper())
        info = solvers.run_win_install("fasthenry",
                                       line_callback=lines.append,
                                       _plan=plan)
        check("correct pin installs and detection sees it",
              info.found and info.path.startswith(managed),
              repr(info))
        check("the pin was actually checked",
              any("verifying sha256" in ln for ln in lines))
        # Positive anchor for the literal the wrong-pin ordering check
        # below matches against. Without this pairing, rewording
        # say("extracting...") turns that must-NOT-contain check vacuous
        # forever — the exact silent decay the gate conventions forbid.
        check("extraction is logged on the success path",
              any("extracting" in ln for ln in lines),
              "if this wording changes, update the ordering check below "
              "IN THE SAME COMMIT")
        shutil.rmtree(managed, ignore_errors=True)

        # (b) wrong pin refuses, BEFORE extraction, leaving nothing.
        bad = ("0" if good_sha[0] != "0" else "1") + good_sha[1:]
        lines = []
        raised = False
        try:
            solvers.run_win_install("fasthenry",
                                    line_callback=lines.append,
                                    _plan=dict(base_plan, sha256=bad))
        except SolverError:
            raised = True
        check("wrong pin REFUSES to install", raised,
              "a hash that does not bind is decoration")
        check("refusal happens BEFORE extraction",
              not any("extracting" in ln for ln in lines),
              "extraction is the first step that feeds untrusted bytes "
              "to code; verify-then-extract is the order that matters")
        check("refusal leaves no install behind",
              not os.path.isdir(os.path.join(managed, "fasthenry")))

        # (c) a plan WITHOUT a pin still installs — elmer/gmsh point at
        # upstream URLs whose bytes legitimately shift; pinning is opt-in.
        lines = []
        info = solvers.run_win_install("fasthenry",
                                       line_callback=lines.append,
                                       _plan=dict(base_plan))
        check("unpinned plans keep working", info.found, repr(info))
    finally:
        os.name = orig_name
        os.access = orig_access
        solvers.BACKENDS["fasthenry"] = orig_backend
        solvers.win_install_root = orig_root
        solvers._pref_path = orig_pref
        os.environ["PATH"] = orig_path
        if orig_env is not None:
            os.environ["EMSTUDIO_FASTHENRY"] = orig_env
        shutil.rmtree(tmp_root, ignore_errors=True)

    print(" windows source build — offer only what can run:")
    # ⚠ These three checks were written as `<real property> if os.name == "nt"
    # else True`. Off Windows the operand IS the literal True — a check whose
    # passing condition is a constant, which is not a check — and the third
    # was vacuous the same way (win_build_toolchain_note() returns "" for
    # everyone off Windows, so "with a compiler -> no complaint" asserted the
    # platform, not the compiler). os.name is faked for BOTH sides instead, so
    # each branch is asserted against a computed value on every platform.
    real_tc = solvers.win_build_toolchain
    real_name = os.name
    try:
        # Off Windows there is no native-Windows build at all; that route is
        # build_plan()'s bash recipe, and offering both would double the button.
        os.name = "posix"
        solvers.win_build_toolchain = lambda: ("cc.exe", "make.exe")
        check("off Windows -> no native-Windows build plan",
              solvers.win_source_build_plan("fasthenry") is None,
              "a toolchain is present in this branch, so None here is the "
              "PLATFORM answering, not a missing compiler")
        check("off Windows -> no toolchain complaint",
              solvers.win_build_toolchain_note() == "")

        os.name = "nt"
        solvers.win_build_toolchain = lambda: (None, None)
        check("no compiler -> no Build button",
              solvers.win_source_build_plan("fasthenry") is None,
              "an offered button that cannot run is worse than none")
        note = solvers.win_build_toolchain_note()
        check("no compiler -> the note says how to get one",
              "pacman" in note, note[:70])
        solvers.win_build_toolchain = lambda: ("cc.exe", "make.exe")
        # Paired positively: without this, deleting fasthenry from
        # WIN_SOURCE_BUILDS would leave "no compiler -> no Build button"
        # passing for the wrong reason, forever.
        check("with a compiler -> the Build plan IS offered",
              solvers.win_source_build_plan("fasthenry") is not None,
              "the recipe must survive in WIN_SOURCE_BUILDS")
        check("with a compiler -> no complaint",
              solvers.win_build_toolchain_note() == "")
    finally:
        solvers.win_build_toolchain = real_tc
        os.name = real_name

    print("")
    if FAILURES:
        print("FAILED {0} check(s): {1}".format(
            len(FAILURES), "; ".join(FAILURES[:5])))
        return 1
    print("FASTHENRY-GUIDANCE GATE PASSED")
    return 0


_UNDER_PYTEST = "pytest" in sys.modules
_UNDER_FREECAD = "FreeCAD" in sys.modules
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        raise SystemExit("validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("fasthenry-guidance validation failed")
    sys.exit(0)
