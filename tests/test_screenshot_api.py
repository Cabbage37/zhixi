import sys,tempfile,threading,json,urllib.request,urllib.error,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import pymupdf
server.execute=lambda job:None
os.environ.update(DEEPSEEK_API_KEY='fixture-only',TABLE_RECOGNITION_MODE='vision',TABLE_VISION_API_KEY='fixture-only',TABLE_VISION_BASE_URL='https://example.invalid/v1',TABLE_VISION_MODEL='fixture')
with tempfile.TemporaryDirectory() as tmp:
    server.DATA=Path(tmp)
    for n in ['uploads','tasks']:(server.DATA/n).mkdir()
    d=pymupdf.open();page=d.new_page(width=100,height=80);page.get_pixmap().save(server.DATA/'sample.png');d.close()
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
    def post(route,data,extra=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+route,data=data if isinstance(data,bytes) else json.dumps(data).encode(),headers={'Host':'127.0.0.1:8765','Content-Type':'application/json',**(extra or {})},method='POST')
        return json.load(urllib.request.urlopen(req,timeout=15))
    try:
        f=post('/api/upload',(server.DATA/'sample.png').read_bytes(),{'X-Filename':'sample.png'})
        assert post('/api/screenshot/inspect',{'fileId':f['id']})['width']==100
        job=post('/api/tasks',{'module':'office','prompt':'截图转表格','files':[f['id']],'screenshot':{}});folder=server.DATA/'tasks'/job['id']
        (folder/'recognition').mkdir();server.save(folder/'recognition/result.json',{'tables':[]});job['status']='completed';server.save(folder/'task.json',job)
        tables=[{'name':'表1','rows':[[{'text':'001','uncertain':True,'reviewed':False}]],'merges':[]}]
        try:post('/api/screenshot/export',{'taskId':job['id'],'tables':tables});raise AssertionError('unreviewed accepted')
        except urllib.error.HTTPError as e:assert e.code==400
        tables[0]['rows'][0][0]['reviewed']=True
        out=post('/api/screenshot/export',{'taskId':job['id'],'tables':tables});assert (folder/'outputs'/out['name']).exists()
        os.environ['TABLE_VISION_API_KEY']=''
        try:post('/api/tasks',{'module':'office','prompt':'截图','files':[f['id']],'screenshot':{}});raise AssertionError('missing key accepted')
        except urllib.error.HTTPError as e:assert e.code==409
        print('PASS: image upload/inspect, task wiring, reviewed export, missing config rejected; no real model called')
    finally:http.shutdown();http.server_close()
