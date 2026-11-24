"""Collect public articles and validate the evidence in an observation report."""
import json
from datetime import datetime
from urllib.parse import urlsplit

from reader_tools import fetch_public


def options(body):
    theme = body.get('theme', '')
    urls = body.get('urls')
    if not isinstance(theme, str) or not 1 <= len(theme.strip()) <= 200:
        raise ValueError('请填写观察主题（200字以内）')
    if not isinstance(urls, list) or not 1 <= len(urls) <= 6:
        raise ValueError('每次可提交1至6个公开网页链接')
    for url in urls:
        if not isinstance(url, str) or len(url) > 2000:
            raise ValueError('网页链接无效')
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('请输入无需登录的公开 HTTP/HTTPS 链接')
    return {'theme': theme.strip(), 'urls': list(dict.fromkeys(urls))}


def collect(settings):
    from lxml import html

    sources, failures = [], []
    for url in settings['urls']:
        try:
            final_url, kind, data = fetch_public(url)
            title = urlsplit(final_url).hostname
            if 'html' in kind.lower():
                doc = html.fromstring(data)
                title = doc.xpath('normalize-space(string(//title))') or title
                for node in doc.xpath('//script|//style|//noscript|//nav|//header|//footer|//aside|//form'):
                    node.drop_tree()
                content = doc.xpath('//article|//main') or doc.xpath('//body') or [doc]
                value = '\n'.join(' '.join(node.itertext()) for node in content)
            elif kind.lower().startswith('text/plain'):
                value = data.decode('utf-8-sig')
            else:
                raise ValueError('仅支持静态 HTML 或 UTF-8 文本网页')
            value = ' '.join(value.split())
            if not value:
                raise ValueError('未提取到网页正文')
            sources.append({'id': len(sources) + 1, 'title': title[:200], 'url': final_url,
                            'text': value[:4000], 'truncated': len(value) > 4000})
        except (ValueError, OSError, UnicodeError) as exc:
            failures.append({'url': url, 'error': str(exc)})
    return {'theme': settings['theme'], 'sources': sources, 'failures': failures,
            'observedAt': datetime.now().astimezone().isoformat(timespec='seconds')}


def finish(evidence, response):
    value = response.strip()
    if value.startswith('```json') and value.endswith('```'):
        value = value[7:-3].strip()
    data = json.loads(value)
    findings = data.get('findings') if isinstance(data, dict) else None
    if not isinstance(findings, list) or len(findings) > 8:
        raise ValueError('模型未返回有效观察条目')
    sources = {s['id']: s for s in evidence['sources']}
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError('观察条目格式不正确')
        sid = finding.get('sourceId')
        quote, summary = finding.get('quote'), finding.get('summary')
        if (type(sid) is not int or sid not in sources or not isinstance(quote, str)
                or not 8 <= len(quote.strip()) <= 300 or quote not in sources[sid]['text']
                or not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 500):
            raise ValueError('观察条目的原文引用未通过校验')
    return {**evidence, 'sources': [{k: v for k, v in s.items() if k != 'text'}
                                   for s in evidence['sources']],
            'findings': [{k: row[k] for k in ('sourceId', 'quote', 'summary')} for row in findings]}
