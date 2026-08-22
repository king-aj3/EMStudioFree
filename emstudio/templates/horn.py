# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pyramidal standard-gain horn template (Ka-band, waveguide-fed).

**Why this template exists.** Until v1.5.0 the highest GATED radiating
structure in EMStudio was a 2.435 GHz patch, while `docs/CAPABILITIES.md`
opened by saying the full-wave engines "reach mmWave". Both statements were
true and the gap between them was the problem: Palace's mmWave validation is on
CLOSED structures (waveguide, cavity), and nothing radiating had ever been
gated above 2.435 GHz. `emstudio/antenna/horn.py` could SYNTHESISE a horn and
no solver in the product could feed one, because openEMS had no waveguide port.
That port landed first; this is the geometry that uses it.

**The geometry is a real, purchasable part, and that is deliberate.**
Mi-Wave **261A-20/599**, a WR-28 Ka-band pyramidal standard gain horn, taken
from the vendor's dimensioned outline drawing (rev B, 9-12-18):

    aperture a1 (H-plane, broad wall)  1.570 in = 39.88 mm   [marked "INSIDE"]
    aperture b1 (E-plane)              1.100 in = 27.94 mm   [marked "INSIDE"]
    axial length, flange to aperture   2.640 in = 67.06 mm
    feed                               WR-28, 7.112 x 3.556 mm
    band                               26.5 - 40 GHz

⚠⚠ **THE ANCHOR IS VENDOR-PUBLISHED, NOT MEASURED, AND MUST BE LABELLED SO.**
The vendor's gain curve is smooth and monotonic with no ripple. Per Bodnar
(NSI-MI, "Numerical Calibration of Standard Gain Horns and OEWG Probes") a
genuinely RANGE-MEASURED standard-gain horn shows 0.1-0.2 dB ripple from
mouth/throat multiple reflections; a smooth curve is the signature of the
NRL/Slayton closed-form calculation. An independent Balanis implementation
reproduces the vendor curve to a near-constant 0.15-0.25 dB offset, which is
further evidence it is aperture theory rather than measurement. So a gate built
on this curve validates the solver against ANALYTIC APERTURE THEORY. That is
not circular — it is not the solver's own output — but it is weaker than a
measured anchor and the tutorial says so out loud.

⛳ **The analytic reference is itself measurement-anchored, one step removed.**
NIST (Francis et al., AMTA 2016, three-antenna extrapolation on the CROMMA
range) measured an electroformed pyramidal standard gain horn at 118.75 GHz:
**15.47 +/- 0.5 dB measured against 15.40 dB predicted**, agreeing to 0.07 dB.
So the pyramidal-horn gain prediction is known to track measurement deep into
mmWave; what this template gates is whether OUR solver reproduces it.

⚠ **Name the part, never "a 20 dB SGH".** Two vendors' nominal 20 dB WR-28
horns have materially different apertures (Mi-Wave 39.9 x 27.9 mm vs Pasternack
35.1 x 25.7 mm). "A 20 dBi standard gain horn" is not a specification.

⚠ **Do NOT re-source this anchor from Eravant or Anteral** — their datasheets
state outright that the pattern and gain data are SIMULATED, which would make
the gate circular.

