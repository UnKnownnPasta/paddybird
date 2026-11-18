"""Layer 2 submergence duration: P(submerged >= d days) per pixel from interval-censored SAR passes,
plus a rice crop-survival curve.

Why interval-censored: Sentinel-1 sees a pixel every R days (6 with two satellites, 12 with one). If a
pixel is dry at pass L, wet at passes a..b and dry again at pass R, its submergence duration D is only
known to lie in [t_b - t_a, t_R - t_L]; with no dry pass after the last wet one it is right-censored.
We estimate the distribution F of D with the Turnbull NPMLE (EM on a day grid) from training pixels,
then for each pixel P(D >= d | its interval) is F restricted to that interval, and
    P(submerged >= d) = P(flooded at the pass) * P(D >= d | interval).

Semi-synthetic: the public chips are single-date, so the time series is simulated around them. The
flood footprint at the observed pass is real (hand label, and the calibrated map's real error rates);
onset, duration and the other passes are synthetic. Every output built from this is labelled
semi-synthetic. No side effects on import.

Crop survival: complete-submergence survival of rice falls steeply after about a week for intolerant
varieties and after about two weeks for SUB1 varieties (Xu et al. 2006, Nature 442:705; Septiningsih
et al. 2009, Ann. Bot. 103:151). We use a logistic S(d) = 1 / (1 + exp((d - d50) / s)) with
d50 = 7, s = 1.5 (intolerant) and d50 = 14, s = 2 (SUB1). These are literature-shaped assumptions,
not fitted curves.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

DUR_DAYS = (3, 7, 10, 14)
SURVIVAL = {"intolerant": (7.0, 1.5), "sub1": (14.0, 2.0)}


def crop_survival(d: np.ndarray, variety: str = "intolerant") -> np.ndarray:
    d50, s = SURVIVAL[variety]
    return 1.0 / (1.0 + np.exp((np.asarray(d, "float64") - d50) / s))


# ---------------------------------------------------------------- semi-synthetic time series
@dataclass
class SimConfig:
    revisit_days: float = 12.0
    passes_before: int = 2
    passes_after: int = 4
    onset_max_days: float = 6.0          # flood began 0..6 days before the observed pass
    median_range: tuple = (4.0, 14.0)    # per-event median duration, days
    sigma_log: float = 0.5               # pixel spread of log duration
    depth_beta: float = 0.25             # darker VV within the flood -> longer (deeper) submergence
    seed: int = 0


def simulate_event(wet0: np.ndarray, obs0: np.ndarray, vv: np.ndarray, sens: float, spec: float,
                   cfg: SimConfig, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """One event's pixels (1-D arrays). wet0: true flooded at the observed pass (hand label); obs0: the
    calibrated map's hard call there (real); vv: VV dB for the depth proxy. Returns true duration D (0 for
    dry pixels), pass times and the observed wet/dry matrix (passes x pixels)."""
    n = wet0.size
    med = rng.uniform(*cfg.median_range)
    z = np.zeros(n)
    if wet0.any():
        v = vv[wet0]
        z[wet0] = -(v - np.nanmean(v)) / (np.nanstd(v) + 1e-6)
    z = np.nan_to_num(z)
    D = med * np.exp(cfg.sigma_log * rng.standard_normal(n) + cfg.depth_beta * z)
    onset = -rng.uniform(0, cfg.onset_max_days, n)
    D = np.where(wet0, np.maximum(D, -onset + 0.25), 0.0)
    onset = np.where(wet0, onset, np.inf)
    times = cfg.revisit_days * np.arange(-cfg.passes_before, cfg.passes_after + 1)
    truth = (times[:, None] >= onset[None, :]) & (times[:, None] < onset[None, :] + D[None, :])
    u = rng.random(truth.shape)
    obs = np.where(truth, u < sens, u < 1 - spec)
    k0 = cfg.passes_before
    obs[k0] = obs0
    return {"D": D, "onset": onset, "times": times, "truth": truth, "obs": obs, "event_median": med}


def intervals_from_obs(obs: np.ndarray, times: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per pixel: (lo, hi, any_wet). lo = t_last_wet - t_first_wet (0 if one wet pass, a tiny positive
    floor is applied later), hi = t_first_dry_after - t_last_dry_before (inf when right-censored)."""
    P, n = obs.shape
    any_wet = obs.any(0)
    first = np.where(any_wet, obs.argmax(0), 0)
    last = np.where(any_wet, P - 1 - obs[::-1].argmax(0), 0)
    lo = times[last] - times[first]
    before = first - 1
    after = last + 1
    t_before = np.where(before >= 0, times[np.clip(before, 0, P - 1)], -np.inf)
    t_after = np.where(after < P, times[np.clip(after, 0, P - 1)], np.inf)
    hi = t_after - t_before
    return lo, hi, any_wet


# ---------------------------------------------------------------- Turnbull NPMLE on a grid
@dataclass
class DurationModel:
    grid: np.ndarray       # bin centres, days
    pmf: np.ndarray        # P(D in bin)

    def _cond(self, lo: np.ndarray, hi: np.ndarray, f: np.ndarray) -> np.ndarray:
        """E[f(D) | lo <= D <= hi] per pixel, computed once per distinct interval (passes are discrete,
        so there are only a few dozen distinct intervals)."""
        lo, hi = np.asarray(lo, "float64"), np.asarray(hi, "float64")
        pairs, inv = np.unique(np.stack([lo, hi], 1), axis=0, return_inverse=True)
        g = self.grid[None, :]
        inside = (g >= np.maximum(pairs[:, :1], 1e-9) - 1e-9) & (g <= pairs[:, 1:] + 1e-9)
        w = inside * self.pmf[None, :]
        den = w.sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            val = np.where(den > 0, (w * f[None, :]).sum(1) / den, np.nan)
        return val[inv.reshape(-1)]

    def p_ge(self, d: float, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        """P(D >= d | lo <= D <= hi) for each pixel."""
        out = self._cond(lo, hi, (self.grid >= d).astype("float64"))
        return np.where(np.isfinite(out), out, (np.asarray(lo) >= d).astype("float64"))

    def expected(self, f, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        out = self._cond(lo, hi, f(self.grid))
        return np.where(np.isfinite(out), out, f(np.asarray(lo, "float64")))


def fit_turnbull(lo: np.ndarray, hi: np.ndarray, step: float = 0.5, d_max: float = 60.0,
                 iters: int = 500, tol: float = 1e-8) -> DurationModel:
    grid = np.arange(step / 2, d_max, step)
    hi = np.minimum(hi, d_max)
    pairs, counts = np.unique(np.stack([lo, hi], 1), axis=0, return_counts=True)
    A = ((grid[None, :] >= np.maximum(pairs[:, :1], 1e-9) - 1e-9) & (grid[None, :] <= pairs[:, 1:] + 1e-9)).astype("float64")
    empty = A.sum(1) == 0
    if empty.any():                    # interval narrower than a bin: put it on the nearest bin
        for i in np.where(empty)[0]:
            A[i, np.argmin(np.abs(grid - pairs[i].mean()))] = 1.0
    p = np.full(grid.size, 1.0 / grid.size)
    w = counts / counts.sum()
    for _ in range(iters):
        den = A @ p
        new = p * (A.T @ (w / den))
        new /= new.sum()
        if np.abs(new - p).max() < tol:
            p = new
            break
        p = new
    return DurationModel(grid, p)


def naive_duration(obs: np.ndarray, revisit: float) -> np.ndarray:
    """Baseline: number of wet passes times the revisit interval (a point estimate, no censoring)."""
    return obs.sum(0) * revisit
