#!/usr/bin/env python3
"""Treemap BEI V2: GUI Tkinter, chart langsung di Canvas, SQLite read-only.
Tidak mengubah skrip pengguna atau tabel database. Python standar saja.
"""
import csv
import datetime
import os
import sqlite3
import traceback
from collections import defaultdict
import math
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from treemap_v2_engine import parse_xlsx_sector_map, recursive_layout, num

BASE = Path(__file__).resolve().parent
DB = BASE / 'pasar_bei_prototipe.db'
SECTOR_FILE = BASE / 'Daftar Saham  sektor.xlsx'
MODE_NAMES = {'net': 'Foreign Net Buy/Sell', 'buy': 'Foreign Buy', 'sell': 'Foreign Sell'}


def collect(conn, dates, sector_map):
    placeholders = ','.join('?' for _ in dates)
    query = 'SELECT trade_date,ticker,company,foreign_buy,foreign_sell FROM daily WHERE trade_date IN (' + placeholders + ')'
    all_tickers = {}
    for date, ticker, company, buy, sell in conn.execute(query, dates):
        ticker = str(ticker or '').strip().upper()
        if not ticker:
            continue
        d = all_tickers.setdefault(ticker, {'ticker': ticker, 'company': company or '', 'sector': sector_map.get(ticker, 'Unknown'), 'dates': set(), 'buy': 0., 'sell': 0.})
        if date in d['dates']:
            raise ValueError(f'Duplikat data {ticker} pada {date}')
        d['dates'].add(date)
        bv, sv = num(buy), num(sell)
        if bv is None or sv is None:
            raise ValueError(f'Volume foreign tidak lengkap untuk {ticker} pada {date}')
        d['buy'] += bv
        d['sell'] += sv
    rows = []
    for d in all_tickers.values():
        if len(d['dates']) == len(dates):
            rows.append({k: d[k] for k in ('ticker', 'company', 'sector', 'buy', 'sell')} | {'net': d['buy'] - d['sell']})
    return rows, len(all_tickers) - len(rows)


