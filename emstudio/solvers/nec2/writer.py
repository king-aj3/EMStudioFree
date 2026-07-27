# SPDX-License-Identifier: LGPL-2.1-or-later
"""NEC2 input deck writer.

Walks an EM Analysis, extracts wire geometry from PEC materials, and emits a ``.nec``
card deck (nec2c's comma-separated free format):

* every straight edge referenced by a ``Metal (PEC)`` material becomes a ``GW`` card
  (units: meters; radius from the material's ``WireRadius``),
* the excited ``EMLumpedPort``'s referenced edge gets the ``EX`` voltage source on its
  center segment (segment count forced odd),
* every ``EMStudio::TransmissionLine`` becomes a ``TL`` card between the center
  segments of the two wires it references (both forced to odd segment counts;
  ``Crossed`` emits the negative-Z0 crossed-line convention — the LPDA feeder),
* the analysis frequency sweep becomes the ``FR`` card.

Curved edges are rejected in Phase 1 (NEC needs piecewise-straight wires; automatic
polyline discretization is a Phase-2 item).
"""

from __future__ import annotations

import math

from emstudio.objects import query

C0 = 299792458.0  # m/s

MM_TO_M = 1e-3


class WireModelError(ValueError):
    """The analysis cannot be expressed as a NEC2 wire model."""


def _is_straight(edge):
    return type(edge.Curve).__name__ == "Line"


def _edge_key(link_obj, subname):
    return (link_obj.Name, subname)


def _iter_material_edges(analysis):
    """Yield (edge_shape, radius_m, key) for every wire edge of every PEC material."""
    for mat in query.get_materials(analysis):
        if not str(mat.Category).startswith("Metal"):
            continue
        radius_m = float(mat.WireRadius.getValueAs("m"))
        for link_obj, shape, sub in query.resolved_references(mat):
            if shape is None:
                continue
            if sub == "":  # whole object: take all its edges
                for i, edge in enumerate(shape.Edges):
                    yield edge, radius_m, _edge_key(link_obj, "Edge{0}".format(i + 1))
            elif sub.startswith("Edge"):
                yield shape, radius_m, _edge_key(link_obj, sub)
            # faces/solids are ignored by the wire backend


def _port_edge_key(port):
    """The (object, subname) key of the edge a port references."""
    for link_obj, shape, sub in query.resolved_references(port):
        if sub.startswith("Edge"):
            return _edge_key(link_obj, sub)
        if sub == "" and shape is not None and len(shape.Edges) == 1:
            return _edge_key(link_obj, "Edge1")
    raise WireModelError(
        "port '{0}' must reference a wire edge for the NEC2 backend".format(port.Label)
    )


def _tl_edge_keys(tl):
    """The two (object, subname) edge keys a transmission line connects, in
    References order."""
    keys = []
    for link_obj, shape, sub in query.resolved_references(tl):
        if sub.startswith("Edge"):
            keys.append(_edge_key(link_obj, sub))
        elif sub == "" and shape is not None and len(shape.Edges) == 1:
            keys.append(_edge_key(link_obj, "Edge1"))
    if len(keys) != 2:
        raise WireModelError(
            "transmission line '{0}' must reference exactly two wire edges "
            "(found {1})".format(tl.Label, len(keys)))
    if keys[0] == keys[1]:
        raise WireModelError(
            "transmission line '{0}' connects an edge to itself".format(tl.Label))
    return keys


def _tl_wire_keys(analysis):
    """Every edge key referenced by any transmission line in the analysis."""
    keys = set()
    for tl in query.get_transmission_lines(analysis):
        keys.update(_tl_edge_keys(tl))
    return keys


