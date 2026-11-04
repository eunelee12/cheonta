import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import strokes


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
        account = self.request(student,'register',profile)
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
                self.assertEqual(prompt['text'], '나무')
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
        for index in range(5):
            prompt = self.request(student,'start',{'mode':'competition','new':index==0})
            self.assertEqual(prompt['number'],index+1)
            result = self.request(student,'submit',{'text':prompt['text']})
            self.assertEqual(result['finished'],index==4)
        self.assertEqual(len(self.request(student,'rankings')['competition']),1)
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
        self.assertEqual(self.request(teacher,'rankings')['competition'],[])
        self.request(teacher,'logout',{})
        self.request(teacher,'admin/students',status=401)

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
