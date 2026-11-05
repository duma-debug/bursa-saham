#!/usr/bin/env python3
"""Importer V1.2 - template 'Financial data TICKER.xlsx'. Stdlib Python only.
Usage: python import_fundamental.py --folder Data_Fundamental --db pasar_bei_prototipe.db
"""
import argparse, csv, datetime, re, sqlite3, sys, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
MAP={
 'Total Sales':('revenue','flow_million_idr'), 'Gross Profit':('gross_profit','flow_million_idr'),
 'Operating Profit':('operating_profit','flow_million_idr'), 'Income Before Tax':('income_before_tax','flow_million_idr'),
 'Net Income':('net_income','flow_million_idr'), 'Cash Equivalents':('cash_equivalents','stock_million_idr'),
 'Current Assets':('current_assets','stock_million_idr'), 'Fixed Assets':('fixed_assets','stock_million_idr'),
 'Total Assets':('total_assets','stock_million_idr'), 'Current Liabilities':('current_liabilities','stock_million_idr'),
 'Long Term Debt':('long_term_debt','stock_million_idr'), 'Minority Interest':('minority_interest','stock_million_idr'),
 'Total Liabilities':('total_liabilities','stock_million_idr'), 'Total Equity':('total_equity','stock_million_idr'),
 'EPS':('eps','flow_idr_per_share'), 'EPS Quarter':('eps_quarter_reported','reported_idr_per_share'), 'Price':('price_reference','reported_idr_per_share'), 'Outstanding Shares':('outstanding_shares','stock_million_shares'),
 'Cash From Operating Act':('cash_from_operating','flow_million_idr'),
 'Cash From Investing Act':('cash_from_investing','flow_million_idr'),
 'Cash From Financing Act':('cash_from_financing','flow_million_idr'),
 'PER (X)':('per_reported','ratio_x'), 'PBV (X)':('pbv_reported','ratio_x'),
 'EV/EBTIDA (X)':('ev_ebitda_reported','ratio_x'), 'BVPS':('bvps','stock_idr_per_share'),
 'ROA':('roa_reported','percent'), 'ROE':('roe_reported','percent'), 'DER (X)':('der_reported','ratio_x'),
 'Sales Growth':('sales_growth_reported','percent'),
 'Operating Income Growth':('operating_income_growth_reported','percent'),
 'Net Income Growth':('net_income_growth_reported','percent'),
 'Gross Profit Margin':('gross_margin_reported','percent'),
 'Operating Profit Margin':('operating_margin_reported','percent'),
 'Net Profit Margin':('net_margin_reported','percent')}
# "stock" means snapshot; flow means YTD cumulative in quarterly source.

def column_index(ref):
 m=re.match(r'([A-Z]+)',ref)
 if not m:return None
 n=0
 for c in m.group(1):n=n*26+ord(c)-64
 return n-1

def excel_rows(path):
 with zipfile.ZipFile(path) as z:
  shared=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   root=ET.fromstring(z.read('xl/sharedStrings.xml'))
   shared=[''.join(t.text or '' for t in x.findall('.//x:t',NS)) for x in root.findall('x:si',NS)]
  sheets=sorted([n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)],key=lambda s:int(re.search(r'sheet(\d+)',s).group(1)))
  for idx,name in enumerate(sheets,1):
   root=ET.fromstring(z.read(name)); rows=[]
   for r in root.findall('.//x:sheetData/x:row',NS):
    d={}
    for cell in r.findall('x:c',NS):
     col=column_index(cell.attrib.get('r',''))
     if col is None:continue
     v=cell.find('x:v',NS)
     if cell.attrib.get('t')=='inlineStr': val=''.join(t.text or '' for t in cell.findall('.//x:is//x:t',NS))
     elif v is None:val=None
     elif cell.attrib.get('t')=='s':val=shared[int(v.text)]
     else:val=v.text
     d[col]=val
    rows.append(d)
   yield idx, rows

