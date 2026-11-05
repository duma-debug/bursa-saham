"""BEI Content Dashboard: read-only evidence-based content analytics."""
from __future__ import annotations
import csv
import math
import sqlite3
from pathlib import Path
from collections import defaultdict

METRICS = {
    'revenue': 'Pendapatan', 'gross_profit':'Laba bruto',
    'net_income_parent':'Laba pemilik induk', 'net_income_total':'Laba bersih konsolidasi',
    'cashflow_operating':'Arus kas operasi', 'cashflow_investing':'Arus kas investasi',
    'cashflow_financing':'Arus kas pendanaan', 'capex_ppe_outflow':'Belanja modal aset tetap',
    'total_assets':'Total aset', 'total_liabilities':'Total liabilitas',
    'total_equity':'Total ekuitas', 'cash_equivalents':'Kas dan setara kas',
    'eps_basic':'Laba per saham (EPS)', 'cost_of_revenue':'Beban pokok pendapatan',
    'current_assets':'Aset lancar', 'current_liabilities':'Liabilitas lancar',
}
DURATION = {'revenue','gross_profit','net_income_parent','net_income_total','cashflow_operating',
'cashflow_investing','cashflow_financing','capex_ppe_outflow','cost_of_revenue'}
ROMAN={'I':1,'II':2,'III':3,'IV':4}

def database_at(base):
    base=Path(base)
    for p in (base/'BEI_Master_Output'/'BEI_Financial_Master.db',base/'BEI_Financial_Master.db',base/'financial_modeling_v4_1.db'):
        if p.is_file():return p
    raise FileNotFoundError('Database tidak ditemukan. Periksa folder BEI_Master_Output atau financial_modeling_v4_1.db.')

def connect_ro(path):
    return sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro',uri=True)

def get_data(path, ticker):
    ticker=ticker.strip().upper()
    if not ticker.isalnum() or not 3<=len(ticker)<=6:raise ValueError('Kode saham harus berupa 3–6 huruf/angka.')
    with connect_ro(path) as con:
        con.row_factory=sqlite3.Row
        master=bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_facts'").fetchone())
        if master:
            query='''SELECT f.fact_id AS id, f.source_id, f.ticker, f.report_year,f.report_period,f.statement,f.metric,f.raw_value,
            f.reporting_context, f.source_sheet,f.source_cell, s.filename, s.sha256,
            m.currency, m.presentation_scale,m.start_current,m.end_current,m.start_prior,m.end_prior
            FROM financial_facts f JOIN source_catalog s on s.source_id=f.source_id
            LEFT JOIN source_metadata m ON m.source_id=f.source_id
            WHERE f.ticker=? AND (s.duplicate_of IS NULL OR s.duplicate_of='')'''
        else:
            query='''SELECT f.id,f.source_id,f.ticker,f.report_year,f.report_period,f.statement,f.metric,f.raw_value,
            f.reporting_context,f.source_sheet,f.source_cell,s.filename,s.sha256,
            '' AS currency, '' AS presentation_scale, '' AS start_current, '' AS end_current,
            '' AS start_prior, '' AS end_prior
            FROM facts f JOIN source_catalog s on s.source_id=f.source_id
            WHERE f.ticker=? AND (s.duplicate_of IS NULL OR s.duplicate_of='')'''
        records=[dict(r) for r in con.execute(query,(ticker,))]
        # Legacy 2022: extra 2021 and 2022 rows recovered from B/C comparative columns.
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_xbrl_facts'").fetchone():
            legacy_query = """SELECT NULL as id, l.source_id, l.ticker,l.report_year,l.report_period,
                 l.statement,l.metric,l.raw_value,l.reporting_context,l.source_sheet,l.source_cell,
                 s.filename,s.sha256,m.currency,m.presentation_scale,
                 m.start_current,m.end_current,m.start_prior,m.end_prior
                 FROM legacy_xbrl_facts l JOIN source_catalog s ON s.source_id=l.source_id
                 LEFT JOIN source_metadata m ON m.source_id=l.source_id
                 WHERE l.ticker=? AND (s.duplicate_of IS NULL OR s.duplicate_of='')"""
            records.extend(dict(r) for r in con.execute(legacy_query,(ticker,)))
    for r in records:
        try: r['value']=float(r['raw_value'])
        except (ValueError,TypeError):r['value']=None
    return records

