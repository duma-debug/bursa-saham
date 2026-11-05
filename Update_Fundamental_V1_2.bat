@echo off
cd /d "%~dp0"
echo === UPDATE FUNDAMENTAL V1.2 ===
python import_fundamental.py --folder Data_Fundamental --db pasar_bei_prototipe.db --output output_fundamental
if errorlevel 1 (
 echo UPDATE SEBAGIAN GAGAL. Periksa import_validation.csv
) else (
 echo UPDATE BERHASIL. Lihat output_fundamental
)
pause
