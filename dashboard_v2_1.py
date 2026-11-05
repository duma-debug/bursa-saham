#!/usr/bin/env python3
"""Integrated Dashboard BEI V2.1 with sector summary and treemap SVG.
No third-party dependencies. Reads sector mapping from xlsx using stdlib XML parser.
"""
import argparse, csv, sys, subprocess, zipfile
from pathlib import Path
from collections import Counter, defaultdict
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

SCHEMAS={
 'Market Overview':[('ticker','Ticker'),('company','Perusahaan'),('trade_date','Tanggal'),('close_idr','Close (Rp)'),('change_pct','Change (%)'),('volume','Volume'),('value_idr','Value (Rp)'),('price_return_5d_pct','Return 5D (%)'),('price_return_20d_pct','Return 20D (%)'),('volume_ratio_5d','Volume / Avg 5D'),('data_quality','Kualitas Data')],
 'Foreign Flow':[('ticker','Ticker'),('company','Perusahaan'),('trade_date','Tanggal'),('net_foreign_volume_today','Net Foreign 1D (volume)'),('net_foreign_5d','Net Foreign 5D'),('net_foreign_10d','Net Foreign 10D'),('net_foreign_20d','Net Foreign 20D'),('foreign_days_available','Sesi Tersedia'),('change_pct','Change (%)'),('data_quality','Kualitas Data')],
 'Fundamental':[('ticker','Ticker'),('company','Perusahaan'),('fiscal_period','Laporan Terakhir'),('revenue_ytd_million_idr','Revenue YTD (Rp juta)'),('net_income_ytd_million_idr','Net Income YTD (Rp juta)'),('net_income_ttm_million_idr','Net Income TTM (Rp juta)'),('eps_ttm_idr_per_share','EPS TTM (Rp/saham)'),('roe_reported_pct','ROE Reported (%)'),('roa_reported_pct','ROA Reported (%)'),('net_margin_reported_pct','Net Margin (%)'),('revenue_growth_reported_pct','Revenue Growth (%)'),('net_income_growth_reported_pct','Net Income Growth (%)'),('publication_date','Tgl Publikasi'),('data_quality','Kualitas Data')],
 'Valuation':[('ticker','Ticker'),('company','Perusahaan'),('close_idr','Close (Rp)'),('fiscal_period','Periode'),('per_market_ttm_x','PER Market TTM (x)'),('pbv_market_x','PBV Market (x)'),('per_reported_x','PER Reported (x)'),('pbv_reported_x','PBV Reported (x)'),('eps_ttm_idr_per_share','EPS TTM (Rp/saham)'),('fundamental_is_historical_only','Fundamental Lama?'),('publication_verified','Publikasi Diverifikasi?'),('data_quality','Kualitas Data')],
 'Stock Screener':[('ticker','Ticker'),('company','Perusahaan'),('close_idr','Close (Rp)'),('change_pct','Change (%)'),('value_idr','Value (Rp)'),('net_foreign_5d','Foreign 5D'),('net_foreign_20d','Foreign 20D'),('price_return_5d_pct','Return 5D (%)'),('price_return_20d_pct','Return 20D (%)'),('volume_ratio_5d','Volume / Avg5D'),('fiscal_period','Fundamental Periode'),('roe_reported_pct','ROE (%)'),('net_income_growth_reported_pct','Net Income Growth (%)'),('per_market_ttm_x','PER TTM (x)'),('pbv_market_x','PBV (x)'),('data_quality','Kualitas Data')],
 'Sector Summary':[('sector','Sektor'),('ticker_count','Jumlah Ticker'),('net_foreign_volume_today','Net Foreign 1D'),('net_foreign_5d','Net Foreign 5D'),('net_foreign_20d','Net Foreign 20D'),('value_idr','Value (Rp)'),('avg_change_pct','Avg Change (%)'),('top_tickers','Top Tickers')],
 'Sector Detail':[('sector','Sektor'),('ticker','Ticker'),('company','Perusahaan'),('net_foreign_volume_today','Net Foreign 1D'),('net_foreign_5d','Net Foreign 5D'),('net_foreign_20d','Net Foreign 20D'),('change_pct','Change (%)'),('close_idr','Close (Rp)'),('value_idr','Value (Rp)'),('fiscal_period','Fundamental Periode'),('data_quality','Kualitas Data')]
}

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

