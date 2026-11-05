#!/usr/bin/env python3
"""BEI Content Verifier v1.0. Python stdlib only.
Cross-check extracted CSV facts against original staging SQLite cell values;
validate same-filing comparative pairs; create conservative publication review.
Never edits input databases or sources. Does not certify official PDF/audit numbers.
"""
import argparse, csv, json, re, sqlite3, hashlib, collections
from decimal import Decimal, InvalidOperation
from pathlib import Path

DURATION={'revenue','gross_profit','net_income_parent','net_income_total','cashflow_operating','cashflow_investing','cashflow_financing','capex_ppe_outflow','cost_of_revenue','eps_basic','profit_before_tax','tax_benefit_expense','finance_costs','selling_expense','general_administrative_expense'}
KEY_METRICS={'revenue':'Pendapatan','gross_profit':'Laba bruto','net_income_parent':'Laba pemilik entitas induk','cashflow_operating':'Arus kas operasi','net_income_total':'Laba bersih konsolidasian','capex_ppe_outflow':'Belanja aset tetap'}

def decimal(s):
    try:
        v=Decimal(str(s).strip());return v if v.is_finite() else None
    except (InvalidOperation,ValueError,TypeError):return None

def csv_read(path):
    with path.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def csv_write(path,rows,cols):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)

