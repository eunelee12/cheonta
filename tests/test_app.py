import base64
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import strokes, PRACTICE_SETS


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.url = f'http://127.0.0.1:{port}'
        cls.proc = subprocess.Popen([sys.executable, 'server.py'], cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'CHEONTA_DB':str(Path(cls.tmp.name)/'test.sqlite3'),
                 'CHEONTA_ADMIN_PASSWORD':'test-admin-only', 'PORT':str(port), 'HOST':'127.0.0.1'},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.public = cls.client()
        for _ in range(100):
            try:
                cls.public.open(cls.url, timeout=1).close()
                break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError('Server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        cls.tmp.cleanup()

    @staticmethod
    def client():
        return urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, client, path, data=None, status=200):
        req = urllib.request.Request(self.url+'/api/'+path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type':'application/json'})
        try:
            response = client.open(req)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            result = json.load(response)
            self.assertEqual(response.status, status, result)
            return result

    def test_workflow(self):
        student, teacher, other = self.client(), self.client(), self.client()
        profile = {'class_name':'1학년 2반','name':'테스트 학생','pin':'0123'}
        self.request(student,'register',{**profile,'pin':'123'},400)
        self.request(student,'register',profile,400)
        self.request(student,'admin/create',profile,400)
        self.request(teacher,'admin/login',{'password':'test-admin-only'})
        created = self.request(teacher,'admin/create',profile)
        self.request(teacher,'admin/create',profile,409)
        self.request(teacher,'admin/create',{'class_name':'','name':'누락'},400)
        self.request(other,'login',profile,400)
        self.request(other,'roster/search',{},400)
        matches = self.request(other,'roster/search',{'class_name':'2반','name':'테스트'})
        self.assertEqual(matches,[{'id':created['id'],'class_name':profile['class_name'],'name':profile['name']}])
        self.assertEqual(self.request(other,'roster/search',{'name':'없는 학생'}),[])
        self.assertFalse(self.request(teacher,'admin/students')[0]['activated'])
        for pin in ('123','12345','abcd','１２３４'):
            self.request(student,'register',{**profile,'pin':pin},400)
        account = self.request(student,'register',profile)
        self.assertEqual(account['id'],created['id'])
        self.assertTrue(self.request(teacher,'admin/students')[0]['activated'])
        self.assertEqual(self.request(other,'roster/search',{'name':'테스트'}),[])
        self.request(other,'register',{**profile,'pin':'9999'},400)
        self.request(other,'login',{**profile,'pin':'9999'},400)
        self.request(other,'login',profile)
        self.assertEqual(self.request(other,'me')['name'], profile['name'])
        self.request(student,'admin/students',status=401)
        self.request(student,'submit',{'text':'abc'},400)
        prompt = self.request(student,'start',{'mode':'practice'})
        failed = self.request(student,'submit',{'text':'오답'})
        self.assertFalse(failed['eligible'])
        self.assertEqual(self.request(student,'rankings')['students'], [])
        retry = self.request(student,'start',{'retry':True})
        self.assertEqual(prompt['text'],retry['text'])
        result = self.request(student,'submit',{'text':retry['text']})
        self.assertTrue(result['eligible'])
        self.assertEqual(result['accuracy'],100)
        rows = self.request(student,'records')
        self.assertEqual(len(rows),2)
        self.assertEqual(sum(r['eligible'] for r in rows),1)
        ranks = self.request(student,'rankings')
        self.assertEqual(ranks['students'][0]['speed'],result['speed'])
        self.assertEqual(ranks['classes'][0]['count'],1)
        self.assertEqual(ranks['classes'][0]['speed'],result['speed'])
        for kind in ('keys', 'words'):
            prompt = self.request(student,'start',{'mode':'practice','practice_type':kind})
            if kind == 'keys':
                self.assertEqual(prompt['text'], 'ㅁ ㄴ ㅇ ㄹ')
            else:
                self.assertIn((prompt['category'],prompt['text']), PRACTICE_SETS['words'])
            wrong = self.request(student,'submit',{'text':'오답'})
            self.assertFalse(wrong['eligible'])
            retry = self.request(student,'start',{'mode':'practice','practice_type':kind,'retry':True})
            self.assertEqual(retry['text'], prompt['text'])
            self.assertTrue(self.request(student,'submit',{'text':retry['text']})['eligible'])
            record = self.request(student,'records')[0]
            self.assertEqual(record['mode'], kind)
            following = self.request(student,'start',{'mode':'practice','practice_type':kind})
            self.assertNotEqual(following['text'], prompt['text'])
        self.request(student,'start',{'practice_type':'unknown'},400)
        self.request(student,'start',{'mode':'competition'},400)
        before = self.request(student,'rankings')
        with sqlite3.connect(Path(self.tmp.name)/'test.sqlite3') as db:
            db.execute("INSERT INTO records(student_id,sentence,speed,accuracy,eligible,mode) VALUES(?,?,?,100,1,'competition')", (account['id'],'이전 대회',99999))
        self.assertEqual(self.request(student,'rankings'),before)
        self.assertNotIn('competition',before)
        eligible_records = [r for r in self.request(student,'records') if r['eligible'] and r['mode'] in ('practice','keys','words')]
        self.assertAlmostEqual(before['students'][0]['speed'],sum(r['speed'] for r in eligible_records)/len(eligible_records))
        self.request(teacher,'admin/login',{'password':'wrong'},400)
        self.request(teacher,'admin/login',{'password':'test-admin-only'})
        self.assertEqual(len(self.request(teacher,'admin/students')),1)
        updated = {**profile,'id':account['id'],'name':'새 이름','pin':'4567'}
        self.request(teacher,'admin/update',updated)
        self.request(student,'me',status=401)
        self.request(other,'login',profile,400)
        self.request(other,'login',updated)
        self.assertEqual(self.request(other,'me')['name'],'새 이름')
        self.request(teacher,'admin/delete',{'id':account['id']})
        self.request(other,'me',status=401)
        self.assertEqual(self.request(teacher,'admin/students'),[])
        self.assertEqual(self.request(teacher,'rankings')['students'],[])
        self.request(teacher,'logout',{})
        self.request(teacher,'admin/students',status=401)

    def test_activity_totals(self):
        teacher, first, second = self.client(), self.client(), self.client()
        self.request(teacher,'admin/login',{'password':'test-admin-only'})
        accounts=[]
        for client,name in ((first,'시간학생1'),(second,'시간학생2')):
            profile={'class_name':'시간반','name':name,'pin':'0123'}
            accounts.append(self.request(teacher,'admin/create',profile)['id'])
            self.request(client,'register',profile)
        total=0
        ids=[]
        for kind,ms in (('keys',12000),('words',25000),('short',63000)):
            prompt=self.request(first,'start',{'practice_type':kind})
            aid=prompt['activity_id'];ids.append(aid)
            with sqlite3.connect(Path(self.tmp.name)/'test.sqlite3') as db:
                db.execute('UPDATE practice_activity SET started=started-200 WHERE id=?',(aid,))
            self.request(first,'activity',{'activity_id':aid,'active_ms':ms})
            self.request(first,'activity',{'activity_id':aid,'active_ms':ms})
            self.request(first,'activity',{'activity_id':aid,'active_ms':ms-1})
            total+=ms
        # Time includes incomplete and incorrect practice; speed ranking still requires 100% accuracy.
        self.request(first,'submit',{'text':'오답'})
        rows=self.request(first,'rankings')
        self.assertEqual(rows['students'][0]['active_ms'],total)
        self.assertIsNone(rows['students'][0]['speed'])
        prompt=self.request(second,'start',{'practice_type':'keys'})
        with sqlite3.connect(Path(self.tmp.name)/'test.sqlite3') as db:
            db.execute('UPDATE practice_activity SET started=started-60 WHERE id=?',(prompt['activity_id'],))
        self.request(second,'activity',{'activity_id':prompt['activity_id'],'active_ms':40000})
        self.request(second,'activity',{'activity_id':ids[0],'active_ms':1},400)
        for bad in (-1,True,'100',float('inf'),10**20):
            self.request(first,'activity',{'activity_id':ids[0],'active_ms':bad},400)
        fresh=self.request(first,'start',{'practice_type':'keys'})
        self.request(first,'activity',{'activity_id':fresh['activity_id'],'active_ms':100000},400)
        self.request(teacher,'activity',{'activity_id':ids[0],'active_ms':1},400)
        rows=self.request(first,'rankings')
        group=next(r for r in rows['classes'] if r['name']=='시간반')
        self.assertEqual(group['active_ms'],total+40000)
        self.assertEqual(group['count'],2)
        # No record/activity join multiplication when this student also has multiple correct records.
        for _ in range(2):
            text=self.request(first,'start',{'practice_type':'words'})['text']
            self.request(first,'submit',{'text':text})
        self.assertEqual(self.request(first,'rankings')['classes'][0]['active_ms'],total+40000)
        self.request(first,'logout',{})
        self.request(first,'login',{'class_name':'시간반','name':'시간학생1','pin':'0123'})
        self.assertEqual(self.request(first,'rankings')['students'][0]['active_ms'],total)
        for sid in accounts:
            self.request(teacher,'admin/delete',{'id':sid})

    def test_individual_rankings_top_100(self):
        teacher = self.client()
        self.request(teacher,'admin/login',{'password':'test-admin-only'})
        ids=[]
        try:
            with sqlite3.connect(Path(self.tmp.name)/'test.sqlite3') as db:
                for index in range(105):
                    sid=db.execute("INSERT INTO students(class_name,name,salt,password) VALUES('공개범위반',?,'','')",(f'공개학생{index:03}',)).lastrowid
                    ids.append(sid)
                    # A tie across the 100th boundary must still expose at most 100 people.
                    speed=500-index if index<99 else 400
                    db.execute("INSERT INTO records(student_id,sentence,speed,accuracy,eligible,mode) VALUES(?,'연습',?,100,1,'words')",(sid,speed))
                    db.execute("INSERT INTO practice_activity(id,student_id,practice_type,active_ms,started) VALUES(?,?,'keys',1000,0)",(f'top100-{sid}',sid))
            result=self.request(teacher,'rankings')
            self.assertEqual(len(result['students']),100)
            self.assertEqual([r['id'] for r in result['students']],ids[:100])
            self.assertFalse(set(ids[100:]) & {r['id'] for r in result['students']})
            group=next(r for r in result['classes'] if r['name']=='공개범위반')
            self.assertEqual(group['count'],105)
            self.assertEqual(group['active_ms'],105000)
            self.assertAlmostEqual(group['speed'],(sum(500-i for i in range(99))+400*6)/105)
            self.assertEqual(len(self.request(teacher,'admin/students')),105)
        finally:
            with sqlite3.connect(Path(self.tmp.name)/'test.sqlite3') as db:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute("DELETE FROM students WHERE class_name='공개범위반'")

    def test_roster_import(self):
        from test_roster import filled_template
        teacher, student = self.client(), self.client()
        self.request(teacher,'admin/login',{'password':'test-admin-only'})
        self.request(student,'admin/roster-template',status=401)
        self.request(student,'admin/import',{'filename':'x.csv','content':''},400)
        with teacher.open(self.url+'/api/admin/roster-template') as response:
            self.assertIn('spreadsheetml',response.headers['Content-Type'])
            self.assertTrue(response.read().startswith(b'PK'))
        def upload(name, content, status=200):
            return self.request(teacher,'admin/import',{'filename':name,'content':base64.b64encode(content).decode()},status)
        result = upload('a.csv','반,이름\n파일반,파일학생\n파일반,파일학생\n'.encode('utf-8-sig'))
        self.assertEqual(result,{'added':1,'skipped':1,'total':2})
        profile={'class_name':'파일반','name':'파일학생','pin':'0123'}
        account = self.request(student,'register',profile)
        upload('a.csv','반,이름\n파일반,파일학생\n'.encode())
        self.request(student,'login',profile)
        upload('a.csv','반,이름\n파일반,추가되면안됨\n파일반,\n'.encode(),400)
        self.assertEqual(self.request(student,'roster/search',{'name':'추가되면안됨'}),[])
        self.assertEqual(upload('a.xlsx',filled_template())['added'],1)
        rows = self.request(teacher,'admin/students')
        imported = next(r for r in rows if r['name']=='김하늘')
        self.assertFalse(imported['activated'])
        for sid in (account['id'],imported['id']):
            self.request(teacher,'admin/delete',{'id':sid})

    def test_strokes(self):
        self.assertEqual(strokes('가'),2)
        self.assertEqual(strokes('각'),3)
        self.assertEqual(strokes('값'),4)
        self.assertEqual(strokes('꽤'),4)
        self.assertEqual(strokes('a .'),3)

    def test_static_and_access(self):
        for path, fragment in [('/', '천타'),('/app.js','compositionend'),('/style.css','@media')]:
            with self.public.open(self.url+path) as response:
                self.assertIn(fragment,response.read().decode())
        self.request(self.public,'me',status=401)


if __name__ == '__main__':
    unittest.main()
