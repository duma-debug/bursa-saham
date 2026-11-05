#!/usr/bin/env python3
"""BEI XBRL fundamental updater V1.5 (general/property/banking; XBRL scale detection, safe partial import). Dry-run by default; --apply writes safely.
Python stdlib only. Source: Financial_Statement/FinancialStatement-YYYY-I|II|III|IV-TICKER.xlsx.
"""
import argparse, csv, datetime as dt, re, shutil, sqlite3, sys, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
PAT=re.compile(r'^FinancialStatement-(20\d{2})-(I|II|III|IV)-([A-Z0-9]+)\.xlsx$',re.I)
Q={'I':1,'II':2,'III':3,'IV':4}
# IDX XBRL English labels, exact matches to prevent over-broad mapping.
METRICS={
 '1210000':{
 'Cash and cash equivalents':('cash_equivalents','stock_million_idr'),
 'Total current assets':('current_assets','stock_million_idr'),
 'Total assets':('total_assets','stock_million_idr'),
 'Total current liabilities':('current_liabilities','stock_million_idr'),
 'Total liabilities':('total_liabilities','stock_million_idr'),
 'Total equity':('total_equity','stock_million_idr'),
 'Property, plant, and equipment':('fixed_assets','stock_million_idr'),
 },
 '1311000':{
 'Sales and revenue':('revenue','flow_million_idr'),
 'Total gross profit':('gross_profit','flow_million_idr'),
 'Total profit (loss) before tax':('income_before_tax','flow_million_idr'),
 'Total profit (loss)':('net_income','flow_million_idr'),
 'Basic earnings (loss) per share from continuing operations':('eps','flow_idr_per_share'),
 'Diluted earnings (loss) per share from continuing operations':('eps_diluted','flow_idr_per_share'),
 },
 '1510000':{
 'Total net cash flows received from (used in) operating activities':('cash_from_operating','flow_million_idr'),
 'Total net cash flows received from (used in) investing activities':('cash_from_investing','flow_million_idr'),
 'Total net cash flows received from (used in) financing activities':('cash_from_financing','flow_million_idr'),
 },
 '1520000':{
 'Total net cash flows received from (used in) operating activities':('cash_from_operating','flow_million_idr'),
 'Total net cash flows received from (used in) investing activities':('cash_from_investing','flow_million_idr'),
 'Total net cash flows received from (used in) financing activities':('cash_from_financing','flow_million_idr'),
 },
}
# Only directly verified bank metrics; bank interest is NOT generic company revenue.
BANK_BS={'Total assets':('total_assets','stock_million_idr'),
         'Total liabilities':('total_liabilities','stock_million_idr'),
         'Total equity':('total_equity','stock_million_idr'),
         'Property, plant, and equipment':('fixed_assets','stock_million_idr')}
BANK_IS={'Interest income':('bank_interest_income','flow_million_idr'),
         'Interest expenses':('bank_interest_expense','flow_million_idr'),
         'Total profit (loss) before tax':('income_before_tax','flow_million_idr'),
         'Total profit (loss)':('net_income','flow_million_idr'),
         'Basic earnings (loss) per share from continuing operations':('eps','flow_idr_per_share'),
         'Diluted earnings (loss) per share from continuing operations':('eps_diluted','flow_idr_per_share')}
