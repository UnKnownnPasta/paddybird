# Threshold-Targeted Survey Calibration of Radar Flood Maps for Crop-Insurance Units

**Subtitle:** an always-answered call on the 25 percent localised-loss rule for every unit, with a calibrated probability, from Sentinel-1 radar and a small, adaptively placed field sample

**Prepared by:** Team Stardust, RVITM
**Date:** 11 November 2026, revised 17 November 2026 (novelty re-checked against 2026 literature; algorithm section rewritten; first simulation result added)
**Status:** proposal. The mapping pipeline exists and the allocation algorithm has a first synthetic simulation (section 5.4, `research/threshold_alloc/`). The U-Net, fusion layer, real-data evaluation and the tool are planned, not measured.

---

## 1. Summary

Indian crop insurance (PMFBY) brings paddy inundation back as a localised-calamity cover from Kharif 2026. The cover was withdrawn in 2018 because, in the Ministry's words, of "the difficulty of assessing submerged crops". The existing localised-claim procedure already turns on one number: the share of insured crop area affected inside an insurance unit, with a legal threshold at 25 percent, and it already requires a sample survey.

This project builds the missing instrument for that number. A multi-layer Sentinel-1 flood mapper produces a flooded-paddy map. A statistical layer then combines the map with a small field sample to give, for every insurance unit, **a call (above or below 25 percent), the flooded paddy share, and a calibrated probability that the call is right**. Every unit is always answered. The same layer tells the survey team where the next field checks do the most good, so the answers sharpen as checks arrive.

The research contribution is **threshold-targeted allocation**: the survey planner chooses each next field check to minimise the expected number of wrong 25 percent calls across all units, rather than to minimise estimator variance. The estimators underneath (prediction-powered inference, stratified and model-assisted estimation, active and adaptive labelling) are established and are used as published; section 3 lists exactly which parts are prior art. The application to radar flood area at insurance-unit scale, and the decision-aware allocation rule, are what we claim. It is not a new flood detector and not a new estimator.

---

## 2. Project requirement and proof of application

### 2.1 The requirement, in the scheme's own text

All quotes below are from sources read in full (section 8, group A). Section numbers in the 2018 guidelines are as they appear in the body text; the PDF's index numbers differ, so check them against the PDF before formal citation.

| What the rules say | Source |
|---|---|
| "Paddy inundation reintroduced under localised calamity", "To be rolled out from Kharif 2026" | PIB release 2191224, 18 Nov 2025 [G2] |
| "Paddy inundation was removed from the localised calamity category in 2018 due to concerns about moral hazard and the difficulty of assessing submerged crops." | [G2] |
| The change is meant to give "timely and technology-based claim settlement"; states expected to benefit include Odisha, Assam, West Bengal, Tamil Nadu, Kerala, Karnataka, Maharashtra and Uttarakhand | [G2] |
| Inundation is where the field "is covered or submerged by water ... and where water stays for prolonged period and causes visible damage to the crop" | Operational Guidelines 2018, Sec. 21.5.1, p. 49 [G1] |
| "If the affected area under a notified crop is more than 25% of the total insured area in a notified insurance unit, all the eligible farmers ... would be deemed to have suffered localised loss" | [G1] Sec. 21.5, p. 49 to 50 |
| "Percentage of loss would be arrived at by Insurance Company through requisite percentage of sample survey as decided by the Joint Committee of the affected area." | [G1] Sec. 21.5 |
| Farmer intimation within 72 hours; joint assessment by the insurer's loss assessor, the block agriculture officer and the farmer; assessment within 10 days in the text (72 hours in Table 11) | [G1] Sec. 21.5, 21.5.6, Table 11 |
| The insurance unit for major crops is the "Village/Village Panchayat or any other equivalent unit" | [G1] Sec. 7.2, p. 8 |
| States "shall adopt technology, such as satellite and UAV remote sensing" for, among others, "loss assessment"; satellite "smart sampling" can cut crop-cutting experiments "by about 30-40%" | [G1] Sec. 2.14, Sec. 20.1 |

### 2.2 Why this is an estimation problem, not a mapping problem

The decision the rules require is not "is this pixel water". It is:

> For this insurance unit, is the affected share of insured paddy area above 25 percent, and what is the loss percentage?

Three properties of that question define the project.

1. **It is an area share over a unit**, so what matters is the error of a total, not pixel accuracy. A map can have high pixel accuracy and still give a biased total.
2. **A sample survey is already mandated.** A method that needs a small field sample asks for nothing the procedure does not already require. The open quantity is the "requisite percentage", which no rule fixes; a principled way to choose it is itself useful.
3. **The deadline is days**, during monsoon cloud, which rules out optical imagery and leaves radar.

### 2.3 Why existing practice does not meet it

- **The yield system does not model floods.** The YES-TECH manual treats "Unseasonal rains/Floods/Cyclones (submergence, lodging, panic harvest etc)" through a "Correction Factor" because the yield models do not parameterise them. It gives no radar flood method, threshold or accuracy figure [G5].
- **The nearest operational system stops at villages and was never an insurance product.** The RIICE brief states the system "does not have the technical ability to monitor crop growth on individual small plots", reports no flood accuracy, and says "No insurance system has been installed using the technology" (as of 2019) [G4].
- **Trust in satellite-only settlement is contested.** A 2026 field study of Madhya Pradesh, the only major state giving satellite-based yield 100 percent weight, records insurers' own remote-sensing teams admitting "room for 20 to 30 per cent error" and district officials calling ground-truthing sometimes "a procedural exercise". That study concerns soybean yield, not floods; it is cited here only as evidence that a satellite number without a stated error and a real ground check is not accepted [R7].
- **Timing is biologically tight.** "Most higher yielding modern rice varieties die within a week of complete submergence", and flash floods last "often for up to 2 weeks" [R3]. A decision tool has to work from the first one or two radar passes.

### 2.4 Limits of this proof of application

- The 2018 guidelines predate the change and still carry the footnote "Inundation peril is not applicable in case of hydrophilic crops like Paddy". The procedure quoted above is the general localised-claim procedure; we assume the paddy cover will follow it, which the press release suggests ("in accordance with the PMFBY Operational Guidelines") but does not spell out.
- No operating procedure for the paddy cover, no list of states that opted in, and no submergence-duration or crop-stage threshold was found. A Lok Sabha answer said to mention such a procedure could not be opened.
- The 25 percent rule is defined on insured area and on farmers who reported in time. Insured-plot records are not public. Without them the tool estimates the share of paddy area flooded, which is a proxy.
- We have no access to officers, insurers or real claims. The application case is therefore theoretical, as the brief for this document requires.

