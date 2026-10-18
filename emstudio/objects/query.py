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


def resolved_references(obj, subobjects=False):
    """Yield (document_object, subelement_shape_or_None, subname) for References.

    For whole-object links the subname is '' and the shape is the object's Shape.
    For sub-element links (e.g. 'Face3', 'Edge1') the shape is that sub-shape.

    ``subobjects=True`` also resolves OBJECT-PATH subnames — what FreeCAD
    stores when a part is picked THROUGH a group in the tree or the 3-D view:
    ``'Body004.'`` (a whole child), ``'Grp.Box.Face2'`` (a face of a nested
    child). ``Shape.getElement`` only knows element names, so it raises
    "Invalid shape name Body004." and the shape came back None — and every
    backend then skipped that reference without a word (measured on a forum
    J-pole, 2026-10: sixteen part picks, all silently dropped).
    ⚠ OFF by default, on purpose: honouring part picks ADDS geometry, and a
    backend that does not also de-duplicate would export a part twice when a
    document references both a group and a child of it (that forum file does
    exactly that). openEMS opts in through :func:`reference_leaves`, which
    de-duplicates; the other backends keep their behaviour byte for byte
    until they do the same.
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
            if shape is None and subobjects:
                shape = _subobject_shape(link_obj, sub)
            yield link_obj, shape, sub


# --------------------------------------------------------------------------
# Sub-object resolution + leaf expansion (openEMS since v1.14.0)
# --------------------------------------------------------------------------
#: Containers nest (groups in groups, App::Part, App::Link to a group, link
#: arrays, Assembly). FreeCAD's own group-shape walk has no depth limit, but a
#: link cycle would recurse for ever; 32 levels is far past any real model.
_MAX_DEPTH = 32

#: Two references reach the SAME placed part when they name the same final
#: object and its global bounding box agrees to this many mm. Coordinates
#: computed along two different paths (a group's child vs. the child itself)
#: can differ by float noise, so a hash of rounded numbers could split one
#: part into two at a rounding boundary — compare with a tolerance instead.
_SAME_PLACE_MM = 1e-6


def _usable_shape(shape):
    """``shape`` if it is a real, non-null Part shape, else None.

    ⚠ An unresolvable element comes back DIFFERENTLY per FreeCAD version —
    measured: ``getSubObject('Face99')`` on a 6-face box returns None on
    0.21.2 but a NULL Shape object on 1.1.4 — so both are folded to None here.
    """
    if shape is None:
        return None
    try:
        if shape.isNull():
            return None
    except Exception:                                        # noqa: BLE001
        return None                    # not a Part shape at all
    return shape


def _subobject_shape(root, sub):
    """The GLOBAL shape a subname path points at, or None.

    ``getSubObject`` applies every placement along the path (measured: a box
    at (5,0,0) inside an App::Part at (0,100,0) comes back at (5,100,0)), so
    the shape is already where it sits in the model.
    """
    try:
        return _usable_shape(root.getSubObject(sub))
    except Exception:                                        # noqa: BLE001
        return None


def _label(obj):
    return str(getattr(obj, "Label", "") or getattr(obj, "Name", "") or "?")


def _is_leaf(obj):
    """True when ``obj``'s geometry is its OWN Shape (or Mesh), not its children's.

    A Part feature is a leaf even when it has children: a PartDesign Body owns
    its features, a Part::Cut its base and tool, and their shape already IS
    the result — expanding them would export every intermediate feature.
    Everything else (App::DocumentObjectGroup, App::Part, an App::Link to a
    group, Assembly) is a container exactly when FreeCAD itself lists
    sub-objects for it, which is the same test FreeCAD's own group-shape
    builder uses.
    """
    try:
        if obj.isDerivedFrom("Part::Feature") or obj.isDerivedFrom("Mesh::Feature"):
            return True
    except Exception:                                        # noqa: BLE001
        return True
    try:
        return not obj.getSubObjects()
    except Exception:                                        # noqa: BLE001
        return True


def _walk(root, sub):
    """(objects along ``sub`` starting at ``root``, trailing element name).

    ⚠ Walked ONE LEVEL AT A TIME on purpose. For a nested path FreeCAD's own
    ``getSubObject(..., retType=1)`` and ``getSubObjectList`` both return the
    FIRST child, not the leaf — measured on 0.21.2 and 1.1.4:
    ``Outer.getSubObjectList('Grp.Box.')`` is [Outer, Grp, Grp]. A one-level
    lookup is exact, so the leaf's identity (what de-duplication keys on) and
    its label path come from here. A component that is not a child ends the
    walk; what is left is the element name (``'Face2'``, or a 1.x mapped name).
    """
    objs = [root]
    rest = str(sub or "")
    while "." in rest:
        head, tail = rest.split(".", 1)
        try:
            nxt = objs[-1].getSubObject(head + ".", retType=1)
        except Exception:                                    # noqa: BLE001
            nxt = None
        if nxt is None or nxt is objs[-1]:
            break
        objs.append(nxt)
        rest = tail
    return objs, rest


def _mesh_of(leaf, root=None, sub=""):
    """A Mesh::Feature's mesh, placed globally, or None if it has no facets.

    A mesh referenced DIRECTLY is returned verbatim, exactly as before
    v1.14.0. One reached through a placed container (a mesh inside an
    App::Part) needs that container's placement too: ``obj.Mesh`` carries only
    the mesh's OWN placement (measured: a mesh at (0,0,7) in a Part at
    (0,100,0) reports BoundBox z 7..8, y 0..1), so the container's part of
    the accumulated matrix is applied to a copy. Measured on 0.21.2 and
    1.1.4: that copy's written STL then reads back at y 100..101, z 7..8.
    """
    mesh = getattr(leaf, "Mesh", None)
    if mesh is None or getattr(mesh, "CountFacets", 0) <= 0:
        return None
    if root is None or root is leaf or not sub:
        return mesh
    try:
        mat = root.getSubObject(sub, retType=2)[1]
        own = leaf.Placement.toMatrix()
        outer = mat.multiply(own.inverse())
        if all(abs(a - b) <= 1e-12 for a, b in zip(outer.A, (
                1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0))):
            return mesh
        placed = mesh.copy()
        placed.transform(outer)
        return placed
    except Exception:                                        # noqa: BLE001
        return mesh


def _geom_kind(shape):
    """'solid', 'surface', or 'wire' (edges / vertices only) for a Part shape."""
    try:
        if shape.Solids:
            return "solid"
        if shape.Faces:
            return "surface"
    except Exception:                                        # noqa: BLE001
        pass
    return "wire"


def _ref_text(root, sub):
    return "'{0}'{1}".format(_label(root),
                             " / '{0}'".format(sub) if sub else "")


def _leaf_record(root, sub, objs, element, shape, expanded_from=None):
    leaf = objs[-1]
    mesh = None if shape is not None else _mesh_of(
        leaf, root if sub else None, sub)
    label = " > ".join(_label(o) for o in objs)
    if element:
        label = "{0} ({1})".format(label, element)
    try:
        final = leaf.getLinkedObject(True)
    except Exception:                                        # noqa: BLE001
        final = leaf
    final = final if final is not None else leaf
    ident = (getattr(getattr(final, "Document", None), "Name", ""),
             getattr(final, "Name", ""), element or "")
    return {"root": root, "sub": sub, "leaf": leaf, "objs": objs,
            "element": element or "", "label": label, "shape": shape,
            "mesh": mesh, "ident": ident, "expanded_from": expanded_from}


def _bbox_of(rec):
    """The record's global bounding box as a 6-tuple, or None — computed ONCE.

    ⚠ Cached in the record on purpose: de-duplication compares every new part
    with every part already kept, and ``Shape.BoundBox`` is recomputed by
    OpenCASCADE on every access (milliseconds on threaded hardware), so an
    uncached n² loop over a few hundred fasteners would cost seconds before a
    single STL is written.
    """
    if "bbox" in rec:
        return rec["bbox"]
    geo = rec["shape"] if rec["shape"] is not None else rec["mesh"]
    try:
        bb = geo.BoundBox
        box = (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)
    except Exception:                                        # noqa: BLE001
        box = None
    rec["bbox"] = box
    return box


def _same_place(a, b):
    """True if two records are the same final object sitting in the same place."""
    if a["ident"] != b["ident"]:
        return False
    ba, bb = _bbox_of(a), _bbox_of(b)
    if ba is None or bb is None:
        return False
    return all(abs(x - y) <= _SAME_PLACE_MM for x, y in zip(ba, bb))


def _has_geometry(rec):
    if rec["mesh"] is not None:
        return True
    return rec["shape"] is not None and _geom_kind(rec["shape"]) != "wire"


def _expand(root, prefix, objs, depth, out, hidden, origin):
    """Append a record per VISIBLE leaf under the container ``objs[-1]``.

    ⛳ Visibility follows FreeCAD's own group-shape rule (Part::Feature::
    getTopoShape): a child the parent reports invisible (``isElementVisible``
    0), or — when the parent has no opinion (-1) — a child whose own
    Visibility is off, is left out. Measured: a group with a hidden cylinder
    reports a 1-solid ``Shape``; with it shown, 2. So a whole-group
    reference exports exactly what it exported before v1.14.0 (the group's
    ``Shape``), only part by part — and the parts left out are REPORTED
    (``hidden``) instead of vanishing.
    """
    cont = objs[-1]
    try:
        names = list(cont.getSubObjects() or ())
    except Exception:                                        # noqa: BLE001
        names = []
    for name in names:
        if not name or not name.endswith("."):
            continue                    # an element of a container: not a part
        try:
            child = cont.getSubObject(name, retType=1)
        except Exception:                                    # noqa: BLE001
            child = None
        if child is None or child is cont:
            continue
        try:
            vis = cont.isElementVisible(name[:-1])
        except Exception:                                    # noqa: BLE001
            vis = -1
        path = prefix + name
        if vis == 0 or (vis < 0 and not getattr(child, "Visibility", True)):
            hidden.append((root, path, objs + [child]))
            continue
        if _is_leaf(child):
            rec = _leaf_record(root, path, objs + [child], "",
                               _subobject_shape(root, path),
                               expanded_from=origin)
            # A sketch, datum or origin inside a group is construction, not
            # a part: it never reached the deck as anything (its edges make
            # no facets) and saying so for every one would be noise.
            if _has_geometry(rec):
                out.append(rec)
        elif depth < _MAX_DEPTH:
            _expand(root, path, objs + [child], depth + 1, out, hidden, origin)




def _is_link(obj):
    try:
        return obj.isDerivedFrom("App::Link")
    except Exception:                                        # noqa: BLE001
        return False


def _no_geometry(rec):
    """Why a resolved part contributes nothing to a volume model, or None."""
    if rec["mesh"] is not None:
        return None
    if rec["shape"] is None:
        return ("'{0}' has no shape or mesh, so there is nothing to "
                "model".format(rec["label"]))
    if _geom_kind(rec["shape"]) == "wire":
        return ("'{0}' is only edges or points, which a volume solver does "
                "not model (it meshes solids and sheets; wires belong to "
                "NEC2, and a feed edge belongs on a port)".format(rec["label"]))
    return None


def _own_shape(obj):
    """``obj.Shape`` or None. ⚠ ``getattr(..., None)`` alone is not enough:
    a group's ``Shape`` is computed on access in FreeCAD 1.x and an empty one
    raises (measured: AttributeError on a group whose only child is hidden),
    and a broken feature can raise something else."""
    try:
        return _usable_shape(getattr(obj, "Shape", None))
    except Exception:                                        # noqa: BLE001
        return None


def _resolve_one(root, sub):
    """(records, problem, hidden) for ONE (object, subname) reference.

    ``problem`` is why it reached nothing, in the user's terms, or None;
    ``hidden`` lists the parts a container reference left out as invisible.
    ⚠ Every route that already worked is tried FIRST and unchanged — a whole
    leaf object's own ``Shape``, a plain element name through ``getElement``
    — so the shapes (and so the STL bytes) of every document that resolved
    before v1.14.0 stay identical. Only what used to come back None, or a
    whole container, takes a new route.
    """
    sub = str(sub or "")
    hidden = []
    if not sub:
        if _is_leaf(root):
            rec = _leaf_record(root, "", [root], "", _own_shape(root))
            return [rec], _no_geometry(rec), hidden
        objs, element = [root], ""
    else:
        try:
            el = _usable_shape(root.Shape.getElement(sub))
        except Exception:                                    # noqa: BLE001
            el = None
        if el is not None:
            rec = _leaf_record(root, sub, [root], sub, el)
            return [rec], _no_geometry(rec), hidden
        objs, element = _walk(root, sub)
        if element:
            shape = _subobject_shape(root, sub)
            if shape is None:
                return [], ("FreeCAD finds no '{0}' in '{1}' (the model may "
                            "have changed since it was picked; re-pick it "
                            "from the model tree or the 3-D view)".format(
                                element, " > ".join(_label(o) for o in objs))
                            ), hidden
            rec = _leaf_record(root, sub, objs, element, shape)
            return [rec], _no_geometry(rec), hidden
        if _is_leaf(objs[-1]):
            rec = _leaf_record(root, sub, objs, "", _subobject_shape(root, sub))
            return [rec], _no_geometry(rec), hidden
    out = []
    _expand(root, sub, objs, len(objs), out, hidden, origin=objs[-1])
    if out:
        return out, None, hidden
    return [], "the {0} '{1}' holds no visible solid or sheet{2}".format(
        "link" if _is_link(objs[-1]) else "container",
        " > ".join(_label(o) for o in objs),
        " ({0} hidden part(s) left out: show them, or pick them on their "
        "own)".format(len(hidden)) if hidden else ""), hidden


def _names(labels, cap):
    """'A', 'B', 'C' and N more — a list a user can read in one line."""
    head = ", ".join("'{0}'".format(x) for x in labels[:cap])
    return head + (" and {0} more".format(len(labels) - cap)
                   if len(labels) > cap else "")


def reference_leaves(obj):
    """Every placed part the References of ``obj`` reach, ONCE each.

    Returns ``(leaves, issues)``:

    * ``leaves`` — one record per part, in first-reference order:
      ``{"label": "Feed > Mount", "shape": <global Part shape or None>,
      "mesh": <Mesh or None>, "leaf": obj, "root": obj, "sub": str,
      "element": "Face3" | "", "objs": [root, ..., leaf], ...}``. A shape is
      already placed globally; a whole-object reference to a leaf carries the
      object's own ``Shape``, exactly what the openEMS writer always used.
    * ``issues`` — ``(level, text)``: ``"warning"`` for a reference that
      reaches nothing (it is NOT in the model), ``"note"`` for what a user
      would want to know (hidden parts left out of a referenced group; a
      group that brings in parts nobody picked).

    WHY IT EXISTS. Until v1.14.0 a part picked THROUGH a group
    (``('Group003', ('Body004.',))``) resolved to None and was dropped in
    silence, so a forum user's sixteen part picks never reached the deck —
    only his whole-group references did, and one of those groups carried a
    Back plate he never picked, shorting his feed. Resolving the picks is not
    enough on its own: he referenced the groups AND their children, so each
    part would then be exported twice — coincident duplicates, the defect
    behind openEMS's polyhedron warnings. Hence:

    * whole-container references are EXPANDED into their visible parts;
    * every part is kept ONCE, keyed on (the final object through any links,
      its global placement — read as where its bounding box sits, so the key
      does not depend on how App::Link composes placements). Two link
      instances of one body in two places are two parts; the same body
      reached as 'Feed' and as 'Feed > Mount' is one;
    * a reference that reaches nothing is a WARNING naming it, never a skip.

    ⚠ Residual, by design: two DIFFERENT objects with identical geometry in
    the same place (a "simple copy" left on top of its original, a
    Part::Compound beside its own child) are two objects and both kept.

    FreeCAD-free like the rest of this module: only methods on the objects
    passed in are used.
    """
    leaves, issues = [], []
    picked, expansions, hidden_all = [], [], []
    for link_obj, subnames in getattr(obj, "References", []) or []:
        if link_obj is None:
            continue
        for sub in (list(subnames or ()) or [""]):
            recs, problem, hidden = _resolve_one(link_obj, sub or "")
            hidden_all.extend(hidden)
            if problem:
                # The REMEDY lives in each problem text, not here: "re-pick
                # it" is right for a stale pick and wrong for a sketch (which
                # no re-pick turns into a solid), so one generic tail would
                # mislead on half the cases.
                issues.append(("warning", (
                    "the reference {0} reaches no geometry — {1} — so it is "
                    "NOT in the model.").format(_ref_text(link_obj, sub or ""),
                                                problem)))
                continue
            group = [r for r in recs if r["expanded_from"] is not None]
            if group:
                expansions.append((group[0]["expanded_from"], group))
            else:
                picked.extend(recs)
            for rec in recs:
                if any(_same_place(rec, kept) for kept in leaves):
                    continue            # the same part, reached a second time
                leaves.append(rec)
    # ⛳ A group referenced WHOLE beside picks of some of its parts: the
    # group reference also brings in every part nobody picked. That is
    # exactly how a Back plate ended up in a forum user's PEC — he picked the
    # Mount through the 'Feed' group, and the whole 'Feed' group came along
    # with the plate inside it. Said once per such group, naming the parts.
    for origin, group in expansions:
        mine = [g["label"] for g in group
                if any(_same_place(g, p) for p in picked)]
        extra = [g["label"] for g in group
                 if not any(_same_place(g, p) for p in picked)]
        if not mine or not extra:
            continue                    # a group alone, or fully picked: clear
        issues.append(("note", (
            "'{grp}' is referenced WHOLE and some of its parts are also "
            "picked on their own ({mine}); the whole-group reference ALSO "
            "brings in {extra}, which is therefore in this material too. If "
            "that is not intended, remove the '{grp}' reference and keep the "
            "part picks.").format(grp=_label(origin), mine=_names(mine, 6),
                                  extra=_names(extra, 8))))
    shown = []
    for root, path, objs in hidden_all:
        if _is_leaf(objs[-1]):
            rec = _leaf_record(root, path, objs, "",
                               _subobject_shape(root, path))
            if not _has_geometry(rec):
                continue                # a hidden sketch or datum: construction
            # ⚠ Hidden in the group but picked on its OWN as well: it IS in
            # the model (an explicit pick is honoured whatever the eye icon
            # says), so "left out" would be a false note — and the very part
            # a user just added on purpose would read as missing.
            if any(_same_place(rec, kept) for kept in leaves):
                continue
        lab = " > ".join(_label(o) for o in objs)
        if lab not in shown:
            shown.append(lab)
    if shown:
        issues.append(("note", (
            "{n} hidden part(s) inside a referenced group are left out, just "
            "as FreeCAD's own group shape leaves them out: {names}. Show "
            "them, or pick them on their own, to include them.").format(
                n=len(shown), names=_names(shown, 8))))
    return leaves, issues
