# SPDX-License-Identifier: LGPL-2.1-or-later
"""Helpers to find EMStudio objects inside a document / analysis group.

The equivalent of FEM's ``femtools.membertools``: writers and commands never walk
``analysis.Group`` by hand — they ask these helpers, which match on the
``EMStudioType`` string tag (robust across reloads, unlike isinstance on proxies).
"""

from __future__ import annotations


def em_type(obj):
    """The EMStudioType tag of an object, or ''."""
    return getattr(obj, "EMStudioType", "") or ""


def is_em_type(obj, type_name):
    return em_type(obj) == type_name


def get_members(analysis, type_name=None):
    """All children of an analysis group, optionally filtered by EMStudioType."""
    members = list(getattr(analysis, "Group", []) or [])
    if type_name is None:
        return members
    return [m for m in members if is_em_type(m, type_name)]


def get_materials(analysis):
    return get_members(analysis, "EMStudio::Material")


def get_ports(analysis):
    ports = get_members(analysis, "EMStudio::LumpedPort")
    return sorted(ports, key=lambda p: p.PortNumber)


def get_coils(analysis):
    return get_members(analysis, "EMStudio::Coil")


def get_transmission_lines(analysis):
    return get_members(analysis, "EMStudio::TransmissionLine")


def get_solvers(analysis):
    return [m for m in get_members(analysis) if em_type(m).startswith("EMStudio::Solver")]


def find_analyses(doc):
    """All EM Analysis containers in a document."""
    return [o for o in doc.Objects if is_em_type(o, "EMStudio::Analysis")]


def get_parent_analysis(obj):
    """The EM Analysis group an object belongs to, or None."""
    for parent in obj.InList:
        if is_em_type(parent, "EMStudio::Analysis"):
            return parent
    return None


def resolved_references(obj):
    """Yield (document_object, subelement_shape_or_None, subname) for References.

    For whole-object links the subname is '' and the shape is the object's Shape.
    For sub-element links (e.g. 'Face3', 'Edge1') the shape is that sub-shape.
    """
    for link_obj, subnames in getattr(obj, "References", []) or []:
        if not subnames or subnames == ("",):
            yield link_obj, getattr(link_obj, "Shape", None), ""
            continue
        for sub in subnames:
            if not sub:
                yield link_obj, getattr(link_obj, "Shape", None), ""
                continue
            shape = None
            try:
                shape = link_obj.Shape.getElement(sub)
            except Exception:
                pass
            yield link_obj, shape, sub
