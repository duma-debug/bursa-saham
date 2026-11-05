#!/usr/bin/env python3
"""GUI lokal, Python tkinter standard library. Tidak mengubah database."""
import csv, re, sqlite3, subprocess, sys, threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
from treemap_sector_ticker import parse_xlsx_sector_map

BASE=Path(__file__).resolve().parent
DB=BASE/'pasar_bei_prototipe.db'
SECTORS=BASE/'Daftar Saham  sektor.xlsx'

class TreemapApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('BEI | Treemap Foreign Flow — Sector → Ticker')
        self.geometry('850x650')
        self.minsize(760,540)
        self.configure(bg='#f3f6fa')
        self.mode=tk.StringVar(value='net')
        self.period=tk.StringVar(value='5')
        self.sector=tk.StringVar(value='Semua Sektor')
        self.end_date=tk.StringVar()
        self.manual=tk.BooleanVar(value=False)
        self.selected=[]
        self.last_svg=None
        self.build_ui()
        self.reload_sources()

    def build_ui(self):
        root=ttk.Frame(self,padding=18)
        root.pack(fill='both',expand=True)
        ttk.Label(root,text='Treemap Foreign Flow BEI',font=('Segoe UI',19,'bold')).pack(anchor='w')
        ttk.Label(root,text='Sector → Ticker  •  Hijau net buy / merah net sell  •  Nilai berbasis volume saham',font=('Segoe UI',10)).pack(anchor='w',pady=(0,18))
        frm=ttk.LabelFrame(root,text='Parameter analisis',padding=13)
        frm.pack(fill='x')
        frm.columnconfigure(1,weight=1)
        frm.columnconfigure(3,weight=1)
        ttk.Label(frm,text='Mode').grid(row=0,column=0,sticky='w',padx=5,pady=8)
        ttk.Combobox(frm,textvariable=self.mode,values=['net','buy','sell'],state='readonly',width=15).grid(row=0,column=1,sticky='ew',padx=5)
        ttk.Label(frm,text='Periode').grid(row=0,column=2,sticky='w',padx=5)
        self.period_box=ttk.Combobox(frm,textvariable=self.period,values=['1','5','10','20'],state='readonly',width=15)
        self.period_box.grid(row=0,column=3,sticky='ew',padx=5)
        self.period_box.bind('<<ComboboxSelected>>',lambda event: self.sync_selection())
        ttk.Label(frm,text='Sektor').grid(row=1,column=0,sticky='w',padx=5,pady=8)
        self.sector_box=ttk.Combobox(frm,textvariable=self.sector,state='readonly',width=40)
        self.sector_box.grid(row=1,column=1,columnspan=3,sticky='ew',padx=5)
        ttk.Label(frm,text='Tanggal akhir').grid(row=2,column=0,sticky='w',padx=5,pady=8)
        self.date_box=ttk.Combobox(frm,textvariable=self.end_date,state='readonly')
        self.date_box.grid(row=2,column=1,sticky='ew',padx=5)
        self.date_box.bind('<<ComboboxSelected>>',lambda event:self.sync_selection())
        ttk.Checkbutton(frm,text='Pilih tanggal bebas',variable=self.manual,command=self.toggle_manual).grid(row=2,column=2,columnspan=2,sticky='w',padx=5)
        dates_frame=ttk.LabelFrame(root,text='Tanggal perdagangan yang tersedia (pilih tepat N dengan Ctrl+klik jika manual)',padding=10)
        dates_frame.pack(fill='both',expand=True,pady=12)
        self.date_list=tk.Listbox(dates_frame,height=10,selectmode='extended',exportselection=False,font=('Consolas',10))
        self.date_list.pack(side='left',fill='both',expand=True)
        sb=ttk.Scrollbar(dates_frame,orient='vertical',command=self.date_list.yview)
        sb.pack(side='right',fill='y')
        self.date_list.configure(yscrollcommand=sb.set)
        self.date_list.bind('<<ListboxSelect>>',lambda e:self.update_selected_caption())
        self.selected_label=ttk.Label(root,text='Tanggal terpilih: —')
        self.selected_label.pack(anchor='w')
        actions=ttk.Frame(root)
        actions.pack(fill='x',pady=14)
        self.run_button=ttk.Button(actions,text='Buat Treemap',command=self.run)
        self.run_button.pack(side='left')
        ttk.Button(actions,text='Buka SVG terakhir',command=self.open_last).pack(side='left',padx=8)
        ttk.Button(actions,text='Muat ulang tanggal',command=self.reload_sources).pack(side='left')
        self.status=tk.StringVar(value='Siap')
        ttk.Label(root,textvariable=self.status,wraplength=790).pack(anchor='w',pady=(3,6))
        self.log=tk.Text(root,height=6,wrap='word',font=('Consolas',9))
        self.log.pack(fill='x')
        self.log.configure(state='disabled')

    def reload_sources(self):
        try:
            if not DB.exists(): raise FileNotFoundError(f'Database tidak ditemukan: {DB}')
            with sqlite3.connect(f'file:{DB.as_posix()}?mode=ro',uri=True) as conn:
                self.dates=[r[0] for r in conn.execute('SELECT DISTINCT trade_date FROM daily ORDER BY trade_date DESC')]
            if not self.dates: raise ValueError('Database belum berisi tanggal perdagangan')
            mapping=parse_xlsx_sector_map(SECTORS)
            sectors=sorted({v for v in mapping.values() if v})
            if not sectors: raise ValueError('Daftar sektor kosong')
            self.sector_box['values']=['Semua Sektor']+sectors
            if self.sector.get() not in self.sector_box['values']: self.sector.set('Semua Sektor')
            self.date_box['values']=self.dates
            if self.end_date.get() not in self.dates: self.end_date.set(self.dates[0])
            self.date_list.delete(0,'end')
            for d in self.dates: self.date_list.insert('end',d)
            self.toggle_manual()
            self.status.set(f'{len(self.dates)} tanggal tersedia. Sumber: {DB.name}')
        except Exception as e:
            messagebox.showerror('Gagal membaca sumber',str(e))

    def toggle_manual(self):
        ismanual=self.manual.get()
        self.date_box.configure(state='disabled' if ismanual else 'readonly')
        self.date_list.configure(state='normal' if ismanual else 'disabled')
        self.sync_selection()

    def sync_selection(self):
        if not hasattr(self,'dates'): return
        self.date_list.selection_clear(0,'end')
        n=int(self.period.get())
        if not self.manual.get():
            d=self.end_date.get()
            if d in self.dates:
                pos=self.dates.index(d)
                vals=self.dates[pos:pos+n]
                for k in range(pos,min(pos+n,len(self.dates))): self.date_list.selection_set(k)
                self.selected=sorted(vals)
        else:
            self.selected=[]
        self.update_selected_caption()

    def update_selected_caption(self):
        if self.manual.get():
            selected=[self.dates[i] for i in self.date_list.curselection()]
            self.selected=sorted(selected)
        dates=', '.join(self.selected) if self.selected else 'belum dipilih'
        self.selected_label.configure(text=f'{len(self.selected)}/{self.period.get()} tanggal: {dates}')

    def log_msg(self,txt):
        self.log.configure(state='normal')
        self.log.insert('end',txt+'\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def run(self):
        n=int(self.period.get())
        if len(self.selected)!=n:
            messagebox.showwarning('Tanggal belum lengkap',f'Pilih tepat {n} tanggal. Sekarang: {len(self.selected)}')
            return
        sector=self.sector.get()
        safe_sector=re.sub(r'[^A-Za-z0-9_-]+','_',sector).strip('_')
        dir_out=BASE/'output_treemap'/(safe_sector if sector!='Semua Sektor' else 'Semua_Sektor')
        dir_out=dir_out/('Tanggal_'+self.selected[-1] if not self.manual.get() else 'Pilihan_'+self.selected[0]+'_'+self.selected[-1])
        cmd=[sys.executable,str(BASE/'treemap_sector_ticker.py'),'--db',str(DB),'--sector-file',str(SECTORS),'--output',str(dir_out),'--mode',self.mode.get(),'--period',str(n),'--sector',sector,'--dates',','.join(self.selected)]
        self.run_button.configure(state='disabled')
        self.status.set('Memproses...')
        self.log_msg('Menjalankan treemap: '+', '.join(self.selected))
        suffix={'net':'Net','buy':'Buy','sell':'Sell'}[self.mode.get()]
        svg=dir_out/f'Treemap_Sector_Ticker_Foreign_{suffix}_{n}D.svg'
        threading.Thread(target=self.worker,args=(cmd,svg),daemon=True).start()

    def worker(self,cmd,svg):
        try:
            proc=subprocess.run(cmd,cwd=str(BASE),capture_output=True,text=True,encoding='utf-8',errors='replace')
            output=(proc.stdout+'\n'+proc.stderr).strip()
            self.after(0,lambda:self.finish(proc.returncode,output,svg))
        except Exception as exc:
            self.after(0,lambda e=str(exc):self.finish(1,e,None))

    def finish(self,code,output,svg):
        self.run_button.configure(state='normal')
        self.log_msg(output)
        if code==0:
            self.last_svg=svg
            self.status.set('BERHASIL — hasil: '+str(svg))
        else:
            self.status.set('GAGAL — lihat pesan di bawah')
            messagebox.showerror('Treemap gagal',output[-1500:])

    def open_last(self):
        import os
        if not self.last_svg or not self.last_svg.exists():
            messagebox.showinfo('Belum ada file','Buat treemap terlebih dahulu.')
            return
        os.startfile(str(self.last_svg))

if __name__=='__main__':
    TreemapApp().mainloop()
