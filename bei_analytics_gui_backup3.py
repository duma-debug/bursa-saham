#!/usr/bin/env python3
"""BEI analytics interactive viewer, Tkinter stdlib only."""
import csv, math, subprocess, sys, tkinter as tk, calendar
from datetime import datetime, date
from pathlib import Path
from tkinter import ttk, messagebox
from collections import defaultdict
from bei_analytics import calculate
BASE=Path(__file__).resolve().parent

def compact(v):
    v=float(v)
    for lim,s in [(1e12,'T'),(1e9,'M'),(1e6,'jt'),(1e3,'rb')]:
        if abs(v)>=lim:return f'{v/lim:,.2f} {s}'
    return f'{v:,.0f}'

class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__();self.title('BEI Analytics — Kapitalisasi Pasar · Foreign Harian · ROE vs Valuasi')
        self.geometry('1330x850');self.minsize(900,600)
        self.db=tk.StringVar(value=str(BASE/'pasar_bei_prototipe.db'))
        self.sector_file=tk.StringVar(value=str(BASE/'Daftar Saham  sektor.xlsx'))
        self.out=tk.StringVar(value=str(BASE/'output_analytics'))
        self.tab=tk.StringVar(value='Foreign Net Harian')
        self.metric=tk.StringVar(value='PBV');self.sector=tk.StringVar(value='Semua Sektor')
        self.date_start=tk.StringVar();self.date_end=tk.StringVar()
        self.status=tk.StringVar(value='Klik Hitung / Muat Data untuk memulai')
        self.daily=[];self.stocks=[];self.sectors=[];self.scatter=[];self.points=[]
        self.sector_daily={}
        self._ui()
    def _ui(self):
        top=ttk.Frame(self,padding=9);top.pack(fill='x')
        ttk.Label(top,text='BEI Market Analytics',font=('Segoe UI',18,'bold')).grid(row=0,column=0,columnspan=5,sticky='w')
        for i,(lab,var) in enumerate([('SQLite',self.db),('Master saham',self.sector_file),('Output',self.out)]):
            ttk.Label(top,text=lab).grid(row=i+1,column=0,sticky='w',padx=4)
            ttk.Entry(top,textvariable=var,width=84).grid(row=i+1,column=1,columnspan=3,sticky='ew',pady=2)
        ttk.Button(top,text='Hitung / Muat Data',command=self.load).grid(row=1,column=4,rowspan=3,padx=10,sticky='nsew')
        top.columnconfigure(1,weight=1)
        ctrl=ttk.Frame(self,padding=(11,4));ctrl.pack(fill='x')
        ttk.Label(ctrl,text='Chart').pack(side='left')
        cbo=ttk.Combobox(ctrl,textvariable=self.tab,values=['Foreign Net Harian','Buy & Sell Harian','Proxy Indeks Basis 100','ROE vs Valuasi'],state='readonly',width=25)
        cbo.pack(side='left',padx=6);cbo.bind('<<ComboboxSelected>>',lambda _:self.redraw())
        ttk.Label(ctrl,text='Valuasi Y').pack(side='left',padx=(15,0))
        cb=ttk.Combobox(ctrl,textvariable=self.metric,values=['PBV','PER','EV/EBITDA'],state='readonly',width=12)
        cb.pack(side='left',padx=6);cb.bind('<<ComboboxSelected>>',lambda _:self.redraw())
        ttk.Label(ctrl,text='Sektor').pack(side='left',padx=(10,0))
        cb2=ttk.Combobox(ctrl,textvariable=self.sector,values=['Semua Sektor'],state='readonly',width=24)
        cb2.pack(side='left',padx=6);cb2.bind('<<ComboboxSelected>>',lambda _:self.redraw());self.sector_box=cb2
        date=ttk.Frame(self,padding=(11,2));date.pack(fill='x')
        ttk.Label(date,text='Mulai (YYYY-MM-DD)').pack(side='left')
        ttk.Entry(date,textvariable=self.date_start,width=13).pack(side='left',padx=5)
        ttk.Button(date,text='📅',width=3,command=lambda:self.show_calendar(self.date_start)).pack(side='left')
        ttk.Label(date,text='Akhir').pack(side='left')
        ttk.Entry(date,textvariable=self.date_end,width=13).pack(side='left',padx=5)
        ttk.Button(date,text='📅',width=3,command=lambda:self.show_calendar(self.date_end)).pack(side='left')
        ttk.Button(date,text='Terapkan',command=self.redraw).pack(side='left',padx=5)
        ttk.Label(date,text='Kosong = semua sesi tersedia').pack(side='left',padx=9)
        ttk.Label(self,textvariable=self.status,foreground='#315575',padding=(12,5)).pack(fill='x')
        self.canvas=tk.Canvas(self,bg='white',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True,padx=12,pady=6)
        self.canvas.bind('<Configure>',lambda _:self.redraw())
        self.canvas.bind('<Motion>',self.on_hover)
        self.note=tk.StringVar(value='Data volume foreign dalam lembar; proxy indeks bukan IHSG resmi.')
        ttk.Label(self,textvariable=self.note,padding=(12,7),wraplength=1200).pack(fill='x')
    def load(self):
        try:
            self.status.set('Memproses SQLite (read-only) dan master saham...');self.update_idletasks()
            self.daily,self.stocks,self.sectors,self.scatter=calculate(self.db.get(),self.sector_file.get(),self.out.get())
            sector_names=sorted({r[1] for r in self.scatter}|{r[1] for r in self.sectors})
            self.sector_box['values']=['Semua Sektor']+sector_names
            self.build_sector_daily()
            self.status.set(f'BERHASIL | {len(self.daily)} sesi | {len(self.stocks)} rekaman saham-hari | {len(self.scatter)} titik valuasi | CSV: {self.out.get()}')
            self.redraw()
        except Exception as exc:
            self.status.set('ERROR: '+str(exc));messagebox.showerror('Gagal memproses data',str(exc))
    def line(self,coords,fill='#2573ab',width=2):
        if len(coords)>=4:self.canvas.create_line(*coords,fill=fill,width=width,smooth=False)
    def axes(self,x0,y0,x1,y1,title,xlabel,ylabel):
        c=self.canvas
        c.create_text((x0+x1)/2,28,text=title,font=('Segoe UI',15,'bold'),fill='#203b5b')
        c.create_line(x0,y1,x1,y1,fill='#64748b');c.create_line(x0,y0,x0,y1,fill='#64748b')
        c.create_text((x0+x1)/2,y1+45,text=xlabel,fill='#475569')
        c.create_text(14,(y0+y1)/2,text=ylabel,angle=90,fill='#475569')
    def show_calendar(self, target):
        """Calendar popup, uses only Python standard library."""
        try:
            selected=datetime.strptime(target.get().strip(),'%Y-%m-%d').date()
        except ValueError:
            selected=date.today()
        window=tk.Toplevel(self)
        window.title('Pilih tanggal perdagangan')
        window.resizable(False,False)
        window.transient(self)
        window.grab_set()
        holder=ttk.Frame(window,padding=10)
        holder.pack()
        current=[selected.year,selected.month]
        header=ttk.Frame(holder);header.pack(fill='x')
        caption=ttk.Label(header,width=25,anchor='center',font=('Segoe UI',11,'bold'))
        caption.pack(side='left',padx=6)
        days=ttk.Frame(holder);days.pack(pady=8)
        existing={r[0] for r in self.daily}
        def render():
            for widget in days.winfo_children():widget.destroy()
            year,month=current
            caption.configure(text=f'{calendar.month_name[month]} {year}')
            for j,name in enumerate(('Sen','Sel','Rab','Kam','Jum','Sab','Min')):
                ttk.Label(days,text=name,width=5,anchor='center').grid(row=0,column=j)
            for i,week in enumerate(calendar.monthcalendar(year,month),1):
                for j,day in enumerate(week):
                    if not day:continue
                    d=date(year,month,day).isoformat()
                    def choose(d=d):
                        target.set(d);window.destroy();self.redraw()
                    button=ttk.Button(days,text=str(day),width=4,command=choose)
                    button.grid(row=i,column=j,padx=1,pady=2)
                    # Database sessions are identifiable but non-session dates remain selectable.
                    if existing and d not in existing:
                        button.state(['!focus'])
        def change(n):
            k=current[0]*12+current[1]-1+n
            current[:]=[k//12,k%12+1]
            render()
        ttk.Button(header,text='◀',width=3,command=lambda:change(-1)).pack(side='left',before=caption)
        ttk.Button(header,text='▶',width=3,command=lambda:change(1)).pack(side='right')
        ttk.Button(holder,text='Kosongkan tanggal',command=lambda:(target.set(''),window.destroy(),self.redraw())).pack(fill='x')
        render()

    def build_sector_daily(self):
        """Daily buy/sell from ticker-level records; sector index based on sector caps."""
        flow=defaultdict(lambda:[0.,0.])
        for r in self.stocks:
            dt,ticker,sector,close,shares,cap,buy,sell,net=r
            if buy is not None and sell is not None:
                flow[(dt,sector)][0]+=buy
                flow[(dt,sector)][1]+=sell
        caps={(r[0],r[1]):float(r[2]) for r in self.sectors}
        previous={};idx={}
        for dt in sorted({r[0] for r in self.daily}):
            for sector in sorted({sec for day,sec in caps if day==dt}):
                cap=caps[(dt,sector)]
                val=100. if sector not in idx else idx[sector]*cap/previous[sector] if previous[sector]>0 else None
                idx[sector]=val
                previous[sector]=cap
                buy,sell=flow[(dt,sector)]
                self.sector_daily[(dt,sector)]=(buy,sell,buy-sell,val)

    def data_range(self):
        low=self.date_start.get().strip();high=self.date_end.get().strip()
        for label,value in [('Mulai',low),('Akhir',high)]:
            if value:
                try:datetime.strptime(value,'%Y-%m-%d')
                except ValueError:
                    self.status.set(f'Format tanggal {label} harus YYYY-MM-DD');return []
        if low and high and low>high:
            self.status.set('Tanggal Mulai harus sebelum atau sama dengan tanggal Akhir');return []
        sector=self.sector.get()
        filtered=[r for r in self.daily if (not low or r[0]>=low) and (not high or r[0]<=high)]
        if sector=='Semua Sektor':return filtered
        converted=[]
        for r in filtered:
            record=self.sector_daily.get((r[0],sector))
            if record is None:continue
            buy,sell,net,proxy=record
            row=list(r);row[7]=buy;row[8]=sell;row[9]=net;row[11]=proxy
            converted.append(tuple(row))
        return converted

    def redraw(self):
        if not self.winfo_exists():return
        self.canvas.delete('all');self.points=[]
        w=max(500,self.canvas.winfo_width());h=max(300,self.canvas.winfo_height())
        x0,y0,x1,y1=92,66,w-44,h-92
        kind=self.tab.get()
        if not self.daily:
            self.canvas.create_text(w/2,h/2,text='Klik “Hitung / Muat Data”',fill='#64748b',font=('Segoe UI',16));return
        if kind=='ROE vs Valuasi':self.scatterplot(x0,y0,x1,y1)
        else:self.daily_chart(x0,y0,x1,y1,kind)
    def daily_chart(self,x0,y0,x1,y1,kind):
        data=self.data_range()
        if not data:self.canvas.create_text(330,130,text='Tidak ada sesi pada rentang tanggal tersebut');return
        n=len(data);width=(x1-x0)/n; values=[]
        if kind=='Foreign Net Harian':values=[r[9] for r in data]
        elif kind=='Buy & Sell Harian':values=[v for r in data for v in (r[7],r[8])]
        else:values=[r[11] for r in data if r[11] is not None]
        if not values:return
        lo=min(0,min(values)) if kind!='Proxy Indeks Basis 100' else min(values)*0.98
        hi=max(0,max(values)) if kind!='Proxy Indeks Basis 100' else max(values)*1.02
        if lo==hi:lo-=1;hi+=1
        transform=lambda v: y1-(v-lo)/(hi-lo)*(y1-y0)
        self.axes(x0,y0,x1,y1,kind+' — '+self.sector.get(),'Tanggal perdagangan','Indeks basis 100' if kind.startswith('Proxy') else 'Volume saham')
        for j in range(5):
            v=lo+(hi-lo)*j/4;yy=transform(v)
            self.canvas.create_line(x0,yy,x1,yy,fill='#eef2f7');self.canvas.create_text(x0-8,yy,text=f'{v:.1f}' if kind.startswith('Proxy') else compact(v),anchor='e',font=('Segoe UI',9))
        label_every=max(1,math.ceil(n/13));coords=[]
        for i,r in enumerate(data):
            x=x0+(i+0.5)*width
            if i%label_every==0:self.canvas.create_text(x,y1+18,text=r[0][5:],angle=40,anchor='ne',font=('Segoe UI',9))
            if kind=='Proxy Indeks Basis 100':
                if r[11] is not None:coords.extend([x,transform(r[11])])
            elif kind=='Foreign Net Harian':
                val=r[9];ya=transform(val);zero=transform(0)
                self.canvas.create_rectangle(x-width*.32,min(ya,zero),x+width*.32,max(ya,zero),fill='#168451' if val>=0 else '#ce4444',outline='')
            else:
                for ind,val in enumerate((r[7],r[8])):
                    xx=x+(-0.19 if ind==0 else .19)*width
                    self.canvas.create_rectangle(xx-width*.16,transform(val),xx+width*.16,transform(0),fill='#1b75bb' if ind==0 else '#e19135',outline='')
        if kind=='Proxy Indeks Basis 100':self.line(coords)
        self.note.set('FOREIGN = volume lembar saham, bukan Rp. Filter sektor aktif untuk Foreign Buy/Sell dan Net. Proxy sektor berbasis kapitalisasi snapshot (bukan indeks resmi dan tidak disesuaikan corporate action); data mungkin tidak berurutan.')
    def scatterplot(self,x0,y0,x1,y1):
        metric=self.metric.get();sector=self.sector.get()
        rows=[r for r in self.scatter if r[3]==metric and (sector=='Semua Sektor' or r[1]==sector)]
        if not rows:
            self.canvas.create_text((x0+x1)/2,(y0+y1)/2,text='Tidak tersedia pasangan ROE dan '+metric+' untuk sektor ini',fill='#a15a22',font=('Segoe UI',13));return
        xs=[r[2] for r in rows];ys=[r[4] for r in rows]
        # preserve genuine values; skip no values. Axis robust: use 1%-99% for viewing while annotate clipped points.
        def q(arr,p):
            z=sorted(arr);return z[int((len(z)-1)*p)]
        xlo=min(0,q(xs,.01)-2);xhi=max(5,q(xs,.99)+2)
        ylo=0;yhi=max(1,q(ys,.95)*1.25)
        if xlo>=xhi:xhi=xlo+1
        self.axes(x0,y0,x1,y1,f'ROE vs {metric} — {sector}','ROE (%)',metric+' (x)')
        for i in range(6):
            xx=x0+i/5*(x1-x0);xv=xlo+i/5*(xhi-xlo)
            self.canvas.create_line(xx,y0,xx,y1,fill='#f1f4f8');self.canvas.create_text(xx,y1+17,text=f'{xv:.0f}%',font=('Segoe UI',9))
            yy=y1-i/5*(y1-y0);yv=yhi*i/5
            self.canvas.create_line(x0,yy,x1,yy,fill='#f1f4f8');self.canvas.create_text(x0-7,yy,text=f'{yv:.1f}',anchor='e',font=('Segoe UI',9))
        palette=['#2171b5','#cb5b33','#369264','#8b5fbf','#c89629','#555b63','#be4092','#55a3a3']
        sectors=sorted({r[1] for r in rows});colors={s:palette[i%len(palette)] for i,s in enumerate(sectors)}
        clipped=0
        for r in rows:
            t,sec,roe,_,mult,roeper,per,_=r
            if not xlo<=roe<=xhi or not ylo<=mult<=yhi:clipped+=1;continue
            x=x0+(roe-xlo)/(xhi-xlo)*(x1-x0);y=y1-(mult-ylo)/(yhi-ylo)*(y1-y0)
            self.canvas.create_oval(x-4,y-4,x+4,y+4,fill=colors[sec],outline='white')
            self.points.append((x,y,f'{t} | {sec} | ROE {roe:.2f}% | {metric} {mult:.2f}x | periode ROE {roeper} | valuasi {per}'))
        self.note.set(f'{len(rows)} pasangan data valuasi tersedia | {clipped} titik di luar batas tampilan (outlier), tidak dihapus dari CSV. Multiple dari laporan fundamental, bukan rasio harga terbaru. Hover titik untuk detail. Data fundamental bukan point-in-time.')
    def on_hover(self,e):
        if self.tab.get()!='ROE vs Valuasi':return
        nearest=next((label for x,y,label in self.points if abs(x-e.x)<7 and abs(y-e.y)<7),None)
        if nearest:self.status.set(nearest)

if __name__=='__main__':Dashboard().mainloop()
