"""Portfolio accounting using weighted-average cost, IDR, 100 shares per lot.
No market database writes. Trades replayed by trade date then id; excludes short sells.
"""
from collections import defaultdict
from datetime import date
from .decisions import connect

LOTSIZE=100

def ensure_dividends(db):
    with connect(db) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS dividends (
          id INTEGER PRIMARY KEY, pay_date TEXT NOT NULL, ticker TEXT NOT NULL,
          amount REAL NOT NULL CHECK(amount>=0), notes TEXT,
          recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

def add_dividend(db,pay_date,ticker,amount,notes=''):
    date.fromisoformat(pay_date)
    t=ticker.strip().upper()
    if not t or amount<=0:raise ValueError('Ticker dan dividen diterima (Rp) harus valid dan positif')
    ensure_dividends(db)
    with connect(db) as c:
        c.execute('INSERT INTO dividends(pay_date,ticker,amount,notes) VALUES(?,?,?,?)',(pay_date,t,float(amount),notes))

def calculate_portfolio(db,prices,as_of=None):
    ensure_dividends(db)
    with connect(db) as c:
        trades=c.execute('SELECT id,trade_date,ticker,side,lots,price,fee FROM transactions ORDER BY trade_date,id').fetchall()
        dividends=c.execute('SELECT id,pay_date,ticker,amount FROM dividends ORDER BY pay_date,id').fetchall()
    holdings=defaultdict(lambda:{'shares':0,'cost':0.0,'realized':0.0,'buy_fees':0.,'sell_fees':0.,'buys':0.,'sells':0.})
    rejected=[]
    for t in trades:
        if as_of and t['trade_date']>as_of:continue
        s=holdings[t['ticker'].upper()];qty=int(t['lots'])*LOTSIZE
        gross=qty*float(t['price']);fee=float(t['fee'])
        if t['side']=='BUY':
            s['shares']+=qty;s['cost']+=gross+fee;s['buy_fees']+=fee;s['buys']+=gross
        else:
            if qty>s['shares']:
                rejected.append((t['id'],t['ticker'],t['trade_date'],'SELL exceeds position when replayed chronologically'))
                continue
            portion=s['cost']*qty/s['shares']
            s['realized']+=gross-fee-portion
            s['cost']-=portion;s['shares']-=qty;s['sell_fees']+=fee;s['sells']+=gross
            if s['shares']==0:s['cost']=0.
    div_by=defaultdict(float)
    for d in dividends:
        if not as_of or d['pay_date']<=as_of:div_by[d['ticker'].upper()]+=float(d['amount'])
    positions=[];totals=dict(cost=0.,market_value=0.,unrealized=0.,realized=0.,dividends=sum(div_by.values()),missing_prices=0)
    for ticker,s in sorted(holdings.items()):
        totals['realized']+=s['realized']
        if s['shares']<=0:continue
        close=prices.get(ticker)
        value=(s['shares']*close) if close is not None else None
        unrl=value-s['cost'] if value is not None else None
        totals['cost']+=s['cost']
        if value is None:totals['missing_prices']+=1
        else:totals['market_value']+=value;totals['unrealized']+=unrl
        positions.append(dict(ticker=ticker,shares=s['shares'],lots=s['shares']/LOTSIZE,avg_cost=s['cost']/s['shares'],cost=s['cost'],close=close,value=value,unrealized=unrl,return_pct=unrl/s['cost']*100 if unrl is not None and s['cost'] else None,realized=s['realized'],dividends=div_by[ticker]))
    # P/L only complete if all current holdings priced
    totals['total_pl']=totals['realized']+totals['unrealized']+totals['dividends'] if totals['missing_prices']==0 else None
    return positions,totals,rejected
