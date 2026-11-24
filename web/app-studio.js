const studioTemplates=[
  ['会议纪要助手','整理会议记录，输出会议结论、待办事项、责任人和截止时间。','tool'],
  ['工作周报生成器','按本周进展、重点事项、问题和下周计划整理工作事项。','skill'],
  ['材料要点提取器','阅读材料，提取结论和关键事实。','tool'],
  ['文件信息提取器','上传 Word/PDF，提取项目名称、金额、负责人、进度和下一步安排。','tool'],
  ['项目进度看板','上传 Excel，展示项目总数、正常和延期数量、负责人分布和项目清单。','dashboard'],
  ['舆情摘要器','根据提供的舆情材料，整理有来源的摘要和待关注事项。','tool'],
  ['政策文件阅读助手','阅读政策文件，提取适用范围、关键要求、生效时间及原文依据。','tool']
];

function renderStudio(feature,selectedApp=null,template=null){
  if(feature==='开始创造' && !selectedApp && !template){
    $('feature-view').innerHTML='<iframe title="AI 工坊对话共创" src="/workshop-chat.html" style="width:100%;height:72vh;border:0;background:white;border-radius:14px"></iframe>';
    return;
  }
  if(workshopTabs.includes(feature)){
    renderWorkshop(feature);
    history.replaceState(null,'','#extend-3');
    return;
  }
  const token=generation,live=()=>token===generation,view=$('feature-view');
  history.replaceState(null,'','#extend-'+['开始创造','我的工具','模板广场','高级设置'].indexOf(feature));
  const post=(action,body)=>api('/api/applications/'+action,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)
  });
  const jump=(name,app=null,tpl=null)=>{
    activeFeature=name;$('breadcrumb').textContent='工作台 / '+current.name+' / '+name;
    generation++;clearTimeout(poll);
    [...$('feature-nav').children].forEach(item=>{item.classList.toggle('selected',item.textContent===name);if(item.textContent===name)item.setAttribute('aria-current','page');else item.removeAttribute('aria-current')});
    renderStudio(name,app,tpl);
  };
  view.innerHTML='<section class="panel studio"><h2>AI 工坊</h2><p>把你的工作方法，变成自己的 AI 工具。</p><div id="studio-body"></div><p id="studio-status" role="status"></p></section>';
  if(feature!=='开始创造'){view.querySelector('h2').textContent=feature;view.querySelector('h2 + p').remove()}
  const body=$('studio-body'), status=$('studio-status');
  let busy=false;
  async function job(options){
    if(busy)throw Error('当前操作正在执行');
    busy=true;
    view.querySelectorAll('button').forEach(button=>button.disabled=true);
    try{
      const task=await post('job',options);
      while(live()){
        const result=await api('/api/tasks/'+task.id);
        if(result.status==='completed')return {value:result.applicationResult,task:result};
        if(!['queued','running'].includes(result.status))throw Error(result.result||'执行失败');
        await new Promise(resolve=>setTimeout(resolve,1500));
      }
      throw Error('已离开当前工具');
    }finally{
      busy=false;
      if(live())view.querySelectorAll('button').forEach(button=>button.disabled=false);
    }
  }
  const button=(caption,fn,primary=false)=>{
    const control=text('button',caption);
    control.className=primary?'primary':'secondary';
    control.onclick=()=>Promise.resolve().then(fn).catch(error=>{if(live())status.textContent=error.message;});
    return control;
  };
  const field=(label,element)=>{
    const container=text('label',label);
    container.className='field';container.append(element);return container;
  };
  const textarea=(placeholder='')=>{
    const input=document.createElement('textarea');
    input.rows=4;input.placeholder=placeholder;return input;
  };
  function advanced(){
    const controls=text('div','');controls.className='studio-actions';
    for(const label of workshopTabs)controls.append(button(label,()=>{
      renderWorkshop(label);
      history.replaceState(null,'','#extend-3');
      const back=button('返回 AI 工坊',()=>jump('高级设置'));
      view.prepend(back);
    }));
    body.append(controls);
  }
  function open(app,previousInput=null){
    body.replaceChildren(text('h3','你的工具做好了'),text('h2',app.name),text('p',app.description));
    const input=textarea('填写内容，或使用样例立即试试看');
    input.value=previousInput?.text??app.sample;
    const upload=document.createElement('input');
    upload.type='file';upload.multiple=true;
    upload.accept=app.input_schema.formats.filter(f=>f!=='text').join(',');
    if(previousInput?.files?.length && upload.accept){
      const transfer=new DataTransfer();
      const formats=upload.accept.split(',');
      for(const file of previousInput.files){
        if(formats.some(format=>file.name.toLowerCase().endsWith(format)))transfer.items.add(file);
      }
      upload.files=transfer.files;
    }
    body.append(field('输入内容（已填入试用样例）',input));
    if(upload.accept)body.append(field('上传材料',upload));
    const result=text('section','');result.className='studio-result';
    body.append(button(app.ui_config.button_label||'试试看',async()=>{
      status.textContent='正在处理你的输入…';result.replaceChildren();
      const ids=[];
      for(const file of upload.files){
        const saved=await api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file});
        ids.push(saved.id);
      }
      const response=await job({action:'run',id:app.id,text:ids.length?'':input.value,files:ids});
      if(!live())return;
      const value=response.value;
      result.append(text('p',value.text));
      if(value.rows.length){
        if(app.output_schema.format==='dashboard'){
          const cards=text('div','');cards.className='studio-metrics';
          const config=value.ui_config, column=config.status_column;
          const project=value.columns.some(name=>name.includes('项目'));
          cards.append(text('strong',(project?'项目总数 ':'记录总数 ')+value.rows.length));
          if(column){
            const counts=new Map(project?[['正常',0],['延期',0]]:[]);
            for(const row of value.rows){
              const state=String(row[column]??'待确认');
              counts.set(state,(counts.get(state)||0)+1);
            }
            for(const [state,count] of counts)cards.append(text('strong',state+' '+count));
          }
          for(const metric of value.metrics||[])cards.append(text('strong',metric));
          result.append(cards);
          if(config.group_by){
            const groups=new Map();
            for(const row of value.rows){const key=String(row[config.group_by]??'待确认');groups.set(key,(groups.get(key)||0)+1);}
            result.append(text('h3',config.group_by+'分布'));
            for(const [name,count] of groups){
              const line=text('div',name+' · '+count),bar=document.createElement('meter');
              bar.max=value.rows.length;bar.value=count;bar.setAttribute('aria-label',name+'数量');
              line.append(bar);result.append(line);
            }
          }
        }
        const table=document.createElement('table'),head=document.createElement('tr');
        for(const column of value.columns)head.append(text('th',column));
        table.append(head);
        for(const row of value.rows){const line=document.createElement('tr');for(const column of value.columns)line.append(text('td',String(row[column]??'')));table.append(line);}
        const wrap=text('div','');wrap.className='studio-table';wrap.append(table);result.append(wrap);
      }
      for(const file of response.task.artifacts||[]){
        const link=text('a','下载 '+file);link.href='/download/'+response.task.id+'/'+encodeURIComponent(file);link.download=file;result.append(link);
        if(file.endsWith('.docx'))addNextSteps(response.task.id,file,result);
      }
      status.textContent='工具可以用了。';
    },true),result);
    const actions=text('div','');actions.className='studio-actions';
    actions.append(button('加入我的工具',async()=>{app=await post('update',{action:'save',id:app.id});if(live())status.textContent='已加入我的工具。';}),
      button('再试一次',()=>{input.focus();status.textContent='调整输入后再次运行。';}));
    body.append(actions);
    const change=textarea('例如：增加负责人字段，或把延期项目放最上面。');
    body.append(field('告诉 AI 你还想怎么改。',change),button('继续调整',async()=>{
      status.textContent='正在调整并保留旧版本…';
      const response=await job({action:'revise',id:app.id,changes:change.value});
      if(live()){
        open(response.value,{text:input.value,files:[...upload.files]});
        status.textContent='已保存新版本，可以立即试用。';
      }
    }));
    const details=document.createElement('details');details.append(text('summary','看看它是怎么做的'));
    details.append(text('pre',JSON.stringify(app,null,2)));
    const skillText=text('pre','正在读取工作方法…');
    details.append(skillText);
    api('/api/workshop/version/'+app.skill_id).then(skill=>{
      if(live())skillText.textContent=skill.content;
    }).catch(error=>{if(live())skillText.textContent=error.message;});
    details.append(button('查看运行与修改记录',async()=>{
      const records=await api('/api/applications/'+app.id+'/runs');
      if(live())historyBox.textContent=JSON.stringify(records,null,2);
    }));
    const historyBox=text('pre','');
    details.append(historyBox);
    const link=text('a','导出应用分享包');link.href='/api/applications/'+app.id+'/share';link.download='application.zip';details.append(link);
    details.append(text('p','分享包中的 application.json 可由对方导入“我的工具”。'));
    const versions=document.createElement('select');
    for(let n=app.version;n>=1;n--)versions.add(new Option('版本 '+n,String(n)));
    const versionPanel=document.createElement('details');versionPanel.append(text('summary','查看或恢复历史版本'));
    versionPanel.append(field('历史版本',versions),button('恢复为新版本',async()=>{
      const restored=await post('update',{action:'restore',id:app.id,version:Number(versions.value)});
      if(live())open(restored);
    }));
    details.append(button('打开高级设置',()=>jump('高级设置')));
    body.append(versionPanel,details);
  }
  function wizard(kind,seed='',input=null){
    let step=0;
    const source=document.createElement('select');
    for(const label of ['一段文字','Word / PDF','Excel','图片','多份文件','手工填写的数据','我自己描述'])source.add(new Option(label,label));
    if(input)source.value=input;else if(kind==='dashboard')source.value='Excel';
    const idea=textarea('用一句话说说你的想法');idea.value=seed;
    const operation=textarea('选择 AI 建议，或补充你希望的操作');
    const output=document.createElement('select');
    for(const label of ['一段文字','一张表格','一个 Excel','一个 Word','一个小页面','一个看板','多项结果'])output.add(new Option(label,label));
    if(kind==='dashboard')output.value='一个看板';
    const requirements=textarea('例如：提取项目名称、金额、负责人、当前进度和下一步安排。');
    const panel=text('div','');
    body.replaceChildren(panel);
    const values=()=>({kind,input:source.value,goal:idea.value+'\n'+operation.value,output:output.value,requirements:requirements.value});
    function draw(){
      panel.replaceChildren(text('small','第 '+(step+1)+' 步，共 4 步'));
      if(step===0)panel.append(text('h3','你想让它处理什么？'),field('材料类型',source),field('你的想法',idea));
      if(step===1)panel.append(text('h3','你希望它帮你做什么？'),field('处理方法',operation));
      if(step===2)panel.append(text('h3','你想得到什么？'),field('结果形式',output));
      if(step===3)panel.append(text('h3','补充你的要求'),requirements);
      if(step>0)panel.append(button('上一步',()=>{step--;draw();}));
      panel.append(button(step===3?'做出我的工具':'继续',async()=>{
        if(step===0){
          status.textContent='AI 正在根据你的想法推荐做法…';
          const response=await job({action:'recommend',...values()});
          if(!live())return;
          step=1;draw();
          const suggestions=text('div','');suggestions.className='studio-actions';
          for(const recommendation of response.value.recommendations)suggestions.append(button(recommendation,()=>{operation.value=recommendation;}));
          panel.prepend(suggestions);status.textContent='';
        }else if(step<3){step++;draw();}
        else{
          status.textContent='明白了，我来给你做。';
          const response=await job({action:'create',...values()});
          if(live()){open(response.value);status.textContent='可以用样例立即试用。';}
        }
      },true));
    }
    draw();
  }
  if(selectedApp){open(selectedApp);return;}
  if(template?.goal){wizard('tool',template.goal,template.input);return;}
  if(feature==='高级设置'){advanced();body.append(button('本地运行配置',()=>$('settings').click()));return;}
  if(feature==='模板广场'){
    const grid=text('div','');grid.className='studio-grid';
    for(const [name,goal,kind] of studioTemplates){
      const card=text('article','');card.append(text('h3',name),text('p',goal),
        button('用这个做一个我的版本',()=>{
          const changes=textarea('例如：会议纪要最后增加责任人和截止时间。');
          body.replaceChildren(text('h3','你希望它哪里不一样？'),changes,
            button('做出我的版本',async()=>{
              status.textContent='明白了，我来给你做。';
              const input=kind==='dashboard'?'Excel':/材料|文件/.test(name)?'Word / PDF':'一段文字';
              const output=kind==='dashboard'?'一个看板':name==='文件信息提取器'?'一张表格':'一段文字';
              const response=await job({action:'create',kind,input,output,goal,requirements:changes.value});
              if(live()){open(response.value);status.textContent='可以用样例立即试用。';}
            },true));
        }));
      grid.append(card);
    }
    body.append(grid);return;
  }
  if(feature==='我的工具'){
    const file=document.createElement('input');file.type='file';file.accept='.json';
    body.append(field('导入同事分享的工具定义文件',file));
    file.onchange=async()=>{
      try{const app=await post('import',JSON.parse(await file.files[0].text()));if(live())open(app);}
      catch(error){if(live())status.textContent=error.message;}
    };
    Promise.all([api('/api/applications'),api('/api/workshop-library')]).then(([apps,local])=>{
      if(!live())return;
      const grid=text('div','');grid.className='studio-grid';
      for(const item of local){
        const card=text('article',''), title=item.localApp?.name||item.name;
        card.append(text('h3',title),text('p',item.plan.split('\n')[0]));
        const edit=()=>{const frame=document.createElement('iframe');frame.title=title;frame.style.cssText='width:100%;height:72vh;border:0';frame.src='/workshop-chat.html?thread='+item.workshopThread;body.replaceChildren(frame)};
        card.append(button('打开使用',()=>{if(item.localApp)window.open(item.localApp.preview,'_blank','noopener');else edit()},true),button('继续修改',edit));grid.append(card);
      }
      for(const app of apps){
        const card=text('article','');
        const names={tool:'小工具',dashboard:'小看板',skill:'工作方法',workflow:'组合工具'};
        card.append(text('h3',(app.type==='dashboard'?'▥ ':'✧ ')+app.name),
          text('small',names[app.type]+' · '+new Date(app.updated_at).toLocaleString('zh-CN')),text('p',app.description));
        const controls=text('div','');controls.className='studio-actions';
        const more=text('details','');more.append(text('summary','更多操作'));
        controls.append(button('打开使用',()=>open(app),true),button('修改',()=>open(app)));
        more.append(
          button('复制一个',async()=>{const copy=await post('update',{action:'copy',id:app.id});if(live())open(copy);}),
          button('删除',async()=>{await post('update',{action:'delete',id:app.id});if(live())card.remove();}),
          button('查看高级信息',()=>{open(app);body.querySelector('details').open=true;}));
        const share=text('a','分享');share.href='/api/applications/'+app.id+'/share';share.download='application.zip';
        more.append(share);controls.append(more);card.append(controls);grid.append(card);
      }
      body.append(grid);
      if(!apps.length&&!local.length)body.append(text('p','还没有工具，从一个想法开始吧。'));
    }).catch(error=>{if(live())status.textContent=error.message;});
    return;
  }
  body.append(text('h3','你想做什么？'),text('p','选一种方式，用自己的话描述需求。'));
  const cards=text('div','');cards.className='studio-grid';
  for(const [kind,title,description] of [
    ['tool','做个小工具','整理文字、处理文件、提取信息，让重复工作简单一点。'],
    ['dashboard','做个小看板','把 Excel 或手工数据变成清楚的指标、图表和项目清单。'],
    ['skill','教 AI 一个工作方法','把你的流程、模板和检查规则变成可以反复使用的工具。']
  ]){
    const card=text('article','');card.append(text('h3',title),text('p',description),button(kind==='dashboard'?'创建看板':kind==='skill'?'教一个方法':'创建工具',()=>wizard(kind),true));cards.append(card);
  }
  body.append(cards);
}
