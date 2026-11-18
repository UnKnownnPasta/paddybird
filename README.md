# Paddybird

Paddybird is the Indian pond heron that stands in paddy fields watching the water. It is also our Mini Project (BCS586) at RVITM, Dept. of CSE: estimating flooded cropland per unit from a calibrated SAR flood map plus a small, routed field sample, with an honest error bar and no "undecided" state.

The question the project asks: how many wrong unit calls does a flood map leave on flood events it has not seen, and how many can a few routed field checks remove?

## Layout

| Path | What |
|---|---|
| `notebooks/` | The five layers as runnable notebooks (`01` to `06`), the `paddybird` helper package, committed artifacts and a small offline data cache |
| `paper/ncdte/` | NCDTE-2026 paper (Word) and the script that builds it |
| `docs/` | `LAYERS.md`, the proposal, the partial mini project report and its build sources |
| `research/` | The calibration, threshold-allocation and routing simulations that came before the notebooks |
| `archive/` | Notes on the ~225 papers we read, one file each |
| `deck/why/` | The "why it matters" deck |

## Run it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r notebooks/requirements.txt     # Windows; use .venv/bin/python on Linux or macOS
.venv/Scripts/python -m ipykernel install --user --name paddybird
.venv/Scripts/python notebooks/run_all.py                              # runs 01 to 06, checks each final assertion cell
```

Notebook 04 takes about 10 minutes on CPU; the others take 1 to 3 minutes. Notebooks run offline from `notebooks/data/` (set `PADDYBIRD_OFFLINE=1`) and fetch live data otherwise. Use `python -m nbconvert`, not `python -m jupyter nbconvert`, inside the venv.

## Rules the notebooks follow

Splits are by flood event, never by tile. Everything is fit on train and validation events, and the test events are scored once, in a marked cell. Seeds are fixed. Where a result is simulated, a notebook says so.

## Limits

Paddy is a proxy (WorldCover cropland). The map counts about 60% of the labelled flooded cropland area. Field checks and road flood probabilities are simulated. Two test events, and only India has test units. See Section 6 of the paper for the full list.

## Team

Nikhil S Rao (1RF24CS112), Sai Bhuwan S (1RF24CS136), Yashita Murlidhar Mandavilli (1RF24CS183), Shashwat Mittal (1RF24CS145). Guide: Mr. S Murugan, Assistant Professor, Dept. of CSE, RVITM.

The earlier prototype (EvidEO, a FastAPI and Leaflet evidence-card app) is archived in the private SatClip repository.