class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('BEI Integrated Foreign Flow Dashboard V1')
        self.geometry('1440x900')
        self.minsize(990, 670)
        self.mode = tk.StringVar(value='net')
        self.period = tk.StringVar(value='5')
        self.sector = tk.StringVar(value='Semua Sektor')
        self.top = tk.StringVar(value='20')
        self.end_date = tk.StringVar()
        self.manual = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Memuat database...')
        self.date_caption = tk.StringVar(value='')
        self.dates = []
        self.rows = []
        self.visible = []
        self.selected_dates = []
        self.drawn = []
        self.hover = None
        self.last_run = None
        self._build()
        self._build_daily()
        self.reload()

    def _build(self):
        self.configure(bg='#f3f6fb')
        header = ttk.Frame(self, padding=(14, 12))
        header.pack(fill='x')
        ttk.Label(header, text='Foreign Flow BEI', font=('Segoe UI', 18, 'bold')).pack(side='left')
        ttk.Label(header, text='Sector → Ticker  |  volume saham, bukan nilai Rp', font=('Segoe UI', 10)).pack(side='left', padx=16)
        control = ttk.LabelFrame(self, text='Pengaturan analisis', padding=10)
        control.pack(fill='x', padx=14)
        for i in range(10):
            control.columnconfigure(i, weight=1)
        ttk.Label(control, text='Mode').grid(row=0, column=0, sticky='w')
        ttk.Combobox(control, textvariable=self.mode, values=['net','buy','sell'], state='readonly', width=11).grid(row=1,column=0,sticky='ew',padx=(0,10))
        ttk.Label(control, text='Periode').grid(row=0,column=1,sticky='w')
        self.period_c = ttk.Combobox(control, textvariable=self.period,values=['1','5','10','20'],state='readonly',width=6)
        self.period_c.grid(row=1,column=1,sticky='ew',padx=(0,10))
        self.period_c.bind('<<ComboboxSelected>>',lambda e:self.sync_dates())
        ttk.Label(control,text='Tanggal akhir').grid(row=0,column=2,sticky='w')
        self.end_c=ttk.Combobox(control,textvariable=self.end_date,state='readonly',width=13)
        self.end_c.grid(row=1,column=2,sticky='ew',padx=(0,10))
        self.end_c.bind('<<ComboboxSelected>>',lambda e:self.on_end_change())
        ttk.Label(control,text='Sektor').grid(row=0,column=3,columnspan=3,sticky='w')
        self.sector_c=ttk.Combobox(control,textvariable=self.sector,state='readonly',width=24)
        self.sector_c.grid(row=1,column=3,columnspan=3,sticky='ew',padx=(0,10))
        self.sector_c.bind('<<ComboboxSelected>>',lambda e:self.on_sector_change())
        ttk.Label(control,text='Top N (treemap)').grid(row=0,column=6,sticky='w')
        ttk.Combobox(control,textvariable=self.top,values=['10','20','50','Semua'],state='readonly',width=9).grid(row=1,column=6,sticky='ew',padx=(0,10))
        self.manual_chk=ttk.Checkbutton(control,text='Tanggal bebas',variable=self.manual,command=self.toggle_manual)
        self.manual_chk.grid(row=1,column=7,sticky='w',padx=4)
        ttk.Button(control,text='Hitung & Tampilkan',command=self.run).grid(row=1,column=8,sticky='ew',padx=4)
        ttk.Button(control,text='Ekspor CSV',command=self.export_csv).grid(row=1,column=9,sticky='ew',padx=4)

        dates_frame=ttk.Frame(self,padding=(14,5))
        dates_frame.pack(fill='x')
        ttk.Label(dates_frame,textvariable=self.date_caption,font=('Segoe UI',9)).pack(side='left',fill='x',expand=True)
        ttk.Button(dates_frame,text='Pilih tanggal manual',command=self.pick_dates).pack(side='right',padx=5)
        ttk.Button(dates_frame,text='Muat ulang database',command=self.reload).pack(side='right',padx=5)

        body=ttk.PanedWindow(self,orient='horizontal')
        self.body=body
        body.pack(fill='both',expand=True,padx=14,pady=(4,12))
        left=ttk.Frame(body)
        right=ttk.Frame(body,width=390)
        body.add(left,weight=4)
        body.add(right,weight=2)
        ttk.Label(left,text='Treemap — luas sesuai absolut volume foreign',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,6))
        self.canvas=tk.Canvas(left,background='#ffffff',highlightthickness=1,highlightbackground='#d1d9e6')
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda event:self.redraw())
        self.canvas.bind('<Motion>',self.on_move)
        self.canvas.bind('<Leave>',lambda e:self.hide_tooltip())
        self.tooltip=tk.Label(self.canvas,bg='#101c31',fg='white',font=('Segoe UI',9),justify='left',padx=8,pady=6)
        ttk.Label(right,text='Ranking Foreign Flow — seluruh saham sesuai sektor',font=('Segoe UI',10,'bold'),wraplength=340).pack(anchor='w',pady=(0,6))
        ttk.Label(right,text='Top Net Buy',font=('Segoe UI',10,'bold')).pack(anchor='w')
        self.buy_tree=self._table(right)
        ttk.Label(right,text='Top Net Sell',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(12,0))
        self.sell_tree=self._table(right)
        ttk.Label(right,text='Ringkasan sektor',font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(12,0))
        self.sector_tree=ttk.Treeview(right,columns=('sector','net'),show='headings',height=6)
        self.sector_tree.heading('sector',text='Sektor');self.sector_tree.heading('net',text='Net (saham)')
        self.sector_tree.column('sector',width=145,anchor='w');self.sector_tree.column('net',width=135,anchor='e')
        self.sector_tree.pack(fill='both',expand=True)
        footer=ttk.Label(self,textvariable=self.status,anchor='w',wraplength=1300,padding=(14,4))
        footer.pack(fill='x')
        self.canvas.create_text(30,30,anchor='nw',text='Pilih parameter, lalu klik Hitung & Tampilkan',font=('Segoe UI',13))

    def _table(self,parent):
        tv=ttk.Treeview(parent,columns=('ticker','sector','amount'),show='headings',height=9)
        for key,title,width in [('ticker','Kode',65),('sector','Sektor',125),('amount','Net (saham)',130)]:
            tv.heading(key,text=title);tv.column(key,width=width,anchor='e' if key=='amount' else 'w')
        tv.pack(fill='both',expand=True)
        return tv

    def reload(self):
        try:
            if not DB.is_file(): raise FileNotFoundError(f'Database tidak ada: {DB}')
            with sqlite3.connect(f'{DB.resolve().as_uri()}?mode=ro',uri=True) as c:
                self.dates=[r[0] for r in c.execute('SELECT DISTINCT trade_date FROM daily ORDER BY trade_date DESC')]
            if not self.dates: raise ValueError('Belum ada data perdagangan dalam tabel daily')
            self.mapping=parse_xlsx_sector_map(SECTOR_FILE)
            sectors=sorted(set(self.mapping.values()))
            self.sector_c['values']=['Semua Sektor']+sectors
            if self.sector.get() not in self.sector_c['values']:self.sector.set('Semua Sektor')
            self.end_c['values']=self.dates
            if self.end_date.get() not in self.dates:self.end_date.set(self.dates[0])
            self.sync_dates()
            self.load_daily()
            self.status.set(f'{len(self.dates)} sesi tersedia | Database: {DB.name} | Read-only')
        except Exception as e:
            messagebox.showerror('Gagal membaca data',str(e))
            self.status.set('GAGAL: '+str(e))

    def toggle_manual(self):
        self.end_c.configure(state='disabled' if self.manual.get() else 'readonly')
        if self.manual.get():
            self.selected_dates=[]
            self.pick_dates()
        else:
            self.sync_dates()

    def sync_dates(self):
        if self.manual.get():
            self.date_caption.set('Pilihan manual: '+(', '.join(self.selected_dates) if self.selected_dates else 'Belum ada'))
        else:
            pos=self.dates.index(self.end_date.get()) if self.end_date.get() in self.dates else 0
            self.selected_dates=sorted(self.dates[pos:pos+int(self.period.get())])
            self.date_caption.set(f'{len(self.selected_dates)}/{self.period.get()} tanggal: '+', '.join(self.selected_dates))

    def pick_dates(self):
        if not self.manual.get():
            messagebox.showinfo('Mode tanggal','Aktifkan kotak Tanggal bebas terlebih dahulu.')
            return
        dlg=tk.Toplevel(self);dlg.title('Pilih tanggal perdagangan secara bebas');dlg.geometry('440x530');dlg.transient(self);dlg.grab_set()
        ttk.Label(dlg,text=f'Pilih tepat {self.period.get()} tanggal (Ctrl+klik)',padding=10).pack(anchor='w')
        frame=ttk.Frame(dlg,padding=10);frame.pack(fill='both',expand=True)
        listbox=tk.Listbox(frame,selectmode='extended',exportselection=False,font=('Consolas',10));listbox.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(frame,command=listbox.yview);scrollbar.pack(side='right',fill='y');listbox.configure(yscrollcommand=scrollbar.set)
        for i,d in enumerate(self.dates):
            listbox.insert('end',d)
            if d in self.selected_dates:listbox.selection_set(i)
        def save():
            sel=sorted([self.dates[i] for i in listbox.curselection()])
            if len(sel)!=int(self.period.get()):
                messagebox.showwarning('Jumlah tidak sesuai',f'Pilih tepat {self.period.get()} tanggal.',parent=dlg)
                return
            self.selected_dates=sel;self.sync_dates();dlg.destroy()
        ttk.Button(dlg,text='Gunakan tanggal pilihan',command=save).pack(pady=10)

    def run(self):
        self.sync_dates() if not self.manual.get() else None
        dates=list(self.selected_dates)
        n=int(self.period.get())
        if len(dates)!=n:
            messagebox.showwarning('Tanggal belum lengkap',f'Diperlukan tepat {n} tanggal, saat ini {len(dates)}')
            return
        try:
            with sqlite3.connect(f'{DB.resolve().as_uri()}?mode=ro',uri=True) as conn:
                rows,skipped=collect(conn,dates,self.mapping)
            selected_sector=self.sector.get()
            if selected_sector!='Semua Sektor':rows=[r for r in rows if r['sector']==selected_sector]
            if not rows:raise ValueError('Tidak ada saham dengan data lengkap untuk pilihan ini')
            mode=self.mode.get();sorted_rows=sorted(rows,key=lambda r:abs(r[mode]),reverse=True)
            if self.top.get()=='Semua':self.visible=[r for r in sorted_rows if abs(r[mode])>0]
            else:self.visible=[r for r in sorted_rows if abs(r[mode])>0][:int(self.top.get())]
            self.rows=rows
            if not self.visible:raise ValueError('Tidak ada foreign volume non-nol pada pilihan ini')
            self.last_run={'mode':mode,'dates':dates,'sector':selected_sector,'top':self.top.get(),'rows':rows,'visible':self.visible}
            self.show_rankings()
            self.redraw()
            self.status.set(f'BERHASIL | {MODE_NAMES[mode]} | {n} sesi ({dates[0]} s.d. {dates[-1]}) | {len(rows)} saham lengkap dalam filter | {len(self.visible)} saham pada treemap | {skipped} saham tidak lengkap (semua sektor) | volume saham, bukan Rp')
        except Exception as e:
            messagebox.showerror('Gagal menghitung',str(e))
            self.status.set('GAGAL: '+str(e))

    def show_rankings(self):
        for tree in (self.buy_tree,self.sell_tree,self.sector_tree):
            for i in tree.get_children():tree.delete(i)
        # Ranking tetap net, meskipun treemap menampilkan gross Buy atau gross Sell.
        buys=sorted([r for r in self.rows if r['net']>0],key=lambda r:r['net'],reverse=True)[:10]
        sells=sorted([r for r in self.rows if r['net']<0],key=lambda r:r['net'])[:10]
        for tree,items in ((self.buy_tree,buys),(self.sell_tree,sells)):
            for r in items:tree.insert('','end',values=(r['ticker'],r['sector'],f'{r["net"]:,.0f}'))
        sec=defaultdict(float)
        for r in self.rows:sec[r['sector']]+=r['net']
        for name,total in sorted(sec.items(),key=lambda x:abs(x[1]),reverse=True):
            self.sector_tree.insert('','end',values=(name,f'{total:,.0f}'))

    def redraw(self):
        c=self.canvas
        c.delete('all');self.drawn=[]
        if not self.last_run:return
        w=max(c.winfo_width(),400);h=max(c.winfo_height(),300)
        mode=self.last_run['mode']
        sections=defaultdict(list)
        for r in self.visible:sections[r['sector']].append(r)
        blocks=[]
        for sector,items in sections.items():
            blocks.append({'sector':sector,'size':sum(abs(r[mode]) for r in items),'rows':items})
        blocks.sort(key=lambda s:s['size'],reverse=True)
        if not blocks:return
        # Independent rectangles in Canvas, retaining original Sector -> Ticker grouping.
        area_w=w-20;area_h=h-30
        layout=recursive_layout(blocks,10,8,area_w,area_h)
        for sx,sy,sw,sh,block in layout:
            c.create_rectangle(sx,sy,sx+sw,sy+sh,outline='white',width=2,fill='#f0f4fa')
            head=min(24,max(14,sh*.12))
            c.create_rectangle(sx,sy,sx+sw,sy+head,fill='#253e61',outline='#253e61')
            if sw>36:
                label=block['sector'] if sw>100 else block['sector'][:max(2,int(sw//8))]
                c.create_text(sx+4,sy+head/2,text=label,fill='white',anchor='w',font=('Segoe UI',9,'bold'))
            inner_w=max(0.5,sw-2);inner_h=max(0.5,sh-head-1)
            if inner_h<1:continue
            items=[{'size':abs(r[mode]),'row':r} for r in sorted(block['rows'],key=lambda r:abs(r[mode]),reverse=True)]
            for tx,ty,tw,th,item in recursive_layout(items,sx+1,sy+head,inner_w,inner_h):
                r=item['row'];v=r[mode]
                fill=('#1976d2' if mode=='buy' else '#e07b25' if mode=='sell' else '#269b65' if v>=0 else '#d9363e')
                rect=c.create_rectangle(tx,ty,tx+tw,ty+th,fill=fill,outline='white',width=1)
                self.drawn.append((rect,r))
                if tw>55 and th>31:
                    fs=10 if tw>95 else 8
                    c.create_text(tx+tw/2,ty+th/2-7,text=r['ticker'],font=('Segoe UI',fs,'bold'),fill='white')
                    c.create_text(tx+tw/2,ty+th/2+8,text=f'{v:,.0f}',font=('Segoe UI',max(fs-2,7)),fill='white')

    def hide_tooltip(self):
        self.tooltip.place_forget();self.hover=None

    def on_move(self,event):
        found=None
        items=self.canvas.find_overlapping(event.x,event.y,event.x,event.y)
        lookup={item:r for item,r in self.drawn}
        for item in reversed(items):
            if item in lookup:
                found=lookup[item];break
        if found is None:
            self.hide_tooltip();return
        self.hover=found
        self.tooltip.configure(text=f'{found["ticker"]}  —  {found["sector"]}\nBuy: {found["buy"]:,.0f}\nSell: {found["sell"]:,.0f}\nNet: {found["net"]:,.0f} saham')
        x=min(event.x+15,max(0,self.canvas.winfo_width()-255));y=min(event.y+15,max(0,self.canvas.winfo_height()-104))
        self.tooltip.place(x=x,y=y)
        self.tooltip.lift()

    def export_csv(self):
        if not self.last_run:
            messagebox.showinfo('Belum ada analisis','Jalankan Hitung & Tampilkan terlebih dahulu.')
            return
        path=filedialog.asksaveasfilename(parent=self,title='Ekspor data semua saham lengkap',defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile=f'Foreign_Flow_{self.last_run["mode"]}_{len(self.last_run["dates"])}D_{self.last_run["dates"][-1]}.csv')
        if not path:return
        try:
            with open(path,'w',newline='',encoding='utf-8-sig') as f:
                wr=csv.writer(f)
                wr.writerow(['ticker','company','sector','foreign_buy_volume','foreign_sell_volume','foreign_net_volume','selected_dates'])
                ds=';'.join(self.last_run['dates'])
                for r in sorted(self.rows,key=lambda r:abs(r['net']),reverse=True):
                    wr.writerow([r['ticker'],r['company'],r['sector'],round(r['buy']),round(r['sell']),round(r['net']),ds])
            self.status.set('CSV tersimpan: '+str(path))
        except Exception as e:messagebox.showerror('Ekspor gagal',str(e))


    def _build_daily(self):
        self.daily_rows=[]
        self.daily_bars=[]
        self.daily_selected=None
        panel=ttk.LabelFrame(self, text='Foreign Net Harian — klik batang untuk memilih tanggal akhir treemap', padding=(8,4))
        panel.pack(fill='x', padx=14, pady=(3,4), before=self.body)
        bar=ttk.Frame(panel); bar.pack(fill='x')
        self.daily_info=tk.StringVar(value='Klik batang pada grafik harian. Satuan: lembar saham, bukan Rp.')
        ttk.Label(bar,textvariable=self.daily_info).pack(side='left',fill='x',expand=True)
        ttk.Button(bar,text='Buka Analytics (Proxy / ROE)',command=self.open_analytics).pack(side='right')
        self.daily_canvas=tk.Canvas(panel,height=187,bg='white',highlightthickness=0,cursor='hand2')
        self.daily_canvas.pack(fill='x')
        self.daily_canvas.bind('<Configure>',lambda e:self.draw_daily())
        self.daily_canvas.bind('<Motion>',self.hover_daily)
        self.daily_canvas.bind('<Leave>',lambda e:self.reset_daily_info())
        self.daily_canvas.bind('<Button-1>',self.click_daily)

    def open_analytics(self):
        path=BASE/'bei_analytics_gui.py'
        if not path.is_file():
            messagebox.showinfo('Analytics belum ditemukan', 'File bei_analytics_gui.py belum tersedia di folder aplikasi. Dashboard terintegrasi tetap dapat digunakan.')
            return
        subprocess.Popen([sys.executable,str(path)],cwd=str(BASE))

    def on_end_change(self):
        self.sync_dates()
        self.draw_daily()

    def on_sector_change(self):
        self.load_daily()
        if self.selected_dates and len(self.selected_dates)==int(self.period.get()):
            self.run()

    def load_daily(self):
        # Sumber yang sama dengan mesin treemap: tabel daily, volume saham.
        if not DB.is_file(): return
        sector=self.sector.get()
        sector_map=getattr(self,'mapping',{})
        dates=defaultdict(lambda:[0.,0.,0])
        with sqlite3.connect(f'{DB.resolve().as_uri()}?mode=ro',uri=True) as c:
            for d,t,b,s in c.execute('SELECT trade_date,ticker,foreign_buy,foreign_sell FROM daily ORDER BY trade_date,ticker'):
                ticker=str(t or '').strip().upper()
                if sector!='Semua Sektor' and sector_map.get(ticker,'Unknown')!=sector:continue
                if b is None or s is None: continue
                try:
                    bv=float(b);sv=float(s)
                except (ValueError,TypeError):continue
                if not (math.isfinite(bv) and math.isfinite(sv)):continue
                rec=dates[d];rec[0]+=bv;rec[1]+=sv;rec[2]+=1
        self.daily_rows=[(d,*v,v[0]-v[1]) for d,v in sorted(dates.items())]
        self.draw_daily()

    def reset_daily_info(self):
        if hasattr(self,'daily_info'):
            self.daily_info.set('Klik batang untuk memilih tanggal akhir treemap. Net = Foreign Buy − Foreign Sell (lembar saham).')

    def draw_daily(self):
        if not hasattr(self,'daily_canvas'):return
        c=self.daily_canvas;c.delete('all');self.daily_bars=[]
        data=getattr(self,'daily_rows',[])
        if not data:return
        w=max(c.winfo_width(),480);h=max(c.winfo_height(),187)
        left,right,top,bottom=66,w-12,14,h-31
        net=[r[4] for r in data]
        low=min(0,min(net)); high=max(0,max(net))
        if low==high:low=-1;high=1
        def yy(v):return bottom-(v-low)/(high-low)*(bottom-top)
        zero=yy(0)
        c.create_line(left,zero,right,zero,fill='#718096')
        for i in range(5):
            value=low+(high-low)*i/4;y=yy(value)
            c.create_line(left,y,right,y,fill='#edf1f5')
            display=f'{value/1e9:,.2f} M' if abs(value)>=1e9 else f'{value/1e6:,.1f} jt'
            c.create_text(left-5,y,text=display,anchor='e',font=('Segoe UI',8),fill='#516173')
        bw=(right-left)/len(data)
        for i,r in enumerate(data):
            date,buy,sell,coverage,value=r
            x=left+(i+.5)*bw
            y=yy(value)
            pad=max(1,min(18,bw*.33))
            width=max(1,min(pad,bw*.46))
            if abs(y-zero)<1.5:y=zero+(-1.5 if value>=0 else 1.5)
            rect=c.create_rectangle(x-width,min(y,zero),x+width,max(y,zero),outline='#172f50' if date==self.end_date.get() else '',width=2 if date==self.end_date.get() else 0,fill='#238759' if value>=0 else '#d04444')
            self.daily_bars.append((rect,x-width,x+width,min(y,zero),max(y,zero),r))
            every=max(1,math.ceil(len(data)/15))
            if i%every==0 or i==len(data)-1:
                c.create_text(x,bottom+11,text=date[5:],font=('Segoe UI',8),fill='#455569',angle=32,anchor='ne')

    def _bar_at(self,x,y):
        for entry in self.daily_bars:
            _,x0,x1,y0,y1,r=entry
            if x0-2<=x<=x1+2 and y0-3<=y<=y1+3:return r
        return None

    def hover_daily(self,event):
        r=self._bar_at(event.x,event.y)
        if r:
            date,buy,sell,count,net=r
            self.daily_info.set(f'{date} | {self.sector.get()} | Buy {buy:,.0f} | Sell {sell:,.0f} | Net {net:+,.0f} lembar | {count} saham')
        else:self.reset_daily_info()

    def click_daily(self,event):
        r=self._bar_at(event.x,event.y)
        if not r:return
        date=r[0]
        if self.manual.get():
            self.manual.set(False)
            self.end_c.configure(state='readonly')
        self.end_date.set(date)
        self.sync_dates()
        if len(self.selected_dates)!=int(self.period.get()):
            messagebox.showwarning('Histori tidak cukup',f'Belum tersedia {self.period.get()} sesi hingga {date}.')
            return
        self.run()
        self.draw_daily()


if __name__=='__main__':
    Dashboard().mainloop()
