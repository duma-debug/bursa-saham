#!/usr/bin/env python3
"""BEI Equity Analytics V2. Pure Tkinter + SQLite read-only. No external packages."""
import csv,math,sqlite3,datetime,tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import ttk,messagebox,filedialog
from bei_analytics import load_master,number
BASE=Path(__file__).resolve().parent
DB=BASE/'pasar_bei_prototipe.db'
MASTER=BASE/'Daftar Saham  sektor.xlsx'
P_GREEN='#14866b';P_RED='#d95354';P_BLUE='#2479ac'

def fmt(v,d=0):
    if v is None:return 'N/A'
    return f'{v:,.{d}f}'
def compact(v):
    if v is None:return 'N/A'
    for n,s in ((1e12,'T'),(1e9,'miliar'),(1e6,'juta'),(1e3,'ribu')):
        if abs(v)>=n:return f'{v/n:,.2f} {s}'
    return f'{v:,.0f}'
def ro_conn(path=DB):
    if not Path(path).exists():raise FileNotFoundError(f'Database belum ditemukan: {path}')
    c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    return c

def table_exists(c,t):return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone())

def snapshot(c,master,day):
    cols={x['name'] for x in c.execute('PRAGMA table_info(daily)')}
    keys=['ticker','close','previous','volume','value','foreign_buy','foreign_sell']
    fields=[k if k in cols else f'NULL AS {k}' for k in keys]
    rows=[]
    for r in c.execute('SELECT '+','.join(fields)+' FROM daily WHERE trade_date=? ORDER BY ticker',(day,)):
        x={k:r[k] for k in keys};t=str(x['ticker'] or '').strip().upper()
        if not t:continue
        for k in keys[1:]:x[k]=number(x[k])
        x['ticker']=t;x['sector']=master.get(t,{}).get('sector','Unknown')
        p=x['previous'];x['change_pct']=100*(x['close']/p-1) if x['close'] is not None and p and p>0 else None
        b,s=x['foreign_buy'],x['foreign_sell'];x['net']=b-s if b is not None and s is not None else None
        shares=master.get(t,{}).get('shares');x['cap']=x['close']*shares if x['close'] and shares and shares>0 else None
        rows.append(x)
    return rows

def market_history(c,master,sector='Semua Sektor'):
    dates=[r[0] for r in c.execute('SELECT DISTINCT trade_date FROM daily ORDER BY trade_date')]
    ans=[];old={};idx=100.
    for day in dates:
        rows=snapshot(c,master,day)
        if sector!='Semua Sektor':rows=[r for r in rows if r['sector']==sector]
        cap={r['ticker']:r['cap'] for r in rows if r['cap'] is not None}
        common=set(old)&set(cap);past=sum(old[t] for t in common)
        if past:idx*=sum(cap[t] for t in common)/past
        old=cap
        ans.append({'date':day,'index':idx,'buy':sum(r['foreign_buy'] or 0 for r in rows),'sell':sum(r['foreign_sell'] or 0 for r in rows),'net':sum(r['net'] or 0 for r in rows),'coverage':sum(r['net'] is not None for r in rows)})
    return ans

def fundamentals(c,ticker):
    result={'annual':defaultdict(dict),'quarterly':defaultdict(dict)}
    for name,typ in [('fundamental_annual','annual'),('fundamental','quarterly')]:
        if not table_exists(c,name):continue
        cols={x['name'] for x in c.execute(f'PRAGMA table_info({name})')}
        fields=['fiscal_year','metric','raw_value']+(['fiscal_quarter'] if typ=='quarterly' else [])
        if not set(fields).issubset(cols):continue
        for r in c.execute('SELECT '+','.join(fields)+f' FROM {name} WHERE ticker=?',(ticker,)):
            period=(int(r['fiscal_year']),int(r['fiscal_quarter'])) if typ=='quarterly' else int(r['fiscal_year'])
            result[typ][period][r['metric']]=number(r['raw_value'])
    return result

