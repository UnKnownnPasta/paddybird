"""Layer 5 intake: read layers 1 to 4, build the documented synthetic fixture, store field checks
offline, take farmer reports and cross-check a claim against the unit call.

Nothing here runs on import. The tool reads only files (the layer contract), never sibling modules.

Synthetic fixture (used for any part the real artifacts do not provide yet):
  * 12 pseudo insurance units on a 4 x 3 grid of 0.05 degree cells. The coordinates are only a
    drawing frame; the units, fields, roads and scenes are invented and are not a real place.
  * Two map strata per unit (map dry, map flooded) with paddy-area shares W_uh, a calibrated
    prior pi_h = (0.08, 0.75) and shrinkage m = 10, as in research/threshold_alloc/routing_sim.py.
  * 0 to 8 field checks per unit with known inclusion probabilities.
  * A 9 x 7 road lattice; edges over the smooth flood field are flooded (8 times slower).
  * Two officers' day routes from a cheapest-insertion planner (gain per extra minute).
  * Scene IDs start with SYNTH_ so they cannot be mistaken for real Sentinel products.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

TAU = 0.25                  # PMFBY localised-loss share
PRIOR_PI = (0.08, 0.75)     # P(flooded | map dry), P(flooded | map flooded)
M_SHRINK = 10.0
FLOOD_X = 8.0

NOTEBOOKS = pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS = NOTEBOOKS / "artifacts"


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def short_hash(obj: Any, n: int = 16) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(s.encode()).hexdigest()[:n]


# ---------------------------------------------------------------- estimator (always answers)
def stratified_call(W, k, n, prior=PRIOR_PI, m=M_SHRINK, tau=TAU, w_check=None):
    """theta_u = sum_h W_h p_h, p_h = (k_h + m pi_h)/(n_h + m); P_u = Phi((theta-tau)/s).

    k and n may be weighted (Hajek: sum of 1/pi over checks), which is how inclusion
    probabilities enter. Returns theta, s, call, P_u. There is no undecided outcome.
    """
    W, k, n, prior = (np.asarray(a, float) for a in (W, k, n, prior))
    p = (k + m * prior) / (n + m)
    theta = float((W * p).sum())
    var = float((W ** 2 * p * (1 - p) / (n + m + 1)).sum())
    s = math.sqrt(max(var, 1e-12))
    P = _phi((theta - tau) / s)
    return theta, s, ("above" if theta > tau else "below"), P


def beta_update(theta, s, k, n, tau=TAU):
    """Update a unit given only (theta_u, s_u) from layer 3: treat it as a Beta prior with the
    same mean and variance (pseudo count m = theta(1-theta)/s^2 - 1), add k flooded of n checks."""
    theta = min(max(float(theta), 1e-4), 1 - 1e-4)
    m = max(theta * (1 - theta) / max(float(s) ** 2, 1e-8) - 1.0, 1.0)
    a, b = theta * m + k, (1 - theta) * m + (n - k)
    t = a / (a + b)
    sd = math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))
    return t, sd, ("above" if t > tau else "below"), _phi((t - tau) / sd)


# ---------------------------------------------------------------- fixture
@dataclass
class Inputs:
    units: pd.DataFrame                 # unit_id, lon, lat, half (cell half width deg), theta, s, call, P_u, n_checks, [W0, W1, k0, n0, k1, n1]
    roads_nodes: pd.DataFrame           # node, lon, lat
    roads_edges: pd.DataFrame           # a, b, minutes, flooded
    routes: list                        # [{officer, nodes: [...], stops: [unit_id...], minutes}]
    scenes: list                        # [{id, date, sensor}]
    checks: pd.DataFrame                # unit_id, stratum, flooded, pi, officer, ts
    region: dict                        # {name, bbox, event}
    provenance: dict = field(default_factory=dict)   # component -> "real: <path>" or "fixture"
    manifests: dict = field(default_factory=dict)


def make_fixture(seed: int = 0) -> Inputs:
    rng = np.random.default_rng(seed)
    lon0, lat0, cell = 86.30, 20.40, 0.05
    nx, ny = 4, 3
    gx, gy = 9, 7
    # smooth flood field on the road lattice, standardised
    xx, yy = np.meshgrid(np.linspace(0, 1, gx), np.linspace(0, 1, gy))
    fld = np.sin(3.0 * xx + 0.5) * np.cos(2.2 * yy - 0.3) + 0.6 * xx - 0.3 + 0.15 * rng.standard_normal(xx.shape)
    fld = (fld - fld.mean()) / fld.std()
    nodes = pd.DataFrame({"node": np.arange(gx * gy),
                          "lon": lon0 + xx.ravel() * nx * cell, "lat": lat0 + yy.ravel() * ny * cell})
    f = fld.ravel()
    edges = []
    for j in range(gy):
        for i in range(gx):
            a = j * gx + i
            for b in ([a + 1] if i < gx - 1 else []) + ([a + gx] if j < gy - 1 else []):
                fl = bool((f[a] + f[b]) / 2 > 0.6)
                edges.append((a, b, 4.0 * (FLOOD_X if fl else 1.0), fl))
    edges = pd.DataFrame(edges, columns=["a", "b", "minutes", "flooded"])

    rows, checks = [], []
    t0 = datetime(2026, 7, 16, 9, 0, tzinfo=timezone.utc)
    for u in range(nx * ny):
        i, j = u % nx, u // nx
        lon, lat = lon0 + (i + 0.5) * cell, lat0 + (j + 0.5) * cell
        # flood intensity at the unit centre, from the nearest lattice node
        ni = int(round((i + 0.5) / nx * (gx - 1))); nj = int(round((j + 0.5) / ny * (gy - 1)))
        z = fld[nj, ni]
        W1 = float(np.clip(0.18 + 0.12 * z + 0.04 * rng.standard_normal(), 0.02, 0.9))
        W = np.array([1 - W1, W1])
        p_true = np.array([rng.beta(2, 20), rng.beta(15, 5)])
        n_chk = int(rng.integers(0, 9))
        k = np.zeros(2); n = np.zeros(2)
        for c in range(n_chk):
            h = int(rng.random() < 0.5)
            pi = float(np.clip(0.2 + 0.6 * W[h], 0.05, 0.95))       # known inclusion probability
            y = bool(rng.random() < p_true[h])
            w = 1.0 / pi
            wn = w / (1.0 / 0.5)                                    # Hajek weights normalised to mean about 1
            k[h] += wn * y; n[h] += wn
            checks.append(dict(unit_id=f"U{u + 1:02d}", stratum=h, flooded=y, pi=round(pi, 3),
                               officer=f"officer {1 + c % 2}", ts=(t0 + timedelta(hours=3 * c + u)).isoformat()))
        theta, s, call, P = stratified_call(W, k, n)
        rows.append(dict(unit_id=f"U{u + 1:02d}", name=f"Unit {u + 1:02d}", lon=lon, lat=lat, half=cell / 2,
                         theta=theta, s=s, call=call, P_u=P, n_checks=n_chk,
                         W0=W[0], W1=W[1], k0=k[0], n0=n[0], k1=k[1], n1=n[1],
                         paddy_ha=float(rng.integers(300, 1500))))
    units = pd.DataFrame(rows)
    scenes = [dict(id="SYNTH_S1A_IW_GRDH_20260604_DRY", date="2026-06-04", sensor="Sentinel-1 VV (synthetic)"),
              dict(id="SYNTH_S1A_IW_GRDH_20260710_WET", date="2026-07-10", sensor="Sentinel-1 VV (synthetic)"),
              dict(id="SYNTH_S1A_IW_GRDH_20260722_WET", date="2026-07-22", sensor="Sentinel-1 VV (synthetic)")]
    inp = Inputs(units=units, roads_nodes=nodes, roads_edges=edges, routes=[], scenes=scenes,
                 checks=pd.DataFrame(checks),
                 region=dict(name="Synthetic fixture district (not a real place)",
                             bbox=[lon0, lat0, lon0 + nx * cell, lat0 + ny * cell], event="synthetic flood, July 2026"))
    inp.routes = plan_routes(inp, n_officers=2, day_minutes=240.0)
    inp.provenance = {k: "fixture" for k in ("units", "roads", "routes", "scenes", "checks")}
    return inp


def _dijkstra(nodes: pd.DataFrame, edges: pd.DataFrame, sources):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    nn = len(nodes)
    A = coo_matrix((edges.minutes.to_numpy(float), (edges.a.to_numpy(int), edges.b.to_numpy(int))), shape=(nn, nn))
    return dijkstra(A, directed=False, indices=sources, return_predecessors=True)


def nearest_node(nodes: pd.DataFrame, lon, lat) -> int:
    d = (nodes.lon - lon) ** 2 + (nodes.lat - lat) ** 2
    return int(nodes.node.iloc[int(np.argmin(d.to_numpy()))])


def path_nodes(pred, src_idx, src_node, dst_node):
    out, n = [dst_node], dst_node
    while n != src_node and n >= 0:
        n = int(pred[src_idx, n]); out.append(n)
    return out[::-1]


def plan_routes(inp: Inputs, n_officers=2, day_minutes=240.0, check_minutes=18.0, depot_node=0):
    """Fallback planner for the fixture only (layer 4 owns real routes): cheapest insertion by
    value of a visit (probability the call is wrong) per extra minute on the flood-aware graph."""
    u = inp.units
    sites = [depot_node] + [nearest_node(inp.roads_nodes, r.lon, r.lat) for r in u.itertuples()]
    dist, pred = _dijkstra(inp.roads_nodes, inp.roads_edges, sites)
    D = dist[:, sites]
    g = np.minimum(u.P_u, 1 - u.P_u).to_numpy()
    routes, tm, left = [[] for _ in range(n_officers)], [0.0] * n_officers, set(range(len(u)))
    while left:
        best = None
        for v in left:
            for r in range(n_officers):
                rt = routes[r]
                for pos in range(len(rt) + 1):
                    a = 0 if pos == 0 else rt[pos - 1] + 1
                    b = 0 if pos == len(rt) else rt[pos] + 1
                    dt = D[a, v + 1] + D[v + 1, b] - D[a, b] + check_minutes
                    if tm[r] + dt <= day_minutes and (best is None or g[v] / dt > best[0]):
                        best = (g[v] / dt, v, r, pos, dt)
        if best is None:
            break
        _, v, r, pos, dt = best
        routes[r].insert(pos, v); tm[r] += dt; left.discard(v)
    out = []
    for r, rt in enumerate(routes):
        seq = [0] + [v + 1 for v in rt] + [0]
        nodes = [sites[0]]
        for a, b in zip(seq[:-1], seq[1:]):
            nodes += path_nodes(pred, a, sites[a], sites[b])[1:]
        out.append(dict(officer=f"officer {r + 1}", nodes=[int(x) for x in nodes],
                        stops=[str(u.unit_id.iloc[v]) for v in rt], minutes=float(round(tm[r], 1))))
    return out


# ---------------------------------------------------------------- real artifacts (best effort, by file)
_SYN = {
    "unit_id": ["unit_id", "unit", "uid", "village", "village_id", "id"],
    "theta": ["theta_u", "theta", "theta_hat", "estimate", "share"],
    "s": ["s_u", "sd_u", "se_u", "sd", "se", "s"],
    "var": ["var_u", "var"],
    "P_u": ["P_u", "p_u", "p_above", "prob_above", "P"],
    "call": ["call_u", "call", "above"],
    "n_checks": ["n_checks", "checks", "n_u", "n_labels", "n"],
    "lon": ["lon", "x", "cx", "lon_c", "centroid_lon"],
    "lat": ["lat", "y", "cy", "lat_c", "centroid_lat"],
}


def _pick(df: pd.DataFrame, key: str) -> Optional[str]:
    low = {c.lower(): c for c in df.columns}
    for c in _SYN[key]:
        if c.lower() in low:
            return low[c.lower()]
    return None


def _read_table(p: pathlib.Path) -> Optional[pd.DataFrame]:
    try:
        if p.suffix == ".parquet":
            return pd.read_parquet(p)
        if p.suffix == ".csv":
            return pd.read_csv(p)
        if p.suffix == ".json":
            obj = json.loads(p.read_text())
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                return pd.DataFrame(obj)
            if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
                return pd.DataFrame([f.get("properties", {}) for f in obj["features"]])
    except Exception:
        return None
    return None


def _tables(d: pathlib.Path):
    if not d.exists():
        return []
    files = [p for p in sorted(d.rglob("*")) if p.suffix in (".parquet", ".csv", ".json") and p.name != "MANIFEST.json"]
    return [(p, t) for p in files if (t := _read_table(p)) is not None and len(t)]


def read_manifests(art: pathlib.Path = ARTIFACTS) -> dict:
    out = {}
    for n in range(1, 5):
        mp = art / f"layer{n}" / "MANIFEST.json"
        if mp.exists():
            try:
                out[f"layer{n}"] = json.loads(mp.read_text())
            except Exception as exc:
                out[f"layer{n}"] = {"error": repr(exc)}
    return out


def _real_units(art: pathlib.Path):
    """A layer-3 table with a unit id and either P_u or theta (with s or var)."""
    for p, t in _tables(art / "layer3"):
        uid, th = _pick(t, "unit_id"), _pick(t, "theta")
        if uid is None or th is None:
            continue
        s = _pick(t, "s"); var = _pick(t, "var"); P = _pick(t, "P_u")
        if s is None and var is None and P is None:
            continue
        df = pd.DataFrame({"unit_id": t[uid].astype(str), "theta": t[th].astype(float)})
        if s is not None:
            df["s"] = t[s].astype(float)
        elif var is not None:
            df["s"] = np.sqrt(t[var].astype(float).clip(lower=1e-12))
        else:   # recover s from P_u
            from scipy.stats import norm
            z = norm.ppf(t[P].astype(float).clip(1e-6, 1 - 1e-6))
            df["s"] = ((df.theta - TAU) / np.where(np.abs(z) < 1e-6, 1e-6, z)).abs().clip(lower=1e-4)
        df["P_u"] = t[P].astype(float) if P is not None else [_phi((a - TAU) / b) for a, b in zip(df.theta, df.s)]
        df["call"] = np.where(df.theta > TAU, "above", "below")
        nc = _pick(t, "n_checks")
        df["n_checks"] = t[nc].fillna(0).astype(int) if nc is not None else 0
        for k in ("lon", "lat"):
            c = _pick(t, k)
            if c is not None:
                df[k] = t[c].astype(float)
        for extra in ("name", "split", "region"):
            if extra in t.columns:
                df[extra] = t[extra].values
        return df, p
    return None, None


def _unit_coords(art: pathlib.Path, ids=None):
    """Unit centres from layer 1; the table sharing most unit IDs with layer 3 wins."""
    best = (0, None, None)
    for p, t in _tables(art / "layer1"):
        uid, lo, la = _pick(t, "unit_id"), _pick(t, "lon"), _pick(t, "lat")
        if uid and lo and la and "unit" in p.name.lower():
            xy = t[[uid, lo, la]].rename(columns={uid: "unit_id", lo: "lon", la: "lat"}).astype({"unit_id": str})
            hit = len(set(xy.unit_id) & set(ids)) if ids is not None else len(xy)
            if hit > best[0]:
                best = (hit, xy, p)
    return best[1], best[2]


def _real_scenes(art: pathlib.Path):
    for n in (1, 2, 3):
        d = art / f"layer{n}"
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.json")):
            try:
                obj = json.loads(p.read_text())
            except Exception:
                continue
            cands = []
            if isinstance(obj, dict):
                for key in ("scenes", "scene_ids", "items"):
                    if key in obj:
                        cands = obj[key]
                        break
                if not cands and isinstance(obj.get("sources"), dict):
                    cands = obj["sources"].get("scenes", [])
            elif isinstance(obj, list) and obj and isinstance(obj[0], dict) and "id" in obj[0]:
                cands = obj
            out = []
            for s in cands or []:
                if isinstance(s, str):
                    out.append(dict(id=s, date="", sensor=""))
                elif isinstance(s, dict) and ("id" in s or "scene_id" in s):
                    out.append(dict(id=str(s.get("id", s.get("scene_id"))), date=str(s.get("date", s.get("datetime", "")))[:10],
                                    sensor=str(s.get("sensor", s.get("collection", "")))))
            if out:
                return out, p
    return None, None


def _real_routes(art: pathlib.Path):
    """layer4 routes: json list/dict with per-officer node or stop sequences, plus road nodes/edges."""
    d = art / "layer4"
    nodes = edges = routes = None
    srcs = []
    if not d.exists():
        return None
    for p, t in _tables(art / "layer1") + _tables(d):
        cols = {c.lower() for c in t.columns}
        if {"a", "b"} <= cols or {"u", "v"} <= cols or {"src", "dst"} <= cols:
            ren = {"u": "a", "v": "b", "src": "a", "dst": "b"}
            e = t.rename(columns={c: ren.get(c.lower(), c.lower()) for c in t.columns})
            if "minutes" not in e.columns:
                tc = next((c for c in e.columns if c in ("base_min", "time", "time_min", "cost", "weight", "w", "t")), None)
                e["minutes"] = e[tc].astype(float) if tc else 1.0
            if "flooded" not in e.columns:
                pc = next((c for c in e.columns if c in ("p_edge", "p_flood", "p_flooded")), None)
                e["flooded"] = (e[pc].astype(float) > 0.5) if pc else False
            edges = e[["a", "b", "minutes", "flooded"]].astype({"a": int, "b": int, "flooded": bool}); srcs.append(p)
        elif ("node" in cols or "node_id" in cols) and ("lon" in cols or "x" in cols):
            n = t.rename(columns={c: c.lower() for c in t.columns}).rename(columns={"x": "lon", "y": "lat", "node_id": "node"})
            nodes = n[["node", "lon", "lat"]]; srcs.append(p)
    for p in sorted(d.rglob("*.json")):
        if "route" not in p.name.lower():
            continue
        try:
            obj = json.loads(p.read_text())
        except Exception:
            continue
        lst = obj.get("routes", obj) if isinstance(obj, dict) else obj
        if isinstance(lst, dict):
            lst = [dict(officer=str(k), **(v if isinstance(v, dict) else {"stops": v})) for k, v in lst.items()]
        if isinstance(lst, list) and lst:
            routes = []
            for i, r in enumerate(lst):
                if isinstance(r, list):
                    r = {"stops": r}
                off = r.get("officer", i + 1)
                routes.append(dict(officer=f"officer {off}" if isinstance(off, int) else str(off),
                                   nodes=[int(x) for x in r.get("node_path", r.get("nodes", r.get("path", [])))],
                                   stops=[str(x) for x in r.get("stops", r.get("units", r.get("villages", [])))],
                                   minutes=r.get("planned_minutes", r.get("minutes", r.get("time", None))),
                                   expected_gain=r.get("expected_gain")))
            srcs.append(p)
            break
    if routes is None:
        return None
    return dict(nodes=nodes, edges=edges, routes=routes, srcs=srcs)


def _real_checks(art: pathlib.Path):
    for p, t in _tables(art / "layer4"):
        if "check" not in p.name.lower():
            continue
        uid = _pick(t, "unit_id")
        if uid is None:
            continue
        df = pd.DataFrame({"unit_id": t[uid].astype(str)})
        for c in ("stratum", "flooded", "pi", "officer", "ts", "label", "y", "inclusion_prob"):
            if c in t.columns:
                df[c] = t[c].values
        if "pi" not in df and "inclusion_prob" in df:
            df["pi"] = df.pop("inclusion_prob")
        if "flooded" not in df:
            for c in ("label", "y"):
                if c in df:
                    df["flooded"] = df.pop(c).astype(bool)
                    break
        if "flooded" not in df:         # planned checks (no outcome yet) are not completed checks
            continue
        return df, p
    return None, None


def load_inputs(art: pathlib.Path = ARTIFACTS, seed: int = 0) -> Inputs:
    """Real artifacts where present, fixture for the rest; inp.provenance says which is which."""
    art = pathlib.Path(art)
    inp = make_fixture(seed)
    inp.manifests = read_manifests(art)
    units, p = _real_units(art)
    if units is not None:
        if "lon" not in units or units.lon.isna().all():
            xy, p1 = _unit_coords(art, set(units.unit_id))
            if xy is not None:
                units = units.drop(columns=[c for c in ("lon", "lat") if c in units]).merge(xy, on="unit_id", how="left")
                if units.lon.notna().all():
                    inp.provenance["unit layout"] = f"real: {p1.relative_to(NOTEBOOKS).as_posix()}"
        sparse = False
        if "lon" in units and units.lon.notna().all() and len(units) > 1:
            xy = units[["lon", "lat"]].to_numpy(float)
            d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1)); np.fill_diagonal(d, np.inf)
            span = max(np.ptp(xy[:, 0]), np.ptp(xy[:, 1]))
            sparse = span > 25 * float(np.median(d.min(1)))     # scattered clusters (e.g. separate chips), not one region
        if "lon" not in units or units.lon.isna().any() or sparse:
            # no usable coordinates: lay the units out on a grid for drawing only (real lon/lat stay in lon_real/lat_real)
            if sparse:
                units = units.rename(columns={"lon": "lon_real", "lat": "lat_real"}).sort_values("unit_id").reset_index(drop=True)
            nx = int(math.ceil(math.sqrt(len(units))))
            units["lon"] = [i % nx for i in range(len(units))]
            units["lat"] = [i // nx for i in range(len(units))]
            units["half"] = 0.5
            units["schematic"] = True
            inp.region = dict(name="Layer 3 units (schematic layout)", bbox=[-0.5, -0.5, nx - 0.5, len(units) // nx + 0.5],
                              event="see layer manifests")
            inp.provenance["unit layout"] = ("schematic grid (units are scattered clusters; real lon/lat kept in lon_real, lat_real)"
                                             if sparse else "schematic grid (no coordinates in artifacts)")
        else:
            span = max(units.lon.max() - units.lon.min(), units.lat.max() - units.lat.min(), 1e-3)
            units["half"] = span / (2 * math.sqrt(len(units)) + 2)
            inp.region = dict(name="Layer 3 units", bbox=[float(units.lon.min()), float(units.lat.min()),
                                                          float(units.lon.max()), float(units.lat.max())], event="see layer manifests")
        if "name" not in units:
            units["name"] = units.unit_id
        inp.units = units
        inp.provenance["units"] = f"real: {p.relative_to(NOTEBOOKS).as_posix()}"
        # fixture roads/routes do not belong to real units: rebuild them over the real layout
        inp.roads_nodes, inp.roads_edges = _lattice_over(units)
        inp.routes = plan_routes(inp)
        inp.provenance["roads"] = "fixture lattice over the unit layout (flooded where nearby units are above tau)"
        inp.provenance["routes"] = "fixture planner over fixture lattice"
        inp.checks = inp.checks.iloc[0:0]
        inp.provenance["checks"] = "none (no layer-4 checks table)"
    sc, p = _real_scenes(art)
    if sc:
        inp.scenes = sc
        inp.provenance["scenes"] = f"real: {p.relative_to(NOTEBOOKS).as_posix()}"
    rr = _real_routes(art)
    # layer-4 routes are used only when they visit the same units the table shows (same population)
    linked = rr is not None and bool(rr["routes"]) and \
        set(s for r in rr["routes"] for s in r["stops"]) <= set(inp.units.unit_id)
    if linked:
        src = ", ".join(q.relative_to(NOTEBOOKS).as_posix() for q in rr["srcs"])
        nodes_ok = rr["nodes"] is not None and rr["edges"] is not None and \
            set(n for r in rr["routes"] for n in r["nodes"]) <= set(rr["nodes"].node)
        if nodes_ok:
            inp.roads_nodes, inp.roads_edges, inp.routes = rr["nodes"], rr["edges"], rr["routes"]
            inp.provenance["roads"] = f"real: {src}"
            inp.provenance["routes"] = f"real: {src}"
        else:
            inp.routes = [dict(r, nodes=[]) for r in rr["routes"]]
            inp.provenance["routes"] = f"real stops: {src} (no matching road geometry; drawn stop to stop)"
    elif rr is not None and rr["routes"]:
        inp.provenance["routes"] += " (layer-4 routes_day1 visits other units than layer 3 shows, so not used)"
    ch, p = _real_checks(art)
    if ch is not None:
        inp.checks = ch
        inp.provenance["checks"] = f"real: {p.relative_to(NOTEBOOKS).as_posix()}"
    rj = art / "layer1" / "region.json"
    if rj.exists():
        try:
            inp.region["layer1_region"] = json.loads(rj.read_text())
        except Exception:
            pass
    # what each upstream layer says about its own input (a real file can hold synthetic content)
    for k, m in inp.manifests.items():
        note = m.get("input_source", m.get("input"))
        if isinstance(note, dict):
            note = note.get("source", json.dumps(note)[:120])
        if note is None and isinstance(m.get("sources"), dict):
            note = ", ".join(f"{a}: {b}" for a, b in m["sources"].items())
        inp.provenance[f"{k} says"] = str(note)[:160] if note is not None else "no input note"
    return inp


def _lattice_over(units: pd.DataFrame, g: int = 8, seed: int = 1):
    rng = np.random.default_rng(seed)
    x0, x1, y0, y1 = units.lon.min(), units.lon.max(), units.lat.min(), units.lat.max()
    pad = 0.08 * max(x1 - x0, y1 - y0, 1e-3)
    xs, ys = np.linspace(x0 - pad, x1 + pad, g), np.linspace(y0 - pad, y1 + pad, g)
    XX, YY = np.meshgrid(xs, ys)
    nodes = pd.DataFrame({"node": np.arange(g * g), "lon": XX.ravel(), "lat": YY.ravel()})
    # a node is wet if the nearest unit is estimated above the threshold (stand-in for a flood map)
    th = units.theta.to_numpy()
    near = np.array([th[int(np.argmin((units.lon - x) ** 2 + (units.lat - y) ** 2))] for x, y in zip(nodes.lon, nodes.lat)])
    wet = near >= min(TAU, float(np.quantile(near, 0.7)))
    edges = []
    for j in range(g):
        for i in range(g):
            a = j * g + i
            for b in ([a + 1] if i < g - 1 else []) + ([a + g] if j < g - 1 else []):
                fl = bool(wet[a] and wet[b] and rng.random() < 0.7)
                edges.append((a, b, 4.0 * (FLOOD_X if fl else 1.0), fl))
    return nodes, pd.DataFrame(edges, columns=["a", "b", "minutes", "flooded"])


# ---------------------------------------------------------------- offline field-check entry
@dataclass
class FieldCheck:
    unit_id: str
    plot_id: str
    flooded: bool
    officer: str
    stratum: int = 1            # 0 map dry, 1 map flooded
    pi: float = 0.5             # known inclusion probability of this plot
    lon: Optional[float] = None
    lat: Optional[float] = None
    photo: Optional[str] = None
    ts: str = ""

    def record(self) -> dict:
        d = asdict(self)
        if not d["ts"]:
            d["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        d["entry_hash"] = short_hash({k: v for k, v in d.items() if k != "ts"})
        return d


class OfflineCheckStore:
    """Append-only JSONL on the device. Works with no network; sync() merges, dropping duplicates
    by entry_hash so a re-sent phone queue cannot double count a plot."""

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, chk: FieldCheck) -> dict:
        if not 0 < chk.pi <= 1:
            raise ValueError("inclusion probability must be in (0, 1]")
        rec = chk.record()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    def pending(self) -> list:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def clear(self):
        if self.path.exists():
            self.path.unlink()

    def sync(self, checks: pd.DataFrame) -> pd.DataFrame:
        new = pd.DataFrame(self.pending())
        if new.empty:
            return checks
        allc = pd.concat([checks, new], ignore_index=True)
        if "entry_hash" in allc:
            has = allc.entry_hash.notna()
            allc = pd.concat([allc[~has], allc[has].drop_duplicates("entry_hash", keep="first")], ignore_index=True)
        return allc


def apply_checks(units: pd.DataFrame, new_checks: pd.DataFrame, tau: float = TAU) -> pd.DataFrame:
    """Live update after sync. Strata-aware when layer-3 strata are known (W0, W1, k*, n*),
    otherwise a Beta update of (theta, s). Each check is weighted by 1/pi (normalised so pi=0.5 is 1)."""
    out = units.copy()
    if new_checks is None or new_checks.empty:
        return out
    for uid, g in new_checks.groupby("unit_id"):
        idx = out.index[out.unit_id == uid]
        if not len(idx):
            continue
        i = idx[0]
        w = 0.5 / g.pi.astype(float).clip(lower=0.01)
        y = g.flooded.astype(bool).astype(float)
        if {"W0", "W1", "k0", "n0", "k1", "n1"} <= set(out.columns):
            k = np.array([out.at[i, "k0"], out.at[i, "k1"]], float)
            n = np.array([out.at[i, "n0"], out.at[i, "n1"]], float)
            for h in (0, 1):
                m = g.stratum.astype(int).to_numpy() == h
                k[h] += float((w[m] * y[m]).sum()); n[h] += float(w[m].sum())
            th, s, call, P = stratified_call([out.at[i, "W0"], out.at[i, "W1"]], k, n, tau=tau)
            out.loc[i, ["k0", "k1", "n0", "n1"]] = [k[0], k[1], n[0], n[1]]
        else:
            th, s, call, P = beta_update(out.at[i, "theta"], out.at[i, "s"], float((w * y).sum()), float(w.sum()), tau=tau)
        out.loc[i, ["theta", "s", "call", "P_u"]] = [th, s, call, P]
        out.loc[i, "n_checks"] = int(out.at[i, "n_checks"]) + len(g)
    return out


# ---------------------------------------------------------------- farmer reports and cross-check
@dataclass
class FarmerReport:
    unit_id: str
    farmer_ref: str             # stored only as a hash
    plot_ha: float
    loss_date: str              # YYYY-MM-DD
    reported_at: str            # ISO timestamp
    claim: str = "flooded"
    lon: Optional[float] = None
    lat: Optional[float] = None
    map_stratum: Optional[int] = None   # map class at the plot (0 mapped dry, 1 mapped flooded), from layer 2

    def record(self) -> dict:
        d = asdict(self)
        d["farmer_ref"] = short_hash({"farmer": self.farmer_ref}, 12)
        hrs = (datetime.fromisoformat(self.reported_at.replace("Z", "+00:00")).replace(tzinfo=None)
               - datetime.fromisoformat(self.loss_date)).total_seconds() / 3600
        d["hours_after_loss"] = round(hrs, 1)
        d["within_72h"] = bool(0 <= hrs <= 72)
        d["report_hash"] = short_hash(d)
        return d


def cross_check(report: dict, unit_row, pixel_p: Optional[float] = None, min_plot_ha: float = 0.5) -> dict:
    """Is this claim consistent with the radar? Always returns a lean, never 'undecided'.

    p_flooded = local map probability if given, else the unit's estimated share theta_u.
    Consistency = P(plot flooded) for a 'flooded' claim. A plot under min_plot_ha is still given
    a lean, marked low weight, because the 10 m radar cannot resolve it on its own.
    The result orders inspections; it never rejects a claim.
    """
    h = report.get("map_stratum")
    if pixel_p is not None:
        p, basis = float(pixel_p), "map probability at the plot"
    elif h is not None and all(f"{a}{int(h)}" in unit_row for a in ("k", "n")):
        prior = PRIOR_PI[int(h)]
        p = (float(unit_row[f"k{int(h)}"]) + M_SHRINK * prior) / (float(unit_row[f"n{int(h)}"]) + M_SHRINK)
        basis = f"checked rate in the plot's map stratum ({('mapped dry', 'mapped flooded')[int(h)]})"
    elif h is not None:
        p, basis = PRIOR_PI[int(h)], "calibrated prior of the plot's map stratum"
    else:
        p, basis = float(unit_row["theta"]), "unit flooded share theta_u (no plot location)"
    consistent_prob = p if report.get("claim", "flooded") == "flooded" else 1 - p
    lean = "consistent with radar" if consistent_prob >= 0.5 else "inconsistent with radar"
    small = float(report.get("plot_ha", 0)) < min_plot_ha
    priority = (1 - consistent_prob) * (0.5 if small else 1.0) + (0.0 if report.get("within_72h", True) else 0.1)
    return dict(report_hash=report.get("report_hash"), unit_id=report["unit_id"], claim=report.get("claim", "flooded"),
                unit_call=unit_row["call"], unit_P_u=round(float(unit_row["P_u"]), 3),
                p_flooded_used=round(p, 3), basis=basis, consistent_prob=round(consistent_prob, 3), lean=lean,
                weight="low (plot below radar resolution)" if small else "normal",
                within_72h=report.get("within_72h"), inspect_priority=round(priority, 3),
                note="Orders inspections; does not reject a claim. Self-selected reports do not enter theta_u here.")
