"""Layer 1 road graph: OpenStreetMap roads for a bbox (osmnx if installed, else the Overpass API directly),
simplified to intersections, with a documented synthetic lattice fallback. No side effects on import.

Graph format (what layer 4 reads):
    nodes: node_id (0..N-1), osm_id (or -1), lon, lat, x_km, y_km (local plane, origin at bbox south-west)
    edges: u, v (node_id, undirected, u < v), length_km, highway, speed_kmh, base_min (dry travel time)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional

import numpy as np

OVERPASS = "https://overpass-api.de/api/interpreter"
DRIVABLE = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
            "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "living_street",
            "service", "track", "road")
# Assumed rural Indian travel speeds (km/h) by OSM class; officers drive two-wheelers or jeeps.
SPEED_KMH = {"motorway": 60, "trunk": 50, "primary": 45, "secondary": 40, "tertiary": 32, "unclassified": 25,
             "residential": 20, "living_street": 15, "service": 15, "track": 12, "road": 20}


def _speed(hw: str) -> float:
    return float(SPEED_KMH.get(hw.replace("_link", ""), 20))


def _haversine_km(lon1, lat1, lon2, lat2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def _local_xy(lon, lat, bbox):
    w, s = bbox[0], bbox[1]
    lat0 = (bbox[1] + bbox[3]) / 2
    return (np.asarray(lon) - w) * 111.32 * math.cos(math.radians(lat0)), (np.asarray(lat) - s) * 110.57


def fetch_overpass(bbox: tuple[float, float, float, float], timeout: int = 120) -> dict[str, Any]:
    """Raw Overpass JSON for drivable ways in a lon/lat bbox (south, west, north, east order in the query)."""
    import httpx
    w, s, e, n = bbox
    q = (f'[out:json][timeout:{timeout}];way["highway"~"^({"|".join(DRIVABLE)})$"]({s},{w},{n},{e});'
         "(._;>;);out body;")
    r = httpx.post(OVERPASS, data={"data": q}, timeout=timeout + 30,
                   headers={"User-Agent": "paddybird-notebooks/0.1 (academic mini project)"})
    r.raise_for_status()
    return r.json()


def graph_from_overpass(osm: dict[str, Any], bbox) -> tuple[list[dict], list[dict]]:
    """Simplify OSM ways to a graph whose nodes are intersections and way ends; keep the largest component."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    pts = {el["id"]: (el["lon"], el["lat"]) for el in osm["elements"] if el["type"] == "node"}
    ways = [el for el in osm["elements"] if el["type"] == "way" and len(el.get("nodes", [])) >= 2]
    use: dict[int, int] = {}
    for wy in ways:
        for nd in wy["nodes"]:
            use[nd] = use.get(nd, 0) + 1
    keep = {nd for nd, c in use.items() if c > 1} | {wy["nodes"][0] for wy in ways} | {wy["nodes"][-1] for wy in ways}
    raw: dict[tuple[int, int], tuple[float, str]] = {}
    for wy in ways:
        hw = wy.get("tags", {}).get("highway", "road")
        seq = [nd for nd in wy["nodes"] if nd in pts]
        start, acc = seq[0], 0.0
        for a, b in zip(seq[:-1], seq[1:]):
            acc += float(_haversine_km(*pts[a], *pts[b]))
            if b in keep:
                if b != start:
                    k = (min(start, b), max(start, b))
                    if k not in raw or raw[k][0] > acc:
                        raw[k] = (acc, hw)
                start, acc = b, 0.0
    ids = sorted({x for k in raw for x in k})
    idx = {o: i for i, o in enumerate(ids)}
    e = np.array([(idx[a], idx[b]) for a, b in raw], int).reshape(-1, 2)
    if len(e) == 0:
        raise ValueError("no roads in bbox")
    A = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(ids), len(ids)))
    _, lab = connected_components(A, directed=False)
    big = np.bincount(lab).argmax()
    keep_nodes = [o for o in ids if lab[idx[o]] == big]
    new = {o: i for i, o in enumerate(keep_nodes)}
    lon = np.array([pts[o][0] for o in keep_nodes]); lat = np.array([pts[o][1] for o in keep_nodes])
    x, y = _local_xy(lon, lat, bbox)
    nodes = [{"node_id": i, "osm_id": int(o), "lon": float(lon[i]), "lat": float(lat[i]),
              "x_km": float(x[i]), "y_km": float(y[i])} for i, o in enumerate(keep_nodes)]
    edges = []
    for (a, b), (L, hw) in sorted(raw.items()):
        if a in new and b in new:
            L = max(L, 0.005)
            sp = _speed(hw)
            u, v = sorted((new[a], new[b]))
            edges.append({"u": u, "v": v, "length_km": L, "highway": hw, "speed_kmh": sp, "base_min": 60 * L / sp})
    return nodes, edges


