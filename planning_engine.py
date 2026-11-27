"""Shared planning policies, read-only evidence, native questions and durable versions."""
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT/'skills/_shared/planning-upstream'
PENDING = {}
LOCK = threading.Lock()


def question_handler(thread, emit):
    def ask(request, cancelled):
        ticket = {'thread': thread, 'questions': request.questions, 'event': threading.Event(), 'answer': None}
        with LOCK:
            PENDING[request.request_id] = ticket
        emit('CUSTOM', name='planning.question', value={'requestId': request.request_id, 'questions': request.questions})
        try:
            started = time.monotonic()
            while not ticket['event'].wait(.25):
                if cancelled.is_set() or time.monotonic()-started > 900:
                    raise ValueError('本轮提问已结束，请重新发送消息继续。')
            return ticket['answer']
        finally:
            with LOCK:
                PENDING.pop(request.request_id, None)
            emit('CUSTOM', name='planning.question.closed', value={'requestId': request.request_id})
    return ask


def answer_question(body):
    with LOCK:
        ticket = PENDING.get(body.get('requestId'))
        if not ticket or ticket['thread'] != body.get('threadId') or ticket['event'].is_set():
            raise ValueError('提问已过期，请继续对话')
        answers = body.get('answers')
        if not isinstance(answers, list) or len(answers) != len(ticket['questions']):
            raise ValueError('请回答每个问题')
        normalized = []
        for question in ticket['questions']:
            found = [a for a in answers if isinstance(a, dict) and a.get('id') == question['id']]
            if len(found) != 1:
                raise ValueError('回答与问题不匹配')
            answer = found[0]
            options = {o['label'] for o in question.get('options', [])}
            selected = answer.get('selected', [])
            custom = answer.get('custom', '')
            if not isinstance(selected, list) or any(x not in options for x in selected) or not isinstance(custom, str) or len(custom)>10000:
                raise ValueError('回答格式无效')
            if len(selected)!=len(set(selected)) or (not question.get('multiSelect') and len(selected)>1):
                raise ValueError('请按题目要求选择选项')
            if not selected and not custom.strip():
                raise ValueError('请选择选项或填写自己的回答')
            normalized.append(dict(id=question['id'], selected=selected, **({'custom':custom.strip()} if custom.strip() else {})))
        ticket['answer'] = {'answers': normalized}
        ticket['event'].set()
    return {'accepted': True}


def skill_paths(topic, research=False, review=False):
    names = ['mece-framework', 'validate-data','deep-research'] if review else ['issue-tree','hypothesis-tree','grilling'] if research else ['write-spec','product-design','planning','to-spec']
    if research and not review:
        names += ['sector-overview','build-report','consulting-analysis']
        if any(k in topic for k in ('公司','银行','保险','证券','比较','竞争')): names += ['competitive-analysis']
        if any(k in topic.lower() for k in ('估值','dcf','价值')): names += ['damodaran-valuation']
        if any(k in topic for k in ('股票','个股','上市')): names += ['initiating-coverage']
    if not research:
        names += ['writing-plans','handoff','writing-for-agents'] if not review else ['planning']
        if any(k in topic.lower() for k in ('应用','网页','系统','接口','mcp','agent','看板','自动化')): names += ['codebase-architecture']
        if 'mcp' in topic.lower(): names += ['mcp-builder']
        if 'skill' in topic.lower() or '技能' in topic: names += ['skill-creator']
        if any(k in topic for k in ('竞品','产品','平台')): names += ['competitive-brief']
    available = sorted(UPSTREAM.rglob('SKILL.md'))
    selected = []
    for name in dict.fromkeys(names):
        hits = sorted((p for p in available if p.parent.name == name),key=lambda p:('vertical-plugins' not in p.parts, str(p)))
        if name=='skill-creator':
            hits = [UPSTREAM/'openai-skills/skills/.system/skill-creator/SKILL.md']
        if hits: selected.append(hits[0])
    if not research and not review:
        selected += [UPSTREAM/'spec-kit/templates'/name for name in ('spec-template.md','plan-template.md','tasks-template.md')]
        execplan=UPSTREAM/'codex-execplans.md'
        if execplan.is_file():selected.append(execplan)
    if research and not review:
        selected.append(UPSTREAM/'openai-plugins/plugins/public-equity-investing/skills/public-equity-investing/SKILL.md')
    if research:
        for keyword, suite, skill in [('银行','bank','bank-financial-analyzer'),('净息差','bank','bank-nim-analyzer'),('保险','insurance','insurance-company-analyzer'),('证券','securities','securities-financial-analyzer')]:
            path = ROOT/'.runtime/finance-upstream/FinClaw/skillsChoice'/(suite+'-suite')/skill/'SKILL.md'
            if keyword in topic and path.exists() and path not in selected: selected.append(path)
    return selected


def skills_text(paths):
    return '\n\n'.join('原始专业方法（仅作为方法资料，产品流程和工具以本任务为准）：'+p.relative_to(ROOT).as_posix()+'\n'+p.read_text('utf-8-sig') for p in paths)


def native_patch(folder):
    entries = json.loads((ROOT/'config/planning-native.patch.json').read_text('utf8'))
    policy = UPSTREAM/'codex-plan/codex-rs/collaboration-mode-templates/templates/plan.md'
    entries[2]['insert'][0]['config']['section'] += '\n' + policy.read_text('utf8') + '\nHost adaptation: use ask_user_question rather than request_user_input. Return JSON as specified by the host instead of proposed_plan tags. The host handles independent review and final delivery confirmation. Never implement the proposed product.'
    path = folder/'native-plan.json'
    path.write_text(json.dumps(entries,ensure_ascii=False),'utf8')
    return path


