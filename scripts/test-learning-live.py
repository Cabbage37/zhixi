"""Real configured Agent acceptance with synthetic learning content only."""
import json,time,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
def req(path,body=None,headers=None):
    raw=json.dumps(body,ensure_ascii=False).encode() if isinstance(body,dict) else body
    try:
        with urlopen(Request('http://127.0.0.1:8765'+path,data=raw,headers=headers or {'Content-Type':'application/json'}),timeout=30) as r:return json.load(r)
    except HTTPError as e:raise RuntimeError(e.read().decode())
def turn(source,action,previous=None,answer=''):
    job=req('/api/reader/ask',{'sid':source['id'],'action':action,'previousTask':previous,'question':answer})
    print(action+': '+job['id'],flush=True);deadline=time.time()+590
    while time.time()<deadline:
        job=req('/api/tasks/'+job['id'])
        if job['status'] not in ['running','queued']:break
        time.sleep(3)
    assert job['status']=='completed',job.get('result')
    r=job['readerResult'];assert r['coaching'];return r
if len(sys.argv)>1:
    s=req('/api/reader/state/'+sys.argv[1]);results=s['history']
else:
    f=req('/api/upload','收入120万元，成本80万元，差额40万元并不等于净利润，还需考虑其他费用和税金。'.encode(),{'X-Filename':'learning-test.txt'})
    doc=req('/api/reader/import',{'fileId':f['id']})
    s=req('/api/reader/learn',{'sourceId':doc['id'],'topic':'理解收入、成本差额与净利润的区别','mode':'grill','level':'入门'});results=[]
for action,answer in [('start',''),('answer','净利润就是120万元，因为收入全部都是利润。'),('hint',''),('recap','')][len(results):]:
    r=turn(s,action,results[-1]['taskId'] if results else None,answer);results.append(r)
    assert r['citations']
    if action=='answer':assert r['coaching']['assessment'] in ['部分理解','需要巩固']
    if action=='hint':assert r['coaching']['nextQuestion']==results[-2]['coaching']['nextQuestion']
    print('Verified '+action,flush=True)
topic=req('/api/reader/learn',{'topic':'理解算术平均数','mode':'teach','level':'入门'})
t=turn(topic,'start');assert t['coaching']['lesson'] and not t['citations']
state=req('/api/reader/state/'+s['id']);assert len(state['history'])==4
(ROOT/'data/learning-acceptance.json').write_text(json.dumps({'materialSession':s['id'],'topicSession':topic['id'],'turns':results,'topicTurn':t},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS material grill, wrong-answer feedback, hint, recap, topic teaching, persistence',flush=True)