---

## 3. Prior art and what this project does differently

Only works read in their entirety are used for claims in this section. Works we could not read in full are listed in section 8, group C, and nothing here depends on them.

### 3.1 The statistical method

| Work | What it does (verified) | What this project does instead |
|---|---|---|
| Angelopoulos et al., Prediction-Powered Inference [S2] | Combines a small labelled sample with many model predictions to give valid intervals "without making any assumptions on the machine-learning algorithm". Assumes labelled and unlabelled data are i.i.d. from one distribution, or a uniform random sample of a finite population. One remote-sensing example: Amazon deforestation. Covariate shift is handled only with known weights. The method can be worse than the classical estimate when the model is poor. | Applies the estimator to flooded area from radar, per insurance unit, under a stratified design, and measures when it helps and when it does not. |
| Lu, Kluger, Bates, Wang [S1] | Uses the same idea for regression coefficients estimated from map products. Area estimation is in Appendix F (early versions had area as a headline): PPI, stratified, post-stratified and **stratified (weighted) PPI** are all run on Amazon deforestation area, and the PPI mean estimator is shown to coincide with the model-assisted estimator of McRoberts et al. 2022 and to be nearly equivalent to the post-stratified estimator. Uses a probability sample of ground truth; no flood, no radar, no decision threshold. | Uses their estimator as published. Adds the unit-level 25 percent decision, adaptive allocation of checks to that decision, and flood-specific failure tests. |
| Li, Irgau, Janmohamed, Rieckmann, Lobell [S5] | The closest analogue. Estimates mean crop yield per area-insurance zone by correcting field-photo predictions with crop cuts, to "make area-based crop insurance more affordable". Reports 73 percent efficiency gain for rice and 12 to 23 percent for maize. Evidence comes from resampling a fully labelled dataset; random selection of fields is assumed, not shown. | Targets a different insured quantity (flooded area share against a legal threshold), a different proxy (radar map, available for every pixel with no field visit), and drops the assumption that reports arrive at random. |
| Stehman, Fonte, Foody, See [S3] | Sets out how volunteered, non-probability data can enter area estimation: as a certainty stratum, or as an auxiliary variable with a separate probability sample. Contains no empirical case study, only hypothetical tables. Finds that using such data alone cannot guarantee validity. | Implements both options for farmer loss reports and measures them on flood data. |
| Zaytar et al. (Microsoft), "Crop Mapping Evaluation under Sampling Bias" [A1] | Inverse-probability-weighted PPI to correct map evaluation for non-random field labels (road-side, large-parcel, low-lying). Weights estimated from satellite embeddings. Reports that the correction is fragile: effective sample size fell to 20 of 2,478 labels on one dataset, and 95 percent intervals covered the truth in fewer than 95 percent of runs. Names "where to collect new labels" as open. | The weighting method is theirs. We test it on farmer loss reports for flood area, expect the same fragility, and report where it fails. |
| Mohanty & Khanna, AdaStrat-ASI [A2]; Wu, Nair, Maechler, Candes, Pro-Active Inference [A3] | Adaptive, importance-weighted label acquisition with valid confidence intervals for a mean, with Neyman-style stratum allocation [A2] and without-replacement sequential selection [A3]. Objective is estimator variance or interval width. No threshold decision, no many-unit decision objective, no remote sensing. [A3] reports under-coverage at small budgets for rare outcomes. | Our allocation rule targets a different objective: the expected number of wrong 25 percent calls across units. We compare against a variance-minimising (Neyman-style) allocation as the strongest baseline. |
| Kawano, Li, Parker, prediction-powered smoothing [A4] | Fay-Herriot smoothing of per-domain PPI/GREG estimates; estimates every domain mean; no adaptive allocation and no threshold decision. | Our pooled stratum prior is a light version of this borrowing; full small-area smoothing across units is a planned extension, not a claim. |
| Petrou-Zeniou, "Uncertainty in Compound Decisions" [A5] | Simultaneous (multiple-testing) inference for decisions made over many units from noisy unit estimates. Does not acquire labels and does not use predictions. | Related framing for the many-unit decision; we do not claim its guarantees. |
| Broska & Howes, Cluster-Robust PPI++ [A6]; Shirota, spatial PPI [A7]; Rizvi et al. with Generali, PPI for time series across space [A8] | Valid PPI intervals under within-cluster dependence [A6], spatially dependent finite populations [A7], and time-series dependence for insurance weather risk [A8]. | Supplies the variance corrections we need when flood errors cluster in space. Evidence that insurers are adopting PPI, for a different quantity. |
| Angelopoulos et al., Conformal Risk Control [S7] | Bounds the expected value of a monotone loss, such as the fraction of true pixels missed, under exchangeability. | Does not use it for the headline number. Error in an area total is two-sided and not monotone in a threshold, so the theorem does not apply directly. This is why the project takes the survey-estimation route. |

### 3.2 Flood mapping and its guarantees

| Work | What it does (verified) | What this project does instead |
|---|---|---|
| Bonafilia et al., Sen1Floods11 [F1] | 4,831 chips over 11 flood events, 446 hand-labelled, India included as one event. Scores pixel overlap on chips. A per-event Otsu threshold on VH scores 0.3591 mean IoU for all water (0.3862 on the Bolivia hold-out); the network trained on hand labels "was never the best performing model by any metric". Only one event is held out. | Uses it as the main labelled data, and evaluates the error of unit totals with every region held out in turn, not pixel overlap. |
| Bountos et al., Kuro Siwo [K1] | 43 flood events with expert labels separating flood from permanent water; the best model reaches 80.12 F1 for flood. Authors list flooded vegetation among limitations. | Second labelled set, used for cross-event tests. |
| Krullikowski et al., Copernicus GFM likelihood [K2] | The operational service gives each pixel a 0 to 100 likelihood by averaging three algorithms. It is not fitted to labels, and a single-site check shows it over-predicts flood. | Provides an interval on the unit total that is checked against labels, which a per-pixel index cannot give. |
| Martinis, Twele, Voigt [K3] | Origin of split-based automatic radar thresholding with minimum-error thresholds. | Already implemented as the physics layer of the mapper. |
| Hasan et al., "Safe test-time adaptation for SAR flood mapping" [F2] | Adapts a network to a new flood without labels, using radar darkness, HAND and slope checks, then bounds the miss rate. The bound holds for "the mean miss rate over floods, not on each flood"; single events still miss up to 83 percent of water. No area estimates, no crops, no flooded vegetation. This is an unreviewed manuscript in a code repository created on 10 November 2026. | Complementary. It improves the map with no labels; this project corrects the total with a few labels and gives a per-unit interval. Its adapted map could serve as one of our layers. |
| Ronneberger, Fischer, Brox, U-Net [F5] | Encoder-decoder segmentation network with skip connections. | Architecture of the learned layer. |

