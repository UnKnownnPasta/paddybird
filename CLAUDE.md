# Project memory

- This repo is the team's **Mini Project (BCS586)** at RVITM, Dept. of CSE. It grew out of an earlier prototype by the same group; the hackathon framing (event name, problem-statement ID, theme) has been deliberately removed. Do not reintroduce it.
- Team: Nikhil S Rao (1RF24CS112), Sai Bhuwan S (1RF24CS136), Yashita Murlidhar Mandavilli (1RF24CS183), Shashwat Mittal (1RF24CS145). Guide: **Mr. S Murugan** (not "Murugan S"), Assistant Professor, Dept. of CSE, RVITM. He approved the move to the flooded-paddy estimation direction.
- **Project name: Paddybird** (chosen 2026-11-17; the Indian pond heron that stands in paddy fields watching the water). Earlier names EvidEO, Tellio and SatClip are retired. The earlier FastAPI/Leaflet prototype is archived in the private SatClip repository; this repo (`paddybird`) starts clean from it. Use Paddybird everywhere, including code identifiers.
- Direction: flooded-paddy (in practice flooded-cropland) area estimation. A calibrated SAR map plus a small, routed field sample gives a per-unit call. Five layers, one notebook each, in `notebooks/` (see `docs/LAYERS.md`). The partial report is in `docs/report/` (text in `docs/report/build/build.js`); the NCDTE-2026 paper is in `paper/ncdte/`.
- **No abstain state.** Every unit gets a call, and `P_u` carries the uncertainty. Do not bring back an "insufficient evidence" rule.
- **Evaluation rules:** split by flood event, not by tile; fit on train and validation events only; score test events once; report val-test gaps and a baseline beside each model; say when a result is simulated. Say "events not used for fitting", not "held out".
- Environment: one shared venv at `.venv/` (Python 3.11) built from `notebooks/requirements.txt`, kernel name `paddybird`. Run notebooks with `python -m nbconvert`, not `python -m jupyter nbconvert`.
- Style: English, no em dashes anywhere (docs, slides, code comments, papers).
- Cover details: V semester (Odd), academic year 2026-2027.
