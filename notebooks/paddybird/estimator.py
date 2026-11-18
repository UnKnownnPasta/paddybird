"""Layer 3 estimation: map strata plus sparse field checks into a unit flooded-paddy share theta_u.

Population frame
    One row per paddy *plot* (a small block of pixels). Each plot has a unit (village or panchayat
    insurance unit), a visit site (the hamlet or road stop it is checked from), a pixel count w_c,
    the mean calibrated map probability f_c (from layer 2) and, where known, the true flooded
    fraction y_c (validation only; in the field y_c comes from a check).

Estimator (stratified, shrunk, prediction-powered, importance-weighted)
    Plots are stratified by calibrated score: h = 0 (f < 0.15), 1 (0.15 <= f < 0.6), 2 (f >= 0.6).
    W_uh is the pixel share of stratum h in unit u, Fbar_uh its mean map probability. The map is
    the prediction; checks measure its error e_c = y_c - f_c (the PPI "rectifier"):

        R_uh  = sum_c d_c w_c e_c / sum_c d_c w_c          (Hajek; d_c = 1 / pi_c, known)
        lam   = n_eff / (n_eff + m)                        (n_eff = Kish size of the d_c w_c)
        Rt_uh = lam R_uh + (1 - lam) Rpool_h               (shrink to the training-region rectifier)
        theta_u = sum_h W_uh (Fbar_uh + Rt_uh)

    With no checks theta_u is the map plus the training-region correction. Because every check
    carries its known inclusion probability pi_c, route-style selection (near-road sites visited
    more) does not bias R_uh; the unweighted version (d_c = 1) is kept as the naive comparison.

    s_u^2 = V_sampling + V_shrink, where V_sampling is the cluster-robust variance over visit sites
    (moderated, see variance.py) and V_shrink = a' T a with a_h = W_uh (1 - lam_uh) and T the
    between-unit covariance of the stratum rectifiers, fitted on the training region.

Hyperparameters (strata cuts are fixed; Rpool, T, within variance, ICC and the prior strength m)
are fitted on a *training region* only and frozen before the held-out region is touched.

Synthetic generator
    `synthetic_pixels` is a documented stand-in for the layer 1 and 2 artifacts, used until they
    exist. It has unit-level map bias, site-level spatial clustering and a road effect (plots near
    motorable roads sit higher and are mapped wetter than they are), so that route-style selection
    is genuinely biased.

No side effects on import.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

import numpy as np
from scipy.special import expit

from .variance import cluster_robust_var, moderated_var, icc_anova

TAU = 0.25
CUTS = (0.15, 0.6)


# ----------------------------------------------------------------------------------------------
# synthetic stand-in for layers 1 and 2
# ----------------------------------------------------------------------------------------------
def platt_fit(z, y, iters=25):
    """1-D logistic calibration prob = expit(a z + b) by Newton steps."""
    X = np.stack([z, np.ones_like(z)], 1)
    beta = np.zeros(2)
    for _ in range(iters):
        p = expit(X @ beta)
        g = X.T @ (y - p)
        Hm = (X * (p * (1 - p))[:, None]).T @ X
        step = np.linalg.solve(Hm + 1e-9 * np.eye(2), g)
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    return float(beta[0]), float(beta[1])


def synthetic_pixels(n_units=120, seed=0, flood_shift=0.0, calib=None, road_effect=1.0,
                     road_map_error=0.9, n_events=1, event_sd=(0.4, 0.4)):
    """Synthetic pixels with true labels and calibrated flood probabilities.

    Hierarchy: unit -> visit site (10 to 22 per unit) -> plot (12 to 35 per site) -> pixel
    (16 to 80 per plot). True flooding has a unit level, a site effect and a plot effect (so
    neighbouring plots flood together). The map sees evidence z = +-1.4 + unit bias + site bias +
    noise; sites near a road (distance road_km, exponential mean 1 km) are both less flooded
    (road_effect) and look wetter on the map (road_map_error). Probabilities are calibrated by a
    global Platt fit, fitted on this world unless `calib` (a, b) from a training world is passed.
    Units are spread over n_events flood events; each event draws its own flood level shift and map
    bias shift (normal, sd event_sd), so a map correction learnt on some events transfers imperfectly
    to a new one, as with real events.

    Returns a dict of per-pixel arrays (unit, site, plot, prob, label, road_km, event) and `calib`.
    """
    rng = np.random.default_rng(seed)
    U = int(n_units)
    S_u = rng.integers(10, 23, U)
    site_unit = np.repeat(np.arange(U), S_u)
    S = len(site_unit)
    road = rng.exponential(1.0, S)
    near = np.exp(-road / 0.6)
    M_s = rng.integers(12, 36, S)
    plot_site = np.repeat(np.arange(S), M_s)
    C = len(plot_site)
    npx = rng.integers(16, 81, C)
    ev_u = np.arange(U) % int(n_events)
    fs_e = rng.normal(0.0, event_sd[0], int(n_events))
    mb_e = rng.normal(0.0, event_sd[1], int(n_events))
    a_u = rng.normal(-1.7 + flood_shift, 1.0, U) + fs_e[ev_u]
    b_s = rng.normal(0.0, 0.8, S) - road_effect * near
    c_c = rng.normal(0.0, 1.5, C)
    p_c = expit(a_u[site_unit[plot_site]] + b_s[plot_site] + c_c)
    pix_plot = np.repeat(np.arange(C), npx)
    P = len(pix_plot)
    Y = rng.random(P) < p_c[pix_plot]
    du = rng.normal(0.0, 0.5, U) + mb_e[ev_u]
    ds = rng.normal(0.0, 0.4, S) + road_map_error * near
    pix_site = plot_site[pix_plot]
    z = np.where(Y, 1.4, -1.4) + du[site_unit[pix_site]] + ds[pix_site] + rng.normal(0.0, 1.0, P)
    if calib is None:
        sub = rng.choice(P, min(P, 300_000), replace=False)
        calib = platt_fit(z[sub], Y[sub].astype(float))
    prob = expit(calib[0] * z + calib[1])
    return dict(unit=site_unit[pix_site], site=pix_site, plot=pix_plot, prob=prob.astype(np.float32),
                label=Y.astype(np.uint8), road_km=road[pix_site].astype(np.float32),
                event=ev_u[site_unit[pix_site]], calib=calib)


# ----------------------------------------------------------------------------------------------
# frame
# ----------------------------------------------------------------------------------------------
@dataclass
class Frame:
    """Plot-level population frame of one region. Build with `frame_from_pixels`."""
    unit: np.ndarray          # 0..U-1
    site: np.ndarray          # 0..S-1, global
    w: np.ndarray             # pixels per plot
    f: np.ndarray             # mean calibrated map probability
    y: np.ndarray | None      # true flooded fraction (validation only)
    road: np.ndarray | None   # km to a motorable road (per plot)
    unit_ids: np.ndarray      # original unit ids
    cuts: tuple = CUTS
    event: np.ndarray | None = None   # flood event per plot (int), used to fit between-event spread

    def __post_init__(self):
        self.U = int(self.unit.max()) + 1
        self.H = len(self.cuts) + 1
        self.h = np.searchsorted(np.asarray(self.cuts), self.f, side="right")
        self.g = self.unit * self.H + self.h
        UH = self.U * self.H
        self.Wu = np.bincount(self.unit, weights=self.w, minlength=self.U)
        wuh = np.bincount(self.g, weights=self.w, minlength=UH).reshape(self.U, self.H)
        self.W_uh = wuh / self.Wu[:, None]
        fs = np.bincount(self.g, weights=self.w * self.f, minlength=UH).reshape(self.U, self.H)
        self.Fbar_uh = np.where(wuh > 0, fs / np.maximum(wuh, 1e-12), 0.0)
        self.theta_map = np.bincount(self.unit, weights=self.w * self.f, minlength=self.U) / self.Wu
        self.theta_true = None
        if self.y is not None:
            self.theta_true = np.bincount(self.unit, weights=self.w * self.y, minlength=self.U) / self.Wu
        self.unit_event = np.zeros(self.U, int)
        if self.event is not None:
            self.unit_event[self.unit] = self.event
        self.S = int(self.site.max()) + 1
        self.site_unit = np.zeros(self.S, int)
        self.site_unit[self.site] = self.unit
        self.site_size = np.bincount(self.site, minlength=self.S)
        self.site_start = np.concatenate([[0], np.cumsum(self.site_size)[:-1]])
        self.site_road = None
        if self.road is not None:
            self.site_road = np.bincount(self.site, weights=self.road, minlength=self.S) / np.maximum(self.site_size, 1)

    @property
    def n_plots(self):
        return len(self.unit)


def frame_from_pixels(unit, plot, prob, site=None, label=None, road=None, cuts=CUTS, event=None):
    """Aggregate per-pixel layer 2 output to a plot frame.

    unit, plot: per-pixel ids (plot ids must be unique across the region). site: per-pixel visit
    site id; if None every plot is its own site (no clustering information). label: per-pixel true
    flooded flag (validation only). road: per-pixel distance to road in km (optional). event:
    per-pixel flood event id (optional, int).
    """
    unit = np.asarray(unit)
    _, pinv = np.unique(np.asarray(plot), return_inverse=True)
    C = pinv.max() + 1
    w = np.bincount(pinv, minlength=C).astype(float)
    f = np.bincount(pinv, weights=np.asarray(prob, float), minlength=C) / w
    y = None if label is None else np.bincount(pinv, weights=np.asarray(label, float), minlength=C) / w
    rd = None if road is None else np.bincount(pinv, weights=np.asarray(road, float), minlength=C) / w
    first = np.zeros(C, int)
    first[pinv[::-1]] = np.arange(len(pinv))[::-1]
    pu = unit[first]
    ps = pinv.copy()[first] if site is None else np.asarray(site)[first]
    uids, u0 = np.unique(pu, return_inverse=True)
    _, ps0 = np.unique(np.asarray(ps), return_inverse=True)
    # a site belongs to one unit: key sites by (unit, site), then sort so each site is contiguous
    _, s0 = np.unique(np.stack([u0, ps0], 1), axis=0, return_inverse=True)
    s0 = s0.ravel()
    order = np.lexsort((s0, u0))
    _, s1 = np.unique(s0[order], return_inverse=True)
    return Frame(unit=u0[order], site=s1, w=w[order], f=f[order],
                 y=None if y is None else y[order], road=None if rd is None else rd[order],
                 unit_ids=uids, cuts=tuple(cuts),
                 event=None if event is None else np.asarray(event)[first][order].astype(int))


def subset_units(fr: Frame, keep_units):
    """Frame restricted to some units (relabelled 0..)."""
    keep = np.isin(fr.unit, np.asarray(keep_units))
    u = fr.unit[keep]
    _, u0 = np.unique(u, return_inverse=True)
    _, s0 = np.unique(fr.site[keep], return_inverse=True)
    return Frame(unit=u0, site=s0, w=fr.w[keep], f=fr.f[keep],
                 y=None if fr.y is None else fr.y[keep], road=None if fr.road is None else fr.road[keep],
                 unit_ids=fr.unit_ids[np.unique(u)], cuts=fr.cuts,
                 event=None if fr.event is None else fr.event[keep])


# ----------------------------------------------------------------------------------------------
# check designs (validation; layer 4 owns the real plan)
# ----------------------------------------------------------------------------------------------
def draw_checks(fr: Frame, n_per_unit, rng, design="random", k=4, road_scale=0.6, floor=0.05,
                unreached=0.0):
    """Draw field checks with KNOWN inclusion probabilities.

    Two stages: visit sites are drawn by Poisson sampling with probability pi_s (expected
    n_per_unit / k sites per unit), then k plots are drawn by simple random sampling inside each
    drawn site. pi_c = pi_s * min(1, k / M_s).

    design='random': pi_s equal inside a unit.
    design='route' : pi_s proportional to floor + exp(-road_km / road_scale) (near-road sites are
                     visited far more often), still known.
    unreached > 0  : after the draw, a drawn site is dropped with probability
                     unreached * road_km / max(road_km) (far sites missed when the day runs out);
                     the returned pi are the NOMINAL ones, so this tests the estimator when the
                     stated probabilities are wrong.
    Returns dict(idx=plot indices, pi=inclusion probabilities, site=site ids).
    """
    if n_per_unit <= 0:
        return dict(idx=np.zeros(0, int), pi=np.zeros(0), site=np.zeros(0, int))
    n_sites = n_per_unit / k
    if design == "random":
        a = np.ones(fr.S)
    elif design == "route":
        a = floor + np.exp(-fr.site_road / road_scale)
    else:
        raise ValueError(design)
    asum = np.bincount(fr.site_unit, weights=a, minlength=fr.U)
    pi_s = np.clip(n_sites * a / asum[fr.site_unit], 0.0, 1.0)
    sel = rng.random(fr.S) < pi_s
    if unreached > 0 and fr.site_road is not None:
        drop = rng.random(fr.S) < unreached * fr.site_road / fr.site_road.max()
        sel &= ~drop
    key = rng.random(fr.n_plots)
    order = np.lexsort((key, fr.site))
    pos = np.arange(fr.n_plots) - fr.site_start[fr.site[order]]
    take = order[(pos < k) & sel[fr.site[order]]]
    pi = pi_s[fr.site[take]] * np.minimum(1.0, k / fr.site_size[fr.site[take]])
    return dict(idx=np.sort(take), pi=pi[np.argsort(take)], site=fr.site[np.sort(take)])


# ----------------------------------------------------------------------------------------------
# hyperparameters from the training region
# ----------------------------------------------------------------------------------------------
@dataclass
class Hyper:
    cuts: tuple
    Rpool: list            # training-region rectifier per stratum
    T: list                # between-unit covariance of stratum rectifiers (H x H)
    sigma2: list           # within unit-stratum plot variance of the rectifier
    icc: float             # intra-site correlation of rectifier residuals
    k: int                 # plots per visit site
    m: float               # prior strength (pseudo checks) for the shrinkage
    k0: float              # pseudo degrees of freedom for the moderated variance
    map_bias: float        # mean (map - truth) on training units
    map_rmse: float        # RMSE of the raw map on training units
    pi_h: list             # stratum flooded rate (report formula)
    y_mean: float          # mean unit share (sample-only prior)
    y_sd: float
    sigma2_y: float
    icc_y: float
    m_grid_rmse: dict = field(default_factory=dict)
    T_ev: list | None = None   # between-EVENT covariance of the pooled stratum rectifier (H x H)
    n_events: int = 1

    @property
    def deff(self):
        return 1.0 + (self.k - 1) * self.icc

    @property
    def deff_y(self):
        return 1.0 + (self.k - 1) * self.icc_y

    def arrays(self):
        return np.asarray(self.Rpool), np.asarray(self.T), np.asarray(self.sigma2)

    def t_ev(self):
        return np.asarray(self.T if self.T_ev is None else self.T_ev)

    def to_json(self):
        d = asdict(self)
        d["deff"], d["deff_y"] = self.deff, self.deff_y
        return json.dumps(d, indent=1)


def fit_hyper(tr: Frame, k=4, m=None, m_grid=(0.5, 1, 2, 4, 8, 16, 32), k0=2.0, seed=0,
              tune_budgets=(8, 16), tune_reps=40):
    """Fit everything the estimator needs on the TRAINING region only (needs tr.y)."""
    assert tr.y is not None, "training frame needs labels"
    H, U = tr.H, tr.U
    e = tr.y - tr.f
    hw = np.bincount(tr.h, weights=tr.w, minlength=H)
    Rpool = np.bincount(tr.h, weights=tr.w * e, minlength=H) / np.maximum(hw, 1e-12)
    pi_h = np.bincount(tr.h, weights=tr.w * tr.y, minlength=H) / np.maximum(hw, 1e-12)
    gw = np.bincount(tr.g, weights=tr.w, minlength=U * H)
    Ruh = (np.bincount(tr.g, weights=tr.w * e, minlength=U * H) / np.maximum(gw, 1e-12)).reshape(U, H)
    has = (gw > 0).reshape(U, H)
    # event-level pooled rectifier: units are compared with their own event's pool (T), and the
    # spread of the event pools around Rpool (T_ev) is the uncertainty about a NEW event's pool
    ev = tr.unit_event
    evs = np.unique(ev)
    eg = ev[tr.unit] * H + tr.h
    ne = int(ev.max()) + 1
    ew = np.bincount(eg, weights=tr.w, minlength=ne * H).reshape(ne, H)
    Reh = np.where(ew > 0, np.bincount(eg, weights=tr.w * e, minlength=ne * H).reshape(ne, H) / np.maximum(ew, 1e-12), Rpool)
    dev = np.where(has, Ruh - Reh[ev], 0.0)
    T = dev.T @ dev / U
    if len(evs) >= 2:
        de = Reh[evs] - Rpool
        T_ev = de.T @ de / (len(evs) - 1)
    else:
        T_ev = T.copy()     # one training event: assume a new event can move as much as a unit
    r = e - Ruh.ravel()[tr.g]
    sigma2 = np.array([np.sum(tr.w[tr.h == j] * r[tr.h == j] ** 2) / max(hw[j], 1e-12) for j in range(H)])
    icc, _, _ = icc_anova(tr.g, tr.site, r, tr.w)
    yu = tr.theta_true
    ry = tr.y - yu[tr.unit]
    icc_y, sigma2_y, _ = icc_anova(tr.unit, tr.site, ry, tr.w)
    hyp = Hyper(cuts=tuple(tr.cuts), Rpool=Rpool.tolist(), T=T.tolist(), sigma2=sigma2.tolist(),
                icc=icc, k=int(k), m=float(m if m is not None else 4.0), k0=float(k0),
                map_bias=float(np.mean(tr.theta_map - yu)),
                map_rmse=float(np.sqrt(np.mean((tr.theta_map - yu) ** 2))),
                pi_h=pi_h.tolist(), y_mean=float(yu.mean()), y_sd=float(yu.std()),
                sigma2_y=sigma2_y, icc_y=icc_y, T_ev=T_ev.tolist(), n_events=int(len(evs)))
    if m is None:
        # tune m event by event (the estimator pools within the region it is run on)
        rng = np.random.default_rng(seed)
        subs = [subset_units(tr, np.flatnonzero(ev == e_)) for e_ in evs if np.sum(ev == e_) >= 3] if len(evs) >= 2 else [tr]
        draws = [(fs, draw_checks(fs, b, rng, "random", k)) for fs in subs for b in tune_budgets
                 for _ in range(max(2, tune_reps // len(subs)))]
        best = None
        for mm in m_grid:
            hyp.m = float(mm)
            err = [np.mean((est_ppi(fs, c, hyp)["theta"] - fs.theta_true) ** 2) for fs, c in draws]
            rm = float(np.sqrt(np.mean(err)))
            hyp.m_grid_rmse[str(mm)] = rm
            if best is None or rm < best[1]:
                best = (mm, rm)
        hyp.m = float(best[0])
    return hyp


# ----------------------------------------------------------------------------------------------
# estimators
# ----------------------------------------------------------------------------------------------
def _ratio_by_group(gid, a, v, n_groups):
    S = np.bincount(gid, weights=a, minlength=n_groups)
    S2 = np.bincount(gid, weights=a * a, minlength=n_groups)
    R = np.bincount(gid, weights=a * v, minlength=n_groups) / np.maximum(S, 1e-300)
    neff = np.where(S2 > 0, S * S / np.maximum(S2, 1e-300), 0.0)
    return S, R, neff


def est_ppi(fr: Frame, checks, hyp: Hyper, weighted=True, labels=None, form="hajek", pool="region"):
    """Stratified shrunk PPI estimate with known inclusion probabilities.

    checks: dict(idx, pi, site). labels: observed y for the checked plots (defaults to fr.y[idx]).
    weighted=False ignores pi (the naive estimator). form="hajek" (ratio, default) or "ht"
    (Horvitz-Thompson with the known stratum size as denominator). pool="region" (v2, default):
    units shrink toward a pool that combines the training prior Rpool (variance T_ev, the
    between-event spread) with the importance-weighted pooled rectifier of all checks in this
    region; pool="train" (v1): shrink toward the training Rpool, treated as exact. Returns theta, s, s_iid, n, n_sites, lam, Rt.
    """
    U, H = fr.U, fr.H
    Rpool, T, sigma2 = hyp.arrays()
    idx = checks["idx"]
    y = fr.y[idx] if labels is None else np.asarray(labels, float)
    g = fr.g[idx]
    u = fr.unit[idx]
    d = 1.0 / checks["pi"] if weighted else np.ones(len(idx))
    a = d * fr.w[idx]
    e = y - fr.f[idx]
    S, R, neff = _ratio_by_group(g, a, e, U * H)
    S, R, neff = S.reshape(U, H), R.reshape(U, H), neff.reshape(U, H)
    if form == "ht" and weighted:
        # Horvitz-Thompson with the KNOWN stratum pixel total as denominator: design-unbiased
        # even when a unit's draw misses the low-probability sites (Hajek is not).
        Nuh = fr.W_uh * fr.Wu[:, None]
        tot = np.bincount(g, weights=a * e, minlength=U * H).reshape(U, H)
        R = np.where(S > 0, tot / np.maximum(Nuh, 1e-300), 0.0)
        S = np.where(S > 0, Nuh, 0.0)
    lam = neff / (neff + hyp.m)
    Tev = np.maximum(np.diag(hyp.t_ev()), 1e-8)
    if pool == "train":
        Ppool, varP = Rpool.copy(), np.zeros(H)
    else:
        h_c = fr.h[idx]
        Sh = np.bincount(h_c, weights=a, minlength=H)
        Rc = np.bincount(h_c, weights=a * e, minlength=H) / np.maximum(Sh, 1e-300)
        zc = a * (e - Rc[h_c]) / np.maximum(Sh[h_c], 1e-300) if len(idx) else np.zeros(0)
        tuh = np.bincount(g, weights=zc, minlength=U * H).reshape(U, H)
        nu = np.bincount(g, minlength=U * H).reshape(U, H) > 0
        nuh = nu.sum(0)
        vc = np.where(nuh >= 2, nuh / np.maximum(nuh - 1, 1) * ((tuh - np.where(nu, tuh, 0).sum(0) / np.maximum(nuh, 1)) ** 2 * nu).sum(0), np.inf)
        vc = np.maximum(vc, 1e-10)
        prec = 1 / Tev + np.where(np.isfinite(vc), 1 / vc, 0.0)
        Ppool = (Rpool / Tev + np.where(np.isfinite(vc), Rc / vc, 0.0)) / prec
        varP = 1 / prec
    Rt = lam * R + (1 - lam) * Ppool[None, :]
    theta = np.sum(fr.W_uh * (fr.Fbar_uh + Rt), 1)
    coef = (fr.W_uh * lam / np.maximum(S, 1e-300)).ravel()
    centre = 0.0 if (form == "ht" and weighted) else R.ravel()[g]
    z = coef[g] * a * (e - centre) if len(idx) else np.zeros(0)
    V_cr, nc = cluster_robust_var(u, checks["site"], z, U)
    V_iid, nn = cluster_robust_var(u, np.arange(len(idx)), z, U)
    with np.errstate(divide="ignore", invalid="ignore"):
        vm = np.where(neff > 0, (fr.W_uh * lam) ** 2 * sigma2[None, :] / np.maximum(neff, 1e-12), 0.0)
    V_model = vm.sum(1) * hyp.deff
    V_model_iid = vm.sum(1)
    A = fr.W_uh * (1 - lam)
    V_shrink = np.einsum("uh,hk,uk->u", A, T, A) + (A ** 2 * varP[None, :]).sum(1)
    V = moderated_var(V_model, V_cr, nc, hyp.k0) + V_shrink
    V_i = moderated_var(V_model_iid, V_iid, nn, hyp.k0) + V_shrink
    return dict(theta=np.clip(theta, 0, 1), s=np.sqrt(np.maximum(V, 1e-10)),
                s_iid=np.sqrt(np.maximum(V_i, 1e-10)), n=np.bincount(u, minlength=U), n_sites=nc,
                lam=lam, Rt=Rt, n_uh=np.bincount(g, minlength=U * H).reshape(U, H), pool=Ppool, pool_var=varP)


def est_map_only(fr: Frame, hyp: Hyper):
    """Raw calibrated map mean; spread from the training-region map RMSE."""
    return dict(theta=fr.theta_map.copy(), s=np.full(fr.U, hyp.map_rmse))


def est_sample_only(fr: Frame, checks, hyp: Hyper, weighted=True):
    """Hajek mean of the checked plots, map ignored; cluster-robust (moderated) variance."""
    U = fr.U
    idx = checks["idx"]
    y = fr.y[idx]
    u = fr.unit[idx]
    d = 1.0 / checks["pi"] if weighted else np.ones(len(idx))
    a = d * fr.w[idx]
    S, R, neff = _ratio_by_group(u, a, y, U)
    z = a * (y - R[u]) / np.maximum(S[u], 1e-300)
    V_cr, nc = cluster_robust_var(u, checks["site"], z, U)
    with np.errstate(divide="ignore", invalid="ignore"):
        Vm = np.where(neff > 0, hyp.sigma2_y * hyp.deff_y / np.maximum(neff, 1e-12), hyp.y_sd ** 2)
    V = moderated_var(Vm, V_cr, nc, hyp.k0)
    theta = np.where(S > 0, R, hyp.y_mean)
    V = np.where(S > 0, V, hyp.y_sd ** 2)
    return dict(theta=theta, s=np.sqrt(np.maximum(V, 1e-10)))


def est_report_formula(fr: Frame, checks, hyp: Hyper):
    """The partial report's Section 3.4 formula: p_uh = (k_uh + m pi_h) / (n_uh + m), iid variance,
    checks treated as a simple random sample (pi ignored, no clustering)."""
    U, H = fr.U, fr.H
    idx = checks["idx"]
    g = fr.g[idx]
    k = np.bincount(g, weights=fr.y[idx], minlength=U * H).reshape(U, H)
    n = np.bincount(g, minlength=U * H).reshape(U, H)
    pi_h = np.asarray(hyp.pi_h)[None, :]
    p = (k + hyp.m * pi_h) / (n + hyp.m)
    theta = np.sum(fr.W_uh * p, 1)
    v = np.sum(fr.W_uh ** 2 * p * (1 - p) / (n + hyp.m + 1), 1)
    return dict(theta=theta, s=np.sqrt(np.maximum(v, 1e-10)))


METHODS = ("map_only", "sample_only", "report_formula", "ppi_v1", "ppi_naive", "ppi_ipw", "ppi_ipw_iid", "ppi_ht")
METHOD_LABELS = {
    "map_only": "map only (raw calibrated mean)",
    "sample_only": "sample only (checks, no map)",
    "report_formula": "report Sec. 3.4 formula (iid, pi ignored)",
    "ppi_v1": "v1: shrink to training pool treated as exact",
    "ppi_naive": "stratified PPI, shrunk, pi ignored",
    "ppi_ipw": "stratified PPI, shrunk, Hajek IPW (Paddybird)",
    "ppi_ipw_iid": "same, but iid variance",
    "ppi_ht": "stratified PPI, unshrunk, Horvitz-Thompson",
}


def run_methods(fr: Frame, checks, hyp: Hyper):
    """All methods on one check draw. ppi_ipw_iid is ppi_ipw with the iid (non-clustered) s;
    ppi_ht is the unshrunk Horvitz-Thompson form (m ~ 0), the design-unbiased reference."""
    out = {"map_only": est_map_only(fr, hyp)}
    out["sample_only"] = est_sample_only(fr, checks, hyp, weighted=True)
    out["report_formula"] = est_report_formula(fr, checks, hyp)
    out["ppi_v1"] = est_ppi(fr, checks, hyp, weighted=True, pool="train")
    out["ppi_naive"] = est_ppi(fr, checks, hyp, weighted=False)
    ours = est_ppi(fr, checks, hyp, weighted=True)
    out["ppi_ipw"] = ours
    out["ppi_ipw_iid"] = dict(theta=ours["theta"], s=ours["s_iid"])
    h0 = Hyper(**{**asdict(hyp), "m": 1e-6})
    out["ppi_ht"] = est_ppi(fr, checks, h0, weighted=True, form="ht")
    return out


def monte_carlo(fr: Frame, hyp: Hyper, budgets, design="random", reps=200, seed=0, unreached=0.0):
    """Repeat random check draws on a fixed (held-out) region. Returns
    res[method][budget] = dict(theta=(reps, U), s=(reps, U)) and n_checks[budget] = (reps, U)."""
    res = {}
    ncheck = {}
    for b in budgets:
        code = {"random": 1, "route": 2}[design] + (10 if unreached > 0 else 0)
        rng = np.random.default_rng([seed, int(b), code])
        acc = {}
        nn = []
        for r in range(reps):
            c = draw_checks(fr, b, rng, design, hyp.k, unreached=unreached)
            out = run_methods(fr, c, hyp)
            nn.append(np.bincount(fr.unit[c["idx"]], minlength=fr.U))
            for mth, o in out.items():
                acc.setdefault(mth, {"theta": [], "s": []})
                acc[mth]["theta"].append(o["theta"])
                acc[mth]["s"].append(o["s"])
        for mth, o in acc.items():
            res.setdefault(mth, {})[b] = {kk: np.asarray(v) for kk, v in o.items()}
        ncheck[b] = np.asarray(nn)
    return res, ncheck


def unit_strata_table(fr: Frame, est):
    """Per unit-stratum arrays layer 4 needs to plan the next checks."""
    return dict(W_uh=fr.W_uh, Fbar_uh=fr.Fbar_uh, n_uh=est["n_uh"], lam_uh=est["lam"], Rt_uh=est["Rt"])


# ----------------------------------------------------------------------------------------------
# real layer 1 and 2 artifacts
# ----------------------------------------------------------------------------------------------
def _q8(a):
    """layer 2 encoding: uint8 value / 250 = probability, 255 = no call (returned as NaN)."""
    a = np.asarray(a)
    if a.dtype == np.uint8:
        out = a.astype(np.float32) / 250.0
        out[a == 255] = np.nan
        return out
    return a.astype(np.float32)


def load_layer2_chips(art_dir):
    """Per-chip layer 2 maps from artifacts/layer2/maps/<chip>.npz (schema in the layer 2 MANIFEST).

    Uses `p_flooded` (calibrated P(flooded, not permanent water)) on paddy pixels, `paddy`, `label`
    (1 water, 0 not, -1 unlabelled), `domain`, `chip`, `event`, `split`. Returns (list of chip dicts,
    source description) or (None, reason).
    """
    import pathlib
    d2 = pathlib.Path(art_dir) / "layer2"
    if not (d2 / "MANIFEST.json").exists():
        return None, "artifacts/layer2/MANIFEST.json not found"
    files = sorted((d2 / "maps").glob("*.npz")) if (d2 / "maps").exists() else []
    chips = []
    need = {"p_flooded", "paddy", "label", "domain", "split"}
    for p in files:
        z = np.load(p, allow_pickle=False)
        if not need <= set(z.files):
            continue
        chips.append(dict(chip=str(z["chip"]) if "chip" in z.files else p.stem,
                          event=str(z["event"]) if "event" in z.files else "?", split=str(z["split"]),
                          prob=_q8(z["p_flooded"]), paddy=_q8(z["paddy"]), label=z["label"].astype(np.int8),
                          domain=z["domain"].astype(bool), path=str(p)))
    if not chips:
        return None, "no layer2 maps/<chip>.npz with p_flooded, paddy, label, domain, split"
    return chips, f"artifacts/layer2/maps ({len(chips)} chips)"


def load_layer1_units(art_dir):
    """Chip-window units from artifacts/layer1/*units* (parquet, csv or json with unit_id, chip, r0, c0, r1, c1)."""
    import csv, pathlib
    d1 = pathlib.Path(art_dir) / "layer1"
    if not (d1 / "MANIFEST.json").exists():
        return None
    need = {"unit_id", "chip", "r0", "c0", "r1", "c1"}
    for p in sorted(d1.rglob("*units*")):
        rows = None
        try:
            if p.suffix == ".parquet":
                import pandas as pd
                rows = pd.read_parquet(p).to_dict("records")
            elif p.suffix == ".csv":
                rows = list(csv.DictReader(p.open()))
            elif p.suffix in (".json", ".geojson"):
                obj = json.loads(p.read_text())
                if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
                    obj = [f.get("properties", {}) for f in obj["features"]]
                rows = obj if isinstance(obj, list) else None
        except Exception:
            rows = None
        if rows and isinstance(rows[0], dict) and need <= set(rows[0]):
            return rows
    return None


def frames_from_chips(chips, units=None, plot_px=4, site_px=16, grid=2, min_px=1000, cuts=CUTS):
    """Train, val and test frames from layer 2 chip maps.

    Paddy pixels only (domain, paddy >= 0.5, label >= 0); map score = calibrated p_flooded, truth =
    label == 1 (Sen1Floods11 hand label). Units are the layer 1 chip windows when they were cut from
    chips of the same size as the layer 2 maps; otherwise each map is cut into grid x grid square
    pseudo-villages (named <chip>_u<i><j>). Units with fewer than min_px paddy pixels are dropped.
    Plots are plot_px blocks, visit sites site_px blocks. Split is by event: 'val' and 'test' are
    held out, everything else trains. Returns dict(train, val, test, unit_source).
    """
    by_chip = {}
    for r in units or []:
        by_chip.setdefault(str(r["chip"]), []).append(r)
    acc = {s: dict(unit=[], plot=[], site=[], prob=[], label=[], event=[]) for s in ("train", "val", "test")}
    ev_code = {e_: i for i, e_ in enumerate(sorted({c["event"] for c in chips}))}
    names = {s: [] for s in acc}
    used_l1 = 0
    for ci, c in enumerate(chips):
        H_, W_ = c["prob"].shape
        part = c["split"] if c["split"] in ("val", "test") else "train"
        wins = by_chip.get(c["chip"], [])
        l1_size = max([int(float(r["r1"])) for r in wins] + [0])
        if wins and l1_size == H_:
            ws = [(str(r["unit_id"]), int(float(r["r0"])), int(float(r["c0"])), int(float(r["r1"])), int(float(r["c1"])))
                  for r in wins]
            used_l1 += 1
        else:
            k = H_ // grid
            ws = [(f"{c['chip']}_u{i}{j}", i * k, j * k, (i + 1) * k, (j + 1) * k) for i in range(grid) for j in range(grid)]
        ok = c["domain"] & (np.nan_to_num(c["paddy"]) >= 0.5) & (c["label"] >= 0) & np.isfinite(c["prob"])
        rr, cc = np.nonzero(ok)
        for uid, r0, c0, r1, c1 in ws:
            m = (rr >= r0) & (rr < r1) & (cc >= c0) & (cc < c1)
            if m.sum() < min_px:
                continue
            u = len(names[part])
            names[part].append(uid)
            r_, c_ = rr[m], cc[m]
            base = (ci * 10_000 + u) * 4096
            a = acc[part]
            a["unit"].append(np.full(len(r_), u))
            a["plot"].append((base + (r_ // plot_px) * 64 + c_ // plot_px).astype(np.int64))
            a["site"].append((base + (r_ // site_px) * 64 + c_ // site_px).astype(np.int64))
            a["prob"].append(c["prob"][r_, c_])
            a["label"].append((c["label"][r_, c_] == 1).astype(np.uint8))
            a["event"].append(np.full(len(r_), ev_code[c["event"]]))
    out = dict(unit_source=(f"layer 1 chip windows ({used_l1} chips)" if used_l1 else
                            f"{grid} x {grid} pseudo-villages per layer 2 chip (layer 1 windows do not match the map size)"))
    for part, a in acc.items():
        if not a["unit"]:
            out[part] = None
            continue
        cat = {k: np.concatenate(v) for k, v in a.items()}
        fr = frame_from_pixels(cat["unit"], cat["plot"], cat["prob"], site=cat["site"], label=cat["label"], cuts=cuts,
                               event=cat["event"])
        fr.unit_ids = np.asarray(names[part])[fr.unit_ids]
        out[part] = fr
    return out
