"""BEI Consolidator V4.3: non-destructive metadata and context reconciliation.
Python standard library only. No source file deletion or valuation calculations.
"""
import argparse,sqlite3,os,json,csv,re,datetime,collections
from pathlib import Path

def connect_ro(p):
    if not Path(p).is_file(): raise FileNotFoundError(p)
    return sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True)

def parse_meta(rows):
    out={}
    for label,value in rows:
        k=(label or '').strip().lower(); v=(value or '').strip()
        for name,needle in [('start_current','tanggal awal periode berjalan'),('end_current','tanggal akhir periode berjalan'),('start_prior','tanggal awal periode sebelumnya'),('end_prior','tanggal akhir periode sebelumnya'),('end_prior_fy','tanggal akhir tahun sebelumnya'),('currency_label','mata uang pelaporan'),('presentation_scale','pembulatan yang digunakan')]:
            if needle in k:out[name]=v
    cur=out.get('currency_label','').lower()
    out['currency_code']='USD' if ('usd' in cur or 'dollar amerika' in cur) else ('IDR' if ('idr' in cur or 'rupiah' in cur) else None)
    return out

def resolve(period_label,report_period,meta,expected):
    p=(period_label or '').lower(); relative='unknown'; mode='unknown'
    if 'prior' in p or 'previous' in p: relative='prior'
    elif 'current' in p: relative='current'
    if 'instant' in p:mode='instant'
    elif 'duration' in p:mode='duration'
    begin=end=None
    if relative=='current':begin=meta.get('start_current');end=meta.get('end_current')
    if relative=='prior':begin=meta.get('start_prior');end=meta.get('end_prior')
    if 'priorendyear' in p: end=meta.get('end_prior_fy') or meta.get('end_prior');begin=None;mode='instant'
    if 'priorstartyear' in p: end=meta.get('start_prior');begin=None;mode='instant'
    if 'currentyearinstant' in p:begin=None
    if mode=='instant':begin=None
    # Calendar dates are candidates. A mismatch between declared and expected type cannot be silently repaired.
    status=('REVIEW_CONTEXT_TYPE' if mode!=expected else 'CONTEXT_LABEL_MATCH')
    if not end or (mode=='duration' and not begin):status='REVIEW_MISSING_PERIOD_DATES' if status=='CONTEXT_LABEL_MATCH' else status
    return relative,mode,begin,end,status

def write_csv(path,headers,items):
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(headers);w.writerows(items)

