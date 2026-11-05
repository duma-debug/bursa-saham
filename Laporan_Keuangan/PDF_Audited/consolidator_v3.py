#!/usr/bin/env python3
"""Consolidator V3 foundation: V1 read-only; V3 staged, provisional facts and PDF catalog.
No delete, no promotion of unverified facts to valuation-ready status.
"""
import argparse, collections, datetime, hashlib, json, re, sqlite3, sys
from pathlib import Path
from mapping_engine_v2 import build

def sha256(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda: stream.read(1<<20),b''):h.update(block)
 return h.hexdigest()

def parse_pdf_name(filename):
 name=Path(filename).stem.upper()
 tokens=re.split(r'[^A-Z0-9]+',name)
 years=[int(t) for t in tokens if re.fullmatch(r'20\d{2}',t)]
 tickers=[t for t in tokens if re.fullmatch(r'[A-Z]{4}',t) and t not in ('TAHU','YEAR','FULL')]
 ticker=tickers[0] if tickers else None
 year=years[0] if years else None
 annual=bool({'TAHUNAN','ANNUAL','FY'} & set(tokens))
 quarters=[t for t in tokens if t in ('Q1','Q2','Q3','Q4')]
 return ticker,year,('Tahunan' if annual else quarters[0] if quarters else None)

def main():
 p=argparse.ArgumentParser(description='BEI V3: independent fundamental staging and PDF source catalog, no cleanup')
 p.add_argument('--input-db',required=True);p.add_argument('--output-db',required=True)
 p.add_argument('--excel-dir',required=False);p.add_argument('--pdf-dir',required=True);p.add_argument('--report',required=True)
 a=p.parse_args();inp=Path(a.input_db).resolve();out=Path(a.output_db).resolve();pdf=Path(a.pdf_dir).resolve();report=Path(a.report).resolve()
 if not inp.is_file():p.error('Missing V1 staging DB: '+str(inp))
 if not pdf.is_dir():p.error('Missing PDF folder: '+str(pdf))
 if inp==out:p.error('Refusing to overwrite input database')
 if out.exists():p.error('Output database exists. Move it or choose a NEW --output-db (protects previous results).')
 out.parent.mkdir(parents=True,exist_ok=True)
 try:
  temp_report=report.with_name(report.stem+'.mapping_tmp.json')
  base=build(inp,out,temp_report)
  con=sqlite3.connect(out)
  con.execute('PRAGMA foreign_keys=ON')
  con.executescript('''
    CREATE TABLE pdf_sources (
      pdf_id INTEGER PRIMARY KEY,filename TEXT NOT NULL,absolute_path TEXT NOT NULL UNIQUE,
      sha256 TEXT NOT NULL,size_bytes INTEGER NOT NULL,ticker TEXT,report_year INTEGER,
      report_period TEXT,link_status TEXT NOT NULL,source_id INTEGER,
      FOREIGN KEY(source_id) REFERENCES source_inventory(source_id));
    CREATE INDEX ix_pdf_link ON pdf_sources(ticker,report_year,report_period);
    CREATE TABLE data_dictionary(metric TEXT PRIMARY KEY,unit_policy TEXT NOT NULL,description TEXT NOT NULL);
    CREATE TABLE quality_gate(gate TEXT PRIMARY KEY,status TEXT NOT NULL,reason TEXT NOT NULL);
    CREATE VIEW valuation_eligible_facts AS SELECT * FROM normalized_facts WHERE review_status='APPROVED' AND unit_status='VERIFIED';
  ''')
  con.executemany('INSERT INTO data_dictionary VALUES(?,?,?)',[
   ('revenue','reported currency; scale requires verification','Sales or operating revenue; banks require separate sector logic'),
   ('net_income','reported currency; scale requires verification','Consolidated profit after tax'),
   ('net_income_parent','reported currency; scale requires verification','Attributable to parent owners'),
   ('total_assets','reported currency; scale requires verification','Total assets at period end'),
   ('total_liabilities','reported currency; scale requires verification','Total liabilities at period end'),
   ('total_equity','reported currency; scale requires verification','Total equity including minority interest'),
   ('operating_cash_flow','reported currency; scale requires verification','Cash from operations; generally cumulative YTD')])
  sources=con.execute('SELECT source_id,ticker,year,period FROM source_inventory WHERE duplicate_of IS NULL').fetchall()
  bykey=collections.defaultdict(list)
  for sid,ticker,year,period in sources:bykey[(ticker,year,period)].append(sid)
  link_stats=collections.Counter();pdf_rows=0
  for f in sorted(pdf.rglob('*')):
   if not f.is_file() or f.suffix.lower()!='.pdf':continue
   ticker,year,period=parse_pdf_name(f.name)
   candidates=bykey.get((ticker,year,period),[]) if period else []
   status='MATCHED_METADATA' if len(candidates)==1 else 'AMBIGUOUS' if len(candidates)>1 else 'UNMATCHED'
   con.execute('INSERT INTO pdf_sources(filename,absolute_path,sha256,size_bytes,ticker,report_year,report_period,link_status,source_id) VALUES(?,?,?,?,?,?,?,?,?)',
    (f.name,str(f),sha256(f),f.stat().st_size,ticker,year,period,status,candidates[0] if len(candidates)==1 else None))
   pdf_rows+=1;link_stats[status]+=1
  gates=[
   ('staging_import','PASS','Input staging DB read-only; file/cell source preserved there'),
   ('metric_mapping','REVIEW','Exact concept-label matching only; unmapped facts retained in original staging'),
   ('unit_currency','BLOCK','Units and currency have not been confirmed from source metadata'),
   ('quarterly_ttm','BLOCK','Quarter vs YTD and instant-vs-duration not fully verified'),
   ('bank_sector','BLOCK','Bank-specific statements and metrics not yet normalized'),
   ('pdf_detail_extract','NOT_STARTED','PDFs indexed and hashed only; notes not extracted'),
   ('valuation_ready','BLOCK','No facts approved until all relevant accounting checks pass'),
   ('source_deletion','DISABLED','Program does not contain deletion of source Excel or PDF')]
  con.executemany('INSERT INTO quality_gate VALUES(?,?,?)',gates)
  con.commit()
  approved=con.execute('SELECT COUNT(*) FROM valuation_eligible_facts').fetchone()[0]
  con.close()
  base.update({'version':'3.0-foundation','pdf_documents_indexed':pdf_rows,'pdf_link_status':dict(link_stats),
      'valuation_eligible_fact_rows':approved,'quality_gates':{x[0]:x[1] for x in gates},
      'source_excel_deleted':0,'source_pdf_deleted':0,
      'notes':'MATCHED_METADATA is filename association only, NOT a PDF-vs-XBRL numerical reconciliation. Monetary units, accounting scopes and period semantics remain unverified.'})
  report.parent.mkdir(parents=True,exist_ok=True)
  report.write_text(json.dumps(base,indent=2,ensure_ascii=False),encoding='utf-8')
  temp_report.unlink(missing_ok=True)
  print(json.dumps(base,indent=2,ensure_ascii=False))
 except Exception as exc:
  print('ERROR:',str(exc),file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
