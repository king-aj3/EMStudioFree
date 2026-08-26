# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validation gate: a RADIATING Palace domain, end to end, from our own mesher.

⭐ THE CLICK-PATH THAT WAS MISSING. Three pieces of this existed separately and
never met: EMStudio could hand Palace an absorbing boundary and a
``Postprocessing.FarField`` block (v1.5.0, gated by ``palace_radiation``); the
far-field parser could turn ``farfield-rE.csv`` into a ``FarFieldResult``
(gated by ``palace_farfield``); and nothing in between ever BUILT a radiating
Palace domain. ``gmsh_box.write_geo_dipole_open`` builds one, and this gate
runs the whole chain — our mesh, our config, Palace, our parser — and checks
the answer against textbook dipole physics.

WHAT IS ASSERTED, AND WHY EACH
------------------------------
1. **All four physical groups are non-empty.** ⚠ An empty physical group is
   silently legal in gmsh, and a mesh with an empty ``radiation`` group makes
   Palace run happily with NO absorbing boundary — a closed metal box that
   cannot radiate, reported as a successful solve. The first version of the
   mesher did exactly that: its bounding-box selector tagged zero sphere
   elements. Counting them is the only thing that catches it.
2. **Broadside is the peak and the axis is a null**, for a z-oriented dipole.
3. **The broadside directivity matches the closed form**, which is 2.151 dBi.
4. **The pattern is omnidirectional in phi at broadside** — any spread is the
   mesh, not the antenna.

⚠ This is DIRECTIVITY, not gain (see ``palace_farfield``): computable from the
pattern alone, equal to gain only for a lossless radiator, which PEC-in-vacuum
is.

⚠ Tolerances are loose on purpose. The dipole arms are deliberately coarsely
meshed — the domain is three wavelengths across and the feed gap is ~1/400 of
one, and a graded field over the whole antenna was measured to run past ten
minutes without finishing. The reference run lands **-0.33 dB** from the closed
form on 64 arm facets; asking for tighter than half a decibel here would be
gating the mesh budget, not the physics.

