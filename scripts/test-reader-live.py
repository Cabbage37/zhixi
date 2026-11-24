"""Synthetic-only acceptance: real configured Agent, citations and follow-up."""
import io,json,sys,time
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.runtime/python')]
from scripts.reader_fixture import docx
def request(path,body=None,headers=None):
    data=json.dumps(body,ensure_ascii=False).encode() if isinstance(body,dict) else body
    with urlopen(Request('http://127.0.0.1:8765'+path,data=data,headers=headers or {'Content-Type':'application/json'}),timeout=240) as r:return json.load(r)
data=docx(['阅读助手验收材料（合成数据）','2025年项目收入为120万元，2024年收入为100万元，同比增长20%。','增长主要来自客户数量增加。成本为80万元，收入减成本为40万元；此处不代表净利润。','下一年度拟优化服务效率，但尚未确定具体投入金额。'])
upload=request('/api/upload',data,{'X-Filename':'reader-acceptance.docx'})
source=request('/api/reader/import',{'fileId':upload['id']})
evidence={'sid':source['id'],'name':source['name'],'turns':[]}
for question in ['2025年收入是多少，增长原因是什么？请引用原文。','刚才的40万元可以称为净利润吗？为什么？']:
    job=request('/api/reader/ask',{'sid':source['id'],'mode':'问答','question':question})
    print('Task started: '+job['id'],flush=True)
    deadline=time.time()+590
    while time.time()<deadline:
        job=request('/api/tasks/'+job['id'])
        if job['status'] not in ('queued','running'):break
        time.sleep(3)
    assert job['status']=='completed',job.get('result')
    result=job['readerResult'];assert result['citations']
    for c in result['citations']:
        b=next(b for b in source['blocks'] if b['id']==c['blockId']);assert c['quote'] in b['text']
    evidence['turns'].append(result);print('Verified answer and citations',flush=True)
request('/api/reader/note',{'sid':source['id'],'selection':{'blockId':source['blocks'][1]['id'],'quote':'2025年项目收入为120万元'}})
state=request('/api/reader/state/'+source['id']);assert len(state['history'])==2 and len(state['notes'])==1
(ROOT/'data/reader-acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: DOCX import, real Agent, citations, follow-up, excerpt persistence',flush=True)
