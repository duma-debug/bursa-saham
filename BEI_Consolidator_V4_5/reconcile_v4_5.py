#!/usr/bin/env python3
"""BEI Consolidator V4.5: evidence-based, no destructive actions.
Audit exemplar: AALI FY2022 sourced from supplied audited PDF and 2022 XBRL preview.
Not a general automated PDF parser. No valuation approval is granted.
"""
import argparse,csv,datetime,decimal,json,pathlib,sqlite3,sys
from decimal import Decimal
D=Decimal
# Values in PDF AALI LK Tahunan 2022.pdf, PDF pages 9-13, IDR million (EPS IDR/share)
# Only explicitly matched Indonesian account labels are reconciled; avoid guessing synonyms.
REF={
 'cash_equivalents':('1210000','Kas dan setara kas','1619616','balance_sheet',9),
 'current_assets':('1210000','Jumlah aset lancar','7390608','balance_sheet',9),
 'total_assets':('1210000','Jumlah aset','29249340','balance_sheet',9),
 'current_liabilities':('1210000','Jumlah liabilitas jangka pendek','2052939','balance_sheet',10),
 'total_liabilities':('1210000','Jumlah liabilitas','7006119','balance_sheet',10),
 'total_equity':('1210000','Jumlah ekuitas','22243221','balance_sheet',10),
 'revenue':('1321000','Penjualan dan pendapatan usaha','21828591','income_statement',11),
 'cost_of_revenue':('1321000','Beban pokok penjualan dan pendapatan','18006474','income_statement',11),
 'gross_profit':('1321000','Jumlah laba bruto','3822117','income_statement',11),
 'profit_before_tax':('1321000','Jumlah laba (rugi) sebelum pajak penghasilan','2429178','income_statement',11),
 'net_income_total':('1321000','Jumlah laba (rugi)','1792050','income_statement',11),
 'net_income_parent':('1321000','Laba (rugi) yang dapat diatribusikan ke entitas induk','1726607','income_statement',11),
 'eps_basic':('1321000','Laba (rugi) per saham dasar dari operasi yang dilanjutkan','897.08','income_statement',11),
}
def psql(path):
 uri=pathlib.Path(path).resolve().as_uri()+'?mode=ro'
 return sqlite3.connect(uri,uri=True)
