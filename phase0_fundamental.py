#!/usr/bin/env python3
"""Preview missing fundamental issuer and optionally import only missing tickers with backup."""
import argparse,sqlite3,sys,datetime
from pathlib import Path
from import_fundamental import read_file, ingest, ensure_db

def main():
    p=argparse.ArgumentParser(description='Audit dan impor fundamental hilang (default preview)')
    p.add_argument('--db',default='pasar_bei_prototipe.db');p.add_argument('--folder',default='Data_Fundamental')
    p.add_argument('--apply',action='store_true')
    a=p.parse_args();db=Path(a.db);folder=Path(a.folder)
    if not db.is_file():sys.exit('STOP: DB tidak ditemukan')
    if not folder.is_dir():sys.exit('STOP: folder fundamental tidak ditemukan')
    con=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        installed={r[0] for r in con.execute('SELECT DISTINCT ticker FROM fundamental')}
        print('Fundamental yang sudah ada:',', '.join(sorted(installed)))
    finally:con.close()
    missing=[];errors=[]
    for f in sorted(folder.glob('Financial data *.xlsx')):
        try:
            ticker,annual,quarter,warnings=read_file(f)
            status='SUDAH ADA' if ticker in installed else 'BELUM ADA'
            print(status, ticker,'annual',len(annual),'quarterly',len(quarter),'warnings',len(set(warnings)))
            if ticker not in installed:
                if not annual or not quarter:errors.append(f'{ticker}: data annual/quarterly kurang')
                else:missing.append((ticker,f))
        except Exception as e:errors.append(f'{f.name}: {e}')
    for e in errors:print('ERROR',e)
    if errors:sys.exit('STOP: masalah pada file fundamental; tidak mengimpor apa pun')
    if not a.apply:print('PREVIEW SAJA; gunakan --apply untuk backup dan impor hanya ticker BELUM ADA');return
    if not missing:print('Tidak ada ticker belum terimpor.');return
    backupdir=db.parent/'Backup_Database'/'Phase0';backupdir.mkdir(parents=True,exist_ok=True)
    dest=backupdir/(db.stem+'_before_fundamental_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
    src=sqlite3.connect(db);destcon=sqlite3.connect(dest)
    try:src.backup(destcon)
    finally:src.close();destcon.close()
    print('Backup:',dest)
    conn=ensure_db(str(db))
    try:
        for ticker,f in missing:
            result=ingest(conn,f)
            print('IMPORTED',result[0],'annual',result[1],'quarter',result[2],'warnings',len(result[3]))
        print('TICKERS:',conn.execute('SELECT COUNT(DISTINCT ticker) FROM fundamental').fetchone()[0])
    finally:conn.close()
if __name__=='__main__':main()
