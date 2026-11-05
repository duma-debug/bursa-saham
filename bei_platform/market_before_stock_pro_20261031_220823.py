from .theme import ThemeCanvas
#!/usr/bin/env python3
"""BEI Equity Analytics V2. Pure Tkinter + SQLite read-only. No external packages."""
import csv,math,sqlite3,datetime,tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import ttk,messagebox,filedialog
from bei_analytics import load_master,number
from .official_indices import import_folder,index_history,index_codes,start_date,FOLDER
BASE=Path(__file__).resolve().parent.parent
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
    ans=[]
    for day in dates:
        rows=snapshot(c,master,day)
        if sector!='Semua Sektor':rows=[r for r in rows if r['sector']==sector]
        ans.append({'date':day,'buy':sum(r['foreign_buy'] or 0 for r in rows),'sell':sum(r['foreign_sell'] or 0 for r in rows),'net':sum(r['net'] or 0 for r in rows),'coverage':sum(r['net'] is not None for r in rows)})
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

def short_sector(value):
    abbreviations={'Consumer cyclical':'Cons.Cyc','Consumer non-cyclical':'Cons.Non','Financial':'Fin','Financials':'Fin','Technology':'Tech','Basic materials':'Materials','Property & real estate':'Property','Infrastructure':'Infra','Industrial':'Ind','Industrials':'Ind','Healthcare':'Health','Transportation & logistic':'Transport'}
    return abbreviations.get(value,value[:12] if value else '—')

def aggregate_foreign(rows,frequency='Harian'):
    if frequency=='Harian':return list(rows)
    groups={}
    for row in rows:
        day=datetime.date.fromisoformat(row['date'])
        if frequency=='Mingguan':
            start=day-datetime.timedelta(days=day.weekday());key=start.isoformat();label=f"{start:%Y-%m-%d} s.d. {start+datetime.timedelta(days=6):%Y-%m-%d}"
        else:key=row['date'][:7];label=key
        if key not in groups:groups[key]={'date':key,'label':label,'buy':0,'sell':0,'net':0}
        for col in ('buy','sell','net'):groups[key][col]+=row.get(col,0) or 0
    return list(groups.values())

