# SPDX-License-Identifier: LGPL-2.1-or-later
"""Point-to-point radio propagation models (ROADMAP §6, phase A).

Each model states the regime it is valid in — no single formula covers every
band/scenario, so the caller (and the future coverage engine) picks the right one:

* ``free_space_path_loss_db`` — the reference free-space (Friis) loss.
* ``knife_edge_loss_db`` / ``fresnel_v`` — single knife-edge diffraction over an
  obstruction (ITU-R P.526 approximation), the dominant terrain-shadowing term.
* ``plane_earth_loss_db`` — the two-ray plane-earth (d^4) loss for a link well
  above a reflecting ground in the far field (frequency-independent).
* ``field_strength_dbuv_m`` — the ITU field-strength relation from EIRP, used for
  broadcast/service-contour work (dBuV/m).
* ``terrain_profile_loss`` — total loss over a supplied terrain profile via the
  first-order (Deygout) dominant knife edge + free-space spreading.
* ``link_budget`` — combine tx power, antenna gains and path loss into received
  power and a fade margin.

Pure-python, Qt-free, FreeCAD-free. SI: distances in metres, frequency in Hz,
powers in dBm/dBW, field strength in dBuV/m. Transmitter locations are
user-supplied; no specific sites are referenced.
"""
from __future__ import annotations

import math

C0 = 299792458.0


def wavelength_m(freq_hz):
    return C0 / float(freq_hz)


def free_space_path_loss_db(dist_m, freq_hz):
    """Free-space (Friis) path loss: 20*log10(4*pi*d/lambda) dB. Valid for an
    unobstructed line-of-sight link (the reference every other model corrects)."""
    lam = wavelength_m(freq_hz)
    d = max(float(dist_m), 1e-6)
    return 20.0 * math.log10(4.0 * math.pi * d / lam)


def fresnel_v(clearance_m, d1_m, d2_m, freq_hz):
    """Fresnel-Kirchhoff diffraction parameter v for an edge ``clearance_m`` above
    (positive) or below (negative) the line of sight, ``d1``/``d2`` from the two
    ends: v = h*sqrt(2/lambda*(1/d1 + 1/d2))."""
    lam = wavelength_m(freq_hz)
    d1 = max(float(d1_m), 1e-6)
    d2 = max(float(d2_m), 1e-6)
    return float(clearance_m) * math.sqrt(2.0 / lam * (1.0 / d1 + 1.0 / d2))


def knife_edge_loss_db(v):
    """Single knife-edge diffraction loss (dB) vs the diffraction parameter v,
    ITU-R P.526: J(v) = 6.9 + 20*log10(sqrt((v-0.1)^2 + 1) + v - 0.1) for
    v > -0.78, else 0. J(0) ~= 6 dB (grazing), rising ~6 dB per unit v."""
    v = float(v)
    if v <= -0.78:
        return 0.0
    return 6.9 + 20.0 * math.log10(math.sqrt((v - 0.1) ** 2 + 1.0) + v - 0.1)


def plane_earth_loss_db(dist_m, ht_m, hr_m):
    """Two-ray plane-earth path loss (dB): 40*log10(d) - 20*log10(ht) -
    20*log10(hr). The far-field (d >> breakpoint) result — frequency-independent,
    a d^4 law: doubling the range adds 12 dB. Valid above a reflecting ground with
    both antennas elevated and d beyond the breakpoint 4*ht*hr/lambda."""
    d = max(float(dist_m), 1e-6)
    ht = max(float(ht_m), 1e-6)
    hr = max(float(hr_m), 1e-6)
    return 40.0 * math.log10(d) - 20.0 * math.log10(ht) - 20.0 * math.log10(hr)


def plane_earth_breakpoint_m(ht_m, hr_m, freq_hz):
    """Distance beyond which the plane-earth (d^4) law applies: 4*ht*hr/lambda."""
    return 4.0 * float(ht_m) * float(hr_m) / wavelength_m(freq_hz)


def field_strength_dbuv_m(eirp_w, dist_m):
    """Free-space field strength (dBuV/m) at ``dist_m`` from an EIRP of ``eirp_w``
    watts: E = sqrt(30*P_eirp)/d (V/m). The basis for service/interference
    contours (broadcast, LF/MF ground-wave uses P.368 instead — a later phase)."""
    d = max(float(dist_m), 1e-6)
    e_vm = math.sqrt(30.0 * float(eirp_w)) / d
    return 20.0 * math.log10(e_vm * 1e6)


def _chord_height(x, x_left, h_left, x_right, h_right):
    """Height of the straight chord (x_left, h_left)->(x_right, h_right) at ``x``."""
    return h_left + (h_right - h_left) * (x - x_left) / (x_right - x_left)


