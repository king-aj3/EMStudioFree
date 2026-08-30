# EMStudio — external validation record

**Swept 2026-08-30.** Every reference value the validation gates anchor on was
traced back to its source on the open web and compared digit by digit.
Method: 13 tracer agents, primary-source-only rules of evidence; every claimed mismatch adversarially re-verified by a second agent that fetched the source itself; 21 agents, 989 tool calls.

**Scoreboard: 172 anchors traced — 144 CONFIRMED against primary sources, 13 corroborated (secondary only), 7 mismatches found (ALL now corrected — see below), 8 unverifiable.**

Rules of evidence: a PRIMARY source is the original paper, standard,
report or datasheet (or an official scan of it). Secondary sources can
only CORROBORATE. An agent's memory of a table counts for nothing — a
value nobody could re-read in a fetched document is UNVERIFIABLE, not
confirmed. Every claimed mismatch was re-verified by a second agent
that fetched the source itself before being believed.

## Works validated against

| Work | Confirmed | Corroborated | Mismatch | Unverifiable |
|---|---|---|---|---|
| **NBS TN-688** — P. P. Viezbicke, “Yagi Antenna Design”, NBS Technical Note 688, Dec 1976 — official NIST scan, read digit-by-digit | 11 | 0 | 1 | 0 |
| **Lyn 1995 / Tian 2013** — D. A. Lyn, S. Einav, W. Rodi, J.-H. Park, J. Fluid Mech. 304 (1995) square-cylinder LDV at Re 21,400; Tian et al. URANS companion study | 5 | 2 | 0 | 0 |
| **Cylinder-flow benchmarks** — C. H. K. Williamson St(Re) relation; Qu, Norberg, Davidson, Peng & Wang (2013); Braza, Chassaing & Ha Minh, JFM 165 (1986) via published comparison tables | 1 | 4 | 0 | 1 |
| **Betts & Bokhari / ERCOFTAC 079** — P. L. Betts, I. H. Bokhari, Int. J. Heat Fluid Flow 21 (2000) tall-cavity experiment — ERCOFTAC Classic Collection case 079; digitised profiles verified against the copies shipped inside ESI OpenFOAM v2512 | 6 | 0 | 0 | 0 |
| **Huynh thesis** — M. Huynh, M.S. thesis (Virginia Tech), PIFA ground-plane study — Table 5-1 anechoic-chamber column | 12 | 0 | 0 | 0 |
| **TEAM Problem 7** — TEAM benchmark Problem 7 (compumag.org problem7.pdf): geometry, drive, and the measured Bz line data | 9 | 1 | 0 | 1 |
| **Belden coax datasheets** — Belden 8240 / 9310 (RG-58, RG-142) manufacturer datasheets; twinax/foam-PE line constants | 18 | 1 | 0 | 3 |
| **Cat5e/Cat6 (TIA class)** — TIA-568-class Cat5e/Cat6 twisted-pair characteristics | 1 | 0 | 0 | 0 |
| **Pozar** — D. M. Pozar, Microwave Engineering, 4th ed. — TE10 waveguide relations (eq. 3.22 chain) | 11 | 0 | 0 | 0 |
| **Nikolova L18** — N. K. Nikolova (McMaster), Lecture 18: Rectangular Horn Antennas — Balanis-derived design chain, eqs 18.24–18.51 | 1 | 0 | 1 | 0 |
| **Stutzman & Thiele** — W. L. Stutzman, G. A. Thiele, Antenna Theory and Design, 2nd ed. — horn phase-error optima | 3 | 0 | 1 | 0 |
| **Balanis** — C. A. Balanis, Antenna Theory: Analysis and Design, 3rd/4th ed. — horn ch. 13 (incl. the author’s published design code) and LPDA Fig 11.13, measured from the PDF’s embedded vector geometry | 26 | 3 | 1 | 0 |
| **Churchill correlations** — S. W. Churchill & H. H. S. Chu, IJHMT 18 (1975) cylinder correlation; Churchill sphere correlation (HEDH/Schlünder 1987; Incropera eq. 9.35 form) | 3 | 1 | 1 | 0 |
| **Incropera / Cengel** — F. P. Incropera et al., Fundamentals of Heat and Mass Transfer (Table 9.1); Y. A. Cengel, Heat Transfer, 2nd ed. worked examples; Cieslinski et al. sphere data | 1 | 0 | 0 | 0 |
| **AHTT (Lienhard)** — J. H. Lienhard IV & V, A Heat Transfer Textbook, 6th ed. — air property table A.6; eq. 8.33 page image read for the citation correction | 1 | 0 | 0 | 0 |
| **Yaghjian & Best** — A. D. Yaghjian, S. R. Best, “Impedance, Bandwidth, and Q of Antennas” (IEEE TAP 2005 / DTIC ADA418158) | 1 | 0 | 0 | 0 |
| **NUWC TR (Rivera & Casey)** — Rivera & Casey, NUWC-NPT Technical Report — tubular monopole capacitance formulas | 0 | 1 | 0 | 0 |
| **Carrel / Butson-Thompson** — R. L. Carrel (1961) LPDA design method; P. C. Butson & G. T. Thompson, IEEE Trans. AP-24 (1976) 1 dB gain correction | 3 | 0 | 0 | 0 |
| **ITU-R Recommendations** — ITU-R P.452-18, P.1546-6, P.1812-8, P.2001 — Recommendation texts and the official SG3 validation sets, via the OFCOM (Stevanovic) reference implementations | 17 | 0 | 2 | 0 |
| **openEMS project** — The openEMS project’s published patch and inverted-F examples — geometry and resonance anchors | 7 | 0 | 0 | 1 |
| **A. D. Watt** — A. D. Watt, VLF Radio Engineering, Pergamon 1967 — independently checkable statements only | 2 | 0 | 0 | 0 |
| **Mi-Wave gain curve** — Mi-Wave standard-gain horn published Ka-band gain curve | 0 | 0 | 0 | 1 |
| **NIST CODATA** — NIST CODATA 2018/2022 recommended values — c, η0, ε0, μ0 | 2 | 0 | 0 | 0 |
| **ESI OpenFOAM v2512 tree** — Reference data and tutorial cases shipped inside the ESI OpenFOAM v2512 release itself, diffed against the upstream archives | 3 | 0 | 0 | 0 |
| **Recomputed closed forms** — Values re-derived by direct computation from the cited formula during the sweep (checked against the named text where one exists) | 0 | 0 | 0 | 1 |

## The seven mismatches — found by this sweep, all corrected 2026-08-30

None touched a solved physics result; they were transcription labels,
citations, one chart-read table and one gate-scoring offset note:

* **dBd-to-dBi offset used to score the gate: 2.15 dB**
  * repo said: DBD_OFFSET = 2.15 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/wire_elements.py:54; applied as g_dbd = g_dbi - 2.15 at tests/validation/yagi_nec2.py:123 and :145
  * source says: TN-688 section 2 (doc p.1): 'If referenced to an isotropic source, the values must be increased by 2.16 dB'
  * citation: NBS TN-688, section 2, doc p.1 (NIST scan PDF p.11, page image)

