# SPDX-License-Identifier: LGPL-2.1-or-later
"""The EMStudio named-material library — pure data, no FreeCAD import.

Split out of ``material.py`` deliberately: the library is a table of physical
constants and the function that copies them onto an object, and NEITHER needs
FreeCAD. Keeping them importable from a bare interpreter is what lets
``tests/validation/material_loss.py`` assert the constants are sane in the FAST
battery, on a machine with no FreeCAD at all. A table of wrong constants is the
same defect class as a discarded sigma, one level up — so it has to be checkable
where the checks actually run.
"""

from __future__ import annotations

#: Named material library, in the spirit of CST/HFSS/FEKO: pick a material by
#: NAME and its properties come with it, or pick "Custom" and type your own.
#:
#: ⚠⚠ **EVERY VALUE HERE IS NOMINAL, AT ROOM TEMPERATURE.** Real conductivity
#: moves with alloy, temper and work-hardening; real permittivity moves with
#: grade, resin content, moisture and FREQUENCY. FR-4 in particular is a class
#: of laminates rather than a material — 4.2-4.8 and tan(d) 0.017-0.025 are all
#: legitimately "FR-4", and it is dispersive across a decade of frequency.
#: These entries are a sane starting point and a labelled one; they are NOT a
#: datasheet. For anything you will build, measure or take the vendor's number
#: and use "Custom". This is the same caveat every commercial library carries,
#: stated out loud rather than buried.
#:
#: sigma_s_m: electric conductivity, S/m at 20 C.
#: alpha_per_k: temperature coefficient of RESISTIVITY, per K.
#: mu_r: relative permeability — ferromagnetics are flagged because a mu_r of
#: several hundred changes skin depth by more than an order of magnitude and is
#: the thing people forget when they model a steel mast as "metal".
MATERIAL_LIBRARY = {
    # ---- the idealisation, and the default -------------------------------
    # ⛳ PEC is not a placeholder for "we do not know" — it is a legitimate and
    # often CORRECT modelling choice: for a well-made antenna in air, conductor
    # loss is a fraction of a dB and PEC gets you the pattern and the impedance
    # for far less compute. It stays the DEFAULT for an unspecified material,
    # so every existing document and template is unchanged. Reach for a real
    # metal when loss is the question: small/electrically-short radiators,
    # high-Q coils, anything ferromagnetic, or mmWave where surface resistance
    # starts to matter.
    "Perfect conductor (PEC)": {
        "category": "Metal (PEC)"},
    # ---- conductors ------------------------------------------------------
    "Copper (annealed, 100% IACS)": {
        "category": "Conductor", "sigma_s_m": 5.800e7,
        "alpha_per_k": 0.00393, "mu_r": 1.0},
    "Copper (hard-drawn)": {
        "category": "Conductor", "sigma_s_m": 5.650e7,
        "alpha_per_k": 0.00393, "mu_r": 1.0},
    "Silver": {
        "category": "Conductor", "sigma_s_m": 6.300e7,
        "alpha_per_k": 0.00380, "mu_r": 1.0},
    "Gold": {
        "category": "Conductor", "sigma_s_m": 4.100e7,
        "alpha_per_k": 0.00340, "mu_r": 1.0},
    "Aluminium (1350, pure)": {
        "category": "Conductor", "sigma_s_m": 3.770e7,
        "alpha_per_k": 0.00429, "mu_r": 1.0},
    "Aluminium 6061-T6": {
        "category": "Conductor", "sigma_s_m": 2.500e7,
        "alpha_per_k": 0.00429, "mu_r": 1.0},
    "Brass (C26000, 70/30)": {
        "category": "Conductor", "sigma_s_m": 1.600e7,
        "alpha_per_k": 0.00200, "mu_r": 1.0},
    "Phosphor bronze": {
        "category": "Conductor", "sigma_s_m": 7.400e6,
        "alpha_per_k": 0.00200, "mu_r": 1.0},
    "Zinc": {
        "category": "Conductor", "sigma_s_m": 1.690e7,
        "alpha_per_k": 0.00370, "mu_r": 1.0},
    "Tin": {
        "category": "Conductor", "sigma_s_m": 9.170e6,
        "alpha_per_k": 0.00450, "mu_r": 1.0},
    "Solder (Sn60Pb40)": {
        "category": "Conductor", "sigma_s_m": 6.700e6,
        "alpha_per_k": 0.00000, "mu_r": 1.0},
    "Tungsten": {
        "category": "Conductor", "sigma_s_m": 1.790e7,
        "alpha_per_k": 0.00450, "mu_r": 1.0},
    "Titanium": {
        "category": "Conductor", "sigma_s_m": 2.380e6,
        "alpha_per_k": 0.00380, "mu_r": 1.0},
    # ⚠ ferromagnetic: mu_r >> 1 collapses skin depth. Values are wildly
    # grade- and field-dependent; these are order-of-magnitude placeholders.
    "Nickel (ferromagnetic)": {
        "category": "Conductor", "sigma_s_m": 1.430e7,
        "alpha_per_k": 0.00600, "mu_r": 100.0},
    "Steel, mild 1018 (ferromagnetic)": {
        "category": "Conductor", "sigma_s_m": 6.990e6,
        "alpha_per_k": 0.00500, "mu_r": 500.0},
    "Stainless steel 304": {
        "category": "Conductor", "sigma_s_m": 1.450e6,
        "alpha_per_k": 0.00100, "mu_r": 1.02},
    "Graphite (isotropic)": {
        "category": "Conductor", "sigma_s_m": 1.000e5,
        "alpha_per_k": 0.00000, "mu_r": 1.0},
    "Seawater (35 PSU, 20 C)": {
        "category": "Conductor", "sigma_s_m": 4.8,
        "alpha_per_k": 0.00000, "mu_r": 1.0},
    # ---- dielectrics -----------------------------------------------------
    "Air / vacuum": {
        "category": "Dielectric", "eps_r": 1.000, "tan_d": 0.0000},
    "PTFE (Teflon)": {
        "category": "Dielectric", "eps_r": 2.100, "tan_d": 0.0002},
    "Polyethylene (HDPE)": {
        "category": "Dielectric", "eps_r": 2.250, "tan_d": 0.0003},
    "Polystyrene": {
        "category": "Dielectric", "eps_r": 2.550, "tan_d": 0.0001},
    "RT/duroid 5880": {
        "category": "Dielectric", "eps_r": 2.200, "tan_d": 0.0009},
    "Rogers RO4003C": {
        "category": "Dielectric", "eps_r": 3.380, "tan_d": 0.0027},
    "FR-4 (typical)": {
        "category": "Dielectric", "eps_r": 4.400, "tan_d": 0.0200},
    "Polycarbonate": {
        "category": "Dielectric", "eps_r": 2.900, "tan_d": 0.0100},
    "ABS": {
        "category": "Dielectric", "eps_r": 2.700, "tan_d": 0.0060},
    "Nylon 6/6": {
        "category": "Dielectric", "eps_r": 3.400, "tan_d": 0.0200},
    "Glass (borosilicate)": {
        "category": "Dielectric", "eps_r": 4.600, "tan_d": 0.0050},
    "Alumina (96%)": {
        "category": "Dielectric", "eps_r": 9.400, "tan_d": 0.0010},
}