def period(head):
 s=str(head or '').strip().upper().lstrip('(')
 m=re.fullmatch(r'Q([1-4])\s+(\d{2}|\d{4})(?:\s*\(M\))?',s)
 if not m:return None
 q=int(m.group(1));y=int(m.group(2));y=2000+y if y<100 else y
 return y,q

def parse_value(v):
 if v is None or str(v).strip().upper() in ('','-','N/A','NA','NAN','#REF!','#N/A','#DIV/0!','#VALUE!','#NUM!','#NAME?','#NULL!'):return None
 try:return float(str(v).replace(',','').strip())
 except ValueError:raise ValueError('Nilai non-numerik: '+repr(v))

def ensure_db(db):
 conn=sqlite3.connect(db)
 conn.executescript('''
 CREATE TABLE IF NOT EXISTS fundamental (
 ticker TEXT NOT NULL, fiscal_year INTEGER NOT NULL, fiscal_quarter INTEGER NOT NULL,
 metric TEXT NOT NULL, raw_value REAL, quarter_value REAL, unit TEXT NOT NULL,
 input_basis TEXT NOT NULL, source_file TEXT NOT NULL, publication_date TEXT,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(ticker,fiscal_year,fiscal_quarter,metric));
 CREATE TABLE IF NOT EXISTS fundamental_annual (
 ticker TEXT NOT NULL, fiscal_year INTEGER NOT NULL, metric TEXT NOT NULL,
 raw_value REAL, unit TEXT NOT NULL, input_basis TEXT NOT NULL,
 source_file TEXT NOT NULL, publication_date TEXT,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(ticker,fiscal_year,metric));
 CREATE TABLE IF NOT EXISTS fundamental_import_log (
 imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, source_file TEXT, ticker TEXT,
 records_read INTEGER, records_saved INTEGER, warnings TEXT);
 ''')
 return conn

def read_file(path):
 mt=re.fullmatch(r'Financial\s+data\s+([A-Za-z0-9]+)\.xlsx',path.name,re.I)
 if not mt:raise ValueError('Nama file harus: Financial data TICKER.xlsx')
 ticker=mt.group(1).upper(); annual={}; quarterly={}; warnings=[]
 sheets={num:rows for num,rows in excel_rows(path)}
 if 1 not in sheets or 2 not in sheets:
  raise ValueError('Template harus memiliki Sheet1 (tahunan) dan Sheet2 (kuartalan)')
 for num,target in ((1,annual),(2,quarterly)):
  rows=sheets[num]
  if not rows or str(rows[0].get(1,'')).strip().lower()!='property name':
   raise ValueError(f'Sheet{num}: header Property Name tidak ditemukan')
  columns={c:period(v) for c,v in rows[0].items() if c>=2 and period(v)}
  if not columns:raise ValueError(f'Sheet{num}: periode tidak ditemukan')
  if num==1 and any(q!=4 for y,q in columns.values()):
   raise ValueError('Sheet1 harus berisi data tahunan (header Q4 tahun)')
  for row in rows[1:]:
   label=str(row.get(1) or '').strip()
   if not label:continue
   if label not in MAP:
    warnings.append(f'Sheet{num}: indikator tidak dikenal: {label}');continue
   metric,kind=MAP[label]
   for col,(year,q) in columns.items():
    cell_value=row.get(col)
    if isinstance(cell_value,str) and cell_value.strip().upper().startswith(('#REF!','#N/A','#DIV/0!','#VALUE!','#NUM!','#NAME?','#NULL!')):
     warnings.append(f'Sheet{num}: {label} {year} Q{q}: Excel error {cell_value}; dilewati')
    raw=parse_value(cell_value)
    if raw is None:continue
    key=(ticker,year,metric) if num==1 else (ticker,year,q,metric)
    if key in target:raise ValueError(f'Sheet{num}: indikator-periode duplikat {key}')
    target[key]=(raw,kind)
 return ticker,annual,quarterly,warnings

