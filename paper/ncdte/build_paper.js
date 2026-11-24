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
add(C(`Paddybird: Estimating Flooded Cropland per Unit from Radar Maps and Field Checks`, { size: 28, bold: true, after: 200 }));
const HR = (t, o = {}) => new TextRun({ font: F, size: 22, italics: true, bold: o.bold, superScript: o.sup, text: t });
add(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { line: 240, after: 40 }, children: [
  HR('Authors: ', { bold: true }),
  HR('Sai Bhuwan S'), HR('1', { sup: true }), HR('*, Nikhil S Rao'), HR('2', { sup: true }),
  HR(', Yashita Murlidhar Mandavilli'), HR('3', { sup: true }), HR(', Shashwat Mittal'), HR('4', { sup: true }),
] }));
add(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { line: 240, after: 40 }, children: [
  HR('Affiliation', { bold: true }), HR('1,2,3,4', { sup: true, bold: true }), HR(': ', { bold: true }),
  HR('Undergraduate Students (B.E., Computer Science and Engineering), RV Institute of Technology and Management, Bengaluru, Karnataka, India'),
] }));
add(C(`**Under the guidance of:** Mr. S Murugan, Assistant Professor, Department of Computer Science and Engineering, RV Institute of Technology and Management, Bengaluru, Karnataka, India`, { size: 22, italics: true, after: 40 }));
add(C(`**Author mail ids:** Sai Bhuwan S (rvit24bcs019.rvitm@rvei.edu.in), Nikhil S Rao (rvit24bcs150.rvitm@rvei.edu.in), Yashita Murlidhar Mandavilli (rvit24bcs082.rvitm@rvei.edu.in), Shashwat Mittal (rvit24bcs085.rvitm@rvei.edu.in)`, { size: 22, italics: true, after: 40 }));
add(C(`**Corresponding author mail id:** rvit24bcs019.rvitm@rvei.edu.in`, { size: 22, italics: true, after: 40 }));
add(C(`**Acknowledgements:** The authors thank Mr. S Murugan for guidance on this work.`, { size: 22, italics: true, after: 200 }));

add(C(`Abstract`, { size: 26, bold: true, after: 100 }));
add(P(`Flood maps are scored pixel by pixel, yet insurance and relief decisions are made per unit and need a stated confidence. We ask how many unit calls a calibrated SAR flood map gets wrong on events it never saw, and how many of those errors a handful of routed field checks can remove. The pipeline has four layers: data, mapping, estimation and field planning. We tested it on 11 Sen1Floods11 events, split by whole event, with India and Bolivia as the test events. Against Otsu thresholding, the fused map reached IoU 0.42 (Otsu 0.19) and a calibration error (ECE) of 0.039 (Otsu 0.338), but inside a cropland mask it captured only 60% of the labelled flooded area. A unit counts as flooded once its estimated flooded share passes 25%. On 34 India units the map alone was wrong 14.7% of the time. With 16 or 32 field checks per unit the estimator's error fell to 9.8% and 6.8%, where the checks alone managed 13.1% and 9.8%, although its nominal 90% intervals covered only 81% and 87%. In simulation, chosen checks and flood-aware routing cut errors further. Below about 12 checks per unit, though, the map did better. We report where each step fails.`, { noIndent: true }));
add(P(`**Keywords:** flood mapping; Sentinel-1 SAR; calibration; survey estimation; field planning; crop insurance`, { noIndent: true, after: 160 }));

