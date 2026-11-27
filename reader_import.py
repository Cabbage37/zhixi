"""Article extraction shared by the web reader and reading sessions."""
import ipaddress
import json
import re
import socket
from html import unescape
from urllib.parse import urlparse, urljoin


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('请输入完整的公开网页链接')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except (OSError, ValueError):
        raise ValueError('无法解析网页地址，请检查链接') from None
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('仅支持公开网页地址')
    return url


def extract_article(html, url):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    wechat = urlparse(url).hostname == 'mp.weixin.qq.com'
    heading = soup.select_one('#activity-name') or soup.find('h1')
    metadata = soup.find('meta', property='og:title')
    title = (heading.get_text(' ', strip=True) if heading else '') or (
        metadata.get('content', '').strip() if metadata else ''
    ) or (soup.title.get_text(strip=True) if soup.title else '') or urlparse(url).hostname
    article = soup.select_one('#js_content, .rich_media_content')
    if wechat and article is None:
        raise ValueError('微信未返回文章正文。请在微信中打开原文，复制后使用「粘贴正文」导入。')
    if article is None:
        article = soup.find('article') or soup.find('main') or soup.body or soup
    for tag in article.select('script,style,noscript,iframe,nav,footer,form'):
        tag.decompose()
    for br in article.find_all('br'):
        br.replace_with('\n')
    for block in article.select('p,section,div,li,blockquote,h1,h2,h3,h4,tr'):
        block.append('\n\n')
    content = '\n'.join(line.strip() for line in article.get_text().splitlines()).strip()
    if len(content) < (1 if wechat else 80) or (not wechat and any(
        term in content[:600] for term in ('环境异常', '访问过于频繁', '完成验证后', '该内容已被发布者删除')
    )):
        raise ValueError('网页未返回可读正文，可能需要登录或验证。请打开原文，复制后使用「粘贴正文」导入。')
    return title, '# ' + title + '\n\n来源：' + url + '\n\n' + content


def wechat_collection(url):
    parsed = urlparse(url)
    return parsed.hostname == 'mp.weixin.qq.com' and parsed.path.rstrip('/') == '/mp/homepage'


def extract_collection(html, url):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    articles = {}
    for script in soup.find_all('script'):
        source = script.string or ''
        for match in re.finditer(r'\bcgiData\.(?:appmsg_list|cate_list)\s*=\s*(?=\{)', source):
            try:
                data, _ = json.JSONDecoder().raw_decode(source, match.end())
            except ValueError:
                continue
            rows = data.get('appmsg_list')
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('link'), str) or not isinstance(row.get('title'), str):
                    continue
                try:
                    link = urlparse(urljoin(url, unescape(row['link'])))
                    if (link.scheme in ('http', 'https') and link.netloc == 'mp.weixin.qq.com'
                            and (link.path == '/s' or link.path.startswith('/s/')) and row['title'].strip()):
                        articles[link._replace(scheme='https', fragment='').geturl()] = unescape(row['title']).strip()
                except ValueError:
                    continue
    if not articles:
        raise ValueError('微信合集未返回可用的文章列表。请在微信中打开合集，复制其中一篇文章的链接后导入。')
    return {
        'title': soup.title.get_text(strip=True) if soup.title else '微信公众号合集',
        'articles': [{'url': link, 'title': title} for link, title in list(articles.items())[:200]],
    }


def decode_html(data):
    from bs4 import UnicodeDammit
    decoded = UnicodeDammit(data, is_html=True).unicode_markup
    if not decoded:
        raise ValueError('网页编码无法识别')
    return decoded


def decode_article(data, url):
    if wechat_collection(url):
        raise ValueError('这是微信公众号合集。请在阅读资料库导入合集链接并选择文章。')
    return extract_article(decode_html(data), url)


def fetch_article(url):
    from reader_tools import fetch_public
    final_url, mime, data = fetch_public(url, max_bytes=5*1024*1024)
    if 'text/html' not in mime.lower() and 'application/xhtml' not in mime.lower():
        raise ValueError('该链接不是网页，请下载文件后导入')
    if wechat_collection(final_url):
        return extract_collection(decode_html(data), final_url)
    return decode_article(data, final_url)
