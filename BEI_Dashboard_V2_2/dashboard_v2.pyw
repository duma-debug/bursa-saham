"""Investor Mandiri BEI Dashboard V2.2 - historical financial statements. Read-only.
Launch: py dashboard_v2.pyw ; Tkinter included with most Python distributions.
"""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import dashboard_core as core
import historical_matrix as hist

NAVY='#142C4A'; BLUE='#28669E'; BG='#EFF4FA'; WHITE='#FFFFFF'; INK='#1C354D'; MUTED='#50677D'
HOME=Path(r'C:\Analisis_Saham_BEI')
if not HOME.exists(): HOME=Path(__file__).resolve().parent.parent

class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('Investor Mandiri | BEI Financial Statements V2.2');self.geometry('1370x800');self.minsize(950,570);self.configure(bg=BG)
  self.db=None;self.records=[];self.periods=[];self.metrics=[];self.chosen={};self.ticker=tk.StringVar(value='AALI');self.mode=tk.StringVar(value='Annual');self.statement=tk.StringVar(value='All');self.quarter_view=tk.StringVar(value='YTD (kumulatif)');self.selection_text=tk.StringVar(value='Pilih sel angka untuk melihat sumbernya. Semua angka REVIEW / belum seragam satuan.')
  st=ttk.Style(self);st.theme_use('clam');st.configure('Treeview',font=('Segoe UI',10),rowheight=29,background=WHITE,fieldbackground=WHITE);st.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background='#D8E7F4',foreground=NAVY);st.configure('TCombobox',font=('Segoe UI',10))
  h=tk.Frame(self,bg=NAVY,padx=18,pady=15);h.pack(fill='x');tk.Label(h,text='INVESTOR MANDIRI  /  FINANCIAL STATEMENTS',font=('Segoe UI',18,'bold'),bg=NAVY,fg=WHITE).pack(anchor='w');tk.Label(h,text='Matriks historis • periode terlama di kiri, terbaru di kanan • data mentah REVIEW',bg=NAVY,fg='#C2D8E8').pack(anchor='w')
  bar=tk.Frame(self,bg=BG,padx=15,pady=12);bar.pack(fill='x')
  tk.Label(bar,text='Emiten',bg=BG,fg=INK).pack(side='left');self.symbol=ttk.Combobox(bar,width=11,textvariable=self.ticker,state='readonly');self.symbol.pack(side='left',padx=8);self.symbol.bind('<<ComboboxSelected>>',lambda e:self.load())
  tk.Label(bar,text='Periode',bg=BG).pack(side='left',padx=(15,4));ttk.Combobox(bar,textvariable=self.mode,state='readonly',values=['Annual','Quarterly','All Periods'],width=11).pack(side='left');self.mode.trace_add('write',lambda *_:self.render())
  tk.Label(bar,text='Quarterly',bg=BG).pack(side='left',padx=(12,4));ttk.Combobox(bar,textvariable=self.quarter_view,state='readonly',values=['YTD (kumulatif)','Standalone'],width=17).pack(side='left');self.quarter_view.trace_add('write',lambda *_:self.render())
  tk.Label(bar,text='Laporan',bg=BG).pack(side='left',padx=(15,4));ttk.Combobox(bar,textvariable=self.statement,state='readonly',values=['All','income_statement','balance_sheet','cash_flow'],width=19).pack(side='left');self.statement.trace_add('write',lambda *_:self.render())
  tk.Button(bar,text='Analisis / Refresh',bg=BLUE,fg=WHITE,bd=0,padx=15,pady=7,command=self.load).pack(side='left',padx=15)
  tk.Button(bar,text='Ekspor Excel/CSV',bg=BLUE,fg=WHITE,bd=0,padx=13,pady=7,command=self.export).pack(side='left',padx=3)
  tk.Button(bar,text='Pilih Database',bg='#526981',fg=WHITE,bd=0,padx=14,pady=7,command=self.pick).pack(side='right')
  self.db_label=tk.Label(self,bg=BG,fg=MUTED,anchor='w',font=('Segoe UI',9));self.db_label.pack(fill='x',padx=18,pady=(0,8))
  self.warn=tk.Label(self,text='REVIEW: FY laba rugi/arus kas hanya dari laporan tahunan; neraca 31 Desember bisa dari kolom pembanding. Sel kosong bukan nol. Kuartal standalone DIBLOKIR sampai satuan dan periode terverifikasi.',bg='#FFF3D9',fg='#754E12',font=('Segoe UI',10,'bold'),anchor='w',padx=12,pady=10,wraplength=1300);self.warn.pack(fill='x',padx=14,pady=(0,10))
  main=tk.Frame(self,bg=WHITE);main.pack(fill='both',expand=True,padx=14,pady=(0,8))
  tk.Label(main,text='AKUN KEUANGAN',bg='#DBE9F5',fg=NAVY,font=('Segoe UI',10,'bold'),anchor='w',padx=13,pady=8).pack(side='top',fill='x')
  body=tk.Frame(main,bg=WHITE);body.pack(fill='both',expand=True)
  self.left=ttk.Treeview(body,columns=('account',),show='headings',selectmode='browse');self.left.heading('account',text='Description (tetap)');self.left.column('account',width=270,stretch=False);self.left.pack(side='left',fill='y')
  right_box=tk.Frame(body,bg=WHITE);right_box.pack(side='left',fill='both',expand=True)
  self.right=ttk.Treeview(right_box,columns=(),show='headings',selectmode='browse');self.right.pack(side='top',fill='both',expand=True)
  hscroll=ttk.Scrollbar(right_box,orient='horizontal',command=self.right.xview);hscroll.pack(side='bottom',fill='x');self.right.configure(xscrollcommand=hscroll.set)
  yscroll=ttk.Scrollbar(body,orient='vertical',command=self._yview);yscroll.pack(side='right',fill='y')
  self.right.configure(yscrollcommand=lambda first,last:self._yscroll(first,last,yscroll,self.left))
  self.left.configure(yscrollcommand=lambda first,last:self._yscroll(first,last,yscroll,self.right))
  for tree in (self.right,self.left):
   tree.bind('<MouseWheel>',self._wheel);tree.bind('<<TreeviewSelect>>',lambda e,t=tree:self._selected(t));tree.bind('<ButtonRelease-1>',lambda e,t=tree:self._clicked(e,t))
  self.detail=tk.Label(self,textvariable=self.selection_text,bg=WHITE,fg=MUTED,anchor='w',justify='left',padx=15,pady=10,wraplength=1300);self.detail.pack(fill='x',padx=14,pady=(0,8))
  self.status=tk.Label(self,text='Siap.',bg=BG,fg=MUTED,anchor='w');self.status.pack(fill='x',padx=18,pady=(0,9))
  try:self.db=core.database_at(HOME);self.activate()
  except Exception as e:self.db_label.config(text=f'Database belum ditemukan — klik Pilih Database. {e}')
 def _yscroll(self,first,last,bar,other):
  bar.set(first,last)
  if abs(other.yview()[0]-float(first))>0.0001:other.yview_moveto(float(first))
 def _yview(self,*args):
  self.left.yview(*args);self.right.yview(*args)
 def _wheel(self,event):
  delta=-1 if event.delta>0 else 1;self.left.yview_scroll(delta,'units');self.right.yview_scroll(delta,'units');return 'break'
 def activate(self):
  self.db_label.config(text='Database read-only: '+str(self.db));tickers=core.available_tickers(self.db);self.symbol['values']=tickers
  if self.ticker.get() not in tickers:self.ticker.set(tickers[0] if tickers else '')
  self.load()
 def pick(self):
  f=filedialog.askopenfilename(title='Pilih BEI_Financial_Master.db',filetypes=[('SQLite Database','*.db'),('All files','*.*')]);
  if f:self.db=Path(f);self.activate()
 def load(self):
  if not self.db:return
  try:self.records=core.get_data(self.db,self.ticker.get());self.render()
  except Exception as e:messagebox.showerror('Gagal membaca database',str(e))
 def render(self):
  if not self.records:return
  if self.mode.get()=='Quarterly' and self.quarter_view.get()=='Standalone':
   self.periods,self.metrics,self.chosen=hist.standalone_view(self.records,self.statement.get())
  else:
   self.periods,self.metrics,self.chosen=hist.build(self.records,'All' if self.mode.get()=='All Periods' else self.mode.get(),self.statement.get());
  for t in (self.left,self.right):
   for item in t.get_children():t.delete(item)
  cols=[f'p{i}' for i in range(len(self.periods))];self.right['columns']=cols
  for name,p in zip(cols,self.periods):
   self.right.heading(name,text=hist.standalone_label(p) if p[1].startswith('S') else hist.label(p));self.right.column(name,width=195,stretch=False,anchor='e',minwidth=165)
  for idx,m in enumerate(self.metrics):
   self.left.insert('', 'end',iid=str(idx),values=(hist.LABELS.get(m,m),))
   vals=[hist.display(self.chosen[(m,p)]['raw_value']) if (m,p) in self.chosen else ('N/A' if hist.cell_status(m,p,self.chosen)[0]=='NOT_APPLICABLE' else 'Belum ada') for p in self.periods]
   self.right.insert('', 'end',iid=str(idx),values=vals)
  self.status.config(text=f'{self.ticker.get()}: {len(self.metrics)} akun × {len(self.periods)} periode | {len(self.chosen)} sel terisi | data REVIEW, tidak untuk valuasi/publikasi.')
  self.selection_text.set('Klik sel untuk sumber atau penyebab kosong. Tahun terbaru paling kanan. N/A = tidak berlaku; Belum ada = tidak ditemukan. Standalone diblokir sampai data tervalidasi.')
  self.update_idletasks();self.right.xview_moveto(1.0)
 def _clicked(self,event,tree):
  if tree is self.right:
   col=tree.identify_column(event.x)
   row=tree.identify_row(event.y)
   try:
    ci=int(col[1:])-1;idx=int(row)
    if ci>=0:self._show_source(self.metrics[idx],self.periods[ci])
   except (ValueError,IndexError):pass
  else:self._selected(tree)
 def _selected(self,tree):
  if tree is self.left:
   ids=self.left.selection();
   if not ids:return
   self.right.selection_set(ids[0]);self.selection_text.set('Klik angka di tabel kanan untuk menelusuri sumber.');return
  ids=self.right.selection()
  if not ids:return
  idx=int(ids[0]);m=self.metrics[idx]
  # Source details depend on clicked cell; handled by column via identify_column in event below.
  p=self.periods[-1] if self.periods else None
  if p:self._show_source(m,p)
 def _show_source(self,m,p):
  r=self.chosen.get((m,p))
  if not r:
   status,reason=hist.cell_status(m,p,self.chosen)
   if p[1].startswith('S'):reason='Perhitungan kuartal standalone memerlukan 2 laporan kumulatif yang terverifikasi periode, mata uang, satuan dan cakupannya. Belum tersedia bukti verifikasi.';status='BLOCKED'
   self.selection_text.set(f'{hist.LABELS.get(m,m)} | {hist.standalone_label(p) if p[1].startswith("S") else hist.label(p)} | {status}: {reason}')
   return
  self.selection_text.set(f"{hist.LABELS.get(m,m)} | {hist.label(p)} | Nilai mentah: {hist.display(r['raw_value'])} | {r.get('currency') or '?'} | Skala laporan: {r.get('presentation_scale') or 'belum tersedia'} | Sumber: {r['filename']} • {r['source_sheet']}!{r['source_cell']} | Alternatif: {r['alternatives']} | REVIEW")
 def export(self):
  if not self.periods:return messagebox.showwarning('Data kosong','Tidak ada periode untuk diekspor.')
  p=HOME/'BEI_Dashboard_Output'/self.ticker.get()/f'{self.ticker.get()}_{self.mode.get().replace(" ","_")}_{self.quarter_view.get().split()[0]}_{self.statement.get()}_REVIEW.csv'
  try:
   if self.mode.get()=='Quarterly' and self.quarter_view.get()=='Standalone':
    messagebox.showwarning('Ekspor diblokir','Kuartal standalone belum boleh dihitung dari fakta yang belum terverifikasi. Pilih YTD dahulu.');return
   hist.export(p,self.periods,self.metrics,self.chosen,self.ticker.get());messagebox.showinfo('Ekspor CSV',f'File dibuat:\n{p}\n\nAngka masih mentah dan berstatus REVIEW.')
  except Exception as e:messagebox.showerror('Gagal ekspor',str(e))

if __name__=='__main__':App().mainloop()
