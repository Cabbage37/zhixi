"""Local monitor storage and deterministic public-source collection."""
import hashlib
import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from reader_tools import ROOT, fetch_public, read, save

BASE = ROOT / 'data/public-opinion'
LOCK = threading.RLock()
THEMES = ['香港资本市场', '证券行业', '金融监管', '跨境金融', '财富管理', '券商动态']


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def canonical(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('请输入公开 HTTP/HTTPS 地址')
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith('utm_') and k.lower() not in {'gclid', 'fbclid'})
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or '/', urlencode(query), ''))


def path(mid):
    if not isinstance(mid, str) or not re.fullmatch(r'[0-9a-f]{32}', mid):
        raise ValueError('监测任务无效')
    return BASE / (mid + '.json')


def get(mid):
    file = path(mid)
    if not file.is_file():
        raise ValueError('监测任务不存在')
    return read(file)


def configure(body):
    fields = ('name', 'url', 'source', 'keywords', 'exclude', 'topics', 'frequency', 'language')
    config = {}
    for key in fields:
        value = body.get(key, '')
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError('监测参数无效')
        config[key] = value.strip()
    if not all(config[k] for k in ('name', 'url', 'source', 'topics')):
        raise ValueError('请填写任务名称、地址、来源和主题')
    config['url'] = canonical(config['url'])
    if config['frequency'] not in ('manual', 'daily', 'weekly') or config['language'] not in ('简体中文', '繁體中文', 'English'):
        raise ValueError('频率或语言无效')
    if type(body.get('enabled')) is not bool:
        raise ValueError('启用状态无效')
    config['enabled'] = body['enabled']
    with LOCK:
        mid = body.get('id')
        state = get(mid) if mid else {'id': uuid.uuid4().hex, 'items': [], 'runs': []}
        state['config'] = config
        BASE.mkdir(parents=True, exist_ok=True)
        save(path(state['id']), state)
        return state


def listing():
    return [{'id': s['id'], 'config': s['config']} for s in
            (read(p) for p in sorted(BASE.glob('*.json')))]


def review(body):
    with LOCK:
        state = get(body.get('monitorId'))
        item = next((x for x in state['items'] if x['id'] == body.get('itemId')), None)
        status, category, starred = body.get('status'), body.get('category'), body.get('starred')
        if (item is None or status not in ('pending', 'selected', 'ignored')
                or not isinstance(category, str) or len(category.strip()) > 60 or type(starred) is not bool):
            raise ValueError('复核参数无效')
        item['review'] = {'status': status, 'category': category.strip(), 'starred': starred}
        save(path(state['id']), state)
        return item


def article(data, content_type):
    from lxml import html
    if content_type.lower().startswith('text/plain'):
        return '', '', data.decode('utf-8-sig').strip(), None
    if 'html' not in content_type.lower():
        raise ValueError('来源不是可读取的 HTML 或文本')
    doc = html.fromstring(data)
    title = doc.xpath('normalize-space(string((//article//h1|//main//h1)[1]))') or doc.xpath('normalize-space(string(//title))')
    date = doc.xpath('string((//meta[@property="article:published_time"]/@content|//time/@datetime)[1])')
    if not date:
        date = doc.xpath('normalize-space(string((//*[contains(concat(" ",normalize-space(@class)," ")," article__time ")])[1]))')
    for node in reversed(doc.xpath('//script|//style|//noscript|//nav|//header|//footer|//aside|//form|//*[@role="navigation" or @hidden]')):
        node.drop_tree()
    content = (doc.xpath('//article|//*[@id="article"]')
               or doc.xpath('//main|//*[@role="main"]')
               or doc.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," content-wrapper ")][.//p]')
               or doc.xpath('//body') or [doc])
    text = '\n'.join(' '.join(' '.join(node.itertext()).split()) for node in content).strip()
    return title, date, text, doc


def feed_entries(data):
    from lxml import etree
    root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    def pick(node, *names):
        for name in names:
            for field in node.xpath('./*[local-name()=$name]', name=name):
                value = (field.get('href') if name == 'link' else None) or ''.join(field.itertext()).strip()
                if value and (name != 'link' or field.get('rel', 'alternate') == 'alternate'):
                    return value
        return ''
    return [(pick(n, 'link'), pick(n, 'title'), pick(n, 'pubDate', 'published', 'updated'),
             pick(n, 'encoded', 'content', 'description', 'summary'))
            for n in root.xpath('//*[local-name()="item" or local-name()="entry"]')[:20]]


