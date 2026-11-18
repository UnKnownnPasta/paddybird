"""Layer 4 selection: randomised choice of villages with KNOWN inclusion probabilities.

Why: routed checks are not a random sample of the region (villages near the depot and on dry
roads are visited first). Any quantity pooled across villages (the map-calibration rate pi_h,
the district flooded share) is then biased. A probability "spine" fixes that: each village v
is drawn independently (Poisson sampling) with a known probability q_v, the drawn villages are
always visited, and inside each drawn village a fixed number of plots per map stratum is
drawn by simple random sampling. Every checked plot i in stratum h of village v then has
inclusion probability  pi_i = q_v * c_vh / N_vh,  which is stored with the check and lets layer 3
weight it (Hajek / Horvitz-Thompson).

q_v is probability-proportional-to-priority with a floor:  q_v = clip(c * priority_v, floor, 1),
with c set by bisection so that sum_v q_v equals the expected sample size. The priority can be the
visit gain, village size, or a mix (`routing.spine_priority_values`); size gives the steadiest
weights. Two estimators: Hajek (ratio, small bias with few villages and uneven weights) and
Horvitz-Thompson with the frame size known from the map (unbiased, noisier).

No side effects on import.
"""
from __future__ import annotations

import numpy as np


def pps_floor(priority, n_expected, floor=0.05):
    """inclusion probabilities proportional to priority, floored and capped at 1, summing to n_expected."""
    g = np.maximum(np.asarray(priority, float), 0)
    U = len(g)
    if U == 0:
        return np.zeros(0)
    n_expected = float(min(max(n_expected, floor * U), U))
    if g.sum() <= 0:
        return np.full(U, n_expected / U)
    lo, hi = 0.0, 1.0
    while np.clip(hi * g, floor, 1).sum() < n_expected:
        hi *= 2
        if hi > 1e12:
            break
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if np.clip(mid * g, floor, 1).sum() < n_expected:
            lo = mid
        else:
            hi = mid
    return np.clip(hi * g, floor, 1)


def poisson_draw(q, rng):
    """independent Bernoulli(q_v) draw; returns indices of drawn villages."""
    return np.flatnonzero(rng.random(len(q)) < np.asarray(q))


def design_split(Nh_v, c):
    """fixed plots per stratum for a spine visit: c split as evenly as possible, capped by stratum size."""
    Nh_v = np.asarray(Nh_v, int)
    out = np.zeros(2, int)
    for j in range(int(c)):
        order = (j % 2, 1 - j % 2)
        for h in order:
            if out[h] < Nh_v[h]:
                out[h] += 1
                break
    return out


def hajek_rate(k, n, Nh, q, units):
    """Hajek estimate of the pooled rate P(flooded | map stratum h) over the region.

    k, n : (U, 2) design checks (flooded count, checks) per village and stratum
    Nh   : (U, 2) stratum sizes;  q : (U,) village inclusion probabilities;  units: visited spine villages
    Weight of a plot = 1 / (q_v * n_vh / N_vh), so stratum h's estimate is
    sum_v (N_vh / q_v) kbar_vh / sum_v (N_vh / q_v).
    """
    num, den = np.zeros(2), np.zeros(2)
    for v in units:
        for h in (0, 1):
            if n[v, h] > 0:
                w = Nh[v, h] / q[v]
                num[h] += w * k[v, h] / n[v, h]
                den[h] += w
    return np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)


def ht_rate(k, n, Nh, q, units, frame):
    """Horvitz-Thompson estimate of P(flooded | map stratum h) over the frame villages.

    The denominator (plots of stratum h in the frame) is known from the map, so only the
    numerator is estimated: sum_v (N_vh / q_v) kbar_vh / sum_{v in frame} N_vh. Exactly
    design-unbiased when every drawn village is checked.
    """
    num = np.zeros(2)
    for v in units:
        for h in (0, 1):
            if n[v, h] > 0:
                num[h] += Nh[v, h] / q[v] * k[v, h] / n[v, h]
    den = Nh[np.asarray(frame, bool)].sum(0)
    return np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)


def ht_share(k, n, Nh, q, units, frame):
    """Horvitz-Thompson estimate of the frame's flooded share (stratified inside each village)."""
    num = 0.0
    for v in units:
        for h in (0, 1):
            if n[v, h] > 0:
                num += Nh[v, h] / q[v] * k[v, h] / n[v, h]
    return num / Nh[np.asarray(frame, bool)].sum()


def hajek_share(k, n, Nh, q, units):
    """Hajek estimate of the district flooded share: villages weighted by N_v / q_v,
    each village's share stratified as sum_h W_vh kbar_vh (strata with no check use the other's mean)."""
    num = den = 0.0
    for v in units:
        N_v = Nh[v].sum()
        rates = np.where(n[v] > 0, k[v] / np.maximum(n[v], 1), np.nan)
        if np.all(np.isnan(rates)):
            continue
        rates = np.where(np.isnan(rates), np.nanmean(rates), rates)
        share = float((Nh[v] / N_v * rates).sum())
        num += N_v / q[v] * share
        den += N_v / q[v]
    return num / den if den > 0 else np.nan


def naive_rate(k, n):
    """pooled rate from every check gathered, unweighted (what plain stratum means do)."""
    tot_n = n.sum(0)
    return np.where(tot_n > 0, k.sum(0) / np.maximum(tot_n, 1), np.nan)


def naive_share(k, n, Nh, units):
    """district share from visited villages, each weighted by its size only (no inclusion weights)."""
    num = den = 0.0
    for v in units:
        rates = np.where(n[v] > 0, k[v] / np.maximum(n[v], 1), np.nan)
        if np.all(np.isnan(rates)):
            continue
        rates = np.where(np.isnan(rates), np.nanmean(rates), rates)
        N_v = Nh[v].sum()
        num += N_v * float((Nh[v] / N_v * rates).sum())
        den += N_v
    return num / den if den > 0 else np.nan
