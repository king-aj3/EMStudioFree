# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: coupled-microstrip-patch isolation via openEMS (co-site §5).

The RELEASE-TIER coupled-antenna benchmark: two identical probe-fed rectangular
patches on one substrate/ground, separated 0.5 free-space wavelength edge to
edge, in the E-plane (offset along the resonant length) and the H-plane
(offset along the width). This is the Jedlicka-Poe-Carver measured benchmark
(IEEE Trans. AP-29, 1981; Pozar's 1982 MoM curves; reprinted in Balanis
Fig. 14.30) via the Kwan & Newman build sheet (DTIC ADA154292): L = 6.55 cm,
W = 10.57 cm, eps_r = 2.55, h = 1.588 mm, probe on the width centerline
2.16 cm from the radiating edge, f ~ 1410 MHz.

Gate anchors (mean of two digitized reproductions of the published curves at
s = 0.5 lambda0): E-plane |S21| = -24.0 dB, H-plane = -33.5 dB, with H-plane
coupling weaker than E-plane (a robust physical trend). The windows below are
set from live openEMS reference runs (achieved E -23.3, H -30.7 dB at the
simulated resonance ~1.31 GHz) AND the digitized-anchor uncertainty: E within
+-2.5 dB of the published -24.0, H within +-3.5 dB of -33.5 (weak H-plane
coupling is the mesh-sensitive case the literature also flags).

Each plane is a multi-minute FDTD solve, so this gate is on-demand only (NOT
in the fast smoke suite) and needs the openEMS venv:
  ~/opt/openEMS/venv/bin/python tests/validation/isolation_patch_openems.py