### 3.3 Radar for crop insurance

| Work | What it does (verified) | What this project does instead |
|---|---|---|
| Thapa, Horanont, Neupane [R1] | Verifies 859 Thai insurance claims per parcel with Sentinel-1, Sentinel-2 and farmers' photos; a decision tree on radar reaches 98.77 percent. Accuracy is the fraction of claimed events detected: every reference case is a claim, so there is no false-positive rate. The classifier was trained on 124 points from one date. Independent field check on 7 plots. No intervals, no treatment of who chooses to claim. Data are proprietary. | Estimates area over whole units, including land nobody claimed for, with an interval, and treats self-selected claims as a statistical problem. |
| Murugesan and Mathieu [R2] | The closest Indian work. Maps prevented and failed rice sowing in 24 Gram Panchayat insurance units in Puri and Khurda, Odisha, and applies the scheme's 75 percent rule; overall accuracy 92.3 percent. Reference data are 20 fields for 2019 and none independent for 2018. No intervals. Standing-crop inundation is not targeted, and short floods between 12-day passes may be missed. | Targets standing-crop inundation and the 25 percent rule, and puts an interval on each unit so that a unit near the line is not decided by map error. |
| RIICE brief [G4] | Sentinel-1 rice area and yield at village scale; flood accuracy not reported; experimental. | Reports flood accuracy and uncertainty explicitly. |
| Singha et al. [R5]; Chen et al. [R6] | Open 10 m rice maps: Bangladesh and Northeast India for 2017 [R5]; 23 Indian states for 2018, 2020 and 2022 [R6]. Both name mixed pixels in small fields as an error source. In [R6] the threshold is set so mapped area matches state statistics, so its totals are not independent estimates. | Uses them only as the paddy mask, and carries the mask's error into the stated range. |
| Segami et al. [R4] | With L-band radar, the difference between inundated and dry paddy shrinks as the crop grows and vanishes at about 60 to 70 cm plant height. Study is of shallow managed water in Japan, not floods, and makes no comparison with C-band. | Motivates testing NISAR L-band as an extra layer, and warns that it will not rescue detection under tall crops. |

### 3.4 Statement of novelty and its limits

**Prior art, stated plainly.** The estimator is established survey statistics: the PPI mean estimator is the model-assisted difference estimator [S1, A6, McRoberts et al. 2022; Mozer 2026 makes the point in full]. Stratified PPI for area exists [S1, Fisch et al. 2024]. Adaptive and active label allocation with valid intervals exists [A2, A3]. Weighting for non-random reference labels exists [A1]. Small-area smoothing of PPI estimates exists [A4]. An insurance-zone application of PPI exists for yield [S5]. None of this is claimed.

**What we claim, bounded by what was read.** Among the works read in full, none (i) applies prediction-powered or model-assisted estimation to a radar flood map, (ii) targets a legal area-share threshold per insurance unit, or (iii) allocates field checks to minimise the expected number of wrong threshold calls across many units. Our contribution is the combination (i) to (iii), the allocation rule in section 5.2, and an evaluation of where it breaks (closed canopy, short floods, self-selected reports). A 2022 conference talk (Dasgupta & Waske, ESA Living Planet Symposium) reports Olofsson-style bias-corrected flooded area from Sentinel-1 and lists confidence intervals as future work; its published form [Landwehr et al. 2024] could not be read in full.

**Limits of the check.** Three relevant works could not be read in full (section 8, group C). The 2026 search (section 8, group D) used one broad discovery query per facet and full-text reads of the closest hits; it is not a systematic review. Commercial providers were not surveyed. The claim must be rechecked before submission.

---

## 4. Technical architecture

```
Sentinel-1 scenes        DEM, HAND, slope       Rice mask        Unit boundaries
(before, during, after)  permanent water        [R5], [R6]       (village or panchayat)
        |                      |                    |                   |
        v                      v                    |                   |
+-----------------------------------------+        |                   |
| 1. MAPPING LAYERS                       |        |                   |
|  a. physics threshold (built)           |        |                   |
|  b. U-Net on Sen1Floods11 (to build)    |        |                   |
|  c. terrain and permanent-water priors  |        |                   |
|  d. per-pixel fusion -> P(flooded)      |        |                   |
|  e. submergence duration across passes  |        |                   |
+-----------------------------------------+        |                   |
        |                                           |                   |
        +----------------> flooded-paddy map <------+                   |
                                   |                                    |
                                   v                                    v
+---------------------------------------------------------------------------+
| 2. ESTIMATION AND ALLOCATION LAYER (the research contribution)            |
|  a. stratify each unit's pixels by map output (flooded / dry)             |
|  b. stratified PPI estimate: corrected share per unit, with the           |
|     paddy-mask error carried into the denominator                         |
|  c. call for EVERY unit: above or below 25%, plus P(call is right)        |
|  d. threshold-targeted planner: next check = largest expected drop in     |
|     wrong calls, summed over units                                        |
|  e. farmer reports as a certainty stratum or weighted auxiliary           |
|  f. loop: new checks update (b) and (c); answers sharpen, never withheld  |
+---------------------------------------------------------------------------+
                                   |
                                   v
+---------------------------------------------------------------------------+
| 3. TOOL: event board, unit calls, survey plan, field entry, unit dossier  |
+---------------------------------------------------------------------------+
```

**What exists today** (this repository): live Sentinel-1 and Sentinel-2 retrieval from public catalogues, district boundaries for 735 districts, the physics threshold layer with VV and VH, a terrain mask (built, off by default), tiled processing on CPU, and receipts that re-ran to identical output on 8 of 8 demo questions. Measured weaknesses that this proposal responds to: the threshold detector scores 0.362 mean IoU on the Sen1Floods11 test chips, the same level as the published Otsu baseline of 0.3591 [F1]; and its confidence is over-stated by about 20 points when moved to Indian chips, an error that a refit on 8 local chips largely removes.

**What must be added:** the U-Net and fusion layers, a permanent-water layer, village or panchayat boundaries (only district outlines are held now), the whole estimation layer, and the tool.

---

## 5. Methodology

### 5.1 Mapping layers

