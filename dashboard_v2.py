#!/usr/bin/env python3
"""Integrated Dashboard BEI V2. Pure Python standard library, SQLite read-only."""
import argparse, csv, sys, subprocess, zipfile, datetime
from pathlib import Path
from collections import Counter
from xml.sax.saxutils import escape

SCHEMAS={
 'Market Overview':[('ticker','Ticker'),('company','Perusahaan'),('trade_date','Tanggal'),('close_idr','Close (Rp)'),('change_pct','Change (%)'),('volume','Volume'),('value_idr','Value (Rp)'),('price_return_5d_pct','Return 5D (%)'),('price_return_20d_pct','Return 20D (%)'),('volume_ratio_5d','Volume / Avg 5D'),('data_quality','Kualitas Data')],
 'Foreign Flow':[('ticker','Ticker'),('company','Perusahaan'),('trade_date','Tanggal'),('net_foreign_volume_today','Net Foreign 1D (volume)'),('net_foreign_5d','Net Foreign 5D'),('net_foreign_10d','Net Foreign 10D'),('net_foreign_20d','Net Foreign 20D'),('foreign_days_available','Sesi Tersedia'),('change_pct','Change (%)'),('data_quality','Kualitas Data')],
 'Fundamental':[('ticker','Ticker'),('company','Perusahaan'),('fiscal_period','Laporan Terakhir'),('revenue_ytd_million_idr','Revenue YTD (Rp juta)'),('net_income_ytd_million_idr','Net Income YTD (Rp juta)'),('net_income_ttm_million_idr','Net Income TTM (Rp juta)'),('eps_ttm_idr_per_share','EPS TTM (Rp/saham)'),('roe_reported_pct','ROE Reported (%)'),('roa_reported_pct','ROA Reported (%)'),('net_margin_reported_pct','Net Margin (%)'),('revenue_growth_reported_pct','Revenue Growth (%)'),('net_income_growth_reported_pct','Net Income Growth (%)'),('publication_date','Tgl Publikasi'),('data_quality','Kualitas Data')],
 'Valuation':[('ticker','Ticker'),('company','Perusahaan'),('close_idr','Close (Rp)'),('fiscal_period','Periode'),('per_market_ttm_x','PER Market TTM (x)'),('pbv_market_x','PBV Market (x)'),('per_reported_x','PER Reported (x)'),('pbv_reported_x','PBV Reported (x)'),('eps_ttm_idr_per_share','EPS TTM (Rp/saham)'),('fundamental_is_historical_only','Fundamental Lama?'),('publication_verified','Publikasi Diverifikasi?'),('data_quality','Kualitas Data')],
 'Stock Screener':[('ticker','Ticker'),('company','Perusahaan'),('close_idr','Close (Rp)'),('change_pct','Change (%)'),('value_idr','Value (Rp)'),('net_foreign_5d','Foreign 5D'),('net_foreign_20d','Foreign 20D'),('price_return_5d_pct','Return 5D (%)'),('price_return_20d_pct','Return 20D (%)'),('volume_ratio_5d','Volume / Avg5D'),('fiscal_period','Fundamental Periode'),('roe_reported_pct','ROE (%)'),('net_income_growth_reported_pct','Net Income Growth (%)'),('per_market_ttm_x','PER TTM (x)'),('pbv_market_x','PBV (x)'),('data_quality','Kualitas Data')]
}
# OOXML serializer; no external packages required on Windows.
def colname(i):
 s='';i+=1
 while i:i,r=divmod(i-1,26);s=chr(65+r)+s
 return s

def num(v):
 if v is None or str(v).strip()=='':return None
 try:
  a=float(v)
  if a!=a or abs(a)==float('inf'):return None
  return a
 except (ValueError,TypeError):return None

def data_cell(ref,value,fmt=0):
 if value is None or value=='':return ''
 if isinstance(value,(int,float)):
  return f'<c r="{ref}" s="{fmt}"><v>{value}</v></c>'
 return f'<c r="{ref}" s="{fmt}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'

