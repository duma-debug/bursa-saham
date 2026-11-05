from pathlib import Path
import dashboard_core as core
import historical_matrix as hist
p=Path(__file__).resolve().parent
root=Path(r'C:\Analisis_Saham_BEI\BEI_Master_Output\BEI_Financial_Master.db')
if not root.exists():
 root=Path('/mnt/data/BEI_Financial_Master_example.db')
if not root.exists():
 raise SystemExit('Tidak ada database master untuk pengujian')
for ticker in ['AALI','HRUM','ADES']:
 records=core.get_data(root,ticker)
 for mode in ('Annual','Quarterly','All'):
  ps,ms,ch=hist.build(records,mode)
  print(ticker,mode,'periods',list(map(hist.label,ps)),'cells',len(ch))
  if ticker=='AALI' and mode=='Annual':
   for metric,val in [('cashflow_operating',4210590),('cashflow_investing',-781980),('cashflow_financing',-3963156),('cash_begin',3236012),('cash_end',2755715)]:
    x=ch.get((metric,(2025,'FY')))
    assert x and float(x['raw_value'])==val,(metric,x)
   assert float(ch[('cashflow_operating',(2024,'FY'))]['raw_value'])==3379195
  if ticker=='HRUM' and mode=='Annual':
   assert ('cashflow_operating',(2025,'FY')) not in ch
print('ALL ASSERTIONS PASS')
