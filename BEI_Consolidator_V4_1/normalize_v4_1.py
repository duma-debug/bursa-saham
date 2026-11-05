"""Conservative, auditable XBRL fact normalization. Read-only inputs, no cleanup."""
import argparse,csv,hashlib,json,re,sqlite3,datetime
from collections import Counter
from pathlib import Path

MAP={
 'Sales and revenue':('income_statement','revenue','duration'),
 'Total gross profit':('income_statement','gross_profit','duration'),
 'Cost of sales and revenue':('income_statement','cost_of_revenue','duration'),
 'Total profit (loss) before tax':('income_statement','profit_before_tax','duration'),
 'Total profit (loss)':('income_statement','net_income_total','duration'),
 'Profit (loss) attributable to parent entity':('income_statement','net_income_parent','duration'),
 'General and administrative expenses':('income_statement','general_administrative_expense','duration'),
 'Selling expenses':('income_statement','selling_expense','duration'),
 'Interest and finance costs':('income_statement','finance_costs','duration'),
 'Tax benefit (expenses)':('income_statement','tax_benefit_expense','duration'),
 'Basic earnings (loss) per share from continuing operations':('income_statement','eps_basic','duration'),
 'Total assets':('balance_sheet','total_assets','instant'),
 'Total equity':('balance_sheet','total_equity','instant'),
 'Total liabilities':('balance_sheet','total_liabilities','instant'),
 'Total current assets':('balance_sheet','current_assets','instant'),
 'Total non-current assets':('balance_sheet','noncurrent_assets','instant'),
 'Total current liabilities':('balance_sheet','current_liabilities','instant'),
 'Total non-current liabilities':('balance_sheet','noncurrent_liabilities','instant'),
 'Cash and cash equivalents':('balance_sheet','cash_equivalents','instant'),
 'Property, plant, and equipment':('balance_sheet','property_plant_equipment','instant'),
 'Current inventories':('balance_sheet','inventories_current','instant'),
 'Non-controlling interests':('balance_sheet','noncontrolling_interests','instant'),
 'Total net cash flows received from (used in) operating activities':('cash_flow','cashflow_operating','duration'),
 'Total net cash flows received from (used in) investing activities':('cash_flow','cashflow_investing','duration'),
 'Total net cash flows received from (used in) financing activities':('cash_flow','cashflow_financing','duration'),
 'Payments for acquisition of property, plant and equipment':('cash_flow','capex_ppe_outflow','duration'),
 'Cash and cash equivalents cash flows, end of the period':('cash_flow','cash_end','instant'),
 'Cash and cash equivalents cash flows, beginning of the period':('cash_flow','cash_begin','instant'),
}
PERIODS={'CurrentYearInstant':('current','instant'), 'PriorEndYearInstant':('prior_end','instant'), 'PriorYearInstant':('prior','instant'), 'CurrentYearDuration':('current','duration'),'PriorYearDuration':('prior','duration'),'PriorEndYearDuration':('prior_end','duration')}
BANKS=set('BBCA BBRI BBNI BMRI BBTN BNGA BNLI BBSI AGRO AGRS ARTO'.split())
RX=re.compile(r'^FinancialStatement-(\d{4})-(Tahunan|I|II|III|IV)-([A-Z0-9]{4})(?: \(\d+\))?\.(?:xlsx|xls)$',re.I)

