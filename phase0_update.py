#!/usr/bin/env python3
"""Phase 0 guarded update; default preview, explicit --apply, never creates DB."""
import argparse,sqlite3,sys,shutil,datetime,re,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from prototipe_bei import date_parse,read_xlsx,ingest,init_db

def get_date(path):
    rows=read_xlsx(path)
    dates=set()
    for row in rows:
        if row.get('last_trade_date'):dates.add(date_parse(row['last_trade_date']))
    if len(dates)!=1:raise ValueError(f'{path.name}: tanggal pada file tidak unik: {dates}')
    return dates.pop()

def main():
    p=argparse.ArgumentParser(description='Update data pasar aman; preview adalah default')
    p.add_argument('--db',default='pasar_bei_prototipe.db')
    p.add_argument('--folder',default='Data_Harian')
    p.add_argument('--apply',action='store_true',help='Backup lalu impor hanya tanggal baru')
    a=p.parse_args(); db=Path(a.db); folder=Path(a.folder)
    if not db.is_file():sys.exit('STOP: database target tidak ditemukan: '+str(db))
    if not folder.is_dir():sys.exit('STOP: folder data harian tidak ditemukan: '+str(folder))
    files=sorted(p for p in folder.glob('*.xlsx') if not p.name.startswith('~$'))
    if not files:sys.exit('STOP: tidak ada file .xlsx di '+str(folder))
    con=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        check=con.execute('PRAGMA integrity_check').fetchone()[0]
        if check!='ok':sys.exit('STOP: integrity_check gagal: '+check)
        existing={d:n for d,n in con.execute('SELECT trade_date,COUNT(*) FROM daily GROUP BY trade_date')}
    finally:con.close()
    new=[];bad=[];skipped=[];seen_dates={}
    for f in files:
        try:
            day=get_date(f)
            if day in seen_dates:bad.append(f'FILE TANGGAL DUPLIKAT {day}: {seen_dates[day].name} dan {f.name}');continue
            seen_dates[day]=f
            if day in existing:
                skipped.append((day,f.name,existing[day]))
                if existing[day]<800:bad.append(f'REVIEW: {day} sudah ada tetapi hanya {existing[day]} ticker; dilewati agar tidak tertimpa')
            else:new.append((day,f))
        except Exception as ex:bad.append(f'{f.name}: {ex}')
    print(f'DB: {db.resolve()} | Sesi eksisting: {len(existing)} | File: {len(files)}')
    print(f'Tanggal baru: {len(new)} | Sudah ada (dilewati): {len(skipped)} | Masalah: {len(bad)}')
    for day,f in new:print('BARU',day,f.name)
    for x in bad:print('PERHATIAN',x)
    if bad:sys.exit('STOP: ada masalah; tidak dilakukan impor. Perbaiki dan jalankan ulang.')
    if not a.apply:
        print('PREVIEW SAJA. Untuk impor jalankan dengan --apply.');return
    if not new:print('Tidak ada tanggal baru; tidak ada perubahan.');return
    backdir=db.parent/'Backup_Database'/'Phase0';backdir.mkdir(parents=True,exist_ok=True)
    dest=backdir/(db.stem+'_before_update_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
    src=sqlite3.connect(db);backup=sqlite3.connect(dest)
    try:src.backup(backup)
    finally:src.close();backup.close()
    print('Backup:',dest)
    conn=sqlite3.connect(db)
    try:
        init_db(conn)
        for day,f in new:
            date,n,delta=ingest(conn,str(f))
            if date!=day:raise RuntimeError('Tanggal berubah secara tak terduga')
            print('OK',date,'file rows',n,'tambahan',delta)
        print('HASIL:',conn.execute('SELECT COUNT(DISTINCT trade_date),COUNT(*),MAX(trade_date) FROM daily').fetchone())
    finally:conn.close()
if __name__=='__main__':main()