1. **Physics layer.** Split-based minimum-error thresholding on VV and VH [K3], as built.
2. **Learned layer.** A U-Net [F5] trained on Sen1Floods11 [F1] and Kuro Siwo [K1].
3. **Priors.** Height above nearest drainage and slope to exclude terrain where standing water is implausible; a permanent-water layer so rivers and wetlands are not counted as flood.
4. **Fusion.** A small per-pixel model over the outputs of layers 1 to 3, trained with whole regions held out.
5. **Duration.** Flood persistence across consecutive passes, since crop loss depends on days submerged [R3].
6. **Optional L-band layer.** NISAR geocoded backscatter is free, posted at 10 or 20 m over most land, on a 12-day cycle, with validated products from 21 October 2026 [G6]. Tested only if time allows.

The map is deliberately not required to be perfect. Its job is to be informative enough that a small sample can correct it; the estimator's interval narrows as the map improves [S2].

### 5.2 Estimation and allocation layer

**Notation.** Unit u has N_u paddy pixels. The map splits them into two strata h (flooded, dry) of sizes N_uh and weights W_uh = N_uh / N_u. A field check reveals the true state Y of one pixel. n_uh checks have been made in stratum h; k_uh of them were flooded. tau = 0.25.

**Step 1. Estimate (stratified PPI, as published [S1, App. F; A-series for variants]).** A pooled stratum rate pi_h is learned across all units from the checks so far (a light form of borrowing across units), and each unit's stratum rate is shrunk toward it:

```
p_uh   = (k_uh + m * pi_h) / (n_uh + m)                       m = prior strength (2)
theta_u = sum_h  W_uh * p_uh                                   flooded share of paddy
var_u   = sum_h  W_uh^2 * p_uh (1 - p_uh) / (n_uh + m + 1)     sampling variance
```

When the map is the only information (no checks), theta_u is the raw map fraction. The estimate stays valid when the map is poor, because the correction comes from the checks [S2]. The paddy-mask error enters the denominator through the delta method for the ratio of two corrected totals; this is planned and not in the first simulation.

**Step 2. Call every unit.** There is no undecided state:

```
call_u = above if theta_u > tau, else below
P_u    = Phi( (theta_u - tau) / sqrt(var_u) )        probability the unit is truly above
```

A unit at 26 percent is answered "above, P = 0.55". P_u says how much to trust the call; it never withholds it.

**Step 3. Allocate the next check (the contribution).** Treat theta_u as normal with mean theta_u and variance var_u. The chance the current call is wrong is Phi(-|d_u| / s_u), with d_u = theta_u - tau and s_u^2 = var_u. One more check in stratum h of unit u lowers the variance to s'^2 (computed from the formula above with n_uh + 1). The planned new estimate d' is then random, with variance s_u^2 - s'^2, so the expected wrong-call probability afterwards is a one-dimensional integral (15-point Gauss-Hermite quadrature):

```
V_after(u,h) = E_{d' ~ N(d_u, s_u^2 - s'^2)}  Phi( -|d'| / s' )
gain(u,h)    = Phi(-|d_u| / s_u)  -  V_after(u,h)
next check   = argmax over (u,h) of gain(u,h)            (per batch: top-k distinct candidates)
```

This is a one-step look-ahead on the expected number of wrong calls summed over all units. Because it integrates over the future estimate, it does not stall at units sitting exactly on the line (a plain derivative of the error probability would be zero there). The baseline it must beat is the decision-blind greedy rule that minimises total variance (the Neyman-style allocation of [A2]).

**Step 4. Keep the answer valid while sampling is adaptive.** Choosing checks from earlier answers breaks the textbook i.i.d. interval [A3 states this requirement]. The first simulation (5.4) uses plain stratum means and measures the resulting bias. The production version will draw each check with a known inclusion probability and use the importance-weighted residual of [A3] and Active Statistical Inference, so that P_u keeps its meaning. Until then P_u is reported with its measured calibration (5.4), not with a guarantee.

**Design choices the project will test:**

| Choice | Why | Status against the literature |
|---|---|---|
| Decision-targeted allocation (step 3) against variance-minimising allocation | The goal is fewer wrong calls, not a narrower interval | New to our reading; baseline is [A2]/[A3]-style |
| Borrow the stratum rate across units (pooled prior; later, Fay-Herriot smoothing) | A village may get only a handful of checks | Smoothing of PPI estimates exists [A4]; flood case untested |
| Spatially aware variance (cluster-robust or block bootstrap) | Flood errors are spatially clustered | Method exists [A6, A7]; to be applied |
| Farmer loss reports as a certainty stratum or weighted auxiliary | Reports come from affected farmers, not at random | Method exists [S3, A1]; fragile there, expected fragile here |
| Carry rice-mask error into the denominator | The denominator is itself a map | [R5], [R6] give no per-unit uncertainty |

**What replaces "requisite percentage of sample survey".** The planner turns it into a stopping and routing number: the total checks needed to bring the expected share of wrong calls below a chosen level, and which plots to visit first.

### 5.3 Evaluation without real claims

No real claims or field surveys are available, so evaluation is by simulation on public hand-labelled data, and the paper will say so.

- **Units.** Labelled chips, or groups of chips from one event, stand in for insurance units; the hand label is the truth.
- **Sampling.** Field checks are simulated by revealing the label at sampled pixels, under random, stratified and deliberately biased (self-selected) schemes.
- **Shift.** All models are trained with the test region held out. India is the headline case; Sen1Floods11 contains an Indian event [F1].
- **Case study.** One or two named Indian events run end to end, compared with the published NRSC or Copernicus GFM extent. Agreement with those products is reported as agreement, not as accuracy, since neither is field truth [K1, K2].

### 5.4 First measured result: wrong 25 percent calls against field checks (synthetic)

`research/threshold_alloc/sim.py` (numpy only, about a minute) simulates 200 units of 1,500 paddy pixels each. Each unit has its own true flooded share (mean 0.25, sd about 0.13) and its own map error (sensitivity about 0.75, false-positive rate about 0.08, varying by unit, so the map is biased differently in each unit). Every method answers every unit. Same estimator throughout; only the allocation of checks differs. Mean of 60 runs; the figure is `docs/figures/wrong_call_vs_checks.png`.

Wrong 25 percent calls, percent of units:

| Field checks per unit | 0 | 2 | 4 | 8 | 12 | 16 | 24 | 32 |
|---|---|---|---|---|---|---|---|---|
| Map only | 15.9 | 15.9 | 15.9 | 15.9 | 15.9 | 15.9 | 15.9 | 15.9 |
| Field only (no map) | n/a | 33.8 | 32.5 | 27.6 | 23.5 | 20.6 | 18.0 | 16.0 |
| Map + checks, equal split | n/a | 18.7 | 19.9 | 19.6 | 16.9 | 16.0 | 13.1 | 11.9 |
| Map + checks, variance-minimising | n/a | 18.4 | 18.9 | 15.7 | 14.8 | 13.9 | 11.8 | 10.9 |
| **Map + checks, decision-targeted** | n/a | 18.7 | 17.4 | **13.5** | **11.9** | **10.2** | **8.6** | **7.1** |

What this shows and does not show:

- At 32 checks per unit the decision-targeted rule makes about 40 percent fewer wrong calls than the equal split (7.1 against 11.9) and about 35 percent fewer than the variance-minimising rule (7.1 against 10.9). It matches the equal split's 32-check result (11.9) with about 12 checks per unit, roughly a third of the field effort.
- **At very small budgets (2 to 4 checks per unit) every check-based method is worse than the raw map in this setup.** A handful of noisy checks adds more variance than it removes bias. Pooling across units is only lightly tuned here; the operating advice from this run is to start from the map and let checks accumulate, and stronger smoothing [A4] is the planned fix.
- Brier score of P_u at 32 checks: 0.059 decision-targeted, 0.076 variance-minimising, 0.085 equal split, 0.120 map only (lower is better), so the stated probabilities are also better calibrated where checks are placed by the new rule.
- Mean bias of the estimate at 32 checks is -0.0013 (decision-targeted) against -0.0073 (variance-minimising). The adaptive rules use plain stratum means, so some bias is expected until step 4 of 5.2 is implemented.
- This is synthetic. Pixels are independent inside a unit (no spatial clustering), the map-error model is simple, and the numbers say nothing about real Sentinel-1 error. The next step is the same experiment on Sen1Floods11 chips grouped into units, with whole regions held out.

### 5.5 Route-aware planning on a flooded road graph (synthetic)

Field checks cost travel. In a flood the same event that creates the loss also slows the roads, and the radar flood map says which road segments are under water. The planner therefore uses the flood map twice: to estimate loss, and to price travel.

**Formulation.** A graph with junctions and village sites; edge time is the normal time, multiplied by 8 when the segment is flooded (planned from the radar map). Dijkstra from the block office gives true travel time to every site around the flooding. Each officer has a time limit per day (an orienteering problem: maximise reward within a time budget; NP-hard). The reward of a village is the expected drop in wrong 25 percent calls from 5.2 step 3, for a batch of C checks there. Heuristic: cheapest insertion by gain per extra minute across K officers, gains recomputed each morning from the checks already made.

**Result** (`research/threshold_alloc/routing_sim.py`, 30 villages, 3 officers, 4-hour days, 4 days, 12 checks per visit, 1.5 min per check, mean of 200 runs; figures `docs/figures/route_wrong_vs_days.png` and `route_example.png`). Wrong 25 percent calls after each day, percent of villages:

| Planner | Day 0 (map only) | 1 | 2 | 3 | 4 | Village visits | Checks |
|---|---|---|---|---|---|---|---|
| Nearest village first (flood-blind) | 14.2 | 13.7 | 12.7 | 11.9 | 11.6 | 47 | 565 |
| Highest gain first, travel ignored | 14.2 | 13.1 | 12.4 | 11.5 | 10.9 | 22 | 269 |
| Gain per minute, flood-blind roads | 14.2 | 13.3 | 12.9 | 12.2 | 11.7 | 29 | 354 |
| **Gain per minute, flood-aware roads (Dijkstra)** | 14.2 | 13.5 | 11.9 | 10.7 | **9.7** | 43 | 511 |

- After 4 days the flood-aware planner has about 2 points fewer wrong calls than nearest-first or flood-blind planning (9.7 against 11.6 and 11.7, roughly 17 percent fewer), and about a third fewer than the map alone. With 6,000 village-decisions the run-to-run error is about 0.4 points.
- The ordering of flood-aware over nearest-first held when days were shortened to 2 and 3 hours (11.9 against 13.5, and 11.7 against 13.0, 40 runs each). The gaps are small and this is synthetic.
- Flood-blind planning is no better than nearest-first: a plan on the dry road map overruns the day on the real flooded roads, which is the case for feeding the radar flood map into the routing.
- **Selection-bias warning, from an exploratory run.** An earlier version pooled the labels collected along routes into a shared stratum prior. Wrong calls for nearest-first rose from about 12 to about 25 percent, because villages near the depot are not a random sample of the district. The final version freezes the prior at a calibrated map value. This is the roadside-sampling bias of [A1] appearing inside our own planner, and it is why the importance-weighted estimator of 5.2 step 4 is required before any claim about P_u.

**Prior art.** Orienteering, team orienteering and informative path planning under a travel budget are established (survey: arXiv:2512.16865; informative path planning on graphs with travel budgets: arXiv:2601.17227, 2402.08841), as is flood-aware routing and road accessibility from flood extents (e.g. Sentinel-1-based network criticality, EGU 2021; Hanoi routing with edge closure, arXiv:2611.02479). A search found none that uses expected wrong threshold calls as the reward for flood-damage survey routing. Dijkstra and the insertion heuristic are standard components; the formulation is the claim.

### 5.6 What would count as success or failure

- **Success:** on held-out regions, the decision-targeted rule makes clearly fewer wrong 25 percent calls than equal and variance-minimising allocation at the same number of checks, and the stated P_u is calibrated (stated 0.8 is right about 80 percent of the time).
- **Honest failure modes, reported either way:** the corrected estimate may be no better than the map at tiny budgets (already seen in 5.4); coverage and calibration may fall under spatial clustering and adaptive sampling; routed sampling may bias unit estimates (seen in 5.5); and no correction may fully repair self-selected reports [S3, A1].

### 5.7 Other layers: candidate algorithmic ideas (not claims, not implemented)

A pass over the rest of the stack for places where an algorithm, not just a pipeline, could be contributed. Evidence level is stated for each. Only the allocation rule and routing planner (5.2 to 5.5) have any simulation behind them.

