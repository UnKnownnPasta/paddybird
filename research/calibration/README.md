# Calibration evidence for presentation/calibration_deck.pptx

`python research/calibration/analyse.py` (repo root) reads `training/calibration/reports/sar_water_otsu_chips.csv`
(408 usable Sen1Floods11 chips, per-chip raw score and right/wrong label) and `config/calibration/sar_water_otsu.json`
(shipped logistic map), and writes `results.json`. Seeded, no downloads.

- Test A: 82 test-split chips, shipped map vs raw score. ECE (10 bins) 0.139 -> 0.074 reproduces `fit_water.py` output; bootstrap 2,000 resamples.
- Test B: for each of 11 regions, refit a logistic (Platt) map on the other 10 regions (all splits) and score the held-out one. Same procedure as `paper/analysis/experiments.py` (E2); +29/+20/+10/-31 reproduce.
- "Confidence error" = ECE = sum over bins of (n_bin/n) * |mean confidence - fraction right|. Right = area within +/-20% of max(label, 5% valid area).
- Baseline = the raw score used as the stated confidence.
