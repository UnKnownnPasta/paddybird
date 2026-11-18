// Builds the NCDTE-2026 paper (single-column Word, template rules from ncdte26.docx).
// Run from this folder: node build_paper.js   (needs the npm package `docx`, installed in ../../docs/report/build/node_modules)
const fs = require('fs');
const path = require('path');
const D = require(path.resolve(__dirname, '../../docs/report/build/node_modules/docx'));
const { Document, Packer, Paragraph, TextRun, ImageRun, AlignmentType, Table, TableRow, TableCell, WidthType, BorderStyle, Footer, PageNumber } = D;

const F = 'Times New Roman';
const CM = 567; // twips per cm
const WIDTH = 11906 - 2 * Math.round(2.5 * CM); // text width in twips
const ROOT = path.resolve(__dirname, '../..');
const L3 = path.join(ROOT, 'notebooks/artifacts/layer3');
const L4 = path.join(ROOT, 'notebooks/artifacts/layer4');

// inline markup: **bold**, *italic*
function runs(t, o = {}) {
  const out = []; const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g; let last = 0, m;
  const base = { font: F, size: o.size || 24, bold: o.bold, italics: o.italics };
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(new TextRun({ ...base, text: t.slice(last, m.index) }));
    const s = m[0];
    if (s.startsWith('**')) out.push(new TextRun({ ...base, text: s.slice(2, -2), bold: true }));
    else out.push(new TextRun({ ...base, text: s.slice(1, -1), italics: true }));
    last = m.index + s.length;
  }
  if (last < t.length) out.push(new TextRun({ ...base, text: t.slice(last) }));
  return out;
}
// body: TNR 12, single spacing, justified, first line 1.1 cm, no space before/after
const P = (t, o = {}) => new Paragraph({
  alignment: o.align || AlignmentType.JUSTIFIED,
  spacing: { line: 240, before: 0, after: o.after ?? 120 },
  indent: o.noIndent ? undefined : { firstLine: Math.round(1.1 * CM) },
  keepNext: o.keepNext, children: runs(t, o),
});
const C = (t, o = {}) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { line: 240, before: o.before || 0, after: o.after ?? 0 },
  children: runs(t, o),
});
const H1 = t => new Paragraph({ keepNext: true, spacing: { before: 240, after: 120 }, children: [new TextRun({ text: t, font: F, size: 26, bold: true })] });
const LEAD = t => new Paragraph({ keepNext: true, spacing: { before: 60, after: 60 }, indent: { left: 360 }, children: [new TextRun({ text: '•  ', font: F, size: 24 }), new TextRun({ text: t, font: F, size: 24, bold: true })] });
const BODY = (t, o = {}) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: 240, after: 120 }, indent: { left: 720, firstLine: 0 }, keepNext: o.keepNext, children: runs(t, o) });
const EQ = t => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 120 }, children: [new TextRun({ text: t, font: F, size: 24, italics: true })] });

const rule = { style: BorderStyle.SINGLE, size: 8, color: '000000' };
const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
function table(widths, rows, align = []) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths, alignment: AlignmentType.CENTER,
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0, cantSplit: true,
      children: r.map((c, ci) => new TableCell({
        width: { size: widths[ci], type: WidthType.DXA },
        borders: { top: ri === 0 ? rule : none, bottom: (ri === 0 || ri === rows.length - 1) ? rule : none, left: none, right: none },
        margins: { top: 40, bottom: 40, left: 80, right: 80 },
        children: [new Paragraph({ alignment: ri === 0 ? AlignmentType.CENTER : (align[ci] || AlignmentType.CENTER), spacing: { line: 240, after: 0 }, keepNext: ri < rows.length - 1, children: runs(c, { size: 21, bold: ri === 0 }) })],
      })),
    })),
  });
}
const TCAP = (n, t) => new Paragraph({ keepNext: true, alignment: AlignmentType.JUSTIFIED, spacing: { before: 120, after: 80 }, children: [new TextRun({ text: `Table ${n}. `, font: F, size: 22, bold: true }), ...runs(t, { size: 22 })] });
const FCAP = (n, t) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { before: 60, after: 160 }, children: [new TextRun({ text: `Figure ${n}. ${t}`, font: F, size: 22, italics: true })] });
const gap = () => new Paragraph({ spacing: { after: 100 }, children: [] });

