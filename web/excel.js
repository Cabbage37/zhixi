function renderExcelCharts(){
 const token=generation,view=$('feature-view');let uploaded=null,inspection=null;
 view.innerHTML=`<section class="panel excel-studio"><div class="section-title"><div><h2>Excel 智能制图</h2><p class="hint">逐个确认工作表，让数据成为清晰、可编辑的图表。</p></div><span class="status-tag">金控标准样式</span></div><div class="steps"><span><b>1</b>上传工作簿</span><span><b>2</b>确认各 Sheet</span><span><b>3</b>生成 Excel</span></div>${uploadHTML('选择 Excel 工作簿（.xlsx）','excel','.xlsx')}<div class="excel-style"><div class="excel-swatches">${['C4621A','D98025','DB953F','E7A447','FBDDB5','00427A'].map(c=>`<i style="background:#${c}"></i>`).join('')}</div><span>橙蓝图表 · 黑色文字与坐标轴 · 白底表格</span></div><p class="hint">下载后，前面是图表和制图数据，后面保留原始工作表。公式采用已保存的计算值，不自动换算单位。</p><div id="excel-sheets" class="excel-sheets"><div class="empty">上传后将展示工作表和数据预览。</div></div><label class="field">补充说明<textarea id="excel-note" rows="2" placeholder="可选：用一句话调整图题或资料来源，例如“图题突出营业收入变化，来源写财务月报”。"></textarea></label><div class="submit-row"><small id="excel-count">尚未上传工作簿</small><button class="primary" id="excel-run" disabled>生成含图表的 Excel →</button></div><p id="excel-error" role="alert"></p></section>`;
 const select=(name,options,value)=>`<select data-option="${name}">${options.map(([v,t])=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(t)}</option>`).join('')}</select>`;
 const input=(name,value,placeholder='')=>`<input data-option="${name}" value="${esc(value)}" placeholder="${esc(placeholder)}">`;
 function count(){const n=view.querySelectorAll('[data-sheet-enabled]:checked').length;$('excel-count').textContent=`已选择 ${n} 个 Sheet`;$('excel-run').disabled=!n}
 function render(data){
  $('excel-sheets').innerHTML=data.sheets.map((s,i)=>`<section class="excel-sheet" data-sheet-index="${i}"><div class="excel-sheet-head"><label><input type="checkbox" data-sheet-enabled ${!s.empty&&!s.hidden?'checked':''} ${s.empty?'disabled':''}> <strong>${esc(s.name)}</strong></label><span class="hint">${s.empty?'空工作表':`${s.rows} 行 × ${s.columns} 列`}</span></div>${s.empty?'':`<div class="excel-preview"><table><tbody>${s.preview.map(row=>`<tr><th>${row.row}</th>${row.cells.map(c=>`<td title="${esc(c.address)}">${esc(c.value??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="hint">预览前6行、8列 · 分类取选区第一列（或第一行），下一行（或列）开始为数据。</p>${(s.warnings||[]).map(w=>`<p class="excel-warning">${esc(w)}</p>`).join('')}<div class="excel-options"><label class="field">表格类型${select('table',['时间序列','分类对比','占比结构','指标关系','明细表'].map(v=>[v,v]),/日期|年月|月份|季度|年份/.test(String(s.preview[0]?.cells[0]?.value||''))?'时间序列':'分类对比')}</label><label class="field">图表类型${select('chart',['自动推荐','折线图','柱状图','条形图','堆积柱状图','散点图','饼图','柱线组合图','仅整理表格'].map(v=>[v,v]),'自动推荐')}</label></div><details><summary>调整数据范围、系列和标注</summary><div class="excel-options"><label class="field">数据范围（含单行/列表头）${input('range',s.range,'例如 A1:E20')}</label><label class="field">数据方向${select('orientation',[['columns','按列：首行是系列名'],['rows','按行：首列是系列名']],'columns')}</label><label class="field">数据系列（按填写顺序配色）${input('series','','列填 B,C；按行时填 2,3；留空选全部')}</label><label class="field">分类顺序${select('order',['原始顺序','分类升序','分类降序'].map(v=>[v,v]),'原始顺序')}</label><label class="field">图表标题${input('title',s.name)}</label><label class="field">单位（不换算）${input('unit','','例如：亿元人民币、%、pps')}</label><label class="field excel-source">资料来源${input('source','','留空则标注文件名、Sheet和数据范围')}</label></div><p class="hint">双系列按填写顺序使用橙、蓝；两期对比请把当期系列放前。柱线组合将最后一个系列画为折线，要求同一单位。饼图限一个系列、最多6类。</p></details>`}</section>`).join('');
  view.querySelectorAll('[data-sheet-enabled]').forEach(c=>c.onchange=count);count();
 }
 view.querySelector('[data-upload]').onchange=async e=>{
  const f=e.target.files[0];if(!f)return;uploaded=null;inspection=null;$('excel-run').disabled=true;$('excel-error').textContent='';$('excel-sheets').textContent='正在读取工作簿…';
  try{
   const d=await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(f.name)},body:f});if(token!==generation)return;
   const data=await api('/api/excel/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fileId:d.id})});if(token!==generation)return;
   uploaded=d;inspection=data;view.querySelector('[data-list]').textContent='✓ '+d.name;render(data);
  }catch(err){if(token===generation){$('excel-error').textContent=err.message;$('excel-sheets').textContent='读取失败，请重新选择文件。';$('excel-count').textContent='尚未读取有效工作簿'}}finally{e.target.value=''}
 };
 $('excel-run').onclick=async()=>{
  if(!uploaded||!inspection)return;
  const sheets=[...view.querySelectorAll('[data-sheet-index]')].filter(el=>el.querySelector('[data-sheet-enabled]').checked).map(el=>{
   const p={sheet:inspection.sheets[Number(el.dataset.sheetIndex)].name};el.querySelectorAll('[data-option]').forEach(x=>p[x.dataset.option]=x.value.trim());return p;
  });
  if(!sheets.length)return;
  const btn=$('excel-run');btn.disabled=true;$('excel-error').textContent='';
  try{
   const t=await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module:'office',files:[uploaded.id],excel:{fileId:uploaded.id,sheets},prompt:'Excel 智能制图：按已确认的 inputs/chart-plan.json 和金控规范生成含原生可编辑图表的 XLSX。补充说明：'+$('excel-note').value})});
   if(token!==generation)return;$('output-panel').hidden=false;watch(t.id);
  }catch(err){if(token===generation)$('excel-error').textContent=err.message}finally{if(token===generation)count()}
 };
}
