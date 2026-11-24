function renderCrossDocument(){
  const token=generation;
  const live=()=>token===generation;
  $('feature-view').innerHTML=`<section class="panel form-panel">
    <h2>跨文档问答</h2>
    <label class="field">选择 2 至 4 份材料<input id="cd-files" type="file" multiple accept=".docx,.pdf,.txt,.md"></label>
    <label class="field">问题<textarea id="cd-question" rows="3" maxlength="1000" placeholder="例如：两份报告对同一指标采用了哪些不同口径？"></textarea></label>
    <p class="hint">每份材料分析可提取正文的前 6,000 字符。上传内容会交给工作台配置的模型处理。</p>
    <button id="cd-run" class="primary">对照材料</button><p id="cd-status" role="status"></p>
  </section><section id="cd-answer" class="panel reading-notes" hidden></section>`;
  const button=$('cd-run'), status=$('cd-status'), panel=$('cd-answer');
  async function check(id){
    try {
      const task=await api('/api/tasks/'+id);
      if(!live())return;
      if(['queued','running'].includes(task.status)){
        poll=setTimeout(()=>check(id),1500);
        return;
      }
      button.disabled=false;
      const report=task.sentimentResult;
      if(!report){status.textContent=task.result||'问答未完成';return;}
      const sources=new Map(report.sources.map(source=>[source.id,source]));
      panel.append(text('h2','回答'));
      if(!report.findings.length)panel.append(text('p','材料中未找到足够证据。'));
      for(const row of report.findings){
        const source=sources.get(row.sourceId);
        const card=text('article','');
        card.append(text('p',row.summary),text('blockquote',row.quote),
          text('small',source.title+' · '+source.location));
        panel.append(card);
      }
      for(const note of report.failures)panel.append(text('p',note.url+'：'+note.error));
      for(const note of report.notes||[])panel.append(text('p',note.file+' · '+note.text));
      panel.hidden=false;
      status.textContent='分析完成';
    }catch(e){
      if(live()){button.disabled=false;status.textContent=e.message;}
    }
  }
  button.onclick=async()=>{
    const materials=[...$('cd-files').files], question=$('cd-question').value.trim();
    if(materials.length<2||materials.length>4){status.textContent='请选择 2 至 4 份材料。';return;}
    if(!question){status.textContent='请先填写问题。';return;}
    button.disabled=true;
    panel.hidden=true;
    panel.replaceChildren();
    status.textContent='正在上传材料…';
    try {
      const files=[];
      for(const file of materials){
        if(!live())return;
        const upload=await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file});
        files.push(upload.id);
      }
      if(!live())return;
      const job=await api('/api/cross-document/run',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({question,files})});
      if(live()){status.textContent='正在对照材料并核验引用…';check(job.id);}
    }catch(e){
      if(live()){button.disabled=false;status.textContent=e.message;}
    }
  };
}

