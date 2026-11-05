@echo off
cd /d "%~dp0"
echo =============================================
echo FUNDAMENTAL IMPORTER V1.1 - BEI
 echo =============================================
if exist "pasar_bei_prototipe.db" (
  if not exist "backup_database" mkdir "backup_database"
  copy /Y "pasar_bei_prototipe.db" "backup_database\pasar_bei_sebelum_V1_1.db" >nul
  if errorlevel 1 (
    echo GAGAL membuat backup database. Proses dibatalkan.
    pause
    exit /b 1
  )
  echo Backup database dibuat.
)
python import_fundamental.py --folder Data_Fundamental --db pasar_bei_prototipe.db --output output_fundamental
if errorlevel 1 (
  echo.
  echo PROSES GAGAL. Periksa pesan di atas.
  pause
  exit /b 1
)
echo.
echo SELESAI. Periksa folder output_fundamental.
pause
