"""Start the pinned ThinkFlow subapplication on loopback using Zhixi's model settings."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.request import urlopen
from model_settings import model_settings

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "integrations/thinkflow"
DATA = ROOT / "data/thinkflow"
URL = "http://127.0.0.1:18766"
_lock = threading.Lock()
_process = None
_started = 0


def open_thinkflow(retry=False):
    global _process, _started
    try:
        with urlopen(URL + "/zhixi-health", timeout=1) as response:
            if json.load(response).get("application") == "zhixi-thinkflow":
                return {"url": URL, "ready": True}
    except (OSError, ValueError):
        pass
    with _lock:
        if _process is not None:
            if _process.poll() is None:
                if time.monotonic() - _started > 120:
                    raise ValueError("阅读工作区启动超时，请查看 data/thinkflow/service.log。")
                return {"ready": False}
            if not retry:
                raise ValueError("阅读工作区启动失败，详情见 data/thinkflow/service.log。")
        python = ROOT / ".runtime/thinkflow-env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file() or not (SOURCE/"frontend/dist/index.html").is_file():
            raise ValueError("ThinkFlow 尚未安装完整，请运行本地部署步骤。")
        base, model, key = model_settings()
        if not base or not model or not key:
            raise ValueError("请先配置知析的模型接口，再打开阅读工作区。")
        base = base.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", LLM_API_URL=base,
                   DEFAULT_LLM_API_URL=base, LLM_API_KEY=key, LLM_MODEL=model, KB_CHAT_MODEL=model,
                   KB_VLM_MODEL=model, MODEL_GPT_4O=model, PAPER2PPT_DEFAULT_MODEL=model,
                   PAPER2PPT_CONTENT_MODEL=model, PAPER2PPT_OUTLINE_MODEL=model,
                   EMBEDDING_PROVIDER="openai", EMBEDDING_API_URL=base, EMBEDDING_API_KEY=key,
                   EMBEDDING_MODEL="CM-Pub-Qwen3_Embedding", EMBEDDING_DIMENSION="4096")
        DATA.mkdir(parents=True, exist_ok=True)
        with (DATA/"service.log").open("ab") as log:
            _process = subprocess.Popen([str(python), str(ROOT/"thinkflow_service.py")], cwd=SOURCE,
                env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        _started = time.monotonic()
    return {"ready": False}

def import_result(task_id, filename, notebook_id):
    """Import an existing, published Zhixi result using ThinkFlow's normal upload API."""
    import uuid
    import requests
    task = ROOT / "data/tasks" / uuid.UUID(task_id).hex
    directory = (task/"outputs").resolve()
    file = (directory/filename).resolve()
    if (not filename or Path(filename).name != filename or file.parent != directory or
            file.suffix.lower() not in {".pdf",".docx",".md",".txt",".csv",".pptx"} or not file.is_file()):
        raise ValueError("请选择已经生成的阅读材料。")
    if json.loads((task/"task.json").read_text("utf8")).get("status") != "completed":
        raise ValueError("请等待任务完成再导入。")
    index = DATA/"outputs/local/_notebooks.json"
    notebooks = json.loads(index.read_text("utf8")) if index.is_file() else []
    notebook = next((row for row in notebooks if row["id"] == notebook_id), None)
    if notebook is None:
        raise ValueError("请先在阅读助手中新建一个笔记本。")
    if not open_thinkflow(retry=True)["ready"]:
        raise ValueError("阅读工作区正在启动，请稍后再次导入。")
    # Preserve similarly named files from different tasks in the same notebook.
    label = f"{file.stem}-{task.name[:8]}{file.suffix}"
    try:
        with file.open("rb") as stream:
            response = requests.post(URL+"/api/v1/kb/upload", headers={"X-API-Key":os.getenv("THINKFLOW_API_KEY", "")},
                data={"email":"local","user_id":"local","notebook_id":notebook_id,"notebook_title":notebook["name"]},
                files={"file":(label,stream)},timeout=(5,240))
            response.raise_for_status()
            result = response.json()
    except requests.RequestException as error:
        raise ValueError("阅读工作区未能确认导入，请在笔记本中核对来源后重试。") from error
    if not result.get("success"):
        raise ValueError("来源导入失败，请查看阅读工作区。")
    return {"embedded":bool(result.get("embedded")), "id":notebook_id}
