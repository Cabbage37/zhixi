"""Validate grounded office variants and export the selected versions."""
import json,re,sys,zipfile,io
from financial_quantities import unsupported_quantities
from pathlib import Path
from material_tools import extract

KINDS=['领导速览','邮件正文','汇报提纲','会议发言稿']
TONES=['简明正式','分析详实','自然口语']

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def validate_options(value):
    if not isinstance(value,dict):raise ValueError('一稿多用参数无效')
    kinds=value.get('kinds')
    if not isinstance(kinds,list) or not kinds or any(k not in KINDS for k in kinds) or len(set(kinds))!=len(kinds):raise ValueError('请选择有效且不重复的用途')
    tone=value.get('tone','简明正式');limit=value.get('limit',600)
    if tone not in TONES:raise ValueError('请选择有效表达风格')
    if type(limit)!=int or not 100<=limit<=3000:raise ValueError('每篇字数上限应为100至3000')
    result={'kinds':[k for k in KINDS if k in kinds],'tone':tone,'limit':limit}
    if isinstance(value.get('alternate'),bool):
        result['alternate'] = value['alternate']
    for key in ['audience','requirements']:
        text=value.get(key,'')
        if not isinstance(text,str) or len(text)>2000:raise ValueError('补充说明最多2000字')
        result[key]=text.strip()
    return result

def prepare(source,folder,options):
    folder.mkdir(exist_ok=True)
    evidence=extract(source)
    save(folder/'source.json',evidence);save(folder/'options.json',validate_options(options))
    return evidence

def budget_warnings(blocks):
    from decimal import Decimal
    amounts=[]
    notices=[]
    for block in blocks:
        for match in re.finditer(r'预算(合计)?(?:为)?\s*([0-9]+(?:\.[0-9]+)?)\s*(亿元|万元|元)',block['text']):
            total,number,unit=match.groups()
            value=Decimal(number)
            if not total:
                amounts.append((value,unit))
                continue
            if len(amounts)>=2 and all(u==unit for _,u in amounts):
                subtotal=sum(v for v,_ in amounts)
                if subtotal!=value:
                    notices.append(f"预算待核对：原文合计{value}{unit}，前述预算逐项相加为{subtotal}{unit}。请确认统计范围后再引用。")
            amounts.clear()
    return notices

def finalize(folder):
    work=folder/'repurpose';source=read(work/'source.json');options=read(work/'options.json');draft=read(work/'draft.json')
    if not (work/'fidelity-review.json').exists():raise ValueError('请先逐段对照引用完成保真自审，保存 fidelity-review.json')
    review=read(work/'fidelity-review.json')
    if not isinstance(review,dict) or review.get('reviewed') is not True or any(not isinstance(review.get(k),list) or any(not isinstance(x,str) for x in review[k]) for k in ['removedUnsupportedClaims','remainingUncertainties']):raise ValueError('保真自审记录格式无效')
    variants=draft.get('variants') if isinstance(draft,dict) else None
    if not isinstance(variants,list) or len(variants)!=len(options['kinds']):raise ValueError('生成版本数量与所选用途不一致')
    lookup={b['id']:b for b in source['blocks']};seen=set();validated=[]
    for item in variants:
        if not isinstance(item,dict) or item.get('kind') not in options['kinds'] or item['kind'] in seen:raise ValueError('版本用途无效或重复')
        seen.add(item['kind']);title=item.get('title');paras=item.get('paragraphs')
        if not isinstance(title,str) or not title.strip() or len(title)>120:raise ValueError('版本标题无效')
        if not isinstance(paras,list) or not 1<=len(paras)<=60:raise ValueError('版本正文为空或过长')
        out=[];warnings=budget_warnings(source['blocks']);citations=0
        for para in paras:
            if not isinstance(para,dict) or not isinstance(para.get('text'),str) or not para['text'].strip():raise ValueError('正文段落无效')
            refs=para.get('evidence',[])
            if not isinstance(refs,list) or len(refs)>15:raise ValueError('原文依据格式无效')
            evidence=[]
            for ref in refs:
                if not isinstance(ref,dict):raise ValueError('原文依据格式无效')
                block=lookup.get(ref.get('blockId'));quote=ref.get('quote')
                if not block or not isinstance(quote,str) or not quote.strip() or quote not in block['text']:raise ValueError('原文引用未匹配，请修正后生成')
                evidence.append({'blockId':block['id'],'location':block['location'],'quote':quote});citations+=1
            # A warning is not a factual verdict: formatting and units can change.
            numbers=re.findall(r'(?<![0-9])\d+(?:[.,]\d+)*(?:%|％)?',para['text'])
            quoted=' '.join(e['quote'] for e in evidence)
            quoted_numbers=set(re.findall(r'(?<![0-9])\d+(?:[.,]\d+)*(?:%|％)?',quoted))
            missing=[n for n in numbers if n not in quoted_numbers]
            missing.extend(unsupported_quantities(para['text'], (e['quote'] for e in evidence)))
            if missing:warnings.append('第'+str(len(out)+1)+'段部分数字未在该段引用中直接匹配：'+'、'.join(dict.fromkeys(missing)))
            if not evidence and re.search(r'将|会及时|另行通知|确保|保证|承诺|请.*(?:配合|提交|执行)',para['text']):
                warnings.append('第'+str(len(out)+1)+'段含行动安排或承诺措辞，但未附原文依据，请核对后使用。')
            out.append({'text':para['text'].strip(),'evidence':evidence})
        if not citations:raise ValueError('每个版本至少应有一条准确原文依据')
        body='\n\n'.join(p['text'] for p in out)
        count=len(re.sub(r'\s','',title+body))
        if count>options['limit']:raise ValueError(f"{item['kind']}共{count}字，超过{options['limit']}字上限，请压缩后重试")
        validated.append({'kind':item['kind'],'title':title.strip(),'paragraphs':out,'text':title.strip()+'\n\n'+body,'count':count,'warnings':warnings})
    validated.sort(key=lambda v:KINDS.index(v['kind']))
    result={'variants':validated,'sourceName':source['name'],'limitations':source['limitations'],'reviewUncertainties':review['remainingUncertainties'],'note':'原文引用已逐条匹配，Agent已执行保真自审；这不等于独立事实核验，使用前请复核。'}
    # Validate every version before publishing any output.
    artifacts={}
    for v in validated:
        notice='\n\n待核对\n'+'\n'.join(v['warnings']) if v['warnings'] else ''
        artifacts[v['kind']+'.txt']=(v['text']+notice).encode('utf-8-sig')
        evidence='\n'.join(f"- 第{i}段 · {e['location']}：{e['quote']}" for i,p in enumerate(v['paragraphs'],1) for e in p['evidence'])
        artifacts[v['kind']+'.md']=('# '+v['title']+'\n\n'+'\n\n'.join(p['text'] for p in v['paragraphs'])+notice+'\n\n---\n原文依据\n'+evidence).encode('utf-8')
    bundle=io.BytesIO()
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in artifacts.items():z.writestr(name,data)
    artifacts['一稿多用合集.zip']=bundle.getvalue()
    for name,data in artifacts.items():(folder/'outputs'/name).write_bytes(data)
    save(work/'result.json',result)
    return result

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');folder=Path(sys.argv[1]).resolve()
    try:print(json.dumps({'versions':len(finalize(folder)['variants'])},ensure_ascii=False))
    except Exception as e:save(folder/'repurpose/error.json',{'error':str(e)});raise
