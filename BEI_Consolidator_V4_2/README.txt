BEI Consolidator V4.2 — DATA QUALITY AUDIT (SAFE / READ ONLY)

Purpose: audit the actual V4.1 financial_modeling SQLite database and export detailed review CSVs.
This is NOT a complete normalizer. It does not resolve units, infer quarter/YTD, modify any DB, or delete files.

Windows CMD:
cd /d C:\Analisis_Saham_BEI\BEI_Consolidator_V4_2
py audit_v4_2.py --input-db "C:\Analisis_Saham_BEI\financial_modeling_v4_1.db" --output-dir "C:\Analisis_Saham_BEI\V4_2_Audit_Output"

Outputs: audit_report_v4_2.json and eight CSV reports.
Do not import review-only numbers into valuation models.
Important: balance_diagnostics compares raw reported amounts only when context is identical; a zero arithmetic difference is not evidence of correct units/scope.
Do not delete Excel/PDF original files.
