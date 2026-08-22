# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: the openEMS RECTANGULAR WAVEGUIDE PORT actually measures.

**Why this gate exists, and what the old one could not see.** v1.5.0's waveguide
port shipped anchored to one number: a WR-90 face produces kc = 137.4275 1/m,
i.e. a TE10 cutoff of 6.557140 GHz against the published 6.557 — 0.0021 %. That
is a real check and it is worth keeping, but it only proves that ``a`` and ``b``
reach ``AddRectWaveGuidePort`` in metres. **kc is computed analytically from a
and b before any field exists**, so it is true whether or not the port excites,
measures, or radiates anything at all. Two defects lived comfortably underneath
it and both reached a shipped template.

**The benchmark here is a structure with no unknowns.** A straight air-filled
WR-28 section with PEC transverse boundaries and PML on both ends is a
PERFECTLY MATCHED transmission line. There is no antenna, no discontinuity and
nothing to tune: the only physical answer is

    |S11| -> 0        (nothing to reflect from)
    P_acc / P_inc = 1 (everything offered is accepted)

so any departure is the port, not the physics. That is what makes it a usable
gate — unlike a horn, it cannot be "close enough".

⛳ **MEASURED, and this is why both checks below are here.** Driving the rig
with the values EMStudio's writer emitted before 2026-08-22:

| port span (probe plane <- source plane) | reference Z | \\|S11\\|   | P_acc/P_inc |
|---|---|---|---|
| 0.48 cells (``min(a,b)/20``) | modal      | **0.00 dB**  | **0.0004** |
| 1, 2, 4, 8, 16 cells         | 50 ohm     | **-1.6 dB**  | **0.31**   |
| 1, 2, 4, 8, 16 cells         | modal      | -45..-53 dB  | 1.0000     |

Both mis-configurations report a perfectly matched line as badly mismatched,
with a plausible-looking number and no warning. The second is where the horn's
``P_rad/P_acc = 1642 %`` came from: with the incident/reflected split wrong,
P_acc is not the accepted power, so the efficiency built on it is not an
efficiency.

⚠ **The negative controls are RUN, not described.** Checks 3 and 4 assert that
the two historical configurations still fail this rig. A gate that only asserts
the good case cannot tell you whether it would notice the bad one; these two
make the mutation proof permanent instead of a note in a commit message.

⚠ **What this gate does NOT prove.** It says nothing about radiation, about the
NF2FF transform, or about a port sitting near a flare or a bend — the rig is
uniform guide by construction. ``horn_openems`` is the radiating anchor.

SOLVER tier: it runs openEMS three times. Each run is a ~22k-cell domain and
takes about a second, which is trivial next to any other SOLVER gate, but it is
still a live solve and belongs here.

Run:  freecadcmd tests/run_gate.py tests/validation/waveguide_port_openems.py
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []

#: WR-28, the section the shipped horn is fed through.
A_MM, B_MM = 7.112, 3.556
#: Long enough that the probe plane is nowhere near either PML.
LEN_MM = 40.0
#: The horn analysis's own band, so the cell size below is the one the product
#: actually uses on the shipped waveguide template.
F1_HZ, F2_HZ = 26.5e9, 40.0e9

#: |S11| a perfectly matched line must beat. The measured value is -45 to -53 dB
#: across the band; -25 dB leaves ample room for grid dispersion while still
#: being 25 dB clear of the -1.6 dB the 50-ohm reference produced.
S11_MAX_DB = -25.0
#: P_acc/P_inc must be unity. The measured value is 1.0000 to four places; the
#: window catches the 0.31 and 0.0004 the two defects produced.
PACC_TOL = 0.02


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


_RIG = '''
import os, sys
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS

A_MM, B_MM, LEN_MM = {a!r}, {b!r}, {L!r}
MESH_RES = {res!r}
DEPTH_MM = {depth!r}
Z_REF = {zref!r}
here = os.path.dirname(os.path.abspath(__file__))

FDTD = openEMS(NrTS=30000, EndCriteria=1e-4)
FDTD.SetGaussExcite({f0!r}, {fc!r})
# PEC transverse walls + PML on both ends: a perfectly matched line, so the only
# physical answer is no reflection and unity accepted power.
FDTD.SetBoundaryCond(['PEC', 'PEC', 'PEC', 'PEC', 'PML_8', 'PML_8'])
CSX = ContinuousStructure(); FDTD.SetCSX(CSX)
mesh = CSX.GetGrid(); mesh.SetDeltaUnit(1e-3)
mesh.AddLine('x', np.linspace(-A_MM/2, A_MM/2, int(round(A_MM/MESH_RES))+1))
mesh.AddLine('y', np.linspace(-B_MM/2, B_MM/2, int(round(B_MM/MESH_RES))+1))
nz = int(round(LEN_MM/MESH_RES))+1
mesh.AddLine('z', np.linspace(0.0, LEN_MM, nz))

z0 = float(mesh.GetLines('z')[10])          # source plane, clear of the PML
port = FDTD.AddRectWaveGuidePort(1, [-A_MM/2, -B_MM/2, z0],
                                 [A_MM/2, B_MM/2, z0 + DEPTH_MM], 'z',
                                 A_MM*1e-3, B_MM*1e-3, 'TE10', excite=1.0)
FDTD.Run(here, cleanup=False, verbose=0)

f = np.linspace({f1!r}, {f2!r}, 271)
port.CalcPort(here, f, ref_impedance=Z_REF)
s11 = np.abs(port.uf_ref / port.uf_inc)
ratio = np.real(np.ravel(port.P_acc)) / np.real(np.ravel(port.P_inc))
# Report the WORST point in the band, not an average: a port that works at one
# frequency and not at another is still broken.
print('RIGRESULT %.6f %.6f' % (20*np.log10(max(s11.max(), 1e-12)),
                               ratio[np.argmax(np.abs(ratio - 1.0))]))
'''


