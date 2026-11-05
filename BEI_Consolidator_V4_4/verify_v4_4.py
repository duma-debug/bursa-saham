#!/usr/bin/env python3
"""V4.4 cautious normalization diagnostic. Input read-only; output new SQLite and JSON/CSV. No deletion."""
import argparse,csv,datetime as dt,json,sqlite3,collections,pathlib,re,sys

def safe_date(v):
    try: return dt.date.fromisoformat(v) if v else None
    except (TypeError,ValueError): return None

def period_label(m,row):
    ctx=(row['reported_context'] or '').lower(); start=safe_date(row['period_start_candidate']); end=safe_date(row['period_end_candidate']);
    if not end: return 'UNRESOLVED', 'BLOCK_MISSING_END'
    if row['expected_type']=='instant': return 'AS_OF_'+end.isoformat(), 'REVIEW_CONTEXT' if row['declared_type']!='instant' else 'CANDIDATE'
    if not start: return 'UNRESOLVED','BLOCK_MISSING_START'
    if end < start: return 'UNRESOLVED','BLOCK_DATE_ORDER'
    days=(end-start).days+1
    fy_start=safe_date(m['start_current'] if row['relative_period']=='current' else m['start_prior'])
    if fy_start and start==fy_start and 70<=days<=380: typ='YTD' if days<330 else 'FY'
    elif 65<=days<=105: typ='QUARTER_CANDIDATE'
    elif 160<=days<=200: typ='HALF_YEAR_CANDIDATE'
    elif 340<=days<=380: typ='FY_CANDIDATE'
    else: typ='UNCLASSIFIED_DURATION'
    return f'{typ}_{start.isoformat()}_{end.isoformat()}', ('REVIEW_CONTEXT' if row['declared_type']!='duration' else 'CANDIDATE')

