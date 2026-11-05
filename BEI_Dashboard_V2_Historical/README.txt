BEI Dashboard V2 Historical — Investor Mandiri

INSTALL
1. Extract folder BEI_Dashboard_V2_Historical to C:\Analisis_Saham_BEI\BEI_Dashboard_V2_Historical
2. Double-click dashboard_v2.pyw; if Windows blocks it, scan first and do NOT disable security.
   Alternatively CMD:
   cd /d C:\Analisis_Saham_BEI\BEI_Dashboard_V2_Historical
   py dashboard_v2.pyw
3. Default database: C:\Analisis_Saham_BEI\BEI_Master_Output\BEI_Financial_Master.db.
   If database differs, click Pilih Database.

FEATURES
- Fixed account column on left, oldest financial period at left, NEWEST AT RIGHT.
- Annual, Quarterly (YTD flow data), All.
- Income, Balance, Cashflow or All.
- Comparative financial values are assigned to the year they refer to.
- Click a number to view its originating file/cell, currency and scale.
- CSV exports in C:\Analisis_Saham_BEI\BEI_Dashboard_Output\<ticker>.

IMPORTANT LIMITATIONS
- All numeric amounts are as reported in XBRL and NOT adjusted into uniform units across filings.
- Values may be in rupiah full amounts, millions or foreign currencies, even in adjacent columns.
- No automatic quarterly standalone, TTM, valuation, PDF reconciliation, or verified restatement precedence.
- If different filings report the same metric/period, the most recent filing-year value is shown provisionally and alternatives counted. This is NOT a verified latest/restatement rule.
- Legacy 2022 data still missing in financial_facts will not appear as mapped metrics.
- Entire application uses SQLite read-only and does not delete or modify originals.
