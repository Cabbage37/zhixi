"""Start the bundled application's own web server without modifying its source."""
import json
import os
from pathlib import Path
import subprocess
import threading
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / 'integrations/full/数据库项目/data-formulator'
URL = 'http://127.0.0.1:5567'
LOCK = threading.Lock()
process = None


def ready():
    try:
        with urlopen(URL + '/api/app-config', timeout=1) as response:
            reply = json.load(response)
        config = reply.get('data') if isinstance(reply, dict) else None
        return isinstance(config, dict) and 'WORKSPACE_BACKEND' in config and 'MAX_DISPLAY_ROWS' in config
    except (OSError, ValueError):
        return False


def open_database(check_only=False):
    global process
    with LOCK:
        if ready():
            return {'url': URL}
        if check_only:
            if process is not None and process.poll() is None:
                return {'starting': True}
            raise ValueError('互动数据库启动中断。请重新打开，详细原因见 data/database-service.log。')
        runtime = ROOT / '.runtime/database-python311/python.exe'
        if not runtime.is_file() or not (PROJECT/'py-src/data_formulator/dist/index.html').is_file():
            raise ValueError('互动数据库工程或 Python 3.11 运行环境尚未就绪。')
        if process is None or process.poll() is not None:
            log = ROOT / 'data/database-service.log'
            with log.open('ab') as stream:
                process = subprocess.Popen([str(runtime), str(ROOT/'database_launcher.py')],
                    cwd=PROJECT, stdout=stream, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW, env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        return {'starting': True}
