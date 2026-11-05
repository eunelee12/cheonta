import os, subprocess, tempfile
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 proc=subprocess.Popen(['python3','server.py'],env={**os.environ,'PORT':'8765','HOST':'127.0.0.1','CHEONTA_DB':tmp+'/browser.sqlite3','CHEONTA_ADMIN_PASSWORD':'browser-test-only'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1920,'height':1080})
   errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:8765')
   assert page.get_by_text('반가워요, 타자 친구!').count()==0
   assert page.locator('#class-options option').evaluate_all('(options)=>options.map(o=>o.value)')==['1반','2반','3반','4반','5반','6반']
   page.get_by_role('button',name='선생님이신가요?',exact=False).click()
   page.locator('[name=password]').fill('browser-test-only')
   page.locator('#login-form button[type=submit]').click()
   with page.expect_download() as download_event:
    page.get_by_role('link',name='엑셀 양식 다운로드').click()
   assert Path(download_event.value.path()).read_bytes().startswith(b'PK')
   from test_roster import filled_template
   for filename, buffer, name in [('명단.xlsx',filled_template(),'김하늘'),('명단.csv','반,이름\n파일반,업로드학생\n'.encode('utf-8-sig'),'업로드학생')]:
    page.locator('#roster-file').set_input_files({'name':filename,'mimeType':'application/octet-stream','buffer':buffer})
    page.get_by_role('button',name='파일 업로드 및 명단 생성').click()
    page.get_by_role('cell',name=name,exact=True).wait_for()
    assert '1명 추가' in page.locator('#import-result').inner_text()
    rows=page.request.get('http://127.0.0.1:8765/api/admin/students').json()
    sid=next(s['id'] for s in rows if s['name']==name)
    assert page.request.post('http://127.0.0.1:8765/api/admin/delete',data={'id':sid}).ok
   page.reload()
   page.locator('#create-student-form').wait_for()
   page.locator('#create-student-form [name=class_name]').fill('3반')
   page.locator('#create-student-form [name=name]').fill('김하늘')
   page.get_by_role('button',name='명단에 추가').click()
   page.get_by_role('cell',name='비밀번호 설정 대기',exact=True).wait_for()
   page.locator('#logout').click()
   page.get_by_role('button',name='처음 왔어요').click()
   assert page.locator('#login-form button[type=submit]').is_disabled()
   page.locator('#roster-class').fill('3반')
   page.locator('#roster-name').fill('김하늘')
   page.get_by_role('button',name='명단 검색',exact=True).click()
   page.get_by_role('radio').check()
   page.locator('[name=pin]').fill('1234')
   page.get_by_role('button',name='비밀번호 설정하고 시작하기').click()
   page.locator('#typing').wait_for()
   assert page.locator('[data-page]').evaluate_all('(buttons)=>buttons.map(b=>b.dataset.page)')==['keys','words','short','records','rankings']
   assert [page.locator(f'[data-page={kind}]').inner_text().strip()[1:].strip() for kind in ['keys','words','short','records','rankings']]==['자리연습','단어연습','짧은 글 연습','나의 기록','실시간 랭킹']
   assert page.locator('#sentence').inner_text()=='ㅁ ㄴ ㅇ ㄹ'
   page.locator('#typing').press_sequentially('abc',delay=150)
   active_before=page.evaluate('activityTracker.total')
   assert active_before>=200,active_before
   page.wait_for_timeout(2200)
   page.locator('#typing').press_sequentially('d')
   assert page.evaluate('activityTracker.total')-active_before<200
   page.locator('[data-page=rankings]').click()
   page.get_by_role('columnheader',name='누적 연습 시간',exact=True).wait_for()
   ranking=page.request.get('http://127.0.0.1:8765/api/rankings').json()
   assert ranking['students'][0]['active_ms']>=200
   assert ranking['students'][0]['speed'] is None
   assert ranking['classes'][0]['active_ms']==ranking['students'][0]['active_ms']
   page.locator('[data-page=keys]').click()
   page.locator('#typing').wait_for()
   text=page.locator('#sentence').inner_text()
   page.locator('#typing').fill('틀린 문장')
   assert page.locator('#live-text .incorrect').count()>0
   page.locator('#submit').click()
   page.wait_for_function("document.querySelector('#typing').value === '' && !document.querySelector('#typing').disabled")
   assert page.locator('#sentence').inner_text()==text
   page.locator('#typing').fill(text)
   page.locator('#submit').click()
   page.wait_for_function("document.querySelector('#completed').textContent.includes('1')")
   for kind, expected in [('keys','ㅎ ㅗ ㅓ ㅏ ㅣ'),('words',None)]:
    page.locator(f'[data-page={kind}]').click()
    if expected is None:
     page.wait_for_function('document.querySelector("#category").textContent.startsWith("교과 어휘")')
     expected=page.locator('#sentence').inner_text()
    else:
     page.wait_for_function('(expected)=>document.querySelector("#sentence").textContent===expected',arg=expected)
    assert page.locator(f'[data-page={kind}]').get_attribute('class')=='active'
    page.locator('#typing').fill(expected)
    page.locator('#submit').click()
    page.wait_for_function("document.querySelector('#completed').textContent.includes('1')")
    assert page.locator('#sentence').inner_text()!=expected
   page.locator('[data-page=short]').click()
   page.locator('#typing').wait_for()
   from practice_content import TEXTS
   page.wait_for_function('(texts)=>texts.includes(document.querySelector("#sentence").textContent)',arg=[t for _,t in TEXTS])
   page.locator('[data-page=records]').click()
   page.get_by_role('cell',name='미반영',exact=True).wait_for()
   page.locator('[data-page=rankings]').click()
   page.get_by_role('cell',name='김하늘',exact=True).wait_for()
   assert page.locator('[data-rank]').count()==2
   page.locator('[data-rank=classes]').click()
   page.get_by_role('cell',name='3반',exact=True).wait_for()
   with page.expect_response(lambda response: response.url.endswith('/api/rankings'),timeout=15000):
    pass
   assert page.locator('[data-rank=classes]').get_attribute('class')=='selected'
   page.get_by_role('cell',name='3반',exact=True).wait_for()
   page.locator('#logout').click()
   page.get_by_role('button',name='로그인',exact=True).wait_for()
   page.locator('[name=pin]').fill('1234')
   page.get_by_role('button',name='연습 시작하기').click()
   page.locator('#typing').wait_for()
   page.screenshot(path='/tmp/cheonta-practice.png',full_page=True)
   assert page.evaluate('document.documentElement.scrollHeight <= window.innerHeight && document.documentElement.scrollWidth <= window.innerWidth')
   page.locator('#logout').click()
   page.get_by_role('button',name='선생님이신가요?',exact=False).click()
   page.locator('[name=password]').fill('browser-test-only')
   page.locator('#login-form button[type=submit]').click()
   page.locator('[data-edit]').wait_for()
   page.locator('[data-edit]').click()
   page.locator('#edit-form [name=name]').fill('김새봄')
   page.get_by_role('button',name='저장하기').click()
   page.get_by_role('cell',name='김새봄',exact=True).wait_for()
   assert errors==[],errors
   print('Browser smoke passed: registration, error colors, retry, records, rankings, re-login, desktop layout, admin edit. No JS errors.')
   browser.close()
 finally:
  proc.terminate();proc.wait()
