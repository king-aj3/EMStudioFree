# SPDX-License-Identifier: LGPL-2.1-or-later
"""Method-of-moments capacitance for bare / insulated wire bundles
(ROADMAP §2 Cable Designer — the insulated-bundle C slice).

This replaces the "bare value only" caveat that :mod:`emstudio.wire.coupling`
carries for insulated bundles: the identity ``C = mu0 eps0 inv(L)`` is exact
only for a homogeneous medium, and cable insulation makes the medium
inhomogeneous (Paul's benchmark: entries move 50-66 %). Here we solve the
inhomogeneous electrostatic problem directly with Clayton Paul's
method-of-moments treatment (Paul, *Analysis of Multiconductor Transmission
Lines* 2e, §5.2.2 bare wires + §5.2.2.1 dielectric insulation; the RIBBON.FOR
/ GETCAP method).

Method (a free-space *equivalent* problem — Paul §5.2.2.1):

* Each conductor carries an entire-domain Fourier surface-charge density on
  its circular boundary: a constant term plus ``nf-1`` cos/sin harmonics.
* Each insulated conductor adds a SECOND charge layer — the bound charge on
  the dielectric's outer surface — with its own Fourier expansion.
* Unknowns are all the Fourier coefficients. Equations, by point matching at
  ``nf`` angles per boundary (spaced ``2 pi / nf`` and rotated by
  ``pi / (2 nf)`` to avoid a singular matrix — Paul App. A eq. A.4):
    - conductor rows: the total potential equals the conductor voltage;
    - dielectric-interface rows: the bound surface charge equals
      ``2 eps0 (er-1)/(er+1)`` times the principal-value normal field there
      (the free-space-equivalent bound-charge relation).
* The generalized (free-space-referenced) capacitance matrix is read from the
  constant terms: ``q_i = 2 pi r_i w_i0`` per conductor, and the free charge
  on an insulated conductor is ``er`` times its conductor-surface layer charge
  (Gauss, eq. 5.47). One unit-voltage solve per conductor fills a column.

Reduce to a transmission-line C with :func:`coupling.reduce_generalized_c`
(eq. 5.21) and close the L loop with ``L = mu0 eps0 inv(C_bare)``.

Pure numpy (harmonic potentials in the complex plane); Qt-free, FreeCAD-free.
SI units. Validated in ``tests/validation/cable.py`` against Paul's printed
ribbon-cable tables (problem 5.15 TL matrix 24.98 / -6.266 pF/m, the bare-L
identity 0.7485 / 0.2408 uH/m) and the internal kernel/degeneracy identities.
"""
from __future__ import annotations

import cmath
import math

import numpy as np

EPS0 = 8.8541878128e-12   # CODATA, matching emstudio.wire.coupling


def _phi_layer(z, zc, a, coeffs):
    """Potential at complex point ``z`` of one circular charge layer centred at
    ``zc`` with radius ``a`` and harmonic coefficients ``coeffs`` = [w0 (real),
    c1, c2, ...] where ``c_k`` weights ``cos(k th)`` (real part) and
    ``sin(k th)`` (imag part)."""
    d = abs(z - zc)
    w0 = coeffs[0].real
    phi = -(a * w0 / EPS0) * math.log(d if d >= a else a)
    for k in range(1, len(coeffs)):
        ck = coeffs[k]
        if d >= a:
            phi += (a / (2 * EPS0 * k)) * (ck * (a / (z - zc)) ** k).real
        else:
            phi += (a / (2 * EPS0 * k)) * (ck.conjugate()
                                           * ((z - zc) / a) ** k).real
    return phi


def _en_layer(z, zc, a, coeffs, alpha, self_pv=False):
    """Normal E field (component along direction ``alpha``) at ``z`` from one
    layer. ``self_pv`` returns the principal value when ``z`` lies on the
    layer (the singular self-term keeps only the k=0 radial jump)."""
    if self_pv:
        w0 = coeffs[0].real
        u = (z - zc) / abs(z - zc)
        return (w0 / (2 * EPS0)) * (u.conjugate() * cmath.exp(1j * alpha)).real
    d = abs(z - zc)
    w0 = coeffs[0].real
    # E_x - j E_y for phi = Re W is -W'(z); ln kernel W' = -(a w0/eps0)/(z-zc)
    exj = (a * w0 / EPS0) / (z - zc) if d >= a else 0.0
    en = (exj * cmath.exp(1j * alpha)).real
    for k in range(1, len(coeffs)):
        ck = coeffs[k]
        if d >= a:
            wp = (a / (2 * EPS0 * k)) * ck * (a ** k) * (-k) \
                * (z - zc) ** (-k - 1)
        else:
            wp = (a / (2 * EPS0 * k)) * ck.conjugate() * (a ** -k) * k \
                * (z - zc) ** (k - 1)
        en += (-wp * cmath.exp(1j * alpha)).real
    return en