function pngSize(f) { const b = fs.readFileSync(f); return [b.readUInt32BE(16), b.readUInt32BE(20)]; }
function fig(f, wpx) {
  const [w, h] = pngSize(f);
  return new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 40 },
    children: [new ImageRun({ type: 'png', data: fs.readFileSync(f), transformation: { width: wpx, height: Math.round(wpx * h / w) } })] });
}
// algorithm box
function algo(title, steps) {
  const b = { style: BorderStyle.SINGLE, size: 6, color: '000000' };
  return new Table({
    width: { size: WIDTH - 400, type: WidthType.DXA }, columnWidths: [WIDTH - 400], alignment: AlignmentType.CENTER,
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      width: { size: WIDTH - 400, type: WidthType.DXA }, borders: { top: b, bottom: b, left: b, right: b }, margins: { top: 80, bottom: 80, left: 140, right: 140 },
      children: [
        new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: title, font: F, size: 22, bold: true })] }),
        ...steps.map((s, i) => new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: 240, after: 40 }, indent: { left: 360, hanging: 360 }, children: runs(`${i + 1}.\t${s}`, { size: 22 }) })),
      ],
    })] })],
  });
}

const A = AlignmentType;
const body = [];
const add = (...x) => body.push(...x);

// ---------------- title block ----------------
add(C('How many wrong calls does a flood map leave, and how many can a few routed field checks remove? Flooded-cropland estimation per unit on flood events not used for fitting', { size: 28, bold: true, after: 200 }));
add(C('**Authors:** Sai Bhuwan S*, Nikhil S Rao, Yashita Murlidhar Mandavilli, Shashwat Mittal', { size: 22, italics: true, after: 40 }));
add(C('**Affiliation:** Undergraduate Students (B.E., Computer Science and Engineering), RV Institute of Technology and Management, Bengaluru, Karnataka, India', { size: 22, italics: true, after: 40 }));
add(C('**Under the guidance of:** Mr. S Murugan, Assistant Professor, Department of Computer Science and Engineering, RV Institute of Technology and Management, Bengaluru, Karnataka, India', { size: 22, italics: true, after: 40 }));
add(C('**Corresponding author mail id:** rvit24bcs019.rvitm@rvei.edu.in', { size: 22, italics: true, after: 40 }));
add(C('**Acknowledgements:** The authors thank Mr. S Murugan for guidance on this work.', { size: 22, italics: true, after: 200 }));

add(C('Abstract', { size: 26, bold: true, after: 100 }));
add(P('Flood maps are usually checked pixel by pixel, but an insurance or relief officer needs one call per unit with an error bar. We ask how many wrong unit calls a calibrated SAR flood map leaves on events it has not seen, and how many a small, randomly drawn and routed field sample removes. We built a four-layer pipeline (data, mapping, estimation, field planning) and tested it on 11 Sen1Floods11 events split by event, with India and Bolivia as test events. On the test events the fused map had IoU 0.42 against 0.19 for Otsu thresholding and calibration error (ECE) 0.039 against 0.338, but inside a cropland mask it counted only 60% of the labelled flooded area. A unit is called flooded when its estimated flooded share exceeds 25%. On 34 units from the India event the map alone made 14.7% wrong calls. With 16 and 32 field checks per unit the estimator made 9.8% and 6.8%, against 13.1% and 9.8% for the checks alone, and its nominal 90% intervals covered 81% and 87%. In simulation, choosing checks by expected drop in wrong calls and routing on a flood-priced road graph reduced wrong calls further, but fewer than about 12 checks per unit did worse than the map alone. We report where each step fails.', { noIndent: true }));
add(P('**Keywords:** flood mapping; Sentinel-1 SAR; calibration; survey estimation; field planning; crop insurance', { noIndent: true, after: 160 }));