| Layer | Idea | What the search found | Next step |
|---|---|---|---|
| Duration (layer 1e) | **Interval-censored submergence duration.** Onset lies between the last dry pass and the first wet pass; recession between the last wet and the first dry. Output P(submerged at least d days) per pixel instead of a flooded flag. The PMFBY rule counts crop "affected" by prolonged water with visible damage, so affected area is not the same as flooded area, and the estimand itself should carry duration. | A European assessment found a single 12-day-revisit Sentinel-1 satellite observes about 20 percent of flood events, so censoring is the central issue. Bayesian change-point flood detection on Sentinel-1 series exists (arXiv:2504.19526). Paddy flood duration with uncertainty was not found in one extended search. | Highest-value next idea; needs a revisit-gap model and a crop-survival curve from [R3]. |
| Fusion (layer 1d) | **Multi-predictor PPI.** Treat the physics threshold, the U-Net and an external product (Copernicus GFM or NRSC) as several predictors; learn their weights per land cover or crop stage, keeping valid intervals. Detection limits depend on land cover and flood type [A227]. | Several multi-predictor PPI methods exist: arXiv:2603.27414, 2606.21232, 2604.27892, 2605.08429 (abstracts only, not read). | Method is theirs; ours would be the application and the per-land-cover weighting. Read before use. |
| Strata (layer 2a) | **Strata from the calibrated score, not two map classes.** Choose stratum boundaries on the calibrated P(flooded) by the classical cumulative-root-frequency rule, with crop stage as a second stratifier. | Classical stratification theory (Dalenius and Hodges) and stratified PPI [S1, Fisch et al.]. | Cheap to test in `sim.py`; low novelty, likely solid gain. |
| Reports (layer 2e) | **Flip value for self-selected reports.** Report, for each unit's call, the smallest selection-bias strength at which the call would flip. The call is still always given; the flip value says how robust it is. | Sensitivity and bounds for non-probability samples exist (Aronow and Lee 2013; Andridge et al. 2019 index; Hartman and Huang 2024 benchmarking; Tudball et al. 2023; Cortes-Gomez et al. 2024). No threshold-flip formulation for area calls found in one search. | Small derivation plus simulation; pairs with [A1]'s fragility finding. |
| Estimation | Cluster-robust and spatial variance; small-area smoothing | Exist [A4, A6, A7] | Apply; not a claim. |
| Tool | Conformal or rank-based flag for individual claim intimations against the pixel probability | Standard methods | Engineering, not a research claim. |

---

## 6. The tool: experience and results to show

### 6.1 Design principle

The current prototype answers a question with one figure and a confidence for a place and a date. That is a readout. A tool is something an officer works through to reach a decision they can defend. The interface is therefore organised around the officer's job after a flood, not around the map.

### 6.2 Workflow

| Step | Screen | What the officer does and gets |
|---|---|---|
| 1 | **Event board** | Picks the district and the flood. Sees which radar passes exist, days since onset, and how long each area has been under water against the one-week survival limit for ordinary varieties. |
| 2 | **Unit calls** | A ranked table of every insurance unit with an answer for every one: flooded paddy share, a call (above or below 25 percent) and the probability the call is right. Units are ordered by how likely the call is to be wrong, so the officer sees where attention helps. The map is a supporting view, not the main one. |
| 3 | **Survey plan** | The specific plots to visit next, chosen by the allocation rule (5.2, step 3), grouped into a route, with the expected drop in wrong calls if they are done. Exportable to a phone. |
| 4 | **Field entry** | For each plot: the radar before and after strip, a photo slot, and a flooded or not flooded answer. Works offline and syncs later. |
| 5 | **Live update** | As checks arrive, calls and probabilities update. The officer sees the expected number of wrong calls fall and can stop when it is low enough for the committee's purpose. Nothing was ever withheld, so there is no point at which units "become answered". |
| 6 | **Claim cross-check** | Individual intimations are listed as consistent with radar, inconsistent, or plot too small to tell. This orders inspections; it does not reject a claim. |
| 7 | **Unit dossier** | A printable record per unit: the estimate, the range, the sample and who checked it, the radar scenes, the method version and the re-run receipt. This is what goes on file with the joint committee. |

### 6.3 Results the project will present

R0 below is measured on synthetic data (section 5.4). Everything else is a planned output and has not been measured.

| # | Result | Form | Question it answers |
|---|---|---|---|
| R0 | **Wrong 25 percent calls against checks (synthetic, measured)** | Curves for map-only, field-only, equal split, variance-minimising and decision-targeted allocation | Does placing checks for the decision beat placing them for variance? (First answer: yes, about 35 to 40 percent fewer wrong calls at 32 checks per unit.) |
| R1 | Calibration of the stated probability, region held out | Stated P against observed hit rate, per region | Can the probability be believed in a place the model never saw? |
| R2 | Wrong-call rate against number of field checks on real labels | Same curves as R0 on Sen1Floods11 units | Does R0 survive real radar error and spatial clustering? |
| R3 | Decisions at the 25 percent line | Wrongly triggered and wrongly denied units, for naive pixel counting, field-only and corrected | Does it change who gets paid, and in which direction? |
| R4 | Survey effort saved | Field checks needed for the same wrong-call rate, with and without the map and with each allocation rule | Is it worth the officer's time? |
| R5 | Layer ablation | R2 and R3 repeated for threshold only, U-Net, fused, with priors | What does each mapping layer buy? |
| R6 | Self-selected reports | Coverage and bias when reports come from affected farmers, under each remedy | Can farmer reports be used safely? |
| R7 | End-to-end case study | One real Indian flood through all seven screens, with time from first radar pass to the first call on every unit, and to the target wrong-call level | Does it work as a tool, start to finish? |
| R8 | Reproducibility | Dossier receipts re-run to identical output | Can an auditor repeat it? |

---

## 7. Risks and limitations

1. **No field truth or real claims.** Evidence is simulation on public labels. The work must not claim validity for insurance settlement.
2. **Radar misses water under a closed canopy.** Even L-band loses the signal at about 60 to 70 cm plant height [R4]. The method corrects the resulting bias through the field sample, but a map that sees nothing leaves the interval no narrower than a field-only survey.
3. **Small plots.** Mixed pixels from small, fragmented fields are a named error in both rice maps [R5, R6], and the nearest operational system could not monitor individual small plots [G4]. The unit, not the plot, is the scale claimed.
4. **Revisit time.** A 12-day gap can miss a short flood entirely [R2]. The current repeat pattern over India has not been confirmed.
5. **Insured area is not observable.** The legal denominator is insured area; the tool uses paddy area unless plot records are supplied.
6. **The rules for the new cover are unpublished.** The design follows the general localised-claim procedure and may need adjusting.
7. **Novelty is bounded by our reading, and mostly sits in the application and the allocation rule.** The estimator and the adaptive-labelling machinery are prior art (section 3). See section 3.4.
9. **Adaptive sampling and the stated probability.** The first simulation uses plain stratum means under adaptive allocation and shows small bias, but P_u has no proven guarantee until the importance-weighted version (5.2, step 4) is built. Small-budget and rare-event regimes are where adaptive methods have been seen to under-cover [A3].
10. **Few checks can be worse than none.** In the synthetic run, 2 to 4 checks per unit did worse than the raw map (5.4). The tool must default to the map and show how many checks a unit has behind its call.
8. **Sen1Floods11 has few Indian chips and no stated licence in the paper or its repository** [F1]. The paper gives no per-country count; the dataset's split files, as recorded in this project's earlier runs, list 68 Indian hand-labelled chips. Indian results will have wide error bars, and data terms must be confirmed before publication.

