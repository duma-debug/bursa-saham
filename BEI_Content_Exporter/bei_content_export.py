#!/usr/bin/env python3
"""BEI Content Exporter: same-filing current/comparative YoY; conservative review-only output.
No DB mutation, no deletion, no fabricated currency scaling or valuation.
Python 3.10+, standard library only; matplotlib optional for PNG charts.
"""
import argparse, csv, json, pathlib, math, re, collections
from decimal import Decimal, InvalidOperation

METRICS={
 'revenue':'Pendapatan', 'gross_profit':'Laba bruto',
 'net_income_parent':'Laba pemilik entitas induk',
 'net_income_total':'Laba bersih konsolidasian',
 'cashflow_operating':'Arus kas operasi',
 'cashflow_investing':'Arus kas investasi',
 'cashflow_financing':'Arus kas pendanaan',
 'capex_ppe_outflow':'Belanja aset tetap',
 'cost_of_revenue':'Beban pokok pendapatan',
 'eps_basic':'EPS dasar',
}
METRIC_ORDER=['revenue','gross_profit','net_income_parent','cashflow_operating','capex_ppe_outflow','eps_basic']
DURATION_METRICS=set(METRICS) - {'eps_basic'}
CSV_COLUMNS=['ticker','filing','filing_period','metric','label','year_prior','year_current','period_end_prior','period_end_current',
             'source_currency','source_presentation_scale','prior_raw','current_raw','yoy_pct_review',
             'status','issues','source_prior_cell','source_current_cell']

def read_csv(p):
    with p.open('r', encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def dec(text):
    try:
        d=Decimal(str(text).strip())
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError, TypeError): return None

def date_ok(a,b):
    # Compare parallel YTD windows by MM-DD; all fiscal period labels must also agree.
    if not (a and b and len(a)==10 and len(b)==10):return False
    return a[5:] == b[5:]

def compute_pairs(rows,ticker):
    # Group BY SAME filing+metric+report-period; cannot silently mix sources or years.
    buckets=collections.defaultdict(lambda:{'CURRENT':[],'COMPARATIVE':[]})
    for r in rows:
        if r['ticker'].upper()!=ticker: continue
        if r['metric'] not in METRICS: continue
        if r.get('duplicate_filing')=='1': continue
        if r.get('context_kind')!='DURATION':
            # Some XBRL cash flow duration amounts carry instant labels. Hold for review;
            # calculations may still be shown only with explicit REVIEW flags.
            if r['metric'] not in ('cashflow_operating','cashflow_investing','cashflow_financing','capex_ppe_outflow'): continue
        role=r.get('source_role','')
        if role not in ('CURRENT','COMPARATIVE'):continue
        key=(r['source_filename'],r['filing_period'],r['metric'])
        buckets[key][role].append(r)
    result=[]
    for (filing,period,metric), both in sorted(buckets.items()):
        if len(both['CURRENT'])!=1 or len(both['COMPARATIVE'])!=1: continue
        cur=both['CURRENT'][0]; pri=both['COMPARATIVE'][0]
        reasons=[]
        try:
            cy=int(cur['data_fiscal_year']);py=int(pri['data_fiscal_year'])
            if cy-py!=1:reasons.append('FISCAL_YEAR_GAP')
        except ValueError:reasons.append('INVALID_FISCAL_YEAR');cy=py=0
        if not date_ok(cur['period_end'],pri['period_end']):reasons.append('YTD_WINDOWS_NOT_PARALLEL')
        if not cur['period_end'] or not pri['period_end']:reasons.append('DATE_MISSING')
        if cur['data_period_label']!=pri['data_period_label']: reasons.append('PERIOD_LABEL_MISMATCH')
        currency=cur.get('currency_metadata','')
        if not currency or pri.get('currency_metadata','') != currency:reasons.append('CURRENCY_MISMATCH')
        scale=cur.get('presentation_scale_metadata','')
        if scale!=pri.get('presentation_scale_metadata',''):reasons.append('SCALE_MISMATCH')
        curv=dec(cur['raw_value_NOT_NORMALIZED']);prv=dec(pri['raw_value_NOT_NORMALIZED'])
        if curv is None or prv is None: reasons.append('NONNUMERIC')
        if prv is not None and prv<=0: reasons.append('ZERO_OR_NEGATIVE_BASE')
        sourceflags=';'.join([cur.get('review_flags',''),pri.get('review_flags','')])
        if 'XBRL_TYPE_MISMATCH' in sourceflags: reasons.append('XBRL_CONTEXT_REVIEW')
        valid=not any(x in reasons for x in ('FISCAL_YEAR_GAP','INVALID_FISCAL_YEAR','YTD_WINDOWS_NOT_PARALLEL',
             'DATE_MISSING','PERIOD_LABEL_MISMATCH','CURRENCY_MISMATCH','SCALE_MISMATCH','NONNUMERIC','ZERO_OR_NEGATIVE_BASE'))
        yoy=float((curv/prv-Decimal(1))*Decimal(100)) if valid else None
        result.append(dict(zip(CSV_COLUMNS,[ticker,filing,period,metric,METRICS[metric],py,cy,pri['period_end'],cur['period_end'],
          currency,scale,pri['raw_value_NOT_NORMALIZED'],cur['raw_value_NOT_NORMALIZED'],f'{yoy:.2f}' if yoy is not None else '',
          'REVIEW_COMPARABLE_SAME_FILING' if valid else 'BLOCK_NOT_COMPARABLE',';'.join(dict.fromkeys(reasons)) or 'UNIT_NOT_INDEPENDENTLY_VERIFIED',
          pri['source_sheet']+'!'+pri['source_cell'],cur['source_sheet']+'!'+cur['source_cell']])) )
    return result

