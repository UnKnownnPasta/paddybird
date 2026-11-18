"""Layer 4 routing: flood-aware road graph, Dijkstra, orienteering by gain per extra minute.

Road graph: nodes with x, y (km); undirected edges with a dry travel time base_min and a
layer-2 probability p_flood that the segment is under water.
Planning costs:
    blind : base_min                                   (the dry road map)
    aware : base_min * (1 + (slow - 1) * p_flood),  and closed (removed) where p_flood >= p_close
Execution (the simulated truth): each segment is flooded with probability p_flood and then takes
slow times its dry time. Officers drive true shortest paths between their planned stops and
turn back to the depot when the next stop no longer fits in the day.

Orienteering heuristic: repeatedly insert the unvisited village with the highest
gain / extra minutes (extra drive + check time) into the cheapest position of any officer's
route while it still fits in the day. Re-plan every morning with updated gains.

Also holds the documented synthetic generator used until layers 1 to 3 write real artifacts.
No side effects on import.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.special import expit, logit

from . import allocation as A
from . import selection as Sel


# ---------------------------------------------------------------- synthetic inputs
def synthetic_region(seed, G=21, U=30, plots=(600, 2400), spacing_km=1.0, m=5.0, tau=0.25):
    """documented stand-in for layers 1 to 3 (one flood event over one block).

    - a G x G lattice of roads, dry time 2 min per segment (x U(0.8, 1.3));
    - a smooth flood field (Gaussian-filtered noise, sd 3 cells); a road segment's layer-2 flood
      probability is expit(2.5 * (field - 0.6));
    - U villages on random nodes, depot at node 0 (block office in a corner);
    - each village has N_u paddy plots with calibrated map probability P = expit(mu_u + 1.8 z),
      mu_u = -1.7 + 0.9 * field(village); map stratum = P > 0.5;
    - calibration prior pi_h = mean P inside each map stratum (what labelled events would give).
    """
    rng = np.random.default_rng(seed)
    fld = gaussian_filter(rng.standard_normal((G, G)), 3)
    fld = (fld - fld.mean()) / fld.std()
    xy = np.array([(j * spacing_km, i * spacing_km) for i in range(G) for j in range(G)], float)
    e = []
    for a in range(G * G):
        i, j = divmod(a, G)
        if j < G - 1:
            e.append((a, a + 1))
        if i < G - 1:
            e.append((a, a + G))
    e = np.array(e)
    fl = fld.ravel()
    mid = (fl[e[:, 0]] + fl[e[:, 1]]) / 2
    base = 2.0 * rng.uniform(0.8, 1.3, len(e))
    p_edge = expit(2.5 * (mid - 0.6))
    unit_node = rng.choice(np.arange(1, G * G), U, replace=False)
    N = rng.integers(plots[0], plots[1] + 1, U)
    P, f = [], []
    for u in range(U):
        mu = -1.7 + 0.9 * fl[unit_node[u]]
        pu = expit(mu + 1.8 * rng.standard_normal(N[u]))
        P.append(pu)
        f.append(pu > 0.5)
    allP, allf = np.concatenate(P), np.concatenate(f)
    pi_h = np.array([allP[~allf].mean(), allP[allf].mean()])
    return dict(source="synthetic", seed=int(seed), xy=xy, edges=e, base_min=base, p_edge=p_edge,
                depot=0, unit_node=unit_node, P=P, f=f, pi_h=pi_h, tau=float(tau), m=float(m),
                unit_id=[f"U{u:03d}" for u in range(U)])


def local_road_flood(region):
    """mean layer-2 flood probability of the road segments touching each village node."""
    e, p = region["edges"], region["p_edge"]
    out = []
    for node in region["unit_node"]:
        sel = (e[:, 0] == node) | (e[:, 1] == node)
        out.append(p[sel].mean() if sel.any() else p.mean())
    return np.array(out)


def draw_truth(region, seed, bias_sd=0.5, bias_road=0.6):
    """one held-out scenario: true plot status and which roads are actually flooded.

    Village map error b_u (logit scale) = bias_road * z_u + bias_sd * noise, where z_u is the
    standardised local road-flood probability: villages behind flooded roads have flooding the
    map under-reads. Mean b_u is ~0, so the calibration prior is right on average, but a sample
    that avoids flooded roads sees a biased rate. Y ~ Bernoulli(expit(logit P + b_u)).
    """
    rng = np.random.default_rng(seed)
    z = local_road_flood(region)
    z = (z - z.mean()) / (z.std() + 1e-9)
    b = bias_road * z + bias_sd * rng.standard_normal(len(z))
    Y = [rng.random(len(P)) < expit(logit(np.clip(P, 1e-6, 1 - 1e-6)) + bu) for P, bu in zip(region["P"], b)]
    flooded_edge = rng.random(len(region["p_edge"])) < region["p_edge"]
    return dict(Y=Y, flooded_edge=flooded_edge, b=b, seed=int(seed))


def load_region(art_dir, seed=4, plot_ha=0.04, paddy_share=0.25, max_plots=3000):
    """planning region from the layer 1 artifacts (+ layer 3 tau and m); None if layer 1 roads are missing.

    Real (layer 1): OSM road nodes and edges with dry minutes, the depot node, grid units over the
    study block and the road node nearest each unit.
    Semi-synthetic (stated in `source`): layer 2 has no flood map over this block (its maps cover
    labelled Sen1Floods11 chips), so the flood layer is drawn here exactly as in synthetic_region:
    a smooth field over the block (Gaussian-filtered noise on a 64 x 64 grid, sd 6 cells),
    p_flood(segment) = expit(2.5 * (field - 0.6)), and per-plot map probability
    P = expit(-1.7 + 0.9 * field(unit) + 1.8 z). Plots per unit = area_ha / 0.04 ha (one 20 m pixel)
    x paddy_share, capped at max_plots. tau and m come from layer 3 (hyper.json) when present;
    pi_h is the mean P per map stratum (calibrated by construction).
    """
    import json, pathlib
    art = pathlib.Path(art_dir)
    l1 = art / "layer1"
    need = [l1 / n for n in ("roads_nodes.parquet", "roads_edges.parquet", "units_grid.parquet", "region.json")]
    if not all(p.exists() for p in need):
        return None
    import pandas as pd
    nodes = pd.read_parquet(need[0]).sort_values("node_id").reset_index(drop=True)
    edges = pd.read_parquet(need[1])
    units = pd.read_parquet(need[2])
    reg = json.loads(need[3].read_text())
    idx = {int(n): i for i, n in enumerate(nodes["node_id"])}
    e = np.array([(idx[int(a)], idx[int(b)]) for a, b in zip(edges["u"], edges["v"])])
    xy = nodes[["x_km", "y_km"]].to_numpy(float)
    rng = np.random.default_rng(seed)
    Gs = 64
    fld = gaussian_filter(rng.standard_normal((Gs, Gs)), 6)
    fld = (fld - fld.mean()) / fld.std()
    lo, hi = xy.min(0), xy.max(0)
    cell = np.clip(((xy - lo) / np.maximum(hi - lo, 1e-9) * (Gs - 1)).round().astype(int), 0, Gs - 1)
    fl = fld[cell[:, 1], cell[:, 0]]
    p_edge = expit(2.5 * ((fl[e[:, 0]] + fl[e[:, 1]]) / 2 - 0.6))
    unit_node = np.array([idx[int(n)] for n in units["node_id"]])
    N = np.clip((units["area_ha"].to_numpy() / plot_ha * paddy_share).round().astype(int), 100, max_plots)
    P, f = [], []
    for u in range(len(units)):
        pu = expit(-1.7 + 0.9 * fl[unit_node[u]] + 1.8 * rng.standard_normal(N[u]))
        P.append(pu)
        f.append(pu > 0.5)
    allP, allf = np.concatenate(P), np.concatenate(f)
    tau, m = 0.25, 5.0
    hyp = art / "layer3" / "hyper.json"
    if hyp.exists():
        h = json.loads(hyp.read_text())
        tau, m = float(h.get("tau", tau)), float(h.get("m", m))
    return dict(source=f"layer1 roads and units ({reg.get('name', 'study block')}); flood layer semi-synthetic",
                seed=int(seed), xy=xy, edges=e, base_min=edges["base_min"].to_numpy(float), p_edge=p_edge,
                depot=idx[int(reg["depot_node"])], unit_node=unit_node, P=P, f=f,
                pi_h=np.array([allP[~allf].mean(), allP[allf].mean()]), tau=tau, m=m,
                unit_id=list(units["unit_id"]), field=fl, name=reg.get("name", ""))


# ---------------------------------------------------------------- graph
def edge_costs(region, mode, slow=8.0, p_close=None, flooded_edge=None):
    base, p = region["base_min"], region["p_edge"]
    if mode == "blind":
        return base.copy()
    if mode == "aware":
        w = base * (1 + (slow - 1) * p)
        if p_close is not None:
            w = np.where(p >= p_close, np.inf, w)
        return w
    if mode == "true":
        return base * np.where(flooded_edge, slow, 1.0)
    raise ValueError(mode)


def shortest(region, w):
    """Dijkstra from the depot and every village; returns (D, pred, sites) with D over sites."""
    e = region["edges"]
    n = len(region["xy"])
    keep = np.isfinite(w)
    A_ = coo_matrix((w[keep], (e[keep, 0], e[keep, 1])), shape=(n, n)).tocsr()
    sites = np.concatenate([[region["depot"]], region["unit_node"]]).astype(int)
    d, pred = dijkstra(A_, directed=False, indices=sites, return_predecessors=True)
    return d[:, sites], pred, sites


def node_path(pred, sites, a, b):
    """node sequence of the shortest path from site a to site b (indices into sites)."""
    path, node = [sites[b]], sites[b]
    while node != sites[a]:
        node = pred[a, node]
        if node < 0:
            return []
        path.append(node)
    return path[::-1]


# ---------------------------------------------------------------- planners
def insertion(score_gain, D, K, t_day, service, mandatory=(), allowed=None):
    """greedy orienteering: mandatory villages first (cheapest insertion), then gain per extra minute."""
    U = D.shape[0] - 1
    routes, tm = [[] for _ in range(K)], [0.0] * K
    left = set(range(U)) if allowed is None else set(int(v) for v in allowed)
    must = [int(v) for v in mandatory if int(v) in left]

    def best_slot(v):
        best = None
        for r in range(K):
            rt = routes[r]
            for pos in range(len(rt) + 1):
                a = 0 if pos == 0 else rt[pos - 1] + 1
                b = 0 if pos == len(rt) else rt[pos] + 1
                dt = D[a, v + 1] + D[v + 1, b] - D[a, b] + service[v]
                if np.isfinite(dt) and tm[r] + dt <= t_day and (best is None or dt < best[0]):
                    best = (dt, r, pos)
        return best

    for v in must:                       # spine villages, cheapest first
        slot = best_slot(v)
        if slot is not None:
            dt, r, pos = slot
            routes[r].insert(pos, v); tm[r] += dt
        left.discard(v)
    left -= set(must)
    while left:
        best = None
        for v in left:
            if score_gain[v] <= 0:
                continue
            slot = best_slot(v)
            if slot is not None:
                ratio = score_gain[v] / max(slot[0], 1e-6)
                if best is None or ratio > best[0]:
                    best = (ratio, v) + slot
        if best is None:
            break
        _, v, dt, r, pos = best
        routes[r].insert(pos, v); tm[r] += dt; left.discard(v)
    return routes


def nearest_first(D_blind, K, t_day, service, visited_ever):
    """baseline: each officer drives to the nearest not-yet-visited village (dry road map)."""
    U = D_blind.shape[0] - 1
    left = [v for v in range(U) if v not in visited_ever] or list(range(U))
    left = set(left)
    routes = []
    for _ in range(K):
        pos, t, r = 0, 0.0, []
        while left:
            v = min(left, key=lambda x: D_blind[pos, x + 1])
            need = D_blind[pos, v + 1] + service[v]
            if t + need + D_blind[v + 1, 0] > t_day:
                break
            r.append(v); left.discard(v); t += need; pos = v + 1
        routes.append(r)
    return routes


def gain_only(g, K, per_officer=10):
    order = [int(v) for v in np.argsort(-g)[: K * per_officer] if g[v] > 0]
    return [order[r::K] for r in range(K)]


def execute(routes, D_true, t_day, service):
    """drive the routes on the true roads; returns per officer the villages reached and drive minutes."""
    done = []
    for r in routes:
        t, drive, pos, got = 0.0, 0.0, 0, []
        for v in r:
            leg = D_true[pos, v + 1]
            if not np.isfinite(leg) or t + leg + service[v] + D_true[v + 1, 0] > t_day:
                break
            t += leg + service[v]; drive += leg; pos = v + 1; got.append(v)
        drive += D_true[pos, 0] if got else 0.0
        done.append(dict(units=got, drive_min=float(drive), day_min=float(t + (D_true[pos, 0] if got else 0.0))))
    return done


# ---------------------------------------------------------------- campaign
PLANNERS = ("nearest", "gain_only", "gain_blind", "gain_aware", "gain_aware_spine")
SPINE_PRIORITIES = ("gain", "size", "size_x_sqrt_gain")


def spine_priority_values(S, C, kind):
    """priority for the spine's inclusion probabilities (all known before any check is made)."""
    if kind == "size":
        return S.N.astype(float)
    g, _ = A.visit_gain(S, C)
    if kind == "gain":
        return g
    if kind == "size_x_sqrt_gain":
        return S.N * np.sqrt(g / max(g.max(), 1e-12) + 0.05)
    raise ValueError(kind)


