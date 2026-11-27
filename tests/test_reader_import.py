import io
import zipfile
from pathlib import Path
import pytest
from fastapi import UploadFile, HTTPException
import marginalia_web as reader
from reader_import import extract_article, extract_collection, public_url


def test_markdown_import_retains_table_and_blocks_html(monkeypatch):
    captured = {}
    def dispatch(channel, value):
        with zipfile.ZipFile(value['filePath']) as archive:
            captured['body'] = archive.read('article.xhtml').decode()
            captured['title'] = archive.read('book.opf').decode()
        return {'ok': True}
    monkeypatch.setattr(reader, 'dispatch', dispatch)
    file = UploadFile(filename='银行.md', file=io.BytesIO('# 年报\n\n|指标|值|\n|---|---|\n|收入|12|\n\n<script>alert(1)</script>'.encode()))
    assert reader.import_file(file)['ok']
    assert '<table>' in captured['body']
    assert '<script>' not in captured['body']
    assert '银行' in captured['title']


def test_empty_markdown_rejected():
    with pytest.raises(HTTPException) as error:
        reader.import_markdown('  ', '空白')
    assert error.value.status_code == 422


def test_wechat_article_excludes_chrome():
    title, content = extract_article('<html><title>网页</title><h1 id="activity-name">银行研究</h1><div id="js_content"><p>'+('净息差分析。'*30)+'</p><script>secret()</script></div><footer>导航垃圾</footer></html>', 'https://mp.weixin.qq.com/s/example')
    assert title == '银行研究'
    assert '导航垃圾' not in content and 'secret()' not in content
    assert 'https://mp.weixin.qq.com/s/example' in content


def test_verification_page_rejected():
    with pytest.raises(ValueError, match='验证'):
        extract_article('<body>环境异常，请完成验证后继续'+('说明'*100)+'</body>', 'https://example.com')


def test_wechat_short_article_preserves_paragraphs_and_inline_text():
    title, content = extract_article(
        '<meta property="og:title" content="更新公告"><div class="rich_media_content">'
        '<p>今日<strong>更新</strong>。</p><p>本段提及环境异常。</p></div>',
        'https://mp.weixin.qq.com/s/example',
    )
    assert title == '更新公告'
    assert '今日更新。\n\n本段提及环境异常。' in content
    with pytest.raises(ValueError, match='粘贴正文'):
        extract_article('<body>参数错误' + '微信导航' * 100 + '</body>', 'https://mp.weixin.qq.com/s/example')


def test_pasted_article_keeps_source_without_fetching(monkeypatch):
    monkeypatch.setattr(reader, 'import_markdown', lambda content, title: (title, content))
    url = 'https://mp.weixin.qq.com/s/example'
    assert reader.import_url({'title': '更新公告', 'content': '公告正文。', 'url': url}) == (
        '更新公告', f'来源：{url}\n\n公告正文。',
    )


def test_wechat_homepage_extracts_article_choices_without_executing_scripts():
    page = '''<title>策略合集</title><script>
      cgiData.appmsg_list = {"appmsg_list":[
        {"title":"策略报告","link":"http://mp.weixin.qq.com/s?mid=1&amp;idx=1#rd"},
        {"title":"外站","link":"https://example.com/s/ignored"}
      ]};
      cgiData.cate_list = {"appmsg_list":[
        {"title":"策略报告","link":"https://mp.weixin.qq.com/s?mid=1&idx=1"}
      ]};
      throw new Error("not executed");
    </script>'''
    assert extract_collection(page, 'https://mp.weixin.qq.com/mp/homepage?hid=99') == {
        'title': '策略合集',
        'articles': [{'title': '策略报告', 'url': 'https://mp.weixin.qq.com/s?mid=1&idx=1'}],
    }


def test_local_url_rejected():
    with pytest.raises(ValueError, match='公开'):
        public_url('http://127.0.0.1/admin')


def test_proxy_dns_resolves_to_validated_public_ip(monkeypatch):
    import json
    from unittest.mock import MagicMock
    import reader_tools
    monkeypatch.setattr(reader_tools.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('198.18.0.12',443))])
    connection=MagicMock()
    connection.getresponse.return_value.status=200
    connection.getresponse.return_value.read.return_value=json.dumps({'Answer':[{'type':1,'data':'93.184.216.34'}]}).encode()
    monkeypatch.setattr(reader_tools.http.client,'HTTPSConnection',lambda *a,**k:connection)
    assert reader_tools.public_address('https://example.com')[2]=='93.184.216.34'
    connection.getresponse.return_value.read.return_value=json.dumps({'Answer':[{'type':1,'data':'127.0.0.1'}]}).encode()
    with pytest.raises(ValueError):reader_tools.public_address('https://example.com')