def fmt_pct(v):return f'{float(v):+.1f}%'.replace('.',',')

def generate_article(ticker, pairs, out):
    pref=[p for p in pairs if p['status'].startswith('REVIEW_') and p['metric'] in METRIC_ORDER and p['yoy_pct_review']]
    # Prefer highest fiscal year latest quarter, not comparing FY with YTD.
    candidate=sorted(pref,key=lambda x:(int(x['year_current']), {'Tahunan':4,'III':3,'II':2,'I':1}.get(x['filing_period'],0)),reverse=True)
    newest=candidate[0] if candidate else None
    block=[]
    if newest:
        period=newest['filing_period'];yr=newest['year_current']
        lines=[p for p in pref if p['filing']==newest['filing']]
        names={'III':'sembilan bulan','II':'enam bulan','I':'tiga bulan','Tahunan':'setahun penuh'}
        title=f'{ticker}: Apa Cerita di Balik Perubahan Laba dan Arus Kas {names.get(period,period)} {yr}?'
        block=[f'# DRAF REVIEW — {title}','',
               '> **BELUM UNTUK PUBLIKASI.** Angka YoY di bawah berasal dari pasangan periode komparatif dalam satu filing XBRL. Satuan, klasifikasi konteks dan angka keuangan belum direkonsiliasi terhadap laporan resmi.','',
               f'Berdasarkan ekstraksi sementara laporan {ticker} untuk periode {names.get(period,period)} {yr}, terdapat beberapa perkembangan yang patut ditelusuri lebih jauh.','',
               '## Angka awal yang perlu diverifikasi','',
               '| Indikator | Perubahan YoY (provisional) |','|---|---:|']
        for p in lines:
            if p['metric'] in METRIC_ORDER:
                block.append(f"| {p['label']} | {fmt_pct(p['yoy_pct_review'])} |")
        block.extend(['','## Pertanyaan analitis','',
          'Apakah perubahan pendapatan didukung volume atau harga jual? Apakah margin berubah karena efisiensi operasional atau faktor nonberulang?',
          'Bagaimana arus kas operasi dibandingkan dengan laba, dan apa pengaruh perubahan modal kerja atau belanja modal?',
          'Periksa catatan laporan keuangan dan harga saham pada tanggal analisis sebelum membahas valuasi.','',
          '## Sumber dan batasan','',f"File sumber: `{newest['filing']}`.",
          'Metode: pasangan current vs comparative dari file yang sama; growth = current / previous − 1.',
          'Tidak ada asumsi konversi Rupiah penuh/jutaan dan tidak ada rekomendasi investasi.',''])
    else: block=[f'# {ticker} — Data belum cukup untuk draf kuantitatif','',
          'Tidak ada pasangan periode berjalan dan pembanding yang memenuhi syarat kesebandingan minimum.','']
    (out/f'{ticker}_DRAF_ARTIKEL_REVIEW.md').write_text('\n'.join(block),encoding='utf-8')

