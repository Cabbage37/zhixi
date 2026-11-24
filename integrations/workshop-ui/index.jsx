import React from 'react';
import {createRoot} from 'react-dom/client';
import {CopilotKitProvider,CopilotChat,useAgent} from '@copilotkit/react-core/v2';
import {HttpAgent} from '@ag-ui/client';
import '@copilotkit/react-core/v2/styles.css';
let threadId,agent;
function Workshop(){
 const {agent:chat}=useAgent({agentId:'workshop'});
 const state=chat.state||{};
 const [added,setAdded]=React.useState(!!state.saved);
 async function save(){
   try{
     const r=await fetch('/api/workshop-library/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:state.workshopThread||threadId})});
     if(!r.ok)throw Error((await r.json()).error);
     setAdded(true);
   }catch(e){setError(e.message)}
 }
 function fresh(){localStorage.removeItem('zhixi-workshop-chat');location.replace('/workshop-chat.html')}
 const [sample,setSample]=React.useState('');
 const [error,setError]=React.useState('');
 const [stage,setStage]=React.useState('');
 const [pending,setPending]=React.useState(false);
 const inFlight=React.useRef(false);
 async function act(props){
   if(inFlight.current || chat.isRunning)return;
   inFlight.current=true;
   setPending(true);setStage('正在准备…');
   setError('');
   try{
     await chat.runAgent({forwardedProps:props},{
       onCustomEvent:({event})=>{if(event.name==='workshopProgress')setStage(event.value)},
       onRunErrorEvent:({event})=>setError(event.message || '本次操作未完成，请重试。')
     });
   }catch(e){setError(e.message || '连接中断，请重试。')}
   finally{inFlight.current=false;setPending(false)}
 }
 React.useEffect(()=>{localStorage.setItem('zhixi-workshop-chat',JSON.stringify({threadId,messages:chat.messages,state}));if(state.workshopThread)localStorage.setItem('zhixi-chat-'+state.workshopThread,JSON.stringify(chat.messages));},[chat.messages,state]);
 return <><header className="chat-actions"><button disabled={pending||chat.isRunning} onClick={fresh}>新对话</button>{(state.localApp||state.artifact)&&<button disabled={added} onClick={save}>{added?'已加入我的工具':'加入我的工具'}</button>}</header><main><section><CopilotChat agentId="workshop" labels={{welcomeMessageText:'有什么想法？和我聊聊。',chatInputPlaceholder:'说说你希望 AI 帮你做什么…'}}/></section>{state.plan&&<aside className={state.localApp?'app-preview':''}><h2>{state.localApp?.name||(state.artifact?'我的工作方法':'当前方案')}</h2>{state.localApp?<details><summary>查看方案</summary><p>{state.plan}</p></details>:<p>{state.plan}</p>}{state.localApp&&<a href={state.localApp.preview} target="_blank" rel="noreferrer">打开应用预览</a>}{state.localApp&&<iframe style={{width:"100%",height:"64vh",border:0}} title="应用预览" src={state.localApp.preview}/>}{state.artifact?<div><p>已保存 · {state.name}</p><label>试用材料<textarea value={sample} onChange={e=>setSample(e.target.value)}/></label><button disabled={!sample.trim()||pending||chat.isRunning} onClick={()=>act({sample})}>{pending?'正在试运行…':'试运行'}</button>{state.sampleResult&&<p>{state.sampleResult}</p>}<p><a href={'/api/workshop/zip/'+state.artifact}>下载工作方法</a></p></div>:!state.localApp&&state.ready&&<button disabled={pending||chat.isRunning} onClick={()=>act({create:true})}>{pending?stage:error?'重新创建':'开始创建'}</button>}{error&&<p role="alert">{error}</p>}</aside>}</main></>
}
async function start(){
 let saved=JSON.parse(localStorage.getItem('zhixi-workshop-chat')||'{}');
 const id=new URLSearchParams(location.search).get('thread')||saved.state?.workshopThread;
 if(id){
   const r=await fetch('/api/workshop-library/'+encodeURIComponent(id));
   if(r.ok){const state=await r.json();saved={threadId:id,state,messages:JSON.parse(localStorage.getItem('zhixi-chat-'+id)||'null')||(saved.state?.workshopThread===id?saved.messages:[])}} 
 }
 threadId=saved.threadId||crypto.randomUUID();
 agent=new HttpAgent({url:'/api/workshop-chat',threadId,initialMessages:saved.messages||[],initialState:saved.state||{}});
 createRoot(document.getElementById('root')).render(<CopilotKitProvider agents__unsafe_dev_only={{workshop:agent}}><Workshop/></CopilotKitProvider>);


}
start();
