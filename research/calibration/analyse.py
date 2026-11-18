"""Calibration evidence for the deck, from the committed per-chip rows. Deterministic.
Run from repo root:  python research/calibration/analyse.py   -> research/calibration/results.json
Confidence error = expected calibration error (ECE), 10 equal-width bins:
    ECE = sum_b (n_b / n) * |mean_confidence_b - fraction_correct_b|
"correct" = measured water area within +/-20% of max(hand-labelled area, 5% of valid chip area).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REP = ROOT / "training/calibration/reports"
rng = np.random.default_rng(20261107)


def sig(a, b, r):
    return 1 / (1 + np.exp(-(a * r + b)))


def platt(raw, y, iters=100):  # same Newton fit with smoothed targets as paper/analysis/experiments.py
    n1, n0 = y.sum(), len(y) - y.sum()
    t = np.where(y > 0, (n1 + 1) / (n1 + 2), 1 / (n0 + 2))
    X = np.stack([raw, np.ones_like(raw)], 1)
    w = np.zeros(2)
    for _ in range(iters):
        p = sig(w[0], w[1], raw)
        w -= np.linalg.solve(X.T @ (X * (p * (1 - p))[:, None]) + 1e-6 * np.eye(2), X.T @ (p - t))
    return float(w[0]), float(w[1])


def ece(p, y, bins=10):
    e = np.linspace(0, 1, bins + 1)
    s = 0.0
    for i in range(bins):
        m = (p >= e[i]) & ((p < e[i + 1]) if i < bins - 1 else (p <= 1))
        if m.any():
            s += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(s)


def boot(fn, *arrs, n=2000):
    m = len(arrs[0])
    v = [fn(*[a[i] for a in arrs]) for i in (rng.integers(0, m, m) for _ in range(n))]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


d = pd.read_csv(REP / "sar_water_otsu_chips.csv")
d = d[d.status == "ok"].copy()
cfg = json.load(open(ROOT / "config/calibration/sar_water_otsu.json"))
A, B = cfg["a"], cfg["b"]
R = {"shipped_map": {"a": A, "b": B}}

# 1. held-out test split (82 chips never used in the fit)
te = d[d.split == "test"]
y, r = te.correct.values.astype(float), te.raw.values
p = sig(A, B, r)
R["test"] = {"n": len(te), "share_correct": y.mean(), "ece_raw": ece(r, y), "ece_cal": ece(p, y),
             "brier_raw": float(((r - y) ** 2).mean()), "brier_cal": float(((p - y) ** 2).mean()),
             "mean_conf_raw": r.mean(), "mean_conf_cal": p.mean(),
             "ece_raw_ci": boot(ece, r, y), "ece_cal_ci": boot(ece, p, y),
             "ece_drop_ci": boot(lambda r_, p_, y_: ece(r_, y_) - ece(p_, y_), r, p, y)}
for tag, q in (("raw", r), ("cal", p)):
    e = np.linspace(0, 1, 6)  # 5 bins for the plot
    R["test"]["reliability_" + tag] = [
        [float(q[m].mean()), float(y[m].mean()), int(m.sum())]
        for i in range(5) if (m := (q >= e[i]) & ((q < e[i + 1]) if i < 4 else (q <= 1))).any()]

# 2. leave-one-region-out over all 408 chips: fit without the region, score on it
loo, P, RR, Y = {}, [], [], []
for ev in sorted(d.event.unique()):
    tr, t = d[d.event != ev], d[d.event == ev]
    a, b = platt(tr.raw.values, tr.correct.values.astype(float))
    yy, rr = t.correct.values.astype(float), t.raw.values
    pp = sig(a, b, rr)
    loo[ev] = {"n": len(t), "acc": yy.mean(), "gap_raw": rr.mean() - yy.mean(), "gap_cal": pp.mean() - yy.mean(),
               "ece_raw": ece(rr, yy), "ece_cal": ece(pp, yy)}
    P += list(pp); RR += list(rr); Y += list(yy)
P, RR, Y = map(np.array, (P, RR, Y))
R["loo_regions"] = loo
R["loo_pooled"] = {"n": len(Y), "ece_raw": ece(RR, Y), "ece_cal": ece(P, Y),
                   "ece_raw_ci": boot(ece, RR, Y), "ece_cal_ci": boot(ece, P, Y),
                   "ece_drop_ci": boot(lambda r_, p_, y_: ece(r_, y_) - ece(p_, y_), RR, P, Y),
                   "mean_abs_region_gap_raw": float(np.mean([abs(v["gap_raw"]) for v in loo.values()])),
                   "mean_abs_region_gap_cal": float(np.mean([abs(v["gap_cal"]) for v in loo.values()]))}
R["n_chips_used"] = len(d)
Path(__file__).with_name("results.json").write_text(json.dumps(R, indent=1, default=float))
print(json.dumps(R, indent=1, default=float))
