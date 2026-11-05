"""Historical matrix read-only from BEI Financial Master; XBRL values are REVIEW, not harmonized."""
import csv, re
from collections import defaultdict
from pathlib import Path
from dashboard_core import METRICS, DURATION, period_label, period_order

METRIC_ORDER={
 'income_statement':['revenue','cost_of_revenue','gross_profit','selling_expense','general_administrative_expense','finance_costs','profit_before_tax','net_income_total','net_income_parent','eps_basic'],
 'balance_sheet':['cash_equivalents','current_assets','inventories_current','noncurrent_assets','property_plant_equipment','total_assets','current_liabilities','noncurrent_liabilities','total_liabilities','noncontrolling_interests','total_equity'],
 'cash_flow':['cashflow_operating','cashflow_investing','cashflow_financing','capex_ppe_outflow','cash_begin','cash_end']}
MORE_LABELS={'profit_before_tax':'Laba sebelum pajak','eps_basic':'EPS (Rp/saham)','selling_expense':'Beban penjualan','general_administrative_expense':'Beban umum & administrasi','finance_costs':'Biaya keuangan','inventories_current':'Persediaan','noncurrent_assets':'Aset tidak lancar','property_plant_equipment':'Aset tetap','noncurrent_liabilities':'Liabilitas jangka panjang','noncontrolling_interests':'Kepentingan nonpengendali','cash_begin':'Kas awal periode','cash_end':'Kas akhir periode'}
LABELS={**METRICS,**MORE_LABELS}

def _context(r):
    c=r.get('reporting_context') or ''
    if c in ('CurrentYearInstant','CurrentYearDuration'):return 'current'
    if c in ('PriorYearInstant','PriorYearDuration','PriorEndYearInstant'):return 'prior'
    return None

def _filing_period(r):
    p=period_label(r.get('report_period'))
    return p if p=='FY' or p in ('Q1','Q2','Q3','Q4') else None

def _period_key(r):
    role=_context(r);fp=_filing_period(r)
    if role is None or fp is None:return None
    fy=int(r['report_year'])-(role=='prior')
    dur=r.get('metric') in DURATION or r.get('statement') in ('income_statement','cash_flow') and r.get('metric') not in ('cash_begin','cash_end')
    if role=='prior' and fp!='FY' and not dur:
        return (fy,'FY')  # prior-end balance is previous year END, not comparable quarter
    return fy,fp

def build(records, mode='Annual', statement='All'):
    items=defaultdict(list)
    allowed={'Annual':lambda p:p=='FY','Quarterly':lambda p:p!='FY','All':lambda p:True}[mode]
    for r in records:
        if statement!='All' and r.get('statement')!=statement:continue
        k=_period_key(r)
        if not k or not allowed(k[1]):continue
        if r.get('value') is None:continue
        items[(r['metric'],k)].append(r)
    # More recent filing is preference only, not verified restatement selection.
    chosen={}
    for k,candidates in items.items():
        candidates.sort(key=lambda r:(r['report_year'],1 if _context(r)=='current' else 0,r.get('source_id') or 0),reverse=True)
        chosen[k]=dict(candidates[0],alternatives=len(candidates)-1)
    periods=sorted(set(p for m,p in chosen),key=lambda p:(p[0],period_order(p[1])))
    # Prevent visually ambiguous column order: FY and Q3 in same calendar year ordered by fiscal period.
    if statement=='All':
        all_order=[(s,m) for s in ('income_statement','balance_sheet','cash_flow') for m in METRIC_ORDER[s]]
    else:all_order=[(statement,m) for m in METRIC_ORDER.get(statement,[])]
    present={(r.get('statement'),r.get('metric')) for r in chosen.values()}
    extras=sorted(present-set(all_order))
    metrics=[m for s,m in all_order if (s,m) in present]+[m for s,m in extras]
    return periods,metrics,chosen

def display(raw):
    try:
        n=float(raw)
        if abs(n)>=1e12:return f'{n:,.0f}'
        if n.is_integer():return f'{n:,.0f}'
        return f'{n:,.2f}'
    except (ValueError,TypeError,OverflowError):return str(raw or '—')

def export(path,periods,metrics,chosen,ticker):
    path=Path(path);path.parent.mkdir(exist_ok=True,parents=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f)
        w.writerow([f'{ticker} / RAW REVIEW (NOT NORMALIZED)',*[' '.join(map(str,p)) for p in periods]])
        for m in metrics:w.writerow([LABELS.get(m,m),*[chosen[(m,p)]['raw_value'] if (m,p) in chosen else '' for p in periods]])
        w.writerow([])
        w.writerow(['IMPORTANT: raw values can have DIFFERENT units/scales between filing sources. Do not compare across columns until reconciled.'])
        w.writerow(['metric','fiscal_period','source_file','source_sheet','source_cell','currency','presentation_scale','alternatives','status'])
        for m in metrics:
            for p in periods:
                if (m,p) not in chosen:continue
                r=chosen[(m,p)]
                w.writerow([m,f'{p[1]} {p[0]}',r['filename'],r['source_sheet'],r['source_cell'],r.get('currency'),r.get('presentation_scale'),r['alternatives'],'REVIEW'])
