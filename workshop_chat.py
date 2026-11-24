"""Co-creation turns on the existing local Harness, exposed as AG-UI events."""
import json
import threading
import uuid
from pathlib import Path
from application_tools import decode
from model_settings import model_settings
from skill_workshop import save_version, get

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/workshop-threads'
LOCK = threading.Lock()

def library_item(ident):
    folder=BASE/uuid.UUID(ident).hex
    path=folder/'state.json'
    if not path.is_file():raise ValueError('找不到这个工坊方案')
    state=json.loads(path.read_text('utf8'))
    state['workshopThread']=folder.name
    state['saved']=(folder/'saved').exists()
    return state

def save_to_library(ident):
    state=library_item(ident)
    if not (state.get('localApp') or state.get('artifact')):raise ValueError('请先完成创建')
    (BASE/state['workshopThread']/'saved').touch(exist_ok=True)
    return {'saved':True}

def run(handler, raw):
    request = json.loads(raw)
    thread = uuid.UUID(request['threadId']).hex
    prior = request.get('state') or {}
    if prior.get('workshopThread'):
        thread = uuid.UUID(prior['workshopThread']).hex
    elif prior.get('plan') and not (BASE/thread/'state.json').exists():
        # Older clients restored the plan but CopilotKit assigned a fresh transport ID.
        matches=[]
        for candidate in BASE.glob('*/state.json'):
            stored=json.loads(candidate.read_text('utf8'))
            if stored.get('plan')==prior['plan'] and stored.get('artifact')==prior.get('artifact'):
                matches.append(candidate.parent.name)
        if len(matches)==1:
            thread=matches[0]
    folder = BASE / thread
    folder.mkdir(parents=True, exist_ok=True)
    statefile = folder / 'state.json'
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
    handler.send_header('Cache-Control', 'no-cache')
    handler.end_headers()
    def emit(kind, **data):
        event = json.dumps(dict(type=kind, **data), ensure_ascii=False)
        handler.wfile.write(('data: '+event+'\n\n').encode())
        handler.wfile.flush()
    ids = dict(threadId=request['threadId'], runId=request['runId'])
    emit('RUN_STARTED', **ids)
    if not LOCK.acquire(blocking=False):
        emit('RUN_ERROR', message='上一轮仍在处理中，请稍后再试。')
        return
    try:
        state = json.loads(statefile.read_text('utf8')) if statefile.exists() else {}
        state['workshopThread']=thread
        messages = request['messages']
        command = request.get('forwardedProps',{}).get('create') is True
        testing = request.get('forwardedProps',{}).get('sample')
        creating = command or bool(state.get('artifact') or state.get('localApp'))
        if command and not state.get('ready'):
            raise ValueError('请先补全方案。')
        from deepseek_harness import DeepSeekHarness
        base, model, key = model_settings()
        rules = (ROOT / ('skills/skill-workshop/references/openai-skill-creator/SKILL.md' if creating
                         else 'skills/learning-coach/references/upstream/grilling.md')).read_text('utf8')
        instruction = ('根据当前方案生成完整 SKILL.md。修改保持原 YAML name。返回 JSON 含 reply, content。'
                       if creating else '用中文与员工讨论想法，维护当前方案。返回 JSON 含 reply、plan（纯文本）、ready（布尔值）、route（skill、streamlit 或 nicegui）。每轮只问影响方案的问题。固定工作方法选 skill，金融数据看板、数据分析、Excel/CSV 分析选 streamlit，一般小工具、查询页面、业务应用和内部网页选 nicegui。')
        if not creating:
            instruction += '这是普通员工对话。不要展示或询问技术类型，由你自行判断。每次最多问一个必要的业务问题。目标、输入、输出足够清楚就 ready=true。方案限200字；不要自行增加历史存档、审批等需求。'
        if testing:
            if not state.get('artifact') or not isinstance(testing,str) or len(testing)>12000:
                raise ValueError('请先创建工作方法，再输入试用材料。')
            rules=get(state['artifact'])['content']
            instruction='按上述工作方法处理试用材料，返回 JSON 含 reply，内容为实际结果。'
        context = dict(sample=testing) if testing else dict(state=state, messages=messages[-16:])
        if state.get('artifact'):
            context['previous']=get(state['artifact'])['content']
        patch=folder/'tools.json'
        patch.write_text(json.dumps([dict(id=i,disabled=True) for i in ('persistent-pwsh','persistent-bash')]),'utf8')
        with DeepSeekHarness(provider='deepseek-official',base_url=base,model=model,api_key=key,cwd=str(folder),profile='sdk-minimal',patches=(str(patch),),dsh_home=str(ROOT/'data/harness')) as harness:
            if creating and not testing and state['route'] not in ('skill','nicegui','streamlit'):
                route=harness.run('根据方案判断实现。金融数据看板或分析工具选 streamlit，一般业务应用选 nicegui。仅返回 JSON {"route":"streamlit 或 nicegui"}。方案：'+state['plan'],session_id=uuid.uuid4().hex)
                state['route']=decode(route.final_response)['route']
                if state['route'] not in ('streamlit','nicegui'):raise ValueError('未能识别应用类型，请重试。')
            if creating and not testing and state['route'] in ('streamlit','nicegui'):
                from workshop_local import build
                if not (command and state.get('localApp')):
                    state['localApp']=build(harness,state,messages,folder,lambda msg:emit('CUSTOM',name='workshopProgress',value=msg))
                value={'reply':'应用已保存，可在右侧预览并继续提出修改。'}
            else:
                result=harness.run(rules+'\n'+instruction+'\n'+json.dumps(context,ensure_ascii=False),session_id=uuid.uuid4().hex)
                value=decode(result.final_response)
        reply=value['reply']
        if not isinstance(reply,str) or not reply.strip():raise ValueError('本轮未生成答复，请重试。')
        if testing:
            state['sampleResult']=reply
        elif creating and state['route']=='skill':
            state.pop('sampleResult',None)
            item=save_version(value['content'],'共创版本',state.get('artifact'))
            state.update(artifact=item['id'],name=item['name'],preview=value['content'])
        elif not creating:
            if value['route'] not in ('skill','streamlit','nicegui') or not isinstance(value['ready'],bool) or not isinstance(value['plan'],str):
                raise ValueError('方案结构不完整，请重试。')
            state.update({k:value[k] for k in ('plan','ready','route')})
        temp=statefile.with_suffix('.tmp')
        temp.write_text(json.dumps(state,ensure_ascii=False),'utf8')
        temp.replace(statefile)
        mid=uuid.uuid4().hex
        emit('TEXT_MESSAGE_START',messageId=mid,role='assistant')
        emit('TEXT_MESSAGE_CONTENT',messageId=mid,delta=reply)
        emit('TEXT_MESSAGE_END',messageId=mid)
        emit('STATE_SNAPSHOT',snapshot=state)
        emit('RUN_FINISHED',**ids)
    except Exception as exc:
        emit('RUN_ERROR',message=str(exc) if isinstance(exc,ValueError) else '工坊执行失败，请重试。')
    finally:
        LOCK.release()
