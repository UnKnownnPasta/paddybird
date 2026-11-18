"""Route-aware, decision-targeted field survey on a flooded road graph (synthetic).

Villages sit on a road lattice. A smooth flood field both raises a village's flooded
share and slows the roads around it (flooded edges cost FLOOD_X times more).
Officers leave a depot each day with T_DAY minutes; every check costs CHECK_MIN.
Planners (all answer every unit; only the visit order/choice differs):
  nearest     : nearest unvisited village by flood-blind distance
  gain_only   : highest decision gain first, travel ignored when choosing
  gain_blind  : gain / detour insertion, but planning on a flood-blind road graph
  gain_aware  : gain / detour insertion on the flood-aware graph (Dijkstra)
Execution always uses the true (flooded) travel times and stops when the day runs out.

Run: python routing_sim.py [reps]   -> routing_results.json, docs/figures/route_*.png
Limits (ponytail): villages are single sites; iid pixels; plain stratum means (no
inclusion-probability weighting yet, so routing-induced selection bias is NOT corrected).
"""
import json, pathlib, sys
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.special import ndtr
import sim

U, G, K, DAYS, C, CHECK_MIN, T_DAY, FLOOD_X = 30, 21, 3, 4, 12, 1.5, 240.0, 8.0
sim.U, sim.M = U, 10.0          # strong shrink toward the calibrated map: a few checks per village must not swamp it
TAU, M, N = sim.TAU, sim.M, sim.N
PR0 = np.array([0.08, 0.75])        # calibrated map prior: P(flooded | map dry), P(flooded | map flooded)


class Survey(sim.Survey):
    def prior(self):        # fixed: pooling labels gathered along routes would import the route's selection bias
        return PR0


def world(rng):
    fld = gaussian_filter(rng.standard_normal((G, G)), 3)
    fld = (fld - fld.mean()) / fld.std()
    ij = np.array([(i, j) for i in range(G) for j in range(G)])
    fl = fld.ravel()
    edges = [(a, b) for a in range(G * G) for b in (a + 1 if ij[a][1] < G - 1 else -1, a + G if ij[a][0] < G - 1 else -1) if b >= 0]
    e = np.array(edges)
    flooded = (fl[e[:, 0]] + fl[e[:, 1]]) / 2 > 0.6
    w_true = 2.0 * np.where(flooded, FLOOD_X, 1.0)
    w_blind = np.full(len(e), 2.0)
    sites = np.concatenate([[0], rng.choice(np.arange(1, G * G), U, replace=False)])   # depot + villages
    th = np.clip(0.22 + 0.15 * fl[sites[1:]] + 0.03 * rng.standard_normal(U), 0.02, 0.9)
    return fld, e, flooded, w_true, w_blind, sites, th


def dmat(e, w, sites):
    A = coo_matrix((w, (e[:, 0], e[:, 1])), shape=(G * G, G * G))
    d, pred = dijkstra(A, directed=False, indices=sites, return_predecessors=True)
    return d[:, sites], pred


def gain(S):
    est, sd, p = S.estimate()
    v0 = S.var_h(S.n, p).sum(1)
    v1 = S.var_h(S.n + C / 2, p).sum(1)
    d = est - TAU
    tau, s1 = np.sqrt(np.maximum(v0 - v1, 0)), np.sqrt(v1)
    after = (ndtr(-np.abs(d[:, None] + tau[:, None] * sim.GX) / s1[:, None]) * sim.GW).sum(1)
    return ndtr(-np.abs(d) / np.sqrt(v0)) - after


def plan_insert(g, D):
    routes, tm = [[] for _ in range(K)], [0.0] * K
    left = set(range(U))
    while left:
        best = None
        for v in left:
            for r in range(K):
                rt = routes[r]
                for pos in range(len(rt) + 1):
                    a = 0 if pos == 0 else rt[pos - 1] + 1
                    b = 0 if pos == len(rt) else rt[pos] + 1
                    dt = D[a, v + 1] + D[v + 1, b] - D[a, b] + C * CHECK_MIN
                    if tm[r] + dt <= T_DAY and (best is None or g[v] / dt > best[0]):
                        best = (g[v] / dt, v, r, pos, dt)
        if best is None:
            break
        _, v, r, pos, dt = best
        routes[r].insert(pos, v); tm[r] += dt; left.discard(v)
    return routes


def plan(method, S, Dtrue, Dblind):
    if method == "nearest":
        left, routes = set(range(U)), []
        for _ in range(K):
            pos, r = 0, []
            while left:
                v = min(left, key=lambda x: Dblind[pos, x + 1])
                r.append(v); left.discard(v); pos = v + 1
                if len(r) * (C * CHECK_MIN + 12) > T_DAY:
                    break
            routes.append(r)
        return routes
    g = gain(S)
    if method == "gain_only":
        order = list(np.argsort(-g)[: K * 8])
        return [order[r::K] for r in range(K)]
    return plan_insert(g, Dblind if method == "gain_blind" else Dtrue)


def execute(routes, S, Dtrue):
    visited = checks = 0
    for r in routes:
        t, pos = 0.0, 0
        for v in r:
            need = Dtrue[pos, v + 1] + C * CHECK_MIN
            if t + need + Dtrue[v + 1, 0] > T_DAY:
                break
            t += need; pos = v + 1; visited += 1
            for _ in range(C):
                est, sd, p = S.estimate()
                q, w = p[v] * (1 - p[v]), S.W[v] ** 2
                v0, v1 = w * q / (S.n[v] + M + 1), w * q / (S.n[v] + M + 2)
                h = int(np.argmax(np.where(S.n[v] < S.Nh[v], v0 - v1, -1)))
                S.label(v, h); checks += 1
    return visited, checks


