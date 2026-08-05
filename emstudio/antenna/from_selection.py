# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build a runnable NEC2 antenna analysis from whatever the user selected.

Why this exists
---------------
Modelling an antenna by hand means creating four objects in the right order
with a selection rule that is not discoverable: the MATERIAL wants the whole
object, the PORT wants one named ``EdgeN`` picked in the 3-D view (not the
tree, not a face), and getting it wrong produces "port must reference a wire
edge", which says what is wrong but not what to do. A real user drew a solid,
then a curve, and hit a different refusal each time.

So: hand this a solid, a curve or an edge and it produces the analysis.

  * a SOLID conductor is reduced to a thin-wire model by
    :mod:`emstudio.geometry.wire_extract` — centreline plus the equivalent
    round radius of its cross-section;
  * a CURVE (or polyline) is used as-is, and the radius must be supplied
    because a curve carries no cross-section to measure;
  * the frequency sweep defaults around the half-wave resonance implied by
    the conductor's own length, which is the frequency the user almost
    certainly wants to look at first.

Everything derived is REPORTED (see :func:`describe`), because a wire model
standing in for a solid is exactly the kind of substitution a user must be
able to audit. Nothing here touches the GUI, so it is testable headlessly.
"""

from __future__ import annotations

C0 = 299792458.0


class AntennaBuildError(ValueError):
    """The selection cannot be turned into a wire antenna."""


def classify(shape):
    """What did the user hand us? Returns 'solid', 'wire' or raises."""
    if shape is None:
        raise AntennaBuildError("nothing selected")
    if getattr(shape, "Solids", None):
        return "solid"
    if getattr(shape, "Edges", None):
        return "wire"
    raise AntennaBuildError(
        "the selection has neither solids nor edges — select the conductor "
        "(a solid) or its path (a curve/polyline)")


def half_wave_hz(length_mm):
    """Free-space half-wave resonance of a conductor of this length."""
    if length_mm <= 0.0:
        raise AntennaBuildError("conductor length is zero")
    return C0 / (2.0 * length_mm * 1e-3)


def plan(shape, radius_mm=None, freq_hz=None, span=1.5):
    """Work out the wire model + sweep WITHOUT touching the document.

    Separated from :func:`build` so the decision can be shown to the user (and
    gated) before anything is created.
    """
    kind = classify(shape)
    notes = []
    if kind == "solid":
        from emstudio.geometry import wire_extract

        info = wire_extract.extract(shape, freq_hz=freq_hz)
        points = info["points"]
        length_mm = info["length_mm"]
        derived_radius = info["radius_mm"]
        notes.extend(info["notes"])
        method = "solid -> centreline ({0} chords)".format(info["chords"])
    else:
        edges = list(shape.Edges)
        length_mm = float(sum(e.Length for e in edges))
        points = None                       # geometry already usable as-is
        derived_radius = None
        method = "curve used as drawn ({0} edge(s))".format(len(edges))

    radius = float(radius_mm) if radius_mm else derived_radius
    if not radius or radius <= 0.0:
        raise AntennaBuildError(
            "no conductor radius: a curve carries no cross-section, so give "
            "the wire radius explicitly (for a polygonal bar use the "
            "equal-area radius, sqrt(area/pi))")
    if derived_radius and radius_mm and abs(radius / derived_radius - 1.0) > 0.01:
        notes.append(
            "using the radius you gave ({0:.4g} mm) rather than the {1:.4g} mm "
            "measured from the solid".format(radius, derived_radius))

    f_res = half_wave_hz(length_mm)
    if freq_hz:
        f_res = float(freq_hz)
    f1 = f_res / span
    f2 = f_res * span
    return {
        "kind": kind,
        "method": method,
        "points": points,
        "length_mm": length_mm,
        "radius_mm": radius,
        "f_res_hz": f_res,
        "f1_hz": f1,
        "f2_hz": f2,
        "notes": notes,
    }


def describe(p, teach=True):
    """What was derived, and — for a first-time user — WHY.

    The audience is a hobbyist before it is an RF engineer, so this explains
    the modelling decision rather than only recording it. Every number below
    is one the user could otherwise only get by knowing to ask for it, and
    the reasoning is what turns a black box into something learnable. Set
    ``teach=False`` for the terse provenance block alone.
    """
    lam_mm = C0 / p["f_res_hz"] * 1000.0
    thin = lam_mm / max(2.0 * p["radius_mm"], 1e-9)
    lines = [
        "Antenna model from the selection",
        "  source            {0}".format(p["method"]),
        "  conductor length  {0:.1f} mm".format(p["length_mm"]),
        "  wire radius       {0:.4g} mm".format(p["radius_mm"]),
        "  half-wave near    {0:.4g} MHz".format(p["f_res_hz"] / 1e6),
        "  sweep             {0:.4g} - {1:.4g} MHz".format(
            p["f1_hz"] / 1e6, p["f2_hz"] / 1e6),
    ]
    for n in p["notes"]:
        lines.append("  NOTE: " + n)

    if not teach:
        return "\n".join(lines)

    lines.append("")
    lines.append("Why it was modelled this way")
    if p["kind"] == "solid":
        lines.append(
            "  You drew a SOLID. NEC2 is a thin-wire solver: it represents a")
        lines.append(
            "  conductor by its centre line plus a radius, because RF current")
        lines.append(
            "  flows on the surface and the radiated field cannot tell a")
        lines.append(
            "  polygonal bar from a round wire of the same cross-section.")
        lines.append(
            "  So the centre line was traced through your solid and its")
        lines.append(
            "  cross-section converted to the equal-area radius above.")
    else:
        lines.append(
            "  You drew a CURVE, which is already a centre line. NEC2 needs")
        lines.append(
            "  straight pieces, so curves are cut into short chords fine")
        lines.append(
            "  enough that the model never leaves the real conductor.")
    lines.append(
        "  This is the ACCURATE method, not a shortcut, while the conductor")
    lines.append(
        "  is thin against the wavelength. Yours is 1/{0:.0f} of a".format(thin))
    lines.append(
        "  wavelength across at {0:.4g} MHz — comfortably thin.".format(
            p["f_res_hz"] / 1e6)
        if thin >= 100.0 else
        "  wavelength across at {0:.4g} MHz — getting THICK; treat the "
        "results with care.".format(p["f_res_hz"] / 1e6))
    lines.append("")
    lines.append(
        "  The sweep is centred on {0:.4g} MHz because a wire is naturally"
        .format(p["f_res_hz"] / 1e6))
    lines.append(
        "  resonant when it is a half wavelength long, and yours is")
    lines.append(
        "  {0:.3f} m of conductor. Expect the reactance to cross zero near"
        .format(p["length_mm"] / 1000.0))
    lines.append(
        "  there; that is the frequency the antenna 'wants' to work at.")
    lines.append("")
    lines.append("What to look at after Run Solver")
    lines.append(
        "  S11 / VSWR  - how much power goes in rather than reflecting back.")
    lines.append(
        "  Impedance   - resonance is where the reactance X crosses zero;")
    lines.append(
        "                the resistance R there is what you must match to 50.")
    lines.append(
        "  Pattern     - the shape of where the energy actually goes.")
    return "\n".join(lines)


def build(doc, source_obj, p, points_label="AntennaWire"):
    """Create the wire geometry (if needed), material, port, analysis, solver.

    Returns ``(analysis, wire_object)``. The port is placed on the MIDDLE edge
    — a centre feed is the sane default for a wire antenna, and it is the one
    place a user would otherwise have to find by hand in the 3-D view.
    """
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    wire_obj = source_obj
    if p["points"] is not None:
        import Part

        wire_obj = doc.addObject("Part::Feature", points_label)
        wire_obj.Shape = Part.makePolygon(p["points"])
        doc.recompute()

    n_edges = len(wire_obj.Shape.Edges)
    if n_edges < 1:
        raise AntennaBuildError("the wire model has no edges")

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Antenna"
    ana.FrequencyStart = "{0} Hz".format(p["f1_hz"])
    ana.FrequencyStop = "{0} Hz".format(p["f2_hz"])
    ana.FrequencyPoints = 51

    mat = material_mod.makeMaterial(doc, ana, name="AntennaPEC",
                                    category="Metal (PEC)",
                                    references=[(wire_obj, "")])
    mat.WireRadius = "{0} mm".format(p["radius_mm"])

    feed_edge = "Edge{0}".format(n_edges // 2 + 1)
    port = ports_mod.makeLumpedPort(doc, ana, name="AntennaFeed",
                                    references=[(wire_obj, feed_edge)])
    port.Impedance = "50 Ohm"
    port.Excited = True

    solver_objs.makeSolverNEC2(doc, ana)
    doc.recompute()
    return ana, wire_obj
