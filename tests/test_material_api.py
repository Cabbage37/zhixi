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
    def post(route,data,extra=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+route,data=data if isinstance(data,bytes) else json.dumps(data).encode(),headers={'Host':'127.0.0.1:8765','Content-Type':'application/json',**(extra or {})},method='POST')
        return json.load(urllib.request.urlopen(req,timeout=15))
    try:
        f=post('/api/upload','正文\n收入100万元。'.encode(),{'X-Filename':'sample.txt'})
        preview=post('/api/material/inspect',{'fileId':f['id']});assert len(preview['blocks'])==2
        payload={'module':'office','prompt':'体检','files':[f['id']],'material':{'checks':['错别字']}}
        job=post('/api/tasks',payload);folder=server.DATA/'tasks'/job['id']
        assert (folder/'review/source.json').is_file() and (folder/'review/consistency.json').is_file()
        payload['material']['checks']=[]
        try:post('/api/tasks',payload);raise AssertionError('empty checks accepted')
        except urllib.error.HTTPError as e:assert e.code==400
        job['status']='completed';server.save(folder/'task.json',job)
        server.save(folder/'outputs/材料体检.json',{'issues':[{'id':'I001'}]})
        states=post('/api/material/review',{'taskId':job['id'],'issueId':'I001','state':'忽略'});assert states['I001']=='忽略'
        try:post('/api/material/review',{'taskId':job['id'],'issueId':'invented','state':'已确认'});raise AssertionError('invalid issue accepted')
        except urllib.error.HTTPError as e:assert e.code==400
        print('PASS: material upload, inspect, structured task, public checker, review state persistence, invalid options rejection')
    finally:http.shutdown();http.server_close()
