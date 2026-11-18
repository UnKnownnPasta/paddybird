"""Receipts and manifests. A receipt is canonical JSON plus SHA-256 hashes so a re-run can prove it
reproduced the answer (adapted from the earlier prototype).

CHANGE from the earlier receipt: a receipt can carry a `survey` block with the first-order inclusion
probability of every field check (pi_i), the design that produced it, the seed, and whether the check was
actually reached. Layer 3 weights each check by 1 / pi_i (Horvitz-Thompson); layer 4 writes the block.

No side effects on import.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

SCHEMA = "paddybird.receipt/1"
MANIFEST_SCHEMA = "paddybird.manifest/1"
DESIGNS = ("stratified_srswor", "pps_systematic", "poisson", "census", "route_nominal")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- survey inclusion probabilities
def stratified_srswor(frame: list[dict[str, Any]], n_per_stratum: dict[str, int], seed: int,
                      stratum_key: str = "stratum", id_key: str = "check_id") -> list[dict[str, Any]]:
    """Draw a stratified simple random sample without replacement and return one row per frame element
    with its inclusion probability pi = n_h / N_h and whether it was selected. Seeded and reproducible."""
    rng = np.random.default_rng(seed)
    by: dict[str, list[int]] = {}
    for i, r in enumerate(frame):
        by.setdefault(str(r[stratum_key]), []).append(i)
    out = []
    for h in sorted(by):
        idx = by[h]
        N, n = len(idx), min(int(n_per_stratum.get(h, 0)), len(idx))
        sel = set(rng.choice(idx, n, replace=False).tolist()) if n else set()
        for i in idx:
            out.append({**frame[i], "stratum": h, "N_h": N, "n_h": n, "pi": n / N if N else 0.0, "selected": i in sel})
    return sorted(out, key=lambda r: str(r[id_key]))


def survey_block(rows: list[dict[str, Any]], design: str, seed: int, id_key: str = "check_id",
                 pairwise: Optional[dict[str, float]] = None) -> dict[str, Any]:
    """Receipt block for the SELECTED checks: id, unit, stratum, pi (nominal), reached (None until the
    field day ends), pi_realised (None unless a correction model is applied). Validates 0 < pi <= 1."""
    if design not in DESIGNS:
        raise ValueError(f"design must be one of {DESIGNS}")
    sel = [r for r in rows if r.get("selected", True)]
    for r in sel:
        p = float(r["pi"])
        if not (0.0 < p <= 1.0):
            raise ValueError(f"inclusion probability out of (0, 1]: {r[id_key]} pi={p}")
    checks = [{"check_id": str(r[id_key]), "unit_id": str(r.get("unit_id", "")), "stratum": str(r.get("stratum", "")),
               "pi": round(float(r["pi"]), 12), "weight": round(1.0 / float(r["pi"]), 12),
               "reached": r.get("reached"), "pi_realised": r.get("pi_realised")} for r in sel]
    return {"design": design, "seed": int(seed), "n_selected": len(checks),
            "frame_size": len(rows), "strata": _strata_summary(rows), "checks": checks,
            "pairwise_pi": pairwise or {}}


def _strata_summary(rows):
    s: dict[str, dict[str, Any]] = {}
    for r in rows:
        h = str(r.get("stratum", ""))
        d = s.setdefault(h, {"N_h": 0, "n_h": 0})
        d["N_h"] += 1
        d["n_h"] += int(bool(r.get("selected", True)))
    return s


def ht_total(y: Iterable[float], pi: Iterable[float]) -> float:
    """Horvitz-Thompson estimate of a frame total from the selected checks."""
    y, pi = np.asarray(list(y), float), np.asarray(list(pi), float)
    return float((y / pi).sum())


# ---------------------------------------------------------------- receipts
def build_receipt(step: str, inputs: dict[str, str], params: dict[str, Any], outputs: dict[str, str],
                  scenes: Optional[list[dict[str, Any]]] = None, windows: Optional[list[dict[str, Any]]] = None,
                  survey: Optional[dict[str, Any]] = None, notes: str = "") -> dict[str, Any]:
    """inputs/outputs map a name to a SHA-256 (of a file or of canonical JSON)."""
    body = {"schema": SCHEMA, "step": step, "inputs": dict(sorted(inputs.items())), "params": params,
            "scenes": scenes or [], "windows": windows or [], "survey": survey,
            "outputs": dict(sorted(outputs.items())), "notes": notes}
    body["output_hash"] = digest({"outputs": body["outputs"], "survey": survey})
    body["receipt_id"] = digest(body)[:16]
    return body


def verify_receipt(rec: dict[str, Any], files: Optional[dict[str, Path]] = None) -> bool:
    """Recompute receipt_id and output_hash; if `files` is given, also re-hash those output files."""
    body = {k: v for k, v in rec.items() if k != "receipt_id"}
    if digest(body)[:16] != rec["receipt_id"]:
        return False
    if digest({"outputs": rec["outputs"], "survey": rec["survey"]}) != rec["output_hash"]:
        return False
    for name, p in (files or {}).items():
        if rec["outputs"].get(name) != file_sha256(p):
            return False
    if rec.get("survey"):
        if any(not (0 < c["pi"] <= 1) for c in rec["survey"]["checks"]):
            return False
    return True


# ---------------------------------------------------------------- manifest
def describe_file(path: Path) -> dict[str, Any]:
    path = Path(path)
    d: dict[str, Any] = {"bytes": path.stat().st_size, "sha256": file_sha256(path)}
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        t = pq.read_schema(path)
        d["format"] = "parquet"
        d["rows"] = pq.ParquetFile(path).metadata.num_rows
        d["columns"] = {f.name: str(f.type) for f in t}
    elif path.suffix == ".npz":
        z = np.load(path, allow_pickle=False)
        d["format"] = "npz"
        d["arrays"] = {k: {"shape": list(z[k].shape), "dtype": str(z[k].dtype)} for k in z.files}
    elif path.suffix in (".json", ".geojson"):
        d["format"] = "geojson" if path.suffix == ".geojson" else "json"
    elif path.suffix == ".png":
        d["format"] = "png"
    return d


def write_manifest(out_dir: Path, layer: int, seed: int, files: dict[str, str], sources: dict[str, Any],
                   extra: Optional[dict[str, Any]] = None, source_hashes: Optional[dict[str, str]] = None) -> Path:
    """MANIFEST.json: one entry per file (description, schema, shape, hash) plus provenance."""
    out_dir = Path(out_dir)
    entries = {}
    for name, desc in sorted(files.items()):
        entries[name] = {"description": desc, **describe_file(out_dir / name)}
    m = {"schema": MANIFEST_SCHEMA, "layer": layer, "seed": seed,
         "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
         "sources": sources, "source_hashes": source_hashes or {}, "files": entries, **(extra or {})}
    p = out_dir / "MANIFEST.json"
    p.write_text(json.dumps(m, indent=2, default=_default), encoding="utf-8")
    return p
