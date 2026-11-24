"""Evidence collection and analysis for financial event briefs."""
import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from financial_quantities import unsupported_quantities
from urllib.parse import parse_qs, urlencode, urlsplit, urljoin

from lxml import etree, html
from application_tools import decode
from public_opinion import article, feed_entries
from reader_tools import fetch_public

ROOT = Path(__file__).resolve().parent
LEVELS = {'快速了解': (2, 3), '标准快评': (3, 4), '深度研究': (4, 6)}
PRIMARY = ('federalreserve.gov', 'hkma.gov.hk', 'sfc.hk', 'hkexnews.hk', 'hkex.com.hk',
           'sec.gov', 'pbc.gov.cn', 'csrc.gov.cn', 'sse.com.cn', 'szse.cn', 'gov.cn', 'ecb.europa.eu', 'mof.gov.cn', 'boc.cn')
SECTIONS = ('分析判断', '已披露事实', '媒体观点', '待核实事项')


def official(url):
    host = urlsplit(url).hostname or ''
    return any(host == domain or host.endswith('.' + domain) for domain in PRIMARY)


def search(query):
    url = 'https://cn.bing.com/search?' + urlencode({'q': query})
    _, _, data = fetch_public(url)
    doc = html.fromstring(data, parser=html.HTMLParser(encoding='utf-8'))
    hits = []
    for a in doc.xpath('//li[contains(@class,"b_algo")]//h2/a[@href]')[:8]:
        link = a.get('href')
        if urlsplit(link).path.startswith('/ck/'):
            value = parse_qs(urlsplit(link).query).get('u', [''])[0]
            if not value.startswith('a1'):
                continue
            try:
                link = base64.urlsafe_b64decode(value[2:] + '===').decode()
            except (ValueError, UnicodeError):
                continue
        if link.startswith(('https://', 'http://')):
            hits.append((link, a.text_content().strip()))
    return hits


def search_rss(query):
    url = 'https://www.bing.com/search?' + urlencode({'q': query, 'format': 'rss'})
    _, _, data = fetch_public(url)
    return [(link, title) for link, title, _, _ in feed_entries(data)
            if urlsplit(link).scheme in ('http', 'https')][:10]


def search_360(query):
    url = 'https://www.so.com/s?' + urlencode({'q': query})
    _, _, data = fetch_public(url)
    doc = html.fromstring(data, parser=html.HTMLParser(encoding='utf-8'))
    return [(a.get('data-mdurl'), ' '.join(a.text_content().split()))
            for a in doc.xpath('//h3/a[@data-mdurl]')[:12]
            if urlsplit(a.get('data-mdurl')).scheme in ('http', 'https')]


def discovery_queries(question):
    topic = re.sub(r'[？?。]+$', '', question.strip())
    # Pasted Chinese text may contain line-wrap marks inside words.
    topic = re.sub(r'(?<=[\u3400-\u9fff])[:：]?\s*[\\\r\n]+\s*(?=[\u3400-\u9fff])', '', topic)
    topic = re.sub(r'(?<=[\u3400-\u9fff]):(?=[\u3400-\u9fff])', '', topic)
    topic = re.sub(r'(意味着什么|有何特别.*|有什么影响|如何解读)$', '', topic).strip('，, ')
    short = re.sub(r'协助|成功|首笔|首次', ' ', topic)
    return list(dict.fromkeys([topic[:180], ' '.join(short.split())[:150]]))


def discover(queries):
    jobs = [(name, query, provider) for query in queries
            for name, provider in (('Bing 网页', search), ('Bing RSS', search_rss),
                                   ('360 搜索', search_360))]

    def lookup(job):
        name, query, provider = job
        try:
            return dict(provider=name, query=query, hits=provider(query))
        except (ValueError, OSError, etree.LxmlError) as error:
            return dict(provider=name, query=query, hits=[], error=type(error).__name__)

    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        return list(pool.map(lookup, jobs))