**Cost.** At 40 GHz lambda is 7.5 mm, and this template asks for lambda/30
there — 0.2498 mm — over a domain holding the horn plus a wavelength of
radiating padding: **19.97 M cells, about 9 minutes** on a 128-thread box. That
is an expensive run by EMStudio's standards and it is deliberate; see
``makeHorn`` for the convergence table behind the choice. SOLVER tier, never
part of the fast battery.
"""

from __future__ import annotations

import FreeCAD
import Part

#: Mi-Wave 261A-20/599, from the vendor outline drawing. Inside dimensions.
WR28_A_MM = 7.112
WR28_B_MM = 3.556
APERTURE_A_MM = 39.88
APERTURE_B_MM = 27.94
FLARE_LEN_MM = 67.06

#: Wall thickness. The real part's aperture lip is 0.050 in = 1.27 mm; this is
#: electrically irrelevant at Ka band but the walls must be SOLID for the STL
#: path (see makeHorn), so it is modelled rather than idealised to zero.
WALL_THICKNESS_MM = 1.27

#: Vendor "Frequency vs Gain 261A-20/599", digitised at 0.5 GHz steps and
#: reproduced to within 0.02 dB. Analytic-grade, per the module docstring.
VENDOR_GAIN_DBI = {
    26.5: 18.8, 28.0: 19.2, 30.0: 19.7, 32.0: 20.2,
    34.0: 20.6, 36.0: 21.0, 38.0: 21.3, 40.0: 21.6,
}

#: IEEE Std 149-1979 p.95 puts the NRL closed form at +/-0.25 to +/-0.5 dB, and
#: Bodnar's seven-laboratory X-band intercomparison shows 0.2 dB spread between
#: labs on real measurements. ⚠ Do NOT tighten below this — we would be gating
#: against aperture theory's own uncertainty and calling it solver accuracy.
GAIN_TOL_DB = 0.5


def _rect_wire(a_mm, b_mm, z_mm):
    """A centred rectangle in the z = const plane, as a closed wire."""
    ha, hb = a_mm / 2.0, b_mm / 2.0
    pts = [FreeCAD.Vector(-ha, -hb, z_mm), FreeCAD.Vector(ha, -hb, z_mm),
           FreeCAD.Vector(ha, hb, z_mm), FreeCAD.Vector(-ha, hb, z_mm),
           FreeCAD.Vector(-ha, -hb, z_mm)]
    return Part.makePolygon(pts)


def makeHorn(doc=None, feed_len_mm=15.0, pad_mm=None):
    """Create the Mi-Wave 261A-20/599 horn analysis. Returns the analysis.

    ``feed_len_mm`` is the straight WR-28 section behind the throat. It exists
    so the TE10 port sits in uniform guide rather than in the flare, where the
    analytic mode profile would not be the local field and the port would
    mis-normalise.
    """
    from emstudio.objects import analysis as analysis_mod
    from emstudio.objects import material as material_mod
    from emstudio.objects import ports as ports_mod
    from emstudio.objects import solver_objs

    if doc is None:
        doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument()

    z_port = -feed_len_mm
    z_throat = 0.0
    z_aper = FLARE_LEN_MM

    # Walls are SOLIDS with a real thickness, matching upstream's own
    # Horn_Antenna tutorial (`horn.thickness`). `AddPolyhedronReader` wants a
    # closed polyhedron, and a closed solid is unambiguously that.
    # ⚠ HONEST NOTE ON WHY, because the first explanation written here was
    # WRONG. I claimed an open shell exported to zero facets and that this was
    # why the first solve produced no radiation. MEASURED afterwards: an open
    # lofted shell exports **148 facets** and a closed solid **152** — the
    # shell was never empty, and the empty-STL "finding" was an artefact of
    # counting ASCII "facet normal" lines in a BINARY STL file. Solids are
    # still the right choice (closed input, upstream's own convention), but
    # they are NOT the fix for the no-radiation result, which is still open.
    t = WALL_THICKNESS_MM

    def _loft(a0, b0, z0, a1, b1, z1):
        return Part.makeLoft([_rect_wire(a0, b0, z0), _rect_wire(a1, b1, z1)],
                             True, True)

    flare_outer = _loft(WR28_A_MM + 2 * t, WR28_B_MM + 2 * t, z_throat,
                        APERTURE_A_MM + 2 * t, APERTURE_B_MM + 2 * t, z_aper)
    # ⚠⚠ THE CUTTING TOOL MUST FOLLOW THE TAPER, NOT JUST OVERSHOOT IT.
    # The inner loft has to start below the throat and end above the mouth so
    # the boolean leaves no skin, but it was built by putting the FINAL
    # cross-sections at those overshot planes — WR-28 at z = -t and the full
    # aperture at z = L + t. That stretches the taper over L + 2t instead of L,
    # so the cavity is too NARROW at the mouth and too WIDE at the throat.
    # ⛳ MEASURED by parsing the binary STL the writer actually exports (the
    # BRep BoundBox is the loose pre-boolean one and says z 0..68.33 for a solid
    # that ends at 67.06 — read the tessellation, not the BoundBox):
    #     mouth  39.282 x 27.495 mm   against the drawing's 39.88 x 27.94
    #     throat  7.710 x  4.001 mm   against WR-28's 7.112 x 3.556
    # The mouth error is -0.135 dB of aperture area, and the throat error is a
    # step discontinuity where the feed section meets the flare — neither is
    # large, and both are invisible because horn_openems.py checks the
    # CONSTANTS above rather than the solid that gets built.
    # ⛳ Extrapolating along the taper instead puts z = 0 and z = L exactly on
    # the drawing; verified on the exported STL, 39.880 x 27.940 at the mouth
    # and 7.112 x 3.556 at the throat.
    slope_a = (APERTURE_A_MM - WR28_A_MM) / FLARE_LEN_MM
    slope_b = (APERTURE_B_MM - WR28_B_MM) / FLARE_LEN_MM
    flare_inner = _loft(WR28_A_MM - slope_a * t, WR28_B_MM - slope_b * t,
                        z_throat - t,
                        APERTURE_A_MM + slope_a * t, APERTURE_B_MM + slope_b * t,
                        z_aper + t)
    flare = doc.addObject("Part::Feature", "HornFlare")
    flare.Shape = flare_outer.cut(flare_inner)
    flare.Label = "Horn flare (PEC)"

    feed_outer = _loft(WR28_A_MM + 2 * t, WR28_B_MM + 2 * t, z_port,
                       WR28_A_MM + 2 * t, WR28_B_MM + 2 * t, z_throat)
    feed_inner = _loft(WR28_A_MM, WR28_B_MM, z_port - t,
                       WR28_A_MM, WR28_B_MM, z_throat + t)
    feed = doc.addObject("Part::Feature", "HornFeed")
    feed.Shape = feed_outer.cut(feed_inner)
    feed.Label = "WR-28 feed section (PEC)"

    face = doc.addObject("Part::Feature", "HornPortFace")
    face.Shape = Part.Face(_rect_wire(WR28_A_MM, WR28_B_MM, z_port))
    face.Label = "TE10 port face"

    ana = analysis_mod.makeAnalysis(doc)
    ana.Label = "Ka-band Horn (Mi-Wave 261A-20/599)"
    ana.FrequencyStart = "26.5 GHz"
    ana.FrequencyStop = "40 GHz"
    ana.FrequencyPoints = 271
    # ⛳ PML_8, not the MUR default. MUR is a first-order absorbing condition and
    # reflects enough of a horn's near field to corrupt the pattern; upstream's
    # horn tutorial uses PML_8 on all six faces for exactly this reason. A
    # closed-structure analysis can keep MUR; a radiating one should not.
    for _side in ("Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"):
        setattr(ana, "Boundary" + _side, "PML_8")
    # ⚠⚠ PML IS 8 CELLS THICK AND THE PADDING MUST CLEAR IT. The default
    # 0.25-wavelength padding is sized for the MUR boundary the patch template
    # uses — MUR is a single-cell condition, so 0.25 lambda of air is ample.
    # PML_8 occupies the OUTERMOST EIGHT CELLS of the mesh, and at this band
    # mesh_res is ~0.375 mm, so the absorber alone is 3.0 mm deep while
    # 0.25 lambda here is only 2.25 mm. The PML then starts INSIDE the horn
    # wall and swallows the structure: measured, the first run returned gain at
    # the -60 dBi pattern floor with eta_rad = nan, because the port accepted
    # no power at all.
    # ⛳ One wavelength leaves ~9 mm: three times the absorber depth, plus real
    # air for the aperture's near field to form in before it is absorbed.
    ana.DomainPaddingWavelengths = 1.0
    # ⚠⚠ lambda/30 AT THE BAND TOP, NOT THE lambda/20 DEFAULT — and this is a
    # COST decision as much as an accuracy one: 6.08 M cells becomes 19.97 M and
    # the solve goes from ~2 min to ~9 min on a 128-thread box. SOLVER tier, so
    # it never touches the fast battery.
    # ⛳ MEASURED on the shipped deck, directivity at 30.000 GHz against the
    # vendor's 19.7 dBi (the transform and the geometry both corrected first —
    # before that, refining appeared to make things WORSE, because the reading
    # was taken through a recording box that was counting backward radiation):
    #     MeshResolution 20   0.3747 mm    6.08 M cells   18.13 dBi   -1.57
    #     MeshResolution 30   0.2498 mm   19.97 M cells   19.29 dBi   -0.41
    #     MeshResolution 40   0.1874 mm   47.05 M cells   18.95 dBi   -0.75
    # ⚠⚠ IT IS NOT MONOTONE, AND THAT MATTERS MORE THAN THE HEADLINE. Run-to-run
    # directivity is reproducible to 0.0016 dB (ten identical decks), so the
    # 0.34 dB between lambda/30 and lambda/40 is REAL mesh behaviour — the
    # staircasing of a 13.7-degree slanted PEC flare on a Cartesian grid, whose
    # error oscillates rather than converging. Read the lambda/30 figure as
    # "19.3 dBi with about 0.3 dB of mesh uncertainty", not as a converged
    # number, and do NOT quote it to two decimals.
    ana.MeshResolution = 30

    metal = material_mod.makeMaterial(doc, ana, name="HornPEC")
    metal.Label = "Horn walls (PEC)"
    metal.References = [(flare, ""), (feed, "")]
    metal.Priority = 10

    port = ports_mod.makeLumpedPort(doc, ana, name="WGPort", direction="+Y")
    port.Label = "WR-28 TE10 port"
    port.PortType = "RectWaveguide"
    port.WaveguideMode = "TE10"
    port.PropagationDirection = "+Z"
    port.References = [(face, "")]

    solver = solver_objs.makeSolverOpenEMS(doc, ana)
    # ⚠⚠ PIN THE PATTERN FREQUENCY. The deck's default picks the far-field
    # frequency as argmin|S11| — the "best match". That is sensible for a
    # resonant antenna and MEANINGLESS for a horn, which is well matched right
    # across its band: S11 is flat, so the argmin lands on noise. Measured, the
    # SAME horn chose 28.45 GHz at one mesh density and 39.55 GHz at another,
    # which makes any comparison against a published gain curve accidental.
    # ⛳ Three patterns over a narrow window around 30 GHz means the reported
    # pattern is at a frequency we CHOSE, and the vendor curve can be read at
    # that frequency rather than wherever the solver happened to look.
    if "PatternFrequencies" in solver.PropertiesList:
        solver.PatternFrequencies = 3
        solver.PatternFreqStart = "29.5 GHz"
        solver.PatternFreqStop = "30.5 GHz"
    # The whole point is the far field; without this the run produces S11 only.
    if "ComputeFarField" in solver.PropertiesList:
        solver.ComputeFarField = True
    doc.recompute()
    return ana