// ---------------- 1 Introduction ----------------
add(H1('1. Introduction'));
add(P('Flood maps from Sentinel-1 radar are plentiful and are validated pixel by pixel against labelled chips [3]. An officer who has to decide which villages or insurance units were flooded needs something else: a call for each unit, how sure it is, and where to send the next field check. A map alone gives a share of flooded pixels with no error bar, and a field sample alone is slow and covers few places. We study how far these two sources together can reduce wrong unit calls, and we call the pipeline we built Paddybird.'));
add(P('The test that matters for such a pipeline is on a flood event it has not seen. A random split of chips lets test chips sit next to training chips from the same event, which flatters the result. We therefore split by whole event, fit everything on training and validation events, and score the test events once.'));
add(LEAD('Research questions'));
add(BODY('(1) How many wrong unit calls does a calibrated SAR flood map leave on events not used for fitting? (2) How many field checks per unit does it take to beat the map alone, and does randomised selection keep the estimate unbiased when roads limit where officers can go? (3) Does choosing and routing the checks beat simple rules?'));
add(LEAD('Scope'));
add(BODY('This is a measurement and extension of the usual map-only practice, not a new mapping model. The unit call rule (flooded if the share exceeds 25%) was fixed before any result was computed. Field checks are simulated from hand labels, and nothing was deployed. Where we changed the design after seeing results, we say so in Section 6.'));

// ---------------- 2 Literature (kept short, template heading) ----------------
add(H1('2. Literature Review'));
add(P('Flood extent from SAR is commonly obtained by choosing a backscatter threshold that separates water from land, either with Otsu\'s method [1] or with minimum-error thresholding [2]. Learned models trained on labelled chips, such as Sen1Floods11 [3] and Kuro Siwo [4], are usually compared with such thresholds. These studies report pixel-level scores. They do not turn a map into a per-unit number with an uncertainty, and they do not say where to collect more ground evidence. Survey sampling offers the missing tools: stratification, inclusion probabilities and weighted estimators [8], and more recently estimators that combine model predictions with a small labelled sample [9]. Field planning with travel time is an orienteering problem [10] on a road graph [11]. Floods change road travel times, so a plan made on the dry road map can overrun the day. We test this on a real road graph in Section 4.'));

// ---------------- 3 Case and Methodology ----------------
add(H1('3. Case and Methodology'));
add(P('Paddybird has four algorithmic layers plus a tool layer. Figure 1 shows the flow, and the sections below follow it.', { keepNext: true }));
add(fig(path.join(__dirname, 'fig_layers.png'), 470));
add(FCAP(1, 'The five layers of Paddybird and how far each is tested in this paper. Layer 5 (the officer tool) is a demonstration notebook and is only described.'));

