"""Period-aware XBRL comparative matrix. Conservative: ambiguous contexts never become FY.
Values are unharmonized raw source values, all REVIEW.
"""
from pathlib import Path
from collections import defaultdict
import csv,datetime
from dashboard_core import METRICS

METRIC_ORDER={
 'income_statement':['revenue','cost_of_revenue','gross_profit','selling_expense','general_administrative_expense','finance_costs','profit_before_tax','net_income_total','net_income_parent','eps_basic'],
 'balance_sheet':['cash_equivalents','current_assets','inventories_current','noncurrent_assets','property_plant_equipment','total_assets','current_liabilities','noncurrent_liabilities','total_liabilities','noncontrolling_interests','total_equity'],
 'cash_flow':['cashflow_operating','cashflow_investing','cashflow_financing','capex_ppe_outflow','cash_begin','cash_end']}
LABELS={**METRICS, 'profit_before_tax':'Laba sebelum pajak','eps_basic':'EPS (Rp/saham)','selling_expense':'Beban penjualan','general_administrative_expense':'Beban umum & administrasi','finance_costs':'Biaya keuangan','inventories_current':'Persediaan','noncurrent_assets':'Aset tidak lancar','property_plant_equipment':'Aset tetap','noncurrent_liabilities':'Liabilitas jangka panjang','noncontrolling_interests':'Kepentingan nonpengendali','cash_begin':'Kas awal periode','cash_end':'Kas akhir periode'}
ROMAN={'I':1,'II':2,'III':3,'IV':4}
FLOW={'income_statement','cash_flow'}

def _date(value):
 try:return datetime.date.fromisoformat(str(value)[:10])
 except (ValueError,TypeError):return None

def period_key(r):
 """Period from source filing dates + statement semantics, not XBRL context label alone.

 Important: IDX spreadsheet cash-flow often has CurrentYearInstant/PriorYearInstant
 context names despite being period-flow statements. These labels are not proof
 of accounting instant. We accept only when the matching current/prior date span
 is present in source metadata and matches the filing's annual/interim window.
 All returned values remain RAW_REVIEW (not publication verified).
 """
 c=str(r.get('reporting_context') or '')
 filing=str(r.get('report_period') or '')
 annual=filing.lower() in ('tahunan','fy','annual')
 q=ROMAN.get(filing)
 if not annual and not q:return None
 statement=r.get('statement')
 year=int(r['report_year'])
 current = c in ('CurrentYearInstant','CurrentYearDuration')
 prior = c in ('PriorYearInstant','PriorYearDuration','PriorEndYearInstant')
 if not (current or prior):return None
 target_year=year if current else year-1
 current_start=_date(r.get('start_current'))
 current_end=_date(r.get('end_current'))
 prior_start=_date(r.get('start_prior'))
 prior_end=_date(r.get('end_prior'))
 start,end=(current_start,current_end) if current else (prior_start,prior_end)
 # All nonbank flow values must match the filing's complete fiscal/YTD span;
 # do not infer missing dates, and never turn a 9M comparator into full-year FY.
 if statement in FLOW:
  if c=='PriorEndYearInstant':return None  # balance comparator, not flow
  if not start or not end or start.year!=target_year or end.year!=target_year:return None
  if (start.month,start.day)!=(1,1):return None
  expected_end=(12,31) if annual else (q*3,{1:31,2:30,3:30,4:31}[q])
  if (end.month,end.day)!=expected_end:return None
  return (target_year,'FY' if annual else 'Q'+str(q))
 if statement=='balance_sheet':
  if c=='PriorEndYearInstant':
   # As-reported previous fiscal year-end balance, commonly the comparative
   # column in an interim balance sheet. This *must not* create FY flows.
   # Prior statement date cannot be proven from duration metadata alone;
   # retain REVIEW and allow source inspection per cell.
   return (year-1,'FY' if annual else 'BS_DEC')
  if c=='CurrentYearInstant':return (year,'FY' if annual else 'Q'+str(q))
  if c=='PriorYearInstant' and annual:return (year-1,'FY')
  # Do not infer prior-year quarter balance from duration metadata.
  return None
 return None

def _included(p,mode):
 code=p[1]
 if mode=='Annual':return code in ('FY','BS_DEC')
 if mode=='Quarterly':return code.startswith('Q')
 return True

def _sort(p):
 year,code=p
 return (year, {'Q1':3,'Q2':6,'Q3':9,'Q4':12,'FY':12,'BS_DEC':12}.get(code,0), {'BS_DEC':0,'FY':1}.get(code,0))

