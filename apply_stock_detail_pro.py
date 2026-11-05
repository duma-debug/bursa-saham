from pathlib import Path
import sys, shutil, datetime, py_compile
p=Path(sys.argv[1] if len(sys.argv)>1 else 'bei_platform/market.py'); src=p.read_text(encoding='utf-8')
if 'STOCK_DETAIL_PRO_PATCH_V01' in src:
 print('Patch sudah diterapkan, tidak ada perubahan.');sys.exit(0)
def replace(old,new,expected=1):
 global src
 n=src.count(old)
 if n!=expected:raise RuntimeError(f'Kecocokan blok tidak sesuai: {n} (harus {expected}); source tidak diubah. Awal: {old[:85]}')
 src=src.replace(old,new)
replace("        self.stock_panes.add(chart_host,weight=3)\n        self.stock_panes.add(viewer,weight=2)","""        # STOCK_DETAIL_PRO_PATCH_V01: adjustable main chart / financial insight split.
        self.stock_panes.add(chart_host,weight=7)
        self.stock_panes.add(right_host,weight=3)""")
replace("        viewer=ttk.LabelFrame(self.stock_panes,text='Financial Statement Viewer — Ctrl+C untuk copy',padding=6)","""        right_host=ttk.Frame(self.stock_panes)
        ratio_frame=ttk.LabelFrame(right_host,text='Key Financial Ratios & Market Cap',padding=5)
        ratio_frame.pack(fill='x',pady=(0,4))
        self.pro_ratios=tk.StringVar(value='Buka saham untuk memuat rasio utama.')
        ttk.Label(ratio_frame,textvariable=self.pro_ratios,wraplength=420,justify='left').pack(fill='x')
        viewer=ttk.LabelFrame(right_host,text='Financial Statement Viewer — Ctrl+C untuk copy',padding=6)
        viewer.pack(fill='both',expand=True)""")
replace("        chart_group=ttk.LabelFrame(self.stock_charts,text='Grafik fundamental — Annual / Quarterly YTD',padding=(5,3))\n        chart_group.pack(fill='x',pady=(3,3))", """        chart_group=ttk.LabelFrame(right_host,text='Financial Insights — Annual / Quarterly YTD',padding=(5,3))
        chart_group.pack(fill='x',pady=(3,3),before=viewer)""")
replace("            cv=ThemeCanvas(cell,bg='white',height=135,highlightthickness=1,highlightbackground='#dce3ec')", "            cv=ThemeCanvas(cell,bg='white',height=85,highlightthickness=1,highlightbackground='#dce3ec')")
replace("        ttk.Label(self.stock_charts,text='Foreign Net — hijau: Net Buy | merah: Net Sell',font=('Segoe UI',8)).pack(anchor='w')", "        # Foreign Net is now a line with secondary Y-axis on the Buy/Sell chart.")
replace("        self.stock_flow_net_canvas.pack(fill='x',pady=(1,3))", "        # Separate net canvas remains instantiated for legacy fullscreen compatibility, but hidden in Stock Detail.")
replace("text='Foreign Flow per Saham (lembar) — Buy / Sell dan Net terpisah'", "text='Foreign Flow — Buy/Sell (batang) + Net (garis, Y kanan)'" )
replace("        self.stock_snapshot.set('    |    '.join(parts))", """        self.stock_snapshot.set('    |    '.join(parts))
        eps,ep_period=latest_metric(self.finance,'eps')
        net,ni_period=latest_metric(self.finance,'net_income')
        revenue,rev_period=latest_metric(self.finance,'revenue')
        assets,_=latest_metric(self.finance,'total_assets')
        margin=100*net/revenue if net is not None and revenue not in (None,0) else None
        roa=100*net/assets if net is not None and assets not in (None,0) else None
        vals=[f'Market Cap   Rp {mcap/1e12:,.2f} T' if mcap is not None else 'Market Cap   —',
              f'Outstanding   {compact(shares)} lembar' if shares else 'Outstanding   —',
              f'PER (EPS laporan)   {price/eps:,.2f}x [{ep_period}]' if price and eps is not None and eps>0 else 'PER   — (EPS tahunan/TTM belum valid)',
              f'PBV   {pbv:,.2f}x' if pbv is not None else 'PBV   —',
              f'Net Margin YTD   {margin:,.1f}% [{ni_period}]' if margin is not None else 'Net Margin   —',
              f'ROA indikatif (belum annualized)   {roa:,.1f}%' if roa is not None else 'ROA   —']
        self.pro_ratios.set('\\n'.join(vals))""")
# Avoid misleading PER: current eps is YTD; replace with clearly unavailability until TTM.
replace("              f'PER (EPS laporan)   {price/eps:,.2f}x [{ep_period}]' if price and eps is not None and eps>0 else 'PER   — (EPS tahunan/TTM belum valid)',", "              'PER   — (memerlukan EPS FY/TTM yang valid)',")
needle="            cv._foreign_hits=hits\n\n    def hover_stock_flow"
replacement="""            cv._foreign_hits=hits
            if mode=='buy' and pts:
                # Net line on secondary Y-axis; zero aligned to middle of plot.
                # Secondary axis is independently scaled to +/- max absolute net.
                mid=(top+bottom)/2
                scale=max(1,(bottom-top)/2-3)
                cv.create_line(right,top,right,bottom,fill='#9eacbc')
                cv.create_text(right-4,top+1,text='Net +'+compact(nmax),anchor='ne',fill='#c18a00',font=('Segoe UI',7))
                cv.create_text(right-4,bottom-1,text='-'+compact(nmax),anchor='se',fill='#c18a00',font=('Segoe UI',7))
                cv.create_line(left,mid,right,mid,fill='#a1adbb',dash=(2,3))
                previous=None
                for i,(date,b,s,n) in enumerate(pts):
                    xx=left+(i+.5)*slot
                    yy=mid-(n/nmax)*scale
                    if previous is not None:
                        cv.create_line(previous[0],previous[1],xx,yy,fill='#edb429',width=2)
                    previous=(xx,yy)
                cv.create_text(left+3,top+1,text='Hijau Buy  |  Merah Sell  |  Kuning Net',anchor='nw',font=('Segoe UI',7),fill='#c18a00')

    def hover_stock_flow"""
replace(needle,replacement)
# Change draw lines to avoid overlap of chart lines covering hovered exact bar by saving data in strip already exists.
backup=p.with_name(p.name+'.before_stockpro_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.bak')
shutil.copy2(p,backup)
p.write_text(src,encoding='utf-8')
try:py_compile.compile(str(p),doraise=True)
except Exception:
 shutil.copy2(backup,p);raise
print('PATCH SUKSES:',p)
print('BACKUP:',backup)
