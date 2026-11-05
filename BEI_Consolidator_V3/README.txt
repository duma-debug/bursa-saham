BEI CONSOLIDATOR V3 - DATA FOUNDATION (safe preliminary version)

PURPOSE: Read existing validated V1 SQLite, generate a NEW V3 SQLite database
with provisional matched financial concepts and an indexed catalog of PDF audited
reports. No mutation of V1, V2 or original Excel/PDF. Uses Python standard library.

SUGGESTED WINDOWS STRUCTURE:
C:\Analisis_Saham_BEI\financial_production.db
C:\Analisis_Saham_BEI\Laporan_Keuangan\Excel_XBRL\...
C:\Analisis_Saham_BEI\Laporan_Keuangan\PDF_Audited\...
C:\Analisis_Saham_BEI\BEI_Consolidator_V3\JALANKAN_V3.bat

HOW TO RUN:
1. Extract entire zip into C:\Analisis_Saham_BEI\BEI_Consolidator_V3
2. Ensure PDF_Audited folder exists (it may be empty).
3. Double click JALANKAN_V3.bat.
4. Send C:\Analisis_Saham_BEI\foundation_report_v3.json back for review.

OUTPUT: financial_foundation_v3.db; foundation_report_v3.json
IMPORTANT: The program refuses to overwrite a V3 database. Before re-running,
rename or archive the previous result. NEVER delete financial_production.db.

PDF filenames recommended: AALI_LK_2022_FY.pdf or AALI LK Tahunan 2022.pdf
Filename matching by issuer/year/period is an association, NOT verification
of PDF financial figures. For PDFs without recognizable ticker/year/period,
link_status will be UNMATCHED. PDF references can be linked later manually.

QUALITY / AUDIT LIMITATIONS:
- V3 mapped facts are PROVISIONAL; all review_status=REVIEW, units UNVERIFIED.
- Fundamental facts are not yet fit for DCF, relative valuation or modeling.
- All PDF reports are indexed with SHA-256 and size; contents/notes not parsed.
- Reporting currency, scale and YTD/Q classification need further validation.
- Bank-specific models, shares and corporate actions not yet implemented.
- Original Excel and PDF are NEVER deleted by this program.

DEPENDENCY: Python 3.10+; no pip installs required.
