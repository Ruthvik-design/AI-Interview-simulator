HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Adaptive Interview Simulator</title><style>
:root{font-family:system-ui,Arial,sans-serif;color:#e5e7eb;background:#0f172a}*{box-sizing:border-box}
body{max-width:1000px;margin:auto;padding:24px}h1{color:#a5b4fc}h2{margin-top:0}
.card{background:#1e293b;padding:24px;border-radius:16px;margin:18px 0;box-shadow:0 8px 20px #0002}
label{display:block;margin:12px 0 5px}input,select,textarea{width:100%;padding:12px;border:1px solid #64748b;border-radius:8px;background:#0f172a;color:white;font:inherit}
textarea{min-height:130px;resize:vertical}button{background:#6366f1;color:white;border:0;border-radius:8px;padding:12px 20px;cursor:pointer;margin:10px 8px 0 0;font:inherit}
button:disabled{opacity:.5;cursor:wait}.secondary{background:#334155}.danger{background:#b91c1c}.hidden{display:none}.muted{color:#94a3b8}.error{color:#fca5a5;white-space:pre-wrap}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.question{font-size:1.25rem;line-height:1.5}
.score{background:#334155;padding:12px;border-radius:10px}.bar{background:#0f172a;height:12px;border-radius:12px;overflow:hidden;margin-top:6px}.fill{height:100%;background:#818cf8}
article{border-top:1px solid #475569;padding:12px 0;white-space:pre-wrap}small{color:#94a3b8}#busy{color:#fbbf24}
.top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.tag{background:#7c3aed;border-radius:6px;padding:2px 8px;font-size:.8rem}
table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #475569;text-align:left;vertical-align:middle}a{color:#a5b4fc}
</style></head><body><h1>🎤 AI Adaptive Interview Simulator</h1><p class="muted">Multi-agent AI with Ollama · Roles · Adaptive follow-ups · Evaluation · History</p>
<div id="topbar" class="top hidden"></div>
<p id="error" class="error" role="alert"></p><p id="busy" aria-live="polite"></p>

<section id="auth" class="card hidden"><h2>Sign in</h2>
<label for="lu">Username</label><input id="lu" maxlength="30" autocomplete="username">
<label for="lp">Password</label><input id="lp" type="password" maxlength="100" autocomplete="current-password">
<button onclick="login()">Login</button>
<hr style="border-color:#475569;margin:24px 0"><h2>New candidate? Register</h2>
<label for="ru">Username (3-30 letters, numbers, . _ -)</label><input id="ru" maxlength="30">
<label for="rn">Your name</label><input id="rn" maxlength="80">
<label for="rp">Password (min 6 characters)</label><input id="rp" type="password" maxlength="100" autocomplete="new-password">
<button class="secondary" onclick="registerUser()">Create candidate account</button></section>

<section id="setup" class="card hidden"><h2>Start a mock interview</h2>
<div class="grid"><div><label for="role">Job role</label><input id="role" maxlength="100" value="Software Developer"></div>
<div><label for="experience">Experience</label><select id="experience"><option>Fresher</option><option>1–3 years</option><option>3+ years</option></select></div>
<div><label for="kind">Interview type</label><select id="kind"><option>Technical</option><option>HR / Behavioral</option><option>Role-specific</option><option>General Placement</option></select></div>
<div><label for="total">Questions</label><select id="total"><option>3</option><option selected>5</option><option>10</option></select></div></div>
<button onclick="startInterview()">Start Interview</button></section>

<section id="live" class="card hidden"><h2>Interview in progress</h2><p id="progress" class="muted"></p><p id="question" class="question"></p>
<label for="answer">Your answer</label><textarea id="answer" maxlength="5000" placeholder="Type your answer here..."></textarea><br>
<button onclick="submitAnswer()">Submit Answer</button><button class="secondary" onclick="finishEarly()">Finish Early</button>
<div id="latest"></div></section>

<section id="results" class="card hidden"><h2>Performance Report</h2><div id="report"></div><button class="secondary" onclick="newInterview()">New Interview</button></section>

<section id="admin" class="hidden"><div id="adminbody"></div></section>

<section id="fbcard" class="card hidden"><h2>Send feedback</h2><p class="muted">Help us improve the interface or the AI models.</p>
<div class="grid"><div><label for="fbcat">About</label><select id="fbcat"><option>User interface</option><option>AI questions</option><option>AI evaluation / feedback</option><option>Other</option></select></div>
<div><label for="fbrate">Rating</label><select id="fbrate"><option>5</option><option>4</option><option selected>3</option><option>2</option><option>1</option></select></div></div>
<label for="fbtext">Your comments</label><textarea id="fbtext" maxlength="1000" style="min-height:80px"></textarea>
<button onclick="sendFeedback()">Send feedback</button> <span id="fbmsg" class="muted"></span></section>

<section id="histcard" class="card hidden"><h2>Interview History</h2><div id="history" class="muted">Loading...</div></section>

<script>
let me=null,currentId=null,lastId=null,question='',isFollow=false,index=0,total=0,working=false;
const $=id=>document.getElementById(id);
function escapeHTML(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function show(id){for(const x of ['auth','setup','live','results','admin'])$(x).classList.toggle('hidden',x!==id);
const inApp=!!me&&id!=='auth'&&id!=='admin';$('histcard').classList.toggle('hidden',!inApp);$('fbcard').classList.toggle('hidden',!inApp||me.role==='admin');}
function error(s){$('error').textContent=s||'';}
function busy(on,label='Working with Ollama...'){working=on;$('busy').textContent=on?label:'';document.querySelectorAll('button').forEach(b=>b.disabled=on);}
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});let j;try{j=await r.json();}catch{throw Error('Unexpected server response');}
if(r.status===401){me=null;renderBar();show('auth');}if(!r.ok)throw Error(j.error||'Request failed');return j;}
function renderBar(){const t=$('topbar');if(!me){t.classList.add('hidden');return;}t.classList.remove('hidden');
t.innerHTML=`<span class="muted">Logged in as <strong>${escapeHTML(me.display_name)}</strong></span><span class="tag">${escapeHTML(me.role)}</span>`+
`<button class="secondary" onclick="newInterview()">Interview</button>`+(me.role==='admin'?`<button class="secondary" onclick="openAdmin()">Admin panel</button>`:'')+`<button class="secondary" onclick="logout()">Logout</button>`;}
async function boot(){try{const r=await api('/api/me');me=r.user;}catch(e){me=null;}renderBar();if(!me){show('auth');return;}show('setup');loadHistory();}
async function login(){if(working)return;error('');busy(true,'Signing in...');try{const r=await api('/api/login',{username:$('lu').value.trim(),password:$('lp').value});me=r.user;$('lp').value='';renderBar();show('setup');loadHistory();}catch(e){error(e.message);}finally{busy(false);}}
async function registerUser(){if(working)return;error('');busy(true,'Creating account...');try{const r=await api('/api/register',{username:$('ru').value.trim(),display_name:$('rn').value.trim(),password:$('rp').value});me=r.user;$('rp').value='';renderBar();show('setup');loadHistory();}catch(e){error(e.message);}finally{busy(false);}}
async function logout(){try{await api('/api/logout',{});}catch(e){}me=null;currentId=null;renderBar();show('auth');}
async function startInterview(){if(working)return;error('');let data={role:$('role').value.trim(),experience:$('experience').value,kind:$('kind').value,total:Number($('total').value)};
if(!data.role){error('Enter the job role.');return;}busy(true,'Generating first question (this may take a minute)...');try{const r=await api('/api/start',data);currentId=r.id;question=r.question;isFollow=false;index=1;total=data.total;$('latest').innerHTML='';$('answer').value='';drawQuestion();show('live');loadHistory();}catch(e){error(e.message);}finally{busy(false);}}
function drawQuestion(){$('progress').innerHTML=`Question ${index} of ${total}`+(isFollow?' <span class="tag">Follow-up</span>':'');$('question').textContent=question;}
async function submitAnswer(){if(working||!currentId)return;const answer=$('answer').value.trim();if(!answer){error('Please type an answer.');return;}error('');busy(true,'Evaluating your answer (evaluator, feedback and question agents are working)...');try{
const r=await api('/api/answer',{id:currentId,answer});if(r.done){await openReport(currentId);}else{question=r.question;isFollow=r.is_followup;index=r.number;$('answer').value='';drawQuestion();$('latest').innerHTML='<p class="muted"><strong>Previous answer feedback:</strong> '+escapeHTML(r.feedback)+'</p>';}
loadHistory();}catch(e){error(e.message);}finally{busy(false);}}
async function finishEarly(){if(working||!currentId)return;error('');busy(true);try{await api('/api/finish',{id:currentId});await openReport(currentId);loadHistory();}catch(e){error(e.message);}finally{busy(false);}}
async function openReport(id){error('');try{const r=await api('/api/report?id='+encodeURIComponent(id));const d=r.interview;
let html=`<p><strong>${escapeHTML(d.name)}</strong> · ${escapeHTML(d.role)} · ${escapeHTML(d.kind)}</p><h3>Overall: ${r.overall}/10 (${(r.overall*10).toFixed(1)}%)</h3>`;
const p=r.progress||{};
html+=`<div class="score"><strong>Candidate progress</strong><p>Completed tests: ${p.attempts??1} · Previous score: ${p.previous_score===null||p.previous_score===undefined?'Baseline':p.previous_score+'/10'} · Current score: ${p.latest_score??r.overall}/10</p><p>Change: ${p.improvement_pct===null||p.improvement_pct===undefined?'Not available for the first test or a zero baseline':(p.improvement_pct>0?'+':'')+p.improvement_pct+'%'} · Rating: <strong>${escapeHTML(p.progress_rating||'Baseline established')}</strong></p></div>`;
if(p.plan)html+=`<div class="score"><h3>AI Improvement Coach — plan for your next test</h3><p style="white-space:pre-wrap">${escapeHTML(p.plan)}</p></div>`;
html+='<div class="grid">';
for(const [key,value] of Object.entries(r.averages)){html+=`<div class="score">${escapeHTML(key.replaceAll('_',' '))}: <strong>${value}/10</strong><div class="bar"><div class="fill" style="width:${value*10}%"></div></div></div>`;}
html+='</div><h3>Questions and Feedback</h3>';for(const [i,a] of r.answers.entries())html+=`<article><strong>Q${i+1}: ${escapeHTML(a.question)}</strong>${a.is_followup?' <span class="tag">Follow-up</span>':''}<p>Answer: ${escapeHTML(a.answer)}</p><p>Feedback: ${escapeHTML(a.feedback)}</p></article>`;
if(!r.answers.length)html+='<p>No answers were submitted.</p>';
$('report').innerHTML=html;lastId=id;currentId=null;show('results');}catch(e){error(e.message);}}
async function loadHistory(){try{const rows=await api('/api/history');$('history').innerHTML=rows.length?rows.map(r=>`<article><strong>${escapeHTML(r.name)}</strong> · ${escapeHTML(r.role)} · ${escapeHTML(r.kind)}<br><small>${escapeHTML(r.created_at)} · ${escapeHTML(r.status)} · ${r.answered}/${r.total} answered</small><br><button class="secondary" onclick="openReport('${r.id}')">View Report</button></article>`).join(''):'No interviews yet.';}catch(e){$('history').textContent=e.message;}}
function newInterview(){currentId=null;error('');show('setup');loadHistory();}
async function sendFeedback(){if(working)return;error('');$('fbmsg').textContent='';const body={category:$('fbcat').value,rating:Number($('fbrate').value),comment:$('fbtext').value.trim(),interview_id:lastId};
if(!body.comment){error('Please write a comment first.');return;}try{await api('/api/feedback',body);$('fbtext').value='';$('fbmsg').textContent='Thank you! Feedback sent.';}catch(e){error(e.message);}}

/* ---------------- Admin panel ---------------- */
async function openAdmin(){error('');try{const o=await api('/api/admin/overview');renderAdmin(o);show('admin');}catch(e){error(e.message);}}
async function adminPost(path,body){if(working)return;error('');busy(true,'Saving...');try{await api(path,body);await openAdmin();}catch(e){error(e.message);}finally{busy(false);}}
function savePrompt(k){adminPost('/api/admin/prompt',{agent:k,prompt:$('p_'+k).value});}
function resetPrompt(k){adminPost('/api/admin/prompt/reset',{agent:k});}
function saveModel(){adminPost('/api/admin/model',{model:$('modelname').value.trim()});}
function setRole(id){adminPost('/api/admin/role',{user_id:id,role:$('r_'+id).value});}
function addExample(){adminPost('/api/admin/example',{question:$('ex_q').value.trim(),sample_answer:$('ex_a').value.trim(),ideal_score:Number($('ex_s').value),note:$('ex_n').value.trim()});}
function delExample(id){adminPost('/api/admin/example/delete',{id:id});}
function renderAdmin(o){
let h=`<div class="card"><h2>Admin panel</h2><p class="muted">Users: ${o.stats.users} · Interviews: ${o.stats.interviews} · Answers: ${o.stats.answers} · Feedback: ${o.stats.feedback}</p><p class="muted">A follow-up question is asked when an answer averages below ${o.followup_below}/10.</p><a href="/api/admin/export" download="interview_data.json">Download all interview data (JSON)</a></div>`;
h+=`<div class="card"><h2>AI model</h2><p class="muted">Ollama model used by all four agents. It must already be downloaded with: ollama pull &lt;name&gt;</p><input id="modelname" value="${escapeHTML(o.model)}"><button onclick="saveModel()">Save model</button></div>`;
h+='<div class="card"><h2>AI agents</h2><p class="muted">Edit how each agent behaves. The output format is fixed by the application, so your edits cannot break it.</p>';
for(const a of o.agents){h+=`<h3>${escapeHTML(a.label)} ${a.custom?'<span class="tag">customised</span>':''}</h3><textarea id="p_${a.key}">${escapeHTML(a.prompt)}</textarea><button onclick="savePrompt('${a.key}')">Save</button><button class="secondary" onclick="resetPrompt('${a.key}')">Reset to default</button>`;}
h+='</div><div class="card"><h2>Training examples</h2><p class="muted">The 3 newest examples are shown to the Answer Evaluator so its scoring matches your expectations.</p>';
for(const e of o.examples)h+=`<article><strong>Q:</strong> ${escapeHTML(e.question)}<br><strong>Sample answer:</strong> ${escapeHTML(e.sample_answer)}<br><strong>Ideal score:</strong> ${e.ideal_score}/10 ${e.note?'· '+escapeHTML(e.note):''}<br><button class="danger" onclick="delExample(${e.id})">Delete</button></article>`;
if(!o.examples.length)h+='<p class="muted">No examples yet.</p>';
h+=`<h3>Add an example</h3><label for="ex_q">Question</label><input id="ex_q" maxlength="500"><label for="ex_a">Sample answer</label><textarea id="ex_a" maxlength="2000" style="min-height:80px"></textarea><div class="grid"><div><label for="ex_s">Ideal score (0-10)</label><input id="ex_s" type="number" min="0" max="10" step="0.5" value="7"></div><div><label for="ex_n">Note (optional)</label><input id="ex_n" maxlength="300"></div></div><button onclick="addExample()">Add example</button></div>`;
h+='<div class="card"><h2>Users and roles</h2><table><tr><th>Username</th><th>Name</th><th>Role</th><th>Interviews</th><th></th></tr>';
for(const u of o.users){const self=u.id===me.id;h+=`<tr><td>${escapeHTML(u.username)}</td><td>${escapeHTML(u.display_name)}</td><td>${self?escapeHTML(u.role)+' (you)':`<select id="r_${u.id}"><option ${u.role==='candidate'?'selected':''}>candidate</option><option ${u.role==='admin'?'selected':''}>admin</option></select>`}</td><td>${u.interviews}</td><td>${self?'':`<button class="secondary" onclick="setRole(${u.id})">Update</button>`}</td></tr>`;}
h+='</table></div><div class="card"><h2>Candidate feedback</h2>';
for(const f of o.feedback)h+=`<article><strong>${escapeHTML(f.category)}</strong> · ${f.rating}/5 · ${escapeHTML(f.username)} · <small>${escapeHTML(f.created_at)}</small><br>${escapeHTML(f.comment)}</article>`;
if(!o.feedback.length)h+='<p class="muted">No feedback yet.</p>';
$('adminbody').innerHTML=h+'</div>';}
boot();
</script></body></html>'''