BANK_CF=METRICS['1510000']
# Financing-industry fields are kept separate from generic company revenue.
FINANCE_BS=METRICS['1210000']
FINANCE_IS={
 'Interest and finance income':('financing_interest_income','flow_million_idr'),
 'Income from consumer financing':('financing_consumer_income','flow_million_idr'),
 'Income from provisions and commissions':('financing_fee_income','flow_million_idr'),
 'Total profit (loss) before tax':('income_before_tax','flow_million_idr'),
 'Total profit (loss)':('net_income','flow_million_idr'),
 'Basic earnings (loss) per share from continuing operations':('eps','flow_idr_per_share'),
 'Diluted earnings (loss) per share from continuing operations':('eps_diluted','flow_idr_per_share'),
}
FINANCE_CF=METRICS['1510000']
METRICS.update({'4220000':BANK_BS,'4322000':BANK_IS,'4510000':BANK_CF, '8220000':FINANCE_BS, '8312000':FINANCE_IS, '8510000':FINANCE_CF})
# Property-industry XBRL sheets share the metric labels and column structure.
# Canonicalize only confirmed primary statements; do not guess other industries.
SHEET_CANONICAL={'2210000':'1210000','2311000':'1311000',
                 '2510000':'1510000','2520000':'1520000',
                 '1321000':'1311000','1312000':'1311000','2321000':'1311000'}
REQ={'revenue','net_income','total_assets','total_liabilities','total_equity'}
BANK_REQ={'bank_interest_income','bank_interest_expense','net_income','total_assets','total_liabilities','total_equity'}

def _col(cell):
 s=re.match(r'[A-Z]+',cell or '')
 if not s:return -1
 n=0
 for ch in s.group():n=n*26+ord(ch)-64
 return n-1

def read_sheets(path):
 with zipfile.ZipFile(path) as z:
  shared=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   x=ET.fromstring(z.read('xl/sharedStrings.xml'))
   shared=[''.join(v.text or '' for v in si.findall('.//m:t',NS)) for si in x.findall('m:si',NS)]
  # Use workbook relationship mapping to parse only relevant XBRL sheets.
  wb=ET.fromstring(z.read('xl/workbook.xml'))
  relroot=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
  targets={r.get('Id'):r.get('Target','') for r in relroot}
  rid_key='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
  chosen={'1000000','1210000','1311000','1312000','1321000','1510000','1520000',
          '2210000','2311000','2321000','2510000','2520000','4220000','4322000','4510000','8220000','8312000','8510000'}
  names=[]
  for sheet in wb.findall('.//{*}sheet'):
   if sheet.get('name') not in chosen:continue
   target=targets.get(sheet.get(rid_key),'').lstrip('/')
   if target.startswith('xl/'):name=target
   else:name='xl/'+target
   if name in z.namelist():names.append(name)
  for name in names:
   root=ET.fromstring(z.read(name));rows=[]
   for rr in root.findall('.//m:sheetData/m:row',NS):
    r={}
    for c in rr.findall('m:c',NS):
     k=_col(c.get('r')); v=c.find('m:v',NS);typ=c.get('t')
     if typ=='inlineStr':s=''.join(t.text or '' for t in c.findall('.//m:is//m:t',NS))
     elif v is None:s=None
     elif typ=='s':s=shared[int(v.text)]
     else:s=v.text
     r[k]=s
    rows.append(r)
   yield rows

