@echo off
cd /d "%~dp0"

echo =====================================
echo UPDATE SEMUA DATA SAHAM BEI + TREEMAP
echo =====================================

echo [1/4] Update data pasar...
call Update_Data_Saham.bat
if errorlevel 1 goto gagal

echo [2/4] Update data fundamental...
python import_fundamental.py --folder Data_Fundamental --db pasar_bei_prototipe.db --output output_fundamental
if errorlevel 1 goto gagal

echo [3/4] Update dashboard utama...
python dashboard_v2_1.py --db pasar_bei_prototipe.db --output output_dashboard --sector-file "Daftar Saham  sektor.xlsx"
if errorlevel 1 goto gagal

echo [4/4] Update treemap dua tingkat...
python treemap_sector_ticker.py --db pasar_bei_prototipe.db --sector-file "Daftar Saham  sektor.xlsx" --output output_treemap --period 5 --mode net
if errorlevel 1 goto gagal

echo.
echo SEMUA UPDATE BERHASIL.
echo Dashboard: output_dashboard
echo Treemap: output_treemap
pause
exit /b 0

:gagal
echo.
echo UPDATE GAGAL. Periksa pesan error di atas.
pause
exit /b 1