def xmlsheet(headers,records,keys,meta=False):
 n=len(headers); end=colname(n-1)
 parts=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
 f'<dimension ref="A1:{end}{max(2,len(records)+1)}"/>','<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
 '<sheetFormatPr defaultRowHeight="16"/>','<cols>']
 for j,h in enumerate(headers):
  width=min(64,max(14,len(h)+3))
  if 'Kualitas' in h:width=64
  if 'Perusahaan' in h:width=33
  parts.append(f'<col min="{j+1}" max="{j+1}" width="{width}" customWidth="1"/>')
 parts.append('</cols><sheetData><row r="1" ht="27" customHeight="1">')
 for j,h in enumerate(headers):parts.append(data_cell(f'{colname(j)}1',h,1))
 parts.append('</row>')
 for i,row in enumerate(records,2):
  parts.append(f'<row r="{i}">')
  for j,k in enumerate(keys):
   v=row.get(k)
   if k not in ('ticker','company','trade_date','fiscal_period','fiscal_period_end','publication_date','publication_verified','fundamental_is_historical_only','data_quality'):
    val=num(v)
    if val is None:continue
    style=3 if 'pct' in k or 'growth' in k or 'margin' in k or k.startswith(('roe_','roa_')) else 2
    parts.append(data_cell(f'{colname(j)}{i}',val,style))
   else:parts.append(data_cell(f'{colname(j)}{i}',v,4 if k=='data_quality' else 0))
  parts.append('</row>')
 parts.append('</sheetData>')
 parts.append(f'<autoFilter ref="A1:{end}{max(2,len(records)+1)}"/>')
 parts.append('<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/></worksheet>')
 return ''.join(parts).encode('utf-8')

def make_xlsx(dest,sheets):
 ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
  overrides=['<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>','<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
  for i in range(1,len(sheets)+1):overrides.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
  z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join(overrides)+'</Types>')
  z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(sheets,1))+'</sheets></workbook>')
  rels=''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))
  z.writestr('xl/_rels/workbook.xml.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+rels+'<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
  z.writestr('xl/styles.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="'+ns+'"><numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00;[Red](#,##0.00);–"/><numFmt numFmtId="165" formatCode="#,##0.00;[Red](#,##0.00);–"/></numFmts><fonts count="3"><font><sz val="11"/><name val="Aptos"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font><font><sz val="10"/><color rgb="FF64748B"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF16355B"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
  for i,(name,(headers,rows,keys)) in enumerate(sheets.items(),1):z.writestr(f'xl/worksheets/sheet{i}.xml',xmlsheet(headers,rows,keys))

def main():
 p=argparse.ArgumentParser(description='Buat dashboard .xlsx dari data SQLite; tanpa paket pihak ketiga')
 p.add_argument('--db',default='pasar_bei_prototipe.db');p.add_argument('--output',default='output_dashboard')
 a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
 db=Path(a.db)
 script=Path(__file__).resolve().parent/'integrated_screener.py'
 if not script.exists():raise RuntimeError('integrated_screener.py tidak ditemukan dalam folder yang sama')
 run=subprocess.run([sys.executable,str(script),'--db',str(db),'--output',str(out/'data_screener')],capture_output=True,text=True)
 if run.returncode:raise RuntimeError(run.stderr or run.stdout)
 csvfile=out/'data_screener'/'Integrated_Screener.csv'
 with csvfile.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
 if not rows:raise RuntimeError('Tidak ada baris saham pada output screener')
 rows.sort(key=lambda r:r.get('ticker',''))
 sheets={}
 for name,spec in SCHEMAS.items():
  r=rows
  if name in ('Fundamental','Valuation'):r=[x for x in rows if x.get('fiscal_period')]
  if name=='Foreign Flow':r=sorted(rows,key=lambda x:num(x.get('net_foreign_volume_today')) or 0,reverse=True)
  sheets[name]=([h for _,h in spec],r,[k for k,_ in spec])
 path=out/'Integrated_Dashboard_BEI_V2.xlsx';make_xlsx(path,sheets)
 print('BERHASIL |',path,'| Saham:',len(rows),'| Dengan fundamental:',sum(bool(x.get('fiscal_period')) for x in rows),'| Tanggal:',rows[0]['trade_date'])
 print('Catatan: kolom kosong berarti data tidak tersedia; bukan nol. Dashboard ini bukan backtesting historis.')
if __name__=='__main__':
 try:main()
 except Exception as e:print('GAGAL:',e,file=sys.stderr);sys.exit(1)
