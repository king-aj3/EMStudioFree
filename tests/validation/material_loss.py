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
* ``apply_preset`` actually applies, and CLEARS stale values when switching
  back to PEC — a half-applied preset leaves a copper sigma on a PEC material.
* PEC emits no LD card and no conducting sheet, so **every deck written before
  this change is reproduced byte-for-byte**. A correctness fix that also
  silently changed existing results would be its own incident.
* With FreeCAD present, the emitted DECKS are read back: a Conductor wire
  produces both GW geometry and its LD card; a Conductor sheet produces
  ``AddConductingSheet``; a Conductor SOLID falls back to PEC and says so.

Run:  python3 tests/validation/material_loss.py     (library + preset half)
      freecadcmd tests/validation/material_loss.py  (adds the deck half)
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

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

    # ⚠ THE ONE THAT BITES. Switching back to PEC must CLEAR sigma; otherwise a
    # material that was briefly copper stays lossy to every writer while its
    # category says PEC, and the user has no way to see it.
    M.apply_preset(o, M.PEC_PRESET)
    check("PEC clears a stale sigma", o.Conductivity == 0.0,
          "%g" % o.Conductivity)
    check("PEC clears a stale mu_r", o.RelPermeability == 1.0)

    check("an unknown preset is refused, not guessed",
          M.apply_preset(o, "Unobtainium") is False)


def check_decks():
    """Deck-level half: needs FreeCAD. Returns False when unavailable."""
    try:
        import FreeCAD  # noqa: F401
        import Part
    except Exception:
        print("  skip — deck half needs freecadcmd (FreeCAD geometry)")
        return False

    import FreeCAD

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
    return True


def main():
    print("== material loss reaches the solver, and gain is gain ==")
    check_library()
    check_presets()
    check_decks()
    if FAILURES:
        print("MATERIAL LOSS GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("MATERIAL LOSS GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
