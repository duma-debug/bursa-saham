#!/usr/bin/env python3
"""BEI Consolidator V2: non-destructive normalized facts and audit from V1 SQLite.
Only Python standard library. Never deletes source Excel. Never writes to V1 DB.
"""
import argparse, collections, datetime, hashlib, json, re, sqlite3, sys
from pathlib import Path

# Conservative taxonomy. Exact label matching only; unmatched concepts remain in staging.
MAP = {
 'cash_and_equivalents':('balance_sheet',{'cash and cash equivalents'}),
 'total_assets':('balance_sheet',{'total assets','assets'}),
 'total_liabilities':('balance_sheet',{'total liabilities','liabilities'}),
 'total_equity':('balance_sheet',{'total equity','equity','total equity attributable to owners of parent entity and non-controlling interests'}),
 'current_assets':('balance_sheet',{'total current assets','current assets'}),
 'current_liabilities':('balance_sheet',{'total current liabilities','current liabilities'}),
 'revenue':('income_statement',{'revenue','revenues','sales and revenue','sales and revenues','net revenue','net revenues','net sales','sales'}),
 'gross_profit':('income_statement',{'gross profit'}),
 'operating_profit':('income_statement',{'profit (loss) from operations','profit (loss) from operation','operating profit (loss)','operating profit','profit from operations'}),
 'profit_before_tax':('income_statement',{'profit (loss) before tax','profit (loss) before income tax','profit before tax'}),
 'net_income':('income_statement',{'profit (loss)','profit (loss) for the year','profit (loss) for the period','net profit (loss)','net income','profit for the year','profit for the period'}),
 'net_income_parent':('income_statement',{'profit (loss) attributable to owners of parent entity','profit (loss) attributable to owners of the parent entity'}),
 'operating_cash_flow':('cash_flow',{'net cash flows from (used in) operating activities','net cash provided by (used in) operating activities','net cash flows provided by (used in) operating activities'}),
 'investing_cash_flow':('cash_flow',{'net cash flows from (used in) investing activities','net cash provided by (used in) investing activities','net cash flows provided by (used in) investing activities'}),
 'financing_cash_flow':('cash_flow',{'net cash flows from (used in) financing activities','net cash provided by (used in) financing activities','net cash flows provided by (used in) financing activities'}),
}
LOOKUP={label:(statement,metric) for metric,(statement,labels) in MAP.items() for label in labels}
def clean(s):return re.sub(r'\s+',' ',str(s or '').strip().casefold())
def classify_period(label):
 s=clean(label)
 if 'instant' in s:return 'instant'
 if 'duration' in s or 'year' in s or 'quarter' in s:return 'duration_or_ytd_unverified'
 return 'unknown'