def notices(question):
    hits = []
    if re.search(r'美联储|联邦储备|FOMC|Federal Reserve', question, re.I):
        data = fetch_public('https://www.federalreserve.gov/feeds/press_monetary.xml')[2]
        hits.extend((url, title + ' · ' + day) for url, title, day, _ in feed_entries(data)[:20])
    if re.search(r'香港|金管局|HKMA|Hong Kong', question, re.I):
        data = fetch_public('https://api.hkma.gov.hk/public/press-releases?lang=en')[2]
        for record in json.loads(data)['result']['records'][:40]:
            hits.append((record['link'], record['title'] + ' · ' + str(record.get('date', ''))))
    return hits


def research_skill_context(names):
    import hashlib
    upstream = ROOT / 'skills/financial-quick-research/upstream'
    manifest = json.loads((upstream / 'openai.json').read_text(encoding='utf8'))
    default_package = (Path.home() / '.codex/plugins/cache/openai-curated-remote'
                       / 'public-equity-investing' / manifest['version'])
    package = Path(os.getenv('ZHIXI_EQUITY_SKILL_PACKAGE', str(default_package)))
    documents, records = [], []
    for name in names:
        if name in manifest['skills']:
            plugin = package / '.codex-plugin/plugin.json'
            if not plugin.is_file() or json.loads(plugin.read_text(encoding='utf-8-sig')).get('version') != manifest['version']:
                raise ValueError('快速研究需要已安装的金融研究 Skill 包 0.1.31。')
            folder = package / 'skills' / name
            metadata = {key: manifest[key] for key in ('source', 'version', 'license')}
        else:
            folder = upstream / name
            metadata = json.loads((folder / 'SOURCE.json').read_text(encoding='utf-8-sig'))
        files = [folder / 'SKILL.md']
        if name == 'deep-research':
            files.append(folder / 'references/researcher.md')
        for path in files:
            raw = path.read_bytes()
            relative = path.relative_to(folder).as_posix()
            body = raw.decode('utf-8-sig')
            headings = {'deep-research': ('Critical Rules', 'Guardrails'),
                        'event-driven-analyzer': ('Required Posture', 'Final QA'),
                        'economic-impact-report': ('Causal Spine', 'Non-Negotiables'),
                        'memo-builder': ('Default Memo Spine', 'QA')}
            if name in headings and relative == 'SKILL.md':
                sections = re.split(r'(?m)(?=^## )', body)
                body = '\n'.join(section for section in sections
                                 if section.split('\n', 1)[0].removeprefix('## ').strip() in headings[name])
                if not body:
                    raise ValueError(f'{name} 缺少所需研究章节')
            if relative == 'references/researcher.md':
                body = body[:1800]
            documents.append(f'\n--- {name}/{relative} ---\n' + body)
            records.append(dict(skill=name, file=relative, chars=len(body),
                                sha256=hashlib.sha256(raw).hexdigest(), **metadata))
    return ''.join(documents), records


def subscription_wording(claim, quotes):
    """Keep total subscriptions / issuance distinct from excess subscriptions."""
    evidence = ''.join(quotes)
    def clarify(match):
        ratio = match.group(1)
        if '发行金额的' + ratio + '倍' in evidence and '超额认购倍数' not in evidence:
            return '总认购金额为发行金额的' + ratio + '倍'
        return match.group()
    return re.sub(r'超额认购倍数(?:达|为|达到)\s*(\d+(?:\.\d+)?)倍', clarify, claim)


