BEI CONTENT EXPORTER — REVIEW ONLY
==================================
1. Extract ZIP to C:\Analisis_Saham_BEI\BEI_Content_Exporter
2. Run BEI Period Exporter for the desired ticker FIRST:
   cd /d C:\Analisis_Saham_BEI\BEI_Period_Exporter
   py bei_period_export.py --base "C:\Analisis_Saham_BEI" --ticker AALI
3. Run content exporter:
   cd /d C:\Analisis_Saham_BEI\BEI_Content_Exporter
   py bei_content_export.py --base "C:\Analisis_Saham_BEI" --ticker AALI
4. Results: C:\Analisis_Saham_BEI\BEI_Content_Output\AALI
   AALI_YOY_REVIEW.csv : annual/semester/9M YoY candidate calculations
   AALI_DRAF_ARTIKEL_REVIEW.md : draft research-only article
   AALI_*_YOY_REVIEW.png : charts (if matplotlib installed)
   AALI_CONTENT_REPORT.json : quality/completeness overview

To enable charts if not available:
   py -m pip install matplotlib

IMPORTANT:
- Uses ONLY same-filing current+comparative amounts for YoY: no cross-file scaling assumptions.
- All results are REVIEW, NOT VERIFIED FOR PUBLICATION.
- Do not publish numerical assertions before checking the official financial statements.
- Does not compute quarter standalone, TTM, FCF, DCF, or valuations.
- Never deletes or modifies original CSV/Excel/PDF/SQLite.
