"""Learned map-calibration prior under routed sampling: naive pooling vs importance weighting (synthetic).

routing_sim.py froze the pooled stratum prior at a calibrated value because pooling labels gathered
along routes imports roadside-sampling bias. A real survey does not know that value, so here the
prior starts miscalibrated (PR_START) and each variant tries to learn it:
  frozen : keep PR_START
  naive  : pool all checks gathered so far (what plain stratum means do)
  ipw    : day 1 is a probability sample (Poisson, known inclusion q_v, floor > 0); the prior is the
           Hajek estimate from that sample only, sum_v w_v N_vh phat_vh / sum_v w_v N_vh, w_v = 1/q_v
  oracle : the realised pooled rate over all villages (not available in practice)
Planners: nearest (deterministic, no inclusion probability exists) and gain_aware (randomised day 1,
flood-aware insertion). Every village is answered every day.

Run: python routing_ipw.py [reps]   -> routing_ipw_results.json
Limits: iid pixels, one site per village, complete road graph, day-1 pilot only (later days are adaptive
and are not used for the prior), nominal q used even when a drawn village is not reached in time
(the share not reached is reported).
"""
import json, pathlib, sys
import numpy as np
import routing_sim as R
from routing_sim import U, K, DAYS, C, CHECK_MIN, T_DAY, TAU, N

PR_START = np.array([0.15, 0.55])      # miscalibrated start: map dry too wet, map flooded too dry
Q_SUM, Q_FLOOR = 3.0, 0.05            # expected day-1 villages, minimum inclusion probability


class LSurvey(R.Survey):
    pri = PR_START.copy()

    def prior(self):
        return self.pri


def plan_cand(g, D, cand):
    routes, tm, left = [[] for _ in range(K)], [0.0] * K, set(cand)
    while left:
        best = None
        for v in left:
            for r in range(K):
                rt = routes[r]
                for pos in range(len(rt) + 1):
                    a = 0 if pos == 0 else rt[pos - 1] + 1
                    b = 0 if pos == len(rt) else rt[pos] + 1
                    dt = D[a, v + 1] + D[v + 1, b] - D[a, b] + C * CHECK_MIN
                    if tm[r] + dt <= T_DAY and (best is None or 1 / dt > best[0]):
                        best = (1 / dt, v, r, pos, dt)
        if best is None:
            break
        _, v, r, pos, dt = best
        routes[r].insert(pos, v); tm[r] += dt; left.discard(v)
    return routes


def hajek(S, vis, q):
    """pooled P(flooded | map stratum) from the day-1 probability sample."""
    num, den = np.zeros(2), np.zeros(2)
    for v in vis:
        for h in (0, 1):
            if S.n[v, h] > 0:
                w = S.Nh[v, h] / q[v]
                num[h] += w * S.k[v, h] / S.n[v, h]; den[h] += w
    return np.where(den > 0, num / np.maximum(den, 1e-9), PR_START)


def naive(S):
    return np.where(S.n.sum(0) > 0, S.k.sum(0) / np.maximum(S.n.sum(0), 1), PR_START)


def truth_prior(Y, f):
    return np.array([Y[~f].mean(), Y[f].mean()])


def one_rep(seed, specs):
    rng = np.random.default_rng(seed)
    fld, e, flooded, wt, wb, sites, th = R.world(rng)
    Dt, _ = R.dmat(e, wt, sites); Db, _ = R.dmat(e, wb, sites)
    Y = rng.random((U, N)) < th[:, None]
    sens, fpr = rng.beta(15, 5, U), rng.beta(2, 22, U)
    f = np.where(Y, rng.random((U, N)) < sens[:, None], rng.random((U, N)) < fpr[:, None])
    truth = Y.mean(1) > TAU
    pstar = truth_prior(Y, f)
    out = {}
    for planner, prior_kind in specs:
        S = LSurvey(Y, f, np.random.default_rng(seed + 7))
        S.pri = pstar.copy() if prior_kind == "oracle" else PR_START.copy()
        drng = np.random.default_rng(seed + 99)
        wrong, perr, dropped = [float(((S.estimate()[0] > TAU) != truth).mean())], [], 0.0
        for day in range(DAYS):
            if planner == "nearest":
                routes = R.plan("nearest", S, Dt, Db) if day == 0 else R.plan("nearest", S, Dt, Db)
                if day:                              # nearest-first revisits: continue past already-visited villages
                    seen = set(np.flatnonzero(S.n.sum(1) > 0))
                    routes = [[v for v in r if v not in seen] or r for r in routes]
            else:
                g = R.gain(S)
                if day == 0:
                    q = np.clip(Q_SUM * g / g.sum(), Q_FLOOR, 1.0)
                    cand = np.flatnonzero(drng.random(U) < q)
                    routes = plan_cand(g, Dt, cand)
                    q1 = q
                else:
                    routes = R.plan_insert(g, Dt)
            vis0 = set(np.flatnonzero(S.n.sum(1) > 0))
            R.execute(routes, S, Dt)
            if day == 0 and planner == "gain_aware":
                got = set(np.flatnonzero(S.n.sum(1) > 0)) - vis0
                dropped = 1 - len(got) / max(len(cand), 1)
                if prior_kind == "ipw":
                    S.pri = hajek(S, got, q1)
            if prior_kind == "naive":
                S.pri = naive(S)
            perr.append(float(np.abs(S.pri - pstar).mean()))
            wrong.append(float(((S.estimate()[0] > TAU) != truth).mean()))
        out[(planner, prior_kind)] = dict(wrong=wrong, perr=perr, dropped=dropped)
    return out


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    specs = [("nearest", "frozen"), ("nearest", "naive"), ("nearest", "oracle"),
             ("gain_aware", "frozen"), ("gain_aware", "naive"), ("gain_aware", "ipw"), ("gain_aware", "oracle")]
    acc = {s: dict(wrong=[], perr=[], dropped=[]) for s in specs}
    for r in range(reps):
        o = one_rep(500 + r, specs)
        for s in specs:
            for k in acc[s]:
                acc[s][k].append(o[s][k])
    res = {}
    for s, a in acc.items():
        w, p = np.array(a["wrong"]), np.array(a["perr"])
        res[f"{s[0]}/{s[1]}"] = dict(wrong=w.mean(0).tolist(), wrong_se=(w.std(0) / np.sqrt(reps)).tolist(),
                                     prior_err=p.mean(0).tolist(), dropped=float(np.mean(a["dropped"])))
    (pathlib.Path(__file__).parent / "routing_ipw_results.json").write_text(json.dumps(res, indent=1))
    print(f"{reps} reps; wrong-call % days 0..{DAYS}; mean |prior - realised| after each day")
    for k, v in res.items():
        print(f"{k:22s}", " ".join(f"{100 * x:5.1f}" for x in v["wrong"]), "| se d4 %.2f" % (100 * v["wrong_se"][-1]),
              "| prior err", " ".join(f"{x:.3f}" for x in v["prior_err"]), "| dropped %.2f" % v["dropped"])


if __name__ == "__main__":
    main()