---

## 8. Sources and reading record

Reading standard: the full text was downloaded, converted to plain text, and read from first line to last by a reader agent, which recorded the page and character counts shown. "Refs skimmed" means the body was read in full and only the reference list was skimmed. Nothing in sections 2 to 7 relies on a source outside groups A and B.

### Group A. Read in full for this document (11 November 2026)

**Statistics**

- **[S1]** K. Lu, D. M. Kluger, S. Bates, S. Wang. "Regression coefficient estimation from remote sensing maps." arXiv:2407.13659v7, 3 Jul 2025. 48 pages, 178,133 characters, read to the end of Appendix F.3.
- **[S2]** A. N. Angelopoulos, S. Bates, C. Fannjiang, M. I. Jordan, T. Zrnic. "Prediction-Powered Inference." arXiv:2301.09633v4, 9 Nov 2023 (published in Science 382:669-674). 40 pages, 151,057 characters, appendices included.
- **[S3]** S. V. Stehman, C. C. Fonte, G. M. Foody, L. See. "Using Volunteered Geographic Information (VGI) in Design-Based Statistical Inference for Area Estimation and Accuracy Assessment of Land Cover." Remote Sensing of Environment, 2018. Author accepted manuscript from the IIASA repository, not the typeset version, so page and equation numbers may differ. 46 pages, 104,973 characters.
- **[S5]** H. H. Li, M. Irgau, N. Janmohamed, K. S. Rieckmann, D. B. Lobell. "Scalable Vision-Guided Crop Yield Estimation." arXiv:2511.12999v1, 17 Nov 2025. 20 pages, 93,615 characters. The text carries no venue line.
- **[S7]** A. N. Angelopoulos, S. Bates, A. Fisch, L. Lei, T. Schuster. "Conformal Risk Control." arXiv:2208.02814v4, 13 Jun 2025. 19 pages, 68,525 characters, refs skimmed.

**Flood mapping**

- **[F1]** D. Bonafilia, B. Tellman, T. Anderson, E. Issenberg. "Sen1Floods11: a georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1." CVPR Workshops 2020. 11 pages, 64,215 characters; Figure 3 read from the rendered page.
- **[F2]** Hasan, Seum, Mursalin, Ahmed, Mahmud, Tasnim. "Safe test-time adaptation for SAR flood mapping: physics-checked self-training with a flood-level miss-rate guarantee." Manuscript `paper/main.pdf` in github.com/Mahim25800/Research-Flood, marked "Preprint submitted to Elsevier", repository created 10 Nov 2026, MIT licence. 18 pages, 79,770 characters, refs skimmed. Not peer reviewed. A later revision draft in the same repository was read only in part and is not used.
- **[F5]** O. Ronneberger, P. Fischer, T. Brox. "U-Net: Convolutional Networks for Biomedical Image Segmentation." arXiv:1505.04597v1, 2015. 8 pages, 24,931 characters.

**Insurance and rice**

- **[R1]** A. Thapa, T. Horanont, B. Neupane. "Parcel-Level Flood and Drought Detection for Insurance Using Sentinel-2A, Sentinel-1 SAR GRD and Mobile Images." Remote Sensing 14(23):6095, 2022. doi 10.3390/rs14236095. 21 pages, 94,275 characters. Note: Sections 2.1 and 3.4 of the paper swap the flood and drought claim counts given in its results tables.
- **[R2]** D. Murugesan, R. Mathieu. "Early season prevented and failed rice sowing detection using temporal Synthetic Aperture Radar data in coastal India for crop insurance applications." Smart Agricultural Technology 10:100868, 2025. doi 10.1016/j.atech.2025.100868. 12 pages, 83,878 characters.
- **[R3]** S. Singh, D. J. Mackill, A. M. Ismail. "Physiological basis of tolerance to complete submergence in rice involves genetic factors in addition to the SUB1 gene." AoB Plants 6:plu060, 2014. doi 10.1093/aobpla/plu060. 94,383 characters, refs skimmed. A field trial, not a review.
- **[R4]** G. Segami, K. Oyoshi, S. Sobue, W. Takeuchi. "Characterizing L-Band Backscatter in Inundated and Non-Inundated Rice Paddies for Water Management Monitoring." Remote Sensing 18(2):370, 2026. doi 10.3390/rs18020370. 24 pages, 107,412 characters; some tables extracted garbled and were reconstructed from the text.
- **[R5]** M. Singha, J. Dong, G. Zhang, X. Xiao. "High resolution paddy rice maps in cloud-prone Bangladesh and Northeast India using Sentinel-1 data." Scientific Data 6:26, 2019. doi 10.1038/s41597-019-0036-3. 41,621 characters. Data: figshare doi 10.6084/m9.figshare.7873157, CC BY 4.0.
- **[R6]** X. Chen, R. Shen, B. Pan, Q. Peng, X. Zhang, Y. Fu, W. Yuan. "A High-Resolution Distribution Dataset of Paddy Rice in India Based on Satellite Data." Remote Sensing 16(17):3180, 2024. doi 10.3390/rs16173180. 24 pages, 103,138 characters; parts of Sec. 3.1 to 3.3 and Table 2 were scrambled in the text layer, so only headline figures are used. Data: figshare doi 10.6084/m9.figshare.24228619, CC BY 4.0.
- **[R7]** C. Mahaur, A. Khurana. "Implementation of Yield Estimation System based on Technology (YES-TECH) in Madhya Pradesh." Centre for Science and Environment, New Delhi, 2026. 40 pages, 72,764 characters.

**Official documents**

