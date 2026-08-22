# SPDX-License-Identifier: LGPL-2.1-or-later
"""openEMS deck writer.

Translates an EM Analysis into a self-contained Python deck (``case_openems.py``) that
runs under the openEMS venv interpreter as a subprocess. The deck mirrors the structure
of the official openEMS Python tutorials (Simple_Patch_Antenna.py):

* geometry as literal CSXCAD boxes (axis-aligned solids/sheets) or STL polyhedra,
* grid built with openEMS's own utilities (AddEdges2Grid thirds-rule for metal edges,
  SmoothMeshLines grading) from parameters computed here,
* one excited lumped port; post-processing writes the shared SweepResult CSV schema.

Everything the deck needs is embedded as literals — the deck never imports FreeCAD.
"""

from __future__ import annotations

import math
import os

from emstudio.objects import query
from emstudio.objects.analysis import Analysis

from . import geometry

C0 = 299792458.0
EPS0 = 8.8541878128e-12
AXES = "xyz"


def excite_dir_negative(direction):
    """True if a '+X'/'-Z'-style direction string points along the negative axis."""
    return str(direction)[0] == "-"


#: Cells the FDTD grid must put across a body's smallest feature before the
#: geometry means anything. Below 1 the body is thinner than a cell and is
#: represented by nothing at all; below this it is a staircase caricature.
MIN_CELLS_ACROSS_FEATURE = 3.0

#: Ceiling on the CELLS local refinement may add for one body. The cost of a
#: refinement is the PRODUCT of its per-axis line counts, not the largest of
#: them: blanketing a 6-turn helix's bounding box at its 20 mm conductor is
#: 105 x 73 x 121 = 927k cells for a single body, inside a domain that is
#: metres across at its resonance. A per-axis cap misses that entirely — 121
#: looks modest until it is multiplied. Declining here hands the case to
#: _refuse_unresolvable, which tells the user plainly that FDTD is the wrong
#: tool for a lambda/600 conductor.
MAX_REFINEMENT_CELLS = 200000

#: Per-axis sanity bound, kept alongside the cell budget so a single
#: pathological axis cannot produce a degenerate grid.
MAX_REFINEMENT_LINES = 400


def _stl_refinement(prim, mesh_res_mm):
    """Local grid for one STL body: (step_mm, (nx, ny, nz)) or None.

    None means "do not refine": either the global cell already resolves the
    body, or refining it would cost more lines than :data:`MAX_REFINEMENT_LINES`
    on some axis. Refusing to refine is not the same as refusing to run — the
    caller decides that separately, from the same feature size.
    """
    feat = float(prim.get("min_feature") or 0.0)
    if feat <= 0.0:
        return None
    step = feat / MIN_CELLS_ACROSS_FEATURE
    if step >= mesh_res_mm:
        return None                     # the global grid already resolves it
    counts = []
    for i in range(3):
        extent = prim["stop"][i] - prim["start"][i]
        if extent <= 0.0:
            counts.append(2)
            continue
        n = int(math.ceil(extent / step)) + 1
        if n > MAX_REFINEMENT_LINES:
            return None                 # degenerate on this axis
        counts.append(max(2, n))
    if counts[0] * counts[1] * counts[2] > MAX_REFINEMENT_CELLS:
        return None                     # unaffordable as a whole
    return step, tuple(counts)


class OpenEMSModelError(ValueError):
    """The analysis cannot be expressed as an openEMS model."""


#: How flat |S11| has to be across the sweep before "the best match" stops
#: meaning anything. Below this span the deck takes the pattern at the sweep
#: CENTRE instead of at argmin|S11| and says so.
#:
#: ⚠ This number decides which existing documents move, so it is chosen to move
#: none of them that had a defensible answer. Any antenna with a usable
#: resonance has far more than 3 dB of |S11| range — the shipped patch, dipole
#: and notch gates are tens of dB — while the Ka-band horn, which is matched
#: right across 26.5-40 GHz, has essentially none and picked 28.45 GHz at one
#: mesh and 39.55 GHz at another. The branch fires on exactly the second kind.
FLAT_S11_SPAN_DB = 3.0


def _pattern_indices(solver, f1_hz, f2_hz, npts):
    """Indices into the deck's own frequency grid that get a radiation pattern.

    Empty means "one pattern, frequency chosen at run time" — the default rule
    needs S11, which does not exist until the run is over.

    Returns INDICES rather than frequencies on purpose: ``port.P_acc`` is
    indexed on that same ``np.linspace(f1, f2, npts)`` grid, and the efficiency
    is only right if the pattern and the accepted power are read at the same
    sample. Snapping also means every pattern lands on a frequency the S11 /
    VSWR / impedance curves were actually computed at, so the results dialog's
    cursor and its pattern picker agree — the reason NEC2 snaps too.
    """
    from emstudio.solvers.nec2 import pattern_band

    n = int(getattr(solver, "PatternFrequencies", 0) or 0)
    if n < 2:
        return []
    b1, b2 = pattern_band.resolve_band(solver, f1_hz, f2_hz)
    f1, f2 = float(f1_hz), float(f2_hz)
    span = f2 - f1
    if span <= 0.0 or int(npts) < 2:
        return []
    step = span / (int(npts) - 1)
    idx = []
    for k in range(n):
        target = b1 + (b2 - b1) * k / float(n - 1)
        i = int(round((target - f1) / step))
        i = max(0, min(int(npts) - 1, i))
        if i not in idx:
            idx.append(i)
    return sorted(idx)


def _nf2ff_bc(boundaries):
    """(bc_size, directions, mirror) for a hand-built NF2FF box.

    A verbatim replication of ``openEMS.CreateNF2FFBox``'s own rule
    (openEMS.pyx), because that method decides ``directions`` itself and so
    cannot be told to drop a face. Getting this wrong moves the recording
    surface, which moves every far-field number, so it is written to match the
    engine line for line rather than to look tidy:

      PEC  -> face OFF, mirrored as PEC (1), no inset
      PMC  -> face OFF, mirrored as PMC (2), no inset
      MUR  -> 2 lines in
      PML_N-> N + 1 lines in    <- the "+1" is the engine's, not a safety margin

    ⚠ An unparseable ``PML_`` is REFUSED here rather than defaulted to 8.
    openEMS does not default either — ``int('PML_'.strip('PML_'))`` raises
    ValueError inside SetBoundaryCond — and a guard that quietly assumed 8
    would disagree with the engine it is meant to mirror.
    """
    bc_size = [0] * 6
    directions = [1] * 6
    mirror = [0] * 6
    for n, bc in enumerate(boundaries):
        bc = str(bc)
        if bc == "PEC":
            directions[n], mirror[n] = 0, 1
        elif bc == "PMC":
            directions[n], mirror[n] = 0, 2
        elif bc == "MUR":
            bc_size[n] = 2
        elif bc.startswith("PML_"):
            try:
                bc_size[n] = int(bc[4:]) + 1
            except ValueError:
                raise OpenEMSModelError(
                    "boundary {0} is '{1}': a PML needs a cell count, e.g. "
                    "'PML_8'. openEMS rejects this too.".format(n, bc))
        else:
            raise OpenEMSModelError(
                "boundary {0} is '{1}', which openEMS does not accept "
                "(PEC, PMC, MUR or PML_<n>)".format(n, bc))
    return bc_size, directions, mirror