add(LEAD('Data and events'));
add(BODY('We took 132 Sen1Floods11 hand-labelled chips, 12 at random from each of 11 events, each a 128 x 128 centre crop at 20 m with VV and VH backscatter (gamma0, dB) [3]. Events were split as a whole: Ghana and Sri-Lanka for validation, India and Bolivia for testing, and the other seven for training. An automated check confirms that no event appears in two splits. The official Sen1Floods11 split puts 10 of the 11 events in more than one split, which is why we did not use it. Permanent water comes from the JRC layer [6] and cropland from ESA WorldCover 2021 [5]. WorldCover has no paddy class, so cropland is our proxy for paddy. Chips with under 30% valid pixels were dropped, leaving 121.'));
add(LEAD('Units'));
add(BODY('A unit is a 64 x 64 pixel window (about 164 ha) cut from a chip. This gives 125 training, 27 validation and 34 test units. Only the India event kept test units, because Bolivia had too few cropland pixels. The unit truth is the labelled flooded share of cropland pixels in the window. Units are constructions standing in for real insurance units.'));
add(LEAD('Layer 1: data and platform'));
add(BODY('Scene search uses public STAC catalogues with window reads from cloud-optimised files. Every output carries a receipt with scene IDs, parameters and a SHA-256 hash, and each field check stores its inclusion probability and weight. For routing we used a real OpenStreetMap road graph of a Godavari delta block (2096 nodes, 2567 edges, 475 km) with 36 grid units.'));
add(LEAD('Layer 2: mapping'));
add(BODY('Predictor 1 is a minimum-error threshold on VV and VH [2], softened with a 1 dB threshold-error model, with permanent water removed. Predictor 2 is a gradient-boosted pixel model trained on training events. A logistic stack fuses them, with weights per WorldCover group fitted on validation events only. Calibration (identity, temperature or isotonic) is chosen by leave-one-validation-event-out, and identity won. Two predictors listed in our design, an optical index and an external product, were not used because the chips have no optical bands. The baseline is Otsu thresholding on VV [1]. We report ECE [7], Brier score, IoU and the ratio of mapped to labelled flooded area.'));
add(LEAD('Layer 3: estimation'));
add(BODY('Units are stratified by calibrated map score (cuts at 0.15 and 0.60). For each unit, the estimate of the flooded share combines the map share in each stratum with the map error measured on the unit\'s own field checks, shrunk towards a prior fitted on training events (Algorithm 1). The call is always given: flooded if the estimated share exceeds 0.25. Its confidence is P_u = Φ((θ_u − 0.25) / s_u), where s_u is a cluster-robust standard error over visit sites. There is no abstain state; a unit with no checks falls back to the raw map.'));
add(gap());
add(algo('Algorithm 1. Unit call and confidence', [
  'Split the unit\'s pixels into three strata by calibrated score (cuts 0.15 and 0.60).',
  'For each stratum, estimate the true flooded rate from the checks (weighted by 1 / inclusion probability), shrunk towards the training-event rate with a between-event variance term.',
  'Set θ_u to the stratum-weighted sum. Compute s_u from the variance across visit sites, blended with a model variance when a unit has few sites.',
  'Call the unit flooded if θ_u > 0.25. Report P_u = Φ((θ_u − 0.25) / s_u).',
]));
add(gap());
add(LEAD('Layer 4: field planning'));
add(BODY('Allocation (Algorithm 2) picks the next check as the one with the largest expected drop in wrong calls, using a Gauss-Hermite look-ahead over the possible outcomes. Routing (Algorithm 3) prices each road by its flood probability, finds travel times with Dijkstra\'s algorithm [11], and builds each officer\'s day by gain per extra minute [10]. Selection of villages is random with known inclusion probabilities, so the estimator in layer 3 stays design-based [8]. Planner settings were tuned on separate seeds from the evaluation seeds.'));
add(gap());
add(algo('Algorithm 2. Greedy allocation of checks', [
  'For every unit and stratum, compute the expected number of wrong calls now.',
  'For each candidate check, integrate over its possible outcomes (Gauss-Hermite nodes) and recompute the expected wrong calls.',
  'Take the check with the largest drop. Repeat until the budget is used.',
]));
add(gap());
add(algo('Algorithm 3. Flood-aware routing for K officers', [
  'Close roads with flood probability above 0.7 and slow the rest by a fitted factor.',
  'Compute travel times between candidate units with Dijkstra\'s algorithm on this graph.',
  'For each officer, add the unit with the best gain (Algorithm 2) per extra minute that still fits the 240 minute day. Re-plan each day.',
]));
add(gap());
add(LEAD('Evaluation protocol and metrics'));
add(BODY('Maps are scored on the test events once. Field checks are simulated by drawing sites from hand labels. Estimation results are Monte Carlo averages over check draws, and planning results are averages over 60 to 160 fixed-seed scenarios with 95% intervals. We report wrong-call rate, coverage of the 90% interval, and ECE of P_u. Because the unit count is small (34), the map-only wrong-call rate is a single number (5 of 34 units), not an average.'));