def ingest(conn,path):
 ticker,annual,quarterly,warnings=read_file(path)
 if not quarterly:raise ValueError('Sheet2 tidak memiliki data kuartalan')
 with conn:
  # Rebuild ticker only; the daily market price tables are never touched.
  conn.execute('DELETE FROM fundamental WHERE ticker=? AND publication_date IS NULL',(ticker,))
  conn.execute('DELETE FROM fundamental_annual WHERE ticker=? AND publication_date IS NULL',(ticker,))
  for (t,y,metric),(raw,kind) in sorted(annual.items()):
   basis='FY' if kind.startswith('flow_') else ('FY_SNAPSHOT' if kind.startswith('stock_') else 'FY_REPORTED_RATIO')
   conn.execute('INSERT INTO fundamental_annual(ticker,fiscal_year,metric,raw_value,unit,input_basis,source_file) VALUES(?,?,?,?,?,?,?) ON CONFLICT(ticker,fiscal_year,metric) DO UPDATE SET raw_value=excluded.raw_value,unit=excluded.unit,input_basis=excluded.input_basis,source_file=excluded.source_file,updated_at=CURRENT_TIMESTAMP',(t,y,metric,raw,kind,basis,path.name))
  for (t,y,q,metric),(raw,kind) in sorted(quarterly.items()):
   quarter=raw
   if kind.startswith('flow_') and q>1:
    prev=quarterly.get((t,y,q-1,metric))
    if prev is not None:quarter=raw-prev[0]
    else:
     quarter=None;warnings.append(f'{metric} Q{q} {y}: YTD kuartal sebelumnya tidak tersedia')
   basis='YTD' if kind.startswith('flow_') else ('SNAPSHOT' if kind.startswith('stock_') else 'REPORTED_RATIO')
   conn.execute('INSERT INTO fundamental(ticker,fiscal_year,fiscal_quarter,metric,raw_value,quarter_value,unit,input_basis,source_file,publication_date) VALUES(?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(ticker,fiscal_year,fiscal_quarter,metric) DO UPDATE SET raw_value=excluded.raw_value,quarter_value=excluded.quarter_value,unit=excluded.unit,input_basis=excluded.input_basis,source_file=excluded.source_file,updated_at=CURRENT_TIMESTAMP',(t,y,q,metric,raw,quarter,kind,basis,path.name))
  conn.execute('INSERT INTO fundamental_import_log(source_file,ticker,records_read,records_saved,warnings) VALUES(?,?,?,?,?)',(path.name,ticker,len(annual)+len(quarterly),len(annual)+len(quarterly),' | '.join(sorted(set(warnings)))))
 return ticker,len(annual),len(quarterly),warnings