def read_xbrl(path):
 m=PAT.match(path.name)
 if not m:raise ValueError('Nama file bukan FinancialStatement-YYYY-I|II|III|IV-TICKER.xlsx')
 year=int(m[1]);quarter=Q[m[2].upper()];ticker=m[3].upper()
 all_sheets=list(read_sheets(path));rounding=None;reported_ticker=None
 for rows in all_sheets:
  if not rows or not str(rows[0].get(0) or '').startswith('[1000000]'):continue
  for r in rows:
   if str(r.get(2) or '').strip()=='Entity code':reported_ticker=str(r.get(1) or '').strip().upper()
   if str(r.get(2) or '').strip()=='Level of rounding used in financial statements':
    rounding=str(r.get(1) or '').lower()
 if reported_ticker and reported_ticker!=ticker:raise ValueError(f'Ticker filename {ticker} != isi XBRL {reported_ticker}')
 if not rounding:raise ValueError('Metadata satuan/pembulatan laporan tidak ditemukan; impor dibatalkan')
 if 'full amount' in rounding or 'satuan penuh' in rounding:factor=1/1_000_000
 elif 'in thousand' in rounding or 'ribuan' in rounding:factor=1/1_000
 elif 'in million' in rounding or 'jutaan' in rounding:factor=1
 elif 'in billion' in rounding or 'miliaran' in rounding:factor=1_000
 else:raise ValueError('Satuan laporan belum didukung: '+rounding)
 bank=any(rows and str(rows[0].get(0) or '').startswith('[4220000]') for rows in all_sheets)
 finance=any(rows and str(rows[0].get(0) or '').startswith('[8220000]') for rows in all_sheets)
 if bank and finance:raise ValueError('Jenis bank dan pembiayaan ambigu')
 sheet_sets=({'4220000':('4220000',),'4322000':('4322000',),'4510000':('4510000',)} if bank else
             {'8220000':('8220000',),'8312000':('8312000',),'8510000':('8510000',)} if finance else
             {'1210000':('1210000','2210000'),'1311000':('1311000','1312000','1321000','2311000','2321000'),
              '1510000':('1510000','1520000','2510000','2520000')})
 sheet_candidates={k:[] for k in sheet_sets};recognized=[]
 for rows in all_sheets:
  title=str(rows[0].get(0) or '') if rows else ''
  sm=re.match(r'\[(\d+)\]',title)
  if not sm:continue
  sheet=sm[1]
  for canonical,options in sheet_sets.items():
   if sheet not in options:continue
   v={}
   for r in rows[1:]:
    label=str(r.get(3) or '').strip(); spec=METRICS[canonical].get(label)
    if not spec or r.get(1) in (None,''):continue
    try:value=float(str(r[1]).replace(',',''))*factor
    except ValueError:raise ValueError(f'{sheet} {label}: nilai bukan angka')
    if not __import__('math').isfinite(value):raise ValueError(f'{sheet} {label}: nilai non-finite')
    key,unit=spec
    # EPS is in Rp/share, even when statement amounts are presented in thousands/millions.
    if unit=='flow_idr_per_share':value=float(str(r[1]).replace(',',''))
    v[key]=(value,unit)
   sheet_candidates[canonical].append((sheet,v))
   if v:recognized.append(sheet)
 vals={};used=[]
 for canonical,candidates in sheet_candidates.items():
  # Highest number of mapped fields indicates the populated primary statement.
  # If two equally populated variants disagree, fail rather than choosing arbitrarily.
  ranked=sorted(candidates,key=lambda x:len(x[1]),reverse=True)
  if not ranked or not ranked[0][1]:continue
  chosen=ranked[0];used.append(chosen[0]);vals.update(chosen[1])
  for sheet,alternative in ranked[1:]:
   if len(alternative)!=len(chosen[1]) or not alternative:continue
   for metric,entry in alternative.items():
    if metric in chosen[1] and abs(chosen[1][metric][0]-entry[0])>max(1e-6,abs(entry[0])*1e-8):
     raise ValueError(f'Sheet {chosen[0]} dan {sheet} berbeda untuk {metric}')
 required=BANK_REQ if bank else {'net_income','total_assets','total_liabilities','total_equity','financing_interest_income'} if finance else REQ
 missing=required-set(vals)
 if missing:raise ValueError('Field wajib tidak ditemukan: '+', '.join(sorted(missing)))
 a=vals['total_assets'][0];le=vals['total_liabilities'][0]+vals['total_equity'][0]
 if a<=0:raise ValueError('Total assets tidak valid')
 if abs(a-le)>max(1,a*0.005):raise ValueError('Balance sheet tidak reconcile: assets != liabilities + equity')
 warnings=[]
 if 'cash_from_operating' not in vals:warnings.append('CFO tidak tersedia')
 if not bank and not finance and 'operating_profit' not in vals:warnings.append('Operating profit belum dipetakan secara aman')
 if 'operating_profit' not in vals and not bank and not finance and 'Operating profit belum dipetakan secara aman' not in warnings:
  warnings.append('Operating Profit belum dapat divalidasi dari label XBRL; tidak diestimasi')
 if bank:warnings.append('BANK: pendapatan bunga disimpan terpisah, bukan revenue perusahaan umum; tidak menghitung NIM/NPL')
 if finance:warnings.append('FINANCING: komponen pendapatan pembiayaan disimpan terpisah; bukan Revenue umum')
 return {'file':path,'ticker':ticker,'year':year,'quarter':quarter,'vals':vals,'warnings':warnings,
         'source_scale':rounding,'sheets':used,'bank':bank,'finance':finance}