def one_rep(seed, methods):
    rng = np.random.default_rng(seed)
    fld, e, flooded, wt, wb, sites, th = world(rng)
    Dt, _ = dmat(e, wt, sites); Db, _ = dmat(e, wb, sites)
    Y = rng.random((U, N)) < th[:, None]
    sens, fpr = rng.beta(15, 5, U), rng.beta(2, 22, U)
    f = np.where(Y, rng.random((U, N)) < sens[:, None], rng.random((U, N)) < fpr[:, None])
    truth = Y.mean(1) > TAU
    out = {}
    for m in methods:
        S = Survey(Y, f, np.random.default_rng(seed + 7))
        wrong = [float(((S.estimate()[0] > TAU) != truth).mean())]
        vis = chk = 0
        for _ in range(DAYS):
            a, b = execute(plan(m, S, Dt, Db), S, Dt); vis += a; chk += b
            wrong.append(float(((S.estimate()[0] > TAU) != truth).mean()))
        out[m] = dict(wrong=wrong, visited=vis, checks=chk)
    return out, (fld, e, flooded, sites, th)


def main():
    global T_DAY
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    T_DAY = float(sys.argv[2]) if len(sys.argv) > 2 else T_DAY      # shorter day = travel binds harder
    methods = ["nearest", "gain_only", "gain_blind", "gain_aware"]
    acc = {m: dict(wrong=np.zeros(DAYS + 1), visited=0.0, checks=0.0) for m in methods}
    for r in range(reps):
        o, _ = one_rep(500 + r, methods)
        for m in methods:
            acc[m]["wrong"] += np.array(o[m]["wrong"]) / reps
            acc[m]["visited"] += o[m]["visited"] / reps; acc[m]["checks"] += o[m]["checks"] / reps
    res = {m: dict(wrong=list(map(float, a["wrong"])), visited=a["visited"], checks=a["checks"]) for m, a in acc.items()}
    here = pathlib.Path(__file__).parent
    (here / "routing_results.json").write_text(json.dumps(res, indent=1))
    print(f"wrong-call % after survey days 0..{DAYS} ({K} officers)")
    for m in methods:
        print(f"{m:11s}", " ".join(f"{100 * x:5.1f}" for x in res[m]["wrong"]),
              f" visited={res[m]['visited']:.0f} checks={res[m]['checks']:.0f}")
    assert res["gain_aware"]["wrong"][-1] <= res["nearest"]["wrong"][-1], "aware routing should not lose to nearest"
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        figdir = here.parents[1] / "docs" / "figures"
        fig, ax = plt.subplots(figsize=(6.4, 4))
        for m, lab in (("nearest", "nearest village first"), ("gain_only", "highest gain, ignore travel"),
                       ("gain_blind", "gain/time, flood-blind roads"), ("gain_aware", "gain/time, flood-aware roads (Dijkstra)")):
            ax.plot(range(DAYS + 1), [100 * x for x in res[m]["wrong"]], marker="o", label=m and lab)
        ax.set_xlabel(f"survey days ({K} officers, {int(T_DAY / 60)} h each)"); ax.set_ylabel("wrong 25% calls (%)")
        ax.set_title(f"{U} villages, flooded roads, mean of {reps} runs"); ax.legend(fontsize=8); ax.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(figdir / "route_wrong_vs_days.png", dpi=150)
        # one example: flooded roads + day-1 flood-aware routes
        o, (fld, e, flooded, sites, th) = one_rep(500, [])
        rng = np.random.default_rng(500); _, _, _, wt, wb, _, _ = world(rng)
        Dt, pred = dmat(e, wt, sites)
        Y = rng.random((U, N)) < th[:, None]
        sens, fpr = rng.beta(15, 5, U), rng.beta(2, 22, U)
        f = np.where(Y, rng.random((U, N)) < sens[:, None], rng.random((U, N)) < fpr[:, None])
        S = Survey(Y, f, np.random.default_rng(507))
        routes = plan("gain_aware", S, Dt, Dt)
        xy = lambda n: (n % G, n // G)
        fig, ax = plt.subplots(figsize=(6, 6))
        for (a, b), fl_ in zip(e, flooded):
            ax.plot(*zip(xy(a), xy(b)), color="#2b6cb0" if fl_ else "#cbd5e0", lw=2.2 if fl_ else 0.8, zorder=1)
        ax.scatter(*zip(*[xy(s) for s in sites[1:]]), c=gain(S), cmap="Oranges", s=40, edgecolor="k", lw=.4, zorder=3)
        ax.scatter(*xy(0), marker="s", c="k", s=70, zorder=4)
        for col, r in zip(("#c53030", "#2f855a", "#6b46c1"), routes):
            seq = [0] + [v + 1 for v in r] + [0]
            for a, b in zip(seq[:-1], seq[1:]):
                path, n = [sites[b]], sites[b]
                while n != sites[a]:
                    n = pred[a, n]; path.append(n)
                ax.plot(*zip(*[xy(p) for p in path]), color=col, lw=2.4, zorder=2)
        ax.set_title("Day-1 routes (colour per officer); blue = flooded roads;\nvillage shade = value of a visit"); ax.set_aspect("equal"); ax.axis("off")
        fig.tight_layout(); fig.savefig(figdir / "route_example.png", dpi=150)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
