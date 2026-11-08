const main=document.querySelector('main');
const state={tab:'passages',expanded:true,review:'Untriaged',reviewNote:'',reviewOpen:false,rechecked:false,rechecking:false,scanRunning:false,scanLog:[],files:['roadmap.md','auth.ts'],sources:['release','gist'],checks:['public','risk'],error:''};
const SOURCES=[['release','Platform update','relay-notes.example/platform-update'],['gist','Public Gist','gist.github.com/[sample]'],['paste','Community paste','paste.example/relay']];
const ic=(n,cls='')=>`<i class="ic ${cls}" style="--i:url(assets/${n}.svg)" aria-hidden="true"></i>`;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const announce=s=>document.querySelector('#announcement').textContent=s;
const head=(title,meta,action='')=>`<div class="page-head"><div><h1>${title}</h1>${meta?`<div class="meta">${meta}</div>`:''}</div>${action}</div>`;

/* ---------- Findings ---------- */
function kpis(){return `<section class="kpis" aria-label="Scan summary">
<div class="kpi red"><span class="label">Public exposure</span><b>1</b><small>1 match in 2 checked sources</small></div>
<button class="kpi ${state.rechecked?'':'amber'}" data-action="risk"><span class="label">Code risks</span><b>${state.rechecked?'0':'1'}</b><small>${state.rechecked?'Not detected in b917':'auth.ts · CWE-532'}</small></button>
<button class="kpi" data-action="coverage"><span class="label">Coverage</span><b>2<span>/3</span></b><span class="segbar" aria-hidden="true"><i class="ok"></i><i class="ok"></i><i class="fail"></i></span><small>1 source failed · result unknown</small></button>
<a class="kpi" href="#activity"><span class="label">Egress</span><b>3</b><small>public URLs → 2 providers</small></a>
</section>`;}

function fingerprint(){const pre=8,hit=30;return `<div class="fp"><span class="label">Token fingerprint</span><div class="fp-bar" role="img" aria-label="30 of 38 tokens in the private window match the public page">${Array.from({length:pre+hit},(_,i)=>`<i class="${i>=pre?'on':''}"></i>`).join('')}</div><small>30 / 38 tokens · contiguous</small></div>`;}

function line(n,html,dim){return `<div class="ln ${dim?'dim':''}"><em>${n}</em><span>${html}</span></div>`;}
function passages(){return fingerprint()+`<div class="viewers">
<section class="viewer" aria-label="Private file"><div class="vhead">${ic('lock')}<strong>roadmap.md</strong><span>L5–8</span><span class="tag">private</span></div><div class="vbody">
${line('04','# 2027 platform roadmap',true)}${line('05','In the first half of 2027 we will <mark>retire the Harbor ingestion cluster</mark>')}${line('06','<mark>and move every tenant onto the Lantern streaming tier,</mark>')}${line('07','<mark>starting with the twelve logistics customers that still</mark>')}${line('08','<mark>depend on nightly batch exports.</mark>')}</div></section>
<section class="viewer" aria-label="Public source"><div class="vhead">${ic('globe')}<strong>relay-notes.example</strong><span>L12–15</span><span class="tag" style="color:var(--red);border-color:rgba(255,107,94,.45)">public</span></div><div class="vbody">
${line('11','# What’s next for Relay',true)}${line('12','The platform team plans to <mark>retire the Harbor ingestion cluster</mark>')}${line('13','<mark>and move every tenant onto the Lantern streaming tier,</mark>')}${line('14','<mark>starting with the twelve logistics customers that still</mark>')}${line('15','<mark>depend on nightly batch exports.</mark>')}</div></section></div>
<div class="evmeta"><span class="tag">match: exact · normalized</span><span class="tag">retrieved 2026-11-07 14:31 EST</span><span class="tag">via exa</span><span class="tag">publication auth: unknown</span></div>`;}

