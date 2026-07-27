# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: antenna-to-antenna isolation via openEMS FDTD (co-site §5).

A second, independent solver for the co-site isolation the NEC2 gate
(``isolation_nec2.py``) already covers with the method of moments — the
cross-solver agreement is the point.

**Dipole tier (this gate).** Two parallel strip dipoles 0.5 wavelength apart,
each a 50-ohm lumped port, port 1 excited. |S21| at resonance is checked
against BOTH the printed value (Balanis eq. 8-71 mutual-impedance conversion:
−13.82 dB at 0.5 lambda for side-by-side half-wave dipoles) AND the shipped
NEC2 gate (−13.78 dB) — openEMS must land within ~1 dB of both. Runtime ~30 s;
this is a FreeCAD-free, on-demand gate (needs the openEMS venv), not part of
the fast smoke suite.

The two-patch coupled-antenna tier (Jedlicka-Poe-Carver, IEEE AP-29 1981) is a
separate release-tier gate — see ``isolation_patch_openems.py`` — because each
frequency point is a multi-minute FDTD run.

Run:  ~/opt/openEMS/venv/bin/python tests/validation/isolation_openems.py
  (or set EMSTUDIO_OPENEMS_PYTHON). Pass: exit 0 and 'ISOLATION-OPENEMS PASSED'.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The openEMS deck (built here so the gate is self-contained). Strip dipole
# arm half-length tuned so the FDTD resonance lands at 300 MHz (0.2222 lam);
# strip width = 4x the NEC2 wire radius (0.5 mm) for equal-perimeter wire.
_DECK = r'''
import json, os, tempfile
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0

F0 = 300e6
LAM = C0 / F0
HALF = 0.2222 * LAM
D = 0.5 * LAM
W = 2e-3
GAP = 6e-3
sim = os.path.join(tempfile.gettempdir(), "emstudio_iso_dipoles")
os.makedirs(sim, exist_ok=True)
fdtd = openEMS(NrTS=600000, EndCriteria=1e-4)
fdtd.SetGaussExcite(F0, F0/2.0)
fdtd.SetBoundaryCond(["PML_8"]*6)
csx = ContinuousStructure(); fdtd.SetCSX(csx)
mesh = csx.GetGrid(); mesh.SetDeltaUnit(1.0)
pec = csx.AddMetal("pec")
for xc in (0.0, D):
    pec.AddBox([xc-W/2,0,GAP/2],[xc+W/2,0,HALF],priority=10)
    pec.AddBox([xc-W/2,0,-HALF],[xc+W/2,0,-GAP/2],priority=10)
p1 = fdtd.AddLumpedPort(1,50.0,[-W/2,0,-GAP/2],[W/2,0,GAP/2],"z",excite=1.0,priority=20)
p2 = fdtd.AddLumpedPort(2,50.0,[D-W/2,0,-GAP/2],[D+W/2,0,GAP/2],"z",excite=0.0,priority=20)
res = LAM/40.0
mesh.AddLine("x",[-LAM/2,-W/2,0,W/2,D-W/2,D,D+W/2,D+LAM/2])
mesh.AddLine("y",[-LAM/2,0,LAM/2])
mesh.AddLine("z",[-LAM/2-HALF,-HALF,-GAP/2,GAP/2,HALF,HALF+LAM/2])
mesh.SmoothMeshLines("all",res,1.4)
fdtd.Run(sim, cleanup=True)
f = np.linspace(200e6,400e6,401)
p1.CalcPort(sim,f); p2.CalcPort(sim,f)
s11 = p1.uf_ref/p1.uf_inc
s21 = p2.uf_ref/p1.uf_inc
i = int(np.argmin(np.abs(s11)))
print("RESULT " + json.dumps({
    "f_res_hz": float(f[i]),
    "s11_db": float(20*np.log10(np.abs(s11[i]))),
    "s21_db": float(20*np.log10(np.abs(s21[i]))),
}))
'''


def _openems_python():
    env = os.environ.get("EMSTUDIO_OPENEMS_PYTHON")
    if env and os.path.exists(env):
        return env
    cand = os.path.expanduser("~/opt/openEMS/venv/bin/python")
    return cand if os.path.exists(cand) else sys.executable


def main():
    print("EMStudio openEMS isolation gate (dipole tier)")
    py = _openems_python()
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(_DECK)
        deck = fh.name
    try:
        out = subprocess.run([py, deck], capture_output=True, text=True,
                             timeout=600)
    finally:
        os.unlink(deck)
    line = next((ln for ln in out.stdout.splitlines()
                 if ln.startswith("RESULT ")), None)
    if line is None:
        print(out.stdout[-2000:])
        print(out.stderr[-2000:])
        raise SystemExit("openEMS dipole deck produced no result")
    r = json.loads(line[len("RESULT "):])
    f_res = r["f_res_hz"] / 1e6
    s21 = r["s21_db"]
    print("  f_res = {0:.1f} MHz, |S11| = {1:.2f} dB, |S21| = {2:.2f} dB"
          .format(f_res, r["s11_db"], s21))

    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print("  {0}  {1}{2}".format("ok  " if cond else "FAIL", name,
                                     " — " + detail if detail else ""))
        ok = ok and cond

    # resonance landed near 300 MHz (mesh/geometry sanity)
    check("strip dipole resonant near 300 MHz", 285.0 <= f_res <= 315.0,
          "{0:.1f} MHz".format(f_res))
    # |S21| vs Balanis -13.82 dB AND the shipped NEC2 gate -13.78 dB
    check("|S21| within 1.0 dB of Balanis -13.82 dB (0.5 lambda)",
          abs(s21 - (-13.82)) <= 1.0, "{0:.2f} dB".format(s21))
    check("|S21| within 1.0 dB of the NEC2 gate -13.78 dB (cross-solver)",
          abs(s21 - (-13.78)) <= 1.0, "{0:.2f} dB".format(s21))
    # ports are well matched at resonance (isolation is meaningful)
    check("driven port matched at resonance (|S11| < -10 dB)",
          r["s11_db"] < -10.0, "{0:.2f} dB".format(r["s11_db"]))

    if not ok:
        raise SystemExit("openEMS isolation validation failed")
    print("ISOLATION-OPENEMS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
