@echo off
cd /d "%~dp0"
py consolidator_v3.py --input-db "C:\Analisis_Saham_BEI\financial_production.db" --output-db "C:\Analisis_Saham_BEI\financial_foundation_v3.db" --pdf-dir "C:\Analisis_Saham_BEI\Laporan_Keuangan\PDF_Audited" --report "C:\Analisis_Saham_BEI\foundation_report_v3.json"
echo.
echo If the output DB already exists, rename it first to preserve the previous version.
echo Send foundation_report_v3.json for audit; NO SOURCE FILES WERE DELETED.
pause