def run_campaign(region, truth, planner, rng, days=5, K=3, t_day=240.0, C=12, check_min=1.5,
                 slow=8.0, p_close=None, spine_n=4.0, spine_floor=0.05, keep_survey=False,
                 plan_slow=None, frame_margin=0.6, spine_priority="size"):
    """multi-day survey with daily re-plan; every village is answered every day.

    plan_slow: slow factor assumed by the flood-aware planner (defaults to the true `slow`).
    frame_margin: a village is in the spine's sampling frame if its expected round trip plus checks
    on the flood-aware graph takes at most frame_margin * t_day (villages outside cannot be drawn,
    and pooled design estimates refer to the frame only).
    """
    S = A.StratSurvey(truth["Y"], region["f"], region["pi_h"], region["m"], region["tau"], rng)
    above = np.array([y.mean() for y in truth["Y"]]) > region["tau"]
    Dt, _, _ = shortest(region, edge_costs(region, "true", slow, flooded_edge=truth["flooded_edge"]))
    Db, _, _ = shortest(region, edge_costs(region, "blind"))
    Da, _, _ = shortest(region, edge_costs(region, "aware", slow if plan_slow is None else plan_slow, p_close))
    U = S.U
    service = np.full(U, C * check_min)
    rec = dict(wrong=[], brier=[], checks=[0], drive_min=[0.0], visits=[0])
    call, P = S.calls()
    rec["wrong"].append(A.wrong_rate(call, above)); rec["brier"].append(A.brier(P, above))
    visited_ever, spine_left = set(), []
    q = None
    design = dict(k=np.zeros((U, 2)), n=np.zeros((U, 2)))
    # sampling frame: villages an officer can expect to reach and return from in one day, with margin
    frame = (Da[0, 1:] + Da[1:, 0] + service) <= frame_margin * t_day
    if planner == "gain_aware_spine":
        q = np.zeros(U)
        q[frame] = Sel.pps_floor(spine_priority_values(S, C, spine_priority)[frame], spine_n, spine_floor)
        spine = Sel.poisson_draw(q, rng)
        spine_left = list(spine)
    else:
        spine = np.array([], int)
    for day in range(days):
        g, _ = A.visit_gain(S, C)
        if planner == "nearest":
            routes = nearest_first(Db, K, t_day, service, visited_ever)
        elif planner == "gain_only":
            routes = gain_only(g, K)
        elif planner == "gain_blind":
            routes = insertion(g, Db, K, t_day, service)
        elif planner in ("gain_aware", "gain_aware_spine"):
            routes = insertion(g, Da, K, t_day, service, mandatory=spine_left)
        else:
            raise ValueError(planner)
        done = execute(routes, Dt, t_day, service)
        for o in done:
            for v in o["units"]:
                if v in spine_left:                      # design visit: fixed SRS per stratum
                    c_h = Sel.design_split(S.Nh[v] - S.n[v], C)
                    for h in (0, 1):
                        for _ in range(int(c_h[h])):
                            before = S.k[v, h]
                            if S.label(v, h):
                                design["n"][v, h] += 1; design["k"][v, h] += S.k[v, h] - before
                    spine_left.remove(v)
                else:
                    add = A.visit_plan(S, v, C)
                    for h in (0, 1):
                        for _ in range(int(add[h])):
                            S.label(v, h)
                visited_ever.add(v)
        call, P = S.calls()
        rec["wrong"].append(A.wrong_rate(call, above)); rec["brier"].append(A.brier(P, above))
        rec["checks"].append(int(S.n.sum()))
        rec["drive_min"].append(rec["drive_min"][-1] + sum(o["drive_min"] for o in done))
        rec["visits"].append(rec["visits"][-1] + sum(len(o["units"]) for o in done))
    rec["spine"] = dict(q=q, drawn=spine, unreached=list(spine_left), design=design, frame=frame)
    if keep_survey:
        rec["survey"] = S
    return rec
