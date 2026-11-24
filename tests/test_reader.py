import json, sys, tempfile, unittest, uuid
from pathlib import Path
from unittest.mock import patch, MagicMock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.runtime/python')]
import reader_tools as reader

class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.patches=[patch.object(reader,'ROOT',self.root),patch.object(reader,'BASE',self.root/'data/readers')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def upload(self,name,data):
        fid=uuid.uuid4().hex;p=self.root/'data/uploads'/fid;p.mkdir(parents=True);(p/name).write_bytes(data)
        return reader.import_source({'fileId':fid})
    def test_import_quote_and_persist(self):
        source=self.upload('研究.txt','收入为120万元。\n增长20%。'.encode())
        cite={'blockId':source['blocks'][0]['id'],'quote':'120万元'}
        self.assertEqual(reader.note({'sid':source['id'],'selection':cite})[0]['quote'],'120万元')
        with self.assertRaises(ValueError):reader.note({'sid':source['id'],'selection':dict(cite,quote='999万元')})
        self.assertEqual(len(reader.state(source['id'])['notes']),1)
    def test_verified_answer_history_and_forgery(self):
        source=self.upload('source.md',b'Net income is 120 million.')
        work=self.root/'task';(work/'reader').mkdir(parents=True)
        reader.save(work/'reader/source.json',source)
        reader.save(work/'reader/options.json',{'mode':'问答','question':'income?'})
        draft={'answer':'120 million [1]','citations':[{'blockId':'b0001','quote':'120 million'}]}
        reader.save(work/'reader/draft.json',draft);reader.finalize(work);reader.finalize(work)
        self.assertEqual(len(reader.state(source['id'])['history']),1)
        _,options=reader.prepare({'sid':source['id'],'question':'增长呢？'})
        self.assertEqual(options['history'][0]['answer'],'120 million [1]')
        draft['citations'][0]['quote']='130 million';reader.save(work/'reader/draft.json',draft)
        with self.assertRaises(ValueError):reader.finalize(work)
    def test_private_addresses_blocked(self):
        for ip in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','224.0.0.1']:
            with patch('socket.getaddrinfo',return_value=[(2,1,6,'',(ip,443))]):
                with self.assertRaises(ValueError):reader.public_address('https://example.com')
        with self.assertRaises(ValueError):reader.public_address('file:///etc/passwd')
    def test_docx_keeps_source_locations(self):
        from scripts.reader_fixture import docx
        source=self.upload('研究.docx',docx(['研究标题','年度收入120万元。']))
        self.assertEqual(source['blocks'][1]['text'],'年度收入120万元。')
        self.assertIn('第2段',source['blocks'][1]['location'])
    def test_ocr_retains_spaces(self):
        from comparison_vision import normalize_lines
        data={'lines':[{'text':'Net income 120 million'}]}
        self.assertEqual(''.join(c['c'] for c in normalize_lines(data,100,100,1,True)),'Net income 120 million')
        self.assertEqual(''.join(c['c'] for c in normalize_lines(data,100,100,1)),'Netincome120million')
    def test_html_import_strips_active_content(self):
        with patch.object(reader,'fetch_public',return_value=('https://example.com','text/html',b'<html><script>bad()</script><main><h1>Report</h1><p>Income 120.</p></main></html>')):
            source=reader.import_source({'url':'https://example.com'})
        self.assertEqual([b['text'] for b in source['blocks']],['Report','Income 120.'])
    def test_redirect_to_private_network_rejected(self):
        response=MagicMock();response.status=302;response.getheader.return_value='http://127.0.0.1/private'
        connection=MagicMock();connection.getresponse.return_value=response
        with patch.object(reader,'public_address',side_effect=[(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit('https://example.com'),443,'93.184.216.34'),ValueError('private')]),patch.object(reader.http.client,'HTTPSConnection',return_value=connection):
            with self.assertRaisesRegex(ValueError,'private'):reader.fetch_public('https://example.com')
        connection.close.assert_called_once()
    def test_chinese_html_without_meta(self):
        with patch.object(reader,'fetch_public',return_value=('https://example.com','text/html; charset=utf-8','<main><p>收入120万元。</p></main>'.encode())):
            source=reader.import_source({'url':'https://example.com'})
        self.assertEqual(source['blocks'][0]['text'],'收入120万元。')

if __name__=='__main__':unittest.main()
