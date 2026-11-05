"""Recover 2021/2022 comparative columns from legacy IDX XBRL 2022 sheets.

Read-only staging; modifies only the add-on table legacy_xbrl_facts inside master
(after creating master backup). The rest of the master schema is unchanged.
No source Excel/PDF deletion. Compatible with Python 3.10+ stdlib.
"""
import argparse, sqlite3, shutil, json, re, datetime, sys
from pathlib import Path

# These are EXACT English accounting labels from historical IDX sheet column D.
# Unknown labels must be reviewed, not guessed.
EXACT={
 'cash and cash equivalents':('balance_sheet','cash_equivalents'),
 'total current assets':('balance_sheet','current_assets'),
 'current inventories':('balance_sheet','inventories_current'),
 'total non-current assets':('balance_sheet','noncurrent_assets'),
 'property, plant, and equipment':('balance_sheet','property_plant_equipment'),
 'total assets':('balance_sheet','total_assets'),
 'total current liabilities':('balance_sheet','current_liabilities'),
 'total non-current liabilities':('balance_sheet','noncurrent_liabilities'),
 'total liabilities':('balance_sheet','total_liabilities'),
 'non-controlling interests':('balance_sheet','noncontrolling_interests'),
 'total equity':('balance_sheet','total_equity'),
 'sales and revenue':('income_statement','revenue'),
 'cost of sales and revenue':('income_statement','cost_of_revenue'),
 'total gross profit':('income_statement','gross_profit'),
 'selling expenses':('income_statement','selling_expense'),
 'general and administrative expenses':('income_statement','general_administrative_expense'),
 'interest and finance costs':('income_statement','finance_costs'),
 'total profit (loss) before tax':('income_statement','profit_before_tax'),
 'tax benefit (expenses)':('income_statement','tax_benefit_expense'),
 'total profit (loss)':('income_statement','net_income_total'),
 'profit (loss) attributable to parent entity':('income_statement','net_income_parent'),
 'basic earnings (loss) per share from continuing operations':('income_statement','eps_basic'),
 'total net cash flows received from (used in) operating activities':('cash_flow','cashflow_operating'),
 'total net cash flows received from (used in) investing activities':('cash_flow','cashflow_investing'),
 'total net cash flows received from (used in) financing activities':('cash_flow','cashflow_financing'),
 'payments for acquisition of property, plant and equipment':('cash_flow','capex_ppe_outflow'),
 'cash and cash equivalents cash flows, beginning of the period':('cash_flow','cash_begin'),
 'cash and cash equivalents cash flows, end of the period':('cash_flow','cash_end'),
}
# Accounting contexts: balance amounts are point-in-time, P&L/cash flows duration.
BS={'1210000','1220000','2210000'}
IS={'1311000','1321000','1322000','2311000'}
CF={'1510000','2510000'}

def clean_num(v):
 if v is None or str(v).strip()=='':return None
 try:
  x=float(str(v).replace(',','').strip())
  if not (-1e100<x<1e100):return None
  return str(v).strip()
 except ValueError:return None

def fetch_sheet(conn,file_id,name):
 row=conn.execute('SELECT id FROM sheets WHERE file_id=? AND name=?',(file_id,name)).fetchone()
 if not row:return {}
 out={}
 for a,v in conn.execute('SELECT address,value FROM cells WHERE sheet_id=?',(row[0],)):
  m=re.fullmatch(r'([ABCD])(\d+)',a)
  if m:out.setdefault(int(m[2]),{})[m[1]]=v
 return out