def write_csv(path, cols, rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(cols);w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description='V4.4: source traceable period/unit/bank/legacy diagnostic; NO data certified or deleted')
    p.add_argument('--input-db',required=True);p.add_argument('--output-db',required=True);p.add_argument('--report',required=True);p.add_argument('--csv-dir',required=True)
    a=p.parse_args(); source=pathlib.Path(a.input_db).resolve();dest=pathlib.Path(a.output_db).resolve();report=pathlib.Path(a.report).resolve();csvdir=pathlib.Path(a.csv_dir).resolve()
    if not source.is_file(): p.error('Input database not found')
    if source==dest: p.error('Output cannot equal input')
    if dest.exists(): p.error('Output exists; choose a new filename to preserve existing data')
    dest.parent.mkdir(parents=True,exist_ok=True);report.parent.mkdir(parents=True,exist_ok=True);csvdir.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    if db.execute('pragma integrity_check').fetchone()[0]!='ok':raise RuntimeError('Input integrity check failed')
    names={r[0] for r in db.execute("select name from sqlite_master where type='table'")}
    if not {'metadata','context_review','source_quality','legacy_2022_preview'}<=names:raise RuntimeError('Input is not expected V4.3 schema')
    out=sqlite3.connect(dest);out.executescript('''
    CREATE TABLE source_metadata(source_id INTEGER PRIMARY KEY, filename TEXT,ticker TEXT, fiscal_year INT,report_period TEXT,currency TEXT,presentation_scale TEXT,scale_multiplier_candidate INT,start_current TEXT,end_current TEXT,metadata_status TEXT);
    CREATE TABLE reviewed_facts(source_fact_id INTEGER PRIMARY KEY,source_id INT,ticker TEXT,statement TEXT,metric TEXT,concept TEXT,raw_value TEXT,currency TEXT,reported_context TEXT,declared_type TEXT,expected_type TEXT,period_start TEXT,period_end TEXT,period_candidate TEXT,period_quality TEXT,scale_quality TEXT,valuation_eligible INT DEFAULT 0,source_sheet TEXT,source_cell TEXT);
    CREATE TABLE legacy_candidates(source_id INT,source_sheet TEXT,row_num INT,label TEXT,current_value TEXT,prior_value TEXT,status TEXT);
    CREATE TABLE quality_gates(gate TEXT PRIMARY KEY,status TEXT,note TEXT);
    CREATE INDEX idx_facts_ticker_metric_period ON reviewed_facts(ticker,metric,period_end);
    CREATE INDEX idx_facts_source ON reviewed_facts(source_id);
    ''')
    metadata={r['source_id']:dict(r) for r in db.execute('select * from metadata')}
    multiples={'Satuan Penuh / Full Amount':1,'Ribuan / In Thousand':1000,'Jutaan / In Million':1000000,'Miliaran / In Billion':1000000000}
    for m in metadata.values():
        out.execute('insert into source_metadata values(?,?,?,?,?,?,?,?,?,?,?)',(m['source_id'],m['filename'],m['ticker'],m['year'],m['report_period'],m['currency_code'],m['presentation_scale'],multiples.get(m['presentation_scale']),m['start_current'],m['end_current'],m['metadata_status']))
    stats=collections.Counter();periods=collections.Counter();issues=[];bank_issues=[];unit_review=[]
    bank_tickers={'ARTO','BBCA','BBNI','BBRI','BBTN','BMRI','BNGA','BNLI','AGRO','AGRS','BBSI','BBSI','BBSI','BBSI'}
    for r in db.execute('select * from context_review order by id'):
        m=metadata.get(r['source_id'],{});label,status=period_label(m,r);periods[label.split('_')[0]]+=1
        reason=[]
        if r['declared_type']!=r['expected_type']:reason.append('CONTEXT_TYPE_MISMATCH')
        if status!='CANDIDATE':reason.append(status)
        if not m.get('currency_code'):reason.append('NO_CURRENCY')
        if not m.get('presentation_scale'):reason.append('NO_SCALE')
        # Presentational scale is metadata only. Never multiply a raw XBRL value.
        if r['ticker'] in bank_tickers:reason.append('BANK_MAPPING_REVIEW')
        if reason:
            if len(issues)<250000:issues.append((r['id'],r['ticker'],r['metric'],r['reported_context'],r['declared_type'],r['expected_type'],label,';'.join(reason)))
            for x in reason:stats[x]+=1
        if r['ticker'] in bank_tickers and r['metric'] in ('total_assets','total_equity','total_liabilities'):
            bank_issues.append((r['id'],r['ticker'],r['metric'],r['raw_value'],r['reported_context'],r['source_sheet'],r['source_cell'],'REVIEW_BANK_SCOPE_AND_EQUITY'))
        out.execute('insert into reviewed_facts values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['id'],r['source_id'],r['ticker'],r['statement'],r['metric'],r['concept'],r['raw_value'],r['currency_code'],r['reported_context'],r['declared_type'],r['expected_type'],r['period_start_candidate'],r['period_end_candidate'],label,status,'BLOCK_SCALE_NOT_VERIFIED',0,r['source_sheet'],r['source_cell']))
    for r in db.execute('select * from legacy_2022_preview'):
        out.execute('insert into legacy_candidates values (?,?,?,?,?,?,?)',(r['source_id'],r['source_sheet'],r['row_num'],r['label'],r['current_value'],r['prior_value'],'REVIEW_LEGACY_UNMAPPED'))
    gates=[('integrity','PASS','Original V4.3 database SQLite integrity OK'),('periods','REVIEW','Period labels are candidates based on source metadata; context mismatch requires assessment'),('unit_currency','BLOCK','Presentation scale cannot be assumed to be the XBRL raw value scale'),('legacy_2022','BLOCK','2022 preview has not been mapped or reconciled'),('bank','BLOCK','Bank accounting taxonomy and scope not verified'),('valuation','BLOCK','0 facts eligible until independently reconciled'),('source_deletion','DISABLED','This program has no delete feature')]
    out.executemany('insert into quality_gates values (?,?,?)',gates);out.commit();integrity=out.execute('pragma integrity_check').fetchone()[0];out.close();db.close()
    write_csv(csvdir/'context_issues.csv',['fact_id','ticker','metric','context','declared_type','expected_type','period_candidate','issues'],issues)
    write_csv(csvdir/'bank_balance_review.csv',['fact_id','ticker','metric','raw_value','context','sheet','cell','status'],bank_issues)
    write_csv(csvdir/'source_metadata.csv',['source_id','filename','ticker','year','period','currency','presentation_scale','scale_multiplier_DISPLAY_ONLY','start_current','end_current'],[(m['source_id'],m['filename'],m['ticker'],m['year'],m['report_period'],m['currency_code'],m['presentation_scale'],multiples.get(m['presentation_scale']),m['start_current'],m['end_current']) for m in metadata.values()])
    total=sum(periods.values());result={'version':'4.4','status':'REVIEW_NOT_VALUATION_READY','sources':len(metadata),'facts':total,'legacy_preview_rows':1506,'bank_balance_rows_for_review':len(bank_issues),'issue_counts':dict(stats),'output_integrity':integrity,'valuation_eligible':0,'quality_gates':dict((k,v) for k,v,_ in gates),'note':'XBRL raw amounts kept unchanged. Source presentation multipliers are recorded but never applied until numerical reconciliation. No sources deleted.'}
    report.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