// ---------------- 1 Introduction ----------------
add(H1(`1. Introduction`));
add(P(`Sentinel-1 flood maps are now routine, and the public datasets behind them score pixels against hand-labelled chips [1, 2]. Insurers and relief offices decide per unit, such as a village. They need a flooded or not-flooded call for each unit and some measure of how far to trust it. The dataset papers we build on stop at the pixel scores, and a map on its own says nothing about where more ground evidence should be collected.`));
add(P(`This paper describes Paddybird, a pipeline that turns a calibrated SAR flood map and a small field sample into a call for each unit, with a confidence attached. It also chooses which units to check next and how officers should drive there. The test that counts is a flood event the pipeline has not seen. A random split of chips places test chips next to training chips from the same event and flatters the score, so we split by whole event, fit on training and validation events, and score the test events once.`));
add(LEAD(`Research questions`));
add(BODY(`(1) On events not used for fitting, how many unit calls does a calibrated SAR flood map get wrong? (2) How many field checks per unit does it take to beat the map alone, and does random selection keep the estimate unbiased when roads decide where officers can go? (3) Do chosen and routed checks beat simple rules?`));
add(LEAD(`Scope`));
add(BODY(`This measures and extends the usual map-only practice; it is not a new mapping model. The call rule (flooded above a 25% share) was fixed before any result existed. Field checks are simulated from hand labels and nothing was deployed. Design changes made after seeing results are listed in Section 6.`));

// ---------------- 2 Literature ----------------
add(H1(`2. Literature Review`));
add(P(`SAR flood extent is usually obtained by thresholding backscatter, with the cut chosen by Otsu's method [3] or minimum-error thresholding [4]. Sen1Floods11 supplies hand-labelled chips from 11 events and reports Otsu as a baseline against learned models [1]; Kuro Siwo extends the idea to 43 events [2]. Both score pixels.`));
add(P(`Deep models now dominate these benchmarks. A cross-modal distillation model, which trains a SAR student from a multispectral teacher, reached a water IoU of 0.73 on the Sen1Floods11 hand-labelled test chips, against 0.55 for Otsu thresholding [5]. Geo-foundational models such as Prithvi-EO-2.0 report a water IoU of about 83 on the Sentinel-2 chips of the same dataset [6]. SAR is the harder sensor. A benchmark of foundation models and U-Nets on 19 flood events found mean IoU of roughly 0.45 to 0.57 on Sentinel-1, only a few points apart across models, and about 0.5 when a whole region was left out [7]. A review of SAR flood mapping, written for urban areas, surveys the range of methods and the shortage of open SAR datasets [8]. These studies score pixels, and their targets differ from ours, which excludes permanent water. As far as we found, none gives a per-unit number with an uncertainty, or says where to collect ground evidence.`));
add(P(`The unit is what insurance uses. Flood index insurance pays out on a satellite or weather index in place of a loss adjuster's visit, and satellite-derived inundated area has been tested as that index for regional covers [9]. Revisit times and cloud cover limit what the satellite sees, and news reports have been proposed to fill the gaps [10]. The central design problem of such contracts is basis risk, the mismatch between the payout and the true loss [11]. A per-unit call that carries its own uncertainty speaks to that problem, and it is what Paddybird returns.`));
add(P(`Survey sampling has the missing pieces: stratification, inclusion probabilities and weighted estimators [12], and more recent estimators that pair model predictions with a small labelled sample [13]. Planning visits under a time limit is an orienteering problem [14] on a road graph [15]. A flood changes that graph, because closed roads lengthen travel, and a plan drawn on the dry map can overrun the day. Section 4 tests this on a real road graph.`));

// ---------------- 3 Case and Methodology ----------------
add(H1(`3. Case and Methodology`));
add(P(`Paddybird has four algorithmic layers and a tool layer (Figure 1). The subsections follow that order.`, { keepNext: true }));
add(fig(path.join(__dirname, 'fig_layers.png'), 470));
add(FCAP(1, `The five layers of Paddybird and how far each is tested in this paper. Layer 5 (the officer tool) is a demonstration notebook and is only described.`));