// ---------------- 4 Results ----------------
add(H1('4. Results'));
add(LEAD('Mapping on events not used for fitting'));
add(BODY('Table 1 shows the test results. The fused, calibrated map had IoU 0.42 and ECE 0.039, against 0.19 and 0.338 for Otsu on VV. Per event, IoU was 0.36 (India) and 0.53 (Bolivia). The gap between validation and test ECE was +0.018 for the fused map, +0.036 for the boosted model alone and +0.045 for the soft threshold.', { keepNext: true }));
add(TCAP(1, 'Mapping on the two test events (India, Bolivia). Area ratio is mapped over labelled flooded area.'));
add(table([3300, 1200, 1200, 1200, 1500], [
  ['Model', 'ECE', 'Brier', 'IoU', 'Area ratio'],
  ['Otsu on VV (baseline)', '0.338', '0.338', '0.19', '3.18'],
  ['Predictor 1, hard rule', '0.087', '0.087', '0.35', '-'],
  ['Predictor 1, soft', '0.074', '0.078', '0.38', '-'],
  ['Predictor 2, boosted', '0.061', '0.073', '0.29', '-'],
  ['Fused and calibrated', '0.039', '0.063', '0.42', '0.84'],
], [A.LEFT]));
add(gap());
add(BODY('The learned model alone did not beat the threshold rule on IoU, on validation or on test. On validation events, the fused map\'s Brier score (0.040) was worse than that of either predictor alone (about 0.031); fusion beat the boosted model on test (0.063 against 0.073), but that order did not hold on validation. The overall ECE looks good partly because most pixels are easy dry pixels. Over pixels called at least 5% wet, the fused ECE was 0.128. Inside the cropland mask, the fused ECE was 0.099 (baseline 0.402), but the map counted 5.1 km² of flooded cropland against 8.6 km² labelled (ratio 0.60), while the baseline counted 16.0 km².'));

add(LEAD('Estimation with field checks'));
add(BODY('Table 2 compares three ways of making the unit call on the 34 India test units. The map alone made 14.7% wrong calls whatever the budget. With 16 and 32 randomly drawn checks per unit, the estimator made 9.8% and 6.8% wrong calls, fewer than the checks alone (13.1%, 9.8%). Its 90% intervals covered 81% and 87%, so they are too narrow. Using an independent-pixel variance instead of the cluster-robust one lowered coverage to 76%. The ECE of P_u at 16 checks was 0.041 (Figure 2).', { keepNext: true }));
add(TCAP(2, 'Wrong-call rate and coverage of the 90% interval on the India test units, random checks.'));
add(table([2300, 1500, 1500, 1500, 1500], [
  ['Checks per unit', 'Map only', 'Checks only', 'Paddybird', 'Coverage'],
  ['16', '14.7%', '13.1%', '9.8%', '0.81'],
  ['32', '14.7%', '9.8%', '6.8%', '0.87'],
]));
add(gap());
add(fig(path.join(__dirname, 'fig2_wrong_calls.png'), 340));
add(FCAP(2, 'Wrong-call rate against field checks per unit on the India test units (Monte Carlo over check draws). The flat line is the map alone, "sample only" is the checks alone, and the stratified PPI line with Hajek weights is the Paddybird estimator.'));
add(fig(path.join(L3, 'fig_test_reliability.png'), 380));
add(FCAP(3, 'Reliability of P_u on the India test units at 16 checks per unit: the share of units truly above 0.25 against the stated P_u. "ppi_ipw" is the Paddybird estimator, "ppi_ipw_iid" is the same with independent-pixel variance, and "report_formula" is the simple formula from our partial report. Points far from the diagonal rest on few units.'));
add(BODY('Two cautions apply. With no checks at all, the correction learned from training events was worse than the raw map on the test units (RMSE 0.222 against 0.160), because the India map under-reads flooding while the training events over-read it. This is why a unit with no checks keeps the raw map call. Second, the first version of the estimator (v1) failed the coverage bound on its single clean test run (0.739 at 16 checks). We describe the revised estimator and its status in Section 6.'));