#: PEC leads, and is the default for an unspecified material — an idealised
#: lossless metal is the right starting point and keeps every existing document
#: byte-identical. "Custom" means "leave my typed numbers alone" and is the
#: escape hatch, not the default.
PEC_PRESET = "Perfect conductor (PEC)"
PRESETS = ([PEC_PRESET, "Custom"]
           + sorted(k for k in MATERIAL_LIBRARY if k != PEC_PRESET))


def apply_preset(obj, name):
    """Copy a library material's properties onto ``obj``. No-op for Custom.

    Sets Category too, because picking "Copper" and leaving the category on
    "Metal (PEC)" would silently discard the conductivity the user just chose —
    the exact defect this library exists to end.

    ⚠⚠ **EVERY BRANCH WRITES EVERY FIELD**, including the ones its own category
    never uses. Until 2026-08-29 each branch set only its own numbers, so a
    preset was applied to whichever fields it happened to name and the rest kept
    the PREVIOUS material's values. Copper → FR-4 left ``Conductivity`` at
    5.8e7 on a Dielectric and ``openems/writer.py:281`` reads that field back
    out for exactly this category (``entry["kappa"] = float(mat.Conductivity)``,
    emitted at :757), so the tutorial patch's substrate went into the deck as
    ``AddMaterial(..., epsilon=4.4, kappa=58000000)`` — a metal slab where the
    user had asked for FR-4, and 5.9e9× the ~0.0098 S/m that eps_r 4.4 / tan(d)
    0.02 actually implies at 2 GHz. The tan(d) they had just picked was thrown
    away with it, because :753 only synthesises kappa from tan(d) when kappa is
    zero. Nothing on screen contradicted any of it: the property editor showed
    the right eps_r and tan(d) the whole time. Steel → PTFE was worse again
    (mue=500 on a Teflon block), and the Dielectric → Conductor / → PEC
    directions leave a stale eps_r/tan(d) that ``palace/model.py:57-59`` reads
    regardless of Category.

    The values written for the fields a category does not define are
    ``material.py``'s OWN property defaults — eps_r 1, tan(d) 0, sigma 0,
    alpha 0, mu_r 1, i.e. vacuum. That is what "this preset says nothing about
    that" has to mean by the time a writer sees it; anything else is the
    previous material leaking through.
    """
    entry = MATERIAL_LIBRARY.get(str(name))
    if entry is None:
        return False
    obj.Category = entry["category"]
    if entry["category"] == "Metal (PEC)":
        # PEC carries no sigma by definition. Zero it so a material switched
        # DOWN from copper to PEC cannot leave a stale 5.8e7 behind for a
        # writer to pick up — a half-applied preset is worse than none.
        obj.Conductivity = 0.0
        obj.ConductivityTempCoeff = 0.0
        obj.RelPermeability = 1.0
        obj.RelPermittivity = 1.0
        obj.LossTangent = 0.0
    elif entry["category"] == "Dielectric":
        obj.RelPermittivity = float(entry["eps_r"])
        obj.LossTangent = float(entry["tan_d"])
        # Every dielectric in this library is an insulator and non-magnetic:
        # its loss is carried by tan(d) ALONE. sigma and alpha go together —
        # elmer/model.py:201 refuses an alpha with no sigma to scale.
        obj.Conductivity = 0.0
        obj.ConductivityTempCoeff = 0.0
        obj.RelPermeability = 1.0
    else:
        obj.Conductivity = float(entry["sigma_s_m"])
        obj.ConductivityTempCoeff = float(entry["alpha_per_k"])
        obj.RelPermeability = float(entry.get("mu_r", 1.0))
        # A metal's bound-charge permittivity is not a modelling input here —
        # the conduction term carries the physics — so the previous material's
        # eps_r/tan(d) must not survive into a solver that reads them anyway.
        obj.RelPermittivity = 1.0
        obj.LossTangent = 0.0
    # ⛳ BHCurveB/BHCurveH are deliberately NOT reset: no library entry supplies
    # a B-H table, so there is nothing to overwrite them WITH, and they are
    # measured user data rather than a nominal constant. Clearing them needs its
    # own decision — do not "finish the sweep" here without making it.
    return True
