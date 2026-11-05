@echo off
cd /d "%~dp0"
echo === INTEGRATED STOCK SCREENER V1 ===
python integrated_screener.py --db pasar_bei_prototipe.db --output output_screener
if errorlevel 1 (
 echo GAGAL. Database tidak diubah; periksa pesan di atas.
 pause
 exit /b 1
)
echo.
echo Selesai. Buka output_screener\Integrated_Screener.csv dengan Excel.
pause
