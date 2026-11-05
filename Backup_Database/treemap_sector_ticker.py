#!/usr/bin/env python3
"""Treemap dua tingkat Sector -> Ticker untuk Foreign Buy/Sell/Net.
Default periode 5 hari perdagangan. Membaca database daily secara read-only.
Tidak memerlukan library tambahan.
"""
import argparse, csv, sys, subprocess, zipfile, sqlite3, datetime
from pathlib import Path
from collections import defaultdict
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET


def num(v):
    if v is None or str(v).strip()=='':
        return None
    try:
        x=float(v)
        if x!=x or abs(x)==float('inf'):
            return None
        return x
    except Exception:
        return None


def parse_xlsx_sector_map(xlsx_path):
    ns={'a':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(xlsx_path,'r') as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall('a:si',ns):
                texts=[]
                for t in si.iterfind('.//a:t',ns):
                    texts.append(t.text or '')
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
                        else:
                            v=node.text
                vals[col]=v
            rows.append(vals)
        if not rows:
            return {}
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
        total=sum(v['size'] for v in items) or 1
        out=[]; horizontal=w>=h; offset=0.0
        for it in items:
            frac=it['size']/total
            if horizontal:
                rw=w*frac; out.append((x+offset,y,rw,h,it)); offset+=rw
            else:
                rh=h*frac; out.append((x,y+offset,w,rh,it)); offset+=rh
        return out
    total=sum(v['size'] for v in items) or 1
    acc=0.0; idx=max(1,len(items)//2)
    for i,it in enumerate(items):
        if acc+it['size'] >= total/2:
            idx=i+1; break
        acc += it['size']
    if idx>=len(items): idx=max(1,len(items)//2)
    g1=items[:idx]; g2=items[idx:]
    frac=(sum(v['size'] for v in g1)/(total or 1))
    if w>=h:
        w1=w*frac
        return recursive_layout(g1,x,y,w1,h)+recursive_layout(g2,x+w1,y,w-w1,h)
    else:
        h1=h*frac
        return recursive_layout(g1,x,y,w,h1)+recursive_layout(g2,x,y+h1,w,h-h1)


def color_for_value(v, mode='net'):
    if mode=='buy': return '#1976d2'
    if mode=='sell': return '#e07b25'
    return '#2ca02c' if v>=0 else '#d62728' 


def font_size(area):
    if area > 180: return 1.7
    if area > 110: return 1.4
    if area > 65: return 1.15
    if area > 35: return 0.95
    return 0.72


def build_svg(path, sector_layouts, mode_label, period_label, trade_date, mode):
    parts=[
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="950" viewBox="0 0 100 62">',
        '<rect x="0" y="0" width="100" height="62" fill="white"/>',
        '<text x="50" y="2.1" text-anchor="middle" font-size="2.2" font-weight="bold" font-family="Arial">Treemap Dua Tingkat Sector → Ticker</text>',
        f'<text x="50" y="4.2" text-anchor="middle" font-size="1.45" font-family="Arial">Mode: {escape(mode_label)} | Periode default: {escape(period_label)} | Tanggal pasar: {escape(trade_date)}</text>',
        f'<text x="50" y="5.8" text-anchor="middle" font-size="1.15" font-family="Arial">{escape("Biru = Foreign Buy" if mode=="buy" else "Oranye = Foreign Sell" if mode=="sell" else "Hijau = Net Buy | Merah = Net Sell")} | Luas = besar absolut volume</text>'
    ]
    top_offset=7.0
    for sx,sy,sw,sh,sector in sector_layouts:
        y0=sy+top_offset
        # outer box
        parts.append(f'<rect x="{sx:.4f}" y="{y0:.4f}" width="{sw:.4f}" height="{sh:.4f}" fill="#f8fafc" stroke="#d0d7de" stroke-width="0.18"/>')
        # sector header bar
        header_h=min(3.2, max(1.5, sh*0.12))
        parts.append(f'<rect x="{sx:.4f}" y="{y0:.4f}" width="{sw:.4f}" height="{header_h:.4f}" fill="#334155"/>')
        sector_label=sector['sector']
        sector_value=int(sector['metric_value']) if sector['metric_value'] is not None else 0
        parts.append(f'<text x="{sx+0.35:.4f}" y="{y0+header_h*0.7:.4f}" text-anchor="start" font-size="1.05" font-family="Arial" font-weight="bold" fill="white">{escape(sector_label)}</text>')
        parts.append(f'<text x="{sx+sw-0.35:.4f}" y="{y0+header_h*0.7:.4f}" text-anchor="end" font-size="0.95" font-family="Arial" fill="white">{sector_value:,}</text>')
        inner_x=sx+0.15; inner_y=y0+header_h+0.15; inner_w=max(0.1, sw-0.30); inner_h=max(0.1, sh-header_h-0.30)
        if not sector['tickers']:
            continue
        ticker_items=[]
        for tk in sector['tickers']:
            ticker_items.append({'ticker':tk['ticker'],'company':tk['company'],'metric_value':tk['metric_value'],'size':tk['abs_metric']})
        ticker_items=sorted(ticker_items,key=lambda x:x['size'], reverse=True)
        t_layouts=recursive_layout(ticker_items, inner_x, inner_y, inner_w, inner_h)
        for tx,ty,tw,th,t in t_layouts:
            val=t['metric_value'] or 0
            color=color_for_value(val,mode)
            parts.append(f'<rect x="{tx:.4f}" y="{ty:.4f}" width="{tw:.4f}" height="{th:.4f}" fill="{color}" stroke="white" stroke-width="0.15"/>')
            area=tw*th
            if area < 6:
                continue
            fs=font_size(area)
            label=f"{t['ticker']}\n{int(val):,}"
            lines=label.split('\n')
            cx=tx+tw/2; cy=ty+th/2
            for i,line in enumerate(lines):
                dy=(-0.45 + i*0.9)*fs
                parts.append(f'<text x="{cx:.4f}" y="{cy+dy:.4f}" text-anchor="middle" font-size="{fs:.2f}" font-family="Arial" font-weight="bold" fill="white">{escape(line)}</text>')
    parts.append('</svg>')
    path.write_text(''.join(parts), encoding='utf-8')


def available_dates(conn):
    return [r[0] for r in conn.execute('SELECT DISTINCT trade_date FROM daily ORDER BY trade_date DESC')]


def choose_dates(available, opts):
    if opts.dates:
        chosen=[x.strip() for x in opts.dates.split(',') if x.strip()]
    elif opts.end_date:
        datetime.date.fromisoformat(opts.end_date)
        chosen=[d for d in available if d<=opts.end_date][:opts.period]
    elif opts.interactive:
        print('\nTanggal tersedia di database (terbaru di atas):')
        for idx,d in enumerate(available,1):
            print(f'{idx:>3}. {d}')
        print('\nPilih cara:')
        print(f'1. {opts.period} sesi sampai tanggal akhir pilihan')
        print(f'2. {opts.period} tanggal bebas (tidak harus berurutan)')
        mode=input('Pilihan [1/2]: ').strip()
        if mode=='1':
            end_date=input('Tanggal akhir (YYYY-MM-DD): ').strip()
            datetime.date.fromisoformat(end_date)
            chosen=[d for d in available if d<=end_date][:opts.period]
        elif mode=='2':
            entered=input(f'Masukkan {opts.period} tanggal dipisah koma (YYYY-MM-DD): ').strip()
            chosen=[x.strip() for x in entered.split(',') if x.strip()]
        else:
            raise ValueError('Pilihan tidak dikenali')
    else:
        # fallback for automated update: latest N sessions
        chosen=available[:opts.period]
    if len(chosen)!=opts.period:
        raise ValueError(f'Harus tepat {opts.period} tanggal; diperoleh {len(chosen)}')
    if len(set(chosen))!=len(chosen):
        raise ValueError('Tanggal tidak boleh duplikat')
    for d in chosen:
        datetime.date.fromisoformat(d)
    missing=sorted(set(chosen)-set(available))
    if missing:
        raise ValueError('Tanggal tidak ditemukan dalam database: '+', '.join(missing))
    return sorted(chosen)


def main():
    p=argparse.ArgumentParser(description='Treemap Sector -> Ticker dengan mode Buy/Sell/Net dan periode dinamis')
    p.add_argument('--db',default='pasar_bei_prototipe.db')
    p.add_argument('--sector-file',default='Daftar Saham  sektor.xlsx')
    p.add_argument('--output',default='output_treemap')
    p.add_argument('--period',type=int,default=5,choices=[1,5,10,20])
    p.add_argument('--mode',default='net',choices=['net','buy','sell'])
    g=p.add_mutually_exclusive_group()
    g.add_argument('--dates',help='Daftar tanggal eksplisit, pisahkan dengan koma, mis. 2026-10-06,2026-10-07,...')
    g.add_argument('--end-date',help='Ambil N sesi tersedia hingga tanggal ini (YYYY-MM-DD)')
    g.add_argument('--interactive',action='store_true',help='Pilih tanggal dengan menu interaktif')
    args=p.parse_args()
    db=Path(args.db)
    if not db.is_file():
        raise FileNotFoundError('Database tidak ditemukan: '+str(db))
    conn=sqlite3.connect('file:'+str(db.resolve())+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    try:
        dates=choose_dates(available_dates(conn),args)
        sector_map=parse_xlsx_sector_map(args.sector_file)
        placeholders=','.join('?' for _ in dates)
        records=conn.execute('SELECT trade_date,ticker,company,close,previous,value,foreign_buy,foreign_sell FROM daily WHERE trade_date IN ('+placeholders+')',dates).fetchall()
        aggregate={}
        for r in records:
            ticker=str(r['ticker']).strip().upper()
            if not ticker: continue
            entry=aggregate.setdefault(ticker,{'ticker':ticker,'company':r['company'] or '', 'sector':sector_map.get(ticker,'Unknown'),'buy':0,'sell':0,'net':0,'sessions':set(),'close':None,'previous':None,'value':0})
            if r['trade_date'] in entry['sessions']:
                raise ValueError('Duplikasi baris pasar: '+ticker+' '+r['trade_date'])
            entry['sessions'].add(r['trade_date'])
            buy=num(r['foreign_buy'])
            sell=num(r['foreign_sell'])
            if buy is None or sell is None: raise ValueError(f'Data foreign kosong/tidak numerik pada {ticker} {r["trade_date"]}')
            entry['buy']+=buy
            entry['sell']+=sell
            entry['net']+=buy-sell
            if r['trade_date']==dates[-1]:
                entry['close']=num(r['close']);entry['previous']=num(r['previous'])
            entry['value']+=num(r['value']) or 0
        rows=[]
        for ticker,entry in aggregate.items():
            if len(entry['sessions'])!=len(dates):
                # Do not silently label an incomplete ticker as a full N-day period.
                continue
            close=entry['close']; prev=entry['previous']
            metric=entry[args.mode]
            rows.append({'ticker':ticker,'company':entry['company'],'sector':entry['sector'], 'metric_value':round(metric), 'abs_metric':abs(metric), 'close_idr':close,'change_pct':100*(close/prev-1) if close is not None and prev and prev>0 else None,'value_idr':entry['value'],'data_quality':'OK'})
        if not rows: raise ValueError('Tidak ada ticker dengan data lengkap pada seluruh tanggal yang dipilih')
        by_sector=defaultdict(list)
        for row in rows: by_sector[row['sector']].append(row)
        sectors=[]; detail=[]
        for sector,items in by_sector.items():
            net=sum(x['metric_value'] for x in items)
            magnitude=sum(x['abs_metric'] for x in items)
            ranked=sorted(items,key=lambda x:x['abs_metric'],reverse=True)
            sectors.append({'sector':sector,'ticker_count':len(items),'metric_value':net,'abs_total':magnitude,'top_tickers':', '.join(x['ticker'] for x in ranked[:5])})
            detail.extend([{'sector':sector,'ticker':x['ticker'],'company':x['company'],'metric_value':x['metric_value'],'close_idr':x['close_idr'],'change_pct':x['change_pct'],'value_idr':x['value_idr'],'data_quality':x['data_quality']} for x in ranked])
        sectors=sorted(sectors,key=lambda x:x['abs_total'],reverse=True)
        sector_items=[]
        for s in sectors:
            tickers=[x for x in by_sector[s['sector']] if x['abs_metric']>0]
            if not tickers: continue
            sector_items.append({'sector':s['sector'],'metric_value':s['metric_value'],'size':s['abs_total'],'tickers':tickers})
        if not sector_items: raise ValueError('Seluruh nilai foreign untuk mode pilihan = 0 pada tanggal terpilih')
        treemap_layout=recursive_layout(sector_items,0,0,100,55)
        out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
        label='Tanggal pilihan: '+', '.join(dates)
        mode_filename={'net':'Net','buy':'Buy','sell':'Sell'}[args.mode]
        mode_label={'net':'Foreign Net Buy/Sell','buy':'Foreign Buy','sell':'Foreign Sell'}[args.mode]
        suffix=f'{args.period}D'
        svg=out/f'Treemap_Sector_Ticker_Foreign_{mode_filename}_{suffix}.svg'
        build_svg(svg,treemap_layout,mode_label,label,dates[-1],args.mode)
        summary=out/f'Sector_Treemap_Summary_Foreign_{mode_filename}_{suffix}.csv'
        details=out/f'Sector_Treemap_Detail_Foreign_{mode_filename}_{suffix}.csv'
        for path,headers,data in [
            (summary,['sector','ticker_count','metric_value','abs_total','top_tickers'],sectors),
            (details,['sector','ticker','company','metric_value','close_idr','change_pct','value_idr','data_quality'],detail)]:
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=headers)
                writer.writeheader();writer.writerows(data)
        (out/f'Tanggal_Terpilih_{mode_filename}_{suffix}.txt').write_text('\n'.join(dates)+'\n',encoding='utf-8')
        print('BERHASIL | Mode:',mode_label,'| Periode:',args.period,'| Tanggal:',', '.join(dates),'| Saham lengkap:',len(rows),'| Sektor:',len(sectors))
        print('Treemap:',svg,'| CSV:',summary)
        print('Catatan: data tanpa kelengkapan semua tanggal pilihan tidak diikutkan; nilai berbasis volume saham.')
    finally:
        conn.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('GAGAL:', e, file=sys.stderr)
        sys.exit(1)
