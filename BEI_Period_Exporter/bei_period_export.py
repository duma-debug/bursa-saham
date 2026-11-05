#!/usr/bin/env python3
"""Export current and comparative XBRL periods from existing BEI databases.
Source DBs only read, outputs separate. All values REVIEW, no valuation readiness.
"""
import argparse, csv, json, sqlite3, pathlib, datetime, collections, re
P=pathlib.Path

def connect_ro(path):
    if not path.is_file(): raise SystemExit(f'File not found: {path}')
    return sqlite3.connect('file:'+path.resolve().as_posix()+'?mode=ro', uri=True)

def csvout(path, headers, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(headers);w.writerows(rows)

def convert_context(ctx, year, report_period, meta):
    # Reporting date: note Balance Sheet comparator typically previous FY end,
    # whereas Income/Cash Flow comparator is same YTD window last year.
    current=ctx.startswith('Current'); comparative=ctx.startswith('Prior')
    role='CURRENT' if current else 'COMPARATIVE' if comparative else 'UNKNOWN'
    kind='INSTANT' if ctx.endswith('Instant') else 'DURATION' if ctx.endswith('Duration') else 'UNKNOWN'
    if role=='CURRENT':
        yr=year; end=meta.get('end_current');start=meta.get('start_current') if kind=='DURATION' else None
        period='FY' if report_period.lower()=='tahunan' else report_period
    elif ctx.startswith('PriorEndYear'):
        yr=year-1;end=(str(year-1)+'-12-31');start=(str(year-1)+'-01-01') if kind=='DURATION' else None
        period='FY_END';
    else:
        yr=year-1;end=meta.get('end_prior');start=meta.get('start_prior') if kind=='DURATION' else None
        period='FY' if report_period.lower()=='tahunan' else report_period
    # First-class explicit uncertainty; never infer authoritative fiscal dates from filenames.
    issues=[]
    if not end:issues.append('DATE_END_MISSING')
    if kind=='DURATION' and not start:issues.append('START_DATE_MISSING')
    if ctx.startswith('PriorYearInstant') and report_period.lower()!='tahunan':issues.append('PRIOR_INSTANT_DATE_REVIEW')
    if ctx.startswith('PriorEndYear') and report_period.lower()!='tahunan':issues.append('PRIOR_FY_END_ASSUMED')
    if kind=='UNKNOWN':issues.append('UNRECOGNIZED_CONTEXT')
    return role,kind,yr,period,start,end,';'.join(issues) or 'DATE_FROM_SOURCE_METADATA'

def main():
    a=argparse.ArgumentParser(description='Current+comparative period exporter (no destructive actions)')
    a.add_argument('--base',default=r'C:\Analisis_Saham_BEI')
    a.add_argument('--ticker',default='AALI')
    args=a.parse_args();base=P(args.base);ticker=args.ticker.upper().strip()
    if not re.fullmatch(r'[A-Z0-9]{3,8}',ticker):raise SystemExit('Invalid ticker')
    model=connect_ro(base/'financial_modeling_v4_1.db');legacy=connect_ro(base/'financial_legacy_v4_6.db')
    out=base/'BEI_Master_Output';out.mkdir(parents=True,exist_ok=True)
    metadata={r[0]:dict(zip(['source_id','ticker','year','report_period','currency','presentation_scale','start_current','end_current','start_prior','end_prior','source_filename'],r)) for r in legacy.execute('select * from source_meta')}
    sources={r[0]:r for r in model.execute('select source_id,filename,sha256,year,report_period,ticker,duplicate_of,source_status from source_catalog')}
    records=[];issues=[]
    sql='''SELECT id,source_id,ticker,report_year,report_period,statement,metric,concept,reporting_context,context_relative,context_type,expected_context_type,raw_value,source_sheet,source_cell,check_status FROM facts WHERE ticker=?'''
    for f in model.execute(sql,(ticker,)):
        fid,sid,tk,yr,rp,statement,metric,concept,context,relative,observed,expected,val,sheet,cell,old_status=f
        meta=metadata.get(sid,{})
        role,kind,dy,period,start,end,issue=convert_context(context,yr,rp,meta)
        src=sources.get(sid,(sid,'',None,yr,rp,tk,None,None))
        if observed!=expected and expected in ('instant','duration'):
            issue=issue+';XBRL_TYPE_MISMATCH_REVIEW'
        if not meta.get('currency'):issue=issue+';CURRENCY_MISSING'
        # Only immutable data with unequivocal units may be used for ratios. Here: REVIEW always.
        records.append((tk,dy,period,start,end,statement,metric,val,meta.get('currency',''),meta.get('presentation_scale',''),
                        kind,role,context,yr,rp,src[1],sheet,cell,src[2],sid,fid,'REVIEW_NOT_NORMALIZED',issue,1 if src[6] is not None else 0))
    headers=['ticker','data_fiscal_year','data_period_label','period_start','period_end','statement','metric',
             'raw_value_NOT_NORMALIZED','currency_metadata','presentation_scale_metadata','context_kind','source_role',
             'xbrl_context','filing_year','filing_period','source_filename','source_sheet','source_cell','source_sha256',
             'source_id','fact_id','quality_status','review_flags','duplicate_filing']
    records.sort(key=lambda r:(r[1],r[2],r[5],r[6],r[13],r[15],r[20]))
    # Separate all versions from one row per metric+data-period; never overwrite revised values.
    chosen={};duplicate_versions=0
    for r in records:
        # accounting concept/context/date retained to prevent merging unlike periods
        key=(r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[10])
        if key in chosen: duplicate_versions+=1
        prior=chosen.get(key)
        if prior is None or (r[23]==0 and prior[23]==1) or (r[23]==prior[23] and r[13]>prior[13]):
            chosen[key]=r
    best=sorted(chosen.values(),key=lambda r:(r[1],r[2],r[5],r[6]))
    # All source revisions visible in full export; chosen is a convenience view only, never verified.
    csvout(out/f'{ticker}_all_periods_ALL_VERSIONS_REVIEW.csv',headers,records)
    csvout(out/f'{ticker}_periods_SELECTED_REVIEW.csv',headers,best)
    # report useful coverage: fiscal year distribution, source roles and period type.
    counts=collections.Counter(r[1] for r in records)
    summary={'status':'REVIEW_NOT_VALUATION_READY','ticker':ticker,'input_files':2,'rows_all_versions':len(records),
             'rows_selected_candidate':len(best),'multiple_version_rows':duplicate_versions,
             'current_rows':sum(r[11]=='CURRENT' for r in records),
             'comparative_rows':sum(r[11]=='COMPARATIVE' for r in records),
             'data_year_counts':dict(sorted(counts.items())),
             'must_verify':['underlying XBRL unit for each value','fiscal period actual start/end',
                            'duplicate and restated values','scope consolidated vs parent','standalone Q vs cumulative YTD'],
             'warning':'SELECTED is convenience only; no values converted, no growth/TTM calculated, no sources deleted.'}
    (out/f'{ticker}_period_export_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    model.close();legacy.close()
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
