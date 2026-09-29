/* Retrieval UI uses server-provided excerpts and independently authorized source APIs. */
let knowledgeTimer=null, searchSequence=0;
function setupKnowledge(){
 const holder=document.createElement('section');holder.id='knowledge-panel';holder.hidden=true;
 holder.innerHTML=`<div class="retrieval-head"><div><span class="scope-chip">${icon('shield')} ${esc(user.class_name)} · 仅检索本班</span></div></div><form id="retrieval-form" class="panel retrieval-form"><label class="retrieval-query">${icon('search')}<input id="retrieval-query" required maxlength="500" placeholder="例如：如何帮助学生清晰地表达自己的观点？" aria-label="知识库检索问题"><button class="primary" type="submit">检索本班资料 ${icon('arrow')}</button></label><div class="retrieval-options"><div class="mode-picker" role="group" aria-label="检索模式"><label><input type="radio" name="retrieval-mode" value="hybrid" checked>混合检索 <span>推荐</span></label><label><input type="radio" name="retrieval-mode" value="keyword">关键词</label><label><input type="radio" name="retrieval-mode" value="vector">语义向量</label></div><span class="small muted">最多展示 5 条原文片段</span></div><p id="mode-hint" class="mode-hint">同时匹配文字与语义，通过 RRF 融合排序。</p></form><div class="index-bar"><span id="index-status" role="status">正在读取索引状态…</span>${user.role==='teacher'?'<button id="retry-index" class="text-button" type="button">重试索引</button>':''}</div><p id="retrieval-error" class="error" role="alert"></p><div id="retrieval-results" aria-live="polite"><div class="retrieval-empty">${icon('book')}<h3>每一条结果，都能回到原文</h3><p>材料标题 · 切片序号 · 字符范围 · 原文摘录</p><p class="small muted">没有找到相关依据时，我们会明确告诉你。</p></div></div>`;
 $('.section-grid').before(holder);
 $('#retrieval-form').onsubmit=searchKnowledge;
 document.querySelectorAll('[name=retrieval-mode]').forEach(el=>el.onchange=()=>{$('#mode-hint').textContent={keyword:'只匹配本班原文中的词，不调用嵌入模型。',vector:'查找语义相近的原文，余弦相似度低于 0.35 的结果不展示。',hybrid:'同时匹配文字与语义，通过 RRF 融合排序。'}[el.value]});
 if($('#retry-index'))$('#retry-index').onclick=async()=>{try{await api('/api/retrieval/retry',{method:'POST',body:'{}'});toast('已安排索引重试');refreshIndexStatus()}catch(e){toast(e.message)}};
 if(knowledgeTimer)clearInterval(knowledgeTimer);
 knowledgeTimer=setInterval(()=>{if(user&&page==='knowledge')refreshIndexStatus()},5000);
}
async function refreshIndexStatus(){
 if(!user||!$('#index-status'))return;
 const owner=user.id;try{const s=await api('/api/retrieval/status');if(!user||user.id!==owner||!$('#index-status'))return;
 $('#index-status').textContent=s.enabled?(s.ready&&s.pending_chunks===0?`向量索引就绪 · ${s.indexed_chunks} / ${s.total_chunks} 个切片`:`索引准备中 · ${s.indexed_chunks} / ${s.total_chunks} 个切片${s.message?' · '+s.message:''}`):s.message;
 $('#index-status').className=s.ready&&s.pending_chunks===0?'index-ready':'muted';
 if($('#retry-index'))$('#retry-index').hidden=!s.enabled||s.ready&&s.pending_chunks===0;
 }catch(e){if($('#index-status'))$('#index-status').textContent=e.message}
}
async function searchKnowledge(e){
 e.preventDefault();const query=$('#retrieval-query').value.trim();if(!query)return;
 const mode=$('[name=retrieval-mode]:checked').value;const seq=++searchSequence;const currentUser=user.id;
 const button=$('#retrieval-form button[type=submit]');button.disabled=true;button.textContent='正在检索…';$('#retrieval-error').textContent='';
 try{
 const data=await api('/api/search?'+new URLSearchParams({q:query,mode,limit:'5'}));
 if(seq!==searchSequence||!user||user.id!==currentUser||!$('#retrieval-results'))return;
 if(!data.hits.length){$('#retrieval-results').innerHTML=`<div class="retrieval-empty">${icon('search')}<h3>资料中未找到相关内容</h3><p>试试更具体的问题，或先上传相关的本班教学材料。</p><span class="small muted">未生成答案，也未引用无关资料。</span></div>`;return}
 $('#retrieval-results').innerHTML=`<div class="results-summary"><strong>找到 ${data.hits.length} 条相关原文</strong><span>${{hybrid:'混合检索 · RRF 排序',keyword:'关键词匹配',vector:'语义向量 · 余弦相似度 ≥ 0.35'}[data.mode]}</span></div>`+data.hits.map((h,i)=>`<article class="panel hit-card"><div class="hit-heading"><span class="citation-number">${i+1}</span><div><h3>${esc(h.title)}</h3><div class="source-meta">${esc(h.filename)}<span>切片 #${h.chunk_index}</span><span>第 ${h.start_char+1}–${h.end_char} 字符</span></div></div><button class="source-button" data-source="${esc(h.chunk_id)}">${icon('eye')}定位原文</button></div><blockquote class="hit-excerpt">${esc(h.excerpt)}</blockquote><div class="hit-footer"><span>${h.matched_by.map(p=>p==='keyword'?'关键词命中':'语义命中').join(' + ')}${h.vector_score!==null?` · 相似度 ${h.vector_score.toFixed(3)}`:''}</span><button class="text-button" data-source="${esc(h.chunk_id)}">查看完整材料 ${icon('arrow')}</button></div></article>`).join('');
 document.querySelectorAll('[data-source]').forEach(b=>b.onclick=()=>openSource(b.dataset.source));
 }catch(err){if(seq===searchSequence&&$('#retrieval-error')){$('#retrieval-error').textContent=err.message;$('#retrieval-results').innerHTML=''}}
 finally{if(seq===searchSequence&&$('#retrieval-form')){button.disabled=false;button.innerHTML=`检索本班资料 ${icon('arrow')}`}}
}
async function openSource(chunkId){
 const owner=user.id;try{const s=await api('/api/chunks/'+encodeURIComponent(chunkId));if(!user||user.id!==owner)return;const chars=Array.from(s.original_body);
 const d=$('#detail-dialog');d.innerHTML=`<div class="dialog-head"><h2>${esc(s.title)}</h2><button class="icon-button" data-close aria-label="关闭">${icon('close')}</button></div><p class="source-caption">${esc(user.class_name)} · 切片 #${s.chunk_index} · 第 ${s.start_char+1}–${s.end_char} 字符</p><p class="muted small">以下展示材料原始文本，高亮部分与检索摘录一致。</p><div class="source-document" tabindex="0">${esc(chars.slice(0,s.start_char).join(''))}<mark id="source-highlight">${esc(chars.slice(s.start_char,s.end_char).join(''))}</mark>${esc(chars.slice(s.end_char).join(''))}</div><div class="source-check"><span>原文指纹 SHA-256：${esc(s.body_hash.slice(0,16))}…</span><a href="/api/materials/${encodeURIComponent(s.material_id)}/download">下载原文件 ↓</a></div>`;
 $('[data-close]',d).onclick=()=>d.close();d.showModal();$('#source-highlight').scrollIntoView({block:'center'});
 }catch(e){toast(e.message)}
}
