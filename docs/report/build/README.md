# Rebuilding the partial mini project report

Sources for `docs/report/Paddybird_Partial_Mini_Project_Report.docx`. All text lives in `build.js`.

```bash
cd docs/report/build
python3 fig_layers.py            # five-layer figure, needs matplotlib -> fig_layers.png (fig2.py/fig_arch.png is the retired 3-layer figure)
node build.js                    # needs the npm package `docx` -> report_raw.docx
soffice --headless --convert-to pdf report_raw.docx
python3 toc.py report_raw.docx report_raw.pdf report.docx   # fills the contents page numbers
soffice --headless --convert-to pdf report.docx
```

`cimg-000.png` (VTU emblem) and `cimg-001.png` (RVITM logo) are the cover images. Layout rules: A4, Times New Roman, 14 pt bold centred capital headings, 12 pt justified body at 1.5 spacing, page border on cover and contents, footer "Dept. of CSE, RVITM". Generated files (`report_raw.*`, `report.*`, `tocx/`) are ignored.

On Windows without LibreOffice: `npm i docx`, `node build.js`, then open `report_raw.docx` in Word via COM, update fields and the table of contents, save as the final .docx and export the PDF (this replaces `toc.py`). Figures 2 and 3 are read from `docs/figures/`; the numbers in Section 4 come from `research/threshold_alloc/` (`results.json`, `routing_results.json`, `routing_ipw.py`).