def _profile_xy(profile, ht_m, hr_m):
    """(xs, hs): distances + heights, with the antenna heights folded into the ends."""
    xs = [float(p[0]) for p in profile]
    hs = [float(p[1]) for p in profile]
    hs[0] += float(ht_m)
    hs[-1] += float(hr_m)
    return xs, hs


def _main_edge(xs, hs, freq_hz, i_left, i_right):
    """(v, index) of the largest-v edge over the ``i_left..i_right`` chord."""
    best_v, best_i = None, None
    x_l, h_l, x_r, h_r = xs[i_left], hs[i_left], xs[i_right], hs[i_right]
    for k in range(i_left + 1, i_right):
        d1 = xs[k] - x_l
        d2 = x_r - xs[k]
        if d1 <= 0 or d2 <= 0:
            continue
        clearance = hs[k] - _chord_height(xs[k], x_l, h_l, x_r, h_r)
        v = fresnel_v(clearance, d1, d2, freq_hz)
        if best_v is None or v > best_v:
            best_v, best_i = v, k
    return best_v, best_i


def _deygout(xs, hs, freq_hz, i_left, i_right):
    """Recursive Deygout diffraction loss (dB) over the sub-path ``i_left..i_right``.

    Over the edges strictly between the two endpoints, pick the one of largest
    diffraction parameter above the endpoint-to-endpoint chord (the "main" edge), add
    its single-edge ``knife_edge_loss_db``, then recurse independently on the two
    sub-paths — each re-referenced to its OWN chord (the key Deygout construction).
    Edges below a chord (v <= -0.78) contribute nothing.
    """
    best_v, best_i = _main_edge(xs, hs, freq_hz, i_left, i_right)
    if best_i is None or best_v <= -0.78:
        return 0.0
    return (knife_edge_loss_db(best_v)
            + _deygout(xs, hs, freq_hz, i_left, best_i)
            + _deygout(xs, hs, freq_hz, best_i, i_right))


def _edge_loss_on_full_path(xs, hs, freq_hz, k):
    """Single-edge loss (dB) edge ``k`` would give ALONE on the full tx-rx chord."""
    d1 = xs[k] - xs[0]
    d2 = xs[-1] - xs[k]
    clearance = hs[k] - _chord_height(xs[k], xs[0], hs[0], xs[-1], hs[-1])
    return knife_edge_loss_db(fresnel_v(clearance, d1, d2, freq_hz))


def deygout_causebrook_loss_db(profile, ht_m, hr_m, freq_hz):
    """Deygout multiple-edge loss with the CAUSEBROOK correction (dB).

    The recursive Deygout construction over-predicts when edges interact;
    Causebrook & Davis (BBC Research Department Report 1971/43, eqs. 13-15,
    derived from the exact Millington two-edge analysis) subtract a correction
    per sub-edge side at the TOP-LEVEL split ONLY (applying it recursively is
    the classic mis-implementation)::

        A = A1 + A2' - C2 + A3' - C3,   Ci = max(0, (6 - A1 + Ai) cos ai)
        cos a2 = sqrt( a(c+e) / ((a+b)(b+c+e)) )      (eq. 14)
        cos a3 = sqrt( (a+b)e / ((a+b+c)(c+e)) )      (eq. 15)

    where A1 is the main edge's loss on the full path, A2'/A3' the ordinary
    Deygout sub-path losses, Ai the loss the dominant sub-edge of side i would
    give ALONE on the full tx-rx chord, and a, b, c, e the tx->e2, e2->e1
    (main), e1->e3, e3->rx distances. Each correction is bounded by 6 dB
    (cos <= 1 and Ai <= A1 by the main-edge selection). A single controlling
    edge reduces exactly to the uncorrected Deygout / single knife edge.
    Measured comparisons (e.g. Lee & Park, IJAP 2018) show the correction
    helps most where Deygout over-predicts (close/many edges) but is not
    uniformly better — both methods stay available.
    """
    if len(profile) < 2:
        raise ValueError("terrain profile needs at least the two endpoints")
    xs, hs = _profile_xy(profile, ht_m, hr_m)
    n = len(xs) - 1
    v1, i1 = _main_edge(xs, hs, freq_hz, 0, n)
    if i1 is None or v1 <= -0.78:
        return 0.0
    a1 = knife_edge_loss_db(v1)
    total = a1

    # left side: ordinary Deygout sub-path loss + eq. 14 correction
    total += _deygout(xs, hs, freq_hz, 0, i1)
    v2, i2 = _main_edge(xs, hs, freq_hz, 0, i1)
    if i2 is not None and v2 > -0.78:
        a2 = _edge_loss_on_full_path(xs, hs, freq_hz, i2)
        a_d = xs[i2] - xs[0]          # a: tx -> e2
        b_d = xs[i1] - xs[i2]         # b: e2 -> main edge
        ce_d = xs[n] - xs[i1]         # c+e: main edge -> rx
        cos_a2 = math.sqrt(a_d * ce_d / ((a_d + b_d) * (b_d + ce_d)))
        total -= max(0.0, (6.0 - a1 + a2) * cos_a2)

    # right side: symmetric, eq. 15
    total += _deygout(xs, hs, freq_hz, i1, n)
    v3, i3 = _main_edge(xs, hs, freq_hz, i1, n)
    if i3 is not None and v3 > -0.78:
        a3 = _edge_loss_on_full_path(xs, hs, freq_hz, i3)
        ab_d = xs[i1] - xs[0]         # a+b: tx -> main edge
        c_d = xs[i3] - xs[i1]         # c: main edge -> e3
        e_d = xs[n] - xs[i3]          # e: e3 -> rx
        cos_a3 = math.sqrt(ab_d * e_d / ((ab_d + c_d) * (c_d + e_d)))
        total -= max(0.0, (6.0 - a1 + a3) * cos_a3)

    return max(total, 0.0)


