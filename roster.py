"""CSV / XLSX roster files using only the Python standard library."""
import base64
import binascii
import csv
import io
import posixpath
import zipfile
from xml.etree import ElementTree as ET

MAX_FILE_SIZE = 1024 * 1024
MAX_ROWS = 2000
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def template():
    files = {
        '[Content_Types].xml': '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''',
        '_rels/.rels': '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''',
        'xl/workbook.xml': '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="학생 명단" sheetId="1" r:id="rId1"/></sheets></workbook>''',
        'xl/_rels/workbook.xml.rels': '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''',
        'xl/worksheets/sheet1.xml': '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="1" max="2" width="24" customWidth="1"/></cols><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>반</t></is></c><c r="B1" t="inlineStr"><is><t>이름</t></is></c></row></sheetData></worksheet>''',
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, '<?xml version="1.0" encoding="UTF-8"?>' + content)
    return output.getvalue()


def excel_rows(content):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if len(archive.infolist()) > 200 or sum(f.file_size for f in archive.infolist()) > 10 * MAX_FILE_SIZE:
                raise ValueError('엑셀 파일의 압축 해제 크기가 너무 큽니다.')
            def xml(path):
                raw = archive.read(path)
                if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                    raise ValueError('지원하지 않는 XML 형식입니다.')
                return ET.fromstring(raw)
            workbook = xml('xl/workbook.xml')
            sheet = workbook.find('s:sheets/s:sheet', NS)
            if sheet is None:
                raise ValueError('엑셀에 시트가 없습니다.')
            rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            rel = next((r for r in xml('xl/_rels/workbook.xml.rels') if r.get('Id') == rid), None)
            if rel is None or rel.get('TargetMode') == 'External':
                raise ValueError('첫 번째 시트를 읽을 수 없습니다.')
            target = rel.get('Target', '')
            path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
            if not path.startswith('xl/'):
                raise ValueError('시트 경로가 올바르지 않습니다.')
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(t.text or '' for t in si.findall('.//s:t', NS)) for si in xml('xl/sharedStrings.xml')]
            rows = []
            for row in xml(path).findall('s:sheetData/s:row', NS):
                values = {}
                for cell in row.findall('s:c', NS):
                    ref = cell.get('r', '')
                    column = ''.join(c for c in ref if c.isalpha())
                    if column not in ('A', 'B'):
                        continue
                    if cell.find('s:f', NS) is not None:
                        raise ValueError(f"{ref}: 수식 대신 반과 이름을 직접 입력해 주세요.")
                    value = cell.findtext('s:v', '', NS)
                    if cell.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.get('t') == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('s:is//s:t', NS)) if cell.find('s:is', NS) is not None else ''
                    values[column] = value
                rows.append((row.get('r', str(len(rows)+1)), [values.get('A',''),values.get('B','')]))
            return rows
    except (zipfile.BadZipFile, KeyError, ET.ParseError, IndexError, TypeError, RuntimeError, NotImplementedError) as exc:
        raise ValueError('엑셀 파일을 읽을 수 없습니다. 양식을 내려받아 .xlsx로 저장해 주세요.') from exc


def parse_roster(filename, encoded):
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error, TypeError) as exc:
        raise ValueError('업로드 파일을 읽을 수 없습니다.') from exc
    if len(content) > MAX_FILE_SIZE:
        raise ValueError('파일은 1MB 이하로 업로드해 주세요.')
    if filename.lower().endswith('.xlsx'):
        rows = excel_rows(content)
    elif filename.lower().endswith('.csv'):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = content.decode('cp949')
            except UnicodeDecodeError as exc:
                raise ValueError('CSV 파일을 UTF-8 형식으로 저장해 주세요.') from exc
        try:
            rows = list(enumerate(csv.reader(io.StringIO(text), strict=True), 1))
        except csv.Error as exc:
            raise ValueError('CSV 형식을 확인해 주세요.') from exc
    else:
        raise ValueError('.xlsx 또는 .csv 파일을 선택해 주세요. .xls는 .xlsx로 저장해 주세요.')
    rows = [(number, [v.strip() for v in values]) for number, values in rows if any(v.strip() for v in values)]
    if not rows or rows[0][1] != ['반','이름']:
        raise ValueError('첫 행은 A열 «반», B열 «이름»이어야 합니다.')
    if len(rows)-1 > MAX_ROWS:
        raise ValueError('한 번에 최대 2,000명까지 등록할 수 있습니다.')
    students = []
    for number, values in rows[1:]:
        if len(values) != 2 or not all(values) or max(map(len, values)) > 30:
            raise ValueError(f'{number}행: 반과 이름을 각각 1~30자로 입력해 주세요. 아무 학생도 추가하지 않았습니다.')
        students.append(tuple(values))
    if not students:
        raise ValueError('양식에 학생의 반과 이름을 입력한 뒤 업로드해 주세요.')
    return students
