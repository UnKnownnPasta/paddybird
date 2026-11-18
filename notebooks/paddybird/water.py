"""Layer 2 predictor 1 and chip input for the mapping notebook.

Chip schema assumed from layer 1 (one .npz per chip, or stacked .npz files with a leading chip axis):

    s1_vv, s1_vh   float, (H, W), post-event Sentinel-1 backscatter in dB (gamma0, 20 m working grid)
    label          int,   (H, W), 1 water, 0 not water, -1 not labelled
    event          str,   flood event id (the unit of every split)
    optional:
    chip           str,   chip id (defaults to the file stem)
    split          str,   train / val / test, must be constant within an event
    s2             float, (6, H, W), reflectance 0..1 in band order B2, B3, B4, B8, B11, B12
    perm_water     uint8, (H, W), 1 where water is permanent (JRC), removed from every flood map
    landcover      uint8, (H, W), ESA WorldCover 2021 class codes (10 tree ... 40 cropland ... 100 moss)
    paddy          float or uint8, (H, W), paddy mask or probability; WorldCover cropland is the fallback
    s1_pre_vv, s1_pre_vh  float, (H, W), pre-event pair for the log-ratio change rule

Aliases such as vv, vh, VV, s1[0], jrc are accepted. If layer 1 has not written any chips yet, the
notebook can build the same schema from the public Sen1Floods11 hand-labelled chips plus ESA WorldCover
(`fetch_public_sample`), cached under notebooks/data/.

Predictor 1 is the transparent rule stack copied and adapted from the earlier sar_water_otsu and
sar_logratio_change instruments (split-based Kittler-Illingworth threshold on VV and VH, 3 dB log-ratio
drop, MNDWI on clear optical pixels), turned into a soft score by the 1 dB threshold-error model the
earlier confidence used. The baseline is plain per-chip Otsu on VV. No side effects on import.
"""
from __future__ import annotations

import hashlib
import json
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

# ---------------------------------------------------------------- thresholds (earlier, train-split bounds)
DEFAULT_DB = -17.0
MAX_WATER_DB = -14.0
VH_MAX_WATER_DB = -18.0
VH_DEFAULT_DB = -22.0
BLOCK_PX = 50
MIN_D = 3.0
MIN_GAP_DB = 3.0
MIN_BLOB_PX = 10
DROP_DB = -3.0
THRESH_SIGMA_DB = 1.0
S2_BANDS = ("B2", "B3", "B4", "B8", "B11", "B12")

# WorldCover classes grouped for fusion strata.
LC_GROUPS = {10: "tree", 20: "shrub_grass", 30: "shrub_grass", 40: "cropland", 50: "built", 60: "bare",
             70: "other", 80: "open_water", 90: "wetland", 95: "wetland", 100: "other", 0: "other"}
LC_NAMES = ("cropland", "tree", "shrub_grass", "built", "bare", "wetland", "open_water", "other")