Needs gmsh AND Palace. Run:  python3 tests/validation/palace_dipole_farfield.py
Pass: exit 0 and 'PALACE DIPOLE FARFIELD GATE PASSED'.
"""
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: Free-space wavelength of the modelled dipole (mm) -> 74.9 MHz, the same
#: point Palace's own antenna example drives, so the two are comparable.
WAVELENGTH_MM = 4000.0
FREQ_GHZ = 0.0749

#: Closed-form directivity of an ideal half-wave dipole.
HALFWAVE_DIPOLE_DBI = 2.151

FAILURES = []


def check(name, ok, detail=""):
    print("  {0}  {1}{2}".format("ok  " if ok else "FAIL", name,
                                 " — " + detail if detail else ""))
    if not ok:
        FAILURES.append(name)


def _group_counts(msh_path):
    """{physical tag -> element count} from a msh2.2 file."""
    import re
    from collections import Counter

    txt = open(msh_path, encoding="utf-8", errors="replace").read()
    m = re.search(r"\$Elements\n(\d+)\n(.*?)\$EndElements", txt, re.S)
    if not m:
        return {}
    c = Counter()
    for line in m.group(2).split("\n"):
        f = line.split()
        if len(f) > 4:
            c[int(f[3])] += 1
    return dict(c)


def main():
    import numpy as np

    from emstudio.meshing import gmsh_box
    from emstudio.setup import solvers as solver_setup
    from emstudio.solvers.palace import parser, runner, writer

    if not solver_setup.find_backend("gmsh").found:
        raise SystemExit("gmsh is required for this gate and was not found.")
    info = solver_setup.find_backend("palace")
    if not info.found:
        raise SystemExit("Palace is required for this gate and was not found.")

    work = tempfile.mkdtemp(prefix="emstudio_dipole_ff_")
    try:
        geo = gmsh_box.write_geo_dipole_open(
            os.path.join(work, "dipole.geo"), WAVELENGTH_MM)
        msh = gmsh_box.run_gmsh(geo, os.path.join(work, "dipole.msh"))

        counts = _group_counts(msh)
        for tag, name in ((gmsh_box.VOLUME_ATTR, "interior"),
                          (gmsh_box.RADIATION_ATTR, "radiation"),
                          (gmsh_box.DIPOLE_PEC_ATTR, "pec"),
                          (gmsh_box.DIPOLE_PORT_ATTR, "port")):
            check("mesh group '{0}' (attr {1}) is NOT empty — an empty one is "
                  "silently legal and would run Palace with no absorber"
                  .format(name, tag),
                  counts.get(tag, 0) > 0, "{0} elements".format(
                      counts.get(tag, 0)))
        if FAILURES:
            print("PALACE DIPOLE FARFIELD GATE FAILED ({0})".format(
                len(FAILURES)))
            return 1

        grid = writer.farfield_grid()
        cfg = {
            "Problem": {"Type": "Driven", "Verbose": 1, "Output": "postpro"},
            "Model": {"Mesh": os.path.basename(msh), "L0": 1e-3},
            "Domains": {"Materials": [{"Attributes": [gmsh_box.VOLUME_ATTR],
                                       "Permeability": 1.0,
                                       "Permittivity": 1.0}]},
            "Boundaries": {
                "PEC": {"Attributes": [gmsh_box.DIPOLE_PEC_ATTR]},
                "Absorbing": {"Attributes": [gmsh_box.RADIATION_ATTR],
                              "Order": 2},
                "LumpedPort": [{"Index": 1,
                                "Attributes": [gmsh_box.DIPOLE_PORT_ATTR],
                                "R": 50.0, "Excitation": True,
                                "Direction": "+Z"}],
                "Postprocessing": {"FarField": {
                    "Attributes": [gmsh_box.RADIATION_ATTR], "NSample": 0,
                    "ThetaPhis": [[t, p] for t, p in grid]}},
            },
            "Solver": {"Order": 2, "Device": "CPU",
                       "Driven": {"Samples": [{"Type": "Point",
                                               "Freq": [FREQ_GHZ],
                                               "SaveStep": 0}]},
                       "Linear": {"Type": "Default", "KSPType": "GMRES",
                                  "Tol": 1e-8, "MaxIts": 200}},
        }
        cfg_path = os.path.join(work, "dipole.json")
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)

        from emstudio.solvers.base import SolverJob

        job = SolverJob(runner.palace_argv(info, os.path.basename(cfg_path)),
                        cwd=work)
        job.run_blocking(timeout=1800)

        ff_csv = os.path.join(work, "postpro", parser.FARFIELD_CSV)
        check("Palace produced a far field from OUR mesh",
              os.path.isfile(ff_csv), ff_csv)
        if not os.path.isfile(ff_csv):
            print("PALACE DIPOLE FARFIELD GATE FAILED")
            return 1

        ff = parser.parse_farfield(ff_csv)
        check("it parses into the shared FarFieldResult",
              ff.theta.size == 19 and ff.phi.size == 24
              and ff.meta.get("quantity") == "directivity",
              "{0}x{1}, {2}".format(ff.theta.size, ff.phi.size,
                                    ff.meta.get("quantity")))

        g_peak, th_peak, _ph = ff.peak()
        check("the pattern peaks at BROADSIDE for a z-oriented dipole",
              abs(th_peak - 90.0) < 1e-6,
              "theta = {0:.1f} deg, {1:+.3f} dBi".format(th_peak, g_peak))

        i90 = int(np.argmin(np.abs(ff.theta - 90.0)))
        i0 = int(np.argmin(np.abs(ff.theta - 0.0)))
        bs = ff.gain[i90]
        mean_bs = float(bs.mean())
        check("broadside directivity matches the closed form within 0.5 dB",
              abs(mean_bs - HALFWAVE_DIPOLE_DBI) < 0.5,
              "{0:+.3f} dBi vs {1:+.3f} analytic ({2:+.3f} dB)".format(
                  mean_bs, HALFWAVE_DIPOLE_DBI,
                  mean_bs - HALFWAVE_DIPOLE_DBI))
        check("there is a deep null on the dipole AXIS",
              float(ff.gain[i0].mean()) < mean_bs - 12.0,
              "{0:+.2f} dBi, {1:.1f} dB down".format(
                  float(ff.gain[i0].mean()),
                  mean_bs - float(ff.gain[i0].mean())))
        ripple = float(bs.max() - bs.min())
        check("the broadside cut is omnidirectional in phi (the spread IS the "
              "mesh, not the antenna)", ripple < 1.0,
              "{0:.3f} dB peak-to-peak".format(ripple))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if FAILURES:
        print("PALACE DIPOLE FARFIELD GATE FAILED ({0})".format(len(FAILURES)))
        return 1
    print("PALACE DIPOLE FARFIELD GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