def metric_value(raw):
 s=str(raw).strip().replace(',','')
 if not re.fullmatch(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',s):return None
 return s

def prepare(out):
 c=sqlite3.connect(out);c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL')
 c.executescript('''CREATE TABLE IF NOT EXISTS source_inventory(source_id INTEGER PRIMARY KEY,filename TEXT NOT NULL,source_path TEXT,sha256 TEXT,year INTEGER,period TEXT,ticker TEXT,cell_count INTEGER,sheet_count INTEGER,duplicate_of INTEGER);
 CREATE TABLE IF NOT EXISTS normalized_facts(id INTEGER PRIMARY KEY,source_id INTEGER NOT NULL REFERENCES source_inventory(source_id),ticker TEXT NOT NULL,report_year INTEGER NOT NULL,report_period TEXT NOT NULL,statement TEXT NOT NULL,metric TEXT NOT NULL,period_label TEXT NOT NULL,period_type TEXT NOT NULL,original_label TEXT NOT NULL,value_text TEXT NOT NULL,source_sheet TEXT NOT NULL,source_cell TEXT NOT NULL,source_row INTEGER NOT NULL,currency TEXT,unit_status TEXT NOT NULL DEFAULT 'UNVERIFIED',review_status TEXT NOT NULL DEFAULT 'REVIEW');
 CREATE TABLE IF NOT EXISTS audit_findings(id INTEGER PRIMARY KEY,level TEXT NOT NULL,source_id INTEGER,rule TEXT NOT NULL,details TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS ix_fact_ticker_period ON normalized_facts(ticker,report_year,report_period,metric);
 CREATE INDEX IF NOT EXISTS ix_fact_origin ON normalized_facts(source_id,source_sheet,source_cell);
 CREATE VIEW IF NOT EXISTS selected_facts AS SELECT f.* FROM normalized_facts f JOIN source_inventory s ON s.source_id=f.source_id WHERE s.duplicate_of IS NULL;
 ''');return c

def build(inp,out,report):
 if inp.resolve()==out.resolve():raise ValueError('Input and output SQLite must be different files')
 src=sqlite3.connect(f'file:{inp.as_posix()}?mode=ro',uri=True)
 src.row_factory=sqlite3.Row
 tables={x[0] for x in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 required={'source_files','financial_facts','sheets','cells'}
 if not required.issubset(tables):raise RuntimeError('V1 staging schema not found: '+str(required-tables))
 dst=prepare(out)
 with dst:
  dst.execute('DELETE FROM audit_findings');dst.execute('DELETE FROM normalized_facts');dst.execute('DELETE FROM source_inventory')
  records=src.execute('SELECT * FROM source_files ORDER BY id').fetchall()
  sha_primary={}; duplicate_count=0; unknown_meta=0
  for s in records:
   digest=s['sha256'];dupe=sha_primary.get(digest)
   if dupe is None:sha_primary[digest]=s['id']
   else:duplicate_count+=1
   dst.execute('INSERT INTO source_inventory VALUES(?,?,?,?,?,?,?,?,?,?)',(s['id'],s['filename'],s['path'],digest,s['year'],s['period'],s['ticker'],s['cell_count'],s['sheet_count'],dupe))
   if dupe is not None:dst.execute('INSERT INTO audit_findings(level,source_id,rule,details) VALUES(?,?,?,?)',('INFO',s['id'],'EXACT_DUPLICATE',f'SHA-256 matches source_id {dupe}; retained, omitted from selected_facts'))
   if s['ticker'] is None or s['year'] is None or s['period'] is None:
    unknown_meta+=1;dst.execute('INSERT INTO audit_findings(level,source_id,rule,details) VALUES(?,?,?,?)',('WARN',s['id'],'MISSING_METADATA','Cannot reliably identify ticker/year/period from filename'))
  matched=0; unverified=collections.Counter(); metrics=collections.Counter()
  for f in src.execute('''SELECT f.file_id, f.sheet_name, f.concept_en, f.statement_row, f.period_label, f.value_text, f.source_cell, s.ticker,s.year,s.period FROM financial_facts f JOIN source_files s ON s.id=f.file_id'''):
   pair=LOOKUP.get(clean(f['concept_en']))
   if not pair:continue
   if f['ticker'] is None or f['year'] is None or f['period'] is None:continue
   v=metric_value(f['value_text'])
   if v is None:continue
   statement,metric=pair;typ=classify_period(f['period_label'])
   dst.execute('''INSERT INTO normalized_facts(source_id,ticker,report_year,report_period,statement,metric,period_label,period_type,original_label,value_text,source_sheet,source_cell,source_row) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(f['file_id'],f['ticker'],f['year'],f['period'],statement,metric,f['period_label'],typ,f['concept_en'],v,f['sheet_name'],f['source_cell'],f['statement_row']))
   matched+=1;metrics[metric]+=1
   if typ=='unknown':unverified[f['file_id']]+=1
  # Audit conflicting mappings without silently selecting a value.
  conflicts=dst.execute('''SELECT source_id,metric,period_label,COUNT(*) n,COUNT(DISTINCT value_text) variants FROM normalized_facts GROUP BY source_id,metric,period_label HAVING variants>1''').fetchall()
  for source_id,metric,label,n,variants in conflicts:
   dst.execute('INSERT INTO audit_findings(level,source_id,rule,details) VALUES(?,?,?,?)',('REVIEW',source_id,'CONFLICTING_METRIC',f'{metric} {label}: {n} entries, {variants} different values'))
  missing=dst.execute('''SELECT s.source_id FROM source_inventory s LEFT JOIN normalized_facts f ON f.source_id=s.source_id WHERE f.id IS NULL GROUP BY s.source_id''').fetchall()
  for (sid,) in missing:dst.execute('INSERT INTO audit_findings(level,source_id,rule,details) VALUES(?,?,?,?)',('WARN',sid,'NO_MATCHED_FACTS','No conservative concept label matched; source remains preserved in V1'))
  # Balance sheet cross checks only when unique current-period values and same source.
  checks=0;imbalances=0
  for (sid,) in dst.execute('SELECT source_id FROM source_inventory WHERE duplicate_of IS NULL').fetchall():
   rows=dst.execute('''SELECT metric,value_text,period_label FROM normalized_facts WHERE source_id=? AND metric IN ('total_assets','total_liabilities','total_equity')''',(sid,)).fetchall()
   byperiod=collections.defaultdict(lambda:collections.defaultdict(set))
   for metric,value,label in rows:byperiod[label][metric].add(value)
   for label,d in byperiod.items():
    if all(len(d.get(key,set()))==1 for key in ('total_assets','total_liabilities','total_equity')):
     checks+=1
     from decimal import Decimal
     assets=Decimal(next(iter(d['total_assets'])));liab=Decimal(next(iter(d['total_liabilities'])));equity=Decimal(next(iter(d['total_equity'])))
     delta=assets-liab-equity
     if abs(delta)>max(Decimal('1'),abs(assets)*Decimal('0.000001')):
      imbalances+=1;dst.execute('INSERT INTO audit_findings(level,source_id,rule,details) VALUES(?,?,?,?)',('REVIEW',sid,'BALANCE_SHEET_CHECK',f'{label}: assets - liabilities - equity = {delta} (raw units)'))
  summary={'input_db':str(inp),'output_db':str(out),'source_files':len(records),'exact_duplicate_files':duplicate_count,'unique_hashes':len(sha_primary),'sources_missing_metadata':unknown_meta,'normalized_fact_rows':matched,'metric_counts':dict(sorted(metrics.items())),'sources_without_matched_facts':len(missing),'conflicting_metric_groups':len(conflicts),'balance_sheet_checks':checks,'balance_sheet_imbalances':imbalances,'normalization_status':'PROVISIONAL; unit/currency and YTD-versus-quarter must be confirmed from source notes','excel_deletion_enabled':False,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
 dst.close();src.close();return summary

def main():
 p=argparse.ArgumentParser(description='Read-only source V1 -> new V2 normalized SQLite; no deletions')
 p.add_argument('--input-db',required=True);p.add_argument('--output-db',required=True);p.add_argument('--report',required=True)
 a=p.parse_args();inp=Path(a.input_db).resolve();out=Path(a.output_db).resolve();rep=Path(a.report).resolve()
 if not inp.is_file():p.error('Input staging DB does not exist: '+str(inp))
 out.parent.mkdir(parents=True,exist_ok=True)
 try:summary=build(inp,out,rep)
 except Exception as ex:print('ERROR:',ex,file=sys.stderr);sys.exit(1)
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
