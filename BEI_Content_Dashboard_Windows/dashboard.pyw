"""Local Windows GUI for BEI Content Research. Python 3.10+, Tkinter; matplotlib optional for PNG."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import dashboard_core as core

NAVY='#142C4A'; BLUE='#2C68A4'; LIGHT='#EFF5FA'; WHITE='#FFFFFF'; TEXT='#1A314B'; MUTED='#61768A'; ORANGE='#9B5900'
BASE=Path(__file__).resolve().parent.parent
if not (BASE/'financial_modeling_v4_1.db').exists() and not (BASE/'BEI_Master_Output').exists():
    BASE=Path(__file__).resolve().parent

class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('BEI Content Dashboard | Investor Mandiri')
        self.geometry('1200x780');self.minsize(960,620)
        self.configure(bg=LIGHT)
        self.db=None;self.records=[];self.pairs=[];self.latest=None;self.ticker='AALI';self.filtered=[]
        self._style();self._ui();self._find_db()
    def _style(self):
        s=ttk.Style(self);s.theme_use('clam')
        s.configure('TNotebook',background=LIGHT,borderwidth=0)
        s.configure('TNotebook.Tab',font=('Segoe UI',10,'bold'),padding=(15,10),background='#DEE8F2',foreground=NAVY)
        s.map('TNotebook.Tab',background=[('selected',WHITE)])
        s.configure('Treeview',font=('Segoe UI',10),rowheight=28,background=WHITE,fieldbackground=WHITE,foreground=TEXT)
        s.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background='#E2ECF5',foreground=NAVY)
        s.configure('TCombobox',font=('Segoe UI',11))
    def _label(self,parent,text,fontsize=10,color=TEXT,bold=False,**kw):
        return tk.Label(parent,text=text,font=('Segoe UI',fontsize,'bold' if bold else 'normal'),fg=color,bg=parent['bg'],**kw)
    def _button(self,parent,text,command,bg=BLUE):
        return tk.Button(parent,text=text,command=command,font=('Segoe UI',10,'bold'),bg=bg,fg=WHITE,
            activebackground=NAVY,activeforeground=WHITE,bd=0,padx=15,pady=9,cursor='hand2')
    def _ui(self):
        head=tk.Frame(self,bg=NAVY,padx=24,pady=16);head.pack(fill='x')
        tk.Label(head,text='INVESTOR MANDIRI  /  BEI CONTENT DASHBOARD',bg=NAVY,fg=WHITE,font=('Segoe UI',17,'bold')).pack(anchor='w')
        tk.Label(head,text='Data → analisis awal → artikel → grafik Instagram  |  Semua hasil REVIEW sampai diverifikasi',bg=NAVY,fg='#BDD2E6',font=('Segoe UI',10)).pack(anchor='w')
        top=tk.Frame(self,bg=LIGHT,padx=22,pady=12);top.pack(fill='x')
        self._label(top,'Ticker',11,bold=True).pack(side='left',padx=(0,9))
        self.ticker_var=tk.StringVar(value='AALI')
        self.symbol=ttk.Combobox(top,textvariable=self.ticker_var,width=13);self.symbol.pack(side='left',padx=(0,9))
        self.symbol.bind('<Return>',lambda e:self.load())
        self._button(top,'Analisis',self.load).pack(side='left',padx=4)
        self._button(top,'Grafik PNG',self.export_png).pack(side='left',padx=4)
        self._button(top,'Artikel .md',self.export_article).pack(side='left',padx=4)
        self._button(top,'Data .csv',self.export_data).pack(side='left',padx=4)
        self._button(top,'Pilih Database',self.pick_db,bg='#61768A').pack(side='right',padx=4)
        self.db_label=self._label(self,'Database: mencari...',9,MUTED)
        self.db_label.pack(anchor='w',padx=22,pady=(0,9))
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=20,pady=(0,12))
        self.tab_summary=tk.Frame(self.tabs,bg=WHITE);self.tab_data=tk.Frame(self.tabs,bg=WHITE)
        self.tab_article=tk.Frame(self.tabs,bg=WHITE);self.tab_source=tk.Frame(self.tabs,bg=WHITE)
        for t,name in [(self.tab_summary,'Ringkasan & Grafik'),(self.tab_data,'Perbandingan YoY'),(self.tab_article,'Draf Artikel'),(self.tab_source,'Jejak Sumber')]:self.tabs.add(t,text=name)
        self._summary_ui();self._data_ui();self._article_ui();self._sources_ui()
        footer=tk.Frame(self,bg=LIGHT,pady=8);footer.pack(fill='x')
        self.status=self._label(footer,'Siap.',10,MUTED);self.status.pack(side='left',padx=22)
        self._label(footer,'DATA REVIEW • bukan rekomendasi investasi',9,ORANGE,bold=True).pack(side='right',padx=22)
    def _summary_ui(self):
        self.title_card=self._label(self.tab_summary,'Ringkasan belum dimuat',18,NAVY,bold=True)
        self.title_card.pack(anchor='w',padx=18,pady=(17,4))
        self.info_card=self._label(self.tab_summary,'',10,MUTED);self.info_card.pack(anchor='w',padx=18)
        self.fig_area=tk.Frame(self.tab_summary,bg=WHITE);self.fig_area.pack(fill='both',expand=True,padx=16,pady=10)
        self.chart_note=self._label(self.tab_summary,'Grafik menunjukkan YoY indikatif dari pasangan kolom dalam file yang sama.',9,ORANGE)
        self.chart_note.pack(anchor='w',padx=18,pady=(0,15))
    def _data_ui(self):
        self._label(self.tab_data,'Pertumbuhan tahunan indikatif, bukan hasil audit PDF',12,NAVY,bold=True).pack(anchor='w',padx=15,pady=13)
        frame=tk.Frame(self.tab_data,bg=WHITE);frame.pack(fill='both',expand=True,padx=12,pady=(0,12))
        cols=('periode','akun','yoy','currency','source')
        self.table=ttk.Treeview(frame,columns=cols,show='headings')
        for c,name,width in [('periode','Filing',110),('akun','Akun',230),('yoy','YoY %',100),('currency','Mata uang*',125),('source','File sumber',410)]:
            self.table.heading(c,text=name);self.table.column(c,width=width,anchor='w' if c in ('akun','source') else 'center')
        scrollbar=ttk.Scrollbar(frame,orient='vertical',command=self.table.yview);self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side='left',fill='both',expand=True);scrollbar.pack(side='right',fill='y')
        self._label(self.tab_data,'*Mata uang hanya metadata tingkat laporan; belum pemeriksaan satuan setiap akun.',9,ORANGE).pack(anchor='w',padx=14,pady=5)
    def _article_ui(self):
        self._label(self.tab_article,'Draf riset otomatis • cek sumber sebelum publikasi',12,NAVY,bold=True).pack(anchor='w',padx=14,pady=12)
        self.article_box=tk.Text(self.tab_article,wrap='word',font=('Segoe UI',11),relief='flat',fg=TEXT,bg='#F7FAFD',padx=16,pady=14)
        self.article_box.pack(fill='both',expand=True,padx=14,pady=(0,14))
    def _sources_ui(self):
        self._label(self.tab_source,'Seluruh data: belum diverifikasi independen dengan PDF sumber',12,NAVY,bold=True).pack(anchor='w',padx=14,pady=12)
        f=tk.Frame(self.tab_source,bg=WHITE);f.pack(fill='both',expand=True,padx=12,pady=10)
        cols=('name','loc','status')
        self.sources=ttk.Treeview(f,columns=cols,show='headings')
        for c,label,w in [('name','Dokumen',460),('loc','Lokasi sel contoh',160),('status','Status',320)]:
            self.sources.heading(c,text=label);self.sources.column(c,width=w)
        sc=ttk.Scrollbar(f,orient='vertical',command=self.sources.yview);self.sources.configure(yscrollcommand=sc.set)
        self.sources.pack(side='left',fill='both',expand=True);sc.pack(side='right',fill='y')
    def _find_db(self):
        try:self.db=core.database_at(BASE)
        except FileNotFoundError:
            self.db=None;self.db_label.config(text='Database tidak ditemukan. Klik Pilih Database.');return
        self.db_label.config(text=f'Database (read-only): {self.db}')
        self.symbol['values']=core.available_tickers(self.db)
        self.load()
    def pick_db(self):
        selected=filedialog.askopenfilename(title='Pilih BEI_Financial_Master.db atau financial_modeling_v4_1.db',filetypes=[('SQLite','*.db'),('Semua','*.*')])
        if selected:
            self.db=Path(selected);self.db_label.config(text=f'Database (read-only): {self.db}')
            try:self.symbol['values']=core.available_tickers(self.db);self.load()
            except Exception as e:messagebox.showerror('Database tidak sesuai',str(e))
    def load(self):
        if not self.db:return
        ticker=self.ticker_var.get().strip().upper()
        try:
            self.records=core.get_data(self.db,ticker)
            self.pairs=core.comparative_pairs(self.records)
            self.filtered,self.latest=core.latest_pairs(self.pairs)
            self.ticker=ticker
            if not self.records:raise ValueError(f'Data {ticker} tidak ditemukan di database. Pilih ticker lain.')
        except Exception as e:messagebox.showerror('Gagal memuat data',str(e));return
        self.title_card.config(text=f'{ticker}  |  Snapshot YoY')
        label=f'{self.latest[1]} {self.latest[0]}' if self.latest else 'tidak tersedia'
        self.info_card.config(text=f'Filing terakhir: {label}  •  {len(self.records)} fakta sumber  •  {len(self.pairs)} perbandingan YoY awal  •  status REVIEW')
        for tree in (self.table,self.sources):
            for item in tree.get_children():tree.delete(item)
        for x in sorted(self.pairs,key=lambda a:(a['year'],core.period_order(a['period']),a['label']),reverse=True):
            self.table.insert('',tk.END,values=(f"{x['period']} {x['year']}",x['label'],f"{x['yoy']:+.1f}%",x['currency'],x['filename']))
            self.sources.insert('',tk.END,values=(x['filename'],f"{x['source_current']} / {x['source_prior']}",'REVIEW • PDF belum direkonsiliasi'))
        self.article_box.delete('1.0',tk.END)
        self.article_box.insert('1.0',core.article(self.ticker,self.pairs,self.latest))
        self.draw()
        self.status.config(text=f'{ticker}: {len(self.pairs)} komparasi. Semua hasil berstatus REVIEW.')
    def draw(self):
        for item in self.fig_area.winfo_children():item.destroy()
        lp=self.filtered
        focus=['revenue','gross_profit','net_income_parent','cashflow_operating','capex_ppe_outflow']
        rows=[next((x for x in lp if x['metric']==m),None) for m in focus]
        rows=[x for x in rows if x]
        if not rows:
            self._label(self.fig_area,'Belum ada pasangan angka yang layak dihitung YoY awal pada filing terakhir.',12,MUTED).pack(pady=45)
            return
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            fig=Figure(figsize=(10,4.4),dpi=100,facecolor=WHITE)
            ax=fig.add_subplot(111)
            colors=['#247D91' if r['yoy']>=0 else '#C26D5D' for r in rows]
            bars=ax.barh([r['label'] for r in rows],[r['yoy'] for r in rows],color=colors,height=0.57)
            ax.invert_yaxis();ax.axvline(0,color='#667C8D',lw=1)
            ax.set_xlabel('Pertumbuhan YoY (%) • indikatif / REVIEW')
            ax.set_title(f"{self.ticker} — {self.latest[1]} {self.latest[0]} vs periode pembanding",loc='left',color=NAVY,fontsize=13)
            ax.spines[['right','top','left']].set_visible(False);ax.grid(axis='x',alpha=.18)
            for bar,r in zip(bars,rows):
                val=r['yoy'];ax.text(val+(.8 if val>=0 else -.8),bar.get_y()+bar.get_height()/2,f'{val:+.1f}%',ha='left' if val>=0 else 'right',va='center',fontsize=10)
            minx=min([r['yoy'] for r in rows]+[0]);maxx=max([r['yoy'] for r in rows]+[0]);pad=max(8,(maxx-minx)*.2)
            ax.set_xlim(minx-pad,maxx+pad);fig.tight_layout(pad=2)
            c=FigureCanvasTkAgg(fig,master=self.fig_area);c.draw();c.get_tk_widget().pack(fill='both',expand=True)
            self.last_figure=fig
        except ImportError:
            self.last_figure=None
            self._label(self.fig_area,'Grafik membutuhkan matplotlib. Jalankan: py -m pip install matplotlib',12,ORANGE).pack(pady=40)
    def outdir(self):
        p=BASE/'BEI_Dashboard_Output'/self.ticker;p.mkdir(parents=True,exist_ok=True);return p
    def export_article(self):
        if not self.records:return
        p=self.outdir()/f'{self.ticker}_DRAF_REVIEW.md'
        p.write_text(self.article_box.get('1.0','end-1c'),encoding='utf-8')
        messagebox.showinfo('Artikel disimpan',str(p))
    def export_data(self):
        if not self.pairs:return messagebox.showwarning('Belum ada data','Tidak ada data YoY awal yang dapat diekspor.')
        p=self.outdir()/f'{self.ticker}_YOY_REVIEW.csv';core.export_csv(p,self.pairs)
        messagebox.showinfo('CSV disimpan',str(p))
    def export_png(self):
        if not getattr(self,'last_figure',None):return messagebox.showwarning('Grafik tidak tersedia','Instal matplotlib atau pilih emiten dengan perbandingan YoY.')
        p=self.outdir()/f'{self.ticker}_YOY_REVIEW_IG.png'
        # 4:5 vertical Instagram export; title and warning deliberately prominent.
        fig=self.last_figure
        from matplotlib.figure import Figure
        x=self.filtered;focus=['revenue','gross_profit','net_income_parent','cashflow_operating','capex_ppe_outflow']
        rows=[next((r for r in x if r['metric']==m),None) for m in focus];rows=[r for r in rows if r]
        out=Figure(figsize=(10.8,13.5),dpi=100,facecolor=NAVY)
        ax=out.add_axes([.12,.24,.83,.46],facecolor=NAVY)
        ax.barh([r['label'] for r in rows],[r['yoy'] for r in rows],color=['#AAE1FF' if r['yoy']>=0 else '#FFB5A9' for r in rows],height=.54)
        ax.invert_yaxis();ax.axvline(0,color='#D2E3EF',alpha=.65);ax.grid(axis='x',alpha=.16,color='white')
        ax.tick_params(axis='both',colors='white',labelsize=13);ax.set_xlabel('YoY (%)',color='white',fontsize=13)
        for sp in ax.spines.values():sp.set_visible(False)
        out.text(.08,.90,f'{self.ticker} | BACA ANGKANYA',fontweight='bold',fontsize=31,color='white')
        out.text(.08,.84,f'{self.latest[1]} {self.latest[0]} vs tahun sebelumnya',fontsize=21,color='#AAE1FF')
        out.text(.08,.14,'DATA REVIEW — BELUM UNTUK PUBLIKASI',color='#FFB5A9',fontsize=19,weight='bold')
        out.text(.08,.09,'Sumber: laporan XBRL BEI • validasi PDF & satuan diperlukan',color='#DCE9F5',fontsize=12)
        out.savefig(p,dpi=100,facecolor=NAVY)
        messagebox.showinfo('Grafik PNG dibuat',f'{p}\n\nPERINGATAN: gambar ini masih memuat label REVIEW.')

if __name__=='__main__':Dashboard().mainloop()
