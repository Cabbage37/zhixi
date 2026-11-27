"""Local web transport for Marginalia's original library and reading repositories."""
import atexit
import base64
import json
import os
import time
import secrets
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "integrations/marginalia"
DATA = ROOT / "data/marginalia"
router = APIRouter(prefix="/marginalia-api")
_lock = threading.Lock()
_process = None
_port = None
_token = secrets.token_urlsafe(32)
CHANNELS = set("""
library:list library:get library:update library:recently-read library:reorder
progress:get progress:save reading-sessions:start reading-sessions:complete reading-sessions:list reading-sessions:get
content:toc content:chapters content:search content:prepare-search content:chapter-text content:chapter-summary content:book-summary
annotations:list-by-book annotations:create annotations:update annotations:delete
book-notes:list-by-book book-notes:create book-notes:update book-notes:delete
conversations:list-by-book conversations:create conversations:get conversations:delete messages:list-by-conversation
ai:build-chips selectionActions:list selectionActions:create selectionActions:update selectionActions:delete selectionActions:reorder
stats:reading-state stats:get stats:usage
""".split())


def stop():
    if _process and _process.poll() is None:
        _process.terminate()


atexit.register(stop)


def port():
    global _process, _port
    with _lock:
        if _process and _process.poll() is None and _port:
            return _port
        DATA.mkdir(parents=True, exist_ok=True)
        executable = SOURCE / "node_modules/electron/dist/electron.exe"
        env = {k:v for k,v in os.environ.items() if k.upper() in ("PATH","SYSTEMROOT","TEMP","TMP","LOCALAPPDATA","APPDATA","USERPROFILE","WINDIR","COMSPEC","PROGRAMDATA","PROGRAMFILES","PROGRAMFILES(X86)","SYSTEMDRIVE")}
        ready_file = DATA / ("startup-" + secrets.token_hex(8))
        env.update(ZHIXI_READY_FILE=str(ready_file), ZHIXI_READER_DATA=str(DATA), ZHIXI_READER_PARENT=str(os.getpid()), ZHIXI_READER_TOKEN=_token)
        _port = None
        proc = subprocess.Popen([str(executable),str(SOURCE/"zhixi/dist/worker.cjs")], cwd=SOURCE,
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, text=True, encoding="utf8",
            errors="replace", creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        _process = proc
        try:
            for _ in range(250):
                if ready_file.exists() and ready_file.read_text().strip():
                    _port = int(ready_file.read_text())
                    break
                if proc.poll() is not None:
                    break
                time.sleep(.1)
        finally:
            ready_file.unlink(missing_ok=True)
        if not _port:
            stop()
        if not _port:
            raise HTTPException(503,"阅读资料库启动失败")
        return _port


def dispatch(channel, value=None):
    payload = {"channel":channel}
    if value is not None:
        payload["input"] = value
    req = urllib.request.Request(f"http://127.0.0.1:{port()}/invoke",data=json.dumps(payload).encode(),
        headers={"Authorization":"Bearer "+_token,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=90) as resp:
            return json.load(resp)["value"]
    except urllib.error.HTTPError as exc:
        raise HTTPException(400,json.load(exc).get("error","阅读操作失败")) from exc


@router.get("/snapshot")
def snapshot():
    state = dispatch("snapshot")
    model = os.getenv("TABLE_VISION_MODEL")
    if model:
        state["chatModel"] = {"providerId":"zhixi","model":model}
    return state


@router.post("/invoke")
def invoke(payload:dict):
    channel = payload.get("channel")
    if channel == "providers:list":
        model = os.getenv("TABLE_VISION_MODEL")
        return [{"id":"zhixi","label":"知析","type":"anthropic","compatibleApis":["anthropic"],"isBuiltin":True,
                 "keyMask":"已配置" if os.getenv("TABLE_VISION_API_KEY") else None,"baseUrl":None,"models":[model]}] if model else []
    if channel == "preferences:set" and payload.get("input",{}).get("key") in {"readerPrefs","lastHighlightStyle","onboardingDismissed","colorMode","language","readerLayout","pdfZoom","soul","instructions","ttsPrefs","showAgentAvatar","autoScrollSpeed","selectionToolbarLabels"}:
        return dispatch(channel,payload["input"])
    if channel not in CHANNELS:
        raise HTTPException(400,"当前网页阅读器未接入此操作")
    return dispatch(channel,payload.get("input"))


@router.get("/bytes/{book_id}")
def document(book_id:str):
    result = dispatch("library:read-book-bytes",{"bookId":book_id})
    if not result["ok"]:
        raise HTTPException(404,"阅读原件不存在")
    return Response(base64.b64decode(result["base64"]),media_type="application/octet-stream")


@router.post("/import")
def import_file(file: UploadFile):
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in (".pdf",".epub",".md",".markdown",".txt") or ":" in name:
        raise HTTPException(422,"请选择 PDF、EPUB、Markdown 或 TXT 文件")
    with tempfile.TemporaryDirectory() as directory:
        dest = Path(directory)/name
        with dest.open("wb") as output:
            while chunk := file.file.read(1024*1024):
                if output.tell()+len(chunk)>128*1024*1024:
                    raise HTTPException(413,"文件超过 128 MB")
                output.write(chunk)
        if dest.suffix.lower() in (".md", ".markdown", ".txt"):
            try:
                content = dest.read_text("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    content = dest.read_text("gb18030")
                except UnicodeDecodeError:
                    raise HTTPException(422,"文本编码无法识别，请另存为 UTF-8 后重试")
            return import_markdown(content, dest.stem)
        return dispatch("library:import",{"filePath":str(dest)})


@router.post("/import-url")
def import_url(payload: dict):
    from reader_import import fetch_article
    from urllib.parse import urlsplit
    url = payload.get("url")
    if not isinstance(url, str) or len(url) > 8192:
        raise HTTPException(422,"请输入网页链接")
    try:
        if "content" in payload:
            content, title = payload["content"], payload.get("title")
            if not isinstance(title, str) or not title.strip() or len(title) > 300:
                raise ValueError("请输入文章标题（最多 300 字）")
            if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > 5*1024*1024:
                raise ValueError("请粘贴正文，大小不得超过 5 MB")
            url = url.strip()
            if url:
                source = urlsplit(url)
                if source.scheme not in ("http", "https") or not source.hostname or source.username or source.password or any(c.isspace() for c in url):
                    raise ValueError("请输入完整的原文链接")
                content = "来源：" + url + "\n\n" + content
            return import_markdown(content, title.strip())
        article = fetch_article(url.strip())
        if isinstance(article, dict):
            return article
        title, content = article
        return import_markdown(content, title)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    except Exception:
        raise HTTPException(502,"网页暂时无法读取，请稍后重试，或将正文保存为 Markdown 后导入") from None




@router.get("/notes/{book_id}.md")
def export_notes(book_id: str):
    key = {"bookId":book_id}
    book = dispatch("library:get",key)
    if not book:
        raise HTTPException(404,"找不到这份资料")
    lines = ["# " + (book["title"] or "阅读笔记"), "", "资料编号：" + book_id]
    from urllib.parse import urlencode
    reader = "http://127.0.0.1:18766/marginalia/?"
    lines.append("[打开阅读原件]("+reader+urlencode({"book":book_id})+")")
    for row in dispatch("annotations:list-by-book",key):
        lines.append("[返回此处原文]("+reader+urlencode({"book":book_id,"annotation":row["id"]})+")")
        lines.extend(["", "位置：" + row["locatorRange"], "", "> " + row["selectedText"].replace("\n","\n> "), "", row["note"]])
    for row in dispatch("book-notes:list-by-book",key):
        lines.extend(["",row["content"]])
    return Response("\n".join(lines),media_type="text/markdown",headers={"Content-Disposition":"attachment; filename=reading-notes.md"})


def source_catalog():
    from hashlib import sha256
    root = (ROOT / "data/thinkflow/outputs/local").resolve()
    catalog = {}
    for original in root.glob("*/sources/*/original/*"):
        if not original.is_file() or not original.resolve().is_relative_to(root):
            continue
        key = sha256(original.relative_to(root).as_posix().encode()).hexdigest()
        catalog[key] = original
    return catalog


@router.get("/sources")
def sources():
    return [{"id":key,"title":path.name} for key,path in source_catalog().items()]


@router.post("/sources/{source_id}")
def open_source(source_id: str):
    original = source_catalog().get(source_id)
    if not original:
        raise HTTPException(404,"来源不存在")
    if original.suffix.lower() in (".epub",".pdf"):
        return dispatch("library:import",{"filePath":str(original)})
    parsed = next((original.parent.parent/"markdown").glob("*.md"),None)
    if not parsed or not parsed.resolve().is_relative_to(original.parent.parent.resolve()):
        raise HTTPException(409,"请先在素材库完成正文解析")
    return import_markdown(parsed.read_text("utf-8-sig"), original.stem)


def import_markdown(content: str, name: str):
    import zipfile
    from hashlib import sha256
    from html import escape
    from markdown_it import MarkdownIt
    if not content.strip():
        raise HTTPException(422,"资料正文为空，请检查文件")
    source_id = sha256(content.encode("utf8")).hexdigest()
    title = escape(name)
    body = MarkdownIt("commonmark",{"html":False,"xhtmlOut":True}).enable("table").render(content)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/"article.epub"
        with zipfile.ZipFile(path,"w") as archive:
            archive.writestr("mimetype","application/epub+zip")
            archive.writestr("META-INF/container.xml",'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            archive.writestr("book.opf",f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">{source_id}</dc:identifier><dc:title>{title}</dc:title><dc:language>zh</dc:language></metadata><manifest><item id="body" href="article.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="body"/></spine></package>')
            styles='table{border-collapse:collapse;width:100%;margin:1em 0}th,td{border:1px solid #d7dcd9;padding:.5em .75em;text-align:left}th{background:#f3f5f4}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}a{overflow-wrap:anywhere}'
            archive.writestr("article.xhtml",f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title><style>{styles}</style></head><body>{body}</body></html>')
            archive.writestr("nav.xhtml",f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title></head><body><nav epub:type="toc"><ol><li><a href="article.xhtml">{title}</a></li></ol></nav></body></html>')
        return dispatch("library:import",{"filePath":str(path)})

@router.post("/chat")
async def chat(payload:dict):
    import asyncio
    import sys
    from fastapi.responses import StreamingResponse
    conversation_id = payload.get("conversationId")
    stream_id = payload.get("streamId")
    question = payload.get("userText")
    if not isinstance(question,str) or not question.strip() or not stream_id:
        raise HTTPException(422,"请输入阅读问题")
    conversation = await asyncio.to_thread(dispatch,"conversations:get",{"id":conversation_id})
    if not conversation or conversation.get("bookId")!=payload.get("bookId"):
        raise HTTPException(409,"请重新打开当前资料的对话")
    history = await asyncio.to_thread(dispatch,"messages:list-by-conversation",{"conversationId":conversation_id,"limit":12})
    context = {"history":history,"question":question,"location":payload.get("readingContext"),
               "passages":[x.get("content") for x in payload.get("chips",[]) if x.get("state")!="off"]}
    if payload.get("bookId"):
        key = {"bookId":payload["bookId"]}
        context["material"] = await asyncio.to_thread(dispatch,"library:get",key)
        chapters = await asyncio.to_thread(dispatch,"content:chapters",key)
        context["outline"] = [{"id":c["id"],"title":c["title"]} for c in chapters[:80]]
        location = payload.get("readingContext") or {}
        chapter = next((c for c in chapters if c["id"]==location.get("chapterId")),None)
        if not chapter and location.get("page"):
            chapter = next((c for c in chapters if (c.get("startPage") or 1)<=location["page"]<=(c.get("endPage") or 1)),None)
        if chapter:
            context["chapterExcerpt"] = await asyncio.to_thread(dispatch,"content:chapter-text",dict(key,chapterId=chapter["id"],maxChars=5000,offset=location.get("offset") or 0))
    prefs = await asyncio.to_thread(dispatch,"snapshot")
    context["readerInstructions"] = prefs.get("instructions","")
    context["assistant"] = prefs.get("soul",{})
    def save(role,text):
        return dispatch("append",{"conversationId":conversation_id,"role":role,"parts":[{"type":"text","text":text}]})
    def event(kind,**fields):
        return "data: "+json.dumps(dict(streamId=stream_id,type=kind,**fields),ensure_ascii=False)+"\n\n"
    async def generate():
        env = dict(os.environ,PYTHONUTF8="1",PYTHONIOENCODING="utf-8")
        proc = await asyncio.create_subprocess_exec(sys._base_executable,str(ROOT/"marginalia_turn.py"),cwd=ROOT,
            env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            proc.stdin.write(json.dumps(context).encode())
            await proc.stdin.drain()
            proc.stdin.close()
            await asyncio.to_thread(save,"user",question)
            parts = []
            yield event("chunk",chunk={"type":"text-start","id":stream_id})
            async with asyncio.timeout(180):
                async for line in proc.stdout:
                    value=json.loads(line)
                    if value.get("delta"):
                        parts.append(value["delta"])
                        yield event("chunk",chunk={"type":"text-delta","id":stream_id,"delta":parts[-1]})
                if await proc.wait() or not parts:
                    raise ValueError("伴读执行失败，请检查模型连接后重试")
            await asyncio.to_thread(save,"assistant","".join(parts))
            yield event("chunk",chunk={"type":"text-end","id":stream_id})
            yield event("finish")
        except TimeoutError:
            yield event("error",message="伴读响应超时，请重试")
        except (ValueError,OSError):
            yield event("error",message="伴读未能完成，请检查模型连接后重试")
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
    return StreamingResponse(generate(),media_type="text/event-stream",headers={"Cache-Control":"no-store"})

@router.get("/notebooks")
def notebooks():
    path = ROOT/"data/thinkflow/outputs/local/_notebooks.json"
    return [{"id":x["id"],"name":x["name"]} for x in json.loads(path.read_text("utf8"))] if path.exists() else []


@router.post("/knowledge")
def save_knowledge(payload:dict):
    import requests
    from thinkflow_bridge import URL
    notebook = next((x for x in notebooks() if x["id"]==payload.get("notebookId")),None)
    if notebook is None:
        raise HTTPException(404,"找不到目标笔记本")
    book_id = payload.get("bookId","")
    notes = export_notes(book_id)
    if not dispatch("book-notes:list-by-book",{"bookId":book_id}) and not dispatch("annotations:list-by-book",{"bookId":book_id}):
        raise HTTPException(422,"请先保存一条笔记或批注")
    resp = requests.post(URL+"/api/v1/kb/upload",headers={"X-API-Key":os.getenv("THINKFLOW_API_KEY", "")},
        data={"email":"local","user_id":"local","notebook_id":notebook["id"],"notebook_title":notebook["name"]},
        files={"file":("阅读笔记-"+book_id[:12]+".md",notes.body,"text/markdown")},timeout=(5,240))
    if not resp.ok or not resp.json().get("success"):
        raise HTTPException(502,"笔记本未确认保存，请核对来源记录")
    return {"embedded":bool(resp.json().get("embedded"))}

@router.get("/cover/{book_id}")
def book_cover(book_id: str):
    hit = dispatch("cover", {"bookId":book_id})
    if not hit:
        raise HTTPException(404,"此资料没有封面")
    return Response(base64.b64decode(hit["data"]), media_type=hit["mime"])
