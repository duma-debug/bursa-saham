#!/usr/bin/env python3
"""BEI Master QuickStart: consolidate evidence without claiming valuation readiness."""
import argparse,csv,datetime,json,sqlite3, pathlib,collections, re
P=pathlib.Path

def ro(path):
    return sqlite3.connect(f'file:{P(path).resolve().as_posix()}?mode=ro',uri=True)
def writecsv(path,headers,rows):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(headers);w.writerows(rows)
def main():
    a=argparse.ArgumentParser()
    a.add_argument('--base',default=r'C:\Analisis_Saham_BEI')
    a.add_argument('--ticker',default='AALI')
    args=a.parse_args(); base=P(args.base); ticker=args.ticker.upper().strip()
    if not re.fullmatch('[A-Z0-9]{3,8}',ticker):raise SystemExit('Ticker invalid')
    names=['financial_production.db','financial_modeling_v4_1.db','financial_legacy_v4_6.db']
    for n in names:
        if not (base/n).is_file():raise SystemExit(f'Missing {base/n}')
    out=base/'BEI_Master_Output';out.mkdir(exist_ok=True)
    dest=out/'BEI_Financial_Master.db'
    if dest.exists():raise SystemExit(f'{dest} already exists; no overwrite. Rename or archive this output before rebuilding.')
    m=ro(base/names[1]);l=ro(base/names[2]);s=ro(base/names[0]); d=sqlite3.connect(dest)
    try:
        d.executescript('''PRAGMA foreign_keys=ON;
          CREATE TABLE source_catalog(source_id INTEGER PRIMARY KEY,filename TEXT,sha256 TEXT,report_year INTEGER,report_period TEXT,ticker TEXT,duplicate_of INTEGER,source_status TEXT);
          CREATE TABLE source_metadata(source_id INTEGER PRIMARY KEY,ticker TEXT,report_year INTEGER,report_period TEXT,currency TEXT,presentation_scale TEXT,start_current TEXT,end_current TEXT,start_prior TEXT,end_prior TEXT,source_filename TEXT);
          CREATE TABLE financial_facts(fact_id INTEGER PRIMARY KEY,source_id INTEGER,ticker TEXT,report_year INTEGER,report_period TEXT,statement TEXT,metric TEXT,concept TEXT,reporting_context TEXT,context_relative TEXT,reported_context_type TEXT,expected_context_type TEXT,raw_value TEXT,source_sheet TEXT,source_cell TEXT,staging_fact_id INTEGER,check_status TEXT,review_reason TEXT,currency_metadata TEXT,period_start TEXT,period_end TEXT,quality_status TEXT NOT NULL DEFAULT 'REVIEW',valuation_eligible INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE legacy_candidates(legacy_id INTEGER PRIMARY KEY,source_id INTEGER,ticker TEXT,report_year INTEGER,metric TEXT,statement TEXT,period_kind TEXT,period_role TEXT,period_start TEXT,period_end TEXT,value_presentation TEXT,currency TEXT,presentation_scale TEXT,source_sheet TEXT,source_row INTEGER,source_label TEXT,status TEXT,reason TEXT);
          CREATE TABLE context_review(fact_id INTEGER PRIMARY KEY,period_start TEXT,period_end TEXT,status TEXT,reason TEXT);
          CREATE TABLE run_manifest(field TEXT PRIMARY KEY,value TEXT);
          CREATE INDEX idx_facts_ticker_period ON financial_facts(ticker,report_year,report_period,metric);
          CREATE INDEX idx_legacy_ticker ON legacy_candidates(ticker,report_year,metric);''')
        d.executemany('INSERT INTO source_catalog VALUES (?,?,?,?,?,?,?,?)',m.execute('SELECT source_id,filename,sha256,year,report_period,ticker,duplicate_of,source_status FROM source_catalog'))
        d.executemany('INSERT INTO source_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?)',l.execute('SELECT source_id,ticker,year,report_period,currency,presentation_scale,start_current,end_current,start_prior,end_prior,source_filename FROM source_meta'))
        d.executemany('INSERT INTO context_review VALUES (?,?,?,?,?)',l.execute('SELECT fact_id,period_start,period_end,status,reason FROM context_resolution'))
        d.executemany('INSERT INTO legacy_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',l.execute('SELECT * FROM recovery_facts'))
        data=m.execute('''SELECT f.id,f.source_id,f.ticker,f.report_year,f.report_period,f.statement,f.metric,f.concept,f.reporting_context,f.context_relative,f.context_type,f.expected_context_type,f.raw_value,f.source_sheet,f.source_cell,f.staging_fact_id,f.check_status,f.review_reason,sm.currency,cr.period_start,cr.period_end,'REVIEW',0 FROM facts f LEFT JOIN (SELECT source_id,currency FROM source_meta) sm ON f.source_id=sm.source_id LEFT JOIN (SELECT fact_id,period_start,period_end FROM context_resolution) cr ON f.id=cr.fact_id''') if False else None
        metadata={r[0]:r[1] for r in l.execute('SELECT source_id,currency FROM source_meta')}
        contexts={r[0]:(r[1],r[2]) for r in l.execute('SELECT fact_id,period_start,period_end FROM context_resolution')}
        rows=[]
        for f in m.execute('SELECT id,source_id,ticker,report_year,report_period,statement,metric,concept,reporting_context,context_relative,context_type,expected_context_type,raw_value,source_sheet,source_cell,staging_fact_id,check_status,review_reason FROM facts'):
            start,end=contexts.get(f[0],(None,None));rows.append(tuple(f)+(metadata.get(f[1]),start,end,'REVIEW',0))
        d.executemany('INSERT INTO financial_facts VALUES ('+','.join(['?']*23)+')',rows)
        for k,v in [('created_utc',datetime.datetime.now(datetime.timezone.utc).isoformat()),('raw_source_path',str(base/names[0])),('model_source_path',str(base/names[1])),('legacy_source_path',str(base/names[2])),('purpose','content preparation / historical data staging'),('valuation_ready','false'),('source_files_copied','metadata only; raw cells remain in financial_production.db')]:d.execute('INSERT INTO run_manifest VALUES (?,?)',(k,v))
        d.commit()
        check=d.execute('PRAGMA integrity_check').fetchone()[0]
        if check!='ok':raise RuntimeError(check)
        raw=d.execute('''SELECT f.ticker,f.report_year,f.report_period,f.metric,f.raw_value,f.currency_metadata,f.reporting_context,f.source_sheet,f.source_cell,sc.filename,f.review_reason FROM financial_facts f JOIN source_catalog sc ON sc.source_id=f.source_id WHERE f.ticker=? AND f.context_relative='current' AND sc.duplicate_of IS NULL ORDER BY f.report_year,f.report_period,f.metric''',(ticker,)).fetchall()
        writecsv(out/f'{ticker}_content_snapshot_REVIEW.csv',['ticker','report_year','report_period','metric','raw_value_NOT_NORMALIZED','source_currency_metadata','xbrl_context','sheet','cell','source_filename','review_reason'],raw)
        legacy=d.execute('''SELECT ticker,report_year,metric,value_presentation,currency,presentation_scale,period_role,source_sheet,source_row,source_label,status FROM legacy_candidates WHERE ticker=? AND period_role='current' ORDER BY report_year,metric''',(ticker,)).fetchall()
        writecsv(out/f'{ticker}_legacy_2022_REVIEW.csv',['ticker','report_year','metric','value_in_source_presentation_units','currency','presentation_scale','period_role','source_sheet','source_row','source_label','status'],legacy)
        stats={'source_files':d.execute('select count(*) from source_catalog').fetchone()[0],'duplicate_files':d.execute('select count(*) from source_catalog where duplicate_of is not null').fetchone()[0],'facts':d.execute('select count(*) from financial_facts').fetchone()[0],'legacy_candidates':d.execute('select count(*) from legacy_candidates').fetchone()[0],'valuation_eligible':0,'integrity_check':check,'ticker_export':ticker,'snapshot_rows':len(raw),'legacy_ticker_rows':len(legacy),'status':'REVIEW_ONLY'}
        (out/'master_report.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
        (out/f'{ticker}_article_brief.md').write_text(f'''# Bahan artikel {ticker} — DRAF RISET, BUKAN ANGKA SIAP PUBLIKASI

**Fokus:** Tren laporan keuangan dan pertanyaan investasi untuk {ticker}.\n
## Poin untuk artikel

1. Bagaimana perkembangan pendapatan, laba, dan arus kas operasional antarperiode?
2. Apakah belanja modal dapat dibiayai dari arus kas operasi?
3. Bagaimana perkembangan posisi kas, utang, dan ekuitas?
4. Apakah harga saham saat ini mencerminkan prospek tersebut? *Belum dinilai: membutuhkan data harga, saham beredar, dan asumsi valuasi yang tervalidasi.*

## Status data dan cara pakai

- Ada **{len(raw)}** baris fakta konteks berjalan hasil ekspor V4.1 dan **{len(legacy)}** kandidat dari file historis 2022.
- Kolom `raw_value_NOT_NORMALIZED` adalah nilai mentah XBRL, **bukan** otomatis Rp juta; jangan gabungkan atau hitung growth tanpa verifikasi unit dan periode.
- Kolom untuk fakta 2022 memakai *presentation units*; tidak dapat langsung digabung dengan angka mentah tanpa konversi terverifikasi.
- Lakukan cross-check dengan Excel XBRL dan laporan PDF audited, lalu tambahkan tanggal publikasi, konteks laba konsolidasian, dan sumber dalam artikel.
- Tidak ada rekomendasi beli/jual atau fair value otomatis dalam paket ini.

## Judul artikel yang bisa dikembangkan

**{ticker}: Apakah pertumbuhan laba didukung arus kas dan kekuatan neraca?**

Contoh lead: *Sebelum memutuskan apakah saham {ticker} menarik, investor perlu melihat tiga hal secara bersamaan: kemampuan bisnis menghasilkan laba, konversinya menjadi arus kas, dan kebutuhan modal untuk mempertahankan pertumbuhan.*
''',encoding='utf-8')
        print(json.dumps({'output_db':str(dest),'report':str(out/'master_report.json'),**stats},indent=2))
    finally:
        d.close();m.close();l.close();s.close()
if __name__=='__main__':main()
