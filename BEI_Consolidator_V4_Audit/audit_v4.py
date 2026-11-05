import argparse,csv,json,sqlite3,collections,re,pathlib,datetime

def connect_ro(path):
    return sqlite3.connect('file:'+pathlib.Path(path).resolve().as_posix()+'?mode=ro',uri=True)
def writecsv(path, rows, fields):
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser(description='Read-only BEI V4 audit. Does not normalize figures or delete sources.')
    ap.add_argument('--foundation-db',required=True);ap.add_argument('--staging-db',required=True);ap.add_argument('--output-dir',required=True)
    a=ap.parse_args();out=pathlib.Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    f=connect_ro(a.foundation_db);s=connect_ro(a.staging_db)
    f.row_factory=sqlite3.Row;s.row_factory=sqlite3.Row
    files=[dict(x) for x in f.execute('select * from source_inventory')]
    findings=[dict(x) for x in f.execute('select * from audit_findings')]
    facts={r['source_id']:r['n'] for r in f.execute('select source_id,count(*) n from normalized_facts group by source_id')}
    reasons=collections.defaultdict(list)
    for r in findings: reasons[r['source_id']].append(r['rule'])
    inventory=[]
    for item in files:
        sid=item['source_id']; item['normalized_fact_count']=facts.get(sid,0);item['audit_rules']=';'.join(sorted(set(reasons.get(sid,[]))))
        item['mapping_status']='REVIEW' if facts.get(sid,0) else 'NO_MATCHED_FACTS'
        if item['duplicate_of']: item['mapping_status']='EXACT_DUPLICATE'
        inventory.append(item)
    writecsv(out/'source_audit.csv',inventory,['source_id','filename','year','period','ticker','sheet_count','cell_count','duplicate_of','normalized_fact_count','mapping_status','audit_rules'])
    issues=[]
    for item in findings:
        sid=item['source_id']; src=files[sid-1] if 0<sid<=len(files) and files[sid-1]['source_id']==sid else next((x for x in files if x['source_id']==sid),{})
        issues.append(dict(filename=src.get('filename',''),source_id=sid,**{k:item[k] for k in ['level','rule','details']}))
    writecsv(out/'audit_findings.csv',issues,['filename','source_id','level','rule','details'])
    # Read Indonesian / English general-information labels directly: never infer monetary scale from year.
    meta=[]
    sources={x['id']:dict(x) for x in s.execute('select id,filename from source_files')}
    for fid,src in sources.items():
        rec={'file_id':fid,'filename':src['filename'],'presentation_currency':'','rounding_label':'','report_start':'','report_end':''}
        for row in s.execute("select a.value label,b.value val from sheets sh join cells a on a.sheet_id=sh.id and a.address like 'A%' left join cells b on b.sheet_id=sh.id and b.address='B'||substr(a.address,2) where sh.file_id=? and sh.name='1000000' and (lower(a.value) like '%mata uang pelaporan%' or lower(a.value) like '%pembulatan yang digunakan%' or lower(a.value) like '%tanggal awal periode berjalan%' or lower(a.value) like '%tanggal akhir periode berjalan%')",(fid,)):
            lab=row['label'].lower(); val=row['val'] or ''
            if 'mata uang' in lab:rec['presentation_currency']=val
            if 'pembulatan' in lab:rec['rounding_label']=val
            if 'tanggal awal' in lab:rec['report_start']=val
            if 'tanggal akhir periode berjalan' in lab:rec['report_end']=val
        meta.append(rec)
    writecsv(out/'source_accounting_metadata.csv',meta,['file_id','filename','presentation_currency','rounding_label','report_start','report_end'])
    # 2022 legacy schema samples; preserve actual raw XBRL cell coordinates.
    legacy=[]
    for item in files:
        if item['year']!=2022 or item['normalized_fact_count'] or item['duplicate_of']:continue
        fid=item['source_id']
        for r in s.execute("select sh.name sheet,c.address,c.value from sheets sh join cells c on c.sheet_id=sh.id where sh.file_id=? and sh.name in ('1210000','1321000','1510000') and c.address like 'A%' order by sh.name,c.address limit 100",(fid,)):
            if not r['value'] or len(r['value'].strip())<4:continue
            legacy.append({'filename':item['filename'],'sheet':r['sheet'],'address':r['address'],'label':r['value']})
    writecsv(out/'legacy_2022_labels.csv',legacy,['filename','sheet','address','label'])
    pdf=[dict(x) for x in f.execute('select * from pdf_sources')];writecsv(out/'pdf_links.csv',pdf,['filename','ticker','report_year','report_period','link_status','source_id','absolute_path'])
    total=len(files);unique=len({x['sha256'] for x in files});unmatched=sum(not x['normalized_fact_count'] for x in files)
    summary={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_files':total,'unique_sha256':unique,'exact_duplicate_files':total-unique,'no_matched_facts':unmatched,'balance_imbalances':sum(x['rule']=='BALANCE_SHEET_CHECK' for x in findings),'accounting_metadata_rows':len(meta),'pdf_links':collections.Counter(x['link_status'] for x in pdf),'quality_status':'AUDIT_ONLY_NOT_VALUATION_READY','source_files_deleted':0,'original_databases_modified':False,'next_steps':['Map legacy 2022 Indonesian taxonomy to concepts with manual review','Analyze bank-sector accounting totals and reconcile balance checks','Verify financial-statement scale per source, without multiplying twice','Validate YTD and instant reporting before TTM','Expand income and cash flow line items with provenance']}
    (out/'audit_summary.json').write_text(json.dumps(summary,indent=2,default=dict,ensure_ascii=False),encoding='utf-8');print(json.dumps(summary,indent=2,default=dict,ensure_ascii=False))
if __name__=='__main__': main()
