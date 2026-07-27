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


class OpenEMSModelError(ValueError):
    """The analysis cannot be expressed as an openEMS model."""


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
        if category.startswith("Metal") or category.startswith("Conductor"):
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


def _collect_ports(analysis):
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
            "excite": excite if port.Excited else 0.0,
            "edges2grid": edges2grid,
            "type": ptype,
        }
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
    if not any(p["excite"] for p in ports):
        raise OpenEMSModelError("the analysis needs exactly one excited port")
    return ports


def _domain(analysis, mats, lam_c_mm):
    """Simulation box = geometry bbox + padding wavelengths on every side."""
    inf = float("inf")
    lo = [inf, inf, inf]
    hi = [-inf, -inf, -inf]
    for m in mats:
        for p in m["prims"]:
            for i in range(3):
                lo[i] = min(lo[i], p["start"][i])
                hi[i] = max(hi[i], p["stop"][i])
    pad = float(analysis.DomainPaddingWavelengths) * lam_c_mm
    return [c - pad for c in lo], [c + pad for c in hi]


def _dielectric_thin_axis_lines(prim):
    """(axis, min, max) of the thinnest axis of a dielectric box (substrate)."""
    dims = [prim["stop"][i] - prim["start"][i] for i in range(3)]
    axis = int(min(range(3), key=lambda i: dims[i] if dims[i] > 0 else float("inf")))
    return axis, prim["start"][axis], prim["stop"][axis]


# --------------------------------------------------------------------------- writer
def write_deck(analysis, solver, workdir):
    """Write case_openems.py + geometry files. Returns (deck_path, z0)."""
    f1, f2, npts = Analysis.freq_range_hz(analysis)
    f0 = 0.5 * (f1 + f2)
    fc = 0.5 * (f2 - f1)
    if fc <= 0:
        raise OpenEMSModelError("FrequencyStop must be greater than FrequencyStart")

    mats = _collect_materials(analysis, workdir)
    ports = _collect_ports(analysis)
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
    dom_lo, dom_hi = _domain(analysis, mats, lam_c_mm)
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
        geo_lo = [min(p["start"][i] for m in mats for p in m["prims"]) for i in range(3)]
        geo_hi = [max(p["stop"][i] for m in mats for p in m["prims"]) for i in range(3)]
        sub_th = geo_hi[2] - geo_lo[2]
        dom_lo = list(geo_lo)
        dom_hi = list(geo_hi)
        dom_hi[2] = geo_hi[2] + max(12.0 * sub_th, 1.0)
    boundaries = Analysis.boundary_list(analysis)
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
    w("# simulation domain")
    w("mesh.AddLine('x', [{0:.9g}, {1:.9g}])".format(dom_lo[0], dom_hi[0]))
    w("mesh.AddLine('y', [{0:.9g}, {1:.9g}])".format(dom_lo[1], dom_hi[1]))
    w("mesh.AddLine('z', [{0:.9g}, {1:.9g}])".format(dom_lo[2], dom_hi[2]))
    w("")

    for m in mats:
        w("# --- material: {0} ({1}) ---".format(m["name"], m["kind"]))
        if m["kind"] == "metal":
            w("{0} = CSX.AddMetal('{0}')".format(m["name"]))
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
        w("nf2ff_box = FDTD.CreateNF2FFBox()")
        w("")
    nf_plane = str(getattr(solver, "NearFieldPlane", "None"))
    if nf_plane in ("XY", "XZ", "YZ"):
        # FD |E| dump on a cut plane through the geometry-bbox center, recorded at
        # the sweep center frequency (FD dumps need the frequency before Run).
        geo_lo = [c + float(analysis.DomainPaddingWavelengths) * lam_c_mm for c in dom_lo]
        geo_hi = [c - float(analysis.DomainPaddingWavelengths) * lam_c_mm for c in dom_hi]
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
    w("for _p in ports.values():")
    w("    _p.CalcPort(sim_path, f, ref_impedance={0:.9g})".format(z0))
    w("port = ports[{0}]".format(excited["nr"]))
    w("s11 = port.uf_ref / port.uf_inc")
    w("zin = port.uf_tot / port.if_tot")
    w("rows = np.column_stack([f, zin.real, zin.imag, s11.real, s11.imag, np.full_like(f, {0:.9g})])".format(z0))
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
        w("")
        w("# --- far field at the best-match frequency (NF2FF) ---")
        w("s11_db = 20*np.log10(np.maximum(np.abs(s11), 1e-30))")
        w("f_ff = f[int(np.argmin(s11_db))]")
        w("# full sphere for 3-D balloon plots (phi=0/90 columns feed the 2-D cuts)")
        w("theta = np.arange(0.0, 180.1, 5.0)")
        w("phi = np.arange(0.0, 360.0, 5.0)")
        w("ff = nf2ff_box.CalcNF2FF(sim_path, f_ff, theta, phi, center={0})".format(_fmt_v(center)))
        w("Dmax_dbi = 10.0*np.log10(ff.Dmax[0])")
        w("E_norm = ff.E_norm[0] / np.max(ff.E_norm[0])")
        w("gain_dbi = 20.0*np.log10(np.maximum(E_norm, 1e-8)) + Dmax_dbi  # (Nt, Np)")
        w("ff_rows = []")
        w("for i_t, th in enumerate(theta):")
        w("    for i_p, ph in enumerate(phi):")
        w("        ff_rows.append((f_ff, th, ph, gain_dbi[i_t, i_p]))")
        w("np.savetxt(os.path.join(sim_path, 'farfield_port_{0}.csv'), np.asarray(ff_rows),".format(excited["nr"]))
        w("           delimiter=',', header='freq_hz,theta_deg,phi_deg,gain_dbi', comments='')")
        w("print('EMStudio: far field at %.4g Hz, Dmax = %.2f dBi' % (f_ff, Dmax_dbi))")
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
