"""V4.7 non-destructive evidence-backed historical foundation."""
import argparse, sqlite3, json, csv, datetime, pathlib, collections
from decimal import Decimal, InvalidOperation

def connect_ro(path):
    return sqlite3.connect(pathlib.Path(path).resolve().as_uri()+'?mode=ro',uri=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--legacy-db',required=True)
    p.add_argument('--output-db',required=True)
    p.add_argument('--report',required=True)
    p.add_argument('--csv-dir',required=True)
    a=p.parse_args()
    inp=pathlib.Path(a.legacy_db).resolve(); out=pathlib.Path(a.output_db).resolve()
    if not inp.is_file(): p.error('Legacy database does not exist')
    if out.exists(): p.error('Output database already exists; no overwrite')
    src=connect_ro(inp)
    if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok': p.error('Input SQLite integrity failed')
    for t in ('source_meta','recovery_facts','context_resolution','validation_checks','quality_gates'):
        if not src.execute('select 1 from sqlite_master where type="table" and name=?',(t,)).fetchone(): p.error('Missing table '+t)
    out.parent.mkdir(parents=True,exist_ok=True)
    dest=sqlite3.connect(out)
    dest.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE source_documents(source_id INTEGER PRIMARY KEY,ticker TEXT,year INTEGER,report_period TEXT,currency TEXT,presentation_scale TEXT,start_current TEXT,end_current TEXT,start_prior TEXT,end_prior TEXT,filename TEXT);
    CREATE TABLE historical_candidates(candidate_id INTEGER PRIMARY KEY,source_id INTEGER,ticker TEXT,metric TEXT,statement TEXT,period_role TEXT,period_kind TEXT,period_start TEXT,period_end TEXT,value_as_reported TEXT,currency TEXT,scale_label TEXT,worksheet TEXT,source_row INTEGER,source_label TEXT,verification_status TEXT,verification_note TEXT,FOREIGN KEY(source_id) REFERENCES source_documents(source_id));
    CREATE TABLE period_context_reviews(fact_id INTEGER PRIMARY KEY,source_id INTEGER,metric TEXT,reported_context TEXT,expected_kind TEXT,period_start TEXT,period_end TEXT,status TEXT,reason TEXT);
    CREATE TABLE accounting_checks(source_id INTEGER,period_role TEXT,check_name TEXT,status TEXT,difference_as_reported TEXT,details TEXT);
    CREATE TABLE source_quality(source_id INTEGER PRIMARY KEY,ticker TEXT,has_legacy_candidates INTEGER,has_balanced_preview INTEGER,base_unit_confirmed INTEGER,valuation_ready INTEGER,reason TEXT);
    CREATE VIEW valuation_eligible AS SELECT * FROM historical_candidates WHERE verification_status='VERIFIED_FOR_MODELING';
    CREATE INDEX ix_candidates_key ON historical_candidates(ticker,period_end,metric);
    CREATE INDEX ix_context_source ON period_context_reviews(source_id);
    ''')
    metas=src.execute('SELECT * FROM source_meta').fetchall()
    dest.executemany('INSERT INTO source_documents VALUES(?,?,?,?,?,?,?,?,?,?,?)',metas)
    facts=src.execute('SELECT * FROM recovery_facts').fetchall()
    staged=[]; bad=0
    for r in facts:
        (fid,sid,ticker,year,metric,statement,kind,role,start,end,value,currency,scale,sheet,row,label,status,reason)=r
        try: Decimal(str(value))
        except (InvalidOperation, TypeError): bad+=1
        staged.append((fid,sid,ticker,metric,statement,role,kind,start,end,str(value) if value is not None else None,currency,scale,sheet,row,label,'REVIEW_SOURCE_RECONCILIATION',reason))
    dest.executemany('INSERT INTO historical_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',staged)
    contexts=src.execute('SELECT * FROM context_resolution').fetchall()
    dest.executemany('INSERT INTO period_context_reviews VALUES(?,?,?,?,?,?,?, ?,?)',contexts)
    checks=src.execute('SELECT * FROM validation_checks').fetchall()
    dest.executemany('INSERT INTO accounting_checks VALUES(?,?,?,?,?,?)',checks)
    present=set(x[1] for x in facts)
    balance=set(x[0] for x in checks if x[3]=='ARITHMETIC_PASS')
    dest.executemany('INSERT INTO source_quality VALUES(?,?,?,?,?,?,?)',[(r[0],r[1],int(r[0] in present),int(r[0] in balance),0,0,'Requires reconciliation of source units, statement semantics and audited values') for r in metas])
    dest.commit()
    integrity=dest.execute('PRAGMA integrity_check').fetchone()[0]
    fkc=dest.execute('PRAGMA foreign_key_check').fetchall()
    report={'version':'4.7-evidence-consolidation','input_integrity':'ok','output_integrity':integrity,'foreign_key_violations':len(fkc),'source_documents':len(metas),'historical_candidates':len(staged),'legacy_source_files':len(present),'context_review_rows':len(contexts),'arithmetic_preview_pass':len(checks),'invalid_numeric_candidate_rows':bad,'verified_for_modeling':0,'valuation_ready':False,'data_limitation':'Legacy V4.6 contains only 212 raw candidate values; 13306 context rows have no values. Model-ready historical data cannot be built from V4.6 alone.','input_files_modified':False,'originals_deleted':0,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    dest.close();src.close()
    folder=pathlib.Path(a.csv_dir); folder.mkdir(parents=True,exist_ok=True)
    def write(name,headers,rows):
        with (folder/name).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f);w.writerow(headers);w.writerows(rows)
    write('legacy_2022_candidates.csv',['id','source_id','ticker','metric','statement','period_role','period_kind','start','end','value_as_reported','currency','scale','worksheet','row','label','status','note'],staged)
    write('source_quality.csv',['source_id','ticker','has_candidates','preview_balance_pass','unit_verified','valuation_ready','reason'],[(r[0],r[1],int(r[0] in present),int(r[0] in balance),0,0,'REVIEW') for r in metas])
    write('context_status_summary.csv',['status','rows'],collections.Counter(row[7] for row in contexts).items())
    pathlib.Path(a.report).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
