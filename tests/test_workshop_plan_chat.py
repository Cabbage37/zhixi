import io
import json
import threading
import uuid
from types import SimpleNamespace
import pytest
import workshop_chat as workshop
import planning_engine as engine
from planning_turn import COCREATE_FIELDS, RESEARCH_FIELDS


def fake_harness(monkeypatch, fail_review=False, research=False):
    import deepseek_harness
    calls=[]
    class Harness:
        def __init__(self, **kwargs): self.options=kwargs
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def close(self): pass
        def run(self,prompt,**kwargs):
            calls.append((prompt,kwargs.get('session_id')))
            if prompt=='/plan':return SimpleNamespace(final_response='Plan mode on.',finish_reason='completed',events=[{'type':'plan/mode','data':{'active':True}}])
            if prompt.startswith('你是独立方案审查者'):
                value={'passed':not fail_review,'summary':'独立检查','issues':[{'severity':'blocking','section':'数据','problem':'来源缺失','fix':'补充来源'}] if fail_review else []}
            elif '"actions"' in prompt[:1000] or prompt.startswith('你是知析规划助手') or prompt.startswith('根据首轮调查'):
                value={'actions':[{'tool':'data_catalog'}]}
            else:
                value={'reply':'已更新','title':'银行研究数据接口','ready':True,'sections':dict.fromkeys(RESEARCH_FIELDS if research else COCREATE_FIELDS,'可执行的研究或实施内容'),'decisions':[{'question':'输入','choice':'脱敏 CSV','reason':'用户指定','status':'已确认'}]}
                if research:value['research_plan']={'title':'研究','chapters':[{'id':'1','title':'盈利质量','question':'盈利来源','argument':'对比趋势','paragraphs':['先对比，再解释'],'methods':['同业比较'],'data':[{'metric':'净息差','definition':'净利息收入/平均生息资产','period':'2022-2025','source':'年报','availability':'待核实'}],'charts':['趋势图'],'tasks':['核对年报'],'acceptance':['记录页码']}],'dependencies':[]}
            return SimpleNamespace(final_response=json.dumps(value,ensure_ascii=False),finish_reason='completed',events=[])
    monkeypatch.setattr(deepseek_harness,'DeepSeekHarness',Harness)
    monkeypatch.setattr(workshop,'model_settings',lambda:('','',''))
    monkeypatch.setattr(engine,'explore',lambda actions:[{'request':a,'status':'verified','result':[]} for a in actions])
    return calls


def turn(thread,messages,research=False):
    handler=SimpleNamespace(wfile=io.BytesIO(),send_response=lambda *args:None,send_header=lambda *args:None,end_headers=lambda:None)
    workshop.run(handler,json.dumps(dict(threadId=thread,runId=uuid.uuid4().hex,messages=messages)),research=research)
    return handler.wfile.getvalue().decode()


def test_plan_roundtrip_and_independent_review(tmp_path,monkeypatch):
    calls=fake_harness(monkeypatch)
    monkeypatch.setattr(workshop,'BASE',tmp_path)
    thread=uuid.uuid4().hex
    messages=[]
    for text in ['规划一个 MCP','输入为脱敏 CSV']:
        messages.append(dict(id=uuid.uuid4().hex,role='user',content=text))
        assert 'RUN_FINISHED' in turn(thread,messages)
        state=workshop.library_item(thread);messages=state['messages']
    assert state['version']==2 and len(state['versions'])==2
    assert state['ready'] and not state['confirmed']
    assert (tmp_path/thread/'versions/1.json').exists()
    writer_sessions={sid for p,sid in calls if p.startswith('根据用户意图')}
    reviewers={sid for p,sid in calls if p.startswith('你是独立方案审查者')}
    assert writer_sessions.isdisjoint(reviewers)
    confirmed=engine.confirm_plan({'threadId':thread,'version':2})
    assert confirmed['confirmed'] and confirmed['confirmedHash']
    with pytest.raises(ValueError,match='已更新'):engine.confirm_plan({'threadId':thread,'version':1})


def test_research_structure_rejects_missing_execution_details():
    with pytest.raises(ValueError,match='执行信息'):
        engine.validate_research_plan({'chapters':[{'id':'1','title':'只有标题'}]})


def test_unconfirmed_research_cannot_be_handed_off():
    import research_planning
    with pytest.raises(ValueError,match='确认'):
        research_planning.handoff({'confirmed':False})


def test_failed_review_cannot_be_confirmed(tmp_path,monkeypatch):
    fake_harness(monkeypatch,fail_review=True)
    monkeypatch.setattr(workshop,'BASE',tmp_path)
    thread=uuid.uuid4().hex
    assert 'RUN_FINISHED' in turn(thread,[{'role':'user','content':'规划应用'}])
    assert not workshop.library_item(thread)['ready']
    with pytest.raises(ValueError,match='审查'):engine.confirm_plan({'threadId':thread,'version':1})


def test_native_question_custom_answer_and_thread_binding():
    request=SimpleNamespace(request_id='question-test',questions=[{'id':'scope','question':'选择范围','options':[{'label':'年度','description':'完整年报'}]}])
    result=[];cancel=threading.Event();opened=threading.Event()
    callback=engine.question_handler('thread-a',lambda kind,**data:opened.set() if data.get('name')=='planning.question' else None)
    worker=threading.Thread(target=lambda:result.append(callback(request,cancel)))
    worker.start();assert opened.wait(2)
    with pytest.raises(ValueError):engine.answer_question({'threadId':'wrong','requestId':'question-test','answers':[]})
    engine.answer_question({'threadId':'thread-a','requestId':'question-test','answers':[{'id':'scope','selected':[],'custom':'只研究半年报'}]})
    worker.join(2)
    assert result[0]['answers'][0]['custom']=='只研究半年报'
    assert 'question-test' not in engine.PENDING


def test_research_structured_delivery(tmp_path,monkeypatch):
    import research_planning
    fake_harness(monkeypatch,research=True)
    monkeypatch.setattr(research_planning,'BASE',tmp_path)
    thread=uuid.uuid4().hex
    assert 'RUN_FINISHED' in turn(thread,[{'role':'user','content':'银行盈利质量研究'}],True)
    state=workshop.library_item(thread,tmp_path)
    assert state['research_plan']['chapters'][0]['data'][0]['definition']=='净利息收入/平均生息资产'