function renderSentiment(){
  const token=generation;
  $('feature-view').innerHTML=`<section class="panel form-panel">
    <h2>舆情观察</h2>
    <label class="field">观察主题<input id="so-theme" maxlength="200" placeholder="例如：商业银行对新资本规则的回应"></label>
    <label class="field">公开网页链接<textarea id="so-urls" rows="4" placeholder="每行一个文章链接，最多 6 个"></textarea></label>
    <p class="hint">请填写可直接打开的文章页。已提取的正文会交给工作台配置的模型整理。</p>
    <button id="so-run" class="primary">开始观察</button>
    <p id="so-status" role="status"></p>
  </section><section id="so-report" class="panel reading-notes" hidden></section>`;
  const live=()=>token===generation;
  const button=$('so-run'), status=$('so-status'), panel=$('so-report');
  function show(report){
    const sources=new Map(report.sources.map(source=>[source.id,source]));
    const markdown=['# '+report.theme,'观察时间：'+report.observedAt];
    panel.append(text('h2',report.theme),text('p','观察时间：'+report.observedAt));
    if(!report.findings.length){
      const empty='已读取的内容中未发现与主题直接相关的条目。';
      panel.append(text('p',empty));
      markdown.push(empty);
    }
    for(const finding of report.findings){
      const source=sources.get(finding.sourceId);
      const card=text('article',''), link=text('a',source.title);
      link.href=source.url;
      link.target='_blank';
      link.rel='noopener noreferrer';
      card.append(text('p',finding.summary),text('blockquote',finding.quote),link);
      panel.append(card);
      markdown.push(finding.summary,'> '+finding.quote,source.title+'：'+source.url);
    }
    panel.append(text('h3','网页读取情况'));
    for(const source of report.sources){
      const line=source.title+'：已读取'+(source.truncated?'（仅分析前 4,000 字符）':'');
      panel.append(text('p',line));
      markdown.push(line+' · '+source.url);
    }
    for(const failure of report.failures){
      const line=failure.url+'：'+failure.error;
      panel.append(text('p',line));
      markdown.push(line);
    }
    const download=text('button','导出 Markdown');
    download.className='secondary';
    download.onclick=()=>{
      const url=URL.createObjectURL(new Blob([markdown.join('\n\n')],{type:'text/markdown;charset=utf-8'}));
      const link=document.createElement('a');
      link.href=url;
      link.download='舆情观察.md';
      link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    panel.append(download);
    panel.hidden=false;
  }
  async function check(id){
    if(!live())return;
    try {
      const task=await api('/api/tasks/'+id);
      if(!live())return;
      if(['queued','running'].includes(task.status)){
        poll=setTimeout(()=>check(id),1500);
        return;
      }
      button.disabled=false;
      if(task.sentimentResult){
        status.textContent='观察完成';
        show(task.sentimentResult);
      }else status.textContent=task.result||'观察未完成，请重试。';
    }catch(e){
      if(live()){status.textContent=e.message;button.disabled=false;}
    }
  }
  button.onclick=async()=>{
    panel.hidden=true;
    panel.replaceChildren();
    button.disabled=true;
    status.textContent='正在读取网页并整理观察…';
    try {
      const theme=$('so-theme').value.trim();
      const urls=$('so-urls').value.split(/\r?\n/).map(url=>url.trim()).filter(Boolean);
      const job=await api('/api/sentiment/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme,urls})});
      if(live())check(job.id);
    }catch(e){
      if(live()){status.textContent=e.message;button.disabled=false;}
    }
  };
}
function renderPublicSearch(){
  const view=$('feature-view'), token=generation;
  view.innerHTML='<section class="panel"><h2>公开信息检索</h2><form><label class="field">关键词<input name="query" required maxlength="240" placeholder="输入公司、政策或公告标题"></label><button class="primary">搜索</button></form><p role="status"></p><ul></ul></section>';
  const form=view.querySelector('form'), status=view.querySelector('[role=status]'), list=view.querySelector('ul');
  form.onsubmit=async event=>{
    event.preventDefault();
    const button=form.querySelector('button');
    button.disabled=true;
    list.replaceChildren();
    status.textContent='正在搜索公开网页…';
    try{
      const result=await api('/api/research/discover',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:form.elements.query.value})});
      if(token!==generation)return;
      status.textContent=result.items.length?'找到 '+result.items.length+' 个网页':
        (result.failed===result.channels?'搜索渠道暂不可用，请稍后重试。':'本轮没有返回网页，可尝试换用完整标题或机构名称。');
      for(const item of result.items){
        const row=text('li',''), link=text('a',item.title||item.url);
        link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
        row.append(link,text('small',' · '+new URL(item.url).hostname+
          (item.officialFeed?' · 官方公告订阅':item.previouslyRead?' · 历史快评已读取':'')));list.append(row);
      }
    }catch(error){if(token===generation)status.textContent=error.message}
    finally{button.disabled=false}
  };
}