def collect(config):
    from lxml import etree, html
    final, kind, data = fetch_public(config['url'])
    errors = []
    if 'xml' in kind.lower() or re.match(rb'\s*(?:<\?xml|<rss\b|<feed\b)', data[:500]):
        entries = feed_entries(data)
    else:
        title, date, body, doc = article(data, kind)
        feed = doc.xpath('string((//link[@rel="alternate" and (@type="application/rss+xml" or @type="application/atom+xml")]/@href)[1])') if doc is not None else ''
        if feed:
            try:
                final, kind, data = fetch_public(urljoin(final, feed))
                entries = feed_entries(data)
            except (ValueError, OSError, etree.XMLSyntaxError) as error:
                raise ValueError(f'网站声明的订阅源读取失败：{error}') from error
        else:
            links = doc.xpath('//main//h2//a/@href|//main//h3//a/@href|//article//h2//a/@href|//article//h3//a/@href') if doc is not None else []
            child_urls = list(dict.fromkeys(urljoin(final, link) for link in links))
            child_urls = [u for u in child_urls if urlsplit(u).netloc == urlsplit(final).netloc and u != final]
            entries = [(u, '', '', '') for u in child_urls[:8]] or [(final, title, date, body)]
    is_feed = source_is_feed(kind, data)
    items = []
    for link, title, date, raw in entries:
        try:
            url = canonical(urljoin(final, link)) if link else None
            if not url:
                raise ValueError('订阅条目缺少原文链接')
            body = raw.strip()
            content_kind = '网页正文'
            if is_feed and '<' in body:
                body = html.fragment_fromstring(body, create_parent=True).text_content()
            if not body or is_feed:
                try:
                    actual, media, page = fetch_public(url)
                    page_title, page_date, page_body, _ = article(page, media)
                    if not page_body:
                        raise ValueError('页面没有可提取正文')
                    url, body = canonical(actual), page_body
                    title, date = title or page_title, date or page_date
                except (ValueError, OSError, etree.LxmlError) as error:
                    if not body:
                        raise
                    errors.append(f'{url}：{error}，保留 RSS 提供的内容')
                    content_kind = 'RSS 内容'
            body = body.strip()
            if not body:
                raise ValueError('没有可提取的正文')
            items.append({'id': uuid.uuid4().hex, 'url': url, 'title': (title or url)[:500],
                          'publishedAt': date, 'fetchedAt': now(), 'source': config['source'],
                          'body': body, 'contentKind': content_kind, 'ai': None,
                          'review': {'status': 'pending', 'category': '', 'starred': False}})
        except (ValueError, OSError, etree.LxmlError) as error:
            errors.append(f'{link}：{error}')
    if not items and not errors:
        errors.append('来源没有可读取的条目')
    return items, errors


def source_is_feed(kind, data):
    return 'xml' in kind.lower() or bool(re.match(rb'\s*(?:<\?xml|<rss\b|<feed\b)', data[:500]))


def normalized(text):
    return re.sub(r'[^\w]+', '', text.casefold())


def add_new(items, history, other=()):
    added, duplicates = [], 0
    for item in items:
        item['fingerprint'] = hashlib.sha256(normalized(item['body']).encode()).hexdigest()
        item['clusterId'] = item['id']
        comparisons = [(x, True) for x in history + added] + [(x, False) for x in other]
        for old, local in comparisons:
            same_body = item['fingerprint'] == old['fingerprint']
            title_similarity = SequenceMatcher(None, normalized(item['title']), normalized(old['title'])).ratio()
            same_origin = urlsplit(item['url']).hostname == urlsplit(old['url']).hostname
            if local and ((item['url'] == old['url'] and same_body) or (same_origin and same_body and title_similarity >= .85)):
                duplicates += 1
                break
            if item['clusterId'] == item['id'] and (same_body or title_similarity >= .88 or item['url'] == old['url']):
                item['clusterId'] = old['clusterId']
        else:
            added.append(item)
    return added, duplicates


def analysis(text, candidates):
    value = text.strip()
    if value.startswith('```json') and value.endswith('```'):
        value = value[7:-3].strip()
    rows = json.loads(value)
    expected = {i['id'] for i in candidates}
    clean = {}
    for row in rows if isinstance(rows, list) else []:
        key = row['id']
        if key not in expected or key in clean or type(row['relevant']) is not bool or row['importance'] not in ('高', '中', '低'):
            raise ValueError('模型输出条目或字段无效')
        result = {k: row[k] for k in ('relevant', 'category', 'importance', 'summary', 'reason', 'entities', 'topics')}
        for k, limit in [('category', 60), ('summary', 1200), ('reason', 600)]:
            if not isinstance(result[k], str) or not 1 <= len(result[k].strip()) <= limit:
                raise ValueError('模型输出文字字段无效')
        for k in ('entities', 'topics'):
            if not isinstance(result[k], list) or len(result[k]) > 15 or any(not isinstance(v, str) or len(v)>100 for v in result[k]):
                raise ValueError('模型输出标签无效')
        clean[key] = result
    if set(clean) != expected:
        raise ValueError('模型未完整返回分析结果')
    return clean


