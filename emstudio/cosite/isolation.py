# SPDX-License-Identifier: LGPL-2.1-or-later
"""Antenna-to-antenna isolation / coupling matrix from NEC2 (co-site §5 phase A).

The device-level input to the co-site interference calculator: how much of one
antenna's power couples into another. For N wire antennas this is a multi-port MoM
solve. NEC2 has no direct impedance-matrix print, but the admittance matrix falls
out cleanly with the **Y-matrix method** (de-risked against the Balanis parallel-
dipole mutual-impedance table):

* drive antenna *i* with a 1 V source at its feed segment and leave every other
  antenna as a **continuous, unfed wire** — an unfed centre gap is a short, i.e.
  exactly the "all other ports shorted" boundary condition of the Y-parameters;
* read each antenna's feed-segment current from the CURRENTS AND LOCATION table →
  that is column *i* of the admittance matrix Y (``I_j = Y_ji`` when ``V_i = 1``);
* after N single-drive runs, invert Y → Z, then convert Z → S at the reference
  impedance. Isolation ``= -20*log10|S_ij|`` (dB).

Reciprocity (``Z_ij == Z_ji``) is exact and is used as a self-check. Free space by
default; the solver's GroundType is honoured (monopoles over ground). Qt-free apart
from the FreeCAD geometry read; the numerics are plain numpy.
"""
from __future__ import annotations

import math
import os

import numpy as np

from emstudio.objects import query
from emstudio.setup import solvers as solver_setup
from emstudio.solvers.base import SolverError, SolverJob, make_workdir
from emstudio.solvers.nec2 import parser
from emstudio.solvers.nec2 import writer as nec_writer

C0 = 299792458.0
MM_TO_M = 1e-3


class IsolationModelError(ValueError):
    """The analysis cannot be expressed as a multi-port NEC2 wire model."""


def build_multiport_model(analysis, solver, f_hz=None):
    """Collect the wires + the per-port (wire, feed-segment) map.

    Returns (wires, ports, f_hz). ``wires`` is a list of dicts
    {p1, p2, radius, nseg, key}; ``ports`` is a list of {label, wire, feed_seg}
    (feed_seg is the 1-based local segment on that wire). Ports must sit on PEC
    wires; at least two are required.
    """
    from emstudio.objects.analysis import Analysis

    f1, f2, _npts = Analysis.freq_range_hz(analysis)
    f_hz = float(f_hz) if f_hz else f2
    seg_per_wl = max(10, int(solver.SegmentsPerWavelength))
    lam_min = C0 / max(f_hz, 1.0)

    wires = []
    key_to_wire = {}
    for edge, radius_m, key in nec_writer._iter_material_edges(analysis):
        if not nec_writer._is_straight(edge):
            raise IsolationModelError(
                "edge {0} is not straight; NEC2 wires must be line segments".format(key))
        v1 = edge.Vertexes[0].Point
        v2 = edge.Vertexes[-1].Point
        p1 = (v1.x * MM_TO_M, v1.y * MM_TO_M, v1.z * MM_TO_M)
        p2 = (v2.x * MM_TO_M, v2.y * MM_TO_M, v2.z * MM_TO_M)
        length = math.dist(p1, p2)
        if length <= 0.0:
            continue
        nseg = max(3, int(math.ceil(length / lam_min * seg_per_wl)))
        if key not in key_to_wire:
            key_to_wire[key] = len(wires)
            wires.append({"p1": p1, "p2": p2, "radius": radius_m, "nseg": nseg,
                          "key": key})

    port_objs = query.get_ports(analysis)
    if len(port_objs) < 2:
        raise IsolationModelError(
            "isolation needs at least two ports (found {0})".format(len(port_objs)))

    ge_card, gn_card, ground_active = nec_writer._ground_cards(solver)
    ports = []
    for p in port_objs:
        key = nec_writer._port_edge_key(p)
        if key not in key_to_wire:
            raise IsolationModelError(
                "port '{0}' is not on any PEC wire".format(p.Label))
        widx = key_to_wire[key]
        # a fed wire needs an odd segment count for a true centre segment
        if wires[widx]["nseg"] % 2 == 0:
            wires[widx]["nseg"] += 1
        feed_seg = nec_writer._feed_segment(wires[widx], ground_active)
        ports.append({"label": p.Label, "wire": widx, "feed_seg": feed_seg})

    return wires, ports, (f_hz, ge_card, gn_card)


