"""Generate and serve versioned, local Python applications for the workshop."""
import ast
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from application_tools import decode

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/workshop-threads'
PYTHON = ROOT / '.runtime/workshop-python/Scripts/python.exe'
SERVICES = {}
LOCK = threading.Lock()
HTTP = build_opener(ProxyHandler({}))

def stop(process):
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)

def preview_environment():
    env = {k:v for k,v in os.environ.items() if k.upper() in
           {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','LOCALAPPDATA','USERPROFILE','APPDATA'}}
    env.update(PYTHONUTF8='1', NO_PROXY='localhost,127.0.0.1')
    return env

def launch(folder, framework):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    if framework == 'streamlit':
        args = ['-m','streamlit','run','app.py','--server.address=127.0.0.1',
                f'--server.port={port}','--server.headless=true','--browser.gatherUsageStats=false',
                '--server.fileWatcherType=none','--client.toolbarMode=minimal']
    else:
        args = ['app.py']
    env=preview_environment()
    env['ZHIXI_PORT']=str(port)
    with (folder/'preview.log').open('wb') as log:
        process = subprocess.Popen([str(PYTHON),*args],cwd=folder,env=env,stdout=log,
                                   stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(150):
        if process.poll() is not None:
            break
        try:
            with HTTP.open(url+('/_stcore/health' if framework=='streamlit' else '/'),timeout=.5) as r:
                if r.status==200:return process,url
        except OSError:pass
        time.sleep(.2)
    stop(process)
    raise ValueError('本地应用启动失败：'+(folder/'preview.log').read_text('utf8',errors='replace')[-700:])

def preview(thread):
    folder=BASE/uuid.UUID(thread).hex
    with LOCK:
        state=json.loads((folder/'state.json').read_text('utf8'))['localApp']
        key=folder.name
        entry=SERVICES.get(key)
        if entry and entry[0]==state['version'] and entry[1].poll() is None:return entry[2]
        service=launch(folder/'versions'/uuid.UUID(state['version']).hex,state['framework'])
        if entry:stop(entry[1])
        SERVICES[key]=(state['version'],*service)
        return service[1]

def build(harness,state,messages,folder,progress=lambda message: None):
    previous=state.get('localApp')
    framework=previous['framework'] if previous else state['route']
    version=uuid.uuid4().hex
    target=folder/'versions'/version
    target.mkdir(parents=True)
    instructions=('生成一个真实可运行的中文本地应用，只返回完整的 Python 源码，可以使用 python 代码围栏。控制在约180行，避免长篇解释和重复实现。'
        '仅实现方案需要的操作。沿用提供的已有代码并按最新要求修改。不要安装依赖、启动进程、读取环境密钥或任意本机路径。'
        '允许用户上传数据。示例须标注为示例。实时数据必须来自真实可核实来源；失败要明确提示。'
        '当前框架为 '+framework+'。可用 pandas、openpyxl。'
        'Streamlit 直接写页面，不要调用 run。NiceGUI 的输入实时筛选用 on_value_change，回调读取 event.value，清空时处理 None。NiceGUI 使用 from nicegui import ui，最后以单独一行 # START_APP 结束，由宿主启动。')
    context={'方案':state['plan'],'最近消息':messages[-6:]}
    if previous:context['已有代码']=(folder/'versions'/previous['version']/'app.py').read_text('utf8').split('# START_APP')[0]
    prompt=instructions+'\n'+json.dumps(context,ensure_ascii=False)
    session=uuid.uuid4().hex
    for attempt in range(2):
        try:
            progress('正在编写应用代码…' if not attempt else '正在修正未通过验证的代码…')
            result=harness.run(prompt,session_id=session)
            if result.finish_reason=='max-tokens':raise ValueError('代码超出本轮输出长度')
            code=result.final_response.strip()
            if code.startswith('```'):
                code=code.partition('\n')[2].removesuffix('```').strip()
            if not code:raise ValueError('未返回代码')
            if previous:
                for resource in (folder/'versions'/previous['version']).glob('*.csv'):
                    shutil.copyfile(resource,target/resource.name)
            progress('正在检查代码并启动预览…')
            if framework=='nicegui':
                code=code.split('# START_APP')[0]+"\n# START_APP\nimport os\nui.run(host='127.0.0.1', port=int(os.environ['ZHIXI_PORT']), show=False, reload=False)\n"
            ast.parse(code)
            (target/'app.py').write_text(code,'utf8')
            if framework=='streamlit':
                check=subprocess.run([str(PYTHON),'-c',"from streamlit.testing.v1 import AppTest; a=AppTest.from_file('app.py').run(timeout=35); assert not a.exception, [x.message for x in a.exception]"],cwd=target,env=preview_environment(),capture_output=True,timeout=50)
                if check.returncode:raise ValueError(check.stderr.decode(errors='replace')[-850:])
            service=launch(target,framework)
            break
        except (SyntaxError,ValueError,KeyError) as exc:
            if attempt:raise
            prompt='请缩短实现，重新输出完整可运行 Python 源码。错误：'+str(exc)
    with LOCK:
        old=SERVICES.get(folder.name)
        SERVICES[folder.name]=(version,*service)
        if old:stop(old[1])
    return {'version':version,'framework':framework,'name':previous['name'] if previous else state['plan'].splitlines()[0][:60],
            'preview':'/api/workshop-preview/'+folder.name+'?v='+version}