def schema_check(conn):
 must={
 'fundamental':{'ticker','fiscal_year','fiscal_quarter','metric','raw_value','quarter_value','unit','input_basis','source_file','publication_date'},
 'fundamental_annual':{'ticker','fiscal_year','metric','raw_value','unit','input_basis','source_file','publication_date'},
 }
 for table,cols in must.items():
  actual={r[1] for r in conn.execute('PRAGMA table_info('+table+')')}
  if not cols<=actual:raise ValueError(f'Skema {table} tidak cocok / tabel belum ada. Gunakan database aplikasi yang sudah diinisialisasi; tidak ada perubahan dilakukan.')

def apply_file(conn,record):
 t,y,q=record['ticker'],record['year'],record['quarter']
 # Never purge the ticker. Update only explicit metrics from the matched filing.
 for metric,(value,unit) in sorted(record['vals'].items()):
  basis='YTD' if unit.startswith('flow_') else 'SNAPSHOT'
  quarter_value=value if (not unit.startswith('flow_') or q==1) else None
  if unit.startswith('flow_') and q>1:
   prev=conn.execute('SELECT raw_value FROM fundamental WHERE ticker=? AND fiscal_year=? AND fiscal_quarter=? AND metric=? AND input_basis=?',(t,y,q-1,metric,'YTD')).fetchone()
   if prev is not None and prev[0] is not None:quarter_value=value-prev[0]
  conn.execute('''INSERT INTO fundamental(ticker,fiscal_year,fiscal_quarter,metric,raw_value,quarter_value,unit,input_basis,source_file,publication_date)
     VALUES(?,?,?,?,?,?,?,?,?,NULL)
     ON CONFLICT(ticker,fiscal_year,fiscal_quarter,metric) DO UPDATE SET
     raw_value=excluded.raw_value,quarter_value=excluded.quarter_value,unit=excluded.unit,
     input_basis=excluded.input_basis,source_file=excluded.source_file,updated_at=CURRENT_TIMESTAMP''',
     (t,y,q,metric,value,quarter_value,unit,basis,record['file'].name))
  if q==4:
   year_basis='FY' if unit.startswith('flow_') else 'FY_SNAPSHOT'
   conn.execute('''INSERT INTO fundamental_annual(ticker,fiscal_year,metric,raw_value,unit,input_basis,source_file,publication_date)
    VALUES(?,?,?,?,?,?,?,NULL) ON CONFLICT(ticker,fiscal_year,metric) DO UPDATE SET
    raw_value=excluded.raw_value,unit=excluded.unit,input_basis=excluded.input_basis,source_file=excluded.source_file,updated_at=CURRENT_TIMESTAMP''',
    (t,y,metric,value,unit,year_basis,record['file'].name))

