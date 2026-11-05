import tkinter as tk
from tkinter import ttk,messagebox
from pathlib import Path
from datetime import date
import subprocess,sys
from . import __version__
from .data import market_summary,latest_prices
from .decisions import save_research,save_transaction,positions,research_rows,transaction_rows
from .accounting import calculate_portfolio,add_dividend
from .cash import add_cash_event,cash_events,cash_reconcile,update_cash_event,delete_cash_event
from .market import MarketModule
from .theme import apply_theme,load_mode,save_mode,P

ROOT=Path(__file__).resolve().parent.parent
DB=ROOT/'pasar_bei_prototipe.db'
WORK=ROOT/'investment_workpapers.db'
NAVY='#0D2247'; BLUE='#1E73D8'


def group_rupiah(value):
    """Format typed rupiah using comma groups, preserving optional decimal part."""
    raw=str(value).replace(',', '').strip()
    if raw in ('','-','+'): return raw
    if raw.count('.')>1 or any(c not in '0123456789.-+' for c in raw):
        return str(value)
    sign=''
    if raw[0] in '+-': sign,raw=raw[0],raw[1:]
    if not raw: return sign
    whole,dot,frac=raw.partition('.')
    if not whole: whole='0'
    if not whole.isdigit() or (dot and not frac.isdigit() and frac!=''): return str(value)
    return sign+f'{int(whole):,}'+('.'+frac if dot else '')

def bind_money_entry(widget):
    """Reformat live and keep caret close to logical digit position."""
    def refresh(_event=None):
        try:
            current=widget.get(); desired=group_rupiah(current)
            if current==desired:return
            old_cursor=widget.index(tk.INSERT)
            raw_before=sum(ch!=',' for ch in current[:old_cursor])
            new_cursor=0; seen=0
            while new_cursor<len(desired) and seen<raw_before:
                if desired[new_cursor]!=',': seen+=1
                new_cursor+=1
            widget.delete(0,tk.END);widget.insert(0,desired)
            widget.icursor(new_cursor)
        except tk.TclError:
            pass
    widget.bind('<KeyRelease>',refresh,add='+')
    widget.bind('<FocusOut>',refresh,add='+')
    widget.bind('<<Paste>>',lambda _e:widget.after_idle(refresh),add='+')
    return widget

