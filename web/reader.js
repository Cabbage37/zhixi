async function renderExcerpts(){
  const token=generation;
  $('feature-view').innerHTML=`<section class="panel reading-notes">
    <div class="reading-heading"><h2>知识摘录</h2><button id="ex-export" class="secondary" disabled>导出当前结果</button></div>
    <div class="reading-search"><input id="ex-search" type="search" placeholder="搜索摘录、材料或出处" aria-label="搜索摘录"><select id="ex-source" aria-label="按材料筛选"><option value="">全部材料</option></select></div>
    <p id="ex-status" role="status">正在读取本地摘录…</p><div id="ex-results"></div>
  </section>`;
  try {
    const groups=await api('/api/reader/excerpts');
    if(token!==generation)return;
    const source=$('ex-source'), search=$('ex-search'), results=$('ex-results'), download=$('ex-export');
    for(const group of groups){
      const option=text('option',group.name);
      option.value=group.id;
      source.append(option);
    }
    let visible=[];
    function draw(){
      const query=search.value.trim().toLowerCase();
      visible=groups
        .filter(group=>!source.value||source.value===group.id)
        .flatMap(group=>group.notes.map(note=>({group,note})))
        .filter(({group,note})=>[group.name,note.location,note.quote,note.answer||''].some(value=>value.toLowerCase().includes(query)));
      results.replaceChildren();
      for(const {group,note} of visible){
        const card=text('article','');
        const link=text('button','查看原文 · '+note.location);
        link.className='secondary';
        link.onclick=()=>{
          window.readerFocus={sid:group.id,citation:note};
          openFeature('阅读助手');
        };
        card.append(text('strong',group.name),text('blockquote',note.answer||note.quote),link);
        results.append(card);
      }
      $('ex-status').textContent=visible.length?`共 ${visible.length} 条摘录`:groups.length?'没有匹配的摘录。':'暂无摘录。在阅读助手中选中文字并保存摘录后，即可在这里查看。';
      download.disabled=!visible.length;
    }
    source.onchange=search.oninput=draw;
    download.onclick=()=>{
      const md='# 知识摘录\n\n'+visible.map(({group,note})=>
        '材料：'+group.name+' · '+note.location+'\n\n> '+(note.answer||note.quote).replace(/\n/g,'\n> ')
      ).join('\n\n');
      const url=URL.createObjectURL(new Blob([md],{type:'text/markdown;charset=utf-8'}));
      const link=document.createElement('a');
      link.href=url;
      link.download='知识摘录.md';
      link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    draw();
  } catch(e) {
    if(token===generation)$('ex-status').textContent=e.message;
  }
}

function renderReader(){
  const focus=window.readerFocus;window.readerFocus=null;
  history.replaceState(null,'','#reader');
  const token=generation,view=$('feature-view');let source=null,selected=null,busy=false,original=false;
  const live=()=>token===generation;
  const post=(path,body)=>api('/api/reader/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  view.innerHTML=`<section class="panel reader-import"><div><h2>阅读助手</h2><p class="hint">读懂材料，留下有出处的思考。</p></div><label class="secondary reader-upload">＋ 导入材料<input id="rd-file" type="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp" hidden></label><input id="rd-url" type="url" placeholder="或粘贴公开文章链接" aria-label="公开文章链接"><button id="rd-import" class="secondary">导入链接</button><button id="rd-new" class="secondary">新阅读</button><button id="rd-learn" class="secondary" disabled>教我学 / 考考我</button><p id="rd-status" role="status"></p></section><div class="reading-workspace"><section class="panel reading-source"><div class="reading-heading"><h2 id="rd-name">原文阅读</h2><button class="secondary" id="rd-toggle" hidden>查看原件</button></div><div class="reading-search"><input id="rd-search" placeholder="搜索原文关键词" aria-label="搜索原文"><span id="rd-count"></span></div><p class="hint" id="rd-limit">支持 PDF、DOCX、TXT、MD 和截图。选中单段中的文字，可针对选段提问或摘录。</p><div id="rd-document" class="reading-document"><div class="reading-empty">从一份材料开始<br><small>导入后，原文与 AI 回答会并排呈现。</small></div></div><div id="rd-original" class="reading-document" hidden></div></section><section class="panel reading-assistant"><div class="reading-heading"><h2>与材料对话</h2><span class="status-tag">当前材料优先</span></div><div id="rd-chat" class="reading-chat"><p class="hint">回答将附原文依据；扩写和改写会标为生成建议。</p></div><div id="rd-selection" class="reading-selection" hidden><span></span><button id="rd-clear" class="secondary">取消选段</button><button id="rd-note" class="secondary">保存摘录</button></div><div class="reading-compose"><label>阅读操作 <select id="rd-mode">${['问答','总结','分析','扩写','改写'].map(x=>`<option>${x}</option>`).join('')}</select></label><textarea id="rd-question" rows="3" maxlength="4000" placeholder="例如：作者的核心观点是什么？有哪些数据支持？" aria-label="阅读问题"></textarea><div class="submit-row"><small>可基于上一轮继续追问</small><button id="rd-ask" class="primary" disabled>发送 →</button></div></div></section></div><section class="panel reading-notes"><div class="reading-heading"><h2>我的摘录</h2><button id="rd-use" class="secondary" disabled>摘录用于一稿多用</button><button id="rd-export" class="secondary" disabled>导出摘录</button></div><p class="hint">在原文中拖选一句话，再点“保存摘录”。已保存的内容可在“知识摘录”按材料查找。</p><div id="rd-notes"></div></section>`;
  const actions=document.createElement('div');
  actions.className='reader-actions';actions.hidden=true;view.append(actions);
  for(const label of ['问 AI','解释','总结','保存摘录']){
    const btn=text('button',label);btn.className='secondary';
    btn.onmousedown=e=>e.preventDefault();
    btn.onclick=()=>{actions.hidden=true;if(label==='保存摘录')return $('rd-note').click();
      $('rd-mode').value=label==='总结'?'总结':'问答';
      if(label==='问 AI')return $('rd-question').focus();
      $('rd-question').value=label==='解释'?'请用通俗的语言解释选中的原文。':'请简要总结选中的原文。';$('rd-ask').click()
    };actions.append(btn)
  }
  view.querySelector('.reading-assistant .reading-heading').append($('rd-learn'));
  $('rd-question').placeholder='针对原文提问，或继续追问…';
  function status(message){if(live())$('rd-status').textContent=message}
  function lock(value){busy=value;if(!live())return;['rd-file','rd-import','rd-new'].forEach(id=>$(id).disabled=value);$('rd-ask').disabled=value||!source;$('rd-learn').disabled=value||!source}
  function clearSelection(){actions.hidden=true;selected=null;$('rd-selection').hidden=true}
  function locate(cite){
    original=false;$('rd-original').hidden=true;$('rd-document').hidden=false;$('rd-toggle').textContent='查看原件';$('rd-search').value='';drawSource();
    const el=[...$('rd-document').querySelectorAll('[data-block]')].find(e=>e.dataset.block===cite.blockId);
    if(!el)return;const p=el.querySelector('p'),value=p.textContent,at=value.indexOf(cite.quote);if(at<0){status('原文已变化，无法定位这条引用');return}p.replaceChildren(document.createTextNode(value.slice(0,at)),text('mark',cite.quote),document.createTextNode(value.slice(at+cite.quote.length)));el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.add('reading-active');
  }
  function drawSource(){
    const q=$('rd-search').value.trim(),list=source.blocks.filter(b=>!q||b.text.toLowerCase().includes(q.toLowerCase()));
    $('rd-count').textContent=q?`${list.length} 处`:`${source.blocks.length} 个文本块`;
    $('rd-document').replaceChildren(...list.map(b=>{const box=document.createElement('article');box.dataset.block=b.id;box.className='reading-block';box.append(text('small',b.location),text('p',b.text));return box}));
    if(!list.length)$('rd-document').append(text('p','未找到匹配内容。'));
  }
  function drawNotes(){
    $('rd-notes').replaceChildren(...source.notes.map(n=>{const box=document.createElement('article');box.append(text('blockquote',n.answer||n.quote));const btn=text('button','↗ '+n.location);btn.className='secondary';btn.onclick=()=>locate(n);box.append(btn);return box}));$('rd-use').disabled=$('rd-export').disabled=!source.notes.length;
  }
  function showAnswer(r){
    const box=document.createElement('article');box.className='reading-answer';box.append(text('small',['扩写','改写'].includes(r.mode)?'AI 生成建议 · 请复核后使用':'AI 回答 · 基于可提取原文'),text('p',r.answer));
    r.citations.forEach((c,i)=>{const btn=text('button',`[${i+1}] ${c.location} · ${c.quote.slice(0,40)}`);btn.className='reading-citation';btn.title=c.quote;btn.onclick=()=>locate(c);box.append(btn)});
    const copy=text('button','复制回答');copy.className='secondary';copy.onclick=async()=>{try{await navigator.clipboard.writeText(r.answer);status('已复制回答')}catch{status('复制失败，请直接选择回答文字复制')}};box.append(copy);
    if(r.taskId && r.citations.length){
      const save=text('button','保存回答到知识摘录');save.className='secondary';
      save.onclick=async()=>{save.disabled=true;try{const notes=await post('note',{sid:source.id,answerId:r.taskId});if(live()){source.notes=notes;drawNotes();save.textContent='已存入知识摘录'}}catch(e){save.disabled=false;status(e.message)}};box.append(save)
    }
    $('rd-chat').append(box);$('rd-chat').scrollTop=$('rd-chat').scrollHeight;
  }
  function display(data){
    view.querySelector('.reader-tutor')?.remove();view.querySelector('.reading-assistant').classList.remove('tutoring');$('rd-learn').textContent='教我学 / 考考我';source=data;clearSelection();localStorage.setItem('zhixi-reader',source.id);$('rd-name').textContent=source.name;$('rd-limit').textContent=source.limitations.join(' ');$('rd-search').value='';drawSource();drawNotes();
    $('rd-chat').replaceChildren();(source.history||[]).forEach(r=>{$('rd-chat').append(text('div',r.question));showAnswer(r)});
    original=false;$('rd-original').hidden=true;$('rd-document').hidden=false;$('rd-toggle').textContent='查看原件';$('rd-toggle').hidden=!['.pdf','.png','.jpg','.jpeg','.webp'].includes(source.kind);
    $('rd-original').replaceChildren();if(!$('rd-toggle').hidden){const el=document.createElement(source.kind==='.pdf'?'iframe':'img');el.src='/reader-preview/'+source.id;el.title='原始材料';el.alt='导入的截图';$('rd-original').append(el)}
    $('rd-ask').disabled=busy;$('rd-learn').disabled=busy;status('材料已导入，可以开始阅读和提问。');
  }
  async function importData(body){lock(true);status('正在提取材料；截图识别可能需要稍等…');try{const data=await post('import',body);if(live())display(data)}catch(e){status(e.message)}finally{lock(false)}}
  $('rd-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;lock(true);status('正在上传…');try{const f=await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file});if(live())await importData({fileId:f.id})}catch(e){status(e.message)}finally{lock(false);if(live())$('rd-file').value=''}};
  $('rd-import').onclick=()=>{const url=$('rd-url').value.trim();if(!url)return status('请填写公开文章链接');importData({url})};
  $('rd-learn').onclick=()=>{if(!source||busy)return;
    const panel=view.querySelector('.reading-assistant');
    const existing=panel.querySelector('.reader-tutor');
    if(existing){const opened=panel.classList.toggle('tutoring');existing.hidden=!opened;$('rd-learn').textContent=opened?'返回对话':'教我学 / 考考我';return}
    const host=document.createElement('div');host.className='reader-tutor';panel.append(host);panel.classList.add('tutoring');
    $('rd-learn').textContent='返回对话';window.learningSeed={sourceId:source.id,name:source.name,selection:selected};
    renderLearning(host,()=>host.isConnected);};
  $('rd-new').onclick=()=>{localStorage.removeItem('zhixi-reader');generation++;renderReader()};
  $('rd-search').oninput=()=>{if(source)drawSource()};
  $('rd-toggle').onclick=()=>{original=!original;$('rd-original').hidden=!original;$('rd-document').hidden=original;$('rd-toggle').textContent=original?'返回文本':'查看原件'};
  $('rd-document').onmouseup=()=>{
    actions.hidden=true;const s=window.getSelection();if(!s||s.isCollapsed)return;const range=s.getRangeAt(0),node=range.commonAncestorContainer,nodeEl=node.nodeType===1?node:node.parentElement,block=nodeEl.closest('[data-block]');
    if(!block||!$('rd-document').contains(block)){status('请在同一文本块内选择片段');return}
    if(!source)return;const quote=s.toString().trim(),b=source.blocks.find(b=>b.id===block.dataset.block);if(!quote||!b.text.includes(quote)){status('请只选取原文文字');return}
    const rect=range.getBoundingClientRect();actions.hidden=false;
    actions.style.left=Math.max(8,Math.min(rect.left,innerWidth-actions.offsetWidth-8))+'px';
    actions.style.top=Math.max(6,Math.min(innerHeight-actions.offsetHeight-6,rect.top-actions.offsetHeight-5))+'px';
    selected={blockId:b.id,quote};$('rd-selection').hidden=false;$('rd-selection').querySelector('span').textContent='选段：'+quote;status('已选中片段，下一次提问将结合此选段。');
  };
  $('rd-document').onkeyup=$('rd-document').onmouseup;
  $('rd-document').onscroll=()=>{actions.hidden=true};
  $('rd-clear').onclick=clearSelection;
  $('rd-note').onclick=async()=>{if(!source||!selected)return;try{const notes=await post('note',{sid:source.id,selection:selected});if(live()){source.notes=notes;drawNotes();status('已保存至本机摘录')}}catch(e){status(e.message)}};
  $('rd-use').onclick=()=>{
    const body=source.notes.map(note=>(note.answer||note.quote)+'\n来源：'+source.name+' · '+note.location).join('\n\n');
    useOfficeFile(new File([body],'阅读摘录.md',{type:'text/markdown'}),'一稿多用');
  };
  $('rd-export').onclick=()=>{const md='# '+source.name+'\n\n'+source.notes.map(n=>'> '+(n.answer||n.quote).replace(/\n/g,'\n> ')+'\n\n来源：'+n.location).join('\n\n');const url=URL.createObjectURL(new Blob([md],{type:'text/markdown;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='阅读摘录.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
  async function watchReader(id){
    if(!live())return;
    try{const job=await api('/api/tasks/'+id);if(!live())return;
      if(job.status==='completed'){if(!job.readerResult)throw Error('未返回有效阅读结果');showAnswer(job.readerResult);localStorage.removeItem('zhixi-reader-pending');status('回答已完成，点击依据可定位原文。');lock(false);return}
      if(['failed','interrupted'].includes(job.status)){localStorage.removeItem('zhixi-reader-pending');throw Error(job.result||'阅读任务失败')}
      status('AI 正在阅读材料并核对依据…');poll=setTimeout(()=>watchReader(id),1800);
    }catch(e){status(e.message);lock(false)}
  }
  $('rd-ask').onclick=async()=>{
    if(!source||busy)return;const question=$('rd-question').value.trim();if(!question)return status('请输入问题或处理要求');lock(true);status('正在提交…');
    try{const job=await post('ask',{sid:source.id,mode:$('rd-mode').value,question,selection:selected});if(!live())return;localStorage.setItem('zhixi-reader-pending',JSON.stringify({sid:source.id,id:job.id}));const bubble=text('div',question);bubble.className='reading-question';$('rd-chat').append(bubble);$('rd-question').value='';watchReader(job.id)}catch(e){status(e.message);lock(false)}
  };
  const saved=focus?.sid||localStorage.getItem('zhixi-reader');if(saved){lock(true);api('/api/reader/state/'+encodeURIComponent(saved)).then(data=>{if(!live())return;display(data);lock(false);if(focus?.citation)locate(focus.citation);let pending;try{pending=JSON.parse(localStorage.getItem('zhixi-reader-pending'))}catch{}if(pending?.sid===saved&&!data.history.some(h=>h.taskId===pending.id)){lock(true);watchReader(pending.id)}}).catch(e=>{status(e.message);lock(false)})}
}

if(location.hash==='#reader')openModule(modules.find(m=>m.id==='knowledge'));
