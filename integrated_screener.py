#!/usr/bin/env python3
"""Integrated BEI stock screener V1. Python standard library, READ-ONLY SQLite.
Usage: python integrated_screener.py --db pasar_bei_prototipe.db --output output_screener
"""
import argparse,csv,sqlite3,sys
from pathlib import Path
from collections import defaultdict

HEADERS=['ticker','company','trade_date','close_idr','change_pct','volume','value_idr','net_foreign_volume_today','net_foreign_5d','net_foreign_10d','net_foreign_20d','foreign_days_available','price_return_5d_pct','price_return_20d_pct','price_days_available','volume_ratio_5d','fiscal_period','fiscal_period_end','publication_date','publication_verified','fundamental_is_historical_only','revenue_ytd_million_idr','net_income_ytd_million_idr','net_income_ttm_million_idr','eps_ttm_idr_per_share','roe_reported_pct','roa_reported_pct','net_margin_reported_pct','per_reported_x','pbv_reported_x','per_market_ttm_x','pbv_market_x','revenue_growth_reported_pct','net_income_growth_reported_pct','data_quality']

def num(v):return float(v) if v is not None else None
def rounded(v,n=3):return round(v,n) if v is not None else None
def ratio(n,d):return n/d if n is not None and d is not None and d!=0 else None