def _write_drive_deck(wires, ports, drive_idx, f_hz, ge_card, gn_card, path):
    """Write a single-frequency deck that drives one port; others left continuous."""
    lines = ["CM EMStudio isolation drive deck (port {0})".format(drive_idx + 1), "CE"]
    for i, w in enumerate(wires):
        lines.append(
            "GW {tag:d},{nseg:d},{x1:.6g},{y1:.6g},{z1:.6g},"
            "{x2:.6g},{y2:.6g},{z2:.6g},{rad:.6g}".format(
                tag=i + 1, nseg=w["nseg"],
                x1=w["p1"][0], y1=w["p1"][1], z1=w["p1"][2],
                x2=w["p2"][0], y2=w["p2"][1], z2=w["p2"][2], rad=w["radius"]))
    lines.append(ge_card)
    if gn_card:
        lines.append(gn_card)
    port = ports[drive_idx]
    drive_tag = port["wire"] + 1
    lines.append("EX 0,{0:d},{1:d},0,1.,0.".format(drive_tag, port["feed_seg"]))
    lines.append("FR 0,1,0,0,{0:.9g},0.".format(f_hz / 1e6))
    lines.append("XQ")
    lines.append("EN")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def _feed_current(currents, wire_tag, feed_seg):
    """Complex current at the feed_seg-th (1-based) segment of a wire tag."""
    tags = currents["tag"]
    ivals = currents["i_complex"]
    order = [k for k in range(len(tags)) if int(tags[k]) == wire_tag]
    if len(order) < feed_seg:
        raise SolverError(
            "wire tag {0} has {1} segments, need feed segment {2}".format(
                wire_tag, len(order), feed_seg))
    return complex(ivals[order[feed_seg - 1]])


def z_to_s(z, z0):
    """N-port impedance matrix → scattering matrix at a common real reference z0."""
    n = z.shape[0]
    zn = z / float(z0)
    ident = np.eye(n, dtype=complex)
    return (zn - ident) @ np.linalg.inv(zn + ident)


def isolation_matrix(analysis, solver, f_hz=None, z0=50.0, workdir=None,
                     line_callback=None):
    """Extract the N-port isolation/coupling matrix for the analysis' antennas.

    Returns a dict: ``labels`` (list), ``freq_hz``, ``z`` (NxN complex ohms),
    ``s`` (NxN complex), ``isolation_db`` (NxN, -20log10|S_ij|; diagonal 0),
    ``reciprocity_err`` (max |Z_ij - Z_ji|), ``workdir``.
    """
    info = solver_setup.find_backend("nec2")
    if not info.found:
        raise SolverError("nec2c not found.\n" + solver_setup.install_hint(info.backend))

    wires, ports, (f_hz, ge_card, gn_card) = build_multiport_model(analysis, solver, f_hz)
    n = len(ports)
    workdir = make_workdir("emstudio_isolation_", base=workdir)

    y = np.zeros((n, n), dtype=complex)
    for i in range(n):
        deck = os.path.join(workdir, "drive_{0}.nec".format(i + 1))
        out = os.path.join(workdir, "drive_{0}.out".format(i + 1))
        _write_drive_deck(wires, ports, i, f_hz, ge_card, gn_card, deck)
        job = SolverJob([info.path, "-i", deck, "-o", out], cwd=workdir,
                        line_callback=line_callback)
        job.run_blocking(timeout=600)
        currents = parser.parse_currents(out, f_hz)
        for j in range(n):
            # V_i = 1 V on port i, all others shorted -> I_j = Y_ji
            y[j, i] = _feed_current(currents, ports[j]["wire"] + 1,
                                    ports[j]["feed_seg"])

    z = np.linalg.inv(y)
    s = z_to_s(z, z0)
    with np.errstate(divide="ignore"):
        iso = -20.0 * np.log10(np.abs(s))
    np.fill_diagonal(iso, 0.0)
    reciprocity_err = float(np.max(np.abs(z - z.T)))

    return {
        "labels": [p["label"] for p in ports],
        "freq_hz": f_hz,
        "z": z,
        "s": s,
        "isolation_db": iso,
        "reciprocity_err": reciprocity_err,
        "z0": float(z0),
        "workdir": workdir,
    }


def summary_text(result):
    """Human-readable isolation matrix + mutual impedances."""
    labels = result["labels"]
    iso = result["isolation_db"]
    z = result["z"]
    n = len(labels)
    short = [lab[:8] for lab in labels]
    L = ["Antenna isolation @ {0:.4g} MHz".format(result["freq_hz"] / 1e6),
         "Antennas: " + ", ".join(labels), "",
         "Isolation (dB, higher = better coupling loss):"]
    header = "  " + "".join("{0:>10}".format(s) for s in short)
    L.append(header)
    for i in range(n):
        row = "{0:<8}".format(short[i]) + "  "
        for j in range(n):
            row += "{0:>10}".format("—" if i == j else "{0:.1f}".format(iso[i, j]))
        L.append(row)
    L.append("")
    L.append("Self-impedance / mutual impedance (ohm):")
    for i in range(n):
        L.append("  {0}: Zii = {1:.1f}{2:+.1f}j".format(
            short[i], z[i, i].real, z[i, i].imag))
    for i in range(n):
        for j in range(i + 1, n):
            L.append("  {0}<->{1}: Z = {2:.1f}{3:+.1f}j".format(
                short[i], short[j], z[i, j].real, z[i, j].imag))
    L.append("")
    L.append("Reciprocity check (max |Zij-Zji|): {0:.2e}".format(
        result["reciprocity_err"]))
    return "\n".join(L)


def isolation_pairs_db(result):
    """Flatten an isolation result into ``{(i, j): isolation_dB}`` for i<j.

    Ready to hand to ``cosite.interference.analyze_site(isolation_db=...)``.
    """
    iso = result["isolation_db"]
    n = iso.shape[0]
    out = {}
    for i in range(n):
        for j in range(n):
            if i != j:
                out[(i, j)] = float(iso[i, j])
    return out
