"""Cash ledger and portfolio reconciliation; market data remains read-only."""
from datetime import date,datetime
from pathlib import Path
import sqlite3
from .decisions import connect
from .accounting import calculate_portfolio

def ensure_cash(db):
    with connect(db) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS cash_events (
          id INTEGER PRIMARY KEY, event_date TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('DEPOSIT','WITHDRAW')),
          amount REAL NOT NULL CHECK(amount>0), notes TEXT,
          recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_cash_events_date ON cash_events(event_date,id)')

def add_cash_event(db,dt,kind,amount,notes=''):
    date.fromisoformat(dt)
    kind=kind.strip().upper(); amount=float(amount)
    if kind not in ('DEPOSIT','WITHDRAW') or not 0<amount<1e17:
        raise ValueError('Jenis atau nilai setoran/penarikan tidak valid')
    ensure_cash(db)
    with connect(db) as c:
        c.execute('INSERT INTO cash_events(event_date,kind,amount,notes) VALUES(?,?,?,?)',(dt,kind,amount,notes))

def cash_events(db):
    ensure_cash(db)
    with connect(db) as c:
        return c.execute('SELECT event_date,kind,amount,COALESCE(notes,\'\'),id FROM cash_events ORDER BY event_date DESC,id DESC').fetchall()

def _backup_before_edit(db):
    # SQLite consistent backup before a user-requested change.
    path=Path(db)
    if not path.is_file():
        raise FileNotFoundError(f'Database investasi tidak ditemukan: {path}')
    folder=path.parent/'Backup_Investment'; folder.mkdir(parents=True,exist_ok=True)
    name=f'{path.stem}_before_cash_edit_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.db'
    dest=folder/name
    with sqlite3.connect(str(path)) as source,sqlite3.connect(str(dest)) as backup:
        source.backup(backup)
    return dest

def _cash_audit(c):
    c.execute('''CREATE TABLE IF NOT EXISTS cash_events_audit (
        id INTEGER PRIMARY KEY, cash_event_id INTEGER NOT NULL,
        action TEXT NOT NULL, old_date TEXT, old_kind TEXT, old_amount REAL,
        old_notes TEXT, new_date TEXT, new_kind TEXT, new_amount REAL,
        new_notes TEXT, changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

def _validated_cash(dt,kind,amount):
    date.fromisoformat(dt)
    kind=str(kind).strip().upper()
    amount=float(amount)
    import math
    if kind not in ('DEPOSIT','WITHDRAW') or not math.isfinite(amount) or not 0 < amount < 1e17:
        raise ValueError('Jenis atau nominal transaksi kas tidak valid')
    return kind,amount

def update_cash_event(db,event_id,dt,kind,amount,notes=''):
    kind,amount=_validated_cash(dt,kind,amount)
    ensure_cash(db)
    backup=_backup_before_edit(db)
    with connect(db) as c:
        _cash_audit(c)
        old=c.execute('SELECT event_date,kind,amount,notes FROM cash_events WHERE id=?',(int(event_id),)).fetchone()
        if old is None:raise ValueError('Setoran/penarikan tidak ditemukan. Muat ulang tabel.')
        c.execute('''INSERT INTO cash_events_audit
          (cash_event_id,action,old_date,old_kind,old_amount,old_notes,new_date,new_kind,new_amount,new_notes)
          VALUES(?,?,?,?,?,?,?,?,?,?)''',(int(event_id),'EDIT',old['event_date'],old['kind'],old['amount'],old['notes'],dt,kind,amount,notes))
        c.execute('UPDATE cash_events SET event_date=?,kind=?,amount=?,notes=? WHERE id=?',
                  (dt,kind,amount,notes,int(event_id)))
    return backup

def delete_cash_event(db,event_id):
    ensure_cash(db)
    backup=_backup_before_edit(db)
    with connect(db) as c:
        _cash_audit(c)
        old=c.execute('SELECT event_date,kind,amount,notes FROM cash_events WHERE id=?',(int(event_id),)).fetchone()
        if old is None:raise ValueError('Setoran/penarikan tidak ditemukan. Muat ulang tabel.')
        c.execute('''INSERT INTO cash_events_audit
          (cash_event_id,action,old_date,old_kind,old_amount,old_notes)
          VALUES(?,?,?,?,?,?)''',(int(event_id),'DELETE',old['event_date'],old['kind'],old['amount'],old['notes']))
        c.execute('DELETE FROM cash_events WHERE id=?',(int(event_id),))
    return backup

def cash_reconcile(db,prices,as_of=None):
    ensure_cash(db)
    with connect(db) as c:
        cash=list(c.execute('SELECT event_date,kind,amount FROM cash_events ORDER BY event_date,id'))
        tr=list(c.execute('SELECT trade_date,side,lots,price,fee,id FROM transactions ORDER BY trade_date,id'))
        has_div=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dividends'").fetchone()
        dvs=list(c.execute('SELECT pay_date,amount FROM dividends ORDER BY pay_date,id')) if has_div else []
    entries=[]
    for a in cash:
        if as_of and a['event_date']>as_of:continue
        v=float(a['amount'])*(1 if a['kind']=='DEPOSIT' else -1)
        entries.append((a['event_date'],0,a['kind'],v))
    for t in tr:
        if as_of and t['trade_date']>as_of:continue
        gross=int(t['lots'])*100*float(t['price']);fee=float(t['fee'])
        entries.append((t['trade_date'],1,t['side'], -gross-fee if t['side']=='BUY' else gross-fee))
    for d in dvs:
        if as_of and d['pay_date']>as_of:continue
        entries.append((d['pay_date'],2,'DIVIDEND',float(d['amount'])))
    entries.sort(key=lambda t:(t[0],t[1]))
    saldo=0;min_saldo=0
    for _,_,_,v in entries:
        saldo+=v;min_saldo=min(min_saldo,saldo)
    positions,totals,rejected=calculate_portfolio(db,prices,as_of)
    deposited=sum(x[3] for x in entries if x[2]=='DEPOSIT')
    withdrawn=-sum(x[3] for x in entries if x[2]=='WITHDRAW')
    equity=(saldo+totals['market_value']) if totals['missing_prices']==0 else None
    net_external=deposited-withdrawn
    since_inception_pnl=(equity-net_external) if equity is not None else None
    return dict(cash=saldo,invested=totals['market_value'],equity=equity,deposits=deposited,withdrawals=withdrawn,net_external=net_external,pl=since_inception_pnl,positions=positions,totals=totals,rejected=rejected,minimum_cash=min_saldo,events=entries)
