@echo off
cd /d "%~dp0"
echo ===============================
echo TREEMAP BEI - MULTI MODE
 echo ===============================
echo 1. Foreign Buy
echo 2. Foreign Sell
echo 3. Foreign Net Buy/Sell
set /p pilihan=Pilihan mode [1/2/3]: 
if "%pilihan%"=="1" set MODE=buy
if "%pilihan%"=="2" set MODE=sell
if "%pilihan%"=="3" set MODE=net
if not defined MODE goto gagal
echo.
set /p PERIOD=Periode [1/5/10/20] (default 5): 
if "%PERIOD%"=="" set PERIOD=5
if not "%PERIOD%"=="1" if not "%PERIOD%"=="5" if not "%PERIOD%"=="10" if not "%PERIOD%"=="20" goto gagal
echo.
python treemap_sector_ticker.py --db pasar_bei_prototipe.db --sector-file "Daftar Saham  sektor.xlsx" --output output_treemap --mode %MODE% --period %PERIOD% --interactive
if errorlevel 1 goto gagal
echo.
echo PROSES BERHASIL. Lihat folder output_treemap.
pause
exit /b 0
:gagal
echo ERROR: pilihan tidak valid atau proses gagal.
pause
exit /b 1
