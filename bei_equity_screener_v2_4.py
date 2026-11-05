#!/usr/bin/env python3
"""BEI Equity Analytics V2.4: Stock Screener extension (SQLite read-only)."""
import csv, math, tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from collections import defaultdict
from bei_equity_v2_3_3 import App, ro_conn, fundamentals, number, BASE

class DashboardScreener(App):
    def __init__(self):
        super().__init__()
        self.title('BEI Equity Analytics V2.4 — Stock Screener')
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
        filters=[('Min Harga Rp','min_price',''),('Max Harga Rp','max_price',''),
                 ('Min Change %','min_change',''),('Max Change %','max_change',''),
                 ('Min Volume (lembar)','min_volume',''),('Min Value (Rp)','min_value',''),
                 ('Min Net Foreign (lembar)','min_net',''),('Max Net Foreign (lembar)','max_net',''),
                 ('Min ROE %','min_roe',''),('Max PBV x','max_pbv',''),('Max PER x','max_per','')]
        for i,(label,key,default) in enumerate(filters):
            row=i//4;col=(i%4)*2
            ttk.Label(top,text=label).grid(row=row,column=col,sticky='w',padx=3,pady=3)
            v=tk.StringVar(value=default);self.scr_vars[key]=v
            ttk.Entry(top,textvariable=v,width=15).grid(row=row,column=col+1,sticky='ew',padx=3,pady=3)
        for c in range(8):top.columnconfigure(c,weight=1)
        tool=ttk.Frame(self.screen_tab,padding=(8,3));tool.pack(fill='x')
        self.scr_require=tk.BooleanVar(value=False)
        ttk.Checkbutton(tool,text='Hanya saham dengan data ROE, PBV, dan PER lengkap',variable=self.scr_require).pack(side='left')
        ttk.Button(tool,text='Jalankan Screener',command=self.run_screener).pack(side='left',padx=6)
        ttk.Button(tool,text='Reset Filter',command=self.reset_screener).pack(side='left',padx=6)
        ttk.Button(tool,text='Ekspor CSV',command=self.export_screener).pack(side='left',padx=6)
        ttk.Button(tool,text='Buka Stock Detail',command=self.open_screen_stock).pack(side='right')
        cols=['ticker','company','sector','close','change','volume','value','net','roe','pbv','per','fund_period']
        headings=['Ticker','Nama Perusahaan','Sektor','Close Rp','Change %','Volume (lembar)','Value Rp','Foreign Net (lembar)','ROE %','PBV x','PER x','Periode fundamental']
        widths=[75,230,155,100,96,145,155,175,95,85,85,145]
        panel=ttk.Frame(self.screen_tab,padding=8);panel.pack(fill='both',expand=True)
        self.scr_tree=ttk.Treeview(panel,columns=cols,show='headings',height=20)
        for col,head,w in zip(cols,headings,widths):
            self.scr_tree.heading(col,text=head,command=lambda c=col:self.sort_screener(c))
            self.scr_tree.column(col,width=w,minwidth=65,anchor='w' if col in ('ticker','company','sector','fund_period') else 'e',stretch=False)
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
        result={}
        for k,v in self.scr_vars.items():
            s=v.get().strip().replace(',','')
            try:result[k]=float(s) if s else None
            except ValueError:raise ValueError(f'Input {k} harus angka atau kosong: {s!r}')
        return result

    def run_screener(self):
        try:
            lim=self._thresholds(); ratio=self._latest_ratios()
            all_rows=self.rows
            selected=self.sector.get()
            def good(v,minv=None,maxv=None):
                if minv is None and maxv is None:return True
                return v is not None and (minv is None or v>=minv) and (maxv is None or v<=maxv)
            selected_rows=[]
            for r in all_rows:
                if selected!='Semua Sektor' and r['sector']!=selected:continue
                vals=ratio.get(r['ticker'],{})
                roe=vals.get('roe_reported',(None,''))[0]
                pbv=vals.get('pbv_reported',(None,''))[0]
                per=vals.get('per_reported',(None,''))[0]
                if self.scr_require.get() and not (roe is not None and pbv is not None and per is not None):continue
                if not all((good(r['close'],lim['min_price'],lim['max_price']),good(r['change_pct'],lim['min_change'],lim['max_change']),good(r['volume'],lim['min_volume']),good(r['value'],lim['min_value']),good(r['net'],lim['min_net'],lim['max_net']),good(roe,lim['min_roe']),good(pbv,maxv=lim['max_pbv']),good(per,maxv=lim['max_per']))):continue
                periods=sorted({p for _,p in vals.values() if p})
                selected_rows.append({'ticker':r['ticker'],'company':self.company_names.get(r['ticker'],'') ,'sector':r['sector'], 'close':r['close'], 'change':r['change_pct'], 'volume':r['volume'], 'value':r['value'], 'net':r['net'], 'roe':roe, 'pbv':pbv, 'per':per, 'fund_period':', '.join(periods)})
            self.scr_data=sorted(selected_rows,key=lambda r:(r['change'] is not None,r['change'] or 0),reverse=True)
            self.show_screener()
            self.scr_status.set(f'{len(self.scr_data)} saham lolos filter dari {len(all_rows)} saham pada {self.date.get()} | Sektor: {selected} | Klik header untuk urutkan, klik dua kali ticker untuk detail.')
        except Exception as e:messagebox.showerror('Stock Screener',str(e))

    def show_screener(self):
        tv=self.scr_tree
        for k in tv.get_children():tv.delete(k)
        for r in self.scr_data:
            formatted=[]
            for k in tv['columns']:
                v=r.get(k)
                if v is None:formatted.append('N/A')
                elif isinstance(v,(int,float)):formatted.append(f'{v:,.2f}' if k in ('change','roe','pbv','per') else f'{v:,.0f}')
                else:formatted.append(str(v))
            tv.insert('','end',values=formatted)

    def sort_screener(self,key):
        descending=not self.scr_sort.get(key,False)
        self.scr_sort[key]=descending
        self.scr_data.sort(key=lambda r:(r.get(key) is not None,r.get(key) if r.get(key) is not None else (0 if key not in ('company','sector','ticker','fund_period') else '')),reverse=descending)
        self.show_screener()

    def reset_screener(self):
        for v in self.scr_vars.values():v.set('')
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
