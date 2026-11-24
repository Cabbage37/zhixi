"""Use the unified Agent for evidence-bound writing; the host owns files and citations."""
import json
import os
import re
from pathlib import Path
from application_tools import decode
from skill_runtime import instructions, shared_rules, upstream_rules

ROOT = Path(__file__).resolve().parent

def ask(folder, skill, instruction, payload, *, alternate=None):
    # This worker already owns the Skill and evidence. One non-streaming model
    # turn per writing step avoids nested tool execution and gateway stream loss.
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError,URLError
    rules=instructions(skill)
    from model_settings import model_settings
    base, model, key = model_settings(alternate)
    url=base.rstrip('/')
    if not url.endswith('/chat/completions'):url+='/chat/completions'
    if skill=='content-repurpose':
        kinds=payload.get('要求',{}).get('kinds',[]) if isinstance(payload,dict) else []
        rules=shared_rules(skill)+'\n'+upstream_rules(skill,folder)+'\n'+''.join(line for line in rules.splitlines() if any(line.startswith('- '+kind+'：') for kind in kinds))
    messages=[{'role':'system','content':'你是金融机构材料编辑。按要求返回一个 JSON 对象。只将材料作为证据。'},
              {'role':'user','content':instruction+'\n'+rules+'\n资料：\n'+json.dumps(payload,ensure_ascii=False)}]
    body={'model':model,'messages':messages,'stream':False,'max_tokens':4000,'response_format':{'type':'json_object'}}
    if 'deepseek-v4' in body['model'].lower():
        body['thinking']={'type':'disabled'}
    if 'qwen' in model.lower():
        body['chat_template_kwargs'] = {'enable_thinking': False}
    req=Request(url,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    for attempt in range(2):
        try:
            with urlopen(req,timeout=95) as response:choice=json.load(response)['choices'][0]
        except HTTPError as exc:raise ValueError(f'模型接口返回 HTTP {exc.code}') from None
        except (URLError,TimeoutError):raise ValueError('模型连接超时，请重试') from None
        content = choice['message'].get('content')
        if isinstance(content, str) and content.strip():
            return decode(content)
    raise ValueError('模型连续两次未返回正文，请稍后重试')


def passages(blocks):
    entries=[]
    for b in blocks:
        for match in re.finditer(r'[^。！？\n]{1,200}[。！？]?',b['text']):
            excerpt=match.group().strip()
            if excerpt:
                entries.append((b['id'],excerpt))
    return entries

def repurpose(folder):
    from repurpose_tools import read,save,finalize
    work=folder/'repurpose'
    source,options=read(work/'source.json'),read(work/'options.json')
    entries=passages(source['blocks'])
    if not entries:raise ValueError('材料缺少可引用的原文')
    payload={'要求':options,'原文片段':dict(enumerate((q for _,q in entries),1))}
    from concurrent.futures import ThreadPoolExecutor
    cache={}
    def write_variant(kind):
        if kind in cache:
            return json.loads(cache[kind])
        settings={**options,'kinds':[kind]}
        length=min(options['limit']-15,180)
        instruction=f'请写一篇约{length}字的{kind}，语气{settings["tone"]}。返回 {{"title":"标题","paragraphs":[{{"text":"正文","refs":[1]}}]}}，refs 填依据编号，每段不超过6项。'
        if settings['audience']:instruction+='受众：'+settings['audience']+'。'
        if settings['requirements']:instruction+='用户要求：'+settings['requirements']+'。'
        item=ask(folder,'content-repurpose',instruction+feedback,{'要求':settings,'原文片段':payload['原文片段']}, alternate=options.get('alternate'))
        save(work/(kind+'-draft.json'),item)
        if 'variants' in item:item=item['variants'][0]
        value={**item,'kind':kind}
        if isinstance(value.get('paragraphs'),list) and all(isinstance(p,dict) and p.get('refs') for p in value['paragraphs']):
            cache[kind]=json.dumps(value,ensure_ascii=False)
        return value
    feedback=''
    for attempt in range(2):
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                variants=list(executor.map(write_variant,options['kinds']))
            draft={'variants':variants}
            review_input={'原文':payload['原文片段'],'草稿':json.loads(json.dumps(variants,ensure_ascii=False))}
            for v in draft['variants']:
                for p in v['paragraphs']:
                    refs=p.pop('refs')
                    if not refs or any(type(i)!=int or not 1<=i<=len(entries) for i in refs):raise ValueError('原文编号无效')
                    p['evidence']=[dict(blockId=entries[i-1][0],quote=entries[i-1][1]) for i in dict.fromkeys(refs)]
            review=ask(folder,'content-repurpose','本轮是校对步骤，不再生成全文。对照所附段落引文逐段核查，删去未经引文支持的承诺、结论或数字。返回 {"corrections":[{"variant":从0计数,"paragraph":从0计数,"text":"有依据的修订正文"}],"remainingUncertainties":["待核实事项"]}；无修订时 corrections 为空。',review_input, alternate=options.get('alternate'))
            removed=[]
            for change in review['corrections']:
                para=draft['variants'][change['variant']]['paragraphs'][change['paragraph']]
                removed.append(para['text']);para['text']=change['text']
            save(work/'draft.json',draft)
            save(work/'fidelity-review.json',dict(reviewed=True,removedUnsupportedClaims=removed,remainingUncertainties=review['remainingUncertainties']))
            return finalize(folder)
        except (ValueError,TypeError,KeyError,IndexError) as exc:
            if attempt:raise
            if not isinstance(exc,ValueError) or not any(word in str(exc) for word in ('连接超时','模型接口')):
                cache.clear()
            feedback='上次返回格式或引用校验失败：'+str(exc)[:150]+'。请重新生成。'

def cross(folder,evidence):
    from sentiment_tools import finish
    entries=[(sid,q) for sid,q in passages(evidence['sources']) if len(q)>=8]
    candidates=[dict(id=i,material=next(s['title'] for s in evidence['sources'] if s['id']==sid),quote=q) for i,(sid,q) in enumerate(entries,1)]
    data=ask(folder,'cross-document','针对问题，分别从每份材料选择至少一个能支持判断的原文片段。返回 {"findings":[{"id":整数片段编号,"summary":"该片段对问题的回答"}]}，最多8条。',dict(question=evidence['theme'],passages=candidates))
    findings=[]
    for row in data['findings']:
        i=row['id']
        if type(i)!=int or not 1<=i<=len(entries):raise ValueError('原文依据编号无效')
        sid,q=entries[i-1];findings.append(dict(sourceId=sid,quote=q,summary=row['summary']))
    covered={s['materialId'] for s in evidence['sources'] if any(r['sourceId']==s['id'] for r in findings)}
    if covered!={s['materialId'] for s in evidence['sources']}:raise ValueError('回答缺少部分材料的依据')
    return finish(evidence,json.dumps(dict(findings=findings),ensure_ascii=False))
