"""Signed bias and spread of the day-1 pooled-prior estimate: Hajek (randomised, known q) vs naive pooling (gain_aware routes)."""
import sys, numpy as np, routing_ipw as I, routing_sim as R
from routing_sim import U, N

def run(qsum, reps):
    I.Q_SUM = qsum
    res = {"ipw": [], "naive": []}
    for r in range(reps):
        seed = 500 + r
        rng = np.random.default_rng(seed)
        fld, e, fl, wt, wb, sites, th = R.world(rng)
        Dt, _ = R.dmat(e, wt, sites)
        Y = rng.random((U, N)) < th[:, None]
        sens, fpr = rng.beta(15, 5, U), rng.beta(2, 22, U)
        f = np.where(Y, rng.random((U, N)) < sens[:, None], rng.random((U, N)) < fpr[:, None])
        ps = I.truth_prior(Y, f)
        S = I.LSurvey(Y, f, np.random.default_rng(seed + 7)); S.pri = I.PR_START.copy()
        g = R.gain(S); q = np.clip(qsum * g / g.sum(), I.Q_FLOOR, 1.0)
        cand = np.flatnonzero(np.random.default_rng(seed + 99).random(U) < q)
        R.execute(I.plan_cand(g, Dt, cand), S, Dt)
        got = np.flatnonzero(S.n.sum(1) > 0)
        if len(got) == 0: continue
        res["ipw"].append(I.hajek(S, got, q) - ps); res["naive"].append(I.naive(S) - ps)
    for k, v in res.items():
        v = np.array(v); print(f"Q_SUM={qsum:g} {k:6s} bias(dry,flooded)=({v[:,0].mean():+.3f},{v[:,1].mean():+.3f}) rmse=({np.sqrt((v[:,0]**2).mean()):.3f},{np.sqrt((v[:,1]**2).mean()):.3f}) n={len(v)}")
for qs in (3.0, 8.0): run(qs, int(sys.argv[1]) if len(sys.argv) > 1 else 200)
