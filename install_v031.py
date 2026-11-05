"""Install V0.3.1 only onto the exact V0.3 market.py; backups and no DB changes."""
from pathlib import Path
import hashlib, shutil, datetime, py_compile
BASE=Path(__file__).resolve().parent
TARGET=BASE/'bei_platform'/'market.py'
SOURCE=BASE/'patch_files'/'market.py'
EXPECTED='06c56a09f4dfbe5226fc802acd0b5129c5d18abba16e0a1acd4d7731b61033e4'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    if not TARGET.is_file() or not SOURCE.is_file():
        print('STOP: file tidak ditemukan. Jalankan dari C:\\Analisis_Saham_BEI setelah ekstraksi ZIP.');return
    if sha(TARGET)==sha(SOURCE):print('V0.3.1 sudah terpasang.');return
    if sha(TARGET)!=EXPECTED:
        print('STOP: market.py aktif tidak identik dengan Stock Detail Pro V0.3. Tidak ada yang diubah.')
        print('SHA256 kode aktif:',sha(TARGET));return
    py_compile.compile(str(SOURCE),doraise=True)
    backup=TARGET.with_name('market_before_v031_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.py')
    shutil.copy2(TARGET,backup)
    try:
        shutil.copy2(SOURCE,TARGET)
        py_compile.compile(str(TARGET),doraise=True)
    except Exception:
        shutil.copy2(backup,TARGET)
        raise
    print('PATCH SUKSES: Fundamental charts V0.3.1 | Backup:',backup)
    print('Jalankan: python start_bei_platform.py')
if __name__=='__main__':main()
