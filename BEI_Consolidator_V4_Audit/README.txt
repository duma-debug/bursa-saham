BEI Consolidator V4 — READ-ONLY AUDIT / DIAGNOSTIC PACK
=====================================================
This is an audit milestone, NOT full normalized valuation-ready database.
It does not modify the source databases, and cannot delete Excel or PDF.

Run in Command Prompt (cmd):
cd /d C:\Analisis_Saham_BEI\BEI_Consolidator_V4_Audit
py audit_v4.py --foundation-db "C:\Analisis_Saham_BEI\financial_foundation_v3.db" --staging-db "C:\Analisis_Saham_BEI\financial_production.db" --output-dir "C:\Analisis_Saham_BEI\V4_Audit_Output"

Outputs: audit_summary.json, source_audit.csv, audit_findings.csv,
source_accounting_metadata.csv, legacy_2022_labels.csv, pdf_links.csv.

WARNING: Do not delete original Excel/PDF or source SQLite databases.
The monetary figures are not confirmed to be on the same scale across years.
The script will NOT generate financial forecasts or valuations.
