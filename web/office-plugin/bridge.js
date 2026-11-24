/* ONLYOFFICE community plugin; expose a fixed command set, never arbitrary code. */
(function(){
 const origin=location.origin;let nonce=null,busy=false,marks=[];
 window.Asc.plugin.init=function(){window.top.postMessage({type:'zhixi-office-ready'},origin)};
 window.addEventListener('message',function(e){
  if(e.source!==window.top||e.origin!==origin)return;
  const m=e.data;if(m?.type==='zhixi-office-connect'){nonce=m.nonce;return}
  if(!nonce||m?.type!=='zhixi-office-command'||m.nonce!==nonce)return;
  const reply=(result)=>{busy=false;window.top.postMessage({type:'zhixi-office-result',id:m.id,nonce,result},origin)};
  if(busy){window.top.postMessage({type:'zhixi-office-result',id:m.id,nonce,result:{error:'编辑器正在处理上一项操作'}},origin);return}busy=true;
  if(m.action==='undo'||m.action==='redo'){
   const undo=m.action==='undo',method=undo?'Undo':'Redo';
   window.Asc.plugin.executeMethod(undo?'CanUndo':'CanRedo',[],can=>{
    if(can===false){reply({error:undo?'没有可撤销的操作':'没有可重做的操作'});return}
    window.Asc.plugin.executeMethod(method,[],()=>{
     window.Asc.plugin.executeMethod('GetFileHTML',[],html=>{
      if(typeof html!=='string'){reply({error:'编辑器未能读取当前内容，请从正文确认操作结果'});return}
      const page=new DOMParser().parseFromString(html,'text/html');
      reply({paragraphs:[...page.querySelectorAll('p,h1,h2,h3,h4,h5,h6')].map((p,index)=>({index,text:p.textContent,level:p.tagName.startsWith('H')?Number(p.tagName[1])-1:9}))});
     });
    });
   });return;
  }
  if(!['snapshot','locate','apply','highlight','clearHighlights'].includes(m.action)){reply({error:'不支持的操作'});return}
  window.Asc.scope.request={action:m.action,...m.payload,marks};
  window.Asc.plugin.callCommand(function(){
   const req=Asc.scope.request,doc=Api.GetDocument(),ps=doc.GetAllParagraphs();
   if(req.action==='clearHighlights'){
    const ranges=req.marks.map(mark=>doc.GetBookmarkRange(mark.name));
    if(ranges.some((range,i)=>!range||range.GetText()!==req.marks[i].text))return {error:'高亮区域在手动编辑后变化，请先撤销该区域修改再清除标记'};
    for(let i=0;i<ranges.length;i++){ranges[i].SetHighlight(req.marks[i].color);doc.DeleteBookmark(req.marks[i].name)}
    return {ok:true,cleared:true};
   }
   if(req.action==='highlight'){
    const marks=[];const occupied=[];
    for(const issue of req.issues){
     if(!issue.anchor)continue;
     const matches=ps.filter(p=>p.GetText().replace(/[\r\n]+$/,'')===issue.anchor.paragraphText);
     if(matches.length!==1)continue;
     const ranges=matches[0].Search(issue.anchor.quote,true);
     if(ranges.length!==1||ranges[0].GetText()!==issue.anchor.quote)continue;
     const range=ranges[0],start=range.GetStartPos(),end=range.GetEndPos();
     if(occupied.some(([a,b])=>start<b&&a<end))continue;
     // Only mark uniformly formatted spans, so restoring never flattens a pre-existing highlight.
     const color=range.GetTextPr().GetHighlight()||'none';
     const colors=new Set();
     for(let n=0;n<issue.anchor.quote.length;n++){const part=range.GetRange(n,n+1);if(part)colors.add(part.GetTextPr().GetHighlight()||'none')}
     if(colors.size!==1||!colors.has(color))continue;
     const name='ZX_'+issue.id;
     if(!range.AddBookmark(name))continue;
     range.SetHighlight(issue.color);occupied.push([start,end]);marks.push({name,text:issue.anchor.quote,color});
    }
    return {ok:true,marks};
   }
   if(req.action==='snapshot')return {paragraphs:ps.map((p,i)=>({index:i,text:p.GetText().replace(/[\r\n]+$/,''),level:p.GetOutlineLvl()}))};
   if(!req.anchor)return {error:'该问题无法唯一定位，请在编辑器中手动查找'};
   let candidates=ps.filter(p=>p.GetText().replace(/[\r\n]+$/,'')===req.anchor.paragraphText);
   if(candidates.length!==1)return {error:'原文段落已变化或存在重复，拒绝自动替换，请重新体检或手动编辑'};
   const p=candidates[0],ranges=p.Search(req.anchor.quote,true);
   if(ranges.length!==1||ranges[0].GetText()!==req.anchor.quote)return {error:'原文片段已变化或不唯一，拒绝替换'};
   ranges[0].Select();return {ok:true};
  },false,['highlight','clearHighlights'].includes(m.action),function(result){
   if(result?.marks)marks=result.marks;if(result?.cleared)marks=[];
   if(!result?.ok||m.action!=='apply'){reply(result||{error:'编辑器未返回结果'});return}
   // Smart replacement retains surrounding paragraph/run formatting.
   window.Asc.plugin.executeMethod('ReplaceTextSmart',[[m.payload.replacement]],function(ok){reply(ok===false?{error:'替换失败'}:{ok:true})});
  });
 });
})();