def xmlsheet(headers,records,keys):
 n=len(headers); end=colname(n-1)
 parts=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
 f'<dimension ref="A1:{end}{max(2,len(records)+1)}"/>','<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
 '<sheetFormatPr defaultRowHeight="16"/>','<cols>']
 for j,h in enumerate(headers):
  width=min(70,max(14,len(h)+3))
  if 'Kualitas' in h:width=68
  if 'Perusahaan' in h or 'Top Tickers' in h:width=36
  if 'Sektor' in h: width=24
  parts.append(f'<col min="{j+1}" max="{j+1}" width="{width}" customWidth="1"/>')
 parts.append('</cols><sheetData><row r="1" ht="27" customHeight="1">')
 for j,h in enumerate(headers):parts.append(data_cell(f'{colname(j)}1',h,1))
 parts.append('</row>')
 text_keys={'ticker','company','trade_date','fiscal_period','fiscal_period_end','publication_date','publication_verified','fundamental_is_historical_only','data_quality','sector','top_tickers'}
 for i,row in enumerate(records,2):
  parts.append(f'<row r="{i}">')
  for j,k in enumerate(keys):
   v=row.get(k)
   if k not in text_keys:
    val=num(v)
    if val is None:continue
    style=3 if 'pct' in k or 'growth' in k or 'margin' in k or k.startswith(('roe_','roa_','avg_change')) else 2
    parts.append(data_cell(f'{colname(j)}{i}',val,style))
   else:
    parts.append(data_cell(f'{colname(j)}{i}',v,4 if k=='data_quality' else 0))
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
  for i,(name,(headers,rows,keys)) in enumerate(sheets.items(),1):
   z.writestr(f'xl/worksheets/sheet{i}.xml',xmlsheet(headers,rows,keys))