def main():
 ap=argparse.ArgumentParser(description='V4.5 verified reconciliation pilot (AALI FY2022). Never edits input DBs.')
 ap.add_argument('--staging-db',required=True);ap.add_argument('--review-db',required=True)
 ap.add_argument('--output-db',required=True);ap.add_argument('--report',required=True)
 ap.add_argument('--csv-dir',required=True)
 a=ap.parse_args()
 for p in (a.staging_db,a.review_db):
  if not pathlib.Path(p).is_file(): ap.error('Input database not found: '+p)
 out=pathlib.Path(a.output_db);report=pathlib.Path(a.report);csvdir=pathlib.Path(a.csv_dir)
 if out.resolve() in (pathlib.Path(a.staging_db).resolve(),pathlib.Path(a.review_db).resolve()):ap.error('Output cannot overwrite inputs')
 if out.exists():ap.error('Output already exists; rename/move output to preserve prior results: '+str(out))
 out.parent.mkdir(parents=True,exist_ok=True);report.parent.mkdir(parents=True,exist_ok=True);csvdir.mkdir(parents=True,exist_ok=True)
 st=psql(a.staging_db);rv=psql(a.review_db)
 st.row_factory=sqlite3.Row;rv.row_factory=sqlite3.Row
 try:
  src=st.execute("select * from source_files where ticker='AALI' and year=2022 and period='Tahunan'").fetchall()
  if len(src)!=1:raise ValueError('Expected exactly one AALI 2022 annual source; got '+str(len(src)))
  source=src[0];sid=source['id']
  md=rv.execute('select * from metadata where source_id=?',(sid,)).fetchone()
  if md is None:raise ValueError('Source metadata missing')
  if md['currency_code']!='IDR' or 'Jutaan' not in (md['presentation_scale'] or '') or md['end_current']!='2022-12-31' or md['start_current']!='2022-01-01':
   raise ValueError('Expected AALI FY2022 metadata IDR / millions / FY2022; found '+str(tuple(md)))
  previews=rv.execute('select * from legacy_2022_preview where source_id=?',(sid,)).fetchall()
  lookup={}
  for x in previews:lookup.setdefault((x['source_sheet'],x['label']),[]).append(x)
  findings=[];verified=[]
  for metric,(sheet,label,pdfval,statement,pdfpage) in REF.items():
   rows=lookup.get((sheet,label),[])
   if len(rows)!=1 or rows[0]['current_value'] is None:
    findings.append((metric,'REVIEW','NO_UNIQUE_XBRL_LABEL',label,str(len(rows)),pdfval));continue
   try: raw=D(str(rows[0]['current_value']));expected=D(pdfval)
   except decimal.InvalidOperation:
    findings.append((metric,'REVIEW','NONNUMERIC_XBRL',label,str(rows[0]['current_value']),pdfval));continue
   if raw!=expected:
    findings.append((metric,'REVIEW','VALUE_MISMATCH',label,str(raw),pdfval));continue
   verified.append((metric,statement,'2022-01-01' if statement=='income_statement' else None,'2022-12-31',str(expected),'IDR/share' if metric=='eps_basic' else 'IDR million',sid,sheet,rows[0]['row_num'],label,pdfpage,'PDF_AND_XBRL_MATCH'))
  vals={r[0]:D(r[4]) for r in verified}
  controls=[]
  def check(name,required,lhs,rhs):
   if all(k in vals for k in required): controls.append((name,'PASS' if lhs()==rhs() else 'FAIL',str(lhs()-rhs())))
   else:controls.append((name,'NOT_TESTED','missing inputs'))
  check('assets_equals_liabilities_plus_equity',['total_assets','total_liabilities','total_equity'],lambda:vals['total_assets'],lambda:vals['total_liabilities']+vals['total_equity'])
  check('gross_profit_equals_revenue_less_cost',['revenue','cost_of_revenue','gross_profit'],lambda:vals['gross_profit'],lambda:vals['revenue']-vals['cost_of_revenue'])
  # A failed control disqualifies ALL rows; don't mark data verified on a conflicting audited source.
  bad=any(status=='FAIL' for _,status,_ in controls)
  db=sqlite3.connect(out)
  db.executescript('''PRAGMA foreign_keys=ON;
 CREATE TABLE source_metadata(source_id INTEGER PRIMARY KEY, ticker TEXT, year INTEGER, report_period TEXT, currency TEXT, presentation_scale TEXT, period_start TEXT, period_end TEXT, source_filename TEXT, sha256 TEXT);
 CREATE TABLE verified_facts(id INTEGER PRIMARY KEY, ticker TEXT, metric TEXT, statement TEXT, period_start TEXT, period_end TEXT, value_text TEXT, unit TEXT, status TEXT, source_id INTEGER, source_sheet TEXT, source_row INTEGER, original_label TEXT, evidence_document TEXT, evidence_pdf_page INTEGER, method TEXT);
 CREATE TABLE reconciliation_checks(name TEXT PRIMARY KEY,status TEXT,difference_text TEXT);
 CREATE TABLE unresolved_issues(metric TEXT,status TEXT,reason TEXT,source_label TEXT,raw_value TEXT,pdf_value TEXT);
 CREATE TABLE quality_gates(name TEXT PRIMARY KEY,status TEXT,description TEXT);
 ''')
  db.execute('insert into source_metadata values (?,?,?,?,?,?,?,?,?,?)',(sid,'AALI',2022,'Tahunan',md['currency_code'],md['presentation_scale'],md['start_current'],md['end_current'],source['filename'],source['sha256']))
  for v in verified:
   metric,statement,ps,pe,value,unit,srcid,sh,row,label,page,method=v
   db.execute('insert into verified_facts(ticker,metric,statement,period_start,period_end,value_text,unit,status,source_id,source_sheet,source_row,original_label,evidence_document,evidence_pdf_page,method) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('AALI',metric,statement,ps,pe,value,unit,'REVIEW' if bad else 'VERIFIED_REFERENCE_MATCH',srcid,sh,row,label,'AALI LK Tahunan 2022.pdf',page,method))
  db.executemany('insert into reconciliation_checks values (?,?,?)',controls)
  db.executemany('insert into unresolved_issues values (?,?,?,?,?,?)',findings)
  gates=[('aali_2022_pdf_xbrl','BLOCK' if bad or findings else 'PASS','Limited to 13 selected audited PDF line items and matching XBRL preview'),('all_emiten_coverage','BLOCK','Pilot does not normalize other securities'),('cash_flow_2022','BLOCK','Cash flow not reconciled in this pilot'),('unit_currency_general','BLOCK','Other sources lack numerical cross-source reconciliation'),('period_quarter_ttm','BLOCK','Quarterly semantics remain unresolved'),('bank_mapping','BLOCK','Bank-specific mappings unverified'),('valuation_ready','BLOCK','No three statement or valuation approval'),('source_deletion','DISABLED','All original source files must be retained')]
  db.executemany('insert into quality_gates values (?,?,?)',gates)
  db.commit();integrity=db.execute('pragma integrity_check').fetchone()[0];db.close()
  with (csvdir/'verified_aali_2022.csv').open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.writer(f);w.writerow(['ticker','metric','value','unit','status','pdf_page','xbrl_sheet','xbrl_row'])
   for v in verified:w.writerow(['AALI',v[0],v[4],v[5],'REVIEW' if bad else 'VERIFIED_REFERENCE_MATCH',v[10],v[7],v[8]])
  with (csvdir/'unresolved_issues.csv').open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.writer(f);w.writerow(['metric','status','reason','source_label','raw_value','pdf_value']);w.writerows(findings)
  with (csvdir/'reconciliation_checks.csv').open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.writer(f);w.writerow(['name','status','difference']);w.writerows(controls)
  result={'version':'4.5-pilot','mode':'NON_DESTRUCTIVE_REFERENCE_RECONCILIATION','source_file':source['filename'],'reference_pdf':'AALI LK Tahunan 2022.pdf','pdf_reference_hardcoded_from_supplied_document':True,'verified_reference_matches':0 if bad else len(verified),'unresolved_reference_items':len(findings),'reconciliation_checks':dict((n,s) for n,s,_ in controls),'integrity_check':integrity,'valuation_eligible':0,'quality_gates':dict((n,s) for n,s,_ in gates),'sources_deleted':0,'output_db':str(out),'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  report.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
  print(json.dumps(result,indent=2,ensure_ascii=False))
 finally:st.close();rv.close()
if __name__=='__main__':main()
