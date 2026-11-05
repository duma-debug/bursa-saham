BEI Consolidator V4.3 - Review only, not valuation ready

1. Extract this folder to C:\Analisis_Saham_BEI\BEI_Consolidator_V4_3.
2. Open CMD and run:
   cd /d C:\Analisis_Saham_BEI\BEI_Consolidator_V4_3
3. Run (all on one line):
   py consolidator_v4_3.py --staging-db "C:\Analisis_Saham_BEI\financial_production.db" --modeling-db "C:\Analisis_Saham_BEI\financial_modeling_v4_1.db" --output-db "C:\Analisis_Saham_BEI\financial_review_v4_3.db" --report "C:\Analisis_Saham_BEI\review_report_v4_3.json"

Safety: Reads both inputs in SQLite read-only mode. Refuses to overwrite output. Does not delete Excel, PDF or any source data. Python standard library only.

The output database contains metadata, context_review, source_quality, legacy_2022_preview, and quality_gates. The CSVs are saved beside the report.

IMPORTANT: XBRL raw values can already be in full currency units even when the financial report is presented in millions. V4.3 records the presentation scale but does NOT multiply amounts. Calendar dates are candidates inferred from XBRL labels, not verified actual XBRL contexts. Legacy 2022 rows are previews, NOT normalized financial facts. All input facts are blocked from valuation. Bank balance discrepancies remain unresolved.
