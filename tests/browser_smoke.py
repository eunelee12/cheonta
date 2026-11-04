import os, subprocess, tempfile
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 proc=subprocess.Popen(['python3','server.py'],env={**os.environ,'PORT':'8765','HOST':'127.0.0.1','CHEONTA_DB':tmp+'/browser.sqlite3','CHEONTA_ADMIN_PASSWORD':'browser-test-only'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1440,'height':1000})
   errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:8765')
   assert page.get_by_text('반가워요, 타자 친구!').count()==0
   assert page.locator('select[name=class_name] option:not([disabled])').all_text_contents()==['1반','2반','3반','4반','5반','6반']
   page.get_by_role('button',name='처음 왔어요').click()
   page.locator('[name=class_name]').select_option('3반')
   page.locator('[name=name]').fill('김하늘')
   page.locator('[name=pin]').fill('1234')
   page.get_by_role('button',name='내 계정 만들기').click()
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
   page.locator('[data-page=records]').click()
   page.get_by_role('cell',name='미반영',exact=True).wait_for()
   page.locator('[data-page=rankings]').click()
   page.get_by_role('cell',name='김하늘',exact=True).wait_for()
   page.locator('[data-rank=classes]').click()
   page.get_by_role('cell',name='3반',exact=True).wait_for()
   page.locator('#logout').click()
   page.get_by_role('button',name='로그인',exact=True).wait_for()
   page.locator('[name=pin]').fill('1234')
   page.get_by_role('button',name='연습 시작하기').click()
   page.locator('#typing').wait_for()
   page.screenshot(path='/tmp/cheonta-practice.png',full_page=True)
   page.set_viewport_size({'width':390,'height':844})
   assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
   page.locator('#mobile-logout').click()
   page.get_by_role('button',name='선생님이신가요?',exact=False).click()
   page.locator('[name=password]').fill('browser-test-only')
   page.locator('#login-form button[type=submit]').click()
   page.locator('[data-edit]').wait_for()
   page.locator('[data-edit]').click()
   page.locator('#edit-form [name=name]').fill('김새봄')
   page.get_by_role('button',name='저장하기').click()
   page.get_by_role('cell',name='김새봄',exact=True).wait_for()
   assert errors==[],errors
   print('Browser smoke passed: registration, error colors, retry, records, rankings, re-login, mobile layout, admin edit. No JS errors.')
   browser.close()
 finally:
  proc.terminate();proc.wait()