# ---------------------------------------------------------------- histogram helpers
def otsu(values: np.ndarray, bins: int = 256) -> float:
    v = values[np.isfinite(values)]
    if v.size < 2:
        return float("nan")
    hist, edges = np.histogram(v, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m = np.cumsum(hist * centers)
    with np.errstate(divide="ignore", invalid="ignore"):
        between = w0 * w1 * (m / w0 - (m[-1] - m) / w1) ** 2
    between[~np.isfinite(between)] = -1
    return float(centers[int(np.argmax(between))])


def kittler_illingworth(values: np.ndarray, bins: int = 256) -> float:
    """Minimum-error threshold (Kittler and Illingworth 1986); allows unequal class spreads."""
    v = values[np.isfinite(values)]
    hist, edges = np.histogram(v, bins=bins)
    c = (edges[:-1] + edges[1:]) / 2
    p = hist / max(hist.sum(), 1)
    P1 = np.cumsum(p)
    P2 = 1 - P1
    m1c = np.cumsum(p * c)
    m2c = m1c[-1] - m1c
    s1c = np.cumsum(p * c * c)
    s2c = s1c[-1] - s1c
    with np.errstate(divide="ignore", invalid="ignore"):
        mu1, mu2 = m1c / P1, m2c / P2
        var1, var2 = s1c / P1 - mu1 ** 2, s2c / P2 - mu2 ** 2
        J = 1 + 2 * (P1 * np.log(np.sqrt(var1)) + P2 * np.log(np.sqrt(var2))) - 2 * (P1 * np.log(P1) + P2 * np.log(P2))
    ok = (P1 > 0.02) & (P2 > 0.02) & (var1 > 1e-6) & (var2 > 1e-6) & np.isfinite(J)
    if not ok.any():
        return otsu(values, bins)
    J[~ok] = np.inf
    return float(c[int(np.argmin(J))])


def split_stats(values: np.ndarray, t: float) -> dict[str, float]:
    v = values[np.isfinite(values)]
    lo, hi = v[v < t], v[v >= t]
    if lo.size < 2 or hi.size < 2:
        return {"ashman_d": 0.0, "minority": 0.0, "mean_low": float("nan"), "mean_high": float("nan")}
    d = np.sqrt(2) * abs(lo.mean() - hi.mean()) / np.sqrt(lo.var() + hi.var() + 1e-9)
    return {"ashman_d": float(d), "minority": float(min(lo.size, hi.size) / v.size),
            "mean_low": float(lo.mean()), "mean_high": float(hi.mean())}


def drop_small(mask: np.ndarray, min_px: int = MIN_BLOB_PX) -> np.ndarray:
    if min_px <= 1 or not mask.any():
        return mask
    from scipy import ndimage
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    keep[1:] = sizes >= min_px
    return keep[lab]


def fit_sar_threshold(band_db: np.ndarray, max_water_db: float = MAX_WATER_DB,
                      default_db: float = DEFAULT_DB) -> dict[str, Any]:
    """Split-based threshold (earlier sar_water_otsu v1.1): keep bimodal 1 km blocks, pool them and fit
    Kittler-Illingworth; reject fits above `max_water_db`; otherwise use `default_db`."""
    h, w = band_db.shape
    kept, n_blocks = [], 0
    step = BLOCK_PX // 2
    for y in range(0, max(h - step, 1), step):
        for x in range(0, max(w - step, 1), step):
            blk = band_db[y:y + BLOCK_PX, x:x + BLOCK_PX]
            if np.isfinite(blk).mean() < 0.8:
                continue
            n_blocks += 1
            t = otsu(blk)
            st = split_stats(blk, t)
            if (st["ashman_d"] >= MIN_D and st["minority"] >= 0.10 and st["mean_low"] < max_water_db - 1
                    and st["mean_high"] - st["mean_low"] >= MIN_GAP_DB):
                kept.append(blk[np.isfinite(blk)])
    fit = {"blocks": n_blocks, "bimodal_blocks": len(kept)}
    if kept:
        t = kittler_illingworth(np.concatenate(kept))
        if t <= max_water_db:
            return {**fit, "threshold_db": float(t), "source": "fitted"}
        fit["rejected_fit_db"] = float(t)
    return {**fit, "threshold_db": float(default_db), "source": "default"}


def norm_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / (a + b)
    out[~np.isfinite(out)] = np.nan
    return out


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1 + np.tanh(0.5 * np.asarray(x, dtype="float64")))


def logit(p: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype="float64"), eps, 1 - eps)
    return np.log(p / (1 - p))


