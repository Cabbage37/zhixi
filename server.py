import hashlib, os, sys, json, uuid, threading, subprocess, importlib.util, time, shutil
from pathlib import Path
from model_settings import model_settings
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.runtime/python'))
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines() if (ROOT/'.env').exists() else []:
    if '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1); os.environ[k.strip()]=v.strip()
for line in (ROOT/'.env.vision').read_text(encoding='utf-8-sig').splitlines() if (ROOT/'.env.vision').exists() else []:
    if '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1)
        if k.strip().startswith('TABLE_') or k.strip() in ['ZHIPU_API_KEY','GLM_OCR_TIMEOUT']:os.environ[k.strip()]=v.strip()
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
for d in ['uploads','tasks']: (DATA/d).mkdir(exist_ok=True)
MODULES={'office':'办公提效','research':'研究分析','knowledge':'知识管理','extend':'AI 拓展'}

OFFICE_TYPES={'excel':'Excel 智能制图','material':'材料体检','screenshot':'截图转表格','comparison':'版本找不同','repurpose':'一稿多用','standardization':'文档标准化'}
RETRY_LOCK=threading.Lock()
SUBMIT_LOCK=threading.Lock()
ACTIVE_SUBMISSIONS={}

def uploaded_workbook(fid):
    if not isinstance(fid,str) or not fid.isalnum(): raise ValueError('无效文件')
    found=list((DATA/'uploads'/fid).glob('*.xlsx'))
    if len(found)!=1: raise ValueError('请上传 XLSX 工作簿')
    return found[0]

def uploaded_material(fid):
    from material_tools import EXTENSIONS
    if not isinstance(fid,str) or not fid.isalnum():raise ValueError('无效文件')
    found=[p for p in (DATA/'uploads'/fid).glob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS]
    if len(found)!=1:raise ValueError('请上传 DOCX、PDF、TXT 或 MD 文件')
    return found[0]

def uploaded_screenshot(fid):
    from screenshot_tools import FORMATS
    if not isinstance(fid,str) or not fid.isalnum():raise ValueError('无效文件')
    files=[f for f in (DATA/'uploads'/fid).glob('*') if f.is_file() and f.suffix.lower() in FORMATS]
    if len(files)!=1:raise ValueError('每次上传一张PNG、JPG或WEBP截图')
    return files[0]
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def save(p,obj):
    tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
    for attempt in range(12):
        try:
            tmp.replace(p)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(0.025 * (attempt + 1))
def status():
    return {'sdk':importlib.util.find_spec('deepseek_harness') is not None,'modelConfigured':bool(model_settings()[2]),'model':model_settings()[1],'runtime':'DeepSeek Harness','skills':[{'name':p.parent.name} for p in (ROOT/'skills').glob('*/SKILL.md')],'mcp':{'servers':[{'name':c['name'],'enabled':c.get('enabled',False)} for c in read(ROOT/'config/mcp.json')['servers']]},'execution':'本地可信任务；SDK shell 非沙箱'}