add(LEAD('Route bias'));
add(BODY('Officers cannot reach every site, so checks are not a simple random sample. In a synthetic stress test with route-style selection (32 checks), ignoring the inclusion probabilities gave a bias of −0.030. The unshrunk Horvitz-Thompson estimator [8] gave +0.002, but with much higher error. Our default, the shrunk Hajek form, reduced the bias to −0.011 and its intervals covered 0.78 to 0.80 of truths. So weighting removes the bias in expectation for Horvitz-Thompson only, and the default estimator trades some bias for stability. In the planning simulation, where routing bias was small, naive pooling had a lower error than the unbiased weighted estimate (0.030 against 0.049). Random selection buys a guarantee of no bias, not a smaller error.', { keepNext: false }));

add(LEAD('Choosing and routing checks'));
add(BODY('Table 3 compares allocation rules. On synthetic villages at 16 checks per village the decision rule made 8.6% wrong calls, against 12.6% for random, 13.8% for proportional and 14.0% for uncertainty-only allocation. It reached the level the others reach at 32 checks (about 10%) with about 12 checks. On the real labelled test chips it was best or tied from 2 to 16 checks per unit, and at 8 checks it made 4.1% wrong calls against 4.9% for uncertainty-only. At 32 checks it lost to uncertainty-only (3.6% against 3.1%, paired difference +0.5 points [0.1, 0.9]).', { keepNext: true }));
add(TCAP(3, 'Wrong-call rate by allocation rule. Synthetic villages (80, 60 evaluation seeds) and real test chips. "-" means not reported in this paper.'));
add(table([2500, 1600, 1600, 1600, 1600], [
  ['Setting', 'Decision rule', 'Uncertainty only', 'Random', 'Proportional'],
  ['Synthetic, 16 per village', '8.6%', '14.0%', '12.6%', '13.8%'],
  ['Real chips, 8 per unit', '4.1%', '4.9%', '-', '-'],
  ['Real chips, 32 per unit', '3.6%', '3.1%', '-', '-'],
], [A.LEFT]));
add(gap());
add(fig(path.join(L4, 'fig_wrong_vs_checks.png'), 430));
add(FCAP(4, 'Wrong-call rate against checks per village for the four allocation rules on synthetic villages, with 95% intervals.'));
add(BODY('Few checks were worse than none. With 2 checks per village the decision rule made 19.2% wrong calls and with 4 checks 14.7%, against 11.4% for the map alone, and only from about 12 checks did it beat the map. In routed campaigns, every planner did worse than the map on days 1 to 3. We therefore keep the map call until a unit has enough checks.'));
add(BODY('Table 4 gives the routing results. After 5 days with 3 officers and a 240 minute day, the flood-aware planner made fewer wrong calls than nearest-first routing by 3.6 points on the synthetic grid and 4.4 points on the real road graph. On the real roads it also beat the same planner run on the dry road map by 3.1 points [1.3, 4.8] (Figure 5). Against a flood-blind planner on the synthetic grid the difference was not significant, though it did the same work with 27% less driving. Pricing roads at their true expected time over-stated travel by about 50%; it only worked after we fitted the slow-down factor (4, against a true 8) on tuning seeds.', { keepNext: true }));
add(TCAP(4, 'Flood-aware routing against other planners, after 5 days. Difference in wrong-call rate in points, flood-aware minus comparator (negative = fewer wrong calls).'));
add(table([3000, 2200, 1500, 2000], [
  ['Comparator', 'Setting', 'Difference', '95% interval'],
  ['Nearest-first', 'Synthetic grid', '−3.6', '-'],
  ['Nearest-first', 'Real roads', '−4.4', '-'],
  ['Same planner, dry map', 'Real roads', '−3.1', '[−4.8, −1.3]'],
  ['Flood-blind planner', 'Synthetic grid', '−0.9', '[−1.9, +0.1]'],
], [A.LEFT, A.LEFT]));
add(gap());
add(fig(path.join(L4, 'route_day1.png'), 400));
add(FCAP(5, 'Day-1 routes for three officers on the real road graph of the Godavari block (flood probabilities on the roads are semi-synthetic). Flooded roads are blue, and villages drawn at random for the survey are circled.'));
add(BODY('Randomly drawing villages with known inclusion probabilities gave Hajek estimates with no detectable bias in the flooded rates of mapped strata (within 0.3 points) and cost no measurable accuracy in village calls (−0.06 points [−0.60, +0.49]). Pooling all routed checks without weights overstated the flooded rate of mapped-dry pixels by 1.5 points [1.1, 2.0]. In about 26% of synthetic scenarios the depot sat inside the flood and no village was reachable, so no random draw could be made.'));

