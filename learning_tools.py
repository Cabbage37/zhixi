"""Teach/grill sessions on the existing reading Agent task pipeline."""
import uuid
import reader_tools as reader

def create(body):
    topic = body.get('topic', '')
    if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 500:
        raise ValueError('请填写500字以内的学习主题或目标')
    mode, level = body.get('mode'), body.get('level')
    if mode not in ['teach', 'grill'] or level not in ['入门', '进阶', '深入']:
        raise ValueError('请选择学习方式和起始难度')
    origin = body.get('sourceId')
    if origin:
        _, original = reader.session(origin)
        if original.get('learning'): raise ValueError('请选择原始阅读材料')
        selected = reader.selection(original, body.get('selection'))
        blocks, limitations = original['blocks'], original['limitations']
    else:
        selected = None
        blocks, limitations = [], ['基于模型已有知识教学，未联网核验；实时数据和最新规定需另行查证。']
    sid = uuid.uuid4().hex
    source = {'id':sid, 'name':topic.strip(), 'kind':'.learning', 'url':'', 'blocks':blocks, 'notes':[], 'limitations':limitations,
              'learning':{'mode':mode, 'level':level, 'origin':origin, 'selection':selected}}
    folder = reader.BASE / sid
    folder.mkdir(parents=True)
    reader.save(folder/'source.json', source); reader.save(folder/'history.json', [])
    return source

def prepare(source, body, history):
    action = body.get('action')
    if action not in ['start','answer','hint','explain','recap','continue']:
        raise ValueError('无效学习操作')
    previous = history[-1] if history else None
    if body.get('previousTask') != (previous['taskId'] if previous else None):
        raise ValueError('学习记录已更新，请刷新后继续')
    if (not previous and action!='start') or (previous and action=='start'):
        raise ValueError('学习状态已变化，请刷新后继续')
    if previous and not previous['coaching']['nextQuestion'] and action in ['answer','hint','explain']:
        raise ValueError('请先继续学习，生成下一题')
    if action=='continue' and previous and previous['coaching']['nextQuestion']:
        raise ValueError('请先回答当前问题，或选择提示、讲解')
    answer=body.get('question','')
    if not isinstance(answer,str) or len(answer)>4000 or (action=='answer' and not answer.strip()):
        raise ValueError('请输入4000字以内的回答')
    return {'mode':'教我学' if source['learning']['mode']=='teach' else '考考我', 'question':answer.strip() if action=='answer' else {'start':'开始学习','hint':'给我提示','explain':'讲解这题','recap':'总结薄弱点','continue':'继续学习'}[action],
            'selection':source['learning']['selection'], 'history':history[-12:], 'learning':True, 'action':action,
            'previousTask':body.get('previousTask')}

def validate(source, options, draft):
    if not isinstance(draft,dict):raise ValueError('教学结果格式无效')
    for key in ['lesson','feedback','nextQuestion']:
        if not isinstance(draft.get(key),str) or len(draft[key])>12000:raise ValueError('教学内容格式无效')
    if draft.get('difficulty') not in ['入门','进阶','深入']:raise ValueError('教学难度格式无效')
    if draft.get('assessment') not in ['未作答','理解到位','部分理解','需要巩固','未评估']:raise ValueError('教学反馈格式无效')
    for key in ['mastered','gaps']:
        if not isinstance(draft.get(key),list) or len(draft[key])>20 or any(not isinstance(x,str) or len(x)>500 for x in draft[key]):raise ValueError('学习记录格式无效')
    action=options['action']
    # Non-answer actions never count as a fresh assessment, even when the model
    # describes performance from an earlier turn in a recap.
    if action!='answer':draft['assessment']='未作答' if action=='start' else '未评估'
    if action=='start' and (draft['feedback'].strip() or draft['mastered']):raise ValueError('首轮不能虚构用户表现')
    if action=='answer' and (not draft['feedback'].strip() or draft['assessment']=='未作答'):
        raise ValueError('作答后必须给出具体反馈')
    if action=='start' and source['learning']['mode']=='grill' and draft['lesson'].strip():raise ValueError('考考我首轮应直接出题，不提前给出讲解')
    if action!='recap' and not draft['nextQuestion'].strip():raise ValueError('缺少下一道学习问题')
    if action=='recap' and draft['nextQuestion'].strip():raise ValueError('学习总结不应同时发出新题')
    if action=='hint' and draft['nextQuestion']!=options['history'][-1]['coaching']['nextQuestion']:raise ValueError('提示应保留当前问题')
    cites=draft.get('citations',[])
    if not isinstance(cites,list) or len(cites)>20:raise ValueError('教学引用格式无效')
    verified=[reader.selection(source,c) for c in cites]
    if any(c is None for c in verified):raise ValueError('引用不能为空')
    if source['blocks'] and not verified:raise ValueError('材料教学缺少原文依据')
    if not source['blocks'] and cites:raise ValueError('主题学习不能编造材料出处')
    answer='\n\n'.join(v for v in [draft['lesson'],draft['feedback'],draft['nextQuestion']] if v.strip())
    if not answer:raise ValueError('教学内容为空')
    return {'answer':answer,'citations':verified,'coaching':{k:draft[k] for k in ['lesson','feedback','nextQuestion','assessment','difficulty','mastered','gaps']},'action':action}