def deygout_multiedge_loss_db(profile, ht_m, hr_m, freq_hz):
    """Total diffraction loss (dB) over a terrain profile by the RECURSIVE Deygout
    multiple-knife-edge construction (uncorrected — no Causebrook term).

    A single controlling edge reduces exactly to ``knife_edge_loss_db`` (so a
    one-obstacle path matches the single-edge Deygout); extra edges that protrude
    above their sub-path chords add their diffraction. Validated against the NTIA
    TR-26-580 worked cases. Reuses the shipped single-edge kernel.
    """
    if len(profile) < 2:
        raise ValueError("terrain profile needs at least the two endpoints")
    xs, hs = _profile_xy(profile, ht_m, hr_m)
    return _deygout(xs, hs, freq_hz, 0, len(xs) - 1)


def epstein_peterson_loss_db(profile, ht_m, hr_m, freq_hz):
    """Total diffraction loss (dB) by the Epstein-Peterson construction: each interior
    profile point diffracts over the chord joining its two ADJACENT points (the
    previous/next point, or a terminal), summing the single-edge losses. Validated
    against NTIA TR-26-580.

    Intended for a sparse obstacle list; over a DENSE DEM profile prefer the Deygout
    method (:func:`deygout_multiedge_loss_db`), which self-selects the dominant edges
    rather than summing a loss for every sample.
    """
    if len(profile) < 2:
        raise ValueError("terrain profile needs at least the two endpoints")
    xs, hs = _profile_xy(profile, ht_m, hr_m)
    total = 0.0
    for k in range(1, len(xs) - 1):
        d1 = xs[k] - xs[k - 1]
        d2 = xs[k + 1] - xs[k]
        if d1 <= 0 or d2 <= 0:
            continue
        clearance = hs[k] - _chord_height(xs[k], xs[k - 1], hs[k - 1],
                                          xs[k + 1], hs[k + 1])
        total += knife_edge_loss_db(fresnel_v(clearance, d1, d2, freq_hz))
    return total


def bullington_loss_db(profile, ht_m, hr_m, freq_hz):
    """Total diffraction loss (dB) by the Bullington equivalent-knife-edge
    construction: the horizon ray from each terminal (the line to its worst-slope
    obstruction) is extended, and their intersection forms ONE equivalent knife
    edge whose ``knife_edge_loss_db`` is the path's loss. Deliberately optimistic
    on multi-obstacle paths (it under-predicts — NTIA TR-26-580); useful as the
    classic quick estimate and as the delta-Bullington building block.
    """
    if len(profile) < 2:
        raise ValueError("terrain profile needs at least the two endpoints")
    xs, hs = _profile_xy(profile, ht_m, hr_m)
    x0, h0, x_n, h_n = xs[0], hs[0], xs[-1], hs[-1]
    d_tot = x_n - x0
    s_t = s_r = None
    for k in range(1, len(xs) - 1):
        d1 = xs[k] - x0
        d2 = x_n - xs[k]
        if d1 <= 0 or d2 <= 0:
            continue
        st = (hs[k] - h0) / d1          # slope of the tx ray grazing this edge
        sr = (hs[k] - h_n) / d2         # slope of the rx ray grazing this edge
        s_t = st if s_t is None or st > s_t else s_t
        s_r = sr if s_r is None or sr > s_r else s_r
    if s_t is None or s_t + s_r <= 0:
        return 0.0  # no edges, or the horizon rays diverge (clear path)
    x_eq = x0 + (h_n - h0 + s_r * d_tot) / (s_t + s_r)
    h_eq = h0 + s_t * (x_eq - x0)
    d1 = x_eq - x0
    d2 = x_n - x_eq
    if d1 <= 0 or d2 <= 0:
        return 0.0  # intersection outside the path (clear)
    clearance = h_eq - _chord_height(x_eq, x0, h0, x_n, h_n)
    return knife_edge_loss_db(fresnel_v(clearance, d1, d2, freq_hz))


