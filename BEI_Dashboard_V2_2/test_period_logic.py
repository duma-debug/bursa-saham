from pathlib import Path
import dashboard_core as c
import historical_matrix as h
base=Path(__file__).resolve().parent
p=base.parent/'BEI_Financial_Master_example.db'
if not p.is_file():
 print('Sample DB absent: skip integration test')
else:
 ades=c.get_data(p,'ADES');ps,ms,ch=h.build(ades,'Annual','All')
 assert (2025,'BS_DEC') in ps
 assert h.cell_status('cashflow_operating',(2025,'BS_DEC'),ch)[0]=='NOT_APPLICABLE'
 assert (2025,'FY') not in ps
 ps,ms,ch=h.build(ades,'All','All')
 assert (2026,'Q3') in ps and (2025,'Q3') in ps
 assert ps==sorted(ps,key=h._sort)
 hr=c.get_data(p,'HRUM');ps,ms,ch=h.build(hr,'Annual','All')
 assert (2025,'BS_DEC') in ps and (2025,'FY') not in ps
 qp,qm,qc=h.standalone_view(hr)
 assert qp and not qc
 print('PASS: ADES BS-only / YTD / All periods; HRUM FY separation; standalone blocked')