class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('BEI Equity Analytics | Unified Platform — Phase 1.3');self.geometry('1200x800');self.minsize(760,520)
  self.theme_mode=tk.StringVar(value=load_mode(self))
  apply_theme(self,self.theme_mode.get())
  header=ttk.Frame(self);header.pack(fill='x',padx=18,pady=(12,4))
  ttk.Label(header,text='BEI Equity Analytics — Unified Platform',style='Title.TLabel').pack(side='left')
  self.theme_button=ttk.Button(header,text='☾ Dark Mode' if self.theme_mode.get()=='light' else '☀ Light Mode',command=self.toggle_theme)
  self.theme_button.pack(side='right')
  self._add_brand(header)
  ttk.Label(self,text='Phase 1 foundation | Market database read-only | Research & portfolio in separate database').pack(anchor='w',padx=18)
  self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=10,pady=(8,3))
  self.size_status=ttk.Label(self,text='Geser pembatas panel untuk mengubah ukurannya. Perbesar jendela atau gunakan scroll untuk tabel.',anchor='w');self.size_status.pack(fill='x',padx=12,pady=(0,5))
  self.market_view=ttk.Frame(self.tabs);self.market=ttk.Frame(self.tabs,padding=12);self.research=ttk.Frame(self.tabs,padding=12);self.portfolio=ttk.Frame(self.tabs,padding=12);self.legacy=ttk.Frame(self.tabs,padding=12);self.cash_tab=ttk.Frame(self.tabs,padding=12)
  for frm,name in [(self.market_view,'Market Intelligence'),(self.market,'Data Health'),(self.research,'Research Workpaper'),(self.portfolio,'Portfolio Journal'),(self.cash_tab,'Cash & Performance'),(self.legacy,'Dashboard Legacy')]:self.tabs.add(frm,text=name)
  self._market_ui();self._research_ui();self._portfolio_ui();self._cash_ui();self._legacy_ui();self.refresh_market();self._integrate_market()
  apply_theme(self,self.theme_mode.get())
 def _add_brand(self,header):
  logo=ROOT/'logos'/'Investor Mandiri.png'
  if logo.is_file():
   try:
    from PIL import Image,ImageTk
    im=Image.open(logo).convert('RGBA');im.thumbnail((140,40))
    self._brand_image=ImageTk.PhotoImage(im)
    ttk.Label(header,image=self._brand_image).pack(side='right',padx=(0,14))
    return
   except (ImportError,OSError,ValueError):pass
  ttk.Label(header,text='Investor Mandiri').pack(side='right',padx=(0,14))
 def toggle_theme(self):
  mode='dark' if self.theme_mode.get()=='light' else 'light'
  self.theme_mode.set(mode)
  apply_theme(self,mode)
  self.theme_button.configure(text='☀ Light Mode' if mode=='dark' else '☾ Dark Mode')
  save_mode(self,mode)
 def _integrate_market(self):
  try:
   self.market_module=MarketModule(self.market_view,on_research=self.research_from_market)
   self.market_module.pack(fill='both',expand=True)
   link=ttk.Frame(self.market_module.detail)
   link.pack(fill='x',padx=10,pady=3)
   ttk.Button(link,text='Buat Research Workpaper untuk saham ini',command=self.research_from_market).pack(side='left')
  except Exception as exc:
   ttk.Label(self.market_view,text='Market Intelligence gagal dimuat: '+str(exc),foreground='#D84C4C',wraplength=700).pack(padx=15,pady=15)
 def research_from_market(self):
  ticker=getattr(getattr(self,'market_module',None),'selected_ticker','')
  if ticker:self.rt.set(ticker)
  if getattr(self,'market_module',None):
   current=self.market_module.date.get()
   if current:self.rd.set(current)
  self.tabs.select(self.research)
 def _market_ui(self):
  ttk.Label(self.market,text='Status database pasar (read-only)',font=('Segoe UI',13,'bold')).pack(anchor='w')
  ttk.Label(self.market,text=f'Lokasi: {DB}').pack(anchor='w',pady=4)
  ttk.Button(self.market,text='Periksa Ulang',command=self.refresh_market).pack(anchor='w',pady=5)
  self.market_info=tk.Text(self.market,height=15,font=('Consolas',11));self.market_info.pack(fill='both',expand=True)
 def refresh_market(self):
  try:
   x=market_summary(DB);info=(f"Integritas: {x['integrity']} | Duplikat tanggal/ticker: {x['duplicate']}\nSesi: {x['sessions']:,} | Rekaman: {x['records']:,} | Saham unik: {x['tickers']}\nRentang: {x['first']} — {x['latest']}\nTicker fundamental ({len(x['fundamentals'])}): {', '.join(x['fundamentals'])}\n\n"
    'Catatan: indeks berbasis kapitalisasi bukan IHSG resmi; foreign volume bukan nilai rupiah.\n'
    'Keterangan: database ini tidak dimodifikasi oleh aplikasi Phase 1.')
  except Exception as e:info='GAGAL: '+str(e)
  self.market_info.delete('1.0','end');self.market_info.insert('1.0',info)
 def _table_with_bars(self,parent,columns,labels,widths,height=7):
  frame=ttk.Frame(parent)
  frame.pack(fill='both',expand=True)
  tree=ttk.Treeview(frame,columns=columns,show='headings',height=height)
  for key,label,w in zip(columns,labels,widths):
   tree.heading(key,text=label)
   tree.column(key,width=w,minwidth=65,stretch=False,anchor='w')
  v=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
  h=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
  tree.configure(yscrollcommand=v.set,xscrollcommand=h.set)
  tree.grid(row=0,column=0,sticky='nsew');v.grid(row=0,column=1,sticky='ns');h.grid(row=1,column=0,sticky='ew')
  frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
  return tree
 def _research_ui(self):
  panes=ttk.PanedWindow(self.research,orient='vertical')
  panes.pack(fill='both',expand=True)
  upper=ttk.Frame(panes,padding=5);lower=ttk.Frame(panes,padding=5)
  panes.add(upper,weight=3);panes.add(lower,weight=2)
  upper.columnconfigure(0,weight=1);upper.rowconfigure(1,weight=1)
  f=ttk.Frame(upper);f.grid(row=0,column=0,sticky='ew')
  self.rt=tk.StringVar();self.rd=tk.StringVar(value=str(date.today()));self.rdec=tk.StringVar(value='REVIEW');self.rfair=tk.StringVar()
  for i,(lab,var) in enumerate([('Ticker',self.rt),('As-of (YYYY-MM-DD)',self.rd),('Fair value (Rp, opsional)',self.rfair)]):
   ttk.Label(f,text=lab).grid(row=i,column=0,sticky='w',padx=(0,12),pady=3)
   bind_money_entry(ttk.Entry(f,textvariable=var,width=30)).grid(row=i,column=1,sticky='ew',pady=3) if var is self.rfair else ttk.Entry(f,textvariable=var,width=30).grid(row=i,column=1,sticky='ew',pady=3)
  f.columnconfigure(1,weight=1)
  ttk.Label(f,text='Rekomendasi analis').grid(row=3,column=0,sticky='w')
  ttk.Combobox(f,textvariable=self.rdec,values=['REVIEW','BUY','HOLD','REDUCE','SELL'],state='readonly',width=20).grid(row=3,column=1,sticky='w')
  fields=ttk.Frame(upper);fields.grid(row=1,column=0,sticky='nsew',pady=(5,0))
  fields.columnconfigure(0,weight=1)
  for i in range(3):fields.rowconfigure(i,weight=1)
  self.entries={}
  for i,name in enumerate(['Investment thesis','Risks','Catalysts']):
   section=ttk.Frame(fields);section.grid(row=i,column=0,sticky='nsew',pady=2)
   section.columnconfigure(0,weight=1);section.rowconfigure(1,weight=1)
   ttk.Label(section,text=name).grid(row=0,column=0,sticky='w')
   txt=tk.Text(section,height=2,wrap='word');txt.grid(row=1,column=0,sticky='nsew')
   sb=ttk.Scrollbar(section,orient='vertical',command=txt.yview);sb.grid(row=1,column=1,sticky='ns');txt.configure(yscrollcommand=sb.set)
   self.entries[name]=txt
  ttk.Button(upper,text='Simpan versi kertas kerja',command=self.save_research_ui).grid(row=2,column=0,sticky='w',pady=5)
  ttk.Label(lower,text='Riwayat (tidak ditimpa saat revisi) — tarik pembatas untuk memperbesar tabel').pack(anchor='w')
  self.rtree=self._table_with_bars(lower,('id','ticker','date','decision','fair','saved'),('ID','Ticker','Tanggal','Keputusan','Fair Value','Disimpan'),(80,120,135,130,130,230))
  self.refresh_research()
 def save_research_ui(self):
  try:
   v=float(self.rfair.get().replace(',','')) if self.rfair.get().strip() else None
   save_research(WORK,self.rt.get(),self.rd.get(),self.rdec.get(),v,*(self.entries[k].get('1.0','end').strip() for k in ('Investment thesis','Risks','Catalysts')))
   self.refresh_research();messagebox.showinfo('Tersimpan','Versi research baru tersimpan dalam investment_workpapers.db')
  except Exception as e:messagebox.showerror('Validasi',str(e))
 def refresh_research(self):
  for row in self.rtree.get_children():self.rtree.delete(row)
  for r in research_rows(WORK):self.rtree.insert('','end',values=tuple(r))
 def _portfolio_ui(self):
  outer=ttk.PanedWindow(self.portfolio,orient='vertical');outer.pack(fill='both',expand=True)
  form_wrap=ttk.Frame(outer,padding=5);tables=ttk.Frame(outer,padding=5)
  outer.add(form_wrap,weight=2);outer.add(tables,weight=3)
  frm=ttk.Frame(form_wrap);frm.pack(fill='x')
  frm.columnconfigure(1,weight=1)
  self.pt=tk.StringVar();self.pdate=tk.StringVar(value=str(date.today()));self.pside=tk.StringVar(value='BUY');self.plots=tk.StringVar();self.pprice=tk.StringVar();self.pfee=tk.StringVar(value='0');self.pnotes=tk.StringVar()
  for i,(label,var) in enumerate([('Tanggal (YYYY-MM-DD)',self.pdate),('Ticker',self.pt),('Side',self.pside),('Lots',self.plots),('Harga per saham (Rp)',self.pprice),('Fee total (Rp)',self.pfee),('Catatan',self.pnotes)]):
   ttk.Label(frm,text=label).grid(row=i,column=0,sticky='w',padx=(0,12),pady=3)
   if label=='Side':ttk.Combobox(frm,textvariable=var,values=['BUY','SELL'],state='readonly',width=24).grid(row=i,column=1,sticky='w')
   else:
    entry=ttk.Entry(frm,textvariable=var,width=30)
    if var in (self.pprice,self.pfee):bind_money_entry(entry)
    entry.grid(row=i,column=1,sticky='ew')
  ttk.Button(frm,text='Catat transaksi',command=self.save_portfolio_ui).grid(row=7,column=0,columnspan=2,sticky='w',pady=5)
  split=ttk.PanedWindow(tables,orient='vertical');split.pack(fill='both',expand=True)
  hold_frame=ttk.Frame(split);trade_frame=ttk.Frame(split)
  split.add(hold_frame,weight=1);split.add(trade_frame,weight=1)
  ttk.Label(hold_frame,text='Posisi tercatat — harga terbaru indikatif',font=('Segoe UI',10,'bold')).pack(anchor='w')
  self.hold=self._table_with_bars(hold_frame,('ticker','lots','avg','cost','price','value','weight','unrl','ret'),('Ticker','Lot','Avg cost Rp','Cost basis Rp','Close Rp','Market value Rp','Bobot %','Unrealized P/L Rp','Return %'),(90,65,125,145,105,145,95,160,90))
  ttk.Label(trade_frame,text='Riwayat transaksi — tarik pembatas untuk memperbesar').pack(anchor='w')
  self.trades=self._table_with_bars(trade_frame,('date','ticker','side','lots','price','fee'),('Tanggal','Ticker','BUY/SELL','Lot','Harga','Fee'),(145,135,95,95,140,140))
  self.portfolio_summary=tk.StringVar(value='')
  ttk.Label(self.portfolio,textvariable=self.portfolio_summary,wraplength=1200).pack(anchor='w',pady=3)
  div=ttk.Frame(self.portfolio);div.pack(fill='x',pady=2)
  self.div_date=tk.StringVar(value=str(date.today()));self.div_ticker=tk.StringVar();self.div_amount=tk.StringVar()
  for lab,var,width in [('Dividen dibayar',self.div_date,13),('Ticker',self.div_ticker,8),('Dividen bersih diterima Rp',self.div_amount,18)]:
   ttk.Label(div,text=lab).pack(side='left',padx=(5,2))
   entry=ttk.Entry(div,textvariable=var,width=width)
   if var is self.div_amount:bind_money_entry(entry)
   entry.pack(side='left')
  ttk.Button(div,text='Catat Dividen',command=self.save_dividend_ui).pack(side='left',padx=8)
  self.refresh_portfolio()
 def save_portfolio_ui(self):
  try:
   save_transaction(WORK,self.pdate.get(),self.pt.get(),self.pside.get(),int(self.plots.get()),float(self.pprice.get().replace(',','')),float(self.pfee.get().replace(',','') or 0),self.pnotes.get())
   self.refresh_portfolio();self.refresh_cash();messagebox.showinfo('Tersimpan','Transaksi tercatat')
  except Exception as e:messagebox.showerror('Validasi',str(e))
 def refresh_portfolio(self):
  for tv in (self.hold,self.trades):
   for i in tv.get_children():tv.delete(i)
  try:dt,prices=latest_prices(DB)
  except Exception:prices={}
  positions_out,totals,rejected=calculate_portfolio(WORK,prices)
  for p in positions_out:
   money=lambda x:f'{x:,.2f}' if x is not None else 'N/A'
   self.hold.insert('','end',values=(p['ticker'],f"{p['lots']:g}",money(p['avg_cost']),money(p['cost']),money(p['close']),money(p['value']),money(100*p['value']/totals['market_value'] if p['value'] is not None and totals['market_value'] else None),money(p['unrealized']),money(p['return_pct'])))
  for r in transaction_rows(WORK):self.trades.insert('','end',values=tuple(r))
  if hasattr(self,'portfolio_summary'):
   note=(' | PERINGATAN: transaksi tidak konsisten: '+str(len(rejected)) if rejected else '')
   note+=(' | Harga N/A: '+str(totals['missing_prices'])+' saham' if totals['missing_prices'] else '')
   self.portfolio_summary.set(f"Portfolio | Cost Rp{totals['cost']:,.2f} | Market Value Rp{totals['market_value']:,.2f} | Realized Rp{totals['realized']:,.2f} | Unrealized Rp{totals['unrealized']:,.2f} | Dividen Rp{totals['dividends']:,.2f} | Total P/L: "+(f"Rp{totals['total_pl']:,.2f}" if totals['total_pl'] is not None else 'N/A')+note)
 def save_dividend_ui(self):
  try:
   add_dividend(WORK,self.div_date.get(),self.div_ticker.get(),float(self.div_amount.get().replace(',','')))
   self.refresh_portfolio();self.refresh_cash();messagebox.showinfo('Tersimpan','Dividen tercatat')
  except Exception as e:messagebox.showerror('Validasi dividen',str(e))
 def _cash_ui(self):
  controls=ttk.LabelFrame(self.cash_tab,text='Setoran / penarikan dana (arus kas eksternal)',padding=8)
  controls.pack(fill='x')
  self.cash_date=tk.StringVar(value=str(date.today()))
  self.cash_kind=tk.StringVar(value='DEPOSIT')
  self.cash_amount=tk.StringVar()
  self.cash_notes=tk.StringVar()
  controls.columnconfigure(1,weight=1)
  for idx,(caption,var) in enumerate((('Tanggal (YYYY-MM-DD)',self.cash_date),('Jenis',self.cash_kind),('Jumlah Rp',self.cash_amount),('Catatan',self.cash_notes))):
   ttk.Label(controls,text=caption).grid(row=idx,column=0,sticky='w',padx=5,pady=3)
   if idx==1:widget=ttk.Combobox(controls,textvariable=var,values=['DEPOSIT','WITHDRAW'],state='readonly',width=18)
   else:
    widget=ttk.Entry(controls,textvariable=var)
    if var is self.cash_amount:bind_money_entry(widget)
   widget.grid(row=idx,column=1,sticky='ew',padx=5,pady=3)
  ttk.Button(controls,text='Catat setoran / penarikan',command=self.save_cash_ui).grid(row=4,column=0,columnspan=2,sticky='w',padx=5,pady=5)
  actions=ttk.Frame(controls);actions.grid(row=5,column=0,columnspan=2,sticky='ew',padx=5,pady=4)
  ttk.Button(actions,text='Muat pilihan untuk edit',command=self.load_cash_selection).pack(side='left',padx=(0,6))
  ttk.Button(actions,text='Simpan perubahan',command=self.edit_cash_ui).pack(side='left',padx=6)
  ttk.Button(actions,text='Hapus pilihan',command=self.delete_cash_ui).pack(side='left',padx=6)
  ttk.Button(actions,text='Batal edit',command=self.clear_cash_edit).pack(side='left',padx=6)
  ttk.Button(controls,text='Hitung ulang',command=self.refresh_cash).grid(row=4,column=1,sticky='e',padx=5,pady=5)
  self.cash_edit_id=None
  self.cash_edit_status=tk.StringVar(value='Pilih baris riwayat lalu klik Muat pilihan untuk edit. BUY/SELL tidak dapat diubah di sini.')
  ttk.Label(controls,textvariable=self.cash_edit_status,foreground='#436078').grid(row=6,column=0,columnspan=2,sticky='w',padx=5,pady=3)
  self.cash_summary=tk.StringVar(value='')
  ttk.Label(self.cash_tab,textvariable=self.cash_summary,wraplength=1100,justify='left').pack(fill='x',pady=(8,5))
  panes=ttk.PanedWindow(self.cash_tab,orient='vertical');panes.pack(fill='both',expand=True)
  ledger_frame=ttk.Frame(panes);flow_frame=ttk.Frame(panes)
  panes.add(ledger_frame,weight=2);panes.add(flow_frame,weight=1)
  ttk.Label(ledger_frame,text='Riwayat setoran / penarikan (hanya arus kas eksternal)').pack(anchor='w')
  self.cash_tree=self._table_with_bars(ledger_frame,('date','type','amount','note','id'),('Tanggal','Jenis','Jumlah Rp','Catatan','ID'),(140,120,160,460,75),height=7)
  self.cash_tree.bind('<Double-1>',lambda _evt:self.load_cash_selection())
  ttk.Label(flow_frame,text='Rekonsiliasi semua arus kas: setoran, penarikan, BUY, SELL, dividen').pack(anchor='w')
  self.flow_tree=self._table_with_bars(flow_frame,('date','source','amount'),('Tanggal','Jenis arus kas','Dampak pada kas Rp'),(145,160,185),height=5)
  ttk.Label(self.cash_tab,text='Saldo dan NAV indikatif; harga terakhir tersedia di database, bukan realtime. Return TWR/XIRR belum dihitung.',foreground='#436078').pack(anchor='w',pady=4)
  self.refresh_cash()
 def save_cash_ui(self):
  try:
   add_cash_event(WORK,self.cash_date.get().strip(),self.cash_kind.get(),float(self.cash_amount.get().strip().replace(',','')),self.cash_notes.get().strip())
   self.cash_amount.set('');self.cash_notes.set('');self.cash_edit_id=None
   self.refresh_cash()
   messagebox.showinfo('Tersimpan','Perubahan kas tersimpan dalam investment_workpapers.db')
  except Exception as exc:messagebox.showerror('Validasi transaksi kas',str(exc))
 def _selected_cash(self):
  selected=self.cash_tree.selection()
  if not selected:raise ValueError('Pilih satu baris setoran/penarikan pada tabel riwayat.')
  vals=self.cash_tree.item(selected[0],'values')
  if len(vals)<5:raise ValueError('ID transaksi tidak tersedia. Hitung ulang tabel.')
  return int(vals[4])
 def load_cash_selection(self):
  try:
   event_id=self._selected_cash()
   record=next((tuple(r) for r in cash_events(WORK) if int(r[4])==event_id),None)
   if record is None:raise ValueError('Transaksi sudah tidak ditemukan; klik Hitung ulang.')
   dt,kind,amount,notes,_=record
   self.cash_edit_id=event_id
   self.cash_date.set(dt);self.cash_kind.set(kind);self.cash_amount.set(group_rupiah(str(amount)));self.cash_notes.set(notes)
   self.cash_edit_status.set(f'Mengedit transaksi ID {event_id}. Simpan perubahan atau Batal edit.')
  except Exception as exc:messagebox.showerror('Pilih transaksi',str(exc))
 def clear_cash_edit(self):
  self.cash_edit_id=None;self.cash_amount.set('');self.cash_notes.set('')
  self.cash_edit_status.set('Mode input baru. Pilih baris untuk edit/hapus.')
 def edit_cash_ui(self):
  try:
   if self.cash_edit_id is None:raise ValueError('Muat pilihan untuk edit terlebih dahulu.')
   ident=self.cash_edit_id
   record=next((tuple(r) for r in cash_events(WORK) if int(r[4])==ident),None)
   if record is None:raise ValueError('Transaksi tidak ditemukan.')
   if not messagebox.askyesno('Konfirmasi perubahan',f'Ubah transaksi kas ID {ident} ({record[1]} Rp{record[2]:,.2f})?'):
    return
   backup=update_cash_event(WORK,ident,self.cash_date.get().strip(),self.cash_kind.get(),self.cash_amount.get().strip().replace(',',''),self.cash_notes.get().strip())
   self.clear_cash_edit();self.refresh_cash()
   messagebox.showinfo('Berhasil',f'Transaksi kas diubah.\nBackup: {backup}')
  except Exception as exc:messagebox.showerror('Edit transaksi kas',str(exc))
 def delete_cash_ui(self):
  try:
   ident=self._selected_cash()
   record=next((tuple(r) for r in cash_events(WORK) if int(r[4])==ident),None)
   if record is None:raise ValueError('Transaksi tidak ditemukan.')
   dt,kind,amount,notes,_=record
   if not messagebox.askyesno('Konfirmasi HAPUS',f'Hapus transaksi kas ID {ident}?\n{dt} | {kind} | Rp{amount:,.2f}\n\nSaldo kas dan NAV akan dihitung ulang. BUY/SELL tidak diubah.',icon='warning'):
    return
   backup=delete_cash_event(WORK,ident)
   self.clear_cash_edit();self.refresh_cash()
   messagebox.showinfo('Berhasil',f'Transaksi kas dihapus dan dicatat dalam audit log.\nBackup: {backup}')
  except Exception as exc:messagebox.showerror('Hapus transaksi kas',str(exc))
 def refresh_cash(self):
  if not hasattr(self,'cash_tree'):return
  for tv in (self.cash_tree,self.flow_tree):
   for key in tv.get_children():tv.delete(key)
  try:
   _,prices=latest_prices(DB)
   report=cash_reconcile(WORK,prices)
   fmt=lambda x: 'N/A' if x is None else f'Rp{x:,.2f}'
   self.cash_summary.set(' | '.join((
    'Saldo kas: '+fmt(report['cash']),
    'Nilai saham: '+fmt(report['invested']),
    'NAV indikatif: '+fmt(report['equity']),
    'Setoran: '+fmt(report['deposits']),
    'Penarikan: '+fmt(report['withdrawals']),
    'P/L sejak awal (nominal): '+fmt(report['pl']))))
   for rec in cash_events(WORK):
    dt,kind,amount,notes,ident=tuple(rec)
    self.cash_tree.insert('','end',values=(dt,kind,fmt(amount),notes,ident))
   for dt,_,kind,amount in reversed(report['events']):
    self.flow_tree.insert('','end',values=(dt,kind,fmt(amount)))
   warnings=[]
   if report['minimum_cash']<0:warnings.append('Saldo kas pernah negatif: periksa setoran awal dan urutan transaksi.')
   if report['totals']['missing_prices']:warnings.append('Ada posisi tanpa harga pasar; NAV tidak lengkap.')
   if report['rejected']:warnings.append('Ada transaksi posisi tidak konsisten.')
   if warnings:self.cash_summary.set(self.cash_summary.get()+'\nPERINGATAN: '+' '.join(warnings))
  except Exception as exc:
   self.cash_summary.set('Gagal menghitung kas: '+str(exc))
 def _legacy_ui(self):
  ttk.Label(self.legacy,text='Kompatibilitas selama migrasi: buka aplikasi lama di jendela terpisah',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,12))
  scripts=[('Instagram Studio V2.7','bei_equity_v2_7.py'),('Mispricing V2.6','bei_equity_v2_6.py'),('Screener V2.5','bei_equity_screener_v2_5.py'),('Market V2.3.3','bei_equity_v2_3_3.py')]
  for label,script in scripts:
   ttk.Button(self.legacy,text=label,command=lambda s=script:self.open_legacy(s)).pack(anchor='w',pady=4)
  ttk.Label(self.legacy,text='Aplikasi legacy belum digabung menjadi tab native. Ini fondasi transisi Phase 1, bukan rilis final V2.8.').pack(anchor='w',pady=16)
 def open_legacy(self,script):
  p=ROOT/script
  if not p.exists():messagebox.showerror('Tidak tersedia',f'File legacy belum ada di: {p}');return
  subprocess.Popen([sys.executable,str(p)],cwd=str(ROOT))

def main():App().mainloop()