def fy_profit_projection(data,year=2026):
    """Forecast annual net profit (million IDR): YTD current + previous FY remaining seasonality.
    Returns (value, method) or (None, reason).
    """
    qds=[(q,m) for (y,q),m in data['quarterly'].items() if y==year and m.get('net_income') is not None]
    if (year in data['annual']) and data['annual'][year].get('net_income') is not None:
        return data['annual'][year]['net_income'], 'FY reported (bukan forecast)'
    if not qds:return None,'Belum ada laba YTD 2026'
    q,m=max(qds,key=lambda a:a[0]);ytd=m['net_income']
    prev_ytd=data['quarterly'].get((year-1,q),{}).get('net_income')
    prev_fy=data['annual'].get(year-1,{}).get('net_income')
    if prev_ytd is not None and prev_fy is not None:
        return ytd+(prev_fy-prev_ytd),f'FY2026E = YTD Q{q} 2026 + (FY2025 − YTD Q{q} 2025), Rp juta'
    return ytd*4/q,f'FY2026E = YTD Q{q} 2026 × 4/{q} (annualisasi sederhana), Rp juta; asumsi kasar'

def latest_metric(data,metric):
    q=sorted(data['quarterly'],reverse=True)
    for period in q:
        v=data['quarterly'][period].get(metric)
        if v is not None:return v,f'{period[0]} Q{period[1]}'
    for yr in sorted(data['annual'],reverse=True):
        v=data['annual'][yr].get(metric)
        if v is not None:return v,f'FY{yr}'
    return None,'tidak tersedia'

