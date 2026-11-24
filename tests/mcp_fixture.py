import sys,json
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 m=r['method']
 result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}} if m=='initialize' else {'tools':[{'name':'echo','inputSchema':{'type':'object'}}]} if m=='tools/list' else {'content':[{'type':'text','text':r['params']['arguments']['text']}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