def _refuse_unresolvable(mats, mesh_res_mm):
    """Refuse a body the grid cannot represent at all, with the numbers.

    FDTD is a volume method on a Cartesian grid: a conductor thinner than one
    cell is not "approximate", it is ABSENT, and the run still produces
    S-parameters and a radiation pattern that look perfectly plausible. Local
    refinement (:func:`_stl_refinement`) rescues the affordable cases; this
    catches the ones no refinement can, and says why in the user's own units.

    The classic example is exactly the geometry that motivated it: a 6-turn
    helix, 20 mm conductor, resonating near 25 MHz. lambda is 12 m there, so
    the default grid cell is ~250 mm — the conductor is 0.04 of a cell. No
    mesh setting fixes that; a lambda/600 conductor in a lambda-sized domain is
    what thin-wire codes exist for, and the message says so.
    """
    worst = None
    for m in mats:
        # SCOPE, and every exclusion is load-bearing — an earlier draft of this
        # check refused EMStudio's own validated 2.4 GHz patch template:
        #  * DIELECTRICS are excluded: a thin substrate already gets explicit
        #    lines across its thickness further down (_dielectric_thin_axis_lines),
        #    so 0.3 global cells across a 1.524 mm Rogers laminate is fine and
        #    is exactly how the published reference design is meshed.
        #  * BOXES and SHEETS are excluded: thin metal is modelled as a
        #    zero-thickness sheet, the openEMS-canonical form, and gets the
        #    metal-edge thirds rule rather than volume cells.
        # What is left is the real hazard: a metal STL body with genuine
        # thickness that no local refinement rescued.
        if m["kind"] != "metal":
            continue
        for p in m["prims"]:
            if p["kind"] != "stl":
                continue
            feat = float(p.get("min_feature") or 0.0)
            if feat <= 0.0:
                continue
            if _stl_refinement(p, mesh_res_mm) is not None:
                continue                # local refinement will resolve it
            cells = feat / mesh_res_mm
            if worst is None or cells < worst[0]:
                worst = (cells, feat, m["name"])
    if worst is None or worst[0] >= 1.0:
        return
    cells, feat, name = worst
    raise OpenEMSModelError(
        "'{0}' has a smallest feature of {1:.4g} mm, but the FDTD cell is "
        "{2:.4g} mm — {3:.3g} cells across it, so this body would be absent "
        "from the grid and the run would still report plausible-looking "
        "results. Either raise MeshResolution until the cell is under "
        "{1:.4g} mm (the domain is wavelength-sized, so check the cell count "
        "first), or model this conductor with the NEC2 wire backend, which is "
        "the accurate method for a conductor this thin against the "
        "wavelength.".format(name, feat, mesh_res_mm, cells))


# --------------------------------------------------------------------------- helpers
def _fmt_v(v):
    return "[{0:.9g}, {1:.9g}, {2:.9g}]".format(*v)


def _collect_materials(analysis, workdir):
    """Returns list of dicts: {name, kind: metal|dielectric, params, prims, priority}."""
    mats = []
    for i, mat in enumerate(query.get_materials(analysis)):
        prims = geometry.classify_shapes(mat, workdir, "mat{0}".format(i + 1))
        if not prims:
            continue
        category = str(mat.Category)
        entry = {
            "name": "mat{0}_{1}".format(i + 1, "".join(c for c in mat.Label if c.isalnum()) or "m"),
            "prims": prims,
            "priority": int(mat.Priority),
        }
        if category.startswith("Conductor") and float(mat.Conductivity) > 0.0:
            # ⚠⚠ UNTIL 2026-08-22 THIS FELL INTO THE "metal" BRANCH AND THE
            # USER'S SIGMA WAS DISCARDED — a settable field that changed
            # nothing, on a backend that reported the resulting lossless gain
            # as fact. openEMS models finite-conductivity metal with a SURFACE
            # IMPEDANCE sheet, which is the only tractable choice: resolving a
            # real skin depth (2 um in copper at 1 GHz) on an FDTD grid is not
            # affordable, and a lossy VOLUME material would demand exactly that.
            entry["kind"] = "conducting_sheet"
            entry["sigma"] = float(mat.Conductivity)
            try:
                entry["thickness_m"] = float(
                    mat.SheetThickness.getValueAs("m"))
            except Exception:
                entry["thickness_m"] = 35e-6      # 1 oz copper
        elif category.startswith("Metal") or category.startswith("Conductor"):
            entry["kind"] = "metal"
        else:
            entry["kind"] = "dielectric"
            entry["epsR"] = float(mat.RelPermittivity)
            entry["tanD"] = float(mat.LossTangent)
            entry["kappa"] = float(mat.Conductivity)
            entry["mu"] = float(mat.RelPermeability)
        mats.append(entry)
    if not mats:
        raise OpenEMSModelError("no material with usable geometry found in the analysis")
    return mats


def _port_span(port):
    """Port span (start, stop) in mm from the referenced sub-shape's bbox."""
    for _, shape, _sub in query.resolved_references(port):
        if shape is None:
            continue
        bb = shape.BoundBox
        return (bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)
    raise OpenEMSModelError(
        "port '{0}' has no usable geometry reference (needs an edge/face spanning "
        "the feed gap)".format(port.Label)
    )


#: How many mesh cells an EXCITED waveguide port spans between its
#: excitation plane and its probe plane. Upstream's Rect_Waveguide
#: tutorial uses four for its excited port; one is already enough
#: (measured, see the comment in _collect_ports), so four is margin.
_WG_PORT_CELLS = 4


def _collect_ports(analysis, excite_port=None, cell_mm=None):
    ports = []
    for port in query.get_ports(analysis):
        start, stop = _port_span(port)
        direction = str(port.Direction)  # e.g. "+Z"
        axis = direction[-1].lower()
        excite = 1.0 if direction[0] == "+" else -1.0
        edges2grid = "".join(a for a in AXES if a != axis)
        ptype = str(getattr(port, "PortType", "Lumped"))
        prop_dir = str(getattr(port, "PropagationDirection", "+X"))
        entry = {
            "nr": int(port.PortNumber),
            "R": float(port.Impedance.getValueAs("Ohm")),
            "start": start,
            "stop": stop,
            "axis": axis,
            # ``excite_port`` overrides the document's own Excited flags so a
            # caller can drive each port in turn for a full S-matrix. openEMS
            # solves ONE excitation per run, so an N-port needs N runs.
            "excite": excite if (
                int(port.PortNumber) == int(excite_port) if excite_port
                else port.Excited) else 0.0,
            "edges2grid": edges2grid,
            "type": ptype,
        }
        if ptype == "RectWaveguide":
            # ⛳ a and b come from the referenced FACE's own bounding box, not
            # from user-typed numbers, so the mode profile and the geometry
            # cannot disagree. openEMS wants them in METRES; the document is in
            # mm, which is exactly the units slip that made a cavity "converge
            # beautifully" on nonsense once before.
            entry["prop_axis"] = prop_dir[-1].lower()
            entry["prop_sign"] = 1.0 if prop_dir[0] == "+" else -1.0
            pi = AXES.index(entry["prop_axis"])
            trans = [i for i in range(3) if i != pi]
            spans = sorted(abs(stop[i] - start[i]) for i in trans)
            # a is the BROAD wall, b the narrow one — the TE10 convention. Taking
            # them by size rather than by axis order means the port works whatever
            # way round the face was drawn.
            entry["wg_b_m"] = spans[0] * 1e-3
            entry["wg_a_m"] = spans[1] * 1e-3
            entry["wg_mode"] = str(getattr(port, "WaveguideMode", "TE10") or "TE10")
            # ⚠⚠ AN EXCITED WAVEGUIDE PORT MAY NOT BE ZERO-LENGTH along the
            # propagation axis — openEMS raises "Port length in excitation
            # direction may not be zero if port is excited!". A port FACE is
            # naturally zero-thickness, so it must be given depth here or every
            # excited waveguide run dies at deck time.
            #
            # ⚠⚠ AND THE DEPTH IS NOT COSMETIC — IT IS THE DISTANCE BETWEEN THE
            # SOURCE AND THE PROBES. openEMS puts the mode excitation on the
            # ``start`` plane and the voltage/current probes on the ``stop``
            # plane (openEMS/ports.py, WaveguidePort.__init__), so this span is
            # how far downstream the port measures. Too close and the probes sit
            # inside the source's own near field and report nonsense.
            #
            # This used to be ``min(a, b) / 20``, a fraction of the guide's
            # NARROW WALL with no relation to the grid, described in a comment
            # as "exactly ONE mesh cell". On WR-28 at Ka band it delivers
            # 0.1778 mm against a 0.3747 mm cell — **0.48 of a cell**.
            # ⛳ MEASURED on a straight PEC-walled WR-28 section terminated in
            # PML (tests/validation/waveguide_port_openems.py), where the right
            # answer is |S11| ~ 0 and P_acc/P_inc = 1:
            #     0.48 cells -> |S11| = 0.00 dB, P_acc/P_inc = 0.0004  (dead)
            #     1, 2, 4, 8, 16 cells -> |S11| = -45..-53 dB, P_acc/P_inc = 1.0000
            # One cell is already enough; four is what upstream's own
            # Rect_Waveguide tutorial gives its EXCITED port (z(11) -> z(15)).
            # ⚠ The one-cell span in that tutorial belongs to port 2, which is
            # NOT excited — copying it onto the excited port was the mistake.
            # ⚠ This assumes at least four cells of STRAIGHT guide behind the
            # face; a port placed within lambda/5 of a flare or a bend will
            # measure inside the discontinuity.
            plo, phi = start[pi], stop[pi]
            if abs(phi - plo) < 1e-12:
                depth = max(_WG_PORT_CELLS * float(cell_mm or 0.0), 1e-3)
                st, sp = list(start), list(stop)
                if entry["prop_sign"] >= 0:
                    sp[pi] = plo + depth
                else:
                    sp[pi] = plo - depth
                entry["start"], entry["stop"] = tuple(st), tuple(sp)
            if entry["wg_a_m"] <= 0.0 or entry["wg_b_m"] <= 0.0:
                raise OpenEMSModelError(
                    "waveguide port '{0}' needs a FACE with two non-zero "
                    "transverse dimensions; got a={1:g} b={2:g} mm".format(
                        port.Label, entry["wg_a_m"] * 1e3, entry["wg_b_m"] * 1e3))
        if ptype == "MSL":
            entry["prop_axis"] = prop_dir[-1].lower()
            entry["prop_sign"] = 1.0 if prop_dir[0] == "+" else -1.0
            # For AddMSLPort the box span encodes two directions that MUST match the
            # physics (bbox min->max is not enough):
            #  * E-field / exc axis: span runs strip->ground, i.e. ALONG the field
            #    Direction (Direction '-Z' => start at top h, stop at 0).
            #  * propagation axis: span runs along PropagationDirection; openEMS
            #    puts the feed at 'start' and the wave leaves toward 'stop'.
            s, e = list(entry["start"]), list(entry["stop"])
            ei = AXES.index(axis)
            lo, hi = min(s[ei], e[ei]), max(s[ei], e[ei])
            if excite_dir_negative(direction):
                s[ei], e[ei] = hi, lo  # field points to -axis: start high, stop low
            else:
                s[ei], e[ei] = lo, hi
            pi = AXES.index(entry["prop_axis"])
            plo, phi = min(s[pi], e[pi]), max(s[pi], e[pi])
            if entry["prop_sign"] < 0:
                s[pi], e[pi] = phi, plo
            else:
                s[pi], e[pi] = plo, phi
            entry["start"], entry["stop"] = tuple(s), tuple(e)
        ports.append(entry)
    # ⚠ "exactly one" has to be COUNTED, not tested with `any`. Every port
    # created through the GUI carries Excited=True by default
    # (``LumpedPort._ensure_properties``), so a user who adds a second port the
    # obvious way gets a deck that drives BOTH — and openEMS accepts it. The
    # post-processing below then computes s11 = uf_ref/uf_inc for port 1 as if
    # it were the only source, so port 1's incident wave is contaminated by
    # port 2's drive and the S-parameters are silently wrong. No exception, no
    # warning, a plausible-looking answer. Reproduced live 2026-08-20.
    # The shipped templates are unaffected — msl_filter sets port2.Excited =
    # False explicitly — and FullSMatrix is unaffected too, because its runner
    # drives one port per excitation and clears the rest.
    n_excited = sum(1 for p in ports if p["excite"])
    if n_excited > 1:
        raise OpenEMSModelError(
            "openEMS solves ONE excitation per run, but {0} ports are marked "
            "Excited: {1}. Un-tick Excited on all but one, or use the "
            "FullSMatrix option, which drives each port in turn and merges "
            "the columns into a full S-matrix.".format(
                n_excited,
                ", ".join("port {0}".format(p.get("nr", "?"))
                          for p in ports if p["excite"])))
    if not any(p["excite"] for p in ports):
        raise OpenEMSModelError(
            "the analysis needs exactly one excited port"
            + ("" if not excite_port else
               " — port {0} was requested but the analysis has no such port"
               .format(excite_port)))
    return ports