def prepare(workspace):
    state = read(workspace / 'monitor-input.json')
    report = {'added': [], 'duplicates': 0, 'errors': [], 'analysis': {}}
    try:
        discovered, report['errors'] = collect(state['config'])
        report['added'], report['duplicates'] = add_new(discovered, state['items'])
        report['readable'] = bool(discovered)
    except Exception as error:
        report['errors'].append(str(error))
        report['readable'] = False
    save(workspace / 'monitor-result.json', report)
    pending = [row for row in state['items'] + report['added'] if row['ai'] is None]
    return state['config'], report, pending


def complete(mid, tid, report, result, success):
    with LOCK:
        state = get(mid)
        run = next((r for r in state['runs'] if r['id'] == tid), None)
        if not run or run['status'] != 'running':
            return
        known = {row['id'] for row in state['items']}
        pending = [row for row in report.get('added', []) if row['id'] not in known]
        if pending:
            other = [item for monitor in listing() if monitor['id'] != mid for item in get(monitor['id'])['items']]
            added, _ = add_new(pending, [], state['items'] + other)
            state['items'].extend(added)
        scores = report.get('analysis', {})
        for row in state['items']:
            if row['id'] in scores:
                row['ai'] = scores[row['id']]
        errors = report.get('errors', [])
        if not success and result and result not in errors:
            errors = [*errors, result]
        run.update(status='completed' if success else 'failed', endedAt=now(),
                   discovered=len(report.get('added', [])), duplicates=report.get('duplicates', 0),
                   included=sum(x['relevant'] for x in scores.values()), errors=errors)
        save(path(mid), state)


def published_day(value):
    if not value:
        return ''
    for parse in (lambda x: datetime.fromisoformat(x.replace('Z', '+00:00')),
                  parsedate_to_datetime, lambda x: datetime.strptime(x, '%B %d, %Y')):
        try:
            return parse(value).date().isoformat()
        except (ValueError, TypeError, AttributeError):
            continue
    return ''


def brief(body):
    kind, refs = body.get('kind'), body.get('items')
    if kind not in ('daily', 'weekly', 'custom') or not isinstance(refs, list) or not 1 <= len(refs) <= 50:
        raise ValueError('请选择简报类型及 1 至 50 条舆情')
    title = body.get('title', '')
    if not isinstance(title, str) or len(title) > 100:
        raise ValueError('标题不可超过100字')
    try:
        end = date.fromisoformat(body.get('date', '')) if kind != 'custom' else None
    except (ValueError, TypeError):
        raise ValueError('请选择有效的简报日期') from None
    start = end - timedelta(days=6 if kind == 'weekly' else 0) if end else None
    label = {'daily': '当日舆情', 'weekly': '舆情周报', 'custom': '舆情简报'}[kind]
    lines = ['# ' + (title.strip() or label)]
    if end:
        lines += ['', f'发布日期范围：{start} 至 {end}']
    states, seen = {}, set()
    count = 0
    for ref in refs:
        mid, iid = ref['monitorId'], ref['itemId']
        if mid not in states:
            states[mid] = {row['id']: row for row in get(mid)['items']}
        row = states[mid].get(iid)
        if not row or not row['ai'] or row['review']['status'] != 'selected':
            raise ValueError('简报只使用已人工入选且有摘要的条目')
        if (mid, iid) in seen:
            continue
        seen.add((mid, iid))
        day = published_day(row['publishedAt'])
        if end and (not day or not str(start) <= day <= str(end)):
            continue
        count += 1
        lines += ['', f'## {count}. {row["title"]}', '', row['ai']['summary'], '',
                  f'来源：{row["source"]}', f'日期：{day or row["publishedAt"] or "发布时间未公开"}',
                  f'原文：{row["url"]}']
    if not count:
        raise ValueError('所选条目中没有符合发布日期范围的内容，可改用自定义简报')
    return {'markdown': '\n'.join(lines), 'count': count, 'excluded': len(seen)-count}