def run(job, folder):
    from evidence_writing import ask as request_json
    from time import monotonic
    from material_tools import extract
    from server import save
    options = job['quickResearch']
    question = job['prompt']
    levels, quota = LEVELS[options['depth']]
    sources, seen, audit = [], set(), []
    progress = folder / 'research-progress.json'


    invocations = []
    topic = discovery_queries(question)[0]
    impact = bool(re.search(r'主权债|宏观|政策|利率|降息|加息|汇率|商品|央行|FOMC', topic + ' ' + question, re.I))
    analysis_skills = ['event-driven-analyzer'] + (['economic-impact-report'] if impact else [])

    def ask(instruction, data, stage='selection', upstream=('deep-research',)):
        skill_text, records = research_skill_context(upstream)
        invocation = dict(stage=stage, upstream=records, status='submitted')
        invocations.append(invocation)
        save(folder/'research-skill-trace.json', invocations)
        adaptation = ('上游原件只提供研究方法。宿主执行搜索和文件操作。不要调用工具、子代理、外部数据账户，'
                      '不要执行脚本或使用上游交付模板。服从当前阶段的 JSON 契约。'
                      '窄问题以直接的一手披露为准，只有可能改变结论的缺口才继续查证。'
                      '如果用户问“能否据此推断”，核验该材料是否提供推断所需的信息即可。'
                      '材料只披露程序或日程时，可以直接判断它无法指示决策方向；'
                      '无需寻找对未来结果的预测、背景动机或核验并未用于回答的媒体说法。')

        started = monotonic()
        try:
            value = request_json(folder, 'financial-quick-research',
                                 skill_text + '\n' + adaptation + '\n日期 ' + str(date.today()) + '\n' + instruction,
                                 data, alternate=options.get('alternate'))
            if not isinstance(value, dict):
                raise ValueError('研究模型返回了非对象结果')
        except Exception:
            invocation.update(status='failed', seconds=round(monotonic()-started, 1))
            save(folder/'research-skill-trace.json', invocations)
            raise
        invocation['seconds'] = round(monotonic()-started, 1)
        invocation['status'] = 'returned'
        save(folder/'research-skill-trace.json', invocations)
        return value

    related = {}

    def read_hit(hit):
        try:
            url, ct, raw = fetch_public(hit[0])
            title, day, body, doc = article(raw, ct)
            links = {}
            if doc is not None:
                for a in doc.xpath('//article//a[@href]|//main//a[@href]|//p/a[@href]'):
                    href = urljoin(url, a.get('href')).split('#')[0]
                    label = ' '.join(a.text_content().split())
                    if href.startswith(('https://','http://')) and len(label) >= 4 and href != url:
                        links[href] = label[:160]
                    if len(links) >= 24:
                        break
            if len(body.strip()) >= 80:
                return dict(url=url, title=title or hit[1], date=day, text=body[:14000], links=links)
        except (ValueError, OSError, etree.LxmlError) as error:
            return {'readError': type(error).__name__}
        return {'readError': '正文不足80字符'}

    parent = options.get('parent')
    previous = ''
    if parent:
        previous = (folder.parent / parent / 'outputs/金融事件快评.md').read_text(encoding='utf-8')[:7000]
    context = {'问题': question, '上次快评': previous}
    if previous:
        for line in previous.splitlines():
            match = re.match(r'^〔\d+〕 (.*?) (https?://\S+)$', line)
            if match:
                related[match[2]] = match[1]
    broad = discovery_queries(question) or [question[:180]]
    queries = broad[:]
    searched = set()
    if job.get('previousId') and (folder/'research-evidence.json').is_file():
        sources = json.loads((folder/'research-evidence.json').read_text(encoding='utf-8'))
        audit = json.loads((folder/'research-trace.json').read_text(encoding='utf-8'))
    for turn in range(0 if sources else levels):
        save(progress, {'message': f'第 {turn+1} 轮检索与核验，已读取 {len(sources)} 份原文'})
        hits = {}
        results = discover(queries)
        errors = [result['error'] for result in results if 'error' in result]
        successful = list(dict.fromkeys(result['query'] for result in results if 'error' not in result))
        searched.update(query.casefold().strip() for query in queries)
        for rank in range(max((len(result['hits']) for result in results), default=0)):
            for result in results:
                if rank < len(result['hits']):
                    url, title = result['hits'][rank]
                    hits.setdefault(url, title)
        for url, title in related.items():
            hits.setdefault(url, title)
        if turn == 0:
            try:
                hits.update(dict(notices(question + previous[:200])))
            except (KeyError, ValueError, OSError, etree.LxmlError) as error:
                errors.append(type(error).__name__)
            if options.get('url'):
                hits[options['url']] = '用户选中的舆情原文'
        choices = [(url,title) for url,title in hits.items() if url not in seen and (urlsplit(url).path.strip('/') or urlsplit(url).query) and urlsplit(url).path.rstrip('/') not in ('/index.htm', '/index.html')]
        selection = ask('根据问题和已有证据，从候选中选择最相关、时效合适且互补的原文，同等相关时优先一手披露。专业媒体、行业报道和转载可作为线索，即便还不能证明关键事实，也应读取能提供名称、日期或原文标题的页面。只返回 {"ids":[从0开始的序号]}，无关可返回空。',
                        {**context, '已有原文':[s['title'] for s in sources], '候选':[(i,title,urlsplit(url).hostname) for i,(url,title) in enumerate(choices)]}) if choices else {}
        wanted = [choices[i] for i in dict.fromkeys(selection.get('ids', [])) if type(i) is int and 0 <= i < len(choices)][:quota]
        unread = []
        with ThreadPoolExecutor(max_workers=quota) as pool:
            for hit, source in zip(wanted, pool.map(read_hit, wanted)):
                if 'readError' in source:
                    unread.append({'url': hit[0], 'reason': source['readError']})
                    continue
                seen.add(hit[0])
                if source and source['url'] not in [s['url'] for s in sources]:
                    related.update(source.pop('links'))
                    source['id'] = len(sources)+1
                    sources.append(source)
        audit.append(dict(queries=queries, successful=successful, providers=[{**r, 'hits':len(r['hits'])} for r in results], leads=choices[:24], candidates=len(choices), attempted=wanted, unread=unread, total=len(sources), errors=errors))
        save(folder/'research-trace.json', audit)
        if sources or turn+1 < levels:
            plan = ask('核验核心事实及因果依据。只列会改变对用户核心问题回答的未解决缺口 gaps；明确区分问题已由来源回答与来源本身无法支持某项推断，后者也可以是已解决的判断。逐份判断是否提供关键新事实、独立核验或改变判断，给出有效来源编号 materialSources，根据原文、可见候选标题及尚未命中的线索生成不同角度的检索词：主体简称或英文、完整标题、时间与地点。优先派生不限制域名的查询，再用 site: 核验明确的发布方。若证据充分，给出支撑核心结论的已读来源编号 supportedBy，并说明独立交叉核验或一手直接披露的依据 verification。返回 {"queries":[],"gaps":[],"supportedBy":[],"materialSources":[],"verification":"","complete":false}。',
                       {**context, '已检索':audit, '证据':[{'id':s['id'],'url':s['url'],'title':s['title'],'text':s['text'][:3000]} for s in sources]}, 'assessment', ('deep-research', *analysis_skills))
            if plan.get('complete') is True and plan.get('gaps') and plan.get('supportedBy'):
                decision = ask('你的判断同时给出了“已充分”和“仍有缺口”。逐项复核：若补查结果不同，'
                               '是否会改变对用户原问题的回答？只保留会改变回答的缺口，'
                               '去掉用于回答扩展问题的材料。返回 {"gaps":["必要缺口"]}，可为空。',
                               {**context, '核验判断':plan}, 'resolve-gaps', ('deep-research',))
                gaps = decision.get('gaps')
                if isinstance(gaps, list) and all(isinstance(g, str) for g in gaps):
                    audit[-1]['proposedGaps'] = plan['gaps']
                    plan['gaps'] = gaps
            audit[-1]['assessment'] = plan
            save(folder/'research-trace.json', audit)
            if (plan.get('complete') is True and plan.get('gaps') == []
                    and plan.get('verification') and any(type(i) is int and 1 <= i <= len(sources)
                    for i in (plan.get('supportedBy') or []) if type(i) is int and 1 <= i <= len(sources) and official(sources[i-1]['url']))):
                audit[-1]['stop'] = '关键问题已有一手依据'
                save(folder/'research-trace.json', audit)
                break
            if turn+1 == levels:
                audit[-1]['stop'] = '达到研究深度上限'
                save(folder/'research-trace.json', audit)
                break
            proposed = plan.get('queries') or []
            fallback = [broad[0][:140] + suffix for suffix in
                        (' 新闻报道', ' 事件 时间 地点', ' announcement news')]
            queries = []
            options_to_search = (proposed if isinstance(proposed, list) else []) + fallback
            for q in options_to_search:
                if not isinstance(q, str):
                    continue
                q = q.strip()[:240]
                if q and q.casefold() not in searched and q not in queries:
                    queries.append(q)
                if len(queries) == 4:
                    break
            queries.sort(key=lambda q: 'site:' in q.casefold())
            if not queries:
                break
    if not sources:
        if sum(bool(r['successful']) for r in audit) < 2:
            raise ValueError('检索或访问受阻，未完成充分核验。请稍后重试。')
        raise ValueError('多轮检索仍未取得可引用的公开原文。可补充主体全称、日期或公告链接继续查证。')
    save(folder/'research-evidence.json', sources)
    # Keep a usable record of the completed verification if the writing service goes offline.
    assessment = audit[-1].get('assessment', {})
    checkpoint = folder / 'outputs/已核验证据（快评生成前）.md'
    notes = ['# ' + question, '', '## 阶段性核验记录', '',
             str(assessment.get('verification') or '已取得以下来源，尚待综合判断。'), '', '## 已读取来源']
    for source in sources:
        notes.append(f"- {source['title']} {source['url']}")
    checkpoint.write_text('\n'.join(notes), encoding='utf-8')
    for path in (folder/'inputs').iterdir():
        content = ' '.join(b['text'] for b in extract(path)['blocks'])
        sources.append(dict(id=len(sources)+1, title=path.name[7:], url='', date='', text=content[:14000]))
    save(progress, {'message':'正在核对引文并撰写快评'})
    instruction = ('输出 {"title":"标题","items":[{"section":"已披露事实/媒体观点/分析判断/待核实事项 中的一种",'
                   '"text":"一条简洁判断","evidence":[{"id":1,"quote":"逐字摘自该来源的短句"}]}]}。'
                   '先写一条无需复述数字的分析判断，回答该事件对用户所问主体的具体意义。不得把普通商业银行写成多边金融机构，不得以认购倍数推断创纪录。每条事实、观点和判断均附原文摘引；谨慎使用未核实数字。待核实事项可无引文。'
                   '先直接回答用户的问题。仅对检索记录中已针对性补查但仍无可靠证据的问题使用待核实事项，并列明查过哪些渠道。检索失败不构成反证。请单列分析判断，以简短连续的原文片段支撑影响分析，引用不可使用省略号拼接。如事件前提未获证实，直接说明。输出中文。')
    cited_ids = set()
    instruction += '判断的强度应匹配引文：一次参与交易只能说明本次角色与能力，不能证明长期竞争优势、角色转型或未来业务增长。'
    instruction += ('当一手披露和媒体报道支持同一事实时，优先引用一手披露的原文。'
                    '涉及动机或市场影响的媒体判断只放在“媒体观点”。'
                    '若用户问能否根据公告推断未来决策，“分析判断”首条只回答公告本身能支持什么，'
                    '直接引用公告，不加入改革动机、人物归因或市场预期。')
    primary_ids=[s['id'] for s in sources if s.get('url') and official(s['url'])]
    report = ask(instruction, {**context, '来源':sources, '一手机构来源编号':primary_ids, '关键缺口':assessment.get('gaps', []),
                               '已查渠道':[[r['queries'],r['attempted']] for r in audit]},
                 'brief', ('research-brief', 'memo-builder'))
    lines = ['# ' + question, '', '研究问题：'+question, '', '研究日期：'+str(date.today())]
    evidence_for_lead = []
    valid = 0
    skipped = 0
    for section in SECTIONS:
        entries = []
        for item in report['items']:
            if item['section'] != section:
                continue
            refs = []
            for ref in item.get('evidence', []):
                idx, quote = ref.get('id'), str(ref.get('quote','')).strip()
                if type(idx) is int and 1 <= idx <= len(sources) and len(quote)>=4:
                    s = sources[idx-1]
                    if ''.join(quote.split()) in ''.join(s['text'].split()):
                        refs.append((idx,quote))
            if section != '待核实事项':
                unsupported_record = re.search(r'创新高|创下.{0,8}纪录|创历史|刷新.{0,8}纪录',item['text']) and not any(
                    re.search(r'纪录|新高|历史最高', q) for _,q in refs)
                if not refs or unsupported_record or unsupported_quantities(item['text'], (q for _, q in refs)):
                    skipped += 1
                    continue
            if section != '待核实事项' and refs and any(sources[i-1]['url'] for i,_ in refs):
                valid += 1
                evidence_for_lead.extend(ref for ref in refs if ref not in evidence_for_lead)
            ids = list(dict.fromkeys(i for i,_ in refs))
            cited_ids.update(ids)
            label = '（单一公开来源）' if len(ids)==1 and sources[ids[0]-1]['url'] else ''
            claim = subscription_wording(item['text'], (q for _,q in refs))
            entries.append('- '+claim+' '+''.join(f'〔{i}〕' for i in ids)+label)
            for i,q in refs:
                entries.append('  原文〔'+str(i)+'〕 '+q)
        if section == '待核实事项' and (len(audit) < 2 or not audit[-1].get('assessment', {}).get('gaps')):
            continue
        if entries:
            lines.extend(['','## '+section,*entries])
    if not valid:
        raise ValueError('模型未提供可在公开原文中定位的依据，本次未出具快评。')
    if '## 分析判断' not in lines:
        repair = ask('根据所附已核验引文直接回答问题，用一至两句说明对具体主体的意义及判断边界。不要重复数字或添加新事实。返回 {"text":"判断","refs":[从1开始的引文编号]}。',
                     {'问题':question,'引文':dict(enumerate((q for _,q in evidence_for_lead),1))},
                     'repair-lead', ('research-brief',))
        lead = repair.get('text')
        picked = [evidence_for_lead[i-1] for i in repair.get('refs',[])
                  if type(i) is int and 1 <= i <= len(evidence_for_lead)]
        if not isinstance(lead,str) or not lead.strip() or not picked or unsupported_quantities(lead,(q for _,q in picked)):
            raise ValueError('核心判断未通过引文校验，核验记录已保存，可恢复出稿。')
        lines[5:5] = ['', '## 分析判断', '- '+lead+' '+''.join(f'〔{i}〕' for i in dict.fromkeys(i for i,_ in picked)),
                      *(f'  原文〔{i}〕 {q}' for i,q in picked)]
    if skipped:
        lines.extend(['',f'有 {skipped} 条草稿判断缺少可定位的引文或数字依据，已略去。'])
    lines.extend(['','## 来源'])
    for s in sources:
        if s['id'] not in cited_ids:
            continue
        lines.append(f"〔{s['id']}〕 {s['title']} {s['date']} {s['url'] or '（本地补充材料）'}")
    output = '\n'.join(lines)
    (folder/'outputs/金融事件快评.md').write_text(output,encoding='utf-8')
    checkpoint.unlink(missing_ok=True)
    print(output)
