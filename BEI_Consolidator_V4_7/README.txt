BEI Consolidator V4.7 — non-destructive consolidation (Windows)

1. Extract this ZIP into C:\Analisis_Saham_BEI\BEI_Consolidator_V4_7
2. Open CMD and run:
cd /d C:\Analisis_Saham_BEI\BEI_Consolidator_V4_7
py consolidate_v4_7.py --legacy-db "C:\Analisis_Saham_BEI\financial_legacy_v4_6.db" --output-db "C:\Analisis_Saham_BEI\financial_history_v4_7.db" --report "C:\Analisis_Saham_BEI\history_report_v4_7.json" --csv-dir "C:\Analisis_Saham_BEI\V4_7_Output"

Safety: input DB is opened read-only. Output will NOT be overwritten. No Excel/PDF deletion or automatic financial forecasts. Source figures remain presentation-scale and REVIEW; verification requires source XBRL/PDF, correct unit, and calendar-period semantics.

For broader 2023–2026 financial values, the V4.1 modeling database must be joined in a later version. V4.6 stores 13,306 context assessments but not those underlying values.
