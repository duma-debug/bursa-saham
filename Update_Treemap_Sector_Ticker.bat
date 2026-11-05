@echo off
cd /d "%~dp0"
python treemap_sector_ticker.py --db pasar_bei_prototipe.db --sector-file "Daftar Saham  sektor.xlsx" --output output_treemap --period 5 --mode net
pause
