#!/usr/bin/env python3
"""Prototipe BEI — import incremental XLSX tanpa pandas/openpyxl.
Pemakaian: python prototipe_bei.py --input 'Ringkasan Saham-20261009.xlsx' --db pasar_bei.db --output hasil
Bergantung hanya pada pustaka standar Python. Hasilnya CSV yang dapat dibuka Excel.
"""
import argparse,csv,datetime as dt,os,re,sqlite3,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
COLUMNS=['no','ticker','company','remarks','previous','open','last_trade_date','first_trade','high','low','close','change','volume','value','frequency','individual_index','offer','offer_volume','bid','bid_volume','listed_shares','tradeable_shares','index_weight','foreign_sell','foreign_buy','nonregular_volume','nonregular_value','nonregular_frequency']
NUMERIC={'previous','open','first_trade','high','low','close','change','volume','value','frequency','individual_index','offer','offer_volume','bid','bid_volume','listed_shares','tradeable_shares','index_weight','foreign_sell','foreign_buy','nonregular_volume','nonregular_value','nonregular_frequency'}
MONTHS={'jan':1,'feb':2,'mar':3,'apr':4,'mei':5,'may':5,'jun':6,'jul':7,'agu':8,'aug':8,'sep':9,'okt':10,'oct':10,'nov':11,'des':12,'dec':12}

def date_parse(value):
    import datetime
    import re

    if isinstance(value, datetime.datetime):
        return value.date().isoformat()

    if isinstance(value, datetime.date):
        return value.isoformat()

    s = str(value).strip().lower()

    months = {
        "jan": 1, "feb": 2, "mar": 3,
        "maret": 3, "apr": 4, "mei": 5,
        "may": 5, "jun": 6, "jul": 7,
        "agu": 8, "agt": 8, "aug": 8,
        "sep": 9, "sept": 9, "okt": 10,
        "oct": 10, "nov": 11, "des": 12,
        "dec": 12
    }

    # Format ISO: 2026-08-13
    try:
        return datetime.date.fromisoformat(s).isoformat()
    except ValueError:
        pass

    # Format: 13-Agt-2026 atau 13 Aug 2026
    m = re.match(
        r"^(\d{1,2})[\s/-]+([a-z]+)[\s/-]+(\d{4})$",
        s
    )

    if m:
        day, month, year = m.groups()
        if month in months:
            return datetime.date(
                int(year), months[month], int(day)
            ).isoformat()

    # Format: 13/08/2026 atau 13-08-2026
    m = re.match(
        r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$",
        s
    )

    if m:
        day, month, year = map(int, m.groups())
        return datetime.date(
            year, month, day
        ).isoformat()

    raise ValueError(f"Format tanggal tidak dikenali: {value}")
def read_xlsx(path):
 with zipfile.ZipFile(path) as z:
  strings=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   r=ET.fromstring(z.read('xl/sharedStrings.xml'))
   strings=[''.join(t.text or '' for t in e.findall('.//x:t',NS)) for e in r.findall('x:si',NS)]
  with z.open('xl/worksheets/sheet1.xml') as f:
   for event, elem in ET.iterparse(f,events=('end',)):
    if elem.tag.endswith('}row'):
     cells={}
     for c in elem:
      if not c.tag.endswith('}c'):continue
      col=re.match(r'[A-Z]+',c.attrib.get('r','')).group(); idx=0
      for ch in col:idx=idx*26+ord(ch)-64
      v=c.find('x:v',NS); inline=c.find('x:is',NS)
      raw=v.text if v is not None else ''.join(t.text or '' for t in inline.findall('.//x:t',NS)) if inline is not None else None
      if c.attrib.get('t')=='s' and raw is not None:raw=strings[int(raw)]
      cells[idx-1]=raw
     if int(elem.attrib.get('r',0))>1:
      data={name:cells.get(i) for i,name in enumerate(COLUMNS)}
      if data['ticker'] and str(data['ticker']).strip():yield data
     elem.clear()
def as_number(x):
 if x in (None,'','-'):return None
 try:return float(str(x).replace(',',''))
 except ValueError:return None
def init_db(conn):
 spec=','.join('"%s" %s'%(c,'REAL' if c in NUMERIC else 'TEXT') for c in COLUMNS if c not in ('no','last_trade_date'))
 conn.execute(f'''CREATE TABLE IF NOT EXISTS daily (trade_date TEXT NOT NULL, {spec}, PRIMARY KEY(trade_date,ticker))''')
 conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_ticker_date ON daily(ticker,trade_date)')
 conn.execute('CREATE TABLE IF NOT EXISTS import_log(imported_at TEXT, source_file TEXT, trade_date TEXT, rows_read INTEGER, rows_inserted INTEGER, rows_updated INTEGER)')
