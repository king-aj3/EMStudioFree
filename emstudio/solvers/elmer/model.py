# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD analysis -> axi model dict for the Elmer magnetics backend.

Geometry class supported (the CENOS induction-heating / WPT class):
solids of revolution about the GLOBAL Z axis whose rz cross-section is a
rectangle — cylinders (billets), tubes/rings (coil cross-sections,
susceptors). Classification reads the solid's cylindrical faces: the
outer radius is the largest face radius, the inner radius the smallest
(0 for solid cylinders); z extent from the bounding box. Anything else
raises ``AxiModelError`` with an actionable message.

FreeCAD imports stay inside functions — the rest of the Elmer backend is
importable without FreeCAD (plain-python validation gates).
"""
from __future__ import annotations

import math
import re

MU0 = 4.0e-7 * math.pi

#: geometric tolerances (mm)
_AXIS_TOL_MM = 1e-4
_DIR_TOL = 1e-6


class AxiModelError(ValueError):
    """The analysis cannot be expressed as an axisymmetric magnetics model."""


def solid_to_rect(shape, label):
    """Classify a solid of revolution into (r0, r1, z0, z1) in mm."""
    import Part

    radii = set()
    for face in shape.Faces:
        surf = face.Surface
        if isinstance(surf, Part.Cylinder):
            axis = surf.Axis
            if abs(abs(axis.z) - 1.0) > _DIR_TOL:
                raise AxiModelError(
                    "'{0}': cylindrical face not aligned with the Z axis — "
                    "magnetics bodies must be coaxial with Z".format(label))
            center = surf.Center
            if math.hypot(center.x, center.y) > _AXIS_TOL_MM:
                raise AxiModelError(
                    "'{0}': cylindrical face not centered on the Z axis "
                    "(offset {1:.3g} mm)".format(label, math.hypot(center.x, center.y)))
            radii.add(round(surf.Radius, 9))
    if not radii:
        raise AxiModelError(
            "'{0}' has no cylindrical faces — the axisymmetric Elmer backend "
            "needs coaxial cylinders/tubes/rings centered on the Z axis "
            "(use Part Cylinder, or a cut of two cylinders for a ring)".format(label))
    r1 = max(radii)
    r0 = min(radii) if len(radii) > 1 else 0.0
    bb = shape.BoundBox
    _check_full_revolution(r1, (bb.XMax, -bb.XMin, bb.YMax, -bb.YMin), label)
    return r0, r1, bb.ZMin, bb.ZMax


def _check_full_revolution(r1, radial_extents, label):
    """Raise AxiModelError unless the radial bounding-box extents match r1.

    The tolerance is deliberately GENEROUS: ``Shape.BoundBox`` is
    tessellation-dependent — under the GUI it can sit ~0.1 mm inside the true
    radius (facet chords) and ``optimalBoundingBox`` pads outward by a similar
    amount, so a tight tolerance rejects valid rings for GUI users (freecadcmd
    gives the exact box, masking it). The check's only job is to reject PARTIAL
    revolutions (arc segments/wedges), which miss by a large fraction of r1, so
    5% of the radius separates them cleanly.
    """
    tol = max(0.05 * r1, 0.25)
    for extent in radial_extents:
        if abs(extent - r1) > tol:
            raise AxiModelError(
                "'{0}' is not a full solid of revolution about Z — its radial "
                "extent ({1:.3g} mm) does not match its outer radius ({2:.3g} mm). "
                "Magnetics bodies must be full rings/cylinders, not arc "
                "segments.".format(label, extent, r1))


def _safe_name(label, used):
    from emstudio.meshing.gmsh_axi import AIR_NAME, BOUNDARY_NAMES

    base = re.sub(r"[^a-z0-9_]", "_", label.lower()).strip("_") or "body"
    if base in BOUNDARY_NAMES or base == AIR_NAME:
        base = base + "_body"
    name = base
    i = 2
    while name in used:
        name = "{0}{1}".format(base, i)
        i += 1
    used.add(name)
    return name


def _skin_depth_m(sigma, mu_r, f_hz):
    if sigma <= 0 or f_hz <= 0:
        return float("inf")
    return math.sqrt(2.0 / (2.0 * math.pi * f_hz * MU0 * mu_r * sigma))


def _auto_lc(rect, sigma, mu_r, f_max_hz):
    """Skin-depth-aware mesh size (mm): resolve min(feature/6, delta/4).

    delta/4: resolves the exponential skin profile well enough for the
    few-percent power windows (the eddy-power scalar and the field peak both
    live in the outer delta).
    """
    r0, r1, z0, z1 = rect
    min_dim = min(r1 - r0 if r0 > 0 else r1, z1 - z0)
    lc = min_dim / 6.0
    delta_mm = _skin_depth_m(sigma, mu_r, f_max_hz) * 1e3
    lc = min(lc, delta_mm / 4.0)
    # floor: don't let a microscopic skin depth explode the mesh — warn-level
    # accuracy loss is preferable to an unusable mesh
    return max(lc, min_dim / 80.0)


def _referenced_solids(obj):
    """Whole-solid references of a material/coil object: [(link_obj, shape)]."""
    from emstudio.objects import query

    out = []
    seen = set()
    for link_obj, shape, sub in query.resolved_references(obj):
        if sub not in ("", None):
            raise AxiModelError(
                "'{0}' references sub-element '{1}' — magnetics objects must "
                "reference whole solids".format(obj.Label, sub))
        if link_obj.Name in seen:
            continue
        seen.add(link_obj.Name)
        if shape is None or not getattr(shape, "Solids", None):
            raise AxiModelError(
                "'{0}' reference '{1}' has no solid shape".format(obj.Label, link_obj.Label))
        out.append((link_obj, shape))
    return out


def build_axi_model(analysis, solver):
    """Extract the axi model dict from a FreeCAD analysis. See writer docs."""
    from emstudio.objects import query
    from emstudio.objects.analysis import Analysis

    _f1, f2, _n = Analysis.freq_range_hz(analysis)
    lc_user = float(solver.MeshSizeBodies.getValueAs("mm")) if hasattr(solver, "MeshSizeBodies") else 0.0

    bodies = []
    used_names = set()
    geo_owner = {}  # FreeCAD object Name -> body dict (to merge material props)
    body_k = {}  # body name -> thermal conductivity (materials with k > 0)

    # coils first — a coil's geometry is a coil body even if a material also
    # references it (the material then only contributes mu_r)
    for coil in query.get_coils(analysis):
        for link_obj, shape in _referenced_solids(coil):
            if link_obj.Name in geo_owner:
                raise AxiModelError(
                    "two coils reference the same solid '{0}'".format(link_obj.Label))
            rect = solid_to_rect(shape, link_obj.Label)
            body = {
                "name": _safe_name(coil.Label, used_names),
                "r0": rect[0], "r1": rect[1], "z0": rect[2], "z1": rect[3],
                "sigma": 0.0,
                "mu_r": 1.0,
                "coil": {
                    "turns": int(coil.Turns),
                    "current_a": float(coil.Current.getValueAs("A")),
                    "phase_deg": float(coil.PhaseDeg),
                    "reversed": bool(coil.Reversed),
                },
            }
            body["lc"] = lc_user if lc_user > 0 else _auto_lc(rect, 0.0, 1.0, f2)
            bodies.append(body)
            geo_owner[link_obj.Name] = body

    for mat in query.get_materials(analysis):
        category = getattr(mat, "Category", "")
        sigma = float(getattr(mat, "Conductivity", 0.0) or 0.0)
        mu_r = float(getattr(mat, "RelPermeability", 1.0) or 1.0)
        if category == "Metal (PEC)":
            raise AxiModelError(
                "material '{0}' is PEC — magnetodynamics needs a finite "
                "conductivity: use the Conductor category and set "
                "Conductivity (S/m)".format(mat.Label))
        for link_obj, shape in _referenced_solids(mat):
            if link_obj.Name in geo_owner:
                # material on a coil body: contributes permeability only
                geo_owner[link_obj.Name]["mu_r"] = mu_r
                continue
            rect = solid_to_rect(shape, link_obj.Label)
            body = {
                "name": _safe_name(mat.Label if len(list(query.resolved_references(mat))) == 1
                                   else link_obj.Label, used_names),
                "r0": rect[0], "r1": rect[1], "z0": rect[2], "z1": rect[3],
                "sigma": sigma,
                "mu_r": mu_r,
            }
            sigma_alpha = float(getattr(mat, "ConductivityTempCoeff", 0.0) or 0.0)
            if sigma_alpha != 0.0:
                if sigma <= 0.0:
                    raise AxiModelError(
                        "material '{0}' has ConductivityTempCoeff but no "
                        "Conductivity — set the reference σ0 (S/m) it scales".format(
                            mat.Label))
                body["sigma_alpha"] = sigma_alpha
            bh_b = list(getattr(mat, "BHCurveB", None) or [])
            bh_h = list(getattr(mat, "BHCurveH", None) or [])
            if bh_b or bh_h:
                from emstudio.solvers.elmer import writer as _writer

                if len(bh_b) != len(bh_h):
                    raise AxiModelError(
                        "material '{0}': BHCurveB and BHCurveH must pair 1:1 "
                        "({1} vs {2} points)".format(
                            mat.Label, len(bh_b), len(bh_h)))
                pairs = list(zip(bh_b, bh_h))
                try:
                    _writer.validate_bh_table(pairs, mat.Label)
                except _writer.ElmerModelError as exc:
                    raise AxiModelError(str(exc))
                body["bh"] = pairs
            body["lc"] = lc_user if lc_user > 0 else _auto_lc(rect, sigma, mu_r, f2)
            bodies.append(body)
            geo_owner[link_obj.Name] = body
            k_th = float(getattr(mat, "ThermalConductivity", 0.0) or 0.0)
            if k_th > 0:
                body_k[body["name"]] = {
                    "k": k_th,
                    "k_beta": float(getattr(
                        mat, "ThermalConductivityTempCoeff", 0.0) or 0.0),
                    "rho": float(getattr(mat, "Density", 0.0) or 0.0),
                    "cp": float(getattr(mat, "SpecificHeat", 0.0) or 0.0),
                }

    if not bodies:
        raise AxiModelError(
            "the analysis has no magnetics bodies — assign a Conductor "
            "material to the workpiece and/or add a Coil excitation")
    if not any(b.get("coil") for b in bodies):
        raise AxiModelError(
            "no coil excitation — add a Coil (select the coil ring solid, "
            "then 'Coil Excitation')")

    model = {
        "bodies": bodies,
        "domain_scale": float(getattr(solver, "DomainScale", 8.0) or 8.0),
    }

    # Static (DC) magnetostatics (MAGNETICS_DEPTH_PLAN §4): exact nonlinear
    # B-H, inductance at the operating current; no eddy/thermal quantities
    static = "Static" in str(getattr(solver, "AnalysisType", "") or "")
    if static:
        if bool(getattr(solver, "SolveThermal", False)):
            raise AxiModelError(
                "Static (DC) analysis has no eddy currents or Joule heating "
                "— turn SolveThermal off, or use Harmonic (AC)")
        model["static"] = True

    # σ(T) coupling prerequisites: the MATC expression reads Temperature, so
    # every σ(T) body must be part of the heat solve (SolveThermal + k > 0)
    sigma_t_names = [b["name"] for b in bodies if b.get("sigma_alpha")]
    if sigma_t_names and not bool(getattr(solver, "SolveThermal", False)):
        raise AxiModelError(
            "material on '{0}' has ConductivityTempCoeff (σ(T)) but the "
            "solver's SolveThermal is off — enable it so the temperature "
            "feeding σ(T) exists".format(", ".join(sigma_t_names)))
    for name in sigma_t_names:
        if name not in body_k:
            raise AxiModelError(
                "'{0}' has ConductivityTempCoeff (σ(T)) but its material has "
                "no ThermalConductivity — set it (W/(m*K)) so the body joins "
                "the heat solve".format(name))

    if bool(getattr(solver, "SolveThermal", False)):
        thermal_bodies = {name: dict(props) for name, props in body_k.items()}
        if not thermal_bodies:
            raise AxiModelError(
                "SolveThermal is on but no material has ThermalConductivity > 0 "
                "— set it on the workpiece material (W/(m*K))")
        thermal = {
            "t_ext": float(solver.AmbientTemperature.getValueAs("K")),
            "h": float(solver.ConvectionCoefficient),
            "bodies": thermal_bodies,
        }
        emis = float(getattr(solver, "SurfaceEmissivity", 0.0) or 0.0)
        if emis > 0.0:
            thermal["emissivity"] = emis
            rad_t = getattr(solver, "RadiationTemperature", None)
            if rad_t is not None:
                rad_k = float(rad_t.getValueAs("K"))
                if rad_k > 0.0:
                    thermal["rad_t_ext"] = rad_k
        if bool(getattr(solver, "TransientHeating", False)):
            for name, tb in thermal_bodies.items():
                if tb["rho"] <= 0 or tb["cp"] <= 0:
                    raise AxiModelError(
                        "TransientHeating is on but '{0}' material lacks Density "
                        "(kg/m^3) and/or SpecificHeat (J/kg/K)".format(name))
            thermal["transient"] = {
                "total_time_s": float(getattr(solver, "HeatingTime", 60.0) or 60.0),
                "n_steps": int(getattr(solver, "HeatingSteps", 30) or 30),
            }
        model["thermal"] = thermal
    return model
