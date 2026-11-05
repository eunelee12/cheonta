"""천타: dependency-free classroom typing application."""
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from roster import parse_roster, template
from practice_content import TEXTS, WORDS

ROOT = Path(__file__).parent
DB = Path(os.environ.get('CHEONTA_DB', ROOT / 'data/cheonta.sqlite3'))
ADMIN_PASSWORD = os.environ.get('CHEONTA_ADMIN_PASSWORD', '')
SESSIONS = {}
ATTEMPTS = {}
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
    'words': WORDS,
}


def practice_index(session, kind):
    """Keep the current prompt until completion; shuffle whole cycles without repeats."""
    if kind == 'keys':
        return session.get('practice_indexes', {}).get(kind, 0)
    state = session.setdefault('practice_decks', {}).setdefault(kind, {'remaining':[], 'current':None, 'last':None})
    if state['current'] is None:
        if not state['remaining']:
            state['remaining'] = list(range(len(PRACTICE_SETS[kind])))
            secrets.SystemRandom().shuffle(state['remaining'])
            if len(state['remaining']) > 1 and state['remaining'][-1] == state['last']:
                state['remaining'][0], state['remaining'][-1] = state['remaining'][-1], state['remaining'][0]
        state['current'] = state['remaining'].pop()
    return state['current']


