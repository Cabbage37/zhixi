import sys, tempfile, threading, json, urllib.request, urllib.error, os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
server.execute=lambda job:None
os.environ['DEEPSEEK_API_KEY']='test-no-model-called'
with tempfile.TemporaryDirectory() as tmp:
 server.DATA=Path(tmp)
 for d in ['uploads','tasks']: (server.DATA/d).mkdir()
 fid='testfile'; (server.DATA/'uploads'/fid).mkdir(); (server.DATA/'uploads'/fid/'original.txt').write_text('Original content')
 http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
 threading.Thread(target=http.serve_forever,daemon=True).start()
 def submit(options):
  req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+'/api/tasks',data=json.dumps({'module':'office','prompt':'test','files':[fid],'standardization':options}).encode(),headers={'Host':'127.0.0.1:8765','Content-Type':'application/json'},method='POST')
  return json.load(urllib.request.urlopen(req,timeout=10))
 try:
  for fmt in ['docx','pdf']:
   job=submit({'templateId':'template-1','format':fmt})
   folder=server.DATA/'tasks'/job['id']/'inputs/reference-template'
   f=next(folder.iterdir())
   assert f.suffix=='.docx'
   assert f.read_bytes()==(server.ROOT/'skills/document-standardize/assets/docx'/f.name).read_bytes()
   assert job['standardization']['format']==fmt
  for options in [{'templateId':'../../wrong','format':'docx'},{'templateId':'template-1','format':'html'}]:
   try:submit(options);raise AssertionError('Invalid accepted')
   except urllib.error.HTTPError as e: assert e.code==400
  catalog=json.loads((server.ROOT/'web/templates/catalog.json').read_text(encoding='utf-8'))
  assert len(catalog)==9
  for item in catalog:assert (server.ROOT/'web'/item['preview'].lstrip('/')).read_bytes().startswith(b'\x89PNG')
  print('PASS: 9 previews, template byte-preserving copy, DOCX/PDF, invalid format/template rejection')
 finally:http.shutdown();http.server_close()