def _tl_cards(analysis, wires):
    """Format the ``TL`` cards. Center-segment to center-segment; ``Crossed``
    flips the Z0 sign (NEC2's crossed/transposed-line convention); LineLength 0
    lets NEC2 use the straight-line distance between the connection points."""
    tls = query.get_transmission_lines(analysis)
    if not tls:
        return []
    index = {}
    for i, w in enumerate(wires):
        index[w["key"]] = (i + 1, (w["nseg"] + 1) // 2)
    cards = []
    for tl in tls:
        k1, k2 = _tl_edge_keys(tl)
        for k in (k1, k2):
            if k not in index:
                raise WireModelError(
                    "transmission line '{0}' references edge {1}, which is not "
                    "part of any PEC material's wires".format(tl.Label, k))
        z0 = float(tl.Z0.getValueAs("Ohm"))
        if z0 <= 0.0:
            raise WireModelError(
                "transmission line '{0}' needs a positive Z0 (use Crossed for "
                "the transposed line)".format(tl.Label))
        if bool(getattr(tl, "Crossed", False)):
            z0 = -z0
        length_m = float(tl.LineLength.getValueAs("m"))
        (t1, s1), (t2, s2) = index[k1], index[k2]
        cards.append(
            "TL {t1:d},{s1:d},{t2:d},{s2:d},{z0:.6g},{L:.6g},"
            "{y1r:.6g},{y1i:.6g},{y2r:.6g},{y2i:.6g}".format(
                t1=t1, s1=s1, t2=t2, s2=s2, z0=z0, L=length_m,
                y1r=float(getattr(tl, "Y1Real", 0.0)),
                y1i=float(getattr(tl, "Y1Imag", 0.0)),
                y2r=float(getattr(tl, "Y2Real", 0.0)),
                y2i=float(getattr(tl, "Y2Imag", 0.0))))
    return cards


_GROUND_Z_TOL = 1e-3  # m — an endpoint this close to z=0 sits on the ground plane


def _ground_cards(solver):
    """Return (ge_card, gn_card_or_None, active) for the solver's GroundType.

    Default (free space) yields ``("GE 0", None, False)`` — byte-identical to the
    pre-ground writer, so dipole/free-space analyses are unaffected.
    """
    gt = str(getattr(solver, "GroundType", "None (free space)"))
    if gt.startswith("Perfect"):
        return "GE 1", "GN 1", True
    if gt.startswith("Finite"):
        eps = float(getattr(solver, "GroundEpsilonR", 13.0))
        sigma = float(getattr(solver, "GroundConductivity", 0.005))
        return "GE 1", "GN 2,0,0,0,{0:.6g},{1:.6g}".format(eps, sigma), True
    return "GE 0", None, False


def _feed_segment(wire, ground_active):
    """Segment to excite: the base (ground-touching) segment of a grounded
    monopole, else the center segment (the dipole/free-space convention)."""
    nseg = wire["nseg"]
    if ground_active:
        z1, z2 = wire["p1"][2], wire["p2"][2]
        if abs(z1) <= _GROUND_Z_TOL and abs(z1) <= abs(z2):
            return 1        # base at end 1 (wire defined from the ground up)
        if abs(z2) <= _GROUND_Z_TOL and abs(z2) < abs(z1):
            return nseg     # base at end 2
    return (nseg + 1) // 2  # center feed


def _port_drive(port):
    """Complex drive voltage of an excited port (V). Ports saved before v0.67.0
    have no Amplitude/PhaseDeg yet (onDocumentRestored adds them on load, but a
    bare object in a gate may not) — default to the historic unity drive."""
    amp = float(getattr(port, "Amplitude", 1.0))
    ph = math.radians(float(getattr(port, "PhaseDeg", 0.0)))
    if not math.isfinite(amp) or not math.isfinite(ph):
        raise WireModelError(
            "port '{0}' has a non-finite drive (Amplitude {1!r}, PhaseDeg "
            "{2!r}) — nec2c would parse 'nan' as 0 V and then silently "
            "rewrite it to 1 V".format(port.Label, amp,
                                       getattr(port, "PhaseDeg", 0.0)))
    re = amp * math.cos(ph)
    im = amp * math.sin(ph)
    # snap the float noise of exact 90-degree multiples (cos(90 deg) = 6.1e-17).
    # abs(amp): Amplitude is an unbounded float, and a negative one (== 180 deg
    # of phase) would otherwise make the threshold negative and never fire.
    tol = 1e-12 * abs(amp)
    if abs(re) < tol:
        re = 0.0
    if abs(im) < tol:
        im = 0.0
    return complex(re, im)


def build_wire_model_multi(analysis, solver):
    """Extract the wire list + every excited port's feed. Returns
    (wires, feeds, sweep) where ``feeds`` is a list (PortNumber order) of dicts
    {port, wire (index into wires), drive (complex V)}.

    Multi-excitation rules (§7 S4):

    * every fed wire gets an odd segment count (a true center segment);
    * an excited port with a ZERO drive voltage is refused — nec2c silently
      rewrites a zero-volt EX card to 1 V (verified), so "excited at 0 V" is
      unexpressible: un-excite the port instead;
    * two ports on one edge are refused (one boolean feed per wire);
    * duplicate wire-edge references are refused when more than one port is
      excited (the multi-port Z-extraction path dedupes; the decks must agree).
    """
    from emstudio.objects.analysis import Analysis

    f1, f2, npts = Analysis.freq_range_hz(analysis)
    lam_min = C0 / f2
    seg_per_wl = max(10, int(solver.SegmentsPerWavelength))

    ports = [p for p in query.get_ports(analysis) if p.Excited]
    if not ports:
        raise WireModelError("NEC2 backend needs at least one excited port")
    feed_keys = {}
    for p in ports:
        key = _port_edge_key(p)
        if key in feed_keys:
            raise WireModelError(
                "ports '{0}' and '{1}' reference the same wire edge — two feed "
                "points on one wire are not expressible in the NEC2 wire model"
                .format(feed_keys[key].Label, p.Label))
        feed_keys[key] = p
    tl_keys = _tl_wire_keys(analysis)

    wires = []
    seen_keys = set()
    key_to_index = {}
    for edge, radius_m, key in _iter_material_edges(analysis):
        if not _is_straight(edge):
            raise WireModelError(
                "edge {0} is not straight; NEC2 wires must be line segments".format(key)
            )
        if key in seen_keys and len(ports) > 1:
            raise WireModelError(
                "wire edge {0} is referenced more than once — the multi-port "
                "deck and the Z-extraction decks would disagree on wire "
                "numbering".format(key))
        seen_keys.add(key)
        v1 = edge.Vertexes[0].Point
        v2 = edge.Vertexes[-1].Point
        p1 = (v1.x * MM_TO_M, v1.y * MM_TO_M, v1.z * MM_TO_M)
        p2 = (v2.x * MM_TO_M, v2.y * MM_TO_M, v2.z * MM_TO_M)
        length = math.dist(p1, p2)
        if length <= 0.0:
            continue
        nseg = max(3, int(math.ceil(length / lam_min * seg_per_wl)))
        fed = key in feed_keys
        if (fed or key in tl_keys) and nseg % 2 == 0:
            nseg += 1  # odd count -> a true center segment (source / TL end)
        if fed:
            key_to_index[key] = len(wires)
        wires.append(
            {"p1": p1, "p2": p2, "radius": radius_m, "nseg": nseg, "fed": fed,
             "key": key}
        )

    if not wires:
        raise WireModelError("no straight PEC wire edges found in the analysis")
    feeds = []
    for p in ports:                      # PortNumber order (query.get_ports)
        key = _port_edge_key(p)
        if key not in key_to_index:
            raise WireModelError(
                "the excited port's edge is not part of any PEC material's references"
            )
        drive = _port_drive(p)
        if drive == 0:
            raise WireModelError(
                "port '{0}' is excited with a 0 V drive — NEC2 silently rewrites "
                "a zero-volt source to 1 V; un-tick Excited instead".format(p.Label))
        feeds.append({"port": p, "wire": key_to_index[key], "drive": drive})
    return wires, feeds, (f1, f2, npts)


def build_wire_model(analysis, solver):
    """Extract the wire list + feed location. Returns (wires, feed_index, sweep).

    wires: list of dicts {p1, p2, radius, nseg, fed}

    Single-excitation view (the historic API): exactly one excited port. The
    multi-excitation general form is :func:`build_wire_model_multi`.
    """
    wires, feeds, sweep = build_wire_model_multi(analysis, solver)
    if len(feeds) != 1:
        raise WireModelError(
            "NEC2 backend needs exactly one excited port (found {0})".format(len(feeds))
        )
    return wires, feeds[0]["wire"], sweep


def _ex_cards(wires, feeds, ground_active):
    """Format one EX card per excited port (PortNumber order).

    The unity drive keeps the exact historic literal ``EX 0,t,s,0,1.,0.`` — the
    frozen-deck gate compares deck text byte-for-byte."""
    cards = []
    for feed in feeds:
        w = wires[feed["wire"]]
        seg = _feed_segment(w, ground_active)
        tag = feed["wire"] + 1
        v = feed["drive"]
        if v == 1.0:                     # the historic single-port literal
            cards.append("EX 0,{0:d},{1:d},0,1.,0.".format(tag, seg))
        else:
            cards.append("EX 0,{0:d},{1:d},0,{2:.9g},{3:.9g}".format(
                tag, seg, v.real, v.imag))
    return cards


def write_nec(analysis, solver, path):
    """Write the .nec deck. Returns (path, sweep, z0).

    Emits one EX card per excited port (multi-excitation, §7 S4); a
    single-port unity-drive analysis produces a byte-identical historic deck.
    z0 is the FIRST excited port's reference impedance (multi-port sweeps are
    post-processed per port via ``parser.parse_port_impedances``)."""
    wires, feeds, (f1, f2, npts) = build_wire_model_multi(analysis, solver)
    z0 = float(feeds[0]["port"].Impedance.getValueAs("Ohm"))

    f1_mhz = f1 / 1e6
    f2_mhz = f2 / 1e6
    dfrq = (f2_mhz - f1_mhz) / (npts - 1) if npts > 1 else 0.0

    lines = [
        "CM EMStudio generated NEC2 deck",
        "CM analysis: {0}".format(analysis.Label),
        "CE",
    ]
    for i, w in enumerate(wires):
        lines.append(
            "GW {tag:d},{nseg:d},{x1:.6g},{y1:.6g},{z1:.6g},"
            "{x2:.6g},{y2:.6g},{z2:.6g},{rad:.6g}".format(
                tag=i + 1,
                nseg=w["nseg"],
                x1=w["p1"][0], y1=w["p1"][1], z1=w["p1"][2],
                x2=w["p2"][0], y2=w["p2"][1], z2=w["p2"][2],
                rad=w["radius"],
            )
        )
    ge_card, gn_card, ground_active = _ground_cards(solver)
    lines.append(ge_card)
    if gn_card:
        lines.append(gn_card)
    lines.extend(_tl_cards(analysis, wires))
    lines.extend(_ex_cards(wires, feeds, ground_active))
    lines.append("FR 0,{0:d},0,0,{1:.6f},{2:.6f}".format(npts, f1_mhz, dfrq))
    lines.append("XQ")
    lines.append("EN")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path, (f1, f2, npts), z0


def write_nec_farfield(analysis, solver, path, f_hz):
    """Write a single-frequency deck with an RP card (radiation pattern pass).

    Pattern grid: theta 0..180 deg step 2, phi cuts at 0 and 90 deg — matching the
    openEMS backend's far-field sampling so results are directly comparable.
    """
    wires, feeds, _ = build_wire_model_multi(analysis, solver)

    lines = [
        "CM EMStudio generated NEC2 far-field deck",
        "CM analysis: {0}".format(analysis.Label),
        "CE",
    ]
    for i, w in enumerate(wires):
        lines.append(
            "GW {tag:d},{nseg:d},{x1:.6g},{y1:.6g},{z1:.6g},"
            "{x2:.6g},{y2:.6g},{z2:.6g},{rad:.6g}".format(
                tag=i + 1,
                nseg=w["nseg"],
                x1=w["p1"][0], y1=w["p1"][1], z1=w["p1"][2],
                x2=w["p2"][0], y2=w["p2"][1], z2=w["p2"][2],
                rad=w["radius"],
            )
        )
    ge_card, gn_card, ground_active = _ground_cards(solver)
    lines.append(ge_card)
    if gn_card:
        lines.append(gn_card)
    lines.extend(_tl_cards(analysis, wires))
    lines.extend(_ex_cards(wires, feeds, ground_active))
    lines.append("FR 0,1,0,0,{0:.6f},0.".format(f_hz / 1e6))
    # Free space: full sphere (theta 0-180 x phi 0-355, 5 deg) for 3-D balloons;
    # the phi=0/90 columns feed the 2-D cuts. Over ground the lower hemisphere is
    # below the earth, so sample only the upper hemisphere (theta 0-90).
    if ground_active:
        lines.append("RP 0,19,72,1000,0.,0.,5.,5.")
    else:
        lines.append("RP 0,37,72,1000,0.,0.,5.,5.")
    lines.append("EN")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path
