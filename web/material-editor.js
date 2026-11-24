let materialOfficeEditor=null,officeConnection=null;
function officeRpc(action,payload={}){
 return new Promise((resolve,reject)=>{
  const c=officeConnection;if(!c?.target){reject(Error('编辑器插件未连接'));return}
  const id=crypto.randomUUID();const timer=setTimeout(()=>{c.pending.delete(id);reject(Error('编辑器响应超时'))},15000);
  c.pending.set(id,{resolve,reject,timer});c.target.postMessage({type:'zhixi-office-command',nonce:c.nonce,id,action,payload},location.origin);
 });
}
window.addEventListener('message',e=>{
 const c=officeConnection;if(!c||e.origin!==location.origin)return;
 if(e.data?.type==='zhixi-office-ready'&&!c.target){c.target=e.source;e.source.postMessage({type:'zhixi-office-connect',nonce:c.nonce},location.origin);c.onReady();return}
 if(e.source!==c.target||e.data?.nonce!==c.nonce||e.data?.type!=='zhixi-office-result')return;
 const p=c.pending.get(e.data.id);if(!p)return;clearTimeout(p.timer);c.pending.delete(e.data.id);e.data.result?.error?p.reject(Error(e.data.result.error)):p.resolve(e.data.result);
});
async function openMaterialEditor(taskId){
 const host=$('material-results'),token=generation;host.innerHTML='<section class="panel">正在连接在线Word编辑服务…</section>';
 try{
  const d=await api('/api/editor/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({taskId})});if(token!==generation)return;
  host.innerHTML=`<section class="material-editor"><div class="editor-top"><strong>AI 在线审校</strong><span id="editor-count"></span><button id="editor-batch">批量接受非实质修改</button><button id="editor-highlight">显示问题高亮</button><button id="editor-clear">清除审校高亮</button><button id="editor-compare">原稿对照</button><button id="editor-undo">撤销</button><button id="editor-redo">重做</button><a href="/editor-download/${d.sid}/original.docx" download="原稿.docx">下载原稿</a><button id="editor-export" class="primary">保存并导出 DOCX</button><button id="editor-repurpose">修订稿用于一稿多用</button></div><div class="editor-locks"><label><input type="checkbox" id="editor-lock-numbers" ${d.lockNumbers?'checked':''}> 锁定数字</label><label>保护术语（逗号分隔）<input id="editor-terms" value="${esc(d.terms.join(','))}"></label><button id="editor-protection">更新保护设置</button></div><p id="editor-error" role="alert"></p><div class="editor-columns"><nav id="editor-outline"><h3>文档目录</h3><p>等待编辑器连接…</p></nav><div class="editor-docs"><div id="office-editor"></div><div id="office-original" hidden></div></div><section id="editor-issues"><h3>AI 审校问题</h3></section></div></section>`;
  function confirmEdit(message){
    return new Promise(resolve=>{
      const dialog=document.createElement('dialog');
      const form=document.createElement('form');form.method='dialog';
      const cancel=text('button','取消');cancel.value='cancel';
      const apply=text('button','确认修改');apply.value='apply';apply.className='primary';
      form.append(cancel,apply);dialog.append(text('h2','确认审校操作'),text('pre',message),form);
      host.append(dialog);
      dialog.addEventListener('close',()=>{resolve(dialog.returnValue==='apply');dialog.remove();},{once:true});
      dialog.showModal();cancel.focus();
    });
  }
  let ignored=new Set(),applied=new Set(),ready=false;const report=d.report;
  const paintHighlights=()=>officeRpc('highlight',{issues:report.issues.filter(i=>!applied.has(i.id)&&!ignored.has(i.id)).map(i=>({id:i.id,anchor:i.anchor,color:['yellow','cyan','green','magenta'][materialChecks.indexOf(i.category)%4]}))});
  const error=e=>{const field=$('editor-error');if(field)field.textContent=e.message||String(e)};
  const call=(route,data)=>api('/api/editor/'+route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sid:d.sid,...data})});
  async function refresh(result){
   const snapshot=result||await officeRpc('snapshot');const texts=snapshot.paragraphs.map(p=>p.text);applied=new Set();
   for(const issue of report.issues){const a=issue.anchor;if(a&&typeof issue.replacement==='string'){const changed=a.paragraphText.slice(0,a.start)+issue.replacement+a.paragraphText.slice(a.end);if(changed!==a.paragraphText&&texts.includes(changed))applied.add(issue.id)}}
   $('editor-count').textContent=`共 ${report.issues.length} 项 · 已修改 ${applied.size} · 已忽略 ${ignored.size} · 待处理 ${report.issues.filter(i=>!applied.has(i.id)&&!ignored.has(i.id)).length}`;
   const outline=$('editor-outline');outline.innerHTML='<h3>文档目录</h3>';
   snapshot.paragraphs.filter(p=>p.text&&(p.level<9||p.index===0)).slice(0,100).forEach(p=>{const b=text('button',p.text.slice(0,45));b.onclick=()=>officeRpc('locate',{anchor:{paragraphText:p.text,quote:p.text}}).catch(error);outline.append(b)});
   renderIssues();
  }
  async function apply(issue,confirmed=false){
   if(issue.substantive&&!confirmed&&!await confirmEdit('该建议涉及实质性内容。确认应用以下修改？\n原文：'+issue.evidence[0].quote+'\n改为：'+issue.replacement))return;
   await officeRpc('clearHighlights');const change=await call('validate',{issueId:issue.id,confirmed:confirmed||issue.substantive});await officeRpc('apply',change);ignored.delete(issue.id);await refresh();
  }
  function renderIssues(){const panel=$('editor-issues');panel.innerHTML='<h3>AI 审校问题</h3>';
   for(const issue of report.issues){const card=document.createElement('article');card.className='editor-issue';card.style.borderLeftColor=['#ca7b37','#4c83a8','#a06e99','#5e9782'][materialChecks.indexOf(issue.category)%4];
    card.innerHTML=`<strong>${esc(issue.category)}</strong><small>${applied.has(issue.id)?'已修改':ignored.has(issue.id)?'已忽略':'待处理'}</small><blockquote>${esc(issue.evidence[0].quote)}</blockquote><p>${esc(issue.reason)}</p><p>建议：${esc(issue.replacement??issue.suggestion)}</p><p class="hint">${esc(issue.locationStatus||'需手动定位')}</p><div><button data-locate>定位原文</button><button data-accept ${!ready||!issue.editable||applied.has(issue.id)?'disabled':''}>接受修改</button><button data-ignore>忽略</button><button data-manual>手动修改</button></div>`;
    const locate=()=>officeRpc('locate',{anchor:issue.anchor}).catch(error);card.querySelector('[data-locate]').onclick=locate;card.querySelector('[data-manual]').onclick=()=>officeRpc('clearHighlights').then(locate).catch(error);card.querySelector('[data-accept]').onclick=()=>apply(issue).catch(error);card.querySelector('[data-ignore]').onclick=()=>{ignored.add(issue.id);refresh().catch(error)};panel.append(card);
   }
  }
  const controls=host.querySelectorAll('.editor-top button,.editor-locks button');
  controls.forEach(button=>button.disabled=true);
  $('editor-error').textContent='正在打开 Word 并连接审校工具，连接后即可编辑和导出。';
  const slow=setTimeout(()=>{
    if(token===generation&&!ready)$('editor-error').textContent='Word 仍在连接。若长时间无响应，请重新打开在线审校。';
  },25000);
  officeConnection={nonce:crypto.randomUUID(),target:null,pending:new Map(),onReady:async()=>{
    try{
      await refresh();await paintHighlights();
      if(token!==generation)return;
      ready=true;controls.forEach(button=>button.disabled=false);renderIssues();
      $('editor-error').textContent='';
    }catch(e){if(token===generation)error(e)}finally{clearTimeout(slow)}
  }};
  $('editor-highlight').onclick=()=>officeRpc('clearHighlights').then(paintHighlights).catch(error);
  $('editor-clear').onclick=()=>officeRpc('clearHighlights').catch(error);
  let originalEditor=null;$('editor-compare').onclick=async()=>{try{if(originalEditor){originalEditor.destroyEditor();originalEditor=null;host.querySelector('.editor-docs').classList.remove('comparing');return}const cfg=await call('original',{});host.querySelector('.editor-docs').classList.add('comparing');$('office-original').hidden=false;originalEditor=new DocsAPI.DocEditor('office-original',cfg)}catch(e){error(e)}};
  $('editor-undo').onclick=()=>officeRpc('undo').then(refresh).catch(error);$('editor-redo').onclick=()=>officeRpc('redo').then(refresh).catch(error);
  $('editor-batch').onclick=async()=>{const selected=report.issues.filter(i=>i.editable&&!i.substantive&&!applied.has(i.id)&&!ignored.has(i.id));if(!selected.length)return;if(!await confirmEdit(`确认接受 ${selected.length} 项非实质修改？数字和术语锁仍有效。`))return;try{for(const i of selected)await apply(i,true)}catch(e){error(e)}};
  $('editor-protection').onclick=async()=>{if(!await confirmEdit('确认更新数字及术语保护设置？解除保护后，相应内容可被修改。'))return;try{await call('protect',{confirmed:true,lockNumbers:$('editor-lock-numbers').checked,terms:$('editor-terms').value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean)});$('editor-error').textContent='保护设置已更新'}catch(e){error(e)}};
  async function deliverRevision(repurpose){
    const buttons=[$('editor-export'),$('editor-repurpose')];
    buttons.forEach(button=>button.disabled=true);
    try{
      await officeRpc('clearHighlights');
      const request=await call('save',{});
      let saved=false;
      for(let i=0;i<30;i++){
        const state=await api('/api/editor/state/'+d.sid);
        if(state.saveError)throw Error(state.saveError);
        if(request.unchanged||state.saved>request.previousSaved){saved=true;break;}
        await new Promise(r=>setTimeout(r,1000));
      }
      if(!saved)throw Error('保存尚未完成，请稍后重试');
      if(token!==generation)return;
      const url='/editor-download/'+d.sid+'/current.docx';
      if(repurpose){
        const response=await fetch(url);
        if(!response.ok)throw Error('无法读取已保存的修订稿。');
        const file=new File([await response.blob()],'修订稿.docx');
        if(token===generation)useOfficeFile(file,'一稿多用');
      }else{
        const link=document.createElement('a');link.href=url;link.download='修订稿.docx';link.click();
      }
    }catch(e){error(e);}finally{buttons.forEach(button=>button.disabled=false);}
  }
  $('editor-export').onclick=()=>deliverRevision(false);
  $('editor-repurpose').onclick=()=>deliverRevision(true);
  if(!window.DocsAPI)await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=d.server+'/web-apps/apps/api/documents/api.js';script.onload=resolve;script.onerror=()=>reject(Error('ONLYOFFICE脚本加载失败'));document.head.append(script)});
  materialOfficeEditor?.destroyEditor();materialOfficeEditor=new DocsAPI.DocEditor('office-editor',{...d.config,events:{onError:e=>error(Error(e.data?.errorDescription||'文档服务错误'))}});renderIssues();
 }catch(e){host.innerHTML=`<section class="panel"><h2>在线审校暂未启动</h2><p>${esc(e.message)}</p><p>现有体检报告和下载不受影响。需要本地 ONLYOFFICE Docs 服务就绪后才能进行真实 Word 编辑。</p></section>`}
}

if(/^#material=[a-zA-Z0-9]+$/.test(location.hash)){openModule(modules.find(m=>m.id==='office'));openFeature('材料体检');$('output-panel').hidden=false;watch(location.hash.split('=')[1]);}