def export(conn,out):
 out.mkdir(parents=True,exist_ok=True)
 cols=['ticker','fiscal_year','fiscal_quarter','metric','raw_value','quarter_value','unit','input_basis','source_file','publication_date']
 with (out/'fundamental_detail.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(cols)
  w.writerows(conn.execute('SELECT '+','.join(cols)+' FROM fundamental ORDER BY ticker,fiscal_year,fiscal_quarter,metric'))
 with (out/'fundamental_annual.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f); w.writerow(['ticker','fiscal_year','metric','raw_value','unit','input_basis','source_file','publication_date'])
  w.writerows(conn.execute('SELECT ticker,fiscal_year,metric,raw_value,unit,input_basis,source_file,publication_date FROM fundamental_annual ORDER BY ticker,fiscal_year,metric'))
 with (out/'fundamental_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(['ticker','annual_records','quarterly_records','first_year','last_year','missing_publication_dates'])
  tickers=[r[0] for r in conn.execute('SELECT ticker FROM fundamental UNION SELECT ticker FROM fundamental_annual ORDER BY ticker')]
  for t in tickers:
   na=conn.execute('SELECT COUNT(*) FROM fundamental_annual WHERE ticker=?',(t,)).fetchone()[0]
   nq=conn.execute('SELECT COUNT(*) FROM fundamental WHERE ticker=?',(t,)).fetchone()[0]
   years=conn.execute('SELECT MIN(fiscal_year),MAX(fiscal_year) FROM (SELECT fiscal_year FROM fundamental WHERE ticker=? UNION ALL SELECT fiscal_year FROM fundamental_annual WHERE ticker=?)',(t,t)).fetchone()
   nmiss=conn.execute('SELECT COUNT(*) FROM fundamental WHERE ticker=? AND publication_date IS NULL',(t,)).fetchone()[0]
   w.writerow([t,na,nq,years[0],years[1],nmiss])
 # derived TTM only when 4 valid quarters available; as-of publication dates unknown -> no backtest readiness
 with (out/'fundamental_ttm.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(['ticker','fiscal_year','fiscal_quarter','metric','ttm_value','unit','publication_verified'])
  rows=conn.execute("SELECT ticker,fiscal_year,fiscal_quarter,metric,quarter_value,unit FROM fundamental WHERE input_basis='YTD' ORDER BY ticker,fiscal_year,fiscal_quarter").fetchall()
  by={ (t,y,q,m):(v,u) for t,y,q,m,v,u in rows}
  for t,y,q,m,v,u in rows:
   periods=[]
   for delta in range(4):
    yi,qi=y,(q-delta)
    while qi<=0:qi+=4;yi-=1
    periods.append(by.get((t,yi,qi,m)))
   if all(p is not None and p[0] is not None for p in periods):
    w.writerow([t,y,q,m,round(sum(p[0] for p in periods),9),u,'NO'])

def main():
 ap=argparse.ArgumentParser(description='Impor fundamental kuartalan emiten ke SQLite yang sama dengan data perdagangan.')
 ap.add_argument('--folder',default='Data_Fundamental');ap.add_argument('--db',default='pasar_bei_prototipe.db');ap.add_argument('--output',default='output_fundamental')
 a=ap.parse_args();folder=Path(a.folder);files=sorted(p for p in folder.glob('*.xlsx') if not p.name.startswith('~$'))
 if not files:print('ERROR: Tidak ada file .xlsx pada',folder);return 1
 db=Path(a.db)
 if db.exists():
  from datetime import datetime
  backup_dir=db.parent/'Backup_Database';backup_dir.mkdir(parents=True,exist_ok=True)
  backup_path=backup_dir/(db.stem+'_backup_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
  s=sqlite3.connect(str(db));d=sqlite3.connect(str(backup_path))
  try:s.backup(d)
  finally:d.close();s.close()
  print('Database dicadangkan:',backup_path)
 conn=ensure_db(db)
 errors=0; reports=[]
 for p in files:
  try:
   ticker,n_annual,n_quarter,warnings=ingest(conn,p)
   reports.append([p.name,ticker,'OK',n_annual,n_quarter,len(set(warnings)),' | '.join(sorted(set(warnings)))])
   print(f'OK {ticker}: {n_annual} tahunan + {n_quarter} kuartalan dari {p.name}; catatan: {len(set(warnings))}')
   for item in sorted(set(warnings))[:8]:print('  CATATAN:',item)
  except Exception as e:
   errors+=1;reports.append([p.name,'','GAGAL',0,0,0,str(e)]);print(f'GAGAL {p.name}: {e}',file=sys.stderr)
 export(conn,Path(a.output))
 with (Path(a.output)/'import_validation.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(['source_file','ticker','status','annual_records_from_file','quarterly_records_from_file','warning_count','messages']);w.writerows(reports)
 n=conn.execute('SELECT count(*) FROM fundamental').fetchone()[0]
 print(f'Total fundamental di database: {n} record; CSV: {a.output}; gagal: {errors}')
 conn.close()
 return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
