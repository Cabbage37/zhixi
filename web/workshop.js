const workshopTabs=['Skill 创建','导入与修改','测试与版本管理','MCP / 工具接入'];
let workshopDraft='', workshopVersion=null;
const workshopPending=new Map();
const skillScenarios=[
  {title:'整理会议纪要',name:'meeting-notes',goal:'把会议笔记整理成一份清楚的会议纪要。',inputs:'会议笔记或会议转写。',outputs:'列出讨论要点、已定事项和行动项。负责人或期限未提到时标注待确认。',sample:'讨论了周报模板。决定周五前提交第一版，由小林负责。数据口径还要和财务确认，暂未指定负责人。'},
  {title:'生成工作周报',name:'weekly-brief',goal:'把零散工作记录整理成团队周报。',inputs:'本周的工作记录、风险和下周安排。',outputs:'按本周进展、风险和下一步整理。保留关键数字，缺失日期不补造。',sample:'已完成模板整理。财务口径还没确认。下周计划核对数据并发出第一版。'},
  {title:'提炼材料要点',name:'document-brief',goal:'把长材料提炼成一份可以快速阅读的摘要。',inputs:'需要阅读的原文或节选。',outputs:'给出一句话结论和三条要点。数字沿用原文，推断单独标注。',sample:'试点覆盖三个部门。连续两周平均处理时间从40分钟降到25分钟。样本只有12份，暂不推广结论。'},
  {title:'我有别的想法',name:'custom-skill',goal:'',inputs:'根据目标建议用户需要提供的材料。材料不足时先指出缺少什么。',outputs:'按目标组织输出，保留原始事实，缺少的信息标注待确认。',sample:''}
];
let workshopExample=null;