Pass: exit 0 and 'ISOLATION-PATCH-OPENEMS PASSED'.
"""
import json
import os
import subprocess
import sys
import tempfile

_DECK = r'''
import json, os, sys, tempfile
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0

PLANE = sys.argv[1]; S_FRAC = float(sys.argv[2])
F0 = 1410e6; LAM0 = C0/F0
L = 65.5e-3; W = 105.7e-3; H = 1.588e-3; EPS_R = 2.55; FEED_X = 21.6e-3
S = S_FRAC*LAM0
off = (L+S, 0.0) if PLANE == "E" else (0.0, W+S)
MS = 30e-3; MA = 60e-3
x_lo, x_hi = -MS, L+off[0]+MS
y_lo, y_hi = -MS, W+off[1]+MS
sim = os.path.join(tempfile.gettempdir(), "emstudio_iso_patch_%s_%s" % (PLANE, S_FRAC))
os.makedirs(sim, exist_ok=True)
fdtd = openEMS(NrTS=1200000, EndCriteria=1e-4)
fdtd.SetGaussExcite(F0, 500e6); fdtd.SetBoundaryCond(["PML_8"]*6)
csx = ContinuousStructure(); fdtd.SetCSX(csx)
mesh = csx.GetGrid(); mesh.SetDeltaUnit(1.0)
sub = csx.AddMaterial("sub", epsilon=EPS_R); sub.AddBox([x_lo,y_lo,0],[x_hi,y_hi,H],priority=1)
gnd = csx.AddMetal("gnd"); gnd.AddBox([x_lo,y_lo,0],[x_hi,y_hi,0],priority=10)
patch = csx.AddMetal("patch"); ports = []
for i,(dx,dy) in enumerate(((0.0,0.0), off)):
    patch.AddBox([dx,dy,H],[dx+L,dy+W,H],priority=10)
    fx,fy = dx+FEED_X, dy+W/2.0
    ports.append(fdtd.AddLumpedPort(i+1,50.0,[fx,fy,0],[fx,fy,H],"z",excite=1.0 if i==0 else 0.0,priority=20))
res_p = 2.5e-3; res_air = LAM0/40.0
xl = [x_lo-MA,x_lo,0,FEED_X,L,x_hi,x_hi+MA] + ([off[0],off[0]+FEED_X,off[0]+L] if PLANE=="E" else [])
yl = [y_lo-MA,y_lo,0,W/2.0,W,y_hi,y_hi+MA] + ([off[1],off[1]+W/2.0,off[1]+W] if PLANE=="H" else [])
mesh.AddLine("x", sorted(set(xl))); mesh.AddLine("y", sorted(set(yl)))
mesh.AddLine("z", [-MA,0,H/3.0,2*H/3.0,H,H+2e-3,H+8e-3,H+MA])
mesh.SmoothMeshLines("z", res_p, 1.3); mesh.SmoothMeshLines("all", res_air, 1.4)
fdtd.Run(sim, cleanup=True)
f = np.linspace(1200e6,1600e6,401)
for p in ports: p.CalcPort(sim,f)
s11 = ports[0].uf_ref/ports[0].uf_inc; s21 = ports[1].uf_ref/ports[0].uf_inc
i = int(np.argmin(np.abs(s11)))
print("RESULT " + json.dumps({"plane":PLANE,"f_res_hz":float(f[i]),
    "s11_db":float(20*np.log10(np.abs(s11[i]))),
    "s21_db":float(20*np.log10(np.abs(s21[i])))}))
'''


def _openems_python():
    env = os.environ.get("EMSTUDIO_OPENEMS_PYTHON")
    if env and os.path.exists(env):
        return env
    cand = os.path.expanduser("~/opt/openEMS/venv/bin/python")
    return cand if os.path.exists(cand) else sys.executable


def _run(py, deck, plane):
    out = subprocess.run([py, deck, plane, "0.5"], capture_output=True,
                         text=True, timeout=3600)
    line = next((ln for ln in out.stdout.splitlines()
                 if ln.startswith("RESULT ")), None)
    if line is None:
        print(out.stdout[-2000:])
        print(out.stderr[-2000:])
        raise SystemExit("openEMS patch deck ({0}) produced no result"
                         .format(plane))
    return json.loads(line[len("RESULT "):])


def main():
    print("EMStudio openEMS coupled-patch isolation gate (release tier)")
    py = _openems_python()
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(_DECK)
        deck = fh.name
    try:
        e = _run(py, deck, "E")
        h = _run(py, deck, "H")
    finally:
        os.unlink(deck)

    print("  E-plane: f_res {0:.0f} MHz, |S21| {1:.2f} dB (published -24.0)"
          .format(e["f_res_hz"] / 1e6, e["s21_db"]))
    print("  H-plane: f_res {0:.0f} MHz, |S21| {1:.2f} dB (published -33.5)"
          .format(h["f_res_hz"] / 1e6, h["s21_db"]))

    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print("  {0}  {1}{2}".format("ok  " if cond else "FAIL", name,
                                     " — " + detail if detail else ""))
        ok = ok and cond

    check("E-plane |S21| within 2.5 dB of the published -24.0 dB",
          abs(e["s21_db"] - (-24.0)) <= 2.5, "{0:.2f} dB".format(e["s21_db"]))
    check("H-plane |S21| within 3.5 dB of the published -33.5 dB",
          abs(h["s21_db"] - (-33.5)) <= 3.5, "{0:.2f} dB".format(h["s21_db"]))
    # the robust physical trend: H-plane coupling is markedly weaker than E-plane
    check("H-plane coupling weaker than E-plane by > 3 dB (measured trend)",
          h["s21_db"] < e["s21_db"] - 3.0,
          "gap {0:.1f} dB".format(e["s21_db"] - h["s21_db"]))
    # both patches resonate at the same (simulated) frequency
    check("both planes share the patch resonance (< 30 MHz apart)",
          abs(e["f_res_hz"] - h["f_res_hz"]) < 30e6,
          "{0:.0f} vs {1:.0f} MHz".format(e["f_res_hz"] / 1e6,
                                          h["f_res_hz"] / 1e6))

    if not ok:
        raise SystemExit("openEMS coupled-patch validation failed")
    print("ISOLATION-PATCH-OPENEMS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
