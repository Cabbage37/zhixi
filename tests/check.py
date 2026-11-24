import sys,json,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp_bridge import MCP
m=MCP({'command':sys.executable,'args':['tests/mcp_fixture.py']})
try:
 assert m.call('tools/list',{})['tools'][0]['name']=='echo'
 assert m.call('tools/call',{'name':'echo','arguments':{'text':'ok'}})['content'][0]['text']=='ok'
finally:m.close()
base='http://127.0.0.1:8765'
assert '办公提效' not in urllib.request.urlopen(base).read().decode() # dynamically rendered
s=json.load(urllib.request.urlopen(base+'/api/status'));assert s['sdk']
r=urllib.request.Request(base+'/api/upload',data=b'smoke test',headers={'X-Filename':'smoke.txt'},method='POST')
u=json.load(urllib.request.urlopen(r));assert u['size']==10
r=urllib.request.Request(base+'/api/tasks',data=json.dumps({'module':'office','prompt':'test','files':[u['id']]}).encode(),headers={'Content-Type':'application/json'},method='POST')
if not s['modelConfigured']:
 try:urllib.request.urlopen(r);raise AssertionError('must reject missing credentials')
 except urllib.error.HTTPError as e:assert e.code==409
r=urllib.request.Request(base+'/api/upload',data=b'x',headers={'Origin':'https://untrusted.example'},method='POST')
try:urllib.request.urlopen(r);raise AssertionError('must reject cross-origin')
except urllib.error.HTTPError as e:assert e.code==403
print('PASS: MCP handshake/list/call; HTTP status/upload; missing-key guard; origin guard')