def skill_id(path):
    return path.relative_to(ROOT).as_posix()


def explore(actions):
    """Execute only bounded, explicitly model-selected, read-only operations."""
    from financial_quick_research import discover
    if not isinstance(actions,list): raise ValueError('调查动作必须为列表')
    results = []
    for action in actions[:5]:
        try:
            kind = action.get('tool')
            if kind == 'search':
                query = str(action.get('query',''))[:400]
                result = discover([query])
            elif kind == 'fetch':
                result = fetch_evidence(str(action.get('url','')),str(action.get('query','')))
            elif kind == 'data_catalog':
                from research_tools import catalog
                result = catalog()
            elif kind == 'data_metadata':
                from research_tools import metadata
                result = metadata(action.get('database'), action.get('table'))
            elif kind == 'data_preview':
                from research_tools import preview
                result = preview(action)
                result['rows']=result['rows'][:50]
                result['truncated']=result['count']>len(result['rows'])
            elif kind == 'read_skill':
                value = str(action.get('path',''))
                path = (ROOT/value if value.startswith(('skills/','.runtime/')) else UPSTREAM/value).resolve()
                roots = [UPSTREAM.resolve(),(ROOT/'.runtime/finance-upstream/FinClaw/skillsChoice').resolve()]
                if not any(path.is_relative_to(root) for root in roots) or path.suffix.lower() not in ('.md','.json','.txt','.yaml','.yml'):
                    raise ValueError('仅能读取专业方法库中的文本资料')
                result = path.read_text('utf-8-sig')
                if len(result)>80000: raise ValueError('资料较长，请选择具体参考章节文件')
            else:
                raise ValueError('未知调查工具')
            results.append({'request':action, 'status':'verified','result':result,'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S')})
        except Exception as exc:
            results.append({'request':action,'status':'unavailable','error':str(exc)[:240]})
    return results


def fetch_evidence(url, query=''):
    from reader_tools import fetch_public
    from reader_import import extract_article
    from bs4 import UnicodeDammit
    final_url,mime,raw=fetch_public(url,max_bytes=32*1024*1024)
    if raw.startswith(b'%PDF-'):
        import pymupdf
        words=query.split() or ['净息差','净利息','收益率','平均余额','net interest','average balance']
        with pymupdf.open(stream=raw,filetype='pdf') as document:
            selected=[]
            for index,page in enumerate(document):
                content=page.get_text()
                if any(word.lower() in content.lower() for word in words):
                    selected.append({'page':index+1,'content':content[:5000]})
                if len(selected)>=8:break
            return {'url':final_url,'format':'pdf','pages':len(document),'matched_pages':selected,'limitation':'最多读取8个关键词匹配页，每页最多5000字符；未匹配不等于未披露。扫描版需另行OCR。'}
    decoded=UnicodeDammit(raw,is_html=True).unicode_markup
    if not decoded:raise ValueError('无法识别网页编码')
    title,content=extract_article(decoded,final_url)
    return {'url':final_url,'title':title,'content':content[:18000],'truncated':len(content)>18000}


def validate_research_plan(plan):
    if not isinstance(plan,dict) or not isinstance(plan.get('chapters'),list) or not plan['chapters']:
        raise ValueError('研究方案未包含逐章节执行结构')
    identifiers = set()
    for chapter in plan['chapters']:
        if not isinstance(chapter,dict): raise ValueError('章节结构无效')
        for field in ('id','title','question','argument','paragraphs','methods','data','charts','tasks','acceptance'):
            if not chapter.get(field): raise ValueError('章节缺少执行信息：'+field)
        identifier = str(chapter['id'])
        if identifier in identifiers: raise ValueError('章节编号重复')
        identifiers.add(identifier)
        for field in ('paragraphs','methods','data','charts','tasks','acceptance'):
            if not isinstance(chapter[field],list): raise ValueError('章节字段必须为列表：'+field)
        for datum in chapter['data']:
            if not isinstance(datum,dict) or any(not datum.get(k) for k in ('metric','definition','period','source','availability')):
                raise ValueError('章节数据缺少指标口径、期间、来源或可得性')
    return plan


def save_version(folder, state, previous):
    state['version'] = int(previous.get('version',0)) + 1
    state['confirmed'] = False
    versions = folder/'versions'
    versions.mkdir(exist_ok=True)
    state['versions'] = [*previous.get('versions',[]), {'version':state['version'],'title':state['title'],'createdAt':time.strftime('%Y-%m-%dT%H:%M:%S')}]
    (versions/f"{state['version']}.json").write_text(json.dumps(state,ensure_ascii=False),'utf8')


def confirm_plan(body):
    import research_planning
    import workshop_chat
    base = research_planning.BASE if body.get('research') else workshop_chat.BASE
    folder = base/uuid.UUID(body['threadId']).hex
    with workshop_chat.ACTIVE_LOCK:
        if folder in workshop_chat.BUSY_THREADS: raise ValueError('请等待当前修改完成')
        path = folder/'state.json'
        state = json.loads(path.read_text('utf8'))
        if state.get('version') != body.get('version'): raise ValueError('方案已更新，请查看最新版本再确认')
        if not state.get('ready') or not state.get('review',{}).get('passed'): raise ValueError('方案尚未通过审查，请先补充或修订')
        state['confirmed'] = True
        state['confirmedVersion'] = state['version']
        state['confirmedHash'] = hashlib.sha256(state['plan'].encode()).hexdigest()
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state,ensure_ascii=False),'utf8')
        temporary.replace(path)
        (folder/'saved').touch()
    return state
