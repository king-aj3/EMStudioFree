# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: a material's LOSS reaches the solver, and gain is gain.

This gate exists because of four defects found together on 2026-08-22, all of
which produced numbers that were wrong in the OPTIMISTIC direction — the one
direction a simulation tool cannot afford to be wrong in:

1. **openEMS reported DIRECTIVITY as GAIN.** The deck wrote ``ff.Dmax`` into a
   column headed ``gain_dbi`` and ``emstudio/post/farfield.py`` documented that
   column as gain. They differ by the radiation efficiency, and this writer
   emits lossy dielectrics. Measured on the shipped patch: D 6.6350 dBi,
   eta 96.24 %, so the published figure overstated gain by **0.166 dB**.
2. **NEC2 silently DROPPED "Conductor" geometry.** ``_iter_material_edges``
   skipped every category that did not start with "Metal", so a user who chose
   Conductor and typed sigma got a deck with no wires from that material — not
   a lossless answer, an absent structure, reported as a result.
3. **NEC2 reported 100.00 % efficiency for every antenna**, because no ``LD``
   card was ever emitted.
4. **openEMS discarded sigma**, folding Conductor into ``AddMetal``.

⛳ **The shape worth remembering: a settable field that changes nothing.** In
every one of the four, the UI offered the user a choice, accepted their number,
and then threw it away somewhere the user could not see. That is worse than not
offering the choice, because the result looks computed.

**What is asserted, and why each:**

* The material LIBRARY is physically sane — no conductor beats silver, no
  permittivity below vacuum, PEC carries no sigma. A library of wrong constants
  would be this defect class all over again, one level up.
* ``apply_preset`` actually applies, and CLEARS stale values on EVERY hop —
  to PEC and to a DIELECTRIC alike. A half-applied preset leaves a copper
  sigma on an FR-4 substrate, and openEMS writes that straight into the deck
  as ``kappa=5.8e7`` (a ferromagnetic source leaves ``mue=500``), so the user
  gets a conducting substrate while the property editor shows a correct eps_r.
* PEC emits no LD card and no conducting sheet, so **every deck written before
  this change is reproduced byte-for-byte**. A correctness fix that also
  silently changed existing results would be its own incident.
* With FreeCAD present, the emitted DECKS are read back: a Conductor wire
  produces both GW geometry and its LD card; a Conductor sheet produces
  ``AddConductingSheet``; a Conductor SOLID falls back to PEC and says so.

Run:  python3 tests/validation/material_loss.py                      (library + preset)
      freecadcmd tests/run_gate.py tests/validation/material_loss.py  (adds the decks)