function renderWorkshop(feature){
  const page=workshopTabs.indexOf(feature), token=generation, view=$('feature-view');
  const live=()=>token===generation;
  history.replaceState(null,'','#extend-'+page);
  const post=(action,body)=>api('/api/workshop/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const field=(id,label,placeholder='',required=false)=>`<label class="field">${label}<textarea id="sw-${id}" rows="3" placeholder="${placeholder}" ${required?'required':''}></textarea></label>`;
  const status=value=>{if(live())$('sw-status').textContent=value};
  function lock(active){view.querySelectorAll('button,input,textarea,select').forEach(el=>el.disabled=active)}
  view.innerHTML=`<section class="panel workshop"><div class="section-title"><h2>${feature}</h2></div><div id="sw-body"></div><p id="sw-status" role="status" class="workshop-status"></p></section>`;
  const body=$('sw-body');
  if(page===3){
    body.innerHTML=`<p>查看已配置的 MCP 服务，并验证能否读取工具清单。</p><div id="sw-mcp"></div><p class="hint">连接由本地 <code>config/mcp.json</code> 管理，支持 stdio。可按 <code>config/mcp.example.json</code> 填写服务名、启动命令及参数后启用。</p>`;
    api('/api/status').then(data=>{
      if(!live())return;
      const target=$('sw-mcp');
      if(!data.mcp.servers.length)target.append(text('p','当前没有配置 MCP 服务。'));
      data.mcp.servers.forEach(server=>{
        const row=document.createElement('article');row.className='workshop-mcp';
        row.append(text('strong',server.name),text('span',server.enabled?'已启用':'未启用'));
        const button=text('button','读取工具');button.className='secondary';button.disabled=!server.enabled;
        const result=document.createElement('div');
        button.onclick=async()=>{
          button.disabled=true;result.textContent='正在连接…';
          try{const response=await post('probe',{name:server.name});result.replaceChildren(text('p',response.tools.length?`读取到 ${response.tools.length} 个工具${response.hasMore?'（首批）':''}`:'连接成功，未声明工具。'));response.tools.forEach(tool=>result.append(text('p',tool.name+' '+tool.description)))}catch(error){result.textContent=error.message}finally{button.disabled=false}
        };
        row.append(button,result);target.append(row);
      });
    }).catch(error=>status(error.message));
    return;
  }
  const markdown=`<label class="field">SKILL.md<textarea id="sw-content" rows="17" spellcheck="false" placeholder="生成草稿或导入已有 Skill 后，在这里检查和编辑。"></textarea></label>`;
  const editor=`<section id="sw-editor">${page===0?'<h3>技能草稿</h3><p id="sw-description"></p><details><summary>查看或编辑技能说明</summary>'+markdown+'</details>':markdown}<p id="sw-resources" class="hint"></p><div class="workshop-actions"><button class="secondary" id="sw-check">检查格式</button><label ${page===0?'hidden':''}>版本标识 <input id="sw-label" value="v0.1.0" maxlength="60"></label><button class="primary" id="sw-save">${page===0?'保存并下载 ZIP':'保存版本'}</button><a id="sw-zip" class="secondary" hidden>下载已保存 ZIP</a>${page===0?'<button class="secondary" id="sw-try">拿样例试一下</button>':''}</div></section>`;
  if(page===0){
    body.innerHTML=`<div class="steps" id="sw-progress"><span><b>1</b>选场景，说目标</span><span><b>2</b>确认做法</span></div><section data-sw-step="0"><div class="workshop-scenarios" role="group" aria-label="常用场景">${skillScenarios.map((scenario,index)=>`<button type="button" class="secondary" data-sw-scenario="${index}" aria-pressed="false">${scenario.title}</button>`).join('')}</div>${field('goal','你想让它帮你做什么？','例如：把一段会议记录整理成纪要，并列出待办。',true)}</section><section data-sw-step="1" hidden><h3>确认它应该怎么做</h3>${field('inputs','你给它什么？')}${field('outputs','你想拿到什么？')}<details><summary>补充规则、参考文件或修改英文标识</summary><label class="field">英文标识 <input id="sw-name" maxlength="64"></label>${field('steps','额外处理规则','例如：先归并重复事项，再按影响排序。')}${field('dependencies','需要用到哪些工具？','没有可以留空。')}<label class="field">参考示例（DOCX / PDF / TXT / MD）<input type="file" id="sw-reference" accept=".docx,.pdf,.txt,.md"></label></details></section><div class="workshop-actions"><button class="secondary" id="sw-back" hidden>上一步</button><button class="primary" id="sw-next">看看建议 →</button><button class="primary" id="sw-create" hidden>生成技能 →</button></div>${editor}`;
  }else if(page===1){
    body.innerHTML=`<p>上传 SKILL.md 或单个技能的 ZIP 包。包内资源随版本保留。</p><label class="field">导入技能<input type="file" id="sw-import" accept=".md,.zip"></label>${editor}${field('changes','希望 AI 修改什么','例如：保留输出结构，补充缺少输入时的处理方式。')}<button class="primary" id="sw-revise">生成修订草稿 →</button>`;
  }else{
    body.innerHTML=`<div class="workshop-actions"><label>本地版本 <select id="sw-versions"><option value="">当前草稿</option></select></label></div>${editor}<p class="hint">文字试运行由模型按 Skill 处理样例。脚本、外部工具以及随包文件的运行需在对应环境验证。</p>${field('sample','样例或本次任务','输入一段真实样例，或填写想交给这个 Skill 的文字任务。')}${field('expected','预期与验收标准','试运行时填写。例如：列出三类事项，不补造日期。')}<div class="workshop-actions"><button class="primary" id="sw-test">试运行并核对</button><button class="secondary" id="sw-run">使用此 Skill</button></div><pre id="sw-output" class="workshop-output" hidden></pre><details class="workshop-guide"><summary>打包与发布</summary><p>保存版本并下载 ZIP。可在知析的「导入与修改」重新导入，或在本页选择版本并使用。</p><p>公司平台接入后，可进入公司平台的技能上传入口，选择 ZIP、填写发布信息并提交审核。上传前请确认目标平台支持的资源与依赖。</p></details>`;
  }
  const value=key=>$('sw-'+key).value;
  const content=$('sw-content');
  function updateVersion(){
    const zip=$('sw-zip');zip.hidden=!workshopVersion||workshopVersion.content!==content.value;
    if(workshopVersion){zip.href='/api/workshop/zip/'+workshopVersion.id;$('sw-label').placeholder=workshopVersion.label}
    $('sw-resources').textContent=workshopVersion?.files.length?'随包文件 '+workshopVersion.files.join('、'):'仅 SKILL.md';
    if(page===0){$('sw-save').disabled=!content.value.trim();$('sw-description').textContent=workshopExample?.description||'可以先用样例试运行，或直接保存技能包。'}
  }
  function useVersion(item){
    workshopVersion=item;content.value=workshopDraft=item.content;updateVersion();
    if($('sw-versions'))$('sw-versions').value=item.id;
  }
  content.value=workshopDraft;$('sw-editor').hidden=page===0&&!workshopDraft;updateVersion();
  content.oninput=()=>{workshopDraft=content.value;updateVersion()};
  async function refreshVersions(){
    if(page!==2)return;
    try{
      const items=await api('/api/workshop/versions');if(!live())return;
      const select=$('sw-versions');select.replaceChildren(new Option('当前草稿',''),...items.map(item=>new Option(`${item.name} · ${item.label}`,item.id)));
      if(workshopVersion)select.value=workshopVersion.id;
    }catch(error){status(error.message)}
  }
  $('sw-check').onclick=async()=>{
    try{const meta=await post('validate',{content:content.value});status(`格式检查通过 · ${meta.name} · ${meta.lines} 行`)}catch(error){status(error.message)}
  };
  $('sw-save').onclick=async()=>{
    if(page===0&&workshopVersion?.content===content.value){$('sw-zip').click();return}
    lock(true);
    try{const item=await post('save',{content:content.value,label:value('label'),parent:workshopVersion?.id});if(!live())return;useVersion(item);await refreshVersions();status('版本已保存，可以下载 ZIP。');if(page===0)$('sw-zip').click()}catch(error){status(error.message)}finally{if(live())lock(false)}
  };
  async function upload(file){return api('/api/upload',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file})}
  async function watchJob(id){
    if(!live())return;
    try{
      const job=await api('/api/tasks/'+id);if(!live())return;
      if(job.status==='queued'||job.status==='running'){poll=setTimeout(()=>watchJob(id),1700);return}
      const pending=workshopPending.get(page);
      workshopPending.delete(page);lock(false);
      if(job.status!=='completed')throw Error(job.result||'任务未完成，请重试');
      const result=job.workshopResult;
      if(result.content){
        workshopVersion=job.workshop==='create'?null:pending?.version;
        $('sw-editor').hidden=false;
        if(job.workshop==='create')workshopExample={...pending.example,description:result.description};
        content.value=workshopDraft=result.content;updateVersion();status('草稿已生成。请检查内容，再保存版本。');
        if(page===0)$('sw-editor').scrollIntoView({block:'nearest'});
      }else{
        $('sw-output').hidden=false;$('sw-output').textContent=result.output;status('模型已返回执行结果。');
      }
    }catch(error){status(error.message);lock(false)}
  }
  async function submit(action,params,reference,example){
    const version=workshopVersion;
    lock(true);status('正在等待模型返回…');
    try{
      if(reference)params.referenceId=(await upload(reference)).id;
      const job=await post('job',{action,...params});
      workshopPending.set(page,{id:job.id,version,example});if(live())watchJob(job.id);
    }catch(error){status(error.message);if(live())lock(false)}
  }
  if(page===0){
    let step=0,scenario=skillScenarios.at(-1),configured=false;
    const show=()=>{
      view.querySelectorAll('[data-sw-step]').forEach(el=>el.hidden=Number(el.dataset.swStep)!==step);
      [...$('sw-progress').children].forEach((el,i)=>el.classList.toggle('workshop-current',i===step));
      $('sw-back').hidden=step===0;$('sw-next').hidden=step!==0;$('sw-create').hidden=step!==1;
    };
    const cards=[...view.querySelectorAll('[data-sw-scenario]')];
    cards.forEach((card,index)=>card.onclick=()=>{
      const goal=$('sw-goal');
      const previouslySelected=scenario;
      scenario=skillScenarios[index];configured=false;
      if(!goal.value.trim()||goal.value===previouslySelected.goal)goal.value=scenario.goal;
      cards.forEach(item=>item.setAttribute('aria-pressed',String(item===card)));
    });
    $('sw-back').onclick=()=>{step=0;show()};
    $('sw-next').onclick=()=>{
      if(!value('goal').trim())return status('说一句你想完成的事，或选择上面的场景。');
      if(!configured){
        $('sw-inputs').value=scenario.inputs;$('sw-outputs').value=scenario.outputs;
        $('sw-name').value=scenario.name+'-'+crypto.randomUUID().slice(0,8);
        configured=true;
      }
      status('');step=1;show();$('sw-inputs').focus();
    };
    $('sw-create').onclick=()=>{
      const params=Object.fromEntries(['name','goal','inputs','outputs','steps','dependencies'].map(key=>[key,value(key).trim()]));
      params.inputs ||= scenario.inputs;params.outputs ||= scenario.outputs;
      submit('create',params,$('sw-reference').files[0],{sample:scenario.sample,expected:params.outputs});
    };
    $('sw-try').onclick=()=>openFeature(workshopTabs[2]);
    show();
  }
  if(page===1){
    $('sw-import').onchange=async event=>{
      const file=event.target.files[0];if(!file)return;
      lock(true);status('正在导入…');
      try{const uploaded=await upload(file);const item=await post('import',{fileId:uploaded.id});if(live()){useVersion(item);status('导入成功。原始版本已保存。')}}catch(error){status(error.message)}finally{if(live()){lock(false);event.target.value=''}}
    };
    $('sw-revise').onclick=()=>submit('revise',{content:content.value,changes:value('changes')});
  }
  if(page===2){
    if(workshopExample){$('sw-sample').value=workshopExample.sample;$('sw-expected').value=workshopExample.expected}
    refreshVersions();
    $('sw-versions').onchange=async event=>{
      const id=event.target.value;if(!id)return;
      lock(true);
      try{const item=await api('/api/workshop/version/'+id);if(live()){useVersion(item);status('已打开 '+item.label)}}catch(error){status(error.message)}finally{if(live())lock(false)}
    };
    $('sw-test').onclick=()=>submit('test',{content:content.value,sample:value('sample'),expected:value('expected')});
    $('sw-run').onclick=()=>submit('run',{content:content.value,sample:value('sample')});
  }
  if(workshopPending.has(page)){lock(true);status('正在等待模型返回…');watchJob(workshopPending.get(page).id)}
}

const initialWorkshop=location.hash.match(/^#extend-([0-3])$/);
window.addEventListener('DOMContentLoaded',()=>{
  if(initialWorkshop){
    openModule(modules.find(m=>m.id==='extend'));
    openFeature(['开始创造','我的工具','模板广场','高级设置'][Number(initialWorkshop[1])]);
  }
});
