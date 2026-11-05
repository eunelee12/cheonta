"""Real desktop layout checks, including long text and large lists."""
import base64
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from practice_content import TEXTS

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
with tempfile.TemporaryDirectory() as tmp:
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 url=f'http://127.0.0.1:{port}'
 db=Path(tmp)/'layout.sqlite3'
 proc=subprocess.Popen(['python3','server.py'],env={**os.environ,'PORT':str(port),'HOST':'127.0.0.1','CHEONTA_DB':str(db),'CHEONTA_ADMIN_PASSWORD':'layout-test-only'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1920,'height':1080})
   for _ in range(100):
    try: page.goto(url);break
    except Exception: time.sleep(.05)
   def check(label):
    page.wait_for_function('Math.abs(document.querySelector("#desktop-stage").getBoundingClientRect().width-innerWidth)<2 && Math.abs(document.querySelector("#desktop-stage").getBoundingClientRect().height-innerHeight)<2')
    bounds=page.evaluate('''()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,content:[...document.querySelectorAll('.typing-bottom,.tip-grid,.login-card,.panel,.workspace>footer')].map(e=>({name:e.className,top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom}))})''')
    assert bounds['scrollHeight']<=bounds['height'] and bounds['scrollWidth']<=bounds['width'],(label,bounds)
    for item in bounds['content']:
     assert item['top']>=0 and item['bottom']<=bounds['height'],(label,item,bounds)
   page.locator('.brand').wait_for()
   assert page.locator('.brand').inner_text()=='천마 타자대회'
   assert page.request.get(url+'/logo.png').headers['content-type']=='image/png'
   check('login')
   page.screenshot(path='/workspace/cheonta-login-design.png')
   assert page.request.post(url+'/api/admin/login',data={'password':'layout-test-only'}).ok
   csv='반,이름\n'+'\n'.join(f'3반,학생{i:02}' for i in range(24))
   assert page.request.post(url+'/api/admin/import',data={'filename':'layout.csv','content':base64.b64encode(csv.encode()).decode()}).ok
   page.reload();page.locator('[data-edit]').first.wait_for()
   check('admin')
   assert page.locator('[data-table-row]:visible').count()==4
   page.get_by_role('button',name='다음',exact=True).click()
   page.get_by_role('cell',name='학생04',exact=True).wait_for()
   page.screenshot(path='/workspace/cheonta-admin-design.png')
   sizes=[(1920,1080),(1920,940),(1600,900),(1536,864),(1366,768),(1280,720),(1024,768)]
   for width,height in sizes:
    page.set_viewport_size({'width':width,'height':height});check(f'admin {width}x{height}')
    page.locator('[data-edit]:visible').first.click()
    page.locator('#edit-dialog').wait_for()
    box=page.locator('#edit-dialog').bounding_box()
    assert box['x']>=0 and box['y']>=0 and box['x']+box['width']<=width+1 and box['y']+box['height']<=height+1,box
    page.locator('#cancel').click()
   page.set_viewport_size({'width':1920,'height':1080})
   page.locator('#logout').click()
   page.get_by_role('button',name='처음 왔어요').click()
   page.locator('#roster-class').fill('3반');page.locator('#roster-search').click()
   page.get_by_role('radio').first.wait_for();check('signup many results')
   page.set_viewport_size({'width':1920,'height':940});check('signup 940')
   page.set_viewport_size({'width':1920,'height':1080})
   page.locator('#roster-next').click();check('signup next results')
   page.locator('#roster-prev').click();page.get_by_role('radio').first.check()
   page.locator('[name=pin]').fill('1234');page.get_by_role('button',name='비밀번호 설정하고 시작하기').click()
   page.locator('#typing').wait_for()
   longest=max((text for _,text in TEXTS),key=len)
   sid=page.request.get(url+'/api/me').json()['id']
   with sqlite3.connect(db) as conn:
    for i in range(100):
     conn.execute("INSERT INTO records(student_id,sentence,speed,accuracy,eligible,mode) VALUES(?,?,100,100,1,'practice')",(sid,longest))
   for width,height in sizes:
    page.set_viewport_size({'width':width,'height':height})
    for kind in ('keys','words','short','records','rankings'):
     page.locator(f'[data-page={kind}]').click()
     if kind in ('keys','words','short'):
      page.locator('#typing').wait_for()
      if kind=='short':page.locator('#sentence').evaluate('(e,text)=>e.textContent=text',longest)
      if kind=='keys':
       page.locator('#typing').press_sequentially('ㅁ ㄴ ㅇ ㄹ',delay=130)
       page.wait_for_timeout(250)
     else:page.locator('table').wait_for()
     check(f'{kind} {width}x{height}')
     emblem=page.locator('.sidebar-emblem img').bounding_box()
     nav=page.locator('nav').bounding_box()
     bottom=page.locator('.sidebar-bottom').bounding_box()
     assert emblem['y']>=nav['y']+nav['height'] and emblem['y']+emblem['height']<bottom['y']
     assert page.locator('aside .brand').inner_text()=='천마 타자대회'
     if kind=='records':
      assert page.locator('[data-table-row]:visible').count()==8
      page.get_by_role('button',name='다음',exact=True).click();check('records next')
     if width==1920 and height==1080:page.screenshot(path=f'/workspace/cheonta-{kind}-design.png')
   page.screenshot(path='/workspace/cheonta-scaled-1024.png')
   browser.close()
   print('Desktop layout passed: login, signup, admin pagination, all five menus, long passages, 100 records at seven desktop sizes from 1920x1080 to 1024x768, including edit dialogs and large sidebar emblem.')
 finally:
  proc.terminate();proc.wait()
