BEI CONSOLIDATOR V4.5 - VERIFIED RECONCILIATION PILOT

PURPOSE
- Read existing financial_production.db and financial_review_v4_3.db in READ-ONLY mode.
- Reconcile 13 curated, high-confidence AALI FY2022 figures from PDF audited report against 2022 XBRL legacy previews.
- Create an isolated verified_facts database and 3 transparent CSV reports.
- Never delete, overwrite, or modify original Excel, PDF, or SQLite sources.

IMPORTANT LIMITATION
- This pilot does NOT automatically process other issuers or PDF files.
- Curated PDF reference values were reviewed from uploaded AALI 2022 audited report pages 9-11.
- Source database does not store the PDF bytes. Reconciliation is against those known PDF reference line items, not a newly uploaded/machine-extracted PDF.
- A successful selected-line match does NOT make all AALI financial data valuation-ready.
- EPS is IDR/share while financial statement amounts are IDR million.
- The xbrl 2022 legacy preview has values in presentation units; values from later XBRL often use full units. No general scaling is applied.

INSTALL
1. Extract into C:\Analisis_Saham_BEI\BEI_Consolidator_V4_5
2. Open CMD, run:
   cd /d C:\Analisis_Saham_BEI\BEI_Consolidator_V4_5
3. Run:
   py reconcile_v4_5.py --staging-db "C:\Analisis_Saham_BEI\financial_production.db" --review-db "C:\Analisis_Saham_BEI\financial_review_v4_3.db" --output-db "C:\Analisis_Saham_BEI\financial_verified_v4_5.db" --report "C:\Analisis_Saham_BEI\reconciliation_report_v4_5.json" --csv-dir "C:\Analisis_Saham_BEI\V4_5_Output"

OUTPUT
- financial_verified_v4_5.db
- reconciliation_report_v4_5.json
- V4_5_Output/verified_aali_2022.csv
- V4_5_Output/unresolved_issues.csv
- V4_5_Output/reconciliation_checks.csv

FILES ARE NOT DELETED. If output DB already exists, program stops rather than overwrites it.
