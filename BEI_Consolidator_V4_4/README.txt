BEI Consolidator V4.4 - data review (NOT valuation-ready)

1. Extract to C:\Analisis_Saham_BEI\BEI_Consolidator_V4_4
2. Open CMD and run:
cd /d C:\Analisis_Saham_BEI\BEI_Consolidator_V4_4
py verify_v4_4.py --input-db "C:\Analisis_Saham_BEI\financial_review_v4_3.db" --output-db "C:\Analisis_Saham_BEI\financial_review_v4_4.db" --report "C:\Analisis_Saham_BEI\review_report_v4_4.json" --csv-dir "C:\Analisis_Saham_BEI\V4_4_Review_Output"
3. Upload review_report_v4_4.json and bank_balance_review.csv and context_issues.csv.

This is a standalone diagnostic tool using only Python standard library.
Input database opened read-only. Refuses to overwrite existing output database.
Does not normalize monetary amounts, confirm bank reconciliation, create quarter/TTM, or delete originals.
Never remove your Excel/PDF or past databases based on this output.
