@echo off
cd /d "%~dp0"
echo Membuat Integrated Dashboard BEI V2...
python dashboard_v2.py --db pasar_bei_prototipe.db --output output_dashboard
if errorlevel 1 (
 echo GAGAL membuat dashboard. Periksa pesan error.
 pause
 exit /b 1
)
echo Dashboard berhasil diperbarui.
pause
