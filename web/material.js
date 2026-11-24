const materialChecks=['错别字','编号跳跃','日期冲突','单位不一致','图文数字不一致','计算与勾稽关系','统计口径一致性','结论与数据一致性','名称与术语一致性','引用与资料来源','残留与遗漏'];
function renderMaterialCheck(){
 const token=generation,view=$('feature-view');let file=null,serial=0;
 view.innerHTML=`<section class="panel"><div class="section-title"><div><h2>材料体检</h2><p class="hint">找出疑似问题，带着原文依据逐项复核。</p></div><span class="status-tag">原稿不改动</span></div>${uploadHTML('上传待检查材料（DOCX / PDF / TXT / MD）','material','.docx,.pdf,.txt,.md')}<p class="hint">默认执行全部 11 类检查，覆盖文字、数字、口径、结论、引用及遗漏。</p><details class="hint"><summary>查看检查范围</summary><p>${materialChecks.map(esc).join('、')}</p></details><details class="hint"><summary>补充术语与检查要求（可选）</summary><div class="material-fields"><label class="field">专有名词与术语表<textarea id="material-glossary" rows="3" placeholder="每行填写：正名 = 变体1, 变体2&#10;例如：招商金控 = 招商金空"></textarea></label><label class="field">补充检查规则<textarea id="material-rules" rows="3" placeholder="例如：本材料报告期为2026年第三季度，金额口径以表头为准。"></textarea></label></div></details><div id="material-preview" class="hint">上传后可预览提取内容和检查范围。旧版 DOC 请先另存为 DOCX。</div><div class="submit-row"><small>保留原文，输出问题清单和修改建议</small><button class="primary" id="material-run" disabled>开始体检 →</button></div><p id="material-error" role="alert"></p></section><div id="material-results"></div>`;
 const ready=()=>{$('material-run').disabled=!file};
 view.querySelector('[data-upload]').onchange=async e=>{
  const f=e.target.files[0];if(!f)return;const request=++serial;file=null;ready();$('material-error').textContent='';$('material-preview').textContent='正在读取材料…';view.querySelector('[data-list]').textContent='';
  try{const d=await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f});if(token!==generation||request!==serial)return;
   const source=await api('/api/material/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fileId:d.id})});if(token!==generation||request!==serial)return;
   file=d;view.querySelector('[data-list]').textContent='✓ '+d.name;
   $('material-preview').innerHTML=`<p>已读取 ${source.blocks.length} 个文本块</p>${source.limitations.map(l=>`<p class="material-limit">${esc(l)}</p>`).join('')}<details><summary>查看原文提取预览</summary>${source.blocks.slice(0,8).map(b=>`<div class="material-excerpt"><strong>${esc(b.location)}</strong><p>${esc(b.text)}</p></div>`).join('')}</details>`;
  }catch(err){if(token===generation&&request===serial){$('material-error').textContent=err.message;$('material-preview').textContent='读取失败，请重新上传。'}}finally{if(token===generation&&request===serial)ready();e.target.value=''}
 };
 $('material-run').onclick=async()=>{
  if(!file)return;const checks=[...materialChecks];
  $('material-run').disabled=true;$('material-error').textContent='';$('material-results').replaceChildren();
  try{const t=await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module:'office',files:[file.id],material:{checks,rules:$('material-rules').value,glossary:$('material-glossary').value},prompt:'材料体检：全面执行十一类检查并遵循术语规范，定位原文，生成问题清单及最小修改建议，不修改原稿。'})});if(token!==generation)return;history.replaceState(null,'','#material='+t.id);$('output-panel').hidden=false;watch(t.id)}
  catch(err){if(token===generation)$('material-error').textContent=err.message}finally{if(token===generation)ready()}
 };
}
function showMaterialReport(task){
 const host=$('material-results');if(!host||host.dataset.taskId===task.id)return;host.dataset.taskId=task.id;
 const report=task.materialReport,states=task.reviewStates||{},lookup=Object.fromEntries(report.blocks.map(b=>[b.id,b]));
 host.innerHTML=`<section class="panel material-report"><div class="section-title"><h2>体检结果</h2><span>${report.issues.length} 项待复核发现</span></div><p class="hint">已检查 ${report.coverage.reviewed} / ${report.coverage.total} 个文本块。未发现问题不代表材料完全无误。</p>${report.limitations.length?`<details class="material-limits" open><summary>检查范围与未核验内容</summary>${report.limitations.map(l=>`<p>${esc(l)}</p>`).join('')}</details>`:''}<div class="material-filters"><label>类型 <select id="material-filter"><option>全部</option>${report.checks.map(c=>`<option>${esc(c)}</option>`).join('')}</select></label><label>复核状态 <select id="material-state-filter"><option>全部</option><option>待复核</option><option>已确认</option><option>忽略</option></select></label></div><p class="hint">复核状态自动保存在当前任务；下载报告保留初始检查结果。</p><div class="material-review-grid"><div id="material-issues"></div><section class="material-source"><h3>原文定位</h3><div id="material-source-body">点击问题的“定位原文”，在这里查看上下文。</div></section></div><p id="material-review-error" role="alert"></p></section>`;
 if(/\.docx$/i.test(report.name)){const b=text('button','进入 AI 在线审校 →');b.className='primary';b.onclick=()=>openMaterialEditor(task.id);host.querySelector('.section-title').append(b)}
 function locate(issue){const target=$('material-source-body');target.replaceChildren();for(const ref of issue.evidence){const b=lookup[ref.blockId];const title=text('strong',b.location);target.append(title);const pre=document.createElement('pre');const at=b.text.indexOf(ref.quote);pre.append(document.createTextNode(b.text.slice(0,at)));const mark=text('mark',ref.quote);pre.append(mark,document.createTextNode(b.text.slice(at+ref.quote.length)));target.append(pre)}target.scrollIntoView({behavior:'smooth',block:'nearest'})}
 function render(){
  const category=$('material-filter').value,state=$('material-state-filter').value;
  const issues=report.issues.filter(i=>(category==='全部'||i.category===category)&&(state==='全部'||(states[i.id]||'待复核')===state));
  $('material-issues').innerHTML=issues.length?'':`<p class="empty">${report.issues.length?'当前筛选下没有问题。':'所选范围内未发现可定位问题，请同时查看未核验内容。'}</p>`;
  for(const issue of issues){const card=document.createElement('article');card.className='material-issue';
   card.innerHTML=`<div class="section-title"><strong>${esc(issue.category)}</strong><span class="status-tag">${esc(issue.severity)}优先级 · ${esc(issue.certainty||'待核实')}</span></div><p class="hint">${esc(issue.evidence.map(r=>r.location).join(' / '))}</p><blockquote>${esc(issue.evidence[0].quote)}</blockquote><p>${esc(issue.reason)}</p><p><strong>建议：</strong>${esc(issue.suggestion)}</p><div class="material-actions"><button class="secondary" data-locate>定位原文</button><label>复核 <select data-state>${['待复核','已确认','忽略'].map(s=>`<option ${(states[issue.id]||'待复核')===s?'selected':''}>${s}</option>`).join('')}</select></label></div>`;
   card.querySelector('[data-locate]').onclick=()=>locate(issue);
   card.querySelector('[data-state]').onchange=async e=>{const select=e.target;select.disabled=true;try{await api('/api/material/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({taskId:task.id,issueId:issue.id,state:select.value})});states[issue.id]=select.value;render()}catch(err){$('material-review-error').textContent=err.message;select.value=states[issue.id]||'待复核'}finally{select.disabled=false}};
   $('material-issues').append(card);
  }
 }
 $('material-filter').onchange=render;$('material-state-filter').onchange=render;render();
}