def chart(ticker,rows,out):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:return False
    for period in ('Tahunan','II','III'):
        valid=[x for x in rows if x['status'].startswith('REVIEW_') and x['filing_period']==period and x['metric'] in METRIC_ORDER]
        if not valid:continue
        # latest one filing only for period
        latest=sorted({x['filing'] for x in valid})[-1]
        valid=[x for x in valid if x['filing']==latest]
        order={v:i for i,v in enumerate(METRIC_ORDER)}
        valid.sort(key=lambda x:order.get(x['metric'],999))
        labels=[x['label'] for x in valid]; vals=[float(x['yoy_pct_review']) for x in valid]
        fig,ax=plt.subplots(figsize=(10,5.3))
        yy=range(len(labels)); bars=ax.barh(list(yy),vals)
        ax.set_yticks(list(yy),labels)
        ax.invert_yaxis();ax.axvline(0,linewidth=0.8)
        ax.set_xlabel('Perubahan YoY (%) — PROVISIONAL')
        ax.set_title(f'{ticker} | {period} | {valid[0]["year_current"]} vs {valid[0]["year_prior"]} (satu filing)')
        maxabs=max(abs(v) for v in vals) or 1
        ax.set_xlim(min(-maxabs*.25, min(vals)-maxabs*.2),max(vals)+maxabs*.35)
        for bar,v in zip(bars,vals):
            ax.text(v+(maxabs*.025 if v>=0 else -maxabs*.025),bar.get_y()+bar.get_height()/2,f'{v:+.1f}%',
                    va='center',ha='left' if v>=0 else 'right',fontsize=9)
        fig.text(.5,.025,'REVIEW • Belum diverifikasi untuk publikasi • Investor Mandiri — bahan riset',
                 ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.06,1,1))
        fig.savefig(out/f'{ticker}_{period}_YOY_REVIEW.png',dpi=160)
        plt.close(fig)
    return True

def main():
    p=argparse.ArgumentParser(description='BEI Content Exporter (REVIEW only; no deletion or DB writes)')
    p.add_argument('--base',default=r'C:\Analisis_Saham_BEI');p.add_argument('--ticker',default='AALI')
    p.add_argument('--input',default=None,help='Optional selected-period CSV')
    args=p.parse_args();ticker=args.ticker.strip().upper()
    if not re.fullmatch('[A-Z0-9]{3,8}',ticker):raise SystemExit('Invalid ticker')
    base=pathlib.Path(args.base)
    inputp=pathlib.Path(args.input) if args.input else base/'BEI_Master_Output'/f'{ticker}_periods_SELECTED_REVIEW.csv'
    if not inputp.is_file():raise SystemExit('CSV not found: '+str(inputp)+'\nRun BEI Period Exporter first.')
    output=base/'BEI_Content_Output'/ticker;output.mkdir(parents=True,exist_ok=True)
    rows=compute_pairs(read_csv(inputp),ticker)
    with (output/f'{ticker}_YOY_REVIEW.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=CSV_COLUMNS);w.writeheader();w.writerows(rows)
    generate_article(ticker,rows,output)
    has_charts=chart(ticker,rows,output)
    report={'ticker':ticker,'status':'REVIEW_ONLY_NO_PUBLICATION_APPROVAL','input':str(inputp),
            'pairs':len(rows),'review_comparable':sum(x['status'].startswith('REVIEW_') for x in rows),
            'blocked':sum(x['status'].startswith('BLOCK_') for x in rows),
            'charts_generated':has_charts,'output_directory':str(output),
            'warnings':['YoY calculated only from same-filing current/prior paired amounts','No unit conversion for absolute amounts',
                        'No model/valuation approval','XBRL context mismatches remain REVIEW',
                        'No original source or SQLite DB modified or deleted']}
    (output/f'{ticker}_CONTENT_REPORT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
