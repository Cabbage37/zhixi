async function renderStudio(feature, thread=null, seed=null){
  const view=$('feature-view');
  const archive=feature==='我的方案';
  history.replaceState(null,'',archive?'#extend-1':'#extend-0');
  view.replaceChildren();
  if(!archive){
    const frame=document.createElement('iframe');
    const url=new URL('/workshop-chat.html',location.origin);
    if(thread)url.searchParams.set('thread',thread);
    if(seed?.goal)url.searchParams.set('idea',seed.goal);
    frame.title='AI 工坊对话共创';frame.src=url;
    frame.style.cssText='width:100%;height:75vh;border:0;background:white;border-radius:14px';
    view.append(frame);return;
  }
  const list=document.createElement('section');list.className='panel studio-drafts';view.append(list);
  try{
    const entries=await api('/api/workshop-library');
    const search=document.createElement('input');
    search.type='search';search.placeholder='搜索方案名称';search.setAttribute('aria-label','搜索方案名称');
    const results=document.createElement('div');
    if(entries.length)list.append(search,results);
    function draw(){
    results.replaceChildren();
    for(const item of entries.filter(item=>item.title.toLowerCase().includes(search.value.trim().toLowerCase()))){
      const button=text('button',item.title);button.className='secondary';
      button.onclick=()=>{openFeature('方案共创');renderStudio('方案共创',item.id)};
      results.append(button);
    }
    if(!results.childElementCount)results.append(text('p','没有匹配的方案。'));
    }
    search.oninput=draw;draw();
    if(!entries.length)list.append(text('p','第一次共创后，方案会自动保存在这里。'));
  }catch(e){list.append(text('p',e.message))}
}
window.addEventListener('DOMContentLoaded',()=>{
  const match=location.hash.match(/^#extend-([0-3])$/);
  if(match)openModule(modules.find(m=>m.id==='extend'),match[1]==='1'?'我的方案':'方案共创');
});
