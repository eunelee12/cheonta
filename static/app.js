const $ = s => document.querySelector(s);
const app = $('#app');
// Keep a complete desktop canvas visible, including browser zoom / window resizing.
function fitDesktop(){
 const width=document.documentElement.clientWidth,height=window.innerHeight;
 const scale=Math.min(1,width/1920,height/1080);
 const stage=$('#desktop-stage');
 stage.style.zoom=scale;
 stage.style.width=`${width/scale}px`;
 stage.style.setProperty('--desktop-height',`${height/scale}px`);
}
fitDesktop();
window.addEventListener('resize',fitDesktop);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let user, page='keys', current, started=0, timer, composing=false, busy=false, active=false;
let register=false, practiceType='keys';
const practiceLevels = {keys:{label:'자리연습',title:'한 글자씩, 차근차근!',description:'기본 자리부터 자음과 모음을 익혀요. 글자 사이의 공백도 똑같이 입력해 주세요.',unit:'문제'},words:{label:'단어연습',title:'한 단어씩, 자신 있게!',description:'국어·수학·과학·사회 등 중학교 주요 교과 어휘를 무작위로 만나 보세요.',unit:'단어'},short:{label:'짧은 글 연습',title:'한 문장씩, 정확하게!',description:'속담·명언·고전 문학 구절을 무작위로 만나 보세요. 문장부호와 공백도 똑같이 입력해요.',unit:'문장'}};
async function api(path, data) {
  const r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},...(data===undefined?{}:{body:JSON.stringify(data)})});
  const result=await r.json(); if(!r.ok) throw Error(result.error||'요청에 실패했습니다.'); return result;
}
// Count only gaps between consecutive typing events up to two seconds.
// No time is added after the last event, on blur, or while the page is hidden.
let activityTracker=null;
function trackTyping(){
 if(!active||busy||document.hidden||!activityTracker)return;
 const now=performance.now();
 if(activityTracker.last!==null){const gap=now-activityTracker.last;if(gap<=2000)activityTracker.total+=gap;}
 activityTracker.last=now;
}
async function saveActivity(tracker=activityTracker){
 if(!tracker||Math.floor(tracker.total)<=tracker.saved)return;
 const total=Math.floor(tracker.total);
 await api('activity',{activity_id:tracker.id,active_ms:total});
 tracker.saved=Math.max(tracker.saved,total);
}
async function stopActivity(){const tracker=activityTracker;activityTracker=null;active=false;if(tracker)tracker.last=null;try{await saveActivity(tracker);}catch(e){activityTracker=tracker;throw e;}}
function pauseActivity(){if(activityTracker)activityTracker.last=null;saveActivity().catch(e=>toast('연습 시간 저장 실패: '+e.message));}
window.addEventListener('blur',pauseActivity);
document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseActivity();});
window.addEventListener('pagehide',()=>{const t=activityTracker;if(t&&Math.floor(t.total)>t.saved)navigator.sendBeacon('/api/activity',new Blob([JSON.stringify({activity_id:t.id,active_ms:Math.floor(t.total)})],{type:'application/json'}));});
function duration(ms){const seconds=Math.floor((ms||0)/1000);return `${Math.floor(seconds/3600)}시간 ${Math.floor(seconds%3600/60)}분 ${seconds%60}초`;}
function toast(message){ $('#toast').textContent=message; $('#toast').classList.add('show'); setTimeout(()=>$('#toast').classList.remove('show'),4500); }
function brand(){return '<span class="brand">천마 타자대회</span>';}
function login(admin=false){
 clearInterval(timer); active=false;
 let remembered={}; try{remembered=JSON.parse(localStorage.getItem('cheonta-profile')||'{}');}catch{}
 app.innerHTML=`<header class="login-header">${brand()}<span>한 글자씩, 더 나은 나로</span></header><main class="login-layout"><section class="intro"><span class="eyebrow">우리의 성장을 잇는 타자 교실</span><h1>손끝에서 시작하는<br>나의 <span>가능성.</span></h1><p>좋은 문장을 마음에 담고, 한 글자씩 채워요.<br>친구들과 함께라면 매일 조금 더 자랄 수 있어요.</p><div class="keyboard-art" aria-hidden="true"><div class="art-top"><span>오늘도 한 걸음 더</span><b>✦</b></div><div class="art-phrase">꾸준함이 만드는<br><strong>작지만 확실한 변화</strong><i></i></div><div class="keys">${['ㅂ','ㅈ','ㄷ','ㄱ','ㅅ','ㅛ','ㅕ','ㅑ','ㅐ','ㅔ','ㅁ','ㄴ','ㅇ','ㄹ','ㅎ','ㅗ','ㅓ','ㅏ','ㅣ','ㅋ','ㅌ','ㅊ','ㅍ','ㅠ','ㅜ','ㅡ'].map(k=>`<span>${k}</span>`).join('')}</div><div class="space-key"></div></div><div class="intro-bottom"><span>✧ 짧은 글 연습</span><span>↗ 나의 성장 기록</span><span>♜ 실시간 랭킹</span></div></section><section class="login-card">${admin?'<h2>선생님, 안녕하세요</h2>':''}<p>${admin?'학생 계정과 학습 기록을 관리해요.':'우리 반과 이름을 입력하고 시작해 볼까요?'}</p>${admin?'':`<div class="segmented"><button class="${!register?'selected':''}" id="signin">로그인</button><button class="${register?'selected':''}" id="signup">처음 왔어요</button></div>`}<form id="login-form">${admin?'<label>관리자 비밀번호<input name="password" type="password" required autocomplete="current-password"></label>':`<label>우리 반<input name="class_name" list="class-options" required aria-label="우리 반" maxlength="30" placeholder="반을 선택하거나 입력해 주세요" value="${esc(remembered.class_name||'')}"><datalist id="class-options">${Array.from({length:6},(_,i)=>`${i+1}반`).map(cls=>`<option value="${cls}"></option>`).join('')}</datalist></label><label>이름<input name="name" placeholder="이름을 입력해 주세요" value="${esc(remembered.name||'')}" maxlength="30" required autocomplete="username"></label><label>비밀번호 <span>숫자 4자리</span><input name="pin" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" placeholder="••••" required autocomplete="${register?'new-password':'current-password'}"></label>`}<div class="form-error" role="alert"></div><button class="primary wide" type="submit">${admin?'관리자 로그인':register?'비밀번호 설정하고 시작하기':'연습 시작하기'} <span>→</span></button></form><div class="login-note">${admin?'관리자 비밀번호는 서버 실행 시 설정합니다.':'⌑ 비밀번호는 나만 알 수 있도록 안전하게 보관해요.'}</div><button class="text-button" id="admin-toggle">${admin?'← 학생 로그인으로 돌아가기':'선생님이신가요? 관리자 로그인 ↗'}</button></section></main><footer>© 천타 · 함께 배우고, 함께 자라는 우리</footer>`;
 if(!admin && register) setupRegistration();
 if(!admin){$('#signin').onclick=()=>{register=false;login();};$('#signup').onclick=()=>{register=true;login();};}
 $('#admin-toggle').onclick=()=>login(!admin);
 $('#login-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const d=Object.fromEntries(new FormData(e.target));user=await api(admin?'admin/login':register?'register':'login',d);if(!admin)try{localStorage.setItem('cheonta-profile',JSON.stringify({class_name:d.class_name,name:d.name}));}catch{}page=admin?'admin':'keys';await dashboard();}catch(err){$('.form-error').textContent=err.message;}finally{button.disabled=false;}};
}
function setupRegistration(){
 const form=$('#login-form');
 form.innerHTML=`<p>선생님이 등록한 명단에서 나를 찾고 비밀번호를 설정해요.</p><label>반 검색<input id="roster-class" maxlength="30" placeholder="예: 3반"></label><label>이름 검색<input id="roster-name" maxlength="30" placeholder="이름을 입력해 주세요"></label><button type="button" id="roster-search" class="wide">명단 검색</button><div id="roster-results" role="status" aria-live="polite"></div><input type="hidden" name="class_name"><input type="hidden" name="name"><label>비밀번호 <span>숫자 4자리</span><input name="pin" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" required autocomplete="new-password" placeholder="••••"></label><div class="form-error" role="alert"></div><button class="primary wide" type="submit" disabled>비밀번호 설정하고 시작하기 →</button>`;
 const clearSelection=()=>{form.elements.class_name.value='';form.elements.name.value='';form.querySelector('[type=submit]').disabled=true;$('#roster-results').replaceChildren();};
 let searchVersion=0;
 for(const id of ['#roster-class','#roster-name'])$(id).oninput=()=>{searchVersion++;clearSelection();};
 $('#roster-search').onclick=async()=>{
  const version=++searchVersion;clearSelection();$('.form-error').textContent='';
  try{
   const rows=await api('roster/search',{class_name:$('#roster-class').value,name:$('#roster-name').value});
   if(version!==searchVersion||!form.isConnected)return;
   let resultPage=0;
   function showResults(){
    const pages=Math.ceil(rows.length/3);
    $('#roster-results').innerHTML=rows.length?'<p>본인의 반과 이름을 선택해 주세요.</p>'+rows.slice(resultPage*3,resultPage*3+3).map((s,i)=>`<label><input type="radio" name="student" value="${resultPage*3+i}" required> ${esc(s.class_name)} · ${esc(s.name)}</label>`).join('')+(pages>1?`<div class="pagination"><button type="button" id="roster-prev" ${resultPage===0?'disabled':''}>이전</button><span>${resultPage+1} / ${pages}</span><button type="button" id="roster-next" ${resultPage===pages-1?'disabled':''}>다음</button></div>`:''):'<p>등록 대기 중인 학생이 없습니다. 이미 비밀번호를 설정했다면 로그인하고, 명단에 없다면 선생님께 문의해 주세요.</p>';
    form.querySelectorAll('[name=student]').forEach(r=>r.onchange=()=>{const selected=rows[Number(r.value)];form.elements.class_name.value=selected.class_name;form.elements.name.value=selected.name;form.querySelector('[type=submit]').disabled=false;});
    for(const [id,step] of [['#roster-prev',-1],['#roster-next',1]])if($(id))$(id).onclick=()=>{resultPage+=step;form.elements.class_name.value='';form.elements.name.value='';form.querySelector('[type=submit]').disabled=true;showResults();};
   }
   showResults();
  }catch(e){if(version===searchVersion&&form.isConnected)form.querySelector('.form-error').textContent=e.message;}
 };
 form.addEventListener('submit',e=>{if(!form.elements.name.value){e.preventDefault();e.stopImmediatePropagation();form.querySelector('.form-error').textContent='명단에서 본인을 먼저 선택해 주세요.';}},true);
}
function shell(){
 app.innerHTML=`<aside>${brand()}<nav>${(user.admin?[['admin','☷','학생 관리']]:[['keys','⌨','자리연습'],['words','✎','단어연습'],['short','☷','짧은 글 연습'],['records','↗','나의 기록'],['rankings','♜','실시간 랭킹']]).map(([id,icon,label])=>`<button data-page="${id}" class="${page===id?'active':''}"><span>${icon}</span>${label}</button>`).join('')}</nav><div class="sidebar-emblem"><img src="/logo.png" width="184" height="184" alt="천마 타자대회 엠블럼"></div><div class="sidebar-bottom"><div class="avatar">${user.admin?'선':esc(user.name.slice(0,1))}</div><div><b>${esc(user.admin?'선생님':user.name)}</b><small>${esc(user.class_name||'관리자')}</small></div><button id="logout" aria-label="로그아웃">↪</button></div></aside><div class="workspace"><header class="topbar"><span>한 글자씩 쌓이는 나의 성장</span><span class="today">${new Date().toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'long'})} <span class="status-dot"></span></span><button id="mobile-logout" class="mobile-logout">로그아웃</button></header><main id="content"></main><footer>빠르기보다 정확하게, 어제보다 조금 더 나답게.</footer></div>`;
 document.querySelectorAll('[data-page]').forEach(b=>b.onclick=async()=>{page=b.dataset.page;try{await dashboard();}catch(e){toast(e.message);}});
 $('#logout').onclick=async()=>{try{await stopActivity();await api('logout',{});user=null;register=false;login();}catch(e){toast(e.message);}};
 if($('#mobile-logout'))$('#mobile-logout').onclick=$('#logout').onclick;
}
async function dashboard(){await stopActivity();clearInterval(timer);active=false;busy=false;shell();if(practiceLevels[page]){practiceType=page;await practice();}else if(page==='records')await records();else if(page==='rankings')await rankings();else await adminPage();}
function heading(title,description){return `<div class="page-heading"><h1>${title}</h1><p>${description}</p></div>`;}
async function practice(){
 const level=practiceLevels[practiceType];
 const unit=level.unit;
 $('#content').innerHTML=heading(level.title,level.description)+`<div class="stat-grid"><div class="stat"><span>현재 평균타수</span><strong id="speed">0 <small>타 / 분</small></strong><i>↗</i></div><div class="stat"><span>현재 정확도</span><strong id="accuracy">100 <small>%</small></strong><i>◎</i></div><div class="stat"><span>이번 연습 완료</span><strong id="completed">0 <small>${unit}</small></strong><i>✓</i></div></div><section class="typing-card"><div class="card-top"><span><span class="status-dot"></span> ${level.label}</span><span id="category" class="pill">좋은 글귀</span></div><div class="sentence-area"><span class="quote-mark">“</span><p id="sentence"></p><span class="sentence-note">${practiceType==='short'?'마음에 담고 싶은 오늘의 한 문장':level.description}</span></div>${practiceType==='keys'?`<div class="keyboard-guide" aria-label="한글 두벌식 키보드 위치 안내">${[[['Q','ㅂ'],['W','ㅈ'],['E','ㄷ'],['R','ㄱ'],['T','ㅅ'],['Y','ㅛ'],['U','ㅕ'],['I','ㅑ'],['O','ㅐ'],['P','ㅔ']],[['A','ㅁ'],['S','ㄴ'],['D','ㅇ'],['F','ㄹ'],['G','ㅎ'],['H','ㅗ'],['J','ㅓ'],['K','ㅏ'],['L','ㅣ']],[['Z','ㅋ'],['X','ㅌ'],['C','ㅊ'],['V','ㅍ'],['B','ㅠ'],['N','ㅜ'],['M','ㅡ']]].map(row=>`<div class="keyboard-row">${row.map(([en,ko])=>`<span data-key="${ko}"><small>${en}</small>${ko}</span>`).join('')}</div>`).join('')}<div class="keyboard-row"><span data-key=" " class="guide-space">스페이스</span></div><p>강조된 키를 찾아 눌러 보세요. 한글 입력 상태에서 연습해요.</p></div>`:''}<label class="input-label" for="typing">아래에 제시된 내용을 똑같이 입력해 주세요 <span>Enter ↵ 로 제출</span></label><div class="typing-input"><textarea id="typing" rows="2" placeholder="첫 글자를 입력하면 측정이 시작돼요." autocomplete="off" autocapitalize="off" spellcheck="false"></textarea></div><div id="live-text" class="live-text" aria-label="입력 내용 오타 확인"></div><div class="typing-bottom"><span id="feedback" role="status">정확도 100%를 달성하면 평균타수에 반영돼요.</span><button id="submit" class="primary">${unit} 완료 <span>↵</span></button></div></section><div class="tip-grid"><div><span class="tip-icon">✦</span><h3>정확함이 먼저예요</h3><p>빨간 글자를 확인하고 고쳐 보세요.<br>100%가 되면 다음 문장으로 넘어가요.</p></div><div><span class="tip-icon">↗</span><h3>작은 기록, 큰 성장</h3><p>문장마다 쌓인 기록으로<br>조금씩 성장하는 나를 만나요.</p></div><div><span class="tip-icon">♡</span><h3>나만의 속도로, 꾸준하게</h3><p>친구와 비교하기보다 어제의 나와 함께!<br>오늘의 도전을 응원해요.</p></div></div>`;
 function highlightKey(index=0){document.querySelectorAll('[data-key]').forEach(key=>key.classList.toggle('next-key',key.dataset.key===current.text[index]));}
 let completed=0;
 async function next(retry=false){current=await api('start',{practice_type:practiceType,retry});if(!activityTracker||activityTracker.id!==current.activity_id)activityTracker={id:current.activity_id,total:0,saved:0,last:null};else activityTracker.last=null;started=0;active=true;$('#sentence').textContent=current.text;$('#category').textContent=current.category;$('#typing').value='';$('#typing').disabled=false;$('#submit').disabled=false;$('#live-text').textContent='';$('#speed').innerHTML='0 <small>타 / 분</small>';$('#accuracy').innerHTML='100 <small>%</small>';highlightKey();}
 await next();
 function live(){if(!active)return;const value=$('#typing').value;highlightKey(value.length);let correct=0;$('#live-text').innerHTML=Array.from(value).map((ch,i)=>{const pending=composing&&i===value.length-1;const ok=ch===current.text[i];if(ok)correct++;return `<span class="${pending?'composing':ok?'correct':'incorrect'}">${esc(ch)}</span>`;}).join('');const accuracy=value.length?Math.round(correct/Math.max(value.length,current.text.length)*100):100;$('#accuracy').innerHTML=`${accuracy} <small>%</small>`;const elapsed=started?(performance.now()-started)/60000:0;$('#speed').innerHTML=`${elapsed?Math.round(strokeCount(value)/elapsed):0} <small>타 / 분</small>`;}
 $('#typing').addEventListener('input',trackTyping);
 $('#typing').addEventListener('compositionstart',trackTyping);
 $('#typing').addEventListener('compositionend',trackTyping);
 $('#typing').addEventListener('blur',pauseActivity);
 $('#typing').oncompositionstart=()=>{composing=true;};$('#typing').oncompositionend=()=>{composing=false;live();};
 $('#typing').onbeforeinput=e=>{if(!started&&e.inputType.startsWith('insert')){started=performance.now();}};
 $('#typing').oninput=()=>{if(!started)started=performance.now();live();};
 $('#typing').onpaste=e=>{e.preventDefault();toast('한 글자씩 직접 입력해 보세요.');};
 $('#typing').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing&&!composing&&e.keyCode!==229){e.preventDefault();submit();}};
 // The server resets its timer on first input, including Korean composition.
 let timingReady=false, timingPromise=Promise.resolve();
 $('#typing').addEventListener('input',async()=>{if(!timingReady&&active){timingReady=true;timingPromise=api('start',{practice_type:practiceType,retry:true});try{await timingPromise;}catch(e){toast(e.message);}}});
 async function submit(){if(busy||!active||composing||!$('#typing').value)return;busy=true;$('#submit').disabled=true;$('#typing').disabled=true;try{await timingPromise;await saveActivity();if(activityTracker)activityTracker.last=null;const r=await api('submit',{text:$('#typing').value});if(r.eligible){completed++;$('#completed').innerHTML=`${completed} <small>${unit}</small>`;toast(`정확도 100%! ${Math.round(r.speed)}타가 기록됐어요.`);await next();$('#feedback').textContent='잘했어요! 다음 문제도 차근차근 입력해 보세요.';}else{await next(true);$('#feedback').textContent=`정확도 ${r.accuracy}%. 기록은 저장했어요. 같은 문제를 다시 연습해요.`;}timingReady=false;$('#typing').focus();}catch(e){toast(e.message);$('#typing').disabled=false;$('#submit').disabled=false;}finally{busy=false;}}
 $('#submit').onclick=submit;let lastSave=performance.now(),saving=false;timer=setInterval(()=>{live();if(!saving&&performance.now()-lastSave>=5000){lastSave=performance.now();saving=true;saveActivity().catch(e=>toast('연습 시간 저장 실패: '+e.message)).finally(()=>saving=false);}},250);
}
function strokeCount(text){let n=0;for(const ch of text){const c=ch.charCodeAt(0)-0xAC00;if(c>=0&&c<11172){n+=[1,4,8,10,13].includes(Math.floor(c/588))?2:1;n+=[9,10,11,14,15,16,19].includes(Math.floor(c%588/28))?2:1;const f=c%28;n+=!f?0:[2,3,5,6,9,10,11,12,13,14,15,18,20].includes(f)?2:1;}else n++;}return n;}
const tablePages=new Map();
function table(headers,rows,empty){
 const size=page==='admin'?4:8,key=page+':'+headers.join('|'),pages=Math.max(1,Math.ceil(rows.length/size));
 const index=Math.min(tablePages.get(key)||0,pages-1);tablePages.set(key,index);
 return `<div class="table-scroll" data-table-key="${esc(key)}" data-table-size="${size}" data-table-index="${index}"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map((r,i)=>`<tr data-table-row ${Math.floor(i/size)===index?'':'hidden'}>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}" class="empty">${empty}</td></tr>`}</tbody></table>${pages>1?`<div class="pagination"><span>전체 ${rows.length}건</span><button type="button" data-table-step="-1" ${index===0?'disabled':''}>이전</button><span data-table-count>${index+1} / ${pages}</span><button type="button" data-table-step="1" ${index===pages-1?'disabled':''}>다음</button></div>`:''}</div>`;
}
app.addEventListener('click',e=>{
 const button=e.target.closest('[data-table-step]');if(!button)return;
 const wrapper=button.closest('[data-table-key]'),rows=Array.from(wrapper.querySelectorAll('[data-table-row]')),size=Number(wrapper.dataset.tableSize),pages=Math.ceil(rows.length/size);
 const index=Math.max(0,Math.min(pages-1,Number(wrapper.dataset.tableIndex)+Number(button.dataset.tableStep)));
 wrapper.dataset.tableIndex=index;tablePages.set(wrapper.dataset.tableKey,index);
 rows.forEach((row,i)=>row.hidden=Math.floor(i/size)!==index);
 wrapper.querySelector('[data-table-count]').textContent=`${index+1} / ${pages}`;
 wrapper.querySelector('[data-table-step="-1"]').disabled=index===0;
 wrapper.querySelector('[data-table-step="1"]').disabled=index===pages-1;
});
async function records(){const rows=await api('records');$('#content').innerHTML=heading('나의 연습 기록','정확도 100%인 자리·단어·짧은 글 연습만 평균타수와 순위에 반영됩니다. 최근 100회 기록을 확인해요.')+`<section class="panel">${table(['연습한 문장','평균타수','정확도','종류','기록 시간'],rows.map(r=>[esc(r.sentence),r.eligible&&['practice','keys','words'].includes(r.mode)?`${Math.round(r.speed)}타`:'미반영',`${r.accuracy}%`,({competition:'대회',practice:'짧은 글 연습',keys:'자리연습',words:'단어연습'}[r.mode]||'연습'),new Date(r.created).toLocaleString('ko-KR')]),'아직 기록이 없어요. 첫 문장을 연습해 볼까요?')}</section>`;}
async function rankings(){let data=await api('rankings');let selected='students';$('#content').innerHTML=heading('실시간 랭킹','정확도 100%인 자리·단어·짧은 글 연습의 평균타수로 개인 순위를 매기며 상위 100명까지만 공개해요. 반 순위는 참여 학생의 개인 평균을 사용해요. 누적 시간은 오답을 포함한 실제 입력 시간이며, 2초를 넘긴 입력 간격과 대기 시간은 제외해요. 반 누적 시간은 학생들의 합계입니다. 10초마다 갱신됩니다.')+`<div class="rank-tabs"><button class="selected" data-rank="students">개인 순위</button><button data-rank="classes">반별 순위</button></div><section class="panel" id="rank-table"></section>`;function render(kind){const rows=data[kind];let rank=0;$('#rank-table').innerHTML=table(['순위',kind==='classes'?'우리 반':'학생',kind==='classes'?'참여 학생':'반','평균타수','누적 연습 시간'],rows.map((r,i)=>{if(i===0||r.speed!==rows[i-1].speed)rank=i+1;return [`<span class="rank-badge">${r.speed===null?'—':rank<=3?['🥇','🥈','🥉'][rank-1]:rank}</span>`,esc(r.name),kind==='classes'?`${r.count}명`:esc(r.class_name),r.speed===null?'—':`<b class="green">${Math.round(r.speed)}타</b>`,duration(r.active_ms)];}),'아직 기록이 없어요. 첫 번째 도전의 주인공이 되어 보세요!');}render('students');document.querySelectorAll('[data-rank]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-rank]').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');selected=b.dataset.rank;render(selected);});const panel=$('#rank-table');timer=setInterval(async()=>{try{const updated=await api('rankings');if(page==='rankings'&&panel.isConnected){data=updated;render(selected);}}catch(e){if(panel.isConnected)toast(e.message);}},10000);}
async function adminPage(){const students=await api('admin/students');$('#content').innerHTML=heading('학생 관리','반과 이름으로 학생 명단을 먼저 등록해 주세요. 학생은 처음 방문할 때 비밀번호를 설정합니다. 학생 정보를 수정하거나 비밀번호를 재설정할 수 있어요. 계정 삭제 시 모든 기록도 삭제됩니다.')+`<section class="panel"><h2>파일로 학생 명단 등록</h2><div class="roster-import"><a class="template-link" href="/api/admin/roster-template" download>엑셀 양식 다운로드 ↓</a><p>양식의 첫 행(반, 이름)은 그대로 두고 2행부터 학생을 입력해 주세요. 첫 번째 시트만 읽습니다. CSV도 같은 열 순서로 사용할 수 있어요.</p><form id="import-students-form"><label>학생 명단 파일<input type="file" id="roster-file" accept=".xlsx,.csv" required></label><p>최대 1MB · 2,000명. 같은 반·이름은 건너뛰고 기존 비밀번호와 기록은 유지합니다. 오류가 있으면 전체 등록을 취소합니다.</p><button class="primary" type="submit">파일 업로드 및 명단 생성</button><div id="import-result" role="status" aria-live="polite"></div></form></div></section><section class="panel"><h2>학생 명단 직접 등록</h2><form id="create-student-form"><label>반<input name="class_name" required maxlength="30" placeholder="예: 3반"></label><label>이름<input name="name" required maxlength="30"></label><button class="primary" type="submit">명단에 추가</button></form></section><section class="panel"><div class="panel-head"><b>전체 학생 <span class="green">${students.length}명</span></b><input id="search" placeholder="반 또는 이름으로 검색" aria-label="학생 검색"></div><div id="students"></div></section><dialog id="edit-dialog"><form id="edit-form"><h2>학생 정보 수정</h2><input name="id" type="hidden"><label>반<input name="class_name" required maxlength="30"></label><label>이름<input name="name" required maxlength="30"></label><label>새 비밀번호<input name="pin" type="password" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" placeholder="변경할 때만 숫자 4자리 입력"></label><div class="dialog-actions"><button type="button" id="cancel">취소</button><button class="primary">저장하기</button></div></form></dialog>`;function render(){const q=$('#search').value;$('#students').innerHTML=table(['반','이름','가입 상태','시도','평균타수','평균 정확도','계정 관리'],students.filter(s=>(s.class_name+s.name).includes(q)).map(s=>[esc(s.class_name),esc(s.name),s.activated?'설정 완료':'비밀번호 설정 대기',`${s.attempts}회`,s.speed===null?'—':`${Math.round(s.speed)}타`,s.accuracy===null?'—':`${s.accuracy.toFixed(1)}%`,`<button data-edit="${s.id}">수정</button> <button class="danger" data-delete="${s.id}">삭제</button>`]),'등록된 학생이 없습니다.');document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>{const s=students.find(s=>s.id===+b.dataset.edit);for(const k of ['id','class_name','name'])$('#edit-form').elements[k].value=s[k];$('#edit-form').elements.pin.value='';$('#edit-dialog').showModal();});document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=async()=>{const s=students.find(s=>s.id===+b.dataset.delete);if(confirm(`${s.class_name} ${s.name} 학생과 모든 기록을 삭제할까요? 복구할 수 없습니다.`))try{await api('admin/delete',{id:s.id});await adminPage();toast('학생 계정을 삭제했습니다.');}catch(e){toast(e.message);}});}render();$('#import-students-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter;const file=$('#roster-file').files[0];const result=$('#import-result');button.disabled=true;result.textContent='명단을 확인하고 있습니다…';try{if(!file||!/\.(xlsx|csv)$/i.test(file.name))throw Error('.xlsx 또는 .csv 파일을 선택해 주세요.');if(file.size>1024*1024)throw Error('파일은 1MB 이하로 업로드해 주세요.');const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('파일을 읽을 수 없습니다.'));reader.readAsDataURL(file);});const r=await api('admin/import',{filename:file.name,content});await adminPage();$('#import-result').textContent=`명단 등록 완료: ${r.added}명 추가, 중복 ${r.skipped}명 건너뜀 (총 ${r.total}행). 학생이 ‘처음 왔어요’에서 비밀번호를 설정할 수 있습니다.`;}catch(err){result.textContent=err.message;}finally{button.disabled=false;}};$('#create-student-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{await api('admin/create',Object.fromEntries(new FormData(e.target)));await adminPage();toast('학생 명단에 추가했습니다.');}catch(e){toast(e.message);}finally{button.disabled=false;}};$('#search').oninput=render;$('#cancel').onclick=()=>$('#edit-dialog').close();$('#edit-form').onsubmit=async e=>{e.preventDefault();try{await api('admin/update',Object.fromEntries(new FormData(e.target)));await adminPage();toast('학생 정보를 저장했습니다.');}catch(e){toast(e.message);}};}
(async()=>{try{user=await api('me');page=user.admin?'admin':'keys';await dashboard();}catch{login();}})();