def label(p):
 year,code=p
 if code=='FY':return f'FY {year}'
 if code=='BS_DEC':return f'31 Dec {year} (BS only)'
 q=int(code[1]);return f'{["3M","6M","9M","12M"][q-1]} {year} (YTD / BS)'

def build(records,mode='Annual',statement='All'):
 found=defaultdict(list)
 for r in records:
  if statement!='All' and r.get('statement')!=statement:continue
  p=period_key(r)
  if p is None or not _included(p,mode) or r.get('value') is None:continue
  found[(r['metric'],p)].append(r)
 # An actual audited FY filing gets preference; BS-only prior December never treated as FY flow.
 chosen={}
 for k,rr in found.items():
  rr.sort(key=lambda r:(int(r['report_year']),r.get('reporting_context','').startswith('Current'),int(r.get('source_id') or 0)),reverse=True)
  chosen[k]=dict(rr[0],alternatives=len(rr)-1)
 # Merge December BS-only with real FY column if actual FY records exist in same fiscal year.
 years_with_fy={p[0] for _,p in chosen if p[1]=='FY'}
 for (metric,p),r in list(chosen.items()):
  if p[1]=='BS_DEC' and p[0] in years_with_fy:
   target=(metric,(p[0],'FY'))
   if target not in chosen:chosen[target]=r
   del chosen[(metric,p)]
 periods=sorted({p for _,p in chosen},key=_sort)
 present={(r.get('statement'),r.get('metric')) for r in chosen.values()}
 order=[(s,m) for s in ('income_statement','balance_sheet','cash_flow') if statement in ('All',s) for m in METRIC_ORDER[s]]
 metrics=[m for s,m in order if (s,m) in present]
 metrics += [m for s,m in sorted(present-set(order))]
 return periods,metrics,chosen

def display(raw):
 try:
  n=float(raw)
  return f'{n:,.0f}' if n.is_integer() else f'{n:,.2f}'
 except (ValueError,TypeError,OverflowError):return str(raw or '—')

def export(path,periods,metrics,chosen,ticker):
 path=Path(path);path.parent.mkdir(exist_ok=True,parents=True)
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow([ticker+' - RAW REVIEW; UNNORMALIZED',*[label(p) for p in periods]])
  for m in metrics:w.writerow([LABELS.get(m,m),*[chosen[(m,p)]['raw_value'] if (m,p) in chosen else ('N/A' if cell_status(m,p,chosen)[0]=='NOT_APPLICABLE' else 'NOT_AVAILABLE') for p in periods]])
  w.writerow([]);w.writerow(['CAUTION: Values from different reports may have DIFFERENT currencies/scales; no valuation, growth or TTM from this CSV.'])
  w.writerow(['metric','period','filename','source_sheet','source_cell','context','currency','presentation_scale','alternatives','quality'])
  for m in metrics:
   for p in periods:
    if (m,p) not in chosen:continue
    r=chosen[(m,p)]
    w.writerow([m,label(p),r['filename'],r['source_sheet'],r['source_cell'],r['reporting_context'],r.get('currency'),r.get('presentation_scale'),r.get('alternatives',0),'REVIEW'])

# V2.2 additions: explicit status for empty cells; no implicit zero.
def cell_status(metric, period, chosen):
    r=chosen.get((metric, period))
    if r is not None:
        return 'REVIEW', 'Angka mentah tersedia, satuan dan sumber pelaporan belum selesai direkonsiliasi.'
    code=period[1]
    if code == 'BS_DEC' and metric not in METRIC_ORDER['balance_sheet']:
        return 'NOT_APPLICABLE', 'Kolom ini hanya posisi neraca 31 Desember; tidak ada laporan laba rugi/arus kas setahun penuh.'
    if code.startswith('Q') and metric in METRIC_ORDER['balance_sheet']:
        return 'NOT_AVAILABLE', 'Saldo neraca pada akhir periode ini belum tersedia di data yang dipetakan.'
    return 'NOT_AVAILABLE', 'Akun/periode ini belum ditemukan atau belum lolos pemetaan konteks; bukan nilai nol.'

def standalone_view(records, statement='All'):
    """No arithmetic on unverified mixed-scale facts. Returns empty derived table with periods populated.
    Computing quarterly standalone is explicitly held until per-record unit/context/scope approval.
    """
    periods,metrics,selected=build(records,'Quarterly',statement)
    translated=[]
    for p in periods:
        year,code=p
        if not code.startswith('Q'):continue
        translated.append((year,'S'+code[1:]))
    return translated, metrics, {}

def standalone_label(p):
    return f'Q{p[1][1:]} {p[0]} (standalone)'
