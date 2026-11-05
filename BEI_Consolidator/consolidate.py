#!/usr/bin/env python3
"""IDX financial XBRL Excel -> SQLite. Read-only ingest, verified cleanup optional.
Standard library only. Preserves cell values/formulas (not workbook formatting).
"""
import argparse, os, re, json, sqlite3, hashlib, zipfile, shutil, datetime, xml.etree.ElementTree as ET
from pathlib import Path
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PKG='{http://schemas.openxmlformats.org/package/2006/relationships}'
PAT=re.compile(r'^FinancialStatement-(\d{4})-(Tahunan|I|II|III|IV)-([A-Za-z0-9]+)\.xlsx$',re.I)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def parse_file(path):
 with zipfile.ZipFile(path) as z:
  ss=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   root=ET.fromstring(z.read('xl/sharedStrings.xml'))
   ss=[''.join(t.text or '' for t in si.iter(NS+'t')) for si in root]
  wb=ET.fromstring(z.read('xl/workbook.xml'))
  rel=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
  targets={x.get('Id'):x.get('Target') for x in rel}
  for s in wb.findall('.//'+NS+'sheet'):
   target=targets.get(s.get(REL+'id'),'')
   if target.startswith('/'):target=target.lstrip('/')
   elif not target.startswith('xl/'):target='xl/'+target
   if target not in z.namelist():continue
   root=ET.fromstring(z.read(target))
   rows=[]
   for row in root.iter(NS+'row'):
    cells=[]
    for c in row.findall(NS+'c'):
     v=c.find(NS+'v'); fx=c.find(NS+'f'); inline=c.find(NS+'is')
     value=v.text if v is not None else None
     if c.get('t')=='s' and value is not None:
      try:value=ss[int(value)]
      except (ValueError,IndexError):pass
     elif c.get('t')=='inlineStr' and inline is not None:
      value=''.join(t.text or '' for t in inline.iter(NS+'t'))
     if value is None and fx is None:continue
     cells.append((c.get('r'),value,c.get('t','n'),fx.text if fx is not None else None))
    if cells:rows.append((int(row.get('r')),cells))
   yield s.get('name'),rows

def create(db):
 c=sqlite3.connect(db);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA foreign_keys=ON')
 c.executescript('''CREATE TABLE IF NOT EXISTS source_files(id INTEGER PRIMARY KEY,path TEXT UNIQUE NOT NULL, filename TEXT NOT NULL, sha256 TEXT NOT NULL, year INTEGER, period TEXT, ticker TEXT, sheet_count INTEGER NOT NULL, cell_count INTEGER NOT NULL, imported_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS sheets(id INTEGER PRIMARY KEY,file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,name TEXT NOT NULL, row_count INTEGER NOT NULL,cell_count INTEGER NOT NULL,UNIQUE(file_id,name));
 CREATE TABLE IF NOT EXISTS cells(sheet_id INTEGER NOT NULL REFERENCES sheets(id) ON DELETE CASCADE,address TEXT NOT NULL,value TEXT,cell_type TEXT,formula TEXT,PRIMARY KEY(sheet_id,address)) WITHOUT ROWID;
 CREATE TABLE IF NOT EXISTS financial_facts(id INTEGER PRIMARY KEY,file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,sheet_name TEXT NOT NULL,concept_en TEXT NOT NULL,concept_id TEXT,statement_row INTEGER NOT NULL,period_label TEXT NOT NULL,value_text TEXT NOT NULL,source_cell TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS idx_sources_ticker_period ON source_files(ticker,year,period);
 CREATE INDEX IF NOT EXISTS idx_facts_by_concept ON financial_facts(file_id,sheet_name,concept_en,period_label);''')
 return c

def convert_number(v):
 if v is None:return False
 try:float(str(v).replace(',',''));return True
 except ValueError:return False

