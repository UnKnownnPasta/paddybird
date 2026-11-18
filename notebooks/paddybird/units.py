"""Layer 1 insurance units: rectangular grid units over a study region, pseudo-village units on chips,
and a loader for public admin polygons (GeoJSON). Pure numpy, no geopandas. No side effects on import.

Unit tables share these columns: unit_id, area_ha, lon, lat (centroid), and either a lon/lat bbox
(grid and admin units) or a pixel window r0, c0, r1, c1 inside one chip (chip units).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

R_EARTH = 6_371_008.8


def km_per_deg(lat: float) -> tuple[float, float]:
    """(km per degree of longitude, km per degree of latitude) at `lat`."""
    return 111.32 * math.cos(math.radians(lat)), 110.57


def polygon_area_ha(ring: list[tuple[float, float]]) -> float:
    """Area of a lon/lat ring (local equirectangular projection, fine for village-size polygons)."""
    if len(ring) < 3:
        return 0.0
    lat0 = float(np.mean([p[1] for p in ring]))
    kx, ky = km_per_deg(lat0)
    x = np.array([p[0] for p in ring]) * kx
    y = np.array([p[1] for p in ring]) * ky
    a_km2 = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    return float(a_km2 * 100.0)


def grid_units(bbox: tuple[float, float, float, float], nx: int, ny: int, prefix: str = "G") -> list[dict[str, Any]]:
    """nx x ny rectangular units covering a lon/lat bbox (row 0 at the north edge)."""
    w, s, e, n = bbox
    dx, dy = (e - w) / nx, (n - s) / ny
    out = []
    for i in range(ny):
        for j in range(nx):
            x0, x1 = w + j * dx, w + (j + 1) * dx
            y1, y0 = n - i * dy, n - (i + 1) * dy
            ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            out.append({"unit_id": f"{prefix}{i:02d}{j:02d}", "row": i, "col": j,
                        "lon": (x0 + x1) / 2, "lat": (y0 + y1) / 2,
                        "west": x0, "south": y0, "east": x1, "north": y1,
                        "area_ha": polygon_area_ha(ring), "kind": "grid"})
    return out


def chip_units(chip_ids: Iterable[str], events: Iterable[str], splits: Iterable[str], bounds: np.ndarray,
               chip_px: int, unit_px: int, pixel_m: float = 20.0) -> list[dict[str, Any]]:
    """Pseudo-villages: each chip of chip_px x chip_px is cut into (chip_px // unit_px)^2 square units.
    A unit inherits its chip's event and split, so unit-level work can never leak across events."""
    k = chip_px // unit_px
    out = []
    for c, ev, sp, b in zip(chip_ids, events, splits, bounds):
        w, s, e, n = [float(v) for v in b]
        for i in range(k):
            for j in range(k):
                r0, c0 = i * unit_px, j * unit_px
                out.append({"unit_id": f"{c}_u{i}{j}", "chip": str(c), "event": str(ev), "split": str(sp),
                            "r0": r0, "c0": c0, "r1": r0 + unit_px, "c1": c0 + unit_px,
                            "lon": w + (c0 + unit_px / 2) / chip_px * (e - w),
                            "lat": n - (r0 + unit_px / 2) / chip_px * (n - s),
                            "area_ha": (unit_px * pixel_m) ** 2 / 1e4, "kind": "chip"})
    return out


def units_to_geojson(units: list[dict[str, Any]]) -> dict[str, Any]:
    feats = []
    for u in units:
        w, s, e, n = u["west"], u["south"], u["east"], u["north"]
        props = {k: v for k, v in u.items() if k not in ("west", "south", "east", "north")}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}})
    return {"type": "FeatureCollection", "features": feats}


def load_admin_geojson(path: Path, id_field: str, name_field: str | None = None) -> list[dict[str, Any]]:
    """Public admin polygons (for example a geoBoundaries ADM3/ADM4 or Survey of India village GeoJSON) into
    the unit table schema. Multipolygons use their largest part for the centroid; area sums all parts."""
    gj = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        area = sum(polygon_area_ha([tuple(p) for p in poly[0]]) - sum(polygon_area_ha([tuple(p) for p in h]) for h in poly[1:])
                   for poly in polys)
        pts = np.array([p for poly in polys for p in poly[0]], float)
        out.append({"unit_id": str(f["properties"][id_field]),
                    "name": str(f["properties"].get(name_field, "")) if name_field else "",
                    "lon": float(pts[:, 0].mean()), "lat": float(pts[:, 1].mean()),
                    "west": float(pts[:, 0].min()), "south": float(pts[:, 1].min()),
                    "east": float(pts[:, 0].max()), "north": float(pts[:, 1].max()),
                    "area_ha": area, "kind": "admin"})
    return out