add(LEAD(`Data and events`));
add(BODY(`We drew 132 hand-labelled Sen1Floods11 chips [1], 12 at random from each of the 11 events. Each is a 128 x 128 centre crop at 20 m, with VV and VH backscatter (gamma0, dB). Events are never split. Ghana and Sri-Lanka go to validation, India and Bolivia to testing, the remaining seven to training, and a check in the code confirms that no event appears twice. The official Sen1Floods11 split could not serve here: 10 of the 11 events straddle more than one of its splits. Permanent water comes from the JRC layer [16], cropland from ESA WorldCover 2021 [17]. WorldCover has no paddy class; cropland stands in for paddy. Chips with under 30% valid pixels were dropped, which leaves 121.`));
add(LEAD(`Units`));
add(BODY(`Each unit is a 64 x 64 pixel window, about 164 ha, cut from a chip. The split gives 125 training, 27 validation and 34 test units. Test units come from India alone; Bolivia had too few cropland pixels to yield any. A unit's truth is the labelled flooded share of its cropland pixels. These units are stand-ins, not real insurance boundaries.`));
add(LEAD(`Layer 1: data and platform`));
add(BODY(`Scene search runs against public STAC catalogues, with window reads from cloud-optimised files. Each output carries a receipt (scene IDs, parameters, SHA-256 hash). Every field check records its inclusion probability and weight. Routing uses a real OpenStreetMap graph of a Godavari delta block: 2096 nodes, 2567 edges, 475 km of road and 36 grid units.`));
add(LEAD(`Layer 2: mapping`));
add(BODY(`Predictor 1 is a minimum-error threshold on VV and VH [4], softened by a 1 dB threshold-error model, with permanent water removed. Predictor 2 is a gradient-boosted pixel model trained on the training events. A logistic stack fuses the two, with weights fitted per WorldCover group on validation events alone. Calibration was chosen by leave-one-validation-event-out among identity, temperature scaling and isotonic regression. Identity won. Our design also listed an optical index and an external product as predictors; the chips carry no optical bands, so both stayed unused. The baseline is Otsu on VV [3]. After review we added a deep comparison, a small U-Net [18] (four levels, 16 base channels) on VV and VH alone, trained on the same training events and stopped at the best validation IoU. Its output is the raw sigmoid, with no calibration, and it was scored on the test events once. Its setup was fixed in a smoke run on training and validation events before any test pixel was scored. Scores are ECE [19], Brier, IoU, and the ratio of mapped to labelled flooded area.`));
add(LEAD(`Layer 3: estimation`));
add(BODY(`Units are stratified by calibrated score, with cuts at 0.15 and 0.60. Within a unit, the flooded-share estimate starts from the map share of each stratum and corrects it with the map error that the unit's own checks reveal, shrunk towards a prior fitted on training events (Algorithm 1). The call is always made: flooded if the estimate exceeds 0.25. Confidence is P_u = Φ((θ_u − 0.25) / s_u), with s_u a cluster-robust standard error over visit sites. No abstain state exists. A unit with no checks keeps the raw map call.`));
add(gap());
add(algo(`Algorithm 1. Unit call and confidence`, [
  `Split the unit's pixels into three strata by calibrated score (cuts 0.15 and 0.60).`,
  `For each stratum, estimate the true flooded rate from the checks (weighted by 1 / inclusion probability), shrunk towards the training-event rate with a between-event variance term.`,
  `Set θ_u to the stratum-weighted sum. Compute s_u from the variance across visit sites, blended with a model variance when a unit has few sites.`,
  `Call the unit flooded if θ_u > 0.25. Report P_u = Φ((θ_u − 0.25) / s_u).`,
]));
add(gap());
add(LEAD(`Layer 4: field planning`));
add(BODY(`Algorithm 2 picks the next check: the one with the largest expected drop in wrong calls, judged by a Gauss-Hermite look-ahead over its possible outcomes. Algorithm 3 builds the day. It prices each road by flood probability, finds travel times with Dijkstra's algorithm [15], and adds visits by gain per extra minute [14]. Villages are drawn at random with known inclusion probabilities, which keeps layer 3 design-based [12]. Planner settings came from tuning seeds. They were kept apart from the evaluation seeds.`));
add(gap());
add(algo(`Algorithm 2. Greedy allocation of checks`, [
  `For every unit and stratum, compute the expected number of wrong calls now.`,
  `For each candidate check, integrate over its possible outcomes (Gauss-Hermite nodes) and recompute the expected wrong calls.`,
  `Take the check with the largest drop. Repeat until the budget is used.`,
]));
add(gap());
add(algo(`Algorithm 3. Flood-aware routing for K officers`, [
  `Close roads with flood probability above 0.7 and slow the rest by a fitted factor.`,
  `Compute travel times between candidate units with Dijkstra's algorithm on this graph.`,
  `For each officer, add the unit with the best gain (Algorithm 2) per extra minute that still fits the 240 minute day. Re-plan each day.`,
]));
add(gap());
add(LEAD(`Evaluation protocol and metrics`));
add(BODY(`Test events are scored once. Field checks are simulated by drawing sites from hand labels. Estimation results average over Monte Carlo check draws; planning results average over 60 to 160 fixed-seed scenarios, with 95% intervals. Metrics: wrong-call rate, coverage of the 90% interval, ECE of P_u. With only 34 units, the map-only wrong-call rate is a single fixed number (5 of 34), not an average.`));

