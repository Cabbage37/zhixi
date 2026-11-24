const researchMarkdown = window.markdownit({html:false, breaks:true});
function displayResearchReport(element, content) {
  element.classList.add('research-report');
  element.innerHTML = researchMarkdown.render(content);
  for (const link of element.querySelectorAll('a[href]')) {
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  }
}
function renderQuickResearch(){
  const view=$('feature-view');
  view.innerHTML='<section class="panel"><h2>金融事件快评</h2><label for="qr-question">你想研究什么事件？</label><textarea id="qr-question" rows="3" maxlength="2000" placeholder="例如：香港金管局最新公布的措施，对银行有什么影响？"></textarea><div class="submit-row"><label>研究深度 <select id="qr-depth"><option>快速了解</option><option selected>标准快评</option><option>深度研究</option></select></label><button class="primary" id="qr-run">开始联网研究 →</button></div><details><summary>补充材料与模型选项</summary><input type="file" id="qr-file" accept=".docx,.pdf,.txt,.md"><label><input type="checkbox" id="qr-alt">本次改用原主模型</label></details><p id="qr-message" role="status"></p><div id="qr-history"></div></section>';
  const previous=JSON.parse(localStorage.getItem('zhixi-quick-history')||'[]');
  for(const item of previous){
    const btn=text('button',item.question);btn.className='secondary';
    btn.onclick=()=>{$('output-panel').hidden=false;watch(item.id)};
    $('qr-history').append(btn);
  }
  $('qr-run').onclick=async()=>{
    const field=$('qr-question'),question=field.value.trim(),button=$('qr-run'),msg=$('qr-message');
    if(!question){msg.textContent='请填写机构、事件或你关注的问题。';field.focus();return}
    button.disabled=true;const token=generation;
    try{
      const file=$('qr-file').files[0], files=[];
      const options={depth:$('qr-depth').value,alternate:$('qr-alt').checked?false:undefined,parent:field.dataset.parent,url:field.dataset.url};
      if(file)files.push((await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file})).id);
      const job=await api('/api/tasks',{method:'POST',body:JSON.stringify({module:'research',feature:'研究简报',prompt:question,files,quickResearch:options})});
      localStorage.setItem('zhixi-quick-history',JSON.stringify([{question,id:job.id},...previous].slice(0,20)));
      if(token!==generation)return;
      renderQuickResearch();$('output-panel').hidden=false;watch(job.id);
    }catch(error){msg.textContent=error.message}finally{button.disabled=false}
  };
}
function startFromOpinion(item){
  const field=$('qr-question');field.dataset.url=item.url;field.value=item.title+'。请核实事件，并分析原因和影响。';field.focus();
}
function quickResearchActions(job){
  const result=$('result'), lines=job.result.split('\n'), urls=new Map();
  for(const line of lines){
    const match=line.match(/^〔(\d+)〕 .*?(https?:\/\/\S+)$/);
    if(match)urls.set(match[1],match[2]);
  }
  result.replaceChildren();
  const sections=new Map();let section='',evidence=null;
  for(const line of lines){
    if(line.startsWith('## ')){
      section=line.slice(3);const block=text('section','');block.append(text('h3',section==='已披露事实'?'已披露事实 · 公告与原文':section));
      sections.set(section,block);evidence=null;continue;
    }
    if(!line.trim()||!section)continue;
    const el=text(line.startsWith('#')?'h3':'p','');
    for(const part of line.replace(/^#{1,2} |^- /,'').split(/(〔\d+〕)/)){
      const url=urls.get(part.slice(1,-1));
      if(url&&part.startsWith('〔')){const a=text('a',part);a.href=url;a.target='_blank';a.rel='noopener noreferrer';el.append(a)}
      else el.append(document.createTextNode(part));
    }
    const block=sections.get(section);
    if(line.trimStart().startsWith('原文〔')){
      if(!evidence){evidence=text('details','');evidence.append(text('summary','核对引文'));block.append(evidence)}
      evidence.append(el);
    }else{evidence=null;block.append(el)}
  }
  result.append(text('h3',job.prompt));
  for(const key of ['分析判断','已披露事实','媒体观点','待核实事项','来源']){
    if(!sections.has(key))continue;
    if(key==='来源'){
      const details=text('details','');details.append(text('summary','查看来源清单'),sections.get(key));result.append(details);
    }else result.append(sections.get(key));
  }
  const follow=text('button','继续追问'),read=text('button','保存到阅读助手');
  for(const b of [follow,read])b.className='secondary';
  $('downloads').append(follow,read);
  follow.onclick=()=>{const field=$('qr-question');field.dataset.parent=job.id;field.value='';field.focus();$('qr-message').textContent='正在追问「'+job.prompt+'」'};
  read.onclick=async()=>{
    read.disabled=true;
    try{
      const name='金融事件快评.md',res=await fetch('/download/'+job.id+'/'+encodeURIComponent(name));
      if(!res.ok)throw Error('快评文件读取失败');
      const upload=await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(name)},body:await res.blob()});
      const source=await api('/api/reader/import',{method:'POST',body:JSON.stringify({fileId:upload.id})});
      localStorage.setItem('zhixi-reader',source.id);
      openModule(modules.find(m=>m.id==='knowledge'));openFeature('阅读助手');
    }catch(error){$('qr-message').textContent=error.message}finally{read.disabled=false}
  };
}
function renderInstitutionResearch(name){
  const view=$('feature-view'), token=generation;
  const key='zhixi-institution:'+name;
  let latest=localStorage.getItem(key), parent=null;
  view.innerHTML='<section class="panel"><header><h2></h2><button type="button" class="secondary" id="institution-new">新对话</button></header><div class="institution-chat" role="log" aria-label="研究对话"></div><form class="research-composer"><div class="composer-box"><textarea aria-label="研究问题" name="question" rows="2" maxlength="2000" required placeholder="输入研究问题，或继续追问…"></textarea><div class="composer-tools"><input hidden name="document" type="file" accept=".pdf,.docx,.txt,.md"><button type="button" class="composer-add" aria-label="添加补充材料" title="添加 PDF、Word 或文本材料">＋</button><button type="button" class="composer-file" hidden></button><button type="submit" class="composer-send" aria-label="发送问题" title="发送问题">↑</button></div></div><p role="status"></p></form></section>';
  view.querySelector('h2').textContent=name;
  const form=view.querySelector('form'),button=form.querySelector('[type=submit]'),status=form.querySelector('p');
  const upload=form.elements.document, chip=form.querySelector('.composer-file'), question=form.elements.question;
  form.querySelector('.composer-add').onclick=()=>upload.click();
  upload.onchange=()=>{chip.hidden=!upload.files.length;chip.textContent=upload.files.length?upload.files[0].name+' ×':'';chip.title='移除附件'};
  chip.onclick=()=>{upload.value='';upload.onchange()};
  question.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();if(question.value.trim()&&!button.disabled)form.requestSubmit()}};
  const chat=view.querySelector('[role=log]'), reset=view.querySelector('#institution-new');
  const active=()=>token===generation;
  function append(turn, answer){
    const question=text('article','');question.className='institution-turn institution-question';
    question.append(text('strong','你'),text('p',turn.prompt));chat.append(question);
    const response=text('article','');response.className='institution-turn';
    response.append(text('strong','研究助手'),text('div',answer));
    if(turn.status==='completed'){
      displayResearchReport(response.querySelector('div'), answer);
      const link=text('a','下载本轮分析');link.href='/download/'+turn.id+'/'+encodeURIComponent('金融机构分析.md');link.download='金融机构分析.md';response.append(link);
    }
    chat.append(response);
    chat.scrollTop=chat.scrollHeight;
    return response.querySelector('div');
  }
  async function observe(id, target){
    while(active()&&latest===id){
      const turn=await api('/api/tasks/'+id);
      if(!active()||latest!==id)return;
      if(turn.status==='completed'){
        const url='/download/'+id+'/'+encodeURIComponent('金融机构分析.md');
        const report=await fetch(url);
        if(!report.ok)throw Error('本轮结果暂不可读取');
        const content=await report.text();
        if(!active()||latest!==id)return;
        displayResearchReport(target, content);
        const link=text('a','下载本轮分析');link.href=url;link.download='金融机构分析.md';target.after(link);
        chat.scrollTop=chat.scrollHeight;parent=id;status.textContent='可以继续追问。';return;
      }
      if(!['running','queued'].includes(turn.status)){
        target.textContent=turn.result||'本轮未完成。';
        if(parent)localStorage.setItem(key,parent);else localStorage.removeItem(key);
        latest=parent;form.elements.question.value=turn.prompt;
        status.textContent='问题已放回输入框。可直接重试；如上一轮有附件，请重新选择。';return;
      }
      await new Promise(resolve=>setTimeout(resolve,2200));
    }
  }
  reset.onclick=()=>{localStorage.removeItem(key);renderInstitutionResearch(name);};
  form.onsubmit=async event=>{
    event.preventDefault();
    const prompt=form.elements.question.value.trim();
    if(!prompt||button.disabled)return;
    button.disabled=reset.disabled=true;
    try{
      const files=[],file=form.elements.document.files[0];
      if(file)files.push((await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file})).id);
      if(!active())return;
      const task=await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module:'research',institutionResearch:name,institutionParent:parent,prompt,files})});
      localStorage.setItem(key,task.id);
      if(!active())return;
      latest=task.id;form.reset();upload.onchange();status.textContent='正在研究…';
      await observe(task.id,append(task,'正在分析…'));
    }catch(error){if(active())status.textContent=error.message;}
    finally{if(active())button.disabled=reset.disabled=false;}
  };
  if(latest){
    button.disabled=reset.disabled=true;
    (async()=>{
      const chain=[];let id=latest;
      while(id&&chain.length<12){
        const task=await api('/api/tasks/'+id);
        if(!active()||task.institutionResearch!==name)return;
        chain.unshift(task);id=task.institutionParent;
      }
      for(const turn of chain){
        if(!active())return;
        if(turn.status==='completed'){
          const result=await fetch('/download/'+turn.id+'/'+encodeURIComponent('金融机构分析.md'));
          if(!result.ok)throw Error('历史结果暂不可读取');
          const answer=await result.text();
          if(!active())return;
          append(turn,answer);parent=turn.id;
        }else await observe(turn.id,append(turn,'正在恢复本轮…'));
      }
    })().catch(error=>{if(active())status.textContent=error.message;})
      .finally(()=>{if(active())button.disabled=reset.disabled=false;});
  }
}
