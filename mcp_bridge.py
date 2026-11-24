"""Local stdio MCP adapter. Commands come only from project configuration."""
import os, json, subprocess, threading, queue, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class MCP:
 def __init__(self, config):
  self.proc=subprocess.Popen([config['command'],*config.get('args',[])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',cwd=ROOT,env={**os.environ,**config.get("env",{})})
  self.messages=queue.Queue(); self.counter=0
  def reader():
   for line in self.proc.stdout:
    try: self.messages.put(json.loads(line))
    except ValueError: pass
  threading.Thread(target=reader,daemon=True).start()
  try:
   self.call('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'zhihui','version':'0.1.0'}})
   self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
  except Exception:
   self.close()
   raise
 def send(self,data):
  self.proc.stdin.write(json.dumps(data)+'\n');self.proc.stdin.flush()
 def call(self,method,params):
  self.counter+=1; ident=self.counter
  self.send({'jsonrpc':'2.0','id':ident,'method':method,'params':params})
  import time
  deadline=time.monotonic()+15
  while True:
   item=self.messages.get(timeout=max(.01,deadline-time.monotonic()))
   if item.get('id')==ident:
    if 'error' in item: raise RuntimeError(str(item['error']))
    return item['result']
 def close(self):
  self.proc.terminate()
  try:self.proc.wait(timeout=3)
  except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
def invoke(server,method,params):
 configs=json.loads((ROOT/'config/mcp.json').read_text(encoding='utf-8'))['servers']
 config=next(c for c in configs if c['name']==server and c.get('enabled',False))
 if method not in ['tools/list','tools/call']:raise ValueError('Unsupported method')
 client=MCP(config)
 try:return client.call(method,params)
 finally:client.close()
if __name__=='__main__':
 print(json.dumps(invoke(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]) if len(sys.argv)>3 else {}),ensure_ascii=False))