def ingest(c,path):
 m=PAT.match(path.name); year=int(m.group(1)) if m else None; period=m.group(2) if m else None; ticker=m.group(3).upper() if m else None
 digest=sha(path);existing=c.execute('SELECT id,sha256,cell_count FROM source_files WHERE path=?',(str(path.resolve()),)).fetchone()
 if existing and existing[1]==digest:return 'unchanged',existing[2],0
 if existing:raise RuntimeError('SOURCE_CHANGED: Existing path has different hash; no overwrite: '+str(path))
 stats=[];all_sheets=list(parse_file(path))
 with c:
  cur=c.execute('INSERT INTO source_files(path,filename,sha256,year,period,ticker,sheet_count,cell_count,imported_at) VALUES(?,?,?,?,?,?,?,?,?)',(str(path.resolve()),path.name,digest,year,period,ticker,len(all_sheets),sum(len(cells) for _,rs in all_sheets for _,cells in rs),datetime.datetime.now(datetime.timezone.utc).isoformat()))
  fid=cur.lastrowid;fact_count=0
  for name,rows in all_sheets:
   cur=c.execute('INSERT INTO sheets(file_id,name,row_count,cell_count) VALUES(?,?,?,?)',(fid,name,len(rows),sum(len(cells) for _,cells in rows)))
   sid=cur.lastrowid
   c.executemany('INSERT INTO cells(sheet_id,address,value,cell_type,formula) VALUES(?,?,?,?,?)',((sid,addr,val,typ,fx) for _,rr in rows for addr,val,typ,fx in rr))
   # XBRL tables: row 4 has explicit period column labels, rightmost English concept column.
   row4=next((rr for rn,rr in rows if rn==4),[])
   period_cols={re.match(r'[A-Z]+',a).group():v for a,v,_,_ in row4 if v and ('Year' in str(v) or 'Quarter' in str(v) or 'Instant' in str(v) or 'Duration' in str(v))}
   facts=[]
   if name not in ('Context','InlineXBRL'):
    for rowno,rr in rows:
     if rowno<6:continue
     vals=[(re.match(r'[A-Z]+',a).group(),a,v,t) for a,v,t,_ in rr if a]
     labels=[(col,v) for col,a,v,t in vals if isinstance(v,str) and not convert_number(v) and col not in period_cols and col!='A']
     if not labels:continue
     concept=labels[-1][1]
     if not concept or len(concept)>400:continue
     for col,addr,v,t in vals:
      if col in period_cols and convert_number(v):facts.append((fid,name,concept,None,rowno,str(period_cols[col]),str(v),addr))
   if facts:c.executemany('INSERT INTO financial_facts(file_id,sheet_name,concept_en,concept_id,statement_row,period_label,value_text,source_cell) VALUES(?,?,?,?,?,?,?,?)',facts)
   fact_count+=len(facts)
 return 'imported',sum(len(rr) for _,rows in all_sheets for _,rr in rows),fact_count

def verify(c,path):
 p=str(path.resolve());rec=c.execute('SELECT id,sha256,sheet_count,cell_count FROM source_files WHERE path=?',(p,)).fetchone()
 if not rec:return {'file':path.name,'status':'NOT_IMPORTED'}
 fid,checksum,ns,nc=rec
 if not path.exists():return {'file':path.name,'status':'MISSING_SOURCE'}
 if checksum!=sha(path):return {'file':path.name,'status':'HASH_MISMATCH'}
 try:
  expected_sheets=0;expected_cells=0;differences=0
  for name,rows in parse_file(path):
   expected_sheets+=1
   sheet=c.execute('SELECT id,row_count,cell_count FROM sheets WHERE file_id=? AND name=?',(fid,name)).fetchone()
   if sheet is None:differences+=1;continue
   expected_cells+=sum(len(rr) for _,rr in rows)
   if sheet[1]!=len(rows) or sheet[2]!=sum(len(rr) for _,rr in rows):differences+=1
   for _,rr in rows:
    for addr,val,typ,fx in rr:
     found=c.execute('SELECT value,cell_type,formula FROM cells WHERE sheet_id=? AND address=?',(sheet[0],addr)).fetchone()
     if found != (val,typ,fx):differences+=1
  status='PASS' if differences==0 and expected_sheets==ns and expected_cells==nc else 'FAIL'
  return {'file':path.name,'status':status,'sheets':expected_sheets,'cells':expected_cells,'mismatches':differences,'sha256':checksum}
 except Exception as ex:return {'file':path.name,'status':'ERROR','details':str(ex)}

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['import','validate','cleanup']);p.add_argument('--source',required=True);p.add_argument('--db',required=True);p.add_argument('--report',default='validation_report.json');p.add_argument('--backup');p.add_argument('--confirm-delete',action='store_true');a=p.parse_args()
 src=Path(a.source).resolve();db=Path(a.db).resolve();db.parent.mkdir(parents=True,exist_ok=True)
 if not src.is_dir():p.error('Source must be an existing directory')
 files=sorted(src.rglob('*.xlsx'))
 if db.is_relative_to(src):p.error('Database must be outside source folder')
 conn=create(db)
 if a.command=='import':
  for f in files:
   try:print(f.name,*ingest(conn,f),flush=True)
   except Exception as ex:print('ERROR',f.name,str(ex),flush=True)
 else:
  results=[verify(conn,f) for f in files]
  report={'database':str(db),'source_dir':str(src),'files':results,'passed':sum(r['status']=='PASS' for r in results),'failed':sum(r['status']!='PASS' for r in results)}
  Path(a.report).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
  print('Validation:',report['passed'],'PASS;',report['failed'],'not PASS; report:',a.report)
  if a.command=='cleanup':
   if not a.confirm_delete or not a.backup:p.error('cleanup requires --confirm-delete and --backup')
   backup=Path(a.backup).resolve();
   if backup==src or backup.is_relative_to(src):p.error('Backup must be outside the source directory')
   if backup.is_relative_to(db.parent) and backup==db.parent:p.error('Use a dedicated backup directory')
   for r in results:
    if r['status']!='PASS':continue
    f=next((x for x in files if x.name==r['file']),None)
    if f is None:continue
    destination=backup/f.relative_to(src);destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists() and sha(destination)!=sha(f):print('SKIPPED existing conflicting backup',f);continue
    if not destination.exists():shutil.copy2(f,destination)
    if sha(destination)!=sha(f):print('SKIPPED backup failed',f);continue
    if verify(conn,f)['status']!='PASS':print('SKIPPED changed source',f);continue
    f.unlink();print('BACKED_UP_AND_DELETED',f)
 conn.close()
if __name__=='__main__':main()