def _run_rig(python, depth_mm, z_ref, mesh_res):
    """Solve the matched line once. Returns (worst |S11| dB, worst P_acc/P_inc)."""
    d = tempfile.mkdtemp(prefix="emstudio_wgrig_")
    try:
        deck = os.path.join(d, "rig.py")
        with open(deck, "w", encoding="utf-8") as fh:
            fh.write(_RIG.format(a=A_MM, b=B_MM, L=LEN_MM, res=mesh_res,
                                 depth=depth_mm, zref=z_ref,
                                 f0=0.5 * (F1_HZ + F2_HZ),
                                 fc=0.5 * (F2_HZ - F1_HZ),
                                 f1=F1_HZ, f2=F2_HZ))
        proc = subprocess.run([python, deck], cwd=d, capture_output=True,
                              text=True, timeout=900)
        # ⚠ Read the rig's OWN exit status, never a pipeline's — a shell
        # pipeline reports the LAST command's, which has masked a failed build
        # in this project before.
        if proc.returncode != 0:
            raise RuntimeError("rig exited {0}: {1}".format(
                proc.returncode, (proc.stderr or "")[-400:]))
        for line in proc.stdout.splitlines():
            if line.startswith("RIGRESULT"):
                _, s11, ratio = line.split()
                return float(s11), float(ratio)
        raise RuntimeError("rig produced no RIGRESULT line")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _stl_inner(path, z_mm, tol=1e-3):
    """(a, b) of the opening at plane z in a BINARY STL, in mm.

    ⚠ Parse the BINARY format. Counting ASCII "facet normal" lines in a binary
    STL once "proved" an exported solid had zero facets, and that wrong
    diagnosis reached a code comment. Check the format, then choose the reader.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    n = struct.unpack("<I", raw[80:84])[0]
    if len(raw) != 84 + 50 * n:
        raise RuntimeError("{0} is not a binary STL ({1} bytes, {2} facets)"
                           .format(os.path.basename(path), len(raw), n))
    xs, ys = [], []
    for i in range(n):
        off = 84 + 50 * i
        v = struct.unpack("<12f", raw[off:off + 48])
        for k in (3, 6, 9):
            if abs(v[k + 2] - z_mm) <= tol:
                xs.append(abs(v[k]))
                ys.append(abs(v[k + 1]))
    if not xs:
        raise RuntimeError("no facet vertices at z = {0}".format(z_mm))
    return 2.0 * min(xs), 2.0 * min(ys)


def main():
    print("== openEMS rectangular waveguide port vs a matched WR-28 line ==")

    from emstudio.setup.solvers import find_openems_python
    python = find_openems_python()
    if not python:
        print("  skip — openEMS python modules not installed")
        return 0

    from emstudio.solvers.openems import writer

    # --- 1. the shipped deck, read rather than assumed ----------------------
    try:
        import FreeCAD  # noqa: F401
    except Exception:
        print("  skip — needs freecadcmd for the deck/geometry checks")
        return 0

    from emstudio.templates import horn as horn_tpl

    workdir = tempfile.mkdtemp(prefix="emstudio_wgdeck_")
    try:
        ana = horn_tpl.makeHorn()
        solver = [o for o in ana.Group
                  if "Solver" in str(getattr(o, "EMStudioType", ""))][0]
        deck_path, _z0, _nr = writer.write_deck(ana, solver, workdir)
        deck = open(deck_path, encoding="utf-8").read()
        mesh_res = float([ln.split("=")[1] for ln in deck.splitlines()
                          if ln.startswith("mesh_res =")][0])

        # the port's span along the propagation axis, taken from the deck text
        wg_line = [ln for ln in deck.splitlines()
                   if "AddRectWaveGuidePort" in ln][0]
        body = wg_line[wg_line.index("(") + 1:]
        start = [float(v) for v in body[body.index("[") + 1:body.index("]")].split(",")]
        rest = body[body.index("]") + 1:]
        stop = [float(v) for v in rest[rest.index("[") + 1:rest.index("]")].split(",")]
        span = abs(stop[2] - start[2])
        check("the EXCITED waveguide port spans at least one mesh cell",
              span >= mesh_res - 1e-9,
              "%.4f mm = %.2f cells of %.4f mm" % (span, span / mesh_res, mesh_res))
        check("...and matches the writer's declared cell count",
              abs(span - writer._WG_PORT_CELLS * mesh_res) < 1e-6,
              "_WG_PORT_CELLS = %d" % writer._WG_PORT_CELLS)

        # the modal reference impedance must survive into the deck
        check("the waveguide port keeps its MODAL reference impedance",
              "ref_impedance=(None if _nr in _WG_PORTS" in deck,
              "not ref_impedance=50")
        check("the z0 column reports the modal impedance, not a nominal 50",
              "z0_col = np.real(np.ravel(port.ZL))" in deck)

        # the NF2FF box must not enclose the backward wave
        check("the NF2FF box drops the face behind the waveguide port",
              "directions=[1, 1, 1, 1, 0, 1]" in deck,
              "upstream Horn_Antenna.m's own convention")
        check("...and its start is clamped to the port's excitation plane",
              "_nf_start[2] = max(_nf_start[2], -15)" in deck)
        check("a non-waveguide analysis still uses openEMS's automatic box",
              "FDTD.CreateNF2FFBox()" in _patch_deck(workdir),
              "the deviation is confined to waveguide-fed models")

        # --- 2. the geometry that gets EXPORTED, not the constants ----------
        # horn_openems checks APERTURE_A_MM etc, which are module constants and
        # cannot notice a loft that builds something else. Read the solid.
        flare = os.path.join(workdir, "mat1_1.stl")
        a_mouth, b_mouth = _stl_inner(flare, horn_tpl.FLARE_LEN_MM)
        a_throat, b_throat = _stl_inner(flare, 0.0)
        check("the EXPORTED mouth is the drawing's aperture",
              abs(a_mouth - horn_tpl.APERTURE_A_MM) < 1e-3
              and abs(b_mouth - horn_tpl.APERTURE_B_MM) < 1e-3,
              "%.4f x %.4f mm vs %.2f x %.2f"
              % (a_mouth, b_mouth, horn_tpl.APERTURE_A_MM, horn_tpl.APERTURE_B_MM))
        check("the EXPORTED throat is WR-28, with no step into the feed",
              abs(a_throat - horn_tpl.WR28_A_MM) < 1e-3
              and abs(b_throat - horn_tpl.WR28_B_MM) < 1e-3,
              "%.4f x %.4f mm vs %.3f x %.3f"
              % (a_throat, b_throat, horn_tpl.WR28_A_MM, horn_tpl.WR28_B_MM))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # --- 3. the live matched line ------------------------------------------
    from emstudio.solvers.openems.writer import C0
    rig_res = C0 / F2_HZ / 1e-3 / 20.0          # lambda/20 at the band top
    depth = writer._WG_PORT_CELLS * rig_res

    print("  .... solving the matched line (3 short runs)")
    s11, ratio = _run_rig(python, depth, None, rig_res)
    check("a matched WR-28 line reflects nothing",
          s11 <= S11_MAX_DB, "worst |S11| = %.2f dB" % s11)
    check("...and accepts all the power offered to it",
          abs(ratio - 1.0) <= PACC_TOL, "worst P_acc/P_inc = %.4f" % ratio)

    # --- 4. negative controls: the two shipped mis-configurations ----------
    # These are the mutation proof, run rather than remembered. If either of
    # them starts passing, this gate has stopped measuring anything.
    bad_s11, bad_ratio = _run_rig(python, depth, 50.0, rig_res)
    check("NEGATIVE CONTROL: a 50-ohm reference still breaks the split",
          bad_s11 > S11_MAX_DB and abs(bad_ratio - 1.0) > PACC_TOL,
          "|S11| = %.2f dB, P_acc/P_inc = %.4f" % (bad_s11, bad_ratio))

    thin = min(A_MM, B_MM) / 20.0               # the pre-2026-08-22 formula
    thin_s11, thin_ratio = _run_rig(python, thin, None, rig_res)
    check("NEGATIVE CONTROL: a sub-cell port span still measures nothing",
          thin_s11 > S11_MAX_DB and abs(thin_ratio - 1.0) > PACC_TOL,
          "%.4f mm = %.2f cells -> |S11| = %.2f dB, P_acc/P_inc = %.4f"
          % (thin, thin / rig_res, thin_s11, thin_ratio))

    if FAILURES:
        print("WAVEGUIDE PORT GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("WAVEGUIDE PORT GATE PASSED")
    return 0


def _patch_deck(_unused):
    """The patch template's deck text — the control for the NF2FF change.

    Built in its own directory so the horn's files are never overwritten.
    """
    from emstudio.solvers.openems import writer
    from emstudio.templates import patch as patch_tpl

    d = tempfile.mkdtemp(prefix="emstudio_patchdeck_")
    try:
        ana = patch_tpl.makePatch()
        solver = [o for o in ana.Group
                  if "SolverOpenEMS" in str(getattr(o, "EMStudioType", ""))][0]
        path, _z0, _nr = writer.write_deck(ana, solver, d)
        return open(path, encoding="utf-8").read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
