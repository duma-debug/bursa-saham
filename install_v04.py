"""Install V0.4 onto exact V0.3.1; backup and safe rollback."""
from pathlib import Path
import hashlib,shutil,datetime,py_compile
BASE=Path(__file__).resolve().parent
TARGET=BASE/'bei_platform'/'market.py'
SOURCE=BASE/'patch_files'/'market.py'
EXPECTED='47ac32391f4234e831cbdd71a1e8c9408f8d499f504a12c57a779fdb3ae1f1f4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if not TARGET.is_file() or not SOURCE.is_file():
        print('STOP: ekstrak ZIP di C:\\Analisis_Saham_BEI; file target tidak ditemukan');return
    if sha(TARGET)==sha(SOURCE):print('V0.4 sudah terpasang.');return
    if sha(TARGET)!=EXPECTED:
        print('STOP: market.py tidak identik dengan V0.3.1; tidak ada file diubah.')
        print('SHA256 aktif:',sha(TARGET));return
    py_compile.compile(str(SOURCE),doraise=True)
    backup=TARGET.with_name('market_before_v04_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.py')
    shutil.copy2(TARGET,backup)
    try:
        shutil.copy2(SOURCE,TARGET)
        py_compile.compile(str(TARGET),doraise=True)
    except Exception:
        shutil.copy2(backup,TARGET)
        raise
    print('PATCH SUKSES V0.4 | Backup:',backup)
    print('Jalankan: python start_bei_platform.py')
if __name__=='__main__':main()
