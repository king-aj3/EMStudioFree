# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: Palace can be given an OPEN domain, not just a metal box.

**Why this exists.** `docs/OUTSTANDING_SWEEP.md` recorded that nothing
radiating was gated above 2.435 GHz and read as though Palace could not
radiate. Palace was never the limitation. Every mesh EMStudio handed it tagged
the ENTIRE outer boundary ``pec_walls`` — correct and necessary for a resonant
cavity, and a closed metal box cannot have a far field by construction. The
capability was blocked by our own mesher.

Palace has supported both halves all along, and this gate pins them:

* ``Boundaries.Absorbing`` — "farfield absorbing (scattering) boundary
  conditions ... applied at farfield boundaries to minimize reflections".
* ``Boundaries.Postprocessing.FarField`` — "far-field electric field
  extraction. The boundary attributes must enclose the system and be on an
  external boundary."

Both quotes are from the INSTALLED Palace's own `config-schema.json`, not from
documentation about it.

**What is asserted, and why each:**

1. The open mesher tags ``radiation``, and does NOT tag ``pec_walls``. Those
   two mean opposite things — reflect everything versus absorb everything — so
   a mesh carrying both, or the wrong one, is not a subtle error.
2. ``RADIATION_ATTR`` differs from ``WALL_ATTR``. If they ever collide, an
   absorbing boundary and a PEC wall become the same MFEM attribute and Palace
   is handed a contradiction it cannot detect.
3. The far-field and absorbing attributes MATCH. Palace requires the far-field
   surface to enclose the system; attaching it to a different attribute than
   the one that absorbs would silently measure the wrong surface.
4. **PALACE ITSELF PARSES THE CONFIG.** `palace -dry-run` validates against the
   real schema. Everything above is our opinion of what Palace wants; this is
   Palace's own answer, and it is the only check here that cannot be wrong
   about the API.

⛳ Check 4 SKIPS when Palace is not installed rather than failing — absence of
an optional backend is not a defect, the same rule the other solver gates use.
Checks 1-3 need nothing installed and always run.

Run:  python3 tests/validation/palace_radiation.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    print("== Palace open/radiating domain ==")
    from emstudio.meshing import gmsh_box
    from emstudio.solvers.palace.writer import radiation_boundaries

    check("RADIATION_ATTR is distinct from WALL_ATTR",
          gmsh_box.RADIATION_ATTR != gmsh_box.WALL_ATTR,
          "radiation=%d wall=%d" % (gmsh_box.RADIATION_ATTR,
                                    gmsh_box.WALL_ATTR))

    tmp = tempfile.mkdtemp(prefix="palace_rad_")
    try:
        geo = gmsh_box.write_geo_open((40.0, 40.0, 40.0),
                                      os.path.join(tmp, "open.geo"),
                                      elem_mm=6.0)
        text = open(geo, encoding="utf-8").read()
        check("the open mesh tags a 'radiation' surface",
              'Physical Surface("radiation", {0})'.format(
                  gmsh_box.RADIATION_ATTR) in text)
        # ⚠ The whole point. A closed cavity mesh tags pec_walls; an open one
        # must not, or the wave is reflected back and there is no far field.
        check("the open mesh does NOT tag pec_walls",
              "pec_walls" not in text,
              "a reflecting wall in an open domain would kill the far field")

        b = radiation_boundaries(gmsh_box.RADIATION_ATTR, nsample=32,
                                 theta_phis=[(0.0, 0.0)])
        check("an Absorbing boundary is emitted", "Absorbing" in b)
        check("FarField postprocessing is emitted",
              "FarField" in b.get("Postprocessing", {}))
        check("absorbing and far-field use the SAME attribute",
              b["Absorbing"]["Attributes"]
              == b["Postprocessing"]["FarField"]["Attributes"],
              "%r vs %r" % (b["Absorbing"]["Attributes"],
                            b["Postprocessing"]["FarField"]["Attributes"]))
        # Second order is only valid for frequency-domain driven runs, which is
        # what this boundary is for; first order would be a silent downgrade.
        check("absorbing boundary is second order",
              b["Absorbing"].get("Order") == 2)

        # --- 4. Palace's own verdict --------------------------------------
        palace = shutil.which("palace") or os.path.expanduser(
            "~/opt/palace/bin/palace")
        gmsh = shutil.which("gmsh")
        if not (os.path.isfile(palace) and gmsh):
            print("  skip  palace -dry-run — palace and/or gmsh not installed")
        else:
            msh = os.path.join(tmp, "open.msh")
            subprocess.run([gmsh, "-3", "-format", "msh22", geo, "-o", msh],
                           capture_output=True, timeout=300)
            cfg = {
                "Problem": {"Type": "Driven", "Verbose": 0,
                            "Output": "postpro"},
                "Model": {"Mesh": "open.msh", "L0": 1e-3},
                "Domains": {"Materials": [
                    {"Attributes": [gmsh_box.VOLUME_ATTR],
                     "Permittivity": 1.0, "Permeability": 1.0}]},
                "Boundaries": b,
                "Solver": {"Order": 2, "Device": "CPU",
                           "Driven": {"MinFreq": 9.0, "MaxFreq": 11.0,
                                      "FreqStep": 1.0, "SaveStep": 0},
                           "Linear": {"Type": "Default", "Tol": 1e-8,
                                      "MaxIts": 500}},
            }
            cfg_path = os.path.join(tmp, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, indent=1)
            out = subprocess.run([palace, "-dry-run", "config.json"],
                                 cwd=tmp, capture_output=True, text=True,
                                 timeout=600)
            blob = (out.stdout or "") + (out.stderr or "")
            check("PALACE ITSELF parses the radiating config (-dry-run)",
                  out.returncode == 0 and "No errors detected" in blob,
                  blob.strip().splitlines()[-1][:90] if blob.strip() else
                  "rc=%d" % out.returncode)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if FAILURES:
        print("PALACE RADIATION GATE FAILED (%d)" % len(FAILURES))
        return 1
    print("PALACE RADIATION GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