// ---------------- 4 Results ----------------
add(H1(`4. Results`));
add(LEAD(`Mapping on events not used for fitting`));
add(BODY(`The fused, calibrated map scored IoU 0.42 and ECE 0.039 on the test events; Otsu on VV scored 0.19 and 0.338 (Table 1). By event, IoU was 0.36 for India and 0.53 for Bolivia. The validation-to-test ECE gap was +0.018 for the fused map, +0.036 for the boosted model alone and +0.045 for the soft threshold. The U-Net, a published deep architecture [18] that we trained ourselves on the same events, was close to the fused map and slightly ahead: IoU 0.45 (India 0.41, Bolivia 0.50) and ECE 0.034. Its gaps were less comfortable, though. Validation IoU was 0.58 and fell by 0.13 on test, where the fused map's IoU rose by 0.06, and its ECE gap was +0.031 against +0.018. With two test events we do not call the 0.03 IoU difference real. We did not score it inside the cropland mask and did not feed it into the unit estimator, so the unit-level results below still use the fused map.`, { keepNext: true }));
add(TCAP(1, `Mapping on the two test events (India, Bolivia). Area ratio is mapped over labelled flooded area. The U-Net was trained on VV and VH only and is uncalibrated.`));
add(table([3300, 1200, 1200, 1200, 1500], [
  ['Model', 'ECE', 'Brier', 'IoU', 'Area ratio'],
  ['Otsu on VV (baseline)', '0.338', '0.338', '0.19', '3.18'],
  ['Predictor 1, hard rule', '0.087', '0.087', '0.35', '-'],
  ['Predictor 1, soft', '0.074', '0.078', '0.38', '-'],
  ['Predictor 2, boosted', '0.061', '0.073', '0.29', '-'],
  ['Fused and calibrated', '0.039', '0.063', '0.42', '0.84'],
  ['U-Net [18], added after review', '0.034', '0.064', '0.45', '0.95'],
], [A.LEFT]));
add(gap());
add(BODY(`The boosted model did not beat the threshold rule on IoU, on validation or on test. Brier scores told a more mixed story. On validation events the fused score (0.040) was worse than either predictor alone, which sat near 0.031, and only on test did fusion come out ahead (0.063 against 0.073). That order did not hold earlier, so we do not lean on it. Overall ECE also flatters the map, because most pixels are easy dry ones. Restrict the count to pixels called at least 5% wet and the fused ECE rises to 0.128. Inside the cropland mask the fused ECE was a respectable 0.099 (baseline 0.402), yet the map found only 5.1 km² of flooded cropland where 8.6 km² was labelled, a ratio of 0.60. The baseline, for its part, claimed 16.0 km².`));

