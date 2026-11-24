import unittest,io,zipfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_document import locate,replace_range,paragraphs,W,check_locks

def fixture():
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
  z.writestr('word/document.xml','''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="32"/></w:rPr><w:t>办公协同试点汇报</w:t></w:r></w:p><w:p><w:pPr><w:spacing w:line="560" w:lineRule="exact"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="仿宋"/><w:sz w:val="28"/></w:rPr><w:t>本次试点覆盖3个部门，预算120万元。请各部门提</w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>交交材料。</w:t></w:r></w:p><w:p><w:r><w:t>预算尚未审批，第二轮测试日期待确认。</w:t></w:r></w:p><w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:bottom="1440" w:left="1440" w:right="1440"/></w:sectPr></w:body></w:document>''')
 return b.getvalue()
class ReviewDocumentTest(unittest.TestCase):
 def test_cross_run_revision_preserves_package_and_styles(self):
  data=fixture();a=locate(data,'提交交材料')[0];edited=replace_range(data,a,'提交材料')
  with zipfile.ZipFile(io.BytesIO(data)) as old,zipfile.ZipFile(io.BytesIO(edited)) as new:
   for name in old.namelist():
    if name!='word/document.xml':self.assertEqual(old.read(name),new.read(name))
  old,ps=paragraphs(data);new,qs=paragraphs(edited)
  from lxml import etree as ET
  for tag in ['pPr','rPr','sectPr']:
   self.assertEqual([ET.tostring(x) for x in old.iter(W+tag)],[ET.tostring(x) for x in new.iter(W+tag)])
  self.assertIn('提交材料',''.join(new.itertext()));self.assertNotEqual(data,edited)
 def test_stale_anchor_rejected(self):
  data=fixture();a=locate(data,'提交交材料')[0];edited=replace_range(data,a,'提交材料')
  with self.assertRaisesRegex(ValueError,'原文已变化'):replace_range(edited,a,'提交资料')
 def test_locks(self):
  with self.assertRaises(ValueError):check_locks('预算120万元','预算130万元',[],True)
  with self.assertRaises(ValueError):check_locks('招商金控','招商金空',['招商金控'],False)
 def test_duplicate_quote_not_unique(self):
  self.assertGreater(len(locate(fixture(),'预算')),1)
if __name__=='__main__':unittest.main()