⚠ **Use ``tests/run_gate.py`` for the FreeCAD run, not this file directly.**
Until 2026-08-29 the line above said ``freecadcmd tests/validation/material_loss.py``
and that command did **nothing at all, in silence, and exited 0**: freecadcmd sets
``__name__`` to the script basename, so the ``if __name__ == "__main__"`` guard
never fired and ``main()`` was never called. The deck half is covered by nothing
BUT a by-hand freecadcmd run (it is a FAST-tier gate; CI runs it under python3),
so the one command documented to exercise it was testing nothing — the same
"settable field that changes nothing" shape this gate exists to catch, one level
up. The guard below now also fires when FreeCAD is in ``sys.modules``, and
``run_gate.py`` additionally routes ``print`` into ``FreeCAD.Console`` (which
survives freecadcmd's exit, exactly once) so the verdict is visible rather than
inferred from an exit code.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

_UNDER_PYTEST = "pytest" in sys.modules
#: True when FreeCAD is running this file (freecadcmd, or the GUI console) —
#: the invocation that REQUESTS the deck half. Captured at import time, before
#: anything below imports FreeCAD itself: probed later it would find the module
#: this gate just loaded and answer "yes" even under plain python3.
_UNDER_FREECAD = "FreeCAD" in sys.modules

#: Conductivity of annealed copper, the 100 % IACS reference. Nothing in the
#: library may claim to conduct better than silver, and silver is the best
#: elemental conductor there is — a sanity ceiling, not a style rule.
SIGMA_SILVER = 6.30e7


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


class _Stub(object):
    """Enough of a FreeCAD object for apply_preset: it only sets attributes."""


def check_library():
    from emstudio.objects import material_library as M

    lib = M.MATERIAL_LIBRARY
    check("library is non-trivial", len(lib) >= 20, "%d materials" % len(lib))
    check("PEC is present and is the default preset",
          M.PEC_PRESET in lib and M.PRESETS[0] == M.PEC_PRESET, M.PRESETS[0])
    check("Custom is offered as the escape hatch", "Custom" in M.PRESETS)
    check("Custom is NOT a library entry (it must not overwrite anything)",
          "Custom" not in lib)

    bad = []
    for name, e in sorted(lib.items()):
        cat = e.get("category")
        if cat == "Metal (PEC)":
            # ⛳ PEC with a conductivity would be a contradiction in terms, and
            # would hand a writer a number it must not act on.
            if "sigma_s_m" in e:
                bad.append(name + ": PEC carries sigma")
        elif cat == "Conductor":
            s = e.get("sigma_s_m", 0.0)
            if not (0.0 < s <= SIGMA_SILVER):
                bad.append("%s: sigma %g outside (0, silver]" % (name, s))
            if e.get("mu_r", 1.0) < 1.0:
                bad.append("%s: mu_r < 1" % name)
            if e.get("alpha_per_k", 0.0) < 0.0:
                bad.append("%s: negative temperature coefficient" % name)
        elif cat == "Dielectric":
            if e.get("eps_r", 0.0) < 1.0:
                bad.append("%s: eps_r < 1 (below vacuum)" % name)
            if not (0.0 <= e.get("tan_d", 0.0) < 1.0):
                bad.append("%s: tan_d outside [0, 1)" % name)
        else:
            bad.append("%s: unknown category %r" % (name, cat))
    check("every library entry is physically sane", not bad,
          "; ".join(bad[:3]))

    # the two the docs quote, pinned by value
    cu = lib["Copper (annealed, 100% IACS)"]
    check("copper is 5.8e7 S/m", abs(cu["sigma_s_m"] - 5.80e7) < 1e5,
          "%g" % cu["sigma_s_m"])
    fr4 = lib["FR-4 (typical)"]
    check("FR-4 is eps_r 4.4 / tan_d 0.02",
          abs(fr4["eps_r"] - 4.4) < 1e-9 and abs(fr4["tan_d"] - 0.02) < 1e-9)


def check_presets():
    from emstudio.objects import material_library as M

    o = _Stub()
    ok = M.apply_preset(o, "Copper (annealed, 100% IACS)")
    check("applying copper returns True", ok is True)
    check("copper sets Category=Conductor", o.Category == "Conductor",
          str(getattr(o, "Category", None)))
    check("copper sets sigma 5.8e7", abs(o.Conductivity - 5.80e7) < 1e5,
          "%g" % o.Conductivity)

    M.apply_preset(o, "FR-4 (typical)")
    check("FR-4 sets Category=Dielectric", o.Category == "Dielectric")
    check("FR-4 sets eps_r 4.4", abs(o.RelPermittivity - 4.4) < 1e-9)

    # ⚠ THE SAME BITE, ON THE HOP THIS GATE WALKED PAST UNTIL 2026-08-29. The
    # three lines above SET UP a stale copper sigma on a dielectric and then
    # never looked at it, so the gate written to prevent a half-applied preset
    # stepped over one. It is not cosmetic: the openEMS writer reads
    # ``Conductivity`` and ``RelPermeability`` off a DIELECTRIC material
    # (openems/writer.py `entry["kappa"]` / `entry["mu"]`) and emits them as
    # ``kappa=`` / ``mue=``, so the substrate is modelled as metal while the
    # property editor shows the eps_r the user chose. Clearing must happen on
    # the way INTO a category, not only on the way back to PEC.
    check("FR-4 clears the stale copper sigma", o.Conductivity == 0.0,
          "%g" % o.Conductivity)
    check("FR-4 clears the stale temperature coefficient",
          o.ConductivityTempCoeff == 0.0, "%g" % o.ConductivityTempCoeff)

    # mu_r needs a FERROMAGNETIC source to be a real check — copper's mu_r is
    # 1.0, so asserting it on the hop above would pass by construction and
    # prove nothing. Steel 1018 -> PTFE is the pair that reaches the deck as
    # `AddMaterial(..., epsilon=2.1, kappa=6.99e6, mue=500)`.
    o2 = _Stub()
    M.apply_preset(o2, "Steel, mild 1018 (ferromagnetic)")
    check("steel 1018 sets mu_r 500 (the stale value to be cleared)",
          o2.RelPermeability == 500.0, "%g" % o2.RelPermeability)
    M.apply_preset(o2, "PTFE (Teflon)")
    check("a dielectric clears a stale mu_r", o2.RelPermeability == 1.0,
          "%g" % o2.RelPermeability)
    check("a dielectric clears a stale sigma", o2.Conductivity == 0.0,
          "%g" % o2.Conductivity)

    # ⚠ THE ONE THAT BITES. Switching back to PEC must CLEAR sigma; otherwise a
    # material that was briefly copper stays lossy to every writer while its
    # category says PEC, and the user has no way to see it.
    M.apply_preset(o, M.PEC_PRESET)
    check("PEC clears a stale sigma", o.Conductivity == 0.0,
          "%g" % o.Conductivity)
    check("PEC clears a stale mu_r", o.RelPermeability == 1.0)
    # ...and the FR-4 hop above left an eps_r 4.4 sitting on it. palace/model.py
    # reads RelPermittivity/LossTangent whatever the Category says, so "PEC"
    # meant a 4.4 dielectric there — the same half-applied preset, on the one
    # hop this gate did check, in the two fields it did not.
    check("PEC clears a stale eps_r", o.RelPermittivity == 1.0,
          "%g" % o.RelPermittivity)
    check("PEC clears a stale tan_d", o.LossTangent == 0.0,
          "%g" % o.LossTangent)

    check("an unknown preset is refused, not guessed",
          M.apply_preset(o, "Unobtainium") is False)


def _freecad_geometry_available():
    """Can the deck half run here at all? ``ImportError`` ONLY — nothing else.

    ⚠ This replaces a bare ``except Exception`` that wrapped the deck half's
    imports and printed the single word "skip" for ANY failure. That shape
    makes a genuine regression — a writer that raises at import, a renamed
    FreeCAD API, a broken Part module — indistinguishable from "this is plain
    python3, there is no FreeCAD here", and the gate printed PASSED for both.
    Only the backend being ABSENT may be absorbed; every other exception must
    escape and fail the gate.
    """
    try:
        import FreeCAD  # noqa: F401
        import Part     # noqa: F401
    except ImportError:
        return False
    return True


def check_openems_decks():
    """openEMS half of the deck read-back: a SHEET carries sigma, a SOLID does not.

    ⚠ Until 2026-08-29 the docstring at the top of this file claimed both of
    these were read back and NOTHING checked either: ``check_decks`` imported
    only the NEC2 writer, so ``grep -rn AddConductingSheet tests/`` matched the
    SENTENCE claiming coverage and nothing else. Both openEMS halves of the
    2026-08-22 finite-conductivity fix — the sheet that carries the user's
    sigma, and the loud fallback when a SOLID cannot — were live and ungated
    while the gate that exists for exactly that defect reported them green.
    That is this gate's own headline shape (a settable field that changes
    nothing) one level up, in the gate itself.
    """
    import shutil
    import tempfile

    import FreeCAD

    from emstudio.solvers.openems import writer as ems_writer
    from emstudio.templates import patch as patch_tpl

    # The SHIPPED tutorial patch, not invented geometry: its metal is two
    # zero-thickness SHEETS (patch + ground) and its substrate is a genuine
    # Part::Box SOLID, so one document exercises both branches of
    # ``_collect_materials``/the emitter exactly as a user's model would.
    workdir = tempfile.mkdtemp(prefix="emstudio_matloss_ems_")
    doc = FreeCAD.newDocument("matloss_ems")
    try:
        ana = patch_tpl.makePatch(doc)
        solver = [o for o in ana.Group
                  if "SolverOpenEMS" in str(getattr(o, "EMStudioType", ""))][0]
        mats = [o for o in ana.Group
                if "Material" in str(getattr(o, "EMStudioType", ""))]
        m_sheet = [m for m in mats if str(m.Category).startswith("Metal")][0]
        m_solid = [m for m in mats if str(m.Category).startswith("Dielectric")][0]

        def deck():
            doc.recompute()
            path, _z0, _nr = ems_writer.write_deck(ana, solver, workdir)
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()

        # PEC first — the historic deck, which must be free of BOTH new
        # emissions. Same reason as the NEC2 "no LD card" check above: a
        # correctness fix that also moved existing results is its own incident.
        pec = deck()
        check("a PEC material emits AddMetal and NO conducting sheet",
              "AddConductingSheet" not in pec and "CSX.AddMetal(" in pec,
              "%d sheet line(s)" % pec.count("AddConductingSheet"))

        # (4) the discarded-sigma regression: a Conductor SHEET must carry it.
        m_sheet.Preset = "Copper (annealed, 100% IACS)"
        cu = deck()
        sheets = [l for l in cu.splitlines() if "AddConductingSheet(" in l]
        check("a Conductor sheet emits AddConductingSheet",
              len(sheets) == 1, "; ".join(sheets) or "no sheet property")
        # Read the thickness back off the OBJECT rather than pinning a literal:
        # the deck must reproduce the property the user can edit, so the check
        # cannot rot if the 1 oz default ever moves.
        th_m = float(m_sheet.SheetThickness.getValueAs("m"))
        check("...carrying the user's sigma and the sheet thickness",
              bool(sheets) and "conductivity=58000000" in sheets[0]
              and "thickness={0:.9g}".format(th_m) in sheets[0],
              "%s [SheetThickness %.9g m]" % ("; ".join(sheets), th_m))
        check("a Conductor SHEET is not mistaken for a solid",
              "is a SOLID" not in cu)

        # ...and a Conductor SOLID must fall back LOUDLY. CSPropConductingSheet
        # is documented "only 2D primitives", so the writer reverts to PEC —
        # which is LOSSLESS, i.e. wrong in the optimistic direction. A silent
        # fallback would BE the defect this gate exists for, so the warning is
        # part of the contract and is asserted, not just the AddMetal call.
        m_solid.Preset = "Copper (annealed, 100% IACS)"
        solid = deck()
        warn = [l for l in solid.splitlines() if "is a SOLID" in l]
        check("a Conductor SOLID says so in the deck", len(warn) == 1,
              "; ".join(w.strip()[:70] for w in warn) or "no warning printed")
        name = ""
        if warn:
            # `print('EMStudio: WARNING - material NAME is a SOLID; ...')`
            name = warn[0].split("material ", 1)[-1].split(" is a SOLID", 1)[0]
        check("...and that material falls back to AddMetal, never to a sheet",
              bool(name)
              and "{0} = CSX.AddMetal('{0}')".format(name) in solid
              and "AddConductingSheet('{0}'".format(name) not in solid,
              name or "no material name in the warning")
    finally:
        FreeCAD.closeDocument(doc.Name)
        shutil.rmtree(workdir, ignore_errors=True)


def check_decks():
    """Deck-level half: needs FreeCAD. Call only when it is importable.

    Returns True when the deck half ran to completion (individual check
    results land in FAILURES as usual). Anything that stops it raises — the
    caller must never be able to mistake "could not run" for "ran and was
    happy".
    """
    import FreeCAD
    import Part

    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.solvers.nec2 import writer as nec_writer
    from emstudio.solvers import base as _base  # noqa: F401

    doc = FreeCAD.newDocument("matloss")
    ana = analysis_mod.makeAnalysis(doc)
    ana.FrequencyStart = "10 MHz"
    ana.FrequencyStop = "10 MHz"
    ana.FrequencyPoints = 1

    wire = doc.addObject("Part::Feature", "W")
    wire.Shape = Part.makeLine(FreeCAD.Vector(0, 0, -5000),
                               FreeCAD.Vector(0, 0, 5000))
    mat = material_mod.makeMaterial(doc, ana, name="Cu")
    mat.Preset = "Copper (annealed, 100% IACS)"
    mat.References = [(wire, "")]
    port = ports_mod.makeLumpedPort(doc, ana, name="P", direction="+Z")
    port.References = [(wire, "Edge1")]
    doc.recompute()

    from emstudio.objects import solver_objs
    solver = solver_objs.makeSolverNEC2(doc, ana)
    doc.recompute()

    path = os.path.join(FreeCAD.ActiveDocument.TransientDir, "t.nec")
    nec_writer.write_nec(ana, solver, path)
    with open(path, "r", encoding="utf-8") as fh:
        deck = fh.read()

    # (2) the geometry-drop regression: a Conductor MUST still make wires.
    n_gw = sum(1 for l in deck.splitlines() if l.startswith("GW "))
    check("a Conductor material still emits GW geometry",
          n_gw > 0, "%d GW card(s)" % n_gw)
    # (3) and it must carry its loss.
    ld = [l for l in deck.splitlines() if l.startswith("LD 5")]
    check("a Conductor material emits its LD 5 conductivity card",
          bool(ld), "; ".join(ld[:2]) or "no LD card")
    check("the LD card carries copper's sigma",
          any("5.8e+07" in l or "5.8e7" in l or "58000000" in l for l in ld),
          "; ".join(ld[:2]))

    # PEC must be byte-identical to the historic deck: no LD at all.
    mat.Preset = "Perfect conductor (PEC)"
    doc.recompute()
    nec_writer.write_nec(ana, solver, path)
    with open(path, "r", encoding="utf-8") as fh:
        pec_deck = fh.read()
    check("a PEC material emits NO LD card (historic decks unchanged)",
          "LD " not in pec_deck,
          "%d LD card(s)" % sum(1 for l in pec_deck.splitlines()
                                if l.startswith("LD ")))
    check("PEC still emits its geometry", "GW " in pec_deck)

    FreeCAD.closeDocument(doc.Name)

    # The other backend the 2026-08-22 fix touched. Called from here, not from
    # main(), so main()'s "the deck half ran to completion" contract still
    # covers BOTH writers with one answer — anything that stops it raises.
    check_openems_decks()
    return True


def main():
    print("== material loss reaches the solver, and gain is gain ==")
    check_library()
    check_presets()

    # ⚠ The deck half is selected BY THE INVOCATION, not by a flag: plain
    # python3 cannot import FreeCAD, freecadcmd always can. So an absent
    # FreeCAD under python3 skips a tier nobody asked for — honest, and the
    # summary says so. Under freecadcmd the deck half WAS requested, and not
    # running it is a FAILURE, not a skip. main() used to call check_decks()
    # and THROW ITS ANSWER AWAY, so both cases printed the same PASS line.
    deck_ran = False
    if _freecad_geometry_available():
        deck_ran = check_decks() is True
        if not deck_ran:
            # Cannot happen today (check_decks either completes or raises) and
            # is NOT printed as a passing check for exactly that reason — a
            # check that cannot fail is not a check. It exists so a future
            # early `return False` inside check_decks cannot slip past.
            check("the deck half ran to completion", False,
                  "check_decks() returned without completing")
    elif _UNDER_FREECAD:
        # Inside FreeCAD, and yet its geometry kernel will not import: a
        # broken install or a broken Part — never a reason to print a pass.
        check("FreeCAD geometry (Part) imports under freecadcmd", False,
              "the deck half was requested by this invocation and cannot run")
    else:
        print("  SKIPPED — deck half needs FreeCAD; run it with "
              "`freecadcmd tests/run_gate.py tests/validation/material_loss.py`")

    if FAILURES:
        print("MATERIAL LOSS GATE FAILED (%d): %s"
              % (len(FAILURES), "; ".join(FAILURES)))
        return 1
    if not deck_ran:
        # Still a pass — the library and preset halves really did run and
        # really did pass, and this gate is FAST-tiered so python3 is its
        # declared home. But the summary must never let a reader believe the
        # decks were read back when they were not.
        print("MATERIAL LOSS GATE PASSED (library + preset halves; "
              "DECK HALF SKIPPED — no FreeCAD in this interpreter)")
        return 0
    print("MATERIAL LOSS GATE PASSED (library + preset + deck halves)")
    return 0


# ⚠ freecadcmd sets __name__ to the script BASENAME, so `__name__ ==
# "__main__"` alone left main() uncalled: the documented FreeCAD invocation
# printed nothing and exited 0. The second clause is the house guard every
# other gate in this directory carries; _UNDER_PYTEST keeps an import-for-
# collection from running the whole gate as a side effect.
if (__name__ == "__main__") or (_UNDER_FREECAD and not _UNDER_PYTEST):
    # freecadcmd exits 0 on an uncaught exception (verified 2026-07-05), so
    # every failure is converted into SystemExit, which does carry a code.
    try:
        rc = main()
    except SystemExit:
        raise
    except BaseException as exc:                                # noqa: BLE001
        import traceback
        traceback.print_exc()
        raise SystemExit("material loss validation failed: {0}".format(exc))
    if rc != 0:
        raise SystemExit("material loss validation failed")
    sys.exit(0)