def synthetic_road_graph(bbox, spacing_km: float = 0.7, drop: float = 0.15, seed: int = 0) -> tuple[list[dict], list[dict]]:
    """SYNTHETIC fallback: a jittered lattice over the bbox with some links removed (rural gaps), every
    4th row and column as a 'secondary' road, the rest 'unclassified'. Largest component kept."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    rng = np.random.default_rng(seed)
    lat0 = (bbox[1] + bbox[3]) / 2
    W = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians(lat0)); H = (bbox[3] - bbox[1]) * 110.57
    nx, ny = int(W / spacing_km) + 1, int(H / spacing_km) + 1
    xs = np.array([(j * spacing_km, i * spacing_km) for i in range(ny) for j in range(nx)], float)
    xs += rng.normal(0, spacing_km * 0.15, xs.shape)
    e, hw = [], []
    for a in range(nx * ny):
        i, j = divmod(a, nx)
        for b, main in ((a + 1 if j < nx - 1 else -1, i % 4 == 0), (a + nx if i < ny - 1 else -1, j % 4 == 0)):
            if b >= 0 and (main or rng.random() > drop):
                e.append((a, b)); hw.append("secondary" if main else "unclassified")
    e = np.array(e)
    A = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nx * ny, nx * ny))
    _, lab = connected_components(A, directed=False)
    big = np.bincount(lab).argmax()
    keep = np.flatnonzero(lab == big)
    new = {int(o): i for i, o in enumerate(keep)}
    nodes = []
    for o, i in new.items():
        x, y = xs[o]
        nodes.append({"node_id": i, "osm_id": -1, "lon": bbox[0] + x / (111.32 * math.cos(math.radians(lat0))),
                      "lat": bbox[1] + y / 110.57, "x_km": float(x), "y_km": float(y)})
    edges = []
    for (a, b), h in zip(e, hw):
        if int(a) in new and int(b) in new:
            L = float(np.hypot(*(xs[a] - xs[b]))) * rng.uniform(1.0, 1.25)   # roads wind a little
            sp = _speed(h)
            u, v = sorted((new[int(a)], new[int(b)]))
            edges.append({"u": u, "v": v, "length_km": L, "highway": h, "speed_kmh": sp, "base_min": 60 * L / sp})
    return nodes, edges


def load_road_graph(bbox, cache: Path, seed: int = 0, allow_network: bool = True) -> tuple[list[dict], list[dict], str]:
    """Cached OSM extract -> Overpass API -> synthetic. Returns (nodes, edges, source) with
    source in {'osm-overpass', 'synthetic'}. The raw OSM JSON is cached at `cache`."""
    cache = Path(cache)
    if cache.exists():
        d = json.loads(cache.read_text())
        n, e = graph_from_overpass(d["osm"], bbox)
        return n, e, d["source"]
    if allow_network:
        # osmnx is not required: it would issue this same Overpass query; we parse the result ourselves.
        src = "osm-overpass"
        try:
            osm = fetch_overpass(bbox)
            n, e = graph_from_overpass(osm, bbox)
            cache.parent.mkdir(parents=True, exist_ok=True)
            slim = {"elements": [{k: (el[k] if k != "tags" else {"highway": el[k].get("highway", "road")})
                                  for k in ("type", "id", "lon", "lat", "nodes", "tags") if k in el
                                  and (k != "tags" or el["type"] == "way")} for el in osm["elements"]]}
            cache.write_text(json.dumps({"source": src, "bbox": list(bbox), "osm": slim}))
            return n, e, src
        except Exception as exc:  # noqa: BLE001
            print(f"OSM fetch failed ({type(exc).__name__}: {str(exc)[:120]}); using the synthetic road graph")
    n, e = synthetic_road_graph(bbox, seed=seed)
    return n, e, "synthetic"


def nearest_node(nodes: list[dict], lon: np.ndarray, lat: np.ndarray, bbox) -> tuple[np.ndarray, np.ndarray]:
    """Index of the nearest graph node to each point and the straight-line distance in km."""
    nx_ = np.array([[n["x_km"], n["y_km"]] for n in nodes])
    px, py = _local_xy(lon, lat, bbox)
    d = np.hypot(nx_[None, :, 0] - np.asarray(px)[:, None], nx_[None, :, 1] - np.asarray(py)[:, None])
    i = d.argmin(1)
    return i, d[np.arange(len(i)), i]


def travel_minutes(n_nodes: int, edges: list[dict], sources, weight: str = "base_min") -> np.ndarray:
    """Dijkstra travel time (minutes) from each source node to every node on the undirected graph."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    u = np.array([e["u"] for e in edges]); v = np.array([e["v"] for e in edges])
    w = np.array([e[weight] for e in edges], float)
    A = coo_matrix((w, (u, v)), shape=(n_nodes, n_nodes)).tocsr()
    return dijkstra(A, directed=False, indices=np.atleast_1d(sources))
