"""천타: dependency-free classroom typing application."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DB = Path(os.environ.get('CHEONTA_DB', ROOT / 'data/cheonta.sqlite3'))
ADMIN_PASSWORD = os.environ.get('CHEONTA_ADMIN_PASSWORD', '')
SESSIONS = {}
ATTEMPTS = {}
TEXTS = [
 ('긍정의 말', '작은 한 걸음이 모여 큰 변화를 만듭니다.'),
 ('속담', '천 리 길도 한 걸음부터.'),
 ('좋은 글귀', '서로의 다름을 존중할 때 함께 성장합니다.'),
 ('명언', '아는 것이 힘이다.'),
 ('긍정의 말', '어제보다 조금 나아진 오늘의 나를 응원해요.'),
 ('속담', '가는 말이 고와야 오는 말이 곱다.'),
 ('좋은 글귀', '실수는 배움으로 가는 길 위의 작은 표지판입니다.'),
 ('명언', '너 자신을 알라.'),
 ('긍정의 말', '나만의 속도로 꾸준히 나아가도 괜찮아요.'),
 ('속담', '티끌 모아 태산.'),
 ('좋은 글귀', '따뜻한 말 한마디가 누군가의 하루를 밝힙니다.'),
 ('명언', '배우고 때때로 익히면 또한 기쁘지 아니한가.'),
 ('긍정의 말', '오늘의 도전이 내일의 자신감이 됩니다.'),
 ('속담', '백지장도 맞들면 낫다.'),
 ('좋은 글귀', '꿈은 매일의 작은 노력 속에서 자랍니다.'),
 ('명언', '시작이 반이다.'),
]


PRACTICE_SETS = {
    'short': TEXTS,
    'keys': [
        ('기본 자리 · 왼손', 'ㅁ ㄴ ㅇ ㄹ'),
        ('기본 자리 · 오른손', 'ㅎ ㅗ ㅓ ㅏ ㅣ'),
        ('윗자리 · 자음', 'ㅂ ㅈ ㄷ ㄱ ㅅ'),
        ('윗자리 · 모음', 'ㅛ ㅕ ㅑ ㅐ ㅔ'),
        ('아랫자리', 'ㅋ ㅌ ㅊ ㅍ ㅠ ㅜ ㅡ'),
        ('기본 자리 반복', 'ㅁ ㅏ ㄴ ㅓ ㅇ ㅗ ㄹ ㅣ'),
        ('자음 익히기', 'ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ'),
        ('모음 익히기', 'ㅏ ㅑ ㅓ ㅕ ㅗ ㅛ ㅜ ㅠ ㅡ ㅣ'),
    ],
    'words': [
        ('쉬운 단어', '나무'), ('쉬운 단어', '하늘'),
        ('쉬운 단어', '바다'), ('쉬운 단어', '마음'),
        ('받침 있는 단어', '학교'), ('받침 있는 단어', '친구'),
        ('받침 있는 단어', '연필'), ('받침 있는 단어', '도전'),
        ('긴 단어', '도서관'), ('긴 단어', '무지개'),
        ('긴 단어', '자신감'), ('긴 단어', '배려심'),
        ('복합 모음', '괜찮아'), ('복합 모음', '계획'),
        ('겹받침', '맑음'), ('겹받침', '읽기'),
    ],
}


def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, class_name TEXT NOT NULL,
          name TEXT NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL,
          UNIQUE(class_name,name));
        CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL
          REFERENCES students(id) ON DELETE CASCADE, sentence TEXT NOT NULL, speed REAL NOT NULL,
          accuracy REAL NOT NULL, eligible INTEGER NOT NULL, mode TEXT NOT NULL,
          created TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        CREATE TABLE IF NOT EXISTS competitions(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL
          REFERENCES students(id) ON DELETE CASCADE, speed REAL NOT NULL,
          created TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
        ''')


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 120000).hex()


def strokes(text):
    count = 0
    for ch in text:
        n = ord(ch) - 0xAC00
        if 0 <= n < 11172:
            initial, vowel, final = n // 588, (n % 588) // 28, n % 28
            count += (2 if initial in (1, 4, 8, 10, 13) else 1)
            count += (2 if vowel in (9, 10, 11, 14, 15, 16, 19) else 1)
            count += 0 if final == 0 else 2 if final in (2,3,5,6,9,10,11,12,13,14,15,18,20) else 1
        else:
            count += 1
    return count


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200, cookie=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def session(self, admin=False):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
        except cookies.CookieError:
            pass
        token = jar.get('session')
        session = SESSIONS.get(token.value if token else '')
        if not session or session['expires'] < time.time():
            raise ValueError('로그인이 필요합니다.')
        if admin and not session.get('admin'):
            raise ValueError('관리자만 사용할 수 있습니다.')
        if not session.get('admin'):
            with connect() as db:
                if not db.execute('SELECT id FROM students WHERE id=?', (session['id'],)).fetchone():
                    raise ValueError('삭제된 계정입니다. 다시 로그인해 주세요.')
        return session

    def login(self, data):
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = {**data, 'expires': time.time() + 28800}
        self.send_json(data, cookie=f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')

    def do_GET(self):
        if self.path.startswith('/api/'):
            try:
                self.get_api()
            except ValueError as e:
                self.send_json({'error': str(e)}, 401)
            return
        paths = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
        name = paths.get(self.path.split('?')[0])
        if not name:
            self.send_error(404)
            return
        body = (ROOT / 'static' / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.split('.')[-1]])
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def get_api(self):
        s = self.session()
        with connect() as db:
            if self.path == '/api/me':
                if s.get('admin'):
                    self.send_json({'admin': True})
                else:
                    self.send_json(dict(db.execute('SELECT id,class_name,name FROM students WHERE id=?', (s['id'],)).fetchone()))
            elif self.path == '/api/records':
                if s.get('admin'):
                    raise ValueError('학생 계정으로 로그인해 주세요.')
                self.send_json([dict(r) for r in db.execute('SELECT * FROM records WHERE student_id=? ORDER BY id DESC LIMIT 100', (s['id'],))])
            elif self.path == '/api/rankings':
                students = [dict(r) for r in db.execute('''SELECT s.id,s.class_name,s.name,AVG(r.speed) speed,
                  COUNT(r.id) count FROM students s JOIN records r ON r.student_id=s.id AND r.eligible=1
                  GROUP BY s.id ORDER BY speed DESC,s.id''')]
                classes = {}
                for r in students:
                    classes.setdefault(r['class_name'], []).append(r['speed'])
                self.send_json({'students': students, 'classes': sorted([
                    {'name': k, 'speed': sum(v)/len(v), 'count': len(v)} for k,v in classes.items()
                ], key=lambda r: (-r['speed'],r['name'])), 'competition': [dict(r) for r in db.execute('''
                  SELECT s.name,s.class_name,MAX(c.speed) speed FROM competitions c
                  JOIN students s ON s.id=c.student_id GROUP BY s.id ORDER BY speed DESC,s.id''')]})
            elif self.path == '/api/admin/students':
                self.session(admin=True)
                self.send_json([dict(r) for r in db.execute('''SELECT s.id,s.class_name,s.name,
                  COUNT(r.id) attempts,AVG(CASE WHEN r.eligible=1 THEN r.speed END) speed,
                  AVG(r.accuracy) accuracy FROM students s LEFT JOIN records r ON r.student_id=s.id
                  GROUP BY s.id ORDER BY s.class_name,s.name''')])
            else:
                self.send_json({'error':'경로를 찾을 수 없습니다.'},404)

    def do_POST(self):
        try:
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise ValueError('다른 사이트의 요청은 허용되지 않습니다.')
            length = int(self.headers.get('Content-Length',0))
            if length > 10000:
                raise ValueError('요청이 너무 큽니다.')
            data = json.loads(self.rfile.read(length) or b'{}')
            self.post_api(data)
        except (ValueError, KeyError, TypeError) as e:
            self.send_json({'error': str(e)},400)
        except sqlite3.IntegrityError:
            self.send_json({'error':'같은 반에 같은 이름의 학생이 이미 있습니다.'},409)

    def post_api(self, d):
        if self.path in ('/api/login','/api/register'):
            cls, name, pin = str(d.get('class_name','')).strip(), str(d.get('name','')).strip(), str(d.get('pin',''))
            if not cls or not name or len(cls)>30 or len(name)>30 or not re.fullmatch(r'[0-9]{4}',pin):
                raise ValueError('반, 이름과 숫자 4자리 비밀번호를 확인해 주세요.')
            # Rate-limit PIN guesses per student and client. No plaintext PIN is retained.
            key = (self.client_address[0],cls,name)
            now = time.time()
            recent = [t for t in ATTEMPTS.get(key,[]) if now-t<300]
            if len(recent)>=10:
                raise ValueError('로그인을 여러 번 시도했습니다. 5분 뒤 다시 시도해 주세요.')
            ATTEMPTS[key] = recent + [now]
            with connect() as db:
                if self.path == '/api/register':
                    salt = secrets.token_hex(16)
                    cur = db.execute('INSERT INTO students(class_name,name,salt,password) VALUES(?,?,?,?)', (cls,name,salt,password_hash(pin,salt)))
                    sid = cur.lastrowid
                else:
                    student = db.execute('SELECT * FROM students WHERE class_name=? AND name=?',(cls,name)).fetchone()
                    if not student or not hmac.compare_digest(student['password'],password_hash(pin,student['salt'])):
                        raise ValueError('반, 이름 또는 비밀번호가 일치하지 않습니다.')
                    sid = student['id']
            ATTEMPTS.pop(key,None)
            self.login({'id':sid,'class_name':cls,'name':name})
            return
        if self.path == '/api/admin/login':
            key = ('admin',self.client_address[0])
            now = time.time()
            recent = [t for t in ATTEMPTS.get(key,[]) if now-t<300]
            if len(recent)>=10:
                raise ValueError('5분 뒤 다시 시도해 주세요.')
            ATTEMPTS[key] = recent + [now]
            if not ADMIN_PASSWORD:
                raise ValueError('서버에 관리자 비밀번호가 설정되지 않았습니다.')
            if not hmac.compare_digest(str(d.get('password','')),ADMIN_PASSWORD):
                raise ValueError('관리자 비밀번호를 확인해 주세요.')
            ATTEMPTS.pop(key,None)
            self.login({'admin':True})
            return
        s = self.session()
        if self.path == '/api/logout':
            for token, value in list(SESSIONS.items()):
                if value is s:
                    del SESSIONS[token]
            self.send_json({'ok':True},cookie='session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        elif self.path == '/api/start':
            if s.get('admin'):
                raise ValueError('학생 계정으로 로그인해 주세요.')
            mode = d.get('mode','practice')
            if mode not in ('practice','competition'):
                raise ValueError('연습 종류를 확인해 주세요.')
            practice_type = d.get('practice_type', 'short') if mode == 'practice' else 'short'
            if practice_type not in PRACTICE_SETS:
                raise ValueError('연습 단계를 확인해 주세요.')
            if (d.get('retry') and s.get('attempt')
                    and s['attempt']['mode'] == mode
                    and s['attempt'].get('practice_type', 'short') == practice_type):
                attempt = s['attempt']
                attempt['started'] = time.monotonic()
            else:
                if mode=='competition':
                    if d.get('new') or not s.get('competition'):
                        s['competition'] = {'index':0,'speeds':[]}
                    index = s['competition']['index']
                else:
                    index = s.get('practice_indexes', {}).get(practice_type, secrets.randbelow(len(TEXTS)) if practice_type == 'short' else 0)
                attempt = {'index': index % len(PRACTICE_SETS[practice_type]), 'mode':mode,
                           'practice_type':practice_type, 'started':time.monotonic()}
                s['attempt'] = attempt
            category,text = PRACTICE_SETS[attempt['practice_type']][attempt['index']]
            self.send_json({'category':category,'text':text,'number': s.get('competition',{}).get('index',0)+1})
        elif self.path == '/api/submit':
            a = s.pop('attempt',None)
            if not a:
                raise ValueError('문장을 먼저 시작해 주세요.')
            text = str(d.get('text',''))
            practice_type = a.get('practice_type', 'short')
            target = PRACTICE_SETS[practice_type][a['index']][1]
            elapsed = max(time.monotonic()-a['started'],1)
            correct = sum(x==y for x,y in zip(text,target))
            accuracy = round(correct/max(len(text),len(target))*100,2)
            eligible = text==target
            speed = round(strokes(text)*60/elapsed,1)
            with connect() as db:
                db.execute('INSERT INTO records(student_id,sentence,speed,accuracy,eligible,mode) VALUES(?,?,?,?,?,?)',
                           (s['id'],target,speed,accuracy,int(eligible),practice_type if a['mode']=='practice' and practice_type!='short' else a['mode']))
                finished = False
                if eligible:
                    if a['mode']=='practice':
                        s.setdefault('practice_indexes', {})[practice_type] = (a['index']+1)%len(PRACTICE_SETS[practice_type])
                    else:
                        c = s['competition']
                        c['index'] += 1
                        c['speeds'].append(speed)
                        finished = c['index']==5
                        if finished:
                            db.execute('INSERT INTO competitions(student_id,speed) VALUES(?,?)',(s['id'],sum(c['speeds'])/5))
                            del s['competition']
                else:
                    s['attempt'] = a
            self.send_json({'speed':speed,'accuracy':accuracy,'eligible':eligible,'finished':finished})
        elif self.path in ('/api/admin/update','/api/admin/delete'):
            self.session(admin=True)
            sid = int(d['id'])
            with connect() as db:
                if not db.execute('SELECT id FROM students WHERE id=?',(sid,)).fetchone():
                    raise ValueError('학생을 찾을 수 없습니다.')
                if self.path.endswith('delete'):
                    db.execute('DELETE FROM students WHERE id=?',(sid,))
                else:
                    cls,name = str(d['class_name']).strip(),str(d['name']).strip()
                    if not cls or not name or max(len(cls),len(name))>30:
                        raise ValueError('반과 이름을 확인해 주세요.')
                    db.execute('UPDATE students SET class_name=?,name=? WHERE id=?',(cls,name,sid))
                    if d.get('pin'):
                        if not re.fullmatch(r'[0-9]{4}',str(d['pin'])):
                            raise ValueError('비밀번호는 숫자 4자리여야 합니다.')
                        salt = secrets.token_hex(16)
                        db.execute('UPDATE students SET salt=?,password=? WHERE id=?',(salt,password_hash(d['pin'],salt),sid))
            for token, session in list(SESSIONS.items()):
                if session.get('id')==sid:
                    del SESSIONS[token]
            self.send_json({'ok':True})
        else:
            self.send_json({'error':'경로를 찾을 수 없습니다.'},404)


if __name__ == '__main__':
    initialize()
    port = int(os.environ.get('PORT','8000'))
    print(f'천타 서버 시작 · port {port}', flush=True)
    ThreadingHTTPServer((os.environ.get('HOST','0.0.0.0'),port),Handler).serve_forever()
