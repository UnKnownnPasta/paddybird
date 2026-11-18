"""Layer 3 calls: the always-answered unit call, its probability P_u, the farmer-report flip value,
and the scoring used to validate them.

Call and probability (no abstain state, every unit is answered):
    call_u = above  if theta_u > tau  else below          (tau = 0.25 by default, configurable)
    P_u    = Phi((theta_u - tau) / s_u)                   (probability the unit is truly above)
    P_right_u = P_u if above else 1 - P_u                 (probability that the stated call is right)

Farmer-report flip value:
    Farmer reports are cheap but self-selected, so they are never mixed into theta_u silently.
    Suppose n_F reports in a unit give a mean flooded share rbar, and one trusted them as an
    estimate of the unit share with an unknown bias b (reports overstate flooding by b). The
    precision-weighted combination is

        theta_c(b) = (theta_u / s_u^2 + (rbar - b) / v_F) / (1 / s_u^2 + 1 / v_F),
        v_F = max(rbar (1 - rbar), 0.05) / n_F.

    The flip value b* solves theta_c(b*) = tau. It is shown next to each call: if the reports
    were taken at face value the combined call is `call_c0`, and that verdict holds only while
    the reports' true bias is on the near side of b*. A large |b*| means the reports could be
    quite biased before they changed anything; a small |b*| means the call hangs on trusting them.

No side effects on import.
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtr

TAU = 0.25


def make_calls(theta, s, tau=TAU):
    """Always-answered call. Returns dict(call, P, P_right, margin_sd)."""
    theta = np.asarray(theta, float)
    s = np.maximum(np.asarray(s, float), 1e-9)
    call = theta > tau
    P = ndtr((theta - tau) / s)
    return dict(call=call, P=P, P_right=np.where(call, P, 1 - P), margin_sd=(theta - tau) / s)


def flip_value(theta, s, rbar, n_F, tau=TAU):
    """Report bias b* at which trusting the reports would put the combined estimate on the line.

    Returns dict(b_star, theta_c0, call_c0); NaN where a unit has no reports.
    """
    theta = np.asarray(theta, float)
    s2 = np.maximum(np.asarray(s, float), 1e-9) ** 2
    rbar = np.asarray(rbar, float)
    n_F = np.asarray(n_F, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        vF = np.maximum(rbar * (1 - rbar), 0.05) / n_F
        prec = 1 / s2 + 1 / vF
        theta_c0 = (theta / s2 + rbar / vF) / prec
        b_star = rbar - (tau * prec - theta / s2) * vF
    none = ~(n_F > 0)
    b_star = np.where(none, np.nan, b_star)
    theta_c0 = np.where(none, np.nan, theta_c0)
    return dict(b_star=b_star, theta_c0=theta_c0, call_c0=np.where(none, False, theta_c0 > tau))


def reliability(P, outcome, n_bins=10):
    """Reliability curve on equal-width bins. Returns dict(mid, mean_P, freq, count, ece)."""
    P = np.asarray(P, float).ravel()
    o = np.asarray(outcome, float).ravel()
    edges = np.linspace(0, 1, n_bins + 1)
    b = np.clip(np.digitize(P, edges) - 1, 0, n_bins - 1)
    cnt = np.bincount(b, minlength=n_bins)
    mp = np.bincount(b, weights=P, minlength=n_bins) / np.maximum(cnt, 1)
    fr = np.bincount(b, weights=o, minlength=n_bins) / np.maximum(cnt, 1)
    ece = float(np.sum(cnt * np.abs(mp - fr)) / max(cnt.sum(), 1))
    return dict(mid=(edges[:-1] + edges[1:]) / 2, mean_P=np.where(cnt > 0, mp, np.nan),
                freq=np.where(cnt > 0, fr, np.nan), count=cnt, ece=ece)


def score(theta, s, truth, tau=TAU, z=1.6449):
    """Metrics over (reps, U) arrays of estimates for a fixed truth (U,).

    bias: mean signed error; abs_unit_bias: mean over units of |mean over draws of the error|
    (shrinkage makes single units biased even when the average is not); rmse; cover90: share of
    90% intervals theta +- 1.645 s containing the truth; wrong: share of wrong calls; brier and
    ece of P_u; mean_s and the ratio of mean s to the realised RMSE (1 is honest).
    """
    theta = np.atleast_2d(theta)
    s = np.atleast_2d(s) * np.ones_like(theta)
    err = theta - truth[None, :]
    above = truth > tau
    c = make_calls(theta, s, tau)
    rel = reliability(c["P"], np.broadcast_to(above, theta.shape))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    return dict(bias=float(err.mean()), abs_unit_bias=float(np.abs(err.mean(0)).mean()), rmse=rmse,
                cover90=float(np.mean(np.abs(err) <= z * s)), wrong=float(np.mean(c["call"] != above[None, :])),
                brier=float(np.mean((c["P"] - above[None, :]) ** 2)), ece=rel["ece"],
                mean_s=float(s.mean()), s_over_rmse=float(np.sqrt(np.mean(s ** 2)) / max(rmse, 1e-12)))
