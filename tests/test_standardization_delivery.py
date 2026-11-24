import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from standardization_delivery import verify


class DeliveryTests(unittest.TestCase):
    def test_word_output_requires_original_text_and_successful_skill_load(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            (folder/'inputs').mkdir()
            (folder/'outputs').mkdir()
            source=folder/'inputs/source.docx'
            target=folder/'outputs/规范文稿.docx'
            def write(path,text):
                with ZipFile(path,'w') as doc:
                    doc.writestr('word/document.xml',
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        '<w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>')
            job={'standardization':{'format':'docx','source':source.name,'templateId':'custom'}}
            events=[{'type':'tool/call','data':{'callId':'1','name':'skill'}},
                    {'type':'tool/result','data':{'message':{'toolCallId':'1','content':[
                        {'type':'text','text':'<skill_content name="office-docx">'}]}}}]
            write(source,'资产100亿元')
            write(target,'资产100亿元')
            verify(job,folder,SimpleNamespace(events=events))
            with self.assertRaisesRegex(ValueError,'未加载'):
                verify(job,folder,SimpleNamespace(events=[]))
            write(target,'资产10亿元')
            with self.assertRaisesRegex(ValueError,'正文一致性'):
                verify(job,folder,SimpleNamespace(events=events))