def complete_practice(session, kind, index):
    if kind == 'keys':
        session.setdefault('practice_indexes', {})[kind] = (index+1)%len(PRACTICE_SETS[kind])
    else:
        state = session['practice_decks'][kind]
        state['last'], state['current'] = index, None


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
        CREATE TABLE IF NOT EXISTS practice_activity(
          id TEXT PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
          practice_type TEXT NOT NULL, active_ms INTEGER NOT NULL DEFAULT 0, started REAL NOT NULL);
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
        paths = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/logo.png': 'logo.png', '/logo-small.png': 'logo-small.png'}
        name = paths.get(self.path.split('?')[0])
        if not name:
            self.send_error(404)
            return
        body = (ROOT / 'static' / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','png':'image/png'}[name.split('.')[-1]])
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def get_api(self):
        s = self.session()
        if self.path == '/api/admin/roster-template':
            self.session(admin=True)
            body = template()
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.send_header('Content-Disposition', 'attachment; filename="cheonta-students-template.xlsx"')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
                students = [dict(r) for r in db.execute("""SELECT s.id,s.class_name,s.name,
                  r.speed,COALESCE(r.count,0) count,COALESCE(a.active_ms,0) active_ms
                  FROM students s LEFT JOIN (
                    SELECT student_id,AVG(speed) speed,COUNT(*) count FROM records
                    WHERE eligible=1 AND mode IN ('practice','keys','words') GROUP BY student_id
                  ) r ON r.student_id=s.id LEFT JOIN (
                    SELECT student_id,SUM(active_ms) active_ms FROM practice_activity GROUP BY student_id
                  ) a ON a.student_id=s.id
                  WHERE r.count>0 OR a.active_ms>0
                  ORDER BY r.speed IS NULL,r.speed DESC,s.id""")]
                classes = {}
                for row in students:
                    group = classes.setdefault(row['class_name'], {'name':row['class_name'], 'speeds':[], 'count':0, 'active_ms':0})
                    group['count'] += 1
                    group['active_ms'] += row['active_ms']
                    if row['speed'] is not None:
                        group['speeds'].append(row['speed'])
                class_rows = []
                for group in classes.values():
                    speeds = group.pop('speeds')
                    group['speed'] = sum(speeds)/len(speeds) if speeds else None
                    class_rows.append(group)
                # Limit the public individual list after computing class totals from everyone.
                self.send_json({'students':students[:100], 'classes':sorted(class_rows,
                    key=lambda row:(row['speed'] is None,-(row['speed'] or 0),row['name']))})
            elif self.path == '/api/admin/students':
                self.session(admin=True)
                self.send_json([dict(r) for r in db.execute('''SELECT s.id,s.class_name,s.name,
                  COUNT(r.id) attempts,AVG(CASE WHEN r.eligible=1 AND r.mode IN ('practice','keys','words') THEN r.speed END) speed,
                  AVG(r.accuracy) accuracy,(s.password != '') activated FROM students s LEFT JOIN records r ON r.student_id=s.id
                  GROUP BY s.id ORDER BY s.class_name,s.name''')])
            else:
                self.send_json({'error':'경로를 찾을 수 없습니다.'},404)

    def do_POST(self):
        try:
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise ValueError('다른 사이트의 요청은 허용되지 않습니다.')
            length = int(self.headers.get('Content-Length',0))
            if self.path == '/api/admin/import':
                self.session(admin=True)
            if length < 0 or length > (1500000 if self.path == '/api/admin/import' else 10000):
                raise ValueError('요청이 너무 큽니다.')
            data = json.loads(self.rfile.read(length) or b'{}')
            self.post_api(data)
        except (ValueError, KeyError, TypeError) as e:
            self.send_json({'error': str(e)},400)
        except sqlite3.IntegrityError:
            self.send_json({'error':'같은 반에 같은 이름의 학생이 이미 있습니다.'},409)

    def post_api(self, d):
        if self.path == '/api/roster/search':
            cls = str(d.get('class_name', '')).strip()
            name = str(d.get('name', '')).strip()
            if not cls and not name:
                raise ValueError('검색할 반 또는 이름을 입력해 주세요.')
            with connect() as db:
                rows = db.execute('''SELECT id,class_name,name FROM students
                  WHERE password='' AND (?='' OR instr(class_name,?)>0)
                  AND (?='' OR instr(name,?)>0) ORDER BY class_name,name LIMIT 100''',
                  (cls,cls,name,name)).fetchall()
            self.send_json([dict(row) for row in rows])
            return
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
                    cur = db.execute("UPDATE students SET salt=?,password=? WHERE class_name=? AND name=? AND password=''",
                                     (salt,password_hash(pin,salt),cls,name))
                    if cur.rowcount != 1:
                        raise ValueError('등록 대기 중인 학생을 찾을 수 없습니다. 이미 설정했다면 로그인하고, 명단에 없다면 선생님께 문의해 주세요.')
                    sid = db.execute('SELECT id FROM students WHERE class_name=? AND name=?',(cls,name)).fetchone()['id']
                else:
                    student = db.execute('SELECT * FROM students WHERE class_name=? AND name=?',(cls,name)).fetchone()
                    if not student or not student['password'] or not hmac.compare_digest(student['password'],password_hash(pin,student['salt'])):
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
            if mode != 'practice':
                raise ValueError('연습 종류를 확인해 주세요.')
            practice_type = d.get('practice_type', 'short')
            if practice_type not in PRACTICE_SETS:
                raise ValueError('연습 단계를 확인해 주세요.')
            if (d.get('retry') and s.get('attempt')
                    and s['attempt']['mode'] == mode
                    and s['attempt'].get('practice_type', 'short') == practice_type):
                attempt = s['attempt']
                attempt['started'] = time.monotonic()
            else:
                index = practice_index(s, practice_type)
                attempt = {'index': index % len(PRACTICE_SETS[practice_type]), 'mode':mode,
                           'practice_type':practice_type, 'started':time.monotonic()}
                s['attempt'] = attempt
            category,text = PRACTICE_SETS[attempt['practice_type']][attempt['index']]
            if 'activity_id' not in attempt:
                attempt['activity_id'] = secrets.token_urlsafe(24)
                with connect() as db:
                    db.execute('INSERT INTO practice_activity(id,student_id,practice_type,started) VALUES(?,?,?,?)',
                               (attempt['activity_id'],s['id'],practice_type,time.time()))
            self.send_json({'category':category,'text':text,'activity_id':attempt['activity_id']})
        elif self.path == '/api/activity':
            if s.get('admin'):
                raise ValueError('학생 계정으로 로그인해 주세요.')
            total = d.get('active_ms')
            if isinstance(total,bool) or not isinstance(total,(int,float)) or total < 0 or total > 1e12 or not math.isfinite(total):
                raise ValueError('연습 시간을 확인해 주세요.')
            with connect() as db:
                row = db.execute('SELECT * FROM practice_activity WHERE id=? AND student_id=?',
                                 (str(d.get('activity_id','')),s['id'])).fetchone()
                if not row or total > max(0,time.time()-row['started'])*1000:
                    raise ValueError('연습 시간을 확인해 주세요.')
                db.execute('UPDATE practice_activity SET active_ms=MAX(active_ms,?) WHERE id=?',
                           (int(total),row['id']))
            self.send_json({'ok':True})
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
                if eligible:
                    complete_practice(s, practice_type, a['index'])
                else:
                    s['attempt'] = a
            self.send_json({'speed':speed,'accuracy':accuracy,'eligible':eligible})
        elif self.path == '/api/admin/import':
            self.session(admin=True)
            students = parse_roster(str(d.get('filename','')), d.get('content',''))
            added = 0
            with connect() as db:
                for cls, name in students:
                    cur = db.execute("INSERT INTO students(class_name,name,salt,password) VALUES(?,?,'','') ON CONFLICT(class_name,name) DO NOTHING", (cls,name))
                    added += cur.rowcount
            self.send_json({'added':added, 'skipped':len(students)-added, 'total':len(students)})
        elif self.path == '/api/admin/create':
            self.session(admin=True)
            cls, name = str(d.get('class_name','')).strip(), str(d.get('name','')).strip()
            if not cls or not name or max(len(cls),len(name)) > 30:
                raise ValueError('반과 이름을 30자 이내로 입력해 주세요.')
            with connect() as db:
                cur = db.execute("INSERT INTO students(class_name,name,salt,password) VALUES(?,?,'','')", (cls,name))
            self.send_json({'id':cur.lastrowid,'class_name':cls,'name':name})
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
