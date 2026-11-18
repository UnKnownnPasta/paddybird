# The five layers

Paddybird turns a flood map and a small, routed field sample into a per-unit call ("flooded or not", with a confidence). Each layer is one notebook in `notebooks/`, and layers pass files to each other under `notebooks/artifacts/layerN/` (see `notebooks/README.md`).

```
 5  TOOL            what officers and field staff touch
 4  FIELD PLANNING  which checks, which roads                       (algorithm)
 3  ESTIMATION      unit number, always-answered call, P_u          (algorithm)
 2  MAPPING         calibrated flooded-cropland probability per pixel
 1  DATA + PLATFORM scenes, chips, units, roads, receipts
```

| Layer | Notebook | What it does | Tested how |
|---|---|---|---|
| 1 Data and platform | `01_data_platform.ipynb` | Sen1Floods11 chips with an event-level split, STAC scene search and window reads, units, OpenStreetMap road graph, receipts that store survey inclusion probabilities, revisit-gap model | Leakage assertion: no event in two splits |
| 2 Mapping | `02_mapping.ipynb` | SAR water threshold, boosted pixel model, fusion per land cover, calibration, cropland mask, semi-synthetic submergence duration | Test events scored once; Otsu baseline beside every model |
| 3 Estimation | `03_estimation.ipynb` | Stratified, shrunk, prediction-powered estimate of each unit's flooded share; always-answered call `[theta_u > 0.25]` with `P_u = Phi((theta_u - 0.25) / s_u)`; cluster-robust variance; Horvitz-Thompson and Hajek weights | Monte Carlo over check draws on test units; map-only and checks-only baselines |
| 4 Field planning | `04_field_planning.ipynb` | Next check = largest expected drop in wrong calls; flood-aware routing (Dijkstra on a flood-priced road graph, gain per extra minute); randomised village selection with known inclusion probabilities | Fixed-seed scenarios, tuning seeds kept apart from evaluation seeds |
| 5 Tool | `05_tool.ipynb` | Unit-calls table, evidence card with receipt hash, officer day-route view, offline field-check entry, farmer-report cross-check | Assertions on receipts and call coverage |
| Demo | `06_live_region_demo.ipynb` | Live Sentinel-1 scenes over an Indian paddy district, run through the chain | No field ground truth, so no accuracy claim |

## Decisions that hold across layers

- **No abstain state.** Every unit gets a call; `P_u` carries the uncertainty. A unit with no field checks falls back to the raw map call.
- **Events, not tiles, are split.** Fit on train and validation events, score test events once.
- **Paddy is a proxy.** The mask is ESA WorldCover cropland. There is no paddy label in the chips.
- **Field checks are simulated** from hand labels. No officers or trips were observed.