#: Real air the guard insists on between the geometry and the ABSORBER, as a
#: fraction of the centre wavelength, when it has to step in. Upstream's own
#: horn tutorial uses lambda/2 to the sides and front and lambda/4 behind, on
#: top of its PML allowance (Horn_Antenna.py); a quarter wavelength is the
#: smaller of the two and is what a rescue should restore — enough for the
#: reactive near field to form before it is absorbed, without silently
#: inflating a domain by more than the situation demands.
MIN_ABSORBER_CLEARANCE_WAVELENGTHS = 0.25


def _geometry_bbox(mats):
    """Tight bounding box over every emitted primitive."""
    inf = float("inf")
    lo = [inf, inf, inf]
    hi = [-inf, -inf, -inf]
    for m in mats:
        for p in m["prims"]:
            for i in range(3):
                lo[i] = min(lo[i], p["start"][i])
                hi[i] = max(hi[i], p["stop"][i])
    return lo, hi


def absorber_depth_mm(boundary, mesh_res_mm):
    """How much of a face's padding the ABSORBER occupies, in mm.

    ⚠ PML_N eats N cells of mesh, and openEMS then places the NF2FF recording
    surface one line further in (``CreateNF2FFBox``: ``BC_size = PML_size + 1``),
    so the depth that matters to a radiating model is **N + 1**, not N. Using N
    leaves the recording surface itself inside the structure, which is the
    failure that produced a -60 dBi pattern floor with eta = nan.

    MUR costs 2 lines by the same rule and PEC/PMC cost none (those faces are
    mirrored, not recorded). Returning 0 for them is what keeps this guard from
    touching the shipped MUR templates.
    """
    bc = str(boundary)
    if bc.startswith("PML_"):
        try:
            return (int(bc[4:]) + 1) * float(mesh_res_mm)
        except ValueError:
            return 0.0            # _nf2ff_bc refuses this properly, with a message
    if bc == "MUR":
        return 2.0 * float(mesh_res_mm)
    return 0.0


def _domain(analysis, mats, lam_c_mm, mesh_res_mm=None, boundaries=None):
    """(geo_lo, geo_hi, dom_lo, dom_hi, notes).

    Simulation box = geometry bbox + ``DomainPaddingWavelengths`` on every side
    — and then, if an ABSORBING boundary would start inside that padding, the
    face is pushed out far enough to clear it.

    ⚠⚠ WHY THE GUARD EXISTS. ``DomainPaddingWavelengths`` defaults to 0.25,
    which was chosen for MUR — a one-cell condition, so 0.25 lambda of padding
    is 0.25 lambda of air. PML_8 is EIGHT cells deep (nine, counting the NF2FF
    surface), and its depth is set by the MESH, not by the wavelength. At Ka
    band on the shipped horn that is 3.373 mm against 2.254 mm of padding:
    MEASURED, the absorber's inner face lands 0.372 mm INSIDE the geometry on
    all six sides, and the NF2FF surface 0.745 mm inside. The first horn run
    done that way returned the -60 dBi pattern floor with eta = nan, because
    the port accepted no power at all.
    ⛳ Upstream sizes its domain the same way and says so:
    ``bc_offset = 9  # PML_8 + 1 cell, matches CreateNF2FFBox placement`` then
    ``margin = lam0/2 + bc_offset*max_res`` (Horn_Antenna.py).

    ⚠ IT ENLARGES, IT DOES NOT RAISE. Refusing would break documents that run
    today and produce a plausible answer; growing the box costs cells and says
    so in the deck and in ``notes``. It fires ONLY when the absorber would
    otherwise start at or inside the geometry, so a model with adequate padding
    — including every shipped MUR template and the horn at its own 1.0 lambda —
    is untouched, byte for byte.
    """
    lo, hi = _geometry_bbox(mats)
    pad = float(analysis.DomainPaddingWavelengths) * lam_c_mm
    dom_lo = [c - pad for c in lo]
    dom_hi = [c + pad for c in hi]
    grown, thin = [], []
    if mesh_res_mm is None or boundaries is None:
        return lo, hi, dom_lo, dom_hi, (grown, thin)
    floor = MIN_ABSORBER_CLEARANCE_WAVELENGTHS * lam_c_mm
    for i in range(3):
        for side, (bc, box, sign) in enumerate((
                (boundaries[2 * i], dom_lo, -1.0),
                (boundaries[2 * i + 1], dom_hi, +1.0))):
            # ⚠ ``depth`` is an UPPER BOUND, not a measurement: SmoothMeshLines
            # guarantees only that no cell EXCEEDS mesh_res, so the outer N+1
            # cells are at most (N+1)*mesh_res and are smaller wherever grading
            # has begun (measured on this horn: 96.2 % of the bound). Say
            # "needs up to", never "is" — quoting a bound as a measurement is
            # the same defect this guard exists to catch.
            depth = absorber_depth_mm(bc, mesh_res_mm)
            if depth <= 0.0:
                continue
            air = pad - depth
            face = "{0}{1}".format(AXES[i], "min" if sign < 0 else "max")
            if air > floor:
                continue
            if air > 0.0:
                # Thin, but the absorber is still outside the structure. Moving
                # the domain here would change results for models that run
                # correctly today, so this only tells the truth about itself.
                # ⚠ ADVISE ONLY FOR A REAL ABSORBER. MUR's two lines are where
                # openEMS places the NF2FF surface, not an absorbing depth —
                # a one-cell condition has no clearance to be short of. Warning
                # about it would put six lines of noise on the validated patch
                # template, whose padding is entirely adequate.
                if not bc.startswith("PML_"):
                    continue
                thin.append(
                    "{face}: {bc} plus its recording surface needs up to "
                    "{depth:.4g} mm of the {pad:.4g} mm padding, leaving about "
                    "{air:.4g} mm ({lam:.3g} lambda) of clear air. That works, "
                    "but a radiating model wants nearer {want:g} lambda — raise "
                    "DomainPaddingWavelengths if the pattern looks "
                    "boundary-limited.".format(
                        face=face, bc=bc, depth=depth, pad=pad, air=air,
                        lam=air / lam_c_mm,
                        want=MIN_ABSORBER_CLEARANCE_WAVELENGTHS))
                continue
            want = depth + floor
            box[i] = (lo[i] - want) if sign < 0 else (hi[i] + want)
            grown.append(
                "{face}: {bc} plus its recording surface needs up to "
                "{depth:.4g} mm, but the padding is only {pad:.4g} mm — the "
                "absorber would start inside the geometry. Domain pushed out "
                "to {want:.4g} mm on this face ({clear:g} lambda of clear "
                "air).".format(face=face, bc=bc, depth=depth, pad=pad,
                               want=want,
                               clear=MIN_ABSORBER_CLEARANCE_WAVELENGTHS))
    return lo, hi, dom_lo, dom_hi, (grown, thin)