def restore(staging,master,report,force=False):
 staging=Path(staging);master=Path(master);report=Path(report)
 if not staging.is_file() or not master.is_file():raise FileNotFoundError('Database staging atau master tidak ditemukan')
 backup=master.with_suffix(master.suffix+'.before_v24.bak')
 if not backup.exists():
  with sqlite3.connect(f'file:{master.as_posix()}?mode=ro',uri=True) as src, sqlite3.connect(backup) as dst:src.backup(dst)
 s=sqlite3.connect(f'file:{staging.as_posix()}?mode=ro',uri=True)
 m=sqlite3.connect(master)
 try:
  master_sources={int(x[0]):x for x in m.execute('select source_id,sha256,ticker from source_catalog')}
  data=[]; skipped=[]; covered=set(); raw_labels=set()
  for fid,fn,ticker,year,period,hash_ in s.execute("SELECT id,filename,ticker,year,period,sha256 FROM source_files WHERE year=2022 AND lower(period) IN ('tahunan','annual','fy') ORDER BY id"):
   rec=master_sources.get(fid)
   if not rec or rec[1]!=hash_:
    skipped.append({'source':fn,'reason':'SOURCE_HASH_OR_ID_MISMATCH'});continue
   meta=fetch_sheet(s,fid,'1000000')
   cur_year=meta.get(22,{}).get('B','')[:4]; prev_year=meta.get(25,{}).get('B','')[:4]
   if str(cur_year)!='2022' or str(prev_year)!='2021':
    skipped.append({'source':fn,'reason':'PERIOD_METADATA_NOT_CONFIRMED'});continue
   # Legacy 2022 uses B=current, C=prior, English account label D.
   for sn in BS|IS|CF:
    rows=fetch_sheet(s,fid,sn)
    if not rows:continue
    for row,d in rows.items():
     label=(d.get('D') or '').strip()
     key=re.sub(r'\s+',' ',label).lower().strip()
     pair=EXACT.get(key)
     if pair is None:continue
     statement,metric=pair
     if (statement=='balance_sheet' and sn not in BS) or (statement=='income_statement' and sn not in IS) or (statement=='cash_flow' and sn not in CF):continue
     raw_labels.add(label)
     for col,role,target in [('B','CurrentYear',2022),('C','PriorYear',2021)]:
      raw=clean_num(d.get(col))
      if raw is None:continue
      context=role+('Instant' if statement=='balance_sheet' else 'Duration')
      # raw values are in source presentation scale, not harmonized with later filings
      data.append((fid,ticker,2022,'Tahunan',statement,metric,raw,context,sn,f'{col}{row}',label,'REVIEW_LEGACY_SOURCE_SCALE'))
      covered.add((fid,target))
  # Detect mappings colliding within a report/context; do not silently prefer one.
  keys={}; collisions=[]
  for r in data:
   k=(r[0],r[5],r[7])
   if k in keys:
    collisions.append({'source_id':r[0],'metric':r[5],'context':r[7],'sources':[keys[k][9],r[9]]})
   else:keys[k]=r
  conflicted={(x['source_id'],x['metric'],x['context']) for x in collisions}
  clean=[r for k,r in keys.items() if k not in conflicted]
  with m:
   m.execute('''CREATE TABLE IF NOT EXISTS legacy_xbrl_facts (
     source_id INTEGER NOT NULL, ticker TEXT, report_year INTEGER, report_period TEXT,
     statement TEXT, metric TEXT, raw_value TEXT, reporting_context TEXT,
     source_sheet TEXT, source_cell TEXT, source_label TEXT, quality_status TEXT,
     PRIMARY KEY (source_id, metric, reporting_context))''')
   m.execute('DELETE FROM legacy_xbrl_facts WHERE report_year=2022')
   m.executemany('INSERT INTO legacy_xbrl_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',clean)
   m.execute('CREATE INDEX IF NOT EXISTS idx_legacy_xbrl_ticker ON legacy_xbrl_facts(ticker,report_year)')
  integrity=m.execute('PRAGMA integrity_check').fetchone()[0]
  out={'status':'OK' if integrity=='ok' else 'FAIL','source_2022_total':s.execute('select count(*) from source_files where year=2022').fetchone()[0],
   'legacy_facts_inserted':len(clean),'files_with_both_periods':len({sid for sid,y in covered if (sid,2022) in covered and (sid,2021) in covered}),
   'fy2021_rows':sum(r[7].startswith('Prior') for r in clean),'fy2022_rows':sum(r[7].startswith('Current') for r in clean),
   'aali_2021':{},'collisions':collisions[:50],'skipped_files':skipped,'master_backup':str(backup),
   'master_db':str(master),'integrity_check':integrity,'quality':'REVIEW - raw source presentation; not valuation ready','original_excel_deleted':0}
  for met,raw,ctx in m.execute("SELECT metric,raw_value,reporting_context FROM legacy_xbrl_facts WHERE ticker='AALI' AND reporting_context LIKE 'Prior%' ORDER BY metric"):
   out['aali_2021'][met]=raw
  report.parent.mkdir(parents=True,exist_ok=True)
  report.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
  return out
 finally:s.close();m.close()

if __name__=='__main__':
 p=argparse.ArgumentParser(description='Recover FY2021 comparatives from archived 2022 XBRL. No source deletion.')
 p.add_argument('--base',default=r'C:\Analisis_Saham_BEI')
 a=p.parse_args();base=Path(a.base)
 try:
  result=restore(base/'financial_production.db',base/'BEI_Master_Output'/'BEI_Financial_Master.db',base/'BEI_Master_Output'/'legacy_2022_recovery_report.json')
  print(json.dumps(result,indent=2,ensure_ascii=False))
 except Exception as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
