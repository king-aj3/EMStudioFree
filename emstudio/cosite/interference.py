# SPDX-License-Identifier: LGPL-2.1-or-later
"""Deterministic co-site interference calculator (the classic EMC problems).

Given a list of co-located radios (each a transmitter and/or receiver) and the
antenna-to-antenna isolation between them, this computes the four textbook co-site
interference mechanisms:

1. **Intermodulation (IMD)** — nonlinear mixing (at a transmitter PA, a receiver
   front end, or a passive "rusty-bolt" junction) of two or more transmit carriers
   produces spurious products at integer linear combinations of the carriers. The
   in-band troublemakers are the odd-order products that fall close to the
   originals (2f1-f2, 2f2-f1, f1+f2-f3, 3f1-2f2, ...). A product of order
   N = sum|a_i| generated from carriers of power P_i (dBm, at the mixing junction)
   in a device of Nth-order output intercept IP_N has level
   ``P = sum(|a_i|*P_i) - (N-1)*IP_N`` (the standard intercept-point relation; for
   the classic two-tone third order 2f1-f2 → 2*P1 + P2 - 2*IP3).
2. **Receiver desensitization** — a strong off-frequency carrier coupled into a
   receiver compresses/blocks its front end. It desenses when the interfering power
   at the receiver input (``P_tx - isolation``) exceeds the receiver's blocking
   level.
3. **Broadband transmitter noise** — a transmitter's wideband noise floor
   (dBc/Hz), integrated over the victim receiver's bandwidth and reduced by the
   isolation, can sit above the victim's sensitivity even far off-frequency.
4. **Frequency-plan clashes** — a transmit carrier landing inside a victim
   receiver's passband (co-channel / adjacent-channel), reported as a
   desired-to-undesired (D/U) ratio.

Pure-python, Qt-free, FreeCAD-free. Frequencies in Hz, powers in dBm. Radio lists
are generic / user-supplied; no specific sites are referenced.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, replace


@dataclass
class Radio:
    """One co-located radio. tx_freq_hz=0 → receive-only; rx_freq_hz=0 → tx-only."""
    label: str
    tx_freq_hz: float = 0.0
    tx_power_dbm: float = 40.0          # +40 dBm = 10 W
    tx_noise_dbc_hz: float = -150.0     # broadband tx noise floor (dBc/Hz)
    rx_freq_hz: float = 0.0
    rx_bw_hz: float = 25.0e3
    rx_sens_dbm: float = -110.0         # receiver sensitivity / noise floor
    rx_blocking_dbm: float = -20.0      # front-end blocking / desense threshold


# --- intermodulation --------------------------------------------------------
def intermod_products(freqs_hz, max_order=3, min_order=2, max_terms=3):
    """All intermodulation product frequencies of the transmit carriers.

    Enumerates integer coefficient vectors a with order = sum|a_i| in
    [min_order, max_order] over up to ``max_terms`` participating carriers, keeping
    positive product frequencies. Returns a list of dicts sorted by frequency:
    ``{"freq_hz", "order", "coeffs", "indices"}`` where coeffs/indices describe the
    combination (one entry per participating carrier). Duplicate product
    frequencies keep the lowest order (the strongest, most relevant product).
    """
    freqs = [float(f) for f in freqs_hz if f and f > 0]
    n = len(freqs)
    best = {}  # rounded freq -> product dict (lowest order wins)
    kmax = min(n, max_terms, max_order)
    for k in range(1, kmax + 1):
        for combo in itertools.combinations(range(n), k):
            for mags in itertools.product(range(1, max_order + 1), repeat=k):
                order = sum(mags)
                if order < min_order or order > max_order:
                    continue
                for signs in itertools.product((-1, 1), repeat=k):
                    coeffs = [signs[t] * mags[t] for t in range(k)]
                    fprod = math.fsum(coeffs[t] * freqs[combo[t]] for t in range(k))
                    if fprod <= 0.0:
                        continue
                    key = round(fprod, 3)
                    prev = best.get(key)
                    if prev is None or order < prev["order"]:
                        best[key] = {
                            "freq_hz": fprod,
                            "order": order,
                            "coeffs": list(coeffs),
                            "indices": list(combo),
                        }
    return sorted(best.values(), key=lambda p: p["freq_hz"])


def product_terms(product, labels):
    """Human string for an IMD product, e.g. '2*A - B'."""
    parts = []
    for c, idx in zip(product["coeffs"], product["indices"]):
        name = labels[idx]
        sign = "-" if c < 0 else "+"
        mag = abs(c)
        term = name if mag == 1 else "{0}*{1}".format(mag, name)
        parts.append((sign, term))
    out = ("-" + parts[0][1]) if parts[0][0] == "-" else parts[0][1]
    for sign, term in parts[1:]:
        out += " {0} {1}".format(sign, term)
    return out


def imd_level_dbm(product, powers_dbm, ip_dbm):
    """Level (dBm) of an IMD product at the mixing junction.

    ``P = sum(|a_i|*P_i) - (order-1)*IP_order``. ``powers_dbm`` is indexed like the
    carriers; ``ip_dbm`` is the junction's order-N output intercept point.
    """
    order = product["order"]
    p = 0.0
    for c, idx in zip(product["coeffs"], product["indices"]):
        p += abs(c) * float(powers_dbm[idx])
    return p - (order - 1) * float(ip_dbm)


# --- coupling / power book-keeping ------------------------------------------
def received_power_dbm(tx_power_dbm, isolation_db):
    """Interfering power arriving at a victim = tx power minus antenna isolation."""
    return float(tx_power_dbm) - float(isolation_db)


def du_ratio_db(desired_dbm, undesired_dbm):
    """Desired-to-undesired ratio (dB)."""
    return float(desired_dbm) - float(undesired_dbm)


def broadband_noise_at_rx_dbm(tx_power_dbm, tx_noise_dbc_hz, rx_bw_hz, isolation_db):
    """Transmitter broadband noise power in the victim's passband, at its input.

    ``P_noise = P_tx + noise_dBc/Hz + 10log10(BW) - isolation``.
    """
    return (float(tx_power_dbm) + float(tx_noise_dbc_hz)
            + 10.0 * math.log10(max(float(rx_bw_hz), 1.0))
            - float(isolation_db))


def in_band(freq_hz, rx_freq_hz, rx_bw_hz):
    """True if ``freq_hz`` falls within the receiver passband (+/- BW/2)."""
    return abs(float(freq_hz) - float(rx_freq_hz)) <= float(rx_bw_hz) / 2.0


# --- whole-site analysis ----------------------------------------------------
def analyze_site(radios, isolation_db=30.0, junction_ip3_dbm=20.0, max_order=3):
    """Run all four co-site checks over a list of :class:`Radio`.

    :param isolation_db: antenna-to-antenna isolation (dB). A scalar applied to all
        pairs, or a dict ``{(i, j): dB}`` (symmetric; missing pairs use a default
        of 30 dB). Real isolation comes from the field-solver matrix (future
        ``cosite.isolation``); here it is a supplied parameter.
    :param junction_ip3_dbm: third-order output intercept of the assumed mixing
        junction (dBm). Lower = more IMD (a passive rusty-bolt junction is far worse
        than a linear amplifier).
    :param max_order: highest intermod order to enumerate.

    Returns a report dict: ``imd``, ``desense``, ``broadband_noise``, ``cochannel``.
    """
    radios = list(radios)
    labels = [r.label for r in radios]

    def iso(i, j):
        if isinstance(isolation_db, dict):
            return float(isolation_db.get((i, j),
                         isolation_db.get((j, i), 30.0)))
        return float(isolation_db)

    tx_idx = [i for i, r in enumerate(radios) if r.tx_freq_hz > 0]
    rx_idx = [i for i, r in enumerate(radios) if r.rx_freq_hz > 0]
    tx_freqs = [radios[i].tx_freq_hz for i in tx_idx]
    tx_labels = [radios[i].label for i in tx_idx]

    # 1. IMD: products of the transmit carriers landing in a receiver's passband.
    products = intermod_products(tx_freqs, max_order=max_order)
    imd = []
    for prod in products:
        # skip a "product" that is just a carrier itself (order-1 handled out)
        for j in rx_idx:
            rx = radios[j]
            if not in_band(prod["freq_hz"], rx.rx_freq_hz, rx.rx_bw_hz):
                continue
            # powers of the participating carriers at the junction (tx minus the
            # isolation between that tx and the victim)
            powers = {}
            for local_i, tx_i in enumerate(tx_idx):
                powers[tx_i] = received_power_dbm(radios[tx_i].tx_power_dbm,
                                                  iso(tx_i, j))
            # imd_level expects powers indexed by the product's carrier indices,
            # which are indices into tx_freqs -> map back to radio indices
            plist = [0.0] * len(tx_freqs)
            for local_i, tx_i in enumerate(tx_idx):
                plist[local_i] = powers[tx_i]
            level = imd_level_dbm(prod, plist, junction_ip3_dbm)
            imd.append({
                "victim": rx.label,
                "victim_idx": j,
                "freq_hz": prod["freq_hz"],
                "order": prod["order"],
                "terms": product_terms(prod, tx_labels),
                "level_dbm": level,
                "margin_db": level - rx.rx_sens_dbm,   # >0 → above sensitivity
            })

    # 2. Receiver desensitization: strong tx coupled into an off-channel rx.
    desense = []
    for j in rx_idx:
        rx = radios[j]
        for i in tx_idx:
            if i == j:
                continue
            tx = radios[i]
            if in_band(tx.tx_freq_hz, rx.rx_freq_hz, rx.rx_bw_hz):
                continue  # co-channel is handled below, not as blocking
            p_int = received_power_dbm(tx.tx_power_dbm, iso(i, j))
            margin = rx.rx_blocking_dbm - p_int      # <0 → desensed
            desense.append({
                "victim": rx.label, "victim_idx": j,
                "source": tx.label, "source_idx": i,
                "interferer_dbm": p_int,
                "margin_db": margin,
                "desensed": margin < 0.0,
            })

    # 3. Broadband transmitter noise into a victim's passband.
    broadband = []
    for j in rx_idx:
        rx = radios[j]
        for i in tx_idx:
            if i == j:
                continue
            tx = radios[i]
            p_noise = broadband_noise_at_rx_dbm(
                tx.tx_power_dbm, tx.tx_noise_dbc_hz, rx.rx_bw_hz, iso(i, j))
            broadband.append({
                "victim": rx.label, "victim_idx": j,
                "source": tx.label, "source_idx": i,
                "noise_dbm": p_noise,
                "margin_db": p_noise - rx.rx_sens_dbm,   # >0 → above sensitivity
            })

    # 4. Frequency-plan clashes: a tx carrier inside a victim rx passband (D/U).
    cochannel = []
    for j in rx_idx:
        rx = radios[j]
        for i in tx_idx:
            if i == j:
                continue
            tx = radios[i]
            if in_band(tx.tx_freq_hz, rx.rx_freq_hz, rx.rx_bw_hz):
                p_int = received_power_dbm(tx.tx_power_dbm, iso(i, j))
                cochannel.append({
                    "victim": rx.label, "victim_idx": j,
                    "source": tx.label, "source_idx": i,
                    "freq_hz": tx.tx_freq_hz,
                    "interferer_dbm": p_int,
                    "du_db": du_ratio_db(rx.rx_sens_dbm, p_int),
                })

    return {"imd": imd, "desense": desense, "broadband_noise": broadband,
            "cochannel": cochannel, "labels": labels}


# --- frequency-plan optimizer (phase C) -------------------------------------
def plan_cost(report, w_imd=10.0, w_desense=5.0, w_cochannel=20.0):
    """Scalar badness of a co-site plan (0 = clean). Counts the interference
    events, weighted by type, plus a small severity term (how far over threshold).
    """
    imd = [h for h in report["imd"] if h["margin_db"] > 0]
    des = [d for d in report["desense"] if d["desensed"]]
    cc = report["cochannel"]
    sev = (sum(max(0.0, h["margin_db"]) for h in imd)
           + sum(max(0.0, -d["margin_db"]) for d in des)) * 0.01
    return w_imd * len(imd) + w_desense * len(des) + w_cochannel * len(cc) + sev


def _apply_plan(radios, assignment):
    """Return a copy of ``radios`` with tunable transmit frequencies reassigned."""
    out = list(radios)
    for idx, freq in assignment.items():
        out[idx] = replace(out[idx], tx_freq_hz=float(freq))
    return out


def optimize_frequency_plan(radios, tunable, candidates, isolation_db=30.0,
                            junction_ip3_dbm=20.0, max_order=3, max_combos=50000):
    """Search transmit-channel assignments that minimise co-site interference.

    :param tunable: list of radio indices whose transmit frequency may be changed.
    :param candidates: a list of candidate frequencies (Hz) applied to every tunable
        radio, or a dict ``{radio_idx: [freqs]}`` for per-radio channel lists.
    :returns: dict with ``assignment`` ({idx: freq}), ``cost``, ``report``,
        ``baseline_cost``/``baseline_report`` (the as-supplied plan), ``method``
        ('exhaustive'|'greedy'), ``evaluated`` (plans scored), and ``capped`` (bool).

    Exhaustive when the assignment space is small; otherwise greedy
    coordinate-descent (retune one radio at a time until stable).
    """
    if isinstance(candidates, dict):
        cand = {i: [float(f) for f in candidates[i]] for i in tunable}
    else:
        cand = {i: [float(f) for f in candidates] for i in tunable}

    def cost_of(assignment):
        rep = analyze_site(_apply_plan(radios, assignment), isolation_db=isolation_db,
                           junction_ip3_dbm=junction_ip3_dbm, max_order=max_order)
        return plan_cost(rep), rep

    base_assign = {i: radios[i].tx_freq_hz for i in tunable}
    base_cost, base_rep = cost_of(base_assign)

    space = 1
    for i in tunable:
        space *= max(1, len(cand[i]))

    evaluated = 0
    if space <= max_combos:
        method, capped = "exhaustive", False
        best_assign, best_cost, best_rep = base_assign, base_cost, base_rep
        keys = list(tunable)
        for combo in itertools.product(*(cand[i] for i in keys)):
            assign = {keys[k]: combo[k] for k in range(len(keys))}
            c, rep = cost_of(assign)
            evaluated += 1
            if c < best_cost:
                best_assign, best_cost, best_rep = assign, c, rep
    else:
        method, capped = "greedy", True
        best_assign = dict(base_assign)
        best_cost, best_rep = base_cost, base_rep
        improved = True
        while improved:
            improved = False
            for i in tunable:
                for f in cand[i]:
                    trial = dict(best_assign)
                    trial[i] = f
                    c, rep = cost_of(trial)
                    evaluated += 1
                    if c < best_cost - 1e-9:
                        best_assign, best_cost, best_rep = trial, c, rep
                        improved = True

    return {
        "assignment": best_assign, "cost": best_cost, "report": best_rep,
        "baseline_cost": base_cost, "baseline_report": base_rep,
        "method": method, "evaluated": evaluated, "capped": capped,
    }


def summary_text(report):
    """Human-readable rendering of an analyze_site() report."""
    L = ["CO-SITE INTERFERENCE REPORT", "==========================="]
    imd_hits = [h for h in report["imd"] if h["margin_db"] > 0]
    L.append("")
    L.append("Intermodulation hits above rx sensitivity: {0}".format(len(imd_hits)))
    for h in sorted(imd_hits, key=lambda x: -x["margin_db"])[:20]:
        L.append("  order {0}  {1}  = {2:.6g} MHz -> rx '{3}'  {4:.1f} dBm "
                 "({5:+.1f} dB over sens)".format(
                     h["order"], h["terms"], h["freq_hz"] / 1e6, h["victim"],
                     h["level_dbm"], h["margin_db"]))
    desensed = [d for d in report["desense"] if d["desensed"]]
    L.append("")
    L.append("Receiver desensitization events: {0}".format(len(desensed)))
    for d in sorted(desensed, key=lambda x: x["margin_db"])[:20]:
        L.append("  '{0}' desenses rx '{1}': {2:.1f} dBm at input ({3:+.1f} dB "
                 "past blocking)".format(d["source"], d["victim"],
                                         d["interferer_dbm"], -d["margin_db"]))
    clashes = report["cochannel"]
    L.append("")
    L.append("Co-channel / frequency-plan clashes: {0}".format(len(clashes)))
    for c in clashes[:20]:
        L.append("  tx '{0}' in rx '{1}' passband ({2:.6g} MHz), D/U {3:.1f} dB".format(
            c["source"], c["victim"], c["freq_hz"] / 1e6, c["du_db"]))
    noisy = [b for b in report["broadband_noise"] if b["margin_db"] > 0]
    L.append("")
    L.append("Broadband-noise elevations above rx sensitivity: {0}".format(len(noisy)))
    return "\n".join(L)