function coverage(){const rows=[
['globe','Platform update','relay-notes.example','Retrieved 14:31:02','<span class="st open">MATCH</span>'],
['globe','Public Gist','gist.github.com · sample','Retrieved 14:31:03','<span class="st ok">CLEAN</span>'],
['globe','Community paste','paste.example','Provider timeout · 30s','<span class="st fail">FAILED</span>'],
['shield','Preventive risk review','2 files · 1 rule hit','Completed 14:32:10','<span class="st ok">COMPLETE</span>']];
return rows.map(([i,n,s,o,r])=>`<div class="cov-row">${ic(i)}<div><strong>${n}</strong><small>${s}</small></div><small class="c-obs">${o}</small><div>${r}</div></div>`).join('')+`<div class="note">${ic('circle-alert')}<span>Failed sources are unknown, not clean. Scope is the 3 selected sources only — not the whole web.</span></div>`;}

function history(){return `<div class="tl">
<div class="tl-item"><time>review</time><div><strong>${esc(state.review)}</strong></div><p>${state.reviewNote?esc(state.reviewNote):'No triage note yet.'}</p></div>
<div class="tl-item warn"><time>14:32:07</time><div><code>match.observed</code></div><p>roadmap.md ↔ relay-notes.example · 30 tokens</p></div>
<div class="tl-item"><time>14:31:02</time><div><code>source.retrieved</code></div><p>Seeded URL fetched via Exa</p></div>
<div class="tl-item"><time>14:31:00</time><div><code>scan.started</code></div><p>SCN-0417 · 2 files · 3 sources</p></div></div>`;}

