"""Local reading sessions, pinned public URL import and verified source citations."""
import http.client, ipaddress, json, re, shutil, socket, ssl, threading, uuid
from pathlib import Path
from urllib.parse import urlsplit, urljoin

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/readers'
LOCK = threading.RLock()
MODES = ['问答', '总结', '分析', '扩写', '改写']

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def save(path, value):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)

def session(sid):
    if not isinstance(sid, str) or not re.fullmatch(r'[a-f0-9]{32}', sid):
        raise ValueError('无效阅读记录')
    folder = BASE / sid
    if not (folder / 'source.json').is_file():
        raise ValueError('阅读记录不存在，请重新导入')
    return folder, read(folder / 'source.json')

def public_address(url):
    u = urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('仅支持无需登录的公开 HTTP/HTTPS 链接')
    port = u.port or (443 if u.scheme == 'https' else 80)
    if port not in (80, 443):
        raise ValueError('公开链接只支持标准网页端口')
    addresses = socket.getaddrinfo(u.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global or ipaddress.ip_address(a[4][0]).is_multicast for a in addresses):
        raise ValueError('不能导入本机、内网或非公开地址')
    return u, port, addresses[0][4][0]

def fetch_public(url):
    for _ in range(6):
        u, port, address = public_address(url)
        cls = http.client.HTTPSConnection if u.scheme == 'https' else http.client.HTTPConnection
        conn = cls(u.hostname, port, timeout=25)
        # Pin the validated destination while preserving the original TLS hostname.
        conn._create_connection = lambda *a, **k: socket.create_connection((address, port), timeout=25)
        try:
            conn.request('GET', (u.path or '/') + ('?' + u.query if u.query else ''),
                         headers={'User-Agent': 'ZhixiReader/1.0', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location: raise ValueError('网页跳转地址缺失')
                url = urljoin(url, location)
                continue
            if response.status != 200: raise ValueError(f'网页访问失败（HTTP {response.status}），可上传本地文件')
            data = response.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024: raise ValueError('网页内容超过10MB，请上传精简文件')
            return url, response.getheader('Content-Type', ''), data
        except ssl.SSLCertVerificationError:
            raise ValueError('该网站的 HTTPS 证书链未获本机信任；请上传下载后的材料，或由管理员补齐受信任证书。') from None
        except (TimeoutError, OSError, http.client.HTTPException):
            raise ValueError('网页连接失败或超时，请检查链接，或下载后上传材料。') from None
        finally:
            conn.close()
    raise ValueError('网页跳转次数过多')

def import_source(body):
    BASE.mkdir(parents=True, exist_ok=True)
    sid = uuid.uuid4().hex
    folder = BASE / sid
    folder.mkdir()
    try:
        url = str(body.get('url', '')).strip()
        if url:
            url, mime, raw = fetch_public(url)
            if 'application/pdf' in mime or raw.startswith(b'%PDF-'):
                path = folder / 'source.pdf'
                path.write_bytes(raw)
            elif 'text/html' in mime:
                from lxml import html
                charset = re.search(r'charset\s*=\s*["\']?([\w-]+)', mime, re.I)
                encoding = charset.group(1) if charset else None
                if not encoding:
                    try: raw.decode('utf-8'); encoding = 'utf-8'
                    except UnicodeDecodeError: pass
                page = html.fromstring(raw, parser=html.HTMLParser(encoding=encoding))
                for node in page.xpath('//script|//style|//nav|//footer|//header|//noscript|//form'):
                    node.drop_tree()
                main = page.xpath('//article|//main')
                node = main[0] if main else page
                lines = [' '.join(x.text_content().split()) for x in node.xpath('.//h1|.//h2|.//h3|.//p|.//li|.//tr|.//pre')]
                path = folder / 'source.txt'
                path.write_text('\n'.join(lines) or node.text_content(), encoding='utf-8')
            elif 'text/plain' in mime or 'text/markdown' in mime:
                path = folder / 'source.txt'; path.write_bytes(raw)
            else: raise ValueError('链接未返回网页、PDF或文本，请下载后上传')
            name = url
        else:
            fid = body.get('fileId', '')
            if not isinstance(fid, str) or not re.fullmatch(r'[a-f0-9]{32}', fid): raise ValueError('请先上传材料')
            found = list((ROOT / 'data/uploads' / fid).glob('*'))
            if len(found) != 1: raise ValueError('上传文件不存在')
            original = found[0]
            if original.suffix.lower() not in ('.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError('支持 PDF、DOCX、TXT、MD 及 PNG/JPG/WEBP 截图')
            path = folder / ('source' + original.suffix.lower())
            shutil.copyfile(original, path); name = original.name
        if path.suffix in ('.png', '.jpg', '.jpeg', '.webp'):
            from screenshot_tools import inspect_image
            from comparison_vision import transcribe
            import pymupdf
            inspect_image(path)
            pix = pymupdf.Pixmap(str(path))
            png = folder / 'preview.png'; pix.save(str(png))
            chars = transcribe(png, pix.width, pix.height, 1, preserve_spaces=True)
            lines = {}
            for char in chars: lines.setdefault(char['ocrLine'], []).append(char['c'])
            blocks = [{'id': f'b{i+1:04d}', 'location': f'截图第{i+1}行', 'text': ''.join(line)} for i, line in enumerate(lines.values())]
            source = {'blocks': blocks, 'limitations': ['截图文字经多模态转录，可能有识别误差，请结合原图复核。']}
        elif path.suffix == '.pdf':
            import pymupdf
            from comparison_vision import transcribe
            blocks, limitations = [], ['PDF 按页提取，复杂多栏的阅读顺序请结合原件复核。']
            with pymupdf.open(path) as doc:
                if doc.needs_pass: raise ValueError('PDF 已加密，请上传可读取版本')
                if len(doc) > 100: raise ValueError('单份 PDF 最多100页，请拆分导入')
                for page in doc:
                    content = page.get_text(sort=True).strip()
                    if not content:
                        png = folder / f'page-{page.number+1}.png'
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
                        pix.save(str(png))
                        chars = transcribe(png, pix.width, pix.height, page.number+1, preserve_spaces=True)
                        lines = {}
                        for char in chars: lines.setdefault(char['ocrLine'], []).append(char['c'])
                        content = '\n'.join(''.join(line) for line in lines.values())
                        limitations.append(f'第{page.number+1}页经多模态识别，请复核文字与数字。')
                    elif page.get_images():
                        limitations.append(f'第{page.number+1}页的嵌入图片未单独识别。')
                    for part in re.split(r'\n\s*\n', content):
                        if part.strip(): blocks.append({'id': f'b{len(blocks)+1:04d}', 'location': f'第{page.number+1}页', 'text': part.strip()})
            source = {'blocks': blocks, 'limitations': limitations}
        else:
            from material_tools import extract
            source = extract(path)
        if not source['blocks']: raise ValueError('未识别到可阅读文字')
        if sum(len(b['text']) for b in source['blocks']) > 100000 or len(source['blocks']) > 1500:
            raise ValueError('材料超过10万字或1500个文本块，请拆分导入')
        source.update(id=sid, name=name, url=url, kind=path.suffix, notes=[])
        if url: source['limitations'].append('仅提取公开网页静态正文，登录内容和动态加载内容可能缺失。')
        save(folder / 'source.json', source)
        save(folder / 'history.json', [])
        return source
    except Exception:
        # Failed imports retain no partial session visible to the UI.
        if (folder / 'source.json').exists(): (folder / 'source.json').unlink()
        raise

def state(sid):
    folder, source = session(sid)
    source['history'] = history(folder)
    return source

def excerpts():
    """List saved excerpts without returning full documents or chat history."""
    groups = []
    for path in BASE.glob('*/source.json'):
        if not re.fullmatch(r'[a-f0-9]{32}', path.parent.name):
            continue
        source = read(path)
        if not source.get('learning') and source.get('notes'):
            groups.append({'id': path.parent.name, 'name': source['name'], 'notes': source['notes']})
    return sorted(groups, key=lambda group: (group['name'].casefold(), group['id']))

def history(folder):
    legacy = read(folder / 'history.json')
    entries = [read(p) for p in sorted((folder / 'turns').glob('*.json'), key=lambda p: p.stat().st_mtime_ns)]
    return list({h['taskId']: h for h in legacy + entries}.values())

def selection(source, value):
    if not value: return None
    if not isinstance(value, dict): raise ValueError('选区格式无效')
    block = next((b for b in source['blocks'] if b['id'] == value.get('blockId')), None)
    quote = value.get('quote')
    if not block or not isinstance(quote, str) or not quote.strip() or quote not in block['text']:
        raise ValueError('选中文字不在当前原文中，请重新选择')
    return {'blockId': block['id'], 'quote': quote, 'location': block['location']}

def note(body):
    with LOCK:
        folder, source = session(body.get('sid'))
        if body.get('answerId'):
            answer = next((r for r in history(folder) if r.get('taskId') == body['answerId']), None)
            if not answer or not answer.get('citations'):
                raise ValueError('此回答没有可定位的原文依据')
            item = dict(answer['citations'][0], answerId=answer['taskId'], answer=answer['answer'],
                        question=answer['question'], citations=answer['citations'])
        else:
            item = selection(source, body.get('selection'))
        if not item: raise ValueError('请先在原文选择片段')
        if len(source['notes']) >= 500: raise ValueError('单份材料最多保存500条摘录')
        if item not in source['notes']: source['notes'].append(item)
        save(folder / 'source.json', source)
        return source['notes']

def prepare(body):
    folder, source = session(body.get('sid'))
    if source.get('learning'):
        from learning_tools import prepare as prepare_learning
        return source, prepare_learning(source, body, history(folder))
    mode = body.get('mode', '问答')
    question = body.get('question', '')
    if not isinstance(question, str): raise ValueError('问题必须为文字')
    question = question.strip()
    if mode not in MODES or not question or len(question) > 4000: raise ValueError('请选择阅读操作并填写4000字以内的问题')
    selected = selection(source, body.get('selection'))
    prior = history(folder)[-8:]
    return source, {'mode': mode, 'question': question, 'selection': selected, 'history': prior}

def finalize(workspace):
    workspace = Path(workspace)
    source = read(workspace / 'reader/source.json')
    options = read(workspace / 'reader/options.json')
    draft = read(workspace / 'reader/draft.json')
    if options.get('learning'):
        from learning_tools import validate
        result=validate(source, options, draft)
        result.update(mode=options['mode'],question=options['question'],taskId=workspace.name)
        save(workspace/'reader/result.json',result)
        folder,_=session(source['id']);(folder/'turns').mkdir(exist_ok=True)
        save(folder/'turns'/(workspace.name+'.json'),result)
        return result
    if not isinstance(draft, dict) or not isinstance(draft.get('answer'), str) or not draft['answer'].strip() or len(draft['answer']) > 24000:
        raise ValueError('阅读回答格式无效')
    cites = draft.get('citations', [])
    if not isinstance(cites, list) or len(cites) > 30: raise ValueError('引用格式无效')
    verified = [selection(source, c) for c in cites]
    if any(c is None for c in verified): raise ValueError('引用不能为空')
    if not verified and draft.get('insufficient') is not True: raise ValueError('回答缺少可验证原文依据')
    result = {'answer': draft['answer'], 'citations': verified, 'mode': options['mode'], 'question': options['question'], 'taskId': workspace.name, 'insufficient': draft.get('insufficient') is True}
    save(workspace / 'reader/result.json', result)
    with LOCK:
        folder, _ = session(source['id'])
        (folder / 'turns').mkdir(exist_ok=True)
        save(folder / 'turns' / (workspace.name + '.json'), result)
    return result