* **Docstring claim: optimum phase error 's = 1/8 in the E-plane, 3/8 in the H-plane'**
  * repo said: '(s = 1/8 in the E-plane, 3/8 in the H-plane)' — emstudio/antenna/horn.py:17
  * source says: Stutzman 2e eq (7-144) context: 'The aperture efficiencies for optimum sectoral horns with s = 0.25 and t = 0.375'; design Step 4 (p.314): 'see if s = 0.25 and t = 0.375'; Nikolova L18: E-plane optimum at q = 1, i.e. s = B^2/(8*lambda*R) = 1/4; Balanis (13-19b
  * citation: Stutzman 2e (7-144) and p.314-315; Balanis 3e (13-19a/b); archive.org scans

* **Aspect-ratio claim: a1 ~ 1.5*b1, 'which is what the E- and H-plane optimum flare conditions imply together'**
  * repo said: 'optimum-horn aspect ratio a1 ~ 1.5*b1' + derivation claim — emstudio/antenna/horn.py:99-101; baked in at horn.py:108-111 (b1 = sqrt(area/1.5), a1 = 1.5*b1); repeated in source_note horn.py:150
  * source says: The optimum flare conditions imply a1/b1 = sqrt(3*lambda*rho)/sqrt(2*lambda*rho) = sqrt(1.5) = 1.225 for equal flare lengths — i.e. a1^2 = 1.5*b1^2, not a1 = 1.5*b1. Realizable textbook optimum designs land near that: Balanis 3e Example 13.6 gives a1/b1 = 6.00
  * citation: Balanis 3e sec 13.4.3 + Example 13.6 (p.781-782); Stutzman 2e Example 7-7 (p.315); Nikolova L18 eq (18.42)-(18.51) (realizability RE = RH, no fixed ratio)

* **Repo's sphere attribution 'AHTT eq. 8.33 form' next to the 0.469 constant**
  * repo said: '(AHTT eq. 8.33 form), Ra_D <= 1e11, Pr >= 0.7 ... (0.469/Pr)' — tests/validation/openfoam_solid.py:86-87 and openfoam_ras_solid.py:59
  * source says: AHTT eq. (8.33) actually prints Nu_D = 2 + 0.589 Ra_D^(1/4)/[1+(0.492/Pr)^(9/16)]^(4/9) with 'Ra_D < 10^12' — constant 0.492, not 0.469; no Pr restriction stated — in BOTH v5.10 (p. 456 area, wayback copy) and v6.00 (p. 433, page image). AHTT cites its [8.11] 
  * citation: AHTT v6.00 eq. 8.33 p. 433 (ahtt.mit.edu PDF, page image read) and AHTT v5.10 (web.archive.org copy of ahtt.mit.edu); vs Incropera 6th ed eq. 9.35 / Cengel 2nd ed eq. 9-26 which print the repo's 0.469

* **SIGMA006_TABLE: corrected-contour crossings at sigma = 0.06 (5 rows)**
  * repo said: [(6.5,0.852),(7.0,0.887),(7.5,0.920),(8.0,0.939),(8.5,0.957)] — emstudio/antenna/lpda.py:78-84
  * source says: Pixel-measured crossings at sigma=0.06 on the corrected chart (Balanis 3e print AND official 4e ch11.pptx, identical): 6.5->0.8486, 7.0->0.8848, 7.5->0.9105, 8.0->0.9355, 8.5->0.9565 (curve end; row scans at sigma 0.065/0.070/0.075 extrapolate 0.956-0.961)
  * citation: Balanis Fig 11.13, both printings, 300-dpi pixel measurement with clean-row cross-checks at sigma 0.065/0.070/0.075; consistency check: ARRL ch.10 worked example reads its (original-calibration) chart

* **py1812 vendored revision label: repo says P.1812-6**
  * repo said: 'the ITU-R reference implementation of Recommendation P.1812-6' — emstudio/vendor/py1812/PROVENANCE.md:4 (also emstudio/coverage/p1812.py:2,29 and tests/validation/p1812.py:2)
  * source says: itu.int: P.1812-6 (09/2021) SUPERSEDED — in force is P.1812-8 (09/2025). The pinned upstream commit a5205e6 (2026-05-18) postdates upstream's 'eeveetza-p1812-8' merge (2026-02-25: Ct argument removed, Gtx/Grx added, README changed to 'Recommendation ITU-R P.18
  * citation: https://www.itu.int/rec/R-REC-P.1812/en; https://github.com/eeveetza/Py1812 commit history + README @ a5205e6a65db27391a8ba79bd5a365e5391f9fdf

* **p1812 data PROVENANCE wording: '64 per-dataset logs' and 'Ver 6.1 set'**
  * repo said: tests/validation/data/p1812/PROVENANCE.md:4-5
  * source says: 63 log files exist on disk and 63 exist at the pinned upstream commit; ITU's current published validation folder holds 64 files = 63 per-dataset logs + 1 combined_results.csv. ITU's SG3 page today lists the P.1812 validation set only as version 8.0 (no 6.1 vis
  * citation: local ls + GitHub tree @ a5205e6 + itu.int P_1812_8.zip listing

## Every anchor, by work

### NBS TN-688
*P. P. Viezbicke, “Yagi Antenna Design”, NBS Technical Note 688, Dec 1976 — official NIST scan, read digit-by-digit*

* [CONFIRMED] **Table 1 measured gain row: 7.1 / 9.2 / 10.2 / 12.25 / 13.4 / 14.2 dBd at booms 0.4 / 0.8 / 1.2 / 2.2 / 3.2 / 4.2 lambda**
  * repo: TN688_TABLE1 gain_dbd values 7.1, 9.2, 10.2, 12.25, 13.4, 14.2 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:61-75; same row in /home/ajenkins/PycharmProjects/EMStudioPro/docs
  * source: 7.1 / 9.2 / 10.2 / 12.25 / 13.4 / 14.2 dB relative to half-wave dipole
  * cite: NBS Technical Note 688, P.P. Viezbicke, 'Yagi Antenna Design', December 1976, Table 1, document p.7 (official NIST scan, nvlpubs.nist.gov/nistpubs/Legacy/TN/nbstechnicalnote688.pdf, PDF p.17, read as 
* [CONFIRMED] **Table 1 reflector lengths: 0.482 lambda for the five booms 0.4-3.2, 0.475 lambda for 4.2**
  * repo: reflector: 0.482 (x5), 0.475 (4.2 row) at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:61-73; docs/upstream/tn688-yagi-anchors.md:22
  * source: LENGTH OF REFLECTOR, lambda: 0.482, 0.482, 0.482, 0.482, 0.482, 0.475
  * cite: NBS TN-688, Table 1, doc p.7 (NIST scan PDF p.17, page image)
* [CONFIRMED] **Table 1 per-director lengths, all six boom columns (incl. the disputed 0.4-lambda single director 0.424 and the non-monotonic tails)**
  * repo: directors lists at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:62-75 — 0.4:[0.424]; 0.8:[0.428,0.424,0.428]; 1.2:[0.428,0.420,0.420,0.428]; 2.2:[0.432,0.415,0.407,0.398,0.390x4
  * source: Identical, every cell: 0.4-lambda 1st director reads 0.424 in the primary scan; 2.2 column runs 0.432/0.415/0.407/0.398/0.390 0.390 0.390 0.390/0.398/0.407; 3.2 column 0.428/0.420/0.407/0.398/0.394/0.390 then 0.386 for 7
  * cite: NBS TN-688, Table 1, doc p.7 (NIST scan PDF p.17, page image)
* [CONFIRMED] **Table 1 director-spacing row: 0.20 / 0.20 / 0.25 / 0.20 / 0.20 / 0.308 lambda**
  * repo: spacing: 0.20, 0.20, 0.25, 0.20, 0.20, 0.308 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:61-73; docs/upstream/tn688-yagi-anchors.md:38
  * source: SPACING BETWEEN DIRECTORS, IN lambda: 0.20, 0.20, 0.25, 0.20, 0.20, 0.308
  * cite: NBS TN-688, Table 1, doc p.7 (NIST scan PDF p.17, page image); 0.308 also in Example 2 GIVEN (doc p.19: '0.308 lambda = 11.2 cm') and Fig 9 legend ('13 DIR, 1 REFL, S=0.308lambda')
* [CONFIRMED] **Table 1 basis conditions: d/lambda = 0.0085, f = 400 MHz, reflector 0.2 lambda behind driven**
  * repo: D_REF = 0.0085 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:45; reflector position 0.2 lambda at yagi.py:232 and reflector_spacing_lambda 0.2 at yagi.py:259; 400 MHz default 
  * source: Table 1 footer: 'ELEMENT DIAMETER = 0.0085', 'f = 400 MHz', 'REFLECTOR SPACED 0.2lambda BEHIND DRIVEN ELEMENT'; section 2: 'All measurements were conducted at a modeling frequency of 400 MHz'; section 3.2: elements 0.008
  * cite: NBS TN-688, Table 1 footer doc p.7; section 2 doc p.1; section 3.1/3.2 doc p.2; Fig 1 doc p.3 (NIST scan, page images)
* [CONFIRMED] **yagi_nec2.py gate regression dict: measured = {0.4: 7.1, 0.8: 9.2, 1.2: 10.2, 2.2: 12.25}**
  * repo: measured = {0.4: 7.1, 0.8: 9.2, 1.2: 10.2, 2.2: 12.25} at /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/yagi_nec2.py:140
  * source: Table 1 gain row: 7.1 (0.4), 9.2 (0.8), 10.2 (1.20), 12.25 (2.2)
  * cite: NBS TN-688, Table 1, doc p.7 (NIST scan PDF p.17, page image)
* [CONFIRMED] **Fig 10 boom-correction anchors: D/lambda 0.0085 -> +0.005 lambda; D/lambda 0.035 -> +0.026 lambda (and the repo's log-linear model BOOM_B0=0.005, BOOM_SLOPE=0.0**
  * repo: BOOM_B0 = 0.005, BOOM_SLOPE = 0.03416 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:51-52; anchors documented at docs/upstream/tn688-yagi-anchors.md:54-57
  * source: Example 1 STEP 5 (doc p.17): 'For a boom diameter-to-wavelength ratio D/lambda = 0.0085 ... From the chart this length = 0.005 lambda'; Example 2 STEP 5 (doc p.19): 'D/lambda = 0.035 ... From the curve, determine this le
  * cite: NBS TN-688, section 4 worked examples STEP 5, doc pp.17 and 19; Fig 10 doc p.10 (NIST scan, page images)
* [CONFIRMED] **Fig 9 diameter-compensation model: K_DIR = 0.048, K_REFL = 0.010 (lambda per decade of d/lambda)**
  * repo: K_DIR = 0.048, K_REFL = 0.010 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:48-49; model documented at docs/upstream/tn688-yagi-anchors.md:63-72
  * source: TN-688 publishes only the Fig 9 curves (doc p.9); the checkable primary digits are the worked-example endpoints: Ex.1 (d/lambda 0.0085->0.0042): directors 0.428->0.442, 0.424->0.438, reflector 0.482->0.485; Ex.2 (0.0085-
  * cite: NBS TN-688, section 4 STEPs 1-4 of both examples, doc pp.17 and 19; Fig 9 doc p.9 (NIST scan, page images)
* [CONFIRMED] **Worked example 1 (0.8-lambda Yagi, 50.1 MHz): full digit chain**
  * repo: docs/upstream/tn688-yagi-anchors.md:74-80 — lambda=597 cm, d/lambda=0.0042, D/lambda=0.0085 (+0.005 corr), spacing 0.2 lambda=119 cm; reflector 0.482->0.485->0.490 lambda=293 cm; D1=D3 0.428->0.442->0
  * source: GIVEN (doc p.16): 50.1 MHz, lambda=597 cm (235 in), d=2.54 cm, d/lambda=0.0042, D=5.1 cm, D/lambda=0.0085, spacing 0.2 lambda=119 cm; STEPs 1-5 (doc p.17): L_D1=L_D3=0.428, L_D2=0.424, L_R=0.482; uncompensated 0.442/0.43
  * cite: NBS TN-688, section 4 Example 1, doc pp.16-17 (NIST scan PDF pp.26-27, page images)
* [CONFIRMED] **Worked example 2 (4.2-lambda Yagi, 827 MHz, 13 directors): full digit chain**
  * repo: docs/upstream/tn688-yagi-anchors.md:82-87 — lambda=36.34 cm, d/lambda=0.013, D/lambda=0.035 (+0.026 corr), spacing 0.308 lambda=11.2 cm; reflector 0.499 lambda=18.1 cm; D1=D2 0.440=16.0; D3 0.435=15.8
  * source: GIVEN (doc p.19): 827 MHz, lambda=36.34 cm (14.3 in), d=0.48 cm, d/lambda=0.013, D=1.27 cm, D/lambda=0.035, spacing 0.308 lambda=11.2 cm; final cut lengths (doc p.21): D1=D2 0.414+0.026=0.440 lambda=16.0 cm; D3 0.435=15.
  * cite: NBS TN-688, section 4 Example 2, doc pp.19-21 (NIST scan PDF pp.29-31, page images)
* [CONFIRMED] **Fig 9 design-curve letters and the flagged Table-1-vs-Fig-9 grouping discrepancy**
  * repo: curve: A/B/B/C/B/D per boom at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/yagi.py:61-73; discrepancy flag at docs/upstream/tn688-yagi-anchors.md:112-118
  * source: Table 1 row 'DESIGN CURVE (SEE FIG. 9)': (A)(B)(B)(C)(B)(D). Fig 9's own legend box (doc p.9, repeated in Figs 20/21): (A) 0.4-lambda 1 dir; (B) 2.2-lambda 10 dir; (C) 0.8-lambda 3 dir + 1.2-lambda 4 dir + 3.2-lambda 15 
  * cite: NBS TN-688, Table 1 doc p.7 and Fig 9 doc p.9 (legend re-printed identically in Fig 20 doc p.18 and Fig 21 doc p.20)
* [MISMATCH] **dBd-to-dBi offset used to score the gate: 2.15 dB**
  * repo: DBD_OFFSET = 2.15 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/antenna/wire_elements.py:54; applied as g_dbd = g_dbi - 2.15 at tests/validation/yagi_nec2.py:123 and :145
  * source: TN-688 section 2 (doc p.1): 'If referenced to an isotropic source, the values must be increased by 2.16 dB'
  * cite: NBS TN-688, section 2, doc p.1 (NIST scan PDF p.11, page image)

### Lyn 1995 / Tian 2013
*D. A. Lyn, S. Einav, W. Rodi, J.-H. Park, J. Fluid Mech. 304 (1995) square-cylinder LDV at Re 21,400; Tian et al. URANS companion study*

* [CONFIRMED] **Lyn et al. (1995) Strouhal number 0.132 at Re 21,400**
  * repo: St 0.132 — tests/validation/openfoam_wind_ras.py:16 (also 'measured 0.132' at :79 and in the gate check label :164)
  * source: f = 1.77 +/- 0.05 Hz; St = fH/U = 0.132 +/- 0.004 (ERCOFTAC Classic Collection case 043, the official archive/description of the Lyn & Rodi LDV dataset); Tian et al. 2013 Table 3 quotes 0.132; Trias et al. 2015 Table 2 q
  * cite: ERCOFTAC Classic Collection case043, http://cfd.mace.manchester.ac.uk/ercoftac/doku.php?id=cases:case043 (fetched, text read); Cambridge JFM 304 abstract page confirms Re ~= 21400; Tian, Ong, Yang & M
* [CONFIRMED] **Lyn et al. (1995) mean drag coefficient 2.1 at Re 21,400**
  * repo: Cd 2.1 — tests/validation/openfoam_wind_ras.py:16 (window rationale :30, 'Lyn 2.1' also at :9 and :78)
  * source: 'At x/H = 8, the time-averaged drag coefficient was estimated from the integral of the time-averaged streamwise momentum flux to be 2.1, which agrees with accepted literature values' (ERCOFTAC case043); Tian Table 3 row 
  * cite: ERCOFTAC Classic Collection case043 (fetched); Tian et al. 2013 Table 3 (fetched primary PDF); Trias, Gorobets & Oliva 2015 Table 2 (fetched UPCommons manuscript)
* [CONFIRMED] **Tian et al. (2013) OpenFOAM 2-D URANS k-omega SST: Cd 2.060, St 0.138, Cl,rms 1.492**
  * repo: 'Cd 2.060, St 0.138, Cl,rms 1.492' — tests/validation/openfoam_wind_ras.py:19-20
  * source: Table 3 row 1: 'Present k-o SST 21,400 2.060 1.492 0.138'; identical in the grid/time-resolution table, case A3 (77,670 elements, DtU/H=0.004): CD 2.060, CLrms 1.492, St 0.138
  * cite: Tian, Ong, Yang & Myrhaug, Ocean Engineering 58 (2013) 208-216, publisher-typeset PDF hosted by the first author's institution: https://naoce.sjtu.edu.cn/upload/1489051464214210.pdf (fetched, text ext
* [CORROBORATED] **Bosch & Rodi (1998) k-epsilon St 0.146 (ceiling of the asymmetric St window)**
  * repo: 'just over Bosch & Rodi's k-epsilon 0.146' — tests/validation/openfoam_wind_ras.py:28
  * source: Tian Table 3 row 7: 'Bosch and Rodi (1998) k-e (2D) 22,000 2.108 1.012 0.146'
  * cite: Quoted in Tian et al. 2013 Table 3 (fetched primary PDF of Tian; secondary with respect to Bosch & Rodi's own paper, IJHFF 19:186, which I could not fetch)
* [CONFIRMED] **RAS gate windows and their inputs: St [0.125, 0.150]; Cd [1.95, 2.25] covering 'experiments 2.05-2.2, DNS 2.18, 2-D URANS 2.05-2.11'; Cl amp [1.1, 3.0] from 'pu**
  * repo: tests/validation/openfoam_wind_ras.py:25-36 (design), :159-170 (checks). Repo-measured results Cd 2.1304/2.1358, St 0.1356, Cl amp 2.49/2.52 (:75-84) sit inside all three
  * source: Tian Table 3: 2-D URANS Cd 2.060/2.108/2.05 (exactly the claimed 2.05-2.11), Cl,rms 0.984-1.6 across LES+URANS, St 0.138-0.146; Trias Table 2: DNS 2.18/1.71/0.132, experiments Lee 2.05 through Luo 2.21, Norberg/Bearman&O
  * cite: Tian et al. 2013 Table 3 (fetched primary); Trias et al. 2015 Table 2 (fetched primary)
* [CONFIRMED] **Tian benchmark configuration claims: 35Hx20H domain (+/-10H lateral = 5% blockage), dt* 0.004, inlet I=2% (Lyn's rig), l=0.07H with <0.27% sensitivity**
  * repo: radius_ratio 20 = 'Tian's 5% blockage' — wind_transient.py:283-285 and openfoam_wind_ras.py:39-40; fixed_dt_star=0.004 'Tian's step' — openfoam_wind_ras.py:127 and docstring :55; 'I = 2 %, l = 0.07 d 
  * source: 'The size of the whole computational domain is 35H by 20H' (lateral +/-10H -> H/20H = 5% blockage, recomputed); 'turbulence intensity I=2% (Lyn et al., 1995)'; 'turbulence length l = 0.07H'; 'a much lower value (l=0.04H)
  * cite: Tian et al. 2013, section 2.2 + Table (fetched primary PDF); Lyn rig parameters independently on ERCOFTAC case043: free-stream turbulence 2%, blockage 7%, aspect ratio 9.75
* [CORROBORATED] **Flat square-cylinder Cd curve: 'Norberg ~2.1 at 38k; Fage & Johansen ~2.05 at 150k'**
  * repo: tests/validation/openfoam_wind_ras.py:9; also wind.py:93-94, :251, :297
  * source: Tian primary text: Fig. 6 compares CD with 'the experimental results (Norberg, 1993; Fage and Johansen, 1927)' and states R=1 results 'agree well'; Trias Table 2 lists Norberg at Re 22e3 with Cd 2.1
  * cite: Tian et al. 2013 (fetched primary — but the specific digits are read off its Fig. 6, a graph, per the repo's own de-risk doc); Trias et al. 2015 Table 2 (fetched)

### Cylinder-flow benchmarks
*C. H. K. Williamson St(Re) relation; Qu, Norberg, Davidson, Peng & Wang (2013); Braza, Chassaing & Ha Minh, JFM 165 (1986) via published comparison tables*

* [CORROBORATED] **Williamson laminar St(Re) correlation constants: St = -3.3265/Re + 0.1816 + 1.6e-4*Re**
  * repo: constants at tests/validation/wind_transient.py:17 and :91 (williamson_st), tests/validation/openfoam_wind_transient.py:13, emstudio/solvers/openfoam/wind.py:42
  * source: 'St = A/Re + B + C Re ... where A= -3.3265, B = 0.1816 and C = 1.6 x 10-4', least-squares fit for Re 50-180 (Beaudan & Moin, Stanford Report TF-62, 1994, eq. 1); same constants quoted in the search-indexed abstract summa
  * cite: Stanford University Report TF-62: https://web.stanford.edu/group/tfsa/TF_reports/TF-062_Beaudon.pdf (fetched, text extracted). Primary is Williamson, Phys. Fluids 31(10):2742 (1988), doi 10.1063/1.866
* [CONFIRMED] **Williamson correlation evaluated: St 0.1643 at Re 100, 0.1834 at Re 150**
  * repo: 'gives 0.1643 at Re 100 and 0.1834 at Re 150' — tests/validation/wind_transient.py:18; openfoam_wind_transient.py:13-14; wind.py:42-43
  * source: -3.3265/100 + 0.1816 + 1.6e-4*100 = 0.164335; -3.3265/150 + 0.1816 + 1.6e-4*150 = 0.1834233
  * cite: Recomputed by hand from the corroborated constants; independently, Stanford TF-62 states the equation gives 0.164 at Re 100, and Qu, Norberg, Davidson, Peng & Wang (2013, Chalmers-hosted PDF) measure 
* [CORROBORATED] **Re-100 circular-cylinder published Cd: 'Park 1.33' and 'Liu 1.35', cluster ~1.32-1.37, gate range 1.30-1.40**
  * repo: openfoam_wind_transient.py:17 and :83-84; wind_transient.py:19-20; WIND_ANCHORS cd_range (1.30, 1.40) at wind_transient.py:83
  * source: Qu et al. (2013) Table 1 (Re 100): Park et al. (1998) CD 1.33, St 0.165; full cluster 1.318-1.336 over 8 comparable-domain studies; arXiv 2205.15886: 'Park et al. [38] got it as 1.33'; Wolf Dynamics tutorial table: Liu e
  * cite: Qu, Norberg, Davidson, Peng & Wang, 'Quantitative numerical analysis of flow past a circular cylinder at Reynolds number between 50 and 200': https://www.tfd.chalmers.se/~lada/postscript_files/lixia_p
* [UNVERIFIABLE] **Re-100 'Braza 1.364' specifically**
  * repo: 'Braza 1.364' — openfoam_wind_transient.py:17; wind_transient.py:20
  * source: The one fetched table quoting Braza et al. (1986) at Re 100 gives 1.386 +/- 0.015 (Wolf Dynamics tutorial); no fetched document this session carries 1.364 attributed to Braza
  * cite: Braza, Chassaing & Ha Minh, JFM 165:79-130 (1986) is paywalled; searched arXiv comparison tables (2205.15886, 2303.09262, 1609.04364, 2210.00148, 1109.3524, 1506.01320), Wolf Dynamics, semanticscholar
* [CORROBORATED] **Re-100 lift amplitude ~0.32-0.34, gate window 0.28-0.38**
  * repo: openfoam_wind_transient.py:18-19 and :85-86; wind_transient.py:21 and clamp_range (0.28, 0.38) at wind_transient.py:83
  * source: Qu et al. (2013): CL'(rms) 0.225 (present D9) and 0.235 (Park) at Re 100 -> sinusoid amplitude ~0.318-0.332; Wolf Dynamics table: cl +/- 0.339 (Liu), +/- 0.333 (Guerrero), +/- 0.25 (Braza)
  * cite: Qu et al. 2013 Tables 1 and 3 (fetched); Wolf Dynamics tut_2D_cylinder.pdf (fetched)
* [CORROBORATED] **WIND_ANCHORS Re-150 row: cd_range (1.26, 1.40); lift amplitude ~0.52, clamp_range (0.44, 0.60)**
  * repo: wind_transient.py:84-85 (row), :78-80 ('~0.33 at Re 100, ~0.52 at Re 150'); fixture Cd 1.3283 / St 0.1835 / clamp 0.5202 are repo-measured record values
  * source: Qu et al. (2013) Table 3, Re 150 (two domain sizes): CD 1.301 and 1.305; CL'(rms) 0.3529 and 0.3546 -> amplitude ~0.499-0.501; St 0.1837 and 0.1841
  * cite: Qu, Norberg, Davidson, Peng & Wang 2013, Chalmers-hosted PDF (fetched)

### Betts & Bokhari / ERCOFTAC 079
*P. L. Betts, I. H. Bokhari, Int. J. Heat Fluid Flow 21 (2000) tall-cavity experiment — ERCOFTAC Classic Collection case 079; digitised profiles verified against the copies shipped inside ESI OpenFOAM v2512*

* [CONFIRMED] **citation: Betts & Bokhari (2000), 'Experiments on turbulent natural convection in an enclosed tall cavity', IJHFF 21(6)**
  * repo: Betts & Bokhari (2000), IJHFF 21(6) — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py:6-8
  * source: Crossref publisher-deposited metadata for DOI 10.1016/S0142-727X(00)00033-3: P.L. Betts, I.H. Bokhari, 'Experiments on turbulent natural convection in an enclosed tall cavity', International Journal of Heat and Fluid Flo
  * cite: api.crossref.org/works/10.1016/S0142-727X(00)00033-3; corroborated by ERCOFTAC Classic Collection case 079 references list (cfd.mace.manchester.ac.uk, 'Vol. 21, pp. 675-683') and by the ESI tutorial R
* [CONFIRMED] **cavity width x height: 0.076 m x 2.18 m**
  * repo: W_M, H_M = 0.076, 2.18 — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py:55 (also docstring line 7)
  * source: 'a tall differentially heated rectangular cavity (2.18 m high by 0.076 m wide by 0.52 m in depth)' — ERCOFTAC Classic Collection case 079 description, cfd.mace.manchester.ac.uk/ercoftac/doku.php?id=cases:case079 (fetched
  * cite: ERCOFTAC Classic Collection case 079; independently the ESI vendor blockMeshDict (/usr/lib/openfoam/openfoam2512/.../buoyantCavity/system/blockMeshDict:17-27) meshes 76 x 2180 mm at scale 0.001
* [CONFIRMED] **0.52 m depth chosen so the midplane is near-2-D (docstring justification for 2-D RANS at z=0)**
  * repo: 'B&B chose the 0.52 m depth to make the midplane near-2-D' — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py:17-19
  * source: '0.52 m in depth' and 'The temperature and flow fields were found to be closely two-dimensional, except close to the front and back walls'; measurements are 'on the mid-span plane (where 2-dimensionality of the flow is g
  * cite: ERCOFTAC Classic Collection case 079, Description + Available Measurements sections; vendor blockMeshDict z runs -260..+260 mm = 0.52 m
* [CONFIRMED] **Ra = 8.6e5, the lower (19.6 K) of the two cases**
  * repo: RA = 8.6e5 ('the data files' own header') — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py:57; '(the lower, 19.6 K case)' docstring line 8
  * source: 'temperature differentials between the vertical plates of 19.6 and 39.9 C, giving Rayleigh numbers based on the cavity width of 0.86e6 and 1.43e6'; section heading 'Lower Rayleigh Number: Ra = 8.6 x 10^5' — ERCOFTAC case
  * cite: ERCOFTAC Classic Collection case 079; /usr/lib/openfoam/openfoam2512/.../buoyantCavity/validation/exptData/*.dat headers; ESI README: 'the lower of the two plate temperature differences, 19.6 degC'
* [CONFIRMED] **wall temperatures T_HOT = 307.75 K / T_COLD = 288.15 K (34.6 / 15.0 degC), attributed to 'the tutorial's own'**
  * repo: T_HOT, T_COLD = 307.75, 288.15 — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py:56
  * source: Vendor artefact /usr/lib/openfoam/openfoam2512/.../buoyantCavity/0.orig/T: hot 'uniform 307.75; // 34.6 degC', cold 'uniform 288.15; // 15 degC' — read verbatim from the installed ESI v2512 tree
  * cite: ESI OpenFOAM v2512 installed tutorial 0.orig/T; experimental consistency from the archive data itself: mt_z0_10_lo.dat's last point (x=75.87 mm) reads exactly 34.6 degC and the cold-side first points 
* [CONFIRMED] **claim: the digitised measured profiles ship INSIDE the ESI v2512 tree beside its buoyantCavity tutorial**
  * repo: docstring lines 9-12 and _expt_dir() path tutorials/heatTransfer/buoyantSimpleFoam/buoyantCavity/validation/exptData — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.p
  * source: Verified on this machine: /usr/lib/openfoam/openfoam2512/tutorials/heatTransfer/buoyantSimpleFoam/buoyantCavity/validation/exptData exists and holds 14 files (mt/mv at y/H = 10,30,40,50,60,70,90) — a superset of the 10 f
  * cite: Local ESI v2512 install + ERCOFTAC case 079 per-file downloads (lib/exe/fetch.php?media=cdata:case079:low-ra:*.dat), diffed 2026-08-30

### Huynh thesis
*M. Huynh, M.S. thesis (Virginia Tech), PIFA ground-plane study — Table 5-1 anechoic-chamber column*

* [CONFIRMED] **GROUND_LADDER_MEAS_HZ, L=20 mm measured resonance**
  * repo: 2440e6 Hz — emstudio/antenna/pifa.py:113
  * source: 2440 MHz, Measured fr column, L=20 row
  * cite: M.-C. T. Huynh, 'A Numerical and Experimental Investigation of Planar Inverted-F Antennas for Wireless Communication Applications', M.S. thesis, Virginia Tech, Oct 19 2000, Table 5-1, pp. 73-74; offic
* [CONFIRMED] **GROUND_LADDER_MEAS_HZ, L=40 mm measured resonance**
  * repo: 1987e6 Hz — emstudio/antenna/pifa.py:114
  * source: 1987 MHz, Measured fr column, L=40 row (px 1.8, computed 2013)
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477
* [CONFIRMED] **GROUND_LADDER_MEAS_HZ, L=60 mm measured resonance**
  * repo: 1905e6 Hz — emstudio/antenna/pifa.py:115
  * source: 1905 MHz, Measured fr column, L=60 row (px 2.0, computed 1956)
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477
* [CONFIRMED] **GROUND_LADDER_MEAS_HZ, L=80 mm measured resonance (also MEASURED_HZ and published_meas_80mm_hz)**
  * repo: 1892e6 Hz — emstudio/antenna/pifa.py:116, emstudio/antenna/pifa.py:91, tests/validation/pifa_openems.py:54
  * source: 1892 MHz, Measured fr column, L=80 row (px 2.1, computed 1943)
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477; §5.3.2 prose quotes the 2.62% computed/measured gap for this row
* [CONFIRMED] **GROUND_LADDER_MEAS_HZ, L=100 mm measured resonance (also published_meas_100mm_hz)**
  * repo: 1886e6 Hz — emstudio/antenna/pifa.py:117 and emstudio/antenna/pifa.py:92
  * source: 1886 MHz, Measured fr column, L=100 row (px 2.2, computed 1928)
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477
* [CONFIRMED] **GROUND_LADDER_MEAS_HZ, L=120 mm measured resonance**
  * repo: 1899e6 Hz — emstudio/antenna/pifa.py:118
  * source: 1899 MHz, Measured fr column, L=120 row (px 2.8, computed 1950)
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477
* [CONFIRMED] **GROUND_LADDER_MEAS_HZ, L=140 mm measured resonance**
  * repo: 1942e6 Hz — emstudio/antenna/pifa.py:119
  * source: 1942 MHz, Measured fr column, L=140 row (px 3.5, computed 2015)
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477
* [CONFIRMED] **Non-monotonic measured trend with minimum at L=100 mm**
  * repo: minimum 1886 MHz at L=100, rising to 1899 (120) and 1942 (140) — emstudio/antenna/pifa.py:102-108 comment, tests/validation/pifa_openems.py:252, docs/upstream/pifa-anchors.md
  * source: Measured column falls 2440-1987-1905-1892-1886 then rises 1899, 1942; minimum is the L=100 row
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477
* [CONFIRMED] **2343 MHz at L=20 belongs to the COMPUTED (IE3D) column, not the measured one**
  * repo: 'computed 2343 MHz at L = 20' — emstudio/antenna/pifa.py:125-126; docs/upstream/pifa-anchors.md table (computed 2343 / measured 2440 at L=20)
  * source: L=20 row: Computed fr 2343 MHz, Measured fr 2440 MHz; simulator identified as IE3D (Zeland Software) in section 5.3.2
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74 and section 5.3.2, VTechWorks handle 10919/35477
* [CONFIRMED] **published_mom_hz — IE3D method-of-moments resonance on infinite ground**
  * repo: 1980e6 Hz — emstudio/antenna/pifa.py:90
  * source: 1980 MHz, Computed fr, 'infinite' ground-plane row (px 2.9)
  * cite: Huynh MS thesis, Virginia Tech 2000, Table 5-1, pp. 73-74, VTechWorks handle 10919/35477
* [CONFIRMED] **GROUND_SHIFT_MEAS_PCT — measured shift, 20 mm vs 80 mm ground**
  * repo: 28.96 — emstudio/antenna/pifa.py:131
  * source: (2440/1892 - 1) * 100 = 28.9641%, from the two confirmed measured digits above
  * cite: Derived from Huynh Table 5-1 measured column (both operands CONFIRMED primary); recomputed independently: 28.96405919661733
* [CONFIRMED] **Ladder caveats: probe re-matched per ground size, and no measured gain published**
  * repo: px runs 1.7 mm at L=20 to 3.5 mm at L=140; 'the table publishes no measured gain at all' — emstudio/antenna/pifa.py:107-109, 126-127; docs/upstream/pifa-anchors.md px column (1.7/1.8/2.0/2.1/2.2/2.8/3
  * source: px column: 1.7, 1.8, 2.0, 2.1, 2.2, 2.8, 3.5, 3.0, 3.0, 3.4, 2.9 mm, chosen 'so that the antenna is matched to 50 ohms at resonance' (section 5.3.1); Peak Gain has a Computed sub-column only
  * cite: Huynh MS thesis, Virginia Tech 2000, section 5.3.1 p. 72 and Table 5-1 pp. 73-74, VTechWorks handle 10919/35477

### TEAM Problem 7
*TEAM benchmark Problem 7 (compumag.org problem7.pdf): geometry, drive, and the measured Bz line data*

* [CORROBORATED] **17 measured Bz points, A1-B1 line, 50 Hz, wt=0 (BZ_MEAS)**
  * repo: [-0.00049, -0.001788, -0.002213, -0.002019, -0.001567, 0.000036, 0.004364, 0.007811, 0.007155, 0.006044, 0.005391, 0.005262, 0.005381, 0.005691, 0.005924, 0.005278, 0.002761] T — tests/validation/team
  * source: Identical 17 values (tesla) in ElmerCSC/elmer-elmag TEAM7/TEAM7_A1B1.csv, fetched raw from https://raw.githubusercontent.com/ElmerCSC/elmer-elmag/main/TEAM7/TEAM7_A1B1.csv 2026-08-30; machine-compared, all 17 rows exact-
  * cite: elmer-elmag TEAM7_A1B1.csv (secondary copy). True primary: K. Fujiwara & T. Nakata, 'Results for benchmark problem 7 (asymmetrical conductor with a hole)', COMPEL 9(3) 137-154, 1990, DOI 10.1108/eb010
* [CONFIRMED] **17 x positions (X_MEAS = 0.018*i, i=0..16, i.e. 0..288 mm step 18)**
  * repo: 0.018*i for i in range(17) — tests/validation/team7_elmer.py:46
  * source: Official spec Table 2(a): rows No.1-17, x(mm) = 0.0, 18.0, 36.0, ..., 288.0 (read from the scan)
  * cite: TEAM Problem 7 official definition, compumag.org/wp/wp-content/uploads/2018/06/problem7.pdf, Table 2(a), downloaded and read page-by-page 2026-08-30
* [CONFIRMED] **A1-B1 measurement line at y=72 mm, z=34 mm**
  * repo: save_lines [((0.0,0.072,0.034),(0.288,0.072,0.034),96)] — team7_elmer.py:112; docstring 'y = 72 mm, z = 34 mm' line 11
  * source: Table 2(a) header: 'Bz along the line A1-B1(y=72,z=34(mm))'; Fig.4 shows A1 at (0,72), B1 at (288,72), z=34 between plate top (19) and coil bottom (49)
  * cite: compumag problem7.pdf Table 2 caption + Fig.4, read from the scan
* [CONFIRMED] **Plate conductivity sigma = 3.526e7 S/m**
  * repo: "sigma": 3.526e7 — team7_elmer.py:90
  * source: Table 1: 'Conductivity sigma (S/m) 3.526x10^7'; Fig.1: 'aluminum (sigma=3.526x10^7 (S/m))'
  * cite: compumag problem7.pdf Table 1 + Fig.1
* [CONFIRMED] **Coil excitation 2742 ampere-turns**
  * repo: "amp_turns": -2742.0 — team7_elmer.py:100; deck check 'Desired Coil Current = Real -2742' line 137
  * source: Table 1: 'Exciting current I0 (AT) 2742'; Fig.1: 'coil (2742(AT))'. Sign: elmer-elmag TEAM7.sif/steady.sif/corr.sif/transient.sif all use 'Desired Coil Current = Real -2742' (fetched raw)
  * cite: compumag problem7.pdf Table 1 + Fig.1 (magnitude); ElmerCSC/elmer-elmag TEAM7 sif files (sign convention, secondary)
* [CONFIRMED] **Frequency 50 Hz (benchmark defines 50 and 200 Hz)**
  * repo: "f_hz": 50.0, 2 periods x 8 steps — team7_elmer.py:111; MATC 'cos(2*pi*50*t)' checked line 143
  * source: Table 1: 'Frequency f (Hz) 50, 200'
  * cite: compumag problem7.pdf Table 1
* [CONFIRMED] **Plate 294x294x19 mm with eccentric 108x108 through-hole at 18/18**
  * repo: plate origin (0,0,0) size (0.294,0.294,0.019); hole origin (0.018,0.018,-0.001) size (0.108,0.108,0.021) — team7_elmer.py:88-94
  * source: Fig.1(a): 294 x 294 plate, hole 108 x 108 offset 18 from each of the two near edges; Fig.1(b): plate thickness 19
  * cite: compumag problem7.pdf Fig.1
* [CONFIRMED] **Racetrack coil: 150x150 window, R25/R50, 25 wide x 100 tall, 30 mm above plate (z=49..149)**
  * repo: racetrack cx0/cy0 0.144/0.050, cx1/cy1 0.244/0.150, r_in 0.025, r_out 0.050, z0 0.049, z1 0.149 — team7_elmer.py:96-98
  * source: Fig.1: inner window 150 x 150, corner radii R25/R50, radial thickness 25, height 100, coil bottom 30 above plate top (19+30=49). Placement (outer envelope x=94..294, y=0..200) from elmer-elmag geo, consistent with offici
  * cite: compumag problem7.pdf Fig.1 (dimensions); elmer-elmag TEAM7.geo (absolute placement, secondary)
* [CONFIRMED] **wt=0 defined as instant of maximum exciting current (gate's step-16 = cosine-peak check)**
  * repo: cosine drive + 'last transient step is step 16 = t = 40 ms (wt = 0, the cosine peak)' — team7_elmer.py:143,171-172
  * source: Spec section 5: 'At wt=0(deg), the exciting current becomes the maximum.'
  * cite: compumag problem7.pdf, section 5 'Quantities and Distributions to be Presented'
* [CONFIRMED] **Normalization peak 7.811 mT = max|Bz_meas|**
  * repo: BZ_PEAK = max(abs(b) for b in BZ_MEAS) with comments '7.811 mT' — team7_elmer.py:13,50,196
  * source: Recomputed: max|BZ_MEAS| = 0.007811 T (the x=126 mm point) — exact
  * cite: Arithmetic over the 17-value array, verified by script
* [UNVERIFIABLE] **'2.83% RMS' figure and NORM_PINS (0.58412768 / 1.7526977e-06)**
  * repo: 'frozen from the first green run of the production writer, 2026-07-16, RMS 2.83%'; NORM_PINS — team7_elmer.py:52-54,74
  * source: No external source exists — these are self-pinned regression values of EMStudio's own deck+mesh, explicitly distinct from elmer-elmag's published Reference Norms (5.81616403E-01 / 2.15104858E-06, which I verified verbati
  * cite: elmer-elmag TEAM7.sif/steady.sif/corr.sif fetched raw 2026-08-30 for the adjacent published-norms cross-check (all four norms in docs/TEAM7_BUILD_SHEET.md B.4 match verbatim)

### Belden coax datasheets
*Belden 8240 / 9310 (RG-58, RG-142) manufacturer datasheets; twinax/foam-PE line constants*

* [CONFIRMED] **RG-58C/U Z0 = 50 ohm nominal**
  * repo: 50 ohm anchor, preset a_eff=0.418mm/b=1.4605mm/eps 2.25 — emstudio/wire/coax.py:52-57; gate |Z0-50.0|<0.15 tests/validation/cable.py:58-59
  * source: Nom. Characteristic Impedance: 50 Ohm
  * cite: Belden 8262 technical datasheet (catalog.belden.com/techdata/EN/8262_techdata.pdf, rev 0.531, 2026-02-20), Electricals table
* [CONFIRMED] **RG-58C/U velocity factor 66%**
  * repo: preset note 'VF 66%' coax.py:57; gate velocity_factor(2.25)==2/3 (66.7%) cable.py:62-63
  * source: Nom. Velocity of Prop.: 66%
  * cite: Belden 8262 technical datasheet, Electricals table
* [CONFIRMED] **RG-58C/U capacitance 101 pF/m (30.8 pF/ft)**
  * repo: '101 pF/m' anchor coax.py:48,57; gate |C'-101.0|<2.0 with comment 'Belden 30.8 pF/ft' cable.py:64-66
  * source: Nom. Capacitance Cond-to-Shield: 30.8 pF/ft (101 pF/m)
  * cite: Belden 8262 technical datasheet, Electricals table
* [CONFIRMED] **RG-58C/U attenuation 1.4 / 4.9 / 11.5 dB/100ft at 10/100/400 MHz**
  * repo: (10.0,1.4),(100.0,4.9),(400.0,11.5) dB/100ft — tests/validation/cable.py:74
  * source: 10 MHz: 1.4 dB/100ft; 100 MHz: 4.9 dB/100ft; 400 MHz: 11.5 dB/100ft
  * cite: Belden 8262 technical datasheet, Attenuation table
* [CONFIRMED] **RG-58C/U geometry: 19x33 20 AWG conductor 0.889 mm, PE dielectric dia 2.921 mm (b=1.4605 mm)**
  * repo: a_phy 0.4445e-3, b 1.4605e-3, '19x33 stranded', 'physical envelope 0.889 mm' — coax.py:47-49,53,55-56; cable.py:55
  * source: Conductor: 20 AWG 19x33, nom. diameter 0.035 in (=0.889 mm); Insulation: PE, nom. diameter 0.115 in (2.92 mm) (0.115 in = 2.921 mm)
  * cite: Belden 8262 technical datasheet, Construction Details
* [UNVERIFIABLE] **RG-58 stranded-centre effective diameter factor 0.94x (a_eff 0.418 mm)**
  * repo: 'classic ~0.94x effective diameter (0.836 mm)' coax.py:47-48,55-56; a_m 0.418e-3 coax.py:53
  * source: no primary found for the 0.94 constant itself
  * cite: none for the constant; its outputs check against Belden 8262 (50 ohm, 101 pF/m)
* [CONFIRMED] **RG-142B/U Z0 50 ohm nominal, MIL 50+/-2 window, honest geometry 48.0 ohm**
  * repo: '50 nominal... canonical geometry honestly gives 48.0 ohm — bottom of the MIL 50+/-2 window' coax.py:60-65; gate |z142-48.0|<0.2 cable.py:88-90
  * source: Belden 83242: Nom. Characteristic Impedance 50 Ohm; RG-142B/U spec sheet: CHARACTERISTIC IMPEDANCE 50 +/- 2 Ohms
  * cite: Belden 83242 techdata (catalog.belden.com/techdata/EN/83242_techdata.pdf, rev 0.515, 2026-02-20); RG 142 B/U spec data sheet, farnell.com/datasheets/1504070.pdf (Issue 2, 29/09/2011, cites MIL-C-17/15
* [CONFIRMED] **RG-142B/U velocity factor 70% (PTFE eps_r 2.04)**
  * repo: 'VF 70%', eps_r 2.04 coax.py:60,65; gate |VF-0.700|<0.001 cable.py:91-92
  * source: Belden 83242: Nom. Velocity of Prop. 70%
  * cite: Belden 83242 techdata, Electricals table
* [CONFIRMED] **RG-142B/U geometry a=0.470 mm, b=1.475 mm**
  * repo: a_m 0.470e-3, b_m 1.475e-3 — coax.py:60; cable.py:86
  * source: Belden 83242: 19 AWG solid SCCS 0.037 in (=0.9398 mm dia), PTFE 0.116 in (2.95 mm); UK sheet: conductor 01/0.940 mm, dielectric 2.95 mm
  * cite: Belden 83242 techdata Construction Details; RG 142 B/U spec sheet (farnell.com/datasheets/1504070.pdf)
* [CONFIRMED] **RG-142 attenuation 30.51 dB/100m max at 400 MHz ('Belden-UK')**
  * repo: 0.55*30.51 <= model <= 30.51, 'Belden-UK 30.5 dB/100m @ 400 MHz' — cable.py:93-95
  * source: ATTENUATION: 30.51 dB/100 Mts MAXIMUM @ 400 MHz
  * cite: RG 142 B/U specification data sheet, farnell.com/datasheets/1504070.pdf (Issue 2, 29/09/2011, ref VR1127)
* [CONFIRMED] **Cat5e preset conductor: 24 AWG solid Cu, d=0.511 mm, polyolefin**
  * repo: d_m 0.511e-3, '24 AWG solid Cu, polyolefin/HDPE' — twisted_pair.py:79-82
  * source: 24 AWG Solid, BC - Bare Copper; Insulation PO - Polyolefin
  * cite: Belden 1583A techdata (catalog.belden.com/techdata/EN/1583A_techdata.pdf) + full datasheet (datasheet.octopart.com/1583A-U1000-F6H-Belden-datasheet-57380.pdf, rev 2, 2007)
* [CONFIRMED] **Cat5e NVP 0.70 (Belden 1583A) -> eps_eff 2.04**
  * repo: nvp 0.70, 'NVP 0.70 (Belden 1583A) -> eps_eff 2.04' — twisted_pair.py:81,83-84
  * source: Nominal Velocity of Propagation: 70 %
  * cite: Belden 1583A full datasheet (octopart 57380), Electrical Characteristics; also 70% in current 1583A techdata Delay table
* [UNVERIFIABLE] **Cat5e insulated-conductor OD 0.993 mm ('Belden construction patent')**
  * repo: s_m 0.993e-3, 'insulated OD 0.993 mm (Belden construction patent)' — twisted_pair.py:80,82-83; long-lay 0.92 mm variant gated at 100.2 ohm cable.py:257-258
  * source: not found; envelope only: DuPont WO1996005601A1 'no more than about 40 mils (1.02 mm)'; Belden 1583E datasheet insulation nom. dia 0.9 mm; Amphenol Cat5e 0.039 in (~1 mm)
  * cite: patents.google.com US5606151A, US5734126A (Belden bonded-pair — ranges only, 24 AWG example spacing 0.035 in), WO1996005601A1; docs.rs-online.com Belden 1583E sheet
* [CONFIRMED] **Cat5e/Cat6 fitted impedance band 100 +/- 15 ohm (TIA/EIA-568-B.2)**
  * repo: 'TIA-568 100 +/- 15 ohm fitted band' twisted_pair.py:53,74-75; gates 85<=Z0<=115 cable.py:253-261
  * source: Fitted Impedance: 100 +/- 15 Ohms (1-100 MHz); 'Third party verified to TIA/EIA-568-B.2'
  * cite: Belden 1583A full datasheet Table 2 and Belden 2412 techdata High Frequency table (both primary); TIA-568-B condensed reproduction (csd.uoc.gr copy, secondary) agrees
* [CONFIRMED] **Cat5e mutual capacitance 49.2 pF/m at 1 kHz**
  * repo: gate 'within 15% of Belden's 49.2 (1 kHz value)' — cable.py:262-264
  * source: Nom. Mutual Capacitance @ 1 KHz: 15 pF/ft (= 49.21 pF/m)
  * cite: Belden 1583A full datasheet (octopart 57380), Electrical Characteristics
* [CONFIRMED] **Cat5e max attenuation 22.0 dB/100m at 100 MHz**
  * repo: one-sided gate 0.55*22.0 <= model <= 22.0 — cable.py:268-271
  * source: Max. Attenuation @ 100 MHz: 22.0 dB/100 m
  * cite: Belden 1583A datasheet (both editions; primary). Same 22.0 in the TIA-568-B Cat5e cable table reproduction (csd.uoc.gr) and Superior Essex Cat6 whitepaper (both secondary)
* [CONFIRMED] **Cat6 preset conductor + OD: 23 AWG (0.573 mm), diameter-over-insulated-conductor 1.029 mm (CommScope CS31CM)**
  * repo: d_m 0.573e-3, s_m 1.029e-3, 'CommScope CS31CM' — twisted_pair.py:90-93
  * source: 23 AWG; Diameter Over Insulated Conductor: 1.029 mm | 0.0405 in; Polyolefin
  * cite: CommScope CS31CM product page (commscope.com item1427254-6) — manufacturer primary; 23 AWG solid BC also on Belden 2412 techdata
* [CONFIRMED] **Cat6 NVP 0.70 (Belden 2412)**
  * repo: nvp 0.70, 'NVP 0.70 (Belden 2412)' — twisted_pair.py:91,93
  * source: Nom. Velocity of Prop.: 70%
  * cite: Belden 2412 techdata (catalog.belden.com/techdata/EN/2412_techdata.pdf), Delay table
* [CORROBORATED] **Cat6 max attenuation 19.8 dB/100m at 100 MHz**
  * repo: one-sided gate 0.55*19.8 <= model <= 19.8, 'the 19.8 dB/100m max' — cable.py:272-274
  * source: Category 6 cable insertion loss (solid) @ 100 MHz: 19.8 dB/100m
  * cite: TIA/EIA-568-B condensed reproduction (csd.uoc.gr/~hy435, Cablingdb, Cat6 cable table) and Superior Essex 'Category 6 Standards Overview' whitepaper (cdn.cableorganizer.com) — both SECONDARY reproducti
* [CONFIRMED] **120-ohm RS-485 identity: 12.8 pF/ft, VF 0.66 -> 120.3 ohm**
  * repo: gate |z0_from_c_vf(12.8 pF/ft, 0.66) - 120.3| < 0.4 — cable.py:307-309
  * source: Nom. Capacitance Cond-to-Cond 12.8 pF/ft (42.0 pF/m); Nom. Characteristic Impedance 120 Ohm; Nom. Velocity of Prop. 66%
  * cite: Belden 9842 techdata (catalog.belden.com/techdata/EN/9842_techdata.pdf), Electricals
* [UNVERIFIABLE] **120-ohm foam-PE (11 pF/ft, VF 0.78 -> 118.5) and 78-ohm twinax (19.7 pF/ft, VF 0.66 -> 78.2; sqrt(0.12uH/19.7pF)=78.0) identity anchors**
  * repo: cable.py:310-315
  * source: not sourced this session
  * cite: none fetched
* [CONFIRMED] **Churchill-Chu horizontal-cylinder all-Ra correlation: Nu = {0.60 + 0.387 [Ra/(1+(0.559/Pr)^(9/16))^(16/9)]^(1/6)}^2**
  * repo: constants 0.60, 0.387, 0.559, 9/16, 16/9, 1/6, outer square — /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/wire/thermal.py:215 (docstring) and :222-223 (code); restated in tests/validation/ther
  * source: AHTT v6.00 eq. (8.29), p. 430: Nu_D = {0.60 + 0.387 [Ra_D/(1+(0.559/Pr)^(9/16))^(16/9)]^(1/6)}^2 — byte-identical layout, page image read. Incropera 6th ed eq. (9.34), p. 580 and Cengel 2nd ed Table 9-1 eq. (9-25), p. 46
  * cite: Lienhard & Lienhard, A Heat Transfer Textbook v6.00 (2024), eq. 8.29 p. 430, author-official PDF from ahtt.mit.edu (page image); same in v5.10 (web.archive.org snapshot of ahtt.mit.edu, 2022-01-20); I

### Cat5e/Cat6 (TIA class)
*TIA-568-class Cat5e/Cat6 twisted-pair characteristics*

* [CONFIRMED] **HA_REF = 125 (charts drawn at h/a = 125)**
  * repo: HA_REF = 125.0 — emstudio/antenna/lpda.py:88
  * source: Carrel 1961 paper p.64: 'In this figure [Fig 11] Z0 equals 100 ohms and h/a equals 125'; Fig 11 caption p.70: 'h/a = 125'
  * cite: Carrel IRE Convention Record 1961, p.64 text and Fig 11 caption read visually; ARRL ch.10 Fig 4 caption ('length to diameter ratio of 125') corroborates

### Pozar
*D. M. Pozar, Microwave Engineering, 4th ed. — TE10 waveguide relations (eq. 3.22 chain)*

* [CONFIRMED] **TE10 cutoff formula fc = c/(2a)**
  * repo: fc_wr28 = 299792458.0/(2.0*7.112e-3), commented 'TE10 cutoff = c / 2a' — tests/validation/smith.py:151; same relation implied by the WR-90 gate's kc = pi/a
  * source: Pozar, Microwave Engineering, 4th ed. (Wiley 2012), sec. 3.3 'Rectangular Waveguide', p.113: eq (3.84) fc_mn = (1/2pi*sqrt(mu*eps))*sqrt((m*pi/a)^2+(n*pi/b)^2); eq (3.85) fc_10 = 1/(2a*sqrt(mu*eps)) — read from the archi
  * cite: Pozar 4e eq (3.85), p.113; archive.org scan
* [CONFIRMED] **TE10 wave impedance Z_TE = eta0/sqrt(1-(fc/f)^2), cited to Pozar sec 3.3 / eq (3.22)**
  * repo: z0_col = eta0/np.sqrt(1.0-(fc_wr28/f_ka)**2) — tests/validation/smith.py:153; docstring form Z_TE(f) = eta0/sqrt(1-(fc/f)^2) — emstudio/post/sparams.py:74; smith.py:142-145 cites 'Pozar, Microwave Eng
  * source: Pozar 4e eq (3.22): Z_TE = E_x/H_y = k*eta/beta ('which is seen to be frequency dependent'), restated for rectangular guide as eq (3.86) E_x/H_y = -E_y/H_x = k*eta/beta, where eta is the intrinsic impedance of the fill; 
  * cite: Pozar 4e eqs (3.22) and (3.86), sec 3.3; archive.org scan
* [CONFIRMED] **WR-28 inside dimensions a = 7.112 mm, b = 3.556 mm**
  * repo: WR28_A_MM = 7.112, WR28_B_MM = 3.556 — emstudio/templates/horn.py:64-65; A_MM, B_MM = 7.112, 3.556 — tests/validation/waveguide_port_openems.py:69
  * source: Pozar 4e Appendix I 'Standard Rectangular Waveguide Data': WR-28, Ka band, recommended 26.5-40.0 GHz, inside 0.280 x 0.140 in (0.711 x 0.356 cm). 0.280 in = 7.1120 mm, 0.140 in = 3.5560 mm exactly
  * cite: Pozar 4e Appendix I, p.720; archive.org scan; corroborated by everythingrf.com/tech-resources/waveguides-sizes/wr28 (7.112 x 3.556 mm) and VDI waveguide-designations PDF (7112 x 3556 um)
* [CONFIRMED] **WR-28 TE10 cutoff fc = 21.077 GHz**
  * repo: 'broad wall a = 7.112 mm, so fc = 21.077 GHz' — tests/validation/smith.py:144; computed exactly as 299792458/(2*7.112e-3) at smith.py:151
  * source: Recomputed: c/(2a) = 21.076523 GHz -> rounds to 21.077. everythingRF WR-28 page: 21.077 GHz (secondary). VDI PDF: 21.1 GHz (rounded). Pozar 4e Appendix I itself prints 21.081 GHz
  * cite: Pozar 4e eq (3.85) + Appendix I dimension; everythingrf.com/tech-resources/waveguides-sizes/wr28
* [CONFIRMED] **WR-90 inside dimensions 22.86 x 10.16 mm, X-band 8.2-12.4 GHz sweep**
  * repo: a_mm=22.86, b_mm=10.16, f1=8.0-f2=12.0 GHz — emstudio/templates/waveguide.py:14-15 (docstring line 5: '22.86 x 10.16 mm'); A_M = 22.86e-3 — tests/validation/waveguide_palace.py:29
  * source: Pozar 4e Appendix I: 'X, 8.20-12.4, 6.557, WR-90, 0.900 x 0.400 (2.286 x 1.016)' — inside 0.900 x 0.400 in = 2.286 x 1.016 cm
  * cite: Pozar 4e Appendix I, p.720; archive.org scan; also Balanis 3e Example 13.6 and Stutzman 2e Example 7-7 both state WR90 a = 0.9 in = 2.286 cm, b = 0.4 in = 1.016 cm
* [CONFIRMED] **WR-90 TE10: kc = 137.4275 1/m, fc = 6.557140 GHz, 'published 6.557'**
  * repo: 'a WR-90 face produces kc = 137.4275 1/m, i.e. a TE10 cutoff of 6.557140 GHz against the published 6.557 — 0.0021 %' — tests/validation/waveguide_port_openems.py:5-6
  * source: Recomputed: pi/0.02286 m = 137.427500 1/m; c/(2*0.02286) = 6.5571404 GHz. Pozar 4e Appendix I prints 6.557 GHz for WR-90
  * cite: Pozar 4e Appendix I (6.557 GHz) + eq (3.84) kc = sqrt((m*pi/a)^2+(n*pi/b)^2); recomputation
* [CONFIRMED] **Z_TE column across WR-28 Ka band: 621.5 ohm at 26.5 GHz, 443.3 ohm at 40 GHz, centre 487.1 ohm, factor 1.40; CHANGELOG's +40.2% -> +9.9%**
  * repo: 621.5/443.3/1.40 — emstudio/post/sparams.py:19-20; 621.5/443.3/487.1 — sparams.py:101-102; same numbers in smith.py:145-147; '+40.2 % to +9.9 %' — CHANGELOG.md:40-41
  * source: Recomputed with eta0 = 376.730313668 and fc = c/(2*7.112mm): Z_TE(26.5 GHz) = 621.5001 ohm; Z_TE(40 GHz) = 443.2543 ohm; centre point of the 51-pt 26.5-40 linspace = 487.0897 ohm; 621.5/443.25 = 1.4021 (+40.2%); 487.09/4
  * cite: Pozar eq (3.22)/(3.85) + NIST eta0, recomputed in python
* [CONFIRMED] **Coupled-patch E-plane |S21| at s=0.5 lambda0 (Jedlicka-Poe-Carver measured benchmark)**
  * repo: -24.0 dB — tests/validation/isolation_patch_openems.py:14 (gate window +/-2.5 dB at :123-124)
  * source: Kwan & Newman DTIC ADA154292 Fig 2.5: measured point -23.40 dB at s=0.509; Balanis 4e Fig 14.32 (credited reprint of Pozar 1982): measured dot -24.31 dB at s=0.498; mean -23.86 dB
  * cite: Kwan & Newman, 'Mutual Coupling Analysis for Conformal Microstrip Antennas', DTIC ADA154292, Fig 2.5 (report p.40), archive.org scan archive.org/details/DTIC_ADA154292; Balanis, Antenna Theory 4e, Fig
* [CONFIRMED] **Coupled-patch H-plane |S21| at s=0.5 lambda0**
  * repo: -33.5 dB — tests/validation/isolation_patch_openems.py:14 (gate window +/-3.5 dB at :125-126)
  * source: Kwan & Newman Fig 2.6: measured point -33.27 dB at s=0.509; Balanis 4e Fig 14.32: measured dot -33.46 dB at s=0.495; mean -33.37 dB
  * cite: Same two sources as the E-plane anchor: DTIC ADA154292 Fig 2.6 (report p.43, archive.org scan) and Balanis 4e Fig 14.32 (Pozar 1982 reprint), both machine-digitized with axis calibration.
* [CONFIRMED] **Coupled-patch geometry: L=6.55 cm, W=10.57 cm, probe 2.16 cm from radiating edge on width centerline, f~1410 MHz**
  * repo: L=65.5e-3, W=105.7e-3, FEED_X=21.6e-3, F0=1410e6 — tests/validation/isolation_patch_openems.py:40-41 (prose at :9-11)
  * source: DTIC Figs 2.5/2.6: patch 6.55 cm x 10.57 cm, feed 2.16 cm from edge (drawn as half-dims x1=3.275 cm, y1=5.285 cm, feed 1.115 cm from center = 2.16 cm from edge); text p.46: 'at 1417 MHz for the computations, and at 1410 
  * cite: DTIC ADA154292 Figs 2.5/2.6 + p.46 text (archive.org scan); Balanis 3e Fig 14.30 caption and 4e Fig 14.32 caption p.828 (archive.org scans, both crediting Pozar 1982).
* [CONFIRMED] **Coupled-patch substrate: eps_r=2.55, h=1.588 mm**
  * repo: EPS_R=2.55, H=1.588e-3 — tests/validation/isolation_patch_openems.py:41 (prose at :10 attributes these to 'the Kwan & Newman build sheet (DTIC ADA154292)')
  * source: Balanis 3e Fig 14.30 / 4e Fig 14.32 captions: h=0.1588 cm, eps_r=2.55 (source: Pozar 1982). BUT the cited Kwan & Newman report itself prints eps_r=2.5 and t=0.1575 cm in both figures
  * cite: Balanis 3e Fig 14.30 caption ('h = 0.1588 cm, e_r = 2.55, f_r = 1,410 MHz') and 4e Fig 14.32 caption p.828, archive.org scans; DTIC ADA154292 Figs 2.5/2.6 ('eps_r = 2.5, t = 0.1575 cm'), verified on t

### Nikolova L18
*N. K. Nikolova (McMaster), Lecture 18: Rectangular Horn Antennas — Balanis-derived design chain, eqs 18.24–18.51*

* [CONFIRMED] **Optimum-horn aperture efficiency eps_ap = 0.51**
  * repo: EPS_AP_OPTIMUM = 0.51 — emstudio/antenna/horn.py:40; used in G = eps*4pi*A*B/lambda^2 at horn.py:64
  * source: Stutzman & Thiele, Antenna Theory and Design 2nd ed., eq (7-146): eps_ap = 0.81 x 0.80 x 0.79 = 0.51, and eq (7-147): G = 0.51*(4pi/lambda^2)*A*B 'optimum pyramidal horn'; also (7-96) 'designed for optimum gain has an ap
  * cite: Stutzman 2e eqs (7-96), (7-146), (7-147), pp.298-313; archive.org scan (an-th-a-des-se). Corroborated by Nikolova L18 eq (18.41): eps_a = 0.81*0.632 = 0.51
* [MISMATCH] **Aspect-ratio claim: a1 ~ 1.5*b1, 'which is what the E- and H-plane optimum flare conditions imply together'**
  * repo: 'optimum-horn aspect ratio a1 ~ 1.5*b1' + derivation claim — emstudio/antenna/horn.py:99-101; baked in at horn.py:108-111 (b1 = sqrt(area/1.5), a1 = 1.5*b1); repeated in source_note horn.py:150
  * source: The optimum flare conditions imply a1/b1 = sqrt(3*lambda*rho)/sqrt(2*lambda*rho) = sqrt(1.5) = 1.225 for equal flare lengths — i.e. a1^2 = 1.5*b1^2, not a1 = 1.5*b1. Realizable textbook optimum designs land near that: Ba
  * cite: Balanis 3e sec 13.4.3 + Example 13.6 (p.781-782); Stutzman 2e Example 7-7 (p.315); Nikolova L18 eq (18.42)-(18.51) (realizability RE = RH, no fixed ratio)

### Stutzman & Thiele
*W. L. Stutzman, G. A. Thiele, Antenna Theory and Design, 2nd ed. — horn phase-error optima*

* [CONFIRMED] **E-plane HPBW constant 54 (theta_E = 54*lambda/b1 degrees)**
  * repo: K_E_DEG = 54.0 — emstudio/antenna/horn.py:46; used as K_E*lam/b1 at horn.py:80
  * source: Stutzman 2e eq (7-138): HP_E = 2*sin^-1(0.47*lambda/B) ~ 0.94*lambda/B rad = 54*lambda/B deg, 'optimum', derived 'from the s = 1/4 plot in Fig. 7-16'. (The scan's OCR garbles the printed digits — fragments '47', '0.9:', 
  * cite: Stutzman 2e eq (7-138), p.310; archive.org scan; Example 7-7 p.315
* [CONFIRMED] **H-plane HPBW constant 78 (theta_H = 78*lambda/a1 degrees)**
  * repo: K_H_DEG = 78.0 — emstudio/antenna/horn.py:47; used as K_H*lam/a1 at horn.py:80
  * source: Stutzman 2e eq (7-124): 'HP_H = 1.36 [rad] lambda/A = 78 [deg] lambda/A, optimum' — from the t = 3/8 pattern's 3-dB point (A/lambda)*sin(theta) = 0.68. Clean in the scan: 'HP, = 1.36 ... 78 ... optimum (7-124)'
  * cite: Stutzman 2e eq (7-124), p.305; archive.org scan
* [CONFIRMED] **Gain-beamwidth estimate G ~ 26000/(theta_E*theta_H)**
  * repo: 10*log10(26000.0/(hpbw_e_deg*hpbw_h_deg)) — emstudio/antenna/horn.py:93; described as 'the standard aperture approximation' horn.py:25,86
  * source: Stutzman 2e eq (7-95): G ~ 26,000/(HP_E*HP_H) (degrees), presented as the practical-antenna variant of the idealized 41,253/(HP*HP) of (7-94); applied to a pyramidal horn on p.316: G = 26,000/((12.4)(14.2)) = 21.7 dB vs 
  * cite: Stutzman 2e eq (7-95), pp.298-299 and 316; archive.org scan
* [MISMATCH] **Docstring claim: optimum phase error 's = 1/8 in the E-plane, 3/8 in the H-plane'**
  * repo: '(s = 1/8 in the E-plane, 3/8 in the H-plane)' — emstudio/antenna/horn.py:17
  * source: Stutzman 2e eq (7-144) context: 'The aperture efficiencies for optimum sectoral horns with s = 0.25 and t = 0.375'; design Step 4 (p.314): 'see if s = 0.25 and t = 0.375'; Nikolova L18: E-plane optimum at q = 1, i.e. s =
  * cite: Stutzman 2e (7-144) and p.314-315; Balanis 3e (13-19a/b); archive.org scans

### Balanis
*C. A. Balanis, Antenna Theory: Analysis and Design, 3rd/4th ed. — horn ch. 13 (incl. the author’s published design code) and LPDA Fig 11.13, measured from the PDF’s embedded vector geometry*

* [CONFIRMED] **Optimum H-plane flare relation a1 = sqrt(3*lambda*rho_h)**
  * repo: rho_h = a1**2/(3.0*lam) with comment 'Optimum flare: a1 = sqrt(3*lambda*rho_h)' — emstudio/antenna/horn.py:113-114; source_note horn.py:150-151
  * source: Balanis, Antenna Theory 3rd ed. (2005), eq (13-41c): a1 ~ sqrt(3*lambda*p2), and design eq (13-58a): a1 = sqrt(3*lambda*p2) ~ sqrt(3*lambda*ph). Stutzman 2e eq (18.24 equivalent): A = sqrt(3*lambda*R0) at t = 3/8
  * cite: Balanis 3e eqs (13-41c), (13-58a), sec 13.4.3, pp.766-781; archive.org scan (AntennaTheoryAnalysisAndDesign3rdEd)
* [CONFIRMED] **Optimum E-plane flare relation b1 = sqrt(2*lambda*rho_e)**
  * repo: rho_e = b1**2/(2.0*lam) with comment 'b1 = sqrt(2*lambda*rho_e)' — emstudio/antenna/horn.py:113,115; source_note horn.py:151
  * source: Balanis 3e eq (13-19a): b1 ~ sqrt(2*lambda*p1), and design eq (13-58b): b1 = sqrt(2*lambda*p1) ~ sqrt(2*lambda*pe). Nikolova L18 eq (18.37): optimum at q = B/sqrt(2*lambda*R0E) = 1
  * cite: Balanis 3e eqs (13-19a), (13-58b); archive.org scan
* [CORROBORATED] **Chu minimum-Q formula Q = 1/(ka)^3 + 1/(ka)**
  * repo: Q = 1/ka**3 + 1/ka at emstudio/antenna/small_antenna.py:43 (docstring :35); gate pins Q=10.0 at ka=0.5, tests/validation/small_antenna.py:53-57; UI plots the same form, emstudio/ui/small_antenna_dialo
  * source: Q_Chu = 1/(ka)^3 + 1/(ka), ka << 1 (single TM10/TE10 mode) — Kim, Breinbjerg & Yaghjian, 'Electrically small magnetic dipole antennas with quality factors approaching the Chu lower bound', arXiv:0911.3822 (published IEEE
  * cite: arXiv:0911.3822 eq (1); MIT RLE Technical Report 64 (Chu, 1948), dspace.mit.edu/handle/1721.1/4984; Balanis, Antenna Theory 3rd ed. eq (11-35), archive.org scan
* [CONFIRMED] **Short dipole Rr = 20*pi^2*(L/lambda)^2 (triangular current)**
  * repo: 20.0*pi**2*(L/lam)**2 at emstudio/antenna/small_antenna.py:70 (docstring :64); gate expects 1.9739 ohm at L=lambda/10, tests/validation/small_antenna.py:35-39
  * source: Rr = 2Prad/|I0|^2 = 20*pi^2*(l/lambda)^2 — 'one-fourth of that obtained for the infinitesimal dipole as given by (4-19)'
  * cite: Balanis, Antenna Theory: Analysis and Design, 3rd ed., eq (4-37), p.165, full scan at ia800501.us.archive.org (AntennaTheoryAnalysisAndDesign3rdEd)
* [CONFIRMED] **Short-dipole effective length le = L/2**
  * repo: le = L/2.0 at emstudio/antenna/small_antenna.py:71; gate tests/validation/small_antenna.py:40-41
  * source: le = -a_theta*(l/2)*sin(theta); maximum l/2 — 'the effective length ... is only half (50%) of its physical length' for the small dipole (l < lambda/10) with triangular current
  * cite: Balanis 3rd ed., Section 2.15 / Example 2.14 (pp. 88-89), same archive.org scan
* [CONFIRMED] **Short monopole Rr = 40*pi^2*(h/lambda)^2, he = h/2**
  * repo: 40.0*pi**2*(h/lam)**2 at emstudio/antenna/small_antenna.py:139, he=h/2 at :140; gate expects 3.9478 ohm and exactly 2x the dipole Rr, tests/validation/small_antenna.py:43-51
  * source: Z(monopole) = (1/2) Z(dipole of twice the length) — Balanis eq (4-106) states the halving and 'the same procedure can be followed for any other length'; combined with (4-37): (1/2)*20*pi^2*(2h/lambda)^2 = 40*pi^2*(h/lamb
  * cite: Balanis 3rd ed., eq (4-106) p.192-193 plus eq (4-37), archive.org scan
* [CONFIRMED] **Small loop Rr = 31171 * N^2 * (A/lambda^2)^2 and he = 2*pi*N*A/lambda**
  * repo: 31171.0*N**2*(A/lam**2)**2 at emstudio/antenna/small_antenna.py:98, he = 2*pi*N*A/lam at :99 (docstring :92-93); gate tests/validation/small_antenna.py:75-85; same 31171 constant quoted in emstudio/so
  * source: Rr = 20*pi^2*(C/lambda)^4*N^2 ~= 31,171*N^2*S^2/lambda^4 (S = area; 'the last form holds for loops of other configurations'); N^2 scaling shown in worked example (0.788 ohm single turn -> 0.788*8^2 = 50.43 ohm for 8 turn
  * cite: Balanis 3rd ed., eqs (5-24) and (5-24a) p. ~238 and Example 5.x p.241, archive.org scan; loop he cross-derived from Terman, Radio Engineers' Handbook (1943), eq (39) p.813 (loop field e = 120*pi^2*N*A
* [CONFIRMED] **Radiation efficiency eta = Rr/(Rr + Rloss)**
  * repo: r_rad/(r_rad+r_loss) at emstudio/antenna/small_antenna.py:55-58; gate 4/(4+4)=0.5 at tests/validation/small_antenna.py:60-61
  * source: e_cd = Rr/(Rr + RL) — 'the ratio of the power delivered to the radiation resistance Rr to the power delivered to Rr and RL'; worked example e_cd = 0.788/(0.788+1.053)
  * cite: Balanis 3rd ed., eq (2-90) p.86 and loop example p.241, archive.org scan
* [CONFIRMED] **Voltage-limited radiated power coefficient 640*pi^4/c0^2 (printed 6.95e-13) — Watt eq 2.1.10a lineage**
  * repo: pr_coeff = 640.0*pi**4/C0**2 at emstudio/antenna/small_antenna.py:204 (docstring :173-175); gate requires exact 640*pi^4/c0^2 AND within 1% of 6.95e-13, tests/validation/small_antenna.py:265-267
  * source: Pr = (2*pi*f*C*V)^2 * Rr with Rr = 160*pi^2*(he/lambda)^2 => coefficient = 640*pi^4/c0^2 = 6.9365e-13 (recomputed); printed book value 6.95e-13 is that with rounding (+0.19%)
  * cite: Algebraic recomputation on top of the Balanis-confirmed primitives above; Watt, VLF Radio Engineering (Pergamon 1967) print value not independently locatable on the open web
* [CONFIRMED] **Rr = 160*pi^2*(he/lambda)^2 for a monopole in terms of effective height, plus the two anonymized measured (he, f, Rr) pairs**
  * repo: docstring form at emstudio/antenna/small_antenna.py:173; gate identity check tests/validation/small_antenna.py:271-277 and measured pairs (83 m, 15.79 kc/s, 0.030 ohm), (96 m, 18.0 kc/s, 0.0524 ohm) a
  * source: Identical to the confirmed 40*pi^2*(h/lambda)^2 with he = h/2, and to the uniform-current monopole by image theory; secondary literature states the same as Rr = 1580*(He/lambda)^2
  * cite: Recomputation from Balanis primitives; engineering-form corroboration in secondary sources (e.g., W8JI radiation-resistance note quoting Rr = 1580(He/lambda)^2)
* [CONFIRMED] **Effective height from measured field: he = 1e7 * E * d / (4*pi*I*f) (Watt eq 2.1.8b)**
  * repo: 1.0e7*e*d/(4.0*pi*i*f) at emstudio/antenna/small_antenna.py:277 (docstring :269-274); gate exact-inversion check tests/validation/small_antenna.py:314-318
  * source: From Balanis eq (4-26a) infinitesimal-dipole far field E_theta = j*eta*k*I0*l/(4*pi*r)*sin(theta), doubled by the ground image: E = 120*pi*I*he/(lambda*d) = 4*pi*1e-7*f*I*he/d at c = 3e8 => he = 1e7*E*d/(4*pi*I*f) exactl
  * cite: Balanis 3rd ed. eq (4-26a) (quoted verbatim in Problem 2.61 of the archive.org scan) plus image theory; the 1e7 constant absorbs the engineering rounding c = 3e8 m/s
* [CORROBORATED] **Efficiency ladder eta_a = Rr/Ra, eta_as = Rr/(Ra+Ri), eta_ts = Rr/(Ra+Ri+Rt); Q(eta=1) = Xc/Rr, b = f/Q (Watt section 2.1.12)**
  * repo: emstudio/antenna/small_antenna.py:252-254 (ladder), :258-260 (Q and b floor pair); gate identity and ordering checks tests/validation/small_antenna.py:300-313
  * source: Base definition eta = Rr/(Rr+Rloss) is Balanis eq (2-90) (confirmed above); Q = X/R and b = f/Q are elementary series-RLC relations; the specific three-rung Rr+Rsd+Rc+Rg / +Ri / +Rt bookkeeping is Watt's
  * cite: Balanis 3rd ed. eq (2-90) for the base definition; ladder decomposition per Watt 1967 section 2.1.12 (repo page-image verified, not independently found)
* [CONFIRMED] **Wheeler 1947 / radiansphere relations**
  * repo: Not present: zero grep hits for 'wheeler', 'radiansphere', or 'mclean' anywhere in emstudio/ or tests/; the electrically-small thresholds used are L/lambda < 0.1 (small_antenna.py:84,159) and ka < 0.1
  * source: Balanis 3rd ed. uses the same conventions: 'small dipole of length l < lambda/10' (Example 2.14) and loops 'electrically small (C < lambda/10)' (chapter 5 opening) — the loop ka < 0.1 is identically C < 0.1*lambda since 
  * cite: Balanis 3rd ed., Example 2.14 and section 5.1, archive.org scan; Balanis ch. 11 confirms Wheeler's 1947/1959 papers as historical lineage only
* [CONFIRMED] **sigma_opt = 0.243*tau - 0.051 (optimum-spacing design line)**
  * repo: 0.243*tau - 0.051 — emstudio/antenna/lpda.py:94
  * source: ARRL Antenna Book 21st ed. ch.10 Eq 8: 'sigma_opt = 0.243*tau - 0.051' (open mirror scan qrz.ru/schemes/contribute/arrl/chap10.pdf); line drawn on the corrected Carrel chart
  * cite: Cebik/ARRL Antenna Book 21st ed. (2007) ch.10 Eq 8; overlay-verified on Balanis 3e Fig 11.13 (p.631) and the official Wiley 4e companion ch11.pptx chart
* [CONFIRMED] **cot(alpha) = 4*sigma/(1-tau)**
  * repo: 4.0*sigma/(1.0-tau) — emstudio/antenna/lpda.py:218
  * source: Carrel 1961 IRE paper eq (24): tan alpha = (1-tau)/(4*sigma), printed p.65; thesis Table 4: sigma = (1/4)(1-tau)cot(alpha)
  * cite: R. Carrel, 'The Design of Log-Periodic Dipole Antennas', IRE Intl. Convention Record vol.9 (1961) pp.61-75, eq (24) p.65 (hamwaves.com scan, page read visually); Carrel thesis (archive.org AnalysisAnd
* [CONFIRMED] **B_ar = 1.1 + 7.7*(1-tau)^2*cot(alpha)**
  * repo: 1.1 + 7.7*(1.0-tau)**2*cot_alpha — emstudio/antenna/lpda.py:220
  * source: Carrel thesis eq (64) p.69: B_ar = 1.1 + 30.7*sigma*(1-tau) [= 7.675*(1-tau)^2*cot(a)]; Carrel's own Figure 80 caption p.149: 'B_ar = 1.1 + 7.7(1-tau)^2 cot(alpha)'; Balanis 3e eq (11-29); ARRL Eq 13
  * cite: Carrel thesis (AD0264558 scan via archive.org), eq 64 read visually on p.69, Fig 80 caption read visually on p.149; Balanis 3e p.632; ARRL ch.10 Eq 13
* [CONFIRMED] **B_s = B*B_ar and N = 1 + ln(B_s)/ln(1/tau)**
  * repo: b_s = B*b_ar; n_exact = 1 + log(b_s)/log(1/tau) — emstudio/antenna/lpda.py:221-222
  * source: Carrel 1961 paper eq (25): B_s = B*B_ar and eq (27): N = 1 + log(B_s)/log(1/tau), printed p.65
  * cite: Carrel IRE Convention Record 1961, eqs (25),(27), p.65 read visually; Balanis 3e eqs (11-30),(11-32); thesis Table 4
* [CONFIRMED] **Boom length L = (lambda_max/4)*(1 - 1/B_s)*cot(alpha), with l1 = lambda_max/2**
  * repo: boom_carrel = (lam_max/4)*(1 - 1/b_s)*cot_alpha — emstudio/antenna/lpda.py:244; l1 = lam_max/2 at :238
  * source: Carrel 1961 paper eq (26): L/lambda_max = (1/4)(1 - 1/B_s)cot(alpha), and 'the length of the first element is always made equal to lambda_max/2' — both printed p.65
  * cite: Carrel IRE Convention Record 1961, eq (26) and adjacent text, p.65 read visually; Balanis 3e eqs (11-31),(11-31a)
* [CONFIRMED] **Za = 120*(ln(h/a) - 2.25)**
  * repo: 120.0*(log(h_over_a) - 2.25) — emstudio/antenna/lpda.py:261
  * source: Carrel 1961 paper eqs (23) and (28): Za = 120(ln h/a - 2.25), printed p.65 (appears twice); thesis Table 4
  * cite: Carrel IRE Convention Record 1961, eqs (23)/(28), p.65 read visually; Balanis 3e eq (11-33); ARRL ch.10
* [CONFIRMED] **BT_DERATE_DB = 1.0 (Butson-Thompson corrected labels = Carrel original - 1.0 dB)**
  * repo: BT_DERATE_DB = 1.0 — emstudio/antenna/lpda.py:55 (applied :186,:200)
  * source: Balanis 3e Fig 11.13 note (p.631): initial curves '1-2 dB too high... They have been reduced by an average of 1 dB (see P.C. Butson and G.T. Thompson...)'; body text: cause is a sin(theta)-vs-1/sin(theta) error in Carrel
  * cite: Balanis, Antenna Theory 3e (2005) sec.11.4.3 + Fig 11.13 note, read in full from the .edu-hosted copy; Carrel 1961 Fig 11 (p.70) label set read visually; corroborated by Lazaridis et al. 2016 Radio Sc
* [CONFIRMED] **GAIN_TABLE: corrected dBi -> tau on the optimum line (9 rows, 7.0->0.780 ... 11.0->0.967)**
  * repo: [(7.0,0.780),(7.5,0.822),(8.0,0.865),(8.5,0.897),(9.0,0.919),(9.5,0.931),(10.0,0.944),(10.5,0.955),(11.0,0.967)] — emstudio/antenna/lpda.py:63-73
  * source: Pixel-measured crossings of each contour with the printed Optimum-sigma line on the corrected chart: 7.0->0.7790, 7.5->0.8227, 8.0->0.8651, 8.5->0.8956, 9.0->0.9173, 9.5->0.9297, 10.0->0.9440, 10.5->0.9560, 11.0->0.9677 
  * cite: Balanis 3e Fig 11.13 (p.631, 300-dpi render of the .edu-hosted PDF) and the official Wiley 4e companion ch11.pptx Fig 11.13 slide — two independent printings, measured identically; the 8.0->0.865 row 
* [MISMATCH] **SIGMA006_TABLE: corrected-contour crossings at sigma = 0.06 (5 rows)**
  * repo: [(6.5,0.852),(7.0,0.887),(7.5,0.920),(8.0,0.939),(8.5,0.957)] — emstudio/antenna/lpda.py:78-84
  * source: Pixel-measured crossings at sigma=0.06 on the corrected chart (Balanis 3e print AND official 4e ch11.pptx, identical): 6.5->0.8486, 7.0->0.8848, 7.5->0.9105, 8.0->0.9355, 8.5->0.9565 (curve end; row scans at sigma 0.065/
  * cite: Balanis Fig 11.13, both printings, 300-dpi pixel measurement with clean-row cross-checks at sigma 0.065/0.070/0.075; consistency check: ARRL ch.10 worked example reads its (original-calibration) chart
* [CONFIRMED] **Chart validity: gains 6.5-11 dBi, TAU_MIN/TAU_MAX = 0.76/0.98, SIGMA_MIN = 0.04**
  * repo: TAU_MIN,TAU_MAX = 0.76,0.98; SIGMA_MIN = 0.04 — emstudio/antenna/lpda.py:47-48
  * source: Corrected chart contour label set: 6.5,7,7.5,8,8.5,9,9.5,10,10.5,11 dB (extracted as vector text from the Balanis figure); Carrel original Fig 11 tau axis runs .98-.76, sigma axis .04-.21 (read visually); Balanis axes ta
  * cite: Balanis 3e Fig 11.13 (axis/label text extracted from the PDF page itself); Carrel 1961 Fig 11 p.70 read visually; Carrel p.64: 'For values of sigma less than .05 the directivity falls off rapidly'
* [CONFIRMED] **Worked-example chain (54-216 MHz classic): cot(a) 4.68, B_ar 1.757, B_s 7.03, N_exact 14.44, boom 5.5-5.6 m; printed chain alpha 12.13deg, B_ar 1.753, B_s 7.01,**
  * repo: docstring emstudio/antenna/lpda.py:29-33; gated in tests/validation/element_designer.py:553-624 (values at :566-611)
  * source: Balanis 3e Example 11.1 (pp.634-635), read in full: sigma=0.157/tau=0.865 for 8 dB; alpha=12.13deg; B_ar=1.753; B_s=7.01; N=14.43 '(14 or 15 elements)'; lambda_max=5.556 m (c=3e8); L=5.541 m; l/d=145.816; Za=327.88 ohm; 
  * cite: Balanis, Antenna Theory 3e, Example 11.1, .edu-hosted copy (jontalle.web.engr.illinois.edu), full solution text read; independent recomputation from the primary-confirmed formulas
* [CONFIRMED] **N rounding rule: fractional part > ~0.3 rounds up**
  * repo: n = int(n_exact) + (1 if frac > 0.3 else 0) — emstudio/antenna/lpda.py:226
  * source: ARRL Antenna Book ch.10: 'If the fractional value is significant, more than about 0.3, increase the value to the next higher integral number' (chapter text near its Eq 14)
  * cite: ARRL Antenna Book 21st ed. ch.10 (open mirror scan); Stroobandt hamwaves.com/lpda states the same rule; Balanis prints '(14 or 15 elements)' leaving the choice open
* [CORROBORATED] **De Vito-Stracca: correction optimism grows to ~2 dB at the high-gain corner (>= 9.5 dBi warning)**
  * repo: comment at emstudio/antenna/lpda.py:53-54 and warning at :126-130
  * source: Balanis 3e: the error 'is variable and leads to 1-2 dB higher directivities' (the 1 dB reduction being an average); De Vito & Stracca papers verified as citations only: IEEE TAP 21(3):303-308 (1973) doi:10.1109/TAP.1973.
  * cite: Balanis 3e sec.11.4.3 (fetched); Stroobandt reference list (fetched) for the exact De Vito-Stracca bibliographic data
* [CONFIRMED] **DBD_OFFSET = 2.15 dB (dBi -> dBd)**
  * repo: DBD_OFFSET = 2.15 — emstudio/antenna/lpda.py:43
  * source: 10*log10(1.641) = 2.151 dB (half-wave dipole directivity); ARRL Fig 4 caption uses 2.14 dB for the same conversion
  * cite: Standard closed form, recomputed; ARRL ch.10 Fig 4 caption (fetched) quotes 2.14
* [CONFIRMED] **Half-wave dipole exact thin-wire impedance 73.08 + j42.52 ohm, D0=1.643, 2.15 dBi**
  * repo: emstudio/antenna/wire_elements.py:23-25 ('Balanis ch. 4: exact thin lambda/2 dipole Z = 73.08 + j42.52'), :30 (gain 2.15 dBi, D = 1.643), :52-53 (DIPOLE_GAIN_DBI = 2.15)
  * source: Recomputed from the induced-EMF closed form with exact eta0=376.7303 ohm: R=73.079, X=42.515 ohm; D0 exact = 1.6409 (2.151 dB). Balanis 4e prints eq (4-93) Zin = 73 + j42.5, eq (4-91) D0 = 1.643 = 2.156 dB (via Cin(2pi) 
  * cite: Balanis, Antenna Theory 4e, eqs (4-90), (4-91), (4-93) (archive.org scan, lines verified in the book text); my recomputation with scipy sici: Cin(2pi)=2.43766, R=eta/(2pi)*[gamma+ln(pi)-Ci(pi)-0.5(gam
* [CONFIRMED] **Dipole NEC2 reference run: f_res 296.29 MHz, R 71.9 ohm, 2.13 dBi**
  * repo: tests/validation/dipole_nec2.py:46 (reference run 2026-07-05, nec2c 1.3.1) and :60-63 (2.13 dBi probe); quoted again at emstudio/antenna/wire_elements.py:38 and emstudio/setup/solvers.py:1242
  * source: No external source exists — these are the repo's own solver outputs. The literature envelope they are gated against is confirmed: resonant-length R sits below the exact 73.08 (shortening to X=0 lowers R toward the 68-72 
  * cite: Envelope check against the recomputed exact values above and Balanis 4e ch.4; the specific digits 296.29/71.9/2.13 are repo-measured, not published anywhere.
* [CONFIRMED] **Monopole-over-ground relations: short-monopole Rr = 40 pi^2 (h/lambda)^2 (=3.948 ohm at h=lambda/10) and lambda/4 monopole Zin ~ 36.5 + j21 ohm over PEC**
  * repo: tests/validation/monopole_nec2.py:8-12 (both relations), :46 (rr_analytic = 40*pi^2*0.1^2), :72-77 (gate 33-43 ohm / +5..+32 ohm); emstudio/antenna/wire_elements.py:25 ('36.5 + j21.25 class'), :55 (MO
  * source: Watt, VLF Radio Engineering (1967), eq (2.1.5): Rr = 160 pi^2 (h_e/lambda)^2 for h_e < 0.1 lambda; with h_e = h/2 (triangular current) this is 40 pi^2 (h/lambda)^2 = 3.9478 ohm at h=0.1 lambda. Balanis 4e eq (4-106): Zin
  * cite: A.D. Watt, VLF Radio Engineering, Pergamon 1967, eq (2.1.5) — read from the project's local PDF ('/home/ajenkins/PycharmProjects/EMStudioPro/Dr_Watt_document.pub_vlf-radio-engineering-14 2.pdf'); Bala

### Churchill correlations
*S. W. Churchill & H. H. S. Chu, IJHMT 18 (1975) cylinder correlation; Churchill sphere correlation (HEDH/Schlünder 1987; Incropera eq. 9.35 form)*

* [CONFIRMED] **Repo citation claim 'AHTT eq. 8.29 = Cengel 9-25' for the cylinder correlation**
  * repo: thermal.py:45 ('Churchill-Chu (AHTT eq. 8.29 = Cengel 9-25)') and thermal.py:216
  * source: AHTT v6.00 eq. (8.29) p. 430 and Cengel 2nd ed Table 9-1 eq. (9-25) p. 468 are both the Churchill-Chu cylinder correlation with identical constants (16/9-inside vs 8/27-outside layouts, algebraically equal); Cengel Ex 9-
  * cite: AHTT v6.00 p. 430 (ahtt.mit.edu PDF, page image); Cengel 2nd ed. p. 468 Table 9-1 + p. 470 Ex 9-1 (archive.org item HeatAndMassTransferByCengel2ndEdition, page image + djvu text)
* [CONFIRMED] **Claimed 'Churchill-Chu printed range Ra 1e-6..1e12' (warned outside)**
  * repo: thermal.py:32 ('printed range is Ra 1e-6..1e12'), :216-217, and the warning text at :403-404
  * source: No single seen source prints '1e-6..1e12' as one range. AHTT v5.10 AND v6.00 print for eq. 8.29 only '10^-6 <= Ra_D' (lower bound, NO upper bound — v5.10 checked specifically because the repo used v5-era values). Cengel 
  * cite: AHTT v6.00 p. 431 page image + AHTT v5.10 p. 431 (web.archive.org copy); Cengel 2nd ed Table 9-1 p. 468 page image; Incropera 6th ed p. 580 page image; ht.readthedocs.io conv_free_immersed (secondary)
* [CONFIRMED] **Churchill sphere correlation: Nu = 2 + 0.589 Ra^(1/4)/[1+(0.469/Pr)^(9/16)]^(4/9), Ra_D <= 1e11, Pr >= 0.7**
  * repo: constants 2, 0.589, 0.469, 9/16, 4/9 — /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/solvers/openfoam/solid.py:317+321; tests/validation/openfoam_solid.py:86-91 (with 'Ra_D <= 1e11, Pr >= 0.7');
  * source: Incropera 6th ed eq. (9.35), p. 583 (page image): Nu_D = 2 + 0.589 Ra_D^(1/4)/[1+(0.469/Pr)^(9/16)]^(4/9), 'due to Churchill [10]... Pr >= 0.7 and Ra_D <= 10^11'; Cengel 2nd ed Table 9-1 eq. (9-26), p. 468 (page image): 
  * cite: Incropera 6th ed p. 583 (archive.org scan, page image; its ref [10] = Churchill, 'Free Convection Around Immersed Bodies,' Heat Exchanger Design Handbook §2.5.7, Begell House 2002); Cengel 2nd ed p. 4
* [MISMATCH] **Repo's sphere attribution 'AHTT eq. 8.33 form' next to the 0.469 constant**
  * repo: '(AHTT eq. 8.33 form), Ra_D <= 1e11, Pr >= 0.7 ... (0.469/Pr)' — tests/validation/openfoam_solid.py:86-87 and openfoam_ras_solid.py:59
  * source: AHTT eq. (8.33) actually prints Nu_D = 2 + 0.589 Ra_D^(1/4)/[1+(0.492/Pr)^(9/16)]^(4/9) with 'Ra_D < 10^12' — constant 0.492, not 0.469; no Pr restriction stated — in BOTH v5.10 (p. 456 area, wayback copy) and v6.00 (p. 
  * cite: AHTT v6.00 eq. 8.33 p. 433 (ahtt.mit.edu PDF, page image read) and AHTT v5.10 (web.archive.org copy of ahtt.mit.edu); vs Incropera 6th ed eq. 9.35 / Cengel 2nd ed eq. 9-26 which print the repo's 0.469
* [CORROBORATED] **Morgan power-law cross-check bands: Nu = C·Ra^n with (1e-2..1e2: 1.02, 0.148), (1e2..1e4: 0.850, 0.188), (1e4..1e7: 0.480, 0.250)**
  * repo: morgan = ((1e-2,1e2,1.02,0.148),(1e2,1e4,0.850,0.188),(1e4,1e7,0.480,0.250)) — tests/validation/thermal.py:160-161 (used as a ±25% oracle on Churchill-Chu at :159-169)
  * source: Incropera 6th ed Table 9.1 p. 580 (page image), 'Constants of Equation 9.33 ... [20]=Morgan': 1e-2–1e2: C 1.02 n 0.148; 1e2–1e4: 0.850, 0.188; 1e4–1e7: 0.480, 0.250 (outer bands 0.675/0.058 and 0.125/0.333 unused by the 
  * cite: Incropera 6th ed Table 9.1 p. 580 (archive.org scan, page image); Cieslinski, Smolen & Sawicka, 'Free Convection Heat Transfer from Horizontal Cylinders', Energies 2021, 14, 559, doi:10.3390/en1403055

### Incropera / Cengel
*F. P. Incropera et al., Fundamentals of Heat and Mass Transfer (Table 9.1); Y. A. Cengel, Heat Transfer, 2nd ed. worked examples; Cieslinski et al. sphere data*

* [CONFIRMED] **Cengel Ex 9-1 gate values: film props (k 0.02699, nu 1.749e-5, Pr 0.7241 at Tf 318 K), Ra 1.869e6, Nu 17.40, h 5.869 W/m2K, Q_conv 443 W, Q_rad(eps=1) 553 W**
  * repo: props_cengel = (0.02699, 1.749e-5, 1.749e-5/0.7241, 0.7241); asserts Ra 1.869e6, Nu 17.40, h 5.869, Q_conv 442.6±2, Q_rad 553.3±1 — tests/validation/thermal.py:118-135
  * source: Cengel 2nd ed Example 9-1 'Heat Loss from Hot Water Pipes' (pp. 470-471): 8-cm pipe, 6 m, 70/20°C, Tf 45°C; printed k = 0.02699 W/m·°C, nu = 1.749e-5 m2/s, Pr = 0.7241; Ra = 1.869e6; 'from Eq. 9-25' Nu = 17.40; h = 5.869
  * cite: Cengel, Heat Transfer: A Practical Approach, 2nd ed., Example 9-1 pp. 470-471 (archive.org item HeatAndMassTransferByCengel2ndEdition, djvu full text — every digit visible)

### AHTT (Lienhard)
*J. H. Lienhard IV & V, A Heat Transfer Textbook, 6th ed. — air property table A.6; eq. 8.33 page image read for the citation correction*

* [CONFIRMED] **AHTT Ex 8.4 gate values: film props (k 0.0297, nu 2.073e-5, alpha 2.93e-5, Pr 0.707 at Tf 350 K), CC bracket 0.9265, 1-g h 13.84 W/m2K**
  * repo: props_ahtt = (0.0297, 2.073e-5, 2.93e-5, 0.707); asserts h 13.841±0.1 and bracket 0.9265±5e-3 — tests/validation/thermal.py:137-146
  * source: AHTT v6.00 Example 8.4, p. 431 (page image): 5 mm wire, 127/27°C, Tf 350 K, nu 2.073e-5, alpha 2.93e-5, k 0.0297 (in the h column), Pr 0.707; Ra_D = 576.2·(g-level); underbrace beneath 0.387[576.2/(1+(0.559/0.707)^(9/16)
  * cite: Lienhard & Lienhard, AHTT v6.00 (2024), Example 8.4 p. 431, author-official ahtt.mit.edu PDF, page image read; v5.10 prints the same example (wayback copy)

### Yaghjian & Best
*A. D. Yaghjian, S. R. Best, “Impedance, Bandwidth, and Q of Antennas” (IEEE TAP 2005 / DTIC ADA418158)*

* [CONFIRMED] **Matched-VSWR fractional bandwidth FBW = (S-1)/(Q*sqrt(S))**
  * repo: (s-1)/(q*sqrt(s)) at emstudio/antenna/small_antenna.py:52; gate checks 0.0707 at Q=10, S=2, tests/validation/small_antenna.py:58-59
  * source: FBW_V(w0) = 4*sqrt(beta)*R0/(w0|Z0'|) with sqrt(beta) = (sigma-1)/(2*sqrt(sigma)) [boxed eq (7)] and Q(w0) ~= 2*sqrt(beta)/FBW_V(w0) [boxed eq (18)] => FBW_V = (sigma-1)/(sqrt(sigma)*Q)
  * cite: Yaghjian & Best, 'Impedance, Bandwidth, and Q of Antennas', AFRL Hanscom, DTIC accession ADA418158 (2003 IEEE APS version of IEEE Trans. AP vol 53 no 4, 2005), eqs (4),(7),(18) read from page images o

### NUWC TR (Rivera & Casey)
*Rivera & Casey, NUWC-NPT Technical Report — tubular monopole capacitance formulas*

* [CORROBORATED] **Monopole static capacitance C = 2*pi*eps0*h / (ln(2h/a) - 1)**
  * repo: 2.0*pi*EPS0*h/(log(2h/a)-1) at emstudio/antenna/small_antenna.py:125 (docstring :117-119 calls it 'an engineering estimate'; radiated quantities do not depend on it); gate only requires the resulting 
  * source: Grover's formula C = 2*pi*eps0*l / (ln(2/D) - gamma), D = d/l (d = tube DIAMETER); at the on-ground-plane limit gamma -> 1, i.e. C = 2*pi*eps0*h/(ln(2h/d) - 1)
  * cite: Rivera & Casey, 'Approximate Capacitance Formulas for Electrically Small Tubular Monopole Antennas', NUWC-NPT Technical Report 10,817 (1995), DTIC accession ADA302235, eqs (6)-(7) read from the page i

### Carrel / Butson-Thompson
*R. L. Carrel (1961) LPDA design method; P. C. Butson & G. T. Thompson, IEEE Trans. AP-24 (1976) 1 dB gain correction*

* [CONFIRMED] **sigma' = sigma/sqrt(tau) and feeder design form Z0 = R0*t + R0*sqrt(t^2+1), t = R0/(8*sigma'*Za)**
  * repo: sigma_prime = sigma/sqrt(tau); feeder_z0 = r0*t + r0*sqrt(t*t+1) — emstudio/antenna/lpda.py:262,266-267
  * source: Carrel 1961 paper eq (22): sigma' = sigma/sqrt(tau); eq (29): Z0/R0 = 1/(8 sigma' Za/R0) + sqrt[1/(8 sigma' Za/R0)^2 + 1]; eq (21) analysis form R0 = Z0/sqrt(1+Z0/(4 sigma' Za)) — all printed p.65
  * cite: Carrel IRE Convention Record 1961, eqs (21),(22),(29), p.65 read visually; thesis Table 4 (p.146) same forms
* [CONFIRMED] **HA_SLOPE = -0.2 dB per doubling of h/a, valid 50 < h/a < 10000**
  * repo: HA_SLOPE_DB_PER_DOUBLING = -0.2 — emstudio/antenna/lpda.py:89; range check 50..10000 at :280
  * source: Carrel 1961 paper sec.7: 'for each doubling of h/a... the directivity decreases by about 0.2 db in the range 50 < h/a < 10000'
  * cite: Carrel IRE Convention Record 1961 p.64 (OCR text, context verified); ARRL ch.10 Fig 4 caption repeats it verbatim ('0.2 dB... in the range 50 to 10000')
* [CONFIRMED] **Terminating stub: short at <= lambda_max/8 behind element 1, optional**
  * repo: documented in warnings/anchors doc; engine ships no stub — emstudio/antenna/lpda.py:337-341 warnings; docs/upstream/lpda-carrel-anchors.md:115-116
  * source: Carrel 1961 paper p.65: 'the feeder termination ZT is a short circuit a distance of lambda_max/8 or less behind element number one. In several cases a short circuit at the terminals of element number one yielded satisfac
  * cite: Carrel IRE Convention Record 1961 p.65 read visually; thesis sec.4.2.2 adds the rationale (ZT stays inductive at the lowest frequencies)

### ITU-R Recommendations
*ITU-R P.452-18, P.1546-6, P.1812-8, P.2001 — Recommendation texts and the official SG3 validation sets, via the OFCOM (Stevanovic) reference implementations*

* [CONFIRMED] **Trias, Gorobets & Oliva (2015) DNS at Re 22,000: Cd 2.18, St 0.132, Cl,rms 1.71**
  * repo: 'Cd 2.18, St 0.132, Cl,rms 1.71 (secondary-confirmed digits; not load-bearing)' — tests/validation/openfoam_wind_ras.py:17-18
  * source: Table 2: 'DNS 22 0.132 2.18 0.205 1.71 1.04'; body text: 'The averaged drag value, <CD> = 2.18', 'CLrms = 1.71', spectra peak 'located at 0.132'
  * cite: Author-accepted manuscript in UPC's official institutional repository (UPCommons): https://upcommons.upc.edu/server/api/core/bitstreams/80e2fadd-9adb-4778-9e8a-a06d1e4531c9/content (Computers & Fluids
* [CONFIRMED] **E = 300*sqrt(P_kW)/d_km mV/m (equivalently Pr = E^2*d^2/90) for a short vertical monopole**
  * repo: gate consistency check 300^2*1e-6/90*1e6 == 1000 W at tests/validation/small_antenna.py:319-322
  * source: 'the radiating element is a short vertical monopole on the surface of a perfectly conducting plane Earth that radiates 1 kW, and the field strength at a distance of 1 km is 300 mV/m, corresponding to a cymomotive force o
  * cite: Recommendation ITU-R P.368-10 (08/2022), official ITU PDF (itu.int R-REC-P.368-10-202208), condition list in section 1
* [CONFIRMED] **py452 vendored revision = ITU-R P.452-18, from eeveetza/Py452 pinned commit**
  * repo: "Recommendation ITU-R P.452-18" + commit c047331... (2025-08-19) — emstudio/vendor/py452/PROVENANCE.md:5, P452.py docstring line 40
  * source: itu.int R-REC-P.452 page: P.452-18 (10/2023) is 'In force (Main)'; upstream README at pinned commit: 'implementation of Recommendation ITU-R P.452-18'; GitHub API confirms commit exists, dated 2025-08-19T15:46:49Z
  * cite: https://www.itu.int/rec/R-REC-P.452/en; https://github.com/eeveetza/Py452 @ c047331990d35288300d0865802c98123aa21d3c
* [CONFIRMED] **P.452 wrapper validity constants: 0.1-50 GHz, time 0.001-50 %**
  * repo: 0.1 <= f <= 50.0 GHz and 0.001 <= p <= 50 % — emstudio/coverage/p452.py:27-31
  * source: P.452-18 §1: 'tested for radio stations operating in the frequency range of about 0.1 GHz to 50 GHz' and 'time percentages over the range 0.001 <= p <= 50%'
  * cite: R-REC-P.452-18-202310-I PDF downloaded from itu.int, Annex 1 §1 (pdftotext lines 337-342)
* [CONFIRMED] **p452 official validation set: 17 profiles / 595 cases, reference Lb 194.24974628**
  * repo: 595 cases asserted (tests/validation/p452.py:203), data in tests/validation/data/p452/ (test_result_flat_land_100km.csv row 1: Lb 194.24974628); TUTORIALS.md:1461-1464 quotes '595 official ITU validat
  * source: ITU's own 'Validation examples for Recommendation ITU-R P.452-18 - Ver 18.0.zip' downloaded from itu.int: all 34 repo CSVs byte-identical (34/34), 194.24974628 verbatim in ITU's file; 17 result files x 35 rows = 595 coun
  * cite: https://www.itu.int/en/ITU-R/study-groups/rsg3/... Validation examples for Recommendation ITU-R P.452-18 - Ver 18.0.zip (README dated 16.05.24, OFCOM copyright notice)
* [CONFIRMED] **TUTORIALS.md p452 gate quality claim: worst deviation 5.0e-09 dB**
  * repo: 'worst basic-transmission-loss deviation 5.0e-09 dB' — docs/TUTORIALS.md:1461-1462
  * source: Live gate run on this box: 'Lb + 8 sub-model losses match <= 1e-6 dB on every case — 0 cases over; worst 5.00e-09 dB (test_profile_flat_land_100km.csv)'
  * cite: python3 tests/validation/p452.py executed 2026-08-30 against the ITU-verified data with installed digital maps
* [CONFIRMED] **TUTORIALS.md tutorial-31 table incl. 131.78 dB (2 GHz, 50 km, smooth earth)**
  * repo: 165.67/165.67/165.68 at p=50; 142.42/137.00/131.78 at p=1; 128.07/127.05/126.30 at p=0.01 — docs/TUTORIALS.md:1438-1441; '10.64 dB at p = 1 %' at line 1446
  * source: Recomputed all 9 cells via emstudio.coverage.p452.path_loss_db with the dialog's documented defaults (linspace(0,50,51) at 0 m AMSL, htg 30 m/hrg 10 m, 51.5N -0.12E to 52.2N 0.13E, zones 2/1/3): every cell reproduces to 
  * cite: emstudio/ui/link_dialog.py:208-221 (profile construction + defaults); engine byte-verified against the WP3M reference implementation and gate-validated to 5e-09 dB
* [CONFIRMED] **py1546 vendored revision = ITU-R P.1546-6, WP3K reference implementation**
  * repo: "Recommendation ITU-R P.1546-6" + commit e235629... (2025-08-19) — emstudio/vendor/py1546/PROVENANCE.md:5
  * source: itu.int: P.1546-6 (08/2019) 'In force (Main)'; upstream README at pinned commit: 'python software implementation of Recommendation ITU-R P.1546-6 ... corresponds to the reference version of the code approved by ITU-R Wor
  * cite: https://www.itu.int/rec/R-REC-P.1546/en; https://github.com/eeveetza/Py1546 @ e235629009ab1a12a33fc4a8fb5612f2883ecb5b
* [CONFIRMED] **P.1546 wrapper validity constants: 30-4000 MHz, 1-50 %, 1-1000 km, heff <= 3000 m**
  * repo: emstudio/coverage/p1546.py:51-62
  * source: P.1546-6 Scope: '30 MHz to 4 000 MHz ... paths up to 1 000 km length for effective transmitting antenna heights less than 3 000 m'; Annex: 'not valid for field strengths exceeded for percentage times outside the range fr
  * cite: R-REC-P.1546-6-201908-I PDF downloaded from itu.int (Scope, and §time-interpolation text)
* [CONFIRMED] **p1546 official validation set: 24 profiles / 52 reference field strengths, worst 0.000000 dB**
  * repo: 24 profiles + combined_results_reference.csv (52 rows) — tests/validation/data/p1546/; gate asserts <= 0.01 dB (tests/validation/p1546.py:214); TUTORIALS.md:633 '52 datasets, all 24 official profiles,
  * source: ITU's official 'Validation examples for Recommendation ITU-R P.1546-6 - Ver 6.2' zip downloaded from itu.int: all 24 profiles byte-identical; all 52 reference AND predicted field-strength values numerically identical to 
  * cite: https://www.itu.int/en/ITU-R/study-groups/rsg3/rwp3m/Validation%20Example/R19-WP3K-C-0264!N05-P2!ZIP-E.zip (Ver 6.2, README dated 2022)
* [MISMATCH] **py1812 vendored revision label: repo says P.1812-6**
  * repo: 'the ITU-R reference implementation of Recommendation P.1812-6' — emstudio/vendor/py1812/PROVENANCE.md:4 (also emstudio/coverage/p1812.py:2,29 and tests/validation/p1812.py:2)
  * source: itu.int: P.1812-6 (09/2021) SUPERSEDED — in force is P.1812-8 (09/2025). The pinned upstream commit a5205e6 (2026-05-18) postdates upstream's 'eeveetza-p1812-8' merge (2026-02-25: Ct argument removed, Gtx/Grx added, READ
  * cite: https://www.itu.int/rec/R-REC-P.1812/en; https://github.com/eeveetza/Py1812 commit history + README @ a5205e6a65db27391a8ba79bd5a365e5391f9fdf
* [CONFIRMED] **P.1812 wrapper validity constants: 30-6000 MHz, 1-50 %, 0.25-3000 km**
  * repo: emstudio/coverage/p1812.py:30-37
  * source: P.1812-6 Scope: '30 MHz to 6 000 MHz ... 1% <= p <= 50% ... path lengths from 0.25 km up to about 3 000 km'
  * cite: R-REC-P.1812-6-202109-S PDF downloaded from itu.int (Scope; §1 repeats all three)
* [CONFIRMED] **p1812 official validation set: 19 profiles / 63 datasets, worst 0.000000 dB Lb and Ep**
  * repo: gate asserts n_cases == 63 (tests/validation/p1812.py:176) over 19 profiles (line 120); TUTORIALS.md:634
  * source: All 82 repo data files (19 profiles + 63 logs) byte-identical to the pinned upstream commit; every one of the 63 Lb/Ep pairs zero-delta against ITU's own published P_1812_8.zip validation logs (ITU file b2iseac_1.csv: Lb
  * cite: https://www.itu.int/en/ITU-R/study-groups/rsg3/rwp3m/Software%20Products/P_1812_8.zip (downloaded from itu.int, dated 2026-06-15)
* [MISMATCH] **p1812 data PROVENANCE wording: '64 per-dataset logs' and 'Ver 6.1 set'**
  * repo: tests/validation/data/p1812/PROVENANCE.md:4-5
  * source: 63 log files exist on disk and 63 exist at the pinned upstream commit; ITU's current published validation folder holds 64 files = 63 per-dataset logs + 1 combined_results.csv. ITU's SG3 page today lists the P.1812 valida
  * cite: local ls + GitHub tree @ a5205e6 + itu.int P_1812_8.zip listing
* [CONFIRMED] **py2001 vendored revision = ITU-R P.2001-6**
  * repo: 'Recommendation ITU-R P.2001-6' + commit a4d61a0... (2025-11-21) — emstudio/vendor/py2001/PROVENANCE.md:5; P2001.py header 'Modified on Fri 21 Nov 2025 to update the version number (IS) to ITU-R P.200
  * source: itu.int: P.2001-6 (09/2025) 'In force (Main)'; pinned upstream commit exists with message 'P.2001 ver6.0' (2025-11-21T16:47:17Z); upstream README at pin: 'Recommendation ITU-R P.2001-6'; ITU SG3 page lists P.2001 softwar
  * cite: https://www.itu.int/rec/R-REC-P.2001/en; https://github.com/eeveetza/Py2001 @ a4d61a056bad606d1147ff0c441511762ee9fb24
* [CONFIRMED] **P.2001 wrapper validity constants: 0.03-50 GHz, Tpc in (0,100), 3-1000 km**
  * repo: emstudio/coverage/p2001.py:28-35; gate also asserts Tpc=0 rejected (tests/validation/p2001.py:129-134)
  * source: P.2001-6 §1.1: 'Frequency: 30 MHz to 50 GHz'; 'most accurate from about 3 km to 1 000 km'; time percentage 'in the range 0% to 100%', internally limited 0.00001-99.99999%. The strict exclusivity (0,100) is the reference 
  * cite: R-REC-P.2001-6-202509-I PDF downloaded from itu.int (§1.1 'range of applicability')
* [CONFIRMED] **p2001 official validation set: 2 x 2215 = 4430 cases; worst 1.17e-12 dB; wrapper 101.263441 vs 101.2634406454913**
  * repo: tests/validation/p2001.py:100 asserts 4430; TUTORIALS.md:1501-1503 quotes '4,430 official ITU validation cases (worst deviation 1.17e-12 dB)' and '101.263441 dB vs the official 101.2634406454913'
  * source: Repo data (gunzipped) byte-identical to the pinned Py2001 commit (sha256 match both results files, both profiles); against ITU's own P_2001_6.zip examples (itu.int, dated 2026-02-24): final Lb identical on all 4430 rows 
  * cite: https://www.itu.int/en/ITU-R/study-groups/rsg3/rwp3m/Software%20Products/P_2001_6.zip
* [CONFIRMED] **TUTORIALS tutorial-32 P.2001 figures: 165.67 dB both engines at p=50; sea-inland -23.06 dB at 1 %, -13.92 dB at 0.01 %**
  * repo: docs/TUTORIALS.md:1489-1491
  * source: Recomputed via emstudio.coverage.p2001.path_loss_db (same 50 km smooth-earth run, zones 4/3/1): p=50 gives 165.67 for all three zones (P.452 run gives 165.67-165.68 — the cross-engine agreement claim holds); sea-inland =
  * cite: engines byte-verified against the WP3M reference implementations and gate-validated against ITU data the same session
* [CONFIRMED] **Radio-zone code claim: 'P.452 numbers them 1 coastal / 2 inland / 3 sea, P.2001 uses 1 sea / 3 coastal / 4 inland'**
  * repo: docs/TUTORIALS.md:1451-1453; emstudio/ui/link_dialog.py:178-181 _ZONE_CODES {p452: Inland 2/Coastal 1/Sea 3; p2001: Inland 4/Coastal 3/Sea 1}
  * source: ITU's own P.452-18 validation profile header (byte-verified from the itu.int zip): 'zone: 1=Coastal Land/2=Inland/3=Sea'; official P.2001 profiles use zone values {1,3,4} with the reference implementation defining '1 = S
  * cite: itu.int P.452-18 Ver 18.0 zip profile CSVs; R-REC-P.452-18 Table 2; R-REC-P.2001-6 Table D.1; reference-implementation docstrings

### openEMS project
*The openEMS project’s published patch and inverted-F examples — geometry and resonance anchors*

* [CONFIRMED] **Patch tutorial geometry: 32x40 mm patch, 60x60x1.524 mm epsR 3.38 substrate, feed at x=-6 mm, 50-ohm lumped port, MUR x6, 1-3 GHz / 401-point sweep**
  * repo: 32 x 40 mm patch, 60 x 60 x 1.524 mm, epsR 3.38, feed -6 mm — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/patch_openems.py:4-6 and /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/t
  * source: patch_width=32, patch_length=40, substrate_width=60, substrate_length=60, substrate_thickness=1.524, substrate_epsR=3.38, feed_pos=-6, feed_R=50, BC ['MUR']x6, f=np.linspace(max(1e9,f0-fc),f0+fc,401) with f0=2e9, fc=1e9 
  * cite: raw.githubusercontent.com/thliebig/openEMS/master/python/Tutorials/Simple_Patch_Antenna.py ((c) 2015-2023 Thorsten Liebig), fetched 2026-08-30; same values shown verbatim on https://docs.openems.de/py
* [CONFIRMED] **Patch resonance 'near 2.4 GHz' is the openEMS project's own published result**
  * repo: 'produces an S11 dip near 2.4 GHz' + gate window 2.30-2.50 GHz — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/patch_openems.py:6,66; 'reproducing the openEMS tutorial's published ~2.4 G
  * source: Published far-field figure titled 'Frequency: 2.43 GHz'; published S11 figure shows a single dip at ~2.43 GHz reaching approx -27 dB (read off the project's own generated plots)
  * cite: https://docs.openems.de/_images/Simp_Patch_Pattern.png and https://docs.openems.de/_images/Simp_Patch_S11.png, the figures embedded in https://docs.openems.de/python/openEMS/Tutorials/Simple_Patch_Ant
* [CONFIRMED] **-29 dB patch S11 depth is EMStudio's own measurement, NOT an openEMS-published figure (the case the audit caught)**
  * repo: 'S11 dip of about -29 dB at 2.435 GHz' — docs/USER_MANUAL.md:101, with the caveat 'our own measurement, not a published figure' at USER_MANUAL.md:1450 and README.md:208-210; PROJECT_MEMORY.md:42-44 re
  * source: openEMS's own published S11 figure bottoms at approx -26.8 dB (visual read; no dB depth is stated in text anywhere in the tutorial code, docs page, or wiki)
  * cite: https://docs.openems.de/_images/Simp_Patch_S11.png (published figure); tutorial code and https://docs.openems.de/python/openEMS/Tutorials/Simple_Patch_Antenna.html text checked — no textual S11 depth
* [CONFIRMED] **IFA published reference geometry, all 11 dimensions (inverted_f.m)**
  * repo: board 80x80x1.5 mm, epsR 4.3, h=8, l=22.5, w1=4, w2=2.5, wf=1, fp=4, e=10 (mm) — /home/ajenkins/PycharmProjects/EMStudioPro/docs/upstream/ifa-anchors.md:26-38 and emstudio/antenna/ifa.py:65-81 (REFERE
  * source: substrate.width=80; substrate.length=80; substrate.thickness=1.5; substrate.epsR=4.3; ifa.h=8; ifa.l=22.5; ifa.w1=4; ifa.w2=2.5; ifa.wf=1; ifa.fp=4; ifa.e=10
  * cite: raw.githubusercontent.com/thliebig/openEMS/master/matlab/examples/antennas/inverted_f.m ((C) 2013 Stefan Mahr), fetched 2026-08-30 — 202 lines, byte-identical (diff clean) to the local install copy at
* [CONFIRMED] **IFA reference solver setup: tan-d 1e-3 at 2.45 GHz, 50-ohm lumped port exciting [0 1 0] over a 0.5 mm gap, f0 2.5 GHz / fc 1 GHz, MUR x6, mesh lambda_min/20**
  * repo: kappa = 1e-3*2*pi*2.45e9*EPS0*epsR; 50-ohm lumped port; excitation f0 2.5 GHz, fc 1 GHz; MUR; lambda_min/20; 0.5 mm port slice — docs/upstream/ifa-anchors.md:40-44,74-78; emstudio/antenna/ifa.py:74-78
  * source: substrate.kappa = 1e-3 * 2*pi*2.45e9 * EPS0*substrate.epsR; feed.R = 50; AddLumpedPort(..., feed.R, start, stop, [0 1 0], true) spanning [0 0 0]+tl to [ifa.wf 0.5 0]+tl (a 0.5 mm y-slice, feed element starting at y=0.5);
  * cite: Same upstream inverted_f.m (thliebig/openEMS master), lines read directly: kappa/feed.R in the setup block, AddLumpedPort and SmoothMesh in the geometry/mesh block
* [CONFIRMED] **'The file publishes no expected numbers — no resonance, no S11, no gain'**
  * repo: Claim at docs/upstream/ifa-anchors.md:46-49 and docs/TUTORIALS.md:1771-1774 ('openEMS's example publishes no expected resonance, S11 or gain, only its title')
  * source: Full 202-line read of upstream inverted_f.m: no numeric expected result anywhere; the only frequency statement beyond the solver setup is the header comment 'EXAMPLE / antennas / inverted-f antenna (ifa) 2.4GHz'; the dis
  * cite: raw.githubusercontent.com/thliebig/openEMS/master/matlab/examples/antennas/inverted_f.m, whole file read; docs.openems.de checked (it hosts only Python tutorials — no IFA page exists); web search foun
* [UNVERIFIABLE] **IFA measured triple: 2.3934 GHz / -26.5 dB / 211 MHz bandwidth (2.295-2.507 GHz) and Zin ~54.7+1.4j**
  * repo: 2.3934 GHz, -26.5 dB, 211 MHz (8.83%), Zin 54.76+1.40j — docs/TUTORIALS.md:1699-1702; CHANGELOG.md:330-331; and -26.57 dB / 54.72+1.38j at docs/upstream/ifa-anchors.md:118
  * source: No primary source exists: openEMS publishes no numeric results for this example (confirmed above), and no independently published run of inverted_f.m was found on the web
  * cite: Searched: the file itself, docs.openems.de (no IFA page), the openEMS wiki, GitHub (https://github.com/thliebig/openEMS/blob/master/matlab/examples/antennas/inverted_f.m), and web searches for publish
* [CONFIRMED] **Standard-gain horn vendor gain curve: 19.70 dBi at 30 GHz (Mi-Wave 261A-20/599, WR-28 Ka band)**
  * repo: VENDOR_GAIN_DBI {26.5:18.8, 28:19.2, 30:19.7, 32:20.2, 34:20.6, 36:21.0, 38:21.3, 40:21.6} — emstudio/templates/horn.py:77-80; gate comparison at tests/validation/horn_openems.py:45 and horn.py:207
  * source: Vendor's own published chart 'Frequency vs Gain 261A-20/599' (p.4 of Mi-Wave's 261A-20 pattern/plot PDF), machine-digitized with gridline calibration: 26.5->18.80, 28.0->19.20, 30.0->19.70, 32.0->20.20, 34.0->20.60, 36.0
  * cite: https://www.miwv.com/wp-content/uploads/2024/04/261A-20dB-Pattern.pdf, page 4 'Frequency vs Gain 261A-20/599' (fetched 2026-08-30; chart digitized programmatically — gridlines at 2 GHz / 1 dB spacing 

### A. D. Watt
*A. D. Watt, VLF Radio Engineering, Pergamon 1967 — independently checkable statements only*

* [CONFIRMED] **Voltage-limited bandwidth coefficient 320*pi^3/c0^2 (printed 1.11e-13) — Watt eq 2.1.13c lineage**
  * repo: bw_coeff = 320.0*pi**3/C0**2 at emstudio/antenna/small_antenna.py:205 (docstring :176-177); gate tests/validation/small_antenna.py:268-270
  * source: b_3dB = f/Q = 2*pi*f^2*C*(Rr/eta_ts) with the confirmed Rr(he) => coefficient 320*pi^3/c0^2 = 1.10397e-13; printed 1.11e-13 (+0.55%)
  * cite: Algebraic recomputation from Q = Xc/R = 1/(2*pi*f*C*R) and the confirmed Rr form; Watt print value not independently locatable
* [CONFIRMED] **Power-bandwidth product closed form 7.71e-26 * V^2 C^3 he^4 f^8 / eta (Watt eq 2.1.13l)**
  * repo: gate compares code's p_r*b_3db against 7.71e-26 closed form within 1%, tests/validation/small_antenna.py:278-283
  * source: Exact product of the two exact coefficients = 204800*pi^7/c0^4 = 7.658e-26; 7.71e-26 equals the product of the two PRINTED rounded constants (6.95e-13 * 1.11e-13), +0.68% above exact
  * cite: Recomputation; consistent with the repo's own note that 7.71e-26 = 6.95e-13*1.11e-13 exactly (docs/upstream/watt-topload-anchors.md)

### Mi-Wave gain curve
*Mi-Wave standard-gain horn published Ka-band gain curve*

* [UNVERIFIABLE] **Horn outline-drawing dimensions: aperture 1.570 x 1.100 in, axial length 2.640 in, WR-28 feed (Mi-Wave outline drawing rev B, 9-12-18)**
  * repo: APERTURE_A_MM=39.88, APERTURE_B_MM=27.94, FLARE_LEN_MM=67.06, WR28 7.112x3.556 — emstudio/templates/horn.py:17-19, 64-68
  * source: Not found in any publicly fetchable document today. The vendor's model-specific outline PDF is not at any guessable URL (the 25 dB sibling has .../2025/09/261A-25-599-Outline.pdf; every 261A-20 outline variant tried retu
  * cite: Searched miwv.com (site search, both Ka-band product pages, wp-content upload URL probes), system.miwv.com storage, web.archive.org CDX for the product URL (www and bare, no captures), and the Series-

### NIST CODATA
*NIST CODATA 2018/2022 recommended values — c, η0, ε0, μ0*

* [CONFIRMED] **Free-space wave impedance eta0 = 376.730313668 ohm**
  * repo: eta0 = 376.730313668 — tests/validation/smith.py:150
  * source: NIST CODATA 2018 archive table: 'characteristic impedance of vacuum 376.730 313 668(57) ohm' (physics.nist.gov/cuu/Constants/ArchiveASCII/allascii_2018.txt). Current CODATA 2022 (physics.nist.gov/cgi-bin/cuu/Value?z0): 3
  * cite: NIST CODATA 2018 archive ASCII table; NIST CODATA 2022 current value page
* [CONFIRMED] **Physical constants C0, ETA0, EPS0, MU0**
  * repo: C0 = 299792458.0, ETA0 = 376.730313668, EPS0 = 8.8541878128e-12, MU0 = 1.25663706212e-6 at emstudio/antenna/small_antenna.py:23-26 (gate re-hardcodes eps0 at tests/validation/small_antenna.py:138)
  * source: NIST CODATA 2022 (fetched from physics.nist.gov): Z0 = 376.730313412(59) ohm, eps0 = 8.8541878188(14)e-12 F/m, mu0 = 1.25663706127(20)e-6 N/A^2; c is exact 299792458 m/s by SI definition
  * cite: physics.nist.gov/cgi-bin/cuu/Value?z0, ?ep0, ?mu0 (CODATA 2022 recommended values)

### ESI OpenFOAM v2512 tree
*Reference data and tutorial cases shipped inside the ESI OpenFOAM v2512 release itself, diffed against the upstream archives*

* [CONFIRMED] **mesh 35 x 150 = 'the tutorial's own in-plane resolution'**
  * repo: NX, NY = 35, 150 — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py:58 (docstring line 21)
  * source: hex (0 1 2 3 4 5 6 7) (35 150 15) simpleGrading (1 1 1) — /usr/lib/openfoam/openfoam2512/.../buoyantCavity/system/blockMeshDict:37; the tutorial's own turbulenceProperties also declares RAS kOmegaSST, the same model the 
  * cite: ESI OpenFOAM v2512 installed tutorial blockMeshDict and constant/turbulenceProperties
* [CONFIRMED] **velocity-scale systematic: writer BETA = 3.3e-3 vs real ~293 K air beta ~= 3.41e-3, '~2 %' scale difference**
  * repo: docstring lines 37-40 of /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py; the constant itself: BETA = 3.3e-3 at /home/ajenkins/PycharmProjects/EMStudioPro/emstudio/s
  * source: Ideal-gas Boussinesq expansion coefficient beta = 1/T: 1/293.15 K = 3.411e-3 K^-1, matching the docstring's 3.41e-3. Buoyant velocity scale U0 = sqrt(g*beta*dT*W) (the writer's own u_b at writer.py:269) gives sqrt(3.411/
  * cite: recomputed from beta = 1/T (ideal gas) and the writer's own velocity-scale formula
* [CONFIRMED] **Quarter-wave rule arithmetic: L_path 30.5 mm -> f_rule 2.4573 GHz; lambda0/4 at 2.45 GHz = 30.591 mm; 0.30% agreement; measured 2.3934 GHz is -2.6% off the rule**
  * repo: 30.500 mm / 2.4573 GHz / 30.591 mm / 0.30% / -2.6% — docs/upstream/ifa-anchors.md:62-69,127-128; docs/TUTORIALS.md:1712-1719; emstudio/antenna/ifa.py:27-28
  * source: Recomputed with c = 299792458 m/s (exact SI): c/(4*0.0305 m) = 2.457315 GHz; c/(2.45e9*4) = 30.5911 mm; (30.591-30.5)/30.5 = +0.2986%; (2.3934-2.4573)/2.4573 = -2.601%
  * cite: Direct recomputation from f = c/(4*L) with the geometry values confirmed against the primary source above; c is the exact SI definition

### Recomputed closed forms
*Values re-derived by direct computation from the cited formula during the sweep (checked against the named text where one exists)*

* [UNVERIFIABLE] **profile tolerances: measured worst 4.8 % (T) / 8.7 % (V), gated at 7 % / 12 % ('~1.4x headroom')**
  * repo: TOL_T_SPAN = 0.07, TOL_V_SPAN = 0.12; 'RMS 0.92 K on a 19.6 K span = 4.8 %', 'RMS 0.024 m/s on 0.28 m/s = 8.7 %' — /home/ajenkins/PycharmProjects/EMStudioPro/tests/validation/openfoam_ras_cavity.py:24
  * source: No external source exists or could exist: these are the repo's OWN 2026-08-23 solve-vs-experiment measurements, not literature values. Recomputed internally: 0.92/19.6 = 4.69 % (quoted 4.8 % — consistent with an unrounde
  * cite: internal measurement, arithmetic recomputed by this audit

---

Generated by `tools/gen_validation.py` from
`docs/validation/anchors.json` — edit the JSON, never this file.