def evaluate(base,ticker,input_file,staging,out):
    rows=csv_read(input_file)
    if not rows:raise ValueError('File CSV kosong')
    required=['ticker','source_filename','source_sheet','source_cell','raw_value_NOT_NORMALIZED','source_role','metric','period_start','period_end','data_fiscal_year','filing_period','currency_metadata','source_sha256']
    missing=[x for x in required if x not in rows[0]]
    if missing:raise ValueError('Kolom CSV tidak ditemukan: '+', '.join(missing))
    uri=staging.resolve().as_uri()+'?mode=ro'
    conn=sqlite3.connect(uri,uri=True)
    try:
        integrity=conn.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok':raise ValueError('Database staging gagal integrity_check')
        source_by_name=collections.defaultdict(list)
        for id,filename,sha in conn.execute('SELECT id,filename,sha256 FROM source_files'):
            source_by_name[filename].append((id,sha))
        # Resolve source sheet IDs once; individual cell lookup uses PK(sheet_id,address).
        sheet_ids={}
        for file_id,filename in conn.execute('SELECT id,filename FROM source_files'):
            for sid,sname in conn.execute('SELECT id,name FROM sheets WHERE file_id=?',(file_id,)):
                sheet_ids[(filename,sname)]=sid
        cell_cache={}
        enriched=[]
        for r in rows:
            if r.get('ticker','').upper()!=ticker:continue
            flags=[];src=r.get('source_filename','')
            listed=source_by_name.get(src,[])
            if not listed:flags.append('SOURCE_FILE_NOT_IN_DB')
            elif not any(sha.lower()==r.get('source_sha256','').lower() for _,sha in listed):flags.append('SOURCE_HASH_MISMATCH')
            key=(src,r.get('source_sheet',''),r.get('source_cell',''))
            if key not in cell_cache:
                sid=sheet_ids.get((key[0],key[1]))
                cell_cache[key]=conn.execute('SELECT value FROM cells WHERE sheet_id=? AND address=?',(sid,key[2])).fetchall() if sid else []
            matched=cell_cache[key]
            if len(matched)!=1:flags.append('SOURCE_CELL_MISSING_OR_AMBIGUOUS')
            elif decimal(matched[0][0]) is None or decimal(r.get('raw_value_NOT_NORMALIZED')) != decimal(matched[0][0]):
                flags.append('SOURCE_VALUE_MISMATCH')
            yr=r.get('data_fiscal_year','')
            try:
                if int(yr)<1990 or int(yr)>2100:flags.append('INVALID_YEAR')
            except ValueError:flags.append('INVALID_YEAR')
            if r.get('context_kind') != 'DURATION' and r.get('metric') in DURATION:flags.append('CONTEXT_REVIEW')
            if r.get('review_flags',''):flags.append('UPSTREAM_REVIEW_FLAGS')
            if r.get('duplicate_filing')=='1':flags.append('DUPLICATE_FILING')
            r=dict(r)
            r['cell_verified']='YES' if not any(f in flags for f in ('SOURCE_FILE_NOT_IN_DB','SOURCE_HASH_MISMATCH','SOURCE_CELL_MISSING_OR_AMBIGUOUS','SOURCE_VALUE_MISMATCH')) else 'NO'
            r['verification_flags']=';'.join(flags)
            r['verification_status']='SOURCE_MATCHED_REVIEW' if r['cell_verified']=='YES' else 'BLOCK_SOURCE_MISMATCH'
            enriched.append(r)
    finally:conn.close()
    group=collections.defaultdict(lambda:collections.defaultdict(list))
    for r in enriched:
        if r.get('duplicate_filing')=='1':continue
        group[(r['source_filename'],r['filing_period'],r['metric'])][r['source_role']].append(r)
    pairs=[]
    for (filename,filing_period,metric), roles in sorted(group.items()):
        if len(roles['CURRENT'])!=1 or len(roles['COMPARATIVE'])!=1:continue
        cur=roles['CURRENT'][0];prior=roles['COMPARATIVE'][0]
        flags=[]
        if cur['cell_verified']!='YES' or prior['cell_verified']!='YES':flags.append('BLOCK_SOURCE')
        try:
            if int(cur['data_fiscal_year'])-int(prior['data_fiscal_year'])!=1:flags.append('YEAR_NOT_CONSECUTIVE')
        except ValueError:flags.append('INVALID_YEAR')
        if cur['data_period_label']!=prior['data_period_label']:flags.append('PERIOD_MISMATCH')
        # Year-over-year match: period dates must be exactly one year apart, including leap handling by MM-DD.
        if not cur['period_start'] or not prior['period_start'] or cur['period_start'][5:]!=prior['period_start'][5:]:flags.append('START_DATE_MISMATCH')
        if not cur['period_end'] or not prior['period_end'] or cur['period_end'][5:]!=prior['period_end'][5:]:flags.append('END_DATE_MISMATCH')
        if cur['currency_metadata']!=prior['currency_metadata'] or not cur['currency_metadata']:flags.append('CURRENCY_MISMATCH')
        if cur['presentation_scale_metadata']!=prior['presentation_scale_metadata']:flags.append('PRESENTATION_SCALE_MISMATCH')
        a=decimal(cur['raw_value_NOT_NORMALIZED']);b=decimal(prior['raw_value_NOT_NORMALIZED'])
        if a is None or b is None:flags.append('NONNUMERIC')
        if b is not None and b<=0:flags.append('BASE_NONPOSITIVE')
        if metric not in DURATION:flags.append('NOT_DURATION_METRIC')
        if 'CONTEXT_REVIEW' in cur['verification_flags'] or 'CONTEXT_REVIEW' in prior['verification_flags']:flags.append('CONTEXT_REVIEW')
        hard=any(x in flags for x in ('BLOCK_SOURCE','YEAR_NOT_CONSECUTIVE','INVALID_YEAR','PERIOD_MISMATCH','START_DATE_MISMATCH','END_DATE_MISMATCH','CURRENCY_MISMATCH','PRESENTATION_SCALE_MISMATCH','NONNUMERIC','BASE_NONPOSITIVE','NOT_DURATION_METRIC'))
        yoy=round((a/b-1)*Decimal(100),2) if not hard else None
        pairs.append(dict(ticker=ticker,metric=metric,filing=filename,filing_period=filing_period,prior_year=prior['data_fiscal_year'],current_year=cur['data_fiscal_year'],currency=cur['currency_metadata'],prior_raw=prior['raw_value_NOT_NORMALIZED'],current_raw=cur['raw_value_NOT_NORMALIZED'],yoy_pct_review=str(yoy) if yoy is not None else '',source_current=cur['source_sheet']+'!'+cur['source_cell'],source_prior=prior['source_sheet']+'!'+prior['source_cell'],quality='BLOCK' if hard else 'SOURCE_MATCHED_REVIEW',issues=';'.join(flags) if flags else 'SOURCE_CELL_MATCHED_PDF_NOT_CHECKED'))
    cols=list(enriched[0].keys()) if enriched else required
    csv_write(out/f'{ticker}_FACT_VERIFICATION.csv',enriched,cols)
    columns=['ticker','metric','filing','filing_period','prior_year','current_year','currency','prior_raw','current_raw','yoy_pct_review','source_current','source_prior','quality','issues']
    csv_write(out/f'{ticker}_YOY_VERIFIED_SOURCE_REVIEW.csv',pairs,columns)
    usable=[p for p in pairs if p['quality']=='SOURCE_MATCHED_REVIEW' and p['metric'] in KEY_METRICS]
    key=lambda r:(int(r['current_year']), {'Tahunan':4,'III':3,'II':2,'I':1}.get(r['filing_period'],0))
    most=max(usable,key=key) if usable else None
    brief=[f'# {ticker} — Bahan Artikel (SOURCE-MATCHED, REVIEW)', '', '> **Belum untuk publikasi.** Nilai telah dibandingkan dengan sel di SQLite staging, **bukan** direkonsiliasi ke PDF audited, skala dan konteks seluruh emiten. Pertumbuhan adalah indikator riset awal.', '']
    if most:
        latest=[r for r in usable if r['filing']==most['filing']]
        brief.extend([f'File: `{most["filing"]}`',f'Periode: {most["filing_period"]} {most["current_year"]} dibandingkan {most["prior_year"]}.','','| Indikator | YoY awal | Status |','|---|---:|---|'])
        for m,label in KEY_METRICS.items():
            for x in latest:
                if x['metric']==m:
                    brief.append(f'| {label} | {Decimal(x["yoy_pct_review"]):+.1f}% | Perlu cek PDF |')
        brief.extend(['','**Pertanyaan untuk artikel:** Apakah perubahan laba sejalan dengan arus kas operasi? Apa penyebab perubahan margin, working capital, dan belanja modal?','', '**Sebelum publikasi:** cocokkan angka ke laporan resmi, pastikan satuan, basis konsolidasian, klasifikasi akun, dan faktor nonberulang.'])
    else:brief.append('Tidak ada pasangan YoY yang memenuhi syarat kesebandingan sumber. Periksa laporan verifikasi.')
    (out/f'{ticker}_ARTICLE_RESEARCH_BRIEF.md').write_text('\n'.join(brief)+'\n',encoding='utf-8')
    report={'ticker':ticker,'status':'SOURCE_VERIFICATION_ONLY_NOT_PUBLICATION_APPROVED', 'facts_checked':len(enriched),'cell_matched':sum(x['cell_verified']=='YES' for x in enriched),'cell_blocked':sum(x['cell_verified']!='YES' for x in enriched),'comparison_pairs':len(pairs),'yoy_review':sum(x['quality']=='SOURCE_MATCHED_REVIEW' for x in pairs),'yoy_blocked':sum(x['quality']=='BLOCK' for x in pairs),'staging_integrity':integrity,'source_db_unchanged':True,'pdf_audit_reconciliation':False,'publication_approved':0,'notes':['Checks stored CSV numeric value against exact stored staging cell and source file SHA','No independent verification of 2026 quarterly PDF or true XBRL concept mappings','Source presentation scale is recorded but is not applied','Comparative period remains associated with its fiscal year','No TTM or valuation computed','All original source files remain untouched']}
    (out/f'{ticker}_VERIFICATION_REPORT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser(description='Cross-check BEI period export with staging SQLite without modifying any database')
    ap.add_argument('--base',default=r'C:\Analisis_Saham_BEI')
    ap.add_argument('--ticker',default='AALI')
    ap.add_argument('--input',default=None)
    ap.add_argument('--staging-db',default=None)
    args=ap.parse_args();ticker=args.ticker.upper()
    if not re.fullmatch('[A-Z0-9]{3,8}',ticker):ap.error('Invalid ticker')
    base=Path(args.base)
    csvpath=Path(args.input) if args.input else base/'BEI_Master_Output'/f'{ticker}_periods_SELECTED_REVIEW.csv'
    staging=Path(args.staging_db) if args.staging_db else base/'financial_production.db'
    if not csvpath.exists():ap.error('File tidak ditemukan: '+str(csvpath)+'; jalankan Period Exporter terlebih dulu')
    if not staging.exists():ap.error('Staging DB tidak ditemukan: '+str(staging))
    out=base/'BEI_Content_Verification_Output'/ticker
    out.mkdir(parents=True,exist_ok=True)
    print(json.dumps(evaluate(base,ticker,csvpath,staging,out),indent=2,ensure_ascii=False))
    print('Output:',out)
if __name__=='__main__':main()
