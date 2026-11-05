import base64
import io
import sys
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roster import parse_roster, template


def encoded(data):
    return base64.b64encode(data).decode()


def filled_template():
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template())) as source, zipfile.ZipFile(output,'w') as dest:
        for name in source.namelist():
            content = source.read(name)
            if name.endswith('sheet1.xml'):
                content = content.replace(b'</sheetData>', '<row r="2"><c r="A2" t="inlineStr"><is><t>3반</t></is></c><c r="B2" t="inlineStr"><is><t>김하늘</t></is></c></row></sheetData>'.encode())
            dest.writestr(name, content)
    return output.getvalue()


class RosterTest(unittest.TestCase):
    def test_template_and_excel(self):
        with self.assertRaisesRegex(ValueError,'학생의 반과 이름'):
            parse_roster('명단.xlsx',encoded(template()))
        self.assertEqual(parse_roster('명단.xlsx',encoded(filled_template())), [('3반','김하늘')])

    def test_csv_encodings_and_validation(self):
        for encoding in ('utf-8-sig','cp949'):
            self.assertEqual(parse_roster('명단.CSV',encoded('반,이름\n 3반 , 김하늘 \n\n'.encode(encoding))), [('3반','김하늘')])
        for data in ('이름,반\n홍길동,1반', '반,이름\n3반,', '반,이름\n3반,학생,추가', '반,이름\n3반,'+'가'*31):
            with self.assertRaises(ValueError):
                parse_roster('a.csv',encoded(data.encode()))
        for name, data in [('a.xls',b'bad'),('a.xlsx',b'bad'),('a.csv',b'x'*(1024*1024+1))]:
            with self.assertRaises(ValueError):
                parse_roster(name, encoded(data))
        with self.assertRaises(ValueError):
            parse_roster('a.csv','invalid base64!')
        with self.assertRaisesRegex(ValueError,'2,000'):
            parse_roster('a.csv',encoded(('반,이름\n'+'1반,학생\n'*2001).encode()))

if __name__ == '__main__':
    unittest.main()