def main():
    ap=argparse.ArgumentParser(description='V4.3 accounting metadata & context diagnostic; input databases read-only')
    ap.add_argument('--staging-db',required=True);ap.add_argument('--modeling-db',required=True)
    ap.add_argument('--output-db',required=True);ap.add_argument('--report',required=True)
    a=ap.parse_args()
    output=Path(a.output_db).resolve();report=Path(a.report).resolve()
    if output.exists():raise SystemExit('Output already exists; choose a different filename. No overwrite permitted: '+str(output))
    if output in (Path(a.staging_db).resolve(),Path(a.modeling_db).resolve()):raise SystemExit('Output must be different from inputs')
    output.parent.mkdir(parents=True,exist_ok=True);report.parent.mkdir(parents=True,exist_ok=True)
    sc=connect_ro(a.staging_db); mc=connect_ro(a.modeling_db)
    out=sqlite3.connect(output)
    out.executescript('''CREATE TABLE metadata(source_id INTEGER PRIMARY KEY,filename TEXT,ticker TEXT,year INT,report_period TEXT,currency_label TEXT,currency_code TEXT,presentation_scale TEXT,start_current TEXT,end_current TEXT,start_prior TEXT,end_prior TEXT,end_prior_fy TEXT,metadata_status TEXT);
CREATE TABLE context_review(id INTEGER PRIMARY KEY,source_id INT,ticker TEXT,statement TEXT,metric TEXT,concept TEXT,reported_context TEXT,declared_type TEXT,expected_type TEXT,relative_period TEXT,period_start_candidate TEXT,period_end_candidate TEXT,review_status TEXT,source_sheet TEXT,source_cell TEXT,raw_value TEXT,currency_code TEXT,scaling_status TEXT);
CREATE TABLE source_quality(source_id INTEGER PRIMARY KEY,filename TEXT,year INT,ticker TEXT,source_status TEXT,fact_count INT,notes TEXT);
CREATE TABLE legacy_2022_preview(source_id INT,source_sheet TEXT,row_num INT,label TEXT,current_value TEXT,prior_value TEXT,review_status TEXT);
CREATE TABLE quality_gates(name TEXT PRIMARY KEY,status TEXT,notes TEXT);
''')
    sources=sc.execute('SELECT id,filename,year,period,ticker FROM source_files ORDER BY id').fetchall()
    lookup={}
    for fid,fn,yr,period,ticker in sources:
        sid=sc.execute("SELECT id FROM sheets WHERE file_id=? AND name='1000000'",(fid,)).fetchone()
        meta={}
        if sid:
            # Only a single metadata sheet per source; avoids scanning all financial cells.
            raw=sc.execute("SELECT address,value FROM cells WHERE sheet_id=? AND (address LIKE 'A%' OR address LIKE 'B%')",(sid[0],)).fetchall()
            cel=dict(raw)
            pairs=[(v,cel.get('B'+addr[1:])) for addr,v in raw if re.fullmatch(r'A\d+',addr)]
            meta=parse_meta(pairs)
        status='FOUND' if (meta.get('start_current') and meta.get('end_current') and meta.get('currency_code')) else 'REVIEW_METADATA'
        out.execute('INSERT INTO metadata VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fid,fn,ticker,yr,period,meta.get('currency_label'),meta.get('currency_code'),meta.get('presentation_scale'),meta.get('start_current'),meta.get('end_current'),meta.get('start_prior'),meta.get('end_prior'),meta.get('end_prior_fy'),status))
        lookup[fid]=meta
    facts=mc.execute('SELECT id,source_id,ticker,statement,metric,concept,reporting_context,context_type,expected_context_type,source_sheet,source_cell,raw_value FROM facts').fetchall()
    statuses=collections.Counter();curcounts=collections.Counter()
    for fid,src,ticker,statement,metric,concept,ctx,ctype,expected,sh,cell,value in facts:
        meta=lookup.get(src,{})
        relative,declared,start,end,status=resolve(ctx,'',meta,expected)
        if declared != ctype:status='REVIEW_INCONSISTENT_TYPE_PARSE'
        scaling='REVIEW_RAW_XBRL_SCALE_NOT_VERIFIED'
        out.execute('INSERT INTO context_review VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fid,src,ticker,statement,metric,concept,ctx,ctype,expected,relative,start,end,status,sh,cell,value,meta.get('currency_code'),scaling))
        statuses[status]+=1;curcounts[meta.get('currency_code') or 'UNKNOWN']+=1
    mapped=collections.Counter(src for _,src,*_ in facts)
    legacy=0
    for fid,fn,yr,period,ticker in sources:
        fc=mapped[fid]; is_legacy=(yr==2022 and fc==0)
        if is_legacy:
            # Preview only financial statement label rows, do NOT map into economic concepts.
            sheetrows=sc.execute("SELECT id,name FROM sheets WHERE file_id=? AND (name LIKE '12%' OR name LIKE '42%' OR name LIKE '13%' OR name LIKE '43%' OR name LIKE '14%' OR name LIKE '44%')",(fid,)).fetchall()
            for sid,sh in sheetrows:
                vals=dict(sc.execute("SELECT address,value FROM cells WHERE sheet_id=? AND (address LIKE 'A%' OR address LIKE 'B%' OR address LIKE 'C%')",(sid,)).fetchall())
                for cell,label in vals.items():
                    m=re.fullmatch(r'A(\d+)',cell)
                    if not m or not label or len(label)>220:continue
                    rn=m.group(1);b=vals.get('B'+rn);c=vals.get('C'+rn)
                    if not (b or c):continue
                    out.execute('INSERT INTO legacy_2022_preview VALUES (?,?,?,?,?,?,?)',(fid,sh,int(rn),label,b,c,'REVIEW_UNMAPPED_LEGACY'))
                    legacy+=1
        out.execute('INSERT INTO source_quality VALUES (?,?,?,?,?,?,?)',(fid,fn,yr,ticker,'NO_MAPPED_FACTS' if fc==0 else 'MAPPED',fc,'LEGACY_2022_PREVIEW_ONLY' if is_legacy else ''))
    gates=[('metadata','REVIEW','source-provided labels, not a verified per-cell unit'),('context','REVIEW','XBRL labels and calendar candidates; mismatches retained'),('legacy_2022','REVIEW','label/value previews are not normalized financial facts'),('bank','BLOCK','bank-specific accounting reconciliation pending'),('valuation','BLOCK','no fact is marked valuation-eligible'),('deletion','DISABLED','no delete function exists')]
    out.executemany('INSERT INTO quality_gates VALUES (?,?,?)',gates);out.commit()
    integrity=out.execute('PRAGMA integrity_check').fetchone()[0]
    overview={'version':'4.3-review','status':'REVIEW_NOT_VALUATION_READY','sources':len(sources),'facts_reviewed':len(facts),'metadata_found':out.execute("SELECT COUNT(*) FROM metadata WHERE metadata_status='FOUND'").fetchone()[0],'context_statuses':dict(statuses),'currencies_fact_rows':dict(curcounts),'legacy_2022_preview_rows':legacy,'sources_without_mapped_facts':sum(mapped[fid]==0 for fid,*_ in sources),'valuation_eligible':0,'integrity_check':integrity,'output_db':str(output),'quality_gates':{name:status for name,status,_ in gates}}
    with report.open('w',encoding='utf8') as f:json.dump(overview,f,indent=2,ensure_ascii=False)
    csvbase=report.parent
    write_csv(csvbase/'v43_metadata_review.csv',['source_id','filename','ticker','year','period','currency','scale','date_begin','date_end','status'],out.execute('SELECT source_id,filename,ticker,year,report_period,currency_code,presentation_scale,start_current,end_current,metadata_status FROM metadata').fetchall())
    write_csv(csvbase/'v43_context_issues.csv',['fact_id','ticker','metric','reporting_context','declared_type','expected_type','start_candidate','end_candidate','status'],out.execute("SELECT id,ticker,metric,reported_context,declared_type,expected_type,period_start_candidate,period_end_candidate,review_status FROM context_review WHERE review_status!='CONTEXT_LABEL_MATCH'").fetchall())
    write_csv(csvbase/'v43_legacy_2022_preview.csv',['source_id','sheet','row','label','current','prior','status'],out.execute('SELECT * FROM legacy_2022_preview').fetchall())
    print(json.dumps(overview,indent=2,ensure_ascii=False));out.close();sc.close();mc.close()
if __name__=='__main__':main()
