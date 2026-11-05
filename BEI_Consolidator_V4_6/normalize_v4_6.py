#!/usr/bin/env python3
"""V4.6: conservative historical XBRL 2022 recovery and metadata-based context audit.
Does not modify inputs, guess multipliers, or declare facts valuation-ready.
"""
import argparse,csv,sqlite3,json,os,collections,datetime,decimal,re,sys
from pathlib import Path
D=decimal.Decimal
MAP={
 'Jumlah aset':('total_assets','balance_sheet','instant'),
 'Jumlah liabilitas':('total_liabilities','balance_sheet','instant'),
 'Jumlah ekuitas':('total_equity','balance_sheet','instant'),
 'Jumlah aset lancar':('current_assets','balance_sheet','instant'),
 'Jumlah liabilitas jangka pendek':('current_liabilities','balance_sheet','instant'),
 'Kas dan setara kas':('cash_equivalents','balance_sheet','instant'),
 'Pendapatan':('revenue','income_statement','duration'),
 'Pendapatan bersih':('revenue','income_statement','duration'),
 'Laba bruto':('gross_profit','income_statement','duration'),
 'Laba tahun berjalan':('net_income_total','income_statement','duration'),
 'Laba periode berjalan':('net_income_total','income_statement','duration'),
 'Laba sebelum pajak penghasilan':('profit_before_tax','income_statement','duration'),
 'Arus kas bersih yang diperoleh dari aktivitas operasi':('cashflow_operating','cash_flow','duration'),
 'Arus kas bersih dari aktivitas operasi':('cashflow_operating','cash_flow','duration'),
 'Arus kas bersih yang digunakan untuk aktivitas investasi':('cashflow_investing','cash_flow','duration'),
 'Arus kas bersih dari aktivitas investasi':('cashflow_investing','cash_flow','duration'),
 'Arus kas bersih yang digunakan untuk aktivitas pendanaan':('cashflow_financing','cash_flow','duration'),
 'Arus kas bersih dari aktivitas pendanaan':('cashflow_financing','cash_flow','duration'),
}
def decimal_str(v):
 try: return str(D(str(v).replace(',','').strip()))
 except (decimal.InvalidOperation,ValueError): return None
def connect_ro(p):
 if not Path(p).is_file(): raise FileNotFoundError(p)
 return sqlite3.connect('file:'+Path(p).resolve().as_posix()+'?mode=ro',uri=True)