add(LEAD(`Estimation with field checks`));
add(BODY(`Table 2 sets three ways of making the call side by side on the 34 India units. The map alone was wrong 14.7% of the time, and no budget changes that, since it uses no checks. Give the estimator 16 randomly drawn checks per unit and it erred 9.8% of the time; at 32 checks the figure fell to 6.8%. Checks on their own did worse, at 13.1% and 9.8%. The intervals were the weak spot. A nominal 90% interval covered the truth 81% and 87% of the time, so they are too narrow. An independent-pixel variance would have cut coverage to 76%. At 16 checks the ECE of P_u was 0.041 (Figures 2 and 3).`, { keepNext: true }));
add(TCAP(2, `Wrong-call rate and coverage of the 90% interval on the India test units, random checks.`));
add(table([2300, 1500, 1500, 1500, 1500], [
  ['Checks per unit', 'Map only', 'Checks only', 'Paddybird', 'Coverage'],
  ['16', '14.7%', '13.1%', '9.8%', '0.81'],
  ['32', '14.7%', '9.8%', '6.8%', '0.87'],
]));
add(gap());
add(fig(path.join(__dirname, 'fig2_wrong_calls.png'), 340));
add(FCAP(2, `Wrong-call rate against field checks per unit on the India test units (Monte Carlo over check draws). The flat line is the map alone, "sample only" is the checks alone, and the stratified PPI line with Hajek weights is the Paddybird estimator.`));
add(fig(path.join(L3, 'fig_test_reliability.png'), 380));
add(FCAP(3, `Reliability of P_u on the India test units at 16 checks per unit: the share of units truly above 0.25 against the stated P_u. "ppi_ipw" is the Paddybird estimator, "ppi_ipw_iid" is the same with independent-pixel variance, and "report_formula" is the simple formula from our partial report. Points far from the diagonal rest on few units.`));
add(BODY(`Two cautions. With no checks at all, the correction learned on training events did worse than the raw map on the test units (RMSE 0.222 against 0.160): the India map under-reads flooding where the training events over-read it. That is why a unit without checks keeps the raw call. The other caution concerns the first estimator, v1, which failed its coverage bound on a single clean test run (0.739 at 16 checks); Section 6 covers the revision and its status.`));

add(LEAD(`Route bias`));
add(BODY(`Officers cannot reach every site; checks are no simple random sample. A synthetic stress test with route-style selection (32 checks) shows the cost. Ignore the inclusion probabilities and the bias is −0.030. The unshrunk Horvitz-Thompson estimator [12] brings it to +0.002, at the price of much higher error. Our default, the shrunk Hajek form, lands at −0.011, with intervals covering 0.78 to 0.80 of truths. Weighting removes bias in expectation only for Horvitz-Thompson. In the planning simulation routing bias was small, and naive pooling had the lower error (0.030 against 0.049). Random selection guarantees no bias; it does not promise smaller error.`));

