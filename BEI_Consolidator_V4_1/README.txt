BEI CONSOLIDATOR V4.1 - FINANCIAL MODELING DATA FOUNDATION

This is a deliberately conservative proof-of-structure, NOT a valuation-ready system.
Input databases are opened read-only. No source Excel/PDF files are touched or removed.
Outputs are new separate SQLite and JSON files; never overwrite existing outputs.

Windows CMD:
cd /d C:\Analisis_Saham_BEI\BEI_Consolidator_V4_1
py normalize_v4_1.py --staging-db "C:\Analisis_Saham_BEI\financial_production.db" --foundation-db "C:\Analisis_Saham_BEI\financial_foundation_v3.db" --output-db "C:\Analisis_Saham_BEI\financial_modeling_v4_1.db" --report "C:\Analisis_Saham_BEI\normalization_report_v4_1.json"

REVIEW the JSON report. Do not delete originals.
Data model: source_catalog (filenames, hashes, duplicate detection), metric_dictionary (explicit mappings), facts (one mapped XBRL value per context, with original source cell), findings (legacy data and other gaps), pdf_references (links only).

All facts are intentionally valuation_eligible=0. Values retain raw units, context metadata. Never treat CurrentYearInstant for an income-statement metric as a valid duration. CurrentYearDuration at Q2/Q3 is not automatically an isolated quarter. Prior year comparative contexts are retained separately. Do not calculate EBITDA, FCF, TTM, WACC, or fair value yet.

Known gaps: 2022 files have raw Excel cells but no extracted financial_facts; banking metric mappings require a separate scheme; currency and unit scale need verification at source; report publication dates and restatements are not yet available. Source PDF catalog is not numerical reconciliation.

Next: review mismatch findings, recover 2022 from XBRL raw sheets, audit monetary units, determine dated contexts and sector mappings, reconcile totals, then create approved per-period tables.