# ---------------------------------------------------------------- chip input
_ALIASES = {
    "s1_vv": ("s1_vv", "vv", "VV", "vv_db", "s1_vv_post", "post_vv"),
    "s1_vh": ("s1_vh", "vh", "VH", "vh_db", "s1_vh_post", "post_vh"),
    "label": ("label", "labels", "y", "label_hand", "water_label"),
    "s2": ("s2", "S2", "s2_bands"),
    "perm_water": ("perm_water", "permanent_water", "jrc", "jrc_water", "perm"),
    "landcover": ("landcover", "land_cover", "worldcover", "lc"),
    "paddy": ("paddy", "paddy_mask", "paddy_prob"),
    "s1_pre_vv": ("s1_pre_vv", "pre_vv", "vv_pre"),
    "s1_pre_vh": ("s1_pre_vh", "pre_vh", "vh_pre"),
}


def _first(z: Any, names: Iterable[str]) -> Optional[np.ndarray]:
    for n in names:
        if n in z:
            return np.asarray(z[n])
    return None


def _scalar(x: Any) -> Optional[str]:
    if x is None:
        return None
    a = np.asarray(x)
    return str(a.item() if a.ndim == 0 else a.reshape(-1)[0])


def _chip_from_mapping(z: Any, chip_id: str) -> Optional[dict[str, Any]]:
    out: dict[str, Any] = {}
    for key, names in _ALIASES.items():
        out[key] = _first(z, names)
    if out["s1_vv"] is None and "s1" in z:
        s1 = np.asarray(z["s1"])
        out["s1_vv"], out["s1_vh"] = s1[0], (s1[1] if s1.shape[0] > 1 else None)
    if out["s1_vv"] is None or out["label"] is None:
        return None
    out["s1_vv"] = out["s1_vv"].astype("float32")
    if out["s1_vh"] is not None:
        out["s1_vh"] = out["s1_vh"].astype("float32")
    if out["s2"] is not None:
        out["s2"] = out["s2"].astype("float32")
        if out["s2"].ndim == 3 and out["s2"].shape[-1] in (6, 13) and out["s2"].shape[0] not in (6, 13):
            out["s2"] = np.moveaxis(out["s2"], -1, 0)
        if np.nanmax(out["s2"]) > 2.0:          # stored as reflectance x 10000
            out["s2"] = out["s2"] / 10000.0
    out["label"] = out["label"].astype("int8")
    out["chip"] = _scalar(z["chip"]) if "chip" in z else chip_id
    out["event"] = _scalar(z["event"]) if "event" in z else str(out["chip"]).split("_")[0]
    out["split"] = _scalar(z["split"]) if "split" in z else None
    out["bounds"] = np.asarray(z["bounds"], "float64").reshape(-1)[:4] if "bounds" in z else None
    return out


def load_chips(root: Path) -> list[dict[str, Any]]:
    """Read every chip .npz under `root` (recursive). Handles one-chip files and stacked files whose
    arrays carry a leading chip axis plus a `chip` array."""
    chips: list[dict[str, Any]] = []
    for f in sorted(Path(root).rglob("*.npz")):
        with np.load(f, allow_pickle=True) as z:
            keys = set(z.files)
            vv_key = next((k for k in _ALIASES["s1_vv"] if k in keys), None)
            if vv_key is None and "s1" not in keys:
                continue
            arr = z[vv_key] if vv_key else z["s1"]
            stacked = "chip" in keys and np.asarray(z["chip"]).ndim == 1 and arr.ndim == (3 if vv_key else 4)
            if stacked:
                data = {k: z[k] for k in keys}
                for i, cid in enumerate(data["chip"]):
                    one = {k: (v[i] if (isinstance(v, np.ndarray) and v.ndim >= 1 and v.shape[0] == len(data["chip"])) else v)
                           for k, v in data.items()}
                    c = _chip_from_mapping(one, str(cid))
                    if c is not None:
                        chips.append(c)
            else:
                c = _chip_from_mapping({k: z[k] for k in keys}, f.stem)
                if c is not None:
                    chips.append(c)
    return chips


