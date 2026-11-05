BEI Consolidator V4.6 — Legacy 2022 Recovery (review-only)

1. Extract ZIP into C:\Analisis_Saham_BEI\BEI_Consolidator_V4_6
2. Open CMD (not the BAT file) and cd into that folder.
3. Run:
py normalize_v4_6.py --staging-db "C:\Analisis_Saham_BEI\financial_production.db" --modeling-db "C:\Analisis_Saham_BEI\financial_modeling_v4_1.db" --review-db "C:\Analisis_Saham_BEI\financial_review_v4_3.db" --output-db "C:\Analisis_Saham_BEI\financial_legacy_v4_6.db" --report "C:\Analisis_Saham_BEI\legacy_report_v4_6.json" --csv-dir "C:\Analisis_Saham_BEI\V4_6_Output"

V4.6 does not change source databases or delete files. It recovers exact-label legacy 2022 rows from previous 2022 previews, preserving reported presentation units. These recovered items are REVIEW, not verified. Many distinct labels remain unmapped. The other original 2023+ facts are not reprocessed, only reviewed for calendar metadata context; values cannot yet be used for DCF/valuation.
Output already exists? The script intentionally stops. Archive/move old output before rerun.
Requires Python 3.10+; standard library only.