- **[G1]** Department of Agriculture, Cooperation and Farmers Welfare. "Operational Guidelines, Pradhan Mantri Fasal Bima Yojana (Revised)." PDF created 20 Sep 2018, from pmfby.gov.in. 99 pages, 339,405 characters. A 2020 revision is referred to in [G5] but was not found.
- **[G2]** Press Information Bureau, Ministry of Agriculture and Farmers Welfare. Release 2191224, 18 Nov 2025. Read in full, together with the All India Radio item of the same date.
- **[G4]** GIZ and MCII. "RIICE In Focus: Innovation and Technology." April 2019. 4 pages, 11,727 characters. Based on the project implementers' own documentation.
- **[G5]** Mahalanobis National Crop Forecast Centre. "YES-TECH Manual for Implementation." January 2023. 48 pages, 117,447 characters of text; figures not read. Read from a copy on the Andhra Pradesh remote-sensing centre's site, not from the Ministry's own site.
- **[G6]** Alaska Satellite Facility. NISAR Data User Guide, pages "GCOV" and "Available NISAR Data", as of November 2026. Both pages read in full; linked sub-pages not read.

### Group B. Read in full earlier, per the project archive record

These carry `read_depth: full` in `archive/papers/`, with a full-text check dated 14 October 2026. They were not re-read for this document.

- **[K1]** N. I. Bountos et al. "Kuro Siwo: 33 billion m² under the water. A global multi-temporal satellite dataset for rapid flood mapping." NeurIPS 2024 Datasets and Benchmarks. arXiv:2311.12056. Archive entry 041. The second check (29 October 2026) covered the main text only, not the supplement.
- **[K2]** C. Krullikowski et al. "Estimating Ensemble Likelihoods for the Sentinel-1-Based Global Flood Monitoring Product of the Copernicus Emergency Management Service." IEEE JSTARS 16:6917-6930, 2023. doi 10.1109/JSTARS.2023.3292350. Archive entry 213.
- **[K3]** S. Martinis, A. Twele, S. Voigt. "Towards operational near real-time flood detection using a split-based automatic thresholding procedure on high resolution TerraSAR-X data." NHESS 9:303-314, 2009. doi 10.5194/nhess-9-303-2009. Archive entry 084.

### Group C. Not read in full. Not relied on. To be obtained before submission

| Source | What was read | Why it matters |
|---|---|---|
| Olofsson et al., "Good practices for estimating area and assessing accuracy of land change", RSE 148:42-57, 2014 | Abstract only (publisher captcha) | The standard reference for the stratified area estimator. Currently cited only through [S1], which reproduces it. |
| Landwehr, Dasgupta, Waske, "Towards robust validation strategies for EO flood maps", RSE 315:114439, 2024 | About half: through Sec. 4.4. Discussion, conclusion and appendices not read | The most likely source of overlapping prior art. In the half read, it compares sampling designs for accuracy metrics and gives no area estimator, but the unread half could differ. |
| Li, Matgen, Chini, "Quantifying and Communicating Uncertainty in SAR-Based Flood Mapping via Density-Aware Neural Networks and Conformal Risk Control", IEEE TGRS 64, 2026 | Abstract only | Conformal guarantees for radar flood maps. Whether it gives any guarantee on area is unknown. |
| Nobre et al., "Height Above the Nearest Drainage", Journal of Hydrology 404:13-29, 2011 | Nothing (closed access) | Original definition of HAND, used as a prior in section 5.1. |
| Lok Sabha starred question 43, 3 Feb 2026 | Nothing (server refused; browser could not read the PDF) | Reported to mention a committee report and operating procedures for the new cover. |
| RIICE, "Remote Sensing-Based Flood Assessment Helps Government of Tamil Nadu" | Text layer only; maps and figures are images | Flood assessment case study. |

The first three are open access or widely held and need only a person to download the PDF.

### Group D. Read through the alphaXiv paper tools on 17 November 2026

Page-ranked excerpts of each paper's full text were read for the questions named; none was read cover to cover. All are arXiv preprints, not peer reviewed unless stated.

- **[A1]** A. Zaytar et al. "Crop Mapping Evaluation under Sampling Bias." Microsoft AI for Good, arXiv:2611.00794, 31 Oct 2026. Technical report.
- **[A2]** P. Mohanty, R. Khanna. "Adaptive Stratified Active Statistical Inference." arXiv 2607 (identifier as listed on alphaXiv: `2607.adaptive-stratified-active-statistical-inference`), Jul 2026.
- **[A3]** S. Wu, Y. Nair, A. Maechler, E. J. Candes. "Pro-Active Inference." arXiv:2610.34681, 26 Oct 2026.
- **[A4]** S. Kawano, Z. R. Li, P. A. Parker. "Prediction-Powered Smoothing and Validation for Disaggregated AI Evaluation." arXiv:2609.20758, Sep 2026.
- **[A5]** A. Petrou-Zeniou. "Uncertainty in Compound Decisions." arXiv:2610.15672, Oct 2026.
- **[A6]** D. Broska, M. Howes. "Cluster-Robust Prediction-Powered Inference." arXiv:2610.09601, 7 Oct 2026.
- **[A7]** S. Shirota. "Conditional validity of prediction-powered inference for spatially dependent finite populations." arXiv:2608.10356, Oct 2026.
- **[A8]** S. Rizvi, D. Burt, V. Srinivasan, R. Berlinghieri, S. Del Col, T. Broderick. "Prediction-powered inference for time series across space." arXiv:2610.08715, Oct 2026 (NeurIPS 2026 TS-LIMITS workshop).
- **[S1] re-read:** Lu et al., arXiv:2407.13659v7, Appendix F read in full this time, including the stratified PPI area experiments.

**Group E. Found by search on 17 November 2026, abstract or snippet level only; nothing in sections 2 to 5 depends on them beyond the statements marked as such.** Orienteering survey arXiv:2512.16865; informative path planning arXiv:2601.17227 and 2402.08841; flood-aware routing arXiv:2611.02479; Sentinel-1 flood detection time series (Bayesian change point) arXiv:2504.19526; effectiveness of Sentinel-1 and Sentinel-2 for flood detection, NHESS 22:2473 (2022); multi-predictor PPI arXiv:2603.27414, 2606.21232, 2604.27892, 2605.08429; selection-bias sensitivity: Aronow and Lee 2013, Andridge et al. 2019 (PMC7750890), Hartman and Huang 2024, Tudball et al. 2023, Cortes-Gomez et al. 2024 (ICML). Code: `research/threshold_alloc/routing_sim.py`.

Also cited from these papers, not read: Fisch et al. 2024 (stratified PPI, arXiv:2406.04291); McRoberts et al. 2022 (model-assisted regression estimators, RSE 281); Mozer 2026 (arXiv:2603.19160); Zrnic and Candes 2024 (Active Statistical Inference). Code and results for the simulation in 5.4: `research/threshold_alloc/`.
