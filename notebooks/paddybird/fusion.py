"""Layer 2 predictor 2 (gradient-boosted pixel model) and multi-predictor fusion per land cover.

Predictor 2 is a histogram gradient-boosted tree classifier on per-pixel SAR, texture and optical-index
features (water.FEATURES). It is CPU-feasible (minutes) and handles missing optical data natively.
It is trained on train events only; its few hyperparameters are chosen on validation events.

Fusion: for each land-cover group g, a two-or-more input logistic regression on the predictors' logits,
    logit P(flooded) = a_g + sum_k w_gk * logit(p_k),
fitted on VALIDATION events only (the predictors were built on train or have no fitted parameters, so
validation is clean data for the weights). Groups with too few validation pixels of either class fall
back to the pooled weights. This is the usual stacked-generalisation form; the per-land-cover weights
are our application of it. No side effects on import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np


def _logit(p, eps=1e-4):
    p = np.clip(np.asarray(p, "float64"), eps, 1 - eps)
    return np.log(p / (1 - p))


def _sig(z):
    return 0.5 * (1 + np.tanh(0.5 * np.asarray(z, "float64")))


# ---------------------------------------------------------------- predictor 2
GBM_GRID = (
    {"max_iter": 200, "learning_rate": 0.1, "max_leaf_nodes": 31, "min_samples_leaf": 200, "l2_regularization": 1.0},
    {"max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 500, "l2_regularization": 1.0},
    {"max_iter": 150, "learning_rate": 0.1, "max_leaf_nodes": 63, "min_samples_leaf": 100, "l2_regularization": 0.0},
)


class PixelModel:
    """A fitted boosted model plus the feature columns it uses (columns that are all missing or constant
    in the training sample, for example optical indices when layer 1 has no Sentinel-2, are dropped)."""

    def __init__(self, model, cols: np.ndarray, lc_col: Optional[int]):
        self.model, self.cols, self.lc_col = model, np.asarray(cols), lc_col

    def _x(self, X: np.ndarray) -> np.ndarray:
        return _lc_codes(X, self.lc_col)[:, self.cols]

    def predict(self, X: np.ndarray, batch: int = 500_000) -> np.ndarray:
        out = np.empty(X.shape[0], "float32")
        for s in range(0, X.shape[0], batch):
            out[s:s + batch] = self.model.predict_proba(self._x(X[s:s + batch]))[:, 1]
        return out


def usable_columns(X: np.ndarray) -> np.ndarray:
    ok = []
    for j in range(X.shape[1]):
        v = X[:, j][np.isfinite(X[:, j])]
        ok.append(v.size > 0 and np.nanmax(v) > np.nanmin(v))
    return np.flatnonzero(ok)


def fit_pixel_model(Xtr: np.ndarray, ytr: np.ndarray, Xva: np.ndarray, yva: np.ndarray, lc_col: Optional[int] = None,
                    grid: Sequence[dict[str, Any]] = GBM_GRID, seed: int = 0) -> dict[str, Any]:
    """Fit each config on train pixels; choose by validation log loss; return the chosen model and the
    small selection table. Land cover enters as a categorical feature (WorldCover codes remapped to 0..k)."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import log_loss
    cols = usable_columns(Xtr)
    cats = np.array([lc_col is not None and j == lc_col for j in cols])
    table, best = [], None
    for i, prm in enumerate(grid):
        m = HistGradientBoostingClassifier(early_stopping=False, random_state=seed, categorical_features=cats, **prm)
        pmod = PixelModel(m, cols, lc_col)
        m.fit(pmod._x(Xtr), ytr)
        pv = pmod.predict(Xva)
        ll = float(log_loss(yva, np.clip(pv, 1e-6, 1 - 1e-6), labels=[0, 1]))
        table.append({"config": i, **prm, "val_log_loss": ll})
        if best is None or ll < best[0]:
            best = (ll, i, pmod)
    return {"model": best[2], "chosen": best[1], "table": table, "cols": cols.tolist()}