class MarketModule(ttk.Frame):
    def __init__(self,parent,on_research=None):
        super().__init__(parent)
        self.on_research = on_research
        self.master_data={};self.dates=[];self.rows=[];self.series=[];self.selected_ticker='';self.finance={};self.picked=None
        self.date=tk.StringVar();self.sector=tk.StringVar(value='Semua Sektor');self.period=tk.StringVar(value='5');self.mode=tk.StringVar(value='net')
        self.ticker_var=tk.StringVar();self.method=tk.StringVar(value='PER');self.target=tk.StringVar(value='10');self.manual_eps=tk.StringVar(value='');self.net_debt=tk.StringVar(value='');self.ebitda=tk.StringVar(value='');self.minority=tk.StringVar(value='0');self.extra_assets=tk.StringVar(value='0')
        self.status=tk.StringVar(value='Memuat data...')
        self.foreign_frequency=tk.StringVar(value='Harian');self.index_code=tk.StringVar(value='COMPOSITE');self.index_series=[];self.index_hit=[];self.cap_hit=[]
        self.zoom_level=1.0;self.zoom_offset=0;self.zoom_window=None;self._zoom_base=None
        self._build()
        try:self.reload()
        except Exception as e:self.status.set('GAGAL: '+str(e));messagebox.showwarning('File belum siap',str(e))
    def _build(self):
        head=ttk.Frame(self,padding=10);head.pack(fill='x')
        ttk.Label(head,text='BEI Equity Analytics',font=('Segoe UI',20,'bold')).pack(side='left')
        ttk.Label(head,text='  ·  Analisis harga · foreign flow · fundamental · valuasi',font=('Segoe UI',10)).pack(side='left')
        ttk.Button(head,text='Muat ulang data',command=self.reload).pack(side='right')
        ttk.Button(head,text='Impor Indeks BEI',command=self.import_indices_clicked).pack(side='right',padx=(0,8))
        controls=ttk.Frame(self,padding=(11,5));controls.pack(fill='x')
        for label,var,opts,w in [('Tanggal',self.date,[],16),('Sektor',self.sector,[],23),('Foreign 1/5/10/20D',self.period,['1','5','10','20'],8),('Treemap',self.mode,['net','buy','sell'],8)]:
            ttk.Label(controls,text=label).pack(side='left',padx=(8,3));box=ttk.Combobox(controls,textvariable=var,values=opts,width=w,state='readonly');box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda e:self.refresh());
            if label=='Tanggal':self.date_box=box
            if label=='Sektor':self.sector_box=box
        ttk.Label(controls,text='Foreign',font=('Segoe UI',9)).pack(side='left',padx=(10,3))
        frequency_box=ttk.Combobox(controls,textvariable=self.foreign_frequency,values=['Harian','Mingguan','Bulanan'],width=10,state='readonly')
        frequency_box.pack(side='left');frequency_box.bind('<<ComboboxSelected>>',lambda e:self.redraw())
        ttk.Label(controls,text='Indeks').pack(side='left',padx=(10,3))
        self.index_box=ttk.Combobox(controls,textvariable=self.index_code,values=['COMPOSITE'],width=12,state='readonly')
        self.index_box.pack(side='left');self.index_box.bind('<<ComboboxSelected>>',lambda e:self.index_changed())
        ttk.Button(controls,text='Refresh',command=self.refresh).pack(side='left',padx=6)
        for title,cmd in [('−',lambda:self.zoom_charts(.65)),('+',lambda:self.zoom_charts(1.5)),('◀',lambda:self.pan_charts(-1)),('▶',lambda:self.pan_charts(1)),('Reset zoom',self.reset_zoom)]:
            ttk.Button(controls,text=title,command=cmd,width=4 if len(title)==1 else 10 if title=='Reset zoom' else 3).pack(side='left',padx=1)
        tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True,padx=11,pady=5);self.tabs=tabs
        self.overview=ttk.Frame(tabs);self.detail=ttk.Frame(tabs);self.valuation=ttk.Frame(tabs);self.health=ttk.Frame(tabs)
        for obj,name in [(self.overview,'Market Overview'),(self.detail,'Stock Detail'),(self.valuation,'Valuation FY2026E'),(self.health,'Data Health')]:tabs.add(obj,text=name)
        # Overview: IHSG, market cap and foreign flow share a single horizontal row.
        f=ttk.Frame(self.overview);f.pack(fill='x',padx=5,pady=3)
        self.summary=tk.StringVar(value='Memuat...');ttk.Label(f,textvariable=self.summary,font=('Segoe UI',11,'bold')).pack(side='left')
        charts=ttk.Frame(self.overview);charts.pack(fill='x',padx=5,pady=5)
        for col in range(3):
            charts.columnconfigure(col,weight=1,uniform='market_chart_columns')
        left_chart=ttk.Frame(charts);right_chart=ttk.Frame(charts);bottom_chart=ttk.Frame(charts)
        left_chart.grid(row=0,column=0,sticky='nsew',padx=(0,4))
        right_chart.grid(row=0,column=1,sticky='nsew',padx=4)
        bottom_chart.grid(row=0,column=2,sticky='nsew',padx=(4,0))
        ttk.Label(left_chart,text='Indeks Resmi BEI | X: Tanggal perdagangan | Y: Poin indeks',font=('Segoe UI',9,'bold')).pack(anchor='w')
        self.market_canvas=ThemeCanvas(left_chart,bg='white',height=145,highlightthickness=1,highlightbackground='#dce3ec');self.market_canvas.pack(fill='x')
        self.market_canvas.bind('<Motion>',self.hover_index);self.market_canvas.bind('<Leave>',self.leave_index)
        self.market_canvas.bind('<MouseWheel>',self.wheel_zoom);self.market_canvas.bind('<Button-4>',lambda e:self.zoom_charts(1.5));self.market_canvas.bind('<Button-5>',lambda e:self.zoom_charts(.65))
        ttk.Label(right_chart,text='Market Cap BEI | X: Tanggal | Y: Rp triliun',font=('Segoe UI',9,'bold')).pack(anchor='w')
        self.cap_canvas=ThemeCanvas(right_chart,bg='white',height=145,highlightthickness=1,highlightbackground='#dce3ec');self.cap_canvas.pack(fill='x')
        self.cap_canvas.bind('<Motion>',self.hover_cap);self.cap_canvas.bind('<Leave>',lambda e:self.cap_canvas.delete('cap_tooltip'))
        self.cap_canvas.bind('<MouseWheel>',self.wheel_zoom);self.cap_canvas.bind('<Button-4>',lambda e:self.zoom_charts(1.5));self.cap_canvas.bind('<Button-5>',lambda e:self.zoom_charts(.65))
        ttk.Label(bottom_chart,text='Foreign Net | Miliar lembar | Tooltip: Buy/Sell/Net',font=('Segoe UI',9,'bold')).pack(anchor='w')
        self.index_info=tk.StringVar(value='Menunggu data resmi BEI')
        self.index_hover=tk.StringVar(value='Arahkan kursor pada grafik IHSG untuk melihat tanggal dan penutupan.')
        ttk.Label(self.overview,textvariable=self.index_info,foreground='#425a72').pack(anchor='w',padx=6,after=charts)
        ttk.Label(self.overview,textvariable=self.index_hover,foreground='#425a72').pack(anchor='w',padx=6,after=charts)
        self.foreign_canvas=ThemeCanvas(bottom_chart,bg='white',height=145,highlightthickness=1,highlightbackground='#dce3ec');self.foreign_canvas.pack(fill='x')
        self.foreign_canvas.bind('<Button-1>',self.click_foreign);self.foreign_canvas.bind('<Motion>',self.hover_foreign);self.foreign_canvas.bind('<Leave>',self.leave_foreign)
        self.foreign_canvas.bind('<MouseWheel>',self.wheel_zoom);self.foreign_canvas.bind('<Button-4>',lambda e:self.zoom_charts(1.5));self.foreign_canvas.bind('<Button-5>',lambda e:self.zoom_charts(.65))
        self.hover_status=tk.StringVar(value='Foreign: jumlah lembar saham, bukan nilai transaksi Rp.');ttk.Label(self.overview,textvariable=self.hover_status).pack(anchor='w',padx=5)
        mid=ttk.PanedWindow(self.overview,orient='horizontal');mid.pack(fill='both',expand=True,padx=5,pady=5)
        left=ttk.Frame(mid);right=ttk.Frame(mid);mid.add(left,weight=4);mid.add(right,weight=3)
        tree_title=ttk.Label(left,text='Treemap Sector → Ticker  ↗  (klik judul untuk layar penuh)',font=('Segoe UI',10,'bold'),foreground='#1258a2',cursor='hand2')
        tree_title.pack(anchor='w')
        tree_title.bind('<Button-1>',lambda e:self.open_treemap_fullscreen())
        self.tree_canvas=ThemeCanvas(left,bg='white',highlightthickness=1,highlightbackground='#dce3ec',height=230);self.tree_canvas.pack(fill='both',expand=True)
        self.tree_canvas.bind('<Button-1>',self.click_treemap);self.tree_canvas.bind('<Motion>',self.hover_treemap)
        self.tree_canvas.bind('<Leave>',lambda e:self.hide_tree_tip())
        self._tree_views={} ; self._tree_tip=None; self._tree_full_window=None
        self.ranking_tabs=ttk.Notebook(right);self.ranking_tabs.pack(fill='both',expand=True)
        specs=[('Top Gainers','change_pct',True),('Top Losers','change_pct',False),('Top Volume','volume',True),('Top Value','value',True),('Foreign Buy','net',True),('Foreign Sell','net',False)]
        self.rankings={}
        for name,key,descending in specs:
            fr=ttk.Frame(self.ranking_tabs);self.ranking_tabs.add(fr,text=name)
            tv=ttk.Treeview(fr,columns=('ticker','sector','close','number','value','foreign'),show='headings',height=9)
            for col,title,width in [('ticker','Kode',68),('sector','Sektor',78),('close','Close',75),('number','Chg% / Rank',100),('value','Value Rp',93),('foreign','F.Net',90)]:
                tv.heading(col,text=title)
                tv.column(col,width=width,minwidth=65,anchor='e' if col in ('close','number') else 'w',stretch=col=='sector')
            sy=ttk.Scrollbar(fr,orient='vertical',command=tv.yview)
            sx=ttk.Scrollbar(fr,orient='horizontal',command=tv.xview)
            tv.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
            tv.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew')
            fr.columnconfigure(0,weight=1);fr.rowconfigure(0,weight=1)
            tv.bind('<Double-1>',lambda e,tv=tv:self.rank_open(tv))
            tv.bind('<Motion>',lambda e,tv=tv:self.hover_rank(e,tv))
            self.rankings[name]=(tv,key,descending)
        self.rank_hint=tk.StringVar(value='Arahkan kursor ke saham untuk nama perusahaan, close, dan gain/loss. Klik dua kali untuk Stock Detail.')
        ttk.Label(right,textvariable=self.rank_hint,wraplength=560).pack(anchor='w',fill='x',padx=3,pady=2)
        # Stock detail
        dtop=ttk.Frame(self.detail,padding=9);dtop.pack(fill='x')
        ttk.Label(dtop,text='Ticker:').pack(side='left');ttk.Entry(dtop,textvariable=self.ticker_var,width=13).pack(side='left',padx=6)
        ttk.Button(dtop,text='Buka Saham',command=lambda:self.open_stock(self.ticker_var.get())).pack(side='left')
        self.logo_img=None
        self.identity_frame=ttk.Frame(self.detail,padding=(12,0))
        self.identity_frame.pack(fill='x')
        self.logo_label=ttk.Label(self.identity_frame,text='LOGO',width=9,anchor='center')
        self.logo_label.pack(side='left',padx=(0,12))
        self.freefloat_text=tk.StringVar(value='Free float: belum tersedia')
        ttk.Label(self.identity_frame,textvariable=self.freefloat_text).pack(side='left')
        self.stock_header=tk.StringVar(value='Klik ticker pada treemap atau ranking');ttk.Label(self.detail,textvariable=self.stock_header,font=('Segoe UI',13,'bold')).pack(anchor='w',padx=12,pady=5)
        # Stock Snapshot: display listed shares from master, without rewriting reported financials.
        self.stock_snapshot=tk.StringVar(value='Outstanding Shares: —    |    Market Cap: —    |    BVPS: —    |    PBV: —')
        ttk.Label(self.detail,textvariable=self.stock_snapshot,
                  font=('Segoe UI',10,'bold'),wraplength=1200,justify='left').pack(anchor='w',padx=12,pady=(0,5),fill='x')

        # Resizable left/right Stock Detail workspace.
        self.stock_panes=ttk.PanedWindow(self.detail,orient='horizontal')
        self.stock_panes.pack(fill='both',expand=True,padx=10,pady=(1,5))
        chart_host=ttk.Frame(self.stock_panes)
        self.stock_scroller=tk.Canvas(chart_host,highlightthickness=0,borderwidth=0)
        chart_scroll=ttk.Scrollbar(chart_host,orient='vertical',command=self.stock_scroller.yview)
        self.stock_scroller.configure(yscrollcommand=chart_scroll.set)
        self.stock_scroller.pack(side='left',fill='both',expand=True)
        chart_scroll.pack(side='right',fill='y')
        self.stock_charts=ttk.Frame(self.stock_scroller)
        self._stock_window=self.stock_scroller.create_window((0,0),window=self.stock_charts,anchor='nw')
        self.stock_charts.bind('<Configure>',lambda e:self.stock_scroller.configure(scrollregion=self.stock_scroller.bbox('all')))
        self.stock_scroller.bind('<Configure>',lambda e:self.stock_scroller.itemconfigure(self._stock_window,width=e.width))
        # Wheel scroll inside Stock Detail only when Control is not held.
        def stock_wheel(event):
            if event.state & 0x4:return
            self.stock_scroller.yview_scroll(-1 if event.delta>0 else 1,'units')
        self.stock_scroller.bind('<MouseWheel>',stock_wheel)
        viewer=ttk.LabelFrame(self.stock_panes,text='Financial Statement Viewer — Ctrl+C untuk copy',padding=6)
        self.stock_panes.add(chart_host,weight=3)
        self.stock_panes.add(viewer,weight=2)
        price_controls=ttk.Frame(self.stock_charts)
        price_controls.pack(fill='x')
        ttk.Label(price_controls,text='Price History (Rp/saham)',font=('Segoe UI',9,'bold')).pack(side='left')
        self.price_height=tk.IntVar(value=85)
        ttk.Label(price_controls,text='Tinggi grafik:').pack(side='left',padx=(15,4))
        ttk.Scale(price_controls,from_=55,to=190,variable=self.price_height,orient='horizontal',
                  command=self.resize_price).pack(side='left',fill='x',expand=True,padx=(2,10))
        self.price_canvas=ThemeCanvas(self.stock_charts,bg='white',height=85,highlightthickness=1,highlightbackground='#dce3ec')
        self.price_canvas.pack(fill='x',pady=(1,3))
        self.price_info=tk.StringVar(value='Arahkan kursor ke garis: Tanggal dan Close akan tampil di sini.')
        ttk.Label(self.stock_charts,textvariable=self.price_info,font=('Segoe UI',8)).pack(anchor='w')
        self.price_canvas.bind('<Motion>',self.hover_price_history)
        self.price_canvas.bind('<Leave>',lambda e:self.price_info.set('Arahkan kursor ke garis: Tanggal dan Close akan tampil di sini.'))
        nav=ttk.Frame(self.stock_charts);nav.pack(fill='x')
        ttk.Label(nav,text='Navigasi histori saham:').pack(side='left')
        for title,command in [('◀',lambda:self.pan_stock(-1)),('▶',lambda:self.pan_stock(1)),('＋',lambda:self.zoom_stock(.7)),('－',lambda:self.zoom_stock(1.4)),('Reset',self.reset_stock_zoom)]:
            ttk.Button(nav,text=title,command=command,width=6).pack(side='left',padx=2)
        self.stock_visible=65
        self.stock_end=None
        ttk.Label(self.stock_charts,text='Sumbu X: tanggal perdagangan (YYYY-MM-DD) | Sumbu Y: harga penutupan (Rp/saham)',font=('Segoe UI',8)).pack(anchor='w')
        flow_bar=ttk.Frame(self.stock_charts);flow_bar.pack(fill='x',pady=(5,0))
        ttk.Label(flow_bar,text='Foreign Flow per Saham (lembar) — Buy / Sell dan Net terpisah',font=('Segoe UI',9,'bold')).pack(side='left')
        ttk.Button(flow_bar,text='Buka grafik besar ↗',command=self.open_stock_foreign_window).pack(side='right')
        ttk.Button(flow_bar,text='Ekspor IG PNG',command=self.export_stock_flow_ig).pack(side='right',padx=(0,8))
        ttk.Label(self.stock_charts,text='Foreign Buy (hijau) vs Foreign Sell (merah) — kedua batang positif',font=('Segoe UI',8)).pack(anchor='w')
        self.stock_flow_buy_canvas=ThemeCanvas(self.stock_charts,bg='white',height=88,highlightthickness=1,highlightbackground='#dce3ec')
        self.stock_flow_buy_canvas.pack(fill='x',pady=(1,2))
        ttk.Label(self.stock_charts,text='Foreign Net — hijau: Net Buy | merah: Net Sell',font=('Segoe UI',8)).pack(anchor='w')
        self.stock_flow_net_canvas=ThemeCanvas(self.stock_charts,bg='white',height=88,highlightthickness=1,highlightbackground='#dce3ec')
        self.stock_flow_net_canvas.pack(fill='x',pady=(1,3))
        ttk.Label(self.stock_charts,text='Sumbu X: Tanggal perdagangan (YYYY-MM-DD) | Sumbu Y: Lembar saham',font=('Segoe UI',8),foreground='#526679').pack(anchor='w')
        self.stock_flow_info=tk.StringVar(value='Arahkan kursor ke batang untuk melihat Tanggal, Buy, Sell, dan Net.')
        ttk.Label(self.stock_charts,textvariable=self.stock_flow_info,justify='left',wraplength=680,foreground='#18324b',font=('Segoe UI',8)).pack(anchor='w',pady=(1,3))
        for hist_cv in (self.price_canvas,self.stock_flow_buy_canvas,self.stock_flow_net_canvas):
            hist_cv.bind('<Shift-MouseWheel>',lambda e:self.pan_stock(-1 if e.delta>0 else 1))
            hist_cv.bind('<Control-MouseWheel>',lambda e:self.zoom_stock(.8 if e.delta>0 else 1.25))
        for flow_cv in (self.stock_flow_buy_canvas,self.stock_flow_net_canvas):
            flow_cv._flow_info=self.stock_flow_info
            flow_cv.bind('<Configure>',lambda e:self.draw_stock_flow())
            flow_cv.bind('<Motion>',lambda e,cv=flow_cv:self.hover_stock_flow(e,cv))
            flow_cv.bind('<Leave>',lambda e,cv=flow_cv:cv.delete('stock_tip'))
        chart_group=ttk.LabelFrame(self.stock_charts,text='Grafik fundamental — Annual / Quarterly YTD',padding=(5,3))
        chart_group.pack(fill='x',pady=(3,3))
        graph_nav=ttk.Frame(chart_group);graph_nav.pack(fill='x')
        ttk.Label(graph_nav,text='Histori fundamental:').pack(side='left')
        for title,step in [('◀ Periode lama',-1),('Periode baru ▶',1)]:
            ttk.Button(graph_nav,text=title,command=lambda direction=step:self.pan_financial_charts(direction)).pack(side='left',padx=3)
        ttk.Button(graph_nav,text='Reset',command=self.reset_financial_charts).pack(side='left',padx=3)
        self.fin_chart_end=None
        # Vertical stacking gives readable labels at narrower left-panel widths.
        self.fin_canvases=[]
        for i,title in enumerate(('Income Statement: Revenue, Net Profit, Net Margin','Cash Flow: CFO, CFI, CFF','Balance Sheet: Assets, Liabilities, DER')):
            cell=ttk.Frame(chart_group);cell.pack(fill='x',pady=2)
            ttk.Label(cell,text=title,font=('Segoe UI',9,'bold')).pack(anchor='w')
            cv=ThemeCanvas(cell,bg='white',height=135,highlightthickness=1,highlightbackground='#dce3ec')
            cv.pack(fill='x');self.fin_canvases.append(cv)
            cv.bind('<Configure>',lambda e:self.draw_financial_charts())
            cv.bind('<Shift-MouseWheel>',lambda e:self.pan_financial_charts(-1 if e.delta>0 else 1))
        tools=ttk.Frame(viewer);tools.pack(fill='x',pady=(0,5))
        ttk.Label(viewer,text='Satuan: Rp juta, kecuali EPS/BVPS (Rp per saham), saham beredar (juta lembar), serta rasio (% atau x).',wraplength=700,foreground='#325574').pack(anchor='w',pady=(0,5))
        ttk.Label(tools,text='Laporan:').pack(side='left')
        self.fin_view=tk.StringVar(value='Annual')
        for label in ('Annual','Quarterly'):
            ttk.Radiobutton(tools,text=label,variable=self.fin_view,value=label,command=self.on_fin_view_change).pack(side='left',padx=5)
        ttk.Button(tools,text='Copy Selected (Ctrl+C)',command=self.copy_financial_selected).pack(side='left',padx=5)
        ttk.Button(tools,text='Copy Entire Table',command=self.copy_financial_all).pack(side='left',padx=5)
        ttk.Button(tools,text='Copy for AI Analysis',command=self.copy_financial_ai).pack(side='left',padx=5)
        ttk.Button(tools,text='Export CSV',command=self.export_financial_csv).pack(side='left',padx=5)
        grid=ttk.Frame(viewer);grid.pack(fill='both',expand=True)
        self.fin_labels=ttk.Treeview(grid,show='headings',selectmode='extended',height=13,columns=('label',))
        self.fin_labels.heading('label',text='Financial Data')
        self.fin_labels.column('label',width=193,minwidth=160,stretch=False,anchor='w')
        self.fin_tree=ttk.Treeview(grid,show='headings',selectmode='extended',height=13)
        def sync_y(*args):
            self.fin_labels.yview(*args);self.fin_tree.yview(*args)
        self._fin_sync_y=sync_y
        vs=ttk.Scrollbar(grid,orient='vertical',command=sync_y)
        hs=ttk.Scrollbar(grid,orient='horizontal',command=self.fin_tree.xview)
        def set_y(*args):
            vs.set(*args)
            try:
                if args and len(args)>=2:self.fin_labels.yview_moveto(float(args[0]))
            except (ValueError,tk.TclError):pass
        def set_label_y(*args):
            vs.set(*args)
            try:
                if args and len(args)>=2:self.fin_tree.yview_moveto(float(args[0]))
            except (ValueError,tk.TclError):pass
        self.fin_tree.configure(yscrollcommand=set_y,xscrollcommand=hs.set)
        self.fin_labels.configure(yscrollcommand=set_label_y)
        self.fin_labels.grid(row=0,column=0,sticky='ns')
        self.fin_tree.grid(row=0,column=1,sticky='nsew')
        vs.grid(row=0,column=2,sticky='ns');hs.grid(row=1,column=1,sticky='ew')
        grid.columnconfigure(1,weight=1);grid.rowconfigure(0,weight=1)
        def sync_select(event,source,target):
            target.selection_set(source.selection())
        self.fin_labels.bind('<<TreeviewSelect>>',lambda e:sync_select(e,self.fin_labels,self.fin_tree))
        self.fin_tree.bind('<<TreeviewSelect>>',lambda e:sync_select(e,self.fin_tree,self.fin_labels))
        for widget in (self.fin_tree,self.fin_labels):
            widget.bind('<Control-c>',lambda event:self.copy_financial_selected())
            widget.bind('<Control-C>',lambda event:self.copy_financial_selected())
            widget.bind('<MouseWheel>',lambda e:sync_y('scroll',-1 if e.delta>0 else 1,'units'))
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
        for cv in (self.market_canvas,self.cap_canvas,self.foreign_canvas,self.tree_canvas,self.price_canvas):cv.bind('<Configure>',lambda e:self.redraw())
    def resize_price(self, value=None):
        if not hasattr(self,'price_canvas'):
            return
        self.price_canvas.configure(height=max(55,int(float(self.price_height.get()))))
        if getattr(self,'selected_ticker',''):
            # Redraw cached price history without re-reading SQLite.
            self.redraw_stock_history()

    def index_changed(self):
        self.index_series=index_history(self.index_code.get())
        self.redraw()

    def import_indices_clicked(self):
        try:
            report=import_folder()
            self.index_series=index_history(self.index_code.get())
            self.index_box['values']=index_codes() or ['COMPOSITE']
            self.redraw()
            msg=f"Folder: {FOLDER}\nFile ditemukan: {report['files']}\nBaris indeks diproses: {report['imported']}\nTanggal berhasil: {len(report.get('dates',[]))}"
            if report['errors']:msg+='\n\nPeringatan:\n'+'\n'.join(report['errors'][:10])
            messagebox.showinfo('Impor Indeks BEI',msg)
        except Exception as e:messagebox.showerror('Impor gagal',str(e))

    def reload(self):
        self.master_data=load_master(MASTER)
        self.index_import_report=import_folder()
        self.index_series=index_history(self.index_code.get())
        self.index_box['values']=index_codes() or ['COMPOSITE']
        with ro_conn() as c:
            self.dates=[x[0] for x in c.execute('SELECT DISTINCT trade_date FROM daily ORDER BY trade_date DESC')]
            cols={r['name'] for r in c.execute('PRAGMA table_info(daily)')}
            self.company_names={}
            if 'company' in cols:
                self.company_names={str(t).strip().upper():str(name or '') for t,name in c.execute('SELECT ticker,MAX(company) FROM daily GROUP BY ticker')}
        if not self.dates:raise ValueError('Belum ada data di tabel daily')
        self.date_box['values']=self.dates
        self.date.set(self.dates[0])  # selalu tanggal perdagangan terbaru ketika Muat ulang data
        self.sector_box['values']=['Semua Sektor']+sorted(set(x['sector'] for x in self.master_data.values()))
        self.refresh()
    def refresh(self):
        try:
            with ro_conn() as c:
                self.rows=snapshot(c,self.master_data,self.date.get())
                self.series=market_history(c,self.master_data,self.sector.get())
            self.index_series=index_history(self.index_code.get())
            self.filtered=[r for r in self.rows if self.sector.get()=='Semua Sektor' or r['sector']==self.sector.get()]
            ups=sum((r['change_pct'] or 0)>0 for r in self.filtered);downs=sum((r['change_pct'] or 0)<0 for r in self.filtered)
            foreign=sum(r['net'] or 0 for r in self.filtered)
            self.summary.set(f'{self.date.get()}   |   Saham: {len(self.filtered)}   |   Naik: {ups}  Turun: {downs}   |   Foreign net: {compact(foreign)} lembar')
            self.populate_ranks();self.render_health();self.redraw()
            if self.selected_ticker:self.open_stock(self.selected_ticker,select=False)
            self.status.set('Berhasil | Data pasar read-only | Indeks resmi BEI dari folder IHSG | Foreign dalam lembar saham')
        except Exception as e:self.status.set('ERROR: '+str(e));messagebox.showerror('Gagal membaca data',str(e))
    def populate_ranks(self):
        self.ranking_lookup={}
        for tv,key,descending in self.rankings.values():
            for item in tv.get_children():tv.delete(item)
            values=[r for r in self.filtered if r.get(key) is not None]
            for r in sorted(values,key=lambda r:r[key],reverse=descending)[:20]:
                v=f'{r[key]:+.2f}%' if key=='change_pct' else compact(r[key])
                iid=tv.insert('','end',values=(r['ticker'],short_sector(r['sector']),f'{r["close"]:,.0f}' if r['close'] is not None else 'N/A',v,compact(r['value']),compact(r['net'])))
                self.ranking_lookup[(str(tv),iid)]=r
    def hover_rank(self,event,tv):
        iid=tv.identify_row(event.y)
        if not iid:return
        r=self.ranking_lookup.get((str(tv),iid))
        if r is None:return
        ticker=r['ticker']
        company=self.company_names.get(ticker,'')
        close=f'Rp{r["close"]:,.0f}' if r['close'] is not None else 'N/A'
        change=f'{r["change_pct"]:+.2f}%' if r['change_pct'] is not None else 'N/A'
        self.rank_hint.set(f'{ticker} — {company} | {r["sector"]} | Close {close} | Gain/Loss {change} | Volume {compact(r["volume"])} | Value Rp{compact(r["value"])}')
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
    def wheel_zoom(self,event):
        self.zoom_charts(1.5 if event.delta>0 else .65)

    def zoom_charts(self,factor):
        self.zoom_level=max(1.0,min(80.0,self.zoom_level*factor))
        self.redraw()

    def pan_charts(self,direction):
        # Offset is measured in trading observations, not calendar days.
        all_dates=self._zoom_base or []
        if not all_dates:return
        n=max(2,round(len(all_dates)/self.zoom_level))
        self.zoom_offset=max(0,min(max(0,len(all_dates)-n),self.zoom_offset+direction*max(1,n//3)))
        self.redraw()

    def reset_zoom(self):
        self.zoom_level=1.0;self.zoom_offset=0
        self.redraw()

    def _shared_zoom_dates(self,index_data,foreign_data):
        all_dates=sorted(set(x['date'] for x in index_data)|set(x['date'] for x in foreign_data))
        self._zoom_base=all_dates
        if not all_dates:return None
        count=max(2,round(len(all_dates)/self.zoom_level))
        count=min(count,len(all_dates))
        self.zoom_offset=max(0,min(self.zoom_offset,len(all_dates)-count))
        stop=len(all_dates)-self.zoom_offset
        chosen=all_dates[stop-count:stop]
        return (chosen[0],chosen[-1])

    def redraw(self):
        if not self.series:return
        ordered=[x for x in self.series if x['date']<=self.date.get()]
        # Tampilkan seluruh data sampai tanggal snapshot; rentang diperbesar dengan zoom tersinkron.
        data=[x for x in self.index_series if x['date']<=self.date.get()]
        foreign_base=ordered
        window=self._shared_zoom_dates(data,foreign_base)
        if window:
            data=[x for x in data if window[0]<=x['date']<=window[1]]
        cv=self.market_canvas;cv.delete('all');self.index_hit=[];w=max(cv.winfo_width(),320);h=max(cv.winfo_height(),115)
        if not data:
            cv.create_text(w/2,h/2,text='Data indeks resmi BEI belum tersedia untuk periode ini',fill='#66798c',font=('Segoe UI',10))
            self.index_info.set('Belum ada data resmi untuk tanggal/periode terpilih')
        else:
            first=self.index_series[0]['date']
            self.index_info.set(f"{self.index_code.get()} | {len(data)} sesi terlihat | Data mulai {first} | Hingga {data[-1]['date']}")
            l,r,t,b=82,w-16,12,h-31
            vals=[x['close'] for x in data];lo=min(vals);hi=max(vals)
            pad=max((hi-lo)*.10,max(abs(hi),1)*.0005);lo-=pad;hi+=pad
            fy=lambda v:b-(v-lo)/(hi-lo)*(b-t)
            for i in range(4):
                v=lo+(hi-lo)*i/3;y=fy(v)
                cv.create_line(l,y,r,y,fill='#e8edf3')
                cv.create_text(l-6,y,text=f'{v:,.1f}',anchor='e',font=('Segoe UI',8))
            xy=[]
            for i,item in enumerate(data):
                x=l+(r-l)*i/max(1,len(data)-1);y=fy(item['close']);xy.extend((x,y));self.index_hit.append((x,y,item))
            if len(xy)>2:cv.create_line(*xy,fill=P_BLUE,width=2)
            else:cv.create_oval(xy[0]-3,xy[1]-3,xy[0]+3,xy[1]+3,fill=P_BLUE,outline='')
            for i in sorted(set([0,len(data)//2,len(data)-1])):
                x=l+(r-l)*i/max(1,len(data)-1)
                cv.create_text(x,h-11,text=data[i]['date'],font=('Segoe UI',8),anchor='s')
            cv.create_text(5,7,text='poin',anchor='nw',font=('Segoe UI',8),fill='#48576b')
        # Kapitalisasi pasar resmi sesuai kode indeks pilihan (tidak dihitung dari saham proxy).
        self.draw_market_cap(window)
        # Foreign chart uses the same shared date window as official index / market cap.
        # Dates without stock data are never fabricated or zero-filled.
        cv=self.foreign_canvas;cv.delete('all');w=max(cv.winfo_width(),320);h=max(cv.winfo_height(),105)
        data=[x for x in foreign_base if not window or window[0]<=x['date']<=window[1]];self.daily_hit=[]
        if data:
            left,right,top,bottom=84,w-14,12,h-29
            data=aggregate_foreign(data,self.foreign_frequency.get())
            vals=[r['net']/1e9 for r in data];lo=min(min(vals),0);hi=max(max(vals),0)
            if lo==hi:lo,hi=-.1,.1
            span=hi-lo;lo-=max(.02,span*.08);hi+=max(.02,span*.08)
            yy=lambda n:bottom-(n-lo)/(hi-lo)*(bottom-top)
            for j in range(5):
                v=lo+(hi-lo)*j/4;y=yy(v)
                cv.create_line(left,y,right,y,fill='#e8edf3' if abs(v)>.001 else '#8694a5')
                cv.create_text(left-6,y,text=f'{v:+.2f}',anchor='e',font=('Segoe UI',8))
            cv.create_text(5,8,text='miliar',anchor='nw',font=('Segoe UI',8),fill='#48576b')
            bw=(right-left)/len(data);zero=yy(0)
            for i,item in enumerate(data):
                x=left+(i+.5)*bw;end=yy(item['net']/1e9)
                half=max(2,bw*.34)
                cv.create_rectangle(x-half,min(end,zero),x+half,max(end,zero),fill=P_GREEN if item['net']>=0 else P_RED,outline='')
                self.daily_hit.append((x-max(4,bw*.45),x+max(4,bw*.45),item))
                if i%max(1,math.ceil(len(data)/7))==0 or i==len(data)-1:
                    cv.create_text(x,h-10,text=item['date'][5:],font=('Segoe UI',8),anchor='s')
        self.draw_treemap()
    def draw_market_cap(self,window):
        cv=self.cap_canvas;cv.delete('all');self.cap_hit=[]
        w=max(cv.winfo_width(),320);h=max(cv.winfo_height(),115)
        data=[r for r in self.index_series if r['date']<=self.date.get() and r.get('market_cap') is not None and (window is None or window[0]<=r['date']<=window[1])]
        if not data:
            cv.create_text(w/2,h/2,text='Kapitalisasi pasar resmi BEI belum tersedia',font=('Segoe UI',9),fill='#66798c');return
        l,r,t,b=87,w-16,12,h-31
        values=[x['market_cap']/1e12 for x in data];lo=min(values);hi=max(values);pad=max((hi-lo)*.1,max(abs(hi),1)*.0005);lo-=pad;hi+=pad
        fy=lambda v:b-(v-lo)/(hi-lo)*(b-t)
        for i in range(4):
            v=lo+(hi-lo)*i/3;y=fy(v)
            cv.create_line(l,y,r,y,fill='#e8edf3');cv.create_text(l-5,y,text=f'{v:,.1f}',anchor='e',font=('Segoe UI',8))
        coords=[]
        for i,row in enumerate(data):
            x=l+(r-l)*i/max(1,len(data)-1);y=fy(values[i]);coords.extend([x,y]);self.cap_hit.append((x,y,row))
        if len(coords)>=4:cv.create_line(*coords,fill='#5844a9',width=2)
        else:cv.create_oval(coords[0]-3,coords[1]-3,coords[0]+3,coords[1]+3,fill='#5844a9',outline='')
        for i in sorted({0,len(data)//2,len(data)-1}):cv.create_text(l+(r-l)*i/max(1,len(data)-1),h-11,text=data[i]['date'],font=('Segoe UI',8),anchor='s')
        cv.create_text(5,7,text='Rp T',anchor='nw',font=('Segoe UI',8),fill='#48576b')
    def hover_cap(self,event):
        cv=self.cap_canvas;cv.delete('cap_tooltip')
        if not self.cap_hit:return
        x,y,row=min(self.cap_hit,key=lambda v:abs(v[0]-event.x))
        if abs(x-event.x)>max(12,(self.cap_hit[-1][0]-self.cap_hit[0][0])/max(1,len(self.cap_hit)-1)*.8):return
        label=f"{row['date']} | Rp {row['market_cap']/1e12:,.3f} triliun"
        width=min(max(220,len(label)*7+16),cv.winfo_width()-6);px=max(3,min(event.x+12,cv.winfo_width()-width-3));py=max(3,min(event.y-35,cv.winfo_height()-30))
        cv.create_line(x,10,x,cv.winfo_height()-30,dash=(3,3),fill='#64748b',tags='cap_tooltip')
        cv.create_rectangle(px,py,px+width,py+26,fill='#18324b',outline='',tags='cap_tooltip')
        cv.create_text(px+7,py+13,text=label,anchor='w',fill='white',font=('Segoe UI',9,'bold'),tags='cap_tooltip')
    def hover_index(self,event):
        """Closest real BEI index observation; tooltip follows the pointer inside plot."""
        cv=self.market_canvas
        cv.delete('index_tooltip')
        if not self.index_hit:return
        x,y,item=min(self.index_hit,key=lambda p:abs(p[0]-event.x))
        if abs(x-event.x)>max(12,(self.index_hit[-1][0]-self.index_hit[0][0])/max(1,len(self.index_hit)-1)*.8):
            self.index_hover.set('Arahkan kursor pada grafik indeks untuk detail tanggal.')
            return
        value=item['close'];self.index_hover.set(f"{self.index_code.get()} | {item['date']} | Penutupan: {value:,.3f} poin")
        cv.create_line(x,10,x,max(12,cv.winfo_height()-30),fill='#64748b',dash=(3,3),tags='index_tooltip')
        cv.create_oval(x-4,y-4,x+4,y+4,fill='#1e73d8',outline='white',tags='index_tooltip')
        label=f"{item['date']}  |  {value:,.3f}"
        width=max(145,len(label)*7+18);height=27
        px=max(3,min(event.x+12,cv.winfo_width()-width-3))
        py=max(3,min(event.y-36,cv.winfo_height()-height-3))
        cv.create_rectangle(px,py,px+width,py+height,fill='#18324b',outline='#18324b',tags='index_tooltip')
        cv.create_text(px+8,py+height/2,text=label,anchor='w',fill='white',font=('Segoe UI',9,'bold'),tags='index_tooltip')
    def leave_index(self,event):
        self.market_canvas.delete('index_tooltip')
        self.index_hover.set('Arahkan kursor pada grafik indeks untuk detail tanggal.')
    def click_foreign(self,event):
        for x0,x1,r in getattr(self,'daily_hit',[]):
            if x0<=event.x<=x1 and self.foreign_frequency.get()=='Harian' and r['date'] in self.dates:self.date.set(r['date']);self.refresh();break
    def hover_foreign(self,event):
        cv=self.foreign_canvas
        cv.delete('foreign_tooltip')
        for x0,x1,r in getattr(self,'daily_hit',[]):
            if x0<=event.x<=x1:
                monthly=self.foreign_frequency.get()=='Bulanan'
                weekly=self.foreign_frequency.get()=='Mingguan'
                unit='Bulan' if monthly else 'Minggu' if weekly else 'Tanggal'
                label=f"{unit}: {r.get('label',r['date'])} | Net {r['net']/1e9:+,.3f} miliar"
                buy=f"Buy: {r['buy']:,.0f} lembar"
                sell=f"Sell: {r['sell']:,.0f} lembar"
                self.hover_status.set(f"{unit} {r.get('label',r['date'])} | Foreign Buy {r['buy']:,.0f} | Foreign Sell {r['sell']:,.0f} | Net {r['net']:+,.0f} lembar"+(" (akumulasi bulanan)" if monthly else ''))
                w=max(cv.winfo_width(),320);h=max(cv.winfo_height(),105)
                width=min(max(215, len(label)*6+18),w-8);height=65
                px=max(3,min(event.x+12,w-width-3));py=max(3,min(event.y-70,h-height-3))
                cv.create_rectangle(px,py,px+width,py+height,fill='#18324b',outline='#18324b',tags='foreign_tooltip')
                for i,line in enumerate((label,buy,sell)):
                    cv.create_text(px+8,py+11+i*20,text=line,fill='white',anchor='w',font=('Segoe UI',8,'bold' if i==0 else 'normal'),tags='foreign_tooltip')
                return

    def leave_foreign(self,event):
        self.foreign_canvas.delete('foreign_tooltip')
        self.hover_status.set('Foreign Net: arahkan kursor ke batang untuk melihat Buy / Sell / Net (lembar saham).')
    def open_treemap_fullscreen(self):
        if self._tree_full_window is not None:
            try:
                if self._tree_full_window.winfo_exists():
                    self._tree_full_window.lift();self._tree_full_window.focus_force();return
            except tk.TclError:pass
        win=tk.Toplevel(self);self._tree_full_window=win
        win.title('BEI · Sector → Ticker Treemap — Layar Penuh')
        win.geometry(f'{max(920,self.winfo_screenwidth()-90)}x{max(580,self.winfo_screenheight()-140)}+25+25')
        header=ttk.Frame(win,padding=8);header.pack(fill='x')
        ttk.Label(header,text=f'Treemap Sector → Ticker | {self.date.get()} | {self.period.get()} hari | {self.mode.get()}',font=('Segoe UI',12,'bold')).pack(side='left')
        ttk.Button(header,text='Tutup (Esc)',command=win.destroy).pack(side='right')
        ttk.Label(header,text='Arahkan kursor untuk tooltip; klik saham untuk Stock Detail',foreground='#526679').pack(side='right',padx=20)
        canvas=ThemeCanvas(win,bg='white',highlightthickness=0)
        canvas.pack(fill='both',expand=True,padx=8,pady=(0,8))
        canvas.bind('<Configure>',lambda e:self.draw_treemap(canvas))
        canvas.bind('<Motion>',self.hover_treemap)
        canvas.bind('<Leave>',lambda e:self.hide_tree_tip())
        canvas.bind('<Button-1>',self.click_treemap)
        win.bind('<Escape>',lambda e:win.destroy())
        win.protocol('WM_DELETE_WINDOW',win.destroy)
        self.draw_treemap(canvas)

    def hide_tree_tip(self):
        if getattr(self,'_tree_tip',None):
            try:self._tree_tip.withdraw()
            except tk.TclError:pass

    def draw_treemap(self,canvas=None):
        cv=canvas if canvas is not None else self.tree_canvas
        cv.delete('all');hits=[];sectors=[];details={};w=max(cv.winfo_width(),400);h=max(cv.winfo_height(),220)
        if self.date.get() not in self.dates:return
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
            if abs(v)>0:
                nodes[sec].append((t,v));details[t]={'buy':b,'sell':s,'net':b-s,'days':len(dates)}
        allnodes=[(sec,sum(math.sqrt(abs(v)) for t,v in items),sorted(items,key=lambda x:abs(x[1]),reverse=True)) for sec,items in nodes.items()]
        allnodes.sort(key=lambda x:x[1],reverse=True);total=sum(x[1] for x in allnodes)
        if not total:cv.create_text(w/2,h/2,text='Tidak ada foreign flow untuk pilihan ini');return
        cx=0
        for sec,weight,items in allnodes:
            sw=w*weight/total
            if sw<3:cx+=sw;continue
            cv.create_rectangle(cx,0,cx+sw,h,fill='#eef3fa',outline='white',width=2)
            cv.create_rectangle(cx,0,cx+sw,min(24,h),fill='#273b5a',outline='white')
            sectors.append((cx,cx+sw,sec,items))
            if sw>25:cv.create_text(cx+3,12,text=sec[:max(2,int(sw/7))],fill='white',anchor='w',font=('Segoe UI',8,'bold'))
            cy=24;usable=max(1,h-24);tt=sum(math.sqrt(abs(v)) for t,v in items)
            for t,v in items:
                th=usable*math.sqrt(abs(v))/tt
                color=('#2e80bb' if mode=='buy' else '#e18a32' if mode=='sell' else P_GREEN if v>0 else P_RED)
                cv.create_rectangle(cx+1,cy,cx+sw-1,cy+th,fill=color,outline='white')
                hits.append((cx+1,cy,cx+sw-1,cy+th,t,v,sec))
                if th>15 and sw>35:cv.create_text(cx+sw/2,cy+th/2,text=t,font=('Segoe UI',8,'bold'),fill='white')
                cy+=th
            cx+=sw
        self._tree_views[str(cv)]=(hits,sectors,details)

    def hover_treemap(self,event):
        cv=event.widget;data=self._tree_views.get(str(cv))
        if not data:self.hide_tree_tip();return
        hits,sectors,details=data;text=None;selected=None
        for x0,y0,x1,y1,t,v,sec in hits:
            if x0<=event.x<=x1 and y0<=event.y<=y1:
                item=details.get(t,{})
                text=[f'{t}  |  {sec}  |  {item.get("days",0)} hari perdagangan',
                      f'Foreign Buy: {fmt(item.get("buy"))} lembar',
                      f'Foreign Sell: {fmt(item.get("sell"))} lembar',
                      f'Foreign Net: {fmt(item.get("net"))} lembar']
                selected=(x0,y0,x1,y1);break
        if text is None and event.y<=24:
            for x0,x1,sec,items in sectors:
                if x0<=event.x<=x1:
                    bs=sum(details.get(t,{}).get('buy',0) for t,_ in items)
                    ss=sum(details.get(t,{}).get('sell',0) for t,_ in items)
                    text=[sec+f'  |  {len(items)} saham',f'Foreign Buy: {fmt(bs)} lembar',f'Foreign Sell: {fmt(ss)} lembar',f'Foreign Net: {fmt(bs-ss)} lembar']
                    selected=(x0,0,x1,24);break
        if not text:self.hide_tree_tip();return
        if not self._tree_tip or not self._tree_tip.winfo_exists():
            popup=tk.Toplevel(self);popup.overrideredirect(True);popup.attributes('-topmost',True)
            frame=tk.Frame(popup,bg='#18324b',padx=9,pady=7);frame.pack()
            labels=[tk.Label(frame,font=('Segoe UI',9,'bold' if i==0 else 'normal'),bg='#18324b',fg='white',anchor='w') for i in range(4)]
            for lab in labels:lab.pack(anchor='w')
            popup._tip_labels=labels;self._tree_tip=popup
        for lab,line in zip(self._tree_tip._tip_labels,text):lab.configure(text=line)
        self._tree_tip.update_idletasks()
        tw,th=self._tree_tip.winfo_reqwidth(),self._tree_tip.winfo_reqheight()
        x0,y0,x1,y1=selected
        bx,by=cv.winfo_rootx(),cv.winfo_rooty()
        # Tooltip lives outside the hovered rectangle, not underneath the pointer.
        screen_w,screen_h=cv.winfo_screenwidth(),cv.winfo_screenheight()
        options=[(bx+x1+10,by+y0),(bx+x0-tw-10,by+y0),
                 (bx+x0,by+y1+10),(bx+x0,by+y0-th-10)]
        def fits(q):
            x,y=q
            return x>=0 and y>=0 and x+tw<=screen_w and y+th<=screen_h and (x>=bx+x1 or x+tw<=bx+x0 or y>=by+y1 or y+th<=by+y0)
        chosen=next((q for q in options if fits(q)),None)
        if chosen is None:
            # Always available: move next to the treemap panel, outside the selected block.
            chosen=(max(0,min(screen_w-tw,bx+cv.winfo_width()+5)),max(0,min(screen_h-th,by+event.y)))
        self._tree_tip.geometry(f'+{int(chosen[0])}+{int(chosen[1])}')
        self._tree_tip.deiconify()

    def click_treemap(self,event):
        data=self._tree_views.get(str(event.widget))
        if not data:return
        for x0,y0,x1,y1,t,v,sec in data[0]:
            if x0<=event.x<=x1 and y0<=event.y<=y1:
                self.hide_tree_tip();self.open_stock(t);return

    def draw_stock_flow(self,canvas=None,rows=None,net_canvas=None):
        # Both diagrams always use exactly the same sessions and x-axis.
        buy_cv=canvas if canvas is not None else getattr(self,'stock_flow_buy_canvas',None)
        net_cv=net_canvas if net_canvas is not None else getattr(self,'stock_flow_net_canvas',None)
        if buy_cv is None or net_cv is None:return
        buy_cv.delete('all');net_cv.delete('all')
        rows=rows if rows is not None else getattr(self,'stock_flow_rows',[])
        pts=[]
        for r in rows:
            b=number(r['foreign_buy']);s=number(r['foreign_sell'])
            if b is not None and s is not None:
                pts.append((str(r['trade_date']),max(0,b),max(0,s),b-s))

        if not pts:
            for cv in (buy_cv,net_cv):
                cv._foreign_hits=[]
                cv.create_text(max(180,cv.winfo_width())/2,45,text='Data Foreign Buy / Sell belum tersedia',fill='#526679')
            return
        vmax=max(max(b,s) for _,b,s,_ in pts) or 1
        nmax=max(abs(n) for *_,n in pts) or 1
        for cv,mode in ((buy_cv,'buy'),(net_cv,'net')):
            w=max(cv.winfo_width(),360);h=max(cv.winfo_height(),88)
            left,right,top,bottom=61,w-12,13,h-23
            slot=(right-left)/len(pts)
            hits=[]
            if mode=='buy':
                baseline=bottom;usable=max(5,bottom-top)
                cv.create_line(left,baseline,right,baseline,fill='#9eacbc')
                cv.create_text(4,top,text=compact(vmax),anchor='nw',font=('Segoe UI',8))
            else:
                baseline=(top+bottom)/2;usable=max(4,(bottom-top)/2-2)
                cv.create_line(left,baseline,right,baseline,fill='#9eacbc')
                cv.create_text(4,top,text='+'+compact(nmax),anchor='nw',font=('Segoe UI',8))
                cv.create_text(4,bottom,text='-'+compact(nmax),anchor='sw',font=('Segoe UI',8))
            for i,(d,b,s,n) in enumerate(pts):
                x=left+(i+.5)*slot
                if mode=='buy':
                    bw=max(1,min(8,slot*.32))
                    cv.create_rectangle(x-bw-0.5,baseline-b/vmax*usable,x-0.5,baseline,fill=P_GREEN,outline='')
                    cv.create_rectangle(x+0.5,baseline-s/vmax*usable,x+bw+0.5,baseline,fill=P_RED,outline='')
                else:
                    y=baseline-n/nmax*usable
                    cv.create_rectangle(x-max(1,slot*.31),min(baseline,y),x+max(1,slot*.31),max(baseline,y),fill=P_GREEN if n>=0 else P_RED,outline='')
                hits.append((x-slot/2,x+slot/2,d,b,s,n))
            cv.create_text(left,bottom+4,text=pts[0][0],anchor='nw',font=('Segoe UI',8))
            cv.create_text(right,bottom+4,text=pts[-1][0],anchor='ne',font=('Segoe UI',8))
            cv._foreign_hits=hits

    def hover_stock_flow(self,event,canvas):
        """Details are displayed outside plotting area, leaving selected bars and dates visible."""
        cv=canvas
        cv.delete('stock_tip')  # clear historical tooltip if present
        info=getattr(cv,'_flow_info',None)
        if info is None:return
        for x0,x1,d,b,s,n in getattr(cv,'_foreign_hits',[]):
            if x0<=event.x<=x1:
                state='NET BUY' if n>0 else ('NET SELL' if n<0 else 'NET ZERO')
                info.set(f'Tanggal: {d}  |  Buy: {fmt(b)} lembar  |  Sell: {fmt(s)} lembar  |  Net: {n:+,.0f} lembar ({state})')
                return
        info.set('Arahkan kursor ke batang untuk melihat Tanggal, Buy, Sell, dan Net.')

    def export_stock_flow_ig(self):
        """Export selected stock's historical foreign flow as an Instagram 4:5 PNG."""
        if not getattr(self,'selected_ticker',None):
            messagebox.showinfo('Pilih ticker','Pilih saham di Stock Detail terlebih dahulu.');return
        try:
            from PIL import Image,ImageDraw,ImageFont
        except ImportError:
            messagebox.showerror('Pillow belum terpasang','Jalankan: python -m pip install Pillow');return
        pts=[]
        for r in getattr(self,'stock_flow_rows',[]):
            b=number(r['foreign_buy']);v=number(r['foreign_sell'])
            if b is not None and v is not None:pts.append((str(r['trade_date']),max(0,b),max(0,v),b-v))
        if not pts:
            messagebox.showwarning('Belum ada data','Tidak ada riwayat foreign flow untuk ticker ini.');return
        portrait=messagebox.askyesno('Format Instagram','Gunakan Portrait 4:5 (1080 × 1350)?\n\nPilih Tidak untuk Square 1:1 (1080 × 1080).')
        outfile=filedialog.asksaveasfilename(title='Ekspor chart ke Instagram',defaultextension='.png',filetypes=[('PNG image','*.png')],initialfile=f'Foreign_Flow_{self.selected_ticker}_{pts[-1][0]}_IG.png')
        if not outfile:return
        W,H=1080,1350
        im=Image.new('RGB',(W,H),'#0d2247');d=ImageDraw.Draw(im)
        fontpath=next((str(q) for q in [Path('C:/Windows/Fonts/arial.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if q.exists()),None)
        def f(size):return ImageFont.truetype(fontpath,size) if fontpath else ImageFont.load_default()
        title,sub,small=f(47),f(26),f(21)
        d.text((64,54),'FOREIGN FLOW  |  BEI EQUITY ANALYTICS',font=sub,fill='#9ecbff')
        logo_path=BASE/'logos'/'Investor Mandiri.png'
        if logo_path.is_file():
            try:
                logo=Image.open(logo_path).convert('RGBA')
                logo.thumbnail((175,88),Image.Resampling.LANCZOS)
                # Use a translucent-safe background in the header and a generous right margin.
                im.paste(logo,(W-64-logo.width,38),logo)
            except (OSError,ValueError):pass
        d.text((64,117),self.selected_ticker,font=title,fill='white')
        d.text((64,190),f'Periode data: {pts[0][0]} s.d. {pts[-1][0]}',font=sub,fill='#c5d5ed')
        end=pts[-1];status='NET BUY' if end[3]>0 else 'NET SELL' if end[3]<0 else 'NET ZERO'
        d.text((64,244),f'Terakhir: {end[3]:+,.0f} lembar  |  {status}',font=sub,fill='#3dd4a8' if end[3]>=0 else '#ff9292')
        # Show last 65 sessions for legibility, while period is explicit.
        selected=pts[-65:];xleft,xright=85,1000
        def drawpanel(top,bottom,mode):
            d.rounded_rectangle((55,top,1025,bottom),radius=20,fill='#142f55')
            d.text((84,top+24),'FOREIGN BUY / SELL' if mode=='trade' else 'FOREIGN NET',font=sub,fill='white')
            l,r=90,995;t=top+90;b=bottom-70
            ymax=max((max(x[1],x[2]) if mode=='trade' else abs(x[3]) for x in selected),default=1) or 1
            zero=b if mode=='trade' else (t+b)/2
            d.line((l,int(zero),r,int(zero)),fill='#7188a5',width=2)
            step=(r-l)/max(1,len(selected));bw=max(2,int(min(8,step*.31)))
            for i,(_,buy,sell,net) in enumerate(selected):
                x=l+(i+.5)*step
                if mode=='trade':
                    y1=zero-buy/ymax*(b-t);y2=zero-sell/ymax*(b-t)
                    d.rectangle((int(x-bw-1),int(y1),int(x-1),int(zero)),fill='#22b891')
                    d.rectangle((int(x+1),int(y2),int(x+bw+1),int(zero)),fill='#f16b72')
                else:
                    y=zero-net/ymax*(b-t)/2
                    d.rectangle((int(x-bw),int(min(y,zero)),int(x+bw),int(max(y,zero))+1),fill='#22b891' if net>=0 else '#f16b72')
            d.text((l,bottom-48),selected[0][0],font=small,fill='#b9cde5')
            right=selected[-1][0]; d.text((r-d.textbbox((0,0),right,font=small)[2],bottom-48),right,font=small,fill='#b9cde5')
        drawpanel(315,720,'trade')
        drawpanel(745,1130,'net')
        d.text((64,1154),'Hijau: Foreign Buy / Net Buy     Merah: Foreign Sell / Net Sell',font=small,fill='#d9e7f5')
        d.text((64,1198),'Satuan: lembar saham  |  Grafik: hingga 65 sesi perdagangan terbaru',font=small,fill='#b9cde5')
        d.line((64,1248,1016,1248),fill='#42648e',width=2)
        d.text((64,1270),'Sumber: data perdagangan BEI pada database lokal',font=small,fill='#b9cde5')
        if not portrait:
            # Fit the complete 4:5 design inside a 1:1 feed image, no cropping.
            square=Image.new('RGB',(1080,1080),'#0d2247')
            inset=im.resize((864,1080),Image.Resampling.LANCZOS)
            square.paste(inset,(108,0))
            im=square
        try:im.save(outfile,'PNG')
        except Exception as exc:messagebox.showerror('Gagal ekspor',str(exc));return
        messagebox.showinfo('Ekspor berhasil',f'Post Instagram {im.width} × {im.height} telah disimpan:\n{outfile}')

    def open_stock_foreign_window(self):
        if not self.selected_ticker:
            messagebox.showinfo('Pilih ticker','Pilih saham dari Treemap atau Ranking terlebih dahulu.');return
        win=tk.Toplevel(self);win.title(f'{self.selected_ticker} · Foreign Buy/Sell & Foreign Net (lembar)')
        win.geometry('1150x690')
        ttk.Label(win,text=f'{self.selected_ticker} — seluruh histori | Buy/Sell: dua batang positif | Net: hijau (+), merah (−)',font=('Segoe UI',12,'bold'),padding=10).pack(anchor='w')
        holder=ttk.Frame(win,padding=(12,4));holder.pack(fill='both',expand=True)
        ttk.Label(holder,text='Foreign Buy (hijau) vs Foreign Sell (merah)',font=('Segoe UI',10,'bold')).pack(anchor='w')
        buy_cv=ThemeCanvas(holder,bg='white',height=245);buy_cv.pack(fill='both',expand=True,pady=(3,12))
        ttk.Label(holder,text='Foreign Net — Net Buy (hijau) / Net Sell (merah)',font=('Segoe UI',10,'bold')).pack(anchor='w')
        net_cv=ThemeCanvas(holder,bg='white',height=245);net_cv.pack(fill='both',expand=True,pady=(3,8))
        ttk.Label(holder,text='Sumbu X: Tanggal perdagangan (YYYY-MM-DD)  |  Sumbu Y: Lembar saham',foreground='#526679').pack(anchor='w')
        big_info=tk.StringVar(value='Arahkan kursor ke batang untuk melihat Tanggal, Buy, Sell, dan Net.')
        ttk.Label(holder,textvariable=big_info,foreground='#18324b',wraplength=1040).pack(anchor='w')
        rows=list(getattr(self,'stock_flow_rows',[]))
        for cv in (buy_cv,net_cv):
            cv._flow_info=big_info
            cv.bind('<Configure>',lambda e:self.draw_stock_flow(buy_cv,rows,net_cv))
            cv.bind('<Motion>',lambda e,c=cv:self.hover_stock_flow(e,c))
            cv.bind('<Leave>',lambda e,c=cv:c.delete('stock_tip'))
        self.draw_stock_flow(buy_cv,rows,net_cv)

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
        self.show_ticker_identity(t)
        self.update_stock_snapshot(t,price)
        self.last_price_rows=rows
        self.stock_flow_rows=rows
        self.stock_end=len(rows)
        self.stock_visible=min(65,len(rows))
        self.redraw_stock_history()
        self.draw_financial_charts()
        self.render_financial_table()
        self.current_price=price;self.current_ticker=t
        self.update_valuation()
        if select:self.tabs.select(self.detail)
    def update_stock_snapshot(self,ticker,close):
        """Stock-level snapshot; share count is a current master snapshot, not historical shares."""
        master=(self.master_data or {}).get(ticker,{})
        shares=number(master.get('shares'))
        shares=shares if shares is not None and shares>0 else None
        price=number(close)
        mcap=price*shares if shares is not None and price is not None and price>0 else None
        equity,eqperiod=latest_metric(self.finance,'total_equity')
        minority,_=latest_metric(self.finance,'minority_interest')
        # Total equity must not be misrepresented as attributable equity when minority share is unknown.
        attributable=(equity-minority) if equity is not None and minority is not None else None
        bvps=(attributable*1_000_000/shares) if attributable is not None and shares else None
        pbv=(price/bvps) if price is not None and bvps is not None and bvps>0 else None
        parts=[f'Outstanding Shares: {compact(shares)} lembar' if shares else 'Outstanding Shares: —',
               f'Market Cap: Rp {mcap/1e12:,.3f} triliun' if mcap is not None else 'Market Cap: —',
               f'BVPS indikatif: Rp {bvps:,.2f}' if bvps is not None else 'BVPS: —',
               f'PBV indikatif: {pbv:,.2f}x' if pbv is not None else 'PBV: —']
        self.stock_snapshot.set('    |    '.join(parts))

    def visible_stock_rows(self):
        rows=getattr(self,'last_price_rows',[])
        end=min(len(rows),getattr(self,'stock_end',len(rows)) or len(rows))
        count=max(3,int(getattr(self,'stock_visible',65)))
        return rows[max(0,end-count):end]

    def redraw_stock_history(self):
        if not getattr(self,'last_price_rows',None):return
        rows=self.visible_stock_rows()
        self.draw_price_history(rows)
        self.draw_stock_flow(rows=rows)

    def pan_stock(self,direction):
        n=len(getattr(self,'last_price_rows',[]))
        if n<1:return
        end=getattr(self,'stock_end',n) or n
        self.stock_end=max(1,min(n,end+direction*max(1,int(self.stock_visible)//3)))
        self.redraw_stock_history()

    def zoom_stock(self,factor):
        n=len(getattr(self,'last_price_rows',[]))
        if n<2:return
        self.stock_visible=max(5,min(n,int(self.stock_visible*factor)))
        self.redraw_stock_history()

    def reset_stock_zoom(self):
        n=len(getattr(self,'last_price_rows',[]))
        self.stock_end=n;self.stock_visible=min(65,n)
        self.redraw_stock_history()

    def hover_price_history(self,event):
        pts=getattr(self.price_canvas,'_price_hits',[])
        if not pts:return
        x,d,value=min(pts,key=lambda p:abs(p[0]-event.x))
        if abs(x-event.x)<max(12,self.price_canvas.winfo_width()/max(1,len(pts))):
            self.price_info.set(f'Tanggal: {d}   |   Close: Rp{fmt(value,2)}')

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
        cv._price_hits=[(xx(i),d,v) for i,(d,v) in enumerate(data)]
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
        self.fin_chart_end=None
        self.render_financial_table()
        self.draw_financial_charts()

    def pan_financial_charts(self,direction):
        d=(getattr(self,'finance',{}) or {}).get('annual' if self.fin_view.get()=='Annual' else 'quarterly',{})
        end=self.fin_chart_end if self.fin_chart_end is not None else len(d)
        self.fin_chart_end=max(1,min(len(d),end+direction)) if d else None
        self.draw_financial_charts()

    def reset_financial_charts(self):
        self.fin_chart_end=None
        self.draw_financial_charts()

    def draw_financial_charts(self):
        """Three fundamental charts, all sourced directly from selected Annual or Quarterly records.
        Quarterly income/cash flow numbers are YTD, balance sheet values are snapshots.
        """
        if not hasattr(self,'fin_canvases'):return
        d=(getattr(self,'finance',{}) or {}).get('annual' if self.fin_view.get()=='Annual' else 'quarterly',{})
        periods_all=sorted(d)
        end=min(len(periods_all),self.fin_chart_end if self.fin_chart_end is not None else len(periods_all))
        periods=periods_all[max(0,end-7):end]
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

    def free_float_reference(self,ticker):
        """Optional external reference; do not impute free float from listed shares."""
        ref=BASE/'free_float.csv'
        if not ref.is_file():return None,None,None
        with ref.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if (row.get('ticker') or '').strip().upper()!=ticker:continue
                val=(row.get('free_float_pct') or '').strip().replace('%','').replace(',','.')
                try:
                    pct=float(val)
                    if not 0<=pct<=100:raise ValueError('out of range')
                except (ValueError,TypeError):return None,None,None
                return pct,(row.get('as_of') or '').strip(),(row.get('source') or '').strip()
        return None,None,None

    def show_ticker_identity(self,ticker):
        pct,as_of,source=self.free_float_reference(ticker)
        if pct is None:
            self.freefloat_text.set('Free float: belum tersedia | isi free_float.csv menggunakan sumber terverifikasi')
        else:
            self.freefloat_text.set(f'Free float: {pct:,.2f}% | Per {as_of or "tanggal belum tercatat"} | Sumber: {source or "belum dicatat"}')
        logo_dir=BASE/'logos'
        self.logo_img=None
        for suffix in ('.png','.gif'):
            path=logo_dir/(ticker+suffix)
            if not path.is_file():continue
            try:
                img=tk.PhotoImage(file=str(path),master=self)
                factor=max(1,math.ceil(max(img.width()/70,img.height()/42)))
                self.logo_img=img.subsample(factor,factor) if factor>1 else img
                break
            except tk.TclError:continue
        if self.logo_img is None:
            self.logo_label.configure(image='',text=ticker)
        else:self.logo_label.configure(image=self.logo_img,text='')

    def financial_matrix(self):
        """Chronological columns; all numbers retain their original units, documented above."""
        fund=getattr(self,'finance',{}) or {}
        mode=self.fin_view.get()
        data=fund.get('annual' if mode=='Annual' else 'quarterly',{})
        periods=sorted(data,reverse=True)
        labels=[f'FY{y}' for y in periods] if mode=='Annual' else [f'{y} Q{q}' for y,q in periods]
        heads=['Financial Data']+labels
        matrix=[];sections=set()
        for caption,key,unit in self.FIN_METRICS:
            if key is None:
                matrix.append([caption]+['']*len(periods));sections.add(len(matrix)-1);continue
            vals=[]
            for p in periods:
                v=data[p].get(key)
                if v is None:vals.append('')
                elif unit in ('%','x','Rp/saham'):vals.append(f'{v:,.2f}')
                else:vals.append(f'{v:,.0f}')
            matrix.append([caption]+vals)
        self.fin_sections=sections
        return heads,matrix

    def render_financial_table(self):
        if not hasattr(self,'fin_tree'):return
        headers,rows=self.financial_matrix()
        tree=self.fin_tree
        for widget in (tree,self.fin_labels):
            for iid in widget.get_children():widget.delete(iid)
        columns=[f'c{i}' for i in range(len(headers)-1)]
        tree.configure(columns=columns)
        for key,label in zip(columns,headers[1:]):
            tree.heading(key,text=label)
            tree.column(key,width=122,minwidth=86,stretch=False,anchor='e')
        for i,row in enumerate(rows):
            tags=('section',) if i in self.fin_sections else ()
            iid=f'row{i}'
            self.fin_labels.insert('','end',iid=iid,values=(row[0],),tags=tags)
            tree.insert('','end',iid=iid,values=row[1:],tags=tags)
        for widget in (tree,self.fin_labels):widget.tag_configure('section',background='#e9eef5',foreground='#173355')
        self.fin_headers=headers;self.fin_rows=rows
        ticker=getattr(self,'selected_ticker','')
        period_note='FY annual' if self.fin_view.get()=='Annual' else 'Quarterly: flows YTD kumulatif; neraca snapshot; rasio sesuai sumber'
        self.fin_status.set(f'{ticker} | {len(headers)-1} periode | {period_note} | kosong = tidak tersedia')
        # Most recent reporting period stays first, immediately after frozen labels.
        self.after_idle(lambda:tree.xview_moveto(0.0) if tree.winfo_exists() else None)

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
              'Satuan: Rp juta kecuali EPS/BVPS Rp/saham, saham beredar juta lembar, rasio % atau x.',
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