def terrain_profile_loss(profile, ht_m, hr_m, freq_hz, method="single"):
    """Total path loss over a terrain profile via a knife-edge diffraction method.

    :param profile: list of (distance_m_from_tx, ground_elevation_m), tx first,
        rx last, monotonically increasing distance.
    :param ht_m/hr_m: antenna heights above ground at the tx/rx ends.
    :param method: ``"single"`` (the dominant single Deygout edge — the default,
        byte-identical to earlier releases), ``"deygout"`` (recursive multi-edge
        Deygout), ``"deygout_causebrook"`` (Deygout with the BBC 1971/43
        interaction correction — counters Deygout's over-prediction on
        close/many edges), ``"epstein_peterson"`` (successive-edge sum) or
        ``"bullington"`` (equivalent single edge from the two horizon rays).
        The multi-edge methods reuse the same single-edge kernel and are
        validated against NTIA TR-26-580 / by construction from BBC 1971/43.

    Returns a dict: ``total_loss_db`` (free-space + diffraction), ``fspl_db``,
    ``diffraction_db``, ``v_max``, ``edge_index`` (profile index of the controlling
    edge for the single-edge method, else None), ``method``.
    """
    if len(profile) < 2:
        raise ValueError("terrain profile needs at least the two endpoints")
    d_tot = float(profile[-1][0]) - float(profile[0][0])
    fspl = free_space_path_loss_db(d_tot, freq_hz)

    if method != "single":
        if method in ("deygout", "deygout_multi", "deygout_multiedge"):
            diff = deygout_multiedge_loss_db(profile, ht_m, hr_m, freq_hz)
        elif method in ("deygout_causebrook", "causebrook"):
            diff = deygout_causebrook_loss_db(profile, ht_m, hr_m, freq_hz)
        elif method in ("epstein_peterson", "ep"):
            diff = epstein_peterson_loss_db(profile, ht_m, hr_m, freq_hz)
        elif method == "bullington":
            diff = bullington_loss_db(profile, ht_m, hr_m, freq_hz)
        else:
            raise ValueError("unknown diffraction method: {0}".format(method))
        return {
            "total_loss_db": fspl + diff, "fspl_db": fspl,
            "diffraction_db": diff, "v_max": float("nan"),
            "edge_index": None, "distance_m": d_tot, "method": method,
        }

    z_tx = float(profile[0][1]) + float(ht_m)
    z_rx = float(profile[-1][1]) + float(hr_m)
    x0 = float(profile[0][0])

    v_max = -1e9
    edge_index = None
    for k in range(1, len(profile) - 1):
        d1 = float(profile[k][0]) - x0
        d2 = d_tot - d1
        if d1 <= 0 or d2 <= 0:
            continue
        # height of the line of sight at this distance, and terrain clearance above it
        z_los = z_tx + (z_rx - z_tx) * (d1 / d_tot)
        clearance = float(profile[k][1]) - z_los
        v = fresnel_v(clearance, d1, d2, freq_hz)
        if v > v_max:
            v_max = v
            edge_index = k

    diff = knife_edge_loss_db(v_max) if edge_index is not None else 0.0
    if diff <= 0.0:
        edge_index = None  # clear line of sight (no controlling edge)
    return {
        "total_loss_db": fspl + diff,
        "fspl_db": fspl,
        "diffraction_db": diff,
        "v_max": v_max if edge_index is not None else float("nan"),
        "edge_index": edge_index,
        "distance_m": d_tot,
        "method": "single",
    }


def link_budget(tx_power_dbm, path_loss_db, tx_gain_dbi=0.0, rx_gain_dbi=0.0,
                extra_loss_db=0.0, rx_sens_dbm=None):
    """Received power and (optional) fade margin for a point-to-point link.

    Returns a dict: ``rx_power_dbm`` = Ptx + Gtx + Grx - path_loss - extra_loss,
    and ``fade_margin_db`` = rx_power - rx_sens when a sensitivity is given.
    """
    rx = (float(tx_power_dbm) + float(tx_gain_dbi) + float(rx_gain_dbi)
          - float(path_loss_db) - float(extra_loss_db))
    out = {"rx_power_dbm": rx}
    if rx_sens_dbm is not None:
        out["fade_margin_db"] = rx - float(rx_sens_dbm)
    return out