# Event-level default split (used when layer 1 gives no split). It is the same fixed split as layer 1's
# paddybird/data.py (DEFAULT_TEST_EVENTS, DEFAULT_VAL_EVENTS), chosen before any model was fit: India
# (target geography) and Bolivia (official held-out region) are test, Sri-Lanka and Ghana validation.
DEFAULT_SPLIT = {
    "train": ("Mekong", "Paraguay", "USA", "Spain", "Nigeria", "Somalia", "Pakistan"),
    "val": ("Sri-Lanka", "Ghana"),
    "test": ("India", "Bolivia"),
}


def assign_splits(chips: list[dict[str, Any]], default: dict[str, tuple[str, ...]] = DEFAULT_SPLIT) -> str:
    """Use layer 1's split if it is event-level (one split per event) and covers train, val and test;
    else apply `default`. Returns which source was used."""
    by_event: dict[str, set] = {}
    for c in chips:
        by_event.setdefault(c["event"], set()).add(c.get("split"))
    ok = all(len(s) == 1 and None not in s for s in by_event.values())
    if ok:
        norm = {"valid": "val", "validation": "val", "holdout": "test"}
        for c in chips:
            c["split"] = norm.get(c["split"], c["split"])
        if {"train", "val", "test"} <= {c["split"] for c in chips}:
            return "layer1"
    lookup = {e: s for s, evs in default.items() for e in evs}
    for c in chips:
        c["split"] = lookup.get(c["event"], "train")
    return "default_event_split"


# ---------------------------------------------------------------- public fallback sample
S1F_BUCKET = "https://storage.googleapis.com/sen1floods11/v1.1"
WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
S2_IDX = (1, 2, 3, 7, 11, 12)    # B2, B3, B4, B8, B11, B12 in the 13-band S2Hand files


def _get(url: str, timeout: float = 120) -> bytes:
    import urllib.request
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"download failed: {url}: {last}")


def _read_tif(blob: bytes):
    from rasterio.io import MemoryFile
    with MemoryFile(blob) as mf, mf.open() as ds:
        return ds.read().astype("float32"), ds.bounds


