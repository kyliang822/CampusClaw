'use strict';
const $ = (s, r=document) => r.querySelector(s);
const paths = {
 book:'M3 5c3-1 6 0 9 2 3-2 6-3 9-2v15c-3-1-6 0-9 2-3-2-6-3-9-2z M12 7v15',
 home:'m3 10 9-7 9 7 M5 9v12h5v-7h4v7h5V9',
 folder:'M3 6h7l2 3h9v11H3z',
 database:'M20 6c0 2-16 2-16 0s16-2 16 0v12c0 3-16 3-16 0V6 M4 12c0 3 16 3 16 0',
 upload:'M12 16V3 m-5 5 5-5 5 5 M4 15v6h16v-6',
 search:'M20 20l-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
 grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
 list:'M8 5h13 M8 12h13 M8 19h13 M3 5h1 M3 12h1 M3 19h1',
 shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z m-4 9 3 3 5-6',
 users:'M16 21v-3c0-5-13-5-13 0v3 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M18 4c4 0 4 7 0 7 M19 14c3 1 3 3 3 7',
 moon:'M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12',
 command:'M9 9V5a2 2 0 1 0-2 2h10a2 2 0 1 0-2-2v14a2 2 0 1 0 2-2H7a2 2 0 1 0 2 2z',
 logout:'M9 3H3v18h6 M9 12h12 m-5-5 5 5-5 5',
 calendar:'M3 5h18v16H3z M7 3v4 M17 3v4 M3 10h18',
 check:'m5 12 4 4L19 6',
 eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
 download:'M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5',
 close:'m6 6 12 12 M6 18 18 6',
 arrow:'M4 12h16 m-5-5 5 5-5 5',
 info:'M12 11v6 M12 7h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
 file:'M5 3h9l5 5v13H5z M14 3v6h5 M8 13h8 M8 17h5'
};
const icon = n => `<svg aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[n]||paths.file}"/></svg>`;
const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let accessToken=sessionStorage.getItem('campus-access-token')||'';
function clearAuth(){if(typeof chatAbort!=='undefined'&&chatAbort)chatAbort.abort();accessToken='';sessionStorage.removeItem('campus-access-token');user=null}
let user=null, materials=[], stats={}, view=localStorage.getItem('campus-view')||'list', page=location.pathname==='/chat'?'chat':location.pathname==='/knowledge'?'knowledge':location.pathname==='/materials'?'materials':'home';
const app=$('#app');
if(localStorage.getItem('campus-theme')==='dark') document.documentElement.classList.add('dark');
const brand=()=>`<div class="brand"><div class="brandmark">${icon('book')}</div><div><strong>CampusClaw</strong><small>教 研 智 能 体</small></div></div>`;
function toast(message){const div=document.createElement('div');div.className='toast';div.textContent=message;$('#toasts').append(div);setTimeout(()=>div.remove(),3500)}
async function api(path, options={}){
 const res=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(accessToken?{'Authorization':'Bearer '+accessToken}:{}),...(user?{'X-CSRF-Token':user.csrf}:{}),...options.headers}});
 const data=await res.json();
 if(!res.ok){if(res.status===401&&path!='/api/login'){clearAuth();loginPage()}throw new Error(data.error||'请求失败，请稍后重试。')}
 return data;
}
function loginPage(){
 ++searchSequence; if(knowledgeTimer)clearInterval(knowledgeTimer);
 for(const d of document.querySelectorAll('dialog[open]'))d.close();
 document.title='登录 · CampusClaw';
 app.innerHTML=`<div class="login-shell"><section class="login-art">${brand()}<div><div class="eyebrow">CAMPUSCLAW / 教研协作</div><h1>让每一份教研积累<br>成为下一堂课的底气。</h1><p>连接教师、学生与知识。<br>从安全共享每一份教学材料开始。</p></div><footer>教研材料与知识库 · 迭代 02</footer></section><section class="login-form-side"><form class="login-form"><h2>欢迎回来</h2><p>登录你的 CampusClaw 教研工作台</p><label class="field">账号<input name="username" autocomplete="username" placeholder="请输入教师或学生账号" required maxlength="80"></label><label class="field">密码<input name="password" type="password" autocomplete="current-password" placeholder="请输入密码" required maxlength="128"></label><p class="error" role="alert"></p><button class="primary" type="submit">登录工作台 ${icon('arrow')}</button><div class="login-note">${icon('shield')} 你的身份与班级由学校账号确定。<br>仅可访问所属班级的教学材料。</div></form></section></div>`;
 $('.login-form').onsubmit=async e=>{e.preventDefault();const button=$('button',e.target);button.disabled=true;$('.error',e.target).textContent='';try{const auth=await api('/api/login',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});accessToken=auth.access_token;sessionStorage.setItem('campus-access-token',accessToken);await boot()}catch(err){$('.error',e.target).textContent=err.message;button.disabled=false}};
}
function layout(){
 document.title=(user.role==='teacher'?'教师首页':'学生首页')+' · CampusClaw';
 const teacher=user.role==='teacher';
 app.innerHTML=`<div class="shell"><aside class="sidebar">${brand()}<div class="nav-label">教学空间</div><nav class="nav" aria-label="主导航"><button data-page="home">${icon('home')}工作台</button><button data-page="materials">${icon('folder')}教研材料</button><button data-page="knowledge">${icon('database')}班级知识库</button><button data-page="chat">${icon('book')}知识问答</button></nav><div class="sidebar-bottom"><div class="class-box"><div class="class-title">${icon('users')} ${esc(user.class_name)} · 教学空间</div><p>材料仅向本班师生开放</p></div><div class="sidebar-footer">CampusClaw <span>·</span> 迭代 02</div></div></aside><div class="workspace"><header class="topbar"><div class="crumb">教学空间 <span>/</span><strong id="crumb-title">工作台</strong></div><div class="top-actions"><button class="icon-button" id="command-button" title="快捷操作（⌘K）" aria-label="快捷操作">${icon('command')}</button><button class="icon-button" id="theme-button" title="切换深浅色" aria-label="切换深浅色">${icon('moon')}</button><div class="vertical-line"></div><div class="profile"><div class="avatar">${esc(user.display_name[0])}</div><div><div class="profile-name">${esc(user.display_name)}</div><div class="profile-role">${teacher?'教师':'学生'} · ${esc(user.class_name)}</div></div></div><button class="icon-button" id="logout-button" title="退出登录" aria-label="退出登录">${icon('logout')}</button></div></header><main class="main"><div class="page-head"><div><div class="eyebrow">YOUR TEACHING WORKSPACE</div><h1 id="greeting">你好，${esc(user.display_name)}</h1><p id="intro">让教研有积累，让知识被共享。这里是你的班级教学空间。</p></div><div class="date-label">${icon('calendar')} ${new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'}).format(new Date())}</div></div><section class="stats" aria-label="班级概览"><div class="stat"><div class="stat-icon">${icon('folder')}</div><div><div class="stat-label">本班教研材料</div><div class="stat-value" id="stat-total">0 <small>份</small></div><div class="stat-note">师生共享的教学资源</div></div></div><div class="stat"><div class="stat-icon">${icon('database')}</div><div><div class="stat-label">已入库知识条目</div><div class="stat-value" id="stat-entries">0 <small>条</small></div><div class="stat-note">材料正文已提取并保存</div></div></div><div class="stat"><div class="stat-icon">${icon('shield')}</div><div><div class="stat-label">当前教学空间</div><div class="stat-value">${esc(user.class_name)}</div><div class="stat-note">班级隔离 · 仅本班可见</div></div></div></section><div class="section-grid"><section class="panel"><div class="panel-head"><div><div class="panel-title"><span id="list-title">本班教研材料</span><span class="counter" id="material-count">0</span></div><div class="panel-subtitle" id="list-subtitle">集中管理教学资料，沉淀班级知识</div></div>${teacher?`<button class="primary" data-upload>${icon('upload')}上传材料</button>`:''}</div><div class="toolbar"><label class="search">${icon('search')}<input id="search" placeholder="搜索本班材料…" aria-label="搜索本班材料"><kbd>⌘ K</kbd></label><div class="view-buttons"><button data-view="list" aria-label="列表视图">${icon('list')}</button><button data-view="grid" aria-label="网格视图">${icon('grid')}</button></div></div><div id="materials"></div><div class="panel-foot"><span id="result-count"></span><span>仅显示 ${esc(user.class_name)} 的材料</span></div></section><aside class="aside-stack">${teacher?`<section class="panel upload-panel">${icon('upload')}<h3>分享一份教学灵感</h3><p>上传教案、课堂笔记或教研记录，<br>正文将自动保存至本班知识库。</p><button class="primary" data-upload>${icon('upload')} 上传教研材料</button><div class="upload-formats">TXT / Markdown · 单文件最大 2 MB</div></section>`:''}<section class="panel info-panel"><div class="info-title">${icon('shield')} 我的访问权限</div><div class="info-row"><span>当前身份</span><strong>${teacher?'教师':'学生'}</strong></div><div class="info-row"><span>所属班级</span><strong>${esc(user.class_name)}</strong></div><div class="info-row"><span>材料操作</span><strong>${teacher?'上传 · 查看 · 下载':'查看 · 下载'}</strong></div><div class="info-divider"></div><p class="permission-note">班级资料独立保存，教师与学生共享本班知识，安心协作。</p></section><div class="tip">${icon('info')}<span>进入班级知识库，可检索相关原文并查看材料出处。</span></div></aside></div><footer class="footer"><span>CampusClaw · 教研材料与知识库</span><span>${icon('shield')} 班级数据隔离保护中</span></footer></main></div></div>`;
 document.querySelectorAll('[data-upload]').forEach(b=>b.onclick=uploadDialog);
 document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>changePage(b.dataset.page));
 document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;localStorage.setItem('campus-view',view);renderMaterials()});
 $('#theme-button').onclick=()=>{document.documentElement.classList.toggle('dark');localStorage.setItem('campus-theme',document.documentElement.classList.contains('dark')?'dark':'light')};
 $('#logout-button').onclick=async()=>{try{await api('/api/logout',{method:'POST'});clearAuth();loginPage()}catch(e){toast(e.message)}};
 $('#command-button').onclick=commandDialog;
 $('#search').oninput=renderMaterials;
 setupKnowledge();
 setupChat();
 changePage(page);
}
function changePage(next){page=next;$('.main').classList.toggle('chat-page',page==='chat');$('#chat-panel').hidden=page!=='chat';if(page==='chat')refreshChat();history.replaceState(null,'',page==='home'?'/':'/'+page);document.title=(page==='chat'?'知识问答':page==='knowledge'?'班级知识库':page==='materials'?'教研材料':user.role==='teacher'?'教师首页':'学生首页')+' · CampusClaw';$('#knowledge-panel').hidden=page!=='knowledge';$('.section-grid').hidden=['knowledge','chat'].includes(page);$('.stats').hidden=['knowledge','chat'].includes(page);if(page==='knowledge')refreshIndexStatus();document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$('#crumb-title').textContent={home:'工作台',materials:'教研材料',knowledge:'班级知识库',chat:'知识问答'}[page];$('#greeting').textContent=page==='home'?`你好，${user.display_name}`:page==='materials'?'教研材料':page==='chat'?user.class_name+' · 知识问答':'班级知识库';$('#intro').textContent=page==='home'?'让教研有积累，让知识被共享。这里是你的班级教学空间。':page==='chat'?'基于本班资料回答，每一处引用都可追溯。':page==='materials'?'上传、查看与下载本班教学资料。':'检索本班材料，查看证据，追溯每一处原文。';$('#list-title').textContent=page==='knowledge'?'已入库正文':'本班教研材料';$('#list-subtitle').textContent=page==='knowledge'?'每份材料对应一条知识记录，点击标题查看正文':'集中管理教学资料，沉淀班级知识';renderMaterials()}
const sizeLabel=n=>n<1024?`${n} B`:`${(n/1024).toFixed(1)} KB`;
const dayLabel=s=>s.slice(0,10).replaceAll('-','.');
const fileIcon=m=>`<span class="file-icon ${m.filename.toLowerCase().endsWith('.txt')?'txt':''}">${m.filename.toLowerCase().endsWith('.txt')?'TXT':'MD'}</span>`;
const status=()=>`<span class="status">${icon('check')} 已入库</span>`;
function actions(m){return `<div class="row-actions"><button data-open="${esc(m.id)}" title="查看正文" aria-label="查看 ${esc(m.title)}">${icon('eye')}</button><a href="/api/materials/${encodeURIComponent(m.id)}/download" title="下载材料" aria-label="下载 ${esc(m.title)}">${icon('download')}</a></div>`}
function renderMaterials(){
 if(!$('#materials'))return;
 const q=$('#search').value.toLocaleLowerCase().trim();const list=materials.filter(m=>(m.title+' '+m.filename).toLocaleLowerCase().includes(q));
 $('#stat-total').innerHTML=`${stats.total||0} <small>份</small>`;$('#stat-entries').innerHTML=`${stats.entries||0} <small>条</small>`;
 $('#material-count').textContent=materials.length;$('#result-count').textContent=`共 ${list.length} 份材料${q?' · 搜索结果':''}`;
 document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('selected',b.dataset.view===view);b.setAttribute('aria-pressed',b.dataset.view===view)});
 if(!list.length){$('#materials').innerHTML=`<div class="empty">${icon('folder')}<h3>${q?'没有找到相关材料':'本班还没有教研材料'}</h3><p>${q?'试试其他关键词。':'上传第一份教学资料，开始积累班级知识。'}</p></div>`;return}
 $('#materials').innerHTML=view==='grid'?`<div class="cards">${list.map(m=>`<article class="material-card">${fileIcon(m)}<button class="file-name" data-open="${esc(m.id)}">${esc(m.title)}</button><div class="file-meta">${esc(m.author)} · ${dayLabel(m.created_at)} · ${sizeLabel(m.size)}</div><div class="card-bottom">${status()}${actions(m)}</div></article>`).join('')}</div>`:`<div class="table-wrap"><table><thead><tr><th>材料名称</th><th>上传时间</th><th>知识库状态</th><th>操作</th></tr></thead><tbody>${list.map(m=>`<tr><td><div class="file-cell">${fileIcon(m)}<div><button class="file-name" data-open="${esc(m.id)}">${esc(m.title)}</button><div class="file-meta">${esc(m.author)} · ${sizeLabel(m.size)}${page==='knowledge'?` · ${m.characters} 字`:''}</div></div></div></td><td class="muted">${dayLabel(m.created_at)}</td><td>${status()}</td><td>${actions(m)}</td></tr>`).join('')}</tbody></table></div>`;
 document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>openMaterial(b.dataset.open));
}
async function loadMaterials(){const data=await api('/api/materials');materials=data.materials;stats=data.stats;renderMaterials()}
function safeMarkdown(text){
 const doc=new DOMParser().parseFromString(marked.parse(text,{gfm:true}),'text/html');
 const allowed=new Set(['H1','H2','H3','H4','H5','H6','P','BR','HR','STRONG','EM','DEL','UL','OL','LI','BLOCKQUOTE','PRE','CODE','TABLE','THEAD','TBODY','TR','TH','TD','A','INPUT']);
 for(const el of [...doc.body.querySelectorAll('*')]){
  if(!allowed.has(el.tagName)){el.replaceWith(document.createTextNode(el.textContent));continue}
  const href=el.getAttribute('href');const checked=el.hasAttribute('checked');
  for(const attr of [...el.attributes])el.removeAttribute(attr.name);
  if(el.tagName==='A'&&href&&/^https?:\/\//i.test(href)){el.setAttribute('href',href);el.setAttribute('target','_blank');el.setAttribute('rel','noopener noreferrer')}
  if(el.tagName==='INPUT'){el.setAttribute('type','checkbox');el.setAttribute('disabled','');if(checked)el.setAttribute('checked','')}
 }
 return doc.body.innerHTML;
}
async function openMaterial(id){try{const m=await api(`/api/materials/${encodeURIComponent(id)}`);const d=$('#detail-dialog');d.innerHTML=`<div class="dialog-head"><h2>${esc(m.title)}</h2><button class="icon-button" data-close aria-label="关闭">${icon('close')}</button></div><p class="muted small">${esc(m.author)} · ${esc(user.class_name)} · ${dayLabel(m.created_at)} ${status()}</p><article class="markdown">${m.filename.toLowerCase().endsWith('.md')?safeMarkdown(m.body):`<div class="plain">${esc(m.body)}</div>`}</article><div class="dialog-actions"><a class="download-link" href="/api/materials/${encodeURIComponent(id)}/download">下载原文件 ↓</a></div>`;$('[data-close]',d).onclick=()=>d.close();d.showModal()}catch(e){toast(e.message)}}
function uploadDialog(){
 const d=$('#upload-dialog');
 d.innerHTML=`<form id="upload-form"><div class="dialog-head"><h2>上传教研材料</h2><button class="icon-button" type="button" data-close aria-label="关闭">${icon('close')}</button></div><p class="muted small">材料将保存到 ${esc(user.class_name)}，本班师生均可查看。</p><label class="dropzone">${icon('upload')}<strong>选择教学资料</strong><p>支持 UTF-8 编码的 TXT / Markdown，最大 2 MB</p><input name="file" type="file" accept=".txt,.md" required aria-label="选择教学资料"></label><label class="field">材料标题<input name="title" placeholder="默认使用文件名" maxlength="120"></label><label class="field">正文切分方式<select name="chunk_strategy" aria-label="正文切分方式"><option value="window">自动窗口 · 800 字 / 重叠 100 字</option><option value="paragraph">按空行分段</option><option value="line">按换行</option><option value="sentence">按句号</option><option value="markdown">按 Markdown 标题分章</option><option value="custom">自定义分隔符</option></select></label><label class="field" id="separator-field" hidden>自定义分隔符<input name="chunk_separator" maxlength="20" placeholder="例如：---"></label><p class="split-help">保存原文位置以支持溯源，上传后自动建立向量索引。</p><div id="upload-progress" hidden><progress max="100" value="0"></progress><div class="progress-text">正在上传并入库…</div></div><p class="error" role="alert"></p><div class="dialog-actions"><button type="button" data-cancel>取消</button><button type="submit" class="primary">上传并入库</button></div></form>`;
 $('[data-close]',d).onclick=$('[data-cancel]',d).onclick=()=>d.close();
 $('input[type=file]',d).onchange=e=>{const file=e.target.files[0];if(file&&!$('input[name=title]',d).value)$('input[name=title]',d).value=file.name.replace(/\.(txt|md)$/i,'')};
 $('[name=chunk_strategy]',d).onchange=ev=>{$('#separator-field').hidden=ev.target.value!=='custom'};
 $('#upload-form').onsubmit=async e=>{
 e.preventDefault();const file=$('input[type=file]',d).files[0];const error=$('.error',d);error.textContent='';
 if(!file)return;if(file.size>2*1024*1024){error.textContent='文件大小不能超过 2 MB。';return}if(!/\.(txt|md)$/i.test(file.name)){error.textContent='仅支持 .txt 和 .md 文件。';return}
 const button=$('button[type=submit]',d);button.disabled=true;$('#upload-progress').hidden=false;
 try{
 const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
 await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/materials');xhr.setRequestHeader('Content-Type','application/json');xhr.setRequestHeader('Authorization','Bearer '+accessToken);xhr.setRequestHeader('X-CSRF-Token',user.csrf);xhr.upload.onprogress=ev=>{if(ev.lengthComputable)$('progress',d).value=ev.loaded/ev.total*100};xhr.onload=()=>{let response;try{response=JSON.parse(xhr.responseText)}catch{reject(new Error('服务响应异常，请重试。'));return}if(xhr.status===201)resolve(response);else{if(xhr.status===401){clearAuth();loginPage()}reject(new Error(response.error||'上传失败'))}};xhr.onerror=()=>reject(new Error('网络连接失败，请重试。'));xhr.send(JSON.stringify({filename:file.name,title:$('input[name=title]',d).value,content:btoa(binary),chunk_strategy:$('[name=chunk_strategy]',d).value,chunk_separator:$('[name=chunk_separator]',d).value}))});
 d.close();await loadMaterials();toast('上传成功，正文已切片，向量索引将在后台建立。');refreshIndexStatus();
 }catch(err){error.textContent=err.message}finally{button.disabled=false}
 };
 d.showModal();
}
function commandDialog(){if(!user)return;const d=$('#command-dialog');d.innerHTML=`<div class="dialog-head"><h2>快捷操作</h2><button class="icon-button" data-close aria-label="关闭">${icon('close')}</button></div><div class="command-list"><button data-command="search">${icon('search')} 搜索本班材料</button>${user.role==='teacher'?`<button data-command="upload">${icon('upload')} 上传教研材料</button>`:''}<button data-command="knowledge">${icon('database')} 查看班级知识库</button></div>`;$('[data-close]',d).onclick=()=>d.close();d.querySelectorAll('[data-command]').forEach(b=>b.onclick=()=>{d.close();if(b.dataset.command==='upload')uploadDialog();else if(b.dataset.command==='search')$('#search').focus();else changePage('knowledge')});d.showModal()}
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();commandDialog()}});
async function boot(){try{user=await api('/api/me');layout();await loadMaterials()}catch(e){if(user)toast(e.message);else loginPage()}}
boot();

// Downloads require explicit Authorization too; never put tokens in URLs.
document.addEventListener('click',async e=>{
 const a=e.target.closest('a[href]');if(!a)return;const url=new URL(a.href,location.href);
 if(url.origin!==location.origin||!/^\/api\/materials\/[^/]+\/download$/.test(url.pathname))return;
 e.preventDefault();try{const res=await fetch(url.pathname,{headers:{Authorization:'Bearer '+accessToken}});
 if(!res.ok){if(res.status===401){clearAuth();loginPage()}throw new Error('无法下载材料，请确认登录状态与班级权限。')}
 const blob=await res.blob();const link=document.createElement('a');const objectURL=URL.createObjectURL(blob);link.href=objectURL;
 const disposition=res.headers.get('Content-Disposition')||'';const match=disposition.match(/filename\*=UTF-8''([^;]+)/i);
 link.download=match?decodeURIComponent(match[1]):'材料.txt';link.click();setTimeout(()=>URL.revokeObjectURL(objectURL),1000);
 }catch(err){toast(err.message)}
});
