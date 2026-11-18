"""Layer 4 allocation: where the next field check goes.

The estimator mirrors layer 3 (stratified, shrunk toward a fixed calibration prior):

    p_uh    = (k_uh + m * pi_h) / (n_uh + m)
    theta_u = sum_h W_uh * p_uh
    s_u^2   = sum_h W_uh^2 * p_uh (1 - p_uh) / (n_uh + m + 1) * fpc_uh
    call_u  = theta_u > tau,   P_u = Phi((theta_u - tau) / s_u)

It is re-implemented here (the contract between layers is files, not imports); tau, m and
pi_h are read from layer 3 when its artifacts exist.

Allocation rules (all answer every unit; only the placement of checks differs):
    random       : each check is a uniformly random plot of the whole region
    proportional : checks split by unit size, and inside a unit by map-stratum share
    uncertainty  : greedy, largest drop in the unit's variance (decision-blind)
    decision     : greedy, largest expected drop in P(wrong call), Gauss-Hermite look-ahead

No side effects on import.
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtr

GH_X, GH_W = np.polynomial.hermite_e.hermegauss(15)
GH_W = GH_W / GH_W.sum()
RULES = ("random", "proportional", "uncertainty", "decision")


class StratSurvey:
    """Field checks inside each (unit, map stratum); plots drawn by SRS without replacement.

    Y : list of bool arrays, true flooded status per plot of each unit (only read when a plot is checked)
    f : list of bool arrays, map stratum per plot (True = mapped flooded)
    """

    def __init__(self, Y, f, pi_h, m, tau, rng):
        self.U = len(Y)
        self.Y, self.f = Y, f
        self.Nh = np.array([[(~fu).sum(), fu.sum()] for fu in f], float)
        self.N = self.Nh.sum(1)
        self.W = self.Nh / self.N[:, None]
        self.pi = np.asarray(pi_h, float)
        self.m, self.tau = float(m), float(tau)
        self.n = np.zeros((self.U, 2))
        self.k = np.zeros((self.U, 2))
        self.order = [[rng.permutation(np.flatnonzero(fu == bool(h))) for h in (0, 1)] for fu in f]
        self.log = []                      # (unit, stratum, plot index, flooded)

    def can(self):
        return self.n < self.Nh

    def label(self, u, h):
        u, h = int(u), int(h)
        if self.n[u, h] >= self.Nh[u, h]:
            return False
        i = int(self.order[u][h][int(self.n[u, h])])
        y = bool(self.Y[u][i])
        self.n[u, h] += 1
        self.k[u, h] += y
        self.log.append((u, h, i, y))
        return True

    def p(self, n=None, k=None):
        n = self.n if n is None else n
        k = self.k if k is None else k
        return (k + self.m * self.pi) / (n + self.m)

    def var_h(self, n, p):
        fpc = np.where(self.Nh > 0, np.clip(1 - n / np.maximum(self.Nh, 1), 0, 1), 0)
        return self.W ** 2 * p * (1 - p) / (n + self.m + 1) * fpc

    def estimate(self):
        p = self.p()
        theta = (self.W * p).sum(1)
        s = np.sqrt(self.var_h(self.n, p).sum(1) + 1e-12)
        return theta, s, p

    def calls(self):
        theta, s, _ = self.estimate()
        return theta > self.tau, ndtr((theta - self.tau) / s)


def p_wrong(d, s):
    """chance the current call is wrong, Phi(-|d| / s)."""
    return ndtr(-np.abs(d) / np.maximum(s, 1e-9))


def lookahead_gain(d, v_now, v_after):
    """expected drop in P(wrong call) when the variance goes from v_now to v_after.

    The future estimate d' ~ N(d, v_now - v_after); E[Phi(-|d'|/s')] by 15-point Gauss-Hermite.
    Broadcasts over any matching shapes.
    """
    tau = np.sqrt(np.maximum(v_now - v_after, 0))
    s1 = np.sqrt(np.maximum(v_after, 1e-14))
    after = (ndtr(-np.abs(d[..., None] + tau[..., None] * GH_X) / s1[..., None]) * GH_W).sum(-1)
    return p_wrong(d, np.sqrt(v_now)) - after


def stratum_gains(S, rule):
    """gain of one more check in each (unit, stratum); -inf where the stratum is exhausted."""
    theta, s, p = S.estimate()
    v0 = S.var_h(S.n, p)
    v1 = S.var_h(S.n + 1, p)
    if rule == "uncertainty":
        g = v0 - v1
    elif rule == "decision":
        tot = v0.sum(1, keepdims=True)
        g = lookahead_gain(np.repeat((theta - S.tau)[:, None], 2, 1), np.repeat(tot, 2, 1), tot - v0 + v1)
    else:
        raise ValueError(rule)
    return np.where(S.can(), g, -np.inf)


def visit_plan(S, u, c):
    """how c checks in unit u are split over its strata (greedy variance drop inside the unit)."""
    n = S.n[u].copy()
    p = S.p()[u]
    W, Nh, m = S.W[u], S.Nh[u], S.m
    for _ in range(int(c)):
        fpc0 = np.clip(1 - n / np.maximum(Nh, 1), 0, 1)
        fpc1 = np.clip(1 - (n + 1) / np.maximum(Nh, 1), 0, 1)
        dv = W ** 2 * p * (1 - p) * (fpc0 / (n + m + 1) - fpc1 / (n + m + 2))
        dv = np.where(n < Nh, dv, -np.inf)
        if not np.isfinite(dv).any():
            break
        n[int(np.argmax(dv))] += 1
    return n - S.n[u]


def visit_gain(S, c):
    """expected drop in P(wrong call) of unit u from a visit of c checks (all units at once)."""
    theta, s, p = S.estimate()
    v0 = S.var_h(S.n, p).sum(1)
    add = np.array([visit_plan(S, u, c) for u in range(S.U)])
    v1 = S.var_h(S.n + add, p).sum(1)
    return lookahead_gain(theta - S.tau, v0, v1), add


def run_allocation(S, rule, checkpoints, rng, pilot=1, batch=1):
    """spend checks one at a time with `rule`; returns {total checks: (call, P_u)} at each checkpoint.

    checkpoints are total checks for the region (sorted). For 'proportional' the allocation is not
    nested, so the caller should use proportional_allocation per checkpoint instead.
    """
    out, spent = {}, 0
    cps = sorted(int(c) for c in checkpoints)
    if 0 in cps:
        out[0] = S.calls()
    target = cps[-1] if cps else 0

    def record():
        if spent in cps and spent not in out:
            out[spent] = S.calls()

    if rule == "random":
        flat = np.concatenate([np.stack([np.full(len(fu), u), fu.astype(int)], 1) for u, fu in enumerate(S.f)])
        for j in rng.permutation(len(flat))[:target]:
            S.label(*flat[j]); spent += 1; record()
    else:
        if pilot:
            for _ in range(int(pilot)):
                for u in range(S.U):
                    for h in (0, 1):
                        if spent < target and S.can()[u, h]:
                            S.label(u, h); spent += 1; record()
        while spent < target:
            g = stratum_gains(S, rule)
            if not np.isfinite(g).any():
                break
            take = np.argsort(g, axis=None)[::-1][: max(1, min(int(batch), target - spent))]
            for flat in take:
                if not np.isfinite(g.flat[flat]):
                    break
                S.label(*divmod(int(flat), 2)); spent += 1; record()
    for c in cps:                         # budgets beyond what could be spent
        if c not in out:
            out[c] = S.calls()
    return out


def proportional_allocation(S, total):
    """deterministic proportional-to-size split (largest remainder), in place."""
    share = S.Nh.ravel() / S.Nh.sum() * total
    base = np.floor(share).astype(int)
    rem = int(total - base.sum())
    if rem > 0:
        base[np.argsort(-(share - base))[:rem]] += 1
    for flat, c in enumerate(base):
        u, h = divmod(flat, 2)
        for _ in range(int(c)):
            S.label(u, h)
    return S.calls()


def load_chip_units(art_dir, split, min_px=200, prob="p_flooded"):
    """pseudo-village units on labelled chips (layer 1 units_chips + layer 2 maps), for a real-error check.

    Plots are pixels where layer 2 makes a call (domain == 1) and the hand label is known (0 or 1).
    Returns dict(Y, P, f, unit_id) or None when the artifacts are missing. Labels are WATER, so this
    checks allocation under real map error for flooded area, not for flooded paddy specifically.
    """
    import pathlib
    art = pathlib.Path(art_dir)
    up = art / "layer1" / "units_chips.parquet"
    if not up.exists() or not (art / "layer2" / "maps").exists():
        return None
    import pandas as pd
    units = pd.read_parquet(up)
    units = units[units["split"] == split]
    out = dict(Y=[], P=[], f=[], unit_id=[], chip=[])
    cache = {}
    for _, r in units.iterrows():
        mp = art / "layer2" / "maps" / f"{r['chip']}.npz"
        if not mp.exists():
            continue
        if r["chip"] not in cache:
            z = np.load(mp)
            cache[r["chip"]] = (z[prob].astype(float) / 250.0, z["label"], z["domain"])
        p, lab, dom = cache[r["chip"]]
        sl = (slice(int(r["r0"]), int(r["r1"])), slice(int(r["c0"]), int(r["c1"])))
        ok = (dom[sl] == 1) & (lab[sl] >= 0) & (p[sl] <= 1.0)
        if ok.sum() < min_px:
            continue
        pu = p[sl][ok]
        out["Y"].append(lab[sl][ok] == 1)
        out["P"].append(pu)
        out["f"].append(pu > 0.5)
        out["unit_id"].append(r["unit_id"])
        out["chip"].append(r["chip"])
    return out if out["Y"] else None


def wrong_rate(call, truth_above):
    return float(np.mean(np.asarray(call) != np.asarray(truth_above)))


def brier(P, truth_above):
    return float(np.mean((np.asarray(P) - np.asarray(truth_above, float)) ** 2))


def next_checks(S, n_next=20, rule="decision"):
    """ranked list of the next checks for the current state (greedy, state updated virtually)."""
    import copy
    T = copy.copy(S)
    T.n, T.k = S.n.copy(), S.k.copy()
    rows = []
    for rank in range(int(n_next)):
        g = stratum_gains(T, rule)
        if not np.isfinite(g).any():
            break
        flat = int(np.argmax(g))
        u, h = divmod(flat, 2)
        rows.append(dict(rank=rank + 1, unit=u, stratum=("mapped_dry", "mapped_flooded")[h], gain=float(g.flat[flat])))
        # virtual check: expected outcome, so n rises and k by its expectation
        T.k[u, h] += T.p()[u, h]
        T.n[u, h] += 1
    return rows