def main():
 p=argparse.ArgumentParser(description='Impor XBRL BEI fundamental (preview secara default).')
 p.add_argument('--folder',default='Financial_Statement');p.add_argument('--db',default='pasar_bei_prototipe.db')
 p.add_argument('--apply',action='store_true');p.add_argument('--ticker',help='Filter emiten, contoh FORE')
 p.add_argument('--skip-invalid',action='store_true',help='Impor hanya file yang VALID; simpan laporan gagal. Default tetap all-or-nothing.')
 p.add_argument('--report',default='fundamental_update_report.csv',help='Lokasi CSV audit per file')
 p.add_argument('--diagnose',action='store_true',help='Tampilkan nomor dan nama sheet XBRL file yang gagal')
 a=p.parse_args(); folder=Path(a.folder);db=Path(a.db)
 if not folder.is_dir():print('ERROR: Folder tidak ditemukan:',folder);return 2
 files=sorted(f for f in folder.glob('*.xlsx') if f.is_file() and not f.name.startswith('~$') and (not a.ticker or f.name.upper().endswith('-'+a.ticker.upper()+'.XLSX')))
 if not files:print('ERROR: Tidak ada file Excel untuk diproses');return 2
 good=[];bad=[]
 for file in files:
  try:
   rec=read_xbrl(file);good.append(rec)
   print(f"OK {rec['file'].name}: {rec['ticker']} {rec['year']} Q{rec['quarter']} | {len(rec['vals'])} metrik (juta Rp) | sheet={','.join(rec['sheets'])} | skala={rec['source_scale']}")
   for w in rec['warnings']:print('  PERINGATAN:',w)
  except Exception as e:
   bad.append((file.name,str(e)));print('GAGAL:',file.name,'—',e)
   if a.diagnose:
    try:
     for rows in read_sheets(file):
      if rows and str(rows[0].get(0) or '').startswith('['):print('    SHEET:',str(rows[0].get(0))[:140])
    except Exception as exc:print('    GAGAL INSPEKSI SHEET:',exc)
 # Audit CSV contains filenames and status, never transaction amounts or private database records.
 try:
  report=Path(a.report)
  if report.parent!=Path('.'):report.parent.mkdir(parents=True,exist_ok=True)
  with report.open('w',newline='',encoding='utf-8-sig') as outf:
   writer=csv.writer(outf);writer.writerow(['file','status','ticker','year','quarter','metrics','issue'])
   for rec in good:writer.writerow([rec['file'].name,'VALID',rec['ticker'],rec['year'],rec['quarter'],len(rec['vals']),''])
   for name,why in bad:writer.writerow([name,'INVALID','','','','',why])
  print('LAPORAN:',report)
 except OSError as exc:
  print('DIBATALKAN: gagal menulis laporan audit:',exc);return 2
 if not a.apply:
  print(f'PREVIEW: {len(good)} file valid, {len(bad)} gagal. Belum ada database yang diubah. Jalankan --apply setelah pemeriksaan.')
  return 1 if bad else 0
 if bad and not a.skip_invalid:
  print('DIBATALKAN: ada file tidak valid; default all-or-nothing. Gunakan --skip-invalid HANYA jika ingin impor file valid.');return 2
 if not good:
  print('DIBATALKAN: tidak ada file valid untuk diimpor.');return 2
 if bad:print('PERINGATAN: mode --skip-invalid,',len(bad),'file invalid dilewati dan dicatat pada CSV')
 if not db.is_file():print('DIBATALKAN: database tidak ditemukan:',db);return 2
 conn=sqlite3.connect(db)
 try:schema_check(conn)
 except Exception as e:conn.close();print('DIBATALKAN:',e);return 2
 backupdir=db.parent/'Backup_Database';backupdir.mkdir(exist_ok=True)
 stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 backup=backupdir/(db.stem+'_before_fundamental_'+stamp+'.db')
 dst=sqlite3.connect(backup)
 try:conn.backup(dst)
 finally:dst.close()
 print('BACKUP:',backup)
 try:
  conn.execute('BEGIN IMMEDIATE')
  for rec in good:apply_file(conn,rec)
  conn.commit()
 except Exception as e:
  conn.rollback();print('GAGAL, transaksi dibatalkan:',e);return 2
 finally:conn.close()
 print('BERHASIL:',len(good),'file valid diproses;',len(bad),'file gagal dilewati. Tabel daily tidak diubah.')
 return 0
if __name__=='__main__':sys.exit(main())