// ---------------- 5 Discussion ----------------
add(H1('5. Discussion'));
add(LEAD('How much a flood map leaves'));
add(BODY('A calibrated SAR map clearly beats Otsu thresholding on events it has not seen, but it left 14.7% wrong calls on the India units and counted only 60% of the flooded cropland area. For an area-based claim this shortfall matters more than the pixel scores.'));
add(LEAD('When field checks help'));
add(BODY('Checks help once there are enough of them. Between about 12 and 32 checks per unit, combining map and checks beat either alone. Below that, the estimate is noisier than the map, in the estimator (Table 2) and in the allocation study. Our recommendation is to keep the map call until a unit has about a dozen checks.'));
add(LEAD('What planning adds'));
add(BODY('Choosing checks by expected drop in wrong calls helped most at moderate budgets, and flood-aware routing helped most when the flooded roads actually changed the best route. The two plain baselines were close at the extremes. We read this as an effect of how planning is evaluated: gains show up where budgets are tight and roads are cut.'));
add(LEAD('Link to related work'));
add(BODY('Like the pixel-level studies [3, 4], we find thresholding is a hard baseline to beat on some measures. Our contribution is the step after the map, which those studies do not cover. The comparison is indirect, because they report pixel scores and we report unit calls.'));

// ---------------- 6 Limitations ----------------
add(H1('6. Limitations'));
add(LEAD('Paddy is a proxy'));
add(BODY('We mask by WorldCover cropland, so we measure flooded cropland, not flooded rice. There is no paddy label in these chips.'));
add(LEAD('Map shortfall and SAR only'));
add(BODY('The map counts about 60% of the labelled flooded cropland area. The chips have no optical bands, so optical water indices were not used. A development run with optical bands on other chips scored better, which we did not use for any decision.'));
add(LEAD('Few test events'));
add(BODY('The test set is two events, and only India has test units, so the estimation intervals are wide and the 34 units give coarse wrong-call rates.'));
add(LEAD('Simulated field checks and roads'));
add(BODY('Field checks are drawn from hand labels. The road flood probabilities on the Godavari block are semi-synthetic because the mapping layer has no flood map there. No officers or trips were observed. The planning study mixes real roads, real chips and synthetic scenarios, which we state in each result.'));
add(LEAD('Intervals under-cover'));
add(BODY('The nominal 90% intervals covered 81% to 87% in estimation and 78% to 80% under route-style selection. We call P_u reasonably calibrated (ECE 0.041), not reliable.'));
add(LEAD('Units and the duration layer'));
add(BODY('Units are windows cut from chips, not real insurance boundaries. A submergence-duration module exists in the code, but its onset and duration are simulated, so we leave it out of the results.'));
add(LEAD('Changes to the design'));
add(BODY('Before any result: the 25% call threshold and the event split. After seeing results we changed the following. The estimator v1 shrank all units towards the training correction and failed the coverage bound on its single clean test run (0.739 at 16 checks); v2 adds a between-event prior variance and learns the pool from each region\'s own checks. We built v2 using validation data, but after seeing the v1 test result, so v2\'s test numbers are not a clean held-out estimate, and the frozen v1 record is kept in the repository. The mapping test cell was first run in a development run on layer 1 data; the only later change was a crash fix with no tuning. For planning, the road-closure cut-off (0.7), the slow-down factor (4) and size-proportional village selection were chosen on tuning seeds separate from the evaluation seeds.'));

