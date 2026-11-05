from pathlib import Path
import sqlite3

def market_connect(path):
    p=Path(path)
    if not p.is_file():
        raise FileNotFoundError(f'Database tidak ditemukan: {p}')
    c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    return c

def market_summary(path):
    with market_connect(path) as c:
        row=c.execute('SELECT COUNT(*),COUNT(DISTINCT trade_date),MIN(trade_date),MAX(trade_date),COUNT(DISTINCT ticker) FROM daily').fetchone()
        integrity=c.execute('PRAGMA quick_check').fetchone()[0]
        duplicate=c.execute('SELECT COUNT(*) FROM (SELECT 1 FROM daily GROUP BY trade_date,ticker HAVING COUNT(*)>1)').fetchone()[0]
        fundamentals=[]
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fundamental'").fetchone():
            fundamentals=[r[0] for r in c.execute('SELECT DISTINCT ticker FROM fundamental ORDER BY ticker')]
        return dict(records=row[0],sessions=row[1],first=row[2],latest=row[3],tickers=row[4],integrity=integrity,duplicate=duplicate,fundamentals=fundamentals)

def latest_prices(path):
    with market_connect(path) as c:
        dt=c.execute('SELECT MAX(trade_date) FROM daily').fetchone()[0]
        return dt,{str(r[0]).upper():float(r[1]) for r in c.execute('SELECT ticker,close FROM daily WHERE trade_date=? AND close IS NOT NULL',(dt,))}