def parse_xlsx_sector_map(xlsx_path):
 ns={'a':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
 with zipfile.ZipFile(xlsx_path,'r') as z:
  shared=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   root=ET.fromstring(z.read('xl/sharedStrings.xml'))
   for si in root.findall('a:si',ns):
    texts=[]
    for t in si.iterfind('.//a:t',ns): texts.append(t.text or '')
    shared.append(''.join(texts))
  wb=ET.fromstring(z.read('xl/workbook.xml'))
  rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
  relmap={r.attrib['Id']:r.attrib['Target'] for r in rels}
  target=None
  for sheet in wb.findall('a:sheets/a:sheet',ns):
    if sheet.attrib.get('name')=='Daftar Saham':
      rid=sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
      target='xl/'+relmap[rid].lstrip('/')
      break
  if target is None:
    # fallback first worksheet
    for sheet in wb.findall('a:sheets/a:sheet',ns):
      rid=sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
      target='xl/'+relmap[rid].lstrip('/')
      break
  root=ET.fromstring(z.read(target))
  rows=[]
  for row in root.findall('.//a:sheetData/a:row',ns):
    vals={}
    for c in row.findall('a:c',ns):
      ref=c.attrib.get('r','A1')
      col=''.join(ch for ch in ref if ch.isalpha())
      t=c.attrib.get('t')
      v=None
      if t=='inlineStr':
        node=c.find('a:is/a:t',ns); v=node.text if node is not None else ''
      else:
        node=c.find('a:v',ns)
        if node is not None:
          if t=='s':
            try:v=shared[int(node.text)]
            except: v=node.text
          else: v=node.text
      vals[col]=v
    rows.append(vals)
  if not rows: return {}
  header_row=rows[0]
  cols=sorted(header_row.keys(), key=lambda x:(len(x),x))
  headers={c:(header_row.get(c) or '').strip() for c in cols}
  by_name={v:c for c,v in headers.items()}
  kode_col=by_name.get('Kode')
  sector_col=by_name.get('Sector')
  if not kode_col or not sector_col:
    raise ValueError('Kolom Kode / Sector tidak ditemukan pada file sektor')
  mapping={}
  for r in rows[1:]:
    ticker=(r.get(kode_col) or '').strip().upper()
    sector=(r.get(sector_col) or '').strip()
    if ticker:
      mapping[ticker]=sector or 'Unknown'
  return mapping

def recursive_layout(items, x, y, w, h):
 if len(items)==1:
  return [(x,y,w,h,items[0])]
 if len(items)==2:
  total=sum(v['abs_size'] for v in items) or 1
  rects=[]; offset=0; horizontal=w>=h
  for item in items:
   frac=item['abs_size']/total
   if horizontal:
    rw=w*frac; rects.append((x+offset,y,rw,h,item)); offset+=rw
   else:
    rh=h*frac; rects.append((x,y+offset,w,rh,item)); offset+=rh
  return rects
 total=sum(v['abs_size'] for v in items) or 1
 acc=0; idx=max(1,len(items)//2)
 for i,item in enumerate(items):
  if acc+item['abs_size']>=total/2:
   idx=i+1; break
  acc+=item['abs_size']
 if idx>=len(items): idx=max(1,len(items)//2)
 g1=items[:idx]; g2=items[idx:]
 frac=(sum(v['abs_size'] for v in g1)/(total or 1))
 if w>=h:
  w1=w*frac
  return recursive_layout(g1,x,y,w1,h)+recursive_layout(g2,x+w1,y,w-w1,h)
 else:
  h1=h*frac
  return recursive_layout(g1,x,y,w,h1)+recursive_layout(g2,x,y+h1,w,h-h1)

def build_treemap_svg(path, sector_rows, title, subtitle):
 width,height=1600,900
 items=[]
 for r in sector_rows:
  val=num(r.get('net_foreign_volume_today')) or 0
  abs_size=abs(val)
  if abs_size>0: items.append({'sector':r['sector'],'value':val,'abs_size':abs_size})
 if not items: items=[{'sector':'No Data','value':0,'abs_size':1}]
 items=sorted(items,key=lambda x:x['abs_size'], reverse=True)
 layout=recursive_layout(items,0,0,100,60)
 parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 100 60">',
        '<rect x="0" y="0" width="100" height="60" fill="white"/>',
        '<text x="50" y="2" text-anchor="middle" font-size="2.2" font-weight="bold" font-family="Arial">'+escape(title)+'</text>',
        '<text x="50" y="4.5" text-anchor="middle" font-size="1.6" font-family="Arial">'+escape(subtitle)+'</text>']
 for x,y,w,h,it in layout:
  color='#2ca02c' if it['value']>=0 else '#d62728'
  parts.append(f'<rect x="{x:.4f}" y="{y+6:.4f}" width="{w:.4f}" height="{h-6:.4f}" fill="{color}" stroke="white" stroke-width="0.2"/>')
  fs=1.5 if w*h>300 else 1.2 if w*h>150 else 0.95 if w*h>70 else 0.75
  label=f"{it['sector']}\n{int(it['value']):,}"
  lines=label.split('\n')
  cx=x+w/2; cy=y+6+(h-6)/2
  for idx,line in enumerate(lines):
   dy=(-0.5+idx)*fs*0.9
   parts.append(f'<text x="{cx:.4f}" y="{cy+dy:.4f}" text-anchor="middle" font-size="{fs}" font-family="Arial" font-weight="bold" fill="white">{escape(line)}</text>')
 parts.append('</svg>')
 path.write_text(''.join(parts), encoding='utf-8')

def main():
 p=argparse.ArgumentParser(description='Dashboard BEI V2.1 + sector treemap')
 p.add_argument('--db',default='pasar_bei_prototipe.db')
 p.add_argument('--output',default='output_dashboard')
 p.add_argument('--sector-file',default='Daftar Saham  sektor.xlsx')
 a=p.parse_args(); out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
 db=Path(a.db)
 script=Path(__file__).resolve().parent/'integrated_screener.py'
 if not script.exists(): raise RuntimeError('integrated_screener.py tidak ditemukan dalam folder yang sama')
 run=subprocess.run([sys.executable,str(script),'--db',str(db),'--output',str(out/'data_screener')],capture_output=True,text=True)
 if run.returncode: raise RuntimeError(run.stderr or run.stdout)
 csvfile=out/'data_screener'/'Integrated_Screener.csv'
 with csvfile.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
 if not rows: raise RuntimeError('Tidak ada baris saham pada output screener')
 rows.sort(key=lambda r:r.get('ticker',''))
 sector_map={}
 sector_path=Path(a.sector_file)
 if sector_path.exists():
  sector_map=parse_xlsx_sector_map(sector_path)
 else:
  print('PERINGATAN: file sektor tidak ditemukan, semua ticker akan menjadi Unknown', file=sys.stderr)
 for r in rows:
  r['sector']=sector_map.get((r.get('ticker') or '').upper(),'Unknown')
 # sector summary
 groups=defaultdict(list)
 for r in rows: groups[r['sector']].append(r)
 sector_rows=[]; detail_rows=[]
 for sector, items in groups.items():
  def s(field):
   total=0; ok=False
   for it in items:
    v=num(it.get(field))
    if v is not None: total+=v; ok=True
   return round(total,3) if ok else None
  changes=[num(it.get('change_pct')) for it in items if num(it.get('change_pct')) is not None]
  top=sorted(items, key=lambda x: abs(num(x.get('net_foreign_volume_today')) or 0), reverse=True)[:3]
  top_text=', '.join(f"{t['ticker']} ({int(num(t.get('net_foreign_volume_today')) or 0):,})" for t in top)
  sector_rows.append({'sector':sector,'ticker_count':len(items),'net_foreign_volume_today':s('net_foreign_volume_today'),'net_foreign_5d':s('net_foreign_5d'),'net_foreign_20d':s('net_foreign_20d'),'value_idr':s('value_idr'),'avg_change_pct':round(sum(changes)/len(changes),3) if changes else None,'top_tickers':top_text})
  for it in sorted(items, key=lambda x: abs(num(x.get('net_foreign_volume_today')) or 0), reverse=True):
   detail_rows.append({'sector':sector, **it})
 sector_rows.sort(key=lambda r: abs(num(r.get('net_foreign_volume_today')) or 0), reverse=True)
 detail_rows.sort(key=lambda r:(r['sector'],-abs(num(r.get('net_foreign_volume_today')) or 0),r['ticker']))
 sheets={}
 for name,spec in SCHEMAS.items():
  if name=='Sector Summary':
   sheets[name]=([h for _,h in spec], sector_rows, [k for k,_ in spec]); continue
  if name=='Sector Detail':
   sheets[name]=([h for _,h in spec], detail_rows, [k for k,_ in spec]); continue
  r=rows
  if name in ('Fundamental','Valuation'): r=[x for x in rows if x.get('fiscal_period')]
  if name=='Foreign Flow': r=sorted(rows,key=lambda x:num(x.get('net_foreign_volume_today')) or 0, reverse=True)
  sheets[name]=([h for _,h in spec], r, [k for k,_ in spec])
 xlsx_path=out/'Integrated_Dashboard_BEI_V2_1.xlsx'; make_xlsx(xlsx_path,sheets)
 # additional outputs
 with (out/'Sector_Summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=[k for k,_ in SCHEMAS['Sector Summary']],extrasaction='ignore'); w.writeheader(); w.writerows(sector_rows)
 with (out/'Sector_Detail.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=[k for k,_ in SCHEMAS['Sector Detail']],extrasaction='ignore'); w.writeheader(); w.writerows(detail_rows)
 market_date=rows[0].get('trade_date','')
 treemap=out/'Foreign_Net_Buy_Treemap_Sector.svg'
 build_treemap_svg(treemap, sector_rows, 'Treemap Foreign Net Buy per Sector', f'Tanggal: {market_date} | Luas = |Net Foreign 1D| | Hijau = Net Buy | Merah = Net Sell')
 print('BERHASIL |',xlsx_path,'| Saham:',len(rows),'| Dengan fundamental:',sum(bool(x.get('fiscal_period')) for x in rows),'| Sektor:',len(sector_rows),'| Tanggal:',market_date)
 print('Output tambahan:', treemap, '|', out/'Sector_Summary.csv')
 print('Catatan: treemap memakai net foreign 1D berbasis volume. Kolom kosong berarti data tidak tersedia; bukan nol.')

if __name__=='__main__':
 try: main()
 except Exception as e: print('GAGAL:',e,file=sys.stderr); sys.exit(1)