_LC_CODES = np.array([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100], "float32")


def _lc_codes(X: np.ndarray, lc_col: Optional[int]) -> np.ndarray:
    if lc_col is None:
        return X
    X = X.copy()
    v = X[:, lc_col]
    idx = np.searchsorted(_LC_CODES, np.nan_to_num(v, nan=0.0))
    idx = np.clip(idx, 0, len(_LC_CODES) - 1).astype("float32")
    idx[~np.isfinite(v)] = np.nan
    X[:, lc_col] = idx
    return X


def predict_pixel_model(model: "PixelModel", X: np.ndarray, lc_col: Optional[int] = None, batch: int = 500_000) -> np.ndarray:
    return model.predict(X, batch)


# ---------------------------------------------------------------- fusion
@dataclass
class LandCoverFusion:
    names: tuple[str, ...]
    C: float = 1.0
    min_class_px: int = 500
    weights: dict[str, list[float]] = field(default_factory=dict)   # group -> [intercept, w_1..w_K]
    source: dict[str, str] = field(default_factory=dict)            # group -> own | pooled
    counts: dict[str, list[int]] = field(default_factory=dict)

    def _fit_one(self, Z: np.ndarray, y: np.ndarray) -> list[float]:
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(C=self.C, max_iter=500)
        lr.fit(Z, y)
        return [float(lr.intercept_[0]), *map(float, lr.coef_[0])]

    def fit(self, P: np.ndarray, y: np.ndarray, groups: np.ndarray) -> "LandCoverFusion":
        Z = _logit(P)
        self.weights = {"_pooled": self._fit_one(Z, y)}
        self.source = {"_pooled": "pooled"}
        self.counts = {"_pooled": [int((y == 0).sum()), int((y == 1).sum())]}
        for g in np.unique(groups):
            m = groups == g
            n0, n1 = int((y[m] == 0).sum()), int((y[m] == 1).sum())
            self.counts[str(g)] = [n0, n1]
            if min(n0, n1) >= self.min_class_px:
                self.weights[str(g)] = self._fit_one(Z[m], y[m])
                self.source[str(g)] = "own"
            else:
                self.weights[str(g)] = self.weights["_pooled"]
                self.source[str(g)] = "pooled (too few val pixels of one class)"
        return self

    def predict(self, P: np.ndarray, groups: np.ndarray) -> np.ndarray:
        Z = _logit(P)
        out = np.empty(Z.shape[0], "float64")
        done = np.zeros(Z.shape[0], bool)
        for g, w in self.weights.items():
            if g == "_pooled":
                continue
            m = groups == g
            out[m] = w[0] + Z[m] @ np.array(w[1:])
            done |= m
        w = self.weights["_pooled"]
        out[~done] = w[0] + Z[~done] @ np.array(w[1:])
        return _sig(out)

    def spec(self) -> dict[str, Any]:
        return {"predictors": list(self.names), "form": "logit P = a_g + sum_k w_gk logit(p_k)", "C": self.C,
                "min_class_px": self.min_class_px, "weights": self.weights, "source": self.source, "val_counts_neg_pos": self.counts}


def fit_fusion_crossfit(P: np.ndarray, y: np.ndarray, groups: np.ndarray, events: np.ndarray,
                        names: tuple[str, ...], **kw) -> tuple[LandCoverFusion, np.ndarray]:
    """Leave-one-val-event-out fused scores (for fitting the calibrator on data the fusion did not see),
    plus the final fusion fitted on all validation events."""
    oof = np.empty(P.shape[0], "float64")
    for e in np.unique(events):
        ho = events == e
        f = LandCoverFusion(names, **kw).fit(P[~ho], y[~ho], groups[~ho])
        oof[ho] = f.predict(P[ho], groups[ho])
    return LandCoverFusion(names, **kw).fit(P, y, groups), oof
