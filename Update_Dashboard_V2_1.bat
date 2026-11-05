@echo off
cd /d "%~dp0"
python dashboard_v2_1.py --db pasar_bei_prototipe.db --output output_dashboard --sector-file "Daftar Saham  sektor.xlsx"
pause
