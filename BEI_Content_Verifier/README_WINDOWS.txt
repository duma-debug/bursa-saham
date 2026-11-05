BEI Content Verifier v1.0 — Windows

1. Extract ZIP to C:\Analisis_Saham_BEI\BEI_Content_Verifier
2. Open Command Prompt and run:
   cd /d C:\Analisis_Saham_BEI\BEI_Content_Verifier
   py bei_content_verify.py --base "C:\Analisis_Saham_BEI" --ticker AALI
3. Output: C:\Analisis_Saham_BEI\BEI_Content_Verification_Output\AALI

Required inputs:
- C:\Analisis_Saham_BEI\financial_production.db
- C:\Analisis_Saham_BEI\BEI_Master_Output\AALI_periods_SELECTED_REVIEW.csv

If CSV absent, first run BEI_Period_Exporter for the ticker.

Checks match each exported raw value to the SQLite staging source cell and source SHA,
then calculate conservative same-filing comparative YoY previews.

IMPORTANT: SOURCE_MATCHED_REVIEW does not mean verified audited financial data.
PDF reconciliation, accounting scale, bank mapping, and true fiscal period must be checked
before publication or use in valuation. Nothing is deleted or modified.
