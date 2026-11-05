"""User-entered decision data, in a separate SQLite database. No connection to market write APIs."""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

def connect(path):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p);c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS research (
      id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, as_of TEXT NOT NULL,
      decision TEXT NOT NULL, fair_value REAL, thesis TEXT NOT NULL, risks TEXT NOT NULL,
      catalysts TEXT NOT NULL, saved_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS transactions (
      id INTEGER PRIMARY KEY, trade_date TEXT NOT NULL, ticker TEXT NOT NULL,
      side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
      lots INTEGER NOT NULL CHECK(lots>0), price REAL NOT NULL CHECK(price>0),
      fee REAL NOT NULL DEFAULT 0 CHECK(fee>=0), notes TEXT,
      recorded_at TEXT NOT NULL);
    ''')
    c.commit();return c

def save_research(path,ticker,as_of,decision,fair_value,thesis,risks,catalysts):
    ticker=ticker.strip().upper()
    if not ticker or not as_of:raise ValueError('Ticker dan tanggal wajib diisi')
    if fair_value is not None and fair_value<=0:raise ValueError('Harga wajar harus positif')
    with connect(path) as c:
        c.execute('INSERT INTO research(ticker,as_of,decision,fair_value,thesis,risks,catalysts,saved_at) VALUES(?,?,?,?,?,?,?,?)',
          (ticker,as_of,decision,fair_value,thesis,risks,catalysts,datetime.now(timezone.utc).isoformat()))

def save_transaction(path,dt,ticker,side,lots,price,fee=0,notes=''):
    ticker=ticker.strip().upper();side=side.upper()
    if not dt or not ticker or side not in ('BUY','SELL') or lots<=0 or price<=0 or fee<0:
        raise ValueError('Data transaksi tidak valid')
    with connect(path) as c:
        pos=c.execute('SELECT COALESCE(SUM(CASE WHEN side="BUY" THEN lots ELSE -lots END),0) FROM transactions WHERE ticker=?',(ticker,)).fetchone()[0]
        if side=='SELL' and lots>pos:raise ValueError(f'Jual {lots} lot melebihi posisi {pos} lot; short selling tidak didukung')
        c.execute('INSERT INTO transactions(trade_date,ticker,side,lots,price,fee,notes,recorded_at) VALUES(?,?,?,?,?,?,?,?)',
          (dt,ticker,side,lots,price,fee,notes,datetime.now(timezone.utc).isoformat()))

def positions(path):
    with connect(path) as c:
        rows=c.execute('''SELECT ticker,SUM(CASE WHEN side='BUY' THEN lots ELSE -lots END) AS lots
            FROM transactions GROUP BY ticker HAVING lots>0 ORDER BY ticker''').fetchall()
        return [(r['ticker'],r['lots']) for r in rows]

def research_rows(path):
    with connect(path) as c:
        return c.execute('SELECT id,ticker,as_of,decision,fair_value,saved_at FROM research ORDER BY id DESC LIMIT 100').fetchall()

def transaction_rows(path):
    with connect(path) as c:
        return c.execute('SELECT trade_date,ticker,side,lots,price,fee FROM transactions ORDER BY id DESC LIMIT 300').fetchall()
