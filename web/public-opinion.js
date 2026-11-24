async function renderPublicOpinion(){
  const token=generation, live=()=>token===generation;
  const drivers=new Map(), picked=new Map();
  let limit=30;
  const post=(action,body)=>api('/api/opinion/'+action,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)
  });
  $('feature-view').innerHTML=`<div class="opinion-workspace">
    <section class="panel">
      <div class="reading-heading"><h2>监测配置</h2><button class="secondary" id="po-new" type="button">新增任务</button></div>
      <label class="field">查看任务<select id="po-monitor"><option value="">新任务</option></select></label>
      <form id="po-config">
        <div class="opinion-fields">
          <label class="field">任务名称<input name="name" required maxlength="200"></label>
          <label class="field">来源名称<input name="source" required maxlength="200"></label>
          <label class="field">网站或 RSS 地址<input name="url" type="url" required maxlength="2000"></label>
          <label class="field">关注主题<input name="topics" required maxlength="500"></label>
          <label class="field">关键词<input name="keywords" placeholder="可用逗号分隔" maxlength="500"></label>
          <label class="field">排除词<input name="exclude" placeholder="可用逗号分隔" maxlength="500"></label>
          <label class="field">监测频率<select name="frequency"><option value="manual">手动</option><option value="daily">每日</option><option value="weekly">每周</option></select></label>
          <label class="field">输出语言<select name="language"><option>简体中文</option><option>繁體中文</option><option>English</option></select></label>
        </div>
        <p class="hint">当前由「立即检查」触发。频率设置已保存，供后续定时任务使用。</p>
        <label><input name="enabled" type="checkbox" checked> 启用</label>
        <div class="opinion-actions"><button class="secondary" type="submit">保存配置</button><button id="po-run" class="primary" type="button" disabled>立即检查</button></div>
      </form>
      <p id="po-status" role="status"></p>
      <details><summary>运行记录</summary><div id="po-runs"></div></details>
    </section>
    <section class="panel reading-notes">
      <h2>舆情列表</h2>
      <div class="opinion-fields">
        <label class="field">搜索<input id="po-search" type="search" placeholder="标题、正文或摘要"></label>
        <label class="field">来源<select id="po-source"></select></label>
        <label class="field">发布日期<input id="po-day" type="date"></label>
        <label class="field">分类<select id="po-category"></select></label>
        <label class="field">复核状态<select id="po-state"><option value="">全部</option><option value="pending">待复核</option><option value="selected">已入选</option><option value="ignored">已忽略</option></select></label>
      </div>
      <p id="po-count" role="status"></p><div id="po-items"></div>
      <button class="secondary" id="po-more" hidden>查看更多</button>
    </section>
    <section class="panel">
      <h2>舆情简报</h2>
      <div class="opinion-fields">
        <label class="field">简报类型<select id="po-kind"><option value="daily">当日舆情</option><option value="weekly">舆情周报</option><option value="custom">自定义简报</option></select></label>
        <label class="field" id="po-date-field">发布日期 / 周报截止日<input id="po-date" type="date"></label>
        <label class="field">标题（可选）<input id="po-title" maxlength="100"></label>
      </div>
      <p class="hint" id="po-picked">已勾选 0 条。请先复核入选，再勾选加入简报。</p>
      <div class="opinion-actions"><button class="primary" id="po-generate">生成简报</button><button class="secondary" id="po-copy">复制</button><button class="secondary" id="po-download">下载 Markdown</button></div>
      <p id="po-brief-status" role="status"></p>
      <textarea id="po-brief" class="opinion-brief" rows="12" aria-label="编辑简报" placeholder="生成后可在这里编辑"></textarea>
    </section>
  </div>`;
  const select=$('po-monitor'), form=$('po-config'), status=$('po-status'), run=$('po-run');
  const themes='香港资本市场、证券行业、金融监管、跨境金融、财富管理、券商动态';
  const localToday=new Date();
  localToday.setMinutes(localToday.getMinutes()-localToday.getTimezoneOffset());
  $('po-date').value=localToday.toISOString().slice(0,10);
  form.elements.topics.value=themes;
  const asCategory=item=>item.review.category||item.ai?.category||'未分类';
  function options(el,values,label){
    const previous=el.value;
    el.replaceChildren(new Option(label,''));
    for(const value of values)el.add(new Option(value,value));
    if(values.includes(previous))el.value=previous;
  }
  function monitorOptions(mid){
    select.replaceChildren(new Option('新任务',''));
    for(const state of drivers.values())select.add(new Option(state.config.name,state.id));
    select.value=mid;
  }
  function showRuns(){
    const state=drivers.get(select.value), box=$('po-runs');
    const rows=state?.runs??[];
    run.disabled=!state?.config.enabled||rows.some(r=>r.status==='running');
    box.replaceChildren();
    if(!rows.length)box.append(text('p','暂无运行记录。'));
    for(const row of [...rows].reverse().slice(0,20)){
      const label={running:'进行中',completed:'成功',failed:'失败'}[row.status];
      const block=text('article','');
      block.append(text('p',row.startedAt+' → '+(row.endedAt||'进行中')+' · '+label+
        ' · 新发现 '+row.discovered+' / 去重 '+row.duplicates+' / AI 入选 '+row.included));
      for(const error of row.errors)block.append(text('small',error));
      box.append(block);
    }
  }
  function fill(){
    const state=drivers.get(select.value);
    form.reset();
    form.elements.topics.value=themes;
    if(state)for(const [key,value] of Object.entries(state.config)){
      if(key==='enabled')form.elements[key].checked=value;
      else form.elements[key].value=value;
    }
    status.textContent='';
    showRuns();
  }
  function updatePicked(){
    $('po-picked').textContent='已勾选 '+picked.size+' 条。请先复核入选，再勾选加入简报。';
  }
  function renderList(){
    const items=[...drivers.values()].flatMap(state=>state.items.map(item=>({mid:state.id,item})));
    const clusters=new Map();
    for(const {item} of items){
      if(!clusters.has(item.clusterId))clusters.set(item.clusterId,new Set());
      clusters.get(item.clusterId).add(item.source);
    }
    options($('po-source'),[...new Set(items.map(x=>x.item.source))],'全部来源');
    options($('po-category'),[...new Set(items.map(x=>asCategory(x.item)))],'全部分类');
    const q=$('po-search').value.trim().toLowerCase(), day=$('po-day').value;
    const source=$('po-source').value, category=$('po-category').value, review=$('po-state').value;
    const filtered=items.filter(({item})=>
      (!source||source===item.source)&&(!category||category===asCategory(item))&&
      (!day||day===item.publishedDay)&&(!review||review===item.review.status)&&
      (!q||[item.title,item.body,item.ai?.summary||''].some(v=>v.toLowerCase().includes(q)))
    ).sort((a,b)=>b.item.fetchedAt.localeCompare(a.item.fetchedAt));
    $('po-count').textContent='共 '+filtered.length+' 条';
    $('po-more').hidden=filtered.length<=limit;
    const list=$('po-items');
    list.replaceChildren();
    for(const {mid,item} of filtered.slice(0,limit)){
      const row=text('article',''), heading=text('h3',item.title), link=text('a','查看原文');
      link.href=item.url; link.target='_blank'; link.rel='noopener noreferrer';
      const ai=item.ai, detail=document.createElement('details');
      const size=clusters.get(item.clusterId).size;
      detail.append(text('summary','AI 判断依据与已保存正文'),
        text('p',ai?ai.reason:'等待 AI 分析'),
        text('p',ai?'机构：'+ai.entities.join('、')+' · 标签：'+ai.topics.join('、'):''),
        text('pre',item.body));
      row.append(heading,text('p',item.source+' · 发布 '+(item.publishedDay||item.publishedAt||'未公开')+
        ' · 抓取 '+item.fetchedAt+' · '+item.contentKind),
        text('p',(ai?(ai.relevant?'AI 相关':'AI 不相关')+' · 重要性 '+ai.importance:'待分析')+
          ' · '+asCategory(item)+(size>1?' · 同簇 '+size+' 个来源':'')),
        text('p',ai?.summary||''),link,detail);
      const controls=text('div','');controls.className='opinion-actions';
      const research=text('button','生成研究快评');
      research.onclick=()=>{openFeature('研究简报');startFromOpinion(item)};
      controls.append(research);
      const decision=document.createElement('select');
      decision.setAttribute('aria-label','复核状态');
      for(const [value,label] of [['pending','待复核'],['selected','入选'],['ignored','忽略']])decision.add(new Option(label,value));
      decision.value=item.review.status;
      const classification=document.createElement('input');
      classification.value=item.review.category;
      classification.placeholder=asCategory(item);
      classification.setAttribute('aria-label','修改分类');
      classification.maxLength=60;
      const checkbox=(caption,checked)=>{
        const label=text('label',''), input=document.createElement('input');
        input.type='checkbox';input.checked=checked;
        label.append(input,document.createTextNode(' '+caption));
        return [label,input];
      };
      const [starLabel,star]=checkbox('重点',item.review.starred);
      const [pickLabel,pick]=checkbox('加入简报',picked.has(item.id));
      pick.disabled=!ai||item.review.status!=='selected';
      pick.onchange=()=>{
        if(pick.checked)picked.set(item.id,{itemId:item.id,monitorId:mid});else picked.delete(item.id);
        updatePicked();
      };
      const save=text('button','保存复核');
      save.className='secondary';
      save.onclick=async()=>{
        save.disabled=true;
        try {
          const updated=await post('review',{monitorId:mid,itemId:item.id,status:decision.value,category:classification.value,starred:star.checked});
          if(!live())return;
          Object.assign(item,updated);
          if(item.review.status!=='selected')picked.delete(item.id);
          updatePicked();renderList();
        }catch(error){if(live())$('po-count').textContent=error.message;}
        finally{save.disabled=false;}
      };
      controls.append(decision,classification,starLabel,save,pickLabel);
      row.append(controls);list.append(row);
    }
  }
  async function refresh(){
    const summaries=await api('/api/opinion');
    const states=await Promise.all(summaries.map(s=>api('/api/opinion/'+s.id)));
    if(!live())return;
    const running=drivers.get(select.value)?.runs.at(-1)?.status==='running';
    for(const state of states)drivers.set(state.id,state);
    const latest=drivers.get(select.value)?.runs.at(-1);
    if(running&&latest?.status==='completed')status.textContent='检查完成。';
    if(running&&latest?.status==='failed')status.textContent='检查失败，详情见运行记录。';
    showRuns();renderList();
    if(states.some(s=>s.runs.some(r=>r.status==='running'))){
      clearTimeout(poll);
      poll=setTimeout(()=>refresh().catch(error=>{if(live())status.textContent=error.message;}),2000);
    }
  }
  select.onchange=fill;
  $('po-new').onclick=()=>{select.value='';fill();form.elements.name.focus();};
  form.onsubmit=async event=>{
    event.preventDefault();
    const data=Object.fromEntries(new FormData(form));
    try{
      const state=await post('save',{...data,id:select.value,enabled:form.elements.enabled.checked});
      if(!live())return;
      drivers.set(state.id,state);monitorOptions(state.id);fill();status.textContent='配置已保存。';
    }catch(error){if(live())status.textContent=error.message;}
  };
  run.onclick=async()=>{
    run.disabled=true;status.textContent='检查已提交，进度见运行记录。';
    try{
      await post('run',{id:select.value});
      if(live())await refresh();
    }catch(error){if(live()){status.textContent=error.message;showRuns();}}
  };
  for(const id of ['po-search','po-source','po-day','po-category','po-state']){
    $(id).oninput=()=>{limit=30;renderList();};
  }
  $('po-more').onclick=()=>{limit+=30;renderList();};
  $('po-kind').onchange=()=>{$('po-date-field').hidden=$('po-kind').value==='custom';};
  $('po-generate').onclick=async()=>{
    const message=$('po-brief-status');
    try{
      const result=await post('brief',{kind:$('po-kind').value,title:$('po-title').value,
        date:$('po-date').value,items:[...picked.values()]});
      if(!live())return;
      $('po-brief').value=result.markdown;
      message.textContent='生成 '+result.count+' 条'+(result.excluded?'，日期范围外 '+result.excluded+' 条':'')+'。';
    }catch(error){if(live())message.textContent=error.message;}
  };
  $('po-copy').onclick=async()=>{
    try{
      if(!$('po-brief').value.trim())throw Error('请先生成简报');
      await navigator.clipboard.writeText($('po-brief').value);
      if(live())$('po-brief-status').textContent='已复制。';
    }catch(error){if(live())$('po-brief-status').textContent=error.message;}
  };
  $('po-download').onclick=()=>{
    const value=$('po-brief').value;
    if(!value.trim()){$('po-brief-status').textContent='请先生成简报';return;}
    const url=URL.createObjectURL(new Blob([value],{type:'text/markdown;charset=utf-8'}));
    const link=text('a','');
    link.href=url;link.download='舆情简报.md';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  try{await refresh();if(live())monitorOptions('');}
  catch(error){if(live())status.textContent=error.message;}
}
