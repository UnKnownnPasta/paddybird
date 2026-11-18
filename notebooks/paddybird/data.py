"""Layer 1 data: labelled flood chips, event-level splits, STAC search, COG window reads, revisit gaps.

Adapted (copied, not imported) from the earlier prototype and
training/calibration/{fit_water,cache_sen1floods11,kurosiwo_stream}.py.

Chips
    Sen1Floods11 hand-labelled chips (Bonafilia et al. 2020, CC BY 4.0), public Google Cloud bucket.
    Each chip is 512 x 512 at 10 m (sigma0 dB, VV and VH). We put it on the Paddybird working grid
    (2 x 2 mean in linear power -> 20 m, +1 dB sigma0-to-gamma0 shift, as in fit_water.py) and keep
    a centre crop so the committed sample stays small.
    If the bucket cannot be reached and no cached sample exists, `synthetic_chips` makes a clearly
    labelled stand-in with the same array layout (source = "synthetic").

Splits
    Always by flood event (never by chip or tile). The official Sen1Floods11 split mixes chips of one
    event across train/valid/test, so it is NOT used; `event_split` reassigns whole events and
    `assert_no_leakage` checks it.

No network access happens on import.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

# ---------------------------------------------------------------- constants
BUCKET = "https://storage.googleapis.com/sen1floods11/v1.1"
SPLIT_FILES = ("flood_train_data.csv", "flood_valid_data.csv", "flood_test_data.csv", "flood_bolivia_data.csv")
SHIFT_DB = 1.0            # sigma0 -> gamma0 shift used by the calibrated threshold instrument
PIXEL_M = 20.0            # working grid
# Event-level split used by every Paddybird notebook. India (the target domain) and Bolivia (the
# official Sen1Floods11 held-out region) are test; Sri-Lanka (South Asia, close to the target) and
# Ghana are validation; the rest train. Fixed on 2026-11-18, before any model was fit.
DEFAULT_TEST_EVENTS = ("India", "Bolivia")
DEFAULT_VAL_EVENTS = ("Sri-Lanka", "Ghana")


def offline() -> bool:
    """PADDYBIRD_OFFLINE=1 forbids every network call; cached files are used instead."""
    return os.environ.get("PADDYBIRD_OFFLINE", "0") not in ("0", "", "false", "False")


def _get(url: str, timeout: float = 120, retries: int = 3) -> bytes:
    import httpx
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            r = httpx.get(url, timeout=timeout, follow_redirects=True)
            r.raise_for_status()
            return r.content
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"GET failed: {url}: {last!r}")


# ---------------------------------------------------------------- Sen1Floods11
def list_sen1floods11_chips() -> list[dict[str, str]]:
    """All 446 hand-labelled chips. The official split column is kept only for reference."""
    chips, seen = [], set()
    for name in SPLIT_FILES:
        text = _get(f"{BUCKET}/splits/flood_handlabeled/{name}").decode()
        for line in text.strip().splitlines():
            s1, lab = [x.strip() for x in line.split(",")[:2]]
            cid = s1.replace("_S1Hand.tif", "")
            if cid in seen:
                continue
            seen.add(cid)
            chips.append({"chip": cid, "event": s1.split("_")[0], "official_split": name.split("_")[1],
                          "s1": f"{BUCKET}/data/flood_events/HandLabeled/S1Hand/{s1}",
                          "label": f"{BUCKET}/data/flood_events/HandLabeled/LabelHand/{lab}",
                          "jrc": f"{BUCKET}/data/flood_events/HandLabeled/JRCWaterHand/{cid}_JRCWaterHand.tif"})
    return chips


def _read_tif(blob: bytes) -> tuple[np.ndarray, tuple[float, float, float, float], Any]:
    from rasterio.io import MemoryFile
    with MemoryFile(blob) as mf, mf.open() as ds:
        return ds.read().astype("float32"), tuple(ds.bounds), ds.transform


def to_working_grid(db10: np.ndarray, label10: np.ndarray, shift_db: float = SHIFT_DB):
    """10 m sigma0 dB -> 20 m gamma0 dB (mean in linear power); label -> 20 m (water if at least half of
    the labelled sub-pixels are water; -1 where no sub-pixel is labelled). Same as fit_water.py."""
    h, w = (db10.shape[0] // 2) * 2, (db10.shape[1] // 2) * 2
    lin = np.where(np.isfinite(db10[:h, :w]), 10 ** (db10[:h, :w] / 10), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"), _quiet():
        mean = np.nanmean(lin.reshape(h // 2, 2, w // 2, 2), axis=(1, 3))
        out = 10 * np.log10(mean) + shift_db
    out[~np.isfinite(out)] = np.nan
    lab = label10[:h, :w].reshape(h // 2, 2, w // 2, 2)
    labelled = (lab >= 0).sum(axis=(1, 3))
    water = (lab == 1).sum(axis=(1, 3))
    lab20 = np.where(labelled == 0, -1, (water * 2 >= labelled).astype("int8")).astype("int8")
    return out.astype("float32"), lab20


class _quiet:
    def __enter__(self):
        import warnings
        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def __exit__(self, *a):
        self._w.__exit__(*a)


def _fetch_chip(chip: dict[str, str], crop: int, shift_db: float) -> Optional[dict[str, Any]]:
    try:
        s1, b, tf = _read_tif(_get(chip["s1"]))
        lab10 = _read_tif(_get(chip["label"]))[0][0]
        try:
            jrc10 = _read_tif(_get(chip["jrc"]))[0][0]
        except Exception:  # noqa: BLE001
            jrc10 = None
    except Exception as exc:  # noqa: BLE001
        print(f"  failed {chip['chip']}: {type(exc).__name__}"[:160], flush=True)
        return None
    vv, lab = to_working_grid(s1[0], lab10, shift_db)
    vh, _ = to_working_grid(s1[1], lab10, shift_db)
    if jrc10 is not None:
        h, w = (jrc10.shape[0] // 2) * 2, (jrc10.shape[1] // 2) * 2
        jrc = (jrc10[:h, :w].reshape(h // 2, 2, w // 2, 2) > 0).mean(axis=(1, 3)) >= 0.5
        jrc = jrc.astype("int8")
    else:
        jrc = np.full(lab.shape, -1, "int8")
    H, W = lab.shape
    r0, c0 = (H - crop) // 2, (W - crop) // 2
    sl = (slice(r0, r0 + crop), slice(c0, c0 + crop))
    # crop bounds in lon/lat (chips are EPSG:4326); 20 m pixel = 2 native pixels
    x0, y0 = tf * (2 * c0, 2 * r0)
    x1, y1 = tf * (2 * (c0 + crop), 2 * (r0 + crop))
    return {"chip": chip["chip"], "event": chip["event"], "official_split": chip["official_split"],
            "vv": vv[sl].astype("float16"), "vh": vh[sl].astype("float16"), "label": lab[sl], "perm_water": jrc[sl],
            "bounds": (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))}


def build_sen1floods11_sample(out_path: Path, per_event: int = 12, crop: int = 128, seed: int = 0,
                              workers: int = 8, shift_db: float = SHIFT_DB) -> Path:
    """Stream up to `per_event` random chips per event (seeded) and save one compressed npz.
    About 3 MB is streamed per chip; the saved sample is a few MB."""
    if offline():
        raise RuntimeError("PADDYBIRD_OFFLINE is set; refusing to download Sen1Floods11")
    chips = list_sen1floods11_chips()
    rng = np.random.default_rng(seed)
    by: dict[str, list] = {}
    for c in chips:
        by.setdefault(c["event"], []).append(c)
    pick = []
    for ev in sorted(by):
        cs = sorted(by[ev], key=lambda c: c["chip"])
        idx = rng.permutation(len(cs))[:per_event]
        pick += [cs[i] for i in sorted(idx)]
    with ThreadPoolExecutor(workers) as pool:
        rows = [r for r in pool.map(lambda c: _fetch_chip(c, crop, shift_db), pick) if r is not None]
    rows.sort(key=lambda r: r["chip"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path, chip=np.array([r["chip"] for r in rows]), event=np.array([r["event"] for r in rows]),
        official_split=np.array([r["official_split"] for r in rows]),
        vv=np.stack([r["vv"] for r in rows]), vh=np.stack([r["vh"] for r in rows]),
        label=np.stack([r["label"] for r in rows]), perm_water=np.stack([r["perm_water"] for r in rows]),
        bounds=np.array([r["bounds"] for r in rows], "float64"),
        source=np.array("sen1floods11"),
        meta=np.array(json.dumps({"dataset": "Sen1Floods11 v1.1 hand-labelled", "license": "CC BY 4.0",
                                  "bucket": BUCKET, "per_event": per_event, "crop_px": crop, "pixel_m": PIXEL_M,
                                  "shift_db": shift_db, "seed": seed,
                                  "grid": "10 m sigma0 dB -> 2x2 linear mean -> 20 m gamma0 dB, centre crop"})))
    return out_path


def synthetic_chips(n_events: int = 8, per_event: int = 10, size: int = 128, seed: int = 0) -> dict[str, np.ndarray]:
    """Clearly labelled SYNTHETIC stand-in with the Sen1Floods11 sample layout.

    Water = smooth Gaussian field above an event-specific level; VV ~ N(-19, 2) dB on water and
    N(-9, 2.5) dB on land, VH = VV - 7 dB +- 1.5; each event has its own backscatter offset
    (domain shift) so event-level splits matter. 2 % of pixels are unlabelled (-1)."""
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(seed)
    out: dict[str, list] = {k: [] for k in ("chip", "event", "official_split", "vv", "vh", "label", "perm_water", "bounds")}
    for e in range(n_events):
        ev = f"Synth{chr(65 + e)}"
        off = rng.normal(0, 1.2)
        level = rng.uniform(0.2, 1.0)
        lon0, lat0 = rng.uniform(-60, 100), rng.uniform(-20, 30)
        for k in range(per_event):
            f = gaussian_filter(rng.standard_normal((size, size)), 6)
            f = (f - f.mean()) / (f.std() + 1e-9)
            water = f > level + rng.normal(0, 0.4)
            perm = f > level + 1.6
            vv = np.where(water, rng.normal(-19, 2, f.shape), rng.normal(-9, 2.5, f.shape)) + off
            vh = vv - 7 + rng.normal(0, 1.5, f.shape)
            lab = water.astype("int8")
            lab[rng.random(f.shape) < 0.02] = -1
            d = size * PIXEL_M / 111_000
            out["chip"].append(f"{ev}_{k:04d}")
            out["event"].append(ev)
            out["official_split"].append("none")
            out["vv"].append(vv.astype("float16"))
            out["vh"].append(vh.astype("float16"))
            out["label"].append(lab)
            out["perm_water"].append(perm.astype("int8"))
            out["bounds"].append((lon0 + k * d, lat0, lon0 + (k + 1) * d, lat0 + d))
    arrs = {k: np.array(v) if k in ("chip", "event", "official_split") else np.stack(v) for k, v in out.items()}
    arrs["bounds"] = arrs["bounds"].astype("float64")
    arrs["source"] = np.array("synthetic")
    arrs["meta"] = np.array(json.dumps({"dataset": "SYNTHETIC stand-in (not real data)", "seed": seed, "pixel_m": PIXEL_M}))
    return arrs


def load_chips(cache: Path, allow_download: bool = True, per_event: int = 12, crop: int = 128,
               seed: int = 0) -> dict[str, np.ndarray]:
    """Cached real sample -> download real sample -> synthetic fallback, in that order.
    The returned dict has key 'source' set to 'sen1floods11' or 'synthetic'."""
    cache = Path(cache)
    if not cache.exists() and allow_download and not offline():
        try:
            build_sen1floods11_sample(cache, per_event=per_event, crop=crop, seed=seed)
        except Exception as exc:  # noqa: BLE001
            print(f"Sen1Floods11 download failed ({type(exc).__name__}); using the synthetic fallback")
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        return {k: z[k] for k in z.files}
    return synthetic_chips(seed=seed)


# ---------------------------------------------------------------- event-level split
def event_split(events: Iterable[str], test: Iterable[str] = DEFAULT_TEST_EVENTS,
                val: Iterable[str] = DEFAULT_VAL_EVENTS, seed: int = 0,
                frac: tuple[float, float] = (0.2, 0.2)) -> dict[str, str]:
    """Map each event to 'train' / 'val' / 'test'. Uses the fixed lists when those events are present
    (real data); otherwise (synthetic) draws whole events at random with the seed."""
    evs = sorted(set(events))
    test, val = [e for e in test if e in evs], [e for e in val if e in evs]
    if not test or not val:
        rng = np.random.default_rng(seed)
        order = list(rng.permutation(evs))
        nt = max(1, int(round(frac[1] * len(evs))))
        nv = max(1, int(round(frac[0] * len(evs))))
        test, val = order[:nt], order[nt:nt + nv]
    return {e: ("test" if e in test else "val" if e in val else "train") for e in evs}


def assert_no_leakage(df, group: str = "event", split: str = "split", ids: Iterable[str] = ("chip",)) -> None:
    """Every group (event) lies in exactly one split, and no id appears twice."""
    n = df.groupby(group)[split].nunique()
    bad = n[n > 1]
    assert bad.empty, f"leakage: {group} values in more than one split: {list(bad.index)}"
    for c in ids:
        if c in df.columns:
            dup = df[c].duplicated()
            assert not dup.any(), f"duplicate {c}: {list(df.loc[dup, c])[:5]}"
    have = set(df[split])
    assert have <= {"train", "val", "test"}, have
    tr, va, te = (set(df.loc[df[split] == s, group]) for s in ("train", "val", "test"))
    assert not (tr & va or tr & te or va & te), "event sets overlap"


# ---------------------------------------------------------------- Kuro Siwo (optional, not run by default)
KUROSIWO_BASE = "https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset/resolve/main"


def kurosiwo_samples(shard: str = "train_GRD/shard-00000.tar", n: int = 4):
    """Stream n samples from a Kuro Siwo GRD webdataset shard (11 GB each; the stream is closed after n).
    Yields dicts with flood_vv, flood_vh, sec1_vv, sec1_vh, mask, valid_mask and info. Optional."""
    import tarfile
    import httpx
    keys = ("flood_vv", "flood_vh", "sec1_vv", "sec1_vh", "mask", "valid_mask")

    class _S(io.RawIOBase):
        def __init__(self, it):
            self.it, self.buf = it, b""

        def readable(self):
            return True

        def readinto(self, b):
            while not self.buf:
                try:
                    self.buf = next(self.it)
                except StopIteration:
                    return 0
            k = min(len(b), len(self.buf))
            b[:k] = self.buf[:k]
            self.buf = self.buf[k:]
            return k

    if offline():
        return
    cur_key, cur, kept = None, {}, 0
    with httpx.stream("GET", f"{KUROSIWO_BASE}/{shard}", follow_redirects=True, timeout=180) as r:
        r.raise_for_status()
        tf = tarfile.open(fileobj=io.BufferedReader(_S(r.iter_bytes(1 << 20)), 1 << 20), mode="r|")
        for m in tf:
            key, _, fld = m.name.partition(".")
            fld = fld.rsplit(".", 1)[0]
            if key != cur_key:
                if cur_key is not None and all(k in cur for k in keys):
                    yield {"key": f"{shard}:{cur_key}", **cur}
                    kept += 1
                    if kept >= n:
                        return
                cur_key, cur = key, {}
            if fld not in keys and fld != "info":
                continue
            f = tf.extractfile(m)
            if f is not None:
                data = f.read()
                cur[fld] = json.loads(data) if fld == "info" else np.load(io.BytesIO(data))[0]


# ---------------------------------------------------------------- STAC search (from earlier data/stac.py, data/scene.py)
@dataclass
class Endpoint:
    name: str
    url: str
    s1_collection: str
    s2_collection: str
    signing: Optional[str] = None
    readable: dict[str, bool] = field(default_factory=lambda: {"S1": True, "S2": True})


ENDPOINTS = [
    Endpoint("earth-search", "https://earth-search.aws.element84.com/v1", "sentinel-1-grd", "sentinel-2-l2a",
             readable={"S1": False, "S2": True}),          # S1 assets are requester-pays: search only
    Endpoint("planetary-computer", "https://planetarycomputer.microsoft.com/api/stac/v1", "sentinel-1-rtc",
             "sentinel-2-l2a", signing="planetary-computer", readable={"S1": True, "S2": True}),
]

BAND_ALIASES = {"blue": ("blue", "b02"), "green": ("green", "b03"), "red": ("red", "b04"), "nir": ("nir", "b08"),
                "swir16": ("swir16", "b11"), "scl": ("scl",), "vv": ("vv",), "vh": ("vh",)}
_LOOKUP = {a: c for c, al in BAND_ALIASES.items() for a in al}


def normalize_item(item: dict[str, Any], catalog: str) -> dict[str, Any]:
    """Catalogue-neutral scene record (plain dict so it can go straight into a receipt)."""
    p = item.get("properties", {})
    coll = item.get("collection") or ""
    sensor = "S1" if "sentinel-1" in coll else "S2"
    assets = {}
    for k, a in (item.get("assets") or {}).items():
        c = _LOOKUP.get(k.lower())
        if c and c not in assets and a.get("href"):
            assets[c] = a["href"]
    rel = p.get("sat:relative_orbit")
    return {"id": item["id"], "sensor": sensor, "datetime": p.get("datetime") or "", "date": (p.get("datetime") or "")[:10],
            "bbox": list(item.get("bbox") or [])[:4], "collection": coll, "catalog": catalog,
            "platform": p.get("platform"), "orbit_state": p.get("sat:orbit_state"),
            "relative_orbit": int(rel) if rel is not None else None, "cloud_cover": p.get("eo:cloud_cover"),
            "assets": assets}


def stac_search(sensor: str, bbox, start: str, end: str, max_cloud: Optional[float] = None,
                endpoints: Optional[list[Endpoint]] = None, need_readable: bool = False, max_items: int = 300,
                cache_dir: Optional[Path] = None, timeout: float = 30) -> dict[str, Any]:
    """POST /search with failover across public catalogues and paging through `next` links.
    Results are cached as JSON in cache_dir (keyed by request) so a re-run works offline.
    Returns {"scenes": [...], "log": [...], "from_cache": bool}."""
    import hashlib
    sensor = sensor.upper()
    eps = endpoints or ENDPOINTS
    if need_readable:
        eps = [e for e in eps if e.readable.get(sensor, True)]
    key = hashlib.sha256(json.dumps([sensor, list(bbox), start, end, max_cloud, [e.url for e in eps]]).encode()).hexdigest()[:16]
    cpath = Path(cache_dir) / f"stac_{sensor}_{key}.json" if cache_dir else None
    if cpath and cpath.exists():
        d = json.loads(cpath.read_text())
        return {**d, "from_cache": True}
    if offline():
        raise RuntimeError("offline and no cached STAC result")
    import httpx
    log = []
    for ep in eps:
        body: dict[str, Any] = {"collections": [ep.s1_collection if sensor == "S1" else ep.s2_collection],
                                "bbox": list(bbox), "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100}
        if max_cloud is not None and sensor == "S2":
            body["query"] = {"eo:cloud_cover": {"lte": max_cloud}}
        try:
            url, payload, feats = ep.url.rstrip("/") + "/search", dict(body), []
            with httpx.Client(timeout=timeout, follow_redirects=True) as http:
                while url and len(feats) < max_items:
                    r = http.post(url, json=payload)
                    r.raise_for_status()
                    data = r.json()
                    feats += data.get("features", [])
                    nxt = next((l for l in data.get("links", []) if l.get("rel") == "next"), None)
                    if not nxt or not data.get("features"):
                        break
                    url = nxt.get("href")
                    payload = {**payload, **(nxt.get("body") or {})} if (nxt.get("method") or "GET").upper() == "POST" else dict(body)
        except Exception as exc:  # noqa: BLE001
            log.append({"endpoint": ep.name, "ok": False, "error": repr(exc)[:200]})
            continue
        scenes = [normalize_item(f, ep.name) for f in feats[:max_items]]
        if max_cloud is not None and sensor == "S2":
            scenes = [s for s in scenes if s["cloud_cover"] is not None and s["cloud_cover"] <= max_cloud]
        for s in scenes:
            s["signing"] = ep.signing
            s["readable"] = ep.readable.get(sensor, True)
        log.append({"endpoint": ep.name, "ok": True, "items": len(scenes)})
        out = {"request": {"sensor": sensor, "bbox": list(bbox), "start": start, "end": end, "max_cloud": max_cloud},
               "scenes": scenes, "log": log}
        if cpath:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(out))
        return {**out, "from_cache": False}
    raise RuntimeError(f"no STAC endpoint answered: {log}")


# ---------------------------------------------------------------- COG window reads (from earlier data/cog.py)
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff,.TIF",
            "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "GDAL_HTTP_MULTIPLEX": "YES", "GDAL_HTTP_MAX_RETRY": "3",
            "GDAL_HTTP_RETRY_DELAY": "1", "VSI_CACHE": "TRUE", "AWS_NO_SIGN_REQUEST": "YES"}
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
           "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")


def dem_tile_url(lon: float, lat: float) -> str:
    la, lo = int(math.floor(lat)), int(math.floor(lon))
    return DEM_URL.format(ns="N" if la >= 0 else "S", lat=abs(la), ew="E" if lo >= 0 else "W", lon=abs(lo))


def sign_href(href: str, signing: Optional[str], collection: str) -> str:
    """Anonymous Planetary Computer SAS token; other hrefs pass through."""
    if signing != "planetary-computer":
        return href
    d = json.loads(_get(f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}", timeout=20))
    return f"{href}{'&' if '?' in href else '?'}{d['token']}"


def read_window(href: str, bbox_lonlat, band: int = 1) -> dict[str, Any]:
    """Read one band of a COG for a lon/lat box at native resolution with HTTP range requests.
    Only the overlapping internal blocks are fetched. Returns data (float32, NaN = nodata), crs, bounds, res."""
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds as win_from_bounds
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as ds:
        left, bottom, right, top = transform_bounds("EPSG:4326", ds.crs, *bbox_lonlat, densify_pts=21)
        win = win_from_bounds(left, bottom, right, top, transform=ds.transform).round_offsets().round_lengths()
        arr = ds.read(band, window=win, boundless=True, masked=True)
        data = np.ma.filled(arr.astype("float32"), np.nan)
        if ds.nodata is not None and not np.isnan(ds.nodata):
            data[data == ds.nodata] = np.nan
        wl, wt = ds.transform * (win.col_off, win.row_off)
        wr, wb = ds.transform * (win.col_off + win.width, win.row_off + win.height)
        return {"data": data, "crs": ds.crs.to_string(), "bounds": (wl, min(wb, wt), wr, max(wb, wt)),
                "res": float(abs(ds.res[0])), "window": [int(win.col_off), int(win.row_off), int(win.width), int(win.height)],
                "href": href.split("?")[0]}


# ---------------------------------------------------------------- revisit-gap model
def unique_pass_dates(scenes: list[dict[str, Any]], point: Optional[tuple[float, float]] = None) -> list[dict[str, Any]]:
    """One row per (date, relative orbit) whose footprint bbox covers `point` (lon, lat)."""
    rows, seen = [], set()
    for s in scenes:
        if point is not None and s.get("bbox"):
            w, so, e, n = s["bbox"]
            if not (w <= point[0] <= e and so <= point[1] <= n):
                continue
        k = (s["date"], s.get("relative_orbit"))
        if k in seen:
            continue
        seen.add(k)
        rows.append({"date": s["date"], "platform": s.get("platform"), "orbit_state": s.get("orbit_state"),
                     "relative_orbit": s.get("relative_orbit"), "scene_id": s["id"]})
    return sorted(rows, key=lambda r: r["date"])


def simulate_passes(start: str, end: str, revisit_days: int = 12, offsets: tuple[int, ...] = (0,),
                    drop_prob: float = 0.05, seed: int = 0) -> list[str]:
    """SYNTHETIC pass schedule: one pass every `revisit_days` per orbit offset, each pass missing with
    drop_prob (acquisition gaps). Used only when no STAC result is available."""
    rng = np.random.default_rng(seed)
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    out = set()
    for off in offsets:
        d = d0 + dt.timedelta(days=off)
        while d <= d1:
            if rng.random() >= drop_prob:
                out.add(d.isoformat())
            d += dt.timedelta(days=revisit_days)
    return sorted(out)


def gaps_days(dates: Iterable[str]) -> np.ndarray:
    """Days between consecutive distinct pass dates."""
    ds = sorted({dt.date.fromisoformat(d) for d in dates})
    return np.array([(b - a).days for a, b in zip(ds[:-1], ds[1:])], int)


def days_since_last_pass(dates: Iterable[str], start: str, end: str) -> dict[str, np.ndarray]:
    """For every calendar day in [start, end]: days since the last pass on or before it (NaN before the first)."""
    ds = np.array(sorted({dt.date.fromisoformat(d).toordinal() for d in dates}))
    days = np.arange(dt.date.fromisoformat(start).toordinal(), dt.date.fromisoformat(end).toordinal() + 1)
    idx = np.searchsorted(ds, days, side="right") - 1
    since = np.where(idx >= 0, days - ds[np.clip(idx, 0, None)], np.nan)
    return {"day": days, "since_last": since}


def gap_survival(gaps: np.ndarray, max_d: int = 40) -> np.ndarray:
    """Empirical P(gap >= d) for d = 0..max_d (the revisit-gap model in its simplest form)."""
    g = np.asarray(gaps)
    return np.array([(g >= d).mean() if g.size else np.nan for d in range(max_d + 1)])


def censor_interval(dates: list[str], wet: list[bool]) -> dict[str, Any]:
    """Interval-censored submergence from a pixel's or unit's wet/dry sequence at the pass dates.

    The first wet run is used. Onset lies in (last dry pass before it, first wet pass]; recession lies in
    (last wet pass of the run, first dry pass after it]. Returns the bracketing dates, the minimum and maximum
    possible duration in days, the days since the last dry and last wet pass at the end of the record, and
    flags for left censoring (no dry pass before) and right censoring (still wet at the last pass)."""
    o = [dt.date.fromisoformat(d) for d in dates]
    order = np.argsort([x.toordinal() for x in o])
    o = [o[i] for i in order]
    w = [bool(wet[i]) for i in order]
    last = o[-1] if o else None
    res: dict[str, Any] = {"n_passes": len(o), "ever_wet": any(w)}
    lw = max((x for x, y in zip(o, w) if y), default=None)
    ld = max((x for x, y in zip(o, w) if not y), default=None)
    res["days_since_last_wet"] = (last - lw).days if lw else None
    res["days_since_last_dry"] = (last - ld).days if ld else None
    if not any(w):
        return {**res, "onset_lo": None, "onset_hi": None, "recede_lo": None, "recede_hi": None,
                "dur_min": 0, "dur_max": 0, "left_censored": False, "right_censored": False}
    i = w.index(True)
    j = i
    while j + 1 < len(w) and w[j + 1]:
        j += 1
    onset_lo = o[i - 1] if i > 0 else None
    recede_hi = o[j + 1] if j + 1 < len(o) else None
    dmin = (o[j] - o[i]).days + 1          # wet at both ends of the run, at least this many days
    dmax = ((recede_hi - onset_lo).days - 1) if (onset_lo and recede_hi) else None
    return {**res, "onset_lo": onset_lo.isoformat() if onset_lo else None, "onset_hi": o[i].isoformat(),
            "recede_lo": o[j].isoformat(), "recede_hi": recede_hi.isoformat() if recede_hi else None,
            "dur_min": dmin, "dur_max": dmax, "left_censored": onset_lo is None, "right_censored": recede_hi is None}