def build(db,output):
 if not db.is_file():raise ValueError('Database tidak ditemukan: '+str(db))
 conn=sqlite3.connect('file:'+str(db.resolve())+'?mode=ro',uri=True)
 conn.row_factory=sqlite3.Row
 names={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 if 'daily' not in names:raise ValueError('Tabel daily tidak ditemukan pada database ini')
 for req in ('trade_date','ticker','close','previous','foreign_buy','foreign_sell','volume','value'):
  if req not in {r[1] for r in conn.execute('PRAGMA table_info(daily)')}:raise ValueError('Kolom daily tidak ditemukan: '+req)
 latest=conn.execute('SELECT MAX(trade_date) FROM daily').fetchone()[0]
 if not latest:raise ValueError('Data pasar belum tersedia')
 # Most recent trading dates across the whole market (not calendar days).
 dates=[r[0] for r in conn.execute('SELECT DISTINCT trade_date FROM daily WHERE trade_date<=? ORDER BY trade_date DESC LIMIT 21',(latest,))]
 daily=defaultdict(dict)
 for r in conn.execute('SELECT trade_date,ticker,company,close,previous,volume,value,foreign_buy,foreign_sell FROM daily WHERE trade_date IN ('+','.join('?'*len(dates))+')',dates):
  daily[r['ticker']][r['trade_date']]=r
 fundamentals=defaultdict(dict)
 if 'fundamental' in names:
  for r in conn.execute('SELECT ticker,fiscal_year,fiscal_quarter,metric,raw_value,quarter_value,publication_date FROM fundamental ORDER BY fiscal_year,fiscal_quarter'):
   key=(r['fiscal_year'],r['fiscal_quarter'])
   entry=fundamentals[r['ticker']].setdefault(key,{'publication_date':None,'metrics':{}})
   entry['metrics'][r['metric']]=(num(r['raw_value']),num(r['quarter_value']))
   if r['publication_date']:entry['publication_date']=r['publication_date']
 rows=[]
 for ticker,hist in daily.items():
  cur=hist.get(latest)
  if cur is None:continue
  p=num(cur['previous']);close=num(cur['close']);vol=num(cur['volume'])
  observed=[hist[d] for d in dates if d in hist]
  flows=[(num(r['foreign_buy']) or 0)-(num(r['foreign_sell']) or 0) for r in observed]
  flow_n=lambda n:round(sum(flows[:n])) if len(observed)>=n else None
  # Closing-price return over 5/20 previous market sessions, if such a session is available for the ticker.
  ret=lambda n:rounded(100*(close/num(hist[dates[n]]['close'])-1)) if close is not None and len(dates)>n and dates[n] in hist and (num(hist[dates[n]]['close']) or 0)>0 else None
  avg5=sum(num(r['volume']) or 0 for r in observed[1:6])/5 if len(observed)>=6 else None
  quality=[];fiscal='';period_end='';pub='';verified='Tidak';hist_only='';metric={};fy=fq=None
  periods=fundamentals.get(ticker,{})
  if periods:
   fy,fq=max(periods)
   entry=periods[(fy,fq)];metric=entry['metrics'];pub=entry['publication_date'] or ''
   # No forecast of availability: date missing means only current snapshot, not historical as-of.
   fiscal=f'{fy} Q{fq}';period_end=f'{fy}-{fq*3:02d}'
   verified='Ya' if pub and pub<=latest else 'Tidak'
   if pub and pub>latest: quality.append('Laporan sesudah tanggal pasar; tidak dipakai untuk valuasi')
   if not pub:quality.append('Tanggal publikasi belum ada; bukan untuk backtesting')
   hist_only='Ya' if fy < int(latest[:4])-1 else 'Tidak'
   if hist_only=='Ya':quality.append('Fundamental lama dibanding data pasar')
  else:quality.append('Fundamental belum tersedia')
  get=lambda m,i=0:metric.get(m,(None,None))[i]
  def ttm(m):
   if fy is None:return None
   parts=[]
   for shift in range(4):
    n=(fy*4+fq-1)-shift; yy=n//4; qq=n%4+1
    period=fundamentals[ticker].get((yy,qq))
    if not period or m not in period['metrics'] or period['metrics'][m][1] is None:return None
    parts.append(period['metrics'][m][1])
   return sum(parts)
  eps=ttm('eps');income=ttm('net_income')
  # Only use BVPS as reported, never infer from nominal or inconsistent share-count units.
  bvps=get('bvps')
  market_ok=not (pub and pub>latest)
  values={
   'ticker':ticker,'company':cur['company'],'trade_date':latest,'close_idr':close,
   'change_pct':rounded(100*(close/p-1)) if close is not None and p and p>0 else None,
   'volume':vol,'value_idr':num(cur['value']),
   'net_foreign_volume_today':flows[0] if flows else None,
   'net_foreign_5d':flow_n(5),'net_foreign_10d':flow_n(10),'net_foreign_20d':flow_n(20),
   'foreign_days_available':len(observed),'price_return_5d_pct':ret(5),'price_return_20d_pct':ret(20),
   'price_days_available':len(observed),'volume_ratio_5d':rounded(ratio(vol,avg5)),
   'fiscal_period':fiscal,'fiscal_period_end':period_end,'publication_date':pub,
   'publication_verified':verified,'fundamental_is_historical_only':hist_only,
   'revenue_ytd_million_idr':get('revenue'),'net_income_ytd_million_idr':get('net_income'),
   'net_income_ttm_million_idr':rounded(income),'eps_ttm_idr_per_share':rounded(eps),
   'roe_reported_pct':get('roe_reported'),'roa_reported_pct':get('roa_reported'),
   'net_margin_reported_pct':get('net_margin_reported'),
   'per_reported_x':get('per_reported'),'pbv_reported_x':get('pbv_reported'),
   'per_market_ttm_x':rounded(ratio(close,eps)) if eps and eps>0 and market_ok else None,
   'pbv_market_x':rounded(ratio(close,bvps)) if bvps and bvps>0 and market_ok else None,
   'revenue_growth_reported_pct':get('sales_growth_reported'),
   'net_income_growth_reported_pct':get('net_income_growth_reported'),
   'data_quality':' | '.join(quality) if quality else 'OK'}
  if len(observed)<20:values['data_quality']+=' | Foreign 20D belum lengkap'
  rows.append(values)
 rows.sort(key=lambda x: (-(x['value_idr'] or 0),x['ticker']))
 output.mkdir(parents=True,exist_ok=True)
 def write(name,head,data):
  with (output/name).open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=head,extrasaction='ignore');w.writeheader();w.writerows(data)
 write('Integrated_Screener.csv',HEADERS,rows)
 eligible=[r for r in rows if r['fiscal_period']]
 write('Fundamental_Overview.csv',HEADERS,eligible)
 write('Foreign_Flow.csv',['ticker','trade_date','net_foreign_volume_today','net_foreign_5d','net_foreign_10d','net_foreign_20d','foreign_days_available','data_quality'],rows)
 with (output/'README_OUTPUT.txt').open('w',encoding='utf-8') as f:
  f.write('INTEGRATED STOCK SCREENER V1 — '+latest+'\n')
  f.write('Baris pasar: '+str(len(rows))+'; emiten dengan fundamental: '+str(len(eligible))+'\n')
  f.write('Foreign net volume = foreign_buy - foreign_sell (satuan sesuai file BEI).\n')
  f.write('Foreign 5/10/20 hanya keluar bila jumlah sesi yang tersedia cukup.\n')
  f.write('Price return 5D/20D menggunakan selisih 5/20 sesi pasar, memerlukan 6/21 tanggal.\n')
  f.write('Volume ratio 5D = volume terbaru / rata-rata lima sesi sebelumnya.\n')
  f.write('TTM dihitung dari empat nilai kuartal murni berurutan, tidak diperkirakan bila tidak lengkap.\n')
  f.write('Fundamental terbaru yang tersedia dipakai sebagai snapshot, bukan as-of backtest.\n')
  f.write('Tanggal publikasi belum tersedia: jangan gunakan untuk backtesting.\n')
  f.write('PER pasar dihitung hanya bila EPS TTM positif; PBV dari BVPS positif.\n')
  f.write('Rasio reported tetap snapshot historis dari file fundamental; mungkin sudah usang.\n')
  f.write('Tidak ada rekomendasi beli/jual atau jaminan akurasi data.\n')
 print('BERHASIL | Tanggal pasar:',latest,'| Saham:',len(rows),'| Dengan fundamental:',len(eligible),'| Folder:',output)
 conn.close()
 return len(rows),len(eligible)
if __name__=='__main__':
 p=argparse.ArgumentParser(description='Screener gabungan BEI (hanya baca database)')
 p.add_argument('--db',default='pasar_bei_prototipe.db');p.add_argument('--output',default='output_screener')
 a=p.parse_args()
 try:build(Path(a.db),Path(a.output))
 except Exception as exc:print('GAGAL:',exc,file=sys.stderr);sys.exit(1)