def run(args):
 for p in (args.staging_db,args.modeling_db,args.review_db):
  if not Path(p).is_file(): raise FileNotFoundError(p)
 out=Path(args.output_db).resolve()
 if out.exists():raise FileExistsError(f'Output already exists: {out}. Rename or move it before rerunning.')
 out.parent.mkdir(parents=True,exist_ok=True)
 stage=connect_ro(args.staging_db); model=connect_ro(args.modeling_db); review=connect_ro(args.review_db)
 dest=sqlite3.connect(str(out))
 dest.executescript('''PRAGMA foreign_keys=ON;
 CREATE TABLE source_meta(source_id INTEGER PRIMARY KEY,ticker TEXT,year INT,report_period TEXT,currency TEXT,presentation_scale TEXT,start_current TEXT,end_current TEXT,start_prior TEXT,end_prior TEXT,source_filename TEXT);
 CREATE TABLE recovery_facts(id INTEGER PRIMARY KEY,source_id INT,ticker TEXT,report_year INT,metric TEXT,statement TEXT,period_kind TEXT,period_role TEXT,period_start TEXT,period_end TEXT,value_presentation TEXT,currency TEXT,presentation_scale TEXT,source_sheet TEXT,source_row INT,source_label TEXT,status TEXT,reason TEXT);
 CREATE TABLE context_resolution(fact_id INT PRIMARY KEY,source_id INT,metric TEXT,reported_context TEXT,expected_kind TEXT,period_start TEXT,period_end TEXT,status TEXT,reason TEXT);
 CREATE TABLE validation_checks(source_id INT,period_role TEXT,check_name TEXT,status TEXT,difference TEXT,detail TEXT);
 CREATE TABLE quality_gates(name TEXT PRIMARY KEY,status TEXT,description TEXT);
 ''')
 md={}
 for row in review.execute('SELECT source_id,ticker,year,report_period,currency_code,presentation_scale,start_current,end_current,start_prior,end_prior,filename FROM metadata'):
  md[row[0]]=row
  dest.execute('INSERT INTO source_meta VALUES (?,?,?,?,?,?,?,?,?,?,?)',row)
 statuses=collections.Counter(); contexts=collections.Counter(); unresolved=[]
 for source_id,metric,period_role,expected_kind,declared_kind,source_fact_id,rep_label in []:pass
 # Use V4.1 modeled facts as authoritative location of existing mappings.
 cols=[x[1] for x in model.execute('PRAGMA table_info(facts)')]
 field='context_relative' if 'context_relative' in cols else 'reporting_context'
 query=f'SELECT id,source_id,metric,reporting_context,expected_context_type,context_type FROM facts'
 for fid,sid,metric,label,expected,declared in model.execute(query):
  m=md.get(sid)
  if m is None:
   result=('MISSING_METADATA',None,None,'Missing source metadata')
  else:
   # Context labels are heuristics; only dates from metadata, no invented quarter dates.
   low=(label or '').lower()
   prior='prior' in low
   start=m[8] if prior else m[6]
   end=m[9] if prior else m[7]
   if expected=='instant':
    start=None
    if 'begin' in metric.lower() or metric=='cash_begin':
     result=('REVIEW_INSTANT_START',None,None,'Beginning balance instant date needs independent confirmation')
    else:result=('REVIEW_CONTEXT',start,end,'End date inferred from report metadata; concept context not independently verified')
   elif expected=='duration':
    result=('REVIEW_DURATION',start,end,'Date range from report metadata; context still needs source concept verification') if start and end else ('BLOCK_PERIOD',start,end,'Start/end missing')
   else:result=('BLOCK_UNKNOWN_SEMANTICS',None,None,'Unknown metric period type')
  status,ps,pe,why=result
  contexts[status]+=1
  dest.execute('INSERT INTO context_resolution VALUES (?,?,?,?,?,?,?,?,?)',(fid,sid,metric,label,expected,ps,pe,status,why))
 # 2022 legacy row previews are an extract, not an approved full normalization.
 bygroup=collections.defaultdict(dict)
 unique_sha={}
 for sid,sha in model.execute('SELECT source_id,sha256 FROM source_catalog ORDER BY source_id'):
  unique_sha.setdefault(sha,sid)
 for sid,sheet,row,label,current,prior,flag in review.execute('SELECT source_id,source_sheet,row_num,label,current_value,prior_value,review_status FROM legacy_2022_preview'):
  m=md.get(sid)
  if not m or m[2]!=2022 or not label:continue
  if label.strip() not in MAP:continue
  metric,statement,period_kind=MAP[label.strip()]
  for role,value in [('current',current),('prior',prior)]:
   dval=decimal_str(value)
   if dval is None:continue
   ps=(m[8] if role=='prior' else m[6]) if period_kind=='duration' else None
   pe=m[9] if role=='prior' else m[7]
   status='REVIEW_LEGACY_2022'
   reason='Legacy preview value uses source presentation scale; source label and units must be verified; not base-currency value'
   dest.execute('INSERT INTO recovery_facts(source_id,ticker,report_year,metric,statement,period_kind,period_role,period_start,period_end,value_presentation,currency,presentation_scale,source_sheet,source_row,source_label,status,reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(sid,m[1],m[2],metric,statement,period_kind,role,ps,pe,dval,m[4],m[5],sheet,row,label,status,reason))
   bygroup[(sid,role)][metric]=D(dval)
 # Preliminary accounting cross checks in source presentation units. Not verification of source extraction.
 for (sid,role),vals in bygroup.items():
  for name,fields,op in [('balance_sheet',('total_assets','total_liabilities','total_equity'),lambda x:x[0]-x[1]-x[2]),('gross_profit',('revenue','gross_profit'),None)]:
   if op is None:continue
   if all(f in vals for f in fields):
    diff=op([vals[f] for f in fields]);status='ARITHMETIC_PASS' if diff==0 else 'ARITHMETIC_FAIL'
    dest.execute('INSERT INTO validation_checks VALUES (?,?,?,?,?,?)',(sid,role,name,status,str(diff),'Arithmetic on 2022 preview only; independent PDF checking not performed'))
   else: dest.execute('INSERT INTO validation_checks VALUES (?,?,?,?,?,?)',(sid,role,name,'INSUFFICIENT_DATA',None,'Required labels not present in preview'))
 for name,status,description in [('database_integrity','PASS','SQLite integrity'),('legacy_2022','REVIEW','Recovered labels need external reconciliation'),('calendar_periods','REVIEW','Dates derived from filing metadata, source contexts not fully verified'),('units','BLOCK','Presentation multiplier not converted into base currency'),('bank_mapping','BLOCK','No bank-specific approval'),('valuation','BLOCK','No value approved for valuation'),('source_deletion','DISABLED','No deletion operation in this program')]:
  dest.execute('INSERT INTO quality_gates VALUES (?,?,?)',(name,status,description))
 dest.commit();integrity=dest.execute('PRAGMA integrity_check').fetchone()[0]
 summary={'version':'4.6-legacy-recovery','status':'REVIEW_NOT_VALUATION_READY','source_files':len(md),'mapped_existing_facts':sum(contexts.values()),'context_statuses':dict(contexts),'recovered_legacy_preview_facts':dest.execute('SELECT count(*) FROM recovery_facts').fetchone()[0],'legacy_source_count':dest.execute('SELECT count(DISTINCT source_id) FROM recovery_facts').fetchone()[0],'legacy_arithmetic_checks':dict(dest.execute('SELECT status,count(*) FROM validation_checks GROUP BY status')),'integrity_check':integrity,'valuation_eligible':0,'input_files_untouched':True,'output_db':str(out)}
 report=Path(args.report).resolve();report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
 csvdir=Path(args.csv_dir).resolve();csvdir.mkdir(parents=True,exist_ok=True)
 for table in ('recovery_facts','validation_checks','context_resolution'):
  cur=dest.execute('SELECT * FROM '+table)
  with (csvdir/(table+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
   writer=csv.writer(f);writer.writerow([c[0] for c in cur.description]);writer.writerows(cur)
 dest.close();stage.close();model.close();review.close()
 print(json.dumps(summary,ensure_ascii=False,indent=2))
 if integrity!='ok':sys.exit(2)
def main():
 p=argparse.ArgumentParser(description='V4.6 non-destructive legacy 2022 recovery + period audit')
 for arg in ('staging-db','modeling-db','review-db','output-db','report','csv-dir'):p.add_argument('--'+arg,required=True)
 run(p.parse_args())
if __name__=='__main__':main()
