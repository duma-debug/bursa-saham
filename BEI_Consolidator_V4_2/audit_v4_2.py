"""Read-only V4.2 modeling-readiness audit of V4.1 SQLite database.
Does not overwrite inputs or mark any figures valuation eligible.
"""
import argparse,csv,json,sqlite3,collections,os,pathlib,datetime,decimal

def main():
 p=argparse.ArgumentParser();p.add_argument('--input-db',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args()
 src=pathlib.Path(a.input_db).resolve(); out=pathlib.Path(a.output_dir).resolve()
 if not src.is_file():p.error('Input database does not exist')
 if out==src.parent: p.error('Use a separate report folder')
 out.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(f'file:{src.as_posix()}?mode=ro',uri=True);c.row_factory=sqlite3.Row
 integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
 facts=c.execute('SELECT f.*,s.filename,s.sha256,s.duplicate_of FROM facts f JOIN source_catalog s ON s.source_id=f.source_id').fetchall()
 sources=c.execute('SELECT * FROM source_catalog').fetchall()
 def write(name,heads,rows):
  with (out/name).open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.writer(f);w.writerow(heads);w.writerows(rows)
 issues=[]; inventory=[]
 for s in sources:
  sf=[x for x in facts if x['source_id']==s['source_id']]
  flags=[]
  if s['duplicate_of'] is not None: flags.append('DUPLICATE_FILE')
  if not sf:flags.append('NO_MAPPED_FACTS')
  if s['year']==2022 and not sf:flags.append('LEGACY_2022_REQUIRES_RAW_EXTRACTION')
  inventory.append([s['source_id'],s['filename'],s['ticker'],s['year'],s['report_period'],s['source_status'],s['duplicate_of'],len(sf),';'.join(flags)])
  for flag in flags:issues.append([s['source_id'],s['filename'],'SOURCE',flag,''])
 write('source_inventory.csv',['source_id','filename','ticker','year','period','source_status','duplicate_of','mapped_facts','flags'],inventory)
 mism=[]; unit=[]; periods=[]; bank=[]; grouped=collections.defaultdict(list)
 for f in facts:
  grouped[(f['source_id'],f['metric'],f['reporting_context'])].append(f)
  if f['context_type']!=f['expected_context_type']:
   mism.append([f['source_id'],f['ticker'],f['filename'],f['metric'],f['reporting_context'],f['context_type'],f['expected_context_type'],f['source_sheet'],f['source_cell'],f['raw_value']])
  if f['currency'] is None or f['unit_multiplier'] is None:
   unit.append([f['source_id'],f['ticker'],f['metric'],f['reporting_context'],f['raw_value'],f['source_sheet'],f['source_cell'],'UNIT_OR_CURRENCY_UNVERIFIED'])
  if f['context_type']=='duration':
   periods.append([f['source_id'],f['ticker'],f['report_year'],f['report_period'],f['metric'],f['reporting_context'],'NOT_VERIFIED_AS_QUARTER_OR_YTD'])
  if 'SECTOR_MAPPING_REVIEW' in (f['review_reason'] or ''):
   bank.append([f['source_id'],f['ticker'],f['metric'],f['concept'],f['reporting_context'],f['raw_value']])
 write('context_mismatches.csv',['source_id','ticker','filename','metric','reporting_context','observed_type','expected_type','sheet','cell','raw_value'],mism)
 write('unit_currency_review.csv',['source_id','ticker','metric','reporting_context','raw_value','sheet','cell','issue'],unit)
 write('duration_semantics_review.csv',['source_id','ticker','year','filing_period','metric','context','status'],periods)
 write('sector_mapping_review.csv',['source_id','ticker','metric','concept','context','raw_value'],bank)
 dupgroups=[]
 for k,group in grouped.items():
  values={g['raw_value'] for g in group}
  if len(values)>1:dupgroups.append([*k,len(group),len(values),'|'.join(sorted(values)[:4])])
 write('conflicting_raw_values.csv',['source_id','metric','context','count','distinct_values','sample_values'],dupgroups)
 pdfs=c.execute('SELECT * FROM pdf_references').fetchall()
 write('pdf_reference_review.csv',['filename','ticker','year','period','link_status','source_id'],[[x['filename'],x['ticker'],x['report_year'],x['report_period'],x['link_status'],x['source_id']] for x in pdfs])
 # Instant balance sheet: compare *only* when metrics share the same source and reporting context. Results are diagnostic, not accounting certifications.
 balance=[]
 for (sid,context),fs in {(f['source_id'],f['reporting_context']):None for f in facts if f['metric'] in ('total_assets','total_liabilities','total_equity')}.items():
  matched=[f for f in facts if f['source_id']==sid and f['reporting_context']==context and f['metric'] in ('total_assets','total_liabilities','total_equity') and f['context_type']=='instant']
  by=collections.defaultdict(list)
  for f in matched:by[f['metric']].append(f)
  if not all(len(by[m])==1 for m in ('total_assets','total_liabilities','total_equity')):continue
  try:
   d=lambda m:decimal.Decimal(str(by[m][0]['raw_value']).replace(',',''))
   A,L,E=d('total_assets'),d('total_liabilities'),d('total_equity'); diff=A-L-E
   balance.append([sid,by['total_assets'][0]['ticker'],context,str(A),str(L),str(E),str(diff),'CHECK_UNITS_AND_SCOPE' if diff else 'ARITHMETIC_MATCH_ONLY'])
  except (decimal.InvalidOperation,TypeError):pass
 write('balance_diagnostics.csv',['source_id','ticker','context','assets_raw','liabilities_raw','equity_raw','difference_raw','assessment'],balance)
 report={'version':'4.2-audit','mode':'READ_ONLY_NOT_VALUATION_READY','input_db':str(src),'integrity_check':integrity,'source_files':len(sources),'unique_source_hashes':len({s['sha256'] for s in sources}),'mapped_fact_rows':len(facts),'context_mismatch_rows':len(mism),'unverified_unit_currency_rows':len(unit),'duration_context_rows':len(periods),'sector_review_rows':len(bank),'sources_without_facts':sum(not any(x['source_id']==s['source_id'] for x in facts) for s in sources),'sources_2022_without_facts':sum(s['year']==2022 and not any(x['source_id']==s['source_id'] for x in facts) for s in sources),'duplicate_source_files':sum(s['duplicate_of'] is not None for s in sources),'conflicting_raw_metric_groups':len(dupgroups),'balance_comparisons':len(balance),'balance_nonzero_raw_differences':sum(decimal.Decimal(b[6])!=0 for b in balance),'pdf_references':len(pdfs),'valuation_eligible':0,'quality_gates':{'unit_currency':'BLOCK','calendar_periods':'BLOCK','sector_specific':'REVIEW','legacy_2022':'BLOCK','valuation':'BLOCK','source_deletion':'DISABLED'},'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 (out/'audit_report_v4_2.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(report,indent=2));c.close()
if __name__=='__main__':main()