def available_tickers(path):
    with connect_ro(path) as c:
        table='financial_facts' if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='financial_facts'").fetchone() else 'facts'
        return [x[0] for x in c.execute(f'SELECT DISTINCT ticker FROM {table} WHERE ticker IS NOT NULL ORDER BY ticker')]

def period_label(v):
    v=str(v or '')
    return 'FY' if v.lower() in ('tahunan','fy','annual') else 'Q'+str(ROMAN[v]) if v in ROMAN else v

def comparative_pairs(records):
    # Each calculation uses current-vs-prior from exactly the same statement/filing and context pair.
    buckets=defaultdict(list)
    for r in records:
        context=r['reporting_context'] or ''
        if r['metric'] not in DURATION or context not in ('CurrentYearDuration','PriorYearDuration'):continue
        key=(r['source_id'],r['metric'])
        buckets[key].append(r)
    pairs=[]
    for key,rr in buckets.items():
        curr=[x for x in rr if x['reporting_context']=='CurrentYearDuration']
        prior=[x for x in rr if x['reporting_context']=='PriorYearDuration']
        if len(curr)!=1 or len(prior)!=1:continue
        c,p=curr[0],prior[0]
        if c['value'] is None or p['value'] is None or p['value']==0:continue
        y=(c['value']/p['value']-1)*100
        if not math.isfinite(y):continue
        pairs.append({'ticker':c['ticker'], 'metric':c['metric'],'label':METRICS.get(c['metric'],c['metric']),
            'year':int(c['report_year']),'period':period_label(c['report_period']),
            'currency':c.get('currency') or 'BELUM DIVERIFIKASI',
            'prior_raw':p['raw_value'],'current_raw':c['raw_value'],'yoy':y,
            'filename':c['filename'],'source_current':f"{c['source_sheet']}!{c['source_cell']}",
            'source_prior':f"{p['source_sheet']}!{p['source_cell']}",
            'status':'REVIEW — sumber XBRL; PDF/satuan belum direkonsiliasi',
            'source_id':c['source_id']})
    # Avoid numeric conflicts masked by duplicated mapping; retain all filing versions in table.
    return sorted(pairs,key=lambda x:(x['year'],x['period'],x['label']))

def latest_pairs(pairs):
    years=sorted({(r['year'],r['period']) for r in pairs}, key=lambda k:(k[0],period_order(k[1])))
    if not years:return [],None
    # preference: last quarter/fiscal period by filing date
    latest=max(years,key=lambda k:(k[0],period_order(k[1])))
    return [x for x in pairs if (x['year'],x['period'])==latest],latest

def period_order(v):
    return {'Q1':1,'Q2':2,'Q3':3,'Q4':4,'FY':5}.get(v,0)

def article(ticker,pairs,latest):
    intro=f'# {ticker}: Apa yang Berubah dalam Laporan Keuangan Terbaru?\n\n'
    intro+='**DRAF RISET — JANGAN DIPUBLIKASIKAN TANPA VERIFIKASI SUMBER.**\n\n'
    if not latest:return intro+'Data komparatif yang memenuhi aturan awal belum tersedia.\n'
    y,period=latest
    lp=[x for x in pairs if (x['year'],x['period'])==latest]
    by_metric={x['metric']:x for x in lp}
    intro+=f'Perbandingan awal {period} {y} dengan periode setara tahun {y-1} dari **file laporan yang sama**.\n\n'
    for metric in ('revenue','gross_profit','net_income_parent','cashflow_operating'):
        if metric in by_metric:
            x=by_metric[metric]
            intro+=f'- **{x["label"]}:** {x["yoy"]:+.1f}% YoY (indikatif; perlu rekonsiliasi).\n'
    intro+='\n## Apa yang perlu diselidiki?\n\n'
    intro+='Periksa apakah perubahan laba berasal dari pendapatan, marjin, keuntungan nonoperasional, atau faktor lain. Bandingkan pertumbuhan laba dengan arus kas operasional dan kebutuhan investasi. Jangan menarik kesimpulan nilai wajar dari YoY saja.\n\n'
    intro+='## Data dan batasan\n\n'
    intro+='Angka dihitung dari sel XBRL yang berasal dari pasangan kolom berjalan dan pembanding dalam satu laporan. Belum ada verifikasi independen terhadap PDF, mata uang per akun, restatement, atau konsolidasi.\n\n'
    if lp:
        intro+='**Sumber:** '+lp[0]['filename']+'\n'
    return intro

def export_csv(dest, rows):
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    if not rows:return
    with dest.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