def generalized_c(wires, nf=10, use_sin=None):
    """Generalized (free-space-referenced) capacitance matrix, F/m.

    :param wires: list of dicts, one per conductor:
        ``{"x", "y", "rw"}`` (metres) for a bare wire, optionally ``"er"``
        (insulation relative permittivity) and ``"t"`` (insulation wall
        thickness, m) for an insulated wire. ``er == 1`` or ``t == 0`` is bare.
    :param nf: Fourier terms per charge layer (1 constant + harmonics). 10 is
        Paul's ribbon-cable value; convergence is monotone in ``nf``.
    :param use_sin: include sin harmonics (needed for asymmetric geometries).
        Default: auto — omitted for a collinear (ribbon) layout where symmetry
        zeroes them, included otherwise.
    :returns: an ``n x n`` numpy array (generalized Maxwell capacitance).

    The matrix is the free-space-referenced (generalized) form; feed it to
    :func:`emstudio.wire.coupling.reduce_generalized_c` for a transmission-line
    C referenced to one conductor.
    """
    n = len(wires)
    if n < 1:
        raise ValueError("need at least one wire")
    if use_sin is None:
        ys = [w["y"] for w in wires]
        use_sin = (max(ys) - min(ys)) > 1e-15   # non-collinear -> need sin

    # harmonic list: (0,'c'), then (k,'c')[,(k,'s')] per order
    harmonics = [(0, "c")]
    k = 1
    while len(harmonics) < nf:
        harmonics.append((k, "c"))
        if use_sin and len(harmonics) < nf:
            harmonics.append((k, "s"))
        k += 1
    m = len(harmonics)

    layers = [(i, "cond", complex(w["x"], w["y"]), w["rw"])
              for i, w in enumerate(wires)]
    for i, w in enumerate(wires):
        if w.get("t", 0.0) > 0.0 and w.get("er", 1.0) != 1.0:
            layers.append((i, "diel", complex(w["x"], w["y"]),
                           w["rw"] + w["t"]))
    ndof = len(layers) * m

    angles = [2 * math.pi * q / m + math.pi / (2 * m) for q in range(m)]

    row_meta = []
    for i, w in enumerate(wires):
        zc = complex(w["x"], w["y"])
        for th in angles:
            row_meta.append(("pot", i, zc + w["rw"] * cmath.exp(1j * th), th,
                             zc, 0.0))
    for li, (i, kind, zc, rad) in enumerate(layers):
        if kind != "diel":
            continue
        fac = 2 * EPS0 * (wires[i]["er"] - 1.0) / (wires[i]["er"] + 1.0)
        for th in angles:
            row_meta.append(("dcont", li, zc + rad * cmath.exp(1j * th), th,
                             zc, fac))
    assert len(row_meta) == ndof

    a_mat = np.zeros((ndof, ndof))
    for lj, (j, kindj, zcj, aj) in enumerate(layers):
        for hidx, (kk, hkind) in enumerate(harmonics):
            col = lj * m + hidx
            coeffs = [complex(0)] * (kk + 1)
            coeffs[kk] = complex(1.0) if (kk == 0 or hkind == "c") \
                else complex(0.0, 1.0)
            for r, meta in enumerate(row_meta):
                tag = meta[0]
                zp = meta[2]
                if tag == "pot":
                    a_mat[r, col] += _phi_layer(zp, zcj, aj, coeffs)
                else:
                    _, li, _zp, th, zci, fac = meta
                    alpha = cmath.phase(zp - zci)
                    sig = 0.0
                    if li == lj:
                        sig = (1.0 if kk == 0 else
                               (math.cos(kk * th) if hkind == "c"
                                else math.sin(kk * th)))
                    en = _en_layer(zp, zcj, aj, coeffs, alpha,
                                   self_pv=(li == lj))
                    a_mat[r, col] += sig - fac * en

    c_gen = np.zeros((n, n))
    for jexc in range(n):
        b = np.zeros(ndof)
        for r, meta in enumerate(row_meta):
            if meta[0] == "pot" and meta[1] == jexc:
                b[r] = 1.0
        xv = np.linalg.solve(a_mat, b)
        for li, (i, kindl, zc, rad) in enumerate(layers):
            if kindl != "cond":
                continue
            q_total = 2 * math.pi * rad * xv[li * m + 0]
            insulated = wires[i].get("t", 0.0) > 0.0 \
                and wires[i].get("er", 1.0) != 1.0
            c_gen[i, jexc] = (wires[i]["er"] * q_total if insulated
                              else q_total)
    return c_gen


def bundle_c_mom(positions, radii, er=None, wall=None, ref=0, nf=10):
    """Insulated-bundle capacitance via MoM — the honest replacement for the
    homogeneous ``coupling.c_matrix_from_l`` when insulation is present.

    :param positions: ``[(x, y), ...]`` conductor centres, metres.
    :param radii: conductor radii, metres.
    :param er: per-conductor insulation permittivity (scalar broadcast, or
        list; ``None`` / 1.0 = bare).
    :param wall: per-conductor insulation wall thickness, metres (scalar or
        list; ``None`` / 0 = bare).
    :param ref: reference conductor for the transmission-line reduction.
    :param nf: Fourier terms per layer.
    :returns: dict — ``c_generalized`` (F/m, free-space-referenced),
        ``c_tl`` (F/m, transmission-line, ``ref`` removed via eq. 5.21),
        ``conductors`` (input indices in ``c_tl`` order), ``nf``.
    """
    from emstudio.wire import coupling

    n = len(positions)
    ers = [1.0] * n if er is None else (
        [float(er)] * n if np.isscalar(er) else [float(e) for e in er])
    walls = [0.0] * n if wall is None else (
        [float(wall)] * n if np.isscalar(wall) else [float(w) for w in wall])
    wires = [{"x": float(positions[i][0]), "y": float(positions[i][1]),
              "rw": float(radii[i]), "er": ers[i], "t": walls[i]}
             for i in range(n)]
    c_gen = generalized_c(wires, nf=nf)
    c_tl = coupling.reduce_generalized_c(c_gen, ref=ref)
    return {
        "c_generalized": c_gen,
        "c_tl": c_tl,
        "conductors": [k for k in range(n) if k != ref],
        "nf": nf,
    }