def execute(job):
    p=DATA/'tasks'/job['id']/'task.json'
    try:
        job['status']='running'; save(p,job)
        result=subprocess.run([sys.executable,str(ROOT/'worker.py'),str(p)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=3600 if job.get('comparison') else 1800 if job.get('monitorId') else 600)
        job['status']='completed' if result.returncode==0 else 'failed'
        job['result']=result.stdout[-24000:] if result.returncode==0 else 'Agent 执行失败，请检查运行配置。'
        events=p.parent/'agent-events.json'
        if result.returncode!=0 and events.exists():
            for event in read(events).get('events',[]):
                if event.get('type')=='turn/end':
                    error=event.get('data',{}).get('reason',{}).get('error',{})
                    if error.get('status')==401 or error.get('code')=='AUTH': job['result']='模型接口认证失败（401）：请检查项目 .env 中的 API 密钥是否属于当前公司网关，修改后重启服务。'
                    if job.get('reader') and error.get('code')=='STREAM_CLOSED':job['result']='模型网关提前关闭了响应，材料已保留，请重新发送问题。'
        if job.get('material') and result.returncode and (p.parent/'review/error.json').is_file():
            job['result']=read(p.parent/'review/error.json')['error']
        if job.get('comparison') and result.returncode!=0 and (p.parent/'comparison/error.json').exists():
            job['result']=read(p.parent/'comparison/error.json')['error']
        if job.get('screenshot') and result.returncode!=0 and (p.parent/'recognition/error.json').exists():
            job['result']=read(p.parent/'recognition/error.json')['error']
        if job.get('repurpose') and result.returncode!=0 and (p.parent/'repurpose/error.json').exists():
            job['result']=read(p.parent/'repurpose/error.json')['error']
        if job.get('reader') and result.returncode!=0 and (p.parent/'reader/error.json').exists():
            job['result']=read(p.parent/'reader/error.json')['error']
        if job.get('workshop') and result.returncode!=0 and (p.parent/'workshop-error.json').exists():
            job['result']=read(p.parent/'workshop-error.json')['error']
        if job.get('application') and result.returncode!=0 and (p.parent/'application-error.json').exists():
            job['result']=read(p.parent/'application-error.json')['error']
        if job.get('quickResearch') and result.returncode and (p.parent/'research-error.json').exists():
            job['result']=read(p.parent/'research-error.json')['error']
        if job.get('standardization') and result.returncode and (p.parent/'standardization-error.json').is_file():
            job['result']=read(p.parent/'standardization-error.json')['error']
        if job.get('research') and result.returncode!=0 and (p.parent/'research-error.json').exists():
            job['result']=read(p.parent/'research-error.json')['error']
        if job.get('sentiment') and result.returncode!=0 and (p.parent/'sentiment-error.json').exists():
            job['result']=read(p.parent/'sentiment-error.json')['error']
        # Keep diagnostics local, never return credentials to browser.
        (p.parent/'runtime.log').write_text(result.stderr,encoding='utf-8')
    except subprocess.TimeoutExpired:
        message='本次处理超时，原始材料已保留。请重新执行，或缩小材料范围。'
        if job.get('comparison'):message='版本对比超时；重新提交相同文件可复用已识别的扫描页。'
        job.update(status='failed',result=message)
    except Exception: job.update(status='failed',result='运行失败，请查看本地服务日志。')
    if job.get('monitorId'):
        import public_opinion as opinion
        report_path=p.parent/'monitor-result.json'
        report=read(report_path) if report_path.is_file() else {}
        if job['status']=='failed' and report.get('errors'):
            job['result']=report['errors'][-1]
        opinion.complete(job['monitorId'],job['id'],report,job['result'],job['status']=='completed')
    save(p,job)

def run_monitor(monitor_id):
    import public_opinion as opinion
    with opinion.LOCK:
        state=opinion.get(monitor_id)
        if not state['config']['enabled']:
            raise ValueError('请先启用监测任务')
        if not model_settings()[2]:
            raise ValueError('请先配置工作台模型接口')
        if any(run['status']=='running' for run in state['runs']):
            raise ValueError('该任务正在检查')
        tid=uuid.uuid4().hex
        folder=DATA/'tasks'/tid
        (folder/'inputs').mkdir(parents=True)
        (folder/'outputs').mkdir()
        save(folder/'monitor-input.json',{'id':monitor_id,'config':state['config'],'items':state['items']})
        job={'id':tid,'module':MODULES['research'],'monitorId':monitor_id,'prompt':'舆情监测','status':'queued','result':''}
        save(folder/'task.json',job)
        state['runs'].append({'id':tid,'status':'running','startedAt':opinion.now(),'endedAt':None,
                              'discovered':0,'duplicates':0,'included':0,'errors':[]})
        opinion.save(opinion.path(monitor_id),state)
        threading.Thread(target=execute,args=(job,),daemon=True).start()
        return job
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,obj,code=200):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def safe(self):
        origin=self.headers.get('Origin')
        return self.headers.get('Host') in ['127.0.0.1:8765','localhost:8765'] and (not origin or origin in ['http://127.0.0.1:8765','http://localhost:8765'])
    def do_GET(self):
        path=urlparse(self.path).path
        plugin_asset=path.startswith('/office-plugin/') and self.headers.get('Origin') in ['http://localhost:8080','http://127.0.0.1:8080'] and self.headers.get('Host') in ['127.0.0.1:8765','localhost:8765']
        if not self.safe() and not plugin_asset:return self.respond({'error':'拒绝外部来源'},403)
        if path=='/api/research/catalog':
            from research_tools import catalog
            return self.respond(catalog())
        if path=='/api/applications' or path.startswith('/api/applications/'):
            import application_tools as apps
            try:
                if path=='/api/applications':return self.respond(apps.listing())
                parts=path.split('/')
                app=apps.get(parts[3])
                if len(parts)==5 and parts[4]=='runs':
                    entries=[]
                    for option_path in (DATA/'tasks').glob('*/application-options.json'):
                        options=read(option_path)
                        if options.get('application',{}).get('id')==app['id']:
                            task=read(option_path.parent/'task.json')
                            result_path=option_path.parent/'application-result.json'
                            entries.append({'id':task['id'],'action':options['action'],'status':task['status'],
                                            'version':options['application']['version'],
                                            'result':read(result_path) if result_path.is_file() else task.get('result','')})
                    return self.respond(entries[-30:])
                if len(parts)==5 and parts[4]=='share':
                    payload=apps.package(app['id'])
                    self.send_response(200);self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Disposition','attachment; filename="application.zip"')
                    self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return
                return self.respond(app)
            except ValueError as error:return self.respond({'error':str(error)},400)
        if path=='/api/opinion' or path.startswith('/api/opinion/'):
            import public_opinion as opinion
            try:
                if path=='/api/opinion':return self.respond(opinion.listing())
                state=opinion.get(path.rsplit('/',1)[1])
                for item in state['items']:
                    item['publishedDay']=opinion.published_day(item['publishedAt'])
                return self.respond(state)
            except ValueError as error:
                return self.respond({'error':str(error)},400)
        if path=='/api/workshop-library' or path.startswith('/api/workshop-library/'):
            from workshop_chat import BASE, library_item
            try:
                if path.endswith('workshop-library'):
                    return self.respond([library_item(f.parent.name) for f in BASE.glob('*/saved')])
                return self.respond(library_item(path.rsplit('/',1)[1]))
            except ValueError as error:return self.respond({'error':str(error)},404)
        if path.startswith('/api/workshop-preview/'):
            from workshop_local import preview
            try:
                url=preview(path.rsplit('/',1)[1])
            except (OSError,KeyError,ValueError):
                return self.respond({'error':'本地预览暂不可打开，请返回工坊重试。'},404)
            self.send_response(302)
            self.send_header('Location',url)
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            return
        if path.startswith('/api/workshop/'):
            import skill_workshop as workshop
            parts=path.split('/')
            try:
                if parts[3:]==['versions']:return self.respond(workshop.versions())
                if len(parts)==5 and parts[3]=='version':return self.respond(workshop.public(workshop.get(parts[4])))
                if len(parts)==5 and parts[3]=='zip':
                    item=workshop.get(parts[4]);data=workshop.package(item)
                    self.send_response(200);self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Disposition',f'attachment; filename="{item["name"]}.zip"')
                    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
                return self.respond({'error':'无效技能请求'},404)
            except ValueError as e:return self.respond({'error':str(e)},400)
        if path == '/api/reader/excerpts':
            from reader_tools import excerpts
            return self.respond(excerpts())
        if path.startswith('/api/reader/state/'):
            from reader_tools import state
            try:return self.respond(state(path.split('/')[-1]))
            except ValueError as e:return self.respond({'error':str(e)},400)
        if path.startswith('/reader-preview/'):
            from reader_tools import session
            try:
                folder,source=session(path.split('/')[-1])
                p=folder/('source.pdf' if source['kind']=='.pdf' else 'preview.png')
                if not p.is_file():raise ValueError('该材料使用文本阅读视图')
                b=p.read_bytes();self.send_response(200);self.send_header('Content-Type','application/pdf' if p.suffix=='.pdf' else 'image/png');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
            except ValueError as e:return self.respond({'error':str(e)},400)
        if path=='/api/editor/health':
            from onlyoffice_service import health
            return self.respond(health())
        if path.startswith('/api/editor/state/'):
            from onlyoffice_service import public_state
            try:return self.respond(public_state(path.split('/')[-1]))
            except ValueError as e:return self.respond({'error':str(e)},400)
        if path.startswith('/editor-download/'):
            from onlyoffice_service import session
            try:
                parts=path.split('/');folder,state=session(parts[2]);name=parts[3]
                if name not in ['current.docx','original.docx'] or (name=='current.docx' and state.get('saveError')):raise ValueError('修订稿尚未通过保护校验')
                data=(folder/name).read_bytes();self.send_response(200);self.send_header('Content-Type','application/vnd.openxmlformats-officedocument.wordprocessingml.document');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            except (ValueError,IndexError) as e:return self.respond({'error':str(e)},400)
        if path=='/api/status': return self.respond(status())
        if path=='/api/screenshot/config':
            from screenshot_tools import config
            return self.respond(config())
        if path=='/api/my-work':
            entries=[]
            def add(kind, ident, feature, title, state, stamp):
                entries.append(dict(kind=kind,id=ident,feature=feature,title=title,state=state,updated=stamp))
            for record in (DATA/'tasks').glob('*/task.json'):
                job=read(record); folder=record.parent
                feature=next((name for key,name in OFFICE_TYPES.items() if job.get(key)),None)
                feature=feature or job.get('institutionResearch')
                if not feature and not job.get('quickResearch'):continue
                title=job['prompt'] if not feature or job.get('institutionResearch') else '、'.join(f.name.partition('_')[2] or f.name for f in (folder/'inputs').glob('*') if f.is_file() and f.name!='chart-plan.json')
                state={'completed':'已完成','running':'处理中','queued':'处理中','interrupted':'已中断','failed':'失败'}.get(job['status'],job['status'])
                report=folder/'outputs/材料体检.json'
                if state=='已完成' and job.get('material') and report.is_file():
                    decisions=read(folder/'review-states.json') if (folder/'review-states.json').exists() else {}
                    if any(decisions.get(i['id'],'待复核')=='待复核' for i in read(report)['issues']):state='待复核'
                add('office' if feature else 'research',job['id'],feature or '金融事件快评',title or feature,state,record.stat().st_mtime)
            for record in (DATA/'readers').glob('*/source.json'):
                src=read(record)
                if not src.get('learning'):add('knowledge',record.parent.name,'阅读助手',src['name'],'可继续阅读',record.stat().st_mtime)
            from application_tools import listing
            from datetime import datetime
            for app in listing():
                add('extend',app['id'],'我的工具',app['name'],'可使用',datetime.fromisoformat(app['updated_at']).timestamp())
            return self.respond(sorted(entries,key=lambda row:row['updated'],reverse=True))
        if path=='/api/work-history':
            entries=[]
            for record in (DATA/'tasks').glob('*/task.json'):
                job=read(record)
                feature=next((name for key,name in OFFICE_TYPES.items() if job.get(key)),None)
                if feature:
                    files=[f.name.partition('_')[2] or f.name for f in (record.parent/'inputs').iterdir() if f.is_file() and f.name!='chart-plan.json']
                    entries.append({'id':job['id'],'name':feature,'files':files,'status':job['status'],'updated':record.stat().st_mtime})
            return self.respond(sorted(entries,key=lambda row:row['updated'],reverse=True))
        if path=='/api/tasks':
            jobs=[read(p) for p in (DATA/'tasks').glob('*/task.json')]; return self.respond(jobs[::-1])
        if path.startswith('/api/tasks/'):
            tid=path.split('/')[-1]
            if not tid.isalnum(): return self.respond({'error':'无效任务'},400)
            p=DATA/'tasks'/tid/'task.json'
            if not p.exists(): return self.respond({'error':'任务不存在'},404)
            job=read(p)
            partial = '已核验证据（快评生成前）.md' if job.get('quickResearch') else None
            job['artifacts'] = [f.name for f in (p.parent/'outputs').glob('*')
                                if f.is_file() and not f.is_symlink() and
                                (job['status']=='completed' or f.name==partial)]
            if (job.get('standardization') or {}).get('source') or (p.parent/'office-export.json').exists():
                expected='规范文稿.'+job['standardization']['format']
                job['artifacts']=[name for name in job['artifacts'] if name==expected]
            if job.get('material') and job['status']=='completed' and (p.parent/'outputs/材料体检.json').is_file():
                job['materialReport']=read(p.parent/'outputs/材料体检.json')
                job['reviewStates']=read(p.parent/'review-states.json') if (p.parent/'review-states.json').exists() else {}
            if job.get('quickResearch') and job['status']=='running' and (p.parent/'research-progress.json').exists():job['result']=read(p.parent/'research-progress.json')['message']
            if job.get('screenshot') and job['status']=='completed' and (p.parent/'recognition/result.json').is_file():job['tableResult']=read(p.parent/'recognition/result.json')
            if job.get('comparison') and job['status']=='running' and (p.parent/'comparison/progress.json').exists():job['result']=read(p.parent/'comparison/progress.json')['message']
            if job.get('comparison') and (p.parent/'comparison/result.json').is_file():job['comparisonResult']=read(p.parent/'comparison/result.json')
            if job.get('repurpose') and job['status']=='completed' and (p.parent/'repurpose/result.json').is_file():job['repurposeResult']=read(p.parent/'repurpose/result.json')
            if job.get('reader') and job['status']=='completed' and (p.parent/'reader/result.json').is_file():job['readerResult']=read(p.parent/'reader/result.json')
            if job.get('workshop') and job['status']=='completed':job['workshopResult']=read(p.parent/'workshop-result.json')
            if job.get('application') and job['status']=='completed':
                job['applicationResult']=read(p.parent/'application-result.json')
            if job.get('research') and (p.parent/'research-result.json').exists():
                job['researchResult']=read(p.parent/'research-result.json')
            if job.get('sentiment') and job['status']=='completed':
                job['sentimentResult']=read(p.parent/'sentiment-result.json')
            return self.respond(job)
        if path.startswith('/comparison-preview/'):
            parts=path.split('/')
            if len(parts)!=4 or not parts[2].isalnum():return self.respond({'error':'无效路径'},400)
            base=(DATA/'tasks'/parts[2]/'comparison').resolve();p=(base/unquote(parts[3])).resolve()
            if p.parent!=base or p.suffix!='.png' or not p.is_file():return self.respond({'error':'不存在'},404)
        elif path.startswith('/screenshot-original/'):
            tid=path.split('/')[-1]
            if len(tid)!=32 or not tid.isalnum():return self.respond({'error':'无效任务'},400)
            folder=DATA/'tasks'/tid
            record=folder/'task.json'
            if not record.exists() or not read(record).get('screenshot'):return self.respond({'error':'找不到原图'},404)
            images=[f for f in (folder/'inputs').iterdir() if f.is_file() and not f.is_symlink() and f.suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
            if len(images)!=1:return self.respond({'error':'找不到原图'},404)
            p=images[0]
        elif path.startswith('/download/'):
            parts=path.split('/')
            if len(parts)!=4 or not parts[2].isalnum(): return self.respond({'error':'无效路径'},400)
            base=(DATA/'tasks'/parts[2]/'outputs').resolve(); p=(base/unquote(parts[3])).resolve()
            if p.parent!=base or not p.is_file(): return self.respond({'error':'文件不存在'},404)
        else:
            p=(ROOT/'web'/('index.html' if path=='/' else path.lstrip('/'))).resolve()
            if not p.is_relative_to(ROOT/'web') or not p.is_file(): return self.respond({'error':'不存在'},404)
        b=p.read_bytes(); self.send_response(200); self.send_header('Content-Type', {'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.png':'image/png','.json':'application/json; charset=utf-8'}.get(p.suffix,'application/octet-stream'))
        if plugin_asset:self.send_header('Access-Control-Allow-Origin',self.headers['Origin']);self.send_header('Vary','Origin')
        self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        if not self.safe(): return self.respond({'error':'拒绝外部来源'},403)
        length=int(self.headers.get('Content-Length',0))
        if length>20*1024*1024: return self.respond({'error':'文件或请求超过 20 MB'},413)
        raw=self.rfile.read(length)
        if self.path=='/api/workshop-chat':
            from workshop_chat import run
            return run(self,raw)
        if self.path=='/api/tasks':
            fingerprint=hashlib.sha256(raw).hexdigest()
            with SUBMIT_LOCK:
                for key,tid in list(ACTIVE_SUBMISSIONS.items()):
                    record=DATA/'tasks'/tid/'task.json'
                    if not record.exists() or read(record)['status'] not in ('queued','running'):
                        del ACTIVE_SUBMISSIONS[key]
                if fingerprint in ACTIVE_SUBMISSIONS:
                    return self.respond(read(DATA/'tasks'/ACTIVE_SUBMISSIONS[fingerprint]/'task.json'))
                return self.process_post(raw,fingerprint)
        return self.process_post(raw)
    def process_post(self,raw,fingerprint=None):
        try:
            if self.path=='/api/workshop-library/save':
                from workshop_chat import save_to_library
                return self.respond(save_to_library(json.loads(raw)['id']))
            if self.path=='/api/research/discover':
                from financial_quick_research import discover, notices
                from lxml.etree import LxmlError
                query=json.loads(raw).get('query')
                if not isinstance(query,str) or not 1<=len(query.strip())<=240:
                    raise ValueError('请输入 1 至 240 字的检索词')
                query=query.strip()
                results=discover([query])
                links={}
                terms=query.casefold().split()
                try:
                    for url,title in notices(query):
                        if url.startswith(('https://','http://')) and all(term in title.casefold() for term in terms):
                            links.setdefault(url,{'url':url,'title':title,'officialFeed':True})
                except (OSError,ValueError,KeyError,LxmlError):
                    pass
                # A previous completed brief can surface sources already read by the workbench.
                for task_path in (DATA/'tasks').glob('*/research-evidence.json'):
                    if not (task_path.parent/'outputs/金融事件快评.md').is_file():
                        continue
                    for source in read(task_path):
                        title=source.get('title','')
                        url=source.get('url','')
                        if url.startswith(('https://','http://')) and all(term in title.casefold() for term in terms):
                            links.setdefault(url,{'url':url,'title':title,'previouslyRead':True})
                for result in results:
                    for url,title in result['hits']:
                        links.setdefault(url,{'url':url,'title':title})
                return self.respond({'items':list(links.values()),
                                     'failed':sum('error' in result for result in results),
                                     'channels':len(results)})
            if self.path in ('/api/interactive-database/open','/api/interactive-database/status'):
                from database_bridge import open_database
                return self.respond(open_database(check_only=self.path.endswith('/status')))
            if self.path=='/api/office-retry':
                request=json.loads(raw)
                tid=request['id']
                if not isinstance(tid,str) or len(tid)!=32 or not tid.isalnum():raise ValueError('无效任务')
                old=DATA/'tasks'/tid
                with RETRY_LOCK:
                    previous=read(old/'task.json')
                    if previous.get('status') not in ('failed','interrupted') or not (previous.get('quickResearch') or any(previous.get(k) for k in OFFICE_TYPES)):
                        raise ValueError('仅可重试未完成的研究或办公任务')
                    if previous.get('retryId'):
                        retry_path=DATA/'tasks'/previous['retryId']/'task.json'
                        if retry_path.is_file():
                            retry=read(retry_path)
                            if retry['status'] in ('queued','running','completed'):
                                return self.respond(retry)
                    job=dict(previous,id=uuid.uuid4().hex,status='queued',result='',previousId=tid)
                    job.pop('retryId',None)
                    if job.get('quickResearch') and request.get('alternate') is True:
                        job['quickResearch'] = dict(job['quickResearch'], alternate=True)
                    folder=old.parent/job['id']
                    (folder/'outputs').mkdir(parents=True)
                    shutil.copytree(old/'inputs',folder/'inputs')
                    if previous.get('quickResearch') and all((old/name).is_file() for name in ('research-evidence.json','research-trace.json')):
                        for name in ('research-evidence.json','research-trace.json'):
                            shutil.copy2(old/name,folder/name)
                    for directory in ('review','repurpose'):
                        if (old/directory).is_dir():
                            (folder/directory).mkdir()
                            for name in ('source.json','options.json','consistency.json'):
                                f=old/directory/name
                                if f.is_file():shutil.copy2(f,folder/directory/name)
                    save(folder/'task.json',job)
                    previous['retryId']=job['id']
                    save(old/'task.json',previous)
                    threading.Thread(target=execute,args=(job,),daemon=True).start()
                    return self.respond(job,201)
            if self.path.startswith('/api/research/'):
                import research_tools as research
                body=json.loads(raw)
                action=self.path.rsplit('/',1)[1]
                if action=='metadata':return self.respond(research.metadata(body.get('database'),body.get('table')))
                if action=='preview':return self.respond(research.preview(body))
                if action in ('analyze','chart'):
                    if action=='analyze' and not model_settings()[2]:raise ValueError('请配置工作台模型')
                    data=research.chart(body) if body.get('x') and body.get('y') else research.preview(body)
                    if not data['rows']:raise ValueError('所选条件没有数据')
                    tid=uuid.uuid4().hex;folder=DATA/'tasks'/tid
                    for name in ('inputs','outputs'):(folder/name).mkdir(parents=True,exist_ok=True)
                    save(folder/'research-input.json',data)
                    job={'id':tid,'module':MODULES['research'],'research':action,'prompt':str(body.get('question','分析该数据的趋势和口径'))[:2000],
                         'status':'queued','result':''}
                    save(folder/'task.json',job)
                    threading.Thread(target=execute,args=(job,),daemon=True).start()
                    return self.respond(job,201)
                return self.respond({'error':'未知研究操作'},404)
            if self.path.startswith('/api/applications/'):
                import application_tools as apps
                body=json.loads(raw)
                action=self.path.rsplit('/',1)[1]
                if action=='update':return self.respond(apps.update(body))
                if action=='import':return self.respond(apps.store(body))
                if action=='job':
                    if not model_settings()[2]:raise ValueError('请先配置工作台模型')
                    options,paths=apps.prepare(body)
                    tid=uuid.uuid4().hex;folder=DATA/'tasks'/tid
                    for name in ('inputs','outputs'):(folder/name).mkdir(parents=True,exist_ok=True)
                    for source in paths:
                        destination=folder/'inputs'/source.parent.name
                        destination.mkdir()
                        shutil.copy2(source,destination/source.name)
                    save(folder/'application-options.json',options)
                    job={'id':tid,'module':MODULES['extend'],'application':True,'prompt':'AI 工坊','status':'queued','result':''}
                    save(folder/'task.json',job)
                    threading.Thread(target=execute,args=(job,),daemon=True).start()
                    return self.respond(job,201)
                return self.respond({'error':'未知应用操作'},404)
            if self.path.startswith('/api/opinion/'):
                import public_opinion as opinion
                body=json.loads(raw)
                action=self.path.rsplit('/',1)[1]
                if action=='save':return self.respond(opinion.configure(body))
                if action=='review':return self.respond(opinion.review(body))
                if action=='brief':return self.respond(opinion.brief(body))
                if action=='run':return self.respond(run_monitor(body.get('id')),201)
                return self.respond({'error':'未知监测操作'},404)
            if self.path=='/api/cross-document/run':
                if not model_settings()[2]:
                    return self.respond({'error':'请先配置工作台模型接口'},400)
                body=json.loads(raw)
                question=body['question']
                ids=body['files']
                if not isinstance(question,str) or not 1<=len(question.strip())<=1000:
                    raise ValueError('请填写问题（1000字以内）')
                if not isinstance(ids,list) or not 2<=len(ids)<=4 or any(not isinstance(fid,str) for fid in ids) or len(set(ids))!=len(ids):
                    raise ValueError('请选择2至4份不同的材料')
                paths=[uploaded_material(fid) for fid in ids]
                tid=uuid.uuid4().hex
                folder=DATA/'tasks'/tid
                for name in ['inputs','outputs']:(folder/name).mkdir(parents=True,exist_ok=True)
                for index,path in enumerate(paths):
                    slot=folder/'inputs'/str(index)
                    slot.mkdir()
                    shutil.copy2(path,slot/path.name)
                job={'id':tid,'module':MODULES['knowledge'],'sentiment':True,'crossDocument':True,
                     'prompt':question.strip(),'status':'queued','result':''}
                save(folder/'task.json',job)
                threading.Thread(target=execute,args=(job,),daemon=True).start()
                return self.respond(job,201)
            if self.path=='/api/sentiment/run':
                from sentiment_tools import options
                if not model_settings()[2]:
                    return self.respond({'error':'请先配置工作台模型接口'},400)
                settings=options(json.loads(raw))
                tid=uuid.uuid4().hex
                folder=DATA/'tasks'/tid
                for name in ['inputs','outputs']:(folder/name).mkdir(parents=True,exist_ok=True)
                save(folder/'sentiment-options.json',settings)
                job={'id':tid,'module':MODULES['research'],'sentiment':True,'prompt':'舆情观察','status':'queued','result':''}
                save(folder/'task.json',job)
                threading.Thread(target=execute,args=(job,),daemon=True).start()
                return self.respond(job,201)
            if self.path.startswith('/api/workshop/'):
                import skill_workshop as workshop
                body=json.loads(raw);action=self.path.split('/')[-1]
                if action=='validate':return self.respond(workshop.validate(body.get('content')))
                if action=='save':return self.respond(workshop.save_version(body.get('content'),body.get('label'),body.get('parent')))
                if action=='import':
                    fid=body.get('fileId')
                    if not isinstance(fid,str) or len(fid)!=32 or not fid.isalnum():raise ValueError('无效上传文件')
                    files=list((DATA/'uploads'/fid).glob('*'))
                    if len(files)!=1:raise ValueError('上传文件不存在')
                    content,assets=workshop.import_bundle(files[0])
                    return self.respond(workshop.save_version(content,'原始导入',assets=assets),201)
                if action=='probe':
                    from mcp_bridge import invoke
                    try:
                        result=invoke(body.get('name'),'tools/list',{})
                        return self.respond({'tools':[{'name':t['name'],'description':str(t.get('description') or '')[:500]} for t in result['tools']], 'hasMore':bool(result.get('nextCursor'))})
                    except Exception:return self.respond({'error':'无法列出工具，请确认该连接已启用且服务可启动。'},400)
                if action=='job':
                    if not status()['sdk'] or not model_settings()[2]:raise ValueError('请先配置 Agent 模型接口')
                    reference=None
                    if body.get('referenceId') and body.get('action')=='create':
                        from material_tools import extract
                        source=extract(uploaded_material(body['referenceId']))
                        reference={'name':source['name'],'text':'\n'.join(block['text'] for block in source['blocks'])[:12000]}
                    options=workshop.job_options(body,reference)
                    tid=uuid.uuid4().hex;folder=DATA/'tasks'/tid;folder.mkdir()
                    (folder/'outputs').mkdir();(folder/'inputs').mkdir()
                    save(folder/'workshop-options.json',options)
                    job={'id':tid,'module':MODULES['extend'],'workshop':options['action'],'prompt':'Skill 创建助手','status':'queued','result':''}
                    save(folder/'task.json',job)
                    threading.Thread(target=execute,args=(job,),daemon=True).start()
                    return self.respond(job,201)
                raise ValueError('无效技能操作')
            if self.path.startswith('/api/reader/'):
                import reader_tools as reader
                body=json.loads(raw);action=self.path.split('/')[-1]
                if action=='import':return self.respond(reader.import_source(body))
                if action=='learn':
                    from learning_tools import create
                    return self.respond(create(body))
                if action=='note':return self.respond(reader.note(body))
                if action=='ask':
                    if not status()['sdk'] or not model_settings()[2]:raise ValueError('请先配置 Agent 模型接口')
                    with reader.LOCK:
                        source,options=reader.prepare(body)
                        if source.get('learning'):
                            for taskfile in (DATA/'tasks').glob('*/task.json'):
                                running=read(taskfile)
                                if (running.get('reader') or {}).get('sid')==source['id'] and running['status'] in ['queued','running']:
                                    raise ValueError('本轮正在处理中，请等待完成后继续')
                        tid=uuid.uuid4().hex;folder=DATA/'tasks'/tid;folder.mkdir()
                        for name in ['reader','inputs','outputs']:(folder/name).mkdir()
                        save(folder/'reader/source.json',source);save(folder/'reader/options.json',options)
                        job={'id':tid,'module':MODULES['knowledge'],'reader':{'sid':source['id']},'learning':bool(options.get('learning')),'prompt':'阅读操作：'+options['mode']+'。问题：'+options['question'],'status':'queued','result':''}
                        save(folder/'task.json',job);threading.Thread(target=execute,args=(job,),daemon=True).start()
                        return self.respond(job,201)
                raise ValueError('无效阅读操作')
            if self.path.startswith('/api/editor/'):
                import onlyoffice_service as office
                body=json.loads(raw);action=self.path.split('/')[-1]
                if action=='open':
                    tid=body.get('taskId','')
                    if not isinstance(tid,str) or not tid.isalnum():raise ValueError('无效任务')
                    return self.respond(office.open_session(DATA/'tasks'/tid))
                if action=='original':return self.respond(office.original_config(body.get('sid')))
                if action=='validate':return self.respond(office.validate_change(body.get('sid'),body))
                if action=='protect':return self.respond(office.protect(body.get('sid'),body))
                if action=='save':return self.respond(office.force_save(body.get('sid')))
                raise ValueError('无效编辑操作')
            if self.path=='/api/screenshot/inspect':
                from screenshot_tools import inspect_image
                return self.respond(inspect_image(uploaded_screenshot(json.loads(raw).get('fileId'))))
            if self.path=='/api/screenshot/export':
                from screenshot_tools import export_tables
                body=json.loads(raw);tid=body.get('taskId','')
                if not isinstance(tid,str) or not tid.isalnum():raise ValueError('无效任务')
                folder=DATA/'tasks'/tid
                if not (folder/'task.json').exists():raise ValueError('任务不存在')
                job=read(folder/'task.json')
                if not job.get('screenshot') or job['status']!='completed' or not (folder/'recognition/result.json').exists():raise ValueError('识别任务尚未完成')
                name=export_tables(folder,body)
                return self.respond({'name':name,'url':'/download/'+tid+'/'+name})
            if self.path=='/api/material/inspect':
                from material_tools import extract
                return self.respond(extract(uploaded_material(json.loads(raw).get('fileId'))))
            if self.path=='/api/material/review':
                body=json.loads(raw);tid=body.get('taskId','')
                if not isinstance(tid,str) or not tid.isalnum():raise ValueError('无效任务')
                folder=DATA/'tasks'/tid
                if not (folder/'task.json').exists() or read(folder/'task.json')['status']!='completed':raise ValueError('任务尚未完成')
                report=read(folder/'outputs/材料体检.json')
                if body.get('issueId') not in [i['id'] for i in report['issues']] or body.get('state') not in ['待复核','已确认','忽略']:raise ValueError('无效复核状态')
                states=read(folder/'review-states.json') if (folder/'review-states.json').exists() else {}
                states[body['issueId']]=body['state'];save(folder/'review-states.json',states)
                return self.respond(states)
            if self.path=='/api/excel/inspect':
                from excel_tools import inspect_book
                body=json.loads(raw)
                return self.respond(inspect_book(uploaded_workbook(body.get('fileId'))))
            if self.path=='/api/upload':
                name=Path(unquote(self.headers.get('X-Filename','file.bin'))).name
                if not name or name in ['.','..']: raise ValueError('无效文件名')
                fid=uuid.uuid4().hex; folder=DATA/'uploads'/fid; folder.mkdir(); (folder/name).write_bytes(raw)
                return self.respond({'id':fid,'name':name,'size':len(raw)})
            if self.path=='/api/tasks':
                body=json.loads(raw)
                if not status()['sdk']: return self.respond({'error':'Harness SDK 尚未安装'},409)
                if not model_settings()[2]: return self.respond({'error':'请先在项目 .env 中配置模型 API 密钥并重启服务'},409)
                if body.get('module') not in MODULES or not str(body.get('prompt','')).strip(): raise ValueError('请选择模块并填写任务')
                institution=body.get('institutionResearch')
                institution_parent=None
                if institution is not None:
                    from institution_research import SECTORS
                    if body['module']!='research' or not isinstance(institution,str) or institution not in SECTORS:
                        raise ValueError('请选择有效的机构分析入口')
                    files=body.get('files',[])
                    if not isinstance(files,list) or len(files)>1:
                        raise ValueError('每次机构分析可附一份材料')
                    if body.get('feature')=='研究简报' or any(body.get(key) is not None for key in OFFICE_TYPES):
                        raise ValueError('请分别提交机构分析与其他任务')
                    for fid in files:uploaded_material(fid)
                    if body.get('institutionParent') is not None:
                        institution_parent=body['institutionParent']
                        if (not isinstance(institution_parent,str) or len(institution_parent)!=32
                                or any(c not in '0123456789abcdef' for c in institution_parent)):
                            raise ValueError('无效的上一轮研究')
                        previous=DATA/'tasks'/institution_parent
                        if not (previous/'outputs/金融机构分析.md').is_file():
                            raise ValueError('上一轮研究尚未完成')
                        parent=read(previous/'task.json')
                        if parent.get('institutionResearch')!=institution or parent.get('status')!='completed':
                            raise ValueError('上一轮研究与当前对话不匹配')
                quick=None
                if body.get('feature')=='研究简报' and body['module']=='research':
                    from financial_quick_research import LEVELS
                    quick=body.get('quickResearch') or {'depth':'标准快评'}
                    if not isinstance(quick,dict) or quick.get('depth') not in LEVELS:raise ValueError('请选择研究深度')
                    parent=quick.get('parent')
                    if parent and (not isinstance(parent,str) or len(parent)!=32 or not parent.isalnum() or not (DATA/'tasks'/parent/'outputs/金融事件快评.md').is_file()):raise ValueError('上一次快评不存在')
                    for fid in body.get('files',[]):uploaded_material(fid)
                options=body.get('standardization')
                excel=body.get('excel')
                material=body.get('material')
                screenshot=body.get('screenshot')
                comparison=body.get('comparison')
                repurpose=body.get('repurpose')
                repurpose_source=None
                if repurpose is not None:
                    from repurpose_tools import validate_options
                    from material_tools import extract
                    if body.get('module')!='office' or any(x is not None for x in [options,excel,material,screenshot,comparison]):raise ValueError('无效一稿多用任务')
                    repurpose=validate_options(repurpose)
                    if not isinstance(body.get('files'),list) or len(body['files'])!=1:raise ValueError('每次上传一份源材料')
                    repurpose_source=extract(uploaded_material(body['files'][0]))
                if comparison is not None:
                    if not isinstance(comparison,dict) or body.get('module')!='office' or any(x is not None for x in [options,excel,material,screenshot]):raise ValueError('无效对比任务')
                    ids=body.get('files')
                    if not isinstance(ids,list) or len(ids)!=2 or len(set(ids))!=2:raise ValueError('请上传旧版和新版')
                    for fid in ids:
                        if not isinstance(fid,str) or not fid.isalnum():raise ValueError('无效文件')
                        found=list((DATA/'uploads'/fid).glob('*'))
                        if len(found)!=1 or found[0].suffix.lower() not in ['.pdf','.doc','.docx']:raise ValueError('仅支持 PDF、DOC、DOCX')
                    comparison={'files':ids}
                if screenshot is not None:
                    from screenshot_tools import inspect_image,config
                    if not isinstance(screenshot,dict) or body.get('module')!='office' or any(x is not None for x in [options,excel,material]):raise ValueError('无效截图任务')
                    if not isinstance(body.get('files'),list) or len(body['files'])!=1:raise ValueError('每次识别一张截图')
                    inspect_image(uploaded_screenshot(body['files'][0]))
                    if not config()['configured']:return self.respond({'error':'请先在项目 .env.vision 中填写截图识别模型密钥并重启服务'},409)
                    screenshot={'mode':config()['mode']}
                if material is not None:
                    from material_tools import validate_options,extract
                    if body.get('module')!='office' or excel is not None or options is not None:raise ValueError('无效材料体检任务')
                    material=validate_options(material)
                    if not isinstance(body.get('files'),list) or len(body['files'])!=1:raise ValueError('每次检查一份材料')
                    extract(uploaded_material(body['files'][0]))
                if excel is not None:
                    from excel_tools import validate_plan
                    if not isinstance(excel,dict) or body.get('module')!='office' or options is not None: raise ValueError('无效 Excel 任务')
                    fid=excel.get('fileId')
                    if body.get('files')!=[fid]: raise ValueError('Excel 任务必须对应一个工作簿')
                    excel={'fileId':fid,'sheets':validate_plan(uploaded_workbook(fid),excel.get('sheets'))}
                template=None
                if options is not None:
                    if not isinstance(options,dict) or options.get('format') not in ['docx','pdf']: raise ValueError('无效输出格式')
                    fids=body.get('files')
                    if body.get('module')!='office' or not isinstance(fids,list) or len(fids) not in (1,2):
                        raise ValueError('请上传一份原始文档，可另附一份自选模板')
                    if any(not isinstance(fid,str) or not fid.isalnum() for fid in fids):
                        raise ValueError('上传文件编号无效')
                    source_files=list((DATA/'uploads'/fids[0]).glob('*'))
                    if len(source_files)!=1 or not source_files[0].is_file():
                        raise ValueError('原始文档不存在，请重新上传')
                    options={**options,'source':fids[0][:6]+'_'+source_files[0].name}
                    if options.get('templateId')!='custom':
                        catalog=json.loads((ROOT/'web/templates/catalog.json').read_text(encoding='utf-8-sig'))
                        entry=next((t for t in catalog if t['id']==options.get('templateId')),None)
                        if not entry: raise ValueError('无效模板')
                        template=ROOT/'skills/document-standardize/assets'/entry['file']
                        if template.suffix.lower()=='.doc':
                            template=template.parent/'docx'/template.with_suffix('.docx').name
                        if not template.is_file(): raise ValueError('模板不存在')
                tid=uuid.uuid4().hex; folder=DATA/'tasks'/tid; folder.mkdir(); (folder/'inputs').mkdir(); (folder/'outputs').mkdir()
                for fid in body.get('files',[]):
                    if not isinstance(fid,str) or not fid.isalnum(): raise ValueError('无效文件')
                    for f in (DATA/'uploads'/fid).glob('*'): shutil.copy2(f,folder/'inputs'/(fid[:6]+'_'+f.name))
                if template:
                    target=folder/'inputs/reference-template'; target.mkdir(); shutil.copy2(template,target/template.name)
                if excel:
                    save(folder/'inputs/chart-plan.json',excel['sheets'])
                if material:
                    from material_tools import prepare
                    source=next((folder/'inputs').iterdir());prepare(source,folder/'review',material)
                if repurpose is not None:
                    (folder/'repurpose').mkdir()
                    save(folder/'repurpose/source.json',repurpose_source)
                    save(folder/'repurpose/options.json',repurpose)
                job={'institutionResearch':institution,'institutionParent':institution_parent,'quickResearch':quick,'repurpose':repurpose,'comparison':comparison,'standardization':options,'excel':excel,'material':material,'screenshot':screenshot,'id':tid,'module':MODULES[body['module']],'prompt':str(body['prompt'])[:20000],'status':'queued','result':''}
                save(folder/'task.json',job)
                ACTIVE_SUBMISSIONS[fingerprint]=tid
                threading.Thread(target=execute,args=(job,),daemon=True).start(); return self.respond(job,201)
            return self.respond({'error':'不存在'},404)
        except (ValueError,TypeError,KeyError) as e: return self.respond({'error':str(e) if isinstance(e,ValueError) else '请求参数无效'},400)
        except Exception: return self.respond({'error':'文件读取失败，请确认文件格式正确、未加密且内容可读取'},400)
if __name__=='__main__':
    for p in (DATA/'tasks').glob('*/task.json'):
        job=read(p)
        if job['status'] in ['running','queued']:
            job.update(status='interrupted',result='服务重启，任务已中断。')
            if job.get('monitorId'):
                from public_opinion import complete
                report=p.parent/'monitor-result.json'
                complete(job['monitorId'],job['id'],read(report) if report.is_file() else {},job['result'],False)
            save(p,job)
    print('智汇工作台 http://127.0.0.1:8765',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
