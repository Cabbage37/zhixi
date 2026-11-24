async function renderResearch(name){
  const token=generation,live=()=>token===generation;
  const post=(action,body)=>api('/api/research/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  $('feature-view').innerHTML=`<section class="panel">
    <h2>${esc(name)}</h2>
    <div class="opinion-fields">
      <label class="field">数据库<select id="rs-db"></select></label>
      <label class="field">数据表<select id="rs-table"></select></label>
      <label class="field">搜索指标或正文<input id="rs-search" placeholder="例如 CPI、GDP、国债"></label>
      <label class="field">精确筛选字段<select id="rs-filter"></select></label>
      <label class="field">精确筛选值<input id="rs-value" placeholder="可点击预览中的指标代码"></label>
      <label class="field">日期字段<select id="rs-date"></select></label>
      <label class="field">开始日期<input id="rs-start" type="date"></label>
      <label class="field">结束日期<input id="rs-end" type="date"></label>
    </div>
    <button disabled id="rs-preview" class="secondary">预览数据</button>
    <p id="rs-status" role="status"></p><div id="rs-preview-table" class="studio-table"></div>
    <div class="opinion-fields">
      <label class="field">横轴<select id="rs-x"></select></label>
      <label class="field">数值列<select id="rs-y"></select></label>
      <label class="field">图表类型<select id="rs-kind"><option value="line">折线图</option><option value="bar">柱状图</option></select></label>
    </div>
    <label class="field" ${name==='宏观数据分析'?'':'hidden'}>分析问题<textarea id="rs-question" rows="3" placeholder="希望分析什么趋势或变化？"></textarea></label>
    <p class="hint">每次最多读取3,000行。制图前请按指标代码筛选单个序列，核对单位及频率。数据来自导入的数据库快照。</p>
    <button disabled id="rs-run" class="primary">${name==='宏观数据分析'?'分析并生成成果':'生成并保存图表'}</button>
  </section><section id="rs-result" class="panel" hidden></section>`;
  const status=$('rs-status');
  let metadata=null;
  const choices=(id,values,empty=false)=>{
    $(id).replaceChildren(...(empty?[new Option('不使用','')]:[]),...values.map(v=>new Option(v,v)));
  };
  const options=()=>({
    database:$('rs-db').value,table:$('rs-table').value,search:$('rs-search').value,
    filters:$('rs-filter').value&&$('rs-value').value?[{column:$('rs-filter').value,value:$('rs-value').value}]:[],
    dateColumn:$('rs-date').value,start:$('rs-start').value,end:$('rs-end').value
  });
  function table(data){
    const target=$('rs-preview-table');target.replaceChildren();
    const grid=document.createElement('table'), head=document.createElement('tr');
    for(const column of data.columns)head.append(text('th',column));
    grid.append(head);
    for(const row of data.rows.slice(0,30)){
      const line=document.createElement('tr');
      for(const column of data.columns){
        const cell=text('td',String(row[column]??''));
        if(['指标代码','序列代码'].includes(column)){
          const pick=text('button',String(row[column]));pick.className='secondary';
          pick.title='仅查看这个指标';
          pick.onclick=()=>{$('rs-filter').value=column;$('rs-value').value=row[column];$('rs-preview').click();};
          cell.replaceChildren(pick);
        }
        line.append(cell);
      }
      grid.append(line);
    }
    target.append(grid);
    status.textContent='匹配 '+data.count+' 行，当前取出 '+data.rows.length+' 行，预览前30行'+(data.truncated?'；已达到读取上限':'');
  }
  let selection=0;
  async function describe(){
    const revision=++selection;
    $('rs-preview').disabled=$('rs-run').disabled=true;
    try{
      if(!$('rs-table').value){status.textContent='该库暂无数据表';return;}
      const description=await post('metadata',options());
      if(!live()||revision!==selection)return;
      metadata=description;
      const columns=metadata.columns.map(c=>c.column_name);
      choices('rs-filter',columns,true);
      $('rs-filter').value=columns.find(c=>['指标代码','序列代码'].includes(c))||'';
      const dates=metadata.columns.filter(c=>/DATE|TIMESTAMP/.test(c.column_type)).map(c=>c.column_name);
      choices('rs-date',dates,true);
      $('rs-date').value=dates.find(c=>['日期','时期'].includes(c))||dates[0]||'';
      choices('rs-x',columns,true);choices('rs-y',metadata.columns.filter(c=>/DOUBLE|FLOAT|INT|DECIMAL/.test(c.column_type)).map(c=>c.column_name),true);
      $('rs-x').value=$('rs-date').value||columns[0];
      const numerical=metadata.columns.filter(c=>/DOUBLE|FLOAT|INT|DECIMAL/.test(c.column_type)).map(c=>c.column_name);
      $('rs-y').value=numerical.find(c=>['数值','收益率'].includes(c))||numerical[0]||'';
      const sample=await post('preview',options());
      if(!live()||revision!==selection)return;
      table(sample);
      $('rs-preview').disabled=$('rs-run').disabled=false;
    }catch(error){if(live())status.textContent=error.message;}
  }
  let databases=[];
  function chooseDatabase(){
    const tables=databases.find(d=>d.name===$('rs-db').value)?.tables||[];
    choices('rs-table',tables);
    $('rs-table').value=tables.includes('统一观测值')?'统一观测值':tables.includes('观测值')?'观测值':tables[0]||'';
    $('rs-search').value='';$('rs-value').value='';
    describe();
  }
  $('rs-db').onchange=chooseDatabase;
  $('rs-table').onchange=()=>{ $('rs-value').value='';describe(); };
  $('rs-preview').onclick=async()=>{try{const data=await post('preview',options());if(live())table(data);}catch(error){if(live())status.textContent=error.message;}};
  function draw(data){
    const panel=$('rs-result');panel.hidden=false;panel.replaceChildren(text('h2','研究结果'));
    if(data.chart){
      const points=data.chart.values.filter(p=>typeof p.y==='number'&&Number.isFinite(p.y)&&p.x!==null);
      if(points.length){
        const canvas=document.createElement('canvas');canvas.width=1000;canvas.height=390;canvas.style.width='100%';
        const ctx=canvas.getContext('2d'), numbers=points.map(p=>p.y);
        let low=Math.min(...numbers),high=Math.max(...numbers);
        if(data.chart.kind==='bar'){low=Math.min(0,low);high=Math.max(0,high);}
        if(high===low){low-=1;high+=1;}
        const x=i=>70+i*880/Math.max(points.length-1,1), y=v=>330-(v-low)/(high-low)*280;
        ctx.font='14px sans-serif';ctx.fillStyle='#333';
        ctx.fillText(data.chart.y,20,22);ctx.fillText(String(high),5,53);ctx.fillText(String(low),5,335);
        ctx.strokeStyle='#ddd';ctx.beginPath();ctx.moveTo(65,45);ctx.lineTo(65,335);ctx.lineTo(960,335);ctx.stroke();
        ctx.strokeStyle='#bf6019';ctx.fillStyle='#d88b2a';ctx.lineWidth=2;
        if(data.chart.kind==='line'){
          ctx.beginPath();points.forEach((p,i)=>{if(i===0)ctx.moveTo(x(i),y(p.y));else ctx.lineTo(x(i),y(p.y));});ctx.stroke();
        }else points.forEach((p,i)=>ctx.fillRect(x(i)-2,Math.min(y(p.y),y(0)),Math.max(1,700/points.length),Math.max(1,Math.abs(y(p.y)-y(0)))));
        ctx.fillStyle='#444';ctx.fillText(String(points[0].x).slice(0,20),70,365);ctx.fillText(String(points.at(-1).x).slice(0,20),770,365);
        panel.append(canvas);
        const picture=text('a','下载图表 PNG');picture.href=canvas.toDataURL('image/png');picture.download='研究图表.png';panel.append(picture);
      }
    }
    if(data.analysis)panel.append(text('pre',data.analysis));
  }
  $('rs-run').onclick=async()=>{
    const run=$('rs-run');run.disabled=true;status.textContent='正在生成研究成果…';
    try{
      const task=await post(name==='宏观数据分析'?'analyze':'chart',{
        ...options(),x:$('rs-x').value,y:$('rs-y').value,kind:$('rs-kind').value,question:$('rs-question').value
      });
      async function check(){
        try{
          const job=await api('/api/tasks/'+task.id);
          if(!live())return;
          if(['queued','running'].includes(job.status)){poll=setTimeout(check,1500);return;}
          run.disabled=false;status.textContent=job.status==='completed'?'成果已保存':job.result;
          if(job.researchResult){
            draw(job.researchResult);
            for(const file of job.artifacts||[]){
              const link=text('a','下载 '+file);link.href='/download/'+job.id+'/'+encodeURIComponent(file);link.download=file;
              $('rs-result').append(document.createElement('br'),link);
            }
          }
        }catch(error){if(live()){status.textContent=error.message;run.disabled=false;}}
      }
      if(live())check();
    }catch(error){if(live()){status.textContent=error.message;run.disabled=false;}}
  };
  try{
    databases=await api('/api/research/catalog');
    if(!live())return;
    choices('rs-db',databases.map(d=>d.name));
    $('rs-db').value='宏观';chooseDatabase();
  }catch(error){if(live())status.textContent=error.message;}
}
