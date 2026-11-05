
@echo off
cd /d "%~dp0"

echo =====================================
echo UPDATE DATA SAHAM BEI
echo =====================================

for %%F in ("Data_Harian\*.xlsx") do (
    echo Memproses: %%~nxF
    python prototipe_bei.py --input "%%~fF"

    if errorlevel 1 (
        echo GAGAL memproses %%~nxF
        pause
        exit /b 1
    )
)

echo.
echo UPDATE DATA SELESAI
pause
