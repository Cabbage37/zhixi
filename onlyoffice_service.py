"""Local ONLYOFFICE session/configuration and authenticated storage bridge."""
import json,os,secrets,hashlib,hmac,base64,time,threading,zipfile,io
from pathlib import Path
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'config/onlyoffice.local.json'
SESSIONS=ROOT/'data/editor';SESSIONS.mkdir(parents=True,exist_ok=True)
LOCK=threading.RLock()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,d):
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8');tmp.replace(p)
def settings():
    if not CONFIG.exists():raise ValueError('ONLYOFFICE尚未配置，请运行 scripts/start-onlyoffice.ps1')
    return read(CONFIG)
def b64(b):return base64.urlsafe_b64encode(b).decode().rstrip('=')
def sign(payload):
    raw=b64(b'{"alg":"HS256","typ":"JWT"}')+'.'+b64(json.dumps(payload,separators=(',',':')).encode())
    return raw+'.'+b64(hmac.new(settings()['secret'].encode(),raw.encode(),hashlib.sha256).digest())
def verify(token):
    try:
        a,b,c=token.split('.');raw=a+'.'+b
        if not hmac.compare_digest(c,b64(hmac.new(settings()['secret'].encode(),raw.encode(),hashlib.sha256).digest())):raise ValueError()
        return json.loads(base64.urlsafe_b64decode(b+'='*(-len(b)%4)))
    except Exception:raise ValueError('无效回调签名') from None
def session(sid):
    if not isinstance(sid,str) or len(sid)!=32 or not sid.isalnum():raise ValueError('无效编辑会话')
    folder=SESSIONS/sid
    if not (folder/'session.json').exists():raise ValueError('编辑会话不存在')
    return folder,read(folder/'session.json')
def health():
    try:
        config=settings()
        with urlopen(config['browserUrl']+'/healthcheck',timeout=3) as r:ok=r.read()==b'true'
        return {'available':ok,'url':config['browserUrl']}
    except Exception:return {'available':False,'message':'ONLYOFFICE Docs未就绪；现有材料体检仍可使用。'}
def open_session(task_folder):
    with LOCK:
        return _open_session(task_folder)

def _open_session(task_folder):
    config=settings()
    if not health()['available']:raise ValueError('ONLYOFFICE Docs未就绪，请先启动文档服务')
    task=read(task_folder/'task.json')
    standardized=bool(task.get('standardization'))
    if task['status']!='completed' or not (standardized or task.get('material')):raise ValueError('请先完成文档处理')
    if standardized and (task_folder/'standard-editor.json').is_file():
        folder,state=session(read(task_folder/'standard-editor.json')['sid'])
        if state.pop('finalSaved',False):
            state['key']=secrets.token_hex(16)
            save(folder/'session.json',state)
        return editor_payload(state)
    sources=list((task_folder/('outputs' if standardized else 'inputs')).glob('*.docx'))
    if standardized and (task_folder/'outputs/规范文稿.docx').is_file():
        sources=[task_folder/'outputs/规范文稿.docx']
    if len(sources)!=1:raise ValueError('首期在线编辑仅支持DOCX')
    from review_document import enrich_report
    report={'issues':[]} if standardized else enrich_report(read(task_folder/'outputs/材料体检.json'),sources[0])
    sid=secrets.token_hex(16);cap=secrets.token_urlsafe(32)
    folder=SESSIONS/sid;folder.mkdir();data=sources[0].read_bytes()
    (folder/'original.docx').write_bytes(data);(folder/'current.docx').write_bytes(data)
    glossary=(task.get('material') or {}).get('glossary','');terms=[line.split('=')[0].strip() for line in glossary.splitlines() if line.strip()]
    state={'sid':sid,'cap':cap,'key':sid,'task':task['id'],'name':sources[0].name,'sourceHash':hashlib.sha256(data).hexdigest(),'saved':0,'lockNumbers':not standardized,'terms':terms,'states':{},'report':report,'standardized':standardized}
    save(folder/'session.json',state)
    if standardized:
        save(task_folder/'standard-editor.json',{'sid':sid})
    return editor_payload(state)
def editor_payload(state):
    config=settings();sid=state['sid'];cap=state['cap'];bridge=config['storageUrl']
    doc={'documentType':'word','type':'desktop','width':'100%','height':'100%','document':{'fileType':'docx','key':state['key'],'title':state['name'],'url':f'{bridge}/file/{sid}/{cap}/current.docx','permissions':{'edit':True,'download':True,'review':True}},'editorConfig':{'mode':'edit','lang':'zh-CN','callbackUrl':f'{bridge}/callback/{sid}/{cap}','user':{'id':'zhixi-local','name':'知析用户'},'customization':{'forcesave':True,'autosave':True},'plugins':{'autostart':['asc.{1EF36940-4531-4926-AAD9-9BC338AB7501}'],'pluginsData':['http://127.0.0.1:8765/office-plugin/config.json']}}}
    if state.get('standardized'):
        doc['editorConfig'].pop('plugins',None)
    doc['token']=sign(doc)
    return {'sid':sid,'config':doc,'server':config['browserUrl'],'report':state['report'],'lockNumbers':state['lockNumbers'],'terms':state['terms']}
