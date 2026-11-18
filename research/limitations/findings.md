# Open-limitation papers (Google Scholar, read via Chrome)

Gap chosen (revised): EO models and flood pipelines state confidence that degrades under regional shift, and terrain false-water is left as future work. Abstention was dropped as a contribution (user decision), so UnivEARTH (Kao et al.) is no longer used in the deck.

## Kept papers

1. **Kao et al., "Towards LLM Agents for Earth Observation" (UnivEARTH)**, Findings of ACL 2026, arXiv 2504.12110.
   - Limitation (Limitations): "the current benchmark does not include unanswerable questions ..., where the ground-truth answer is 'inconclusive.'"
   - Citing papers checked (Scholar "Cited by 30", first page only): Earth-Agent-Pro (2609.12533), Earth-Agent (2509.23141), disaster benchmark (2605.11633), agentic RS survey (2604.24919), IC-EO (2602.00117). Keyword scan for abstain / unanswerable / inconclusive / insufficient evidence: zero hits. Earth-Agent-Pro limitations section read.
   - Not opened: SeaScope, AI4Research survey, HIAPLLM, Deep Research survey (title/snippet only).

2. **Lehmann et al., "Beyond Accuracy: Assessing Calibration of Geospatial Foundation Models and Their Sensitivity to Distribution Shifts"**, arXiv 2608.16614, 2026.
   - Limitation ("Limitations of the frozen probing protocol"): "What this coupling leaves open is whether the same encoders would remain overconfident under a different head, in particular a fine-tuned backbone."
   - Scholar shows no citing papers. Motivation more than a limitation we close.

3. **Gonzalez-Calabuig et al., "SHRUG-FM: Reliability-Aware Foundation Models for Earth Observation"**, CVPR Workshops 2026, arXiv 2511.10370.
   - Limitation: design choices "introduce sensitivity to hyperparameter choices, particularly in low-data regimes."
   - Cited by 6; only the Prithvi crop paper (2610.08810) abstract and Lehmann were read. Other three judged from snippets.

4. **Liang et al., "Rapid Probabilistic Inundation Mapping Using Local Thresholds and Sentinel-1 SAR Data on Google Earth Engine"**, Remote Sensing 17(10):1747, 2025.
   - Limitations (Sec. 4.2): HAND and higher-resolution DEMs left as future refinement; Sen1Floods11 validation "may not represent all flood types."
   - 3 citing papers: Kazakhstan DL paper (opened, no HAND content), a wetland paper (not opened), a JAIST thesis (Japanese, not read). Weakest evidence of the four.

## Rejected / unreadable
- No paper rejected because a newer one solved its limitation.
- Roth et al., "Evaluating the robustness of Bayesian flood mapping" (2025): human-verification wall, not used.
- Geo-OLM (2504.04319): limitations unrelated to our approach, dropped.

## Caveats
- Citing-paper checks were keyword scans plus section reads on arXiv HTML, not full reads. Scholar "Cited by" paged only once for UnivEARTH.
- SHRUG-FM authors beyond the first two not seen (reference reads "et al.").
