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
        super().__init__();self.title('BEI Equity Analytics V2.2 — Fundamental Charts')
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
        self.market_canvas=tk.Canvas(self.overview,bg='white',height=96,highlightthickness=1,highlightbackground='#dce3ec');self.market_canvas.pack(fill='x',padx=5)
        ttk.Label(self.overview,text='Foreign net harian (volume lembar saham) — klik batang untuk memilih tanggal',font=('Segoe UI',9,'bold')).pack(anchor='w',padx=5,pady=(5,0))
        self.foreign_canvas=tk.Canvas(self.overview,bg='white',height=59,highlightthickness=1,highlightbackground='#dce3ec');self.foreign_canvas.pack(fill='x',padx=5)
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
        # Resizable left/right Stock Detail workspace.
        self.stock_panes=ttk.PanedWindow(self.detail,orient='horizontal')
        self.stock_panes.pack(fill='both',expand=True,padx=10,pady=(1,5))
        self.stock_charts=ttk.Frame(self.stock_panes)
        viewer=ttk.LabelFrame(self.stock_panes,text='Financial Statement Viewer — Ctrl+C untuk copy',padding=6)
        self.stock_panes.add(self.stock_charts,weight=3)
        self.stock_panes.add(viewer,weight=2)
        price_controls=ttk.Frame(self.stock_charts)
        price_controls.pack(fill='x')
        ttk.Label(price_controls,text='Price History (Rp/saham)',font=('Segoe UI',9,'bold')).pack(side='left')
        self.price_height=tk.IntVar(value=85)
        ttk.Label(price_controls,text='Tinggi grafik:').pack(side='left',padx=(15,4))
        ttk.Scale(price_controls,from_=55,to=190,variable=self.price_height,orient='horizontal',
                  command=self.resize_price).pack(side='left',fill='x',expand=True,padx=(2,10))
        self.price_canvas=tk.Canvas(self.stock_charts,bg='white',height=85,highlightthickness=1,highlightbackground='#dce3ec')
        self.price_canvas.pack(fill='x',pady=(1,3))
        ttk.Label(self.stock_charts,text='X: Tanggal perdagangan | Y: Harga penutupan (Rp/saham)',font=('Segoe UI',8)).pack(anchor='w')
        chart_group=ttk.LabelFrame(self.stock_charts,text='Grafik fundamental — Annual / Quarterly YTD',padding=(5,3))
        chart_group.pack(fill='both',expand=True,pady=(3,3))
        # Vertical stacking gives readable labels at narrower left-panel widths.
        self.fin_canvases=[]
        for i,title in enumerate(('Income Statement: Revenue, Net Profit, Net Margin','Cash Flow: CFO, CFI, CFF','Balance Sheet: Assets, Liabilities, DER')):
            cell=ttk.Frame(chart_group);cell.pack(fill='both',expand=True,pady=2)
            ttk.Label(cell,text=title,font=('Segoe UI',9,'bold')).pack(anchor='w')
            cv=tk.Canvas(cell,bg='white',height=135,highlightthickness=1,highlightbackground='#dce3ec')
            cv.pack(fill='both',expand=True);self.fin_canvases.append(cv)
            cv.bind('<Configure>',lambda e:self.draw_financial_charts())
        tools=ttk.Frame(viewer);tools.pack(fill='x',pady=(0,5))
        ttk.Label(tools,text='Laporan:').pack(side='left')
        self.fin_view=tk.StringVar(value='Annual')
        for label in ('Annual','Quarterly'):
            ttk.Radiobutton(tools,text=label,variable=self.fin_view,value=label,command=self.on_fin_view_change).pack(side='left',padx=5)
        ttk.Button(tools,text='Copy Selected (Ctrl+C)',command=self.copy_financial_selected).pack(side='left',padx=5)
        ttk.Button(tools,text='Copy Entire Table',command=self.copy_financial_all).pack(side='left',padx=5)
        ttk.Button(tools,text='Copy for AI Analysis',command=self.copy_financial_ai).pack(side='left',padx=5)
        ttk.Button(tools,text='Export CSV',command=self.export_financial_csv).pack(side='left',padx=5)
        grid=ttk.Frame(viewer);grid.pack(fill='both',expand=True)
        self.fin_tree=ttk.Treeview(grid,show='headings',selectmode='extended',height=13)
        vs=ttk.Scrollbar(grid,orient='vertical',command=self.fin_tree.yview)
        hs=ttk.Scrollbar(grid,orient='horizontal',command=self.fin_tree.xview)
        self.fin_tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        self.fin_tree.grid(row=0,column=0,sticky='nsew');vs.grid(row=0,column=1,sticky='ns');hs.grid(row=1,column=0,sticky='ew')
        grid.columnconfigure(0,weight=1);grid.rowconfigure(0,weight=1)
        self.fin_tree.bind('<Control-c>',lambda event:self.copy_financial_selected())
        self.fin_tree.bind('<Control-C>',lambda event:self.copy_financial_selected())
        self.fin_status=tk.StringVar(value='Buka saham untuk melihat laporan.')
        ttk.Label(viewer,textvariable=self.fin_status).pack(anchor='w',pady=(4,0))
        ttk.Button(self.stock_charts,text='Buka Valuasi Saham Ini',command=lambda:self.tabs.select(self.valuation)).pack(anchor='e',padx=12,pady=5)
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
    def resize_price(self, value=None):
        if not hasattr(self,'price_canvas'):
            return
        self.price_canvas.configure(height=max(55,int(float(self.price_height.get()))))
        if getattr(self,'selected_ticker',''):
            # Redraw cached price history without re-reading SQLite.
            rows=getattr(self,'last_price_rows',[])
            if rows:self.draw_price_history(rows)

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
        self.last_price_rows=rows[-250:]
        self.draw_price_history(self.last_price_rows)
        self.draw_financial_charts()
        self.render_financial_table()
        self.current_price=price;self.current_ticker=t
        self.update_valuation()
        if select:self.tabs.select(self.detail)
    def draw_price_history(self,rows):
        cv=self.price_canvas;cv.delete('all')
        data=[(str(r['trade_date']),number(r['close'])) for r in rows]
        data=[(d,v) for d,v in data if v is not None and v>0]
        if not data:return
        w=max(cv.winfo_width(),440);h=max(cv.winfo_height(),120)
        x0,y0,x1,y1=66,14,w-54,h-28
        values=[v for _,v in data]
        lo=min(values);hi=max(values);delta=(hi-lo)*.10 or max(1,hi*.02)
        lo-=delta;hi+=delta
        xx=lambda i:x0+(x1-x0)*i/max(1,len(data)-1)
        yy=lambda v:y1-(v-lo)/(hi-lo)*(y1-y0)
        cv.create_line(x0,y1,x1,y1,fill='#a1adbb')
        cv.create_line(x0,y0,x0,y1,fill='#a1adbb')
        for i in range(3):
            v=lo+(hi-lo)*i/2;y=yy(v)
            cv.create_line(x0,y,x1,y,fill='#e9eff5')
            cv.create_text(x0-5,y,text=f'{v:,.0f}',anchor='e',font=('Segoe UI',8),fill='#586778')
        coords=[]
        for i,(date,value) in enumerate(data):coords.extend([xx(i),yy(value)])
        if len(coords)>=4:cv.create_line(*coords,fill=P_BLUE,width=2)
        for i in sorted(set([0,len(data)//2,len(data)-1])):
            cv.create_text(xx(i),y1+5,text=data[i][0][5:],anchor='n',font=('Segoe UI',8),fill='#59697a')
        cv.create_text(x1,y0,text='Rp/saham',anchor='ne',font=('Segoe UI',8,'bold'),fill='#59697a')

    FIN_METRICS = [
        ('INCOME STATEMENT',None,None),
        ('Revenue','revenue','Rp juta'),('Gross Profit','gross_profit','Rp juta'),
        ('Operating Profit','operating_profit','Rp juta'),('Income Before Tax','income_before_tax','Rp juta'),
        ('Net Income','net_income','Rp juta'),('EPS','eps','Rp/saham'),
        ('CASH FLOW',None,None),('Operating Cash Flow','cash_from_operating','Rp juta'),
        ('Investing Cash Flow','cash_from_investing','Rp juta'),('Financing Cash Flow','cash_from_financing','Rp juta'),
        ('BALANCE SHEET',None,None),('Cash Equivalents','cash_equivalents','Rp juta'),
        ('Current Assets','current_assets','Rp juta'),('Fixed Assets','fixed_assets','Rp juta'),
        ('Total Assets','total_assets','Rp juta'),('Current Liabilities','current_liabilities','Rp juta'),
        ('Long Term Debt','long_term_debt','Rp juta'),('Total Liabilities','total_liabilities','Rp juta'),
        ('Total Equity','total_equity','Rp juta'),('Minority Interest','minority_interest','Rp juta'),
        ('Outstanding Shares','outstanding_shares','juta lembar'),('BVPS','bvps','Rp/saham'),
        ('FINANCIAL RATIOS',None,None),('ROE','roe_reported','%'),('ROA','roa_reported','%'),
        ('Gross Margin','gross_margin_reported','%'),('Operating Margin','operating_margin_reported','%'),
        ('Net Profit Margin','net_margin_reported','%'),('Sales Growth','sales_growth_reported','%'),
        ('Net Income Growth','net_income_growth_reported','%'),('DER','der_reported','x'),
        ('PER','per_reported','x'),('PBV','pbv_reported','x'),('EV/EBITDA','ev_ebitda_reported','x'),
    ]
    
    def on_fin_view_change(self):
        self.render_financial_table()
        self.draw_financial_charts()

    def draw_financial_charts(self):
        """Three fundamental charts, all sourced directly from selected Annual or Quarterly records.
        Quarterly income/cash flow numbers are YTD, balance sheet values are snapshots.
        """
        if not hasattr(self,'fin_canvases'):return
        d=(getattr(self,'finance',{}) or {}).get('annual' if self.fin_view.get()=='Annual' else 'quarterly',{})
        periods=sorted(d)[-9:]
        labels=[f'FY{p}' if isinstance(p,int) else f'{p[0]}Q{p[1]}' for p in periods]
        specs=[
            (('revenue','net_income'),('Revenue','Net Profit'),'net_margin_reported','Net Margin','Rp miliar','%',('revenue','net_income')),
            (('cash_from_operating','cash_from_investing','cash_from_financing'),('CFO','CFI','CFF'),None,None,'Rp miliar',None,('cash_from_operating','cash_from_investing','cash_from_financing')),
            (('total_assets','total_liabilities'),('Assets','Liabilities'),'der_reported','DER','Rp miliar','x',('total_assets','total_liabilities'))]
        colors=['#287db8','#d45d56','#1c9978']
        for k,cv in enumerate(self.fin_canvases):
            cv.delete('all');w=max(cv.winfo_width(),260);h=max(cv.winfo_height(),150)
            metrics,names,line_metric,line_name,left_unit,right_unit,_=specs[k]
            x0,y0,x1,y1=52,29,w-38,h-35
            if not periods:
                cv.create_text(w/2,h/2,text='Data fundamental belum tersedia',fill='#66788b');continue
            values=[[d[p].get(m) for p in periods] for m in metrics]
            # Financial source uses million IDR; present chart in billion IDR.
            vals=[v/1000 for series in values for v in series if v is not None and math.isfinite(v)]
            if not vals:
                cv.create_text(w/2,h/2,text='Metrik tidak tersedia',fill='#66788b');continue
            lo=min(0,min(vals));hi=max(0,max(vals));span=hi-lo or 1
            lo-=.06*span;hi+=.06*span
            # reserve right axis for margin/DER when available
            secondary=[]
            for p in periods:
                v=d[p].get(line_metric) if line_metric else None
                if k==0 and v is None:
                    rev=d[p].get('revenue');profit=d[p].get('net_income')
                    if rev and profit is not None:v=100*profit/rev
                secondary.append(v if v is not None and math.isfinite(v) else None)
            sec_vals=[v for v in secondary if v is not None]
            sl=min(0,min(sec_vals)) if sec_vals else 0
            sh=max(sec_vals) if sec_vals else 1
            if sh==sl:sh=sl+1
            xx=lambda i:x0+(i+.5)*(x1-x0)/len(periods)
            yy=lambda v:y1-(v-lo)/(hi-lo)*(y1-y0)
            ys=lambda v:y1-(v-sl)/(sh-sl)*(y1-y0)
            cv.create_line(x0,y1,x1,y1,fill='#9aa8b7')
            cv.create_line(x0,y0,x0,y1,fill='#9aa8b7')
            if sec_vals:cv.create_line(x1,y0,x1,y1,fill='#9aa8b7')
            for i in range(3):
                value=lo+(hi-lo)*i/2;y=yy(value)
                cv.create_line(x0,y,x1,y,fill='#eef2f5')
                cv.create_text(x0-4,y,text=f'{value:,.0f}',font=('Segoe UI',7),anchor='e',fill='#52677c')
                if sec_vals:cv.create_text(x1+3,y,text=f'{(sl+(sh-sl)*i/2):,.1f}',font=('Segoe UI',7),anchor='w',fill='#52677c')
            cv.create_text(x0,y0-19,text=left_unit,anchor='w',font=('Segoe UI',8,'bold'),fill='#536579')
            if sec_vals:cv.create_text(x1,y0-19,text=right_unit,anchor='e',font=('Segoe UI',8,'bold'),fill='#536579')
            width=(x1-x0)/len(periods)
            for i,p in enumerate(periods):
                for j,arr in enumerate(values):
                    value=arr[i]
                    if value is None or not math.isfinite(value):continue
                    v=value/1000
                    barw=min(10,width*.65/max(1,len(metrics)))
                    bx=xx(i)+(j-(len(metrics)-1)/2)*barw*1.1
                    by=yy(v);zero=yy(0)
                    cv.create_rectangle(bx-barw*.47,min(by,zero),bx+barw*.47,max(by,zero),fill=colors[j],outline='')
                if len(periods)<=6 or i%2==0 or i==len(periods)-1:
                    cv.create_text(xx(i),y1+9,text=labels[i],font=('Segoe UI',7),anchor='n',fill='#52677c')
            if sec_vals:
                pts=[]
                for i,v in enumerate(secondary):
                    if v is None:
                        if len(pts)>=4:cv.create_line(*pts,fill='#854fa0',width=2)
                        pts=[];continue
                    pts.extend([xx(i),ys(v)])
                    cv.create_oval(xx(i)-2,ys(v)-2,xx(i)+2,ys(v)+2,fill='#854fa0',outline='')
                if len(pts)>=4:cv.create_line(*pts,fill='#854fa0',width=2)
            legend=list(zip(names,colors))
            if line_name and sec_vals:legend.append((line_name,'#854fa0'))
            # Legend below axis, compact enough to work at common Windows desktop widths
            for j,(name,color) in enumerate(legend):
                x=6+j*(w-10)/len(legend)
                cv.create_rectangle(x,h-12,x+7,h-6,fill=color,outline='')
                cv.create_text(x+10,h-9,text=name,anchor='w',font=('Segoe UI',7),fill='#3c4b60')
            if self.fin_view.get()=='Quarterly':
                cv.create_text(w/2,16,text='Arus laba/CF: YTD | Neraca: snapshot',font=('Segoe UI',7),fill='#666666')

    def financial_matrix(self):
        """Return display matrix with stable period columns; annual vs quarterly YTD/snapshot."""
        fund=getattr(self,'finance',{}) or {}
        mode=self.fin_view.get()
        data=fund.get('annual' if mode=='Annual' else 'quarterly',{})
        periods=sorted(data)  # chronological: oldest left, newest right
        if mode=='Annual': labels=[f'FY{y}' for y in periods]
        else: labels=[f'{y} Q{q}' for y,q in periods]
        heads=['Financial Data','Unit']+labels
        matrix=[]
        for caption,key,unit in self.FIN_METRICS:
            if key is None:
                matrix.append([caption,'']+['']*len(periods));continue
            vals=[]
            for p in periods:
                v=data[p].get(key)
                if v is None:vals.append('')
                elif unit in ('%','x'):vals.append(f'{v:,.2f}')
                elif unit=='Rp/saham':vals.append(f'{v:,.2f}')
                else:vals.append(f'{v:,.0f}')
            matrix.append([caption,unit]+vals)
        return heads,matrix
    
    def render_financial_table(self):
        if not hasattr(self,'fin_tree'):return
        headers,rows=self.financial_matrix()
        tree=self.fin_tree
        for iid in tree.get_children():tree.delete(iid)
        columns=[f'c{i}' for i in range(len(headers))]
        tree.configure(columns=columns)
        for i,(key,label) in enumerate(zip(columns,headers)):
            tree.heading(key,text=label)
            tree.column(key,width=190 if i==0 else 105 if i==1 else 124,
                        minwidth=90,stretch=False,anchor='w' if i<=1 else 'e')
        for i,row in enumerate(rows):
            tree.insert('','end',iid=f'row{i}',values=row,tags=('section',) if row[1]=='' else ())
        tree.tag_configure('section',background='#e9eef5',foreground='#173355')
        self.fin_headers=headers;self.fin_rows=rows
        ticker=getattr(self,'selected_ticker','')
        period_note='FY annual' if self.fin_view.get()=='Annual' else 'Quarterly: flows YTD kumulatif; neraca snapshot; rasio sesuai sumber'
        self.fin_status.set(f'{ticker} | {len(headers)-2} periode | {period_note} | angka kosong = tidak tersedia')
    
    def _copy_tsv(self,rows):
        output='\n'.join('\t'.join(str(v) for v in row) for row in rows)
        self.clipboard_clear();self.clipboard_append(output);self.update()
        self.status.set(f'Disalin ke clipboard: {max(len(rows)-1,0)} baris. Tempel di Excel dengan Ctrl+V.')
    
    def copy_financial_selected(self):
        if not getattr(self,'fin_rows',None):return
        selected={int(iid[3:]) for iid in self.fin_tree.selection() if iid.startswith('row')}
        if not selected:
            messagebox.showinfo('Pilih baris','Pilih satu atau beberapa baris dengan Ctrl/Shift, lalu tekan Ctrl+C.')
            return
        self._copy_tsv([self.fin_headers]+[r for i,r in enumerate(self.fin_rows) if i in selected])
    
    def copy_financial_all(self):
        if hasattr(self,'fin_rows'):self._copy_tsv([self.fin_headers]+self.fin_rows)
    
    def copy_financial_ai(self):
        if not hasattr(self,'fin_rows'):return
        ticker=getattr(self,'selected_ticker','')
        meta=[f'Ticker: {ticker}',f'Data: Financial Statements ({self.fin_view.get()})',
              f'Sumber: database SQLite fundamental / fundamental_annual; nilai yang tidak ada dibiarkan kosong.',
              'Satuan: lihat kolom Unit; Rp juta berarti jutaan rupiah, bukan rupiah.',
              'Quarterly: metrik aliran (laba/pendapatan/arus kas) adalah YTD kumulatif; metrik neraca adalah snapshot.',
              'Rasio merupakan rasio yang dilaporkan sumber; bukan perhitungan ulang berdasarkan harga terkini.',
              'Tanggal publikasi mungkin tidak tersedia; jangan gunakan sebagai data point-in-time untuk backtest.','']
        content='\n'.join(meta)+'\n'.join('\t'.join(map(str,r)) for r in [self.fin_headers]+self.fin_rows)
        self.clipboard_clear();self.clipboard_append(content);self.update()
        self.status.set(f'Data {ticker} disalin dengan konteks analisis AI.')
    
    def export_financial_csv(self):
        if not hasattr(self,'fin_rows'):return
        tick=getattr(self,'selected_ticker','SAHAM')
        file=filedialog.asksaveasfilename(title='Export Fundamental',defaultextension='.csv',
          initialfile=f'{tick}_Financial_{self.fin_view.get()}.csv',filetypes=[('CSV','*.csv')])
        if not file:return
        with open(file,'w',newline='',encoding='utf-8-sig') as f:
            writer=csv.writer(f);writer.writerow(self.fin_headers);writer.writerows(self.fin_rows)
        self.status.set(f'Export CSV: {file}')
    
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
