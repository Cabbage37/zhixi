"""Isolated HTTP validation; no model or external API requests."""
import sys,tempfile,threading,json,urllib.request,urllib.error,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
server.execute=lambda job:None
os.environ['DEEPSEEK_API_KEY']='fixture-only'
with tempfile.TemporaryDirectory() as tmp:
 server.DATA=Path(tmp)
 for name in ['uploads','tasks']:(server.DATA/name).mkdir()
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
 threading.Thread(target=http.serve_forever,daemon=True).start()
 def request(route,data=None,extra=None):
  req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+route,data=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None,headers={'Host':'127.0.0.1:8765','Content-Type':'application/json',**(extra or {})})
  return json.load(urllib.request.urlopen(req,timeout=10))
 try:
  f=request('/api/upload','预算120万元，尚未批准。'.encode(),{'X-Filename':'source.txt'})
  payload={'module':'office','prompt':'一稿多用','files':[f['id']],'repurpose':{'kinds':['邮件正文'],'limit':300}}
  job=request('/api/tasks',payload);folder=server.DATA/'tasks'/job['id']
  assert server.read(folder/'repurpose/options.json')['kinds']==['邮件正文']
  assert server.read(folder/'repurpose/source.json')['blocks'][0]['text']=='预算120万元，尚未批准。'
  for change in [{'repurpose':{'kinds':[]}},{'files':[]},{'material':{}},{'files':['../escape']}]:
   try:request('/api/tasks',{**payload,**change});raise AssertionError('invalid task accepted')
   except urllib.error.HTTPError as e:assert e.code==400
  server.save(folder/'repurpose/result.json',{'variants':[]})
  assert 'repurposeResult' not in request('/api/tasks/'+job['id'])
  job['status']='completed';server.save(folder/'task.json',job)
  assert 'repurposeResult' in request('/api/tasks/'+job['id'])
  print('PASS: structured task, extracted source, invalid options/files/mixed features rejection, completed-result delivery')
 finally:http.shutdown();http.server_close()