class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('BEI Equity Analytics V2 — Market | Stock Detail | FY2026 Valuation | Data Health')
        self.geometry('1500x930');self.minsize(1050,680)
        self.master_data={};self.dates=[];self.rows=[];self.series=[];self.selected_ticker='';self.finance={};self.picked=None
        self.date=tk.StringVar();self.sector=tk.StringVar(value='Semua Sektor');self.period=tk.StringVar(value='5');self.mode=tk.StringVar(value='net')
        self.ticker_var=tk.StringVar();self.method=tk.StringVar(value='PER');self.target=tk.StringVar(value='10');self.manual_eps=tk.StringVar(value='');self.net_debt=tk.StringVar(value='');self.ebitda=tk.StringVar(value='');self.minority=tk.StringVar(value='0');self.extra_assets=tk.StringVar(value='0')
        self.status=tk.StringVar(value='Memuat data...')
        self._build()
        try:self.reload()
        except Exception as e:self.status.set('GAGAL: '+str(e));messagebox.showwarning('File belum siap',str(e))
    def _build(self):
        head=ttk.Frame(self,padding=10);head.pack(fill='x')
        ttk.Label(head,text='BEI Equity Analytics',font=('Segoe UI',20,'bold')).pack(side='left')
        ttk.Label(head,text='  ·  Analisis harga · foreign flow · fundamental · valuasi',font=('Segoe UI',10)).pack(side='left')
        ttk.Button(head,text='Muat ulang data',command=self.reload).pack(side='right')
        controls=ttk.Frame(self,padding=(11,5));controls.pack(fill='x')
        for label,var,opts,w in [('Tanggal',self.date,[],16),('Sektor',self.sector,[],23),('Foreign 1/5/10/20D',self.period,['1','5','10','20'],8),('Treemap',self.mode,['net','buy','sell'],8)]:
            ttk.Label(controls,text=label).pack(side='left',padx=(8,3));box=ttk.Combobox(controls,textvariable=var,values=opts,width=w,state='readonly');box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda e:self.refresh());
            if label=='Tanggal':self.date_box=box
            if label=='Sektor':self.sector_box=box
        ttk.Button(controls,text='Refresh',command=self.refresh).pack(side='left',padx=12)
        tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True,padx=11,pady=5);self.tabs=tabs
        self.overview=ttk.Frame(tabs);self.detail=ttk.Frame(tabs);self.valuation=ttk.Frame(tabs);self.health=ttk.Frame(tabs)
        for obj,name in [(self.overview,'Market Overview'),(self.detail,'Stock Detail'),(self.valuation,'Valuation FY2026E'),(self.health,'Data Health')]:tabs.add(obj,text=name)
        # Overview: two compact charts + rankings and treemap
        f=ttk.Frame(self.overview);f.pack(fill='x',padx=5,pady=3)
        self.summary=tk.StringVar(value='Memuat...');ttk.Label(f,textvariable=self.summary,font=('Segoe UI',11,'bold')).pack(side='left')
        ttk.Label(self.overview,text='Market-cap weighted proxy (basis 100; BUKAN IHSG resmi)',font=('Segoe UI',10,'bold')).pack(anchor='w',padx=5)
        self.market_canvas=tk.Canvas(self.overview,bg='white',height=142,highlightthickness=1,highlightbackground='#dce3ec');self.market_canvas.pack(fill='x',padx=5)
        ttk.Label(self.overview,text='Foreign net harian (volume lembar saham) — klik batang untuk memilih tanggal',font=('Segoe UI',9,'bold')).pack(anchor='w',padx=5,pady=(5,0))
        self.foreign_canvas=tk.Canvas(self.overview,bg='white',height=82,highlightthickness=1,highlightbackground='#dce3ec');self.foreign_canvas.pack(fill='x',padx=5)
        self.foreign_canvas.bind('<Button-1>',self.click_foreign);self.foreign_canvas.bind('<Motion>',self.hover_foreign)
        self.hover_status=tk.StringVar(value='Foreign: jumlah lembar saham, bukan nilai transaksi Rp.');ttk.Label(self.overview,textvariable=self.hover_status).pack(anchor='w',padx=5)
        mid=ttk.PanedWindow(self.overview,orient='horizontal');mid.pack(fill='both',expand=True,padx=5,pady=5)
        left=ttk.Frame(mid);right=ttk.Frame(mid);mid.add(left,weight=4);mid.add(right,weight=3)
        ttk.Label(left,text='Treemap Sector → Ticker (skala Square Root untuk visualisasi)',font=('Segoe UI',10,'bold')).pack(anchor='w')
        self.tree_canvas=tk.Canvas(left,bg='white',highlightthickness=1,highlightbackground='#dce3ec',height=230);self.tree_canvas.pack(fill='both',expand=True)
        self.tree_canvas.bind('<Button-1>',self.click_treemap);self.tree_canvas.bind('<Motion>',self.hover_treemap)
        self.ranking_tabs=ttk.Notebook(right);self.ranking_tabs.pack(fill='both',expand=True)
        specs=[('Top Gainers','change_pct',True),('Top Losers','change_pct',False),('Top Volume','volume',True),('Top Value','value',True),('Foreign Buy','net',True),('Foreign Sell','net',False)]
        self.rankings={}
        for name,key,descending in specs:
            fr=ttk.Frame(self.ranking_tabs);self.ranking_tabs.add(fr,text=name)
            tv=ttk.Treeview(fr,columns=('ticker','sector','number'),show='headings',height=9)
            for col,text,width in [('ticker','Kode',70),('sector','Sektor',125),('number','Nilai',150)]:tv.heading(col,text=text);tv.column(col,width=width,anchor='e' if col=='number' else 'w')
            tv.pack(fill='both',expand=True);tv.bind('<Double-1>',lambda e,tv=tv:self.rank_open(tv))
            self.rankings[name]=(tv,key,descending)
        # Stock detail
        dtop=ttk.Frame(self.detail,padding=9);dtop.pack(fill='x')
        ttk.Label(dtop,text='Ticker:').pack(side='left');ttk.Entry(dtop,textvariable=self.ticker_var,width=13).pack(side='left',padx=6)
        ttk.Button(dtop,text='Buka Saham',command=lambda:self.open_stock(self.ticker_var.get())).pack(side='left')
        self.stock_header=tk.StringVar(value='Klik ticker pada treemap atau ranking');ttk.Label(self.detail,textvariable=self.stock_header,font=('Segoe UI',13,'bold')).pack(anchor='w',padx=12,pady=5)
        self.price_canvas=tk.Canvas(self.detail,bg='white',height=220,highlightthickness=1,highlightbackground='#dce3ec');self.price_canvas.pack(fill='x',padx=10,pady=5)
        self.stock_text=tk.Text(self.detail,height=19,font=('Consolas',10),wrap='word');self.stock_text.pack(fill='both',expand=True,padx=10,pady=6)
        ttk.Button(self.detail,text='Buka Valuasi Saham Ini',command=lambda:self.tabs.select(self.valuation)).pack(anchor='e',padx=12,pady=5)
        # valuation
        vf=ttk.Frame(self.valuation,padding=12);vf.pack(fill='x')
        for i,(lab,var,opts) in enumerate([('Metode',self.method,['PER','PBV','EV/EBITDA'])]):
            ttk.Label(vf,text=lab).grid(row=i,column=0,sticky='w');b=ttk.Combobox(vf,textvariable=var,values=opts,state='readonly',width=16);b.grid(row=i,column=1,sticky='w',padx=8,pady=5);b.bind('<<ComboboxSelected>>',lambda e:self.update_valuation())
        fields=[('Target multiple (x)',self.target),('Forecast EPS manual (Rp; opsional)',self.manual_eps),('Forecast EBITDA (Rp juta; khusus EV)',self.ebitda),('Net debt (Rp juta; khusus EV)',self.net_debt),('Minority interest (Rp juta)',self.minority),('Aset nonoperasional (Rp juta)',self.extra_assets)]
        for i,(lab,var) in enumerate(fields,1):
            ttk.Label(vf,text=lab).grid(row=i,column=0,sticky='w',pady=3);ttk.Entry(vf,textvariable=var,width=20).grid(row=i,column=1,sticky='w',padx=8,pady=3)
        ttk.Button(vf,text='Hitung Harga Wajar',command=self.update_valuation).grid(row=len(fields)+1,column=1,sticky='w',pady=8)
        self.val_text=tk.Text(self.valuation,font=('Consolas',11),wrap='word');self.val_text.pack(fill='both',expand=True,padx=12,pady=8)
        # health
        ttk.Label(self.health,text='Database Quality & Capacity',font=('Segoe UI',15,'bold'),padding=12).pack(anchor='w')
        self.health_text=tk.Text(self.health,font=('Consolas',10),wrap='word');self.health_text.pack(fill='both',expand=True,padx=12,pady=8)
        ttk.Label(self,textvariable=self.status,anchor='w',padding=(12,4)).pack(fill='x')
        for cv in (self.market_canvas,self.foreign_canvas,self.tree_canvas,self.price_canvas):cv.bind('<Configure>',lambda e:self.redraw())
    def reload(self):
        self.master_data=load_master(MASTER)
        with ro_conn() as c:self.dates=[x[0] for x in c.execute('SELECT DISTINCT trade_date FROM daily ORDER BY trade_date DESC')]
        if not self.dates:raise ValueError('Belum ada data di tabel daily')
        self.date_box['values']=self.dates
        if self.date.get() not in self.dates:self.date.set(self.dates[0])
        self.sector_box['values']=['Semua Sektor']+sorted(set(x['sector'] for x in self.master_data.values()))
        self.refresh()
    def refresh(self):
        try:
            with ro_conn() as c:
                self.rows=snapshot(c,self.master_data,self.date.get())
                self.series=market_history(c,self.master_data,self.sector.get())
            self.filtered=[r for r in self.rows if self.sector.get()=='Semua Sektor' or r['sector']==self.sector.get()]
            ups=sum((r['change_pct'] or 0)>0 for r in self.filtered);downs=sum((r['change_pct'] or 0)<0 for r in self.filtered)
            foreign=sum(r['net'] or 0 for r in self.filtered)
            self.summary.set(f'{self.date.get()}   |   Saham: {len(self.filtered)}   |   Naik: {ups}  Turun: {downs}   |   Foreign net: {compact(foreign)} lembar')
            self.populate_ranks();self.render_health();self.redraw()
            if self.selected_ticker:self.open_stock(self.selected_ticker,select=False)
            self.status.set('Berhasil | Data SQLite read-only | Foreign dalam lembar saham | Indeks = proxy, bukan IHSG resmi')
        except Exception as e:self.status.set('ERROR: '+str(e));messagebox.showerror('Gagal membaca data',str(e))
    def populate_ranks(self):
        for tv,key,descending in self.rankings.values():
            for item in tv.get_children():tv.delete(item)
            values=[r for r in self.filtered if r.get(key) is not None]
            for r in sorted(values,key=lambda r:r[key],reverse=descending)[:20]:
                v=f'{r[key]:+.2f}%' if key=='change_pct' else compact(r[key])
                tv.insert('','end',values=(r['ticker'],r['sector'],v))
    def rank_open(self,tree):
        sel=tree.selection()
        if sel:self.open_stock(tree.item(sel[0],'values')[0])
    def line_plot(self,cv,values,title='',color=P_BLUE):
        cv.delete('all');w=max(cv.winfo_width(),320);h=max(cv.winfo_height(),80)
        data=[v for v in values if v is not None]
        if not data:return
        low=min(data);high=max(data);pad=(high-low)*.1 or 1;low-=pad;high+=pad
        coords=[]
        for i,v in enumerate(values):
            if v is None:continue
            x=40+(w-55)*i/max(1,len(values)-1);y=h-17-(v-low)/(high-low)*(h-32);coords.extend((x,y))
        cv.create_line(38,h-15,w-10,h-15,fill='#d1dae6')
        if len(coords)>=4:cv.create_line(*coords,fill=color,width=2.3)
        cv.create_text(5,6,anchor='nw',text=f'{min(data):,.1f}',font=('Segoe UI',8),fill='#6b7280')
        cv.create_text(w-5,6,anchor='ne',text=f'{max(data):,.1f}',font=('Segoe UI',8),fill='#6b7280')
    def redraw(self):
        if not self.series:return
        ordered=[x for x in self.series if x['date']<=self.date.get()]
        self.line_plot(self.market_canvas,[x['index'] for x in ordered][-160:])
        self.foreign_canvas.delete('all');cv=self.foreign_canvas;w=max(cv.winfo_width(),320);h=max(cv.winfo_height(),80)
        data=ordered[-45:];self.daily_hit=[]
        if data:
            vals=[r['net'] for r in data];lo=min(min(vals),0);hi=max(max(vals),0)
            if lo==hi:lo,hi=-1,1
            yy=lambda n:h-14-(n-lo)/(hi-lo)*(h-22)
            cv.create_line(35,yy(0),w-8,yy(0),fill='#7c8899');bw=(w-48)/len(data)
            for i,r in enumerate(data):
                x=35+(i+.5)*bw;end=yy(r['net']);zero=yy(0)
                cv.create_rectangle(x-max(1,bw*.3),min(end,zero),x+max(1,bw*.3),max(end,zero),fill=P_GREEN if r['net']>=0 else P_RED,outline='')
                self.daily_hit.append((x-max(3,bw*.45),x+max(3,bw*.45),r))
            cv.create_text(37,h-5,text=data[0]['date'],font=('Segoe UI',8),anchor='sw');cv.create_text(w-9,h-5,text=data[-1]['date'],font=('Segoe UI',8),anchor='se')
        self.draw_treemap()
    def click_foreign(self,event):
        for x0,x1,r in getattr(self,'daily_hit',[]):
            if x0<=event.x<=x1:self.date.set(r['date']);self.refresh();break
    def hover_foreign(self,event):
        for x0,x1,r in getattr(self,'daily_hit',[]):
            if x0<=event.x<=x1:
                self.hover_status.set(f"{r['date']} · {self.sector.get()} · Buy {compact(r['buy'])} · Sell {compact(r['sell'])} · Net {compact(r['net'])} lembar")
                return
    def draw_treemap(self):
        cv=self.tree_canvas;cv.delete('all');self.treemap_hit=[];w=max(cv.winfo_width(),400);h=max(cv.winfo_height(),220)
        pos=self.dates.index(self.date.get());dates=set(self.dates[pos:pos+int(self.period.get())])
        if len(dates)<int(self.period.get()):cv.create_text(w/2,h/2,text='Histori belum cukup');return
        with ro_conn() as c:
            bind=','.join('?' for _ in dates)
            agg={}
            for d,t,b,s in c.execute(f'SELECT trade_date,ticker,foreign_buy,foreign_sell FROM daily WHERE trade_date IN ({bind})',tuple(dates)):
                t=str(t or '').strip().upper()
                if t not in agg:agg[t]=[0.,0.,set()]
                if b is not None and s is not None:
                    agg[t][0]+=number(b) or 0;agg[t][1]+=number(s) or 0;agg[t][2].add(d)
        mode=self.mode.get();nodes=defaultdict(list)
        for t,(b,s,have) in agg.items():
            if len(have)!=len(dates):continue
            sec=self.master_data.get(t,{}).get('sector','Unknown')
            if self.sector.get()!='Semua Sektor' and sec!=self.sector.get():continue
            v={'net':b-s,'buy':b,'sell':s}[mode]
            if abs(v)>0:nodes[sec].append((t,v))
        allnodes=[(sec,sum(math.sqrt(abs(v)) for t,v in items),sorted(items,key=lambda x:abs(x[1]),reverse=True)) for sec,items in nodes.items()]
        allnodes.sort(key=lambda x:x[1],reverse=True)
        total=sum(x[1] for x in allnodes)
        if not total:cv.create_text(w/2,h/2,text='Tidak ada foreign flow untuk pilihan ini');return
        # Stable sector bands, squared-root visual sizing only; underlying figures unchanged.
        cx=0
        for sec,weight,items in allnodes:
            sw=w*weight/total
            if sw<3:cx+=sw;continue
            cv.create_rectangle(cx,0,cx+sw,h,fill='#eef3fa',outline='white',width=2)
            cv.create_rectangle(cx,0,cx+sw,min(24,h),fill='#273b5a',outline='white')
            if sw>65:cv.create_text(cx+4,12,text=sec[:int(sw/8)],fill='white',anchor='w',font=('Segoe UI',8,'bold'))
            cy=24;usable=max(1,h-24);tt=sum(math.sqrt(abs(v)) for t,v in items)
            for t,v in items:
                th=usable*math.sqrt(abs(v))/tt
                color=('#2e80bb' if mode=='buy' else '#e18a32' if mode=='sell' else P_GREEN if v>0 else P_RED)
                cv.create_rectangle(cx+1,cy,cx+sw-1,cy+th,fill=color,outline='white')
                self.treemap_hit.append((cx+1,cy,cx+sw-1,cy+th,t,v,sec))
                if th>15 and sw>35:cv.create_text(cx+sw/2,cy+th/2,text=t,font=('Segoe UI',8,'bold'),fill='white')
                cy+=th
            cx+=sw
    def hover_treemap(self,event):
        for x0,y0,x1,y1,t,v,sec in getattr(self,'treemap_hit',[]):
            if x0<=event.x<=x1 and y0<=event.y<=y1:
                self.status.set(f'{t} · {sec} · {self.mode.get()} {compact(v)} lembar · klik untuk Stock Detail');return
    def click_treemap(self,event):
        for x0,y0,x1,y1,t,v,sec in getattr(self,'treemap_hit',[]):
            if x0<=event.x<=x1 and y0<=event.y<=y1:self.open_stock(t);return
    def open_stock(self,ticker,select=True):
        t=ticker.strip().upper()
        if not t:return
        self.selected_ticker=t;self.ticker_var.set(t)
        with ro_conn() as c:
            cols={x['name'] for x in c.execute('PRAGMA table_info(daily)')}
            fields=[k if k in cols else f'NULL AS {k}' for k in ['trade_date','close','previous','volume','value','foreign_buy','foreign_sell']]
            rows=c.execute('SELECT '+','.join(fields)+' FROM daily WHERE ticker=? AND trade_date<=? ORDER BY trade_date',(t,self.date.get())).fetchall()
            self.finance=fundamentals(c,t)
        if not rows:
            self.stock_header.set(f'{t}: tidak ada histori hingga tanggal pilihan');return
        latest=rows[-1];price=number(latest['close']);previous=number(latest['previous']);change=100*(price/previous-1) if price and previous else None
        sec=self.master_data.get(t,{}).get('sector','Unknown')
        self.stock_header.set(f'{t} · {sec} · Close Rp{fmt(price)} · Return {fmt(change,2)}% · {latest["trade_date"]}')
        self.line_plot(self.price_canvas,[number(r['close']) for r in rows[-250:]],color=P_BLUE)
        q=self.finance['quarterly'];a=self.finance['annual'];text=[]
        text.append(f'PRICE HISTORY: {len(rows)} sesi tercatat | latest {latest["trade_date"]}\n')
        text.append('DATA KEUANGAN (nilai umumnya Rp juta, EPS Rp/saham; ROE dalam %)\n')
        for yr in sorted(a,reverse=True)[:4]:
            m=a[yr];text.append(f"FY{yr}  Revenue {fmt(m.get('revenue'))} | Net profit {fmt(m.get('net_income'))} | ROE {fmt(m.get('roe_reported'),2)}% | EPS {fmt(m.get('eps'),2)}")
        for yy,qq in sorted(q,reverse=True)[:4]:
            m=q[yy,qq];text.append(f"{yy} Q{qq} YTD  Revenue {fmt(m.get('revenue'))} | Net profit {fmt(m.get('net_income'))} | ROE {fmt(m.get('roe_reported'),2)}%")
        for met in ['total_assets','total_equity','long_term_debt','cash_equivalents','pbv_reported','per_reported','ev_ebitda_reported','roe_reported','roa_reported','der_reported']:
            val,period=latest_metric(self.finance,met);text.append(f'{met:<26} {fmt(val,2):>17}  ({period})')
        if not q and not a:text.append('\nBELUM ADA FUNDAMENTAL: impor Financial data TICKER.xlsx untuk mengisi data ini.')
        self.stock_text.delete('1.0','end');self.stock_text.insert('1.0','\n'.join(text))
        self.current_price=price;self.current_ticker=t
        self.update_valuation()
        if select:self.tabs.select(self.detail)
    def update_valuation(self):
        if not self.selected_ticker:return
        data=self.finance;t=self.selected_ticker;price=getattr(self,'current_price',None)
        shares=self.master_data.get(t,{}).get('shares')
        lines=[f'VALUATION FY2026E | {t} | Harga pasar Rp{fmt(price)} | Shares {fmt(shares)}',
               'Bukan rekomendasi investasi. Target multiple = asumsi analis, bukan nilai objektif.',
               '']
        def val(var):
            st=var.get().strip().replace(',','')
            return float(st) if st else None
        try:
            method=self.method.get();target=val(self.target)
            if target is None or target<=0:raise ValueError('Target multiple harus positif')
            fair=None;detail='';source='';basis=None
            if method=='PER':
                manual=val(self.manual_eps)
                if manual is not None:eps=manual;source='Forecast EPS manual dari analis'
                else:
                    profit,source=fy_profit_projection(data)
                    eps=profit*1e6/shares if profit is not None and shares and shares>0 else None
                if eps is not None and eps>0:fair=eps*target;basis=eps;detail=f'Forecast EPS: Rp{eps:,.2f} × PER {target:g}x'
                else:detail='Belum dapat dihitung: EPS FY2026E tidak tersedia/positif atau jumlah saham tidak valid.'
            elif method=='PBV':
                equity,p=latest_metric(data,'total_equity')
                if equity is not None and shares and shares>0 and equity>0:
                    bvps=equity*1e6/shares;fair=bvps*target;basis=bvps
                    source=f'Ekuitas snapshot {p}, bukan proyeksi ekuitas FY2026';detail=f'BVPS snapshot: Rp{bvps:,.2f} × PBV {target:g}x'
                else:detail='Ekuitas/saham beredar belum tersedia atau tidak positif.'
            else:
                eb=val(self.ebitda);debt=val(self.net_debt);mi=val(self.minority) or 0;assets=val(self.extra_assets) or 0
                if eb is not None and debt is not None and shares and shares>0 and eb>0:
                    ev=eb*target;eq=ev-debt-mi+assets;fair=eq*1e6/shares
                    detail=f'EBITDA forecast Rp{eb:,.0f} juta × {target:g}x − net debt {debt:,.0f} juta − minority {mi:,.0f} juta + other assets {assets:,.0f} juta'
                    source='Forecast EBITDA dan net debt = input manual analis; jangan isi dengan total liabilities'
                else:detail='Masukkan Forecast EBITDA dan Net Debt (Rp juta) secara manual; keduanya wajib untuk EV/EBITDA.'
            lines.extend([f'Metode: {method}',f'Basis: {detail}',f'Sumber/asumsi: {source}',''])
            if fair is not None and math.isfinite(fair):
                upside=100*(fair/price-1) if price and price>0 else None
                lines.extend([f'ESTIMASI HARGA WAJAR: Rp{fair:,.2f} per saham',f'Upside/downside vs harga saat ini: {fmt(upside,2)}%',
                              '\nSENSITIVITAS TARGET MULTIPLE (asumsi tetap):'])
                for factor,label in [(.8,'Bear 80%'),(1.,'Base 100%'),(1.2,'Bull 120%')]:
                    scenario=fair*factor if method!='EV/EBITDA' else ((val(self.ebitda)*target*factor)-(val(self.net_debt))-(val(self.minority) or 0)+(val(self.extra_assets) or 0))*1e6/shares
                    lines.append(f'{label:12} : Rp{scenario:,.2f}')
            else:lines.append('HARGA WAJAR: TIDAK DAPAT DIHITUNG dengan data saat ini.')
            lines.extend(['','PERINGATAN DATA:',
                '• Rasio lama bisa memakai harga historis; tidak digunakan sebagai harga wajar otomatis.',
                '• EPS/YTD historis tanpa tanggal publikasi tidak layak untuk backtest point-in-time.',
                '• Saham master = snapshot; tidak memodelkan diluted shares maupun corporate action.',
                '• Valuasi PBV menggunakan ekuitas snapshot terakhir, tidak mengklaim BVPS FY2026E.',
                '• Angka net_income importer mungkin tidak identik dengan laba atribusi induk.',
                '• EV/EBITDA perlu EBITDA forecast, net debt, minority, dan aset nonoperasional yang valid.',
                '• Metode EV/EBITDA tidak direkomendasikan untuk bank.'])
        except (ValueError,TypeError,ZeroDivisionError) as exc:lines.append('ERROR ASUMSI: '+str(exc))
        self.val_text.delete('1.0','end');self.val_text.insert('1.0','\n'.join(lines))
    def render_health(self):
        p=DB;size=p.stat().st_size if p.exists() else 0
        with ro_conn() as c:
            n=c.execute('SELECT COUNT(*) FROM daily').fetchone()[0]
            unique=c.execute('SELECT COUNT(DISTINCT trade_date),COUNT(DISTINCT ticker),MIN(trade_date),MAX(trade_date) FROM daily').fetchone()
            duplicates=c.execute('SELECT COUNT(*) FROM (SELECT trade_date,ticker FROM daily GROUP BY trade_date,ticker HAVING COUNT(*)>1)').fetchone()[0]
            fund=c.execute('SELECT COUNT(DISTINCT ticker) FROM fundamental').fetchone()[0] if table_exists(c,'fundamental') else 0
        lines=['DATABASE: '+str(p),'Ukuran saat ini: '+f'{size/1024/1024:,.2f} MB','Total rekaman: '+fmt(n),'Tanggal tersedia: '+str(unique[0]),'Ticker unik: '+str(unique[1]),'Awal: '+str(unique[2]),'Akhir: '+str(unique[3]),'Duplikasi tanggal-ticker: '+str(duplicates),'Ticker dengan fundamental kuartalan: '+str(fund),'Master ticker: '+str(len(self.master_data)),
              '\nKONTROL KUALITAS:','• Database dibaca read-only oleh aplikasi ini.','• Bar chart foreign berbasis lembar saham, bukan nilai rupiah.','• Proxy indeks bukan IHSG resmi dan dapat terdistorsi oleh missing dates / corporate action.','• Jumlah saham tercatat memakai snapshot master, tidak historical point-in-time.','• Simpan salinan DB dengan SQLite backup, bukan copy saat database sedang ditulis.','• Tambahkan indeks (ticker,trade_date) pada proses maintenance terpisah jika query melambat.','• Untuk histori harian selama bertahun-tahun, SQLite masih memadai.']
        self.health_text.delete('1.0','end');self.health_text.insert('1.0','\n'.join(lines))

if __name__=='__main__':App().mainloop()