function detail(){return `<div class="detail" id="tf-001-detail">
<div class="trace" aria-label="Trace: private file matched on public page">
<div class="node priv"><span class="nico">${ic('file-text')}</span><div><span class="label">Private</span><strong>roadmap.md:5–8</strong></div></div>
<div class="link"><span>EXACT · 30 TOK</span></div>
<div class="node pub"><span class="nico">${ic('globe')}</span><div><span class="label">Public</span><strong>relay-notes.example/platform-update</strong></div></div></div>
<div class="tabs" role="tablist" aria-label="Finding detail">${[['passages','Compare'],['coverage','Coverage'],['history','History']].map(([id,l])=>`<button role="tab" id="tab-${id}" data-tab="${id}" aria-selected="${state.tab===id}" aria-controls="tabpanel" tabindex="${state.tab===id?0:-1}">${l}</button>`).join('')}
<div class="right"><span class="tag hide-sm">triage: ${esc(state.review)}</span><button class="btn sm" data-action="review">${ic('plus')}${state.reviewNote?'Edit triage':'Triage'}</button></div></div>
<div class="tabpanel" id="tabpanel" role="tabpanel" aria-labelledby="tab-${state.tab}">${state.tab==='passages'?passages():state.tab==='coverage'?coverage():history()}</div>
${state.reviewOpen?`<form class="triage" id="review-form"><div class="field"><label class="label" for="decision">State</label><select id="decision">${['Needs investigation','Expected publication','Dismissed'].map(v=>`<option ${state.review===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="field"><label class="label" for="review-note">Reason / next step</label><textarea id="review-note" required maxlength="500">${esc(state.reviewNote)}</textarea></div><div class="actions"><button class="btn primary" type="submit">Save</button><button class="btn ghost" type="button" data-action="cancel-review">Cancel</button></div></form>`:''}
</div>`;}

function evidence(){
main.innerHTML=head('Findings',`<span>SCN-0417</span><span>${ic('file-text')}2 files</span><span>${ic('globe')}3 sources</span><span>2026-11-07 14:32 EST</span>`,`<a class="btn primary" href="#scan">${ic('plus')}New scan</a>`)+kpis()+
`<section class="pane ftable" aria-label="Findings">
<div class="fgrid fhead" aria-hidden="true"><span class="label">Sev</span><span class="label">ID</span><span class="label c-type">Type</span><span class="label">Finding</span><span class="label">Location</span><span class="label c-signal">Signal</span><span class="label">Status</span><span></span></div>
<button class="frow fgrid" data-action="toggle" aria-expanded="${state.expanded}" aria-controls="tf-001-detail"><span class="c-sev"><span class="sev high">HIGH</span></span><span class="fid c-id">TF-001</span><span class="tag c-type">exposure</span><span class="ftitle c-title">Roadmap passage on public page</span><span class="floc c-loc">roadmap.md:5 → relay-notes</span><span class="tag c-signal">30 tok exact</span><span class="c-status"><span class="st open">OPEN</span></span>${ic('chevron-right','chev')}</button>
${state.expanded?detail():''}
<button class="frow fgrid" data-action="risk"><span class="c-sev"><span class="sev ${state.rechecked?'low':'med'}">${state.rechecked?'LOW':'MED'}</span></span><span class="fid c-id">TF-002</span><span class="tag c-type">code risk</span><span class="ftitle c-title">Session token written to logs</span><span class="floc c-loc">auth.ts:42</span><span class="tag c-signal">CWE-532</span><span class="c-status"><span class="st ${state.rechecked?'ok':'review'}">${state.rechecked?'NOT DETECTED':'REVIEW'}</span></span>${ic('chevron-right','chev')}</button>
</section>`;}

/* ---------- New scan ---------- */
function scan(){
const sel=SOURCES.filter(([id])=>state.sources.includes(id));
main.innerHTML=head('New scan',`<span>Prototype · file names only, nothing uploaded</span>`,`<a class="btn ghost" href="#evidence">Cancel</a>`)+
`<form id="scan-form"><div class="steps">
<section class="pane"><div class="pane-head"><span><span class="step-n">01</span><strong>Inputs</strong></span><small class="mono">${state.files.length}/10</small></div><div class="pane-body">
<label class="drop" for="files" id="dropzone">${ic('upload')}<span>Drop files or <u>browse</u></span><small>.md .txt .docx · code</small></label>
<input class="sr-only" id="files" type="file" multiple accept=".docx,.txt,.md,.ts,.tsx,.js,.jsx,.py,.json,.yaml,.yml,.go,.rs,.css,.html">
<div class="flist">${state.files.length?state.files.map((f,i)=>`<div class="frow-file">${ic('file-text')}<span>${esc(f)}</span><span class="sz">${/\.(md|txt|docx)$/i.test(f)?'doc':'code'}</span><button class="icon-btn" type="button" data-remove="${i}" aria-label="Remove ${esc(f)}">${ic('x')}</button></div>`).join(''):`<div class="empty">No files <button class="btn sm" type="button" data-action="sample-files">Use samples</button></div>`}</div></div></section>
<section class="pane"><div class="pane-head"><span><span class="step-n">02</span><strong>Targets</strong></span><small class="mono"><span id="source-count">${state.sources.length}</span> selected</small></div><div class="pane-body">
${SOURCES.map(([id,n,u])=>`<label class="opt"><input type="checkbox" name="source" value="${id}" ${state.sources.includes(id)?'checked':''}>${ic('globe')}<div><strong>${n}</strong><small>${u}</small></div></label>`).join('')}</div></section>
<section class="pane"><div class="pane-head"><span><span class="step-n">03</span><strong>Checks</strong></span></div><div class="pane-body">
${[['public','Public exposure','passage matching','globe'],['risk','Code & doc risks','secrets · PII · logging','shield']].map(([id,t,s,i])=>`<label class="opt"><input type="checkbox" name="check" value="${id}" ${state.checks.includes(id)?'checked':''}>${ic(i)}<div><strong>${t}</strong><small>${s}</small></div></label>`).join('')}
<div class="flow" aria-label="Data boundary"><span class="label">Data boundary</span><div class="ok">${ic('lock')}private text → scan server</div><div class="out">${ic('arrow-up-right')}public URLs → Exa / Tavily</div></div></div></section>
</div>
<section class="pane"><div class="runbar"><div class="summary"><span class="tag">${state.files.length} files</span><span class="tag">${sel.length} targets</span><span class="tag">${state.checks.length} checks</span></div><button class="btn primary" type="submit" ${state.scanRunning?'disabled':''}>${ic('scan-line')}${state.scanRunning?'Scanning…':'Run sample scan'}</button></div>${state.error?`<p class="error" role="alert">${esc(state.error)}</p>`:''}</section>
${state.scanRunning||state.scanLog.length?`<section class="term" aria-label="Scan log"><div class="pane-head">${ic('terminal')}<span class="label">scan log · SCN-0418</span></div><pre role="status">${state.scanLog.join('\n')}${state.scanRunning?'\n<span class="cursor"></span>':''}</pre></section>`:''}
</form>`;wireFiles();}

function runScan(){
const t=n=>`<span class="t">[14:31:${String(n).padStart(2,'0')}]</span>`;
const lines=[`${t(0)} <span class="c">scan.start</span> files=${state.files.length} targets=${state.sources.length} checks=${state.checks.join(',')}`];
state.files.forEach(f=>lines.push(`${t(1)} hash ${esc(f)} <span class="g">ok</span>`));
if(state.checks.includes('public'))state.sources.forEach((id,i)=>{const s=SOURCES.find(x=>x[0]===id);lines.push(`${t(2+i)} fetch ${s[2]} ${id==='paste'?'<span class="r">TIMEOUT 30s</span>':'<span class="g">200</span>'}`)});
if(state.checks.includes('public')&&state.sources.includes('release'))lines.push(`${t(6)} <span class="r">match</span> roadmap.md:5 ↔ relay-notes.example:12 · 30 tok`);
if(state.checks.includes('risk'))lines.push(`${t(8)} <span class="a">rule</span> secrets.log-sensitive-field auth.ts:42`);
lines.push(`${t(9)} <span class="c">scan.done</span>`);
state.scanRunning=true;state.scanLog=[];scan();announce('Running the sample scan');
let i=0;const tick=setInterval(()=>{state.scanLog.push(lines[i++]);if(location.hash==='#scan')scan();if(i>=lines.length){clearInterval(tick);setTimeout(()=>{state.scanRunning=false;location.hash='result';state.scanLog=[];announce('Sample scan completed')},500)}},220);}

function sampleResult(){
const pub=!state.checks.includes('public')?['—','not requested','']:state.sources.includes('release')?['1','sample match','red']:['0',`in ${state.sources.filter(s=>s!=='paste').length} checked sources`,'green'];
const risk=state.checks.includes('risk')?['1','sample risk','amber']:['—','not requested',''];
const partial=state.checks.includes('public')&&state.sources.includes('paste');
main.innerHTML=head('Scan complete',`<span>SCN-0418</span><span>${state.files.map(esc).join(' · ')}</span>`)+
`<div class="result-grid"><div class="kpi ${pub[2]}"><span class="label">Public exposure</span><b>${pub[0]}</b><small>${pub[1]}</small></div><div class="kpi ${risk[2]}"><span class="label">Code risks</span><b>${risk[0]}</b><small>${risk[1]}</small></div><div class="kpi"><span class="label">Coverage</span><b>${partial?'Partial':'Full'}</b><small>${partial?'community paste timed out':'all selected checks ran'}</small></div></div>
<div class="note">${ic('circle-alert')}<span>Sample data — evidence shows the Northwind Relay fixture, not your selected files.</span></div>
<div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap"><a class="btn primary" href="#evidence">View findings ${ic('arrow-right')}</a><a class="btn" href="#scan">Edit setup</a></div>`;}

/* ---------- Code risk / recheck ---------- */
function recheck(){
const r=state.rechecked;
main.innerHTML=head(`Session token written to logs`,`<span class="sev ${r?'low':'med'}">${r?'LOW':'MED'}</span><span>TF-002</span><span>auth.ts:42</span><span class="tag">CWE-532</span><span class="tag">secrets.log-sensitive-field</span>`,`<a class="btn ghost" href="#evidence">${ic('arrow-left')}Findings</a>`)+
`<div class="code-layout"><section class="pane" style="overflow:hidden"><div class="pane-head"><span style="display:flex;gap:10px;align-items:center">${ic('file-text')}<strong class="mono" style="font-size:13px">src/auth.ts</strong></span><span class="tag">suggested patch</span></div>
<pre class="diff" aria-label="Code diff: remove the session token from the log"><code><span><em>39</em><b> </b>const session = await createSession(user);</span><span><em>40</em><b> </b></span><span class="rm"><em>41</em><b>−</b>logger.info('session created', {</span><span class="rm"><em>42</em><b>−</b><span>  userId: user.id, <i class="hl">token: session.token</i></span></span><span class="rm"><em>43</em><b>−</b>});</span><span class="add"><em>41</em><b>+</b>logger.info('session created', {</span><span class="add"><em>42</em><b>+</b>  userId: user.id</span><span class="add"><em>43</em><b>+</b>});</span><span><em>44</em><b> </b>return session;</span></code></pre></section>
<div class="stack">
<section class="pane"><div class="pane-head"><span class="label">Verification</span><span class="st ${r?'ok':'review'}">${r?'NOT DETECTED':'NEEDS FIX'}</span></div><div class="pane-body">
<div class="chain">${`<span class="v bad">${ic('git-commit')}a82c</span><span class="arrow"></span>`}<span class="v ${r?'good':'pending'}">${ic('git-commit')}${r?'b917':'next'}</span></div>
<dl class="kv"><dt>Source</dt><dd>MCP · scan_changes</dd><dt>Host</dt><dd>local model</dd><dt>Scanner</dt><dd>read-only</dd></dl>
<div style="margin-top:16px"><button class="btn primary" data-action="recheck" ${state.rechecking?'disabled':''} style="width:100%">${ic('rotate-ccw')}${state.rechecking?'Rechecking…':r?'Replay recheck':'Run recheck'}</button></div>
${r?`<div class="verdict" role="status">${ic('check')}Not detected in b917</div>`:''}</div></section>
<section class="pane"><div class="pane-head"><span class="label">Check log</span></div><div class="pane-body log">
<div><time>14:35</time><code>scan_changes</code><span>hit · a82c</span></div><div><time>14:36</time><code>explain_finding</code><span>patch proposed</span></div>${r?'<div><time>14:39</time><code>recheck_fix</code><span style="color:var(--green)">clear · b917</span></div>':''}</div></section>
<a class="pane linked" href="#evidence"><span class="sev high">HIGH</span><span>TF-001 public match still <b style="color:var(--red)">OPEN</b></span>${ic('arrow-up-right')}</a>
</div></div>`;}

/* ---------- Egress ---------- */
function activity(){
const rows=[['14:31:02','Exa','relay-notes.example/platform-update','200',420,false],['14:31:03','Tavily','gist.github.com/[sample]','200',610,false],['14:31:04','Tavily','paste.example/relay','TIMEOUT',3000,true]];
main.innerHTML=head('Egress',`<span>Every outbound request from SCN-0417</span>`,`<a class="btn ghost" href="#evidence">${ic('arrow-left')}Findings</a>`)+
`<div class="egress-strip"><div class="kpi"><span class="label">Requests</span><b>3</b><small>2 ok · 1 timeout</small></div><div class="kpi"><span class="label">Providers</span><b>2</b><small>Exa · Tavily</small></div><div class="kpi"><span class="label">Payload</span><b style="font-size:16px;padding-top:4px">public URL</b><small>auth headers masked</small></div><div class="kpi"><span class="label">Private text</span><b style="font-size:16px;padding-top:4px">scan server</b><small>not sent to providers</small></div></div>
<section class="pane" style="overflow:hidden"><div class="table-wrap"><table><thead><tr><th>Time</th><th>Provider</th><th>Req</th><th>Destination</th><th>Status</th><th>Latency</th></tr></thead><tbody>
${rows.map(([t,p,d,s,ms,bad])=>`<tr><td class="mono">${t}</td><td>${p}</td><td><span class="method">EXTRACT</span></td><td class="mono">${d}</td><td><span class="st ${bad?'fail':'ok'}">${s}</span></td><td><span class="lat"><i class="${bad?'bad':''}" style="width:${Math.round(ms/3000*80)}px"></i>${bad?'>30s':ms+'ms'}</span></td></tr>`).join('')}
</tbody></table></div></section>
<div class="boundary">${ic('circle-alert')}<span>Sample ledger. A cloud-hosted MCP assistant has its own separate disclosure boundary.</span></div>`;}

/* ---------- Router & events ---------- */
const NAMES={evidence:'findings',scan:'new-scan',recheck:'TF-002',activity:'egress',result:'scan-complete'};
const NAV={evidence:'evidence',scan:'scan',recheck:'recheck',activity:'activity',result:'scan'};
function route(focus=false){const r=NAMES[location.hash.slice(1)]?location.hash.slice(1):'evidence';
document.querySelectorAll('[data-nav]').forEach(a=>a.dataset.nav===NAV[r]?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current'));
document.querySelector('#crumb').textContent=NAMES[r];({evidence,scan,recheck,activity,result:sampleResult})[r]();
document.title=`Tracefold — ${NAMES[r]}`;if(focus){window.scrollTo(0,0);main.focus({preventScroll:true})}}
window.addEventListener('hashchange',()=>route(true));
main.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
if(b.dataset.tab){state.tab=b.dataset.tab;evidence();document.querySelector('#tab-'+state.tab).focus();return}
if(b.dataset.remove!==undefined){state.files.splice(Number(b.dataset.remove),1);state.error='';scan();return}
switch(b.dataset.action){
case'toggle':state.expanded=!state.expanded;evidence();break;
case'risk':location.hash='recheck';break;
case'coverage':state.expanded=true;state.tab='coverage';evidence();document.querySelector('#tab-coverage').focus();break;
case'review':state.reviewOpen=true;evidence();document.querySelector('#decision').focus();break;
case'cancel-review':state.reviewOpen=false;evidence();break;
case'sample-files':state.files=['roadmap.md','auth.ts'];scan();break;
case'recheck':state.rechecking=true;recheck();announce('Checking the sample correction');setTimeout(()=>{state.rechecked=true;state.rechecking=false;if(location.hash==='#recheck')recheck();announce('Sample recheck complete. Not detected in b917. Public exposure remains open.')},1100);break;}});
main.addEventListener('keydown',e=>{const b=e.target.closest('[role="tab"]');if(!b)return;const tabs=['passages','coverage','history'];let i=tabs.indexOf(state.tab);
if(e.key==='ArrowRight')i=(i+1)%3;else if(e.key==='ArrowLeft')i=(i+2)%3;else if(e.key==='Home')i=0;else if(e.key==='End')i=2;else return;
e.preventDefault();state.tab=tabs[i];evidence();document.querySelector('#tab-'+state.tab).focus()});
main.addEventListener('change',e=>{if(e.target.name==='source'){state.sources=Array.from(main.querySelectorAll('[name="source"]:checked'),x=>x.value);scan()}if(e.target.name==='check'){state.checks=Array.from(main.querySelectorAll('[name="check"]:checked'),x=>x.value);scan()}});
main.addEventListener('submit',e=>{e.preventDefault();
if(e.target.id==='review-form'){const note=document.querySelector('#review-note');if(!note.value.trim()){note.setCustomValidity('Add a reason for your triage decision.');note.reportValidity();return}
state.review=document.querySelector('#decision').value;state.reviewNote=note.value.trim();state.reviewOpen=false;state.tab='history';evidence();announce('Triage saved for this session. Exposure observation is unchanged.');return}
if(e.target.id==='scan-form'){if(!state.files.length)state.error='Choose at least one file or use the samples.';else if(!state.checks.length)state.error='Choose at least one check.';else if(state.checks.includes('public')&&!state.sources.length)state.error='Select a public target to compare against.';else{state.error='';runScan();return}scan()}});
main.addEventListener('input',e=>{if(e.target.id==='review-note')e.target.setCustomValidity('')});
function addFiles(files){const ok=/\.(docx|txt|md|ts|tsx|js|jsx|py|json|yaml|yml|go|rs|css|html)$/i;const names=Array.from(files,x=>x.name);
if(names.some(n=>!ok.test(n)))state.error='Choose DOCX, text, Markdown, or a supported code file.';
else if(state.files.length+names.length>10)state.error='Up to 10 files. Remove one before adding more.';
else{state.files=[...new Set([...state.files,...names])];state.error=''}scan()}
function wireFiles(){document.querySelector('#files').addEventListener('change',e=>addFiles(e.target.files));const d=document.querySelector('#dropzone');
d.addEventListener('dragover',e=>{e.preventDefault();d.classList.add('dragging')});d.addEventListener('dragleave',()=>d.classList.remove('dragging'));d.addEventListener('drop',e=>{e.preventDefault();addFiles(e.dataTransfer.files)});}
route();
