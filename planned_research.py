"""Execute a confirmed research plan chapter by chapter with inspectable evidence."""
import json
import re
from pathlib import Path
from planning_engine import explore, validate_research_plan

def save(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')
    temporary.replace(path)

def run(job,folder):
    from evidence_writing import ask
    state=json.loads((folder/'confirmed-plan.json').read_text('utf8'))
    plan=validate_research_plan(state['research_plan'])
    outputs=folder/'outputs';outputs.mkdir(exist_ok=True)
    research=folder/'chapters';research.mkdir(exist_ok=True)
    completed=[]
    for index,chapter in enumerate(plan['chapters'],1):
        save(folder/'research-progress.json',{'message':f"正在研究第 {index}/{len(plan['chapters'])} 章：{chapter['title']}"})
        path=research/(str(index)+'.json')
        if path.exists():
            completed.append(json.loads(path.read_text('utf8')));continue
        searches=explore([{'tool':'search','query':plan.get('title','')+' '+chapter['question']}])
        actions=[]
        for datum in chapter['data']:
            for url in re.findall(r'https?://[^\s<>"）)]+',str(datum.get('source',''))):
                actions.append({'tool':'fetch','url':url,'query':datum['metric']})
        for result in searches:
            for provider in result.get('result',[]) if isinstance(result.get('result'),list) else []:
                for url,title in provider.get('hits',[])[:2]:
                    if not any(a['url']==url for a in actions):actions.append({'tool':'fetch','url':url,'query':chapter['question']})
        evidence=explore(actions[:5])
        source_texts={}
        for index,item in enumerate(evidence,1):
            if item.get('status')!='verified':
                continue
            source=item['result']
            source_texts[str(index)]=source.get('content') or '\n'.join(
                f"第 {page['page']} 页\n{page['content']}" for page in source.get('matched_pages',[]))
        value=ask(folder,'financial-quick-research',
            '按已确认的逐章方案开展研究。不要改写研究计划。只依据实际返回的原文写有依据的段落。不得将假设、搜索摘要或规划示例当事实。缺失数据写入 gaps；无法得出结论时明确说明。返回 {"title":...,"paragraphs":[{"text":...,"citations":[{"source":"原文编号","quote":"逐字原文"}]}],"gaps":[...],"acceptance":[{"criterion":...,"met":布尔,"reason":...}]}。每个事实或推断段落都必须引用原文；推断明确标注，计算写公式和输入值。',
            {'chapter':chapter,'dependencies':plan.get('dependencies',[]),'previous_chapters':[{k:v for k,v in c.items() if k in ('title','gaps','acceptance')} for c in completed],'sources':source_texts})
        if not isinstance(value,dict) or not isinstance(value.get('paragraphs'),list):raise ValueError('章节研究输出格式不完整')
        for paragraph in value['paragraphs']:
            citations=paragraph.get('citations',[])
            if not citations:raise ValueError('章节段落缺少原文依据，未发布研究结论')
            for citation in citations:
                quote=str(citation.get('quote','')).strip()
                source=source_texts.get(str(citation.get('source')),'')
                if len(quote)<8 or re.sub(r'\s+','',quote) not in re.sub(r'\s+','',source):
                    raise ValueError('章节引用未通过原文核验，未发布研究结论')
        value['evidence']=evidence;save(path,value);completed.append(value)
    review=ask(folder,'financial-quick-research','独立审查章节与确认方案的一致性、口径、证据支持和缺口。返回 {"passed":布尔,"issues":[...],"summary":...}。缺失关键证据不得通过。',{'plan':plan,'chapters':[{k:v for k,v in chapter.items() if k!='evidence'} for chapter in completed]})
    if any(not chapter['paragraphs'] for chapter in completed):
        review['passed']=False
    save(outputs/'研究执行记录.json',{'planVersion':state['version'],'chapters':completed,'review':review})
    lines=['# '+state['title'],'','审查通过' if review.get('passed') is True else '研究草稿：独立审查仍有待解决事项','',str(review.get('summary',''))]
    for chapter in completed:
        lines+=['','## '+chapter['title']]
        for paragraph in chapter['paragraphs']:
            lines+=['',paragraph['text']]
            for citation in paragraph.get('citations',[]):
                item=chapter['evidence'][int(citation['source'])-1]
                lines+=['> '+citation['quote'],'来源：'+item['request']['url']]
        lines+=['','待补充：'+'；'.join(map(str,chapter.get('gaps',[])))]
    (outputs/'逐章研究报告.md').write_text('\n'.join(lines),'utf8')
    print('逐章研究已保存。'+('独立审查通过。' if review.get('passed') is True else '成果标记为草稿，请查看审查与数据缺口。'))
