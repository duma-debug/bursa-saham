#!/usr/bin/env python3
"""BEI Equity Analytics V2.5: expanded stock screener dropdown ranges (SQLite read-only)."""
import csv, math, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from collections import defaultdict
from bei_equity_v2_3_3 import App, ro_conn, fundamentals, number, BASE

class DashboardScreener(App):
    def __init__(self):
        super().__init__()
        self.title('BEI Equity Analytics V2.5 — Stock Screener')
        self.scr_values = []
        self.scr_data = []
        self.scr_vars = {}
        self._build_screener()
        self.run_screener()

    def _build_screener(self):
        self.screen_tab=ttk.Frame(self.tabs)
        self.tabs.add(self.screen_tab,text='Stock Screener')
        top=ttk.LabelFrame(self.screen_tab,text='Filter saham pada tanggal yang dipilih di dashboard',padding=8)
        top.pack(fill='x',padx=8,pady=6)
        # Rentang disimpan sebagai [minimum inklusif, maksimum eksklusif].
        # Semua nilai berasal dari angka mentah database, bukan teks tabel.
        self.price_ranges = {
            'Semua harga': (None, None),
            '< Rp50': (None, 50),
            'Rp50 – <Rp100': (50, 100),
            'Rp100 – <Rp200': (100, 200),
            'Rp200 – <Rp500': (200, 500),
            'Rp500 – <Rp1.000': (500, 1000),
            'Rp1.000 – <Rp2.000': (1000, 2000),
            'Rp2.000 – <Rp5.000': (2000, 5000),
            'Rp5.000 – <Rp10.000': (5000, 10000),
            '≥ Rp10.000': (10000, None),
        }
        self.change_ranges = {
            'Semua perubahan': (None, None),
            '< 0% (turun)': (None, 0),
            '0% – <5%': (0, 5),
            '5% – <10%': (5, 10),
            '10% – <15%': (10, 15),
            '15% – <20%': (15, 20),
            '20% – <30%': (20, 30),
            '≥ 30%': (30, None),
        }
        self.price_choice = tk.StringVar(value='Semua harga')
        self.change_choice = tk.StringVar(value='Semua perubahan')
        ttk.Label(top, text='Rentang harga (Rp)').grid(row=0,column=0,sticky='w',padx=4,pady=5)
        ttk.Combobox(top,textvariable=self.price_choice,values=list(self.price_ranges),
                     state='readonly',width=22).grid(row=0,column=1,sticky='ew',padx=4,pady=5)
        ttk.Label(top,text='Perubahan harian (%)').grid(row=0,column=2,sticky='w',padx=4,pady=5)
        ttk.Combobox(top,textvariable=self.change_choice,values=list(self.change_ranges),
                     state='readonly',width=23).grid(row=0,column=3,sticky='ew',padx=4,pady=5)
        # Semua filter memakai dropdown. Batas bawah inklusif, atas eksklusif.
        def bands(name, thresholds, fmt):
            choices={f'Semua {name}':(None,None)}
            choices[f'< {fmt(thresholds[0])}']=(None,thresholds[0])
            for lo,hi in zip(thresholds,thresholds[1:]):
                choices[f'{fmt(lo)} – <{fmt(hi)}']=(lo,hi)
            choices[f'≥ {fmt(thresholds[-1])}']=(thresholds[-1],None)
            return choices
        self.extra_ranges={
          'volume':bands('volume',[100000,1000000,10000000,100000000,1000000000],lambda v:f'{v/1e6:g} jt lembar' if v>=1e6 else f'{v/1e3:g} rb lembar'),
          'value':bands('value',[100000000,1000000000,10000000000,100000000000,1000000000000],lambda v:f'Rp{v/1e12:g} T' if v>=1e12 else (f'Rp{v/1e9:g} M' if v>=1e9 else f'Rp{v/1e6:g} jt')),
          'net':bands('net',[-1e9,-1e8,-1e7,0,1e7,1e8,1e9],lambda v:f'{v/1e6:g} jt'),
          'roe':bands('ROE',[-20,0,5,10,15,20,30,50],lambda v:f'{v:g}%'),
          'pbv':bands('PBV',[0,0.5,1,2,3,5,10,20],lambda v:f'{v:g}x'),
          'per':bands('PER',[0,5,10,15,20,30,50,100],lambda v:f'{v:g}x'),
          'der':bands('DER',[0,0.25,0.5,1,2,3,5],lambda v:f'{v:g}x'),
          'cap':bands('kapitalisasi',[1e11,1e12,5e12,1e13,5e13,1e14,1e15],lambda v:f'Rp{v/1e12:g} T' if v>=1e12 else f'Rp{v/1e9:g} M'),
          'foreign_multi':bands('foreign multi-hari',[-1e9,-1e8,-1e7,0,1e7,1e8,1e9],lambda v:f'{v/1e6:g} jt'),
          'net_margin':bands('net margin',[-20,0,5,10,15,20,30,50],lambda v:f'{v:g}%'),
        }
        self.extra_names={'volume':'Volume (lembar)','value':'Nilai transaksi (Rp)',
          'net':'Foreign Net 1D (lembar)','roe':'ROE (%)','pbv':'PBV (x)','per':'PER (x)',
          'der':'DER (x)','cap':'Market Cap (Rp)','foreign_multi':'Foreign Net multi-hari',
          'net_margin':'Net Profit Margin (%)'}
        self.foreign_horizon=tk.StringVar(value='5')
        ttk.Label(top,text='Foreign periode (sesi tersedia)').grid(row=1,column=0,sticky='w',padx=4)
        ttk.Combobox(top,textvariable=self.foreign_horizon,values=['5','10','20'],state='readonly',width=12).grid(row=1,column=1,sticky='ew',padx=4)
        for i,key in enumerate(self.extra_ranges):
            row=2+i//4;col=i%4
            cell=ttk.Frame(top);cell.grid(row=row,column=col,sticky='ew',padx=4,pady=4)
            ttk.Label(cell,text=self.extra_names[key]).pack(anchor='w')
            choices=self.extra_ranges[key]
            v=tk.StringVar(value=next(iter(choices)));self.scr_vars[key]=v
            ttk.Combobox(cell,textvariable=v,values=list(choices),state='readonly',width=24).pack(fill='x')
        for c in range(4):top.columnconfigure(c,weight=1)
        tool=ttk.Frame(self.screen_tab,padding=(8,3));tool.pack(fill='x')
        self.scr_require=tk.BooleanVar(value=False)
        ttk.Checkbutton(tool,text='Hanya saham dengan data ROE, PBV, dan PER lengkap',variable=self.scr_require).pack(side='left')
        ttk.Button(tool,text='Jalankan Screener',command=self.run_screener).pack(side='left',padx=6)
        ttk.Button(tool,text='Reset Filter',command=self.reset_screener).pack(side='left',padx=6)
        ttk.Button(tool,text='Ekspor CSV',command=self.export_screener).pack(side='left',padx=6)
        ttk.Button(tool,text='Buka Stock Detail',command=self.open_screen_stock).pack(side='right')
        cols=['ticker','sector','close','change','volume','value','cap','net','foreign_multi','roe','net_margin','der','pbv','per','fund_period']
        headings=['Ticker','Sektor','Close Rp','Change %','Volume (lembar)','Value Rp','Market Cap Rp','Foreign Net 1D','Foreign Net Multi','ROE %','Net Margin %','DER x','PBV x','PER x','Periode fundamental']
        widths=[90,185,105,105,150,175,170,150,150,95,110,85,85,85,145]
        panel=ttk.Frame(self.screen_tab,padding=8);panel.pack(fill='both',expand=True)
        self.scr_tree=ttk.Treeview(panel,columns=cols,show='headings',height=20)
        for col,head,w in zip(cols,headings,widths):
            self.scr_tree.heading(col,text=head,command=lambda c=col:self.sort_screener(c))
            self.scr_tree.column(col,width=w,minwidth=65,anchor='w' if col in ('ticker','sector','fund_period') else 'e',stretch=False)
        vs=ttk.Scrollbar(panel,orient='vertical',command=self.scr_tree.yview)
        hs=ttk.Scrollbar(panel,orient='horizontal',command=self.scr_tree.xview)
        self.scr_tree.configure(yscrollcommand=vs.set,xscrollcommand=hs.set)
        self.scr_tree.grid(row=0,column=0,sticky='nsew');vs.grid(row=0,column=1,sticky='ns');hs.grid(row=1,column=0,sticky='ew')
        panel.rowconfigure(0,weight=1);panel.columnconfigure(0,weight=1)
        self.scr_tree.bind('<Double-1>',lambda e:self.open_screen_stock())
        self.scr_status=tk.StringVar(value='')
        ttk.Label(self.screen_tab,textvariable=self.scr_status,padding=(10,4),wraplength=1250).pack(fill='x')
        ttk.Label(self.screen_tab,text='Fundamental: snapshot terbaru per metrik, bukan point-in-time; rasio dilaporkan, bukan dihitung ulang pada close harian. Foreign dalam lembar saham, bukan Rp.',padding=(10,4),wraplength=1250,foreground='#436078').pack(fill='x')
        self.scr_sort={}

    def _latest_ratios(self):
        out=defaultdict(dict)
        with ro_conn() as con:
            for table in ('fundamental','fundamental_annual'):
                if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():continue
                cols={r['name'] for r in con.execute(f'PRAGMA table_info({table})')}
                wanted={'ticker','metric','raw_value','fiscal_year'}
                if not wanted.issubset(cols):continue
                q='fiscal_quarter' if 'fiscal_quarter' in cols else 'NULL AS fiscal_quarter'
                rows=con.execute(f'SELECT ticker,metric,raw_value,fiscal_year,{q} FROM {table} WHERE metric IN (\'roe_reported\',\'pbv_reported\',\'per_reported\') ORDER BY fiscal_year DESC, fiscal_quarter DESC').fetchall()
                for r in rows:
                    t=str(r['ticker']).strip().upper();m=r['metric']
                    if m not in out[t]:
                        per=f"{r['fiscal_year']} Q{r['fiscal_quarter']}" if r['fiscal_quarter'] is not None else f"FY{r['fiscal_year']}"
                        out[t][m]=(number(r['raw_value']),per)
        return out

    def _thresholds(self):
        return {k:self.extra_ranges[k][v.get()] for k,v in self.scr_vars.items()}

    def _foreign_multiday(self,period):
        # Hanya saham dengan data lengkap pada seluruh N sesi terpilih.
        result={}
        with ro_conn() as con:
            dates=[r[0] for r in con.execute('SELECT DISTINCT trade_date FROM daily WHERE trade_date<=? ORDER BY trade_date DESC LIMIT ?',(self.date.get(),period))]
            if len(dates)<period:return result,False
            pl=','.join('?' for _ in dates)
            q=f"""SELECT ticker,COUNT(DISTINCT trade_date),SUM(foreign_buy-foreign_sell),COUNT(foreign_buy),COUNT(foreign_sell)
                  FROM daily WHERE trade_date IN ({pl}) GROUP BY ticker"""
            for t,n,net,nb,ns in con.execute(q,dates):
                if n==period and nb==period and ns==period and net is not None:
                    result[str(t).strip().upper()]=float(net)
        return result,True

    @staticmethod
    def _in_range(v, bounds):
        lower, upper = bounds
        if lower is None and upper is None:
            return True
        return v is not None and (lower is None or v >= lower) and (upper is None or v < upper)

    def run_screener(self):
        try:
            lim=self._thresholds();ratio=self._latest_ratios()
            price_bounds=self.price_ranges[self.price_choice.get()]
            change_bounds=self.change_ranges[self.change_choice.get()]
            period=int(self.foreign_horizon.get())
            flows,complete_period=self._foreign_multiday(period)
            all_rows=self.rows;selected=self.sector.get()
            selected_rows=[]
            for r in all_rows:
                if selected!='Semua Sektor' and r['sector']!=selected:continue
                vals=ratio.get(r['ticker'],{})
                def metric(m):return vals.get(m,(None,''))[0]
                roe=metric('roe_reported');pbv=metric('pbv_reported');per=metric('per_reported')
                der=metric('der_reported');margin=metric('net_margin_reported')
                fm=flows.get(r['ticker'])
                if self.scr_require.get() and not (roe is not None and pbv is not None and per is not None):continue
                observed={'volume':r['volume'],'value':r['value'],'net':r['net'],
                  'roe':roe,'pbv':pbv,'per':per,'der':der,'cap':r['cap'],
                  'foreign_multi':fm,'net_margin':margin}
                if not self._in_range(r['close'],price_bounds) or not self._in_range(r['change_pct'],change_bounds):continue
                if any(not self._in_range(observed[k],bounds) for k,bounds in lim.items()):continue
                periods=sorted({p for _,p in vals.values() if p})
                selected_rows.append({'ticker':r['ticker'],'sector':r['sector'],'close':r['close'],
                  'change':r['change_pct'],'volume':r['volume'],'value':r['value'],'cap':r['cap'],
                  'net':r['net'],'foreign_multi':fm,'roe':roe,'net_margin':margin,'der':der,
                  'pbv':pbv,'per':per,'fund_period':', '.join(periods)})
            self.scr_data=sorted(selected_rows,key=lambda r:(r['change'] is not None,r['change'] or 0),reverse=True)
            self.show_screener()
            warn='' if complete_period else f' | PERINGATAN: histori {period} sesi belum cukup, Foreign Net Multi = N/A'
            self.scr_status.set(f'{len(self.scr_data)} saham lolos dari {len(all_rows)} | {self.date.get()} | {selected} | Foreign multi {period} sesi{warn}')
        except Exception as e:messagebox.showerror('Stock Screener',str(e))

    def show_screener(self):
        tv=self.scr_tree
        for k in tv.get_children():tv.delete(k)
        for r in self.scr_data:
            formatted=[]
            for k in tv['columns']:
                v=r.get(k)
                if v is None:formatted.append('N/A')
                elif isinstance(v,(int,float)):formatted.append(f'{v:,.2f}' if k in ('change','roe','net_margin','der','pbv','per') else f'{v:,.0f}')
                else:formatted.append(str(v))
            tv.insert('','end',values=formatted)

    def sort_screener(self,key):
        descending=not self.scr_sort.get(key,False)
        self.scr_sort[key]=descending
        self.scr_data.sort(key=lambda r:(r.get(key) is not None,r.get(key) if r.get(key) is not None else (0 if key not in ('sector','ticker','fund_period') else '')),reverse=descending)
        self.show_screener()

    def reset_screener(self):
        for k,v in self.scr_vars.items():v.set(next(iter(self.extra_ranges[k])))
        self.foreign_horizon.set('5')
        self.price_choice.set('Semua harga')
        self.change_choice.set('Semua perubahan')
        self.scr_require.set(False);self.run_screener()

    def open_screen_stock(self):
        sel=self.scr_tree.selection()
        if sel:self.open_stock(self.scr_tree.item(sel[0],'values')[0])
        else:messagebox.showinfo('Pilih saham','Pilih satu ticker dalam tabel terlebih dahulu.')

    def export_screener(self):
        if not self.scr_data:return
        out=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile=f'Screener_{self.date.get()}.csv')
        if not out:return
        fields=list(self.scr_data[0].keys())
        with open(out,'w',newline='',encoding='utf-8-sig') as f:
            wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(self.scr_data)
        self.scr_status.set(f'CSV diekspor: {out}')

if __name__=='__main__':
    DashboardScreener().mainloop()
