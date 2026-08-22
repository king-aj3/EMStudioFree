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

**Cost.** At 40 GHz lambda is 7.5 mm, so a lambda/20 grid is 0.375 mm and the
domain must hold the horn plus radiating padding. This is an expensive run by
EMStudio's standards; it is a SOLVER-tier gate, never part of the fast battery.
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
    flare_inner = _loft(WR28_A_MM, WR28_B_MM, z_throat - t,
                        APERTURE_A_MM, APERTURE_B_MM, z_aper + t)
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
