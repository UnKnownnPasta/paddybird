"""Layer 2 probability calibration and scoring.

Two maps from a raw score (or logit) to a probability, both fitted on validation data only:
  temperature  p = sigmoid(z / T), one parameter, keeps the ranking and the 0.5 point (Guo et al. 2017)
  isotonic     pool-adjacent-violators, monotone step map (Zadrozny and Elkan 2002), adapted from the
               earlier paddybird/calibration.py fit_isotonic with a minimum block size so a few pixels
               cannot create a cliff
Scores: expected calibration error (equal-width bins), Brier, log loss, AUC, IoU and F1 at 0.5, and a
reliability table for plotting. No side effects on import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


def _sig(z):
    return 0.5 * (1 + np.tanh(0.5 * np.asarray(z, "float64")))


def _logit(p, eps=1e-4):
    p = np.clip(np.asarray(p, "float64"), eps, 1 - eps)
    return np.log(p / (1 - p))


# ---------------------------------------------------------------- metrics
def reliability(p: np.ndarray, y: np.ndarray, bins: int = 15) -> dict[str, np.ndarray]:
    p, y = np.asarray(p, "float64"), np.asarray(y, "float64")
    edges = np.linspace(0, 1, bins + 1)
    k = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    n = np.bincount(k, minlength=bins).astype("float64")
    conf = np.bincount(k, weights=p, minlength=bins)
    acc = np.bincount(k, weights=y, minlength=bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"edges": edges, "n": n, "conf": conf / n, "freq": acc / n}


def ece(p: np.ndarray, y: np.ndarray, bins: int = 15) -> float:
    r = reliability(p, y, bins)
    m = r["n"] > 0
    return float(np.sum(r["n"][m] / r["n"].sum() * np.abs(r["conf"][m] - r["freq"][m])))


def scores(p: np.ndarray, y: np.ndarray, bins: int = 15) -> dict[str, float]:
    p, y = np.asarray(p, "float64"), np.asarray(y).astype(bool)
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    hard = p >= 0.5
    tp, fp, fn = float((hard & y).sum()), float((hard & ~y).sum()), float((~hard & y).sum())
    out = {"n": int(p.size), "prevalence": float(y.mean()), "mean_p": float(p.mean()),
           "ece": ece(p, y, bins),
           # pixel ECE is dominated by easy dry pixels; this one keeps only pixels the model calls at least 5 % wet
           "ece_p_ge_0.05": ece(p[p >= 0.05], y[p >= 0.05], bins) if (p >= 0.05).any() else float("nan"),
           "brier": float(np.mean((p - y) ** 2)),
           "log_loss": float(-np.mean(y * np.log(pc) + (~y) * np.log(1 - pc))),
           "iou": tp / max(tp + fp + fn, 1.0), "f1": 2 * tp / max(2 * tp + fp + fn, 1.0),
           "area_ratio_hard": float(hard.sum() / max(y.sum(), 1)), "area_ratio_expected": float(p.sum() / max(y.sum(), 1))}
    try:
        from sklearn.metrics import roc_auc_score
        out["auc"] = float(roc_auc_score(y, p)) if 0 < y.mean() < 1 else float("nan")
    except Exception:  # noqa: BLE001
        out["auc"] = float("nan")
    return out


# ---------------------------------------------------------------- calibrators
def fit_temperature(z: np.ndarray, y: np.ndarray) -> float:
    from scipy.optimize import minimize_scalar
    z, y = np.asarray(z, "float64"), np.asarray(y, "float64")

    def nll(logT):
        p = np.clip(_sig(z / np.exp(logT)), 1e-7, 1 - 1e-7)
        return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    return float(np.exp(minimize_scalar(nll, bounds=(-3, 3), method="bounded").x))


def fit_isotonic(p: np.ndarray, y: np.ndarray, min_block: int = 200, max_points: int = 200_000,
                 seed: int = 0) -> list[list[float]]:
    """PAV on (score, label), then tiny blocks pooled into a neighbour (as in the earlier fit_isotonic).
    Points are block centres; prediction interpolates linearly between them."""
    p, y = np.asarray(p, "float64"), np.asarray(y, "float64")
    if p.size > max_points:
        idx = np.random.default_rng(seed).choice(p.size, max_points, replace=False)
        p, y = p[idx], y[idx]
    o = np.argsort(p, kind="mergesort")
    xs, ys = p[o], y[o]
    # PAV with a stack of blocks [sum x, sum y, weight]
    sx, sy, w = [], [], []
    for xi, yi in zip(xs, ys):
        sx.append(xi); sy.append(yi); w.append(1.0)
        while len(w) > 1 and sy[-2] / w[-2] > sy[-1] / w[-1]:
            sx[-2] += sx[-1]; sy[-2] += sy[-1]; w[-2] += w[-1]
            sx.pop(); sy.pop(); w.pop()
    blocks = [[a / c, b / c, c] for a, b, c in zip(sx, sy, w)]

    def merge(i):
        x0, y0, w0 = blocks[i]
        x1, y1, w1 = blocks[i + 1]
        blocks[i] = [(x0 * w0 + x1 * w1) / (w0 + w1), (y0 * w0 + y1 * w1) / (w0 + w1), w0 + w1]
        del blocks[i + 1]
    i = 0
    while len(blocks) > 1 and i < len(blocks):
        if blocks[i][2] >= min_block:
            i += 1
            continue
        if i == len(blocks) - 1:
            merge(i - 1)
            i = max(i - 2, 0)
        elif i == 0 or blocks[i + 1][2] <= blocks[i - 1][2]:
            merge(i)
        else:
            merge(i - 1)
            i -= 1
    pts: list[list[float]] = []
    for x, yv, _ in blocks:
        if pts and x <= pts[-1][0]:
            pts[-1] = [x, yv]
        else:
            pts.append([float(x), float(yv)])
    return pts


@dataclass
class Calibrator:
    method: str = "identity"              # identity | temperature | isotonic
    T: float = 1.0
    points: list = field(default_factory=list)
    fit_info: dict = field(default_factory=dict)

    def __call__(self, p: np.ndarray) -> np.ndarray:
        p = np.asarray(p, "float64")
        if self.method == "temperature":
            return _sig(_logit(p) / self.T)
        if self.method == "isotonic":
            xs, ys = np.array(self.points).T
            return np.interp(p, xs, ys)
        return p

    def spec(self) -> dict[str, Any]:
        return {"method": self.method, "T": self.T, "points": self.points, "fit": self.fit_info}

    @classmethod
    def from_spec(cls, s: dict[str, Any]) -> "Calibrator":
        return cls(s["method"], s.get("T", 1.0), s.get("points", []), s.get("fit", {}))


def fit_calibrator(p: np.ndarray, y: np.ndarray, method: str) -> Calibrator:
    if method == "temperature":
        return Calibrator("temperature", T=fit_temperature(_logit(p), y), fit_info={"n": int(np.size(p))})
    if method == "isotonic":
        return Calibrator("isotonic", points=fit_isotonic(p, y), fit_info={"n": int(np.size(p))})
    return Calibrator()


def choose_by_event(p: np.ndarray, y: np.ndarray, events: np.ndarray,
                    methods: tuple[str, ...] = ("identity", "temperature", "isotonic")) -> dict[str, Any]:
    """Leave-one-event-out over the validation events: fit each method on the other events, score ECE on
    the held-out one. The method with the lowest mean held-out ECE wins and is refitted on all of val."""
    evs = np.unique(events)
    table: dict[str, list[float]] = {m: [] for m in methods}
    for e in evs:
        tr, ho = events != e, events == e
        for m in methods:
            cal = fit_calibrator(p[tr], y[tr], m)
            table[m].append(ece(cal(p[ho]), y[ho]))
    mean = {m: float(np.mean(v)) for m, v in table.items()}
    best = min(mean, key=mean.get)
    return {"per_event": {m: dict(zip(map(str, evs), map(float, v))) for m, v in table.items()},
            "mean_heldout_ece": mean, "chosen": best, "calibrator": fit_calibrator(p, y, best)}
