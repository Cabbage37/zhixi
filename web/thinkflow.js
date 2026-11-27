async function renderThinkFlow(retry = false) {
  const view = $('feature-view'), token = generation;
  view.innerHTML = '<section class="panel"><h2>阅读助手</h2><p role="status">正在打开阅读资料库…</p></section>';
  try {
    let state;
    const started = Date.now();
    do {
      if (Date.now() - started > 180000) throw Error('阅读资料库启动超时，请重新打开。');
      state = await api('/api/thinkflow/open', {method:'POST',body:JSON.stringify({retry})});
      retry = false;
      if (token !== generation) return;
      if (!state.ready) await new Promise(resolve => setTimeout(resolve, 1000));
    } while (!state.ready && token === generation);
    if (token !== generation) return;
    const url = new URL(state.url);
    if(window.thinkFlowNotebook)url.searchParams.set('notebook',window.thinkFlowNotebook);
    else url.pathname='/marginalia/';
    window.thinkFlowNotebook=null;
    const link = text('a','独立窗口 ↗');
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener';
    const frame = document.createElement('iframe');
    frame.title = '知析阅读工作区'; frame.src = url.href;
    frame.className = 'embedded-frame';
    const shell = document.createElement('section'); shell.className = 'embedded-workspace';
    const toolbar = document.createElement('div'); toolbar.className = 'embedded-toolbar';
    const focus = text('button','专注阅读');focus.className='secondary';
    focus.onclick=()=>{const expanded=shell.classList.toggle('expanded');focus.textContent=expanded?'退出专注':'专注阅读';focus.setAttribute('aria-pressed',String(expanded))};
    toolbar.append(text('strong','阅读资料库'),focus,link);
    shell.append(toolbar);
    if(url.pathname==='/marginalia/'){
      const form=document.createElement('form');
      form.className='reader-url-import';
      const input=document.createElement('input');
      input.type='url';input.required=true;
      input.placeholder='粘贴网页、公众号文章或合集链接';
      input.setAttribute('aria-label','网页、公众号文章或合集链接');
      const submit=text('button','导入网址');submit.className='primary';
      const paste=text('button','粘贴正文');paste.type='button';paste.className='secondary';
      const status=text('span','');status.setAttribute('role','status');
      form.append(input,submit,paste,status);
      function selectArticle(collection){
        const dialog=document.createElement('dialog');dialog.className='reader-article-dialog';
        const heading=text('h2',collection.title);heading.id='reader-collection-heading';
        dialog.setAttribute('aria-labelledby',heading.id);
        const picker=document.createElement('form');
        const select=document.createElement('select');select.required=true;
        const prompt=new Option('请选择一篇文章','',true,true);prompt.disabled=true;select.add(prompt);
        for(const article of collection.articles)select.add(new Option(article.title,article.url));
        const label=text('label','合集文章（'+collection.articles.length+' 篇）');label.append(select);
        const confirm=text('button','导入所选文章');confirm.className='primary';
        const cancel=text('button','关闭');cancel.type='button';cancel.className='secondary';
        const feedback=text('p','');feedback.setAttribute('role','status');
        cancel.onclick=()=>dialog.close();
        dialog.onclose=()=>dialog.remove();
        picker.append(label,confirm,cancel,feedback);
        dialog.append(heading,picker);shell.append(dialog);dialog.showModal();
        picker.onsubmit=async event=>{
          event.preventDefault();confirm.disabled=true;select.disabled=true;feedback.textContent='正在提取正文…';
          try{
            await openArticle({url:select.value});
            dialog.close();
          }catch(error){
            const current=collection.articles.find(article=>article.url===select.value);
            const original=text('a','打开微信原文 ↗');
            original.href=current.url;original.target='_blank';original.rel='noopener';
            const copy=text('button','粘贴所选文章正文');copy.type='button';copy.className='secondary';
            copy.onclick=()=>{dialog.close();pasteArticle(current)};
            feedback.replaceChildren(text('span',error.message+' '),original,document.createTextNode(' '),copy);
          }
          finally{confirm.disabled=false;select.disabled=false}
        };
      }
      async function openArticle(payload){
        const book=await api('/api/reader/import-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        if(token!==generation)return;
        if(Array.isArray(book.articles)){
          status.textContent='';
          selectArticle(book);
          return;
        }
        const destination=new URL(url);
        destination.searchParams.set('book',book.id);
        frame.src=destination.href;
        status.textContent='已导入：'+book.title;input.value='';
      }
      function pasteArticle(article={}){
        const dialog=document.createElement('dialog');dialog.className='reader-article-dialog';
        const heading=text('h2','粘贴文章正文');heading.id='reader-paste-heading';
        dialog.setAttribute('aria-labelledby',heading.id);
        const editor=document.createElement('form');
        const title=document.createElement('input');title.required=true;title.maxLength=300;title.value=article.title||'';
        const source=document.createElement('input');source.type='url';source.value=article.url||input.value.trim();
        const content=document.createElement('textarea');content.required=true;content.rows=10;
        for(const [name,field] of [['文章标题',title],['原文链接（可选）',source],['正文',content]]){
          const label=text('label',name);label.append(field);editor.append(label);
        }
        const feedback=text('p','');feedback.setAttribute('role','status');
        const save=text('button','导入正文');save.className='primary';
        const cancel=text('button','取消');cancel.type='button';cancel.className='secondary';
        cancel.onclick=()=>dialog.close();
        dialog.onclose=()=>dialog.remove();
        editor.append(save,cancel,feedback);
        dialog.append(heading,editor);shell.append(dialog);dialog.showModal();
        editor.onsubmit=async event=>{
          event.preventDefault();save.disabled=true;feedback.textContent='正在导入…';
          try{
            await openArticle({url:source.value.trim(),title:title.value.trim(),content:content.value.trim()});
            dialog.close();
          }catch(error){feedback.textContent=error.message}
          finally{save.disabled=false}
        };
      }
      paste.onclick=()=>pasteArticle();
      form.onsubmit=async event=>{
        event.preventDefault();submit.disabled=true;paste.disabled=true;status.textContent='正在提取正文…';
        try{
          await openArticle({url:input.value.trim()});
        }catch(error){status.textContent=error.message}
        finally{submit.disabled=false;paste.disabled=false}
      };
      shell.append(form);
    }
    shell.append(frame);view.replaceChildren(shell);
  } catch (error) {
    if (token !== generation) return;
    const button = text('button','重新打开'); button.className = 'secondary';
    button.onclick = () => renderThinkFlow(true);
    view.firstElementChild.replaceChildren(text('p',error.message),button);
  }
}

function addThinkFlowImport(task, filename) {
  const trigger = text('button','加入阅读笔记本');
  trigger.className = 'secondary';
  $('downloads').append(trigger);
  trigger.onclick = async () => {
    const dialog = document.createElement('dialog');
    const select = document.createElement('select');
    select.setAttribute('aria-label','目标阅读笔记本');
    const status = text('p','正在读取笔记本…');
    status.setAttribute('role','status');
    const confirm = text('button','加入笔记本'), close = text('button','关闭');
    confirm.disabled = true;
    close.onclick = () => dialog.close();
    dialog.append(text('h3','将成果加入阅读笔记本'),text('p',filename),select,status,confirm,close);
    document.body.append(dialog);
    dialog.onclose = () => dialog.remove();
    dialog.showModal();
    try {
      const entries = (await api('/api/my-work')).filter(row => row.state==='阅读笔记本');
      for (const entry of entries) select.add(new Option(entry.title,entry.id));
      status.textContent = entries.length ? '' : '请先到阅读助手新建一个笔记本。';
      confirm.disabled = !entries.length;
      confirm.onclick = async () => {
        confirm.disabled = true;
        status.textContent = '正在导入材料…';
        try {
          const result = await api('/api/thinkflow/import-result',{method:'POST',
            body:JSON.stringify({task,filename,notebook:select.value})});
          status.textContent = result.embedded?'材料已加入，可以检索。':'原件已加入，请在笔记本中查看处理状态。';
          const open = text('button','打开笔记本');
          open.onclick = () => { dialog.close(); window.thinkFlowNotebook=result.id; openModule(modules[2],'阅读助手'); };
          confirm.replaceWith(open);
        } catch (error) {status.textContent=error.message;confirm.disabled=false;}
      };
    } catch(error) {status.textContent=error.message;}
  };
}