add(LEAD(`Choosing and routing checks`));
add(BODY(`Allocation rules are compared in Table 3. On synthetic villages at 16 checks each, the decision rule erred 8.6% of the time; random allocation 12.6%, proportional 13.8%, uncertainty-only 14.0%. It matched the 32-check level of the others (about 10%) with about 12 checks. On the real labelled test chips it was best or tied from 2 to 16 checks per unit; at 8 checks, 4.1% against 4.9% for uncertainty-only. At 32 checks it lost to uncertainty-only, 3.6% to 3.1% (paired difference +0.5 points [0.1, 0.9]).`, { keepNext: true }));
add(TCAP(3, `Wrong-call rate by allocation rule. Synthetic villages (80, 60 evaluation seeds) and real test chips. "-" means not reported in this paper.`));
add(table([2500, 1600, 1600, 1600, 1600], [
  ['Setting', 'Decision rule', 'Uncertainty only', 'Random', 'Proportional'],
  ['Synthetic, 16 per village', '8.6%', '14.0%', '12.6%', '13.8%'],
  ['Real chips, 8 per unit', '4.1%', '4.9%', '-', '-'],
  ['Real chips, 32 per unit', '3.6%', '3.1%', '-', '-'],
], [A.LEFT]));
add(gap());
add(fig(path.join(L4, 'fig_wrong_vs_checks.png'), 430));
add(FCAP(4, `Wrong-call rate against checks per village for the four allocation rules on synthetic villages, with 95% intervals.`));
add(BODY(`Few checks were worse than none. At 2 checks per village the decision rule erred 19.2% of the time, at 4 checks 14.7%; the map alone erred 11.4%. Only around 12 checks did the rule pull ahead. In routed campaigns every planner trailed the map on days 1 to 3. Keep the map call until a unit has enough checks.`));
add(BODY(`Routing results are in Table 4: 3 officers, 240-minute days, 5 days. The flood-aware planner made fewer wrong calls than nearest-first routing, by 3.6 points on the synthetic grid and 4.4 on the real road graph. On real roads it also beat the same planner run on the dry map, by 3.1 points [1.3, 4.8] (Figure 5). Against a flood-blind planner on the synthetic grid the gap was not significant, although the flood-aware plan drove 27% less. Pricing roads at their true expected time overstated travel by about 50%; only after fitting the slow-down factor (4, against a true 8) on tuning seeds did it work.`, { keepNext: true }));
add(TCAP(4, `Flood-aware routing against other planners, after 5 days. Difference in wrong-call rate in points, flood-aware minus comparator (negative = fewer wrong calls).`));
add(table([3000, 2200, 1500, 2000], [
  ['Comparator', 'Setting', 'Difference', '95% interval'],
  ['Nearest-first', 'Synthetic grid', '−3.6', '-'],
  ['Nearest-first', 'Real roads', '−4.4', '-'],
  ['Same planner, dry map', 'Real roads', '−3.1', '[−4.8, −1.3]'],
  ['Flood-blind planner', 'Synthetic grid', '−0.9', '[−1.9, +0.1]'],
], [A.LEFT, A.LEFT]));
add(gap());
add(fig(path.join(L4, 'route_day1.png'), 400));
add(FCAP(5, `Day-1 routes for three officers on the real road graph of the Godavari block (flood probabilities on the roads are semi-synthetic). Flooded roads are blue, and villages drawn at random for the survey are circled.`));
add(BODY(`Drawing villages at random with known inclusion probabilities left the Hajek estimates without detectable bias in the flooded rates of mapped strata (within 0.3 points) and cost nothing measurable in village calls (−0.06 points [−0.60, +0.49]). Pooling routed checks without weights overstated the flooded rate of mapped-dry pixels by 1.5 points [1.1, 2.0]. One synthetic scenario in four (about 26%) had the depot inside the flood. No village was reachable, and no random draw could be made.`));

// ---------------- 5 Discussion ----------------
add(H1(`5. Discussion`));
add(LEAD(`How much a flood map leaves`));
add(BODY(`On unseen events a calibrated SAR map still left 14.7% wrong calls on the India units, and it saw only 60% of the flooded cropland area. For any claim about area, that shortfall matters more than the pixel scores.`));
add(LEAD(`When field checks help`));
add(BODY(`Checks pay off once there are enough of them. Between about 12 and 32 per unit, map plus checks beat either alone; below that the estimate is noisier than the map, in the estimator (Table 2) and in the allocation study. Our advice: keep the map call until a unit has about a dozen checks.`));
add(LEAD(`What planning adds`));
add(BODY(`Choosing checks by expected drop in wrong calls helped most at moderate budgets. Flood-aware routing earned its keep when flooded roads really changed the best route. At the extremes, with very few or very many checks, the plain baselines came close. We read that as a property of the evaluation: gains appear where budgets are tight and roads are cut.`));
add(LEAD(`Link to related work`));
add(BODY(`Like the Sen1Floods11 authors [1], we found that simple thresholding is hard to beat on some measures. What the dataset papers [1, 2] leave out is the step after the map, and that is where this work sits. The comparison is only indirect, because they report pixel scores and we report unit calls. Sentinel-1 mapping is hard even for large pretrained models on unseen sites [7], and the U-Net row in Table 1 is consistent with that. The metrics, labels and sites differ, so we compare the pattern and not the numbers.`));

