"""Install verified BEI Stock Detail Pro patch; never touches SQLite/data files."""
from pathlib import Path
import hashlib, shutil, datetime, sys, py_compile
HERE=Path(__file__).resolve().parent
TARGET=HERE/'bei_platform'/'market.py'
NEW=HERE/'patch_files'/'market.py'
# Exact source version provided by user on Oct 31 2026.
EXPECTED='e481a9a27a307b395246b29925ed8f1723e993bdc8b9ee5a5bd8e963863b2211'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if not TARGET.is_file():raise SystemExit('STOP: bei_platform/market.py tidak ada. Tidak ada file diubah.')
    current=sha(TARGET)
    if current==sha(NEW):print('Patch sudah terpasang. Tidak ada perubahan.');return
    if current!=EXPECTED:
        print('STOP: kode market.py di komputer berbeda dengan sumber yang diuji.')
        print('SHA256 aktif:',current)
        print('Jangan timpa; kirim market.py yang baru untuk penyesuaian.')
        return
    backup=TARGET.with_name('market_before_stock_pro_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.py')
    shutil.copy2(TARGET,backup)
    try:
        py_compile.compile(str(NEW),doraise=True)
        shutil.copy2(NEW,TARGET)
        py_compile.compile(str(TARGET),doraise=True)
    except Exception:
        shutil.copy2(backup,TARGET)
        print('GAGAL: file awal dipulihkan dari backup.')
        raise
    print('PATCH SUKSES. Backup:',backup)
    print('Buka: python start_bei_platform.py')
if __name__=='__main__':main()