def main():
 p=argparse.ArgumentParser(description='V4.1 conservative normalized facts (read-only inputs; never deletes files)')
 p.add_argument('--staging-db',required=True);p.add_argument('--foundation-db',required=True);p.add_argument('--output-db',required=True);p.add_argument('--report',required=True);a=p.parse_args()
 st=sqlite3.connect('file:'+Path(a.staging_db).resolve().as_posix()+'?mode=ro',uri=True)
 fd=sqlite3.connect('file:'+Path(a.foundation_db).resolve().as_posix()+'?mode=ro',uri=True)
 out=Path(a.output_db).resolve();out.parent.mkdir(parents=True,exist_ok=True)
 if out.exists():raise SystemExit('Output already exists: '+str(out)+'; move/delete only THIS generated output before rerunning.')
 db=sqlite3.connect(str(out));db.executescript('''PRAGMA journal_mode=DELETE;
 CREATE TABLE run_info(key TEXT PRIMARY KEY,value TEXT);
 CREATE TABLE source_catalog(source_id INTEGER PRIMARY KEY,filename TEXT,sha256 TEXT,year INTEGER,report_period TEXT,ticker TEXT,duplicate_of INTEGER,source_status TEXT);
 CREATE TABLE metric_dictionary(metric TEXT PRIMARY KEY,statement TEXT,expected_period_type TEXT,original_concept TEXT);
 CREATE TABLE facts(id INTEGER PRIMARY KEY,source_id INTEGER,ticker TEXT,report_year INTEGER,report_period TEXT,statement TEXT,metric TEXT,concept TEXT,reporting_context TEXT,context_relative TEXT,context_type TEXT,expected_context_type TEXT,raw_value TEXT,source_sheet TEXT,source_cell TEXT,staging_fact_id INTEGER,check_status TEXT,review_reason TEXT,currency TEXT,unit_multiplier TEXT,normalised_value TEXT,valuation_eligible INTEGER NOT NULL DEFAULT 0);
 CREATE INDEX facts_lookup ON facts(ticker,report_year,report_period,metric,context_relative);
 CREATE TABLE findings(source_id INTEGER,ticker TEXT,code TEXT,detail TEXT);
 CREATE TABLE pdf_references(pdf_id INTEGER,filename TEXT,ticker TEXT,report_year INTEGER,report_period TEXT,link_status TEXT,source_id INTEGER,sha256 TEXT);
 ''')
 db.executemany('INSERT INTO metric_dictionary VALUES(?,?,?,?)',[(v[1],v[0],v[2],k) for k,v in MAP.items()])
 source=st.execute('SELECT id, filename,sha256,year,period,ticker FROM source_files').fetchall()
 seen={};valid={};stats=Counter()
 for sid,fn,h,y,per,ticker in source:
  m=RX.match(fn)
  if (not ticker or not y or not per) and m: y,per,ticker=int(m.group(1)),m.group(2),m.group(3).upper()
  dupe=seen.get(h);status='DUPLICATE' if dupe else ('OK' if ticker and y and per else 'METADATA_REVIEW')
  if not dupe:seen[h]=sid
  valid[sid]=(ticker,y,per,dupe,status)
  db.execute('INSERT INTO source_catalog VALUES(?,?,?,?,?,?,?,?)',(sid,fn,h,y,per,ticker,dupe,status))
  stats['sources']+=1;stats['duplicates']+=bool(dupe)
  if not (ticker and y and per):stats['metadata_review']+=1
 st.row_factory=sqlite3.Row
 sql='''SELECT id,file_id,sheet_name,concept_en,period_label,value_text,source_cell FROM financial_facts ORDER BY id'''
 mapped_source=set(); rejected=Counter()
 batch=[]
 for r in st.execute(sql):
  sid=r['file_id']; ticker,y,per,dupe,status=valid[sid];concept=r['concept_en']
  if concept not in MAP:continue
  if dupe:continue
  if not ticker or not y or not per: continue
  stmt,metric,expected=MAP[concept]
  relative,ptype=PERIODS.get(r['period_label'],('unknown','unknown'))
  raw=(r['value_text'] or '').strip().replace(',','')
  try:float(raw); numeric=True
  except (ValueError,OverflowError): numeric=False
  reasons=[]
  if ptype!=expected:reasons.append('CONTEXT_TYPE_MISMATCH')
  if ptype=='unknown':reasons.append('UNKNOWN_CONTEXT')
  if ticker in BANKS:reasons.append('SECTOR_MAPPING_REVIEW')
  if not numeric:reasons.append('NON_NUMERIC')
  if relative!='current':reasons.append('COMPARATIVE_CONTEXT')
  # no reported currency/scale verification; never grant valuation eligibility
  reasons.append('UNIT_CURRENCY_NOT_VERIFIED')
  if ptype=='duration':reasons.append('YTD_QUARTER_UNVERIFIED')
  check='REVIEW' if reasons else 'PASS'
  batch.append((sid,ticker,y,per,stmt,metric,concept,r['period_label'],relative,ptype,expected,raw,r['sheet_name'],r['source_cell'],r['id'],check,';'.join(reasons),None,None,None,0))
  mapped_source.add(sid);stats['facts']+=1
  if 'CONTEXT_TYPE_MISMATCH' in reasons:stats['context_type_mismatch']+=1
  if len(batch)>=5000:
   db.executemany('INSERT INTO facts(source_id,ticker,report_year,report_period,statement,metric,concept,reporting_context,context_relative,context_type,expected_context_type,raw_value,source_sheet,source_cell,staging_fact_id,check_status,review_reason,currency,unit_multiplier,normalised_value,valuation_eligible) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch);batch=[]
 if batch:db.executemany('INSERT INTO facts(source_id,ticker,report_year,report_period,statement,metric,concept,reporting_context,context_relative,context_type,expected_context_type,raw_value,source_sheet,source_cell,staging_fact_id,check_status,review_reason,currency,unit_multiplier,normalised_value,valuation_eligible) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch)
 for sid,(ticker,y,per,dupe,status) in valid.items():
  if dupe:continue
  if sid not in mapped_source:
   c=st.execute('SELECT count(*) FROM financial_facts WHERE file_id=?',(sid,)).fetchone()[0]
   code='LEGACY_OR_UNEXTRACTED' if c==0 else 'NO_WHITELISTED_METRICS'
   db.execute('INSERT INTO findings VALUES (?,?,?,?)',(sid,ticker,code,f'financial_facts={c}; inspect raw staging'))
   stats[code]+=1
 for row in fd.execute('select pdf_id,filename,ticker,report_year,report_period,link_status,source_id,sha256 from pdf_sources'):
  db.execute('INSERT INTO pdf_references VALUES(?,?,?,?,?,?,?,?)',row)
 for k,v in {'mode':'CONSERVATIVE_REVIEW_ONLY','source_staging':str(Path(a.staging_db).resolve()),'source_foundation':str(Path(a.foundation_db).resolve()),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'version':'4.1','source_deletion':'DISABLED'}.items():db.execute('INSERT INTO run_info VALUES(?,?)',(k,v))
 db.commit()
 checks={'integrity_check':db.execute('PRAGMA integrity_check').fetchone()[0], 'facts':db.execute('select count(*) from facts').fetchone()[0],'valuation_eligible':db.execute('select count(*) from facts where valuation_eligible=1').fetchone()[0]}
 report={'version':'4.1','status':'REVIEW_ONLY','stats':dict(stats),'checks':checks,'facts_by_statement':dict(db.execute('select statement,count(*) from facts group by statement').fetchall()),'facts_by_metric':dict(db.execute('select metric,count(*) from facts group by metric').fetchall()),'quality_gates':{'raw_traceability':'PASS','sector_specific':'REVIEW','unit_currency':'BLOCK','duration_context':'BLOCK','valuation':'BLOCK','delete_original':'DISABLED'},'note':'Period labels are XBRL context names, not verified calendar dates. Do not compute TTM/FCF or valuation from this output without review.'}
 Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(report,indent=2),encoding='utf-8')
 db.close();st.close();fd.close();print(json.dumps({'status':'OK','output_db':str(out),'report':a.report,**checks,'files':stats['sources']},indent=2))
if __name__=='__main__':main()