def _mean2(a: np.ndarray, lin: bool = False) -> np.ndarray:
    h, w = (a.shape[-2] // 2) * 2, (a.shape[-1] // 2) * 2
    a = a[..., :h, :w]
    if lin:
        a = np.where(np.isfinite(a), 10 ** (a / 10), np.nan)
    b = a.reshape(*a.shape[:-2], h // 2, 2, w // 2, 2)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.nanmean(b, axis=(-3, -1))
        if lin:
            m = 10 * np.log10(m)
    m[~np.isfinite(m)] = np.nan
    return m


def _label20(lab: np.ndarray) -> np.ndarray:
    h, w = (lab.shape[0] // 2) * 2, (lab.shape[1] // 2) * 2
    b = lab[:h, :w].reshape(h // 2, 2, w // 2, 2)
    labelled = (b >= 0).sum(axis=(1, 3))
    water = (b == 1).sum(axis=(1, 3))
    return np.where(labelled == 0, -1, (water * 2 >= labelled).astype("int8")).astype("int8")


def _worldcover(bounds, shape) -> np.ndarray:
    import math

    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    lat0 = int(math.floor(bounds.bottom / 3) * 3)
    lon0 = int(math.floor(bounds.left / 3) * 3)
    tile = f"{'N' if lat0 >= 0 else 'S'}{abs(lat0):02d}{'E' if lon0 >= 0 else 'W'}{abs(lon0):03d}"
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open("/vsicurl/" + WC_URL.format(tile=tile)) as ds:
            win = from_bounds(bounds.left, bounds.bottom, bounds.right, bounds.top, ds.transform)
            return ds.read(1, window=win, out_shape=shape, resampling=Resampling.mode, boundless=True, fill_value=0)


def enrich_landcover(chips: list[dict[str, Any]], cache: Path, workers: int = 8) -> int:
    """Add a WorldCover `landcover` array to chips that lack one but carry lon/lat `bounds` (layer 1 chips
    may come without land cover). Results are cached in one npz keyed by chip id. Returns how many
    chips were filled."""
    cache = Path(cache)
    have: dict[str, np.ndarray] = {}
    if cache.exists():
        with np.load(cache, allow_pickle=False) as z:
            have = {k: z[k] for k in z.files}
    need = [c for c in chips if c.get("landcover") is None and c.get("bounds") is not None
            and not (str(c["chip"]) in have and have[str(c["chip"])].shape == c["s1_vv"].shape)]

    class _B:
        def __init__(self, b):
            self.left, self.bottom, self.right, self.top = (float(x) for x in b)

    def one(c):
        try:
            return str(c["chip"]), _worldcover(_B(c["bounds"]), c["s1_vv"].shape).astype("uint8")
        except Exception as exc:  # noqa: BLE001
            print(f"  WorldCover failed for {c['chip']}: {exc}"[:160])
            return str(c["chip"]), None
    if need:
        with ThreadPoolExecutor(workers) as pool:
            for k, a in pool.map(one, need):
                if a is not None:
                    have[k] = a
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, **have)
    n = 0
    for c in chips:
        if c.get("landcover") is None and str(c["chip"]) in have and have[str(c["chip"])].shape == c["s1_vv"].shape:
            c["landcover"] = have[str(c["chip"])]
            n += 1
    return n


def _fetch_one(chip: str, event: str, shift_db: float) -> Optional[dict[str, Any]]:
    base = f"{S1F_BUCKET}/data/flood_events/HandLabeled"
    try:
        s1, bounds = _read_tif(_get(f"{base}/S1Hand/{chip}_S1Hand.tif"))
        s2, _ = _read_tif(_get(f"{base}/S2Hand/{chip}_S2Hand.tif"))
        lab, _ = _read_tif(_get(f"{base}/LabelHand/{chip}_LabelHand.tif"))
        jrc, _ = _read_tif(_get(f"{base}/JRCWaterHand/{chip}_JRCWaterHand.tif"))
    except Exception as exc:  # noqa: BLE001
        print(f"  skipped {chip}: {exc}"[:160])
        return None
    vv = _mean2(s1[0], lin=True) + shift_db
    vh = _mean2(s1[1], lin=True) + shift_db
    s2r = _mean2(s2[list(S2_IDX)] / 10000.0)
    lab20 = _label20(lab[0])
    jrc20 = (_mean2(jrc[0].astype("float32")) >= 0.5).astype("uint8")
    try:
        lc = _worldcover(bounds, vv.shape).astype("uint8")
    except Exception as exc:  # noqa: BLE001
        print(f"  WorldCover failed for {chip}: {exc}"[:160])
        lc = np.zeros(vv.shape, "uint8")
    return {"chip": chip, "event": event, "s1_vv": vv.astype("float16"), "s1_vh": vh.astype("float16"),
            "s2": s2r.astype("float16"), "label": lab20, "perm_water": jrc20, "landcover": lc,
            "bounds": np.array([bounds.left, bounds.bottom, bounds.right, bounds.top])}


def fetch_public_sample(out_dir: Path, per_event: int = 10, seed: int = 0, shift_db: float = 1.0,
                        workers: int = 8) -> dict[str, Any]:
    """Build a small layer-1-shaped sample from Sen1Floods11 v1.1 hand labels (all four official splits
    pooled; we re-split by event) plus ESA WorldCover 2021. Already cached chips are not downloaded again."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for split in ("flood_train_data.csv", "flood_valid_data.csv", "flood_test_data.csv", "flood_bolivia_data.csv"):
        text = _get(f"{S1F_BUCKET}/splits/flood_handlabeled/{split}").decode()
        names += [ln.split(",")[0].strip().replace("_S1Hand.tif", "") for ln in text.strip().splitlines()]
    names = sorted(set(names))
    rng = np.random.default_rng(seed)
    by: dict[str, list[str]] = {}
    for n in names:
        by.setdefault(n.split("_")[0], []).append(n)
    picks = []
    for ev in sorted(by):
        lst = sorted(by[ev])
        idx = rng.permutation(len(lst))[:per_event]
        picks += [(lst[i], ev) for i in sorted(idx)]
    todo = [(c, e) for c, e in picks if not (out_dir / f"{c}.npz").exists()]
    with ThreadPoolExecutor(workers) as pool:
        for res in pool.map(lambda ce: _fetch_one(ce[0], ce[1], shift_db), todo):
            if res is not None:
                np.savez_compressed(out_dir / f"{res['chip']}.npz", **res)
    return {"source": "Sen1Floods11 v1.1 HandLabeled (S1Hand, S2Hand, LabelHand, JRCWaterHand) + ESA WorldCover 2021 v200",
            "per_event": per_event, "seed": seed, "shift_db": shift_db, "picked": len(picks),
            "cached": len(list(out_dir.glob("*.npz")))}


# ---------------------------------------------------------------- predictor 1 and baseline
def valid_mask(c: dict[str, Any]) -> np.ndarray:
    v = np.isfinite(c["s1_vv"]) & (c["label"] >= 0)
    if c.get("s1_vh") is not None:
        v &= np.isfinite(c["s1_vh"])
    return v


def perm_mask(c: dict[str, Any]) -> np.ndarray:
    p = c.get("perm_water")
    return np.zeros(c["s1_vv"].shape, bool) if p is None else np.asarray(p) > 0


def s2_indices(c: dict[str, Any]) -> dict[str, np.ndarray]:
    """NDWI (McFeeters), MNDWI (Xu), NDVI on clear pixels; NaN on cloud (blue > 0.18 or cirrus-bright
    SWIR) or where S2 is missing."""
    shape = c["s1_vv"].shape
    nan = np.full(shape, np.nan, "float32")
    s2 = c.get("s2")
    if s2 is None or s2.shape[0] < 6:
        return {"ndwi": nan, "mndwi": nan, "ndvi": nan, "clear": np.zeros(shape, bool)}
    b2, b3, b4, b8, b11, _ = (s2[i] for i in range(6))
    clear = np.isfinite(b2) & (b2 < 0.18) & (b2 > 0) & (b8 > 0)
    nd = {"ndwi": norm_diff(b3, b8), "mndwi": norm_diff(b3, b11), "ndvi": norm_diff(b8, b4)}
    return {**{k: np.where(clear, v, np.nan).astype("float32") for k, v in nd.items()}, "clear": clear}


def baseline_otsu(c: dict[str, Any]) -> dict[str, Any]:
    """Baseline: one global Otsu split of VV per chip, water below it, permanent water removed. Hard 0/1."""
    v = valid_mask(c)
    vv = np.where(v, c["s1_vv"], np.nan)
    t = otsu(vv)
    water = v & (vv < t) & ~perm_mask(c)
    return {"water": water, "threshold_db": t}


def predictor1(c: dict[str, Any]) -> dict[str, Any]:
    """Rule stack: split-based VV/VH threshold margin -> soft score with a 1 dB threshold error,
    averaged with an MNDWI score on clear optical pixels, gated by the 3 dB log-ratio drop when a
    pre-event pair exists. Permanent water is set to 0."""
    v = valid_mask(c)
    vv = np.where(v, c["s1_vv"], np.nan)
    fvv = fit_sar_threshold(vv)
    margin = vv - fvv["threshold_db"]
    fvh = None
    if c.get("s1_vh") is not None:
        vh = np.where(v, c["s1_vh"], np.nan)
        fvh = fit_sar_threshold(vh, VH_MAX_WATER_DB, VH_DEFAULT_DB)
        with np.errstate(invalid="ignore"):
            margin = np.fmin(margin, vh - fvh["threshold_db"])
    sar = sigmoid(-margin / THRESH_SIGMA_DB * 1.7)   # 1.7 makes the logistic close to a normal CDF with sd 1 dB
    idx = s2_indices(c)
    opt = sigmoid(idx["mndwi"] / 0.05)
    score = np.where(idx["clear"], 0.5 * (sar + opt), sar)
    used = ["sar_threshold"] + (["mndwi"] if idx["clear"].any() else [])
    pre_vv = c.get("s1_pre_vv")
    if pre_vv is not None and np.isfinite(pre_vv).any():
        with np.errstate(invalid="ignore"):
            ratio = c["s1_vv"] - pre_vv
            if c.get("s1_pre_vh") is not None and c.get("s1_vh") is not None:
                ratio = np.fmin(ratio, c["s1_vh"] - c["s1_pre_vh"])
        change = sigmoid(-(ratio - DROP_DB) / THRESH_SIGMA_DB * 1.7)
        score = np.where(np.isfinite(ratio), np.sqrt(score * change), score)
        used.append("logratio_change")
    score = np.where(v & ~perm_mask(c), score, 0.0)
    hard = drop_small(v & ~perm_mask(c) & (margin < 0))
    return {"p1": np.nan_to_num(score).astype("float32"), "hard": hard, "margin": margin.astype("float32"),
            "fit_vv": fvv, "fit_vh": fvh, "components": used}


# ---------------------------------------------------------------- predictor 2 features
FEATURES = ("vv", "vh", "vv_minus_vh", "vv_m5", "vh_m5", "vv_s5", "vv_m15", "vh_m15", "margin",
            "vv_rel_t", "ndwi", "mndwi", "ndvi", "lc")


def _box(a: np.ndarray, k: int) -> np.ndarray:
    from scipy import ndimage
    f = np.isfinite(a)
    num = ndimage.uniform_filter(np.where(f, a, 0.0), k, mode="nearest")
    den = ndimage.uniform_filter(f.astype("float64"), k, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def pixel_features(c: dict[str, Any], p1: dict[str, Any]) -> np.ndarray:
    """(H*W, len(FEATURES)) float32 matrix; NaN where a source is missing (the boosted model handles NaN)."""
    vv = c["s1_vv"].astype("float64")
    vh = c["s1_vh"].astype("float64") if c.get("s1_vh") is not None else np.full_like(vv, np.nan)
    m5 = _box(vv, 5)
    s5 = np.sqrt(np.maximum(_box(vv * vv, 5) - m5 ** 2, 0))
    idx = s2_indices(c)
    lc = np.asarray(c["landcover"], "float64") if c.get("landcover") is not None else np.full_like(vv, np.nan)
    cols = [vv, vh, vv - vh, m5, _box(vh, 5), s5, _box(vv, 15), _box(vh, 15), p1["margin"],
            vv - p1["fit_vv"]["threshold_db"], idx["ndwi"], idx["mndwi"], idx["ndvi"], lc]
    return np.stack([np.asarray(x, "float32").reshape(-1) for x in cols], 1)


def lc_group(c: dict[str, Any]) -> np.ndarray:
    lc = c.get("landcover")
    if lc is None:
        return np.full(c["s1_vv"].shape, "other", dtype=object)
    look = np.array([LC_GROUPS.get(i, "other") for i in range(256)], dtype=object)
    return look[np.asarray(lc, "uint8")]


def paddy_mask(c: dict[str, Any]) -> tuple[np.ndarray, str]:
    """Paddy probability or mask. Layer 1's `paddy` array if present; else WorldCover cropland (40) as
    a proxy (WorldCover has no paddy class, so outside rice regions this over-counts)."""
    if c.get("paddy") is not None:
        return np.clip(np.asarray(c["paddy"], "float32"), 0, 1), "layer1 paddy layer"
    if c.get("landcover") is not None:
        return (np.asarray(c["landcover"]) == 40).astype("float32"), "WorldCover 2021 cropland (class 40) proxy"
    return np.ones(c["s1_vv"].shape, "float32"), "none (no land cover; every pixel treated as paddy)"


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def dumps(obj: Any) -> str:
    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return str(o)
    return json.dumps(obj, indent=2, default=conv)