// ---------------- 6 Limitations ----------------
add(H1(`6. Limitations`));
add(LEAD(`Paddy is a proxy`));
add(BODY(`Masking uses WorldCover cropland, so what we measure is flooded cropland and not flooded rice. The chips carry no paddy label, and nothing here can tell the two apart.`));
add(LEAD(`Map shortfall and SAR only`));
add(BODY(`About 40% of the labelled flooded cropland area goes uncounted. The chips have no optical bands, which put optical water indices out of reach. A development run on other chips that did have optical bands scored better, but no decision rests on it.`));
add(LEAD(`Few test events`));
add(BODY(`There are only two test events, and only India yields test units, so every unit-level result here rests on a single flood in a single country. With 34 units, each wrong-call rate moves in coarse steps, and the estimation intervals are wide. Bolivia supports the mapping scores (Table 1) but no unit call. We did not add events after seeing the results, because that would break the rule that test events are scored once, and the split by whole event leaves no further event untouched. Our numbers show that the pipeline behaves sensibly on unseen events. They do not show how large the gains would be in other regions or seasons, and a pilot should score many more events before any rate is quoted.`));
add(LEAD(`Simulated field checks and roads`));
add(BODY(`Field checks are drawn from hand labels. The mapping layer has no flood map for the Godavari block, so road flood probabilities there are semi-synthetic. No officers or trips were observed. The planning study mixes real roads, real chips and synthetic scenarios, and each result says which one it rests on.`));
add(LEAD(`Intervals under-cover`));
add(BODY(`Nominal 90% intervals covered 81% to 87% of truths in estimation and only 78% to 80% under route-style selection. P_u is reasonably calibrated (ECE 0.041), but it is not reliable.`));
add(LEAD(`Units and the duration layer`));
add(BODY(`Units are windows cut from chips, not insurance boundaries. The code has a submergence-duration module, but its onset and duration are simulated; it stays out of the results.`));
add(LEAD(`Changes to the design`));
add(BODY(`Two things were fixed before any result existed: the 25% call threshold and the event split. The estimator was the one thing we changed after seeing results. Version 1 shrank every unit towards the training correction, and on a single clean test run it failed its coverage bound (0.739 at 16 checks). Version 2 adds a between-event prior variance and learns the pool from each region's own checks. We built it on validation data, but only after seeing the v1 test result, so its test numbers are not a clean estimate. The frozen v1 record is in the repository. The mapping test cell was first run in a development run on layer 1 data, and only a crash fix followed, with no tuning. The U-Net comparison was added after the reviews. Its settings were fixed on training and validation events, but its validation IoU picked the stopping epoch, so its validation numbers are optimistic. For planning, the road-closure cut-off (0.7), the slow-down factor (4) and size-proportional village selection were all chosen on tuning seeds kept separate from the evaluation seeds.`));

// ---------------- 7 Conclusion ----------------
add(H1(`7. Conclusion`));
add(P(`On flood events not used for fitting, a calibrated SAR map got 14.7% of unit calls wrong and found only 60% of the flooded cropland area. Sixteen to 32 randomly drawn field checks per unit brought the error down to 9.8% and 6.8%, better than either source alone, though the stated 90% intervals covered just 81% to 87%. In simulation, chosen checks and flood-aware routes helped further. Below about 12 checks per unit the map did better, which is the practical catch. From this we take four habits: report a map-only baseline, score whole events, keep inclusion probabilities for every check, and hold the map call until a unit has enough checks. The evidence comes from two test events, one of which yields units, so the rates above are indicative and not settled. A pilot would need real insurance units, a paddy label, optical bands and the actual trips officers make.`));

add(H1(`Data and code availability`));
add(P(`Sen1Floods11 chips (CC BY 4.0), ESA WorldCover, the JRC surface-water layer, Sentinel-1 scenes from public STAC catalogues and OpenStreetMap roads are all public. Code, the notebooks that produce every table and figure, and the frozen first-run test records are at https://github.com/UnKnownnPasta/paddybird.`, { noIndent: true }));