// ---------------- 7 Conclusion ----------------
add(H1('7. Conclusion'));
add(P('On flood events not used for fitting, a calibrated SAR map left 14.7% wrong unit calls, and counted only 60% of the flooded cropland area. Combining it with 16 to 32 randomly drawn field checks per unit cut wrong calls to 9.8% and 6.8%, better than either source alone, though the stated 90% intervals covered only 81% to 87%. In simulation, choosing checks by expected gain and routing on a flood-priced road graph reduced wrong calls further, but fewer than about 12 checks per unit did worse than the map. We recommend reporting a map-only baseline, scoring whole events, keeping inclusion probabilities for every check, and keeping the map call until a unit has enough checks. A pilot would need real insurance units, a paddy label, optical bands, and officers\' actual trips.'));

add(H1('Data and code availability'));
add(P('Sen1Floods11 chips (CC BY 4.0), ESA WorldCover, the JRC surface-water layer, Sentinel-1 scenes from public STAC catalogues and OpenStreetMap roads are all public. Code, the notebooks that produce every table and figure, and the frozen first-run test records are at https://github.com/UnKnownnPasta/paddybird.', { noIndent: true }));

add(H1('References'));
const refs = [
  'Otsu N. A threshold selection method from gray-level histograms. IEEE Transactions on Systems, Man, and Cybernetics. 1979; 9(1): 62-66.',
  'Kittler J, Illingworth J. Minimum error thresholding. Pattern Recognition. 1986; 19(1): 41-47.',
  'Bonafilia D, Tellman B, Anderson T, Issenberg E. Sen1Floods11: a georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1. Proceedings of the IEEE/CVF CVPR Workshops. 2020.',
  'Bountos N I, et al. Kuro Siwo: a large-scale SAR flood mapping dataset. arXiv preprint. 2023.',
  'Zanaga D, et al. ESA WorldCover 10 m 2021 v200. Zenodo. 2022.',
  'Pekel J F, Cottam A, Gorelick N, Belward A S. High-resolution mapping of global surface water and its long-term changes. Nature. 2016; 540: 418-422.',
  'Guo C, Pleiss G, Sun Y, Weinberger K Q. On calibration of modern neural networks. Proceedings of the 34th ICML. 2017.',
  'Horvitz D G, Thompson D J. A generalization of sampling without replacement from a finite universe. Journal of the American Statistical Association. 1952; 47(260): 663-685.',
  'Angelopoulos A N, Bates S, Fannjiang C, Jordan M I, Zrnic T. Prediction-powered inference. Science. 2023; 382: 669-674.',
  'Golden B L, Levy L, Vohra R. The orienteering problem. Naval Research Logistics. 1987; 34(3): 307-318.',
  'Dijkstra E W. A note on two problems in connexion with graphs. Numerische Mathematik. 1959; 1: 269-271.',
];
refs.forEach((r, i) => add(new Paragraph({ alignment: A.JUSTIFIED, spacing: { line: 240, after: 80 }, indent: { left: 480, hanging: 480 }, children: runs(`[${i + 1}] ${r}`, { size: 22 }) })));

const doc = new Document({
  creator: 'Paddybird team', title: 'Paddybird NCDTE-2026 paper',
  styles: { default: { document: { run: { font: F, size: 24 } } } },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: Math.round(2.5 * CM), bottom: 2 * CM, left: Math.round(2.5 * CM), right: Math.round(2.5 * CM) } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: A.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: F, size: 20 })] })] }) },
    children: body,
  }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(__dirname, 'Paddybird_NCDTE2026_paper.docx'), b); console.log('written', b.length); });
