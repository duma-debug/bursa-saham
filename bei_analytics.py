#!/usr/bin/env python3
"""BEI Market Analytics V1 - standard library only, SQLite read-only.
Exports daily full-market-cap proxy, foreign net volume, and valuation/ROE scatter snapshots.
Not the official IHSG. Fundamental snapshots NOT point-in-time for backtesting.
"""
import argparse, csv, math, sqlite3, zipfile, xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

N={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

def number(v):
    if v is None: return None
    try:
        s=str(v).strip()
        if s.count('.')>1 and ',' not in s: s=s.replace('.','')
        elif '.' in s and ',' in s: s=s.replace('.','').replace(',','.')
        elif ',' in s: s=s.replace(',','')
        x=float(s)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

def xlsx_rows(path):
    """Read first sheet of master XLSX via stdlib, no Excel or external dependencies."""
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(t.text or '' for t in x.findall('.//m:t',N)) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',N)]
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        targets={r.attrib['Id']:r.attrib['Target'] for r in rels}
        sheets=wb.findall('m:sheets/m:sheet',N)
        selected=next((s for s in sheets if s.attrib.get('name')=='Daftar Saham'),sheets[0])
        rid=selected.attrib['{'+N['r']+'}id']; target=targets[rid]
        fn=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        root=ET.fromstring(z.read(fn))
        for r in root.findall('.//m:sheetData/m:row',N):
            d={}
            for c in r.findall('m:c',N):
                col=''.join(x for x in c.attrib.get('r','') if x.isalpha())
                typ=c.attrib.get('t'); v=c.find('m:v',N)
                if typ=='inlineStr':
                    cell=c.find('m:is',N); value=''.join(t.text or '' for t in cell.findall('.//m:t',N)) if cell is not None else ''
                elif v is None: value=''
                elif typ=='s': value=shared[int(v.text)]
                else: value=v.text
                d[col]=value
            yield d

def load_master(path):
    rows=iter(xlsx_rows(path)); first=next(rows,{})
    headers={str(v or '').strip().lower():k for k,v in first.items()}
    def col(*candidates):
        for n in candidates:
            if n.lower() in headers:return headers[n.lower()]
        return None
    code=col('Kode','Ticker'); shares=col('Saham','Jumlah Saham','Listed Shares','Shares Outstanding');sector=col('Sector','Sektor')
    if not code or not shares:raise ValueError('Master perlu kolom Kode dan Saham; header ditemukan: '+str(list(headers)))
    out={}
    for r in rows:
        ticker=str(r.get(code) or '').strip().upper(); sh=number(r.get(shares))
        if ticker:
            out[ticker]={'shares':sh,'sector':str(r.get(sector) or 'Unknown').strip() if sector else 'Unknown'}
    return out

def db_readonly(path):
    if not Path(path).is_file():raise FileNotFoundError('Database tidak ditemukan: '+str(path))
    con=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
    return con

def exists(con,table):return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def valuation_latest(con):
    result=defaultdict(dict)
    if not exists(con,'fundamental'):return result
    cols={x[1] for x in con.execute('PRAGMA table_info(fundamental)')}
    if not {'ticker','metric','raw_value','fiscal_year','fiscal_quarter'} <= cols:return result
    # Latest reported source period for each metric. Not point-in-time as of historical market date.
    rows=con.execute('SELECT ticker,metric,raw_value,fiscal_year,fiscal_quarter FROM fundamental ORDER BY fiscal_year DESC,fiscal_quarter DESC').fetchall()
    for r in rows:
        t=str(r['ticker']).strip().upper(); metric=r['metric']
        if metric not in result[t]: result[t][metric]=(number(r['raw_value']),str(r['fiscal_year'])+'Q'+str(r['fiscal_quarter']))
    if exists(con,'fundamental_annual'):
        cols2={x[1] for x in con.execute('PRAGMA table_info(fundamental_annual)')}
        if {'ticker','metric','raw_value','fiscal_year'} <= cols2:
            annual=con.execute('SELECT ticker,metric,raw_value,fiscal_year FROM fundamental_annual ORDER BY fiscal_year DESC').fetchall()
            for r in annual:
                t=str(r['ticker']).strip().upper()
                if r['metric'] not in result[t]: result[t][r['metric']]=(number(r['raw_value']),str(r['fiscal_year'])+' FY')
    return result

def export_csv(path,headers,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(headers);w.writerows(rows)

def calculate(db,master_path,output):
    master=load_master(master_path)
    con=db_readonly(db)
    if not exists(con,'daily'):raise ValueError('Tabel daily tidak ditemukan')
    cols={r[1] for r in con.execute('PRAGMA table_info(daily)')}
    required={'trade_date','ticker','close','foreign_buy','foreign_sell'}
    if not required <= cols:raise ValueError('Kolom daily tidak lengkap: '+str(required-cols))
    prev_col='previous' if 'previous' in cols else 'NULL'
    rec=con.execute(f'SELECT trade_date,ticker,close,{prev_col} AS previous,foreign_buy,foreign_sell FROM daily ORDER BY trade_date,ticker').fetchall()
    byday=defaultdict(list);bad=0
    for r in rec:
        t=str(r['ticker'] or '').strip().upper()
        if not t: continue
        byday[str(r['trade_date'])].append((t,number(r['close']),number(r['previous']),number(r['foreign_buy']),number(r['foreign_sell'])))
    daily=[];stocks=[]; sectors=[]; prev_caps={}; prev_date=None; base_cap=None; proxy=None
    for date in sorted(byday):
        total_cap=0.; total_buy=0.; total_sell=0.; cap_valid=0
        up=down=flat=0; sector_caps=defaultdict(float);cap_by_ticker={}
        seen=set(); missing_master=0;missing_shares=0; missing_foreign=0
        for t,close,previous,buy,sell in byday[date]:
            if t in seen: raise ValueError(f'Duplikat ticker {t} pada {date}')
            seen.add(t)
            if buy is None or sell is None:missing_foreign+=1
            else:total_buy+=buy;total_sell+=sell
            if close is not None and previous is not None and previous>0:
                if close>previous: up+=1
                elif close<previous:down+=1
                else:flat+=1
            data=master.get(t)
            if data is None:missing_master+=1;continue
            sh=data['shares']
            if sh is None or sh<=0:missing_shares+=1;continue
            if close is None or close<=0:continue
            cap=close*sh; sector=data['sector'];total_cap+=cap;cap_valid+=1
            sector_caps[sector]+=cap;cap_by_ticker[t]=cap
            stocks.append((date,t,sector,close,int(sh) if sh.is_integer() else sh,round(cap,2),buy,sell, (buy-sell) if buy is not None and sell is not None else None))
        # Comparable matched-universe return: weights from prior date, only overlapping tickers.
        common=set(cap_by_ticker)&set(prev_caps)
        past=sum(prev_caps[t] for t in common);current=sum(cap_by_ticker[t] for t in common)
        ret=(current/past-1) if past>0 else None
        if proxy is None:proxy=100.0; base_cap=total_cap
        elif ret is not None:proxy*=1+ret
        else:proxy=None
        daily.append((date,len(seen),cap_valid,missing_master,missing_shares,missing_foreign,
                     round(total_cap,2),round(total_buy,2),round(total_sell,2),round(total_buy-total_sell,2),
                     round(ret*100,6) if ret is not None else None, round(proxy,6) if proxy is not None else None,
                     up,down,flat,len(common),prev_date or ''))
        for sector,cap in sorted(sector_caps.items()):sectors.append((date,sector,round(cap,2),round(100*cap/total_cap,4) if total_cap else None))
        prev_caps=cap_by_ticker;prev_date=date
    fundamentals=valuation_latest(con)
    latest=sorted(byday)[-1] if byday else ''
    latest_closes={r[0]:r[1] for r in byday[latest]} if latest else {}
    scatter=[]
    for t,values in sorted(fundamentals.items()):
        roe,roe_period=values.get('roe_reported',(None,''))
        if roe is None:continue
        # Ratios as reported in fundamentals; may be based on a historical price and NOT current as-of date.
        for metric,label in [('pbv_reported','PBV'),('per_reported','PER'),('ev_ebitda_reported','EV/EBITDA')]:
            multiple,period=values.get(metric,(None,''))
            if multiple is None or multiple<=0:continue
            scatter.append((t,master.get(t,{}).get('sector','Unknown'),roe,label,multiple,roe_period,period,latest_closes.get(t)))
    out=Path(output)
    export_csv(out/'market_daily.csv', ['date','tickers','cap_valid','missing_master','missing_shares','missing_foreign','full_market_cap_idr_snapshot','foreign_buy_shares','foreign_sell_shares','foreign_net_shares','matched_cap_return_pct','market_cap_proxy_index_base100','advancers','decliners','unchanged','matched_tickers','previous_available_date'],daily)
    export_csv(out/'stock_daily.csv',['date','ticker','sector','close_idr','listed_shares_master_snapshot','market_cap_idr','foreign_buy_shares','foreign_sell_shares','foreign_net_shares'],stocks)
    export_csv(out/'sector_daily.csv',['date','sector','market_cap_idr','market_cap_weight_pct'],sectors)
    export_csv(out/'fundamental_scatter.csv',['ticker','sector','roe_reported_pct','valuation_metric','valuation_multiple_x','roe_fiscal_period','valuation_fiscal_period','latest_close_reference_only'],scatter)
    with (out/'DATA_QUALITY.txt').open('w',encoding='utf-8') as f:
        f.write('BEI ANALYTICS — QUALITY & METHODOLOGY\n\n')
        f.write('1. market_cap_proxy_index_base100 BUKAN IHSG resmi. Base 100 pada sesi paling awal dalam DB.\n')
        f.write('2. Return menggunakan emiten yang muncul baik pada dua sesi tersedia berturutan; bukan divisor IHSG.\n')
        f.write('3. Jumlah saham master adalah snapshot; histori tidak disesuaikan corporate action/free float.\n')
        f.write('4. FOREIGN BUY/SELL/NET adalah VOLUME LEMBAR SAHAM, BUKAN NILAI RUPIAH.\n')
        f.write('5. Scatter memakai fundamental terbaru per metrik (campuran periode mungkin terjadi), bukan data point-in-time; tidak cocok untuk backtest.\n')
        f.write('6. PER/PBV/EV EBITDA adalah multiple tersimpan dari file fundamental dan BUKAN valuasi recalculated pada harga harian terakhir.\n')
        f.write('7. Data yang tersedia mungkin melompati sesi BEI; cek previous_available_date.\n')
        f.write('8. Multiple negatif/nol disembunyikan dari scatter; emiten tanpa ROE atau valuation tidak tampil.\n')
        f.write(f'\nMASTER tickers: {len(master)} | DB dates: {len(daily)} | fundamental points: {len(scatter)}\n')
        f.write('Missing master by date (date,count): '+str([(r[0],r[3]) for r in daily if r[3]])+'\n')
    con.close()
    return daily,stocks,sectors,scatter

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',default='pasar_bei_prototipe.db');p.add_argument('--master',default='Daftar Saham  sektor.xlsx');p.add_argument('--output',default='output_analytics');a=p.parse_args()
    d,s,se,sc=calculate(a.db,a.master,a.output)
    print(f'BERHASIL | Sesi {len(d)} | Saham-hari {len(s)} | Sektor-hari {len(se)} | Titik scatter {len(sc)} | Folder {a.output}')
    print('IHSG: proxy indeks basis 100, BUKAN IHSG resmi | Foreign: volume lembar, BUKAN Rp')
if __name__=='__main__':main()