add(H1(`References`));
const refs = [
  `D. Bonafilia, B. Tellman, T. Anderson, and E. Issenberg, "Sen1Floods11: A georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1," in *Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit. Workshops (CVPRW)*, 2020, pp. 835-845, doi: 10.1109/CVPRW50498.2020.00113.`,
  `N. I. Bountos *et al.*, "Kuro Siwo: 33 billion m2 under the water. A global multi-temporal satellite dataset for rapid flood mapping," in *Adv. Neural Inf. Process. Syst. (NeurIPS)*, 2024, arXiv:2311.12056.`,
  `N. Otsu, "A threshold selection method from gray-level histograms," *IEEE Trans. Syst., Man, Cybern.*, vol. 9, no. 1, pp. 62-66, 1979.`,
  `J. Kittler and J. Illingworth, "Minimum error thresholding," *Pattern Recognit.*, vol. 19, no. 1, pp. 41-47, 1986.`,
  `S. Garg *et al.*, "Cross modal distillation for flood extent mapping," arXiv:2302.08180, 2023.`,
  `D. Szwarcman *et al.*, "Prithvi-EO-2.0: A versatile multi-temporal foundation model for Earth observation applications," arXiv:2412.02732, 2024.`,
  `S. Kaushik, L. Maurya, E. Tellman, and Z. Zhang, "Assessing the value of geo-foundational models for flood inundation mapping: Benchmarking models for Sentinel-1, Sentinel-2, and PlanetScope for end-users," *IEEE J. Sel. Topics Appl. Earth Observ. Remote Sens.*, 2026, arXiv:2511.01990.`,
  `J. Zhao, M. Li, Y. Li, P. Matgen, and M. Chini, "Urban flood mapping using satellite synthetic aperture radar data: A review of characteristics, approaches and datasets," arXiv:2411.04153, 2024.`,
  `B. Tellman, U. Lall, A. K. M. S. Islam, and M. A. Bhuyan, "Regional index insurance using satellite-based fractional flooded area," *Earth's Future*, vol. 10, no. 3, p. e2021EF002418, Mar. 2022, doi: 10.1029/2021EF002418.`,
  `T. Pabari *et al.*, "Flood event extraction from news media to support satellite-based flood insurance," arXiv:2312.14943, 2023.`,
  `M. J. Maier and M. Scherer, "Expectiles as basis risk-optimal payment schemes in parametric insurance," arXiv:2505.02607, 2025.`,
  `D. G. Horvitz and D. J. Thompson, "A generalization of sampling without replacement from a finite universe," *J. Amer. Statist. Assoc.*, vol. 47, no. 260, pp. 663-685, 1952.`,
  `A. N. Angelopoulos, S. Bates, C. Fannjiang, M. I. Jordan, and T. Zrnic, "Prediction-powered inference," *Science*, vol. 382, no. 6671, pp. 669-674, 2023.`,
  `B. L. Golden, L. Levy, and R. Vohra, "The orienteering problem," *Nav. Res. Logist.*, vol. 34, no. 3, pp. 307-318, 1987.`,
  `E. W. Dijkstra, "A note on two problems in connexion with graphs," *Numer. Math.*, vol. 1, pp. 269-271, 1959.`,
  `J.-F. Pekel, A. Cottam, N. Gorelick, and A. S. Belward, "High-resolution mapping of global surface water and its long-term changes," *Nature*, vol. 540, pp. 418-422, 2016.`,
  `D. Zanaga *et al.*, "ESA WorldCover 10 m 2021 v200," Zenodo, 2022, doi: 10.5281/zenodo.7254221.`,
  `O. Ronneberger, P. Fischer, and T. Brox, "U-Net: Convolutional networks for biomedical image segmentation," in *Proc. Int. Conf. Med. Image Comput. Comput.-Assist. Interv. (MICCAI)*, 2015, pp. 234-241.`,
  `C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, "On calibration of modern neural networks," in *Proc. 34th Int. Conf. Mach. Learn. (ICML)*, PMLR 70, 2017, pp. 1321-1330.`,
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
Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(__dirname, 'TR1147.docx'), b); console.log('written', b.length); });
