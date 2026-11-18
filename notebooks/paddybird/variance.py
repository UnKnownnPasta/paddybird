"""Layer 3 variance helpers: cluster-robust (visit-site) variance and a moderated fallback.

Field checks are not independent. An officer stops at a site (a hamlet, a stretch of embankment)
and checks several neighbouring plots, and neighbouring plots flood together and are mis-mapped
together. Treating every checked plot as an independent draw then understates the error.

The estimators in `estimator.py` are smooth functions of weighted sums, so their sampling error is
approximated by a linearisation: each checked plot c gets an influence value z_c, and the estimate
moves by about sum_c z_c. The cluster-robust ("ultimate cluster") variance sums z within each visit
site, t_s = sum_{c in s} z_c, and uses the spread of the t_s across the n_s sites of the unit:

    V_cr = n_s / (n_s - 1) * sum_s (t_s - mean t)^2

With one or two visit sites V_cr is either undefined or very noisy, so it is blended with a model
variance V_model fitted on the training region (pooled within-stratum variance times a design
effect), with k0 pseudo degrees of freedom:

    V = (k0 * V_model + (n_s - 1) * V_cr) / (k0 + n_s - 1)

which is V_model for n_s <= 1 and tends to V_cr as the number of sites grows.

No side effects on import.
"""
from __future__ import annotations

import numpy as np


def cluster_robust_var(unit, cluster, z, n_units):
    """Ultimate-cluster variance of sum(z) per unit.

    unit, cluster, z: one entry per checked plot. cluster ids may be any integers (global).
    Returns (V, n_clusters): V is NaN where a unit has fewer than 2 clusters.
    """
    unit = np.asarray(unit, int)
    z = np.asarray(z, float)
    if len(z) == 0:
        return np.full(n_units, np.nan), np.zeros(n_units, int)
    cl, inv = np.unique(np.asarray(cluster), return_inverse=True)
    t = np.bincount(inv, weights=z, minlength=len(cl))
    cu = np.zeros(len(cl), int)
    cu[inv] = unit
    nc = np.bincount(cu, minlength=n_units)
    tbar = np.bincount(cu, weights=t, minlength=n_units) / np.maximum(nc, 1)
    ss = np.bincount(cu, weights=(t - tbar[cu]) ** 2, minlength=n_units)
    V = np.where(nc >= 2, nc / np.maximum(nc - 1, 1) * ss, np.nan)
    return V, nc


def moderated_var(V_model, V_emp, n_clusters, k0=2.0):
    """Blend a training-region model variance with the empirical one (k0 pseudo degrees of freedom)."""
    df = np.maximum(np.asarray(n_clusters, float) - 1.0, 0.0)
    Ve = np.where(np.isfinite(V_emp), V_emp, 0.0)
    return (k0 * np.asarray(V_model, float) + df * Ve) / (k0 + df)


def icc_anova(group, cluster, r, w=None):
    """One-way ANOVA intraclass correlation of residuals r within clusters, ignoring groups' means.

    r should already be centred within its group (for example the unit-stratum). Returns
    (icc, sigma2, mean_cluster_size). Weights w are pixel counts (optional).
    """
    r = np.asarray(r, float)
    w = np.ones_like(r) if w is None else np.asarray(w, float)
    cl, inv = np.unique(np.asarray(cluster) * 1_000_003 + np.asarray(group), return_inverse=True)
    sw = np.bincount(inv, weights=w)
    cm = np.bincount(inv, weights=w * r) / sw
    within = np.sum(w * (r - cm[inv]) ** 2) / w.sum()
    total = np.sum(w * r ** 2) / w.sum()
    nbar = np.mean(np.bincount(inv))
    # cluster means carry within-cluster noise of size within / nbar; remove it
    between = max(total - within - within / max(nbar - 1.0, 1.0), 0.0)
    sigma2 = total
    icc = float(np.clip(between / max(total, 1e-12), 0.0, 1.0))
    return icc, float(sigma2), float(nbar)
