let screenshotPreviewURL;
function renderScreenshotTable(){
 const token=generation,view=$('feature-view');let file=null,sequence=0,configured=false;
 if(screenshotPreviewURL){URL.revokeObjectURL(screenshotPreviewURL);screenshotPreviewURL=null}
 view.innerHTML=`<section class="panel"><div class="section-title"><div><h2>截图转表格</h2><p class="hint">把图片中的数据，变成可以继续编辑的表格。</p></div><span class="status-tag">先复核，再导出</span></div><div class="steps"><span><b>1</b>上传截图</span><span><b>2</b>识别与复核</span><span><b>3</b>导出表格</span></div><p id="screenshot-config" class="hint">正在检查识别接口…</p>${uploadHTML('选择表格截图（PNG / JPG / WEBP）','screenshot','.png,.jpg,.jpeg,.webp')}<p class="hint">尽量截取完整表格，包含表头和单位。当前每次识别一张图片，可提取其中多张表。</p><div class="submit-row"><small id="screenshot-info">尚未上传截图</small><button class="primary" id="screenshot-run" disabled>识别表格 →</button></div><p id="screenshot-error" role="alert"></p></section><div class="screenshot-review"><section class="panel screenshot-original"><h3>原始截图</h3><div class="screenshot-image-wrap" id="screenshot-image">上传后在此对照原图</div><label class="field">图片缩放<input id="screenshot-zoom" type="range" min="50" max="200" value="100"></label></section><section class="panel screenshot-editor"><h3>可编辑表格</h3><div id="screenshot-result" class="hint">识别完成后，可以直接修改单元格，并复核疑点。</div></section></div>`;
 const ready=()=>{$('screenshot-run').disabled=!file||!configured};
 api('/api/screenshot/config').then(c=>{if(token!==generation)return;configured=c.configured;$('screenshot-config').textContent=c.configured?`识别模型：${c.model} · 图片将发送至 ${c.destination}`:`识别模型：${c.model||'尚未配置'} · 请填写项目 .env.vision 中的对应密钥并重启服务`;ready()}).catch(e=>{if(token===generation)$('screenshot-config').textContent=e.message});
 $('screenshot-zoom').oninput=e=>{const img=$('screenshot-image').querySelector('img');if(img)img.style.width=e.target.value+'%'};
 view.querySelector('[data-upload]').onchange=async e=>{
  const f=e.target.files[0];if(!f)return;const request=++sequence;file=null;ready();$('screenshot-error').textContent='';$('screenshot-result').textContent='正在读取图片…';delete $('screenshot-result').dataset.taskId;
  try{const d=await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f});if(token!==generation||request!==sequence)return;
   const info=await api('/api/screenshot/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fileId:d.id})});if(token!==generation||request!==sequence)return;
   file=d;view.querySelector('[data-list]').textContent='✓ '+d.name;$('screenshot-info').textContent=`${info.width} × ${info.height} 像素`;
   if(screenshotPreviewURL)URL.revokeObjectURL(screenshotPreviewURL);screenshotPreviewURL=URL.createObjectURL(f);const img=document.createElement('img');img.src=screenshotPreviewURL;img.alt='待识别表格原图';$('screenshot-image').replaceChildren(img);$('screenshot-result').textContent='图片已准备好，点击“识别表格”开始。';
  }catch(err){if(token===generation&&request===sequence){$('screenshot-error').textContent=err.message;$('screenshot-result').textContent='图片读取失败，请重新上传'}}finally{if(token===generation&&request===sequence)ready();e.target.value=''}
 };
 $('screenshot-run').onclick=async()=>{
  if(!file)return;$('screenshot-run').disabled=true;$('screenshot-error').textContent='';$('screenshot-result').textContent='正在识别，请稍候…';delete $('screenshot-result').dataset.taskId;
  try{const t=await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module:'office',files:[file.id],screenshot:{},prompt:'截图转表格：调用已配置的图像识别工具，保留原始文字、行列和合并关系，标注疑点，返回可供用户复核的结构化表格。'})});if(token!==generation)return;$('output-panel').hidden=false;watch(t.id)}
  catch(err){if(token===generation)$('screenshot-error').textContent=err.message}finally{if(token===generation)ready()}
 };
}
function showScreenshotResult(task){
 const host=$('screenshot-result');if(!host||host.dataset.taskId===task.id)return;host.dataset.taskId=task.id;
 const original=document.createElement('img');original.alt='待复核表格原图';original.src='/screenshot-original/'+task.id;$('screenshot-image').replaceChildren(original);
 const tables=structuredClone(task.tableResult.tables);let index=0;
 host.innerHTML=`<p class="hint">${esc(task.tableResult.notice)}</p><label class="field">选择表格<select id="screenshot-table-select">${tables.map((t,i)=>`<option value="${i}">${esc(t.name)}</option>`).join('')}</select></label><div class="screenshot-toolbar"><button class="secondary" data-edit="row">＋ 行</button><button class="secondary" data-edit="col">＋ 列</button><button class="secondary" data-edit="unmerge">取消本表合并</button><button class="secondary" id="screenshot-confirm-all">本表已全部复核</button></div><p id="screenshot-review-count"></p><div id="screenshot-grid" class="screenshot-grid"></div><p class="hint">点击单元格修改，勾选表示已对照原图复核。橙色格为识别疑点；合并区域只有左上角可编辑。所有内容按文本保留，避免前导零和日期被自动改写。</p><div class="submit-row"><label class="field">输出格式<select id="screenshot-format"><option value="xlsx">Excel（保留合并）</option><option value="csv">CSV（多表打包ZIP）</option></select></label><button class="primary" id="screenshot-export">导出表格 →</button></div><p class="hint">CSV不保留合并和样式；以公式符号开头的文本会加前缀防止误执行。需要完整保真请选Excel。</p><p id="screenshot-export-error" role="alert"></p><div id="screenshot-download"></div>`;
 function covered(t,r,c){return t.merges.find(m=>r>=m.r&&r<m.r+m.rowspan&&c>=m.c&&c<m.c+m.colspan&&(r!==m.r||c!==m.c))}
 function counts(){let pending=0;for(const t of tables)for(let r=0;r<t.rows.length;r++)for(let c=0;c<t.rows[r].length;c++){if(!covered(t,r,c)&&t.rows[r][c].uncertain&&!t.rows[r][c].reviewed)pending++}$('screenshot-review-count').textContent=pending?`还有 ${pending} 个识别疑点待复核`:'识别疑点已复核，仍建议核对全部数据';$('screenshot-export').disabled=pending>0}
 function draw(){const t=tables[index];const table=document.createElement('table');
  t.rows.forEach((row,r)=>{const tr=document.createElement('tr');const number=text('th',String(r+1));tr.append(number);
   row.forEach((cell,c)=>{if(covered(t,r,c))return;const td=document.createElement('td'),merge=t.merges.find(m=>m.r===r&&m.c===c);if(merge){td.rowSpan=merge.rowspan;td.colSpan=merge.colspan}
    const input=document.createElement('textarea');input.rows=2;input.value=cell.text;input.setAttribute('aria-label',`第${r+1}行第${c+1}列`);
    const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=cell.reviewed;label.append(check,document.createTextNode('已复核'));
    const style=()=>td.classList.toggle('uncertain',cell.uncertain&&!cell.reviewed);style();
    input.oninput=()=>{cell.text=input.value;cell.reviewed=false;check.checked=false;style();counts()};check.onchange=()=>{cell.reviewed=check.checked;style();counts()};
    td.append(input,label);if(cell.uncertain)td.append(text('small',cell.reason||'请核对原图'));tr.append(td);
   });table.append(tr);
  });$('screenshot-grid').replaceChildren(table);counts();
 }
 $('screenshot-table-select').onchange=e=>{index=Number(e.target.value);draw()};
 host.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>{const t=tables[index],blank=()=>({text:'',uncertain:true,reason:'新增单元格，请填写并复核',reviewed:false});
  if(b.dataset.edit==='row'&&t.rows.length<300)t.rows.push(t.rows[0].map(blank));
  if(b.dataset.edit==='col'&&t.rows[0].length<50)t.rows.forEach(row=>row.push(blank()));
  if(b.dataset.edit==='unmerge')t.merges=[];draw();
 });
 $('screenshot-confirm-all').onclick=()=>{tables[index].rows.forEach(row=>row.forEach(c=>c.reviewed=true));draw()};
 $('screenshot-export').onclick=async()=>{const button=$('screenshot-export');button.disabled=true;$('screenshot-export-error').textContent='';
  try{const copy=structuredClone(tables);for(const t of copy)for(let r=0;r<t.rows.length;r++)for(let c=0;c<t.rows[r].length;c++)if(covered(t,r,c))t.rows[r][c].reviewed=true;
   const result=await api('/api/screenshot/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({taskId:task.id,tables:copy,format:$('screenshot-format').value})});
   if(!document.contains(host))return;const link=text('a','↓ '+result.name);link.href=result.url;link.download=result.name;$('screenshot-download').replaceChildren(link);
  }catch(e){if(document.contains(host))$('screenshot-export-error').textContent=e.message}finally{if(document.contains(host))counts()}
 };draw();
}