def public_state(sid):
    _,s=session(sid);return {k:s.get(k) for k in ['saved','saveError','lockNumbers','terms','states']}
def original_config(sid):
    _,s=session(sid);cfg=settings()
    doc={'documentType':'word','type':'desktop','width':'100%','height':'100%','document':{'fileType':'docx','key':sid+'-original','title':'原稿（只读）','url':f"{cfg['storageUrl']}/file/{sid}/{s['cap']}/original.docx",'permissions':{'edit':False}},'editorConfig':{'mode':'view','lang':'zh-CN'}}
    doc['token']=sign(doc);return doc
def protect(sid,body):
    with LOCK:
        p,s=session(sid)
        if body.get('confirmed') is not True:raise ValueError('保护设置调整需要明确确认')
        terms=body.get('terms',s['terms'])
        if not isinstance(terms,list) or len(terms)>300 or any(not isinstance(x,str) or len(x)>200 for x in terms):raise ValueError('术语格式无效')
        s['lockNumbers']=body.get('lockNumbers',True) is not False;s['terms']=terms;save(p/'session.json',s)
    return public_state(sid)
def validate_change(sid,body):
    _,s=session(sid);issue=next((i for i in s['report']['issues'] if i['id']==body.get('issueId')),None)
    if not issue or not issue.get('anchor') or not isinstance(issue.get('replacement'),str):raise ValueError('此问题没有可安全应用的替换建议，请手动编辑')
    if issue.get('substantive',True) and body.get('confirmed') is not True:raise ValueError('实质性修改必须逐项确认')
    from review_document import check_locks
    check_locks(issue['anchor']['quote'],issue['replacement'],s['terms'],s['lockNumbers'])
    return {'anchor':issue['anchor'],'replacement':issue['replacement']}
def force_save(sid):
    _,s=session(sid);config=settings();payload={'c':'forcesave','key':s['key']};payload['token']=sign(payload)
    with urlopen(Request(config['browserUrl']+'/coauthoring/CommandService.ashx',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=20) as r:result=json.load(r)
    if result.get('error') not in [0,4]:raise ValueError('编辑器暂未保存，请等待或使用编辑器保存按钮')
    return {'requested':True,'unchanged':result.get('error')==4,'previousSaved':s['saved']}
def accept_callback(sid,cap,body):
    with LOCK:
        folder,state=session(sid)
        if not hmac.compare_digest(cap,state['cap']):raise ValueError('无效文件凭证')
        signed=verify(body.get('token',''));payload=signed.get('payload',signed)
        if payload.get('key')!=state['key']:raise ValueError('回调文档不匹配')
        if payload.get('status') not in [2,6]:return {'error':0}
        url=payload.get('url','');expected=urlparse(settings()['browserUrl']);target=urlparse(url)
        if (target.scheme,target.netloc)!=(expected.scheme,expected.netloc):raise ValueError('拒绝非文档服务下载地址')
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):raise ValueError('拒绝重定向')
        with build_opener(NoRedirect).open(settings().get('callbackFetchUrl',settings()['browserUrl'])+target.path+('?' + target.query if target.query else ''),timeout=30) as r:data=r.read(30*1024*1024+1)
        if len(data)>30*1024*1024:raise ValueError('修订文件过大')
        from review_document import paragraphs,check_locks,W
        try:
            _,original=paragraphs((folder/'original.docx').read_bytes());_,revised=paragraphs(data)
            check_locks('\n'.join(''.join(t.text or '' for t in p.iter(W+'t')) for p in original),'\n'.join(''.join(t.text or '' for t in p.iter(W+'t')) for p in revised),state['terms'],state['lockNumbers'])
        except Exception as e:
            state['saveError']=str(e);save(folder/'session.json',state);return {'error':1}
        version=state['saved']+1;(folder/f'version-{version}.docx').write_bytes(data)
        (folder/'current.docx').write_bytes(data);state.update(saved=version,saveError=None)
        if payload['status']==2 and state.get('standardized'):
            state['finalSaved']=True
        save(folder/'session.json',state)
        return {'error':0}

if __name__=='__main__':
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    class Bridge(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,data,code=200,mime='application/json'):
            raw=data if isinstance(data,bytes) else json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            try:
                _,kind,sid,cap,name=self.path.split('/');p,s=session(sid)
                if kind!='file' or not hmac.compare_digest(cap,s['cap']) or name not in ['current.docx','original.docx']:raise ValueError()
                self.reply((p/name).read_bytes(),mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            except Exception:self.reply({'error':1},403)
        def do_POST(self):
            try:
                _,kind,sid,cap=self.path.split('/');length=int(self.headers.get('Content-Length',0))
                if kind!='callback' or not 0<length<1000000:raise ValueError()
                self.reply(accept_callback(sid,cap,json.loads(self.rfile.read(length))))
            except Exception:self.reply({'error':1},400)
    ThreadingHTTPServer(('127.0.0.1',8766),Bridge).serve_forever()
