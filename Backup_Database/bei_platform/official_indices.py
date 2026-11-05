"""Read BEI Ringkasan Indeks Excel files from IHSG/ and store in separate SQLite.
Uses Python standard library only; does not modify market/portfolio databases.
"""
import datetime as dt
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FOLDER = BASE / 'IHSG'
INDEX_DB = BASE / 'market_indices.db'
FILE_RE = re.compile(r'^Ringkasan\s+Indeks\s*[-_ ]\s*(\d{8})\.xlsx$', re.I)
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def parse_xlsx(path):
    """Read first worksheet from a normal non-encrypted xlsx (values, not formulas)."""
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            strings=[''.join(t.text or '' for t in si.findall('.//m:t',NS)) for si in root.findall('m:si',NS)]
        book=ET.fromstring(z.read('xl/workbook.xml'))
        first=book.find('m:sheets/m:sheet',NS)
        if first is None:raise ValueError('Worksheet tidak ditemukan')
        relid=first.get('{%s}id'%NS['r'])
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target=None
        for rel in rels:
            if rel.get('Id')==relid:target=rel.get('Target');break
        if not target:raise ValueError('Relasi worksheet tidak ditemukan')
        target=target.lstrip('/')
        sheet_path=target if target.startswith('xl/') else 'xl/'+target
        root=ET.fromstring(z.read(sheet_path))
        output=[]
        for row in root.findall('.//m:sheetData/m:row',NS):
            result={}
            for cell in row.findall('m:c',NS):
                cref=cell.get('r','A');letters=re.match('[A-Z]+',cref)
                if not letters:continue
                col=0
                for c in letters.group():col=col*26+ord(c)-64
                val=cell.find('m:v',NS)
                if cell.get('t')=='inlineStr':
                    value=''.join(x.text or '' for x in cell.findall('.//m:t',NS))
                elif val is None:value=None
                elif cell.get('t')=='s':value=strings[int(val.text)]
                elif cell.get('t') in ('str','e'):value=val.text
                else:
                    try:value=float(val.text)
                    except (TypeError,ValueError):value=val.text
                result[col-1]=value
            if result:output.append(result)
        return output


def numeric(v):
    if isinstance(v,(int,float)):return float(v)
    if v is None or str(v).strip()=='':return None
    s=str(v).strip().replace(' ','')
    if ',' in s and '.' in s:s=s.replace('.','').replace(',','.') if s.rfind(',')>s.rfind('.') else s.replace(',','')
    elif ',' in s:s=s.replace(',','.')
    try:return float(s)
    except ValueError:return None


def parse_file(path):
    m=FILE_RE.match(path.name)
    if not m:raise ValueError(f'Nama file bukan Ringkasan Indeks-YYYYMMDD.xlsx: {path.name}')
    day=dt.datetime.strptime(m.group(1),'%Y%m%d').date().isoformat()
    cells=parse_xlsx(path)
    if not cells:raise ValueError('Workbook kosong')
    header=None
    for i,row in enumerate(cells[:20]):
        content={str(v).strip().lower():col for col,v in row.items() if isinstance(v,str)}
        if 'kode indeks' in content and 'penutupan' in content:
            header=(i,content);break
    if header is None:raise ValueError('Header Kode Indeks/Penutupan tidak ditemukan')
    ix,cols=header
    mapping={'index_code':'kode indeks','previous':'sebelumnya','high':'tertinggi','low':'terendah','close':'penutupan',
             'volume':'volume','value':'nilai','frequency':'frekuensi','market_cap':'kapitalisasi pasar*'}
    parsed=[]
    for row in cells[ix+1:]:
        code=str(row.get(cols['kode indeks'],'') or '').strip().upper()
        if not code or code in ('NONE','TOTAL'):continue
        v={key:numeric(row.get(cols[name])) if name in cols else None for key,name in mapping.items() if key!='index_code'}
        if v['close'] is None:continue
        parsed.append((day,code,v['previous'],v['high'],v['low'],v['close'],v['volume'],v['value'],v['frequency'],v['market_cap'],path.name))
    if not parsed:raise ValueError('Tidak ada indeks dengan nilai Penutupan valid')
    if not any(r[1]=='COMPOSITE' for r in parsed):raise ValueError('Kode COMPOSITE (IHSG) tidak ditemukan')
    return parsed


def import_folder(folder=FOLDER, database=INDEX_DB):
    folder=Path(folder);database=Path(database)
    if not folder.is_dir():return {'files':0,'imported':0,'unchanged':0,'errors':[f'Folder belum ditemukan: {folder}']}
    paths=sorted(p for p in folder.iterdir() if p.is_file() and FILE_RE.match(p.name))
    report={'files':len(paths),'imported':0,'unchanged':0,'errors':[],'dates':[]}
    # Parse BEFORE opening DB transaction; one invalid file must not block other dates.
    parsed=[]
    for p in paths:
        try:parsed.append((p,parse_file(p)))
        except Exception as e:report['errors'].append(f'{p.name}: {e}')
    if not parsed:return report
    with sqlite3.connect(database) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS market_indices (
            trade_date TEXT NOT NULL, index_code TEXT NOT NULL,
            previous REAL, high REAL, low REAL, close REAL NOT NULL,
            volume REAL, value REAL, frequency REAL, market_cap REAL,
            source_file TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(trade_date,index_code))''')
        con.execute('CREATE INDEX IF NOT EXISTS ix_market_indices_code_day ON market_indices(index_code,trade_date)')
        for path,records in parsed:
            try:
                con.execute('SAVEPOINT one_file')
                # Replace an entire date, so removed/changed index codes cannot stay stale.
                con.execute('DELETE FROM market_indices WHERE trade_date=?',(records[0][0],))
                con.executemany('''INSERT INTO market_indices(trade_date,index_code,previous,high,low,close,volume,value,frequency,market_cap,source_file)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)''',records)
                con.execute('RELEASE one_file')
                report['imported']+=len(records);report['dates'].append(records[0][0])
            except Exception as e:
                con.execute('ROLLBACK TO one_file');con.execute('RELEASE one_file')
                report['errors'].append(f'{path.name}: {e}')
    return report


def index_history(code='COMPOSITE',database=INDEX_DB):
    if not Path(database).exists():return []
    with sqlite3.connect(database) as con:
        try:rows=con.execute('SELECT trade_date, close FROM market_indices WHERE index_code=? ORDER BY trade_date',(code,)).fetchall()
        except sqlite3.OperationalError:return []
    return [{'date':r[0],'close':r[1]} for r in rows]


def index_codes(database=INDEX_DB):
    if not Path(database).exists():return []
    with sqlite3.connect(database) as con:
        try:return [r[0] for r in con.execute('SELECT DISTINCT index_code FROM market_indices ORDER BY index_code')]
        except sqlite3.OperationalError:return []


def start_date(period,end):
    end=dt.date.fromisoformat(end)
    if period=='All':return '0001-01-01'
    if period=='YTD':return f'{end.year}-01-01'
    years=int(period.rstrip('Y'))
    try:d=end.replace(year=end.year-years)
    except ValueError:d=end.replace(year=end.year-years,day=28)
    return d.isoformat()
