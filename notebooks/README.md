# Paddybird notebooks

Step-by-step, runnable implementation of the five layers in `docs/LAYERS.md`. The earlier FastAPI/Leaflet prototype (EvidEO) is deprecated and kept only in the archived SatClip repository.

| Notebook | Layer | Reads | Writes (`notebooks/artifacts/`) |
|---|---|---|---|
| `01_data_platform.ipynb` | 1 Data + platform | public chips, STAC | `layer1/` chips, units, roads, receipts |
| `02_mapping.ipynb` | 2 Mapping | `layer1/` | `layer2/` calibrated P(flooded paddy) per pixel, duration |
| `03_estimation.ipynb` | 3 Estimation | `layer1/`, `layer2/` | `layer3/` theta_u, calls, P_u |
| `04_field_planning.ipynb` | 4 Field planning | `layer1/`, `layer2/`, `layer3/` | `layer4/` checks, routes, inclusion probs |
| `05_tool.ipynb` | 5 Tool | all | `layer5/` unit-calls table, route view, card |
| `06_live_region_demo.ipynb` | live Indian paddy region on top | STAC | `demo/` (no accuracy claim, no ground truth) |

## Rules every notebook follows

1. **No overfitting.** Splits are by event or region, never by tile. Thresholds, calibration and hyperparameters are fit on train/val only; the test split is touched once, at the end, in a clearly marked cell. Report the test numbers even if they are worse than val.
2. **Reproducible.** Fixed seeds, pinned versions in `notebooks/requirements.txt`, small cached sample in `notebooks/data/` so a notebook runs top to bottom offline in minutes on CPU. Every notebook ends with an assertion cell that checks the key metric against a stated bound.
3. **Contract between layers is files**, not imports: parquet/npz/json under `notebooks/artifacts/layerN/`, each with a `MANIFEST.json` (schema, shapes, seed, source hashes). A later notebook must run from the earlier layer's committed small artifacts if the earlier notebook was not re-run.
4. Reusable code goes in `notebooks/paddybird/` (importable package, no side effects on import). Notebooks stay narrative: markdown explaining the step, short code cells, a figure per step.
5. Style: English, no em dashes anywhere (markdown, comments, plots). Name is Paddybird; do not reintroduce the hackathon framing.
6. Code adapted from the earlier prototype or from `research/` is copied into `notebooks/paddybird/`, never imported.