def ingest(conn, source):
 items=list(read_xlsx(source)); assert items,'File tanpa data saham'
 dates={date_parse(row['last_trade_date']) for row in items if row['last_trade_date']}
 if len(dates)!=1: raise ValueError('File memuat tanggal berbeda: '+str(dates))
 trade_date=dates.pop(); tickers=[str(r['ticker']).strip().upper() for r in items]
 if len(tickers)!=len(set(tickers)):raise ValueError('Ticker duplikat pada file: '+source)
 fields=['trade_date']+[c for c in COLUMNS if c not in ('no','last_trade_date')]
 cols=','.join('"'+x+'"' for x in fields); q=','.join('?' for _ in fields)
 update=','.join(f'"{c}"=excluded."{c}"' for c in fields if c not in ('trade_date','ticker'))
 nold=conn.execute('SELECT COUNT(*) FROM daily WHERE trade_date=?',(trade_date,)).fetchone()[0]
 with conn:
  for r in items:
   r['ticker']=str(r['ticker']).strip().upper()
   vals=[trade_date]+[as_number(r[c]) if c in NUMERIC else r[c] for c in fields[1:]]
   conn.execute(f'INSERT INTO daily ({cols}) VALUES ({q}) ON CONFLICT(trade_date,ticker) DO UPDATE SET {update}',vals)
  nnew=conn.execute('SELECT COUNT(*) FROM daily WHERE trade_date=?',(trade_date,)).fetchone()[0]
  conn.execute('INSERT INTO import_log VALUES (?,?,?,?,?,?)',(dt.datetime.now().isoformat(timespec='seconds'),str(source),trade_date,len(items),max(nnew-nold,0),min(nold,len(items))))
 return trade_date,len(items),nnew-nold
def export(conn,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 latest=conn.execute('SELECT MAX(trade_date) FROM daily').fetchone()[0]
 if latest is None:raise ValueError('Database kosong')
 sql='''WITH latest AS (
  SELECT *, foreign_buy-foreign_sell AS net_foreign_volume,
         CASE WHEN previous>0 THEN (close/previous-1)*100 END AS change_pct,
         CASE WHEN volume>0 THEN value/volume END AS vwap_proxy,
         CASE WHEN bid>0 AND offer>0 THEN (offer-bid)*100.0/bid END AS bid_offer_spread_pct
  FROM daily WHERE trade_date = ?),
  calc AS (SELECT *, ROW_NUMBER() OVER (ORDER BY value DESC,ticker) AS value_rank,
         ROW_NUMBER() OVER (ORDER BY foreign_buy-foreign_sell DESC,ticker) AS foreign_rank,
         ROW_NUMBER() OVER (ORDER BY volume DESC,ticker) AS volume_rank FROM latest)
 SELECT trade_date,ticker,company,previous,open,high,low,close,ROUND(change_pct,3) AS change_pct,
  volume,value,frequency,foreign_buy,foreign_sell,net_foreign_volume,foreign_rank,value_rank,volume_rank,
  nonregular_volume,nonregular_value,ROUND(vwap_proxy,2) AS vwap_proxy,ROUND(bid_offer_spread_pct,3) AS bid_offer_spread_pct
 FROM calc ORDER BY value_rank'''
 cur=conn.execute(sql,(latest,)); names=[d[0] for d in cur.description];rows=cur.fetchall()
 with (folder/'market_dashboard.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(names);w.writerows(rows)
 c=conn.execute('''SELECT ticker,COUNT(*) AS observed_days,ROUND(SUM(foreign_buy-foreign_sell),0) AS cumulative_foreign_volume,ROUND(SUM(value),0) AS cumulative_value,
 MIN(trade_date) AS first_date,MAX(trade_date) AS last_date FROM daily GROUP BY ticker ORDER BY cumulative_foreign_volume DESC''')
 with (folder/'foreign_accumulation.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow([a[0] for a in c.description]);w.writerows(c.fetchall())
 c=conn.execute('''SELECT trade_date,ticker,close,previous,value,volume,foreign_buy-foreign_sell AS net_foreign_volume FROM daily ORDER BY ticker,trade_date''')
 with (folder/'historical_prices.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow([a[0] for a in c.description]);w.writerows(c.fetchall())
 print('Data terbaru:',latest,'Saham:',len(rows),'Folder hasil:',folder)
 return latest,len(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',nargs='+',required=True);p.add_argument('--db',default='pasar_bei.db');p.add_argument('--output',default='output_bei');args=p.parse_args()
 conn=sqlite3.connect(args.db);init_db(conn)
 for f in args.input:print('Impor:',f,ingest(conn,f))
 export(conn,args.output);conn.close()
if __name__=='__main__':main()