def _dielectric_thin_axis_lines(prim):
    """(axis, min, max) of the thinnest axis of a dielectric box (substrate)."""
    dims = [prim["stop"][i] - prim["start"][i] for i in range(3)]
    axis = int(min(range(3), key=lambda i: dims[i] if dims[i] > 0 else float("inf")))
    return axis, prim["start"][axis], prim["stop"][axis]


# --------------------------------------------------------------------------- writer
def write_deck(analysis, solver, workdir, excite_port=None):
    """Write case_openems.py + geometry files. Returns (deck_path, z0)."""
    f1, f2, npts = Analysis.freq_range_hz(analysis)
    f0 = 0.5 * (f1 + f2)
    fc = 0.5 * (f2 - f1)
    if fc <= 0:
        raise OpenEMSModelError("FrequencyStop must be greater than FrequencyStart")

    mats = _collect_materials(analysis, workdir)
    # ⚠ An excited waveguide port's probe plane must clear its excitation
    # plane by whole mesh cells, so _collect_ports needs the cell size
    # BEFORE the mesh block below computes it. The microstrip branch can
    # only make the grid FINER, so this plain-air value is a safe lower
    # bound for the one port type that depends on it.
    cell_mm = C0 / (f0 + fc) / 1e-3 / max(6, int(analysis.MeshResolution))
    ports = _collect_ports(analysis, excite_port=excite_port,
                           cell_mm=cell_mm)
    z0 = [p["R"] for p in ports if p["excite"]][0]

    # Trace-aware meshing for microstrip (MSL) ports: resolve the grid in the
    # DIELECTRIC (lambda/50) rather than in air, and grade it across the narrow
    # strip, so the port can self-extract its characteristic impedance. Without
    # this the sub-mm trace gets <1 cell and S-params come out non-physical
    # (|S|>1). Gated so antenna analyses (lumped ports) stay byte-identical.
    has_msl = any(p["type"] == "MSL" for p in ports)
    msl_mesh = has_msl and str(getattr(solver, "MicrostripMeshMode", "Auto")) == "Auto"

    # Critical grid coordinates that MUST survive smoothing bit-exactly: every
    # primitive/port boundary plane. openEMS's SmoothMeshLines can return fixed
    # lines perturbed by ~1 ULP (observed: 1.524 -> 1.524000000000001, v0.37.0-rc1),
    # which silently drops zero-thickness metal from the simulation. The deck snaps
    # the smoothed grid back onto these values (see _snap in the generated deck).
    criticals = {0: set(), 1: set(), 2: set()}
    for m in mats:
        for p in m["prims"]:
            for i in range(3):
                criticals[i].add(p["start"][i])
                criticals[i].add(p["stop"][i])
    for p in ports:
        for i in range(3):
            criticals[i].add(p["start"][i])
            criticals[i].add(p["stop"][i])

    lam_c_mm = C0 / f0 * 1000.0
    if msl_mesh:
        # lambda/50 in the highest-permittivity dielectric (the substrate).
        eps_max = max([m["epsR"] for m in mats if m["kind"] == "dielectric"] or [1.0])
        n_lines = max(50, int(analysis.MeshResolution))
        mesh_res_mm = C0 / f2 / math.sqrt(eps_max) / 1e-3 / n_lines
    else:
        mesh_res_mm = C0 / (f0 + fc) / 1e-3 / max(6, int(analysis.MeshResolution))
    _refuse_unresolvable(mats, mesh_res_mm)
    boundaries = Analysis.boundary_list(analysis)
    # ⚠ The absorber guard is skipped on the microstrip path DELIBERATELY: that
    # branch below throws the padded box away and hugs the geometry so the line
    # runs INTO the PML, which is what makes the termination matched. Giving it
    # air would strand the line end short of the absorber — the |S| > 1 failure
    # the branch's own comment describes.
    geo_lo, geo_hi, dom_lo, dom_hi, (pad_grown, pad_thin) = _domain(
        analysis, mats, lam_c_mm,
        mesh_res_mm=None if msl_mesh else mesh_res_mm,
        boundaries=None if msl_mesh else boundaries)
    if msl_mesh:
        # A microstrip is a GUIDED (not radiating) structure, so the antenna-
        # style 0.25-wavelength air padding is wrong on every face:
        #  * in the propagation/transverse plane it strands the line end in open
        #    air short of the PML, breaking the matched termination (|S|>1), and
        #  * below z=0 it detaches the strip from the PEC-Zmin ground plane.
        # Hug the geometry: the substrate/line run to the absorbing boundary
        # (PML on the line axis, MUR transverse), the domain bottom sits on the
        # ground (z-min), and only a thin air lid caps the top for the fringing
        # field. This also cuts the cell count ~10x vs the padded box.
        sub_th = geo_hi[2] - geo_lo[2]
        dom_lo = list(geo_lo)
        dom_hi = list(geo_hi)
        dom_hi[2] = geo_hi[2] + max(12.0 * sub_th, 1.0)
    end_criteria = 10.0 ** (float(solver.EndCriteriaDB) / 10.0)
    nr_ts = max(1000, int(solver.MaxTimesteps))

    L = []
    w = L.append
    w("# Auto-generated by EMStudio — openEMS FDTD deck")
    w("# Analysis: {0}".format(analysis.Label))
    w("import os, sys")
    w("import numpy as np")
    w("from CSXCAD import ContinuousStructure")
    w("from openEMS import openEMS")
    w("")
    w("sim_path = os.path.dirname(os.path.abspath(__file__))")
    w("preview_only = '--preview' in sys.argv")
    w("")
    w("FDTD = openEMS(NrTS={0}, EndCriteria={1:.6g})".format(nr_ts, end_criteria))
    w("FDTD.SetGaussExcite({0:.9g}, {1:.9g})".format(f0, fc))
    w("FDTD.SetBoundaryCond({0!r})".format(list(boundaries)))
    w("")
    w("CSX = ContinuousStructure()")
    w("FDTD.SetCSX(CSX)")
    w("mesh = CSX.GetGrid()")
    w("mesh.SetDeltaUnit(1e-3)  # drawing unit: mm")
    w("mesh_res = {0:.9g}".format(mesh_res_mm))
    w("")
    for _n in pad_grown + pad_thin:
        # A domain that grew for a reason the user cannot see is the same class
        # of defect as a field that changes nothing: say it in the deck, and say
        # it again on stdout so it reaches the solver log the runner captures.
        w("# EMStudio absorber guard — " + _n)
    if pad_grown:
        w("print({0!r})".format(
            "EMStudio: domain ENLARGED so the absorbing boundary clears the "
            "geometry — " + " ".join(pad_grown)))
    for _n in pad_thin:
        # Advisory only: nothing moved, so it must not claim anything did.
        w("print({0!r})".format("EMStudio: absorber clearance is thin — " + _n))
    if pad_grown or pad_thin:
        w("")
    w("# simulation domain")
    w("mesh.AddLine('x', [{0:.9g}, {1:.9g}])".format(dom_lo[0], dom_hi[0]))
    w("mesh.AddLine('y', [{0:.9g}, {1:.9g}])".format(dom_lo[1], dom_hi[1]))
    w("mesh.AddLine('z', [{0:.9g}, {1:.9g}])".format(dom_lo[2], dom_hi[2]))
    w("")

    for m in mats:
        w("# --- material: {0} ({1}) ---".format(m["name"], m["kind"]))
        if m["kind"] == "metal":
            w("{0} = CSX.AddMetal('{0}')".format(m["name"]))
        elif m["kind"] == "conducting_sheet":
            # ⛳ CSPropConductingSheet is documented "Only 2D primitives
            # (sheets) should be added to this property". A solid handed to it
            # is not a supported model, so we say so and fall back to PEC
            # LOUDLY rather than emit something openEMS will interpret in a way
            # nobody predicted. Silence here would recreate the exact defect
            # this branch exists to fix.
            solid = any(p["kind"] != "box" or p["sheet_axis"] is None
                        for p in m["prims"])
            if solid:
                w("print('EMStudio: WARNING - material {0} is a SOLID; the "
                  "finite-conductivity sheet model needs a 2-D sheet, so it "
                  "is modelled as PEC (lossless). Gain/Q will be optimistic.')"
                  .format(m["name"]))
                w("{0} = CSX.AddMetal('{0}')".format(m["name"]))
            else:
                w("{0} = CSX.AddConductingSheet('{0}', conductivity={1:.9g}, "
                  "thickness={2:.9g})".format(m["name"], m["sigma"],
                                              m["thickness_m"]))
        else:
            kappa = m["kappa"]
            if kappa <= 0 and m["tanD"] > 0:
                kappa = m["tanD"] * 2 * math.pi * f0 * EPS0 * m["epsR"]
            extra = ""
            if kappa > 0:
                extra += ", kappa={0:.9g}".format(kappa)
            if m["mu"] not in (0.0, 1.0):
                extra += ", mue={0:.9g}".format(m["mu"])
            w("{0} = CSX.AddMaterial('{0}', epsilon={1:.9g}{2})".format(m["name"], m["epsR"], extra))
        sheet_dirs = set()
        has_solid = False
        for p in m["prims"]:
            if p["kind"] == "box":
                w(
                    "{0}.AddBox(priority={1}, start={2}, stop={3})".format(
                        m["name"], m["priority"], _fmt_v(p["start"]), _fmt_v(p["stop"])
                    )
                )
                if p["sheet_axis"] is None:
                    has_solid = True
                else:
                    sheet_dirs.add("".join(a for i, a in enumerate(AXES) if i != p["sheet_axis"]))
            else:  # stl
                w(
                    "{0}.AddPolyhedronReader(r'{1}', priority={2}).ReadFile()".format(
                        m["name"], os.path.basename(p["path"]), m["priority"]
                    )
                )
                # anchor the STL bbox in the grid on all axes
                for i, a in enumerate(AXES):
                    w(
                        "mesh.AddLine('{0}', [{1:.9g}, {2:.9g}])".format(
                            a, p["start"][i], p["stop"][i]
                        )
                    )
                # LOCAL REFINEMENT. Until v0.84.0 an STL body got these six
                # bounding-box lines and nothing else, so the only thing
                # sizing the cells inside it was the global mesh_res — a body
                # thinner than one cell was represented by no cells at all,
                # silently. Lay a grid across the body's own bounding box fine
                # enough to resolve its smallest feature, but only when that
                # is affordable; _stl_refinement decides and returns None when
                # it is not (the caller has already refused the hopeless case).
                ref = _stl_refinement(p, mesh_res_mm)
                if ref is not None:
                    step, counts = ref
                    w("# resolve this body's own {0:.4g} mm feature "
                      "({1} x {2} x {3} lines at {4:.4g} mm)".format(
                          p.get("min_feature") or 0.0, counts[0], counts[1],
                          counts[2], step))
                    for i, a in enumerate(AXES):
                        if counts[i] <= 2:
                            continue
                        w("mesh.AddLine('{0}', np.linspace({1:.9g}, {2:.9g}, "
                          "{3:d}).tolist())".format(
                              a, p["start"][i], p["stop"][i], counts[i]))
                has_solid = True    # an STL body is a solid: it wants the
                                    # metal-edge thirds rule like any other
        if m["kind"] == "metal":
            if has_solid:
                w("FDTD.AddEdges2Grid(dirs='all', properties={0}, metal_edge_res=mesh_res/2)".format(m["name"]))
            for dirs in sorted(sheet_dirs):
                w("FDTD.AddEdges2Grid(dirs='{0}', properties={1}, metal_edge_res=mesh_res/2)".format(dirs, m["name"]))
        else:
            # discretize thin dielectrics (substrates) across their thickness —
            # bbox-based, so it applies to STL-imported substrates as well
            for p in m["prims"]:
                axis, a1, a2 = _dielectric_thin_axis_lines(p)
                if 0 < (a2 - a1) < mesh_res_mm * 2:
                    w(
                        "mesh.AddLine('{0}', np.linspace({1:.9g}, {2:.9g}, 5).tolist())".format(
                            AXES[axis], a1, a2
                        )
                    )
        w("")

    if msl_mesh:
        # Build the trace-aware grid BEFORE AddMSLPort: the strip width gets a
        # thirds-rule refinement, the propagation axis and substrate thickness
        # are graded to mesh_res. AddMSLPort requires >=5 lines already present
        # along the line, and the port's Zc extraction needs the strip resolved.
        w("# --- trace-aware grid for microstrip (MSL) ports ---")
        for p in ports:
            if p["type"] != "MSL":
                continue
            prop_axis = p["prop_axis"]
            exc_i = AXES.index(p["axis"])
            prop_i = AXES.index(prop_axis)
            width_i = ({0, 1, 2} - {prop_i, exc_i}).pop()
            width_axis = AXES[width_i]
            w_lo = min(p["start"][width_i], p["stop"][width_i])
            w_hi = max(p["start"][width_i], p["stop"][width_i])
            w("third = mesh_res / 3.0")
            w("mesh.AddLine('{0}', [{1:.9g}+2*third/4, {1:.9g}-third/4, "
              "{2:.9g}+2*third/4, {2:.9g}-third/4])".format(width_axis, w_lo, w_hi))
            w("mesh.SmoothMeshLines('{0}', mesh_res/4)".format(width_axis))
            w("mesh.SmoothMeshLines('{0}', mesh_res)".format(prop_axis))
        w("mesh.SmoothMeshLines('z', mesh_res)")
        w("")

    w("# --- ports ---")
    w("ports = {}")
    needs_port_pec = any(p["type"] == "MSL" for p in ports)
    if needs_port_pec:
        w("port_pec = CSX.AddMetal('port_pec')")
    for p in ports:
        if p["type"] == "MSL":
            # feed/measure offsets along the line. CRITICAL: the feed must sit well
            # BEFORE the measurement plane, else the incident-wave estimate is taken
            # downstream of the source and S-params come out non-physical (>0 dB).
            # With EMStudio's coarser antenna-scale mesh, 10*mesh_res (tutorial value
            # for its fine mesh) can exceed MeasPlaneShift — so cap the feed shift.
            i = AXES.index(p["prop_axis"])
            span = abs(p["stop"][i] - p["start"][i])
            meas = span / 3.0
            w(
                "ports[{nr}] = FDTD.AddMSLPort({nr}, port_pec, {start}, {stop}, "
                "'{pax}', '{eax}', excite={excite:.1f}, "
                "FeedShift=min(10*mesh_res, {feed:.9g}), MeasPlaneShift={mps:.9g}, "
                "priority=10)".format(
                    nr=p["nr"], start=_fmt_v(p["start"]), stop=_fmt_v(p["stop"]),
                    pax=p["prop_axis"], eax=p["axis"], excite=p["excite"],
                    feed=meas / 2.0, mps=meas,
                )
            )
        elif p["type"] == "RectWaveguide":
            # AddRectWaveGuidePort builds the analytic TE_mn profile (Pozar) and
            # imposes it on the port plane. Unlike a lumped port it is a real
            # modal excitation, which is what a horn or a filter fed from guide
            # actually needs — and what EMStudio had no way to express until
            # v1.5.0, leaving antenna/horn.py's design_pyramidal a designer with
            # no solver that could feed it.
            w(
                "ports[{nr}] = FDTD.AddRectWaveGuidePort({nr}, {start}, {stop}, "
                "'{pax}', {a:.9g}, {b:.9g}, '{mode}', excite={excite:.1f})".format(
                    nr=p["nr"], start=_fmt_v(p["start"]), stop=_fmt_v(p["stop"]),
                    pax=p["prop_axis"], a=p["wg_a_m"], b=p["wg_b_m"],
                    mode=p["wg_mode"], excite=p["excite"],
                )
            )
        else:
            w(
                "ports[{nr}] = FDTD.AddLumpedPort({nr}, {R:.9g}, {start}, {stop}, "
                "'{axis}', excite={excite:.1f}, priority=5, edges2grid='{e2g}')".format(
                    nr=p["nr"], R=p["R"], start=_fmt_v(p["start"]), stop=_fmt_v(p["stop"]),
                    axis=p["axis"], excite=p["excite"], e2g=p["edges2grid"],
                )
            )
    w("")
    compute_ff = bool(getattr(solver, "ComputeFarField", False))
    # MSL ports need the mesh resolved across the narrow strip width (thirds rule)
    # and along the line — the antenna auto-gridder doesn't know the strip exists
    # (it is created by AddMSLPort, not drawn as metal).
    for p in ports:
        if p["type"] != "MSL":
            continue
        prop_i = AXES.index(p["prop_axis"])
        exc_i = AXES.index(p["axis"])
        width_i = ({0, 1, 2} - {prop_i, exc_i}).pop()
        width_axis = AXES[width_i]
        w_lo = min(p["start"][width_i], p["stop"][width_i])
        w_hi = max(p["start"][width_i], p["stop"][width_i])
        w("# MSL port {0}: thirds-rule mesh across the {1}-width strip".format(p["nr"], width_axis))
        w("third = mesh_res / 3.0")
        w("mesh.AddLine('{0}', [{1:.9g}+2*third/4, {1:.9g}-third/4, {2:.9g}+2*third/4, {2:.9g}-third/4])".format(
            width_axis, w_lo, w_hi))
        w("mesh.SmoothMeshLines('{0}', mesh_res/4)".format(width_axis))
    w("")
    w("mesh.SmoothMeshLines('all', mesh_res, {0:.4g})".format(float(analysis.MeshSmoothRatio)))
    w("")
    w("# Snap smoothed lines back onto critical geometry planes (SmoothMeshLines can")
    w("# perturb fixed lines by ~1 ULP, silently dropping zero-thickness metal).")
    w("def _snap(vals, criticals, tol=1e-6):")
    w("    vals = list(vals)")
    w("    for i, v in enumerate(vals):")
    w("        for c in criticals:")
    w("            if abs(v - c) <= tol:")
    w("                vals[i] = c")
    w("                break")
    w("    return sorted(set(vals))")
    w("")
    for i, ax in enumerate(AXES):
        vals = sorted(criticals[i])
        w("mesh.SetLines('{0}', _snap(mesh.GetLines('{0}'), {1}))".format(
            ax, "[" + ", ".join("{0:.9g}".format(v) for v in vals) + "]"))
    w("")
    if compute_ff:
        wg_exc = next((p for p in ports
                       if p["excite"] and p["type"] == "RectWaveguide"), None)
        if wg_exc is None:
            # Every other analysis keeps openEMS's own automatic box, byte for
            # byte. The deviation below is confined to waveguide-fed models on
            # purpose: it is the only port type that launches a wave BACKWARDS
            # out of the structure.
            w("nf2ff_box = FDTD.CreateNF2FFBox()")
        else:
            # ⚠⚠ THE NF2FF BOX MUST NOT ENCLOSE A WAVEGUIDE PORT'S BACKWARD
            # WAVE. openEMS's waveguide port is a SOFT source on a plane
            # (CSX.AddExcitation with a zero-thickness box, openEMS/ports.py),
            # so it launches the mode in BOTH directions. The forward half feeds
            # the antenna; the backward half runs out of the guide's open end and
            # is absorbed by the boundary — but ``CreateNF2FFBox`` wraps all six
            # faces, so that half crosses the recording surface and is counted as
            # RADIATED POWER. Directivity is 4*pi*U_max/P_rad, so inflating P_rad
            # deflates the reported directivity.
            # ⛳ MEASURED on the shipped Ka-band horn, one run and two recording
            # boxes over identical fields:
            #     all six faces   D = 16.113 dBi, 40.7 % of P_rad going BACKWARDS
            #     -z face off     D = 18.252 dBi,  4.1 %
            # 2.14 dB, and it is most of the "~3 dB low" the horn gate was red
            # for. ⚠ It is NOT aperture illumination: the same run's aperture
            # dump matches the analytic cosine to 2.35 % RMS.
            # ⛳ This is upstream's own convention — Horn_Antenna.m passes
            # ``'Directions',[1 1 1 1 0 1]`` for exactly this reason. The python
            # Horn_Antenna.py can keep all six only because its guide is closed
            # by a back-short and has no backward wave to lose.
            # ⚠ CreateNF2FFBox passes ``directions=`` itself, so it cannot be
            # overridden through **kw — the box has to be built by hand, which
            # means replicating its start/stop rule (below) exactly.
            bc_size, dirs, mirror = _nf2ff_bc(boundaries)
            pi = AXES.index(wg_exc["prop_axis"])
            back_is_min = wg_exc["prop_sign"] >= 0
            dirs[2 * pi + (0 if back_is_min else 1)] = 0
            # ...and pull that face up to the excitation plane, so the whole
            # backward region is outside the box rather than merely unrecorded
            # on one face. Measured: back-hemisphere power 4.1 % -> 2.2 %.
            plane = wg_exc["start"][pi]
            w("from openEMS.nf2ff import nf2ff as _NF2FF")
            w("# NF2FF surface: openEMS places it PML_N+1 lines in (MUR: 2, "
              "PEC/PMC: 0 with mirroring) — CreateNF2FFBox's own rule.")
            w("_bc_size = {0!r}".format(bc_size))
            w("_lines = [list(mesh.GetLines(_a)) for _a in 'xyz']")
            w("_nf_start = [_lines[_n][_bc_size[2*_n]] for _n in range(3)]")
            w("_nf_stop = [_lines[_n][-_bc_size[2*_n+1]-1] for _n in range(3)]")
            w("# the face behind the excited waveguide port, clamped to its "
              "excitation plane and switched off")
            if back_is_min:
                w("_nf_start[{0}] = max(_nf_start[{0}], {1:.9g})".format(pi, plane))
            else:
                w("_nf_stop[{0}] = min(_nf_stop[{0}], {1:.9g})".format(pi, plane))
            w("if _nf_start[{0}] >= _nf_stop[{0}]:".format(pi))
            w("    raise SystemExit('EMStudio: the NF2FF box collapsed along "
              "{0} — the waveguide port plane is outside the recording "
              "region'.format('{0}'))".format(AXES[pi]))
            w("nf2ff_box = _NF2FF(CSX, 'nf2ff', _nf_start, _nf_stop, "
              "directions={0!r}, mirror={1!r})".format(dirs, mirror))
            w("print('EMStudio: NF2FF box %r -> %r, face %d off (waveguide "
              "port backward wave)' % (_nf_start, _nf_stop, {0}))".format(
                  2 * pi + (0 if back_is_min else 1)))
        w("")
    nf_plane = str(getattr(solver, "NearFieldPlane", "None"))
    if nf_plane in ("XY", "XZ", "YZ"):
        # FD |E| dump on a cut plane through the geometry-bbox center, recorded at
        # the sweep center frequency (FD dumps need the frequency before Run).
        # ⚠ The real geometry bbox, not dom -/+ padding. That reconstruction
        # was only ever correct when the padding was uniform; the guard above
        # can now enlarge one face and not its opposite, and the microstrip
        # branch discards the padding altogether.
        center = [(geo_lo[i] + geo_hi[i]) / 2.0 for i in range(3)]
        flat_axis = {"XY": 2, "XZ": 1, "YZ": 0}[nf_plane]
        d_start = list(dom_lo)
        d_stop = list(dom_hi)
        d_start[flat_axis] = d_stop[flat_axis] = center[flat_axis]
        w("# near-field FD |E| dump ({0} plane at geometry center, f0)".format(nf_plane))
        w("nf_dump = CSX.AddDump('Ef_fd', dump_type=10, file_type=1, frequency=[{0:.9g}])".format(f0))
        w("nf_dump.AddBox({0}, {1})".format(_fmt_v(d_start), _fmt_v(d_stop)))
        w("")
    w("if preview_only:")
    w("    CSX.Write2XML(os.path.join(sim_path, 'case.xml'))")
    w("    print('CSX geometry written to case.xml (open with AppCSXCAD)')")
    w("    sys.exit(0)")
    w("")
    w("print('EMStudio: starting openEMS run (NrTS={0}, EndCriteria={1:.3g})...')".format(nr_ts, end_criteria))
    w("FDTD.Run(sim_path, cleanup=False)")
    w("")
    w("# --- post-processing: S-parameters in the shared EMStudio CSV schema ---")
    w("f = np.linspace({0:.9g}, {1:.9g}, {2})".format(f1, f2, npts))
    excited = [p for p in ports if p["excite"]][0]
    wg_nrs = sorted(p["nr"] for p in ports if p["type"] == "RectWaveguide")
    if wg_nrs:
        # ⚠⚠ A WAVEGUIDE PORT MUST KEEP ITS OWN MODAL IMPEDANCE.
        # ``WaveguidePort.CalcPort`` computes the analytic TE wave impedance
        # ZL(f) = k*Z0/beta and uses it as the reference — unless a caller hands
        # it one, in which case ``Port.CalcPort`` overwrites it. This writer used
        # to hand EVERY port the excited port's ``R`` (50 ohm), which for WR-28
        # at 30 GHz replaces 529 ohm with 50 and destroys the incident/reflected
        # split.
        # ⛳ MEASURED on a straight PEC-walled WR-28 section terminated in PML —
        # a PERFECTLY MATCHED line, where the answer must be |S11| ~ 0 and
        # P_acc/P_inc = 1 (tests/validation/waveguide_port_openems.py):
        #     ref_impedance=50    -> |S11| = -1.64 dB, P_acc/P_inc = 0.314
        #     ref_impedance=None  -> |S11| = -50.9 dB, P_acc/P_inc = 1.0000
        # This is where ``P_rad/P_acc = 1642 %`` came from: with the power split
        # wrong, P_acc is not the accepted power and the efficiency it feeds is
        # not an efficiency.
        # ⚠ A lumped or MSL port still gets its own R — do not widen this.
        w("_WG_PORTS = {0!r}  # modal Z_ref, never 50 ohm".format(wg_nrs))
        w("for _nr, _p in ports.items():")
        w("    _p.CalcPort(sim_path, f, ref_impedance=("
          "None if _nr in _WG_PORTS else {0:.9g}))".format(z0))
    else:
        w("for _p in ports.values():")
        w("    _p.CalcPort(sim_path, f, ref_impedance={0:.9g})".format(z0))
    w("port = ports[{0}]".format(excited["nr"]))
    w("s11 = port.uf_ref / port.uf_inc")
    w("zin = port.uf_tot / port.if_tot")
    if excited["nr"] in wg_nrs:
        # The z0 COLUMN must say what the S-parameters are actually referenced
        # to, or the row is self-contradictory: zin ~ 530 ohm beside a 50 in the
        # reference column invites every reader to recompute s11 and get a
        # different answer. A waveguide's modal impedance varies with frequency,
        # and the column is per-row, so it can carry it exactly.
        # ⚠ Touchstone cannot: ``SweepResult`` keeps the FIRST row's value
        # (post/sparams.py) and ``write_touchstone`` emits one ``R`` for the
        # whole file. That is a Touchstone limitation, not a new inaccuracy —
        # but do not read the .s1p's R as valid across the band.
        w("z0_col = np.real(np.ravel(port.ZL))  # modal TE impedance, per frequency")
    else:
        w("z0_col = np.full_like(f, {0:.9g})".format(z0))
    w("rows = np.column_stack([f, zin.real, zin.imag, s11.real, s11.imag, z0_col])")
    w("np.savetxt(os.path.join(sim_path, 'port_{0}.csv'.format({0})), rows, delimiter=',',".format(excited["nr"]))
    w("           header='freq_hz,re_zin,im_zin,re_s11,im_s11,z0', comments='')")
    for p in ports:
        if p["nr"] == excited["nr"]:
            continue
        w("s_t = ports[{0}].uf_ref / port.uf_inc  # S{0}{1}".format(p["nr"], excited["nr"]))
        w("np.savetxt(os.path.join(sim_path, 'sparam_{0}_{1}.csv'),".format(p["nr"], excited["nr"]))
        w("           np.column_stack([f, s_t.real, s_t.imag]), delimiter=',',")
        w("           header='freq_hz,re_s,im_s', comments='')")
    if compute_ff:
        # Radiator phase center: middle of the domain bbox. CalcNF2FF's ``center``
        # is in METERS, not drawing units (the tutorial passes [0,0,1e-3] for a
        # point 1 mm up) — passing mm values puts the center far outside the
        # recording box and yields NaN directivity (observed 2026-07-05).
        center = [(dom_lo[i] + dom_hi[i]) / 2.0 * 1e-3 for i in range(3)]
        # WHICH frequencies get a pattern. PatternFrequencies / PatternFreqStart
        # / PatternFreqStop mean here exactly what they mean on NEC2 — 0 = one
        # pattern at the default frequency, N > 1 = N across the band — so the
        # same dialog and the same results picker serve both backends.
        # ⚠ On openEMS the COST IS NOT NEC2's. The NF2FF box is recorded
        # broadband in the time domain, so every extra frequency is one more
        # transform of data the run already holds: no extra solve, no extra
        # solver output. One CalcNF2FF call takes the whole list.
        pat_idx = _pattern_indices(solver, f1, f2, npts)
        w("")
        w("# --- far field (NF2FF) ---")
        w("s11_db = 20*np.log10(np.maximum(np.abs(s11), 1e-30))")
        if pat_idx:
            w("ff_idx = {0!r}".format(pat_idx))
        else:
            # ⚠⚠ argmin|S11| IS ONLY MEANINGFUL IF THERE IS A RESONANCE TO
            # FIND. On a broadband, well-matched antenna S11 is flat and the
            # argmin lands on numerical noise: measured, the SAME Ka-band horn
            # chose 28.45 GHz at one mesh density and 39.55 GHz at another,
            # which makes any comparison against a published gain curve
            # accidental.
            # ⛳ The fallback is the sweep CENTRE, and specifically that: it is
            # already the Gaussian excitation centre a few lines above, so it
            # is the best-conditioned bin in the recording; it is already the
            # near-field dump frequency; and it is deterministic and
            # mesh-independent.
            # ⚠ Resonant documents are UNTOUCHED. A patch, dipole or notch has
            # far more than {flat:g} dB of S11 range, so the branch below never
            # fires on them and their reported frequency does not move.
            w("if float(s11_db.max() - s11_db.min()) < {flat:g}:".format(
                flat=FLAT_S11_SPAN_DB))
            w("    i_ff = int(np.argmin(np.abs(f - {0:.9g})))".format(f0))
            w("    print('EMStudio: S11 varies by only %.2f dB across the band"
              " — there is no resonance to pick, so the pattern is taken at the"
              " sweep centre %.4g Hz. Set PatternFrequencies to choose your"
              " own.' % (float(s11_db.max() - s11_db.min()), f[i_ff]))")
            w("else:")
            w("    i_ff = int(np.argmin(s11_db))")
            w("ff_idx = [i_ff]")
        w("f_ff_list = [float(f[_i]) for _i in ff_idx]")
        w("f_ff = f_ff_list[0]")
        w("# full sphere for 3-D balloon plots (phi=0/90 columns feed the 2-D cuts)")
        w("theta = np.arange(0.0, 180.1, 5.0)")
        w("phi = np.arange(0.0, 360.0, 5.0)")
        w("ff = nf2ff_box.CalcNF2FF(sim_path, f_ff_list, theta, phi, center={0})".format(_fmt_v(center)))
        # ⚠⚠ ``ff.Dmax`` IS DIRECTIVITY, NOT GAIN. Until 2026-08-22 this block
        # wrote Dmax straight into a column headed ``gain_dbi``, and
        # emstudio/post/farfield.py documents that column as "Gain pattern
        # G(theta, phi) in dBi". They are equal ONLY for a lossless antenna.
        # This writer emits lossy dielectrics (kappa synthesised from
        # tan(delta) a few lines above), so every lossy model shipped a number
        # that OVERSTATED gain by exactly the radiation efficiency — the
        # dangerous direction, in a product whose whole claim is checkable
        # numbers.
        # ⛳ G = D * eta_rad, with eta_rad = P_radiated / P_accepted. openEMS
        # gives both directly: nf2ff carries Prad, and CalcPort leaves P_acc on
        # the port. No extra simulation is needed — the numbers were already in
        # the run and simply never read.
        # One iteration per requested pattern frequency. ``ff.*`` is already
        # indexed per frequency (openEMS/nf2ff.py builds a list per entry of the
        # freq array), so this loop only had to stop hard-coding [0]; and
        # ``port.P_acc`` is indexed on the deck's own f grid, which is why the
        # frequencies were resolved to INDICES rather than to Hz.
        w("_meta_rows = []")
        w("for _k, _i in enumerate(ff_idx):")
        w(" f_ff = float(f[_i])")
        w(" Dmax_dbi = 10.0*np.log10(ff.Dmax[_k])")
        w(" E_norm = ff.E_norm[_k] / np.max(ff.E_norm[_k])")
        w(" dir_dbi = 20.0*np.log10(np.maximum(E_norm, 1e-8)) + Dmax_dbi  # DIRECTIVITY")
        w(" p_acc = float(np.real(np.ravel(port.P_acc)[_i]))")
        w(" p_rad = float(np.real(np.ravel(ff.Prad)[_k]))")
        w(" eta = (p_rad / p_acc) if p_acc > 0 else float('nan')")
        # ⚠⚠ AN EFFICIENCY ABOVE 1 IS NOT A NUMBER, IT IS A FAILED POWER
        # BUDGET. A passive antenna cannot radiate more than it accepts, so
        # eta > 1 means p_acc is not the accepted power at this port — measured
        # with a rectangular WAVEGUIDE port, where CalcPort's modal
        # normalisation differs from a lumped port's: eta came back at 1642 %
        # and would have SCALED GAIN UP BY 12 dB. That is worse than the
        # directivity-as-gain defect this whole block was written to fix, so it
        # must never be applied silently.
        # ⛳ Falling back to DIRECTIVITY is the honest choice: it is a real,
        # well-defined quantity, it is what the code reported before v1.4.0,
        # and it is an UPPER BOUND on gain — erring toward the conservative
        # reading rather than the flattering one. The deck says so out loud.
        w(" if not (eta == eta) or not (0.0 < eta <= 1.05):")
        w("     print('EMStudio: WARNING - power budget did not close "
          "(P_rad/P_acc = %r). Reporting DIRECTIVITY, not gain; the true gain "
          "is at or below this.' % (eta,))")
        w("     eta_db = 0.0")
        w("     eta = float('nan')")
        w(" else:")
        w("     eta_db = 10.0*np.log10(min(eta, 1.0))")
        w(" gain_dbi = dir_dbi + eta_db  # (Nt, Np) TRUE GAIN (or directivity"
          " if the budget failed)")
        w(" ff_rows = []")
        w(" for i_t, th in enumerate(theta):")
        w("     for i_p, ph in enumerate(phi):")
        w("         ff_rows.append((f_ff, th, ph, gain_dbi[i_t, i_p]))")
        # ⚠ ONE CSV PER FREQUENCY, never one CSV holding several. Pouring two
        # frequencies into one grid is exactly the trap NEC2's pattern pass hit:
        # the file parses, and the pattern it returns belongs to no frequency.
        w(" _stem = 'farfield_port_{0}' + ('_%d' % _k if len(ff_idx) > 1 else '')".format(excited["nr"]))
        w(" np.savetxt(os.path.join(sim_path, _stem + '.csv'), np.asarray(ff_rows),")
        w("            delimiter=',', header='freq_hz,theta_deg,phi_deg,gain_dbi', comments='')")
        w(" _meta_rows.append((f_ff, Dmax_dbi, eta, p_acc, p_rad))")
        w(" print('EMStudio: far field at %.4g Hz, D = %.2f dBi, eta_rad = %.1f %%, "
          "G = %.2f dBi' % (f_ff, Dmax_dbi, 100.0*eta, Dmax_dbi + eta_db))")
        # A sidecar, not a 5th column: post.farfield.load_csv unpacks exactly
        # four fields, and NEC2's save_csv writes the same four. Widening the
        # pattern CSV would break both for a scalar that belongs beside it.
        # ⛳ ONE ROW PER FREQUENCY, in the same order as the CSVs, so the runner
        # can pair them without re-deriving anything.
        w("np.savetxt(os.path.join(sim_path, 'farfield_meta_{0}.csv'),".format(excited["nr"]))
        w("           np.asarray(_meta_rows), delimiter=',',")
        w("           header='freq_hz,directivity_dbi,eta_rad,p_acc_w,p_rad_w', comments='')")
        # The single-frequency name is kept as THE pattern for every existing
        # caller (the PDF report, the 3-D balloon, horn_openems). With several,
        # the DEFAULT one is written under both names: the picker reads the
        # numbered files, everything else keeps reading the plain one.
        # ⛳ THE DEFAULT IS THE MIDDLE OF THE BAND THE USER ASKED FOR, not the
        # first entry. NEC2 picks the entry nearest argmin|S11|, which is
        # exactly the choice that has no meaning on a flat band — and the horn
        # template asks for three patterns around 30 GHz precisely so the
        # reported one IS 30 GHz. First-of-list would report 29.5.
        w("if len(ff_idx) > 1:")
        w("    import shutil as _sh")
        w("    _default_k = len(ff_idx) // 2")
        w("    _sh.copyfile(os.path.join(sim_path, 'farfield_port_{0}_%d.csv' % _default_k),".format(excited["nr"]))
        w("                 os.path.join(sim_path, 'farfield_port_{0}.csv'))".format(excited["nr"]))
        w("    print('EMStudio: %d patterns; the reported one is %.4g Hz'"
          " % (len(ff_idx), f[ff_idx[_default_k]]))")
    if nf_plane in ("XY", "XZ", "YZ"):
        w("")
        w("# --- near-field h5 -> npz (|E| map; venv has h5py, FreeCAD may not) ---")
        w("try:")
        w("    import glob")
        w("    import h5py")
        w("    h5s = sorted(glob.glob(os.path.join(sim_path, 'Ef_fd*.h5')))")
        w("    with h5py.File(h5s[0], 'r') as h5:")
        w("        # /FieldData/FD/f0 is complex (3, nx, ny, nz): components x,y,z")
        w("        e = np.array(h5['/FieldData/FD/f0'])")
        w("        ax_x = np.array(h5['/Mesh/x']); ax_y = np.array(h5['/Mesh/y']); ax_z = np.array(h5['/Mesh/z'])")
        w("    e_mag = np.sqrt((np.abs(e) ** 2).sum(axis=0))  # -> (nx, ny, nz)")
        w("    e_mag = np.squeeze(e_mag)                      # 2-D on the cut plane")
        w("    np.savez(os.path.join(sim_path, 'nearfield.npz'),")
        w("             e_mag=e_mag, x=ax_x, y=ax_y, z=ax_z,")
        w("             plane='{0}', freq={1:.9g})".format(nf_plane, f0))
        w("    print('EMStudio: near-field map saved (nearfield.npz), shape %s' % (e_mag.shape,))")
        w("except Exception as _exc:")
        w("    print('EMStudio: near-field conversion failed: %r' % (_exc,))")
    w("print('EMStudio: openEMS deck finished OK')")
    w("")

    deck_path = os.path.join(workdir, "case_openems.py")
    with open(deck_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return deck_path, z0, excited["nr"]
