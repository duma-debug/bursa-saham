"""Smoke test using provided BEI database copies: python test_v24.py BASE"""
import sys,sqlite3
from pathlib import Path
from dashboard_core import get_data
from historical_matrix import build
from restore_comparatives import restore
if __name__=='__main__':
 base=Path(sys.argv[1])
 res=restore(base/'financial_production.db',base/'BEI_Master_Output'/'BEI_Financial_Master.db',base/'BEI_Master_Output'/'legacy_2022_recovery_report.json')
 assert res['integrity_check']=='ok'
 rows=get_data(base/'BEI_Master_Output'/'BEI_Financial_Master.db','AALI')
 periods,_,chosen=build(rows,'Annual','All')
 assert (2021,'FY') in periods
 assert float(chosen[('revenue',(2021,'FY'))]['raw_value'])==24322048
 assert float(chosen[('cashflow_operating',(2021,'FY'))]['raw_value'])==4895119
 print('PASS FY2021 revenue, cash flow; periods:',periods)
