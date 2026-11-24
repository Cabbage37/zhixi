import sys,tempfile,threading,json,urllib.request,urllib.error,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
import server
server.execute=lambda job:None
os.environ['DEEPSEEK_API_KEY']='test-no-model-called'
with tempfile.TemporaryDirectory() as tmp:
    server.DATA=Path(tmp)
    for name in ['uploads','tasks']:(server.DATA/name).mkdir()
    book=Workbook();book.active.append(['年份','收入']);book.active.append([2025,10]);book.save(server.DATA/'test.xlsx')
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    def post(route,body,extra=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+route,data=body if isinstance(body,bytes) else json.dumps(body).encode(),headers={'Host':'127.0.0.1:8765','Content-Type':'application/json',**(extra or {})},method='POST')
        return json.load(urllib.request.urlopen(req,timeout=10))
    try:
        f=post('/api/upload',(server.DATA/'test.xlsx').read_bytes(),{'X-Filename':'sample.xlsx'})
        info=post('/api/excel/inspect',{'fileId':f['id']});assert info['sheets'][0]['range']=='A1:B2'
        payload={'module':'office','prompt':'Excel','files':[f['id']],'excel':{'fileId':f['id'],'sheets':[{'sheet':'Sheet','range':'A1:B2'}]}}
        job=post('/api/tasks',payload)
        assert job['excel']['sheets'][0]['range']=='A1:B2'
        folder=server.DATA/'tasks'/job['id']/'inputs'
        assert (folder/'chart-plan.json').exists() and len(list(folder.glob('*.xlsx')))==1
        payload['excel']['sheets'][0]['range']='A1:XFD1048576'
        try:post('/api/tasks',payload);raise AssertionError('invalid range accepted')
        except urllib.error.HTTPError as e:assert e.code==400
        print('PASS: upload, Sheet inspection, task parameters, source copy, invalid bounds rejected')
    finally:http.shutdown();http.server_close()
