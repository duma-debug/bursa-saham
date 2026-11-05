BEI FINANCIAL PERIOD EXPORTER — CURRENT + COMPARATIVE

1. Extract ZIP to C:\Analisis_Saham_BEI\BEI_Period_Exporter
2. Keep financial_modeling_v4_1.db and financial_legacy_v4_6.db in C:\Analisis_Saham_BEI
3. Open CMD:
   cd /d C:\Analisis_Saham_BEI\BEI_Period_Exporter
   py bei_period_export.py --base "C:\Analisis_Saham_BEI" --ticker AALI
4. Open output folder C:\Analisis_Saham_BEI\BEI_Master_Output

Outputs:
* <TICKER>_all_periods_ALL_VERSIONS_REVIEW.csv — all source versions, incl comparator
* <TICKER>_periods_SELECTED_REVIEW.csv — candidate per period/metric; may hide restatements, not authoritative
* <TICKER>_period_export_report.json — coverage summary

IMPORTANT:
Data are NOT VERIFIED: numeric values remain raw XBRL (not Rp million automatically).
PriorEndYearInstant refers typically to the previous FY-end balance sheet,
NOT the same quarter last year. Income & cash flow prior duration generally
refers to the comparative YTD, NOT standalone quarter.
Quarterly Q2 = H1 - Q1 can only be computed AFTER verifying matching period,
unit, scope, and restatement vintage. No growth, TTM, or valuation is calculated.
Source databases and Excel/PDF remain untouched.
